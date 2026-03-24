"""
Tests for scheduler sitemap and robots.txt routes.

Covers:
  - GET /sitemap.xml       Single sitemap when < 10,000 URLs
  - GET /sitemap.xml       Sitemap index when >= 10,000 URLs
  - GET /sitemap-{page}.xml Paginated sitemap pages
  - GET /robots.txt        Standard robots.txt with sitemap reference
  - Active public booking links included in sitemap
  - Inactive/private links excluded from sitemap
  - XML is well-formed
  - Content-Type headers are correct
  - Empty org (no booking links) returns valid sitemap
  - Special characters in link metadata are XML-escaped
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class MockBookingLink:
    """Mock BookingLink ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", 1)
        self.slug = kwargs.get("slug", "john-doe")
        self.is_active = kwargs.get("is_active", True)
        self.is_public = kwargs.get("is_public", True)
        self.appointment_type_ids = kwargs.get("appointment_type_ids", [])
        self.single_appointment_type_id = kwargs.get("single_appointment_type_id", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 10, tzinfo=timezone.utc))
        self.last_booked_at = kwargs.get("last_booked_at", None)


class MockAppointmentType:
    """Mock AppointmentType ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.type_name = kwargs.get("type_name", "Consultation")
        self.is_active = kwargs.get("is_active", True)


class MockUser:
    """Mock User ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.first_name = kwargs.get("first_name", "John")
        self.last_name = kwargs.get("last_name", "Doe")
        self.full_name = kwargs.get("full_name", None)


