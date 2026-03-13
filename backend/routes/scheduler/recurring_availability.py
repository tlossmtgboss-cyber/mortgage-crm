"""
Recurring Availability Routes

Endpoints for managing weekly recurring availability patterns, date exceptions,
and org-level templates.

Endpoints:
  - GET    /availability/schedule                  Get weekly schedule
  - PUT    /availability/schedule                  Update weekly schedule
  - GET    /availability/exceptions                List date exceptions
  - POST   /availability/exceptions                Add date exception
  - DELETE /availability/exceptions/{id}           Remove date exception
  - GET    /availability/templates                 List org templates
  - POST   /availability/templates                 Create template
  - POST   /availability/templates/{id}/apply      Apply template to user
  - GET    /availability/effective                 Get effective schedule for a date
  - GET    /availability/slots                     Get computed available slots
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id
from db import get_db
from services.recurring_availability_service import RecurringAvailabilityService

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================================================================
# PYDANTIC SCHEMAS
# ==================================================================

class TimeBlock(BaseModel):
    start: str = Field(..., description="Start time HH:MM")
    end: str = Field(..., description="End time HH:MM")
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None


class WeeklyScheduleUpdate(BaseModel):
    schedule: Dict[str, List[TimeBlock]] = Field(
        ..., description="Map of day_of_week (0-6) to list of time blocks"
    )
    timezone: str = "America/Chicago"


class ExceptionCreate(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    start_time: Optional[str] = Field(None, description="Start time HH:MM (null = full day)")
    end_time: Optional[str] = Field(None, description="End time HH:MM (null = full day)")
    is_blocked: bool = Field(True, description="True=unavailable, False=extra availability")
    reason: Optional[str] = Field(None, max_length=500)


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    schedule: Dict[str, List[TimeBlock]]
    is_default: bool = False
    timezone: str = "America/Chicago"


# ==================================================================
# WEEKLY SCHEDULE ENDPOINTS
# ==================================================================

@router.get("/availability/schedule")
async def get_weekly_schedule(
    request: Request,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get the weekly recurring availability schedule for a user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    # Validate target user belongs to same org
    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    service = RecurringAvailabilityService(db)
    schedule = service.get_weekly_schedule(target_user_id, org_id)

    return {
        "user_id": target_user_id,
        "schedule": schedule,
        "total_blocks": len(schedule),
    }


@router.put("/availability/schedule")
async def update_weekly_schedule(
    body: WeeklyScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Bulk-replace the weekly recurring schedule for the authenticated user.

    Accepts a schedule dict mapping day_of_week (0-6) to list of time blocks.
    Previous schedule rows are deactivated (soft delete).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Convert Pydantic models to plain dicts
    schedule_dict = {}
    for dow, blocks in body.schedule.items():
        schedule_dict[int(dow)] = [b.model_dump(exclude_none=True) for b in blocks]

    service = RecurringAvailabilityService(db)
    try:
        new_schedule = service.set_weekly_schedule(
            user_id=user.id,
            org_id=org_id,
            schedule=schedule_dict,
            tz=body.timezone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    return {
        "message": "Weekly schedule updated",
        "schedule": new_schedule,
        "total_blocks": len(new_schedule),
    }


# ==================================================================
# EXCEPTION ENDPOINTS
# ==================================================================

@router.get("/availability/exceptions")
async def list_exceptions(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """List availability exceptions, optionally filtered by date range."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    exceptions = service.get_exceptions(
        user_id=user.id,
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "exceptions": exceptions,
        "total": len(exceptions),
    }


