"""
Tests for AI Cost Circuit Breaker

Covers:
- Circuit breaker threshold logic (warning, critical, exceeded)
- Budget enforcement with custom org budgets
- Redis cache for fast-path checking
- Circuit breaker reset
- Graceful degradation (critical agents bypass breaker)
"""

import os
import sys
import time
import threading
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ai_cost_tracker import (
    DEFAULT_DAILY_BUDGET,
    ALERT_THRESHOLDS,
    CRITICAL_AGENT_TYPES,
    AICostTracker,
    calculate_cost,
    check_circuit_breaker,
    reset_circuit_breaker,
    _get_circuit_breaker_state,
    _set_circuit_breaker_state,
    _cb_memory_lock,
    _cb_memory_state,
    _CB_KEY_PREFIX,
)


# =============================================================================
# Helpers
# =============================================================================

class FakeRedis:
    """In-memory dict-based Redis mock for testing."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._ttls: Dict[str, float] = {}

    def get(self, key: str) -> Optional[bytes]:
        self._expire_check(key)
        val = self._store.get(key)
        if val is None:
            return None
        return val.encode("utf-8") if isinstance(val, str) else val

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value
        self._ttls[key] = time.time() + ttl

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttls.pop(key, None)

    def _expire_check(self, key: str) -> None:
        if key in self._ttls and time.time() > self._ttls[key]:
            self._store.pop(key, None)
            self._ttls.pop(key, None)


class MockDB:
    """Minimal mock for SQLAlchemy Session."""

    def __init__(self, spent_today: float = 0.0, budget: Optional[float] = 50.0):
        self._spent_today = spent_today
        self._budget = budget

    def execute(self, query, params=None):
        query_str = str(query)
        if "ai_daily_budget_usd" in query_str:
            return MockResult(self._budget)
        if "SUM(cost_usd)" in query_str:
            return MockResult(Decimal(str(self._spent_today)))
        return MockResult(None)

    def commit(self):
        pass

    def rollback(self):
        pass


class MockResult:
    """Mock for SQLAlchemy query result."""

    def __init__(self, scalar_value):
        self._value = scalar_value

    def scalar(self):
        return self._value

    def fetchone(self):
        return (self._value,) if self._value is not None else None

    def fetchall(self):
        return []


def _clear_memory_state():
    """Clear in-memory circuit breaker state between tests."""
    with _cb_memory_lock:
        _cb_memory_state.clear()


# =============================================================================
# Test: Circuit Breaker Threshold Logic
# =============================================================================

class TestCircuitBreakerThresholds:
    """Test the three-tier threshold system."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_under_warning_threshold_allows(self, mock_redis):
        """Spending under 75% of budget should return ok."""
        db = MockDB(spent_today=30.0, budget=50.0)  # 60%
        allowed, reason = check_circuit_breaker(org_id=1, db=db)

        assert allowed is True
        assert reason == "ok"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_warning_threshold(self, mock_redis):
        """Spending at 75-89% of budget should return warning."""
        db = MockDB(spent_today=40.0, budget=50.0)  # 80%
        allowed, reason = check_circuit_breaker(org_id=2, db=db)

        assert allowed is True
        assert reason == "warning"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_critical_threshold(self, mock_redis):
        """Spending at 90-99% of budget should return critical."""
        db = MockDB(spent_today=46.0, budget=50.0)  # 92%
        allowed, reason = check_circuit_breaker(org_id=3, db=db)

        assert allowed is True
        assert reason == "critical"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_exceeded_threshold_blocks(self, mock_redis):
        """Spending at 100%+ of budget should block requests."""
        db = MockDB(spent_today=55.0, budget=50.0)  # 110%
        allowed, reason = check_circuit_breaker(org_id=4, db=db)

        assert allowed is False
        assert reason == "exceeded"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_exact_100_pct_blocks(self, mock_redis):
        """Spending exactly at 100% should trigger exceeded."""
        db = MockDB(spent_today=50.0, budget=50.0)  # exactly 100%
        allowed, reason = check_circuit_breaker(org_id=5, db=db)

        assert allowed is False
        assert reason == "exceeded"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_exact_75_pct_warns(self, mock_redis):
        """Spending exactly at 75% should trigger warning."""
        db = MockDB(spent_today=37.50, budget=50.0)  # exactly 75%
        allowed, reason = check_circuit_breaker(org_id=6, db=db)

        assert allowed is True
        assert reason == "warning"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_exact_90_pct_critical(self, mock_redis):
        """Spending exactly at 90% should trigger critical."""
        db = MockDB(spent_today=45.0, budget=50.0)  # exactly 90%
        allowed, reason = check_circuit_breaker(org_id=7, db=db)

        assert allowed is True
        assert reason == "critical"


