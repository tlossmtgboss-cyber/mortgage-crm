"""
Incident Management Endpoints
CRUD operations for security incidents.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.incident_service import IncidentService
from ..constants import IncidentCategory, IncidentStatus, SeverityLevel
from .dependencies import get_soc2_db as get_db, get_current_admin_user

router = APIRouter()


class CreateIncidentRequest(BaseModel):
    title: str = Field(..., max_length=500)
    description: str
    category: IncidentCategory
    severity: SeverityLevel
    assigned_to: Optional[UUID] = None
    affected_systems: Optional[list[str]] = None


class UpdateStatusRequest(BaseModel):
    status: IncidentStatus
    notes: Optional[str] = None


class RootCauseRequest(BaseModel):
    root_cause: str
    remediation_steps: str
    preventive_measures: str


@router.post("/")
async def create_incident(
    request: CreateIncidentRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Create a new security incident."""
    service = IncidentService(db)
    incident_id = await service.create(
        title=request.title,
        description=request.description,
        category=request.category,
        severity=request.severity,
        reported_by=current_user.id,
        assigned_to=request.assigned_to,
        tenant_id=current_user.tenant_id,
        affected_systems=request.affected_systems,
    )
    return {"id": str(incident_id), "status": "created"}


@router.get("/")
async def list_incidents(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """List security incidents."""
    service = IncidentService(db)
    incidents = await service.list_incidents(
        tenant_id=current_user.tenant_id,
        status=status,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return {"data": incidents, "count": len(incidents)}


@router.get("/{incident_id}")
async def get_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get incident details with full timeline."""
    service = IncidentService(db)
    incident = await service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}/status")
async def update_incident_status(
    incident_id: UUID,
    request: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Update incident status (triggers timeline entry)."""
    service = IncidentService(db)
    success = await service.update_status(
        incident_id=incident_id,
        new_status=request.status,
        actor_id=current_user.id,
        notes=request.notes,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"status": "updated"}


@router.post("/{incident_id}/note")
async def add_incident_note(
    incident_id: UUID,
    note: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Add a note to an incident timeline."""
    service = IncidentService(db)
    await service.add_note(incident_id, note, current_user.id)
    return {"status": "note_added"}


@router.post("/{incident_id}/root-cause")
async def set_root_cause(
    incident_id: UUID,
    request: RootCauseRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Document root cause analysis and remediation."""
    service = IncidentService(db)
    await service.set_root_cause(
        incident_id=incident_id,
        root_cause=request.root_cause,
        remediation_steps=request.remediation_steps,
        preventive_measures=request.preventive_measures,
        actor_id=current_user.id,
    )
    return {"status": "root_cause_documented"}
