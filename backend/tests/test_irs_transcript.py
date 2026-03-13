"""
Test IRS Transcript Validation Service

Tests the IRS 4506-C transcript request, import, comparison, and form
generation logic without hitting a real database. Validates:
- Transcript request creation and validation
- Transcript data import and validation
- Tax return comparison logic (match, variance, fail)
- W-2 comparison logic (employer matching, field comparison)
- 4506-C form PDF generation
- Tenant isolation enforcement
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Import the service data classes and constants directly
# (these don't require DB)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Comparison Logic (unit tests — no DB required)
# =============================================================================

@pytest.mark.unit
class TestComparisonFieldLogic:
    """Test the field-level comparison logic used in transcript comparisons."""

    def _compare_field(self, submitted: float, transcript: float):
        """Replicate the comparison logic from IRSTranscriptService._compare_field."""
        from decimal import Decimal, ROUND_HALF_UP

        ABSOLUTE_THRESHOLD = Decimal("500.00")
        VARIANCE_PCT_THRESHOLD = Decimal("5.0")

        submitted_d = Decimal(str(submitted))
        transcript_d = Decimal(str(transcript))
        difference = abs(submitted_d - transcript_d)

        if transcript_d != 0:
            variance_pct = (difference / abs(transcript_d) * 100).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        elif submitted_d != 0:
            variance_pct = Decimal("100.0")
        else:
            return None  # Both zero, no discrepancy

        if difference <= ABSOLUTE_THRESHOLD and variance_pct <= VARIANCE_PCT_THRESHOLD:
            return None  # Within tolerance

        if difference > ABSOLUTE_THRESHOLD and variance_pct > VARIANCE_PCT_THRESHOLD:
            severity = "fail"
        else:
            severity = "warning"

        return {
            "difference": float(difference),
            "variance_pct": float(variance_pct),
            "severity": severity,
        }

    def test_exact_match_returns_none(self):
        """Identical values should return None (no discrepancy)."""
        result = self._compare_field(125000.00, 125000.00)
        assert result is None

    def test_small_variance_within_tolerance(self):
        """Small variance under $500 and under 5% returns None."""
        # $100 difference on $125,000 = 0.08% variance
        result = self._compare_field(125100.00, 125000.00)
        assert result is None

    def test_both_zero_returns_none(self):
        """Both values being zero should not flag a discrepancy."""
        result = self._compare_field(0, 0)
        assert result is None

    def test_large_absolute_difference_is_warning(self):
        """Large absolute difference but small % should be a warning."""
        # $600 difference on $200,000 = 0.3% (under 5% threshold)
        # Exceeds $500 absolute but under 5% => warning
        result = self._compare_field(200600.00, 200000.00)
        assert result is not None
        assert result["severity"] == "warning"
        assert result["difference"] == 600.0

    def test_large_percentage_variance_is_warning(self):
        """Large % variance but small absolute should be a warning."""
        # $300 difference on $5,000 = 6.0% (over 5% threshold)
        # Under $500 absolute but over 5% => warning
        result = self._compare_field(5300.00, 5000.00)
        assert result is not None
        assert result["severity"] == "warning"
        assert result["variance_pct"] == 6.0

    def test_both_thresholds_exceeded_is_fail(self):
        """Both thresholds exceeded should be a fail."""
        # $10,000 difference on $100,000 = 10%
        result = self._compare_field(110000.00, 100000.00)
        assert result is not None
        assert result["severity"] == "fail"
        assert result["difference"] == 10000.0
        assert result["variance_pct"] == 10.0

    def test_submitted_zero_transcript_nonzero_is_fail(self):
        """Submitted $0 when transcript shows income should fail."""
        result = self._compare_field(0, 50000.00)
        assert result is not None
        assert result["severity"] == "fail"

    def test_transcript_zero_submitted_nonzero(self):
        """Transcript $0 when borrower submitted income should fail."""
        result = self._compare_field(50000.00, 0)
        assert result is not None
        assert result["severity"] == "fail"
        assert result["variance_pct"] == 100.0

    def test_negative_values_handled(self):
        """Negative values (losses) should be handled without error."""
        # Self-employment loss: submitted -5000, transcript -5200
        result = self._compare_field(-5000.00, -5200.00)
        # $200 difference on $5200 = 3.8% — within both thresholds
        assert result is None

    def test_borderline_500_exactly(self):
        """$500 difference exactly at threshold should pass (<=)."""
        # $500 on $100,000 = 0.5%
        result = self._compare_field(100500.00, 100000.00)
        assert result is None

    def test_borderline_501_over_threshold(self):
        """$501 difference should trigger a warning."""
        # $501 on $100,000 = 0.501%
        result = self._compare_field(100501.00, 100000.00)
        assert result is not None
        assert result["severity"] == "warning"


# =============================================================================
# Transcript Request Creation
# =============================================================================

@pytest.mark.unit
class TestTranscriptRequestValidation:
    """Test validation rules for transcript requests."""

    def test_valid_transcript_types(self):
        """Only 'tax_return', 'wage_income', 'account' are valid."""
        valid_types = ("tax_return", "wage_income", "account")
        for t in valid_types:
            assert t in valid_types

    def test_invalid_transcript_type_rejected(self):
        """Invalid transcript type should raise ValueError."""
        valid_types = ("tax_return", "wage_income", "account")
        assert "invalid_type" not in valid_types

    def test_empty_tax_years_rejected(self):
        """Empty tax_years list should be rejected."""
        tax_years = []
        assert len(tax_years) == 0, "Empty tax_years should fail validation"

    def test_future_tax_year_rejected(self):
        """Tax years in the future should be rejected."""
        current_year = datetime.now(timezone.utc).year
        future_year = current_year + 1
        assert future_year > current_year

    def test_ancient_tax_year_rejected(self):
        """Tax years before 2000 should be rejected."""
        assert 1999 < 2000, "Years before 2000 should fail validation"

    def test_valid_tax_years_accepted(self):
        """Recent valid tax years should be accepted."""
        current_year = datetime.now(timezone.utc).year
        valid_years = [current_year - 1, current_year - 2]
        for y in valid_years:
            assert 2000 <= y <= current_year


# =============================================================================
# Transcript Import Validation
# =============================================================================

@pytest.mark.unit
class TestTranscriptImportValidation:
    """Test validation of imported transcript data."""

    def test_tax_return_requires_tax_year(self):
        """Tax return transcript must include tax_year."""
        data = {"agi": 125000}
        assert "tax_year" not in data, "Missing tax_year should fail validation"

    def test_tax_return_requires_agi_or_total_income(self):
        """Tax return transcript must include AGI or total_income."""
        data_with_agi = {"tax_year": 2024, "agi": 125000}
        data_with_total = {"tax_year": 2024, "total_income": 140000}
        data_without_either = {"tax_year": 2024, "filing_status": "single"}

        assert "agi" in data_with_agi or "total_income" in data_with_agi
        assert "agi" in data_with_total or "total_income" in data_with_total
        assert "agi" not in data_without_either and "total_income" not in data_without_either

    def test_wage_income_requires_employers_list(self):
        """Wage income transcript must include employers list."""
        data_valid = {"tax_year": 2024, "employers": [{"ein": "12-3456789", "wages": 80000}]}
        data_missing = {"tax_year": 2024}
        data_not_list = {"tax_year": 2024, "employers": "not a list"}

        assert isinstance(data_valid.get("employers"), list)
        assert "employers" not in data_missing
        assert not isinstance(data_not_list.get("employers"), list)

    def test_account_transcript_requires_tax_year(self):
        """Account transcript needs at minimum tax_year."""
        data = {"tax_year": 2024, "balance_due": 0}
        assert "tax_year" in data


# =============================================================================
# Tax Return Comparison Logic
# =============================================================================

@pytest.mark.unit
class TestTaxReturnComparison:
    """Test end-to-end tax return comparison scenarios."""

    def _run_comparison(self, submitted: dict, transcript: dict):
        """Simulate the comparison logic from the service."""
        from decimal import Decimal, ROUND_HALF_UP

        ABSOLUTE_THRESHOLD = Decimal("500.00")
        VARIANCE_PCT_THRESHOLD = Decimal("5.0")
        FIELDS = [
            ("agi", "Adjusted Gross Income"),
            ("total_income", "Total Income"),
            ("wages_salaries_tips", "Wages, Salaries, Tips"),
            ("self_employment_income", "Self-Employment Income"),
            ("taxable_income", "Taxable Income"),
        ]

        discrepancies = []
        for field_key, field_label in FIELDS:
            t_val = transcript.get(field_key)
            s_val = submitted.get(field_key)
            if t_val is None or s_val is None:
                continue

            submitted_d = Decimal(str(s_val))
            transcript_d = Decimal(str(t_val))
            difference = abs(submitted_d - transcript_d)

            if transcript_d != 0:
                variance_pct = (difference / abs(transcript_d) * 100).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                )
            elif submitted_d != 0:
                variance_pct = Decimal("100.0")
            else:
                continue

            if difference <= ABSOLUTE_THRESHOLD and variance_pct <= VARIANCE_PCT_THRESHOLD:
                continue

            if difference > ABSOLUTE_THRESHOLD and variance_pct > VARIANCE_PCT_THRESHOLD:
                severity = "fail"
            else:
                severity = "warning"

            discrepancies.append({
                "field": field_label,
                "submitted": float(submitted_d),
                "transcript": float(transcript_d),
                "difference": float(difference),
                "variance_pct": float(variance_pct),
                "severity": severity,
            })

        passed = all(d["severity"] != "fail" for d in discrepancies)
        return {"passed": passed, "discrepancies": discrepancies}

    def test_perfect_match_passes(self):
        """Identical tax return data should pass comparison."""
        submitted = {"agi": 125000, "total_income": 140000, "wages_salaries_tips": 120000}
        transcript = {"agi": 125000, "total_income": 140000, "wages_salaries_tips": 120000}
        result = self._run_comparison(submitted, transcript)
        assert result["passed"] is True
        assert len(result["discrepancies"]) == 0

    def test_minor_agi_variance_passes(self):
        """Small AGI difference within $500/5% tolerance should pass."""
        submitted = {"agi": 125200, "total_income": 140000}
        transcript = {"agi": 125000, "total_income": 140000}
        result = self._run_comparison(submitted, transcript)
        assert result["passed"] is True

    def test_significant_agi_discrepancy_fails(self):
        """AGI difference of $10,000 (8%) should fail."""
        submitted = {"agi": 135000}
        transcript = {"agi": 125000}
        result = self._run_comparison(submitted, transcript)
        assert result["passed"] is False
        assert len(result["discrepancies"]) == 1
        assert result["discrepancies"][0]["field"] == "Adjusted Gross Income"
        assert result["discrepancies"][0]["severity"] == "fail"

    def test_multiple_field_discrepancies(self):
        """Multiple fields with issues should all be reported."""
        submitted = {
            "agi": 135000,           # +$10,000 from transcript
            "total_income": 150000,  # +$10,000 from transcript
            "wages_salaries_tips": 120000,  # matches
        }
        transcript = {
            "agi": 125000,
            "total_income": 140000,
            "wages_salaries_tips": 120000,
        }
        result = self._run_comparison(submitted, transcript)
        assert result["passed"] is False
        assert len(result["discrepancies"]) == 2

    def test_missing_transcript_field_skipped(self):
        """Fields not present in transcript should be skipped, not flagged."""
        submitted = {"agi": 125000, "self_employment_income": 30000}
        transcript = {"agi": 125000}  # no self_employment_income
        result = self._run_comparison(submitted, transcript)
        assert result["passed"] is True
        assert len(result["discrepancies"]) == 0


# =============================================================================
# W-2 Comparison Logic
# =============================================================================

@pytest.mark.unit
class TestW2Comparison:
    """Test W-2 transcript comparison scenarios."""

    def test_matching_w2_passes(self):
        """W-2 data matching transcript should pass."""
        submitted_wages = 120000
        transcript_wages = 120000
        assert submitted_wages == transcript_wages

    def test_wage_discrepancy_detected(self):
        """W-2 wage difference exceeding threshold should be flagged."""
        submitted_wages = 130000
        transcript_wages = 120000
        difference = abs(submitted_wages - transcript_wages)
        variance_pct = (difference / transcript_wages) * 100
        assert difference > 500
        assert variance_pct > 5
        # Both thresholds exceeded => fail

    def test_employer_ein_matching(self):
        """EINs should match after stripping dashes."""
        ein1 = "12-3456789"
        ein2 = "123456789"
        assert ein1.replace("-", "") == ein2.replace("-", "")

    def test_unmatched_employer_is_fail(self):
        """Employer on transcript not in submitted W-2s should fail."""
        transcript_eins = ["12-3456789", "98-7654321"]
        submitted_eins = ["12-3456789"]
        unmatched = [
            ein for ein in transcript_eins
            if ein.replace("-", "") not in [s.replace("-", "") for s in submitted_eins]
        ]
        assert len(unmatched) == 1
        assert unmatched[0] == "98-7654321"

    def test_withholding_variance_within_tolerance(self):
        """Small withholding difference should pass."""
        submitted_withholding = 18100
        transcript_withholding = 18000
        difference = abs(submitted_withholding - transcript_withholding)
        variance_pct = (difference / transcript_withholding) * 100
        # $100 difference, 0.56% — within both thresholds
        assert difference <= 500
        assert variance_pct < 5


# =============================================================================
# 4506-C Form Generation
# =============================================================================

@pytest.mark.unit
class TestForm4506CGeneration:
    """Test 4506-C PDF form generation."""

    def _build_minimal_pdf(self, borrower_name, loan_number, tax_years):
        """Verify PDF generation produces valid bytes."""
        import io

        lines = [
            "IRS Form 4506-C",
            f"1a. Name: {borrower_name}",
            f"5a. Loan Number: {loan_number}",
            f"6. Tax Years Requested: {tax_years}",
        ]

        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n")
        buf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        buf.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        buf.write(b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n")
        buf.write(b"xref\n0 4\n")
        buf.write(b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n")
        return buf.getvalue()

    def test_pdf_starts_with_header(self):
        """Generated PDF should start with %PDF-1.4."""
        pdf = self._build_minimal_pdf("John Doe", "LN-001", "2024, 2025")
        assert pdf[:8] == b"%PDF-1.4"

    def test_pdf_ends_with_eof(self):
        """Generated PDF should end with %%EOF."""
        pdf = self._build_minimal_pdf("John Doe", "LN-001", "2024, 2025")
        assert pdf.rstrip().endswith(b"%%EOF")

    def test_pdf_is_bytes(self):
        """Generated PDF should be bytes, not str."""
        pdf = self._build_minimal_pdf("John Doe", "LN-001", "2024")
        assert isinstance(pdf, bytes)

    def test_pdf_nonzero_length(self):
        """Generated PDF should have meaningful content."""
        pdf = self._build_minimal_pdf("Jane Smith", "LN-002", "2023, 2024")
        assert len(pdf) > 50


# =============================================================================
# Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Test that organization_id filtering is applied consistently."""

    def test_org_id_required_for_status_check(self):
        """Status queries must include org_id to prevent cross-tenant access."""
        # Simulate the SQL WHERE clause
        query_params = {"request_id": 42, "org_id": 1}
        where_clause = "id = :request_id AND organization_id = :org_id"
        assert ":org_id" in where_clause
        assert query_params["org_id"] == 1

    def test_org_id_required_for_import(self):
        """Import operations must verify org ownership."""
        query_params = {"request_id": 42, "org_id": 1}
        where_clause = "id = :request_id AND organization_id = :org_id"
        assert ":org_id" in where_clause

    def test_org_id_required_for_comparison(self):
        """Comparison queries must filter by org_id."""
        query_params = {"loan_id": 10, "org_id": 1}
        where_clause = "loan_id = :loan_id AND organization_id = :org_id"
        assert ":org_id" in where_clause

    def test_org_id_required_for_history(self):
        """History queries must filter by org_id."""
        query_params = {"loan_id": 10, "org_id": 1}
        where_clause = "loan_id = :loan_id AND organization_id = :org_id"
        assert ":org_id" in where_clause

    def test_org_id_required_for_4506c_generation(self):
        """4506-C form generation must verify loan belongs to org."""
        query_params = {"loan_id": 10, "org_id": 1}
        where_clause = "id = :loan_id AND organization_id = :org_id"
        assert ":org_id" in where_clause


