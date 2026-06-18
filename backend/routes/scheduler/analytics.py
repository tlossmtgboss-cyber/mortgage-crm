"""
Scheduler Analytics - Calendar analytics dashboard API endpoints.

Endpoints:
  - GET /analytics/overview     Key metrics: total, completed, cancelled, no-shows, utilization
  - GET /analytics/trends       Daily/weekly appointment counts for charting
  - GET /analytics/by-type      Breakdown by appointment type (paginated)
  - GET /analytics/by-lo        Breakdown by loan officer (paginated, manager view)

All endpoints require authentication and are scoped to the user's organization.
"""

import csv
import io
import json
import math
from datetime import date as date_type, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from db import get_db
from middleware.feature_gate import require_feature_tier
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
# REDIS ANALYTICS CACHE HELPERS
# =============================================================================
# TTL: 300 seconds (5 minutes) — analytics tolerate slight staleness.
# All Redis errors are silently swallowed so analytics never breaks on Redis outage.

_ANALYTICS_CACHE_TTL = 300


def _analytics_cache_key(org_id: int, endpoint: str, **params) -> str:
    param_str = ":".join(f"{k}={v}" for k, v in sorted(params.items()))
    return f"analytics:{org_id}:{endpoint}:{param_str}"


def _analytics_cache_get(key: str):
    try:
        from services.redis_service import redis_service
        r = redis_service.get_client()
        if r is None:
            return None
        raw = r.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.debug("Analytics cache GET failed key=%s: %s", key, exc)
        return None


def _analytics_cache_set(key: str, value: dict) -> None:
    try:
        from services.redis_service import redis_service
        r = redis_service.get_client()
        if r is None:
            return
        r.setex(key, _ANALYTICS_CACHE_TTL, json.dumps(value))
    except Exception as exc:
        logger.debug("Analytics cache SET failed key=%s: %s", key, exc)


# =============================================================================
# BRANCH MANAGER SCOPING HELPERS
# =============================================================================

def _is_branch_manager(user) -> bool:
    role = getattr(user, 'permission_role', '') or ''
    return role.lower() in ('branch_manager', 'manager', 'team_lead', 'management')


def _get_managed_user_ids(user_id: int, org_id: int, db) -> list:
    """Return IDs of users managed by this user (direct reports + same-branch peers)."""
    try:
        from database.models.core import User
        from sqlalchemy import or_ as sql_or

        manager = db.query(User.branch_id).filter(
            User.id == user_id,
            User.organization_id == org_id,
        ).first()
        manager_branch_id = manager.branch_id if manager else None

        scoping_conditions = [User.manager_id == user_id]
        if manager_branch_id is not None:
            scoping_conditions.append(User.branch_id == manager_branch_id)

        rows = db.query(User.id).filter(
            User.organization_id == org_id,
            sql_or(*scoping_conditions),
        ).all()
        ids = [str(row.id) for row in rows]
    except Exception as e:
        logger.warning("_get_managed_user_ids failed (falling back to self-only): %s", e)
        ids = []

    if str(user_id) not in ids:
        ids.append(str(user_id))
    return ids


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")


class AnalyticsByType(BaseModel):
    """Paginated appointment breakdown by type."""
    period: str = Field(..., description="Time period code")
    types: List[TypeBreakdownEntry] = Field(default_factory=list, description="Type breakdown rows")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")

    model_config = ConfigDict(from_attributes=True)


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
    loan_officers: List[LOBreakdownEntry] = Field(default_factory=list, description="LO breakdown rows")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")

    model_config = ConfigDict(from_attributes=True)


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
    now = datetime.now(timezone.utc).date()
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    delta = days_map.get(period, 30)
    return (now - timedelta(days=delta)).isoformat(), now.isoformat()


# =============================================================================
# OVERVIEW
# =============================================================================

