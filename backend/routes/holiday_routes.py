"""
Holiday & PTO Management Routes - Perennia AI Scheduler

Endpoints:
  Holidays:
    GET    /holidays                   List holidays for the org (with year filter)
    POST   /holidays                   Create a custom holiday
    PUT    /holidays/{id}              Update a holiday
    DELETE /holidays/{id}              Delete a holiday
    POST   /holidays/seed-federal      Seed US federal holidays for a year

  PTO Requests:
    GET    /pto                        List PTO requests (own or team, with filters)
    POST   /pto                        Submit a PTO request
    GET    /pto/{id}                   Get PTO request details
    PUT    /pto/{id}                   Update a PTO request
    POST   /pto/{id}/approve           Approve a PTO request (admin)
    POST   /pto/{id}/deny              Deny a PTO request (admin)
    POST   /pto/{id}/cancel            Cancel own PTO request

  Availability:
    GET    /availability/check         Check if a date is a working day
    GET    /availability/blocked-dates Get blocked dates in a range
    GET    /availability/team-grid     Team availability calendar grid

URL prefix: /api/v1/scheduler/  (applied by parent aggregator)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Holidays & PTO"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class HolidayCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    holiday_date: date
    holiday_type: str = Field("company", max_length=30)  # federal, state, company, custom
    is_half_day: bool = False
    half_day_end_time: Optional[str] = Field(None, max_length=5)  # "13:00"
    observed_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=1000)

    @validator("holiday_type")
    def validate_holiday_type(cls, v):
        allowed = {"federal", "state", "company", "custom"}
        if v not in allowed:
            raise ValueError(f"holiday_type must be one of: {', '.join(sorted(allowed))}")
        return v


class HolidayUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    holiday_date: Optional[date] = None
    holiday_type: Optional[str] = Field(None, max_length=30)
    is_half_day: Optional[bool] = None
    half_day_end_time: Optional[str] = Field(None, max_length=5)
    observed_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class PTORequestCreate(BaseModel):
    start_date: date
    end_date: date
    pto_type: str = Field("vacation", max_length=30)
    reason: Optional[str] = Field(None, max_length=2000)
    is_half_day_start: bool = False
    is_half_day_end: bool = False

    @validator("end_date")
    def end_after_start(cls, v, values):
        if "start_date" in values and v < values["start_date"]:
            raise ValueError("end_date must be on or after start_date")
        return v

    @validator("pto_type")
    def validate_pto_type(cls, v):
        allowed = {"vacation", "sick", "personal", "bereavement", "jury_duty", "parental", "other"}
        if v not in allowed:
            raise ValueError(f"pto_type must be one of: {', '.join(sorted(allowed))}")
        return v


class PTORequestUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pto_type: Optional[str] = Field(None, max_length=30)
    reason: Optional[str] = Field(None, max_length=2000)
    is_half_day_start: Optional[bool] = None
    is_half_day_end: Optional[bool] = None


class PTOReviewRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class SeedFederalHolidaysRequest(BaseModel):
    year: int = Field(..., ge=2020, le=2050)


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None  # scheduler models dict (BlockedTime, etc.)
_holiday_models = None  # Holiday, PTORequest


def set_dependencies(get_db_func, get_current_user_func, models_dict, holiday_models_dict):
    """
    Set dependencies from parent module.

    Args:
        get_db_func: DB session dependency
        get_current_user_func: Auth dependency
        models_dict: Scheduler models dict containing BlockedTime, etc.
        holiday_models_dict: Holiday-specific models (Holiday, PTORequest)
    """
    global _get_db, _get_current_user_func, _models, _holiday_models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _holiday_models = holiday_models_dict


from db import get_db, get_async_db


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Holiday route dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


async def get_current_user_async(request: Request):
    """Variant that uses its own short-lived sync session, freeing async
    handlers to use `get_async_db()` independently."""
    if _get_current_user_func is None:
        raise RuntimeError("Holiday route dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    from database import SessionLocal
    local_db = SessionLocal()
    try:
        return await _get_current_user_func(token=token, request=request, db=local_db)
    finally:
        local_db.close()


def _get_org_id(user) -> int:
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_admin(user) -> bool:
    role = getattr(user, "permission_role", "") or getattr(user, "role", "") or ""
    return role.lower() in ("admin", "site_admin", "platform_admin")


def _get_holiday_model():
    if not _holiday_models or "Holiday" not in _holiday_models:
        raise HTTPException(status_code=503, detail="Holiday service not initialized")
    return _holiday_models["Holiday"]


def _get_pto_model():
    if not _holiday_models or "PTORequest" not in _holiday_models:
        raise HTTPException(status_code=503, detail="PTO service not initialized")
    return _holiday_models["PTORequest"]


def _serialize_holiday(h) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "holiday_date": h.holiday_date.isoformat() if h.holiday_date else None,
        "holiday_type": h.holiday_type,
        "is_half_day": h.is_half_day,
        "half_day_end_time": h.half_day_end_time,
        "observed_date": h.observed_date.isoformat() if h.observed_date else None,
        "notes": h.notes,
        "is_active": h.is_active,
    }


def _serialize_pto(p) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "pto_type": p.pto_type,
        "reason": p.reason,
        "is_half_day_start": p.is_half_day_start,
        "is_half_day_end": p.is_half_day_end,
        "status": p.status,
        "reviewed_by_id": p.reviewed_by_id,
        "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "review_notes": p.review_notes,
        "blocked_time_id": p.blocked_time_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ============================================================================
# HOLIDAY ENDPOINTS
# ============================================================================

@router.get("/holidays")
async def list_holidays(
    request: Request,
    year: Optional[int] = Query(None, ge=2020, le=2050),
    holiday_type: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_async_db),
):
    """List holidays for the organization, optionally filtered by year and type."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)
    Holiday = _get_holiday_model()

    stmt = select(Holiday).where(Holiday.organization_id == org_id)

    if not include_inactive:
        stmt = stmt.where(Holiday.is_active == True)

    if year:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        stmt = stmt.where(
            Holiday.holiday_date >= start,
            Holiday.holiday_date <= end,
        )

    if holiday_type:
        stmt = stmt.where(Holiday.holiday_type == holiday_type)

    stmt = stmt.order_by(Holiday.holiday_date)
    result = await db.execute(stmt)
    holidays = result.scalars().all()

    return {
        "holidays": [_serialize_holiday(h) for h in holidays],
        "count": len(holidays),
    }


