"""
Default event subscribers for appointment lifecycle events.

Each subscriber is a standalone async function that handles one concern
(email, calendar sync, task creation, analytics, audit logging).  Failures
in any subscriber are isolated by the EventBus — they never propagate to
the publisher or block other subscribers.

Call ``register_all_subscribers()`` during application startup (e.g. in
``main.py`` or a startup event handler).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


# =============================================================================
# Email / SMS notifications
# =============================================================================

async def on_appointment_created_send_confirmation(event: Event) -> None:
    """Send confirmation email + SMS to the attendee when an appointment is booked."""
    data = event.data
    appointment_id = data.get("appointment_id")
    attendee_email = data.get("attendee_email")
    attendee_phone = data.get("attendee_phone")
    attendee_name = data.get("attendee_name", "")

    if not appointment_id:
        logger.warning("on_appointment_created_send_confirmation: missing appointment_id")
        return

    try:
        from scheduler_email_service import (
            send_appointment_confirmation_email,
            send_appointment_confirmation_sms,
        )

        if attendee_email:
            await _call_or_run(
                send_appointment_confirmation_email,
                to_email=attendee_email,
                attendee_name=attendee_name,
                appointment_data=data,
            )
            logger.info(
                "Confirmation email sent for appointment %s [%s]",
                appointment_id,
                event.correlation_id,
            )

        if attendee_phone:
            await _call_or_run(
                send_appointment_confirmation_sms,
                to_phone=attendee_phone,
                attendee_name=attendee_name,
                appointment_data=data,
            )
    except ImportError:
        logger.debug("scheduler_email_service not available — skipping confirmation email")
    except Exception as e:
        logger.error(
            "Failed to send confirmation for appointment %s: %s",
            appointment_id,
            e,
            exc_info=True,
        )
        raise  # Let EventBus catch and isolate


async def on_appointment_cancelled_send_notification(event: Event) -> None:
    """Send cancellation notice to attendee and assigned LO."""
    data = event.data
    appointment_id = data.get("appointment_id")
    attendee_email = data.get("attendee_email")

    if not appointment_id:
        return

    try:
        from scheduler_email_service import (
            send_appointment_cancellation_email,
            send_team_member_cancellation_email,
        )

        if attendee_email:
            await _call_or_run(
                send_appointment_cancellation_email,
                to_email=attendee_email,
                appointment_data=data,
            )

        lo_email = data.get("assigned_user_email")
        if lo_email:
            await _call_or_run(
                send_team_member_cancellation_email,
                to_email=lo_email,
                appointment_data=data,
            )

        logger.info("Cancellation notifications sent for appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduler_email_service not available — skipping cancellation email")
    except Exception as e:
        logger.error("Failed to send cancellation notice for %s: %s", appointment_id, e)
        raise


# =============================================================================
# Calendar sync (Google / Outlook)
# =============================================================================

async def on_appointment_created_sync_calendar(event: Event) -> None:
    """Sync newly created appointment to external calendar (Google Calendar, Outlook)."""
    data = event.data
    appointment_id = data.get("appointment_id")
    assigned_user_id = data.get("assigned_user_id")

    if not appointment_id or not assigned_user_id:
        return

    try:
        from services.unified_calendar_service import unified_calendar_service
        await _call_or_run(
            unified_calendar_service.create_event_from_appointment,
            user_id=assigned_user_id,
            appointment_data=data,
        )
        logger.info(
            "Calendar sync completed for appointment %s [%s]",
            appointment_id,
            event.correlation_id,
        )
    except ImportError:
        logger.debug("unified_calendar_service not available — skipping calendar sync")
    except Exception as e:
        logger.error("Calendar sync failed for appointment %s: %s", appointment_id, e)
        raise


async def on_appointment_cancelled_sync_calendar(event: Event) -> None:
    """Remove or cancel the calendar event when an appointment is cancelled."""
    data = event.data
    appointment_id = data.get("appointment_id")
    google_event_id = data.get("google_calendar_event_id")
    outlook_event_id = data.get("outlook_event_id")

    if not (google_event_id or outlook_event_id):
        return

    try:
        from services.unified_calendar_service import unified_calendar_service
        await _call_or_run(
            unified_calendar_service.cancel_event_from_appointment,
            appointment_data=data,
        )
        logger.info("Calendar event cancelled for appointment %s", appointment_id)
    except ImportError:
        logger.debug("unified_calendar_service not available — skipping calendar cancel")
    except Exception as e:
        logger.error("Calendar cancel failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Task creation
# =============================================================================

async def on_appointment_created_create_tasks(event: Event) -> None:
    """Create follow-up tasks when an appointment is booked.

    For example: "Prepare docs for pre-approval review with Jane Doe".
    """
    data = event.data
    appointment_id = data.get("appointment_id")
    assigned_user_id = data.get("assigned_user_id")
    meeting_type = data.get("meeting_type")
    org_id = event.org_id

    if not appointment_id or not assigned_user_id:
        return

    try:
        from services.workflow_task_generator import generate_appointment_prep_tasks
        await _call_or_run(
            generate_appointment_prep_tasks,
            appointment_id=appointment_id,
            user_id=assigned_user_id,
            meeting_type=meeting_type,
            organization_id=org_id,
        )
        logger.info("Follow-up tasks created for appointment %s", appointment_id)
    except ImportError:
        logger.debug("workflow_task_generator not available — skipping task creation")
    except Exception as e:
        logger.error("Task creation failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Analytics / conversion tracking
# =============================================================================

async def on_appointment_completed_track_conversion(event: Event) -> None:
    """Track the appointment completion in the analytics pipeline."""
    data = event.data
    appointment_id = data.get("appointment_id")
    meeting_type = data.get("meeting_type")
    lead_id = data.get("lead_id")

    if not appointment_id:
        return

    try:
        from services.scheduling_intelligence import track_appointment_outcome
        await _call_or_run(
            track_appointment_outcome,
            appointment_id=appointment_id,
            outcome="completed",
            meeting_type=meeting_type,
            lead_id=lead_id,
        )
        logger.info("Conversion tracked for completed appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduling_intelligence not available — skipping conversion tracking")
    except Exception as e:
        logger.error("Conversion tracking failed for appointment %s: %s", appointment_id, e)
        raise


async def on_appointment_no_show_track(event: Event) -> None:
    """Record a no-show event for analytics and potential re-engagement."""
    data = event.data
    appointment_id = data.get("appointment_id")

    if not appointment_id:
        return

    try:
        from services.scheduling_intelligence import track_appointment_outcome
        await _call_or_run(
            track_appointment_outcome,
            appointment_id=appointment_id,
            outcome="no_show",
            meeting_type=data.get("meeting_type"),
            lead_id=data.get("lead_id"),
        )
        logger.info("No-show tracked for appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduling_intelligence not available — skipping no-show tracking")
    except Exception as e:
        logger.error("No-show tracking failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Audit logging
# =============================================================================

async def on_any_appointment_event_audit_log(event: Event) -> None:
    """Write every appointment lifecycle event to SchedulerAuditLog.

    This subscriber is registered for all appointment event types to provide
    a complete audit trail.
    """
    data = event.data
    appointment_id = data.get("appointment_id")
    org_id = event.org_id

    if not appointment_id:
        return

    # Map event type to audit action
    action_map = {
        EventType.APPOINTMENT_CREATED: "created",
        EventType.APPOINTMENT_CONFIRMED: "confirmed",
        EventType.APPOINTMENT_CANCELLED: "cancelled",
        EventType.APPOINTMENT_RESCHEDULED: "rescheduled",
        EventType.APPOINTMENT_COMPLETED: "completed",
        EventType.APPOINTMENT_NO_SHOW: "no_show",
        EventType.SLOT_HELD: "slot_held",
        EventType.SLOT_RELEASED: "slot_released",
        EventType.BOOKING_CONFLICT: "booking_conflict",
        EventType.WAITLIST_NOTIFIED: "waitlist_notified",
    }
    action = action_map.get(event.type, event.type.value)

    try:
        from db import SessionLocal
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base

        models = create_smart_scheduler_models(Base)
        AuditLog = models["SchedulerAuditLog"]

        session = SessionLocal()
        try:
            log_entry = AuditLog(
                organization_id=int(org_id) if org_id else None,
                user_id=data.get("changed_by_user_id"),
                action=action,
                entity_type="appointment",
                entity_id=appointment_id,
                changes={
                    "event_type": event.type.value,
                    "correlation_id": event.correlation_id,
                    "source": event.source,
                    "timestamp": event.timestamp.isoformat(),
                    **{k: v for k, v in data.items() if k not in ("appointment_id",)},
                },
            )
            session.add(log_entry)
            session.commit()
            logger.debug("Audit log written for appointment %s action=%s", appointment_id, action)
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB modules not available — skipping audit log")
    except Exception as e:
        logger.error("Audit logging failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Slot management
# =============================================================================

async def on_slot_released_notify_waitlist(event: Event) -> None:
    """When a slot is released (cancellation), notify anyone on the waitlist."""
    data = event.data
    slot_start = data.get("slot_start")
    assigned_user_id = data.get("assigned_user_id")

    if not slot_start or not assigned_user_id:
        return

    try:
        from services.notification_service import notification_service
        await _call_or_run(
            notification_service.notify_waitlist,
            user_id=assigned_user_id,
            slot_start=slot_start,
            org_id=event.org_id,
        )
        logger.info("Waitlist notified for released slot at %s", slot_start)
    except (ImportError, AttributeError):
        logger.debug("Waitlist notification not available — skipping")
    except Exception as e:
        logger.error("Waitlist notification failed: %s", e)
        raise


# =============================================================================
# Registration
# =============================================================================

def register_all_subscribers() -> None:
    """Register all default event subscribers.  Call once during app startup."""

    # -- appointment.created --
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_send_confirmation)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_sync_calendar)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_create_tasks)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_any_appointment_event_audit_log)

    # -- appointment.confirmed --
    event_bus.subscribe(EventType.APPOINTMENT_CONFIRMED, on_any_appointment_event_audit_log)

    # -- appointment.cancelled --
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_appointment_cancelled_send_notification)
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_appointment_cancelled_sync_calendar)
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_any_appointment_event_audit_log)

    # -- appointment.rescheduled --
    event_bus.subscribe(EventType.APPOINTMENT_RESCHEDULED, on_any_appointment_event_audit_log)

    # -- appointment.completed --
    event_bus.subscribe(EventType.APPOINTMENT_COMPLETED, on_appointment_completed_track_conversion)
    event_bus.subscribe(EventType.APPOINTMENT_COMPLETED, on_any_appointment_event_audit_log)

    # -- appointment.no_show --
    event_bus.subscribe(EventType.APPOINTMENT_NO_SHOW, on_appointment_no_show_track)
    event_bus.subscribe(EventType.APPOINTMENT_NO_SHOW, on_any_appointment_event_audit_log)

    # -- slot.released --
    event_bus.subscribe(EventType.SLOT_RELEASED, on_slot_released_notify_waitlist)
    event_bus.subscribe(EventType.SLOT_RELEASED, on_any_appointment_event_audit_log)

    # -- slot.held --
    event_bus.subscribe(EventType.SLOT_HELD, on_any_appointment_event_audit_log)

    # -- booking.conflict --
    event_bus.subscribe(EventType.BOOKING_CONFLICT, on_any_appointment_event_audit_log)

    # -- waitlist.notified --
    event_bus.subscribe(EventType.WAITLIST_NOTIFIED, on_any_appointment_event_audit_log)

    logger.info(
        "Registered %d appointment event subscribers across %d event types",
        event_bus.subscriber_count,
        len(EventType),
    )


# =============================================================================
# Helpers
# =============================================================================

async def _call_or_run(fn, **kwargs):
    """Call *fn* with **kwargs, awaiting if it returns a coroutine.

    Many service functions in the codebase are plain sync functions.  This
    helper lets subscribers call them without caring.
    """
    import asyncio
    import inspect

    if asyncio.iscoroutinefunction(fn):
        return await fn(**kwargs)
    else:
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
