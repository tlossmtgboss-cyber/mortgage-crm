"""
Scheduler audit logging — compliance-grade operation recording.

Also provides audit log retention/archival functions:
  - archive_old_audit_logs(db)   -- batch-delete records older than retention window
  - get_audit_log_stats(db)      -- aggregate stats for admin dashboard
"""

import os
from datetime import datetime, timedelta, timezone
from fastapi import Request
from typing import Optional, Dict, Any
import logging

from sqlalchemy import func, and_, text
from sqlalchemy.orm import Session

from routes.scheduler._core import get_models
from routes.scheduler._rate_limiting import _get_client_ip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retention configuration
# ---------------------------------------------------------------------------
# Default: 365 days.  Override via AUDIT_RETENTION_DAYS environment variable.
# Mortgage compliance typically requires 3-7 year retention depending on
# jurisdiction — adjust accordingly.
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "365"))

# Maximum rows to delete per batch to avoid long-running transactions
_ARCHIVE_BATCH_SIZE = 1000

# PII keys to mask in audit log changes dicts
_PII_EMAIL_KEYS = {'attendee_email', 'email', 'borrower_email', 'lo_email'}
_PII_PHONE_KEYS = {'attendee_phone', 'phone', 'borrower_phone'}
_PII_NAME_KEYS = {'attendee_name', 'borrower_name'}


def _mask_pii_value(key: str, value) -> str:
    """Mask a PII field value for audit storage."""
    if value is None:
        return None
    val = str(value)
    if key in _PII_EMAIL_KEYS:
        # j***@example.com
        parts = val.split('@')
        if len(parts) == 2 and len(parts[0]) > 1:
            return parts[0][0] + '***@' + parts[1]
        return '***'
    if key in _PII_PHONE_KEYS:
        # ***-***-1234
        return '***' + val[-4:] if len(val) >= 4 else '***'
    if key in _PII_NAME_KEYS:
        # J***
        return val[0] + '***' if val else '***'
    return val


def _mask_pii_in_changes(changes: dict) -> dict:
    """Recursively mask PII in an audit changes dict."""
    if not changes or not isinstance(changes, dict):
        return changes
    masked = {}
    for key, value in changes.items():
        if isinstance(value, dict):
            masked[key] = _mask_pii_in_changes(value)
        elif isinstance(value, list):
            masked[key] = [
                _mask_pii_in_changes(item) if isinstance(item, dict)
                else _mask_pii_value(key, item) if key in (_PII_EMAIL_KEYS | _PII_PHONE_KEYS | _PII_NAME_KEYS)
                else item
                for item in value
            ]
        elif key in (_PII_EMAIL_KEYS | _PII_PHONE_KEYS | _PII_NAME_KEYS):
            masked[key] = _mask_pii_value(key, value)
        else:
            masked[key] = value
    return masked


def _audit_log(db, org_id: int, user_id: int, action: str, entity_type: str,
               entity_id: int = None, changes: dict = None, request: Request = None,
               booking_source: str = None):
    """Record an audit log entry for scheduler operations.

    Args:
        booking_source: "authenticated", "public_booking", or "ai_pipeline".
    """
    _models = get_models()
    AuditLog = _models.get('SchedulerAuditLog') if _models else None
    if not AuditLog:
        if os.getenv("RAILWAY_ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "AUDIT_LOG_MODEL_MISSING: SchedulerAuditLog not available in production. "
                "Audit logging is required for compliance."
            )
        logger.warning("SchedulerAuditLog model not available - audit logging disabled (non-production)")
        return
    try:
        # Mask PII in changes dict before persisting
        safe_changes = _mask_pii_in_changes(changes) if changes else changes

        entry = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=safe_changes,
            booking_source=booking_source,
            ip_address=_get_client_ip(request) if request else None,
            user_agent=str(request.headers.get('user-agent', ''))[:255] if request else None,
        )
        db.add(entry)
        # Don't commit here -- let the caller's commit include this
    except Exception as e:
        logger.error("AUDIT_LOG_WRITE_FAILURE", exc_info=True)
        # Compliance-critical operations (GDPR deletion, data export, purge)
        # must not proceed if the audit trail cannot be written.
        _COMPLIANCE_CRITICAL_ACTIONS = {
            'data_deletion', 'data_export', 'data_deleted', 'data_exported',
            'pii_purged', 'gdpr_delete', 'gdpr_export',
            'borrower_data_deleted', 'borrower_data_exported',
            'consent_revoked',
        }
        if action in _COMPLIANCE_CRITICAL_ACTIONS:
            raise RuntimeError(
                f"COMPLIANCE_AUDIT_REQUIRED: Audit log write failed for "
                f"compliance-critical action '{action}'. Aborting operation."
            ) from e


# =============================================================================
# AUDIT LOG RETENTION / ARCHIVAL
# =============================================================================

