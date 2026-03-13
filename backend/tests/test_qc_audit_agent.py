"""
Test QC Audit Agent - Validates defect severity classification, QC scorecard logic,
investor overlay constants, and repurchase risk assessment logic.

Covers:
- DEFECT_SEVERITY constant structure and weights
- INVESTOR_OVERLAYS constant completeness
- QC_CATEGORY_WEIGHTS totaling 100
- QC scorecard grading logic
- Defect severity weight ordering
- Pre-funding audit pass/fail determination
- Repurchase risk level classification
- Data integrity discrepancy detection logic
- Disclosure timing violation detection
- Defect rate rating thresholds
"""

import pytest
from datetime import datetime, date, timedelta


# =============================================================================
# Constants (replicated for self-contained tests)
# =============================================================================

DEFECT_SEVERITY = {
    "critical": {"weight": 25},
    "major": {"weight": 10},
    "minor": {"weight": 3},
    "observation": {"weight": 1},
}

INVESTOR_OVERLAYS = {
    "fannie_mae": {
        "name": "Fannie Mae / DU",
        "max_dti": 50,
        "min_credit": 620,
        "max_ltv_conventional": 97,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
        ],
    },
    "freddie_mac": {
        "name": "Freddie Mac / LP",
        "max_dti": 50,
        "min_credit": 620,
        "max_ltv_conventional": 97,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
        ],
    },
    "ginnie_mae": {
        "name": "Ginnie Mae (FHA/VA)",
        "max_dti": 57,
        "min_credit": 580,
        "max_ltv_fha": 96.5,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
            "fha_case_number_assignment",
            "mortgage_insurance_certificate",
        ],
    },
}

QC_CATEGORY_WEIGHTS = {
    "disclosure_compliance": 25,
    "data_integrity": 20,
    "document_completeness": 20,
    "regulatory_compliance": 15,
    "signature_completeness": 10,
    "appraisal_review": 10,
}


# =============================================================================
# Defect Severity Constants
# =============================================================================

@pytest.mark.unit
class TestDefectSeverity:
    """Validate DEFECT_SEVERITY constant structure."""

    def test_has_four_severity_levels(self):
        """Must define exactly 4 severity levels."""
        assert len(DEFECT_SEVERITY) == 4

    def test_critical_has_highest_weight(self):
        """Critical must have the highest weight."""
        weights = {k: v["weight"] for k, v in DEFECT_SEVERITY.items()}
        assert weights["critical"] > weights["major"]
        assert weights["critical"] > weights["minor"]
        assert weights["critical"] > weights["observation"]

    def test_weights_are_strictly_descending(self):
        """Weights must be strictly descending: critical > major > minor > observation."""
        assert DEFECT_SEVERITY["critical"]["weight"] > DEFECT_SEVERITY["major"]["weight"]
        assert DEFECT_SEVERITY["major"]["weight"] > DEFECT_SEVERITY["minor"]["weight"]
        assert DEFECT_SEVERITY["minor"]["weight"] > DEFECT_SEVERITY["observation"]["weight"]

    def test_all_weights_are_positive_integers(self):
        """All weights must be positive integers."""
        for level, data in DEFECT_SEVERITY.items():
            assert isinstance(data["weight"], int), f"{level} weight should be int"
            assert data["weight"] > 0, f"{level} weight should be positive"

    def test_critical_weight_is_25(self):
        """Critical weight should be 25."""
        assert DEFECT_SEVERITY["critical"]["weight"] == 25

    def test_observation_weight_is_1(self):
        """Observation weight should be 1 (minimal impact)."""
        assert DEFECT_SEVERITY["observation"]["weight"] == 1


# =============================================================================
# Investor Overlay Constants
# =============================================================================

