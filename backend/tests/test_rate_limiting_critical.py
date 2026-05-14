"""
Rate Limiting Tests

Tests the rate limiting infrastructure:
1. In-memory token bucket rate limiter (middleware/rate_limiting.py)
2. Endpoint-level decorator rate limiter (middleware/rate_limiter.py)
3. API rate limit middleware configuration (middleware/api_rate_limit.py)

These test real code paths to verify the rate limiting logic works
correctly without requiring Redis.
"""

import pytest
import time
import logging
from unittest.mock import MagicMock, patch

logger = logging.getLogger(__name__)


# =============================================================================
# In-Memory Token Bucket (middleware/rate_limiting.py)
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestInMemoryTokenBucket:
    """Test the InMemoryRateLimiter (token bucket algorithm)."""

    def test_allows_requests_within_limit(self):
        """Requests within the limit should be allowed."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()
        # 10 requests allowed in 60 seconds (conservative = 5)
        for i in range(5):
            allowed, remaining = limiter.check("test_key", 10, 60)
            assert allowed, f"Request {i+1} should be allowed"
            assert remaining >= 0

    def test_blocks_requests_over_limit(self):
        """Requests over the limit should be blocked."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()
        # Max 4 requests (conservative 50% of 8 = 4)
        for i in range(4):
            allowed, _ = limiter.check("block_key", 8, 60)
            assert allowed

        # 5th request should be blocked
        allowed, remaining = limiter.check("block_key", 8, 60)
        assert not allowed
        assert remaining == 0

    def test_different_keys_are_independent(self):
        """Rate limits for different keys should be independent."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()
        # Exhaust key A
        for _ in range(5):
            limiter.check("key_a", 10, 60)

        # Key B should still have budget
        allowed, _ = limiter.check("key_b", 10, 60)
        assert allowed

    def test_conservative_factor_halves_limit(self):
        """In-memory limiter applies 50% conservative factor."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()
        assert limiter.CONSERVATIVE_FACTOR == 0.5

        # With max_requests=10, conservative max = 5
        allowed_count = 0
        for _ in range(20):
            allowed, _ = limiter.check("conservative_key", 10, 60)
            if allowed:
                allowed_count += 1
        assert allowed_count == 5


# =============================================================================
# Endpoint-Level Rate Limiter (middleware/rate_limiter.py)
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestEndpointRateLimiter:
    """Test the RateLimiter singleton used by the @rate_limit decorator."""

    def _get_fresh_limiter(self):
        """Get a fresh RateLimiter instance by resetting the singleton."""
        from middleware.rate_limiter import RateLimiter
        # Reset singleton for test isolation
        RateLimiter._instance = None
        limiter = RateLimiter(default_limit=5, default_window=60)
        return limiter

    def test_rate_limiter_is_singleton(self):
        """RateLimiter should be a singleton."""
        from middleware.rate_limiter import RateLimiter
        RateLimiter._instance = None
        a = RateLimiter()
        b = RateLimiter()
        assert a is b
        RateLimiter._instance = None  # cleanup

    def test_rate_limiter_allows_within_limit(self):
        """Requests within the configured limit should pass."""
        limiter = self._get_fresh_limiter()
        for i in range(5):
            allowed = limiter.check_rate_limit("test_user", limit=5, window=60)
            assert allowed, f"Request {i+1} should be allowed"
        # Clean up singleton
        from middleware.rate_limiter import RateLimiter
        RateLimiter._instance = None

    def test_rate_limiter_blocks_over_limit(self):
        """Requests over the limit should be blocked."""
        limiter = self._get_fresh_limiter()
        for _ in range(5):
            limiter.check_rate_limit("over_user", limit=5, window=60)
        allowed = limiter.check_rate_limit("over_user", limit=5, window=60)
        assert not allowed
        from middleware.rate_limiter import RateLimiter
        RateLimiter._instance = None


# =============================================================================
# API Rate Limit Configuration (middleware/api_rate_limit.py)
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestAPIRateLimitConfig:
    """Test the API rate limit middleware configuration."""

    def test_health_endpoints_are_exempt(self):
        """Health check paths should be in the exempt set."""
        from middleware.api_rate_limit import EXEMPT_PATHS
        assert "/health" in EXEMPT_PATHS
        assert "/health/live" in EXEMPT_PATHS
        assert "/api/health" in EXEMPT_PATHS

    def test_docs_endpoints_are_exempt(self):
        """Documentation paths should be in the exempt set."""
        from middleware.api_rate_limit import EXEMPT_PATHS
        assert "/docs" in EXEMPT_PATHS
        assert "/openapi.json" in EXEMPT_PATHS

    def test_webhook_prefixes_are_exempt(self):
        """Webhook prefixes should be exempt from rate limiting."""
        from middleware.api_rate_limit import EXEMPT_PREFIXES
        assert any("/api/v1/webhook/" in p for p in EXEMPT_PREFIXES)

    def test_ai_endpoints_have_lower_limit(self):
        """AI endpoints should have a lower per-minute limit than general endpoints."""
        from middleware.api_rate_limit import _get_limit_for_request, AI_RPM, AUTH_RPM
        ai_limit = _get_limit_for_request("/api/v1/ai/chat", is_authenticated=True)
        general_limit = _get_limit_for_request("/api/v1/leads/", is_authenticated=True)
        assert ai_limit <= general_limit, (
            f"AI limit ({ai_limit}) should be <= general limit ({general_limit})"
        )

    def test_unauthenticated_gets_lower_limit(self):
        """Unauthenticated requests should get a lower limit."""
        from middleware.api_rate_limit import _get_limit_for_request
        auth_limit = _get_limit_for_request("/api/v1/leads/", is_authenticated=True)
        unauth_limit = _get_limit_for_request("/api/v1/leads/", is_authenticated=False)
        assert unauth_limit < auth_limit, (
            f"Unauth limit ({unauth_limit}) should be < auth limit ({auth_limit})"
        )

    def test_prefix_limits_are_positive(self):
        """All prefix limits should be positive integers."""
        from middleware.api_rate_limit import PREFIX_LIMITS
        for prefix, limit in PREFIX_LIMITS:
            assert isinstance(limit, int), f"Limit for {prefix} is not int: {type(limit)}"
            assert limit > 0, f"Limit for {prefix} is not positive: {limit}"

    def test_window_is_60_seconds(self):
        """Sliding window should be 60 seconds (1 minute)."""
        from middleware.api_rate_limit import WINDOW_SECONDS
        assert WINDOW_SECONDS == 60


# =============================================================================
# Tenant-Level Rate Limits (config)
# =============================================================================

@pytest.mark.security
@pytest.mark.unit
class TestTenantRateLimitConfig:
    """Verify tenant tier rate limit configuration is complete."""

    def test_tenant_tiers_have_required_keys(self):
        """Each tenant tier config must have requests_per_min and ai_per_min."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import TENANT_TIER_LIMITS

        for tier_name, config in TENANT_TIER_LIMITS.items():
            assert "requests_per_min" in config, f"Missing requests_per_min in tier {tier_name}"
            assert "ai_per_min" in config, f"Missing ai_per_min in tier {tier_name}"
            assert config["requests_per_min"] > 0
            assert config["ai_per_min"] > 0

    def test_default_tier_exists(self):
        """A 'default' tier must exist as fallback."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from middleware.rate_limiting import TENANT_TIER_LIMITS

        assert "default" in TENANT_TIER_LIMITS
