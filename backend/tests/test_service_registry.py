"""
Tests for SmartDocsServiceRegistry

Verifies:
- Registry creates services with correct org context
- Services are cached (same instance on repeat access)
- Loan access verification enforces tenant isolation
- Document access verification enforces tenant isolation
- Decision logging auto-fills org_id and user_id from context
- get_service_registry dependency injection helper works
- create_registry_for_agent helper works
- Registry rejects missing org_id
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from services.smart_docs.service_registry import (
    SmartDocsServiceRegistry,
    OrgAwareService,
)
from services.smart_docs.service_context import (
    get_service_registry,
    create_registry_for_agent,
    ServiceContext,
)
from exceptions import TenantIsolationError


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockUser:
    """Mock user for testing."""
    id: int = 7
    organization_id: int = 42
    email: str = "lo@example.com"


class MockRow:
    """Mock database row result."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def registry(mock_db):
    """Create a registry with standard test org context."""
    return SmartDocsServiceRegistry(
        db=mock_db,
        org_id=42,
        user_id=7,
        trace_id="test-trace-001",
    )


# =============================================================================
# CONSTRUCTION TESTS
# =============================================================================

class TestRegistryConstruction:
    """Test registry initialization and validation."""

    def test_basic_construction(self, mock_db):
        reg = SmartDocsServiceRegistry(db=mock_db, org_id=42, user_id=7)
        assert reg.org_id == 42
        assert reg.user_id == 7
        assert reg.db is mock_db
        assert reg.trace_id is not None  # auto-generated

    def test_construction_with_trace_id(self, mock_db):
        reg = SmartDocsServiceRegistry(
            db=mock_db, org_id=42, trace_id="custom-trace"
        )
        assert reg.trace_id == "custom-trace"

    def test_construction_without_user_id(self, mock_db):
        reg = SmartDocsServiceRegistry(db=mock_db, org_id=42)
        assert reg.user_id is None

    def test_construction_requires_org_id(self, mock_db):
        with pytest.raises(ValueError, match="org_id is required"):
            SmartDocsServiceRegistry(db=mock_db, org_id=0)

    def test_construction_rejects_none_org_id(self, mock_db):
        with pytest.raises(ValueError, match="org_id is required"):
            SmartDocsServiceRegistry(db=mock_db, org_id=None)

    def test_repr(self, registry):
        r = repr(registry)
        assert "org_id=42" in r
        assert "user_id=7" in r
        assert "test-trace-001" in r

    def test_empty_cache_on_construction(self, registry):
        assert registry.cached_services == []


# =============================================================================
# SERVICE CACHING TESTS
# =============================================================================

