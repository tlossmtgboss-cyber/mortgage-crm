"""
Scheduler Pydantic Models / Schemas
====================================
Backward-compatibility re-export wrapper.

All Pydantic schemas have been consolidated into schemas/scheduler.py.
This module re-exports every class so that existing imports like
    from scheduler_models import AppointmentCreate
continue to work without modification.
"""

from schemas.scheduler import (  # noqa: F401
    IntakeQuestion,
    WorkingHoursDay,
    SchedulerConfigCreate,
    SchedulerConfigUpdate,
    LandingPageSettings,
    AppointmentTypeCreate,
    AppointmentTypeUpdate,
    AppointmentTypeReorder,
    AvailabilitySlotCreate,
    AvailabilitySlotUpdate,
    AppointmentCreate,
    AppointmentUpdate,
    CancelAppointmentRequest,
    BlockedTimeCreate,
    BookingLinkCreate,
    AvailableSlotsRequest,
    PublicBookingConfirmRequest,
    PublicAvailableSlotsRequest,
    SlotRecommendation,
    WebsiteDemoBookingRequest,
)

__all__ = [
    "IntakeQuestion",
    "WorkingHoursDay",
    "SchedulerConfigCreate",
    "SchedulerConfigUpdate",
    "LandingPageSettings",
    "AppointmentTypeCreate",
    "AppointmentTypeUpdate",
    "AppointmentTypeReorder",
    "AvailabilitySlotCreate",
    "AvailabilitySlotUpdate",
    "AppointmentCreate",
    "AppointmentUpdate",
    "CancelAppointmentRequest",
    "BlockedTimeCreate",
    "BookingLinkCreate",
    "AvailableSlotsRequest",
    "PublicBookingConfirmRequest",
    "PublicAvailableSlotsRequest",
    "SlotRecommendation",
    "WebsiteDemoBookingRequest",
]
