"""
Virtual Meeting Integration Test Suite

Tests for:
  - MeetingProvider abstract interface
  - ZoomMeetingProvider (create, update, delete, get_join_url, test_connection)
  - GoogleMeetProvider (create, update, delete, get_join_url, test_connection)
  - TeamsMeetingProvider (create, update, delete, get_join_url, test_connection)
  - PerenniaMeetProvider (create, update, delete, get_join_url, test_connection)
  - MeetingProviderFactory (get_provider, auto-detection, validation)
  - create_meeting_for_appointment convenience function
  - Route endpoints (create, delete, get, test-connection)
  - MeetingDetails and MeetingResult data classes
  - Provider detection from URLs
  - Meeting ID extraction
  - Fallback behavior (primary fails -> Perennia)
  - Error handling and edge cases
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, AsyncMock, patch, PropertyMock
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def mock_db_with_zoom_token(mock_db):
    """DB session that returns a Zoom token when queried."""
    result = MagicMock()
    row = ("fake_access_token", "fake_refresh_token", datetime.utcnow() + timedelta(hours=1))
    result.fetchone.return_value = row
    mock_db.execute.return_value = result
    return mock_db


@pytest.fixture
def mock_db_with_google_token(mock_db):
    """DB session that returns a Google token when queried."""
    result = MagicMock()
    row = ("google_access_token", "google_refresh_token", datetime.utcnow() + timedelta(hours=1))
    result.fetchone.return_value = row
    mock_db.execute.return_value = result
    return mock_db


@pytest.fixture
def mock_db_with_microsoft_token(mock_db):
    """DB session that returns a Microsoft token when queried."""
    result = MagicMock()
    row = ("ms_access_token", "ms_refresh_token", datetime.utcnow() + timedelta(hours=1))
    result.fetchone.return_value = row
    mock_db.execute.return_value = result
    return mock_db


@pytest.fixture
def mock_db_no_token(mock_db):
    """DB session that returns no token."""
    result = MagicMock()
    result.fetchone.return_value = None
    result.fetchall.return_value = []
    mock_db.execute.return_value = result
    return mock_db


@pytest.fixture
def sample_meeting_details():
    """Sample MeetingDetails for tests."""
    from services.virtual_meeting_service import MeetingDetails
    return MeetingDetails(
        title="Rate Lock Discussion",
        scheduled_start=datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
        scheduled_end=datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
        duration_minutes=30,
        description="Discuss rate lock options for the Johnson loan",
        timezone="America/Chicago",
        attendee_emails=["borrower@example.com"],
        attendee_name="John Johnson",
        appointment_id=42,
        organization_id=1,
    )


@pytest.fixture
def mock_appointment():
    """Mock Appointment ORM object."""
    appt = MagicMock()
    appt.id = 42
    appt.title = "Rate Lock Discussion"
    appt.description = "Discuss rate lock options"
    appt.scheduled_start = datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc)
    appt.scheduled_end = datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    appt.duration_minutes = 30
    appt.timezone = "America/Chicago"
    appt.attendee_email = "borrower@example.com"
    appt.attendee_name = "John Johnson"
    appt.assigned_user_id = 1
    appt.organization_id = 1
    appt.video_link = None
    appt.dial_in_info = None
    appt.google_calendar_event_id = None
    appt.outlook_event_id = None
    return appt


# =============================================================================
# MEETINGDETAILS DATA CLASS TESTS
# =============================================================================

class TestMeetingDetails:
    """Tests for the MeetingDetails data class."""

    def test_meeting_details_defaults(self):
        from services.virtual_meeting_service import MeetingDetails
        details = MeetingDetails(
            title="Test",
            scheduled_start=datetime(2026, 3, 15, 10, 0),
            scheduled_end=datetime(2026, 3, 15, 10, 30),
        )
        assert details.duration_minutes == 30
        assert details.timezone == "America/Chicago"
        assert details.attendee_emails == []
        assert details.appointment_id is None

    def test_meeting_details_all_fields(self, sample_meeting_details):
        assert sample_meeting_details.title == "Rate Lock Discussion"
        assert sample_meeting_details.duration_minutes == 30
        assert len(sample_meeting_details.attendee_emails) == 1
        assert sample_meeting_details.appointment_id == 42


class TestMeetingResult:
    """Tests for the MeetingResult data class."""

    def test_meeting_result_success(self):
        from services.virtual_meeting_service import MeetingResult
        result = MeetingResult(
            success=True,
            provider="zoom",
            join_url="https://zoom.us/j/123",
            meeting_id="123",
            passcode="abc",
        )
        assert result.success is True
        assert result.provider == "zoom"
        assert result.join_url == "https://zoom.us/j/123"

    def test_meeting_result_failure(self):
        from services.virtual_meeting_service import MeetingResult
        result = MeetingResult.failure("zoom", "Connection refused")
        assert result.success is False
        assert result.error == "Connection refused"
        assert result.provider == "zoom"

    def test_meeting_result_to_dict(self):
        from services.virtual_meeting_service import MeetingResult
        result = MeetingResult(
            success=True,
            provider="google_meet",
            join_url="https://meet.google.com/abc-def",
            meeting_id="abc-def",
            dial_in_numbers=[{"number": "+15551234567", "country": "US"}],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["provider"] == "google_meet"
        assert d["join_url"] == "https://meet.google.com/abc-def"
        assert len(d["dial_in_numbers"]) == 1

    def test_meeting_result_defaults(self):
        from services.virtual_meeting_service import MeetingResult
        result = MeetingResult(success=True, provider="perennia")
        assert result.join_url == ""
        assert result.host_url == ""
        assert result.meeting_id == ""
        assert result.passcode == ""
        assert result.dial_in_numbers == []
        assert result.metadata == {}


# =============================================================================
# PERENNIA MEET PROVIDER TESTS
# =============================================================================

class TestPerenniaMeetProvider:
    """Tests for the self-hosted Perennia Meet provider."""

    @pytest.mark.asyncio
    async def test_create_meeting(self, mock_db, sample_meeting_details):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result = await provider.create_meeting(sample_meeting_details)

        assert result.success is True
        assert result.provider == "perennia"
        assert "/meet/" in result.join_url
        assert result.meeting_id != ""
        assert "-" in result.meeting_id  # Room ID format: xxxx-xxxx-xxxx

    @pytest.mark.asyncio
    async def test_create_meeting_deterministic(self, mock_db, sample_meeting_details):
        """Same inputs should produce the same room ID."""
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result1 = await provider.create_meeting(sample_meeting_details)
        result2 = await provider.create_meeting(sample_meeting_details)
        assert result1.meeting_id == result2.meeting_id

    @pytest.mark.asyncio
    async def test_update_meeting_noop(self, mock_db, sample_meeting_details):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result = await provider.update_meeting("room-1234", sample_meeting_details)
        assert result.success is True
        assert result.metadata.get("note") == "Perennia Meet rooms are stateless"

    @pytest.mark.asyncio
    async def test_delete_meeting_noop(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result = await provider.delete_meeting("room-1234")
        assert result.success is True
        assert result.metadata.get("note") == "Perennia Meet rooms are ephemeral"

    @pytest.mark.asyncio
    async def test_get_join_url(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        url = await provider.get_join_url("abcd-efgh-ijkl")
        assert url is not None
        assert "/meet/abcd-efgh-ijkl" in url

    @pytest.mark.asyncio
    async def test_test_connection(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result = await provider.test_connection()
        assert result.success is True
        assert result.metadata.get("status") == "always_available"


# =============================================================================
# ZOOM PROVIDER TESTS
# =============================================================================

class TestZoomMeetingProvider:
    """Tests for the Zoom meeting provider."""

    @pytest.mark.asyncio
    async def test_create_meeting_no_token(self, mock_db_no_token, sample_meeting_details):
        from services.virtual_meeting_service import ZoomMeetingProvider
        provider = ZoomMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.create_meeting(sample_meeting_details)
        assert result.success is False
        assert "No Zoom OAuth connection" in result.error

    @pytest.mark.asyncio
    async def test_create_meeting_no_user_id(self, mock_db, sample_meeting_details):
        from services.virtual_meeting_service import ZoomMeetingProvider
        provider = ZoomMeetingProvider(db=mock_db, user_id=None, org_id=1)
        result = await provider.create_meeting(sample_meeting_details)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_create_meeting_success(self, mock_db_with_zoom_token, sample_meeting_details):
        from services.virtual_meeting_service import ZoomMeetingProvider

        mock_zoom_client = MagicMock()
        mock_zoom_client.enabled = True
        mock_zoom_client.async_create_meeting = AsyncMock(return_value={
            "id": 12345678,
            "join_url": "https://zoom.us/j/12345678",
            "start_url": "https://zoom.us/s/12345678",
            "password": "abc123",
            "host_id": "host_123",
            "uuid": "uuid_abc",
            "settings": {
                "global_dial_in_numbers": [
                    {"number": "+15551234567", "country": "US", "country_name": "United States"},
                ]
            },
        })

        with patch.dict("sys.modules", {"integrations.zoom_service": MagicMock(zoom_client=mock_zoom_client)}):
            provider = ZoomMeetingProvider(db=mock_db_with_zoom_token, user_id=1, org_id=1)
            result = await provider.create_meeting(sample_meeting_details)

        assert result.success is True
        assert result.provider == "zoom"
        assert result.join_url == "https://zoom.us/j/12345678"
        assert result.passcode == "abc123"
        assert result.meeting_id == "12345678"
        assert len(result.dial_in_numbers) == 1
        assert result.dial_in_numbers[0]["country"] == "US"

    @pytest.mark.asyncio
    async def test_create_meeting_zoom_not_enabled(self, mock_db_with_zoom_token, sample_meeting_details):
        from services.virtual_meeting_service import ZoomMeetingProvider

        mock_zoom_client = MagicMock()
        mock_zoom_client.enabled = False

        with patch.dict("sys.modules", {"integrations.zoom_service": MagicMock(zoom_client=mock_zoom_client)}):
            provider = ZoomMeetingProvider(db=mock_db_with_zoom_token, user_id=1, org_id=1)
            result = await provider.create_meeting(sample_meeting_details)

        assert result.success is False
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_delete_meeting_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import ZoomMeetingProvider
        provider = ZoomMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.delete_meeting("12345678")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_connection_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import ZoomMeetingProvider
        provider = ZoomMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.test_connection()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_join_url_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import ZoomMeetingProvider
        provider = ZoomMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        url = await provider.get_join_url("12345678")
        assert url is None


# =============================================================================
# GOOGLE MEET PROVIDER TESTS
# =============================================================================

class TestGoogleMeetProvider:
    """Tests for the Google Meet provider."""

    @pytest.mark.asyncio
    async def test_create_meeting_no_token(self, mock_db_no_token, sample_meeting_details):
        from services.virtual_meeting_service import GoogleMeetProvider
        provider = GoogleMeetProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.create_meeting(sample_meeting_details)
        assert result.success is False
        assert "No Google OAuth connection" in result.error

    @pytest.mark.asyncio
    async def test_create_meeting_success(self, mock_db_with_google_token, sample_meeting_details):
        from services.virtual_meeting_service import GoogleMeetProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "event_abc123",
            "htmlLink": "https://calendar.google.com/event/abc123",
            "conferenceData": {
                "conferenceId": "abc-defg-hij",
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"},
                    {"entryPointType": "phone", "uri": "tel:+15551234567", "regionCode": "US", "pin": "1234"},
                ],
            },
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.virtual_meeting_service.GoogleMeetProvider._get_user_token") as mock_token:
            mock_token.return_value = {
                "access_token": "google_token",
                "refresh_token": "google_refresh",
                "expires_at": datetime.utcnow() + timedelta(hours=1),
            }
            with patch("httpx.AsyncClient", return_value=mock_client):
                provider = GoogleMeetProvider(db=mock_db_with_google_token, user_id=1, org_id=1)
                result = await provider.create_meeting(sample_meeting_details)

        assert result.success is True
        assert result.provider == "google_meet"
        assert result.join_url == "https://meet.google.com/abc-defg-hij"
        assert result.meeting_id == "abc-defg-hij"
        assert len(result.dial_in_numbers) == 1

    @pytest.mark.asyncio
    async def test_delete_meeting_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import GoogleMeetProvider
        provider = GoogleMeetProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.delete_meeting("event_abc")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_connection_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import GoogleMeetProvider
        provider = GoogleMeetProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.test_connection()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_join_url_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import GoogleMeetProvider
        provider = GoogleMeetProvider(db=mock_db_no_token, user_id=1, org_id=1)
        url = await provider.get_join_url("event_abc")
        assert url is None

    @pytest.mark.asyncio
    async def test_update_meeting_no_token(self, mock_db_no_token, sample_meeting_details):
        from services.virtual_meeting_service import GoogleMeetProvider
        provider = GoogleMeetProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.update_meeting("event_abc", sample_meeting_details)
        assert result.success is False


# =============================================================================
# TEAMS PROVIDER TESTS
# =============================================================================

class TestTeamsMeetingProvider:
    """Tests for the Microsoft Teams provider."""

    @pytest.mark.asyncio
    async def test_create_meeting_success(self, mock_db_with_microsoft_token, sample_meeting_details):
        from services.virtual_meeting_service import TeamsMeetingProvider

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.join_url = "https://teams.microsoft.com/l/meetup-join/abc123"
        mock_result.event_id = "event_ms_123"

        with patch("services.virtual_meeting_service.create_event_via_graph", new_callable=AsyncMock, return_value=mock_result):
            provider = TeamsMeetingProvider(db=mock_db_with_microsoft_token, user_id=1, org_id=1)
            result = await provider.create_meeting(sample_meeting_details)

        assert result.success is True
        assert result.provider == "teams"
        assert "teams.microsoft.com" in result.join_url

    @pytest.mark.asyncio
    async def test_create_meeting_import_error(self, mock_db_with_microsoft_token, sample_meeting_details):
        from services.virtual_meeting_service import TeamsMeetingProvider

        with patch.dict("sys.modules", {"services.microsoft_graph": None}):
            with patch("services.virtual_meeting_service.create_event_via_graph", side_effect=ImportError("no module")):
                provider = TeamsMeetingProvider(db=mock_db_with_microsoft_token, user_id=1, org_id=1)
                result = await provider.create_meeting(sample_meeting_details)

        assert result.success is False
        assert "not available" in result.error or "no module" in result.error

    @pytest.mark.asyncio
    async def test_delete_meeting_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import TeamsMeetingProvider
        provider = TeamsMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.delete_meeting("event_ms_123")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_connection_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import TeamsMeetingProvider
        provider = TeamsMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.test_connection()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_join_url_no_token(self, mock_db_no_token):
        from services.virtual_meeting_service import TeamsMeetingProvider
        provider = TeamsMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        url = await provider.get_join_url("event_ms_123")
        assert url is None

    @pytest.mark.asyncio
    async def test_update_meeting_no_token(self, mock_db_no_token, sample_meeting_details):
        from services.virtual_meeting_service import TeamsMeetingProvider
        provider = TeamsMeetingProvider(db=mock_db_no_token, user_id=1, org_id=1)
        result = await provider.update_meeting("event_ms_123", sample_meeting_details)
        assert result.success is False


# =============================================================================
# PROVIDER FACTORY TESTS
# =============================================================================

class TestMeetingProviderFactory:
    """Tests for the MeetingProviderFactory."""

    def test_get_zoom_provider(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, ZoomMeetingProvider
        provider = MeetingProviderFactory.get_provider("zoom", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, ZoomMeetingProvider)

    def test_get_google_meet_provider(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, GoogleMeetProvider
        provider = MeetingProviderFactory.get_provider("google_meet", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, GoogleMeetProvider)

    def test_get_teams_provider(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, TeamsMeetingProvider
        provider = MeetingProviderFactory.get_provider("teams", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, TeamsMeetingProvider)

    def test_get_perennia_provider(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, PerenniaMeetProvider
        provider = MeetingProviderFactory.get_provider("perennia", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, PerenniaMeetProvider)

    def test_invalid_provider_raises(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory
        with pytest.raises(ValueError, match="Unknown meeting provider"):
            MeetingProviderFactory.get_provider("webex", mock_db, user_id=1, org_id=1)

    def test_auto_detection_no_user(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, PerenniaMeetProvider
        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=None, org_id=1)
        assert isinstance(provider, PerenniaMeetProvider)

    def test_auto_detection_no_integrations(self, mock_db_no_token):
        from services.virtual_meeting_service import MeetingProviderFactory, PerenniaMeetProvider
        provider = MeetingProviderFactory.get_provider("auto", mock_db_no_token, user_id=1, org_id=1)
        assert isinstance(provider, PerenniaMeetProvider)

    def test_auto_detection_zoom_available(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, ZoomMeetingProvider

        result = MagicMock()
        result.fetchall.return_value = [("zoom",)]
        mock_db.execute.return_value = result

        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, ZoomMeetingProvider)

    def test_auto_detection_google_available(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, GoogleMeetProvider

        result = MagicMock()
        result.fetchall.return_value = [("google",)]
        mock_db.execute.return_value = result

        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, GoogleMeetProvider)

    def test_auto_detection_microsoft_available(self, mock_db):
        from services.virtual_meeting_service import MeetingProviderFactory, TeamsMeetingProvider

        result = MagicMock()
        result.fetchall.return_value = [("microsoft",)]
        mock_db.execute.return_value = result

        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, TeamsMeetingProvider)

    def test_auto_detection_priority_order(self, mock_db):
        """Zoom should be preferred over Google and Teams."""
        from services.virtual_meeting_service import MeetingProviderFactory, ZoomMeetingProvider

        result = MagicMock()
        result.fetchall.return_value = [("zoom",), ("google",), ("microsoft",)]
        mock_db.execute.return_value = result

        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, ZoomMeetingProvider)

    def test_get_available_providers(self):
        from services.virtual_meeting_service import MeetingProviderFactory
        providers = MeetingProviderFactory.get_available_providers()
        assert "zoom" in providers
        assert "google_meet" in providers
        assert "teams" in providers
        assert "perennia" in providers
        assert len(providers) == 4

    def test_auto_detection_db_error_fallback(self, mock_db):
        """DB error during auto-detection should fall back to Perennia."""
        from services.virtual_meeting_service import MeetingProviderFactory, PerenniaMeetProvider

        mock_db.execute.side_effect = Exception("DB connection lost")
        provider = MeetingProviderFactory.get_provider("auto", mock_db, user_id=1, org_id=1)
        assert isinstance(provider, PerenniaMeetProvider)


# =============================================================================
# CREATE MEETING FOR APPOINTMENT (CONVENIENCE FUNCTION) TESTS
# =============================================================================

class TestCreateMeetingForAppointment:
    """Tests for the create_meeting_for_appointment convenience function."""

    @pytest.mark.asyncio
    async def test_creates_perennia_meet_as_fallback(self, mock_db_no_token, mock_appointment):
        from services.virtual_meeting_service import create_meeting_for_appointment
        result = await create_meeting_for_appointment(
            db=mock_db_no_token, appointment=mock_appointment, provider="auto",
        )
        assert result.success is True
        assert result.provider == "perennia"
        assert mock_appointment.video_link is not None
        assert "/meet/" in mock_appointment.video_link

    @pytest.mark.asyncio
    async def test_attaches_video_link_to_appointment(self, mock_db_no_token, mock_appointment):
        from services.virtual_meeting_service import create_meeting_for_appointment
        assert mock_appointment.video_link is None

        result = await create_meeting_for_appointment(
            db=mock_db_no_token, appointment=mock_appointment, provider="perennia",
        )
        assert result.success is True
        assert mock_appointment.video_link is not None

    @pytest.mark.asyncio
    async def test_explicit_perennia_provider(self, mock_db, mock_appointment):
        from services.virtual_meeting_service import create_meeting_for_appointment
        result = await create_meeting_for_appointment(
            db=mock_db, appointment=mock_appointment, provider="perennia",
        )
        assert result.success is True
        assert result.provider == "perennia"
        assert "/meet/" in result.join_url

    @pytest.mark.asyncio
    async def test_uses_appointment_fields(self, mock_db, mock_appointment):
        from services.virtual_meeting_service import create_meeting_for_appointment
        mock_appointment.title = "Custom Title"
        mock_appointment.timezone = "America/New_York"

        result = await create_meeting_for_appointment(
            db=mock_db, appointment=mock_appointment, provider="perennia",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, mock_db, mock_appointment):
        """If primary provider fails, should fall back to Perennia Meet."""
        from services.virtual_meeting_service import create_meeting_for_appointment, ZoomMeetingProvider, MeetingResult

        with patch.object(ZoomMeetingProvider, "create_meeting", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MeetingResult.failure("zoom", "API error")

            # Mock the factory to return a Zoom provider
            with patch("services.virtual_meeting_service.MeetingProviderFactory.get_provider") as mock_factory:
                mock_factory.return_value = ZoomMeetingProvider(db=mock_db, user_id=1, org_id=1)

                result = await create_meeting_for_appointment(
                    db=mock_db, appointment=mock_appointment, provider="zoom",
                )

        assert result.success is True
        assert result.provider == "perennia"

    @pytest.mark.asyncio
    async def test_no_fallback_when_perennia_requested(self, mock_db, mock_appointment):
        """If perennia is explicitly requested and succeeds, no fallback logic needed."""
        from services.virtual_meeting_service import create_meeting_for_appointment
        result = await create_meeting_for_appointment(
            db=mock_db, appointment=mock_appointment, provider="perennia",
        )
        assert result.success is True
        assert result.provider == "perennia"

    @pytest.mark.asyncio
    async def test_dial_in_attached(self, mock_db, mock_appointment):
        """Dial-in info from provider should be attached to appointment."""
        from services.virtual_meeting_service import (
            create_meeting_for_appointment, MeetingProviderFactory, PerenniaMeetProvider, MeetingResult,
        )

        # Create a mock provider that returns dial-in info
        class MockProvider(PerenniaMeetProvider):
            async def create_meeting(self, details):
                return MeetingResult(
                    success=True,
                    provider="mock",
                    join_url="https://example.com/join",
                    meeting_id="mock-123",
                    passcode="secret",
                    dial_in_numbers=[{"number": "+15551234567", "country": "US"}],
                )

        with patch.object(MeetingProviderFactory, "get_provider", return_value=MockProvider(db=mock_db)):
            result = await create_meeting_for_appointment(
                db=mock_db, appointment=mock_appointment, provider="perennia",
            )

        assert result.success is True
        assert mock_appointment.video_link == "https://example.com/join"
        assert "Dial-in: +15551234567" in mock_appointment.dial_in_info
        assert "Passcode: secret" in mock_appointment.dial_in_info


# =============================================================================
# ROUTE HELPER TESTS
# =============================================================================

class TestRouteHelpers:
    """Tests for route-level helper functions."""

    def test_detect_provider_from_zoom_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("https://zoom.us/j/12345678") == "zoom"
        assert _detect_provider_from_url("https://us02web.zoom.us/j/12345678") == "zoom"

    def test_detect_provider_from_google_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("https://meet.google.com/abc-defg-hij") == "google_meet"

    def test_detect_provider_from_teams_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("https://teams.microsoft.com/l/meetup-join/abc") == "teams"

    def test_detect_provider_from_perennia_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("https://app.perenniaai.com/meet/abcd-efgh") == "perennia"

    def test_detect_provider_from_empty_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("") == "unknown"
        assert _detect_provider_from_url(None) == "unknown"

    def test_detect_provider_from_unknown_url(self):
        from routes.scheduler.meetings import _detect_provider_from_url
        assert _detect_provider_from_url("https://example.com/meeting") == "unknown"

    def test_extract_meeting_id_from_zoom_url(self):
        from routes.scheduler.meetings import _extract_meeting_id
        appt = MagicMock()
        appt.video_link = "https://zoom.us/j/12345678"
        appt.google_calendar_event_id = None
        appt.outlook_event_id = None
        meeting_id = _extract_meeting_id(appt)
        assert meeting_id == "12345678"

    def test_extract_meeting_id_from_google_event(self):
        from routes.scheduler.meetings import _extract_meeting_id
        appt = MagicMock()
        appt.video_link = "https://meet.google.com/abc-defg"
        appt.google_calendar_event_id = "event_google_123"
        appt.outlook_event_id = None
        meeting_id = _extract_meeting_id(appt)
        assert meeting_id == "event_google_123"

    def test_extract_meeting_id_from_outlook_event(self):
        from routes.scheduler.meetings import _extract_meeting_id
        appt = MagicMock()
        appt.video_link = "https://teams.microsoft.com/join/abc"
        appt.google_calendar_event_id = None
        appt.outlook_event_id = "event_outlook_456"
        meeting_id = _extract_meeting_id(appt)
        assert meeting_id == "event_outlook_456"

    def test_extract_meeting_id_from_perennia_url(self):
        from routes.scheduler.meetings import _extract_meeting_id
        appt = MagicMock()
        appt.video_link = "https://app.perenniaai.com/meet/abcd-efgh-ijkl"
        appt.google_calendar_event_id = None
        appt.outlook_event_id = None
        meeting_id = _extract_meeting_id(appt)
        assert meeting_id == "abcd-efgh-ijkl"


# =============================================================================
# MEETING PROVIDER TYPE ENUM TESTS
# =============================================================================

class TestMeetingProviderType:
    """Tests for the MeetingProviderType enum."""

    def test_enum_values(self):
        from services.virtual_meeting_service import MeetingProviderType
        assert MeetingProviderType.ZOOM == "zoom"
        assert MeetingProviderType.GOOGLE_MEET == "google_meet"
        assert MeetingProviderType.TEAMS == "teams"
        assert MeetingProviderType.PERENNIA == "perennia"

    def test_enum_membership(self):
        from services.virtual_meeting_service import MeetingProviderType
        assert "zoom" in [e.value for e in MeetingProviderType]
        assert "google_meet" in [e.value for e in MeetingProviderType]


# =============================================================================
# PROVIDER BASE CLASS TESTS
# =============================================================================

class TestMeetingProviderBase:
    """Tests for the abstract MeetingProvider base class."""

    def test_get_user_token_no_user(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider
        provider = PerenniaMeetProvider(db=mock_db, user_id=None, org_id=1)
        token = provider._get_user_token("zoom")
        assert token is None

    def test_get_user_token_found(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider

        result = MagicMock()
        result.fetchone.return_value = ("access", "refresh", datetime.utcnow())
        mock_db.execute.return_value = result

        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        token = provider._get_user_token("zoom")
        assert token is not None
        assert token["access_token"] == "access"
        assert token["refresh_token"] == "refresh"

    def test_get_user_token_not_found(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider

        result = MagicMock()
        result.fetchone.return_value = None
        mock_db.execute.return_value = result

        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        token = provider._get_user_token("zoom")
        assert token is None

    def test_get_user_token_db_error(self, mock_db):
        from services.virtual_meeting_service import PerenniaMeetProvider

        mock_db.execute.side_effect = Exception("Connection lost")
        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        token = provider._get_user_token("zoom")
        assert token is None


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_appointment_with_no_title(self, mock_db):
        """Appointment with None title should use default."""
        from services.virtual_meeting_service import create_meeting_for_appointment

        appt = MagicMock()
        appt.id = 99
        appt.title = None
        appt.description = None
        appt.scheduled_start = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        appt.scheduled_end = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        appt.duration_minutes = 30
        appt.timezone = None
        appt.attendee_email = None
        appt.attendee_name = None
        appt.assigned_user_id = None
        appt.organization_id = 1
        appt.video_link = None
        appt.dial_in_info = None

        result = await create_meeting_for_appointment(db=mock_db, appointment=appt, provider="perennia")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_appointment_with_existing_video_link(self, mock_db, mock_appointment):
        """Creating meeting should overwrite existing video_link."""
        from services.virtual_meeting_service import create_meeting_for_appointment

        mock_appointment.video_link = "https://old-link.com/meeting"
        result = await create_meeting_for_appointment(
            db=mock_db, appointment=mock_appointment, provider="perennia",
        )
        assert result.success is True
        assert mock_appointment.video_link != "https://old-link.com/meeting"

    def test_factory_provider_names_are_consistent(self):
        """Available providers should match the factory's internal registry."""
        from services.virtual_meeting_service import MeetingProviderFactory
        providers = MeetingProviderFactory.get_available_providers()
        for provider_name in providers:
            # Should not raise
            MeetingProviderFactory.get_provider(provider_name, MagicMock())

    @pytest.mark.asyncio
    async def test_perennia_room_id_format(self, mock_db, sample_meeting_details):
        """Room ID should be in xxxx-xxxx-xxxx format."""
        from services.virtual_meeting_service import PerenniaMeetProvider
        import re

        provider = PerenniaMeetProvider(db=mock_db, user_id=1, org_id=1)
        result = await provider.create_meeting(sample_meeting_details)

        assert re.match(r"^[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}$", result.meeting_id)
