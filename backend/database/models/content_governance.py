"""
Marketing Content Governance Models

Enterprise-grade approval workflow for marketing materials. Ensures all
content distributed to borrowers and prospects has passed compliance review
before use, satisfying enterprise lender audit requirements.

Models:
    - ContentTemplate: Versioned marketing content with full lifecycle status
    - ContentApproval: Immutable record of each reviewer decision (approved /
      rejected / revision_requested)
    - ContentUsageLog: Append-only log of every time an approved template is
      used for distribution

Usage:
    from database.models.content_governance import (
        ContentTemplate,
        ContentApproval,
        ContentUsageLog,
    )

    pending = db.query(ContentTemplate).filter(
        ContentTemplate.status == "pending_review",
        ContentTemplate.organization_id == org_id,
    ).all()
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import relationship

from db import Base
import enum


# =============================================================================
# ENUMS
# =============================================================================

class ContentType(str, enum.Enum):
    """Channel/format for a piece of marketing content."""
    EMAIL = "email"
    SMS = "sms"
    SOCIAL = "social"
    PRINT = "print"


class ContentStatus(str, enum.Enum):
    """Lifecycle stage of a content template.

    Allowed transitions:
        draft            -> pending_review   (submit-for-review)
        pending_review   -> approved         (approve)
        pending_review   -> rejected         (reject)
        pending_review   -> draft            (request-revision  — resets to draft for editing)
        approved         -> archived         (archive)
        rejected         -> draft            (creator edits and re-submits)
        draft            -> archived         (creator abandons)
    """
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ApprovalDecision(str, enum.Enum):
    """Decision recorded on a single ContentApproval row."""
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


# =============================================================================
# CONTENT TEMPLATE
# =============================================================================

class ContentTemplate(Base):
    """Marketing content template subject to compliance approval.

    A template may be created by any authenticated user (e.g., loan officer,
    marketing manager) but cannot be sent to recipients until a compliance
    reviewer has moved it to ``approved`` status.

    Each edit that occurs after rejection or a revision request creates a new
    ``updated_at`` timestamp; the approval history (ContentApproval rows) is
    preserved so auditors can see every decision made on the template.
    """
    __tablename__ = "content_templates"
    __table_args__ = (
        Index("ix_content_templates_org_id", "organization_id"),
        Index("ix_content_templates_status", "status"),
        Index("ix_content_templates_content_type", "content_type"),
        Index("ix_content_templates_created_by", "created_by"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Tenant isolation
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    # Content fields
    title = Column(String(500), nullable=False)
    content_type = Column(
        SQLEnum(ContentType, name="content_type_enum"),
        nullable=False,
    )
    subject_line = Column(String(998), nullable=True)   # RFC 2822 subject max; null for SMS/print
    body_html = Column(Text, nullable=True)              # Rich HTML body (email / print)
    body_text = Column(Text, nullable=True)              # Plain-text fallback or SMS body

    # Categorisation & discovery
    category = Column(String(200), nullable=True)        # e.g. "rate_promo", "post_close", "refi"
    tags = Column(JSON, nullable=True)                   # ["fair_housing", "purchase", "q1_2026"]

    # Workflow status
    status = Column(
        SQLEnum(ContentStatus, name="content_status_enum"),
        nullable=False,
        default=ContentStatus.DRAFT,
        index=True,
    )

    # Ownership
    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

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

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="content_templates_created")
    organization = relationship("Organization", backref="content_templates")
    approvals = relationship(
        "ContentApproval",
        back_populates="template",
        order_by="ContentApproval.created_at",
        cascade="all, delete-orphan",
    )
    usage_logs = relationship(
        "ContentUsageLog",
        back_populates="template",
        order_by="ContentUsageLog.used_at",
        cascade="all, delete-orphan",
    )


# =============================================================================
# CONTENT APPROVAL
# =============================================================================

class ContentApproval(Base):
    """Immutable record of a single reviewer action on a content template.

    One row is appended every time a compliance reviewer (or requestor)
    takes an action: approve, reject, or request-revision. Rows are never
    updated or deleted so the full decision audit trail is always available.

    Multiple ContentApproval rows may exist for a single template if the
    template goes through multiple review cycles (e.g., revised after
    rejection and re-submitted).
    """
    __tablename__ = "content_approvals"
    __table_args__ = (
        Index("ix_content_approvals_template_id", "template_id"),
        Index("ix_content_approvals_reviewer_id", "reviewer_id"),
        Index("ix_content_approvals_status", "status"),
        Index("ix_content_approvals_reviewed_at", "reviewed_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Foreign keys
    template_id = Column(
        String,
        ForeignKey("content_templates.id"),
        nullable=False,
        index=True,
    )
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Decision
    status = Column(
        SQLEnum(ApprovalDecision, name="approval_decision_enum"),
        nullable=False,
    )
    review_notes = Column(Text, nullable=True)  # Rationale / change requests

    # Timestamps
    reviewed_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    template = relationship("ContentTemplate", back_populates="approvals")
    reviewer = relationship("User", foreign_keys=[reviewer_id], backref="content_approvals_given")


# =============================================================================
# CONTENT USAGE LOG
# =============================================================================

class ContentUsageLog(Base):
    """Append-only log recording every use of an approved content template.

    A new row is written each time an approved template is used for a
    real distribution event (campaign send, bulk email, etc.).  Only
    ``approved`` templates may generate usage log entries; the route
    layer enforces this constraint.

    This table supports:
    - Audit queries: "which templates were used in Q1?"
    - Compliance reporting: volume per channel per template
    - Usage-based billing or throttling if needed in future
    """
    __tablename__ = "content_usage_logs"
    __table_args__ = (
        Index("ix_content_usage_logs_template_id", "template_id"),
        Index("ix_content_usage_logs_used_by", "used_by"),
        Index("ix_content_usage_logs_used_at", "used_at"),
        Index("ix_content_usage_logs_channel", "channel"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Foreign keys
    template_id = Column(
        String,
        ForeignKey("content_templates.id"),
        nullable=False,
        index=True,
    )
    used_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Usage context
    used_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    channel = Column(String(50), nullable=True)     # Actual dispatch channel: email, sms, print, social
    recipient_count = Column(Integer, nullable=False, default=0)

    # Optional reference back to the campaign or send event
    campaign_id = Column(Integer, nullable=True)     # FK to campaign_definitions if used in a campaign
    reference_id = Column(String, nullable=True)     # Arbitrary external reference (e.g. email send job ID)

    # Relationships
    template = relationship("ContentTemplate", back_populates="usage_logs")
    user = relationship("User", foreign_keys=[used_by], backref="content_usage_logs")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ContentType",
    "ContentStatus",
    "ApprovalDecision",
    "ContentTemplate",
    "ContentApproval",
    "ContentUsageLog",
]
