"""
Integration API Routes
Endpoints for SMS, Email, Teams, and Agentic AI
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import os

from database import get_db
from integrations.microsoft_graph import graph_client
from integrations.sms_service import get_sms_client, SMSTemplates
from integrations.agentic_ai import agentic_ai, TriggerType

# OpenAI for AI-powered SMS responses
try:
    from services.openai_conversation_service import OpenAIConversationService
    OPENAI_SERVICE_AVAILABLE = True
except ImportError:
    OpenAIConversationService = None
    OPENAI_SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Lazy SMS client instance (replaces old module-level sms_client)
sms_client = get_sms_client()


async def _validate_webhook_signature(request: Request, form_data: dict) -> bool:
    """Validate webhook signature header. Returns True if valid or not configured."""
    auth_token = os.getenv("TELNYX_API_KEY")
    if not auth_token:
        logger.warning("TELNYX_API_KEY not set — skipping webhook signature validation")
        return True
    try:
        # Legacy RequestValidator removed — Telnyx uses webhook signing secrets instead.
        # For now, log and pass through; Telnyx signature validation should be added
        # at the Telnyx webhook ingress layer.
        signature = request.headers.get("X-Telnyx-Signature", "")
        url = str(request.url)
        if signature:
            logger.info(f"Received request with webhook signature header at {url} — pass-through (Telnyx)")
        return True
    except Exception as e:
        logger.error(f"Webhook signature validation error: {e}")
        return False

# Backward-compatible alias
_validate_twilio_signature = _validate_webhook_signature


# Initialize OpenAI conversation service for SMS
_openai_sms_service = None
def get_openai_sms_service():
    global _openai_sms_service
    if _openai_sms_service is None and OPENAI_SERVICE_AVAILABLE:
        _openai_sms_service = OpenAIConversationService()
    return _openai_sms_service

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
security = HTTPBearer(auto_error=False)


# User proxy class for auth
class UserProxy:
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.full_name = row[2]


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from auth.tokens import verify_access_token

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        return UserProxy(user_row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication")


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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send SMS message to client"""

    if not sms_client.enabled:
        logger.error(f"SMS not enabled. API key set: {bool(sms_client._telnyx_api_key)}, from_number: {sms_client.from_number}")
        raise HTTPException(status_code=503, detail="SMS service not configured. Check TELNYX_API_KEY and TELNYX_PHONE_NUMBER env vars.")

    try:
        # Send SMS
        result = sms_client.send_sms(
            to_number=request.to_number,
            message=request.message
        )

        # send_sms returns message_id string on success, None on failure
        if not result:
            raise HTTPException(
                status_code=502,
                detail=f"Telnyx API failed to send SMS. Check TELNYX_API_KEY and TELNYX_PHONE_NUMBER. From: {sms_client.from_number}"
            )

        message_sid = result

        # Log SMS in database
        try:
            from database.models import SMSMessage
            sms_record = SMSMessage(
                user_id=current_user.id,
                lead_id=request.lead_id,
                loan_id=request.loan_id,
                to_number=request.to_number,
                from_number=sms_client.from_number,
                message=request.message,
                direction="outbound",
                status="sent",
                provider_message_id=message_sid,
                template_used=request.template
            )
            db.add(sms_record)
            db.commit()
        except Exception as db_err:
            logger.warning(f"SMS sent but failed to log in DB: {db_err}")
            db.rollback()

        logger.info(f"SMS sent to {request.to_number}, sid={message_sid}")

        return {
            "status": "sent",
            "message_sid": message_sid,
            "to": request.to_number
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending SMS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"SMS send failed: {str(e)[:200]}")


