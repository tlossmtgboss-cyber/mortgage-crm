"""
Scheduler Label Routes - CRUD for calendar color labels.

Endpoints:
  - GET    /labels                    List labels for the user's org (org-wide + personal)
  - POST   /labels                    Create a new label
  - PUT    /labels/{id}               Update a label
  - DELETE /labels/{id}               Delete a label
  - PUT    /labels/reorder            Batch-update sort order
  - POST   /labels/assign             Assign label(s) to an appointment
  - DELETE /labels/assign             Remove label(s) from an appointment
  - GET    /labels/appointment/{id}   Get labels for a specific appointment
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import asc
from datetime import datetime, timezone
from typing import Optional
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from routes.scheduler.error_responses import (
    validation_error, not_found_error, conflict_error,
)
from db import get_db
from middleware.feature_gate import require_feature_tier

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# LIST LABELS
# ============================================================================

@router.get("/labels")
@require_feature_tier("scheduler_labels")
async def list_labels(
    request: Request,
    include_personal: bool = Query(True, description="Include personal labels"),
    db: Session = Depends(get_db),
):
    """List all calendar labels visible to the authenticated user.

    Returns org-wide labels (user_id IS NULL) plus the user's personal
    labels (user_id = current user), ordered by sort_order.
    """
    from database.models.calendar_label import CalendarLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    from sqlalchemy import or_

    filters = [CalendarLabel.organization_id == org_id]

    if include_personal and user_id:
        filters.append(
            or_(
                CalendarLabel.user_id.is_(None),
                CalendarLabel.user_id == user_id,
            )
        )
    else:
        filters.append(CalendarLabel.user_id.is_(None))

    labels = (
        db.query(CalendarLabel)
        .filter(*filters)
        .order_by(asc(CalendarLabel.sort_order), asc(CalendarLabel.id))
        .all()
    )

    return {
        "labels": [_serialize_label(label) for label in labels],
        "total": len(labels),
    }


# ============================================================================
# CREATE LABEL
# ============================================================================

@router.post("/labels", status_code=201)
@require_feature_tier("scheduler_labels")
async def create_label(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new calendar label for the organization (or personal)."""
    from database.models.calendar_label import CalendarLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)
    body = await request.json()

    # Validate required fields
    name = (body.get("name") or "").strip()
    if not name:
        validation_error("name is required")
    if len(name) > 50:
        validation_error("name must be 50 characters or fewer")

    color = (body.get("color") or "").strip()
    if not color:
        validation_error("color is required")
    if not _is_valid_hex_color(color):
        validation_error("color must be a valid hex color (e.g. #4A90D9)")

    icon = (body.get("icon") or "").strip() or None
    is_personal = body.get("is_personal", False)

    # Determine ownership
    label_user_id = user_id if is_personal else None

    # Cap at 30 labels per org to prevent abuse
    existing_count = (
        db.query(CalendarLabel)
        .filter(CalendarLabel.organization_id == org_id)
        .count()
    )
    if existing_count >= 30:
        validation_error("Maximum of 30 labels per organization")

    # Check for duplicate name within scope
    from sqlalchemy import or_

    duplicate_filter = [
        CalendarLabel.organization_id == org_id,
        CalendarLabel.name == name,
    ]
    if label_user_id:
        duplicate_filter.append(CalendarLabel.user_id == label_user_id)
    else:
        duplicate_filter.append(CalendarLabel.user_id.is_(None))

    existing = db.query(CalendarLabel).filter(*duplicate_filter).first()
    if existing:
        conflict_error(f"Label '{name}' already exists")

    # Get next sort_order
    max_sort = (
        db.query(CalendarLabel.sort_order)
        .filter(CalendarLabel.organization_id == org_id)
        .order_by(CalendarLabel.sort_order.desc())
        .first()
    )
    next_sort = (max_sort[0] + 1) if max_sort and max_sort[0] is not None else 0

    label = CalendarLabel(
        organization_id=org_id,
        user_id=label_user_id,
        name=name,
        color=color,
        icon=icon,
        is_default=False,
        sort_order=next_sort,
    )
    db.add(label)
    db.flush()

    _audit_log(
        db, org_id, user_id, "created",
        "calendar_label", label.id,
        changes={"name": name, "color": color},
        request=request,
    )
    db.commit()

    return _serialize_label(label)


