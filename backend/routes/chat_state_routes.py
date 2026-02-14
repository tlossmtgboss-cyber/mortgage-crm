# backend/routes/chat_state_routes.py
"""
Chat State Machine Routes - FULLY INTEGRATED PRODUCTION VERSION

Implements the 4-phase conversational AI flow:
1. REASSURE: Build trust, establish expertise
2. EDUCATE: Share valuable mortgage knowledge
3. PERSONALIZE: Gather borrower-specific details
4. EARNED_CTA: Offer appropriate next steps

Production features:
- Message deduplication
- Response caching
- Circuit breaker protection
- Quality analysis
- Structured logging
- Sensitive data detection
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import time
import re
import logging

from database import get_db
from services.chat_session_manager import ChatSessionManager
from services.chat_prompt_constructor import PromptConstructor as ChatPromptConstructor
from services.response_cache import ResponseCache
from services.message_deduplication import MessageDeduplicator
from services.conversation_quality import ConversationQualityAnalyzer, get_quality_summary
from services.session_recovery import SessionRecoveryService
from middleware.structured_logging import StructuredLogger, get_structured_logger
from models.chat_state_machine_models import ChatSession, ChatMessage, ConversationPhase
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger()


# =============================================================================
# SCHEMAS
# =============================================================================

class ChatSessionCreate(BaseModel):
    """Create a new chat session."""
    visitor_id: str = Field(..., description="Unique visitor identifier")
    microsite_id: Optional[int] = Field(None, description="Associated microsite ID")
    user_id: Optional[str] = Field(None, description="Authenticated user ID if available")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    user_agent: Optional[str] = Field(None, description="Browser user agent")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatSessionResponse(BaseModel):
    """Chat session response."""
    session_id: int
    visitor_id: str
    current_phase: int
    intent_score: int
    is_new_session: bool
    recovered_from: Optional[str] = None
    greeting: Optional[str] = None


class ChatMessageCreate(BaseModel):
    """Send a message to a chat session."""
    content: str = Field(..., min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    session_id: int
    message: Dict[str, Any]
    cta: Optional[str] = None
    phase: int
    intent_score: int
    cached: bool = False
    processing_time_ms: float


class CTAResponse(BaseModel):
    """CTA response action."""
    action: str = Field(..., description="accepted, declined, deferred")
    cta_type: str = Field(..., description="call_now, schedule, application")
    phone_number: Optional[str] = Field(None, description="Phone for callback")


# =============================================================================
# SENSITIVE DATA DETECTOR
# =============================================================================

class SensitiveDataDetector:
    """Detect and block sensitive data in messages."""

    SSN_PATTERN = r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'
    CREDIT_CARD_PATTERN = r'\b(?:\d{4}[-.\s]?){3}\d{4}\b'
    BANK_ACCOUNT_PATTERN = r'\b\d{8,17}\b'  # Generic account numbers

    REDACTION_RESPONSE = (
        "I noticed you may have included sensitive information like a Social Security "
        "or account number. For your security, please don't share that in chat. "
        "When we connect with Tim, he'll collect any sensitive details through "
        "our secure application process. How can I help you with your mortgage questions?"
    )

    @classmethod
    def should_block(cls, message: str) -> bool:
        """Check if message contains sensitive data that should be blocked."""
        # SSN pattern
        if re.search(cls.SSN_PATTERN, message):
            return True

        # Credit card pattern
        if re.search(cls.CREDIT_CARD_PATTERN, message):
            return True

        return False

    @classmethod
    def detect_all(cls, message: str) -> List[str]:
        """Detect all types of sensitive data."""
        detected = []

        if re.search(cls.SSN_PATTERN, message):
            detected.append("ssn")

        if re.search(cls.CREDIT_CARD_PATTERN, message):
            detected.append("credit_card")

        if re.search(cls.BANK_ACCOUNT_PATTERN, message):
            detected.append("bank_account")

        return detected


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_chat_components(request: Request):
    """Get chat system components from app state."""
    return getattr(request.app.state, 'chat_system', None)


def get_redis_client(request: Request):
    """Get Redis client from app state."""
    components = get_chat_components(request)
    return components.redis_client if components else None


def get_ai_service(request: Request):
    """Get AI service from app state."""
    components = get_chat_components(request)
    return components.ai_service if components else None


# =============================================================================
# SESSION ENDPOINTS
# =============================================================================

@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(
    session_data: ChatSessionCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create or recover a chat session.

    Attempts session recovery if visitor has previous sessions.
    """
    start_time = time.time()

    session_manager = ChatSessionManager(db)
    redis_client = get_redis_client(request)

    # Try session recovery first
    recovered_session = None
    recovery_source = None

    if redis_client:
        try:
            recovery_service = SessionRecoveryService(db, redis_client)
            recovered_session = await recovery_service.recover_or_create_session(
                visitor_id=session_data.visitor_id,
                user_id=session_data.user_id,
                phone=None,  # Could be passed if available
                microsite_id=session_data.microsite_id
            )

            if recovered_session and recovered_session.turn_count > 0:
                recovery_source = "visitor_id"
                logger.info(f"Recovered session {recovered_session.id} for visitor {session_data.visitor_id}")

        except SQLAlchemyError as e:
            logger.warning(f"Session recovery failed: {e}")

    # Create new session if no recovery
    if not recovered_session:
        session = session_manager.create_session(
            visitor_id=session_data.visitor_id,
            microsite_id=session_data.microsite_id,
            metadata={
                "referrer": session_data.referrer,
                "user_agent": session_data.user_agent,
                **(session_data.metadata or {})
            }
        )
        is_new = True
    else:
        session = recovered_session
        is_new = False

    # Generate greeting for new sessions
    greeting = None
    if is_new:
        greeting = (
            "Hi there! I'm here to help you explore your mortgage options. "
            "Whether you're buying your first home, refinancing, or just curious "
            "about current rates, I can help guide you through the process. "
            "What brings you here today?"
        )

    # Log session creation
    structured_logger.log_performance(
        operation="session_create",
        duration_ms=(time.time() - start_time) * 1000,
        success=True,
        metadata={
            "session_id": session.id,
            "visitor_id": session_data.visitor_id,
            "is_new": is_new,
            "recovered": recovery_source is not None
        }
    )

    return ChatSessionResponse(
        session_id=session.id,
        visitor_id=session.visitor_id,
        current_phase=session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
        intent_score=session.intent_score,
        is_new_session=is_new,
        recovered_from=recovery_source,
        greeting=greeting
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get session details and conversation history."""
    session_manager = ChatSessionManager(db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get conversation history
    messages = session_manager.get_conversation_history(session_id, limit=50)

    return {
        "session_id": session.id,
        "visitor_id": session.visitor_id,
        "current_phase": session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
        "intent_score": session.intent_score,
        "intent_signals": session.intent_signals or [],
        "turn_count": session.turn_count,
        "cta_offered": session.cta_offered,
        "cta_accepted": session.cta_accepted,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "messages": messages
    }


# =============================================================================
# MESSAGE ENDPOINT
# =============================================================================

@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: int,
    message: ChatMessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Send message with full production stack:
    - Sensitive data detection
    - Deduplication
    - Caching
    - Circuit breaker
    - Quality analysis
    - Structured logging
    """
    start_time = time.time()

    # Get services
    redis_client = get_redis_client(request)
    ai_service = get_ai_service(request)
    components = get_chat_components(request)

    session_manager = ChatSessionManager(db)
    prompt_constructor = ChatPromptConstructor(db)

    # =========================================================================
    # 1. SENSITIVE DATA CHECK
    # =========================================================================
    if SensitiveDataDetector.should_block(message.content):
        structured_logger.log_chat_interaction(
            session_id=session_id,
            visitor_id="blocked",
            user_message="[REDACTED - SENSITIVE DATA]",
            ai_response=SensitiveDataDetector.REDACTION_RESPONSE,
            phase=0,
            intent_score=0,
            processing_time_ms=(time.time() - start_time) * 1000,
            cached=False
        )

        return ChatMessageResponse(
            session_id=session_id,
            message={
                "role": "assistant",
                "content": SensitiveDataDetector.REDACTION_RESPONSE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "blocked_sensitive_data": True
            },
            phase=0,
            intent_score=0,
            cached=False,
            processing_time_ms=(time.time() - start_time) * 1000
        )

    # =========================================================================
    # 2. GET SESSION
    # =========================================================================
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # =========================================================================
    # 3. DEDUPLICATION CHECK
    # =========================================================================
    if redis_client and components and components.deduplicator:
        deduplicator = components.deduplicator

        if await deduplicator.is_duplicate(session_id, message.content):
            # Return cached response if available
            if components.response_cache:
                session_context = {
                    'current_phase': session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
                    'intent_score': session.intent_score,
                    'intent_signals': [s.get('type') for s in (session.intent_signals or [])]
                }
                cached = await components.response_cache.get(session_context, message.content)

                if cached:
                    return ChatMessageResponse(
                        session_id=session_id,
                        message={
                            "role": "assistant",
                            "content": cached,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        },
                        phase=session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
                        intent_score=session.intent_score,
                        cached=True,
                        processing_time_ms=(time.time() - start_time) * 1000
                    )

            raise HTTPException(status_code=409, detail="Duplicate message")

        # Acquire processing lock
        can_process = await deduplicator.mark_processing(session_id, message.content)
        if not can_process:
            raise HTTPException(status_code=409, detail="Message already being processed")

    # =========================================================================
    # 4. CHECK CACHE
    # =========================================================================
    session_context = {
        'current_phase': session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
        'intent_score': session.intent_score,
        'intent_signals': [s.get('type') for s in (session.intent_signals or [])]
    }

    if redis_client and components and components.response_cache:
        cached_response = await components.response_cache.get(session_context, message.content)

        if cached_response:
            # Save messages to database
            session_manager.add_message(session_id=session_id, role='user', content=message.content)
            session_manager.add_message(session_id=session_id, role='assistant', content=cached_response)

            structured_logger.log_chat_interaction(
                session_id=session_id,
                visitor_id=session.visitor_id,
                user_message=message.content,
                ai_response=cached_response,
                phase=session_context['current_phase'],
                intent_score=session.intent_score,
                processing_time_ms=(time.time() - start_time) * 1000,
                cached=True
            )

            return ChatMessageResponse(
                session_id=session_id,
                message={
                    "role": "assistant",
                    "content": cached_response,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                phase=session_context['current_phase'],
                intent_score=session.intent_score,
                cached=True,
                processing_time_ms=(time.time() - start_time) * 1000
            )

    # =========================================================================
    # 5. PROCESS MESSAGE (Update session state)
    # =========================================================================
    updated_session = session_manager.process_message(
        session_id=session_id,
        user_message=message.content
    )

    # =========================================================================
    # 6. BUILD AI PROMPT
    # =========================================================================
    # LO context - in production, fetch from database
    lo_context = {
        'name': 'Tim Loss',
        'location': 'Mt. Pleasant / Charleston, SC',
        'specialties': ['VA', 'FHA', 'Conventional', 'Jumbo'],
        'reputation': 'Known for smooth closings and clear communication',
        'years_experience': 15
    }

    is_returning = updated_session.turn_count > 1

    system_prompt = prompt_constructor.build_system_prompt_with_continuity(
        session=updated_session,
        lo_context=lo_context,
        is_returning_user=is_returning
    )

    # =========================================================================
    # 7. GET CONVERSATION HISTORY
    # =========================================================================
    messages_history = session_manager.get_conversation_history(session_id, limit=10)

    # Add current message
    messages_for_ai = [
        {"role": msg['role'], "content": msg['content']}
        for msg in messages_history
    ]
    messages_for_ai.append({"role": "user", "content": message.content})

    # =========================================================================
    # 8. CALL AI (with circuit breaker if available)
    # =========================================================================
    if ai_service:
        try:
            assistant_message = await ai_service.get_response(
                messages=messages_for_ai,
                system_prompt=system_prompt
            )
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            assistant_message = (
                "I'm experiencing some technical difficulties at the moment. "
                "Would you like to speak directly with Tim? "
                "Click 'Call Now' below, or I can have him call you back at a convenient time."
            )
    else:
        # Fallback for development without AI service
        assistant_message = _generate_fallback_response(
            message.content,
            updated_session.current_phase
        )

    # =========================================================================
    # 9. EXTRACT AND PROCESS CTA
    # =========================================================================
    cta_match = re.search(r'\{\{CTA:(CALL_NOW|SCHEDULE|APPLICATION)\}\}', assistant_message)
    cta_type = None

    if cta_match:
        cta_type = cta_match.group(1).lower()
        assistant_message = re.sub(
            r'\{\{CTA:(CALL_NOW|SCHEDULE|APPLICATION)\}\}',
            '',
            assistant_message
        ).strip()

        session_manager.record_cta_offered(session_id, cta_type)

        structured_logger.log_cta_event(
            session_id=session_id,
            cta_type=cta_type,
            action='offered',
            intent_score=updated_session.intent_score,
            turn_count=updated_session.turn_count,
            visitor_id=session.visitor_id
        )

    # =========================================================================
    # 10. SAVE MESSAGES
    # =========================================================================
    session_manager.add_message(session_id=session_id, role='user', content=message.content)
    session_manager.add_message(
        session_id=session_id,
        role='assistant',
        content=assistant_message,
        cta_offered=cta_type
    )

    # =========================================================================
    # 11. CACHE RESPONSE
    # =========================================================================
    if redis_client and components and components.response_cache:
        await components.response_cache.set(session_context, message.content, assistant_message)

    # =========================================================================
    # 12. LOG INTERACTION
    # =========================================================================
    processing_time = (time.time() - start_time) * 1000

    structured_logger.log_chat_interaction(
        session_id=session_id,
        visitor_id=session.visitor_id,
        user_message=message.content,
        ai_response=assistant_message,
        phase=updated_session.current_phase.value if hasattr(updated_session.current_phase, 'value') else updated_session.current_phase,
        intent_score=updated_session.intent_score,
        processing_time_ms=processing_time,
        cached=False
    )

    # =========================================================================
    # 13. BACKGROUND QUALITY ANALYSIS
    # =========================================================================
    if updated_session.turn_count >= 3:
        background_tasks.add_task(
            _analyze_conversation_quality,
            session_id,
            db,
            components
        )

    # =========================================================================
    # 14. RETURN RESPONSE
    # =========================================================================
    return ChatMessageResponse(
        session_id=session_id,
        message={
            "role": "assistant",
            "content": assistant_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        cta=cta_type,
        phase=updated_session.current_phase.value if hasattr(updated_session.current_phase, 'value') else updated_session.current_phase,
        intent_score=updated_session.intent_score,
        cached=False,
        processing_time_ms=round(processing_time, 2)
    )


# =============================================================================
# CTA ENDPOINTS
# =============================================================================

@router.post("/sessions/{session_id}/cta")
async def respond_to_cta(
    session_id: int,
    response: CTAResponse,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle CTA response from borrower."""
    session_manager = ChatSessionManager(db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if response.action == "accepted":
        session_manager.record_cta_accepted(session_id, response.cta_type)

        structured_logger.log_cta_event(
            session_id=session_id,
            cta_type=response.cta_type,
            action='accepted',
            intent_score=session.intent_score,
            turn_count=session.turn_count,
            visitor_id=session.visitor_id
        )

        return {
            "status": "success",
            "message": f"CTA {response.cta_type} accepted",
            "next_step": _get_cta_next_step(response.cta_type)
        }

    elif response.action == "declined":
        structured_logger.log_cta_event(
            session_id=session_id,
            cta_type=response.cta_type,
            action='declined',
            intent_score=session.intent_score,
            turn_count=session.turn_count,
            visitor_id=session.visitor_id
        )

        return {
            "status": "success",
            "message": "No problem! Feel free to continue chatting or come back anytime."
        }

    else:  # deferred
        structured_logger.log_cta_event(
            session_id=session_id,
            cta_type=response.cta_type,
            action='deferred',
            intent_score=session.intent_score,
            turn_count=session.turn_count,
            visitor_id=session.visitor_id
        )

        return {
            "status": "success",
            "message": "I'll check back later. What else can I help with?"
        }


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """End a chat session."""
    session_manager = ChatSessionManager(db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager.end_session(session_id)

    return {
        "status": "success",
        "message": "Session ended",
        "summary": {
            "turn_count": session.turn_count,
            "final_phase": session.current_phase.value if hasattr(session.current_phase, 'value') else session.current_phase,
            "final_intent_score": session.intent_score,
            "cta_offered": session.cta_offered,
            "cta_accepted": session.cta_accepted
        }
    }


# =============================================================================
# QUALITY ENDPOINTS
# =============================================================================

@router.get("/sessions/{session_id}/quality")
async def get_session_quality(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get quality analysis for a session."""
    session_manager = ChatSessionManager(db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session_manager.get_conversation_history(session_id, limit=100)

    analyzer = ConversationQualityAnalyzer()
    metrics = analyzer.analyze_conversation(
        messages=[{"role": m['role'], "content": m['content']} for m in messages],
        session=session
    )

    return {
        "session_id": session_id,
        "quality": metrics.to_dict(),
        "summary": get_quality_summary(metrics)
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_fallback_response(user_message: str, phase: Any) -> str:
    """Generate fallback response when AI is unavailable - follows trust-first approach."""
    phase_value = phase.value if hasattr(phase, 'value') else phase

    # IMPORTANT: Only Phase 4 should mention scheduling calls
    if phase_value == 1:
        return (
            "Thanks for reaching out! I'm here to help you explore your mortgage options. "
            "What questions do you have about the home buying or refinancing process?"
        )
    elif phase_value == 2:
        return (
            "Great question! There are several factors that go into mortgage rates and options. "
            "Can you tell me a bit more about what you're looking for so I can give you more relevant information?"
        )
    elif phase_value == 3:
        return (
            "Thanks for sharing those details! To give you the most accurate guidance, "
            "I'd love to learn a bit more. What's your timeline looking like for this?"
        )
    else:  # Phase 4 only
        return (
            "Based on our conversation, I think Tim could really help you take the next step. "
            "Would you prefer to speak with him now, or schedule a call at a time that works better?"
        )


def _get_cta_next_step(cta_type: str) -> dict:
    """Get next step instructions for CTA type."""
    steps = {
        "call_now": {
            "action": "initiate_call",
            "message": "Connecting you with Tim now..."
        },
        "schedule": {
            "action": "show_scheduler",
            "message": "Let's find a time that works for you."
        },
        "application": {
            "action": "open_application",
            "message": "Starting your pre-approval application..."
        }
    }
    return steps.get(cta_type, {"action": "unknown", "message": "Processing..."})


async def _analyze_conversation_quality(
    session_id: int,
    db: Session,
    components: Any
):
    """Background task for quality analysis."""
    try:
        session_manager = ChatSessionManager(db)
        session = session_manager.get_session(session_id)

        if not session:
            return

        messages = session_manager.get_conversation_history(session_id, limit=50)

        analyzer = ConversationQualityAnalyzer()
        quality = analyzer.analyze_conversation(
            messages=[{"role": m['role'], "content": m['content']} for m in messages],
            session=session
        )

        # Log quality issues
        if quality.flags:
            structured_logger.logger.warning(
                "Quality issues detected",
                extra={
                    "event_type": "quality_alert",
                    "session_id": session_id,
                    "quality_score": quality.overall_score,
                    "flags": [f.value for f in quality.flags],
                    "recommendations": quality.recommendations[:3]
                }
            )

    except Exception as e:
        logger.error(f"Quality analysis failed for session {session_id}: {e}")
