"""
Loan State Change Audit Model (D5 — SOC 2 blocker)

Durable, append-only audit trail for every loan/lead state transition. Captures
both the source pipeline (leads / active_loans / mum) and the stage change so
that a complete history can be reconstructed for SOC 2 Type II reporting and
incident investigation.

This complements `audit_events` (generic platform audit) with structured,
loan-pipeline-specific fields so reconciliation, Salesforce sync, manual
edits, and webhook-driven changes all land in one queryable place.

Usage:
    from database.models.loan_state_audit import LoanStateChangeAudit
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from database import Base


class LoanStateChangeAudit(Base):
    """
    One row per loan/lead state transition. **INSERT-ONLY** — never updated or
    deleted by application code. There is intentionally no `updated_at`
    column; rows are immutable for SOC 2 compliance. Retention is enforced
    by a periodic cleanup job (7 years for financial controls).
    """

    __tablename__ = "loan_state_change_audit"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )

    # FK to loans.id (Integer in this schema). Indexed for per-loan history.
    loan_id = Column(
        Integer,
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pre-loan (lead-stage) transitions reference the lead by id. Spec calls
    # for UUID; left nullable so post-conversion transitions can omit it.
    lead_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Tenant scoping for RLS. Spec mandates UUID — this is a logical org id
    # carried alongside any integer FK on the loans table.
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Stage transition
    from_stage = Column(String(64), nullable=True)  # null = initial creation
    to_stage = Column(String(64), nullable=False)

    # Pipeline category transition: leads / active_loans / mum
    from_pipeline = Column(String(32), nullable=True)
    to_pipeline = Column(String(32), nullable=False)

    # Where did this transition originate from?
    # e.g. salesforce_sync, manual, reconciliation, webhook, encompass_sync
    trigger_source = Column(String(64), nullable=False)

    # Who triggered it. null = system / automated.
    actor_user_id = Column(UUID(as_uuid=True), nullable=True)

    # Free-form structured context (reconciliation result, raw SF stage,
    # warnings, etc.). NO PII — use references, not copies.
    audit_metadata = Column(JSONB, nullable=True)

    # Server time (UTC).
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # --- Tamper-evident SHA-256 hash chain ------------------------------
    # ``prev_hash`` is the ``entry_hash`` of the previous row in this
    # logical audit chain (NULL for the very first row). ``entry_hash`` is
    # SHA-256 of (prev_hash || canonical_json(this_row_minus_hash_fields))
    # so any tampering breaks every downstream entry.
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_loan_state_audit_org_loan_created",
            "organization_id",
            "loan_id",
            "created_at",
        ),
    )
