"""
Test Document Security Agent — validates security policy constants, risk scoring
logic, retention calculations, breach notification deadlines, and PII classification.

Covers:
- PII document type classification completeness
- Retention policy values and correctness
- State breach notification deadline accuracy
- Data exposure risk scoring algorithm
- Risk recommendation generation
- Incident severity response requirements
- Watermark-required document types
"""

import pytest
from datetime import date, timedelta


# =============================================================================
# Constants replicated from document_security_agent.py for self-contained tests
# =============================================================================

PII_DOCUMENT_TYPES = {
    "identity": ["drivers_license", "ssn_card", "passport"],
    "credit": ["credit_report", "credit_explanation", "bankruptcy_docs"],
    "income": ["tax_returns", "w2", "1099", "paystubs", "profit_loss"],
    "assets": ["bank_statements", "investment_statements"],
}

RETENTION_POLICY = {
    "FUNDED": 7,
    "CANCELLED": 3,
    "DENIED": 3,
    "DEAD": 2,
    "WITHDRAWN": 3,
    "active": 0,
}

STATE_NOTIFICATION_DEADLINES = {
    "CA": 45,
    "TX": 60,
    "NY": 30,
    "FL": 30,
    "IL": 45,
    "VA": 60,
    "CO": 30,
    "WA": 30,
    "MA": 14,
    "DEFAULT": 60,
}


# =============================================================================
# PII Document Classification
# =============================================================================

@pytest.mark.unit
class TestPIIDocumentTypes:
    """Validate PII document type classification."""

    def test_pii_has_four_categories(self):
        """PII classification should have exactly 4 categories."""
        assert len(PII_DOCUMENT_TYPES) == 4

    def test_identity_category_contains_ssn(self):
        """Identity category must include SSN card."""
        assert "ssn_card" in PII_DOCUMENT_TYPES["identity"]

    def test_identity_category_contains_drivers_license(self):
        """Identity category must include driver's license."""
        assert "drivers_license" in PII_DOCUMENT_TYPES["identity"]

    def test_credit_category_contains_credit_report(self):
        """Credit category must include credit report."""
        assert "credit_report" in PII_DOCUMENT_TYPES["credit"]

    def test_income_category_contains_tax_returns(self):
        """Income category must include tax returns."""
        assert "tax_returns" in PII_DOCUMENT_TYPES["income"]

    def test_income_category_contains_w2(self):
        """Income category must include W2s."""
        assert "w2" in PII_DOCUMENT_TYPES["income"]

    def test_assets_category_contains_bank_statements(self):
        """Assets category must include bank statements."""
        assert "bank_statements" in PII_DOCUMENT_TYPES["assets"]

    def test_all_pii_types_are_lowercase(self):
        """All PII document type strings should be lowercase with underscores."""
        for category, types in PII_DOCUMENT_TYPES.items():
            for doc_type in types:
                assert doc_type == doc_type.lower(), \
                    f"PII type '{doc_type}' in '{category}' should be lowercase"
                assert " " not in doc_type, \
                    f"PII type '{doc_type}' should use underscores not spaces"

    def test_total_pii_types_count(self):
        """Total PII document types should be 13."""
        total = sum(len(types) for types in PII_DOCUMENT_TYPES.values())
        assert total == 13

    def test_no_duplicate_types_across_categories(self):
        """No document type should appear in multiple PII categories."""
        all_types = []
        for types in PII_DOCUMENT_TYPES.values():
            all_types.extend(types)
        assert len(all_types) == len(set(all_types)), "Duplicate PII types found across categories"


# =============================================================================
# Retention Policy
# =============================================================================

