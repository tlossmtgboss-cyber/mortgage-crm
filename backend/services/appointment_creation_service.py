"""
Unified Appointment Creation Service

Single source of truth for creating appointments across all 3 booking paths:
  1. Authenticated UI  (routes/scheduler/appointments.py)
  2. Public booking     (routes/scheduler/public_booking.py)
  3. AI pipeline        (services/pipeline_appointment_trigger.py)

This module consolidates the triplicated appointment creation logic into one
async function that all callers can delegate to.  The caller still owns the
HTTP response shaping and any path-specific side effects (e.g. booking-link
counter increments, confirmation token generation).

Usage:
    from services.appointment_creation_service import create_appointment

    appointment = await create_appointment(
        db=db,
        organization_id=org_id,
        assigned_user_id=lo_id,
        source="public_booking",
        title="Initial Consultation",
        scheduled_start=slot_start,
        scheduled_end=slot_end,
        duration_minutes=30,
        attendee_name="Jane Doe",
        attendee_email="jane@example.com",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _sanitize_and_validate_ai_context(context: Optional[Dict]) -> Optional[Dict]:
    """Validate ai_booking_context at the persistence layer.

    AGENT-002: Delegates to the schema validator in public_booking if available,
    otherwise applies a lightweight inline check.  Returns None if input is None.

    D5-002: Also applies semantic validation to detect hallucinated/unreasonable
    values in AI-generated data (duration, confidence, string lengths).
    """
    if context is None:
        return None
    try:
        from routes.scheduler.public_booking import _sanitize_ai_context
        context = _sanitize_ai_context(context)
    except ImportError:
        # Fallback: if the import fails (e.g. in tests), pass through with a
        # warning — the schema validation is best-effort at this layer.
        logger.warning("Could not import _sanitize_ai_context; passing ai_booking_context through unsanitized")

    # --- D5-002: Semantic validation of AI-generated values ---

    # Clamp duration_minutes to reasonable range (5–480)
    duration = context.get("duration_minutes")
    if duration is not None and (duration < 5 or duration > 480):
        logger.warning("AI context has unreasonable duration_minutes=%s, clamping", duration)
        context["duration_minutes"] = max(5, min(480, duration))

    # Validate confidence_score is between 0 and 1
    score = context.get("confidence_score")
    if score is not None and (score < 0 or score > 1):
        logger.warning("AI context has invalid confidence_score=%s, removing", score)
        context.pop("confidence_score", None)

    # Truncate excessively long string values (>500 chars)
    for key, val in list(context.items()):
        if isinstance(val, str) and len(val) > 500:
            logger.warning("AI context key '%s' exceeds 500 chars, truncating", key)
            context[key] = val[:500]

    return context


# =============================================================================
# RESULT TYPE
# =============================================================================

@dataclass
class AppointmentCreationResult:
    """Standardized result from the unified creation flow.

    Attributes:
        success: True if the appointment was persisted.
        appointment: The ORM Appointment instance (None on failure).
        appointment_id: Convenience shortcut for appointment.id.
        lead_id: Lead record linked or created (None if skipped).
        video_link: Auto-generated meeting link (None if skipped/failed).
        warnings: Non-fatal issues encountered during creation.
        error: Error message if success is False.
    """
    success: bool
    appointment: Any = None
    appointment_id: Optional[int] = None
    lead_id: Optional[int] = None
    video_link: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# MODEL + ENUM HELPERS (lazy imports to avoid circular deps)
# =============================================================================

def _get_appointment_model():
    """Lazy-load the Appointment model."""
    try:
        from services.appointment._models import get_model
        return get_model("Appointment")
    except Exception:
        pass
    # Fallback: load from factory directly
    try:
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base
        models = create_smart_scheduler_models(Base)
        return models.get("Appointment")
    except Exception as e:
        logger.error(f"Cannot load Appointment model: {e}")
        return None


def _get_scheduler_config_model():
    """Lazy-load the SchedulerConfig model."""
    try:
        from services.appointment._models import get_model
        return get_model("SchedulerConfig")
    except Exception:
        pass
    try:
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base
        models = create_smart_scheduler_models(Base)
        return models.get("SchedulerConfig")
    except Exception:
        return None


def _safe_enum_parse(enum_name: str, value: Optional[str], default: Optional[str] = None):
    """Safely parse MeetingType / MeetingMode / AppointmentStatus enums."""
    if value is None and default is None:
        return None
    try:
        from smart_scheduler_models import AppointmentStatus, MeetingType, MeetingMode
        enum_map = {
            "AppointmentStatus": AppointmentStatus,
            "MeetingType": MeetingType,
            "MeetingMode": MeetingMode,
        }
        cls = enum_map.get(enum_name)
        if cls:
            try:
                return cls(value)
            except (ValueError, KeyError):
                if default:
                    return cls(default)
        return value or default
    except ImportError:
        return value or default


def _get_user_timezone(db: Session, user_id: int, org_id: int) -> str:
    """Get user's configured timezone from SchedulerConfig.

    Falls back to DEFAULT_TIMEZONE from scheduler constants if no config is found.
    """
    from routes.scheduler.constants import DEFAULT_TIMEZONE
    SchedulerConfig = _get_scheduler_config_model()
    if SchedulerConfig and user_id:
        try:
            config = (
                db.query(SchedulerConfig)
                .filter(
                    SchedulerConfig.user_id == user_id,
                    SchedulerConfig.organization_id == org_id,
                )
                .first()
            )
            if config and getattr(config, "timezone", None):
                return config.timezone
        except Exception as e:
            logger.debug(f"Could not fetch user timezone: {e}")
    return DEFAULT_TIMEZONE


def _mask_email(email: Optional[str]) -> str:
    """Mask email for safe logging: j***@example.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


