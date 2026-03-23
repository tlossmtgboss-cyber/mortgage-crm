"""
Smart Scheduler Models - Perennia AI AI-Native Appointment Scheduling

Database models for the intelligent scheduling system that replaces third-party
tools like Calendly with AI-native appointment management.

Tables:
- SchedulerConfig: Team/user availability settings
- AvailabilitySlot: Individual time slots with dynamic pricing
- Appointment: Booked appointments with all context
- AppointmentType: Meeting type templates
- SchedulerRoutingRule: Intelligent appointment routing
- BlockedTime: PTO, holidays, blocked periods
- BookingLink: Shareable scheduling links
- AppointmentReminder: Multi-channel reminder tracking
- AppointmentStatusHistory: Status change audit trail
- SchedulerAuditLog: General audit log
- SlotHold: Soft hold / slot reservation during booking flows

Migrated from the factory pattern in smart_scheduler_models.py to proper
top-level SQLAlchemy model classes.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text,
    Enum as SQLEnum, Float, Numeric, Time, Date, UniqueConstraint, Index,
    CheckConstraint, text,
)
from sqlalchemy.orm import relationship
from datetime import datetime, time, timezone
import enum

from db import Base


# ============================================================================
# ENUMS (canonical definitions -- smart_scheduler_models re-exports these)
# ============================================================================

class AppointmentStatus(str, enum.Enum):
    AVAILABLE = "available"
    TENTATIVE = "tentative"
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    REMINDED = "reminded"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class MeetingType(str, enum.Enum):
    DISCOVERY_CALL = "discovery_call"
    PRE_APPROVAL_REVIEW = "pre_approval_review"
    APPLICATION_WALKTHROUGH = "application_walkthrough"
    DOCUMENT_REVIEW = "document_review"
    RATE_LOCK_DISCUSSION = "rate_lock_discussion"
    CLOSING_PREP = "closing_prep"
    POST_CLOSE_REVIEW = "post_close_review"
    REFERRAL_PARTNER_MEETING = "referral_partner_meeting"
    TEAM_SYNC = "team_sync"
    CUSTOM = "custom"


class MeetingMode(str, enum.Enum):
    VIDEO = "video"           # Zoom/Google Meet
    PHONE = "phone"           # Phone call
    IN_PERSON = "in_person"   # Office visit
    SCREEN_SHARE = "screen_share"  # Screen share session


class RoutingStrategy(str, enum.Enum):
    ROUND_ROBIN = "round_robin"       # Distribute evenly
    LOAD_BALANCED = "load_balanced"   # Based on current load
    EXPERTISE = "expertise"           # Match by skill/specialty
    RELATIONSHIP = "relationship"     # Existing LO relationship
    AVAILABILITY = "availability"     # First available
    AI_OPTIMIZED = "ai_optimized"     # AI determines best match


class ReminderChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    VOICE = "voice"  # AI voice reminder


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class DayOfWeek(str, enum.Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class SlotPriority(str, enum.Enum):
    PREFERRED = "preferred"    # Best times for meetings
    STANDARD = "standard"      # Normal availability
    OVERFLOW = "overflow"      # Available if needed
    BLOCKED = "blocked"        # Not available


class SlotHoldStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    CONVERTED = "converted"


class SchedulerConfig(Base):
    """
    Team or user-level scheduler configuration.
    Defines availability windows, buffer times, and scheduling preferences.
    """
    __tablename__ = "scheduler_configs"
    __table_args__ = (
        Index('ix_scheduler_configs_org_id', 'organization_id'),
        UniqueConstraint('organization_id', 'user_id', name='uq_scheduler_config_org_user'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Null = team-level config
    team_id = Column(Integer, nullable=True)  # For team-level settings

    # Name/description
    config_name = Column(String(100), nullable=False)
    description = Column(Text)

    # Timezone
    timezone = Column(String(50), default="America/Chicago")

    # Default meeting settings
    default_duration_minutes = Column(Integer, default=30)
    min_duration_minutes = Column(Integer, default=15)
    max_duration_minutes = Column(Integer, default=120)

    # Buffer times
    buffer_before_minutes = Column(Integer, default=5)
    buffer_after_minutes = Column(Integer, default=5)

    # Booking window
    min_notice_hours = Column(Integer, default=2)  # Can't book less than 2 hours ahead
    max_advance_days = Column(Integer, default=60)  # Can book up to 60 days ahead

    # Daily limits
    max_meetings_per_day = Column(Integer, default=8)
    max_consecutive_meetings = Column(Integer, default=3)

    # Break requirements
    lunch_break_start = Column(Time, default=time(12, 0))
    lunch_break_end = Column(Time, default=time(13, 0))
    enforce_lunch_break = Column(Boolean, default=True)

    # Working hours (JSON for flexibility)
    # Format: {"monday": {"start": "09:00", "end": "17:00", "enabled": true}, ...}
    working_hours = Column(JSON, default=dict)

    # Meeting preferences
    preferred_meeting_modes = Column(JSON, default=lambda: ["video", "phone"])
    default_meeting_mode = Column(SQLEnum(MeetingMode), default=MeetingMode.VIDEO)

    # Video conferencing
    zoom_enabled = Column(Boolean, default=True)
    google_meet_enabled = Column(Boolean, default=True)
    auto_create_meeting_link = Column(Boolean, default=True)

    # Routing preferences
    routing_strategy = Column(SQLEnum(RoutingStrategy), default=RoutingStrategy.RELATIONSHIP)
    accept_overflow_bookings = Column(Boolean, default=False)

    # AI settings
    ai_scheduling_enabled = Column(Boolean, default=True)
    ai_can_reschedule = Column(Boolean, default=True)
    ai_can_cancel = Column(Boolean, default=False)
    auto_reschedule_enabled = Column(Boolean, default=True)
    smart_reminders_enabled = Column(Boolean, default=True)

    # Landing page customization settings (JSON)
    landing_page_settings = Column(JSON, default=dict)

    # Notification preferences (JSON)
    # Format: {"email_reminder_24h": true, "sms_reminder_2h": true, "quiet_hours_enabled": false, ...}
    notification_settings = Column(JSON, default=dict)

    # Setup wizard tracking
    setup_completed = Column(Boolean, default=False)
    setup_progress = Column(JSON, default=lambda: {"completed_steps": [], "current_step": 0})

    # Feature toggles (JSON dict of feature_name -> bool)
    feature_toggles = Column(JSON, default=dict)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="scheduler_configs")
    availability_slots = relationship("AvailabilitySlot", back_populates="config", cascade="all, delete-orphan")
    appointment_types = relationship("SchedulerAppointmentType", back_populates="config", cascade="all, delete-orphan")


class AvailabilitySlot(Base):
    """
    Individual availability slots with dynamic attributes.
    Can represent recurring patterns or specific date overrides.
    """
    __tablename__ = "availability_slots"
    __table_args__ = (
        Index('ix_availability_date_user', 'specific_date', 'user_id'),
        Index('ix_availability_slots_org_id', 'organization_id'),
        UniqueConstraint('user_id', 'day_of_week', 'start_time', 'end_time', 'organization_id', name='uq_availability_recurring_slot'),
        UniqueConstraint('organization_id', 'user_id', 'specific_date', name='uq_avail_slot_org_user_date'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("scheduler_configs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Slot timing
    day_of_week = Column(SQLEnum(DayOfWeek), nullable=True)  # For recurring slots
    specific_date = Column(Date, nullable=True)  # For date-specific overrides
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Slot attributes
    priority = Column(SQLEnum(SlotPriority), default=SlotPriority.STANDARD)
    is_recurring = Column(Boolean, default=True)

    # Meeting type restrictions
    allowed_meeting_types = Column(JSON, default=list)  # Empty = all types allowed
    excluded_meeting_types = Column(JSON, default=list)

    # Capacity
    max_bookings = Column(Integer, default=1)  # For group sessions
    current_bookings = Column(Integer, default=0)

    # Dynamic pricing/priority (for AI optimization)
    slot_score = Column(Float, default=1.0)  # AI-calculated desirability

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    config = relationship("SchedulerConfig", back_populates="availability_slots")
    user = relationship("User", backref="scheduler_availability_slots")


class SchedulerAppointmentType(Base):
    """
    Meeting type templates with default settings.
    Defines what kinds of appointments can be booked.

    Note: Named SchedulerAppointmentType (not AppointmentType) to avoid
    collision with the document_followup.AppointmentType enum already
    registered in the models package.  The original __tablename__ is
    preserved as 'appointment_types'.
    """
    __tablename__ = "appointment_types"
    __table_args__ = (
        UniqueConstraint('organization_id', 'public_slug', name='uq_appt_type_org_slug'),
        Index('ix_appointment_types_org_id', 'organization_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("scheduler_configs.id", ondelete="CASCADE"), nullable=False)

    # Type identification
    type_key = Column(String(50), nullable=False)  # Internal key
    type_name = Column(String(100), nullable=False)  # Display name
    description = Column(Text)

    # Meeting settings
    meeting_type = Column(SQLEnum(MeetingType), default=MeetingType.CUSTOM)
    default_duration_minutes = Column(Integer, default=30)
    allowed_durations = Column(JSON, default=lambda: [15, 30, 45, 60])  # Minutes

    # Meeting modes
    allowed_modes = Column(JSON, default=lambda: ["video", "phone"])
    default_mode = Column(SQLEnum(MeetingMode), default=MeetingMode.VIDEO)

    # Booking rules
    min_notice_hours = Column(Integer, nullable=True)  # Override config
    max_advance_days = Column(Integer, nullable=True)  # Override config
    max_per_day = Column(Integer, nullable=True)  # Limit per day
    max_per_week = Column(Integer, nullable=True)  # Limit per week

    # Required context
    requires_loan_id = Column(Boolean, default=False)
    requires_lead_id = Column(Boolean, default=False)
    requires_contact_info = Column(Boolean, default=True)

    # Intake questions (JSON array)
    intake_questions = Column(JSON, default=list)

    # Confirmation/reminder settings
    send_confirmation = Column(Boolean, default=True)
    reminder_schedule = Column(JSON, default=lambda: [24, 1])  # Hours before: 24h and 1h

    # Routing
    assigned_users = Column(JSON, default=list)  # Specific users who can take this type
    routing_strategy = Column(SQLEnum(RoutingStrategy), nullable=True)  # Override

    # Display
    color = Column(String(20), default="#3b82f6")
    icon = Column(String(50), default="calendar")
    display_order = Column(Integer, default=0)

    # Public booking
    is_public = Column(Boolean, default=True)  # Can be booked via public link
    public_slug = Column(String(100), nullable=True)  # Per-org unique via __table_args__

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    config = relationship("SchedulerConfig", back_populates="appointment_types")
    appointments = relationship("Appointment", back_populates="appointment_type")


class Appointment(Base):
    """
    Booked appointments with full context.
    Central record for all scheduled meetings.
    """
    __tablename__ = "scheduler_appointments"
    __table_args__ = (
        Index('ix_appointment_datetime', 'scheduled_start', 'scheduled_end'),
        Index('ix_appointment_user', 'assigned_user_id', 'scheduled_start'),
        Index('ix_appointment_status', 'status'),
        Index('ix_appointment_org_user_start', 'organization_id', 'assigned_user_id', 'scheduled_start'),
        Index('ix_appt_conflict_check', 'assigned_user_id', 'status', 'scheduled_start', 'scheduled_end'),
        Index('ix_appt_attendee_status', 'attendee_email', 'status', 'scheduled_start'),
        Index('ix_appt_no_show_detection', 'status', 'scheduled_end', 'organization_id'),
        Index('ix_appt_org_status_start', 'organization_id', 'status', 'scheduled_start'),
        Index('ix_appt_org_created', 'organization_id', 'created_at'),
        # Enterprise: Prevent double-booking at DB level (defense-in-depth behind app-level conflict check)
        Index(
            'uq_appointment_no_double_book',
            'assigned_user_id', 'scheduled_start', 'scheduled_end',
            unique=True,
            postgresql_where=text("status NOT IN ('cancelled', 'rescheduled', 'no_show', 'completed')"),
        ),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    # Organization CASCADE: deleting an org removes all its appointments (business requirement —
    # org deletion is a full teardown; orphaned appointments would have no owner or context)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Reference IDs
    # AppointmentType SET NULL: deleting a type orphans appointments (they keep their data, just lose the type link)
    appointment_type_id = Column(Integer, ForeignKey("appointment_types.id", ondelete="SET NULL"), nullable=True)
    # User SET NULL: deleting a user orphans appointments (reassignment needed, not deletion —
    # appointments contain borrower data and compliance records that must be preserved)
    assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Related entities — SET NULL: lead/loan deletion should not cascade to appointment records
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)
    contact_id = Column(Integer, nullable=True)  # Reference to contact (no FK)

    # External reference (for linking to other systems)
    external_id = Column(String(100), nullable=True)
    external_source = Column(String(50), nullable=True)  # "calendly", "google", etc.

    # Meeting details
    title = Column(String(255), nullable=False)
    description = Column(Text)
    meeting_type = Column(SQLEnum(MeetingType), default=MeetingType.CUSTOM)
    meeting_mode = Column(SQLEnum(MeetingMode), default=MeetingMode.VIDEO)

    # Scheduling
    scheduled_start = Column(DateTime, nullable=False, index=True)
    scheduled_end = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    timezone = Column(String(50), default="America/Chicago")

    # Location/connection info
    location = Column(String(255))  # Physical address or "Video Call"
    video_link = Column(String(500))  # Zoom/Meet link
    phone_number = Column(String(20))  # For phone appointments
    dial_in_info = Column(Text)  # Conference dial-in details

    # Attendee info (for external bookings)
    attendee_name = Column(String(255))
    attendee_email = Column(String(255), index=True)
    attendee_phone = Column(String(20))
    attendee_notes = Column(Text)

    # Intake responses
    intake_responses = Column(JSON, default=dict)

    # Status tracking
    status = Column(SQLEnum(AppointmentStatus), default=AppointmentStatus.BOOKED)
    status_changed_at = Column(DateTime)
    status_changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Completion tracking
    completed_at = Column(DateTime)
    no_show_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancellation_reason = Column(Text)

    # Rescheduling
    rescheduled_from_id = Column(Integer, ForeignKey("scheduler_appointments.id", ondelete="SET NULL"), nullable=True)
    reschedule_count = Column(Integer, default=0)

    # AI/automation flags
    booked_by_ai = Column(Boolean, default=False)
    ai_booking_context = Column(JSON)  # AI decision context
    auto_confirmed = Column(Boolean, default=False)

    # Sync tracking
    google_calendar_event_id = Column(String(255))
    outlook_event_id = Column(String(255))
    last_synced_at = Column(DateTime)

    # Notes
    internal_notes = Column(Text)  # LO notes
    meeting_notes = Column(Text)  # Post-meeting notes

    # Optimistic locking
    version = Column(Integer, nullable=False, default=1, server_default="1")

    # Recovery tracking (no-show recovery workflow)
    recovery_step = Column(Integer, default=0, server_default="0")
    recovery_started_at = Column(DateTime, nullable=True)
    recovery_completed_at = Column(DateTime, nullable=True)
    recovery_opted_out = Column(Boolean, default=False, server_default="false")

    # Consent tracking
    communication_consent_at = Column(DateTime, nullable=True)
    communication_consent_source = Column(String(50), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Mapper args for optimistic locking
    __mapper_args__ = {"version_id_col": version}

    # Relationships
    appointment_type = relationship("SchedulerAppointmentType", back_populates="appointments")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id], backref="scheduler_assigned_appointments")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    status_changed_by_user = relationship("User", foreign_keys=[status_changed_by])
    rescheduled_from = relationship("Appointment", remote_side=[id])
    reminders = relationship("AppointmentReminder", back_populates="appointment", cascade="all, delete-orphan")
    status_history = relationship("AppointmentStatusHistory", back_populates="appointment", cascade="all, delete-orphan", order_by="AppointmentStatusHistory.changed_at")


class SchedulerRoutingRule(Base):
    """
    Intelligent routing rules for appointment assignment.
    Determines which team member gets which appointment.

    Note: Named SchedulerRoutingRule (not RoutingRule) to avoid collision
    with the routing_rule.RoutingRule model already registered in the
    models package.  The original __tablename__ is preserved as
    'scheduler_routing_rules'.
    """
    __tablename__ = "scheduler_routing_rules"
    __table_args__ = (
        Index('ix_routing_rules_org_id', 'organization_id'),
        Index('ix_routing_rules_active_priority', 'organization_id', 'is_active', 'priority'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule identification
    rule_name = Column(String(100), nullable=False)
    description = Column(Text)
    priority = Column(Integer, default=0)  # Higher = evaluated first

    # Conditions (JSON for flexibility)
    # Format: {"field": "meeting_type", "operator": "equals", "value": "discovery_call"}
    conditions = Column(JSON, default=list)

    # Matching criteria
    appointment_type_id = Column(Integer, ForeignKey("appointment_types.id", ondelete="SET NULL"), nullable=True)
    meeting_types = Column(JSON, default=list)  # List of MeetingType values
    lead_sources = Column(JSON, default=list)  # Route by lead source
    loan_amounts_min = Column(Numeric(18, 2), nullable=True)
    loan_amounts_max = Column(Numeric(18, 2), nullable=True)

    # Assignment
    routing_strategy = Column(SQLEnum(RoutingStrategy), default=RoutingStrategy.ROUND_ROBIN)
    assigned_users = Column(JSON, default=list)  # User IDs to route to
    fallback_users = Column(JSON, default=list)  # If primary unavailable

    # Expertise matching
    required_expertise = Column(JSON, default=list)  # Skills/certifications needed
    preferred_expertise = Column(JSON, default=list)  # Nice to have

    # Time-based rules
    active_days = Column(JSON, default=list)  # Days this rule applies
    active_hours_start = Column(Time, nullable=True)
    active_hours_end = Column(Time, nullable=True)

    # Load balancing settings
    max_daily_assignments = Column(Integer, nullable=True)
    max_weekly_assignments = Column(Integer, nullable=True)
    current_assignment_count = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    appointment_type = relationship("SchedulerAppointmentType")


class BlockedTime(Base):
    """
    Blocked time periods (PTO, holidays, focus time, etc.)
    """
    __tablename__ = "scheduler_blocked_times"
    __table_args__ = (
        Index('ix_blocked_time_range', 'start_datetime', 'end_datetime'),
        Index('ix_blocked_times_org_id', 'organization_id'),
        CheckConstraint("block_type IN ('pto', 'holiday', 'focus', 'custom', 'meeting', 'personal')", name='ck_blocked_time_block_type'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Null = company-wide

    # Block details
    title = Column(String(255), nullable=False)
    description = Column(Text)
    block_type = Column(String(50), default="custom")  # "pto", "holiday", "focus", "custom"

    # Time range
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(JSON)  # {"frequency": "weekly", "days": ["monday"], ...}
    recurrence_end_date = Column(Date, nullable=True)

    # Scope
    applies_to_all_users = Column(Boolean, default=False)  # Company holiday
    applies_to_teams = Column(JSON, default=list)  # Team IDs

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="scheduler_blocked_times")
    created_by = relationship("User", foreign_keys=[created_by_id])


class BookingLink(Base):
    """
    Shareable scheduling links for external booking.
    Like Calendly links but native to the platform.
    """
    __tablename__ = "scheduler_booking_links"
    __table_args__ = (
        UniqueConstraint('organization_id', 'slug', name='uq_booking_link_org_slug'),
        Index('ix_booking_links_org_id', 'organization_id'),
        Index('ix_booking_link_analytics', 'organization_id', 'is_active', 'last_booked_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Owner

    # Link identification
    slug = Column(String(100), nullable=False)  # URL slug -- per-org unique via __table_args__
    link_name = Column(String(100), nullable=False)
    description = Column(Text)

    # What can be booked
    appointment_type_ids = Column(JSON, default=list)  # Allowed types
    single_appointment_type_id = Column(Integer, ForeignKey("appointment_types.id", ondelete="SET NULL"), nullable=True)

    # Link settings
    is_public = Column(Boolean, default=True)
    requires_authentication = Column(Boolean, default=False)
    password_protected = Column(Boolean, default=False)
    password_hash = Column(String(255), nullable=True)

    # Branding
    custom_title = Column(String(255))
    custom_description = Column(Text)
    custom_logo_url = Column(String(500))
    custom_color = Column(String(20))

    # Booking limits
    max_bookings = Column(Integer, nullable=True)  # Total limit
    current_bookings = Column(Integer, default=0)
    max_per_person = Column(Integer, nullable=True)  # Per email address

    # Date range
    available_from = Column(DateTime, nullable=True)
    available_until = Column(DateTime, nullable=True)

    # Routing
    routing_strategy = Column(SQLEnum(RoutingStrategy), default=RoutingStrategy.RELATIONSHIP)
    assigned_users = Column(JSON, default=list)  # Route to specific users

    # Tracking
    view_count = Column(Integer, default=0)
    booking_count = Column(Integer, default=0)
    last_booked_at = Column(DateTime)

    # UTM tracking
    default_utm_source = Column(String(100))
    default_utm_medium = Column(String(100))
    default_utm_campaign = Column(String(100))

    # Status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="scheduler_booking_links")
    single_appointment_type = relationship("SchedulerAppointmentType")


class AppointmentReminder(Base):
    """
    Multi-channel reminder tracking for appointments.
    """
    __tablename__ = "scheduler_reminders"
    __table_args__ = (
        Index('ix_reminders_org_id', 'organization_id'),
        Index('ix_reminders_pending_delivery', 'status', 'scheduled_for', 'organization_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("scheduler_appointments.id", ondelete="CASCADE"), nullable=False)

    # Reminder settings
    channel = Column(SQLEnum(ReminderChannel), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)  # When to send
    hours_before = Column(Integer)  # X hours before appointment

    # Content
    message_template = Column(String(100))  # Template key
    custom_message = Column(Text)

    # Delivery tracking
    status = Column(SQLEnum(ReminderStatus), default=ReminderStatus.PENDING)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    failed_at = Column(DateTime)
    failure_reason = Column(Text)

    # Response tracking
    acknowledged_at = Column(DateTime)
    response_action = Column(String(50))  # "confirmed", "rescheduled", "cancelled"

    # External IDs
    external_message_id = Column(String(255))  # SMS/Email provider ID

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    appointment = relationship("Appointment", back_populates="reminders")


class AppointmentStatusHistory(Base):
    """
    Tracks every status change for an appointment, providing a full
    audit trail used by the timeline widget on the frontend.
    """
    __tablename__ = "appointment_status_history"
    __table_args__ = (
        Index('ix_appt_status_history_appt', 'appointment_id', 'changed_at'),
        Index('ix_appt_status_history_org', 'organization_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("scheduler_appointments.id", ondelete="CASCADE"), nullable=False)

    # Status transition
    previous_status = Column(String(30), nullable=True)  # Null for initial creation
    new_status = Column(String(30), nullable=False)

    # Who made the change
    changed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(255), nullable=True)  # Denormalized for display
    change_source = Column(String(50), default="manual")  # manual, ai, system, reminder, public

    # Notes and context
    notes = Column(Text, nullable=True)
    extra_data = Column("metadata", JSON, default=dict)  # Extra context (e.g., cancellation_reason, reschedule_from)

    # Timestamps
    changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    appointment = relationship("Appointment", back_populates="status_history")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])


class SchedulerAuditLog(Base):
    __tablename__ = 'scheduler_audit_log'
    __table_args__ = (
        Index('idx_scheduler_audit_org_ts', 'organization_id', 'created_at'),
        Index('idx_scheduler_audit_entity', 'entity_type', 'entity_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False)  # created, updated, cancelled, deleted, settings_changed
    entity_type = Column(String(50), nullable=False)  # appointment, booking_link, blocked_time, settings, appointment_type
    entity_id = Column(Integer, nullable=True)
    changes = Column(JSON, nullable=True)  # {field: {old: x, new: y}}
    booking_source = Column(String(30), nullable=True)  # authenticated, public_booking, ai_pipeline
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SlotHold(Base):
    """
    Soft hold / slot reservation during AI conversations or multi-step booking.
    TTL-based: auto-expires after a configurable duration (default 5 min).
    """
    __tablename__ = 'slot_holds'
    __table_args__ = (
        Index('idx_slot_holds_lo_active', 'lo_id', 'status', 'expires_at'),
        Index('idx_slot_holds_org_status', 'organization_id', 'status'),
        Index('idx_slot_holds_cleanup', 'status', 'expires_at'),
        CheckConstraint("status IN ('active', 'expired', 'released', 'converted')", name='ck_slot_hold_status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    lo_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    held_by = Column(String(50), nullable=False)  # 'ai_conversation', 'public_booking', 'manual'
    held_for_name = Column(String(200), nullable=True)
    held_for_phone = Column(String(30), nullable=True)
    held_for_email = Column(String(255), nullable=True)
    conversation_id = Column(String(100), nullable=True)  # Vapi call/conversation ID
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default=SlotHoldStatus.ACTIVE.value)
    converted_to_appointment_id = Column(Integer, ForeignKey("scheduler_appointments.id", ondelete="SET NULL"), nullable=True)
    converted_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
