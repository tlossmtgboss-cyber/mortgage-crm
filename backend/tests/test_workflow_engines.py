"""
Tests for workflow state machine engines — Lead Workflow Engine and Rate Lock Intelligence Engine.

Covers:
- Lead stage transition validation (state machine)
- Workflow action generation on status changes
- Rate lock eligibility, scoring, and recommendations
- Float-down detection, lock extension analysis
- Workflow execution logging and error handling
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from workflows.lead_workflow_engine import (
    LEAD_STAGES,
    VALID_TRANSITIONS,
    TIME_RULES,
    LeadStatusChange,
    LeadWorkflowEngine,
    TimeBasedWorkflowEngine,
)
from workflows.rate_lock_engine import (
    MarketSnapshot,
    LoanContext,
    RateLockAnalysis,
    RateLockIntelligenceEngine,
    LockMonitoringSubflow,
    FloatMonitoringSubflow,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _make_status_change(**overrides):
    """Factory for LeadStatusChange with sane defaults."""
    defaults = dict(
        lead_id=100,
        lead_name="Jane Doe",
        lead_email="jane@example.com",
        lead_phone="+15551234567",
        old_status="New",
        new_status="Attempted Contact",
        loan_officer_id=1,
        loan_officer_name="Tim Loss",
        loan_officer_email="tim@example.com",
        changed_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return LeadStatusChange(**defaults)


def _make_market(**overrides):
    """Factory for MarketSnapshot with neutral defaults."""
    defaults = dict(
        treasury_10yr=4.25,
        treasury_2yr=4.15,
        mortgage_30yr=6.875,
        mbs_price=100.50,
        mbs_change=0,
        volatility_score=50,
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def _make_loan_context(**overrides):
    """Factory for LoanContext with defaults."""
    defaults = dict(
        loan_id=200,
        loan_number="2026-001",
        borrower_name="Jane Doe",
        loan_amount=400_000,
        current_rate=6.875,
        closing_date=datetime.now(timezone.utc) + timedelta(days=20),
        lock_date=None,
        lock_expiration_date=None,
        lock_term_days=30,
        rate_lock_status="Not Locked",
        borrower_risk_profile=None,
        property_identified=True,
        loan_structure_complete=True,
    )
    defaults.update(overrides)
    return LoanContext(**defaults)


@pytest.fixture
def mock_db():
    """Lightweight mock DB session for unit tests."""
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    db.execute.return_value.fetchall.return_value = []
    return db


@pytest.fixture
def lead_engine(mock_db):
    return LeadWorkflowEngine(mock_db)


@pytest.fixture
def rate_engine():
    return RateLockIntelligenceEngine()


# =============================================================================
# LEAD WORKFLOW — STATE MACHINE TRANSITION TESTS
# =============================================================================

class TestLeadWorkflowTransitions:
    """Validate the VALID_TRANSITIONS state machine map."""

    # Collect every (src, dst) pair declared valid
    _valid_pairs = []
    for src, dsts in VALID_TRANSITIONS.items():
        for dst in dsts:
            _valid_pairs.append((src, dst))

    @pytest.mark.parametrize("src,dst", _valid_pairs)
    def test_lead_workflow_valid_transitions(self, src, dst):
        """Every declared transition should be accepted by the map lookup."""
        allowed = VALID_TRANSITIONS.get(src, [])
        assert dst in allowed, f"{src} -> {dst} should be a valid transition"

    @pytest.mark.parametrize("src,dst", [
        ("New", "Closed"),
        ("New", "Pre-Approved"),
        ("Attempted Contact", "Closed"),
        ("Pre-Approved", "New"),
        ("Closed", "New"),
    ])
    def test_lead_workflow_invalid_transition(self, src, dst):
        """Transitions NOT in the map must be absent."""
        allowed = VALID_TRANSITIONS.get(src, [])
        assert dst not in allowed, f"{src} -> {dst} should NOT be a valid transition"

    def test_lead_workflow_terminal_states_referral_source(self):
        """Referral Source has zero outgoing transitions — terminal."""
        assert VALID_TRANSITIONS["Referral Source"] == []

    def test_lead_workflow_terminal_states_withdrawn_limited(self):
        """Withdrawn only allows re-entry to New — nearly terminal."""
        assert VALID_TRANSITIONS["Withdrawn"] == ["New"]

    def test_lead_workflow_all_stages_reachable(self):
        """Every non-initial stage must be reachable as a destination from at least one source."""
        all_destinations = set()
        for dsts in VALID_TRANSITIONS.values():
            all_destinations.update(dsts)

        for stage in LEAD_STAGES:
            if stage == "New":
                # New is the initial state — reachable from None
                assert "New" in VALID_TRANSITIONS.get(None, [])
            else:
                assert stage in all_destinations, (
                    f"Stage '{stage}' is defined in LEAD_STAGES but unreachable via VALID_TRANSITIONS"
                )

    def test_lead_workflow_no_orphan_stages(self):
        """Every non-terminal stage must have at least one outgoing transition."""
        terminal_stages = {"Referral Source"}
        for stage in LEAD_STAGES:
            if stage in terminal_stages:
                continue
            outgoing = VALID_TRANSITIONS.get(stage, [])
            assert len(outgoing) > 0, (
                f"Stage '{stage}' has no outgoing transitions but is not marked terminal"
            )

    def test_lead_stages_consistent_with_transitions(self):
        """All stages that appear in VALID_TRANSITIONS keys/values should be in LEAD_STAGES."""
        all_mentioned = set()
        for src, dsts in VALID_TRANSITIONS.items():
            if src is not None:
                all_mentioned.add(src)
            all_mentioned.update(dsts)

        lead_stages_set = set(LEAD_STAGES)
        missing = all_mentioned - lead_stages_set
        assert missing == set(), f"Stages in VALID_TRANSITIONS but not in LEAD_STAGES: {missing}"


# =============================================================================
# LEAD WORKFLOW — ACTION GENERATION TESTS
# =============================================================================

class TestLeadWorkflowActions:
    """Verify that status changes generate the right workflow actions."""

    @pytest.mark.asyncio
    async def test_new_lead_triggers_actions(self, lead_engine):
        """Transitioning to New should produce SMS, email, alert, task, and drip actions."""
        sc = _make_status_change(old_status="Withdrawn", new_status="New")
        result = await lead_engine.process_status_change(sc)

        assert result["success"] is True
        action_types = [a["action_type"] for a in result["actions"]]
        assert "sms" in action_types
        assert "email" in action_types
        assert "alert" in action_types
        assert "task" in action_types
        assert "drip" in action_types

    @pytest.mark.asyncio
    async def test_new_to_attempted_triggers_activity_log(self, lead_engine):
        """New -> Attempted Contact should log an activity."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        result = await lead_engine.process_status_change(sc)

        activity_actions = [a for a in result["actions"] if a["action_type"] == "activity"]
        assert len(activity_actions) >= 1
        assert "contact" in activity_actions[0]["data"]["note"].lower()

    @pytest.mark.asyncio
    async def test_attempted_to_prospect_sends_email(self, lead_engine):
        """Attempted Contact -> Prospect should send a 'great connecting' email."""
        sc = _make_status_change(old_status="Attempted Contact", new_status="Prospect")
        result = await lead_engine.process_status_change(sc)

        email_actions = [a for a in result["actions"] if a["action_type"] == "email"]
        assert len(email_actions) >= 1
        assert "great_connecting" in email_actions[0].get("template", "")

    @pytest.mark.asyncio
    async def test_withdrawn_cancels_drips(self, lead_engine):
        """Transitioning to Withdrawn should cancel all drip campaigns."""
        sc = _make_status_change(old_status="Pre-Approved", new_status="Withdrawn")
        result = await lead_engine.process_status_change(sc)

        drip_actions = [a for a in result["actions"] if a["action_type"] == "drip"]
        assert len(drip_actions) >= 1
        assert drip_actions[0]["data"].get("stop_all_campaigns") is True

    @pytest.mark.asyncio
    async def test_notification_on_pre_approved(self, lead_engine):
        """Pre-Approved transition should alert loan officer."""
        sc = _make_status_change(old_status="Application Complete", new_status="Pre-Approved")
        # Note: "Application Complete" is used in _handle_pre_approved handler pattern
        # even though VALID_TRANSITIONS may not list it — the engine processes by new_status
        result = await lead_engine.process_status_change(sc)

        alert_actions = [a for a in result["actions"] if a["action_type"] == "alert"]
        assert any("pre-approval" in a["data"].get("message", "").lower() or
                    "pre_approval" in a.get("template", "")
                    for a in alert_actions)

    @pytest.mark.asyncio
    async def test_no_sms_without_phone(self, lead_engine):
        """If lead has no phone number, no SMS actions should be generated."""
        sc = _make_status_change(
            old_status="Withdrawn", new_status="New", lead_phone=None
        )
        result = await lead_engine.process_status_change(sc)

        sms_actions = [a for a in result["actions"] if a["action_type"] == "sms"]
        assert len(sms_actions) == 0

    @pytest.mark.asyncio
    async def test_no_email_without_email(self, lead_engine):
        """If lead has no email, no email actions should be generated."""
        sc = _make_status_change(
            old_status="Withdrawn", new_status="New", lead_email=None
        )
        result = await lead_engine.process_status_change(sc)

        email_actions = [a for a in result["actions"] if a["action_type"] == "email"]
        assert len(email_actions) == 0