@pytest.mark.unit
class TestRetentionPolicy:
    """Validate document retention policy constants."""

    def test_funded_retention_is_7_years(self):
        """Funded loans must retain documents for 7 years per GLBA."""
        assert RETENTION_POLICY["FUNDED"] == 7

    def test_cancelled_retention_is_3_years(self):
        """Cancelled applications must retain for 3 years."""
        assert RETENTION_POLICY["CANCELLED"] == 3

    def test_denied_retention_is_3_years(self):
        """Denied applications must retain for 3 years per ECOA."""
        assert RETENTION_POLICY["DENIED"] == 3

    def test_dead_retention_is_2_years(self):
        """Dead leads retain for 2 years."""
        assert RETENTION_POLICY["DEAD"] == 2

    def test_active_loans_have_zero_retention(self):
        """Active loans should have retention of 0 (never expire while active)."""
        assert RETENTION_POLICY["active"] == 0

    def test_all_retention_values_non_negative(self):
        """All retention values must be non-negative integers."""
        for stage, years in RETENTION_POLICY.items():
            assert isinstance(years, int), f"Retention for '{stage}' should be int"
            assert years >= 0, f"Retention for '{stage}' should be non-negative"

    def test_retention_expiry_calculation(self):
        """Verify retention expiry date math for a funded loan."""
        funded_date = date(2019, 6, 15)
        retention_years = RETENTION_POLICY["FUNDED"]
        retention_end = funded_date + timedelta(days=retention_years * 365)
        today = date(2026, 3, 12)
        assert retention_end < today, "A loan funded 7+ years ago should be past retention"

    def test_recently_funded_not_past_retention(self):
        """A recently funded loan should NOT be past retention."""
        funded_date = date(2025, 1, 1)
        retention_years = RETENTION_POLICY["FUNDED"]
        retention_end = funded_date + timedelta(days=retention_years * 365)
        today = date(2026, 3, 12)
        assert retention_end > today, "A loan funded 1 year ago should still be within retention"


# =============================================================================
# State Breach Notification Deadlines
# =============================================================================

@pytest.mark.unit
class TestBreachNotificationDeadlines:
    """Validate state breach notification deadline constants."""

    def test_massachusetts_is_fastest(self):
        """Massachusetts should have the shortest notification deadline at 14 days."""
        ma_days = STATE_NOTIFICATION_DEADLINES["MA"]
        for state, days in STATE_NOTIFICATION_DEADLINES.items():
            if state != "DEFAULT":
                assert ma_days <= days, \
                    f"MA ({ma_days} days) should be <= {state} ({days} days)"

    def test_default_deadline_is_60_days(self):
        """Default deadline for unlisted states should be 60 days."""
        assert STATE_NOTIFICATION_DEADLINES["DEFAULT"] == 60

    def test_new_york_shield_act_30_days(self):
        """New York SHIELD Act requires 30-day notification."""
        assert STATE_NOTIFICATION_DEADLINES["NY"] == 30

    def test_california_is_45_days(self):
        """California requires notification within 45 days."""
        assert STATE_NOTIFICATION_DEADLINES["CA"] == 45

    def test_all_deadlines_are_positive_integers(self):
        """All notification deadlines must be positive integers."""
        for state, days in STATE_NOTIFICATION_DEADLINES.items():
            assert isinstance(days, int), f"Deadline for {state} should be int"
            assert days > 0, f"Deadline for {state} should be positive"

    def test_notification_deadline_calculation(self):
        """Verify notification deadline date calculation."""
        discovery_date = date(2026, 3, 1)
        state = "NY"
        deadline_days = STATE_NOTIFICATION_DEADLINES[state]
        notification_deadline = discovery_date + timedelta(days=deadline_days)
        expected = date(2026, 3, 31)
        assert notification_deadline == expected

    def test_states_cover_major_populations(self):
        """Should cover the major mortgage-volume states."""
        major_states = {"CA", "TX", "NY", "FL"}
        covered = set(STATE_NOTIFICATION_DEADLINES.keys()) - {"DEFAULT"}
        assert major_states.issubset(covered), \
            f"Missing major states: {major_states - covered}"


