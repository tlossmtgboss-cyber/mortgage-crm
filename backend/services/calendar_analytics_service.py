"""
Calendar Analytics Service - Business logic for appointment analytics.

Provides:
  - calculate_utilization: booked / available percentage for a user
  - get_appointment_trends: time series data for charting
  - get_peak_hours: histogram of appointments by hour
  - get_cancellation_rate: cancellation % with breakdown by reason
  - get_overview_metrics: top-level KPI aggregation
  - get_by_type_breakdown: appointment counts/rates grouped by type
  - get_by_lo_breakdown: appointment counts/rates grouped by loan officer
"""

from datetime import datetime, date, timedelta, time, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, case, extract, and_, cast, Date as SQLDate
import logging

from smart_scheduler_models import AppointmentStatus

logger = logging.getLogger(__name__)

# Statuses considered "terminal" — the appointment is over
_TERMINAL_STATUSES = {
    AppointmentStatus.COMPLETED.value,
    AppointmentStatus.CANCELLED.value,
    AppointmentStatus.NO_SHOW.value,
    AppointmentStatus.RESCHEDULED.value,
}

_COMPLETED_STATUSES = {AppointmentStatus.COMPLETED.value, AppointmentStatus.CHECKED_IN.value}
_ACTIVE_STATUSES = {
    AppointmentStatus.BOOKED.value,
    AppointmentStatus.CONFIRMED.value,
    AppointmentStatus.REMINDED.value,
    AppointmentStatus.TENTATIVE.value,
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _resolve_date_range(period: str) -> Tuple[datetime, datetime]:
    """Convert period string to (start, end) datetimes."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if period == "7d":
        start = now - timedelta(days=7)
    elif period == "90d":
        start = now - timedelta(days=90)
    else:  # default 30d
        start = now - timedelta(days=30)
    return start, now


def _get_appointment_model(models: dict):
    """Get Appointment model from models dict."""
    return models.get("Appointment")


# =============================================================================
# OVERVIEW METRICS
# =============================================================================

def get_overview_metrics(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
    user_id: Optional[int] = None,
) -> dict:
    """
    Calculate top-level KPI metrics:
    total_appointments, completed, cancelled, no_shows, rescheduled,
    avg_duration_minutes, utilization_rate, busiest_day_of_week, busiest_hour.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"error": "Appointment model not available"}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    # Core counts
    row = db.query(
        func.count(Appointment.id).label("total"),
        func.count(case(
            (Appointment.status.in_(list(_COMPLETED_STATUSES)), 1),
        )).label("completed"),
        func.count(case(
            (Appointment.status == AppointmentStatus.CANCELLED.value, 1),
        )).label("cancelled"),
        func.count(case(
            (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
        )).label("no_shows"),
        func.count(case(
            (Appointment.status == AppointmentStatus.RESCHEDULED.value, 1),
        )).label("rescheduled"),
        func.avg(Appointment.duration_minutes).label("avg_duration"),
    ).filter(and_(*filters)).first()

    total = row.total or 0
    completed = row.completed or 0
    cancelled = row.cancelled or 0
    no_shows = row.no_shows or 0
    rescheduled = row.rescheduled or 0
    avg_duration = round(float(row.avg_duration or 0), 1)

    # Busiest day of week (0=Sunday in extract('dow'), but Python weekday is 0=Monday)
    busiest_dow_row = db.query(
        extract("dow", Appointment.scheduled_start).label("dow"),
        func.count(Appointment.id).label("cnt"),
    ).filter(and_(*filters)).group_by("dow").order_by(func.count(Appointment.id).desc()).first()

    busiest_day = None
    if busiest_dow_row:
        # PostgreSQL dow: 0=Sunday, 1=Monday, ... 6=Saturday
        pg_dow = int(busiest_dow_row.dow)
        python_idx = (pg_dow - 1) % 7  # Convert to 0=Monday
        busiest_day = DAY_NAMES[python_idx]

    # Busiest hour
    busiest_hour_row = db.query(
        extract("hour", Appointment.scheduled_start).label("hr"),
        func.count(Appointment.id).label("cnt"),
    ).filter(and_(*filters)).group_by("hr").order_by(func.count(Appointment.id).desc()).first()

    busiest_hour = int(busiest_hour_row.hr) if busiest_hour_row else None

    # Utilization rate
    utilization = calculate_utilization(db, models, org_id, start, end, user_id=user_id)

    completion_rate = round((completed / total) * 100, 1) if total > 0 else 0

    return {
        "period": period,
        "total_appointments": total,
        "completed": completed,
        "cancelled": cancelled,
        "no_shows": no_shows,
        "rescheduled": rescheduled,
        "completion_rate": completion_rate,
        "avg_duration_minutes": avg_duration,
        "utilization_rate": utilization,
        "busiest_day_of_week": busiest_day,
        "busiest_hour": busiest_hour,
        "busiest_hour_label": f"{busiest_hour}:00" if busiest_hour is not None else None,
    }


# =============================================================================
# UTILIZATION
# =============================================================================

def calculate_utilization(
    db: Session,
    models: dict,
    org_id: int,
    start: datetime,
    end: datetime,
    user_id: Optional[int] = None,
) -> float:
    """
    Calculate utilization: total booked minutes / total available minutes * 100.
    Available hours estimated from SchedulerConfig working hours.
    """
    Appointment = _get_appointment_model(models)
    SchedulerConfig = models.get("SchedulerConfig")
    if not Appointment:
        return 0.0

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value]),
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    booked_minutes_row = db.query(
        func.sum(Appointment.duration_minutes).label("total_minutes"),
    ).filter(and_(*filters)).first()

    booked_minutes = float(booked_minutes_row.total_minutes or 0)

    # Estimate available minutes from config working hours
    available_minutes = _estimate_available_minutes(db, models, org_id, start, end, user_id)

    if available_minutes <= 0:
        return 0.0

    return round((booked_minutes / available_minutes) * 100, 1)


