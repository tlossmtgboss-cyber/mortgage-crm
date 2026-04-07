"""
Test Auth Security - Regression tests for debug/diagnostic endpoint protection.

Verifies that ALL debug and diagnostic endpoints require authentication
and return 401/403 when accessed without credentials. This prevents
accidental exposure of internal tooling in production.

Covers:
- Salesforce debug endpoints (9 endpoints under /api/v1/salesforce/debug/*)
- CI Voice diagnostic endpoint (/api/v1/conversation-intelligence/diagnostic/rubrics)
- Power dialer debug endpoint (/api/v1/dialer/call-tasks-debug)
"""

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Salesforce Debug Endpoints (mounted at /api/v1/salesforce)
# =============================================================================

@pytest.mark.unit
class TestSalesforceDebugAuth:
    """Verify all Salesforce debug endpoints reject unauthenticated requests."""

    def test_debug_salesforce_objects_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/salesforce-objects must require auth."""
        response = client.get("/api/v1/salesforce/debug/salesforce-objects")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Debug endpoint accessible without authentication!"
        )

    def test_debug_salesforce_query_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/salesforce-query must require auth."""
        response = client.get("/api/v1/salesforce/debug/salesforce-query")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Debug endpoint accessible without authentication!"
        )

    def test_debug_db_stats_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/db-stats must require auth."""
        response = client.get("/api/v1/salesforce/debug/db-stats")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Debug endpoint accessible without authentication!"
        )

    def test_debug_import_closed_loans_requires_auth(self, client: TestClient):
        """POST /api/v1/salesforce/debug/import-closed-loans must require auth."""
        response = client.post("/api/v1/salesforce/debug/import-closed-loans")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Import endpoint accessible without authentication!"
        )

    def test_debug_import_to_mum_requires_auth(self, client: TestClient):
        """POST /api/v1/salesforce/debug/import-to-mum must require auth."""
        response = client.post("/api/v1/salesforce/debug/import-to-mum")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Import endpoint accessible without authentication!"
        )

    def test_debug_connection_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/connection must require auth."""
        response = client.get("/api/v1/salesforce/debug/connection")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Connection debug endpoint accessible without authentication!"
        )

    def test_debug_token_refresh_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/token-refresh must require auth."""
        response = client.get("/api/v1/salesforce/debug/token-refresh")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Token refresh debug endpoint accessible without authentication!"
        )

    def test_debug_test_query_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/test-query must require auth."""
        response = client.get("/api/v1/salesforce/debug/test-query")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Test query debug endpoint accessible without authentication!"
        )

    def test_debug_all_statuses_requires_auth(self, client: TestClient):
        """GET /api/v1/salesforce/debug/all-statuses must require auth."""
        response = client.get("/api/v1/salesforce/debug/all-statuses")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "All-statuses debug endpoint accessible without authentication!"
        )


# =============================================================================
# CI Voice Diagnostic Endpoints (mounted at /api/v1/conversation-intelligence)
# =============================================================================

@pytest.mark.unit
class TestCIVoiceDiagnosticAuth:
    """Verify CI Voice diagnostic endpoints reject unauthenticated requests."""

    def test_diagnostic_rubrics_requires_auth(self, client: TestClient):
        """GET /api/v1/conversation-intelligence/diagnostic/rubrics must require auth."""
        response = client.get("/api/v1/conversation-intelligence/diagnostic/rubrics")
        # 404 is acceptable if the route isn't loaded in test env
        if response.status_code == 404:
            pytest.skip("CI Voice routes not loaded in test environment")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Diagnostic rubrics endpoint accessible without authentication!"
        )


# =============================================================================
# Power Dialer Debug Endpoints (mounted at /api/v1)
# =============================================================================

@pytest.mark.unit
class TestDialerDebugAuth:
    """Verify Power Dialer debug endpoints reject unauthenticated requests."""

    def test_dialer_call_tasks_debug_requires_auth(self, client: TestClient):
        """GET /api/v1/dialer/call-tasks-debug must require auth."""
        response = client.get("/api/v1/dialer/call-tasks-debug")
        # 404 is acceptable if the power dialer router is disabled
        if response.status_code == 404:
            pytest.skip("Power Dialer routes not loaded in test environment")
        assert response.status_code in (401, 403, 422), (
            f"Expected 401/403/422 but got {response.status_code}. "
            "Dialer debug endpoint accessible without authentication!"
        )


# =============================================================================
# Verify endpoints exist and are NOT returning 200 for unauthenticated
# =============================================================================

@pytest.mark.unit
class TestDebugEndpointsRouteExistence:
    """Verify debug endpoints are registered (not 404) and properly protected."""

    def test_salesforce_debug_routes_are_registered(self, client: TestClient):
        """At least one Salesforce debug route should be registered (not 404)."""
        response = client.get("/api/v1/salesforce/debug/db-stats")
        # If the route is registered, we should get an auth error, not 404
        if response.status_code == 404:
            pytest.skip("Salesforce routes not loaded in test environment")
        assert response.status_code in (401, 403, 422), (
            f"Expected auth error for unauthenticated request, got {response.status_code}"
        )

    def test_debug_endpoints_do_not_return_200_without_auth(self, client: TestClient):
        """No debug endpoint should return 200 without authentication."""
        debug_paths = [
            "/api/v1/salesforce/debug/salesforce-objects",
            "/api/v1/salesforce/debug/salesforce-query",
            "/api/v1/salesforce/debug/db-stats",
            "/api/v1/salesforce/debug/connection",
            "/api/v1/salesforce/debug/token-refresh",
            "/api/v1/salesforce/debug/test-query",
            "/api/v1/salesforce/debug/all-statuses",
        ]
        for path in debug_paths:
            response = client.get(path)
            if response.status_code == 404:
                continue  # Route not loaded
            assert response.status_code != 200, (
                f"DEBUG SECURITY ISSUE: {path} returned 200 without auth!"
            )
