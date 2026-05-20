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

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Fields included in the canonical-JSON payload that gets hashed. The hash
# columns themselves are deliberately excluded — they are derived values.
_HASH_FIELDS = (
    "id",
    "loan_id",
    "lead_id",
    "organization_id",
    "from_stage",
    "to_stage",
    "from_pipeline",
    "to_pipeline",
    "trigger_source",
    "actor_user_id",
    "audit_metadata",
    "created_at",
)


def _canonical_payload(row) -> str:
    """Stable JSON serialization of an audit row for hashing."""
    out: Dict[str, Any] = {}
    for field in _HASH_FIELDS:
        value = getattr(row, field, None)
        if value is None:
            out[field] = None
        elif isinstance(value, (str, int, float, bool)):
            out[field] = value
        elif isinstance(value, uuid.UUID):
            out[field] = str(value)
        elif isinstance(value, dict):
            out[field] = value
        else:
            # datetime, Decimal, etc. — stringify deterministically.
            out[field] = str(value)
    return json.dumps(out, sort_keys=True, separators=(",", ":"), default=str)


def _compute_entry_hash(prev_hash: Optional[str], row) -> str:
    payload = (prev_hash or "") + "|" + _canonical_payload(row)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash_for_loan(db: Session, loan_id: int) -> Optional[str]:
    """Return the most-recent ``entry_hash`` for ``loan_id`` if any."""
    from database.models.loan_state_audit import LoanStateChangeAudit
    last = (
        db.query(LoanStateChangeAudit)
        .filter(LoanStateChangeAudit.loan_id == int(loan_id))
        .order_by(LoanStateChangeAudit.created_at.desc())
        .first()
    )
    if last is None:
        return None
    return getattr(last, "entry_hash", None)


def verify_chain(db: Session, loan_id: int) -> bool:
    """Walk the hash chain for ``loan_id`` and confirm every entry is intact.

    Returns ``True`` if every row's ``entry_hash`` matches the recomputed
    hash of ``(prev_hash || canonical_json(row))`` AND each row's
    ``prev_hash`` equals the previous row's ``entry_hash``. Returns
    ``False`` on the first mismatch.
    """
    from database.models.loan_state_audit import LoanStateChangeAudit

    rows = (
        db.query(LoanStateChangeAudit)
        .filter(LoanStateChangeAudit.loan_id == int(loan_id))
        .order_by(LoanStateChangeAudit.created_at.asc())
        .all()
    )

    expected_prev: Optional[str] = None
    for row in rows:
        stored_prev = getattr(row, "prev_hash", None)
        stored_entry = getattr(row, "entry_hash", None)
        if stored_entry is None:
            # Pre-chain row — skip but keep walking so partial backfill is OK.
            expected_prev = stored_entry
            continue
        if expected_prev is not None and stored_prev != expected_prev:
            return False
        recomputed = _compute_entry_hash(stored_prev, row)
        if recomputed != stored_entry:
            return False
        expected_prev = stored_entry
    return True


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

        # Compute hash chain BEFORE the insert so a verifier walking the
        # rows after-the-fact can recompute every entry deterministically.
        # ``id`` and ``created_at`` may be server-defaulted — pre-populate
        # them so they participate in the canonical payload.
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()
        if getattr(row, "created_at", None) is None:
            from datetime import datetime, timezone
            row.created_at = datetime.now(timezone.utc)

        try:
            prev_hash = _last_hash_for_loan(own_db, int(loan_id))
        except Exception as _exc:  # noqa: BLE001
            # If the column doesn't exist yet (older deploy), skip chaining.
            prev_hash = None

        try:
            row.prev_hash = prev_hash
            row.entry_hash = _compute_entry_hash(prev_hash, row)
        except Exception as _exc:  # noqa: BLE001
            # Never block an audit write on hash-chain math.
            logger.exception("loan_state_audit: hash chain computation failed")

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
