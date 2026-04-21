"""
05-audit-logs/service.py

Audit event service. Two entry points:
  - audit_event(...)           — explicit call from route handlers for semantic events
  - AuditMiddleware            — catches mutating API calls for breadcrumb coverage

Writes are async and non-blocking — an audit failure should NEVER fail the
underlying business operation. Failures log loudly but return silently.

Drop-in: backend/app/services/audit.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


# --- Well-known event types --------------------------------------------------
# Keep this list authoritative. SOC 2 auditors will ask for the catalog.

class EventType:
    # Authentication
    USER_LOGIN = "USER_LOGIN"
    USER_LOGOUT = "USER_LOGOUT"
    USER_LOGOUT_ALL = "USER_LOGOUT_ALL"
    LOGIN_FAILED_NO_USER = "LOGIN_FAILED_NO_USER"
    LOGIN_FAILED_BAD_PASSWORD = "LOGIN_FAILED_BAD_PASSWORD"
    MFA_ENROLLED = "MFA_ENROLLED"
    MFA_CHALLENGED = "MFA_CHALLENGED"
    MFA_FAILED = "MFA_FAILED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    SESSION_REVOKED = "SESSION_REVOKED"
    TOKEN_FAMILY_REVOKED = "TOKEN_FAMILY_REVOKED"

    # User / org admin
    USER_CREATED = "USER_CREATED"
    USER_DISABLED = "USER_DISABLED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"

    # PII access (HIGH SENSITIVITY)
    PII_VIEWED = "PII_VIEWED"
    PII_EXPORTED = "PII_EXPORTED"
    CREDIT_REPORT_PULLED = "CREDIT_REPORT_PULLED"

    # Loan lifecycle
    LOAN_CREATED = "LOAN_CREATED"
    LOAN_STAGE_CHANGED = "LOAN_STAGE_CHANGED"
    LOAN_DELETED = "LOAN_DELETED"
    LOAN_EXPORTED = "LOAN_EXPORTED"

    # Document handling
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"

    # Integration events
    INTEGRATION_CONNECTED = "INTEGRATION_CONNECTED"
    INTEGRATION_DISCONNECTED = "INTEGRATION_DISCONNECTED"
    INTEGRATION_SYNC_STARTED = "INTEGRATION_SYNC_STARTED"
    INTEGRATION_SYNC_COMPLETED = "INTEGRATION_SYNC_COMPLETED"

    # System / admin
    CONFIG_CHANGED = "CONFIG_CHANGED"
    SECRET_ROTATED = "SECRET_ROTATED"


# --- Write API ---------------------------------------------------------------

async def audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    outcome: str = "success",
    actor_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    org_id: uuid.UUID | str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Persist an audit event. Async, fire-and-forget from caller's perspective —
    any failure is logged but does not propagate.
    """
    try:
        event = AuditEvent(
            occurred_at=datetime.now(timezone.utc),
            event_type=event_type,
            outcome=outcome,
            actor_id=_coerce_uuid(actor_id),
            actor_email=actor_email,
            actor_role=actor_role,
            org_id=_coerce_uuid(org_id),
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            metadata_json=_sanitize_metadata(metadata or {}),
        )
        db.add(event)
        await db.flush()
    except Exception as e:
        # Do not let audit failure break the request path.
        logger.exception("Failed to write audit event %s: %s", event_type, e)


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# Keys that must never be written to audit metadata (PII leak protection)
_BLOCKED_KEYS = {
    "ssn", "social_security_number", "tax_id", "ein",
    "password", "password_hash", "secret", "token", "api_key",
    "credit_card", "card_number", "cvv",
    "date_of_birth", "dob", "drivers_license",
    "bank_account", "account_number", "routing_number",
}


def _sanitize_metadata(md: dict[str, Any]) -> dict[str, Any]:
    """Strip keys that would leak PII or credentials."""
    clean: dict[str, Any] = {}
    for k, v in md.items():
        if k.lower() in _BLOCKED_KEYS:
            clean[k] = "[REDACTED]"
            continue
        if isinstance(v, dict):
            clean[k] = _sanitize_metadata(v)
        else:
            clean[k] = v
    return clean
