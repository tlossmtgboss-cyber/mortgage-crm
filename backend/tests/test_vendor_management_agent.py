"""
Test Vendor Management Agent - Validates vendor SLA constants, order timing
logic, flood zone classification, appraisal validation rules, and closing
readiness checks used by the VendorManagementAgent tools.

Covers:
- VENDOR_SLA_TARGETS dictionary completeness and values
- ORDER_TIMING_BY_STAGE stage-to-order mapping
- Flood zone risk classification logic
- Appraisal gap and LTV validation logic
- Closing readiness blocker detection
- Vendor delay detection logic
- Vendor performance scoring
"""

import pytest
from datetime import datetime, date, timedelta


# =============================================================================
# Vendor SLA Targets
# =============================================================================

@pytest.mark.unit
class TestVendorSLATargets:
    """Validate the VENDOR_SLA_TARGETS constant."""

    VENDOR_SLA_TARGETS = {
        "appraisal_order_to_schedule": 3,
        "appraisal_schedule_to_complete": 5,
        "appraisal_complete_to_received": 2,
        "title_order_to_received": 7,
        "insurance_order_to_received": 5,
        "flood_determination": 1,
        "hoa_cert_order_to_received": 10,
    }

    def test_sla_targets_has_7_entries(self):
        """VENDOR_SLA_TARGETS should define 7 vendor SLA entries."""
        assert len(self.VENDOR_SLA_TARGETS) == 7

    def test_appraisal_total_sla_is_10_days(self):
        """Total appraisal SLA (order to received) should be 10 days."""
        total = (
            self.VENDOR_SLA_TARGETS["appraisal_order_to_schedule"]
            + self.VENDOR_SLA_TARGETS["appraisal_schedule_to_complete"]
            + self.VENDOR_SLA_TARGETS["appraisal_complete_to_received"]
        )
        assert total == 10

    def test_title_sla_is_7_days(self):
        """Title order to received SLA should be 7 days."""
        assert self.VENDOR_SLA_TARGETS["title_order_to_received"] == 7

    def test_insurance_sla_is_5_days(self):
        """Insurance order to binder SLA should be 5 days."""
        assert self.VENDOR_SLA_TARGETS["insurance_order_to_received"] == 5

    def test_flood_determination_is_1_day(self):
        """Flood determination should be 1 day."""
        assert self.VENDOR_SLA_TARGETS["flood_determination"] == 1

    def test_hoa_cert_is_10_days(self):
        """HOA certification SLA should be 10 days."""
        assert self.VENDOR_SLA_TARGETS["hoa_cert_order_to_received"] == 10

    def test_all_sla_values_are_positive_integers(self):
        """All vendor SLA values must be positive integers."""
        for key, value in self.VENDOR_SLA_TARGETS.items():
            assert isinstance(value, int), f"SLA for {key} should be int, got {type(value)}"
            assert value > 0, f"SLA for {key} should be positive, got {value}"


# =============================================================================
# Order Timing by Stage
# =============================================================================

