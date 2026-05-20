"""
Integration tests for the calendar provider interface and registry.

Covers:
  - SyncDirection / SyncStatus enums
  - ExternalCalendarEvent dataclass shape + to_dict()
  - BusyBlock construction
  - ProviderSyncResult.success property
  - CalendarProviderRegistry register/unregister/lookup
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


try:
    from services.calendar_providers.base import (
        SyncDirection,
        SyncStatus,
        ExternalCalendarEvent,
        BusyBlock,
        ProviderSyncResult,
        CalendarProvider,
    )
    from services.calendar_providers import CalendarProviderRegistry
except Exception as e:
    pytest.skip(f"calendar_providers not importable: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_sync_direction_push_value():
    assert SyncDirection.PUSH == "push"


def test_sync_direction_bidirectional_value():
    assert SyncDirection.BIDIRECTIONAL.value == "bidirectional"


def test_sync_status_includes_conflict():
    assert SyncStatus.CONFLICT == "conflict"
    assert SyncStatus.SUCCESS.value == "success"


# ---------------------------------------------------------------------------
# ExternalCalendarEvent + BusyBlock
# ---------------------------------------------------------------------------

def _make_event():
    return ExternalCalendarEvent(
        external_id="evt_1",
        provider="google",
        title="Borrower meet",
        start=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc),
    )


def test_external_event_to_dict_includes_iso_start():
    e = _make_event()
    d = e.to_dict()
    assert d["external_id"] == "evt_1"
    assert d["provider"] == "google"
    assert d["start"].startswith("2026-05-20")


def test_external_event_default_attendees_empty():
    e = _make_event()
    assert e.attendees == []


def test_busy_block_construction():
    b = BusyBlock(
        start=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        provider="outlook",
    )
    assert b.is_all_day is False
    assert (b.end - b.start) == timedelta(hours=1)


# ---------------------------------------------------------------------------
# ProviderSyncResult
# ---------------------------------------------------------------------------

def test_provider_sync_result_success_property_true():
    r = ProviderSyncResult(provider="google", status=SyncStatus.SUCCESS)
    assert r.success is True


def test_provider_sync_result_success_property_false_on_failed():
    r = ProviderSyncResult(provider="google", status=SyncStatus.FAILED, error="oops")
    assert r.success is False
    assert r.error == "oops"


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------

class _FakeProvider(CalendarProvider):
    def __init__(self, name="fake"):
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name

    async def create_event(self, appointment, credentials):
        return ProviderSyncResult(provider=self._name, status=SyncStatus.SUCCESS)

    async def update_event(self, external_id, appointment, credentials):
        return ProviderSyncResult(provider=self._name, status=SyncStatus.SUCCESS)

    async def delete_event(self, external_id, credentials):
        return ProviderSyncResult(provider=self._name, status=SyncStatus.SUCCESS)

    async def get_busy_times(self, credentials, start, end):
        return []

    async def test_connection(self, credentials):
        return True


def test_registry_register_and_get():
    CalendarProviderRegistry.clear()
    p = _FakeProvider("fakeA")
    CalendarProviderRegistry.register(p)
    assert CalendarProviderRegistry.get("fakeA") is p
    assert CalendarProviderRegistry.is_registered("fakeA")


def test_registry_unregister_returns_true_for_existing():
    CalendarProviderRegistry.clear()
    CalendarProviderRegistry.register(_FakeProvider("toRemove"))
    assert CalendarProviderRegistry.unregister("toRemove") is True
    assert CalendarProviderRegistry.unregister("toRemove") is False


def test_registry_get_all_returns_list():
    CalendarProviderRegistry.clear()
    CalendarProviderRegistry.register(_FakeProvider("a"))
    CalendarProviderRegistry.register(_FakeProvider("b"))
    assert CalendarProviderRegistry.count() == 2
    names = CalendarProviderRegistry.get_names()
    assert set(names) == {"a", "b"}


def test_registry_get_missing_returns_none():
    CalendarProviderRegistry.clear()
    assert CalendarProviderRegistry.get("never-registered") is None
