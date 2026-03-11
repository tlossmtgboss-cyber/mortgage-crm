"""
Scheduler Availability & Slot Generation

Extracted from scheduler_appointment_routes.py (Part 1 of decomposition).

Contains:
- Cross-source conflict detection
- Appointment conflict checking (SELECT FOR UPDATE)
- Duplicate booking detection
- Unified slot generation engine
- Availability CRUD endpoints
- Available slots endpoints (authenticated + public)
- AI slot recommendations
- Public/website demo slot generation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
import logging

from smart_scheduler_models import (
    AppointmentStatus, DayOfWeek, SlotPriority, DEFAULT_WORKING_HOURS
)
from scheduler_models import (
    AvailabilitySlotCreate, AvailableSlotsRequest,
    PublicAvailableSlotsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# DEPENDENCY INJECTION STORAGE (set by parent module)
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# CROSS-SOURCE CONFLICT HELPERS
# ============================================================================

def _get_cross_source_conflicts(db, target_user_id: int, start_dt, end_dt, org_id: int = None):
    """
    Gather all busy time blocks from all 3 calendar sources for a user.
    Returns a list of (start, end) tuples representing occupied time.
    org_id filtering is ALWAYS applied when provided (mandatory for tenant isolation).
    """
    conflicts = []

    # Source 1: v2 Appointment (scheduler_appointments) -- canonical table
    if _models and _models.get('Appointment'):
        try:
            V2Appt = _models['Appointment']
            v2_query = db.query(V2Appt).filter(
                V2Appt.assigned_user_id == target_user_id,
                V2Appt.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
                V2Appt.scheduled_start >= start_dt,
                V2Appt.scheduled_start <= end_dt
            )
            if org_id:
                v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            v2_appts = v2_query.all()
            for a in v2_appts:
                if a.scheduled_start and a.scheduled_end:
                    conflicts.append((a.scheduled_start, a.scheduled_end))
        except Exception as e:
            logger.warning(f"v2 Appointment cross-source check unavailable: {e}")

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) -- deprecated, kept for backward compat
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id == target_user_id,
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt
        )
        if org_id:
            sa_query = sa_query.filter(SAModel.organization_id == org_id)
        sa_appts = sa_query.all()
        for a in sa_appts:
            if a.start_time and a.end_time:
                conflicts.append((a.start_time, a.end_time))
    except Exception as e:
        logger.debug(f"Legacy ScheduledAppointment cross-source check skipped: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        from database.models.communication import CalendarEvent
        cal_query = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == target_user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_dt,
            CalendarEvent.start_time <= end_dt
        )
        if org_id:
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
        cal_events = cal_query.all()
        for e in cal_events:
            if e.start_time and e.end_time:
                conflicts.append((e.start_time, e.end_time))
    except Exception as ex:
        logger.warning(f"CalendarEvent cross-source check unavailable: {ex}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_query = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == target_user_id,
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_dt,
            CRMCalendarEvent.start_at <= end_dt
        )
        if org_id:
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
        crm_events = crm_query.all()
        for e in crm_events:
            if e.start_at and e.end_at:
                conflicts.append((e.start_at, e.end_at))
    except Exception as ex:
        logger.warning(f"CRMCalendarEvent cross-source check unavailable: {ex}")

    return conflicts


def _has_cross_source_conflict(conflicts, slot_start, slot_end, buffer_before=0, buffer_after=0):
    """Check if a proposed slot conflicts with any cross-source busy time."""
    for busy_start, busy_end in conflicts:
        buffered_start = busy_start - timedelta(minutes=buffer_before)
        buffered_end = busy_end + timedelta(minutes=buffer_after)
        if slot_start < buffered_end and slot_end > buffered_start:
            return True
    return False


# ============================================================================
# CONFLICT & DUPLICATE DETECTION
# ============================================================================

def _check_appointment_conflict(db, assigned_user_id: int, start_time, end_time, org_id: int = None, exclude_appointment_id=None):
    """
    Check for overlapping appointments using SELECT FOR UPDATE to prevent double-booking.
    Raises HTTPException 409 if a conflict is found or rows are locked by another transaction.
    exclude_appointment_id: skip this appointment (used when rescheduling to avoid self-conflict).
    org_id: ALWAYS applied when provided for tenant isolation.
    """
    from sqlalchemy.exc import OperationalError
    Appointment = _models['Appointment']
    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value, 'no_show', 'cancelled']),
        Appointment.scheduled_start < end_time,
        Appointment.scheduled_end > start_time,
    ]
    # Always scope by org_id when available (mandatory for tenant isolation)
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)
    if exclude_appointment_id is not None:
        filters.append(Appointment.id != exclude_appointment_id)

    try:
        conflict = db.query(Appointment).filter(and_(*filters)).with_for_update(nowait=True).first()
    except OperationalError:
        # Row is locked by another transaction -- treat as conflict
        raise HTTPException(
            status_code=409,
            detail="This time slot is being booked by another user. Please select a different time."
        )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="This time slot is no longer available. Please select a different time."
        )


# C2: Duplicate booking detection
def _check_duplicate_booking(db, attendee_email: str, assigned_user_id: int,
                              start_time, org_id: int = None, window_minutes=30):
    """
    Check for an existing booking with the same attendee_email + same LO
    within +/-window_minutes of the proposed start_time.
    Raises HTTPException 409 if a duplicate is found.
    org_id: ALWAYS applied when provided for tenant isolation.
    """
    if not attendee_email:
        return  # No email to check against

    Appointment = _models['Appointment']
    window_start = start_time - timedelta(minutes=window_minutes)
    window_end = start_time + timedelta(minutes=window_minutes)

    filters = [
        Appointment.attendee_email == attendee_email,
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value, 'cancelled']),
        Appointment.scheduled_start >= window_start,
        Appointment.scheduled_start <= window_end,
    ]
    # Always scope by org_id when available (mandatory for tenant isolation)
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)

    duplicate = db.query(Appointment).filter(and_(*filters)).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A booking for this email already exists at this time. "
                   f"Existing appointment ID: {duplicate.id}"
        )


# ============================================================================
# UNIFIED SLOT GENERATION ENGINE
# ============================================================================

def _generate_available_slots(
    db: Session,
    user_ids: list,
    start_date: date,
    end_date: date,
    duration_minutes: int = 30,
    org_id: int = None,
    max_per_day: int = None,
    check_cross_source: bool = True,
    include_user_id: bool = False,
    include_day_name: bool = False,
    time_key_format: str = "start",  # "start"->{start,end} or "start_time"->{start_time,end_time}
) -> list:
    """
    Unified slot generator used by all availability endpoints.

    Computes available time slots for one or more users by checking:
    - Working hours from SchedulerConfig
    - Blocked times
    - Existing appointments (with buffers)
    - Cross-source calendar conflicts (if enabled)
    - Lunch break (if configured)
    - Minimum notice period
    - Max meetings per day (if set)

    Returns a sorted list of slot dicts. Key names controlled by params:
      time_key_format="start"      -> {"start": ..., "end": ...}
      time_key_format="start_time" -> {"start_time": ...Z, "end_time": ...Z}
    """
    SchedulerConfig = _models.get('SchedulerConfig')
    BlockedTime = _models.get('BlockedTime')
    Appointment = _models.get('Appointment')

    if not SchedulerConfig or not BlockedTime or not Appointment:
        logger.error("Scheduler models not available for slot generation")
        return []

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC -- consistent with datetime.combine() outputs
    all_slots = []

    for user_id in user_ids:
        # Load user config
        config_query = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user_id
        )
        if org_id:
            config_query = config_query.filter(SchedulerConfig.organization_id == org_id)
        config = config_query.first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        min_notice = config.min_notice_hours if config else 2
        user_max_per_day = max_per_day or (config.max_meetings_per_day if config else None)
        enforce_lunch = getattr(config, 'enforce_lunch_break', True) if config else True
        lunch_start_time = getattr(config, 'lunch_break_start', time(12, 0)) if config else time(12, 0)
        lunch_end_time = getattr(config, 'lunch_break_end', time(13, 0)) if config else time(13, 0)

        min_booking_time = now + timedelta(hours=min_notice)
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        # Query blocked times
        blocked_query = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        )
        if org_id:
            blocked_query = blocked_query.filter(BlockedTime.organization_id == org_id)
        blocked_times = blocked_query.all()

        # Query existing appointments
        appt_query = db.query(Appointment).filter(
            Appointment.assigned_user_id == user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        )
        if org_id:
            appt_query = appt_query.filter(Appointment.organization_id == org_id)
        existing_appts = appt_query.all()

        # Cross-source conflicts
        cross_source_busy = (
            _get_cross_source_conflicts(db, user_id, start_dt, end_dt, org_id=org_id)
            if check_cross_source else []
        )

        # Generate slots day by day
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            # Check max meetings per day
            if user_max_per_day:
                day_appts = [a for a in existing_appts
                             if a.scheduled_start.date() == current_date]
                day_cross = [c for c in cross_source_busy
                             if c[0].date() == current_date]
                if (len(day_appts) + len(day_cross)) >= user_max_per_day:
                    current_date += timedelta(days=1)
                    continue

            # Parse working hours
            try:
                work_start = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                work_end = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, work_start)
            day_end = datetime.combine(current_date, work_end)
            lunch_start = datetime.combine(current_date, lunch_start_time) if enforce_lunch else None
            lunch_end = datetime.combine(current_date, lunch_end_time) if enforce_lunch else None

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Skip past/too-soon slots
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Skip lunch break
                if lunch_start and lunch_end and slot_start < lunch_end and slot_end > lunch_start:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )
                if is_blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check appointment conflicts (with buffers)
                has_conflict = any(
                    slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                    slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                    for appt in existing_appts
                )

                # Check cross-source conflicts
                if not has_conflict and cross_source_busy:
                    has_conflict = _has_cross_source_conflict(
                        cross_source_busy, slot_start, slot_end,
                        buffer_before, buffer_after
                    )

                if not has_conflict:
                    # Build slot dict based on format params
                    if time_key_format == "start_time":
                        slot = {
                            "start_time": slot_start.isoformat() + "Z",
                            "end_time": slot_end.isoformat() + "Z",
                            "date": current_date.isoformat(),
                        }
                    else:
                        slot = {
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": current_date.isoformat(),
                        }
                    if include_user_id:
                        slot["user_id"] = user_id
                    if include_day_name:
                        slot["day"] = day_name
                    all_slots.append(slot)

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Deduplicate and sort
    sort_key = "start_time" if time_key_format == "start_time" else "start"
    unique_slots = list({s[sort_key]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x[sort_key])
    return unique_slots


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@router.get("/availability")
async def get_availability(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get availability slots for a date range"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    target_user_id = user_id or user.id

    # S1: Validate target user belongs to same organization (prevent cross-tenant IDOR)
    if user_id and user_id != user.id:
        User = _models.get('User')
        if User:
            target_user = db.query(User).filter(
                User.id == user_id,
                User.organization_id == org_id
            ).first()
            if not target_user:
                raise HTTPException(status_code=403, detail="User not found in your organization")

    # Get config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == target_user_id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        # Return default working hours
        return {
            "availability": [],
            "working_hours": DEFAULT_WORKING_HOURS,
            "blocked_times": [],
            "existing_appointments": []
        }

    # Get custom availability slots
    slots = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.config_id == config.id,
        AvailabilitySlot.is_active == True,
        or_(
            AvailabilitySlot.is_recurring == True,
            and_(
                AvailabilitySlot.specific_date >= start_date,
                AvailabilitySlot.specific_date <= end_date
            )
        )
    ).all()

    # Get blocked times
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    blocked = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        BlockedTime.organization_id == org_id,
        or_(
            BlockedTime.user_id == target_user_id,
            and_(BlockedTime.applies_to_all_users == True, BlockedTime.organization_id == org_id)
        ),
        BlockedTime.start_datetime <= end_dt,
        BlockedTime.end_datetime >= start_dt
    ).all()

    # Get existing appointments
    appointments = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.assigned_user_id == target_user_id,
        Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    ).all()

    return {
        "availability": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week.value if s.day_of_week else None,
                "specific_date": s.specific_date.isoformat() if s.specific_date else None,
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "priority": s.priority.value if s.priority else "standard",
                "is_recurring": s.is_recurring
            }
            for s in slots
        ],
        "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "start": b.start_datetime.isoformat(),
                "end": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "block_type": b.block_type
            }
            for b in blocked
        ],
        "existing_appointments": [
            {
                "id": a.id,
                "title": a.title,
                "start": a.scheduled_start.isoformat(),
                "end": a.scheduled_end.isoformat(),
                "status": a.status.value if a.status else "booked"
            }
            for a in appointments
        ]
    }


@router.post("/availability/slots")
async def create_availability_slot(
    slot_data: AvailabilitySlotCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a custom availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        raise HTTPException(status_code=400, detail="Please create scheduler config first")

    # Parse times
    try:
        start_time_parsed = datetime.strptime(slot_data.start_time, "%H:%M").time()
        end_time_parsed = datetime.strptime(slot_data.end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    # Parse day of week
    day_of_week = None
    if slot_data.day_of_week:
        try:
            day_of_week = DayOfWeek(slot_data.day_of_week.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid day of week")

    # Parse priority
    priority = SlotPriority.STANDARD
    if slot_data.priority:
        try:
            priority = SlotPriority(slot_data.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {slot_data.priority}")

    # Validate max_bookings
    if slot_data.max_bookings is not None and slot_data.max_bookings < 1:
        raise HTTPException(status_code=400, detail="max_bookings must be at least 1")

    slot = AvailabilitySlot(
        organization_id=org_id,
        config_id=config.id,
        user_id=user.id,
        day_of_week=day_of_week,
        specific_date=slot_data.specific_date,
        start_time=start_time_parsed,
        end_time=end_time_parsed,
        priority=priority,
        is_recurring=slot_data.is_recurring,
        allowed_meeting_types=slot_data.allowed_meeting_types,
        max_bookings=max(1, slot_data.max_bookings or 1)
    )

    db.add(slot)
    db.commit()
    db.refresh(slot)

    return {"message": "Availability slot created", "slot_id": slot.id}


@router.delete("/availability/slots/{slot_id}")
async def delete_availability_slot(
    slot_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete an availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AvailabilitySlot = _models['AvailabilitySlot']

    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.user_id == user.id,
        AvailabilitySlot.organization_id == org_id
    ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    db.delete(slot)
    db.commit()

    return {"message": "Slot deleted"}


# ============================================================================
# SLOT AVAILABILITY ENGINE
# ============================================================================

@router.post("/available-slots")
async def get_available_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get available time slots for booking.
    Delegates to the unified _generate_available_slots engine.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=slot_request.start_date,
        end_date=slot_request.end_date,
        duration_minutes=slot_request.duration_minutes,
        org_id=org_id,
        max_per_day=8,  # Default max per day for authenticated endpoint
        check_cross_source=True,
        include_user_id=True,
        include_day_name=True,
    )

    return {
        "available_slots": available_slots,
        "total_slots": len(available_slots),
        "request": {
            "start_date": slot_request.start_date.isoformat(),
            "end_date": slot_request.end_date.isoformat(),
            "duration_minutes": slot_request.duration_minutes,
            "user_ids": user_ids
        }
    }


# ============================================================================
# AI SLOT RECOMMENDATIONS
# ============================================================================

@router.post("/ai-recommend-slots")
async def ai_recommend_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get AI-recommended time slots based on:
    - User preferences
    - Lead/loan context
    - Historical patterns
    - Optimal meeting times
    """
    user = await get_current_user(request, db)

    # First get available slots
    available_response = await get_available_slots(slot_request, request, db)
    available_slots = available_response.get("available_slots", [])

    if not available_slots:
        return {
            "recommendations": [],
            "message": "No available slots found in the requested range"
        }

    # Score each slot
    recommendations = []

    for slot in available_slots[:20]:  # Limit to first 20 for performance
        score = 1.0
        reasons = []

        # Parse the slot time
        try:
            slot_dt = datetime.fromisoformat(slot["start"])
        except (ValueError, TypeError):
            continue
        hour = slot_dt.hour
        day_name = slot["day"]

        # Score based on time of day (prefer mid-morning and early afternoon)
        if 9 <= hour <= 11:
            score += 0.3
            reasons.append("Optimal morning time slot")
        elif 14 <= hour <= 16:
            score += 0.2
            reasons.append("Good afternoon time slot")
        elif hour < 9 or hour > 17:
            score -= 0.2
            reasons.append("Outside peak hours")

        # Score based on day of week
        if day_name in ["tuesday", "wednesday", "thursday"]:
            score += 0.1
            reasons.append("Mid-week availability")
        elif day_name == "monday":
            score -= 0.1
            reasons.append("Monday may have competing priorities")
        elif day_name == "friday":
            score -= 0.1
            reasons.append("Friday afternoon may have lower engagement")

        # Bonus for sooner availability
        days_from_now = (slot_dt.date() - datetime.now(timezone.utc).date()).days
        if days_from_now <= 2:
            score += 0.2
            reasons.append("Soon availability - strike while hot")
        elif days_from_now > 7:
            score -= 0.1
            reasons.append("Further out - lead may cool")

        recommendations.append({
            "slot": slot,
            "score": round(score, 2),
            "reasons": reasons
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return {
        "recommendations": recommendations[:5],  # Top 5
        "total_available": len(available_slots)
    }


# ============================================================================
# PUBLIC SLOT AVAILABILITY ENDPOINTS (No auth required)
# ============================================================================

@router.get("/public/book/{slug}/slots")
async def get_public_available_slots(
    slug: str,
    appointment_type_id: int = Query(...),
    date: date = Query(..., description="Date to get slots for"),
    duration_minutes: int = Query(30),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get available slots for public booking. Delegates to unified slot engine."""
    # Rate limiting imported lazily to avoid circular dependency
    from routes.scheduler_appointment_routes import _check_rate_limit
    if request:
        _check_rate_limit(request)

    BookingLink = _models['BookingLink']
    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    user_ids = link.assigned_users if link.assigned_users else [link.user_id]
    link_org_id = getattr(link, 'organization_id', None)

    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=date,
        end_date=date,
        duration_minutes=duration_minutes,
        org_id=link_org_id,
        check_cross_source=True,
    )

    return {"available_slots": available_slots}


@router.post("/public/available-slots")
async def get_website_demo_available_slots(
    request: PublicAvailableSlotsRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    from routes.scheduler_appointment_routes import _check_rate_limit
    _check_rate_limit(http_request)
    """
    Get available slots for website demo scheduling.

    This endpoint looks up the calendar assignment for 'website_demo' purpose
    and returns available slots from the assigned user's calendar.

    Used by the public website demo scheduler.
    """
    from sqlalchemy import text

    try:
        # Parse dates
        start_date_parsed = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end_date_parsed = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Look up calendar assignment for website_demo purpose
    assignment_result = db.execute(text("""
        SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,
               u.full_name as user_name, u.email as user_email
        FROM calendar_assignments ca
        LEFT JOIN users u ON u.id = ca.assigned_user_id
        WHERE ca.purpose = 'website_demo' AND ca.is_active = true
        LIMIT 1
    """)).fetchone()

    if not assignment_result:
        # No assignment configured - return empty slots with helpful message
        logger.warning("No calendar assignment found for website_demo purpose")
        return {
            "available_slots": [],
            "message": "Website demo calendar not configured. Please assign a team member in Calendar Management.",
            "configured": False
        }

    assigned_user_id = assignment_result.assigned_user_id
    calendly_url = assignment_result.calendly_url
    booking_link_id = assignment_result.booking_link_id

    # If there's a booking link configured, use it
    if booking_link_id and _models:
        BookingLink = _models.get('BookingLink')
        if BookingLink:
            link = db.query(BookingLink).filter(
                BookingLink.id == booking_link_id,
                BookingLink.is_active == True
            ).first()
            if link:
                # Use the booking link's assigned users
                link_org_id = getattr(link, 'organization_id', None)
                user_ids = link.assigned_users if link.assigned_users else [link.user_id]
                return await _generate_slots_for_users(
                    db, user_ids, start_date_parsed, end_date_parsed, request.duration_minutes,
                    org_id=link_org_id
                )

    # If there's an assigned user, get their availability
    if assigned_user_id:
        return await _generate_slots_for_users(
            db, [assigned_user_id], start_date_parsed, end_date_parsed, request.duration_minutes
        )

    # If there's a Calendly URL, redirect to Calendly
    if calendly_url:
        return {
            "available_slots": [],
            "calendly_url": calendly_url,
            "message": "Please use the Calendly link to schedule",
            "configured": True
        }

    return {
        "available_slots": [],
        "message": "No calendar configuration found",
        "configured": False
    }


async def _generate_slots_for_users(
    db: Session,
    user_ids: List[int],
    start_date: date,
    end_date: date,
    duration_minutes: int = 30,
    org_id: Optional[int] = None
) -> dict:
    """Generate available slots for a list of users. Delegates to unified slot engine."""
    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        org_id=org_id,
        check_cross_source=False,
        include_user_id=True,
        time_key_format="start_time",
    )

    return {
        "available_slots": available_slots,
        "configured": True,
        "slot_count": len(available_slots)
    }