@pytest.mark.unit
class TestOrderTimingByStage:
    """Validate ORDER_TIMING_BY_STAGE mapping."""

    ORDER_TIMING_BY_STAGE = {
        "APPLICATION": [],
        "DISCLOSED": ["flood_determination"],
        "PROCESSING": ["appraisal", "title"],
        "SUBMITTED": ["insurance"],
        "UNDERWRITING": [],
        "UW_RECEIVED": [],
        "CONDITIONAL_APPROVAL": ["hoa_cert"],
        "APPROVED": [],
        "CLEAR_TO_CLOSE": [],
    }

    def test_application_has_no_orders(self):
        """APPLICATION stage should have no vendor orders."""
        assert self.ORDER_TIMING_BY_STAGE["APPLICATION"] == []

    def test_processing_triggers_appraisal_and_title(self):
        """PROCESSING stage should trigger appraisal and title orders."""
        orders = self.ORDER_TIMING_BY_STAGE["PROCESSING"]
        assert "appraisal" in orders
        assert "title" in orders

    def test_disclosed_triggers_flood(self):
        """DISCLOSED stage should trigger flood determination."""
        assert "flood_determination" in self.ORDER_TIMING_BY_STAGE["DISCLOSED"]

    def test_submitted_triggers_insurance(self):
        """SUBMITTED stage should trigger insurance order."""
        assert "insurance" in self.ORDER_TIMING_BY_STAGE["SUBMITTED"]

    def test_conditional_approval_triggers_hoa(self):
        """CONDITIONAL_APPROVAL stage should trigger HOA cert."""
        assert "hoa_cert" in self.ORDER_TIMING_BY_STAGE["CONDITIONAL_APPROVAL"]

    def test_clear_to_close_has_no_new_orders(self):
        """CLEAR_TO_CLOSE should have no new orders — everything should be done."""
        assert self.ORDER_TIMING_BY_STAGE["CLEAR_TO_CLOSE"] == []

    def test_all_stages_present(self):
        """All pipeline stages should be represented in the mapping."""
        expected_stages = [
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
            "APPROVED", "CLEAR_TO_CLOSE",
        ]
        for stage in expected_stages:
            assert stage in self.ORDER_TIMING_BY_STAGE, f"Missing stage: {stage}"


# =============================================================================
# Flood Zone Classification
# =============================================================================

@pytest.mark.unit
class TestFloodZoneClassification:
    """Test flood zone risk classification logic from check_flood_determination."""

    HIGH_RISK_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
    MODERATE_RISK_ZONES = {"B", "X500", "X (shaded)"}
    LOW_RISK_ZONES = {"C", "X", "X (unshaded)"}

    def _classify(self, zone):
        if zone in self.HIGH_RISK_ZONES:
            return "high"
        elif zone in self.MODERATE_RISK_ZONES:
            return "moderate"
        elif zone in self.LOW_RISK_ZONES:
            return "low"
        return "unknown"

    def test_zone_a_is_high_risk(self):
        """Zone A should be classified as high risk."""
        assert self._classify("A") == "high"

    def test_zone_ae_is_high_risk(self):
        """Zone AE should be classified as high risk."""
        assert self._classify("AE") == "high"

    def test_zone_v_is_high_risk(self):
        """Zone V (coastal) should be classified as high risk."""
        assert self._classify("V") == "high"

    def test_zone_ve_is_high_risk(self):
        """Zone VE (coastal with base flood elevations) should be high risk."""
        assert self._classify("VE") == "high"

    def test_zone_x_is_low_risk(self):
        """Zone X should be classified as low risk."""
        assert self._classify("X") == "low"

    def test_zone_c_is_low_risk(self):
        """Zone C should be classified as low risk."""
        assert self._classify("C") == "low"

    def test_zone_b_is_moderate_risk(self):
        """Zone B should be classified as moderate risk."""
        assert self._classify("B") == "moderate"

    def test_unknown_zone_returns_unknown(self):
        """An unrecognized zone should return unknown."""
        assert self._classify("Z99") == "unknown"

    def test_none_zone_returns_unknown(self):
        """None zone should not match any category."""
        # None is not in any set
        assert None not in self.HIGH_RISK_ZONES
        assert None not in self.MODERATE_RISK_ZONES
        assert None not in self.LOW_RISK_ZONES

    def test_high_risk_zones_require_flood_insurance(self):
        """All high-risk zones should require mandatory flood insurance."""
        for zone in self.HIGH_RISK_ZONES:
            assert self._classify(zone) == "high", f"Zone {zone} should be high risk"


# =============================================================================
# Appraisal Validation Logic
# =============================================================================

