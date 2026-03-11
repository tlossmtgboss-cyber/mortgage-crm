"""
Tests for the Calendar Provider abstraction layer.

Covers:
- CalendarProviderRegistry (register, get, unregister, clear)
- CalendarProvider interface contract enforcement
- ExternalCalendarEvent, BusyBlock, ProviderSyncResult data classes
- GoogleCalendarProvider method delegation (mocked)
- OutlookCalendarProvider method delegation (mocked)
- CalendarSyncOrchestrator sync/delete/busy-times logic (mocked providers)
- CalendarEventMap model attributes
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Base data classes
# ---------------------------------------------------------------------------
from services.calendar_providers.base import (
    BusyBlock,
    CalendarProvider,
    ExternalCalendarEvent,
    ProviderSyncResult,
    SyncDirection,
    SyncStatus,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from services.calendar_providers import CalendarProviderRegistry


# ===========================================================================
# Helpers
# ===========================================================================

class _DummyProvider(CalendarProvider):
    """Minimal concrete provider for testing."""

    def __init__(self, name: str = "dummy"):
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name

    async def create_event(self, appointment, credentials):
        return ProviderSyncResult(
            provider=self._name,
            status=SyncStatus.SUCCESS,
            external_id="ext-123",
            link="https://example.com/event/ext-123",
        )

    async def update_event(self, external_id, appointment, credentials):
        return ProviderSyncResult(
            provider=self._name,
            status=SyncStatus.SUCCESS,
            external_id=external_id,
        )

    async def delete_event(self, external_id, credentials):
        return ProviderSyncResult(
            provider=self._name,
            status=SyncStatus.SUCCESS,
            external_id=external_id,
        )

    async def get_busy_times(self, credentials, start, end):
        return [
            BusyBlock(
                start=start,
                end=start + timedelta(hours=1),
                provider=self._name,
                title="Busy",
            )
        ]

    async def test_connection(self, credentials):
        return True


class _FailingProvider(CalendarProvider):
    """Provider that always fails."""

    @property
    def provider_name(self) -> str:
        return "failing"

    async def create_event(self, appointment, credentials):
        return ProviderSyncResult(
            provider=self.provider_name,
            status=SyncStatus.FAILED,
            error="Simulated failure",
        )

    async def update_event(self, external_id, appointment, credentials):
        return ProviderSyncResult(
            provider=self.provider_name,
            status=SyncStatus.FAILED,
            error="Simulated failure",
        )

    async def delete_event(self, external_id, credentials):
        return ProviderSyncResult(
            provider=self.provider_name,
            status=SyncStatus.FAILED,
            error="Simulated failure",
        )

    async def get_busy_times(self, credentials, start, end):
        return []

    async def test_connection(self, credentials):
        return False


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry is clean before and after each test."""
    CalendarProviderRegistry.clear()
    yield
    CalendarProviderRegistry.clear()


@pytest.fixture
def dummy_provider():
    return _DummyProvider()


@pytest.fixture
def failing_provider():
    return _FailingProvider()


@pytest.fixture
def sample_appointment():
    """Dict-based appointment for tests that don't need ORM."""
    return {
        "id": 42,
        "organization_id": 1,
        "title": "Discovery Call - John Doe",
        "scheduled_start": datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
        "scheduled_end": datetime(2026, 3, 15, 14, 30, tzinfo=timezone.utc),
        "description": "Initial consultation",
        "location": "Video Call",
        "attendee_email": "john@example.com",
        "video_link": "https://meet.example.com/abc",
    }


@pytest.fixture
def sample_credentials():
    return {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }


# ===========================================================================
# ExternalCalendarEvent tests
# ===========================================================================

class TestExternalCalendarEvent:
    def test_to_dict(self):
        event = ExternalCalendarEvent(
            external_id="ext-1",
            provider="google",
            title="Meeting",
            start=datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 15, 14, 30, tzinfo=timezone.utc),
            location="Office",
            attendees=["a@b.com"],
            link="https://calendar.google.com/event/ext-1",
        )
        d = event.to_dict()
        assert d["external_id"] == "ext-1"
        assert d["provider"] == "google"
        assert d["title"] == "Meeting"
        assert d["location"] == "Office"
        assert d["attendees"] == ["a@b.com"]
        assert "2026-03-15" in d["start"]

    def test_defaults(self):
        event = ExternalCalendarEvent(
            external_id="ext-2",
            provider="outlook",
            title="Call",
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        )
        assert event.attendees == []
        assert event.location is None
        assert event.link is None
        assert event.is_all_day is False


