"""
Document Models

Document intake and management models for the mortgage CRM.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.document import Document, EmailIntake, AttachmentIntake

    # Query documents
    docs = db.query(Document).filter(Document.loan_id == loan_id).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base

# Import enums from the database package
from database.enums import (
    EmailIntakeMatchStatus,
    AttachmentClassificationStatus,
    DocumentType,
    DocumentCategory,
)


# ============================================================================
# EMAIL DOCUMENT INTAKE MODELS
# ============================================================================

class EmailIntake(Base):
    """
    Represents an inbound email with attachments for document intake.
    Created when docs@yourcrm.com receives an email.
    """
    __tablename__ = "email_intakes"
    __table_args__ = (
        Index('ix_email_intakes_match_status', 'match_status'),
        Index('ix_email_intakes_received_at', 'received_at'),
        Index('ix_email_intakes_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    from_email = Column(String, nullable=False, index=True)
    to_email = Column(String)
    cc_emails = Column(String)  # Comma-separated
    subject = Column(String)
    body_snippet = Column(Text)  # First 500 chars of body
    received_at = Column(DateTime, nullable=False)
    raw_message_id = Column(String, unique=True, index=True)  # Email Message-ID header
    in_reply_to = Column(String)  # For thread matching

    # Matching results
    matched_borrower_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    matched_loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    match_status = Column(SQLEnum(EmailIntakeMatchStatus), default=EmailIntakeMatchStatus.UNMATCHED)
    match_candidates = Column(JSON)  # List of potential matches if MULTIPLE

    # Processing status
    processing_status = Column(String, default="pending")  # pending, processed, error
    processing_error = Column(Text)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime)
    processed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    attachments = relationship("AttachmentIntake", back_populates="email_intake", cascade="all, delete-orphan")
    matched_borrower = relationship("Lead", foreign_keys=[matched_borrower_id])
    matched_loan = relationship("Loan", foreign_keys=[matched_loan_id])
    classification_task = relationship("Task", back_populates="email_intake", uselist=False)


class AttachmentIntake(Base):
    """
    Represents an attachment from an inbound email awaiting classification.
    """
    __tablename__ = "attachment_intakes"
    __table_args__ = (
        Index('ix_attachment_intakes_classification_status', 'classification_status'),
        Index('ix_attachment_intakes_email_intake_id', 'email_intake_id'),
        Index('ix_attachment_intakes_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    email_intake_id = Column(Integer, ForeignKey("email_intakes.id"), nullable=False)

    # File info
    filename = Column(String, nullable=False)
    original_filename = Column(String)  # Before sanitization
    file_size = Column(Integer)  # Bytes
    mime_type = Column(String)
    storage_location = Column(String)  # Temp storage path/URL

    # AI suggestions
    ai_suggested_doc_type = Column(String)
    ai_suggested_doc_category = Column(String)
    ai_suggested_borrower_id = Column(Integer, nullable=True)
    ai_suggested_loan_id = Column(Integer, nullable=True)
    ai_confidence = Column(Float)  # 0-1 confidence score
    ai_extracted_text = Column(Text)  # OCR text snippet for matching

    # Classification (filled by user)
    classification_status = Column(SQLEnum(AttachmentClassificationStatus), default=AttachmentClassificationStatus.PENDING)
    classified_doc_type = Column(SQLEnum(DocumentType), nullable=True)
    classified_doc_category = Column(SQLEnum(DocumentCategory), nullable=True)
    classified_borrower_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    classified_loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    period_start_date = Column(Date)  # For statements
    period_end_date = Column(Date)
    classification_notes = Column(Text)

    # When classified, becomes a Document
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Audit
    classified_at = Column(DateTime)
    classified_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    discarded_reason = Column(String)  # If discarded
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    email_intake = relationship("EmailIntake", back_populates="attachments")
    classified_borrower = relationship("Lead", foreign_keys=[classified_borrower_id])
    classified_loan = relationship("Loan", foreign_keys=[classified_loan_id])
    document = relationship("Document", back_populates="source_attachment")


class Document(Base):
    """
    A classified document attached to a borrower/loan.
    Created when an AttachmentIntake is classified.
    """
    __tablename__ = "documents"
    __table_args__ = (
        Index('ix_documents_borrower_id', 'borrower_id'),
        Index('ix_documents_loan_id', 'loan_id'),
        Index('ix_documents_doc_type', 'doc_type'),
        Index('ix_documents_organization_id', 'organization_id'),
        # Performance indexes (added via add_performance_indexes migration)
        Index('ix_documents_loan_status', 'loan_id', 'status'),
        Index('ix_documents_borrower_status', 'borrower_id', 'status'),
        Index('ix_documents_org_status', 'organization_id', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    borrower_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    # Document info
    doc_type = Column(SQLEnum(DocumentType), nullable=False)
    doc_category = Column(SQLEnum(DocumentCategory))
    filename = Column(String, nullable=False)
    original_filename = Column(String)
    file_size = Column(Integer)
    mime_type = Column(String)
    file_location = Column(String, nullable=False)  # Final storage path/URL

    # Period info (for statements)
    period_start_date = Column(Date)
    period_end_date = Column(Date)

    # Source tracking
    source = Column(String, default="EMAIL_INTAKE")  # EMAIL_INTAKE, MANUAL_UPLOAD, API
    source_email_intake_id = Column(Integer, ForeignKey("email_intakes.id"), nullable=True)

    # Status
    status = Column(String, default="active")  # active, archived, deleted
    notes = Column(Text)

    # Audit
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    borrower = relationship("Lead", foreign_keys=[borrower_id], backref="documents")
    loan = relationship("Loan", foreign_keys=[loan_id], backref="documents")
    source_email_intake = relationship("EmailIntake", foreign_keys=[source_email_intake_id])
    source_attachment = relationship("AttachmentIntake", back_populates="document", uselist=False)
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "EmailIntake",
    "AttachmentIntake",
    "Document",
]
