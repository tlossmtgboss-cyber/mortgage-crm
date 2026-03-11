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
    """Create scheduler tables if they don't exist. Call during app startup, not at import."""
    from database import engine
    try:
        SchedulerSettings.__table__.create(engine, checkfirst=True)
        LoanOfficerSchedule.__table__.create(engine, checkfirst=True)
        ScheduledAppointment.__table__.create(engine, checkfirst=True)
        # Add organization_id columns if missing (tables may pre-date this column)
        from sqlalchemy import text, inspect
        insp = inspect(engine)
        for table_name, model in [
            ("scheduler_settings", SchedulerSettings),
            ("loan_officer_schedules", LoanOfficerSchedule),
            ("scheduled_appointments", ScheduledAppointment),
        ]:
            if table_name in insp.get_table_names():
                existing_cols = {c["name"] for c in insp.get_columns(table_name)}
                if "organization_id" not in existing_cols:
                    with engine.begin() as conn:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN organization_id INTEGER"
                        ))
                        conn.execute(text(
                            f"CREATE INDEX IF NOT EXISTS ix_{table_name}_organization_id "
                            f"ON {table_name} (organization_id)"
                        ))
                    logger.info(f"Added organization_id column to {table_name}")
        logger.info("Smart Scheduler tables created/verified")
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
