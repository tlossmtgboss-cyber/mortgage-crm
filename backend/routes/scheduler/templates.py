"""
Appointment Template Routes - CRUD for pre-configured appointment settings.

Templates are reusable appointment presets (e.g., "Discovery Call - 30min Virtual")
that pre-fill form fields when creating new appointments.

Endpoints:
  - GET    /templates                 List org's appointment templates
  - POST   /templates                 Create template
  - PUT    /templates/{id}            Update template
  - DELETE /templates/{id}            Soft delete template
  - POST   /templates/{id}/duplicate  Clone template
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone
from typing import Optional
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# SERIALIZER
# ============================================================================

def _serialize_template(t) -> dict:
    """Serialize an AppointmentTemplate to a JSON-safe dict."""
    return {
        "id": t.id,
        "organization_id": t.organization_id,
        "created_by": t.created_by,
        "name": t.name,
        "description": t.description,
        "duration_minutes": t.duration_minutes,
        "appointment_type": t.appointment_type,
        "location_type": t.location_type,
        "default_location": t.default_location,
        "buffer_before_minutes": t.buffer_before_minutes,
        "buffer_after_minutes": t.buffer_after_minutes,
        "intake_form_fields": t.intake_form_fields or [],
        "reminder_config": t.reminder_config or {},
        "is_active": t.is_active,
        "is_default": t.is_default,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ============================================================================
# LIST TEMPLATES
# ============================================================================

@router.get("/templates")
async def list_appointment_templates(
    request: Request,
    include_inactive: bool = Query(False, description="Include deactivated templates"),
    db: Session = Depends(get_db),
):
    """List all appointment templates for the authenticated user's organization."""
    from database.models.appointment_template import AppointmentTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    query = db.query(AppointmentTemplate).filter(
        AppointmentTemplate.organization_id == org_id,
        AppointmentTemplate.deleted_at.is_(None),
    )

    if not include_inactive:
        query = query.filter(AppointmentTemplate.is_active == True)

    templates = query.order_by(
        AppointmentTemplate.sort_order.asc(),
        AppointmentTemplate.name.asc(),
    ).all()

    return {
        "templates": [_serialize_template(t) for t in templates],
        "total": len(templates),
    }


# ============================================================================
# CREATE TEMPLATE
# ============================================================================

VALID_LOCATION_TYPES = ("in_person", "virtual", "phone")
MAX_TEMPLATES_PER_ORG = 50


