"""Drip sequence routes — enroll, pause, resume, switch, and manage lead nurture campaigns."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db import get_db
from auth.dependencies import get_current_user
from services.drip_enrollment_service import get_drip_enrollment_service
from services.drip_campaign_templates import list_templates, get_template
from services.drip_trigger_engine import get_drip_trigger_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/drip-sequences", tags=["drip-sequences"])


class EnrollRequest(BaseModel):
    lead_id: str
    sequence_name: str  # purchase_12_month, refinance_12_month, post_close, reengagement
    organization_id: str


class SwitchRequest(BaseModel):
    lead_id: str
    new_sequence: str
    organization_id: str
    reason: str = ""


class TriggerEventRequest(BaseModel):
    lead_id: str
    event_type: str  # email_opened, link_clicked, sms_replied, opted_out, etc.
    organization_id: str
    event_data: Optional[dict] = None


@router.post("/enroll")
async def enroll_lead(request: EnrollRequest, db=Depends(get_db),
                      current_user=Depends(get_current_user)):
    """Enroll a lead in a drip sequence."""
    # Enforce tenant isolation: use authenticated user's org
    org_id = str(current_user.organization_id)
    service = get_drip_enrollment_service()
    result = service.enroll_lead(
        db=db,
        lead_id=request.lead_id,
        sequence_name=request.sequence_name,
        org_id=org_id,
    )
    return result


@router.post("/pause/{lead_id}")
async def pause_drip(lead_id: str, reason: str = "", db=Depends(get_db),
                     current_user=Depends(get_current_user)):
    """Pause all active drip sequences for a lead."""
    org_id = str(current_user.organization_id)
    service = get_drip_enrollment_service()
    result = service.pause_enrollment(db=db, lead_id=lead_id, reason=reason,
                                      org_id=org_id)
    return result


@router.post("/resume/{lead_id}")
async def resume_drip(lead_id: str, db=Depends(get_db),
                      current_user=Depends(get_current_user)):
    """Resume paused drip sequences for a lead."""
    org_id = str(current_user.organization_id)
    service = get_drip_enrollment_service()
    result = service.resume_enrollment(db=db, lead_id=lead_id, org_id=org_id)
    return result


@router.post("/switch")
async def switch_sequence(request: SwitchRequest, db=Depends(get_db),
                          current_user=Depends(get_current_user)):
    """Stop current sequences and switch to a new one."""
    org_id = str(current_user.organization_id)
    service = get_drip_enrollment_service()
    result = service.switch_sequence(
        db=db,
        lead_id=request.lead_id,
        new_sequence=request.new_sequence,
        org_id=org_id,
        reason=request.reason,
    )
    return result


@router.post("/trigger")
async def process_trigger(request: TriggerEventRequest, db=Depends(get_db),
                          current_user=Depends(get_current_user)):
    """Process a behavioral trigger event and execute resulting actions."""
    org_id = str(current_user.organization_id)
    engine = get_drip_trigger_engine()
    actions = engine.evaluate_triggers(request.event_type, request.event_data)

    if not actions:
        return {"status": "no_triggers", "event_type": request.event_type}

    results = engine.execute_actions(
        db=db,
        lead_id=request.lead_id,
        actions=actions,
        org_id=org_id,
    )
    return {
        "status": "processed",
        "event_type": request.event_type,
        "actions_taken": len(results),
        "results": results,
    }


@router.get("/templates")
async def get_templates():
    """List all available drip campaign templates."""
    return {"templates": list_templates()}


@router.get("/templates/{template_name}")
async def get_template_detail(template_name: str):
    """Get full detail of a specific drip campaign template."""
    template = get_template(template_name)
    if not template:
        return {"error": f"Template '{template_name}' not found", "available": [t["key"] for t in list_templates()]}
    return template


@router.get("/enrollments/{lead_id}")
async def get_enrollments(
    lead_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all drip enrollments for a lead (paginated)."""
    org_id = str(current_user.organization_id)
    service = get_drip_enrollment_service()
    enrollments, total_count = service.get_all_enrollments(
        db=db, lead_id=lead_id, org_id=org_id,
        limit=limit, offset=offset,
    )
    active = service.get_active_enrollments(db=db, lead_id=lead_id, org_id=org_id)
    return {
        "lead_id": lead_id,
        "active_count": len(active),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "enrollments": enrollments,
    }


@router.post("/process-due-steps")
async def process_due_steps(db=Depends(get_db),
                            current_user=Depends(get_current_user)):
    """Process all enrollments with due steps. Called by scheduler/cron."""
    org_id = int(current_user.organization_id)
    service = get_drip_enrollment_service()
    results = service.process_due_steps(db=db, org_id=org_id)
    return {
        "status": "processed",
        "steps_processed": len(results),
        "results": results,
    }
