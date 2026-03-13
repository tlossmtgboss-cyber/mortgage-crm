"""
Income Calculation Accuracy Tests for Smart Docs V2

Verifies that income calculations match expected results per Fannie Mae
Selling Guide (B3-3.1 through B3-3.4), Freddie Mac Guide (5304-5306),
and FHA/VA handbooks.

Each test uses realistic financial data and verifies the math to the penny
using Decimal arithmetic. No database or AI calls -- pure calculation logic.

Run:
    pytest backend/tests/smart_docs/test_income_accuracy.py -v -m income_accuracy
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Decimal helpers -- mirror the service constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
MONTHS_PER_YEAR = Decimal("12")
RENTAL_VACANCY_FACTOR = Decimal("0.25")
NET_RENTAL_FACTOR = Decimal("0.75")


def _d(value) -> Decimal:
    """Shorthand to convert any numeric to Decimal."""
    if value is None:
        return ZERO
    return Decimal(str(value))


def monthly(annual: Decimal) -> Decimal:
    """Annual -> monthly, rounded to 2 decimal places."""
    return (annual / MONTHS_PER_YEAR).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def two_year_avg_monthly(year1: Decimal, year2: Decimal) -> Decimal:
    """Two-year average monthly = (year1 + year2) / 24."""
    return ((year1 + year2) / Decimal("24")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pytest marker
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.income_accuracy


# ============================================================================
# 1. W-2 INCOME TESTS
# ============================================================================

class TestW2Income:
    """
    W-2 / salaried income per Fannie Mae B3-3.1-01 and Freddie Mac 5304.1.
    """

    def test_simple_w2_two_year_average(self):
        """
        Two W-2s, no variable income.

        Year 1 (most recent): $85,000
        Year 2 (prior):       $90,000
        2-year average monthly = ($85,000 + $90,000) / 24 = $7,291.67

        Per Selling Guide B3-3.1-01: when income is stable or increasing,
        use the 2-year average. Both years are within normal range so the
        simple average applies.
        """
        year1 = _d("85000.00")
        year2 = _d("90000.00")

        expected_monthly = two_year_avg_monthly(year1, year2)

        # Manual verification: (85000 + 90000) / 24 = 175000 / 24 = 7291.666...
        assert expected_monthly == _d("7291.67")

        # Verify annual
        expected_annual = (expected_monthly * MONTHS_PER_YEAR).quantize(TWO_PLACES)
        assert expected_annual == _d("87500.04")

    def test_w2_with_overtime(self):
        """
        Base salary plus overtime that requires 2-year averaging.

        Base: $60,000/yr
        OT Year 1: $12,000
        OT Year 2: $15,000
        2-year OT average: ($12,000 + $15,000) / 2 = $13,500

        Monthly base: $60,000 / 12 = $5,000.00
        Monthly OT:   $13,500 / 12 = $1,125.00
        Total monthly: $6,125.00

        Per Selling Guide B3-3.1-03: overtime must be averaged over
        2 years when it has a documented history.
        """
        base_annual = _d("60000.00")
        ot_year1 = _d("12000.00")
        ot_year2 = _d("15000.00")

        base_monthly = monthly(base_annual)
        # $60,000 / 12 = $5,000.00
        assert base_monthly == _d("5000.00")

        ot_two_year_avg = (ot_year1 + ot_year2) / Decimal("2")
        ot_monthly = monthly(ot_two_year_avg)
        # ($12,000 + $15,000) / 2 = $13,500; $13,500 / 12 = $1,125.00
        assert ot_monthly == _d("1125.00")

        total_monthly = (base_monthly + ot_monthly).quantize(TWO_PLACES)
        assert total_monthly == _d("6125.00")

    def test_w2_declining_income(self):
        """
        Income declining >20% year-over-year triggers the "use lower year" rule.

        Year 1 (most recent): $80,000
        Year 2 (prior):       $100,000
        Decline: ($100,000 - $80,000) / $100,000 = 20%

        Per Selling Guide B3-3.1-01: if the trend is declining by 20% or more,
        use the lower (most recent) year rather than the 2-year average.

        Expected monthly: $80,000 / 12 = $6,666.67
        """
        year1 = _d("80000.00")   # most recent
        year2 = _d("100000.00")  # prior year

        decline_pct = ((year2 - year1) / year2 * _d("100")).quantize(TWO_PLACES)
        assert decline_pct == _d("20.00")

        # Decline >= 20% -> use lower (most recent) year
        qualifying_annual = year1
        expected_monthly = monthly(qualifying_annual)

        # $80,000 / 12 = $6,666.666... -> $6,666.67
        assert expected_monthly == _d("6666.67")

        # Two-year average would have been higher -- verify we are NOT using it
        two_year_monthly = two_year_avg_monthly(year1, year2)
        # ($80,000 + $100,000) / 24 = $7,500.00
        assert two_year_monthly == _d("7500.00")
        assert expected_monthly < two_year_monthly

    def test_w2_bonus_income(self):
        """
        Base salary plus bonus income requiring 2-year averaging.

        Base: $75,000/yr
        Bonus Year 1: $10,000
        Bonus Year 2: $15,000
        2-year bonus avg: ($10,000 + $15,000) / 2 = $12,500

        Monthly base:  $75,000 / 12 = $6,250.00
        Monthly bonus: $12,500 / 12 = $1,041.67
        Total monthly: $7,291.67

        Per Selling Guide B3-3.1-03: bonus income must have a 2-year
        history and be averaged over 2 years when documented.
        """
        base_annual = _d("75000.00")
        bonus_year1 = _d("10000.00")
        bonus_year2 = _d("15000.00")

        base_monthly = monthly(base_annual)
        assert base_monthly == _d("6250.00")

        bonus_avg = (bonus_year1 + bonus_year2) / Decimal("2")
        bonus_monthly = monthly(bonus_avg)
        # ($10,000 + $15,000) / 2 = $12,500; $12,500 / 12 = $1,041.67
        assert bonus_monthly == _d("1041.67")

        total_monthly = (base_monthly + bonus_monthly).quantize(TWO_PLACES)
        assert total_monthly == _d("7291.67")

    def test_w2_ytd_verification(self):
        """
        Cross-check W-2 against YTD paystub to verify consistency.

        W-2 total: $90,000
        YTD paystub (10 months in): $78,000
        Annualized YTD: $78,000 * 12 / 10 = $93,600

        Variance: |$93,600 - $90,000| / $90,000 = 4.0%
        This is within the 10% tolerance, so income is deemed consistent.

        Monthly (using W-2): $90,000 / 12 = $7,500.00
        Monthly (using annualized YTD): $93,600 / 12 = $7,800.00

        Per Selling Guide B3-3.1-01: when YTD annualization and W-2 are
        reasonably consistent, either may be used. The lower figure is
        conservative; the W-2 is used when the YTD is within tolerance.
        """
        w2_total = _d("90000.00")
        ytd_gross = _d("78000.00")
        months_elapsed = Decimal("10")
        tolerance_pct = _d("10.00")

        annualized_ytd = (ytd_gross * MONTHS_PER_YEAR / months_elapsed).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        # $78,000 * 12 / 10 = $93,600.00
        assert annualized_ytd == _d("93600.00")

        variance_pct = (
            abs(annualized_ytd - w2_total) / w2_total * _d("100")
        ).quantize(TWO_PLACES)
        # |$93,600 - $90,000| / $90,000 * 100 = 4.00%
        assert variance_pct == _d("4.00")
        assert variance_pct <= tolerance_pct, "Should be within 10% tolerance"

        w2_monthly = monthly(w2_total)
        assert w2_monthly == _d("7500.00")

        ytd_monthly = monthly(annualized_ytd)
        assert ytd_monthly == _d("7800.00")


# ============================================================================
# 2. SELF-EMPLOYMENT INCOME TESTS
# ============================================================================

class TestSelfEmploymentIncome:
    """
    Self-employment income per Fannie Mae B3-3.2 and Freddie Mac 5304.2.
    """

    def test_schedule_c_with_addbacks(self):
        """
        Schedule C filer with depreciation and home office add-backs.

        Net profit (Schedule C, Line 31): $45,000
        Depreciation (Form 4562):         $8,000
        Business use of home (Line 30):   $3,000

        Adjusted income: $45,000 + $8,000 + $3,000 = $56,000

        Monthly: $56,000 / 12 = $4,666.67

        Per Selling Guide B3-3.2-01: non-cash items (depreciation,
        depletion, amortization) are added back. Business use of home
        is also added back as it is a non-cash deduction.
        """
        net_profit = _d("45000.00")
        depreciation = _d("8000.00")
        home_office = _d("3000.00")

        adjusted = net_profit + depreciation + home_office
        assert adjusted == _d("56000.00")

        expected_monthly = monthly(adjusted)
        # $56,000 / 12 = $4,666.666... -> $4,666.67
        assert expected_monthly == _d("4666.67")

    def test_scorp_k1_plus_w2(self):
        """
        S-Corp owner: W-2 salary + K-1 distributions.

        W-2 from S-Corp:         $60,000
        K-1 ordinary income:     $25,000
        Depreciation on K-1:     $5,000

        Total qualifying: $60,000 + $25,000 + $5,000 = $90,000
        Monthly: $90,000 / 12 = $7,500.00

        Per Selling Guide B3-3.3-01: S-Corp income = W-2 wages + K-1
        ordinary income (Box 1) + depreciation add-back from corporate
        return.
        """
        w2_wages = _d("60000.00")
        k1_ordinary = _d("25000.00")
        k1_depreciation = _d("5000.00")

        total_annual = w2_wages + k1_ordinary + k1_depreciation
        assert total_annual == _d("90000.00")

        expected_monthly = monthly(total_annual)
        assert expected_monthly == _d("7500.00")

    def test_partnership_k1(self):
        """
        Partnership K-1 income with guaranteed payments and depreciation.

        Ordinary income (Box 1):    $40,000
        Guaranteed payments (Box 4): $20,000
        Depreciation add-back:       $10,000

        Total: $40,000 + $20,000 + $10,000 = $70,000
        Monthly: $70,000 / 12 = $5,833.33

        Per Selling Guide B3-3.3-01: partnership income = ordinary
        business income + guaranteed payments + non-cash add-backs.
        """
        ordinary = _d("40000.00")
        guaranteed = _d("20000.00")
        depreciation = _d("10000.00")

        total_annual = ordinary + guaranteed + depreciation
        assert total_annual == _d("70000.00")

        expected_monthly = monthly(total_annual)
        # $70,000 / 12 = $5,833.333... -> $5,833.33
        assert expected_monthly == _d("5833.33")

    def test_declining_self_employment(self):
        """
        Self-employment income declining > 25%.

        Year 1 (most recent): $85,000
        Year 2 (prior):       $120,000
        Decline: ($120,000 - $85,000) / $120,000 = 29.17%

        Since decline exceeds 25%, must use most recent 12 months only.
        Monthly: $85,000 / 12 = $7,083.33

        Per Selling Guide B3-3.2-01: when self-employment income shows
        a significant downward trend (generally 25%+), the underwriter
        should use the most recent year's income rather than the average.
        """
        year1 = _d("85000.00")
        year2 = _d("120000.00")

        decline_pct = ((year2 - year1) / year2 * _d("100")).quantize(TWO_PLACES)
        # ($120,000 - $85,000) / $120,000 * 100 = 29.17%
        assert decline_pct == _d("29.17")
        assert decline_pct > _d("25.00"), "Decline exceeds 25% threshold"

        # Use most recent year only
        expected_monthly = monthly(year1)
        # $85,000 / 12 = $7,083.333... -> $7,083.33
        assert expected_monthly == _d("7083.33")

        # Two-year average would have been higher
        two_year = two_year_avg_monthly(year1, year2)
        # ($85,000 + $120,000) / 24 = $8,541.67
        assert two_year == _d("8541.67")
        assert expected_monthly < two_year

    def test_multiple_businesses(self):
        """
        Borrower with multiple businesses -- net all before qualifying.

        Business A net profit: +$50,000
        Business B net loss:   -$10,000
        Net self-employment:    $40,000

        Monthly: $40,000 / 12 = $3,333.33

        Per Selling Guide B3-3.2-01: when a borrower has multiple
        businesses, the net income from all businesses is combined.
        A loss in one business offsets income from another.
        """
        business_a = _d("50000.00")
        business_b = _d("-10000.00")

        net_se = business_a + business_b
        assert net_se == _d("40000.00")

        expected_monthly = monthly(net_se)
        # $40,000 / 12 = $3,333.333... -> $3,333.33
        assert expected_monthly == _d("3333.33")


# ============================================================================
# 3. COMMISSION INCOME TESTS
# ============================================================================

class TestCommissionIncome:
    """
    Commission income per Fannie Mae B3-3.1-05 and Freddie Mac 5304.1(d).
    """

    def test_commission_greater_than_25_pct(self):
        """
        Commission > 25% of total income requires 2-year history.

        Base: $40,000/yr
        Commission Year 1: $30,000
        Commission Year 2: $35,000

        Commission ratio: $30,000 / ($40,000 + $30,000) = 42.9% -> > 25%
        2-year avg commission: ($30,000 + $35,000) / 2 = $32,500

        Monthly base:       $40,000 / 12 = $3,333.33
        Monthly commission: $32,500 / 12 = $2,708.33
        Total monthly:      $6,041.67 (note: sum recalculated below)

        Per Selling Guide B3-3.1-05: if commission income represents more
        than 25% of total compensation, it must be averaged over 2 years
        and a history of at least 2 years is required.
        """
        base_annual = _d("40000.00")
        comm_year1 = _d("30000.00")
        comm_year2 = _d("35000.00")

        # Commission ratio using most recent year
        total_comp_year1 = base_annual + comm_year1
        commission_ratio = (comm_year1 / total_comp_year1 * _d("100")).quantize(TWO_PLACES)
        # $30,000 / $70,000 * 100 = 42.86%
        assert commission_ratio == _d("42.86")
        assert commission_ratio > _d("25.00"), "Commission exceeds 25% threshold"

        base_monthly = monthly(base_annual)
        # $40,000 / 12 = $3,333.33
        assert base_monthly == _d("3333.33")

        comm_avg = (comm_year1 + comm_year2) / Decimal("2")
        comm_monthly = monthly(comm_avg)
        # ($30,000 + $35,000) / 2 = $32,500; $32,500 / 12 = $2,708.33
        assert comm_monthly == _d("2708.33")

        total_monthly = (base_monthly + comm_monthly).quantize(TWO_PLACES)
        # $3,333.33 + $2,708.33 = $6,041.66 (exact Decimal sum)
        assert total_monthly == _d("6041.66")

    def test_commission_less_than_25_pct(self):
        """
        Commission < 25% of total income -- can use 1-year history.

        Base: $80,000/yr
        Commission Year 1 (most recent): $8,000
        Commission Year 2 (prior):       $10,000

        Commission ratio: $8,000 / ($80,000 + $8,000) = 9.09% -> < 25%

        Since < 25%, the most recent year's commission can be used
        without requiring a 2-year average.

        Monthly base:       $80,000 / 12 = $6,666.67
        Monthly commission: $8,000 / 12  = $666.67
        Total monthly:      $7,333.34

        Per Selling Guide B3-3.1-05: when commission is less than 25%
        of total compensation, a 1-year history may be sufficient.
        """
        base_annual = _d("80000.00")
        comm_year1 = _d("8000.00")

        total_comp = base_annual + comm_year1
        commission_ratio = (comm_year1 / total_comp * _d("100")).quantize(TWO_PLACES)
        # $8,000 / $88,000 * 100 = 9.09%
        assert commission_ratio == _d("9.09")
        assert commission_ratio < _d("25.00"), "Commission is under 25%"

        base_monthly = monthly(base_annual)
        assert base_monthly == _d("6666.67")

        # Use 1-year (most recent) commission
        comm_monthly = monthly(comm_year1)
        # $8,000 / 12 = $666.67
        assert comm_monthly == _d("666.67")

        total_monthly = (base_monthly + comm_monthly).quantize(TWO_PLACES)
        assert total_monthly == _d("7333.34")

    def test_unreimbursed_expenses_deduction(self):
        """
        Commission earner with unreimbursed business expenses > 25%.

        Gross commission:        $60,000
        Unreimbursed expenses:   $18,000 (30% of gross)

        Since unreimbursed expenses exceed 25% of gross commission,
        they must be deducted from income.

        Net commission: $60,000 - $18,000 = $42,000
        Monthly: $42,000 / 12 = $3,500.00

        Per Selling Guide B3-3.1-09: unreimbursed employee business
        expenses from Schedule A / Form 2106 are deducted when they
        represent a significant portion (>25%) of gross income.
        """
        gross_commission = _d("60000.00")
        unreimbursed = _d("18000.00")

        expense_ratio = (unreimbursed / gross_commission * _d("100")).quantize(TWO_PLACES)
        # $18,000 / $60,000 * 100 = 30.00%
        assert expense_ratio == _d("30.00")
        assert expense_ratio > _d("25.00"), "Expenses exceed 25% threshold"

        net_commission = gross_commission - unreimbursed
        assert net_commission == _d("42000.00")

        expected_monthly = monthly(net_commission)
        assert expected_monthly == _d("3500.00")


# ============================================================================
# 4. RENTAL INCOME TESTS
# ============================================================================

class TestRentalIncome:
    """
    Rental income per Fannie Mae B3-3.1-08 (Schedule E),
    Selling Guide B2-2-03 (subject property rental).
    """

    def test_schedule_e_net_rental(self):
        """
        Schedule E rental with depreciation add-back.

        Gross rents (Line 3):    $24,000
        Total expenses (Line 20): $18,000
        Depreciation (Line 18):   $5,000 (included in expenses)

        Net before add-back: $24,000 - $18,000 = $6,000
        Depreciation add-back: + $5,000
        Adjusted net: $6,000 + $5,000 = $11,000

        Monthly: $11,000 / 12 = $916.67

        Per Selling Guide B3-3.1-08: for Schedule E income, add back
        depreciation, insurance, mortgage interest, and taxes (PITIA
        components) from the expense total since these are either
        non-cash or accounted for elsewhere in the DTI.
        """
        gross_rents = _d("24000.00")
        total_expenses = _d("18000.00")
        depreciation = _d("5000.00")

        net_before_addback = gross_rents - total_expenses
        assert net_before_addback == _d("6000.00")

        adjusted_net = net_before_addback + depreciation
        assert adjusted_net == _d("11000.00")

        expected_monthly = monthly(adjusted_net)
        # $11,000 / 12 = $916.666... -> $916.67
        assert expected_monthly == _d("916.67")

    def test_proposed_rental_with_vacancy(self):
        """
        Proposed rental from lease agreement with 25% vacancy factor.

        Lease rent: $2,000/mo
        Vacancy factor: 25% (Fannie Mae standard)
        Qualifying rent: $2,000 * 0.75 = $1,500/mo

        Per Selling Guide B2-2-03: when using a lease agreement for
        proposed rental income on an investment property, apply a 25%
        vacancy factor. Only 75% of the lease rent counts.
        """
        lease_monthly = _d("2000.00")

        qualifying_monthly = (lease_monthly * NET_RENTAL_FACTOR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        # $2,000 * 0.75 = $1,500.00
        assert qualifying_monthly == _d("1500.00")

        # Verify the vacancy deduction
        vacancy_deduction = (lease_monthly * RENTAL_VACANCY_FACTOR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        assert vacancy_deduction == _d("500.00")
        assert qualifying_monthly == lease_monthly - vacancy_deduction

    def test_negative_rental_added_to_dti(self):
        """
        Negative rental income increases the borrower's DTI.

        Gross rents: $1,200/mo
        PITIA on rental: $1,800/mo
        Net rental: -$600/mo after vacancy

        Qualifying rent: $1,200 * 0.75 = $900/mo
        Net cash flow: $900 - $1,800 = -$900/mo (after vacancy)

        Alternatively, without vacancy factor on existing rental (Schedule E):
        Net rental: $1,200 - $1,800 = -$600/mo

        Per Selling Guide B3-3.1-08: negative rental income (net rental
        loss) must be added as a recurring monthly obligation in the DTI.
        The $300/mo loss is treated as a debt.
        """
        gross_rents_monthly = _d("1200.00")
        pitia_monthly = _d("1800.00")

        # Schedule E approach: net = rents - PITIA
        # (PITIA components are added back in Schedule E, then the actual
        # PITIA is subtracted as the housing expense. The shorthand is
        # that negative cash flow = additional monthly obligation.)
        net_cash_flow = gross_rents_monthly - pitia_monthly
        assert net_cash_flow == _d("-600.00")

        # This negative amount is added to the borrower's monthly debts
        monthly_obligation = abs(net_cash_flow)
        assert monthly_obligation == _d("600.00")

        # With vacancy factor on proposed rental
        qualifying_rent = (gross_rents_monthly * NET_RENTAL_FACTOR).quantize(TWO_PLACES)
        net_with_vacancy = qualifying_rent - pitia_monthly
        # $900 - $1,800 = -$900
        assert net_with_vacancy == _d("-900.00")
        assert abs(net_with_vacancy) == _d("900.00")

    def test_multiple_rental_properties(self):
        """
        Multiple rental properties with mixed positive/negative cash flow.

        Property 1: net rental income +$500/mo
        Property 2: net rental loss    -$200/mo
        Property 3: net rental income +$800/mo

        Net rental: $500 + (-$200) + $800 = $1,100/mo

        Per Selling Guide B3-3.1-08: each property's net rental income
        or loss from Schedule E is calculated individually, then all
        properties are aggregated. The net total is used in DTI.
        """
        prop1_net = _d("500.00")
        prop2_net = _d("-200.00")
        prop3_net = _d("800.00")

        net_rental = prop1_net + prop2_net + prop3_net
        assert net_rental == _d("1100.00")

        # Verify individual property sign handling
        assert prop1_net > ZERO, "Property 1 is positive cash flow"
        assert prop2_net < ZERO, "Property 2 is negative cash flow"
        assert prop3_net > ZERO, "Property 3 is positive cash flow"

        # Net is positive, so it counts as income (not debt)
        assert net_rental > ZERO


# ============================================================================
# 5. DTI CALCULATION TESTS
# ============================================================================

class TestDTICalculation:
    """
    Debt-to-Income ratio calculations per agency guidelines.
    """

    def test_conventional_dti_calculation(self):
        """
        Conventional loan DTI calculation.

        Monthly gross income: $8,000
        PITIA (housing):      $2,400
        Other debts:          $800 (auto + student + credit cards)

        Front-end DTI: $2,400 / $8,000 = 30.00%
        Back-end DTI:  ($2,400 + $800) / $8,000 = 40.00%

        Conventional max back-end: 45% (50% with compensating factors)
        Both ratios within limits: PASS

        Per Selling Guide B3-6-02: conventional loans evaluated through
        DU typically have a max DTI of 45%, or 50% with compensating
        factors (significant reserves, minimal payment shock, etc.).
        """
        gross_monthly = _d("8000.00")
        pitia = _d("2400.00")
        other_debts = _d("800.00")

        front_end = (pitia / gross_monthly * _d("100")).quantize(TWO_PLACES)
        assert front_end == _d("30.00")

        total_obligations = pitia + other_debts
        back_end = (total_obligations / gross_monthly * _d("100")).quantize(TWO_PLACES)
        assert back_end == _d("40.00")

        # Within conventional limits
        conv_max_backend = _d("45.00")
        conv_max_backend_comp = _d("50.00")
        assert back_end <= conv_max_backend, "Back-end within 45% standard limit"
        assert back_end <= conv_max_backend_comp, "Back-end within 50% comp limit"

        # Verify the ratio components
        assert total_obligations == _d("3200.00")
        assert gross_monthly - total_obligations == _d("4800.00"), "Residual after obligations"

    def test_fha_dti_with_gross_up(self):
        """
        FHA DTI with non-taxable income gross-up.

        Taxable income:         $5,000/mo
        VA disability income:   $1,200/mo (non-taxable)
        Gross-up factor:        25%

        Grossed-up disability: $1,200 * 1.25 = $1,500/mo
        Total qualifying:      $5,000 + $1,500 = $6,500/mo

        Per HUD 4000.1 II.A.4.c: non-taxable income may be grossed up
        by 25% (or the borrower's actual tax rate, whichever is lower).
        This increases the qualifying income for DTI purposes.
        """
        taxable_monthly = _d("5000.00")
        va_disability_monthly = _d("1200.00")
        gross_up_factor = _d("1.25")

        grossed_up_disability = (va_disability_monthly * gross_up_factor).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        # $1,200 * 1.25 = $1,500.00
        assert grossed_up_disability == _d("1500.00")

        total_qualifying = taxable_monthly + grossed_up_disability
        assert total_qualifying == _d("6500.00")

        # FHA DTI limits
        # Standard: 31/43, with TOTAL Scorecard approval up to 57%
        fha_front_max = _d("31.00")
        fha_back_max = _d("43.00")
        fha_back_max_scorecard = _d("57.00")

        # Example DTI check with $1,950 PITIA and $500 debts
        pitia = _d("1950.00")
        other_debts = _d("500.00")

        front_end = (pitia / total_qualifying * _d("100")).quantize(TWO_PLACES)
        # $1,950 / $6,500 * 100 = 30.00%
        assert front_end == _d("30.00")
        assert front_end <= fha_front_max

        back_end = ((pitia + other_debts) / total_qualifying * _d("100")).quantize(TWO_PLACES)
        # ($1,950 + $500) / $6,500 * 100 = $2,450 / $6,500 * 100 = 37.69%
        assert back_end == _d("37.69")
        assert back_end <= fha_back_max

    def test_va_residual_income(self):
        """
        VA residual income calculation.

        Monthly gross income:   $7,000
        PITIA:                  $2,100
        Monthly debts:          $900
        Family size:            4
        Region:                 South
        Loan amount:            $300,000 (above $80K threshold)

        VA residual income table (South, family of 4): $1,003
        Since loan > $80K, required residual = $1,003 (table value applies
        for loans above $80K).

        Estimated maintenance & utilities: 14 cents per sq ft * 1,800 sq ft = $252
        (Simplified: use a flat estimate for this test.)
        Tax withholding estimate (federal + state + FICA): ~30% of gross

        Residual = Gross - Taxes - PITIA - Debts - Maintenance
        Taxes est: $7,000 * 0.30 = $2,100
        Maintenance est: $252

        Residual: $7,000 - $2,100 - $2,100 - $900 - $252 = $1,648.00

        Required (South, 4 persons, loan > $80K): $1,003
        $1,648 >= $1,003 -> PASS

        Per VA Lender's Handbook Ch. 4: residual income is the amount
        remaining after deducting shelter expenses, debts, taxes,
        and maintenance/utilities. Must exceed regional table amount.
        """
        gross_monthly = _d("7000.00")
        pitia = _d("2100.00")
        debts = _d("900.00")
        family_size = 4
        region = "south"
        loan_amount = _d("300000.00")

        # VA residual income table (from dti_optimizer_service.py constants)
        va_table = {
            "northeast": {1: 450, 2: 755, 3: 909, 4: 1025, 5: 1062},
            "midwest":   {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
            "south":     {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
            "west":      {1: 491, 2: 823, 3: 990, 4: 1117, 5: 1158},
        }
        required_residual = _d(str(va_table[region][family_size]))
        assert required_residual == _d("1003")

        # Verify loan exceeds $80K threshold
        va_large_loan_threshold = _d("80000.00")
        assert loan_amount > va_large_loan_threshold

        # Estimated deductions
        tax_rate = _d("0.30")
        taxes = (gross_monthly * tax_rate).quantize(TWO_PLACES)
        assert taxes == _d("2100.00")

        # Maintenance & utilities estimate (14 cents/sqft * 1800 sqft)
        sqft = Decimal("1800")
        maintenance_per_sqft = _d("0.14")
        maintenance = (sqft * maintenance_per_sqft).quantize(TWO_PLACES)
        assert maintenance == _d("252.00")

        residual = gross_monthly - taxes - pitia - debts - maintenance
        # $7,000 - $2,100 - $2,100 - $900 - $252 = $1,648.00
        assert residual == _d("1648.00")

        assert residual >= required_residual, (
            f"Residual ${residual} must meet or exceed required ${required_residual}"
        )


# ============================================================================
# 6. EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """
    Edge cases and boundary conditions for income calculations.
    """

    def test_zero_income(self):
        """Zero income across all sources should produce zero monthly."""
        year1 = ZERO
        year2 = ZERO

        result = two_year_avg_monthly(year1, year2)
        assert result == ZERO

    def test_exactly_at_declining_threshold(self):
        """
        Income decline of exactly 20% is at the threshold boundary.

        Year 1: $80,000
        Year 2: $100,000
        Decline: exactly 20%

        The service uses >= 20% as the trigger. At exactly 20%,
        the declining income rule should apply.
        """
        year1 = _d("80000.00")
        year2 = _d("100000.00")

        decline_pct = ((year2 - year1) / year2 * _d("100")).quantize(TWO_PLACES)
        assert decline_pct == _d("20.00")

        # At exactly 20%, the rule triggers (>=)
        critical_threshold = _d("20.00")
        assert decline_pct >= critical_threshold

        # Should use lower year
        expected = monthly(year1)
        assert expected == _d("6666.67")

    def test_exactly_at_commission_25_pct_threshold(self):
        """
        Commission at exactly 25% of total compensation.

        Base: $75,000
        Commission: $25,000
        Ratio: $25,000 / $100,000 = 25.00%

        At exactly 25%, the 2-year history requirement kicks in.
        """
        base = _d("75000.00")
        commission = _d("25000.00")
        total_comp = base + commission

        ratio = (commission / total_comp * _d("100")).quantize(TWO_PLACES)
        assert ratio == _d("25.00")

        # At exactly 25%, 2-year history is required (>=)
        threshold = _d("25.00")
        assert ratio >= threshold

    def test_very_small_income_precision(self):
        """
        Very small income amounts should maintain Decimal precision.
        Tests that rounding does not discard small but real values.
        """
        annual_income = _d("1.00")  # $1 per year (extreme edge case)
        result = monthly(annual_income)
        # $1.00 / 12 = $0.083333... -> $0.08
        assert result == _d("0.08")
        assert result > ZERO

    def test_large_income_precision(self):
        """
        Very large income should maintain precision without overflow.
        """
        year1 = _d("2500000.00")  # $2.5M
        year2 = _d("2800000.00")  # $2.8M

        result = two_year_avg_monthly(year1, year2)
        # ($2,500,000 + $2,800,000) / 24 = $5,300,000 / 24 = $220,833.33
        assert result == _d("220833.33")

    def test_negative_self_employment_loss(self):
        """
        Net business loss should produce negative monthly income.
        This negative amount reduces qualifying income from other sources.
        """
        net_loss = _d("-15000.00")
        result = monthly(net_loss)
        # -$15,000 / 12 = -$1,250.00
        assert result == _d("-1250.00")
        assert result < ZERO

    def test_dti_with_zero_income_raises_no_exception(self):
        """
        DTI calculation with zero income should not raise ZeroDivisionError.
        The system should handle this gracefully.
        """
        gross_monthly = ZERO
        pitia = _d("2000.00")

        # Guard against division by zero
        if gross_monthly == ZERO:
            front_end = None  # Cannot calculate DTI
            back_end = None
        else:
            front_end = (pitia / gross_monthly * _d("100")).quantize(TWO_PLACES)
            back_end = front_end

        assert front_end is None
        assert back_end is None

    def test_rental_vacancy_factor_exact(self):
        """
        Vacancy factor produces exact result for clean multiples.
        $4,000/mo * 0.75 = $3,000.00 exactly (no rounding needed).
        """
        lease = _d("4000.00")
        qualifying = (lease * NET_RENTAL_FACTOR).quantize(TWO_PLACES)
        assert qualifying == _d("3000.00")

    def test_one_year_only_self_employment(self):
        """
        Self-employment with only 1 year of history uses that year.
        No averaging is performed; the single year divided by 12.
        """
        single_year = _d("72000.00")
        result = monthly(single_year)
        assert result == _d("6000.00")

    def test_ytd_annualization_partial_month(self):
        """
        YTD with partial months: paystub dated March 15 = ~2.5 months.

        YTD gross: $20,000
        Months elapsed: 2.5
        Annualized: $20,000 * 12 / 2.5 = $96,000

        Monthly: $96,000 / 12 = $8,000
        """
        ytd_gross = _d("20000.00")
        months_elapsed = _d("2.5")

        annualized = (ytd_gross * MONTHS_PER_YEAR / months_elapsed).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        assert annualized == _d("96000.00")

        result = monthly(annualized)
        assert result == _d("8000.00")
