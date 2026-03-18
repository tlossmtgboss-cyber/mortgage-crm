"""
Unified Scheduler Settings API

Provides a single endpoint to retrieve ALL calendar settings as one JSON blob,
plus section-specific update endpoints, setup wizard tracking, and
settings import/export.

Endpoints:
  - GET    /settings/all                  Get ALL settings for the current user
  - PUT    /settings/{section}            Update a specific settings section
  - GET    /settings/setup-status         Get setup wizard progress
  - PUT    /settings/setup-status         Save setup wizard progress
  - POST   /settings/reset               Reset settings to defaults (confirmation required)
  - GET    /settings/export               Export all settings as JSON backup
  - POST   /settings/import              Import settings from JSON backup
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
import json
import logging
import secrets
import re

from routes.scheduler._helpers import (
    get_current_user,
    get_models,
    _get_org_id,
    _is_scheduler_admin,
    _audit_log,
)
from routes.scheduler.error_responses import (
    scheduler_error,
    VALIDATION_ERROR, FORBIDDEN, INVALID_SECTION, SERVICE_UNAVAILABLE,
    RESET_ERROR, IMPORT_ERROR,
)
from routes.scheduler.recurring_availability import (
    _sync_working_hours_json_to_recurring,
)
from routes.scheduler.constants import DEFAULT_TIMEZONE
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class WorkingHoursDaySchema(BaseModel):
    start: str = "09:00"
    end: str = "17:00"
    enabled: bool = True

    @validator("start", "end")
    def validate_time_format(cls, v):
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
            raise ValueError("Time must be in HH:MM format (e.g., 09:00, 17:30)")
        return v


class AvailabilityUpdate(BaseModel):
    timezone: Optional[str] = None
    working_hours: Optional[Dict[str, WorkingHoursDaySchema]] = None
    lunch_break_start: Optional[str] = Field(None, description="HH:MM format")
    lunch_break_end: Optional[str] = Field(None, description="HH:MM format")
    enforce_lunch_break: Optional[bool] = None
    buffer_before_minutes: Optional[int] = Field(None, ge=0, le=60)
    buffer_after_minutes: Optional[int] = Field(None, ge=0, le=60)
    max_meetings_per_day: Optional[int] = Field(None, ge=1, le=24)
    max_consecutive_meetings: Optional[int] = Field(None, ge=1, le=12)
    min_notice_hours: Optional[int] = Field(None, ge=0, le=168)
    max_advance_days: Optional[int] = Field(None, ge=1, le=365)
    default_duration_minutes: Optional[int] = Field(None, ge=5, le=480)

    @validator("timezone")
    def validate_timezone(cls, v):
        if v is not None:
            import pytz
            aliases = {"EST": "America/New_York", "CST": "America/Chicago",
                       "MST": "America/Denver", "PST": "America/Los_Angeles"}
            if v.upper() in aliases:
                return aliases[v.upper()]
            if v not in pytz.all_timezones:
                raise ValueError(f"Invalid timezone: {v}")
        return v

    @validator("lunch_break_start", "lunch_break_end")
    def validate_lunch_time(cls, v):
        if v is not None and not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
            raise ValueError("Time must be in HH:MM format")
        return v


class NotificationsUpdate(BaseModel):
    email_reminder_24h: Optional[bool] = None
    email_reminder_2h: Optional[bool] = None
    sms_reminder_2h: Optional[bool] = None
    sms_reminder_24h: Optional[bool] = None
    push_notifications: Optional[bool] = None
    booking_confirmation: Optional[bool] = None
    cancellation_notification: Optional[bool] = None
    reschedule_notification: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    daily_digest_enabled: Optional[bool] = None
    daily_digest_time: Optional[str] = None
    browser_notifications: Optional[bool] = None


class BookingPageUpdate(BaseModel):
    logo_url: Optional[str] = Field(None, max_length=1000)
    profile_picture_url: Optional[str] = Field(None, max_length=1000)
    video_url: Optional[str] = Field(None, max_length=1000)
    video_type: Optional[str] = Field(None, max_length=50)
    headline: Optional[str] = Field(None, max_length=200)
    subheadline: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    show_profile: Optional[bool] = None
    profile_name: Optional[str] = Field(None, max_length=200)
    profile_title: Optional[str] = Field(None, max_length=200)
    profile_bio: Optional[str] = Field(None, max_length=2000)
    accent_color: Optional[str] = Field(None, max_length=20)
    background_style: Optional[str] = Field(None, max_length=50)
    show_company_logo: Optional[bool] = None
    show_social_proof: Optional[bool] = None
    testimonial_text: Optional[str] = Field(None, max_length=2000)
    testimonial_author: Optional[str] = Field(None, max_length=200)


class IntegrationsUpdate(BaseModel):
    zoom_enabled: Optional[bool] = None
    google_meet_enabled: Optional[bool] = None
    auto_create_meeting_link: Optional[bool] = None
    google_calendar_sync: Optional[bool] = None
    outlook_calendar_sync: Optional[bool] = None
    calendar_feed_enabled: Optional[bool] = None


class TeamUpdate(BaseModel):
    routing_strategy: Optional[str] = Field(None, max_length=50)
    accept_overflow_bookings: Optional[bool] = None


class AdvancedUpdate(BaseModel):
    ai_scheduling_enabled: Optional[bool] = None
    ai_can_reschedule: Optional[bool] = None
    ai_can_cancel: Optional[bool] = None
    auto_reschedule_enabled: Optional[bool] = None
    smart_reminders_enabled: Optional[bool] = None
    default_meeting_mode: Optional[str] = Field(None, max_length=50)
    preferred_meeting_modes: Optional[List[str]] = None
    feature_toggles: Optional[Dict[str, bool]] = None


class AISchedulingUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_book_enabled: Optional[bool] = None
    preferred_times: Optional[List[str]] = None
    max_ai_bookings_per_day: Optional[int] = Field(None, ge=1, le=20)
    buffer_before_minutes: Optional[int] = Field(None, ge=0, le=60)
    buffer_after_minutes: Optional[int] = Field(None, ge=0, le=60)
    allowed_appointment_types: Optional[List[str]] = None
    require_confirmation: Optional[bool] = None
    confirmation_method: Optional[str] = Field(None, max_length=20)
    smart_scheduling: Optional[Dict[str, Any]] = None
    sms_triggers: Optional[Dict[str, Any]] = None
    ai_response_handling: Optional[Dict[str, Any]] = None


class SetupStatusUpdate(BaseModel):
    completed_steps: List[str] = Field(default_factory=list)
    current_step: int = Field(0, ge=0)


class ResetRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=16, max_length=128)


class SettingsImport(BaseModel):
    data: Dict[str, Any]
    overwrite: bool = Field(False, description="If true, overwrite all settings; if false, merge")


# ============================================================================
# SECTION VALIDATORS
# ============================================================================

VALID_SECTIONS = {
    "availability", "notifications", "booking_page",
    "integrations", "team", "advanced", "ai_scheduling",
}

SECTION_MODELS = {
    "availability": AvailabilityUpdate,
    "notifications": NotificationsUpdate,
    "booking_page": BookingPageUpdate,
    "integrations": IntegrationsUpdate,
    "team": TeamUpdate,
    "advanced": AdvancedUpdate,
    "ai_scheduling": AISchedulingUpdate,
}


# ============================================================================
# HELPERS
# ============================================================================

def _get_or_create_config(db: Session, user_id: int, org_id: int):
    """Get the user's SchedulerConfig, creating one with defaults if needed."""
    models = get_models()
    if not models:
        scheduler_error(500, SERVICE_UNAVAILABLE, "Scheduler service is not available")
    SchedulerConfig = models["SchedulerConfig"]

    config = (
        db.query(SchedulerConfig)
        .filter(
            SchedulerConfig.user_id == user_id,
            SchedulerConfig.organization_id == org_id,
        )
        .first()
    )
    if config:
        return config

    # Fall back to org-level config (team config)
    config = (
        db.query(SchedulerConfig)
        .filter(
            SchedulerConfig.user_id.is_(None),
            SchedulerConfig.organization_id == org_id,
        )
        .first()
    )
    if config:
        return config

    # Create a default config for the user
    from smart_scheduler_models import DEFAULT_WORKING_HOURS

    config = SchedulerConfig(
        organization_id=org_id,
        user_id=user_id,
        config_name="Default Settings",
        timezone=DEFAULT_TIMEZONE,
        working_hours=DEFAULT_WORKING_HOURS,
        notification_settings={},
        landing_page_settings={},
        setup_completed=False,
        setup_progress={"completed_steps": [], "current_step": 0},
        feature_toggles={},
    )
    db.add(config)
    db.flush()
    return config


