"""
Consent Audit Trail Logger

Centralized utility for logging consent lifecycle events to the immutable
ConsentAuditLog table. Used by:
  - telephony/compliance.py (consent verification checks)
  - routes/tcpa_consent_routes.py (TCPA consent grants/revocations)
  - ChannelPreference updates (call_consent, sms_consent toggles)

All functions are fire-and-forget: they catch and log exceptions internally
so that audit logging failures never block the primary operation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Mask phone number to last 4 digits for PII compliance."""
    if not phone:
        return ""
    import re
    digits = re.sub(r'\D', '', phone)
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return f"***{digits}"


def log_consent_event(
    db: Session,
    *,
    organization_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    contact_uuid: Optional[str] = None,
    contact_type: Optional[str] = None,
    consent_type: str,
    action: str,
    method: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    source_table: Optional[str] = None,
    source_record_id: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    verification_result: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
    phone: Optional[str] = None,
) -> None:
    """
    Write a single consent event to the immutable ConsentAuditLog.

    This function does NOT commit the transaction -- the caller's transaction
    will flush and commit it. This ensures the audit record is atomically
    committed with the consent change itself (e.g. if revocation + audit
    must succeed together).

    Args:
        db: SQLAlchemy session (caller manages transaction).
        organization_id: Tenant isolation.
        contact_id: Integer contact/lead ID.
        contact_uuid: UUID-based contact ID (for TCPAConsent contacts).
        contact_type: "lead", "borrower", "referral_partner".
        consent_type: "call", "sms", "email", "voice_ai", "both".
        action: "granted", "revoked", "verified", "expired", "updated".
        method: How consent was captured/revoked.
        ip_address: IP address of the actor.
        user_agent: Browser/app user-agent string.
        source_table: Which table triggered this event.
        source_record_id: ID in the source table.
        actor_user_id: User ID performing the action.
        verification_result: "passed", "failed", "not_found" (for action=verified).
        reason: Human-readable reason.
        details: Additional structured metadata.
        phone: Phone number (will be masked to last 4 digits).
    """
    try:
        from database.models.consent_audit import ConsentAuditLog

        entry = ConsentAuditLog(
            organization_id=organization_id,
            contact_id=contact_id,
            contact_uuid=contact_uuid,
            contact_type=contact_type,
            consent_type=consent_type,
            action=action,
            method=method,
            ip_address=ip_address,
            user_agent=user_agent,
            source_table=source_table,
            source_record_id=source_record_id,
            actor_user_id=actor_user_id,
            verification_result=verification_result,
            reason=reason,
            details=details,
            phone_masked=_mask_phone(phone) if phone else None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        # Do NOT commit -- let the caller's transaction handle it
    except Exception as e:
        logger.error(f"Failed to log consent audit event: {e}", exc_info=True)


def log_consent_granted(
    db: Session,
    *,
    organization_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    contact_uuid: Optional[str] = None,
    contact_type: Optional[str] = None,
    consent_type: str,
    method: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    source_table: Optional[str] = None,
    source_record_id: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    phone: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Shorthand: log a consent GRANTED event."""
    log_consent_event(
        db,
        organization_id=organization_id,
        contact_id=contact_id,
        contact_uuid=contact_uuid,
        contact_type=contact_type,
        consent_type=consent_type,
        action="granted",
        method=method,
        ip_address=ip_address,
        user_agent=user_agent,
        source_table=source_table,
        source_record_id=source_record_id,
        actor_user_id=actor_user_id,
        phone=phone,
        details=details,
    )


def log_consent_revoked(
    db: Session,
    *,
    organization_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    contact_uuid: Optional[str] = None,
    contact_type: Optional[str] = None,
    consent_type: str,
    method: Optional[str] = None,
    ip_address: Optional[str] = None,
    source_table: Optional[str] = None,
    source_record_id: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    phone: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Shorthand: log a consent REVOKED event."""
    log_consent_event(
        db,
        organization_id=organization_id,
        contact_id=contact_id,
        contact_uuid=contact_uuid,
        contact_type=contact_type,
        consent_type=consent_type,
        action="revoked",
        method=method,
        ip_address=ip_address,
        source_table=source_table,
        source_record_id=source_record_id,
        actor_user_id=actor_user_id,
        phone=phone,
        reason=reason,
        details=details,
    )


def log_consent_verified(
    db: Session,
    *,
    organization_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    consent_type: str,
    verification_result: str,
    phone: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    source_table: Optional[str] = None,
    source_record_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Shorthand: log a consent VERIFIED (check) event."""
    log_consent_event(
        db,
        organization_id=organization_id,
        contact_id=contact_id,
        consent_type=consent_type,
        action="verified",
        verification_result=verification_result,
        phone=phone,
        actor_user_id=actor_user_id,
        source_table=source_table,
        source_record_id=source_record_id,
        reason=reason,
        details=details,
    )
