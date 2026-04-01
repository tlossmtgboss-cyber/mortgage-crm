"""Drip sequence routes — enroll, pause, resume, switch, and manage lead nurture campaigns."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
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
async def enroll_lead(request: EnrollRequest, db=Depends(get_db)):
    """Enroll a lead in a drip sequence."""
    service = get_drip_enrollment_service()
    result = service.enroll_lead(
        db=db,
        lead_id=request.lead_id,
        sequence_name=request.sequence_name,
        org_id=request.organization_id,
    )
    return result


@router.post("/pause/{lead_id}")
async def pause_drip(lead_id: str, reason: str = ""):
    """Pause all active drip sequences for a lead."""
    service = get_drip_enrollment_service()
    result = service.pause_enrollment(lead_id, reason)
    return result


@router.post("/resume/{lead_id}")
async def resume_drip(lead_id: str):
    """Resume paused drip sequences for a lead."""
    service = get_drip_enrollment_service()
    result = service.resume_enrollment(lead_id)
    return result


@router.post("/switch")
async def switch_sequence(request: SwitchRequest, db=Depends(get_db)):
    """Stop current sequences and switch to a new one."""
    service = get_drip_enrollment_service()
    result = service.switch_sequence(
        db=db,
        lead_id=request.lead_id,
        new_sequence=request.new_sequence,
        org_id=request.organization_id,
        reason=request.reason,
    )
    return result


@router.post("/trigger")
async def process_trigger(request: TriggerEventRequest, db=Depends(get_db)):
    """Process a behavioral trigger event and execute resulting actions."""
    engine = get_drip_trigger_engine()
    actions = engine.evaluate_triggers(request.event_type, request.event_data)

    if not actions:
        return {"status": "no_triggers", "event_type": request.event_type}

    results = engine.execute_actions(
        db=db,
        lead_id=request.lead_id,
        actions=actions,
        org_id=request.organization_id,
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
async def get_enrollments(lead_id: str):
    """Get all drip enrollments for a lead."""
    service = get_drip_enrollment_service()
    enrollments = service.get_all_enrollments(lead_id)
    active = service.get_active_enrollments(lead_id)
    return {
        "lead_id": lead_id,
        "active_count": len(active),
        "total_count": len(enrollments),
        "enrollments": enrollments,
    }