@router.get("/analytics/overview", response_model=AnalyticsOverview)
@require_feature_tier("scheduler_analytics")
async def analytics_overview(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
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

    # Three-tier access: admin → org-wide, branch_manager → team, LO → self
    effective_user_id = None
    effective_user_ids = None

    if _is_scheduler_admin(current_user):
        if user_id and user_id != current_user.id:
            effective_user_id = user_id
        elif user_id == current_user.id:
            effective_user_id = current_user.id
    elif _is_branch_manager(current_user):
        if user_id and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Branch managers cannot view arbitrary users' analytics")
        managed = _get_managed_user_ids(current_user.id, org_id, db)
        effective_user_ids = [int(uid) for uid in managed]
    else:
        effective_user_id = current_user.id

    try:
        cache_key = _analytics_cache_key(
            org_id, "overview", period=period, user_id=effective_user_id or 0,
        )
        cached = _analytics_cache_get(cache_key)
        if cached is not None:
            return AnalyticsOverview(**cached)

        data = get_overview_metrics(
            db, models, org_id, period=period,
            user_id=effective_user_id, user_ids=effective_user_ids,
        )
        eff_start, eff_end = _effective_date_range(period, start_date, end_date)
        data["start_date"] = eff_start
        data["end_date"] = eff_end
        _analytics_cache_set(cache_key, data)
        return AnalyticsOverview(**data)
    except Exception as e:
        logger.exception(f"Analytics overview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute analytics")


# =============================================================================
# TRENDS
# =============================================================================

@router.get("/analytics/trends", response_model=AnalyticsTrends)
@require_feature_tier("scheduler_analytics")
async def analytics_trends(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
    granularity: str = Query("daily", pattern="^(daily|weekly)$", description="Aggregation granularity"),
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

    effective_user_id = None
    effective_user_ids = None

    if _is_scheduler_admin(current_user):
        if user_id and user_id != current_user.id:
            effective_user_id = user_id
        elif user_id == current_user.id:
            effective_user_id = current_user.id
    elif _is_branch_manager(current_user):
        if user_id and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Branch managers cannot view arbitrary users' analytics")
        managed = _get_managed_user_ids(current_user.id, org_id, db)
        effective_user_ids = [int(uid) for uid in managed]
    else:
        effective_user_id = current_user.id

    try:
        cache_key = _analytics_cache_key(
            org_id, "trends",
            period=period, granularity=granularity, user_id=effective_user_id or 0,
        )
        cached = _analytics_cache_get(cache_key)
        if cached is not None:
            return AnalyticsTrends(**cached)

        data = get_appointment_trends(
            db, models, org_id, period=period, granularity=granularity,
            user_id=effective_user_id, user_ids=effective_user_ids,
        )
        peak = get_peak_hours(
            db, models, org_id, period=period,
            user_id=effective_user_id, user_ids=effective_user_ids,
        )
        data["peak_hours"] = peak
        cancellation = get_cancellation_rate(
            db, models, org_id, period=period,
            user_id=effective_user_id, user_ids=effective_user_ids,
        )
        data["cancellation"] = cancellation
        eff_start, eff_end = _effective_date_range(period, start_date, end_date)
        data["start_date"] = eff_start
        data["end_date"] = eff_end
        _analytics_cache_set(cache_key, data)
        return AnalyticsTrends(**data)
    except Exception as e:
        logger.exception(f"Analytics trends failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute trends")


# =============================================================================
# BY TYPE (paginated)
# =============================================================================

@router.get("/analytics/by-type", response_model=AnalyticsByType)
@require_feature_tier("scheduler_analytics")
async def analytics_by_type(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
    user_id: Optional[int] = Query(None, description="Filter by specific user (admin only)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Number of items per page"),
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

    effective_user_id = None
    effective_user_ids = None

    if _is_scheduler_admin(current_user):
        if user_id and user_id != current_user.id:
            effective_user_id = user_id
        elif user_id == current_user.id:
            effective_user_id = current_user.id
    elif _is_branch_manager(current_user):
        if user_id and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Branch managers cannot view arbitrary users' analytics")
        managed = _get_managed_user_ids(current_user.id, org_id, db)
        effective_user_ids = [int(uid) for uid in managed]
    else:
        effective_user_id = current_user.id

    try:
        cache_key = _analytics_cache_key(
            org_id, "by_type", period=period, user_id=effective_user_id or 0,
        )
        cached = _analytics_cache_get(cache_key)
        if cached is not None:
            data = cached
        else:
            data = get_by_type_breakdown(
                db, models, org_id, period=period,
                user_id=effective_user_id, user_ids=effective_user_ids,
            )
            _analytics_cache_set(cache_key, data)
        all_types = data.get("types", [])
        total_count = len(all_types)
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        offset = (page - 1) * page_size
        paginated_types = all_types[offset:offset + page_size]
        return AnalyticsByType(
            period=data.get("period", period),
            types=[TypeBreakdownEntry(**t) for t in paginated_types],
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total_count,
                total_pages=total_pages,
                has_next=page < total_pages,
            ),
        )
    except Exception as e:
        logger.exception(f"Analytics by-type failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute type breakdown")


# =============================================================================
# BY LOAN OFFICER (paginated)
# =============================================================================

@router.get("/analytics/by-lo", response_model=AnalyticsByLO)
@require_feature_tier("scheduler_analytics")
async def analytics_by_lo(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Number of items per page"),
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

    # Admins see all LOs; branch managers see their direct reports; others are blocked
    is_admin = _is_scheduler_admin(current_user)
    is_manager = _is_branch_manager(current_user)
    if not is_admin and not is_manager:
        raise HTTPException(status_code=403, detail="Admin or branch manager access required for team analytics")

    # Build cache key before the DB-heavy _get_managed_user_ids call
    # (manager scoping baked in via user id; org-wide requests use user_id=0)
    cache_key = _analytics_cache_key(
        org_id, "by_lo", period=period, user_id=current_user.id if is_manager else 0,
    )
    cached = _analytics_cache_get(cache_key)
    if cached is not None:
        data = cached
    else:
        # Cache miss — resolve effective user scope (2 DB queries for managers)
        effective_user_ids = None
        if is_manager:
            managed = _get_managed_user_ids(current_user.id, org_id, db)
            effective_user_ids = [int(uid) for uid in managed]

        data = get_by_lo_breakdown(db, models, org_id, period=period, user_ids=effective_user_ids)
        _analytics_cache_set(cache_key, data)

    try:
        all_los = data.get("loan_officers", [])
        total_count = len(all_los)
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        offset = (page - 1) * page_size
        paginated_los = all_los[offset:offset + page_size]
        return AnalyticsByLO(
            period=data.get("period", period),
            loan_officers=[LOBreakdownEntry(**lo) for lo in paginated_los],
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total_count,
                total_pages=total_pages,
                has_next=page < total_pages,
            ),
        )
    except Exception as e:
        logger.exception(f"Analytics by-lo failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute LO breakdown")


# =============================================================================
# CSV EXPORT (admin only)
# =============================================================================

@router.get("/analytics/export/csv")
@require_feature_tier("scheduler_analytics")
async def analytics_export_csv(
    request: Request,
    start_date: date_type = Query(..., description="Export start date (YYYY-MM-DD)"),
    end_date: date_type = Query(..., description="Export end date (YYYY-MM-DD)"),
    report_type: str = Query(
        "appointments",
        pattern="^(overview|appointments|by_lo|by_type)$",
        description="Report type: overview, appointments, by_lo, by_type",
    ),
    db: Session = Depends(get_db),
):
    """Export appointment analytics as a CSV file (admin only)."""
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required for CSV export")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")

    models = get_models()
    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        days = (end_date - start_date).days
        period = "7d" if days <= 7 else ("30d" if days <= 30 else "90d")

        if report_type == "appointments":
            _write_appointments_csv(writer, db, models, org_id, start_date, end_date)

        elif report_type == "by_lo":
            data = get_by_lo_breakdown(db, models, org_id, period=period)
            writer.writerow(["lo_name", "total", "completed", "cancelled", "no_shows", "show_rate"])
            for lo in data.get("loan_officers", []):
                total = lo.get("total", 0)
                no_shows = lo.get("no_shows", 0)
                show_rate = round(((total - no_shows) / total) * 100, 1) if total > 0 else 0.0
                writer.writerow([
                    lo.get("name", ""), total, lo.get("completed", 0),
                    lo.get("cancelled", 0), no_shows, show_rate,
                ])

        elif report_type == "by_type":
            data = get_by_type_breakdown(db, models, org_id, period=period)
            writer.writerow(["type_name", "total", "completed", "cancelled", "no_shows", "avg_duration_minutes", "show_rate"])
            for t in data.get("types", []):
                total = t.get("total", 0)
                no_shows = t.get("no_shows", 0)
                show_rate = round(((total - no_shows) / total) * 100, 1) if total > 0 else 0.0
                writer.writerow([
                    t.get("type_name", ""), total, t.get("completed", 0),
                    t.get("cancelled", 0), no_shows, t.get("avg_duration", 0.0), show_rate,
                ])

        else:  # overview
            data = get_overview_metrics(db, models, org_id, period=period)
            writer.writerow([
                "period", "start_date", "end_date", "total_appointments",
                "completed", "cancelled", "no_shows", "rescheduled",
                "completion_rate", "avg_duration_minutes", "utilization_rate",
                "busiest_day_of_week", "busiest_hour",
            ])
            writer.writerow([
                period, start_str, end_str,
                data.get("total_appointments", 0), data.get("completed", 0),
                data.get("cancelled", 0), data.get("no_shows", 0),
                data.get("rescheduled", 0), data.get("completion_rate", 0.0),
                data.get("avg_duration_minutes", 0.0), data.get("utilization_rate", 0.0),
                data.get("busiest_day_of_week", ""), data.get("busiest_hour", ""),
            ])

        filename = f"appointments-{start_str}-{end_str}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Analytics CSV export failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV export")