# ===========================================================================
# ProviderSyncResult tests
# ===========================================================================

class TestProviderSyncResult:
    def test_success_property(self):
        r = ProviderSyncResult(provider="google", status=SyncStatus.SUCCESS, external_id="e1")
        assert r.success is True

    def test_failure_property(self):
        r = ProviderSyncResult(provider="outlook", status=SyncStatus.FAILED, error="timeout")
        assert r.success is False
        assert r.error == "timeout"


# ===========================================================================
# BusyBlock tests
# ===========================================================================

class TestBusyBlock:
    def test_construction(self):
        start = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        block = BusyBlock(start=start, end=end, provider="google", title="Meeting")
        assert block.start == start
        assert block.end == end
        assert block.provider == "google"
        assert block.is_all_day is False


# ===========================================================================
# CalendarProviderRegistry tests
# ===========================================================================

class TestCalendarProviderRegistry:
    def test_register_and_get(self, dummy_provider):
        CalendarProviderRegistry.register(dummy_provider)
        assert CalendarProviderRegistry.get("dummy") is dummy_provider
        assert CalendarProviderRegistry.is_registered("dummy")
        assert CalendarProviderRegistry.count() == 1

    def test_get_nonexistent_returns_none(self):
        assert CalendarProviderRegistry.get("nonexistent") is None

    def test_unregister(self, dummy_provider):
        CalendarProviderRegistry.register(dummy_provider)
        assert CalendarProviderRegistry.unregister("dummy") is True
        assert CalendarProviderRegistry.get("dummy") is None
        assert CalendarProviderRegistry.count() == 0

    def test_unregister_nonexistent(self):
        assert CalendarProviderRegistry.unregister("nope") is False

    def test_get_all(self, dummy_provider, failing_provider):
        CalendarProviderRegistry.register(dummy_provider)
        CalendarProviderRegistry.register(failing_provider)
        all_providers = CalendarProviderRegistry.get_all()
        assert len(all_providers) == 2
        names = {p.provider_name for p in all_providers}
        assert names == {"dummy", "failing"}

    def test_get_names(self, dummy_provider, failing_provider):
        CalendarProviderRegistry.register(dummy_provider)
        CalendarProviderRegistry.register(failing_provider)
        names = CalendarProviderRegistry.get_names()
        assert set(names) == {"dummy", "failing"}

    def test_clear(self, dummy_provider):
        CalendarProviderRegistry.register(dummy_provider)
        CalendarProviderRegistry.clear()
        assert CalendarProviderRegistry.count() == 0

    def test_replace_existing_provider(self, dummy_provider):
        CalendarProviderRegistry.register(dummy_provider)
        new_provider = _DummyProvider("dummy")
        CalendarProviderRegistry.register(new_provider)
        assert CalendarProviderRegistry.get("dummy") is new_provider
        assert CalendarProviderRegistry.count() == 1


# ===========================================================================
# Abstract interface contract tests
# ===========================================================================

