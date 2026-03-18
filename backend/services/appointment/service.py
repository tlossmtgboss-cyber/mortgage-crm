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
from datetime import datetime, timedelta, date, time, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from services.appointment._models import (
    AppointmentEvent,
    AppointmentResult,
    AppointmentSource,
    ConflictCheckResult,
    ConflictError,
    DEFAULT_BUFFER_AFTER,
    DEFAULT_BUFFER_BEFORE,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_HOLD_TTL_SECONDS,
    DEFAULT_MIN_NOTICE_HOURS,
    DEFAULT_WORKING_HOURS,
    MAX_DATE_RANGE_DAYS,
    TERMINAL_STATUSES,
    get_model,
    mask_email,
    safe_enum_parse,
)
from services.appointment.conflict_checker import (
    check_conflict as _check_conflict,
    check_conflict_for_update as _check_conflict_for_update,
    check_duplicate_booking as _check_duplicate_booking,
    get_all_busy_times as _get_all_busy_times,
    slot_conflicts_with_busy as _slot_conflicts_with_busy,
)
from services.appointment.hold_manager import (
    hold_slot as _hold_slot,
    release_hold as _release_hold,
    release_holds_for_slot as _release_holds_for_slot,
    slot_conflicts_with_holds as _slot_conflicts_with_holds,
)
from services.appointment.crm_bridge import (
    create_followup_task as _create_followup_task,
    ensure_lead as _ensure_lead,
    log_activity as _log_activity,
)
from services.appointment.notifications import (
    create_outlook_event as _create_outlook_event,
    send_cancellation_notification as _send_cancellation_notification,
    send_confirmation_email as _send_confirmation_email,
    send_update_notification as _send_update_notification,
)

