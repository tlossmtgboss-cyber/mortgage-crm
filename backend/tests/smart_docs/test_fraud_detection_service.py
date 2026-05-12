"""
Tests for FraudDetectionService

Covers:
- Cross-document name validation (with name variations)
- Cross-document income validation
- Cross-document employment validation
- Cross-document address validation
- Income plausibility checks
- Temporal anomaly detection
- Suspicious pattern detection
- Duplicate submission detection
- PDF metadata analysis
- Risk score calculation
- Sanitized report access levels
- SAR data generation
- Helper methods (name canonicalization, company normalization, etc.)
- Edge cases: clean documents, empty data, false positive avoidance

All tests mock the database layer -- no real DB or AI calls.

Run:
    pytest backend/tests/smart_docs/test_fraud_detection_service.py -v
"""

import pytest
import hashlib
from decimal import Decimal
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.smart_docs.fraud_detection_service import (
    FraudDetectionService,
    FraudIndicator,
    CrossValidationResult,
    get_fraud_detection_service,
    SEVERITY_WEIGHTS,
    RISK_THRESHOLDS,
    NAME_VARIATIONS,
    SUSPICIOUS_CREATORS,
    INCOME_PLAUSIBILITY,
    _NAME_REVERSE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchall.return_value = []
    execute_result.fetchone.return_value = None
    db.execute.return_value = execute_result
    return db


@pytest.fixture
def service(mock_db):
    return FraudDetectionService(mock_db, org_id=1)


@pytest.fixture
def service_no_org(mock_db):
    return FraudDetectionService(mock_db, org_id=None)


def _make_indicator(
    severity="MEDIUM",
    confidence=70,
    indicator_type="SUSPICIOUS_PATTERN",
    description="Test indicator",
):
    return FraudIndicator(
        indicator_type=indicator_type,
        severity=severity,
        description=description,
        evidence="Test evidence",
        affected_documents=[1],
        confidence=confidence,
        recommendation="Review manually",
    )


# ===========================================================================
# 1. HELPER METHODS
# ===========================================================================

class TestCanonicalizeName:
    def test_lowercases(self, service):
        assert service._canonicalize_name("JOHN DOE") == "john doe"

    def test_strips_jr_suffix(self, service):
        assert service._canonicalize_name("John Smith Jr.") == "john smith"

    def test_strips_sr_suffix(self, service):
        assert service._canonicalize_name("John Smith Sr") == "john smith"

    def test_strips_ii_suffix(self, service):
        assert service._canonicalize_name("John Smith II") == "john smith"

    def test_strips_iii_suffix(self, service):
        assert service._canonicalize_name("John Smith III") == "john smith"

    def test_removes_punctuation(self, service):
        result = service._canonicalize_name("O'Brien, Mary")
        assert "'" not in result
        assert "," not in result

    def test_normalizes_whitespace(self, service):
        result = service._canonicalize_name("  John   Doe  ")
        assert result == "john doe"

    def test_empty_string(self, service):
        assert service._canonicalize_name("") == ""

    def test_none_returns_empty(self, service):
        assert service._canonicalize_name(None) == ""


class TestNamesMatch:
    def test_exact_match(self, service):
        assert service._names_match("john doe", "john doe") is True

    def test_name_variation_william_bill(self, service):
        assert service._names_match("william doe", "bill doe") is True

    def test_name_variation_robert_bob(self, service):
        assert service._names_match("robert smith", "bob smith") is True

    def test_name_variation_elizabeth_liz(self, service):
        assert service._names_match("elizabeth jones", "liz jones") is True

    def test_different_last_name_no_match(self, service):
        assert service._names_match("john doe", "john smith") is False

    def test_prefix_match(self, service):
        """Jon vs Jonathan should match (prefix)."""
        assert service._names_match("jon doe", "jonathan doe") is True

    def test_completely_different_names(self, service):
        assert service._names_match("john doe", "maria gonzalez") is False

    def test_empty_strings(self, service):
        assert service._names_match("", "") is False
        assert service._names_match("john doe", "") is False


class TestNormalizeCompanyName:
    def test_strips_inc(self, service):
        assert service._normalize_company_name("Acme Inc.") == "acme"

    def test_strips_llc(self, service):
        assert service._normalize_company_name("My Business LLC") == "my business"

    def test_strips_corporation(self, service):
        assert service._normalize_company_name("Big Corp Corporation") == "big corp"

    def test_strips_punctuation(self, service):
        result = service._normalize_company_name("Smith & Associates, P.A.")
        assert "&" not in result
        assert "." not in result

    def test_empty_string(self, service):
        assert service._normalize_company_name("") == ""

    def test_none(self, service):
        assert service._normalize_company_name(None) == ""


class TestNormalizeEIN:
    def test_strips_dashes(self, service):
        assert service._normalize_ein("12-3456789") == "123456789"

    def test_already_clean(self, service):
        assert service._normalize_ein("123456789") == "123456789"

    def test_empty(self, service):
        assert service._normalize_ein("") == ""

    def test_none(self, service):
        assert service._normalize_ein(None) == ""


class TestNormalizeAddress:
    def test_abbreviates_street(self, service):
        result = service._normalize_address("123 Main Street")
        assert "st" in result
        assert "street" not in result

    def test_abbreviates_avenue(self, service):
        result = service._normalize_address("456 Oak Avenue")
        assert "ave" in result

    def test_abbreviates_directions(self, service):
        result = service._normalize_address("789 North Elm Drive")
        assert "n" in result and "dr" in result

    def test_empty(self, service):
        assert service._normalize_address("") == ""

    def test_none(self, service):
        assert service._normalize_address(None) == ""


class TestStringSimilarity:
    def test_identical_strings(self, service):
        assert service._string_similarity("acme corp", "acme corp") == 1.0

    def test_completely_different(self, service):
        result = service._string_similarity("abc", "xyz")
        assert result < 0.5

    def test_empty_strings(self, service):
        assert service._string_similarity("", "") == 0.0
        assert service._string_similarity("abc", "") == 0.0

    def test_similar_strings(self, service):
        result = service._string_similarity("acme corp", "acme corporation")
        assert result > 0.5


class TestSafeFloat:
    def test_none(self, service):
        assert service._safe_float(None) is None

    def test_dollar_string(self, service):
        assert service._safe_float("$1,234.56") == 1234.56

    def test_plain_number(self, service):
        assert service._safe_float("5000") == 5000.0

    def test_empty_string(self, service):
        assert service._safe_float("") is None

    def test_garbage(self, service):
        assert service._safe_float("abc") is None


class TestParseDate:
    def test_yyyy_mm_dd(self, service):
        assert service._parse_date("2026-01-15") == date(2026, 1, 15)

    def test_mm_dd_yyyy(self, service):
        assert service._parse_date("01/15/2026") == date(2026, 1, 15)

    def test_mm_dd_yy(self, service):
        result = service._parse_date("01/15/26")
        assert result is not None
        assert result.month == 1 and result.day == 15

    def test_invalid(self, service):
        assert service._parse_date("not-a-date") is None

    def test_none(self, service):
        assert service._parse_date(None) is None

    def test_non_string(self, service):
        assert service._parse_date(12345) is None


class TestParsePdfDate:
    def test_standard_format(self, service):
        result = service._parse_pdf_date("D:20260115120000")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_date_only(self, service):
        result = service._parse_pdf_date("D:20260115")
        assert result is not None
        assert result.year == 2026

    def test_invalid(self, service):
        assert service._parse_pdf_date("invalid") is None

    def test_none(self, service):
        assert service._parse_pdf_date(None) is None


class TestAnnualizeYTD:
    def test_mid_year(self, service):
        # YTD = 50000 through 06/30 -> 181 days -> 50000/181*365 = ~100828
        result = service._annualize_ytd(50000, "2026-06-30")
        assert result is not None
        assert 95000 < result < 110000

    def test_invalid_date(self, service):
        assert service._annualize_ytd(50000, "bad-date") is None

    def test_jan_1(self, service):
        # Day 1 -> 50000/1*365 = very large
        result = service._annualize_ytd(50000, "2026-01-01")
        assert result is not None
        assert result > 1000000  # wildly high because only 1 day


# ===========================================================================
# 2. RISK SCORE CALCULATION
# ===========================================================================

class TestCalculateRiskScore:
    def test_no_indicators(self, service):
        score, level = service.calculate_risk_score([])
        assert score == 0
        assert level == "LOW"

    def test_single_low_indicator(self, service):
        indicators = [_make_indicator(severity="LOW", confidence=100)]
        score, level = service.calculate_risk_score(indicators)
        assert score == 3  # LOW weight=3, confidence=1.0
        assert level == "LOW"

    def test_single_critical_indicator(self, service):
        indicators = [_make_indicator(severity="CRITICAL", confidence=100)]
        score, level = service.calculate_risk_score(indicators)
        assert score == 25
        assert level == "MEDIUM"

    def test_multiple_indicators(self, service):
        indicators = [
            _make_indicator(severity="CRITICAL", confidence=100),
            _make_indicator(severity="HIGH", confidence=100),
            _make_indicator(severity="MEDIUM", confidence=100),
        ]
        score, level = service.calculate_risk_score(indicators)
        # 25 + 15 + 8 = 48
        assert score == 48
        assert level == "HIGH"

    def test_confidence_factor(self, service):
        """50% confidence halves the contribution."""
        indicators = [_make_indicator(severity="HIGH", confidence=50)]
        score, level = service.calculate_risk_score(indicators)
        # HIGH=15 * 0.5 = 7.5 -> rounded to 8
        assert score == 8

    def test_capped_at_100(self, service):
        indicators = [_make_indicator(severity="CRITICAL", confidence=100)] * 10
        score, level = service.calculate_risk_score(indicators)
        assert score == 100
        assert level == "CRITICAL"

    def test_risk_level_boundaries(self, service):
        """Verify the exact boundary values for risk levels."""
        # LOW: 0-20
        ind_low = [_make_indicator(severity="MEDIUM", confidence=100)] * 2  # 16
        _, level = service.calculate_risk_score(ind_low)
        assert level == "LOW"

        # MEDIUM: 21-45
        ind_med = [_make_indicator(severity="CRITICAL", confidence=100)]  # 25
        _, level = service.calculate_risk_score(ind_med)
        assert level == "MEDIUM"

        # HIGH: 46-70
        ind_high = [
            _make_indicator(severity="CRITICAL", confidence=100),
            _make_indicator(severity="CRITICAL", confidence=100),
        ]  # 50
        _, level = service.calculate_risk_score(ind_high)
        assert level == "HIGH"


# ===========================================================================
# 3. CROSS-VALIDATE NAMES
# ===========================================================================

class TestCrossValidateNames:
    def test_no_documents_returns_empty(self, service, mock_db):
        mock_db.execute.return_value.fetchall.return_value = []
        result = service.cross_validate_names(loan_id=1)
        assert result == []

    def test_single_document_returns_empty(self, service, mock_db):
        """Need at least 2 documents to cross-validate."""
        row = MagicMock()
        row.document_id = 1
        row.doc_type = "PAYSTUB"
        row.extracted_names = ["John Doe"]
        row.extracted_fields = {}
        mock_db.execute.return_value.fetchall.return_value = [row]

        result = service.cross_validate_names(loan_id=1)
        assert result == []

    def test_matching_names_no_inconsistency(self, service, mock_db):
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_names=["John Doe"],
                extracted_fields={"employee_name": "John Doe"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_names=["John Doe"],
                extracted_fields={"employee_name": "John Doe"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=1)
        assert len(result) == 0

    def test_name_variation_not_flagged(self, service, mock_db):
        """William vs Bill should NOT be flagged."""
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_names=["William Smith"],
                extracted_fields={},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_names=["Bill Smith"],
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=1)
        assert len(result) == 0

    def test_different_names_flagged(self, service, mock_db):
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_names=["John Doe"],
                extracted_fields={},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_names=["Maria Gonzalez"],
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_names(loan_id=1)
        assert len(result) >= 1
        assert result[0]["check_type"] == "NAME_MISMATCH"
        assert result[0]["severity"] == "HIGH"


# ===========================================================================
# 4. CROSS-VALIDATE INCOME
# ===========================================================================

class TestCrossValidateIncome:
    def test_paystub_w2_consistent(self, service, mock_db):
        """Consistent income: annualized paystub ~= W2 wages."""
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": "4000",
                    "pay_frequency": "biweekly",
                    "ytd_gross": "48000",
                    "pay_period_end": "2026-06-15",
                },
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": "104000",
                    "tax_year": "2025",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=1)
        # Annualized from period: 4000 * 26 = 104000
        # W2 = 104000. Difference = 0% -> no inconsistency
        income_mismatches = [r for r in result if "INCOME_MISMATCH" in r.get("check_type", "")]
        assert len(income_mismatches) == 0

    def test_paystub_w2_inconsistent(self, service, mock_db):
        """Paystub annualized far from W2 wages flags inconsistency."""
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={
                    "gross_pay": "6000",
                    "pay_frequency": "biweekly",
                },
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": "100000",
                    "tax_year": "2025",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=1)
        # Annualized: 6000 * 26 = 156000 vs W2 = 100000 -> 56% diff
        income_mismatches = [r for r in result if "INCOME_MISMATCH_PAYSTUB_W2" in r.get("check_type", "")]
        assert len(income_mismatches) >= 1
        assert income_mismatches[0]["severity"] == "HIGH"  # >30% diff

    def test_bank_deposits_below_income(self, service, mock_db):
        """Bank deposits < 50% of stated income flags mismatch."""
        rows = [
            MagicMock(
                document_id=1, doc_type="BANK_STATEMENT",
                extracted_fields={"total_deposits": "3000"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={
                    "wages_tips_compensation": "100000",
                    "tax_year": "2025",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_income(loan_id=1)
        # 3000 * 12 = 36000 < 100000 * 0.5 = 50000
        bank_mismatches = [r for r in result if "INCOME_MISMATCH_BANK_W2" in r.get("check_type", "")]
        assert len(bank_mismatches) >= 1


# ===========================================================================
# 5. CROSS-VALIDATE EMPLOYMENT
# ===========================================================================

class TestCrossValidateEmployment:
    def test_matching_employers(self, service, mock_db):
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=1)
        assert len(result) == 0

    def test_different_employer_flagged(self, service, mock_db):
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Totally Different Company"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=1)
        name_mismatches = [r for r in result if r.get("check_type") == "EMPLOYER_NAME_MISMATCH"]
        assert len(name_mismatches) >= 1

    def test_ein_mismatch_critical(self, service, mock_db):
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "12-3456789"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp", "employer_ein": "98-7654321"},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=1)
        ein_mismatches = [r for r in result if r.get("check_type") == "EMPLOYER_EIN_MISMATCH"]
        assert len(ein_mismatches) >= 1
        assert ein_mismatches[0]["severity"] == "CRITICAL"

    def test_company_name_with_suffix_variation(self, service, mock_db):
        """Acme Corp vs Acme Corp Inc should match after normalization."""
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                extracted_fields={"employer_name": "Acme Corp"},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                extracted_fields={"employer_name": "Acme Corp Inc."},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.cross_validate_employment(loan_id=1)
        name_mismatches = [r for r in result if r.get("check_type") == "EMPLOYER_NAME_MISMATCH"]
        assert len(name_mismatches) == 0


# ===========================================================================
# 6. INCOME PLAUSIBILITY
# ===========================================================================

class TestCheckIncomePlausibility:
    def test_round_paystub_gross_flagged(self, service, mock_db):
        """Perfectly round gross pay (e.g., $5000.00) is suspicious."""
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            extracted_fields={"gross_pay": "5000.00"},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_income_plausibility(loan_id=1)
        round_flags = [i for i in result if "round number" in i.description.lower()]
        assert len(round_flags) >= 1

    def test_normal_paystub_gross_not_flagged(self, service, mock_db):
        """Normal gross pay like $4230.77 should not be flagged as round."""
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            extracted_fields={"gross_pay": "4230.77"},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_income_plausibility(loan_id=1)
        round_flags = [i for i in result if "round number" in i.description.lower()]
        assert len(round_flags) == 0

    def test_high_variable_pay_ratio(self, service, mock_db):
        """OT+bonus+commission > 80% of regular earnings is suspicious."""
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            extracted_fields={
                "gross_pay": "10000",
                "regular_earnings": "3000",
                "overtime_earnings": "4000",
                "bonus": "2000",
                "commission": "1000",
            },
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_income_plausibility(loan_id=1)
        variable_flags = [i for i in result if "Variable pay" in i.description]
        assert len(variable_flags) >= 1

    def test_no_documents(self, service, mock_db):
        mock_db.execute.return_value.fetchall.return_value = []
        result = service.check_income_plausibility(loan_id=1)
        assert result == []


# ===========================================================================
# 7. TEMPORAL ANOMALIES
# ===========================================================================

class TestCheckTemporalAnomalies:
    def test_future_dated_document(self, service, mock_db):
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            doc_date=future_date,
            uploaded_at=datetime.now(timezone.utc),
            extracted_fields={},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=1)
        future_flags = [i for i in result if "future" in i.description.lower()]
        assert len(future_flags) >= 1
        assert future_flags[0].severity == "HIGH"

    def test_weekend_pay_date(self, service, mock_db):
        """Pay date on Saturday is flagged as LOW severity."""
        # Find the next Saturday
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        saturday = today - timedelta(days=today.weekday() + 2)  # last Saturday

        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            doc_date=None,
            uploaded_at=datetime.now(timezone.utc),
            extracted_fields={
                "pay_date": saturday.strftime("%Y-%m-%d"),
            },
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=1)
        weekend_flags = [i for i in result if "Saturday" in i.description or "Sunday" in i.description]
        if saturday.weekday() in (5, 6):
            assert len(weekend_flags) >= 1
            assert weekend_flags[0].severity == "LOW"

    def test_pay_period_end_after_pay_date(self, service, mock_db):
        """Period end > pay date is a HIGH severity anomaly."""
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            doc_date=None,
            uploaded_at=datetime.now(timezone.utc),
            extracted_fields={
                "pay_date": "2026-01-15",
                "pay_period_end": "2026-01-20",
            },
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=1)
        period_flags = [i for i in result if "Pay period end" in i.description]
        assert len(period_flags) >= 1
        assert period_flags[0].severity == "HIGH"

    def test_bank_statement_gap(self, service, mock_db):
        """Gap > 5 days between bank statements flagged."""
        rows = [
            MagicMock(
                document_id=1, doc_type="BANK_STATEMENT",
                doc_date=None,
                uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "statement_start_date": "2026-01-01",
                    "statement_end_date": "2026-01-31",
                },
            ),
            MagicMock(
                document_id=2, doc_type="BANK_STATEMENT",
                doc_date=None,
                uploaded_at=datetime.now(timezone.utc),
                extracted_fields={
                    "statement_start_date": "2026-02-15",
                    "statement_end_date": "2026-03-15",
                },
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=1)
        gap_flags = [i for i in result if "Gap" in i.description]
        assert len(gap_flags) >= 1

    def test_uploaded_before_document_date(self, service, mock_db):
        """Document uploaded before its stated date is HIGH."""
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            doc_date=None,
            uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            extracted_fields={"pay_date": "2026-01-15"},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_temporal_anomalies(loan_id=1)
        upload_flags = [i for i in result if "uploaded" in i.description.lower() and "before" in i.description.lower()]
        assert len(upload_flags) >= 1


