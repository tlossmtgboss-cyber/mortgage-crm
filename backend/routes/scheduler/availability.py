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
    _generate_available_slots,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


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

    _models = get_models()
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

    _models = get_models()
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
# SLOT AVAILABILITY ENGINE (authenticated)
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
