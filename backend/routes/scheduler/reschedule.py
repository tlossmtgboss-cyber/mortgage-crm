"""
Scheduler Reschedule Routes — appointment rescheduling endpoints.

Endpoints:
  Authenticated (LO / admin):
    POST /reschedule/{appointment_id}           Initiate a reschedule request
    GET  /reschedule/history/{appointment_id}    Get reschedule history
    POST /reschedule/{appointment_id}/link       Generate borrower self-service link

  Public (borrower self-service, rate-limited):
    GET  /public/reschedule/{token}/slots        Available slots for rescheduling
    POST /public/reschedule/{token}/confirm      Confirm new time
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from typing import Optional
import logging

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _check_rate_limit,
    _sanitize_text, _audit_log,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC REQUEST MODELS (inline to avoid circular imports)
# ============================================================================

from pydantic import BaseModel, Field


class RescheduleInitiateRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=1000)


class RescheduleConfirmRequest(BaseModel):
    new_start: str = Field(..., description="ISO 8601 datetime for new start")
    new_end: str = Field(..., description="ISO 8601 datetime for new end")
    reason: Optional[str] = Field(None, max_length=1000)


# ============================================================================
# HELPER: build service
# ============================================================================

def _get_reschedule_service(db: Session):
    """Create a RescheduleService instance with the current models dict."""
    from services.reschedule_service import RescheduleService
    models = get_models()
    if not models:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    return RescheduleService(db, models)


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

@router.post("/reschedule/{appointment_id}")
async def initiate_reschedule(
    request: Request,
    appointment_id: int,
    body: RescheduleInitiateRequest,
    db: Session = Depends(get_db),
):
    """
    Start a reschedule flow for an appointment (LO / admin).

    Creates a reschedule history record and returns the current
    reschedule count along with the appointment details.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    svc = _get_reschedule_service(db)

    reason = _sanitize_text(body.reason) if body.reason else None

    try:
        result = svc.initiate_reschedule(
            appointment_id=appointment_id,
            requested_by_type="lo",
            reason=reason,
            org_id=org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _audit_log(
        db, org_id, user.id, "reschedule_initiated",
        "appointment", appointment_id,
        changes={"reason": reason},
        request=request,
    )

    db.commit()

    return {
        "status": "ok",
        **result,
    }


@router.get("/reschedule/history/{appointment_id}")
async def get_reschedule_history(
    request: Request,
    appointment_id: int,
    db: Session = Depends(get_db),
):
    """Get full reschedule history for an appointment (LO / admin)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    svc = _get_reschedule_service(db)

    try:
        history = svc.get_reschedule_history(appointment_id, org_id=org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "appointment_id": appointment_id,
        "history": history,
        "count": len(history),
    }


@router.post("/reschedule/{appointment_id}/link")
async def generate_reschedule_link(
    request: Request,
    appointment_id: int,
    db: Session = Depends(get_db),
):
    """
    Generate a borrower-facing reschedule link (JWT token, 72-hour expiry).

    The borrower can use this link to pick a new time without logging in.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    svc = _get_reschedule_service(db)

    try:
        link_data = svc.generate_reschedule_link(appointment_id, org_id=org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    _audit_log(
        db, org_id, user.id, "reschedule_link_generated",
        "appointment", appointment_id,
        request=request,
    )

    db.commit()

    return {
        "status": "ok",
        **link_data,
    }


# ============================================================================
# PUBLIC ENDPOINTS (borrower self-service, no auth, rate-limited)
# ============================================================================

@router.get("/public/reschedule/{token}/slots")
async def public_reschedule_slots(
    request: Request,
    token: str,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD start date"),
    db: Session = Depends(get_db),
):
    """
    Get available time slots for rescheduling (public, borrower self-service).

    The token is a JWT from the reschedule link.  No login needed.
    """
    _check_rate_limit(request, max_requests=20)

    svc = _get_reschedule_service(db)

    try:
        payload = svc.verify_reschedule_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    appointment_id = payload["appt_id"]
    org_id = payload.get("org_id")

    # Parse optional target_date
    parsed_date = None
    if target_date:
        try:
            parsed_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        appt = svc._get_appointment(appointment_id, org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        slots = svc.get_available_slots(
            appointment_id=appointment_id,
            target_date=parsed_date,
            org_id=org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "appointment_id": appointment_id,
        "current_start": appt.scheduled_start.isoformat(),
        "current_end": appt.scheduled_end.isoformat(),
        "duration_minutes": appt.duration_minutes,
        "attendee_name": appt.attendee_name,
        "title": appt.title,
        "slots": slots,
        "slots_count": len(slots),
    }


@router.post("/public/reschedule/{token}/confirm")
async def public_reschedule_confirm(
    request: Request,
    token: str,
    body: RescheduleConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm a reschedule from the borrower self-service link.

    Moves the appointment to the new time and sends a confirmation email.
    """
    _check_rate_limit(request, max_requests=10)

    svc = _get_reschedule_service(db)

    try:
        payload = svc.verify_reschedule_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    appointment_id = payload["appt_id"]
    org_id = payload.get("org_id")

    # Parse datetimes
    try:
        new_start = datetime.fromisoformat(body.new_start.replace("Z", "+00:00"))
        new_end = datetime.fromisoformat(body.new_end.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Make naive (consistent with DB storage)
    if new_start.tzinfo is not None:
        new_start = new_start.replace(tzinfo=None)
    if new_end.tzinfo is not None:
        new_end = new_end.replace(tzinfo=None)

    # Basic validation
    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    if new_start < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Cannot reschedule to a past time")

    try:
        result = svc.confirm_reschedule(
            appointment_id=appointment_id,
            new_start=new_start,
            new_end=new_end,
            org_id=org_id,
            confirmed_by="borrower",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # Conflict from _check_appointment_conflict bubbles up as 409
        raise

    db.commit()

    return {
        "status": "ok",
        "message": "Appointment rescheduled successfully",
        **result,
    }
