"""
Scheduler Appointment Routes - THIN BACKWARD-COMPATIBLE WRAPPER

All route logic has been decomposed into focused modules under routes/scheduler/:
  - _helpers.py:       Shared helpers (auth, rate limiting, sanitization, conflict detection, CRM, slot engine)
  - appointments.py:   Appointment CRUD, status transitions, timeline
  - availability.py:   Availability slots CRUD, authenticated available-slots endpoint
  - blocked_times.py:  Blocked time CRUD (lunch breaks, OOO, capacity blocks)
  - booking_links.py:  Booking link CRUD endpoints
  - public_booking.py: Public booking endpoints (no auth required, rate-limited)
  - ai_scheduling.py:  AI slot recommendations, no-show risk scoring
  - email_testing.py:  Email service status and test endpoints

This file re-exports the combined router and all helper functions/symbols needed
by tests and other modules (smart_scheduler_routes.py, scheduler_enhanced_routes.py,
inline_legacy_routes.py, etc.) for backward compatibility.
"""

from fastapi import APIRouter

# Import the aggregated scheduler router from the sub-package
from routes.scheduler import scheduler_router

# Import shared helpers for backward-compatible re-export
from routes.scheduler._helpers import (
    set_dependencies as _set_helpers_deps,
    set_enhanced_dependencies,
    get_shared_helpers,
    # Auth helpers
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
    _get_user_timezone,
    # Rate limiting
    _check_rate_limit,
    _check_memory_rate_limit,
    _memory_rate_limits,
    # Input sanitization
    _sanitize_text,
    _mask_email,
    _validate_url,
    _sanitize_public_error,
    # Turnstile
    _verify_turnstile_token,
    # Audit
    _audit_log,
    # Conflict detection
    _get_cross_source_conflicts,
    _has_cross_source_conflict,
    _check_appointment_conflict,
    _check_duplicate_booking,
    # CRM helpers
    _log_appointment_activity,
    _ensure_lead_for_booking,
    _create_followup_task,
    _create_comm_failure_task,
    _check_lo_licensing,
    # Slot engine
    _generate_available_slots,
)

# Import the public_booking sub-module for backward compat (some modules import set_dependencies from it)
from routes.scheduler.public_booking import (
    set_dependencies as _set_public_booking_deps,
)

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# COMBINED ROUTER
# ============================================================================

router = APIRouter()
router.include_router(scheduler_router)


# ============================================================================
# DEPENDENCY INJECTION (backward-compatible interface)
# ============================================================================

def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies for all scheduler sub-modules.

    Called from smart_scheduler_routes.py and inline_legacy_routes.py.
    Wires up the shared helpers and all sub-module dependency injection.
    """
    # Set dependencies on the shared helpers module (single source of truth)
    _set_helpers_deps(get_db_func, get_current_user_func, models_dict)

    # Wire up legacy sub-modules that still use their own set_dependencies
    _shared_helpers = get_shared_helpers()

    # Public booking still has its own set_dependencies for historical reasons
    _set_public_booking_deps(get_db_func, get_current_user_func, models_dict, helpers=_shared_helpers)

    # Note: appointments_crud.py and blocked_time.py were deprecated and removed.
    # Their routers were superseded by appointments.py and blocked_times.py.


# ============================================================================
# BACKWARD-COMPATIBLE EXPORTS
# ============================================================================

# These symbols are imported by:
# - backend/scheduler_appointment_routes.py (thin wrapper at project root)
# - backend/scheduler_enhanced_routes.py
# - backend/smart_scheduler_routes.py
# - backend/routes/inline_legacy_routes.py
# - backend/tests/test_scheduler_integration.py
# - backend/tests/test_scheduler_ops_intelligence.py
# - backend/tests/test_scheduler_routes.py
# - backend/tests/test_scheduler_timezone.py

__all__ = [
    "router",
    "set_dependencies",
    "set_enhanced_dependencies",
    # Helpers (used by tests)
    "_check_duplicate_booking",
    "_check_lo_licensing",
    "_ensure_lead_for_booking",
    "_log_appointment_activity",
    "_create_followup_task",
    "_create_comm_failure_task",
    "_check_memory_rate_limit",
    "_memory_rate_limits",
    "_check_appointment_conflict",
    "_check_rate_limit",
    "_get_cross_source_conflicts",
    "_has_cross_source_conflict",
    "_get_org_id",
    "_is_scheduler_admin",
    "_get_user_timezone",
    "_sanitize_text",
    "_mask_email",
    "_validate_url",
    "_sanitize_public_error",
    "_verify_turnstile_token",
    "_audit_log",
    "_generate_available_slots",
]
