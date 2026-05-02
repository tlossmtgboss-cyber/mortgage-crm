"""
Chat State Machine API Routes - Production Version

FastAPI routes for the phase-based chat system:
- Session management (create, get, end)
- Message handling with AI responses
- Click-to-call integration
- Analytics and state inspection
- Sensitive data guardrails
- Business hours validation
"""

import os
import time
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session

from database import get_db
from routes.auth_deps import require_auth
from chat_state_machine_models import (
    ChatSession, ChatMessage, CallRequest,
    ChatPhase, UrgencyLevel, CTAType, CallStatus
)
from services.chat_session_manager import ChatSessionManager
from services.chat_prompt_constructor import (
    PromptConstructor, create_prompt_constructor_for_microsite,
    get_phase_appropriate_greeting, get_fallback_response
)

# Production guardrails - import with fallbacks
try:
    from services.sensitive_data_detector import SensitiveDataDetector
except ImportError:
    SensitiveDataDetector = None

try:
    from services.enhanced_intent_detector import EnhancedIntentDetector, intent_detector
except ImportError:
    EnhancedIntentDetector = None
    intent_detector = None

try:
    from services.phase_transition_validator import PhaseTransitionValidator, CTASelector
except ImportError:
    PhaseTransitionValidator = None
    CTASelector = None

try:
    from services.business_hours import BusinessHoursValidator
except ImportError:
    BusinessHoursValidator = None

try:
    from services.chat_analytics import ChatAnalytics, get_analytics_summary
except ImportError:
    ChatAnalytics = None
    get_analytics_summary = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat State Machine"], dependencies=[Depends(require_auth)])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class SessionCreateRequest(BaseModel):
    visitor_id: str = Field(..., description="Unique visitor identifier")
    microsite_id: Optional[int] = Field(None, description="Microsite ID if on LO site")
    source_url: Optional[str] = Field(None, description="Page URL where chat started")


class SessionResponse(BaseModel):
    id: str
    visitor_id: str
    current_phase: int
    phase_name: str
    turn_count: int
    intent_score: int
    urgency: str
    intent_signals: List[dict]
    is_active: bool
    greeting_message: Optional[str] = None

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    user_message: dict
    assistant_message: dict
    session_state: dict
    cta_recommendation: Optional[str] = None


class CallRequestCreate(BaseModel):
    phone: str = Field(..., description="Caller phone number")
    name: Optional[str] = Field(None, description="Caller name")
    is_immediate: bool = Field(True, description="True for click-to-call, False for scheduled")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled time for callback")
    preferred_time_slot: Optional[str] = Field(None, description="Preferred time slot")


class CallRequestResponse(BaseModel):
    id: str
    status: str
    direction: str
    is_immediate: bool
    scheduled_at: Optional[str] = None
    whisper_message: Optional[str] = None


class CTAResponseRequest(BaseModel):
    message_id: str = Field(..., description="ID of message with CTA")
    response: str = Field(..., description="accepted or declined")


# =============================================================================
# AI INTEGRATION
# =============================================================================

async def generate_ai_response(
    prompt_constructor: PromptConstructor,
    context: dict,
    user_message: str,
) -> tuple[str, dict]:
    """
    Generate AI response using Claude/OpenAI.

    Returns tuple of (response_text, metadata)
    """
    import anthropic

    # Build the system prompt
    system_prompt = prompt_constructor.build_system_prompt(context)

    # Build conversation messages
    messages = []
    for msg in context.get('conversation_history', [])[-10:]:  # Last 10 messages
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })

    # Add current user message
    messages.append({
        "role": "user",
        "content": user_message
    })

    # Call Claude API
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, using fallback response")
        return get_fallback_response(context.get('current_phase', 1), context), {"model": "fallback"}

    try:
        start_time = time.time()

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        content = response.content[0].text if response.content else ""
        metadata = {
            "model": response.model,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            "response_time_ms": response_time_ms,
        }

        return content, metadata

    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        return get_fallback_response(context.get('current_phase', 1), context), {"model": "fallback", "error": "Internal server error"}


# =============================================================================
# SESSION ROUTES
# =============================================================================