# ===========================================================================
# 8. SUSPICIOUS PATTERNS
# ===========================================================================

class TestCheckSuspiciousPatterns:
    def test_rapid_uploads(self, service, mock_db):
        """5+ documents uploaded within 2 minutes flagged."""
        base_time = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        rows = [
            MagicMock(
                document_id=i, doc_type="PAYSTUB",
                uploaded_at=base_time + timedelta(seconds=i * 10),
                file_name=f"doc{i}.pdf", file_size=1000 + i,
                extracted_fields={},
            )
            for i in range(6)
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=1)
        rapid_flags = [i for i in result if "batch fabrication" in i.description.lower()]
        assert len(rapid_flags) >= 1

    def test_identical_file_sizes(self, service, mock_db):
        """Documents with identical file sizes flagged."""
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                uploaded_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
                file_name="doc1.pdf", file_size=12345,
                extracted_fields={},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                uploaded_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
                file_name="doc2.pdf", file_size=12345,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=1)
        size_flags = [i for i in result if "identical file size" in i.description.lower()]
        assert len(size_flags) >= 1

    def test_near_ctr_threshold(self, service, mock_db):
        """Bank statement with total deposits $9,900-$9,999 flagged."""
        rows = [MagicMock(
            document_id=1, doc_type="BANK_STATEMENT",
            uploaded_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            file_name="stmt.pdf", file_size=5000,
            extracted_fields={"total_deposits": "9950"},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_suspicious_patterns(loan_id=1)
        ctr_flags = [i for i in result if "CTR" in i.description]
        assert len(ctr_flags) >= 1

    def test_no_documents(self, service, mock_db):
        mock_db.execute.return_value.fetchall.return_value = []
        result = service.check_suspicious_patterns(loan_id=1)
        assert result == []


# ===========================================================================
# 9. DUPLICATE SUBMISSIONS
# ===========================================================================

class TestCheckDuplicateSubmissions:
    def test_identical_ocr_text(self, service, mock_db):
        """Same OCR content across 2 documents flagged."""
        ocr = "This is the OCR text of a paystub with employer name and amounts and dates" + " " * 100
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                file_size=5000, ocr_text=ocr,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
            MagicMock(
                document_id=2, doc_type="PAYSTUB",
                file_size=5100, ocr_text=ocr,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_duplicate_submissions(loan_id=1)
        dup_flags = [i for i in result if i.indicator_type == "DUPLICATE_SUBMISSION"]
        assert len(dup_flags) >= 1

    def test_same_content_different_types_high_severity(self, service, mock_db):
        """Identical content submitted as different doc types is HIGH."""
        ocr = "Full document text content for a financial document with numbers and details" + " " * 100
        rows = [
            MagicMock(
                document_id=1, doc_type="PAYSTUB",
                file_size=5000, ocr_text=ocr,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
            MagicMock(
                document_id=2, doc_type="W2",
                file_size=5100, ocr_text=ocr,
                extracted_names=None, extracted_amount=None,
                extracted_fields={},
            ),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        result = service.check_duplicate_submissions(loan_id=1)
        dup_flags = [i for i in result if i.indicator_type == "DUPLICATE_SUBMISSION"]
        assert len(dup_flags) >= 1
        assert any(i.severity == "HIGH" for i in dup_flags)

    def test_single_document_returns_empty(self, service, mock_db):
        rows = [MagicMock(
            document_id=1, doc_type="PAYSTUB",
            file_size=5000, ocr_text="Some text",
            extracted_names=None, extracted_amount=None,
            extracted_fields={},
        )]
        mock_db.execute.return_value.fetchall.return_value = rows
        result = service.check_duplicate_submissions(loan_id=1)
        assert result == []


# ===========================================================================
# 10. PDF METADATA ANALYSIS
# ===========================================================================

class TestCheckDocumentMetadata:
    def test_photoshop_creator_critical(self, service):
        """PDF created with Photoshop flagged as CRITICAL."""
        pdf_content = b"%PDF-1.4 /Creator (Adobe Photoshop) /Producer (Adobe Photoshop)"
        result = service.check_document_metadata(document_id=1, file_content=pdf_content)
        altered_flags = [i for i in result if i.indicator_type == "ALTERED_TEXT"]
        assert len(altered_flags) >= 1
        assert altered_flags[0].severity == "CRITICAL"

    def test_legitimate_creator_no_flag(self, service):
        """PDF from a legitimate tool (e.g., ADP) should not be flagged."""
        pdf_content = b"%PDF-1.4 /Creator (ADP Payroll System) /Producer (iText)"
        result = service.check_document_metadata(document_id=1, file_content=pdf_content)
        creator_flags = [
            i for i in result
            if i.indicator_type == "ALTERED_TEXT" and "editing software" in i.description.lower()
        ]
        assert len(creator_flags) == 0

    def test_modification_after_creation(self, service):
        """Large gap between creation and modification flagged."""
        pdf_content = (
            b"%PDF-1.4 "
            b"/Creator (Word) "
            b"/CreationDate (D:20260101120000) "
            b"/ModDate (D:20260115120000)"
        )
        result = service.check_document_metadata(document_id=1, file_content=pdf_content)
        mod_flags = [i for i in result if "modified" in i.description.lower()]
        assert len(mod_flags) >= 1

    def test_no_metadata_returns_empty(self, service):
        """Non-PDF or minimal content returns no indicators."""
        result = service.check_document_metadata(document_id=1, file_content=b"not a pdf")
        assert result == []

    def test_gimp_flagged(self, service):
        pdf_content = b"%PDF-1.4 /Creator (GIMP 2.10) /Producer (cairo)"
        result = service.check_document_metadata(document_id=1, file_content=pdf_content)
        assert any(i.severity == "CRITICAL" for i in result)


# ===========================================================================
# 11. SANITIZED REPORT ACCESS LEVELS
# ===========================================================================

class TestGenerateSanitizedReport:
    def test_restricted_hides_fraud_details(self, service, mock_db):
        """Restricted (borrower) access only shows neutral document_status."""
        # Mock analyze_loan_documents to return a result
        with patch.object(service, "analyze_loan_documents") as mock_analyze:
            mock_analyze.return_value = CrossValidationResult(
                loan_id=1, documents_analyzed=5, inconsistencies=[],
                fraud_indicators=[_make_indicator(severity="HIGH")],
                risk_score=40, risk_level="MEDIUM",
                summary="Test", recommendations=["Review"],
            )
            result = service.generate_sanitized_report(
                loan_id=1, organization_id=1, access_level="restricted"
            )
            assert "fraud_indicators" not in result
            assert "risk_score" not in result
            assert result["document_status"] == "under_review"

    def test_summary_shows_risk_score(self, service, mock_db):
        """Summary access shows risk but no indicator details."""
        with patch.object(service, "analyze_loan_documents") as mock_analyze:
            mock_analyze.return_value = CrossValidationResult(
                loan_id=1, documents_analyzed=5, inconsistencies=[],
                fraud_indicators=[], risk_score=10, risk_level="LOW",
                summary="Clean", recommendations=["All clear"],
            )
            result = service.generate_sanitized_report(
                loan_id=1, organization_id=1, access_level="summary"
            )
            assert result["risk_score"] == 10
            assert "fraud_indicators" not in result

    def test_full_shows_everything(self, service, mock_db):
        """Full access shows all fraud indicators and details."""
        indicator = _make_indicator(severity="HIGH")
        with patch.object(service, "analyze_loan_documents") as mock_analyze:
            mock_analyze.return_value = CrossValidationResult(
                loan_id=1, documents_analyzed=5,
                inconsistencies=[{"check_type": "NAME_MISMATCH"}],
                fraud_indicators=[indicator],
                risk_score=30, risk_level="MEDIUM",
                summary="Findings", recommendations=["Review"],
            )
            result = service.generate_sanitized_report(
                loan_id=1, organization_id=1, access_level="full"
            )
            assert "fraud_indicators" in result
            assert len(result["fraud_indicators"]) == 1
            assert "inconsistencies" in result

    def test_restricted_high_risk_under_review(self, service, mock_db):
        """HIGH risk in restricted mode shows 'under_review'."""
        with patch.object(service, "analyze_loan_documents") as mock_analyze:
            mock_analyze.return_value = CrossValidationResult(
                loan_id=1, documents_analyzed=5, inconsistencies=[],
                fraud_indicators=[], risk_score=60, risk_level="HIGH",
                summary="Test", recommendations=[],
            )
            result = service.generate_sanitized_report(
                loan_id=1, organization_id=1, access_level="restricted"
            )
            assert result["document_status"] == "under_review"

    def test_restricted_zero_risk_approved(self, service, mock_db):
        with patch.object(service, "analyze_loan_documents") as mock_analyze:
            mock_analyze.return_value = CrossValidationResult(
                loan_id=1, documents_analyzed=5, inconsistencies=[],
                fraud_indicators=[], risk_score=0, risk_level="LOW",
                summary="Clean", recommendations=[],
            )
            result = service.generate_sanitized_report(
                loan_id=1, organization_id=1, access_level="restricted"
            )
            assert result["document_status"] == "approved"


# ===========================================================================
# 12. BUILD RECOMMENDATIONS
# ===========================================================================

class TestBuildRecommendations:
    def test_critical_risk_escalation(self, service):
        indicators = [_make_indicator(severity="CRITICAL")]
        recs = service._build_recommendations(indicators, [], "CRITICAL")
        assert any("escalate" in r.lower() for r in recs)
        assert any("hold" in r.lower() for r in recs)

    def test_high_risk_hold(self, service):
        indicators = [_make_indicator(severity="HIGH")]
        recs = service._build_recommendations(indicators, [], "HIGH")
        assert any("hold" in r.lower() for r in recs)

    def test_low_risk_proceed(self, service):
        recs = service._build_recommendations([], [], "LOW")
        assert any("proceed" in r.lower() or "no significant" in r.lower() for r in recs)

    def test_deduplication(self, service):
        indicators = [
            _make_indicator(severity="HIGH", description="Issue A"),
            _make_indicator(severity="HIGH", description="Issue B"),
        ]
        # Both have same recommendation text
        recs = service._build_recommendations(indicators, [], "HIGH")
        # Unique recommendations: the "hold" + "Review manually" from indicators
        unique_recs = set(recs)
        assert len(unique_recs) == len(recs)


# ===========================================================================
# 13. MAIN ENTRY POINT
# ===========================================================================

class TestAnalyzeLoanDocuments:
    def test_no_documents_returns_clean(self, service, mock_db):
        # First call: org check
        # Second call: doc count
        call_count = [0]
        def side_effect(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                row = MagicMock()
                row.organization_id = 1
                result.fetchone.return_value = row
            elif call_count[0] == 2:
                row = MagicMock()
                row.cnt = 0
                result.fetchone.return_value = row
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = None
            return result
        mock_db.execute.side_effect = side_effect

        result = service.analyze_loan_documents(loan_id=1)
        assert result.documents_analyzed == 0
        assert result.risk_level == "LOW"
        assert "No documents found" in result.summary

    def test_tenant_isolation(self, service, mock_db):
        """Loan from different org returns access denied."""
        row = MagicMock()
        row.organization_id = 999
        mock_db.execute.return_value.fetchone.return_value = row

        result = service.analyze_loan_documents(loan_id=1)
        assert "Access denied" in result.summary

    def test_no_org_skips_tenant_check(self, service_no_org, mock_db):
        """Without org_id, tenant check is skipped."""
        # doc count
        row = MagicMock()
        row.cnt = 0
        mock_db.execute.return_value.fetchone.return_value = row

        result = service_no_org.analyze_loan_documents(loan_id=1)
        assert result.documents_analyzed == 0


# ===========================================================================
# 14. COMBINE ANALYSIS SCORES
# ===========================================================================

class TestCombineAnalysisScores:
    def test_all_components(self, service):
        vendor = MagicMock(risk_score=50)
        forensics = MagicMock(risk_score=30)
        cross_doc = MagicMock(risk_score=20)

        score, level = service._combine_analysis_scores(
            vendor_result=vendor,
            forensics_result=forensics,
            cross_doc_result=cross_doc,
        )
        # (50*0.4 + 30*0.3 + 20*0.3) / 1.0 = 20+9+6 = 35
        assert 34 <= score <= 36

    def test_vendor_only(self, service):
        vendor = MagicMock(risk_score=80)
        score, level = service._combine_analysis_scores(
            vendor_result=vendor, forensics_result=None, cross_doc_result=None,
        )
        assert score == 80.0

    def test_no_components(self, service):
        score, level = service._combine_analysis_scores()
        assert score == 0.0
        assert level == "LOW"

    def test_high_combined_score(self, service):
        vendor = MagicMock(risk_score=90)
        forensics = MagicMock(risk_score=80)
        cross_doc = MagicMock(risk_score=70)
        score, level = service._combine_analysis_scores(
            vendor_result=vendor, forensics_result=forensics, cross_doc_result=cross_doc,
        )
        assert level in ("HIGH", "CRITICAL")


# ===========================================================================
# 15. FACTORY FUNCTION
# ===========================================================================

class TestFactory:
    def test_get_fraud_detection_service(self, mock_db):
        svc = get_fraud_detection_service(mock_db, org_id=5)
        assert isinstance(svc, FraudDetectionService)
        assert svc.org_id == 5

    def test_get_fraud_detection_service_no_org(self, mock_db):
        svc = get_fraud_detection_service(mock_db)
        assert svc.org_id is None


# ===========================================================================
# 16. NAME VARIATION REVERSE LOOKUP
# ===========================================================================

class TestNameVariationReverseLookup:
    def test_formal_maps_to_itself(self):
        assert _NAME_REVERSE["william"] == "william"

    def test_variant_maps_to_formal(self):
        assert _NAME_REVERSE["bill"] == "william"
        assert _NAME_REVERSE["bob"] == "robert"
        assert _NAME_REVERSE["liz"] == "elizabeth"
        assert _NAME_REVERSE["mike"] == "michael"

    def test_unknown_name_not_in_reverse(self):
        assert "zzzzunknown" not in _NAME_REVERSE


# ===========================================================================
# 17. EXTRACT NAMES FROM ROW
# ===========================================================================

class TestExtractNamesFromRow:
    def test_from_extracted_names_list(self, service):
        row = MagicMock()
        row.extracted_names = ["John Doe", "Jane Doe"]
        row.extracted_fields = {}
        names = service._extract_names_from_row(row)
        assert "John Doe" in names
        assert "Jane Doe" in names

    def test_from_extracted_fields(self, service):
        row = MagicMock()
        row.extracted_names = None
        row.extracted_fields = {"employee_name": "Maria Gonzalez"}
        names = service._extract_names_from_row(row)
        assert "Maria Gonzalez" in names

    def test_builds_full_name_from_parts(self, service):
        row = MagicMock()
        row.extracted_names = None
        row.extracted_fields = {"first_name": "John", "last_name": "Smith"}
        names = service._extract_names_from_row(row)
        assert "John Smith" in names

    def test_empty_row(self, service):
        row = MagicMock()
        row.extracted_names = None
        row.extracted_fields = {}
        names = service._extract_names_from_row(row)
        assert names == []

    def test_deduplicates(self, service):
        row = MagicMock()
        row.extracted_names = ["John Doe", "John Doe"]
        row.extracted_fields = {"employee_name": "John Doe"}
        names = service._extract_names_from_row(row)
        assert len(names) == len(set(names))