# =============================================================================
# CONFLICT CHECKING
# =============================================================================

def _check_internal_conflict(
    db: Session,
    organization_id: int,
    assigned_user_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_appointment_id: Optional[int] = None,
) -> Optional[str]:
    """Check for overlapping appointments using SELECT FOR UPDATE (NOWAIT).

    Returns an error message if a conflict is found, None otherwise.
    Uses SELECT FOR UPDATE with NOWAIT to prevent race-condition double-booking.
    """
    from sqlalchemy import and_
    from sqlalchemy.exc import OperationalError

    Appointment = _get_appointment_model()
    if not Appointment:
        return None  # Cannot check without the model

    try:
        from smart_scheduler_models import AppointmentStatus
        cancelled_values = [AppointmentStatus.CANCELLED.value, "no_show", "cancelled", "completed", "rescheduled"]
    except ImportError:
        cancelled_values = ["cancelled", "no_show", "completed", "rescheduled"]

    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.organization_id == organization_id,
        Appointment.status.notin_(cancelled_values),
        Appointment.scheduled_start < end_time,
        Appointment.scheduled_end > start_time,
    ]
    if exclude_appointment_id is not None:
        filters.append(Appointment.id != exclude_appointment_id)

    try:
        conflict = (
            db.query(Appointment)
            .filter(and_(*filters))
            .with_for_update(nowait=True)
            .first()
        )
    except OperationalError:
        return "This time slot is being booked by another user. Please select a different time."

    if conflict:
        return "This time slot is no longer available. Please select a different time."

    return None


def _check_duplicate(
    db: Session,
    organization_id: int,
    attendee_email: Optional[str],
    assigned_user_id: int,
    start_time: datetime,
    window_minutes: int = 30,
) -> Optional[str]:
    """Check for duplicate booking (same email + LO within a time window).

    Returns an error message if a duplicate is found, None otherwise.
    """
    if not attendee_email:
        return None

    from sqlalchemy import and_

    Appointment = _get_appointment_model()
    if not Appointment:
        return None

    try:
        from smart_scheduler_models import AppointmentStatus
        cancelled_values = [AppointmentStatus.CANCELLED.value, "cancelled"]
    except ImportError:
        cancelled_values = ["cancelled"]

    window_start = start_time - timedelta(minutes=window_minutes)
    window_end = start_time + timedelta(minutes=window_minutes)

    filters = [
        Appointment.attendee_email == attendee_email,
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.organization_id == organization_id,
        Appointment.status.notin_(cancelled_values),
        Appointment.scheduled_start >= window_start,
        Appointment.scheduled_start <= window_end,
    ]

    duplicate = db.query(Appointment).filter(and_(*filters)).first()
    if duplicate:
        logger.info(
            f"Duplicate booking detected: existing appointment {duplicate.id} "
            f"for {_mask_email(attendee_email)}"
        )
        return f"A booking for this email already exists at this time (appointment #{duplicate.id})."

    return None