def archive_old_audit_logs(
    db: Session,
    retention_days: int = AUDIT_RETENTION_DAYS,
) -> Dict[str, Any]:
    """Delete audit log records older than ``retention_days`` in batches.

    Deletes in batches of ``_ARCHIVE_BATCH_SIZE`` to keep each transaction
    short and avoid holding locks for extended periods.

    This function is safe to call from background jobs — it does not require
    HTTP context or authentication.

    Args:
        db: Active SQLAlchemy session (caller is responsible for final commit).
        retention_days: Records older than this many days are deleted.

    Returns:
        Dict with ``deleted_count`` and ``oldest_remaining`` (datetime or None).
    """
    from database.models.scheduler import SchedulerAuditLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    # Count how many records are eligible before deleting
    eligible_count = (
        db.query(func.count(SchedulerAuditLog.id))
        .filter(SchedulerAuditLog.created_at < cutoff)
        .scalar()
    ) or 0

    if eligible_count == 0:
        oldest_remaining = (
            db.query(func.min(SchedulerAuditLog.created_at)).scalar()
        )
        logger.info(
            "Audit log archival: 0 records older than %d days — nothing to delete",
            retention_days,
        )
        return {
            "deleted_count": 0,
            "oldest_remaining": oldest_remaining.isoformat() if oldest_remaining else None,
        }

    total_deleted = 0

    while True:
        # Find the IDs of the next batch to delete
        batch_ids = (
            db.query(SchedulerAuditLog.id)
            .filter(SchedulerAuditLog.created_at < cutoff)
            .order_by(SchedulerAuditLog.created_at.asc())
            .limit(_ARCHIVE_BATCH_SIZE)
            .all()
        )

        if not batch_ids:
            break

        ids_to_delete = [row[0] for row in batch_ids]

        deleted = (
            db.query(SchedulerAuditLog)
            .filter(SchedulerAuditLog.id.in_(ids_to_delete))
            .delete(synchronize_session="fetch")
        )
        db.flush()

        total_deleted += deleted
        logger.info(
            "Audit log archival batch: deleted %d records (%d total so far)",
            deleted,
            total_deleted,
        )

        # If this batch was smaller than the limit, we are done
        if len(ids_to_delete) < _ARCHIVE_BATCH_SIZE:
            break

    # Find the oldest remaining record
    oldest_remaining = (
        db.query(func.min(SchedulerAuditLog.created_at)).scalar()
    )

    logger.info(
        "Audit log archival complete: deleted %d records (retention=%d days, cutoff=%s)",
        total_deleted,
        retention_days,
        cutoff.isoformat(),
    )

    return {
        "deleted_count": total_deleted,
        "oldest_remaining": oldest_remaining.isoformat() if oldest_remaining else None,
    }


def get_audit_log_stats(
    db: Session,
    org_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Return aggregate statistics about the scheduler audit log.

    Powers the admin dashboard "Audit Log Health" card.

    Args:
        db: Active SQLAlchemy session.
        org_id: If provided, scope stats to a single organization.

    Returns:
        Dict with total_count, oldest_record, newest_record,
        estimated_size_bytes, and breakdown_by_entity_type.
    """
    from database.models.scheduler import SchedulerAuditLog

    filters = []
    if org_id is not None:
        filters.append(SchedulerAuditLog.organization_id == org_id)

    base_q = db.query(SchedulerAuditLog)
    if filters:
        base_q = base_q.filter(and_(*filters))

    # Aggregate counts and date range
    agg = (
        db.query(
            func.count(SchedulerAuditLog.id).label("total_count"),
            func.min(SchedulerAuditLog.created_at).label("oldest_record"),
            func.max(SchedulerAuditLog.created_at).label("newest_record"),
        )
        .filter(*filters)
        .one()
    )

    total_count = agg.total_count or 0
    oldest_record = agg.oldest_record
    newest_record = agg.newest_record

    # Rough size estimate: ~400 bytes per row (id, org_id, user_id, action,
    # entity_type, entity_id, changes JSON, timestamps, ip, user_agent)
    estimated_size_bytes = total_count * 400

    # Breakdown by entity_type
    breakdown_q = (
        db.query(
            SchedulerAuditLog.entity_type,
            func.count(SchedulerAuditLog.id).label("count"),
        )
        .filter(*filters)
        .group_by(SchedulerAuditLog.entity_type)
        .order_by(func.count(SchedulerAuditLog.id).desc())
    )

    breakdown = {row.entity_type: row.count for row in breakdown_q.all()}

    return {
        "total_count": total_count,
        "oldest_record": oldest_record.isoformat() if oldest_record else None,
        "newest_record": newest_record.isoformat() if newest_record else None,
        "estimated_size_bytes": estimated_size_bytes,
        "estimated_size_mb": round(estimated_size_bytes / (1024 * 1024), 2),
        "retention_days": AUDIT_RETENTION_DAYS,
        "breakdown_by_entity_type": breakdown,
    }
