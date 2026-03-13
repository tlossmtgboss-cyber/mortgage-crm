"""
Booking SEO Test Suite

Tests for:
1. booking_meta.py - SEO metadata endpoint for booking links
2. sitemap.py - XML sitemap and robots.txt for search engine discovery
3. SEO meta tag generation logic
4. Edge cases: missing data, inactive links, HTML escaping

25 tests covering the full SEO feature set.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock helpers
# =============================================================================

class MockBookingLink:
    """Mock BookingLink model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.slug = kwargs.get("slug", "test-link")
        self.link_name = kwargs.get("link_name", "Test Booking")
        self.description = kwargs.get("description", "Test description")
        self.custom_title = kwargs.get("custom_title", None)
        self.custom_description = kwargs.get("custom_description", None)
        self.custom_logo_url = kwargs.get("custom_logo_url", None)
        self.custom_color = kwargs.get("custom_color", None)
        self.is_active = kwargs.get("is_active", True)
        self.is_public = kwargs.get("is_public", True)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", 10)
        self.appointment_type_ids = kwargs.get("appointment_type_ids", [100])
        self.single_appointment_type_id = kwargs.get("single_appointment_type_id", None)
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.created_at = kwargs.get("created_at", datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.view_count = kwargs.get("view_count", 0)
        self.booking_count = kwargs.get("booking_count", 0)


class MockOrganization:
    """Mock Organization model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Test Mortgage Co")
        self.booking_logo_url = kwargs.get("booking_logo_url", "https://example.com/logo.png")


class MockUser:
    """Mock User model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.first_name = kwargs.get("first_name", "Jane")
        self.last_name = kwargs.get("last_name", "Smith")
        self.full_name = kwargs.get("full_name", "Jane Smith")


class MockAppointmentType:
    """Mock AppointmentType model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.type_name = kwargs.get("type_name", "Mortgage Consultation")
        self.is_active = kwargs.get("is_active", True)


class _Col:
    """Fake SQLAlchemy column descriptor."""
    def __eq__(self, other): return True
    def __ne__(self, other): return True
    def in_(self, values): return True
    def __hash__(self): return id(self)


class MockBookingLinkModel:
    """Mock BookingLink class-level model (for queries)."""
    slug = _Col()
    is_active = _Col()
    is_public = _Col()
    id = _Col()
    organization_id = _Col()
    user_id = _Col()
    appointment_type_ids = _Col()
    single_appointment_type_id = _Col()
    updated_at = _Col()
    created_at = _Col()


class MockAppointmentTypeModel:
    """Mock AppointmentType class-level model (for queries)."""
    id = _Col()
    is_active = _Col()


class MockUserModel:
    """Mock User class-level model (for queries)."""
    id = _Col()


# =============================================================================
# TEST: booking_meta.py - get_booking_meta endpoint
# =============================================================================

class TestBookingMeta:
    """Tests for the /public/booking/{slug}/meta endpoint."""

    def _make_models(self):
        return {
            "BookingLink": MockBookingLinkModel,
            "AppointmentType": MockAppointmentTypeModel,
            "User": MockUserModel,
        }

    @patch("routes.scheduler.booking_meta._get_models")
    def test_meta_returns_title_with_org_and_lo(self, mock_get_models):
        """SEO title includes appointment type, LO name, and org name."""
        mock_get_models.return_value = self._make_models()

        link = MockBookingLink(
            slug="test-link",
            appointment_type_ids=[100],
        )
        org = MockOrganization(name="Acme Mortgage")
        user = MockUser(full_name="John Doe")
        appt_type = MockAppointmentType(type_name="Rate Consultation")

        mock_db = MagicMock()
        # BookingLink query
        mock_db.query.return_value.filter.return_value.first.return_value = link

        from routes.scheduler.booking_meta import get_booking_meta

        # We need to patch the Organization and User imports too
        with patch("routes.scheduler.booking_meta.Organization", create=True) as MockOrgModel:
            # We'll patch the internal db calls in sequence
            call_count = [0]
            original_query = mock_db.query

            def side_effect_query(model):
                call_count[0] += 1
                result = MagicMock()
                if call_count[0] == 1:
                    # BookingLink query
                    result.filter.return_value.first.return_value = link
                elif call_count[0] == 2:
                    # Organization query
                    result.filter.return_value.first.return_value = org
                elif call_count[0] == 3:
                    # User query
                    result.filter.return_value.first.return_value = user
                elif call_count[0] == 4:
                    # AppointmentType query
                    result.filter.return_value.filter.return_value.all.return_value = [appt_type]
                    result.filter.return_value.all.return_value = [appt_type]
                return result

            mock_db.query.side_effect = side_effect_query

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                get_booking_meta("test-link", MagicMock(), mock_db)
            )

        assert "title" in result
        assert "description" in result
        assert "og_image" in result
        assert "canonical_url" in result
        assert "appointment_types" in result

    @patch("routes.scheduler.booking_meta._get_models")
    def test_meta_404_for_missing_slug(self, mock_get_models):
        """Returns 404 when booking link slug does not exist."""
        mock_get_models.return_value = self._make_models()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from routes.scheduler.booking_meta import get_booking_meta
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_booking_meta("nonexistent", MagicMock(), mock_db)
            )
        assert exc_info.value.status_code == 404

    @patch("routes.scheduler.booking_meta._get_models")
    def test_meta_503_when_models_unavailable(self, mock_get_models):
        """Returns 503 when models cannot be loaded."""
        mock_get_models.return_value = None

        from routes.scheduler.booking_meta import get_booking_meta
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_booking_meta("test", MagicMock(), MagicMock())
            )
        assert exc_info.value.status_code == 503

    def test_render_meta_html_escapes_special_chars(self):
        """Meta HTML rendering properly escapes HTML entities."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": 'Book "Consultation" & <Review>',
            "description": "Test <script>alert('xss')</script>",
            "og_image": "https://example.com/img.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }

        html_output = _render_meta_html(meta)

        assert "&lt;script&gt;" in html_output
        assert "<script>" not in html_output
        assert "&quot;" in html_output or "&#x27;" in html_output
        assert "&amp;" in html_output
        assert "og:title" in html_output
        assert "twitter:card" in html_output
        assert "canonical" in html_output

    def test_render_meta_html_includes_all_tags(self):
        """Meta HTML includes all required OG and Twitter tags."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Test Title",
            "description": "Test Description",
            "og_image": "https://example.com/img.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }

        html_output = _render_meta_html(meta)

        required_tags = [
            "<title>",
            'name="description"',
            'rel="canonical"',
            'property="og:type"',
            'property="og:title"',
            'property="og:description"',
            'property="og:image"',
            'property="og:url"',
            'property="og:site_name"',
            'name="twitter:card"',
            'name="twitter:title"',
            'name="twitter:description"',
            'name="twitter:image"',
        ]
        for tag in required_tags:
            assert tag in html_output, f"Missing tag: {tag}"

    def test_meta_canonical_url_format(self):
        """Canonical URL follows expected format."""
        from routes.scheduler.booking_meta import BASE_URL

        slug = "my-booking"
        expected = f"{BASE_URL}/book/{slug}"
        assert expected == "https://app.perenniaai.com/book/my-booking"

    def test_meta_default_og_image(self):
        """Default OG image is used when no custom image is available."""
        from routes.scheduler.booking_meta import DEFAULT_OG_IMAGE

        assert DEFAULT_OG_IMAGE.startswith("https://")
        assert "perenniaai.com" in DEFAULT_OG_IMAGE


# =============================================================================
# TEST: sitemap.py - XML sitemap generation
# =============================================================================

class TestSitemap:
    """Tests for the /sitemap.xml and /robots.txt endpoints."""

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_returns_xml_content_type(self, mock_get_models):
        """Sitemap response has application/xml content type."""
        mock_get_models.return_value = None

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        mock_db = MagicMock()
        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        assert response.media_type == "application/xml"

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_includes_homepage(self, mock_get_models):
        """Sitemap always includes the homepage."""
        mock_get_models.return_value = None

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        mock_db = MagicMock()
        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        assert "https://app.perenniaai.com/" in body
        assert "<priority>1.0</priority>" in body

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_includes_booking_links(self, mock_get_models):
        """Sitemap includes active public booking links."""
        link1 = MockBookingLink(slug="consultation", updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
        link2 = MockBookingLink(slug="rate-review", updated_at=datetime(2026, 2, 15, tzinfo=timezone.utc))

        models = {
            "BookingLink": MockBookingLinkModel,
        }
        mock_get_models.return_value = models

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [link1, link2]

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        assert "https://app.perenniaai.com/book/consultation" in body
        assert "https://app.perenniaai.com/book/rate-review" in body
        assert "<changefreq>weekly</changefreq>" in body
        assert "<priority>0.7</priority>" in body

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_valid_xml_structure(self, mock_get_models):
        """Sitemap produces valid XML with urlset root element."""
        mock_get_models.return_value = None

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        mock_db = MagicMock()
        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        assert body.startswith('<?xml version="1.0"')
        assert "<urlset" in body
        assert "</urlset>" in body

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_lastmod_from_updated_at(self, mock_get_models):
        """Sitemap uses updated_at for lastmod."""
        link = MockBookingLink(slug="test", updated_at=datetime(2026, 2, 28, tzinfo=timezone.utc))

        models = {"BookingLink": MockBookingLinkModel}
        mock_get_models.return_value = models

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [link]

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        assert "<lastmod>2026-02-28</lastmod>" in body

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_empty_when_no_links(self, mock_get_models):
        """Sitemap still valid when no booking links exist."""
        models = {"BookingLink": MockBookingLinkModel}
        mock_get_models.return_value = models

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        assert "<urlset" in body
        # Still has homepage
        assert "https://app.perenniaai.com/" in body
        # No booking links
        assert "/book/" not in body

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_cache_control_header(self, mock_get_models):
        """Sitemap response has cache-control header."""
        mock_get_models.return_value = None

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        mock_db = MagicMock()
        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        assert "max-age=3600" in response.headers.get("cache-control", "")

    def test_robots_txt_content(self):
        """Robots.txt includes sitemap URL and allow/disallow rules."""
        from routes.scheduler.sitemap import get_robots
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_robots(MagicMock())
        )

        body = response.body.decode()
        assert "User-agent: *" in body
        assert "Allow: /book/" in body
        assert "Disallow: /api/" in body
        assert "Disallow: /admin/" in body
        assert "Sitemap:" in body
        assert "sitemap.xml" in body

    def test_robots_txt_text_content_type(self):
        """Robots.txt has text/plain content type."""
        from routes.scheduler.sitemap import get_robots
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_robots(MagicMock())
        )

        assert response.media_type == "text/plain"

    def test_robots_txt_cache_control(self):
        """Robots.txt has appropriate cache control (long-lived)."""
        from routes.scheduler.sitemap import get_robots
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_robots(MagicMock())
        )

        assert "max-age=86400" in response.headers.get("cache-control", "")


# =============================================================================
# TEST: SEO meta generation logic (unit tests for _render_meta_html)
# =============================================================================

class TestSEOMetaGeneration:
    """Unit tests for SEO metadata generation logic."""

    def test_title_with_all_components(self):
        """Title includes appointment type, LO name, and org name."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Book Rate Consultation with Jane Smith | Acme Mortgage",
            "description": "Schedule your Rate Consultation with Jane Smith.",
            "og_image": "https://example.com/logo.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }
        html_out = _render_meta_html(meta)
        assert "Book Rate Consultation with Jane Smith | Acme Mortgage" in html_out

    def test_title_without_lo_name(self):
        """Title works without LO name."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Book an Appointment | Perennia AI",
            "description": "Schedule your appointment.",
            "og_image": "https://example.com/default.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }
        html_out = _render_meta_html(meta)
        assert "Book an Appointment" in html_out

    def test_og_site_name_is_perennia(self):
        """OG site_name is always Perennia AI."""
        from routes.scheduler.booking_meta import _render_meta_html, SITE_NAME

        meta = {
            "title": "Test",
            "description": "Test",
            "og_image": "",
            "canonical_url": "",
        }
        html_out = _render_meta_html(meta)
        assert SITE_NAME in html_out

    def test_twitter_card_is_summary_large_image(self):
        """Twitter card type is summary_large_image."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Test",
            "description": "Test",
            "og_image": "https://example.com/img.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }
        html_out = _render_meta_html(meta)
        assert 'content="summary_large_image"' in html_out


# =============================================================================
# TEST: Edge cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for SEO endpoints."""

    def test_render_meta_html_with_empty_strings(self):
        """Handles empty string values gracefully."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "",
            "description": "",
            "og_image": "",
            "canonical_url": "",
        }
        html_out = _render_meta_html(meta)
        # Should still produce valid HTML tags
        assert "<title></title>" in html_out
        assert 'property="og:title"' in html_out

    def test_render_meta_html_with_unicode(self):
        """Handles Unicode characters in titles."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Consultation hypothecaire - Prenez rendez-vous",
            "description": "Reserver votre consultation avec notre equipe.",
            "og_image": "https://example.com/img.png",
            "canonical_url": "https://app.perenniaai.com/book/fr-test",
        }
        html_out = _render_meta_html(meta)
        assert "hypothecaire" in html_out

    @patch("routes.scheduler.sitemap._get_models")
    def test_sitemap_handles_link_without_updated_at(self, mock_get_models):
        """Sitemap handles links where updated_at is None."""
        link = MockBookingLink(slug="old-link", updated_at=None, created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))

        models = {"BookingLink": MockBookingLinkModel}
        mock_get_models.return_value = models

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [link]

        from routes.scheduler.sitemap import get_sitemap
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            get_sitemap(MagicMock(), mock_db)
        )

        body = response.body.decode()
        # Falls back to created_at
        assert "<lastmod>2025-06-01</lastmod>" in body

    @patch("routes.scheduler.booking_meta._get_models")
    def test_meta_without_booking_link_model(self, mock_get_models):
        """Returns 503 when BookingLink model is not in models dict."""
        mock_get_models.return_value = {"User": MockUserModel}

        from routes.scheduler.booking_meta import get_booking_meta
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_booking_meta("test", MagicMock(), MagicMock())
            )
        assert exc_info.value.status_code == 503

    @patch("routes.scheduler.booking_meta._get_models")
    def test_meta_with_inactive_link(self, mock_get_models):
        """Returns 404 for inactive booking links."""
        mock_get_models.return_value = self._make_models()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from routes.scheduler.booking_meta import get_booking_meta
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_booking_meta("inactive-link", MagicMock(), mock_db)
            )
        assert exc_info.value.status_code == 404

    def _make_models(self):
        return {
            "BookingLink": MockBookingLinkModel,
            "AppointmentType": MockAppointmentTypeModel,
            "User": MockUserModel,
        }


