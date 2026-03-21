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
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
    _get_user_timezone,
    _check_rate_limit,
    _check_memory_rate_limit,
    _memory_rate_limits,
    _sanitize_text,
    _mask_email,
    _validate_url,
    _sanitize_public_error,
    _verify_turnstile_token,
    _audit_log,
    _get_cross_source_conflicts,
    _has_cross_source_conflict,
    _check_appointment_conflict,
    _check_duplicate_booking,
    _check_lo_licensing,
    _ensure_lead_for_booking,
    _log_appointment_activity,
    _create_followup_task,
    _create_comm_failure_task,
    _generate_available_slots,
)

# DI proxy — tests do ``sar._models = {...}`` to mock models
_DI_PROXY_ATTRS = ('_models', '_enhanced_models', '_get_db', '_get_current_user_func')


def __getattr__(name):
    if name in _DI_PROXY_ATTRS:
        import routes.scheduler._core as _core
        return getattr(_core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "router",
    "set_dependencies",
    "set_enhanced_dependencies",
    "get_current_user",
    "_get_org_id",
    "_is_scheduler_admin",
    "_get_user_timezone",
    "_check_rate_limit",
    "_check_memory_rate_limit",
    "_memory_rate_limits",
    "_sanitize_text",
    "_mask_email",
    "_validate_url",
    "_sanitize_public_error",
    "_verify_turnstile_token",
    "_audit_log",
    "_get_cross_source_conflicts",
    "_has_cross_source_conflict",
    "_check_appointment_conflict",
    "_check_duplicate_booking",
    "_check_lo_licensing",
    "_ensure_lead_for_booking",
    "_log_appointment_activity",
    "_create_followup_task",
    "_create_comm_failure_task",
    "_generate_available_slots",
]
