"""
Smart Scheduler API Routes

Provides endpoints for configuring and using the AI Smart Scheduler:
- Scheduler settings (scheduling method, business hours)
- Loan officer management (add, update, availability)
- Appointment booking and management
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, time
from database import get_db
from routes.auth_deps import require_auth
import logging

from services.smart_scheduler_service import (
    get_scheduler_service,
    SmartSchedulerService,
    SchedulingMethod,
    AppointmentStatus,
    SchedulerSettings,
    LoanOfficerSchedule,
    ScheduledAppointment
)

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class BusinessHours(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"
    enabled: bool = True


class SchedulerSettingsUpdate(BaseModel):
    scheduling_method: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    buffer_between_appointments: Optional[int] = None
    business_hours: Optional[Dict[str, BusinessHours]] = None
    min_notice_hours: Optional[int] = None
    max_advance_days: Optional[int] = None


class SchedulerSettingsResponse(BaseModel):
    id: int
    scheduling_method: str
    default_duration_minutes: int
    buffer_between_appointments: int
    business_hours: Dict[str, Any]
    min_notice_hours: int
    max_advance_days: int
    last_assigned_lo_id: Optional[int]

    class Config:
        from_attributes = True


class LoanOfficerCreate(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    priority: int = 1
    max_daily_appointments: int = 8
    max_weekly_appointments: int = 40


class LoanOfficerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    max_daily_appointments: Optional[int] = None
    max_weekly_appointments: Optional[int] = None
    custom_hours: Optional[Dict[str, BusinessHours]] = None


class LoanOfficerResponse(BaseModel):
    id: int
    user_id: int
    lo_name: str
    lo_email: str
    lo_phone: Optional[str]
    is_active: bool
    priority: int
    max_daily_appointments: int
    max_weekly_appointments: int
    custom_hours: Optional[Dict[str, Any]]
    total_appointments: int
    appointments_this_week: int
    appointments_today: int

    class Config:
        from_attributes = True


class BookAppointmentRequest(BaseModel):
    contact_name: str
    contact_email: EmailStr
    appointment_time: datetime
    contact_phone: Optional[str] = None
    contact_id: Optional[int] = None
    appointment_type: str = "consultation"
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    loan_officer_id: Optional[int] = None  # Optional - will auto-assign if not provided


class AppointmentResponse(BaseModel):
    id: int
    appointment_id: str
    lo_name: str
    lo_email: str
    contact_name: str
    contact_email: str
    contact_phone: Optional[str]
    appointment_type: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    status: str
    meeting_link: Optional[str]
    notes: Optional[str]
    booked_via: str
    customer_invite_sent: bool
    lo_invite_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# SCHEDULER SETTINGS ROUTES
# =============================================================================

@router.get("/settings", response_model=SchedulerSettingsResponse)
def get_scheduler_settings(db: Session = Depends(get_db)):
    """Get current scheduler settings"""
    service = get_scheduler_service(db)
    settings = service.get_settings()

    if not settings:
        raise HTTPException(status_code=404, detail="Scheduler settings not found")

    return SchedulerSettingsResponse(
        id=settings.id,
        scheduling_method=settings.scheduling_method,
        default_duration_minutes=settings.default_duration_minutes,
        buffer_between_appointments=settings.buffer_between_appointments,
        business_hours=settings.business_hours,
        min_notice_hours=settings.min_notice_hours,
        max_advance_days=settings.max_advance_days,
        last_assigned_lo_id=settings.last_assigned_lo_id
    )


@router.put("/settings", response_model=SchedulerSettingsResponse)
def update_scheduler_settings(
    settings_update: SchedulerSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update scheduler settings"""
    service = get_scheduler_service(db)

    # Validate scheduling method
    if settings_update.scheduling_method:
        valid_methods = [m.value for m in SchedulingMethod]
        if settings_update.scheduling_method not in valid_methods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scheduling method. Must be one of: {valid_methods}"
            )

    # Convert to dict, excluding None values
    update_data = settings_update.dict(exclude_none=True)

    # Convert business hours if provided
    if "business_hours" in update_data:
        update_data["business_hours"] = {
            day: hours.dict() if hasattr(hours, 'dict') else hours
            for day, hours in update_data["business_hours"].items()
        }

    settings = service.update_settings(update_data)

    logger.info(f"Scheduler settings updated: {update_data.keys()}")

    return SchedulerSettingsResponse(
        id=settings.id,
        scheduling_method=settings.scheduling_method,
        default_duration_minutes=settings.default_duration_minutes,
        buffer_between_appointments=settings.buffer_between_appointments,
        business_hours=settings.business_hours,
        min_notice_hours=settings.min_notice_hours,
        max_advance_days=settings.max_advance_days,
        last_assigned_lo_id=settings.last_assigned_lo_id
    )


