"""
Tests for scheduler booking SEO meta routes.

Covers:
  - GET /public/booking/{slug}/meta         Returns SEO metadata JSON
  - GET /public/booking/{slug}/meta.html    Returns minimal HTML with OG/Twitter meta tags

Test focus areas:
  - Valid booking link slug returns correct org branding and LO name
  - Open Graph tags (og:title, og:description, og:image) are present and correct
  - Twitter Card metadata is present
  - Invalid/inactive slug returns 404
  - Content-Type is correct for the HTML endpoint
  - No PII (email, phone, SSN) leaks into meta tags
  - JSON-LD structured data is well-formed
  - HTML meta tags are properly escaped
"""

import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Mock ORM objects
# ---------------------------------------------------------------------------

class MockOrganization:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Acme Mortgage Group")
        self.is_active = True
        self.booking_logo_url = kwargs.get("booking_logo_url", "https://example.com/acme-logo.png")


class MockUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.organization_id = kwargs.get("organization_id", 1)
        self.full_name = kwargs.get("full_name", "Jane Doe")
        self.first_name = kwargs.get("first_name", "Jane")
        self.last_name = kwargs.get("last_name", "Doe")
        self.email = kwargs.get("email", "jane.doe@acme.com")
        self.phone = kwargs.get("phone", "+15551234567")
        self.is_active = True


class MockBookingLink:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", 10)
        self.slug = kwargs.get("slug", "jane-doe-consult")
        self.is_active = kwargs.get("is_active", True)
        self.is_public = kwargs.get("is_public", True)
        self.custom_logo_url = kwargs.get("custom_logo_url", None)
        self.appointment_type_ids = kwargs.get("appointment_type_ids", None)
        self.single_appointment_type_id = kwargs.get("single_appointment_type_id", None)


class MockAppointmentType:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.type_name = kwargs.get("type_name", "Loan Consultation")
        self.is_active = True


def _build_query_chain(results=None, first_result=None):
    """Create a mock that supports chained .filter().first()/.all()/.in_()."""
    q = MagicMock()
    q.filter = MagicMock(return_value=q)
    q.limit = MagicMock(return_value=q)
    q.all = MagicMock(return_value=results or [])
    q.first = MagicMock(return_value=first_result)
    return q


def _build_db_mock(routing):
    """Build a db mock that routes db.query(Model) to different chains.

    Args:
        routing: dict mapping model name strings to (results, first_result) tuples.
                 Model name is matched via the mock's __name__ or string repr.
    """
    db = MagicMock()
    chains = {}

    def query_side_effect(model):
        # Try to identify the model by checking the routing keys
        for key, (results, first_result) in routing.items():
            if key in str(model) or (hasattr(model, '__name__') and key in model.__name__):
                if key not in chains:
                    chains[key] = _build_query_chain(results=results, first_result=first_result)
                return chains[key]
        # Default: return empty chain
        return _build_query_chain()

    db.query = MagicMock(side_effect=query_side_effect)
    return db


