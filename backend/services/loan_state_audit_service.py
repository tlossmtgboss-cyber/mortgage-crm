"""
Loan State Audit Service (D5 — SOC 2 durable audit trail)

Single-entry helper for inserting rows into `loan_state_change_audit`.

Design rules:
  * INSERT-ONLY — rows are never updated or deleted by application code.
  * Best-effort — failures MUST NOT propagate. The audit log must never
    block a successful state transition. All errors are logged and
    swallowed.
  * Caller-agnostic — accepts any SQLAlchemy session. If the caller's
    session is already in a transaction, the audit row is committed on a
    fresh session so a rollback in the caller cannot lose the audit row.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Stable namespace for deriving deterministic UUIDs from legacy integer IDs.
# Keep constant — never change after the table has rows or audit lookups break.
_LEGACY_INT_ID_NS = uuid.UUID("d5a4d171-0000-4000-8000-000000000005")


def _coerce_uuid(value: Any, *, kind: str = "id") -> Optional[uuid.UUID]:
    """
    Best-effort coercion to UUID.

    * Already a UUID → returned as-is.
    * String that parses as UUID → returned.
    * Integer (or numeric string) → deterministic UUIDv5 in the legacy
      namespace, so the same int always maps to the same UUID. This lets the
      audit table serve the current Integer-FK schema today and a future
      UUID-FK schema without code changes.
    * Anything else → ``None``.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except (ValueError, AttributeError, TypeError):
        pass
    # Fall back to deterministic UUIDv5 for legacy integer IDs.
    try:
        if s.lstrip("-").isdigit():
            return uuid.uuid5(_LEGACY_INT_ID_NS, f"{kind}:{s}")
    except Exception as _exc:  # noqa: BLE001
        return None
    return None


def record_state_change(
    db: Session,
    *,
    loan_id: int,
    lead_id: Optional[Union[str, uuid.UUID]] = None,
    organization_id: Union[str, uuid.UUID],
    from_stage: Optional[str],
    to_stage: str,
    from_pipeline: Optional[str],
    to_pipeline: str,
    trigger_source: str,
    actor_user_id: Optional[Union[str, uuid.UUID]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[uuid.UUID]:
    """
    Insert a row into `loan_state_change_audit`.

    Returns the new row's UUID on success, or ``None`` if the write failed.
    NEVER raises — failures are logged and swallowed so the calling
    transition path is never blocked by audit-log issues.

    Uses a *fresh* SessionLocal so the audit row is durable even if the
    caller's session is later rolled back. Inherits RLS tenant context from
    the caller when possible.
    """
    # Coerce types
    org_uuid = _coerce_uuid(organization_id, kind="org")
    if org_uuid is None:
        logger.warning(
            "loan_state_audit: refusing to record — invalid organization_id=%r",
            organization_id,
        )
        return None

    if not to_stage or not to_pipeline or not trigger_source:
        logger.warning(
            "loan_state_audit: refusing to record — missing required field "
            "(to_stage=%r, to_pipeline=%r, trigger_source=%r)",
            to_stage,
            to_pipeline,
            trigger_source,
        )
        return None

    own_db: Optional[Session] = None
    try:
        # Fresh session so the audit row is durable even if the caller rolls
        # back its own transaction.
        from db import SessionLocal  # local import to avoid cycles
        own_db = SessionLocal()

        # Inherit RLS context from the caller's session if possible.
        try:
            from sqlalchemy import text as _sa_text
            tenant = db.execute(_sa_text("SHOW app.current_tenant")).scalar()
            if tenant:
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(own_db, int(tenant))
                except Exception as _exc:  # noqa: BLE001
                    # tenant_mixin shape may differ; fall back to raw SET
                    logger.exception("unhandled exception")
                    own_db.execute(
                        _sa_text("SET LOCAL app.current_tenant = :t"),
                        {"t": str(tenant)},
                    )
        except Exception as _exc:  # noqa: BLE001
            # No RLS context configured — fine for system-wide writes.
            pass

        from database.models.loan_state_audit import LoanStateChangeAudit

        row = LoanStateChangeAudit(
            loan_id=int(loan_id),
            lead_id=_coerce_uuid(lead_id, kind="lead"),
            organization_id=org_uuid,
            from_stage=from_stage,
            to_stage=to_stage,
            from_pipeline=from_pipeline,
            to_pipeline=to_pipeline,
            trigger_source=trigger_source,
            actor_user_id=_coerce_uuid(actor_user_id, kind="user"),
            audit_metadata=dict(metadata) if metadata else None,
        )
        own_db.add(row)
        own_db.commit()
        own_db.refresh(row)
        return row.id
    except Exception as exc:
        logger.error(
            "loan_state_audit: failed to record state change "
            "(loan_id=%s, %s -> %s, src=%s): %s",
            loan_id,
            from_stage,
            to_stage,
            trigger_source,
            exc,
        )
        if own_db is not None:
            try:
                own_db.rollback()
            except Exception as rb_exc:  # pragma: no cover
                logger.debug("loan_state_audit: rollback failed: %s", rb_exc)
        return None
    finally:
        if own_db is not None:
            try:
                own_db.close()
            except Exception as _exc:  # pragma: no cover  # noqa: BLE001
                pass
