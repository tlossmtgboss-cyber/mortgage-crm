"""
AI Orchestrator Chat Routes
AI Chat powered by AgentOrchestrator with tool execution and streaming
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import os
import json
import uuid
import time
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Lead': main.Lead,
        'Loan': main.Loan,
        'Task': main.Task,
        'LeadStage': main.LeadStage,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


@router.post("/orchestrator-chat")
async def orchestrator_chat(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    AI Chat powered by the AgentOrchestrator brain with Tool Execution
    Routes messages to specialized agents and executes real actions
    """
    try:
        from openai import OpenAI
        from conversation_memory_service import ConversationMemory as ConvMemory

        request_start_time = time.time()

        data = await request.json()
        message = data.get("message", "")
        context = data.get("context", {})
        session_id = data.get("session_id")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        if not session_id:
            session_id = str(uuid.uuid4())

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Load conversation history
        conversation_history = ConvMemory.get_session_messages(db, session_id)

        # Load user context
        try:
            from agents.memory.user_context import UserContextManager
            user_context = await UserContextManager.get_context(db, current_user.id)
            user_context_summary = user_context.get('summary', '')
            user_preferences = user_context.get('preferences', {})
        except Exception as ctx_err:
            logger.warning(f"Failed to load user context: {ctx_err}")
            try:
                db.rollback()
            except Exception:
                pass
            user_context = {}
            user_context_summary = ''
            user_preferences = {}

        # Build system prompt with user context
        system_prompt = f"""You are an AI assistant for a mortgage CRM system.

User Context: {user_context_summary}

You help loan officers manage their pipeline, follow up with leads, and track tasks.
Be concise and helpful. When asked about data, provide specific numbers when available."""

        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        for hist in conversation_history[-10:]:
            messages.append({"role": hist.get("role", "user"), "content": hist.get("content", "")})
        messages.append({"role": "user", "content": message})

        # Get AI response
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )

        ai_response = response.choices[0].message.content

        # Save to conversation memory
        try:
            ConvMemory.save_message(db, session_id, current_user.id, "user", message)
            ConvMemory.save_message(db, session_id, current_user.id, "assistant", ai_response)
        except Exception as save_err:
            logger.warning(f"Failed to save conversation: {save_err}")

        response_time = time.time() - request_start_time

        return {
            "success": True,
            "response": ai_response,
            "session_id": session_id,
            "response_time_ms": int(response_time * 1000)
        }

    except Exception as e:
        logger.error(f"Orchestrator chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orchestrator-chat-stream")
async def orchestrator_chat_stream(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Streaming AI Chat - sends response tokens as they're generated
    Uses Server-Sent Events (SSE) for real-time streaming
    """
    from openai import OpenAI
    import asyncio

    data = await request.json()
    message = data.get("message", "")
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    async def generate():
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # Load user context
            try:
                from agents.memory.user_context import UserContextManager
                user_context = await UserContextManager.get_context(db, current_user.id)
                user_context_summary = user_context.get('summary', '')
            except Exception:
                user_context_summary = ''

            system_prompt = f"""You are an AI assistant for a mortgage CRM system.
User Context: {user_context_summary}
Be concise and helpful."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]

            # Stream response
            stream = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True
            )

            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"

            # Send completion
            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

            # Save conversation
            try:
                from conversation_memory_service import ConversationMemory as ConvMemory
                ConvMemory.save_message(db, session_id, current_user.id, "user", message)
                ConvMemory.save_message(db, session_id, current_user.id, "assistant", full_response)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
