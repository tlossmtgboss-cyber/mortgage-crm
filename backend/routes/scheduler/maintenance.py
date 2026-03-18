"""
Scheduler Maintenance - Periodic cleanup tasks for scheduler data.

Endpoints:
  - POST /maintenance/cleanup-holds    Delete expired/released SlotHold records (admin-only)

Also exposes ``cleanup_expired_slot_holds`` as a standalone function that can
be called from cron jobs or background task schedulers without going through
the HTTP layer.
"""

import logging
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_

from db import get_db
from routes.scheduler._helpers import (
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
    _audit_log,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["Scheduler Maintenance"])


# =============================================================================
# STANDALONE CLEANUP FUNCTION (callable from cron / background tasks)
# =============================================================================

def cleanup_expired_slot_holds(
    db: Session,
    *,
    grace_period_hours: int = 1,
    org_id: Optional[int] = None,
) -> int:
    """Delete SlotHold records that expired more than ``grace_period_hours`` ago
    and whose status is 'expired' or 'released'.

    This is safe to call from a cron job or background task -- it does not
    require HTTP context or authentication.

    Args:
        db: Active SQLAlchemy session (caller is responsible for commit/rollback).
        grace_period_hours: Only delete holds that expired at least this many
            hours ago.  Defaults to 1 hour to avoid racing with in-flight
            booking flows.
        org_id: If provided, restrict cleanup to a single organization.

    Returns:
        Number of deleted records.
    """
    from database.models.scheduler import SlotHold

    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_period_hours)

    filters = [
        SlotHold.expires_at < cutoff,
        SlotHold.status.in_(["expired", "released"]),
    ]
    if org_id is not None:
        filters.append(SlotHold.organization_id == org_id)

    count = (
        db.query(SlotHold)
        .filter(and_(*filters))
        .delete(synchronize_session="fetch")
    )

    db.flush()
    logger.info(
        "SlotHold cleanup: deleted %d expired/released records (cutoff=%s, org_id=%s)",
        count,
        cutoff.isoformat(),
        org_id,
    )
    return count


# =============================================================================
# HTTP ENDPOINT
# =============================================================================

@router.post("/cleanup-holds")
async def cleanup_holds_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete expired and released SlotHold records from the database.

    Only records whose ``expires_at`` is more than 1 hour in the past AND
    whose status is ``expired`` or ``released`` are removed.  Active and
    converted holds are never touched.

    Requires admin authentication.
    """
    current_user = await get_current_user(request, db)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = _get_org_id(current_user)

    try:
        deleted_count = cleanup_expired_slot_holds(db, org_id=org_id)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("SlotHold cleanup endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail="Cleanup failed")

    _audit_log(
        db,
        user_id=getattr(current_user, "id", None),
        org_id=org_id,
        action="slot_hold_cleanup",
        details={"deleted_count": deleted_count},
    )

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"Cleaned up {deleted_count} expired/released slot holds",
    }