def _check_daily_capacity(
    db: Session,
    organization_id: int,
    assigned_user_id: int,
    appointment_date: datetime,
    appointment_type_id: Optional[int] = None,
) -> Optional[str]:
    """Check if the user has exceeded their daily appointment capacity.

    Enforces two levels of capacity limits:
      1. Per-type limit: SchedulerAppointmentType.max_per_day (if configured)
      2. Overall user limit: SchedulerConfig.max_meetings_per_day (default 12)

    Returns an error message if capacity is exceeded, None otherwise.
    """
    from sqlalchemy import and_, func
    from datetime import time as _time

    Appointment = _get_appointment_model()
    if not Appointment:
        return None  # Cannot check without the model

    try:
        from smart_scheduler_models import AppointmentStatus
        excluded_statuses = [
            AppointmentStatus.CANCELLED.value,
            AppointmentStatus.NO_SHOW.value,
            AppointmentStatus.RESCHEDULED.value,
        ]
    except ImportError:
        excluded_statuses = ["cancelled", "no_show", "rescheduled"]

    appt_date = appointment_date.date() if hasattr(appointment_date, 'date') else appointment_date
    day_start = datetime.combine(appt_date, _time.min)
    day_end = day_start + timedelta(days=1)
    # Preserve timezone if present on the input
    if hasattr(appointment_date, 'tzinfo') and appointment_date.tzinfo is not None:
        day_start = day_start.replace(tzinfo=appointment_date.tzinfo)
        day_end = day_end.replace(tzinfo=appointment_date.tzinfo)

    base_filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.organization_id == organization_id,
        Appointment.status.notin_(excluded_statuses),
        Appointment.scheduled_start >= day_start,
        Appointment.scheduled_start < day_end,
    ]

    # --- Check 1: Per-type daily limit ---
    if appointment_type_id:
        try:
            from services.appointment._models import get_model
            AppointmentType = get_model("SchedulerAppointmentType")
            if AppointmentType:
                appt_type = db.query(AppointmentType).filter(
                    AppointmentType.id == appointment_type_id,
                    AppointmentType.organization_id == organization_id,
                ).first()
                type_max = getattr(appt_type, 'max_per_day', None) if appt_type else None
                if type_max is not None:
                    type_count = (
                        db.query(func.count(Appointment.id))
                        .filter(and_(
                            *base_filters,
                            Appointment.appointment_type_id == appointment_type_id,
                        ))
                        .scalar()
                    ) or 0
                    if type_count >= type_max:
                        return (
                            f"Daily capacity reached for this appointment type "
                            f"({type_count}/{type_max}). Please choose another day."
                        )
        except Exception as e:
            logger.debug(f"Per-type capacity check skipped: {e}")

    # --- Check 2: Overall user daily limit from SchedulerConfig ---
    overall_max = 12  # Sensible default: prevents unbounded booking
    SchedulerConfig = _get_scheduler_config_model()
    if SchedulerConfig:
        try:
            config = (
                db.query(SchedulerConfig)
                .filter(
                    SchedulerConfig.user_id == assigned_user_id,
                    SchedulerConfig.organization_id == organization_id,
                )
                .first()
            )
            if config and getattr(config, 'max_meetings_per_day', None):
                overall_max = config.max_meetings_per_day
        except Exception as e:
            logger.debug(f"Could not fetch SchedulerConfig for capacity check: {e}")

    total_count = (
        db.query(func.count(Appointment.id))
        .filter(and_(*base_filters))
        .scalar()
    ) or 0

    if total_count >= overall_max:
        return (
            f"Daily appointment capacity reached ({total_count}/{overall_max}). "
            f"Please choose another day."
        )

    return None


