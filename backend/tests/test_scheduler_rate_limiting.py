"""
Integration tests for scheduler rate limiting.
Tests per-IP, per-email, and global rate limits on public booking endpoints.

The rate limiting system has three layers:
  1. General per-IP+path rate limit (_check_rate_limit in _helpers.py)
  2. Booking-specific per-IP rate limit (_check_booking_ip_rate_limit in public_booking.py)
  3. Per-email booking rate limit (_check_booking_email_rate_limit in public_booking.py)

Each layer supports Redis-backed and in-memory fallback modes.
"""
import pytest
import time as _time
from collections import OrderedDict, deque
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers for building fake Request objects
# ---------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, host: str = "203.0.113.50"):
        self.host = host


class _FakeURL:
    def __init__(self, path: str = "/api/scheduler/public/book/test-slug/confirm"):
        self.path = path


class _FakeRequest:
    """Minimal Request-like object accepted by _check_rate_limit / _get_client_ip."""
    def __init__(self, client_ip: str = "203.0.113.50", path: str = "/api/scheduler/public/book/test-slug/confirm"):
        self.client = _FakeClient(client_ip)
        self.url = _FakeURL(path)
        self.headers = {}


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_memory_rate_limits():
    """Clear in-memory rate limit state before each test to prevent leakage."""
    from routes.scheduler import _helpers
    _helpers._memory_rate_limits.clear()
    _helpers._memory_rate_check_count = 0
    yield
    _helpers._memory_rate_limits.clear()
    _helpers._memory_rate_check_count = 0


@pytest.fixture
def _no_redis():
    """Force all rate limit checks to use in-memory fallback by stubbing Redis out."""
    with patch("routes.scheduler._helpers._get_rate_limit_redis", return_value=None):
        yield


@pytest.fixture
def _mock_redis():
    """Provide a mock Redis client whose incr/expire/ttl behave like a real Redis."""
    counters = {}

    class FakeRedis:
        def incr(self, key):
            counters[key] = counters.get(key, 0) + 1
            return counters[key]

        def expire(self, key, seconds):
            pass  # no-op for testing

        def ttl(self, key):
            return 60

    fake = FakeRedis()
    with patch("routes.scheduler._helpers._get_rate_limit_redis", return_value=fake):
        yield fake, counters


# ===========================================================================
# Per-IP Rate Limiting (_check_rate_limit)
# ===========================================================================

