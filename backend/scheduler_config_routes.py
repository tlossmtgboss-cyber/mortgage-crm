"""
Scheduler Configuration Routes
Extracted from smart_scheduler_routes.py

Endpoints:
- GET/POST/PUT /config
- GET/PUT /landing-page-settings
- GET/POST/PUT/DELETE /appointment-types
- POST /seed-defaults
- POST /migrate
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from smart_scheduler_models import (
    MeetingType, RoutingStrategy, DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_WORKING_HOURS
)
from scheduler_models import (
    SchedulerConfigCreate, SchedulerConfigUpdate,
    LandingPageSettings, AppointmentTypeCreate, AppointmentTypeUpdate
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module"""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


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
# SCHEDULER CONFIG ENDPOINTS
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
# LANDING PAGE SETTINGS ENDPOINTS
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
# APPOINTMENT TYPE ENDPOINTS
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
                "requires_loan_id": t.requires_loan_id,
                "requires_lead_id": t.requires_lead_id,
                "intake_questions": t.intake_questions,
                "color": t.color,
                "icon": t.icon,
                "is_public": t.is_public,
                "public_slug": t.public_slug,
                "is_active": t.is_active
            }
            for t in types
        ],
        "source": "database"
    }


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
        requires_loan_id=type_data.requires_loan_id,
        requires_lead_id=type_data.requires_lead_id,
        intake_questions=type_data.intake_questions,
        color=type_data.color,
        icon=type_data.icon,
        is_public=type_data.is_public,
        public_slug=type_data.public_slug
    )

    db.add(appt_type)
    db.commit()
    db.refresh(appt_type)

    return {"message": "Appointment type created", "type_id": appt_type.id}


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


# ============================================================================
# SEED DEFAULT APPOINTMENT TYPES
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


# ============================================================================
# MIGRATION ENDPOINT
# ============================================================================

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
            from sqlalchemy import text
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