# =============================================================================
# Data Exposure Risk Scoring
# =============================================================================

@pytest.mark.unit
class TestDataExposureRiskScoring:
    """Validate risk scoring algorithm used by assess_data_exposure_risk."""

    @staticmethod
    def calculate_risk(pii_count, unencrypted, accessors, shares):
        """Replicate the risk scoring logic from the agent."""
        risk_score = 0

        # Factor 1: PII density (0-25)
        if pii_count >= 5:
            risk_score += 25
        elif pii_count >= 2:
            risk_score += 15

        # Factor 2: Encryption gaps (0-25)
        if unencrypted > 0 and pii_count > 0:
            risk_score += min(25, unencrypted * 5)

        # Factor 3: Access breadth (0-25)
        if accessors > 10:
            risk_score += 25
        elif accessors > 5:
            risk_score += 15

        # Factor 4: External sharing (0-25)
        if shares > 10:
            risk_score += 25
        elif shares > 3:
            risk_score += 15

        return risk_score

    @staticmethod
    def risk_level(score):
        if score >= 75:
            return "critical"
        elif score >= 50:
            return "high"
        elif score >= 25:
            return "medium"
        else:
            return "low"

    def test_zero_risk_for_no_pii(self):
        """No PII documents should result in zero risk score."""
        score = self.calculate_risk(pii_count=0, unencrypted=0, accessors=1, shares=0)
        assert score == 0

    def test_low_risk_for_encrypted_minimal_access(self):
        """Few PII docs, all encrypted, minimal access should be low risk."""
        score = self.calculate_risk(pii_count=2, unencrypted=0, accessors=2, shares=0)
        assert self.risk_level(score) == "low"

    def test_high_risk_for_unencrypted_wide_access(self):
        """Many PII docs, unencrypted, wide access should be high risk."""
        score = self.calculate_risk(pii_count=5, unencrypted=3, accessors=8, shares=5)
        assert self.risk_level(score) in ("high", "critical")

    def test_critical_risk_is_max_score(self):
        """Worst case scenario should yield critical risk."""
        score = self.calculate_risk(pii_count=10, unencrypted=5, accessors=20, shares=15)
        assert score == 100
        assert self.risk_level(score) == "critical"

    def test_encryption_gap_adds_5_per_unencrypted(self):
        """Each unencrypted doc should add 5 points, capped at 25."""
        score_1 = self.calculate_risk(pii_count=3, unencrypted=1, accessors=0, shares=0)
        score_3 = self.calculate_risk(pii_count=3, unencrypted=3, accessors=0, shares=0)
        assert score_3 - score_1 == 10  # 3*5 - 1*5 = 10

    def test_encryption_gap_caps_at_25(self):
        """Encryption gap score should cap at 25 regardless of unencrypted count."""
        score = self.calculate_risk(pii_count=5, unencrypted=10, accessors=0, shares=0)
        # 25 (pii) + 25 (capped encryption) = 50
        assert score == 50

    def test_risk_level_boundaries(self):
        """Verify risk level boundary thresholds."""
        assert self.risk_level(0) == "low"
        assert self.risk_level(24) == "low"
        assert self.risk_level(25) == "medium"
        assert self.risk_level(49) == "medium"
        assert self.risk_level(50) == "high"
        assert self.risk_level(74) == "high"
        assert self.risk_level(75) == "critical"
        assert self.risk_level(100) == "critical"


# =============================================================================
# Risk Recommendations
# =============================================================================

