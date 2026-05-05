"""
Smart Document Collection Models

SQLAlchemy models for the intelligent document collection system:
- DocumentRequest: Tracks document requirements and needs list
- SmartDocument: Enhanced document with detection and freshness
- DocPolicyEvent: Event tracking for auto-renewal and compliance
- NeedsListTemplate: Configurable templates for document requirements
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, Enum as SQLEnum, Numeric, Index, func
)
from sqlalchemy.orm import validates
# Note: relationship import removed - using ID-based queries instead of ORM relationships

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class DocType(str, enum.Enum):
    """Document types for needs list"""
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    PAYSTUB = "PAYSTUB"
    W2 = "W2"
    TAX_RETURN = "TAX_RETURN"
    BUSINESS_TAX_RETURN = "BUSINESS_TAX_RETURN"
    PROFIT_LOSS = "PROFIT_LOSS"
    BALANCE_SHEET = "BALANCE_SHEET"
    BANK_STATEMENT = "BANK_STATEMENT"
    INVESTMENT_STATEMENT = "INVESTMENT_STATEMENT"
    GIFT_LETTER = "GIFT_LETTER"
    LOE = "LOE"  # Letter of Explanation
    LEASE_AGREEMENT = "LEASE_AGREEMENT"
    FHA_CERT = "FHA_CERT"
    VA_COE = "VA_COE"
    DD214 = "DD214"
    BANKRUPTCY_DISCHARGE = "BANKRUPTCY_DISCHARGE"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    APPRAISAL = "APPRAISAL"
    TITLE_REPORT = "TITLE_REPORT"
    HOMEOWNERS_INSURANCE = "HOMEOWNERS_INSURANCE"
    OTHER = "OTHER"


class RequestStatus(str, enum.Enum):
    """Status of a document request"""
    OPEN = "OPEN"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WAIVED = "WAIVED"


class RequestPriority(str, enum.Enum):
    """Priority level for document requests"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class AppliesTo(str, enum.Enum):
    """Who the document request applies to"""
    BORROWER = "BORROWER"
    CO_BORROWER = "CO_BORROWER"
    BOTH = "BOTH"


class PayrollFrequency(str, enum.Enum):
    """Payroll frequency for auto-renewal calculation"""
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    SEMIMONTHLY = "SEMIMONTHLY"
    MONTHLY = "MONTHLY"


class DocumentDecision(str, enum.Enum):
    """Automated review decision"""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RejectionCategory(str, enum.Enum):
    """Category of document rejection"""
    SCREENSHOT = "SCREENSHOT"
    EXPIRED = "EXPIRED"
    POOR_QUALITY = "POOR_QUALITY"
    INCOMPLETE = "INCOMPLETE"
    WRONG_TYPE = "WRONG_TYPE"
    OTHER = "OTHER"


class DocumentStatus(str, enum.Enum):
    """Valid statuses for SmartDocument lifecycle."""
    UPLOADED = "UPLOADED"
    SCANNING = "SCANNING"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"
    SUPERSEDED = "SUPERSEDED"
    UPLOAD_FAILED = "UPLOAD_FAILED"


# =============================================================================
# DOCUMENT STATUS TRANSITION RULES
# =============================================================================

