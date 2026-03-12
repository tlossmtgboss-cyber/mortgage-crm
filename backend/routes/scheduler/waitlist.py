"""
Scheduler Waitlist Routes - Queue management for appointment scheduling.

Endpoints:
  Authenticated (admin):
    - POST   /waitlist                    Join waitlist (authenticated user)
    - GET    /waitlist                    Get waitlist for org
    - GET    /waitlist/{id}/position      Check position
    - DELETE /waitlist/{id}               Leave waitlist
    - POST   /waitlist/{id}/offer         Manually offer slot to entry
    - POST   /waitlist/{id}/reorder       Reorder entry position
    - POST   /waitlist/expire-offers      Manually expire stale offers

  Public (no auth):
    - POST   /public/waitlist/join        Public waitlist join
    - POST   /public/waitlist/{id}/accept Accept offered slot
    - GET    /public/waitlist/{id}/position Check position (public)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
import html
import logging

try:
    import nh3
except ImportError:
    nh3 = None

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
    _audit_log,
)
from db import get_db
from services.waitlist_service import WaitlistService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class WaitlistJoinRequest(BaseModel):
    appointment_type_id: int
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    preferred_dates: Optional[List[str]] = None
    preferred_times: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)


class PublicWaitlistJoinRequest(BaseModel):
    appointment_type_id: int
    organization_id: int
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    preferred_dates: Optional[List[str]] = None
    preferred_times: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)


class OfferSlotRequest(BaseModel):
    slot_time: str  # ISO format datetime


class ReorderRequest(BaseModel):
    new_position: int = Field(..., ge=1)


# ============================================================================
# INPUT SANITIZATION
# ============================================================================

def _sanitize(value: Optional[str]) -> Optional[str]:
    """Strip HTML from user input."""
    if value is None:
        return None
    if nh3:
        return nh3.clean(value, tags=set())
    return html.escape(value)


# ============================================================================
# HELPER
# ============================================================================

def _get_waitlist_service(db: Session) -> WaitlistService:
    """Create a WaitlistService with current models."""
    models = get_models()
    return WaitlistService(db, models)


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

@router.post("/waitlist")
async def join_waitlist_authenticated(
    body: WaitlistJoinRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Join waitlist as an authenticated user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = _get_waitlist_service(db)

    try:
        entry = service.join_waitlist({
            "organization_id": org_id,
            "appointment_type_id": body.appointment_type_id,
            "user_id": user.id,
            "name": _sanitize(body.name),
            "email": _sanitize(body.email),
            "phone": _sanitize(body.phone),
            "preferred_dates": body.preferred_dates or [],
            "preferred_times": body.preferred_times or [],
            "notes": _sanitize(body.notes),
        })

        db.commit()

        return {
            "success": True,
            "entry": service._entry_to_dict(entry),
            "message": f"Added to waitlist at position {entry.position}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/waitlist")
async def get_waitlist(
    request: Request,
    appointment_type_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get waitlist for the organization (admin view)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = _get_waitlist_service(db)

    try:
        result = service.get_waitlist(
            org_id=org_id,
            appointment_type_id=appointment_type_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/waitlist/{entry_id}/position")
async def get_waitlist_position(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Check waitlist position for an entry."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = _get_waitlist_service(db)

    try:
        return service.get_position(entry_id, org_id=org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/waitlist/{entry_id}")
async def leave_waitlist(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Leave the waitlist."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = _get_waitlist_service(db)

    try:
        service.leave_waitlist(entry_id, org_id=org_id)
        db.commit()
        return {"success": True, "message": "Removed from waitlist"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/waitlist/{entry_id}/offer")
async def offer_slot_to_entry(
    entry_id: int,
    body: OfferSlotRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Manually offer a slot to a waitlist entry (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = _get_waitlist_service(db)

    try:
        slot_time = datetime.fromisoformat(body.slot_time.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid slot_time format. Use ISO 8601.")

    try:
        entry = service.offer_slot(entry_id, slot_time, org_id=org_id)
        _audit_log(db, org_id, user.id, "waitlist_offer", "waitlist_entry",
                   entity_id=entry_id, changes={"slot_time": body.slot_time}, request=request)
        db.commit()

        return {
            "success": True,
            "entry": service._entry_to_dict(entry),
            "message": f"Slot offered to {entry.name}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/waitlist/{entry_id}/reorder")
async def reorder_waitlist_entry(
    entry_id: int,
    body: ReorderRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reorder a waitlist entry (admin only, for drag-to-reorder)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = _get_waitlist_service(db)

    try:
        entry = service.reorder_entry(entry_id, body.new_position, org_id)
        db.commit()

        return {
            "success": True,
            "entry": service._entry_to_dict(entry),
            "message": f"Moved to position {entry.position}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/waitlist/expire-offers")
async def expire_stale_offers(
    request: Request,
    db: Session = Depends(get_db),
):
    """Manually trigger expiration of stale offers (admin only)."""
    user = await get_current_user(request, db)
    _get_org_id(user)  # Ensure user is in an org

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    service = _get_waitlist_service(db)
    count = service.expire_offers()
    db.commit()

    return {
        "success": True,
        "expired_count": count,
        "message": f"Expired {count} offers",
    }


# ============================================================================
# PUBLIC ENDPOINTS (no auth required)
# ============================================================================

@router.post("/public/waitlist/join")
async def public_join_waitlist(
    body: PublicWaitlistJoinRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public endpoint for joining a waitlist (no authentication required)."""
    service = _get_waitlist_service(db)

    try:
        entry = service.join_waitlist({
            "organization_id": body.organization_id,
            "appointment_type_id": body.appointment_type_id,
            "name": _sanitize(body.name),
            "email": _sanitize(body.email),
            "phone": _sanitize(body.phone),
            "preferred_dates": body.preferred_dates or [],
            "preferred_times": body.preferred_times or [],
            "notes": _sanitize(body.notes),
        })

        db.commit()

        return {
            "success": True,
            "entry_id": entry.id,
            "position": entry.position,
            "message": f"You are #{entry.position} on the waitlist",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/public/waitlist/{entry_id}/accept")
async def public_accept_offer(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public endpoint for accepting a waitlist offer (no auth, identified by entry ID)."""
    service = _get_waitlist_service(db)

    try:
        result = service.accept_offer(entry_id)
        db.commit()

        return {
            "success": True,
            "message": "Appointment booked successfully!",
            "appointment": result["appointment"],
            "waitlist_entry": result["waitlist_entry"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/public/waitlist/{entry_id}/position")
async def public_check_position(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public endpoint for checking waitlist position."""
    service = _get_waitlist_service(db)

    try:
        result = service.get_position(entry_id)
        # Return limited info for public access
        return {
            "position": result["position"],
            "total_waiting": result["total_waiting"],
            "status": result["status"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