class TestServiceCaching:
    """Test that services are lazily initialized and cached."""

    @patch("services.smart_docs.ai_classifier_service.get_ai_classifier_service")
    def test_classifier_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        # First access creates instance
        svc1 = registry.classifier
        assert svc1 is mock_service
        assert mock_factory.call_count == 1

        # Second access returns same instance without calling factory
        svc2 = registry.classifier
        assert svc2 is svc1
        assert mock_factory.call_count == 1

        assert "classifier" in registry.cached_services

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_reviewer_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.reviewer
        svc2 = registry.reviewer
        assert svc1 is svc2
        assert mock_factory.call_count == 1
        # Verify db session was passed
        mock_factory.assert_called_once_with(registry.db)

    @patch("services.smart_docs.income_calculator_service.get_income_calculator_service")
    def test_income_calculator_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.income_calculator
        svc2 = registry.income_calculator
        assert svc1 is svc2
        mock_factory.assert_called_once_with(registry.db)

    @patch("services.smart_docs.bank_statement_analyzer.get_bank_statement_analyzer")
    def test_bank_analyzer_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.bank_analyzer
        svc2 = registry.bank_analyzer
        assert svc1 is svc2
        mock_factory.assert_called_once_with(registry.db)

    @patch("services.smart_docs.fraud_detection_service.get_fraud_detection_service")
    def test_fraud_detector_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.fraud_detector
        svc2 = registry.fraud_detector
        assert svc1 is svc2

    @patch("services.smart_docs.document_ocr_service.get_document_ocr_service")
    def test_ocr_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.ocr
        svc2 = registry.ocr
        assert svc1 is svc2
        mock_factory.assert_called_once()

    @patch("services.smart_docs.pos_analyzer_service.get_pos_analyzer_service")
    def test_pos_analyzer_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.pos_analyzer
        svc2 = registry.pos_analyzer
        assert svc1 is svc2

    @patch("services.smart_docs.followup_automation_service.get_followup_automation_service")
    def test_followup_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.followup
        svc2 = registry.followup
        assert svc1 is svc2

    @patch("services.smart_docs.document_validation_engine.get_document_validation_engine")
    def test_validation_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.validation
        svc2 = registry.validation
        assert svc1 is svc2

    @patch("services.smart_docs.tax_return_analyzer_service.get_tax_return_analyzer")
    def test_tax_analyzer_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.tax_analyzer
        svc2 = registry.tax_analyzer
        assert svc1 is svc2

    @patch("services.smart_docs.w2_paystub_cross_validator.get_w2_paystub_cross_validator")
    def test_w2_validator_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.w2_validator
        svc2 = registry.w2_validator
        assert svc1 is svc2

    @patch("services.smart_docs.call_intel_extractor.get_call_intel_extractor")
    def test_call_intel_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.call_intel
        svc2 = registry.call_intel
        assert svc1 is svc2

    @patch("services.smart_docs.pdf_generation_service.get_pdf_generation_service")
    def test_pdf_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.pdf
        svc2 = registry.pdf
        assert svc1 is svc2

    @patch("services.smart_docs.document_cache_service.get_document_cache_service")
    def test_cache_service_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.cache
        svc2 = registry.cache
        assert svc1 is svc2

    @patch("services.smart_docs.business_rules_service.get_business_rules_service")
    def test_business_rules_cached(self, mock_factory, registry):
        mock_service = MagicMock()
        mock_factory.return_value = mock_service

        svc1 = registry.business_rules
        svc2 = registry.business_rules
        assert svc1 is svc2

    def test_cached_services_tracks_accessed(self, registry):
        """Only accessed services appear in cached_services list."""
        assert registry.cached_services == []

        with patch(
            "services.smart_docs.ai_classifier_service.get_ai_classifier_service",
            return_value=MagicMock(),
        ):
            _ = registry.classifier

        assert "classifier" in registry.cached_services
        assert len(registry.cached_services) == 1


# =============================================================================
# ACCESS VERIFICATION TESTS
# =============================================================================

class TestLoanAccessVerification:
    """Test verify_loan_access tenant isolation."""

    def test_loan_access_allowed(self, registry, mock_db):
        """Loan belonging to same org should pass verification."""
        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=42
        )

        result = registry.verify_loan_access(loan_id=100)
        assert result is True

    def test_loan_not_found_raises_404(self, registry, mock_db):
        """Missing loan should raise HTTPException 404."""
        from fastapi import HTTPException

        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            registry.verify_loan_access(loan_id=999)
        assert exc_info.value.status_code == 404
        assert "999" in str(exc_info.value.detail)

    def test_loan_wrong_org_raises_404(self, registry, mock_db):
        """Loan belonging to different org should raise HTTPException 404
        (not 403, to avoid leaking existence)."""
        from fastapi import HTTPException

        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=99  # different from registry's org_id=42
        )

        with pytest.raises(HTTPException) as exc_info:
            registry.verify_loan_access(loan_id=100)
        assert exc_info.value.status_code == 404

    def test_loan_access_executes_correct_query(self, registry, mock_db):
        """Verify the SQL query checks organization_id."""
        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=42
        )

        registry.verify_loan_access(loan_id=100)

        call_args = mock_db.execute.call_args
        # First positional arg is the SQL text object
        query_text = str(call_args[0][0])
        assert "organization_id" in query_text
        assert "loans" in query_text
        # Second arg is the params dict
        params = call_args[0][1]
        assert params["loan_id"] == 100