def _estimate_available_minutes(
    db: Session,
    models: dict,
    org_id: int,
    start: datetime,
    end: datetime,
    user_id: Optional[int] = None,
) -> float:
    """
    Estimate total available minutes over the date range using SchedulerConfig working_hours.
    Falls back to 8 hours/day on weekdays if no config found.
    """
    SchedulerConfig = models.get("SchedulerConfig")
    working_hours = None

    if SchedulerConfig and user_id:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.organization_id == org_id,
            SchedulerConfig.user_id == user_id,
        ).first()
        if config and config.working_hours:
            working_hours = config.working_hours

    if not working_hours:
        # Default: Mon-Fri, 9am-5pm = 480 min/day
        working_hours = {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
            "friday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "09:00", "end": "17:00", "enabled": False},
            "sunday": {"start": "09:00", "end": "17:00", "enabled": False},
        }

    # Calculate minutes per day-of-week
    day_minutes = {}
    day_name_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day_name in day_name_map:
        cfg = working_hours.get(day_name, {})
        if not cfg.get("enabled", False):
            day_minutes[day_name] = 0
            continue
        try:
            s = datetime.strptime(cfg.get("start", "09:00"), "%H:%M")
            e = datetime.strptime(cfg.get("end", "17:00"), "%H:%M")
            day_minutes[day_name] = max(0, (e - s).total_seconds() / 60)
        except (ValueError, TypeError):
            day_minutes[day_name] = 480  # fallback 8h

    # Sum across the date range
    total = 0.0
    current = start.date() if isinstance(start, datetime) else start
    end_date = end.date() if isinstance(end, datetime) else end

    # If single user, just count their days
    # If org-wide, multiply by number of users with configs
    user_count = 1
    if not user_id and SchedulerConfig:
        user_count = db.query(func.count(func.distinct(SchedulerConfig.user_id))).filter(
            SchedulerConfig.organization_id == org_id,
            SchedulerConfig.is_active == True,
            SchedulerConfig.user_id.isnot(None),
        ).scalar() or 1

    while current <= end_date:
        weekday_idx = current.weekday()  # 0=Monday
        day_name = day_name_map[weekday_idx]
        total += day_minutes.get(day_name, 0)
        current += timedelta(days=1)

    return total * user_count


# =============================================================================
# TRENDS
# =============================================================================

