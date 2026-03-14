"""
Scheduler Analytics - Calendar analytics dashboard API endpoints.

Endpoints:
  - GET /analytics/overview     Key metrics: total, completed, cancelled, no-shows, utilization
  - GET /analytics/trends       Daily/weekly appointment counts for charting
  - GET /analytics/by-type      Breakdown by appointment type (paginated)
  - GET /analytics/by-lo        Breakdown by loan officer (paginated, manager view)

All endpoints require authentication and are scoped to the user's organization.
"""

from datetime import date as date_type, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
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
# PYDANTIC RESPONSE MODELS
# =============================================================================

class AnalyticsOverview(BaseModel):
    """Top-level KPI metrics for the analytics dashboard."""
    period: str = Field(..., description="Time period code (7d, 30d, 90d)")
    start_date: Optional[str] = Field(None, description="Effective start date (ISO format)")
    end_date: Optional[str] = Field(None, description="Effective end date (ISO format)")
    total_appointments: int = Field(0, description="Total appointment count in period")
    completed: int = Field(0, description="Number of completed appointments")
    cancelled: int = Field(0, description="Number of cancelled appointments")
    no_shows: int = Field(0, description="Number of no-show appointments")
    rescheduled: int = Field(0, description="Number of rescheduled appointments")
    completion_rate: float = Field(0.0, description="Completion rate as percentage")
    avg_duration_minutes: float = Field(0.0, description="Average appointment duration in minutes")
    utilization_rate: float = Field(0.0, description="Utilization rate as percentage")
    busiest_day_of_week: Optional[str] = Field(None, description="Day name with most appointments")
    busiest_hour: Optional[int] = Field(None, description="Hour (0-23) with most appointments")
    busiest_hour_label: Optional[str] = Field(None, description="Formatted hour label (e.g. '10:00')")

    class Config:
        from_attributes = True


class TrendDatasets(BaseModel):
    """Time-series datasets for trend charts."""
    total: List[int] = Field(default_factory=list)
    completed: List[int] = Field(default_factory=list)
    cancelled: List[int] = Field(default_factory=list)
    no_shows: List[int] = Field(default_factory=list)


class PeakHourEntry(BaseModel):
    """Single cell in the peak hours heatmap grid."""
    day: str = Field(..., description="Day name (Monday-Sunday)")
    day_index: int = Field(..., description="Day index (0=Monday, 6=Sunday)")
    hour: int = Field(..., description="Hour of day (0-23)")
    count: int = Field(0, description="Appointment count for this slot")


class PeakHoursData(BaseModel):
    """Peak hours heatmap data."""
    period: str
    grid: List[PeakHourEntry] = Field(default_factory=list)
    max_count: int = Field(0)


class CancellationReason(BaseModel):
    """Single cancellation reason with count."""
    reason: str
    count: int


class CancellationData(BaseModel):
    """Cancellation rate breakdown."""
    period: str
    total_appointments: int = Field(0)
    cancelled: int = Field(0)
    rate: float = Field(0.0)
    reasons: List[CancellationReason] = Field(default_factory=list)


class AnalyticsTrends(BaseModel):
    """Time-series trend data with peak hours and cancellation breakdown."""
    period: str = Field(..., description="Time period code")
    start_date: Optional[str] = Field(None, description="Effective start date (ISO format)")
    end_date: Optional[str] = Field(None, description="Effective end date (ISO format)")
    granularity: str = Field("daily", description="Aggregation granularity (daily or weekly)")
    labels: List[str] = Field(default_factory=list, description="Date labels for x-axis")
    datasets: TrendDatasets = Field(default_factory=TrendDatasets)
    peak_hours: Optional[PeakHoursData] = Field(None, description="Peak hours heatmap data")
    cancellation: Optional[CancellationData] = Field(None, description="Cancellation breakdown")

    class Config:
        from_attributes = True


class TypeBreakdownEntry(BaseModel):
    """Single appointment type breakdown row."""
    type_id: Optional[int] = Field(None, description="Appointment type ID")
    type_name: str = Field("Unassigned", description="Appointment type name")
    color: str = Field("#94a3b8", description="Display color hex code")
    total: int = Field(0)
    completed: int = Field(0)
    cancelled: int = Field(0)
    no_shows: int = Field(0)
    avg_duration: float = Field(0.0, description="Average duration in minutes")
    percentage: float = Field(0.0, description="Percentage of total appointments")


class AnalyticsByType(BaseModel):
    """Paginated appointment breakdown by type."""
    period: str = Field(..., description="Time period code")
    total_count: int = Field(0, description="Total number of appointment types (before pagination)")
    limit: int = Field(50, description="Page size")
    offset: int = Field(0, description="Page offset")
    types: List[TypeBreakdownEntry] = Field(default_factory=list, description="Type breakdown rows")

    class Config:
        from_attributes = True


class LOBreakdownEntry(BaseModel):
    """Single loan officer breakdown row."""
    user_id: Optional[int] = Field(None, description="Loan officer user ID")
    name: str = Field("", description="Loan officer display name")
    total: int = Field(0)
    completed: int = Field(0)
    cancelled: int = Field(0)
    no_shows: int = Field(0)
    avg_duration: float = Field(0.0, description="Average duration in minutes")
    completion_rate: float = Field(0.0, description="Completion rate as percentage")
    utilization_rate: float = Field(0.0, description="Utilization rate as percentage")
    percentage: float = Field(0.0, description="Percentage of total appointments")


