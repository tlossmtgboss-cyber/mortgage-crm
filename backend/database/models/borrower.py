"""
Borrower Application System Models

Models for borrower profiles, applications, documents, co-borrower invitations,
and application tracking/analytics.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.borrower import BorrowerProfile, BorrowerApplication, ApplicationDocument
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Numeric,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.orm import relationship

from db import Base
from database.enums import ApplicationStatus, ApplicationStep, DocumentCategory
from encryption_utils import EncryptedString


class BorrowerProfile(Base):
    """
    Borrower identity profile - created via social login.
    Links to one or more BorrowerApplications.
    """
    __tablename__ = "borrower_profiles"
    __table_args__ = (
        Index('ix_borrower_profile_email', 'email'),
        Index('ix_borrower_profile_provider', 'provider', 'provider_user_id'),
        Index('ix_borrower_profile_org_id', 'organization_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation

    # Identity from social provider
    email = Column(String, nullable=False, index=True)  # NOTE: Not encrypted — indexed for lookups. Consider adding email_hash column.
    first_name = Column(EncryptedString)
    last_name = Column(EncryptedString)
    profile_photo = Column(String)

    # Social provider info
    provider = Column(String(20), nullable=False)
    provider_user_id = Column(String, nullable=False)
    raw_profile = Column(JSON)

    # Consent tracking (basic)
    communication_consent = Column(Boolean, default=True)
    marketing_consent = Column(Boolean, default=False)
    consent_captured_at = Column(DateTime)
    consent_ip_address = Column(EncryptedString)  # PII: IP address

    # Granular consent tracking (FCC Jan 2025 one-to-one consent rule)
    consent_given_to = Column(String(255))       # Company or user name consent was given to
    consent_method = Column(String(50))           # 'web_form', 'verbal', 'written', 'sms_optin'
    consent_text = Column(Text)                   # Exact disclosure language agreed to
    consent_revoked_at = Column(DateTime)         # When consent was revoked (if applicable)
    consent_revocation_method = Column(String(50))  # 'sms_stop', 'email', 'phone', 'web_form'

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    applications = relationship("BorrowerApplication", back_populates="borrower_profile")
    auth_events = relationship("BorrowerAuthEvent", back_populates="borrower_profile")


class BorrowerAuthEvent(Base):
    """Track borrower authentication events for security and analytics."""
    __tablename__ = "borrower_auth_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    borrower_id = Column(String(36), ForeignKey("borrower_profiles.id", ondelete="CASCADE"), nullable=False)

    event_type = Column(String(20), nullable=False)  # login, logout, token_refresh
    provider = Column(String(20))
    ip_address = Column(EncryptedString)  # PII: IP address
    user_agent = Column(String)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    borrower_profile = relationship("BorrowerProfile", back_populates="auth_events")


class BorrowerMagicLink(Base):
    """Magic link tokens for email-based login."""
    __tablename__ = "borrower_magic_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    borrower_id = Column(String(36), ForeignKey("borrower_profiles.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BorrowerApplication(Base):
    """
    Main borrower application - stores full URLA data and tracks progress.
    Uses public_token for secure borrower access without login.
    """
    __tablename__ = "borrower_applications"
    __table_args__ = (
        Index('ix_borrower_app_public_token', 'public_token'),
        Index('ix_borrower_app_lead_id', 'lead_id'),
        Index('ix_borrower_app_status', 'status'),
        Index('ix_borrower_app_owner', 'owner_id'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Public access token
    public_token = Column(String(64), unique=True, nullable=False, index=True)

    # Link to borrower profile
    borrower_profile_id = Column(String(36), ForeignKey("borrower_profiles.id"), nullable=True)

    # Link to internal records
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    # Application status and progress
    status = Column(SQLEnum(ApplicationStatus), default=ApplicationStatus.DRAFT)
    current_step = Column(SQLEnum(ApplicationStep), default=ApplicationStep.PERSONAL_INFO)
    progress_percentage = Column(Integer, default=0)

    # Step completion tracking
    completed_steps = Column(JSON, default=list)
    step_data = Column(JSON, default=dict)

    # Borrower information
    borrower_first_name = Column(EncryptedString)  # PII: name
    borrower_last_name = Column(EncryptedString)  # PII: name
    borrower_email = Column(String, index=True)  # NOTE: Not encrypted — indexed for lookups. Consider adding email_hash column.
    borrower_phone = Column(EncryptedString)  # PII: phone number

    # Co-borrower tracking
    has_coborrower = Column(Boolean, default=False)
    coborrower_email = Column(EncryptedString)  # PII: email address
    coborrower_completed = Column(Boolean, default=False)

    # Pre-qualification data
    prequalification_amount = Column(Numeric(18, 2))
    prequalification_rate = Column(Numeric(8, 4))
    prequalification_monthly_payment = Column(Numeric(18, 2))
    prequalification_data = Column(JSON)

    # Credit authorization
    credit_auth_captured = Column(Boolean, default=False)
    credit_auth_timestamp = Column(DateTime)
    credit_auth_ip_address = Column(EncryptedString)  # PII: IP address
    credit_auth_user_agent = Column(String)
    credit_auth_ssn_last4 = Column(EncryptedString)  # PII: partial SSN

    # Encrypted SSN storage (P0-3: SSN must not be stored plaintext)
    ssn_encrypted = Column(EncryptedString, nullable=True)
    co_ssn_encrypted = Column(EncryptedString, nullable=True)

    # Submission tracking
    submitted_at = Column(DateTime)
    reviewed_at = Column(DateTime)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"))

    # Token expiration
    expires_at = Column(DateTime)

    # Analytics
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    time_spent_seconds = Column(Integer, default=0)
    device_info = Column(JSON)

    # Metadata
    notes = Column(Text)
    application_metadata = Column(JSON, default=dict)

    # GMI (Government Monitoring Information) - ECOA/HMDA demographics
    # Stored separately from decisioning data per ECOA requirements.
    # All fields are nullable (voluntary collection per ECOA).
    applicant_ethnicity = Column(String, nullable=True)      # HMDA ethnicity code
    applicant_race = Column(String, nullable=True)            # HMDA race code
    applicant_sex = Column(String, nullable=True)             # HMDA sex code
    applicant_age = Column(Integer, nullable=True)            # Applicant age at application
    co_applicant_ethnicity = Column(String, nullable=True)    # Co-applicant HMDA ethnicity
    co_applicant_race = Column(String, nullable=True)         # Co-applicant HMDA race
    co_applicant_sex = Column(String, nullable=True)          # Co-applicant HMDA sex
    co_applicant_age = Column(Integer, nullable=True)         # Co-applicant age
    gmi_collection_method = Column(String, nullable=True)     # face_to_face, telephone, mail_internet
    gmi_collected_at = Column(DateTime, nullable=True)        # When GMI data was collected

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def ssn_display(self) -> str:
        """Masked SSN display: ***-**-1234 (derived from credit_auth_ssn_last4)"""
        if self.credit_auth_ssn_last4:
            return f"***-**-{self.credit_auth_ssn_last4}"
        return None

    # Relationships
    borrower_profile = relationship("BorrowerProfile", back_populates="applications")
    lead = relationship("Lead", backref="borrower_applications")
    loan = relationship("Loan", backref="borrower_applications")
    owner = relationship("User", foreign_keys=[owner_id], backref="created_applications")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id], backref="reviewed_applications")
    documents = relationship("ApplicationDocument", back_populates="application", cascade="all, delete-orphan")
    coborrower_invitations = relationship("CoborrowerInvitation", back_populates="application", cascade="all, delete-orphan")
    events = relationship("ApplicationEvent", back_populates="application", cascade="all, delete-orphan")
    notifications = relationship("ApplicationNotification", back_populates="application", cascade="all, delete-orphan")


class ApplicationDocument(Base):
    """Documents uploaded by borrowers during application process."""
    __tablename__ = "application_documents"
    __table_args__ = (
        Index('ix_app_doc_application', 'application_id'),
        Index('ix_app_doc_category', 'category'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Document metadata
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String)
    category = Column(SQLEnum(DocumentCategory), default=DocumentCategory.MISC)
    description = Column(String)

    # Storage info
    storage_key = Column(String)
    storage_bucket = Column(String)
    storage_url = Column(String)

    # Verification
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    verified_by_id = Column(Integer, ForeignKey("users.id"))
    verification_notes = Column(Text)

    # AI classification and analysis
    ai_classified_type = Column(String)
    ai_confidence = Column(Float)
    ai_extracted_data = Column(JSON)
    ai_verified = Column(Boolean, default=False)
    ai_document_type = Column(String)
    ai_analysis = Column(JSON)
    ai_analyzed_at = Column(DateTime)

    # Metadata
    uploaded_by = Column(String)
    borrower_notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    application = relationship("BorrowerApplication", back_populates="documents")
    verified_by = relationship("User", backref="verified_app_documents")


class CoborrowerInvitation(Base):
    """Tracks co-borrower invitations and their completion status."""
    __tablename__ = "coborrower_invitations"
    __table_args__ = (
        Index('ix_coborrower_inv_token', 'invitation_token'),
        Index('ix_coborrower_inv_app', 'application_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Invitation details
    invitation_token = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(EncryptedString, nullable=False)  # PII: email address
    first_name = Column(EncryptedString)  # PII: name
    last_name = Column(EncryptedString)  # PII: name
    phone = Column(EncryptedString)  # PII: phone number
    relationship_type = Column(String)

    # Status tracking
    status = Column(String, default="pending")

    # Invitation tracking
    sent_at = Column(DateTime)
    opened_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Co-borrower data
    coborrower_data = Column(JSON, default=dict)

    # Credit authorization
    credit_auth_captured = Column(Boolean, default=False)
    credit_auth_timestamp = Column(DateTime)
    credit_auth_ip_address = Column(EncryptedString)  # PII: IP address

    # Reminder tracking
    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    application = relationship("BorrowerApplication", back_populates="coborrower_invitations")


class ApplicationEvent(Base):
    """Tracks all events/actions in the application process for analytics and audit."""
    __tablename__ = "application_events"
    __table_args__ = (
        Index('ix_app_event_application', 'application_id', 'created_at'),
        Index('ix_app_event_type', 'event_type'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Event details
    event_type = Column(String, nullable=False)
    event_data = Column(JSON, default=dict)

    # Actor info
    actor_type = Column(String)
    actor_email = Column(EncryptedString)  # PII: email address

    # Context
    step = Column(String)
    ip_address = Column(EncryptedString)  # PII: IP address
    user_agent = Column(String)
    device_type = Column(String)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    application = relationship("BorrowerApplication", back_populates="events")


class ApplicationNotification(Base):
    """Tracks notifications sent during the application process."""
    __tablename__ = "application_notifications"
    __table_args__ = (
        Index('ix_app_notif_application', 'application_id'),
        Index('ix_app_notif_type', 'notification_type'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Notification details
    notification_type = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    recipient_email = Column(EncryptedString)  # PII: email address
    recipient_phone = Column(EncryptedString)  # PII: phone number

    # Content
    subject = Column(String)
    body = Column(Text)
    template_id = Column(String)

    # Delivery tracking
    status = Column(String, default="pending")
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    failed_at = Column(DateTime)
    failure_reason = Column(String)

    # External IDs
    external_id = Column(String)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    application = relationship("BorrowerApplication", back_populates="notifications")


class ApplicationSession(Base):
    """Tracks active sessions for save/resume functionality.

    Note: This model is reserved for future use. The table may exist in
    production; do not drop it. Session-based save/resume is not yet
    wired into the borrower application flow.
    """
    __tablename__ = "application_sessions"
    __table_args__ = (
        Index('ix_app_session_token', 'session_token'),
        Index('ix_app_session_app', 'application_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Session token for resume
    session_token = Column(String(64), unique=True, nullable=False)

    # Session data
    last_step = Column(String)
    unsaved_data = Column(JSON, default=dict)
    scroll_position = Column(JSON)

    # Device info
    device_fingerprint = Column(EncryptedString)  # PII: device fingerprint
    ip_address = Column(EncryptedString)  # PII: IP address
    user_agent = Column(String)

    # Status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VoiceApplicationSession(Base):
    """Tracks AI voice agent sessions for borrower applications."""
    __tablename__ = "voice_application_sessions"
    __table_args__ = (
        Index('ix_voice_app_session', 'application_id'),
        Index('ix_voice_app_call_sid', 'call_sid'),
    )

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("borrower_applications.id", ondelete="CASCADE"), nullable=False)

    # Call details
    call_sid = Column(String, unique=True, index=True)
    phone_number = Column(EncryptedString)  # PII: phone number

    # Session state
    current_step = Column(String)
    conversation_context = Column(JSON, default=dict)
    collected_data = Column(JSON, default=dict)

    # Status
    status = Column(String, default="active")

    # Metrics
    duration_seconds = Column(Integer)
    fields_collected = Column(Integer, default=0)

    # Timestamps
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)

    # Relationships
    application = relationship("BorrowerApplication", backref="voice_sessions")


__all__ = [
    "BorrowerProfile",
    "BorrowerAuthEvent",
    "BorrowerMagicLink",
    "BorrowerApplication",
    "ApplicationDocument",
    "CoborrowerInvitation",
    "ApplicationEvent",
    "ApplicationNotification",
    "ApplicationSession",
    "VoiceApplicationSession",
]
