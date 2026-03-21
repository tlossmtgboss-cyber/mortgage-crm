"""
Appointment lifecycle operations: update, cancel, reschedule, confirm,
mark_no_show, mark_completed.

Extracted from AppointmentService to keep the main service file focused.
Each function receives the db session, organization_id, and callback references
for audit logging and event emission, so it can operate without a reference
back to the service instance.

This module is NOT meant to be called directly by route handlers -- the
AppointmentService facade delegates here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from services.appointment._models import (
    AppointmentEvent,
    AppointmentResult,
    AppointmentSource,
    ConflictError,
    get_model,
    mask_email,
    safe_enum_parse,
)
from services.appointment.conflict_checker import (
    check_conflict_for_update as _check_conflict_for_update,
)
from services.appointment.crm_bridge import (
    create_followup_task as _create_followup_task,
    log_activity as _log_activity,
)
from services.appointment.notifications import (
    send_cancellation_notification as _send_cancellation_notification,
    send_update_notification as _send_update_notification,
    send_confirmation_email as _send_confirmation_email,
)

logger = logging.getLogger(__name__)


# =========================================================================
# STATUS TRANSITION VALIDATION (DATA-001)
# =========================================================================

VALID_TRANSITIONS = {
    "booked": {"confirmed", "cancelled", "rescheduled", "no_show"},
    "tentative": {"booked", "confirmed", "cancelled"},
    "confirmed": {"reminded", "cancelled", "rescheduled", "no_show", "checked_in"},
    "reminded": {"checked_in", "cancelled", "rescheduled", "no_show"},
    "checked_in": {"completed", "no_show"},
    "completed": set(),
    "no_show": {"rescheduled"},
    "cancelled": set(),
    "rescheduled": set(),
}


def _validate_status_transition(current_status, new_status):
    """Validate that status transition is allowed. Returns True or raises ValueError."""
    current = current_status.value if hasattr(current_status, 'value') else str(current_status).lower()
    new = new_status.value if hasattr(new_status, 'value') else str(new_status).lower()
    allowed = VALID_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ValueError(f"Invalid status transition: {current} -> {new}. Allowed: {sorted(allowed)}")
    return True


# =========================================================================
# UPDATE
# =========================================================================

async def update_appointment(
    db: Session,
    organization_id: int,
    appointment_id: int,
    data: Dict[str, Any],
    requester_user_id: Optional[int] = None,
    *,
    write_audit_log,
    emit_event,
    serialize_appointment,
) -> AppointmentResult:
    """
    Update an appointment. Handles status transitions, rescheduling detection,
    and notification dispatch.

    Args:
        db: SQLAlchemy session.
        organization_id: Tenant ID.
        appointment_id: ID of the appointment to update.
        data: Dict of fields to update (only provided fields are changed).
        requester_user_id: User performing the update.
        write_audit_log: Callback to write an audit log entry.
        emit_event: Callback to emit an event.
        serialize_appointment: Callback to serialize an appointment ORM object.

    Returns:
        AppointmentResult.
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not appointment:
        return AppointmentResult(success=False, error="Appointment not found")

    warnings: List[str] = []
    changes: Dict[str, Dict[str, Any]] = {}
    is_reschedule = False

    # Detect time change (rescheduling)
    new_start = data.get("scheduled_start")
    if new_start:
        if isinstance(new_start, str):
            new_start = datetime.fromisoformat(new_start.replace("Z", "+00:00"))
            if new_start.tzinfo:
                new_start = new_start.replace(tzinfo=None)

        new_duration = data.get("duration_minutes", appointment.duration_minutes)
        new_end = data.get("scheduled_end")
        if new_end and isinstance(new_end, str):
            new_end = datetime.fromisoformat(new_end.replace("Z", "+00:00"))
            if new_end.tzinfo:
                new_end = new_end.replace(tzinfo=None)
        if not new_end:
            new_end = new_start + timedelta(minutes=new_duration)

        assigned = data.get("assigned_user_id", appointment.assigned_user_id)

        # Conflict check for new time (excluding self)
        try:
            _check_conflict_for_update(
                db, organization_id,
                assigned, new_start, new_end,
                exclude_appointment_id=appointment_id,
            )
        except ConflictError as e:
            return AppointmentResult(success=False, error=str(e))

        old_start = appointment.scheduled_start
        if old_start != new_start:
            is_reschedule = True
            changes["scheduled_start"] = {
                "old": old_start.isoformat() if old_start else None,
                "new": new_start.isoformat(),
            }
            appointment.scheduled_start = new_start
            appointment.scheduled_end = new_end
            if "duration_minutes" in data:
                appointment.duration_minutes = new_duration
            appointment.reschedule_count = (appointment.reschedule_count or 0) + 1

    # Handle status changes
    new_status_str = data.get("status")
    if new_status_str:
        new_status = safe_enum_parse("AppointmentStatus", new_status_str, None)
        if new_status:
            # DATA-001: Validate status transition
            try:
                _validate_status_transition(appointment.status, new_status)
            except ValueError as e:
                return AppointmentResult(success=False, error=str(e))

            old_status = appointment.status
            appointment.status = new_status
            appointment.status_changed_at = datetime.now(timezone.utc)
            appointment.status_changed_by = requester_user_id
            changes["status"] = {
                "old": old_status.value if hasattr(old_status, "value") else str(old_status),
                "new": new_status_str,
            }

            if new_status_str == "completed":
                appointment.completed_at = datetime.now(timezone.utc)
            elif new_status_str == "no_show":
                appointment.no_show_at = datetime.now(timezone.utc)
            elif new_status_str == "cancelled":
                appointment.cancelled_at = datetime.now(timezone.utc)
                appointment.cancellation_reason = data.get("cancellation_reason")

    # Apply simple field updates
    simple_fields = [
        "title", "description", "location", "video_link", "phone_number",
        "attendee_name", "attendee_email", "attendee_phone", "attendee_notes",
        "internal_notes", "meeting_notes", "intake_responses",
    ]
    for field_name in simple_fields:
        if field_name in data:
            old_val = getattr(appointment, field_name, None)
            new_val = data[field_name]
            if old_val != new_val:
                setattr(appointment, field_name, new_val)
                changes[field_name] = {"old": str(old_val)[:100], "new": str(new_val)[:100]}

    # Handle meeting_mode
    if "meeting_mode" in data:
        mode = safe_enum_parse("MeetingMode", data["meeting_mode"], None)
        if mode:
            appointment.meeting_mode = mode

    write_audit_log(
        user_id=requester_user_id,
        action="rescheduled" if is_reschedule else "updated",
        entity_type="appointment",
        entity_id=appointment_id,
        changes=changes,
    )
    db.commit()

    # Send update notifications
    send_notification = data.get("send_notification", True)
    if send_notification and is_reschedule and appointment.attendee_email:
        await _send_update_notification(appointment)

    # Emit appropriate event
    event = AppointmentEvent.RESCHEDULED if is_reschedule else AppointmentEvent.UPDATED
    emit_event(event, {
        "appointment_id": appointment_id,
        "changes": changes,
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment_id,
        data=serialize_appointment(appointment),
        warnings=warnings,
        events_emitted=[event.value],
    )


# =========================================================================
# CANCEL
# =========================================================================

async def cancel_appointment(
    db: Session,
    organization_id: int,
    appointment_id: int,
    reason: Optional[str] = None,
    requester_user_id: Optional[int] = None,
    send_notification: bool = True,
    *,
    write_audit_log,
    emit_event,
) -> AppointmentResult:
    """
    Cancel an appointment, notify attendees, and log the cancellation.
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not appointment:
        return AppointmentResult(success=False, error="Appointment not found")

    old_status = appointment.status
    cancelled_status = safe_enum_parse("AppointmentStatus", "cancelled", "cancelled")

    # DATA-001: Validate status transition
    try:
        _validate_status_transition(old_status, cancelled_status)
    except ValueError as e:
        return AppointmentResult(success=False, error=str(e))

    appointment.status = cancelled_status
    appointment.status_changed_at = datetime.now(timezone.utc)
    appointment.status_changed_by = requester_user_id
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = reason

    write_audit_log(
        user_id=requester_user_id,
        action="cancelled",
        entity_type="appointment",
        entity_id=appointment_id,
        changes={
            "status": {
                "old": old_status.value if hasattr(old_status, "value") else str(old_status),
                "new": "cancelled",
            },
            "reason": reason,
        },
    )

    # Log CRM Activity
    _log_activity(
        db, organization_id,
        user_id=requester_user_id or appointment.assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        content=f"Appointment cancelled: {appointment.title}. Reason: {reason or 'Not specified'}",
    )

    db.commit()

    # Send cancellation notifications
    if send_notification and appointment.attendee_email:
        await _send_cancellation_notification(appointment)

    emit_event(AppointmentEvent.CANCELLED, {
        "appointment_id": appointment_id,
        "reason": reason,
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment_id,
        events_emitted=[AppointmentEvent.CANCELLED.value],
    )


# =========================================================================
# RESCHEDULE (atomic cancel + create)
# =========================================================================

async def reschedule_appointment(
    db: Session,
    organization_id: int,
    appointment_id: int,
    new_start: datetime,
    new_duration_minutes: Optional[int] = None,
    requester_user_id: Optional[int] = None,
    *,
    write_audit_log,
    emit_event,
    do_create_appointment,
) -> AppointmentResult:
    """
    Reschedule an appointment atomically: mark old as rescheduled, create new
    record linked to the original.

    Args:
        do_create_appointment: Async callable that creates a new appointment
            (the AppointmentService.create_appointment method).
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    original = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not original:
        return AppointmentResult(success=False, error="Appointment not found")

    if isinstance(new_start, str):
        new_start = datetime.fromisoformat(new_start.replace("Z", "+00:00"))
        if new_start.tzinfo:
            new_start = new_start.replace(tzinfo=None)

    duration = new_duration_minutes or original.duration_minutes
    new_end = new_start + timedelta(minutes=duration)

    # Conflict check for the new time
    try:
        _check_conflict_for_update(
            db, organization_id,
            original.assigned_user_id, new_start, new_end,
            exclude_appointment_id=appointment_id,
        )
    except ConflictError as e:
        return AppointmentResult(success=False, error=str(e))

    # DATA-001: Validate status transition before proceeding
    rescheduled_status = safe_enum_parse("AppointmentStatus", "rescheduled", "rescheduled")
    try:
        _validate_status_transition(original.status, rescheduled_status)
    except ValueError as e:
        return AppointmentResult(success=False, error=str(e))

    # NC2 fix: Create new appointment FIRST, then mark original as rescheduled
    # only on success. This prevents the original being stuck in RESCHEDULED
    # status if the new appointment creation fails.
    new_data = {
        "title": original.title,
        "description": original.description,
        "scheduled_start": new_start,
        "scheduled_end": new_end,
        "duration_minutes": duration,
        "timezone": original.timezone,
        "assigned_user_id": original.assigned_user_id,
        "appointment_type_id": original.appointment_type_id,
        "lead_id": original.lead_id,
        "loan_id": original.loan_id,
        "contact_id": original.contact_id,
        "meeting_type": original.meeting_type.value if hasattr(original.meeting_type, "value") else str(original.meeting_type) if original.meeting_type else None,
        "meeting_mode": original.meeting_mode.value if hasattr(original.meeting_mode, "value") else str(original.meeting_mode) if original.meeting_mode else None,
        "location": original.location,
        "video_link": original.video_link,
        "phone_number": original.phone_number,
        "attendee_name": original.attendee_name,
        "attendee_email": original.attendee_email,
        "attendee_phone": original.attendee_phone,
        "attendee_notes": original.attendee_notes,
        "intake_responses": original.intake_responses,
        "ai_booking_context": original.ai_booking_context,
    }

    result = await do_create_appointment(
        data=new_data,
        source=AppointmentSource.MANUAL_UI,
        requester_user_id=requester_user_id,
    )

    if result.success and result.appointment_id:
        # New appointment created successfully — now safe to mark original
        original.status = rescheduled_status
        original.status_changed_at = datetime.now(timezone.utc)
        original.status_changed_by = requester_user_id

        # TENANT-N06: Link the new appointment to the original, with tenant isolation
        new_appt = db.query(Appointment).filter(
            Appointment.id == result.appointment_id,
            Appointment.organization_id == organization_id,
        ).first()
        if new_appt:
            new_appt.rescheduled_from_id = appointment_id
            new_appt.reschedule_count = (original.reschedule_count or 0) + 1

        write_audit_log(
            user_id=requester_user_id,
            action="rescheduled",
            entity_type="appointment",
            entity_id=appointment_id,
            changes={
                "new_appointment_id": result.appointment_id,
                "old_start": original.scheduled_start.isoformat() if original.scheduled_start else None,
                "new_start": new_start.isoformat(),
            },
        )
        db.commit()

        emit_event(AppointmentEvent.RESCHEDULED, {
            "original_appointment_id": appointment_id,
            "new_appointment_id": result.appointment_id,
        })

        result.events_emitted.append(AppointmentEvent.RESCHEDULED.value)

    return result


# =========================================================================
# CONFIRM
# =========================================================================

async def confirm_appointment(
    db: Session,
    organization_id: int,
    appointment_id: int,
    *,
    emit_event,
) -> AppointmentResult:
    """
    Confirm a booked appointment and send confirmation email.
    Transitions status from booked/tentative to confirmed (auto_confirmed=True).
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not appointment:
        return AppointmentResult(success=False, error="Appointment not found")

    # Only confirm if currently booked or tentative
    current = appointment.status.value if hasattr(appointment.status, "value") else str(appointment.status)
    if current not in ("booked", "tentative"):
        return AppointmentResult(
            success=False,
            error=f"Cannot confirm appointment in '{current}' status",
        )

    confirmed_status = safe_enum_parse("AppointmentStatus", "confirmed", "confirmed")

    # DATA-001: Validate status transition
    try:
        _validate_status_transition(appointment.status, confirmed_status)
    except ValueError as e:
        return AppointmentResult(success=False, error=str(e))

    appointment.status = confirmed_status
    appointment.auto_confirmed = True
    appointment.status_changed_at = datetime.now(timezone.utc)

    db.commit()

    # Send confirmation
    email_sent = False
    if appointment.attendee_email:
        email_sent = await _send_confirmation_email(
            db, appointment, appointment.assigned_user_id,
        )

    emit_event(AppointmentEvent.CONFIRMED, {
        "appointment_id": appointment_id,
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment_id,
        data={"email_sent": email_sent},
        events_emitted=[AppointmentEvent.CONFIRMED.value],
    )


# =========================================================================
# NO-SHOW
# =========================================================================

async def mark_no_show(
    db: Session,
    organization_id: int,
    appointment_id: int,
    *,
    write_audit_log,
    emit_event,
) -> AppointmentResult:
    """
    Mark an appointment as no-show and trigger recovery workflow.
    Creates a high-priority follow-up task.
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not appointment:
        return AppointmentResult(success=False, error="Appointment not found")

    no_show_status = safe_enum_parse("AppointmentStatus", "no_show", "no_show")

    # DATA-001: Validate status transition
    try:
        _validate_status_transition(appointment.status, no_show_status)
    except ValueError as e:
        return AppointmentResult(success=False, error=str(e))

    appointment.status = no_show_status
    appointment.no_show_at = datetime.now(timezone.utc)
    appointment.status_changed_at = datetime.now(timezone.utc)

    # Create high-priority re-engagement task
    _create_followup_task(
        db, organization_id,
        owner_id=appointment.assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        title=f"No-show recovery: {appointment.attendee_name or 'Client'}"[:255],
        description=(
            f"{appointment.attendee_name or 'Client'} missed their appointment "
            f"'{appointment.title}' scheduled for "
            f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p') if appointment.scheduled_start else 'unknown'}. "
            f"Please reach out to reschedule."
        ),
        due_date=datetime.now(timezone.utc) + timedelta(hours=4),
        priority="high",
    )

    _log_activity(
        db, organization_id,
        user_id=appointment.assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        content=f"No-show: {appointment.attendee_name or 'Client'} missed appointment '{appointment.title}'",
    )

    write_audit_log(
        user_id=None,
        action="no_show",
        entity_type="appointment",
        entity_id=appointment_id,
    )

    db.commit()

    emit_event(AppointmentEvent.NO_SHOW, {
        "appointment_id": appointment_id,
        "attendee_name": appointment.attendee_name,
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment_id,
        events_emitted=[AppointmentEvent.NO_SHOW.value],
    )


# =========================================================================
# COMPLETED
# =========================================================================

async def mark_completed(
    db: Session,
    organization_id: int,
    appointment_id: int,
    notes: Optional[str] = None,
    *,
    write_audit_log,
    emit_event,
) -> AppointmentResult:
    """
    Mark an appointment as completed and trigger post-appointment flow.
    Stores meeting notes and logs a CRM activity.
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == organization_id,
    ).first()

    if not appointment:
        return AppointmentResult(success=False, error="Appointment not found")

    completed_status = safe_enum_parse("AppointmentStatus", "completed", "completed")

    # DATA-001: Validate status transition
    try:
        _validate_status_transition(appointment.status, completed_status)
    except ValueError as e:
        return AppointmentResult(success=False, error=str(e))

    appointment.status = completed_status
    appointment.completed_at = datetime.now(timezone.utc)
    appointment.status_changed_at = datetime.now(timezone.utc)

    if notes:
        appointment.meeting_notes = notes

    _log_activity(
        db, organization_id,
        user_id=appointment.assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        content=(
            f"Appointment completed: {appointment.title}. "
            + (f"Notes: {notes[:500]}" if notes else "No notes recorded.")
        ),
    )

    write_audit_log(
        user_id=None,
        action="completed",
        entity_type="appointment",
        entity_id=appointment_id,
        changes={"notes": notes[:200] if notes else None},
    )

    db.commit()

    emit_event(AppointmentEvent.COMPLETED, {
        "appointment_id": appointment_id,
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment_id,
        events_emitted=[AppointmentEvent.COMPLETED.value],
    )
