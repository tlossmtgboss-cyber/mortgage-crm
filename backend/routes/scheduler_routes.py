"""
Scheduler Core Routes - Configuration, Settings, Appointment Types
Consolidated from:
  - smart_scheduler_routes.py (thin aggregator)
  - scheduler_config_routes.py (config CRUD, landing page, appointment types, seed, migrate)
  - routes/smart_scheduler_settings_routes.py (settings with validation, timezones, scheduling methods)

URL prefix: /api/v1/scheduler/ (applied by parent aggregator)

Sections:
  1. Scheduler Config CRUD (GET/POST/PUT /config)
  2. Landing Page Settings (GET/PUT /landing-page-settings)
  3. Appointment Type CRUD (GET/POST/PUT/DELETE /appointment-types)
  4. Seed & Migration (POST /seed-defaults, POST /migrate)
  5. Advanced Settings (GET/PUT /settings, POST /settings/test)
  6. Timezones & Scheduling Methods (GET /timezones, GET /scheduling-methods)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum
import pytz
import re
import logging

from smart_scheduler_models import (
    MeetingType, RoutingStrategy, DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_WORKING_HOURS
)
from scheduler_models import (
    SchedulerConfigCreate, SchedulerConfigUpdate,
    LandingPageSettings, AppointmentTypeCreate, AppointmentTypeUpdate,
    AppointmentTypeReorder,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None


from db import get_db


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module"""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# SECTION 1: SCHEDULER CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_scheduler_config(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the current user's scheduler configuration"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        # Return default config structure
        return {
            "config": None,
            "defaults": {
                "timezone": "America/Chicago",
                "default_duration_minutes": 30,
                "buffer_before_minutes": 5,
                "buffer_after_minutes": 5,
                "min_notice_hours": 2,
                "max_advance_days": 60,
                "max_meetings_per_day": 8,
                "working_hours": DEFAULT_WORKING_HOURS
            }
        }

    return {
        "config": {
            "id": config.id,
            "config_name": config.config_name,
            "description": config.description,
            "timezone": config.timezone,
            "default_duration_minutes": config.default_duration_minutes,
            "buffer_before_minutes": config.buffer_before_minutes,
            "buffer_after_minutes": config.buffer_after_minutes,
            "min_notice_hours": config.min_notice_hours,
            "max_advance_days": config.max_advance_days,
            "max_meetings_per_day": config.max_meetings_per_day,
            "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
            "routing_strategy": config.routing_strategy.value if config.routing_strategy else "relationship",
            "ai_scheduling_enabled": config.ai_scheduling_enabled,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }
    }


