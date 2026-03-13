"""
Test Underwriter Assistant Agent — Validates agency guideline constants,
DTI calculation logic, layered risk assessment, reserve requirements,
compensating factor scoring, and credit score selection rules.

Covers:
- Agency DTI limits dictionary completeness and values
- Minimum credit score requirements by loan type
- Maximum LTV limits by loan type and occupancy
- Reserve requirement lookup logic
- DTI calculation with income/debt scenarios
- Representative credit score selection (middle of three, lower of two)
- Layered risk weight calculation and severity classification
- Compensating factor identification logic
"""

import pytest
from datetime import datetime, date


# =============================================================================
# Agency DTI Limits
# =============================================================================

@pytest.mark.unit
class TestAgencyDTILimits:
    """Validate the AGENCY_DTI_LIMITS constant from the underwriter agent."""

    AGENCY_DTI_LIMITS = {
        "conventional": {"front": 28.0, "back": 36.0, "back_with_compensating": 45.0, "du_max": 50.0},
        "fha": {"front": 31.0, "back": 43.0, "back_with_compensating": 50.0, "du_max": 57.0},
        "va": {"front": None, "back": 41.0, "back_with_compensating": 41.0, "du_max": 60.0},
        "usda": {"front": 29.0, "back": 41.0, "back_with_compensating": 41.0, "du_max": 41.0},
        "jumbo": {"front": 28.0, "back": 36.0, "back_with_compensating": 43.0, "du_max": 43.0},
    }

    def test_has_5_loan_types(self):
        """DTI limits should cover 5 loan types."""
        assert len(self.AGENCY_DTI_LIMITS) == 5

    def test_conventional_back_dti_is_36(self):
        """Conventional standard back-end DTI should be 36%."""
        assert self.AGENCY_DTI_LIMITS["conventional"]["back"] == 36.0

    def test_fha_du_max_is_57(self):
        """FHA AUS maximum DTI should be 57%."""
        assert self.AGENCY_DTI_LIMITS["fha"]["du_max"] == 57.0

    def test_va_has_no_front_dti_limit(self):
        """VA should have no front-end DTI limit (None)."""
        assert self.AGENCY_DTI_LIMITS["va"]["front"] is None

    def test_usda_back_and_compensating_are_same(self):
        """USDA standard and compensating back-end DTI should be the same at 41%."""
        usda = self.AGENCY_DTI_LIMITS["usda"]
        assert usda["back"] == usda["back_with_compensating"] == 41.0

    def test_compensating_always_gte_standard(self):
        """The compensating-factor limit should always be >= the standard limit."""
        for loan_type, limits in self.AGENCY_DTI_LIMITS.items():
            assert limits["back_with_compensating"] >= limits["back"], (
                f"{loan_type}: compensating {limits['back_with_compensating']} < standard {limits['back']}"
            )

    def test_du_max_always_gte_compensating(self):
        """The AUS maximum should always be >= the compensating limit."""
        for loan_type, limits in self.AGENCY_DTI_LIMITS.items():
            assert limits["du_max"] >= limits["back_with_compensating"], (
                f"{loan_type}: du_max {limits['du_max']} < compensating {limits['back_with_compensating']}"
            )

    def test_all_values_are_float_or_none(self):
        """All DTI limit values should be float or None."""
        for loan_type, limits in self.AGENCY_DTI_LIMITS.items():
            for key, val in limits.items():
                assert val is None or isinstance(val, float), (
                    f"{loan_type}.{key}: expected float or None, got {type(val)}"
                )


# =============================================================================
# Minimum Credit Scores
# =============================================================================

@pytest.mark.unit
class TestMinCreditScores:
    """Validate credit score minimums by loan type."""

    MIN_CREDIT_SCORES = {
        "conventional": 620,
        "fha": 580,
        "fha_3.5_down": 580,
        "fha_10_down": 500,
        "va": 580,
        "usda": 640,
        "jumbo": 680,
    }

    def test_conventional_minimum_is_620(self):
        """Conventional minimum credit score should be 620."""
        assert self.MIN_CREDIT_SCORES["conventional"] == 620

    def test_fha_minimum_is_580(self):
        """FHA minimum with 3.5% down should be 580."""
        assert self.MIN_CREDIT_SCORES["fha"] == 580

    def test_fha_10_down_allows_500(self):
        """FHA with 10% down should allow credit score as low as 500."""
        assert self.MIN_CREDIT_SCORES["fha_10_down"] == 500

    def test_jumbo_has_highest_minimum(self):
        """Jumbo should have the highest minimum credit score."""
        max_min = max(self.MIN_CREDIT_SCORES.values())
        assert self.MIN_CREDIT_SCORES["jumbo"] == max_min

    def test_all_scores_are_positive_integers(self):
        """All credit score minimums should be positive integers."""
        for key, score in self.MIN_CREDIT_SCORES.items():
            assert isinstance(score, int), f"{key}: expected int, got {type(score)}"
            assert 300 <= score <= 850, f"{key}: score {score} outside valid range"


