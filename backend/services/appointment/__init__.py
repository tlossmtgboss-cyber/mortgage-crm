"""
Appointment service sub-package.

Canonical location for all appointment operations. Re-exports the main
service class and supporting types for backward compatibility.

Usage:
    from services.appointment import AppointmentService
    from services.appointment import ConflictCheckResult, SlotHold
"""

from services.appointment.service import AppointmentService
from services.appointment._models import (
    AppointmentEvent,
    AppointmentNotFoundError,
    AppointmentResult,
    AppointmentSource,
    ConflictCheckResult,
    ConflictError,
    SlotHold,
)

__all__ = [
    "AppointmentService",
    "AppointmentEvent",
    "AppointmentNotFoundError",
    "AppointmentResult",
    "AppointmentSource",
    "ConflictCheckResult",
    "ConflictError",
    "SlotHold",
]
