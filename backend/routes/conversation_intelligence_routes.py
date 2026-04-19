"""
Conversation Intelligence API Routes

Unified API for AI-powered conversations across email and SMS channels.
Provides endpoints for:
- Processing messages through the QualificationAgent
- Getting conversation state and summaries
- Managing conversation settings
- Testing tone analysis
"""

import html as html_mod
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Database
from database import get_db

# Services
from services.conversation_intelligence import (
    get_conversation_service,
    process_inbound_message,
    get_tone_analysis,
    extract_lead_data,
    Channel
)

# Agent
from sqlalchemy.exc import SQLAlchemyError
from agents.qualification_agent import (
    QualificationAgent,
    create_qualification_agent,
    process_qualification_message
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversation-intelligence", tags=["Conversation Intelligence"])


def _get_current_user():
    """Lazy import to avoid circular dependency."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ProcessMessageRequest(BaseModel):
    """Request to process an inbound message."""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    message: str = Field(..., description="The message text to process")
    channel: str = Field(..., description="Channel: 'email' or 'sms'")
    sender_info: Optional[Dict[str, Any]] = Field(None, description="Optional sender details")
    organization_id: Optional[int] = Field(None, description="Organization ID for white-label")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class ProcessMessageResponse(BaseModel):
    """Response from message processing."""
    conversation_id: str
    channel: str
    response: str
    response_type: str
    should_send: bool
    should_escalate: bool
    escalation_reason: Optional[str]
    qualification: Dict[str, Any]
    tone_analysis: Dict[str, Any]
    conversation_state: Dict[str, Any]
    next_action: str


class ToneAnalysisRequest(BaseModel):
    """Request for tone analysis."""
    text: str = Field(..., description="Text to analyze")


class ToneAnalysisResponse(BaseModel):
    """Response from tone analysis."""
    emotional_state: Dict[str, Any]
    communication_style: Dict[str, Any]
    sentiment: Dict[str, Any]
    urgency: Dict[str, Any]
    risk_level: str
    response_guidance: Dict[str, Any]


class ConversationSummaryResponse(BaseModel):
    """Summary of a conversation's state."""
    conversation_id: str
    channel: str
    stage: str
    message_count: int
    qualification: Dict[str, Any]
    tone: Dict[str, Any]
    objections: Dict[str, Any]
    ai_enabled: bool
    escalation_reason: Optional[str]


class ExtractDataRequest(BaseModel):
    """Request to extract qualification data from text."""
    text: str = Field(..., description="Text to extract data from")


class CreateLeadRequest(BaseModel):
    """Request to create a lead from conversation."""
    conversation_id: str = Field(..., description="Conversation to create lead from")


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/process", response_model=ProcessMessageResponse)
async def process_message(
    request: ProcessMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """
    Process an inbound message through the QualificationAgent.

    This is the main entry point for AI-powered conversations.
    It analyzes the message, extracts qualification data, and generates
    an appropriate response.

    The response includes:
    - AI-generated response text
    - Tone analysis (emotion, sentiment, urgency)
    - Qualification progress
    - Next recommended action
    """
    try:
        # Get organization for white-label (if provided)
        organization = None
        if request.organization_id:
            org_result = db.execute(text("""
                SELECT id, name, settings FROM organizations WHERE id = :org_id
            """), {"org_id": request.organization_id}).fetchone()
            if org_result:
                organization = {
                    "id": org_result[0],
                    "name": org_result[1],
                    "settings": org_result[2] or {}
                }

        # Process through qualification agent
        result = process_qualification_message(
            conversation_id=request.conversation_id,
            message=request.message,
            channel=request.channel,
            sender_info=request.sender_info,
            organization=organization
        )

        # Log processing (async)
        background_tasks.add_task(
            log_conversation_processing,
            conversation_id=request.conversation_id,
            channel=request.channel,
            result=result
        )

        return ProcessMessageResponse(
            conversation_id=result["conversation_id"],
            channel=result["channel"],
            response=result["response"],
            response_type=result["response_type"],
            should_send=result["should_send"],
            should_escalate=result["should_escalate"],
            escalation_reason=result.get("escalation_reason"),
            qualification=result["qualification"],
            tone_analysis=result["tone_analysis"],
            conversation_state=result["conversation_state"],
            next_action=result["next_action"]
        )

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/analyze-tone", response_model=ToneAnalysisResponse)
async def analyze_tone_endpoint(
    request: ToneAnalysisRequest,
    current_user=Depends(_get_current_user()),
):
    """
    Analyze the tone of a text message.

    Returns detailed analysis including:
    - Emotional state (angry, frustrated, excited, etc.)
    - Communication style (formal, casual, urgent, etc.)
    - Sentiment intensity (very negative to very positive)
    - Urgency level (critical, high, medium, low)
    - Response guidance
    """
    try:
        analysis = get_tone_analysis(request.text)
        return ToneAnalysisResponse(**analysis)
    except Exception as e:
        logger.error(f"Error analyzing tone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/conversation/{conversation_id}", response_model=ConversationSummaryResponse)
async def get_conversation_summary(
    conversation_id: str,
    current_user=Depends(_get_current_user()),
):
    """
    Get a summary of a conversation's current state.

    Returns:
    - Qualification progress and collected data
    - Tone history and trends
    - Objection count and types
    - Current stage and AI status
    """
    try:
        service = get_conversation_service()
        summary = service.get_conversation_summary(conversation_id)

        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])

        return ConversationSummaryResponse(**summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/extract-data")
async def extract_data_from_text(
    request: ExtractDataRequest,
    current_user=Depends(_get_current_user()),
):
    """
    Extract qualification data from text without conversation context.

    Useful for:
    - Processing form submissions
    - Extracting data from notes
    - Testing extraction logic
    """
    try:
        data = extract_lead_data(request.text)
        return {
            "extracted_data": data,
            "completion_percentage": data.get("completion_percentage", 0),
            "missing_fields": data.get("missing_required", [])
        }
    except Exception as e:
        logger.error(f"Error extracting data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conversation/{conversation_id}/create-lead")
async def create_lead_from_conversation(
    conversation_id: str,
    owner_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """
    Create a lead record from the qualification data collected in a conversation.

    This should be called after qualification is complete (or at booking stage)
    to persist the collected data to the leads table.

    Args:
        conversation_id: The conversation ID to create a lead from
        owner_id: Optional owner (loan officer) ID to assign the lead to
    """
    # Lazy import to avoid circular import
    from database.enums import LeadStage
    from database.models import Lead

    try:
        agent = create_qualification_agent()
        lead_data = agent.generate_lead_from_qualification(conversation_id)

        if "error" in lead_data:
            raise HTTPException(status_code=404, detail=lead_data["error"])

        # Check if lead already exists by email or phone
        existing_lead = None
        if lead_data.get("email"):
            existing_lead = db.query(Lead).filter(
                Lead.email == lead_data["email"]
            ).first()
        if not existing_lead and lead_data.get("phone"):
            # Clean phone and search
            phone = lead_data["phone"]
            phone_clean = ''.join(c for c in phone if c.isdigit())
            if len(phone_clean) >= 10:
                existing_lead = db.query(Lead).filter(
                    Lead.phone.contains(phone_clean[-10:])
                ).first()

        if existing_lead:
            # Update existing lead with new qualification data
            if lead_data.get("first_name"):
                existing_lead.first_name = lead_data["first_name"]
            if lead_data.get("last_name"):
                existing_lead.last_name = lead_data["last_name"]
            if lead_data.get("first_name") and lead_data.get("last_name"):
                existing_lead.name = f"{lead_data['first_name']} {lead_data['last_name']}"
            if lead_data.get("email"):
                existing_lead.email = lead_data["email"]
            if lead_data.get("phone"):
                existing_lead.phone = lead_data["phone"]
            if lead_data.get("property_type"):
                existing_lead.property_type = lead_data["property_type"]
            if lead_data.get("estimated_amount"):
                existing_lead.loan_amount = lead_data["estimated_amount"]
            if lead_data.get("first_time_buyer") is not None:
                existing_lead.first_time_buyer = lead_data["first_time_buyer"]
            if lead_data.get("closing_timeline"):
                existing_lead.notes = f"Timeline: {lead_data['closing_timeline']}\n{existing_lead.notes or ''}"

            # Update stage if qualified
            if lead_data.get("qualification_complete"):
                if existing_lead.stage in [LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT, LeadStage.PROSPECT]:
                    existing_lead.stage = LeadStage.PRE_QUALIFIED

            existing_lead.last_contact = datetime.now(timezone.utc)
            existing_lead.ai_score = min(100, (existing_lead.ai_score or 50) + 10)

            # Detect if stage changed for workflow trigger
            _stage_changed_to_pq = lead_data.get("qualification_complete") and existing_lead.stage == LeadStage.PRE_QUALIFIED

            db.commit()
            db.refresh(existing_lead)

            # Event-driven workflow enrollment if stage changed (eliminates 60s polling delay)
            if _stage_changed_to_pq:
                try:
                    from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
                    trigger_workflow_evaluation_for_lead(
                        db, existing_lead.id, 'Pre-Qualified',
                        lead_source=getattr(existing_lead, 'source', None),
                    )
                except Exception as wf_err:
                    logger.warning(f"Workflow evaluation trigger failed for conversation lead {existing_lead.id}: {wf_err}")

            logger.info(f"Updated existing lead {existing_lead.id} from conversation {conversation_id}")

            return {
                "status": "success",
                "message": "Existing lead updated with qualification data",
                "lead_id": existing_lead.id,
                "is_new": False,
                "lead": {
                    "id": existing_lead.id,
                    "name": existing_lead.name,
                    "email": existing_lead.email,
                    "phone": existing_lead.phone,
                    "stage": existing_lead.stage.value if existing_lead.stage else None,
                    "ai_score": existing_lead.ai_score,
                    "qualification_percentage": lead_data.get("qualification_percentage", 0),
                }
            }

        # Create new lead
        first_name = lead_data.get("first_name") or ""
        last_name = lead_data.get("last_name") or ""
        name = f"{first_name} {last_name}".strip() or "Unknown"

        # Determine initial stage based on qualification
        if lead_data.get("qualification_complete"):
            stage = LeadStage.PRE_QUALIFIED
        elif lead_data.get("qualification_percentage", 0) >= 50:
            stage = LeadStage.PROSPECT
        else:
            stage = LeadStage.NEW

        new_lead = Lead(
            name=name,
            first_name=first_name or None,
            last_name=last_name or None,
            email=lead_data.get("email"),
            phone=lead_data.get("phone"),
            source=lead_data.get("source", "ai_conversation"),
            stage=stage,
            property_type=lead_data.get("property_type"),
            loan_amount=lead_data.get("estimated_amount"),
            first_time_buyer=lead_data.get("first_time_buyer", False),
            owner_id=owner_id,
            ai_score=70 if lead_data.get("qualification_complete") else 50,
            notes=f"Created from AI conversation {conversation_id}\n"
                  f"Channel: {lead_data.get('channel', 'unknown')}\n"
                  f"Qualification: {lead_data.get('qualification_percentage', 0)}%\n"
                  f"Timeline: {lead_data.get('closing_timeline', 'not specified')}",
            lead_received_date=datetime.now(timezone.utc),
            last_contact=datetime.now(timezone.utc),
        )

        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

        logger.info(f"Created new lead {new_lead.id} from conversation {conversation_id}")

        return {
            "status": "success",
            "message": "Lead created from conversation",
            "lead_id": new_lead.id,
            "is_new": True,
            "lead": {
                "id": new_lead.id,
                "name": new_lead.name,
                "email": new_lead.email,
                "phone": new_lead.phone,
                "stage": new_lead.stage.value if new_lead.stage else None,
                "ai_score": new_lead.ai_score,
                "qualification_percentage": lead_data.get("qualification_percentage", 0),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conversation/{conversation_id}/toggle-ai")
async def toggle_conversation_ai(
    conversation_id: str,
    enabled: bool = True,
    current_user=Depends(_get_current_user()),
):
    """
    Enable or disable AI responses for a conversation.

    When disabled, messages will still be analyzed but no auto-responses
    will be generated.
    """
    try:
        service = get_conversation_service()
        state = service._conversation_cache.get(conversation_id)

        if not state:
            raise HTTPException(status_code=404, detail="Conversation not found")

        state.ai_enabled = enabled

        return {
            "conversation_id": conversation_id,
            "ai_enabled": enabled,
            "message": f"AI {'enabled' if enabled else 'disabled'} for conversation"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling AI: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_conversation_stats(
    current_user=Depends(_get_current_user()),
):
    """
    Get statistics about active conversations.
    """
    try:
        service = get_conversation_service()
        cache = service._conversation_cache

        stats = {
            "active_conversations": len(cache),
            "by_channel": {},
            "by_stage": {},
            "by_qualification_status": {},
            "total_messages": 0,
            "total_objections": 0
        }

        for conv_id, state in cache.items():
            # By channel
            channel = state.channel.value
            stats["by_channel"][channel] = stats["by_channel"].get(channel, 0) + 1

            # By stage
            stage = state.stage.value
            stats["by_stage"][stage] = stats["by_stage"].get(stage, 0) + 1

            # By qualification status
            q_status = state.qualification_status.value
            stats["by_qualification_status"][q_status] = stats["by_qualification_status"].get(q_status, 0) + 1

            # Totals
            stats["total_messages"] += state.message_count
            stats["total_objections"] += state.objection_count

        return stats
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# EMAIL INTEGRATION ENDPOINT
# =============================================================================

@router.post("/webhook/email")
async def process_email_webhook(
    request: Request,
    email_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for incoming emails.

    Integrates with Microsoft Graph webhooks to process
    inbound emails through the QualificationAgent.
    """
    # Webhook security: Legacy webhook_security module removed.
    # Telnyx webhook validation is handled in telnyx_webhook_routes.py.
    logger.info("Conversation intelligence webhook received (legacy signature validation removed)")

    try:
        # Extract email details
        subject = email_data.get("subject", "")
        body = email_data.get("body", {}).get("content", "") or email_data.get("body", "")
        from_email = email_data.get("from", {}).get("emailAddress", {}).get("address", "")
        from_name = email_data.get("from", {}).get("emailAddress", {}).get("name", "")
        message_id = email_data.get("id", "")
        conversation_id = email_data.get("conversationId", message_id)

        # Combine subject and body for analysis
        full_message = f"Subject: {subject}\n\n{body}"

        # Process through qualification agent
        result = process_qualification_message(
            conversation_id=f"email_{conversation_id}",
            message=full_message,
            channel="email",
            sender_info={
                "email": from_email,
                "first_name": from_name.split()[0] if from_name else None
            }
        )

        # If we should send a response, queue it
        if result["should_send"] and result.get("response"):
            background_tasks.add_task(
                send_email_response,
                to_email=from_email,
                subject=f"Re: {subject}",
                body=result["response"],
                conversation_id=conversation_id
            )

        return {
            "status": "processed",
            "conversation_id": conversation_id,
            "response_queued": result["should_send"],
            "qualification_progress": result["qualification"]["completion_percentage"],
            "next_action": result["next_action"]
        }

    except Exception as e:
        logger.error(f"Error processing email webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# SMS INTEGRATION ENDPOINT
# =============================================================================

@router.post("/webhook/sms")
async def process_sms_webhook(
    request: Request,
    sms_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for incoming SMS messages.

    Integrates with telephony webhooks to process
    inbound SMS through the QualificationAgent.
    """
    # Webhook security: Legacy webhook_security module removed.
    # Telnyx webhook validation is handled in telnyx_webhook_routes.py.
    logger.info("Conversation intelligence webhook received (legacy signature validation removed)")

    try:
        # Extract SMS details (form-encoded format)
        message_body = sms_data.get("Body", "")
        from_number = sms_data.get("From", "")
        to_number = sms_data.get("To", "")
        message_sid = sms_data.get("MessageSid", "")

        # Use phone number as conversation ID
        conversation_id = f"sms_{from_number.replace('+', '')}"

        # Process through qualification agent
        result = process_qualification_message(
            conversation_id=conversation_id,
            message=message_body,
            channel="sms",
            sender_info={
                "phone": from_number
            }
        )

        # If we should send a response, queue it
        if result["should_send"] and result.get("response"):
            background_tasks.add_task(
                send_sms_response,
                to_number=from_number,
                message=result["response"],
                conversation_id=conversation_id
            )

        return {
            "status": "processed",
            "conversation_id": conversation_id,
            "response_queued": result["should_send"],
            "qualification_progress": result["qualification"]["completion_percentage"],
            "next_action": result["next_action"]
        }

    except Exception as e:
        logger.error(f"Error processing SMS webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def log_conversation_processing(
    conversation_id: str,
    channel: str,
    result: Dict[str, Any]
):
    """Log conversation processing for analytics."""
    try:
        logger.info(
            f"Processed {channel} conversation {conversation_id}: "
            f"stage={result['conversation_state']['stage']}, "
            f"qualification={result['qualification']['completion_percentage']}%"
        )

        # Store in analytics table
        from database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("""
                INSERT INTO conversation_analytics (
                    conversation_id, channel, stage, qualification_percentage,
                    response_type, should_escalate, tone_sentiment, processed_at
                ) VALUES (
                    :conv_id, :channel, :stage, :qual_pct,
                    :resp_type, :escalate, :sentiment, CURRENT_TIMESTAMP
                )
            """), {
                "conv_id": conversation_id,
                "channel": channel,
                "stage": result['conversation_state']['stage'],
                "qual_pct": result['qualification']['completion_percentage'],
                "resp_type": result.get('response_type'),
                "escalate": result.get('should_escalate', False),
                "sentiment": result['tone_analysis'].get('sentiment', {}).get('sentiment_category')
            })
            db.commit()
        except Exception as db_err:
            logger.warning(f"Could not store analytics (table may not exist): {db_err}")
        finally:
            db.close()
    except SQLAlchemyError as e:
        logger.error(f"Error logging conversation: {e}")


async def send_email_response(
    to_email: str,
    subject: str,
    body: str,
    conversation_id: str
):
    """Send email response via Microsoft Graph or NotificationService."""
    try:
        # Try Microsoft Graph first for authenticated users
        from integrations.microsoft_graph import MicrosoftGraphClient
        graph_client = MicrosoftGraphClient()

        if graph_client.enabled:
            result = await graph_client.send_email(
                to_email=to_email,
                subject=subject,
                body=body
            )
            logger.info(f"Email sent via Microsoft Graph to {to_email} for conversation {conversation_id}")
            return result
        else:
            # Fallback to NotificationService (SendGrid)
            from services.notification_service import NotificationService
            notification_service = NotificationService()
            result = notification_service.send_email(
                to_email=to_email,
                subject=subject,
                html_content=f"<div style='font-family: Arial, sans-serif;'>{html_mod.escape(body).replace(chr(10), '<br>')}</div>"
            )
            logger.info(f"Email sent via SendGrid to {to_email} for conversation {conversation_id}")
            return result
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        raise


async def send_sms_response(
    to_number: str,
    message: str,
    conversation_id: str
):
    """Send SMS response via telephony provider."""
    try:
        from integrations.sms_service import get_sms_client
        sms_client = get_sms_client()

        if sms_client.enabled:
            message_sid = sms_client.send_sms(
                to_number=to_number,
                message=message
            )
            logger.info(f"SMS sent to {to_number} for conversation {conversation_id}, SID: {message_sid}")
            return message_sid
        else:
            # Fallback to NotificationService which may have alternative SMS provider
            from services.notification_service import NotificationService
            notification_service = NotificationService()
            result = notification_service.send_sms(
                to_phone=to_number,
                message=message
            )
            logger.info(f"SMS sent via NotificationService to {to_number} for conversation {conversation_id}")
            return result
    except Exception as e:
        logger.error(f"Error sending SMS to {to_number}: {e}")
        raise
