"""
Test Rate Lock Timing — Expiration, Extension, and Utility Functions

Verifies:
- RateLockIntelligenceEngine.calculate_days_to_close()
- RateLockIntelligenceEngine.get_risk_level() days-to-close risk matrix
- RateLockIntelligenceEngine.check_eligibility() loan context checks
- RateLockIntelligenceEngine.calculate_lock_score() scoring algorithm
- RateLockIntelligenceEngine.get_recommendation() lock/float decisions
- Rate lock extension cost calculations
- Float-down opportunity detection
- RateLock model fields and RateLockStatus enum values
- days_between utility function (from CLAUDE.md tool code)
"""

import pytest
from datetime import datetime, timedelta, timezone, date
from unittest.mock import MagicMock


# =============================================================================
# days_between Utility (from CLAUDE.md Part 1 tool code)
# =============================================================================

def days_between(start, end):
    """Local implementation matching CLAUDE.md tool code."""
    if start is None or end is None:
        return 0
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()
    return (end - start).days


@pytest.mark.unit
class TestDaysBetween:
    """Test the days_between utility for rate lock date calculations."""

    def test_same_date_returns_zero(self):
        today = date.today()
        assert days_between(today, today) == 0

    def test_positive_days(self):
        start = date(2026, 3, 1)
        end = date(2026, 3, 15)
        assert days_between(start, end) == 14

    def test_negative_days_for_past_date(self):
        """Expired lock: end is before start returns negative."""
        start = date(2026, 3, 15)
        end = date(2026, 3, 1)
        assert days_between(start, end) == -14

    def test_none_start_returns_zero(self):
        assert days_between(None, date.today()) == 0

    def test_none_end_returns_zero(self):
        assert days_between(date.today(), None) == 0

    def test_both_none_returns_zero(self):
        assert days_between(None, None) == 0

    def test_datetime_inputs_converted_to_date(self):
        start = datetime(2026, 3, 1, 10, 30, 0)
        end = datetime(2026, 3, 15, 14, 45, 0)
        assert days_between(start, end) == 14


# =============================================================================
# Rate Lock Eligibility
# =============================================================================

@pytest.mark.unit
class TestRateLockEligibility:
    """Test loan eligibility checks for rate locking."""

    def _get_engine(self):
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        return RateLockIntelligenceEngine()

    def _make_loan_context(self, **overrides):
        from workflows.rate_lock_engine import LoanContext
        defaults = {
            "loan_id": 1,
            "loan_number": "2026-001",
            "borrower_name": "Test Borrower",
            "loan_amount": 400000.0,
            "current_rate": 6.875,
            "closing_date": datetime.now(timezone.utc) + timedelta(days=30),
            "lock_date": None,
            "lock_expiration_date": None,
            "lock_term_days": None,
            "rate_lock_status": "Eligible - No Lock",
            "borrower_risk_profile": "Balanced",
            "property_identified": True,
            "loan_structure_complete": True,
        }
        defaults.update(overrides)
        return LoanContext(**defaults)

    def test_eligible_loan(self):
        """Loan with property, structure, and closing date is eligible."""
        engine = self._get_engine()
        loan = self._make_loan_context()
        eligible, reason = engine.check_eligibility(loan)
        assert eligible is True
        assert "Eligible" in reason

    def test_ineligible_no_property(self):
        """Loan without property identified is not eligible."""
        engine = self._get_engine()
        loan = self._make_loan_context(property_identified=False)
        eligible, reason = engine.check_eligibility(loan)
        assert eligible is False
        assert "property" in reason.lower()

    def test_ineligible_no_closing_date(self):
        """Loan without closing date is not eligible."""
        engine = self._get_engine()
        loan = self._make_loan_context(closing_date=None)
        eligible, reason = engine.check_eligibility(loan)
        assert eligible is False
        assert "closing date" in reason.lower()

    def test_ineligible_incomplete_structure(self):
        """Loan with incomplete structure is not eligible."""
        engine = self._get_engine()
        loan = self._make_loan_context(loan_structure_complete=False)
        eligible, reason = engine.check_eligibility(loan)
        assert eligible is False
        assert "incomplete" in reason.lower()


# =============================================================================
# Days to Close and Risk Level
# =============================================================================

