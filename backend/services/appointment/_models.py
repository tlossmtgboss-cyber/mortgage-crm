"""
Shared types, constants, and model loader for the appointment sub-package.

All sub-modules import from here to avoid circular dependencies and
duplicated definitions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class AppointmentSource(str, Enum):
    """Where an appointment operation originated."""
    MANUAL_UI = "manual_ui"
    PUBLIC_BOOKING = "public_booking"
    AI_RECEPTIONIST = "ai_receptionist"
    AI_SCHEDULER = "ai_scheduler"
    GOOGLE_SYNC = "google_sync"
    OUTLOOK_SYNC = "outlook_sync"
    SALESFORCE_SYNC = "salesforce_sync"
    API = "api"


class AppointmentEvent(str, Enum):
    """Events emitted by the service for downstream consumers."""
    CREATED = "appointment.created"
    CONFIRMED = "appointment.confirmed"
    UPDATED = "appointment.updated"
    CANCELLED = "appointment.cancelled"
    RESCHEDULED = "appointment.rescheduled"
    NO_SHOW = "appointment.no_show"
    COMPLETED = "appointment.completed"
    HOLD_CREATED = "appointment.hold_created"
    HOLD_RELEASED = "appointment.hold_released"
    HOLD_EXPIRED = "appointment.hold_expired"
    CONVERSION_TRACKED = "appointment.conversion_tracked"


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class SlotHold:
    """A soft hold on a time slot during an AI conversation (local DTO)."""
    hold_id: str
    lo_id: int
    organization_id: int
    start_time: "datetime"
    end_time: "datetime"
    created_at: "datetime"
    expires_at: "datetime"
    source: str
    released: bool = False


@dataclass
class ConflictCheckResult:
    """Result of a cross-source conflict check."""
    has_conflict: bool
    conflicting_source: Optional[str] = None
    conflicting_event_id: Optional[str] = None
    message: str = ""


@dataclass
class AppointmentResult:
    """Standardized result from appointment operations."""
    success: bool
    appointment_id: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    events_emitted: List[str] = field(default_factory=list)


# =============================================================================
# CONSTANTS
# =============================================================================

# Active statuses that occupy calendar time
ACTIVE_STATUSES = ("booked", "tentative", "confirmed")
TERMINAL_STATUSES = ("cancelled", "no_show", "completed", "rescheduled")

# Default buffer times in minutes
DEFAULT_BUFFER_BEFORE = 5
DEFAULT_BUFFER_AFTER = 5
DEFAULT_MIN_NOTICE_HOURS = 2
DEFAULT_DURATION_MINUTES = 30
DEFAULT_HOLD_TTL_SECONDS = 300  # 5 minutes
MAX_DATE_RANGE_DAYS = 90

DEFAULT_WORKING_HOURS = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
}


# =============================================================================
# EXCEPTIONS
# =============================================================================

class ConflictError(Exception):
    """Raised when a time slot conflict is detected."""
    pass


class AppointmentNotFoundError(Exception):
    """Raised when an appointment is not found or not accessible."""
    pass


# =============================================================================
# MODEL LAZY LOADER
# =============================================================================

_models_cache: Dict[str, Any] = {}


def get_model(name: str):
    """Lazy-load scheduler and CRM models to avoid circular imports."""
    if name in _models_cache:
        return _models_cache[name]

    model = None

    # Try smart_scheduler_models factory first (the canonical scheduler models)
    if name in (
        "Appointment", "SchedulerConfig", "AvailabilitySlot",
        "BlockedTime", "AppointmentType", "BookingLink",
        "AppointmentReminder", "SchedulerAuditLog", "RoutingRule",
        "SlotHold",
    ):
        try:
            from smart_scheduler_models import create_smart_scheduler_models
            from db import Base
            models = create_smart_scheduler_models(Base)
            # Cache all of them at once
            for k, v in models.items():
                _models_cache[k] = v
            model = _models_cache.get(name)
        except Exception as e:
            logger.debug(f"Could not load scheduler models via factory: {e}")

    # ScheduledAppointment (AI-booked, legacy table)
    if name == "ScheduledAppointment" and model is None:
        try:
            from services.smart_scheduler_service import ScheduledAppointment
            model = ScheduledAppointment
        except Exception as e:
            logger.debug(f"ScheduledAppointment model not available: {e}")

    # CalendarEvent (manual calendar)
    if name == "CalendarEvent" and model is None:
        try:
            import main
            model = main.CalendarEvent
        except Exception as e:
            logger.debug(f"CalendarEvent model not available: {e}")

    # CRMCalendarEvent (Salesforce-synced)
    if name == "CRMCalendarEvent" and model is None:
        try:
            from models.calendar_sync_models import CRMCalendarEvent
            model = CRMCalendarEvent
        except Exception as e:
            logger.debug(f"CRMCalendarEvent model not available: {e}")

    # Lead
    if name == "Lead" and model is None:
        try:
            from database.models.lead_loan import Lead
            model = Lead
        except Exception as e:
            logger.debug(f"Lead model not available: {e}")

    # User
    if name == "User" and model is None:
        try:
            from database.models.core import User
            model = User
        except Exception as e:
            logger.debug(f"User model not available: {e}")

    # Activity
    if name == "Activity" and model is None:
        try:
            from database.models.communication import Activity
            model = Activity
        except Exception as e:
            logger.debug(f"Activity model not available: {e}")

    # Task
    if name == "Task" and model is None:
        try:
            from database.models.task import Task
            model = Task
        except Exception as e:
            logger.debug(f"Task model not available: {e}")

    if model is not None:
        _models_cache[name] = model
    return model


# =============================================================================
# UTILITY HELPERS
# =============================================================================

def safe_enum_parse(enum_name: str, value: Optional[str], default: Optional[str]):
    """Safely parse an enum value from the smart_scheduler_models module."""
    if value is None:
        return None

    try:
        from smart_scheduler_models import (
            AppointmentStatus, MeetingType, MeetingMode,
        )
        enum_map = {
            "AppointmentStatus": AppointmentStatus,
            "MeetingType": MeetingType,
            "MeetingMode": MeetingMode,
        }
        enum_cls = enum_map.get(enum_name)
        if enum_cls:
            return enum_cls(value)
    except (ValueError, ImportError):
        pass

    # Return the raw string if enum parse fails -- the DB column may accept it
    return value if value else default


def mask_email(email: Optional[str]) -> str:
    """Mask email for logging: j***@example.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
