"""
Scheduler Maintenance - Periodic cleanup tasks for scheduler data.

Endpoints:
  - POST /maintenance/cleanup-holds          Delete expired/released SlotHold records (admin-only)
  - POST /maintenance/archive-audit-logs     Archive/delete old audit log entries (admin-only)
  - GET  /maintenance/audit-log-stats        Audit log aggregate statistics (admin-only)

Also exposes standalone functions that can be called from cron jobs or
background task schedulers without going through the HTTP layer:

  - ``expire_stale_active_holds(db)``  -- mark active holds past their TTL as expired
  - ``cleanup_expired_slot_holds(db)`` -- delete old expired/released hold records
  - ``run_hold_maintenance(db)``       -- run both steps in sequence (used by scheduler_service)
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
# STANDALONE CLEANUP FUNCTIONS (callable from cron / background tasks)
# =============================================================================

def expire_stale_active_holds(
    db: Session,
    *,
    org_id: Optional[int] = None,
) -> int:
    """Transition SlotHold records from 'active' to 'expired' when their
    ``expires_at`` has passed.

    This is the critical step that prevents phantom slot blocking: without it,
    holds whose TTL has elapsed remain in 'active' status and any code that
    checks ``status == 'active'`` (without also filtering on ``expires_at``)
    treats them as real reservations.

    The ``slot_hold_service`` already filters on ``expires_at > now`` for its
    own queries, but this bulk update keeps the data consistent for any other
    callers and reduces the working set of active holds.

    NOTE for the agent editing ``_availability.py``: if that module adds
    SlotHold conflict checking, make sure the query includes
    ``SlotHold.expires_at > datetime.now(timezone.utc)`` so expired holds
    are invisible even before this cleanup runs.

    Safe to call frequently (every few minutes).  Designed for the background
    scheduler -- does not require HTTP context or authentication.

    Args:
        db: Active SQLAlchemy session (caller is responsible for commit/rollback).
        org_id: If provided, restrict to a single organization.

    Returns:
        Number of holds transitioned to 'expired'.
    """
    from database.models.scheduler import SlotHold

    now = datetime.now(timezone.utc)

    filters = [
        SlotHold.status == "active",
        SlotHold.expires_at <= now,
    ]
    if org_id is not None:
        filters.append(SlotHold.organization_id == org_id)

    count = (
        db.query(SlotHold)
        .filter(and_(*filters))
        .update(
            {SlotHold.status: "expired"},
            synchronize_session="fetch",
        )
    )

    db.flush()
    if count > 0:
        logger.info(
            "SlotHold expiry: marked %d active holds as expired (org_id=%s)",
            count,
            org_id,
        )
    return count


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
    if count > 0:
        logger.info(
            "SlotHold cleanup: deleted %d expired/released records (cutoff=%s, org_id=%s)",
            count,
            cutoff.isoformat(),
            org_id,
        )
    return count


def run_hold_maintenance(
    db: Session,
    *,
    org_id: Optional[int] = None,
) -> dict:
    """Run both maintenance steps in sequence:
    1. Expire stale active holds (active -> expired)
    2. Delete old expired/released records

    This is the function called by the background scheduler every 5 minutes.

    Args:
        db: Active SQLAlchemy session (caller is responsible for commit/rollback).
        org_id: If provided, restrict to a single organization.

    Returns:
        Dict with ``expired_count`` and ``deleted_count``.
    """
    expired_count = expire_stale_active_holds(db, org_id=org_id)
    deleted_count = cleanup_expired_slot_holds(db, org_id=org_id)
    return {"expired_count": expired_count, "deleted_count": deleted_count}


# =============================================================================
# HTTP ENDPOINT
# =============================================================================

@router.post("/cleanup-holds")
async def cleanup_holds_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Run full SlotHold maintenance: expire stale active holds, then delete
    old expired/released records.

    Step 1: Any hold with status ``active`` whose ``expires_at`` has passed
    is transitioned to ``expired``.

    Step 2: Records whose ``expires_at`` is more than 1 hour in the past AND
    whose status is ``expired`` or ``released`` are deleted.

    Converted holds are never touched.

    Requires admin authentication.
    """
    current_user = await get_current_user(request, db)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = _get_org_id(current_user)

    try:
        result = run_hold_maintenance(db, org_id=org_id)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("SlotHold cleanup endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail="Cleanup failed")

    _audit_log(
        db, org_id, getattr(current_user, "id", None),
        "slot_hold_cleanup", "slot_hold",
        changes=result,
    )
    db.commit()

    return {
        "status": "success",
        "expired_count": result["expired_count"],
        "deleted_count": result["deleted_count"],
        "message": (
            f"Expired {result['expired_count']} stale holds, "
            f"deleted {result['deleted_count']} old records"
        ),
    }


# =============================================================================
# AUDIT LOG ARCHIVAL / STATS ENDPOINTS
# =============================================================================

# Simple in-memory rate limiter for audit archival: track last invocation time
# per org_id so the endpoint cannot be spammed.
_archive_last_run: dict[int, datetime] = {}
_ARCHIVE_COOLDOWN_SECONDS = 300  # 5 minutes


@router.post("/archive-audit-logs")
async def archive_audit_logs_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete scheduler audit log entries older than the retention period.

    Deletes in batches of 1,000 rows to keep transactions short.  Returns the
    total number of deleted records and the timestamp of the oldest remaining
    record.

    Rate-limited to 1 request per 5 minutes per organization.

    Requires admin authentication.
    """
    current_user = await get_current_user(request, db)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = _get_org_id(current_user)

    # Rate limit: 1 request per 5 minutes per org
    now = datetime.now(timezone.utc)
    last_run = _archive_last_run.get(org_id)
    if last_run and (now - last_run).total_seconds() < _ARCHIVE_COOLDOWN_SECONDS:
        remaining = int(_ARCHIVE_COOLDOWN_SECONDS - (now - last_run).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Audit log archival can only be run once every 5 minutes. Try again in {remaining}s.",
        )

    try:
        from routes.scheduler._audit import archive_old_audit_logs

        result = archive_old_audit_logs(db)
        db.commit()
        _archive_last_run[org_id] = now
    except Exception as e:
        db.rollback()
        logger.exception("Audit log archival endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail="Audit log archival failed")

    _audit_log(
        db, org_id, getattr(current_user, "id", None),
        "audit_log_archival", "scheduler_audit_log",
        changes=result,
    )
    db.commit()

    return {
        "status": "success",
        "deleted_count": result["deleted_count"],
        "oldest_remaining": result["oldest_remaining"],
        "message": f"Archived {result['deleted_count']} old audit log entries",
    }


@router.get("/audit-log-stats")
async def audit_log_stats_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return aggregate statistics about the scheduler audit log.

    Provides total count, date range, estimated storage size, and a breakdown
    by entity_type.  Powers the admin dashboard "Audit Log Health" card.

    Requires admin authentication.
    """
    current_user = await get_current_user(request, db)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = _get_org_id(current_user)

    try:
        from routes.scheduler._audit import get_audit_log_stats

        stats = get_audit_log_stats(db, org_id=org_id)
    except Exception as e:
        logger.exception("Audit log stats endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve audit log stats")

    return {
        "status": "success",
        **stats,
    }