# ============================================================================
# REORDER LABELS (must be defined before /labels/{label_id} to avoid route conflict)
# ============================================================================

@router.put("/labels/reorder")
@require_feature_tier("scheduler_labels")
async def reorder_labels(
    request: Request,
    db: Session = Depends(get_db),
):
    """Batch-update label sort order.

    Body: { "order": [label_id_1, label_id_2, ...] }
    The list position becomes the new sort_order value.
    """
    from database.models.calendar_label import CalendarLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)
    body = await request.json()

    order = body.get("order")
    if not order or not isinstance(order, list):
        validation_error("order must be a non-empty list of label IDs")

    from sqlalchemy import or_

    # Fetch all labels visible to this user in the org
    labels = (
        db.query(CalendarLabel)
        .filter(
            CalendarLabel.organization_id == org_id,
            CalendarLabel.id.in_(order),
            or_(
                CalendarLabel.user_id.is_(None),
                CalendarLabel.user_id == user_id,
            ),
        )
        .all()
    )

    label_map = {label.id: label for label in labels}

    updated = 0
    for idx, label_id in enumerate(order):
        label = label_map.get(label_id)
        if label:
            label.sort_order = idx
            updated += 1

    if updated:
        _audit_log(
            db, org_id, user_id, "reordered",
            "calendar_label", None,
            changes={"new_order": order},
            request=request,
        )

    db.commit()

    return {"success": True, "updated": updated}


# ============================================================================
# UPDATE LABEL
# ============================================================================

@router.put("/labels/{label_id}")
@require_feature_tier("scheduler_labels")
async def update_label(
    label_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update an existing calendar label."""
    from database.models.calendar_label import CalendarLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    label = _get_label_for_user(db, label_id, org_id, user_id)
    if not label:
        not_found_error("Label not found")

    body = await request.json()
    changes = {}

    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            validation_error("name cannot be empty")
        if len(name) > 50:
            validation_error("name must be 50 characters or fewer")
        changes["name"] = {"old": label.name, "new": name}
        label.name = name

    if "color" in body:
        color = (body["color"] or "").strip()
        if not _is_valid_hex_color(color):
            validation_error("color must be a valid hex color (e.g. #4A90D9)")
        changes["color"] = {"old": label.color, "new": color}
        label.color = color

    if "icon" in body:
        label.icon = (body["icon"] or "").strip() or None

    if changes:
        _audit_log(
            db, org_id, user_id, "updated",
            "calendar_label", label.id,
            changes=changes,
            request=request,
        )

    db.commit()

    return _serialize_label(label)


# ============================================================================
# DELETE LABEL
# ============================================================================

@router.delete("/labels/{label_id}")
@require_feature_tier("scheduler_labels")
async def delete_label(
    label_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a calendar label. Associated appointment_labels are CASCADE-deleted."""
    from database.models.calendar_label import CalendarLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    label = _get_label_for_user(db, label_id, org_id, user_id)
    if not label:
        not_found_error("Label not found")

    label_name = label.name
    db.delete(label)

    _audit_log(
        db, org_id, user_id, "deleted",
        "calendar_label", label_id,
        changes={"name": label_name},
        request=request,
    )
    db.commit()

    return {"success": True, "deleted_id": label_id}


# ============================================================================
# ASSIGN / UNASSIGN LABELS TO APPOINTMENTS
# ============================================================================

@router.post("/labels/assign")
@require_feature_tier("scheduler_labels")
async def assign_labels(
    request: Request,
    db: Session = Depends(get_db),
):
    """Assign one or more labels to an appointment.

    Body: { "appointment_id": int, "label_ids": [int, ...] }
    """
    from database.models.calendar_label import CalendarLabel, AppointmentLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)
    body = await request.json()

    appointment_id = body.get("appointment_id")
    label_ids = body.get("label_ids", [])

    if not appointment_id:
        validation_error("appointment_id is required")
    if not label_ids or not isinstance(label_ids, list):
        validation_error("label_ids must be a non-empty list")

    # Verify appointment belongs to this org
    from routes.scheduler._helpers import get_models
    models = get_models()
    Appointment = models["Appointment"]

    appt = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == org_id,
        )
        .first()
    )
    if not appt:
        not_found_error("Appointment not found")

    # Verify all labels belong to this org
    from sqlalchemy import or_

    valid_labels = (
        db.query(CalendarLabel)
        .filter(
            CalendarLabel.organization_id == org_id,
            CalendarLabel.id.in_(label_ids),
            or_(
                CalendarLabel.user_id.is_(None),
                CalendarLabel.user_id == user_id,
            ),
        )
        .all()
    )
    valid_ids = {label.id for label in valid_labels}

    # Get existing assignments to avoid duplicates
    existing = (
        db.query(AppointmentLabel.label_id)
        .filter(AppointmentLabel.appointment_id == appointment_id)
        .all()
    )
    existing_ids = {row[0] for row in existing}

    created = 0
    for lid in label_ids:
        if lid in valid_ids and lid not in existing_ids:
            db.add(AppointmentLabel(
                appointment_id=appointment_id,
                label_id=lid,
                assigned_by=user_id,
            ))
            created += 1

    if created:
        db.commit()

    return {"success": True, "assigned": created, "appointment_id": appointment_id}


