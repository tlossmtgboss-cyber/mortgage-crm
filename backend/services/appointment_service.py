"""
AppointmentService -- Single source of truth for ALL appointment operations.

Every path that creates, reads, updates, or checks appointments goes through here:
- Public booking page
- AI receptionist (Vapi)
- AI scheduler agent
- Manual calendar UI
- Google/Outlook sync
- API integrations

This service handles:
- Cross-source availability checking
- Double-booking prevention (SELECT FOR UPDATE)
- Buffer time enforcement
- Capacity limits
- Soft holds (TTL-based slot reservation during AI conversations)
- LO routing
- Notification dispatch
- Conversion tracking

Usage:
    from services.appointment_service import AppointmentService

    service = AppointmentService(db=db, organization_id=org_id)

    slots = await service.get_available_slots(
        lo_id=42,
        start_date=date(2026, 3, 15),
        end_date=date(2026, 3, 20),
    )

    appointment = await service.create_appointment(
        data={...},
        source="public_booking",
        requester_user_id=None,  # unauthenticated public booking
    )
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, date, time, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# TYPES AND CONSTANTS
# =============================================================================

class AppointmentSource(str, Enum):
    """Where an appointment operation originated."""
    MANUAL_UI = "manual_ui"
    PUBLIC_BOOKING = "public_booking"
    AI_RECEPTIONIST = "ai_receptionist"
    AI_SCHEDULER = "ai_scheduler"
    GOOGLE_SYNC = "google_sync"
    OUTLOOK_SYNC = "outlook_sync"
    SALESFORCE_SYNC = "salesforce_sync"
    API = "api"


class AppointmentEvent(str, Enum):
    """Events emitted by the service for downstream consumers."""
    CREATED = "appointment.created"
    CONFIRMED = "appointment.confirmed"
    UPDATED = "appointment.updated"
    CANCELLED = "appointment.cancelled"
    RESCHEDULED = "appointment.rescheduled"
    NO_SHOW = "appointment.no_show"
    COMPLETED = "appointment.completed"
    HOLD_CREATED = "appointment.hold_created"
    HOLD_RELEASED = "appointment.hold_released"
    HOLD_EXPIRED = "appointment.hold_expired"
    CONVERSION_TRACKED = "appointment.conversion_tracked"


# Active statuses that occupy calendar time
_ACTIVE_STATUSES = ("booked", "tentative", "confirmed")
_TERMINAL_STATUSES = ("cancelled", "no_show", "completed", "rescheduled")

# Default buffer times in minutes
_DEFAULT_BUFFER_BEFORE = 5
_DEFAULT_BUFFER_AFTER = 5
_DEFAULT_MIN_NOTICE_HOURS = 2
_DEFAULT_DURATION_MINUTES = 30
_DEFAULT_HOLD_TTL_SECONDS = 300  # 5 minutes
_MAX_DATE_RANGE_DAYS = 90


@dataclass
class SlotHold:
    """A soft hold on a time slot during an AI conversation."""
    hold_id: str
    lo_id: int
    organization_id: int
    start_time: datetime
    end_time: datetime
    created_at: datetime
    expires_at: datetime
    source: str
    released: bool = False


@dataclass
class ConflictCheckResult:
    """Result of a cross-source conflict check."""
    has_conflict: bool
    conflicting_source: Optional[str] = None
    conflicting_event_id: Optional[str] = None
    message: str = ""


@dataclass
class AppointmentResult:
    """Standardized result from appointment operations."""
    success: bool
    appointment_id: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    events_emitted: List[str] = field(default_factory=list)


# =============================================================================
# DEFAULT WORKING HOURS (matches smart_scheduler_models.py)
# =============================================================================

_DEFAULT_WORKING_HOURS = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
}


# =============================================================================
# IN-MEMORY HOLD STORE
# =============================================================================
# In production with multiple workers, replace with Redis.
# The service checks expiry on every access so stale holds are harmless.

import threading

_holds_lock = threading.Lock()
_active_holds: Dict[str, SlotHold] = {}


def _cleanup_expired_holds() -> int:
    """Remove expired holds. Returns count removed."""
    now = datetime.now(timezone.utc)
    expired_ids = [
        hid for hid, hold in _active_holds.items()
        if hold.expires_at <= now or hold.released
    ]
    for hid in expired_ids:
        del _active_holds[hid]
    return len(expired_ids)


# =============================================================================
# MODEL LAZY LOADER
# =============================================================================

_models_cache: Dict[str, Any] = {}


def _get_model(name: str):
    """Lazy-load scheduler and CRM models to avoid circular imports."""
    if name in _models_cache:
        return _models_cache[name]

    model = None

    # Try smart_scheduler_models factory first (the canonical scheduler models)
    if name in (
        "Appointment", "SchedulerConfig", "AvailabilitySlot",
        "BlockedTime", "AppointmentType", "BookingLink",
        "AppointmentReminder", "SchedulerAuditLog", "RoutingRule",
    ):
        try:
            from smart_scheduler_models import create_smart_scheduler_models
            from db import Base
            models = create_smart_scheduler_models(Base)
            # Cache all of them at once
            for k, v in models.items():
                _models_cache[k] = v
            model = _models_cache.get(name)
        except Exception as e:
            logger.debug(f"Could not load scheduler models via factory: {e}")

    # ScheduledAppointment (AI-booked, legacy table)
    if name == "ScheduledAppointment" and model is None:
        try:
            from services.smart_scheduler_service import ScheduledAppointment
            model = ScheduledAppointment
        except Exception as e:
            logger.debug(f"ScheduledAppointment model not available: {e}")

    # CalendarEvent (manual calendar)
    if name == "CalendarEvent" and model is None:
        try:
            import main
            model = main.CalendarEvent
        except Exception as e:
            logger.debug(f"CalendarEvent model not available: {e}")

    # CRMCalendarEvent (Salesforce-synced)
    if name == "CRMCalendarEvent" and model is None:
        try:
            from models.calendar_sync_models import CRMCalendarEvent
            model = CRMCalendarEvent
        except Exception as e:
            logger.debug(f"CRMCalendarEvent model not available: {e}")

    # Lead
    if name == "Lead" and model is None:
        try:
            from database.models.lead_loan import Lead
            model = Lead
        except Exception as e:
            logger.debug(f"Lead model not available: {e}")

    # User
    if name == "User" and model is None:
        try:
            from database.models.core import User
            model = User
        except Exception as e:
            logger.debug(f"User model not available: {e}")

    # Activity
    if name == "Activity" and model is None:
        try:
            from database.models.communication import Activity
            model = Activity
        except Exception as e:
            logger.debug(f"Activity model not available: {e}")

    # Task
    if name == "Task" and model is None:
        try:
            from database.models.task import Task
            model = Task
        except Exception as e:
            logger.debug(f"Task model not available: {e}")

    if model is not None:
        _models_cache[name] = model
    return model


# =============================================================================
# APPOINTMENT SERVICE
# =============================================================================

class AppointmentService:
    """
    Unified service for all appointment operations.

    Enforces:
    - Tenant isolation (organization_id on every query)
    - Double-booking prevention (SELECT FOR UPDATE with NOWAIT)
    - Cross-source conflict detection (scheduler_appointments + Google + Outlook + Salesforce)
    - Buffer time enforcement between appointments
    - Capacity limits per LO per day
    - Soft holds with automatic TTL expiry
    - Audit logging for all mutations
    - Event emission for downstream consumers
    """

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self._emitted_events: List[Dict[str, Any]] = []

    # =========================================================================
    # AVAILABILITY
    # =========================================================================

    async def get_available_slots(
        self,
        lo_id: int,
        start_date: date,
        end_date: date,
        timezone_str: str = "America/Chicago",
        duration_minutes: int = _DEFAULT_DURATION_MINUTES,
        source: AppointmentSource = AppointmentSource.MANUAL_UI,
        meeting_type: Optional[str] = None,
        exclude_appointment_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute available time slots for an LO, checking ALL calendar sources.

        Cross-source conflict check includes:
        1. scheduler_appointments table (main appointment records)
        2. ScheduledAppointment table (AI-booked legacy)
        3. CalendarEvent table (manual calendar entries)
        4. CRMCalendarEvent table (Salesforce-synced events)
        5. Active soft holds (in-memory)
        6. Blocked times (PTO, holidays, focus time)

        Args:
            lo_id: The loan officer's user_id.
            start_date: Start of the date range.
            end_date: End of the date range.
            timezone_str: IANA timezone for display.
            duration_minutes: Slot duration in minutes.
            source: Where this request originated.
            meeting_type: Optional filter by appointment type.
            exclude_appointment_id: Exclude this appointment from conflict check
                (used during rescheduling to avoid self-conflict).

        Returns:
            Sorted list of slot dicts with keys: start, end, date, day.
        """
        if (end_date - start_date).days > _MAX_DATE_RANGE_DAYS:
            raise ValueError(f"Date range cannot exceed {_MAX_DATE_RANGE_DAYS} days")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        Appointment = _get_model("Appointment")
        SchedulerConfig = _get_model("SchedulerConfig")
        BlockedTime = _get_model("BlockedTime")

        if not Appointment or not SchedulerConfig or not BlockedTime:
            logger.error("Required scheduler models not available")
            return []

        # Load LO config
        config = self.db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == lo_id,
            SchedulerConfig.organization_id == self.organization_id,
        ).first()

        working_hours = config.working_hours if config else _DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else _DEFAULT_BUFFER_BEFORE
        buffer_after = config.buffer_after_minutes if config else _DEFAULT_BUFFER_AFTER
        min_notice = config.min_notice_hours if config else _DEFAULT_MIN_NOTICE_HOURS
        max_per_day = config.max_meetings_per_day if config else None
        enforce_lunch = getattr(config, "enforce_lunch_break", True) if config else True
        lunch_start_t = getattr(config, "lunch_break_start", time(12, 0)) if config else time(12, 0)
        lunch_end_t = getattr(config, "lunch_break_end", time(13, 0)) if config else time(13, 0)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        min_booking_time = now + timedelta(hours=min_notice)
        range_start_dt = datetime.combine(start_date, time.min)
        range_end_dt = datetime.combine(end_date, time.max)

        # Gather ALL busy times from every source
        busy_times = self._get_all_busy_times(
            lo_id, range_start_dt, range_end_dt,
            exclude_appointment_id=exclude_appointment_id,
        )

        # Query blocked times
        blocked = self.db.query(BlockedTime).filter(
            BlockedTime.is_active == True,  # noqa: E712
            BlockedTime.organization_id == self.organization_id,
            or_(
                BlockedTime.user_id == lo_id,
                BlockedTime.applies_to_all_users == True,  # noqa: E712
            ),
            BlockedTime.start_datetime <= range_end_dt,
            BlockedTime.end_datetime >= range_start_dt,
        ).all()

        # Count existing appointments per day for capacity checks
        day_counts: Dict[date, int] = {}
        for busy_start, busy_end in busy_times:
            d = busy_start.date() if isinstance(busy_start, datetime) else busy_start
            day_counts[d] = day_counts.get(d, 0) + 1

        # Generate slots day by day
        slots: List[Dict[str, Any]] = []
        current_d = start_date

        while current_d <= end_date:
            day_name = current_d.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_d += timedelta(days=1)
                continue

            # Check daily capacity
            if max_per_day and day_counts.get(current_d, 0) >= max_per_day:
                current_d += timedelta(days=1)
                continue

            # Parse working hours
            try:
                work_start = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                work_end = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_d += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_d, work_start)
            day_end = datetime.combine(current_d, work_end)
            lunch_start_dt = datetime.combine(current_d, lunch_start_t) if enforce_lunch else None
            lunch_end_dt = datetime.combine(current_d, lunch_end_t) if enforce_lunch else None

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Skip past or too-soon slots
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Skip lunch break
                if lunch_start_dt and lunch_end_dt:
                    if slot_start < lunch_end_dt and slot_end > lunch_start_dt:
                        slot_start += timedelta(minutes=30)
                        continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked
                )
                if is_blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check cross-source busy times (with buffers)
                has_conflict = self._slot_conflicts_with_busy(
                    slot_start, slot_end, busy_times,
                    buffer_before, buffer_after,
                )

                # Check soft holds
                if not has_conflict:
                    has_conflict = self._slot_conflicts_with_holds(
                        lo_id, slot_start, slot_end,
                    )

                if not has_conflict:
                    slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "date": current_d.isoformat(),
                        "day": day_name,
                        "duration_minutes": duration_minutes,
                    })

                slot_start += timedelta(minutes=30)

            current_d += timedelta(days=1)

        # Deduplicate by start time and sort
        unique = list({s["start"]: s for s in slots}.values())
        unique.sort(key=lambda x: x["start"])
        return unique

    # =========================================================================
    # CREATE
    # =========================================================================

    async def create_appointment(
        self,
        data: Dict[str, Any],
        source: AppointmentSource = AppointmentSource.MANUAL_UI,
        requester_user_id: Optional[int] = None,
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
            data: Dict with appointment fields. Required: title, scheduled_start,
                  duration_minutes. Optional: all Appointment model fields.
            source: Where this booking originated.
            requester_user_id: User performing the action (None for public bookings).

        Returns:
            AppointmentResult with success status and appointment_id.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        # Extract and validate required fields
        title = data.get("title")
        scheduled_start = data.get("scheduled_start")
        duration_minutes = data.get("duration_minutes", _DEFAULT_DURATION_MINUTES)

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
            self._check_conflict_for_update(
                assigned_user_id, scheduled_start, scheduled_end,
                exclude_appointment_id=None,
            )
        except ConflictError as e:
            return AppointmentResult(success=False, error=str(e))

        # --- Duplicate booking detection ---
        if attendee_email and assigned_user_id:
            dup = self._check_duplicate_booking(
                attendee_email, assigned_user_id, scheduled_start,
            )
            if dup:
                return AppointmentResult(
                    success=False,
                    error=f"Duplicate booking detected: existing appointment ID {dup}",
                )

        # --- Parse enum values safely ---
        meeting_type = self._safe_enum_parse(
            "MeetingType", data.get("meeting_type"), "custom"
        )
        meeting_mode = self._safe_enum_parse(
            "MeetingMode", data.get("meeting_mode"), "video"
        )

        # --- Create the appointment record ---
        appointment = Appointment(
            organization_id=self.organization_id,
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
            timezone=data.get("timezone", "America/Chicago"),
            location=data.get("location"),
            video_link=data.get("video_link"),
            phone_number=data.get("phone_number"),
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            attendee_notes=data.get("attendee_notes"),
            intake_responses=data.get("intake_responses"),
            status=self._safe_enum_parse(
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

        self.db.add(appointment)
        self._write_audit_log(
            user_id=requester_user_id,
            action="created",
            entity_type="appointment",
            changes={
                "title": title,
                "scheduled_start": scheduled_start.isoformat(),
                "source": source.value,
                "attendee_email": self._mask_email(attendee_email),
            },
        )
        self.db.flush()  # Get the ID without committing

        # --- CRM integrations (best-effort, never block the booking) ---

        # Link or create Lead
        if not appointment.lead_id and attendee_email:
            lead_id = self._ensure_lead(
                attendee_email, attendee_name, attendee_phone,
                assigned_user_id,
            )
            if lead_id:
                appointment.lead_id = lead_id

        # Log CRM Activity
        self._log_activity(
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
            self._create_followup_task(
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

        self.db.commit()
        self.db.refresh(appointment)

        # --- Release any holds for this slot ---
        self._release_holds_for_slot(
            lo_id=assigned_user_id,
            start_time=scheduled_start,
            end_time=scheduled_end,
        )

        # --- Post-commit notifications (best-effort) ---
        email_sent = False
        outlook_event_id = None

        if attendee_email:
            email_sent = await self._send_confirmation_email(
                appointment, assigned_user_id,
            )
            if not email_sent:
                warnings.append("Confirmation email could not be sent")

        if assigned_user_id:
            outlook_event_id = await self._create_outlook_event(
                appointment, attendee_email, attendee_name, attendee_phone,
            )

        # Emit event
        self._emit_event(AppointmentEvent.CREATED, {
            "appointment_id": appointment.id,
            "source": source.value,
            "lo_id": assigned_user_id,
            "attendee_email": self._mask_email(attendee_email),
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

    # =========================================================================
    # READ
    # =========================================================================

    async def get_appointment(self, appointment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single appointment by ID with tenant isolation.

        Returns None if not found or not in this organization.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return None

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return None

        return self._serialize_appointment(appointment)

    async def list_appointments(
        self,
        user_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List appointments with filters and pagination. Always scoped to organization.

        Args:
            user_id: Filter by assigned_user_id or created_by_user_id.
            start_date: Filter appointments starting on or after this date.
            end_date: Filter appointments starting on or before this date.
            status: Filter by AppointmentStatus value.
            lead_id: Filter by linked lead.
            loan_id: Filter by linked loan.
            limit: Max results (capped at 200).
            offset: Pagination offset.

        Returns:
            Dict with keys: appointments (list), total, limit, offset.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return {"appointments": [], "total": 0, "limit": limit, "offset": offset}

        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        query = self.db.query(Appointment).filter(
            Appointment.organization_id == self.organization_id,
        )

        if user_id is not None:
            query = query.filter(
                or_(
                    Appointment.assigned_user_id == user_id,
                    Appointment.created_by_user_id == user_id,
                )
            )

        if start_date:
            query = query.filter(
                Appointment.scheduled_start >= datetime.combine(start_date, time.min)
            )
        if end_date:
            query = query.filter(
                Appointment.scheduled_start <= datetime.combine(end_date, time.max)
            )

        if status:
            status_enum = self._safe_enum_parse("AppointmentStatus", status, None)
            if status_enum:
                query = query.filter(Appointment.status == status_enum)

        if lead_id is not None:
            query = query.filter(Appointment.lead_id == lead_id)
        if loan_id is not None:
            query = query.filter(Appointment.loan_id == loan_id)

        total = query.count()
        appointments = (
            query.order_by(Appointment.scheduled_start.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "appointments": [self._serialize_appointment(a) for a in appointments],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # =========================================================================
    # UPDATE
    # =========================================================================

    async def update_appointment(
        self,
        appointment_id: int,
        data: Dict[str, Any],
        requester_user_id: Optional[int] = None,
    ) -> AppointmentResult:
        """
        Update an appointment. Handles status transitions, rescheduling detection,
        and notification dispatch.

        Args:
            appointment_id: ID of the appointment to update.
            data: Dict of fields to update (only provided fields are changed).
            requester_user_id: User performing the update.

        Returns:
            AppointmentResult.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
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
                self._check_conflict_for_update(
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
            new_status = self._safe_enum_parse("AppointmentStatus", new_status_str, None)
            if new_status:
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
            mode = self._safe_enum_parse("MeetingMode", data["meeting_mode"], None)
            if mode:
                appointment.meeting_mode = mode

        self._write_audit_log(
            user_id=requester_user_id,
            action="rescheduled" if is_reschedule else "updated",
            entity_type="appointment",
            entity_id=appointment_id,
            changes=changes,
        )
        self.db.commit()

        # Send update notifications
        send_notification = data.get("send_notification", True)
        if send_notification and is_reschedule and appointment.attendee_email:
            await self._send_update_notification(appointment)

        # Emit appropriate event
        event = AppointmentEvent.RESCHEDULED if is_reschedule else AppointmentEvent.UPDATED
        self._emit_event(event, {
            "appointment_id": appointment_id,
            "changes": changes,
        })

        return AppointmentResult(
            success=True,
            appointment_id=appointment_id,
            data=self._serialize_appointment(appointment),
            warnings=warnings,
            events_emitted=[event.value],
        )

    # =========================================================================
    # CANCEL
    # =========================================================================

    async def cancel_appointment(
        self,
        appointment_id: int,
        reason: Optional[str] = None,
        requester_user_id: Optional[int] = None,
        send_notification: bool = True,
    ) -> AppointmentResult:
        """
        Cancel an appointment, notify attendees, and log the cancellation.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        old_status = appointment.status
        cancelled_status = self._safe_enum_parse("AppointmentStatus", "cancelled", "cancelled")

        appointment.status = cancelled_status
        appointment.status_changed_at = datetime.now(timezone.utc)
        appointment.status_changed_by = requester_user_id
        appointment.cancelled_at = datetime.now(timezone.utc)
        appointment.cancellation_reason = reason

        self._write_audit_log(
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
        self._log_activity(
            user_id=requester_user_id or appointment.assigned_user_id,
            lead_id=appointment.lead_id,
            loan_id=appointment.loan_id,
            content=f"Appointment cancelled: {appointment.title}. Reason: {reason or 'Not specified'}",
        )

        self.db.commit()

        # Send cancellation notifications
        if send_notification and appointment.attendee_email:
            await self._send_cancellation_notification(appointment)

        self._emit_event(AppointmentEvent.CANCELLED, {
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
        self,
        appointment_id: int,
        new_start: datetime,
        new_duration_minutes: Optional[int] = None,
        requester_user_id: Optional[int] = None,
    ) -> AppointmentResult:
        """
        Reschedule an appointment atomically: mark old as rescheduled, create new
        record linked to the original.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        original = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
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
            self._check_conflict_for_update(
                original.assigned_user_id, new_start, new_end,
                exclude_appointment_id=appointment_id,
            )
        except ConflictError as e:
            return AppointmentResult(success=False, error=str(e))

        # Mark original as rescheduled
        rescheduled_status = self._safe_enum_parse("AppointmentStatus", "rescheduled", "rescheduled")
        original.status = rescheduled_status
        original.status_changed_at = datetime.now(timezone.utc)
        original.status_changed_by = requester_user_id

        # Create new appointment linked to original
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

        result = await self.create_appointment(
            data=new_data,
            source=AppointmentSource.MANUAL_UI,
            requester_user_id=requester_user_id,
        )

        if result.success and result.appointment_id:
            # Link the new appointment to the original
            new_appt = self.db.query(Appointment).filter(
                Appointment.id == result.appointment_id,
            ).first()
            if new_appt:
                new_appt.rescheduled_from_id = appointment_id
                new_appt.reschedule_count = (original.reschedule_count or 0) + 1
                self.db.commit()

            self._write_audit_log(
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
            self.db.commit()

        self._emit_event(AppointmentEvent.RESCHEDULED, {
            "original_appointment_id": appointment_id,
            "new_appointment_id": result.appointment_id,
        })

        result.events_emitted.append(AppointmentEvent.RESCHEDULED.value)
        return result

    # =========================================================================
    # CONFIRM
    # =========================================================================

    async def confirm_appointment(self, appointment_id: int) -> AppointmentResult:
        """
        Confirm a booked appointment and send confirmation email.
        Transitions status from booked/tentative to confirmed (auto_confirmed=True).
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
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

        booked_status = self._safe_enum_parse("AppointmentStatus", "booked", "booked")
        appointment.status = booked_status
        appointment.auto_confirmed = True
        appointment.status_changed_at = datetime.now(timezone.utc)

        self.db.commit()

        # Send confirmation
        email_sent = False
        if appointment.attendee_email:
            email_sent = await self._send_confirmation_email(
                appointment, appointment.assigned_user_id,
            )

        self._emit_event(AppointmentEvent.CONFIRMED, {
            "appointment_id": appointment_id,
        })

        return AppointmentResult(
            success=True,
            appointment_id=appointment_id,
            data={"email_sent": email_sent},
            events_emitted=[AppointmentEvent.CONFIRMED.value],
        )

    # =========================================================================
    # SOFT HOLDS
    # =========================================================================

    async def hold_slot(
        self,
        lo_id: int,
        start_time: datetime,
        duration_minutes: int = _DEFAULT_DURATION_MINUTES,
        ttl_seconds: int = _DEFAULT_HOLD_TTL_SECONDS,
        source: str = "ai_conversation",
    ) -> Dict[str, Any]:
        """
        Create a soft hold on a time slot during an AI conversation.

        Holds are TTL-based and automatically expire. They prevent other
        callers from seeing the slot as available but do not create a
        database record. In production, replace in-memory store with Redis.

        Args:
            lo_id: Loan officer user_id.
            start_time: Proposed appointment start.
            duration_minutes: Slot duration.
            ttl_seconds: Time-to-live in seconds (default 5 minutes).
            source: Description of the hold requester.

        Returns:
            Dict with hold_id and expiry info.
        """
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if start_time.tzinfo:
                start_time = start_time.replace(tzinfo=None)

        end_time = start_time + timedelta(minutes=duration_minutes)
        now = datetime.now(timezone.utc)

        hold = SlotHold(
            hold_id=str(uuid_lib.uuid4()),
            lo_id=lo_id,
            organization_id=self.organization_id,
            start_time=start_time,
            end_time=end_time,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            source=source,
        )

        with _holds_lock:
            _cleanup_expired_holds()
            _active_holds[hold.hold_id] = hold

        logger.info(
            f"Slot hold created: {hold.hold_id} for LO {lo_id} "
            f"at {start_time.isoformat()}, TTL={ttl_seconds}s"
        )

        self._emit_event(AppointmentEvent.HOLD_CREATED, {
            "hold_id": hold.hold_id,
            "lo_id": lo_id,
            "start_time": start_time.isoformat(),
            "ttl_seconds": ttl_seconds,
        })

        return {
            "hold_id": hold.hold_id,
            "lo_id": lo_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "expires_at": hold.expires_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        }

    async def release_hold(self, hold_id: str) -> bool:
        """
        Release a soft hold. Returns True if the hold existed and was released.
        """
        with _holds_lock:
            hold = _active_holds.get(hold_id)
            if hold and hold.organization_id == self.organization_id:
                hold.released = True
                del _active_holds[hold_id]
                logger.info(f"Slot hold released: {hold_id}")
                self._emit_event(AppointmentEvent.HOLD_RELEASED, {"hold_id": hold_id})
                return True
        return False

    # =========================================================================
    # CONFLICT CHECK (public API)
    # =========================================================================

    async def check_conflict(
        self,
        lo_id: int,
        start: datetime,
        end: datetime,
    ) -> ConflictCheckResult:
        """
        Check for conflicts across ALL calendar sources for a proposed time slot.

        Sources checked:
        1. scheduler_appointments (with SELECT FOR UPDATE)
        2. ScheduledAppointment (AI-booked legacy)
        3. CalendarEvent (manual calendar)
        4. CRMCalendarEvent (Salesforce-synced)
        5. Active soft holds
        """
        if isinstance(start, str):
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if start.tzinfo:
                start = start.replace(tzinfo=None)
        if isinstance(end, str):
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end.tzinfo:
                end = end.replace(tzinfo=None)

        # Check main appointment table
        Appointment = _get_model("Appointment")
        if Appointment:
            conflict = self.db.query(Appointment).filter(
                Appointment.assigned_user_id == lo_id,
                Appointment.organization_id == self.organization_id,
                Appointment.status.notin_(_TERMINAL_STATUSES),
                Appointment.scheduled_start < end,
                Appointment.scheduled_end > start,
            ).first()
            if conflict:
                return ConflictCheckResult(
                    has_conflict=True,
                    conflicting_source="scheduler_appointments",
                    conflicting_event_id=str(conflict.id),
                    message=f"Conflicts with appointment #{conflict.id}: {conflict.title}",
                )

        # Check all other sources
        busy = self._get_all_busy_times(lo_id, start, end)
        for busy_start, busy_end in busy:
            if start < busy_end and end > busy_start:
                return ConflictCheckResult(
                    has_conflict=True,
                    conflicting_source="cross_source",
                    message="Conflicts with an existing calendar event",
                )

        # Check soft holds
        if self._slot_conflicts_with_holds(lo_id, start, end):
            return ConflictCheckResult(
                has_conflict=True,
                conflicting_source="soft_hold",
                message="This slot is temporarily held by another booking in progress",
            )

        return ConflictCheckResult(has_conflict=False)

    # =========================================================================
    # STATUS TRANSITIONS
    # =========================================================================

    async def mark_no_show(self, appointment_id: int) -> AppointmentResult:
        """
        Mark an appointment as no-show and trigger recovery workflow.
        Creates a high-priority follow-up task.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        no_show_status = self._safe_enum_parse("AppointmentStatus", "no_show", "no_show")
        appointment.status = no_show_status
        appointment.no_show_at = datetime.now(timezone.utc)
        appointment.status_changed_at = datetime.now(timezone.utc)

        # Create high-priority re-engagement task
        self._create_followup_task(
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

        self._log_activity(
            user_id=appointment.assigned_user_id,
            lead_id=appointment.lead_id,
            loan_id=appointment.loan_id,
            content=f"No-show: {appointment.attendee_name or 'Client'} missed appointment '{appointment.title}'",
        )

        self._write_audit_log(
            user_id=None,
            action="no_show",
            entity_type="appointment",
            entity_id=appointment_id,
        )

        self.db.commit()

        self._emit_event(AppointmentEvent.NO_SHOW, {
            "appointment_id": appointment_id,
            "attendee_name": appointment.attendee_name,
        })

        return AppointmentResult(
            success=True,
            appointment_id=appointment_id,
            events_emitted=[AppointmentEvent.NO_SHOW.value],
        )

    async def mark_completed(
        self,
        appointment_id: int,
        notes: Optional[str] = None,
    ) -> AppointmentResult:
        """
        Mark an appointment as completed and trigger post-appointment flow.
        Stores meeting notes and logs a CRM activity.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        completed_status = self._safe_enum_parse("AppointmentStatus", "completed", "completed")
        appointment.status = completed_status
        appointment.completed_at = datetime.now(timezone.utc)
        appointment.status_changed_at = datetime.now(timezone.utc)

        if notes:
            appointment.meeting_notes = notes

        self._log_activity(
            user_id=appointment.assigned_user_id,
            lead_id=appointment.lead_id,
            loan_id=appointment.loan_id,
            content=(
                f"Appointment completed: {appointment.title}. "
                + (f"Notes: {notes[:500]}" if notes else "No notes recorded.")
            ),
        )

        self._write_audit_log(
            user_id=None,
            action="completed",
            entity_type="appointment",
            entity_id=appointment_id,
            changes={"notes": notes[:200] if notes else None},
        )

        self.db.commit()

        self._emit_event(AppointmentEvent.COMPLETED, {
            "appointment_id": appointment_id,
        })

        return AppointmentResult(
            success=True,
            appointment_id=appointment_id,
            events_emitted=[AppointmentEvent.COMPLETED.value],
        )

    # =========================================================================
    # CONVERSION TRACKING
    # =========================================================================

    async def track_conversion(
        self,
        appointment_id: int,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
    ) -> AppointmentResult:
        """
        Link an appointment to a lead/loan for conversion tracking.
        This allows measuring: booking -> lead -> loan -> funded pipeline.
        """
        Appointment = _get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        changes: Dict[str, Any] = {}

        if lead_id is not None and appointment.lead_id != lead_id:
            changes["lead_id"] = {"old": appointment.lead_id, "new": lead_id}
            appointment.lead_id = lead_id

        if loan_id is not None and appointment.loan_id != loan_id:
            changes["loan_id"] = {"old": appointment.loan_id, "new": loan_id}
            appointment.loan_id = loan_id

        if changes:
            self._write_audit_log(
                user_id=None,
                action="conversion_tracked",
                entity_type="appointment",
                entity_id=appointment_id,
                changes=changes,
            )
            self.db.commit()

        self._emit_event(AppointmentEvent.CONVERSION_TRACKED, {
            "appointment_id": appointment_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
        })

        return AppointmentResult(
            success=True,
            appointment_id=appointment_id,
            data={"lead_id": appointment.lead_id, "loan_id": appointment.loan_id},
            events_emitted=[AppointmentEvent.CONVERSION_TRACKED.value],
        )

    # =========================================================================
    # PRIVATE: CROSS-SOURCE BUSY TIME AGGREGATION
    # =========================================================================

    def _get_all_busy_times(
        self,
        lo_id: int,
        range_start: datetime,
        range_end: datetime,
        exclude_appointment_id: Optional[int] = None,
    ) -> List[Tuple[datetime, datetime]]:
        """
        Aggregate busy times from ALL calendar sources for an LO.

        Sources:
        1. scheduler_appointments (main table)
        2. ScheduledAppointment (AI-booked legacy table)
        3. CalendarEvent (manual calendar entries)
        4. CRMCalendarEvent (Salesforce-synced events)
        """
        busy: List[Tuple[datetime, datetime]] = []

        # Source 1: scheduler_appointments
        Appointment = _get_model("Appointment")
        if Appointment:
            try:
                filters = [
                    Appointment.assigned_user_id == lo_id,
                    Appointment.organization_id == self.organization_id,
                    Appointment.status.notin_(list(_TERMINAL_STATUSES)),
                    Appointment.scheduled_start <= range_end,
                    Appointment.scheduled_end >= range_start,
                ]
                if exclude_appointment_id:
                    filters.append(Appointment.id != exclude_appointment_id)

                appts = self.db.query(Appointment).filter(and_(*filters)).all()
                for a in appts:
                    if a.scheduled_start and a.scheduled_end:
                        busy.append((a.scheduled_start, a.scheduled_end))
            except Exception as e:
                logger.warning(f"Error querying scheduler_appointments: {e}")

        # Source 2: ScheduledAppointment (AI-booked)
        SAModel = _get_model("ScheduledAppointment")
        if SAModel:
            try:
                sa_query = self.db.query(SAModel).filter(
                    SAModel.loan_officer_id == lo_id,
                    SAModel.status.in_(["scheduled", "confirmed"]),
                    SAModel.start_time >= range_start,
                    SAModel.start_time <= range_end,
                )
                if hasattr(SAModel, "organization_id"):
                    sa_query = sa_query.filter(
                        SAModel.organization_id == self.organization_id,
                    )
                for a in sa_query.all():
                    if a.start_time and a.end_time:
                        busy.append((a.start_time, a.end_time))
            except Exception as e:
                logger.debug(f"ScheduledAppointment query unavailable: {e}")

        # Source 3: CalendarEvent (manual calendar)
        CalendarEvent = _get_model("CalendarEvent")
        if CalendarEvent:
            try:
                ce_query = self.db.query(CalendarEvent).filter(
                    CalendarEvent.user_id == lo_id,
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.start_time >= range_start,
                    CalendarEvent.start_time <= range_end,
                )
                if hasattr(CalendarEvent, "organization_id"):
                    ce_query = ce_query.filter(
                        CalendarEvent.organization_id == self.organization_id,
                    )
                for e in ce_query.all():
                    if e.start_time and e.end_time:
                        busy.append((e.start_time, e.end_time))
            except Exception as e:
                logger.debug(f"CalendarEvent query unavailable: {e}")

        # Source 4: CRMCalendarEvent (Salesforce-synced)
        CRMCalendarEvent = _get_model("CRMCalendarEvent")
        if CRMCalendarEvent:
            try:
                crm_query = self.db.query(CRMCalendarEvent).filter(
                    CRMCalendarEvent.owner_user_id == lo_id,
                    CRMCalendarEvent.status != "canceled",
                    CRMCalendarEvent.start_at >= range_start,
                    CRMCalendarEvent.start_at <= range_end,
                )
                if hasattr(CRMCalendarEvent, "organization_id"):
                    crm_query = crm_query.filter(
                        CRMCalendarEvent.organization_id == self.organization_id,
                    )
                for e in crm_query.all():
                    if e.start_at and e.end_at:
                        busy.append((e.start_at, e.end_at))
            except Exception as e:
                logger.debug(f"CRMCalendarEvent query unavailable: {e}")

        return busy

    def _slot_conflicts_with_busy(
        self,
        slot_start: datetime,
        slot_end: datetime,
        busy_times: List[Tuple[datetime, datetime]],
        buffer_before: int = 0,
        buffer_after: int = 0,
    ) -> bool:
        """Check if a proposed slot conflicts with any busy time (including buffers)."""
        for busy_start, busy_end in busy_times:
            buffered_start = busy_start - timedelta(minutes=buffer_before)
            buffered_end = busy_end + timedelta(minutes=buffer_after)
            if slot_start < buffered_end and slot_end > buffered_start:
                return True
        return False

    def _slot_conflicts_with_holds(
        self,
        lo_id: int,
        slot_start: datetime,
        slot_end: datetime,
    ) -> bool:
        """Check if a proposed slot conflicts with any active soft hold."""
        now = datetime.now(timezone.utc)
        with _holds_lock:
            for hold in _active_holds.values():
                if hold.released or hold.expires_at <= now:
                    continue
                if (
                    hold.lo_id == lo_id
                    and hold.organization_id == self.organization_id
                    and slot_start < hold.end_time
                    and slot_end > hold.start_time
                ):
                    return True
        return False

    # =========================================================================
    # PRIVATE: DOUBLE-BOOKING PREVENTION
    # =========================================================================

    def _check_conflict_for_update(
        self,
        assigned_user_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
        exclude_appointment_id: Optional[int] = None,
    ) -> None:
        """
        SELECT FOR UPDATE with NOWAIT to prevent double-booking.
        Raises ConflictError if a conflict exists or the row is locked.
        """
        if not assigned_user_id:
            return

        Appointment = _get_model("Appointment")
        if not Appointment:
            return

        filters = [
            Appointment.assigned_user_id == assigned_user_id,
            Appointment.organization_id == self.organization_id,
            Appointment.status.notin_(list(_TERMINAL_STATUSES)),
            Appointment.scheduled_start < end_time,
            Appointment.scheduled_end > start_time,
        ]
        if exclude_appointment_id is not None:
            filters.append(Appointment.id != exclude_appointment_id)

        try:
            conflict = (
                self.db.query(Appointment)
                .filter(and_(*filters))
                .with_for_update(nowait=True)
                .first()
            )
        except OperationalError:
            raise ConflictError(
                "This time slot is being booked by another user. "
                "Please select a different time."
            )

        if conflict:
            raise ConflictError(
                "This time slot is no longer available. "
                "Please select a different time."
            )

    def _check_duplicate_booking(
        self,
        attendee_email: str,
        assigned_user_id: int,
        start_time: datetime,
        window_minutes: int = 30,
    ) -> Optional[int]:
        """
        Check for duplicate booking (same email + LO within a time window).
        Returns conflicting appointment ID or None.
        """
        Appointment = _get_model("Appointment")
        if not Appointment or not attendee_email:
            return None

        window_start = start_time - timedelta(minutes=window_minutes)
        window_end = start_time + timedelta(minutes=window_minutes)

        duplicate = self.db.query(Appointment).filter(
            Appointment.attendee_email == attendee_email,
            Appointment.assigned_user_id == assigned_user_id,
            Appointment.organization_id == self.organization_id,
            Appointment.status.notin_(list(_TERMINAL_STATUSES)),
            Appointment.scheduled_start >= window_start,
            Appointment.scheduled_start <= window_end,
        ).first()

        return duplicate.id if duplicate else None

    # =========================================================================
    # PRIVATE: HOLD MANAGEMENT
    # =========================================================================

    def _release_holds_for_slot(
        self,
        lo_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Release all holds that overlap with a booked slot. Returns count released."""
        released = 0
        with _holds_lock:
            to_remove = []
            for hold_id, hold in _active_holds.items():
                if (
                    hold.lo_id == lo_id
                    and hold.organization_id == self.organization_id
                    and not hold.released
                    and start_time < hold.end_time
                    and end_time > hold.start_time
                ):
                    to_remove.append(hold_id)

            for hold_id in to_remove:
                _active_holds[hold_id].released = True
                del _active_holds[hold_id]
                released += 1

        if released:
            logger.info(f"Released {released} holds for slot {start_time.isoformat()}")
        return released

    # =========================================================================
    # PRIVATE: CRM INTEGRATIONS
    # =========================================================================

    def _ensure_lead(
        self,
        email: str,
        name: Optional[str],
        phone: Optional[str],
        assigned_user_id: Optional[int],
    ) -> Optional[int]:
        """Find or create a Lead record for a booking attendee. Returns lead_id."""
        Lead = _get_model("Lead")
        if not Lead or not email:
            return None

        try:
            existing = self.db.query(Lead).filter(
                Lead.email == email,
                Lead.organization_id == self.organization_id,
            ).first()

            if existing:
                existing.last_contact = datetime.now(timezone.utc)
                logger.info(f"Linked booking to existing lead {existing.id}")
                return existing.id

            name_parts = (name or "").strip().split(None, 1)
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            new_lead = Lead(
                organization_id=self.organization_id,
                name=name or email,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                stage="New",
                source="scheduler",
                owner_id=assigned_user_id,
                last_contact=datetime.now(timezone.utc),
                lead_received_date=datetime.now(timezone.utc),
            )
            self.db.add(new_lead)
            self.db.flush()
            logger.info(f"Created new lead {new_lead.id} from booking")
            return new_lead.id
        except Exception as e:
            logger.error(f"Failed to ensure lead for booking: {e}")
            return None

    def _log_activity(
        self,
        user_id: Optional[int],
        lead_id: Optional[int],
        loan_id: Optional[int],
        content: str,
        activity_type: str = "Meeting",
    ) -> None:
        """Log appointment-related activity to CRM Activity table."""
        Activity = _get_model("Activity")
        if not Activity:
            return

        try:
            from database.enums import ActivityType
            type_map = {
                "Meeting": ActivityType.MEETING,
                "Note": ActivityType.NOTE,
                "Email": ActivityType.EMAIL,
            }
            activity = Activity(
                organization_id=self.organization_id,
                type=type_map.get(activity_type, ActivityType.MEETING),
                content=content[:2000],
                lead_id=lead_id,
                loan_id=loan_id,
                user_id=user_id,
            )
            self.db.add(activity)
        except Exception as e:
            logger.debug(f"Could not log activity: {e}")

    def _create_followup_task(
        self,
        owner_id: Optional[int],
        lead_id: Optional[int],
        loan_id: Optional[int],
        title: str,
        description: str,
        due_date: datetime,
        priority: str = "medium",
    ) -> None:
        """Create a follow-up task linked to a lead/loan."""
        Task = _get_model("Task")
        if not Task:
            return

        try:
            task = Task(
                organization_id=self.organization_id,
                title=title[:255],
                description=description[:2000],
                status="pending",
                priority=priority,
                due_date=due_date,
                owner_id=owner_id,
                lead_id=lead_id,
                loan_id=loan_id,
            )
            self.db.add(task)
        except Exception as e:
            logger.debug(f"Could not create followup task: {e}")

    # =========================================================================
    # PRIVATE: NOTIFICATIONS
    # =========================================================================

    async def _send_confirmation_email(
        self,
        appointment,
        assigned_user_id: Optional[int],
    ) -> bool:
        """Send confirmation email to attendee. Returns True on success."""
        try:
            from scheduler_email_service import (
                send_appointment_confirmation_email,
                generate_reschedule_url,
            )

            # Format display values
            appt_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
            appt_time = appointment.scheduled_start.strftime("%I:%M %p")
            duration_str = f"{appointment.duration_minutes} minutes"

            mode_display = {
                "video": "Video Call",
                "phone": "Phone Call",
                "in_person": "In Person",
                "screen_share": "Screen Share",
            }
            raw_mode = (
                appointment.meeting_mode.value
                if hasattr(appointment.meeting_mode, "value")
                else str(appointment.meeting_mode or "phone")
            )
            meeting_mode_str = mode_display.get(raw_mode.lower(), "Phone Call")

            # Get team member info
            team_member_name = None
            team_member_email = None
            if assigned_user_id:
                User = _get_model("User")
                if User:
                    user = self.db.query(User).filter(User.id == assigned_user_id).first()
                    if user:
                        team_member_name = user.first_name
                        if user.last_name:
                            team_member_name += f" {user.last_name}"
                        team_member_email = user.email

            reschedule_url = generate_reschedule_url(
                appointment.id, appointment.attendee_email,
            )

            result = send_appointment_confirmation_email(
                attendee_email=appointment.attendee_email,
                attendee_name=appointment.attendee_name or "there",
                appointment_title=appointment.title,
                appointment_date=appt_date,
                appointment_time=appt_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                team_member_name=team_member_name,
                team_member_email=team_member_email,
                video_link=appointment.video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes,
                reschedule_url=reschedule_url,
            )

            success = result.get("success", False) if isinstance(result, dict) else bool(result)
            if success:
                logger.info(
                    f"Confirmation email sent for appointment {appointment.id}"
                )
            else:
                logger.warning(
                    f"Confirmation email failed for appointment {appointment.id}: "
                    f"{result.get('error', 'unknown') if isinstance(result, dict) else 'unknown'}"
                )
            return success
        except Exception as e:
            logger.error(f"Error sending confirmation email: {e}")
            return False

    async def _send_update_notification(self, appointment) -> bool:
        """Send update/reschedule notification to attendee."""
        try:
            from scheduler_email_service import send_appointment_update_email

            appt_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
            appt_time = appointment.scheduled_start.strftime("%I:%M %p")
            duration_str = f"{appointment.duration_minutes} minutes"

            result = send_appointment_update_email(
                attendee_email=appointment.attendee_email,
                attendee_name=appointment.attendee_name or "there",
                appointment_title=appointment.title,
                new_date=appt_date,
                new_time=appt_time,
                duration=duration_str,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes,
            )

            return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception as e:
            logger.error(f"Error sending update notification: {e}")
            return False

    async def _send_cancellation_notification(self, appointment) -> bool:
        """Send cancellation notification to attendee."""
        try:
            from scheduler_email_service import send_appointment_cancellation_email

            result = send_appointment_cancellation_email(
                attendee_email=appointment.attendee_email,
                attendee_name=appointment.attendee_name or "there",
                appointment_title=appointment.title,
                appointment_date=appointment.scheduled_start.strftime("%A, %B %d, %Y"),
                appointment_time=appointment.scheduled_start.strftime("%I:%M %p"),
                cancellation_reason=appointment.cancellation_reason,
            )

            return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception as e:
            logger.error(f"Error sending cancellation notification: {e}")
            return False

    async def _create_outlook_event(
        self,
        appointment,
        attendee_email: Optional[str],
        attendee_name: Optional[str],
        attendee_phone: Optional[str],
    ) -> Optional[str]:
        """Create an Outlook calendar event. Returns event_id or None."""
        try:
            import html as html_mod
            from services.microsoft_graph import create_event_via_graph, CalendarResult

            mode_display = {
                "video": "Video Call",
                "phone": "Phone Call",
                "in_person": "In Person",
                "screen_share": "Screen Share",
            }
            mode_val = (
                appointment.meeting_mode.value
                if hasattr(appointment.meeting_mode, "value")
                else str(appointment.meeting_mode or "phone")
            )
            meeting_mode_str = mode_display.get(mode_val.lower(), "Phone Call")

            description = (
                f"<h3>Client Meeting</h3>"
                f"<p><strong>Client:</strong> {html_mod.escape(attendee_name or 'Not specified')}</p>"
                f"<p><strong>Email:</strong> {html_mod.escape(attendee_email or 'Not specified')}</p>"
                f"<p><strong>Phone:</strong> {html_mod.escape(attendee_phone or 'Not specified')}</p>"
                f"<p><strong>Meeting Type:</strong> {html_mod.escape(meeting_mode_str)}</p>"
            )
            if appointment.description:
                description += f"<p><strong>Notes:</strong> {html_mod.escape(appointment.description)}</p>"
            if appointment.video_link:
                description += (
                    f"<p><strong>Video Link:</strong> "
                    f"<a href='{html_mod.escape(appointment.video_link)}'>"
                    f"{html_mod.escape(appointment.video_link)}</a></p>"
                )

            calendar_result: CalendarResult = await create_event_via_graph(
                user_id=appointment.assigned_user_id,
                subject=f"Meeting: {attendee_name or 'Client'} - {appointment.title}",
                start=appointment.scheduled_start,
                end=appointment.scheduled_end,
                db=self.db,
                attendees=[attendee_email] if attendee_email else None,
                location=appointment.video_link,
                add_teams_link=False,
                body=description,
            )

            if calendar_result.success:
                appointment.outlook_event_id = calendar_result.event_id
                self.db.commit()
                logger.info(
                    f"Outlook event created for appointment {appointment.id}: "
                    f"{calendar_result.event_id}"
                )
                return calendar_result.event_id
            else:
                logger.warning(
                    f"Could not create Outlook event: {calendar_result.error}"
                )
                return None
        except Exception as e:
            logger.debug(f"Outlook calendar event creation unavailable: {e}")
            return None

    # =========================================================================
    # PRIVATE: AUDIT & EVENTS
    # =========================================================================

    def _write_audit_log(
        self,
        user_id: Optional[int],
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        changes: Optional[Dict] = None,
    ) -> None:
        """Write to scheduler_audit_log table."""
        AuditLog = _get_model("SchedulerAuditLog")
        if not AuditLog:
            return

        try:
            entry = AuditLog(
                organization_id=self.organization_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
            )
            self.db.add(entry)
        except Exception as e:
            logger.debug(f"Failed to write audit log: {e}")

    def _emit_event(self, event: AppointmentEvent, data: Dict[str, Any]) -> None:
        """
        Emit an event for downstream consumers.

        Currently stores events in-memory on the service instance.
        Future: publish to Redis pub/sub, webhook queue, or event bus.
        """
        event_record = {
            "event": event.value,
            "organization_id": self.organization_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._emitted_events.append(event_record)
        logger.info(f"Event emitted: {event.value} | {data}")

    @property
    def events(self) -> List[Dict[str, Any]]:
        """Access events emitted during this service instance's lifetime."""
        return list(self._emitted_events)

    # =========================================================================
    # PRIVATE: SERIALIZATION
    # =========================================================================

    def _serialize_appointment(self, appointment) -> Dict[str, Any]:
        """Convert an Appointment ORM object to a JSON-safe dict."""
        return {
            "id": appointment.id,
            "organization_id": appointment.organization_id,
            "appointment_type_id": appointment.appointment_type_id,
            "assigned_user_id": appointment.assigned_user_id,
            "created_by_user_id": appointment.created_by_user_id,
            "lead_id": appointment.lead_id,
            "loan_id": appointment.loan_id,
            "contact_id": appointment.contact_id,
            "external_id": appointment.external_id,
            "external_source": appointment.external_source,
            "title": appointment.title,
            "description": appointment.description,
            "meeting_type": (
                appointment.meeting_type.value
                if hasattr(appointment.meeting_type, "value")
                else str(appointment.meeting_type) if appointment.meeting_type else None
            ),
            "meeting_mode": (
                appointment.meeting_mode.value
                if hasattr(appointment.meeting_mode, "value")
                else str(appointment.meeting_mode) if appointment.meeting_mode else None
            ),
            "scheduled_start": (
                appointment.scheduled_start.isoformat()
                if appointment.scheduled_start else None
            ),
            "scheduled_end": (
                appointment.scheduled_end.isoformat()
                if appointment.scheduled_end else None
            ),
            "duration_minutes": appointment.duration_minutes,
            "timezone": appointment.timezone,
            "location": appointment.location,
            "video_link": appointment.video_link,
            "phone_number": appointment.phone_number,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
            "attendee_phone": appointment.attendee_phone,
            "attendee_notes": appointment.attendee_notes,
            "intake_responses": appointment.intake_responses,
            "status": (
                appointment.status.value
                if hasattr(appointment.status, "value")
                else str(appointment.status) if appointment.status else None
            ),
            "status_changed_at": (
                appointment.status_changed_at.isoformat()
                if appointment.status_changed_at else None
            ),
            "booked_by_ai": appointment.booked_by_ai,
            "ai_booking_context": appointment.ai_booking_context,
            "reschedule_count": appointment.reschedule_count,
            "rescheduled_from_id": appointment.rescheduled_from_id,
            "google_calendar_event_id": appointment.google_calendar_event_id,
            "outlook_event_id": appointment.outlook_event_id,
            "internal_notes": appointment.internal_notes,
            "meeting_notes": appointment.meeting_notes,
            "created_at": (
                appointment.created_at.isoformat()
                if appointment.created_at else None
            ),
            "updated_at": (
                appointment.updated_at.isoformat()
                if appointment.updated_at else None
            ),
        }

    # =========================================================================
    # PRIVATE: UTILITIES
    # =========================================================================

    @staticmethod
    def _safe_enum_parse(enum_name: str, value: Optional[str], default: Optional[str]):
        """Safely parse an enum value from the smart_scheduler_models module."""
        if value is None:
            return None

        try:
            from smart_scheduler_models import (
                AppointmentStatus, MeetingType, MeetingMode,
            )
            enum_map = {
                "AppointmentStatus": AppointmentStatus,
                "MeetingType": MeetingType,
                "MeetingMode": MeetingMode,
            }
            enum_cls = enum_map.get(enum_name)
            if enum_cls:
                return enum_cls(value)
        except (ValueError, ImportError):
            pass

        # Return the raw string if enum parse fails -- the DB column may accept it
        return value if value else default

    @staticmethod
    def _mask_email(email: Optional[str]) -> str:
        """Mask email for logging: j***@example.com"""
        if not email or "@" not in email:
            return "***"
        local, domain = email.split("@", 1)
        return f"{local[0]}***@{domain}" if local else f"***@{domain}"


# =============================================================================
# EXCEPTIONS
# =============================================================================

class ConflictError(Exception):
    """Raised when a time slot conflict is detected."""
    pass


class AppointmentNotFoundError(Exception):
    """Raised when an appointment is not found or not accessible."""
    pass
