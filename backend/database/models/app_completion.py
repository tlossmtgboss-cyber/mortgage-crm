"""
Application Completion Orchestrator (ACO) - Database Models

These models power the automated application review, scoring, and resolution
system that ensures submitted loan applications move forward without stalling.

Models:
    - ApplicationCompletenessReview: AI review of a submitted loan application
    - MissingItem: Individual missing field, clarification, document, or exception
    - DocumentStagingRequest: Documents identified as needed, staged for borrower
    - BorrowerCommunicationLog: Every message sent to/from borrower in ACO flow
    - AppointmentCoordination: PA call scheduling for complex file reviews
    - ApplicationScoreHistory: Append-only score change audit trail

Usage:
    from database.models.app_completion import (
        ApplicationCompletenessReview,
        MissingItem,
        DocumentStagingRequest,
        BorrowerCommunicationLog,
        AppointmentCoordination,
        ApplicationScoreHistory,
    )

    # Get latest review for a loan
    review = db.query(ApplicationCompletenessReview).filter(
        ApplicationCompletenessReview.loan_id == loan_id,
        ApplicationCompletenessReview.organization_id == org_id,
    ).order_by(ApplicationCompletenessReview.created_at.desc()).first()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)

from db import Base


__all__ = [
    # Enums
    "ReviewStatus",
    "ComplexityLevel",
    "NextAction",
    "MissingItemType",
    "MissingItemSeverity",
    "MissingItemStatus",
    "ResolutionMethod",
    "DocStagingStatus",
    "CommChannel",
    "SenderType",
    "MessageIntent",
    "BookingStatus",
    "ScoreChangeReason",
    "ActorType",
    # Models
    "ApplicationCompletenessReview",
    "MissingItem",
    "DocumentStagingRequest",
    "BorrowerCommunicationLog",
    "AppointmentCoordination",
    "ApplicationScoreHistory",
]


# ============================================================================
# ENUMS — ApplicationCompletenessReview
# ============================================================================

class ReviewStatus(str, enum.Enum):
    """Lifecycle status of an application completeness review."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ComplexityLevel(str, enum.Enum):
    """Estimated complexity of resolving outstanding items."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class NextAction(str, enum.Enum):
    """AI-recommended next action after review."""
    SEND_INTRO_SMS = "SEND_INTRO_SMS"
    RESOLVE_BY_TEXT = "RESOLVE_BY_TEXT"
    SCHEDULE_PA_CALL = "SCHEDULE_PA_CALL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    WAITING_ON_BORROWER = "WAITING_ON_BORROWER"
    REVIEW_COMPLETE = "REVIEW_COMPLETE"


# ============================================================================
# ENUMS — MissingItem
# ============================================================================

class MissingItemType(str, enum.Enum):
    """Classification of the missing item."""
    FIELD = "FIELD"
    CLARIFICATION = "CLARIFICATION"
    DOCUMENT = "DOCUMENT"
    EXCEPTION = "EXCEPTION"


class MissingItemSeverity(str, enum.Enum):
    """Severity / priority of the missing item."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MissingItemStatus(str, enum.Enum):
    """Resolution lifecycle of a missing item."""
    IDENTIFIED = "IDENTIFIED"
    STAGED = "STAGED"
    SENT_TO_BORROWER = "SENT_TO_BORROWER"
    BORROWER_RESPONDED = "BORROWER_RESPONDED"
    RESOLVED = "RESOLVED"
    DEFERRED = "DEFERRED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class ResolutionMethod(str, enum.Enum):
    """How the missing item was resolved."""
    TEXT_SMS = "TEXT_SMS"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    PA_CALL = "PA_CALL"
    PORTAL_UPLOAD = "PORTAL_UPLOAD"
    AI_AUTO_FILL = "AI_AUTO_FILL"
    BORROWER_PORTAL = "BORROWER_PORTAL"


# ============================================================================
# ENUMS — DocumentStagingRequest
# ============================================================================

class DocStagingStatus(str, enum.Enum):
    """Lifecycle status of a document staging request."""
    IDENTIFIED = "IDENTIFIED"
    STAGED = "STAGED"
    SELECTED = "SELECTED"
    SENT = "SENT"
    UPLOADED = "UPLOADED"
    REVIEWED = "REVIEWED"
    CLEARED = "CLEARED"
    WAIVED = "WAIVED"