# =============================================================================
# Test: Custom Org Budgets
# =============================================================================

class TestCustomBudgets:
    """Test circuit breaker with different per-org budgets."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_null_budget_means_unlimited(self, mock_redis):
        """NULL budget = unlimited, always allowed."""
        db = MockDB(spent_today=10000.0, budget=None)
        allowed, reason = check_circuit_breaker(org_id=10, db=db)

        assert allowed is True
        assert reason == "ok"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_high_custom_budget(self, mock_redis):
        """Org with $200 budget should tolerate $180 spend."""
        db = MockDB(spent_today=180.0, budget=200.0)  # 90%
        allowed, reason = check_circuit_breaker(org_id=11, db=db)

        assert allowed is True
        assert reason == "critical"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_low_custom_budget(self, mock_redis):
        """Org with $10 budget should block at $10 spend."""
        db = MockDB(spent_today=10.0, budget=10.0)  # 100%
        allowed, reason = check_circuit_breaker(org_id=12, db=db)

        assert allowed is False
        assert reason == "exceeded"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_zero_budget_allows(self, mock_redis):
        """Zero budget should be treated as no enforcement (edge case)."""
        db = MockDB(spent_today=5.0, budget=0.0)
        allowed, reason = check_circuit_breaker(org_id=13, db=db)

        assert allowed is True
        assert reason == "ok"


# =============================================================================
# Test: Redis Cache Fast Path
# =============================================================================

class TestRedisCache:
    """Test Redis-backed circuit breaker state caching."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    def test_redis_set_and_get_state(self):
        """Setting state via Redis should be retrievable."""
        fake_redis = FakeRedis()

        with patch("services.ai_cost_tracker._get_redis_client", return_value=fake_redis):
            _set_circuit_breaker_state(org_id=20, state="critical")
            state = _get_circuit_breaker_state(org_id=20)

        assert state == "critical"

    def test_redis_open_state_blocks_without_db_query(self):
        """When Redis has 'open' state, DB should not be queried."""
        fake_redis = FakeRedis()
        fake_redis.setex(f"{_CB_KEY_PREFIX}21", 86400, "open")

        db = MockDB(spent_today=0.0, budget=50.0)
        db.execute = MagicMock(side_effect=AssertionError("DB should not be called"))

        with patch("services.ai_cost_tracker._get_redis_client", return_value=fake_redis):
            allowed, reason = check_circuit_breaker(org_id=21, db=db)

        assert allowed is False
        assert reason == "exceeded"

    def test_redis_critical_cached_returns_without_db(self):
        """Cached 'critical' state should return immediately."""
        fake_redis = FakeRedis()
        fake_redis.setex(f"{_CB_KEY_PREFIX}22", 86400, "critical")

        db = MockDB()
        db.execute = MagicMock(side_effect=AssertionError("DB should not be called"))

        with patch("services.ai_cost_tracker._get_redis_client", return_value=fake_redis):
            allowed, reason = check_circuit_breaker(org_id=22, db=db)

        assert allowed is True
        assert reason == "critical"

    def test_redis_warning_cached_returns_without_db(self):
        """Cached 'warning' state should return immediately."""
        fake_redis = FakeRedis()
        fake_redis.setex(f"{_CB_KEY_PREFIX}23", 86400, "warning")

        db = MockDB()
        db.execute = MagicMock(side_effect=AssertionError("DB should not be called"))

        with patch("services.ai_cost_tracker._get_redis_client", return_value=fake_redis):
            allowed, reason = check_circuit_breaker(org_id=23, db=db)

        assert allowed is True
        assert reason == "warning"

    def test_in_memory_fallback_when_redis_unavailable(self):
        """When Redis returns None, in-memory state should be used."""
        _set_circuit_breaker_state.__wrapped__ = None  # just ensure we can call it

        with patch("services.ai_cost_tracker._get_redis_client", return_value=None):
            # Set state (will go to in-memory only)
            _set_circuit_breaker_state(org_id=24, state="open")
            state = _get_circuit_breaker_state(org_id=24)

        assert state == "open"

    def test_closed_state_triggers_db_refresh(self):
        """When cached state is 'closed', DB should be queried to refresh."""
        db = MockDB(spent_today=46.0, budget=50.0)  # 92% = critical

        with patch("services.ai_cost_tracker._get_redis_client", return_value=None):
            # No cached state = closed default
            allowed, reason = check_circuit_breaker(org_id=25, db=db)

        assert allowed is True
        assert reason == "critical"


