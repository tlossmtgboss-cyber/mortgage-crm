"""
Analytics Routes - Application analytics and reporting endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, case, extract
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def get_db():
    """Database session dependency - imported from main"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(db: Session):
    """Get current user - simplified for analytics"""
    from auth.dependencies import get_current_user as main_get_current_user
    return main_get_current_user


@router.get("/applications/overview")
async def get_application_overview(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get overview metrics for borrower applications."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    # Build base query filters
    base_filters = f"created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    # Get aggregate metrics
    metrics_query = text(f"""
        SELECT
            COUNT(*) as total_applications,
            COUNT(CASE WHEN status = 'submitted' THEN 1 END) as submitted,
            COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
            COUNT(CASE WHEN status = 'draft' THEN 1 END) as draft,
            COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned,
            COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
            AVG(progress_percentage) as avg_progress,
            AVG(time_spent_seconds) / 60.0 as avg_time_minutes,
            COUNT(CASE WHEN submitted_at IS NOT NULL THEN 1 END) as completed_count
        FROM borrower_applications
        WHERE {base_filters}
    """)

    result = db.execute(metrics_query, params).fetchone()

    # Calculate conversion rate
    total = result.total_applications or 0
    completed = result.completed_count or 0
    conversion_rate = (completed / total * 100) if total > 0 else 0

    return {
        "period_days": days,
        "metrics": {
            "total_applications": total,
            "submitted": result.submitted or 0,
            "in_progress": result.in_progress or 0,
            "draft": result.draft or 0,
            "abandoned": result.abandoned or 0,
            "approved": result.approved or 0,
            "avg_progress": round(float(result.avg_progress or 0), 1),
            "avg_time_minutes": round(float(result.avg_time_minutes or 0), 1),
            "conversion_rate": round(conversion_rate, 1),
        }
    }


@router.get("/applications/by-status")
async def get_applications_by_status(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get application counts broken down by status."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            status,
            COUNT(*) as count
        FROM borrower_applications
        WHERE {base_filters}
        GROUP BY status
        ORDER BY count DESC
    """)

    results = db.execute(query, params).fetchall()

    return {
        "period_days": days,
        "by_status": [
            {"status": row.status, "count": row.count}
            for row in results
        ]
    }


@router.get("/applications/by-step")
async def get_applications_by_step(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get application counts broken down by current step (for incomplete apps)."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter AND status IN ('draft', 'in_progress')"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            current_step,
            COUNT(*) as count
        FROM borrower_applications
        WHERE {base_filters}
        GROUP BY current_step
        ORDER BY count DESC
    """)

    results = db.execute(query, params).fetchall()

    return {
        "period_days": days,
        "by_step": [
            {"step": row.current_step, "count": row.count}
            for row in results
        ]
    }


@router.get("/applications/funnel")
async def get_application_funnel(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get application funnel with drop-off rates at each step."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    # Get total and step completions
    query = text(f"""
        SELECT
            COUNT(*) as total_started,
            COUNT(CASE WHEN completed_steps::text LIKE '%personal_info%' THEN 1 END) as completed_personal,
            COUNT(CASE WHEN completed_steps::text LIKE '%property%' THEN 1 END) as completed_property,
            COUNT(CASE WHEN completed_steps::text LIKE '%income%' THEN 1 END) as completed_income,
            COUNT(CASE WHEN completed_steps::text LIKE '%assets%' THEN 1 END) as completed_assets,
            COUNT(CASE WHEN completed_steps::text LIKE '%credit_auth%' THEN 1 END) as completed_credit,
            COUNT(CASE WHEN status = 'submitted' THEN 1 END) as submitted
        FROM borrower_applications
        WHERE {base_filters}
    """)

    result = db.execute(query, params).fetchone()

    total = result.total_started or 0

    def calc_rate(count, base):
        return round((count / base * 100), 1) if base > 0 else 0

    funnel = [
        {
            "step": "Started",
            "count": total,
            "rate": 100,
            "drop_off": 0,
        },
        {
            "step": "Personal Info",
            "count": result.completed_personal or 0,
            "rate": calc_rate(result.completed_personal or 0, total),
            "drop_off": calc_rate(total - (result.completed_personal or 0), total),
        },
        {
            "step": "Property",
            "count": result.completed_property or 0,
            "rate": calc_rate(result.completed_property or 0, total),
            "drop_off": calc_rate((result.completed_personal or 0) - (result.completed_property or 0), result.completed_personal or 1),
        },
        {
            "step": "Income",
            "count": result.completed_income or 0,
            "rate": calc_rate(result.completed_income or 0, total),
            "drop_off": calc_rate((result.completed_property or 0) - (result.completed_income or 0), result.completed_property or 1),
        },
        {
            "step": "Credit Auth",
            "count": result.completed_credit or 0,
            "rate": calc_rate(result.completed_credit or 0, total),
            "drop_off": calc_rate((result.completed_income or 0) - (result.completed_credit or 0), result.completed_income or 1),
        },
        {
            "step": "Submitted",
            "count": result.submitted or 0,
            "rate": calc_rate(result.submitted or 0, total),
            "drop_off": calc_rate((result.completed_credit or 0) - (result.submitted or 0), result.completed_credit or 1),
        },
    ]

    return {
        "period_days": days,
        "funnel": funnel,
        "overall_conversion": calc_rate(result.submitted or 0, total),
    }


@router.get("/applications/daily-trend")
async def get_daily_trend(
    days: int = Query(30, ge=1, le=90),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get daily application counts for trend visualization."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'submitted' THEN 1 END) as submitted
        FROM borrower_applications
        WHERE {base_filters}
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """)

    results = db.execute(query, params).fetchall()

    return {
        "period_days": days,
        "daily_data": [
            {
                "date": row.date.isoformat() if row.date else None,
                "total": row.total,
                "submitted": row.submitted,
            }
            for row in results
        ]
    }


@router.get("/applications/by-source")
async def get_applications_by_source(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get application counts by referral source."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "ba.created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND ba.owner_id = :lo_id"
        params["lo_id"] = lo_id

    # Join with leads to get source info
    query = text(f"""
        SELECT
            COALESCE(l.source, 'Direct') as source,
            COUNT(*) as count,
            COUNT(CASE WHEN ba.status = 'submitted' THEN 1 END) as submitted
        FROM borrower_applications ba
        LEFT JOIN leads l ON ba.lead_id = l.id
        WHERE {base_filters}
        GROUP BY COALESCE(l.source, 'Direct')
        ORDER BY count DESC
    """)

    results = db.execute(query, params).fetchall()

    return {
        "period_days": days,
        "by_source": [
            {
                "source": row.source,
                "count": row.count,
                "submitted": row.submitted,
                "conversion_rate": round((row.submitted / row.count * 100), 1) if row.count > 0 else 0,
            }
            for row in results
        ]
    }


@router.get("/applications/avg-completion-time")
async def get_avg_completion_time(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get average time to complete applications."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter AND submitted_at IS NOT NULL"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            AVG(EXTRACT(EPOCH FROM (submitted_at - created_at)) / 3600) as avg_hours,
            MIN(EXTRACT(EPOCH FROM (submitted_at - created_at)) / 3600) as min_hours,
            MAX(EXTRACT(EPOCH FROM (submitted_at - created_at)) / 3600) as max_hours,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (submitted_at - created_at)) / 3600) as median_hours,
            COUNT(*) as sample_size
        FROM borrower_applications
        WHERE {base_filters}
    """)

    result = db.execute(query, params).fetchone()

    return {
        "period_days": days,
        "completion_time": {
            "avg_hours": round(float(result.avg_hours or 0), 1),
            "min_hours": round(float(result.min_hours or 0), 1),
            "max_hours": round(float(result.max_hours or 0), 1),
            "median_hours": round(float(result.median_hours or 0), 1),
            "sample_size": result.sample_size or 0,
        }
    }


@router.get("/applications/device-breakdown")
async def get_device_breakdown(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get application counts by device type."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            COALESCE(device_info->>'device_type', 'Unknown') as device_type,
            COUNT(*) as count,
            COUNT(CASE WHEN status = 'submitted' THEN 1 END) as submitted
        FROM borrower_applications
        WHERE {base_filters}
        GROUP BY COALESCE(device_info->>'device_type', 'Unknown')
        ORDER BY count DESC
    """)

    results = db.execute(query, params).fetchall()

    return {
        "period_days": days,
        "by_device": [
            {
                "device": row.device_type,
                "count": row.count,
                "submitted": row.submitted,
                "conversion_rate": round((row.submitted / row.count * 100), 1) if row.count > 0 else 0,
            }
            for row in results
        ]
    }


@router.get("/applications/lo-performance")
async def get_lo_performance(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get application performance by loan officer."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    query = text("""
        SELECT
            ba.owner_id,
            COALESCE(u.first_name || ' ' || u.last_name, u.email, 'Unassigned') as lo_name,
            COUNT(*) as total,
            COUNT(CASE WHEN ba.status = 'submitted' THEN 1 END) as submitted,
            AVG(ba.progress_percentage) as avg_progress,
            AVG(ba.time_spent_seconds) / 60.0 as avg_time_minutes
        FROM borrower_applications ba
        LEFT JOIN users u ON ba.owner_id = u.id
        WHERE ba.created_at >= :date_filter
        GROUP BY ba.owner_id, u.first_name, u.last_name, u.email
        ORDER BY submitted DESC, total DESC
    """)

    results = db.execute(query, {"date_filter": date_filter}).fetchall()

    return {
        "period_days": days,
        "by_lo": [
            {
                "lo_id": row.owner_id,
                "lo_name": row.lo_name,
                "total": row.total,
                "submitted": row.submitted,
                "avg_progress": round(float(row.avg_progress or 0), 1),
                "avg_time_minutes": round(float(row.avg_time_minutes or 0), 1),
                "conversion_rate": round((row.submitted / row.total * 100), 1) if row.total > 0 else 0,
            }
            for row in results
        ]
    }


@router.get("/applications/drop-off-analysis")
async def get_drop_off_analysis(
    days: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Analyze where users are dropping off in the application process."""

    date_filter = datetime.now(timezone.utc) - timedelta(days=days)

    base_filters = "created_at >= :date_filter AND status IN ('draft', 'in_progress', 'abandoned')"
    params = {"date_filter": date_filter}

    if lo_id:
        base_filters += " AND owner_id = :lo_id"
        params["lo_id"] = lo_id

    query = text(f"""
        SELECT
            current_step,
            COUNT(*) as count,
            AVG(time_spent_seconds) / 60.0 as avg_time_on_step,
            AVG(progress_percentage) as avg_progress
        FROM borrower_applications
        WHERE {base_filters}
        GROUP BY current_step
        ORDER BY count DESC
    """)

    results = db.execute(query, params).fetchall()

    # Calculate total for percentages
    total = sum(row.count for row in results)

    return {
        "period_days": days,
        "drop_off_points": [
            {
                "step": row.current_step,
                "count": row.count,
                "percentage": round((row.count / total * 100), 1) if total > 0 else 0,
                "avg_time_on_step": round(float(row.avg_time_on_step or 0), 1),
                "avg_progress": round(float(row.avg_progress or 0), 1),
            }
            for row in results
        ],
        "total_incomplete": total,
    }