class TestCalendarProviderInterface:
    def test_cannot_instantiate_abstract(self):
        """Verify CalendarProvider itself cannot be instantiated."""
        with pytest.raises(TypeError):
            CalendarProvider()

    def test_repr(self, dummy_provider):
        r = repr(dummy_provider)
        assert "DummyProvider" in r or "dummy" in r

    @pytest.mark.asyncio
    async def test_dummy_create_event(self, dummy_provider, sample_appointment, sample_credentials):
        result = await dummy_provider.create_event(sample_appointment, sample_credentials)
        assert result.success
        assert result.external_id == "ext-123"

    @pytest.mark.asyncio
    async def test_dummy_update_event(self, dummy_provider, sample_appointment, sample_credentials):
        result = await dummy_provider.update_event("ext-123", sample_appointment, sample_credentials)
        assert result.success
        assert result.external_id == "ext-123"

    @pytest.mark.asyncio
    async def test_dummy_delete_event(self, dummy_provider, sample_credentials):
        result = await dummy_provider.delete_event("ext-123", sample_credentials)
        assert result.success

    @pytest.mark.asyncio
    async def test_dummy_get_busy_times(self, dummy_provider, sample_credentials):
        start = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)
        blocks = await dummy_provider.get_busy_times(sample_credentials, start, end)
        assert len(blocks) == 1
        assert blocks[0].provider == "dummy"

    @pytest.mark.asyncio
    async def test_dummy_test_connection(self, dummy_provider, sample_credentials):
        assert await dummy_provider.test_connection(sample_credentials) is True

    @pytest.mark.asyncio
    async def test_failing_provider(self, failing_provider, sample_appointment, sample_credentials):
        result = await failing_provider.create_event(sample_appointment, sample_credentials)
        assert not result.success
        assert result.error == "Simulated failure"
        assert await failing_provider.test_connection(sample_credentials) is False


# ===========================================================================
# SyncDirection enum tests
# ===========================================================================

class TestSyncDirection:
    def test_values(self):
        assert SyncDirection.PUSH == "push"
        assert SyncDirection.PULL == "pull"
        assert SyncDirection.BIDIRECTIONAL == "bidirectional"


# ===========================================================================
# Google provider tests (mocked API client)
# ===========================================================================

class TestGoogleCalendarProvider:
    @pytest.mark.asyncio
    async def test_create_event_success(self, sample_appointment, sample_credentials):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()

        mock_client = MagicMock()
        mock_client.create_event = AsyncMock(return_value={"id": "gcal-event-1", "htmlLink": "https://cal.google.com/e/1"})
        mock_client.refresh_access_token = AsyncMock(return_value=None)

        with patch("services.calendar_providers.google._get_google_client", return_value=mock_client):
            result = await provider.create_event(sample_appointment, sample_credentials)

        assert result.success
        assert result.external_id == "gcal-event-1"
        assert result.link == "https://cal.google.com/e/1"
        assert result.provider == "google"

    @pytest.mark.asyncio
    async def test_create_event_api_returns_none(self, sample_appointment, sample_credentials):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()

        mock_client = MagicMock()
        mock_client.create_event = AsyncMock(return_value=None)

        with patch("services.calendar_providers.google._get_google_client", return_value=mock_client):
            result = await provider.create_event(sample_appointment, sample_credentials)

        assert not result.success
        assert "no event ID" in result.error

    @pytest.mark.asyncio
    async def test_delete_event_success(self, sample_credentials):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()

        mock_client = MagicMock()
        mock_client.delete_event = AsyncMock(return_value=True)

        with patch("services.calendar_providers.google._get_google_client", return_value=mock_client):
            result = await provider.delete_event("gcal-event-1", sample_credentials)

        assert result.success
        assert result.external_id == "gcal-event-1"

    @pytest.mark.asyncio
    async def test_get_busy_times(self, sample_credentials):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()
        now = datetime.now(timezone.utc)

        mock_client = MagicMock()
        mock_client.list_events = AsyncMock(return_value={
            "items": [
                {
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                    "summary": "Team Standup",
                },
                {
                    "start": {"dateTime": (now + timedelta(hours=2)).isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=3)).isoformat()},
                    "transparency": "transparent",  # Should be skipped
                },
            ]
        })

        with patch("services.calendar_providers.google._get_google_client", return_value=mock_client):
            blocks = await provider.get_busy_times(sample_credentials, now, now + timedelta(days=1))

        assert len(blocks) == 1
        assert blocks[0].title == "Team Standup"

    @pytest.mark.asyncio
    async def test_no_access_token(self, sample_appointment):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()
        result = await provider.create_event(sample_appointment, {})
        assert not result.success
        assert "access token" in result.error.lower()

    @pytest.mark.asyncio
    async def test_test_connection(self, sample_credentials):
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()

        mock_client = MagicMock()
        mock_client.get_calendar = AsyncMock(return_value={"id": "primary"})

        with patch("services.calendar_providers.google._get_google_client", return_value=mock_client):
            assert await provider.test_connection(sample_credentials) is True