logger = logging.getLogger(__name__)


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
        duration_minutes: int = DEFAULT_DURATION_MINUTES,
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
        if (end_date - start_date).days > MAX_DATE_RANGE_DAYS:
            raise ValueError(f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        Appointment = get_model("Appointment")
        SchedulerConfig = get_model("SchedulerConfig")
        BlockedTime = get_model("BlockedTime")

        if not Appointment or not SchedulerConfig or not BlockedTime:
            logger.error("Required scheduler models not available")
            return []

        # Load LO config
        config = self.db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == lo_id,
            SchedulerConfig.organization_id == self.organization_id,
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else DEFAULT_BUFFER_BEFORE
        buffer_after = config.buffer_after_minutes if config else DEFAULT_BUFFER_AFTER
        min_notice = config.min_notice_hours if config else DEFAULT_MIN_NOTICE_HOURS
        max_per_day = config.max_meetings_per_day if config else None
        enforce_lunch = getattr(config, "enforce_lunch_break", True) if config else True
        lunch_start_t = getattr(config, "lunch_break_start", time(12, 0)) if config else time(12, 0)
        lunch_end_t = getattr(config, "lunch_break_end", time(13, 0)) if config else time(13, 0)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        min_booking_time = now + timedelta(hours=min_notice)
        range_start_dt = datetime.combine(start_date, time.min)
        range_end_dt = datetime.combine(end_date, time.max)

        # Gather ALL busy times from every source
        busy_times = _get_all_busy_times(
            self.db, self.organization_id,
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
                has_conflict = _slot_conflicts_with_busy(
                    slot_start, slot_end, busy_times,
                    buffer_before, buffer_after,
                )

                # Check soft holds
                if not has_conflict:
                    has_conflict = _slot_conflicts_with_holds(
                        self.db, self.organization_id,
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
                self.db, self.organization_id,
                assigned_user_id, scheduled_start, scheduled_end,
                exclude_appointment_id=None,
            )
        except ConflictError as e:
            return AppointmentResult(success=False, error=str(e))

        # --- Duplicate booking detection ---
        if attendee_email and assigned_user_id:
            dup = _check_duplicate_booking(
                self.db, self.organization_id,
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

        self.db.add(appointment)
        self._write_audit_log(
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
        self.db.flush()  # Get the ID without committing

        # --- CRM integrations (best-effort, never block the booking) ---

        # Link or create Lead
        if not appointment.lead_id and attendee_email:
            lead_id = _ensure_lead(
                self.db, self.organization_id,
                attendee_email, attendee_name, attendee_phone,
                assigned_user_id,
            )
            if lead_id:
                appointment.lead_id = lead_id

        # Log CRM Activity
        _log_activity(
            self.db, self.organization_id,
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
                self.db, self.organization_id,
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
        _release_holds_for_slot(
            self.db, self.organization_id,
            lo_id=assigned_user_id,
            start_time=scheduled_start,
            end_time=scheduled_end,
        )

        # --- Post-commit notifications (best-effort) ---
        email_sent = False
        outlook_event_id = None

        if attendee_email:
            email_sent = await _send_confirmation_email(
                self.db, appointment, assigned_user_id,
            )
            if not email_sent:
                warnings.append("Confirmation email could not be sent")

        if assigned_user_id:
            outlook_event_id = await _create_outlook_event(
                self.db, appointment, attendee_email, attendee_name, attendee_phone,
            )

        # Emit event
        self._emit_event(AppointmentEvent.CREATED, {
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

    # =========================================================================
    # READ
    # =========================================================================

    async def get_appointment(self, appointment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single appointment by ID with tenant isolation.

        Returns None if not found or not in this organization.
        """
        Appointment = get_model("Appointment")
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
        Appointment = get_model("Appointment")
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
            status_enum = safe_enum_parse("AppointmentStatus", status, None)
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
        Appointment = get_model("Appointment")
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
                _check_conflict_for_update(
                    self.db, self.organization_id,
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
            await _send_update_notification(appointment)

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
        Appointment = get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        old_status = appointment.status
        cancelled_status = safe_enum_parse("AppointmentStatus", "cancelled", "cancelled")

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
        _log_activity(
            self.db, self.organization_id,
            user_id=requester_user_id or appointment.assigned_user_id,
            lead_id=appointment.lead_id,
            loan_id=appointment.loan_id,
            content=f"Appointment cancelled: {appointment.title}. Reason: {reason or 'Not specified'}",
        )

        self.db.commit()

        # Send cancellation notifications
        if send_notification and appointment.attendee_email:
            await _send_cancellation_notification(appointment)

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
        Appointment = get_model("Appointment")
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
            _check_conflict_for_update(
                self.db, self.organization_id,
                original.assigned_user_id, new_start, new_end,
                exclude_appointment_id=appointment_id,
            )
        except ConflictError as e:
            return AppointmentResult(success=False, error=str(e))

        # Mark original as rescheduled
        rescheduled_status = safe_enum_parse("AppointmentStatus", "rescheduled", "rescheduled")
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
        Appointment = get_model("Appointment")
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

        booked_status = safe_enum_parse("AppointmentStatus", "booked", "booked")
        appointment.status = booked_status
        appointment.auto_confirmed = True
        appointment.status_changed_at = datetime.now(timezone.utc)

        self.db.commit()

        # Send confirmation
        email_sent = False
        if appointment.attendee_email:
            email_sent = await _send_confirmation_email(
                self.db, appointment, appointment.assigned_user_id,
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
        duration_minutes: int = DEFAULT_DURATION_MINUTES,
        ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS,
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
        result = _hold_slot(
            self.db, self.organization_id,
            lo_id, start_time, duration_minutes, ttl_seconds, source,
        )

        self._emit_event(AppointmentEvent.HOLD_CREATED, {
            "hold_id": result["hold_id"],
            "lo_id": lo_id,
            "start_time": result["start_time"],
            "ttl_seconds": ttl_seconds,
        })

        return result

    async def release_hold(self, hold_id: str) -> bool:
        """
        Release a soft hold. Returns True if the hold existed and was released.
        """
        released = _release_hold(self.db, self.organization_id, hold_id)
        if released:
            self._emit_event(AppointmentEvent.HOLD_RELEASED, {"hold_id": hold_id})
        return released

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
        return _check_conflict(
            self.db, self.organization_id,
            lo_id, start, end,
        )

    # =========================================================================
    # STATUS TRANSITIONS
    # =========================================================================

    async def mark_no_show(self, appointment_id: int) -> AppointmentResult:
        """
        Mark an appointment as no-show and trigger recovery workflow.
        Creates a high-priority follow-up task.
        """
        Appointment = get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        no_show_status = safe_enum_parse("AppointmentStatus", "no_show", "no_show")
        appointment.status = no_show_status
        appointment.no_show_at = datetime.now(timezone.utc)
        appointment.status_changed_at = datetime.now(timezone.utc)

        # Create high-priority re-engagement task
        _create_followup_task(
            self.db, self.organization_id,
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
            self.db, self.organization_id,
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
        Appointment = get_model("Appointment")
        if not Appointment:
            return AppointmentResult(success=False, error="Appointment model not available")

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == self.organization_id,
        ).first()

        if not appointment:
            return AppointmentResult(success=False, error="Appointment not found")

        completed_status = safe_enum_parse("AppointmentStatus", "completed", "completed")
        appointment.status = completed_status
        appointment.completed_at = datetime.now(timezone.utc)
        appointment.status_changed_at = datetime.now(timezone.utc)

        if notes:
            appointment.meeting_notes = notes

        _log_activity(
            self.db, self.organization_id,
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
        Appointment = get_model("Appointment")
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
        AuditLog = get_model("SchedulerAuditLog")
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
    # PRIVATE: UTILITIES (static, delegated to _models)
    # =========================================================================

    @staticmethod
    def _safe_enum_parse(enum_name: str, value: Optional[str], default: Optional[str]):
        """Safely parse an enum value from the smart_scheduler_models module."""
        return safe_enum_parse(enum_name, value, default)

    @staticmethod
    def _mask_email(email: Optional[str]) -> str:
        """Mask email for logging: j***@example.com"""
        return mask_email(email)