@router.post("/config")
async def create_scheduler_config(
    config_data: SchedulerConfigCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create scheduler configuration for the current user"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']

    # Check if config already exists
    existing = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Configuration already exists. Use PUT to update.")

    # Parse routing strategy
    routing_strategy = None
    if config_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(config_data.routing_strategy)
        except ValueError:
            routing_strategy = RoutingStrategy.RELATIONSHIP

    config = SchedulerConfig(
        user_id=user.id,
        organization_id=org_id,
        config_name=config_data.config_name,
        description=config_data.description,
        timezone=config_data.timezone,
        default_duration_minutes=config_data.default_duration_minutes,
        buffer_before_minutes=config_data.buffer_before_minutes,
        buffer_after_minutes=config_data.buffer_after_minutes,
        min_notice_hours=config_data.min_notice_hours,
        max_advance_days=config_data.max_advance_days,
        max_meetings_per_day=config_data.max_meetings_per_day,
        working_hours=config_data.working_hours or DEFAULT_WORKING_HOURS,
        routing_strategy=routing_strategy,
        ai_scheduling_enabled=config_data.ai_scheduling_enabled
    )

    db.add(config)
    db.commit()
    db.refresh(config)

    return {"message": "Scheduler configuration created", "config_id": config.id}


@router.put("/config")
async def update_scheduler_config(
    config_data: SchedulerConfigUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update scheduler configuration"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Update fields
    update_fields = config_data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for field, value in update_fields.items():
        if field in _protected:
            continue
        if field == "routing_strategy" and value:
            try:
                value = RoutingStrategy(value)
            except ValueError:
                continue
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"message": "Configuration updated", "config_id": config.id}


# ============================================================================
# SECTION 2: LANDING PAGE SETTINGS ENDPOINTS
# ============================================================================

@router.get("/landing-page-settings")
async def get_landing_page_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get landing page customization settings"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    # Return default settings if no config exists
    default_settings = {
        "logo_url": "",
        "profile_picture_url": "",
        "video_url": "",
        "video_type": "youtube",
        "headline": "Schedule a Meeting",
        "subheadline": "Choose a time that works for you",
        "description": "",
        "show_profile": True,
        "profile_name": user.first_name or "",
        "profile_title": "Loan Officer",
        "profile_bio": "",
        "accent_color": "#217F8D",
        "background_style": "white",
        "show_company_logo": True,
        "show_social_proof": False,
        "testimonial_text": "",
        "testimonial_author": ""
    }

    if not config:
        return {"settings": default_settings}

    # Get landing page settings from config (stored as JSON)
    stored_settings = getattr(config, 'landing_page_settings', None) or {}

    # Merge with defaults
    settings = {**default_settings, **stored_settings}

    return {"settings": settings}


@router.put("/landing-page-settings")
async def update_landing_page_settings(
    settings_data: LandingPageSettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update landing page customization settings"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        # Auto-create config with landing page settings
        config = SchedulerConfig(
            user_id=user.id,
            organization_id=org_id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS,
            landing_page_settings=settings_data.model_dump()
        )
        db.add(config)
    else:
        # Update existing config
        config.landing_page_settings = settings_data.model_dump()

    db.commit()

    logger.info(f"Landing page settings updated for user {user.id}")

    return {"message": "Landing page settings saved successfully"}


# ============================================================================
# SECTION 3: APPOINTMENT TYPE ENDPOINTS
# ============================================================================

@router.get("/appointment-types")
async def list_appointment_types(
    request: Request,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """List all appointment types"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        SchedulerConfig = _models['SchedulerConfig']
        AppointmentType = _models['AppointmentType']

        # Get user's config
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user.id,
            SchedulerConfig.organization_id == org_id
        ).first()

        if not config:
            # Return default types
            return {"appointment_types": DEFAULT_APPOINTMENT_TYPES, "source": "defaults"}

        query = db.query(AppointmentType).filter(
            AppointmentType.config_id == config.id,
            AppointmentType.organization_id == org_id
        )

        if not include_inactive:
            query = query.filter(AppointmentType.is_active == True)

        types = query.order_by(AppointmentType.display_order).all()

        return {
            "appointment_types": [
                {
                    "id": t.id,
                    "type_key": t.type_key,
                    "type_name": t.type_name,
                    "description": t.description,
                    "meeting_type": t.meeting_type.value if t.meeting_type else "custom",
                    "default_duration_minutes": t.default_duration_minutes,
                    "allowed_durations": t.allowed_durations,
                    "allowed_modes": t.allowed_modes,
                    "default_mode": t.default_mode.value if t.default_mode else (t.allowed_modes[0] if t.allowed_modes else "video"),
                    "buffer_before": getattr(t, 'min_notice_hours', 0) or 0,
                    "buffer_after": 0,
                    "max_per_day": t.max_per_day,
                    "requires_loan_id": t.requires_loan_id,
                    "requires_lead_id": t.requires_lead_id,
                    "requires_intake": bool(t.intake_questions),
                    "intake_questions": t.intake_questions,
                    "color": t.color,
                    "icon": t.icon,
                    "is_public": t.is_public,
                    "public_slug": t.public_slug,
                    "display_order": t.display_order,
                    "is_active": t.is_active,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in types
            ],
            "source": "database"
        }
    except Exception as e:
        logger.warning(f"Scheduler tables not available for appointment types query: {e}")
        return {"appointment_types": DEFAULT_APPOINTMENT_TYPES, "source": "defaults"}


@router.post("/appointment-types")
async def create_appointment_type(
    type_data: AppointmentTypeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment type"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        # Auto-create config
        config = SchedulerConfig(
            user_id=user.id,
            organization_id=org_id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    # Check for duplicate type_key
    existing = db.query(AppointmentType).filter(
        AppointmentType.config_id == config.id,
        AppointmentType.organization_id == org_id,
        AppointmentType.type_key == type_data.type_key
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Appointment type with this key already exists")

    # Parse meeting type
    meeting_type = MeetingType.CUSTOM
    if type_data.meeting_type:
        try:
            meeting_type = MeetingType(type_data.meeting_type)
        except ValueError:
            pass

    # Scope slug uniqueness to org
    if type_data.public_slug:
        slug_exists = db.query(AppointmentType).filter(
            AppointmentType.organization_id == org_id,
            AppointmentType.public_slug == type_data.public_slug
        ).first()
        if slug_exists:
            raise HTTPException(status_code=400, detail="An appointment type with this slug already exists")

    # Calculate display_order: put new type at end
    from sqlalchemy import func as sqla_func
    max_order = db.query(sqla_func.max(AppointmentType.display_order)).filter(
        AppointmentType.config_id == config.id,
        AppointmentType.organization_id == org_id,
    ).scalar()
    next_order = (max_order or 0) + 1

    # Parse default_mode if provided
    from smart_scheduler_models import MeetingMode
    default_mode = None
    if type_data.default_mode:
        try:
            default_mode = MeetingMode(type_data.default_mode)
        except ValueError:
            pass

    appt_type = AppointmentType(
        config_id=config.id,
        organization_id=org_id,
        type_key=type_data.type_key,
        type_name=type_data.type_name,
        description=type_data.description,
        meeting_type=meeting_type,
        default_duration_minutes=type_data.default_duration_minutes,
        allowed_durations=type_data.allowed_durations,
        allowed_modes=type_data.allowed_modes,
        default_mode=default_mode,
        max_per_day=type_data.max_per_day,
        requires_loan_id=type_data.requires_loan_id,
        requires_lead_id=type_data.requires_lead_id,
        requires_contact_info=True,
        intake_questions=type_data.intake_questions,
        color=type_data.color,
        icon=type_data.icon,
        is_public=type_data.is_public,
        public_slug=type_data.public_slug,
        display_order=next_order,
    )

    db.add(appt_type)
    db.commit()
    db.refresh(appt_type)

    return {"message": "Appointment type created", "type_id": appt_type.id}


@router.put("/appointment-types/reorder")
async def reorder_appointment_types(
    reorder_data: AppointmentTypeReorder,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reorder appointment types by providing an ordered list of IDs."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    # Get user's config to scope the query
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Scheduler configuration not found")

    # Verify all IDs belong to this user's config and org
    types = db.query(AppointmentType).filter(
        AppointmentType.config_id == config.id,
        AppointmentType.organization_id == org_id,
        AppointmentType.id.in_(reorder_data.ordered_ids),
    ).all()

    type_map = {t.id: t for t in types}

    if len(type_map) != len(reorder_data.ordered_ids):
        raise HTTPException(
            status_code=400,
            detail="Some appointment type IDs are invalid or do not belong to your configuration"
        )

    # Update display_order based on list position
    for idx, type_id in enumerate(reorder_data.ordered_ids):
        type_map[type_id].display_order = idx

    db.commit()

    return {"message": f"Reordered {len(reorder_data.ordered_ids)} appointment types"}


@router.put("/appointment-types/{type_id}")
async def update_appointment_type(
    type_id: int,
    type_data: AppointmentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment type"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    # Verify ownership scoped to org
    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        AppointmentType.organization_id == org_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    update_fields = type_data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for field, value in update_fields.items():
        if field not in _protected:
            setattr(appt_type, field, value)

    db.commit()

    return {"message": "Appointment type updated"}


@router.delete("/appointment-types/{type_id}")
async def delete_appointment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete (deactivate) an appointment type"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        AppointmentType.organization_id == org_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    appt_type.is_active = False
    db.commit()

    return {"message": "Appointment type deactivated"}


@router.post("/appointment-types/{type_id}/duplicate")
async def duplicate_appointment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Clone an appointment type with a new name."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    original = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        AppointmentType.organization_id == org_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not original:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    # Calculate next display_order
    from sqlalchemy import func as sqla_func
    max_order = db.query(sqla_func.max(AppointmentType.display_order)).filter(
        AppointmentType.config_id == original.config_id,
        AppointmentType.organization_id == org_id,
    ).scalar()
    next_order = (max_order or 0) + 1

    # Generate unique type_key
    base_key = f"{original.type_key}_copy"
    suffix = 1
    new_key = base_key
    while db.query(AppointmentType).filter(
        AppointmentType.config_id == original.config_id,
        AppointmentType.organization_id == org_id,
        AppointmentType.type_key == new_key
    ).first():
        new_key = f"{base_key}_{suffix}"
        suffix += 1

    clone = AppointmentType(
        config_id=original.config_id,
        organization_id=org_id,
        type_key=new_key,
        type_name=f"{original.type_name} (Copy)",
        description=original.description,
        meeting_type=original.meeting_type,
        default_duration_minutes=original.default_duration_minutes,
        allowed_durations=original.allowed_durations,
        allowed_modes=original.allowed_modes,
        default_mode=original.default_mode,
        min_notice_hours=original.min_notice_hours,
        max_advance_days=original.max_advance_days,
        max_per_day=original.max_per_day,
        max_per_week=original.max_per_week,
        requires_loan_id=original.requires_loan_id,
        requires_lead_id=original.requires_lead_id,
        requires_contact_info=original.requires_contact_info,
        intake_questions=original.intake_questions or [],
        send_confirmation=original.send_confirmation,
        reminder_schedule=original.reminder_schedule,
        assigned_users=original.assigned_users,
        routing_strategy=original.routing_strategy,
        color=original.color,
        icon=original.icon,
        display_order=next_order,
        is_public=original.is_public,
        public_slug=None,  # Slug must be unique, so don't copy
        is_active=True,
    )

    db.add(clone)
    db.commit()
    db.refresh(clone)

    logger.info(f"Appointment type {type_id} duplicated as {clone.id} by user {user.id}")

    return {
        "message": "Appointment type duplicated",
        "type_id": clone.id,
        "type_key": clone.type_key,
        "type_name": clone.type_name,
    }


# ============================================================================
# SECTION 4: SEED DEFAULT APPOINTMENT TYPES & MIGRATION
# ============================================================================

@router.post("/seed-defaults")
async def seed_default_appointment_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """Seed default appointment types for the user"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        config = SchedulerConfig(
            user_id=user.id,
            organization_id=org_id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    created_count = 0

    for default_type in DEFAULT_APPOINTMENT_TYPES:
        # Check if already exists
        existing = db.query(AppointmentType).filter(
            AppointmentType.config_id == config.id,
            AppointmentType.organization_id == org_id,
            AppointmentType.type_key == default_type["type_key"]
        ).first()

        if not existing:
            appt_type = AppointmentType(
                config_id=config.id,
                organization_id=org_id,
                type_key=default_type["type_key"],
                type_name=default_type["type_name"],
                description=default_type["description"],
                meeting_type=default_type["meeting_type"],
                default_duration_minutes=default_type["default_duration_minutes"],
                allowed_durations=default_type["allowed_durations"],
                requires_loan_id=default_type["requires_loan_id"],
                requires_lead_id=default_type["requires_lead_id"],
                intake_questions=default_type["intake_questions"],
                color=default_type["color"],
                icon=default_type["icon"],
                is_public=True,
                public_slug=f"{user.id}-{default_type['type_key']}"
            )
            db.add(appt_type)
            created_count += 1

    db.commit()

    return {
        "message": f"Seeded {created_count} default appointment types",
        "config_id": config.id
    }


@router.post("/migrate")
async def run_scheduler_migration(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create all scheduler tables if they don't exist.
    This is safe to call multiple times.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Only admins can trigger schema migrations
    user_role = (getattr(user, 'permission_role', '') or getattr(user, 'role', '') or '').lower()
    if user_role not in ('admin', 'site_admin', 'platform_admin'):
        raise HTTPException(status_code=403, detail="Admin access required for schema migration")

    try:
        # Get all model classes
        SchedulerConfig = _models['SchedulerConfig']
        AvailabilitySlot = _models['AvailabilitySlot']
        AppointmentType = _models['AppointmentType']
        Appointment = _models['Appointment']
        RoutingRule = _models['RoutingRule']
        BlockedTime = _models['BlockedTime']
        BookingLink = _models['BookingLink']
        AppointmentReminder = _models['AppointmentReminder']

        # Get the metadata from any model
        metadata = SchedulerConfig.__table__.metadata

        # Create all tables
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        existing_tables = inspector.get_table_names()

        tables_to_create = [
            'scheduler_configs',
            'availability_slots',
            'appointment_types',
            'scheduler_appointments',
            'scheduler_routing_rules',
            'scheduler_blocked_times',
            'scheduler_booking_links',
            'scheduler_reminders'
        ]

        created = []
        for table_name in tables_to_create:
            if table_name not in existing_tables:
                created.append(table_name)

        # Create tables
        metadata.create_all(bind=db.bind, checkfirst=True)

        # Add landing_page_settings column if it doesn't exist
        try:
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'scheduler_configs' AND column_name = 'landing_page_settings'
            """))
            if not result.fetchone():
                db.execute(text("ALTER TABLE scheduler_configs ADD COLUMN landing_page_settings JSONB DEFAULT '{}'::jsonb"))
                db.commit()
                logger.info("Added landing_page_settings column to scheduler_configs")
        except Exception as col_e:
            logger.warning(f"Could not add landing_page_settings column: {col_e}")

        logger.info(f"Scheduler migration complete. Created tables: {created}")

        # Ensure demo booking link exists (scoped to org)
        demo_link = db.query(BookingLink).filter(
            BookingLink.slug == "demo",
            BookingLink.organization_id == org_id
        ).first()
        if not demo_link:
            # Create default appointment types first
            demo_type = db.query(AppointmentType).filter(
                AppointmentType.type_key == "demo_consultation",
                AppointmentType.organization_id == org_id
            ).first()
            if not demo_type:
                demo_type = AppointmentType(
                    user_id=user.id,
                    organization_id=org_id,
                    type_name="Demo Consultation",
                    type_key="demo_consultation",
                    description="Schedule a demo of our mortgage production management platform",
                    default_duration_minutes=30,
                    allowed_durations=[15, 30, 45, 60],
                    meeting_type="consultation",
                    meeting_mode="video",
                    color="#667eea",
                    icon="calendar",
                    is_public=True,
                    is_active=True,
                    requires_confirmation=False,
                    buffer_before_minutes=5,
                    buffer_after_minutes=5
                )
                db.add(demo_type)
                db.flush()

            demo_link = BookingLink(
                user_id=user.id,
                organization_id=org_id,
                slug="demo",
                link_name="Schedule a Demo",
                description="Book a personalized demo of Perennia AI - Intelligent Mortgage Production Manager",
                is_active=True,
                is_public=True,
                appointment_type_ids=[demo_type.id],
                custom_title="Schedule Your Demo",
                custom_description="See how Perennia AI can transform your mortgage operations with AI-powered automation.",
                routing_strategy="round_robin",
                max_bookings_per_day=10
            )
            db.add(demo_link)
            db.commit()
            logger.info("Created demo booking link")

        return {
            "message": "Scheduler migration complete",
            "created_tables": created,
            "existing_tables": [t for t in tables_to_create if t in existing_tables],
            "demo_link_exists": True
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")


# ============================================================================
# SECTION 5: ADVANCED SETTINGS (from smart_scheduler_settings_routes.py)
# With comprehensive validation, permission checks, and capacity estimates
# ============================================================================

# --- Enums ---

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


# --- Pydantic Models with Validation ---

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


# --- Helper Functions ---

def _validate_settings_warnings(settings: SmartSchedulerSettingsUpdate) -> List[str]:
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


def _calculate_weekly_capacity(business_hours: BusinessHours, booking_settings: BookingSettings) -> Dict[str, Any]:
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


# --- Settings API Routes ---

@router.get("/settings")
async def get_scheduler_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current Smart Scheduler settings.

    Returns the scheduler configuration including business hours,
    booking settings, AI preferences, and video conferencing options.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        # Import response helpers (from settings routes pattern)
        try:
            from utils.error_handling import success_response, DatabaseException
        except ImportError:
            success_response = lambda data, message="": {"status": "success", "data": data, "message": message}
            DatabaseException = HTTPException

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
            WHERE sc.organization_id = :org_id AND (sc.user_id = :user_id OR sc.team_id = :org_id)
            ORDER BY sc.user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": user.id,
            "org_id": org_id
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
        raise HTTPException(status_code=500, detail="Failed to retrieve scheduler settings")


@router.put("/settings")
async def update_scheduler_settings(
    settings: SmartSchedulerSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update Smart Scheduler settings.

    Validates all settings including:
    - Timezone validity
    - Business hours logic (end > start)
    - At least one working day enabled
    - Reasonable booking limits

    Returns updated settings, warnings, and capacity estimates.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Import response helpers
    try:
        from utils.error_handling import success_response, PermissionException, DatabaseException
    except ImportError:
        success_response = lambda data, message="": {"status": "success", "data": data, "message": message}
        PermissionException = HTTPException
        DatabaseException = HTTPException

    # 1. Check permission
    has_permission = getattr(user, 'has_permission', lambda x: True)
    if not has_permission("manage_settings"):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to update scheduler settings"
        )

    # 2. Validate and collect warnings
    warnings = _validate_settings_warnings(settings)

    # 3. Get or create config
    try:
        result = db.execute(text("""
            SELECT id FROM scheduler_configs
            WHERE organization_id = :org_id AND (user_id = :user_id OR team_id = :org_id)
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": user.id,
            "org_id": org_id
        })

        row = result.fetchone()
        config_id = row.id if row else None

    except SQLAlchemyError as e:
        logger.error(f"Database error checking config: {e}")
        raise HTTPException(status_code=500, detail="Failed to check existing configuration")

    # 4. Build update data
    update_fields = []
    update_params = {"user_id": user.id, "org_id": org_id}

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
                    organization_id, user_id, team_id, config_name, timezone, working_hours,
                    default_duration_minutes, buffer_before_minutes, buffer_after_minutes,
                    min_notice_hours, max_advance_days, max_meetings_per_day,
                    routing_strategy, ai_scheduling_enabled, ai_can_reschedule,
                    ai_can_cancel, smart_reminders_enabled, auto_reschedule_enabled,
                    default_meeting_mode, zoom_enabled, google_meet_enabled,
                    auto_create_meeting_link, is_active, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :org_id, 'Default Configuration',
                    :timezone, :working_hours,
                    :default_duration_minutes, :buffer_before_minutes, :buffer_after_minutes,
                    :min_notice_hours, :max_advance_days, :max_meetings_per_day,
                    :routing_strategy, :ai_scheduling_enabled, :ai_can_reschedule,
                    :ai_can_cancel, :smart_reminders_enabled, :auto_reschedule_enabled,
                    :default_meeting_mode, :zoom_enabled, :google_meet_enabled,
                    :auto_create_meeting_link, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "user_id": user.id,
                "org_id": org_id,
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
        raise HTTPException(status_code=500, detail="Failed to save scheduler settings. Please try again.")

    # 6. Calculate capacity if we have business hours and booking settings
    capacity = None
    if settings.business_hours and settings.booking_settings:
        capacity = _calculate_weekly_capacity(settings.business_hours, settings.booking_settings)

    logger.info(f"Scheduler settings updated by user {user.id}")

    return success_response(
        data={
            "updated": True,
            "warnings": warnings,
            "capacity": capacity,
        },
        message="Scheduler settings updated successfully"
    )


@router.post("/settings/test")
async def test_scheduler_configuration(
    test_request: TestSchedulerRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Test scheduler configuration.

    Validates that the current settings allow bookings to be made.
    Can optionally test against a specific date.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Import response helpers
    try:
        from utils.error_handling import success_response, DatabaseException
    except ImportError:
        success_response = lambda data, message="": {"status": "success", "data": data, "message": message}
        DatabaseException = HTTPException

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
            WHERE organization_id = :org_id AND (user_id = :user_id OR team_id = :org_id)
            ORDER BY user_id IS NOT NULL DESC
            LIMIT 1
        """), {
            "user_id": user.id,
            "org_id": org_id
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
                "test_date": test_request.test_date,
                "test_duration": test_request.test_duration,
            },
            message="Configuration test passed" if success else "Configuration test found issues"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error testing scheduler: {e}")
        raise HTTPException(status_code=500, detail="Failed to test scheduler configuration")


# ============================================================================
# SECTION 6: TIMEZONES & SCHEDULING METHODS
# ============================================================================

@router.get("/timezones")
async def get_available_timezones(
    search: Optional[str] = Query(None, description="Filter timezones by name")
):
    """
    Get list of available timezones.

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

    # Import response helpers
    try:
        from utils.error_handling import success_response
    except ImportError:
        success_response = lambda data, message="": {"status": "success", "data": data, "message": message}

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
            "description": "Book directly with you - no routing or distribution",
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

    # Import response helpers
    try:
        from utils.error_handling import success_response
    except ImportError:
        success_response = lambda data, message="": {"status": "success", "data": data, "message": message}

    return success_response(
        data={"methods": methods},
        message="Scheduling methods retrieved"
    )
