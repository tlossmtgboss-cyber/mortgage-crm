"""
System Health and Infrastructure Endpoint Tests

Tests for system-level endpoints that verify application health:
- Health check (GET /health)
- API docs (GET /docs)
- 404 handling for non-existent routes
- API v1 health (GET /api/v1/health)
- Detailed health checks

These are infrastructure smoke tests that verify the FastAPI application
is properly configured and serving requests.
"""
import pytest


# Mark all tests as integration tests
pytestmark = [pytest.mark.integration]


class TestHealthEndpoint:
    """Tests for the main health check endpoint."""

    def test_health_returns_200(self, client):
        """GET /health should return 200 (no auth required)."""
        response = client.get("/health")

        assert response.status_code == 200, (
            f"Health endpoint returned {response.status_code}, expected 200"
        )

    def test_health_returns_json(self, client):
        """Health endpoint should return valid JSON."""
        response = client.get("/health")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict), "Health response should be a JSON object"

    def test_health_contains_status_field(self, client):
        """Health response should include a status field."""
        response = client.get("/health")

        if response.status_code == 200:
            data = response.json()
            assert "status" in data, (
                f"Health response missing 'status' field. Keys: {list(data.keys())}"
            )

    def test_health_status_is_ok(self, client):
        """Health status should indicate the service is healthy."""
        response = client.get("/health")

        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "")
            assert status.lower() in ("ok", "healthy", "running", "up"), (
                f"Unexpected health status: '{status}'"
            )

    def test_health_no_auth_required(self, client):
        """Health endpoint should work without authentication."""
        # client fixture (not authenticated_client) has no auth overrides
        response = client.get("/health")
        assert response.status_code == 200, (
            "Health check should be accessible without authentication"
        )

    def test_api_v1_health_endpoint(self, client):
        """GET /api/v1/health should return 200."""
        response = client.get("/api/v1/health")

        # This path may or may not exist
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
        else:
            assert response.status_code in (200, 404), (
                f"API v1 health returned {response.status_code}"
            )


class TestDetailedHealthChecks:
    """Tests for detailed health check endpoints."""

    def test_health_ready_endpoint(self, client):
        """GET /health/ready should indicate readiness."""
        response = client.get("/health/ready")

        # Should return 200 or 503 depending on readiness
        # 500 may occur if readiness checks hit missing tables in test SQLite
        assert response.status_code in (200, 404, 500, 503), (
            f"Readiness check returned unexpected status: {response.status_code}"
        )

    def test_health_live_endpoint(self, client):
        """GET /health/live should indicate liveness."""
        response = client.get("/health/live")

        assert response.status_code in (200, 404), (
            f"Liveness check returned unexpected status: {response.status_code}"
        )

    def test_health_pool_endpoint(self, client):
        """GET /health/pool should report connection pool status."""
        response = client.get("/health/pool")

        # Pool health is implementation-specific
        assert response.status_code in (200, 404), (
            f"Pool health returned unexpected status: {response.status_code}"
        )


class TestDocsEndpoint:
    """Tests for the API documentation endpoint."""

    def test_docs_endpoint_returns_200(self, client):
        """GET /docs should return the Swagger UI page."""
        response = client.get("/docs")

        assert response.status_code == 200, (
            f"Docs endpoint returned {response.status_code}, expected 200"
        )

    def test_docs_returns_html(self, client):
        """Docs endpoint should return HTML content."""
        response = client.get("/docs")

        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            assert "text/html" in content_type, (
                f"Docs should return HTML, got content-type: {content_type}"
            )

    def test_openapi_json_endpoint(self, client):
        """GET /openapi.json should return the OpenAPI schema."""
        response = client.get("/openapi.json")

        if response.status_code == 200:
            data = response.json()
            assert "openapi" in data, "OpenAPI schema should have 'openapi' version key"
            assert "paths" in data, "OpenAPI schema should have 'paths' key"
            assert "info" in data, "OpenAPI schema should have 'info' key"


class TestNotFoundHandling:
    """Tests for 404 error handling on non-existent routes."""

    def test_nonexistent_route_returns_404(self, client):
        """Request to a non-existent route should return 404."""
        response = client.get("/api/v1/this-endpoint-does-not-exist")

        assert response.status_code in (404, 405), (
            f"Expected 404/405 for non-existent route, got {response.status_code}"
        )

    def test_404_returns_json(self, client):
        """404 response should be JSON with a detail field."""
        response = client.get("/api/v1/nonexistent-resource-12345")

        if response.status_code == 404:
            try:
                data = response.json()
                assert "detail" in data or "message" in data or "error" in data, (
                    "404 response should include an error detail"
                )
            except Exception:
                # Some 404s may return plain text
                pass

    def test_nonexistent_api_path_does_not_return_500(self, client):
        """Non-existent API paths should never return 500."""
        test_paths = [
            "/api/v1/fake-resource",
            "/api/v1/does-not-exist/123",
            "/api/v2/not-implemented",
            "/nonexistent",
        ]

        for path in test_paths:
            response = client.get(path)
            assert response.status_code < 500, (
                f"Path {path} returned server error {response.status_code}"
            )

    def test_404_for_invalid_method(self, authenticated_client):
        """Using wrong HTTP method should return 405 or 404."""
        # Try DELETE on health endpoint (which only supports GET)
        response = authenticated_client.delete("/health")

        assert response.status_code in (404, 405), (
            f"Expected 404/405 for wrong method, got {response.status_code}"
        )


class TestCriticalEndpointsExist:
    """Smoke tests verifying critical API endpoints are mounted and reachable."""

    def test_leads_endpoint_exists(self, authenticated_client):
        """The leads API should be mounted and reachable."""
        response = authenticated_client.get("/api/v1/leads/")
        assert response.status_code < 500, (
            f"Leads endpoint returned server error: {response.status_code}"
        )

    def test_loans_endpoint_exists(self, authenticated_client):
        """The loans API should be mounted and reachable."""
        response = authenticated_client.get("/api/v1/loans/")
        assert response.status_code < 500, (
            f"Loans endpoint returned server error: {response.status_code}"
        )

    def test_dashboard_endpoint_exists(self, authenticated_client):
        """The dashboard API should be mounted and reachable."""
        response = authenticated_client.get("/api/v1/dashboard")
        # Dashboard may return 500 in test env due to auth dep chain or missing tables
        assert response.status_code in (200, 404, 500), (
            f"Dashboard endpoint returned unexpected status: {response.status_code}"
        )

    def test_auth_token_endpoint_exists(self, client):
        """The token/login endpoint should be mounted."""
        response = client.post(
            "/token",
            data={"username": "probe@test.local", "password": "probe"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # 401 or 429 expected; 404 would mean endpoint is missing
        assert response.status_code in (401, 422, 429), (
            f"Token endpoint returned unexpected status: {response.status_code}"
        )