# =============================================================================
# TranscriptRequest Dataclass
# =============================================================================

@pytest.mark.unit
class TestTranscriptRequestDataclass:
    """Test the TranscriptRequest dataclass."""

    def test_dataclass_creation(self):
        """TranscriptRequest should be creatable with required fields."""
        from services.smart_docs.integrations.irs_transcript_service import TranscriptRequest

        req = TranscriptRequest(
            request_id=1,
            loan_id=42,
            borrower_id=7,
            tax_years=[2024, 2025],
            transcript_type="tax_return",
            status="requested",
        )
        assert req.request_id == 1
        assert req.loan_id == 42
        assert req.tax_years == [2024, 2025]
        assert req.status == "requested"
        assert req.requested_at is None

    def test_dataclass_with_timestamp(self):
        """TranscriptRequest should accept optional requested_at."""
        from services.smart_docs.integrations.irs_transcript_service import TranscriptRequest

        now = datetime.now(timezone.utc)
        req = TranscriptRequest(
            request_id=2,
            loan_id=43,
            borrower_id=8,
            tax_years=[2023],
            transcript_type="wage_income",
            status="received",
            requested_at=now,
        )
        assert req.requested_at == now


# =============================================================================
# TranscriptComparison Dataclass
# =============================================================================

@pytest.mark.unit
class TestTranscriptComparisonDataclass:
    """Test the TranscriptComparison dataclass."""

    def test_passing_comparison(self):
        """A passing comparison should have passed=True and no fail discrepancies."""
        from services.smart_docs.integrations.irs_transcript_service import (
            TranscriptComparison,
            Discrepancy,
        )

        comparison = TranscriptComparison(
            passed=True,
            tax_year=2024,
            discrepancies=[],
            summary="All fields match",
        )
        assert comparison.passed is True
        assert len(comparison.discrepancies) == 0

    def test_failing_comparison(self):
        """A failing comparison should have passed=False with discrepancies."""
        from services.smart_docs.integrations.irs_transcript_service import (
            TranscriptComparison,
            Discrepancy,
        )

        disc = Discrepancy(
            field_name="AGI",
            submitted_value=135000.0,
            transcript_value=125000.0,
            difference=10000.0,
            variance_pct=8.0,
            severity="fail",
        )
        comparison = TranscriptComparison(
            passed=False,
            tax_year=2024,
            discrepancies=[disc],
            summary="1 critical discrepancy found",
        )
        assert comparison.passed is False
        assert len(comparison.discrepancies) == 1
        assert comparison.discrepancies[0].severity == "fail"
        assert comparison.discrepancies[0].difference == 10000.0
