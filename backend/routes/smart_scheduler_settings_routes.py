"""
Smart Scheduler Settings API Routes - Comprehensive Error Handling

Proof-of-concept implementation following the Agent Governance pattern:
- Field-level validation with Pydantic
- Structured success/error responses
- Permission checking
- Database transactions with rollback
- Timezone validation
- Working hours logic validation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime, time
from enum import Enum
import pytz
import re
import logging

from database import get_db as db_get_db
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    BusinessRuleException,
    success_response,
    created_response,
)

router = APIRouter(prefix="/api/v1/smart-scheduler-settings", tags=["Smart Scheduler Settings"])
logger = logging.getLogger(__name__)

# Dependency injection for auth
_get_current_user: Optional[Callable] = None


def set_dependencies(get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func


def get_db():
    yield from db_get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# ENUMS
# =============================================================================

class SchedulingMethod(str, Enum):
    DIRECT = "direct"
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"
    AVAILABILITY = "availability"
    LOAD_BALANCED = "load_balanced"


class MeetingMode(str, Enum):
    VIDEO = "video"
    PHONE = "phone"
    IN_PERSON = "in_person"


# =============================================================================
# PYDANTIC MODELS WITH VALIDATION
# =============================================================================

class BusinessHoursDay(BaseModel):
    """Business hours for a single day"""
    start: str = Field(..., description="Start time in HH:MM format")
    end: str = Field(..., description="End time in HH:MM format")
    enabled: bool = True

    @validator('start', 'end')
    def validate_time_format(cls, v):
        """Ensure time is in HH:MM format"""
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('Time must be in HH:MM format (e.g., 09:00, 17:30)')
        return v

    @root_validator(skip_on_failure=True)
    def validate_time_range(cls, values):
        """Ensure end time is after start time"""
        start = values.get('start')
        end = values.get('end')
        enabled = values.get('enabled', True)

        if enabled and start and end:
            start_parts = [int(x) for x in start.split(':')]
            end_parts = [int(x) for x in end.split(':')]
            start_minutes = start_parts[0] * 60 + start_parts[1]
            end_minutes = end_parts[0] * 60 + end_parts[1]

            if end_minutes <= start_minutes:
                raise ValueError('End time must be after start time')

        return values


class BusinessHours(BaseModel):
    """Complete business hours configuration"""
    monday: BusinessHoursDay = BusinessHoursDay(start="09:00", end="17:00", enabled=True)
    tuesday: BusinessHoursDay = BusinessHoursDay(start="09:00", end="17:00", enabled=True)
    wednesday: BusinessHoursDay = BusinessHoursDay(start="09:00", end="17:00", enabled=True)
    thursday: BusinessHoursDay = BusinessHoursDay(start="09:00", end="17:00", enabled=True)
    friday: BusinessHoursDay = BusinessHoursDay(start="09:00", end="17:00", enabled=True)
    saturday: BusinessHoursDay = BusinessHoursDay(start="10:00", end="14:00", enabled=False)
    sunday: BusinessHoursDay = BusinessHoursDay(start="10:00", end="14:00", enabled=False)

    @root_validator(skip_on_failure=True)
    def validate_at_least_one_day_enabled(cls, values):
        """Ensure at least one day has hours enabled"""
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        enabled_days = [values.get(day) for day in days if values.get(day) and values.get(day).enabled]

        if not enabled_days:
            raise ValueError('At least one day must have working hours enabled')

        return values


class BookingSettings(BaseModel):
    """Booking window and limits"""
    min_notice_hours: int = Field(2, ge=0, le=168, description="Minimum hours notice required")
    max_advance_days: int = Field(60, ge=1, le=365, description="How far in advance bookings allowed")
    default_duration_minutes: int = Field(30, ge=15, le=240, description="Default meeting duration")
    buffer_between_appointments: int = Field(5, ge=0, le=60, description="Buffer between meetings")
    max_meetings_per_day: int = Field(8, ge=1, le=24, description="Maximum meetings per day")


class AISettings(BaseModel):
    """AI scheduling preferences"""
    ai_scheduling_enabled: bool = True
    ai_can_reschedule: bool = True
    ai_can_cancel: bool = False
    smart_reminders_enabled: bool = True
    auto_reschedule_enabled: bool = True


class SmartSchedulerSettingsUpdate(BaseModel):
    """Complete settings update payload"""
    timezone: Optional[str] = None
    scheduling_method: Optional[SchedulingMethod] = None
    business_hours: Optional[BusinessHours] = None
    booking_settings: Optional[BookingSettings] = None
    ai_settings: Optional[AISettings] = None
    default_meeting_mode: Optional[MeetingMode] = None
    zoom_enabled: Optional[bool] = None
    google_meet_enabled: Optional[bool] = None
    auto_create_meeting_link: Optional[bool] = None

    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone is a real timezone"""
        if v and v not in pytz.all_timezones:
            # Try common aliases
            aliases = {
                'EST': 'America/New_York',
                'CST': 'America/Chicago',
                'MST': 'America/Denver',
                'PST': 'America/Los_Angeles',
            }
            if v.upper() in aliases:
                return aliases[v.upper()]
            raise ValueError(f'Invalid timezone: {v}. Use format like "America/Chicago"')
        return v


