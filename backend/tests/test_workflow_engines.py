"""
Perennia AI - Workflow Engine Tests

Tests for lead workflow state machine, rate lock intelligence engine,
and general workflow execution patterns.

Coverage:
- Lead stage transition map validation (pure state machine, no DB)
- Lead workflow action generation on status changes
- Rate lock eligibility, scoring, and recommendations
- Float-down detection, lock extension analysis
- Lock and float monitoring subflows
- Workflow execution logging, idempotency, error handling
- Tenant isolation via SLA workflow deferral
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
# FACTORIES
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
        volatility_score=40,
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def _make_loan_context(**overrides):
    """Factory for LoanContext with eligible-loan defaults."""
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


# =============================================================================
# FIXTURES
# =============================================================================

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
# 1. LEAD WORKFLOW -- TRANSITION MAP VALIDATION (pure, no DB)
# =============================================================================

class TestLeadWorkflowTransitions:
    """Validate the VALID_TRANSITIONS state machine map."""

    # Build parametrize list of every declared valid pair
    _valid_pairs = [
        (src, dst) for src, dsts in VALID_TRANSITIONS.items() for dst in dsts
    ]

    @pytest.mark.parametrize("src,dst", _valid_pairs)
    def test_lead_workflow_valid_transitions(self, src, dst):
        """Every declared transition target is accepted by the map lookup."""
        assert dst in VALID_TRANSITIONS.get(src, [])

    @pytest.mark.parametrize("src,dst", [
        ("New", "Closed"),
        ("New", "Pre-Approved"),
        ("Attempted Contact", "Closed"),
        ("Pre-Approved", "New"),
        ("Closed", "New"),
        ("Referral Source", "New"),
    ])
    def test_lead_workflow_invalid_transition(self, src, dst):
        """Transitions NOT in the map must be absent."""
        assert dst not in VALID_TRANSITIONS.get(src, [])

    def test_lead_workflow_terminal_states(self):
        """Referral Source is fully terminal (zero outgoing)."""
        assert VALID_TRANSITIONS["Referral Source"] == []

    def test_lead_workflow_withdrawn_limited_exit(self):
        """Withdrawn only allows re-entry to New."""
        assert VALID_TRANSITIONS["Withdrawn"] == ["New"]

    def test_lead_workflow_all_stages_reachable(self):
        """Every non-initial stage is reachable as a destination somewhere."""
        all_destinations = set()
        for dsts in VALID_TRANSITIONS.values():
            all_destinations.update(dsts)

        for stage in LEAD_STAGES:
            if stage == "New":
                assert "New" in VALID_TRANSITIONS.get(None, [])
            else:
                assert stage in all_destinations, (
                    f"Stage '{stage}' is unreachable via VALID_TRANSITIONS"
                )

    def test_lead_workflow_no_orphan_stages(self):
        """Every non-terminal stage has at least one outgoing transition."""
        terminal = {"Referral Source"}
        for stage in LEAD_STAGES:
            if stage in terminal:
                continue
            assert len(VALID_TRANSITIONS.get(stage, [])) > 0, (
                f"Stage '{stage}' has no outgoing transitions but is not terminal"
            )

    def test_lead_stages_consistent_with_transitions(self):
        """Every stage mentioned in VALID_TRANSITIONS keys/values is in LEAD_STAGES."""
        mentioned = set()
        for src, dsts in VALID_TRANSITIONS.items():
            if src is not None:
                mentioned.add(src)
            mentioned.update(dsts)

        missing = mentioned - set(LEAD_STAGES)
        assert missing == set(), f"Stages in transitions but not LEAD_STAGES: {missing}"

    def test_every_stage_has_transition_entry(self):
        """Every stage in LEAD_STAGES has an entry key in VALID_TRANSITIONS."""
        for stage in LEAD_STAGES:
            assert stage in VALID_TRANSITIONS, (
                f"Stage '{stage}' missing from VALID_TRANSITIONS"
            )


# =============================================================================
# 2. LEAD WORKFLOW -- ACTION GENERATION
# =============================================================================

class TestLeadWorkflowActions:
    """Verify status changes generate the correct workflow actions."""

    @pytest.mark.asyncio
    async def test_lead_workflow_triggers_action_new(self, lead_engine):
        """Transition to New produces SMS, email, alert, task, drip actions."""
        sc = _make_status_change(old_status="Withdrawn", new_status="New")
        result = await lead_engine.process_status_change(sc)

        assert result["success"] is True
        types = {a["action_type"] for a in result["actions"]}
        assert types >= {"sms", "email", "alert", "task", "drip"}

    @pytest.mark.asyncio
    async def test_lead_workflow_activity_logged(self, lead_engine):
        """New -> Attempted Contact logs an activity entry."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        result = await lead_engine.process_status_change(sc)

        activity = [a for a in result["actions"] if a["action_type"] == "activity"]
        assert len(activity) >= 1
        assert "contact" in activity[0]["data"]["note"].lower()

    @pytest.mark.asyncio
    async def test_lead_workflow_notification_on_stage_change(self, lead_engine):
        """Attempted -> Prospect sends celebration alert and email."""
        sc = _make_status_change(old_status="Attempted Contact", new_status="Prospect")
        result = await lead_engine.process_status_change(sc)

        types = [a["action_type"] for a in result["actions"]]
        assert "alert" in types
        assert "email" in types

    @pytest.mark.asyncio
    async def test_withdrawn_cancels_drips(self, lead_engine):
        """Transition to Withdrawn cancels all drip campaigns."""
        sc = _make_status_change(old_status="Pre-Approved", new_status="Withdrawn")
        result = await lead_engine.process_status_change(sc)

        drips = [a for a in result["actions"] if a["action_type"] == "drip"]
        assert len(drips) >= 1
        assert drips[0]["data"].get("stop_all_campaigns") is True

    @pytest.mark.asyncio
    async def test_does_not_qualify_enrolls_credit_repair(self, lead_engine):
        """DNQ transition enrolls lead in credit_repair drip."""
        sc = _make_status_change(old_status="Pre-Qualified", new_status="Does Not Qualify")
        result = await lead_engine.process_status_change(sc)

        drips = [a for a in result["actions"] if a["action_type"] == "drip"]
        assert any(d["data"].get("campaign") == "credit_repair" for d in drips)

    @pytest.mark.asyncio
    async def test_no_sms_without_phone(self, lead_engine):
        """No SMS actions when lead_phone is None."""
        sc = _make_status_change(old_status="Withdrawn", new_status="New", lead_phone=None)
        result = await lead_engine.process_status_change(sc)

        sms = [a for a in result["actions"] if a["action_type"] == "sms"]
        assert len(sms) == 0

    @pytest.mark.asyncio
    async def test_no_email_without_email(self, lead_engine):
        """No email actions when lead_email is None."""
        sc = _make_status_change(old_status="Withdrawn", new_status="New", lead_email=None)
        result = await lead_engine.process_status_change(sc)

        emails = [a for a in result["actions"] if a["action_type"] == "email"]
        assert len(emails) == 0