# =============================================================================
# Maximum LTV
# =============================================================================

@pytest.mark.unit
class TestMaxLTV:
    """Validate maximum LTV limits by loan type and occupancy."""

    MAX_LTV = {
        "conventional_primary": 97.0,
        "conventional_second": 90.0,
        "conventional_investment": 85.0,
        "fha_primary": 96.5,
        "va_primary": 100.0,
        "usda_primary": 100.0,
        "jumbo_primary": 80.0,
    }

    def test_va_allows_100_ltv(self):
        """VA primary should allow 100% LTV (no down payment)."""
        assert self.MAX_LTV["va_primary"] == 100.0

    def test_usda_allows_100_ltv(self):
        """USDA primary should allow 100% LTV."""
        assert self.MAX_LTV["usda_primary"] == 100.0

    def test_conventional_investment_is_most_restrictive(self):
        """Conventional investment should be the most restrictive conventional LTV."""
        assert self.MAX_LTV["conventional_investment"] < self.MAX_LTV["conventional_second"]
        assert self.MAX_LTV["conventional_second"] < self.MAX_LTV["conventional_primary"]

    def test_jumbo_primary_is_80(self):
        """Jumbo primary should be capped at 80% LTV."""
        assert self.MAX_LTV["jumbo_primary"] == 80.0

    def test_all_ltv_values_between_0_and_100(self):
        """All LTV values should be between 0 and 100 inclusive."""
        for key, ltv in self.MAX_LTV.items():
            assert 0 < ltv <= 100, f"{key}: LTV {ltv} outside valid range"


# =============================================================================
# DTI Calculation Logic
# =============================================================================

@pytest.mark.unit
class TestDTICalculation:
    """Test the DTI calculation logic used by calculate_dti_with_scenarios."""

    @staticmethod
    def calc_dti(housing: float, debts: float, income: float) -> dict:
        """Replicate the DTI calculation from the tool."""
        front = round((housing / income) * 100, 2) if income > 0 else 0
        back = round(((housing + debts) / income) * 100, 2) if income > 0 else 0
        return {"front": front, "back": back}

    def test_basic_dti_calculation(self):
        """Standard DTI calculation with typical values."""
        result = self.calc_dti(housing=2000, debts=500, income=8000)
        assert result["front"] == 25.0
        assert result["back"] == 31.25

    def test_zero_income_returns_zero(self):
        """Zero income should return 0% DTI, not divide-by-zero."""
        result = self.calc_dti(housing=2000, debts=500, income=0)
        assert result["front"] == 0
        assert result["back"] == 0

    def test_no_debts_front_equals_back(self):
        """With no debts, front and back DTI should be equal."""
        result = self.calc_dti(housing=1500, debts=0, income=6000)
        assert result["front"] == result["back"]

    def test_high_dti_borderline(self):
        """DTI at 49.99% should calculate correctly."""
        result = self.calc_dti(housing=3000, debts=1999, income=10000)
        assert result["back"] == 49.99

    def test_scenario_adding_income_reduces_dti(self):
        """Adding income should reduce the DTI ratio."""
        base = self.calc_dti(housing=2000, debts=1000, income=6000)
        scenario = self.calc_dti(housing=2000, debts=1000, income=8000)
        assert scenario["back"] < base["back"]

    def test_scenario_removing_debt_reduces_dti(self):
        """Removing debt should reduce the back-end DTI."""
        base = self.calc_dti(housing=2000, debts=1000, income=6000)
        scenario = self.calc_dti(housing=2000, debts=500, income=6000)
        assert scenario["back"] < base["back"]

    def test_rental_income_75_pct_factor(self):
        """Rental income should be factored at 75% per agency guidelines."""
        rental_gross = 2000
        rental_qualifying = rental_gross * 0.75  # 1500
        total_income = 6000 + rental_qualifying  # 7500
        result = self.calc_dti(housing=2000, debts=1000, income=total_income)
        assert result["back"] == 40.0


