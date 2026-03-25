"""
Appointment creation logic.

Extracted from AppointmentService to keep the main service file focused.
Contains the full creation flow: validation, conflict checking, lead creation,
CRM activity logging, notification dispatch, and event emission.

This module exposes a single async function that the AppointmentService facade
delegates to. It is NOT meant to be called directly by route handlers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE
from services.appointment._models import (
    AppointmentEvent,
    AppointmentResult,
    AppointmentSource,
    ConflictError,
    DEFAULT_DURATION_MINUTES,
    get_model,
    mask_email,
    safe_enum_parse,
)
from services.appointment.conflict_checker import (
    check_conflict_for_update as _check_conflict_for_update,
    check_duplicate_booking as _check_duplicate_booking,
)
from services.appointment.hold_manager import (
    release_holds_for_slot as _release_holds_for_slot,
)
from services.appointment.crm_bridge import (
    create_followup_task as _create_followup_task,
    ensure_lead as _ensure_lead,
    log_activity as _log_activity,
)
from services.appointment.notifications import (
    create_outlook_event as _create_outlook_event,
    send_confirmation_email as _send_confirmation_email,
)

logger = logging.getLogger(__name__)


async def create_appointment(
    db: Session,
    organization_id: int,
    data: Dict[str, Any],
    source: AppointmentSource = AppointmentSource.MANUAL_UI,
    requester_user_id: Optional[int] = None,
    *,
    write_audit_log,
    emit_event,
    background_tasks=None,
) -> AppointmentResult:
    """
    Create a new appointment with full double-booking prevention.

    Uses SELECT FOR UPDATE with NOWAIT to prevent race conditions.
    Automatically:
    - Links or creates a Lead record for the attendee
    - Logs a CRM Activity
    - Creates a follow-up Task
    - Sends confirmation email + SMS
    - Creates Outlook calendar event
    - Emits CREATED event

    Args:
        db: SQLAlchemy session.
        organization_id: Tenant ID.
        data: Dict with appointment fields. Required: title, scheduled_start,
              duration_minutes. Optional: all Appointment model fields.
        source: Where this booking originated.
        requester_user_id: User performing the action (None for public bookings).
        write_audit_log: Callback to write an audit log entry.
        emit_event: Callback to emit an event.

    Returns:
        AppointmentResult with success status and appointment_id.
    """
    Appointment = get_model("Appointment")
    if not Appointment:
        return AppointmentResult(success=False, error="Appointment model not available")

    # Extract and validate required fields
    title = data.get("title")
    scheduled_start = data.get("scheduled_start")
    duration_minutes = data.get("duration_minutes", DEFAULT_DURATION_MINUTES)

    if not title or not scheduled_start:
        return AppointmentResult(
            success=False,
            error="title and scheduled_start are required",
        )

    if isinstance(scheduled_start, str):
        scheduled_start = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
        if scheduled_start.tzinfo:
            scheduled_start = scheduled_start.replace(tzinfo=None)

    scheduled_end = data.get("scheduled_end")
    if scheduled_end and isinstance(scheduled_end, str):
        scheduled_end = datetime.fromisoformat(scheduled_end.replace("Z", "+00:00"))
        if scheduled_end.tzinfo:
            scheduled_end = scheduled_end.replace(tzinfo=None)
    if not scheduled_end:
        scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)

    assigned_user_id = data.get("assigned_user_id") or requester_user_id
    attendee_email = data.get("attendee_email")
    attendee_name = data.get("attendee_name")
    attendee_phone = data.get("attendee_phone")

    warnings: List[str] = []

    # --- Double-booking prevention via SELECT FOR UPDATE ---
    try:
        _check_conflict_for_update(
            db, organization_id,
            assigned_user_id, scheduled_start, scheduled_end,
            exclude_appointment_id=None,
        )
    except ConflictError as e:
        return AppointmentResult(success=False, error=str(e))

    # --- Duplicate booking detection ---
    if attendee_email and assigned_user_id:
        dup = _check_duplicate_booking(
            db, organization_id,
            attendee_email, assigned_user_id, scheduled_start,
        )
        if dup:
            return AppointmentResult(
                success=False,
                error=f"Duplicate booking detected: existing appointment ID {dup}",
            )

    # --- Parse enum values safely ---
    meeting_type = safe_enum_parse(
        "MeetingType", data.get("meeting_type"), "custom"
    )
    meeting_mode = safe_enum_parse(
        "MeetingMode", data.get("meeting_mode"), "video"
    )

    # --- Create the appointment record ---
    appointment = Appointment(
        organization_id=organization_id,
        appointment_type_id=data.get("appointment_type_id"),
        assigned_user_id=assigned_user_id,
        created_by_user_id=requester_user_id,
        lead_id=data.get("lead_id"),
        loan_id=data.get("loan_id"),
        contact_id=data.get("contact_id"),
        external_id=data.get("external_id"),
        external_source=source.value,
        title=title,
        description=data.get("description"),
        meeting_type=meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=duration_minutes,
        timezone=data.get("timezone", DEFAULT_TIMEZONE),
        location=data.get("location"),
        video_link=data.get("video_link"),
        phone_number=data.get("phone_number"),
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        attendee_notes=data.get("attendee_notes"),
        intake_responses=data.get("intake_responses"),
        status=safe_enum_parse(
            "AppointmentStatus", "booked", "booked"
        ),
        status_changed_at=datetime.now(timezone.utc),
        booked_by_ai=source in (
            AppointmentSource.AI_RECEPTIONIST,
            AppointmentSource.AI_SCHEDULER,
        ),
        ai_booking_context=data.get("ai_booking_context"),
        internal_notes=data.get("internal_notes"),
    )

    db.add(appointment)
    write_audit_log(
        user_id=requester_user_id,
        action="created",
        entity_type="appointment",
        changes={
            "title": title,
            "scheduled_start": scheduled_start.isoformat(),
            "source": source.value,
            "attendee_email": mask_email(attendee_email),
        },
    )
    db.flush()  # Get the ID without committing

    # --- CRM integrations (best-effort, never block the booking) ---

    # Link or create Lead
    if not appointment.lead_id and attendee_email:
        lead_id = _ensure_lead(
            db, organization_id,
            attendee_email, attendee_name, attendee_phone,
            assigned_user_id,
        )
        if lead_id:
            appointment.lead_id = lead_id

    # Log CRM Activity
    _log_activity(
        db, organization_id,
        user_id=requester_user_id or assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        content=(
            f"Appointment scheduled: {title} on "
            f"{scheduled_start.strftime('%m/%d/%Y %I:%M %p')}"
        ),
    )

    # Create follow-up Task
    if appointment.scheduled_end:
        _create_followup_task(
            db, organization_id,
            owner_id=assigned_user_id,
            lead_id=appointment.lead_id,
            loan_id=appointment.loan_id,
            title=f"Follow up after: {title}"[:255],
            description=(
                f"Follow up with {attendee_name or 'attendee'} after "
                f"meeting on {scheduled_start.strftime('%m/%d/%Y')}"
            ),
            due_date=appointment.scheduled_end + timedelta(days=1),
        )

    db.commit()
    db.refresh(appointment)

    # --- Release any holds for this slot ---
    _release_holds_for_slot(
        db, organization_id,
        lo_id=assigned_user_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
    )

    # --- Post-commit notifications (best-effort, background when possible) ---
    # PERF-007: Move notification dispatch to background to avoid blocking
    # the API response on SendGrid/Outlook Graph API latency.
    email_sent = False
    outlook_event_id = None

    if background_tasks is not None:
        # FastAPI BackgroundTasks available -- dispatch after response
        if attendee_email:
            background_tasks.add_task(
                _send_confirmation_email, db, appointment, assigned_user_id,
            )
        if assigned_user_id:
            background_tasks.add_task(
                _create_outlook_event,
                db, appointment, attendee_email, attendee_name, attendee_phone,
            )
    else:
        # Fallback: inline await (e.g. called from AppointmentService directly)
        if attendee_email:
            email_sent = await _send_confirmation_email(
                db, appointment, assigned_user_id,
            )
            if not email_sent:
                warnings.append("Confirmation email could not be sent")

        if assigned_user_id:
            outlook_event_id = await _create_outlook_event(
                db, appointment, attendee_email, attendee_name, attendee_phone,
            )

    # Emit event
    emit_event(AppointmentEvent.CREATED, {
        "appointment_id": appointment.id,
        "source": source.value,
        "lo_id": assigned_user_id,
        "attendee_email": mask_email(attendee_email),
    })

    return AppointmentResult(
        success=True,
        appointment_id=appointment.id,
        data={
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
            "email_sent": email_sent,
            "outlook_event_id": outlook_event_id,
        },
        warnings=warnings,
        events_emitted=[AppointmentEvent.CREATED.value],
    )
