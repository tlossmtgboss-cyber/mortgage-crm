"""
Scheduler Analytics - Calendar analytics dashboard API endpoints.

Endpoints:
  - GET /analytics/overview     Key metrics: total, completed, cancelled, no-shows, utilization
  - GET /analytics/trends       Daily/weekly appointment counts for charting
  - GET /analytics/by-type      Breakdown by appointment type
  - GET /analytics/by-lo        Breakdown by loan officer (manager view)

All endpoints require authentication and are scoped to the user's organization.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
)
from services.calendar_analytics_service import (
    get_overview_metrics,
    get_appointment_trends,
    get_peak_hours,
    get_cancellation_rate,
    get_by_type_breakdown,
    get_by_lo_breakdown,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# OVERVIEW
# =============================================================================

@router.get("/analytics/overview")
async def analytics_overview(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Key metrics for the analytics dashboard.

    Returns total_appointments, completed, cancelled, no_shows, rescheduled,
    avg_duration_minutes, utilization_rate, busiest_day_of_week, busiest_hour.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    # Non-admins can only see their own data
    effective_user_id = user_id
    if user_id and user_id != current_user.id and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can view other users' analytics")
    if not _is_scheduler_admin(current_user):
        effective_user_id = current_user.id

    try:
        data = get_overview_metrics(db, models, org_id, period=period, user_id=effective_user_id)
        return data
    except Exception as e:
        logger.exception(f"Analytics overview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute analytics")


# =============================================================================
# TRENDS
# =============================================================================

@router.get("/analytics/trends")
async def analytics_trends(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    granularity: str = Query("daily", regex="^(daily|weekly)$", description="Aggregation granularity"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Time-series data for trend charts.

    Returns {labels: [...], datasets: {total: [...], completed: [...], cancelled: [...], no_shows: [...]}}.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    effective_user_id = user_id
    if user_id and user_id != current_user.id and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can view other users' analytics")
    if not _is_scheduler_admin(current_user):
        effective_user_id = current_user.id

    try:
        data = get_appointment_trends(
            db, models, org_id, period=period, granularity=granularity, user_id=effective_user_id
        )
        # Also include peak hours data for the heatmap
        peak = get_peak_hours(db, models, org_id, period=period, user_id=effective_user_id)
        data["peak_hours"] = peak
        # Include cancellation breakdown
        cancellation = get_cancellation_rate(db, models, org_id, period=period, user_id=effective_user_id)
        data["cancellation"] = cancellation
        return data
    except Exception as e:
        logger.exception(f"Analytics trends failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute trends")


# =============================================================================
# BY TYPE
# =============================================================================

@router.get("/analytics/by-type")
async def analytics_by_type(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Appointment breakdown by appointment type.

    Returns {types: [{type_name, total, completed, cancelled, no_shows, avg_duration, percentage}, ...]}.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    effective_user_id = user_id
    if user_id and user_id != current_user.id and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can view other users' analytics")
    if not _is_scheduler_admin(current_user):
        effective_user_id = current_user.id

    try:
        data = get_by_type_breakdown(db, models, org_id, period=period, user_id=effective_user_id)
        return data
    except Exception as e:
        logger.exception(f"Analytics by-type failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute type breakdown")


# =============================================================================
# BY LOAN OFFICER
# =============================================================================

@router.get("/analytics/by-lo")
async def analytics_by_lo(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    db: Session = Depends(get_db),
):
    """
    Appointment breakdown by loan officer (manager view).
    Only admins can access this endpoint; non-admins see just their own data.

    Returns {loan_officers: [{name, total, completed, cancelled, utilization_rate, ...}, ...]}.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required for team analytics")

    try:
        data = get_by_lo_breakdown(db, models, org_id, period=period)
        return data
    except Exception as e:
        logger.exception(f"Analytics by-lo failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute LO breakdown")