def get_appointment_trends(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
    granularity: str = "daily",
    user_id: Optional[int] = None,
) -> dict:
    """
    Time-series data of appointment counts.
    Returns {labels: [...], datasets: {total: [...], completed: [...], cancelled: [...]}}.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"labels": [], "datasets": {}}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    if granularity == "weekly":
        # Group by ISO week
        date_expr = func.date_trunc("week", Appointment.scheduled_start)
    else:
        # Group by day
        date_expr = cast(Appointment.scheduled_start, SQLDate)

    rows = db.query(
        date_expr.label("bucket"),
        func.count(Appointment.id).label("total"),
        func.count(case(
            (Appointment.status.in_(list(_COMPLETED_STATUSES)), 1),
        )).label("completed"),
        func.count(case(
            (Appointment.status == AppointmentStatus.CANCELLED.value, 1),
        )).label("cancelled"),
        func.count(case(
            (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
        )).label("no_shows"),
    ).filter(and_(*filters)).group_by("bucket").order_by("bucket").all()

    labels = []
    total_data = []
    completed_data = []
    cancelled_data = []
    no_show_data = []

    for row in rows:
        bucket_date = row.bucket
        if isinstance(bucket_date, datetime):
            bucket_date = bucket_date.date()
        label = bucket_date.isoformat() if bucket_date else ""
        labels.append(label)
        total_data.append(row.total or 0)
        completed_data.append(row.completed or 0)
        cancelled_data.append(row.cancelled or 0)
        no_show_data.append(row.no_shows or 0)

    return {
        "period": period,
        "granularity": granularity,
        "labels": labels,
        "datasets": {
            "total": total_data,
            "completed": completed_data,
            "cancelled": cancelled_data,
            "no_shows": no_show_data,
        },
    }


# =============================================================================
# PEAK HOURS
# =============================================================================

def get_peak_hours(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
    user_id: Optional[int] = None,
) -> dict:
    """
    Histogram of appointments by day-of-week and hour.
    Returns a 7x24 grid: {grid: [{day, hour, count}, ...], max_count}.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"grid": [], "max_count": 0}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    rows = db.query(
        extract("dow", Appointment.scheduled_start).label("dow"),
        extract("hour", Appointment.scheduled_start).label("hr"),
        func.count(Appointment.id).label("cnt"),
    ).filter(and_(*filters)).group_by("dow", "hr").all()

    # Build lookup
    counts = {}
    for row in rows:
        dow = int(row.dow)  # PG: 0=Sun
        hr = int(row.hr)
        counts[(dow, hr)] = row.cnt or 0

    max_count = max(counts.values()) if counts else 0

    # Build grid: iterate Mon(1)..Sun(0) mapped to display order Mon..Sun
    # PG dow: 0=Sun, 1=Mon, ..., 6=Sat
    # Display order: Mon, Tue, Wed, Thu, Fri, Sat, Sun
    pg_order = [1, 2, 3, 4, 5, 6, 0]  # Mon=1 through Sun=0
    grid = []
    for display_idx, pg_dow in enumerate(pg_order):
        day_name = DAY_NAMES[display_idx]
        for hr in range(24):
            count = counts.get((pg_dow, hr), 0)
            grid.append({
                "day": day_name,
                "day_index": display_idx,
                "hour": hr,
                "count": count,
            })

    return {
        "period": period,
        "grid": grid,
        "max_count": max_count,
    }


# =============================================================================
# CANCELLATION RATE
# =============================================================================

def get_cancellation_rate(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
    user_id: Optional[int] = None,
) -> dict:
    """
    Cancellation % with breakdown by reason.
    """
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"rate": 0, "reasons": []}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    total = db.query(func.count(Appointment.id)).filter(and_(*filters)).scalar() or 0

    cancel_filters = filters + [Appointment.status == AppointmentStatus.CANCELLED.value]
    cancelled = db.query(func.count(Appointment.id)).filter(and_(*cancel_filters)).scalar() or 0

    # Breakdown by reason
    reason_rows = db.query(
        func.coalesce(Appointment.cancellation_reason, "No reason provided").label("reason"),
        func.count(Appointment.id).label("cnt"),
    ).filter(and_(*cancel_filters)).group_by("reason").order_by(func.count(Appointment.id).desc()).all()

    reasons = [
        {"reason": row.reason[:100], "count": row.cnt}
        for row in reason_rows
    ]

    rate = round((cancelled / total) * 100, 1) if total > 0 else 0

    return {
        "period": period,
        "total_appointments": total,
        "cancelled": cancelled,
        "rate": rate,
        "reasons": reasons,
    }


# =============================================================================
# BY APPOINTMENT TYPE
# =============================================================================