# ===========================================================================
# Outlook provider tests (mocked API client)
# ===========================================================================

class TestOutlookCalendarProvider:
    @pytest.mark.asyncio
    async def test_create_event_success(self, sample_appointment, sample_credentials):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()

        mock_client = MagicMock()
        mock_client.create_event = MagicMock(return_value={"id": "outlook-event-1", "webLink": "https://outlook.com/e/1"})

        with patch("services.calendar_providers.outlook._get_outlook_client", return_value=mock_client):
            result = await provider.create_event(sample_appointment, sample_credentials)

        assert result.success
        assert result.external_id == "outlook-event-1"
        assert result.link == "https://outlook.com/e/1"
        assert result.provider == "outlook"

    @pytest.mark.asyncio
    async def test_create_event_api_returns_none(self, sample_appointment, sample_credentials):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()

        mock_client = MagicMock()
        mock_client.create_event = MagicMock(return_value=None)

        with patch("services.calendar_providers.outlook._get_outlook_client", return_value=mock_client):
            result = await provider.create_event(sample_appointment, sample_credentials)

        assert not result.success

    @pytest.mark.asyncio
    async def test_delete_event_success(self, sample_credentials):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()

        mock_client = MagicMock()
        mock_client.delete_event = MagicMock(return_value=True)

        with patch("services.calendar_providers.outlook._get_outlook_client", return_value=mock_client):
            result = await provider.delete_event("outlook-event-1", sample_credentials)

        assert result.success

    @pytest.mark.asyncio
    async def test_get_busy_times(self, sample_credentials):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()
        now = datetime.now(timezone.utc)

        mock_client = MagicMock()
        mock_client.list_events = MagicMock(return_value={
            "value": [
                {
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                    "subject": "Client Call",
                    "showAs": "busy",
                    "isAllDay": False,
                },
                {
                    "start": {"dateTime": (now + timedelta(hours=2)).isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=3)).isoformat()},
                    "showAs": "free",  # Should be skipped
                    "isAllDay": False,
                },
            ]
        })

        with patch("services.calendar_providers.outlook._get_outlook_client", return_value=mock_client):
            blocks = await provider.get_busy_times(sample_credentials, now, now + timedelta(days=1))

        assert len(blocks) == 1
        assert blocks[0].title == "Client Call"

    @pytest.mark.asyncio
    async def test_no_access_token(self, sample_appointment):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()
        result = await provider.create_event(sample_appointment, {})
        assert not result.success

    @pytest.mark.asyncio
    async def test_test_connection(self, sample_credentials):
        from services.calendar_providers.outlook import OutlookCalendarProvider

        provider = OutlookCalendarProvider()

        mock_client = MagicMock()
        mock_client.get_user_info = MagicMock(return_value={"displayName": "Test User"})

        with patch("services.calendar_providers.outlook._get_outlook_client", return_value=mock_client):
            assert await provider.test_connection(sample_credentials) is True


# ===========================================================================
# CalendarSyncOrchestrator tests
# ===========================================================================

