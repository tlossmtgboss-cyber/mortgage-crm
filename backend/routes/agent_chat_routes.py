"""
Agent Chat API Routes
Perennia AI - IBMA

Provides endpoints for:
- Interactive chat with agents
- Chat session management
- Message history
- Agent conversation context
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime, timedelta
import logging
import uuid
import json
import asyncio

from database import get_db

from services.agent_governance_service import AgentGovernanceService
from models.agent_governance import AgentProfile, AgentExecution, AgentChatSession, AgentChatMessage
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import to avoid circular dependency."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

# Initialize OpenAI client lazily
_openai_client = None
_openai_enabled = False

def get_openai_client():
    """Get or create OpenAI client."""
    global _openai_client, _openai_enabled
    if _openai_client is None:
        try:
            from openai import OpenAI
            import os
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                _openai_client = OpenAI(api_key=api_key)
                _openai_enabled = True
                logger.info("OpenAI client initialized for agent chat")
            else:
                logger.warning("OPENAI_API_KEY not set - agent chat will use fallback responses")
        except ImportError:
            logger.warning("OpenAI package not installed - agent chat will use fallback responses")
    return _openai_client, _openai_enabled


router = APIRouter(prefix="/api/v1/agents/chat", tags=["agent-chat"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ChatSessionCreate(BaseModel):
    """Request model for creating a chat session."""
    agent_id: int = Field(..., description="Agent ID to chat with")
    user_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


class ChatMessageCreate(BaseModel):
    """Request model for sending a message."""
    content: str = Field(..., description="Message content")
    context: Optional[Dict[str, Any]] = None


class ChatSessionResponse(BaseModel):
    """Response model for chat session."""
    id: int
    session_id: str
    agent_id: int
    agent_name: str
    user_id: Optional[int]
    is_active: bool
    message_count: int
    created_at: datetime
    last_activity_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """Response model for chat message."""
    id: int
    session_id: int
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]]
    tokens_used: Optional[int]
    response_time_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Chat Session Routes
# ============================================================================

@router.post("/sessions")
async def create_chat_session(
    session_data: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Create a new chat session with an agent."""
    try:
        # Verify agent exists
        agent = db.query(AgentProfile).filter(AgentProfile.id == session_data.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.status != "active":
            raise HTTPException(status_code=400, detail=f"Agent is {agent.status}, cannot start chat")

        # Create session
        session = AgentChatSession(
            agent_id=session_data.agent_id,
            agent_name=agent.agent_name,
            user_id=session_data.user_id,
            context=session_data.context or {},
            is_active=True
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return {
            "status": "success",
            "session_id": str(session.session_id),
            "id": session.id,
            "agent_id": agent.id,
            "agent_name": agent.display_name or agent.agent_name,
            "agent_category": agent.category
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions")
async def list_chat_sessions(
    agent_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    days: int = Query(30, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """List chat sessions with filtering (scoped to current user)."""
    try:
        query = db.query(AgentChatSession)

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(AgentChatSession.created_at >= cutoff)

        # Scope to current user's sessions
        query = query.filter(AgentChatSession.user_id == current_user.id)

        if agent_id:
            query = query.filter(AgentChatSession.agent_id == agent_id)
        if is_active is not None:
            query = query.filter(AgentChatSession.is_active == is_active)

        total = query.count()
        sessions = query.order_by(AgentChatSession.created_at.desc()).offset(offset).limit(limit).all()

        # Build response
        result = []
        for session in sessions:
            result.append({
                "id": session.id,
                "session_id": str(session.session_id),
                "agent_id": session.agent_id,
                "agent_name": session.agent_name,
                "user_id": session.user_id,
                "is_active": session.is_active,
                "message_count": session.message_count,
                "created_at": session.created_at,
                "last_activity_at": session.last_activity_at
            })

        return {
            "sessions": result,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Get a chat session with its messages (scoped to current user)."""
    session = db.query(AgentChatSession).filter(
        AgentChatSession.id == session_id,
        AgentChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(AgentChatMessage).filter(
        AgentChatMessage.session_id == session_id
    ).order_by(AgentChatMessage.created_at.asc()).all()

    agent = db.query(AgentProfile).filter(AgentProfile.id == session.agent_id).first()

    return {
        "session": {
            "id": session.id,
            "session_id": str(session.session_id),
            "agent_id": session.agent_id,
            "agent_name": agent.display_name or agent.agent_name if agent else session.agent_name,
            "agent_category": agent.category if agent else None,
            "user_id": session.user_id,
            "is_active": session.is_active,
            "context": session.context,
            "created_at": session.created_at
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tokens_used": m.tokens_used,
                "response_time_ms": m.response_time_ms,
                "created_at": m.created_at
            }
            for m in messages
        ],
        "message_count": len(messages)
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    message: ChatMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Send a message in a chat session and get agent response."""
    try:
        session = db.query(AgentChatSession).filter(
            AgentChatSession.id == session_id,
            AgentChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if not session.is_active:
            raise HTTPException(status_code=400, detail="Session is not active")

        agent = db.query(AgentProfile).filter(AgentProfile.id == session.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        start_time = datetime.utcnow()

        # Create user message
        user_message = AgentChatMessage(
            session_id=session_id,
            role="user",
            content=message.content
        )
        db.add(user_message)

        # Generate agent response (placeholder - would integrate with actual agent)
        agent_response = await generate_agent_response(
            agent=agent,
            message=message.content,
            session=session,
            context=message.context,
            db=db
        )

        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        # Create agent message
        agent_message = AgentChatMessage(
            session_id=session_id,
            role="assistant",
            content=agent_response["content"],
            tool_calls=agent_response.get("tool_calls"),
            tokens_used=agent_response.get("tokens_used"),
            response_time_ms=response_time
        )
        db.add(agent_message)

        # Update session metrics
        session.message_count = (session.message_count or 0) + 2
        session.total_tokens = (session.total_tokens or 0) + (agent_response.get("tokens_used") or 0)
        session.last_activity_at = datetime.utcnow()

        db.commit()
        db.refresh(user_message)
        db.refresh(agent_message)

        return {
            "status": "success",
            "user_message": {
                "id": user_message.id,
                "role": "user",
                "content": user_message.content,
                "created_at": user_message.created_at
            },
            "agent_message": {
                "id": agent_message.id,
                "role": "assistant",
                "content": agent_message.content,
                "tool_calls": agent_message.tool_calls,
                "tokens_used": agent_message.tokens_used,
                "response_time_ms": agent_message.response_time_ms,
                "created_at": agent_message.created_at
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: int,
    message: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Send a message and stream the agent response."""
    try:
        session = db.query(AgentChatSession).filter(
            AgentChatSession.id == session_id,
            AgentChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        agent = db.query(AgentProfile).filter(AgentProfile.id == session.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Create user message first
        user_message = AgentChatMessage(
            session_id=session_id,
            role="user",
            content=message.content
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        async def generate_stream() -> AsyncGenerator[str, None]:
            """Generate streaming response."""
            full_response = ""

            # Start streaming indicator
            yield f"data: {json.dumps({'type': 'start', 'user_message_id': user_message.id})}\n\n"

            # Generate streaming response using OpenAI
            response_parts = await generate_streaming_response(
                agent=agent,
                message=message.content,
                session=session,
                context=message.context,
                db=db
            )

            for part in response_parts:
                full_response += part
                yield f"data: {json.dumps({'type': 'content', 'content': part})}\n\n"
                await asyncio.sleep(0.05)  # Small delay for streaming effect

            # Save complete message to database
            from database import SessionLocal
            async_db = SessionLocal()
            try:
                agent_message = AgentChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    tokens_used=len(full_response) // 4
                )
                async_db.add(agent_message)

                # Update session
                sess = async_db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
                if sess:
                    sess.message_count = (sess.message_count or 0) + 2
                    sess.last_activity_at = datetime.utcnow()

                async_db.commit()
                async_db.refresh(agent_message)

                # End streaming
                yield f"data: {json.dumps({'type': 'end', 'message_id': agent_message.id, 'total_length': len(full_response)})}\n\n"
            finally:
                async_db.close()

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error in streaming message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/sessions/{session_id}")
async def close_chat_session(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Close a chat session and trigger post-session AI learning analysis."""
    session = db.query(AgentChatSession).filter(
        AgentChatSession.id == session_id,
        AgentChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    session.ended_at = datetime.utcnow()

    # Collect session messages before committing, so we can pass them to the
    # background learning task without needing the DB session later.
    session_messages = []
    try:
        messages = db.query(AgentChatMessage).filter(
            AgentChatMessage.session_id == session_id
        ).order_by(AgentChatMessage.created_at.asc()).all()

        session_messages = [
            {"role": m.role, "content": m.content or ""}
            for m in messages
        ]
    except Exception as e:
        logger.warning(f"Failed to collect session messages for learning: {e}")

    db.commit()

    # Schedule post-session AI learning analysis in background.
    # This never blocks the response; failures are logged and swallowed.
    if session_messages:
        conversation_id = str(session.session_id)
        background_tasks.add_task(
            _run_post_session_analysis,
            conversation_id=conversation_id,
            messages=session_messages,
            session_id_int=session_id,
        )

    return {
        "status": "success",
        "message": "Session closed",
        "session_id": session_id
    }


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Get messages for a chat session."""
    session = db.query(AgentChatSession).filter(
        AgentChatSession.id == session_id,
        AgentChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    query = db.query(AgentChatMessage).filter(AgentChatMessage.session_id == session_id)
    total = query.count()
    messages = query.order_by(AgentChatMessage.created_at.asc()).offset(offset).limit(limit).all()

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tokens_used": m.tokens_used,
                "response_time_ms": m.response_time_ms,
                "created_at": m.created_at
            }
            for m in messages
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ============================================================================
# Agent Quick Actions
# ============================================================================

@router.post("/quick/{agent_id}")
async def quick_agent_action(
    agent_id: int,
    message: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """
    Send a one-off message to an agent without creating a persistent session.
    Useful for quick queries and single-turn interactions.
    """
    try:
        agent = db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.status != "active":
            raise HTTPException(status_code=400, detail=f"Agent is {agent.status}")

        start_time = datetime.utcnow()

        # Generate response
        response = await generate_agent_response(
            agent=agent,
            message=message.content,
            session=None,
            context=message.context,
            db=db
        )

        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return {
            "status": "success",
            "agent_id": agent_id,
            "agent_name": agent.display_name or agent.agent_name,
            "response": response["content"],
            "tool_calls": response.get("tool_calls"),
            "tokens_used": response.get("tokens_used"),
            "response_time_ms": response_time
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in quick action: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Helper Functions
# ============================================================================

def _build_agent_system_prompt(agent: AgentProfile, context: Optional[Dict[str, Any]]) -> str:
    """Build system prompt for an agent based on its profile."""
    agent_name = agent.display_name or agent.agent_name
    description = agent.description or f"A specialized {agent.category} agent"

    # Get agent-specific configuration
    config = agent.config or {}
    custom_prompt = config.get("system_prompt", "")
    capabilities = config.get("capabilities", [])

    # Agent category-specific context
    category_context = {
        "core_crm": """You specialize in core CRM operations including:
- Pipeline analysis and loan tracking
- Compliance checking and regulatory adherence
- Lead management and nurturing
- Document tracking and status updates

You have access to loan data, borrower information, and pipeline metrics.""",

        "extended": """You provide extended mortgage services including:
- Team coaching and performance analysis
- Appointment scheduling and calendar management
- Rate analysis and market updates
- Communication templates and outreach

You can analyze trends and provide actionable recommendations.""",

        "custom": """You are a customizable agent that can be configured for specific workflows and tasks.
You adapt to the user's needs and provide tailored assistance."""
    }

    base_prompt = f"""You are {agent_name}, an AI assistant at Perennia AI - a mortgage CRM and AI platform.

{description}

{category_context.get(agent.category, category_context['custom'])}

{custom_prompt}

Guidelines:
- Be concise and professional
- Provide specific, actionable information when possible
- If you need more context to help effectively, ask clarifying questions
- When discussing loans or borrower data, maintain confidentiality
- Use clear formatting for lists and data
"""

    if capabilities:
        base_prompt += f"\nYour specific capabilities: {', '.join(capabilities)}"

    if context:
        base_prompt += f"\n\nCurrent context: {json.dumps(context, default=str)}"

    return base_prompt


async def generate_agent_response(
    agent: AgentProfile,
    message: str,
    session: Optional[AgentChatSession],
    context: Optional[Dict[str, Any]],
    db: Session
) -> Dict[str, Any]:
    """
    Generate agent response using OpenAI.
    Falls back to template responses if OpenAI is unavailable.
    """
    import os

    client, enabled = get_openai_client()
    agent_name = agent.display_name or agent.agent_name

    if enabled and client:
        try:
            # Build conversation history from session
            messages = [{"role": "system", "content": _build_agent_system_prompt(agent, context)}]

            # Add conversation history if in a session
            if session:
                history = db.query(AgentChatMessage).filter(
                    AgentChatMessage.session_id == session.id
                ).order_by(AgentChatMessage.created_at.desc()).limit(10).all()

                # Add in chronological order
                for msg in reversed(history):
                    messages.append({"role": msg.role, "content": msg.content})

            # Add current message
            messages.append({"role": "user", "content": message})

            # Call OpenAI
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )

            content = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens if response.usage else len(content) // 4

            return {
                "content": content,
                "tool_calls": None,
                "tools_used": [],
                "tokens_used": tokens_used,
                "model": model
            }

        except Exception as e:
            logger.error(f"OpenAI API error for agent {agent_name}: {e}")
            # Fall through to fallback response

    # Fallback response when OpenAI is unavailable
    fallback_responses = {
        "core_crm": f"I'm {agent_name}, your CRM assistant. I can help with pipeline analysis, compliance checking, lead management, and document tracking. What would you like me to help with regarding: '{message[:100]}...'?",
        "extended": f"I'm {agent_name}, and I specialize in coaching, scheduling, and rate analysis. Regarding your question about '{message[:100]}...', how can I assist you?",
        "custom": f"I'm {agent_name}, ready to help with your request. Could you provide more details about: '{message[:100]}...'?",
    }

    response_content = fallback_responses.get(
        agent.category,
        f"I'm {agent_name}. I'd be happy to help with your request about '{message[:100]}...'. What specific information do you need?"
    )

    return {
        "content": response_content,
        "tool_calls": None,
        "tools_used": [],
        "tokens_used": len(response_content) // 4,
        "model": "fallback"
    }


async def generate_streaming_response(
    agent: AgentProfile,
    message: str,
    session: AgentChatSession,
    context: Optional[Dict[str, Any]],
    db: Session = None
) -> List[str]:
    """
    Generate streaming response using OpenAI streaming API.
    Returns list of strings to be streamed.
    Falls back to chunked template response if OpenAI unavailable.
    """
    import os

    client, enabled = get_openai_client()
    agent_name = agent.display_name or agent.agent_name

    if enabled and client:
        try:
            # Build messages for OpenAI
            messages = [{"role": "system", "content": _build_agent_system_prompt(agent, context)}]

            # Add conversation history if available
            if session and db:
                history = db.query(AgentChatMessage).filter(
                    AgentChatMessage.session_id == session.id
                ).order_by(AgentChatMessage.created_at.desc()).limit(10).all()

                for msg in reversed(history):
                    messages.append({"role": msg.role, "content": msg.content})

            messages.append({"role": "user", "content": message})

            # Use OpenAI streaming
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7,
                stream=True
            )

            # Collect chunks from stream
            chunks = []
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    chunks.append(chunk.choices[0].delta.content)

            return chunks

        except Exception as e:
            logger.error(f"OpenAI streaming error for agent {agent_name}: {e}")
            # Fall through to fallback

    # Fallback: Generate template response and chunk it
    full_response = f"I'm {agent_name}. "
    full_response += f"Based on your message about '{message[:50]}...', "
    full_response += "here's my analysis:\n\n"
    full_response += "1. I've reviewed the relevant data\n"
    full_response += "2. Key findings are being processed\n"
    full_response += "3. Recommendations will follow\n\n"
    full_response += "Would you like me to elaborate on any specific point?"

    # Break into chunks for streaming effect
    chunk_size = 20
    return [full_response[i:i + chunk_size] for i in range(0, len(full_response), chunk_size)]


# ============================================================================
# Post-Session AI Learning Hook
# ============================================================================

def _run_post_session_analysis(
    conversation_id: str,
    messages: List[Dict[str, Any]],
    session_id_int: int,
) -> None:
    """
    Background task that feeds a completed chat session into the
    ConversationAILearningService for analysis and continuous improvement.

    This function is designed to be called via BackgroundTasks.add_task()
    so it never blocks the HTTP response. All exceptions are caught and logged.
    """
    try:
        from services.conversation_ai_learning_service import (
            ConversationAILearningService,
            ConversationOutcome,
        )

        learning_service = ConversationAILearningService()

        # Determine outcome heuristically from messages
        outcome = _infer_conversation_outcome(messages)

        analysis = learning_service.analyze_conversation(
            conversation_id=conversation_id,
            messages=messages,
            outcome=outcome,
            caller_satisfaction=None,  # No explicit satisfaction score from chat sessions
            metadata={"session_id_int": session_id_int, "message_count": len(messages)},
        )

        logger.info(
            f"Post-session analysis complete for session {session_id_int}: "
            f"outcome={analysis.outcome.value}, quality={analysis.quality_score:.2f}, "
            f"gaps={len(analysis.knowledge_gaps_identified)}, "
            f"recommendations={len(analysis.recommendations)}"
        )
    except Exception as e:
        logger.warning(
            f"Post-session analysis failed for session {session_id_int}: {e}",
            exc_info=True,
        )


def _infer_conversation_outcome(messages: List[Dict[str, Any]]) -> "ConversationOutcome":
    """
    Heuristically infer conversation outcome from message content.
    Lazy-imports ConversationOutcome to avoid circular deps at module load.
    """
    from services.conversation_ai_learning_service import ConversationOutcome

    if not messages:
        return ConversationOutcome.UNKNOWN

    # Look at the last few user messages for signals
    user_messages = [m for m in messages if m.get("role") == "user"]
    ai_messages = [m for m in messages if m.get("role") == "assistant"]

    if not user_messages:
        return ConversationOutcome.UNKNOWN

    last_user = user_messages[-1].get("content", "").lower() if user_messages else ""

    # Positive signals
    positive_signals = ["thank", "thanks", "great", "perfect", "that helps", "awesome", "got it"]
    if any(signal in last_user for signal in positive_signals):
        return ConversationOutcome.SUCCESS

    # Negative signals
    negative_signals = ["not helpful", "wrong", "doesn't help", "useless", "frustrated"]
    if any(signal in last_user for signal in negative_signals):
        return ConversationOutcome.FAILURE

    # If conversation is very short (1-2 exchanges), may be abandoned
    if len(user_messages) <= 1 and len(ai_messages) <= 1:
        return ConversationOutcome.ABANDONED

    # Default: partial success for multi-turn conversations
    return ConversationOutcome.PARTIAL_SUCCESS