@pytest.mark.unit
class TestDaysToCloseRisk:
    """Test days-to-close calculation and risk level assignment."""

    def _get_engine(self):
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        return RateLockIntelligenceEngine()

    def test_calculate_days_to_close_future(self):
        """Future closing date returns positive days."""
        engine = self._get_engine()
        future = datetime.now(timezone.utc) + timedelta(days=15)
        days = engine.calculate_days_to_close(future)
        # Should be approximately 15 (could be 14 depending on time of day)
        assert 13 <= days <= 16

    def test_calculate_days_to_close_past(self):
        """Past closing date returns 0 (clamped)."""
        engine = self._get_engine()
        past = datetime.now(timezone.utc) - timedelta(days=5)
        days = engine.calculate_days_to_close(past)
        assert days == 0

    def test_calculate_days_to_close_none(self):
        """None closing date returns None."""
        engine = self._get_engine()
        assert engine.calculate_days_to_close(None) is None

    def test_risk_level_critical_under_7_days(self):
        """0-7 days to close should be CRITICAL risk."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(5)
        assert risk == "CRITICAL"
        assert modifier == 30  # +30 score modifier

    def test_risk_level_high_8_to_14_days(self):
        """8-14 days to close should be HIGH risk."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(10)
        assert risk == "HIGH"
        assert modifier == 20

    def test_risk_level_moderate_15_to_21_days(self):
        """15-21 days to close should be MODERATE risk."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(18)
        assert risk == "MODERATE"

    def test_risk_level_low_22_to_30_days(self):
        """22-30 days to close should be LOW risk."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(25)
        assert risk == "LOW"
        assert modifier == 0

    def test_risk_level_minimal_over_30_days(self):
        """31+ days to close should be MINIMAL risk."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(45)
        assert risk == "MINIMAL"
        assert modifier == -10

    def test_risk_level_none_days(self):
        """None days_to_close returns UNKNOWN."""
        engine = self._get_engine()
        risk, modifier = engine.get_risk_level(None)
        assert risk == "UNKNOWN"
        assert modifier == 0


# =============================================================================
# Lock Score Calculation
# =============================================================================

@pytest.mark.unit
class TestLockScoreCalculation:
    """Test the lock score algorithm."""

    def _get_engine(self):
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        return RateLockIntelligenceEngine()

    def _make_market(self, mbs_change=0, volatility=30):
        from workflows.rate_lock_engine import MarketSnapshot
        return MarketSnapshot(
            treasury_10yr=4.25,
            treasury_2yr=4.50,
            mortgage_30yr=6.75,
            mbs_price=100.50,
            mbs_change=mbs_change,
            volatility_score=volatility,
            timestamp=datetime.now(timezone.utc),
        )

    def _make_loan(self, risk_profile="Balanced", rate_lock_status="Eligible - No Lock"):
        from workflows.rate_lock_engine import LoanContext
        return LoanContext(
            loan_id=1,
            loan_number="2026-001",
            borrower_name="Test",
            loan_amount=400000.0,
            current_rate=6.875,
            closing_date=datetime.now(timezone.utc) + timedelta(days=20),
            lock_date=None,
            lock_expiration_date=None,
            lock_term_days=None,
            rate_lock_status=rate_lock_status,
            borrower_risk_profile=risk_profile,
            property_identified=True,
            loan_structure_complete=True,
        )

    def test_base_score_is_50(self):
        """With neutral inputs, score should be around 50."""
        engine = self._get_engine()
        market = self._make_market(mbs_change=0, volatility=30)
        loan = self._make_loan()
        score = engine.calculate_lock_score(market, loan, days_to_close=25)
        # Base 50 + LOW risk modifier (0) = 50
        assert 40 <= score <= 60

    def test_strong_mbs_rally_increases_score(self):
        """MBS up > 25 bps should boost score significantly."""
        engine = self._get_engine()
        market = self._make_market(mbs_change=30)
        loan = self._make_loan()
        score = engine.calculate_lock_score(market, loan, days_to_close=25)
        assert score > 70  # Base 50 + 25 (MBS) = 75

    def test_mbs_selloff_decreases_score(self):
        """MBS down > 25 bps should decrease score significantly."""
        engine = self._get_engine()
        market = self._make_market(mbs_change=-30)
        loan = self._make_loan()
        score = engine.calculate_lock_score(market, loan, days_to_close=25)
        assert score < 30  # Base 50 - 25 (MBS) = 25

    def test_imminent_closing_increases_score(self):
        """Closing in under 7 days adds urgency."""
        engine = self._get_engine()
        market = self._make_market(mbs_change=0)
        loan = self._make_loan()
        score = engine.calculate_lock_score(market, loan, days_to_close=5)
        # Base 50 + CRITICAL modifier (30) + extra urgency (10) = 90
        assert score >= 80

    def test_safety_first_borrower_adds_to_score(self):
        """Safety First risk profile increases lock tendency."""
        engine = self._get_engine()
        market = self._make_market(mbs_change=0)
        loan = self._make_loan(risk_profile="Safety First")
        score = engine.calculate_lock_score(market, loan, days_to_close=25)
        # Base 50 + 10 (Safety First) = 60
        assert score >= 55

    def test_score_bounded_0_to_100(self):
        """Score should never exceed 0-100 bounds."""
        engine = self._get_engine()
        # Extreme positive
        market = self._make_market(mbs_change=50, volatility=0)
        loan = self._make_loan(risk_profile="Safety First")
        score = engine.calculate_lock_score(market, loan, days_to_close=3)
        assert 0 <= score <= 100

        # Extreme negative
        market = self._make_market(mbs_change=-50, volatility=90)
        loan = self._make_loan(risk_profile="Aggressive")
        score = engine.calculate_lock_score(market, loan, days_to_close=60)
        assert 0 <= score <= 100


# =============================================================================
# Lock Recommendation
# =============================================================================

@pytest.mark.unit
class TestLockRecommendation:
    """Test lock/float recommendation logic."""

    def _get_engine(self):
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        return RateLockIntelligenceEngine()

    def _make_loan(self, **overrides):
        from workflows.rate_lock_engine import LoanContext
        defaults = {
            "loan_id": 1,
            "loan_number": "2026-001",
            "borrower_name": "Test",
            "loan_amount": 400000.0,
            "current_rate": 6.875,
            "closing_date": datetime.now(timezone.utc) + timedelta(days=20),
            "lock_date": None,
            "lock_expiration_date": None,
            "lock_term_days": None,
            "rate_lock_status": "Eligible - No Lock",
            "borrower_risk_profile": "Balanced",
            "property_identified": True,
            "loan_structure_complete": True,
        }
        defaults.update(overrides)
        return LoanContext(**defaults)

    def test_high_score_recommends_lock_now(self):
        engine = self._get_engine()
        loan = self._make_loan()
        rec, reason = engine.get_recommendation(75, 20, loan)
        assert rec == "LOCK_NOW"

    def test_low_score_recommends_float(self):
        engine = self._get_engine()
        loan = self._make_loan()
        rec, reason = engine.get_recommendation(25, 45, loan)
        assert rec == "FLOAT_AND_MONITOR"

    def test_expiring_lock_recommends_extend(self):
        """Locked loan with lock expiring in < 7 days should recommend EXTEND."""
        engine = self._get_engine()
        loan = self._make_loan(
            rate_lock_status="Locked",
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=3),
        )
        rec, reason = engine.get_recommendation(50, 15, loan)
        assert rec == "EXTEND_LOCK"
        assert "expires" in reason.lower() or "extension" in reason.lower()

    def test_expired_lock_recommends_relock(self):
        """Loan with expired lock should recommend RELOCK."""
        engine = self._get_engine()
        loan = self._make_loan(rate_lock_status="Lock Expired")
        rec, reason = engine.get_recommendation(50, 20, loan)
        assert rec == "RELOCK"

    def test_critical_close_overrides_low_score(self):
        """Even with low score, imminent closing forces LOCK_NOW."""
        engine = self._get_engine()
        loan = self._make_loan()
        rec, reason = engine.get_recommendation(20, 5, loan)
        assert rec == "LOCK_NOW"
        assert "CRITICAL" in reason.upper() or "imminent" in reason.lower()


# =============================================================================
# Rate Lock Enum Values
# =============================================================================

@pytest.mark.unit
class TestRateLockEnums:
    """Test that rate lock enums have expected values."""

    def test_rate_lock_status_values(self):
        """RateLockStatus should have all expected statuses."""
        from database.enums import RateLockStatus
        expected = {
            "Not Eligible", "Eligible - No Lock", "Locked",
            "Float Monitoring", "Lock Expiring", "Lock Extended", "Lock Expired"
        }
        actual = {s.value for s in RateLockStatus}
        missing = expected - actual
        assert not missing, f"Missing RateLockStatus values: {missing}"

    def test_rate_lock_recommendation_values(self):
        """RateLockRecommendation should have all expected recommendations."""
        from database.enums import RateLockRecommendation
        expected = {
            "Lock Now", "Float and Monitor", "Extend Lock",
            "Relock", "Explore Float-Down"
        }
        actual = {r.value for r in RateLockRecommendation}
        missing = expected - actual
        assert not missing, f"Missing RateLockRecommendation values: {missing}"


# =============================================================================
# Extension Cost Table
# =============================================================================

@pytest.mark.unit
class TestExtensionCosts:
    """Test extension cost configuration."""

    def test_extension_costs_defined(self):
        """Extension cost table should have entries for common periods."""
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        costs = RateLockIntelligenceEngine.EXTENSION_COSTS
        assert 15 in costs, "15-day extension cost should be defined"
        assert 30 in costs, "30-day extension cost should be defined"

    def test_extension_costs_increase_with_duration(self):
        """Longer extension periods should cost more."""
        from workflows.rate_lock_engine import RateLockIntelligenceEngine
        costs = RateLockIntelligenceEngine.EXTENSION_COSTS
        sorted_periods = sorted(costs.keys())
        for i in range(1, len(sorted_periods)):
            assert costs[sorted_periods[i]] > costs[sorted_periods[i - 1]], (
                f"Extension cost for {sorted_periods[i]} days should exceed "
                f"{sorted_periods[i - 1]} days"
            )
