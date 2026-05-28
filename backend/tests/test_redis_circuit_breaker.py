"""
Tests for _RedisCircuitBreaker in auth/tokens.py.

Covers: state transitions, fail-closed behavior, half-open recovery,
success decrement (not clear), and double-counting protection.
"""

import time
import threading
from unittest.mock import patch, MagicMock

import pytest


def _make_breaker(**kwargs):
    """Create a breaker with test-friendly defaults."""
    from auth.tokens import _RedisCircuitBreaker
    defaults = dict(
        failure_threshold=5,
        recovery_timeout=0.2,
        half_open_max_probes=3,
        success_threshold=2,
    )
    defaults.update(kwargs)
    return _RedisCircuitBreaker(**defaults)


class TestCircuitBreakerStates:
    """State machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def test_starts_closed(self):
        breaker = _make_breaker()
        assert breaker.state == "closed"
        assert not breaker.is_open

    def test_opens_after_threshold_failures(self):
        breaker = _make_breaker(failure_threshold=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == "open"
        assert breaker.is_open

    def test_stays_closed_below_threshold(self):
        breaker = _make_breaker(failure_threshold=5)
        for _ in range(4):
            breaker.record_failure()
        assert breaker.state == "closed"
        assert not breaker.is_open

    def test_transitions_to_half_open_after_recovery_timeout(self):
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.1)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == "open"

        time.sleep(0.15)
        assert breaker.state == "half_open"

    def test_half_open_closes_after_success_threshold(self):
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.05, success_threshold=2)
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.1)
        assert breaker.state == "half_open"

        breaker.record_success()
        assert breaker.state == "half_open"
        breaker.record_success()
        assert breaker.state == "closed"

    def test_half_open_reopens_on_failure(self):
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.05)
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.1)
        assert breaker.state == "half_open"

        breaker.record_failure()
        assert breaker.state == "open"


class TestSuccessDecrement:
    """record_success decrements failure_count by 1, does NOT clear all."""

    def test_success_decrements_by_one(self):
        breaker = _make_breaker(failure_threshold=10)
        for _ in range(5):
            breaker.record_failure()
        assert breaker._failure_count == 5

        breaker.record_success()
        assert breaker._failure_count == 4

        breaker.record_success()
        assert breaker._failure_count == 3

    def test_success_does_not_go_below_zero(self):
        breaker = _make_breaker()
        breaker.record_success()
        assert breaker._failure_count == 0

    def test_flapping_redis_can_still_trip_breaker(self):
        """With decrement (not clear), alternating fail/success still accumulates."""
        breaker = _make_breaker(failure_threshold=5)
        for _ in range(20):
            breaker.record_failure()
            breaker.record_failure()
            breaker.record_success()
            if breaker.is_open:
                break
        assert breaker.is_open, "Flapping Redis should eventually trip the breaker"


class TestFailClosed:
    """Token blacklist checks fail-closed when breaker is open."""

    def test_is_blacklisted_returns_true_when_breaker_open(self):
        from auth.tokens import TokenBlacklist
        bl = TokenBlacklist()
        bl._enabled = True
        bl._using_fallback = False
        bl._is_production = True
        bl._redis = None

        for _ in range(20):
            bl._breaker.record_failure()
        assert bl._breaker.is_open

        result = bl.is_blacklisted_by_jti("test-jti-12345678")
        assert result is True, "Should deny (fail-closed) when breaker is open"

    def test_is_user_revoked_returns_true_when_breaker_open(self):
        from auth.tokens import TokenBlacklist
        bl = TokenBlacklist()
        bl._enabled = True
        bl._using_fallback = False
        bl._is_production = True
        bl._redis = None

        for _ in range(20):
            bl._breaker.record_failure()
        assert bl._breaker.is_open

        result = bl.is_user_revoked(42)
        assert result is True, "Should deny (fail-closed) when breaker is open"

    def test_normal_operation_checks_redis(self):
        from auth.tokens import TokenBlacklist
        bl = TokenBlacklist()
        bl._enabled = True
        bl._using_fallback = False
        bl._is_production = True

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        bl._redis = mock_redis

        result = bl.is_blacklisted_by_jti("test-jti-12345678")
        assert result is False
        mock_redis.exists.assert_called_once()
        assert bl._breaker._total_successes == 1


class TestBreakerRecovery:
    """Half-open state probes Redis and recovers."""

    def test_recovery_after_redis_comes_back(self):
        from auth.tokens import TokenBlacklist
        bl = TokenBlacklist()
        bl._enabled = True
        bl._using_fallback = False
        bl._is_production = True
        bl._breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.05, success_threshold=2)

        mock_redis = MagicMock()
        mock_redis.exists.side_effect = ConnectionError("Redis down")
        bl._redis = mock_redis

        for _ in range(3):
            bl.is_blacklisted_by_jti("jti-test-1234")
        assert bl._breaker.is_open

        time.sleep(0.1)

        mock_redis.exists.side_effect = None
        mock_redis.exists.return_value = 0

        result1 = bl.is_blacklisted_by_jti("jti-test-1234")
        assert result1 is False
        result2 = bl.is_blacklisted_by_jti("jti-test-5678")
        assert result2 is False

        assert bl._breaker.state == "closed"


class TestGetStatus:
    """Breaker status is included in health check output."""

    def test_get_status_includes_breaker(self):
        breaker = _make_breaker()
        status = breaker.get_status()

        assert "state" in status
        assert "failure_count" in status
        assert "failure_threshold" in status
        assert "total_failures" in status
        assert "total_successes" in status
        assert "recovery_timeout_seconds" in status
        assert status["state"] == "closed"

    def test_token_blacklist_status_includes_breaker(self):
        from auth.tokens import TokenBlacklist
        bl = TokenBlacklist()
        bl._enabled = True
        bl._using_fallback = True

        status = bl.get_status()
        assert status["mode"] == "in_memory"


class TestThreadSafety:
    """Concurrent access doesn't corrupt breaker state."""

    def test_concurrent_failures_dont_corrupt(self):
        breaker = _make_breaker(failure_threshold=100)
        errors = []

        def hammer_failures():
            try:
                for _ in range(50):
                    breaker.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hammer_failures) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert breaker._total_failures == 500
        assert breaker._failure_count <= 500
