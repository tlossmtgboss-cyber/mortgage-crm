"""
Team Calendar Routes - Multi-LO schedule management for managers/admins.

Endpoints:
- GET  /api/v1/calendar/team           — all LOs' appointments for date range
- GET  /api/v1/calendar/team/capacity   — capacity summary per LO per day
- POST /api/v1/calendar/team/reassign   — move appointment to different LO
- GET  /api/v1/calendar/team/availability-matrix — available slots across all LOs
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
from pydantic import BaseModel
import logging

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendar/team", tags=["Team Calendar"])

# ---------------------------------------------------------------------------
# Dependency injection (same pattern as scheduler_appointment_routes.py)
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
        raise RuntimeError("Dependencies not set for team_calendar_routes")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org_id(user) -> int:
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _require_manager_or_admin(user):
    """Raise 403 unless user is admin, site_admin, platform_admin, management, or leadership."""
    role = (getattr(user, "permission_role", "") or getattr(user, "role", "") or "").lower()
    if role not in ("admin", "site_admin", "platform_admin", "management", "leadership"):
        raise HTTPException(
            status_code=403,
            detail="Team calendar requires manager or admin role",
        )


def _is_platform_admin(user) -> bool:
    role = (getattr(user, "permission_role", "") or getattr(user, "role", "") or "").lower()
    return role == "platform_admin"


def _get_org_users(db: Session, org_id: int, lo_ids: Optional[List[int]] = None):
    """Return user rows for the org (optionally filtered by id list)."""
    try:
        from database.models import User
    except ImportError:
        from database.models.user import User

    query = db.query(User).filter(User.organization_id == org_id, User.is_active == True)
    if lo_ids:
        query = query.filter(User.id.in_(lo_ids))
    return query.order_by(User.first_name, User.last_name).all()


def _get_appointment_model():
    """Return Appointment model class, preferring injected models dict."""
    if _models and _models.get("Appointment"):
        return _models["Appointment"]
    from smart_scheduler_models import _define_models
    models = _define_models()
    return models.get("Appointment")


WORKING_START_HOUR = 7
WORKING_END_HOUR = 19
SLOT_DURATION_MINUTES = 30
SLOTS_PER_DAY = (WORKING_END_HOUR - WORKING_START_HOUR) * (60 // SLOT_DURATION_MINUTES)  # 24


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ReassignRequest(BaseModel):
    appointment_id: int
    new_lo_id: int
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /api/v1/calendar/team — team appointments
# ---------------------------------------------------------------------------

@router.get("")
async def get_team_calendar(
    request: Request,
    start_date: date = Query(..., description="Start of date range (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End of date range (YYYY-MM-DD)"),
    lo_ids: Optional[str] = Query(None, description="Comma-separated LO user IDs to filter"),
    db: Session = Depends(get_db),
):
    """
    Get all LOs' appointments for a date range, grouped by LO.
    Requires manager/admin role (platform_admin sees all orgs).
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    # Parse optional LO filter
    parsed_lo_ids = None
    if lo_ids:
        try:
            parsed_lo_ids = [int(x.strip()) for x in lo_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="lo_ids must be comma-separated integers")

    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    # Date range to datetime
    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time(23, 59, 59)).replace(tzinfo=timezone.utc)

    # Get org users
    users = _get_org_users(db, org_id, parsed_lo_ids)
    user_ids = [u.id for u in users]

    if not user_ids:
        return {"team": {}, "date_range": {"start": str(start_date), "end": str(end_date)}}

    # Fetch appointments
    query = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.assigned_user_id.in_(user_ids),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt,
        Appointment.status.notin_(["cancelled", "CANCELLED"]),
    )
    appointments = query.order_by(Appointment.scheduled_start).all()

    # Group by LO
    team = {}
    for u in users:
        full_name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip() or f"User {u.id}"
        team[str(u.id)] = {
            "lo_id": u.id,
            "lo_name": full_name,
            "email": getattr(u, "email", ""),
            "appointments": [],
        }

    for appt in appointments:
        lo_key = str(appt.assigned_user_id)
        if lo_key not in team:
            continue

        team[lo_key]["appointments"].append({
            "id": appt.id,
            "title": appt.title,
            "description": getattr(appt, "description", None),
            "meeting_type": str(appt.meeting_type.value) if appt.meeting_type else None,
            "meeting_mode": str(appt.meeting_mode.value) if appt.meeting_mode else None,
            "scheduled_start": appt.scheduled_start.isoformat() if appt.scheduled_start else None,
            "scheduled_end": appt.scheduled_end.isoformat() if appt.scheduled_end else None,
            "duration_minutes": appt.duration_minutes,
            "status": str(appt.status.value) if appt.status else None,
            "attendee_name": getattr(appt, "attendee_name", None),
            "attendee_email": getattr(appt, "attendee_email", None),
            "attendee_phone": getattr(appt, "attendee_phone", None),
            "location": getattr(appt, "location", None),
            "video_link": getattr(appt, "video_link", None),
            "phone_number": getattr(appt, "phone_number", None),
            "lead_id": getattr(appt, "lead_id", None),
            "loan_id": getattr(appt, "loan_id", None),
        })

    return {
        "team": team,
        "date_range": {"start": str(start_date), "end": str(end_date)},
        "total_appointments": len(appointments),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/calendar/team/capacity — capacity per LO per day
# ---------------------------------------------------------------------------

@router.get("/capacity")
async def get_team_capacity(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    lo_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Capacity summary: booked slots vs available capacity per LO per day.
    Default capacity = SLOTS_PER_DAY (24 half-hour slots from 7am-7pm).
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    parsed_lo_ids = None
    if lo_ids:
        try:
            parsed_lo_ids = [int(x.strip()) for x in lo_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="lo_ids must be comma-separated integers")

    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    users = _get_org_users(db, org_id, parsed_lo_ids)
    user_ids = [u.id for u in users]

    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time(23, 59, 59)).replace(tzinfo=timezone.utc)

    # Count appointments per LO per day
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

    # Build capacity map: { lo_id: { "YYYY-MM-DD": { booked_minutes, booked_count } } }
    capacity_raw = {}
    for appt in appointments:
        lo_id = str(appt.assigned_user_id)
        day_key = appt.scheduled_start.strftime("%Y-%m-%d")
        if lo_id not in capacity_raw:
            capacity_raw[lo_id] = {}
        if day_key not in capacity_raw[lo_id]:
            capacity_raw[lo_id][day_key] = {"booked_minutes": 0, "booked_count": 0}
        capacity_raw[lo_id][day_key]["booked_minutes"] += appt.duration_minutes or 30
        capacity_raw[lo_id][day_key]["booked_count"] += 1

    total_available_minutes = (WORKING_END_HOUR - WORKING_START_HOUR) * 60  # 720 min

    result = {}
    for u in users:
        lo_id = str(u.id)
        full_name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
        result[lo_id] = {"lo_name": full_name, "days": {}}
        lo_days = capacity_raw.get(lo_id, {})

        current = start_date
        while current <= end_date:
            day_key = current.strftime("%Y-%m-%d")
            day_data = lo_days.get(day_key, {"booked_minutes": 0, "booked_count": 0})
            booked_min = day_data["booked_minutes"]
            pct = round((booked_min / total_available_minutes) * 100, 1) if total_available_minutes > 0 else 0
            result[lo_id]["days"][day_key] = {
                "booked": day_data["booked_count"],
                "capacity": SLOTS_PER_DAY,
                "booked_minutes": booked_min,
                "available_minutes": max(0, total_available_minutes - booked_min),
                "pct": min(pct, 100),
            }
            current += timedelta(days=1)

    return {"capacity": result}


# ---------------------------------------------------------------------------
# POST /api/v1/calendar/team/reassign — move appointment to different LO
# ---------------------------------------------------------------------------

@router.post("/reassign")
async def reassign_appointment(
    request: Request,
    body: ReassignRequest,
    db: Session = Depends(get_db),
):
    """
    Move an appointment to a different LO.
    - Validates the new LO exists in same org
    - Checks for time conflicts on the new LO's schedule
    - Updates assigned_user_id
    - Returns updated appointment
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    # Load the appointment
    appointment = (
        db.query(Appointment)
        .filter(Appointment.id == body.appointment_id, Appointment.organization_id == org_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.assigned_user_id == body.new_lo_id:
        raise HTTPException(status_code=400, detail="Appointment is already assigned to this LO")

    # Verify new LO exists in org
    new_lo_users = _get_org_users(db, org_id, [body.new_lo_id])
    if not new_lo_users:
        raise HTTPException(status_code=404, detail="Target LO not found in your organization")
    new_lo = new_lo_users[0]

    # Check for time conflicts on the new LO
    conflict = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            Appointment.assigned_user_id == body.new_lo_id,
            Appointment.id != body.appointment_id,
            Appointment.status.notin_(["cancelled", "CANCELLED"]),
            Appointment.scheduled_start < appointment.scheduled_end,
            Appointment.scheduled_end > appointment.scheduled_start,
        )
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Time conflict: {new_lo.first_name} has '{conflict.title}' from "
                   f"{conflict.scheduled_start.strftime('%I:%M %p')} to {conflict.scheduled_end.strftime('%I:%M %p')}",
        )

    old_lo_id = appointment.assigned_user_id
    old_lo_users = _get_org_users(db, org_id, [old_lo_id])
    old_lo_name = ""
    if old_lo_users:
        old_lo_name = f"{old_lo_users[0].first_name or ''} {old_lo_users[0].last_name or ''}".strip()

    # Reassign
    appointment.assigned_user_id = body.new_lo_id
    appointment.updated_at = datetime.now(timezone.utc)
    appointment.internal_notes = (
        (appointment.internal_notes or "")
        + f"\n[Reassigned from {old_lo_name} (ID {old_lo_id}) to "
        + f"{new_lo.first_name} {new_lo.last_name} (ID {body.new_lo_id}) "
        + f"by {getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')} "
        + f"on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        + (f" | Reason: {body.reason}" if body.reason else "")
        + "]"
    )

    db.commit()
    db.refresh(appointment)

    # Send notification emails (best-effort, non-blocking)
    try:
        from scheduler_email_service import send_team_member_notification_email
        new_lo_name = f"{new_lo.first_name or ''} {new_lo.last_name or ''}".strip()

        # Notify new LO
        send_team_member_notification_email(
            team_member_email=getattr(new_lo, "email", ""),
            team_member_name=new_lo_name,
            appointment_title=appointment.title,
            appointment_time=appointment.scheduled_start.strftime("%B %d, %Y at %I:%M %p") if appointment.scheduled_start else "",
            attendee_name=getattr(appointment, "attendee_name", "") or "",
        )
    except Exception as e:
        logger.warning(f"Failed to send reassignment notification: {e}")

    return {
        "status": "reassigned",
        "appointment_id": appointment.id,
        "old_lo_id": old_lo_id,
        "old_lo_name": old_lo_name,
        "new_lo_id": body.new_lo_id,
        "new_lo_name": f"{new_lo.first_name or ''} {new_lo.last_name or ''}".strip(),
        "scheduled_start": appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
        "scheduled_end": appointment.scheduled_end.isoformat() if appointment.scheduled_end else None,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/calendar/team/availability-matrix — find open slots across LOs
# ---------------------------------------------------------------------------

@router.get("/availability-matrix")
async def get_availability_matrix(
    request: Request,
    target_date: date = Query(..., description="Date to check availability (YYYY-MM-DD)"),
    duration_minutes: int = Query(30, description="Desired appointment duration"),
    lo_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Shows available time slots across all LOs for a given date.
    Useful for "find any available LO" scenarios.
    Returns a matrix of half-hour slots per LO.
    """
    user = await get_current_user(request, db)
    _require_manager_or_admin(user)
    org_id = _get_org_id(user)

    parsed_lo_ids = None
    if lo_ids:
        try:
            parsed_lo_ids = [int(x.strip()) for x in lo_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="lo_ids must be comma-separated integers")

    Appointment = _get_appointment_model()
    if Appointment is None:
        raise HTTPException(status_code=500, detail="Appointment model not available")

    users = _get_org_users(db, org_id, parsed_lo_ids)

    start_dt = datetime.combine(target_date, time(WORKING_START_HOUR, 0)).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, time(WORKING_END_HOUR, 0)).replace(tzinfo=timezone.utc)

    user_ids = [u.id for u in users]
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            Appointment.assigned_user_id.in_(user_ids),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start < end_dt,
            Appointment.status.notin_(["cancelled", "CANCELLED"]),
        )
        .all()
    )

    # Build busy map per LO
    busy_map = {}  # { lo_id: [(start, end), ...] }
    for appt in appointments:
        lo_id = appt.assigned_user_id
        if lo_id not in busy_map:
            busy_map[lo_id] = []
        busy_map[lo_id].append((appt.scheduled_start, appt.scheduled_end))

    # Generate slot grid
    slots_needed = max(1, duration_minutes // SLOT_DURATION_MINUTES)

    matrix = {}
    for u in users:
        full_name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
        lo_busy = busy_map.get(u.id, [])
        lo_slots = []

        current_slot = start_dt
        while current_slot + timedelta(minutes=duration_minutes) <= end_dt:
            slot_end = current_slot + timedelta(minutes=duration_minutes)

            # Check if this slot conflicts with any busy block
            is_available = True
            for busy_start, busy_end in lo_busy:
                # Make both timezone-aware or naive for comparison
                bs = busy_start.replace(tzinfo=timezone.utc) if busy_start.tzinfo is None else busy_start
                be = busy_end.replace(tzinfo=timezone.utc) if busy_end.tzinfo is None else busy_end
                if current_slot < be and slot_end > bs:
                    is_available = False
                    break

            lo_slots.append({
                "start": current_slot.strftime("%H:%M"),
                "end": slot_end.strftime("%H:%M"),
                "start_iso": current_slot.isoformat(),
                "end_iso": slot_end.isoformat(),
                "available": is_available,
            })
            current_slot += timedelta(minutes=SLOT_DURATION_MINUTES)

        matrix[str(u.id)] = {
            "lo_name": full_name,
            "lo_id": u.id,
            "email": getattr(u, "email", ""),
            "slots": lo_slots,
        }

    return {
        "date": str(target_date),
        "duration_minutes": duration_minutes,
        "working_hours": {"start": WORKING_START_HOUR, "end": WORKING_END_HOUR},
        "matrix": matrix,
    }


# ---------------------------------------------------------------------------
# Route registration function (called from main.py)
# ---------------------------------------------------------------------------

def register_team_calendar_routes(app, get_current_user, models_dict=None):
    """Register team calendar routes on the FastAPI app."""
    set_dependencies(get_current_user, models_dict or {})
    app.include_router(router)
    logger.info("Team Calendar routes registered at /api/v1/calendar/team")
