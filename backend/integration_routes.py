"""
Integration API Routes
Endpoints for SMS, Email, Teams, and Agentic AI
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from integrations.microsoft_graph import graph_client
from integrations.twilio_service import sms_client, SMSTemplates
from integrations.agentic_ai import agentic_ai, TriggerType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class SMSSendRequest(BaseModel):
    to_number: str
    message: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    template: Optional[str] = None

class EmailSendRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None

class TeamsMessageRequest(BaseModel):
    to_user_email: str
    message: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None

class AgenticTaskRequest(BaseModel):
    trigger: str
    context: Dict[str, Any]

class EmailWebhookPayload(BaseModel):
    from_email: str
    to_email: str
    subject: str
    body: str
    received_at: str
    message_id: Optional[str] = None

class SMSWebhookPayload(BaseModel):
    From: str
    To: str
    Body: str
    MessageSid: str


# ============================================================================
# SMS ENDPOINTS
# ============================================================================

@router.post("/sms/send")
async def send_sms(
    request: SMSSendRequest,
    db: Session = Depends(get_db),  # This needs to be imported from main
    current_user = Depends(get_current_user)  # This needs to be imported from main
):
    """Send SMS message to client"""

    if not sms_client.enabled:
        raise HTTPException(status_code=503, detail="SMS service not configured")

    try:
        # Send SMS
        message_sid = await sms_client.send_sms(
            to_number=request.to_number,
            message=request.message
        )

        if not message_sid:
            raise HTTPException(status_code=500, detail="Failed to send SMS")

        # Log SMS in database
        from main import SMSMessage  # Import model
        sms_record = SMSMessage(
            user_id=current_user.id,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            to_number=request.to_number,
            from_number=sms_client.from_number,
            message=request.message,
            direction="outbound",
            status="sent",
            twilio_sid=message_sid,
            template_used=request.template
        )
        db.add(sms_record)
        db.commit()

        logger.info(f"SMS sent to {request.to_number}")

        return {
            "status": "sent",
            "message_sid": message_sid,
            "to": request.to_number
        }

    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sms/history")
async def get_sms_history(
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get SMS message history"""

    from main import SMSMessage

    query = db.query(SMSMessage).filter(SMSMessage.user_id == current_user.id)

    if lead_id:
        query = query.filter(SMSMessage.lead_id == lead_id)
    if loan_id:
        query = query.filter(SMSMessage.loan_id == loan_id)

    messages = query.order_by(SMSMessage.created_at.desc()).limit(limit).all()

    return [{
        "id": msg.id,
        "to_number": msg.to_number,
        "from_number": msg.from_number,
        "message": msg.message,
        "direction": msg.direction,
        "status": msg.status,
        "created_at": msg.created_at.isoformat()
    } for msg in messages]


