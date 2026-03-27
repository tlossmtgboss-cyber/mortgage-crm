"""
Compliance Models

Enterprise readiness: TRID, ECOA, HMDA compliance automation.
Domain 2 critical checks: 2.1-2.8

Models:
    - LoanFee: Individual fee tracking for TRID tolerance calculations
    - DisclosureEvent: Audit trail for all disclosure delivery events
    - AdverseActionNotice: ECOA-compliant adverse action tracking
    - ComplianceAlert: Real-time compliance violation alerting

Usage:
    from database.models.compliance import LoanFee, DisclosureEvent, AdverseActionNotice, ComplianceAlert
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric, text
)
from sqlalchemy.orm import relationship

from db import Base

import enum


# ============================================================================
# COMPLIANCE ENUMS
# ============================================================================

class ToleranceCategory(str, enum.Enum):
    """TRID fee tolerance categories (12 CFR 1026.19(e)(3))"""
    ZERO = "zero"                    # No increase allowed (lender fees, transfer taxes)
    TEN_PERCENT = "ten_percent"      # Aggregate 10% increase allowed (third-party fees with no shopping)
    UNLIMITED = "unlimited"          # No limit (services borrower can shop for)


class DisclosureType(str, enum.Enum):
    """Types of regulated disclosures"""
    LOAN_ESTIMATE = "loan_estimate"
    REVISED_LE = "revised_le"
    CLOSING_DISCLOSURE = "closing_disclosure"
    REVISED_CD = "revised_cd"


class AdverseActionReason(str, enum.Enum):
    """ECOA adverse action reason codes (Regulation B, 12 CFR 1002.9)"""
    CREDIT_SCORE = "credit_score"
    DEBT_TO_INCOME = "debt_to_income"
    EMPLOYMENT_HISTORY = "employment_history"
    INSUFFICIENT_INCOME = "insufficient_income"
    COLLATERAL_VALUE = "collateral_value"
    INCOMPLETE_APPLICATION = "incomplete_application"
    RESIDENCY_STATUS = "residency_status"
    OTHER = "other"


# ============================================================================
# LOAN FEE MODEL (TRID Tolerance Tracking - Checks 2.3-2.4)
# ============================================================================

class LoanFee(Base):
    """Individual fee on a loan for TRID tolerance tracking.

    TRID (TILA-RESPA Integrated Disclosure) requires that fees disclosed on
    the Loan Estimate stay within tolerance categories when compared to the
    Closing Disclosure. This model tracks each fee line item with both LE
    and CD amounts to enable automated tolerance violation detection.

    Tolerance categories:
        - Zero tolerance: Fees cannot increase (origination, transfer taxes)
        - 10% tolerance: Aggregate increase capped at 10% of LE total
        - Unlimited: No cap (borrower-shopped services)
    """
    __tablename__ = "loan_fees"
    __table_args__ = (
        Index('ix_loan_fees_loan_id', 'loan_id'),
        Index('ix_loan_fees_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)

    fee_name = Column(String, nullable=False)
    fee_category = Column(String)  # origination, title, government, prepaids, etc.
    tolerance_category = Column(SQLEnum(ToleranceCategory), nullable=False)

    # LE amounts
    le_amount = Column(Numeric(12, 2), default=0)
    le_revision_amount = Column(Numeric(12, 2))
    le_revision_date = Column(DateTime)
    le_revision_reason = Column(String)  # Changed circumstance reason

    # CD amounts
    cd_amount = Column(Numeric(12, 2))

    # Tolerance tracking
    variance = Column(Numeric(12, 2))  # CD - LE amount
    cure_amount = Column(Numeric(12, 2))  # Amount lender must refund
    is_violation = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# DISCLOSURE EVENT MODEL (TRID Audit Trail - Checks 2.1-2.2, 2.6)
# ============================================================================

class DisclosureEvent(Base):
    """Tracks all disclosure delivery events for TRID audit trail.

    TRID requires:
        - Loan Estimate: Delivered within 3 business days of application
        - Closing Disclosure: Delivered at least 3 business days before consummation
        - Changed circumstance revisions must be documented

    This model provides a complete audit trail of when disclosures were
    prepared, sent, and acknowledged, enabling compliance deadline tracking.
    """
    __tablename__ = "disclosure_events"
    __table_args__ = (
        Index('ix_disclosure_events_loan_id', 'loan_id'),
        Index('ix_disclosure_events_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)

    disclosure_type = Column(SQLEnum(DisclosureType), nullable=False)

    # Delivery tracking
    prepared_at = Column(DateTime)
    sent_at = Column(DateTime, nullable=True)  # Nullable: pending disclosures have sent_at=None until delivered
    delivery_method = Column(String)  # email, mail, in_person, esign
    received_at = Column(DateTime)  # Borrower acknowledged/signed

    # Deadline calculation
    deadline_date = Column(Date)  # Computed deadline (3 business days from app or before closing)
    is_on_time = Column(Boolean)  # Was it delivered on time?
    business_days_used = Column(Integer)  # How many business days between trigger and delivery

    # Changed circumstance (for revised disclosures)
    change_reason = Column(String)  # rate_change, loan_amount_change, program_change, etc.
    change_description = Column(Text)

    # Document reference
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Audit
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# ADVERSE ACTION NOTICE MODEL (ECOA Compliance - Checks 2.7-2.8)
# ============================================================================

class AdverseActionNotice(Base):
    """Adverse action notices for ECOA compliance.

    Equal Credit Opportunity Act (ECOA) / Regulation B requires:
        - Notice within 30 days of denial
        - Specific reason codes for adverse action
        - Name/address of federal regulator
        - Creditor information

    This model tracks the full lifecycle of adverse action notices
    from denial through delivery and acknowledgment.
    """
    __tablename__ = "adverse_action_notices"
    __table_args__ = (
        Index('ix_adverse_action_loan_id', 'loan_id'),
        Index('ix_adverse_action_org_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    # Denial info
    denial_date = Column(Date, nullable=False)
    notice_deadline = Column(Date, nullable=False)  # 30 days from denial
    notice_sent_date = Column(Date)
    is_on_time = Column(Boolean)

    # Reason codes (ECOA requires specific reasons)
    primary_reason = Column(SQLEnum(AdverseActionReason), nullable=False)
    secondary_reasons = Column(JSON)  # List of additional reason codes
    reason_description = Column(Text)  # Human-readable explanation

    # Delivery
    delivery_method = Column(String)  # mail, email, both
    recipient_name = Column(String)
    recipient_address = Column(Text)

    # Regulatory fields
    creditor_name = Column(String)
    creditor_address = Column(Text)
    federal_regulator = Column(String)  # CFPB, OCC, etc.

    # Status
    status = Column(String, default="pending")  # pending, sent, acknowledged

    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# COMPLIANCE ALERT MODEL
# ============================================================================

class ComplianceAlert(Base):
    """Real-time compliance violation alerts.

    Generated automatically by the compliance engines (TRID, ECOA, HMDA)
    when deadlines are approaching or violations are detected. Provides
    a centralized view of all compliance issues needing attention.
    """
    __tablename__ = "compliance_alerts"
    __table_args__ = (
        Index('ix_compliance_alerts_loan_id', 'loan_id'),
        Index('ix_compliance_alerts_org_id', 'organization_id'),
        Index('ix_compliance_alerts_status', 'status'),
        # Performance indexes (added via add_performance_indexes migration)
        Index('ix_compliance_alerts_loan_status', 'loan_id', 'status'),
        Index('ix_compliance_alerts_org_severity', 'organization_id', 'severity'),
        Index('ix_compliance_alerts_org_type', 'organization_id', 'alert_type'),
        Index('ix_compliance_alerts_deadline', 'deadline_date'),
        Index(
            'ix_compliance_alerts_open_deadline',
            'organization_id', 'deadline_date',
            postgresql_where=text("status = 'open'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    alert_type = Column(String, nullable=False)  # trid_le_deadline, trid_cd_deadline, adverse_action_deadline, tolerance_violation, etc.
    severity = Column(String, nullable=False)  # critical, high, medium
    title = Column(String, nullable=False)
    description = Column(Text)

    # Deadline
    deadline_date = Column(Date)
    days_remaining = Column(Integer)

    # Resolution
    status = Column(String, default="open")  # open, acknowledged, resolved, expired
    resolved_at = Column(DateTime)
    resolved_by_id = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ToleranceCategory",
    "DisclosureType",
    "AdverseActionReason",
    "LoanFee",
    "DisclosureEvent",
    "AdverseActionNotice",
    "ComplianceAlert",
]
