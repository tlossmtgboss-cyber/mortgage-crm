"""
E-Signature Models

Complete e-signature envelope, recipient, field, audit, and template models
for the mortgage CRM platform.  Supports multi-recipient signing workflows
with configurable field placement, comprehensive audit trails, and reusable
document templates.

Models:
    - ESignatureEnvelope: Top-level signing package (document + recipients)
    - ESignatureRecipient: Individual signer/CC/witness on an envelope
    - ESignatureField: Positioned form field on a document page
    - ESignatureAuditEvent: Immutable audit log for every envelope action
    - ESignatureTemplate: Reusable pre-configured document + field layouts

Usage:
    from database.models.esignature import (
        ESignatureEnvelope, ESignatureRecipient, ESignatureField,
        ESignatureAuditEvent, ESignatureTemplate,
    )

    envelope = db.query(ESignatureEnvelope).filter(
        ESignatureEnvelope.envelope_uuid == uuid_str,
        ESignatureEnvelope.organization_id == org_id,
    ).first()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class EnvelopeStatus(str, enum.Enum):
    """Lifecycle status of a signing envelope."""
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PARTIALLY_SIGNED = "partially_signed"
    COMPLETED = "completed"
    DECLINED = "declined"
    VOIDED = "voided"
    EXPIRED = "expired"


class RecipientType(str, enum.Enum):
    """Role of a recipient on an envelope."""
    SIGNER = "signer"
    CC = "cc"
    WITNESS = "witness"
    APPROVER = "approver"


class RecipientStatus(str, enum.Enum):
    """Signing status of an individual recipient."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    VIEWED = "viewed"
    SIGNED = "signed"
    DECLINED = "declined"
    AUTH_FAILED = "auth_failed"


class RecipientAuthMethod(str, enum.Enum):
    """Authentication method used to verify recipient identity."""
    EMAIL_LINK = "email_link"
    SMS_CODE = "sms_code"
    ACCESS_CODE = "access_code"
    KBA = "kba"  # Knowledge-based authentication


class SignatureFieldType(str, enum.Enum):
    """Type of form field placed on a document page."""
    SIGNATURE = "signature"
    INITIAL = "initial"
    DATE_SIGNED = "date_signed"
    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    FULL_NAME = "full_name"
    TITLE = "title"
    COMPANY = "company"


class AuditEventType(str, enum.Enum):
    """Classification of audit events recorded against an envelope."""
    CREATED = "created"
    SENT = "sent"
    DELIVERED = "delivered"
    VIEWED = "viewed"
    FIELD_FILLED = "field_filled"
    SIGNED = "signed"
    DECLINED = "declined"
    VOIDED = "voided"
    COMPLETED = "completed"
    DOWNLOADED = "downloaded"
    PRINTED = "printed"
    REMINDER_SENT = "reminder_sent"
    AUTH_FAILED = "auth_failed"
    AUTH_PASSED = "auth_passed"
    DELEGATED = "delegated"
    CORRECTED = "corrected"
    EXPIRED = "expired"
    TAMPER_DETECTED = "tamper_detected"
    CONSENT_GIVEN = "consent_given"
    CONSENT_DECLINED = "consent_declined"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    KBA_STARTED = "kba_started"
    KBA_PASSED = "kba_passed"
    KBA_FAILED = "kba_failed"
    KBA_LOCKED = "kba_locked"
    PAPER_REQUESTED = "paper_requested"


# ============================================================================
# ESIGNATURE ENVELOPE
# ============================================================================

