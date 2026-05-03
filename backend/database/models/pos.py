"""
POS (Point-of-Sale) URLA 1003 application models.

These tables hold borrower-side DRAFT state. They are deliberately separate
from the canonical BorrowerApplication store so that:

  - borrower autosaves don't contend with LO-side edits
  - URLA panel schemas can evolve without canonical-store migrations
  - submission is an atomic event with the full payload, not partial writes

On submit, a POS_APPLICATION_SUBMITTED event is emitted with the full
payload. An existing handler is responsible for mapping fields into
BorrowerApplication.

Author: perennia-pos-1003 skill v1.0.0
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

# Project-local imports — match Perennia's existing model conventions.
from db import Base
from encryption_utils import EncryptedString


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class POSStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ABANDONED = "abandoned"
    WITHDRAWN = "withdrawn"

    ALL = (DRAFT, SUBMITTED, ABANDONED, WITHDRAWN)


class POSSectionKey:
    INTAKE = "intake"
    PERSONAL = "personal"
    RESIDENCE = "residence"
    EMPLOYMENT = "employment"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    REO = "reo"
    LOAN = "loan"
    DECLARATIONS = "declarations"
    REVIEW = "review"

    # Source of truth for ordering and the step count shown to the borrower.
    # intake is excluded — it's a pre-screen, not a numbered step.
    ORDERED = (
        PERSONAL,
        RESIDENCE,
        EMPLOYMENT,
        ASSETS,
        LIABILITIES,
        REO,
        LOAN,
        DECLARATIONS,
        REVIEW,
    )

    # All valid section keys (includes pre-screen sections not in ORDERED).
    ALL_VALID = ORDERED + (INTAKE,)


class POSAuditEvent:
    APPLICATION_CREATED = "application.created"
    SECTION_UPDATED = "section.updated"
    SECTION_COMPLETED = "section.completed"
    APPLICATION_SUBMITTED = "application.submitted"
    APPLICATION_ABANDONED = "application.abandoned"
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    AI_QA_ASKED = "ai_qa.asked"


class AIQAConfidence:
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ESCALATE = "escalate"  # Aria deferred to LO


# ---------------------------------------------------------------------------
# Application root
# ---------------------------------------------------------------------------

class POSApplication(Base):
    """One row per (borrower, loan) URLA in progress."""

    __tablename__ = "pos_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-tenant scoping (matches Perennia's standard tenant model).
    organization_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)

    # Borrower identity (PURL contact_id) and loan linkage.
    contact_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(
        Integer,
        ForeignKey("loans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Lifecycle.
    status = Column(String(32), nullable=False, default=POSStatus.DRAFT, index=True)
    current_step = Column(String(32), nullable=False, default=POSSectionKey.PERSONAL)
    completion_pct = Column(Integer, nullable=False, default=0)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Source attribution — which entry point started this application.
    # Useful for funnel analysis later.
    source_channel = Column(String(64), nullable=True)  # 'purl_email', 'sms_invite', 'self_serve', etc.

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships.
    sections = relationship(
        "POSApplicationSection",
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    pii = relationship(
        "POSApplicationPII",
        back_populates="application",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="joined",
    )
    audit_events = relationship(
        "POSApplicationAudit",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="POSApplicationAudit.created_at.desc()",
    )
    qa_messages = relationship(
        "POSAIQAMessage",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="POSAIQAMessage.created_at.asc()",
    )

    __table_args__ = (
        # A borrower can have one in-progress draft per loan at a time.
        # Submitted/abandoned drafts can coexist for history.
        Index(
            "ix_pos_app_one_active_per_loan",
            "contact_id",
            "loan_id",
            unique=True,
            postgresql_where=(status == POSStatus.DRAFT),  # type: ignore[arg-type]
        ),
        Index("ix_pos_app_status_updated", "status", "updated_at"),
        Index("ix_pos_app_org_status", "organization_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<POSApplication id={self.id} contact={self.contact_id} "
            f"loan={self.loan_id} status={self.status} pct={self.completion_pct}>"
        )


# ---------------------------------------------------------------------------
# Section data (JSONB per section for fast partial saves)
# ---------------------------------------------------------------------------

class POSApplicationSection(Base):
    """One row per (application, section). JSONB body holds the URLA fields."""

    __tablename__ = "pos_application_sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pos_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_key = Column(String(32), nullable=False)  # e.g. 'personal'
    data: Any = Column(JSONB, nullable=False, default=dict)

    is_complete = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    application = relationship("POSApplication", back_populates="sections")

    __table_args__ = (
        UniqueConstraint("application_id", "section_key", name="uq_pos_section"),
    )


# ---------------------------------------------------------------------------
# PII (separate table — narrower access in audit and easier rotation)
# ---------------------------------------------------------------------------

class POSApplicationPII(Base):
    """Sensitive fields kept off the JSONB section blob."""

    __tablename__ = "pos_application_pii"

    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pos_applications.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # SSN columns use the shared EncryptedString TypeDecorator
    # (Fernet AES-128 CBC + HMAC, key from DATA_ENCRYPTION_KEY).
    ssn_encrypted = Column(EncryptedString, nullable=True)
    co_ssn_encrypted = Column(EncryptedString, nullable=True)

    # Date of birth — stored unencrypted (low sensitivity, queryable for age checks).
    dob = Column(Date, nullable=True)
    co_dob = Column(Date, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    application = relationship("POSApplication", back_populates="pii")


# ---------------------------------------------------------------------------
# Audit (every borrower-side action gets a row)
# ---------------------------------------------------------------------------

class POSApplicationAudit(Base):
    """ECOA / TRID compliance trail for every borrower-side action."""

    __tablename__ = "pos_application_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pos_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    actor_type = Column(String(16), nullable=False)  # 'borrower' | 'lo' | 'system'
    actor_id = Column(Integer, nullable=True)  # contact_id or user_id

    event_type = Column(String(64), nullable=False, index=True)
    section_key = Column(String(32), nullable=True)
    delta: Any = Column(JSONB, nullable=True)  # what changed; NEVER includes raw PII

    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    application = relationship("POSApplication", back_populates="audit_events")


# ---------------------------------------------------------------------------
# AI Q&A messages (conversation history with Aria)
# ---------------------------------------------------------------------------

class POSAIQAMessage(Base):
    """Conversation log between the borrower and Aria for this application."""

    __tablename__ = "pos_ai_qa_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pos_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role = Column(String(16), nullable=False)  # 'borrower' | 'aria'
    content = Column(Text, nullable=False)

    # Sources cited for Aria responses (None for borrower turns).
    # Schema: [{"type": "loan_file"|"guideline", "label": str, "anchor": str|None}]
    sources: Any = Column(JSONB, nullable=True)

    # Suggested follow-up questions (None for borrower turns).
    follow_ups: Any = Column(JSONB, nullable=True)

    # Telemetry.
    latency_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    confidence = Column(String(16), nullable=True)  # AIQAConfidence

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    application = relationship("POSApplication", back_populates="qa_messages")

    __table_args__ = (
        Index("ix_ai_qa_app_created", "application_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def calculate_completion_pct(sections_complete: int, total_sections: int = None) -> int:
    """Return integer 0..100 completion percentage."""
    if total_sections is None:
        total_sections = len(POSSectionKey.ORDERED)
    if total_sections <= 0:
        return 0
    return int(round((sections_complete / total_sections) * 100))