@router.post("/holidays")
async def create_holiday(
    data: HolidayCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Create a custom holiday (admin only)."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can create holidays")

    Holiday = _get_holiday_model()

    # Check for duplicate
    existing_result = await db.execute(
        select(Holiday).where(
            Holiday.organization_id == org_id,
            Holiday.holiday_date == data.holiday_date,
            Holiday.name == data.name,
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Holiday '{data.name}' already exists on {data.holiday_date}",
        )

    holiday = Holiday(
        organization_id=org_id,
        name=data.name,
        holiday_date=data.holiday_date,
        holiday_type=data.holiday_type,
        is_half_day=data.is_half_day,
        half_day_end_time=data.half_day_end_time,
        observed_date=data.observed_date,
        notes=data.notes,
        created_by_id=user.id,
    )
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)

    return {
        "message": "Holiday created",
        "holiday": _serialize_holiday(holiday),
    }


@router.put("/holidays/{holiday_id}")
async def update_holiday(
    holiday_id: int,
    data: HolidayUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Update a holiday (admin only)."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can update holidays")

    Holiday = _get_holiday_model()

    result = await db.execute(
        select(Holiday).where(Holiday.id == holiday_id, Holiday.organization_id == org_id)
    )
    holiday = result.scalars().first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(holiday, field, value)

    await db.commit()
    await db.refresh(holiday)

    return {
        "message": "Holiday updated",
        "holiday": _serialize_holiday(holiday),
    }


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a holiday (admin only)."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can delete holidays")

    Holiday = _get_holiday_model()

    result = await db.execute(
        select(Holiday).where(Holiday.id == holiday_id, Holiday.organization_id == org_id)
    )
    holiday = result.scalars().first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    await db.delete(holiday)
    await db.commit()

    return {"message": "Holiday deleted"}


@router.post("/holidays/seed-federal")
async def seed_federal_holidays(
    data: SeedFederalHolidaysRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Seed US federal holidays for a given year (admin only). Idempotent."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can seed holidays")

    Holiday = _get_holiday_model()

    from services.holiday_service import seed_federal_holidays as _seed

    result = _seed(db, org_id, data.year, Holiday, created_by_id=user.id)
    db.commit()

    return {
        "message": f"Federal holidays seeded for {data.year}",
        **result,
    }


# ============================================================================
# PTO ENDPOINTS
# ============================================================================