@router.post("/sms/webhook")
async def sms_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Webhook for incoming SMS messages from Twilio"""

    try:
        form_data = await request.form()
        from_number = form_data.get("From")
        to_number = form_data.get("To")
        body = form_data.get("Body")
        message_sid = form_data.get("MessageSid")

        logger.info(f"Received SMS from {from_number}: {body}")

        # Store incoming SMS
        from main import SMSMessage
        sms_record = SMSMessage(
            to_number=to_number,
            from_number=from_number,
            message=body,
            direction="inbound",
            status="received",
            twilio_sid=message_sid
        )
        db.add(sms_record)
        db.commit()

        # TODO: Use agentic AI to process and respond

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error processing SMS webhook: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# EMAIL ENDPOINTS
# ============================================================================

@router.post("/email/send")
async def send_email(
    request: EmailSendRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send email via Microsoft Outlook"""

    if not graph_client.enabled:
        raise HTTPException(status_code=503, detail="Email service not configured")

    try:
        success = await graph_client.send_email(
            to_email=request.to_email,
            subject=request.subject,
            body=request.body,
            from_email=current_user.email
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to send email")

        # Log email
        from main import EmailMessage
        email_record = EmailMessage(
            user_id=current_user.id,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            to_email=request.to_email,
            from_email=current_user.email,
            subject=request.subject,
            body=request.body,
            html_body=request.body,
            direction="outbound",
            status="sent"
        )
        db.add(email_record)
        db.commit()

        return {"status": "sent", "to": request.to_email}

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/email/inbox")
async def get_inbox(
    limit: int = 20,
    current_user = Depends(get_current_user)
):
    """Get inbox emails from Outlook"""

    if not graph_client.enabled:
        raise HTTPException(status_code=503, detail="Email service not configured")

    try:
        emails = await graph_client.get_emails(
            user_email=current_user.email,
            folder="inbox",
            limit=limit
        )

        return {"emails": emails, "count": len(emails)}

    except Exception as e:
        logger.error(f"Error getting inbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email/webhook")
async def email_webhook(
    payload: EmailWebhookPayload,
    db: Session = Depends(get_db)
):
    """Webhook for incoming emails"""

    try:
        logger.info(f"Received email from {payload.from_email}: {payload.subject}")

        # Store email
        from main import EmailMessage
        email_record = EmailMessage(
            from_email=payload.from_email,
            to_email=payload.to_email,
            subject=payload.subject,
            body=payload.body,
            direction="inbound",
            status="received",
            microsoft_message_id=payload.message_id,
            received_at=datetime.fromisoformat(payload.received_at)
        )
        db.add(email_record)
        db.commit()

        # Use agentic AI to process email
        context = {
            "trigger_type": TriggerType.EMAIL_RECEIVED,
            "email_from": payload.from_email,
            "email_subject": payload.subject,
            "email_body": payload.body
        }

        integrations = {
            "sms": sms_client,
            "email": graph_client,
            "teams": graph_client
        }

        result = await agentic_ai.analyze_and_execute(
            trigger=TriggerType.EMAIL_RECEIVED,
            context=context,
            db_session=db,
            integrations=integrations
        )

        return {"status": "processed", "actions_taken": result.get("actions_taken", 0)}

    except Exception as e:
        logger.error(f"Error processing email webhook: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# TEAMS ENDPOINTS
# ============================================================================

@router.post("/teams/send")
async def send_teams_message(
    request: TeamsMessageRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send Teams message"""

    if not graph_client.enabled:
        raise HTTPException(status_code=503, detail="Teams service not configured")

    try:
        success = await graph_client.send_teams_message(
            user_email=request.to_user_email,
            message=request.message
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to send Teams message")

        # Log Teams message
        from main import TeamsMessage
        teams_record = TeamsMessage(
            user_id=current_user.id,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            to_user=request.to_user_email,
            from_user=current_user.email,
            message=request.message,
            message_type="direct",
            status="sent"
        )
        db.add(teams_record)
        db.commit()

        return {"status": "sent", "to": request.to_user_email}

    except Exception as e:
        logger.error(f"Error sending Teams message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AGENTIC AI ENDPOINTS
# ============================================================================

@router.post("/agentic/execute")
async def execute_agentic_task(
    request: AgenticTaskRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Execute agentic AI task based on trigger"""

    try:
        trigger = TriggerType(request.trigger)

        integrations = {
            "sms": sms_client,
            "email": graph_client,
            "teams": graph_client
        }

        result = await agentic_ai.analyze_and_execute(
            trigger=trigger,
            context=request.context,
            db_session=db,
            integrations=integrations
        )

        return result

    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trigger type: {request.trigger}")
    except Exception as e:
        logger.error(f"Error executing agentic task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_integration_status():
    """Get status of all integrations"""

    return {
        "sms": {
            "enabled": sms_client.enabled,
            "provider": "Twilio"
        },
        "email": {
            "enabled": graph_client.enabled,
            "provider": "Microsoft Graph"
        },
        "teams": {
            "enabled": graph_client.enabled,
            "provider": "Microsoft Teams"
        },
        "calendar": {
            "enabled": graph_client.enabled,
            "provider": "Microsoft Outlook"
        },
        "ai": {
            "enabled": agentic_ai.enabled,
            "provider": "OpenAI"
        }
    }


# Placeholder imports - these need to be properly set up
def get_db():
    """Placeholder - should import from main"""
    pass

def get_current_user():
    """Placeholder - should import from main"""
    pass
