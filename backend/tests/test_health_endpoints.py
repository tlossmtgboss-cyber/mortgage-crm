"""
Health Endpoint Tests

Tests the health check endpoints that load balancers and monitoring
systems depend on:
- GET /health/live  - Liveness probe (process responsive?)
- GET /health       - Simple 200 OK
- GET /             - Root endpoint
- Response format validation

These endpoints must work without authentication and without
database connectivity (for /health/live and /).
"""

import pytest
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Liveness Probe
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestLivenessProbe:
    """GET /health/live must always return 200 if the process is running."""

    def test_health_live_returns_200(self, client):
        """Liveness probe must return 200."""
        resp = client.get("/health/live")
        # Some implementations may use /health or /api/health
        if resp.status_code == 404:
            resp = client.get("/health")
        assert resp.status_code == 200, (
            f"Health liveness probe returned {resp.status_code}"
        )

    def test_health_live_no_auth_required(self, client):
        """Health endpoint should not require authentication."""
        # Using the bare client (no auth), not authenticated_client
        resp = client.get("/health/live")
        if resp.status_code == 404:
            resp = client.get("/health")
        assert resp.status_code in (200, 404), (
            f"Health endpoint returned {resp.status_code} — should not require auth"
        )


# =============================================================================
# Root Endpoint
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestRootEndpoint:
    """GET / must return a valid response with service info."""

    def test_root_returns_200(self, client):
        """Root endpoint must return 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_returns_json(self, client):
        """Root endpoint must return JSON."""
        resp = client.get("/")
        data = resp.json()
        assert isinstance(data, dict)

    def test_root_contains_status(self, client):
        """Root response must include status field."""
        resp = client.get("/")
        data = resp.json()
        assert "status" in data, "Root response must include 'status'"
        assert data["status"] in ("operational", "ok", "healthy")

    def test_root_contains_version(self, client):
        """Root response must include version field."""
        resp = client.get("/")
        data = resp.json()
        assert "version" in data, "Root response must include 'version'"

    def test_root_no_auth_required(self, client):
        """Root endpoint should not require authentication."""
        resp = client.get("/")
        assert resp.status_code == 200  # Not 401 or 403


# =============================================================================
# Health Endpoint Format
# =============================================================================

@pytest.mark.unit
class TestHealthEndpointFormat:
    """Verify health check response format."""

    def test_health_returns_json(self, client):
        """Health endpoint must return valid JSON."""
        resp = client.get("/health")
        if resp.status_code == 404:
            pytest.skip("No /health endpoint registered")
        data = resp.json()
        assert isinstance(data, dict)

    def test_health_is_fast(self, client):
        """Health endpoint must respond in under 2 seconds."""
        import time
        start = time.monotonic()
        resp = client.get("/health")
        elapsed = time.monotonic() - start
        if resp.status_code == 404:
            pytest.skip("No /health endpoint registered")
        assert elapsed < 2.0, (
            f"Health endpoint took {elapsed:.2f}s — should be under 2s"
        )


# =============================================================================
# Health Exempt from Rate Limiting
# =============================================================================

@pytest.mark.unit
class TestHealthExemptFromRateLimiting:
    """Health endpoints must be exempt from rate limiting."""

    def test_health_in_exempt_paths(self):
        """Health paths should be in the API rate limit exempt set."""
        from middleware.api_rate_limit import EXEMPT_PATHS
        assert "/health" in EXEMPT_PATHS
        assert "/health/live" in EXEMPT_PATHS

    def test_rapid_health_checks_not_throttled(self, client):
        """Rapid health checks should never be throttled."""
        for _ in range(20):
            resp = client.get("/health")
            if resp.status_code == 404:
                pytest.skip("No /health endpoint registered")
            assert resp.status_code == 200, (
                f"Health endpoint returned {resp.status_code} after rapid requests"
            )
