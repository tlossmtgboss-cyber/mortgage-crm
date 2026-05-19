"""
Audit Service — Hash-Chained Append-Only Audit Logging

P0-4 Enterprise Remediation: Audit log entries are hash-chained for tamper detection.
Each new entry includes:
  - sequence_number: monotonically increasing
  - record_hash: SHA-256 of (user_id + change_type + entity_type + timestamp + before_state + after_state + previous_hash)
  - previous_hash: hash of the prior entry (NULL for the first entry)

The database enforces immutability via triggers that prevent UPDATE and DELETE.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _compute_record_hash(
    user_id: int,
    change_type: str,
    entity_type: str,
    timestamp: str,
    before_state: Optional[str],
    after_state: Optional[str],
    previous_hash: Optional[str],
) -> str:
    """Compute SHA-256 hash for an audit log record."""
    payload = "|".join([
        str(user_id),
        change_type,
        entity_type,
        timestamp,
        before_state or "",
        after_state or "",
        previous_hash or "",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_audit_entry(
    db: Session,
    user_id: int,
    changed_by_id: int,
    change_type: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    session_id: Optional[str] = None,
    reason: Optional[str] = None,
    organization_id: Optional[int] = None,
) -> int:
    """
    Create a hash-chained audit log entry.

    Returns the new audit log entry ID.
    """
    from database.models.security import AuditLog

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    before_json = json.dumps(before_state, sort_keys=True, default=str) if before_state else None
    after_json = json.dumps(after_state, sort_keys=True, default=str) if after_state else None

    # Get previous entry's hash and sequence number, scoped to org if provided
    if organization_id:
        prev = db.execute(text("""
            SELECT sequence_number, record_hash
            FROM audit_logs
            WHERE sequence_number IS NOT NULL AND organization_id = :org_id
            ORDER BY sequence_number DESC
            LIMIT 1
        """), {"org_id": organization_id}).fetchone()
    else:
        prev = db.execute(text("""
            SELECT sequence_number, record_hash
            FROM audit_logs
            WHERE sequence_number IS NOT NULL
            ORDER BY sequence_number DESC
            LIMIT 1
        """)).fetchone()

    if prev:
        prev_seq = prev[0]
        prev_hash = prev[1]
    else:
        prev_seq = 0
        prev_hash = None

    new_seq = prev_seq + 1

    record_hash = _compute_record_hash(
        user_id=user_id,
        change_type=change_type,
        entity_type=entity_type,
        timestamp=now_iso,
        before_state=before_json,
        after_state=after_json,
        previous_hash=prev_hash,
    )

    entry = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        changed_by_id=changed_by_id,
        change_type=change_type,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        session_id=session_id,
        reason=reason,
        timestamp=now,
        sequence_number=new_seq,
        record_hash=record_hash,
        previous_hash=prev_hash,
        hash_algorithm="sha256",
    )

    db.add(entry)
    db.flush()  # Get the ID without committing (caller controls transaction)

    logger.info(f"Audit entry #{new_seq} created (hash: {record_hash[:12]}...)")
    return entry.id


def cleanup_old_audit_events(db: Session, retention_days: int = 2555) -> Dict[str, Any]:
    """Delete audit log entries older than the retention period.

    Default retention is 2555 days (~7 years), which satisfies RESPA/TILA
    regulatory requirements for mortgage record-keeping.

    NOTE: The audit_logs table has immutability triggers that prevent DELETE.
    This function temporarily disables the trigger, performs the cleanup,
    then re-enables it. Only call from admin management endpoints.

    Args:
        db: Database session
        retention_days: Number of days to retain. Must be >= 365 (1 year minimum).

    Returns:
        Dict with count of deleted rows and cutoff date.
    """
    if retention_days < 365:
        raise ValueError(f"retention_days must be >= 365 for compliance, got: {retention_days}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    # Count rows to delete before executing
    count_result = db.execute(
        text("SELECT count(*) FROM audit_logs WHERE timestamp < :cutoff"),
        {"cutoff": cutoff},
    ).scalar()

    if count_result == 0:
        return {
            "deleted": 0,
            "cutoff_date": cutoff.isoformat(),
            "retention_days": retention_days,
            "message": "No audit entries older than retention period",
        }

    # Temporarily disable immutability trigger if it exists, then delete
    try:
        db.execute(text(
            "ALTER TABLE audit_logs DISABLE TRIGGER ALL"
        ))
    except Exception as _exc:  # noqa: BLE001
        pass  # Trigger may not exist in dev/test environments

    result = db.execute(
        text("DELETE FROM audit_logs WHERE timestamp < :cutoff"),
        {"cutoff": cutoff},
    )
    deleted = result.rowcount

    try:
        db.execute(text(
            "ALTER TABLE audit_logs ENABLE TRIGGER ALL"
        ))
    except Exception as _exc:  # noqa: BLE001
        pass

    db.commit()

    logger.info(
        f"Audit retention cleanup: deleted {deleted} entries older than "
        f"{cutoff.isoformat()} ({retention_days} days)"
    )

    return {
        "deleted": deleted,
        "cutoff_date": cutoff.isoformat(),
        "retention_days": retention_days,
        "message": f"Deleted {deleted} audit entries older than {retention_days} days",
    }


def verify_audit_chain(db: Session, limit: int = 1000, organization_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Verify the integrity of the audit log hash chain.

    Args:
        db: Database session
        limit: Max entries to verify
        organization_id: If provided, only verify chain for this organization

    Returns a dict with verification results.
    """
    if organization_id:
        rows = db.execute(text("""
            SELECT id, user_id, change_type, entity_type, timestamp,
                   before_state, after_state, sequence_number,
                   record_hash, previous_hash
            FROM audit_logs
            WHERE sequence_number IS NOT NULL AND organization_id = :org_id
            ORDER BY sequence_number ASC
            LIMIT :limit
        """), {"limit": limit, "org_id": organization_id}).fetchall()
    else:
        rows = db.execute(text("""
            SELECT id, user_id, change_type, entity_type, timestamp,
                   before_state, after_state, sequence_number,
                   record_hash, previous_hash
            FROM audit_logs
            WHERE sequence_number IS NOT NULL
            ORDER BY sequence_number ASC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

    if not rows:
        return {"verified": True, "count": 0, "message": "No hash-chained entries found"}

    broken_links = []
    prev_hash = None

    for row in rows:
        row_id, user_id, change_type, entity_type, ts, before_state, after_state, seq, stored_hash, stored_prev = row

        # Verify previous_hash linkage
        if stored_prev != prev_hash:
            broken_links.append({
                "id": row_id,
                "sequence": seq,
                "issue": "previous_hash mismatch",
                "expected": prev_hash,
                "actual": stored_prev,
            })

        # Verify record_hash
        before_json = json.dumps(before_state, sort_keys=True, default=str) if before_state else None
        after_json = json.dumps(after_state, sort_keys=True, default=str) if after_state else None
        ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)

        expected_hash = _compute_record_hash(
            user_id=user_id,
            change_type=change_type,
            entity_type=entity_type,
            timestamp=ts_str,
            before_state=before_json,
            after_state=after_json,
            previous_hash=stored_prev,
        )

        if stored_hash != expected_hash:
            broken_links.append({
                "id": row_id,
                "sequence": seq,
                "issue": "record_hash mismatch",
                "expected": expected_hash[:16] + "...",
                "actual": stored_hash[:16] + "..." if stored_hash else None,
            })

        prev_hash = stored_hash

    return {
        "verified": len(broken_links) == 0,
        "count": len(rows),
        "broken_links": broken_links,
        "message": "Chain intact" if not broken_links else f"{len(broken_links)} broken links detected",
    }
