"""
Scheduler Appointment Routes - THIN WRAPPER
Original code consolidated into routes/scheduler_appointment_routes.py

Re-exports router, set_dependencies, set_enhanced_dependencies, and internal helpers
for backward compatibility with tests and other modules.
"""
from routes.scheduler_appointment_routes import (
    router,
    set_dependencies,
    set_enhanced_dependencies,
    _check_duplicate_booking,
    _check_lo_licensing,
    _ensure_lead_for_booking,
    _log_appointment_activity,
    _create_followup_task,
    _create_comm_failure_task,
    _check_memory_rate_limit,
    _memory_rate_limits,
)

__all__ = [
    "router",
    "set_dependencies",
    "set_enhanced_dependencies",
    "_check_duplicate_booking",
    "_check_lo_licensing",
    "_ensure_lead_for_booking",
    "_log_appointment_activity",
    "_create_followup_task",
    "_create_comm_failure_task",
    "_check_memory_rate_limit",
    "_memory_rate_limits",
]
