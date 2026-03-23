"""
Smart Scheduler Service  [DEPRECATED — Mar 2026]

WARNING: This module has ZERO multi-tenant (organization_id) isolation.
All queries return data across ALL organizations.

DO NOT add new features here. Use the tenant-aware routes instead:
  - scheduler_appointment_routes.py  (appointments, public booking)
  - scheduler_config_routes.py       (config CRUD)
  - routes/smart_scheduler_settings_routes.py  (settings UI)

Legacy assignment strategies (kept for reference only):
- Direct: Book directly with a specific LO
- Round Robin: Distribute appointments evenly among loan officers
- Priority: Assign based on LO priority/seniority
- Availability: Assign to first available LO (checks all calendar sources)
- Load Balanced: Assign to LO with fewest active appointments (real-time count)
"""

import logging
from datetime import datetime, timedelta, time, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, JSON, Text, func
from sqlalchemy.orm import Session
from database import Base, SessionLocal
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class SchedulingMethod(str, Enum):
    DIRECT = "direct"
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"
    AVAILABILITY = "availability"
    LOAD_BALANCED = "load_balanced"


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


# =============================================================================
# DATABASE MODELS
# =============================================================================

class SchedulerSettings(Base):
    """Per-organization scheduler configuration"""
    __tablename__ = "scheduler_settings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # Organization/user who owns settings
    organization_id = Column(Integer, index=True, nullable=True)

    # Scheduling method
    scheduling_method = Column(String(50), default=SchedulingMethod.ROUND_ROBIN.value)

    # Default appointment settings
    default_duration_minutes = Column(Integer, default=30)
    buffer_between_appointments = Column(Integer, default=15)  # minutes

    # Business hours (JSON: {"monday": {"start": "09:00", "end": "17:00"}, ...})
    business_hours = Column(JSON, default=lambda: {
        "monday": {"start": "09:00", "end": "17:00", "enabled": True},
        "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
        "friday": {"start": "09:00", "end": "17:00", "enabled": True},
        "saturday": {"start": "10:00", "end": "14:00", "enabled": True},
        "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
    })

    # Booking settings
    min_notice_hours = Column(Integer, default=2)  # Minimum hours in advance
    max_advance_days = Column(Integer, default=30)  # Maximum days in advance

    # Round robin tracking
    last_assigned_lo_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class LoanOfficerSchedule(Base):
    """Individual loan officer availability and priority"""
    __tablename__ = "loan_officer_schedules"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # References users table
    organization_id = Column(Integer, index=True, nullable=True)

    # LO Info (denormalized for quick access)
    lo_name = Column(String(255))
    lo_email = Column(String(255))
    lo_phone = Column(String(50), nullable=True)

    # Scheduling settings
    is_active = Column(Boolean, default=True)  # Available for scheduling
    priority = Column(Integer, default=1)  # Higher = more priority (for priority scheduling)
    max_daily_appointments = Column(Integer, default=8)
    max_weekly_appointments = Column(Integer, default=40)

    # Custom availability (overrides global business hours)
    # JSON: {"monday": {"start": "10:00", "end": "16:00"}, ...}
    custom_hours = Column(JSON, nullable=True)

    # Blocked times (JSON array of {"start": datetime, "end": datetime, "reason": str})
    blocked_times = Column(JSON, default=list)

    # Stats (kept for backward compat but real-time queries are preferred)
    total_appointments = Column(Integer, default=0)
    appointments_this_week = Column(Integer, default=0)
    appointments_today = Column(Integer, default=0)
    last_appointment_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ScheduledAppointment(Base):
    """Appointments scheduled through the smart scheduler"""
    __tablename__ = "scheduled_appointments"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(String(50), unique=True, index=True)  # APPT-XXXXXXXX
    organization_id = Column(Integer, index=True, nullable=True)

    # Loan Officer
    loan_officer_id = Column(Integer, index=True)
    lo_name = Column(String(255))
    lo_email = Column(String(255))

    # Contact/Lead
    contact_id = Column(Integer, nullable=True, index=True)
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    contact_phone = Column(String(50), nullable=True)

    # Appointment details
    appointment_type = Column(String(50), default="consultation")
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer, default=30)

    # Status
    status = Column(String(50), default=AppointmentStatus.SCHEDULED.value)

    # Meeting info
    meeting_link = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Tracking
    booked_via = Column(String(50), default="ai_assistant")  # ai_assistant, manual, api
    conversation_id = Column(String(255), nullable=True)

    # Calendar invite tracking
    customer_invite_sent = Column(Boolean, default=False)
    lo_invite_sent = Column(Boolean, default=False)
    lo_confirmation_sent = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


