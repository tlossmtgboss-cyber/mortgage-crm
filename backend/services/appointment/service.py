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

The heavy lifting for creation and lifecycle mutations is delegated to:
- services.appointment.create_service     (create_appointment)
- services.appointment.lifecycle_service   (update, cancel, reschedule, confirm,
                                            mark_no_show, mark_completed)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, date, time, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE
from services.appointment._models import (
    AppointmentEvent,
    AppointmentResult,
    AppointmentSource,
    ConflictCheckResult,
    DEFAULT_BUFFER_AFTER,
    DEFAULT_BUFFER_BEFORE,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_HOLD_TTL_SECONDS,
    DEFAULT_MIN_NOTICE_HOURS,
    DEFAULT_WORKING_HOURS,
    MAX_DATE_RANGE_DAYS,
    get_model,
    mask_email,
    safe_enum_parse,
)
from services.appointment.conflict_checker import (
    check_conflict as _check_conflict,
    get_all_busy_times as _get_all_busy_times,
    slot_conflicts_with_busy as _slot_conflicts_with_busy,
)
from services.appointment.hold_manager import (
    hold_slot as _hold_slot,
    release_hold as _release_hold,
    slot_conflicts_with_holds as _slot_conflicts_with_holds,
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
        timezone_str: str = DEFAULT_TIMEZONE,
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
    # CREATE (delegated)
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
        from services.appointment.create_service import create_appointment as _do_create
        return await _do_create(
            self.db,
            self.organization_id,
            data,
            source=source,
            requester_user_id=requester_user_id,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
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
    # UPDATE (delegated)
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
        from services.appointment.lifecycle_service import update_appointment as _do_update
        return await _do_update(
            self.db,
            self.organization_id,
            appointment_id,
            data,
            requester_user_id=requester_user_id,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
            serialize_appointment=self._serialize_appointment,
        )

    # =========================================================================
    # CANCEL (delegated)
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
        from services.appointment.lifecycle_service import cancel_appointment as _do_cancel
        return await _do_cancel(
            self.db,
            self.organization_id,
            appointment_id,
            reason=reason,
            requester_user_id=requester_user_id,
            send_notification=send_notification,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
        )

    # =========================================================================
    # RESCHEDULE (delegated)
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
        from services.appointment.lifecycle_service import reschedule_appointment as _do_reschedule
        return await _do_reschedule(
            self.db,
            self.organization_id,
            appointment_id,
            new_start,
            new_duration_minutes=new_duration_minutes,
            requester_user_id=requester_user_id,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
            do_create_appointment=self.create_appointment,
        )

    # =========================================================================
    # CONFIRM (delegated)
    # =========================================================================

    async def confirm_appointment(self, appointment_id: int) -> AppointmentResult:
        """
        Confirm a booked appointment and send confirmation email.
        Transitions status from booked/tentative to confirmed (auto_confirmed=True).
        """
        from services.appointment.lifecycle_service import confirm_appointment as _do_confirm
        return await _do_confirm(
            self.db,
            self.organization_id,
            appointment_id,
            emit_event=self._emit_event,
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
    # STATUS TRANSITIONS (delegated)
    # =========================================================================

    async def mark_no_show(self, appointment_id: int) -> AppointmentResult:
        """
        Mark an appointment as no-show and trigger recovery workflow.
        Creates a high-priority follow-up task.
        """
        from services.appointment.lifecycle_service import mark_no_show as _do_mark_no_show
        return await _do_mark_no_show(
            self.db,
            self.organization_id,
            appointment_id,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
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
        from services.appointment.lifecycle_service import mark_completed as _do_mark_completed
        return await _do_mark_completed(
            self.db,
            self.organization_id,
            appointment_id,
            notes=notes,
            write_audit_log=self._write_audit_log,
            emit_event=self._emit_event,
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