def _check_cross_source_conflicts(
    db: Session,
    organization_id: int,
    assigned_user_id: int,
    start_time: datetime,
    end_time: datetime,
) -> Optional[str]:
    """Check cross-source calendar conflicts (legacy table, CalendarEvent, CRM).

    Returns an error message if a conflict is found, None otherwise.
    Non-fatal: failures in individual sources are logged and skipped.
    """
    busy_times: list = []

    # Source 1: ScheduledAppointment (AI-booked legacy table)
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id == assigned_user_id,
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_time,
            SAModel.start_time <= end_time,
        )
        if hasattr(SAModel, "organization_id"):
            sa_query = sa_query.filter(SAModel.organization_id == organization_id)
        for a in sa_query.all():
            if a.start_time and a.end_time:
                busy_times.append((a.start_time, a.end_time))
    except Exception as e:
        logger.debug(f"Legacy ScheduledAppointment cross-source check skipped: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        from database.models.communication import CalendarEvent
        cal_query = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == assigned_user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_time,
            CalendarEvent.start_time <= end_time,
        )
        if hasattr(CalendarEvent, "organization_id"):
            cal_query = cal_query.filter(CalendarEvent.organization_id == organization_id)
        for e in cal_query.all():
            if e.start_time and e.end_time:
                busy_times.append((e.start_time, e.end_time))
    except Exception as ex:
        logger.debug(f"CalendarEvent cross-source check unavailable: {ex}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_query = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == assigned_user_id,
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_time,
            CRMCalendarEvent.start_at <= end_time,
        )
        if hasattr(CRMCalendarEvent, "organization_id"):
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == organization_id)
        for e in crm_query.all():
            if e.start_at and e.end_at:
                busy_times.append((e.start_at, e.end_at))
    except Exception as ex:
        logger.debug(f"CRMCalendarEvent cross-source check unavailable: {ex}")

    # Check for overlap with any busy time
    for busy_start, busy_end in busy_times:
        if start_time < busy_end and end_time > busy_start:
            return "This time slot is no longer available. Please select another time."

    return None


# =============================================================================
# CRM INTEGRATION (best-effort, never blocks the booking)
# =============================================================================

def _ensure_lead(
    db: Session,
    organization_id: int,
    attendee_email: str,
    attendee_name: Optional[str],
    attendee_phone: Optional[str],
    assigned_user_id: int,
) -> Optional[int]:
    """Find or create a Lead record for the booking attendee. Returns lead_id."""
    if not attendee_email:
        return None

    try:
        from database.models.lead_loan import Lead
    except ImportError:
        logger.debug("Lead model not available, skipping lead creation")
        return None

    try:
        existing = db.query(Lead).filter(
            Lead.email == attendee_email,
            Lead.organization_id == organization_id,
        ).first()

        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            logger.info(
                f"Linked booking to existing lead {existing.id} "
                f"({_mask_email(attendee_email)})"
            )
            return existing.id

        # Parse name into first/last
        name_parts = (attendee_name or "").strip().split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        new_lead = Lead(
            organization_id=organization_id,
            name=attendee_name or attendee_email,
            first_name=first_name,
            last_name=last_name,
            email=attendee_email,
            phone=attendee_phone,
            stage="New",
            source="scheduler",
            owner_id=assigned_user_id,
            last_contact=datetime.now(timezone.utc),
            lead_received_date=datetime.now(timezone.utc),
        )
        db.add(new_lead)
        db.flush()  # Get the ID without committing

        from services.client_file_service import ensure_client_file
        ensure_client_file(db, new_lead)

        logger.info(
            f"Created new lead {new_lead.id} from booking "
            f"({_mask_email(attendee_email)})"
        )
        return new_lead.id

    except Exception as e:
        logger.error(f"Failed to ensure lead for booking: {e}")
        return None


def _log_appointment_activity(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    lead_id: Optional[int],
    loan_id: Optional[int],
    content: str,
) -> None:
    """Log an appointment-related activity to the CRM Activity table."""
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        activity = Activity(
            organization_id=organization_id,
            type=ActivityType.MEETING,
            content=content[:2000],
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=user_id,
        )
        db.add(activity)
        logger.debug(f"Activity logged: {content[:80]}")
    except ImportError:
        logger.debug("Activity model not available, skipping activity log")
    except Exception as e:
        logger.error(f"Failed to log appointment activity: {e}")