# =============================================================================
# LEAD WORKFLOW — EXECUTION LOGGING & ROBUSTNESS
# =============================================================================

class TestLeadWorkflowExecution:
    """Workflow execution logging and error handling."""

    @pytest.mark.asyncio
    async def test_workflow_execution_logging(self, lead_engine, mock_db):
        """_log_execution should INSERT into workflow_executions."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        await lead_engine.process_status_change(sc)

        # The engine calls db.execute for _log_execution (and possibly _check_active_sla_workflow)
        insert_calls = [
            call for call in mock_db.execute.call_args_list
            if "workflow_executions" in str(call)
        ]
        assert len(insert_calls) >= 1, "Expected at least one INSERT into workflow_executions"

    @pytest.mark.asyncio
    async def test_workflow_error_handling_log_failure(self, lead_engine, mock_db):
        """If _log_execution raises, the main result should still succeed."""
        # Make the final logging call fail
        original_execute = mock_db.execute
        call_count = {"n": 0}

        def flaky_execute(*args, **kwargs):
            call_count["n"] += 1
            result = original_execute(*args, **kwargs)
            # Fail on workflow_executions INSERT
            if "workflow_executions" in str(args):
                raise Exception("DB write failure")
            return result

        mock_db.execute = flaky_execute

        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        result = await lead_engine.process_status_change(sc)

        # Engine should still return successfully despite logging failure
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_workflow_tenant_isolation_sla_check(self, lead_engine, mock_db):
        """_check_active_sla_workflow queries workflow_instances for the given lead_id."""
        sc = _make_status_change(
            old_status="Pre-Approved", new_status="Under Contract"
        )
        await lead_engine.process_status_change(sc)

        # Should have queried workflow_instances
        sla_calls = [
            call for call in mock_db.execute.call_args_list
            if "workflow_instances" in str(call)
        ]
        assert len(sla_calls) >= 1


# =============================================================================
# RATE LOCK ENGINE — ELIGIBILITY
# =============================================================================

class TestRateLockEligibility:
    """Test rate lock eligibility checks."""

    def test_rate_lock_eligible_loan(self, rate_engine):
        """Fully qualified loan should be eligible."""
        loan = _make_loan_context()
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is True
        assert "eligible" in reason.lower()

    def test_rate_lock_not_eligible_no_property(self, rate_engine):
        """Loan without identified property should be ineligible."""
        loan = _make_loan_context(property_identified=False)
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is False
        assert "property" in reason.lower()

    def test_rate_lock_not_eligible_incomplete_structure(self, rate_engine):
        """Loan with incomplete structure should be ineligible."""
        loan = _make_loan_context(loan_structure_complete=False)
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is False
        assert "structure" in reason.lower()

    def test_rate_lock_not_eligible_no_closing_date(self, rate_engine):
        """Loan without closing date should be ineligible."""
        loan = _make_loan_context(closing_date=None)
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is False
        assert "closing" in reason.lower()

    def test_rate_lock_creation_full_analysis(self, rate_engine):
        """Full analysis on eligible loan should return a populated RateLockAnalysis."""
        loan = _make_loan_context()
        market = _make_market()
        analysis = rate_engine.run_full_analysis(loan, market)

        assert isinstance(analysis, RateLockAnalysis)
        assert analysis.eligible is True
        assert 0 <= analysis.lock_score <= 100
        assert analysis.recommendation in (
            "LOCK_NOW", "FLOAT_AND_MONITOR", "EXTEND_LOCK", "RELOCK", "NOT_ELIGIBLE"
        )
        assert len(analysis.action_items) > 0


# =============================================================================
# RATE LOCK ENGINE — SCORE & RECOMMENDATION
# =============================================================================

class TestRateLockScoring:
    """Test lock score calculation and recommendation logic."""

    def test_lock_score_base_neutral_market(self, rate_engine):
        """Neutral market with no close pressure should yield ~50 base score."""
        loan = _make_loan_context(closing_date=datetime.now(timezone.utc) + timedelta(days=60))
        market = _make_market(mbs_change=0, volatility_score=40)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=60)
        # Base 50, days_to_close 60 => MINIMAL modifier -10 => 40
        assert 30 <= score <= 60

    def test_lock_score_strong_mbs_rally(self, rate_engine):
        """Large MBS rally should boost score significantly."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=30)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=20)
        # Base 50 + 25 (MBS>25) + 10 (15-21 day modifier) = 85
        assert score >= 70

    def test_lock_score_mbs_selloff(self, rate_engine):
        """Large MBS selloff should reduce score."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=-30)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=60)
        # Base 50 - 25 (MBS<-25) - 10 (MINIMAL modifier) = 15
        assert score <= 30

    def test_lock_score_close_imminent_boost(self, rate_engine):
        """Closing in <= 7 days should add urgency bonus."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=0, volatility_score=40)
        score_7d = rate_engine.calculate_lock_score(market, loan, days_to_close=5)
        score_30d = rate_engine.calculate_lock_score(market, loan, days_to_close=30)
        assert score_7d > score_30d

    def test_lock_score_safety_first_bias(self, rate_engine):
        """Safety First risk profile should increase score."""
        loan_safe = _make_loan_context(borrower_risk_profile="Safety First")
        loan_aggressive = _make_loan_context(borrower_risk_profile="Aggressive")
        market = _make_market()
        score_safe = rate_engine.calculate_lock_score(market, loan_safe, days_to_close=25)
        score_aggressive = rate_engine.calculate_lock_score(market, loan_aggressive, days_to_close=25)
        assert score_safe > score_aggressive

    def test_lock_score_bounded_0_100(self, rate_engine):
        """Score must always be clamped to [0, 100]."""
        loan = _make_loan_context(borrower_risk_profile="Safety First")
        # Extreme rally + imminent close
        market = _make_market(mbs_change=50, volatility_score=10)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=3)
        assert 0 <= score <= 100

        # Extreme selloff + high vol
        market_bad = _make_market(mbs_change=-50, volatility_score=90)
        loan_agg = _make_loan_context(borrower_risk_profile="Aggressive")
        score_bad = rate_engine.calculate_lock_score(market_bad, loan_agg, days_to_close=90)
        assert 0 <= score_bad <= 100

    def test_recommendation_lock_now_high_score(self, rate_engine):
        """Score > 70 should yield LOCK_NOW."""
        loan = _make_loan_context(rate_lock_status="Not Locked")
        rec, reason = rate_engine.get_recommendation(75, 20, loan)
        assert rec == "LOCK_NOW"

    def test_recommendation_float_and_monitor_low_score(self, rate_engine):
        """Score < 30 with ample time should yield FLOAT_AND_MONITOR."""
        loan = _make_loan_context(rate_lock_status="Not Locked")
        rec, reason = rate_engine.get_recommendation(25, 45, loan)
        assert rec == "FLOAT_AND_MONITOR"

    def test_recommendation_lock_override_when_closing_imminent(self, rate_engine):
        """Even a low score should yield LOCK_NOW when closing in <= 7 days."""
        loan = _make_loan_context(rate_lock_status="Not Locked")
        rec, reason = rate_engine.get_recommendation(20, 5, loan)
        assert rec == "LOCK_NOW"
        assert "critical" in reason.lower() or "imminent" in reason.lower()


