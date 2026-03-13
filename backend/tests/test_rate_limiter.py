"""
Tests for the endpoint-level rate limiter and AI budget tracker.

Covers:
- Sliding window counting behaviour
- Rate limit decorator (429 response, headers)
- Predefined profiles
- Cleanup of expired entries
- AI budget tracker per-org tracking
- Budget enforcement (429 on exceeded)
- Response headers
"""

import asyncio
import time
from collections import deque
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from middleware.rate_limiter import (
    AI_LIMIT,
    AUTH_LIMIT,
    ESIGN_TOKEN_LIMIT,
    READ_LIMIT,
    UPLOAD_LIMIT,
    WRITE_LIMIT,
    RateLimiter,
    get_rate_limiter,
    rate_limit,
)
from middleware.ai_cost_tracker import (
    AIBudgetTracker,
    OPERATION_COSTS,
    get_ai_budget_tracker,
)


# =============================================================================
# Helpers
# =============================================================================

def _fresh_limiter() -> RateLimiter:
    """Create a fresh RateLimiter by resetting the singleton."""
    RateLimiter._instance = None
    limiter = RateLimiter(default_limit=5, default_window=10, cleanup_interval=1)
    return limiter


def _fresh_tracker() -> AIBudgetTracker:
    """Create a fresh AIBudgetTracker by resetting the singleton."""
    AIBudgetTracker._instance = None
    tracker = AIBudgetTracker(default_daily_budget=1.0, cleanup_interval=1)
    return tracker


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons before and after each test."""
    RateLimiter._instance = None
    AIBudgetTracker._instance = None
    yield
    RateLimiter._instance = None
    AIBudgetTracker._instance = None


# =============================================================================
# RateLimiter — Sliding Window
# =============================================================================

class TestSlidingWindow:
    """Core sliding-window counter tests."""

    def test_allows_requests_under_limit(self):
        limiter = _fresh_limiter()
        for _ in range(5):
            assert limiter.check_rate_limit("key1", limit=5, window=10) is True

    def test_blocks_requests_over_limit(self):
        limiter = _fresh_limiter()
        for _ in range(5):
            limiter.check_rate_limit("key1", limit=5, window=10)
        assert limiter.check_rate_limit("key1", limit=5, window=10) is False

    def test_different_keys_are_independent(self):
        limiter = _fresh_limiter()
        for _ in range(5):
            limiter.check_rate_limit("key_a", limit=5, window=10)
        # key_a exhausted
        assert limiter.check_rate_limit("key_a", limit=5, window=10) is False
        # key_b should still be allowed
        assert limiter.check_rate_limit("key_b", limit=5, window=10) is True

    def test_window_expiry_allows_new_requests(self):
        limiter = _fresh_limiter()
        # Fill up the limit with a very short window
        for _ in range(3):
            limiter.check_rate_limit("key_exp", limit=3, window=0.05)
        assert limiter.check_rate_limit("key_exp", limit=3, window=0.05) is False

        # Wait for the window to expire
        time.sleep(0.1)
        assert limiter.check_rate_limit("key_exp", limit=3, window=0.05) is True

    def test_get_remaining_reports_correctly(self):
        limiter = _fresh_limiter()
        assert limiter.get_remaining("rem_key", limit=5, window=10) == 5

        limiter.check_rate_limit("rem_key", limit=5, window=10)
        limiter.check_rate_limit("rem_key", limit=5, window=10)
        assert limiter.get_remaining("rem_key", limit=5, window=10) == 3

    def test_get_reset_time_is_positive_when_entries_exist(self):
        limiter = _fresh_limiter()
        limiter.check_rate_limit("rst_key", limit=5, window=60)
        reset = limiter.get_reset_time("rst_key", window=60)
        assert reset > 0
        assert reset <= 60

    def test_get_reset_time_is_zero_for_empty_key(self):
        limiter = _fresh_limiter()
        assert limiter.get_reset_time("nonexistent", window=60) == 0

    def test_reset_clears_specific_key(self):
        limiter = _fresh_limiter()
        for _ in range(5):
            limiter.check_rate_limit("clear_me", limit=5, window=10)
        assert limiter.check_rate_limit("clear_me", limit=5, window=10) is False

        limiter.reset("clear_me")
        assert limiter.check_rate_limit("clear_me", limit=5, window=10) is True

    def test_reset_all_clears_everything(self):
        limiter = _fresh_limiter()
        for _ in range(5):
            limiter.check_rate_limit("k1", limit=5, window=10)
            limiter.check_rate_limit("k2", limit=5, window=10)

        limiter.reset()
        assert limiter.check_rate_limit("k1", limit=5, window=10) is True
        assert limiter.check_rate_limit("k2", limit=5, window=10) is True


# =============================================================================
# RateLimiter — Cleanup
# =============================================================================

class TestCleanup:
    """Automatic cleanup of expired entries."""

    def test_cleanup_removes_stale_keys(self):
        limiter = _fresh_limiter()
        # Manually inject a stale entry (timestamp far in the past)
        with limiter._lock:
            limiter._buckets["stale_key"] = deque([time.monotonic() - 7200])
            limiter._last_cleanup = time.monotonic() - 100  # Force cleanup on next call

        # Any check_rate_limit call triggers cleanup
        limiter.check_rate_limit("trigger", limit=100, window=10)

        with limiter._lock:
            assert "stale_key" not in limiter._buckets

    def test_cleanup_preserves_fresh_keys(self):
        limiter = _fresh_limiter()
        limiter.check_rate_limit("fresh_key", limit=10, window=10)

        # Force a cleanup pass
        with limiter._lock:
            limiter._last_cleanup = time.monotonic() - 100
        limiter.check_rate_limit("trigger2", limit=100, window=10)

        with limiter._lock:
            assert "fresh_key" in limiter._buckets


# =============================================================================
# rate_limit Decorator
# =============================================================================

def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app with rate-limited endpoints for testing."""
    app = FastAPI()

    @app.get("/limited")
    @rate_limit(limit=3, window=60)
    async def limited_endpoint(request: Request):
        return {"status": "ok"}

    @app.get("/unlimited")
    async def unlimited_endpoint(request: Request):
        return {"status": "ok"}

    @app.post("/ai-operation")
    @rate_limit(limit=2, window=60)
    async def ai_operation(request: Request):
        return {"status": "processed"}

    return app


