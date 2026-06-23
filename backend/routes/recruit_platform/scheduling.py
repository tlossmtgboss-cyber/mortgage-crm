"""
Recruit Platform — Standalone scheduling (availability + appointments).

Public endpoints (no auth): GET /availability, POST /appointments
Protected endpoints (recruiter auth): GET /appointments, PUT /availability/settings,
    PUT /appointments/{id}/status
"""
import logging
import random
import string
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

scheduling_router = APIRouter(prefix="/api/v1/recruit-platform/scheduling")
scheduling_public_router = APIRouter(prefix="/api/v1/recruit-platform/scheduling")

DEFAULT_WEEKLY_SCHEDULE = {
    "monday":    [{"start": "09:00", "end": "17:00"}],
    "tuesday":   [{"start": "09:00", "end": "17:00"}],
    "wednesday": [{"start": "09:00", "end": "17:00"}],
    "thursday":  [{"start": "09:00", "end": "17:00"}],
    "friday":    [{"start": "09:00", "end": "17:00"}],
    "saturday":  [],
    "sunday":    [],
}


def _cu_dep():
    from main import get_current_user
    return Depends(get_current_user)


_CU = _cu_dep()


def _create_tables():
    with SessionLocal() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_availability_settings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE,
                weekly_schedule JSONB NOT NULL DEFAULT '{}',
                slot_duration_minutes INTEGER NOT NULL DEFAULT 30,
                buffer_minutes INTEGER NOT NULL DEFAULT 0,
                timezone VARCHAR(50) NOT NULL DEFAULT 'America/New_York',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_appointments (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                candidate_id INTEGER,
                candidate_name VARCHAR(255) NOT NULL,
                candidate_email VARCHAR(255),
                candidate_phone VARCHAR(50),
                recruiter_id INTEGER,
                appointment_date DATE NOT NULL,
                appointment_time TIME NOT NULL,
                appointment_type VARCHAR(20) NOT NULL DEFAULT 'phone',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                notes TEXT,
                confirmation_code VARCHAR(20),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_recruit_appts_org
                ON recruit_appointments(organization_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_recruit_appts_date
                ON recruit_appointments(appointment_date)
        """))
        db.commit()
        logger.info("recruit scheduling tables ready")


try:
    _create_tables()
except Exception as e:
    logger.warning(f"recruit scheduling table init: {e}")


def _get_or_create_settings(db, org_id: int) -> dict:
    row = db.execute(
        text("SELECT weekly_schedule, slot_duration_minutes, buffer_minutes, timezone FROM recruit_availability_settings WHERE organization_id = :oid"),
        {"oid": org_id},
    ).fetchone()
    if row:
        import json as _json
        schedule = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
        return {"weekly_schedule": schedule, "slot_duration_minutes": row[1], "buffer_minutes": row[2], "timezone": row[3]}
    # Auto-create default
    import json as _json
    db.execute(text("""
        INSERT INTO recruit_availability_settings (organization_id, weekly_schedule, slot_duration_minutes, buffer_minutes, timezone)
        VALUES (:oid, CAST(:sched AS jsonb), 30, 0, 'America/New_York')
        ON CONFLICT (organization_id) DO NOTHING
    """), {"oid": org_id, "sched": _json.dumps(DEFAULT_WEEKLY_SCHEDULE)})
    db.commit()
    return {"weekly_schedule": DEFAULT_WEEKLY_SCHEDULE, "slot_duration_minutes": 30, "buffer_minutes": 0, "timezone": "America/New_York"}


def _generate_slots(weekly_schedule: dict, slot_duration_minutes: int, date_str: str, booked_times: set) -> List[str]:
    day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A").lower()
    windows = weekly_schedule.get(day_name, [])
    slots = []
    for window in windows:
        start = datetime.strptime(window["start"], "%H:%M")
        end = datetime.strptime(window["end"], "%H:%M")
        current = start
        while current + timedelta(minutes=slot_duration_minutes) <= end:
            time_str = current.strftime("%H:%M")
            if time_str not in booked_times:
                slots.append(time_str)
            current += timedelta(minutes=slot_duration_minutes)
    return slots


def _format_slot_display(time_str: str) -> str:
    dt = datetime.strptime(time_str, "%H:%M")
    return dt.strftime("%-I:%M %p")


def _gen_confirmation_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ─── Public: GET availability ───────────────────────────────────────────────

@scheduling_public_router.get("/availability")
def get_availability(org_id: int = Query(...), date: str = Query(...)):
    """Return available time slots for a given org + date. No auth required."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    with SessionLocal() as db:
        settings = _get_or_create_settings(db, org_id)
        booked = set(
            row[0].strftime("%H:%M") for row in db.execute(
                text("SELECT appointment_time FROM recruit_appointments WHERE organization_id = :oid AND appointment_date = :d AND status != 'cancelled'"),
                {"oid": org_id, "d": date},
            ).fetchall()
        )

    slots = _generate_slots(settings["weekly_schedule"], settings["slot_duration_minutes"], date, booked)
    return {
        "slots": [{"value": s, "display": _format_slot_display(s)} for s in slots],
        "timezone": settings["timezone"],
    }


# ─── Public: POST appointments ───────────────────────────────────────────────

class CreateAppointmentBody(BaseModel):
    org_id: int
    candidate_id: Optional[int] = None
    candidate_name: str
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    recruiter_id: Optional[int] = None
    recruiter_name: Optional[str] = None
    date: str
    time: str
    type: str = "phone"
    notes: Optional[str] = None


@scheduling_public_router.post("/appointments")
def create_appointment(body: CreateAppointmentBody):
    """Book an appointment. No auth required (candidate-facing)."""
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
        datetime.strptime(body.time, "%H:%M")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD, time must be HH:MM")

    if body.type not in ("phone", "video"):
        raise HTTPException(400, "type must be phone or video")

    code = _gen_confirmation_code()
    with SessionLocal() as db:
        # Check slot is still available
        existing = db.execute(text("""
            SELECT id FROM recruit_appointments
            WHERE organization_id = :oid AND appointment_date = :d AND appointment_time = :t AND status != 'cancelled'
        """), {"oid": body.org_id, "d": body.date, "t": body.time}).fetchone()
        if existing:
            raise HTTPException(409, "That time slot is no longer available. Please choose another.")

        row = db.execute(text("""
            INSERT INTO recruit_appointments
                (organization_id, candidate_id, candidate_name, candidate_email, candidate_phone,
                 recruiter_id, appointment_date, appointment_time, appointment_type, status, notes, confirmation_code)
            VALUES
                (:org_id, :cid, :cname, :cemail, :cphone,
                 :rid, :d, :t, :atype, 'pending', :notes, :code)
            RETURNING id, confirmation_code
        """), {
            "org_id": body.org_id, "cid": body.candidate_id,
            "cname": body.candidate_name, "cemail": body.candidate_email,
            "cphone": body.candidate_phone, "rid": body.recruiter_id,
            "d": body.date, "t": body.time, "atype": body.type,
            "notes": body.notes, "code": code,
        }).fetchone()
        db.commit()

    return {"id": row[0], "confirmation_code": row[1]}


# ─── Protected: GET appointments list ────────────────────────────────────────

@scheduling_router.get("/appointments")
def list_appointments(
    org_id: Optional[int] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
    current_user=_CU,
):
    oid = org_id or getattr(current_user, "organization_id", None)
    if not oid:
        raise HTTPException(400, "org_id required")

    clauses = ["organization_id = :oid"]
    params = {"oid": oid}
    if date:
        clauses.append("appointment_date = :d")
        params["d"] = date
    if status:
        clauses.append("status = :status")
        params["status"] = status

    with SessionLocal() as db:
        rows = db.execute(text(
            f"SELECT id, candidate_name, candidate_email, candidate_phone, recruiter_id, "
            f"appointment_date, appointment_time, appointment_type, status, notes, confirmation_code, created_at "
            f"FROM recruit_appointments WHERE {' AND '.join(clauses)} ORDER BY appointment_date, appointment_time"
        ), params).fetchall()

    return [
        {
            "id": r[0], "candidate_name": r[1], "candidate_email": r[2],
            "candidate_phone": r[3], "recruiter_id": r[4],
            "date": str(r[5]), "time": str(r[6])[:5],
            "type": r[7], "status": r[8], "notes": r[9],
            "confirmation_code": r[10], "created_at": str(r[11]),
        }
        for r in rows
    ]


# ─── Protected: PUT availability settings ────────────────────────────────────

class AvailabilitySettingsBody(BaseModel):
    org_id: Optional[int] = None
    weekly_schedule: dict
    slot_duration_minutes: int = 30
    buffer_minutes: int = 0
    timezone: str = "America/New_York"


@scheduling_router.put("/availability/settings")
def update_availability_settings(body: AvailabilitySettingsBody, current_user=_CU):
    import json as _json
    oid = body.org_id or getattr(current_user, "organization_id", None)
    if not oid:
        raise HTTPException(400, "org_id required")

    with SessionLocal() as db:
        db.execute(text("""
            INSERT INTO recruit_availability_settings
                (organization_id, weekly_schedule, slot_duration_minutes, buffer_minutes, timezone)
            VALUES (:oid, CAST(:sched AS jsonb), :dur, :buf, :tz)
            ON CONFLICT (organization_id) DO UPDATE SET
                weekly_schedule = CAST(EXCLUDED.weekly_schedule AS jsonb),
                slot_duration_minutes = EXCLUDED.slot_duration_minutes,
                buffer_minutes = EXCLUDED.buffer_minutes,
                timezone = EXCLUDED.timezone,
                updated_at = NOW()
        """), {
            "oid": oid, "sched": _json.dumps(body.weekly_schedule),
            "dur": body.slot_duration_minutes, "buf": body.buffer_minutes, "tz": body.timezone,
        })
        db.commit()

    return {"ok": True}


# ─── Protected: PUT appointment status ───────────────────────────────────────

class AppointmentStatusBody(BaseModel):
    status: str
    reschedule_date: Optional[str] = None
    reschedule_time: Optional[str] = None


@scheduling_router.put("/appointments/{appt_id}/status")
def update_appointment_status(appt_id: int, body: AppointmentStatusBody, current_user=_CU):
    if body.status not in ("confirmed", "cancelled", "rescheduled", "completed", "no_show"):
        raise HTTPException(400, "invalid status")

    with SessionLocal() as db:
        appt = db.execute(text("SELECT organization_id FROM recruit_appointments WHERE id = :id"), {"id": appt_id}).fetchone()
        if not appt:
            raise HTTPException(404, "Appointment not found")
        if appt[0] != getattr(current_user, "organization_id", None):
            raise HTTPException(403, "Forbidden")

        updates = {"status": body.status, "id": appt_id}
        extra = ""
        if body.status == "rescheduled" and body.reschedule_date and body.reschedule_time:
            extra = ", appointment_date = :new_date, appointment_time = :new_time"
            updates["new_date"] = body.reschedule_date
            updates["new_time"] = body.reschedule_time

        db.execute(text(f"UPDATE recruit_appointments SET status = :status{extra}, updated_at = NOW() WHERE id = :id"), updates)
        db.commit()

    return {"ok": True}
