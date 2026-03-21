"""
Scheduler shared helpers — re-export layer.

This module was split into focused sub-modules for maintainability:
  - _core.py            Dependency injection storage and wiring
  - _auth.py            Auth helpers (get_current_user, _get_org_id, _is_scheduler_admin)
  - _rate_limiting.py   Rate limiting (Redis with in-memory fallback), IP extraction
  - _input_validation.py  Input sanitization, URL/phone validation, Turnstile CAPTCHA
  - _audit.py           Audit logging (_audit_log)
  - _conflicts.py       Appointment conflict & duplicate booking detection
  - _crm_integration.py CRM helpers (lead creation, activity logging, tasks, LO licensing)
  - _availability.py    Cross-source conflicts, timezone, unified slot generation engine

All public symbols are re-exported here for backward compatibility.
Existing imports like ``from routes.scheduler._helpers import get_current_user``
continue to work without modification.
"""

# --- Core: DI storage ---
from routes.scheduler._core import (  # noqa: F401
    set_dependencies,
    set_enhanced_dependencies,
    get_models,
    get_enhanced_models,
)

# --- Auth ---
from routes.scheduler._auth import (  # noqa: F401
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
)

# --- Rate limiting & IP ---
from routes.scheduler._rate_limiting import (  # noqa: F401
    _get_client_ip,
    _get_rate_limit_redis,
    _check_rate_limit,
    _check_memory_rate_limit,
    _is_private_ip,
    _is_trusted_proxy,
    _RATE_LIMIT_WINDOW,
    _RATE_LIMIT_MAX_PUBLIC,
    _RATE_LIMIT_MAX_AUTHENTICATED,
    _memory_rate_limits,
)

# --- Input validation & Turnstile ---
from routes.scheduler._input_validation import (  # noqa: F401
    _sanitize_text,
    _mask_email,
    _validate_url,
    _validate_phone,
    _sanitize_public_error,
    _verify_turnstile_token,
    _TURNSTILE_SECRET_KEY,
    _IS_PRODUCTION,
)

# --- Audit logging ---
from routes.scheduler._audit import _audit_log  # noqa: F401

# --- Conflict detection ---
from routes.scheduler._conflicts import (  # noqa: F401
    _check_appointment_conflict,
    _check_duplicate_booking,
)

# --- CRM integration ---
from routes.scheduler._crm_integration import (  # noqa: F401
    _log_appointment_activity,
    _ensure_lead_for_booking,
    _create_followup_task,
    _create_comm_failure_task,
    _check_lo_licensing,
)

# --- Availability & slot generation ---
from routes.scheduler._availability import (  # noqa: F401
    _get_user_timezone,
    _convert_utc_to_user_tz,
    _get_cross_source_conflicts,
    _has_cross_source_conflict,
    _get_cross_source_conflicts_batch,
    _generate_available_slots,
)


# ============================================================================
# HELPERS DICT (for backward-compatible injection into sub-modules)
# ============================================================================

# ============================================================================
# MODULE __getattr__ — backward-compatible access to DI variables
# ============================================================================
# Tests do ``import routes.scheduler._helpers as sar; sar._models = {...}``
# After decomposition, DI variables live in _core.py. This __getattr__
# proxies reads so that ``sar._models`` returns ``_core._models``.
# Writes (``sar._models = {}``) go into this module's __dict__ and are
# detected by get_models() in _core.py.

_DI_PROXY_ATTRS = ('_models', '_enhanced_models', '_get_db', '_get_current_user_func')


def __getattr__(name):
    if name in _DI_PROXY_ATTRS:
        import routes.scheduler._core as _core
        return getattr(_core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_shared_helpers() -> dict:
    """Return a dict of all shared helper functions for sub-module injection."""
    return {
        '_check_appointment_conflict': _check_appointment_conflict,
        '_check_duplicate_booking': _check_duplicate_booking,
        '_log_appointment_activity': _log_appointment_activity,
        '_ensure_lead_for_booking': _ensure_lead_for_booking,
        '_create_followup_task': _create_followup_task,
        '_check_lo_licensing': _check_lo_licensing,
        '_get_user_timezone': _get_user_timezone,
        '_convert_utc_to_user_tz': _convert_utc_to_user_tz,
        '_generate_available_slots': _generate_available_slots,
        '_audit_log': _audit_log,
        '_validate_url': _validate_url,
        '_validate_phone': _validate_phone,
        '_mask_email': _mask_email,
        '_sanitize_text': _sanitize_text,
        '_sanitize_public_error': _sanitize_public_error,
        '_create_comm_failure_task': _create_comm_failure_task,
        '_get_cross_source_conflicts': _get_cross_source_conflicts,
        '_has_cross_source_conflict': _has_cross_source_conflict,
        '_get_cross_source_conflicts_batch': _get_cross_source_conflicts_batch,
        '_check_rate_limit': _check_rate_limit,
        '_get_client_ip': _get_client_ip,
        '_verify_turnstile_token': _verify_turnstile_token,
    }
