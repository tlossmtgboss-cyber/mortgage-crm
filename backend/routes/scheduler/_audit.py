"""
Scheduler audit logging — compliance-grade operation recording.
"""

from fastapi import Request
from typing import Optional
import logging

from routes.scheduler._core import get_models
from routes.scheduler._rate_limiting import _get_client_ip

logger = logging.getLogger(__name__)


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
        return
    try:
        entry = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            booking_source=booking_source,
            ip_address=_get_client_ip(request) if request else None,
            user_agent=str(request.headers.get('user-agent', ''))[:255] if request else None,
        )
        db.add(entry)
        # Don't commit here -- let the caller's commit include this
    except Exception as e:
        logger.error("AUDIT_LOG_WRITE_FAILURE", exc_info=True)
