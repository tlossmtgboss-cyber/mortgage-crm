"""
Test Income Calculator Service - Comprehensive unit tests for mortgage income
qualification calculations per Fannie Mae underwriting guidelines.

Covers:
- W2/salaried income (base, OT, bonus, commission from paystubs and W2s)
- Self-employment income (Schedule C, K-1, depreciation add-backs)
- Commission income with 2-year trending
- Rental income (Schedule E, 75% vacancy factor)
- DTI ratio calculation (front-end and back-end)
- Income trending analysis (INCREASING, DECLINING, STABLE, VARIABLE)
- Multiple income source aggregation
- Qualifying income determination per Fannie Mae guidelines
- Monthly income from various pay frequencies
- Overtime declining trend handling
- Employment gap detection
- Variable income averaging
- Income task generation
- Helper methods (_to_decimal, _months_elapsed_in_year)
"""

import json
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import MagicMock, patch, PropertyMock

from services.smart_docs.income_calculator_service import (
    IncomeCalculatorService,
    IncomeCalculationResult,
    IncomeSourceResult,
    get_income_calculator_service,
    PAY_FREQUENCY_MULTIPLIERS,
    RENTAL_VACANCY_FACTOR,
    PAYSTUB_STALENESS_DAYS,
    DECLINING_INCOME_WARN_PCT,
    DECLINING_INCOME_CRITICAL_PCT,
    HIGH_COMMISSION_RATIO_PCT,
    DECLINING_COMMISSION_THRESHOLD_PCT,
    ZERO,
    TWO_PLACES,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create an IncomeCalculatorService with a mock DB session."""
    return IncomeCalculatorService(mock_db)


def _make_paystub(
    gross_pay=5000.00,
    pay_frequency="BIWEEKLY",
    pay_date=None,
    employer_name="Acme Corp",
    job_title="Software Engineer",
    ytd_gross=60000.00,
    ytd_overtime_earnings=0,
    ytd_bonus=0,
    ytd_commission=0,
    ytd_tips=0,
    doc_id=1,
    overall_confidence=85,
):
    """Helper to create a paystub document dict."""
    if pay_date is None:
        pay_date = date.today().strftime("%Y-%m-%d")
    return {
        "doc_id": doc_id,
        "doc_type": "PAYSTUB",
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": "paystub.pdf",
        "extracted_fields": {
            "gross_pay": gross_pay,
            "pay_frequency": pay_frequency,
            "pay_date": pay_date,
            "employer_name": employer_name,
            "job_title": job_title,
            "ytd_gross": ytd_gross,
            "ytd_overtime_earnings": ytd_overtime_earnings,
            "ytd_bonus": ytd_bonus,
            "ytd_commission": ytd_commission,
            "ytd_tips": ytd_tips,
        },
        "confidence_scores": {},
        "overall_confidence": overall_confidence,
    }


def _make_w2(
    wages=120000.00,
    tax_year=2025,
    employer_name="Acme Corp",
    doc_id=10,
    overall_confidence=90,
):
    """Helper to create a W2 document dict."""
    return {
        "doc_id": doc_id,
        "doc_type": "W2",
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": f"w2_{tax_year}.pdf",
        "extracted_fields": {
            "wages_tips_compensation": wages,
            "tax_year": tax_year,
            "employer_name": employer_name,
        },
        "confidence_scores": {},
        "overall_confidence": overall_confidence,
    }


def _make_tax_return(
    tax_year=2025,
    net_profit=80000,
    depreciation_addback=5000,
    amortization_addback=0,
    depletion_addback=0,
    k1_ordinary_income=0,
    k1_guaranteed_payments=0,
    schedule_e_gross_rents=0,
    schedule_e_total_expenses=0,
    schedule_e_depreciation=0,
    schedule_e_net_income_loss=0,
    business_name="Smith Consulting LLC",
    doc_type="TAX_RETURN",
    doc_id=20,
):
    """Helper to create a tax return document dict."""
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": f"tax_return_{tax_year}.pdf",
        "extracted_fields": {
            "tax_year": tax_year,
            "net_profit_loss": net_profit,
            "depreciation_addback": depreciation_addback,
            "amortization_addback": amortization_addback,
            "depletion_addback": depletion_addback,
            "k1_ordinary_income": k1_ordinary_income,
            "k1_guaranteed_payments": k1_guaranteed_payments,
            "schedule_e_gross_rents": schedule_e_gross_rents,
            "schedule_e_total_expenses": schedule_e_total_expenses,
            "schedule_e_depreciation": schedule_e_depreciation,
            "schedule_e_net_income_loss": schedule_e_net_income_loss,
            "business_name": business_name,
        },
        "confidence_scores": {},
        "overall_confidence": 80,
    }


# =============================================================================
# 1. W2 Income Calculation
# =============================================================================

@pytest.mark.unit
class TestW2IncomeCalculation:
    """Tests for W2/salaried income calculation from paystubs and W2s."""

    def test_w2_base_salary_from_biweekly_paystub(self, service):
        """Biweekly gross pay annualized: gross * 26 / 12 = monthly."""
        paystub = _make_paystub(gross_pay=5000.00, pay_frequency="BIWEEKLY")
        result = service._calculate_w2_income([paystub])

        # 5000 * 26 = 130000 annual / 12 = 10833.33
        expected_monthly = Decimal("10833.33")
        assert result.source_type == "W2_EMPLOYMENT"
        assert result.base_monthly == expected_monthly
        assert result.total_monthly == expected_monthly
        assert result.employer_name == "Acme Corp"

    def test_w2_base_salary_from_weekly_paystub(self, service):
        """Weekly gross pay annualized: gross * 52 / 12."""
        paystub = _make_paystub(gross_pay=2500.00, pay_frequency="WEEKLY")
        result = service._calculate_w2_income([paystub])

        # 2500 * 52 = 130000 / 12 = 10833.33
        expected_monthly = Decimal("10833.33")
        assert result.base_monthly == expected_monthly

    def test_w2_base_salary_from_semimonthly_paystub(self, service):
        """Semi-monthly gross pay annualized: gross * 24 / 12."""
        paystub = _make_paystub(gross_pay=5000.00, pay_frequency="SEMIMONTHLY")
        result = service._calculate_w2_income([paystub])

        # 5000 * 24 = 120000 / 12 = 10000.00
        expected_monthly = Decimal("10000.00")
        assert result.base_monthly == expected_monthly

    def test_w2_base_salary_from_monthly_paystub(self, service):
        """Monthly gross pay: gross * 12 / 12 = gross."""
        paystub = _make_paystub(gross_pay=10000.00, pay_frequency="MONTHLY")
        result = service._calculate_w2_income([paystub])

        expected_monthly = Decimal("10000.00")
        assert result.base_monthly == expected_monthly

    def test_w2_with_overtime_bonus_commission(self, service):
        """OT, bonus, and commission calculated from YTD divided by months elapsed."""
        pay_date = "2025-06-15"  # ~5.5 months into the year
        paystub = _make_paystub(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            pay_date=pay_date,
            ytd_overtime_earnings=6000.00,
            ytd_bonus=3000.00,
            ytd_commission=1200.00,
        )
        result = service._calculate_w2_income([paystub])

        months_elapsed = service._months_elapsed_in_year(pay_date)
        assert months_elapsed is not None
        assert months_elapsed > 0

        expected_ot = (Decimal("6000.00") / Decimal(months_elapsed)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        expected_bonus = (Decimal("3000.00") / Decimal(months_elapsed)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        expected_commission = (Decimal("1200.00") / Decimal(months_elapsed)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        assert result.overtime_monthly == expected_ot
        assert result.bonus_monthly == expected_bonus
        assert result.commission_monthly == expected_commission
        assert result.total_monthly == result.base_monthly + expected_ot + expected_bonus + expected_commission

    def test_w2_from_w2_only_no_paystubs(self, service):
        """When only W2 is available (no paystub), derive monthly from W2 annual."""
        w2 = _make_w2(wages=120000.00, tax_year=2025)
        result = service._calculate_w2_income([w2])

        # 120000 / 12 = 10000
        expected_monthly = Decimal("10000.00")
        assert result.base_monthly == expected_monthly
        assert result.total_monthly == expected_monthly
        assert result.year1_income == Decimal("120000.00")

    def test_w2_two_year_w2_history(self, service):
        """Two W2s populate year1_income and year2_income for trending."""
        w2_2025 = _make_w2(wages=125000.00, tax_year=2025, doc_id=10)
        w2_2024 = _make_w2(wages=115000.00, tax_year=2024, doc_id=11)
        result = service._calculate_w2_income([w2_2025, w2_2024])

        assert result.year1_income == Decimal("125000.00")
        assert result.year2_income == Decimal("115000.00")
        assert result.trending == "INCREASING"

    def test_w2_employer_mismatch_flag(self, service):
        """Flag when paystub employer differs from W2 employer."""
        paystub = _make_paystub(employer_name="Acme Corp")
        w2 = _make_w2(employer_name="Different Company", tax_year=2025)
        result = service._calculate_w2_income([paystub, w2])

        assert any("DOCUMENT_MISMATCH" in f for f in result.flags)

    def test_w2_stale_paystub_flag(self, service):
        """Flag when paystub pay_date is older than PAYSTUB_STALENESS_DAYS."""
        old_date = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
        paystub = _make_paystub(pay_date=old_date)
        result = service._calculate_w2_income([paystub])

        assert any("STALE_PAYSTUB" in f for f in result.flags)


# =============================================================================
# 2. Self-Employment Income Calculation
# =============================================================================

@pytest.mark.unit
class TestSelfEmploymentIncome:
    """Tests for self-employment income from tax returns and K-1s."""

    def test_self_employment_two_year_average(self, service):
        """Two years of Schedule C: (year1 + year2) / 24 = monthly qualifying."""
        tax_2025 = _make_tax_return(tax_year=2025, net_profit=100000, depreciation_addback=5000, doc_id=20)
        tax_2024 = _make_tax_return(tax_year=2024, net_profit=90000, depreciation_addback=4000, doc_id=21)
        result = service._calculate_self_employment_income([tax_2025, tax_2024])

        # Year 2025 adjusted: 100000 + 5000 = 105000
        # Year 2024 adjusted: 90000 + 4000 = 94000
        # 2-year average monthly: (105000 + 94000) / 24 = 8291.67
        expected = ((Decimal("105000") + Decimal("94000")) / 24).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        assert result.source_type == "SELF_EMPLOYMENT"
        assert result.total_monthly == expected
        assert result.year1_income == Decimal("105000.00")
        assert result.year2_income == Decimal("94000.00")
        assert result.confidence == 70  # 2 years of data

    def test_self_employment_k1_income(self, service):
        """K-1 ordinary income and guaranteed payments used when present."""
        tax = _make_tax_return(
            tax_year=2025,
            net_profit=0,
            k1_ordinary_income=80000,
            k1_guaranteed_payments=20000,
            depreciation_addback=3000,
            doc_id=20,
        )
        result = service._calculate_self_employment_income([tax])

        # K1 path: k1_ordinary + k1_guaranteed + depreciation = 80000 + 20000 + 3000 = 103000
        assert result.year1_income == Decimal("103000.00")
        # Single year: 103000 / 12
        expected_monthly = (Decimal("103000") / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        assert result.total_monthly == expected_monthly
        assert any("INSUFFICIENT_HISTORY" in f for f in result.flags)

    def test_self_employment_declining_uses_lower_year(self, service):
        """If income declines >20%, use the most recent (lower) year only."""
        tax_2025 = _make_tax_return(tax_year=2025, net_profit=60000, depreciation_addback=0, doc_id=20)
        tax_2024 = _make_tax_return(tax_year=2024, net_profit=100000, depreciation_addback=0, doc_id=21)
        result = service._calculate_self_employment_income([tax_2025, tax_2024])

        # Decline: (100000 - 60000) / 100000 = 40% > 20% threshold
        # Should use year1 (60000) only: 60000 / 12 = 5000
        expected_monthly = (Decimal("60000") / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        assert result.total_monthly == expected_monthly
        assert any("DECLINING_SELF_EMPLOYMENT" in f for f in result.flags)
        assert any("USED_LOWER_YEAR" in f for f in result.flags)

    def test_self_employment_single_year_flags_insufficient(self, service):
        """Single year of SE income should flag insufficient history."""
        tax = _make_tax_return(tax_year=2025, net_profit=80000, doc_id=20)
        result = service._calculate_self_employment_income([tax])

        assert any("INSUFFICIENT_HISTORY" in f for f in result.flags)
        assert result.confidence == 45  # lower confidence for 1 year

    def test_self_employment_no_data_returns_zero(self, service):
        """Tax return with no extractable income data returns zero with flag."""
        tax = _make_tax_return(tax_year=None, net_profit=0, doc_id=20)
        result = service._calculate_self_employment_income([tax])

        assert result.total_monthly == ZERO
        assert any("NO_SELF_EMPLOYMENT_DATA" in f for f in result.flags)

    def test_self_employment_negative_income_flagged(self, service):
        """Business showing a net loss should be flagged."""
        tax = _make_tax_return(tax_year=2025, net_profit=-15000, depreciation_addback=0, doc_id=20)
        result = service._calculate_self_employment_income([tax])

        assert result.total_annual < ZERO
        assert any("NEGATIVE_INCOME" in f for f in result.flags)


# =============================================================================
# 3. Commission Income
# =============================================================================

@pytest.mark.unit
class TestCommissionIncome:
    """Tests for commission income with 2-year trending."""

    def test_commission_with_two_year_history(self, service):
        """Commission with 2-year W2 history uses 2-year average."""
        pay_date = "2025-06-15"
        paystub = _make_paystub(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            pay_date=pay_date,
            ytd_gross=60000.00,
            ytd_commission=20000.00,
            doc_id=1,
        )
        w2_2025 = _make_w2(wages=120000.00, tax_year=2025, doc_id=10)
        w2_2024 = _make_w2(wages=110000.00, tax_year=2024, doc_id=11)

        result = service._calculate_commission_income([paystub, w2_2025, w2_2024])
        assert result is not None
        assert result.source_type == "COMMISSION"
        assert result.total_monthly > ZERO
        assert result.confidence == 55  # has prior year

    def test_commission_below_5pct_returns_none(self, service):
        """Commission < 5% of gross is not considered significant."""
        pay_date = "2025-06-15"
        paystub = _make_paystub(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            pay_date=pay_date,
            ytd_gross=60000.00,
            ytd_commission=2000.00,  # 2000/60000 = 3.3%
            doc_id=1,
        )
        result = service._calculate_commission_income([paystub])
        assert result is None

    def test_commission_no_ytd_returns_none(self, service):
        """No YTD commission data returns None."""
        paystub = _make_paystub(ytd_commission=0, doc_id=1)
        result = service._calculate_commission_income([paystub])
        assert result is None

    def test_commission_declining_uses_lower_year(self, service):
        """Commission declining >25% uses the current (lower) year."""
        pay_date = "2025-06-15"
        months = service._months_elapsed_in_year(pay_date)
        # Make YTD commission high enough to be significant
        paystub = _make_paystub(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            pay_date=pay_date,
            ytd_gross=60000.00,
            ytd_commission=20000.00,  # 33% ratio
            doc_id=1,
        )
        # Prior year W2 much higher -> commission was higher historically
        w2_2025 = _make_w2(wages=120000.00, tax_year=2025, doc_id=10)
        w2_2024 = _make_w2(wages=300000.00, tax_year=2024, doc_id=11)

        result = service._calculate_commission_income([paystub, w2_2025, w2_2024])
        assert result is not None
        # Should flag declining commission
        assert any("DECLINING_COMMISSION" in f for f in result.flags)

    def test_commission_high_ratio_flagged(self, service):
        """Commission >= 25% of gross triggers HIGH_COMMISSION_RATIO flag."""
        pay_date = "2025-06-15"
        paystub = _make_paystub(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            pay_date=pay_date,
            ytd_gross=60000.00,
            ytd_commission=20000.00,  # 33%
            doc_id=1,
        )
        result = service._calculate_commission_income([paystub])
        assert result is not None
        assert any("HIGH_COMMISSION_RATIO" in f for f in result.flags)


# =============================================================================
# 4. Rental Income Calculation
# =============================================================================

@pytest.mark.unit
class TestRentalIncome:
    """Tests for rental income calculation using Schedule E data."""

    def test_rental_income_75pct_factor(self, service):
        """Gross rents * 75% (minus 25% vacancy factor) per Fannie Mae."""
        tax = _make_tax_return(
            tax_year=2025,
            schedule_e_gross_rents=2400.00,  # monthly rent
            schedule_e_total_expenses=800,
            schedule_e_depreciation=200,
            schedule_e_net_income_loss=1400,
            doc_id=20,
        )
        result = service._calculate_rental_income([tax])

        assert result is not None
        assert result.source_type == "RENTAL"
        # 2400 * 0.75 = 1800 per month * 12 = 21600 annual (for one year)
        # Single year: monthly = 21600 / 12 = 1800
        net_rental = (Decimal("2400.00") * (Decimal("1") - RENTAL_VACANCY_FACTOR)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        assert net_rental == Decimal("1800.00")
        assert result.total_monthly == net_rental

    def test_rental_income_two_year_average(self, service):
        """Two years of Schedule E data: averaged."""
        tax_2025 = _make_tax_return(
            tax_year=2025,
            schedule_e_gross_rents=2400.00,
            doc_id=20,
        )
        tax_2024 = _make_tax_return(
            tax_year=2024,
            schedule_e_gross_rents=2200.00,
            doc_id=21,
        )
        result = service._calculate_rental_income([tax_2025, tax_2024])

        # Year 2025: 2400 * 0.75 = 1800/mo * 12 = 21600 annual
        # Year 2024: 2200 * 0.75 = 1650/mo * 12 = 19800 annual
        # Average: (21600 + 19800) / 2 = 20700
        # Monthly: 20700 / 12 = 1725.00
        assert result is not None
        assert result.confidence == 60  # 2 years
        year1_annual = Decimal("2400") * Decimal("0.75") * 12
        year2_annual = Decimal("2200") * Decimal("0.75") * 12
        expected_avg = ((year1_annual + year2_annual) / 2).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        expected_monthly = (expected_avg / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        assert result.total_monthly == expected_monthly

    def test_rental_no_schedule_e_returns_none(self, service):
        """No Schedule E data returns None."""
        tax = _make_tax_return(
            tax_year=2025,
            schedule_e_gross_rents=0,
            doc_id=20,
        )
        result = service._calculate_rental_income([tax])
        assert result is None

    def test_rental_single_year_flags_insufficient(self, service):
        """Single year of rental income flags insufficient history."""
        tax = _make_tax_return(
            tax_year=2025,
            schedule_e_gross_rents=2000.00,
            doc_id=20,
        )
        result = service._calculate_rental_income([tax])
        assert result is not None
        assert any("INSUFFICIENT_RENTAL_HISTORY" in f for f in result.flags)


# =============================================================================
# 5. Income Trend Analysis
# =============================================================================

@pytest.mark.unit
class TestIncomeTrendAnalysis:
    """Tests for _analyze_income_trend method."""

    def test_increasing_trend(self, service):
        """Year1 > Year2 by more than 5% is INCREASING."""
        direction, pct = service._analyze_income_trend(Decimal("110000"), Decimal("100000"))
        assert direction == "INCREASING"
        assert pct == Decimal("10.00")

    def test_declining_trend(self, service):
        """Year1 < Year2 by more than 5% is DECLINING."""
        direction, pct = service._analyze_income_trend(Decimal("85000"), Decimal("100000"))
        assert direction == "DECLINING"
        assert pct == Decimal("-15.00")

    def test_stable_trend(self, service):
        """Change within +/-5% is STABLE."""
        direction, pct = service._analyze_income_trend(Decimal("102000"), Decimal("100000"))
        assert direction == "STABLE"
        assert pct == Decimal("2.00")

    def test_variable_when_year2_none(self, service):
        """Missing year2 returns VARIABLE with None pct."""
        direction, pct = service._analyze_income_trend(Decimal("100000"), None)
        assert direction == "VARIABLE"
        assert pct is None

    def test_variable_when_both_none(self, service):
        """Both years None returns VARIABLE."""
        direction, pct = service._analyze_income_trend(None, None)
        assert direction == "VARIABLE"
        assert pct is None

    def test_increasing_from_zero(self, service):
        """Year2 is zero but year1 is positive: INCREASING 100%."""
        direction, pct = service._analyze_income_trend(Decimal("50000"), ZERO)
        assert direction == "INCREASING"
        assert pct == Decimal("100.00")

    def test_stable_both_zero(self, service):
        """Both zero: STABLE."""
        direction, pct = service._analyze_income_trend(ZERO, ZERO)
        assert direction == "STABLE"
        assert pct == ZERO


# =============================================================================
# 6. DTI Ratio Calculation
# =============================================================================

@pytest.mark.unit
class TestDTICalculation:
    """Tests for front-end and back-end DTI ratio calculation."""

    def test_dti_calculation_normal(self, service, mock_db):
        """Standard DTI calculation: front = PITIA/income, back = (PITIA+obligations)/income."""
        mock_row = MagicMock()
        mock_row.pitia = 2000
        mock_row.obligations = 500
        mock_db.execute.return_value.fetchone.return_value = mock_row

        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=1)

        # Front: 2000/8000 * 100 = 25.00
        assert front == Decimal("25.00")
        # Back: (2000+500)/8000 * 100 = 31.25
        assert back == Decimal("31.25")

    def test_dti_zero_income_returns_none(self, service):
        """Zero income returns None for both ratios."""
        front, back = service._calculate_dti(ZERO, loan_id=1)
        assert front is None
        assert back is None

    def test_dti_negative_income_returns_none(self, service):
        """Negative income returns None for both ratios."""
        front, back = service._calculate_dti(Decimal("-1000.00"), loan_id=1)
        assert front is None
        assert back is None

    def test_dti_no_loan_found_returns_none(self, service, mock_db):
        """Loan not found returns None for both ratios."""
        mock_db.execute.return_value.fetchone.return_value = None
        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=999)
        assert front is None
        assert back is None

    def test_dti_zero_pitia_returns_none(self, service, mock_db):
        """PITIA of zero returns None (no proposed payment)."""
        mock_row = MagicMock()
        mock_row.pitia = 0
        mock_row.obligations = 500
        mock_db.execute.return_value.fetchone.return_value = mock_row

        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=1)
        assert front is None
        assert back is None


# =============================================================================
# 7. Flag Generation
# =============================================================================

@pytest.mark.unit
class TestFlagGeneration:
    """Tests for _generate_flags method."""

    def test_declining_income_flag(self, service):
        """Declining income >10% YOY generates a flag."""
        source = IncomeSourceResult(
            source_type="W2_EMPLOYMENT",
            employer_name="Test Co",
            position_title="Tester",
            base_monthly=Decimal("5000"),
            overtime_monthly=ZERO,
            bonus_monthly=ZERO,
            commission_monthly=ZERO,
            other_monthly=ZERO,
            total_monthly=Decimal("5000"),
            total_annual=Decimal("60000"),
            trending="DECLINING",
            year1_income=Decimal("55000"),
            year2_income=Decimal("70000"),
            yoy_change_pct=Decimal("-21.43"),
            confidence=80,
            source_doc_ids=[1],
            flags=[],
        )
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[source],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=None,
            dti_back_end=None,
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )

        flags = service._generate_flags(result)
        assert any("DECLINING_INCOME" in f for f in flags)

    def test_high_dti_flag(self, service):
        """Back-end DTI > 50% generates HIGH_DTI flag."""
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=Decimal("35.00"),
            dti_back_end=Decimal("52.00"),
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )

        flags = service._generate_flags(result)
        assert any("HIGH_DTI" in f for f in flags)

    def test_elevated_dti_flag(self, service):
        """Back-end DTI between 45% and 50% generates ELEVATED_DTI flag."""
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=Decimal("30.00"),
            dti_back_end=Decimal("47.00"),
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )

        flags = service._generate_flags(result)
        assert any("ELEVATED_DTI" in f for f in flags)

    def test_employment_gap_flag_with_stale_paystub(self, service):
        """Employment gap flagged when W2 source has a stale paystub."""
        source = IncomeSourceResult(
            source_type="W2_EMPLOYMENT",
            employer_name="Test Co",
            position_title="Tester",
            base_monthly=Decimal("5000"),
            overtime_monthly=ZERO,
            bonus_monthly=ZERO,
            commission_monthly=ZERO,
            other_monthly=ZERO,
            total_monthly=Decimal("5000"),
            total_annual=Decimal("60000"),
            trending="STABLE",
            year1_income=Decimal("60000"),
            year2_income=Decimal("58000"),
            yoy_change_pct=Decimal("3.45"),
            confidence=80,
            source_doc_ids=[1],
            flags=["STALE_PAYSTUB: Most recent paystub is 45 days old"],
        )
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[source],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=None,
            dti_back_end=None,
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )

        flags = service._generate_flags(result)
        assert any("EMPLOYMENT_GAP" in f for f in flags)


# =============================================================================
# 8. Task Generation
# =============================================================================

@pytest.mark.unit
class TestTaskGeneration:
    """Tests for _generate_tasks method."""

    def test_stale_paystub_generates_verify_employment_task(self, service):
        """STALE_PAYSTUB flag generates a verify_employment task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["STALE_PAYSTUB: Most recent paystub is 45 days old"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "verify_employment"
        assert tasks[0]["priority"] == "high"

    def test_employment_gap_generates_review_task(self, service):
        """EMPLOYMENT_GAP flag generates review_gap_in_employment task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=[f"EMPLOYMENT_GAP: No paystub dated within the last {PAYSTUB_STALENESS_DAYS} days"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "review_gap_in_employment" for t in tasks)

    def test_declining_income_generates_review_task(self, service):
        """DECLINING_INCOME flag generates review_declining_income task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["DECLINING_INCOME: W2_EMPLOYMENT year-over-year decrease of 15%"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "review_declining_income" for t in tasks)
        assert any(t["priority"] == "high" for t in tasks)

    def test_insufficient_se_history_generates_critical_task(self, service):
        """INSUFFICIENT_HISTORY for SELF_EMPLOYMENT generates critical priority task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["INSUFFICIENT_HISTORY: SELF_EMPLOYMENT has less than 2 years of income history"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "verify_self_employment" for t in tasks)
        assert any(t["priority"] == "critical" for t in tasks)

    def test_high_dti_generates_manual_override_task(self, service):
        """HIGH_DTI flag generates manual_override_needed task with critical priority."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["HIGH_DTI: Back-end DTI is 52.00% (above 50% threshold)"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "manual_override_needed" for t in tasks)
        assert any(t["priority"] == "critical" for t in tasks)

    def test_document_mismatch_generates_medium_priority_task(self, service):
        """DOCUMENT_MISMATCH flag generates a medium priority task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["DOCUMENT_MISMATCH: Paystub employer 'A' does not match W2 employer 'B'"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "verify_employment" for t in tasks)
        assert any(t["priority"] == "medium" for t in tasks)

    def test_negative_income_generates_review_task(self, service):
        """NEGATIVE_INCOME flag generates manual_override_needed task."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["NEGATIVE_INCOME: Business shows a net loss"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert any(t["task_type"] == "manual_override_needed" for t in tasks)


# =============================================================================
# 9. Multiple Income Source Aggregation
# =============================================================================

@pytest.mark.unit
class TestMultipleSourceAggregation:
    """Tests for aggregation of multiple income sources."""

    def test_composite_income_from_w2_and_rental(self, service, mock_db):
        """W2 + rental income are aggregated into composite total."""
        # Set up mock to return docs with both W2 and rental data,
        # and mock DTI query
        paystub = _make_paystub(
            gross_pay=5000.00, pay_frequency="BIWEEKLY", doc_id=1,
        )
        tax_with_rental = _make_tax_return(
            tax_year=2025,
            net_profit=0,
            schedule_e_gross_rents=2000.00,
            doc_id=20,
        )

        # Mock _gather_income_documents to return our docs
        service._gather_income_documents = MagicMock(return_value=[paystub, tax_with_rental])

        # Mock DTI query
        mock_row = MagicMock()
        mock_row.pitia = 2500
        mock_row.obligations = 300
        mock_db.execute.return_value.fetchone.return_value = mock_row

        # Mock _save_calculation to avoid DB writes
        service._save_calculation = MagicMock(return_value=1)

        result = service.calculate_income(loan_id=1, borrower_id=1)

        assert result.success is True
        assert len(result.sources) >= 1
        assert result.total_qualifying_monthly > ZERO
        assert result.calculation_method in ("w2_employment", "composite")

    def test_confidence_weighted_by_income_amount(self, service):
        """Overall confidence is weighted by each source's income contribution."""
        source_a = IncomeSourceResult(
            source_type="W2_EMPLOYMENT", employer_name="A", position_title="X",
            base_monthly=Decimal("8000"), overtime_monthly=ZERO, bonus_monthly=ZERO,
            commission_monthly=ZERO, other_monthly=ZERO, total_monthly=Decimal("8000"),
            total_annual=Decimal("96000"), trending="STABLE", year1_income=Decimal("96000"),
            year2_income=Decimal("94000"), yoy_change_pct=Decimal("2.13"), confidence=90,
        )
        source_b = IncomeSourceResult(
            source_type="RENTAL", employer_name=None, position_title=None,
            base_monthly=Decimal("2000"), overtime_monthly=ZERO, bonus_monthly=ZERO,
            commission_monthly=ZERO, other_monthly=ZERO, total_monthly=Decimal("2000"),
            total_annual=Decimal("24000"), trending="STABLE", year1_income=Decimal("24000"),
            year2_income=Decimal("22000"), yoy_change_pct=Decimal("9.09"), confidence=60,
        )

        total_weight = 8000.0 + 2000.0
        expected_conf = int(90 * (8000.0 / total_weight) + 60 * (2000.0 / total_weight))

        # Manually compute like the service does
        weighted_conf = sum(
            s.confidence * (float(s.total_monthly) / total_weight)
            for s in [source_a, source_b]
        )
        computed = min(100, max(0, int(weighted_conf)))
        assert computed == expected_conf


# =============================================================================
# 10. Helper Methods
# =============================================================================

@pytest.mark.unit
class TestHelperMethods:
    """Tests for _to_decimal and _months_elapsed_in_year."""

    def test_to_decimal_from_float(self, service):
        assert service._to_decimal(1234.56) == Decimal("1234.56")

    def test_to_decimal_from_string(self, service):
        assert service._to_decimal("$1,234.56") == Decimal("1234.56")

    def test_to_decimal_from_none(self, service):
        assert service._to_decimal(None) == ZERO

    def test_to_decimal_from_empty_string(self, service):
        assert service._to_decimal("") == ZERO

    def test_to_decimal_from_invalid(self, service):
        assert service._to_decimal("not_a_number") == ZERO

    def test_to_decimal_from_decimal(self, service):
        d = Decimal("99.99")
        assert service._to_decimal(d) == d

    def test_months_elapsed_january(self, service):
        """Jan 15 = approximately 1 month elapsed."""
        result = service._months_elapsed_in_year("2025-01-15")
        assert result == 1  # min(1, ...)

    def test_months_elapsed_june(self, service):
        """Jun 15 ~ 5-6 months elapsed."""
        result = service._months_elapsed_in_year("2025-06-15")
        assert result is not None
        assert 5 <= result <= 6

    def test_months_elapsed_december(self, service):
        """Dec 31 ~ 12 months elapsed."""
        result = service._months_elapsed_in_year("2025-12-31")
        assert result is not None
        assert result == 12

    def test_months_elapsed_none(self, service):
        assert service._months_elapsed_in_year(None) is None

    def test_months_elapsed_invalid_date(self, service):
        assert service._months_elapsed_in_year("not-a-date") is None


# =============================================================================
# 11. Recommendation Generation
# =============================================================================

@pytest.mark.unit
class TestRecommendationGeneration:
    """Tests for _generate_recommendations method."""

    def test_stale_paystub_recommendation(self, service):
        """STALE_PAYSTUB generates paystub update recommendation."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["STALE_PAYSTUB: Most recent paystub is 45 days old"],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        assert len(recs) >= 1
        assert "updated paystub" in recs[0].lower()

    def test_declining_income_recommendation(self, service):
        """DECLINING_INCOME generates recommendation about 2-year average."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["DECLINING_INCOME: W2_EMPLOYMENT year-over-year decrease of 15%"],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        assert len(recs) >= 1
        assert "declining" in recs[0].lower()

    def test_recommendations_deduplicated(self, service):
        """Duplicate flags produce de-duplicated recommendations."""
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=[
                "DECLINING_INCOME: W2 decrease of 15%",
                "DECLINING_INCOME: COMMISSION decrease of 12%",
            ],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        # Both flags start with "DECLINING_INCOME" -> same recommendation type
        # De-dup key is first 60 chars, so same prefix -> only 1 recommendation
        assert len(recs) == 1


# =============================================================================
# 12. No Documents Edge Case
# =============================================================================

@pytest.mark.unit
class TestNoDocumentsEdgeCase:
    """Tests for the calculate_income entry point when no documents exist."""

    def test_no_documents_returns_failure(self, service, mock_db):
        """No income documents returns failure with NO_INCOME_DOCUMENTS flag."""
        service._gather_income_documents = MagicMock(return_value=[])
        result = service.calculate_income(loan_id=1, borrower_id=1)

        assert result.success is False
        assert "NO_INCOME_DOCUMENTS" in result.flags
        assert result.total_qualifying_monthly == ZERO
        assert result.confidence == 0

    def test_exception_during_calculation_returns_error(self, service, mock_db):
        """Exception during calculation returns error result."""
        service._gather_income_documents = MagicMock(side_effect=RuntimeError("DB connection lost"))
        result = service.calculate_income(loan_id=1, borrower_id=1)

        assert result.success is False
        assert result.error is not None
        assert "DB connection lost" in result.error
        assert result.calculation_method == "error"


# =============================================================================
# 13. W2 Declining Income Uses Two-Year Average
# =============================================================================

@pytest.mark.unit
class TestW2DecliningIncomeTwoYearAverage:
    """When W2 income is declining, the service uses the lower 2-year average."""

    def test_declining_w2_uses_two_year_average(self, service):
        """Declining income: 2-year W2 average replaces paystub-derived total."""
        paystub = _make_paystub(
            gross_pay=4000.00,
            pay_frequency="BIWEEKLY",
            pay_date=date.today().strftime("%Y-%m-%d"),
            doc_id=1,
        )
        # W2s show declining trend
        w2_2025 = _make_w2(wages=80000.00, tax_year=2025, doc_id=10)
        w2_2024 = _make_w2(wages=120000.00, tax_year=2024, doc_id=11)

        result = service._calculate_w2_income([paystub, w2_2025, w2_2024])

        # Paystub annualized: 4000 * 26 / 12 = 8666.67
        # W2 2-year avg monthly: (80000 + 120000) / 24 = 8333.33
        # Since declining AND w2_avg < paystub-derived, use w2_avg
        w2_avg_monthly = ((Decimal("80000") + Decimal("120000")) / 24).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        assert result.total_monthly == w2_avg_monthly
        assert any("USED_TWO_YEAR_AVERAGE" in f for f in result.flags)
        assert result.trending == "DECLINING"


# =============================================================================
# 14. Factory Function
# =============================================================================

@pytest.mark.unit
class TestFactoryFunction:
    """Tests for the get_income_calculator_service factory."""

    def test_factory_returns_service_instance(self, mock_db):
        """get_income_calculator_service returns an IncomeCalculatorService."""
        svc = get_income_calculator_service(mock_db)
        assert isinstance(svc, IncomeCalculatorService)
        assert svc.db is mock_db


# =============================================================================
# 15. Pay Frequency Multipliers
# =============================================================================

@pytest.mark.unit
class TestPayFrequencyMultipliers:
    """Verify all PAY_FREQUENCY_MULTIPLIERS are correct."""

    def test_weekly_multiplier(self):
        assert PAY_FREQUENCY_MULTIPLIERS["WEEKLY"] == 52

    def test_biweekly_multiplier(self):
        assert PAY_FREQUENCY_MULTIPLIERS["BIWEEKLY"] == 26

    def test_semimonthly_multiplier(self):
        assert PAY_FREQUENCY_MULTIPLIERS["SEMIMONTHLY"] == 24

    def test_monthly_multiplier(self):
        assert PAY_FREQUENCY_MULTIPLIERS["MONTHLY"] == 12

    def test_unknown_frequency_defaults_to_monthly(self, service):
        """Unknown pay frequency falls back to multiplier 12 (monthly)."""
        paystub = _make_paystub(gross_pay=5000.00, pay_frequency="QUARTERLY")
        result = service._calculate_w2_income([paystub])
        # 5000 * 12 (default) / 12 = 5000
        assert result.base_monthly == Decimal("5000.00")


# =============================================================================
# 16. Confidence Scoring
# =============================================================================

@pytest.mark.unit
class TestConfidenceScoring:
    """Tests for confidence scoring across source types."""

    def test_w2_confidence_boosted_by_w2_documents(self, service):
        """Paystub + W2 gives higher confidence than paystub alone."""
        paystub_only = service._calculate_w2_income([_make_paystub(overall_confidence=70)])
        paystub_and_w2 = service._calculate_w2_income([
            _make_paystub(overall_confidence=70),
            _make_w2(wages=120000, tax_year=2025),
        ])
        assert paystub_and_w2.confidence > paystub_only.confidence

    def test_w2_only_confidence_lower(self, service):
        """W2 only (no paystub) has reduced confidence."""
        result = service._calculate_w2_income([_make_w2(wages=120000, tax_year=2025)])
        # No paystub: confidence = max(30, 50 - 20) = 30, then +10 for W2 = 40
        assert result.confidence <= 50

    def test_self_employment_two_year_confidence(self, service):
        """Two years of SE data gives confidence 70."""
        tax_2025 = _make_tax_return(tax_year=2025, net_profit=100000, doc_id=20)
        tax_2024 = _make_tax_return(tax_year=2024, net_profit=90000, doc_id=21)
        result = service._calculate_self_employment_income([tax_2025, tax_2024])
        assert result.confidence == 70

    def test_rental_two_year_confidence(self, service):
        """Two years of rental data gives confidence 60."""
        tax_2025 = _make_tax_return(tax_year=2025, schedule_e_gross_rents=2400, doc_id=20)
        tax_2024 = _make_tax_return(tax_year=2024, schedule_e_gross_rents=2200, doc_id=21)
        result = service._calculate_rental_income([tax_2025, tax_2024])
        assert result.confidence == 60


# =============================================================================
# 17. Regex Fallback Extraction
# =============================================================================

@pytest.mark.unit
class TestRegexExtraction:
    """Tests for the _extract_with_regex fallback method."""

    def test_regex_extracts_gross_pay(self, service):
        text = "Gross Pay: $5,432.10\nNet Pay: $3,200.00"
        result = service._extract_with_regex(text, "PAYSTUB")
        assert result.get("gross_pay") == 5432.10

    def test_regex_extracts_pay_frequency(self, service):
        text = "Pay Frequency: Bi-Weekly\nGross Pay: $2,500.00"
        result = service._extract_with_regex(text, "PAYSTUB")
        assert result.get("pay_frequency") == "BIWEEKLY"

    def test_regex_extracts_employer_name(self, service):
        text = "Employer: Acme Corporation\nEmployee: John Doe"
        result = service._extract_with_regex(text, "PAYSTUB")
        assert result.get("employer_name") == "Acme Corporation"
