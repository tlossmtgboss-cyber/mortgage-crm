"""
GDPR Erasure Request Model

Tracks right-to-erasure (Article 17) requests through a full lifecycle:
pending -> approved -> executing -> completed (or failed).

This model exists alongside the lighter-weight DataSubjectRequest in
security.py, which covers all DSAR types (access, rectification, erasure,
restriction). ErasureRequest is specifically for tracking the *execution*
of data deletion — the destructive operation that cascades PII removal
across the CRM while preserving loan records required by NMLS/RESPA.

IMPORTANT — Mortgage Compliance Tension:
    GDPR Article 17 grants the right to erasure, BUT US mortgage
    regulations (RESPA Section 8, ECOA/Reg B, TRID/TILA) require
    7-year retention of loan records, disclosures, adverse actions,
    and fee histories. The resolution:

    - Borrower PII (name, email, phone, SSN, address) is ANONYMIZED
      with "[GDPR_REDACTED]" markers.
    - Loan structure (amounts, rates, dates, stages, fees, disclosures)
      is PRESERVED for the full 7-year regulatory window.
    - Audit trail entries are retained but PII within them is stripped.
    - Communication content (SMS, email bodies) is redacted.
    - Documents containing PII are hard-deleted.

    This approach satisfies both GDPR erasure and US mortgage compliance.

Usage:
    from database.models.gdpr import ErasureRequest

    request = ErasureRequest(
        requester_id=admin_user.id,
        organization_id=admin_user.organization_id,
        data_subject_email="borrower@example.com",
        reason="GDPR Article 17 right to erasure",
    )
    db.add(request)
    db.commit()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Index,
)

from db import Base


class ErasureRequest(Base):
    """Tracks a GDPR right-to-erasure request through its lifecycle.

    Status flow:
        pending -> approved -> executing -> completed
                                         -> failed

    The audit_log JSON column accumulates a timestamped record of every
    table touched, rows affected, and any errors encountered during
    execution. This log is itself PII-free (it records counts and table
    names, never the data being deleted).
    """

    __tablename__ = "erasure_requests"
    __table_args__ = (
        Index("ix_erasure_requests_org_id", "organization_id"),
        Index("ix_erasure_requests_status", "status"),
        Index("ix_erasure_requests_email", "data_subject_email"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Who requested the erasure (must be an admin user)
    requester_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        doc="Admin user who submitted the erasure request.",
    )

    # Tenant isolation
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        doc="Organization scope for the erasure.",
    )

    # Data subject identification — at least one must be provided.
    # Using email as the primary key for borrower identification since
    # BorrowerProfile has no phone column (match on email only per CLAUDE.md).
    data_subject_email = Column(
        String(255),
        nullable=True,
        index=True,
        doc="Email of the data subject requesting erasure.",
    )
    data_subject_user_id = Column(
        Integer,
        nullable=True,
        doc="Internal user ID if the data subject is a platform user.",
    )

    # Lifecycle status
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        doc="Request status: pending, approved, executing, completed, failed.",
    )

    # Reason / legal basis
    reason = Column(
        Text,
        nullable=True,
        default="GDPR Article 17 right to erasure",
        doc="Legal basis or reason for the erasure request.",
    )

    # Timestamps
    requested_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="When the erasure request was submitted.",
    )
    approved_at = Column(
        DateTime,
        nullable=True,
        doc="When the request was approved for execution.",
    )
    executed_at = Column(
        DateTime,
        nullable=True,
        doc="When execution started.",
    )
    completed_at = Column(
        DateTime,
        nullable=True,
        doc="When the erasure finished (success or failure).",
    )

    # Execution details — JSON log of what was done
    audit_log = Column(
        JSON,
        nullable=True,
        default=dict,
        doc=(
            "Structured log of the erasure execution. Contains table names, "
            "row counts, actions taken (redacted vs deleted), and any errors. "
            "This log itself must NOT contain PII."
        ),
    )

    # Error tracking
    error_message = Column(
        Text,
        nullable=True,
        doc="Error details if status is 'failed'.",
    )


__all__ = [
    "ErasureRequest",
]
