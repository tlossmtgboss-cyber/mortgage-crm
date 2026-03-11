"""
Smart Scheduler API Routes - Perennia AI AI-Native Appointment Scheduling

Thin router that includes consolidated sub-routers:
- routes/scheduler_routes.py: Config, landing page, appointment types, settings, seed, migrate
- routes/scheduler_appointment_routes.py: Appointments, availability, blocked times, booking links,
  slot engine, AI recommendations, public booking, resources, SLA, analytics, group sessions, campaigns
- routes/holiday_routes.py: Holiday CRUD, PTO requests, team availability grid
- routes/calendar_export_routes.py: ICS download and PDF schedule generation
"""

from fastapi import APIRouter
import logging

from routes.scheduler_routes import router as config_router
from routes.scheduler_routes import set_dependencies as set_config_deps

from routes.scheduler_appointment_routes import router as appointment_router
from routes.scheduler_appointment_routes import set_dependencies as set_appointment_deps
from routes.scheduler_appointment_routes import set_enhanced_dependencies

from routes.holiday_routes import router as holiday_router
from routes.holiday_routes import set_dependencies as set_holiday_deps

from routes.calendar_export_routes import router as export_router
from routes.calendar_export_routes import set_dependencies as set_export_deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Smart Scheduler"])

# Stored for deferred initialization by inline_legacy_routes
_holiday_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies for all sub-routers (called from inline_legacy_routes)"""
    set_config_deps(get_db_func, get_current_user_func, models_dict)
    set_appointment_deps(get_db_func, get_current_user_func, models_dict)
    set_export_deps(get_db_func, get_current_user_func, models_dict)


def set_holiday_dependencies(get_db_func, get_current_user_func, models_dict, holiday_models_dict):
    """Set dependencies for the holiday/PTO sub-router."""
    global _holiday_models
    _holiday_models = holiday_models_dict
    set_holiday_deps(get_db_func, get_current_user_func, models_dict, holiday_models_dict)


# Include sub-routers (no prefix - parent router already has /api/v1/scheduler)
router.include_router(config_router)
router.include_router(appointment_router)
router.include_router(holiday_router)
router.include_router(export_router)