@router.post("/templates", status_code=201)
async def create_appointment_template(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new appointment template for the organization."""
    from database.models.appointment_template import AppointmentTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    body = await request.json()

    # Validate required fields
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="name must be 200 characters or fewer")

    duration = body.get("duration_minutes", 30)
    if not isinstance(duration, int) or duration < 5 or duration > 480:
        raise HTTPException(status_code=400, detail="duration_minutes must be an integer between 5 and 480")

    location_type = body.get("location_type", "virtual")
    if location_type not in VALID_LOCATION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"location_type must be one of: {', '.join(VALID_LOCATION_TYPES)}",
        )

    buffer_before = body.get("buffer_before_minutes", 0)
    buffer_after = body.get("buffer_after_minutes", 0)
    if not isinstance(buffer_before, int) or buffer_before < 0 or buffer_before > 120:
        raise HTTPException(status_code=400, detail="buffer_before_minutes must be 0-120")
    if not isinstance(buffer_after, int) or buffer_after < 0 or buffer_after > 120:
        raise HTTPException(status_code=400, detail="buffer_after_minutes must be 0-120")

    # Cap at MAX_TEMPLATES_PER_ORG to prevent abuse
    existing_count = (
        db.query(AppointmentTemplate)
        .filter(
            AppointmentTemplate.organization_id == org_id,
            AppointmentTemplate.deleted_at.is_(None),
        )
        .count()
    )
    if existing_count >= MAX_TEMPLATES_PER_ORG:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_TEMPLATES_PER_ORG} appointment templates per organization",
        )

    # If setting as default, clear existing default
    is_default = bool(body.get("is_default", False))
    if is_default:
        _clear_org_default(db, org_id)

    template = AppointmentTemplate(
        organization_id=org_id,
        created_by=getattr(user, "id", None),
        name=name,
        description=(body.get("description") or "").strip() or None,
        duration_minutes=duration,
        appointment_type=(body.get("appointment_type") or "").strip() or None,
        location_type=location_type,
        default_location=(body.get("default_location") or "").strip() or None,
        buffer_before_minutes=buffer_before,
        buffer_after_minutes=buffer_after,
        intake_form_fields=body.get("intake_form_fields") or [],
        reminder_config=body.get("reminder_config") or {},
        is_active=body.get("is_active", True),
        is_default=is_default,
        sort_order=body.get("sort_order", existing_count),
    )
    db.add(template)
    db.flush()

    _audit_log(
        db, org_id, getattr(user, "id", None), "created",
        "appointment_template", template.id,
        changes={"name": template.name, "location_type": template.location_type},
        request=request,
    )
    db.commit()

    return _serialize_template(template)


# ============================================================================
# UPDATE TEMPLATE
# ============================================================================

@router.put("/templates/{template_id}")
async def update_appointment_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update an existing appointment template."""
    from database.models.appointment_template import AppointmentTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    template = (
        db.query(AppointmentTemplate)
        .filter(
            AppointmentTemplate.id == template_id,
            AppointmentTemplate.organization_id == org_id,
            AppointmentTemplate.deleted_at.is_(None),
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    body = await request.json()
    changes = {}

    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        if len(name) > 200:
            raise HTTPException(status_code=400, detail="name must be 200 characters or fewer")
        changes["name"] = {"old": template.name, "new": name}
        template.name = name

    if "description" in body:
        template.description = (body["description"] or "").strip() or None

    if "duration_minutes" in body:
        duration = body["duration_minutes"]
        if not isinstance(duration, int) or duration < 5 or duration > 480:
            raise HTTPException(status_code=400, detail="duration_minutes must be 5-480")
        changes["duration_minutes"] = {"old": template.duration_minutes, "new": duration}
        template.duration_minutes = duration

    if "appointment_type" in body:
        template.appointment_type = (body["appointment_type"] or "").strip() or None

    if "location_type" in body:
        lt = body["location_type"]
        if lt not in VALID_LOCATION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"location_type must be one of: {', '.join(VALID_LOCATION_TYPES)}",
            )
        changes["location_type"] = {"old": template.location_type, "new": lt}
        template.location_type = lt

    if "default_location" in body:
        template.default_location = (body["default_location"] or "").strip() or None

    if "buffer_before_minutes" in body:
        val = body["buffer_before_minutes"]
        if not isinstance(val, int) or val < 0 or val > 120:
            raise HTTPException(status_code=400, detail="buffer_before_minutes must be 0-120")
        template.buffer_before_minutes = val

    if "buffer_after_minutes" in body:
        val = body["buffer_after_minutes"]
        if not isinstance(val, int) or val < 0 or val > 120:
            raise HTTPException(status_code=400, detail="buffer_after_minutes must be 0-120")
        template.buffer_after_minutes = val

    if "intake_form_fields" in body:
        template.intake_form_fields = body["intake_form_fields"] or []

    if "reminder_config" in body:
        template.reminder_config = body["reminder_config"] or {}

    if "is_active" in body:
        changes["is_active"] = {"old": template.is_active, "new": body["is_active"]}
        template.is_active = bool(body["is_active"])

    if "is_default" in body:
        new_default = bool(body["is_default"])
        if new_default and not template.is_default:
            _clear_org_default(db, org_id)
        changes["is_default"] = {"old": template.is_default, "new": new_default}
        template.is_default = new_default

    if "sort_order" in body:
        template.sort_order = int(body["sort_order"])

    if changes:
        _audit_log(
            db, org_id, getattr(user, "id", None), "updated",
            "appointment_template", template.id,
            changes=changes,
            request=request,
        )

    db.commit()

    return _serialize_template(template)


# ============================================================================
# DELETE TEMPLATE (soft delete)
# ============================================================================

@router.delete("/templates/{template_id}")
async def delete_appointment_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Soft-delete an appointment template."""
    from database.models.appointment_template import AppointmentTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    template = (
        db.query(AppointmentTemplate)
        .filter(
            AppointmentTemplate.id == template_id,
            AppointmentTemplate.organization_id == org_id,
            AppointmentTemplate.deleted_at.is_(None),
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.deleted_at = datetime.now(timezone.utc)
    template.is_active = False

    _audit_log(
        db, org_id, getattr(user, "id", None), "deleted",
        "appointment_template", template_id,
        changes={"name": template.name},
        request=request,
    )
    db.commit()

    return {"success": True, "deleted_id": template_id}


# ============================================================================
# DUPLICATE TEMPLATE
# ============================================================================

@router.post("/templates/{template_id}/duplicate", status_code=201)
async def duplicate_appointment_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Clone an existing appointment template."""
    from database.models.appointment_template import AppointmentTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    source = (
        db.query(AppointmentTemplate)
        .filter(
            AppointmentTemplate.id == template_id,
            AppointmentTemplate.organization_id == org_id,
            AppointmentTemplate.deleted_at.is_(None),
        )
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Template not found")

    # Cap check
    existing_count = (
        db.query(AppointmentTemplate)
        .filter(
            AppointmentTemplate.organization_id == org_id,
            AppointmentTemplate.deleted_at.is_(None),
        )
        .count()
    )
    if existing_count >= MAX_TEMPLATES_PER_ORG:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_TEMPLATES_PER_ORG} appointment templates per organization",
        )

    # Optionally use name from body, otherwise generate "Copy of ..."
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    clone_name = (body.get("name") or "").strip() or f"Copy of {source.name}"
    if len(clone_name) > 200:
        clone_name = clone_name[:200]

    clone = AppointmentTemplate(
        organization_id=org_id,
        created_by=getattr(user, "id", None),
        name=clone_name,
        description=source.description,
        duration_minutes=source.duration_minutes,
        appointment_type=source.appointment_type,
        location_type=source.location_type,
        default_location=source.default_location,
        buffer_before_minutes=source.buffer_before_minutes,
        buffer_after_minutes=source.buffer_after_minutes,
        intake_form_fields=list(source.intake_form_fields or []),
        reminder_config=dict(source.reminder_config or {}),
        is_active=True,
        is_default=False,  # clones are never default
        sort_order=existing_count,
    )
    db.add(clone)
    db.flush()

    _audit_log(
        db, org_id, getattr(user, "id", None), "duplicated",
        "appointment_template", clone.id,
        changes={"source_id": source.id, "source_name": source.name, "new_name": clone.name},
        request=request,
    )
    db.commit()

    return _serialize_template(clone)


# ============================================================================
# HELPERS
# ============================================================================

def _clear_org_default(db: Session, org_id: int):
    """Clear any existing default template for the organization."""
    from database.models.appointment_template import AppointmentTemplate

    db.query(AppointmentTemplate).filter(
        AppointmentTemplate.organization_id == org_id,
        AppointmentTemplate.is_default == True,
        AppointmentTemplate.deleted_at.is_(None),
    ).update({"is_default": False}, synchronize_session="fetch")