@router.post("/sessions", response_model=SessionResponse)
async def create_or_resume_session(
    request: SessionCreateRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """
    Create a new chat session or resume an existing one for a visitor.

    Returns session state and an initial greeting message.
    """
    manager = ChatSessionManager(db)

    # Extract request metadata
    user_agent = req.headers.get("user-agent")
    ip_address = req.client.host if req.client else None

    # Get or create session
    session = manager.get_or_create_session(
        visitor_id=request.visitor_id,
        microsite_id=request.microsite_id,
        source_url=request.source_url,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    # Get LO name for greeting if we have microsite context
    lo_name = None
    if request.microsite_id:
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT u.full_name FROM microsites m
            JOIN users u ON u.id = m.user_id
            WHERE m.id = :microsite_id
        """), {"microsite_id": request.microsite_id}).first()
        if result:
            lo_name = result.full_name

    # Generate greeting for new sessions
    greeting = None
    if session.turn_count == 0:
        greeting = get_phase_appropriate_greeting(session.current_phase, lo_name)

    # Get phase name
    from chat_state_machine_models import get_phase_description
    phase_info = get_phase_description(session.current_phase)

    return {
        "id": str(session.id),
        "visitor_id": session.visitor_id,
        "current_phase": session.current_phase,
        "phase_name": phase_info['name'],
        "turn_count": session.turn_count,
        "intent_score": session.intent_score,
        "urgency": session.urgency,
        "intent_signals": session.intent_signals or [],
        "is_active": session.is_active,
        "greeting_message": greeting,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    include_messages: bool = False,
    db: Session = Depends(get_db),
):
    """Get session details and optionally include message history"""
    manager = ChatSessionManager(db)

    if include_messages:
        session = manager.get_session_with_messages(session_id)
    else:
        session = manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_dict(include_messages=include_messages)


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """End an active chat session"""
    manager = ChatSessionManager(db)
    session = manager.end_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": str(session_id)}


# =============================================================================
# MESSAGE ROUTES
# =============================================================================

@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: UUID,
    request: MessageRequest,
    db: Session = Depends(get_db),
):
    """
    Send a user message and get AI response.

    This is the main chat endpoint with production guardrails:
    1. Sensitive data detection (COMPLIANCE CRITICAL)
    2. Process user message
    3. Enhanced intent detection
    4. Phase transition validation
    5. Generate phase-appropriate AI response
    6. CTA selection based on earned trust
    7. Return both messages and current state
    """
    manager = ChatSessionManager(db)

    # =========================================================================
    # 1. SENSITIVE DATA CHECK - COMPLIANCE CRITICAL
    # =========================================================================
    if SensitiveDataDetector is not None:
        if SensitiveDataDetector.should_block(request.content):
            # Don't process the message - return safety response
            warning_msg = SensitiveDataDetector.get_warning_message(request.content)
            logger.warning(f"Blocked sensitive data in session {session_id}")

            # Get session for state
            session = manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            from chat_state_machine_models import get_phase_description
            phase_info = get_phase_description(session.current_phase)

            return {
                "user_message": {"content": "[Content redacted for security]", "role": "user"},
                "assistant_message": {
                    "content": warning_msg or SensitiveDataDetector.REDACTION_RESPONSE,
                    "role": "assistant",
                    "cta_presented": None,
                },
                "session_state": {
                    "current_phase": session.current_phase,
                    "phase_name": phase_info['name'],
                    "turn_count": session.turn_count,
                    "intent_score": session.intent_score,
                    "urgency": session.urgency,
                    "intent_signals": session.intent_signals or [],
                },
                "cta_recommendation": None,
                "blocked_sensitive_data": True,
            }

    # =========================================================================
    # 2. GET AND VALIDATE SESSION
    # =========================================================================
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is not active")

    # =========================================================================
    # 3. CHECK FOR EXPLICIT CTA REQUEST (bypass normal flow)
    # =========================================================================
    explicit_cta_requested = False
    if PhaseTransitionValidator is not None:
        explicit_cta_requested = PhaseTransitionValidator._is_explicit_cta_request(request.content)
        if explicit_cta_requested:
            logger.info(f"Explicit CTA request detected in session {session_id}")

    # =========================================================================
    # 4. ENHANCED INTENT DETECTION
    # =========================================================================
    detected_intents = []
    urgency_override = None

    if intent_detector is not None:
        # Use enhanced fuzzy matching detector
        intent_result = intent_detector.detect(request.content)
        detected_intents = intent_result.get('signals', [])

        # Check for urgency signals
        if intent_result.get('urgency_boost'):
            urgency_override = 'high'

    # =========================================================================
    # 5. PROCESS USER MESSAGE (saves, detects intents, updates state)
    # =========================================================================
    user_message, session = manager.process_user_message(
        session_id=session_id,
        content=request.content,
        additional_signals=detected_intents,
    )

    # Override urgency if detected
    if urgency_override and session.urgency != 'high':
        session.urgency = urgency_override
        db.commit()

    # =========================================================================
    # 6. PHASE TRANSITION VALIDATION
    # =========================================================================
    current_phase = session.current_phase
    proposed_phase = current_phase

    if PhaseTransitionValidator is not None:
        signal_count = len(session.intent_signals or [])

        # Check for phase reversion after CTA decline
        should_revert, revert_phase = PhaseTransitionValidator.should_revert_phase(
            current_phase=current_phase,
            cta_declined_count=session.cta_declined_count,
        )

        if should_revert:
            proposed_phase = revert_phase
            session.current_phase = proposed_phase
            db.commit()
            logger.info(f"Phase reverted to {proposed_phase} after CTA decline")

        # Check for phase advancement (only advance by 1)
        elif current_phase < 4:
            next_phase = current_phase + 1
            transition_result = PhaseTransitionValidator.can_transition_to(
                target_phase=next_phase,
                current_turn=session.turn_count,
                intent_score=session.intent_score,
                signal_count=signal_count,
                user_message=request.content,
            )

            if transition_result.allowed:
                proposed_phase = next_phase
                session.current_phase = proposed_phase
                db.commit()
                logger.info(f"Phase advanced to {proposed_phase}: {transition_result.reason}")

    # =========================================================================
    # 7. BUILD CONTEXT AND GENERATE AI RESPONSE
    # =========================================================================
    context = manager.build_conversation_context(session)

    # Add phase progress to context
    if PhaseTransitionValidator is not None:
        signal_count = len(session.intent_signals or [])
        context['phase_progress'] = PhaseTransitionValidator.calculate_phase_progress(
            current_phase=session.current_phase,
            turn_count=session.turn_count,
            intent_score=session.intent_score,
            signal_count=signal_count,
        )

    # Create prompt constructor with LO context if available
    if session.microsite_id:
        prompt_constructor = create_prompt_constructor_for_microsite(session.microsite_id, db)
    else:
        prompt_constructor = PromptConstructor()

    # Generate AI response
    ai_response, ai_metadata = await generate_ai_response(
        prompt_constructor=prompt_constructor,
        context=context,
        user_message=request.content,
    )

    # =========================================================================
    # 8. CTA SELECTION (using deterministic selector)
    # =========================================================================
    cta_to_present = None
    cta_framing = None
    business_hours_status = None

    # Get business hours status
    if BusinessHoursValidator is not None:
        try:
            if session.loan_officer_id:
                bh_validator = BusinessHoursValidator.for_loan_officer(session.loan_officer_id, db)
            else:
                bh_validator = BusinessHoursValidator()
            business_hours_status = bh_validator.get_availability_status()
        except Exception as e:
            logger.error(f"Business hours check failed: {e}")
            business_hours_status = {'available': True}  # Default to available

    # Honor explicit CTA requests
    if explicit_cta_requested:
        cta_to_present = 'call_now' if (business_hours_status and business_hours_status.get('available')) else 'schedule'
        cta_framing = "Absolutely! Let me connect you right away." if cta_to_present == 'call_now' else "Let's find a time that works for you."

    # Normal CTA selection based on phase
    elif session.current_phase >= 4 and CTASelector is not None:
        signal_types = [s.get('signal') for s in (session.intent_signals or []) if s.get('signal')]

        cta_type, framing = CTASelector.select_cta(
            intent_signals=signal_types,
            urgency=session.urgency,
            phase=session.current_phase,
            conversation_context=request.content,
            cta_declined_count=session.cta_declined_count,
        )

        if cta_type:
            # Respect business hours for call_now
            if cta_type == 'call_now' and business_hours_status and not business_hours_status.get('available'):
                cta_to_present = 'schedule'
                cta_framing = f"Tim is {business_hours_status.get('message', 'currently unavailable')}. Schedule a time that works for you."
            else:
                cta_to_present = cta_type
                cta_framing = framing

    # Soft CTA in Phase 3 (only if high intent)
    elif session.current_phase == 3 and session.intent_score >= 70:
        cta_to_present = 'schedule'
        cta_framing = "When you're ready, I'd be happy to set up a time to chat."

    # =========================================================================
    # 9. SAVE ASSISTANT MESSAGE
    # =========================================================================
    assistant_message = manager.save_assistant_message(
        session_id=session_id,
        content=ai_response,
        cta_presented=cta_to_present,
        model_used=ai_metadata.get('model'),
        tokens_used=ai_metadata.get('tokens_used'),
        response_time_ms=ai_metadata.get('response_time_ms'),
    )

    # Mark CTA as offered on session
    if cta_to_present and not session.cta_offered:
        session.cta_offered = cta_to_present
        db.commit()

    # Refresh session for latest state
    db.refresh(session)

    # =========================================================================
    # 10. BUILD RESPONSE
    # =========================================================================
    from chat_state_machine_models import get_phase_description
    phase_info = get_phase_description(session.current_phase)

    response_data = {
        "user_message": user_message.to_dict(),
        "assistant_message": assistant_message.to_dict(),
        "session_state": {
            "current_phase": session.current_phase,
            "phase_name": phase_info['name'],
            "phase_objective": phase_info.get('objective', ''),
            "turn_count": session.turn_count,
            "intent_score": session.intent_score,
            "urgency": session.urgency,
            "intent_signals": session.intent_signals or [],
        },
        "cta_recommendation": cta_to_present,
    }

    # Add CTA details if presenting
    if cta_to_present:
        response_data["cta_details"] = {
            "type": cta_to_present,
            "framing": cta_framing,
            "business_hours": business_hours_status,
        }

        # Add button config if CTASelector available
        if CTASelector is not None:
            response_data["cta_details"]["button_config"] = CTASelector.get_cta_button_config(cta_to_present)

    # Add phase progress if available
    if 'phase_progress' in context:
        response_data["phase_progress"] = context['phase_progress']

    return response_data


@router.post("/sessions/{session_id}/cta-response")
async def record_cta_response(
    session_id: UUID,
    request: CTAResponseRequest,
    db: Session = Depends(get_db),
):
    """Record user's response to a CTA (accepted/declined)"""
    manager = ChatSessionManager(db)

    if request.response not in ['accepted', 'declined']:
        raise HTTPException(status_code=400, detail="Response must be 'accepted' or 'declined'")

    try:
        message_id = UUID(request.message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message_id format")

    session = manager.record_cta_response(
        session_id=session_id,
        message_id=message_id,
        response=request.response,
    )

    return {
        "success": True,
        "cta_accepted": session.cta_accepted,
        "cta_declined_count": session.cta_declined_count,
    }


# =============================================================================
# CONTACT INFO ROUTES
# =============================================================================

class ContactInfoRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


@router.post("/sessions/{session_id}/contact")
async def update_contact_info(
    session_id: UUID,
    request: ContactInfoRequest,
    db: Session = Depends(get_db),
):
    """Update session with collected contact information"""
    manager = ChatSessionManager(db)

    session = manager.update_contact_info(
        session_id=session_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
    )

    return {
        "success": True,
        "contact_info": {
            "name": session.contact_name,
            "email": session.contact_email,
            "phone": session.contact_phone,
        }
    }


# =============================================================================
# CALL REQUEST ROUTES
# =============================================================================

@router.post("/sessions/{session_id}/call-request", response_model=CallRequestResponse)
async def create_call_request(
    session_id: UUID,
    request: CallRequestCreate,
    db: Session = Depends(get_db),
):
    """
    Create a call request for click-to-call or scheduled callback.

    For immediate calls (is_immediate=True):
    - Initiates Telnyx click-to-call flow
    - Returns call request ID for status polling

    For scheduled callbacks:
    - Creates callback request for specified time
    - Loan officer will be notified
    """
    manager = ChatSessionManager(db)

    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    call_request = manager.create_call_request(
        session_id=session_id,
        caller_phone=request.phone,
        caller_name=request.name,
        is_immediate=request.is_immediate,
        scheduled_at=request.scheduled_at,
        preferred_time_slot=request.preferred_time_slot,
    )

    # If immediate, trigger Telnyx click-to-call
    if request.is_immediate:
        try:
            from services.click_to_call_service import ClickToCallService
            click_service = ClickToCallService(db)
            call_result = click_service.initiate_call(call_request.id)
            if call_result.get("success"):
                logger.info(f"Click-to-call initiated for session {session_id}: {call_result.get('call_sid')}")
            else:
                logger.warning(f"Click-to-call failed for session {session_id}: {call_result.get('error')}")
        except ImportError:
            logger.warning("ClickToCallService not available - call request created but not initiated")
        except Exception as e:
            logger.error(f"Click-to-call error for session {session_id}: {e}")

    return {
        "id": str(call_request.id),
        "status": call_request.status,
        "direction": call_request.direction,
        "is_immediate": call_request.is_immediate,
        "scheduled_at": call_request.scheduled_at.isoformat() if call_request.scheduled_at else None,
        "whisper_message": call_request.whisper_message,
    }


@router.get("/call-requests/{call_id}/status")
async def get_call_status(
    call_id: UUID,
    db: Session = Depends(get_db),
):
    """Get current status of a call request"""
    call = db.query(CallRequest).filter(CallRequest.id == call_id).first()

    if not call:
        raise HTTPException(status_code=404, detail="Call request not found")

    return {
        "id": str(call.id),
        "status": call.status,
        "initiated_at": call.initiated_at.isoformat() if call.initiated_at else None,
        "connected_at": call.connected_at.isoformat() if call.connected_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.call_duration_seconds,
    }


# =============================================================================
# ANALYTICS ROUTES
# =============================================================================

@router.get("/sessions/{session_id}/stats")
async def get_session_stats(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Get analytics for a chat session"""
    manager = ChatSessionManager(db)
    stats = manager.get_session_stats(session_id)

    if not stats:
        raise HTTPException(status_code=404, detail="Session not found")

    return stats


@router.get("/analytics/summary")
async def get_chat_analytics(
    microsite_id: Optional[int] = None,
    loan_officer_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get aggregate chat analytics"""
    # Use enhanced ChatAnalytics if available
    if get_analytics_summary is not None:
        try:
            return get_analytics_summary(
                db=db,
                days=days,
                microsite_id=microsite_id,
                loan_officer_id=loan_officer_id,
            )
        except Exception as e:
            logger.error(f"Enhanced analytics failed, falling back: {e}")

    # Fallback to basic analytics
    from sqlalchemy import text, func
    from datetime import timedelta

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Build filter conditions
    filters = ["created_at >= :cutoff_date"]
    params = {"cutoff_date": cutoff_date}

    if microsite_id:
        filters.append("microsite_id = :microsite_id")
        params["microsite_id"] = microsite_id
    if loan_officer_id:
        filters.append("loan_officer_id = :loan_officer_id")
        params["loan_officer_id"] = loan_officer_id

    where_clause = " AND ".join(filters)

    # Aggregate stats
    result = db.execute(text(f"""
        SELECT
            COUNT(*) as total_sessions,
            AVG(turn_count) as avg_turns,
            AVG(intent_score) as avg_intent_score,
            COUNT(CASE WHEN cta_accepted THEN 1 END) as cta_accepted_count,
            COUNT(CASE WHEN converted_to_lead THEN 1 END) as conversions,
            COUNT(CASE WHEN current_phase = 4 THEN 1 END) as reached_phase_4
        FROM chat_sessions
        WHERE {where_clause}
    """), params).first()

    # Phase distribution
    phase_dist = db.execute(text(f"""
        SELECT current_phase, COUNT(*) as count
        FROM chat_sessions
        WHERE {where_clause}
        GROUP BY current_phase
        ORDER BY current_phase
    """), params).fetchall()

    # Urgency distribution
    urgency_dist = db.execute(text(f"""
        SELECT urgency, COUNT(*) as count
        FROM chat_sessions
        WHERE {where_clause}
        GROUP BY urgency
    """), params).fetchall()

    return {
        "period_days": days,
        "total_sessions": result.total_sessions or 0,
        "avg_turns": round(float(result.avg_turns or 0), 1),
        "avg_intent_score": round(float(result.avg_intent_score or 0), 1),
        "cta_acceptance_rate": round(
            (result.cta_accepted_count / result.total_sessions * 100)
            if result.total_sessions > 0 else 0, 1
        ),
        "conversion_rate": round(
            (result.conversions / result.total_sessions * 100)
            if result.total_sessions > 0 else 0, 1
        ),
        "phase_4_rate": round(
            (result.reached_phase_4 / result.total_sessions * 100)
            if result.total_sessions > 0 else 0, 1
        ),
        "phase_distribution": {str(p.current_phase): p.count for p in phase_dist},
        "urgency_distribution": {p.urgency: p.count for p in urgency_dist},
    }


@router.get("/analytics/conversion-funnel")
async def get_conversion_funnel(
    microsite_id: Optional[int] = None,
    loan_officer_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get detailed conversion funnel analytics"""
    if ChatAnalytics is None:
        raise HTTPException(status_code=501, detail="Enhanced analytics not available")

    analytics = ChatAnalytics(db)
    return analytics.get_conversion_funnel(
        days=days,
        microsite_id=microsite_id,
        loan_officer_id=loan_officer_id,
    )


@router.get("/analytics/cta-effectiveness")
async def get_cta_effectiveness(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get CTA effectiveness by type"""
    if ChatAnalytics is None:
        raise HTTPException(status_code=501, detail="Enhanced analytics not available")

    analytics = ChatAnalytics(db)
    return {
        "by_type": analytics.get_cta_effectiveness_by_type(days),
        "avg_messages_to_cta": analytics.get_avg_messages_to_cta(days),
    }


@router.get("/analytics/intent-signals")
async def get_intent_signal_distribution(
    microsite_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get distribution of intent signals"""
    if ChatAnalytics is None:
        raise HTTPException(status_code=501, detail="Enhanced analytics not available")

    analytics = ChatAnalytics(db)
    return {
        "distribution": analytics.get_intent_distribution(days, microsite_id),
        "top_converting_signals": analytics.get_top_performing_signals(days),
    }


@router.get("/analytics/phase-dropoff")
async def get_phase_dropoff_analysis(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get phase drop-off analysis"""
    if ChatAnalytics is None:
        raise HTTPException(status_code=501, detail="Enhanced analytics not available")

    analytics = ChatAnalytics(db)
    return analytics.get_phase_drop_off_analysis(days)


@router.get("/analytics/daily-trend")
async def get_daily_session_trend(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get daily session and conversion trend"""
    if ChatAnalytics is None:
        raise HTTPException(status_code=501, detail="Enhanced analytics not available")

    analytics = ChatAnalytics(db)
    return {
        "trend": analytics.get_daily_session_trend(days),
        "session_duration": analytics.get_session_duration_analysis(days),
    }


# =============================================================================
# BUSINESS HOURS ROUTES
# =============================================================================

@router.get("/availability")
async def get_availability_status(
    loan_officer_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get current availability status for click-to-call.

    Returns whether the LO is available now, or when they'll next be available.
    """
    if BusinessHoursValidator is None:
        # Default to always available if not configured
        return {
            "available": True,
            "message": "Available now",
            "next_available": None,
            "call_option": "call_now",
        }

    try:
        if loan_officer_id:
            validator = BusinessHoursValidator.for_loan_officer(loan_officer_id, db)
        else:
            validator = BusinessHoursValidator()

        status = validator.get_availability_status()
        cta_guidance = validator.get_cta_guidance()

        return {
            **status,
            "cta_guidance": cta_guidance,
        }
    except Exception as e:
        logger.error(f"Availability check failed: {e}")
        return {
            "available": True,
            "message": "Available now",
            "next_available": None,
            "call_option": "call_now",
            "error": "Internal server error",
        }


@router.get("/availability/schedule-slots")
async def get_schedule_slots(
    loan_officer_id: Optional[int] = None,
    days_ahead: int = 5,
    db: Session = Depends(get_db),
):
    """
    Get available time slots for scheduling a callback.

    Returns list of available slots for the next N days.
    """
    if BusinessHoursValidator is None:
        raise HTTPException(status_code=501, detail="Business hours not configured")

    try:
        from services.business_hours import CallScheduleHelper

        if loan_officer_id:
            validator = BusinessHoursValidator.for_loan_officer(loan_officer_id, db)
        else:
            validator = BusinessHoursValidator()

        slots = CallScheduleHelper.get_available_slots(
            validator=validator,
            days_ahead=days_ahead,
            slot_duration_minutes=30,
        )

        return {
            "slots": slots,
            "total_available": len(slots),
            "days_ahead": days_ahead,
        }
    except Exception as e:
        logger.error(f"Schedule slots failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def chat_health_check():
    """Health check for chat service"""
    return {
        "status": "healthy",
        "service": "chat_state_machine",
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
    }
