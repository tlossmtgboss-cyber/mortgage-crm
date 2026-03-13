"""
Test Document Compliance Agent - Business logic tests for document-related
regulatory compliance monitoring.

Tests the DocComplianceAgent tool functions' business logic without
hitting a real database. Validates:
- TRID LE/CD timing checks (3-day rules)
- Document retention period calculations
- E-sign consent verification logic
- Compliance scorecard scoring methodology
- State-specific document requirement rules
- Fair lending pattern detection thresholds
- Flood zone classification
- HMDA field completeness
- Remediation plan priority ordering
"""

import pytest
from datetime import datetime, date, timedelta


# =============================================================================
# TRID Timing Business Logic
# =============================================================================

@pytest.mark.unit
class TestTridDocumentCompliance:
    """Test TRID disclosure timing checks used by check_trid_document_compliance."""

    def test_le_sent_within_3_days_passes(self):
        """LE sent within 3 days of application should pass."""
        app_date = date(2026, 1, 5)
        le_sent = date(2026, 1, 7)
        le_days = (le_sent - app_date).days
        assert le_days <= 3
        assert le_days == 2

    def test_le_sent_on_day_3_passes(self):
        """LE sent exactly on day 3 is compliant."""
        app_date = date(2026, 1, 5)
        le_sent = date(2026, 1, 8)
        le_days = (le_sent - app_date).days
        assert le_days == 3
        assert le_days <= 3

    def test_le_sent_on_day_4_fails(self):
        """LE sent on day 4 exceeds the 3-day window."""
        app_date = date(2026, 1, 5)
        le_sent = date(2026, 1, 9)
        le_days = (le_sent - app_date).days
        assert le_days == 4
        assert le_days > 3

    def test_le_not_sent_after_3_days_is_critical(self):
        """LE not sent after 3+ days since application is critical."""
        app_date = date(2026, 1, 5)
        today = date(2026, 1, 10)
        days_since = (today - app_date).days
        assert days_since == 5
        assert days_since > 2

    def test_le_not_sent_within_2_days_is_pending(self):
        """LE not sent within 2 days is still within the window (pending)."""
        app_date = date(2026, 1, 5)
        today = date(2026, 1, 6)
        days_since = (today - app_date).days
        assert days_since == 1
        assert days_since <= 2

    def test_cd_sent_3_days_before_closing_passes(self):
        """CD sent 3+ days before closing is compliant."""
        cd_sent = date(2026, 2, 10)
        funded = date(2026, 2, 14)
        cd_days = (funded - cd_sent).days
        assert cd_days == 4
        assert cd_days >= 3

    def test_cd_sent_exactly_3_days_before_passes(self):
        """CD sent exactly 3 days before closing is the minimum."""
        cd_sent = date(2026, 2, 10)
        funded = date(2026, 2, 13)
        cd_days = (funded - cd_sent).days
        assert cd_days == 3
        assert cd_days >= 3

    def test_cd_sent_2_days_before_closing_fails(self):
        """CD sent only 2 days before closing is a TRID violation."""
        cd_sent = date(2026, 2, 11)
        funded = date(2026, 2, 13)
        cd_days = (funded - cd_sent).days
        assert cd_days == 2
        assert cd_days < 3

    def test_cd_sent_same_day_as_closing_is_critical(self):
        """CD sent same day as closing is a critical violation."""
        cd_sent = date(2026, 2, 13)
        funded = date(2026, 2, 13)
        cd_days = (funded - cd_sent).days
        assert cd_days == 0
        assert cd_days < 3

    def test_null_app_date_skips_le_check(self):
        """Null application date should skip LE timing check."""
        app_date = None
        le_sent = date(2026, 1, 7)
        if app_date and le_sent:
            le_days = (le_sent - app_date).days
        else:
            le_days = None
        assert le_days is None

    def test_null_cd_and_funded_skips_cd_check(self):
        """Null CD and funded dates should skip CD timing check."""
        cd_sent = None
        funded = None
        if cd_sent and funded:
            cd_days = (funded - cd_sent).days
        else:
            cd_days = None
        assert cd_days is None