@router.get("/scheduling-methods")
def get_scheduling_methods():
    """Get available scheduling methods"""
    return {
        "methods": [
            {
                "value": SchedulingMethod.DIRECT.value,
                "label": "Direct",
                "description": "Book directly with you — no routing or distribution"
            },
            {
                "value": SchedulingMethod.ROUND_ROBIN.value,
                "label": "Round Robin",
                "description": "Distribute appointments evenly among all active loan officers"
            },
            {
                "value": SchedulingMethod.PRIORITY.value,
                "label": "Priority",
                "description": "Assign to highest priority loan officer who is available"
            },
            {
                "value": SchedulingMethod.AVAILABILITY.value,
                "label": "Availability",
                "description": "Assign to first available loan officer"
            },
            {
                "value": SchedulingMethod.LOAD_BALANCED.value,
                "label": "Load Balanced",
                "description": "Assign to loan officer with fewest appointments this week"
            }
        ]
    }


# =============================================================================
# LOAN OFFICER ROUTES
# =============================================================================

@router.get("/loan-officers", response_model=List[LoanOfficerResponse])
def get_loan_officers(
    active_only: bool = Query(False, description="Only return active LOs"),
    db: Session = Depends(get_db)
):
    """Get all loan officers in the scheduling pool"""
    service = get_scheduler_service(db)

    if active_only:
        los = service.get_active_loan_officers()
    else:
        los = db.query(LoanOfficerSchedule).order_by(
            LoanOfficerSchedule.priority.desc()
        ).all()

    return [LoanOfficerResponse(
        id=lo.id,
        user_id=lo.user_id,
        lo_name=lo.lo_name,
        lo_email=lo.lo_email,
        lo_phone=lo.lo_phone,
        is_active=lo.is_active,
        priority=lo.priority,
        max_daily_appointments=lo.max_daily_appointments,
        max_weekly_appointments=lo.max_weekly_appointments,
        custom_hours=lo.custom_hours,
        total_appointments=lo.total_appointments or 0,
        appointments_this_week=lo.appointments_this_week or 0,
        appointments_today=lo.appointments_today or 0
    ) for lo in los]


@router.post("/loan-officers", response_model=LoanOfficerResponse)
def add_loan_officer(
    lo_data: LoanOfficerCreate,
    db: Session = Depends(get_db)
):
    """Add a loan officer to the scheduling pool"""
    service = get_scheduler_service(db)

    # Check if LO already exists
    existing = db.query(LoanOfficerSchedule).filter(
        LoanOfficerSchedule.lo_email == lo_data.email
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Loan officer with email {lo_data.email} already exists"
        )

    lo = service.add_loan_officer(
        user_id=lo_data.user_id,
        name=lo_data.name,
        email=lo_data.email,
        phone=lo_data.phone,
        priority=lo_data.priority
    )

    # Update additional fields
    lo.max_daily_appointments = lo_data.max_daily_appointments
    lo.max_weekly_appointments = lo_data.max_weekly_appointments
    db.commit()
    db.refresh(lo)

    return LoanOfficerResponse(
        id=lo.id,
        user_id=lo.user_id,
        lo_name=lo.lo_name,
        lo_email=lo.lo_email,
        lo_phone=lo.lo_phone,
        is_active=lo.is_active,
        priority=lo.priority,
        max_daily_appointments=lo.max_daily_appointments,
        max_weekly_appointments=lo.max_weekly_appointments,
        custom_hours=lo.custom_hours,
        total_appointments=lo.total_appointments or 0,
        appointments_this_week=lo.appointments_this_week or 0,
        appointments_today=lo.appointments_today or 0
    )


@router.put("/loan-officers/{lo_id}", response_model=LoanOfficerResponse)
def update_loan_officer(
    lo_id: int,
    lo_update: LoanOfficerUpdate,
    db: Session = Depends(get_db)
):
    """Update a loan officer's scheduling settings"""
    service = get_scheduler_service(db)

    # Build update dict
    update_data = {}
    if lo_update.name:
        update_data["lo_name"] = lo_update.name
    if lo_update.email:
        update_data["lo_email"] = lo_update.email
    if lo_update.phone is not None:
        update_data["lo_phone"] = lo_update.phone
    if lo_update.is_active is not None:
        update_data["is_active"] = lo_update.is_active
    if lo_update.priority is not None:
        update_data["priority"] = lo_update.priority
    if lo_update.max_daily_appointments is not None:
        update_data["max_daily_appointments"] = lo_update.max_daily_appointments
    if lo_update.max_weekly_appointments is not None:
        update_data["max_weekly_appointments"] = lo_update.max_weekly_appointments
    if lo_update.custom_hours is not None:
        update_data["custom_hours"] = {
            day: hours.dict() if hasattr(hours, 'dict') else hours
            for day, hours in lo_update.custom_hours.items()
        }

    lo = service.update_loan_officer(lo_id, update_data)

    if not lo:
        raise HTTPException(status_code=404, detail="Loan officer not found")

    return LoanOfficerResponse(
        id=lo.id,
        user_id=lo.user_id,
        lo_name=lo.lo_name,
        lo_email=lo.lo_email,
        lo_phone=lo.lo_phone,
        is_active=lo.is_active,
        priority=lo.priority,
        max_daily_appointments=lo.max_daily_appointments,
        max_weekly_appointments=lo.max_weekly_appointments,
        custom_hours=lo.custom_hours,
        total_appointments=lo.total_appointments or 0,
        appointments_this_week=lo.appointments_this_week or 0,
        appointments_today=lo.appointments_today or 0
    )