def _serialize_config_availability(config) -> dict:
    """Build the availability section from a SchedulerConfig."""
    lunch_start = config.lunch_break_start
    lunch_end = config.lunch_break_end
    return {
        "timezone": config.timezone or DEFAULT_TIMEZONE,
        "working_hours": config.working_hours or {},
        "lunch_break": {
            "start": lunch_start.strftime("%H:%M") if isinstance(lunch_start, time) else str(lunch_start or "12:00"),
            "end": lunch_end.strftime("%H:%M") if isinstance(lunch_end, time) else str(lunch_end or "13:00"),
            "enforced": config.enforce_lunch_break if config.enforce_lunch_break is not None else True,
        },
        "buffers": {
            "before_minutes": config.buffer_before_minutes or 5,
            "after_minutes": config.buffer_after_minutes or 5,
        },
        "daily_limits": {
            "max_meetings_per_day": config.max_meetings_per_day or 8,
            "max_consecutive_meetings": config.max_consecutive_meetings or 3,
        },
        "booking_window": {
            "min_notice_hours": config.min_notice_hours or 2,
            "max_advance_days": config.max_advance_days or 60,
        },
        "default_duration_minutes": config.default_duration_minutes or 30,
    }


def _serialize_appointment_type(at) -> dict:
    """Serialize an AppointmentType row."""
    return {
        "id": at.id,
        "type_key": at.type_key,
        "type_name": at.type_name,
        "description": at.description,
        "meeting_type": at.meeting_type.value if hasattr(at.meeting_type, "value") else at.meeting_type,
        "default_duration_minutes": at.default_duration_minutes,
        "allowed_durations": at.allowed_durations or [],
        "allowed_modes": at.allowed_modes or [],
        "default_mode": at.default_mode.value if hasattr(at.default_mode, "value") else at.default_mode,
        "min_notice_hours": at.min_notice_hours,
        "max_advance_days": at.max_advance_days,
        "max_per_day": at.max_per_day,
        "max_per_week": at.max_per_week,
        "requires_loan_id": at.requires_loan_id,
        "requires_lead_id": at.requires_lead_id,
        "requires_contact_info": at.requires_contact_info,
        "intake_questions": at.intake_questions or [],
        "reminder_schedule": at.reminder_schedule or [],
        "assigned_users": at.assigned_users or [],
        "routing_strategy": at.routing_strategy.value if hasattr(at.routing_strategy, "value") else at.routing_strategy,
        "color": at.color,
        "icon": at.icon,
        "display_order": at.display_order,
        "is_public": at.is_public,
        "public_slug": at.public_slug,
        "is_active": at.is_active,
    }


def _serialize_notifications(config) -> dict:
    """Build the notifications section from a SchedulerConfig."""
    ns = config.notification_settings or {}
    return {
        "reminders": {
            "email_24h": ns.get("email_reminder_24h", True),
            "email_2h": ns.get("email_reminder_2h", True),
            "sms_24h": ns.get("sms_reminder_24h", False),
            "sms_2h": ns.get("sms_reminder_2h", False),
            "push": ns.get("push_notifications", True),
        },
        "events": {
            "booking_confirmation": ns.get("booking_confirmation", True),
            "cancellation": ns.get("cancellation_notification", True),
            "reschedule": ns.get("reschedule_notification", True),
        },
        "quiet_hours": {
            "enabled": ns.get("quiet_hours_enabled", False),
            "start": ns.get("quiet_hours_start", "21:00"),
            "end": ns.get("quiet_hours_end", "08:00"),
        },
        "digest": {
            "daily_digest_enabled": ns.get("daily_digest_enabled", False),
            "daily_digest_time": ns.get("daily_digest_time", "08:00"),
        },
        "browser": ns.get("browser_notifications", True),
    }


