"""
Scheduler audit logging — compliance-grade operation recording.
"""

import os
from fastapi import Request
from typing import Optional
import logging

from routes.scheduler._core import get_models
from routes.scheduler._rate_limiting import _get_client_ip

logger = logging.getLogger(__name__)

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
