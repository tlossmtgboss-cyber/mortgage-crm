"""
Slot hold management for the appointment service.

Handles soft holds on time slots during AI conversations. Holds are
TTL-based and DB-backed (via the SlotHold SQLAlchemy model) to work
correctly in multi-worker deployments.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from services.appointment._models import (
    DEFAULT_DURATION_MINUTES,
    DEFAULT_HOLD_TTL_SECONDS,
    get_model,
)

logger = logging.getLogger(__name__)


def hold_slot(
    db: Session,
    organization_id: int,
    lo_id: int,
    start_time: datetime,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS,
    source: str = "ai_conversation",
) -> Dict[str, Any]:
    """
    Create a soft hold on a time slot during an AI conversation.

    Holds are TTL-based and automatically expire. They prevent other
    callers from seeing the slot as available.

    Args:
        db: Database session.
        organization_id: Tenant ID.
        lo_id: Loan officer user_id.
        start_time: Proposed appointment start.
        duration_minutes: Slot duration.
        ttl_seconds: Time-to-live in seconds (default 5 minutes).
        source: Description of the hold requester.

    Returns:
        Dict with hold_id and expiry info.
    """
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if start_time.tzinfo:
            start_time = start_time.replace(tzinfo=None)

    end_time = start_time + timedelta(minutes=duration_minutes)
    now = datetime.now(timezone.utc)

    hold_id = str(uuid_lib.uuid4())
    expires_at = now + timedelta(seconds=ttl_seconds)

    # Persist hold to the database (multi-worker safe)
    DbSlotHold = get_model("SlotHold")
    if DbSlotHold:
        db_hold = DbSlotHold(
            organization_id=organization_id,
            lo_id=lo_id,
            start_time=start_time,
            end_time=end_time,
            expires_at=expires_at,
            held_by=source,
            status="active",
        )
        db.add(db_hold)
        db.flush()
        hold_id = db_hold.id  # Use the DB-generated integer PK
    else:
        logger.error("SlotHold model not available -- hold not persisted")

    logger.info(
        f"Slot hold created: {hold_id} for LO {lo_id} "
        f"at {start_time.isoformat()}, TTL={ttl_seconds}s"
    )

    return {
        "hold_id": hold_id,
        "lo_id": lo_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
    }


def release_hold(
    db: Session,
    organization_id: int,
    hold_id: str,
) -> bool:
    """
    Release a soft hold. Returns True if the hold existed and was released.
    """
    DbSlotHold = get_model("SlotHold")
    if not DbSlotHold:
        return False

    hold = db.query(DbSlotHold).filter(
        DbSlotHold.id == hold_id,
        DbSlotHold.organization_id == organization_id,
        DbSlotHold.status == "active",
    ).first()

    if hold:
        hold.status = "released"
        db.flush()
        logger.info(f"Slot hold released: {hold_id}")
        return True
    return False


def slot_conflicts_with_holds(
    db: Session,
    organization_id: int,
    lo_id: int,
    slot_start: datetime,
    slot_end: datetime,
) -> bool:
    """Check if a proposed slot conflicts with any active soft hold (DB-backed)."""
    DbSlotHold = get_model("SlotHold")
    if not DbSlotHold:
        return False

    now = datetime.now(timezone.utc)
    conflict = db.query(DbSlotHold).filter(
        DbSlotHold.lo_id == lo_id,
        DbSlotHold.organization_id == organization_id,
        DbSlotHold.status == "active",
        DbSlotHold.expires_at > now,
        DbSlotHold.start_time < slot_end,
        DbSlotHold.end_time > slot_start,
    ).first()
    return conflict is not None


def load_active_holds(
    db: Session,
    organization_id: int,
    lo_id: int,
    range_start: datetime,
    range_end: datetime,
) -> list:
    """
    Batch-load all active, non-expired holds for a user within a date range.

    PERF-012: Replaces per-slot calls to slot_conflicts_with_holds() with a
    single query. The caller can then check conflicts in memory using
    slot_conflicts_with_loaded_holds().

    Returns a list of (start_time, end_time) tuples.
    """
    DbSlotHold = get_model("SlotHold")
    if not DbSlotHold:
        return []

    now = datetime.now(timezone.utc)
    holds = db.query(DbSlotHold).filter(
        DbSlotHold.lo_id == lo_id,
        DbSlotHold.organization_id == organization_id,
        DbSlotHold.status == "active",
        DbSlotHold.expires_at > now,
        DbSlotHold.start_time < range_end,
        DbSlotHold.end_time > range_start,
    ).all()

    return [(h.start_time, h.end_time) for h in holds]


def slot_conflicts_with_loaded_holds(
    holds: list,
    slot_start: datetime,
    slot_end: datetime,
) -> bool:
    """
    Check if a proposed slot conflicts with any pre-loaded holds (in-memory).

    PERF-012: O(N) in-memory check instead of a DB query per slot.
    `holds` is a list of (start_time, end_time) tuples from load_active_holds().
    """
    for hold_start, hold_end in holds:
        if slot_start < hold_end and slot_end > hold_start:
            return True
    return False


def release_holds_for_slot(
    db: Session,
    organization_id: int,
    lo_id: int,
    start_time: datetime,
    end_time: datetime,
) -> int:
    """Release all holds that overlap with a booked slot (DB-backed). Returns count released."""
    DbSlotHold = get_model("SlotHold")
    if not DbSlotHold:
        return 0

    overlapping = db.query(DbSlotHold).filter(
        DbSlotHold.lo_id == lo_id,
        DbSlotHold.organization_id == organization_id,
        DbSlotHold.status == "active",
        DbSlotHold.start_time < end_time,
        DbSlotHold.end_time > start_time,
    ).all()

    for hold in overlapping:
        hold.status = "released"

    released = len(overlapping)
    if released:
        db.flush()
        logger.info(f"Released {released} holds for slot {start_time.isoformat()}")
    return released