def ensure_scheduler_tables():
    """Create scheduler tables if they don't exist. Uses a SINGLE connection to avoid pool exhaustion."""
    from database import engine
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            # 1. Create PostgreSQL ENUM types first (safe if already exist)
            enum_definitions = [
                ("appointmentstatus", "'available','tentative','booked','confirmed','reminded','checked_in','completed','no_show','cancelled','rescheduled'"),
                ("meetingtype", "'discovery_call','pre_approval_review','application_walkthrough','document_review','rate_lock_discussion','closing_prep','post_close_review','referral_partner_meeting','team_sync','custom'"),
                ("meetingmode", "'video','phone','in_person','screen_share'"),
                ("routingstrategy", "'round_robin','load_balanced','expertise','relationship','availability','ai_optimized'"),
                ("dayofweek", "'monday','tuesday','wednesday','thursday','friday','saturday','sunday'"),
                ("slotpriority", "'preferred','standard','overflow','blocked'"),
                ("reminderchannel", "'email','sms','push','voice'"),
                ("reminderstatus", "'pending','sent','delivered','failed','acknowledged'"),
                ("slotholdstatus", "'active','expired','released','converted'"),
            ]
            for type_name, values in enum_definitions:
                conn.execute(text(f"""
                    DO $$ BEGIN
                        CREATE TYPE {type_name} AS ENUM ({values});
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$
                """))

            # 2. Create all scheduler tables via raw SQL (single connection, no pool pressure)
            conn.execute(text("""
                -- Legacy tables
                CREATE TABLE IF NOT EXISTS scheduler_settings (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    user_id INTEGER,
                    settings JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS loan_officer_schedules (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    user_id INTEGER,
                    day_of_week INTEGER,
                    start_time TIME,
                    end_time TIME,
                    is_available BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS scheduled_appointments (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    user_id INTEGER,
                    lead_id INTEGER,
                    loan_id INTEGER,
                    title VARCHAR(255),
                    description TEXT,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    status VARCHAR(50) DEFAULT 'scheduled',
                    meeting_type VARCHAR(50),
                    location VARCHAR(255),
                    video_link VARCHAR(500),
                    attendee_name VARCHAR(255),
                    attendee_email VARCHAR(255),
                    attendee_phone VARCHAR(20),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    cancelled_at TIMESTAMP
                );

                -- New scheduler tables (used by calendar_settings_routes.py)
                CREATE TABLE IF NOT EXISTS scheduler_configs (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    user_id INTEGER,
                    team_id INTEGER,
                    config_name VARCHAR(100) NOT NULL DEFAULT 'Default',
                    description TEXT,
                    timezone VARCHAR(50) DEFAULT 'America/Chicago',
                    default_duration_minutes INTEGER DEFAULT 30,
                    min_duration_minutes INTEGER DEFAULT 15,
                    max_duration_minutes INTEGER DEFAULT 120,
                    buffer_before_minutes INTEGER DEFAULT 5,
                    buffer_after_minutes INTEGER DEFAULT 5,
                    min_notice_hours INTEGER DEFAULT 2,
                    max_advance_days INTEGER DEFAULT 60,
                    max_meetings_per_day INTEGER DEFAULT 8,
                    max_consecutive_meetings INTEGER DEFAULT 3,
                    lunch_break_start TIME DEFAULT '12:00',
                    lunch_break_end TIME DEFAULT '13:00',
                    enforce_lunch_break BOOLEAN DEFAULT true,
                    working_hours JSONB DEFAULT '{}',
                    preferred_meeting_modes JSONB DEFAULT '["video","phone"]',
                    default_meeting_mode VARCHAR(20) DEFAULT 'video',
                    zoom_enabled BOOLEAN DEFAULT true,
                    google_meet_enabled BOOLEAN DEFAULT true,
                    auto_create_meeting_link BOOLEAN DEFAULT true,
                    routing_strategy VARCHAR(20) DEFAULT 'relationship',
                    accept_overflow_bookings BOOLEAN DEFAULT false,
                    ai_scheduling_enabled BOOLEAN DEFAULT true,
                    ai_can_reschedule BOOLEAN DEFAULT true,
                    ai_can_cancel BOOLEAN DEFAULT false,
                    auto_reschedule_enabled BOOLEAN DEFAULT true,
                    smart_reminders_enabled BOOLEAN DEFAULT true,
                    landing_page_settings JSONB DEFAULT '{}',
                    notification_settings JSONB DEFAULT '{}',
                    setup_completed BOOLEAN DEFAULT false,
                    setup_progress JSONB DEFAULT '{"completed_steps":[],"current_step":0}',
                    feature_toggles JSONB DEFAULT '{}',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_scheduler_configs_org_id ON scheduler_configs(organization_id);

                CREATE TABLE IF NOT EXISTS appointment_types (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    config_id INTEGER NOT NULL REFERENCES scheduler_configs(id) ON DELETE CASCADE,
                    type_key VARCHAR(50) NOT NULL,
                    type_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    meeting_type VARCHAR(30) DEFAULT 'custom',
                    default_duration_minutes INTEGER DEFAULT 30,
                    allowed_durations JSONB DEFAULT '[15,30,45,60]',
                    allowed_modes JSONB DEFAULT '["video","phone"]',
                    default_mode VARCHAR(20) DEFAULT 'video',
                    min_notice_hours INTEGER,
                    max_advance_days INTEGER,
                    max_per_day INTEGER,
                    max_per_week INTEGER,
                    requires_loan_id BOOLEAN DEFAULT false,
                    requires_lead_id BOOLEAN DEFAULT false,
                    requires_contact_info BOOLEAN DEFAULT true,
                    intake_questions JSONB DEFAULT '[]',
                    send_confirmation BOOLEAN DEFAULT true,
                    reminder_schedule JSONB DEFAULT '[24,1]',
                    assigned_users JSONB DEFAULT '[]',
                    routing_strategy VARCHAR(20),
                    color VARCHAR(20) DEFAULT '#3b82f6',
                    icon VARCHAR(50) DEFAULT 'calendar',
                    display_order INTEGER DEFAULT 0,
                    is_public BOOLEAN DEFAULT true,
                    public_slug VARCHAR(100),
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_appointment_types_org_id ON appointment_types(organization_id);

                CREATE TABLE IF NOT EXISTS scheduler_appointments (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    appointment_type_id INTEGER REFERENCES appointment_types(id) ON DELETE SET NULL,
                    assigned_user_id INTEGER,
                    created_by_user_id INTEGER,
                    lead_id INTEGER,
                    loan_id INTEGER,
                    contact_id INTEGER,
                    external_id VARCHAR(100),
                    external_source VARCHAR(50),
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    meeting_type VARCHAR(30) DEFAULT 'custom',
                    meeting_mode VARCHAR(20) DEFAULT 'video',
                    scheduled_start TIMESTAMP NOT NULL,
                    scheduled_end TIMESTAMP NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    timezone VARCHAR(50) DEFAULT 'America/Chicago',
                    location VARCHAR(255),
                    video_link VARCHAR(500),
                    phone_number VARCHAR(20),
                    dial_in_info TEXT,
                    attendee_name VARCHAR(255),
                    attendee_email VARCHAR(255),
                    attendee_phone VARCHAR(20),
                    attendee_notes TEXT,
                    intake_responses JSONB DEFAULT '{}',
                    status VARCHAR(30) DEFAULT 'booked',
                    status_changed_at TIMESTAMP,
                    status_changed_by INTEGER,
                    completed_at TIMESTAMP,
                    no_show_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    cancellation_reason TEXT,
                    rescheduled_from_id INTEGER,
                    reschedule_count INTEGER DEFAULT 0,
                    booked_by_ai BOOLEAN DEFAULT false,
                    ai_booking_context JSONB,
                    auto_confirmed BOOLEAN DEFAULT false,
                    google_calendar_event_id VARCHAR(255),
                    outlook_event_id VARCHAR(255),
                    last_synced_at TIMESTAMP,
                    internal_notes TEXT,
                    meeting_notes TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    recovery_step INTEGER DEFAULT 0,
                    recovery_started_at TIMESTAMP,
                    recovery_completed_at TIMESTAMP,
                    recovery_opted_out BOOLEAN DEFAULT false,
                    communication_consent_at TIMESTAMP,
                    communication_consent_source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_appointment_datetime ON scheduler_appointments(scheduled_start, scheduled_end);
                CREATE INDEX IF NOT EXISTS ix_appointment_org_user_start ON scheduler_appointments(organization_id, assigned_user_id, scheduled_start);

                CREATE TABLE IF NOT EXISTS scheduler_booking_links (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    user_id INTEGER,
                    slug VARCHAR(100) NOT NULL,
                    link_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    appointment_type_ids JSONB DEFAULT '[]',
                    single_appointment_type_id INTEGER REFERENCES appointment_types(id) ON DELETE SET NULL,
                    is_public BOOLEAN DEFAULT true,
                    requires_authentication BOOLEAN DEFAULT false,
                    password_protected BOOLEAN DEFAULT false,
                    password_hash VARCHAR(255),
                    custom_title VARCHAR(255),
                    custom_description TEXT,
                    custom_logo_url VARCHAR(500),
                    custom_color VARCHAR(20),
                    max_bookings INTEGER,
                    current_bookings INTEGER DEFAULT 0,
                    max_per_person INTEGER,
                    available_from TIMESTAMP,
                    available_until TIMESTAMP,
                    routing_strategy VARCHAR(20) DEFAULT 'relationship',
                    assigned_users JSONB DEFAULT '[]',
                    view_count INTEGER DEFAULT 0,
                    booking_count INTEGER DEFAULT 0,
                    last_booked_at TIMESTAMP,
                    default_utm_source VARCHAR(100),
                    default_utm_medium VARCHAR(100),
                    default_utm_campaign VARCHAR(100),
                    is_active BOOLEAN DEFAULT true,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_booking_links_org_id ON scheduler_booking_links(organization_id);

                CREATE TABLE IF NOT EXISTS scheduler_routing_rules (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    rule_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    priority INTEGER DEFAULT 0,
                    conditions JSONB DEFAULT '[]',
                    appointment_type_id INTEGER REFERENCES appointment_types(id) ON DELETE SET NULL,
                    routing_strategy VARCHAR(20) DEFAULT 'round_robin',
                    assigned_users JSONB DEFAULT '[]',
                    fallback_users JSONB DEFAULT '[]',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scheduler_blocked_times (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    user_id INTEGER,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    block_type VARCHAR(50) DEFAULT 'custom',
                    start_datetime TIMESTAMP NOT NULL,
                    end_datetime TIMESTAMP NOT NULL,
                    all_day BOOLEAN DEFAULT false,
                    is_recurring BOOLEAN DEFAULT false,
                    recurrence_pattern JSONB,
                    recurrence_end_date DATE,
                    applies_to_all_users BOOLEAN DEFAULT false,
                    applies_to_teams JSONB DEFAULT '[]',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS scheduler_reminders (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    appointment_id INTEGER REFERENCES scheduler_appointments(id) ON DELETE CASCADE,
                    channel VARCHAR(20) NOT NULL,
                    scheduled_for TIMESTAMP NOT NULL,
                    hours_before INTEGER,
                    message_template VARCHAR(100),
                    custom_message TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    sent_at TIMESTAMP,
                    delivered_at TIMESTAMP,
                    failed_at TIMESTAMP,
                    failure_reason TEXT,
                    acknowledged_at TIMESTAMP,
                    response_action VARCHAR(50),
                    external_message_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS appointment_status_history (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    appointment_id INTEGER REFERENCES scheduler_appointments(id) ON DELETE CASCADE,
                    previous_status VARCHAR(30),
                    new_status VARCHAR(30) NOT NULL,
                    changed_by_user_id INTEGER,
                    changed_by_name VARCHAR(255),
                    change_source VARCHAR(50) DEFAULT 'manual',
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scheduler_audit_log (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    user_id INTEGER,
                    action VARCHAR(50) NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id INTEGER,
                    changes JSONB,
                    booking_source VARCHAR(30),
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                );

                CREATE TABLE IF NOT EXISTS slot_holds (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    lo_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    held_by VARCHAR(50) NOT NULL,
                    held_for_name VARCHAR(200),
                    held_for_phone VARCHAR(30),
                    held_for_email VARCHAR(255),
                    conversation_id VARCHAR(100),
                    expires_at TIMESTAMP NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    converted_to_appointment_id INTEGER REFERENCES scheduler_appointments(id) ON DELETE SET NULL,
                    converted_at TIMESTAMP,
                    released_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                );
            """))

            # 3. Add organization_id to legacy tables if missing
            for table_name in ["scheduler_settings", "loan_officer_schedules", "scheduled_appointments"]:
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = :tbl AND column_name = 'organization_id'
                """), {"tbl": table_name})
                if not result.fetchone():
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS organization_id INTEGER"))
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_organization_id ON {table_name} (organization_id)"))
                    logger.info(f"Added organization_id column to {table_name}")

        logger.info("Smart Scheduler tables created/verified (legacy + new)")
    except Exception as e:
        logger.warning(f"Could not create Smart Scheduler tables: {e}")


# =============================================================================
# CROSS-SOURCE AVAILABILITY HELPERS
# =============================================================================

def _get_cross_source_busy_times(db: Session, user_id: int, start_dt: datetime, end_dt: datetime):
    """
    Gather all busy time blocks from all 3 calendar sources for a user.
    Returns a list of (start, end) tuples representing occupied time.
    """
    conflicts = []

    # Source 1: ScheduledAppointment (this module's appointments)
    try:
        sa_appts = db.query(ScheduledAppointment).filter(
            ScheduledAppointment.loan_officer_id == user_id,
            ScheduledAppointment.status.in_(["scheduled", "confirmed"]),
            ScheduledAppointment.start_time >= start_dt,
            ScheduledAppointment.start_time <= end_dt
        ).all()
        for a in sa_appts:
            if a.start_time and a.end_time:
                conflicts.append((a.start_time, a.end_time))
    except Exception as e:
        logger.debug(f"ScheduledAppointment cross-source check: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        import main
        CalendarEvent = main.CalendarEvent
        cal_events = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_dt,
            CalendarEvent.start_time <= end_dt
        ).all()
        for ev in cal_events:
            if ev.start_time and ev.end_time:
                conflicts.append((ev.start_time, ev.end_time))
    except Exception as ex:
        logger.debug(f"CalendarEvent cross-source check skipped: {ex}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_events = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_dt,
            CRMCalendarEvent.start_at <= end_dt
        ).all()
        for ev in crm_events:
            if ev.start_at and ev.end_at:
                conflicts.append((ev.start_at, ev.end_at))
    except Exception as ex:
        logger.debug(f"CRMCalendarEvent cross-source check skipped: {ex}")

    return conflicts


# =============================================================================
# SMART SCHEDULER SERVICE
# =============================================================================

class SmartSchedulerService:
    """Service for intelligent appointment scheduling.

    Always instantiate with a db session — never cache across requests.
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self._ensure_default_settings()

    def _ensure_default_settings(self):
        """Ensure default scheduler settings exist"""
        try:
            settings = self.db.query(SchedulerSettings).first()
            if not settings:
                settings = SchedulerSettings()
                self.db.add(settings)
                self.db.commit()
                logger.info("Created default scheduler settings")
        except Exception as e:
            logger.debug(f"Default settings check: {e}")

    def get_settings(self, user_id: int = None) -> SchedulerSettings:
        """Get scheduler settings"""
        query = self.db.query(SchedulerSettings)
        if user_id:
            query = query.filter(SchedulerSettings.user_id == user_id)
        return query.first()

    def update_settings(self, settings_data: Dict[str, Any], user_id: int = None) -> SchedulerSettings:
        """Update scheduler settings.

        BLOCKED: Use scheduler_config_routes.py instead.
        """
        raise RuntimeError(
            "SmartSchedulerService.update_settings() is permanently disabled — no tenant isolation. "
            "Use scheduler_config_routes.py instead."
        )

    def get_active_loan_officers(self) -> List[LoanOfficerSchedule]:
        """Get all active loan officers available for scheduling"""
        return self.db.query(LoanOfficerSchedule).filter(
            LoanOfficerSchedule.is_active == True
        ).order_by(LoanOfficerSchedule.priority.desc()).all()

    def add_loan_officer(self, user_id: int, name: str, email: str,
                         phone: str = None, priority: int = 1,
                         organization_id: int = None) -> LoanOfficerSchedule:
        """Add a loan officer to the scheduling pool.

        BLOCKED: Use scheduler_config_routes.py instead.
        """
        raise RuntimeError(
            "SmartSchedulerService.add_loan_officer() is permanently disabled — no tenant isolation. "
            "Use scheduler_config_routes.py instead."
        )

    def update_loan_officer(self, lo_id: int, updates: Dict[str, Any]) -> Optional[LoanOfficerSchedule]:
        """Update loan officer scheduling settings.

        BLOCKED: Use scheduler_config_routes.py instead.
        """
        raise RuntimeError(
            "SmartSchedulerService.update_loan_officer() is permanently disabled — no tenant isolation. "
            "Use scheduler_config_routes.py instead."
        )

    def _get_real_time_appointment_count(self, lo_user_id: int, period: str = "week") -> int:
        """Get real-time appointment count from the database instead of stale counters."""
        now = datetime.now(timezone.utc)
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == "week":
            # Monday of current week
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7)
        else:
            return 0

        count = self.db.query(func.count(ScheduledAppointment.id)).filter(
            ScheduledAppointment.loan_officer_id == lo_user_id,
            ScheduledAppointment.start_time >= start,
            ScheduledAppointment.start_time < end,
            ScheduledAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value
            ])
        ).scalar() or 0

        return count

    def assign_loan_officer(self, appointment_time: datetime = None) -> Optional[LoanOfficerSchedule]:
        """Assign a loan officer based on the configured scheduling method.

        BLOCKED: Use scheduler_appointment_routes.py (which uses scheduler_routing_service.py)
        for tenant-aware LO assignment.
        """
        raise RuntimeError(
            "SmartSchedulerService.assign_loan_officer() is permanently disabled — no tenant isolation. "
            "Use scheduler_routing_service.py via scheduler_appointment_routes.py instead."
        )

    def _assign_direct(self, los: List[LoanOfficerSchedule]) -> Optional[LoanOfficerSchedule]:
        """Direct booking — no routing, assign to the first (primary) LO.
        Used when there's a single LO or routing is not desired."""
        if not los:
            return None
        selected = los[0]
        logger.info(f"Direct assigned: {selected.lo_name}")
        return selected

    def _assign_round_robin(self, settings: SchedulerSettings,
                            los: List[LoanOfficerSchedule]) -> Optional[LoanOfficerSchedule]:
        """Assign using round robin - rotate through LOs evenly.

        Uses SELECT FOR UPDATE to prevent race conditions where two concurrent
        bookings could be assigned to the same LO.
        """
        if not los:
            return None

        # Lock the settings row to prevent concurrent reads of stale last_assigned_lo_id
        locked_settings = self.db.query(SchedulerSettings).with_for_update().filter(
            SchedulerSettings.id == settings.id
        ).first()

        if not locked_settings:
            return los[0]

        last_assigned_id = locked_settings.last_assigned_lo_id
        lo_ids = [lo.id for lo in los]

        if last_assigned_id is None or last_assigned_id not in lo_ids:
            # Start from first LO
            next_lo = los[0]
        else:
            # Find next LO in rotation
            current_idx = lo_ids.index(last_assigned_id)
            next_idx = (current_idx + 1) % len(los)
            next_lo = los[next_idx]

        # Update last assigned
        locked_settings.last_assigned_lo_id = next_lo.id
        self.db.commit()

        logger.info(f"Round robin assigned: {next_lo.lo_name}")
        return next_lo

    def _assign_by_priority(self, los: List[LoanOfficerSchedule],
                            appointment_time: datetime = None) -> Optional[LoanOfficerSchedule]:
        """Assign to highest priority LO who is available"""
        # LOs are already sorted by priority (desc) from query
        for lo in los:
            if self._is_lo_available(lo, appointment_time):
                logger.info(f"Priority assigned: {lo.lo_name} (priority: {lo.priority})")
                return lo

        # If no one is available at the time, return highest priority anyway
        logger.info(f"Priority assigned (no availability check): {los[0].lo_name}")
        return los[0] if los else None

    def _assign_by_availability(self, los: List[LoanOfficerSchedule],
                                appointment_time: datetime = None) -> Optional[LoanOfficerSchedule]:
        """Assign to first available LO"""
        for lo in los:
            if self._is_lo_available(lo, appointment_time):
                logger.info(f"Availability assigned: {lo.lo_name}")
                return lo

        # Return first LO if none specifically available
        return los[0] if los else None

    def _assign_load_balanced(self, los: List[LoanOfficerSchedule]) -> Optional[LoanOfficerSchedule]:
        """Assign to LO with fewest appointments this week (real-time count)"""
        if not los:
            return None

        # Use real-time COUNT query instead of stale counter columns
        lo_counts = []
        for lo in los:
            count = self._get_real_time_appointment_count(lo.id, "week")
            lo_counts.append((lo, count))

        lo_counts.sort(key=lambda x: x[1])
        selected = lo_counts[0][0]
        week_count = lo_counts[0][1]

        logger.info(f"Load balanced assigned: {selected.lo_name} ({week_count} appts this week)")
        return selected

    def _is_lo_available(self, lo: LoanOfficerSchedule, appointment_time: datetime = None) -> bool:
        """Check if LO is available at the given time.

        Checks all 3 calendar sources: ScheduledAppointment, CalendarEvent, CRMCalendarEvent.
        """
        if not appointment_time:
            return True

        settings = self.get_settings()
        buffer_mins = settings.buffer_between_appointments if settings else 15

        # Check blocked times (JSON on the LO record)
        blocked_times = lo.blocked_times or []
        for blocked in blocked_times:
            try:
                blocked_start = datetime.fromisoformat(blocked.get("start", ""))
                blocked_end = datetime.fromisoformat(blocked.get("end", ""))
                if blocked_start <= appointment_time <= blocked_end:
                    return False
            except (ValueError, TypeError):
                continue

        # Check daily capacity (real-time)
        if lo.max_daily_appointments:
            today_count = self._get_real_time_appointment_count(lo.id, "today")
            if today_count >= lo.max_daily_appointments:
                return False

        # Check all calendar sources for conflicts at the proposed time
        check_start = appointment_time - timedelta(minutes=buffer_mins)
        check_end = appointment_time + timedelta(minutes=(settings.default_duration_minutes if settings else 30) + buffer_mins)
        busy_times = _get_cross_source_busy_times(self.db, lo.id, check_start, check_end)

        for busy_start, busy_end in busy_times:
            # Apply buffer around busy times
            buffered_start = busy_start - timedelta(minutes=buffer_mins)
            buffered_end = busy_end + timedelta(minutes=buffer_mins)
            if appointment_time < buffered_end and (appointment_time + timedelta(minutes=(settings.default_duration_minutes if settings else 30))) > buffered_start:
                return False

        return True

    def book_appointment(
        self,
        contact_name: str,
        contact_email: str,
        appointment_time: datetime,
        contact_phone: str = None,
        contact_id: int = None,
        appointment_type: str = "consultation",
        duration_minutes: int = None,
        notes: str = None,
        conversation_id: str = None,
        loan_officer_id: int = None,
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """Book an appointment.

        BLOCKED: Use scheduler_appointment_routes.py for tenant-aware booking,
        or direct ORM creation of ScheduledAppointment with organization_id filtering.
        """
        raise RuntimeError(
            "SmartSchedulerService.book_appointment() is permanently disabled — no tenant isolation. "
            "Use scheduler_appointment_routes.py or direct ORM with organization_id filtering instead."
        )

    def get_appointment(self, appointment_id: str) -> Optional[ScheduledAppointment]:
        """Get appointment by ID"""
        return self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.appointment_id == appointment_id
        ).first()

    def cancel_appointment(self, appointment_id: str, reason: str = None) -> bool:
        """Cancel an appointment.

        BLOCKED: Use scheduler_appointment_routes.py for tenant-aware cancellation.
        """
        raise RuntimeError(
            "SmartSchedulerService.cancel_appointment() is permanently disabled — no tenant isolation. "
            "Use scheduler_appointment_routes.py instead."
        )

    def get_upcoming_appointments(self, loan_officer_id: int = None,
                                   days_ahead: int = 7) -> List[ScheduledAppointment]:
        """Get upcoming appointments"""
        query = self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.start_time >= datetime.now(timezone.utc),
            ScheduledAppointment.start_time <= datetime.now(timezone.utc) + timedelta(days=days_ahead),
            ScheduledAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value
            ])
        )

        if loan_officer_id:
            query = query.filter(ScheduledAppointment.loan_officer_id == loan_officer_id)

        return query.order_by(ScheduledAppointment.start_time).all()

    def get_appointments_in_range(self, loan_officer_id: int = None,
                                   start_date: str = None,
                                   end_date: str = None,
                                   days_ahead: int = 30) -> List[ScheduledAppointment]:
        """Get appointments within a date range"""
        # Parse date strings if provided
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                start_dt = datetime.now(timezone.utc)
        else:
            start_dt = datetime.now(timezone.utc)

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                end_dt = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        else:
            end_dt = datetime.now(timezone.utc) + timedelta(days=days_ahead)

        query = self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.start_time >= start_dt,
            ScheduledAppointment.start_time <= end_dt,
            ScheduledAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value
            ])
        )

        if loan_officer_id:
            query = query.filter(ScheduledAppointment.loan_officer_id == loan_officer_id)

        return query.order_by(ScheduledAppointment.start_time).all()


def get_scheduler_service(db_session=None) -> SmartSchedulerService:
    """HARD-DEPRECATED — this service has NO tenant isolation.

    Use scheduler_appointment_routes.py or scheduler_config_routes.py instead.
    Raises RuntimeError to prevent accidental use of unscoped queries.
    """
    import traceback
    caller = traceback.extract_stack(limit=3)[0]
    logger.error(
        f"BLOCKED get_scheduler_service() called from {caller.filename}:{caller.lineno} "
        f"— this service has NO tenant isolation. Use scheduler_appointment_routes instead."
    )
    raise RuntimeError(
        "smart_scheduler_service.get_scheduler_service() is permanently deprecated. "
        "This service has ZERO multi-tenant isolation. "
        "Use scheduler_appointment_routes.py with organization_id filtering instead."
    )