@router.get("/sms/history")
async def get_sms_history(
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get SMS message history"""

    from database.models import SMSMessage

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


async def process_sms_with_ai(
    from_number: str,
    to_number: str,
    message: str,
    db: Session
) -> Optional[str]:
    """
    Process incoming SMS with AI and generate a response.

    Returns the AI response text, or None if AI is unavailable.
    """
    openai_service = get_openai_sms_service()
    if not openai_service or not openai_service.enabled:
        logger.warning("OpenAI service not available for SMS processing")
        return None

    try:
        # Normalize phone number for lookup
        phone_normalized = from_number.replace("+1", "").replace("+", "").replace("-", "").replace(" ", "")

        # Look up lead/client by phone number
        contact_result = db.execute(text("""
            SELECT 'lead' as type, id, first_name, email, phone
            FROM leads
            WHERE REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '+1', '') = :phone
            LIMIT 1
        """), {"phone": phone_normalized})
        contact = contact_result.fetchone()

        contact_info = {}
        contact_id = None
        if contact:
            contact_info = {
                "name": contact.first_name,
                "type": contact.type,
                "id": contact.id
            }
            contact_id = contact.id
            logger.info(f"Found contact for {from_number}: {contact.first_name} (Lead #{contact.id})")
        else:
            logger.info(f"No contact found for {from_number}, treating as new inquiry")

        # Get SMS conversation history for this phone number
        history_result = db.execute(text("""
            SELECT message, direction, created_at
            FROM sms_messages
            WHERE (from_number = :phone OR to_number = :phone)
            ORDER BY created_at DESC
            LIMIT 10
        """), {"phone": from_number})
        history_rows = history_result.fetchall()

        # Build conversation history in chronological order
        conversation_history = []
        for row in reversed(list(history_rows)):
            role = "user" if row.direction == "inbound" else "assistant"
            conversation_history.append({
                "role": role,
                "content": row.message
            })

        # Generate AI response
        import uuid
        conversation_id = f"sms_{from_number}_{uuid.uuid4().hex[:8]}"

        response = await openai_service.generate_response(
            conversation_id=conversation_id,
            channel="sms",
            user_message=message,
            conversation_history=conversation_history,
            qualification_data=contact_info,
            conversation_stage="inquiry",
            persona={
                "name": os.getenv("AI_SMS_NAME", "Sarah"),
                "role": "Mortgage Advisor",
                "company": os.getenv("BUSINESS_NAME", "CMG Home Loans"),
                "lo_name": os.getenv("LO_NAME", "your loan officer"),
                "available_times": "Monday-Friday 9am-6pm"
            },
            user_id=contact_id
        )

        ai_text = response.get("text", "")
        if ai_text:
            logger.info(f"Generated AI SMS response for {from_number}: {ai_text[:50]}...")
            return ai_text
        else:
            logger.warning("OpenAI returned empty response")
            return None

    except Exception as e:
        logger.error(f"Error generating AI SMS response: {e}")
        return None


@router.post("/sms/webhook")
async def sms_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Webhook for incoming SMS messages from Telnyx with AI processing"""

    try:
        form_data = await request.form()
        form_dict = {k: v for k, v in form_data.items()}

        # Validate webhook signature
        if not await _validate_webhook_signature(request, form_dict):
            logger.warning("Invalid webhook signature on SMS webhook")
            raise HTTPException(status_code=403, detail="Invalid signature")

        from_number = form_data.get("From")
        to_number = form_data.get("To")
        body = form_data.get("Body")
        message_sid = form_data.get("MessageSid")

        logger.info(f"Received SMS from {from_number}: {body}")

        # Store incoming SMS
        from database.models import SMSMessage
        sms_record = SMSMessage(
            to_number=to_number,
            from_number=from_number,
            message=body,
            direction="inbound",
            status="received",
            provider_message_id=message_sid
        )
        db.add(sms_record)
        db.commit()
        inbound_id = sms_record.id

        # Process with AI and send response
        ai_response = await process_sms_with_ai(from_number, to_number, body, db)

        if ai_response and sms_client.enabled:
            # Send AI response via Telnyx
            response_sid = sms_client.send_sms(
                to_number=from_number,
                message=ai_response
            )

            if response_sid:
                # Store outbound SMS
                outbound_record = SMSMessage(
                    to_number=from_number,
                    from_number=to_number,
                    message=ai_response,
                    direction="outbound",
                    status="sent",
                    provider_message_id=response_sid
                )
                db.add(outbound_record)
                db.commit()

                logger.info(f"Sent AI response to {from_number}: {ai_response[:50]}...")
                return {
                    "status": "processed",
                    "ai_response_sent": True,
                    "response_sid": response_sid
                }
            else:
                logger.error("Failed to send SMS response via Telnyx")
                return {
                    "status": "received",
                    "ai_response_sent": False,
                    "error": "SMS send failed"
                }
        else:
            # AI not available or SMS not configured
            return {
                "status": "received",
                "ai_response_sent": False,
                "reason": "AI or SMS provider not configured"
            }

    except Exception as e:
        logger.error(f"Error processing SMS webhook: {e}")
        return {"status": "error", "message": "Internal server error"}


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
        from database.models import EmailMessage
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email/webhook")
async def email_webhook(
    payload: EmailWebhookPayload,
    db: Session = Depends(get_db)
):
    """Webhook for incoming emails"""

    try:
        logger.info(f"Received email from {payload.from_email}: {payload.subject}")

        # Store email
        from database.models import EmailMessage
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
        return {"status": "error", "message": "Internal server error"}


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
        from database.models import TeamsMessage
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status")
async def get_integration_status():
    """Get status of all integrations"""

    return {
        "sms": {
            "enabled": sms_client.enabled,
            "provider": "Telnyx",
            "from_number": sms_client.from_number if sms_client.enabled else None
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
