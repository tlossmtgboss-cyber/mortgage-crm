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
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _DEFAULT_ORGANIZER_EMAIL
except ImportError:
    _DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/ai-outreach", tags=["AI Outreach"],
    dependencies=[Depends(_get_current_user())],
)


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
        contacts = []
        params = {"limit": limit, "offset": offset}

        # Build search condition
        search_condition = ""
        if search:
            params["search"] = f"%{search}%"
            search_condition = """ AND (
                LOWER(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) LIKE LOWER(:search) OR
                LOWER(first_name) LIKE LOWER(:search) OR
                LOWER(last_name) LIKE LOWER(:search) OR
                LOWER(email) LIKE LOWER(:search) OR
                phone LIKE :search OR
                LOWER(name) LIKE LOWER(:search)
            )"""

        # Search leads
        try:
            lead_query = f"""
                SELECT
                    'lead' as type,
                    id,
                    COALESCE(name, COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) as name,
                    email,
                    phone,
                    stage as status
                FROM leads
                WHERE (email IS NOT NULL AND email != '') OR (phone IS NOT NULL AND phone != '')
                {search_condition.replace('name', 'COALESCE(name, first_name)')}
                ORDER BY created_at DESC
                LIMIT :limit
            """
            result = db.execute(text(lead_query), params)
            for row in result.fetchall():
                contacts.append({
                    "type": "lead",
                    "id": row[1],
                    "name": row[2] or "Unknown",
                    "email": row[3],
                    "phone": row[4],
                    "status": row[5]
                })
        except SQLAlchemyError as e:
            logger.warning(f"Error searching leads: {e}")

        # Search loan borrowers
        try:
            loan_query = f"""
                SELECT
                    'borrower' as type,
                    id,
                    borrower_name as name,
                    borrower_email as email,
                    borrower_phone as phone,
                    status
                FROM loans
                WHERE (borrower_email IS NOT NULL AND borrower_email != '')
                   OR (borrower_phone IS NOT NULL AND borrower_phone != '')
                {"AND LOWER(borrower_name) LIKE LOWER(:search)" if search else ""}
                ORDER BY created_at DESC
                LIMIT :limit
            """
            result = db.execute(text(loan_query), params)
            for row in result.fetchall():
                # Avoid duplicates by email
                if not any(c.get('email') == row[3] for c in contacts if row[3]):
                    contacts.append({
                        "type": "borrower",
                        "id": row[1],
                        "name": row[2] or "Unknown",
                        "email": row[3],
                        "phone": row[4],
                        "status": row[5]
                    })
        except SQLAlchemyError as e:
            logger.warning(f"Error searching loans: {e}")

        # Search users (for internal notifications)
        try:
            user_query = f"""
                SELECT
                    'user' as type,
                    id,
                    COALESCE(first_name, '') || ' ' || COALESCE(last_name, '') as name,
                    email,
                    phone,
                    role as status
                FROM users
                WHERE email IS NOT NULL AND email != ''
                {"AND (LOWER(first_name) LIKE LOWER(:search) OR LOWER(last_name) LIKE LOWER(:search) OR LOWER(email) LIKE LOWER(:search))" if search else ""}
                ORDER BY first_name
                LIMIT 20
            """
            result = db.execute(text(user_query), params)
            for row in result.fetchall():
                if not any(c.get('email') == row[3] for c in contacts if row[3]):
                    contacts.append({
                        "type": "user",
                        "id": row[1],
                        "name": row[2] or "Unknown",
                        "email": row[3],
                        "phone": row[4],
                        "status": row[5]
                    })
        except SQLAlchemyError as e:
            logger.warning(f"Error searching users: {e}")

        # Sort by name and limit
        contacts.sort(key=lambda x: x.get('name', '').lower())
        contacts = contacts[:limit]

        return {
            "contacts": contacts,
            "total": len(contacts),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching contacts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


async def _send_email_outreach(email: str, first_name: str, subject: str, message: str, db: Session):
    """Send email outreach with proper conversation tracking for two-way AI replies"""
    try:
        from email_service import EmailService
        from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

        email_service = EmailService()

        # Create conversation ID using email format (matches main.py webhook handler)
        # Format: email_tlossmtgboss_gmail_com (email with @ and . replaced)
        conv_id = f"email_{email.replace('@', '_').replace('.', '_')}"

        # Initialize conversation state (in-memory)
        conv_service = get_conversation_service()
        state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

        # Record AI's initial message
        state.message_history.append({
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        state.stage = ConversationStage.QUALIFICATION

        # Format HTML email with conversation footer
        html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px;">
{message.replace(chr(10), '<br>')}

<br><br>
<p style="color: #666; font-size: 10pt;">---<br>
This is an AI-assisted conversation. Simply reply to this email to continue chatting with Sarah, your mortgage assistant.</p>
</body>
</html>"""

        # Use reply.perenniaai.com subdomain for SendGrid Inbound Parse
        # When user replies, SendGrid forwards to /api/v1/webhook/sendgrid-inbound
        reply_to = os.getenv("REPLY_TO_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

        # Generate message ID for threading
        message_id = f"<{conv_id}@mortgagecrm.ai>"

        # Get user ID (demo user for now)
        user_id = 1
        try:
            import main
            demo_user = db.execute(text("SELECT id FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1")).fetchone()
            if demo_user:
                user_id = demo_user.id
        except Exception as e:
            logger.error(f"Error fetching demo user: {e}")

        # Ensure conversation tables exist
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_email_conversations (
                    id SERIAL PRIMARY KEY,
                    conversation_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER,
                    recipient_email VARCHAR(255),
                    recipient_name VARCHAR(255),
                    loan_id INTEGER,
                    lead_id INTEGER,
                    conversation_type VARCHAR(50) DEFAULT 'outreach',
                    status VARCHAR(50) DEFAULT 'active',
                    context JSONB,
                    message_count INTEGER DEFAULT 0,
                    last_message_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_email_messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id VARCHAR(255) NOT NULL,
                    direction VARCHAR(20) NOT NULL,
                    from_email VARCHAR(255),
                    to_email VARCHAR(255),
                    subject VARCHAR(500),
                    body_text TEXT,
                    body_html TEXT,
                    message_id VARCHAR(255),
                    in_reply_to VARCHAR(255),
                    ai_generated BOOLEAN DEFAULT FALSE,
                    ai_model VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.commit()
        except Exception as table_err:
            logger.warning(f"Table creation note: {table_err}")

        # Create conversation record in ai_email_conversations
        try:
            db.execute(text("""
                INSERT INTO ai_email_conversations
                (conversation_id, user_id, recipient_email, recipient_name,
                 conversation_type, status, message_count, created_at)
                VALUES (:conv_id, :user_id, :email, :name,
                        'outreach', 'active', 1, NOW())
                ON CONFLICT (conversation_id) DO UPDATE
                SET message_count = ai_email_conversations.message_count + 1,
                    last_message_at = NOW()
            """), {
                "conv_id": conv_id,
                "user_id": user_id,
                "email": email,
                "name": first_name
            })
            db.commit()
        except Exception as conv_err:
            logger.warning(f"Conversation record note: {conv_err}")
            db.rollback()

        # Send email with tracking headers - use reply subdomain as FROM so replies come back
        result = email_service.send_html_email(
            to_email=email,
            subject=subject,
            html_body=html_body,
            plain_text_body=message,
            from_email=reply_to,  # Send FROM the reply subdomain
            reply_to=reply_to,
            headers={
                "Message-ID": message_id,
                "X-Conversation-ID": conv_id,
                "X-AI-Conversation": "true"
            }
        )

        # Store outbound message in ai_email_messages
        if result:
            try:
                db.execute(text("""
                    INSERT INTO ai_email_messages
                    (conversation_id, direction, from_email, to_email, subject,
                     body_text, body_html, message_id, ai_generated, created_at)
                    VALUES (:conv_id, 'outbound', :from_email, :to_email, :subject,
                            :body_text, :body_html, :msg_id, true, NOW())
                """), {
                    "conv_id": conv_id,
                    "from_email": reply_to,  # Use the same FROM address we sent with
                    "to_email": email,
                    "subject": subject,
                    "body_text": message,
                    "body_html": html_body,
                    "msg_id": message_id
                })
                db.commit()
            except Exception as msg_err:
                logger.warning(f"Message record note: {msg_err}")

        # Also log to outreach log for statistics
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

        logger.info(f"Started AI outreach conversation {conv_id} with {email}, reply-to: {reply_to}")

        return {
            "success": result,
            "channel": "email",
            "conversation_id": conv_id,
            "recipient": email,
            "subject": subject,
            "reply_to": reply_to,
            "message": "Email sent successfully! AI will handle replies automatically." if result else "Failed to send email"
        }

    except Exception as e:
        logger.error(f"Email outreach error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _send_sms_outreach(phone: str, first_name: str, message: str, db: Session):
    """Send SMS outreach"""
    try:
        from services.notification_service import notification_service
        from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

        # Clean phone number
        clean_phone = ''.join(filter(str.isdigit, phone))
        if len(clean_phone) == 10:
            clean_phone = '+1' + clean_phone
        elif not clean_phone.startswith('+'):
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

        # Send SMS using notification service
        sms_result = notification_service.send_sms(
            to_phone=clean_phone,
            message=message
        )

        success = sms_result is not None and sms_result.get("success", False)

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

    except SQLAlchemyError as e:
        logger.error(f"SMS outreach error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    except SQLAlchemyError as e:
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

        # Build collected info from qualification_data
        collected_info = {}
        if state.qualification_data:
            qual_data = state.qualification_data
            if qual_data.loan_purpose:
                collected_info["loan_purpose"] = qual_data.loan_purpose
            if qual_data.property_value:
                collected_info["property_value"] = qual_data.property_value
            if qual_data.closing_timeline:
                collected_info["closing_timeline"] = qual_data.closing_timeline
            if qual_data.first_name:
                collected_info["first_name"] = qual_data.first_name
            if qual_data.email:
                collected_info["email"] = qual_data.email
            if qual_data.phone:
                collected_info["phone"] = qual_data.phone

        return {
            "conversation_id": conversation_id,
            "channel": channel.value,
            "stage": state.stage.value if hasattr(state.stage, 'value') else str(state.stage),
            "messages": state.message_history,
            "collected_info": collected_info,
            "qualification_status": state.qualification_status.value if hasattr(state.qualification_status, 'value') else str(state.qualification_status),
            "message_count": state.message_count
        }
    except Exception as e:
        logger.error(f"Error fetching conversation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    except SQLAlchemyError as e:
        logger.warning(f"Could not create outreach table: {e}")
