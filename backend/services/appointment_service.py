"""
Backward-compatible re-export. Canonical location: services/appointment/

All code has been decomposed into:
- services/appointment/service.py      -- AppointmentService class (CRUD, status transitions)
- services/appointment/hold_manager.py  -- SlotHold management
- services/appointment/conflict_checker.py -- Double-booking prevention, cross-source checks
- services/appointment/crm_bridge.py    -- Lead creation, activity logging, follow-up tasks
- services/appointment/notifications.py -- Email, SMS, Outlook calendar event dispatch
- services/appointment/_models.py       -- Shared types, constants, model lazy loader
"""

from services.appointment.service import AppointmentService  # noqa: F401
from services.appointment._models import (  # noqa: F401
    AppointmentEvent,
    AppointmentNotFoundError,
    AppointmentResult,
    AppointmentSource,
    ConflictCheckResult,
    ConflictError,
    SlotHold,
)
