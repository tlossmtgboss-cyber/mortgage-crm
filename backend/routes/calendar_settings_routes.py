"""
Calendar Settings Routes
Comprehensive settings API for the Calendar Settings page.

Covers:
  - Availability (business hours, lunch break, buffer, booking window)
  - Appointment types CRUD with reorder
  - Notification preferences (email/SMS reminders, quiet hours)
  - Booking page branding (logo, colors, tagline, link, QR)
  - Integration status (Google/Outlook connect/disconnect)
  - Team management (LO list, assignment strategy, capacity) [managers only]

URL prefix: /api/v1/calendar-settings (applied by parent include_router)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, validator
import logging
import json
import re

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendar-settings", tags=["Calendar Settings"])

# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

_get_current_user_func = None


def set_dependencies(get_current_user_func):
    """Set auth dependency from parent module."""
    global _get_current_user_func
    _get_current_user_func = get_current_user_func


async def _get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Calendar settings dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_manager(user) -> bool:
    role = (getattr(user, 'permission_role', '') or getattr(user, 'role', '') or '').lower()
    return role in ('admin', 'site_admin', 'platform_admin', 'manager', 'branch_manager')


def _success_response(data: Any, message: str = ""):
    return {"status": "success", "data": data, "message": message}


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class LunchBreak(BaseModel):
    enabled: bool = True
    start: str = Field("12:00", description="Lunch start HH:MM")
    end: str = Field("13:00", description="Lunch end HH:MM")


class AvailabilityDay(BaseModel):
    enabled: bool = True
    start: str = Field("09:00", description="Day start HH:MM")
    end: str = Field("17:00", description="Day end HH:MM")
    lunch_break: Optional[LunchBreak] = None


class AvailabilitySettings(BaseModel):
    timezone: Optional[str] = None
    business_hours: Optional[Dict[str, AvailabilityDay]] = None
    lunch_break: Optional[LunchBreak] = None
    buffer_minutes: Optional[int] = Field(None, ge=0, le=60)
    min_booking_notice_hours: Optional[int] = Field(None, ge=0, le=168)
    max_advance_booking_days: Optional[int] = Field(None, ge=1, le=365)


class AppointmentTypeCreate(BaseModel):
    type_name: str = Field(..., min_length=1, max_length=100)
    type_key: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: int = Field(30, ge=15, le=240)
    color: Optional[str] = "#218D8D"
    icon: Optional[str] = "fa-calendar"
    is_public: bool = True
    sort_order: Optional[int] = 0


class AppointmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=240)
    color: Optional[str] = None
    icon: Optional[str] = None
    is_public: Optional[bool] = None
    sort_order: Optional[int] = None


class AppointmentTypeReorder(BaseModel):
    type_ids: List[int] = Field(..., description="Ordered list of appointment type IDs")


class NotificationSettings(BaseModel):
    email_reminder_24h: Optional[bool] = True
    email_reminder_2h: Optional[bool] = True
    email_reminder_15m: Optional[bool] = False
    sms_reminder_24h: Optional[bool] = False
    sms_reminder_2h: Optional[bool] = True
    sms_reminder_15m: Optional[bool] = False
    quiet_hours_enabled: Optional[bool] = False
    quiet_hours_start: Optional[str] = "21:00"
    quiet_hours_end: Optional[str] = "08:00"
    notify_on_booking: Optional[bool] = True
    notify_on_cancellation: Optional[bool] = True
    notify_on_reschedule: Optional[bool] = True


class BookingPageSettings(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = "#218D8D"
    secondary_color: Optional[str] = "#e6f5f5"
    tagline: Optional[str] = None
    welcome_message: Optional[str] = None
    show_branding: Optional[bool] = True
    custom_css: Optional[str] = None

    @validator('custom_css', pre=True, always=True)
    def sanitize_custom_css(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        # Limit length to 10,000 characters
        v = v[:10000]
        # Strip HTML tags
        css = re.sub(r'<[^>]*>', '', v)
        # Strip CSS comments BEFORE checking for dangerous patterns.
        # This prevents bypass via comment-wrapping, e.g. "u/**/rl(" or
        # "/* url( */". Without this step, an attacker can split dangerous
        # tokens across comment boundaries to evade pattern matching.
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
        # Remove dangerous CSS constructs that enable XSS (case-insensitive)
        dangerous_patterns = [
            r'url\s*\(',               # url() can load external resources / exfiltrate data
            r'@import',                # @import can load external stylesheets
            r'expression\s*\(',        # IE CSS expression() - legacy but still a vector
            r'javascript\s*:',         # javascript: protocol in CSS values
            r'behavior\s*:',           # IE behavior: directive
            r'-moz-binding\s*:',       # Firefox XBL binding
        ]
        for pattern in dangerous_patterns:
            css = re.sub(pattern, '/* sanitized */', css, flags=re.IGNORECASE)
        # Return None if empty after cleaning
        cleaned = css.strip()
        return cleaned if cleaned else None


class TeamMemberCapacity(BaseModel):
    user_id: int
    max_daily_appointments: Optional[int] = Field(None, ge=0, le=24)
    is_accepting_appointments: Optional[bool] = True


class TeamSettings(BaseModel):
    assignment_strategy: Optional[str] = "round_robin"  # round_robin, priority, load_balanced, manual
    auto_reassign_on_absence: Optional[bool] = True
    members: Optional[List[TeamMemberCapacity]] = None


# ============================================================================
# SECTION 1: AVAILABILITY SETTINGS
# ============================================================================

@router.get("/availability")
async def get_availability_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the current user's availability / business hours settings."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = db.execute(text("""
            SELECT
                sc.id,
                sc.timezone,
                sc.working_hours,
                sc.buffer_before_minutes,
                sc.min_notice_hours,
                sc.max_advance_days,
                sc.default_duration_minutes,
                sc.max_meetings_per_day
            FROM scheduler_configs sc
            WHERE sc.organization_id = :org_id
              AND (sc.user_id = :user_id OR sc.team_id = :org_id)
            ORDER BY sc.user_id IS NOT NULL DESC
            LIMIT 1
        """), {"user_id": user.id, "org_id": org_id})
        row = result.fetchone()

        if not row:
            return _success_response({
                "timezone": "America/Chicago",
                "business_hours": {
                    "monday": {"start": "09:00", "end": "17:00", "enabled": True, "lunch_break": None},
                    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True, "lunch_break": None},
                    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True, "lunch_break": None},
                    "thursday": {"start": "09:00", "end": "17:00", "enabled": True, "lunch_break": None},
                    "friday": {"start": "09:00", "end": "17:00", "enabled": True, "lunch_break": None},
                    "saturday": {"start": "10:00", "end": "14:00", "enabled": False, "lunch_break": None},
                    "sunday": {"start": "10:00", "end": "14:00", "enabled": False, "lunch_break": None},
                },
                "lunch_break": {"enabled": True, "start": "12:00", "end": "13:00"},
                "buffer_minutes": 5,
                "min_booking_notice_hours": 2,
                "max_advance_booking_days": 60,
                "default_duration_minutes": 30,
                "max_meetings_per_day": 8,
                "is_default": True,
            }, "Default availability (no custom configuration)")

        working_hours = row.working_hours if row.working_hours else {}
        # Extract lunch_break from working_hours JSON if stored there
        lunch_break = working_hours.pop("_lunch_break", None) or {
            "enabled": True, "start": "12:00", "end": "13:00"
        }

        return _success_response({
            "config_id": row.id,
            "timezone": row.timezone or "America/Chicago",
            "business_hours": working_hours,
            "lunch_break": lunch_break,
            "buffer_minutes": row.buffer_before_minutes or 5,
            "min_booking_notice_hours": row.min_notice_hours or 2,
            "max_advance_booking_days": row.max_advance_days or 60,
            "default_duration_minutes": row.default_duration_minutes or 30,
            "max_meetings_per_day": row.max_meetings_per_day or 8,
        })

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching availability: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve availability settings")


@router.put("/availability")
async def update_availability_settings(
    settings: AvailabilitySettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update availability / business hours settings."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = db.execute(text("""
            SELECT id FROM scheduler_configs
            WHERE organization_id = :org_id AND (user_id = :user_id OR team_id = :org_id)
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {"user_id": user.id, "org_id": org_id})
        row = result.fetchone()
        config_id = row.id if row else None

        update_fields = []
        params = {"user_id": user.id, "org_id": org_id}

        if settings.timezone:
            update_fields.append("timezone = :timezone")
            params["timezone"] = settings.timezone

        if settings.business_hours is not None:
            wh = {}
            for day, day_settings in settings.business_hours.items():
                wh[day] = day_settings.dict()
            if settings.lunch_break:
                wh["_lunch_break"] = settings.lunch_break.dict()
            update_fields.append("working_hours = :working_hours")
            params["working_hours"] = json.dumps(wh)

        if settings.buffer_minutes is not None:
            update_fields.append("buffer_before_minutes = :buffer")
            update_fields.append("buffer_after_minutes = :buffer")
            params["buffer"] = settings.buffer_minutes

        if settings.min_booking_notice_hours is not None:
            update_fields.append("min_notice_hours = :min_notice")
            params["min_notice"] = settings.min_booking_notice_hours

        if settings.max_advance_booking_days is not None:
            update_fields.append("max_advance_days = :max_advance")
            params["max_advance"] = settings.max_advance_booking_days

        if config_id:
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params["config_id"] = config_id
                db.execute(text(f"""
                    UPDATE scheduler_configs
                    SET {', '.join(update_fields)}
                    WHERE id = :config_id
                """), params)
        else:
            wh_json = params.get("working_hours", json.dumps({}))
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    organization_id, user_id, team_id, config_name,
                    timezone, working_hours, buffer_before_minutes, buffer_after_minutes,
                    min_notice_hours, max_advance_days,
                    is_active, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :org_id, 'Default Configuration',
                    :tz, :wh, :buf, :buf,
                    :mn, :ma,
                    true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "org_id": org_id,
                "user_id": user.id,
                "tz": settings.timezone or "America/Chicago",
                "wh": wh_json,
                "buf": settings.buffer_minutes or 5,
                "mn": settings.min_booking_notice_hours or 2,
                "ma": settings.max_advance_booking_days or 60,
            })

        db.commit()

        return _success_response(
            {"updated": True},
            "Availability settings saved"
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating availability: {e}")
        raise HTTPException(status_code=500, detail="Failed to save availability settings")


# ============================================================================
# SECTION 2: APPOINTMENT TYPES (with reorder)
# ============================================================================

@router.get("/appointment-types")
async def get_appointment_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """List appointment types for the current user's org."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        rows = db.execute(text("""
            SELECT
                at.id, at.type_key, at.type_name, at.description,
                at.default_duration_minutes, at.color, at.icon,
                at.is_public, at.is_active, at.sort_order,
                at.created_at, at.updated_at
            FROM appointment_types at
            JOIN scheduler_configs sc ON sc.id = at.config_id
            WHERE at.organization_id = :org_id
              AND sc.user_id = :user_id
              AND at.is_active = true
            ORDER BY COALESCE(at.sort_order, 999), at.created_at
        """), {"org_id": org_id, "user_id": user.id}).fetchall()

        types = []
        for r in rows:
            types.append({
                "id": r.id,
                "type_key": r.type_key,
                "type_name": r.type_name,
                "description": r.description,
                "duration_minutes": r.default_duration_minutes,
                "color": r.color,
                "icon": r.icon,
                "is_public": r.is_public,
                "sort_order": r.sort_order or 0,
            })

        return _success_response({"appointment_types": types, "count": len(types)})

    except SQLAlchemyError as e:
        logger.error(f"Error fetching appointment types: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve appointment types")


@router.post("/appointment-types")
async def create_appointment_type(
    data: AppointmentTypeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment type."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        # Get config
        config = db.execute(text("""
            SELECT id FROM scheduler_configs
            WHERE organization_id = :org_id AND user_id = :user_id
            LIMIT 1
        """), {"org_id": org_id, "user_id": user.id}).fetchone()

        if not config:
            raise HTTPException(status_code=404, detail="Scheduler config not found. Save availability settings first.")

        type_key = data.type_key or data.type_name.lower().replace(" ", "_").replace("-", "_")

        result = db.execute(text("""
            INSERT INTO appointment_types (
                config_id, organization_id, type_key, type_name, description,
                default_duration_minutes, color, icon, is_public, sort_order,
                is_active, created_at, updated_at
            ) VALUES (
                :config_id, :org_id, :type_key, :type_name, :description,
                :duration, :color, :icon, :is_public, :sort_order,
                true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
        """), {
            "config_id": config.id,
            "org_id": org_id,
            "type_key": type_key,
            "type_name": data.type_name,
            "description": data.description,
            "duration": data.duration_minutes,
            "color": data.color,
            "icon": data.icon,
            "is_public": data.is_public,
            "sort_order": data.sort_order or 0,
        })
        new_id = result.fetchone().id
        db.commit()

        return _success_response({"id": new_id}, "Appointment type created")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating appointment type: {e}")
        raise HTTPException(status_code=500, detail="Failed to create appointment type")


@router.put("/appointment-types/{type_id}")
async def update_appointment_type(
    type_id: int,
    data: AppointmentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an existing appointment type."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        fields = []
        params = {"type_id": type_id, "org_id": org_id, "user_id": user.id}

        if data.type_name is not None:
            fields.append("type_name = :type_name")
            params["type_name"] = data.type_name
        if data.description is not None:
            fields.append("description = :description")
            params["description"] = data.description
        if data.duration_minutes is not None:
            fields.append("default_duration_minutes = :duration")
            params["duration"] = data.duration_minutes
        if data.color is not None:
            fields.append("color = :color")
            params["color"] = data.color
        if data.icon is not None:
            fields.append("icon = :icon")
            params["icon"] = data.icon
        if data.is_public is not None:
            fields.append("is_public = :is_public")
            params["is_public"] = data.is_public
        if data.sort_order is not None:
            fields.append("sort_order = :sort_order")
            params["sort_order"] = data.sort_order

        if not fields:
            return _success_response({"updated": False}, "No fields to update")

        fields.append("updated_at = CURRENT_TIMESTAMP")

        result = db.execute(text(f"""
            UPDATE appointment_types
            SET {', '.join(fields)}
            WHERE id = :type_id
              AND organization_id = :org_id
              AND config_id IN (
                  SELECT id FROM scheduler_configs WHERE user_id = :user_id
              )
        """), params)

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Appointment type not found")

        db.commit()
        return _success_response({"updated": True}, "Appointment type updated")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating appointment type: {e}")
        raise HTTPException(status_code=500, detail="Failed to update appointment type")


@router.delete("/appointment-types/{type_id}")
async def delete_appointment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Soft-delete (deactivate) an appointment type."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = db.execute(text("""
            UPDATE appointment_types
            SET is_active = false, updated_at = CURRENT_TIMESTAMP
            WHERE id = :type_id
              AND organization_id = :org_id
              AND config_id IN (
                  SELECT id FROM scheduler_configs WHERE user_id = :user_id
              )
        """), {"type_id": type_id, "org_id": org_id, "user_id": user.id})

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Appointment type not found")

        db.commit()
        return _success_response({"deleted": True}, "Appointment type removed")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting appointment type: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete appointment type")


@router.put("/appointment-types/reorder")
async def reorder_appointment_types(
    data: AppointmentTypeReorder,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reorder appointment types by providing a sorted list of IDs."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        for idx, type_id in enumerate(data.type_ids):
            db.execute(text("""
                UPDATE appointment_types
                SET sort_order = :sort_order, updated_at = CURRENT_TIMESTAMP
                WHERE id = :type_id
                  AND organization_id = :org_id
                  AND config_id IN (
                      SELECT id FROM scheduler_configs WHERE user_id = :user_id
                  )
            """), {"sort_order": idx, "type_id": type_id, "org_id": org_id, "user_id": user.id})

        db.commit()
        return _success_response({"reordered": True}, "Appointment types reordered")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error reordering appointment types: {e}")
        raise HTTPException(status_code=500, detail="Failed to reorder appointment types")


# ============================================================================
# SECTION 3: NOTIFICATION PREFERENCES
# The notification_settings JSONB column on scheduler_configs is created by
# the migration script: backend/migrations/add_notification_settings_column.py
# ============================================================================

@router.get("/notifications")
async def get_notification_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get calendar notification preferences for the current user."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = db.execute(text("""
            SELECT notification_settings
            FROM scheduler_configs
            WHERE organization_id = :org_id
              AND (user_id = :user_id OR team_id = :org_id)
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {"user_id": user.id, "org_id": org_id})
        row = result.fetchone()

        defaults = {
            "email_reminder_24h": True,
            "email_reminder_2h": True,
            "email_reminder_15m": False,
            "sms_reminder_24h": False,
            "sms_reminder_2h": True,
            "sms_reminder_15m": False,
            "quiet_hours_enabled": False,
            "quiet_hours_start": "21:00",
            "quiet_hours_end": "08:00",
            "notify_on_booking": True,
            "notify_on_cancellation": True,
            "notify_on_reschedule": True,
        }

        if row and row.notification_settings:
            data = row.notification_settings if isinstance(row.notification_settings, dict) else {}
            merged = {**defaults, **data}
        else:
            merged = defaults

        return _success_response(merged)

    except SQLAlchemyError as e:
        logger.error(f"Error fetching notification settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve notification settings")


@router.put("/notifications")
async def update_notification_settings(
    settings: NotificationSettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update calendar notification preferences."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        notif_json = json.dumps(settings.dict(exclude_unset=False))

        result = db.execute(text("""
            UPDATE scheduler_configs
            SET notification_settings = :notif, updated_at = CURRENT_TIMESTAMP
            WHERE organization_id = :org_id
              AND (user_id = :user_id OR team_id = :org_id)
        """), {"notif": notif_json, "user_id": user.id, "org_id": org_id})

        if result.rowcount == 0:
            # Create config if none exists
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    organization_id, user_id, team_id, config_name,
                    notification_settings, is_active, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :org_id, 'Default Configuration',
                    :notif, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {"org_id": org_id, "user_id": user.id, "notif": notif_json})

        db.commit()
        return _success_response({"updated": True}, "Notification settings saved")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating notification settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save notification settings")


# ============================================================================
# SECTION 4: BOOKING PAGE BRANDING
# ============================================================================

@router.get("/booking-page")
async def get_booking_page_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get booking page branding and link settings."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        result = db.execute(text("""
            SELECT sc.landing_page_settings, sc.id as config_id
            FROM scheduler_configs sc
            WHERE sc.organization_id = :org_id
              AND (sc.user_id = :user_id OR sc.team_id = :org_id)
            ORDER BY sc.user_id IS NOT NULL DESC
            LIMIT 1
        """), {"user_id": user.id, "org_id": org_id})
        row = result.fetchone()

        branding_defaults = {
            "logo_url": None,
            "primary_color": "#218D8D",
            "secondary_color": "#e6f5f5",
            "tagline": "",
            "welcome_message": "Schedule a time to meet with us",
            "show_branding": True,
            "custom_css": None,
        }

        branding = branding_defaults.copy()
        if row and row.landing_page_settings:
            lps = row.landing_page_settings if isinstance(row.landing_page_settings, dict) else {}
            branding.update({k: v for k, v in lps.items() if k in branding_defaults})

        # Get booking links
        links = db.execute(text("""
            SELECT id, slug, link_name, is_active, is_public
            FROM scheduler_booking_links
            WHERE organization_id = :org_id
              AND user_id = :user_id
              AND is_active = true
            ORDER BY created_at
        """), {"org_id": org_id, "user_id": user.id}).fetchall()

        booking_links = []
        for link in links:
            booking_links.append({
                "id": link.id,
                "slug": link.slug,
                "name": link.link_name,
                "url": f"/book/{link.slug}",
                "is_public": link.is_public,
            })

        return _success_response({
            "branding": branding,
            "booking_links": booking_links,
        })

    except SQLAlchemyError as e:
        logger.error(f"Error fetching booking page settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve booking page settings")


@router.put("/booking-page")
async def update_booking_page_settings(
    settings: BookingPageSettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update booking page branding."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        lps_json = json.dumps(settings.dict(exclude_unset=False))

        result = db.execute(text("""
            UPDATE scheduler_configs
            SET landing_page_settings = :lps, updated_at = CURRENT_TIMESTAMP
            WHERE organization_id = :org_id
              AND (user_id = :user_id OR team_id = :org_id)
        """), {"lps": lps_json, "user_id": user.id, "org_id": org_id})

        if result.rowcount == 0:
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    organization_id, user_id, team_id, config_name,
                    landing_page_settings, is_active, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :org_id, 'Default Configuration',
                    :lps, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {"org_id": org_id, "user_id": user.id, "lps": lps_json})

        db.commit()
        return _success_response({"updated": True}, "Booking page settings saved")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating booking page settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save booking page settings")


# ============================================================================
# SECTION 5: INTEGRATIONS (Google / Outlook status)
# ============================================================================

@router.get("/integrations")
async def get_integration_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get calendar integration connection status (Google, Outlook)."""
    user = await _get_current_user(request, db)

    google_status = {"connected": False, "email": None, "last_synced": None}
    outlook_status = {"connected": False, "email": None, "last_synced": None}

    try:
        # Check Google Calendar
        gcal = db.execute(text("""
            SELECT gc.google_email, gc.last_sync_at, gc.sync_enabled
            FROM google_calendar_connections gc
            WHERE gc.user_id = :user_id AND gc.is_active = true
            LIMIT 1
        """), {"user_id": user.id}).fetchone()

        if gcal:
            google_status = {
                "connected": True,
                "email": gcal.google_email,
                "last_synced": gcal.last_sync_at.isoformat() if gcal.last_sync_at else None,
                "sync_enabled": gcal.sync_enabled if hasattr(gcal, 'sync_enabled') else True,
            }
    except Exception as e:
        logger.debug(f"Google calendar table may not exist: {e}")

    try:
        # Check Outlook / Microsoft Calendar
        outlook = db.execute(text("""
            SELECT mc.email, mc.last_sync_at, mc.sync_enabled
            FROM microsoft_calendar_connections mc
            WHERE mc.user_id = :user_id AND mc.is_active = true
            LIMIT 1
        """), {"user_id": user.id}).fetchone()

        if outlook:
            outlook_status = {
                "connected": True,
                "email": outlook.email,
                "last_synced": outlook.last_sync_at.isoformat() if outlook.last_sync_at else None,
                "sync_enabled": outlook.sync_enabled if hasattr(outlook, 'sync_enabled') else True,
            }
    except Exception as e:
        logger.debug(f"Microsoft calendar table may not exist: {e}")

    return _success_response({
        "google": google_status,
        "outlook": outlook_status,
    })


# ============================================================================
# SECTION 6: TEAM MANAGEMENT (managers only)
# ============================================================================

@router.get("/team")
async def get_team_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get team calendar settings. Managers only."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Manager access required")

    try:
        # Get org-level scheduler config for assignment strategy
        org_config = db.execute(text("""
            SELECT routing_strategy
            FROM scheduler_configs
            WHERE organization_id = :org_id AND team_id = :org_id
            LIMIT 1
        """), {"org_id": org_id}).fetchone()

        assignment_strategy = org_config.routing_strategy if org_config else "round_robin"

        # Get team members (LOs) with their scheduler capacities
        members = db.execute(text("""
            SELECT
                u.id,
                u.first_name,
                u.last_name,
                u.email,
                u.is_active,
                sc.max_meetings_per_day,
                sc.is_active as scheduler_active,
                (SELECT COUNT(*) FROM scheduler_appointments sa
                 WHERE sa.loan_officer_id = u.id
                   AND sa.status NOT IN ('cancelled', 'no_show')
                   AND sa.start_time >= CURRENT_DATE
                   AND sa.start_time < CURRENT_DATE + INTERVAL '7 days'
                ) as upcoming_appointments
            FROM users u
            LEFT JOIN scheduler_configs sc ON sc.user_id = u.id AND sc.organization_id = :org_id
            WHERE u.organization_id = :org_id
              AND u.is_active = true
              AND u.role IN ('lo', 'loan_officer', 'admin', 'manager', 'site_admin')
            ORDER BY u.first_name, u.last_name
        """), {"org_id": org_id}).fetchall()

        team = []
        for m in members:
            team.append({
                "user_id": m.id,
                "name": f"{m.first_name or ''} {m.last_name or ''}".strip(),
                "email": m.email,
                "is_active": m.is_active,
                "max_daily_appointments": m.max_meetings_per_day or 8,
                "is_accepting_appointments": m.scheduler_active if m.scheduler_active is not None else True,
                "upcoming_appointments": m.upcoming_appointments or 0,
            })

        return _success_response({
            "assignment_strategy": assignment_strategy,
            "auto_reassign_on_absence": True,
            "members": team,
            "total_members": len(team),
        })

    except SQLAlchemyError as e:
        logger.error(f"Error fetching team settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve team settings")


@router.put("/team")
async def update_team_settings(
    settings: TeamSettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update team calendar settings. Managers only."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Manager access required")

    try:
        if settings.assignment_strategy:
            db.execute(text("""
                UPDATE scheduler_configs
                SET routing_strategy = :strategy, updated_at = CURRENT_TIMESTAMP
                WHERE organization_id = :org_id AND team_id = :org_id
            """), {"strategy": settings.assignment_strategy, "org_id": org_id})

        if settings.members:
            for member in settings.members:
                db.execute(text("""
                    UPDATE scheduler_configs
                    SET max_meetings_per_day = COALESCE(:max_daily, max_meetings_per_day),
                        is_active = COALESCE(:accepting, is_active),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND organization_id = :org_id
                """), {
                    "user_id": member.user_id,
                    "org_id": org_id,
                    "max_daily": member.max_daily_appointments,
                    "accepting": member.is_accepting_appointments,
                })

        db.commit()
        return _success_response({"updated": True}, "Team settings saved")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating team settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save team settings")
