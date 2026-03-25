"""
Scheduler Conflicts - Conflict detection, listing, and resolution endpoints.

Endpoints:
  GET  /conflicts/check                    Check for conflicts before booking
  GET  /conflicts/list                     List all current conflicts for user
  POST /conflicts/resolve/{appointment_id} Resolve by moving to alternative slot
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import logging

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id,
    _check_appointment_conflict, _audit_log,
)
from routes.scheduler.constants import DEFAULT_APPOINTMENT_DURATION_MINUTES
from routes.scheduler.error_responses import (
    validation_error, not_found_error, conflict_error,
    internal_error, service_unavailable_error,
)
from db import get_db
from middleware.feature_gate import require_feature_tier
from services.conflict_resolution_service import (
    detect_conflicts,
    suggest_alternatives,
    list_user_conflicts,
    auto_resolve_soft_conflicts,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC REQUEST MODELS
# ============================================================================

class ResolveConflictRequest(BaseModel):
    new_start: str = Field(..., description="ISO 8601 datetime for new start")
    new_end: str = Field(..., description="ISO 8601 datetime for new end")


# ============================================================================
# PYDANTIC RESPONSE MODELS
# ============================================================================

class ConflictDetail(BaseModel):
    """A single scheduling conflict."""
    severity: str = Field(..., description="Conflict severity: 'hard' or 'soft'")
    appointment_id: Optional[int] = Field(None, description="ID of the conflicting appointment")
    title: Optional[str] = Field(None, description="Title of the conflicting appointment")
    scheduled_start: Optional[str] = Field(None, description="Start time of conflicting appointment (ISO 8601)")
    scheduled_end: Optional[str] = Field(None, description="End time of conflicting appointment (ISO 8601)")
    reason: Optional[str] = Field(None, description="Human-readable conflict reason")

    model_config = ConfigDict(extra="allow")


class AlternativeSlot(BaseModel):
    """A suggested alternative time slot."""
    start: str = Field(..., description="Suggested start time (ISO 8601)")
    end: str = Field(..., description="Suggested end time (ISO 8601)")
    score: Optional[float] = Field(None, description="Preference score for this alternative")

    model_config = ConfigDict(extra="allow")


class SoftResolution(BaseModel):
    """An auto-resolved soft conflict."""
    conflict_index: Optional[int] = Field(None, description="Index of the resolved conflict")
    action: Optional[str] = Field(None, description="Resolution action taken")
    message: Optional[str] = Field(None, description="Resolution description")

    model_config = ConfigDict(extra="allow")


class ConflictCheckResponse(BaseModel):
    """Response for conflict check endpoint."""
    has_conflicts: bool = Field(..., description="Whether any conflicts were found")
    has_hard_conflicts: bool = Field(False, description="Whether any hard (unresolvable) conflicts exist")
    has_soft_conflicts: bool = Field(False, description="Whether any soft (auto-resolvable) conflicts exist")
    conflict_count: int = Field(0, description="Total number of conflicts detected")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="List of conflict details")
    alternatives: List[Dict[str, Any]] = Field(default_factory=list, description="Suggested alternative time slots")
    soft_resolutions: List[Dict[str, Any]] = Field(default_factory=list, description="Auto-resolved soft conflicts")


class ConflictPair(BaseModel):
    """A pair of conflicting appointments."""
    appointment_a_id: Optional[int] = None
    appointment_b_id: Optional[int] = None
    overlap_start: Optional[str] = None
    overlap_end: Optional[str] = None
    severity: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ConflictListResponse(BaseModel):
    """Response for conflict list endpoint."""
    user_id: int = Field(..., description="User whose conflicts are listed")
    conflict_count: int = Field(0, description="Total number of conflict pairs found")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="List of conflict pairs")


class ConflictResolveResponse(BaseModel):
    """Response for conflict resolution endpoint."""
    status: str = Field(..., description="Resolution status (e.g. 'resolved')")
    appointment_id: int = Field(..., description="ID of the rescheduled appointment")
    old_start: Optional[str] = Field(None, description="Previous start time (ISO 8601)")
    old_end: Optional[str] = Field(None, description="Previous end time (ISO 8601)")
    new_start: str = Field(..., description="New start time (ISO 8601)")
    new_end: str = Field(..., description="New end time (ISO 8601)")
    remaining_soft_conflicts: int = Field(0, description="Number of remaining soft conflicts in the new slot")


# ============================================================================
# CHECK FOR CONFLICTS
# ============================================================================

@router.get("/conflicts/check", response_model=ConflictCheckResponse)
@require_feature_tier("scheduler_conflicts")
async def check_conflicts(
    request: Request,
    user_id: Optional[int] = Query(None, description="User ID to check (defaults to current user)"),
    start: str = Query(..., description="ISO 8601 start datetime"),
    end: str = Query(..., description="ISO 8601 end datetime"),
    exclude_appointment_id: Optional[int] = Query(None, description="Appointment ID to exclude (for edits)"),
    duration_minutes: Optional[int] = Query(DEFAULT_APPOINTMENT_DURATION_MINUTES, description="Duration in minutes for alternative suggestions"),
    db: Session = Depends(get_db),
):
    """
    Check for conflicts before booking or editing an appointment.

    Returns any overlapping appointments and suggested alternative times.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    # Default to current user if no user_id specified
    target_user_id = user_id or current_user.id

    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00').replace('+00:00', ''))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00').replace('+00:00', ''))
    except (ValueError, TypeError) as e:
        validation_error("Invalid datetime format", detail=str(e))

    if end_dt <= start_dt:
        validation_error("End time must be after start time")

    # Detect conflicts
    conflicts = detect_conflicts(
        db=db,
        user_id=target_user_id,
        start=start_dt,
        end=end_dt,
        org_id=org_id,
        exclude_id=exclude_appointment_id,
    )

    # Get alternative suggestions if there are conflicts
    alternatives = []
    if conflicts:
        duration = duration_minutes or int((end_dt - start_dt).total_seconds() / 60)
        alternatives = suggest_alternatives(
            db=db,
            user_id=target_user_id,
            start=start_dt,
            end=end_dt,
            duration=duration,
            org_id=org_id,
        )

    # Auto-resolve soft conflicts
    soft_resolutions = auto_resolve_soft_conflicts(conflicts)

    has_hard_conflicts = any(c['severity'] == 'hard' for c in conflicts)
    has_soft_conflicts = any(c['severity'] == 'soft' for c in conflicts)

    return {
        'has_conflicts': len(conflicts) > 0,
        'has_hard_conflicts': has_hard_conflicts,
        'has_soft_conflicts': has_soft_conflicts,
        'conflict_count': len(conflicts),
        'conflicts': conflicts,
        'alternatives': alternatives,
        'soft_resolutions': soft_resolutions,
    }