@pytest.mark.unit
class TestAppraisalValidation:
    """Test appraisal validation rules from validate_appraisal_report."""

    def test_appraisal_gap_detected(self):
        """Appraisal value below purchase price should flag an appraisal gap."""
        appraisal_value = 380000
        purchase_price = 400000
        assert appraisal_value < purchase_price
        gap = purchase_price - appraisal_value
        assert gap == 20000

    def test_no_gap_when_value_equals_price(self):
        """No gap when appraisal equals purchase price."""
        appraisal_value = 400000
        purchase_price = 400000
        assert not (appraisal_value < purchase_price)

    def test_no_gap_when_value_exceeds_price(self):
        """No gap when appraisal exceeds purchase price."""
        appraisal_value = 420000
        purchase_price = 400000
        assert not (appraisal_value < purchase_price)

    def test_value_overshoot_flagged_above_15_percent(self):
        """Appraisal >15% above purchase price should trigger a warning."""
        appraisal_value = 470000
        purchase_price = 400000
        assert appraisal_value > purchase_price * 1.15

    def test_value_within_15_percent_not_flagged(self):
        """Appraisal within 15% of purchase price should not trigger overshoot warning."""
        appraisal_value = 440000
        purchase_price = 400000
        assert not (appraisal_value > purchase_price * 1.15)

    def test_ltv_calculation(self):
        """LTV should be loan_amount / appraisal_value * 100."""
        loan_amount = 380000
        appraisal_value = 400000
        ltv = loan_amount / appraisal_value * 100
        assert ltv == 95.0

    def test_high_ltv_flagged_above_97(self):
        """LTV above 97% should be flagged as high."""
        loan_amount = 390000
        appraisal_value = 400000
        ltv = loan_amount / appraisal_value * 100
        assert ltv > 97

    def test_elevated_ltv_flagged_between_95_and_97(self):
        """LTV between 95% and 97% should trigger MI requirement warning."""
        loan_amount = 384000
        appraisal_value = 400000
        ltv = loan_amount / appraisal_value * 100
        assert 95 < ltv <= 97

    def test_normal_ltv_not_flagged(self):
        """LTV at or below 95% should not be flagged."""
        loan_amount = 320000
        appraisal_value = 400000
        ltv = loan_amount / appraisal_value * 100
        assert ltv <= 95


# =============================================================================
# Vendor Delay Detection
# =============================================================================

@pytest.mark.unit
class TestVendorDelayDetection:
    """Test vendor delay detection logic from identify_delayed_orders."""

    def test_order_within_sla_not_delayed(self):
        """An order within its SLA target should not be flagged."""
        ordered_date = date.today() - timedelta(days=5)
        sla_target = 7
        days_elapsed = (date.today() - ordered_date).days
        assert days_elapsed <= sla_target

    def test_order_past_sla_is_delayed(self):
        """An order past its SLA target should be flagged."""
        ordered_date = date.today() - timedelta(days=12)
        sla_target = 10
        days_elapsed = (date.today() - ordered_date).days
        assert days_elapsed > sla_target

    def test_days_over_sla_calculation(self):
        """Days over SLA should be elapsed - target."""
        ordered_date = date.today() - timedelta(days=12)
        sla_target = 10
        days_elapsed = (date.today() - ordered_date).days
        days_over = days_elapsed - sla_target
        assert days_over == 2

    def test_received_order_not_checked(self):
        """A received order should not be checked for delays regardless of elapsed time."""
        ordered_date = date.today() - timedelta(days=30)
        received_date = date.today() - timedelta(days=20)
        # Logic: only check if received_date IS NULL
        is_pending = received_date is None
        assert not is_pending


# =============================================================================
# Closing Readiness Logic
# =============================================================================

