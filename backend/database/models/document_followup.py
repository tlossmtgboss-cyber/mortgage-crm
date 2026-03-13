"""
Document Follow-Up & Scheduling Models

Automated follow-up campaigns for outstanding document requests, individual
follow-up events/actions, scheduled document-related appointments, and
reusable message templates.

Models:
    - FollowupCampaign: Multi-step follow-up sequence for missing documents
    - FollowupEvent: Individual action taken within a campaign (email, SMS, call)
    - DocumentAppointment: Scheduled appointment for document review/collection
    - FollowupTemplate: Reusable email/SMS/call-script templates for follow-ups

Usage:
    from database.models.document_followup import (
        FollowupCampaign,
        FollowupEvent,
        DocumentAppointment,
        FollowupTemplate,
    )

    # Get active campaigns for a loan
    campaigns = db.query(FollowupCampaign).filter(
        FollowupCampaign.loan_id == loan_id,
        FollowupCampaign.status == CampaignStatus.ACTIVE,
    ).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Enum as SQLEnum,
)

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class CampaignType(str, enum.Enum):
    """Type of document follow-up campaign."""
    INITIAL_REQUEST = "initial_request"
    GENTLE_REMINDER = "gentle_reminder"
    URGENT_REMINDER = "urgent_reminder"
    ESCALATION = "escalation"
    APPOINTMENT_OFFER = "appointment_offer"


class CampaignStatus(str, enum.Enum):
    """Lifecycle status of a follow-up campaign."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignTriggerSource(str, enum.Enum):
    """What triggered the creation of this campaign."""
    NEEDS_LIST_GENERATED = "needs_list_generated"
    DOCUMENT_REJECTED = "document_rejected"
    DOCUMENT_EXPIRED = "document_expired"
    AI_RECOMMENDATION = "ai_recommendation"
    MANUAL = "manual"
    SLA_BREACH = "sla_breach"


class FollowupEventType(str, enum.Enum):
    """Type of follow-up action taken."""
    EMAIL_SENT = "email_sent"
    SMS_SENT = "sms_sent"
    CALL_SCHEDULED = "call_scheduled"
    CALL_COMPLETED = "call_completed"
    PORTAL_NOTIFICATION = "portal_notification"
    IN_APP_NOTIFICATION = "in_app_notification"
    APPOINTMENT_BOOKED = "appointment_booked"
    APPOINTMENT_COMPLETED = "appointment_completed"
    BORROWER_RESPONDED = "borrower_responded"
    DOCUMENT_UPLOADED = "document_uploaded"
    ESCALATED_TO_LO = "escalated_to_lo"


class DeliveryStatus(str, enum.Enum):
    """Delivery status for outbound messages."""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"


class AppointmentType(str, enum.Enum):
    """Type of document-related appointment."""
    DOCUMENT_REVIEW = "document_review"
    INCOME_VERIFICATION = "income_verification"
    NOTARY_SIGNING = "notary_signing"
    DOCUMENT_COLLECTION = "document_collection"
    GENERAL_CONSULTATION = "general_consultation"


class AppointmentStatus(str, enum.Enum):
    """Lifecycle status of a document appointment."""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class LocationType(str, enum.Enum):
    """Where the appointment takes place."""
    IN_PERSON = "in_person"
    VIDEO_CALL = "video_call"
    PHONE_CALL = "phone_call"


# ============================================================================
# FOLLOWUP CAMPAIGN
# ============================================================================

