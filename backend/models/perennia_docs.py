"""
Perennia Docs AI - Document Management System Models

SQLAlchemy models for AI-powered mortgage document collection and verification.

Tables defined:
- DocumentRequest: Document requests tied to loans
- Document: Uploaded documents with AI classification
- TemplatePack: Reusable document requirement templates
- DocumentRule: Automated rules for document processing
- DocumentEvent: Audit trail for all document activities
- NotificationOutbox: Queued notifications with quiet hours
- RetentionPolicy: Document retention and archival rules

Enum types:
- DocumentStatus, RequestStatus, RequestPriority
- ClassificationStatus, VirusScanStatus
- NotificationChannel, NotificationStatus
- EventType, ActorType
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Index, CheckConstraint, UniqueConstraint, Enum as SQLEnum,
    BigInteger
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class DocumentStatus(str, enum.Enum):
    """Document lifecycle status"""
    PENDING_UPLOAD = "pending_upload"   # Awaiting file upload
    UPLOADED = "uploaded"               # File received, pending scan
    SCANNING = "scanning"               # Virus scan in progress
    PROCESSING = "processing"           # AI classification in progress
    APPROVED = "approved"               # Verified and approved
    REJECTED = "rejected"               # Failed validation
    EXPIRED = "expired"                 # Document has expired


class RequestStatus(str, enum.Enum):
    """Document request status"""
    PENDING = "pending"         # No documents uploaded yet
    IN_PROGRESS = "in_progress" # Some documents uploaded
    COMPLETE = "complete"       # All required docs received
    OVERDUE = "overdue"         # Past due date


class RequestPriority(str, enum.Enum):
    """Document request priority"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ClassificationStatus(str, enum.Enum):
    """AI classification status"""
    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class VirusScanStatus(str, enum.Enum):
    """Antivirus scan status"""
    PENDING = "pending"
    SCANNING = "scanning"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"


class NotificationChannel(str, enum.Enum):
    """Notification delivery channel"""
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, enum.Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"


class EventType(str, enum.Enum):
    """Document event types for audit trail"""
    # Document lifecycle
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_SCANNED = "document_scanned"
    DOCUMENT_CLASSIFIED = "document_classified"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"
    DOCUMENT_EXPIRED = "document_expired"

    # Request lifecycle
    REQUEST_CREATED = "request_created"
    REQUEST_UPDATED = "request_updated"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_REMINDER_SENT = "request_reminder_sent"

    # System events
    CHECKLIST_GENERATED = "checklist_generated"
    VIRUS_DETECTED = "virus_detected"
    RULE_EXECUTED = "rule_executed"
    TEMPLATE_APPLIED = "template_applied"

    # AI events
    AI_CLASSIFICATION = "ai_classification"
    AI_QUALITY_CHECK = "ai_quality_check"
    AI_CROSS_VALIDATION = "ai_cross_validation"


class ActorType(str, enum.Enum):
    """Actor types for audit trail"""
    BORROWER = "borrower"
    LO = "lo"           # Loan Officer
    PROCESSOR = "processor"
    SYSTEM = "system"
    AI = "ai"


class DocType(str, enum.Enum):
    """Standard document types"""
    # Income
    PAYSTUB = "paystub"
    W2 = "w2"
    TAX_RETURN = "tax_return"
    PROFIT_LOSS = "profit_loss"
    EMPLOYMENT_VERIFICATION = "employment_verification"

    # Assets
    BANK_STATEMENT = "bank_statement"
    INVESTMENT_STATEMENT = "investment_statement"
    GIFT_LETTER = "gift_letter"

    # Property
    PURCHASE_CONTRACT = "purchase_contract"
    APPRAISAL = "appraisal"
    TITLE = "title"
    INSURANCE = "insurance"
    HOA = "hoa"

    # Identity
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"
    SSN_CARD = "ssn_card"

    # Credit
    CREDIT_REPORT = "credit_report"
    CREDIT_EXPLANATION = "credit_explanation"
    BANKRUPTCY_DOCS = "bankruptcy_docs"

    # Other
    OTHER = "other"


# =============================================================================
# MODEL FACTORY
# =============================================================================

from model_cache import base_memoize


