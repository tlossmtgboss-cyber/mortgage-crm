"""
Smart Scheduler API Routes - Perennia AI AI-Native Appointment Scheduling

Thin router that includes sub-routers:
- scheduler_config_routes: Config, landing page, appointment types, seed, migrate
- scheduler_appointment_routes: Appointments, availability, blocked times, booking links,
  slot engine, AI recommendations, public booking, website demo

Extracted modules:
- scheduler_models.py: Pydantic request/response schemas
- scheduler_email_service.py: Email/SMS notification helpers
"""

from fastapi import APIRouter
import logging

from scheduler_config_routes import router as config_router
from scheduler_config_routes import set_dependencies as set_config_deps

from scheduler_appointment_routes import router as appointment_router
from scheduler_appointment_routes import set_dependencies as set_appointment_deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Smart Scheduler"])


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies for all sub-routers"""
    set_config_deps(get_db_func, get_current_user_func, models_dict)
    set_appointment_deps(get_db_func, get_current_user_func, models_dict)


# Include sub-routers (no prefix - parent router already has /api/v1/scheduler)
router.include_router(config_router)
router.include_router(appointment_router)