# ============================================================================
# LIST ALL CURRENT CONFLICTS
# ============================================================================

@router.get("/conflicts/list", response_model=ConflictListResponse)
@require_feature_tier("scheduler_conflicts")
async def list_conflicts(
    request: Request,
    user_id: Optional[int] = Query(None, description="User ID (defaults to current user)"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    List all current scheduling conflicts for a user.

    Scans existing appointments within the date range and returns all
    overlapping pairs.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    target_user_id = user_id or current_user.id

    parsed_start = None
    parsed_end = None
    if start_date:
        try:
            parsed_start = date.fromisoformat(start_date)
        except ValueError:
            validation_error("Invalid start_date format (expected YYYY-MM-DD)")
    if end_date:
        try:
            parsed_end = date.fromisoformat(end_date)
        except ValueError:
            validation_error("Invalid end_date format (expected YYYY-MM-DD)")

    conflict_pairs = list_user_conflicts(
        db=db,
        user_id=target_user_id,
        org_id=org_id,
        start_date=parsed_start,
        end_date=parsed_end,
    )

    return {
        'user_id': target_user_id,
        'conflict_count': len(conflict_pairs),
        'conflicts': conflict_pairs,
    }


# ============================================================================
# RESOLVE CONFLICT BY MOVING APPOINTMENT
# ============================================================================

@router.post("/conflicts/resolve/{appointment_id}", response_model=ConflictResolveResponse)
@require_feature_tier("scheduler_conflicts")
async def resolve_conflict(
    appointment_id: int,
    body: ResolveConflictRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Resolve a conflict by moving an appointment to a new time slot.

    Validates the new slot is conflict-free before applying the change.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    _models = get_models()
    Appointment = _models.get('Appointment')
    if not Appointment:
        service_unavailable_error("Scheduler models not available")

    from sqlalchemy import or_

    # Fetch the appointment (must belong to this org and be accessible by user)
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == current_user.id,
            Appointment.created_by_user_id == current_user.id,
        ),
    ).first()

    if not appointment:
        not_found_error("Appointment not found")

    from smart_scheduler_models import AppointmentStatus
    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        validation_error("Cannot reschedule a cancelled or completed appointment")

    # Parse new times
    try:
        new_start = datetime.fromisoformat(body.new_start.replace('Z', '+00:00').replace('+00:00', ''))
        new_end = datetime.fromisoformat(body.new_end.replace('Z', '+00:00').replace('+00:00', ''))
    except (ValueError, TypeError) as e:
        validation_error("Invalid datetime format", detail=str(e))

    if new_end <= new_start:
        validation_error("End time must be after start time")

    # Verify new slot is conflict-free
    new_conflicts = detect_conflicts(
        db=db,
        user_id=appointment.assigned_user_id,
        start=new_start,
        end=new_end,
        org_id=org_id,
        exclude_id=appointment_id,
    )

    hard_conflicts = [c for c in new_conflicts if c['severity'] == 'hard']
    if hard_conflicts:
        conflict_error("The selected time slot still has conflicts. Please choose a different time.")

    # Store old times for audit
    old_start = appointment.scheduled_start
    old_end = appointment.scheduled_end

    # Apply the change
    appointment.scheduled_start = new_start
    appointment.scheduled_end = new_end
    appointment.duration_minutes = int((new_end - new_start).total_seconds() / 60)
    appointment.reschedule_count = (appointment.reschedule_count or 0) + 1

    # Audit log
    _audit_log(
        db, org_id, current_user.id,
        action='conflict_resolve',
        entity_type='appointment',
        entity_id=appointment_id,
        changes={
            'old_start': old_start.isoformat() if old_start else None,
            'old_end': old_end.isoformat() if old_end else None,
            'new_start': new_start.isoformat(),
            'new_end': new_end.isoformat(),
        },
        request=request,
    )

    db.commit()

    return {
        'status': 'resolved',
        'appointment_id': appointment_id,
        'old_start': old_start.isoformat() if old_start else None,
        'old_end': old_end.isoformat() if old_end else None,
        'new_start': new_start.isoformat(),
        'new_end': new_end.isoformat(),
        'remaining_soft_conflicts': len([c for c in new_conflicts if c['severity'] == 'soft']),
    }