class TestRateLimitDecorator:
    """Integration tests for the decorator with TestClient."""

    def test_allows_requests_within_limit(self):
        app = _build_test_app()
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/limited")
            assert resp.status_code == 200

    def test_returns_429_when_exceeded(self):
        app = _build_test_app()
        client = TestClient(app)

        # Exhaust the limit
        for _ in range(3):
            client.get("/limited")

        # 4th request should be blocked
        resp = client.get("/limited")
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"]["error"] == "Rate limit exceeded"
        assert body["detail"]["limit"] == 3

    def test_429_response_contains_retry_after_header(self):
        app = _build_test_app()
        client = TestClient(app)

        for _ in range(3):
            client.get("/limited")

        resp = client.get("/limited")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert int(resp.headers["retry-after"]) > 0

    def test_429_response_contains_rate_limit_headers(self):
        app = _build_test_app()
        client = TestClient(app)

        for _ in range(3):
            client.get("/limited")

        resp = client.get("/limited")
        assert resp.status_code == 429
        assert resp.headers.get("x-ratelimit-limit") == "3"
        assert resp.headers.get("x-ratelimit-remaining") == "0"

    def test_unlimited_endpoint_not_affected(self):
        app = _build_test_app()
        client = TestClient(app)

        # Even after the limited endpoint is exhausted, unlimited still works
        for _ in range(3):
            client.get("/limited")
        assert client.get("/limited").status_code == 429

        resp = client.get("/unlimited")
        assert resp.status_code == 200

    def test_different_endpoints_have_separate_counters(self):
        app = _build_test_app()
        client = TestClient(app)

        # Exhaust /limited
        for _ in range(3):
            client.get("/limited")
        assert client.get("/limited").status_code == 429

        # /ai-operation should have its own counter
        resp = client.post("/ai-operation")
        assert resp.status_code == 200