@router.post("/availability/exceptions")
async def add_exception(
    body: ExceptionCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Add a date-specific availability exception (block or extra availability)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Parse date
    try:
        exc_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Parse times if provided
    start_time = None
    end_time = None
    if body.start_time:
        try:
            start_time = datetime.strptime(body.start_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format. Use HH:MM.")
    if body.end_time:
        try:
            end_time = datetime.strptime(body.end_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format. Use HH:MM.")

    service = RecurringAvailabilityService(db)
    try:
        exception = service.add_exception(
            user_id=user.id,
            org_id=org_id,
            exc_date=exc_date,
            start_time=start_time,
            end_time=end_time,
            is_blocked=body.is_blocked,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    return {
        "message": "Exception added",
        "exception": exception,
    }


@router.delete("/availability/exceptions/{exception_id}")
async def remove_exception(
    exception_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Remove a date-specific availability exception."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    deleted = service.remove_exception(exception_id, user.id, org_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Exception not found")

    db.commit()

    return {"message": "Exception removed", "id": exception_id}


# ==================================================================
# TEMPLATE ENDPOINTS
# ==================================================================

@router.get("/availability/templates")
async def list_templates(
    request: Request,
    db: Session = Depends(get_db),
):
    """List all availability templates for the user's organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    templates = service.get_templates(org_id)

    return {
        "templates": templates,
        "total": len(templates),
    }


@router.post("/availability/templates")
async def create_template(
    body: TemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a reusable availability template for the organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Convert Pydantic blocks to plain dicts for JSON storage
    schedule_dict = {}
    for dow, blocks in body.schedule.items():
        schedule_dict[dow] = [b.model_dump(exclude_none=True) for b in blocks]

    service = RecurringAvailabilityService(db)
    template = service.create_template(
        org_id=org_id,
        name=body.name,
        description=body.description,
        schedule=schedule_dict,
        is_default=body.is_default,
        tz=body.timezone,
    )

    db.commit()

    return {
        "message": "Template created",
        "template": template,
    }


@router.post("/availability/templates/{template_id}/apply")
async def apply_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Apply an org template to the authenticated user's schedule."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = RecurringAvailabilityService(db)
    try:
        new_schedule = service.apply_template(
            user_id=user.id,
            org_id=org_id,
            template_id=template_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    db.commit()

    return {
        "message": "Template applied",
        "schedule": new_schedule,
        "total_blocks": len(new_schedule),
    }


# ==================================================================
# EFFECTIVE SCHEDULE & SLOT COMPUTATION
# ==================================================================

@router.get("/availability/effective")
async def get_effective_schedule(
    request: Request,
    target_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get the effective availability schedule for a specific date.
    Merges recurring schedule with date exceptions.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    service = RecurringAvailabilityService(db)
    schedule = service.get_effective_schedule(target_user_id, org_id, target_date)

    return {
        "user_id": target_user_id,
        "date": target_date.isoformat(),
        "day_of_week": target_date.weekday(),
        "available_blocks": schedule,
        "total_blocks": len(schedule),
    }


@router.get("/availability/slots")
async def get_computed_slots(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    duration_minutes: int = Query(30, ge=15, le=480),
    user_id: Optional[int] = None,
    buffer_before: int = Query(0, ge=0, le=60),
    buffer_after: int = Query(0, ge=0, le=60),
    max_per_day: Optional[int] = Query(None, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Compute available time slots for booking.
    Merges recurring schedule + exceptions - existing appointments.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    if user_id and user_id != user.id:
        _validate_same_org(db, user_id, org_id)

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    service = RecurringAvailabilityService(db)
    slots = service.get_available_slots(
        user_id=target_user_id,
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        buffer_before=buffer_before,
        buffer_after=buffer_after,
        max_per_day=max_per_day,
    )

    return {
        "user_id": target_user_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_minutes": duration_minutes,
        "available_slots": slots,
        "total_slots": len(slots),
    }


# ==================================================================
# HELPERS
# ==================================================================

def _validate_same_org(db: Session, target_user_id: int, org_id: int):
    """Validate that the target user belongs to the same organization."""
    try:
        from database.models.core import User
        target_user = db.query(User).filter(
            User.id == target_user_id,
            User.organization_id == org_id,
        ).first()
        if not target_user:
            raise HTTPException(
                status_code=403, detail="User not found in your organization"
            )
    except ImportError:
        pass
