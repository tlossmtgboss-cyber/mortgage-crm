"""
Scheduling Optimizer Routes - AI-ranked slot recommendations and insights.

Provides endpoints for the scheduling optimization engine that learns from
historical booking patterns to recommend optimal time slots, predict no-show
risk, and generate org-level scheduling insights.

URL prefix: /api/v1/scheduler/optimize (applied by parent aggregator)

Endpoints:
  GET  /slots           - AI-ranked available slots for a date
  GET  /no-show-risk/{email} - No-show prediction for an attendee
  GET  /insights        - Org-level scheduling insights
  GET  /best-times      - Best times for the next week
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from services.scheduling_optimizer import SchedulingOptimizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/optimize", tags=["Scheduling Optimizer"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies from parent module (called during app startup)."""
    global _get_db, _get_current_user_func
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func


from db import get_async_db


async def get_current_user(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Resolve current user via the injected auth function."""
    if _get_current_user_func is None:
        raise RuntimeError("Scheduling optimizer dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Extract organization_id from user, raise 403 if missing."""
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# GET /slots - AI-ranked available slots
# ============================================================================

@router.get("/slots")
async def get_optimal_slots(
    request: Request,
    target_date: date = Query(..., description="Date to get optimized slots for (YYYY-MM-DD)"),
    count: int = Query(5, ge=1, le=20, description="Number of top slots to return"),
    duration_minutes: int = Query(30, ge=15, le=120, description="Appointment duration in minutes"),
    user_id: Optional[int] = Query(None, description="Specific user to check (defaults to current user)"),
    meeting_type: Optional[str] = Query(None, description="Meeting type filter"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get AI-ranked available time slots for a specific date.

    Slots are scored by predicted conversion probability based on historical
    show rates by hour, day of week, and meeting type. Higher-scored slots
    are more likely to result in completed appointments.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    target_user_id = user_id or current_user.id

    # Validate target_date is not in the past
    if target_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Cannot get slots for a past date",
        )

    try:
        result = await SchedulingOptimizer.get_optimal_slots(
            db=db,
            org_id=org_id,
            user_id=target_user_id,
            target_date=target_date,
            count=count,
            duration_minutes=duration_minutes,
            meeting_type=meeting_type,
        )
        return result
    except Exception as e:
        logger.exception(f"Error getting optimal slots: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute optimal slots")


# ============================================================================
# GET /no-show-risk/{email} - No-show prediction
# ============================================================================

@router.get("/no-show-risk/{email}")
async def get_no_show_risk(
    email: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Predict no-show risk for a specific attendee based on their historical
    appointment record within the organization.

    Returns risk level (low/medium/high/unknown), a numeric score (0.0-1.0),
    history counts, and an actionable recommendation.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    try:
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db,
            attendee_email=email.lower().strip(),
            org_id=org_id,
        )
        return result
    except Exception as e:
        logger.exception(f"Error computing no-show risk: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute no-show risk")


# ============================================================================
# GET /insights - Org-level insights
# ============================================================================

@router.get("/insights")
async def get_booking_insights(
    request: Request,
    days: int = Query(90, ge=7, le=365, description="Analysis period in days"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Generate comprehensive scheduling insights for the organization.

    Includes best booking hours, best days, average lead time, popular
    appointment types, conversion by booking source, and overall
    show/no-show/cancel rates.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    try:
        result = await SchedulingOptimizer.get_booking_insights(
            db=db,
            org_id=org_id,
            days=days,
        )
        return result
    except Exception as e:
        logger.exception(f"Error getting booking insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate insights")


# ============================================================================
# GET /best-times - Best times for next week
# ============================================================================

@router.get("/best-times")
async def get_best_times(
    request: Request,
    count: int = Query(10, ge=1, le=30, description="Number of top slots to return"),
    user_id: Optional[int] = Query(None, description="Specific user (defaults to current user)"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get the best available time slots for the next 7 business days,
    ranked by historical show rate.

    Useful for proactively suggesting meeting times to leads and clients.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    target_user_id = user_id or current_user.id

    try:
        result = await SchedulingOptimizer.get_best_times_next_week(
            db=db,
            org_id=org_id,
            user_id=target_user_id,
            count=count,
        )
        return result
    except Exception as e:
        logger.exception(f"Error getting best times: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute best times")
