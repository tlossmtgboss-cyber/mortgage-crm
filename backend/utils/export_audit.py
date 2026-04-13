"""
Export Audit Trail Helper
=========================

Provides a lightweight, non-blocking helper for recording data export/download
events in the audit_logs table. Uses the existing hash-chained audit service
(services/audit_service.py) when possible, falling back to a direct INSERT.

Usage:
    from utils.export_audit import log_export_event

    # Inside an export endpoint:
    log_export_event(
        db=db,
        user_id=current_user.id,
        organization_id=org_id,
        resource_type="leads",
        export_format="csv",
        ip_address=request.client.host,
        details={"record_count": 150, "filters": {"stage": "FUNDED"}},
    )

All calls are wrapped in try/except so a failed audit write never blocks
the actual export response.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_export_event(
    db: Session,
    user_id: int,
    organization_id: Optional[int] = None,
    resource_type: str = "unknown",
    export_format: str = "unknown",
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a data_export audit log entry.

    This is intentionally non-blocking: if the audit insert fails for any
    reason (missing table, constraint violation, etc.) it logs a warning
    and returns silently so the export response is not affected.

    Args:
        db: Active SQLAlchemy session (the same one used by the endpoint).
        user_id: ID of the user performing the export.
        organization_id: Tenant org ID (for RLS scoping).
        resource_type: What is being exported (e.g. "leads", "loans",
            "scorecard", "hmda_lar", "schedule", "document").
        export_format: File format (e.g. "csv", "pdf", "xlsx", "ics", "json", "zip").
        ip_address: Client IP from ``request.client.host``.
        details: Arbitrary metadata dict (record count, filters, etc.).
    """
    try:
        from services.audit_service import create_audit_entry

        after_state = {
            "resource_type": resource_type,
            "export_format": export_format,
        }
        if details:
            after_state.update(details)

        create_audit_entry(
            db=db,
            user_id=user_id,
            changed_by_id=user_id,
            change_type="data_export",
            entity_type=resource_type,
            before_state=None,
            after_state=after_state,
            ip_address=ip_address,
            reason=f"Data export: {resource_type} as {export_format}",
            organization_id=organization_id,
        )
        # Flush is done inside create_audit_entry; we do NOT commit here
        # because the caller's transaction boundary controls that.
        # If the endpoint does not commit after this call, the audit entry
        # will be committed with the next db.commit() or lost on rollback,
        # which is acceptable for a non-critical audit write.

    except Exception as e:
        # Fallback: try a lightweight direct INSERT (handles case where
        # audit_service import fails or hash-chain query errors).
        logger.warning(f"Audit service unavailable, attempting direct insert: {e}")
        try:
            from sqlalchemy import text

            now = datetime.now(timezone.utc)
            after_json = json.dumps(
                {"resource_type": resource_type, "export_format": export_format, **(details or {})},
                default=str,
            )
            db.execute(
                text("""
                    INSERT INTO audit_logs
                        (user_id, changed_by_id, change_type, entity_type,
                         reason, after_state, ip_address, timestamp, organization_id)
                    VALUES
                        (:user_id, :user_id, 'data_export', :entity_type,
                         :reason, :after_state, :ip_address, :ts, :org_id)
                """),
                {
                    "user_id": user_id,
                    "entity_type": resource_type,
                    "reason": f"Data export: {resource_type} as {export_format}",
                    "after_state": after_json,
                    "ip_address": ip_address,
                    "ts": now,
                    "org_id": organization_id,
                },
            )
        except Exception as inner_err:
            # Last resort: just log it. Never break the export.
            logger.warning(
                f"Failed to record export audit event: {inner_err} | "
                f"user={user_id} org={organization_id} resource={resource_type} format={export_format}"
            )


def _get_client_ip(request) -> Optional[str]:
    """Extract client IP from a FastAPI Request object.

    Checks X-Forwarded-For first (for load-balanced/proxied setups),
    then falls back to request.client.host.
    """
    try:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
    except Exception:
        pass
    return None
