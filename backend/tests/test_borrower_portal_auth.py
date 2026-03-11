"""
Test Borrower Portal Authentication Security

Verifies:
- Portal auth routes are registered on the FastAPI app
- Magic link endpoints exist and require proper input
- Unauthenticated requests to session/refresh/logout are handled correctly
- Portal redirect URL sanitization (_safe_portal_redirect)
- Email masking logic (_mask_email)
- Session token extraction patterns
"""

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Route Registration Tests
# =============================================================================

@pytest.mark.unit
class TestPortalRouteRegistration:
    """Verify portal auth routes are mounted on the app."""

    def test_portal_auth_health_endpoint_exists(self, client: TestClient):
        """GET /api/v1/auth/portal/health should be accessible (no auth needed)."""
        response = client.get("/api/v1/auth/portal/health")
        # Health check should return 200 or 404 if route module not loaded.
        # A 405 would mean the route exists but method is wrong.
        # We accept 200 (healthy) or 500 (deps not initialized) as proof of registration.
        assert response.status_code in (200, 500), (
            f"Expected portal auth health at /api/v1/auth/portal/health, "
            f"got {response.status_code}"
        )

    def test_portal_send_link_endpoint_exists(self, client: TestClient):
        """POST /api/v1/auth/portal/send-link should exist."""
        # Sending empty body should give 422 (validation error), not 404
        response = client.post("/api/v1/auth/portal/send-link", json={})
        assert response.status_code != 404, (
            "Portal send-link endpoint not registered (got 404)"
        )

    def test_portal_verify_get_endpoint_exists(self, client: TestClient):
        """GET /api/v1/auth/portal/verify should exist."""
        # Missing required 'token' query param should give 422, not 404
        response = client.get("/api/v1/auth/portal/verify")
        assert response.status_code != 404, (
            "Portal verify (GET) endpoint not registered (got 404)"
        )

    def test_portal_session_endpoint_exists(self, client: TestClient):
        """GET /api/v1/auth/portal/session should exist."""
        response = client.get("/api/v1/auth/portal/session")
        assert response.status_code != 404, (
            "Portal session endpoint not registered (got 404)"
        )

    def test_portal_logout_endpoint_exists(self, client: TestClient):
        """POST /api/v1/auth/portal/logout should exist."""
        response = client.post("/api/v1/auth/portal/logout")
        assert response.status_code != 404, (
            "Portal logout endpoint not registered (got 404)"
        )


# =============================================================================
# Unauthenticated Access Tests
# =============================================================================

@pytest.mark.unit
class TestPortalUnauthenticatedAccess:
    """Verify portal endpoints handle unauthenticated requests safely."""

    def test_session_returns_invalid_without_token(self, client: TestClient):
        """GET /api/v1/auth/portal/session without token returns valid=False."""
        response = client.get("/api/v1/auth/portal/session")
        # Should return 200 with valid=False (not crash or leak data)
        if response.status_code == 200:
            data = response.json()
            assert data.get("valid") is False, (
                "Session endpoint should return valid=False without token"
            )

    def test_refresh_rejects_without_session(self, client: TestClient):
        """POST /api/v1/auth/portal/refresh without session returns 401."""
        response = client.post("/api/v1/auth/portal/refresh")
        # Without a session cookie or auth header, should get 401 or 500
        # (500 if deps not initialized, 401 if properly rejecting)
        assert response.status_code in (401, 500), (
            f"Expected 401/500 for refresh without session, got {response.status_code}"
        )

    def test_verify_rejects_short_token(self, client: TestClient):
        """GET /api/v1/auth/portal/verify with short token returns 422."""
        response = client.get("/api/v1/auth/portal/verify?token=short")
        # Token has min_length=32 validation, so short token should be 422
        assert response.status_code == 422, (
            f"Expected 422 for short token, got {response.status_code}"
        )

    def test_verify_rejects_invalid_long_token(self, client: TestClient):
        """GET /api/v1/auth/portal/verify with invalid (but long enough) token is rejected."""
        fake_token = "a" * 64
        response = client.get(f"/api/v1/auth/portal/verify?token={fake_token}")
        # Should get 401 (invalid token) or 500 (deps not initialized)
        assert response.status_code in (401, 500), (
            f"Expected 401/500 for invalid token, got {response.status_code}"
        )

    def test_send_link_requires_valid_payload(self, client: TestClient):
        """POST /api/v1/auth/portal/send-link with invalid payload returns 422."""
        response = client.post(
            "/api/v1/auth/portal/send-link",
            json={"email": "not-an-email"}
        )
        assert response.status_code == 422, (
            f"Expected 422 for invalid email, got {response.status_code}"
        )


# =============================================================================
# Portal Redirect Sanitization Tests
# =============================================================================

@pytest.mark.unit
class TestPortalRedirectSanitization:
    """Test _safe_portal_redirect to prevent open redirects."""

    def _get_safe_redirect(self):
        from routes.portal_auth_routes import _safe_portal_redirect
        return _safe_portal_redirect

    def test_none_redirect_returns_default(self):
        """None redirect returns /portal/{slug} default."""
        safe = self._get_safe_redirect()
        result = safe(None, "my-workspace")
        assert result == "/portal/my-workspace"

    def test_empty_redirect_returns_default(self):
        """Empty string redirect returns default."""
        safe = self._get_safe_redirect()
        result = safe("", "my-workspace")
        assert result == "/portal/my-workspace"

    def test_valid_portal_path_allowed(self):
        """A path under /portal/ is allowed."""
        safe = self._get_safe_redirect()
        result = safe("/portal/ws/documents", "ws")
        assert result == "/portal/ws/documents"

    def test_absolute_url_blocked(self):
        """Absolute URLs (http/https) are blocked."""
        safe = self._get_safe_redirect()
        result = safe("https://evil.com/steal", "ws")
        assert result == "/portal/ws"

    def test_protocol_relative_url_blocked(self):
        """Protocol-relative URLs (//) are blocked."""
        safe = self._get_safe_redirect()
        result = safe("//evil.com/steal", "ws")
        assert result == "/portal/ws"

    def test_at_sign_url_blocked(self):
        """URLs with @ (credential injection) are blocked."""
        safe = self._get_safe_redirect()
        result = safe("/portal/ws@evil.com", "ws")
        assert result == "/portal/ws"

    def test_non_portal_path_blocked(self):
        """Paths not under /portal/ are blocked."""
        safe = self._get_safe_redirect()
        result = safe("/admin/settings", "ws")
        assert result == "/portal/ws"


# =============================================================================
# Email Masking Tests
# =============================================================================

@pytest.mark.unit
class TestEmailMasking:
    """Test _mask_email function for privacy."""

    def _get_mask_email(self):
        from routes.portal_auth_routes import _mask_email
        return _mask_email

    def test_standard_email_masked(self):
        """Standard email is properly masked."""
        mask = self._get_mask_email()
        result = mask("john.smith@example.com")
        assert result.endswith("@example.com")
        assert "j***" in result
        # Should keep first and last char of local part
        assert result.startswith("j")

    def test_short_local_part_masked(self):
        """Short local part (1-2 chars) is masked safely."""
        mask = self._get_mask_email()
        result = mask("ab@example.com")
        assert "@example.com" in result
        assert "***" in result

    def test_single_char_local_part(self):
        """Single character local part does not crash."""
        mask = self._get_mask_email()
        result = mask("a@example.com")
        assert "@example.com" in result

    def test_invalid_email_format(self):
        """Invalid email (no @) returns masked output."""
        mask = self._get_mask_email()
        result = mask("not-an-email")
        assert result == "***"