class TestSchedulerRequest(BaseModel):
    """Request to test scheduler configuration"""
    test_date: Optional[str] = None  # ISO format date to test
    test_duration: int = Field(30, ge=15, le=120)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_settings_warnings(settings: SmartSchedulerSettingsUpdate) -> List[str]:
    """Check for potential issues with settings and return warnings"""
    warnings = []

    if settings.business_hours:
        # Check for very short working days
        for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            day = getattr(settings.business_hours, day_name)
            if day.enabled:
                start_parts = [int(x) for x in day.start.split(':')]
                end_parts = [int(x) for x in day.end.split(':')]
                hours = (end_parts[0] * 60 + end_parts[1] - start_parts[0] * 60 - start_parts[1]) / 60
                if hours < 4:
                    warnings.append(f"{day_name.capitalize()} has less than 4 working hours")

    if settings.booking_settings:
        if settings.booking_settings.min_notice_hours > 24:
            warnings.append("Minimum notice over 24 hours may reduce booking convenience")

        if settings.booking_settings.max_meetings_per_day > 12:
            warnings.append("More than 12 meetings per day may lead to burnout")

    if settings.ai_settings:
        if settings.ai_settings.ai_can_cancel:
            warnings.append("AI cancellation is enabled - appointments may be cancelled automatically")

    return warnings


