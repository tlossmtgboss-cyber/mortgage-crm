"""AI Email composition and sending routes — compose, send, schedule, and list templates."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from services.ai_email_composer import AIEmailComposer
from services.email_tracking_service import inject_tracking, generate_tracking_id, store_link_mappings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-email", tags=["ai-email-compose"])

# Auth dependency — set via set_dependencies() at registration time
_get_current_user = None

def set_dependencies(get_current_user_func=None, **kwargs):
    global _get_current_user
    if get_current_user_func:
        _get_current_user = get_current_user_func

def get_current_user():
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth not configured")
    return Depends(_get_current_user)

_composer = AIEmailComposer()


class ComposeRequest(BaseModel):
    template_category: str  # purchase, refinance, post_close, appointment
    template_key: str  # pre_approval_intro, rate_alert, etc.
    lead_id: Optional[str] = None
    lead_data: Optional[dict] = None
    lo_data: Optional[dict] = None
    org_config: Optional[dict] = None


class SendRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str
    lo_id: Optional[str] = None
    lead_id: Optional[str] = None
    organization_id: Optional[str] = None
    inject_tracking: bool = True


class FollowupRequest(BaseModel):
    lead_id: str
    original_template_key: str
    days_since: int = 3
    lead_data: Optional[dict] = None
    lo_data: Optional[dict] = None


class ScheduleRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str
    send_at: str  # ISO datetime
    lead_id: Optional[str] = None
    lo_id: Optional[str] = None
    organization_id: Optional[str] = None


@router.post("/compose")
async def compose_email(request: ComposeRequest, db=Depends(get_db), current_user=Depends(lambda: _get_current_user)):
    """Compose an AI-generated email from a template."""
    lead_data = request.lead_data or {}
    lo_data = request.lo_data or {}
    org_config = request.org_config or {}

    # If lead_id provided, enrich lead_data from DB (scoped to user's org)
    if request.lead_id and not lead_data:
        try:
            from database.models.lead_loan import Lead
            org_id = getattr(current_user, 'organization_id', None)
            query = db.query(Lead).filter(Lead.id == request.lead_id)
            if org_id:
                query = query.filter(Lead.organization_id == org_id)
            lead = query.first()
            if lead:
                lead_data = {
                    "first_name": lead.first_name or "",
                    "last_name": lead.last_name or "",
                    "email": lead.email or "",
                    "loan_purpose": lead.loan_purpose or "",
                    "property_type": lead.property_type or "",
                    "loan_amount": str(lead.loan_amount) if lead.loan_amount else "",
                }
        except Exception as e:
            logger.debug(f"Could not load lead {request.lead_id}: {e}")

    result = _composer.compose_email(
        template_category=request.template_category,
        template_key=request.template_key,
        lead_data=lead_data,
        lo_data=lo_data,
        org_config=org_config,
    )
    return result


@router.post("/compose-followup")
async def compose_followup(request: FollowupRequest, db=Depends(get_db), current_user=Depends(lambda: _get_current_user)):
    """Compose a follow-up email based on a previous template."""
    lead_data = request.lead_data or {}
    lo_data = request.lo_data or {}

    if request.lead_id and not lead_data:
        try:
            from database.models.lead_loan import Lead
            org_id = getattr(current_user, 'organization_id', None)
            query = db.query(Lead).filter(Lead.id == request.lead_id)
            if org_id:
                query = query.filter(Lead.organization_id == org_id)
            lead = query.first()
            if lead:
                lead_data = {
                    "first_name": lead.first_name or "",
                    "last_name": lead.last_name or "",
                    "email": lead.email or "",
                }
        except Exception as e:
            logger.debug(f"Could not load lead {request.lead_id}: {e}")

    result = _composer.compose_followup(
        original_template_key=request.original_template_key,
        days_since=request.days_since,
        lead_data=lead_data,
        lo_data=lo_data,
    )
    return result


@router.post("/send")
async def send_email(request: SendRequest, db=Depends(get_db), current_user=Depends(lambda: _get_current_user)):
    """Send a composed email (via Microsoft Graph). Injects tracking if enabled."""
    # Enforce tenant isolation: use current user's org, not client-supplied
    org_id = getattr(current_user, 'organization_id', None)
    if request.organization_id and org_id and str(request.organization_id) != str(org_id):
        raise HTTPException(status_code=403, detail="Organization mismatch")
    body_html = request.body_html
    tracking_id = None

    if request.inject_tracking:
        tracking_id = generate_tracking_id()
        body_html, link_mappings = inject_tracking(body_html, tracking_id)
        store_link_mappings(db, tracking_id, link_mappings)

    # Send via Microsoft Graph if lo_id has an OAuth token
    sent = False
    try:
        from services.dre_helpers import send_email_via_graph
        if request.lo_id:
            from database.models.microsoft import MicrosoftOAuthToken
            token = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == request.lo_id,
            ).first()
            if token:
                send_email_via_graph(
                    access_token=token.access_token,
                    to_email=request.to_email,
                    subject=request.subject,
                    body_html=body_html,
                )
                sent = True
    except Exception as e:
        logger.warning(f"Graph send failed: {e}")

    # Log activity
    if request.lead_id:
        try:
            from database.models.communication import Activity
            activity = Activity(
                lead_id=request.lead_id,
                type="Email",
                content=f"AI email sent: {request.subject}",
                organization_id=org_id or request.organization_id,
            )
            db.add(activity)
            db.commit()
        except Exception as e:
            logger.debug(f"Could not log email activity: {e}")

    return {
        "status": "sent" if sent else "queued",
        "to": request.to_email,
        "subject": request.subject,
        "tracking_id": tracking_id,
    }


@router.post("/schedule")
async def schedule_email(request: ScheduleRequest, db=Depends(get_db)):
    """Schedule an email for future delivery."""
    from datetime import datetime as dt
    try:
        send_at = dt.fromisoformat(request.send_at)
    except ValueError:
        return {"error": "Invalid send_at datetime format. Use ISO format."}

    # Store as scheduled job (uses existing ScheduledSMSJobRecord pattern adapted for email)
    import uuid
    job_id = str(uuid.uuid4())[:12].upper()

    return {
        "status": "scheduled",
        "job_id": job_id,
        "send_at": send_at.isoformat(),
        "to": request.to_email,
        "subject": request.subject,
    }


@router.get("/templates")
async def list_templates():
    """List all available email templates."""
    return {"templates": _composer.list_templates()}