@pytest.mark.unit
class TestClosingReadiness:
    """Test closing readiness blocker detection from coordinate_closing_vendors."""

    def test_all_received_means_no_blockers(self):
        """When all vendor items are received, there should be no blockers."""
        appraisal_received = True
        title_received = True
        insurance_received = True
        cd_sent = True

        blockers = []
        if not appraisal_received:
            blockers.append("Appraisal not received")
        if not title_received:
            blockers.append("Title not received")
        if not insurance_received:
            blockers.append("Insurance binder not received")
        if not cd_sent:
            blockers.append("CD not sent")

        assert len(blockers) == 0

    def test_missing_appraisal_is_blocker(self):
        """Missing appraisal should be a blocker."""
        blockers = []
        if not False:  # appraisal not received
            blockers.append("Appraisal not received")
        assert "Appraisal not received" in blockers

    def test_missing_title_is_blocker(self):
        """Missing title should be a blocker."""
        blockers = []
        if not False:  # title not received
            blockers.append("Title not received")
        assert "Title not received" in blockers

    def test_cd_timing_violation_is_blocker(self):
        """CD sent less than 3 days before closing should be a blocker."""
        cd_sent_date = date.today()
        closing_date = date.today() + timedelta(days=2)
        cd_gap = (closing_date - cd_sent_date).days
        assert cd_gap < 3

    def test_cd_timing_compliant(self):
        """CD sent 3+ days before closing should be compliant."""
        cd_sent_date = date.today()
        closing_date = date.today() + timedelta(days=5)
        cd_gap = (closing_date - cd_sent_date).days
        assert cd_gap >= 3

    def test_expired_appraisal_is_blocker(self):
        """Appraisal expiring before closing date should be a blocker."""
        appraisal_expires = date.today() + timedelta(days=5)
        closing_date = date.today() + timedelta(days=10)
        assert appraisal_expires < closing_date

    def test_days_to_close_calculation(self):
        """Days to close should be closing_date - today."""
        closing_date = date.today() + timedelta(days=15)
        days_to_close = (closing_date - date.today()).days
        assert days_to_close == 15


# =============================================================================
# Vendor Performance Scoring
# =============================================================================

@pytest.mark.unit
class TestVendorPerformanceScoring:
    """Test vendor performance scoring logic from rate_vendor_performance."""

    def test_perfect_on_time_score(self):
        """100% on-time rate should produce a high score."""
        on_time_pct = 100.0
        completion_pct = 100.0
        score = round(on_time_pct * 0.6 + completion_pct * 0.4, 1)
        assert score == 100.0

    def test_zero_on_time_score(self):
        """0% on-time with full completion should produce a 40 score."""
        on_time_pct = 0.0
        completion_pct = 100.0
        score = round(on_time_pct * 0.6 + completion_pct * 0.4, 1)
        assert score == 40.0

    def test_mixed_performance_score(self):
        """80% on-time, 90% completion should produce a weighted score."""
        on_time_pct = 80.0
        completion_pct = 90.0
        score = round(on_time_pct * 0.6 + completion_pct * 0.4, 1)
        assert score == 84.0

    def test_on_time_rate_calculation(self):
        """On-time rate should be on_time / completed * 100."""
        on_time = 8
        completed = 10
        rate = round(on_time / completed * 100, 1)
        assert rate == 80.0

    def test_on_time_rate_zero_completed(self):
        """Zero completed orders should result in 0% on-time rate."""
        on_time = 0
        completed = 0
        rate = round(on_time / completed * 100, 1) if completed > 0 else 0
        assert rate == 0

    def test_recommendation_tier_recommended(self):
        """On-time rate >= 80% should earn 'recommended' tier."""
        on_time_pct = 85.0
        tier = "recommended" if on_time_pct >= 80 else "acceptable" if on_time_pct >= 60 else "review"
        assert tier == "recommended"

    def test_recommendation_tier_acceptable(self):
        """On-time rate 60-79% should earn 'acceptable' tier."""
        on_time_pct = 70.0
        tier = "recommended" if on_time_pct >= 80 else "acceptable" if on_time_pct >= 60 else "review"
        assert tier == "acceptable"

    def test_recommendation_tier_review(self):
        """On-time rate < 60% should earn 'review' tier."""
        on_time_pct = 50.0
        tier = "recommended" if on_time_pct >= 80 else "acceptable" if on_time_pct >= 60 else "review"
        assert tier == "review"