# =============================================================================
# Test: Circuit Breaker Reset
# =============================================================================

class TestCircuitBreakerReset:
    """Test manual circuit breaker reset."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_reset_clears_state(self, mock_redis):
        """Resetting should clear the circuit breaker state."""
        # Set to open
        _set_circuit_breaker_state(org_id=30, state="open")
        assert _get_circuit_breaker_state(org_id=30) == "open"

        # Reset
        reset_circuit_breaker(org_id=30)

        # Should be back to closed (default)
        assert _get_circuit_breaker_state(org_id=30) == "closed"

    def test_reset_clears_redis_and_memory(self):
        """Reset should clear both Redis and in-memory state."""
        fake_redis = FakeRedis()

        with patch("services.ai_cost_tracker._get_redis_client", return_value=fake_redis):
            _set_circuit_breaker_state(org_id=31, state="open")

            # Verify both stores have the state
            assert fake_redis.get(f"{_CB_KEY_PREFIX}31") == b"open"
            with _cb_memory_lock:
                assert 31 in _cb_memory_state

            # Reset
            reset_circuit_breaker(org_id=31)

            # Both should be cleared
            assert fake_redis.get(f"{_CB_KEY_PREFIX}31") is None
            with _cb_memory_lock:
                assert 31 not in _cb_memory_state

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_reset_then_recheck(self, mock_redis):
        """After reset, circuit breaker should re-evaluate from DB."""
        # Start with open state
        _set_circuit_breaker_state(org_id=32, state="open")

        # Verify blocked
        db = MockDB(spent_today=0.0, budget=50.0)
        allowed, reason = check_circuit_breaker(org_id=32, db=db)
        assert allowed is False

        # Reset
        reset_circuit_breaker(org_id=32)

        # Now it should re-check DB (which shows $0 spent)
        allowed, reason = check_circuit_breaker(org_id=32, db=db)
        assert allowed is True
        assert reason == "ok"


# =============================================================================
# Test: Graceful Degradation (Critical Agents Bypass)
# =============================================================================

class TestGracefulDegradation:
    """Test that critical agent types bypass the circuit breaker."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_compliance_checker_bypasses_open_breaker(self, mock_redis):
        """compliance_checker should be allowed even when breaker is open."""
        db = MockDB(spent_today=60.0, budget=50.0)  # 120% = exceeded
        allowed, reason = check_circuit_breaker(
            org_id=40, db=db, agent_type="compliance_checker"
        )

        assert allowed is True
        assert reason == "exceeded_bypass"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_quality_control_bypasses_open_breaker(self, mock_redis):
        """quality_control should be allowed even when breaker is open."""
        db = MockDB(spent_today=60.0, budget=50.0)
        allowed, reason = check_circuit_breaker(
            org_id=41, db=db, agent_type="quality_control"
        )

        assert allowed is True
        assert reason == "exceeded_bypass"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_non_critical_agent_blocked_when_exceeded(self, mock_redis):
        """pipeline_analyst should be blocked when breaker is open."""
        db = MockDB(spent_today=60.0, budget=50.0)
        allowed, reason = check_circuit_breaker(
            org_id=42, db=db, agent_type="pipeline_analyst"
        )

        assert allowed is False
        assert reason == "exceeded"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_cached_open_state_still_allows_critical(self, mock_redis):
        """Even with cached 'open' state, critical agents bypass."""
        _set_circuit_breaker_state(org_id=43, state="open")

        db = MockDB()  # DB shouldn't be queried
        allowed, reason = check_circuit_breaker(
            org_id=43, db=db, agent_type="compliance_checker"
        )

        assert allowed is True
        assert reason == "exceeded_bypass"

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_no_agent_type_blocked_when_exceeded(self, mock_redis):
        """Without agent_type, exceeded state should block."""
        db = MockDB(spent_today=60.0, budget=50.0)
        allowed, reason = check_circuit_breaker(org_id=44, db=db, agent_type=None)

        assert allowed is False
        assert reason == "exceeded"

    def test_critical_agent_types_include_expected(self):
        """CRITICAL_AGENT_TYPES should include the expected agents."""
        assert "compliance_checker" in CRITICAL_AGENT_TYPES
        assert "quality_control" in CRITICAL_AGENT_TYPES
        assert "pipeline_analyst" not in CRITICAL_AGENT_TYPES


