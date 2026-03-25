"""
Smart Scheduler Service — MODEL-ONLY SHIM

The service logic was deleted (Mar 2026) because it had ZERO multi-tenant
isolation. Only the SQLAlchemy model classes are kept here so that the 3
files below can continue to query the ``scheduled_appointments`` table:

  - services/unified_calendar_service.py
  - services/smart_docs/appointment_intelligence_service.py
  - agents/qualification_agent.py

The canonical scheduler lives in routes/scheduler/ and database/models/scheduler.py.
Do NOT add new service logic here.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from database import Base

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS (kept for backward-compat imports)
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
# MODELS — thin ORM mapping to legacy tables
# =============================================================================

class ScheduledAppointment(Base):
    """Legacy scheduled_appointments table (read/write by 3 service files)."""
    __tablename__ = "scheduled_appointments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(String(50), unique=True, index=True)
    organization_id = Column(Integer, index=True, nullable=True)

    loan_officer_id = Column(Integer, index=True)
    lo_name = Column(String(255))
    lo_email = Column(String(255))

    contact_id = Column(Integer, nullable=True, index=True)
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    contact_phone = Column(String(50), nullable=True)

    appointment_type = Column(String(50), default="consultation")
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer, default=30)

    status = Column(String(50), default=AppointmentStatus.SCHEDULED.value)

    meeting_link = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)

    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    booked_via = Column(String(50), default="ai_assistant")
    conversation_id = Column(String(255), nullable=True)

    customer_invite_sent = Column(Boolean, default=False)
    lo_invite_sent = Column(Boolean, default=False)
    lo_confirmation_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