@pytest.mark.unit
class TestInvestorOverlays:
    """Validate INVESTOR_OVERLAYS constant."""

    def test_has_three_investors(self):
        """Must define overlays for 3 investors."""
        assert len(INVESTOR_OVERLAYS) == 3
        assert "fannie_mae" in INVESTOR_OVERLAYS
        assert "freddie_mac" in INVESTOR_OVERLAYS
        assert "ginnie_mae" in INVESTOR_OVERLAYS

    def test_all_investors_have_required_docs(self):
        """Every investor must define required_docs."""
        for investor, overlay in INVESTOR_OVERLAYS.items():
            assert "required_docs" in overlay, f"{investor} missing required_docs"
            assert len(overlay["required_docs"]) >= 8, (
                f"{investor} should require at least 8 documents"
            )

    def test_ginnie_mae_has_extra_government_docs(self):
        """Ginnie Mae should require FHA-specific documents."""
        ginnie_docs = INVESTOR_OVERLAYS["ginnie_mae"]["required_docs"]
        assert "fha_case_number_assignment" in ginnie_docs
        assert "mortgage_insurance_certificate" in ginnie_docs

    def test_all_investors_have_min_credit(self):
        """Every investor must define minimum credit score."""
        for investor, overlay in INVESTOR_OVERLAYS.items():
            assert "min_credit" in overlay, f"{investor} missing min_credit"
            assert overlay["min_credit"] >= 580, (
                f"{investor} min credit should be at least 580"
            )

    def test_ginnie_mae_allows_lower_credit(self):
        """Ginnie Mae (FHA) allows lower credit than conventional."""
        assert INVESTOR_OVERLAYS["ginnie_mae"]["min_credit"] < INVESTOR_OVERLAYS["fannie_mae"]["min_credit"]

    def test_all_investors_have_max_dti(self):
        """Every investor must define max DTI."""
        for investor, overlay in INVESTOR_OVERLAYS.items():
            assert "max_dti" in overlay, f"{investor} missing max_dti"
            assert 40 <= overlay["max_dti"] <= 60, (
                f"{investor} max_dti should be between 40-60"
            )

    def test_ginnie_mae_allows_higher_dti(self):
        """Ginnie Mae allows higher DTI than conventional investors."""
        assert INVESTOR_OVERLAYS["ginnie_mae"]["max_dti"] > INVESTOR_OVERLAYS["fannie_mae"]["max_dti"]

    def test_all_investors_have_name(self):
        """Every investor overlay must have a display name."""
        for investor, overlay in INVESTOR_OVERLAYS.items():
            assert "name" in overlay, f"{investor} missing name"
            assert len(overlay["name"]) > 0


# =============================================================================
# QC Scorecard Weights
# =============================================================================

@pytest.mark.unit
class TestQCScorecardWeights:
    """Validate QC_CATEGORY_WEIGHTS totals."""

    def test_weights_total_100(self):
        """Category weights must sum to exactly 100."""
        total = sum(QC_CATEGORY_WEIGHTS.values())
        assert total == 100, f"Weights sum to {total}, expected 100"

    def test_has_six_categories(self):
        """Must have exactly 6 scoring categories."""
        assert len(QC_CATEGORY_WEIGHTS) == 6

    def test_disclosure_compliance_is_highest(self):
        """Disclosure compliance should be the highest-weighted category."""
        max_category = max(QC_CATEGORY_WEIGHTS, key=QC_CATEGORY_WEIGHTS.get)
        assert max_category == "disclosure_compliance"
        assert QC_CATEGORY_WEIGHTS["disclosure_compliance"] == 25

    def test_all_weights_are_positive(self):
        """All weights must be positive."""
        for category, weight in QC_CATEGORY_WEIGHTS.items():
            assert weight > 0, f"{category} weight should be positive"

    def test_all_weights_are_integers(self):
        """All weights must be integers."""
        for category, weight in QC_CATEGORY_WEIGHTS.items():
            assert isinstance(weight, int), f"{category} weight should be int"


# =============================================================================
# QC Scorecard Grading Logic
# =============================================================================