# =============================================================================
# Test: Error Handling / Fail-Open
# =============================================================================

class TestFailOpen:
    """Test that circuit breaker fails open on errors."""

    def setup_method(self):
        _clear_memory_state()

    def teardown_method(self):
        _clear_memory_state()

    @patch("services.ai_cost_tracker._get_redis_client", return_value=None)
    def test_db_error_fails_open(self, mock_redis):
        """If DB query fails, should allow the request (fail open)."""
        db = MagicMock()
        db.execute.side_effect = Exception("DB connection lost")

        allowed, reason = check_circuit_breaker(org_id=50, db=db)

        assert allowed is True
        assert reason == "ok"

    def test_redis_error_falls_back_to_memory(self):
        """If Redis errors, in-memory fallback should work."""
        broken_redis = MagicMock()
        broken_redis.get.side_effect = Exception("Redis timeout")
        broken_redis.setex.side_effect = Exception("Redis timeout")

        with patch("services.ai_cost_tracker._get_redis_client", return_value=broken_redis):
            # Set state (will fail Redis, succeed in-memory)
            _set_circuit_breaker_state(org_id=51, state="open")

            # Get state (Redis fails, in-memory succeeds)
            state = _get_circuit_breaker_state(org_id=51)

        assert state == "open"


# =============================================================================
# Test: Calculate Cost (existing, sanity check)
# =============================================================================

class TestCalculateCost:
    """Sanity check on cost calculation."""

    def test_known_model_cost(self):
        """Claude Sonnet: 1M input + 1M output = $3 + $15 = $18."""
        cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == Decimal("18.000000")

    def test_small_token_count(self):
        """1500 input + 800 output for Sonnet."""
        cost = calculate_cost("claude-sonnet-4-6", 1500, 800)
        expected = (Decimal("1500") / Decimal("1000000") * Decimal("3.00") +
                    Decimal("800") / Decimal("1000000") * Decimal("15.00"))
        assert cost == expected.quantize(Decimal("0.000001"))

    def test_unknown_model_uses_default(self):
        """Unknown model should use default pricing."""
        cost = calculate_cost("unknown-model-v99", 1_000_000, 1_000_000)
        # Default is $3/M input + $15/M output = $18
        assert cost == Decimal("18.000000")


# =============================================================================
# Test: AICostTracker.get_all_budget_status (new method)
# =============================================================================

class TestBudgetStatusMethod:
    """Test the get_all_budget_status method on AICostTracker."""

    def test_returns_list(self):
        """Should return a list even with no data."""
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []

        tracker = AICostTracker(db)
        result = tracker.get_all_budget_status()

        assert isinstance(result, list)

    def test_returns_empty_on_error(self):
        """Should return empty list on DB error."""
        db = MagicMock()
        db.execute.side_effect = Exception("DB error")

        tracker = AICostTracker(db)
        result = tracker.get_all_budget_status()

        assert result == []


# =============================================================================
# Test: AICostTracker.get_recent_alerts (new method)
# =============================================================================

class TestRecentAlertsMethod:
    """Test the get_recent_alerts method on AICostTracker."""

    def test_returns_list(self):
        """Should return a list even with no data."""
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []

        tracker = AICostTracker(db)
        result = tracker.get_recent_alerts()

        assert isinstance(result, list)

    def test_returns_empty_on_error(self):
        """Should return empty list on DB error."""
        db = MagicMock()
        db.execute.side_effect = Exception("DB error")

        tracker = AICostTracker(db)
        result = tracker.get_recent_alerts()

        assert result == []


# =============================================================================
# Test: Constants Sanity
# =============================================================================

class TestConstants:
    """Validate that threshold constants are correctly defined."""

    def test_thresholds_ordered(self):
        """Warning < Critical < Exceeded."""
        assert ALERT_THRESHOLDS["warning"] < ALERT_THRESHOLDS["critical"]
        assert ALERT_THRESHOLDS["critical"] < ALERT_THRESHOLDS["exceeded"]

    def test_default_budget_positive(self):
        """Default budget should be positive."""
        assert DEFAULT_DAILY_BUDGET > 0

    def test_warning_is_75_pct(self):
        assert ALERT_THRESHOLDS["warning"] == Decimal("0.75")

    def test_critical_is_90_pct(self):
        assert ALERT_THRESHOLDS["critical"] == Decimal("0.90")

    def test_exceeded_is_100_pct(self):
        assert ALERT_THRESHOLDS["exceeded"] == Decimal("1.00")