class _MockCalendarEventMapInstance:
    """Lightweight stand-in for a CalendarEventMap ORM instance.

    Avoids triggering SQLAlchemy mapper configuration (which fails in test
    environments due to unrelated mapper issues).
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_mock_event_map_class():
    """Create a MagicMock class that acts like CalendarEventMap.

    Supports both class-level attribute access (for SQLAlchemy .filter()
    expressions) and instantiation (returns _MockCalendarEventMapInstance).
    """
    mock_cls = MagicMock()
    mock_cls.side_effect = lambda **kw: _MockCalendarEventMapInstance(**kw)
    return mock_cls


class TestCalendarSyncOrchestrator:
    """Tests for the orchestrator with fully mocked providers and DB."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock DB session."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.all.return_value = []
        db.flush.return_value = None
        db.execute.return_value.fetchall.return_value = []
        db.bind = MagicMock()
        db.bind.dialect.name = "postgresql"
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = 1
        user.organization_id = 10
        return user

    @pytest.mark.asyncio
    async def test_sync_creates_event_for_new_appointment(
        self, mock_db, mock_user, sample_appointment, dummy_provider
    ):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        CalendarProviderRegistry.register(dummy_provider)

        orchestrator = CalendarSyncOrchestrator()

        # Mock _get_user_providers to return our dummy provider
        orchestrator._get_user_providers = MagicMock(
            return_value=[("dummy", {"access_token": "tok"})]
        )

        with patch("services.calendar_sync_orchestrator._lazy_model", return_value=_make_mock_event_map_class()):
            results = await orchestrator.sync_appointment(mock_db, sample_appointment, mock_user)

        assert len(results) == 1
        assert results[0].success
        assert results[0].external_id == "ext-123"

        # Verify a CalendarEventMap was added
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_updates_existing_mapping(
        self, mock_db, mock_user, sample_appointment, dummy_provider
    ):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        CalendarProviderRegistry.register(dummy_provider)

        # Create a mock existing mapping
        existing_map = MagicMock()
        existing_map.external_id = "ext-old"
        existing_map.sync_status = "synced"
        existing_map.provider = "dummy"
        mock_db.query.return_value.filter.return_value.first.return_value = existing_map

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_user_providers = MagicMock(
            return_value=[("dummy", {"access_token": "tok"})]
        )

        with patch("services.calendar_sync_orchestrator._lazy_model", return_value=_make_mock_event_map_class()):
            results = await orchestrator.sync_appointment(mock_db, sample_appointment, mock_user)

        assert len(results) == 1
        assert results[0].success

        # Should have updated existing map, not created a new one
        assert existing_map.sync_status == "synced"
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_records_failure(
        self, mock_db, mock_user, sample_appointment, failing_provider
    ):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        CalendarProviderRegistry.register(failing_provider)

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_user_providers = MagicMock(
            return_value=[("failing", {"access_token": "tok"})]
        )

        with patch("services.calendar_sync_orchestrator._lazy_model", return_value=_make_mock_event_map_class()):
            results = await orchestrator.sync_appointment(mock_db, sample_appointment, mock_user)

        assert len(results) == 1
        assert not results[0].success

        # Should have created a failed mapping record
        mock_db.add.assert_called_once()
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.sync_status == "failed"

    @pytest.mark.asyncio
    async def test_delete_appointment_events(
        self, mock_db, mock_user, sample_appointment, dummy_provider
    ):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        CalendarProviderRegistry.register(dummy_provider)

        existing_map = MagicMock()
        existing_map.external_id = "ext-123"
        existing_map.provider = "dummy"
        existing_map.sync_status = "synced"
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_map]

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_credentials_for_provider = MagicMock(
            return_value=("dummy", {"access_token": "tok"})
        )

        results = await orchestrator.delete_appointment_events(mock_db, sample_appointment, mock_user)
        assert len(results) == 1
        assert results[0].success
        assert existing_map.sync_status == "deleted"

    @pytest.mark.asyncio
    async def test_get_all_busy_times(self, mock_db, mock_user, dummy_provider):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        CalendarProviderRegistry.register(dummy_provider)

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_user_providers = MagicMock(
            return_value=[("dummy", {"access_token": "tok"})]
        )

        start = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)

        blocks = await orchestrator.get_all_busy_times(mock_db, mock_user, start, end)
        assert len(blocks) == 1
        assert blocks[0].provider == "dummy"

    @pytest.mark.asyncio
    async def test_get_all_busy_times_multiple_providers(self, mock_db, mock_user):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        provider_a = _DummyProvider("provider_a")
        provider_b = _DummyProvider("provider_b")
        CalendarProviderRegistry.register(provider_a)
        CalendarProviderRegistry.register(provider_b)

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_user_providers = MagicMock(
            return_value=[
                ("provider_a", {"access_token": "tok_a"}),
                ("provider_b", {"access_token": "tok_b"}),
            ]
        )

        start = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)

        blocks = await orchestrator.get_all_busy_times(mock_db, mock_user, start, end)
        assert len(blocks) == 2
        providers_seen = {b.provider for b in blocks}
        assert providers_seen == {"provider_a", "provider_b"}

    @pytest.mark.asyncio
    async def test_sync_no_providers_returns_empty(self, mock_db, mock_user, sample_appointment):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        orchestrator = CalendarSyncOrchestrator()
        orchestrator._get_user_providers = MagicMock(return_value=[])

        results = await orchestrator.sync_appointment(mock_db, sample_appointment, mock_user)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_sync_status(self, mock_db):
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator

        mapping = MagicMock()
        mapping.provider = "google"
        mapping.external_id = "gcal-1"
        mapping.external_link = "https://cal.google.com/e/1"
        mapping.sync_status = "synced"
        mapping.synced_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        mapping.last_error = None
        mock_db.query.return_value.filter.return_value.all.return_value = [mapping]

        orchestrator = CalendarSyncOrchestrator()
        status = await orchestrator.get_sync_status(mock_db, 42)

        assert len(status) == 1
        assert status[0]["provider"] == "google"
        assert status[0]["sync_status"] == "synced"
        assert status[0]["external_id"] == "gcal-1"