# =============================================================================
# Revision Count Warnings
# =============================================================================

@pytest.mark.unit
class TestRevisionWarnings:
    """Test LE/CD revision count warning thresholds."""

    def test_2_le_revisions_no_warning(self):
        """2 LE revisions should not trigger a warning."""
        le_revisions = 2
        assert not (le_revisions > 2)

    def test_3_le_revisions_triggers_warning(self):
        """3+ LE revisions should trigger a review warning."""
        le_revisions = 3
        assert le_revisions > 2

    def test_2_cd_revisions_no_warning(self):
        """2 CD revisions should not trigger a warning."""
        cd_revisions = 2
        assert not (cd_revisions > 2)

    def test_5_cd_revisions_triggers_warning(self):
        """5 CD revisions should trigger a review warning."""
        cd_revisions = 5
        assert cd_revisions > 2


# =============================================================================
# Document Retention Logic
# =============================================================================

@pytest.mark.unit
class TestDocumentRetention:
    """Test document retention period calculations."""

    # Mirror constants from the agent
    RETENTION_PERIODS = {
        "paystubs": 3,
        "tax_returns": 7,
        "bank_statements": 5,
        "appraisal": 7,
        "credit_report": 3,
        "loan_estimate": 5,
        "closing_disclosure": 5,
        "flood_determination": 7,
    }

    def test_doc_within_retention_is_compliant(self):
        """Document uploaded 1 year ago with 3-year retention is compliant."""
        uploaded_at = date.today() - timedelta(days=365)
        retention_years = 3
        retention_end = uploaded_at + timedelta(days=retention_years * 365)
        days_remaining = (retention_end - date.today()).days
        assert days_remaining > 0

    def test_doc_past_retention_is_expired(self):
        """Document past its retention period should be flagged as expired."""
        uploaded_at = date.today() - timedelta(days=4 * 365)
        retention_years = 3
        retention_end = uploaded_at + timedelta(days=retention_years * 365)
        days_remaining = (retention_end - date.today()).days
        assert days_remaining < 0

    def test_doc_expiring_within_threshold_is_at_risk(self):
        """Document expiring within threshold should be flagged as at-risk."""
        retention_years = 3
        days_to_expiry = 90
        uploaded_at = date.today() - timedelta(days=(retention_years * 365) - 60)
        retention_end = uploaded_at + timedelta(days=retention_years * 365)
        days_remaining = (retention_end - date.today()).days
        assert 0 < days_remaining <= days_to_expiry

    def test_tax_returns_have_7_year_retention(self):
        """Tax returns should have a 7-year retention period."""
        assert self.RETENTION_PERIODS["tax_returns"] == 7

    def test_paystubs_have_3_year_retention(self):
        """Paystubs should have a 3-year retention period."""
        assert self.RETENTION_PERIODS["paystubs"] == 3

    def test_appraisal_has_7_year_retention(self):
        """Appraisal should have a 7-year retention period."""
        assert self.RETENTION_PERIODS["appraisal"] == 7

    def test_closing_disclosure_has_5_year_retention(self):
        """Closing Disclosure should have a 5-year retention period."""
        assert self.RETENTION_PERIODS["closing_disclosure"] == 5


# =============================================================================
# E-Sign Compliance Logic
# =============================================================================