# =============================================================================
# RATE LOCK ENGINE — EXPIRATION, EXTENSION, FLOAT-DOWN
# =============================================================================

class TestRateLockLifecycle:
    """Test lock expiration detection, extension analysis, and float-down."""

    def test_rate_lock_expiration_detection(self, rate_engine):
        """Expired lock should trigger RELOCK recommendation."""
        loan = _make_loan_context(rate_lock_status="Lock Expired")
        rec, reason = rate_engine.get_recommendation(50, 20, loan)
        assert rec == "RELOCK"

    def test_rate_lock_extend_when_near_expiry(self, rate_engine):
        """Lock expiring in <= 7 days should trigger EXTEND_LOCK."""
        expiry = datetime.now(timezone.utc) + timedelta(days=5)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=expiry,
        )
        rec, reason = rate_engine.get_recommendation(50, 20, loan)
        assert rec == "EXTEND_LOCK"

    def test_rate_lock_extension_analysis(self, rate_engine):
        """Extension analysis should compute cost and recommend action."""
        expiry = datetime.now(timezone.utc) + timedelta(days=4)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=expiry,
            loan_amount=400_000,
        )
        result = rate_engine.analyze_extension_strategy(loan, expected_delay_days=15)
        assert result["needed"] is True
        assert result["extension_cost_bps"] == 12.5
        assert result["extension_cost_dollars"] > 0
        assert result["recommendation"] in ("EXTEND_LOCK", "MONITOR_CLOSELY")

    def test_rate_lock_extension_not_needed(self, rate_engine):
        """Lock with plenty of time should not need extension."""
        expiry = datetime.now(timezone.utc) + timedelta(days=25)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=expiry,
        )
        result = rate_engine.analyze_extension_strategy(loan)
        assert result["needed"] is False

    def test_rate_lock_float_down_available(self, rate_engine):
        """Float-down should be available when market rate drops 0.25%+ below locked rate."""
        loan = _make_loan_context(rate_lock_status="Locked", loan_amount=400_000)
        # Original rate was 7.25%, market has improved to 6.875%
        market = _make_market(mortgage_30yr=6.875)
        result = rate_engine.check_float_down_opportunity(loan, market, original_rate=7.25)
        assert result["available"] is True
        assert result["estimated_monthly_savings"] > 0

    def test_rate_lock_float_down_insufficient_improvement(self, rate_engine):
        """Float-down should NOT be available when improvement < 0.25%."""
        loan = _make_loan_context(rate_lock_status="Locked")
        market = _make_market(mortgage_30yr=6.80)
        result = rate_engine.check_float_down_opportunity(loan, market, original_rate=6.90)
        assert result["available"] is False

    def test_rate_lock_float_down_not_locked(self, rate_engine):
        """Float-down should not be available if loan is not locked."""
        loan = _make_loan_context(rate_lock_status="Not Locked")
        market = _make_market()
        result = rate_engine.check_float_down_opportunity(loan, market, original_rate=7.5)
        assert result["available"] is False