class TestIPRateLimiting:
    """Test per-IP rate limiting via _check_rate_limit."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, _no_redis):
        """Requests under the configured max should succeed (no exception)."""
        from routes.scheduler._helpers import _check_rate_limit

        request = _FakeRequest(client_ip="198.51.100.1")
        # Default _RATE_LIMIT_MAX_PUBLIC is 10; send 5 requests
        for _ in range(5):
            await _check_rate_limit(request, max_requests=10)
        # No HTTPException means all requests were allowed

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self, _no_redis):
        """Exceeding the rate limit should raise HTTP 429."""
        from routes.scheduler._helpers import _check_rate_limit

        request = _FakeRequest(client_ip="198.51.100.2")
        max_req = 3
        # Use up the quota
        for _ in range(max_req):
            await _check_rate_limit(request, max_requests=max_req)

        # The next request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(request, max_requests=max_req)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_returns_retry_after_header(self, _no_redis):
        """429 response must include a Retry-After header."""
        from routes.scheduler._helpers import _check_rate_limit

        request = _FakeRequest(client_ip="198.51.100.3")
        max_req = 2
        for _ in range(max_req):
            await _check_rate_limit(request, max_requests=max_req)

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(request, max_requests=max_req)
        headers = exc_info.value.headers or {}
        assert "Retry-After" in headers
        retry_after = int(headers["Retry-After"])
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_different_ips_have_independent_limits(self, _no_redis):
        """Each IP should be tracked independently."""
        from routes.scheduler._helpers import _check_rate_limit

        req_a = _FakeRequest(client_ip="198.51.100.10")
        req_b = _FakeRequest(client_ip="198.51.100.11")
        max_req = 2

        # Exhaust limit for IP A
        for _ in range(max_req):
            await _check_rate_limit(req_a, max_requests=max_req)

        # IP B should still be allowed
        await _check_rate_limit(req_b, max_requests=max_req)

        # IP A should be blocked
        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(req_a, max_requests=max_req)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_different_paths_have_independent_limits(self, _no_redis):
        """Rate limit keys include the URL path, so different paths are tracked separately."""
        from routes.scheduler._helpers import _check_rate_limit

        ip = "198.51.100.20"
        req_slots = _FakeRequest(client_ip=ip, path="/api/scheduler/public/book/slug/slots")
        req_confirm = _FakeRequest(client_ip=ip, path="/api/scheduler/public/book/slug/confirm")
        max_req = 2

        # Exhaust limit on /slots path
        for _ in range(max_req):
            await _check_rate_limit(req_slots, max_requests=max_req)

        # /confirm path should still be allowed for same IP
        await _check_rate_limit(req_confirm, max_requests=max_req)


# ===========================================================================
# Per-Email Booking Rate Limiting (_check_booking_email_rate_limit)
# ===========================================================================

class TestEmailRateLimiting:
    """Test per-email booking rate limiting."""

    def test_allows_normal_booking_frequency(self):
        """Should not raise when email has fewer bookings than the limit."""
        from routes.scheduler.public_booking import _check_booking_email_rate_limit

        mock_db = MagicMock()
        # Simulate 0 recent bookings
        mock_result = MagicMock()
        mock_result.cnt = 0
        mock_db.execute.return_value.fetchone.return_value = mock_result

        # Should not raise
        _check_booking_email_rate_limit(mock_db, "user@example.com")

    def test_blocks_excessive_bookings_from_same_email(self):
        """Should raise HTTP 429 when email has >= max bookings in the window."""
        from routes.scheduler.public_booking import (
            _check_booking_email_rate_limit,
            _BOOKING_MAX_PER_EMAIL,
        )

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.cnt = _BOOKING_MAX_PER_EMAIL  # At or above limit
        mock_db.execute.return_value.fetchone.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            _check_booking_email_rate_limit(mock_db, "spammer@example.com")
        assert exc_info.value.status_code == 429
        assert "Retry-After" in (exc_info.value.headers or {})

    def test_skips_check_for_empty_email(self):
        """Should silently return when email is empty/None."""
        from routes.scheduler.public_booking import _check_booking_email_rate_limit

        mock_db = MagicMock()
        # Should return without calling DB
        _check_booking_email_rate_limit(mock_db, "")
        _check_booking_email_rate_limit(mock_db, None)
        mock_db.execute.assert_not_called()


# ===========================================================================
# Booking IP Rate Limiting (_check_booking_ip_rate_limit)
# ===========================================================================

class TestBookingIPRateLimiting:
    """Test the tighter per-IP rate limit for booking confirmation."""

    @pytest.mark.asyncio
    async def test_allows_under_booking_ip_limit(self, _no_redis):
        """Should allow requests under the booking-specific IP limit."""
        from routes.scheduler.public_booking import _check_booking_ip_rate_limit

        request = _FakeRequest(client_ip="198.51.100.30")
        # Default _BOOKING_MAX_PER_IP is 5; send 3
        for _ in range(3):
            await _check_booking_ip_rate_limit(request)

    @pytest.mark.asyncio
    async def test_blocks_over_booking_ip_limit(self, _no_redis):
        """Should raise 429 when IP exceeds booking-specific limit."""
        from routes.scheduler.public_booking import (
            _check_booking_ip_rate_limit,
            _BOOKING_MAX_PER_IP,
        )

        request = _FakeRequest(client_ip="198.51.100.31")
        for _ in range(_BOOKING_MAX_PER_IP):
            await _check_booking_ip_rate_limit(request)

        with pytest.raises(HTTPException) as exc_info:
            await _check_booking_ip_rate_limit(request)
        assert exc_info.value.status_code == 429


# ===========================================================================
# Redis vs. In-Memory Fallback
# ===========================================================================

class TestRateLimitBackends:
    """Test Redis-backed and in-memory fallback rate limiters."""

    @pytest.mark.asyncio
    async def test_redis_rate_limiter_incr_and_expire(self, _mock_redis):
        """Redis-backed limiter should call incr/expire and enforce limits."""
        from routes.scheduler._helpers import _check_rate_limit

        fake_redis, counters = _mock_redis
        request = _FakeRequest(client_ip="198.51.100.40")
        max_req = 3

        for _ in range(max_req):
            await _check_rate_limit(request, max_requests=max_req)

        key = f"sched_rl:{request.url.path}:{request.client.host}"
        assert counters[key] == max_req

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(request, max_requests=max_req)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_memory_fallback_rate_limiter(self, _no_redis):
        """In-memory fallback should enforce limits when Redis is unavailable."""
        from routes.scheduler._helpers import _check_rate_limit

        request = _FakeRequest(client_ip="198.51.100.41")
        max_req = 4
        for _ in range(max_req):
            await _check_rate_limit(request, max_requests=max_req)

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(request, max_requests=max_req)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_memory_fallback_capacity_exhaustion_returns_503(self):
        """When memory store is full and a new key arrives, 503 should be returned."""
        from routes.scheduler._helpers import _check_rate_limit, _memory_rate_limits

        # Pre-fill the in-memory store to capacity
        with patch("routes.scheduler._helpers._get_rate_limit_redis", return_value=None), \
             patch("routes.scheduler._helpers._MAX_RATE_LIMIT_KEYS", 2):
            # Fill with 2 existing keys
            req1 = _FakeRequest(client_ip="198.51.100.50", path="/path1")
            req2 = _FakeRequest(client_ip="198.51.100.51", path="/path2")
            await _check_rate_limit(req1, max_requests=100)
            await _check_rate_limit(req2, max_requests=100)

            # A third distinct key should trigger 503 (capacity exhausted)
            req3 = _FakeRequest(client_ip="198.51.100.52", path="/path3")
            with pytest.raises(HTTPException) as exc_info:
                await _check_rate_limit(req3, max_requests=100)
            assert exc_info.value.status_code == 503
            assert "Retry-After" in (exc_info.value.headers or {})

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_memory(self):
        """If Redis raises during incr(), the limiter should fall back to memory."""
        from routes.scheduler._helpers import _check_rate_limit

        # Redis that raises on incr
        broken_redis = MagicMock()
        broken_redis.incr.side_effect = ConnectionError("Redis gone")

        with patch("routes.scheduler._helpers._get_rate_limit_redis", return_value=broken_redis):
            request = _FakeRequest(client_ip="198.51.100.60")
            # Should not raise -- falls back to memory
            await _check_rate_limit(request, max_requests=10)

    @pytest.mark.asyncio
    async def test_sliding_window_expires_old_entries(self, _no_redis):
        """After the window elapses, old timestamps should be evicted and quota restored."""
        from routes.scheduler._helpers import _check_memory_rate_limit

        key = "test_sliding_window"
        max_req = 2
        window = 1  # 1 second window for fast test

        # Use up the quota
        for _ in range(max_req):
            result = await _check_memory_rate_limit(key, max_req, window_seconds=window)
            assert result is True

        # Should be blocked now
        result = await _check_memory_rate_limit(key, max_req, window_seconds=window)
        assert result is False

        # Wait for window to expire
        _time.sleep(1.1)

        # Should be allowed again
        result = await _check_memory_rate_limit(key, max_req, window_seconds=window)
        assert result is True