def calculate_weekly_capacity(business_hours: BusinessHours, booking_settings: BookingSettings) -> Dict[str, Any]:
    """Calculate weekly meeting capacity based on settings"""
    total_hours = 0
    days_with_hours = 0

    for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
        day = getattr(business_hours, day_name)
        if day.enabled:
            start_parts = [int(x) for x in day.start.split(':')]
            end_parts = [int(x) for x in day.end.split(':')]
            hours = (end_parts[0] * 60 + end_parts[1] - start_parts[0] * 60 - start_parts[1]) / 60
            total_hours += hours
            days_with_hours += 1

    # Calculate meetings capacity
    avg_meeting_duration = (booking_settings.default_duration_minutes + booking_settings.buffer_between_appointments) / 60
    max_meetings_possible = int(total_hours / avg_meeting_duration) if avg_meeting_duration > 0 else 0

    # Cap by daily limit
    max_per_week = min(max_meetings_possible, booking_settings.max_meetings_per_day * days_with_hours)

    return {
        "total_working_hours": round(total_hours, 1),
        "working_days": days_with_hours,
        "max_meetings_per_week": max_per_week,
        "avg_hours_per_day": round(total_hours / days_with_hours, 1) if days_with_hours > 0 else 0,
    }


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("")
async def get_scheduler_settings(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current Smart Scheduler settings

    Returns the scheduler configuration including business hours,
    booking settings, AI preferences, and video conferencing options.
    """
    try:
        # Get user's organization scheduler config
        result = db.execute(text("""
            SELECT
                sc.id,
                sc.timezone,
                sc.working_hours,
                sc.default_duration_minutes,
                sc.buffer_before_minutes,
                sc.buffer_after_minutes,
                sc.min_notice_hours,
                sc.max_advance_days,
                sc.max_meetings_per_day,
                sc.routing_strategy,
                sc.ai_scheduling_enabled,
                sc.ai_can_reschedule,
                sc.ai_can_cancel,
                sc.smart_reminders_enabled,
                sc.auto_reschedule_enabled,
                sc.default_meeting_mode,
                sc.zoom_enabled,
                sc.google_meet_enabled,
                sc.auto_create_meeting_link,
                sc.is_active,
                sc.created_at,
                sc.updated_at
            FROM scheduler_configs sc
            WHERE sc.user_id = :user_id OR sc.team_id = :org_id
            ORDER BY sc.user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": current_user.id,
            "org_id": getattr(current_user, 'organization_id', None) or 1
        })

        row = result.fetchone()

        if not row:
            # Return default settings if none exist
            return success_response(
                data={
                    "id": None,
                    "timezone": "America/Chicago",
                    "business_hours": {
                        "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                        "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                        "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                        "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                        "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                        "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
                        "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
                    },
                    "booking_settings": {
                        "min_notice_hours": 2,
                        "max_advance_days": 60,
                        "default_duration_minutes": 30,
                        "buffer_between_appointments": 5,
                        "max_meetings_per_day": 8,
                    },
                    "ai_settings": {
                        "ai_scheduling_enabled": True,
                        "ai_can_reschedule": True,
                        "ai_can_cancel": False,
                        "smart_reminders_enabled": True,
                        "auto_reschedule_enabled": True,
                    },
                    "scheduling_method": "round_robin",
                    "default_meeting_mode": "video",
                    "zoom_enabled": True,
                    "google_meet_enabled": True,
                    "auto_create_meeting_link": True,
                    "is_default": True,
                },
                message="Default settings (no custom configuration found)"
            )

        # Parse working hours JSON
        working_hours = row.working_hours if row.working_hours else {}

        return success_response(
            data={
                "id": row.id,
                "timezone": row.timezone or "America/Chicago",
                "business_hours": working_hours,
                "booking_settings": {
                    "min_notice_hours": row.min_notice_hours or 2,
                    "max_advance_days": row.max_advance_days or 60,
                    "default_duration_minutes": row.default_duration_minutes or 30,
                    "buffer_between_appointments": row.buffer_before_minutes or 5,
                    "max_meetings_per_day": row.max_meetings_per_day or 8,
                },
                "ai_settings": {
                    "ai_scheduling_enabled": row.ai_scheduling_enabled if row.ai_scheduling_enabled is not None else True,
                    "ai_can_reschedule": row.ai_can_reschedule if row.ai_can_reschedule is not None else True,
                    "ai_can_cancel": row.ai_can_cancel if row.ai_can_cancel is not None else False,
                    "smart_reminders_enabled": row.smart_reminders_enabled if row.smart_reminders_enabled is not None else True,
                    "auto_reschedule_enabled": row.auto_reschedule_enabled if row.auto_reschedule_enabled is not None else True,
                },
                "scheduling_method": row.routing_strategy or "round_robin",
                "default_meeting_mode": row.default_meeting_mode or "video",
                "zoom_enabled": row.zoom_enabled if row.zoom_enabled is not None else True,
                "google_meet_enabled": row.google_meet_enabled if row.google_meet_enabled is not None else True,
                "auto_create_meeting_link": row.auto_create_meeting_link if row.auto_create_meeting_link is not None else True,
                "is_active": row.is_active,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            },
            message="Scheduler settings retrieved successfully"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching scheduler settings: {e}")
        raise DatabaseException("Failed to retrieve scheduler settings")


@router.put("")
async def update_scheduler_settings(
    settings: SmartSchedulerSettingsUpdate,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update Smart Scheduler settings

    Validates all settings including:
    - Timezone validity
    - Business hours logic (end > start)
    - At least one working day enabled
    - Reasonable booking limits

    Returns updated settings, warnings, and capacity estimates.
    """
    # 1. Check permission
    has_permission = getattr(current_user, 'has_permission', lambda x: True)
    if not has_permission("manage_settings"):
        raise PermissionException(
            "You don't have permission to update scheduler settings",
            required_permission="manage_settings"
        )

    # 2. Validate and collect warnings
    warnings = validate_settings_warnings(settings)

    # 3. Get or create config
    try:
        result = db.execute(text("""
            SELECT id FROM scheduler_configs
            WHERE user_id = :user_id OR team_id = :org_id
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": current_user.id,
            "org_id": getattr(current_user, 'organization_id', None) or 1
        })

        row = result.fetchone()
        config_id = row.id if row else None

    except SQLAlchemyError as e:
        logger.error(f"Database error checking config: {e}")
        raise DatabaseException("Failed to check existing configuration")

    # 4. Build update data
    update_fields = []
    update_params = {"user_id": current_user.id, "org_id": getattr(current_user, 'organization_id', None) or 1}

    if settings.timezone:
        update_fields.append("timezone = :timezone")
        update_params["timezone"] = settings.timezone

    if settings.scheduling_method:
        update_fields.append("routing_strategy = :routing_strategy")
        update_params["routing_strategy"] = settings.scheduling_method.value

    if settings.business_hours:
        update_fields.append("working_hours = :working_hours")
        update_params["working_hours"] = {
            "monday": settings.business_hours.monday.model_dump(),
            "tuesday": settings.business_hours.tuesday.model_dump(),
            "wednesday": settings.business_hours.wednesday.model_dump(),
            "thursday": settings.business_hours.thursday.model_dump(),
            "friday": settings.business_hours.friday.model_dump(),
            "saturday": settings.business_hours.saturday.model_dump(),
            "sunday": settings.business_hours.sunday.model_dump(),
        }

    if settings.booking_settings:
        update_fields.extend([
            "min_notice_hours = :min_notice_hours",
            "max_advance_days = :max_advance_days",
            "default_duration_minutes = :default_duration_minutes",
            "buffer_before_minutes = :buffer_before_minutes",
            "buffer_after_minutes = :buffer_after_minutes",
            "max_meetings_per_day = :max_meetings_per_day",
        ])
        update_params.update({
            "min_notice_hours": settings.booking_settings.min_notice_hours,
            "max_advance_days": settings.booking_settings.max_advance_days,
            "default_duration_minutes": settings.booking_settings.default_duration_minutes,
            "buffer_before_minutes": settings.booking_settings.buffer_between_appointments,
            "buffer_after_minutes": settings.booking_settings.buffer_between_appointments,
            "max_meetings_per_day": settings.booking_settings.max_meetings_per_day,
        })

    if settings.ai_settings:
        update_fields.extend([
            "ai_scheduling_enabled = :ai_scheduling_enabled",
            "ai_can_reschedule = :ai_can_reschedule",
            "ai_can_cancel = :ai_can_cancel",
            "smart_reminders_enabled = :smart_reminders_enabled",
            "auto_reschedule_enabled = :auto_reschedule_enabled",
        ])
        update_params.update({
            "ai_scheduling_enabled": settings.ai_settings.ai_scheduling_enabled,
            "ai_can_reschedule": settings.ai_settings.ai_can_reschedule,
            "ai_can_cancel": settings.ai_settings.ai_can_cancel,
            "smart_reminders_enabled": settings.ai_settings.smart_reminders_enabled,
            "auto_reschedule_enabled": settings.ai_settings.auto_reschedule_enabled,
        })

    if settings.default_meeting_mode:
        update_fields.append("default_meeting_mode = :default_meeting_mode")
        update_params["default_meeting_mode"] = settings.default_meeting_mode.value

    if settings.zoom_enabled is not None:
        update_fields.append("zoom_enabled = :zoom_enabled")
        update_params["zoom_enabled"] = settings.zoom_enabled

    if settings.google_meet_enabled is not None:
        update_fields.append("google_meet_enabled = :google_meet_enabled")
        update_params["google_meet_enabled"] = settings.google_meet_enabled

    if settings.auto_create_meeting_link is not None:
        update_fields.append("auto_create_meeting_link = :auto_create_meeting_link")
        update_params["auto_create_meeting_link"] = settings.auto_create_meeting_link

    # 5. Execute update with transaction
    try:
        if config_id:
            # Update existing
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_params["config_id"] = config_id

            db.execute(text(f"""
                UPDATE scheduler_configs
                SET {', '.join(update_fields)}
                WHERE id = :config_id
            """), update_params)
        else:
            # Create new config
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    user_id, team_id, config_name, timezone, working_hours,
                    default_duration_minutes, buffer_before_minutes, buffer_after_minutes,
                    min_notice_hours, max_advance_days, max_meetings_per_day,
                    routing_strategy, ai_scheduling_enabled, ai_can_reschedule,
                    ai_can_cancel, smart_reminders_enabled, auto_reschedule_enabled,
                    default_meeting_mode, zoom_enabled, google_meet_enabled,
                    auto_create_meeting_link, is_active, created_at, updated_at
                ) VALUES (
                    :user_id, :org_id, 'Default Configuration',
                    :timezone, :working_hours,
                    :default_duration_minutes, :buffer_before_minutes, :buffer_after_minutes,
                    :min_notice_hours, :max_advance_days, :max_meetings_per_day,
                    :routing_strategy, :ai_scheduling_enabled, :ai_can_reschedule,
                    :ai_can_cancel, :smart_reminders_enabled, :auto_reschedule_enabled,
                    :default_meeting_mode, :zoom_enabled, :google_meet_enabled,
                    :auto_create_meeting_link, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "user_id": current_user.id,
                "org_id": getattr(current_user, 'organization_id', None) or 1,
                "timezone": settings.timezone or "America/Chicago",
                "working_hours": update_params.get("working_hours", {}),
                "default_duration_minutes": update_params.get("default_duration_minutes", 30),
                "buffer_before_minutes": update_params.get("buffer_before_minutes", 5),
                "buffer_after_minutes": update_params.get("buffer_after_minutes", 5),
                "min_notice_hours": update_params.get("min_notice_hours", 2),
                "max_advance_days": update_params.get("max_advance_days", 60),
                "max_meetings_per_day": update_params.get("max_meetings_per_day", 8),
                "routing_strategy": update_params.get("routing_strategy", "round_robin"),
                "ai_scheduling_enabled": update_params.get("ai_scheduling_enabled", True),
                "ai_can_reschedule": update_params.get("ai_can_reschedule", True),
                "ai_can_cancel": update_params.get("ai_can_cancel", False),
                "smart_reminders_enabled": update_params.get("smart_reminders_enabled", True),
                "auto_reschedule_enabled": update_params.get("auto_reschedule_enabled", True),
                "default_meeting_mode": update_params.get("default_meeting_mode", "video"),
                "zoom_enabled": update_params.get("zoom_enabled", True),
                "google_meet_enabled": update_params.get("google_meet_enabled", True),
                "auto_create_meeting_link": update_params.get("auto_create_meeting_link", True),
            })

        db.commit()

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating scheduler settings: {e}")
        raise DatabaseException("Failed to save scheduler settings. Please try again.")

    # 6. Calculate capacity if we have business hours and booking settings
    capacity = None
    if settings.business_hours and settings.booking_settings:
        capacity = calculate_weekly_capacity(settings.business_hours, settings.booking_settings)

    logger.info(f"Scheduler settings updated by user {current_user.id}")

    return success_response(
        data={
            "updated": True,
            "warnings": warnings,
            "capacity": capacity,
        },
        message="Scheduler settings updated successfully"
    )