class TestDocumentAccessVerification:
    """Test verify_document_access tenant isolation."""

    def test_document_access_allowed(self, registry, mock_db):
        """Document belonging to same org should pass verification."""
        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=42
        )

        result = registry.verify_document_access(document_id=55)
        assert result is True

    def test_document_not_found_raises_404(self, registry, mock_db):
        """Missing document should raise HTTPException 404."""
        from fastapi import HTTPException

        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            registry.verify_document_access(document_id=999)
        assert exc_info.value.status_code == 404

    def test_document_wrong_org_raises_404(self, registry, mock_db):
        """Document belonging to different org should raise 404."""
        from fastapi import HTTPException

        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=99
        )

        with pytest.raises(HTTPException) as exc_info:
            registry.verify_document_access(document_id=55)
        assert exc_info.value.status_code == 404

    def test_document_access_joins_through_loan(self, registry, mock_db):
        """Verify query joins smart_documents -> loans to check org."""
        mock_db.execute.return_value.fetchone.return_value = MockRow(
            organization_id=42
        )

        registry.verify_document_access(document_id=55)

        query_text = str(mock_db.execute.call_args[0][0])
        assert "smart_documents" in query_text
        assert "loans" in query_text
        assert "organization_id" in query_text


# =============================================================================
# DECISION LOGGING TESTS
# =============================================================================

class TestDecisionLogging:
    """Test log_decision auto-fills context from registry."""

    @patch("services.smart_docs.decision_audit_service.log_decision")
    def test_log_decision_auto_fills_context(self, mock_log, registry):
        """log_decision should auto-fill db, org_id, user_id."""
        registry.log_decision(
            loan_id=100,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=55,
            decision="approved",
            reasoning="All checks passed",
            new_state="approved",
        )

        mock_log.assert_called_once()
        kwargs = mock_log.call_args[1]
        assert kwargs["db"] is registry.db
        assert kwargs["organization_id"] == 42
        assert kwargs["maker_id"] == 7
        assert kwargs["loan_id"] == 100
        assert kwargs["decision"] == "approved"

    @patch("services.smart_docs.decision_audit_service.log_decision")
    def test_log_decision_includes_trace_id(self, mock_log, registry):
        """supporting_data should include the registry's trace_id."""
        registry.log_decision(
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=55,
            decision="rejected",
            reasoning="Document expired",
            new_state="rejected",
            supporting_data={"confidence": 95},
        )

        kwargs = mock_log.call_args[1]
        assert kwargs["supporting_data"]["trace_id"] == "test-trace-001"
        # Original data should be preserved
        assert kwargs["supporting_data"]["confidence"] == 95

    @patch("services.smart_docs.decision_audit_service.log_decision")
    def test_log_decision_without_supporting_data(self, mock_log, registry):
        """supporting_data defaults to dict with just trace_id when None."""
        registry.log_decision(
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=55,
            decision="approved",
            reasoning="Clean pass",
            new_state="approved",
        )

        kwargs = mock_log.call_args[1]
        assert kwargs["supporting_data"] == {"trace_id": "test-trace-001"}

    @patch("services.smart_docs.decision_audit_service.log_decision")
    def test_log_decision_passes_all_params(self, mock_log, registry):
        """All optional parameters should be forwarded."""
        registry.log_decision(
            loan_id=100,
            decision_type="fraud_alert",
            entity_type="smart_document",
            entity_id=55,
            decision="escalated",
            reasoning="Suspicious patterns detected",
            new_state="flagged",
            maker_type="ai_agent",
            maker_name="DocumentIntelligenceAgent",
            previous_state="pending_review",
            document_id=55,
            ip_address="10.0.0.1",
            user_agent="test-agent/1.0",
        )

        kwargs = mock_log.call_args[1]
        assert kwargs["maker_type"] == "ai_agent"
        assert kwargs["maker_name"] == "DocumentIntelligenceAgent"
        assert kwargs["previous_state"] == "pending_review"
        assert kwargs["document_id"] == 55
        assert kwargs["ip_address"] == "10.0.0.1"
        assert kwargs["user_agent"] == "test-agent/1.0"


# =============================================================================
# ORG-AWARE SERVICE BASE CLASS TESTS
# =============================================================================