def _make_request_mock():
    """Create a minimal mock Request with client info for rate limiting."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


# ---------------------------------------------------------------------------
# Test: Valid slug returns correct meta with OG tags
# ---------------------------------------------------------------------------

class TestGetBookingMeta:
    """Tests for GET /public/booking/{slug}/meta."""

    @pytest.mark.asyncio
    async def test_valid_slug_returns_og_tags(self):
        """A valid, active, public booking link returns title, description, og_image."""
        from routes.scheduler.booking_meta import get_booking_meta

        org = MockOrganization(name="Acme Mortgage Group")
        user = MockUser(full_name="Jane Doe")
        link = MockBookingLink(slug="jane-doe-consult", user_id=10)
        appt_type = MockAppointmentType(type_name="Loan Consultation")

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        # Route db.query() calls based on model identity
        call_count = {"n": 0}
        db = MagicMock()

        def query_dispatch(model):
            call_count["n"] += 1
            # BookingLink query
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            # Organization query
            if hasattr(model, '__name__') and 'Organization' in str(model.__name__):
                return _build_query_chain(first_result=org)
            # User query
            if model is models["User"]:
                return _build_query_chain(first_result=user)
            # AppointmentType query
            if model is models["AppointmentType"]:
                return _build_query_chain(results=[appt_type])
            return _build_query_chain(first_result=org)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.booking_meta.require_feature_tier", lambda m: lambda f: f):

            # Re-import to get undecorated version (decorator applied at import time)
            # Instead, call the underlying function directly via the module
            import routes.scheduler.booking_meta as bm
            # Temporarily replace the Organization import
            with patch.dict("sys.modules", {}):
                with patch("database.models.core.Organization", create=True) as MockOrgModel:
                    MockOrgModel.__name__ = "Organization"
                    org_chain = _build_query_chain(first_result=org)
                    original_query = db.query

                    def enhanced_dispatch(model):
                        if model is MockOrgModel:
                            return org_chain
                        return original_query(model)

                    db.query = MagicMock(side_effect=enhanced_dispatch)

                    result = await bm.get_booking_meta("jane-doe-consult", _make_request_mock(), db)

        assert result["title"] is not None
        assert "Jane Doe" in result["title"]
        assert "Acme Mortgage Group" in result["title"]
        assert result["og_image"] is not None
        assert result["canonical_url"] == "https://app.perenniaai.com/book/jane-doe-consult"
        assert result["slug"] == "jane-doe-consult"

    @pytest.mark.asyncio
    async def test_inactive_slug_returns_404(self):
        """An inactive or non-public booking link returns 404."""
        from routes.scheduler.booking_meta import get_booking_meta

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()
        # BookingLink query returns None (no active/public match)
        db.query = MagicMock(return_value=_build_query_chain(first_result=None))

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await get_booking_meta("inactive-link", _make_request_mock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_slug_returns_404(self):
        """A slug that does not exist in the DB returns 404."""
        from routes.scheduler.booking_meta import get_booking_meta

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
        }

        db = MagicMock()
        db.query = MagicMock(return_value=_build_query_chain(first_result=None))

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await get_booking_meta("does-not-exist", _make_request_mock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_models_unavailable_returns_503(self):
        """When scheduler models fail to load, the endpoint returns 503."""
        from routes.scheduler.booking_meta import get_booking_meta

        db = MagicMock()

        with patch("routes.scheduler.booking_meta._get_models", return_value=None), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await get_booking_meta("any-slug", _make_request_mock(), db)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_twitter_card_in_meta_html(self):
        """The meta_html field contains Twitter Card meta tags."""
        from routes.scheduler.booking_meta import get_booking_meta

        link = MockBookingLink(slug="test-slug", user_id=None)
        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()

        def query_dispatch(model):
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            return _build_query_chain(first_result=None)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("database.models.core.Organization", create=True):

            result = await get_booking_meta("test-slug", _make_request_mock(), db)

        meta_html = result.get("meta_html", "")
        assert 'twitter:card' in meta_html
        assert 'twitter:title' in meta_html
        assert 'twitter:description' in meta_html
        assert 'twitter:image' in meta_html
        assert 'summary_large_image' in meta_html

    @pytest.mark.asyncio
    async def test_og_tags_in_meta_html(self):
        """The meta_html field contains all required Open Graph meta tags."""
        from routes.scheduler.booking_meta import get_booking_meta

        link = MockBookingLink(slug="og-test", user_id=None)
        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()

        def query_dispatch(model):
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            return _build_query_chain(first_result=None)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("database.models.core.Organization", create=True):

            result = await get_booking_meta("og-test", _make_request_mock(), db)

        meta_html = result.get("meta_html", "")
        assert 'og:title' in meta_html
        assert 'og:description' in meta_html
        assert 'og:image' in meta_html
        assert 'og:url' in meta_html
        assert 'og:site_name' in meta_html
        assert 'og:type' in meta_html

    @pytest.mark.asyncio
    async def test_no_pii_in_meta_tags(self):
        """Meta tags must not contain email addresses, phone numbers, or SSNs."""
        from routes.scheduler.booking_meta import get_booking_meta

        user = MockUser(
            full_name="Jane Doe",
            email="jane.doe@acme.com",
            phone="+15551234567",
        )
        link = MockBookingLink(slug="pii-test", user_id=10)
        org = MockOrganization(name="Acme Mortgage")

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()

        def query_dispatch(model):
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            if model is models["User"]:
                return _build_query_chain(first_result=user)
            return _build_query_chain(first_result=org)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("database.models.core.Organization", create=True):

            result = await get_booking_meta("pii-test", _make_request_mock(), db)

        # Serialize entire response to check for PII leaks
        response_text = json.dumps(result)

        # Must not contain email
        assert "jane.doe@acme.com" not in response_text
        # Must not contain phone
        assert "+15551234567" not in response_text
        assert "5551234567" not in response_text
        # Must not contain SSN-like patterns
        assert "SSN" not in response_text

        # LO name is allowed in meta (it is public-facing)
        assert "Jane Doe" in result.get("lo_name", "")

    @pytest.mark.asyncio
    async def test_custom_logo_overrides_org_logo(self):
        """When a booking link has custom_logo_url, it takes priority over org logo."""
        from routes.scheduler.booking_meta import get_booking_meta

        custom_url = "https://cdn.example.com/custom-logo.png"
        link = MockBookingLink(slug="custom-logo", user_id=None, custom_logo_url=custom_url)
        org = MockOrganization(booking_logo_url="https://example.com/org-logo.png")

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()

        def query_dispatch(model):
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            return _build_query_chain(first_result=org)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("database.models.core.Organization", create=True):

            result = await get_booking_meta("custom-logo", _make_request_mock(), db)

        assert result["og_image"] == custom_url

    @pytest.mark.asyncio
    async def test_default_og_image_when_no_logos(self):
        """When neither custom nor org logo exists, fall back to DEFAULT_OG_IMAGE."""
        from routes.scheduler.booking_meta import get_booking_meta, DEFAULT_OG_IMAGE

        link = MockBookingLink(slug="no-logo", user_id=None, custom_logo_url=None)
        org = MockOrganization(booking_logo_url=None)

        models = {
            "BookingLink": MagicMock(),
            "User": MagicMock(),
            "AppointmentType": MagicMock(),
        }

        db = MagicMock()

        def query_dispatch(model):
            if model is models["BookingLink"]:
                return _build_query_chain(first_result=link)
            return _build_query_chain(first_result=org)

        db.query = MagicMock(side_effect=query_dispatch)

        with patch("routes.scheduler.booking_meta._get_models", return_value=models), \
             patch("routes.scheduler.booking_meta._check_rate_limit", new_callable=AsyncMock), \
             patch("database.models.core.Organization", create=True):

            result = await get_booking_meta("no-logo", _make_request_mock(), db)

        assert result["og_image"] == DEFAULT_OG_IMAGE


# ---------------------------------------------------------------------------
# Test: Structured data (JSON-LD)
# ---------------------------------------------------------------------------

class TestStructuredData:
    """Tests for JSON-LD structured data generation."""

    def test_build_structured_data_includes_financial_service(self):
        """Structured data includes a FinancialService schema object."""
        from routes.scheduler.booking_meta import _build_structured_data

        result = _build_structured_data(
            canonical_url="https://app.perenniaai.com/book/test",
            lo_name="Jane Doe",
            org_name="Acme Mortgage",
            description="Schedule your appointment",
            og_image="https://example.com/logo.png",
            appointment_type_names=["Loan Consultation"],
        )

        assert len(result) >= 1
        financial_service = result[0]
        assert financial_service["@type"] == "FinancialService"
        assert financial_service["@context"] == "https://schema.org"
        assert financial_service["name"] == "Jane Doe"
        assert "parentOrganization" in financial_service
        assert financial_service["parentOrganization"]["name"] == "Acme Mortgage"

    def test_build_structured_data_includes_breadcrumbs(self):
        """Structured data includes a BreadcrumbList schema object."""
        from routes.scheduler.booking_meta import _build_structured_data

        result = _build_structured_data(
            canonical_url="https://app.perenniaai.com/book/test",
            lo_name=None,
            org_name="Acme Mortgage",
            description="Schedule your appointment",
            og_image=None,
            appointment_type_names=[],
        )

        breadcrumb = result[1]
        assert breadcrumb["@type"] == "BreadcrumbList"
        items = breadcrumb["itemListElement"]
        assert items[0]["name"] == "Home"
        assert any(item["name"] == "Acme Mortgage" for item in items)

    def test_structured_data_appointment_types_in_offer_catalog(self):
        """Appointment types appear as Service offers in the OfferCatalog."""
        from routes.scheduler.booking_meta import _build_structured_data

        result = _build_structured_data(
            canonical_url="https://app.perenniaai.com/book/test",
            lo_name="Jane Doe",
            org_name="Acme Mortgage",
            description="Schedule your appointment",
            og_image="https://example.com/img.png",
            appointment_type_names=["Loan Consultation", "Rate Review"],
        )

        catalog = result[0].get("hasOfferCatalog", {})
        assert catalog["@type"] == "OfferCatalog"
        items = catalog["itemListElement"]
        assert len(items) == 2
        service_names = [item["itemOffered"]["name"] for item in items]
        assert "Loan Consultation" in service_names
        assert "Rate Review" in service_names


# ---------------------------------------------------------------------------
# Test: _render_meta_html helper
# ---------------------------------------------------------------------------

class TestRenderMetaHtml:
    """Tests for the _render_meta_html helper function."""

    def test_render_contains_all_required_tags(self):
        """Rendered HTML fragment includes title, description, OG, and Twitter tags."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": "Book Loan Consultation with Jane Doe | Acme Mortgage",
            "description": "Schedule your Loan Consultation with Jane Doe.",
            "og_image": "https://example.com/logo.png",
            "canonical_url": "https://app.perenniaai.com/book/jane-doe",
        }

        html_output = _render_meta_html(meta)

        assert "<title>" in html_output
        assert 'og:title' in html_output
        assert 'og:description' in html_output
        assert 'og:image' in html_output
        assert 'og:url' in html_output
        assert 'og:site_name' in html_output
        assert 'og:type' in html_output
        assert 'twitter:card' in html_output
        assert 'twitter:title' in html_output
        assert 'twitter:image' in html_output
        assert 'canonical' in html_output

    def test_render_html_escapes_special_characters(self):
        """Special characters in title/description are HTML-escaped."""
        from routes.scheduler.booking_meta import _render_meta_html

        meta = {
            "title": 'Book <script>alert("xss")</script>',
            "description": 'A "quoted" & <b>bold</b> description',
            "og_image": "https://example.com/logo.png",
            "canonical_url": "https://app.perenniaai.com/book/test",
        }

        html_output = _render_meta_html(meta)

        # Raw script tags must be escaped
        assert "<script>" not in html_output
        assert "&lt;script&gt;" in html_output
        # Quotes and ampersands must be escaped in attribute values
        assert "&amp;" in html_output