def _write_appointments_csv(
    writer,
    db: Session,
    models: dict,
    org_id: int,
    start_date: date_type,
    end_date: date_type,
) -> None:
    """Write raw appointment rows for the date range to the CSV writer."""
    from datetime import datetime as dt
    from sqlalchemy import and_

    Appointment = models.get("Appointment")
    AppointmentType = models.get("AppointmentType")
    if not Appointment:
        writer.writerow(["error"])
        writer.writerow(["Appointment model not available"])
        return

    writer.writerow([
        "date", "lo_name", "attendee_name", "appointment_type",
        "status", "duration_minutes", "source",
    ])

    type_names: dict = {}
    if AppointmentType:
        try:
            types = db.query(AppointmentType).filter(
                AppointmentType.organization_id == org_id,
                AppointmentType.is_active == True,
            ).all()
            type_names = {t.id: t.type_name for t in types}
        except Exception:
            pass

    user_names: dict = {}
    try:
        from database.models.core import User
        users = db.query(User.id, User.first_name, User.last_name).filter(
            User.organization_id == org_id,
        ).all()
        user_names = {
            u.id: f"{u.first_name or ''} {u.last_name or ''}".strip() or f"User {u.id}"
            for u in users
        }
    except Exception:
        pass

    start_dt = dt.combine(start_date, dt.min.time())
    end_dt = dt.combine(end_date, dt.max.time())

    rows = db.query(
        Appointment.id,
        Appointment.scheduled_start,
        Appointment.assigned_user_id,
        Appointment.attendee_name,
        Appointment.appointment_type_id,
        Appointment.status,
        Appointment.duration_minutes,
        Appointment.external_source,
        Appointment.booked_by_ai,
    ).filter(
        and_(
            Appointment.organization_id == org_id,
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt,
            Appointment.deleted_at.is_(None),
        )
    ).order_by(Appointment.scheduled_start).all()

    for row in rows:
        date_str = row.scheduled_start.date().isoformat() if row.scheduled_start else ""
        lo_name = user_names.get(row.assigned_user_id, f"User {row.assigned_user_id}") if row.assigned_user_id else ""

        raw_name = row.attendee_name or ""
        if raw_name:
            parts = raw_name.split()
            masked_name = f"{parts[0]} {parts[-1][0]}." if len(parts) >= 2 else (parts[0] if parts else "")
        else:
            masked_name = ""

        type_name = type_names.get(row.appointment_type_id, "Unassigned") if row.appointment_type_id else "Unassigned"
        status = row.status.value if hasattr(row.status, "value") else str(row.status or "")
        source = row.external_source or ("ai" if row.booked_by_ai else "manual")

        writer.writerow([date_str, lo_name, masked_name, type_name, status, row.duration_minutes or 0, source])