class ESignatureEnvelope(Base):
    """Top-level e-signature envelope containing a document and recipients.

    An envelope represents a single document sent for signing to one or more
    recipients.  The document is hashed at creation time so any subsequent
    tampering can be detected by comparing document_hash_sha256.

    Lifecycle:  DRAFT -> SENT -> VIEWED -> PARTIALLY_SIGNED -> COMPLETED
                         |                                |
                         +-> VOIDED                       +-> DECLINED
                         +-> EXPIRED
    """
    __tablename__ = "esignature_envelopes"
    __table_args__ = (
        Index("ix_esignature_envelopes_organization_id", "organization_id"),
        Index("ix_esignature_envelopes_envelope_uuid", "envelope_uuid", unique=True),
        Index("ix_esignature_envelopes_loan_id", "loan_id"),
        Index("ix_esignature_envelopes_created_by", "created_by_user_id"),
        Index("ix_esignature_envelopes_status", "status"),
        Index("ix_esignature_envelopes_expires_at", "expires_at"),
        Index("ix_esignature_envelopes_org_status", "organization_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="references organizations.id")
    loan_id = Column(Integer, nullable=True, comment="references loans.id")
    created_by_user_id = Column(Integer, nullable=True, comment="references users.id")

    # Public identifier (never expose internal id externally)
    envelope_uuid = Column(String(36), unique=True, nullable=False, index=True)

    # Document metadata
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    original_filename = Column(String(512), nullable=True)
    page_count = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), nullable=False, default=EnvelopeStatus.DRAFT.value)

    # Document integrity
    document_hash_sha256 = Column(String(64), nullable=True, comment="SHA-256 hash of original document at creation")

    # Storage keys (S3 / object storage)
    document_storage_key = Column(String(1024), nullable=True, comment="S3 key for the original document")
    signed_document_storage_key = Column(String(1024), nullable=True, comment="S3 key for the completed signed document")
    completion_certificate_key = Column(String(1024), nullable=True, comment="S3 key for the completion certificate PDF")

    # Recipient counters
    total_recipients = Column(Integer, nullable=False, default=0)
    completed_recipients = Column(Integer, nullable=False, default=0)

    # Lifecycle timestamps
    sent_at = Column(DateTime, nullable=True)
    viewed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Void details
    void_reason = Column(Text, nullable=True)

    # Creator context
    ip_address_created = Column(String(45), nullable=True)

    # Reminders
    reminder_frequency_hours = Column(Integer, nullable=False, default=48)
    last_reminder_sent_at = Column(DateTime, nullable=True)

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    recipients = relationship("ESignatureRecipient", back_populates="envelope", cascade="all, delete-orphan")
    fields = relationship("ESignatureField", back_populates="envelope", cascade="all, delete-orphan")
    audit_events = relationship("ESignatureAuditEvent", back_populates="envelope", cascade="all, delete-orphan")


# ============================================================================
# ESIGNATURE RECIPIENT
# ============================================================================

