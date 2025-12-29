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

logger = logging.getLogger(__name__)

# Initialize OpenAI client eagerly at module load for faster first request
_openai_client = None
_openai_enabled = False

def _init_openai_client():
    """Initialize OpenAI client at module load."""
    global _openai_client, _openai_enabled
    try:
        from openai import OpenAI
        import os
        import httpx
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            # Configure client with connection pooling and optimized timeouts
            _openai_client = OpenAI(
                api_key=api_key,
                timeout=httpx.Timeout(30.0, connect=5.0),  # Fast connect, reasonable total
                max_retries=1,  # Minimize retry delays
            )
            _openai_enabled = True
            logger.info("OpenAI client initialized for agent chat (eager loading)")
        else:
            logger.warning("OPENAI_API_KEY not set - agent chat will use fallback responses")
    except ImportError:
        logger.warning("OpenAI package not installed - agent chat will use fallback responses")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")

# Initialize immediately
_init_openai_client()

def get_openai_client():
    """Get OpenAI client (already initialized)."""
    global _openai_client, _openai_enabled
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
    db: Session = Depends(get_db)
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
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_chat_sessions(
    agent_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    days: int = Query(30, le=90),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """List chat sessions with filtering."""
    try:
        query = db.query(AgentChatSession)

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(AgentChatSession.created_at >= cutoff)

        if agent_id:
            query = query.filter(AgentChatSession.agent_id == agent_id)
        if user_id:
            query = query.filter(AgentChatSession.user_id == user_id)
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

    except Exception as e:
        logger.error(f"Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Get a chat session with its messages."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
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
    db: Session = Depends(get_db)
):
    """Send a message in a chat session and get agent response."""
    try:
        session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: int,
    message: ChatMessageCreate,
    db: Session = Depends(get_db)
):
    """Send a message and stream the agent response with true streaming from OpenAI."""
    try:
        session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        agent = db.query(AgentProfile).filter(AgentProfile.id == session.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Fetch conversation history (limit to last 6 for speed)
        history = db.query(AgentChatMessage).filter(
            AgentChatMessage.session_id == session_id
        ).order_by(AgentChatMessage.created_at.desc()).limit(6).all()

        # Create user message first
        user_message = AgentChatMessage(
            session_id=session_id,
            role="user",
            content=message.content
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        # Pre-build messages for OpenAI
        messages = [{"role": "system", "content": _build_agent_system_prompt(agent, message.context)}]
        for msg in reversed(history):
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": message.content})

        async def generate_stream() -> AsyncGenerator[str, None]:
            """Generate true streaming response directly from OpenAI."""
            import os
            full_response = ""
            client, enabled = get_openai_client()
            agent_name = agent.display_name or agent.agent_name

            # Start streaming indicator immediately
            yield f"data: {json.dumps({'type': 'start', 'user_message_id': user_message.id})}\n\n"

            if enabled and client:
                try:
                    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                    # True streaming - iterate directly over OpenAI stream
                    stream = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.7,
                        stream=True
                    )

                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            # Stream immediately - no artificial delay!
                            yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                except Exception as e:
                    logger.error(f"OpenAI streaming error: {e}")
                    # Fallback response
                    fallback = f"I'm {agent_name}. I'd be happy to help with your request. Could you provide more details?"
                    full_response = fallback
                    yield f"data: {json.dumps({'type': 'content', 'content': fallback})}\n\n"
            else:
                # Fallback when OpenAI unavailable
                fallback = f"I'm {agent_name}. I'd be happy to help with your request about '{message.content[:50]}...'. What specific information do you need?"
                full_response = fallback
                yield f"data: {json.dumps({'type': 'content', 'content': fallback})}\n\n"

            # Save complete message to database (async after streaming)
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
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in streaming message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def close_chat_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Close a chat session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    session.ended_at = datetime.utcnow()
    db.commit()

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
    db: Session = Depends(get_db)
):
    """Get messages for a chat session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
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
    db: Session = Depends(get_db)
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
        raise HTTPException(status_code=500, detail=str(e))


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


# Simple in-memory cache for quick responses (avoids Redis overhead for hot paths)
_response_cache: Dict[str, tuple] = {}  # key -> (response, timestamp)
_CACHE_TTL_SECONDS = 300  # 5 minutes for quick cache

def _get_cache_key(agent_id: int, message: str, context_hash: str = "") -> str:
    """Generate cache key for response."""
    import hashlib
    normalized = message.lower().strip()[:200]  # Normalize and limit length
    key_input = f"{agent_id}:{normalized}:{context_hash}"
    return hashlib.sha256(key_input.encode()).hexdigest()[:24]

def _check_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    """Check if response is cached and still valid."""
    if cache_key in _response_cache:
        response, timestamp = _response_cache[cache_key]
        if (datetime.utcnow() - timestamp).total_seconds() < _CACHE_TTL_SECONDS:
            logger.debug(f"Cache hit for {cache_key[:12]}...")
            return response
        else:
            del _response_cache[cache_key]
    return None

def _set_cache(cache_key: str, response: Dict[str, Any]):
    """Cache a response."""
    # Limit cache size to prevent memory issues
    if len(_response_cache) > 1000:
        # Remove oldest entries
        oldest_keys = sorted(_response_cache.keys(),
                            key=lambda k: _response_cache[k][1])[:100]
        for k in oldest_keys:
            del _response_cache[k]
    _response_cache[cache_key] = (response, datetime.utcnow())

async def generate_agent_response(
    agent: AgentProfile,
    message: str,
    session: Optional[AgentChatSession],
    context: Optional[Dict[str, Any]],
    db: Session
) -> Dict[str, Any]:
    """
    Generate agent response using OpenAI with caching.
    Falls back to template responses if OpenAI is unavailable.
    """
    import os

    client, enabled = get_openai_client()
    agent_name = agent.display_name or agent.agent_name

    # Check cache for non-session (quick action) requests
    cache_key = None
    if not session:
        cache_key = _get_cache_key(agent.id, message)
        cached = _check_cache(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    if enabled and client:
        try:
            # Build conversation history from session
            messages = [{"role": "system", "content": _build_agent_system_prompt(agent, context)}]

            # Add conversation history if in a session (reduced to 6 messages for speed)
            if session:
                history = db.query(AgentChatMessage).filter(
                    AgentChatMessage.session_id == session.id
                ).order_by(AgentChatMessage.created_at.desc()).limit(6).all()

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

            result = {
                "content": content,
                "tool_calls": None,
                "tools_used": [],
                "tokens_used": tokens_used,
                "model": model,
                "from_cache": False
            }

            # Cache non-session responses
            if cache_key and len(content) > 50:
                _set_cache(cache_key, result)

            return result

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
        "model": "fallback",
        "from_cache": False
    }


# NOTE: generate_streaming_response was removed - streaming is now done directly
# in send_message_stream() for true real-time streaming without buffering
