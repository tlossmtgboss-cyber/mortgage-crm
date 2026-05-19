"""
Invitation Audit Logger — Tracks all invitation lifecycle events.

Writes to the existing `admin_audit_log` table (best-effort) and always
emits a structured application log line so events are captured even when
the table has not been created yet.

Usage:
    from utils.invitation_audit import log_invite_event

    log_invite_event(db, "invite_created", invite_id=123, actor_id=1, org_id=5,
                     details={"email": "j***@example.com", "role": "sales"})
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Valid event types for invitation lifecycle
INVITE_EVENT_TYPES = frozenset({
    "invite_created",
    "invite_resent",
    "invite_revoked",
    "invite_accepted",
    "invite_accept_failed",
    "invite_expired",
})


def mask_email_for_audit(email: str) -> str:
    """Mask email for audit logging. Shows first 2 chars + domain."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def log_invite_event(
    db: Session,
    event_type: str,
    *,
    invite_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    actor_name: Optional[str] = None,
    org_id: Optional[int] = None,
    target_email: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Log an invitation lifecycle event.

    event_type: One of:
        - invite_created
        - invite_resent
        - invite_revoked
        - invite_accepted
        - invite_accept_failed
        - invite_expired

    Writes to admin_audit_log (best-effort) and always logs via the
    application logger so the event is never silently lost.
    """
    try:
        masked_email = mask_email_for_audit(target_email) if target_email else None

        log_data = {
            "event": event_type,
            "invite_id": invite_id,
            "org_id": org_id,
            "email": masked_email,
        }
        if details:
            log_data.update(details)

        # ------------------------------------------------------------------ #
        # Database insert (best-effort)
        # Matches the admin_audit_log schema:
        #   actor_admin_id  INTEGER NOT NULL
        #   actor_name      VARCHAR(255)
        #   action_type     VARCHAR(100) NOT NULL
        #   target_type     VARCHAR(50) NOT NULL
        #   target_id       INTEGER
        #   target_name     VARCHAR(255)
        #   old_values      JSONB
        #   new_values      JSONB
        #   ip_address      VARCHAR(45)
        #   reason          TEXT
        #   metadata        JSONB
        #   created_at      TIMESTAMP
        # ------------------------------------------------------------------ #
        if actor_id is not None:
            try:
                db.execute(
                    text("""
                        INSERT INTO admin_audit_log (
                            actor_admin_id, actor_name, action_type,
                            target_type, target_id, target_name,
                            new_values, ip_address, metadata, created_at
                        ) VALUES (
                            :actor_id, :actor_name, :action_type,
                            'invitation', :target_id, :target_name,
                            :new_values, :ip_address, :metadata, :created_at
                        )
                    """),
                    {
                        "actor_id": actor_id,
                        "actor_name": actor_name,
                        "action_type": f"invitation.{event_type}",
                        "target_id": invite_id,
                        "target_name": masked_email,
                        "new_values": json.dumps(log_data),
                        "ip_address": ip_address,
                        "metadata": json.dumps({"org_id": org_id} if org_id else {}),
                        "created_at": datetime.now(timezone.utc),
                    },
                )
                # Do NOT commit here — let the caller's transaction handle it.
                # If the caller rolls back, the audit row rolls back too, which
                # is fine because the action itself didn't happen.
            except Exception as _exc:  # noqa: BLE001
                # Table might not exist yet, or actor_id might be invalid.
                # Fall through to the application logger.
                logger.debug("admin_audit_log insert skipped (table may not exist)")

        # ------------------------------------------------------------------ #
        # Application logger (always fires)
        # ------------------------------------------------------------------ #
        logger.info(
            "INVITE_AUDIT: %s | invite_id=%s | actor=%s | org=%s | email=%s",
            event_type,
            invite_id,
            actor_id,
            org_id,
            masked_email,
        )

    except Exception as e:
        # Audit logging must never break the main flow
        logger.warning("Failed to log invite event: %s", e)