def _create_followup_task(
    db: Session,
    organization_id: int,
    owner_id: Optional[int],
    lead_id: Optional[int],
    loan_id: Optional[int],
    title: str,
    description: str,
    due_date: datetime,
    priority: str = "medium",
) -> None:
    """Create a follow-up task linked to a lead/loan."""
    try:
        from database.models.task import Task

        task = Task(
            organization_id=organization_id,
            title=title[:255],
            description=description[:2000],
            status="pending",
            priority=priority,
            due_date=due_date,
            owner_id=owner_id,
            lead_id=lead_id,
            loan_id=loan_id,
        )
        db.add(task)
        logger.info(f"Follow-up task created: {title[:80]}")
    except ImportError:
        logger.debug("Task model not available, skipping task creation")
    except Exception as e:
        logger.error(f"Failed to create follow-up task: {e}")


# =============================================================================
# MEETING LINK GENERATION
# =============================================================================

async def _generate_meeting_link(
    db: Session,
    appointment,
    user_id: Optional[int],
    org_id: int,
) -> Optional[str]:
    """Auto-generate a virtual meeting link for video appointments.

    Returns the meeting join URL on success, None otherwise.
    """
    try:
        from services.virtual_meeting_service import create_meeting_for_appointment
        meeting_result = await create_meeting_for_appointment(
            db=db,
            appointment=appointment,
            provider="auto",
            user_id=user_id or appointment.assigned_user_id,
            org_id=org_id,
        )
        if meeting_result.success:
            logger.info(
                f"Auto-generated meeting link for appointment {appointment.id}: "
                f"provider={meeting_result.provider}, url={meeting_result.join_url}"
            )
            return meeting_result.join_url
    except Exception as e:
        logger.warning(
            f"Could not auto-generate meeting link for appointment "
            f"{getattr(appointment, 'id', '?')}: {e}"
        )
    return None


# =============================================================================
# AUDIT LOGGING (delegates to shared _audit_log from scheduler helpers)
# =============================================================================

def _write_audit_log(
    db,
    organization_id: int,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    changes: Optional[dict] = None,
) -> None:
    """Write an audit log entry — delegates to the shared _audit_log."""
    try:
        from routes.scheduler._audit import _audit_log
        _audit_log(
            db, org_id=organization_id, user_id=user_id,
            action=action, entity_type=entity_type,
            entity_id=entity_id, changes=changes,
        )
    except ImportError:
        # Fallback if scheduler helpers aren't available
        try:
            from services.appointment._models import get_model
            AuditLog = get_model("SchedulerAuditLog")
            if not AuditLog:
                return
            entry = AuditLog(
                organization_id=organization_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
            )
            db.add(entry)
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")


# =============================================================================
# MAIN API: create_appointment
# =============================================================================

