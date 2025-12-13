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

from backend.services.agent_governance_service import AgentGovernanceService
from backend.models.agent_governance import AgentProfile, AgentExecution, AgentChatSession, AgentChatMessage

logger = logging.getLogger(__name__)
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
    """Send a message and stream the agent response."""
    try:
        session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
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

            # Simulate streaming response (would integrate with actual agent)
            response_parts = await generate_streaming_response(
                agent=agent,
                message=message.content,
                session=session,
                context=message.context
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

async def generate_agent_response(
    agent: AgentProfile,
    message: str,
    session: Optional[AgentChatSession],
    context: Optional[Dict[str, Any]],
    db: Session
) -> Dict[str, Any]:
    """
    Generate agent response based on agent type and message.
    This is a placeholder - would integrate with actual agent implementation.
    """
    # In production, this would:
    # 1. Load the appropriate agent based on category
    # 2. Pass message and context to the agent
    # 3. Execute any tool calls
    # 4. Return the response

    agent_name = agent.display_name or agent.agent_name

    # Placeholder response based on agent category
    agent_responses = {
        "core_crm": f"I've analyzed your request based on the query: '{message}'. I can help with pipeline analysis, compliance checking, lead management, and document tracking. What would you like me to focus on?",
        "extended": f"Based on your request about '{message}', I can provide specialized assistance. This includes coaching, scheduling, rate analysis, and more. How can I help?",
        "custom": f"I'm a custom agent ready to assist with: '{message}'. Please let me know what specific help you need.",
    }

    response_content = agent_responses.get(
        agent.category,
        f"I'm {agent_name}, and I can help you with: '{message}'. How would you like me to assist further?"
    )

    return {
        "content": response_content,
        "tool_calls": None,
        "tools_used": [],
        "tokens_used": len(response_content) // 4  # Rough estimate
    }


async def generate_streaming_response(
    agent: AgentProfile,
    message: str,
    session: AgentChatSession,
    context: Optional[Dict[str, Any]]
) -> List[str]:
    """
    Generate streaming response parts.
    Returns list of strings to be streamed.
    """
    agent_name = agent.display_name or agent.agent_name

    # Generate full response first (in production, this would be actual streaming)
    full_response = f"I'm {agent_name}. "
    full_response += f"Based on your message about '{message[:50]}...', "
    full_response += "here's my analysis:\n\n"
    full_response += "1. I've reviewed the relevant data\n"
    full_response += "2. Key findings are being processed\n"
    full_response += "3. Recommendations will follow\n\n"
    full_response += "Would you like me to elaborate on any specific point?"

    # Break into chunks for streaming
    chunk_size = 20
    return [full_response[i:i + chunk_size] for i in range(0, len(full_response), chunk_size)]
