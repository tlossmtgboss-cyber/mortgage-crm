"""
SSE Streaming Chat Routes
Server-Sent Events streaming chat endpoint using Anthropic with full tool support
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import json
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai")

# Check for SSE support
try:
    from sse_starlette.sse import EventSourceResponse
    SSE_AVAILABLE = True
except ImportError:
    EventSourceResponse = None
    SSE_AVAILABLE = False


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'AITask': main.AITask,
        'Loan': main.Loan,
        'TaskType': main.TaskType,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


# Pydantic models
class ChatStreamRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    session_id: Optional[str] = None


@router.post("/chat-stream")
async def chat_stream(
    request: ChatStreamRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Streaming chat endpoint - responses arrive in real-time via Server-Sent Events (SSE)

    This endpoint uses the AIAgentService with AsyncAnthropic for true token streaming,
    reducing perceived latency from ~28s to <2s.

    Returns:
        EventSourceResponse with SSE events:
        - event: status - thinking/gathering/reasoning status updates
        - event: tool - tool execution notifications
        - event: message - actual response content chunks
        - event: done - completion signal with metadata
        - event: error - error notifications
    """
    from agents.service import create_ai_agent_service

    models = get_models()
    AITask = models['AITask']
    Loan = models['Loan']
    TaskType = models['TaskType']

    message = request.message
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    async def generate_stream():
        """Generate SSE stream of AI responses using full LangGraph pipeline"""
        try:
            # Initialize the agent service with full tool support
            agent_service = await create_ai_agent_service(
                db=db,
                current_user=current_user,
                autonomous_mode=True
            )

            # Prepare context from request
            context = request.context or {}

            # Add loan/lead context if provided
            if request.loan_id:
                context["loan_id"] = request.loan_id
            if request.lead_id:
                context["lead_id"] = request.lead_id

            # Track full response and metadata for final event
            full_response = ""
            final_metadata = {}

            # Stream using the full LangGraph pipeline
            async for chunk in agent_service.chat_streaming(
                message=message,
                context=context,
                session_id=request.session_id
            ):
                event_type = chunk.get("event")
                event_data = chunk.get("data", {})

                if event_type == "status":
                    status = event_data.get("status", "thinking")
                    sse_event = "thinking"
                    if status in ["gathering"]:
                        sse_event = "tool_start"
                    elif status in ["reasoning", "responding"]:
                        sse_event = "thinking"

                    yield {
                        "event": sse_event,
                        "data": json.dumps({
                            "status": status,
                            "message": event_data.get("message", ""),
                            "tools": event_data.get("tools", [])
                        })
                    }

                elif event_type == "tool":
                    tool_status = event_data.get("status", "executing")
                    sse_event = "tool_start" if tool_status == "executing" else "tool_end"

                    yield {
                        "event": sse_event,
                        "data": json.dumps({
                            "tool": event_data.get("tool_name", "unknown"),
                            "status": tool_status,
                            "success": event_data.get("success", True),
                            "execution_time_ms": event_data.get("execution_time_ms", 0)
                        })
                    }

                elif event_type == "action":
                    yield {
                        "event": "action",
                        "data": json.dumps({
                            "action_type": event_data.get("action_type"),
                            "success": event_data.get("success"),
                            "message": event_data.get("message")
                        })
                    }

                elif event_type == "content":
                    content = event_data.get("content", "")
                    full_response += content
                    yield {
                        "event": "content",
                        "data": json.dumps({
                            "chunk": content
                        })
                    }

                elif event_type == "complete":
                    final_metadata = {
                        "session_id": event_data.get("session_id"),
                        "tools_used": event_data.get("tools_used", []),
                        "insights": event_data.get("insights", []),
                        "follow_up_suggestions": event_data.get("follow_up_suggestions", []),
                        "execution_time_ms": event_data.get("execution_time_ms", 0),
                        "query_intent": event_data.get("query_intent", "unknown"),
                        "data_quality": event_data.get("data_quality", "unknown")
                    }

                elif event_type == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "error": event_data.get("error", "Unknown error"),
                            "message": event_data.get("message", "An error occurred")
                        })
                    }
                    return

            # Get prioritized tasks for sidebar (if relevant)
            message_lower = message.lower()
            is_task_question = any(keyword in message_lower for keyword in [
                'task', 'priority', 'priorities', 'briefing', 'what should i do',
                'outstanding', 'overdue', 'due today', 'pipeline', 'bottleneck'
            ])

            prioritized_tasks_data = []
            if is_task_question:
                all_tasks = db.query(AITask).filter(
                    AITask.assigned_to_id == current_user.id,
                    AITask.type != TaskType.COMPLETED
                ).all()
                all_loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

                priority_tasks = sorted(
                    all_tasks,
                    key=lambda x: (
                        0 if x.priority == "urgent" else 1 if x.priority == "high" else 2 if x.priority == "medium" else 3,
                        x.due_date or datetime.max
                    )
                )[:10]

                for task in priority_tasks:
                    loan_info = None
                    if task.loan_id:
                        loan = next((l for l in all_loans if l.id == task.loan_id), None)
                        if loan:
                            loan_info = {
                                "borrower": loan.borrower_name,
                                "amount": f"${loan.amount:,.0f}" if loan.amount else None
                            }

                    prioritized_tasks_data.append({
                        "id": task.id,
                        "title": task.title,
                        "priority": task.priority.upper() if task.priority else "MEDIUM",
                        "due_date": task.due_date.strftime("%m/%d/%Y") if task.due_date else None,
                        "client": loan_info["borrower"] if loan_info else (task.borrower_name or "")
                    })

            # Send completion signal with all metadata
            yield {
                "event": "done",
                "data": json.dumps({
                    "session_id": request.session_id or final_metadata.get("session_id"),
                    "full_response": full_response,
                    "prioritized_tasks": prioritized_tasks_data if prioritized_tasks_data else None,
                    "metadata": {
                        "model": "claude-sonnet-4-20250514",
                        "streaming": True,
                        "tools_used": final_metadata.get("tools_used", []),
                        "insights": final_metadata.get("insights", []),
                        "follow_up_suggestions": final_metadata.get("follow_up_suggestions", []),
                        "execution_time_ms": final_metadata.get("execution_time_ms", 0),
                        "query_intent": final_metadata.get("query_intent", "unknown"),
                        "data_quality": final_metadata.get("data_quality", "unknown")
                    }
                })
            }

        except Exception as e:
            logger.error(f"SSE Streaming error: {str(e)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": "Internal server error"
                })
            }

    # Use EventSourceResponse if available, otherwise fall back to StreamingResponse
    if SSE_AVAILABLE and EventSourceResponse:
        return EventSourceResponse(generate_stream())
    else:
        async def sse_generator():
            async for event in generate_stream():
                event_type = event.get("event", "message")
                data = event.get("data", "{}")
                yield f"event: {event_type}\ndata: {data}\n\n"

        return StreamingResponse(
            sse_generator(),
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