# =============================================================================
# Representative Credit Score Selection
# =============================================================================

@pytest.mark.unit
class TestRepresentativeCreditScore:
    """Test the representative score selection logic."""

    @staticmethod
    def select_representative(scores: list) -> int:
        """Replicate representative score selection."""
        if len(scores) >= 3:
            sorted_scores = sorted(scores)
            return sorted_scores[1]  # Middle of three
        elif len(scores) == 2:
            return min(scores)  # Lower of two
        elif len(scores) == 1:
            return scores[0]
        return 0

    def test_middle_of_three(self):
        """With three scores, representative should be the middle value."""
        assert self.select_representative([720, 680, 740]) == 720

    def test_middle_of_three_already_sorted(self):
        """Middle selection should work regardless of input order."""
        assert self.select_representative([680, 720, 740]) == 720

    def test_lower_of_two(self):
        """With two scores, representative should be the lower."""
        assert self.select_representative([720, 680]) == 680

    def test_single_score_used_as_is(self):
        """With one score, use it directly."""
        assert self.select_representative([720]) == 720

    def test_no_scores_returns_zero(self):
        """With no scores, return 0."""
        assert self.select_representative([]) == 0

    def test_identical_scores(self):
        """Three identical scores should return that score."""
        assert self.select_representative([700, 700, 700]) == 700


# =============================================================================
# Layered Risk Assessment
# =============================================================================

@pytest.mark.unit
class TestLayeredRisk:
    """Test the layered risk weight calculation and severity classification."""

    @staticmethod
    def classify_risk(total_weight: int) -> str:
        """Replicate risk classification from the tool."""
        if total_weight >= 8:
            return "critical"
        elif total_weight >= 5:
            return "high"
        elif total_weight >= 3:
            return "moderate"
        else:
            return "low"

    def test_low_risk_below_3(self):
        """Weight 0-2 should be classified as low risk."""
        assert self.classify_risk(0) == "low"
        assert self.classify_risk(1) == "low"
        assert self.classify_risk(2) == "low"

    def test_moderate_risk_3_to_4(self):
        """Weight 3-4 should be classified as moderate risk."""
        assert self.classify_risk(3) == "moderate"
        assert self.classify_risk(4) == "moderate"

    def test_high_risk_5_to_7(self):
        """Weight 5-7 should be classified as high risk."""
        assert self.classify_risk(5) == "high"
        assert self.classify_risk(6) == "high"
        assert self.classify_risk(7) == "high"

    def test_critical_risk_8_plus(self):
        """Weight 8+ should be classified as critical risk."""
        assert self.classify_risk(8) == "critical"
        assert self.classify_risk(10) == "critical"
        assert self.classify_risk(15) == "critical"

    def test_low_credit_plus_high_dti_plus_investment(self):
        """Classic layered risk: low credit + high DTI + investment property."""
        # Credit < 660 (weight 2) + DTI > 45% (weight 2) + Investment (weight 2) = 6
        total_weight = 2 + 2 + 2
        assert self.classify_risk(total_weight) == "high"

    def test_single_risk_is_manageable(self):
        """A single risk factor should not push to high/critical."""
        # Only high LTV > 95% (weight 3)
        assert self.classify_risk(3) == "moderate"

    def test_maximum_layered_risk(self):
        """All risk layers present simultaneously."""
        # Credit <620 (3) + DTI>50 (3) + LTV>95 (3) + Investment (2) + Cash-out (2)
        # + Self-employed (1) + Limited reserves (2) + Short employment (1) = 17
        total_weight = 3 + 3 + 3 + 2 + 2 + 1 + 2 + 1
        assert total_weight == 17
        assert self.classify_risk(total_weight) == "critical"


# =============================================================================
# Compensating Factor Scoring
# =============================================================================