async def create_appointment(
    db: Session,
    *,
    organization_id: int,
    assigned_user_id: int,
    created_by_user_id: Optional[int] = None,
    source: str,  # "authenticated", "public_booking", "ai_pipeline"
    # ---- appointment fields ----
    title: str,
    scheduled_start: datetime,
    scheduled_end: datetime,
    duration_minutes: int,
    timezone: Optional[str] = None,  # Uses user's SchedulerConfig TZ if not provided
    attendee_name: Optional[str] = None,
    attendee_email: Optional[str] = None,
    attendee_phone: Optional[str] = None,
    # ---- optional fields ----
    appointment_type_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    description: Optional[str] = None,
    meeting_type: Optional[str] = None,
    meeting_mode: Optional[str] = None,
    intake_responses: Optional[dict] = None,
    attendee_notes: Optional[str] = None,
    booked_by_ai: bool = False,
    ai_booking_context: Optional[dict] = None,
    internal_notes: Optional[str] = None,
    external_source: Optional[str] = None,
    # ---- control flags ----
    check_conflicts: bool = True,
    check_cross_source: bool = True,
    check_capacity: bool = True,
    generate_meeting_link: bool = True,
    send_confirmation: bool = True,
    create_lead_if_missing: bool = False,
    auto_commit: bool = True,
) -> AppointmentCreationResult:
    """Create an appointment through the unified path.

    All 3 booking paths (authenticated, public, AI pipeline) converge here.
    The caller controls which optional steps run via the control-flag kwargs.

    Steps performed:
      1. Resolve timezone from SchedulerConfig if not provided.
      2. Check for internal conflicts (SELECT FOR UPDATE).
      3. Check for duplicate bookings (same email + LO + time window).
      4. Optionally check cross-source calendar conflicts.
      5. Check daily capacity limits (per-type and overall user limit).
      6. Create the Appointment ORM instance and flush (get ID).
      7. Optionally generate a virtual meeting link.
      8. Optionally create or link a Lead record.
      9. Log a CRM Activity for the appointment.
     10. Create a follow-up Task.
     11. Write an audit log entry.
     12. Commit the transaction (unless auto_commit=False).
     13. Return the result with the persisted appointment.

    The caller is responsible for:
      - Sending confirmation emails / SMS (path-specific templates and fallbacks)
      - Creating Outlook/Google calendar events (path-specific logic)
      - Incrementing booking-link counters (public path only)
      - Generating confirmation tokens (public path only)
      - Enterprise audit logging via scheduler_audit (authenticated path only)
      - Any HTTP response shaping

    Args:
        db: Active SQLAlchemy session. Commits unless auto_commit=False.
        organization_id: Tenant ID (required for multi-tenant isolation).
        assigned_user_id: LO or team member the appointment is assigned to.
        created_by_user_id: User who initiated the booking (None for public/AI).
        source: Origin identifier for audit trail.
        title: Appointment title.
        scheduled_start: UTC datetime for appointment start.
        scheduled_end: UTC datetime for appointment end.
        duration_minutes: Duration in minutes.
        timezone: IANA timezone string. If None, looked up from SchedulerConfig.
        attendee_name: Name of the person being met with.
        attendee_email: Email of the attendee (used for dedup, lead linking).
        attendee_phone: Phone of the attendee.
        appointment_type_id: FK to scheduler_appointment_types.
        lead_id: FK to leads (pre-linked).
        loan_id: FK to loans (pre-linked).
        contact_id: FK to contacts (pre-linked).
        description: Free-text description.
        meeting_type: MeetingType enum value string (e.g. "custom", "review_call").
        meeting_mode: MeetingMode enum value string (e.g. "video", "phone", "in_person").
        intake_responses: Dict of intake form responses from public booking.
        attendee_notes: Notes provided by the attendee.
        booked_by_ai: True if this appointment was created by an AI system.
        ai_booking_context: Dict of AI context metadata.
        internal_notes: Internal-only notes (not shown to attendee).
        external_source: External origin label (e.g. "booking_link", "pipeline_stage_change").
        check_conflicts: If True, run SELECT FOR UPDATE conflict check + duplicate check.
        check_cross_source: If True, also check legacy, CalendarEvent, CRM sources.
        check_capacity: If True, enforce daily capacity limits (per-type max_per_day
            and overall SchedulerConfig.max_meetings_per_day, default 12).
        generate_meeting_link: If True, auto-generate meeting link for video appointments.
        send_confirmation: Reserved for future use (callers currently handle this).
        create_lead_if_missing: If True, create/link a Lead record for the attendee.
        auto_commit: If True (default), commit the transaction after creation.
            Set to False when the caller manages its own transaction (e.g. pipeline
            trigger, which writes additional log entries before committing).

    Returns:
        AppointmentCreationResult with the persisted appointment or error details.
    """
    warnings: List[str] = []

    # -------------------------------------------------------------------------
    # 1. Resolve timezone
    # -------------------------------------------------------------------------
    resolved_timezone = (
        timezone
        if timezone
        else _get_user_timezone(db, assigned_user_id, organization_id)
    )

    # -------------------------------------------------------------------------
    # 2. Internal conflict check (SELECT FOR UPDATE + NOWAIT)
    # -------------------------------------------------------------------------
    if check_conflicts:
        conflict_error = _check_internal_conflict(
            db, organization_id, assigned_user_id,
            scheduled_start, scheduled_end,
        )
        if conflict_error:
            return AppointmentCreationResult(success=False, error=conflict_error)

        # Duplicate booking check
        dup_error = _check_duplicate(
            db, organization_id, attendee_email,
            assigned_user_id, scheduled_start,
        )
        if dup_error:
            return AppointmentCreationResult(success=False, error=dup_error)

    # -------------------------------------------------------------------------
    # 3. Cross-source conflict check (optional)
    # -------------------------------------------------------------------------
    if check_conflicts and check_cross_source:
        cross_error = _check_cross_source_conflicts(
            db, organization_id, assigned_user_id,
            scheduled_start, scheduled_end,
        )
        if cross_error:
            # Cross-source failures are warnings, not blockers, unless a real
            # conflict is detected (cross_error is non-None only on real conflict)
            return AppointmentCreationResult(success=False, error=cross_error)

    # -------------------------------------------------------------------------
    # 4. Daily capacity check (per-type and overall user limit)
    # -------------------------------------------------------------------------
    if check_capacity:
        capacity_error = _check_daily_capacity(
            db, organization_id, assigned_user_id,
            scheduled_start, appointment_type_id,
        )
        if capacity_error:
            return AppointmentCreationResult(success=False, error=capacity_error)

    # -------------------------------------------------------------------------
    # 5. Parse enums
    # -------------------------------------------------------------------------
    parsed_meeting_type = _safe_enum_parse("MeetingType", meeting_type, "custom")
    parsed_meeting_mode = _safe_enum_parse("MeetingMode", meeting_mode, "video")
    parsed_status = _safe_enum_parse("AppointmentStatus", "booked", "booked")

    # -------------------------------------------------------------------------
    # 6. Create Appointment model instance
    # -------------------------------------------------------------------------
    Appointment = _get_appointment_model()
    if not Appointment:
        return AppointmentCreationResult(
            success=False,
            error="Appointment model is not available",
        )

    appointment = Appointment(
        organization_id=organization_id,
        appointment_type_id=appointment_type_id,
        assigned_user_id=assigned_user_id,
        created_by_user_id=created_by_user_id,
        lead_id=lead_id,
        loan_id=loan_id,
        contact_id=contact_id,
        title=title,
        description=description,
        meeting_type=parsed_meeting_type,
        meeting_mode=parsed_meeting_mode,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=duration_minutes,
        timezone=resolved_timezone,
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        attendee_notes=attendee_notes,
        intake_responses=intake_responses,
        status=parsed_status,
        status_changed_at=datetime.now(timezone_module_utc()),
        booked_by_ai=booked_by_ai,
        ai_booking_context=_sanitize_and_validate_ai_context(ai_booking_context),
        internal_notes=internal_notes,
        external_source=external_source,
    )

    db.add(appointment)

    # Write audit log for the creation
    _write_audit_log(
        db, organization_id, created_by_user_id,
        action="created",
        entity_type="appointment",
        changes={
            "title": title,
            "attendee_email": _mask_email(attendee_email),
            "scheduled_start": scheduled_start.isoformat(),
            "source": source,
        },
    )

    db.flush()  # Get appointment.id without committing

    # Backfill entity_id in the audit log now that we have it
    _write_audit_log(
        db, organization_id, created_by_user_id,
        action="_id_backfill",
        entity_type="appointment",
        entity_id=appointment.id,
    )

    logger.info(
        f"Appointment created: {appointment.id} by "
        f"{'user ' + str(created_by_user_id) if created_by_user_id else source} "
        f"for org {organization_id}"
    )

    # -------------------------------------------------------------------------
    # 7. Auto-generate meeting link for video appointments
    # -------------------------------------------------------------------------
    video_link = None
    if generate_meeting_link and parsed_meeting_mode:
        mode_value = (
            parsed_meeting_mode.value
            if hasattr(parsed_meeting_mode, "value")
            else str(parsed_meeting_mode)
        )
        if mode_value.lower() == "video" and not getattr(appointment, "video_link", None):
            video_link = await _generate_meeting_link(
                db, appointment,
                user_id=created_by_user_id or assigned_user_id,
                org_id=organization_id,
            )
            if not video_link:
                warnings.append("Could not auto-generate meeting link")

    # -------------------------------------------------------------------------
    # 8. CRM: Create or link Lead
    # -------------------------------------------------------------------------
    linked_lead_id = lead_id
    if create_lead_if_missing and not appointment.lead_id and attendee_email:
        linked_lead_id = _ensure_lead(
            db, organization_id,
            attendee_email, attendee_name, attendee_phone,
            assigned_user_id,
        )
        if linked_lead_id:
            appointment.lead_id = linked_lead_id

    # -------------------------------------------------------------------------
    # 9. CRM: Log activity
    # -------------------------------------------------------------------------
    _log_appointment_activity(
        db, organization_id,
        user_id=created_by_user_id or assigned_user_id,
        lead_id=appointment.lead_id,
        loan_id=appointment.loan_id,
        content=(
            f"Appointment scheduled: {title} on "
            f"{scheduled_start.strftime('%m/%d/%Y %I:%M %p')}"
        ),
    )

    # -------------------------------------------------------------------------
    # 10. CRM: Create follow-up task
    # -------------------------------------------------------------------------
    if scheduled_end:
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
            due_date=scheduled_end + timedelta(days=1),
        )

    # -------------------------------------------------------------------------
    # 11. Schedule reminders for the appointment
    # -------------------------------------------------------------------------
    _schedule_reminders(db, appointment, organization_id)

    # -------------------------------------------------------------------------
    # 12. Commit the transaction (unless caller manages its own)
    # -------------------------------------------------------------------------
    if auto_commit:
        db.commit()
        db.refresh(appointment)

    # -------------------------------------------------------------------------
    # 13. Push to Outlook via .ics email invite (best-effort, non-blocking)
    # -------------------------------------------------------------------------
    try:
        import os
        outlook_email = os.environ.get("OUTLOOK_SYNC_EMAIL", "")
        if outlook_email:
            from services.outlook_calendar_sync import push_appointment_to_outlook
            result = await push_appointment_to_outlook(db, appointment, outlook_email)
            if not result.get("success"):
                logger.debug("Outlook .ics sync skipped: %s", result.get("error", ""))
    except Exception as exc:
        logger.debug("Outlook .ics sync error (non-fatal): %s", exc)

    return AppointmentCreationResult(
        success=True,
        appointment=appointment,
        appointment_id=appointment.id,
        lead_id=appointment.lead_id,
        video_link=video_link,
        warnings=warnings,
    )


