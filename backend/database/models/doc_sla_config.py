"""
Smart Docs SLA Configuration & Tracking Models

Per-organization SLA definitions for document operations (classification, review,
income calculation, condition clearance, borrower response, package generation,
signing completion) with business-hours-aware tracking, pause/resume, and
escalation chain support.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Float,
    ForeignKey, Index, Numeric,
)
from db import Base


def utcnow():
    return datetime.now(timezone.utc)


class DocSLAConfig(Base):
    """Per-org SLA definition for a specific document operation type."""
    __tablename__ = "smart_docs_sla_configs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    sla_name = Column(String(200), nullable=False)
    sla_type = Column(String(50), nullable=False)
    # SLA types:
    #   DOC_CLASSIFICATION     - AI document classification
    #   DOC_REVIEW             - Human document review / approval
    #   INCOME_CALCULATION     - Income calculation completion
    #   CONDITION_CLEARANCE    - Underwriting condition clearance
    #   BORROWER_RESPONSE      - Borrower document submission response
    #   PACKAGE_GENERATION     - Submission package generation
    #   SIGNING_COMPLETION     - E-signature completion by all parties
    target_hours = Column(Float, nullable=False)  # SLA target in business hours
    warning_threshold_pct = Column(Numeric(8, 5), default=75.0)  # Warn at this % of SLA
    business_hours_only = Column(Boolean, default=True)
    business_hours_start = Column(Integer, default=8)   # 8 AM
    business_hours_end = Column(Integer, default=18)     # 6 PM
    exclude_weekends = Column(Boolean, default=True)
    exclude_holidays = Column(Boolean, default=True)
    escalation_enabled = Column(Boolean, default=True)
    escalation_chain = Column(JSON)
    # Example:
    # [
    #   {"at_pct": 75,  "notify": "processor"},
    #   {"at_pct": 100, "notify": "manager"},
    #   {"at_pct": 150, "notify": "branch_manager"},
    #   {"at_pct": 200, "notify": "vp_operations"},
    # ]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class DocSLATracking(Base):
    """Individual SLA timer instance for a specific entity (document, condition, etc.)."""
    __tablename__ = "smart_docs_sla_tracking"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    sla_config_id = Column(Integer, ForeignKey("smart_docs_sla_configs.id"), nullable=False)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    document_id = Column(Integer, nullable=True)
    entity_type = Column(String(50))   # document, income_calc, condition, package, signing
    entity_id = Column(Integer)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, MET, BREACHED, PAUSED, CANCELLED
    started_at = Column(DateTime, nullable=False)
    target_at = Column(DateTime, nullable=False)   # When SLA expires (computed from business hours)
    warning_at = Column(DateTime)                   # When warning triggers
    completed_at = Column(DateTime)
    elapsed_business_hours = Column(Float)
    breached = Column(Boolean, default=False)
    paused_at = Column(DateTime)
    pause_reason = Column(String(200))
    total_paused_hours = Column(Float, default=0.0)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    escalation_level = Column(Integer, default=0)   # Current escalation level reached
    last_escalation_at = Column(DateTime)
    exempted = Column(Boolean, default=False)
    exemption_reason = Column(String(200))
    exempted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_sla_tracking_org_status", "organization_id", "status"),
        Index("ix_sla_tracking_target", "status", "target_at"),
        Index("ix_sla_tracking_loan", "loan_id", "status"),
    )