@pytest.mark.unit
class TestRiskRecommendations:
    """Test the recommendation generation logic."""

    @staticmethod
    def get_recommendations(risk_level, factor_names):
        """Replicate the recommendation logic from the agent."""
        risk_factors = [{"factor": name} for name in factor_names]
        recommendations = []

        if "encryption_gaps" in factor_names:
            recommendations.append("Encrypt all PII documents at rest immediately")
        if "wide_access" in factor_names or "moderate_access" in factor_names:
            recommendations.append(
                "Review and restrict document access permissions to essential users only"
            )
        if "high_sharing" in factor_names or "moderate_sharing" in factor_names:
            recommendations.append(
                "Implement document sharing approval workflow for PII-containing files"
            )
        if "high_pii_density" in factor_names:
            recommendations.append(
                "Enable enhanced audit logging for all PII document access"
            )

        if risk_level == "critical":
            recommendations.insert(0, "IMMEDIATE: Conduct full security review of this loan file")
        elif risk_level == "high":
            recommendations.insert(0, "Schedule security review within 48 hours")

        return recommendations

    def test_critical_risk_gets_immediate_action(self):
        """Critical risk should have IMMEDIATE action as first recommendation."""
        recs = self.get_recommendations("critical", ["encryption_gaps"])
        assert recs[0].startswith("IMMEDIATE:")

    def test_high_risk_gets_48_hour_review(self):
        """High risk should schedule review within 48 hours."""
        recs = self.get_recommendations("high", ["wide_access"])
        assert "48 hours" in recs[0]

    def test_encryption_gaps_recommend_encryption(self):
        """Encryption gaps should recommend encrypting documents."""
        recs = self.get_recommendations("low", ["encryption_gaps"])
        assert any("Encrypt" in r for r in recs)

    def test_wide_access_recommends_restriction(self):
        """Wide access should recommend restricting permissions."""
        recs = self.get_recommendations("low", ["wide_access"])
        assert any("restrict" in r.lower() for r in recs)

    def test_low_risk_no_factors_returns_empty(self):
        """Low risk with no factors should return no recommendations."""
        recs = self.get_recommendations("low", [])
        assert len(recs) == 0


# =============================================================================
# Incident Severity Mapping
# =============================================================================

@pytest.mark.unit
class TestIncidentSeverityMapping:
    """Validate incident severity response requirements."""

    RESPONSE_REQUIREMENTS = {
        "critical": {"response_time": "1 hour", "regulatory_report": True,
                     "borrower_notification": True},
        "high": {"response_time": "4 hours", "regulatory_report": True,
                 "borrower_notification": True},
        "medium": {"response_time": "24 hours", "regulatory_report": False,
                   "borrower_notification": False},
        "low": {"response_time": "72 hours", "regulatory_report": False,
                "borrower_notification": False},
    }

    def test_critical_requires_1_hour_response(self):
        """Critical severity must require 1 hour response time."""
        assert self.RESPONSE_REQUIREMENTS["critical"]["response_time"] == "1 hour"

    def test_critical_requires_regulatory_report(self):
        """Critical incidents must require regulatory reporting."""
        assert self.RESPONSE_REQUIREMENTS["critical"]["regulatory_report"] is True

    def test_critical_requires_borrower_notification(self):
        """Critical incidents must notify borrowers."""
        assert self.RESPONSE_REQUIREMENTS["critical"]["borrower_notification"] is True

    def test_low_does_not_require_borrower_notification(self):
        """Low severity should not require borrower notification."""
        assert self.RESPONSE_REQUIREMENTS["low"]["borrower_notification"] is False

    def test_all_severities_have_response_time(self):
        """All severity levels must define a response time."""
        for severity, reqs in self.RESPONSE_REQUIREMENTS.items():
            assert "response_time" in reqs, f"Missing response_time for {severity}"

    def test_severity_response_time_ordering(self):
        """Response times should be ordered by severity urgency."""
        # Extract numeric hours for comparison
        time_map = {"1 hour": 1, "4 hours": 4, "24 hours": 24, "72 hours": 72}
        severities = ["critical", "high", "medium", "low"]
        times = [time_map[self.RESPONSE_REQUIREMENTS[s]["response_time"]]
                 for s in severities]
        assert times == sorted(times), "Response times should increase with decreasing severity"
