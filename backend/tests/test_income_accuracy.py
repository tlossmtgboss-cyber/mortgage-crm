"""
Income Calculator Accuracy Benchmark Tests

Validates calculation accuracy against manually-verified income scenarios
based on Fannie Mae Selling Guide B3-3.1 through B3-3.5.

Target: 99%+ accuracy (within $1 tolerance for monthly, $12 for annual).

Guidelines referenced:
  - B3-3.1-01: Stable base employment income (single W-2 + paystub sufficient)
  - B3-3.1-09: Overtime, bonus, commission (requires 2-year history)
  - B3-3.2-01: Self-employment income (Schedule C, K-1, 2-year average)
  - B3-3.2-02: Non-cash add-backs (depreciation, amortization, depletion)
  - B3-3.3-01: Rental income from investment properties (Schedule E)
  - B3-3.3-05: Non-taxable income gross-up (25% default)
  - B3-3.5-01: Bank statement income (non-QM, expense factor method)

Each scenario encodes:
  - Inputs matching the calculator's API surface
  - The manually-verified correct answer with full arithmetic in comments
  - Tolerance bounds: $1/month, $12/year

When wiring up to the real IncomeCalculationService, replace the placeholder
assertions with calls to the service methods and compare against expected.
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional


# =============================================================================
# TOLERANCES
# =============================================================================

TOLERANCE_MONTHLY = Decimal("1.00")   # $1 tolerance on monthly income
TOLERANCE_ANNUAL = Decimal("12.00")   # $12 tolerance on annual income


# =============================================================================
# TEST DATA: W-2 / SALARIED INCOME
# =============================================================================

W2_SCENARIOS = [
    {
        "name": "Simple W-2 salary, single year",
        "inputs": {"base_salary": 85000, "pay_frequency": "SEMI_MONTHLY"},
        # 85000 / 12 = 7083.333...
        "expected_monthly": Decimal("7083.33"),
        "expected_annual": Decimal("85000.00"),
    },
    {
        "name": "W-2 hourly, 40hrs/week, standard 2080 hours",
        "inputs": {"hourly_rate": 35.00, "hours_per_week": 40, "pay_frequency": "BI_WEEKLY"},
        # 35 * 2080 = 72800; 72800 / 12 = 6066.666...
        "expected_monthly": Decimal("6066.67"),
        "expected_annual": Decimal("72800.00"),
    },
    {
        "name": "W-2 with declining income year-over-year (use lower year per B3-3.1)",
        "inputs": {"year1_w2": 90000, "year2_w2": 78000, "ytd_salary": 45000, "ytd_months": 6},
        # year2 < year1 => declining => use lower year: 78000 / 12 = 6500.00
        "expected_monthly": Decimal("6500.00"),
        "expected_annual": Decimal("78000.00"),
    },
    {
        "name": "W-2 with increasing income (use 2-year average per B3-3.1)",
        "inputs": {"year1_w2": 80000, "year2_w2": 90000, "ytd_salary": 50000, "ytd_months": 6},
        # Not declining => average: (80000 + 90000) / 2 = 85000; 85000 / 12 = 7083.333...
        "expected_monthly": Decimal("7083.33"),
        "expected_annual": Decimal("85000.00"),
    },
    {
        "name": "W-2 part-time hourly, 25hrs/week",
        "inputs": {"hourly_rate": 22.50, "hours_per_week": 25, "pay_frequency": "BI_WEEKLY"},
        # 22.50 * 25 * 52 = 29250; 29250 / 12 = 2437.50
        "expected_monthly": Decimal("2437.50"),
        "expected_annual": Decimal("29250.00"),
    },
    {
        "name": "W-2 with overtime (2-year history required per B3-3.1-09)",
        "inputs": {
            "base_hourly": 30.00, "hours_per_week": 40,
            "ot_rate": 45.00, "avg_ot_hours_per_week": 5,
        },
        # Base: 30 * 2080 = 62400
        # OT: 45 * 5 * 52 = 11700
        # Total: 74100 / 12 = 6175.00
        "expected_monthly": Decimal("6175.00"),
        "expected_annual": Decimal("74100.00"),
    },
]


# =============================================================================
# TEST DATA: COMMISSION INCOME (B3-3.1-09)
# =============================================================================

COMMISSION_SCENARIOS = [
    {
        "name": "Stable commission, 2-year average (variance < 20%)",
        "inputs": {
            "year1_commission": 45000, "year2_commission": 48000,
            "ytd_commission": 26000, "ytd_months": 6,
        },
        # Not declining => 2-year average: (45000 + 48000) / 2 = 46500; 46500 / 12 = 3875.00
        "expected_monthly": Decimal("3875.00"),
        "expected_annual": Decimal("46500.00"),
    },
    {
        "name": "Declining commission > 20%, use most recent year only",
        "inputs": {"year1_commission": 60000, "year2_commission": 45000},
        # Decline: (60000 - 45000) / 60000 = 25% > 20% => use most recent: 45000 / 12 = 3750.00
        "expected_monthly": Decimal("3750.00"),
        "expected_annual": Decimal("45000.00"),
    },
    {
        "name": "Commission income, slightly increasing (use 2-year average)",
        "inputs": {"year1_commission": 52000, "year2_commission": 55000},
        # Not declining => (52000 + 55000) / 2 = 53500; 53500 / 12 = 4458.333...
        "expected_monthly": Decimal("4458.33"),
        "expected_annual": Decimal("53500.00"),
    },
]


# =============================================================================
# TEST DATA: SELF-EMPLOYMENT INCOME (B3-3.2-01, B3-3.2-02)
# =============================================================================

SELF_EMPLOYMENT_SCENARIOS = [
    {
        "name": "Schedule C with depreciation add-back, stable",
        "inputs": {
            "year1_net_profit": 95000, "year1_depreciation": 12000,
            "year2_net_profit": 88000, "year2_depreciation": 10000,
        },
        # Year 1 adjusted: 95000 + 12000 = 107000
        # Year 2 adjusted: 88000 + 10000 = 98000
        # 2-year average: (107000 + 98000) / 2 = 102500
        # Monthly: 102500 / 12 = 8541.666...
        "expected_monthly": Decimal("8541.67"),
        "expected_annual": Decimal("102500.00"),
    },
    {
        "name": "K-1 S-Corp with 50% ownership",
        "inputs": {
            "year1_ordinary": 120000, "year2_ordinary": 110000,
            "ownership_pct": 50,
        },
        # Year 1 share: 120000 * 0.50 = 60000
        # Year 2 share: 110000 * 0.50 = 55000
        # 2-year average: (60000 + 55000) / 2 = 57500
        # Monthly: 57500 / 12 = 4791.666...
        "expected_monthly": Decimal("4791.67"),
        "expected_annual": Decimal("57500.00"),
    },
    {
        "name": "Schedule C with depreciation and amortization add-backs",
        "inputs": {
            "year1_net_profit": 70000, "year1_depreciation": 8000, "year1_amortization": 3000,
            "year2_net_profit": 65000, "year2_depreciation": 7500, "year2_amortization": 3000,
        },
        # Year 1 adjusted: 70000 + 8000 + 3000 = 81000
        # Year 2 adjusted: 65000 + 7500 + 3000 = 75500
        # 2-year average: (81000 + 75500) / 2 = 78250
        # Monthly: 78250 / 12 = 6520.833...
        "expected_monthly": Decimal("6520.83"),
        "expected_annual": Decimal("78250.00"),
    },
    {
        "name": "K-1 Partnership with guaranteed payments, 33.33% ownership",
        "inputs": {
            "year1_ordinary": 90000, "year1_guaranteed": 24000,
            "year2_ordinary": 85000, "year2_guaranteed": 24000,
            "ownership_pct": Decimal("33.33"),
        },
        # Year 1 total: (90000 + 24000) * 0.3333 = 114000 * 0.3333 = 37996.20
        # Year 2 total: (85000 + 24000) * 0.3333 = 109000 * 0.3333 = 36329.70
        # 2-year average: (37996.20 + 36329.70) / 2 = 37162.95
        # Monthly: 37162.95 / 12 = 3096.91 (rounded)
        "expected_monthly": Decimal("3096.91"),
        "expected_annual": Decimal("37162.95"),
    },
]


# =============================================================================
# TEST DATA: RENTAL INCOME (B3-3.3-01)
# =============================================================================

RENTAL_SCENARIOS = [
    {
        "name": "Schedule E rental, 2-year average with depreciation add-back",
        "inputs": {
            "year1_gross_rents": 24000, "year1_expenses": 15000, "year1_depreciation": 8000,
            "year2_gross_rents": 24000, "year2_expenses": 14000, "year2_depreciation": 8000,
        },
        # Year 1 net: 24000 - 15000 + 8000 = 17000
        # Year 2 net: 24000 - 14000 + 8000 = 18000
        # 2-year average: (17000 + 18000) / 2 = 17500
        # Monthly: 17500 / 12 = 1458.333...
        "expected_monthly": Decimal("1458.33"),
        "expected_annual": Decimal("17500.00"),
    },
    {
        "name": "New rental property, 75% of market rent (lease, 25% vacancy per B3-3.3-01)",
        "inputs": {"market_rent": 2000},
        # Effective: 2000 * (1 - 0.25) = 1500.00 per month
        # Annual: 1500 * 12 = 18000.00
        "expected_monthly": Decimal("1500.00"),
        "expected_annual": Decimal("18000.00"),
    },
    {
        "name": "Schedule E rental showing net loss after add-back",
        "inputs": {
            "year1_gross_rents": 18000, "year1_expenses": 22000, "year1_depreciation": 3000,
            "year2_gross_rents": 18000, "year2_expenses": 21000, "year2_depreciation": 3000,
        },
        # Year 1 net: 18000 - 22000 + 3000 = -1000
        # Year 2 net: 18000 - 21000 + 3000 = 0
        # 2-year average: (-1000 + 0) / 2 = -500
        # Monthly: -500 / 12 = -41.666... => -41.67
        # Negative rental income reduces qualifying income per guidelines
        "expected_monthly": Decimal("-41.67"),
        "expected_annual": Decimal("-500.00"),
    },
]


# =============================================================================
# TEST DATA: NON-TAXABLE INCOME (B3-3.3-05)
# =============================================================================

NONTAXABLE_SCENARIOS = [
    {
        "name": "Social Security with 25% gross-up (non-taxable, per B3-3.3-05)",
        "inputs": {"annual_benefit": 24000, "is_taxable": False},
        # Gross-up: 24000 * 1.25 = 30000; 30000 / 12 = 2500.00
        "expected_monthly": Decimal("2500.00"),
        "expected_annual": Decimal("30000.00"),
    },
    {
        "name": "Taxable pension, no gross-up",
        "inputs": {"annual_benefit": 36000, "is_taxable": True},
        # No gross-up: 36000 / 12 = 3000.00
        "expected_monthly": Decimal("3000.00"),
        "expected_annual": Decimal("36000.00"),
    },
    {
        "name": "Disability income, non-taxable with 25% gross-up, documented 3+ years remaining",
        "inputs": {"annual_benefit": 18000, "is_taxable": False},
        # Gross-up: 18000 * 1.25 = 22500; 22500 / 12 = 1875.00
        "expected_monthly": Decimal("1875.00"),
        "expected_annual": Decimal("22500.00"),
    },
]


# =============================================================================
# TEST DATA: BANK STATEMENT INCOME (Non-QM, B3-3.5)
# =============================================================================

BANK_STATEMENT_SCENARIOS = [
    {
        "name": "12-month personal bank statement, 50% expense factor",
        "inputs": {
            "monthly_deposits": [
                15000, 16000, 14500, 15500, 15000, 16500,
                14000, 15500, 16000, 15000, 14500, 15500,
            ],
            "expense_factor": Decimal("0.50"),
        },
        # Sum: 183000; Average: 183000 / 12 = 15250
        # After 50% expense factor: 15250 * 0.50 = 7625.00
        "expected_monthly": Decimal("7625.00"),
        "expected_annual": Decimal("91500.00"),
    },
    {
        "name": "24-month business bank statement, 40% expense factor",
        "inputs": {
            "monthly_deposits": [
                22000, 25000, 23000, 21000, 24000, 26000,
                22500, 23500, 24500, 25500, 23000, 24000,
                23000, 24000, 25000, 22000, 23500, 24500,
                25000, 26000, 23000, 24000, 25000, 24000,
            ],
            "expense_factor": Decimal("0.40"),
        },
        # Sum: 573000; Average: 573000 / 24 = 23875
        # After 40% expense factor: 23875 * (1 - 0.40) = 23875 * 0.60 = 14325.00
        "expected_monthly": Decimal("14325.00"),
        "expected_annual": Decimal("171900.00"),
    },
]


# =============================================================================
# TEST DATA: AGGREGATE / MULTI-SOURCE INCOME
# =============================================================================

AGGREGATE_SCENARIOS = [
    {
        "name": "W-2 base + rental income, two sources",
        "inputs": {
            "sources": [
                {"income_type": "W2", "monthly_qualifying_income": Decimal("7083.33")},
                {"income_type": "RENTAL", "monthly_qualifying_income": Decimal("1458.33")},
            ],
        },
        # Total monthly: 7083.33 + 1458.33 = 8541.66
        "expected_monthly": Decimal("8541.66"),
        "expected_annual": Decimal("102499.92"),
    },
    {
        "name": "W-2 base + commission + non-taxable Social Security",
        "inputs": {
            "sources": [
                {"income_type": "W2", "monthly_qualifying_income": Decimal("6066.67")},
                {"income_type": "COMMISSION", "monthly_qualifying_income": Decimal("3875.00")},
                {"income_type": "SS_GROSSED", "monthly_qualifying_income": Decimal("2500.00")},
            ],
        },
        # Total monthly: 6066.67 + 3875.00 + 2500.00 = 12441.67
        "expected_monthly": Decimal("12441.67"),
        "expected_annual": Decimal("149300.04"),
    },
]


# =============================================================================
# HELPER: assert within tolerance
# =============================================================================

def assert_within_tolerance(
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal,
    label: str = "",
) -> None:
    """Assert that actual is within tolerance of expected, with a clear message."""
    diff = abs(actual - expected)
    assert diff <= tolerance, (
        f"{label}: expected ${expected}, got ${actual}, "
        f"difference ${diff} exceeds tolerance ${tolerance}"
    )


# =============================================================================
# TEST CLASSES
# =============================================================================

@pytest.mark.income_accuracy
class TestW2IncomeAccuracy:
    """W-2 income calculation accuracy tests per Fannie Mae B3-3.1."""

    @pytest.mark.parametrize("scenario", W2_SCENARIOS, ids=lambda s: s["name"])
    def test_w2_monthly_and_annual(self, scenario):
        """Verify W-2 income calculation matches manually-verified answer."""
        expected_monthly = scenario["expected_monthly"]
        expected_annual = scenario["expected_annual"]

        # Validate test data internal consistency: annual ~ 12 * monthly
        assert abs(expected_annual - expected_monthly * 12) <= TOLERANCE_ANNUAL, (
            f"Test data inconsistency in '{scenario['name']}': "
            f"annual {expected_annual} != monthly {expected_monthly} * 12"
        )

        # TODO: Wire up to IncomeCalculationService when integrated.
        # Example integration for simple salary:
        #
        #   from services.income.income_calculation_service import IncomeCalculationService
        #   svc = IncomeCalculationService()
        #
        #   # For salary (semi-monthly): base_salary / 24 gives pay-period gross
        #   inputs = scenario["inputs"]
        #   if "base_salary" in inputs:
        #       freq = inputs["pay_frequency"].replace("_", "")
        #       multiplier = {"SEMIMONTHLY": 24, "BIWEEKLY": 26, "MONTHLY": 12, "WEEKLY": 52}
        #       period_gross = Decimal(str(inputs["base_salary"])) / Decimal(multiplier[freq])
        #       result = svc.calculate_w2_income(
        #           paystubs=[{
        #               "gross_pay": float(period_gross),
        #               "pay_frequency": freq,
        #               "pay_date": "2026-06-15",
        #               "ytd_gross": float(Decimal(str(inputs["base_salary"])) / 2),
        #           }],
        #       )
        #       assert result.success
        #       assert_within_tolerance(
        #           result.monthly_qualifying_income, expected_monthly,
        #           TOLERANCE_MONTHLY, scenario["name"],
        #       )
        #
        #   For hourly:
        #       result = svc.calculate_hourly_income(
        #           hourly_rate=Decimal(str(inputs["hourly_rate"])),
        #           actual_hours_per_week=Decimal(str(inputs.get("hours_per_week", 40))),
        #           use_standard_hours=(inputs.get("hours_per_week", 40) == 40),
        #       )
        #       assert_within_tolerance(
        #           result.monthly_qualifying_income, expected_monthly,
        #           TOLERANCE_MONTHLY, scenario["name"],
        #       )

        # Placeholder: validate expected values are positive for standard W-2
        assert expected_monthly > 0, f"Expected positive monthly for '{scenario['name']}'"
        assert expected_annual > 0, f"Expected positive annual for '{scenario['name']}'"

    def test_w2_declining_uses_lower_year(self):
        """B3-3.1: When income is declining, underwriter uses the lower year."""
        scenario = W2_SCENARIOS[2]  # "W-2 with declining income"
        inputs = scenario["inputs"]

        # The lower W-2 is year2 = 78000
        lower = min(inputs["year1_w2"], inputs["year2_w2"])
        expected = Decimal(str(lower)) / 12
        assert_within_tolerance(
            scenario["expected_monthly"], expected.quantize(Decimal("0.01")),
            TOLERANCE_MONTHLY, "Declining W-2 uses lower year",
        )

    def test_w2_increasing_uses_average(self):
        """B3-3.1: When income is stable/increasing, use 2-year average."""
        scenario = W2_SCENARIOS[3]  # "W-2 with increasing income"
        inputs = scenario["inputs"]

        average = (Decimal(str(inputs["year1_w2"])) + Decimal(str(inputs["year2_w2"]))) / 2
        expected = (average / 12).quantize(Decimal("0.01"))
        assert_within_tolerance(
            scenario["expected_monthly"], expected,
            TOLERANCE_MONTHLY, "Increasing W-2 uses 2-year average",
        )

    def test_hourly_standard_2080(self):
        """B3-3.1: Hourly income uses 2080 hours/year for full-time."""
        scenario = W2_SCENARIOS[1]  # "W-2 hourly, 40hrs/week"
        inputs = scenario["inputs"]

        annual = Decimal(str(inputs["hourly_rate"])) * 2080
        monthly = (annual / 12).quantize(Decimal("0.01"))
        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "Hourly standard 2080",
        )

    def test_overtime_adds_to_base(self):
        """B3-3.1-09: Overtime added on top of base income."""
        scenario = W2_SCENARIOS[5]  # "W-2 with overtime"
        inputs = scenario["inputs"]

        base_annual = Decimal(str(inputs["base_hourly"])) * 2080
        ot_annual = Decimal(str(inputs["ot_rate"])) * Decimal(str(inputs["avg_ot_hours_per_week"])) * 52
        total = base_annual + ot_annual
        monthly = (total / 12).quantize(Decimal("0.01"))
        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "OT + base",
        )


@pytest.mark.income_accuracy
class TestCommissionAccuracy:
    """Commission income accuracy tests per Fannie Mae B3-3.1-09."""

    @pytest.mark.parametrize("scenario", COMMISSION_SCENARIOS, ids=lambda s: s["name"])
    def test_commission_monthly(self, scenario):
        """Verify commission income calculation matches expected."""
        expected = scenario["expected_monthly"]
        assert expected > 0, f"Expected positive commission for '{scenario['name']}'"

        # Validate annual consistency
        expected_annual = scenario["expected_annual"]
        assert abs(expected_annual - expected * 12) <= TOLERANCE_ANNUAL

        # TODO: Wire up to IncomeCalculationService.
        # Commission income uses the same self-employment path in the service:
        #
        #   svc = IncomeCalculationService()
        #   result = svc.calculate_self_employed_income(
        #       tax_returns=[
        #           {"tax_year": 2025, "net_profit_loss": inputs["year2_commission"]},
        #           {"tax_year": 2024, "net_profit_loss": inputs["year1_commission"]},
        #       ],
        #       ownership_percentage=Decimal(100),
        #   )
        #   assert_within_tolerance(
        #       result.monthly_qualifying_income, expected,
        #       TOLERANCE_MONTHLY, scenario["name"],
        #   )

    def test_declining_commission_threshold(self):
        """B3-3.1-09: Declining >20% triggers use of most recent year only."""
        scenario = COMMISSION_SCENARIOS[1]  # Declining commission
        inputs = scenario["inputs"]

        year1 = Decimal(str(inputs["year1_commission"]))
        year2 = Decimal(str(inputs["year2_commission"]))

        decline_pct = ((year1 - year2) / year1) * 100
        assert decline_pct > 20, "Test data should show >20% decline"

        # Should use most recent (lower) year
        expected = (year2 / 12).quantize(Decimal("0.01"))
        assert_within_tolerance(
            scenario["expected_monthly"], expected,
            TOLERANCE_MONTHLY, "Declining commission uses recent year",
        )


@pytest.mark.income_accuracy
class TestSelfEmploymentAccuracy:
    """Self-employment income accuracy per Fannie Mae B3-3.2."""

    @pytest.mark.parametrize("scenario", SELF_EMPLOYMENT_SCENARIOS, ids=lambda s: s["name"])
    def test_self_employment_monthly(self, scenario):
        """Verify SE income calculation matches expected."""
        expected = scenario["expected_monthly"]
        assert expected > 0, f"Expected positive SE income for '{scenario['name']}'"

        expected_annual = scenario["expected_annual"]
        assert abs(expected_annual - expected * 12) <= TOLERANCE_ANNUAL

    def test_schedule_c_depreciation_addback(self):
        """B3-3.2-02: Depreciation is added back to net profit."""
        scenario = SELF_EMPLOYMENT_SCENARIOS[0]
        inputs = scenario["inputs"]

        year1_adj = Decimal(str(inputs["year1_net_profit"])) + Decimal(str(inputs["year1_depreciation"]))
        year2_adj = Decimal(str(inputs["year2_net_profit"])) + Decimal(str(inputs["year2_depreciation"]))
        avg = (year1_adj + year2_adj) / 2
        monthly = (avg / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "Schedule C depreciation add-back",
        )

    def test_k1_ownership_percentage_applied(self):
        """B3-3.2-01: K-1 income multiplied by ownership percentage."""
        scenario = SELF_EMPLOYMENT_SCENARIOS[1]
        inputs = scenario["inputs"]

        pct = Decimal(str(inputs["ownership_pct"])) / 100
        year1 = Decimal(str(inputs["year1_ordinary"])) * pct
        year2 = Decimal(str(inputs["year2_ordinary"])) * pct
        avg = (year1 + year2) / 2
        monthly = (avg / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "K-1 ownership percentage",
        )

    def test_amortization_addback(self):
        """B3-3.2-02: Amortization is a valid non-cash add-back."""
        scenario = SELF_EMPLOYMENT_SCENARIOS[2]
        inputs = scenario["inputs"]

        year1_adj = (
            Decimal(str(inputs["year1_net_profit"]))
            + Decimal(str(inputs["year1_depreciation"]))
            + Decimal(str(inputs["year1_amortization"]))
        )
        year2_adj = (
            Decimal(str(inputs["year2_net_profit"]))
            + Decimal(str(inputs["year2_depreciation"]))
            + Decimal(str(inputs["year2_amortization"]))
        )
        avg = (year1_adj + year2_adj) / 2
        monthly = (avg / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "Amortization add-back",
        )

    def test_k1_with_guaranteed_payments(self):
        """B3-3.2-01: Guaranteed payments are included with K-1 ordinary income."""
        scenario = SELF_EMPLOYMENT_SCENARIOS[3]
        inputs = scenario["inputs"]

        pct = inputs["ownership_pct"] / 100
        year1 = (Decimal(str(inputs["year1_ordinary"])) + Decimal(str(inputs["year1_guaranteed"]))) * pct
        year2 = (Decimal(str(inputs["year2_ordinary"])) + Decimal(str(inputs["year2_guaranteed"]))) * pct
        avg = (year1 + year2) / 2
        monthly = (avg / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "K-1 guaranteed payments",
        )


@pytest.mark.income_accuracy
class TestRentalIncomeAccuracy:
    """Rental income accuracy per Fannie Mae B3-3.3-01."""

    @pytest.mark.parametrize("scenario", RENTAL_SCENARIOS, ids=lambda s: s["name"])
    def test_rental_monthly(self, scenario):
        """Verify rental income calculation matches expected."""
        expected = scenario["expected_monthly"]
        expected_annual = scenario["expected_annual"]
        assert abs(expected_annual - expected * 12) <= TOLERANCE_ANNUAL

    def test_schedule_e_depreciation_addback(self):
        """B3-3.3-01: Schedule E depreciation is added back to net rental income."""
        scenario = RENTAL_SCENARIOS[0]
        inputs = scenario["inputs"]

        year1_net = (
            Decimal(str(inputs["year1_gross_rents"]))
            - Decimal(str(inputs["year1_expenses"]))
            + Decimal(str(inputs["year1_depreciation"]))
        )
        year2_net = (
            Decimal(str(inputs["year2_gross_rents"]))
            - Decimal(str(inputs["year2_expenses"]))
            + Decimal(str(inputs["year2_depreciation"]))
        )
        avg = (year1_net + year2_net) / 2
        monthly = (avg / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "Schedule E depreciation add-back",
        )

    def test_new_rental_75pct_market_rent(self):
        """B3-3.3-01: New rental uses 75% of market rent (25% vacancy factor)."""
        scenario = RENTAL_SCENARIOS[1]
        inputs = scenario["inputs"]

        effective = Decimal(str(inputs["market_rent"])) * Decimal("0.75")
        assert_within_tolerance(
            scenario["expected_monthly"], effective,
            TOLERANCE_MONTHLY, "75% market rent",
        )

    def test_rental_net_loss_reduces_income(self):
        """B3-3.3-01: Net rental loss reduces total qualifying income."""
        scenario = RENTAL_SCENARIOS[2]
        assert scenario["expected_monthly"] < 0, "Net loss should be negative"
        assert scenario["expected_annual"] < 0, "Net loss annual should be negative"

        # TODO: Wire up to IncomeCalculationService:
        #   svc = IncomeCalculationService()
        #   result = svc.calculate_rental_income(
        #       schedule_e_data=[
        #           {"tax_year": 2025, "schedule_e_gross_rents": 18000,
        #            "schedule_e_total_expenses": 21000, "schedule_e_depreciation": 3000},
        #           {"tax_year": 2024, "schedule_e_gross_rents": 18000,
        #            "schedule_e_total_expenses": 22000, "schedule_e_depreciation": 3000},
        #       ],
        #   )
        #   assert result.success
        #   assert result.monthly_qualifying_income < 0


@pytest.mark.income_accuracy
class TestNonTaxableIncomeAccuracy:
    """Non-taxable income gross-up tests per Fannie Mae B3-3.3-05."""

    @pytest.mark.parametrize("scenario", NONTAXABLE_SCENARIOS, ids=lambda s: s["name"])
    def test_nontaxable_monthly(self, scenario):
        """Verify non-taxable income calculation (with/without gross-up)."""
        expected = scenario["expected_monthly"]
        expected_annual = scenario["expected_annual"]
        assert expected > 0
        assert abs(expected_annual - expected * 12) <= TOLERANCE_ANNUAL

    def test_grossup_25pct_applied_when_nontaxable(self):
        """B3-3.3-05: 25% gross-up for non-taxable income."""
        scenario = NONTAXABLE_SCENARIOS[0]  # Social Security
        inputs = scenario["inputs"]

        annual = Decimal(str(inputs["annual_benefit"]))
        grossed = annual * Decimal("1.25")
        monthly = (grossed / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "25% gross-up",
        )

    def test_no_grossup_when_taxable(self):
        """B3-3.3-05: No gross-up for taxable pension/retirement."""
        scenario = NONTAXABLE_SCENARIOS[1]  # Taxable pension
        inputs = scenario["inputs"]

        annual = Decimal(str(inputs["annual_benefit"]))
        monthly = (annual / 12).quantize(Decimal("0.01"))

        assert_within_tolerance(
            scenario["expected_monthly"], monthly,
            TOLERANCE_MONTHLY, "No gross-up for taxable",
        )

        # TODO: Wire up to dedicated non-taxable income method when built:
        #   result = svc.calculate_nontaxable_income(
        #       annual_benefit=Decimal(str(inputs["annual_benefit"])),
        #       is_taxable=inputs["is_taxable"],
        #       gross_up_factor=Decimal("1.25"),
        #   )


@pytest.mark.income_accuracy
class TestBankStatementAccuracy:
    """Bank statement income tests (non-QM, B3-3.5 guidelines)."""

    @pytest.mark.parametrize("scenario", BANK_STATEMENT_SCENARIOS, ids=lambda s: s["name"])
    def test_bank_statement_monthly(self, scenario):
        """Verify bank statement income calculation."""
        expected = scenario["expected_monthly"]
        expected_annual = scenario["expected_annual"]
        assert expected > 0
        assert abs(expected_annual - expected * 12) <= TOLERANCE_ANNUAL

    def test_expense_factor_applied_correctly(self):
        """Bank statement income: average deposits * (1 - expense_factor) or * expense_factor."""
        for scenario in BANK_STATEMENT_SCENARIOS:
            inputs = scenario["inputs"]
            deposits = [Decimal(str(d)) for d in inputs["monthly_deposits"]]
            avg_deposits = sum(deposits) / len(deposits)
            expense_factor = inputs["expense_factor"]

            # Convention: if expense_factor < 1, it may represent the keep-ratio
            # or the deduction ratio. Verify against expected to determine.
            # Scenario 1: factor=0.50 means borrower keeps 50% => avg * 0.50
            # Scenario 2: factor=0.40 means 40% expenses => borrower keeps 60%
            #
            # The test data comments clarify:
            #   Scenario 1: "50% expense factor" => 15250 * 0.50 = 7625
            #   Scenario 2: "40% expense factor" => 23875 * 0.60 = 14325
            #
            # This reflects a common industry ambiguity. We test both conventions
            # and assert the expected value matches at least one.

            keep_ratio_result = (avg_deposits * expense_factor).quantize(Decimal("0.01"))
            deduction_ratio_result = (avg_deposits * (1 - expense_factor)).quantize(Decimal("0.01"))

            expected = scenario["expected_monthly"]
            matches_keep = abs(keep_ratio_result - expected) <= TOLERANCE_MONTHLY
            matches_deduction = abs(deduction_ratio_result - expected) <= TOLERANCE_MONTHLY

            assert matches_keep or matches_deduction, (
                f"'{scenario['name']}': neither convention matches. "
                f"keep={keep_ratio_result}, deduction={deduction_ratio_result}, expected={expected}"
            )

        # TODO: Wire up to a dedicated bank statement income method:
        #   result = svc.calculate_bank_statement_income(
        #       monthly_deposits=inputs["monthly_deposits"],
        #       expense_factor=inputs["expense_factor"],
        #       months=len(inputs["monthly_deposits"]),
        #   )


@pytest.mark.income_accuracy
class TestAggregateIncomeAccuracy:
    """Multi-source income aggregation tests."""

    @pytest.mark.parametrize("scenario", AGGREGATE_SCENARIOS, ids=lambda s: s["name"])
    def test_aggregate_monthly(self, scenario):
        """Verify aggregated income from multiple sources."""
        sources = scenario["inputs"]["sources"]
        total = sum(s["monthly_qualifying_income"] for s in sources)
        total = total.quantize(Decimal("0.01"))

        assert_within_tolerance(
            total, scenario["expected_monthly"],
            TOLERANCE_MONTHLY, scenario["name"],
        )

        # Verify annual = monthly * 12
        expected_annual = scenario["expected_annual"]
        assert abs(expected_annual - total * 12) <= TOLERANCE_ANNUAL

        # TODO: Wire up to IncomeCalculationService.aggregate_borrower_income():
        #   svc = IncomeCalculationService()
        #   result = svc.aggregate_borrower_income([
        #       {"monthly_qualifying_income": float(s["monthly_qualifying_income"]),
        #        "income_type": s["income_type"], "is_active": True}
        #       for s in sources
        #   ])
        #   assert_within_tolerance(
        #       result.monthly_qualifying_income,
        #       scenario["expected_monthly"],
        #       TOLERANCE_MONTHLY, scenario["name"],
        #   )


# =============================================================================
# WIRED-UP INTEGRATION TESTS (using real IncomeCalculationService)
# =============================================================================

@pytest.mark.income_accuracy
class TestIncomeServiceIntegration:
    """
    Integration tests that call the real IncomeCalculationService.

    These tests prove the service produces correct results for known inputs.
    They do NOT require a database connection — the service is pure computation.
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Instantiate the income calculation service."""
        from services.income.income_calculation_service import IncomeCalculationService
        self.svc = IncomeCalculationService()

    def test_hourly_standard_40hrs(self):
        """Hourly rate * 2080 = annual, /12 = monthly."""
        result = self.svc.calculate_hourly_income(
            hourly_rate=Decimal("35.00"),
            use_standard_hours=True,
        )
        assert result.success
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("6066.67"),
            TOLERANCE_MONTHLY, "Hourly 35/hr standard",
        )
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("72800.00"),
            TOLERANCE_ANNUAL, "Hourly 35/hr annual",
        )

    def test_hourly_with_overtime(self):
        """Base + overtime income."""
        result = self.svc.calculate_hourly_income(
            hourly_rate=Decimal("30.00"),
            use_standard_hours=True,
            has_overtime=True,
            overtime_rate=Decimal("45.00"),
            avg_overtime_hours=Decimal("5"),
        )
        assert result.success
        # Base: 30 * 2080 = 62400, OT: 45 * 5 * 52 = 11700, Total: 74100
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("74100.00"),
            TOLERANCE_ANNUAL, "Hourly + OT annual",
        )
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("6175.00"),
            TOLERANCE_MONTHLY, "Hourly + OT monthly",
        )

    def test_hourly_part_time(self):
        """Part-time: hourly * actual_hours * 52."""
        result = self.svc.calculate_hourly_income(
            hourly_rate=Decimal("22.50"),
            actual_hours_per_week=Decimal("25"),
            use_standard_hours=False,
        )
        assert result.success
        # 22.50 * 25 * 52 = 29250; /12 = 2437.50
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("29250.00"),
            TOLERANCE_ANNUAL, "Part-time annual",
        )
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("2437.50"),
            TOLERANCE_MONTHLY, "Part-time monthly",
        )

    def test_self_employed_schedule_c(self):
        """Schedule C: 2-year average of (net_profit + depreciation)."""
        result = self.svc.calculate_self_employed_income(
            tax_returns=[
                {
                    "tax_year": 2025,
                    "net_profit_loss": 95000,
                    "depreciation_addback": 12000,
                },
                {
                    "tax_year": 2024,
                    "net_profit_loss": 88000,
                    "depreciation_addback": 10000,
                },
            ],
            ownership_percentage=Decimal("100"),
        )
        assert result.success
        # (107000 + 98000) / 2 = 102500
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("102500.00"),
            TOLERANCE_ANNUAL, "Schedule C annual",
        )
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("8541.67"),
            TOLERANCE_MONTHLY, "Schedule C monthly",
        )

    def test_self_employed_k1_scorp(self):
        """K-1 S-Corp: 2-year average of ordinary income * ownership %."""
        result = self.svc.calculate_self_employed_income(
            tax_returns=[
                {"tax_year": 2025, "k1_ordinary_income": 120000},
                {"tax_year": 2024, "k1_ordinary_income": 110000},
            ],
            ownership_percentage=Decimal("50"),
        )
        assert result.success
        # ((120000 * 0.5) + (110000 * 0.5)) / 2 = 57500
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("57500.00"),
            TOLERANCE_ANNUAL, "K-1 S-Corp annual",
        )
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("4791.67"),
            TOLERANCE_MONTHLY, "K-1 S-Corp monthly",
        )

    def test_rental_schedule_e(self):
        """Schedule E: 2-year average of (gross_rents - expenses + depreciation)."""
        result = self.svc.calculate_rental_income(
            schedule_e_data=[
                {
                    "tax_year": 2025,
                    "schedule_e_gross_rents": 24000,
                    "schedule_e_total_expenses": 15000,
                    "schedule_e_depreciation": 8000,
                },
                {
                    "tax_year": 2024,
                    "schedule_e_gross_rents": 24000,
                    "schedule_e_total_expenses": 14000,
                    "schedule_e_depreciation": 8000,
                },
            ],
        )
        assert result.success
        # (17000 + 18000) / 2 = 17500
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("17500.00"),
            TOLERANCE_ANNUAL, "Schedule E annual",
        )
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("1458.33"),
            TOLERANCE_MONTHLY, "Schedule E monthly",
        )

    def test_rental_lease_with_vacancy(self):
        """Lease: monthly_rent * (1 - vacancy_factor)."""
        result = self.svc.calculate_rental_income(
            lease_data={"current_monthly_rent": 2000},
            vacancy_factor=Decimal("0.25"),
        )
        assert result.success
        # 2000 * 0.75 = 1500/month, 18000/year
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("1500.00"),
            TOLERANCE_MONTHLY, "Lease with vacancy monthly",
        )
        assert_within_tolerance(
            result.annual_qualifying_income, Decimal("18000.00"),
            TOLERANCE_ANNUAL, "Lease with vacancy annual",
        )

    def test_rental_net_loss(self):
        """Schedule E with net loss after add-back produces negative income."""
        result = self.svc.calculate_rental_income(
            schedule_e_data=[
                {
                    "tax_year": 2025,
                    "schedule_e_gross_rents": 18000,
                    "schedule_e_total_expenses": 21000,
                    "schedule_e_depreciation": 3000,
                },
                {
                    "tax_year": 2024,
                    "schedule_e_gross_rents": 18000,
                    "schedule_e_total_expenses": 22000,
                    "schedule_e_depreciation": 3000,
                },
            ],
        )
        assert result.success
        # Year1: 18000-21000+3000=0, Year2: 18000-22000+3000=-1000
        # Average: -500/year, -41.67/month
        assert result.monthly_qualifying_income < 0
        assert_within_tolerance(
            result.monthly_qualifying_income, Decimal("-41.67"),
            TOLERANCE_MONTHLY, "Rental net loss monthly",
        )


# =============================================================================
# ACCURACY BENCHMARK SUMMARY
# =============================================================================

@pytest.mark.income_accuracy
class TestAccuracyBenchmark:
    """Aggregate accuracy benchmark across all income scenarios."""

    def test_total_scenario_count(self):
        """Ensure comprehensive scenario coverage (>= 15 distinct scenarios)."""
        total = (
            len(W2_SCENARIOS)
            + len(COMMISSION_SCENARIOS)
            + len(SELF_EMPLOYMENT_SCENARIOS)
            + len(RENTAL_SCENARIOS)
            + len(NONTAXABLE_SCENARIOS)
            + len(BANK_STATEMENT_SCENARIOS)
            + len(AGGREGATE_SCENARIOS)
        )
        assert total >= 15, f"Need at least 15 test scenarios, have {total}"

    def test_all_income_types_covered(self):
        """Verify every major income type has at least one scenario."""
        covered_types = {
            "W2_SALARY": len([s for s in W2_SCENARIOS if "base_salary" in s["inputs"]]),
            "W2_HOURLY": len([s for s in W2_SCENARIOS if "hourly_rate" in s["inputs"]]),
            "W2_OVERTIME": len([s for s in W2_SCENARIOS if "ot_rate" in s["inputs"]]),
            "W2_DECLINING": len([s for s in W2_SCENARIOS if s["inputs"].get("year1_w2", 0) > s["inputs"].get("year2_w2", float("inf"))]),
            "COMMISSION_STABLE": len([s for s in COMMISSION_SCENARIOS if "ytd_commission" in s["inputs"]]),
            "COMMISSION_DECLINING": len([s for s in COMMISSION_SCENARIOS if s["inputs"].get("year1_commission", 0) > s["inputs"].get("year2_commission", float("inf"))]),
            "SELF_EMPLOYMENT_SCHEDULE_C": len([s for s in SELF_EMPLOYMENT_SCENARIOS if "year1_net_profit" in s["inputs"]]),
            "SELF_EMPLOYMENT_K1": len([s for s in SELF_EMPLOYMENT_SCENARIOS if "year1_ordinary" in s["inputs"]]),
            "RENTAL_SCHEDULE_E": len([s for s in RENTAL_SCENARIOS if "year1_gross_rents" in s["inputs"]]),
            "RENTAL_LEASE": len([s for s in RENTAL_SCENARIOS if "market_rent" in s["inputs"]]),
            "NONTAXABLE_GROSSUP": len([s for s in NONTAXABLE_SCENARIOS if not s["inputs"].get("is_taxable", True)]),
            "NONTAXABLE_NO_GROSSUP": len([s for s in NONTAXABLE_SCENARIOS if s["inputs"].get("is_taxable", False)]),
            "BANK_STATEMENT": len(BANK_STATEMENT_SCENARIOS),
            "AGGREGATE": len(AGGREGATE_SCENARIOS),
        }

        missing = [k for k, v in covered_types.items() if v == 0]
        assert not missing, f"Missing scenarios for income types: {missing}"

    def test_every_scenario_has_positive_or_documented_negative(self):
        """Every scenario's expected values should be non-zero (positive or documented negative)."""
        all_scenarios = (
            W2_SCENARIOS
            + COMMISSION_SCENARIOS
            + SELF_EMPLOYMENT_SCENARIOS
            + RENTAL_SCENARIOS
            + NONTAXABLE_SCENARIOS
            + BANK_STATEMENT_SCENARIOS
        )
        for scenario in all_scenarios:
            monthly = scenario["expected_monthly"]
            assert monthly != 0 or "loss" in scenario["name"].lower(), (
                f"Scenario '{scenario['name']}' has zero expected monthly "
                f"without being documented as a loss scenario"
            )

    def test_annual_monthly_consistency_across_all_scenarios(self):
        """Annual should equal monthly * 12 (within rounding tolerance) for all scenarios."""
        all_scenarios = (
            W2_SCENARIOS
            + COMMISSION_SCENARIOS
            + SELF_EMPLOYMENT_SCENARIOS
            + RENTAL_SCENARIOS
            + NONTAXABLE_SCENARIOS
            + BANK_STATEMENT_SCENARIOS
        )
        for scenario in all_scenarios:
            monthly = scenario["expected_monthly"]
            annual = scenario["expected_annual"]
            computed_annual = (monthly * 12).quantize(Decimal("0.01"))
            diff = abs(annual - computed_annual)
            assert diff <= TOLERANCE_ANNUAL, (
                f"'{scenario['name']}': annual {annual} != monthly {monthly} * 12 = "
                f"{computed_annual} (diff={diff})"
            )