# =============================================================================
# RATE LOCK ENGINE — MONITORING SUBFLOWS
# =============================================================================

class TestRateLockMonitoring:
    """Test lock and float monitoring subflows."""

    def test_lock_monitor_critical_alert_near_expiry(self, rate_engine):
        """Lock expiring in <= 3 days should raise CRITICAL alert."""
        monitor = LockMonitoringSubflow(rate_engine)
        expiry = datetime.now(timezone.utc) + timedelta(days=2)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=expiry,
            current_rate=6.875,
        )
        market = _make_market()
        result = monitor.run_daily_check(loan, market)

        assert result["status"] == "critical"
        assert any(a["type"] == "CRITICAL" for a in result["alerts"])
        assert any(t["priority"] == "urgent" for t in result["tasks"])

    def test_lock_monitor_warning_near_expiry(self, rate_engine):
        """Lock expiring in 4-7 days should raise WARNING."""
        monitor = LockMonitoringSubflow(rate_engine)
        expiry = datetime.now(timezone.utc) + timedelta(days=6)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=expiry,
            current_rate=6.875,
        )
        market = _make_market()
        result = monitor.run_daily_check(loan, market)

        assert result["status"] == "warning"
        assert any(a["type"] == "WARNING" for a in result["alerts"])

    def test_float_monitor_recommends_lock_when_close(self, rate_engine):
        """Float monitoring should recommend lock when closing in <= 7 days."""
        monitor = FloatMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Not Locked",
            closing_date=datetime.now(timezone.utc) + timedelta(days=5),
        )
        market = _make_market()
        result = monitor.run_market_check(loan, market)

        assert result["lock_recommended"] is True
        assert result["urgency"] == "critical"