# ============================================================================
# ENUMS — BorrowerCommunicationLog
# ============================================================================

class CommChannel(str, enum.Enum):
    """Communication channel used."""
    SMS = "SMS"
    EMAIL = "EMAIL"
    PORTAL = "PORTAL"
    VOICE = "VOICE"
    VCARD = "VCARD"


class SenderType(str, enum.Enum):
    """Who sent the message."""
    AI_AGENT = "AI_AGENT"
    STAFF = "STAFF"
    BORROWER = "BORROWER"
    SYSTEM = "SYSTEM"


class MessageIntent(str, enum.Enum):
    """Purpose of the message."""
    INTRO = "INTRO"
    CONTACT_CARD = "CONTACT_CARD"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    DOC_REQUEST = "DOC_REQUEST"
    REMINDER = "REMINDER"
    ESCALATION = "ESCALATION"
    CONFIRMATION = "CONFIRMATION"
    AVAILABILITY_REQUEST = "AVAILABILITY_REQUEST"
    SCHEDULING = "SCHEDULING"


# ============================================================================
# ENUMS — AppointmentCoordination
# ============================================================================

class BookingStatus(str, enum.Enum):
    """Lifecycle status of a PA call booking."""
    AVAILABILITY_REQUESTED = "AVAILABILITY_REQUESTED"
    WINDOWS_COLLECTED = "WINDOWS_COLLECTED"
    BOOKED = "BOOKED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


# ============================================================================
# ENUMS — ApplicationScoreHistory
# ============================================================================

class ScoreChangeReason(str, enum.Enum):
    """What caused the score to change."""
    INITIAL_REVIEW = "INITIAL_REVIEW"
    FIELD_RESOLVED = "FIELD_RESOLVED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    BORROWER_RESPONSE = "BORROWER_RESPONSE"
    STAFF_UPDATE = "STAFF_UPDATE"
    AI_AUTO_FILL = "AI_AUTO_FILL"
    RECALCULATION = "RECALCULATION"
    ESCALATION_RESOLVED = "ESCALATION_RESOLVED"
    PA_CALL_COMPLETED = "PA_CALL_COMPLETED"


class ActorType(str, enum.Enum):
    """Who triggered the score change."""
    AI_AGENT = "AI_AGENT"
    STAFF = "STAFF"
    BORROWER = "BORROWER"
    SYSTEM = "SYSTEM"


# ============================================================================
# APPLICATION COMPLETENESS REVIEW
# ============================================================================