@router.post("/test")
async def test_scheduler_configuration(
    request: TestSchedulerRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test scheduler configuration

    Validates that the current settings allow bookings to be made.
    Can optionally test against a specific date.
    """
    issues = []

    try:
        # Get current config
        result = db.execute(text("""
            SELECT
                working_hours,
                min_notice_hours,
                max_advance_days,
                max_meetings_per_day,
                zoom_enabled,
                google_meet_enabled
            FROM scheduler_configs
            WHERE user_id = :user_id OR team_id = :org_id
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": current_user.id,
            "org_id": getattr(current_user, 'organization_id', None) or 1
        })

        row = result.fetchone()

        if not row:
            issues.append("No scheduler configuration found - using defaults")
        else:
            working_hours = row.working_hours or {}

            # Check if any days are enabled
            enabled_days = [day for day, hours in working_hours.items()
                          if isinstance(hours, dict) and hours.get('enabled', False)]

            if not enabled_days:
                issues.append("No working days are enabled")

            # Check video conferencing
            if not row.zoom_enabled and not row.google_meet_enabled:
                issues.append("No video conferencing integration is enabled")

        # Check for loan officers in the pool
        lo_result = db.execute(text("""
            SELECT COUNT(*) as count FROM loan_officer_schedules
            WHERE is_active = true
        """))
        lo_count = lo_result.fetchone()

        if lo_count and lo_count.count == 0:
            issues.append("No active loan officers in the scheduling pool")

        success = len(issues) == 0

        return success_response(
            data={
                "success": success,
                "issues": issues,
                "loan_officers_available": lo_count.count if lo_count else 0,
                "test_date": request.test_date,
                "test_duration": request.test_duration,
            },
            message="Configuration test passed" if success else "Configuration test found issues"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error testing scheduler: {e}")
        raise DatabaseException("Failed to test scheduler configuration")


@router.get("/timezones")
async def get_available_timezones(
    search: Optional[str] = Query(None, description="Filter timezones by name")
):
    """
    Get list of available timezones

    Returns common US timezones first, then all others.
    Can filter by search term.
    """
    # Common US timezones first
    common_timezones = [
        {"value": "America/New_York", "label": "Eastern Time (ET)", "offset": "UTC-5"},
        {"value": "America/Chicago", "label": "Central Time (CT)", "offset": "UTC-6"},
        {"value": "America/Denver", "label": "Mountain Time (MT)", "offset": "UTC-7"},
        {"value": "America/Los_Angeles", "label": "Pacific Time (PT)", "offset": "UTC-8"},
        {"value": "America/Phoenix", "label": "Arizona Time", "offset": "UTC-7"},
        {"value": "Pacific/Honolulu", "label": "Hawaii Time", "offset": "UTC-10"},
        {"value": "America/Anchorage", "label": "Alaska Time", "offset": "UTC-9"},
    ]

    # Filter by search if provided
    if search:
        search_lower = search.lower()
        common_timezones = [tz for tz in common_timezones
                          if search_lower in tz["value"].lower() or search_lower in tz["label"].lower()]

        # Add matching from full list
        all_matching = [{"value": tz, "label": tz.replace("_", " "), "offset": ""}
                       for tz in pytz.all_timezones if search_lower in tz.lower()][:20]

        # Combine, removing duplicates
        existing_values = {tz["value"] for tz in common_timezones}
        for tz in all_matching:
            if tz["value"] not in existing_values:
                common_timezones.append(tz)

    return success_response(
        data={
            "timezones": common_timezones[:30],  # Limit results
            "total_available": len(pytz.all_timezones),
        },
        message="Timezones retrieved"
    )


@router.get("/scheduling-methods")
async def get_scheduling_methods():
    """
    Get available scheduling/routing methods with descriptions
    """
    methods = [
        {
            "value": "direct",
            "label": "Direct",
            "description": "Book directly with you — no routing or distribution",
            "recommended_for": "Solo LOs or personal booking links",
        },
        {
            "value": "round_robin",
            "label": "Round Robin",
            "description": "Distribute appointments evenly among all active loan officers",
            "recommended_for": "Equal distribution across team",
        },
        {
            "value": "priority",
            "label": "Priority",
            "description": "Assign to highest priority loan officer who is available",
            "recommended_for": "Senior LOs getting first pick",
        },
        {
            "value": "availability",
            "label": "First Available",
            "description": "Assign to the first loan officer with an open slot",
            "recommended_for": "Fastest booking experience",
        },
        {
            "value": "load_balanced",
            "label": "Load Balanced",
            "description": "Assign to loan officer with fewest appointments this week",
            "recommended_for": "Preventing burnout",
        },
    ]

    return success_response(
        data={"methods": methods},
        message="Scheduling methods retrieved"
    )