@base_memoize
def create_perennia_docs_models(Base):
    """
    Factory function to create Perennia Docs AI models with the provided SQLAlchemy Base.

    This follows the established pattern to avoid circular imports.
    """

    class DocumentRequest(Base):
        """
        Document request tied to a loan.
        Represents a single document requirement that borrowers need to fulfill.
        """
        __tablename__ = 'perennia_document_requests'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Foreign keys
        loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False, index=True)
        lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True, index=True)
        template_pack_id = Column(Integer, ForeignKey('perennia_template_packs.id'), nullable=True)

        # Document type info
        doc_type = Column(String(50), nullable=False)  # PAYSTUB, BANK_STATEMENT, etc.
        doc_subtype = Column(String(50), nullable=True)  # PAYSTUB_BIWEEKLY, etc.
        title = Column(String(255), nullable=False)  # "Recent Paystub"
        description = Column(Text, nullable=True)  # "Upload your 2 most recent paystubs"

        # Requirements
        quantity = Column(Integer, default=1)  # Number of docs needed
        status = Column(String(20), default=RequestStatus.PENDING.value)
        priority = Column(String(20), default=RequestPriority.NORMAL.value)

        # Expiration handling
        expiration_date = Column(DateTime(timezone=True), nullable=True)
        expiration_threshold = Column(Integer, default=90)  # Days before expiration

        # Template tracking
        template_pack_version = Column(String(20), nullable=True)

        # Reminder configuration
        reminder_schedule = Column(JSONB, nullable=True)  # [1, 3, 7] = day offsets
        last_reminder_sent = Column(DateTime(timezone=True), nullable=True)
        reminder_count = Column(Integer, default=0)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Indexes
        __table_args__ = (
            Index('idx_doc_request_status', 'status'),
            Index('idx_doc_request_expiration', 'expiration_date'),
            Index('idx_doc_request_doc_type', 'doc_type'),
        )

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'loan_id': self.loan_id,
                'lead_id': self.lead_id,
                'doc_type': self.doc_type,
                'doc_subtype': self.doc_subtype,
                'title': self.title,
                'description': self.description,
                'quantity': self.quantity,
                'status': self.status,
                'priority': self.priority,
                'expiration_date': self.expiration_date.isoformat() if self.expiration_date else None,
                'expiration_threshold': self.expiration_threshold,
                'reminder_schedule': self.reminder_schedule,
                'reminder_count': self.reminder_count,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }


    class PerenniaDocument(Base):
        """
        Uploaded document with AI classification and quality checks.
        Tracks the full lifecycle from upload through approval.
        """
        __tablename__ = 'perennia_documents'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Foreign keys
        loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False, index=True)
        lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True, index=True)
        request_id = Column(Integer, ForeignKey('perennia_document_requests.id'), nullable=True, index=True)
        borrower_id = Column(Integer, nullable=True)  # Link to borrower/lead
        uploaded_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

        # File metadata
        file_name = Column(String(500), nullable=False)
        file_size = Column(BigInteger, nullable=False)  # bytes
        mime_type = Column(String(100), nullable=False)

        # Storage keys (S3 paths)
        original_storage_key = Column(String(500), nullable=False)
        compressed_storage_key = Column(String(500), nullable=True)
        preview_storage_key = Column(String(500), nullable=True)

        # Compression info
        compression_ratio = Column(Numeric(5, 2), nullable=True)
        compression_method = Column(String(50), nullable=True)  # GHOSTSCRIPT, IMAGEMAGICK
        derivative_type = Column(String(20), default="ORIGINAL")  # ORIGINAL, COMPRESSED, PREVIEW

        # Status tracking
        status = Column(String(20), default=DocumentStatus.PENDING_UPLOAD.value)
        rejection_reason = Column(Text, nullable=True)

        # AI Classification
        classification_status = Column(String(20), default=ClassificationStatus.PENDING.value)
        doc_type = Column(String(50), nullable=True)  # AI-classified type
        doc_subtype = Column(String(50), nullable=True)  # AI-classified subtype
        classification_confidence = Column(Numeric(3, 2), nullable=True)  # 0.00 - 1.00
        extracted_data = Column(JSONB, nullable=True)  # AI-extracted fields
        validation_errors = Column(JSONB, nullable=True)  # QA issues found
        quality_checks = Column(JSONB, nullable=True)  # Quality check results

        # AI metadata
        ai_model = Column(String(50), nullable=True)  # gpt-4-turbo, claude-sonnet-4
        ai_prompt_hash = Column(String(64), nullable=True)  # For replay/audit
        retrieval_context_ids = Column(ARRAY(String), nullable=True)  # For grounded answers

        # Virus scan
        virus_scan_status = Column(String(20), default=VirusScanStatus.PENDING.value)
        virus_scan_result = Column(JSONB, nullable=True)

        # Document dates
        document_date = Column(DateTime(timezone=True), nullable=True)  # Extracted from doc
        expires_at = Column(DateTime(timezone=True), nullable=True)  # When doc becomes invalid

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Indexes
        __table_args__ = (
            Index('idx_document_status', 'status'),
            Index('idx_document_scan_status', 'virus_scan_status'),
            Index('idx_document_expires', 'expires_at'),
            Index('idx_document_doc_type', 'doc_type'),
        )

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'loan_id': self.loan_id,
                'lead_id': self.lead_id,
                'request_id': self.request_id,
                'file_name': self.file_name,
                'file_size': self.file_size,
                'mime_type': self.mime_type,
                'status': self.status,
                'rejection_reason': self.rejection_reason,
                'classification_status': self.classification_status,
                'doc_type': self.doc_type,
                'doc_subtype': self.doc_subtype,
                'classification_confidence': float(self.classification_confidence) if self.classification_confidence else None,
                'extracted_data': self.extracted_data,
                'validation_errors': self.validation_errors,
                'quality_checks': self.quality_checks,
                'virus_scan_status': self.virus_scan_status,
                'document_date': self.document_date.isoformat() if self.document_date else None,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None,
                'compression_ratio': float(self.compression_ratio) if self.compression_ratio else None,
                'has_preview': bool(self.preview_storage_key),
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }


    class TemplatePack(Base):
        """
        Reusable document requirement templates.
        Defines standard document checklists for different loan programs.
        """
        __tablename__ = 'perennia_template_packs'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Template info
        name = Column(String(255), nullable=False)  # "Conventional W2 Salaried v1"
        slug = Column(String(100), nullable=False)  # "conventional-w2-v1"
        description = Column(Text, nullable=True)
        version = Column(String(20), default="1")

        # Applicability
        loan_programs = Column(ARRAY(String), nullable=True)  # [CONVENTIONAL, FHA, VA]
        employment_types = Column(ARRAY(String), nullable=True)  # [W2, SELF_EMPLOYED]
        property_types = Column(ARRAY(String), nullable=True)  # [PRIMARY, INVESTMENT]

        # Configuration (document requirements + expiration rules)
        config = Column(JSONB, nullable=False)
        """
        config structure:
        {
            "documentRequirements": [
                {
                    "docType": "PAYSTUB",
                    "docSubtype": "BIWEEKLY",
                    "title": "Recent Paystub",
                    "description": "Upload your 2 most recent paystubs",
                    "quantity": 2,
                    "expirationThreshold": 30,
                    "required": true
                },
                ...
            ],
            "reminderSchedule": [1, 3, 7],
            "autoApproveRules": {...}
        }
        """

        # Status
        is_active = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Unique constraint
        __table_args__ = (
            UniqueConstraint('slug', 'version', name='uq_template_pack_slug_version'),
        )

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'name': self.name,
                'slug': self.slug,
                'description': self.description,
                'version': self.version,
                'loan_programs': self.loan_programs,
                'employment_types': self.employment_types,
                'property_types': self.property_types,
                'config': self.config,
                'is_active': self.is_active,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }


    class DocumentRule(Base):
        """
        Automated rules for document processing.
        Triggers actions based on document events.
        """
        __tablename__ = 'perennia_document_rules'

        id = Column(Integer, primary_key=True, autoincrement=True)

        name = Column(String(255), nullable=False)
        description = Column(Text, nullable=True)

        # Trigger
        trigger = Column(String(50), nullable=False)  # EVENT_TYPE

        # Conditions (all must pass for rule to fire)
        conditions = Column(JSONB, nullable=False)
        """
        conditions structure:
        [
            {"field": "doc_type", "operator": "equals", "value": "PAYSTUB"},
            {"field": "confidence", "operator": "greater_than", "value": 0.9}
        ]
        """

        # Actions (executed when rule fires)
        actions = Column(JSONB, nullable=False)
        """
        actions structure:
        [
            {"type": "AUTO_APPROVE", "params": {}},
            {"type": "CREATE_NOTIFICATION", "params": {"template": "DOCUMENT_APPROVED"}},
            {"type": "SEND_WEBHOOK", "params": {"url": "..."}}
        ]
        """

        priority = Column(Integer, default=100)  # Lower = higher priority
        is_active = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        __table_args__ = (
            Index('idx_rule_trigger', 'trigger'),
            Index('idx_rule_active', 'is_active'),
        )


    class DocumentEvent(Base):
        """
        Audit trail for all document-related activities.
        Immutable log of all events in the system.
        """
        __tablename__ = 'perennia_document_events'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Foreign keys (all optional - event may relate to any entity)
        loan_id = Column(Integer, ForeignKey('loans.id'), nullable=True, index=True)
        lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True, index=True)
        request_id = Column(Integer, ForeignKey('perennia_document_requests.id'), nullable=True, index=True)
        document_id = Column(Integer, ForeignKey('perennia_documents.id'), nullable=True, index=True)

        # Event info
        event_type = Column(String(50), nullable=False)
        event_data = Column(JSONB, nullable=True)

        # Actor info
        actor_type = Column(String(20), nullable=False)  # BORROWER, LO, SYSTEM, AI
        actor_id = Column(Integer, nullable=True)  # user_id if applicable

        # Timestamp (immutable)
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

        __table_args__ = (
            Index('idx_event_type', 'event_type'),
            Index('idx_event_created', 'created_at'),
        )


    class DocumentNotification(Base):
        """
        Queued notifications for document-related activities.
        Supports quiet hours and scheduled delivery.
        """
        __tablename__ = 'perennia_notifications'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Foreign keys
        loan_id = Column(Integer, ForeignKey('loans.id'), nullable=True)
        lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True)

        # Recipient
        recipient_email = Column(String(255), nullable=True)
        recipient_phone = Column(String(20), nullable=True)
        recipient_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

        # Channel and template
        channel = Column(String(10), nullable=False)  # EMAIL, SMS
        template = Column(String(50), nullable=False)  # DOCUMENT_REMINDER, APPROVAL, etc.

        # Content
        subject = Column(String(500), nullable=True)  # For emails
        body = Column(Text, nullable=False)
        notification_data = Column(JSONB, nullable=True)  # Additional context (renamed from 'metadata' - reserved)

        # Delivery status
        status = Column(String(20), default=NotificationStatus.PENDING.value)
        sent_at = Column(DateTime(timezone=True), nullable=True)
        failure_reason = Column(Text, nullable=True)

        # Quiet hours (borrower timezone)
        quiet_hours_start = Column(String(5), default="21:00")  # 9 PM
        quiet_hours_end = Column(String(5), default="08:00")  # 8 AM
        scheduled_for = Column(DateTime(timezone=True), nullable=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        __table_args__ = (
            Index('idx_notification_status', 'status'),
            Index('idx_notification_scheduled', 'scheduled_for'),
        )


    class RetentionPolicy(Base):
        """
        Document retention and archival rules.
        Defines how long documents are kept and when they're archived.
        """
        __tablename__ = 'perennia_retention_policies'

        id = Column(Integer, primary_key=True, autoincrement=True)

        name = Column(String(255), nullable=False)
        description = Column(Text, nullable=True)

        # Applicability
        doc_types = Column(ARRAY(String), nullable=True)  # [PAYSTUB, BANK_STATEMENT] or ["*"]

        # Retention rules
        retention_years = Column(Integer, default=3)  # Years to keep
        archive_after_days = Column(Integer, default=365)  # Days before moving to cold storage

        # Status
        is_active = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))


    class BorrowerPortalSession(Base):
        """
        Magic link session for borrower portal access.
        Tracks active sessions and token expiration.
        """
        __tablename__ = 'perennia_portal_sessions'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Session info
        lead_id = Column(Integer, ForeignKey('leads.id'), nullable=False, index=True)
        loan_id = Column(Integer, ForeignKey('loans.id'), nullable=True, index=True)

        # Token
        magic_link_token = Column(String(255), unique=True, nullable=False, index=True)
        token_expires_at = Column(DateTime(timezone=True), nullable=False)

        # Session tracking
        session_expires_at = Column(DateTime(timezone=True), nullable=True)
        last_activity_at = Column(DateTime(timezone=True), nullable=True)
        ip_address = Column(String(45), nullable=True)
        user_agent = Column(String(500), nullable=True)

        # Status
        is_active = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


    # Return all models
    return {
        'DocumentRequest': DocumentRequest,
        'PerenniaDocument': PerenniaDocument,
        'Document': PerenniaDocument,  # Alias for backwards compatibility
        'TemplatePack': TemplatePack,
        'DocumentRule': DocumentRule,
        'DocumentEvent': DocumentEvent,
        'DocumentNotification': DocumentNotification,
        'RetentionPolicy': RetentionPolicy,
        'BorrowerPortalSession': BorrowerPortalSession,
    }


# =============================================================================
# STANDALONE USAGE (for migrations)
# =============================================================================

if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.ext.declarative import declarative_base
    import os

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    engine = create_engine(DATABASE_URL)
    Base = declarative_base()

    models = create_perennia_docs_models(Base)
    Base.metadata.create_all(engine)
    print("Perennia Docs AI tables created successfully!")