def _serialize_booking_page(config) -> dict:
    """Build the booking page section from a SchedulerConfig."""
    lps = config.landing_page_settings or {}
    return {
        "branding": {
            "logo_url": lps.get("logo_url", ""),
            "profile_picture_url": lps.get("profile_picture_url", ""),
            "accent_color": lps.get("accent_color", "#217F8D"),
            "background_style": lps.get("background_style", "white"),
            "show_company_logo": lps.get("show_company_logo", True),
        },
        "content": {
            "headline": lps.get("headline", "Schedule a Meeting"),
            "subheadline": lps.get("subheadline", "Choose a time that works for you"),
            "description": lps.get("description", ""),
            "video_url": lps.get("video_url", ""),
            "video_type": lps.get("video_type", "youtube"),
        },
        "profile": {
            "show_profile": lps.get("show_profile", True),
            "profile_name": lps.get("profile_name", ""),
            "profile_title": lps.get("profile_title", ""),
            "profile_bio": lps.get("profile_bio", ""),
        },
        "social_proof": {
            "show_social_proof": lps.get("show_social_proof", False),
            "testimonial_text": lps.get("testimonial_text", ""),
            "testimonial_author": lps.get("testimonial_author", ""),
        },
    }


def _serialize_integrations(config) -> dict:
    """Build the integrations section from a SchedulerConfig."""
    ft = config.feature_toggles or {} if hasattr(config, "feature_toggles") else {}
    return {
        "google": {
            "meet_enabled": config.google_meet_enabled if config.google_meet_enabled is not None else True,
            "calendar_sync": ft.get("google_calendar_sync", False),
        },
        "outlook": {
            "calendar_sync": ft.get("outlook_calendar_sync", False),
        },
        "zoom": {
            "enabled": config.zoom_enabled if config.zoom_enabled is not None else True,
        },
        "meeting_link": {
            "auto_create": config.auto_create_meeting_link if config.auto_create_meeting_link is not None else True,
        },
        "feed": {
            "calendar_feed_enabled": ft.get("calendar_feed_enabled", False),
        },
    }


def _serialize_team(config) -> dict:
    """Build the team section from a SchedulerConfig."""
    rs = config.routing_strategy
    strategy_value = rs.value if hasattr(rs, "value") else (rs or "relationship")
    return {
        "strategy": strategy_value,
        "overflow": {
            "accept_overflow_bookings": config.accept_overflow_bookings if config.accept_overflow_bookings is not None else False,
        },
    }


def _serialize_advanced(config) -> dict:
    """Build the advanced section from a SchedulerConfig."""
    ft = config.feature_toggles or {} if hasattr(config, "feature_toggles") else {}
    dmm = config.default_meeting_mode
    meeting_mode_value = dmm.value if hasattr(dmm, "value") else (dmm or "video")
    return {
        "ai": {
            "ai_scheduling_enabled": config.ai_scheduling_enabled if config.ai_scheduling_enabled is not None else True,
            "ai_can_reschedule": config.ai_can_reschedule if config.ai_can_reschedule is not None else True,
            "ai_can_cancel": config.ai_can_cancel if config.ai_can_cancel is not None else False,
            "auto_reschedule_enabled": config.auto_reschedule_enabled if config.auto_reschedule_enabled is not None else True,
            "smart_reminders_enabled": config.smart_reminders_enabled if config.smart_reminders_enabled is not None else True,
        },
        "display": {
            "default_meeting_mode": meeting_mode_value,
            "preferred_meeting_modes": config.preferred_meeting_modes or ["video", "phone"],
        },
        "feature_toggles": ft,
    }


def _serialize_ai_scheduling(config) -> dict:
    """Build the AI scheduling section from a SchedulerConfig."""
    stored = config.ai_scheduling_config or {} if hasattr(config, "ai_scheduling_config") else {}
    return {
        "enabled": config.ai_scheduling_enabled if config.ai_scheduling_enabled is not None else True,
        "auto_book_enabled": stored.get("auto_book_enabled", False),
        "preferred_times": stored.get("preferred_times", ["10:00", "14:00", "16:00"]),
        "max_ai_bookings_per_day": stored.get("max_ai_bookings_per_day", 5),
        "buffer_before_minutes": stored.get("buffer_before_minutes", 15),
        "buffer_after_minutes": stored.get("buffer_after_minutes", 10),
        "allowed_appointment_types": stored.get("allowed_appointment_types", ["discovery_call", "pre_purchase_consultation", "document_review"]),
        "require_confirmation": stored.get("require_confirmation", True),
        "confirmation_method": stored.get("confirmation_method", "sms"),
        "smart_scheduling": stored.get("smart_scheduling", {
            "avoid_back_to_back": True,
            "cluster_similar_meetings": True,
            "protect_focus_time": True,
            "focus_time_blocks": ["08:00-09:30"],
        }),
        "sms_triggers": stored.get("sms_triggers", {
            "send_booking_link": True,
            "follow_up_no_response_hours": 24,
            "max_follow_ups": 3,
            "include_calendar_preview": True,
        }),
        "ai_response_handling": stored.get("ai_response_handling", {
            "auto_reschedule_on_cancel": True,
            "suggest_alternatives": 3,
            "respect_borrower_timezone": True,
        }),
    }


def _serialize_label(label) -> dict:
    """Serialize a CalendarLabel row."""
    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "icon": getattr(label, "icon", None),
        "is_default": getattr(label, "is_default", False),
        "is_personal": label.user_id is not None,
        "sort_order": getattr(label, "sort_order", 0),
    }