@router.get("/pto")
async def list_pto_requests(
    request: Request,
    user_id: Optional[int] = Query(None, description="Filter by user (admin only)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List PTO requests.
    Non-admins see only their own. Admins can filter by user_id.
    """
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)
    PTORequest = _get_pto_model()

    stmt = select(PTORequest).where(
        PTORequest.organization_id == org_id,
        PTORequest.is_active == True,
    )

    if _is_admin(user) and user_id:
        stmt = stmt.where(PTORequest.user_id == user_id)
    elif not _is_admin(user):
        stmt = stmt.where(PTORequest.user_id == user.id)
    # else: admin with no user_id filter sees all

    if status:
        stmt = stmt.where(PTORequest.status == status)

    if start_date:
        stmt = stmt.where(PTORequest.end_date >= start_date)
    if end_date:
        stmt = stmt.where(PTORequest.start_date <= end_date)

    stmt = stmt.order_by(PTORequest.start_date.desc())
    result = await db.execute(stmt)
    pto_list = result.scalars().all()

    return {
        "pto_requests": [_serialize_pto(p) for p in pto_list],
        "count": len(pto_list),
    }


@router.post("/pto")
async def create_pto_request(
    data: PTORequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Submit a PTO request."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)
    PTORequest = _get_pto_model()

    # Check for overlapping approved/pending PTO
    overlap_result = await db.execute(
        select(PTORequest).where(
            PTORequest.organization_id == org_id,
            PTORequest.user_id == user.id,
            PTORequest.is_active == True,
            PTORequest.status.in_(["pending", "approved"]),
            PTORequest.start_date <= data.end_date,
            PTORequest.end_date >= data.start_date,
        )
    )
    overlap = overlap_result.scalars().first()
    if overlap:
        raise HTTPException(
            status_code=409,
            detail=f"Overlapping PTO request exists (id={overlap.id}, "
                   f"{overlap.start_date} - {overlap.end_date}, status={overlap.status})",
        )

    pto = PTORequest(
        organization_id=org_id,
        user_id=user.id,
        start_date=data.start_date,
        end_date=data.end_date,
        pto_type=data.pto_type,
        reason=data.reason,
        is_half_day_start=data.is_half_day_start,
        is_half_day_end=data.is_half_day_end,
        status="pending",
    )
    db.add(pto)
    await db.commit()
    await db.refresh(pto)

    return {
        "message": "PTO request submitted",
        "pto_request": _serialize_pto(pto),
    }


@router.get("/pto/{pto_id}")
async def get_pto_request(
    pto_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get a single PTO request."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)
    PTORequest = _get_pto_model()

    result = await db.execute(
        select(PTORequest).where(PTORequest.id == pto_id, PTORequest.organization_id == org_id)
    )
    pto = result.scalars().first()
    if not pto:
        raise HTTPException(status_code=404, detail="PTO request not found")

    # Non-admins can only view their own
    if not _is_admin(user) and pto.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this PTO request")

    return {"pto_request": _serialize_pto(pto)}


@router.put("/pto/{pto_id}")
async def update_pto_request(
    pto_id: int,
    data: PTORequestUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Update a pending PTO request (own only, must still be pending)."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)
    PTORequest = _get_pto_model()

    result = await db.execute(
        select(PTORequest).where(
            PTORequest.id == pto_id,
            PTORequest.organization_id == org_id,
            PTORequest.user_id == user.id,
        )
    )
    pto = result.scalars().first()
    if not pto:
        raise HTTPException(status_code=404, detail="PTO request not found")

    if pto.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update PTO request in '{pto.status}' status. Only pending requests can be updated.",
        )

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pto, field, value)

    await db.commit()
    await db.refresh(pto)

    return {
        "message": "PTO request updated",
        "pto_request": _serialize_pto(pto),
    }


@router.post("/pto/{pto_id}/approve")
async def approve_pto_request(
    pto_id: int,
    data: PTOReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Approve a PTO request (admin only). Creates a BlockedTime entry."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can approve PTO requests")

    PTORequest = _get_pto_model()

    pto = (
        db.query(PTORequest)
        .filter(
            PTORequest.id == pto_id,
            PTORequest.organization_id == org_id,
        )
        .first()
    )
    if not pto:
        raise HTTPException(status_code=404, detail="PTO request not found")

    if pto.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"PTO request is already '{pto.status}'",
        )

    # Approve the request
    pto.status = "approved"
    pto.reviewed_by_id = user.id
    pto.reviewed_at = datetime.now(timezone.utc)
    pto.review_notes = data.notes

    # Create a BlockedTime entry so the scheduling engine respects this PTO
    BlockedTime = _models.get("BlockedTime") if _models else None
    if BlockedTime:
        from services.holiday_service import create_blocked_time_for_pto
        blocked_id = create_blocked_time_for_pto(db, pto, BlockedTime)
        pto.blocked_time_id = blocked_id

    db.commit()
    db.refresh(pto)

    return {
        "message": "PTO request approved",
        "pto_request": _serialize_pto(pto),
    }


@router.post("/pto/{pto_id}/deny")
async def deny_pto_request(
    pto_id: int,
    data: PTOReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Deny a PTO request (admin only)."""
    user = await get_current_user_async(request)
    org_id = _get_org_id(user)

    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only admins can deny PTO requests")

    PTORequest = _get_pto_model()

    result = await db.execute(
        select(PTORequest).where(
            PTORequest.id == pto_id,
            PTORequest.organization_id == org_id,
        )
    )
    pto = result.scalars().first()
    if not pto:
        raise HTTPException(status_code=404, detail="PTO request not found")

    if pto.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"PTO request is already '{pto.status}'",
        )

    pto.status = "denied"
    pto.reviewed_by_id = user.id
    pto.reviewed_at = datetime.now(timezone.utc)
    pto.review_notes = data.notes

    await db.commit()
    await db.refresh(pto)

    return {
        "message": "PTO request denied",
        "pto_request": _serialize_pto(pto),
    }


@router.post("/pto/{pto_id}/cancel")
async def cancel_pto_request(
    pto_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cancel own PTO request. If approved, also removes the BlockedTime entry."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    PTORequest = _get_pto_model()

    pto = (
        db.query(PTORequest)
        .filter(
            PTORequest.id == pto_id,
            PTORequest.organization_id == org_id,
            PTORequest.user_id == user.id,
        )
        .first()
    )
    if not pto:
        raise HTTPException(status_code=404, detail="PTO request not found")

    if pto.status in ("denied", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"PTO request is already '{pto.status}'",
        )

    # If was approved, remove the associated BlockedTime
    if pto.blocked_time_id and _models:
        BlockedTime = _models.get("BlockedTime")
        if BlockedTime:
            blocked = db.query(BlockedTime).filter(BlockedTime.id == pto.blocked_time_id).first()
            if blocked:
                db.delete(blocked)

    pto.status = "cancelled"
    pto.blocked_time_id = None
    db.commit()
    db.refresh(pto)

    return {
        "message": "PTO request cancelled",
        "pto_request": _serialize_pto(pto),
    }


# ============================================================================
# AVAILABILITY CHECK ENDPOINTS
# ============================================================================

@router.get("/availability/check")
async def check_working_day(
    request: Request,
    check_date: date = Query(..., description="Date to check"),
    user_id: Optional[int] = Query(None, description="User ID (defaults to self)"),
    db: Session = Depends(get_db),
):
    """Check if a specific date is a working day for a user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    Holiday = _get_holiday_model()
    PTORequest = _get_pto_model()
    BlockedTime = _models.get("BlockedTime") if _models else None

    from services.holiday_service import is_working_day as _check

    result = _check(
        db, org_id, target_user_id, check_date,
        Holiday, PTORequest, BlockedTime,
    )

    return {
        "date": check_date.isoformat(),
        "user_id": target_user_id,
        **result,
    }


@router.get("/availability/blocked-dates")
async def get_blocked_dates_endpoint(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: Optional[int] = Query(None, description="User ID (defaults to self)"),
    db: Session = Depends(get_db),
):
    """Get all blocked dates in a range for a user (holidays, PTO, weekends)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_user_id = user_id or user.id

    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    Holiday = _get_holiday_model()
    PTORequest = _get_pto_model()
    BlockedTime = _models.get("BlockedTime") if _models else None

    from services.holiday_service import get_blocked_dates as _get_blocked

    blocked = _get_blocked(
        db, org_id, target_user_id, start_date, end_date,
        Holiday, PTORequest, BlockedTime,
    )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "user_id": target_user_id,
        "blocked_dates": blocked,
        "count": len(blocked),
    }


@router.get("/availability/team-grid")
async def get_team_availability_grid(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_ids: Optional[str] = Query(
        None, description="Comma-separated user IDs. Omit for all org users."
    ),
    db: Session = Depends(get_db),
):
    """
    Team availability calendar grid.
    Shows who's in/out for each date in the range.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    Holiday = _get_holiday_model()
    PTORequest = _get_pto_model()
    BlockedTime = _models.get("BlockedTime") if _models else None

    # Resolve user IDs
    if user_ids:
        try:
            target_ids = [int(uid.strip()) for uid in user_ids.split(",") if uid.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="user_ids must be comma-separated integers")
    else:
        # Get all active users in the org
        try:
            from database.models import User
            org_users = (
                db.query(User)
                .filter(User.organization_id == org_id, User.is_active == True)
                .all()
            )
            target_ids = [u.id for u in org_users]
        except Exception as e:
            logger.warning(f"Could not load org users: {e}")
            target_ids = [user.id]

    # Get User model for name resolution
    try:
        from database.models import User
        UserModel = User
    except ImportError:
        UserModel = None

    from services.holiday_service import get_team_availability

    grid = get_team_availability(
        db, org_id, target_ids, start_date, end_date,
        Holiday, PTORequest, BlockedTime, UserModel,
    )

    return grid
