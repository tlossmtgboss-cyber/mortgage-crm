"""
Event Models for Acquisition Engine
AcquisitionEvent - Behavioral event tracking for lead scoring and attribution
"""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import Base


class EventType(str, Enum):
    """
    Event types for tracking lead behavior.
    Categorized by signal strength for temperature calculation.
    """
    # ==================== HOT SIGNALS (Explicit Intent) ====================
    MEETING_BOOKED = "MEETING_BOOKED"
    APPLICATION_STARTED = "APPLICATION_STARTED"
    APPLICATION_COMPLETED = "APPLICATION_COMPLETED"
    FORM_SUBMITTED = "FORM_SUBMITTED"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    CHAT_INITIATED = "CHAT_INITIATED"
    VIDEO_WATCHED_75_PLUS = "VIDEO_WATCHED_75_PLUS"
    CALCULATOR_COMPLETED = "CALCULATOR_COMPLETED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"

    # ==================== WARM SIGNALS (Educational Engagement) ====================
    PRICING_PAGE_VIEW = "PRICING_PAGE_VIEW"
    CALCULATOR_STARTED = "CALCULATOR_STARTED"
    QUIZ_STARTED = "QUIZ_STARTED"
    QUIZ_COMPLETED = "QUIZ_COMPLETED"
    VIDEO_WATCHED_25_PLUS = "VIDEO_WATCHED_25_PLUS"
    VIDEO_WATCHED_50_PLUS = "VIDEO_WATCHED_50_PLUS"
    FAQ_VIEWED = "FAQ_VIEWED"
    BLOG_READ = "BLOG_READ"
    EMAIL_LINK_CLICKED = "EMAIL_LINK_CLICKED"
    SMS_REPLIED = "SMS_REPLIED"
    MULTIPLE_PAGE_VIEWS = "MULTIPLE_PAGE_VIEWS"

    # ==================== COLD SIGNALS (First Touch / Minimal) ====================
    PAGE_VIEW = "PAGE_VIEW"
    FUNNEL_VISIT = "FUNNEL_VISIT"
    EMAIL_OPENED = "EMAIL_OPENED"
    SMS_DELIVERED = "SMS_DELIVERED"
    AD_IMPRESSION = "AD_IMPRESSION"
    AD_CLICK = "AD_CLICK"

    # ==================== COMMUNICATION EVENTS ====================
    CALL_ATTEMPTED = "CALL_ATTEMPTED"
    CALL_CONNECTED = "CALL_CONNECTED"
    CALL_COMPLETED = "CALL_COMPLETED"
    CALL_VOICEMAIL = "CALL_VOICEMAIL"
    EMAIL_SENT = "EMAIL_SENT"
    EMAIL_BOUNCED = "EMAIL_BOUNCED"
    SMS_SENT = "SMS_SENT"
    SMS_FAILED = "SMS_FAILED"
    SMS_OPT_OUT = "SMS_OPT_OUT"

    # ==================== CONVERSION EVENTS ====================
    LEAD_CREATED = "LEAD_CREATED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    MEETING_COMPLETED = "MEETING_COMPLETED"
    MEETING_NO_SHOW = "MEETING_NO_SHOW"
    LOAN_SUBMITTED = "LOAN_SUBMITTED"
    LOAN_APPROVED = "LOAN_APPROVED"
    LOAN_FUNDED = "LOAN_FUNDED"
    LOAN_CANCELLED = "LOAN_CANCELLED"

    # ==================== SYSTEM EVENTS ====================
    TEMPERATURE_CHANGED = "TEMPERATURE_CHANGED"
    SEGMENT_ENTERED = "SEGMENT_ENTERED"
    SEGMENT_EXITED = "SEGMENT_EXITED"
    SLA_BREACH = "SLA_BREACH"
    SPEED_TO_LEAD_SUCCESS = "SPEED_TO_LEAD_SUCCESS"


class EventSource(str, Enum):
    """Source channel of the event"""
    FUNNEL = "FUNNEL"
    WEBSITE = "WEBSITE"
    SMS = "SMS"
    EMAIL = "EMAIL"
    CALL = "CALL"
    CHAT = "CHAT"
    APP = "APP"
    ADS = "ADS"
    SYSTEM = "SYSTEM"


