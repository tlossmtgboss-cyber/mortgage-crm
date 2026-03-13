"""
Test Fraud Access Control — BSA/SAR Tipping Prevention

Verifies that fraud detection data is properly access-controlled to prevent
SAR tipping (a federal crime under 31 USC 5318(g)(2)).

Tests:
- Portal users get RESTRICTED access (no fraud data whatsoever)
- Regular internal users get SUMMARY access (risk score only)
- Compliance officers get FULL access (all indicators)
- filter_fraud_response removes fraud indicators for SUMMARY
- filter_fraud_response removes everything for RESTRICTED
- Fraud data access is logged for audit trail
- Borrower-facing status uses neutral language ("under review", not "fraud")
- generate_sanitized_report returns correct data per access level
"""

import pytest
from unittest.mock import MagicMock, patch

from services.smart_docs.fraud_access_control import (
    FraudAccessLevel,
    FRAUD_RESTRICTED_FIELDS,
    get_fraud_access_level,
    filter_fraud_response,
    strip_fraud_fields,
    log_fraud_data_access,
)


# =============================================================================
# Mock user factory
# =============================================================================

class _MockUser:
    """Lightweight mock user for testing access level determination."""
    def __init__(self, id=1, organization_id=1, permission_role="sales"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = permission_role


def _portal_user():
    return _MockUser(id=100, organization_id=1, permission_role="sales")


def _regular_user():
    return _MockUser(id=10, organization_id=1, permission_role="sales")


def _manager_user():
    return _MockUser(id=20, organization_id=1, permission_role="management")


def _compliance_user():
    return _MockUser(id=30, organization_id=1, permission_role="compliance")


def _admin_user():
    return _MockUser(id=2, organization_id=1, permission_role="admin")


def _site_admin_user():
    return _MockUser(id=3, organization_id=1, permission_role="site_admin")


# =============================================================================
# Sample fraud response data (simulates raw unfiltered output)
# =============================================================================

def _sample_fraud_response(risk_level="high", risk_score=75):
    """Build a sample fraud analysis response with all fields present."""
    return {
        "loan_id": 42,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "total_documents": 8,
        "indicators": [
            {
                "type": "tamper_detected",
                "severity": "critical",
                "description": "2 document(s) failed integrity check",
                "document_ids": [101, 102],
            },
            {
                "type": "access_denials",
                "severity": "high",
                "description": "12 access denial(s) in the last 7 days",
            },
        ],
        "fraud_indicators": [
            {
                "indicator_type": "ALTERED_TEXT",
                "severity": "CRITICAL",
                "description": "Document created with Photoshop",
                "evidence": "Document 101: creator='Adobe Photoshop'",
            },
        ],
        "sar_status": "pending_review",
        "investigation_notes": "Borrower documents show signs of fabrication",
        "suspicious_patterns": ["round_numbers", "batch_upload"],
        "recommendations": [
            "Escalate to compliance officer for manual review",
            "Re-request affected documents from borrower",
        ],
        "analyzed_at": "2026-03-12T10:00:00+00:00",
    }


# =============================================================================
# Tests: Access Level Determination
# =============================================================================

@pytest.mark.unit
class TestGetFraudAccessLevel:
    """Test access level determination based on user role and request context."""

    def test_portal_request_always_restricted(self):
        """Portal requests must ALWAYS return RESTRICTED, even for admins."""
        # Even an admin on a portal request must be RESTRICTED
        admin = _admin_user()
        level = get_fraud_access_level(admin, is_portal_request=True)
        assert level == FraudAccessLevel.RESTRICTED

    def test_portal_request_regular_user_restricted(self):
        """Portal request from regular user -> RESTRICTED."""
        level = get_fraud_access_level(_regular_user(), is_portal_request=True)
        assert level == FraudAccessLevel.RESTRICTED

    def test_regular_user_gets_summary(self):
        """Internal regular user (sales) -> SUMMARY."""
        level = get_fraud_access_level(_regular_user(), is_portal_request=False)
        assert level == FraudAccessLevel.SUMMARY

    def test_manager_gets_summary(self):
        """Manager -> SUMMARY (can see risk score, not details)."""
        level = get_fraud_access_level(_manager_user(), is_portal_request=False)
        assert level == FraudAccessLevel.SUMMARY

    def test_compliance_officer_gets_full(self):
        """Compliance officer -> FULL access."""
        level = get_fraud_access_level(_compliance_user(), is_portal_request=False)
        assert level == FraudAccessLevel.FULL

    def test_admin_gets_full(self):
        """Platform admin -> FULL access."""
        level = get_fraud_access_level(_admin_user(), is_portal_request=False)
        assert level == FraudAccessLevel.FULL

    def test_site_admin_gets_full(self):
        """Site admin -> FULL access."""
        level = get_fraud_access_level(_site_admin_user(), is_portal_request=False)
        assert level == FraudAccessLevel.FULL

    def test_processing_user_gets_summary(self):
        """Processing staff -> SUMMARY."""
        user = _MockUser(permission_role="processing")
        level = get_fraud_access_level(user, is_portal_request=False)
        assert level == FraudAccessLevel.SUMMARY

    def test_operations_user_gets_summary(self):
        """Operations staff -> SUMMARY."""
        user = _MockUser(permission_role="operations")
        level = get_fraud_access_level(user, is_portal_request=False)
        assert level == FraudAccessLevel.SUMMARY

    def test_no_role_defaults_to_summary(self):
        """User with no permission_role -> SUMMARY (not FULL)."""
        user = _MockUser(permission_role="")
        level = get_fraud_access_level(user, is_portal_request=False)
        assert level == FraudAccessLevel.SUMMARY


# =============================================================================
# Tests: Response Filtering
# =============================================================================

@pytest.mark.unit
class TestFilterFraudResponse:
    """Test that filter_fraud_response correctly strips data by access level."""

    def test_full_access_returns_everything(self):
        """FULL access: all fields returned unchanged."""
        data = _sample_fraud_response()
        result = filter_fraud_response(data, FraudAccessLevel.FULL)
        assert result == data
        assert "indicators" in result
        assert "fraud_indicators" in result
        assert "sar_status" in result
        assert "investigation_notes" in result

    def test_summary_strips_indicators(self):
        """SUMMARY access: risk_score present, indicators removed."""
        data = _sample_fraud_response(risk_score=75, risk_level="high")
        result = filter_fraud_response(data, FraudAccessLevel.SUMMARY)
        assert result["risk_score"] == 75
        assert result["risk_level"] == "high"
        # Must NOT contain indicator details
        assert "indicators" not in result
        assert "fraud_indicators" not in result
        assert "sar_status" not in result
        assert "investigation_notes" not in result
        assert "suspicious_patterns" not in result

    def test_summary_includes_single_recommendation(self):
        """SUMMARY: includes a single recommendation string."""
        data = _sample_fraud_response()
        result = filter_fraud_response(data, FraudAccessLevel.SUMMARY)
        assert "recommendation" in result
        assert isinstance(result["recommendation"], str)

    def test_restricted_returns_neutral_status_only(self):
        """RESTRICTED access: only document_status, no fraud info at all."""
        data = _sample_fraud_response(risk_level="high", risk_score=75)
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        # Must have document_status
        assert "document_status" in result
        # Must NOT have ANY fraud information
        assert "risk_score" not in result
        assert "risk_level" not in result
        assert "indicators" not in result
        assert "fraud_indicators" not in result
        assert "sar_status" not in result
        assert "recommendations" not in result
        assert "investigation_notes" not in result
        assert "suspicious_patterns" not in result

    def test_restricted_high_risk_shows_under_review(self):
        """RESTRICTED: high risk loan shows 'under_review', not 'fraud'."""
        data = _sample_fraud_response(risk_level="high")
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        assert result["document_status"] == "under_review"
        # The word "fraud" must NEVER appear in restricted responses
        response_str = str(result).lower()
        assert "fraud" not in response_str
        assert "sar" not in response_str
        assert "suspicious" not in response_str

    def test_restricted_critical_risk_shows_under_review(self):
        """RESTRICTED: critical risk also shows 'under_review'."""
        data = _sample_fraud_response(risk_level="CRITICAL", risk_score=90)
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        assert result["document_status"] == "under_review"

    def test_restricted_low_risk_shows_approved(self):
        """RESTRICTED: low/no risk shows 'approved'."""
        data = _sample_fraud_response(risk_level="none", risk_score=0)
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        assert result["document_status"] == "approved"

    def test_restricted_medium_risk_shows_under_review(self):
        """RESTRICTED: medium risk shows 'under_review'."""
        data = _sample_fraud_response(risk_level="MEDIUM", risk_score=30)
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        assert result["document_status"] == "under_review"


# =============================================================================
# Tests: strip_fraud_fields utility
# =============================================================================

@pytest.mark.unit
class TestStripFraudFields:
    """Test the strip_fraud_fields utility for deep field removal."""

    def test_removes_all_restricted_fields(self):
        """All fields in FRAUD_RESTRICTED_FIELDS are removed."""
        data = {
            "loan_id": 1,
            "risk_score": 50,
            "fraud_indicators": [{"type": "test"}],
            "sar_status": "filed",
            "investigation_notes": "secret notes",
            "alert_details": {"detail": "x"},
            "suspicious_patterns": ["pattern1"],
        }
        result = strip_fraud_fields(data)
        for field in FRAUD_RESTRICTED_FIELDS:
            assert field not in result, f"Field '{field}' should have been removed"
        # Non-restricted fields preserved
        assert result["loan_id"] == 1
        assert result["risk_score"] == 50

    def test_recursive_stripping(self):
        """Restricted fields in nested dicts are also removed."""
        data = {
            "loan_id": 1,
            "nested": {
                "safe_field": "ok",
                "sar_status": "filed",
                "fraud_indicators": [],
            },
        }
        result = strip_fraud_fields(data)
        assert "sar_status" not in result["nested"]
        assert "fraud_indicators" not in result["nested"]
        assert result["nested"]["safe_field"] == "ok"

    def test_stripping_in_list_items(self):
        """Restricted fields in dicts inside lists are also removed."""
        data = {
            "items": [
                {"id": 1, "investigation_notes": "secret"},
                {"id": 2, "safe": "ok"},
            ],
        }
        result = strip_fraud_fields(data)
        assert "investigation_notes" not in result["items"][0]
        assert result["items"][0]["id"] == 1
        assert result["items"][1]["safe"] == "ok"


# =============================================================================
# Tests: Audit Logging
# =============================================================================

@pytest.mark.unit
class TestFraudDataAccessLogging:
    """Test that fraud data access is properly logged."""

    def test_successful_access_is_logged(self):
        """Fraud data access creates an audit log entry."""
        mock_db = MagicMock()
        log_fraud_data_access(
            db=mock_db,
            user_id=10,
            organization_id=1,
            loan_id=42,
            access_level=FraudAccessLevel.FULL,
            endpoint="/doc-security/fraud-analysis/42",
            granted=True,
        )
        # Verify db.execute was called (INSERT into document_access_logs)
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_denied_access_is_logged(self):
        """Denied fraud data access is also logged with reason."""
        mock_db = MagicMock()
        log_fraud_data_access(
            db=mock_db,
            user_id=100,
            organization_id=1,
            loan_id=42,
            access_level=FraudAccessLevel.RESTRICTED,
            endpoint="/doc-security/fraud-analysis/42",
            granted=False,
            denial_reason="Portal user attempted fraud data access",
        )
        mock_db.execute.assert_called_once()
        # Verify the call includes denial_reason in params
        call_args = mock_db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["granted"] is False
        assert params["denial_reason"] is not None

    def test_logging_failure_does_not_raise(self):
        """If logging fails, it must not crash the request."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB unavailable")
        # Should not raise
        log_fraud_data_access(
            db=mock_db,
            user_id=10,
            organization_id=1,
            loan_id=42,
            access_level=FraudAccessLevel.FULL,
            endpoint="/test",
        )
        # Rollback should have been attempted
        mock_db.rollback.assert_called_once()


# =============================================================================
# Tests: Borrower-Facing Neutral Language
# =============================================================================

@pytest.mark.unit
class TestBorrowerFacingNeutrality:
    """Verify that borrower-visible responses never contain fraud language."""

    def test_no_fraud_language_in_restricted_response(self):
        """The word 'fraud' must never appear in a RESTRICTED response."""
        for risk_level in ("none", "low", "medium", "high", "CRITICAL"):
            data = _sample_fraud_response(risk_level=risk_level, risk_score=90)
            result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
            result_text = str(result).lower()
            forbidden_terms = ["fraud", "sar", "suspicious", "tipping",
                               "investigation", "indicator", "tamper"]
            for term in forbidden_terms:
                assert term not in result_text, (
                    f"Forbidden term '{term}' found in RESTRICTED response "
                    f"for risk_level={risk_level}: {result}"
                )

    def test_restricted_response_has_only_allowed_keys(self):
        """RESTRICTED response must contain only safe keys."""
        allowed_keys = {"loan_id", "document_status", "total_documents"}
        data = _sample_fraud_response()
        result = filter_fraud_response(data, FraudAccessLevel.RESTRICTED)
        for key in result:
            assert key in allowed_keys, (
                f"Unexpected key '{key}' in RESTRICTED response. "
                f"Allowed: {allowed_keys}"
            )


# =============================================================================
# Tests: generate_sanitized_report
# =============================================================================

@pytest.mark.unit
class TestGenerateSanitizedReport:
    """Test the FraudDetectionService.generate_sanitized_report method."""

    def _make_service(self):
        """Create a FraudDetectionService with a mock DB."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService
        mock_db = MagicMock()
        return FraudDetectionService(mock_db)

    @patch("services.smart_docs.fraud_detection_service.FraudDetectionService.analyze_loan_documents")
    def test_restricted_returns_neutral_status(self, mock_analyze):
        """generate_sanitized_report with 'restricted' returns only document_status."""
        from services.smart_docs.fraud_detection_service import CrossValidationResult
        mock_analyze.return_value = CrossValidationResult(
            loan_id=42,
            documents_analyzed=5,
            inconsistencies=[],
            fraud_indicators=[],
            risk_score=80,
            risk_level="CRITICAL",
            summary="High risk detected",
            recommendations=["Escalate immediately"],
        )
        service = self._make_service()
        result = service.generate_sanitized_report(42, organization_id=1, access_level="restricted")
        assert result["document_status"] == "under_review"
        assert "risk_score" not in result
        assert "fraud_indicators" not in result
        assert "recommendations" not in result

    @patch("services.smart_docs.fraud_detection_service.FraudDetectionService.analyze_loan_documents")
    def test_summary_returns_risk_score_only(self, mock_analyze):
        """generate_sanitized_report with 'summary' returns risk score but no indicators."""
        from services.smart_docs.fraud_detection_service import CrossValidationResult, FraudIndicator
        mock_analyze.return_value = CrossValidationResult(
            loan_id=42,
            documents_analyzed=5,
            inconsistencies=[{"check_type": "NAME_MISMATCH"}],
            fraud_indicators=[
                FraudIndicator(
                    indicator_type="ALTERED_TEXT",
                    severity="CRITICAL",
                    description="Photoshop detected",
                    evidence="doc 101",
                    affected_documents=[101],
                    confidence=85,
                    recommendation="Request originals",
                ),
            ],
            risk_score=65,
            risk_level="HIGH",
            summary="Multiple indicators found",
            recommendations=["Escalate to compliance"],
        )
        service = self._make_service()
        result = service.generate_sanitized_report(42, organization_id=1, access_level="summary")
        assert result["risk_score"] == 65
        assert result["risk_level"] == "HIGH"
        assert "fraud_indicators" not in result
        assert "inconsistencies" not in result
        assert result["recommendation"] == "Escalate to compliance"

    @patch("services.smart_docs.fraud_detection_service.FraudDetectionService.analyze_loan_documents")
    def test_full_returns_everything(self, mock_analyze):
        """generate_sanitized_report with 'full' returns all data."""
        from services.smart_docs.fraud_detection_service import CrossValidationResult, FraudIndicator
        mock_analyze.return_value = CrossValidationResult(
            loan_id=42,
            documents_analyzed=5,
            inconsistencies=[{"check_type": "NAME_MISMATCH"}],
            fraud_indicators=[
                FraudIndicator(
                    indicator_type="ALTERED_TEXT",
                    severity="CRITICAL",
                    description="Photoshop detected",
                    evidence="doc 101",
                    affected_documents=[101],
                    confidence=85,
                    recommendation="Request originals",
                ),
            ],
            risk_score=65,
            risk_level="HIGH",
            summary="Multiple indicators found",
            recommendations=["Escalate to compliance"],
        )
        service = self._make_service()
        result = service.generate_sanitized_report(42, organization_id=1, access_level="full")
        assert result["risk_score"] == 65
        assert "fraud_indicators" in result
        assert len(result["fraud_indicators"]) == 1
        assert "inconsistencies" in result
        assert "recommendations" in result

    @patch("services.smart_docs.fraud_detection_service.FraudDetectionService.analyze_loan_documents")
    def test_restricted_low_risk_shows_approved(self, mock_analyze):
        """Restricted access on a clean loan shows 'approved'."""
        from services.smart_docs.fraud_detection_service import CrossValidationResult
        mock_analyze.return_value = CrossValidationResult(
            loan_id=42,
            documents_analyzed=3,
            inconsistencies=[],
            fraud_indicators=[],
            risk_score=0,
            risk_level="LOW",
            summary="No issues",
            recommendations=[],
        )
        service = self._make_service()
        result = service.generate_sanitized_report(42, organization_id=1, access_level="restricted")
        assert result["document_status"] == "approved"
