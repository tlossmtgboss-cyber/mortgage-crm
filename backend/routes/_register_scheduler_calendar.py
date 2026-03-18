"""
Scheduler & Calendar route registrations.

Routes: Smart Scheduler, team calendar, Calendly, calendar settings, calendar sync.
"""
import logging

logger = logging.getLogger(__name__)


def register_scheduler_calendar_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register scheduler and calendar routes.

    Returns:
        dict: smart_scheduler_models dict for downstream consumers.
    """
    from fastapi import Depends
    from sqlalchemy.orm import Session
    from sqlalchemy import text
    from datetime import datetime, timedelta
    from database import engine
    from database.models import User

    smart_scheduler_models = {}

    # Include Smart Scheduler routes (AI-native appointment scheduling)
    try:
        from smart_scheduler_models import (
            SchedulerConfig, AvailabilitySlot, AppointmentType as SchedAppointmentType,
            Appointment, RoutingRule, BlockedTime, BookingLink,
            AppointmentReminder, SchedulerAuditLog,
        )
        from smart_scheduler_routes import router as smart_scheduler_router, set_dependencies as set_scheduler_deps

        # Ensure the simple scheduler tables exist
        try:
            from services.smart_scheduler_service import ensure_scheduler_tables
            ensure_scheduler_tables()
        except Exception as tbl_err:
            logger.warning(f"Scheduler table setup: {tbl_err}")

        # Run tenant isolation migration
        try:
            from migrations.add_scheduler_tenant_isolation import run_migration
            run_migration()
        except Exception as mig_err:
            logger.warning(f"Scheduler tenant migration: {mig_err}")

        smart_scheduler_models = {
            'SchedulerConfig': SchedulerConfig,
            'AvailabilitySlot': AvailabilitySlot,
            'AppointmentType': SchedAppointmentType,
            'Appointment': Appointment,
            'RoutingRule': RoutingRule,
            'BlockedTime': BlockedTime,
            'BookingLink': BookingLink,
            'AppointmentReminder': AppointmentReminder,
            'SchedulerAuditLog': SchedulerAuditLog,
        }
        smart_scheduler_models['User'] = User

        set_scheduler_deps(get_db, get_current_user, smart_scheduler_models)
        app.include_router(smart_scheduler_router, tags=["Smart Scheduler"])
        logger.info("Smart Scheduler routes loaded")
    except Exception as e:
        import traceback
        logger.error(f"Could not load Smart Scheduler routes: {e}")
        logger.error(f"Smart Scheduler traceback: {traceback.format_exc()}")

        # Add fallback endpoint if main scheduler routes failed to load
        import pytz
        from pydantic import BaseModel
        from typing import Optional

        class FallbackSlotsRequest(BaseModel):
            start_date: str
            end_date: str
            duration_minutes: int = 30
            appointment_type: str = "platform-demo"

        @app.post("/api/v1/scheduler/public/available-slots")
        async def fallback_available_slots(request: FallbackSlotsRequest, db: Session = Depends(get_db)):
            """Fallback endpoint for public available slots when main scheduler routes fail to load"""
            try:
                tz = pytz.timezone("America/Chicago")
                slots = []

                start = datetime.strptime(request.start_date, "%Y-%m-%d")
                end = datetime.strptime(request.end_date, "%Y-%m-%d")

                result = db.execute(text("""
                    SELECT ca.assigned_user_id, u.full_name as user_name
                    FROM calendar_assignments ca
                    LEFT JOIN users u ON u.id = ca.assigned_user_id
                    WHERE ca.purpose = 'website_demo' AND ca.is_active = true
                    LIMIT 1
                """)).fetchone()

                user_name = result.user_name if result else "Team Member"
                user_id = result.assigned_user_id if result else None

                current = start
                while current <= end:
                    if current.weekday() < 5:
                        for hour in range(9, 17):
                            for minute in [0, 30]:
                                slot_time = tz.localize(current.replace(hour=hour, minute=minute, second=0))
                                if slot_time > datetime.now(tz):
                                    slots.append({
                                        "start_time": slot_time.isoformat(),
                                        "end_time": (slot_time + timedelta(minutes=request.duration_minutes)).isoformat(),
                                        "user_id": user_id,
                                        "user_name": user_name,
                                        "available": True
                                    })
                    current += timedelta(days=1)

                return {
                    "available_slots": slots[:100],
                    "message": "Generated default availability (fallback mode)",
                    "configured": bool(result),
                    "fallback": True
                }
            except Exception as fallback_error:
                logger.error(f"Fallback scheduler error: {fallback_error}")
                return {"available_slots": [], "error": str(fallback_error), "fallback": True}

        logger.info("Fallback scheduler endpoint registered")

    # Include AI Smart Scheduler Setup routes
    try:
        from routes.smart_scheduler_routes import router as ai_scheduler_setup_router
        app.include_router(ai_scheduler_setup_router, prefix="/api/v1/scheduler-setup", tags=["AI Scheduler Setup"])
        logger.info("AI Scheduler Setup routes loaded")
    except Exception as e:
        import traceback
        logger.warning(f"Could not load AI Scheduler Setup routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Set Enhanced Scheduler dependencies
    try:
        from scheduler_enhancements import create_scheduler_enhancement_models
        from routes.scheduler_appointment_routes import set_enhanced_dependencies
        from database import Base

        scheduler_enhanced_models = create_scheduler_enhancement_models(Base)
        set_enhanced_dependencies(get_db, get_current_user, smart_scheduler_models, scheduler_enhanced_models)
        logger.info("Enhanced Scheduler dependencies set")
    except Exception as e:
        import traceback
        logger.warning(f"Could not set Enhanced Scheduler dependencies: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Include Team Calendar routes
    try:
        from routes.team_calendar_routes import register_team_calendar_routes
        _models = smart_scheduler_models if smart_scheduler_models else {}
        register_team_calendar_routes(
            app=app,
            get_current_user=get_current_user,
            models_dict=_models,
        )
        logger.info("Team Calendar routes loaded")
    except Exception as e:
        import traceback
        logger.warning(f"Could not load Team Calendar routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Include Calendly Integration routes
    try:
        from routes.calendly_routes import router as calendly_router
        app.include_router(calendly_router, prefix="/api/v1/calendly", tags=["Calendly Integration"])
        logger.info("Calendly Integration routes loaded")
    except Exception as e:
        import traceback
        logger.warning(f"Could not load Calendly routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Smart Scheduler Settings (consolidated into scheduler routes)
    try:
        from routes.smart_scheduler_settings_routes import router as smart_scheduler_settings_router, set_dependencies as set_scheduler_settings_deps
        set_scheduler_settings_deps(get_current_user)
        app.include_router(smart_scheduler_settings_router, tags=["Smart Scheduler Settings"])
        logger.info("Smart Scheduler Settings routes loaded (consolidated)")
    except Exception as e:
        logger.warning(f"Smart Scheduler Settings routes not loaded: {e}")

    # Calendar Settings routes
    try:
        from routes.calendar_settings_routes import router as calendar_settings_router, set_dependencies as set_cal_settings_deps
        set_cal_settings_deps(get_current_user)
        app.include_router(calendar_settings_router, tags=["Calendar Settings"])
        logger.info("Calendar Settings routes loaded")
    except Exception as e:
        logger.warning(f"Calendar Settings routes not loaded: {e}")

    # Calendar sync table creation
    try:
        from models.calendar_sync_models import CRMCalendarEvent, CalendarEventSyncMap, CalendarSyncLog, CalendarSyncSettings
        for model in [CRMCalendarEvent, CalendarEventSyncMap, CalendarSyncLog, CalendarSyncSettings]:
            try:
                model.__table__.create(engine, checkfirst=True)
            except Exception as e:
                logger.warning(f"Calendar sync table {model.__tablename__}: {e}")
    except Exception as e:
        logger.warning(f"Calendar sync models import: {e}")

    # Calendar sync routes
    try:
        from routes.calendar_sync_routes import router as calendar_sync_router
        app.include_router(calendar_sync_router, tags=["Calendar Sync"])
        logger.info("Calendar routes loaded (sync, events, unified view)")
    except Exception as e:
        logger.warning(f"Calendar routes not loaded: {e}")

    # Google Calendar dependencies
    try:
        from routes.calendar_sync_routes import set_dependencies as set_google_calendar_deps
        set_google_calendar_deps(get_db, get_current_user)
        logger.info("Google Calendar dependencies set")
    except Exception as e:
        logger.warning(f"Google Calendar dependencies not set: {e}")

    logger.info("Scheduler & Calendar route group loaded")
    return smart_scheduler_models