class AcquisitionEvent(Base):
    """
    Acquisition Event - Records all behavioral events for leads

    Every interaction, from ad impression to funded loan, is captured as an event.
    Events are used for:
    - Lead temperature calculation
    - Segment membership computation
    - Attribution tracking
    - Triggering automation (speed-to-lead, sequences)
    - Analytics and reporting
    """
    __tablename__ = "acquisition_events"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Ownership
    organization_id = Column(Integer, nullable=False, index=True)

    # Campaign Reference (optional - events can exist without campaign)
    campaign_instance_id = Column(UUID(as_uuid=True), ForeignKey("campaign_instances.id"), index=True)
    campaign_instance = relationship("CampaignInstance", back_populates="events")

    # ==================== IDENTITY ====================
    # Lead ID (NULL until identified - e.g., form submission)
    lead_id = Column(Integer, index=True)

    # Anonymous visitor tracking (for pre-identification attribution)
    anonymous_visitor_id = Column(String(255), index=True)  # Cookie/fingerprint hash
    session_id = Column(String(255))  # Browser session ID
    device_fingerprint = Column(String(255))  # Device fingerprint

    # Identity linking (when anonymous becomes known)
    identity_linked_at = Column(DateTime)
    identity_linked_from = Column(String(255))  # Event that caused linking

    # ==================== EVENT DATA ====================
    event_type = Column(String(100), nullable=False, index=True)  # EventType enum
    event_source = Column(String(50))  # EventSource enum

    # Event-specific payload
    event_payload = Column(JSON, default=dict)
    # Examples:
    # PAGE_VIEW: {"url": "/rates", "referrer": "google.com", "time_on_page": 45}
    # FORM_SUBMITTED: {"form_id": "contact", "fields": {"loan_amount": 500000}}
    # VIDEO_WATCHED: {"video_id": "intro", "percent_watched": 75, "duration": 180}
    # CALL_COMPLETED: {"duration_seconds": 300, "disposition": "interested"}
    # EMAIL_CLICKED: {"email_id": "welcome_1", "link_url": "/calculator"}

    # ==================== COMPUTED FIELDS ====================
    # Lead temperature at time of event (for historical tracking)
    lead_temperature = Column(String(20))  # COLD, WARM, HOT, REPEAT

    # Segment memberships at time of event
    segment_memberships = Column(JSON, default=list)  # Array of segment IDs

    # Temperature impact (how much this event affected temperature)
    temperature_impact = Column(Integer, default=0)  # Points added

    # ==================== ATTRIBUTION ====================
    # UTM parameters for attribution
    utm_source = Column(String(100))
    utm_medium = Column(String(100))
    utm_campaign = Column(String(100))
    utm_term = Column(String(100))
    utm_content = Column(String(100))

    # Attribution metadata
    first_touch = Column(Boolean, default=False)  # Is this the first event for this lead?
    conversion_event = Column(Boolean, default=False)  # Is this a conversion event?

    # ==================== CONTEXT ====================
    # User agent / device info
    user_agent = Column(String(500))
    device_type = Column(String(50))  # desktop, mobile, tablet
    browser = Column(String(100))
    os = Column(String(100))

    # Geo info
    ip_address = Column(String(50))
    geo_country = Column(String(2))
    geo_state = Column(String(50))
    geo_city = Column(String(100))
    geo_zip = Column(String(10))

    # ==================== TIMESTAMPS ====================
    event_timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Processing tracking
    processed_at = Column(DateTime)  # When event was processed for temperature/triggers
    triggered_actions = Column(JSON, default=list)  # List of actions triggered by this event

    def __repr__(self):
        return f"<AcquisitionEvent {self.event_type} lead={self.lead_id}>"

    @property
    def is_hot_signal(self) -> bool:
        """Check if this event is a hot signal"""
        hot_events = {
            EventType.MEETING_BOOKED.value,
            EventType.APPLICATION_STARTED.value,
            EventType.APPLICATION_COMPLETED.value,
            EventType.FORM_SUBMITTED.value,
            EventType.CALLBACK_REQUESTED.value,
            EventType.CHAT_INITIATED.value,
            EventType.VIDEO_WATCHED_75_PLUS.value,
            EventType.CALCULATOR_COMPLETED.value,
            EventType.DOCUMENT_UPLOADED.value,
        }
        return self.event_type in hot_events

    @property
    def is_warm_signal(self) -> bool:
        """Check if this event is a warm signal"""
        warm_events = {
            EventType.PRICING_PAGE_VIEW.value,
            EventType.CALCULATOR_STARTED.value,
            EventType.QUIZ_STARTED.value,
            EventType.QUIZ_COMPLETED.value,
            EventType.VIDEO_WATCHED_25_PLUS.value,
            EventType.VIDEO_WATCHED_50_PLUS.value,
            EventType.FAQ_VIEWED.value,
            EventType.BLOG_READ.value,
            EventType.EMAIL_LINK_CLICKED.value,
            EventType.SMS_REPLIED.value,
            EventType.MULTIPLE_PAGE_VIEWS.value,
        }
        return self.event_type in warm_events

    @property
    def is_conversion_event(self) -> bool:
        """Check if this is a conversion event for attribution"""
        conversion_events = {
            EventType.LEAD_CREATED.value,
            EventType.MEETING_BOOKED.value,
            EventType.APPLICATION_STARTED.value,
            EventType.LOAN_FUNDED.value,
        }
        return self.event_type in conversion_events


# Create composite indexes for common query patterns
Index('idx_events_lead_timestamp', AcquisitionEvent.lead_id, AcquisitionEvent.event_timestamp)
Index('idx_events_campaign_timestamp', AcquisitionEvent.campaign_instance_id, AcquisitionEvent.event_timestamp)
Index('idx_events_type_timestamp', AcquisitionEvent.event_type, AcquisitionEvent.event_timestamp)
Index('idx_events_org_timestamp', AcquisitionEvent.organization_id, AcquisitionEvent.event_timestamp)
Index('idx_events_anonymous_visitor', AcquisitionEvent.anonymous_visitor_id, AcquisitionEvent.event_timestamp)
