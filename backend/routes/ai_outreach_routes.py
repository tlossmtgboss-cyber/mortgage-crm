"""
AI Outreach Routes
Send AI-powered email and SMS conversations to leads/contacts
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
import logging
import os

from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ai-outreach", tags=["AI Outreach"])


class OutreachChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"


class OutreachTemplate(BaseModel):
    id: str
    name: str
    channel: str
    subject: Optional[str] = None
    message: str
    description: str


class StartOutreachRequest(BaseModel):
    contact_id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    channel: OutreachChannel = OutreachChannel.EMAIL
    template_id: Optional[str] = None
    custom_message: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    contact_name: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    channel: str
    status: str
    stage: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


# Predefined outreach templates
OUTREACH_TEMPLATES = [
    {
        "id": "mortgage_inquiry",
        "name": "Mortgage Inquiry",
        "channel": "email",
        "subject": "Quick question about your mortgage goals",
        "message": """Hi {first_name},

I'm Sarah, a mortgage assistant at Perennia AI. I help people find the best mortgage options for their situation.

Are you looking to purchase a new home or refinance your current mortgage?

Just reply to this email and I'll guide you through the process.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI""",
        "description": "Initial outreach asking about purchase vs refinance"
    },
    {
        "id": "rate_check",
        "name": "Rate Check Offer",
        "channel": "email",
        "subject": "Mortgage rates are moving - let's check your options",
        "message": """Hi {first_name},

I noticed mortgage rates have been shifting lately, and I wanted to reach out.

Would you like me to run a quick rate check to see what options might be available for you? It only takes a few minutes and there's no obligation.

Just reply with a good time to chat, or let me know if you have any questions.

Best,
Sarah
AI Mortgage Assistant | Perennia AI""",
        "description": "Outreach about current rate environment"
    },
    {
        "id": "follow_up",
        "name": "Friendly Follow-up",
        "channel": "email",
        "subject": "Following up on your mortgage interest",
        "message": """Hi {first_name},

I wanted to follow up and see if you had any questions about mortgage options.

Whether you're thinking about buying, refinancing, or just exploring what's possible, I'm here to help.

What questions can I answer for you?

Best,
Sarah
AI Mortgage Assistant | Perennia AI""",
        "description": "Gentle follow-up for leads who haven't responded"
    },
    {
        "id": "sms_intro",
        "name": "SMS Introduction",
        "channel": "sms",
        "subject": None,
        "message": "Hi {first_name}! This is Sarah from Perennia AI. I help people find great mortgage options. Are you looking to buy or refinance? Reply to chat!",
        "description": "Short SMS introduction"
    },
    {
        "id": "sms_rate_alert",
        "name": "SMS Rate Alert",
        "channel": "sms",
        "subject": None,
        "message": "Hi {first_name}! Rates are moving - want me to check what options are available for you? Takes just a few minutes. Reply YES to get started!",
        "description": "SMS about rate changes"
    }
]


@router.get("/templates", response_model=List[OutreachTemplate])
async def get_outreach_templates(
    channel: Optional[OutreachChannel] = None
):
    """Get available outreach templates"""
    templates = OUTREACH_TEMPLATES
    if channel:
        templates = [t for t in templates if t["channel"] == channel.value]
    return templates


