"""
Capacity Dashboard Routes - Team scheduling load and availability analytics.

Endpoints:
- GET /api/v1/scheduler/capacity/overview   — team capacity data per LO
- GET /api/v1/scheduler/capacity/heatmap    — hour-by-day booking density
- GET /api/v1/scheduler/capacity/trends     — weekly booking trends over past N weeks
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case, and_
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
import logging

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler/capacity", tags=["Capacity Dashboard"])

# ---------------------------------------------------------------------------
# Dependency injection (same pattern as team_calendar_routes.py)
# ---------------------------------------------------------------------------

_get_current_user_func = None
_models = None


def set_dependencies(get_current_user_func, models_dict):
    """Wire up auth and model references from main.py."""
    global _get_current_user_func, _models
    _get_current_user_func = get_current_user_func
    _models = models_dict


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Dependencies not set for capacity_dashboard_routes")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKING_START_HOUR = 7
WORKING_END_HOUR = 19
TOTAL_WORKING_MINUTES = (WORKING_END_HOUR - WORKING_START_HOUR) * 60  # 720
SLOT_DURATION_MINUTES = 30
SLOTS_PER_DAY = TOTAL_WORKING_MINUTES // SLOT_DURATION_MINUTES  # 24

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org_id(user) -> int:
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _require_manager_or_admin(user):
    role = (getattr(user, "permission_role", "") or getattr(user, "role", "") or "").lower()
    if role not in ("admin", "site_admin", "platform_admin", "management", "leadership"):
        raise HTTPException(
            status_code=403,
            detail="Capacity dashboard requires manager or admin role",
        )


def _get_org_users(db: Session, org_id: int, lo_ids: Optional[List[int]] = None):
    try:
        from database.models import User
    except ImportError:
        from database.models.user import User

    query = db.query(User).filter(User.organization_id == org_id, User.is_active == True)
    if lo_ids:
        query = query.filter(User.id.in_(lo_ids))
    return query.order_by(User.first_name, User.last_name).all()


def _get_appointment_model():
    if _models and _models.get("Appointment"):
        return _models["Appointment"]
    from smart_scheduler_models import _define_models
    models = _define_models()
    return models.get("Appointment")


def _parse_lo_ids(lo_ids_str: Optional[str]) -> Optional[List[int]]:
    if not lo_ids_str:
        return None
    try:
        return [int(x.strip()) for x in lo_ids_str.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="lo_ids must be comma-separated integers")


# ---------------------------------------------------------------------------
# GET /api/v1/scheduler/capacity/overview
# ---------------------------------------------------------------------------

@router.get("/overview")
async def get_capacity_overview(
    request: Request,
    start_date: date = Query(..., description="Start of date range (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End of date range (YYYY-MM-DD)"),
    lo_ids: Optional[str] = Query(None, description="Comma-separated LO user IDs"),
    db: Session = Depends(get_db),
):
    """
    Team capacity overview: per-LO booked vs available minutes,
    utilization percentage, appointment counts, and next available slot.
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    parsed_lo_ids = _parse_lo_ids(lo_ids)
    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    users = _get_org_users(db, org_id, parsed_lo_ids)
    user_ids = [u.id for u in users]

    if not user_ids:
        return {"team": [], "summary": {"total_booked_minutes": 0, "avg_utilization": 0}}

    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time(23, 59, 59)).replace(tzinfo=timezone.utc)

    # Count working days in range (Mon-Fri only)
    working_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            working_days += 1
        current += timedelta(days=1)
    if working_days == 0:
        working_days = 1  # avoid division by zero

    # Fetch all non-cancelled appointments in range
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            Appointment.assigned_user_id.in_(user_ids),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt,
            Appointment.status.notin_(["cancelled", "CANCELLED"]),
        )
        .all()
    )

    # Build per-LO aggregates
    lo_data = {}
    for u in users:
        lo_data[u.id] = {
            "booked_minutes": 0,
            "appointment_count": 0,
            "no_show_count": 0,
            "completed_count": 0,
            "latest_end": None,
        }

    for appt in appointments:
        uid = appt.assigned_user_id
        if uid not in lo_data:
            continue
        duration = appt.duration_minutes or 30
        lo_data[uid]["booked_minutes"] += duration
        lo_data[uid]["appointment_count"] += 1

        status_val = str(appt.status.value).lower() if appt.status else ""
        if status_val == "no_show":
            lo_data[uid]["no_show_count"] += 1
        elif status_val == "completed":
            lo_data[uid]["completed_count"] += 1

        appt_end = appt.scheduled_end
        if appt_end:
            if lo_data[uid]["latest_end"] is None or appt_end > lo_data[uid]["latest_end"]:
                lo_data[uid]["latest_end"] = appt_end

    # Find next available slot for each LO (look ahead from now)
    now = datetime.now(timezone.utc)
    next_available = {}

    for u in users:
        uid = u.id
        # Get future appointments for this LO
        future_appts = sorted(
            [
                a for a in appointments
                if a.assigned_user_id == uid
                and a.scheduled_start
                and a.scheduled_start > now
            ],
            key=lambda a: a.scheduled_start,
        )

        # Walk through working hours to find first gap
        check_time = max(now, start_dt)
        # Snap to next half-hour
        if check_time.minute < 30:
            check_time = check_time.replace(minute=30, second=0, microsecond=0)
        else:
            check_time = (check_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        found_slot = None
        for _ in range(SLOTS_PER_DAY * 14):  # Check up to 14 days of slots
            h = check_time.hour
            wd = check_time.weekday()
            if wd < 5 and WORKING_START_HOUR <= h < WORKING_END_HOUR:
                slot_end = check_time + timedelta(minutes=SLOT_DURATION_MINUTES)
                conflict = False
                for fa in future_appts:
                    fa_start = fa.scheduled_start.replace(tzinfo=timezone.utc) if fa.scheduled_start.tzinfo is None else fa.scheduled_start
                    fa_end = fa.scheduled_end.replace(tzinfo=timezone.utc) if fa.scheduled_end and fa.scheduled_end.tzinfo is None else fa.scheduled_end
                    if fa_end is None:
                        fa_end = fa_start + timedelta(minutes=fa.duration_minutes or 30)
                    if check_time < fa_end and slot_end > fa_start:
                        conflict = True
                        break
                if not conflict:
                    found_slot = check_time.isoformat()
                    break
            check_time += timedelta(minutes=SLOT_DURATION_MINUTES)

        next_available[uid] = found_slot

    # Build response
    total_capacity_minutes = working_days * TOTAL_WORKING_MINUTES
    team_list = []
    total_booked = 0
    total_utilization_sum = 0

    for u in users:
        uid = u.id
        d = lo_data[uid]
        utilization = round((d["booked_minutes"] / total_capacity_minutes) * 100, 1) if total_capacity_minutes > 0 else 0
        utilization = min(utilization, 100.0)

        full_name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip() or f"User {uid}"
        avg_per_day = round(d["appointment_count"] / working_days, 1)

        no_show_rate = 0
        if d["appointment_count"] > 0:
            no_show_rate = round((d["no_show_count"] / d["appointment_count"]) * 100, 1)

        team_list.append({
            "lo_id": uid,
            "lo_name": full_name,
            "email": getattr(u, "email", ""),
            "booked_minutes": d["booked_minutes"],
            "available_minutes": max(0, total_capacity_minutes - d["booked_minutes"]),
            "total_capacity_minutes": total_capacity_minutes,
            "utilization_pct": utilization,
            "appointment_count": d["appointment_count"],
            "avg_bookings_per_day": avg_per_day,
            "no_show_count": d["no_show_count"],
            "no_show_rate": no_show_rate,
            "completed_count": d["completed_count"],
            "next_available_slot": next_available.get(uid),
        })

        total_booked += d["booked_minutes"]
        total_utilization_sum += utilization

    avg_utilization = round(total_utilization_sum / len(team_list), 1) if team_list else 0

    return {
        "team": team_list,
        "summary": {
            "total_booked_minutes": total_booked,
            "total_capacity_minutes": total_capacity_minutes * len(team_list),
            "avg_utilization": avg_utilization,
            "total_appointments": sum(d["appointment_count"] for d in lo_data.values()),
            "total_no_shows": sum(d["no_show_count"] for d in lo_data.values()),
            "working_days": working_days,
            "team_size": len(team_list),
        },
        "date_range": {"start": str(start_date), "end": str(end_date)},
    }


# ---------------------------------------------------------------------------
# GET /api/v1/scheduler/capacity/heatmap
# ---------------------------------------------------------------------------

@router.get("/heatmap")
async def get_capacity_heatmap(
    request: Request,
    start_date: date = Query(..., description="Start of date range (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End of date range (YYYY-MM-DD)"),
    lo_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Booking density heatmap: number of appointments per hour per day-of-week.
    Returns a grid suitable for rendering as hour (y-axis) x day (x-axis).
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    parsed_lo_ids = _parse_lo_ids(lo_ids)
    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    users = _get_org_users(db, org_id, parsed_lo_ids)
    user_ids = [u.id for u in users]

    if not user_ids:
        return {"heatmap": [], "hours": list(range(WORKING_START_HOUR, WORKING_END_HOUR)), "days": DAY_NAMES[:5]}

    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time(23, 59, 59)).replace(tzinfo=timezone.utc)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            Appointment.assigned_user_id.in_(user_ids),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt,
            Appointment.status.notin_(["cancelled", "CANCELLED"]),
        )
        .all()
    )

    # Build heatmap grid: [hour][day_of_week] = count
    # day_of_week: 0=Monday .. 4=Friday
    grid = {}
    for h in range(WORKING_START_HOUR, WORKING_END_HOUR):
        grid[h] = {d: 0 for d in range(5)}  # Mon-Fri

    max_count = 0
    for appt in appointments:
        if appt.scheduled_start is None:
            continue
        h = appt.scheduled_start.hour
        dow = appt.scheduled_start.weekday()  # 0=Mon
        if WORKING_START_HOUR <= h < WORKING_END_HOUR and dow < 5:
            grid[h][dow] += 1
            if grid[h][dow] > max_count:
                max_count = grid[h][dow]

    # Format as array of rows
    heatmap_rows = []
    for h in range(WORKING_START_HOUR, WORKING_END_HOUR):
        cells = []
        for d in range(5):
            count = grid[h][d]
            intensity = round((count / max_count) * 100, 0) if max_count > 0 else 0
            cells.append({
                "day": d,
                "day_name": DAY_NAMES[d],
                "count": count,
                "intensity": intensity,
            })
        heatmap_rows.append({
            "hour": h,
            "hour_label": f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}",
            "cells": cells,
        })

    return {
        "heatmap": heatmap_rows,
        "hours": list(range(WORKING_START_HOUR, WORKING_END_HOUR)),
        "days": DAY_NAMES[:5],
        "max_count": max_count,
        "total_appointments": len(appointments),
        "date_range": {"start": str(start_date), "end": str(end_date)},
    }


