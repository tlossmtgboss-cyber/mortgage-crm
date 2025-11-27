"""
Smart Scheduler API Routes - Pipeline 360 AI-Native Appointment Scheduling

Comprehensive API endpoints for:
- Scheduler configuration management
- Availability slot management
- Appointment booking (internal + public)
- Routing rules
- Blocked time management
- Booking links
- AI-powered slot recommendations
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import logging
import pytz
from enum import Enum

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode, RoutingStrategy,
    ReminderChannel, DayOfWeek, SlotPriority, DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_WORKING_HOURS
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Smart Scheduler"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user = None
_models = None  # Will hold all scheduler models


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    return _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class WorkingHoursDay(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"
    enabled: bool = True


class SchedulerConfigCreate(BaseModel):
    config_name: str
    description: Optional[str] = None
    timezone: str = "America/Chicago"
    default_duration_minutes: int = 30
    buffer_before_minutes: int = 5
    buffer_after_minutes: int = 5
    min_notice_hours: int = 2
    max_advance_days: int = 60
    max_meetings_per_day: int = 8
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = "relationship"
    ai_scheduling_enabled: bool = True


class SchedulerConfigUpdate(BaseModel):
    config_name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    min_notice_hours: Optional[int] = None
    max_advance_days: Optional[int] = None
    max_meetings_per_day: Optional[int] = None
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = None
    ai_scheduling_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class AppointmentTypeCreate(BaseModel):
    type_key: str
    type_name: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    default_duration_minutes: int = 30
    allowed_durations: List[int] = [15, 30, 45, 60]
    allowed_modes: List[str] = ["video", "phone"]
    requires_loan_id: bool = False
    requires_lead_id: bool = False
    intake_questions: List[Dict] = []
    color: str = "#3b82f6"
    icon: str = "calendar"
    is_public: bool = True
    public_slug: Optional[str] = None


class AppointmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    allowed_durations: Optional[List[int]] = None
    allowed_modes: Optional[List[str]] = None
    intake_questions: Optional[List[Dict]] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class AvailabilitySlotCreate(BaseModel):
    day_of_week: Optional[str] = None
    specific_date: Optional[date] = None
    start_time: str  # "09:00"
    end_time: str    # "17:00"
    priority: str = "standard"
    is_recurring: bool = True
    allowed_meeting_types: List[str] = []
    max_bookings: int = 1


class AvailabilitySlotUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_meeting_types: Optional[List[str]] = None


class AppointmentCreate(BaseModel):
    appointment_type_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = "video"
    scheduled_start: datetime
    duration_minutes: int = 30
    timezone: str = "America/Chicago"

    # Attendee info (for external bookings)
    attendee_name: Optional[str] = None
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None

    # Related entities
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None

    # Intake responses
    intake_responses: Dict = {}

    # AI context
    booked_by_ai: bool = False
    ai_booking_context: Optional[Dict] = None


class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    meeting_mode: Optional[str] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    status: Optional[str] = None
    cancellation_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None


class BlockedTimeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    block_type: str = "custom"
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool = False
    is_recurring: bool = False
    recurrence_pattern: Optional[Dict] = None
    applies_to_all_users: bool = False


class BookingLinkCreate(BaseModel):
    slug: str
    link_name: str
    description: Optional[str] = None
    appointment_type_ids: List[int] = []
    single_appointment_type_id: Optional[int] = None
    is_public: bool = True
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    routing_strategy: str = "relationship"
    assigned_users: List[int] = []


class AvailableSlotsRequest(BaseModel):
    appointment_type_id: Optional[int] = None
    meeting_type: Optional[str] = None
    duration_minutes: int = 30
    start_date: date
    end_date: date
    timezone: str = "America/Chicago"
    user_ids: List[int] = []  # Empty = any available user
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None


class SlotRecommendation(BaseModel):
    slot_start: datetime
    slot_end: datetime
    user_id: int
    user_name: str
    score: float  # AI-calculated score
    reasons: List[str]  # Why this slot is recommended


# ============================================================================
# SCHEDULER CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_scheduler_config(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the current user's scheduler configuration"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Return default config structure
        return {
            "config": None,
            "defaults": {
                "timezone": "America/Chicago",
                "default_duration_minutes": 30,
                "buffer_before_minutes": 5,
                "buffer_after_minutes": 5,
                "min_notice_hours": 2,
                "max_advance_days": 60,
                "max_meetings_per_day": 8,
                "working_hours": DEFAULT_WORKING_HOURS
            }
        }

    return {
        "config": {
            "id": config.id,
            "config_name": config.config_name,
            "description": config.description,
            "timezone": config.timezone,
            "default_duration_minutes": config.default_duration_minutes,
            "buffer_before_minutes": config.buffer_before_minutes,
            "buffer_after_minutes": config.buffer_after_minutes,
            "min_notice_hours": config.min_notice_hours,
            "max_advance_days": config.max_advance_days,
            "max_meetings_per_day": config.max_meetings_per_day,
            "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
            "routing_strategy": config.routing_strategy.value if config.routing_strategy else "relationship",
            "ai_scheduling_enabled": config.ai_scheduling_enabled,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }
    }


@router.post("/config")
async def create_scheduler_config(
    config_data: SchedulerConfigCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create scheduler configuration for the current user"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    # Check if config already exists
    existing = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Configuration already exists. Use PUT to update.")

    # Parse routing strategy
    routing_strategy = None
    if config_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(config_data.routing_strategy)
        except ValueError:
            routing_strategy = RoutingStrategy.RELATIONSHIP

    config = SchedulerConfig(
        user_id=user.id,
        config_name=config_data.config_name,
        description=config_data.description,
        timezone=config_data.timezone,
        default_duration_minutes=config_data.default_duration_minutes,
        buffer_before_minutes=config_data.buffer_before_minutes,
        buffer_after_minutes=config_data.buffer_after_minutes,
        min_notice_hours=config_data.min_notice_hours,
        max_advance_days=config_data.max_advance_days,
        max_meetings_per_day=config_data.max_meetings_per_day,
        working_hours=config_data.working_hours or DEFAULT_WORKING_HOURS,
        routing_strategy=routing_strategy,
        ai_scheduling_enabled=config_data.ai_scheduling_enabled
    )

    db.add(config)
    db.commit()
    db.refresh(config)

    return {"message": "Scheduler configuration created", "config_id": config.id}


@router.put("/config")
async def update_scheduler_config(
    config_data: SchedulerConfigUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update scheduler configuration"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Update fields
    update_fields = config_data.dict(exclude_unset=True)
    for field, value in update_fields.items():
        if field == "routing_strategy" and value:
            try:
                value = RoutingStrategy(value)
            except ValueError:
                continue
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"message": "Configuration updated", "config_id": config.id}


# ============================================================================
# APPOINTMENT TYPE ENDPOINTS
# ============================================================================

@router.get("/appointment-types")
async def list_appointment_types(
    request: Request,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """List all appointment types"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get user's config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Return default types
        return {"appointment_types": DEFAULT_APPOINTMENT_TYPES, "source": "defaults"}

    query = db.query(AppointmentType).filter(AppointmentType.config_id == config.id)

    if not include_inactive:
        query = query.filter(AppointmentType.is_active == True)

    types = query.order_by(AppointmentType.display_order).all()

    return {
        "appointment_types": [
            {
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "meeting_type": t.meeting_type.value if t.meeting_type else "custom",
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": t.allowed_durations,
                "allowed_modes": t.allowed_modes,
                "requires_loan_id": t.requires_loan_id,
                "requires_lead_id": t.requires_lead_id,
                "intake_questions": t.intake_questions,
                "color": t.color,
                "icon": t.icon,
                "is_public": t.is_public,
                "public_slug": t.public_slug,
                "is_active": t.is_active
            }
            for t in types
        ],
        "source": "database"
    }