# =============================================================================
# REMINDER SCHEDULING
# =============================================================================

def _schedule_reminders(
    db: Session,
    appointment,
    organization_id: int,
) -> None:
    """Schedule default reminders (24h and 1h before) for a newly created appointment.

    Creates AppointmentReminder records that the reminder service will pick up
    and send at the scheduled times. Non-fatal: failures are logged but do not
    block appointment creation.
    """
    try:
        from services.appointment._models import get_model
        AppointmentReminder = get_model("AppointmentReminder")
        if not AppointmentReminder:
            logger.debug("AppointmentReminder model not available, skipping reminder scheduling")
            return

        from datetime import timezone as _tz

        # Determine reminder schedule: use appointment type's schedule or default [24, 1]
        reminder_hours = [24, 1]
        if appointment.appointment_type_id:
            try:
                AppointmentType = get_model("SchedulerAppointmentType")
                if AppointmentType:
                    appt_type = db.query(AppointmentType).filter(
                        AppointmentType.id == appointment.appointment_type_id,
                    ).first()
                    if appt_type and getattr(appt_type, "reminder_schedule", None):
                        reminder_hours = appt_type.reminder_schedule
            except Exception:
                pass  # Use default

        scheduled_start = appointment.scheduled_start
        if not scheduled_start:
            return

        for hours_before in reminder_hours:
            remind_at = scheduled_start - timedelta(hours=hours_before)
            # Don't schedule reminders in the past
            now = datetime.now(_tz.utc)
            if remind_at <= now:
                continue

            reminder = AppointmentReminder(
                appointment_id=appointment.id,
                organization_id=organization_id,
                channel="email",
                scheduled_at=remind_at,
                status="pending",
                hours_before=hours_before,
            )
            db.add(reminder)

            # Also schedule SMS reminder if attendee has a phone number
            if appointment.attendee_phone:
                sms_reminder = AppointmentReminder(
                    appointment_id=appointment.id,
                    organization_id=organization_id,
                    channel="sms",
                    scheduled_at=remind_at,
                    status="pending",
                    hours_before=hours_before,
                )
                db.add(sms_reminder)

        logger.info(
            f"Scheduled reminders for appointment {appointment.id}: "
            f"{reminder_hours} hours before"
        )
    except Exception as e:
        logger.error(f"Failed to schedule reminders for appointment: {e}")


# =============================================================================
# INTERNAL: timezone.utc workaround
# =============================================================================
# We use `timezone` as a parameter name, which shadows the stdlib import.
# This helper provides access to datetime.timezone.utc inside the function body.

def timezone_module_utc():
    """Return datetime.timezone.utc (avoids shadowing by the `timezone` kwarg)."""
    from datetime import timezone as _tz
    return _tz.utc