# ---------------------------------------------------------------------------
# GET /api/v1/scheduler/capacity/trends
# ---------------------------------------------------------------------------

@router.get("/trends")
async def get_capacity_trends(
    request: Request,
    weeks: int = Query(4, ge=1, le=12, description="Number of weeks to look back"),
    lo_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Weekly booking trends: appointments per week, show rate, no-show rate,
    avg bookings/day, and utilization over the past N weeks.
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    parsed_lo_ids = _parse_lo_ids(lo_ids)
    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    users = _get_org_users(db, org_id, parsed_lo_ids)
    user_ids = [u.id for u in users]

    if not user_ids:
        return {"trends": [], "weeks_analyzed": weeks}

    # Calculate date range: from start of (N weeks ago) week to end of current week
    today = date.today()
    # Start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    range_start = current_week_start - timedelta(weeks=weeks - 1)
    range_end = current_week_start + timedelta(days=6)

    start_dt = datetime.combine(range_start, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(range_end, time(23, 59, 59)).replace(tzinfo=timezone.utc)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            Appointment.assigned_user_id.in_(user_ids),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt,
            Appointment.status.notin_(["cancelled", "CANCELLED"]),
        )
        .all()
    )

    # Bucket appointments by week
    week_data = {}
    for i in range(weeks):
        week_start = range_start + timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        week_key = week_start.isoformat()
        week_data[week_key] = {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "week_label": f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}",
            "total": 0,
            "completed": 0,
            "no_show": 0,
            "booked_minutes": 0,
        }

    for appt in appointments:
        if appt.scheduled_start is None:
            continue
        appt_date = appt.scheduled_start.date() if isinstance(appt.scheduled_start, datetime) else appt.scheduled_start
        # Find which week bucket
        for i in range(weeks):
            week_start = range_start + timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            if week_start <= appt_date <= week_end:
                wk = week_start.isoformat()
                week_data[wk]["total"] += 1
                week_data[wk]["booked_minutes"] += appt.duration_minutes or 30

                status_val = str(appt.status.value).lower() if appt.status else ""
                if status_val == "completed":
                    week_data[wk]["completed"] += 1
                elif status_val == "no_show":
                    week_data[wk]["no_show"] += 1
                break

    # Calculate metrics per week
    team_size = len(users) or 1
    trends = []
    for i in range(weeks):
        week_start = range_start + timedelta(weeks=i)
        wk = week_start.isoformat()
        wd = week_data[wk]

        # Count working days in this week (Mon-Fri, capped at actual range)
        working_days = sum(
            1 for d in range(7)
            if (week_start + timedelta(days=d)).weekday() < 5
        )
        if working_days == 0:
            working_days = 1

        total_capacity = working_days * TOTAL_WORKING_MINUTES * team_size
        utilization = round((wd["booked_minutes"] / total_capacity) * 100, 1) if total_capacity > 0 else 0
        show_rate = round((wd["completed"] / wd["total"]) * 100, 1) if wd["total"] > 0 else 0
        no_show_rate = round((wd["no_show"] / wd["total"]) * 100, 1) if wd["total"] > 0 else 0
        avg_per_day = round(wd["total"] / working_days, 1)

        trends.append({
            "week_start": wd["week_start"],
            "week_end": wd["week_end"],
            "week_label": wd["week_label"],
            "total_appointments": wd["total"],
            "completed": wd["completed"],
            "no_shows": wd["no_show"],
            "booked_minutes": wd["booked_minutes"],
            "utilization_pct": min(utilization, 100.0),
            "show_rate": show_rate,
            "no_show_rate": no_show_rate,
            "avg_bookings_per_day": avg_per_day,
        })

    return {
        "trends": trends,
        "weeks_analyzed": weeks,
        "team_size": team_size,
    }


# ---------------------------------------------------------------------------
# Route registration function (called from main.py / inline_legacy_routes.py)
# ---------------------------------------------------------------------------

def register_capacity_dashboard_routes(app, get_current_user, models_dict=None):
    """Register capacity dashboard routes on the FastAPI app."""
    set_dependencies(get_current_user, models_dict or {})
    app.include_router(router)
    logger.info("Capacity Dashboard routes registered at /api/v1/scheduler/capacity")
