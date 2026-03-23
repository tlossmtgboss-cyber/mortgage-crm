"""
Scheduler conflict detection — appointment conflict and duplicate booking checks.
"""

from fastapi import HTTPException
from sqlalchemy import and_
from datetime import timedelta
from typing import Optional
import logging
import asyncio
import hashlib

from smart_scheduler_models import AppointmentStatus
from routes.scheduler.constants import DEFAULT_APPOINTMENT_DURATION_MINUTES
from routes.scheduler._core import get_models
from routes.scheduler._input_validation import _mask_email

logger = logging.getLogger(__name__)


async def _check_appointment_conflict(db, assigned_user_id: int, start_time, end_time,
                                       org_id: int = None, exclude_appointment_id=None):
    """
    Check for overlapping appointments using advisory lock + SELECT FOR UPDATE.
    Raises HTTPException 409 if a conflict is found or rows are locked by another transaction.
    exclude_appointment_id: skip this appointment (used when rescheduling to avoid self-conflict).
    org_id: ALWAYS applied for tenant isolation.

    The advisory lock serializes concurrent booking attempts for the same
    LO + time slot, closing the race window where SELECT FOR UPDATE finds
    no rows to lock (empty slot) and two transactions both INSERT.
    """
    if org_id is None:
        raise ValueError("org_id is required")
    from sqlalchemy.exc import OperationalError
    from sqlalchemy import text as sa_text

    # Acquire a transaction-scoped advisory lock keyed on (user_id, time_slot).
    # This serializes concurrent booking attempts for the same LO + time window.
    # Uses pg_try_advisory_xact_lock (non-blocking) with retry to avoid
    # indefinite blocking that could exhaust the connection pool under load.
    try:
        # Build a collision-resistant lock key from user_id + date + time slot
        # using SHA-256, taking lower 63 bits to fit Postgres bigint range.
        start_iso = start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time)
        key_str = f"{assigned_user_id}:{start_iso}"
        lock_key = int.from_bytes(hashlib.sha256(key_str.encode()).digest()[:8], 'big') & 0x7FFFFFFFFFFFFFFF
        for _attempt in range(3):
            result = db.execute(sa_text("SELECT pg_try_advisory_xact_lock(:key) AS acquired"), {"key": lock_key})
            if result.scalar():
                break
            await asyncio.sleep(0.05)
        else:
            logger.error("Advisory lock not acquired after 3 attempts for key %s — rejecting booking", lock_key)
            raise HTTPException(
                status_code=409,
                detail="This time slot is temporarily locked by another booking attempt. Please try again in a few seconds."
            )
    except HTTPException:
        raise  # Re-raise our 409 — don't swallow it
    except Exception as e:
        logger.debug("Advisory lock failed (non-blocking): %s", e)

    _models = get_models()
    Appointment = _models['Appointment']
    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_start < end_time,
        Appointment.scheduled_end > start_time,
    ]
    # Always scope by org_id for tenant isolation
    filters.append(Appointment.organization_id == org_id)
    if exclude_appointment_id is not None:
        filters.append(Appointment.id != exclude_appointment_id)

    try:
        conflict = db.query(Appointment).filter(and_(*filters)).with_for_update(nowait=True).first()
    except OperationalError:
        # Row is locked by another transaction -- treat as conflict
        raise HTTPException(
            status_code=409,
            detail="This time slot is being booked by another user. Please select a different time."
        )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="This time slot is no longer available. Please select a different time."
        )


def _check_duplicate_booking(db, attendee_email: str, assigned_user_id: int,
                              start_time, org_id: int = None, window_minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES):
    """
    Check for an existing booking with the same attendee_email + same LO
    within +/-window_minutes of the proposed start_time.
    Raises HTTPException 409 if a duplicate is found.
    org_id: ALWAYS applied for tenant isolation.
    """
    if org_id is None:
        raise ValueError("org_id is required")
    if not attendee_email:
        return  # No email to check against

    _models = get_models()
    Appointment = _models['Appointment']
    window_start = start_time - timedelta(minutes=window_minutes)
    window_end = start_time + timedelta(minutes=window_minutes)

    filters = [
        Appointment.attendee_email == attendee_email,
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_start >= window_start,
        Appointment.scheduled_start <= window_end,
    ]
    # Always scope by org_id for tenant isolation
    filters.append(Appointment.organization_id == org_id)

    duplicate = db.query(Appointment).filter(and_(*filters)).first()
    if duplicate:
        logger.info(f"Duplicate booking detected: existing appointment {duplicate.id} for {_mask_email(attendee_email)}")
        raise HTTPException(
            status_code=409,
            detail="A booking for this email already exists at this time."
        )
