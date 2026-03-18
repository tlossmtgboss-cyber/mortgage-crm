"""
Tests for scheduler calendar feed routes.

Covers:
  - GET    /feed/{token}.ics       Public ICS feed (token-authenticated, no login)
  - POST   /feed/generate-token    Generate a unique feed URL token (auth required)
  - DELETE /feed/revoke            Revoke the active feed token (auth required)
  - GET    /feed/status            Check if a feed is active (auth required)

Edge cases: invalid/expired token, proper ICS content-type, token revocation,
no active feed status, and token replacement on re-generation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="loan_officer", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockFeedToken:
    """Mock CalendarFeedToken ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", 1)
        self.token = kwargs.get("token", "a" * 43)  # URL-safe base64, 43 chars
        self.is_active = kwargs.get("is_active", True)
        self.include_details = kwargs.get("include_details", True)
        self.access_count = kwargs.get("access_count", 0)
        self.last_accessed_at = kwargs.get("last_accessed_at", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


def _mock_db_query_chain(results=None, single=None):
    """Create a mock DB query chain."""
    query_mock = MagicMock()
    query_mock.filter = MagicMock(return_value=query_mock)
    query_mock.all = MagicMock(return_value=results if results is not None else [])
    query_mock.first = MagicMock(return_value=single)
    return query_mock


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Perennia AI//Calendar Feed//EN
BEGIN:VEVENT
DTSTART:20260318T100000Z
DTEND:20260318T103000Z
SUMMARY:Loan Review - John Smith
END:VEVENT
END:VCALENDAR"""


# ---------------------------------------------------------------------------
# Tests: GET /feed/{token}.ics (Public endpoint)
# ---------------------------------------------------------------------------

class TestGetIcsFeed:
    """Tests for GET /feed/{token}.ics."""

    @pytest.mark.asyncio
    async def test_short_token_returns_404(self):
        """Token shorter than 20 chars should return 404."""
        from routes.scheduler.calendar_feed import get_ics_feed

        with pytest.raises(HTTPException) as exc_info:
            await get_ics_feed("short", MagicMock(), MagicMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_token_returns_404(self):
        """Empty token should return 404."""
        from routes.scheduler.calendar_feed import get_ics_feed

        with pytest.raises(HTTPException) as exc_info:
            await get_ics_feed("", MagicMock(), MagicMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_token_returns_404(self):
        """Valid-length token that doesn't exist in DB should return 404."""
        from routes.scheduler.calendar_feed import get_ics_feed

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=None)
        db.query = MagicMock(return_value=query_mock)

        unknown_token = "x" * 43

        with pytest.raises(HTTPException) as exc_info:
            await get_ics_feed(unknown_token, MagicMock(), db)
        assert exc_info.value.status_code == 404
        assert "not found or revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_token_returns_ics_content(self):
        """Valid token should return ICS content with correct content type."""
        from routes.scheduler.calendar_feed import get_ics_feed

        feed_token = MockFeedToken(token="a" * 43, access_count=5)

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=feed_token)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.generate_ical_feed",
                   return_value=SAMPLE_ICS):
            response = await get_ics_feed("a" * 43, MagicMock(), db)

        # Response is a fastapi.responses.Response
        assert response.media_type == "text/calendar; charset=utf-8"
        assert b"BEGIN:VCALENDAR" in response.body
        assert b"VEVENT" in response.body

    @pytest.mark.asyncio
    async def test_valid_token_increments_access_count(self):
        """Accessing a valid feed should increment access_count."""
        from routes.scheduler.calendar_feed import get_ics_feed

        feed_token = MockFeedToken(token="b" * 43, access_count=3)

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=feed_token)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.generate_ical_feed",
                   return_value=SAMPLE_ICS):
            await get_ics_feed("b" * 43, MagicMock(), db)

        assert feed_token.access_count == 4
        assert feed_token.last_accessed_at is not None

    @pytest.mark.asyncio
    async def test_ics_generation_failure_returns_500(self):
        """If generate_ical_feed raises, endpoint should return 500."""
        from routes.scheduler.calendar_feed import get_ics_feed

        feed_token = MockFeedToken(token="c" * 43)

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=feed_token)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.generate_ical_feed",
                   side_effect=Exception("ICS generation error")):
            with pytest.raises(HTTPException) as exc_info:
                await get_ics_feed("c" * 43, MagicMock(), db)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Tests: POST /feed/generate-token
# ---------------------------------------------------------------------------

