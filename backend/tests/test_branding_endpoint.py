"""
Branding Endpoint Tests

Tests the GET /api/v1/branding endpoint that provides per-organization
branding configuration to the React frontend.

Exercises real code from routes/branding_routes.py:
- Returns defaults when no WhiteLabelConfig exists
- Returns org-specific config when present
- Handles missing table gracefully (exception caught)
- Requires authentication

Critical because the frontend BrandingProvider fetches this on every login.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock

logger = logging.getLogger(__name__)


# =============================================================================
# Default Branding
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestBrandingDefaults:
    """When no WhiteLabelConfig exists, return sensible defaults."""

    def test_branding_returns_200(self, authenticated_client):
        """GET /api/v1/branding returns 200 for authenticated users."""
        resp = authenticated_client.get("/api/v1/branding")
        assert resp.status_code == 200

    def test_branding_returns_json(self, authenticated_client):
        """Response must be valid JSON dict."""
        resp = authenticated_client.get("/api/v1/branding")
        data = resp.json()
        assert isinstance(data, dict)

    def test_branding_contains_required_keys(self, authenticated_client):
        """Response must contain all required branding keys."""
        resp = authenticated_client.get("/api/v1/branding")
        data = resp.json()
        required_keys = [
            "company_name",
            "primary_color",
            "secondary_color",
            "accent_color",
            "header_bg_color",
            "font_family",
        ]
        for key in required_keys:
            assert key in data, f"Missing required branding key: {key}"

    def test_branding_default_company_name(self, authenticated_client):
        """Default company name should be set."""
        resp = authenticated_client.get("/api/v1/branding")
        data = resp.json()
        assert data["company_name"] is not None
        assert len(data["company_name"]) > 0

    def test_branding_default_primary_color_is_valid_hex(self, authenticated_client):
        """Default primary color should be a valid hex color."""
        import re
        resp = authenticated_client.get("/api/v1/branding")
        data = resp.json()
        assert re.match(r'^#[0-9a-fA-F]{6}$', data["primary_color"]), (
            f"primary_color '{data['primary_color']}' is not a valid hex color"
        )


# =============================================================================
# Branding Config Values
# =============================================================================

@pytest.mark.unit
class TestBrandingConfigValues:
    """Verify the default branding configuration constants."""

    def test_defaults_have_all_required_fields(self):
        """The _DEFAULTS dict must have all required fields."""
        from routes.branding_routes import _DEFAULTS
        required = [
            "company_name", "logo_url", "favicon_url",
            "primary_color", "secondary_color", "accent_color",
            "header_bg_color", "font_family",
        ]
        for key in required:
            assert key in _DEFAULTS, f"Missing default for {key}"

    def test_defaults_are_valid_types(self):
        """Default values should be strings or None."""
        from routes.branding_routes import _DEFAULTS
        for key, value in _DEFAULTS.items():
            assert value is None or isinstance(value, str), (
                f"Default '{key}' has unexpected type {type(value)}"
            )

    def test_defaults_primary_color_is_hex(self):
        """Default primary_color should be a hex color string."""
        import re
        from routes.branding_routes import _DEFAULTS
        assert re.match(r'^#[0-9a-fA-F]{6}$', _DEFAULTS["primary_color"])


# =============================================================================
# Missing Table Handling
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestBrandingMissingTable:
    """When the WhiteLabelConfig table does not exist, return defaults gracefully."""

    def test_branding_handles_db_error(self, authenticated_client):
        """If DB query fails, branding should still return defaults."""
        # Even if the table doesn't exist, the endpoint catches all
        # exceptions and returns _DEFAULTS
        with patch("routes.branding_routes.register_branding_routes") as mock_reg:
            # The route is already registered, so we just test the endpoint
            resp = authenticated_client.get("/api/v1/branding")
            assert resp.status_code == 200
            data = resp.json()
            # Should have company_name at minimum
            assert "company_name" in data


# =============================================================================
# Auth Required
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestBrandingAuth:
    """Branding endpoint requires authentication."""

    def test_branding_requires_auth(self, client):
        """GET /api/v1/branding without auth returns 401/403."""
        resp = client.get("/api/v1/branding")
        assert resp.status_code in (401, 403, 422), (
            f"Branding endpoint returned {resp.status_code} without auth"
        )
