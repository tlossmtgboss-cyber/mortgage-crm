"""
Slot Hold Routes - TTL-based soft holds for slot reservation.

Endpoints:
- POST   /holds           — Create a new hold (internal: AI/booking flow)
- PUT    /holds/{id}/extend — Extend hold TTL
- POST   /holds/{id}/convert — Convert hold to appointment
- DELETE /holds/{id}       — Release hold
- GET    /holds            — List active holds (admin/LO view)
- GET    /holds/stats      — Hold analytics
- POST   /holds/cleanup    — Manually trigger expired hold cleanup
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
import logging

from services.slot_hold_service import (
    create_hold,
    extend_hold,
    convert_hold_to_appointment,
    release_hold,
    cleanup_expired_holds,
    get_active_holds,
    get_hold_stats,
    SlotHoldError,
    DEFAULT_HOLD_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# DEPENDENCY INJECTION (same pattern as scheduler_appointment_routes)
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
        raise RuntimeError("Slot hold dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Slot hold dependencies not set")
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
# PYDANTIC SCHEMAS
# ============================================================================

class CreateHoldRequest(BaseModel):
    lo_id: int
    start_time: datetime
    end_time: datetime
    held_by: str = "manual"  # 'ai_conversation', 'public_booking', 'manual'
    ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS
    held_for_name: Optional[str] = None
    held_for_phone: Optional[str] = None
    held_for_email: Optional[str] = None
    conversation_id: Optional[str] = None


class ExtendHoldRequest(BaseModel):
    additional_seconds: int = 300  # Default: extend by 5 more minutes


class ConvertHoldRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    duration_minutes: Optional[int] = None
    timezone: str = "America/Chicago"
    appointment_type_id: Optional[int] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    intake_responses: Optional[dict] = None
    ai_booking_context: Optional[dict] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/holds")
async def create_slot_hold(
    hold_request: CreateHoldRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a soft hold on a time slot.

    Used by AI conversation handlers and public booking flows to temporarily
    reserve a slot while the caller confirms. Default TTL is 5 minutes.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = await create_hold(
            lo_id=hold_request.lo_id,
            start_time=hold_request.start_time,
            end_time=hold_request.end_time,
            held_by=hold_request.held_by,
            organization_id=org_id,
            db=db,
            models=_models,
            ttl_seconds=hold_request.ttl_seconds,
            held_for_name=hold_request.held_for_name,
            held_for_phone=hold_request.held_for_phone,
            held_for_email=hold_request.held_for_email,
            conversation_id=hold_request.conversation_id,
        )
        db.commit()
        return {"hold": result, "message": "Slot hold created"}
    except SlotHoldError as e:
        db.rollback()
        status_map = {
            "APPOINTMENT_CONFLICT": 409,
            "HOLD_CONFLICT": 409,
            "CONCURRENT_BOOKING": 409,
            "CONCURRENT_HOLD": 409,
            "MAX_HOLDS_EXCEEDED": 429,
            "INVALID_TIME_RANGE": 400,
            "PAST_SLOT": 400,
            "INVALID_SOURCE": 400,
            "MODELS_UNAVAILABLE": 503,
        }
        status_code = status_map.get(e.code, 400)
        raise HTTPException(status_code=status_code, detail=e.message)


@router.put("/holds/{hold_id}/extend")
async def extend_slot_hold(
    hold_id: int,
    extend_request: ExtendHoldRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Extend the TTL of an active hold.

    Total hold lifetime cannot exceed 15 minutes from creation.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = await extend_hold(
            hold_id=hold_id,
            additional_seconds=extend_request.additional_seconds,
            organization_id=org_id,
            db=db,
            models=_models,
        )
        db.commit()
        return {"hold": result, "message": "Hold extended"}
    except SlotHoldError as e:
        db.rollback()
        status_map = {
            "NOT_FOUND": 404,
            "EXPIRED": 410,
            "INVALID_STATUS": 409,
            "MAX_TTL_REACHED": 409,
        }
        status_code = status_map.get(e.code, 400)
        raise HTTPException(status_code=status_code, detail=e.message)


@router.post("/holds/{hold_id}/convert")
async def convert_hold(
    hold_id: int,
    convert_request: ConvertHoldRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Convert a hold into a real appointment.

    Atomic operation: creates the appointment and marks the hold as converted
    in the same transaction. If the hold has expired, returns 410.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = await convert_hold_to_appointment(
            hold_id=hold_id,
            appointment_data=convert_request.model_dump(exclude_none=True),
            organization_id=org_id,
            user_id=user.id,
            db=db,
            models=_models,
        )
        db.commit()
        return {"appointment": result, "message": "Hold converted to appointment"}
    except SlotHoldError as e:
        db.rollback()
        status_map = {
            "NOT_FOUND": 404,
            "EXPIRED": 410,
            "INVALID_STATUS": 409,
        }
        status_code = status_map.get(e.code, 400)
        raise HTTPException(status_code=status_code, detail=e.message)


@router.delete("/holds/{hold_id}")
async def release_slot_hold(
    hold_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Release a hold before it expires. Idempotent: if already released/expired,
    returns the current state without error.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = await release_hold(
            hold_id=hold_id,
            organization_id=org_id,
            db=db,
            models=_models,
        )
        db.commit()
        return result
    except SlotHoldError as e:
        db.rollback()
        if e.code == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.message)
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/holds")
async def list_active_holds(
    request: Request,
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    List active holds for a loan officer. If lo_id not specified,
    defaults to the current user.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    target_lo_id = lo_id or user.id

    holds = await get_active_holds(
        lo_id=target_lo_id,
        organization_id=org_id,
        db=db,
        models=_models,
    )

    return {
        "holds": holds,
        "count": len(holds),
        "lo_id": target_lo_id,
    }


@router.get("/holds/stats")
async def get_hold_statistics(
    request: Request,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """
    Get hold analytics: conversion rate, average hold duration, expiry rate.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    stats = await get_hold_stats(
        organization_id=org_id,
        db=db,
        models=_models,
        days=min(days, 365),
    )

    return {"stats": stats}


@router.post("/holds/cleanup")
async def trigger_cleanup(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Manually trigger cleanup of expired holds. Normally runs automatically
    every minute via background scheduler.
    """
    user = await get_current_user(request, db)
    # Only allow authenticated users to trigger cleanup
    _get_org_id(user)

    result = await cleanup_expired_holds(db=db, models=_models)
    db.commit()

    return {"message": "Cleanup complete", **result}