def _serialize_location(loc) -> dict:
    """Serialize an AppointmentLocation row."""
    return {
        "id": loc.id,
        "name": loc.name,
        "location_type": loc.location_type,
        "address_line1": loc.address_line1,
        "address_line2": getattr(loc, "address_line2", None),
        "city": loc.city,
        "state": loc.state,
        "zip_code": loc.zip_code,
        "meeting_url": loc.meeting_url,
        "phone_number": loc.phone_number,
        "instructions": getattr(loc, "instructions", None),
        "is_default": loc.is_default,
        "is_active": loc.is_active,
    }


# ============================================================================
# Reset tokens are stored in the SchedulerConfig.feature_toggles JSON field
# under the '_reset_token' key: {"token": str, "expires_at": ISO string}
# This ensures multi-worker safety (no in-memory state).
# ============================================================================

RESET_TOKEN_TTL_SECONDS = 300


# ============================================================================
# GET /settings/all - Unified settings blob
# ============================================================================

@router.get("/settings/all")
async def get_all_settings(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Return ALL scheduler settings for the current user as a single JSON blob.

    Sections: availability, appointment_types, notifications, booking_page,
    integrations, cancellation_policy, team, advanced, locations, labels,
    setup_completed, setup_progress.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    config = _get_or_create_config(db, user_id, org_id)

    # Appointment types
    models = get_models()
    AppointmentType = models.get("AppointmentType")
    appointment_types = []
    if AppointmentType:
        at_rows = (
            db.query(AppointmentType)
            .filter(
                AppointmentType.config_id == config.id,
                AppointmentType.organization_id == org_id,
            )
            .order_by(AppointmentType.display_order, AppointmentType.id)
            .all()
        )
        appointment_types = [_serialize_appointment_type(at) for at in at_rows]

    # Labels
    labels_list = []
    try:
        from database.models.calendar_label import CalendarLabel
        from sqlalchemy import or_, asc
        label_rows = (
            db.query(CalendarLabel)
            .filter(
                CalendarLabel.organization_id == org_id,
                or_(
                    CalendarLabel.user_id.is_(None),
                    CalendarLabel.user_id == user_id,
                ),
            )
            .order_by(asc(CalendarLabel.sort_order), asc(CalendarLabel.id))
            .all()
        )
        labels_list = [_serialize_label(lbl) for lbl in label_rows]
    except Exception:
        logger.debug("CalendarLabel model not available, skipping labels")

    # Locations
    locations_list = []
    try:
        from database.models.appointment_location import AppointmentLocation
        from sqlalchemy import or_ as or_clause, asc as asc_order
        loc_rows = (
            db.query(AppointmentLocation)
            .filter(
                AppointmentLocation.organization_id == org_id,
                AppointmentLocation.is_active == True,  # noqa: E712
            )
            .order_by(AppointmentLocation.name)
            .all()
        )
        locations_list = [_serialize_location(loc) for loc in loc_rows]
    except Exception:
        logger.debug("AppointmentLocation model not available, skipping locations")

    # Cancellation policy
    cancellation_policy = {}
    try:
        from services.cancellation_policy_service import CancellationPolicyService
        svc = CancellationPolicyService(db)
        policy = svc.get_or_create_policy(org_id)
        cancellation_policy = {
            "min_notice_hours": policy.min_notice_hours,
            "max_cancellations_per_borrower": policy.max_cancellations_per_borrower,
            "allow_borrower_cancel": policy.allow_borrower_cancel,
            "require_reason": policy.require_reason,
            "cancellation_reasons": policy.cancellation_reasons or [],
            "late_cancel_message": policy.late_cancel_message or "",
        }
    except Exception:
        logger.debug("CancellationPolicy not available, using empty defaults")

    # Setup progress
    setup_completed = getattr(config, "setup_completed", False) or False
    setup_progress = getattr(config, "setup_progress", None) or {"completed_steps": [], "current_step": 0}

    db.commit()

    return {
        "availability": _serialize_config_availability(config),
        "appointment_types": appointment_types,
        "notifications": _serialize_notifications(config),
        "booking_page": _serialize_booking_page(config),
        "integrations": _serialize_integrations(config),
        "cancellation_policy": cancellation_policy,
        "team": _serialize_team(config),
        "advanced": _serialize_advanced(config),
        "ai_scheduling": _serialize_ai_scheduling(config),
        "locations": locations_list,
        "labels": labels_list,
        "setup_completed": setup_completed,
        "setup_progress": setup_progress,
    }


# ============================================================================
# GET /settings/ai-scheduling - AI scheduling settings
# ============================================================================

@router.get("/settings/ai-scheduling")
async def get_ai_scheduling_settings(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get AI scheduling settings for the current user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)
    config = _get_or_create_config(db, user_id, org_id)
    db.commit()
    return {"data": _serialize_ai_scheduling(config)}


# ============================================================================
# PUT /settings/{section} - Update a specific section
# ============================================================================

@router.put("/settings/{section}")
async def update_settings_section(
    section: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Update a specific settings section.

    Accepted sections: availability, notifications, booking_page,
    integrations, team, advanced.
    """
    if section not in VALID_SECTIONS:
        scheduler_error(
            400, INVALID_SECTION,
            f"Invalid settings section '{section}'",
            detail=f"Valid sections: {sorted(VALID_SECTIONS)}",
        )

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    # Team section requires admin
    if section == "team" and not _is_scheduler_admin(user):
        scheduler_error(403, FORBIDDEN, "Admin access required to modify team settings")

    # Parse and validate body
    body_json = await request.json()
    model_cls = SECTION_MODELS[section]
    try:
        payload = model_cls(**body_json)
    except Exception as e:
        scheduler_error(
            422, VALIDATION_ERROR,
            "Invalid settings data",
            detail=str(e),
        )

    config = _get_or_create_config(db, user_id, org_id)
    changes = {}

    if section == "availability":
        _apply_availability(config, payload, changes)
    elif section == "notifications":
        _apply_notifications(config, payload, changes)
    elif section == "booking_page":
        _apply_booking_page(config, payload, changes)
    elif section == "integrations":
        _apply_integrations(config, payload, changes)
    elif section == "team":
        _apply_team(config, payload, changes)
    elif section == "advanced":
        _apply_advanced(config, payload, changes)
    elif section == "ai_scheduling":
        _apply_ai_scheduling(config, payload, changes)

    # Phase 2 reverse sync: if working_hours JSON was updated, propagate to
    # RecurringAvailability structured tables so both sources stay consistent.
    if section == "availability" and changes.get("working_hours"):
        _sync_working_hours_json_to_recurring(
            db, user_id, org_id, config.working_hours,
            timezone_str=config.timezone or DEFAULT_TIMEZONE,
        )

    config.updated_at = datetime.now(timezone.utc)
    db.flush()

    _audit_log(
        db, org_id, user_id, "settings_changed", "settings",
        entity_id=config.id, changes={"section": section, "fields": changes},
        request=request,
    )
    db.commit()

    # Return the updated section
    section_serializers = {
        "availability": _serialize_config_availability,
        "notifications": _serialize_notifications,
        "booking_page": _serialize_booking_page,
        "integrations": _serialize_integrations,
        "team": _serialize_team,
        "advanced": _serialize_advanced,
        "ai_scheduling": _serialize_ai_scheduling,
    }

    return {
        "section": section,
        "data": section_serializers[section](config),
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


# ============================================================================
# Section apply helpers
# ============================================================================

def _apply_availability(config, payload: AvailabilityUpdate, changes: dict):
    """Apply availability section updates to config."""
    if payload.timezone is not None:
        changes["timezone"] = {"old": config.timezone, "new": payload.timezone}
        config.timezone = payload.timezone
    if payload.working_hours is not None:
        wh = {day: dv.dict() for day, dv in payload.working_hours.items()}
        changes["working_hours"] = True
        config.working_hours = wh
    if payload.lunch_break_start is not None:
        parts = payload.lunch_break_start.split(":")
        config.lunch_break_start = time(int(parts[0]), int(parts[1]))
        changes["lunch_break_start"] = payload.lunch_break_start
    if payload.lunch_break_end is not None:
        parts = payload.lunch_break_end.split(":")
        config.lunch_break_end = time(int(parts[0]), int(parts[1]))
        changes["lunch_break_end"] = payload.lunch_break_end
    if payload.enforce_lunch_break is not None:
        config.enforce_lunch_break = payload.enforce_lunch_break
        changes["enforce_lunch_break"] = payload.enforce_lunch_break
    if payload.buffer_before_minutes is not None:
        config.buffer_before_minutes = payload.buffer_before_minutes
        changes["buffer_before_minutes"] = payload.buffer_before_minutes
    if payload.buffer_after_minutes is not None:
        config.buffer_after_minutes = payload.buffer_after_minutes
        changes["buffer_after_minutes"] = payload.buffer_after_minutes
    if payload.max_meetings_per_day is not None:
        config.max_meetings_per_day = payload.max_meetings_per_day
        changes["max_meetings_per_day"] = payload.max_meetings_per_day
    if payload.max_consecutive_meetings is not None:
        config.max_consecutive_meetings = payload.max_consecutive_meetings
        changes["max_consecutive_meetings"] = payload.max_consecutive_meetings
    if payload.min_notice_hours is not None:
        config.min_notice_hours = payload.min_notice_hours
        changes["min_notice_hours"] = payload.min_notice_hours
    if payload.max_advance_days is not None:
        config.max_advance_days = payload.max_advance_days
        changes["max_advance_days"] = payload.max_advance_days
    if payload.default_duration_minutes is not None:
        config.default_duration_minutes = payload.default_duration_minutes
        changes["default_duration_minutes"] = payload.default_duration_minutes


def _apply_notifications(config, payload: NotificationsUpdate, changes: dict):
    """Apply notifications section updates to config."""
    ns = dict(config.notification_settings or {})
    for field_name in payload.__fields__:
        value = getattr(payload, field_name)
        if value is not None:
            ns[field_name] = value
            changes[field_name] = value
    config.notification_settings = ns


def _apply_booking_page(config, payload: BookingPageUpdate, changes: dict):
    """Apply booking page section updates to config."""
    lps = dict(config.landing_page_settings or {})
    for field_name in payload.__fields__:
        value = getattr(payload, field_name)
        if value is not None:
            lps[field_name] = value
            changes[field_name] = value
    config.landing_page_settings = lps


def _apply_integrations(config, payload: IntegrationsUpdate, changes: dict):
    """Apply integrations section updates to config."""
    if payload.zoom_enabled is not None:
        config.zoom_enabled = payload.zoom_enabled
        changes["zoom_enabled"] = payload.zoom_enabled
    if payload.google_meet_enabled is not None:
        config.google_meet_enabled = payload.google_meet_enabled
        changes["google_meet_enabled"] = payload.google_meet_enabled
    if payload.auto_create_meeting_link is not None:
        config.auto_create_meeting_link = payload.auto_create_meeting_link
        changes["auto_create_meeting_link"] = payload.auto_create_meeting_link

    # Feature-toggle-based integrations
    ft = dict(config.feature_toggles or {}) if hasattr(config, "feature_toggles") else {}
    for key in ("google_calendar_sync", "outlook_calendar_sync", "calendar_feed_enabled"):
        value = getattr(payload, key, None)
        if value is not None:
            ft[key] = value
            changes[key] = value
    config.feature_toggles = ft


def _apply_team(config, payload: TeamUpdate, changes: dict):
    """Apply team section updates to config."""
    if payload.routing_strategy is not None:
        config.routing_strategy = payload.routing_strategy
        changes["routing_strategy"] = payload.routing_strategy
    if payload.accept_overflow_bookings is not None:
        config.accept_overflow_bookings = payload.accept_overflow_bookings
        changes["accept_overflow_bookings"] = payload.accept_overflow_bookings


def _apply_advanced(config, payload: AdvancedUpdate, changes: dict):
    """Apply advanced section updates to config."""
    if payload.ai_scheduling_enabled is not None:
        config.ai_scheduling_enabled = payload.ai_scheduling_enabled
        changes["ai_scheduling_enabled"] = payload.ai_scheduling_enabled
    if payload.ai_can_reschedule is not None:
        config.ai_can_reschedule = payload.ai_can_reschedule
        changes["ai_can_reschedule"] = payload.ai_can_reschedule
    if payload.ai_can_cancel is not None:
        config.ai_can_cancel = payload.ai_can_cancel
        changes["ai_can_cancel"] = payload.ai_can_cancel
    if payload.auto_reschedule_enabled is not None:
        config.auto_reschedule_enabled = payload.auto_reschedule_enabled
        changes["auto_reschedule_enabled"] = payload.auto_reschedule_enabled
    if payload.smart_reminders_enabled is not None:
        config.smart_reminders_enabled = payload.smart_reminders_enabled
        changes["smart_reminders_enabled"] = payload.smart_reminders_enabled
    if payload.default_meeting_mode is not None:
        config.default_meeting_mode = payload.default_meeting_mode
        changes["default_meeting_mode"] = payload.default_meeting_mode
    if payload.preferred_meeting_modes is not None:
        config.preferred_meeting_modes = payload.preferred_meeting_modes
        changes["preferred_meeting_modes"] = payload.preferred_meeting_modes
    if payload.feature_toggles is not None:
        ft = dict(config.feature_toggles or {}) if hasattr(config, "feature_toggles") else {}
        ft.update(payload.feature_toggles)
        config.feature_toggles = ft
        changes["feature_toggles"] = payload.feature_toggles


def _apply_ai_scheduling(config, payload: AISchedulingUpdate, changes: dict):
    """Apply AI scheduling section updates to config."""
    # Master toggle stored as dedicated column
    if payload.enabled is not None:
        config.ai_scheduling_enabled = payload.enabled
        changes["ai_scheduling_enabled"] = payload.enabled

    # Everything else stored in JSON config
    current = dict(config.ai_scheduling_config or {}) if hasattr(config, "ai_scheduling_config") else {}

    for field in ("auto_book_enabled", "preferred_times", "max_ai_bookings_per_day",
                  "buffer_before_minutes", "buffer_after_minutes", "allowed_appointment_types",
                  "require_confirmation", "confirmation_method", "smart_scheduling",
                  "sms_triggers", "ai_response_handling"):
        val = getattr(payload, field, None)
        if val is not None:
            current[field] = val
            changes[field] = val

    config.ai_scheduling_config = current


# ============================================================================
# GET /settings/setup-status
# ============================================================================

@router.get("/settings/setup-status")
async def get_setup_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the setup wizard progress for the current user."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    config = _get_or_create_config(db, user_id, org_id)
    db.commit()

    return {
        "setup_completed": getattr(config, "setup_completed", False) or False,
        "setup_progress": getattr(config, "setup_progress", None) or {"completed_steps": [], "current_step": 0},
    }


# ============================================================================
# PUT /settings/setup-status
# ============================================================================

@router.put("/settings/setup-status")
async def update_setup_status(
    body: SetupStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Save setup wizard progress (completed_steps, current_step)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    config = _get_or_create_config(db, user_id, org_id)

    progress = {
        "completed_steps": body.completed_steps,
        "current_step": body.current_step,
    }
    config.setup_progress = progress

    # Auto-mark setup as completed when all wizard steps are done
    WIZARD_STEPS = ["availability", "appointment_types", "notifications", "booking_page", "integrations"]
    if all(step in body.completed_steps for step in WIZARD_STEPS):
        config.setup_completed = True

    config.updated_at = datetime.now(timezone.utc)
    db.flush()

    _audit_log(
        db, org_id, user_id, "settings_changed", "setup_status",
        entity_id=config.id, changes=progress, request=request,
    )
    db.commit()

    return {
        "setup_completed": config.setup_completed or False,
        "setup_progress": progress,
    }


# ============================================================================
# POST /settings/reset - Reset to defaults
# ============================================================================

@router.post("/settings/reset")
async def reset_settings(
    body: ResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reset all scheduler settings to defaults.

    Requires a confirmation_token previously obtained from GET /settings/reset-token.
    This is a destructive operation -- all customizations are lost.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    # Validate token (stored in DB, not in-memory)
    config = _get_or_create_config(db, user_id, org_id)
    toggles = config.feature_toggles or {}
    stored = toggles.pop("_reset_token", None)
    config.feature_toggles = toggles  # clear the token immediately (single-use)
    db.flush()

    if not stored:
        scheduler_error(400, RESET_ERROR, "No reset token found. Request one first via GET /settings/reset-token.")
    if datetime.now(timezone.utc) > datetime.fromisoformat(stored["expires_at"]):
        scheduler_error(400, RESET_ERROR, "Reset token has expired. Request a new one.")
    token = stored["token"]
    if not secrets.compare_digest(token, body.confirmation_token):
        scheduler_error(400, RESET_ERROR, "Invalid confirmation token.")

    from smart_scheduler_models import DEFAULT_WORKING_HOURS

    # Reset all fields to defaults
    config.timezone = DEFAULT_TIMEZONE
    config.working_hours = DEFAULT_WORKING_HOURS
    config.default_duration_minutes = 30
    config.min_duration_minutes = 15
    config.max_duration_minutes = 120
    config.buffer_before_minutes = 5
    config.buffer_after_minutes = 5
    config.min_notice_hours = 2
    config.max_advance_days = 60
    config.max_meetings_per_day = 8
    config.max_consecutive_meetings = 3
    config.lunch_break_start = time(12, 0)
    config.lunch_break_end = time(13, 0)
    config.enforce_lunch_break = True
    config.preferred_meeting_modes = ["video", "phone"]
    config.default_meeting_mode = "video"
    config.zoom_enabled = True
    config.google_meet_enabled = True
    config.auto_create_meeting_link = True
    config.routing_strategy = "relationship"
    config.accept_overflow_bookings = False
    config.ai_scheduling_enabled = True
    config.ai_can_reschedule = True
    config.ai_can_cancel = False
    config.auto_reschedule_enabled = True
    config.smart_reminders_enabled = True
    config.landing_page_settings = {}
    config.notification_settings = {}
    config.setup_completed = False
    config.setup_progress = {"completed_steps": [], "current_step": 0}
    config.feature_toggles = {}
    config.updated_at = datetime.now(timezone.utc)

    # Phase 2 reverse sync: reset RecurringAvailability to match defaults
    _sync_working_hours_json_to_recurring(
        db, user_id, org_id, DEFAULT_WORKING_HOURS,
        timezone_str=DEFAULT_TIMEZONE,
    )

    db.flush()

    _audit_log(
        db, org_id, user_id, "settings_reset", "settings",
        entity_id=config.id, changes={"action": "reset_to_defaults"},
        request=request,
    )
    db.commit()

    return {"status": "ok", "message": "All settings have been reset to defaults."}


@router.get("/settings/reset-token")
async def get_reset_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate a single-use confirmation token for resetting settings.
    Token expires after 5 minutes.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)

    config = _get_or_create_config(db, user_id, org_id)
    toggles = config.feature_toggles or {}
    toggles["_reset_token"] = {
        "token": token,
        "expires_at": expires_at.isoformat(),
    }
    config.feature_toggles = toggles
    db.flush()

    return {
        "confirmation_token": token,
        "expires_in_seconds": RESET_TOKEN_TTL_SECONDS,
    }


# ============================================================================
# GET /settings/export - Export settings as JSON
# ============================================================================

@router.get("/settings/export")
async def export_settings(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Export all scheduler settings as a JSON object suitable for backup or
    transfer to another user/org.

    Does NOT include entity IDs or organization_id -- those are stripped to
    keep the export portable.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    config = _get_or_create_config(db, user_id, org_id)
    db.commit()

    # Build exportable settings blob
    export_data = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "availability": _serialize_config_availability(config),
        "notifications": _serialize_notifications(config),
        "booking_page": _serialize_booking_page(config),
        "integrations": _serialize_integrations(config),
        "team": _serialize_team(config),
        "advanced": _serialize_advanced(config),
        "setup_completed": getattr(config, "setup_completed", False) or False,
        "setup_progress": getattr(config, "setup_progress", None) or {"completed_steps": [], "current_step": 0},
    }

    # Appointment types (strip IDs for portability)
    models = get_models()
    AppointmentType = models.get("AppointmentType")
    if AppointmentType:
        at_rows = (
            db.query(AppointmentType)
            .filter(
                AppointmentType.config_id == config.id,
                AppointmentType.organization_id == org_id,
            )
            .order_by(AppointmentType.display_order, AppointmentType.id)
            .all()
        )
        export_data["appointment_types"] = [
            {
                "type_key": at.type_key,
                "type_name": at.type_name,
                "description": at.description,
                "default_duration_minutes": at.default_duration_minutes,
                "allowed_durations": at.allowed_durations or [],
                "allowed_modes": at.allowed_modes or [],
                "color": at.color,
                "icon": at.icon,
                "display_order": at.display_order,
                "is_public": at.is_public,
                "intake_questions": at.intake_questions or [],
                "reminder_schedule": at.reminder_schedule or [],
            }
            for at in at_rows
        ]

    return export_data


# ============================================================================
# POST /settings/import - Import settings from JSON
# ============================================================================

@router.post("/settings/import")
async def import_settings(
    body: SettingsImport,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Import scheduler settings from a previously exported JSON payload.

    If `overwrite` is true, replaces all settings. If false (default),
    only non-null/non-empty fields from the import are applied (merge).

    Admin-only endpoint.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    if not _is_scheduler_admin(user):
        scheduler_error(403, FORBIDDEN, "Admin access required to import settings")

    data = body.data

    # Basic version check
    version = data.get("version", "1.0")
    if version not in ("1.0",):
        scheduler_error(
            400, IMPORT_ERROR,
            "Unsupported settings version",
            detail=f"Got version '{version}', supported versions: ['1.0']",
        )

    config = _get_or_create_config(db, user_id, org_id)
    applied_sections = []

    # Apply each section if present
    if "availability" in data:
        avail = data["availability"]
        if avail.get("timezone"):
            config.timezone = avail["timezone"]
        wh = avail.get("working_hours")
        if wh:
            config.working_hours = wh
        dd = avail.get("default_duration_minutes")
        if dd:
            config.default_duration_minutes = dd
        buffers = avail.get("buffers", {})
        if buffers.get("before_minutes") is not None:
            config.buffer_before_minutes = buffers["before_minutes"]
        if buffers.get("after_minutes") is not None:
            config.buffer_after_minutes = buffers["after_minutes"]
        daily = avail.get("daily_limits", {})
        if daily.get("max_meetings_per_day") is not None:
            config.max_meetings_per_day = daily["max_meetings_per_day"]
        if daily.get("max_consecutive_meetings") is not None:
            config.max_consecutive_meetings = daily["max_consecutive_meetings"]
        bw = avail.get("booking_window", {})
        if bw.get("min_notice_hours") is not None:
            config.min_notice_hours = bw["min_notice_hours"]
        if bw.get("max_advance_days") is not None:
            config.max_advance_days = bw["max_advance_days"]
        lb = avail.get("lunch_break", {})
        if lb.get("start"):
            parts = lb["start"].split(":")
            config.lunch_break_start = time(int(parts[0]), int(parts[1]))
        if lb.get("end"):
            parts = lb["end"].split(":")
            config.lunch_break_end = time(int(parts[0]), int(parts[1]))
        if lb.get("enforced") is not None:
            config.enforce_lunch_break = lb["enforced"]
        # Phase 2 reverse sync: propagate imported working_hours to
        # RecurringAvailability structured tables.
        if wh:
            _sync_working_hours_json_to_recurring(
                db, user_id, org_id, wh,
                timezone_str=avail.get("timezone", config.timezone or DEFAULT_TIMEZONE),
            )
        applied_sections.append("availability")

    if "notifications" in data:
        ns_import = data["notifications"]
        # Flatten the nested structure back to notification_settings
        flat = {}
        reminders = ns_import.get("reminders", {})
        flat["email_reminder_24h"] = reminders.get("email_24h", True)
        flat["email_reminder_2h"] = reminders.get("email_2h", True)
        flat["sms_reminder_24h"] = reminders.get("sms_24h", False)
        flat["sms_reminder_2h"] = reminders.get("sms_2h", False)
        flat["push_notifications"] = reminders.get("push", True)
        events = ns_import.get("events", {})
        flat["booking_confirmation"] = events.get("booking_confirmation", True)
        flat["cancellation_notification"] = events.get("cancellation", True)
        flat["reschedule_notification"] = events.get("reschedule", True)
        qh = ns_import.get("quiet_hours", {})
        flat["quiet_hours_enabled"] = qh.get("enabled", False)
        flat["quiet_hours_start"] = qh.get("start", "21:00")
        flat["quiet_hours_end"] = qh.get("end", "08:00")
        digest = ns_import.get("digest", {})
        flat["daily_digest_enabled"] = digest.get("daily_digest_enabled", False)
        flat["daily_digest_time"] = digest.get("daily_digest_time", "08:00")
        flat["browser_notifications"] = ns_import.get("browser", True)
        if body.overwrite:
            config.notification_settings = flat
        else:
            existing = dict(config.notification_settings or {})
            existing.update(flat)
            config.notification_settings = existing
        applied_sections.append("notifications")

    if "booking_page" in data:
        bp = data["booking_page"]
        # Flatten nested structure back to landing_page_settings
        flat_lps = {}
        for sub in ("branding", "content", "profile", "social_proof"):
            sub_data = bp.get(sub, {})
            flat_lps.update(sub_data)
        if body.overwrite:
            config.landing_page_settings = flat_lps
        else:
            existing = dict(config.landing_page_settings or {})
            existing.update(flat_lps)
            config.landing_page_settings = existing
        applied_sections.append("booking_page")

    if "integrations" in data:
        ig = data["integrations"]
        google = ig.get("google", {})
        if google.get("meet_enabled") is not None:
            config.google_meet_enabled = google["meet_enabled"]
        zoom = ig.get("zoom", {})
        if zoom.get("enabled") is not None:
            config.zoom_enabled = zoom["enabled"]
        ml = ig.get("meeting_link", {})
        if ml.get("auto_create") is not None:
            config.auto_create_meeting_link = ml["auto_create"]
        # Feature toggle integrations
        ft = dict(config.feature_toggles or {}) if hasattr(config, "feature_toggles") else {}
        if google.get("calendar_sync") is not None:
            ft["google_calendar_sync"] = google["calendar_sync"]
        outlook = ig.get("outlook", {})
        if outlook.get("calendar_sync") is not None:
            ft["outlook_calendar_sync"] = outlook["calendar_sync"]
        feed = ig.get("feed", {})
        if feed.get("calendar_feed_enabled") is not None:
            ft["calendar_feed_enabled"] = feed["calendar_feed_enabled"]
        config.feature_toggles = ft
        applied_sections.append("integrations")

    if "team" in data:
        tm = data["team"]
        if tm.get("strategy"):
            config.routing_strategy = tm["strategy"]
        overflow = tm.get("overflow", {})
        if overflow.get("accept_overflow_bookings") is not None:
            config.accept_overflow_bookings = overflow["accept_overflow_bookings"]
        applied_sections.append("team")

    if "advanced" in data:
        adv = data["advanced"]
        ai = adv.get("ai", {})
        for key in ("ai_scheduling_enabled", "ai_can_reschedule", "ai_can_cancel",
                     "auto_reschedule_enabled", "smart_reminders_enabled"):
            if ai.get(key) is not None:
                setattr(config, key, ai[key])
        display = adv.get("display", {})
        if display.get("default_meeting_mode"):
            config.default_meeting_mode = display["default_meeting_mode"]
        if display.get("preferred_meeting_modes"):
            config.preferred_meeting_modes = display["preferred_meeting_modes"]
        imported_ft = adv.get("feature_toggles")
        if imported_ft:
            ft = dict(config.feature_toggles or {}) if hasattr(config, "feature_toggles") else {}
            ft.update(imported_ft)
            config.feature_toggles = ft
        applied_sections.append("advanced")

    if "setup_completed" in data:
        config.setup_completed = bool(data["setup_completed"])
    if "setup_progress" in data:
        config.setup_progress = data["setup_progress"]

    config.updated_at = datetime.now(timezone.utc)
    db.flush()

    _audit_log(
        db, org_id, user_id, "settings_imported", "settings",
        entity_id=config.id,
        changes={"sections": applied_sections, "overwrite": body.overwrite},
        request=request,
    )
    db.commit()

    return {
        "status": "ok",
        "applied_sections": applied_sections,
        "message": f"Imported {len(applied_sections)} section(s) successfully.",
    }


# ============================================================================
# GET /settings/availability-source - Check availability source divergence
# ============================================================================

@router.get("/settings/availability-source")
async def get_availability_source_info(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Check which availability source is active and whether the two sources
    (RecurringAvailability rows vs SchedulerConfig.working_hours JSON) are
    diverged.

    When both exist, the RecurringAvailability tables take precedence and the
    JSON blob is effectively ignored by slot generation -- but the settings UI
    may still display/edit the JSON blob without the user realizing it has no
    effect.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    # Check if RecurringAvailability rows exist for this user
    has_recurring = False
    try:
        from services.recurring_availability_service import RecurringAvailabilityService
        ra_service = RecurringAvailabilityService(db)
        recurring_rows = ra_service.get_weekly_schedule(user_id, org_id)
        has_recurring = bool(recurring_rows)
    except Exception as e:
        logger.debug(f"RecurringAvailability check failed: {e}")

    # Check if working_hours JSON exists in SchedulerConfig
    config = _get_or_create_config(db, user_id, org_id)
    has_json = bool(config.working_hours and len(config.working_hours) > 0)

    active_source = "recurring" if has_recurring else "json"
    # Both exist means the JSON blob may be stale / out of sync
    is_diverged = has_recurring and has_json

    return {
        "active_source": active_source,
        "has_recurring_availability": has_recurring,
        "has_working_hours_json": has_json,
        "is_diverged": is_diverged,
        "warning": (
            "Your availability settings may be out of sync. Changes made in "
            "Settings may not take effect because recurring availability rules "
            "take precedence."
        ) if is_diverged else None,
    }
