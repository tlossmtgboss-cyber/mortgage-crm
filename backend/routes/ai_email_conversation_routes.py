"""
AI Email Conversation Routes

Enables two-way AI-powered email conversations with borrowers and clients.
Recipients can reply to system emails and receive intelligent AI responses.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import uuid
import json
import re
import os
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class ConversationStartRequest(BaseModel):
    """Request to start a new AI email conversation"""
    recipient_email: str
    recipient_name: str
    subject: str
    initial_message: str
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    conversation_type: str = "weekly_update"  # weekly_update, document_request, status_inquiry, general
    context: Optional[Dict[str, Any]] = None


class ConversationMessageResponse(BaseModel):
    """Response model for conversation messages"""
    id: int
    conversation_id: str
    direction: str  # inbound, outbound
    from_email: str
    to_email: str
    subject: str
    body_text: str
    body_html: Optional[str]
    ai_generated: bool
    created_at: datetime


class ConversationResponse(BaseModel):
    """Response model for a conversation"""
    id: int
    conversation_id: str
    recipient_email: str
    recipient_name: str
    loan_id: Optional[int]
    lead_id: Optional[int]
    conversation_type: str
    status: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


# =============================================================================
# Dependencies
# =============================================================================

from database import get_db

def get_current_user_dep():
    """Get current user - imports from main at runtime"""
    import main
    return main.get_current_user


# =============================================================================
# Routes
# =============================================================================

@router.post("/start", response_model=dict)
async def start_conversation(
    request: ConversationStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Start a new AI-powered email conversation.

    Creates a conversation thread and sends the initial email with
    tracking headers for reply detection.
    """
    try:
        # Generate unique conversation ID
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"

        # Get or create conversation tracking table
        ensure_conversation_tables(db)

        # Create conversation record
        db.execute(text("""
            INSERT INTO ai_email_conversations
            (conversation_id, user_id, recipient_email, recipient_name,
             loan_id, lead_id, conversation_type, status, context, created_at)
            VALUES (:conv_id, :user_id, :recipient_email, :recipient_name,
                    :loan_id, :lead_id, :conv_type, 'active', :context, NOW())
        """), {
            "conv_id": conversation_id,
            "user_id": current_user.id,
            "recipient_email": request.recipient_email,
            "recipient_name": request.recipient_name,
            "loan_id": request.loan_id,
            "lead_id": request.lead_id,
            "conv_type": request.conversation_type,
            "context": json.dumps(request.context) if request.context else None
        })
        db.commit()

        # Generate message ID for threading
        message_id = f"<{conversation_id}@mortgagecrm.ai>"

        # Build email with reply-to address that includes conversation ID
        reply_to_email = os.getenv("AI_REPLY_EMAIL", "ai-reply@mortgagecrm.ai")
        # Encode conversation ID in reply-to for tracking
        tagged_reply_to = f"ai-reply+{conversation_id}@{reply_to_email.split('@')[1]}" if '@' in reply_to_email else reply_to_email

        # Add footer to email body with AI conversation notice
        enhanced_html = add_conversation_footer(
            request.initial_message,
            conversation_id,
            request.recipient_name
        )

        # Send email with conversation tracking
        from email_service import email_service

        success = email_service.send_html_email(
            to_email=request.recipient_email,
            subject=request.subject,
            html_body=enhanced_html,
            plain_text_body=strip_html(request.initial_message),
            headers={
                "Message-ID": message_id,
                "Reply-To": tagged_reply_to,
                "X-Conversation-ID": conversation_id,
                "X-AI-Conversation": "true"
            }
        )

        if success:
            # Store outbound message
            db.execute(text("""
                INSERT INTO ai_email_messages
                (conversation_id, direction, from_email, to_email, subject,
                 body_text, body_html, message_id, ai_generated, created_at)
                VALUES (:conv_id, 'outbound', :from_email, :to_email, :subject,
                        :body_text, :body_html, :msg_id, true, NOW())
            """), {
                "conv_id": conversation_id,
                "from_email": os.getenv("SENDGRID_FROM_EMAIL", "noreply@mortgagecrm.com"),
                "to_email": request.recipient_email,
                "subject": request.subject,
                "body_text": strip_html(request.initial_message),
                "body_html": enhanced_html,
                "msg_id": message_id
            })
            db.commit()

            logger.info(f"Started AI conversation {conversation_id} with {request.recipient_email}")

            return {
                "success": True,
                "conversation_id": conversation_id,
                "message": f"Conversation started with {request.recipient_email}",
                "reply_to": tagged_reply_to
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send initial email")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error starting conversation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhook/inbound")
async def inbound_email_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    SendGrid Inbound Parse webhook for receiving email replies.

    This endpoint receives emails sent to the AI reply address,
    extracts the conversation ID, and generates AI responses.

    Supports both SendGrid modes:
    - Parsed mode: 'text' and 'html' fields contain body content
    - Raw mode: 'email' field contains full RFC822 email
    """
    try:
        # Parse form data from SendGrid
        form_data = await request.form()

        from_email = form_data.get("from", "")
        to_email = form_data.get("to", "")
        subject = form_data.get("subject", "")
        text_body = form_data.get("text", "")
        html_body = form_data.get("html", "")
        raw_email = form_data.get("email", "")

        # Log what we received for debugging
        logger.info(f"SendGrid form fields: {list(form_data.keys())}")
        logger.info(f"text_body length={len(text_body)}, html_body length={len(html_body)}, raw_email length={len(raw_email)}")

        # If text/html fields are empty but we have raw email, parse it
        if not text_body.strip() and not html_body.strip() and raw_email:
            logger.info("Parsing raw RFC822 email to extract body")
            text_body, html_body = parse_raw_email(raw_email)
            logger.info(f"Extracted from raw email - text: {len(text_body)} chars, html: {len(html_body)} chars")
            if text_body:
                logger.info(f"Extracted text preview: {text_body[:300]}...")

        # If text is empty but we have HTML, extract text from HTML
        if not text_body.strip() and html_body:
            logger.info("Text body empty, extracting from HTML")
            text_body = html_to_text(html_body)
            logger.info(f"Extracted text from HTML: {text_body[:200]}...")

        # Extract email address from "Name <email>" format
        from_match = re.search(r'<([^>]+)>', from_email)
        from_address = from_match.group(1) if from_match else from_email

        to_match = re.search(r'<([^>]+)>', to_email)
        to_address = to_match.group(1) if to_match else to_email

        logger.info(f"Inbound email from {from_address} to {to_address}: {subject}")

        # Extract conversation ID from to address (ai-reply+conv_xxx@domain.com)
        conv_match = re.search(r'ai-reply\+([^@]+)@', to_address)
        conversation_id = conv_match.group(1) if conv_match else None

        # Also check headers for conversation ID
        headers = form_data.get("headers", "")
        if not conversation_id and "X-Conversation-ID" in headers:
            conv_header_match = re.search(r'X-Conversation-ID:\s*(\S+)', headers)
            conversation_id = conv_header_match.group(1) if conv_header_match else None

        # Get Message-ID for threading
        inbound_message_id = form_data.get("Message-ID", "")
        if not inbound_message_id and headers:
            msg_id_match = re.search(r'Message-ID:\s*(<[^>]+>)', headers, re.IGNORECASE)
            inbound_message_id = msg_id_match.group(1) if msg_id_match else ""

        # Check In-Reply-To header for message threading
        in_reply_to = form_data.get("In-Reply-To", "")
        if not conversation_id and in_reply_to:
            # Extract from message ID format: <conv_xxx@mortgagecrm.ai>
            reply_match = re.search(r'<(conv_[^@]+)@', in_reply_to)
            conversation_id = reply_match.group(1) if reply_match else None

        # Variables for conversation context
        conv_result = None
        lead_id = None
        loan_id = None
        user_id = None
        context = None
        is_new_conversation = False

        if conversation_id:
            # Verify conversation exists
            conv_result = db.execute(text("""
                SELECT id, user_id, recipient_email, loan_id, lead_id,
                       conversation_type, context, status
                FROM ai_email_conversations
                WHERE conversation_id = :conv_id
            """), {"conv_id": conversation_id}).fetchone()

            if conv_result:
                if conv_result.status == "closed":
                    logger.info(f"Conversation {conversation_id} is closed")
                    return {"status": "ignored", "reason": "conversation_closed"}
                lead_id = conv_result.lead_id
                loan_id = conv_result.loan_id
                user_id = conv_result.user_id
                context = conv_result.context

        # If no existing conversation, create a new one for this fresh inbound email
        if not conv_result:
            logger.info(f"Creating new conversation for fresh inbound email from {from_address}")
            is_new_conversation = True

            # Generate new conversation ID
            conversation_id = f"conv_{uuid.uuid4().hex[:12]}"

            # Extract sender name from email "Name <email>" format
            sender_name_match = re.match(r'^([^<]+)\s*<', from_email)
            sender_name = sender_name_match.group(1).strip() if sender_name_match else from_address.split('@')[0]

            # Determine organization context from the recipient (LO) address
            recipient_user = db.execute(text("""
                SELECT id, organization_id FROM users WHERE email = :email LIMIT 1
            """), {"email": to_address}).fetchone()
            org_id = recipient_user.organization_id if recipient_user else None

            # Try to find existing lead by email (scoped to organization if known)
            if org_id:
                existing_lead = db.execute(text("""
                    SELECT id, name, owner_id
                    FROM leads
                    WHERE email = :email AND organization_id = :org_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"email": from_address, "org_id": org_id}).fetchone()
            else:
                existing_lead = db.execute(text("""
                    SELECT id, name, owner_id
                    FROM leads
                    WHERE email = :email
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"email": from_address}).fetchone()

            if existing_lead:
                lead_id = existing_lead.id
                user_id = existing_lead.owner_id
                sender_name = existing_lead.name or sender_name
                logger.info(f"Matched inbound email to existing lead {lead_id}")
            else:
                # Create a new lead for this email
                # Use recipient LO as owner, or fall back to first admin
                if recipient_user:
                    user_id = recipient_user.id
                else:
                    default_user = db.execute(text("""
                        SELECT id FROM users
                        WHERE role IN ('admin', 'owner', 'loan_officer')
                        ORDER BY id ASC
                        LIMIT 1
                    """)).fetchone()
                    user_id = default_user.id if default_user else 1

                # Create new lead with organization_id for tenant isolation
                db.execute(text("""
                    INSERT INTO leads (name, email, source, owner_id, organization_id, created_at, updated_at)
                    VALUES (:name, :email, 'inbound_email', :owner_id, :org_id, NOW(), NOW())
                """), {
                    "name": sender_name,
                    "email": from_address,
                    "owner_id": user_id,
                    "org_id": org_id
                })

                # Get the new lead ID (scoped to org if known)
                if org_id:
                    new_lead = db.execute(text("""
                        SELECT id FROM leads WHERE email = :email AND organization_id = :org_id ORDER BY id DESC LIMIT 1
                    """), {"email": from_address, "org_id": org_id}).fetchone()
                else:
                    new_lead = db.execute(text("""
                        SELECT id FROM leads WHERE email = :email ORDER BY id DESC LIMIT 1
                    """), {"email": from_address}).fetchone()
                lead_id = new_lead.id if new_lead else None
                logger.info(f"Created new lead {lead_id} from inbound email")

            # Create the new conversation
            db.execute(text("""
                INSERT INTO ai_email_conversations
                (conversation_id, user_id, recipient_email, recipient_name,
                 lead_id, conversation_type, status, message_count, created_at, last_message_at)
                VALUES (:conv_id, :user_id, :email, :name,
                        :lead_id, 'inbound_inquiry', 'active', 0, NOW(), NOW())
            """), {
                "conv_id": conversation_id,
                "user_id": user_id,
                "email": from_address,
                "name": sender_name,
                "lead_id": lead_id
            })

            logger.info(f"Created new conversation {conversation_id} for {from_address}")

        # Clean the reply text (remove quoted content)
        clean_reply = clean_email_reply(text_body)
        logger.info(f"After cleaning - reply length: {len(clean_reply)}, content: {clean_reply[:200] if clean_reply else 'EMPTY'}...")

        # Store inbound message with message_id for threading
        db.execute(text("""
            INSERT INTO ai_email_messages
            (conversation_id, direction, from_email, to_email, subject,
             body_text, body_html, message_id, ai_generated, created_at)
            VALUES (:conv_id, 'inbound', :from_email, :to_email, :subject,
                    :body_text, :body_html, :message_id, false, NOW())
        """), {
            "conv_id": conversation_id,
            "from_email": from_address,
            "to_email": to_address,
            "subject": subject,
            "body_text": clean_reply,
            "body_html": html_body,
            "message_id": inbound_message_id or None
        })

        # Update conversation last_message_at
        db.execute(text("""
            UPDATE ai_email_conversations
            SET last_message_at = NOW(),
                message_count = COALESCE(message_count, 0) + 1
            WHERE conversation_id = :conv_id
        """), {"conv_id": conversation_id})

        db.commit()

        # Process AI response in background (uses its own DB session)
        background_tasks.add_task(
            generate_ai_response,
            conversation_id,
            clean_reply,
            from_address,
            subject,
            context,
            loan_id,
            lead_id
        )

        status_msg = "new_conversation" if is_new_conversation else "received"
        return {"status": status_msg, "conversation_id": conversation_id, "lead_id": lead_id}

    except Exception as e:
        logger.error(f"Error processing inbound email: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/debug/history")
async def debug_conversation_history(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Debug endpoint to view all conversation history (temporary)"""
    try:
        ensure_conversation_tables(db)

        # Get all conversations with their messages
        conversations = db.execute(text("""
            SELECT c.conversation_id, c.recipient_email, c.recipient_name,
                   c.conversation_type, c.status, c.message_count, c.created_at,
                   c.last_message_at
            FROM ai_email_conversations c
            ORDER BY c.created_at DESC
            LIMIT 20
        """)).fetchall()

        result = []
        for conv in conversations:
            # Get messages for this conversation
            messages = db.execute(text("""
                SELECT direction, from_email, to_email, subject,
                       body_text, created_at, ai_generated
                FROM ai_email_messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
            """), {"conv_id": conv.conversation_id}).fetchall()

            result.append({
                "conversation_id": conv.conversation_id,
                "recipient": f"{conv.recipient_name} <{conv.recipient_email}>",
                "type": conv.conversation_type,
                "status": conv.status,
                "message_count": conv.message_count,
                "created": conv.created_at.isoformat() if conv.created_at else None,
                "messages": [
                    {
                        "direction": "OUTBOUND" if m.direction == "outbound" else "INBOUND",
                        "from": m.from_email,
                        "to": m.to_email,
                        "subject": m.subject,
                        "body": m.body_text[:500] if m.body_text else "",
                        "ai_generated": m.ai_generated,
                        "time": m.created_at.isoformat() if m.created_at else None
                    }
                    for m in messages
                ]
            })

        return result
    except Exception as e:
        logger.error(f"Error in debug history: {e}")
        return {"error": "Internal server error"}


@router.get("/conversations", response_model=List[dict])
async def list_conversations(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """List all AI email conversations for the current user"""
    try:
        ensure_conversation_tables(db)

        query = """
            SELECT id, conversation_id, recipient_email, recipient_name,
                   loan_id, lead_id, conversation_type, status,
                   message_count, last_message_at, created_at
            FROM ai_email_conversations
            WHERE user_id = :user_id
        """
        params = {"user_id": current_user.id}

        if status:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY last_message_at DESC NULLS LAST, created_at DESC LIMIT :limit"
        params["limit"] = limit

        results = db.execute(text(query), params).fetchall()

        return [
            {
                "id": r.id,
                "conversation_id": r.conversation_id,
                "recipient_email": r.recipient_email,
                "recipient_name": r.recipient_name,
                "loan_id": r.loan_id,
                "lead_id": r.lead_id,
                "conversation_type": r.conversation_type,
                "status": r.status,
                "message_count": r.message_count or 0,
                "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]

    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/conversations/{conversation_id}/messages", response_model=List[dict])
async def get_conversation_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all messages in a conversation"""
    try:
        # Verify user owns conversation
        conv = db.execute(text("""
            SELECT id FROM ai_email_conversations
            WHERE conversation_id = :conv_id AND user_id = :user_id
        """), {"conv_id": conversation_id, "user_id": current_user.id}).fetchone()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = db.execute(text("""
            SELECT id, conversation_id, direction, from_email, to_email,
                   subject, body_text, body_html, ai_generated, created_at
            FROM ai_email_messages
            WHERE conversation_id = :conv_id
            ORDER BY created_at ASC
        """), {"conv_id": conversation_id}).fetchall()

        return [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "direction": m.direction,
                "from_email": m.from_email,
                "to_email": m.to_email,
                "subject": m.subject,
                "body_text": m.body_text,
                "body_html": m.body_html,
                "ai_generated": m.ai_generated,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conversations/{conversation_id}/reply", response_model=dict)
async def send_manual_reply(
    conversation_id: str,
    message: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Send a manual (non-AI) reply to a conversation"""
    try:
        # Get conversation
        conv = db.execute(text("""
            SELECT id, recipient_email, recipient_name, user_id
            FROM ai_email_conversations
            WHERE conversation_id = :conv_id AND user_id = :user_id
        """), {"conv_id": conversation_id, "user_id": current_user.id}).fetchone()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get last subject for threading
        last_msg = db.execute(text("""
            SELECT subject FROM ai_email_messages
            WHERE conversation_id = :conv_id
            ORDER BY created_at DESC LIMIT 1
        """), {"conv_id": conversation_id}).fetchone()

        subject = f"Re: {last_msg.subject}" if last_msg else "Follow-up"
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        # Send email
        from email_service import email_service

        reply_to = os.getenv("AI_REPLY_EMAIL", "ai-reply@mortgagecrm.ai")
        tagged_reply_to = f"ai-reply+{conversation_id}@{reply_to.split('@')[1]}" if '@' in reply_to else reply_to

        html_body = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6;">
            {message.replace(chr(10), '<br>')}
        </div>
        """

        success = email_service.send_html_email(
            to_email=conv.recipient_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=message,
            headers={
                "Reply-To": tagged_reply_to,
                "X-Conversation-ID": conversation_id
            }
        )

        if success:
            # Store message
            db.execute(text("""
                INSERT INTO ai_email_messages
                (conversation_id, direction, from_email, to_email, subject,
                 body_text, body_html, ai_generated, created_at)
                VALUES (:conv_id, 'outbound', :from_email, :to_email, :subject,
                        :body_text, :body_html, false, NOW())
            """), {
                "conv_id": conversation_id,
                "from_email": os.getenv("SENDGRID_FROM_EMAIL", "noreply@mortgagecrm.com"),
                "to_email": conv.recipient_email,
                "subject": subject,
                "body_text": message,
                "body_html": html_body
            })

            db.execute(text("""
                UPDATE ai_email_conversations
                SET last_message_at = NOW(),
                    message_count = COALESCE(message_count, 0) + 1
                WHERE conversation_id = :conv_id
            """), {"conv_id": conversation_id})

            db.commit()

            return {"success": True, "message": "Reply sent"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send reply")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error sending manual reply: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/conversations/{conversation_id}/close", response_model=dict)
async def close_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Close an AI conversation (stop auto-replies)"""
    try:
        result = db.execute(text("""
            UPDATE ai_email_conversations
            SET status = 'closed', closed_at = NOW()
            WHERE conversation_id = :conv_id AND user_id = :user_id
            RETURNING id
        """), {"conv_id": conversation_id, "user_id": current_user.id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found")

        db.commit()
        return {"success": True, "message": "Conversation closed"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error closing conversation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/conversations/{conversation_id}", response_model=dict)
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Delete an AI conversation and all its messages"""
    try:
        # Verify user owns conversation
        conv = db.execute(text("""
            SELECT id FROM ai_email_conversations
            WHERE conversation_id = :conv_id AND user_id = :user_id
        """), {"conv_id": conversation_id, "user_id": current_user.id}).fetchone()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Delete all messages first
        db.execute(text("""
            DELETE FROM ai_email_messages
            WHERE conversation_id = :conv_id
        """), {"conv_id": conversation_id})

        # Delete the conversation
        db.execute(text("""
            DELETE FROM ai_email_conversations
            WHERE conversation_id = :conv_id AND user_id = :user_id
        """), {"conv_id": conversation_id, "user_id": current_user.id})

        db.commit()
        logger.info(f"Deleted AI conversation {conversation_id}")
        return {"success": True, "message": "Conversation deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error deleting conversation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Helper Functions
# =============================================================================

def ensure_conversation_tables(db: Session):
    """Create conversation tables if they don't exist"""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_email_conversations (
                id SERIAL PRIMARY KEY,
                conversation_id VARCHAR(50) UNIQUE NOT NULL,
                user_id INTEGER REFERENCES users(id),
                recipient_email VARCHAR(255) NOT NULL,
                recipient_name VARCHAR(255),
                loan_id INTEGER REFERENCES loans(id),
                lead_id INTEGER REFERENCES leads(id),
                conversation_type VARCHAR(50) DEFAULT 'general',
                status VARCHAR(20) DEFAULT 'active',
                context JSONB,
                message_count INTEGER DEFAULT 0,
                last_message_at TIMESTAMP,
                closed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS ix_ai_conv_user ON ai_email_conversations(user_id);
            CREATE INDEX IF NOT EXISTS ix_ai_conv_recipient ON ai_email_conversations(recipient_email);
            CREATE INDEX IF NOT EXISTS ix_ai_conv_status ON ai_email_conversations(status);
        """))

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_email_messages (
                id SERIAL PRIMARY KEY,
                conversation_id VARCHAR(50) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                from_email VARCHAR(255) NOT NULL,
                to_email VARCHAR(255) NOT NULL,
                subject VARCHAR(500),
                body_text TEXT,
                body_html TEXT,
                message_id VARCHAR(255),
                in_reply_to VARCHAR(255),
                ai_generated BOOLEAN DEFAULT false,
                ai_model VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS ix_ai_msg_conv ON ai_email_messages(conversation_id);
            CREATE INDEX IF NOT EXISTS ix_ai_msg_created ON ai_email_messages(created_at);
        """))

        db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Table creation note: {e}")
        db.rollback()


def add_conversation_footer(html_body: str, conversation_id: str, recipient_name: str) -> str:
    """Add AI conversation footer to email"""
    footer = f"""
    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
        <p style="font-size: 13px; color: #666;">
            <strong>Have questions?</strong> Simply reply to this email and our AI assistant
            will respond promptly with helpful information about your loan.
        </p>
        <p style="font-size: 11px; color: #999; margin-top: 10px;">
            This message supports two-way communication. Your replies are processed securely.
            <br>Conversation ID: {conversation_id}
        </p>
    </div>
    """

    # Insert footer before closing body/html tags
    if "</body>" in html_body.lower():
        return html_body.replace("</body>", f"{footer}</body>")
    elif "</html>" in html_body.lower():
        return html_body.replace("</html>", f"{footer}</html>")
    else:
        return html_body + footer


def strip_html(html: str) -> str:
    """Strip HTML tags to get plain text"""
    clean = re.sub('<[^<]+?>', '', html)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def html_to_text(html_body: str) -> str:
    """Convert HTML to plain text"""
    import html as html_module
    # Remove style and script tags
    clean_html = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
    # Replace br and p tags with newlines
    clean_html = re.sub(r'<br\s*/?>', '\n', clean_html, flags=re.IGNORECASE)
    clean_html = re.sub(r'</p>', '\n', clean_html, flags=re.IGNORECASE)
    clean_html = re.sub(r'<div[^>]*>', '\n', clean_html, flags=re.IGNORECASE)
    # Remove all other HTML tags
    clean_html = re.sub(r'<[^>]+>', '', clean_html)
    # Decode HTML entities
    return html_module.unescape(clean_html).strip()


def parse_raw_email(raw_email: str) -> tuple:
    """
    Parse a raw RFC822 email and extract text and HTML parts.
    Returns (text_body, html_body) tuple.
    """
    import email
    from email import policy
    from email.parser import Parser

    try:
        # Parse the raw email
        msg = email.message_from_string(raw_email, policy=policy.default)

        text_body = ""
        html_body = ""

        if msg.is_multipart():
            # Walk through all parts
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_content()
                    if isinstance(payload, bytes):
                        payload = payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    logger.error(f"Error getting multipart content in parse_raw_email: {e}")
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            payload = payload.decode('utf-8', errors='ignore')
                        else:
                            continue
                    except Exception as e2:
                        logger.error(f"Error getting multipart payload fallback in parse_raw_email: {e2}")
                        continue

                if content_type == "text/plain" and not text_body:
                    text_body = payload
                elif content_type == "text/html" and not html_body:
                    html_body = payload
        else:
            # Single-part email
            content_type = msg.get_content_type()
            try:
                payload = msg.get_content()
                if isinstance(payload, bytes):
                    payload = payload.decode('utf-8', errors='ignore')
            except Exception as e:
                logger.error(f"Error getting single-part content in parse_raw_email: {e}")
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        payload = payload.decode('utf-8', errors='ignore')
                    else:
                        payload = ""
                except Exception as e2:
                    logger.error(f"Error getting single-part payload fallback in parse_raw_email: {e2}")
                    payload = ""

            if content_type == "text/plain":
                text_body = payload
            elif content_type == "text/html":
                html_body = payload

        return text_body, html_body

    except Exception as e:
        logger.error(f"Error parsing raw email: {e}")
        # Try a simple extraction as fallback
        # Look for the body after headers (blank line separator)
        try:
            parts = raw_email.split('\r\n\r\n', 1)
            if len(parts) < 2:
                parts = raw_email.split('\n\n', 1)
            if len(parts) >= 2:
                body = parts[1]
                # Check if it looks like HTML
                if '<html' in body.lower() or '<body' in body.lower():
                    return "", body
                else:
                    return body, ""
        except Exception as e2:
            logger.error(f"Error in fallback email body extraction in parse_raw_email: {e2}")
        return "", ""


def clean_email_reply(text: str) -> str:
    """
    Clean email reply by removing quoted content.
    Returns just the new reply text.
    """
    if not text:
        return ""

    lines = text.split('\n')
    clean_lines = []

    for line in lines:
        line_lower = line.lower().strip()

        # Skip lines that start with '>' (quoted text)
        if line.strip().startswith('>'):
            continue

        # Stop at common reply headers (more specific patterns)
        if any([
            line_lower.startswith('on ') and 'wrote:' in line_lower,  # "On Dec 24, 2025, ... wrote:"
            line_lower.startswith('from:') and '@' in line_lower,      # "From: someone@email.com"
            '-----original message-----' in line_lower,
            '________________________________' in line,
            line_lower.startswith('sent from my iphone'),
            line_lower.startswith('sent from my ipad'),
            line_lower.startswith('get outlook for'),
            'wrote:' in line_lower and ('@' in line_lower or 'am' in line_lower or 'pm' in line_lower),
        ]):
            break

        clean_lines.append(line)

    result = '\n'.join(clean_lines).strip()

    # If we got nothing meaningful, return original (might be inline reply)
    if not result or len(result) < 3:
        # Try to extract non-quoted lines from original
        non_quoted = [l for l in lines if not l.strip().startswith('>')]
        result = '\n'.join(non_quoted).strip()

    return result if result else text.strip()


async def generate_ai_response(
    conversation_id: str,
    user_message: str,
    user_email: str,
    subject: str,
    context: Optional[str],
    loan_id: Optional[int],
    lead_id: Optional[int]
):
    """
    Generate and send AI response to an email reply.
    Runs as a background task.

    Uses the consolidated OpenAIConversationService for Trust-First Architecture.
    """
    # Create a new database session for this background task
    from database import get_db, SessionLocal
    db = SessionLocal()

    try:
        logger.info(f"Generating AI response for conversation {conversation_id}")

        # Import the consolidated AI service
        from services.openai_conversation_service import get_openai_service
        ai_service = get_openai_service()

        # Get conversation history from database
        messages_result = db.execute(text("""
            SELECT direction, body_text, created_at
            FROM ai_email_messages
            WHERE conversation_id = :conv_id
            ORDER BY created_at ASC
            LIMIT 10
        """), {"conv_id": conversation_id}).fetchall()

        # Build conversation history for the AI service
        conversation_history = []
        for msg in messages_result:
            role = "assistant" if msg.direction == "outbound" else "user"
            conversation_history.append({
                "role": role,
                "content": msg.body_text or ""
            })

        # Get loan context if available
        loan_context = ""
        if loan_id:
            loan = db.execute(text("""
                SELECT borrower_name, property_address, loan_type, loan_amount,
                       current_stage, closing_date
                FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()
            if loan:
                loan_context = f"""
Loan Information:
- Borrower: {loan.borrower_name}
- Property: {loan.property_address}
- Loan Type: {loan.loan_type}
- Stage: {loan.current_stage}
- Closing Date: {loan.closing_date}
"""

        # Get LO info for value pitch
        lo_name = "Tim"  # Default LO name
        lo_available_times = "Monday-Friday 9am-5pm, Saturday 10am-2pm"

        # Try to get LO from loan first
        if loan_id:
            lo_result = db.execute(text("""
                SELECT u.full_name, u.first_name, u.email, u.phone
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()
            if lo_result:
                lo_name = lo_result.first_name or (lo_result.full_name.split()[0] if lo_result.full_name else "Tim")

        # If no loan, try to get LO from lead
        elif lead_id:
            lo_result = db.execute(text("""
                SELECT u.full_name, u.first_name, u.email, u.phone
                FROM leads l
                LEFT JOIN users u ON u.id = l.owner_id
                WHERE l.id = :lead_id
            """), {"lead_id": lead_id}).fetchone()
            if lo_result:
                lo_name = lo_result.first_name or (lo_result.full_name.split()[0] if lo_result.full_name else "Tim")

        logger.info(f"Using LO name: {lo_name} for conversation {conversation_id}")

        # =================================================================
        # Use consolidated AI service with Trust-First Architecture
        # =================================================================
        result = ai_service.generate_email_response_sync(
            conversation_id=conversation_id,
            user_message=user_message,
            conversation_history=conversation_history,
            loan_context=loan_context,
            additional_context=context or "",
            lo_name=lo_name,
            lo_available_times=lo_available_times
        )

        ai_response = result.get("text", "Thank you for your message.")
        phase = result.get("trust_phase", 1)
        turn_count = result.get("turn_count", 0)

        # Format response email
        reply_subject = f"Re: {subject}" if not subject.startswith("Re:") else subject

        html_response = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <p>{ai_response.replace(chr(10), '<br>')}</p>

            <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee;">
                <p style="font-size: 13px; color: #666;">
                    This response was generated by our AI assistant. For complex questions
                    or to speak with your loan officer directly, please call us or reply
                    with "HUMAN" to connect with a team member.
                </p>
            </div>
        </div>
        """

        # Send response
        from email_service import email_service

        reply_to_base = os.getenv("AI_REPLY_EMAIL", "sarah@reply.perenniaai.com")
        # Create tagged reply-to for conversation threading
        if '@' in reply_to_base:
            domain = reply_to_base.split('@')[1]
            tagged_reply_to = f"ai-reply+{conversation_id}@{domain}"
        else:
            tagged_reply_to = reply_to_base

        # Get last message_id for email threading
        last_msg = db.execute(text("""
            SELECT message_id FROM ai_email_messages
            WHERE conversation_id = :conv_id AND direction = 'inbound' AND message_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """), {"conv_id": conversation_id}).fetchone()

        # Generate a new message_id for this response
        new_message_id = f"<{conversation_id}-{uuid.uuid4().hex[:8]}@reply.perenniaai.com>"

        # Build headers with threading support
        email_headers = {
            "Message-ID": new_message_id,
            "X-Conversation-ID": conversation_id,
            "X-AI-Generated": "true"
        }

        # Add In-Reply-To and References for proper email threading
        if last_msg and last_msg.message_id:
            email_headers["In-Reply-To"] = last_msg.message_id
            email_headers["References"] = last_msg.message_id

        success = email_service.send_html_email(
            to_email=user_email,
            subject=reply_subject,
            html_body=html_response,
            plain_text_body=ai_response,
            reply_to=tagged_reply_to,
            headers=email_headers
        )

        if success:
            # Store AI response
            db.execute(text("""
                INSERT INTO ai_email_messages
                (conversation_id, direction, from_email, to_email, subject,
                 body_text, body_html, ai_generated, ai_model, created_at)
                VALUES (:conv_id, 'outbound', :from_email, :to_email, :subject,
                        :body_text, :body_html, true, 'gpt-4o-mini', NOW())
            """), {
                "conv_id": conversation_id,
                "from_email": os.getenv("SENDGRID_FROM_EMAIL", "noreply@mortgagecrm.com"),
                "to_email": user_email,
                "subject": reply_subject,
                "body_text": ai_response,
                "body_html": html_response
            })

            db.execute(text("""
                UPDATE ai_email_conversations
                SET last_message_at = NOW(),
                    message_count = COALESCE(message_count, 0) + 1
                WHERE conversation_id = :conv_id
            """), {"conv_id": conversation_id})

            db.commit()

            logger.info(f"AI response sent for conversation {conversation_id} (phase {phase}, turn {turn_count})")
        else:
            logger.error(f"Failed to send AI response for conversation {conversation_id}")

    except SQLAlchemyError as e:
        import traceback
        logger.error(f"Error generating AI response for {conversation_id}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        db.rollback()
    finally:
        db.close()
