"""
In-process async event bus for appointment lifecycle events.

Decouples synchronous chains (email, calendar sync, task creation, analytics)
so that a failure in any subscriber does not block or fail the publisher.

Usage:
    from services.event_bus import event_bus, Event, EventType

    # Publish (async context)
    await event_bus.publish(Event(
        type=EventType.APPOINTMENT_CREATED,
        data={"appointment_id": 42, "attendee_email": "jane@example.com"},
        org_id="7",
    ))

    # Publish (sync context — fire-and-forget)
    event_bus.publish_sync(Event(
        type=EventType.APPOINTMENT_CANCELLED,
        data={"appointment_id": 42, "reason": "conflict"},
    ))
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Event types
# =============================================================================

class EventType(str, Enum):
    """Lifecycle events emitted by the scheduler and agent subsystems."""

    # Appointment lifecycle
    APPOINTMENT_CREATED = "appointment.created"
    APPOINTMENT_CONFIRMED = "appointment.confirmed"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_COMPLETED = "appointment.completed"
    APPOINTMENT_NO_SHOW = "appointment.no_show"

    # Slot management
    SLOT_HELD = "slot.held"
    SLOT_RELEASED = "slot.released"

    # Booking operations
    BOOKING_CONFLICT = "booking.conflict"
    WAITLIST_NOTIFIED = "waitlist.notified"

    # =========================================================================
    # Inter-agent events — emitted by AgentEventBridge
    # =========================================================================

    # Loan pipeline events
    LOAN_STALLED = "agent.loan_stalled"
    LOAN_STAGE_CHANGED = "agent.loan_stage_changed"

    # Lead events
    HOT_LEAD_DETECTED = "agent.hot_lead_detected"

    # Document events
    DOCUMENTS_EXPIRED = "agent.documents_expired"

    # Compliance events
    COMPLIANCE_VIOLATION = "agent.compliance_violation"

    # Email / inbound data events
    EMAIL_DATA_EXTRACTED = "agent.email_data_extracted"

    # POS (borrower-side application)
    POS_APPLICATION_SUBMITTED = "pos.application.submitted"
    POS_APPOINTMENT_BOOKED = "pos.appointment.booked"


# =============================================================================
# Event payload
# =============================================================================

@dataclass
class Event:
    """Immutable-ish event envelope carried through the bus."""

    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "system"
    org_id: Optional[str] = None
    correlation_id: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.correlation_id is None:
            self.correlation_id = uuid.uuid4().hex[:12]


# =============================================================================
# Subscriber / handler type
# =============================================================================

EventHandler = Callable[[Event], Any]  # sync or async


# =============================================================================
# Event Bus
# =============================================================================

class EventBus:
    """In-process async event bus with subscriber management.

    * Subscribers are isolated: a failure in one handler never propagates to the
      publisher or to other handlers.
    * Supports both sync and async handlers.
    * Provides ``publish_sync`` for callers that do not have an active event loop
      (e.g. background threads).
    * Singleton — use the module-level ``event_bus`` instance.
    """

    _instance: Optional["EventBus"] = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._subscribers: Dict[EventType, List[EventHandler]] = {}
            inst._error_handlers: List[Callable] = []
            inst._middleware: List[Callable] = []
            inst._event_log: List[Event] = []
            inst._max_log_size: int = 1000
            cls._instance = inst
        return cls._instance

    # -- subscription --------------------------------------------------------

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register *handler* for *event_type*.

        The same handler can be registered for multiple event types but will
        only be added once per type.
        """
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)
            logger.debug("Subscribed %s to %s", handler.__name__, event_type.value)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove *handler* from *event_type*.  No-op if not registered."""
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
            logger.debug("Unsubscribed %s from %s", handler.__name__, event_type.value)
        except ValueError:
            pass

    def on_error(self, handler: Callable) -> None:
        """Register a global error handler: ``fn(event, failing_handler, exception)``."""
        if handler not in self._error_handlers:
            self._error_handlers.append(handler)

    def add_middleware(self, middleware: Callable) -> None:
        """Register middleware that runs before every handler.

        Signature: ``async fn(event) -> Event | None``.
        Return ``None`` to suppress the event (short-circuit).
        """
        if middleware not in self._middleware:
            self._middleware.append(middleware)

    # -- publishing ----------------------------------------------------------

    async def publish(self, event: Event) -> Dict[str, Any]:
        """Publish *event* to all registered subscribers.

        Errors in individual subscribers are caught, logged, and forwarded to
        any registered error handlers — they never propagate to the caller.

        Returns a summary dict with handler results for observability.
        """
        # Run middleware
        for mw in self._middleware:
            try:
                if asyncio.iscoroutinefunction(mw):
                    result = await mw(event)
                else:
                    result = mw(event)
                if result is None:
                    logger.debug("Middleware %s suppressed event %s", mw.__name__, event.type.value)
                    return {"suppressed": True, "by": mw.__name__}
                event = result
            except Exception as e:
                logger.error("Middleware %s raised for %s: %s", mw.__name__, event.type.value, e)

        # Keep an in-memory log for debugging / recent-event queries
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

        handlers = self._subscribers.get(event.type, [])
        results: Dict[str, Any] = {
            "event_type": event.type.value,
            "correlation_id": event.correlation_id,
            "handler_count": len(handlers),
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

        for handler in handlers:
            handler_name = getattr(handler, "__name__", repr(handler))
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
                results["succeeded"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"handler": handler_name, "error": str(e)})
                logger.error(
                    "Event handler %s failed for %s [%s]: %s",
                    handler_name,
                    event.type.value,
                    event.correlation_id,
                    e,
                    exc_info=True,
                )
                # Notify error handlers — but never let those blow up either
                for error_handler in self._error_handlers:
                    try:
                        error_handler(event, handler, e)
                    except Exception:
                        pass

        if results["failed"]:
            logger.warning(
                "Event %s [%s]: %d/%d handlers failed",
                event.type.value,
                event.correlation_id,
                results["failed"],
                results["handler_count"],
            )

        return results

    def publish_sync(self, event: Event) -> None:
        """Fire-and-forget publish for synchronous / non-async callers.

        If an event loop is already running (common inside FastAPI request
        handlers called from sync code), the publish is scheduled as a task.
        Otherwise a new loop is spun up transiently.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            loop.create_task(self.publish(event))
        else:
            try:
                asyncio.run(self.publish(event))
            except RuntimeError:
                logger.warning(
                    "Cannot publish event %s synchronously — no usable event loop",
                    event.type.value,
                )

    # -- introspection -------------------------------------------------------

    def get_subscribers(self, event_type: EventType) -> List[EventHandler]:
        """Return a copy of the handler list for *event_type*."""
        return list(self._subscribers.get(event_type, []))

    def get_recent_events(self, limit: int = 50, event_type: Optional[EventType] = None) -> List[Event]:
        """Return recent events from the in-memory log."""
        events = self._event_log
        if event_type is not None:
            events = [e for e in events if e.type == event_type]
        return list(events[-limit:])

    @property
    def subscriber_count(self) -> int:
        return sum(len(h) for h in self._subscribers.values())

    # -- lifecycle -----------------------------------------------------------

    def clear(self) -> None:
        """Remove all subscribers, error handlers, middleware, and event log.

        Intended for testing teardown — not for production use.
        """
        self._subscribers.clear()
        self._error_handlers.clear()
        self._middleware.clear()
        self._event_log.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Destroy the singleton — only for tests."""
        cls._instance = None


# =============================================================================
# Module-level singleton
# =============================================================================

event_bus = EventBus()
