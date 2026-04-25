"""
Smart Docs Follow-Up & Appointment Scheduling Routes

Automated follow-up campaigns for outstanding document requests, borrower
appointment scheduling for document review/collection, and reusable
message templates.

Endpoints:
    - Campaigns: create, list, detail, pause, resume, cancel, events, response
    - Appointments: create, list, detail, confirm, cancel, reschedule, complete, no-show
    - Templates: list, create, update
    - Admin: process-pending, stats
"""

import logging
from datetime import datetime, date, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from database import get_db
from auth.dependencies import get_current_user
from database.models.document_followup import (
    FollowupCampaign,
    FollowupEvent,
    DocumentAppointment,
    FollowupTemplate,
    CampaignType,
    CampaignStatus,
    CampaignTriggerSource,
    FollowupEventType,
    DeliveryStatus,
    AppointmentType,
    AppointmentStatus,
    LocationType,
)

from routes.smart_docs_models import _verify_loan_tenant

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Follow-up"])


# =============================================================================
# Pydantic Models
# =============================================================================

class CreateCampaignBody(BaseModel):
    loan_id: int
    borrower_id: Optional[int] = None
    campaign_type: str  # INITIAL_REQUEST, GENTLE_REMINDER, URGENT_REMINDER, DOCUMENT_REJECTED, DOCUMENT_EXPIRED
    request_ids: List[int] = Field(default_factory=list)
    trigger_source: Optional[str] = None  # needs_list_generated, document_rejected, manual, etc.
    max_reminders: int = 5
    step_config: Optional[List[dict]] = None  # custom step config; generated if omitted


class PauseCampaignBody(BaseModel):
    reason: str


class CancelCampaignBody(BaseModel):
    reason: str


class RecordResponseBody(BaseModel):
    response_type: str  # uploaded, called_back, appointment_booked


class CreateAppointmentBody(BaseModel):
    loan_id: int
    borrower_id: Optional[int] = None
    appointment_type: str  # DOCUMENT_REVIEW, INCOME_VERIFICATION, NOTARY_SIGNING, DOCUMENT_COLLECTION, GENERAL_CONSULTATION
    title: str
    description: Optional[str] = None
    scheduled_time_start: datetime
    scheduled_time_end: Optional[datetime] = None
    duration_minutes: int = 30
    location_type: Optional[str] = None  # in_person, video_call, phone_call
    location_details: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    documents_to_discuss: Optional[List[int]] = None
    campaign_id: Optional[int] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None


class RescheduleAppointmentBody(BaseModel):
    new_start_time: datetime
    new_end_time: Optional[datetime] = None
    reason: Optional[str] = None


class CompleteAppointmentBody(BaseModel):
    outcome_notes: Optional[str] = None
    documents_collected: Optional[List[int]] = None


class CreateTemplateBody(BaseModel):
    name: str
    slug: str
    channel: str  # email, sms, call_script
    category: Optional[str] = None  # initial, reminder, urgent, escalation, appointment
    subject_template: Optional[str] = None
    body_template: str
    variables: Optional[List[str]] = None


class UpdateTemplateBody(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    category: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None


# =============================================================================
# Helpers
# =============================================================================

_CAMPAIGN_TYPE_MAP = {
    "INITIAL_REQUEST": CampaignType.INITIAL_REQUEST,
    "GENTLE_REMINDER": CampaignType.GENTLE_REMINDER,
    "URGENT_REMINDER": CampaignType.URGENT_REMINDER,
    # Allow the API-specified names as well as model enum names
    "DOCUMENT_REJECTED": CampaignType.ESCALATION,
    "DOCUMENT_EXPIRED": CampaignType.ESCALATION,
    "ESCALATION": CampaignType.ESCALATION,
    "APPOINTMENT_OFFER": CampaignType.APPOINTMENT_OFFER,
}

_TRIGGER_SOURCE_MAP = {
    "needs_list_generated": CampaignTriggerSource.NEEDS_LIST_GENERATED,
    "document_rejected": CampaignTriggerSource.DOCUMENT_REJECTED,
    "document_expired": CampaignTriggerSource.DOCUMENT_EXPIRED,
    "ai_recommendation": CampaignTriggerSource.AI_RECOMMENDATION,
    "manual": CampaignTriggerSource.MANUAL,
    "sla_breach": CampaignTriggerSource.SLA_BREACH,
}

_APPOINTMENT_TYPE_MAP = {
    "DOCUMENT_REVIEW": AppointmentType.DOCUMENT_REVIEW,
    "INCOME_VERIFICATION": AppointmentType.INCOME_VERIFICATION,
    "NOTARY_SIGNING": AppointmentType.NOTARY_SIGNING,
    "DOCUMENT_COLLECTION": AppointmentType.DOCUMENT_COLLECTION,
    "GENERAL_CONSULTATION": AppointmentType.GENERAL_CONSULTATION,
}

_LOCATION_TYPE_MAP = {
    "in_person": LocationType.IN_PERSON,
    "video_call": LocationType.VIDEO_CALL,
    "phone_call": LocationType.PHONE_CALL,
}


def _default_step_config(campaign_type: str) -> List[dict]:
    """Generate default step config based on campaign type."""
    configs = {
        "INITIAL_REQUEST": [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder_sms"},
            {"step": 3, "channel": "email", "delay_hours": 96, "template": "second_reminder"},
        ],
        "GENTLE_REMINDER": [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "gentle_reminder"},
            {"step": 2, "channel": "sms", "delay_hours": 72, "template": "gentle_reminder_sms"},
        ],
        "URGENT_REMINDER": [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "urgent_reminder"},
            {"step": 2, "channel": "sms", "delay_hours": 24, "template": "urgent_sms"},
            {"step": 3, "channel": "call", "delay_hours": 48, "template": "urgent_call_script"},
        ],
        "DOCUMENT_REJECTED": [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "document_rejected"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "resubmit_reminder_sms"},
        ],
        "DOCUMENT_EXPIRED": [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "document_expired"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "expired_reminder_sms"},
            {"step": 3, "channel": "email", "delay_hours": 120, "template": "urgent_expiration"},
        ],
    }
    return configs.get(campaign_type, configs["INITIAL_REQUEST"])


