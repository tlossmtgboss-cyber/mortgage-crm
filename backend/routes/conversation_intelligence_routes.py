"""
Conversation Intelligence API Routes

Unified API for AI-powered conversations across email and SMS channels.
Provides endpoints for:
- Processing messages through the QualificationAgent
- Getting conversation state and summaries
- Managing conversation settings
- Testing tone analysis
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
from agents.qualification_agent import (
    QualificationAgent,
    create_qualification_agent,
    process_qualification_message
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversation-intelligence", tags=["Conversation Intelligence"])


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
    db: Session = Depends(get_db)
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
            # TODO: Load organization from database
            pass

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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-tone", response_model=ToneAnalysisResponse)
async def analyze_tone_endpoint(request: ToneAnalysisRequest):
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation/{conversation_id}", response_model=ConversationSummaryResponse)
async def get_conversation_summary(conversation_id: str):
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-data")
async def extract_data_from_text(request: ExtractDataRequest):
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/{conversation_id}/create-lead")
async def create_lead_from_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """
    Create a lead record from the qualification data collected in a conversation.

    This should be called after qualification is complete (or at booking stage)
    to persist the collected data to the leads table.
    """
    try:
        agent = create_qualification_agent()
        lead_data = agent.generate_lead_from_qualification(conversation_id)

        if "error" in lead_data:
            raise HTTPException(status_code=404, detail=lead_data["error"])

        # TODO: Actually insert into leads table
        # For now, return the lead data that would be created

        return {
            "status": "success",
            "message": "Lead data generated from conversation",
            "lead": lead_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/{conversation_id}/toggle-ai")
async def toggle_conversation_ai(
    conversation_id: str,
    enabled: bool = True
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_conversation_stats():
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
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EMAIL INTEGRATION ENDPOINT
# =============================================================================

@router.post("/webhook/email")
async def process_email_webhook(
    email_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for incoming emails.

    Integrates with Microsoft Graph webhooks to process
    inbound emails through the QualificationAgent.
    """
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
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SMS INTEGRATION ENDPOINT
# =============================================================================

@router.post("/webhook/sms")
async def process_sms_webhook(
    sms_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for incoming SMS messages.

    Integrates with Twilio webhooks to process
    inbound SMS through the QualificationAgent.
    """
    try:
        # Extract SMS details (Twilio format)
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
        raise HTTPException(status_code=500, detail=str(e))


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
        # TODO: Store in analytics table
    except Exception as e:
        logger.error(f"Error logging conversation: {e}")


async def send_email_response(
    to_email: str,
    subject: str,
    body: str,
    conversation_id: str
):
    """Send email response via Microsoft Graph."""
    try:
        from services.microsoft_graph import MicrosoftGraphClient
        # TODO: Implement actual email sending
        logger.info(f"Would send email to {to_email}: {subject[:50]}...")
    except Exception as e:
        logger.error(f"Error sending email: {e}")


async def send_sms_response(
    to_number: str,
    message: str,
    conversation_id: str
):
    """Send SMS response via Twilio."""
    try:
        from integrations.twilio_service import TwilioSMSClient
        # TODO: Implement actual SMS sending
        logger.info(f"Would send SMS to {to_number}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
