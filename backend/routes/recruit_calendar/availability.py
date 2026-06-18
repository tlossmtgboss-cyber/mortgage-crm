"""
Recruit Calendar — Availability endpoints.

Reuses the scheduler's availability infrastructure (SchedulerConfig,
RecurringAvailability, slot generator). Recruiters/interviewers use the
same availability configuration as for mortgage appointments.

Prefix: /api/v1/recruit-calendar/availability
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database.models import User
from db import get_db
from routes.scheduler._helpers import _generate_available_slots

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_org(user: User) -> int:
    oid = getattr(user, "organization_id", None)
    if not oid:
        raise HTTPException(status_code=400, detail="User has no organization")
    return oid


@router.get("/{user_id}/slots")
async def get_interviewer_slots(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    duration_minutes: int = Query(30, ge=15, le=240),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get available interview slots for a specific interviewer.
    Delegates to the smart calendar slot generator — same availability
    rules apply (working hours, blocked times, existing appointments).
    """
    org_id = _get_org(current_user)

    now = datetime.now(timezone.utc)
    start_dt = datetime.fromisoformat(date_from) if date_from else now
    end_dt = datetime.fromisoformat(date_to) if date_to else (now + timedelta(days=14))

    try:
        slots = await _generate_available_slots(
            db=db,
            user_id=user_id,
            org_id=org_id,
            duration_minutes=duration_minutes,
            start_date=start_dt,
            end_date=end_dt,
            buffer_before=0,
            buffer_after=0,
        )
    except Exception as e:
        logger.warning("Slot generation error for user %s: %s", user_id, e)
        slots = []

    return {
        "user_id": user_id,
        "duration_minutes": duration_minutes,
        "date_from": start_dt.isoformat(),
        "date_to": end_dt.isoformat(),
        "slots": slots,
        "count": len(slots),
    }


@router.post("/check")
async def check_slot_availability(
    user_id: int,
    start_time: str,
    end_time: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if a specific time slot is available for an interviewer."""
    from sqlalchemy import text

    org_id = _get_org(current_user)

    conflict = db.execute(text("""
        SELECT COUNT(*) FROM scheduler_appointments
        WHERE organization_id = :org_id
          AND assigned_user_id = :uid
          AND deleted_at IS NULL
          AND status NOT IN ('cancelled', 'no_show')
          AND scheduled_start < :end_time
          AND scheduled_end > :start_time
    """), {
        "org_id": org_id,
        "uid": user_id,
        "start_time": start_time,
        "end_time": end_time,
    }).scalar()

    return {
        "available": conflict == 0,
        "conflict_count": conflict,
        "start_time": start_time,
        "end_time": end_time,
    }