class TestGenerateFeedToken:
    """Tests for POST /feed/generate-token."""

    @pytest.mark.asyncio
    async def test_generate_token_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.calendar_feed import generate_feed_token

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await generate_feed_token(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_token_returns_feed_urls(self):
        """Generating a token should return feed_url, webcal_url, and token."""
        from routes.scheduler.calendar_feed import generate_feed_token

        user = MockUser()

        # Mock request with json body and headers
        request = MagicMock()
        request.json = AsyncMock(return_value={"include_details": True})
        request.url = MagicMock()
        request.url.scheme = "https"
        request.headers = {"host": "api.perenniaai.com"}

        db = MagicMock()
        # Return no existing tokens
        query_mock = _mock_db_query_chain(results=[])
        db.query = MagicMock(return_value=query_mock)

        new_token = MockFeedToken(id=5, include_details=True)
        db.flush = MagicMock()

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_feed._audit_log"), \
             patch("routes.scheduler.calendar_feed._get_api_base_url",
                   return_value="https://api.perenniaai.com"), \
             patch("database.models.calendar_feed.CalendarFeedToken",
                   return_value=new_token, create=True):
            result = await generate_feed_token(request, db)

        assert "token" in result
        assert "feed_url" in result
        assert "webcal_url" in result
        assert "instructions" in result
        assert result["include_details"] is True
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_token_revokes_existing(self):
        """Generating a new token should deactivate any existing active tokens."""
        from routes.scheduler.calendar_feed import generate_feed_token

        user = MockUser()
        old_token = MockFeedToken(id=1, is_active=True)

        request = MagicMock()
        request.json = AsyncMock(return_value={})
        request.headers = {"host": "api.perenniaai.com"}
        request.url = MagicMock()
        request.url.scheme = "https"

        db = MagicMock()
        query_mock = _mock_db_query_chain(results=[old_token])
        db.query = MagicMock(return_value=query_mock)

        new_token = MockFeedToken(id=5)
        db.flush = MagicMock()

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_feed._audit_log"), \
             patch("routes.scheduler.calendar_feed._get_api_base_url",
                   return_value="https://api.perenniaai.com"), \
             patch("database.models.calendar_feed.CalendarFeedToken",
                   return_value=new_token, create=True):
            await generate_feed_token(request, db)

        # Old token should have been deactivated
        assert old_token.is_active is False


# ---------------------------------------------------------------------------
# Tests: DELETE /feed/revoke
# ---------------------------------------------------------------------------

class TestRevokeFeedToken:
    """Tests for DELETE /feed/revoke."""

    @pytest.mark.asyncio
    async def test_revoke_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.calendar_feed import revoke_feed_token

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await revoke_feed_token(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_no_active_feed_returns_404(self):
        """Revoking when no active feed exists should return 404."""
        from routes.scheduler.calendar_feed import revoke_feed_token

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain(results=[])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await revoke_feed_token(MagicMock(), db)
            assert exc_info.value.status_code == 404
            assert "No active calendar feed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_revoke_deactivates_token(self):
        """Revoking should deactivate the token and return revoked_count."""
        from routes.scheduler.calendar_feed import revoke_feed_token

        user = MockUser()
        active_token = MockFeedToken(is_active=True)

        db = MagicMock()
        query_mock = _mock_db_query_chain(results=[active_token])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_feed._audit_log"):
            result = await revoke_feed_token(MagicMock(), db)

        assert result["success"] is True
        assert result["revoked_count"] == 1
        assert active_token.is_active is False
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: GET /feed/status
# ---------------------------------------------------------------------------

class TestGetFeedStatus:
    """Tests for GET /feed/status."""

    @pytest.mark.asyncio
    async def test_status_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.calendar_feed import get_feed_status

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await get_feed_status(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_status_no_active_feed(self):
        """No active feed should return is_active=False."""
        from routes.scheduler.calendar_feed import get_feed_status

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain(single=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await get_feed_status(MagicMock(), db)

        assert result["is_active"] is False
        assert result["feed_url"] is None
        assert result["access_count"] == 0

    @pytest.mark.asyncio
    async def test_status_active_feed(self):
        """Active feed should return is_active=True with URLs."""
        from routes.scheduler.calendar_feed import get_feed_status

        user = MockUser()
        feed_token = MockFeedToken(
            token="d" * 43,
            access_count=12,
            last_accessed_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        )

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=feed_token)
        db.query = MagicMock(return_value=query_mock)

        request = MagicMock()
        request.headers = {"host": "api.perenniaai.com"}
        request.url = MagicMock()
        request.url.scheme = "https"

        with patch("routes.scheduler.calendar_feed.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_feed._get_api_base_url",
                   return_value="https://api.perenniaai.com"):
            result = await get_feed_status(request, db)

        assert result["is_active"] is True
        assert result["feed_url"] is not None
        assert "/feed/" in result["feed_url"]
        assert ".ics" in result["feed_url"]
        assert result["webcal_url"] is not None
        assert result["webcal_url"].startswith("webcal://")
        assert result["access_count"] == 12
        assert result["include_details"] is True


# ---------------------------------------------------------------------------
# Tests: _get_api_base_url helper
# ---------------------------------------------------------------------------

class TestGetApiBaseUrl:
    """Tests for the _get_api_base_url helper."""

    def test_uses_env_domain_when_set(self):
        """Should prefer API_DOMAIN env var."""
        from routes.scheduler.calendar_feed import _get_api_base_url

        request = MagicMock()

        with patch.dict("os.environ", {"API_DOMAIN": "api.perenniaai.com"}):
            result = _get_api_base_url(request)

        assert result == "https://api.perenniaai.com"

    def test_falls_back_to_request_host(self):
        """Should use request host when API_DOMAIN is not set."""
        from routes.scheduler.calendar_feed import _get_api_base_url

        request = MagicMock()
        request.headers = {
            "x-forwarded-proto": "https",
            "host": "localhost:8000",
        }
        request.url = MagicMock()
        request.url.scheme = "http"

        with patch.dict("os.environ", {}, clear=False):
            # Ensure API_DOMAIN is empty
            import os
            original = os.environ.pop("API_DOMAIN", None)
            try:
                result = _get_api_base_url(request)
            finally:
                if original is not None:
                    os.environ["API_DOMAIN"] = original

        assert "localhost" in result
