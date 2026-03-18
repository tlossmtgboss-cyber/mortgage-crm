"""
Tests for scheduler widget configuration routes (public, no auth required).

Covers:
  - GET /widget/config/{org_slug}              Org-level widget config
  - GET /widget/config/{org_slug}/{lo_slug}    LO-specific widget config

These endpoints are public (no auth), so the tests focus on:
  - Org lookup and 404 handling
  - Branding defaults
  - LO slug resolution
  - Embed instruction generation
  - Handling of missing scheduler models gracefully
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Mock ORM objects
# ---------------------------------------------------------------------------

class MockOrganization:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Test Mortgage Co")
        self.is_active = True
        self.booking_slug = kwargs.get("booking_slug", "test-mortgage")
        self.slug = kwargs.get("slug", "test-mortgage")
        self.booking_logo_url = kwargs.get("booking_logo_url", "https://example.com/logo.png")
        self.booking_primary_color = kwargs.get("booking_primary_color", "#112233")
        self.booking_accent_color = kwargs.get("booking_accent_color", "#445566")
        self.booking_tagline = kwargs.get("booking_tagline", "Best rates guaranteed")


class MockLOUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.organization_id = kwargs.get("organization_id", 1)
        self.slug = kwargs.get("slug", "john-smith")
        self.full_name = kwargs.get("full_name", "John Smith")
        self.title = kwargs.get("title", "Senior Loan Officer")
        self.nmls_number = kwargs.get("nmls_number", "123456")
        self.nmls_id = kwargs.get("nmls_id", None)
        self.headshot_url = kwargs.get("headshot_url", "https://example.com/john.jpg")
        self.is_active = True
        self.email = "john@test.com"


class MockBookingLink:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", None)
        self.slug = kwargs.get("slug", "book-with-us")
        self.is_active = True
        self.is_public = True
        self.single_appointment_type_id = kwargs.get("single_appointment_type_id", None)
        self.appointment_type_ids = kwargs.get("appointment_type_ids", None)


class MockAppointmentType:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.type_key = kwargs.get("type_key", "loan_review")
        self.type_name = kwargs.get("type_name", "Loan Review Call")
        self.description = kwargs.get("description", "30-minute loan review")
        self.default_duration_minutes = kwargs.get("default_duration_minutes", 30)
        self.allowed_durations = kwargs.get("allowed_durations", [15, 30, 60])
        self.color = kwargs.get("color", "#1a73e8")
        self.is_active = True
        self.is_public = True
        self.organization_id = kwargs.get("organization_id", 1)


def _build_chainable_mock(results=None, first_result=None):
    """Create a mock that supports chained .filter().first()/.all()."""
    q = MagicMock()
    q.filter = MagicMock(return_value=q)
    q.limit = MagicMock(return_value=q)
    q.all = MagicMock(return_value=results or [])
    q.first = MagicMock(return_value=first_result)
    return q


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWidgetConfigOrgLevel:
    """Tests for GET /widget/config/{org_slug}."""

    @pytest.mark.asyncio
    async def test_org_not_found_returns_404(self):
        """Unknown org slug returns 404."""
        from routes.scheduler.widget_config import get_widget_config

        db = MagicMock()
        q = _build_chainable_mock(first_result=None)
        db.query = MagicMock(return_value=q)

        with patch("routes.scheduler.widget_config.Organization", create=True), \
             patch("routes.scheduler.widget_config.User", create=True):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_widget_config("nonexistent-slug", MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_org_found_returns_branding(self):
        """Valid org slug returns branding information."""
        from routes.scheduler.widget_config import _get_widget_config_impl

        org = MockOrganization()
        db = MagicMock()

        # First query returns org; subsequent queries return booking link/types
        call_count = [0]
        def side_effect_query(model):
            call_count[0] += 1
            q = _build_chainable_mock(first_result=org if call_count[0] == 1 else None)
            return q

        db.query = MagicMock(side_effect=side_effect_query)

        with patch("routes.scheduler.widget_config.Organization", MockOrganization), \
             patch("routes.scheduler.widget_config.User", MockLOUser):
            result = await _get_widget_config_impl("test-mortgage", None, db)

        assert result["branding"]["org_name"] == "Test Mortgage Co"
        assert result["branding"]["primary_color"] == "#112233"
        assert result["lo"] is None  # No LO slug provided

    @pytest.mark.asyncio
    async def test_default_colors_when_not_configured(self):
        """When org has no custom colors, defaults are returned."""
        from routes.scheduler.widget_config import _get_widget_config_impl

        org = MockOrganization(
            booking_primary_color=None,
            booking_accent_color=None,
        )
        db = MagicMock()

        call_count = [0]
        def side_effect_query(model):
            call_count[0] += 1
            q = _build_chainable_mock(first_result=org if call_count[0] == 1 else None)
            return q

        db.query = MagicMock(side_effect=side_effect_query)

        with patch("routes.scheduler.widget_config.Organization", MockOrganization), \
             patch("routes.scheduler.widget_config.User", MockLOUser):
            result = await _get_widget_config_impl("test-mortgage", None, db)

        assert result["branding"]["primary_color"] == "#1a73e8"
        assert result["branding"]["accent_color"] == "#34a853"


class TestWidgetConfigWithLO:
    """Tests for GET /widget/config/{org_slug}/{lo_slug}."""

    @pytest.mark.asyncio
    async def test_lo_slug_returns_lo_info(self):
        """Valid LO slug returns LO details alongside org branding."""
        from routes.scheduler.widget_config import _get_widget_config_impl

        org = MockOrganization()
        lo = MockLOUser()
        db = MagicMock()

        call_count = [0]
        def side_effect_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return _build_chainable_mock(first_result=org)
            elif call_count[0] == 2:
                return _build_chainable_mock(first_result=lo)
            else:
                return _build_chainable_mock(first_result=None)

        db.query = MagicMock(side_effect=side_effect_query)

        with patch("routes.scheduler.widget_config.Organization", MockOrganization), \
             patch("routes.scheduler.widget_config.User", MockLOUser):
            result = await _get_widget_config_impl("test-mortgage", "john-smith", db)

        assert result["lo"] is not None
        assert result["lo"]["name"] == "John Smith"
        assert result["lo"]["nmls"] == "123456"

    @pytest.mark.asyncio
    async def test_invalid_lo_slug_omits_lo_info(self):
        """Unknown LO slug returns branding but lo is None."""
        from routes.scheduler.widget_config import _get_widget_config_impl

        org = MockOrganization()
        db = MagicMock()

        call_count = [0]
        def side_effect_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return _build_chainable_mock(first_result=org)
            else:
                return _build_chainable_mock(first_result=None)

        db.query = MagicMock(side_effect=side_effect_query)

        with patch("routes.scheduler.widget_config.Organization", MockOrganization), \
             patch("routes.scheduler.widget_config.User", MockLOUser):
            result = await _get_widget_config_impl("test-mortgage", "nobody", db)

        assert result["lo"] is None


class TestEmbedInstructions:
    """Tests for embed code generation."""

    def test_embed_instructions_org_only(self):
        """Embed instructions use org slug when no LO."""
        from routes.scheduler.widget_config import _build_embed_instructions

        instructions = _build_embed_instructions("my-org", None)

        assert 'data-org="my-org"' in instructions["script_embed"]
        assert "data-lo" not in instructions["script_embed"]
        assert "/book/my-org?embed=true" in instructions["iframe_embed"]

    def test_embed_instructions_with_lo(self):
        """Embed instructions include LO slug when provided."""
        from routes.scheduler.widget_config import _build_embed_instructions

        instructions = _build_embed_instructions("my-org", "john-doe")

        assert 'data-org="my-org"' in instructions["script_embed"]
        assert 'data-lo="john-doe"' in instructions["script_embed"]
        assert "/book/my-org/john-doe?embed=true" in instructions["iframe_embed"]
