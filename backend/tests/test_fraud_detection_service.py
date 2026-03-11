"""
Test Fraud Detection Service - Comprehensive tests for document fraud detection
and cross-source validation.

Covers:
1. Cross-document name consistency validation
2. Income consistency across paystubs, W2s, and tax returns
3. Employment history verification across documents
4. Address consistency validation
5. Social Security number consistency check (via name/identity cross-check)
6. Fraud score calculation (weighted scoring)
7. Photo/image manipulation detection indicators (PDF metadata)
8. Font inconsistency detection (via suspicious creator tools)
9. Date tampering indicators (temporal anomalies)
10. Employer information cross-validation (name + EIN)
11. Income inflation detection (paystub vs W2 mismatch)
12. Multiple identity detection (different names/SSNs across docs)
13. Synthetic identity indicators (implausible income for job title)
14. Risk level assignment (LOW, MEDIUM, HIGH, CRITICAL)
15. Alert generation for detected fraud (SAR data, recommendations)
"""

import pytest
from datetime import datetime, date, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from collections import namedtuple

from services.smart_docs.fraud_detection_service import (
    FraudDetectionService,
    FraudIndicator,
    CrossValidationResult,
    SEVERITY_WEIGHTS,
    RISK_THRESHOLDS,
    NAME_VARIATIONS,
    SUSPICIOUS_CREATORS,
    INCOME_PLAUSIBILITY,
    get_fraud_detection_service,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create a FraudDetectionService instance with a mock DB session."""
    return FraudDetectionService(mock_db)


def _make_row(**kwargs):
    """Build a mock DB row as a namedtuple-like object with attribute access."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


# =============================================================================
# 1. CROSS-DOCUMENT NAME CONSISTENCY VALIDATION
# =============================================================================

@pytest.mark.unit
class TestCrossValidateNames:
    """Test cross-document name consistency validation."""

    def test_matching_names_no_inconsistencies(self, service, mock_db):
        """Identical names across documents should produce no inconsistencies."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        assert result == []

    def test_name_variation_allowed(self, service, mock_db):
        """Common name variations (e.g., William vs Bill) should not be flagged."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "William Jones"},
                extracted_names=["William Jones"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "Bill Jones"},
                extracted_names=["Bill Jones"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        assert result == [], "Common name variations (William/Bill) should not trigger a mismatch"

    def test_name_mismatch_flagged(self, service, mock_db):
        """Completely different names across documents should be flagged as HIGH severity."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "Jane Doe"},
                extracted_names=["Jane Doe"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        assert len(result) >= 1
        assert result[0]["check_type"] == "NAME_MISMATCH"
        assert result[0]["severity"] == "HIGH"
        assert 1 in result[0]["document_ids"]
        assert 2 in result[0]["document_ids"]

    def test_single_document_returns_empty(self, service, mock_db):
        """A single document cannot be cross-validated and should return empty."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        assert result == []

    def test_name_with_suffix_stripped(self, service, mock_db):
        """Name suffixes (Jr, Sr, III) should be stripped before comparison."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith Jr."},
                extracted_names=["John Smith Jr."],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        assert result == [], "Name with Jr. suffix should match the base name"


# =============================================================================
# 2. INCOME CONSISTENCY ACROSS PAYSTUBS, W2S, AND TAX RETURNS
# =============================================================================

@pytest.mark.unit
class TestCrossValidateIncome:
    """Test income consistency checks across document types."""

    def test_consistent_paystub_w2_no_flag(self, service, mock_db):
        """Paystub annualized income within 15% of W2 should not be flagged."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 5000,
                    "pay_frequency": "monthly",
                },
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 60000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        assert result == [], "Income within 15% tolerance should not generate an inconsistency"

    def test_paystub_w2_mismatch_medium(self, service, mock_db):
        """Paystub annualized > 15% but <= 30% from W2 should be MEDIUM severity."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 7000,
                    "pay_frequency": "monthly",
                },
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 60000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        assert len(result) >= 1
        mismatch = result[0]
        assert mismatch["check_type"] == "INCOME_MISMATCH_PAYSTUB_W2"
        assert mismatch["severity"] == "MEDIUM"

    def test_paystub_w2_mismatch_high(self, service, mock_db):
        """Paystub annualized > 30% from W2 should be HIGH severity."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 10000,
                    "pay_frequency": "monthly",
                },
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 60000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        assert len(result) >= 1
        assert result[0]["severity"] == "HIGH"
        assert result[0]["check_type"] == "INCOME_MISMATCH_PAYSTUB_W2"

    def test_w2_vs_tax_return_high_agi(self, service, mock_db):
        """Tax return AGI significantly higher than W2 wages should be flagged."""
        rows = [
            _make_row(
                document_id=1, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 60000,
                    "tax_year": "2025",
                },
            ),
            _make_row(
                document_id=2, doc_type="TAX_RETURN",
                extracted_fields={
                    "adjusted_gross_income": 120000,
                    "tax_year": "2025",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        assert len(result) >= 1
        assert result[0]["check_type"] == "INCOME_MISMATCH_W2_TAX"

    def test_bank_deposits_much_lower_than_w2(self, service, mock_db):
        """Bank deposits annualized < 50% of W2 income should be flagged."""
        rows = [
            _make_row(
                document_id=1, doc_type="BANK_STATEMENT",
                extracted_fields={
                    "total_deposits": 1500,
                },
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 80000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        assert len(result) >= 1
        assert result[0]["check_type"] == "INCOME_MISMATCH_BANK_W2"


# =============================================================================
# 3. EMPLOYMENT HISTORY VERIFICATION
# =============================================================================

@pytest.mark.unit
class TestCrossValidateEmployment:
    """Test employer information cross-validation."""

    def test_matching_employer_names(self, service, mock_db):
        """Same employer name across documents should produce no inconsistencies."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": None},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": None},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=100)
        assert result == []

    def test_employer_name_mismatch(self, service, mock_db):
        """Different employer names across documents should be flagged as HIGH."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corporation", "employer_ein": None},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Globex Industries", "employer_ein": None},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=100)
        assert len(result) >= 1
        assert result[0]["check_type"] == "EMPLOYER_NAME_MISMATCH"
        assert result[0]["severity"] == "HIGH"

    def test_employer_name_with_suffix_normalization(self, service, mock_db):
        """Employer names differing only by suffix (Inc, LLC) should match."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Inc.", "employer_ein": None},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme", "employer_ein": None},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=100)
        assert result == [], "Employer name with/without Inc. suffix should match"

    def test_employer_ein_mismatch_critical(self, service, mock_db):
        """Different EINs across documents should be flagged as CRITICAL severity."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "12-3456789"},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "98-7654321"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=100)
        ein_mismatches = [r for r in result if r["check_type"] == "EMPLOYER_EIN_MISMATCH"]
        assert len(ein_mismatches) >= 1
        assert ein_mismatches[0]["severity"] == "CRITICAL"
        assert ein_mismatches[0]["confidence"] == 95


# =============================================================================
# 4. ADDRESS CONSISTENCY VALIDATION
# =============================================================================

@pytest.mark.unit
class TestCrossValidateAddresses:
    """Test address consistency validation across documents."""

    def test_matching_addresses(self, service, mock_db):
        """Identical addresses should produce no inconsistencies."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"address": "123 Main Street", "city": "Springfield", "state": "IL"},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"address": "123 Main Street", "city": "Springfield", "state": "IL"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_addresses(loan_id=100)
        assert result == []

    def test_address_abbreviation_normalization(self, service, mock_db):
        """Addresses differing only by abbreviation (Street vs St) should match."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"address": "123 Main Street", "city": "Springfield", "state": "IL"},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"address": "123 Main St", "city": "Springfield", "state": "IL"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_addresses(loan_id=100)
        assert result == [], "Street vs St abbreviation should be normalized and match"

    def test_completely_different_addresses_flagged(self, service, mock_db):
        """Completely different addresses should be flagged as MEDIUM severity."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"address": "123 Main Street", "city": "Springfield", "state": "IL"},
            ),
            _make_row(
                document_id=2, doc_type="BANK_STATEMENT",
                extracted_fields={"address": "999 Oak Avenue", "city": "Chicago", "state": "IL"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_addresses(loan_id=100)
        assert len(result) >= 1
        assert result[0]["check_type"] == "ADDRESS_MISMATCH"
        assert result[0]["severity"] == "MEDIUM"


# =============================================================================
# 5. SSN / IDENTITY CONSISTENCY (via multiple identity detection)
# =============================================================================

@pytest.mark.unit
class TestMultipleIdentityDetection:
    """Test detection of multiple identities (different names/SSNs) across documents."""

    def test_different_names_suggest_multiple_identities(self, service, mock_db):
        """Multiple entirely different names across documents indicates potential identity fraud."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "Alice Johnson"},
                extracted_names=["Alice Johnson"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "Carlos Rivera"},
                extracted_names=["Carlos Rivera"],
            ),
            _make_row(
                document_id=3, doc_type="BANK_STATEMENT",
                extracted_fields={"account_holder_name": "Dmitri Volkov"},
                extracted_names=["Dmitri Volkov"],
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=100)
        # Should flag mismatches between doc 1 vs doc 2 and doc 1 vs doc 3
        assert len(result) >= 2, "Multiple completely different names should generate multiple mismatches"
        for item in result:
            assert item["severity"] == "HIGH"


# =============================================================================
# 6. FRAUD SCORE CALCULATION (WEIGHTED SCORING)
# =============================================================================

@pytest.mark.unit
class TestRiskScoreCalculation:
    """Test weighted fraud score calculation and risk level assignment."""

    def test_no_indicators_zero_score(self, service):
        """No indicators should produce a score of 0 and LOW risk."""
        score, level = service.calculate_risk_score([])
        assert score == 0
        assert level == "LOW"

    def test_single_low_indicator(self, service):
        """A single LOW severity indicator should produce a small score."""
        indicators = [
            FraudIndicator(
                indicator_type="SUSPICIOUS_PATTERN", severity="LOW",
                description="test", evidence="test", affected_documents=[1],
                confidence=100, recommendation="test",
            ),
        ]
        score, level = service.calculate_risk_score(indicators)
        # LOW weight = 3, confidence factor = 1.0 => 3 points
        assert score == 3
        assert level == "LOW"

    def test_single_critical_indicator(self, service):
        """A single CRITICAL severity indicator with full confidence should produce 25 points."""
        indicators = [
            FraudIndicator(
                indicator_type="ALTERED_TEXT", severity="CRITICAL",
                description="test", evidence="test", affected_documents=[1],
                confidence=100, recommendation="test",
            ),
        ]
        score, level = service.calculate_risk_score(indicators)
        assert score == 25
        assert level == "MEDIUM"

    def test_multiple_indicators_accumulate(self, service):
        """Multiple indicators should accumulate scores."""
        indicators = [
            FraudIndicator(
                indicator_type="ALTERED_TEXT", severity="CRITICAL",
                description="test", evidence="test", affected_documents=[1],
                confidence=100, recommendation="test",
            ),
            FraudIndicator(
                indicator_type="INCONSISTENT_DATA", severity="HIGH",
                description="test", evidence="test", affected_documents=[2],
                confidence=100, recommendation="test",
            ),
            FraudIndicator(
                indicator_type="SUSPICIOUS_PATTERN", severity="MEDIUM",
                description="test", evidence="test", affected_documents=[3],
                confidence=100, recommendation="test",
            ),
        ]
        score, level = service.calculate_risk_score(indicators)
        # CRITICAL(25) + HIGH(15) + MEDIUM(8) = 48
        assert score == 48
        assert level == "HIGH"

    def test_confidence_factor_scales_score(self, service):
        """Confidence < 100% should reduce the contribution of an indicator."""
        indicators = [
            FraudIndicator(
                indicator_type="ALTERED_TEXT", severity="CRITICAL",
                description="test", evidence="test", affected_documents=[1],
                confidence=50, recommendation="test",
            ),
        ]
        score, level = service.calculate_risk_score(indicators)
        # CRITICAL weight 25 * 0.5 confidence = 12.5 => 12 rounded
        assert score == 12
        assert level == "LOW"

    def test_score_capped_at_100(self, service):
        """Score should never exceed 100 regardless of indicators."""
        indicators = [
            FraudIndicator(
                indicator_type="ALTERED_TEXT", severity="CRITICAL",
                description="test", evidence="test", affected_documents=[i],
                confidence=100, recommendation="test",
            )
            for i in range(10)
        ]
        score, level = service.calculate_risk_score(indicators)
        assert score == 100
        assert level == "CRITICAL"


# =============================================================================
# 7. PDF METADATA / IMAGE MANIPULATION DETECTION
# =============================================================================

@pytest.mark.unit
class TestDocumentMetadataCheck:
    """Test PDF metadata analysis for manipulation indicators."""

    def test_photoshop_creator_flagged_critical(self, service):
        """PDF created with Photoshop should be flagged as CRITICAL."""
        # Build a fake PDF with Photoshop metadata
        pdf_content = b"%PDF-1.4 /Creator (Adobe Photoshop CC 2025) /Producer (Adobe PDF Library)"
        indicators = service.check_document_metadata(document_id=1, file_content=pdf_content)

        assert len(indicators) >= 1
        photoshop_flags = [i for i in indicators if "photoshop" in i.description.lower()]
        assert len(photoshop_flags) >= 1
        assert photoshop_flags[0].severity == "CRITICAL"
        assert photoshop_flags[0].indicator_type == "ALTERED_TEXT"

    def test_gimp_creator_flagged_critical(self, service):
        """PDF created with GIMP should be flagged as CRITICAL."""
        pdf_content = b"%PDF-1.4 /Creator (GIMP 2.10) /Producer (GIMP PDF)"
        indicators = service.check_document_metadata(document_id=2, file_content=pdf_content)

        assert len(indicators) >= 1
        gimp_flags = [i for i in indicators if "gimp" in i.description.lower()]
        assert len(gimp_flags) >= 1
        assert gimp_flags[0].severity == "CRITICAL"

    def test_legitimate_creator_not_flagged(self, service):
        """PDF from legitimate payroll software should not be flagged for creator."""
        pdf_content = (
            b"%PDF-1.4 /Creator (ADP Workforce Now) "
            b"/Producer (Apache FOP Version 2.3) "
            b"/CreationDate (D:20260201120000+00'00') "
            b"/ModDate (D:20260201120000+00'00')"
        )
        indicators = service.check_document_metadata(document_id=3, file_content=pdf_content)

        creator_flags = [i for i in indicators if i.indicator_type == "ALTERED_TEXT"]
        assert len(creator_flags) == 0, "Legitimate payroll PDF creator should not be flagged"

    def test_modification_long_after_creation_flagged(self, service):
        """PDF modified significantly after creation should be flagged HIGH."""
        pdf_content = (
            b"%PDF-1.4 /Creator (Microsoft Word) "
            b"/Producer (Microsoft PDF) "
            b"/CreationDate (D:20260101120000+00'00') "
            b"/ModDate (D:20260215120000+00'00')"
        )
        indicators = service.check_document_metadata(document_id=4, file_content=pdf_content)

        mod_flags = [i for i in indicators if "modified" in i.description.lower()]
        assert len(mod_flags) >= 1
        assert mod_flags[0].severity == "HIGH"


# =============================================================================
# 8. FONT INCONSISTENCY / SUSPICIOUS CREATOR DETECTION
# =============================================================================

@pytest.mark.unit
class TestSuspiciousCreatorConstants:
    """Verify the suspicious creator tool set is comprehensive."""

    def test_all_image_editors_in_suspicious_set(self):
        """Known image editing tools should be in the SUSPICIOUS_CREATORS set."""
        expected_tools = ["photoshop", "gimp", "illustrator", "inkscape", "canva"]
        for tool in expected_tools:
            assert tool in SUSPICIOUS_CREATORS, f"{tool} should be in SUSPICIOUS_CREATORS"

    def test_suspicious_creators_are_lowercase(self):
        """All suspicious creator entries should be lowercase for matching."""
        for tool in SUSPICIOUS_CREATORS:
            assert tool == tool.lower(), f"SUSPICIOUS_CREATORS entry '{tool}' should be lowercase"


# =============================================================================
# 9. DATE TAMPERING INDICATORS (TEMPORAL ANOMALIES)
# =============================================================================

@pytest.mark.unit
class TestTemporalAnomalies:
    """Test detection of temporal anomalies in documents."""

    def test_future_dated_document_flagged(self, service, mock_db):
        """A document dated in the future should be flagged as HIGH severity."""
        future_date = date.today() + timedelta(days=30)
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                doc_date=future_date, uploaded_at=datetime.now(timezone.utc),
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=100)
        future_flags = [i for i in result if "future" in i.description.lower() and "dated" in i.description.lower()]
        assert len(future_flags) >= 1
        assert future_flags[0].severity == "HIGH"

    def test_pay_period_end_after_pay_date(self, service, mock_db):
        """Pay period end after pay date should be flagged as HIGH (indicates tampering)."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                doc_date=date(2026, 2, 15), uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "pay_date": "2026-02-01",
                    "pay_period_end": "2026-02-15",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=100)
        period_flags = [i for i in result if "period end" in i.description.lower()]
        assert len(period_flags) >= 1
        assert period_flags[0].severity == "HIGH"

    def test_weekend_pay_date_flagged_low(self, service, mock_db):
        """A paystub pay date on a weekend should produce a LOW severity indicator."""
        # 2026-03-07 is a Saturday
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                doc_date=date(2026, 3, 1), uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "pay_date": "2026-03-07",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=100)
        weekend_flags = [i for i in result if "saturday" in i.description.lower() or "sunday" in i.description.lower()]
        assert len(weekend_flags) >= 1
        assert weekend_flags[0].severity == "LOW"

    def test_bank_statement_gap_flagged(self, service, mock_db):
        """A gap > 5 days between bank statement periods should be flagged MEDIUM."""
        rows = [
            _make_row(
                document_id=1, doc_type="BANK_STATEMENT",
                doc_date=date(2026, 1, 31), uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "statement_start_date": "2026-01-01",
                    "statement_end_date": "2026-01-31",
                },
            ),
            _make_row(
                document_id=2, doc_type="BANK_STATEMENT",
                doc_date=date(2026, 3, 31), uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "statement_start_date": "2026-03-01",
                    "statement_end_date": "2026-03-31",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=100)
        gap_flags = [i for i in result if "gap" in i.description.lower()]
        assert len(gap_flags) >= 1
        assert gap_flags[0].severity == "MEDIUM"

    def test_document_uploaded_before_stated_date(self, service, mock_db):
        """Document uploaded before its stated date should be flagged as HIGH."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                doc_date=date(2026, 2, 1),
                uploaded_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
                extracted_fields={
                    "pay_date": "2026-02-15",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=100)
        upload_flags = [i for i in result if "uploaded before" in i.description.lower()]
        assert len(upload_flags) >= 1
        assert upload_flags[0].severity == "HIGH"


# =============================================================================
# 10. EMPLOYER INFORMATION CROSS-VALIDATION (see also class 3)
# =============================================================================

@pytest.mark.unit
class TestEmployerEINCrossValidation:
    """Test EIN normalization and matching."""

    def test_ein_with_different_formatting_matches(self, service, mock_db):
        """EINs differing only in formatting (dash vs no dash) should match."""
        rows = [
            _make_row(
                document_id=1, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "12-3456789"},
            ),
            _make_row(
                document_id=2, doc_type="TAX_RETURN",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "123456789"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=100)
        ein_mismatches = [r for r in result if r["check_type"] == "EMPLOYER_EIN_MISMATCH"]
        assert len(ein_mismatches) == 0, "Same EIN with different formatting should not be flagged"


# =============================================================================
# 11. INCOME INFLATION DETECTION
# =============================================================================

@pytest.mark.unit
class TestIncomeInflationDetection:
    """Test detection of inflated income on paystubs compared to W2."""

    def test_inflated_paystub_vs_w2_detected(self, service, mock_db):
        """Paystub showing 2x the W2 income should be flagged as HIGH."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 10000,
                    "pay_frequency": "biweekly",
                },
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 120000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=100)
        # Biweekly * 26 = 260,000 vs W2 120,000 => > 100% difference
        assert len(result) >= 1
        assert result[0]["severity"] == "HIGH"


# =============================================================================
# 12. (Covered in class 5 - Multiple Identity Detection)
# =============================================================================


# =============================================================================
# 13. SYNTHETIC IDENTITY INDICATORS (Income Plausibility)
# =============================================================================

@pytest.mark.unit
class TestIncomePlausibility:
    """Test income plausibility checks against job title ranges."""

    def test_cashier_with_high_income_flagged(self, service, mock_db):
        """A cashier reporting $200K income should be flagged as implausible."""
        rows = [
            _make_row(
                document_id=1, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 200000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        # Mock the job title lookup to return "cashier"
        with patch.object(service, "_get_job_title_for_loan", return_value="Cashier"):
            result = service.check_income_plausibility(loan_id=100)

        plausibility_flags = [i for i in result if i.indicator_type == "INCOME_PLAUSIBILITY"]
        assert len(plausibility_flags) >= 1
        assert plausibility_flags[0].severity == "HIGH"
        assert "cashier" in plausibility_flags[0].description.lower()

    def test_engineer_with_reasonable_income_not_flagged(self, service, mock_db):
        """An engineer reporting $150K should not be flagged."""
        rows = [
            _make_row(
                document_id=1, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": 150000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        with patch.object(service, "_get_job_title_for_loan", return_value="Software Engineer"):
            result = service.check_income_plausibility(loan_id=100)

        plausibility_flags = [i for i in result if i.indicator_type == "INCOME_PLAUSIBILITY"]
        assert len(plausibility_flags) == 0

    def test_round_paystub_amount_flagged(self, service, mock_db):
        """Perfectly round gross pay on paystub should produce a MEDIUM indicator."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 5000,
                    "regular_earnings": 5000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        with patch.object(service, "_get_job_title_for_loan", return_value=None):
            result = service.check_income_plausibility(loan_id=100)

        round_flags = [i for i in result if "round" in i.description.lower()]
        assert len(round_flags) >= 1
        assert round_flags[0].severity == "MEDIUM"

    def test_excessive_variable_pay_flagged(self, service, mock_db):
        """Variable pay > 80% of regular earnings should be flagged MEDIUM."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": 15000,
                    "regular_earnings": 3000,
                    "overtime_earnings": 5000,
                    "bonus": 4000,
                    "commission": 3000,
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        with patch.object(service, "_get_job_title_for_loan", return_value=None):
            result = service.check_income_plausibility(loan_id=100)

        variable_flags = [i for i in result if "variable pay" in i.description.lower()]
        assert len(variable_flags) >= 1
        assert variable_flags[0].severity == "MEDIUM"


# =============================================================================
# 14. RISK LEVEL ASSIGNMENT
# =============================================================================

@pytest.mark.unit
class TestRiskLevelAssignment:
    """Test correct assignment of risk levels at threshold boundaries."""

    def test_score_0_is_low(self, service):
        score, level = service.calculate_risk_score([])
        assert level == "LOW"

    def test_score_20_is_low(self, service):
        """Score of exactly 20 should be LOW (boundary: 0-20)."""
        indicators = self._make_indicators_for_score(service, target=20)
        score, level = service.calculate_risk_score(indicators)
        assert score == 20
        assert level == "LOW"

    def test_score_21_is_medium(self, service):
        """Score of 21 should be MEDIUM (boundary: 21-45)."""
        indicators = self._make_indicators_for_score(service, target=21)
        score, level = service.calculate_risk_score(indicators)
        assert score == 21
        assert level == "MEDIUM"

    def test_score_46_is_high(self, service):
        """Score of 46 should be HIGH (boundary: 46-70)."""
        indicators = self._make_indicators_for_score(service, target=46)
        score, level = service.calculate_risk_score(indicators)
        assert score == 46
        assert level == "HIGH"

    def test_score_71_is_critical(self, service):
        """Score of 71 should be CRITICAL (boundary: 71-100)."""
        indicators = self._make_indicators_for_score(service, target=71)
        score, level = service.calculate_risk_score(indicators)
        assert score == 71
        assert level == "CRITICAL"

    @staticmethod
    def _make_indicators_for_score(service, target: int):
        """Build a list of LOW indicators that sum to approximately the target score."""
        # LOW weight = 3 at confidence=100 => 3 points each
        # Use fractional confidence to hit exact targets
        # One indicator with exact contribution
        indicators = []
        remaining = target
        while remaining > 0:
            # Each LOW indicator at confidence=100 gives 3 points
            if remaining >= 3:
                indicators.append(FraudIndicator(
                    indicator_type="TEST", severity="LOW",
                    description="test", evidence="test", affected_documents=[1],
                    confidence=100, recommendation="test",
                ))
                remaining -= 3
            else:
                # Use fractional confidence to hit exact target
                # weight=3, need remaining points, so confidence = remaining/3 * 100
                conf = int(round(remaining / 3.0 * 100))
                if conf > 0:
                    indicators.append(FraudIndicator(
                        indicator_type="TEST", severity="LOW",
                        description="test", evidence="test", affected_documents=[1],
                        confidence=conf, recommendation="test",
                    ))
                remaining = 0
        return indicators


# =============================================================================
# 15. ALERT GENERATION / SAR DATA / RECOMMENDATIONS
# =============================================================================

@pytest.mark.unit
class TestAlertGeneration:
    """Test SAR data generation and recommendation building."""

    def test_critical_risk_generates_sar_escalation(self, service, mock_db):
        """CRITICAL risk level should produce SAR escalation recommendation."""
        indicators = [
            FraudIndicator(
                indicator_type="ALTERED_TEXT", severity="CRITICAL",
                description="Photoshop-created document", evidence="test",
                affected_documents=[1], confidence=100, recommendation="Request originals",
            ),
        ]
        inconsistencies = []
        recommendations = service._build_recommendations(indicators, inconsistencies, "CRITICAL")

        assert any("escalate" in r.lower() for r in recommendations), \
            "CRITICAL risk should include escalation recommendation"
        assert any("sar" in r.lower() for r in recommendations), \
            "CRITICAL risk should mention SAR"

    def test_high_risk_recommends_hold(self, service, mock_db):
        """HIGH risk should recommend placing the loan on hold."""
        indicators = [
            FraudIndicator(
                indicator_type="INCONSISTENT_DATA", severity="HIGH",
                description="Name mismatch", evidence="test",
                affected_documents=[1, 2], confidence=80, recommendation="Verify identity",
            ),
        ]
        recommendations = service._build_recommendations(indicators, [], "HIGH")

        assert any("hold" in r.lower() for r in recommendations), \
            "HIGH risk should recommend placing loan on hold"

    def test_low_risk_recommends_proceed(self, service, mock_db):
        """LOW risk with no indicators should recommend proceeding normally."""
        recommendations = service._build_recommendations([], [], "LOW")
        assert any("proceed normally" in r.lower() for r in recommendations)

    def test_generate_sar_data_structure(self, service, mock_db):
        """SAR data should contain all required fields."""
        # Mock the document count query
        doc_count_result = MagicMock()
        doc_count_result.cnt = 3

        # Mock the document rows for analysis
        doc_rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith"},
                extracted_names=["John Smith"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "Jane Doe"},
                extracted_names=["Jane Doe"],
            ),
        ]

        # Mock loan info for SAR data
        loan_info = _make_row(
            id=100, loan_number="LN-001", amount=350000, loan_type="conventional",
            stage="PROCESSING", borrower_name="John Smith", borrower_email="john@test.com",
            property_address="123 Main St", application_date=date(2026, 1, 15),
            loan_officer_id=1, organization_id=1, lo_name="Agent Smith",
        )

        # Set up mock to return different results for different queries
        call_count = {"n": 0}
        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                # First call: document count
                mock_result.fetchone.return_value = doc_count_result
            elif call_count["n"] <= 6:
                # Subsequent calls: cross-validation queries
                mock_result.fetchall.return_value = doc_rows
            elif call_count["n"] == 7:
                # document count for SAR
                mock_result.fetchone.return_value = doc_count_result
            elif call_count["n"] <= 12:
                # More cross-validation for SAR's analyze_loan_documents
                mock_result.fetchall.return_value = doc_rows
            else:
                # Loan info query
                mock_result.fetchone.return_value = loan_info
                mock_result.fetchall.return_value = []
            return mock_result

        mock_db.execute.side_effect = side_effect

        sar = service.generate_sar_data(loan_id=100)

        assert sar["report_type"] == "SUSPICIOUS_ACTIVITY_REPORT"
        assert "generated_at" in sar
        assert "risk_score" in sar
        assert "risk_level" in sar
        assert "loan_information" in sar
        assert "subject_information" in sar
        assert "suspicious_activities" in sar
        assert "compliance_notes" in sar


# =============================================================================
# MAIN ENTRY POINT / INTEGRATION-STYLE TEST
# =============================================================================

@pytest.mark.unit
class TestAnalyzeLoanDocuments:
    """Test the main analyze_loan_documents entry point."""

    def test_no_documents_returns_low_risk(self, service, mock_db):
        """Loan with no documents should return LOW risk and zero score."""
        doc_count_result = MagicMock()
        doc_count_result.cnt = 0
        mock_db.execute.return_value.fetchone.return_value = doc_count_result

        result = service.analyze_loan_documents(loan_id=100)

        assert isinstance(result, CrossValidationResult)
        assert result.risk_score == 0
        assert result.risk_level == "LOW"
        assert result.documents_analyzed == 0
        assert result.inconsistencies == []
        assert result.fraud_indicators == []

    def test_clean_documents_low_risk(self, service, mock_db):
        """Documents with consistent data should produce LOW risk."""
        doc_count_result = MagicMock()
        doc_count_result.cnt = 2

        consistent_rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employee_name": "John Smith", "gross_pay": 5000, "pay_frequency": "monthly"},
                extracted_names=["John Smith"],
            ),
            _make_row(
                document_id=2, doc_type="W2",
                extracted_fields={"employee_name": "John Smith", "wages_tips_compensation": 60000},
                extracted_names=["John Smith"],
            ),
        ]

        # The main entry point calls doc count, then 4 cross-validate + 4 check methods
        # Each calls db.execute. We simplify by making all return the same consistent data.
        call_count = {"n": 0}
        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                mock_result.fetchone.return_value = doc_count_result
            else:
                mock_result.fetchall.return_value = consistent_rows
                mock_result.fetchone.return_value = None
            return mock_result

        mock_db.execute.side_effect = side_effect

        with patch.object(service, "_get_job_title_for_loan", return_value=None):
            result = service.analyze_loan_documents(loan_id=100)

        assert isinstance(result, CrossValidationResult)
        assert result.risk_level == "LOW"
        assert result.documents_analyzed == 2


# =============================================================================
# SUSPICIOUS PATTERNS
# =============================================================================

@pytest.mark.unit
class TestSuspiciousPatterns:
    """Test detection of suspicious document patterns."""

    def test_rapid_batch_upload_flagged(self, service, mock_db):
        """5+ documents uploaded within 2 minutes should be flagged."""
        base_time = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        rows = [
            _make_row(
                document_id=i, doc_type="PAYSTUB",
                uploaded_at=base_time + timedelta(seconds=i * 10),
                file_name=f"doc_{i}.pdf", file_size=1000 + i,
                extracted_fields={},
            )
            for i in range(6)
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=100)
        batch_flags = [i for i in result if "batch" in i.description.lower() or "quickly" in i.description.lower()]
        assert len(batch_flags) >= 1
        assert batch_flags[0].severity == "MEDIUM"

    def test_deposits_near_ctr_threshold_flagged(self, service, mock_db):
        """Total deposits just below $10K CTR threshold should be flagged HIGH."""
        rows = [
            _make_row(
                document_id=1, doc_type="BANK_STATEMENT",
                uploaded_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                file_name="bank.pdf", file_size=5000,
                extracted_fields={"total_deposits": 9950},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=100)
        ctr_flags = [i for i in result if "threshold" in i.description.lower() or "10,000" in i.description]
        assert len(ctr_flags) >= 1
        assert ctr_flags[0].severity == "HIGH"

    def test_identical_file_sizes_flagged(self, service, mock_db):
        """Documents with identical file sizes should be flagged as potential duplicates."""
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                uploaded_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                file_name="paystub1.pdf", file_size=12345,
                extracted_fields={},
            ),
            _make_row(
                document_id=2, doc_type="PAYSTUB",
                uploaded_at=datetime(2026, 3, 2, tzinfo=timezone.utc),
                file_name="paystub2.pdf", file_size=12345,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=100)
        size_flags = [i for i in result if "identical file size" in i.description.lower()]
        assert len(size_flags) >= 1
        assert size_flags[0].severity == "MEDIUM"


# =============================================================================
# DUPLICATE SUBMISSION DETECTION
# =============================================================================

@pytest.mark.unit
class TestDuplicateSubmissions:
    """Test detection of duplicate document submissions."""

    def test_identical_ocr_text_different_types_flagged_high(self, service, mock_db):
        """Same OCR text submitted under different doc types should be HIGH."""
        long_text = "This is a sufficiently long OCR text content " * 5
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                file_size=5000, ocr_text=long_text,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
            _make_row(
                document_id=2, doc_type="W2",
                file_size=5000, ocr_text=long_text,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_duplicate_submissions(loan_id=100)
        dup_flags = [i for i in result if i.indicator_type == "DUPLICATE_SUBMISSION"]
        assert len(dup_flags) >= 1
        assert dup_flags[0].severity == "HIGH"

    def test_identical_ocr_text_same_type_flagged_medium(self, service, mock_db):
        """Same OCR text submitted under the same doc type should be MEDIUM."""
        long_text = "This is a sufficiently long OCR text content " * 5
        rows = [
            _make_row(
                document_id=1, doc_type="PAYSTUB",
                file_size=5000, ocr_text=long_text,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
            _make_row(
                document_id=2, doc_type="PAYSTUB",
                file_size=5001, ocr_text=long_text,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_duplicate_submissions(loan_id=100)
        dup_flags = [i for i in result if i.indicator_type == "DUPLICATE_SUBMISSION"]
        assert len(dup_flags) >= 1
        assert dup_flags[0].severity == "MEDIUM"


# =============================================================================
# HELPER METHOD UNIT TESTS
# =============================================================================

@pytest.mark.unit
class TestHelperMethods:
    """Test private helper methods for correctness."""

    def test_safe_float_with_currency_string(self, service):
        assert service._safe_float("$1,234.56") == 1234.56

    def test_safe_float_with_none(self, service):
        assert service._safe_float(None) is None

    def test_safe_float_with_empty_string(self, service):
        assert service._safe_float("") is None

    def test_safe_float_with_number(self, service):
        assert service._safe_float(42.5) == 42.5

    def test_parse_date_iso_format(self, service):
        result = service._parse_date("2026-03-10")
        assert result == date(2026, 3, 10)

    def test_parse_date_us_format(self, service):
        result = service._parse_date("03/10/2026")
        assert result == date(2026, 3, 10)

    def test_parse_date_invalid_returns_none(self, service):
        assert service._parse_date("not-a-date") is None
        assert service._parse_date(None) is None
        assert service._parse_date("") is None

    def test_parse_pdf_date(self, service):
        result = service._parse_pdf_date("D:20260310120000")
        assert result == datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_parse_pdf_date_invalid(self, service):
        assert service._parse_pdf_date("") is None
        assert service._parse_pdf_date(None) is None
        assert service._parse_pdf_date("not-a-date") is None

    def test_canonicalize_name(self, service):
        assert service._canonicalize_name("John Smith Jr.") == "john smith"
        assert service._canonicalize_name("  JANE   DOE  III ") == "jane doe"
        assert service._canonicalize_name("") == ""

    def test_normalize_company_name(self, service):
        assert service._normalize_company_name("Acme Inc.") == "acme"
        assert service._normalize_company_name("Global Corp.") == "global"
        assert service._normalize_company_name("TechCo LLC") == "techco"

    def test_normalize_ein(self, service):
        assert service._normalize_ein("12-3456789") == "123456789"
        assert service._normalize_ein("123456789") == "123456789"
        assert service._normalize_ein("") == ""

    def test_normalize_address(self, service):
        result = service._normalize_address("123 Main Street, Apt 4")
        assert "123 main st" in result
        assert "apt 4" in result

    def test_string_similarity_identical(self, service):
        assert service._string_similarity("hello", "hello") == 1.0

    def test_string_similarity_different(self, service):
        sim = service._string_similarity("hello", "world")
        assert sim < 0.5

    def test_string_similarity_empty(self, service):
        assert service._string_similarity("", "hello") == 0.0
        assert service._string_similarity("hello", "") == 0.0

    def test_names_match_exact(self, service):
        assert service._names_match("john smith", "john smith") is True

    def test_names_match_variation(self, service):
        assert service._names_match("robert smith", "bob smith") is True
        assert service._names_match("elizabeth jones", "liz jones") is True

    def test_names_match_different_last(self, service):
        assert service._names_match("john smith", "john doe") is False

    def test_names_match_empty(self, service):
        assert service._names_match("", "john") is False
        assert service._names_match("john", "") is False

    def test_annualize_ytd_midyear(self, service):
        """YTD of $30K through June 30 should annualize to ~$60K."""
        result = service._annualize_ytd(30000, "2026-06-30")
        # 181 days elapsed, annualized = 30000 / 181 * 365 ~ 60497
        assert result is not None
        assert 59000 < result < 62000

    def test_get_fraud_detection_service_factory(self, mock_db):
        """get_fraud_detection_service should return a FraudDetectionService."""
        svc = get_fraud_detection_service(mock_db)
        assert isinstance(svc, FraudDetectionService)
        assert svc.db is mock_db


# =============================================================================
# SEVERITY WEIGHT CONSTANTS VALIDATION
# =============================================================================

@pytest.mark.unit
class TestConstants:
    """Validate that constants are correctly defined."""

    def test_severity_weights_all_present(self):
        assert "CRITICAL" in SEVERITY_WEIGHTS
        assert "HIGH" in SEVERITY_WEIGHTS
        assert "MEDIUM" in SEVERITY_WEIGHTS
        assert "LOW" in SEVERITY_WEIGHTS

    def test_severity_weights_ordering(self):
        assert SEVERITY_WEIGHTS["CRITICAL"] > SEVERITY_WEIGHTS["HIGH"]
        assert SEVERITY_WEIGHTS["HIGH"] > SEVERITY_WEIGHTS["MEDIUM"]
        assert SEVERITY_WEIGHTS["MEDIUM"] > SEVERITY_WEIGHTS["LOW"]

    def test_risk_thresholds_descending(self):
        thresholds = [t[0] for t in RISK_THRESHOLDS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_income_plausibility_ranges_valid(self):
        for job, (low, high) in INCOME_PLAUSIBILITY.items():
            assert low < high, f"Income range for {job} is invalid: {low} >= {high}"
            assert low > 0, f"Income minimum for {job} must be positive"

    def test_name_variations_all_lowercase(self):
        for formal, variants in NAME_VARIATIONS.items():
            assert formal == formal.lower()
            for v in variants:
                assert v == v.lower(), f"Variant '{v}' for '{formal}' should be lowercase"