class FollowupCampaign(Base):
    """Automated follow-up sequence for outstanding document requests.

    A campaign consists of multiple steps (configured in step_config), each
    specifying a channel, delay, and template. The scheduler advances through
    steps automatically until the borrower responds or max_reminders is reached.

    step_config example:
        [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder"},
            {"step": 3, "channel": "call", "delay_hours": 96, "template": "urgent_reminder"}
        ]
    """
    __tablename__ = "document_followup_campaigns"
    __table_args__ = (
        Index("ix_document_followup_campaigns_organization_id", "organization_id"),
        Index("ix_document_followup_campaigns_loan_id", "loan_id"),
        Index("ix_document_followup_campaigns_borrower_id", "borrower_id"),
        Index("ix_document_followup_campaigns_status", "status"),
        Index("ix_document_followup_campaigns_next_action_at", "next_action_at"),
        Index("ix_document_followup_campaigns_campaign_type", "campaign_type"),
        Index(
            "ix_document_followup_campaigns_active_loan",
            "loan_id", "status",
        ),
        # Composite indexes for tenant-scoped queries
        Index("ix_followup_camp_org_loan", "organization_id", "loan_id"),
        Index("ix_followup_camp_org_status", "organization_id", "status"),
        Index("ix_followup_camp_org_created", "organization_id", "created_at"),
        Index("ix_followup_camp_org_next_action", "organization_id", "next_action_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id
    loan_id = Column(Integer, nullable=False)  # ref loans.id
    borrower_id = Column(Integer, nullable=True)  # ref leads.id

    # Campaign configuration
    campaign_type = Column(
        SQLEnum(CampaignType, name="campaigntype", create_constraint=False, native_enum=False),
        nullable=False,
    )
    status = Column(
        SQLEnum(CampaignStatus, name="campaignstatus", create_constraint=False, native_enum=False),
        default=CampaignStatus.ACTIVE,
        nullable=False,
    )
    trigger_source = Column(
        SQLEnum(CampaignTriggerSource, name="campaigntriggersource", create_constraint=False, native_enum=False),
        nullable=True,
    )

    # Links to document requests being followed up
    linked_request_ids = Column(JSON, default=list)  # list of smart_document_requests.id

    # Step management
    total_steps = Column(Integer, default=3)
    current_step = Column(Integer, default=0)
    step_config = Column(JSON, default=list)  # list of step configuration dicts

    # Scheduling
    next_action_at = Column(DateTime, nullable=True)  # when next step fires

    # Lifecycle timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)

    # Reminder tracking
    max_reminders = Column(Integer, default=5)
    reminders_sent = Column(Integer, default=0)

    # Borrower response tracking
    borrower_responded = Column(Boolean, default=False)
    response_date = Column(DateTime, nullable=True)

    # Audit
    created_by_user_id = Column(Integer, nullable=True)  # ref users.id
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# FOLLOWUP EVENT
# ============================================================================

class FollowupEvent(Base):
    """Individual follow-up action taken within a campaign.

    Each row represents a single touchpoint: an email sent, an SMS delivered,
    a call scheduled, a borrower response, etc. Provides a complete audit
    trail of all document collection outreach.
    """
    __tablename__ = "document_followup_events"
    __table_args__ = (
        Index("ix_document_followup_events_campaign_id", "campaign_id"),
        Index("ix_document_followup_events_event_type", "event_type"),
        Index("ix_document_followup_events_delivery_status", "delivery_status"),
        Index("ix_document_followup_events_created_at", "created_at"),
        # Composite indexes for tenant-scoped queries
        Index("ix_followup_evt_org_id", "organization_id"),
        Index("ix_followup_evt_org_campaign", "organization_id", "campaign_id"),
        Index("ix_followup_evt_org_created", "organization_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, default=0, comment="FK to organizations.id — tenant isolation")
    campaign_id = Column(Integer, nullable=False)  # ref document_followup_campaigns.id

    # Event details
    event_type = Column(
        SQLEnum(FollowupEventType, name="followupeventtype", create_constraint=False, native_enum=False),
        nullable=False,
    )
    step_number = Column(Integer, nullable=True)
    channel = Column(String(20), nullable=True)  # email, sms, call, portal, in_app
    template_used = Column(String(128), nullable=True)

    # Recipient info
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(20), nullable=True)

    # Message content
    message_subject = Column(String(500), nullable=True)
    message_preview = Column(Text, nullable=True)  # first 500 chars

    # Delivery tracking
    delivery_status = Column(
        SQLEnum(DeliveryStatus, name="deliverystatus", create_constraint=False, native_enum=False),
        default=DeliveryStatus.QUEUED,
        nullable=True,
    )
    delivery_error = Column(Text, nullable=True)

    # Engagement tracking
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    # Extensible metadata
    extra_metadata = Column("metadata", JSON, nullable=True)  # additional event data

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# DOCUMENT APPOINTMENT
# ============================================================================

class DocumentAppointment(Base):
    """Scheduled appointment for document-related issues.

    Supports in-person, video-call, and phone-call appointments for document
    review, income verification, notary signing, and general consultation.
    Can be linked to a follow-up campaign or created independently.
    """
    __tablename__ = "document_appointments"
    __table_args__ = (
        Index("ix_document_appointments_organization_id", "organization_id"),
        Index("ix_document_appointments_loan_id", "loan_id"),
        Index("ix_document_appointments_borrower_id", "borrower_id"),
        Index("ix_document_appointments_campaign_id", "campaign_id"),
        Index("ix_document_appointments_status", "status"),
        Index("ix_document_appointments_scheduled_date", "scheduled_date"),
        Index("ix_document_appointments_assigned_to", "assigned_to_user_id"),
        Index(
            "ix_document_appointments_upcoming",
            "status", "scheduled_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id
    loan_id = Column(Integer, nullable=False)  # ref loans.id
    borrower_id = Column(Integer, nullable=True)  # ref leads.id
    campaign_id = Column(Integer, nullable=True)  # ref document_followup_campaigns.id

    # Appointment details
    appointment_type = Column(
        SQLEnum(AppointmentType, name="appointmenttype", create_constraint=False, native_enum=False),
        nullable=False,
    )
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        SQLEnum(AppointmentStatus, name="appointmentstatus", create_constraint=False, native_enum=False),
        default=AppointmentStatus.SCHEDULED,
        nullable=False,
    )

    # Scheduling
    scheduled_date = Column(Date, nullable=False)
    scheduled_time_start = Column(DateTime, nullable=False)
    scheduled_time_end = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=30)

    # Location
    location_type = Column(
        SQLEnum(LocationType, name="locationtype", create_constraint=False, native_enum=False),
        nullable=True,
    )
    location_details = Column(Text, nullable=True)  # address or meeting link description
    meeting_link = Column(String(1024), nullable=True)

    # Assignment
    assigned_to_user_id = Column(Integer, nullable=True)  # ref users.id — LO or processor

    # Attendee info
    attendee_name = Column(String(255), nullable=True)
    attendee_email = Column(String(255), nullable=True)
    attendee_phone = Column(String(20), nullable=True)

    # Document context
    documents_to_discuss = Column(JSON, nullable=True)  # list of document request IDs
    outcome_notes = Column(Text, nullable=True)
    documents_collected = Column(JSON, nullable=True)  # list of docs collected during appointment

    # Reminder tracking
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime, nullable=True)

    # Lifecycle timestamps
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Rescheduling
    rescheduled_from_id = Column(Integer, nullable=True)  # ref document_appointments.id (original)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# FOLLOWUP TEMPLATE
# ============================================================================

class FollowupTemplate(Base):
    """Reusable email/SMS/call-script template for document follow-up messages.

    Supports merge variables like {{borrower_name}}, {{document_list}},
    {{portal_link}}, {{due_date}}, {{lo_name}}, {{lo_phone}} which are
    substituted at send time by the follow-up engine.

    Templates can be platform defaults (organization_id=NULL, is_default=True)
    or organization-specific customizations.
    """
    __tablename__ = "document_followup_templates"
    __table_args__ = (
        Index("ix_document_followup_templates_organization_id", "organization_id"),
        Index("ix_document_followup_templates_channel", "channel"),
        Index("ix_document_followup_templates_category", "category"),
        Index("ix_document_followup_templates_is_default", "is_default"),
        Index("ix_document_followup_templates_is_active", "is_active"),
        Index(
            "ix_document_followup_templates_org_slug",
            "organization_id", "slug",
            unique=True,
        ),
        Index(
            "ix_document_followup_templates_org_channel",
            "organization_id", "channel",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id

    # Template identity
    name = Column(String(255), nullable=False)
    slug = Column(String(128), nullable=False)  # unique within org (enforced by composite index)
    channel = Column(String(20), nullable=False)  # email, sms, call_script

    # Categorization
    category = Column(String(64), nullable=True)  # initial, reminder, urgent, escalation, appointment

    # Content
    subject_template = Column(String(500), nullable=True)  # for emails; supports {{variables}}
    body_template = Column(Text, nullable=False)  # supports {{borrower_name}}, {{document_list}}, etc.

    # Template metadata
    variables = Column(JSON, default=list)  # list of available template variables

    # Flags
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Usage tracking
    usage_count = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "CampaignType",
    "CampaignStatus",
    "CampaignTriggerSource",
    "FollowupEventType",
    "DeliveryStatus",
    "AppointmentType",
    "AppointmentStatus",
    "LocationType",
    # Models
    "FollowupCampaign",
    "FollowupEvent",
    "DocumentAppointment",
    "FollowupTemplate",
]