class ESignatureRecipient(Base):
    """Individual recipient (signer, CC, witness, or approver) on an envelope.

    Each recipient receives a unique signing_token embedded in their signing
    URL.  An optional access_code provides an additional layer of identity
    verification (the recipient must enter the code before viewing the doc).

    Signing order is enforced: recipients with a lower signing_order value
    must complete before higher-ordered recipients are notified.
    """
    __tablename__ = "esignature_recipients"
    __table_args__ = (
        Index("ix_esignature_recipients_envelope_id", "envelope_id"),
        Index("ix_esignature_recipients_signing_token", "signing_token", unique=True),
        Index("ix_esignature_recipients_email", "email"),
        Index("ix_esignature_recipients_status", "status"),
        Index("ix_esignature_recipients_envelope_order", "envelope_id", "signing_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    envelope_id = Column(Integer, nullable=False, comment="references esignature_envelopes.id")

    # Recipient role and ordering
    recipient_type = Column(String(20), nullable=False, default=RecipientType.SIGNER.value)
    signing_order = Column(Integer, nullable=False, default=1)

    # Contact information
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)

    # Security
    access_code = Column(String(128), nullable=True, comment="Optional PIN for extra security")
    auth_method = Column(String(20), nullable=False, default=RecipientAuthMethod.EMAIL_LINK.value)

    # Signing URL token
    signing_token = Column(String(128), unique=True, nullable=True, comment="Unique URL token for this recipient")
    signing_token_expires_at = Column(DateTime, nullable=True)

    # Status tracking
    status = Column(String(20), nullable=False, default=RecipientStatus.PENDING.value)

    # Action timestamps
    viewed_at = Column(DateTime, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)

    # Decline details
    decline_reason = Column(Text, nullable=True)

    # Signing context (captured at time of signing for legal evidence)
    signing_ip_address = Column(String(45), nullable=True)
    signing_user_agent = Column(String(512), nullable=True)
    signing_geo_location = Column(String(255), nullable=True)

    # Captured signature image
    signature_image_key = Column(String(1024), nullable=True, comment="S3 key for captured signature image")

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    envelope = relationship("ESignatureEnvelope", back_populates="recipients")
    fields = relationship("ESignatureField", back_populates="recipient", cascade="all, delete-orphan")


# ============================================================================
# ESIGNATURE FIELD
# ============================================================================

class ESignatureField(Base):
    """Positioned form field on a specific page of the envelope document.

    Fields are assigned to a recipient and define where on the document the
    recipient must provide input (signature, initials, text, etc.).  Position
    coordinates (x, y, width, height) are expressed as points relative to the
    page origin (top-left corner).

    Radio button groups share the same group_name; only one radio in a group
    can be selected.  Dropdown options are stored as a JSON array of strings.
    """
    __tablename__ = "esignature_fields"
    __table_args__ = (
        Index("ix_esignature_fields_envelope_id", "envelope_id"),
        Index("ix_esignature_fields_recipient_id", "recipient_id"),
        Index("ix_esignature_fields_field_uuid", "field_uuid"),
        Index("ix_esignature_fields_envelope_page", "envelope_id", "page_number"),
        Index("ix_esignature_fields_group", "envelope_id", "group_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    envelope_id = Column(Integer, nullable=False, comment="references esignature_envelopes.id")
    recipient_id = Column(Integer, nullable=True, comment="references esignature_recipients.id")

    # Field classification
    field_type = Column(String(20), nullable=False)
    field_uuid = Column(String(36), nullable=False, comment="Stable identifier for frontend reference")

    # Position on page (points from top-left origin)
    page_number = Column(Integer, nullable=False)
    x_position = Column(Float, nullable=False)
    y_position = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    # Behaviour
    is_required = Column(Boolean, nullable=False, default=True)
    placeholder_text = Column(String(255), nullable=True)
    default_value = Column(String(500), nullable=True)
    validation_regex = Column(String(255), nullable=True)

    # Complex field config
    dropdown_options = Column(JSON, nullable=True, comment="Array of option strings for dropdown fields")
    group_name = Column(String(128), nullable=True, comment="Shared name for radio button groups")

    # Filled data
    value = Column(Text, nullable=True, comment="Value entered/selected by the recipient")
    filled_at = Column(DateTime, nullable=True)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    envelope = relationship("ESignatureEnvelope", back_populates="fields")
    recipient = relationship("ESignatureRecipient", back_populates="fields")


# ============================================================================
# ESIGNATURE AUDIT EVENT
# ============================================================================

class ESignatureAuditEvent(Base):
    """Immutable audit log entry for an envelope action.

    Every meaningful interaction with an envelope is recorded here to
    satisfy legal and compliance requirements.  The document_hash_at_event
    column captures the document hash at the instant the event occurs,
    enabling tamper detection across the full signing lifecycle.

    Rows in this table should NEVER be updated or deleted.
    """
    __tablename__ = "esignature_audit_events"
    __table_args__ = (
        Index("ix_esignature_audit_events_envelope_id", "envelope_id"),
        Index("ix_esignature_audit_events_recipient_id", "recipient_id"),
        Index("ix_esignature_audit_events_event_type", "event_type"),
        Index("ix_esignature_audit_events_timestamp", "timestamp"),
        Index("ix_esignature_audit_events_envelope_type", "envelope_id", "event_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    envelope_id = Column(Integer, nullable=False, comment="references esignature_envelopes.id")
    recipient_id = Column(Integer, nullable=True, comment="references esignature_recipients.id; null for envelope-level events")

    # Event classification
    event_type = Column(String(30), nullable=False)
    event_description = Column(Text, nullable=True)

    # Client context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    geo_location = Column(String(255), nullable=True)

    # Extensible payload
    extra_metadata = Column("metadata", JSON, nullable=True, comment="Additional event-specific data")

    # Document integrity snapshot
    document_hash_at_event = Column(String(64), nullable=True, comment="SHA-256 hash of document at time of event")

    # Timestamp (immutable)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    envelope = relationship("ESignatureEnvelope", back_populates="audit_events")


# ============================================================================
# ESIGNATURE TEMPLATE
# ============================================================================

class ESignatureTemplate(Base):
    """Reusable document template with pre-configured field positions.

    Templates allow loan officers to set up commonly-used documents
    (disclosures, LOEs, authorization forms) once and reuse them across
    multiple envelopes.  The fields_config JSON stores an array of field
    placement definitions; default_recipients stores pre-configured
    recipient role slots that get filled in when creating an envelope.

    fields_config schema (JSON array):
        [{
            "field_type": "signature",
            "page_number": 1,
            "x": 100.0, "y": 500.0,
            "width": 200.0, "height": 50.0,
            "is_required": true,
            "recipient_role": "borrower"
        }, ...]

    default_recipients schema (JSON array):
        [{
            "role_label": "borrower",
            "recipient_type": "signer",
            "signing_order": 1
        }, ...]
    """
    __tablename__ = "esignature_templates"
    __table_args__ = (
        Index("ix_esignature_templates_organization_id", "organization_id"),
        Index("ix_esignature_templates_created_by", "created_by_user_id"),
        Index("ix_esignature_templates_category", "category"),
        Index("ix_esignature_templates_org_active", "organization_id", "is_active"),
        Index("ix_esignature_templates_org_category", "organization_id", "category"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="references organizations.id")
    created_by_user_id = Column(Integer, nullable=True, comment="references users.id")

    # Template identity
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Source document
    document_storage_key = Column(String(1024), nullable=True, comment="S3 key for the template document")

    # Pre-configured layout
    fields_config = Column(JSON, nullable=True, comment="Array of field placement definitions")
    default_recipients = Column(JSON, nullable=True, comment="Array of pre-configured recipient role slots")

    # Classification
    category = Column(String(128), nullable=True, comment="e.g. disclosure, loe, authorization")

    # State
    is_active = Column(Boolean, nullable=False, default=True)
    usage_count = Column(Integer, nullable=False, default=0)

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# ESIGN CONSENT SESSION
# ============================================================================

class ESignConsentSession(Base):
    """Records ESIGN Act consent (or refusal) for a recipient on an envelope.

    The ESIGN Act (15 U.S.C. 7001) requires that consumers affirmatively
    consent to receive electronic records *before* any electronic signature
    is legally binding.  This table captures:

    - The version of the disclosure text shown to the signer.
    - Whether consent was given or declined.
    - The IP address and user-agent string at the moment of consent.
    - Withdrawal details if the signer later revokes consent.

    A consent row must exist with ``consent_given = True`` and
    ``withdrawn_at IS NULL`` before the signing endpoint will accept a
    signature from the corresponding recipient.
    """
    __tablename__ = "esign_consent_sessions"
    __table_args__ = (
        Index("ix_esign_consent_recipient_id", "recipient_id"),
        Index("ix_esign_consent_envelope_id", "envelope_id"),
        Index("ix_esign_consent_org_id", "organization_id"),
        Index(
            "ix_esign_consent_recipient_envelope",
            "recipient_id",
            "envelope_id",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, nullable=False, comment="references esignature_recipients.id")
    envelope_id = Column(Integer, nullable=False, comment="references esignature_envelopes.id")
    organization_id = Column(Integer, nullable=True, comment="references organizations.id")

    # Consent state
    consent_given = Column(Boolean, nullable=False, default=False)
    consent_text_version = Column(String(50), nullable=False, default="1.0")

    # Client context at time of consent
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Timestamps
    consented_at = Column(DateTime, nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    withdrawal_reason = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# ESIGN KBA SESSION
# ============================================================================

class ESignKBASession(Base):
    """Knowledge-Based Authentication session for recipient identity verification.

    KBA sessions are created when an envelope's auth_method requires identity
    proofing beyond simple email-link verification.  The session tracks:

    - Generated questions and their correct answers (hashed).
    - Number of attempts and whether the session is locked.
    - Pass/fail outcome.

    After 3 failed attempts the session is locked and the recipient is
    marked AUTH_FAILED on the envelope.
    """
    __tablename__ = "esign_kba_sessions"
    __table_args__ = (
        Index("ix_esign_kba_recipient_id", "recipient_id"),
        Index("ix_esign_kba_envelope_id", "envelope_id"),
        Index("ix_esign_kba_session_uuid", "session_uuid", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_uuid = Column(String(36), unique=True, nullable=False, index=True)
    recipient_id = Column(Integer, nullable=False, comment="references esignature_recipients.id")
    envelope_id = Column(Integer, nullable=False, comment="references esignature_envelopes.id")

    # Questions / answers stored as JSON: [{question, options, correct_answer_hash}]
    # correct_answer_hash is a bcrypt hash of the correct answer text (lowercased, stripped)
    questions = Column(JSON, nullable=True)

    # Attempt tracking
    max_attempts = Column(Integer, nullable=False, default=3)
    attempts_used = Column(Integer, nullable=False, default=0)
    locked = Column(Boolean, nullable=False, default=False)

    # Outcome
    passed = Column(Boolean, nullable=True, comment="null = not yet attempted")

    # Client context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Timestamps
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "EnvelopeStatus",
    "RecipientType",
    "RecipientStatus",
    "RecipientAuthMethod",
    "SignatureFieldType",
    "AuditEventType",
    # Models
    "ESignatureEnvelope",
    "ESignatureRecipient",
    "ESignatureField",
    "ESignatureAuditEvent",
    "ESignatureTemplate",
    "ESignConsentSession",
    "ESignKBASession",
]
