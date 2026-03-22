"""
Immutable Compliance Decision Audit Log

Append-only audit trail for every compliance decision made by the system:
DNC checks, TCPA calling-hours validation, consent verification, rate-limit
enforcement, and multi-agent soft-lock acquisition.

This table is APPEND-ONLY. No UPDATE or DELETE operations should ever be
performed on this table. Each row represents a single compliance check or
decision made by the system.

Regulatory context:
    - TCPA (47 U.S.C. 227) requires evidence of compliance checks before
      autodialed/prerecorded calls.
    - TRID (12 CFR 1026.19) mandates disclosure-timing audit trails.
    - FCC 1:1 consent rule (eff. April 2026) requires provable consent checks.
    - Recommended retention: 7 years (matches IRS guidance for mortgage lenders).

Usage:
    from database.models.compliance_log import ComplianceDecisionLog

    log_entry = ComplianceDecisionLog(
        organization_id=org_id,
        user_id=agent_id,
        decision_type="dnc_check",
        phone_number="***1234",       # Masked for PII
        contact_id=lead_id,
        decision="blocked",
        reason="Number on internal DNC list",
        details={"source": "internal_dnc", "dnc_reason": "customer_request"},
    )
    db.add(log_entry)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)

from db import Base


class ComplianceDecisionLog(Base):
    """
    Immutable audit log for all compliance decisions.

    This table is APPEND-ONLY. No UPDATE or DELETE operations should ever
    be performed on this table. Each row represents a single compliance
    check or decision made by the system.

    Decision types:
        - dnc_check: Do Not Call list verification
        - calling_hours: TCPA calling-hours (8 AM - 9 PM local) validation
        - consent_check: Call consent verification (FCC 1:1 rule)
        - rate_limit: Agent daily call-limit enforcement
        - soft_lock: Multi-agent collision prevention lock check/acquisition
        - call_blocked: Composite decision from full_compliance_check
        - two_party_consent: Two-party recording consent (state-specific)

    Decision values:
        - allowed: Check passed, action may proceed
        - blocked: Check failed, action was prevented
        - warning: Check raised a concern but did not block
        - acquired: Lock was successfully acquired (soft_lock only)
    """
    __tablename__ = "compliance_decision_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # What was checked
    decision_type = Column(String, nullable=False, index=True)
    phone_number = Column(String, nullable=True)  # Masked: last 4 digits only for PII
    contact_id = Column(Integer, nullable=True)
    lead_id = Column(Integer, nullable=True)

    # Decision
    decision = Column(String, nullable=False)  # allowed, blocked, warning
    reason = Column(String, nullable=True)  # Human-readable reason

    # Context
    details = Column(JSON, nullable=True)  # Additional structured data (timezone, area_code, etc.)

    # Immutable timestamp -- no updated_at by design
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Ensure immutability at application level
    __table_args__ = (
        Index('ix_compliance_log_org_created', 'organization_id', 'created_at'),
        Index('ix_compliance_log_type_created', 'decision_type', 'created_at'),
    )


__all__ = [
    "ComplianceDecisionLog",
]