def _campaign_to_dict(c: FollowupCampaign) -> dict:
    """Serialize a campaign to a dict."""
    return {
        "id": c.id,
        "organization_id": c.organization_id,
        "loan_id": c.loan_id,
        "borrower_id": c.borrower_id,
        "campaign_type": c.campaign_type.value if c.campaign_type else None,
        "status": c.status.value if c.status else None,
        "trigger_source": c.trigger_source.value if c.trigger_source else None,
        "linked_request_ids": c.linked_request_ids or [],
        "total_steps": c.total_steps,
        "current_step": c.current_step,
        "step_config": c.step_config or [],
        "next_action_at": c.next_action_at.isoformat() if c.next_action_at else None,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "cancelled_at": c.cancelled_at.isoformat() if c.cancelled_at else None,
        "cancel_reason": c.cancel_reason,
        "max_reminders": c.max_reminders,
        "reminders_sent": c.reminders_sent,
        "borrower_responded": c.borrower_responded,
        "response_date": c.response_date.isoformat() if c.response_date else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _event_to_dict(e: FollowupEvent) -> dict:
    """Serialize a follow-up event to a dict."""
    return {
        "id": e.id,
        "campaign_id": e.campaign_id,
        "event_type": e.event_type.value if e.event_type else None,
        "step_number": e.step_number,
        "channel": e.channel,
        "template_used": e.template_used,
        "recipient_email": e.recipient_email,
        "recipient_phone": e.recipient_phone,
        "message_subject": e.message_subject,
        "message_preview": e.message_preview,
        "delivery_status": e.delivery_status.value if e.delivery_status else None,
        "delivery_error": e.delivery_error,
        "opened_at": e.opened_at.isoformat() if e.opened_at else None,
        "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
        "metadata": e.extra_metadata,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _appointment_to_dict(a: DocumentAppointment) -> dict:
    """Serialize an appointment to a dict."""
    return {
        "id": a.id,
        "organization_id": a.organization_id,
        "loan_id": a.loan_id,
        "borrower_id": a.borrower_id,
        "campaign_id": a.campaign_id,
        "appointment_type": a.appointment_type.value if a.appointment_type else None,
        "title": a.title,
        "description": a.description,
        "status": a.status.value if a.status else None,
        "scheduled_date": a.scheduled_date.isoformat() if a.scheduled_date else None,
        "scheduled_time_start": a.scheduled_time_start.isoformat() if a.scheduled_time_start else None,
        "scheduled_time_end": a.scheduled_time_end.isoformat() if a.scheduled_time_end else None,
        "duration_minutes": a.duration_minutes,
        "location_type": a.location_type.value if a.location_type else None,
        "location_details": a.location_details,
        "meeting_link": a.meeting_link,
        "assigned_to_user_id": a.assigned_to_user_id,
        "attendee_name": a.attendee_name,
        "attendee_email": a.attendee_email,
        "attendee_phone": a.attendee_phone,
        "documents_to_discuss": a.documents_to_discuss,
        "outcome_notes": a.outcome_notes,
        "documents_collected": a.documents_collected,
        "reminder_sent": a.reminder_sent,
        "reminder_sent_at": a.reminder_sent_at.isoformat() if a.reminder_sent_at else None,
        "confirmed_at": a.confirmed_at.isoformat() if a.confirmed_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "cancelled_at": a.cancelled_at.isoformat() if a.cancelled_at else None,
        "cancellation_reason": a.cancellation_reason,
        "rescheduled_from_id": a.rescheduled_from_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _template_to_dict(t: FollowupTemplate) -> dict:
    """Serialize a template to a dict."""
    return {
        "id": t.id,
        "organization_id": t.organization_id,
        "name": t.name,
        "slug": t.slug,
        "channel": t.channel,
        "category": t.category,
        "subject_template": t.subject_template,
        "body_template": t.body_template,
        "variables": t.variables or [],
        "is_default": t.is_default,
        "is_active": t.is_active,
        "usage_count": t.usage_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _get_user_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the current user."""
    return getattr(current_user, "organization_id", None)


def _verify_campaign_tenant(
    db: Session, campaign_id: int, current_user
) -> FollowupCampaign:
    """Load a campaign and verify tenant isolation. Returns the campaign or raises 404."""
    campaign = db.query(FollowupCampaign).filter(
        FollowupCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _verify_loan_tenant(db, campaign.loan_id, current_user)
    return campaign


def _verify_appointment_tenant(
    db: Session, appointment_id: int, current_user
) -> DocumentAppointment:
    """Load an appointment and verify tenant isolation. Returns the appointment or raises 404."""
    appointment = db.query(DocumentAppointment).filter(
        DocumentAppointment.id == appointment_id
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _verify_loan_tenant(db, appointment.loan_id, current_user)
    return appointment


# =============================================================================
# Campaign Endpoints
# =============================================================================

@router.post("/followup/campaigns")
async def create_campaign(
    body: CreateCampaignBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a follow-up campaign for outstanding document requests."""
    _verify_loan_tenant(db, body.loan_id, current_user)

    # Resolve campaign type
    campaign_type = _CAMPAIGN_TYPE_MAP.get(body.campaign_type)
    if not campaign_type:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid campaign_type '{body.campaign_type}'. "
                   f"Valid values: {list(_CAMPAIGN_TYPE_MAP.keys())}",
        )

    # Resolve trigger source
    trigger_source = None
    if body.trigger_source:
        trigger_source = _TRIGGER_SOURCE_MAP.get(body.trigger_source)

    # Build step config
    step_config = body.step_config or _default_step_config(body.campaign_type)
    now = datetime.now(timezone.utc)

    campaign = FollowupCampaign(
        organization_id=_get_user_org_id(current_user),
        loan_id=body.loan_id,
        borrower_id=body.borrower_id,
        campaign_type=campaign_type,
        status=CampaignStatus.ACTIVE,
        trigger_source=trigger_source,
        linked_request_ids=body.request_ids,
        total_steps=len(step_config),
        current_step=0,
        step_config=step_config,
        max_reminders=body.max_reminders,
        started_at=now,
        created_by_user_id=getattr(current_user, "id", None),
    )

    # Calculate next_action_at from first step
    if step_config:
        from datetime import timedelta
        delay_hours = step_config[0].get("delay_hours", 0)
        campaign.next_action_at = now + timedelta(hours=delay_hours)

    try:
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create follow-up campaign: {e}")
        raise HTTPException(status_code=500, detail="Failed to create campaign")

    logger.info(
        f"Created follow-up campaign {campaign.id} for loan {body.loan_id}, "
        f"type={body.campaign_type}"
    )
    return _campaign_to_dict(campaign)


@router.get("/followup/campaigns")
async def list_campaigns(
    loan_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List follow-up campaigns for the current user's organization."""
    org_id = _get_user_org_id(current_user)
    query = db.query(FollowupCampaign)

    if org_id:
        query = query.filter(FollowupCampaign.organization_id == org_id)

    if loan_id is not None:
        query = query.filter(FollowupCampaign.loan_id == loan_id)

    if status:
        try:
            status_enum = CampaignStatus(status)
            query = query.filter(FollowupCampaign.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. "
                       f"Valid values: {[s.value for s in CampaignStatus]}",
            )

    campaigns = query.order_by(FollowupCampaign.created_at.desc()).all()
    return {
        "campaigns": [_campaign_to_dict(c) for c in campaigns],
        "total": len(campaigns),
    }


@router.get("/followup/campaigns/{campaign_id}")
async def get_campaign_detail(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full detail for a follow-up campaign including events and timeline."""
    campaign = _verify_campaign_tenant(db, campaign_id, current_user)

    events = (
        db.query(FollowupEvent)
        .filter(FollowupEvent.campaign_id == campaign_id)
        .order_by(FollowupEvent.created_at.asc())
        .all()
    )

    data = _campaign_to_dict(campaign)
    data["events"] = [_event_to_dict(e) for e in events]
    data["event_count"] = len(events)
    return data


@router.post("/followup/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    body: PauseCampaignBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Pause an active follow-up campaign."""
    campaign = _verify_campaign_tenant(db, campaign_id, current_user)

    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause campaign in '{campaign.status.value}' status. "
                   "Only active campaigns can be paused.",
        )

    campaign.status = CampaignStatus.PAUSED
    campaign.cancel_reason = f"Paused: {body.reason}"
    campaign.updated_at = datetime.now(timezone.utc)

    # Log event
    event = FollowupEvent(
        campaign_id=campaign_id,
        event_type=FollowupEventType.ESCALATED_TO_LO,
        channel="system",
        message_preview=f"Campaign paused: {body.reason}",
        extra_metadata={"action": "pause", "reason": body.reason},
    )
    db.add(event)

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to pause campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause campaign")

    return {"campaign_id": campaign_id, "status": "paused", "message": "Campaign paused"}


@router.post("/followup/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resume a paused follow-up campaign."""
    campaign = _verify_campaign_tenant(db, campaign_id, current_user)

    if campaign.status != CampaignStatus.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume campaign in '{campaign.status.value}' status. "
                   "Only paused campaigns can be resumed.",
        )

    campaign.status = CampaignStatus.ACTIVE
    campaign.updated_at = datetime.now(timezone.utc)

    # Recalculate next_action_at based on current step
    from datetime import timedelta
    step_config = campaign.step_config or []
    current_step = campaign.current_step or 0
    if current_step < len(step_config):
        delay_hours = step_config[current_step].get("delay_hours", 0)
        campaign.next_action_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

    # Log event
    event = FollowupEvent(
        campaign_id=campaign_id,
        event_type=FollowupEventType.ESCALATED_TO_LO,
        channel="system",
        message_preview="Campaign resumed",
        extra_metadata={"action": "resume"},
    )
    db.add(event)

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to resume campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume campaign")

    return {"campaign_id": campaign_id, "status": "active", "message": "Campaign resumed"}


@router.post("/followup/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: int,
    body: CancelCampaignBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancel a follow-up campaign."""
    campaign = _verify_campaign_tenant(db, campaign_id, current_user)

    if campaign.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is already '{campaign.status.value}'.",
        )

    now = datetime.now(timezone.utc)
    campaign.status = CampaignStatus.CANCELLED
    campaign.cancelled_at = now
    campaign.cancel_reason = body.reason
    campaign.next_action_at = None
    campaign.updated_at = now

    # Log event
    event = FollowupEvent(
        campaign_id=campaign_id,
        event_type=FollowupEventType.ESCALATED_TO_LO,
        channel="system",
        message_preview=f"Campaign cancelled: {body.reason}",
        extra_metadata={"action": "cancel", "reason": body.reason},
    )
    db.add(event)

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to cancel campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel campaign")

    return {"campaign_id": campaign_id, "status": "cancelled", "message": "Campaign cancelled"}


@router.get("/followup/campaigns/{campaign_id}/events")
async def get_campaign_events(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all events for a follow-up campaign in chronological order."""
    _verify_campaign_tenant(db, campaign_id, current_user)

    events = (
        db.query(FollowupEvent)
        .filter(FollowupEvent.campaign_id == campaign_id)
        .order_by(FollowupEvent.created_at.asc())
        .all()
    )

    return {
        "campaign_id": campaign_id,
        "events": [_event_to_dict(e) for e in events],
        "total": len(events),
    }


@router.post("/followup/campaigns/{campaign_id}/response")
async def record_borrower_response(
    campaign_id: int,
    body: RecordResponseBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record a borrower response to a follow-up campaign."""
    campaign = _verify_campaign_tenant(db, campaign_id, current_user)

    valid_responses = ("uploaded", "called_back", "appointment_booked")
    if body.response_type not in valid_responses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid response_type '{body.response_type}'. "
                   f"Valid values: {list(valid_responses)}",
        )

    now = datetime.now(timezone.utc)
    campaign.borrower_responded = True
    campaign.response_date = now
    campaign.updated_at = now

    # Mark campaign completed if document uploaded
    if body.response_type == "uploaded":
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = now
        campaign.next_action_at = None

    # Map response type to event type
    event_type_map = {
        "uploaded": FollowupEventType.DOCUMENT_UPLOADED,
        "called_back": FollowupEventType.BORROWER_RESPONDED,
        "appointment_booked": FollowupEventType.APPOINTMENT_BOOKED,
    }

    event = FollowupEvent(
        campaign_id=campaign_id,
        event_type=event_type_map[body.response_type],
        channel="borrower",
        message_preview=f"Borrower responded: {body.response_type}",
        extra_metadata={"response_type": body.response_type},
    )
    db.add(event)

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to record response for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to record response")

    return {
        "campaign_id": campaign_id,
        "response_type": body.response_type,
        "campaign_status": campaign.status.value,
        "message": "Borrower response recorded",
    }


# =============================================================================
# Appointment Endpoints
# =============================================================================

@router.post("/followup/appointments")
async def create_appointment(
    body: CreateAppointmentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a document-related appointment."""
    _verify_loan_tenant(db, body.loan_id, current_user)

    # Resolve appointment type
    appt_type = _APPOINTMENT_TYPE_MAP.get(body.appointment_type)
    if not appt_type:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid appointment_type '{body.appointment_type}'. "
                   f"Valid values: {list(_APPOINTMENT_TYPE_MAP.keys())}",
        )

    # Resolve location type
    loc_type = None
    if body.location_type:
        loc_type = _LOCATION_TYPE_MAP.get(body.location_type)
        if not loc_type:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid location_type '{body.location_type}'. "
                       f"Valid values: {list(_LOCATION_TYPE_MAP.keys())}",
            )

    # Derive scheduled_date from start time
    scheduled_date = body.scheduled_time_start.date()

    appointment = DocumentAppointment(
        organization_id=_get_user_org_id(current_user),
        loan_id=body.loan_id,
        borrower_id=body.borrower_id,
        campaign_id=body.campaign_id,
        appointment_type=appt_type,
        title=body.title,
        description=body.description,
        status=AppointmentStatus.SCHEDULED,
        scheduled_date=scheduled_date,
        scheduled_time_start=body.scheduled_time_start,
        scheduled_time_end=body.scheduled_time_end,
        duration_minutes=body.duration_minutes,
        location_type=loc_type,
        location_details=body.location_details,
        assigned_to_user_id=body.assigned_to_user_id,
        attendee_name=body.attendee_name,
        attendee_email=body.attendee_email,
        attendee_phone=body.attendee_phone,
        documents_to_discuss=body.documents_to_discuss,
    )

    try:
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create appointment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create appointment")

    logger.info(
        f"Created appointment {appointment.id} for loan {body.loan_id}, "
        f"type={body.appointment_type}"
    )
    return _appointment_to_dict(appointment)


@router.get("/followup/appointments")
async def list_appointments(
    loan_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List appointments for the current user's organization."""
    org_id = _get_user_org_id(current_user)
    query = db.query(DocumentAppointment)

    if org_id:
        query = query.filter(DocumentAppointment.organization_id == org_id)

    if loan_id is not None:
        query = query.filter(DocumentAppointment.loan_id == loan_id)

    if status:
        try:
            status_enum = AppointmentStatus(status)
            query = query.filter(DocumentAppointment.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. "
                       f"Valid values: {[s.value for s in AppointmentStatus]}",
            )

    if date_from:
        query = query.filter(DocumentAppointment.scheduled_date >= date_from)
    if date_to:
        query = query.filter(DocumentAppointment.scheduled_date <= date_to)

    appointments = query.order_by(DocumentAppointment.scheduled_time_start.asc()).all()
    return {
        "appointments": [_appointment_to_dict(a) for a in appointments],
        "total": len(appointments),
    }


@router.get("/followup/appointments/{appointment_id}")
async def get_appointment_detail(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full detail for an appointment."""
    appointment = _verify_appointment_tenant(db, appointment_id, current_user)
    return _appointment_to_dict(appointment)


@router.post("/followup/appointments/{appointment_id}/confirm")
async def confirm_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Confirm an appointment and send confirmation to the borrower."""
    appointment = _verify_appointment_tenant(db, appointment_id, current_user)

    if appointment.status not in (AppointmentStatus.SCHEDULED,):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm appointment in '{appointment.status.value}' status.",
        )

    now = datetime.now(timezone.utc)
    appointment.status = AppointmentStatus.CONFIRMED
    appointment.confirmed_at = now
    appointment.updated_at = now

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to confirm appointment {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm appointment")

    logger.info(f"Appointment {appointment_id} confirmed")
    return {
        "appointment_id": appointment_id,
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
        "message": "Appointment confirmed",
    }


@router.post("/followup/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    body: CancelCampaignBody,  # reuse: has a reason field
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancel an appointment."""
    appointment = _verify_appointment_tenant(db, appointment_id, current_user)

    terminal = (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW)
    if appointment.status in terminal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel appointment in '{appointment.status.value}' status.",
        )

    now = datetime.now(timezone.utc)
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now
    appointment.cancellation_reason = body.reason
    appointment.updated_at = now

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to cancel appointment {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel appointment")

    logger.info(f"Appointment {appointment_id} cancelled: {body.reason}")
    return {
        "appointment_id": appointment_id,
        "status": "cancelled",
        "message": "Appointment cancelled",
    }


@router.post("/followup/appointments/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: int,
    body: RescheduleAppointmentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Reschedule an appointment. Creates a new appointment linked to the original."""
    old_appointment = _verify_appointment_tenant(db, appointment_id, current_user)

    terminal = (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW)
    if old_appointment.status in terminal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reschedule appointment in '{old_appointment.status.value}' status.",
        )

    now = datetime.now(timezone.utc)

    # Mark old appointment as rescheduled
    old_appointment.status = AppointmentStatus.RESCHEDULED
    old_appointment.cancellation_reason = body.reason or "Rescheduled"
    old_appointment.cancelled_at = now
    old_appointment.updated_at = now

    # Create new appointment linked to old
    new_appointment = DocumentAppointment(
        organization_id=old_appointment.organization_id,
        loan_id=old_appointment.loan_id,
        borrower_id=old_appointment.borrower_id,
        campaign_id=old_appointment.campaign_id,
        appointment_type=old_appointment.appointment_type,
        title=old_appointment.title,
        description=old_appointment.description,
        status=AppointmentStatus.SCHEDULED,
        scheduled_date=body.new_start_time.date(),
        scheduled_time_start=body.new_start_time,
        scheduled_time_end=body.new_end_time,
        duration_minutes=old_appointment.duration_minutes,
        location_type=old_appointment.location_type,
        location_details=old_appointment.location_details,
        meeting_link=old_appointment.meeting_link,
        assigned_to_user_id=old_appointment.assigned_to_user_id,
        attendee_name=old_appointment.attendee_name,
        attendee_email=old_appointment.attendee_email,
        attendee_phone=old_appointment.attendee_phone,
        documents_to_discuss=old_appointment.documents_to_discuss,
        rescheduled_from_id=old_appointment.id,
    )

    try:
        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to reschedule appointment {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reschedule appointment")

    logger.info(
        f"Appointment {appointment_id} rescheduled -> new appointment {new_appointment.id}"
    )
    return {
        "old_appointment_id": appointment_id,
        "new_appointment": _appointment_to_dict(new_appointment),
        "message": "Appointment rescheduled",
    }


@router.post("/followup/appointments/{appointment_id}/complete")
async def complete_appointment(
    appointment_id: int,
    body: CompleteAppointmentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark an appointment as completed with outcome notes."""
    appointment = _verify_appointment_tenant(db, appointment_id, current_user)

    terminal = (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW, AppointmentStatus.RESCHEDULED)
    if appointment.status in terminal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete appointment in '{appointment.status.value}' status.",
        )

    now = datetime.now(timezone.utc)
    appointment.status = AppointmentStatus.COMPLETED
    appointment.completed_at = now
    appointment.outcome_notes = body.outcome_notes
    appointment.documents_collected = body.documents_collected
    appointment.updated_at = now

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to complete appointment {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete appointment")

    logger.info(f"Appointment {appointment_id} completed")
    return {
        "appointment_id": appointment_id,
        "status": "completed",
        "message": "Appointment completed",
    }


@router.post("/followup/appointments/{appointment_id}/no-show")
async def mark_no_show(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark an appointment as no-show."""
    appointment = _verify_appointment_tenant(db, appointment_id, current_user)

    terminal = (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED)
    if appointment.status in terminal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark no-show for appointment in '{appointment.status.value}' status.",
        )

    now = datetime.now(timezone.utc)
    appointment.status = AppointmentStatus.NO_SHOW
    appointment.updated_at = now

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to mark appointment {appointment_id} as no-show: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark no-show")

    logger.info(f"Appointment {appointment_id} marked as no-show")
    return {
        "appointment_id": appointment_id,
        "status": "no_show",
        "message": "Appointment marked as no-show",
    }


# =============================================================================
# Template Endpoints
# =============================================================================

@router.get("/followup/templates")
async def list_templates(
    channel: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List follow-up templates available to the current organization."""
    org_id = _get_user_org_id(current_user)
    query = db.query(FollowupTemplate).filter(FollowupTemplate.is_active == True)

    # Show org-specific templates plus platform defaults
    if org_id:
        query = query.filter(
            (FollowupTemplate.organization_id == org_id)
            | (FollowupTemplate.is_default == True)
        )
    else:
        query = query.filter(FollowupTemplate.is_default == True)

    if channel:
        query = query.filter(FollowupTemplate.channel == channel)
    if category:
        query = query.filter(FollowupTemplate.category == category)

    templates = query.order_by(FollowupTemplate.category, FollowupTemplate.name).all()
    return {
        "templates": [_template_to_dict(t) for t in templates],
        "total": len(templates),
    }


@router.post("/followup/templates")
async def create_template(
    body: CreateTemplateBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new follow-up template for the current organization."""
    org_id = _get_user_org_id(current_user)

    # Check for duplicate slug within organization
    existing = db.query(FollowupTemplate).filter(
        FollowupTemplate.organization_id == org_id,
        FollowupTemplate.slug == body.slug,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Template with slug '{body.slug}' already exists for this organization.",
        )

    valid_channels = ("email", "sms", "call_script")
    if body.channel not in valid_channels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel '{body.channel}'. Valid values: {list(valid_channels)}",
        )

    template = FollowupTemplate(
        organization_id=org_id,
        name=body.name,
        slug=body.slug,
        channel=body.channel,
        category=body.category,
        subject_template=body.subject_template,
        body_template=body.body_template,
        variables=body.variables or [],
        is_default=False,
        is_active=True,
    )

    try:
        db.add(template)
        db.commit()
        db.refresh(template)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(status_code=500, detail="Failed to create template")

    return _template_to_dict(template)


@router.put("/followup/templates/{template_id}")
async def update_template(
    template_id: int,
    body: UpdateTemplateBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing follow-up template."""
    org_id = _get_user_org_id(current_user)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"

    template = db.query(FollowupTemplate).filter(
        FollowupTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Tenant isolation: only allow editing own org templates or platform defaults if admin
    if not is_platform_admin:
        if template.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Template not found")
        if template.is_default:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify platform default templates. Create an org-specific override instead.",
            )

    if body.name is not None:
        template.name = body.name
    if body.channel is not None:
        valid_channels = ("email", "sms", "call_script")
        if body.channel not in valid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid channel '{body.channel}'. Valid values: {list(valid_channels)}",
            )
        template.channel = body.channel
    if body.category is not None:
        template.category = body.category
    if body.subject_template is not None:
        template.subject_template = body.subject_template
    if body.body_template is not None:
        template.body_template = body.body_template
    if body.variables is not None:
        template.variables = body.variables
    if body.is_active is not None:
        template.is_active = body.is_active

    template.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(template)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update template {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update template")

    return _template_to_dict(template)


# =============================================================================
# Admin / Cron Endpoints
# =============================================================================

@router.post("/followup/process-pending")
async def process_pending_followups(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Process all pending follow-up campaign steps that are due.

    This endpoint is designed to be called by a cron job or admin action.
    It finds active campaigns whose next_action_at has passed and advances
    them to the next step.
    """
    now = datetime.now(timezone.utc)

    # Find campaigns that are due for their next action
    due_campaigns = (
        db.query(FollowupCampaign)
        .filter(
            FollowupCampaign.status == CampaignStatus.ACTIVE,
            FollowupCampaign.next_action_at <= now,
        )
        .all()
    )

    processed = []
    completed = []
    errors = []

    for campaign in due_campaigns:
        try:
            step_config = campaign.step_config or []
            current_step = campaign.current_step or 0

            if current_step >= len(step_config):
                # All steps exhausted
                campaign.status = CampaignStatus.COMPLETED
                campaign.completed_at = now
                campaign.next_action_at = None
                completed.append(campaign.id)
                continue

            step = step_config[current_step]

            # Create the follow-up event for this step
            event = FollowupEvent(
                campaign_id=campaign.id,
                event_type=FollowupEventType.EMAIL_SENT
                if step.get("channel") == "email"
                else FollowupEventType.SMS_SENT
                if step.get("channel") == "sms"
                else FollowupEventType.CALL_SCHEDULED,
                step_number=step.get("step", current_step + 1),
                channel=step.get("channel", "email"),
                template_used=step.get("template"),
                delivery_status=DeliveryStatus.QUEUED,
            )
            db.add(event)

            # Advance campaign
            campaign.current_step = current_step + 1
            campaign.reminders_sent = (campaign.reminders_sent or 0) + 1
            campaign.updated_at = now

            # Schedule next step or complete
            next_step_idx = current_step + 1
            if next_step_idx < len(step_config):
                from datetime import timedelta
                delay_hours = step_config[next_step_idx].get("delay_hours", 48)
                campaign.next_action_at = now + timedelta(hours=delay_hours)
            else:
                # Check if max_reminders reached
                if (campaign.reminders_sent or 0) >= (campaign.max_reminders or 5):
                    campaign.status = CampaignStatus.COMPLETED
                    campaign.completed_at = now
                    campaign.next_action_at = None
                    completed.append(campaign.id)
                else:
                    campaign.next_action_at = None  # No more steps configured

            processed.append(campaign.id)

        except Exception as e:
            logger.error(f"Error processing campaign {campaign.id}: {e}")
            errors.append({"campaign_id": campaign.id, "error": str(e)})

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to commit pending follow-up processing: {e}")
        raise HTTPException(status_code=500, detail="Failed to process pending follow-ups")

    return {
        "processed_count": len(processed),
        "completed_count": len(completed),
        "error_count": len(errors),
        "processed_campaign_ids": processed,
        "completed_campaign_ids": completed,
        "errors": errors,
        "message": f"Processed {len(processed)} campaigns, {len(completed)} completed",
    }


@router.get("/followup/stats")
async def get_followup_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get follow-up and appointment statistics for the current organization."""
    org_id = _get_user_org_id(current_user)

    # --- Campaign stats ---
    campaign_query = db.query(FollowupCampaign)
    if org_id:
        campaign_query = campaign_query.filter(FollowupCampaign.organization_id == org_id)

    total_campaigns = campaign_query.count()
    active_campaigns = campaign_query.filter(
        FollowupCampaign.status == CampaignStatus.ACTIVE
    ).count()
    completed_campaigns = campaign_query.filter(
        FollowupCampaign.status == CampaignStatus.COMPLETED
    ).count()
    responded_campaigns = campaign_query.filter(
        FollowupCampaign.borrower_responded == True
    ).count()

    response_rate = (
        round((responded_campaigns / total_campaigns) * 100, 1)
        if total_campaigns > 0
        else 0.0
    )

    # --- Appointment stats ---
    appt_query = db.query(DocumentAppointment)
    if org_id:
        appt_query = appt_query.filter(DocumentAppointment.organization_id == org_id)

    total_appointments = appt_query.count()
    scheduled_appointments = appt_query.filter(
        DocumentAppointment.status.in_([
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        ])
    ).count()
    completed_appointments = appt_query.filter(
        DocumentAppointment.status == AppointmentStatus.COMPLETED
    ).count()
    no_show_appointments = appt_query.filter(
        DocumentAppointment.status == AppointmentStatus.NO_SHOW
    ).count()

    no_show_rate = (
        round((no_show_appointments / total_appointments) * 100, 1)
        if total_appointments > 0
        else 0.0
    )

    # --- Channel stats (from events) ---
    event_base = db.query(FollowupEvent)
    if org_id:
        # Join through campaign for org filtering
        event_base = event_base.join(
            FollowupCampaign,
            FollowupEvent.campaign_id == FollowupCampaign.id,
        ).filter(FollowupCampaign.organization_id == org_id)

    total_emails = event_base.filter(
        FollowupEvent.event_type == FollowupEventType.EMAIL_SENT
    ).count()
    emails_opened = event_base.filter(
        FollowupEvent.event_type == FollowupEventType.EMAIL_SENT,
        FollowupEvent.opened_at.isnot(None),
    ).count()
    email_open_rate = (
        round((emails_opened / total_emails) * 100, 1)
        if total_emails > 0
        else 0.0
    )

    total_sms = event_base.filter(
        FollowupEvent.event_type == FollowupEventType.SMS_SENT
    ).count()
    sms_responded = event_base.filter(
        FollowupEvent.event_type == FollowupEventType.SMS_SENT,
        FollowupEvent.delivery_status == DeliveryStatus.CLICKED,
    ).count()
    sms_response_rate = (
        round((sms_responded / total_sms) * 100, 1)
        if total_sms > 0
        else 0.0
    )

    # --- Average time to document collection ---
    avg_collection_row = (
        db.query(
            func.avg(
                func.extract(
                    "epoch",
                    FollowupCampaign.completed_at - FollowupCampaign.started_at,
                )
            ).label("avg_seconds")
        )
        .filter(
            FollowupCampaign.status == CampaignStatus.COMPLETED,
            FollowupCampaign.completed_at.isnot(None),
            FollowupCampaign.started_at.isnot(None),
        )
    )
    if org_id:
        avg_collection_row = avg_collection_row.filter(
            FollowupCampaign.organization_id == org_id
        )
    avg_result = avg_collection_row.first()
    avg_seconds = avg_result[0] if avg_result and avg_result[0] else None
    avg_hours = round(avg_seconds / 3600, 1) if avg_seconds else None

    return {
        "campaigns": {
            "total": total_campaigns,
            "active": active_campaigns,
            "completed": completed_campaigns,
            "responded": responded_campaigns,
            "response_rate": response_rate,
        },
        "appointments": {
            "total": total_appointments,
            "scheduled": scheduled_appointments,
            "completed": completed_appointments,
            "no_show": no_show_appointments,
            "no_show_rate": no_show_rate,
        },
        "channels": {
            "email": {
                "total_sent": total_emails,
                "opened": emails_opened,
                "open_rate": email_open_rate,
            },
            "sms": {
                "total_sent": total_sms,
                "responded": sms_responded,
                "response_rate": sms_response_rate,
            },
        },
        "avg_time_to_collection_hours": avg_hours,
    }