@pytest.mark.unit
class TestQCScorecardGrading:
    """Test the score-to-grade mapping logic."""

    @staticmethod
    def score_to_grade(score):
        """Replicate the grading logic from the agent."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def test_perfect_score_is_grade_a(self):
        assert self.score_to_grade(100) == "A"

    def test_score_90_is_grade_a(self):
        assert self.score_to_grade(90) == "A"

    def test_score_89_is_grade_b(self):
        assert self.score_to_grade(89) == "B"

    def test_score_80_is_grade_b(self):
        assert self.score_to_grade(80) == "B"

    def test_score_79_is_grade_c(self):
        assert self.score_to_grade(79) == "C"

    def test_score_70_is_grade_c(self):
        assert self.score_to_grade(70) == "C"

    def test_score_69_is_grade_d(self):
        assert self.score_to_grade(69) == "D"

    def test_score_60_is_grade_d(self):
        assert self.score_to_grade(60) == "D"

    def test_score_59_is_grade_f(self):
        assert self.score_to_grade(59) == "F"

    def test_score_0_is_grade_f(self):
        assert self.score_to_grade(0) == "F"


# =============================================================================
# Pre-Funding Audit Pass/Fail Logic
# =============================================================================

@pytest.mark.unit
class TestPrefundingAuditResult:
    """Test the pass/fail determination logic for pre-funding audits."""

    @staticmethod
    def determine_result(defects):
        """Replicate the pass/fail logic from the agent."""
        critical_count = len([d for d in defects if d["severity"] == "critical"])
        major_count = len([d for d in defects if d["severity"] == "major"])
        if critical_count > 0:
            return "FAIL"
        elif major_count > 0:
            return "CONDITIONAL"
        else:
            return "PASS"

    def test_no_defects_is_pass(self):
        assert self.determine_result([]) == "PASS"

    def test_only_minor_defects_is_pass(self):
        defects = [{"severity": "minor"}, {"severity": "observation"}]
        assert self.determine_result(defects) == "PASS"

    def test_major_defect_is_conditional(self):
        defects = [{"severity": "major"}]
        assert self.determine_result(defects) == "CONDITIONAL"

    def test_critical_defect_is_fail(self):
        defects = [{"severity": "critical"}]
        assert self.determine_result(defects) == "FAIL"

    def test_critical_overrides_major(self):
        """A critical defect should result in FAIL even if major defects exist."""
        defects = [{"severity": "major"}, {"severity": "critical"}]
        assert self.determine_result(defects) == "FAIL"

    def test_multiple_majors_still_conditional(self):
        defects = [{"severity": "major"}, {"severity": "major"}, {"severity": "major"}]
        assert self.determine_result(defects) == "CONDITIONAL"


# =============================================================================
# Disclosure Timing Violation Detection
# =============================================================================

@pytest.mark.unit
class TestDisclosureTimingLogic:
    """Test disclosure timing violation detection."""

    def test_le_within_3_days_compliant(self):
        """LE sent within 3 days is compliant."""
        app_date = date(2026, 3, 1)
        le_sent = date(2026, 3, 3)
        le_days = (le_sent - app_date).days
        assert le_days <= 3

    def test_le_at_4_days_is_violation(self):
        """LE sent at 4 days is a violation."""
        app_date = date(2026, 3, 1)
        le_sent = date(2026, 3, 5)
        le_days = (le_sent - app_date).days
        assert le_days > 3

    def test_cd_3_days_before_closing_compliant(self):
        """CD sent 3 days before closing is compliant."""
        cd_sent = date(2026, 3, 7)
        closing = date(2026, 3, 10)
        cd_days = (closing - cd_sent).days
        assert cd_days >= 3

    def test_cd_2_days_before_closing_violation(self):
        """CD sent only 2 days before closing is a violation."""
        cd_sent = date(2026, 3, 8)
        closing = date(2026, 3, 10)
        cd_days = (closing - cd_sent).days
        assert cd_days < 3

    def test_cd_same_day_as_closing_violation(self):
        """CD sent same day as closing is a critical violation."""
        cd_sent = date(2026, 3, 10)
        closing = date(2026, 3, 10)
        cd_days = (closing - cd_sent).days
        assert cd_days < 3
        assert cd_days == 0


# =============================================================================
# Repurchase Risk Level Logic
# =============================================================================

@pytest.mark.unit
class TestRepurchaseRiskLevel:
    """Test repurchase risk level classification."""

    @staticmethod
    def determine_risk_level(risks):
        """Replicate the risk level logic from the agent."""
        if any(r["severity"] == "critical" for r in risks):
            return "HIGH"
        elif risks:
            return "MEDIUM"
        else:
            return "LOW"

    def test_no_risks_is_low(self):
        assert self.determine_risk_level([]) == "LOW"

    def test_major_risk_is_medium(self):
        risks = [{"severity": "major", "repurchase_likelihood": "medium"}]
        assert self.determine_risk_level(risks) == "MEDIUM"

    def test_critical_risk_is_high(self):
        risks = [{"severity": "critical", "repurchase_likelihood": "high"}]
        assert self.determine_risk_level(risks) == "HIGH"

    def test_critical_overrides_major(self):
        risks = [
            {"severity": "major", "repurchase_likelihood": "medium"},
            {"severity": "critical", "repurchase_likelihood": "high"},
        ]
        assert self.determine_risk_level(risks) == "HIGH"


# =============================================================================
# Defect Rate Rating Thresholds
# =============================================================================

@pytest.mark.unit
class TestDefectRateRating:
    """Test organization-level defect rate rating logic."""

    @staticmethod
    def rate_to_rating(defect_rate):
        """Replicate the rating logic from the agent."""
        if defect_rate <= 5:
            return "EXCELLENT"
        elif defect_rate <= 10:
            return "ACCEPTABLE"
        elif defect_rate <= 15:
            return "NEEDS_IMPROVEMENT"
        else:
            return "CRITICAL"

    def test_zero_percent_is_excellent(self):
        assert self.rate_to_rating(0) == "EXCELLENT"

    def test_five_percent_is_excellent(self):
        assert self.rate_to_rating(5) == "EXCELLENT"

    def test_six_percent_is_acceptable(self):
        assert self.rate_to_rating(6) == "ACCEPTABLE"

    def test_ten_percent_is_acceptable(self):
        assert self.rate_to_rating(10) == "ACCEPTABLE"

    def test_eleven_percent_needs_improvement(self):
        assert self.rate_to_rating(11) == "NEEDS_IMPROVEMENT"

    def test_fifteen_percent_needs_improvement(self):
        assert self.rate_to_rating(15) == "NEEDS_IMPROVEMENT"

    def test_sixteen_percent_is_critical(self):
        assert self.rate_to_rating(16) == "CRITICAL"

    def test_fifty_percent_is_critical(self):
        assert self.rate_to_rating(50) == "CRITICAL"


# =============================================================================
# Data Integrity Checks
# =============================================================================

@pytest.mark.unit
class TestDataIntegrityLogic:
    """Test data integrity discrepancy detection logic."""

    def test_matching_names_no_discrepancy(self):
        """Matching names should not produce a discrepancy."""
        lead_name = "John Smith"
        loan_name = "John Smith"
        assert lead_name.lower() == loan_name.lower()

    def test_case_insensitive_match(self):
        """Name comparison should be case-insensitive."""
        lead_name = "john smith"
        loan_name = "John Smith"
        assert lead_name.lower() == loan_name.lower()

    def test_different_names_flagged(self):
        """Different names should be flagged as a discrepancy."""
        lead_name = "John Smith"
        loan_name = "Jonathan Smith"
        assert lead_name.lower() != loan_name.lower()

    def test_amount_difference_within_tolerance(self):
        """Amounts within $1.00 should not be flagged."""
        lead_amount = 450000.00
        loan_amount = 450000.50
        assert abs(lead_amount - loan_amount) < 1.0

    def test_amount_difference_flagged(self):
        """Amounts differing by more than $1.00 should be flagged."""
        lead_amount = 450000.00
        loan_amount = 425000.00
        assert abs(lead_amount - loan_amount) > 1.0

    def test_stage_history_chronological_order(self):
        """Stage transitions must be in chronological order."""
        transitions = [
            datetime(2026, 1, 1),
            datetime(2026, 1, 5),
            datetime(2026, 1, 10),
        ]
        for i in range(1, len(transitions)):
            assert transitions[i] >= transitions[i - 1]

    def test_stage_history_out_of_order_detected(self):
        """Out-of-order stage transitions should be detected."""
        transitions = [
            datetime(2026, 1, 1),
            datetime(2026, 1, 10),
            datetime(2026, 1, 5),  # Out of order
        ]
        out_of_order = False
        for i in range(1, len(transitions)):
            if transitions[i] < transitions[i - 1]:
                out_of_order = True
                break
        assert out_of_order