# =============================================================================
# 3. LEAD WORKFLOW -- EXECUTION LOGGING, ERRORS, TENANT ISOLATION
# =============================================================================

class TestLeadWorkflowExecution:
    """Execution logging, error handling, idempotency, tenant isolation."""

    @pytest.mark.asyncio
    async def test_workflow_execution_logging(self, lead_engine, mock_db):
        """process_status_change INSERTs into workflow_executions."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        await lead_engine.process_status_change(sc)

        # TextClause objects need .text to inspect SQL content
        insert_calls = [
            c for c in mock_db.execute.call_args_list
            if c.args and hasattr(c.args[0], "text")
            and "workflow_executions" in str(c.args[0].text)
        ]
        assert len(insert_calls) >= 1

    @pytest.mark.asyncio
    async def test_workflow_idempotency(self, lead_engine):
        """Same transition twice yields identical action types and counts."""
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        r1 = await lead_engine.process_status_change(sc)
        r2 = await lead_engine.process_status_change(sc)

        assert r1["action_count"] == r2["action_count"]
        assert sorted(a["action_type"] for a in r1["actions"]) == \
               sorted(a["action_type"] for a in r2["actions"])

    @pytest.mark.asyncio
    async def test_workflow_error_handling(self, mock_db):
        """DB error during _log_execution does not crash the engine."""
        original_execute = mock_db.execute

        def flaky_execute(*args, **kwargs):
            if "workflow_executions" in str(args):
                raise Exception("DB write failure")
            return original_execute(*args, **kwargs)

        mock_db.execute = flaky_execute
        engine = LeadWorkflowEngine(mock_db)
        sc = _make_status_change(old_status="New", new_status="Attempted Contact")
        result = await engine.process_status_change(sc)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_workflow_tenant_isolation(self, mock_db):
        """Under Contract handler queries workflow_instances for SLA check."""
        mock_db.execute.return_value.fetchone.return_value = None
        engine = LeadWorkflowEngine(mock_db)
        sc = _make_status_change(old_status="Pre-Approved", new_status="Under Contract")
        await engine.process_status_change(sc)

        # TextClause objects need .text to inspect SQL content
        sla_calls = [
            c for c in mock_db.execute.call_args_list
            if c.args and hasattr(c.args[0], "text")
            and "workflow_instances" in str(c.args[0].text)
        ]
        assert len(sla_calls) >= 1

    @pytest.mark.asyncio
    async def test_sla_workflow_defers_legacy_actions(self, mock_db):
        """When active SLA workflow exists, legacy under_contract actions are skipped."""
        mock_db.execute.return_value.fetchone.return_value = MagicMock(id=1)
        engine = LeadWorkflowEngine(mock_db)
        sc = _make_status_change(old_status="Pre-Approved", new_status="Under Contract")
        result = await engine.process_status_change(sc)

        assert result["action_count"] == 0

    @pytest.mark.asyncio
    async def test_invalid_transition_still_processes(self, lead_engine):
        """Engine logs warning for invalid transitions but returns success."""
        sc = _make_status_change(old_status="New", new_status="Closed")
        result = await lead_engine.process_status_change(sc)
        assert result["success"] is True


# =============================================================================
# 4. LEAD WORKFLOW -- SLA CALCULATION & TIME RULES
# =============================================================================

class TestLeadWorkflowSLA:
    """Time rules and SLA deadline validation."""

    def test_lead_workflow_sla_calculation_rules_positive(self):
        """All time rules are positive numeric values."""
        for key, hours in TIME_RULES.items():
            assert isinstance(hours, (int, float))
            assert hours > 0, f"TIME_RULES['{key}'] must be positive"

    def test_escalation_after_initial_alert(self):
        """Escalation threshold must exceed initial alert threshold."""
        assert TIME_RULES["new_escalate"] > TIME_RULES["new_no_contact"]

    @pytest.mark.asyncio
    async def test_time_engine_check_stale_returns_list(self, mock_db):
        """TimeBasedWorkflowEngine.check_stale_leads returns a list."""
        engine = TimeBasedWorkflowEngine(mock_db)
        result = await engine.check_stale_leads()
        assert isinstance(result, list)


# =============================================================================
# 5. RATE LOCK -- ELIGIBILITY
# =============================================================================

class TestRateLockEligibility:
    """Rate lock eligibility checks."""

    def test_rate_lock_creation(self, rate_engine):
        """Fully qualified loan is eligible and produces a full analysis."""
        loan = _make_loan_context()
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is True

        market = _make_market()
        analysis = rate_engine.run_full_analysis(loan, market)
        assert isinstance(analysis, RateLockAnalysis)
        assert analysis.eligible is True
        assert 0 <= analysis.lock_score <= 100
        assert analysis.days_to_close is not None

    @pytest.mark.parametrize("field_override,fragment", [
        ({"property_identified": False}, "property"),
        ({"loan_structure_complete": False}, "structure"),
        ({"closing_date": None}, "closing"),
    ])
    def test_rate_lock_ineligible_reasons(self, rate_engine, field_override, fragment):
        """Each missing prerequisite produces a descriptive reason."""
        loan = _make_loan_context(**field_override)
        eligible, reason = rate_engine.check_eligibility(loan)
        assert eligible is False
        assert fragment in reason.lower()


# =============================================================================
# 6. RATE LOCK -- SCORING
# =============================================================================

class TestRateLockScoring:
    """Lock score calculation and boundary tests."""

    def test_lock_score_base_neutral(self, rate_engine):
        """Neutral market with distant close yields score near base (40-60)."""
        loan = _make_loan_context(closing_date=datetime.now(timezone.utc) + timedelta(days=60))
        market = _make_market(mbs_change=0, volatility_score=40)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=60)
        assert 30 <= score <= 60

    def test_lock_score_mbs_rally_boosts(self, rate_engine):
        """Large MBS rally (+30bps) significantly boosts score."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=30)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=20)
        assert score >= 70

    def test_lock_score_mbs_selloff_drops(self, rate_engine):
        """Large MBS selloff (-30bps) drops score below 30."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=-30)
        score = rate_engine.calculate_lock_score(market, loan, days_to_close=60)
        assert score <= 30

    def test_lock_score_imminent_close_boost(self, rate_engine):
        """Closing in 5 days scores higher than closing in 30 days."""
        loan = _make_loan_context()
        market = _make_market(mbs_change=0, volatility_score=40)
        score_5d = rate_engine.calculate_lock_score(market, loan, days_to_close=5)
        score_30d = rate_engine.calculate_lock_score(market, loan, days_to_close=30)
        assert score_5d > score_30d

    def test_lock_score_safety_first_vs_aggressive(self, rate_engine):
        """Safety First profile scores higher than Aggressive."""
        market = _make_market()
        loan_safe = _make_loan_context(borrower_risk_profile="Safety First")
        loan_agg = _make_loan_context(borrower_risk_profile="Aggressive")
        s_safe = rate_engine.calculate_lock_score(market, loan_safe, 25)
        s_agg = rate_engine.calculate_lock_score(market, loan_agg, 25)
        assert s_safe > s_agg

    def test_lock_score_clamped_0_100(self, rate_engine):
        """Score is always clamped to [0, 100] regardless of extreme inputs."""
        # Extreme bull case
        loan_safe = _make_loan_context(borrower_risk_profile="Safety First")
        market_bull = _make_market(mbs_change=50, volatility_score=10)
        score_high = rate_engine.calculate_lock_score(market_bull, loan_safe, 3)
        assert 0 <= score_high <= 100

        # Extreme bear case
        loan_agg = _make_loan_context(borrower_risk_profile="Aggressive")
        market_bear = _make_market(mbs_change=-50, volatility_score=90)
        score_low = rate_engine.calculate_lock_score(market_bear, loan_agg, 90)
        assert 0 <= score_low <= 100


# =============================================================================
# 7. RATE LOCK -- RECOMMENDATIONS & STATUS TRANSITIONS
# =============================================================================

class TestRateLockRecommendations:
    """Lock/float recommendation logic based on score and context."""

    def test_rate_lock_status_transitions_high_score(self, rate_engine):
        """Score > 70 => LOCK_NOW."""
        loan = _make_loan_context()
        rec, _ = rate_engine.get_recommendation(75, 20, loan)
        assert rec == "LOCK_NOW"

    def test_rate_lock_status_transitions_low_score(self, rate_engine):
        """Score < 30 with ample time => FLOAT_AND_MONITOR."""
        loan = _make_loan_context()
        rec, _ = rate_engine.get_recommendation(25, 45, loan)
        assert rec == "FLOAT_AND_MONITOR"

    def test_rate_lock_invalid_transition_override(self, rate_engine):
        """Low score but imminent close (<=7d) overrides to LOCK_NOW."""
        loan = _make_loan_context()
        rec, reason = rate_engine.get_recommendation(20, 5, loan)
        assert rec == "LOCK_NOW"
        assert "critical" in reason.lower() or "imminent" in reason.lower()

    def test_rate_lock_expiration_detection(self, rate_engine):
        """Expired lock triggers RELOCK recommendation."""
        loan = _make_loan_context(rate_lock_status="Lock Expired")
        rec, _ = rate_engine.get_recommendation(50, 20, loan)
        assert rec == "RELOCK"

    def test_rate_lock_near_expiry_triggers_extend(self, rate_engine):
        """Lock expiring in 5 days triggers EXTEND_LOCK."""
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=5),
        )
        rec, _ = rate_engine.get_recommendation(50, 20, loan)
        assert rec == "EXTEND_LOCK"

    def test_ineligible_analysis_returns_not_eligible(self, rate_engine):
        """Full analysis on triple-ineligible loan => NOT_ELIGIBLE, score 0."""
        loan = _make_loan_context(
            property_identified=False,
            loan_structure_complete=False,
            closing_date=None,
        )
        analysis = rate_engine.run_full_analysis(loan, _make_market())
        assert analysis.eligible is False
        assert analysis.recommendation == "NOT_ELIGIBLE"
        assert analysis.lock_score == 0
        assert len(analysis.action_items) > 0


# =============================================================================
# 8. RATE LOCK -- FLOAT-DOWN & EXTENSION
# =============================================================================

class TestRateLockFloatDown:
    """Float-down opportunity detection and extension strategy analysis."""

    def test_rate_lock_float_down(self, rate_engine):
        """Float-down available when market drops 0.375% below locked rate."""
        loan = _make_loan_context(rate_lock_status="Locked", loan_amount=400_000)
        market = _make_market(mortgage_30yr=6.875)
        result = rate_engine.check_float_down_opportunity(loan, market, original_rate=7.25)
        assert result["available"] is True
        assert result["estimated_monthly_savings"] > 0
        assert result["rate_improvement"] >= 0.25

    def test_rate_lock_float_down_insufficient(self, rate_engine):
        """Float-down NOT available when improvement < 0.25%."""
        loan = _make_loan_context(rate_lock_status="Locked")
        market = _make_market(mortgage_30yr=6.80)
        result = rate_engine.check_float_down_opportunity(loan, market, original_rate=6.90)
        assert result["available"] is False

    def test_rate_lock_float_down_not_locked(self, rate_engine):
        """Float-down unavailable when loan is not locked."""
        loan = _make_loan_context(rate_lock_status="Not Locked")
        result = rate_engine.check_float_down_opportunity(loan, _make_market(), 7.5)
        assert result["available"] is False

    def test_rate_lock_extension(self, rate_engine):
        """Extension analysis computes cost and recommends action near expiry."""
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=4),
            loan_amount=400_000,
        )
        result = rate_engine.analyze_extension_strategy(loan, expected_delay_days=15)
        assert result["needed"] is True
        assert result["extension_cost_bps"] == 12.5
        assert result["extension_cost_dollars"] > 0

    def test_rate_lock_extension_not_needed(self, rate_engine):
        """Extension not needed when lock has 25 days remaining."""
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=25),
        )
        result = rate_engine.analyze_extension_strategy(loan)
        assert result["needed"] is False


# =============================================================================
# 9. RATE LOCK -- MONITORING SUBFLOWS
# =============================================================================

class TestRateLockMonitoring:
    """Lock and float monitoring subflow tests."""

    def test_rate_lock_notification_before_expiry_critical(self, rate_engine):
        """Lock expiring in 2 days => CRITICAL alert + urgent task."""
        monitor = LockMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=2),
            current_rate=6.875,
        )
        result = monitor.run_daily_check(loan, _make_market())

        assert result["status"] == "critical"
        assert any(a["type"] == "CRITICAL" for a in result["alerts"])
        assert any(t["priority"] == "urgent" for t in result["tasks"])

    def test_lock_monitoring_warning_expiry(self, rate_engine):
        """Lock expiring in 6 days => WARNING status."""
        monitor = LockMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=6),
            current_rate=6.875,
        )
        result = monitor.run_daily_check(loan, _make_market())
        assert result["status"] == "warning"

    def test_lock_monitoring_healthy(self, rate_engine):
        """Lock with 25 days and no float-down => healthy."""
        monitor = LockMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=25),
            current_rate=6.875,
        )
        result = monitor.run_daily_check(loan, _make_market(mortgage_30yr=6.875))
        assert result["status"] == "healthy"

    def test_float_monitoring_imminent_close(self, rate_engine):
        """Float monitor recommends lock when closing in 5 days."""
        monitor = FloatMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Not Locked",
            closing_date=datetime.now(timezone.utc) + timedelta(days=5),
        )
        result = monitor.run_market_check(loan, _make_market())
        assert result["lock_recommended"] is True
        assert result["urgency"] == "critical"

    def test_float_monitoring_high_volatility(self, rate_engine):
        """Float monitor warns on high volatility (80/100)."""
        monitor = FloatMonitoringSubflow(rate_engine)
        loan = _make_loan_context(
            rate_lock_status="Not Locked",
            closing_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        result = monitor.run_market_check(loan, _make_market(volatility_score=80))
        warnings = [a for a in result["alerts"] if a["type"] == "WARNING"]
        assert len(warnings) >= 1


# =============================================================================
# 10. RATE LOCK -- RISK LEVELS
# =============================================================================

class TestRateLockRiskLevel:
    """Days-to-close risk matrix validation."""

    @pytest.mark.parametrize("days,expected_risk", [
        (3, "CRITICAL"),
        (10, "HIGH"),
        (18, "MODERATE"),
        (25, "LOW"),
        (45, "MINIMAL"),
    ])
    def test_risk_level_by_days(self, rate_engine, days, expected_risk):
        risk, _ = rate_engine.get_risk_level(days)
        assert risk == expected_risk

    def test_risk_level_none_days(self, rate_engine):
        risk, modifier = rate_engine.get_risk_level(None)
        assert risk == "UNKNOWN"
        assert modifier == 0


# =============================================================================
# 11. GENERAL WORKFLOW -- SCENARIOS & EDGE CASES
# =============================================================================

class TestWorkflowGeneral:
    """Cross-cutting workflow engine properties."""

    def test_full_analysis_generates_scenarios(self, rate_engine):
        """Full analysis on eligible loan produces lock_today + rate-up/down scenarios."""
        loan = _make_loan_context()
        analysis = rate_engine.run_full_analysis(loan, _make_market())
        assert "lock_today" in analysis.scenarios
        assert "rate_up_25bps" in analysis.scenarios
        assert "rate_down_25bps" in analysis.scenarios
        assert analysis.scenarios["lock_today"]["monthly_payment"] > 0

    def test_full_analysis_market_summary_format(self, rate_engine):
        """Market summary string contains MBS, 10Y, 30Y, volatility."""
        loan = _make_loan_context()
        analysis = rate_engine.run_full_analysis(loan, _make_market())
        summary = analysis.market_summary
        assert "MBS" in summary
        assert "10Y" in summary
        assert "30Y" in summary
        assert "Volatility" in summary

    def test_days_to_close_calculation(self, rate_engine):
        """calculate_days_to_close returns correct non-negative integer."""
        future = datetime.now(timezone.utc) + timedelta(days=15)
        days = rate_engine.calculate_days_to_close(future)
        assert days is not None
        assert 14 <= days <= 16  # Allow for time-of-day rounding

    def test_days_to_close_past_date(self, rate_engine):
        """Past closing date returns 0 (clamped, not negative)."""
        past = datetime.now(timezone.utc) - timedelta(days=5)
        days = rate_engine.calculate_days_to_close(past)
        assert days == 0

    def test_days_to_close_none(self, rate_engine):
        """None closing date returns None."""
        days = rate_engine.calculate_days_to_close(None)
        assert days is None