class ApplicationCompletenessReview(Base):
    """AI review of a submitted loan application.

    Scores the application across data completeness, consistency, and document
    readiness. Produces a list of MissingItem records and recommends the best
    next action (text resolution, PA call, manual review, etc.).

    A loan may have multiple reviews over its lifecycle — one per trigger event
    (initial submission, document upload, borrower response, recalculation).
    """
    __tablename__ = "application_completeness_reviews"
    __table_args__ = (
        Index("ix_acr_org_loan", "organization_id", "loan_id"),
        Index("ix_acr_org_status", "organization_id", "review_status"),
        Index("ix_acr_org_score", "organization_id", "overall_score"),
        Index("ix_acr_org_queue_status", "organization_id", "assigned_to_queue", "review_status"),
        Index("ix_acr_org_created", "organization_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id
    borrower_id = Column(String, nullable=True)  # ref leads.id

    # Review status
    review_status = Column(String, nullable=False, default=ReviewStatus.PENDING.value)

    # Scores (overall 0-100, subscores weighted)
    overall_score = Column(Numeric(5, 2), nullable=True)
    data_completeness_score = Column(Numeric(5, 2), nullable=True)  # 0-60 subscore
    data_consistency_score = Column(Numeric(5, 2), nullable=True)   # 0-25 subscore
    document_readiness_score = Column(Numeric(5, 2), nullable=True) # 0-15 subscore

    # Complexity assessment
    complexity_score = Column(Integer, nullable=True)  # 0-10, resolution complexity
    complexity_level = Column(String, nullable=True)    # ComplexityLevel enum value
    confidence_score = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Recommended action
    next_recommended_action = Column(String, nullable=True)  # NextAction enum value

    # Item counts
    total_missing_items = Column(Integer, nullable=False, default=0)
    total_clarifications_needed = Column(Integer, nullable=False, default=0)
    total_documents_needed = Column(Integer, nullable=False, default=0)
    total_escalations = Column(Integer, nullable=False, default=0)
    items_resolved_by_ai = Column(Integer, nullable=False, default=0)
    items_resolved_by_staff = Column(Integer, nullable=False, default=0)

    # AI execution metadata
    ai_model_used = Column(String, nullable=True)
    review_duration_ms = Column(Integer, nullable=True)

    # AI-generated summary
    review_summary = Column(Text, nullable=True)

    # Per-section score breakdown: {borrower_identity: 7/8, employment: 12/15, ...}
    section_scores = Column(JSON, nullable=True)

    # Trigger context
    triggered_by = Column(String, nullable=False, default="APPLICATION_SUBMITTED")

    # Assignment / routing
    assigned_to_user_id = Column(String, nullable=True)
    assigned_to_queue = Column(String, nullable=True)  # "AI_QUEUE", "PA_QUEUE", "LO_QUEUE"

    # Lifecycle timestamps
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# MISSING ITEM
# ============================================================================

class MissingItem(Base):
    """Individual missing data field, clarification, document, or exception.

    Each item represents a single gap identified during an application
    completeness review. Items progress through a resolution lifecycle:
    IDENTIFIED -> STAGED -> SENT_TO_BORROWER -> BORROWER_RESPONDED -> RESOLVED.

    Items can be resolved via multiple channels: SMS text conversation,
    PA phone call, borrower portal upload, or AI auto-fill.
    """
    __tablename__ = "missing_items"
    __table_args__ = (
        Index("ix_mi_org_loan_status", "organization_id", "loan_id", "status"),
        Index("ix_mi_org_review", "organization_id", "review_id"),
        Index("ix_mi_org_type_status", "organization_id", "item_type", "status"),
        Index("ix_mi_org_severity_status", "organization_id", "severity", "status"),
        Index("ix_mi_loan_field", "loan_id", "field_path"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    review_id = Column(
        Integer,
        ForeignKey("application_completeness_reviews.id"),
        nullable=False,
        index=True,
    )
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id

    # Classification
    item_type = Column(String, nullable=False)   # MissingItemType enum value
    severity = Column(String, nullable=False)     # MissingItemSeverity enum value

    # Field identification
    field_path = Column(String, nullable=True)     # e.g. "borrower.employment.employer_phone"
    field_section = Column(String, nullable=True)  # e.g. "employment", "assets", "declarations"

    # Borrower-facing and staff-facing descriptions
    borrower_question = Column(Text, nullable=True)  # friendly question for borrower
    internal_note = Column(Text, nullable=True)       # for staff context

    # Resolution tracking
    resolution_method = Column(String, nullable=True)  # ResolutionMethod enum value
    status = Column(String, nullable=False, default=MissingItemStatus.IDENTIFIED.value)

    # Source engine identification
    source_engine = Column(String, nullable=True)  # "data_completeness", "consistency_check", "document_rules", "plausibility"

    # AI confidence in this identification
    ai_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Value tracking
    current_value = Column(String, nullable=True)   # what's currently in the field
    resolved_value = Column(String, nullable=True)   # what was filled in

    # Resolution attribution
    resolved_by_user_id = Column(String, nullable=True)
    resolved_by_type = Column(String, nullable=True)  # "AI", "STAFF", "BORROWER"

    # Lifecycle timestamps
    sent_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# DOCUMENT STAGING REQUEST
# ============================================================================

class DocumentStagingRequest(Base):
    """Documents identified as needed, staged for review, then sent to borrower.

    Represents a single document requirement discovered during application
    review. Follows a lifecycle: IDENTIFIED -> STAGED (PA reviews) -> SELECTED
    -> SENT (to borrower) -> UPLOADED -> REVIEWED -> CLEARED/WAIVED.

    Can be linked to an ApplicationCompletenessReview or created independently
    (e.g., by an underwriter adding a condition).
    """
    __tablename__ = "document_staging_requests"
    __table_args__ = (
        Index("ix_dsr_org_loan_status", "organization_id", "loan_id", "status"),
        Index("ix_dsr_org_review", "organization_id", "review_id"),
        Index("ix_dsr_org_status_priority", "organization_id", "status", "priority"),
        Index("ix_dsr_loan_doctype", "loan_id", "doc_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    review_id = Column(
        Integer,
        ForeignKey("application_completeness_reviews.id"),
        nullable=True,
        index=True,
    )
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id

    # Document identification
    doc_type = Column(String, nullable=False)   # e.g. "paystub", "w2", "bank_statement"
    doc_label = Column(String, nullable=False)  # display label for borrower

    # Reason for request
    reason_code = Column(String, nullable=True)       # "income_validation", "asset_verification", etc.
    reason_description = Column(Text, nullable=True)  # human-readable explanation

    # Status and priority
    status = Column(String, nullable=False, default=DocStagingStatus.IDENTIFIED.value)
    priority = Column(String, nullable=False, default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, LOW

    # Staging workflow
    staged_by_user_id = Column(String, nullable=True)
    staged_at = Column(DateTime, nullable=True)

    # Delivery to borrower
    sent_at = Column(DateTime, nullable=True)
    sent_channel = Column(String, nullable=True)  # "PORTAL", "EMAIL", "SMS"

    # Upload tracking
    uploaded_at = Column(DateTime, nullable=True)
    uploaded_document_id = Column(String, nullable=True)  # ref documents.id

    # Review workflow
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(String, nullable=True)

    # Clearance / waiver
    cleared_at = Column(DateTime, nullable=True)
    waived_at = Column(DateTime, nullable=True)
    waived_reason = Column(String, nullable=True)

    # Scheduling
    due_date = Column(DateTime, nullable=True)

    # Borrower notification flags
    borrower_notified = Column(Boolean, nullable=False, default=False)
    portal_published = Column(Boolean, nullable=False, default=False)

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# BORROWER COMMUNICATION LOG
# ============================================================================

class BorrowerCommunicationLog(Base):
    """Every message sent to or received from the borrower in the ACO flow.

    Provides a complete audit trail of all orchestration communications:
    intro SMS, data collection questions, borrower answers, document request
    messages, reminders, escalation notices, and scheduling confirmations.

    Each row captures the channel, intent, delivery status, and — for inbound
    messages — the AI-classified intent and sentiment of the borrower response.
    """
    __tablename__ = "borrower_communication_logs"
    __table_args__ = (
        Index("ix_bcl_org_loan_channel", "organization_id", "loan_id", "channel"),
        Index("ix_bcl_org_review", "organization_id", "review_id"),
        Index("ix_bcl_org_delivery", "organization_id", "delivery_status"),
        Index("ix_bcl_loan_item", "loan_id", "missing_item_id"),
        Index("ix_bcl_org_created", "organization_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id
    review_id = Column(
        Integer,
        ForeignKey("application_completeness_reviews.id"),
        nullable=True,
        index=True,
    )
    missing_item_id = Column(
        Integer,
        ForeignKey("missing_items.id"),
        nullable=True,
        index=True,
    )

    # Message metadata
    channel = Column(String, nullable=False)         # CommChannel enum value
    sender_type = Column(String, nullable=False)     # SenderType enum value
    message_intent = Column(String, nullable=False)  # MessageIntent enum value
    template_id = Column(String, nullable=True)

    # Message content
    message_body = Column(Text, nullable=False)

    # Recipient info
    recipient_phone = Column(String, nullable=True)
    recipient_email = Column(String, nullable=True)

    # Delivery tracking
    delivery_status = Column(String, nullable=True)  # "QUEUED", "SENT", "DELIVERED", "READ", "FAILED", "BOUNCED"

    # Borrower response tracking
    response_detected = Column(Boolean, nullable=False, default=False)
    response_body = Column(Text, nullable=True)
    response_intent = Column(String, nullable=True)          # AI-classified intent of borrower response
    response_confidence = Column(Numeric(5, 2), nullable=True)

    # Sentiment analysis
    sentiment = Column(String, nullable=True)  # "POSITIVE", "NEUTRAL", "NEGATIVE", "FRUSTRATED"

    # Error tracking
    error_message = Column(String, nullable=True)

    # External provider reference
    external_message_id = Column(String, nullable=True)  # Telnyx/Twilio message ID

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# APPOINTMENT COORDINATION
# ============================================================================

class AppointmentCoordination(Base):
    """PA call scheduling for complex file reviews.

    When the ACO determines a loan file is too complex for text-based
    resolution, it initiates appointment coordination. This tracks the full
    booking lifecycle: availability collection from the borrower, PA matching,
    calendar booking, pre-call brief generation, and post-call resolution.

    Typical flow:
        AVAILABILITY_REQUESTED -> WINDOWS_COLLECTED -> BOOKED -> CONFIRMED
        -> COMPLETED (with items_resolved_in_call logged)
    """
    __tablename__ = "appointment_coordinations"
    __table_args__ = (
        Index("ix_ac_org_loan", "organization_id", "loan_id"),
        Index("ix_ac_org_status", "organization_id", "booking_status"),
        Index("ix_ac_org_pa_status", "organization_id", "assigned_pa_user_id", "booking_status"),
        Index("ix_ac_org_booked", "organization_id", "booked_start"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id
    review_id = Column(
        Integer,
        ForeignKey("application_completeness_reviews.id"),
        nullable=True,
        index=True,
    )

    # Staff assignment
    assigned_pa_user_id = Column(String, nullable=True)   # production assistant
    assigned_lo_user_id = Column(String, nullable=True)   # loan officer

    # Borrower contact info (denormalized for scheduling convenience)
    borrower_name = Column(String, nullable=True)
    borrower_phone = Column(String, nullable=True)
    borrower_email = Column(String, nullable=True)

    # Availability and booking
    proposed_windows = Column(JSON, nullable=True)  # [{day, start, end}, ...]
    booked_start = Column(DateTime, nullable=True)
    booked_end = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=15)

    # Status
    booking_status = Column(String, nullable=False, default=BookingStatus.AVAILABILITY_REQUESTED.value)
    appointment_type = Column(String, nullable=False, default="APPLICATION_REVIEW")  # "APPLICATION_REVIEW", "INCOME_REVIEW", "DOCUMENT_COLLECTION"

    # Meeting details
    meeting_link = Column(String, nullable=True)
    calendar_event_id = Column(String, nullable=True)  # external calendar ID

    # Pre-call preparation
    pre_call_brief = Column(Text, nullable=True)  # AI summary of unresolved items for PA
    unresolved_items_count = Column(Integer, nullable=False, default=0)
    complexity_score = Column(Integer, nullable=False, default=0)

    # Confirmation tracking
    borrower_confirmed = Column(Boolean, nullable=False, default=False)
    pa_confirmed = Column(Boolean, nullable=False, default=False)

    # Post-call tracking
    call_notes = Column(Text, nullable=True)
    items_resolved_in_call = Column(Integer, nullable=False, default=0)

    # Lifecycle timestamps
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# APPLICATION SCORE HISTORY
# ============================================================================

class ApplicationScoreHistory(Base):
    """Append-only audit trail of application score changes.

    Every time an application's overall_score changes — whether from initial
    review, borrower response, document upload, staff update, or AI auto-fill —
    a new row is appended. This makes scoring operational and auditable,
    enabling trend visualization and SLA measurement.

    This table is intentionally append-only: no updated_at column, no
    modifications to existing rows.
    """
    __tablename__ = "application_score_history"
    __table_args__ = (
        Index("ix_ash_org_loan_created", "organization_id", "loan_id", "created_at"),
        Index("ix_ash_org_review", "organization_id", "review_id"),
        Index("ix_ash_loan_created", "loan_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(String, nullable=False, index=True)  # ref loans.id
    review_id = Column(
        Integer,
        ForeignKey("application_completeness_reviews.id"),
        nullable=True,
        index=True,
    )

    # Score change
    prior_score = Column(Numeric(5, 2), nullable=False)
    new_score = Column(Numeric(5, 2), nullable=False)
    score_delta = Column(Numeric(5, 2), nullable=False)  # new_score - prior_score

    # Change context
    reason = Column(String, nullable=False)       # ScoreChangeReason enum value
    reason_detail = Column(Text, nullable=True)   # e.g. "Borrower provided employer phone via SMS"

    # Actor attribution
    actor_type = Column(String, nullable=False)   # ActorType enum value
    actor_user_id = Column(String, nullable=True)

    # Related item
    missing_item_id = Column(
        Integer,
        ForeignKey("missing_items.id"),
        nullable=True,
        index=True,
    )

    # Which section improved
    section_affected = Column(String, nullable=True)

    # Append-only: created_at only, no updated_at
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
