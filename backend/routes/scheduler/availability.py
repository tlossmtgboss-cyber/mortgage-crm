"""
Scheduler Availability - Availability CRUD and slot generation endpoints.

Endpoints:
  - GET    /availability                Get availability for a date range
  - POST   /availability/slots          Create a custom availability slot
  - DELETE /availability/slots/{id}     Delete an availability slot
  - POST   /available-slots             Get available time slots (authenticated)
  - GET    /capacity                    Get capacity metrics (future)
  - POST   /check-availability          Check if a specific time is available (future)

This module delegates slot generation to the unified engine in _helpers.py.

NOTE: Availability Data Sources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This module works with THREE availability-related data stores:

1. SchedulerConfig.working_hours (JSON blob) — the original weekly schedule
   storage. Updated via PUT /settings/availability. Used as a FALLBACK by the
   slot generator when no RecurringAvailability rows exist.

2. AvailabilitySlot table — custom per-date or per-day-of-week availability
   overrides created through this module's POST /availability/slots endpoint.
   These are returned by GET /availability but are NOT used by the unified
   slot generator in _helpers._generate_available_slots().

3. RecurringAvailability / AvailabilityException tables — structured weekly
   patterns managed via the recurring_availability.py endpoints. These take
   PRECEDENCE over the JSON blob in the slot generator when they exist.

The GET /availability endpoint returns data from store #1 (working_hours JSON)
and store #2 (AvailabilitySlot rows). The POST /available-slots endpoint uses
the unified slot generator which reads from store #3 (if populated) or store #1
(as fallback), but never store #2.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date, time, timezone
from typing import Optional
import logging

from smart_scheduler_models import (
    AppointmentStatus, DayOfWeek, SlotPriority, DEFAULT_WORKING_HOURS,
)
from scheduler_models import (
    AvailabilitySlotCreate, AvailableSlotsRequest,
)

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id,
    _is_scheduler_admin, _audit_log,
    _generate_available_slots,
)
from auth.scope_enforcement import require_scope
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

MAX_AVAILABILITY_RANGE_DAYS = 90


@router.get("/availability")
async def get_availability(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _scope=Depends(require_scope("read:appointments")),
):
    """Get availability slots for a date range"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Validate date range to prevent unbounded queries
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    if (end_date - start_date).days > MAX_AVAILABILITY_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range cannot exceed {MAX_AVAILABILITY_RANGE_DAYS} days",
        )

    _models = get_models()
    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    target_user_id = user_id or user.id

    # S1: Validate target user belongs to same organization (prevent cross-tenant IDOR)
    # S2: Check permission level — non-admins viewing other users get redacted personal details
    is_viewing_other_user = user_id is not None and user_id != user.id
    is_admin = _is_scheduler_admin(user)

    if is_viewing_other_user:
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

    # Non-admins viewing another user's availability get redacted personal details:
    # blocked time titles/descriptions and appointment titles are stripped to prevent
    # leaking personal information (e.g., "Doctor appointment", "Therapy session").
    redact_details = is_viewing_other_user and not is_admin

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
                "title": "Blocked" if redact_details else b.title,
                "start": b.start_datetime.isoformat(),
                "end": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "block_type": b.block_type if not redact_details else "blocked"
            }
            for b in blocked
        ],
        "existing_appointments": [
            {
                "id": a.id,
                "title": "Busy" if redact_details else a.title,
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
    db: Session = Depends(get_db),
    _scope=Depends(require_scope("write:appointments")),
):
    """Create a custom availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
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
    db.flush()

    _audit_log(
        db, org_id, user.id, "created",
        "availability_slot", slot.id,
        changes={
            "day_of_week": slot_data.day_of_week,
            "specific_date": str(slot_data.specific_date) if slot_data.specific_date else None,
            "start_time": slot_data.start_time,
            "end_time": slot_data.end_time,
        },
        request=request,
    )
    db.commit()
    # Invalidate availability cache for this user
    from routes.scheduler._availability import invalidate_availability_cache
    invalidate_availability_cache(org_id=org_id, user_id=user.id)

    return {"message": "Availability slot created", "slot_id": slot.id}


@router.delete("/availability/slots/{slot_id}")
async def delete_availability_slot(
    slot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _scope=Depends(require_scope("write:appointments")),
):
    """Delete an availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    AvailabilitySlot = _models['AvailabilitySlot']

    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.user_id == user.id,
        AvailabilitySlot.organization_id == org_id
    ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    slot.is_active = False

    _audit_log(
        db, org_id, user.id, "deleted",
        "availability_slot", slot_id,
        changes={
            "day_of_week": slot.day_of_week.value if slot.day_of_week else None,
            "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
            "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
        },
        request=request,
    )
    db.commit()
    # Invalidate availability cache for this user
    from routes.scheduler._availability import invalidate_availability_cache
    invalidate_availability_cache(org_id=org_id, user_id=user.id)

    return {"message": "Slot deleted"}


# ============================================================================
# SLOT AVAILABILITY ENGINE (authenticated)
# ============================================================================

@router.post("/available-slots")
async def get_available_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db),
    _scope=Depends(require_scope("read:appointments")),
):
    """
    Get available time slots for booking.
    Delegates to the unified _generate_available_slots engine.

    FUNC-006: When appointment_type_id is provided in the request, the slot
    duration is resolved from the appointment type's default_duration_minutes
    instead of relying solely on the request's duration_minutes field (which
    defaults to the global 30-minute fallback).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    try:
        # Validate that all requested user_ids belong to the same organization
        other_user_ids = [uid for uid in user_ids if uid != user.id]
        if other_user_ids:
            _models = get_models()
            User = _models.get('User')
            if User:
                valid_count = db.query(User).filter(
                    User.id.in_(other_user_ids),
                    User.organization_id == org_id
                ).count()
                if valid_count != len(other_user_ids):
                    raise HTTPException(
                        status_code=403,
                        detail="One or more user IDs not found in your organization"
                    )

        # FUNC-006: Resolve duration from appointment type when provided
        effective_duration = slot_request.duration_minutes
        if slot_request.appointment_type_id:
            _models = get_models()
            AppointmentType = _models.get('AppointmentType') if _models else None
            if AppointmentType:
                appt_type = db.query(AppointmentType).filter(
                    AppointmentType.id == slot_request.appointment_type_id,
                    AppointmentType.is_active == True,
                    AppointmentType.organization_id == org_id,
                ).first()
                if appt_type and getattr(appt_type, 'default_duration_minutes', None):
                    effective_duration = appt_type.default_duration_minutes

        # ---------------------------------------------------------------
        # Redis availability cache (TTL=120s, per-user per date-range)
        # Cache key: avail:{org_id}:{user_id}:{start}:{end}:{duration}
        # Multi-user requests are cached per-user and merged.
        # On any Redis error: log warning, compute fresh (never fail).
        # ---------------------------------------------------------------
        from routes.scheduler._availability import (
            _avail_cache_get, _avail_cache_set,
        )
        try:
            from services.redis_service import redis_service
            _redis = redis_service.get_client()
        except Exception:
            _redis = None

        start_str = slot_request.start_date.isoformat()
        end_str = slot_request.end_date.isoformat()

        if _redis is not None and len(user_ids) > 0:
            # Try to serve from cache (all user_ids must hit)
            cached_slots = []
            all_hit = True
            for uid in user_ids:
                cache_key = f"avail:{org_id}:{uid}:{start_str}:{end_str}:{effective_duration}"
                hit = _avail_cache_get(_redis, cache_key)
                if hit is None:
                    all_hit = False
                    break
                cached_slots.extend(hit)

            if all_hit:
                logger.debug(
                    "Availability cache HIT for org=%s users=%s %s..%s",
                    org_id, user_ids, start_str, end_str,
                )
                available_slots = sorted(
                    cached_slots,
                    key=lambda s: s.get("start_time", s.get("start", "")),
                )
            else:
                # Cache miss — compute and store per-user
                available_slots = _generate_available_slots(
                    db=db,
                    user_ids=user_ids,
                    start_date=slot_request.start_date,
                    end_date=slot_request.end_date,
                    duration_minutes=effective_duration,
                    org_id=org_id,
                    max_per_day=8,
                    check_cross_source=True,
                    include_user_id=True,
                    include_day_name=True,
                )
                # Store per-user slices so invalidation is targeted
                slots_by_user: dict = {}
                for slot in available_slots:
                    uid = slot.get("user_id")
                    if uid is not None:
                        slots_by_user.setdefault(uid, []).append(slot)
                for uid in user_ids:
                    cache_key = f"avail:{org_id}:{uid}:{start_str}:{end_str}:{effective_duration}"
                    _avail_cache_set(_redis, cache_key, slots_by_user.get(uid, []))
        else:
            # Redis unavailable — compute without caching
            available_slots = _generate_available_slots(
                db=db,
                user_ids=user_ids,
                start_date=slot_request.start_date,
                end_date=slot_request.end_date,
                duration_minutes=effective_duration,
                org_id=org_id,
                max_per_day=8,
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
                "duration_minutes": effective_duration,
                "user_ids": user_ids
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Scheduler tables not available for available-slots query: {e}")
        return {
            "available_slots": [],
            "total_slots": 0,
            "request": {
                "start_date": slot_request.start_date.isoformat(),
                "end_date": slot_request.end_date.isoformat(),
                "duration_minutes": slot_request.duration_minutes,
                "user_ids": user_ids
            },
            "error": "Scheduler tables not available"
        }


# ============================================================================
# BACKWARD-COMPATIBLE RE-EXPORTS
# ============================================================================
# Tests import these from routes.scheduler.availability; they live in sub-modules.
from routes.scheduler._availability import (  # noqa: F401, E402
    _generate_available_slots,
    _get_cross_source_conflicts,
    _has_cross_source_conflict,
    _get_cross_source_conflicts_batch,
)
from routes.scheduler._conflicts import (  # noqa: F401, E402
    _check_appointment_conflict,
    _check_duplicate_booking,
)