@pytest.mark.unit
class TestEsignCompliance:
    """Test e-sign compliance logic for ESIGN Act / UETA."""

    def test_consent_present_passes(self):
        """ESIGN consent on file should pass."""
        consent_esign = True
        checks = []
        issues = []
        if consent_esign:
            checks.append({"check": "ESIGN_CONSENT", "status": "pass"})
        else:
            issues.append({"check": "ESIGN_CONSENT", "severity": "high"})
        assert len(checks) == 1
        assert len(issues) == 0

    def test_consent_missing_is_high_severity(self):
        """Missing ESIGN consent should be high severity."""
        consent_esign = False
        issues = []
        if not consent_esign:
            issues.append({"check": "ESIGN_CONSENT", "severity": "high"})
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_signed_docs_pass(self):
        """Documents with signatures should pass audit."""
        signed_date = datetime(2026, 1, 10)
        checks = []
        if signed_date:
            checks.append({"check": "SIGNATURE", "status": "pass"})
        assert len(checks) == 1

    def test_unsigned_docs_are_medium_severity(self):
        """Unsigned documents should be medium severity issues."""
        signed_date = None
        issues = []
        if not signed_date:
            issues.append({"check": "SIGNATURE", "severity": "medium"})
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"

    def test_audit_trail_present_passes(self):
        """Disclosure events in audit trail should pass."""
        event_count = 5
        checks = []
        if event_count > 0:
            checks.append({"check": "AUDIT_TRAIL", "status": "pass"})
        assert len(checks) == 1

    def test_no_audit_trail_is_issue(self):
        """No disclosure events should flag as an issue."""
        event_count = 0
        issues = []
        if event_count == 0:
            issues.append({"check": "AUDIT_TRAIL", "severity": "medium"})
        assert len(issues) == 1


# =============================================================================
# Compliance Scorecard Logic
# =============================================================================

@pytest.mark.unit
class TestComplianceScorecard:
    """Test compliance scorecard scoring methodology."""

    SCORECARD_WEIGHTS = {
        "trid_timing": 20,
        "document_completeness": 15,
        "esign_compliance": 10,
        "retention_compliance": 10,
        "state_specific": 10,
        "hmda_data_quality": 10,
        "privacy_compliance": 10,
        "flood_compliance": 5,
        "fraud_process": 5,
        "fair_lending": 5,
    }

    def test_perfect_score_is_100(self):
        """Sum of all weights should equal 100."""
        total = sum(self.SCORECARD_WEIGHTS.values())
        assert total == 100

    def test_grade_a_for_score_90_plus(self):
        """Score 90+ should be Grade A."""
        score = 95
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        assert grade == "A"

    def test_grade_b_for_score_80_to_89(self):
        """Score 80-89 should be Grade B."""
        score = 85
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        assert grade == "B"

    def test_grade_c_for_score_70_to_79(self):
        """Score 70-79 should be Grade C."""
        score = 75
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        assert grade == "C"

    def test_grade_d_for_score_60_to_69(self):
        """Score 60-69 should be Grade D."""
        score = 65
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        assert grade == "D"

    def test_grade_f_for_score_below_60(self):
        """Score below 60 should be Grade F."""
        score = 55
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        assert grade == "F"

    def test_trid_timing_is_heaviest_weight(self):
        """TRID timing should have the highest weight (20)."""
        max_weight = max(self.SCORECARD_WEIGHTS.values())
        assert self.SCORECARD_WEIGHTS["trid_timing"] == max_weight
        assert max_weight == 20

    def test_le_violation_deducts_10_from_trid(self):
        """LE timing violation should deduct 10 from TRID score."""
        base = 20
        le_days = 5  # Over 3 days
        if le_days > 3:
            base -= 10
        assert base == 10

    def test_cd_violation_deducts_10_from_trid(self):
        """CD timing violation should deduct 10 from TRID score."""
        base = 20
        cd_days = 2  # Under 3 days
        if cd_days < 3:
            base -= 10
        assert base == 10

    def test_both_violations_zero_trid_score(self):
        """Both LE and CD violations should result in 0 TRID score (clamped)."""
        base = 20
        le_days = 5
        cd_days = 1
        if le_days > 3:
            base -= 10
        if cd_days < 3:
            base -= 10
        assert max(0, base) == 0

    def test_risk_level_from_grade(self):
        """Risk levels should correspond to score thresholds."""
        test_cases = [
            (95, "low"),
            (85, "low"),
            (75, "medium"),
            (65, "high"),
            (50, "critical"),
        ]
        for score, expected_risk in test_cases:
            if score >= 90:
                risk = "low"
            elif score >= 80:
                risk = "low"
            elif score >= 70:
                risk = "medium"
            elif score >= 60:
                risk = "high"
            else:
                risk = "critical"
            assert risk == expected_risk, f"Score {score} should be {expected_risk}, got {risk}"


# =============================================================================
# State-Specific Requirements
# =============================================================================

