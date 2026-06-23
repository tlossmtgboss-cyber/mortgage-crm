"""
Builder Application Models
==========================
Stores builder pre-approval applications submitted via the CMG Builder Portal
(static HTML on GitHub Pages). Each application links to a loan officer (via
User.slug) and optionally to a ReferralPartner record.

Tables:
    builder_applications — One row per builder submission
    builder_documents    — Files uploaded during the application (stored in S3)
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index,
    Numeric,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base


class BuilderApplication(Base):
    __tablename__ = "builder_applications"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    lo_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    partner_id = Column(Integer, ForeignKey("referral_partners.id"), nullable=True, index=True)

    # Submission auth
    submission_token = Column(String(512), nullable=False, unique=True, index=True)

    # Builder contact (from register.html)
    company_name = Column(String(255), nullable=False)
    ein = Column(String(20))
    contact_first = Column(String(100), nullable=False)
    contact_last = Column(String(100), nullable=False)
    contact_email = Column(String(255), nullable=False, index=True)
    contact_phone = Column(String(20))

    # Full application data (9-step form from application.html)
    application_data = Column(JSONB, default=dict)

    # E-signature audit trail (from review.html)
    signature_data = Column(JSONB, default=dict)

    # Status workflow
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    # DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED | REJECTED

    review_notes = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True))

    submitted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    documents = relationship("BuilderDocument", back_populates="application", lazy="selectin")

    __table_args__ = (
        Index("ix_builder_app_org_status", "organization_id", "status"),
    )


class BuilderDocument(Base):
    __tablename__ = "builder_documents"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("builder_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    doc_type = Column(String(100), nullable=False)
    file_name = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_key = Column(String(1024), nullable=False)

    status = Column(String(30), nullable=False, default="UPLOADED")
    # UPLOADED -> REVIEWING -> APPROVED | REJECTED

    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    application = relationship("BuilderApplication", back_populates="documents")
