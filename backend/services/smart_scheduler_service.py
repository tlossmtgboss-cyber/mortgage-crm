"""
Smart Scheduler Service

AI-powered appointment scheduling with multiple assignment strategies:
- Round Robin: Distribute appointments evenly among loan officers
- Priority: Assign based on LO priority/seniority
- Availability: Assign to first available LO
- Load Balanced: Assign to LO with fewest active appointments
"""

import os
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, JSON, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database import Base, engine, SessionLocal
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
    """Global scheduler configuration"""
    __tablename__ = "scheduler_settings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # Organization/user who owns settings

    # Scheduling method
    scheduling_method = Column(String(50), default=SchedulingMethod.ROUND_ROBIN.value)

    # Default appointment settings
    default_duration_minutes = Column(Integer, default=30)
    buffer_between_appointments = Column(Integer, default=15)  # minutes

    # Business hours (JSON: {"monday": {"start": "09:00", "end": "17:00"}, ...})
    business_hours = Column(JSON, default={
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LoanOfficerSchedule(Base):
    """Individual loan officer availability and priority"""
    __tablename__ = "loan_officer_schedules"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # References users table

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
    blocked_times = Column(JSON, default=[])

    # Stats
    total_appointments = Column(Integer, default=0)
    appointments_this_week = Column(Integer, default=0)
    appointments_today = Column(Integer, default=0)
    last_appointment_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledAppointment(Base):
    """Appointments scheduled through the smart scheduler"""
    __tablename__ = "scheduled_appointments"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(String(50), unique=True, index=True)  # APPT-XXXXXXXX

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


# Create tables
try:
    SchedulerSettings.__table__.create(engine, checkfirst=True)
    LoanOfficerSchedule.__table__.create(engine, checkfirst=True)
    ScheduledAppointment.__table__.create(engine, checkfirst=True)
    logger.info("Smart Scheduler tables created/verified")
except Exception as e:
    logger.warning(f"Could not create Smart Scheduler tables: {e}")


# =============================================================================
# SMART SCHEDULER SERVICE
# =============================================================================

class SmartSchedulerService:
    """Service for intelligent appointment scheduling"""

    def __init__(self, db_session=None):
        self.db = db_session or SessionLocal()
        self._ensure_default_settings()

    def _ensure_default_settings(self):
        """Ensure default scheduler settings exist"""
        settings = self.db.query(SchedulerSettings).first()
        if not settings:
            settings = SchedulerSettings()
            self.db.add(settings)
            self.db.commit()
            logger.info("Created default scheduler settings")

    def get_settings(self, user_id: int = None) -> SchedulerSettings:
        """Get scheduler settings"""
        query = self.db.query(SchedulerSettings)
        if user_id:
            query = query.filter(SchedulerSettings.user_id == user_id)
        return query.first()

    def update_settings(self, settings_data: Dict[str, Any], user_id: int = None) -> SchedulerSettings:
        """Update scheduler settings"""
        settings = self.get_settings(user_id)
        if not settings:
            settings = SchedulerSettings(user_id=user_id)
            self.db.add(settings)

        for key, value in settings_data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        self.db.commit()
        self.db.refresh(settings)
        return settings

    def get_active_loan_officers(self) -> List[LoanOfficerSchedule]:
        """Get all active loan officers available for scheduling"""
        return self.db.query(LoanOfficerSchedule).filter(
            LoanOfficerSchedule.is_active == True
        ).order_by(LoanOfficerSchedule.priority.desc()).all()

    def add_loan_officer(self, user_id: int, name: str, email: str,
                         phone: str = None, priority: int = 1) -> LoanOfficerSchedule:
        """Add a loan officer to the scheduling pool"""
        lo = LoanOfficerSchedule(
            user_id=user_id,
            lo_name=name,
            lo_email=email,
            lo_phone=phone,
            priority=priority,
            is_active=True
        )
        self.db.add(lo)
        self.db.commit()
        self.db.refresh(lo)
        logger.info(f"Added loan officer to scheduler: {name} ({email})")
        return lo

    def update_loan_officer(self, lo_id: int, updates: Dict[str, Any]) -> Optional[LoanOfficerSchedule]:
        """Update loan officer scheduling settings"""
        lo = self.db.query(LoanOfficerSchedule).filter(LoanOfficerSchedule.id == lo_id).first()
        if not lo:
            return None

        for key, value in updates.items():
            if hasattr(lo, key):
                setattr(lo, key, value)

        self.db.commit()
        self.db.refresh(lo)
        return lo

    def assign_loan_officer(self, appointment_time: datetime = None) -> Optional[LoanOfficerSchedule]:
        """
        Assign a loan officer based on the configured scheduling method.

        Returns the assigned LoanOfficerSchedule or None if no one is available.
        """
        settings = self.get_settings()
        active_los = self.get_active_loan_officers()

        if not active_los:
            logger.warning("No active loan officers available for scheduling")
            return None

        method = settings.scheduling_method

        if method == SchedulingMethod.DIRECT.value:
            return self._assign_direct(active_los)
        elif method == SchedulingMethod.ROUND_ROBIN.value:
            return self._assign_round_robin(settings, active_los)
        elif method == SchedulingMethod.PRIORITY.value:
            return self._assign_by_priority(active_los, appointment_time)
        elif method == SchedulingMethod.AVAILABILITY.value:
            return self._assign_by_availability(active_los, appointment_time)
        elif method == SchedulingMethod.LOAD_BALANCED.value:
            return self._assign_load_balanced(active_los)
        else:
            # Default to round robin
            return self._assign_round_robin(settings, active_los)

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
        """Assign using round robin - rotate through LOs evenly"""
        if not los:
            return None

        last_assigned_id = settings.last_assigned_lo_id
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
        settings.last_assigned_lo_id = next_lo.id
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
        """Assign to LO with fewest appointments this week"""
        if not los:
            return None

        # Sort by appointments this week (ascending)
        sorted_los = sorted(los, key=lambda x: x.appointments_this_week or 0)
        selected = sorted_los[0]

        logger.info(f"Load balanced assigned: {selected.lo_name} ({selected.appointments_this_week} appts this week)")
        return selected

    def _is_lo_available(self, lo: LoanOfficerSchedule, appointment_time: datetime = None) -> bool:
        """Check if LO is available at the given time"""
        if not appointment_time:
            return True

        # Check blocked times
        blocked_times = lo.blocked_times or []
        for blocked in blocked_times:
            blocked_start = datetime.fromisoformat(blocked.get("start", ""))
            blocked_end = datetime.fromisoformat(blocked.get("end", ""))
            if blocked_start <= appointment_time <= blocked_end:
                return False

        # Check existing appointments
        existing = self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.loan_officer_id == lo.id,
            ScheduledAppointment.start_time <= appointment_time,
            ScheduledAppointment.end_time > appointment_time,
            ScheduledAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value
            ])
        ).first()

        return existing is None

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
    ) -> Dict[str, Any]:
        """
        Book an appointment with automatic or specified LO assignment.

        Returns booking details including assigned LO and calendar info.
        """
        import uuid

        settings = self.get_settings()
        duration = duration_minutes or settings.default_duration_minutes

        # Assign loan officer
        if loan_officer_id:
            lo = self.db.query(LoanOfficerSchedule).filter(
                LoanOfficerSchedule.id == loan_officer_id
            ).first()
        else:
            lo = self.assign_loan_officer(appointment_time)

        if not lo:
            return {
                "success": False,
                "error": "No loan officers available for scheduling"
            }

        # Generate appointment ID
        appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"

        # Calculate end time
        end_time = appointment_time + timedelta(minutes=duration)

        # Create appointment record
        appointment = ScheduledAppointment(
            appointment_id=appt_id,
            loan_officer_id=lo.id,
            lo_name=lo.lo_name,
            lo_email=lo.lo_email,
            contact_id=contact_id,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            appointment_type=appointment_type,
            start_time=appointment_time,
            end_time=end_time,
            duration_minutes=duration,
            notes=notes,
            conversation_id=conversation_id,
            booked_via="ai_assistant"
        )

        self.db.add(appointment)

        # Update LO stats
        lo.total_appointments = (lo.total_appointments or 0) + 1
        lo.appointments_this_week = (lo.appointments_this_week or 0) + 1
        lo.appointments_today = (lo.appointments_today or 0) + 1
        lo.last_appointment_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(appointment)

        logger.info(f"Appointment booked: {appt_id} with {lo.lo_name} at {appointment_time}")

        return {
            "success": True,
            "appointment_id": appt_id,
            "loan_officer": {
                "id": lo.id,
                "name": lo.lo_name,
                "email": lo.lo_email,
                "phone": lo.lo_phone
            },
            "contact": {
                "name": contact_name,
                "email": contact_email,
                "phone": contact_phone
            },
            "appointment": {
                "type": appointment_type,
                "start_time": appointment_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_minutes": duration,
                "display_time": appointment_time.strftime("%A, %B %d at %I:%M %p")
            },
            "title": f"Mortgage Consultation - {contact_name}"
        }

    def get_appointment(self, appointment_id: str) -> Optional[ScheduledAppointment]:
        """Get appointment by ID"""
        return self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.appointment_id == appointment_id
        ).first()

    def cancel_appointment(self, appointment_id: str, reason: str = None) -> bool:
        """Cancel an appointment"""
        appointment = self.get_appointment(appointment_id)
        if not appointment:
            return False

        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.cancelled_at = datetime.utcnow()
        if reason:
            appointment.internal_notes = f"Cancelled: {reason}"

        # Update LO stats
        lo = self.db.query(LoanOfficerSchedule).filter(
            LoanOfficerSchedule.id == appointment.loan_officer_id
        ).first()
        if lo:
            lo.appointments_this_week = max(0, (lo.appointments_this_week or 1) - 1)

        self.db.commit()
        logger.info(f"Appointment cancelled: {appointment_id}")
        return True

    def get_upcoming_appointments(self, loan_officer_id: int = None,
                                   days_ahead: int = 7) -> List[ScheduledAppointment]:
        """Get upcoming appointments"""
        query = self.db.query(ScheduledAppointment).filter(
            ScheduledAppointment.start_time >= datetime.utcnow(),
            ScheduledAppointment.start_time <= datetime.utcnow() + timedelta(days=days_ahead),
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
                start_dt = datetime.utcnow()
        else:
            start_dt = datetime.utcnow()

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                end_dt = datetime.utcnow() + timedelta(days=days_ahead)
        else:
            end_dt = datetime.utcnow() + timedelta(days=days_ahead)

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


# Global service instance
_scheduler_service = None


def get_scheduler_service(db_session=None) -> SmartSchedulerService:
    """Get the smart scheduler service instance"""
    global _scheduler_service
    if _scheduler_service is None or db_session:
        _scheduler_service = SmartSchedulerService(db_session)
    return _scheduler_service