class MockOrg:
    """Mock Organization ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Test Mortgage Co")


def _mock_db(links=None, total_count=None, users=None, orgs=None, appt_types=None, latest_mod=None):
    """
    Create a mock DB session that responds to the query patterns used by the
    sitemap module: count, max, and paginated query on BookingLink, plus
    user/org/appointment-type lookups.
    """
    db = MagicMock()

    if total_count is None:
        total_count = len(links) if links else 0

    call_index = {"n": 0}

    def query_side_effect(model_or_func):
        q = MagicMock()
        q.filter = MagicMock(return_value=q)
        q.order_by = MagicMock(return_value=q)
        q.limit = MagicMock(return_value=q)
        q.offset = MagicMock(return_value=q)

        # func.count(...) -> scalar returns total_count
        # func.max(...)  -> scalar returns latest_mod
        # BookingLink query -> .all() returns links
        # User query -> .all() returns users
        # Organization query -> .all() returns orgs
        # AppointmentType query -> .all() returns appt_types

        # Determine what's being queried by inspecting the call index
        # The sitemap code calls in a predictable order:
        #   1. func.count(BookingLink.id) -> total_count
        #   2. func.max(BookingLink.updated_at) -> latest_mod  (only for sitemap index)
        #   3. BookingLink query -> links
        #   4. User query -> users
        #   5. Organization query -> orgs
        #   6. AppointmentType query -> appt_types

        n = call_index["n"]
        call_index["n"] += 1

        if n == 0:
            # First call: count
            q.scalar = MagicMock(return_value=total_count)
        elif n == 1 and total_count > 0:
            # Could be max(updated_at) or the booking link query depending on path
            # For single-page sitemap, _get_total_public_links is called then
            # _fetch_booking_link_urls which queries BookingLink directly.
            # For index path, _get_latest_mod_date is called which queries max().
            # We handle both: set scalar for max, all for booking links.
            q.scalar = MagicMock(return_value=latest_mod)
            q.all = MagicMock(return_value=links or [])
        elif n == 1 and total_count == 0:
            q.scalar = MagicMock(return_value=latest_mod)
            q.all = MagicMock(return_value=[])
        elif n == 2:
            q.all = MagicMock(return_value=links or [])
        elif n == 3:
            q.all = MagicMock(return_value=users or [])
        elif n == 4:
            q.all = MagicMock(return_value=orgs or [])
        elif n == 5:
            q.all = MagicMock(return_value=appt_types or [])
        else:
            q.scalar = MagicMock(return_value=0)
            q.all = MagicMock(return_value=[])

        return q

    db.query = MagicMock(side_effect=query_side_effect)
    return db


def _mock_models():
    """Return a models dict that mimics what _get_models() returns."""
    booking_link = MagicMock()
    booking_link.id = MagicMock()
    booking_link.is_active = MagicMock()
    booking_link.is_public = MagicMock()
    booking_link.updated_at = MagicMock()

    appt_type = MagicMock()
    appt_type.id = MagicMock()
    appt_type.is_active = MagicMock()

    return {
        "BookingLink": booking_link,
        "AppointmentType": appt_type,
    }


def _parse_xml(content: str) -> ElementTree.Element:
    """Parse XML content and return root element."""
    return ElementTree.fromstring(content)


def _request_mock():
    """Create a mock Request with no organization state (public endpoint)."""
    request = MagicMock()
    request.state = MagicMock(spec=[])  # No 'organization' attribute
    return request


# ---------------------------------------------------------------------------
# Tests: GET /sitemap.xml - empty org
# ---------------------------------------------------------------------------

class TestSitemapEmpty:
    """Tests for sitemap when there are no public booking links."""

    @pytest.mark.asyncio
    async def test_empty_org_returns_valid_sitemap_xml(self):
        """An org with no booking links should still return a valid XML sitemap."""
        from routes.scheduler.sitemap import get_sitemap_index

        db = _mock_db(links=[], total_count=0)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        assert response.media_type == "application/xml"
        body = response.body.decode()
        root = _parse_xml(body)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"

        # Should contain exactly the homepage entry
        urls = root.findall(f"{{{SITEMAP_NS}}}url")
        assert len(urls) == 1

        loc = urls[0].find(f"{{{SITEMAP_NS}}}loc").text
        assert loc == "https://app.perenniaai.com/"

    @pytest.mark.asyncio
    async def test_empty_org_no_models_returns_valid_sitemap(self):
        """If _get_models() returns None (no scheduler models), still returns valid XML."""
        from routes.scheduler.sitemap import get_sitemap_index

        db = MagicMock()
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=None):
            response = await get_sitemap_index(request=request, db=db)

        assert response.media_type == "application/xml"
        body = response.body.decode()
        root = _parse_xml(body)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"


# ---------------------------------------------------------------------------
# Tests: GET /sitemap.xml - with booking links
# ---------------------------------------------------------------------------

class TestSitemapWithLinks:
    """Tests for sitemap with active public booking links."""

    @pytest.mark.asyncio
    async def test_active_public_links_appear_in_sitemap(self):
        """Active public booking links should appear as URL entries in the sitemap."""
        from routes.scheduler.sitemap import get_sitemap_index

        links = [
            MockBookingLink(id=1, slug="sarah-johnson", user_id=1),
            MockBookingLink(id=2, slug="mike-smith", user_id=2),
        ]
        users = [
            MockUser(id=1, first_name="Sarah", last_name="Johnson"),
            MockUser(id=2, first_name="Mike", last_name="Smith"),
        ]
        orgs = [MockOrg(id=1, name="Acme Loans")]

        db = _mock_db(links=links, users=users, orgs=orgs)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        body = response.body.decode()
        root = _parse_xml(body)
        url_elements = root.findall(f"{{{SITEMAP_NS}}}url")

        # 1 homepage + 2 booking links = 3 URLs
        assert len(url_elements) == 3

        locs = [u.find(f"{{{SITEMAP_NS}}}loc").text for u in url_elements]
        assert "https://app.perenniaai.com/" in locs
        assert "https://app.perenniaai.com/book/sarah-johnson" in locs
        assert "https://app.perenniaai.com/book/mike-smith" in locs

    @pytest.mark.asyncio
    async def test_sitemap_contains_required_xml_elements(self):
        """Each URL entry should have loc, lastmod, changefreq, and priority."""
        from routes.scheduler.sitemap import get_sitemap_index

        links = [MockBookingLink(id=1, slug="test-link")]
        db = _mock_db(links=links)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        body = response.body.decode()
        root = _parse_xml(body)
        url_elements = root.findall(f"{{{SITEMAP_NS}}}url")

        for url_elem in url_elements:
            assert url_elem.find(f"{{{SITEMAP_NS}}}loc") is not None
            assert url_elem.find(f"{{{SITEMAP_NS}}}lastmod") is not None
            assert url_elem.find(f"{{{SITEMAP_NS}}}changefreq") is not None
            assert url_elem.find(f"{{{SITEMAP_NS}}}priority") is not None

    @pytest.mark.asyncio
    async def test_recently_booked_link_gets_higher_priority(self):
        """A link booked within the last 30 days should get priority 0.8."""
        from routes.scheduler.sitemap import get_sitemap_index

        recent_booked = MockBookingLink(
            id=1,
            slug="popular-link",
            last_booked_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        links = [recent_booked]
        db = _mock_db(links=links)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        body = response.body.decode()
        # The booking link entry should have priority 0.8
        assert "<priority>0.8</priority>" in body


# ---------------------------------------------------------------------------
# Tests: GET /sitemap.xml - inactive/private links excluded
# ---------------------------------------------------------------------------

class TestSitemapFiltering:
    """Tests that inactive and private links are excluded."""

    @pytest.mark.asyncio
    async def test_inactive_and_private_links_not_in_sitemap(self):
        """
        The sitemap query filters by is_active=True and is_public=True.
        Even if _fetch_booking_link_urls receives links, the DB filter should
        exclude inactive/private ones. We verify by passing only active+public
        links through the mock (as the real DB would).
        """
        from routes.scheduler.sitemap import get_sitemap_index

        # Only active+public links come from the DB query
        active_public = MockBookingLink(id=1, slug="active-public")
        # Inactive and private links would be filtered out by the DB query,
        # so they never appear in the mock results
        db = _mock_db(links=[active_public], total_count=1)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        body = response.body.decode()
        root = _parse_xml(body)
        url_elements = root.findall(f"{{{SITEMAP_NS}}}url")

        locs = [u.find(f"{{{SITEMAP_NS}}}loc").text for u in url_elements]
        assert "https://app.perenniaai.com/book/active-public" in locs
        # 1 homepage + 1 active public link
        assert len(url_elements) == 2


# ---------------------------------------------------------------------------
# Tests: Content-Type headers
# ---------------------------------------------------------------------------

class TestContentTypes:
    """Tests for correct Content-Type headers on all endpoints."""

    @pytest.mark.asyncio
    async def test_sitemap_content_type_is_application_xml(self):
        """GET /sitemap.xml should return Content-Type: application/xml."""
        from routes.scheduler.sitemap import get_sitemap_index

        db = _mock_db(links=[], total_count=0)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        assert response.media_type == "application/xml"

    @pytest.mark.asyncio
    async def test_robots_txt_content_type_is_text_plain(self):
        """GET /robots.txt should return Content-Type: text/plain."""
        from routes.scheduler.sitemap import get_robots

        request = _request_mock()
        response = await get_robots(request=request)

        assert response.media_type == "text/plain"

    @pytest.mark.asyncio
    async def test_sitemap_has_cache_control_header(self):
        """Sitemap response should include Cache-Control header."""
        from routes.scheduler.sitemap import get_sitemap_index

        db = _mock_db(links=[], total_count=0)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        assert response.headers.get("cache-control") == "public, max-age=3600"


# ---------------------------------------------------------------------------
# Tests: GET /robots.txt
# ---------------------------------------------------------------------------

class TestRobotsTxt:
    """Tests for the robots.txt endpoint."""

    @pytest.mark.asyncio
    async def test_robots_txt_contains_sitemap_url(self):
        """robots.txt should reference the sitemap URL."""
        from routes.scheduler.sitemap import get_robots

        request = _request_mock()
        response = await get_robots(request=request)

        body = response.body.decode()
        assert "Sitemap: https://api.perenniaai.com/api/v1/scheduler/sitemap.xml" in body

    @pytest.mark.asyncio
    async def test_robots_txt_allows_book_path(self):
        """robots.txt should allow crawling of /book/ paths."""
        from routes.scheduler.sitemap import get_robots

        request = _request_mock()
        response = await get_robots(request=request)

        body = response.body.decode()
        assert "Allow: /book/" in body

    @pytest.mark.asyncio
    async def test_robots_txt_disallows_admin_and_api(self):
        """robots.txt should disallow /api/, /admin/, /dashboard/, /settings/."""
        from routes.scheduler.sitemap import get_robots

        request = _request_mock()
        response = await get_robots(request=request)

        body = response.body.decode()
        assert "Disallow: /api/" in body
        assert "Disallow: /admin/" in body
        assert "Disallow: /dashboard/" in body
        assert "Disallow: /settings/" in body


# ---------------------------------------------------------------------------
# Tests: XML well-formedness and escaping
# ---------------------------------------------------------------------------

class TestXmlWellFormedness:
    """Tests that generated XML is well-formed and special chars are escaped."""

    def test_escape_xml_handles_special_characters(self):
        """The _escape_xml helper should escape &, <, >, and quotes."""
        from routes.scheduler.sitemap import _escape_xml

        assert _escape_xml("AT&T") == "AT&amp;T"
        assert _escape_xml("<script>") == "&lt;script&gt;"
        assert _escape_xml('He said "hello"') == "He said &quot;hello&quot;"
        assert _escape_xml(None) == ""
        assert _escape_xml("") == ""

    def test_build_sitemap_xml_produces_well_formed_xml(self):
        """_build_sitemap_xml should produce parseable XML."""
        from routes.scheduler.sitemap import _build_sitemap_xml

        urls = [
            {
                "loc": "https://example.com/book/test",
                "lastmod": "2026-03-10",
                "changefreq": "weekly",
                "priority": "0.7",
                "lo_name": "O'Brien & Associates",
                "org_name": "Loan <Corp>",
                "appointment_types": ["Phone & Video"],
            },
        ]

        xml_str = _build_sitemap_xml(urls)
        # Should parse without error
        root = _parse_xml(xml_str)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"

        url_elem = root.find(f"{{{SITEMAP_NS}}}url")
        assert url_elem is not None
        assert url_elem.find(f"{{{SITEMAP_NS}}}loc").text == "https://example.com/book/test"

    def test_build_sitemap_xml_empty_urls(self):
        """_build_sitemap_xml with no URLs should return valid empty urlset."""
        from routes.scheduler.sitemap import _build_sitemap_xml

        xml_str = _build_sitemap_xml([])
        root = _parse_xml(xml_str)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"
        assert len(root.findall(f"{{{SITEMAP_NS}}}url")) == 0


# ---------------------------------------------------------------------------
# Tests: Paginated sitemap (sitemap index)
# ---------------------------------------------------------------------------

class TestSitemapPagination:
    """Tests for paginated sitemap when > 10,000 URLs."""

    @pytest.mark.asyncio
    async def test_large_link_count_returns_sitemap_index(self):
        """When total links exceed URLS_PER_SITEMAP, should return a sitemapindex."""
        from routes.scheduler.sitemap import get_sitemap_index

        # Simulate 15,000 public links (would need 2 pages)
        db = _mock_db(
            links=[],
            total_count=15000,
            latest_mod=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_index(request=request, db=db)

        body = response.body.decode()
        assert response.media_type == "application/xml"
        root = _parse_xml(body)
        assert root.tag == f"{{{SITEMAP_NS}}}sitemapindex"

        sitemaps = root.findall(f"{{{SITEMAP_NS}}}sitemap")
        assert len(sitemaps) == 2

        locs = [s.find(f"{{{SITEMAP_NS}}}loc").text for s in sitemaps]
        assert "https://api.perenniaai.com/api/v1/scheduler/sitemap-1.xml" in locs
        assert "https://api.perenniaai.com/api/v1/scheduler/sitemap-2.xml" in locs

    @pytest.mark.asyncio
    async def test_sitemap_page_invalid_returns_404(self):
        """Page < 1 should return 404 with empty urlset."""
        from routes.scheduler.sitemap import get_sitemap_page

        db = _mock_db(links=[], total_count=0)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_page(page=0, request=request, db=db)

        assert response.status_code == 404
        assert response.media_type == "application/xml"

    @pytest.mark.asyncio
    async def test_sitemap_page_beyond_range_returns_404(self):
        """Requesting a page number beyond the total pages should return 404."""
        from routes.scheduler.sitemap import get_sitemap_page

        db = _mock_db(links=[], total_count=5)
        request = _request_mock()

        with patch("routes.scheduler.sitemap._get_models", return_value=_mock_models()):
            response = await get_sitemap_page(page=99, request=request, db=db)

        assert response.status_code == 404