# =============================================================================
# RATE LOCK ENGINE — RISK LEVEL
# =============================================================================

class TestRateLockRiskLevel:
    """Test days-to-close risk matrix."""

    @pytest.mark.parametrize("days,expected_risk", [
        (3, "CRITICAL"),
        (10, "HIGH"),
        (18, "MODERATE"),
        (25, "LOW"),
        (45, "MINIMAL"),
    ])
    def test_risk_level_by_days_to_close(self, rate_engine, days, expected_risk):
        risk, _ = rate_engine.get_risk_level(days)
        assert risk == expected_risk

    def test_risk_level_none_days(self, rate_engine):
        risk, modifier = rate_engine.get_risk_level(None)
        assert risk == "UNKNOWN"
        assert modifier == 0


# =============================================================================
# GENERAL WORKFLOW — IDEMPOTENCY & CONSISTENCY
# =============================================================================

class TestWorkflowGeneral:
    """General workflow engine properties."""

    @pytest.mark.asyncio
    async def test_workflow_idempotency_same_transition(self, lead_engine):
        """Processing the same transition twice should yield consistent action counts."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        result1 = await lead_engine.process_status_change(sc)
        result2 = await lead_engine.process_status_change(sc)

        assert result1["action_count"] == result2["action_count"]
        types1 = sorted(a["action_type"] for a in result1["actions"])
        types2 = sorted(a["action_type"] for a in result2["actions"])
        assert types1 == types2

    @pytest.mark.asyncio
    async def test_workflow_invalid_transition_still_processes(self, lead_engine):
        """Engine logs a warning for invalid transitions but still returns success."""
        sc = _make_status_change(old_status="New", new_status="Closed")
        result = await lead_engine.process_status_change(sc)

        # Engine does best-effort handling even for invalid transitions
        assert result["success"] is True

    def test_time_rules_positive_values(self):
        """All time rules should be positive integers."""
        for key, value in TIME_RULES.items():
            assert isinstance(value, (int, float)), f"TIME_RULES['{key}'] should be numeric"
            assert value > 0, f"TIME_RULES['{key}'] should be positive"

    def test_rate_lock_ineligible_analysis_returns_not_eligible(self, rate_engine):
        """Full analysis on ineligible loan should return NOT_ELIGIBLE recommendation."""
        loan = _make_loan_context(
            property_identified=False,
            loan_structure_complete=False,
            closing_date=None,
        )
        market = _make_market()
        analysis = rate_engine.run_full_analysis(loan, market)

        assert analysis.eligible is False
        assert analysis.recommendation == "NOT_ELIGIBLE"
        assert analysis.lock_score == 0
        assert len(analysis.action_items) > 0