class AnalyticsByLO(BaseModel):
    """Paginated appointment breakdown by loan officer."""
    period: str = Field(..., description="Time period code")
    total_count: int = Field(0, description="Total number of loan officers (before pagination)")
    limit: int = Field(50, description="Page size")
    offset: int = Field(0, description="Page offset")
    loan_officers: List[LOBreakdownEntry] = Field(default_factory=list, description="LO breakdown rows")

    class Config:
        from_attributes = True


# =============================================================================
# HELPERS
# =============================================================================

def _effective_date_range(
    period: str,
    start_date: Optional[date_type],
    end_date: Optional[date_type],
) -> tuple:
    """
    Return (effective_start_str, effective_end_str) for inclusion in the response.
    When explicit dates are provided, they take documentation precedence.
    The service layer currently resolves ranges from the period string.
    """
    if start_date and end_date:
        return start_date.isoformat(), end_date.isoformat()
    # Compute from period string for informational purposes
    from datetime import timedelta
    now = datetime.utcnow().date()
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    delta = days_map.get(period, 30)
    return (now - timedelta(days=delta)).isoformat(), now.isoformat()


# =============================================================================
# OVERVIEW
# =============================================================================

@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    start_date: Optional[date_type] = Query(None, description="Explicit start date (YYYY-MM-DD) — reserved for future use"),
    end_date: Optional[date_type] = Query(None, description="Explicit end date (YYYY-MM-DD) — reserved for future use"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Key metrics for the analytics dashboard.

    Returns total_appointments, completed, cancelled, no_shows, rescheduled,
    avg_duration_minutes, utilization_rate, busiest_day_of_week, busiest_hour.

    The `start_date` and `end_date` parameters are accepted for API contract
    completeness. Currently the service resolves date ranges from the `period`
    parameter (7d, 30d, 90d).
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
        eff_start, eff_end = _effective_date_range(period, start_date, end_date)
        data["start_date"] = eff_start
        data["end_date"] = eff_end
        return AnalyticsOverview(**data)
    except Exception as e:
        logger.exception(f"Analytics overview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute analytics")


# =============================================================================
# TRENDS
# =============================================================================

@router.get("/analytics/trends", response_model=AnalyticsTrends)
async def analytics_trends(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    granularity: str = Query("daily", regex="^(daily|weekly)$", description="Aggregation granularity"),
    start_date: Optional[date_type] = Query(None, description="Explicit start date (YYYY-MM-DD) — reserved for future use"),
    end_date: Optional[date_type] = Query(None, description="Explicit end date (YYYY-MM-DD) — reserved for future use"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    db: Session = Depends(get_db),
):
    """
    Time-series data for trend charts.

    Returns labels, datasets (total, completed, cancelled, no_shows),
    peak_hours heatmap, and cancellation breakdown.

    The `start_date` and `end_date` parameters are accepted for API contract
    completeness. Currently the service resolves date ranges from the `period`
    parameter (7d, 30d, 90d).
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
        # Add effective date range
        eff_start, eff_end = _effective_date_range(period, start_date, end_date)
        data["start_date"] = eff_start
        data["end_date"] = eff_end
        return AnalyticsTrends(**data)
    except Exception as e:
        logger.exception(f"Analytics trends failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute trends")


# =============================================================================
# BY TYPE (paginated)
# =============================================================================

@router.get("/analytics/by-type", response_model=AnalyticsByType)
async def analytics_by_type(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of type rows to return"),
    offset: int = Query(0, ge=0, description="Number of type rows to skip"),
    db: Session = Depends(get_db),
):
    """
    Appointment breakdown by appointment type (paginated).

    Returns paginated list of types with total, completed, cancelled,
    no_shows, avg_duration, and percentage.
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
        all_types = data.get("types", [])
        total_count = len(all_types)
        paginated_types = all_types[offset:offset + limit]
        return AnalyticsByType(
            period=data.get("period", period),
            total_count=total_count,
            limit=limit,
            offset=offset,
            types=[TypeBreakdownEntry(**t) for t in paginated_types],
        )
    except Exception as e:
        logger.exception(f"Analytics by-type failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute type breakdown")


# =============================================================================
# BY LOAN OFFICER (paginated)
# =============================================================================

@router.get("/analytics/by-lo", response_model=AnalyticsByLO)
async def analytics_by_lo(
    request: Request,
    period: str = Query("30d", regex="^(7d|30d|90d)$", description="Time period"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of LO rows to return"),
    offset: int = Query(0, ge=0, description="Number of LO rows to skip"),
    db: Session = Depends(get_db),
):
    """
    Appointment breakdown by loan officer (manager view, paginated).
    Only admins can access this endpoint; non-admins receive 403.

    Returns paginated list of loan officers with total, completed,
    cancelled, utilization_rate, and completion_rate.
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
        all_los = data.get("loan_officers", [])
        total_count = len(all_los)
        paginated_los = all_los[offset:offset + limit]
        return AnalyticsByLO(
            period=data.get("period", period),
            total_count=total_count,
            limit=limit,
            offset=offset,
            loan_officers=[LOBreakdownEntry(**lo) for lo in paginated_los],
        )
    except Exception as e:
        logger.exception(f"Analytics by-lo failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute LO breakdown")
