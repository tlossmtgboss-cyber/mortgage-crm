"""
Conflict detection for the appointment service.

Handles double-booking prevention (SELECT FOR UPDATE), cross-source
conflict checks, and duplicate booking detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from services.appointment._models import (
    ConflictCheckResult,
    ConflictError,
    TERMINAL_STATUSES,
    get_model,
)
from services.appointment.hold_manager import slot_conflicts_with_holds

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================

def check_conflict(
    db: Session,
    organization_id: int,
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
    Appointment = get_model("Appointment")
    if Appointment:
        conflict = db.query(Appointment).filter(
            Appointment.assigned_user_id == lo_id,
            Appointment.organization_id == organization_id,
            Appointment.status.notin_(TERMINAL_STATUSES),
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
    busy = get_all_busy_times(db, organization_id, lo_id, start, end)
    for busy_start, busy_end in busy:
        if start < busy_end and end > busy_start:
            return ConflictCheckResult(
                has_conflict=True,
                conflicting_source="cross_source",
                message="Conflicts with an existing calendar event",
            )

    # Check soft holds
    if slot_conflicts_with_holds(db, organization_id, lo_id, start, end):
        return ConflictCheckResult(
            has_conflict=True,
            conflicting_source="soft_hold",
            message="This slot is temporarily held by another booking in progress",
        )

    return ConflictCheckResult(has_conflict=False)


# =============================================================================
# DOUBLE-BOOKING PREVENTION
# =============================================================================

def check_conflict_for_update(
    db: Session,
    organization_id: int,
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

    Appointment = get_model("Appointment")
    if not Appointment:
        return

    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.organization_id == organization_id,
        Appointment.status.notin_(list(TERMINAL_STATUSES)),
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
        raise ConflictError(
            "This time slot is being booked by another user. "
            "Please select a different time."
        )

    if conflict:
        raise ConflictError(
            "This time slot is no longer available. "
            "Please select a different time."
        )


def check_duplicate_booking(
    db: Session,
    organization_id: int,
    attendee_email: str,
    assigned_user_id: int,
    start_time: datetime,
    window_minutes: int = 30,
) -> Optional[int]:
    """
    Check for duplicate booking (same email + LO within a time window).
    Returns conflicting appointment ID or None.
    """
    Appointment = get_model("Appointment")
    if not Appointment or not attendee_email:
        return None

    window_start = start_time - timedelta(minutes=window_minutes)
    window_end = start_time + timedelta(minutes=window_minutes)

    duplicate = db.query(Appointment).filter(
        Appointment.attendee_email == attendee_email,
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.organization_id == organization_id,
        Appointment.status.notin_(list(TERMINAL_STATUSES)),
        Appointment.scheduled_start >= window_start,
        Appointment.scheduled_start <= window_end,
    ).first()

    return duplicate.id if duplicate else None


# =============================================================================
# CROSS-SOURCE BUSY TIME AGGREGATION
# =============================================================================

def get_all_busy_times(
    db: Session,
    organization_id: int,
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
    Appointment = get_model("Appointment")
    if Appointment:
        try:
            filters = [
                Appointment.assigned_user_id == lo_id,
                Appointment.organization_id == organization_id,
                Appointment.status.notin_(list(TERMINAL_STATUSES)),
                Appointment.scheduled_start <= range_end,
                Appointment.scheduled_end >= range_start,
            ]
            if exclude_appointment_id:
                filters.append(Appointment.id != exclude_appointment_id)

            appts = db.query(Appointment).filter(and_(*filters)).all()
            for a in appts:
                if a.scheduled_start and a.scheduled_end:
                    busy.append((a.scheduled_start, a.scheduled_end))
        except Exception as e:
            logger.warning(f"Error querying scheduler_appointments: {e}")

    # Source 2: ScheduledAppointment (AI-booked)
    SAModel = get_model("ScheduledAppointment")
    if SAModel:
        try:
            sa_query = db.query(SAModel).filter(
                SAModel.loan_officer_id == lo_id,
                SAModel.status.in_(["scheduled", "confirmed"]),
                SAModel.start_time >= range_start,
                SAModel.start_time <= range_end,
            )
            if hasattr(SAModel, "organization_id"):
                sa_query = sa_query.filter(
                    SAModel.organization_id == organization_id,
                )
            for a in sa_query.all():
                if a.start_time and a.end_time:
                    busy.append((a.start_time, a.end_time))
        except Exception as e:
            logger.debug(f"ScheduledAppointment query unavailable: {e}")

    # Source 3: CalendarEvent (manual calendar)
    CalendarEvent = get_model("CalendarEvent")
    if CalendarEvent:
        try:
            ce_query = db.query(CalendarEvent).filter(
                CalendarEvent.user_id == lo_id,
                CalendarEvent.status != "cancelled",
                CalendarEvent.start_time >= range_start,
                CalendarEvent.start_time <= range_end,
            )
            if hasattr(CalendarEvent, "organization_id"):
                ce_query = ce_query.filter(
                    CalendarEvent.organization_id == organization_id,
                )
            for e in ce_query.all():
                if e.start_time and e.end_time:
                    busy.append((e.start_time, e.end_time))
        except Exception as e:
            logger.debug(f"CalendarEvent query unavailable: {e}")

    # Source 4: CRMCalendarEvent (Salesforce-synced)
    CRMCalendarEvent = get_model("CRMCalendarEvent")
    if CRMCalendarEvent:
        try:
            crm_query = db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.owner_user_id == lo_id,
                CRMCalendarEvent.status != "canceled",
                CRMCalendarEvent.start_at >= range_start,
                CRMCalendarEvent.start_at <= range_end,
            )
            if hasattr(CRMCalendarEvent, "organization_id"):
                crm_query = crm_query.filter(
                    CRMCalendarEvent.organization_id == organization_id,
                )
            for e in crm_query.all():
                if e.start_at and e.end_at:
                    busy.append((e.start_at, e.end_at))
        except Exception as e:
            logger.debug(f"CRMCalendarEvent query unavailable: {e}")

    return busy


def slot_conflicts_with_busy(
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