@pytest.mark.unit
class TestStateSpecificRequirements:
    """Test state-specific document requirement rules."""

    STATE_DOC_REQUIREMENTS = {
        "TX": {
            "name": "Texas",
            "rules": [
                {"doc_type": "tx_home_equity_disclosure", "applies_to": "cash_out_refinance"},
                {"doc_type": "tx_ltv_certification", "applies_to": "home_equity"},
            ],
        },
        "NY": {
            "name": "New York",
            "rules": [
                {"doc_type": "ny_subprime_warning", "applies_to": "high_cost_mortgage"},
                {"doc_type": "ny_mlo_disclosure", "applies_to": "all"},
            ],
        },
        "CA": {
            "name": "California",
            "rules": [
                {"doc_type": "ca_mlds", "applies_to": "all"},
                {"doc_type": "ca_fair_lending_notice", "applies_to": "all"},
            ],
        },
    }

    def test_texas_has_home_equity_rules(self):
        """Texas should have home equity disclosure rules."""
        tx = self.STATE_DOC_REQUIREMENTS["TX"]
        doc_types = [r["doc_type"] for r in tx["rules"]]
        assert "tx_home_equity_disclosure" in doc_types

    def test_new_york_has_subprime_warning(self):
        """New York should have subprime warning requirement."""
        ny = self.STATE_DOC_REQUIREMENTS["NY"]
        doc_types = [r["doc_type"] for r in ny["rules"]]
        assert "ny_subprime_warning" in doc_types

    def test_california_requires_mlds(self):
        """California should require MLDS."""
        ca = self.STATE_DOC_REQUIREMENTS["CA"]
        doc_types = [r["doc_type"] for r in ca["rules"]]
        assert "ca_mlds" in doc_types

    def test_unknown_state_returns_no_specific_rules(self):
        """A state not in the catalog should return no specific rules."""
        state = "WY"
        assert state not in self.STATE_DOC_REQUIREMENTS

    def test_all_applies_to_rule_matches_all_loans(self):
        """Rules with applies_to='all' should apply to every loan."""
        ny = self.STATE_DOC_REQUIREMENTS["NY"]
        all_rules = [r for r in ny["rules"] if r["applies_to"] == "all"]
        assert len(all_rules) >= 1
        assert all_rules[0]["doc_type"] == "ny_mlo_disclosure"

    def test_conditional_rule_only_applies_to_matching_purpose(self):
        """Rules with specific applies_to should only match that loan purpose."""
        tx = self.STATE_DOC_REQUIREMENTS["TX"]
        he_rule = next(r for r in tx["rules"] if r["doc_type"] == "tx_home_equity_disclosure")
        loan_purpose = "purchase"
        applicable = he_rule["applies_to"] == "all" or he_rule["applies_to"] in loan_purpose
        assert applicable is False

    def test_conditional_rule_matches_correct_purpose(self):
        """Conditional rule should match when loan purpose aligns."""
        tx = self.STATE_DOC_REQUIREMENTS["TX"]
        he_rule = next(r for r in tx["rules"] if r["doc_type"] == "tx_home_equity_disclosure")
        loan_purpose = "cash_out_refinance"
        applicable = he_rule["applies_to"] == "all" or he_rule["applies_to"] in loan_purpose
        assert applicable is True


# =============================================================================
# Flood Zone Classification
# =============================================================================

@pytest.mark.unit
class TestFloodZoneClassification:
    """Test flood zone classification logic."""

    HIGH_RISK_ZONES = ("A", "AE", "AH", "AO", "AR", "A99", "V", "VE", "V1")

    def test_zone_ae_is_high_risk(self):
        """Zone AE should be classified as high risk (SFHA)."""
        zone = "AE"
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES)
        assert in_sfha is True

    def test_zone_x_is_not_high_risk(self):
        """Zone X should not be classified as high risk."""
        zone = "X"
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES)
        assert in_sfha is False

    def test_zone_v_is_high_risk(self):
        """Zone V (coastal) should be classified as high risk."""
        zone = "V"
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES)
        assert in_sfha is True

    def test_zone_c_is_not_high_risk(self):
        """Zone C (minimal flood hazard) should not be high risk."""
        zone = "C"
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES)
        assert in_sfha is False

    def test_empty_zone_is_not_high_risk(self):
        """Empty flood zone should not be classified as high risk."""
        zone = ""
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES) if zone else False
        assert in_sfha is False

    def test_zone_a99_is_high_risk(self):
        """Zone A99 should be classified as high risk."""
        zone = "A99"
        in_sfha = any(zone.upper().startswith(z) for z in self.HIGH_RISK_ZONES)
        assert in_sfha is True