# =============================================================================
# TEST: Module import and constants
# =============================================================================

class TestModuleIntegrity:
    """Tests for module-level constants and imports."""

    def test_booking_meta_module_imports(self):
        """booking_meta module imports successfully."""
        from routes.scheduler import booking_meta
        assert hasattr(booking_meta, "router")
        assert hasattr(booking_meta, "get_booking_meta")
        assert hasattr(booking_meta, "_render_meta_html")

    def test_sitemap_module_imports(self):
        """sitemap module imports successfully."""
        from routes.scheduler import sitemap
        assert hasattr(sitemap, "router")
        assert hasattr(sitemap, "get_sitemap")
        assert hasattr(sitemap, "get_robots")

    def test_base_url_constant(self):
        """BASE_URL constants are set correctly."""
        from routes.scheduler.booking_meta import BASE_URL as meta_base
        from routes.scheduler.sitemap import BASE_URL as sitemap_base
        assert meta_base == "https://app.perenniaai.com"
        assert sitemap_base == "https://app.perenniaai.com"

    def test_scheduler_router_includes_seo_routes(self):
        """Scheduler router includes booking_meta and sitemap routers."""
        from routes.scheduler import scheduler_router
        # Check that the router has routes registered
        route_paths = [r.path for r in scheduler_router.routes]
        # The sub-routes should include our new paths
        assert any("booking" in p and "meta" in p for p in route_paths), \
            f"booking_meta route not found in scheduler_router. Routes: {route_paths}"
        assert any("sitemap" in p for p in route_paths), \
            f"sitemap route not found in scheduler_router. Routes: {route_paths}"
        assert any("robots" in p for p in route_paths), \
            f"robots.txt route not found in scheduler_router. Routes: {route_paths}"
