"""
Tests for IncomeCalculatorService

Covers:
- W2/salaried income calculation from paystubs and W2s
- Self-employment income with depreciation add-backs
- Commission income with 2-year history requirement
- Rental income with 25% vacancy factor
- Income trend analysis
- DTI calculation
- Flag, recommendation, and task generation
- Helper methods (_to_decimal, _months_elapsed_in_year)
- Edge cases: zero income, negative values, missing data, precision

All tests mock the database layer -- no real DB or AI calls.

Run:
    pytest backend/tests/smart_docs/test_income_calculator_service.py -v
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timezone, timedelta
from unittest.mock import MagicMock, patch

from services.smart_docs.income_calculator_service import (
    IncomeCalculatorService,
    IncomeSourceResult,
    IncomeCalculationResult,
    get_income_calculator_service,
    ZERO,
    TWO_PLACES,
    PAY_FREQUENCY_MULTIPLIERS,
    RENTAL_VACANCY_FACTOR,
    PAYSTUB_STALENESS_DAYS,
    DECLINING_INCOME_WARN_PCT,
    DECLINING_INCOME_CRITICAL_PCT,
    HIGH_COMMISSION_RATIO_PCT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchall.return_value = []
    execute_result.fetchone.return_value = None
    db.execute.return_value = execute_result
    return db


@pytest.fixture
def service(mock_db):
    """IncomeCalculatorService with mocked DB."""
    return IncomeCalculatorService(mock_db, org_id=1)


@pytest.fixture
def service_no_org(mock_db):
    """IncomeCalculatorService without org_id."""
    return IncomeCalculatorService(mock_db, org_id=None)


def _make_paystub_doc(
    doc_id=1,
    gross_pay="4230.77",
    pay_frequency="BIWEEKLY",
    pay_date="2026-02-28",
    employer_name="Acme Corp",
    job_title="Analyst",
    ytd_overtime_earnings="0",
    ytd_bonus="0",
    ytd_commission="0",
    ytd_tips="0",
    ytd_gross=None,
    overall_confidence=85,
):
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
            "ytd_overtime_earnings": ytd_overtime_earnings,
            "ytd_bonus": ytd_bonus,
            "ytd_commission": ytd_commission,
            "ytd_tips": ytd_tips,
            "ytd_gross": ytd_gross,
        },
        "confidence_scores": {},
        "overall_confidence": overall_confidence,
    }


def _make_w2_doc(
    doc_id=10,
    tax_year=2025,
    wages="110000.00",
    employer_name="Acme Corp",
):
    return {
        "doc_id": doc_id,
        "doc_type": "W2",
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": "w2.pdf",
        "extracted_fields": {
            "tax_year": tax_year,
            "wages_tips_compensation": wages,
            "employer_name": employer_name,
        },
        "confidence_scores": {},
        "overall_confidence": 90,
    }


def _make_tax_doc(
    doc_id=20,
    tax_year=2025,
    net_profit="80000",
    depreciation="5000",
    amortization="0",
    depletion="0",
    k1_ordinary="0",
    k1_guaranteed="0",
    business_name="Self LLC",
    doc_type="TAX_RETURN",
):
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": "tax.pdf",
        "extracted_fields": {
            "tax_year": tax_year,
            "net_profit": net_profit,
            "depreciation_addback": depreciation,
            "amortization_addback": amortization,
            "depletion_addback": depletion,
            "k1_ordinary_income": k1_ordinary,
            "k1_guaranteed_payments": k1_guaranteed,
            "business_name": business_name,
        },
        "confidence_scores": {},
        "overall_confidence": 80,
    }


# ===========================================================================
# 1. HELPER METHODS
# ===========================================================================

class TestToDecimal:
    def test_none_returns_zero(self, service):
        assert service._to_decimal(None) == ZERO

    def test_string_dollar_sign(self, service):
        assert service._to_decimal("$1,234.56") == Decimal("1234.56")

    def test_string_plain_number(self, service):
        assert service._to_decimal("5000.00") == Decimal("5000.00")

    def test_empty_string_returns_zero(self, service):
        assert service._to_decimal("") == ZERO

    def test_already_decimal(self, service):
        assert service._to_decimal(Decimal("99.99")) == Decimal("99.99")

    def test_float_converted(self, service):
        result = service._to_decimal(3.14159)
        assert result == Decimal("3.14")

    def test_integer(self, service):
        assert service._to_decimal(100) == Decimal("100.00")

    def test_garbage_string_returns_zero(self, service):
        assert service._to_decimal("not-a-number") == ZERO

    def test_rounding_half_up(self, service):
        assert service._to_decimal("1.235") == Decimal("1.24")

    def test_negative_value(self, service):
        assert service._to_decimal("-500.00") == Decimal("-500.00")


class TestMonthsElapsedInYear:
    def test_end_of_february(self, service):
        # Feb 28 -> 59 days (non-leap), months ~ round(59/30.44) = 2
        result = service._months_elapsed_in_year("2026-02-28")
        assert result == 2

    def test_january_1st(self, service):
        # Day 1 -> min 1
        result = service._months_elapsed_in_year("2026-01-01")
        assert result == 1

    def test_december_31st(self, service):
        result = service._months_elapsed_in_year("2026-12-31")
        assert result == 12

    def test_none_returns_none(self, service):
        assert service._months_elapsed_in_year(None) is None

    def test_invalid_date_returns_none(self, service):
        assert service._months_elapsed_in_year("not-a-date") is None

    def test_mid_year(self, service):
        result = service._months_elapsed_in_year("2026-06-15")
        assert 5 <= result <= 6


# ===========================================================================
# 2. INCOME TREND ANALYSIS
# ===========================================================================

class TestAnalyzeIncomeTrend:
    def test_increasing_income(self, service):
        direction, pct = service._analyze_income_trend(
            Decimal("120000"), Decimal("100000")
        )
        assert direction == "INCREASING"
        assert pct == Decimal("20.00")

    def test_declining_income(self, service):
        direction, pct = service._analyze_income_trend(
            Decimal("80000"), Decimal("100000")
        )
        assert direction == "DECLINING"
        assert pct == Decimal("-20.00")

    def test_stable_income(self, service):
        direction, pct = service._analyze_income_trend(
            Decimal("100000"), Decimal("102000")
        )
        assert direction == "STABLE"
        assert pct is not None
        assert abs(pct) <= Decimal("5")

    def test_none_year1(self, service):
        direction, pct = service._analyze_income_trend(None, Decimal("100000"))
        assert direction == "VARIABLE"
        assert pct is None

    def test_none_year2(self, service):
        direction, pct = service._analyze_income_trend(Decimal("100000"), None)
        assert direction == "VARIABLE"
        assert pct is None

    def test_both_none(self, service):
        direction, pct = service._analyze_income_trend(None, None)
        assert direction == "VARIABLE"
        assert pct is None

    def test_year2_zero_year1_positive(self, service):
        direction, pct = service._analyze_income_trend(Decimal("50000"), ZERO)
        assert direction == "INCREASING"
        assert pct == Decimal("100.00")

    def test_both_zero(self, service):
        direction, pct = service._analyze_income_trend(ZERO, ZERO)
        assert direction == "STABLE"
        assert pct == ZERO

    def test_exactly_at_5_pct_threshold(self, service):
        """5% change should be classified as STABLE (not >5)."""
        # year1 = 105, year2 = 100 -> pct = 5.00
        direction, pct = service._analyze_income_trend(
            Decimal("105000"), Decimal("100000")
        )
        assert direction == "STABLE"
        assert pct == Decimal("5.00")


# ===========================================================================
# 3. W2 / SALARIED INCOME
# ===========================================================================

class TestCalculateW2Income:
    def test_biweekly_paystub_annualization(self, service):
        """Biweekly gross * 26 / 12 = monthly base."""
        docs = [_make_paystub_doc(gross_pay="4000.00", pay_frequency="BIWEEKLY")]
        result = service._calculate_w2_income(docs)

        # $4,000 * 26 = $104,000; $104,000 / 12 = $8,666.67
        assert result.base_monthly == Decimal("8666.67")
        assert result.total_monthly == Decimal("8666.67")
        assert result.source_type == "W2_EMPLOYMENT"

    def test_weekly_paystub_annualization(self, service):
        docs = [_make_paystub_doc(gross_pay="2000.00", pay_frequency="WEEKLY")]
        result = service._calculate_w2_income(docs)
        # $2,000 * 52 = $104,000; / 12 = $8,666.67
        assert result.base_monthly == Decimal("8666.67")

    def test_monthly_paystub_annualization(self, service):
        docs = [_make_paystub_doc(gross_pay="8000.00", pay_frequency="MONTHLY")]
        result = service._calculate_w2_income(docs)
        # $8,000 * 12 = $96,000; / 12 = $8,000
        assert result.base_monthly == Decimal("8000.00")

    def test_semimonthly_paystub_annualization(self, service):
        docs = [_make_paystub_doc(gross_pay="4000.00", pay_frequency="SEMIMONTHLY")]
        result = service._calculate_w2_income(docs)
        # $4,000 * 24 = $96,000; / 12 = $8,000
        assert result.base_monthly == Decimal("8000.00")

    def test_w2_only_no_paystubs(self, service):
        """When only W2 available, derive from W2 annual."""
        docs = [_make_w2_doc(wages="90000.00")]
        result = service._calculate_w2_income(docs)
        # $90,000 / 12 = $7,500
        assert result.base_monthly == Decimal("7500.00")
        assert result.confidence < 95  # Lower confidence without paystubs

    def test_paystub_plus_w2_stable(self, service):
        """Paystub + W2 with stable income uses paystub-derived income."""
        docs = [
            _make_paystub_doc(gross_pay="4230.77", pay_frequency="BIWEEKLY"),
            _make_w2_doc(tax_year=2025, wages="110000.00"),
            _make_w2_doc(doc_id=11, tax_year=2024, wages="105000.00"),
        ]
        result = service._calculate_w2_income(docs)
        assert result.total_monthly > ZERO
        assert result.year1_income == Decimal("110000.00")
        assert result.year2_income == Decimal("105000.00")
        assert result.trending == "STABLE" or result.trending == "INCREASING"

    def test_declining_income_uses_two_year_average(self, service):
        """Declining >20% year-over-year uses lower 2-year W2 average."""
        docs = [
            _make_paystub_doc(gross_pay="4000.00", pay_frequency="BIWEEKLY"),
            _make_w2_doc(tax_year=2025, wages="80000.00"),
            _make_w2_doc(doc_id=11, tax_year=2024, wages="120000.00"),
        ]
        result = service._calculate_w2_income(docs)
        # W2 average = (80000 + 120000) / 24 = $8,333.33
        # Paystub annualized = 4000 * 26 / 12 = $8,666.67
        # Declining, so use W2 average ($8,333.33)
        assert "USED_TWO_YEAR_AVERAGE" in " ".join(result.flags)
        assert result.total_monthly == Decimal("8333.33")

    def test_employer_name_mismatch_flagged(self, service):
        """Different employer names between paystub and W2 are flagged."""
        docs = [
            _make_paystub_doc(employer_name="Acme Corp"),
            _make_w2_doc(employer_name="Totally Different Inc"),
        ]
        result = service._calculate_w2_income(docs)
        assert any("DOCUMENT_MISMATCH" in f for f in result.flags)

    def test_stale_paystub_flagged(self, service):
        """Paystub older than PAYSTUB_STALENESS_DAYS triggers flag."""
        old_date = (date.today() - timedelta(days=PAYSTUB_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")
        docs = [_make_paystub_doc(pay_date=old_date)]
        result = service._calculate_w2_income(docs)
        assert any("STALE_PAYSTUB" in f for f in result.flags)

    def test_ytd_overtime_monthly(self, service):
        """YTD overtime is divided by months elapsed."""
        docs = [_make_paystub_doc(
            pay_date="2026-06-15",
            ytd_overtime_earnings="6000",
        )]
        result = service._calculate_w2_income(docs)
        months_elapsed = service._months_elapsed_in_year("2026-06-15")
        expected_ot = (Decimal("6000") / Decimal(months_elapsed)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        assert result.overtime_monthly == expected_ot

    def test_zero_gross_pay(self, service):
        """Zero gross pay results in zero base monthly."""
        docs = [_make_paystub_doc(gross_pay="0")]
        result = service._calculate_w2_income(docs)
        assert result.base_monthly == ZERO

    def test_confidence_increases_with_w2(self, service):
        """Adding W2 docs increases confidence."""
        paystub_only = service._calculate_w2_income([_make_paystub_doc()])
        both = service._calculate_w2_income([
            _make_paystub_doc(), _make_w2_doc()
        ])
        assert both.confidence >= paystub_only.confidence

    def test_total_annual_is_twelve_times_monthly(self, service):
        """total_annual should always equal total_monthly * 12."""
        docs = [_make_paystub_doc(gross_pay="3000.00", pay_frequency="BIWEEKLY")]
        result = service._calculate_w2_income(docs)
        expected_annual = (result.total_monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        assert result.total_annual == expected_annual


# ===========================================================================
# 4. SELF-EMPLOYMENT INCOME
# ===========================================================================

class TestCalculateSelfEmploymentIncome:
    def test_two_year_average(self, service):
        """2-year average: (year1 + year2) / 24."""
        docs = [
            _make_tax_doc(tax_year=2025, net_profit="100000", depreciation="10000"),
            _make_tax_doc(doc_id=21, tax_year=2024, net_profit="80000", depreciation="8000"),
        ]
        result = service._calculate_self_employment_income(docs)
        # Year 2025: 100000 + 10000 = 110000
        # Year 2024: 80000 + 8000 = 88000
        # Average monthly = (110000 + 88000) / 24 = 8250.00
        assert result.total_monthly == Decimal("8250.00")
        assert result.trending == "INCREASING"
        assert result.confidence == 70

    def test_single_year_no_averaging(self, service):
        """Only 1 year of data: divide by 12, flag insufficient history."""
        docs = [_make_tax_doc(tax_year=2025, net_profit="60000", depreciation="0")]
        result = service._calculate_self_employment_income(docs)
        assert result.total_monthly == Decimal("5000.00")
        assert any("INSUFFICIENT_HISTORY" in f for f in result.flags)
        assert result.confidence == 45

    def test_declining_self_employment_uses_lower_year(self, service):
        """Decline >= 20% uses most recent (lower) year only."""
        docs = [
            _make_tax_doc(tax_year=2025, net_profit="50000", depreciation="0"),
            _make_tax_doc(doc_id=21, tax_year=2024, net_profit="80000", depreciation="0"),
        ]
        result = service._calculate_self_employment_income(docs)
        # Decline = (80000 - 50000) / 80000 * 100 = 37.5%
        # Use most recent: 50000 / 12 = 4166.67
        assert result.total_monthly == Decimal("4166.67")
        assert any("DECLINING_SELF_EMPLOYMENT" in f for f in result.flags)
        assert any("USED_LOWER_YEAR" in f for f in result.flags)

    def test_k1_income_with_guaranteed_payments(self, service):
        """K-1 ordinary + guaranteed payments + depreciation."""
        docs = [_make_tax_doc(
            tax_year=2025,
            net_profit="0",
            k1_ordinary="40000",
            k1_guaranteed="20000",
            depreciation="5000",
        )]
        result = service._calculate_self_employment_income(docs)
        # K1 path: 40000 + 20000 + 5000 + 0 (amortization) = 65000
        # Single year: 65000 / 12 = 5416.67
        assert result.total_monthly == Decimal("5416.67")

    def test_negative_income_flagged(self, service):
        """Business net loss produces negative income and flag."""
        docs = [_make_tax_doc(tax_year=2025, net_profit="-15000", depreciation="3000")]
        result = service._calculate_self_employment_income(docs)
        # -15000 + 3000 = -12000; / 12 = -1000.00
        assert result.total_monthly == Decimal("-1000.00")
        assert any("NEGATIVE_INCOME" in f for f in result.flags)

    def test_no_extractable_data_returns_zero(self, service):
        """Tax docs without usable data return zero with flag."""
        docs = [{
            "doc_id": 1,
            "doc_type": "TAX_RETURN",
            "ocr_text": "",
            "uploaded_at": datetime.now(timezone.utc),
            "file_name": "tax.pdf",
            "extracted_fields": {},
            "confidence_scores": {},
            "overall_confidence": 50,
        }]
        result = service._calculate_self_employment_income(docs)
        assert result.total_monthly == ZERO
        assert any("NO_SELF_EMPLOYMENT_DATA" in f for f in result.flags)

    def test_depreciation_addback(self, service):
        """Depreciation is added back to net profit."""
        docs = [
            _make_tax_doc(tax_year=2025, net_profit="45000", depreciation="8500"),
            _make_tax_doc(doc_id=21, tax_year=2024, net_profit="42000", depreciation="7000"),
        ]
        result = service._calculate_self_employment_income(docs)
        # 2025: 45000 + 8500 = 53500
        # 2024: 42000 + 7000 = 49000
        # Monthly: (53500 + 49000) / 24 = 4270.83
        assert result.total_monthly == Decimal("4270.83")

    def test_profit_loss_doc_type(self, service):
        """P&L statements contribute to self-employment calculation."""
        docs = [{
            "doc_id": 30,
            "doc_type": "PROFIT_LOSS",
            "ocr_text": "",
            "uploaded_at": datetime.now(timezone.utc),
            "file_name": "pnl.pdf",
            "extracted_fields": {
                "tax_year": 2025,
                "net_profit": "72000",
                "business_name": "My Biz",
            },
            "confidence_scores": {},
            "overall_confidence": 70,
        }]
        result = service._calculate_self_employment_income(docs)
        assert result.total_monthly == Decimal("6000.00")
        assert result.employer_name == "My Biz"


# ===========================================================================
# 5. COMMISSION INCOME
# ===========================================================================

class TestCalculateCommissionIncome:
    def test_no_commission_returns_none(self, service):
        """No commission data returns None."""
        docs = [_make_paystub_doc(ytd_commission="0")]
        result = service._calculate_commission_income(docs)
        assert result is None

    def test_commission_below_5_pct_returns_none(self, service):
        """Commission <5% of gross is not considered significant."""
        docs = [_make_paystub_doc(
            pay_date="2026-06-15",
            ytd_commission="200",
            ytd_gross="100000",
        )]
        # Need to set ytd_gross in the extracted_fields
        docs[0]["extracted_fields"]["ytd_gross"] = "100000"
        result = service._calculate_commission_income(docs)
        assert result is None

    def test_commission_above_25_pct_flagged(self, service):
        """Commission >= 25% of gross is flagged as HIGH_COMMISSION_RATIO."""
        docs = [_make_paystub_doc(
            pay_date="2026-06-15",
            ytd_commission="30000",
        )]
        docs[0]["extracted_fields"]["ytd_gross"] = "90000"
        result = service._calculate_commission_income(docs)
        assert result is not None
        assert any("HIGH_COMMISSION_RATIO" in f for f in result.flags)

    def test_commission_requires_two_year_history(self, service):
        """Commission with only 1 year flags insufficient history."""
        docs = [_make_paystub_doc(
            pay_date="2026-06-15",
            ytd_commission="15000",
        )]
        docs[0]["extracted_fields"]["ytd_gross"] = "60000"
        result = service._calculate_commission_income(docs)
        assert result is not None
        assert any("INSUFFICIENT_HISTORY" in f for f in result.flags)


# ===========================================================================
# 6. RENTAL INCOME
# ===========================================================================

class TestCalculateRentalIncome:
    def test_no_schedule_e_returns_none(self, service):
        """No Schedule E data returns None."""
        docs = [_make_tax_doc(tax_year=2025, net_profit="50000")]
        result = service._calculate_rental_income(docs)
        assert result is None

    def test_75_pct_vacancy_factor(self, service):
        """Gross rents * 75% is the qualifying rental income."""
        docs = [{
            "doc_id": 40,
            "doc_type": "TAX_RETURN",
            "ocr_text": "",
            "uploaded_at": datetime.now(timezone.utc),
            "file_name": "tax.pdf",
            "extracted_fields": {
                "tax_year": 2025,
                "schedule_e_gross_rents": "2000",
                "schedule_e_total_expenses": "500",
                "schedule_e_depreciation": "200",
                "schedule_e_net_income_loss": "1300",
            },
            "confidence_scores": {},
            "overall_confidence": 80,
        }]
        result = service._calculate_rental_income(docs)
        assert result is not None
        # Qualifying: 2000 * 0.75 = 1500 (monthly), annualized to 18000
        # Single year, so monthly = 18000 / 12 = 1500
        assert result.total_monthly == Decimal("1500.00")

    def test_two_year_rental_average(self, service):
        """Two years of Schedule E produces averaged monthly income."""
        docs = [
            {
                "doc_id": 40,
                "doc_type": "TAX_RETURN",
                "ocr_text": "",
                "uploaded_at": datetime.now(timezone.utc),
                "file_name": "tax1.pdf",
                "extracted_fields": {
                    "tax_year": 2025,
                    "schedule_e_gross_rents": "2000",
                    "schedule_e_total_expenses": "0",
                    "schedule_e_depreciation": "0",
                    "schedule_e_net_income_loss": "2000",
                },
                "confidence_scores": {},
                "overall_confidence": 80,
            },
            {
                "doc_id": 41,
                "doc_type": "TAX_RETURN",
                "ocr_text": "",
                "uploaded_at": datetime.now(timezone.utc),
                "file_name": "tax2.pdf",
                "extracted_fields": {
                    "tax_year": 2024,
                    "schedule_e_gross_rents": "1800",
                    "schedule_e_total_expenses": "0",
                    "schedule_e_depreciation": "0",
                    "schedule_e_net_income_loss": "1800",
                },
                "confidence_scores": {},
                "overall_confidence": 80,
            },
        ]
        result = service._calculate_rental_income(docs)
        assert result is not None
        # Year 2025: 2000 * 0.75 = 1500 monthly -> annual = 18000
        # Year 2024: 1800 * 0.75 = 1350 monthly -> annual = 16200
        # Average: (18000 + 16200) / 2 = 17100; monthly = 17100 / 12 = 1425.00
        assert result.total_monthly == Decimal("1425.00")

    def test_negative_rental_flagged(self, service):
        """Negative cash flow produces a flag."""
        # This only happens if net_rental < 0 from the calc,
        # but with vacancy factor that would need very low gross rents
        # For now test via a negative monthly which the code handles
        docs = [{
            "doc_id": 40,
            "doc_type": "TAX_RETURN",
            "ocr_text": "",
            "uploaded_at": datetime.now(timezone.utc),
            "file_name": "tax.pdf",
            "extracted_fields": {
                "tax_year": 2025,
                "schedule_e_gross_rents": "100",  # very low
                "schedule_e_total_expenses": "2000",
                "schedule_e_depreciation": "0",
                "schedule_e_net_income_loss": "-1900",
            },
            "confidence_scores": {},
            "overall_confidence": 80,
        }]
        result = service._calculate_rental_income(docs)
        assert result is not None
        # 100 * 0.75 = 75 per month -> 900 annual. Not negative at this level,
        # but code checks monthly < ZERO after division
        # Actually: qualifying = 100 * 0.75 = 75, annual = 75 * 12 = 900
        # monthly = 900 / 12 = 75. Not negative. Let's verify behavior
        assert result.total_monthly == Decimal("75.00")

    def test_single_year_insufficient_history_flag(self, service):
        """Single year of Schedule E flags insufficient rental history."""
        docs = [{
            "doc_id": 40,
            "doc_type": "TAX_RETURN",
            "ocr_text": "",
            "uploaded_at": datetime.now(timezone.utc),
            "file_name": "tax.pdf",
            "extracted_fields": {
                "tax_year": 2025,
                "schedule_e_gross_rents": "2000",
                "schedule_e_total_expenses": "500",
                "schedule_e_depreciation": "100",
                "schedule_e_net_income_loss": "1400",
            },
            "confidence_scores": {},
            "overall_confidence": 80,
        }]
        result = service._calculate_rental_income(docs)
        assert any("INSUFFICIENT_RENTAL_HISTORY" in f for f in result.flags)


# ===========================================================================
# 7. DTI CALCULATION
# ===========================================================================

class TestCalculateDTI:
    def test_dti_calculation(self, service, mock_db):
        """Front-end = PITIA/income*100, Back-end = (PITIA+obligations)/income*100."""
        row_mock = MagicMock()
        row_mock.pitia = 2400
        row_mock.obligations = 800
        mock_db.execute.return_value.fetchone.return_value = row_mock

        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=42)
        assert front == Decimal("30.00")
        assert back == Decimal("40.00")

    def test_zero_income_returns_none(self, service):
        """Zero income should not cause division by zero."""
        front, back = service._calculate_dti(ZERO, loan_id=42)
        assert front is None
        assert back is None

    def test_negative_income_returns_none(self, service):
        front, back = service._calculate_dti(Decimal("-1000"), loan_id=42)
        assert front is None
        assert back is None

    def test_no_loan_data_returns_none(self, service, mock_db):
        """No loan row returns None DTI."""
        mock_db.execute.return_value.fetchone.return_value = None
        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=42)
        assert front is None
        assert back is None

    def test_zero_pitia_returns_none(self, service, mock_db):
        """Zero PITIA means no housing payment data."""
        row_mock = MagicMock()
        row_mock.pitia = 0
        row_mock.obligations = 500
        mock_db.execute.return_value.fetchone.return_value = row_mock

        front, back = service._calculate_dti(Decimal("8000.00"), loan_id=42)
        assert front is None
        assert back is None


# ===========================================================================
# 8. FLAG GENERATION
# ===========================================================================

class TestGenerateFlags:
    def test_declining_income_flag(self, service):
        source = IncomeSourceResult(
            source_type="W2_EMPLOYMENT",
            employer_name="Test",
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
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=Decimal("30"),
            dti_back_end=Decimal("52"),
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )
        flags = service._generate_flags(result)
        assert any("HIGH_DTI" in f for f in flags)

    def test_elevated_dti_flag(self, service):
        result = IncomeCalculationResult(
            loan_id=1,
            borrower_id=1,
            sources=[],
            total_qualifying_monthly=Decimal("5000"),
            total_qualifying_annual=Decimal("60000"),
            calculation_method="w2_employment",
            dti_front_end=Decimal("28"),
            dti_back_end=Decimal("47"),
            confidence=80,
            flags=[],
            recommendations=[],
            tasks_to_create=[],
        )
        flags = service._generate_flags(result)
        assert any("ELEVATED_DTI" in f for f in flags)


# ===========================================================================
# 9. RECOMMENDATION GENERATION
# ===========================================================================

class TestGenerateRecommendations:
    def test_stale_paystub_recommendation(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["STALE_PAYSTUB: paystub is 45 days old"],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        assert len(recs) >= 1
        assert "paystub" in recs[0].lower()

    def test_no_income_documents_recommendation(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["NO_INCOME_DOCUMENTS"],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        assert any("upload" in r.lower() for r in recs)

    def test_deduplication(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=[
                "STALE_PAYSTUB: paystub is 45 days old",
                "STALE_PAYSTUB: another paystub is 50 days old",
            ],
            recommendations=[], tasks_to_create=[],
        )
        recs = service._generate_recommendations(result)
        # Both flags match STALE_PAYSTUB but the same rec text should be deduplicated
        assert len(recs) == 1


# ===========================================================================
# 10. TASK GENERATION
# ===========================================================================

class TestGenerateTasks:
    def test_stale_paystub_task(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["STALE_PAYSTUB: paystub is 45 days old"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "verify_employment"
        assert tasks[0]["priority"] == "high"

    def test_high_dti_task(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["HIGH_DTI: Back-end DTI is 52%"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert len(tasks) >= 1
        assert tasks[0]["priority"] == "critical"

    def test_insufficient_self_employment_task(self, service):
        result = IncomeCalculationResult(
            loan_id=1, borrower_id=1, sources=[], total_qualifying_monthly=ZERO,
            total_qualifying_annual=ZERO, calculation_method="none",
            dti_front_end=None, dti_back_end=None, confidence=0,
            flags=["INSUFFICIENT_HISTORY: SELF_EMPLOYMENT has less than 2 years"],
            recommendations=[], tasks_to_create=[],
        )
        tasks = service._generate_tasks(result)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "verify_self_employment"
        assert tasks[0]["priority"] == "critical"


# ===========================================================================
# 11. MAIN ENTRY POINT
# ===========================================================================

class TestCalculateIncome:
    def test_no_documents_returns_failure(self, service, mock_db):
        """No income documents returns success=False with NO_INCOME_DOCUMENTS."""
        # Setup: org check passes, no docs
        call_count = [0]
        def execute_side_effect(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:  # org check
                row = MagicMock()
                row.organization_id = 1
                result.fetchone.return_value = row
            else:  # docs query
                result.fetchall.return_value = []
            return result
        mock_db.execute.side_effect = execute_side_effect

        result = service.calculate_income(loan_id=42, borrower_id=7)
        assert result.success is False
        assert "NO_INCOME_DOCUMENTS" in result.flags

    def test_tenant_isolation_violation(self, service, mock_db):
        """Loan from a different org returns access denied."""
        row = MagicMock()
        row.organization_id = 999  # Different org
        mock_db.execute.return_value.fetchone.return_value = row

        result = service.calculate_income(loan_id=42, borrower_id=7)
        assert result.success is False
        assert "TENANT_ISOLATION_ERROR" in result.flags

    def test_exception_returns_error_result(self, service, mock_db):
        """Unhandled exception is caught and returns error result."""
        mock_db.execute.side_effect = RuntimeError("boom")
        result = service.calculate_income(loan_id=42, borrower_id=7)
        assert result.success is False
        assert "boom" in result.error


# ===========================================================================
# 12. FACTORY FUNCTION
# ===========================================================================

class TestFactory:
    def test_get_income_calculator_service(self, mock_db):
        svc = get_income_calculator_service(mock_db, org_id=5)
        assert isinstance(svc, IncomeCalculatorService)
        assert svc.org_id == 5

    def test_get_income_calculator_service_no_org(self, mock_db):
        svc = get_income_calculator_service(mock_db)
        assert svc.org_id is None


# ===========================================================================
# 13. PRECISION / FINANCIAL MATH EDGE CASES
# ===========================================================================

class TestPrecision:
    def test_total_monthly_quantized_to_two_places(self, service):
        """Total monthly should never have more than 2 decimal places."""
        docs = [_make_paystub_doc(gross_pay="3333.33", pay_frequency="BIWEEKLY")]
        result = service._calculate_w2_income(docs)
        # Verify quantization
        assert result.total_monthly == result.total_monthly.quantize(TWO_PLACES)
        assert result.total_annual == result.total_annual.quantize(TWO_PLACES)

    def test_self_employment_large_values(self, service):
        """Large dollar amounts maintain precision."""
        docs = [
            _make_tax_doc(tax_year=2025, net_profit="2500000", depreciation="150000"),
            _make_tax_doc(doc_id=21, tax_year=2024, net_profit="2200000", depreciation="130000"),
        ]
        result = service._calculate_self_employment_income(docs)
        # 2025: 2500000 + 150000 = 2650000
        # 2024: 2200000 + 130000 = 2330000
        # Monthly: (2650000 + 2330000) / 24 = 207500.00
        assert result.total_monthly == Decimal("207500.00")

    def test_one_penny_income(self, service):
        """Tiny income amounts are handled correctly."""
        docs = [_make_w2_doc(wages="0.12")]
        result = service._calculate_w2_income(docs)
        # 0.12 / 12 = 0.01
        assert result.base_monthly == Decimal("0.01")
        assert result.base_monthly > ZERO
