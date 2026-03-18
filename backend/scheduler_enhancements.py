"""
Smart Scheduler Enhancements - Advanced Features Module

This module extends the base scheduler with:
- Resource Management (skills, language, licensing, capacity)
- SLA & Load Balancing
- Advanced Scheduling Modes (Round Robin, Collective, Group, Series)
- Reminder System with multi-channel delivery
- No-Show Detection & Recovery
- Analytics & Reporting
- Soft Hold Mechanism for AI conversations
- Campaign Attribution & Tracking
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, Float, Date, Time, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, time, date, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from enum import Enum
from encryption_utils import EncryptedString
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ADDITIONAL ENUMS
# ============================================================================

class ResourceType(str, Enum):
    LOAN_OFFICER = "loan_officer"
    CONCIERGE = "concierge"
    PROCESSOR = "processor"
    UNDERWRITER = "underwriter"
    CLOSER = "closer"
    BUILDER_PARTNER = "builder_partner"
    REALTOR_PARTNER = "realtor_partner"
    TEAM_LEAD = "team_lead"


class ResourceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    VACATION = "vacation"
    TRAINING = "training"
    OUT_OF_OFFICE = "out_of_office"


class SchedulingMode(str, Enum):
    ONE_TO_ONE = "one_to_one"           # Single borrower with single resource
    ROUND_ROBIN = "round_robin"         # Automatic load distribution
    COLLECTIVE = "collective"           # Multiple resources required
    GROUP = "group"                     # Workshops, seminars
    SERIES = "series"                   # Sequential multi-step meetings


class SoftHoldStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    CONVERTED = "converted"
    EXPIRED = "expired"


class ReminderType(str, Enum):
    CONFIRMATION = "confirmation"
    REMINDER_24H = "reminder_24h"
    REMINDER_1H = "reminder_1h"
    REMINDER_15M = "reminder_15m"
    FOLLOW_UP = "follow_up"
    NO_SHOW = "no_show"
    RESCHEDULE_OFFER = "reschedule_offer"


class BookingChannel(str, Enum):
    AI_VOICE = "ai_voice"
    SMS = "sms"
    EMAIL = "email"
    VOICEMAIL_SMS = "voicemail_sms"
    WEB_LINK = "web_link"
    CRM_MANUAL = "crm_manual"
    PARTNER_PORTAL = "partner_portal"


# ============================================================================
# MODEL FACTORY
# ============================================================================

def create_scheduler_enhancement_models(Base):
    """Create enhanced scheduler models"""

    class SchedulerResource(Base):
        """
        Resource (staff member) management for scheduling.
        Tracks skills, availability, capacity, and performance.
        """
        __tablename__ = "scheduler_resources"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Resource info
        resource_type = Column(SQLEnum(ResourceType), default=ResourceType.LOAN_OFFICER)
        display_name = Column(String(255))
        title = Column(String(100))
        bio = Column(Text)
        photo_url = Column(String(500))

        # Contact
        direct_phone = Column(String(20))
        backup_phone = Column(String(20))
        calendar_email = Column(String(255))

        # Skills & Expertise
        skills = Column(JSON, default=list)  # ["FHA", "VA", "Jumbo", "First-Time Buyer"]
        product_expertise = Column(JSON, default=list)  # Product types they specialize in
        certifications = Column(JSON, default=list)

        # Language capabilities
        languages = Column(JSON, default=lambda: ["en"])  # ["en", "es", "zh"]
        primary_language = Column(String(10), default="en")

        # Licensing
        licensed_states = Column(JSON, default=list)  # ["TX", "CA", "FL"]
        nmls_id = Column(String(50))

        # Capacity & Load
        max_daily_appointments = Column(Integer, default=8)
        max_weekly_appointments = Column(Integer, default=35)
        current_daily_load = Column(Integer, default=0)
        current_weekly_load = Column(Integer, default=0)
        sla_target_hours = Column(Float, default=24.0)  # Response SLA

        # Status
        status = Column(SQLEnum(ResourceStatus), default=ResourceStatus.ACTIVE)
        status_reason = Column(String(255))
        status_until = Column(DateTime)  # For vacation/out_of_office

        # Performance metrics
        total_appointments = Column(Integer, default=0)
        completed_appointments = Column(Integer, default=0)
        no_show_count = Column(Integer, default=0)
        cancellation_count = Column(Integer, default=0)
        avg_rating = Column(Float, default=5.0)
        conversion_rate = Column(Float, default=0.0)  # Appointments to applications

        # Routing preferences
        accept_new_leads = Column(Boolean, default=True)
        accept_existing_clients = Column(Boolean, default=True)
        accept_partner_referrals = Column(Boolean, default=True)
        routing_weight = Column(Float, default=1.0)  # For weighted distribution

        # Settings
        auto_accept_bookings = Column(Boolean, default=True)
        send_calendar_invites = Column(Boolean, default=True)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        user = relationship("User", backref="scheduler_resource")


    class SoftHold(Base):
        """
        Temporary slot holds during AI conversations.
        Prevents double-booking while AI is working with a client.
        """
        __tablename__ = "scheduler_soft_holds"
        __table_args__ = (
            Index('ix_soft_hold_expires', 'expires_at'),
            Index('ix_soft_hold_slot', 'slot_start', 'resource_id'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Slot being held
        slot_start = Column(DateTime, nullable=False)
        slot_end = Column(DateTime, nullable=False)
        resource_id = Column(Integer, ForeignKey("scheduler_resources.id"), nullable=True)

        # Hold details
        hold_duration_minutes = Column(Integer, default=5)
        expires_at = Column(DateTime, nullable=False)
        status = Column(SQLEnum(SoftHoldStatus), default=SoftHoldStatus.ACTIVE)

        # Context
        channel = Column(SQLEnum(BookingChannel))
        session_id = Column(String(255))  # AI conversation session ID
        contact_phone = Column(String(20))
        contact_email = Column(String(255))

        # Conversion tracking
        converted_to_appointment_id = Column(Integer, ForeignKey("scheduler_appointments.id"), nullable=True)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        released_at = Column(DateTime)
        converted_at = Column(DateTime)


    class ReminderProfile(Base):
        """
        Reminder schedules for appointment types.
        Defines when and how reminders are sent.
        """
        __tablename__ = "scheduler_reminder_profiles"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Profile info
        profile_name = Column(String(100), nullable=False)
        description = Column(Text)

        # Linked to appointment type (optional)
        appointment_type_id = Column(Integer, ForeignKey("appointment_types.id"), nullable=True)

        # Reminder schedule (JSON array)
        # [{"type": "confirmation", "channel": "email", "immediate": true},
        #  {"type": "reminder_24h", "channel": "sms", "hours_before": 24},
        #  {"type": "reminder_1h", "channel": "sms", "hours_before": 1}]
        reminder_schedule = Column(JSON, default=list)

        # Content templates
        confirmation_template = Column(Text)
        reminder_template = Column(Text)
        no_show_template = Column(Text)
        follow_up_template = Column(Text)

        # Reschedule link settings
        include_reschedule_link = Column(Boolean, default=True)
        include_cancel_link = Column(Boolean, default=True)

        # Reply handling
        enable_confirmation_reply = Column(Boolean, default=True)  # "Reply C to confirm"
        enable_reschedule_reply = Column(Boolean, default=True)   # "Reply R to reschedule"

        # Status
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    class SchedulerAnalytics(Base):
        """
        Analytics and metrics tracking for scheduler performance.
        Aggregated daily/weekly/monthly stats.
        """
        __tablename__ = "scheduler_analytics"
        __table_args__ = (
            Index('ix_analytics_date_resource', 'date', 'resource_id'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Period
        date = Column(Date, nullable=False)
        period_type = Column(String(20), default="daily")  # daily, weekly, monthly

        # Resource (null = company-wide)
        resource_id = Column(Integer, ForeignKey("scheduler_resources.id"), nullable=True)

        # Booking metrics
        total_bookings = Column(Integer, default=0)
        completed_appointments = Column(Integer, default=0)
        no_shows = Column(Integer, default=0)
        cancellations = Column(Integer, default=0)
        rescheduled = Column(Integer, default=0)

        # Rate metrics
        show_rate = Column(Float, default=0.0)
        no_show_rate = Column(Float, default=0.0)
        cancellation_rate = Column(Float, default=0.0)

        # Time metrics
        avg_time_to_book_hours = Column(Float, default=0.0)
        avg_meeting_duration_minutes = Column(Float, default=0.0)

        # Conversion metrics
        appointments_to_applications = Column(Integer, default=0)
        applications_to_fundings = Column(Integer, default=0)
        conversion_rate = Column(Float, default=0.0)

        # Channel breakdown (JSON)
        bookings_by_channel = Column(JSON, default=dict)
        # {"ai_voice": 10, "sms": 5, "web_link": 15, ...}

        # Time slot popularity (JSON)
        popular_time_slots = Column(JSON, default=dict)
        # {"9:00": 5, "10:00": 8, "14:00": 10, ...}

        # Day popularity (JSON)
        popular_days = Column(JSON, default=dict)
        # {"monday": 10, "tuesday": 15, ...}

        # Revenue impact
        estimated_revenue = Column(Float, default=0.0)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    class CampaignBooking(Base):
        """
        Campaign attribution for bookings.
        Tracks voicemail drops, SMS campaigns, etc.
        """
        __tablename__ = "scheduler_campaign_bookings"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Campaign info
        campaign_id = Column(String(100))
        campaign_name = Column(String(255))
        campaign_type = Column(String(50))  # "voicemail_drop", "sms_blast", "email_campaign"

        # Source tracking
        channel = Column(SQLEnum(BookingChannel))
        utm_source = Column(String(100))
        utm_medium = Column(String(100))
        utm_campaign = Column(String(100))

        # Partner attribution
        partner_id = Column(Integer)
        partner_type = Column(String(50))  # "realtor", "builder"
        partner_name = Column(String(255))

        # Contact
        contact_phone = Column(String(20))
        contact_email = Column(String(255))
        contact_name = Column(String(255))

        # Funnel tracking
        voicemail_sent_at = Column(DateTime)
        sms_reply_at = Column(DateTime)
        booking_started_at = Column(DateTime)
        booking_completed_at = Column(DateTime)
        appointment_kept_at = Column(DateTime)
        converted_to_application_at = Column(DateTime)
        funded_at = Column(DateTime)

        # Linked entities
        appointment_id = Column(Integer, ForeignKey("scheduler_appointments.id"), nullable=True)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

        # ROI tracking
        cost_per_contact = Column(Float, default=0.0)
        revenue_generated = Column(Float, default=0.0)
        roi = Column(Float, default=0.0)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    class GroupSession(Base):
        """
        Group/workshop scheduling for seminars, training, etc.
        Allows multiple attendees for a single time slot.
        """
        __tablename__ = "scheduler_group_sessions"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Session info
        title = Column(String(255), nullable=False)
        description = Column(Text)
        session_type = Column(String(50))  # "homebuyer_seminar", "rate_workshop", etc.

        # Scheduling
        scheduled_start = Column(DateTime, nullable=False)
        scheduled_end = Column(DateTime, nullable=False)
        timezone = Column(String(50), default="America/Chicago")

        # Capacity
        max_attendees = Column(Integer, default=20)
        min_attendees = Column(Integer, default=1)
        current_attendees = Column(Integer, default=0)
        waitlist_enabled = Column(Boolean, default=True)
        waitlist_count = Column(Integer, default=0)

        # Host/presenter
        host_resource_id = Column(Integer, ForeignKey("scheduler_resources.id"))
        co_host_ids = Column(JSON, default=list)

        # Location
        meeting_mode = Column(String(20), default="video")  # video, in_person, hybrid
        location = Column(String(255))
        video_link = Column(String(500))

        # Registration
        registration_open = Column(Boolean, default=True)
        registration_deadline = Column(DateTime)
        require_approval = Column(Boolean, default=False)

        # Attendees (JSON array of registrations)
        attendees = Column(JSON, default=list)
        waitlist = Column(JSON, default=list)

        # Status
        status = Column(String(20), default="scheduled")  # scheduled, in_progress, completed, cancelled

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    class SeriesSchedule(Base):
        """
        Series scheduling for sequential multi-step meetings.
        E.g., Discovery → Pre-approval → Application review
        """
        __tablename__ = "scheduler_series"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Series info
        series_name = Column(String(255), nullable=False)
        description = Column(Text)

        # Steps (JSON array)
        # [{"order": 1, "appointment_type_id": 1, "days_after_previous": 0},
        #  {"order": 2, "appointment_type_id": 2, "days_after_previous": 3},
        #  {"order": 3, "appointment_type_id": 3, "days_after_previous": 7}]
        steps = Column(JSON, default=list)

        # Linked contact
        contact_id = Column(Integer)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

        # Progress tracking
        current_step = Column(Integer, default=1)
        completed_steps = Column(JSON, default=list)  # List of appointment IDs

        # Status
        status = Column(String(20), default="active")  # active, paused, completed, cancelled

        # Timestamps
        started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        completed_at = Column(DateTime)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    class CalendarSync(Base):
        """
        External calendar synchronization tracking.
        Google Calendar, Outlook integration.

        Security: access_token and refresh_token are encrypted at rest using
        Fernet symmetric encryption (via EncryptedString TypeDecorator).
        Encryption/decryption is transparent to application code -- reading
        these columns returns plaintext, writing stores ciphertext.
        """
        __tablename__ = "scheduler_calendar_sync"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # User
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

        # Provider
        provider = Column(String(50), nullable=False)  # "google", "outlook", "apple"
        provider_account_id = Column(String(255))
        calendar_id = Column(String(255))
        calendar_name = Column(String(255))

        # Auth — encrypted at rest via Fernet (EncryptedString TypeDecorator)
        access_token = Column(EncryptedString, nullable=True)
        refresh_token = Column(EncryptedString, nullable=True)
        token_expires_at = Column(DateTime)

        # Sync settings
        sync_enabled = Column(Boolean, default=True)
        sync_direction = Column(String(20), default="bidirectional")  # to_provider, from_provider, bidirectional
        sync_busy_time_only = Column(Boolean, default=False)

        # Status
        last_sync_at = Column(DateTime)
        last_sync_status = Column(String(20))
        sync_error = Column(Text)

        # Timestamps
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        @property
        def is_token_expired(self) -> bool:
            """Check if the access token has expired."""
            if self.token_expires_at is None:
                return True
            now = datetime.now(timezone.utc)
            expires = self.token_expires_at
            if expires.tzinfo is None:
                from datetime import timezone as _tz
                expires = expires.replace(tzinfo=_tz.utc)
            return now >= expires

        @property
        def has_valid_credentials(self) -> bool:
            """Check if this sync entry has usable OAuth credentials."""
            return bool(self.access_token) and (
                not self.is_token_expired or bool(self.refresh_token)
            )


    class IntakeQuestion(Base):
        """
        Custom intake questions for booking forms.
        Supports multiple question types and conditional logic.
        """
        __tablename__ = "scheduler_intake_questions"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

        # Linked to appointment type
        appointment_type_id = Column(Integer, ForeignKey("appointment_types.id"), nullable=False)

        # Question details
        question_key = Column(String(50), nullable=False)
        question_text = Column(Text, nullable=False)
        question_type = Column(String(20), default="text")  # text, select, multi_select, date, number, boolean, phone, email

        # Options (for select/multi_select)
        options = Column(JSON, default=list)

        # Validation
        is_required = Column(Boolean, default=False)
        min_length = Column(Integer)
        max_length = Column(Integer)
        validation_regex = Column(String(255))

        # Conditional display
        # {"field": "employment_type", "operator": "equals", "value": "self_employed"}
        show_if = Column(JSON)

        # Display
        display_order = Column(Integer, default=0)
        placeholder = Column(String(255))
        help_text = Column(Text)

        # Status
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    return {
        'SchedulerResource': SchedulerResource,
        'SoftHold': SoftHold,
        'ReminderProfile': ReminderProfile,
        'SchedulerAnalytics': SchedulerAnalytics,
        'CampaignBooking': CampaignBooking,
        'GroupSession': GroupSession,
        'SeriesSchedule': SeriesSchedule,
        'CalendarSync': CalendarSync,
        'IntakeQuestion': IntakeQuestion
    }


# ============================================================================
# DEFAULT REMINDER PROFILES
# ============================================================================

DEFAULT_REMINDER_PROFILES = [
    {
        'profile_name': 'Standard',
        'description': 'Default reminder schedule for most appointment types',
        'reminder_schedule': [
            {"type": "confirmation", "channel": "email", "immediate": True},
            {"type": "confirmation", "channel": "sms", "immediate": True},
            {"type": "reminder_24h", "channel": "email", "hours_before": 24},
            {"type": "reminder_24h", "channel": "sms", "hours_before": 24},
            {"type": "reminder_1h", "channel": "sms", "hours_before": 1}
        ],
        'include_reschedule_link': True,
        'include_cancel_link': True,
        'enable_confirmation_reply': True,
        'enable_reschedule_reply': True
    },
    {
        'profile_name': 'High-Touch',
        'description': 'More frequent reminders for important appointments',
        'reminder_schedule': [
            {"type": "confirmation", "channel": "email", "immediate": True},
            {"type": "confirmation", "channel": "sms", "immediate": True},
            {"type": "reminder_24h", "channel": "email", "hours_before": 24},
            {"type": "reminder_24h", "channel": "sms", "hours_before": 24},
            {"type": "reminder_1h", "channel": "email", "hours_before": 1},
            {"type": "reminder_1h", "channel": "sms", "hours_before": 1},
            {"type": "reminder_15m", "channel": "sms", "hours_before": 0.25}
        ],
        'include_reschedule_link': True,
        'include_cancel_link': True,
        'enable_confirmation_reply': True,
        'enable_reschedule_reply': True
    },
    {
        'profile_name': 'Minimal',
        'description': 'Basic confirmation only',
        'reminder_schedule': [
            {"type": "confirmation", "channel": "email", "immediate": True}
        ],
        'include_reschedule_link': True,
        'include_cancel_link': True,
        'enable_confirmation_reply': False,
        'enable_reschedule_reply': False
    }
]


# ============================================================================
# PYDANTIC SCHEMAS FOR API
# ============================================================================

class ResourceCreate(BaseModel):
    user_id: int
    resource_type: str = "loan_officer"
    display_name: Optional[str] = None
    title: Optional[str] = None
    direct_phone: Optional[str] = None
    skills: List[str] = []
    product_expertise: List[str] = []
    languages: List[str] = ["en"]
    licensed_states: List[str] = []
    nmls_id: Optional[str] = None
    max_daily_appointments: int = 8
    max_weekly_appointments: int = 35


class ResourceUpdate(BaseModel):
    display_name: Optional[str] = None
    title: Optional[str] = None
    direct_phone: Optional[str] = None
    skills: Optional[List[str]] = None
    product_expertise: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    licensed_states: Optional[List[str]] = None
    status: Optional[str] = None
    status_reason: Optional[str] = None
    max_daily_appointments: Optional[int] = None
    routing_weight: Optional[float] = None


class SoftHoldCreate(BaseModel):
    slot_start: datetime
    slot_end: datetime
    resource_id: Optional[int] = None
    channel: str = "ai_voice"
    session_id: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    hold_duration_minutes: int = 5


class GroupSessionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    session_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    max_attendees: int = 20
    host_resource_id: int
    meeting_mode: str = "video"
    location: Optional[str] = None


class CampaignBookingCreate(BaseModel):
    campaign_id: str
    campaign_name: str
    campaign_type: str
    channel: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    partner_id: Optional[int] = None
    partner_type: Optional[str] = None
    partner_name: Optional[str] = None


class AnalyticsQuery(BaseModel):
    start_date: date
    end_date: date
    resource_id: Optional[int] = None
    period_type: str = "daily"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_show_rate(completed: int, total: int) -> float:
    """Calculate appointment show rate"""
    if total == 0:
        return 0.0
    return round((completed / total) * 100, 2)


def calculate_no_show_rate(no_shows: int, total: int) -> float:
    """Calculate no-show rate"""
    if total == 0:
        return 0.0
    return round((no_shows / total) * 100, 2)


def get_optimal_slot_score(slot_datetime: datetime, resource_load: int, max_load: int) -> float:
    """
    Calculate an optimal slot score based on:
    - Time of day preference
    - Day of week preference
    - Current resource load
    """
    score = 1.0
    hour = slot_datetime.hour
    day = slot_datetime.weekday()

    # Time preferences (9-11 AM and 2-4 PM are optimal)
    if 9 <= hour <= 11:
        score += 0.3
    elif 14 <= hour <= 16:
        score += 0.2
    elif hour < 9 or hour >= 17:
        score -= 0.2

    # Day preferences (Tue-Thu are optimal)
    if day in [1, 2, 3]:  # Tuesday, Wednesday, Thursday
        score += 0.1
    elif day == 0:  # Monday
        score -= 0.1
    elif day == 4:  # Friday
        score -= 0.1

    # Load factor
    if max_load > 0:
        load_factor = resource_load / max_load
        if load_factor < 0.5:
            score += 0.1  # Room for more
        elif load_factor > 0.8:
            score -= 0.2  # Getting full

    return round(score, 2)


def parse_natural_language_time(text: str, base_date: date = None) -> Optional[datetime]:
    """
    Parse natural language time expressions.
    Supports: "tomorrow afternoon", "Thursday at 2pm", "next week", etc.
    """
    import re
    from datetime import datetime, timedelta

    if base_date is None:
        base_date = datetime.now().date()

    text = text.lower().strip()

    # Tomorrow
    if "tomorrow" in text:
        target_date = base_date + timedelta(days=1)
        if "morning" in text:
            return datetime.combine(target_date, time(9, 0))
        elif "afternoon" in text:
            return datetime.combine(target_date, time(14, 0))
        elif "evening" in text:
            return datetime.combine(target_date, time(17, 0))
        else:
            return datetime.combine(target_date, time(10, 0))

    # Day names
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day_name in enumerate(days):
        if day_name in text:
            current_day = base_date.weekday()
            days_ahead = i - current_day
            if days_ahead <= 0:
                days_ahead += 7
            target_date = base_date + timedelta(days=days_ahead)

            # Check for time
            time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2) or 0)
                period = time_match.group(3)
                if period == 'pm' and hour < 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0
                return datetime.combine(target_date, time(hour, minute))
            else:
                return datetime.combine(target_date, time(10, 0))

    # Next week
    if "next week" in text:
        target_date = base_date + timedelta(days=7)
        return datetime.combine(target_date, time(10, 0))

    # Specific time patterns
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = time_match.group(3)
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        return datetime.combine(base_date, time(hour, minute))

    return None


def generate_ics_content(appointment: dict) -> str:
    """Generate ICS content. Delegates to canonical RFC 5545 implementation.

    Uses ``services.ics_generator.generate_appointment_ics`` which accepts
    a dict and returns bytes; this wrapper decodes to str for backward compat.
    """
    from services.ics_generator import generate_appointment_ics

    return generate_appointment_ics(appointment).decode("utf-8")
