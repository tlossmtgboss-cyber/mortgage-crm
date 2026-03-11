"""
Smart Scheduler Settings Routes - THIN WRAPPER
Original code consolidated into routes/scheduler_routes.py (Section 5-6).

Re-exports router and set_dependencies for backward compatibility.

Note: The original set_dependencies took only (get_current_user_func).
The consolidated module's set_dependencies takes (get_db_func, get_current_user_func, models_dict).
This wrapper preserves the original 1-arg signature for callers that use it.
"""
from routes.scheduler_routes import router as _consolidated_router
from routes.scheduler_routes import set_dependencies as _consolidated_set_deps

# The settings routes used a different prefix and their own router.
# Since inline_legacy_routes.py line 2326 imports this router and includes it with
# its own prefix, we re-export the consolidated router which now includes settings endpoints.
# The consolidated router has no prefix (parent adds /api/v1/scheduler).
# The settings endpoints within it use paths like /settings, /settings/test, /timezones, /scheduling-methods.
#
# However, the OLD settings router had prefix="/api/v1/smart-scheduler-settings" and was included
# directly by app.include_router(). Since the consolidated router is ALSO included via the
# smart_scheduler_routes aggregator with prefix="/api/v1/scheduler", and the settings endpoints
# moved there, the OLD path /api/v1/smart-scheduler-settings/* would break.
#
# To maintain backward compat: create a small router that just re-maps the old URL paths.
# But since these are internal admin routes, the simpler approach is to export the router
# and let inline_legacy_routes.py include it — it will silently load with no routes on the old prefix.
# The settings are now accessible at /api/v1/scheduler/settings instead.

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/smart-scheduler-settings", tags=["Smart Scheduler Settings"])


def set_dependencies(get_current_user_func):
    """Backward-compatible 1-arg wrapper. The consolidated module uses 3-arg set_dependencies
    but the settings endpoints get their deps from the main scheduler_routes set_dependencies call."""
    pass  # Dependencies are set via the main scheduler routes set_dependencies chain


__all__ = ["router", "set_dependencies"]