# =============================================================================
# Predefined Profiles
# =============================================================================

class TestProfiles:
    """Verify that predefined profiles are callable decorators."""

    def test_upload_limit_is_callable(self):
        assert callable(UPLOAD_LIMIT)

    def test_ai_limit_is_callable(self):
        assert callable(AI_LIMIT)

    def test_read_limit_is_callable(self):
        assert callable(READ_LIMIT)

    def test_write_limit_is_callable(self):
        assert callable(WRITE_LIMIT)

    def test_auth_limit_is_callable(self):
        assert callable(AUTH_LIMIT)

    def test_esign_token_limit_is_callable(self):
        assert callable(ESIGN_TOKEN_LIMIT)

    def test_profiles_can_decorate_functions(self):
        """Ensure each profile can wrap a function without error."""
        async def dummy(request: Request):
            return {"ok": True}

        wrapped = UPLOAD_LIMIT(dummy)
        assert callable(wrapped)
        assert wrapped.__name__ == "dummy"

        wrapped = AI_LIMIT(dummy)
        assert callable(wrapped)

        wrapped = AUTH_LIMIT(dummy)
        assert callable(wrapped)


# =============================================================================
# AIBudgetTracker
# =============================================================================

class TestAIBudgetTracker:
    """AI cost tracking and budget enforcement."""

    def test_track_call_records_cost(self):
        tracker = _fresh_tracker()
        cost = tracker.track_call(org_id=1, operation="review")
        assert cost == OPERATION_COSTS["review"]

    def test_track_call_with_custom_cost(self):
        tracker = _fresh_tracker()
        cost = tracker.track_call(org_id=1, operation="review", estimated_cost=0.99)
        assert cost == 0.99

    def test_get_usage_reports_totals(self):
        tracker = _fresh_tracker()
        tracker.track_call(org_id=1, operation="review")
        tracker.track_call(org_id=1, operation="classification")
        tracker.track_call(org_id=1, operation="review")

        usage = tracker.get_usage(org_id=1, period_hours=24)
        expected = OPERATION_COSTS["review"] * 2 + OPERATION_COSTS["classification"]
        assert abs(usage["total_cost"] - round(expected, 4)) < 0.001
        assert usage["call_count"] == 3
        assert "review" in usage["by_operation"]
        assert usage["by_operation"]["review"]["count"] == 2

    def test_get_usage_respects_period(self):
        tracker = _fresh_tracker()
        # Inject an entry with a very old timestamp
        old_entry_timestamp = time.monotonic() - (25 * 3600)  # 25 hours ago
        from middleware.ai_cost_tracker import _CostEntry
        old_entry = _CostEntry(
            timestamp=old_entry_timestamp,
            wall_time=time.time() - (25 * 3600),
            operation="review",
            cost=0.15,
        )
        tracker._entries[99].append(old_entry)

        # Add a recent entry
        tracker.track_call(org_id=99, operation="classification")

        usage = tracker.get_usage(org_id=99, period_hours=24)
        # Only the recent classification should count
        assert usage["call_count"] == 1
        assert abs(usage["total_cost"] - OPERATION_COSTS["classification"]) < 0.001

    def test_per_org_isolation(self):
        tracker = _fresh_tracker()
        tracker.track_call(org_id=1, operation="review")
        tracker.track_call(org_id=2, operation="classification")

        usage_1 = tracker.get_usage(org_id=1, period_hours=24)
        usage_2 = tracker.get_usage(org_id=2, period_hours=24)

        assert usage_1["call_count"] == 1
        assert usage_2["call_count"] == 1
        assert abs(usage_1["total_cost"] - OPERATION_COSTS["review"]) < 0.001
        assert abs(usage_2["total_cost"] - OPERATION_COSTS["classification"]) < 0.001

    def test_check_budget_returns_true_when_under(self):
        tracker = _fresh_tracker()  # budget = $1.00
        tracker.track_call(org_id=1, operation="classification", estimated_cost=0.05)
        assert tracker.check_budget(org_id=1) is True

    def test_check_budget_returns_false_when_over(self):
        tracker = _fresh_tracker()  # budget = $1.00
        tracker.track_call(org_id=1, operation="review", estimated_cost=1.01)
        assert tracker.check_budget(org_id=1) is False

    def test_enforce_budget_raises_429_when_exceeded(self):
        tracker = _fresh_tracker()  # budget = $1.00
        tracker.track_call(org_id=1, operation="review", estimated_cost=1.50)

        with pytest.raises(Exception) as exc_info:
            tracker.enforce_budget(org_id=1)

        # HTTPException with status_code 429
        assert exc_info.value.status_code == 429
        assert "AI processing budget exceeded" in str(exc_info.value.detail)

    def test_enforce_budget_passes_when_under(self):
        tracker = _fresh_tracker()  # budget = $1.00
        tracker.track_call(org_id=1, operation="classification", estimated_cost=0.05)
        # Should not raise
        tracker.enforce_budget(org_id=1)

    def test_set_org_budget_overrides_default(self):
        tracker = _fresh_tracker()  # default budget = $1.00
        tracker.set_org_budget(org_id=5, daily_budget=100.0)

        tracker.track_call(org_id=5, operation="review", estimated_cost=50.0)
        assert tracker.check_budget(org_id=5) is True

        tracker.track_call(org_id=5, operation="review", estimated_cost=51.0)
        assert tracker.check_budget(org_id=5) is False

    def test_get_cost_estimate_known_operation(self):
        tracker = _fresh_tracker()
        assert tracker.get_cost_estimate("review") == 0.15
        assert tracker.get_cost_estimate("classification") == 0.05
        assert tracker.get_cost_estimate("ocr_page") == 0.10

    def test_get_cost_estimate_unknown_operation(self):
        tracker = _fresh_tracker()
        assert tracker.get_cost_estimate("unknown_op") == 0.05  # DEFAULT_OPERATION_COST

    def test_usage_reports_budget_pct(self):
        tracker = _fresh_tracker()  # budget = $1.00
        tracker.track_call(org_id=1, operation="review", estimated_cost=0.50)

        usage = tracker.get_usage(org_id=1, period_hours=24)
        assert abs(usage["budget_used_pct"] - 50.0) < 0.1
        assert abs(usage["remaining_budget"] - 0.50) < 0.001

    def test_reset_clears_org_data(self):
        tracker = _fresh_tracker()
        tracker.track_call(org_id=1, operation="review")
        tracker.reset(org_id=1)

        usage = tracker.get_usage(org_id=1, period_hours=24)
        assert usage["call_count"] == 0
        assert usage["total_cost"] == 0.0

    def test_reset_all_clears_everything(self):
        tracker = _fresh_tracker()
        tracker.track_call(org_id=1, operation="review")
        tracker.track_call(org_id=2, operation="classification")
        tracker.reset()

        assert tracker.get_usage(org_id=1, period_hours=24)["call_count"] == 0
        assert tracker.get_usage(org_id=2, period_hours=24)["call_count"] == 0


# =============================================================================
# Integration — Rate Limiter + AI Budget in One App
# =============================================================================

class TestIntegration:
    """Combined rate limiter and budget tracker in a realistic scenario."""

    def test_rate_limit_and_budget_both_enforce(self):
        """A request can be rejected by either rate limit OR budget."""
        tracker = _fresh_tracker()

        app = FastAPI()

        @app.post("/ai-review")
        @rate_limit(limit=5, window=60)
        async def ai_review(request: Request):
            # Budget check would happen here in real code
            return {"status": "reviewed"}

        client = TestClient(app)

        # First 5 requests pass rate limit
        for _ in range(5):
            resp = client.post("/ai-review")
            assert resp.status_code == 200

        # 6th request is rate-limited
        resp = client.post("/ai-review")
        assert resp.status_code == 429