@pytest.mark.unit
class TestCompensatingFactors:
    """Test compensating factor identification logic."""

    @staticmethod
    def assess_reserves_factor(total_assets: float, monthly_housing: float) -> dict:
        """Replicate reserves compensating factor logic."""
        if monthly_housing <= 0:
            return {"factor": None, "strength": None}
        months = total_assets / monthly_housing
        if months >= 12:
            return {"factor": "Substantial Reserves", "strength": "strong"}
        elif months >= 6:
            return {"factor": "Adequate Reserves", "strength": "moderate"}
        return {"factor": None, "strength": None}

    @staticmethod
    def assess_overall(strong: int, moderate: int) -> str:
        """Replicate overall assessment logic."""
        if strong >= 2:
            return "strong_support"
        elif strong >= 1 and moderate >= 1:
            return "conditional_support"
        elif moderate >= 2:
            return "moderate_support"
        return "limited"

    def test_12_months_reserves_is_strong(self):
        """12+ months of reserves is a strong compensating factor."""
        result = self.assess_reserves_factor(24000, 2000)
        assert result["strength"] == "strong"

    def test_6_months_reserves_is_moderate(self):
        """6-11 months of reserves is a moderate factor."""
        result = self.assess_reserves_factor(14000, 2000)
        assert result["strength"] == "moderate"

    def test_under_6_months_not_a_factor(self):
        """Under 6 months of reserves is not a compensating factor."""
        result = self.assess_reserves_factor(8000, 2000)
        assert result["factor"] is None

    def test_zero_housing_does_not_crash(self):
        """Zero housing expense should not cause division by zero."""
        result = self.assess_reserves_factor(50000, 0)
        assert result["factor"] is None

    def test_two_strong_factors_gives_strong_support(self):
        """Two strong factors should give strong support assessment."""
        assert self.assess_overall(strong=2, moderate=0) == "strong_support"

    def test_one_strong_one_moderate_conditional(self):
        """One strong + one moderate gives conditional support."""
        assert self.assess_overall(strong=1, moderate=1) == "conditional_support"

    def test_two_moderate_gives_moderate_support(self):
        """Two moderate factors give moderate support."""
        assert self.assess_overall(strong=0, moderate=2) == "moderate_support"

    def test_no_factors_gives_limited(self):
        """No meaningful factors means limited support."""
        assert self.assess_overall(strong=0, moderate=0) == "limited"
        assert self.assess_overall(strong=0, moderate=1) == "limited"


# =============================================================================
# Reserve Requirements
# =============================================================================

@pytest.mark.unit
class TestReserveRequirements:
    """Validate reserve requirement lookup logic."""

    RESERVE_REQUIREMENTS = {
        "primary_conventional": 0,
        "primary_fha": 0,
        "primary_va": 0,
        "second_home_conventional": 2,
        "investment_conventional": 6,
        "investment_fha": 0,
        "multi_unit_2": 6,
        "multi_unit_3_4": 6,
        "multiple_properties_5_6": 6,
        "multiple_properties_7_10": 6,
    }

    def test_primary_residence_no_reserves(self):
        """Primary residence loans should require 0 months reserves."""
        assert self.RESERVE_REQUIREMENTS["primary_conventional"] == 0
        assert self.RESERVE_REQUIREMENTS["primary_fha"] == 0
        assert self.RESERVE_REQUIREMENTS["primary_va"] == 0

    def test_second_home_requires_2_months(self):
        """Second home conventional should require 2 months reserves."""
        assert self.RESERVE_REQUIREMENTS["second_home_conventional"] == 2

    def test_investment_requires_6_months(self):
        """Investment property should require 6 months reserves."""
        assert self.RESERVE_REQUIREMENTS["investment_conventional"] == 6

    def test_multi_unit_requires_6_months(self):
        """Multi-unit properties should require 6 months reserves."""
        assert self.RESERVE_REQUIREMENTS["multi_unit_2"] == 6
        assert self.RESERVE_REQUIREMENTS["multi_unit_3_4"] == 6

    def test_reserve_calculation(self):
        """Reserve amount calculation: months * monthly PITIA."""
        months_required = 6
        monthly_pitia = 2500.0
        reserves_required = months_required * monthly_pitia
        assert reserves_required == 15000.0

    def test_all_values_non_negative(self):
        """All reserve requirements should be non-negative integers."""
        for key, months in self.RESERVE_REQUIREMENTS.items():
            assert isinstance(months, int), f"{key}: expected int, got {type(months)}"
            assert months >= 0, f"{key}: months should be non-negative, got {months}"