@router.post("/appointment-types")
async def create_appointment_type(
    type_data: AppointmentTypeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment type"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Auto-create config
        config = SchedulerConfig(
            user_id=user.id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    # Check for duplicate type_key
    existing = db.query(AppointmentType).filter(
        AppointmentType.config_id == config.id,
        AppointmentType.type_key == type_data.type_key
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Appointment type with this key already exists")

    # Parse meeting type
    meeting_type = MeetingType.CUSTOM
    if type_data.meeting_type:
        try:
            meeting_type = MeetingType(type_data.meeting_type)
        except ValueError:
            pass

    appt_type = AppointmentType(
        config_id=config.id,
        type_key=type_data.type_key,
        type_name=type_data.type_name,
        description=type_data.description,
        meeting_type=meeting_type,
        default_duration_minutes=type_data.default_duration_minutes,
        allowed_durations=type_data.allowed_durations,
        allowed_modes=type_data.allowed_modes,
        requires_loan_id=type_data.requires_loan_id,
        requires_lead_id=type_data.requires_lead_id,
        intake_questions=type_data.intake_questions,
        color=type_data.color,
        icon=type_data.icon,
        is_public=type_data.is_public,
        public_slug=type_data.public_slug
    )

    db.add(appt_type)
    db.commit()
    db.refresh(appt_type)

    return {"message": "Appointment type created", "type_id": appt_type.id}


@router.put("/appointment-types/{type_id}")
async def update_appointment_type(
    type_id: int,
    type_data: AppointmentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment type"""
    user = await get_current_user(request, db)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    # Verify ownership
    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    update_fields = type_data.dict(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(appt_type, field, value)

    db.commit()

    return {"message": "Appointment type updated"}


@router.delete("/appointment-types/{type_id}")
async def delete_appointment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete (deactivate) an appointment type"""
    user = await get_current_user(request, db)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    appt_type.is_active = False
    db.commit()

    return {"message": "Appointment type deactivated"}


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

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    target_user_id = user_id or user.id

    # Get config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == target_user_id
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
        or_(
            BlockedTime.user_id == target_user_id,
            BlockedTime.applies_to_all_users == True
        ),
        BlockedTime.start_datetime <= end_dt,
        BlockedTime.end_datetime >= start_dt
    ).all()

    # Get existing appointments
    appointments = db.query(Appointment).filter(
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

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        raise HTTPException(status_code=400, detail="Please create scheduler config first")

    # Parse times
    try:
        start_time = datetime.strptime(slot_data.start_time, "%H:%M").time()
        end_time = datetime.strptime(slot_data.end_time, "%H:%M").time()
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
            pass

    slot = AvailabilitySlot(
        config_id=config.id,
        user_id=user.id,
        day_of_week=day_of_week,
        specific_date=slot_data.specific_date,
        start_time=start_time,
        end_time=end_time,
        priority=priority,
        is_recurring=slot_data.is_recurring,
        allowed_meeting_types=slot_data.allowed_meeting_types,
        max_bookings=slot_data.max_bookings
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

    AvailabilitySlot = _models['AvailabilitySlot']

    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.user_id == user.id
    ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    db.delete(slot)
    db.commit()

    return {"message": "Slot deleted"}


# ============================================================================
# APPOINTMENT ENDPOINTS
# ============================================================================

@router.get("/appointments")
async def list_appointments(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List appointments with filters"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    query = db.query(Appointment).filter(
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    )

    if start_date:
        query = query.filter(Appointment.scheduled_start >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(Appointment.scheduled_start <= datetime.combine(end_date, time.max))

    if status:
        try:
            status_enum = AppointmentStatus(status)
            query = query.filter(Appointment.status == status_enum)
        except ValueError:
            pass

    if lead_id:
        query = query.filter(Appointment.lead_id == lead_id)

    if loan_id:
        query = query.filter(Appointment.loan_id == loan_id)

    total = query.count()
    appointments = query.order_by(Appointment.scheduled_start.desc()).offset(offset).limit(limit).all()

    return {
        "appointments": [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "meeting_type": a.meeting_type.value if a.meeting_type else None,
                "meeting_mode": a.meeting_mode.value if a.meeting_mode else None,
                "scheduled_start": a.scheduled_start.isoformat(),
                "scheduled_end": a.scheduled_end.isoformat(),
                "duration_minutes": a.duration_minutes,
                "status": a.status.value if a.status else None,
                "attendee_name": a.attendee_name,
                "attendee_email": a.attendee_email,
                "video_link": a.video_link,
                "lead_id": a.lead_id,
                "loan_id": a.loan_id,
                "booked_by_ai": a.booked_by_ai,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in appointments
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get appointment details"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {
        "appointment": {
            "id": appointment.id,
            "appointment_type_id": appointment.appointment_type_id,
            "title": appointment.title,
            "description": appointment.description,
            "meeting_type": appointment.meeting_type.value if appointment.meeting_type else None,
            "meeting_mode": appointment.meeting_mode.value if appointment.meeting_mode else None,
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
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
            "status": appointment.status.value if appointment.status else None,
            "lead_id": appointment.lead_id,
            "loan_id": appointment.loan_id,
            "contact_id": appointment.contact_id,
            "assigned_user_id": appointment.assigned_user_id,
            "booked_by_ai": appointment.booked_by_ai,
            "ai_booking_context": appointment.ai_booking_context,
            "internal_notes": appointment.internal_notes,
            "meeting_notes": appointment.meeting_notes,
            "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
            "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None
        }
    }


@router.post("/appointments")
async def create_appointment(
    appt_data: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    # Calculate end time
    scheduled_end = appt_data.scheduled_start + timedelta(minutes=appt_data.duration_minutes)

    # Parse enums
    meeting_type = MeetingType.CUSTOM
    if appt_data.meeting_type:
        try:
            meeting_type = MeetingType(appt_data.meeting_type)
        except ValueError:
            pass

    meeting_mode = MeetingMode.VIDEO
    if appt_data.meeting_mode:
        try:
            meeting_mode = MeetingMode(appt_data.meeting_mode)
        except ValueError:
            pass

    appointment = Appointment(
        appointment_type_id=appt_data.appointment_type_id,
        assigned_user_id=appt_data.assigned_user_id or user.id,
        created_by_user_id=user.id,
        lead_id=appt_data.lead_id,
        loan_id=appt_data.loan_id,
        contact_id=appt_data.contact_id,
        title=appt_data.title,
        description=appt_data.description,
        meeting_type=meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=appt_data.scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=appt_data.duration_minutes,
        timezone=appt_data.timezone,
        attendee_name=appt_data.attendee_name,
        attendee_email=appt_data.attendee_email,
        attendee_phone=appt_data.attendee_phone,
        attendee_notes=appt_data.attendee_notes,
        intake_responses=appt_data.intake_responses,
        status=AppointmentStatus.BOOKED,
        booked_by_ai=appt_data.booked_by_ai,
        ai_booking_context=appt_data.ai_booking_context
    )

    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    logger.info(f"Appointment created: {appointment.id} by user {user.id}")

    return {
        "message": "Appointment created",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat()
    }


@router.put("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: int,
    appt_data: AppointmentUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    update_fields = appt_data.dict(exclude_unset=True)

    # Handle status changes
    if "status" in update_fields:
        try:
            new_status = AppointmentStatus(update_fields["status"])
            update_fields["status"] = new_status
            update_fields["status_changed_at"] = datetime.utcnow()
            update_fields["status_changed_by"] = user.id

            if new_status == AppointmentStatus.COMPLETED:
                update_fields["completed_at"] = datetime.utcnow()
            elif new_status == AppointmentStatus.NO_SHOW:
                update_fields["no_show_at"] = datetime.utcnow()
            elif new_status == AppointmentStatus.CANCELLED:
                update_fields["cancelled_at"] = datetime.utcnow()
        except ValueError:
            del update_fields["status"]

    # Handle meeting mode
    if "meeting_mode" in update_fields:
        try:
            update_fields["meeting_mode"] = MeetingMode(update_fields["meeting_mode"])
        except ValueError:
            del update_fields["meeting_mode"]

    # Handle rescheduling
    if "scheduled_start" in update_fields:
        new_start = update_fields["scheduled_start"]
        duration = appt_data.duration_minutes or appointment.duration_minutes
        update_fields["scheduled_end"] = new_start + timedelta(minutes=duration)
        update_fields["reschedule_count"] = appointment.reschedule_count + 1

    for field, value in update_fields.items():
        setattr(appointment, field, value)

    db.commit()

    return {"message": "Appointment updated"}


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    reason: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Cancel an appointment"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.utcnow()
    appointment.cancellation_reason = reason
    appointment.status_changed_by = user.id
    appointment.status_changed_at = datetime.utcnow()

    db.commit()

    logger.info(f"Appointment {appointment_id} cancelled by user {user.id}")

    return {"message": "Appointment cancelled"}


# ============================================================================
# BLOCKED TIME ENDPOINTS
# ============================================================================

@router.get("/blocked-times")
async def list_blocked_times(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """List blocked time periods"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    query = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        or_(
            BlockedTime.user_id == user.id,
            BlockedTime.applies_to_all_users == True
        )
    )

    if start_date:
        query = query.filter(BlockedTime.end_datetime >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(BlockedTime.start_datetime <= datetime.combine(end_date, time.max))

    blocked = query.order_by(BlockedTime.start_datetime).all()

    return {
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "block_type": b.block_type,
                "start_datetime": b.start_datetime.isoformat(),
                "end_datetime": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "is_recurring": b.is_recurring,
                "recurrence_pattern": b.recurrence_pattern,
                "applies_to_all_users": b.applies_to_all_users
            }
            for b in blocked
        ]
    }


@router.post("/blocked-times")
async def create_blocked_time(
    block_data: BlockedTimeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a blocked time period"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    blocked = BlockedTime(
        user_id=user.id,
        title=block_data.title,
        description=block_data.description,
        block_type=block_data.block_type,
        start_datetime=block_data.start_datetime,
        end_datetime=block_data.end_datetime,
        all_day=block_data.all_day,
        is_recurring=block_data.is_recurring,
        recurrence_pattern=block_data.recurrence_pattern,
        applies_to_all_users=block_data.applies_to_all_users,
        created_by_id=user.id
    )

    db.add(blocked)
    db.commit()
    db.refresh(blocked)

    return {"message": "Blocked time created", "blocked_time_id": blocked.id}


@router.delete("/blocked-times/{block_id}")
async def delete_blocked_time(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a blocked time period"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    blocked = db.query(BlockedTime).filter(
        BlockedTime.id == block_id,
        BlockedTime.user_id == user.id
    ).first()

    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked time not found")

    db.delete(blocked)
    db.commit()

    return {"message": "Blocked time deleted"}


# ============================================================================
# BOOKING LINK ENDPOINTS
# ============================================================================

@router.get("/booking-links")
async def list_booking_links(
    request: Request,
    db: Session = Depends(get_db)
):
    """List user's booking links"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    links = db.query(BookingLink).filter(
        BookingLink.user_id == user.id,
        BookingLink.is_active == True
    ).all()

    return {
        "booking_links": [
            {
                "id": link.id,
                "slug": link.slug,
                "link_name": link.link_name,
                "description": link.description,
                "url": f"/book/{link.slug}",
                "is_public": link.is_public,
                "view_count": link.view_count,
                "booking_count": link.booking_count,
                "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
                "created_at": link.created_at.isoformat() if link.created_at else None
            }
            for link in links
        ]
    }


@router.post("/booking-links")
async def create_booking_link(
    link_data: BookingLinkCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a booking link"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    # Check for duplicate slug
    existing = db.query(BookingLink).filter(BookingLink.slug == link_data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already in use")

    # Parse routing strategy
    routing_strategy = RoutingStrategy.RELATIONSHIP
    if link_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(link_data.routing_strategy)
        except ValueError:
            pass

    link = BookingLink(
        user_id=user.id,
        slug=link_data.slug,
        link_name=link_data.link_name,
        description=link_data.description,
        appointment_type_ids=link_data.appointment_type_ids,
        single_appointment_type_id=link_data.single_appointment_type_id,
        is_public=link_data.is_public,
        custom_title=link_data.custom_title,
        custom_description=link_data.custom_description,
        routing_strategy=routing_strategy,
        assigned_users=link_data.assigned_users
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "message": "Booking link created",
        "link_id": link.id,
        "url": f"/book/{link.slug}"
    }


@router.delete("/booking-links/{link_id}")
async def delete_booking_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a booking link"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    link = db.query(BookingLink).filter(
        BookingLink.id == link_id,
        BookingLink.user_id == user.id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    link.is_active = False
    db.commit()

    return {"message": "Booking link deactivated"}


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
    This is the core slot calculation engine.
    """
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    # Determine which users to check
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    available_slots = []

    for target_user_id in user_ids:
        # Get user's config
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == target_user_id
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        max_per_day = config.max_meetings_per_day if config else 8
        min_notice = config.min_notice_hours if config else 2

        # Get blocked times for this user
        start_dt = datetime.combine(slot_request.start_date, time.min)
        end_dt = datetime.combine(slot_request.end_date, time.max)

        blocked_times = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == target_user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        ).all()

        # Get existing appointments
        existing_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == target_user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        ).all()

        # Generate slots for each day
        current_date = slot_request.start_date
        now = datetime.utcnow()
        min_booking_time = now + timedelta(hours=min_notice)

        while current_date <= slot_request.end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            # Count appointments for this day
            day_appts = [a for a in existing_appts
                        if a.scheduled_start.date() == current_date]
            if len(day_appts) >= max_per_day:
                current_date += timedelta(days=1)
                continue

            # Parse working hours
            try:
                start_time = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                end_time = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            # Generate slots at 30-minute intervals
            slot_start = datetime.combine(current_date, start_time)
            day_end = datetime.combine(current_date, end_time)

            while slot_start + timedelta(minutes=slot_request.duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=slot_request.duration_minutes)

                # Check if slot is in the past or within min notice
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check for conflicts with blocked time
                blocked = False
                for bt in blocked_times:
                    if (slot_start < bt.end_datetime and slot_end > bt.start_datetime):
                        blocked = True
                        break

                if blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check for conflicts with existing appointments (including buffers)
                conflict = False
                for appt in existing_appts:
                    appt_start_with_buffer = appt.scheduled_start - timedelta(minutes=buffer_before)
                    appt_end_with_buffer = appt.scheduled_end + timedelta(minutes=buffer_after)

                    if (slot_start < appt_end_with_buffer and slot_end > appt_start_with_buffer):
                        conflict = True
                        break

                if not conflict:
                    available_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "user_id": target_user_id,
                        "date": current_date.isoformat(),
                        "day": day_name
                    })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Sort by datetime
    available_slots.sort(key=lambda x: x["start"])

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
        slot_dt = datetime.fromisoformat(slot["start"])
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
        days_from_now = (slot_dt.date() - datetime.now().date()).days
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
# PUBLIC BOOKING ENDPOINTS (No auth required)
# ============================================================================

@router.get("/public/book/{slug}")
async def get_public_booking_page(
    slug: str,
    db: Session = Depends(get_db)
):
    """Get public booking page data"""
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # Increment view count
    link.view_count += 1
    db.commit()

    # Get available appointment types
    appointment_types = []
    if link.single_appointment_type_id:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == link.single_appointment_type_id,
            AppointmentType.is_active == True
        ).first()
        if appt_type:
            appointment_types.append({
                "id": appt_type.id,
                "type_key": appt_type.type_key,
                "type_name": appt_type.type_name,
                "description": appt_type.description,
                "default_duration_minutes": appt_type.default_duration_minutes,
                "allowed_durations": appt_type.allowed_durations,
                "intake_questions": appt_type.intake_questions,
                "color": appt_type.color
            })
    elif link.appointment_type_ids:
        types = db.query(AppointmentType).filter(
            AppointmentType.id.in_(link.appointment_type_ids),
            AppointmentType.is_active == True
        ).all()
        for t in types:
            appointment_types.append({
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": t.allowed_durations,
                "intake_questions": t.intake_questions,
                "color": t.color
            })

    return {
        "booking_page": {
            "title": link.custom_title or link.link_name,
            "description": link.custom_description or link.description,
            "logo_url": link.custom_logo_url,
            "color": link.custom_color,
            "appointment_types": appointment_types
        }
    }


@router.post("/public/book/{slug}/slots")
async def get_public_available_slots(
    slug: str,
    appointment_type_id: int = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    duration_minutes: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get available slots for public booking"""
    BookingLink = _models['BookingLink']
    SchedulerConfig = _models['SchedulerConfig']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # Get user IDs to check
    user_ids = link.assigned_users if link.assigned_users else [link.user_id]

    all_slots = []

    for target_user_id in user_ids:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == target_user_id
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        min_notice = config.min_notice_hours if config else 2

        # Get blocked times
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        blocked_times = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == target_user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        ).all()

        # Get existing appointments
        existing_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == target_user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        ).all()

        # Generate slots
        current_date = start_date
        now = datetime.utcnow()
        min_booking_time = now + timedelta(hours=min_notice)

        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            try:
                start_time = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                end_time = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, start_time)
            day_end = datetime.combine(current_date, end_time)

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check conflicts
                blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )

                if not blocked:
                    conflict = any(
                        slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                        slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                        for appt in existing_appts
                    )

                    if not conflict:
                        all_slots.append({
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": current_date.isoformat()
                        })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Remove duplicates and sort
    unique_slots = list({s["start"]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x["start"])

    return {"available_slots": unique_slots}


@router.post("/public/book/{slug}/confirm")
async def confirm_public_booking(
    slug: str,
    appointment_type_id: int,
    slot_start: datetime,
    duration_minutes: int,
    attendee_name: str,
    attendee_email: EmailStr,
    attendee_phone: Optional[str] = None,
    intake_responses: Dict = {},
    db: Session = Depends(get_db)
):
    """Confirm a public booking"""
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']
    Appointment = _models['Appointment']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    appt_type = db.query(AppointmentType).filter(
        AppointmentType.id == appointment_type_id,
        AppointmentType.is_active == True
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    # Determine assigned user (for now, use link owner)
    assigned_user_id = link.user_id

    # Create appointment
    slot_end = slot_start + timedelta(minutes=duration_minutes)

    appointment = Appointment(
        appointment_type_id=appointment_type_id,
        assigned_user_id=assigned_user_id,
        title=f"{appt_type.type_name} with {attendee_name}",
        description=appt_type.description,
        meeting_type=appt_type.meeting_type,
        meeting_mode=MeetingMode.VIDEO,
        scheduled_start=slot_start,
        scheduled_end=slot_end,
        duration_minutes=duration_minutes,
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        intake_responses=intake_responses,
        status=AppointmentStatus.BOOKED,
        external_source="booking_link"
    )

    db.add(appointment)

    # Update link stats
    link.booking_count += 1
    link.current_bookings += 1
    link.last_booked_at = datetime.utcnow()

    db.commit()
    db.refresh(appointment)

    logger.info(f"Public booking confirmed: {appointment.id} via link {slug}")

    return {
        "message": "Appointment booked successfully",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "confirmation_details": {
            "title": appointment.title,
            "date": appointment.scheduled_start.strftime("%A, %B %d, %Y"),
            "time": appointment.scheduled_start.strftime("%I:%M %p"),
            "duration": f"{duration_minutes} minutes"
        }
    }


# ============================================================================
# SEED DEFAULT APPOINTMENT TYPES
# ============================================================================

@router.post("/seed-defaults")
async def seed_default_appointment_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """Seed default appointment types for the user"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        config = SchedulerConfig(
            user_id=user.id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    created_count = 0

    for default_type in DEFAULT_APPOINTMENT_TYPES:
        # Check if already exists
        existing = db.query(AppointmentType).filter(
            AppointmentType.config_id == config.id,
            AppointmentType.type_key == default_type["type_key"]
        ).first()

        if not existing:
            appt_type = AppointmentType(
                config_id=config.id,
                type_key=default_type["type_key"],
                type_name=default_type["type_name"],
                description=default_type["description"],
                meeting_type=default_type["meeting_type"],
                default_duration_minutes=default_type["default_duration_minutes"],
                allowed_durations=default_type["allowed_durations"],
                requires_loan_id=default_type["requires_loan_id"],
                requires_lead_id=default_type["requires_lead_id"],
                intake_questions=default_type["intake_questions"],
                color=default_type["color"],
                icon=default_type["icon"],
                is_public=True,
                public_slug=f"{user.id}-{default_type['type_key']}"
            )
            db.add(appt_type)
            created_count += 1

    db.commit()

    return {
        "message": f"Seeded {created_count} default appointment types",
        "config_id": config.id
    }