def get_by_type_breakdown(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
    user_id: Optional[int] = None,
) -> dict:
    """Appointment counts grouped by appointment type."""
    Appointment = _get_appointment_model(models)
    AppointmentType = models.get("AppointmentType")
    if not Appointment:
        return {"types": []}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]
    if user_id:
        filters.append(Appointment.assigned_user_id == user_id)

    query = db.query(
        Appointment.appointment_type_id,
        func.count(Appointment.id).label("total"),
        func.count(case(
            (Appointment.status.in_(list(_COMPLETED_STATUSES)), 1),
        )).label("completed"),
        func.count(case(
            (Appointment.status == AppointmentStatus.CANCELLED.value, 1),
        )).label("cancelled"),
        func.count(case(
            (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
        )).label("no_shows"),
        func.avg(Appointment.duration_minutes).label("avg_duration"),
    ).filter(and_(*filters)).group_by(Appointment.appointment_type_id)

    rows = query.all()

    # Fetch type names
    type_names = {}
    if AppointmentType and rows:
        type_ids = [r.appointment_type_id for r in rows if r.appointment_type_id]
        if type_ids:
            types = db.query(AppointmentType).filter(
                AppointmentType.id.in_(type_ids),
            ).all()
            type_names = {t.id: {"name": t.type_name, "color": t.color} for t in types}

    grand_total = sum(r.total for r in rows) or 1

    result = []
    for row in rows:
        type_info = type_names.get(row.appointment_type_id, {})
        result.append({
            "type_id": row.appointment_type_id,
            "type_name": type_info.get("name", "Unassigned"),
            "color": type_info.get("color", "#94a3b8"),
            "total": row.total,
            "completed": row.completed,
            "cancelled": row.cancelled,
            "no_shows": row.no_shows,
            "avg_duration": round(float(row.avg_duration or 0), 1),
            "percentage": round((row.total / grand_total) * 100, 1),
        })

    result.sort(key=lambda x: x["total"], reverse=True)

    return {
        "period": period,
        "types": result,
    }


# =============================================================================
# BY LOAN OFFICER
# =============================================================================

def get_by_lo_breakdown(
    db: Session,
    models: dict,
    org_id: int,
    period: str = "30d",
) -> dict:
    """Appointment counts grouped by loan officer (assigned_user_id)."""
    Appointment = _get_appointment_model(models)
    if not Appointment:
        return {"loan_officers": []}

    start, end = _resolve_date_range(period)

    filters = [
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
    ]

    rows = db.query(
        Appointment.assigned_user_id,
        func.count(Appointment.id).label("total"),
        func.count(case(
            (Appointment.status.in_(list(_COMPLETED_STATUSES)), 1),
        )).label("completed"),
        func.count(case(
            (Appointment.status == AppointmentStatus.CANCELLED.value, 1),
        )).label("cancelled"),
        func.count(case(
            (Appointment.status == AppointmentStatus.NO_SHOW.value, 1),
        )).label("no_shows"),
        func.avg(Appointment.duration_minutes).label("avg_duration"),
    ).filter(and_(*filters)).group_by(Appointment.assigned_user_id).all()

    # Fetch user names
    user_names = {}
    if rows:
        user_ids = [r.assigned_user_id for r in rows if r.assigned_user_id]
        if user_ids:
            try:
                from database.models.core import User
                users = db.query(User).filter(User.id.in_(user_ids)).all()
                user_names = {
                    u.id: f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip() or f"User {u.id}"
                    for u in users
                }
            except ImportError:
                logger.debug("User model not available for LO name lookup")

    grand_total = sum(r.total for r in rows) or 1

    result = []
    for row in rows:
        total = row.total or 0
        completed = row.completed or 0
        completion_rate = round((completed / total) * 100, 1) if total > 0 else 0
        utilization = calculate_utilization(
            db, models, org_id, start, end, user_id=row.assigned_user_id
        )
        result.append({
            "user_id": row.assigned_user_id,
            "name": user_names.get(row.assigned_user_id, f"User {row.assigned_user_id}"),
            "total": total,
            "completed": completed,
            "cancelled": row.cancelled or 0,
            "no_shows": row.no_shows or 0,
            "avg_duration": round(float(row.avg_duration or 0), 1),
            "completion_rate": completion_rate,
            "utilization_rate": utilization,
            "percentage": round((total / grand_total) * 100, 1),
        })

    result.sort(key=lambda x: x["total"], reverse=True)

    return {
        "period": period,
        "loan_officers": result,
    }