@router.get("/contacts")
async def get_contacts_for_outreach(
    search: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get contacts/leads available for outreach"""
    try:
        # Search in both leads and contacts tables
        query = """
            SELECT
                'lead' as type,
                l.id,
                COALESCE(l.first_name, '') || ' ' || COALESCE(l.last_name, '') as name,
                l.email,
                l.phone,
                l.status,
                l.created_at,
                l.last_contacted_at
            FROM leads l
            WHERE l.email IS NOT NULL OR l.phone IS NOT NULL
        """

        params = {"limit": limit, "offset": offset}

        if search:
            query += """ AND (
                LOWER(l.first_name) LIKE LOWER(:search) OR
                LOWER(l.last_name) LIKE LOWER(:search) OR
                LOWER(l.email) LIKE LOWER(:search) OR
                l.phone LIKE :search
            )"""
            params["search"] = f"%{search}%"

        query += " ORDER BY l.created_at DESC LIMIT :limit OFFSET :offset"

        result = db.execute(text(query), params)
        contacts = [dict(row._mapping) for row in result.fetchall()]

        # Get total count
        count_query = """
            SELECT COUNT(*) as total FROM leads l
            WHERE l.email IS NOT NULL OR l.phone IS NOT NULL
        """
        if search:
            count_query += """ AND (
                LOWER(l.first_name) LIKE LOWER(:search) OR
                LOWER(l.last_name) LIKE LOWER(:search) OR
                LOWER(l.email) LIKE LOWER(:search) OR
                l.phone LIKE :search
            )"""

        total_result = db.execute(text(count_query), {"search": f"%{search}%" if search else ""})
        total = total_result.scalar() or 0

        return {
            "contacts": contacts,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_ai_outreach(
    request: StartOutreachRequest,
    db: Session = Depends(get_db)
):
    """Start an AI-powered outreach conversation"""
    try:
        # Get contact info
        email = request.email
        phone = request.phone
        first_name = request.first_name or "there"

        if request.contact_id:
            # Fetch contact details
            result = db.execute(text("""
                SELECT first_name, last_name, email, phone
                FROM leads WHERE id = :id
            """), {"id": request.contact_id})
            contact = result.fetchone()
            if contact:
                first_name = contact.first_name or first_name
                email = contact.email or email
                phone = contact.phone or phone

        # Get template
        template = None
        if request.template_id:
            template = next((t for t in OUTREACH_TEMPLATES if t["id"] == request.template_id), None)

        # Use custom message or template
        if request.custom_message:
            message = request.custom_message.replace("{first_name}", first_name)
            subject = "Message from Perennia AI"
        elif template:
            message = template["message"].replace("{first_name}", first_name)
            subject = template.get("subject", "Message from Perennia AI")
            if subject:
                subject = subject.replace("{first_name}", first_name)
        else:
            # Default message
            message = f"Hi {first_name}, I'm Sarah from Perennia AI. How can I help you with your mortgage needs today?"
            subject = "Quick question about your mortgage goals"

        if request.channel == OutreachChannel.EMAIL:
            if not email:
                raise HTTPException(status_code=400, detail="Email address required for email outreach")
            return await _send_email_outreach(email, first_name, subject, message, db)
        else:
            if not phone:
                raise HTTPException(status_code=400, detail="Phone number required for SMS outreach")
            return await _send_sms_outreach(phone, first_name, message, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting outreach: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _send_email_outreach(email: str, first_name: str, subject: str, message: str, db: Session):
    """Send email outreach"""
    try:
        from email_service import EmailService
        from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

        email_service = EmailService()

        # Create conversation ID
        conv_id = f"email_{email.replace('@', '_').replace('.', '_')}"

        # Initialize conversation state
        conv_service = get_conversation_service()
        state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

        # Record AI's initial message
        state.message_history.append({
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        state.stage = ConversationStage.QUALIFICATION

        # Format HTML email
        html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px;">
{message.replace(chr(10), '<br>')}
</body>
</html>"""

        # Get reply-to from settings or env
        reply_to = os.getenv("REPLY_TO_EMAIL", email_service.from_email)

        # Send email
        result = email_service.send_html_email(
            to_email=email,
            subject=subject,
            html_body=html_body,
            plain_text_body=message,
            reply_to=reply_to
        )

        # Log to database
        try:
            db.execute(text("""
                INSERT INTO ai_outreach_log (
                    conversation_id, channel, recipient_email, recipient_name,
                    subject, message, status, created_at
                ) VALUES (
                    :conv_id, 'email', :email, :name, :subject, :message,
                    :status, CURRENT_TIMESTAMP
                )
            """), {
                "conv_id": conv_id,
                "email": email,
                "name": first_name,
                "subject": subject,
                "message": message,
                "status": "sent" if result else "failed"
            })
            db.commit()
        except Exception as log_err:
            logger.warning(f"Failed to log outreach: {log_err}")

        return {
            "success": result,
            "channel": "email",
            "conversation_id": conv_id,
            "recipient": email,
            "subject": subject,
            "message": "Email sent successfully! AI will handle replies automatically." if result else "Failed to send email"
        }

    except Exception as e:
        logger.error(f"Email outreach error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _send_sms_outreach(phone: str, first_name: str, message: str, db: Session):
    """Send SMS outreach"""
    try:
        from services.twilio_client import TwilioClient
        from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

        # Clean phone number
        clean_phone = ''.join(filter(str.isdigit, phone))
        if len(clean_phone) == 10:
            clean_phone = '1' + clean_phone
        if not clean_phone.startswith('+'):
            clean_phone = '+' + clean_phone

        # Create conversation ID
        conv_id = f"sms_{clean_phone.replace('+', '')}"

        # Initialize conversation state
        conv_service = get_conversation_service()
        state = conv_service.get_or_create_conversation(conv_id, Channel.SMS)

        # Record AI's initial message
        state.message_history.append({
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        state.stage = ConversationStage.QUALIFICATION

        # Send SMS
        twilio_client = TwilioClient()
        sms_result = await twilio_client.send_sms(
            to_number=clean_phone,
            message=message
        )

        success = sms_result is not None

        # Log to database
        try:
            db.execute(text("""
                INSERT INTO ai_outreach_log (
                    conversation_id, channel, recipient_phone, recipient_name,
                    message, status, created_at
                ) VALUES (
                    :conv_id, 'sms', :phone, :name, :message,
                    :status, CURRENT_TIMESTAMP
                )
            """), {
                "conv_id": conv_id,
                "phone": clean_phone,
                "name": first_name,
                "message": message,
                "status": "sent" if success else "failed"
            })
            db.commit()
        except Exception as log_err:
            logger.warning(f"Failed to log SMS outreach: {log_err}")

        return {
            "success": success,
            "channel": "sms",
            "conversation_id": conv_id,
            "recipient": clean_phone,
            "message_sid": sms_result,
            "message": "SMS sent successfully! AI will handle replies automatically." if success else "Failed to send SMS"
        }

    except Exception as e:
        logger.error(f"SMS outreach error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def get_ai_conversations(
    channel: Optional[OutreachChannel] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get active AI conversations"""
    try:
        query = """
            SELECT
                conversation_id as id,
                channel,
                COALESCE(recipient_name, 'Unknown') as contact_name,
                recipient_email as contact_email,
                recipient_phone as contact_phone,
                status,
                message as last_message,
                created_at,
                (SELECT COUNT(*) FROM ai_outreach_log l2
                 WHERE l2.conversation_id = ai_outreach_log.conversation_id) as message_count
            FROM ai_outreach_log
            WHERE 1=1
        """
        params = {"limit": limit, "offset": offset}

        if channel:
            query += " AND channel = :channel"
            params["channel"] = channel.value

        if status:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        result = db.execute(text(query), params)
        conversations = [dict(row._mapping) for row in result.fetchall()]

        return {
            "conversations": conversations,
            "total": len(conversations),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        # Return empty if table doesn't exist yet
        return {"conversations": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get conversation detail with full message history"""
    try:
        from services.conversation_intelligence import get_conversation_service, Channel

        # Determine channel from conversation ID
        channel = Channel.EMAIL if conversation_id.startswith("email_") else Channel.SMS

        conv_service = get_conversation_service()
        state = conv_service.get_or_create_conversation(conversation_id, channel)

        return {
            "conversation_id": conversation_id,
            "channel": channel.value,
            "stage": state.stage.value if hasattr(state.stage, 'value') else str(state.stage),
            "messages": state.message_history,
            "collected_info": state.collected_info,
            "appointment_booked": state.appointment_booked
        }
    except Exception as e:
        logger.error(f"Error fetching conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_outreach_stats(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get outreach statistics"""
    try:
        result = db.execute(text("""
            SELECT
                channel,
                COUNT(*) as total_sent,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) as successful,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM ai_outreach_log
            WHERE created_at >= CURRENT_DATE - :days
            GROUP BY channel
        """), {"days": days})

        stats_by_channel = {}
        for row in result.fetchall():
            stats_by_channel[row.channel] = {
                "total_sent": row.total_sent,
                "successful": row.successful,
                "failed": row.failed
            }

        return {
            "period_days": days,
            "by_channel": stats_by_channel,
            "total_sent": sum(s["total_sent"] for s in stats_by_channel.values()),
            "total_successful": sum(s["successful"] for s in stats_by_channel.values())
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {"period_days": days, "by_channel": {}, "total_sent": 0, "total_successful": 0}


# Create the outreach log table
def create_outreach_table(engine):
    """Create the AI outreach log table if it doesn't exist"""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_outreach_log (
                    id SERIAL PRIMARY KEY,
                    conversation_id VARCHAR(255) NOT NULL,
                    channel VARCHAR(20) NOT NULL,
                    recipient_email VARCHAR(255),
                    recipient_phone VARCHAR(50),
                    recipient_name VARCHAR(255),
                    subject VARCHAR(500),
                    message TEXT,
                    status VARCHAR(50) DEFAULT 'sent',
                    response_received BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_outreach_conv_id ON ai_outreach_log(conversation_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_outreach_channel ON ai_outreach_log(channel)
            """))
            conn.commit()
            logger.info("✅ AI outreach log table ready")
    except Exception as e:
        logger.warning(f"Could not create outreach table: {e}")
