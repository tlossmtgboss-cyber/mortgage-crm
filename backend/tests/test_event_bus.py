"""
Tests for the in-process event bus (services/event_bus.py)
and default subscriber registration (services/event_subscribers.py).

Run with:
    pytest backend/tests/test_event_bus.py -v
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.event_bus import Event, EventBus, EventType, event_bus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_bus():
    """Reset the singleton before and after every test.

    Also ensures that event_subscribers.py's module-level ``event_bus``
    reference points to the same singleton we are testing against.
    """
    import services.event_bus as eb_mod
    import services.event_subscribers as es_mod

    # Make sure all modules share the same singleton
    es_mod.event_bus = eb_mod.event_bus
    event_bus.clear()
    yield
    event_bus.clear()


def _make_event(
    event_type: EventType = EventType.APPOINTMENT_CREATED,
    **data_overrides,
) -> Event:
    """Convenience factory for test events."""
    data = {"appointment_id": 42, "attendee_email": "test@example.com"}
    data.update(data_overrides)
    return Event(type=event_type, data=data, org_id="1")


# ===========================================================================
# Core delivery
# ===========================================================================

class TestEventDelivery:
    """Events are delivered to all registered subscribers."""

    @pytest.mark.asyncio
    async def test_async_handler_receives_event(self):
        received = []

        async def handler(event: Event):
            received.append(event)

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)
        event = _make_event()
        result = await event_bus.publish(event)

        assert len(received) == 1
        assert received[0] is event
        assert result["succeeded"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_sync_handler_receives_event(self):
        received = []

        def handler(event: Event):
            received.append(event)

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)
        event = _make_event()
        result = await event_bus.publish(event)

        assert len(received) == 1
        assert received[0] is event
        assert result["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self):
        call_order = []

        async def handler_a(event: Event):
            call_order.append("a")

        async def handler_b(event: Event):
            call_order.append("b")

        def handler_c(event: Event):
            call_order.append("c")

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler_a)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler_b)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler_c)

        await event_bus.publish(_make_event())

        assert call_order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_different_event_types_isolated(self):
        created_calls = []
        cancelled_calls = []

        async def on_created(event: Event):
            created_calls.append(event)

        async def on_cancelled(event: Event):
            cancelled_calls.append(event)

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_created)
        event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_cancelled)

        await event_bus.publish(_make_event(EventType.APPOINTMENT_CREATED))

        assert len(created_calls) == 1
        assert len(cancelled_calls) == 0

    @pytest.mark.asyncio
    async def test_no_subscribers_is_fine(self):
        """Publishing to an event with no subscribers should not raise."""
        result = await event_bus.publish(_make_event(EventType.SLOT_HELD))
        assert result["handler_count"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0


# ===========================================================================
# Error isolation
# ===========================================================================

class TestErrorIsolation:
    """Subscriber errors must not block the publisher or other subscribers."""

    @pytest.mark.asyncio
    async def test_failing_handler_does_not_block_others(self):
        call_order = []

        async def good_handler_1(event: Event):
            call_order.append("good1")

        async def bad_handler(event: Event):
            call_order.append("bad")
            raise RuntimeError("Something went wrong")

        async def good_handler_2(event: Event):
            call_order.append("good2")

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, good_handler_1)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, bad_handler)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, good_handler_2)

        result = await event_bus.publish(_make_event())

        assert call_order == ["good1", "bad", "good2"]
        assert result["succeeded"] == 2
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert "bad_handler" in result["errors"][0]["handler"]

    @pytest.mark.asyncio
    async def test_failing_sync_handler_isolated(self):
        calls = []

        def sync_bad(event: Event):
            raise ValueError("sync boom")

        async def async_good(event: Event):
            calls.append("ok")

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, sync_bad)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, async_good)

        result = await event_bus.publish(_make_event())

        assert calls == ["ok"]
        assert result["failed"] == 1
        assert result["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_error_handler_is_called(self):
        errors_received = []

        def error_handler(event, handler, exc):
            errors_received.append((event.type, handler.__name__, str(exc)))

        async def bad(event: Event):
            raise RuntimeError("kaboom")

        event_bus.on_error(error_handler)
        event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, bad)

        await event_bus.publish(_make_event(EventType.APPOINTMENT_CANCELLED))

        assert len(errors_received) == 1
        assert errors_received[0][1] == "bad"
        assert "kaboom" in errors_received[0][2]

    @pytest.mark.asyncio
    async def test_error_handler_failure_does_not_propagate(self):
        """Even if the error handler itself blows up, nothing propagates."""

        def broken_error_handler(event, handler, exc):
            raise RuntimeError("error handler broke too")

        async def bad(event: Event):
            raise RuntimeError("initial failure")

        event_bus.on_error(broken_error_handler)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, bad)

        # Should not raise
        result = await event_bus.publish(_make_event())
        assert result["failed"] == 1


# ===========================================================================
# Unsubscribe
# ===========================================================================

class TestUnsubscribe:

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_handler(self):
        calls = []

        async def handler(event: Event):
            calls.append(1)

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)
        await event_bus.publish(_make_event())
        assert len(calls) == 1

        event_bus.unsubscribe(EventType.APPOINTMENT_CREATED, handler)
        await event_bus.publish(_make_event())
        assert len(calls) == 1  # still 1, not 2

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_is_noop(self):
        """Unsubscribing a handler that was never subscribed should not raise."""

        async def never_subscribed(event: Event):
            pass

        event_bus.unsubscribe(EventType.APPOINTMENT_CREATED, never_subscribed)

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_is_idempotent(self):
        calls = []

        async def handler(event: Event):
            calls.append(1)

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)  # duplicate

        await event_bus.publish(_make_event())
        assert len(calls) == 1  # called only once


# ===========================================================================
# publish_sync
# ===========================================================================

class TestPublishSync:

    def test_publish_sync_from_sync_context(self):
        """publish_sync should work when called outside an async context."""
        calls = []

        async def handler(event: Event):
            calls.append(event.data["appointment_id"])

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)

        # We are NOT inside an async function — call publish_sync
        event_bus.publish_sync(_make_event())

        assert calls == [42]

    @pytest.mark.asyncio
    async def test_publish_sync_from_async_context(self):
        """publish_sync inside an already-running event loop should schedule the task."""
        calls = []

        async def handler(event: Event):
            calls.append(event.data["appointment_id"])

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)

        event_bus.publish_sync(_make_event())

        # The task was scheduled via create_task — give it a tick to run
        await asyncio.sleep(0)

        assert calls == [42]


# ===========================================================================
# Event construction
# ===========================================================================

class TestEventConstruction:

    def test_event_gets_correlation_id(self):
        event = Event(type=EventType.APPOINTMENT_CREATED, data={})
        assert event.correlation_id is not None
        assert len(event.correlation_id) == 12

    def test_event_preserves_explicit_correlation_id(self):
        event = Event(
            type=EventType.APPOINTMENT_CREATED,
            data={},
            correlation_id="custom-id-123",
        )
        assert event.correlation_id == "custom-id-123"

    def test_event_timestamp_is_utc(self):
        event = Event(type=EventType.APPOINTMENT_CREATED, data={})
        assert event.timestamp.tzinfo is not None


# ===========================================================================
# Middleware
# ===========================================================================

class TestMiddleware:

    @pytest.mark.asyncio
    async def test_middleware_can_suppress_event(self):
        calls = []

        def suppress_all(event: Event):
            return None  # suppress

        async def handler(event: Event):
            calls.append(1)

        event_bus.add_middleware(suppress_all)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)

        result = await event_bus.publish(_make_event())

        assert len(calls) == 0
        assert result.get("suppressed") is True

    @pytest.mark.asyncio
    async def test_middleware_can_transform_event(self):
        received_data = []

        def enrich(event: Event):
            event.data["enriched"] = True
            return event

        async def handler(event: Event):
            received_data.append(event.data.get("enriched"))

        event_bus.add_middleware(enrich)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, handler)

        await event_bus.publish(_make_event())

        assert received_data == [True]


# ===========================================================================
# Introspection
# ===========================================================================

class TestIntrospection:

    def test_get_subscribers(self):
        async def h1(e): pass
        async def h2(e): pass

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, h1)
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, h2)

        subs = event_bus.get_subscribers(EventType.APPOINTMENT_CREATED)
        assert len(subs) == 2
        # Returned list is a copy
        subs.clear()
        assert len(event_bus.get_subscribers(EventType.APPOINTMENT_CREATED)) == 2

    @pytest.mark.asyncio
    async def test_recent_events_log(self):
        async def noop(e): pass
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, noop)

        for i in range(5):
            await event_bus.publish(_make_event(appointment_id=i))

        recent = event_bus.get_recent_events(limit=3)
        assert len(recent) == 3
        assert recent[-1].data["appointment_id"] == 4

    @pytest.mark.asyncio
    async def test_recent_events_filtered_by_type(self):
        async def noop(e): pass
        event_bus.subscribe(EventType.APPOINTMENT_CREATED, noop)
        event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, noop)

        await event_bus.publish(_make_event(EventType.APPOINTMENT_CREATED))
        await event_bus.publish(_make_event(EventType.APPOINTMENT_CANCELLED))
        await event_bus.publish(_make_event(EventType.APPOINTMENT_CREATED))

        created_events = event_bus.get_recent_events(event_type=EventType.APPOINTMENT_CREATED)
        assert len(created_events) == 2

    def test_subscriber_count(self):
        async def h1(e): pass
        async def h2(e): pass

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, h1)
        event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, h2)

        assert event_bus.subscriber_count == 2


# ===========================================================================
# Singleton behavior
# ===========================================================================

class TestSingleton:

    def test_same_instance(self):
        bus1 = EventBus()
        bus2 = EventBus()
        assert bus1 is bus2

    def test_module_level_is_singleton(self):
        assert event_bus is EventBus()

    def test_reset_instance_allows_new_creation(self):
        """reset_instance sets _instance to None so a future __new__ would create fresh."""
        assert EventBus._instance is not None
        original = EventBus._instance

        EventBus.reset_instance()
        assert EventBus._instance is None

        # Restore immediately — we just needed to verify the mechanism.
        # Actually creating a new instance would invalidate all module-level
        # references, so we restore the original instead.
        EventBus._instance = original


# ===========================================================================
# Subscriber registration (event_subscribers.py)
# ===========================================================================

class TestSubscriberRegistration:

    def test_register_all_subscribers_populates_bus(self):
        from services.event_subscribers import register_all_subscribers

        event_bus.clear()
        register_all_subscribers()

        # Verify at least 1 handler for key event types
        assert len(event_bus.get_subscribers(EventType.APPOINTMENT_CREATED)) >= 3
        assert len(event_bus.get_subscribers(EventType.APPOINTMENT_CANCELLED)) >= 2
        assert len(event_bus.get_subscribers(EventType.APPOINTMENT_COMPLETED)) >= 1
        assert len(event_bus.get_subscribers(EventType.APPOINTMENT_NO_SHOW)) >= 1

    def test_register_all_is_idempotent(self):
        from services.event_subscribers import register_all_subscribers

        event_bus.clear()
        register_all_subscribers()
        count_after_first = event_bus.subscriber_count

        register_all_subscribers()
        count_after_second = event_bus.subscriber_count

        assert count_after_first == count_after_second

    @pytest.mark.asyncio
    async def test_audit_subscriber_registered_for_all_appointment_events(self):
        from services.event_subscribers import (
            on_any_appointment_event_audit_log,
            register_all_subscribers,
        )

        event_bus.clear()
        register_all_subscribers()

        appointment_events = [
            EventType.APPOINTMENT_CREATED,
            EventType.APPOINTMENT_CONFIRMED,
            EventType.APPOINTMENT_CANCELLED,
            EventType.APPOINTMENT_RESCHEDULED,
            EventType.APPOINTMENT_COMPLETED,
            EventType.APPOINTMENT_NO_SHOW,
        ]

        for et in appointment_events:
            subs = event_bus.get_subscribers(et)
            handler_names = [h.__name__ for h in subs]
            assert "on_any_appointment_event_audit_log" in handler_names, (
                f"Audit handler not registered for {et.value}"
            )


# ===========================================================================
# Clear / teardown
# ===========================================================================

class TestClear:

    def test_clear_removes_everything(self):
        async def h(e): pass
        def err(e, h, ex): pass

        event_bus.subscribe(EventType.APPOINTMENT_CREATED, h)
        event_bus.on_error(err)

        event_bus.clear()

        assert event_bus.subscriber_count == 0
        assert len(event_bus.get_recent_events()) == 0
