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

  Public (no auth, token-protected):
    - POST   /public/waitlist/join        Public waitlist join
    - POST   /public/waitlist/accept      Accept offered slot (token required)
    - GET    /public/waitlist/position     Check position (token required)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
import html
import logging
import os

try:
    import jwt
except ImportError:
    jwt = None

try:
    import nh3
except ImportError:
    nh3 = None

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
    _audit_log, _check_rate_limit,
)
from routes.scheduler.error_responses import (
    validation_error, not_found_error, forbidden_error,
    unauthorized_error, internal_error, service_unavailable_error,
)
from db import get_db
from middleware.feature_gate import require_feature_tier
from services.waitlist_service import WaitlistService

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    import warnings
    warnings.warn("SECRET_KEY not set in waitlist module")

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
    organization_id: Optional[int] = None  # Deprecated: derived from appointment_type_id
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    preferred_dates: Optional[List[str]] = None
    preferred_times: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)


class PublicAcceptRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


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
# WAITLIST TOKEN HELPERS
# ============================================================================

def _generate_waitlist_token(entry_id: int, email: str) -> str:
    """Generate a JWT token scoped to a specific waitlist entry.

    The token encodes the entry_id and email so that public endpoints can
    authenticate callers without exposing sequential entry IDs.
    Tokens expire after 7 days (waitlist offers are typically shorter-lived).
    """
    if not jwt:
        raise RuntimeError("PyJWT is required for waitlist token generation")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY required for waitlist token generation")
    payload = {
        "wl_entry_id": entry_id,
        "email": email,
        "purpose": "waitlist",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _verify_waitlist_token(token: str) -> dict:
    """Verify a waitlist token and return the decoded payload.

    Returns dict with 'wl_entry_id' and 'email' on success.
    Raises HTTPException on failure.
    """
    if not jwt:
        internal_error("Server configuration error")
    if not SECRET_KEY:
        internal_error("Server configuration error")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        unauthorized_error("Waitlist link has expired")
    except jwt.InvalidTokenError:
        unauthorized_error("Invalid waitlist link")

    if payload.get("purpose") != "waitlist":
        unauthorized_error("Invalid waitlist link")

    entry_id = payload.get("wl_entry_id")
    email = payload.get("email")
    if not entry_id or not email:
        unauthorized_error("Invalid waitlist link")

    return {"entry_id": entry_id, "email": email}


def _resolve_org_from_appointment_type(appointment_type_id: int, db: Session) -> int:
    """Look up the organization_id from an appointment_type_id.

    This prevents clients from supplying an arbitrary organization_id.
    Raises HTTPException if the appointment type does not exist or is inactive.
    """
    models = get_models()
    AppointmentType = models.get("AppointmentType")
    if not AppointmentType:
        service_unavailable_error("Server configuration error")

    appt_type = db.query(AppointmentType).filter(
        AppointmentType.id == appointment_type_id
    ).first()

    if not appt_type:
        not_found_error("Appointment type not found")

    # Verify the appointment type is active if it has an is_active flag
    if hasattr(appt_type, "is_active") and not appt_type.is_active:
        not_found_error("Appointment type not found")

    return appt_type.organization_id


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
@require_feature_tier("scheduler_waitlist")
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
        validation_error(str(e))


@router.get("/waitlist")
@require_feature_tier("scheduler_waitlist")
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
        forbidden_error("Admin access required")

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
        validation_error(str(e))


@router.get("/waitlist/{entry_id}/position")
@require_feature_tier("scheduler_waitlist")
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
        not_found_error(str(e))


@router.delete("/waitlist/{entry_id}")
@require_feature_tier("scheduler_waitlist")
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
        validation_error(str(e))


@router.post("/waitlist/{entry_id}/offer")
@require_feature_tier("scheduler_waitlist")
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
        forbidden_error("Admin access required")

    service = _get_waitlist_service(db)

    try:
        slot_time = datetime.fromisoformat(body.slot_time.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        validation_error("Invalid slot_time format. Use ISO 8601.")

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
        validation_error(str(e))


@router.post("/waitlist/{entry_id}/reorder")
@require_feature_tier("scheduler_waitlist")
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
        forbidden_error("Admin access required")

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
        validation_error(str(e))


@router.post("/waitlist/expire-offers")
@require_feature_tier("scheduler_waitlist")
async def expire_stale_offers(
    request: Request,
    db: Session = Depends(get_db),
):
    """Manually trigger expiration of stale offers (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        forbidden_error("Admin access required")

    service = _get_waitlist_service(db)
    count = service.expire_offers(org_id=org_id)
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
    """Public endpoint for joining a waitlist (no authentication required).

    The organization_id is derived from the appointment_type_id to prevent
    callers from associating entries with arbitrary orgs. A legacy
    organization_id field in the request body is accepted but ignored.

    Returns a signed token that the caller must use for subsequent
    accept/position requests (prevents IDOR on sequential entry IDs).
    """
    await _check_rate_limit(request, max_requests=10)

    # Derive org_id from appointment_type_id (never trust client-supplied org_id)
    org_id = _resolve_org_from_appointment_type(body.appointment_type_id, db)

    service = _get_waitlist_service(db)

    try:
        sanitized_email = _sanitize(body.email) or ""
        entry = service.join_waitlist({
            "organization_id": org_id,
            "appointment_type_id": body.appointment_type_id,
            "name": _sanitize(body.name),
            "email": sanitized_email,
            "phone": _sanitize(body.phone),
            "preferred_dates": body.preferred_dates or [],
            "preferred_times": body.preferred_times or [],
            "notes": _sanitize(body.notes),
        })

        db.commit()

        # Generate a signed token so the caller can accept/check position
        # without exposing the raw entry_id to IDOR attacks.
        token = _generate_waitlist_token(entry.id, sanitized_email)

        return {
            "success": True,
            "token": token,
            "position": entry.position,
            "message": f"You are #{entry.position} on the waitlist",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/public/waitlist/accept")
async def public_accept_offer(
    body: PublicAcceptRequest,
    request: Request,
    token: str = Query(..., description="Signed waitlist token from join response"),
    db: Session = Depends(get_db),
):
    """Accept a waitlist offer using a signed token.

    The token (from the join response or notification email) encodes the
    entry_id and email. The request body must include the matching email
    as a second verification factor.
    """
    await _check_rate_limit(request, max_requests=5)

    # Verify the signed token
    payload = _verify_waitlist_token(token)
    entry_id = payload["entry_id"]
    token_email = payload["email"]

    # Double-check: body email must match the token's email
    if (body.email or "").strip().lower() != (token_email or "").strip().lower():
        raise HTTPException(status_code=403, detail="Email does not match waitlist entry")

    # Resolve org_id from the waitlist entry for tenant isolation
    models = get_models()
    WaitlistEntry = models.get("WaitlistEntry")
    resolved_org_id = None
    if WaitlistEntry:
        entry_row = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).first()
        if entry_row:
            resolved_org_id = getattr(entry_row, "organization_id", None)

    service = _get_waitlist_service(db)

    try:
        result = service.accept_offer(entry_id, org_id=resolved_org_id)
        db.commit()

        return {
            "success": True,
            "message": "Appointment booked successfully!",
            "appointment": result["appointment"],
            "waitlist_entry": result["waitlist_entry"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/public/waitlist/position")
async def public_check_position(
    request: Request,
    token: str = Query(..., description="Signed waitlist token from join response"),
    db: Session = Depends(get_db),
):
    """Check waitlist position using a signed token.

    The token (from the join response) encodes the entry_id, preventing
    enumeration of other users' waitlist entries.
    """
    await _check_rate_limit(request, max_requests=30)

    # Verify the signed token
    payload = _verify_waitlist_token(token)
    entry_id = payload["entry_id"]

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