class TestOrgAwareService:
    """Test the OrgAwareService base class."""

    def test_construction(self, mock_db):
        svc = OrgAwareService(db=mock_db, org_id=42, user_id=7)
        assert svc.db is mock_db
        assert svc.org_id == 42
        assert svc.user_id == 7

    def test_construction_without_user_id(self, mock_db):
        svc = OrgAwareService(db=mock_db, org_id=42)
        assert svc.user_id is None

    def test_require_org_match_passes(self, mock_db):
        svc = OrgAwareService(db=mock_db, org_id=42)
        # Should not raise
        svc._require_org_match(42)

    def test_require_org_match_fails(self, mock_db):
        svc = OrgAwareService(db=mock_db, org_id=42)
        with pytest.raises(TenantIsolationError) as exc_info:
            svc._require_org_match(99)
        assert exc_info.value.requesting_org_id == 42
        assert exc_info.value.target_org_id == 99


# =============================================================================
# SERVICE CONTEXT TESTS
# =============================================================================

class TestServiceContext:
    """Test the ServiceContext dataclass."""

    def test_construction(self, mock_db):
        ctx = ServiceContext(
            db=mock_db,
            org_id=42,
            user_id=7,
            trace_id="abc123",
        )
        assert ctx.db is mock_db
        assert ctx.org_id == 42
        assert ctx.user_id == 7
        assert ctx.trace_id == "abc123"

    def test_defaults(self, mock_db):
        ctx = ServiceContext(db=mock_db, org_id=42)
        assert ctx.user_id is None
        assert ctx.trace_id is None


# =============================================================================
# DEPENDENCY INJECTION TESTS
# =============================================================================

class TestGetServiceRegistry:
    """Test the get_service_registry FastAPI dependency helper."""

    def test_from_user_object(self, mock_db):
        user = MockUser(id=7, organization_id=42)
        reg = get_service_registry(mock_db, user)
        assert isinstance(reg, SmartDocsServiceRegistry)
        assert reg.org_id == 42
        assert reg.user_id == 7
        assert reg.db is mock_db

    def test_from_dict_user(self, mock_db):
        user = {"id": 7, "organization_id": 42}
        reg = get_service_registry(mock_db, user)
        assert reg.org_id == 42
        assert reg.user_id == 7

    def test_missing_org_id_raises(self, mock_db):
        user = MockUser(id=7, organization_id=None)
        with pytest.raises(ValueError, match="organization_id"):
            get_service_registry(mock_db, user)

    def test_dict_missing_org_id_raises(self, mock_db):
        user = {"id": 7}
        with pytest.raises(ValueError, match="organization_id"):
            get_service_registry(mock_db, user)


class TestCreateRegistryForAgent:
    """Test the create_registry_for_agent helper."""

    def test_creates_registry(self, mock_db):
        reg = create_registry_for_agent(
            db=mock_db,
            org_id=42,
            user_id=7,
            trace_id="agent-trace",
        )
        assert isinstance(reg, SmartDocsServiceRegistry)
        assert reg.org_id == 42
        assert reg.user_id == 7
        assert reg.trace_id == "agent-trace"

    def test_creates_without_optional_params(self, mock_db):
        reg = create_registry_for_agent(db=mock_db, org_id=42)
        assert reg.org_id == 42
        assert reg.user_id is None
        assert reg.trace_id is not None  # auto-generated


# =============================================================================
# ISOLATION BETWEEN REGISTRIES
# =============================================================================

class TestRegistryIsolation:
    """Test that separate registries are independent."""

    def test_different_registries_have_separate_caches(self, mock_db):
        """Two registries should not share cached service instances."""
        reg1 = SmartDocsServiceRegistry(db=mock_db, org_id=42, user_id=7)
        reg2 = SmartDocsServiceRegistry(db=mock_db, org_id=99, user_id=5)

        with patch(
            "services.smart_docs.ai_classifier_service.get_ai_classifier_service",
            side_effect=[MagicMock(), MagicMock()],
        ):
            svc1 = reg1.classifier
            svc2 = reg2.classifier
            assert svc1 is not svc2

    def test_different_org_ids(self, mock_db):
        """Registries for different orgs should have distinct org_ids."""
        reg1 = SmartDocsServiceRegistry(db=mock_db, org_id=42)
        reg2 = SmartDocsServiceRegistry(db=mock_db, org_id=99)
        assert reg1.org_id != reg2.org_id