_VALID_DOCUMENT_TRANSITIONS: dict = {
    DocumentStatus.UPLOADED: {
        DocumentStatus.SCANNING,
        DocumentStatus.PROCESSING,
        DocumentStatus.DELETED,
        DocumentStatus.UPLOAD_FAILED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.UPLOAD_FAILED: {
        DocumentStatus.UPLOADED,
        DocumentStatus.DELETED,
    },
    DocumentStatus.SCANNING: {
        DocumentStatus.PROCESSING,
        DocumentStatus.APPROVED,  # AI review can approve directly from SCANNING
        DocumentStatus.REJECTED,
        DocumentStatus.UPLOAD_FAILED,
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.PROCESSING: {
        DocumentStatus.SCANNING,  # AI review re-entry from batch_review
        DocumentStatus.PENDING_REVIEW,
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.PENDING_REVIEW: {
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.UPLOADED,  # Reprocess resets to UPLOADED
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.NEEDS_REVIEW: {
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
        DocumentStatus.PENDING_REVIEW,
        DocumentStatus.PROCESSING,  # AI review error fallback
        DocumentStatus.UPLOADED,  # Reprocess resets to UPLOADED
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.APPROVED: {
        DocumentStatus.EXPIRED,
        DocumentStatus.SUPERSEDED,
        DocumentStatus.DELETED,
        DocumentStatus.UPLOADED,  # Reprocess resets to UPLOADED
    },
    DocumentStatus.REJECTED: {
        DocumentStatus.UPLOADED,  # Re-upload or reprocess after rejection
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.EXPIRED: {
        DocumentStatus.UPLOADED,  # Re-upload after expiry
        DocumentStatus.DELETED,
        DocumentStatus.SUPERSEDED,
    },
    DocumentStatus.DELETED: set(),  # Terminal
    DocumentStatus.SUPERSEDED: set(),  # Terminal
}


def validate_document_status_transition(current_status: str, new_status: str) -> bool:
    """Check if a document status transition is valid. Returns True if valid."""
    if current_status == new_status:
        return True  # No-op transitions are always valid
    try:
        current = DocumentStatus(current_status)
        new = DocumentStatus(new_status)
    except ValueError:
        return True  # Don't block on unknown statuses
    return new in _VALID_DOCUMENT_TRANSITIONS.get(current, set())


class DocPolicyEventType(str, enum.Enum):
    """Types of policy events"""
    NEEDS_LIST_GENERATED = "NEEDS_LIST_GENERATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    AUTO_REQUEST_CREATED = "AUTO_REQUEST_CREATED"
    EXPIRED = "EXPIRED"
    EXPIRATION_REMINDER_SENT = "EXPIRATION_REMINDER_SENT"
    SCREENSHOT_REJECTED = "SCREENSHOT_REJECTED"
    FRESHNESS_REJECTED = "FRESHNESS_REJECTED"
    PORTAL_DOCUSIGN_REQUEST = "PORTAL_DOCUSIGN_REQUEST"


# =============================================================================
# MODELS
# =============================================================================

class DocumentRequest(Base):
    """
    Document request in needs list.
    Generated from application data and tracked through fulfillment.
    """
    __tablename__ = "smart_document_requests"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships (foreign keys omitted to allow isolated table creation)
    loan_id = Column(Integer, nullable=False)  # References loans.id - indexed in __table_args__
    borrower_id = Column(Integer, nullable=True)  # References borrower_profiles.id

    # Request details — native_enum=False avoids PG ENUM type mismatches
    doc_type = Column(SQLEnum(DocType, native_enum=False, create_type=False, length=100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)

    # Requirements
    required_count = Column(Integer, default=1, server_default="1")
    applies_to = Column(SQLEnum(AppliesTo, native_enum=False, create_type=False, length=50), default=AppliesTo.BORROWER)
    priority = Column(SQLEnum(RequestPriority, native_enum=False, create_type=False, length=50), default=RequestPriority.NORMAL)

    # Freshness policy
    freshness_days = Column(Integer, nullable=True)
    auto_renew = Column(Boolean, default=False)
    next_expected_available_at = Column(DateTime, nullable=True)
    payroll_frequency = Column(SQLEnum(PayrollFrequency, native_enum=False, create_type=False, length=50), nullable=True)

    # Status
    status = Column(SQLEnum(RequestStatus, native_enum=False, create_type=False, length=50), default=RequestStatus.OPEN)
    is_required = Column(Boolean, default=True, server_default="true")
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)  # When request was fulfilled (synced with completed_at)

    # E-sign
    requires_esign = Column(Boolean, default=False, server_default="false")

    # Portal metadata (e.g., DocuSign details, LOE instructions)
    # "metadata" is reserved by SQLAlchemy DeclarativeBase — use request_metadata
    request_metadata = Column("request_metadata", JSON, nullable=True)

    # SLA Tracking
    sla_due_at = Column(DateTime, nullable=True)  # 3 business days from created_at
    is_active = Column(Boolean, default=True)  # For superseding logic
    superseded_by = Column(Integer, nullable=True)  # FK to replacement request

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Note: Documents relationship accessed via SmartDocument.request_id queries

    # Indexes
    __table_args__ = (
        Index("ix_smart_doc_requests_loan_id", "loan_id"),
        Index("ix_smart_doc_requests_status", "status"),
        Index("ix_smart_doc_requests_auto_renew", "auto_renew"),
        Index("ix_smart_doc_requests_next_expected", "next_expected_available_at"),
        Index("ix_smart_doc_requests_sla_due", "sla_due_at"),
        Index("ix_smart_doc_requests_is_active", "is_active"),
    )


class SmartDocument(Base):
    """
    Enhanced document with detection results and freshness tracking.
    Extends basic document with screenshot detection, date extraction, and expiration.
    """
    __tablename__ = "smart_documents"

    id = Column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation (nullable for backfill of existing rows)
    organization_id = Column(Integer, nullable=True, index=True)  # TODO: backfill existing rows then set nullable=False

    # Relationships (foreign keys omitted to allow isolated table creation)
    request_id = Column(Integer, nullable=True)  # References smart_document_requests.id - indexed in __table_args__
    loan_id = Column(Integer, nullable=True)  # References loans.id - indexed in __table_args__
    borrower_id = Column(Integer, nullable=False)  # References borrower_profiles.id - indexed in __table_args__

    # File info
    file_name = Column(String(512), nullable=False)
    original_filename = Column(String(512), nullable=True)  # Original uploaded filename
    mime_type = Column(String(128), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=True, index=True)
    storage_key = Column(String(1024), nullable=False)  # S3 key
    page_count = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())  # When document was uploaded

    # Document type
    doc_type = Column(SQLEnum(DocType, native_enum=False, create_type=False, length=100), nullable=True)
    detected_doc_type = Column(String(64), nullable=True)  # AI-detected type

    # Screenshot detection
    detected_is_screenshot = Column(Boolean, default=False)
    screenshot_confidence = Column(Float, nullable=True)
    screenshot_reasons = Column(JSON, nullable=True)  # Array of detection layer results

    # Extracted data
    extracted_dates = Column(JSON, nullable=True)  # { payDate, periodEnd, statementEnd }
    extracted_names = Column(JSON, nullable=True)
    extracted_employer = Column(String(255), nullable=True)
    extracted_account_number = Column(String(64), nullable=True)
    extracted_amount = Column(Numeric(15, 2), nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    ocr_text = Column(Text, nullable=True)

    # Freshness validation
    doc_date = Column(DateTime, nullable=True)  # Primary date on document
    doc_expires_at = Column(DateTime, nullable=True)
    is_expired = Column(Boolean, default=False)
    days_until_expiration = Column(Integer, nullable=True)

    # Review decision
    status = Column(String(32), default="UPLOADED")  # UPLOADED, SCANNING, PROCESSING, APPROVED, REJECTED, EXPIRED
    decision = Column(SQLEnum(DocumentDecision, native_enum=False, create_type=False, length=50), nullable=True)
    decision_reasons = Column(JSON, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejection_category = Column(SQLEnum(RejectionCategory, native_enum=False, create_type=False, length=50), nullable=True)
    fix_instructions = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(64), nullable=True)  # 'SYSTEM' or user ID

    # Upload metadata
    upload_source = Column(String(32), nullable=True)  # WEB, MOBILE, EMAIL
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)

    # Review display info
    display_name = Column(String(255), nullable=True)  # User-editable document name
    assigned_owner = Column(String(20), nullable=True)  # BORROWER, CO_BORROWER

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Note: Request relationship accessed via request_id column

    # Indexes
    __table_args__ = (
        Index("ix_smart_documents_organization_id", "organization_id"),
        Index("ix_smart_documents_request_id", "request_id"),
        Index("ix_smart_documents_loan_id", "loan_id"),
        Index("ix_smart_documents_borrower_id", "borrower_id"),
        Index("ix_smart_documents_status", "status"),
        Index("ix_smart_documents_decision", "decision"),
        Index("ix_smart_documents_is_expired", "is_expired"),
        Index("ix_smart_documents_doc_expires_at", "doc_expires_at"),
        Index("ix_smart_documents_is_screenshot", "detected_is_screenshot"),
    )

    @validates('status')
    def validate_status(self, key, value):
        """Warn on invalid document status values and invalid transitions without raising."""
        import logging
        _logger = logging.getLogger(__name__)
        valid = {s.value for s in DocumentStatus}
        if value not in valid:
            _logger.warning(f"Invalid document status: {value}")
        # Check transition if we have a committed (pre-flush) status
        if hasattr(self, '_sa_instance_state') and self._sa_instance_state.committed_state.get('status'):
            old_status = self._sa_instance_state.committed_state['status']
            if old_status and not validate_document_status_transition(old_status, value):
                _logger.warning(
                    f"Invalid document status transition: {old_status} -> {value} "
                    f"for document {self.id}"
                )
        return value


class DocPolicyEvent(Base):
    """
    Event tracking for document policy actions.
    Used for audit trail and analytics.
    """
    __tablename__ = "doc_policy_events"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships (foreign keys omitted to allow isolated table creation)
    loan_id = Column(Integer, nullable=False)  # References loans.id
    request_id = Column(Integer, nullable=True)  # References smart_document_requests.id
    document_id = Column(Integer, nullable=True)  # References smart_documents.id

    # Event details
    event_type = Column(SQLEnum(DocPolicyEventType, native_enum=False, create_type=False, length=100), nullable=False)
    payload = Column(JSON, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_doc_policy_events_loan_id", "loan_id"),
        Index("ix_doc_policy_events_event_type", "event_type"),
        Index("ix_doc_policy_events_created_at", "created_at"),
    )


class NeedsListTemplate(Base):
    """
    Configurable templates for document needs lists.
    Allows customization of requirements by loan program, occupancy, income type.
    """
    __tablename__ = "needs_list_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Template identification
    name = Column(String(255), nullable=False)
    slug = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    # Conditions (when to use this template)
    loan_programs = Column(JSON, nullable=True)  # ['CONVENTIONAL', 'FHA', 'VA', 'USDA']
    occupancy_types = Column(JSON, nullable=True)  # ['PRIMARY', 'SECOND_HOME', 'INVESTMENT']
    income_types = Column(JSON, nullable=True)  # ['W2', 'SELF_EMPLOYED', 'RETIREMENT']

    # Template structure
    request_templates = Column(JSON, nullable=False)  # Array of request template objects

    # Status
    is_active = Column(Boolean, default=True)
    version = Column(String(16), default="1")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_needs_list_templates_slug", "slug"),
        Index("ix_needs_list_templates_is_active", "is_active"),
    )


class ClientReminderSettings(Base):
    """
    Per-client reminder settings for document collection.
    Controls whether and how often reminders are sent.
    """
    __tablename__ = "client_reminder_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Client identification (loan_id is the unique key)
    loan_id = Column(Integer, nullable=False, unique=True)

    # Reminder preferences
    reminders_enabled = Column(Boolean, default=True)
    reminder_frequency_hours = Column(Integer, default=72)  # 3 days default

    # Tracking
    last_reminder_sent_at = Column(DateTime, nullable=True)
    reminder_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_client_reminder_settings_loan_id", "loan_id"),
    )