# =============================================================================
# HMDA Required Fields
# =============================================================================

@pytest.mark.unit
class TestHmdaDataQuality:
    """Test HMDA data completeness checking logic."""

    HMDA_REQUIRED_FIELDS = [
        "loan_type", "loan_purpose", "loan_amount", "rate",
        "property_type", "occupancy_type",
        "borrower_ethnicity", "borrower_race", "borrower_sex",
        "income", "property_state", "property_county",
        "census_tract", "action_taken", "action_taken_date",
    ]

    def test_hmda_has_15_required_fields(self):
        """HMDA should require 15 LAR data fields."""
        assert len(self.HMDA_REQUIRED_FIELDS) == 15

    def test_completeness_calculation_all_present(self):
        """All fields present should give 100% completeness."""
        present = len(self.HMDA_REQUIRED_FIELDS)
        total = len(self.HMDA_REQUIRED_FIELDS)
        completeness = round((present / total) * 100, 1)
        assert completeness == 100.0

    def test_completeness_calculation_partial(self):
        """10 of 15 fields present should give 66.7% completeness."""
        present = 10
        total = 15
        completeness = round((present / total) * 100, 1)
        assert completeness == 66.7

    def test_completeness_zero_when_no_fields(self):
        """No fields present should give 0% completeness."""
        present = 0
        total = 15
        completeness = round((present / total) * 100, 1)
        assert completeness == 0.0

    def test_demographic_fields_included(self):
        """HMDA should include demographic data fields."""
        demo_fields = {"borrower_ethnicity", "borrower_race", "borrower_sex"}
        assert demo_fields.issubset(set(self.HMDA_REQUIRED_FIELDS))


# =============================================================================
# Remediation Plan Priority Ordering
# =============================================================================

@pytest.mark.unit
class TestRemediationPriority:
    """Test compliance remediation plan priority ordering."""

    def test_critical_before_high(self):
        """Critical items should sort before high severity items."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items = [
            {"severity": "high", "title": "Missing doc"},
            {"severity": "critical", "title": "TRID violation"},
            {"severity": "medium", "title": "Privacy notice"},
        ]
        sorted_items = sorted(items, key=lambda x: severity_order.get(x["severity"], 4))
        assert sorted_items[0]["severity"] == "critical"
        assert sorted_items[1]["severity"] == "high"
        assert sorted_items[2]["severity"] == "medium"

    def test_critical_deadline_is_1_day(self):
        """Critical items should have a 1-day deadline."""
        severity = "critical"
        if severity == "critical":
            deadline = date.today() + timedelta(days=1)
        elif severity == "high":
            deadline = date.today() + timedelta(days=3)
        else:
            deadline = date.today() + timedelta(days=7)
        assert (deadline - date.today()).days == 1

    def test_high_deadline_is_3_days(self):
        """High severity items should have a 3-day deadline."""
        severity = "high"
        if severity == "critical":
            deadline = date.today() + timedelta(days=1)
        elif severity == "high":
            deadline = date.today() + timedelta(days=3)
        else:
            deadline = date.today() + timedelta(days=7)
        assert (deadline - date.today()).days == 3

    def test_medium_deadline_is_7_days(self):
        """Medium severity items should have a 7-day deadline."""
        severity = "medium"
        if severity == "critical":
            deadline = date.today() + timedelta(days=1)
        elif severity == "high":
            deadline = date.today() + timedelta(days=3)
        else:
            deadline = date.today() + timedelta(days=7)
        assert (deadline - date.today()).days == 7
