"""
Decision Audit Trail Models

Immutable audit log for every significant decision made on mortgage documents,
income calculations, fraud alerts, and compliance actions. Designed for
regulatory retention (7-year default, 3-year TRID minimum) and SOC 2 compliance.

Models:
    - DecisionAuditLog: Append-only record of every decision (human, system, AI)
    - AuditRetentionConfig: Per-organization retention policy configuration

Critical design constraints:
    - DecisionAuditLog is APPEND-ONLY — no UPDATE or DELETE operations
    - Minimum retention is 3 years (TRID requirement, 12 CFR 1026.25)
    - Default retention is 7 years (matches IRS record-keeping guidance)
    - Expired records are archived, never deleted

Usage:
    from database.models.decision_audit import (
        DecisionAuditLog,
        AuditRetentionConfig,
    )

    # Log a document review decision
    entry = DecisionAuditLog(
        organization_id=org_id,
        loan_id=loan_id,
        decision_type="document_review",
        entity_type="smart_document",
        entity_id=doc_id,
        decision="approved",
        decision_maker_type="user",
        decision_maker_id=user_id,
        decision_maker_name="Jane Smith",
        reasoning="Paystub matches W-2 income within 5% tolerance",
        supporting_data={"confidence": 0.95, "variance_pct": 3.2},
        previous_state="pending_review",
        new_state="approved",
    )
    db.add(entry)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
    Index,
)

from db import Base


# =============================================================================
# DECISION AUDIT LOG — APPEND-ONLY
# =============================================================================

class DecisionAuditLog(Base):
    """Immutable audit trail for every decision in the mortgage workflow.

    Captures the full context of decisions: who made it, why, what changed,
    and supporting evidence. This table is APPEND-ONLY — rows are never
    updated or deleted. Expired records are moved to an archive table by
    the retention service.

    Decision types include:
        - document_review: Human or AI review of uploaded documents
        - income_calculation: Automated or manual income computation
        - income_approval: Approval/rejection of calculated income
        - fraud_alert: Fraud detection system flagging or clearing
        - followup_escalation: Escalation of overdue follow-ups
        - auto_classification: AI document type classification
        - esign_action: E-signature send, sign, decline, void actions

    Decision maker types:
        - user: Human user (decision_maker_id references users.id)
        - system: Automated rule or cron task
        - ai_agent: AI agent (decision_maker_name captures agent name)
    """
    __tablename__ = "decision_audit_logs"
    __table_args__ = (
        Index(
            "ix_decision_audit_org_loan",
            "organization_id", "loan_id",
        ),
        Index(
            "ix_decision_audit_org_type_created",
            "organization_id", "decision_type", "created_at",
        ),
        Index(
            "ix_decision_audit_entity",
            "entity_type", "entity_id",
        ),
        Index(
            "ix_decision_audit_created_at",
            "created_at",
        ),
        Index(
            "ix_decision_audit_maker",
            "decision_maker_type", "decision_maker_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant isolation — every audit record belongs to an organization
    organization_id = Column(Integer, nullable=False, index=True)  # ref organizations.id

    # Loan context (most decisions relate to a loan)
    loan_id = Column(Integer, nullable=True)  # ref loans.id — nullable for org-level decisions

    # Document context (optional — set when decision is about a specific document)
    document_id = Column(Integer, nullable=True)  # ref documents.id or smart_documents.id

    # What kind of decision
    decision_type = Column(String(64), nullable=False)
    # Allowed: document_review, income_calculation, income_approval,
    #          fraud_alert, followup_escalation, auto_classification, esign_action

    # What entity this decision applies to
    entity_type = Column(String(64), nullable=False)  # e.g. smart_document, loan, lead, esignature_envelope
    entity_id = Column(Integer, nullable=False)

    # The decision itself
    decision = Column(String(32), nullable=False)
    # Allowed: approved, rejected, needs_review, escalated, auto_approved, auto_rejected

    # Who made the decision
    decision_maker_type = Column(String(20), nullable=False)  # user, system, ai_agent
    decision_maker_id = Column(Integer, nullable=True)  # ref users.id for human decisions
    decision_maker_name = Column(String(255), nullable=True)  # Display name, captures AI agent name

    # Why — narrative explanation is mandatory for audit compliance
    reasoning = Column(Text, nullable=False)

    # Machine-readable evidence and context
    supporting_data = Column(JSON, nullable=True)
    # Examples:
    #   {"quality_score": 0.92, "fraud_indicators": [], "confidence": 0.95}
    #   {"rule_name": "auto_approve_high_confidence", "threshold": 0.90}
    #   {"variance_pct": 3.2, "w2_income": 85000, "paystub_annualized": 87550}

    # State transition
    previous_state = Column(String(32), nullable=True)  # what the entity was before
    new_state = Column(String(32), nullable=False)  # what the entity became

    # Request context for human decisions
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)

    # Immutable timestamp — no updated_at by design
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# =============================================================================
# AUDIT RETENTION CONFIG — PER-ORGANIZATION
# =============================================================================

class AuditRetentionConfig(Base):
    """Per-organization retention policy for audit records.

    Controls how long different categories of audit records are kept before
    being archived to cold storage. Enforces regulatory minimums:
        - TRID requires 3 years minimum (12 CFR 1026.25)
        - Default is 7 years (IRS record-keeping guidance for mortgage lenders)

    The min_retention_days field (default 1095 = 3 years) acts as a hard floor
    that cannot be reduced. Any attempt to set retention below this floor
    is rejected by the service layer.
    """
    __tablename__ = "audit_retention_configs"
    __table_args__ = (
        Index(
            "ix_audit_retention_org_unique",
            "organization_id",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # One config per organization
    organization_id = Column(Integer, nullable=False, unique=True, index=True)  # ref organizations.id

    # Retention periods in days
    # 2555 days = ~7 years (7 * 365 = 2555)
    default_retention_days = Column(Integer, nullable=False, default=2555)
    document_retention_days = Column(Integer, nullable=False, default=2555)
    esign_retention_days = Column(Integer, nullable=False, default=2555)
    followup_retention_days = Column(Integer, nullable=False, default=2555)

    # Hard floor — cannot set any retention below this (TRID minimum)
    # 1095 days = 3 years
    min_retention_days = Column(Integer, nullable=False, default=1095)

    # Whether to archive expired records to cold storage (S3 Glacier, etc.)
    archive_to_cold_storage = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# =============================================================================
# ARCHIVED DECISION AUDIT LOG
# =============================================================================

class ArchivedDecisionAuditLog(Base):
    """Cold-storage archive for expired decision audit records.

    Records are moved here by the retention service when they exceed the
    configured retention period. This table has the same schema as
    DecisionAuditLog plus an archived_at timestamp. Records in this table
    are kept indefinitely (or until manual purge with executive approval).
    """
    __tablename__ = "archived_decision_audit_logs"
    __table_args__ = (
        Index(
            "ix_archived_audit_org_loan",
            "organization_id", "loan_id",
        ),
        Index(
            "ix_archived_audit_created_at",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Mirrored from DecisionAuditLog
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=True)
    document_id = Column(Integer, nullable=True)
    decision_type = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Integer, nullable=False)
    decision = Column(String(32), nullable=False)
    decision_maker_type = Column(String(20), nullable=False)
    decision_maker_id = Column(Integer, nullable=True)
    decision_maker_name = Column(String(255), nullable=True)
    reasoning = Column(Text, nullable=False)
    supporting_data = Column(JSON, nullable=True)
    previous_state = Column(String(32), nullable=True)
    new_state = Column(String(32), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Original creation timestamp (preserved from source record)
    created_at = Column(DateTime, nullable=False)

    # When this record was archived
    archived_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Original ID from decision_audit_logs for traceability
    original_audit_id = Column(Integer, nullable=True, index=True)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "DecisionAuditLog",
    "AuditRetentionConfig",
    "ArchivedDecisionAuditLog",
]