@router.delete("/loan-officers/{lo_id}")
def remove_loan_officer(
    lo_id: int,
    db: Session = Depends(get_db)
):
    """Remove a loan officer from the scheduling pool (soft delete - sets inactive)"""
    service = get_scheduler_service(db)
    lo = service.update_loan_officer(lo_id, {"is_active": False})

    if not lo:
        raise HTTPException(status_code=404, detail="Loan officer not found")

    return {"success": True, "message": f"Loan officer {lo.lo_name} deactivated"}


# =============================================================================
# APPOINTMENT ROUTES
# =============================================================================

@router.post("/appointments", response_model=dict)
def book_appointment(
    booking: BookAppointmentRequest,
    db: Session = Depends(get_db)
):
    """Book a new appointment (AI will auto-assign loan officer if not specified)"""
    service = get_scheduler_service(db)

    result = service.book_appointment(
        contact_name=booking.contact_name,
        contact_email=booking.contact_email,
        appointment_time=booking.appointment_time,
        contact_phone=booking.contact_phone,
        contact_id=booking.contact_id,
        appointment_type=booking.appointment_type,
        duration_minutes=booking.duration_minutes,
        notes=booking.notes,
        loan_officer_id=booking.loan_officer_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Booking failed"))

    return result


@router.get("/appointments", response_model=List[AppointmentResponse])
def get_appointments(
    loan_officer_id: Optional[int] = Query(None, description="Filter by loan officer"),
    status: Optional[str] = Query(None, description="Filter by status"),
    days_ahead: int = Query(30, description="Days to look ahead (default 30)"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: Session = Depends(get_db)
):
    """Get upcoming appointments"""
    service = get_scheduler_service(db)
    appointments = service.get_appointments_in_range(
        loan_officer_id=loan_officer_id,
        start_date=start_date,
        end_date=end_date,
        days_ahead=days_ahead
    )

    if status:
        appointments = [a for a in appointments if a.status == status]

    return [AppointmentResponse(
        id=a.id,
        appointment_id=a.appointment_id,
        lo_name=a.lo_name or '',
        lo_email=a.lo_email or '',
        contact_name=a.contact_name or '',
        contact_email=a.contact_email or '',
        contact_phone=a.contact_phone,
        appointment_type=a.appointment_type or 'consultation',
        start_time=a.start_time,
        end_time=a.end_time,
        duration_minutes=a.duration_minutes or 30,
        status=a.status or 'scheduled',
        meeting_link=a.meeting_link,
        notes=a.notes,
        booked_via=a.booked_via or 'unknown',
        customer_invite_sent=bool(a.customer_invite_sent),
        lo_invite_sent=bool(a.lo_invite_sent),
        created_at=a.created_at
    ) for a in appointments]


@router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific appointment"""
    service = get_scheduler_service(db)
    appointment = service.get_appointment(appointment_id)

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return AppointmentResponse(
        id=appointment.id,
        appointment_id=appointment.appointment_id,
        lo_name=appointment.lo_name,
        lo_email=appointment.lo_email,
        contact_name=appointment.contact_name,
        contact_email=appointment.contact_email,
        contact_phone=appointment.contact_phone,
        appointment_type=appointment.appointment_type,
        start_time=appointment.start_time,
        end_time=appointment.end_time,
        duration_minutes=appointment.duration_minutes,
        status=appointment.status,
        meeting_link=appointment.meeting_link,
        notes=appointment.notes,
        booked_via=appointment.booked_via,
        customer_invite_sent=appointment.customer_invite_sent,
        lo_invite_sent=appointment.lo_invite_sent,
        created_at=appointment.created_at
    )


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: str,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Cancel an appointment"""
    service = get_scheduler_service(db)
    success = service.cancel_appointment(appointment_id, reason)

    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {"success": True, "message": f"Appointment {appointment_id} cancelled"}


# =============================================================================
# QUICK SETUP ROUTE
# =============================================================================

@router.post("/quick-setup")
def quick_setup_scheduler(
    scheduling_method: str = "round_robin",
    db: Session = Depends(get_db)
):
    """
    Quick setup for the scheduler - initializes settings and prompts for LO addition.
    Use this for initial configuration.
    """
    service = get_scheduler_service(db)

    # Update scheduling method
    settings = service.update_settings({"scheduling_method": scheduling_method})

    # Check for existing LOs
    los = service.get_active_loan_officers()

    return {
        "success": True,
        "settings": {
            "scheduling_method": settings.scheduling_method,
            "default_duration_minutes": settings.default_duration_minutes,
            "business_hours": settings.business_hours
        },
        "loan_officers_count": len(los),
        "loan_officers": [{"id": lo.id, "name": lo.lo_name, "email": lo.lo_email} for lo in los],
        "next_steps": [
            "Add loan officers via POST /api/v1/scheduler/loan-officers" if not los else None,
            "Configure business hours via PUT /api/v1/scheduler/settings",
            "Start booking appointments via POST /api/v1/scheduler/appointments"
        ]
    }