@router.delete("/labels/assign")
@require_feature_tier("scheduler_labels")
async def unassign_labels(
    request: Request,
    db: Session = Depends(get_db),
):
    """Remove one or more labels from an appointment.

    Body: { "appointment_id": int, "label_ids": [int, ...] }
    """
    from database.models.calendar_label import AppointmentLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    body = await request.json()

    appointment_id = body.get("appointment_id")
    label_ids = body.get("label_ids", [])

    if not appointment_id:
        validation_error("appointment_id is required")
    if not label_ids or not isinstance(label_ids, list):
        validation_error("label_ids must be a non-empty list")

    # Verify appointment belongs to this org
    from routes.scheduler._helpers import get_models
    models = get_models()
    Appointment = models["Appointment"]

    appt = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == org_id,
        )
        .first()
    )
    if not appt:
        not_found_error("Appointment not found")

    deleted = (
        db.query(AppointmentLabel)
        .filter(
            AppointmentLabel.appointment_id == appointment_id,
            AppointmentLabel.label_id.in_(label_ids),
        )
        .delete(synchronize_session="fetch")
    )

    db.commit()

    return {"success": True, "removed": deleted, "appointment_id": appointment_id}


# ============================================================================
# GET LABELS FOR AN APPOINTMENT
# ============================================================================

@router.get("/labels/appointment/{appointment_id}")
@require_feature_tier("scheduler_labels")
async def get_appointment_labels(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get all labels assigned to a specific appointment."""
    from database.models.calendar_label import CalendarLabel, AppointmentLabel

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Verify appointment belongs to this org
    from routes.scheduler._helpers import get_models
    models = get_models()
    Appointment = models["Appointment"]

    appt = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == org_id,
        )
        .first()
    )
    if not appt:
        not_found_error("Appointment not found")

    labels = (
        db.query(CalendarLabel)
        .join(AppointmentLabel, AppointmentLabel.label_id == CalendarLabel.id)
        .filter(AppointmentLabel.appointment_id == appointment_id)
        .order_by(CalendarLabel.sort_order)
        .all()
    )

    return {
        "appointment_id": appointment_id,
        "labels": [_serialize_label(label) for label in labels],
    }


# ============================================================================
# HELPERS
# ============================================================================

def _serialize_label(label) -> dict:
    """Serialize a CalendarLabel to a dict."""
    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "icon": label.icon,
        "is_default": label.is_default,
        "is_personal": label.user_id is not None,
        "sort_order": label.sort_order,
        "created_at": label.created_at.isoformat() if label.created_at else None,
        "updated_at": label.updated_at.isoformat() if label.updated_at else None,
    }


def _is_valid_hex_color(color: str) -> bool:
    """Validate hex color format (#RGB or #RRGGBB)."""
    if not color or not color.startswith("#"):
        return False
    hex_part = color[1:]
    if len(hex_part) not in (3, 6):
        return False
    try:
        int(hex_part, 16)
        return True
    except ValueError:
        return False


def _get_label_for_user(db, label_id: int, org_id: int, user_id: int):
    """Get a label if it belongs to this org and is accessible to the user."""
    from database.models.calendar_label import CalendarLabel
    from sqlalchemy import or_

    return (
        db.query(CalendarLabel)
        .filter(
            CalendarLabel.id == label_id,
            CalendarLabel.organization_id == org_id,
            or_(
                CalendarLabel.user_id.is_(None),
                CalendarLabel.user_id == user_id,
            ),
        )
        .first()
    )