# ===========================================================================
# CalendarEventMap model attribute tests
# ===========================================================================

class TestCalendarEventMapModel:
    def test_model_attributes(self):
        from database.models.calendar_event_map import CalendarEventMap

        # Verify column names exist on the model class
        assert hasattr(CalendarEventMap, "id")
        assert hasattr(CalendarEventMap, "organization_id")
        assert hasattr(CalendarEventMap, "appointment_id")
        assert hasattr(CalendarEventMap, "provider")
        assert hasattr(CalendarEventMap, "external_id")
        assert hasattr(CalendarEventMap, "external_link")
        assert hasattr(CalendarEventMap, "sync_status")
        assert hasattr(CalendarEventMap, "synced_at")
        assert hasattr(CalendarEventMap, "last_error")
        assert hasattr(CalendarEventMap, "created_at")
        assert hasattr(CalendarEventMap, "updated_at")

    def test_tablename(self):
        from database.models.calendar_event_map import CalendarEventMap
        assert CalendarEventMap.__tablename__ == "calendar_event_maps"

    def test_repr(self):
        from database.models.calendar_event_map import CalendarEventMap

        # Test __repr__ via the class method directly to avoid triggering
        # SQLAlchemy mapper configuration (broken by unrelated model)
        obj = _MockCalendarEventMapInstance(appointment_id=42, provider="google", external_id="gcal-123")
        # Bind the model's __repr__ to our mock object
        r = CalendarEventMap.__repr__(obj)
        assert "42" in r
        assert "google" in r
        assert "gcal-123" in r


# ===========================================================================
# Google provider: _extract_appointment_fields tests
# ===========================================================================

class TestExtractAppointmentFields:
    def test_from_dict(self):
        from services.calendar_providers.google import _extract_appointment_fields

        data = {
            "title": "Call",
            "scheduled_start": datetime(2026, 3, 15, 14, 0),
            "scheduled_end": datetime(2026, 3, 15, 14, 30),
            "description": "Notes",
            "location": "Office",
            "attendee_email": "a@b.com",
            "video_link": "https://zoom.us/j/123",
        }
        fields = _extract_appointment_fields(data)
        assert fields["title"] == "Call"
        assert fields["attendee_email"] == "a@b.com"

    def test_from_orm_object(self):
        from services.calendar_providers.google import _extract_appointment_fields

        obj = MagicMock()
        obj.title = "Review"
        obj.scheduled_start = datetime(2026, 3, 15, 14, 0)
        obj.scheduled_end = datetime(2026, 3, 15, 14, 30)
        obj.description = "Desc"
        obj.location = "Room A"
        obj.attendee_email = "x@y.com"
        obj.video_link = None

        fields = _extract_appointment_fields(obj)
        assert fields["title"] == "Review"
        assert fields["video_link"] is None


# ===========================================================================
# register_default_providers smoke test
# ===========================================================================

class TestRegisterDefaultProviders:
    def test_registers_google_and_outlook(self):
        from services.calendar_providers import register_default_providers

        register_default_providers()
        assert CalendarProviderRegistry.is_registered("google")
        assert CalendarProviderRegistry.is_registered("outlook")
        assert CalendarProviderRegistry.count() == 2
