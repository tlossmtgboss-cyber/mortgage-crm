"""
AI System API Endpoints
FastAPI routes for the AI architecture
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import uuid
from datetime import datetime

from main import get_db
from ai_models import (
    AgentConfig, ExecuteAgentRequest, ExecuteAgentResponse,
    DispatchEventRequest, SendMessageRequest, ProvideExecutionFeedbackRequest,
    ApproveAuditFindingRequest, CreatePromptVersionRequest
)
from ai_services import AgentOrchestrator, AgentRegistry, ToolRegistry, MessageBus
from ai_tool_handlers import TOOL_HANDLERS

# Create router
router = APIRouter(prefix="/api/ai", tags=["AI System"])


# ============================================================================
# AGENT MANAGEMENT
# ============================================================================

@router.get("/agents")
async def list_agents(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all AI agents"""
    query = text("""
        SELECT id, name, description, agent_type, status,
               goals, tools, triggers, version
        FROM ai_agents
        WHERE (:status IS NULL OR status = :status)
        ORDER BY name
    """)

    results = db.execute(query, {"status": status}).fetchall()

    agents = []
    for row in results:
        agents.append({
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "agent_type": row.agent_type,
            "status": row.status,
            "goals": row.goals,
            "tools": row.tools,
            "triggers": row.triggers,
            "version": row.version
        })

    return {
        "agents": agents,
        "count": len(agents)
    }


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Get specific agent details"""
    registry = AgentRegistry(db)
    agent = await registry.get_agent(agent_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return agent.dict()


@router.post("/agents/{agent_id}/execute")
async def execute_agent_manually(
    agent_id: str,
    request: ExecuteAgentRequest,
    db: Session = Depends(get_db)
):
    """Manually execute an agent"""
    from ai_models import AgentEvent, EventStatus

    orchestrator = AgentOrchestrator(db)
    registry = AgentRegistry(db)

    # Get agent
    agent = await registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Create event
    event = AgentEvent(
        event_id=str(uuid.uuid4()),
        event_type=request.event_type,
        source="user",
        payload=request.payload,
        status=EventStatus.PENDING
    )

    # Execute
    try:
        execution = await orchestrator.execute_agent(agent, event)

        return ExecuteAgentResponse(
            execution_id=execution.execution_id,
            status=execution.status,
            output=execution.output,
            confidence_score=execution.confidence_score
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Execution failed: {str(e)}"
        )


# ============================================================================
# EVENT DISPATCH
# ============================================================================

@router.post("/events")
async def dispatch_event(
    request: DispatchEventRequest,
    db: Session = Depends(get_db)
):
    """Dispatch an event to appropriate agents"""
    from ai_models import AgentEvent, EventStatus

    orchestrator = AgentOrchestrator(db)

    event = AgentEvent(
        event_id=str(uuid.uuid4()),
        event_type=request.event_type,
        source="api",
        payload=request.payload,
        status=EventStatus.PENDING
    )

    # Dispatch to agents
    try:
        executions = await orchestrator.dispatch_event(event)

        return {
            "event_id": event.event_id,
            "agents_triggered": len(executions),
            "executions": [
                {
                    "execution_id": ex.execution_id,
                    "agent_id": ex.agent_id,
                    "status": ex.status.value
                }
                for ex in executions
            ]
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Event dispatch failed: {str(e)}"
        )


# ============================================================================
# EXECUTION MONITORING
# ============================================================================

@router.get("/executions")
async def list_executions(
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List agent executions"""
    query = text("""
        SELECT
            ae.execution_id,
            ae.agent_id,
            a.name as agent_name,
            ae.tool_name,
            ae.status,
            ae.duration_ms,
            ae.confidence_score,
            ae.user_feedback,
            ae.entity_type,
            ae.entity_id,
            ae.created_at
        FROM ai_agent_executions ae
        JOIN ai_agents a ON ae.agent_id = a.id
        WHERE (:agent_id IS NULL OR ae.agent_id = :agent_id)
        AND (:status IS NULL OR ae.status = :status)
        ORDER BY ae.created_at DESC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "agent_id": agent_id,
        "status": status,
        "limit": limit
    }).fetchall()

    executions = []
    for row in results:
        executions.append({
            "execution_id": row.execution_id,
            "agent_id": row.agent_id,
            "agent_name": row.agent_name,
            "tool_name": row.tool_name,
            "status": row.status,
            "duration_ms": row.duration_ms,
            "confidence_score": row.confidence_score,
            "user_feedback": row.user_feedback,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat() if row.created_at else None
        })

    return {
        "executions": executions,
        "count": len(executions)
    }


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db)
):
    """Get specific execution details"""
    query = text("""
        SELECT
            ae.*,
            a.name as agent_name
        FROM ai_agent_executions ae
        JOIN ai_agents a ON ae.agent_id = a.id
        WHERE ae.execution_id = :execution_id
    """)

    result = db.execute(query, {"execution_id": execution_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Execution not found")

    return dict(result._mapping)


# ============================================================================
# FEEDBACK
# ============================================================================

@router.post("/feedback")
async def provide_feedback(
    request: ProvideExecutionFeedbackRequest,
    db: Session = Depends(get_db)
):
    """Provide feedback on an agent execution"""
    query = text("""
        UPDATE ai_agent_executions
        SET user_feedback = :feedback,
            user_feedback_comment = :comment,
            user_id = :user_id
        WHERE execution_id = :execution_id
        RETURNING execution_id
    """)

    result = db.execute(query, {
        "execution_id": request.execution_id,
        "feedback": request.feedback,
        "comment": request.comment,
        "user_id": request.user_id
    }).fetchone()

    db.commit()

    if not result:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "success": True,
        "message": "Feedback recorded"
    }


# ============================================================================
# MESSAGES
# ============================================================================

@router.get("/messages")
async def list_messages(
    agent_id: Optional[str] = None,
    status: Optional[str] = "pending",
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List agent messages"""
    query = text("""
        SELECT
            m.message_id,
            m.from_agent_id,
            fa.name as from_agent_name,
            m.to_agent_id,
            ta.name as to_agent_name,
            m.message_type,
            m.subject,
            m.content,
            m.priority,
            m.status,
            m.requires_human_review,
            m.created_at
        FROM ai_agent_messages m
        LEFT JOIN ai_agents fa ON m.from_agent_id = fa.id
        LEFT JOIN ai_agents ta ON m.to_agent_id = ta.id
        WHERE (:agent_id IS NULL OR m.to_agent_id = :agent_id OR m.from_agent_id = :agent_id)
        AND (:status IS NULL OR m.status = :status)
        ORDER BY
            CASE m.priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                WHEN 'low' THEN 4
            END,
            m.created_at DESC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "agent_id": agent_id,
        "status": status,
        "limit": limit
    }).fetchall()

    messages = []
    for row in results:
        messages.append({
            "message_id": row.message_id,
            "from_agent_id": row.from_agent_id,
            "from_agent_name": row.from_agent_name,
            "to_agent_id": row.to_agent_id,
            "to_agent_name": row.to_agent_name,
            "message_type": row.message_type,
            "subject": row.subject,
            "content": row.content,
            "priority": row.priority,
            "status": row.status,
            "requires_human_review": row.requires_human_review,
            "created_at": row.created_at.isoformat() if row.created_at else None
        })

    return {
        "messages": messages,
        "count": len(messages)
    }


@router.post("/messages/{message_id}/process")
async def process_message(
    message_id: str,
    db: Session = Depends(get_db)
):
    """Mark message as processed"""
    query = text("""
        UPDATE ai_agent_messages
        SET status = 'processed'
        WHERE message_id = :message_id
        RETURNING message_id
    """)

    result = db.execute(query, {"message_id": message_id}).fetchone()
    db.commit()

    if not result:
        raise HTTPException(status_code=404, detail="Message not found")

    return {
        "success": True,
        "message": "Message marked as processed"
    }


# ============================================================================
# ANALYTICS
# ============================================================================

@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get analytics dashboard data"""
    # Agent execution stats
    exec_query = text("""
        SELECT
            agent_id,
            a.name as agent_name,
            COUNT(*) as total_executions,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
            AVG(duration_ms) as avg_duration_ms,
            AVG(confidence_score) as avg_confidence
        FROM ai_agent_executions ae
        JOIN ai_agents a ON ae.agent_id = a.id
        WHERE ae.created_at > CURRENT_TIMESTAMP - INTERVAL ':hours hours'
        GROUP BY agent_id, a.name
        ORDER BY total_executions DESC
    """)

    exec_results = db.execute(exec_query, {"hours": hours}).fetchall()

    agent_stats = []
    for row in exec_results:
        success_rate = (row.successful / row.total_executions * 100) if row.total_executions > 0 else 0
        agent_stats.append({
            "agent_id": row.agent_id,
            "agent_name": row.agent_name,
            "total_executions": row.total_executions,
            "success_rate": round(success_rate, 2),
            "avg_duration_ms": round(row.avg_duration_ms or 0, 0),
            "avg_confidence": round(row.avg_confidence or 0, 2)
        })

    # Overall stats
    overall_query = text("""
        SELECT
            COUNT(*) as total_executions,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
            AVG(duration_ms) as avg_duration_ms
        FROM ai_agent_executions
        WHERE created_at > CURRENT_TIMESTAMP - INTERVAL ':hours hours'
    """)

    overall = db.execute(overall_query, {"hours": hours}).fetchone()

    total = overall.total_executions or 0
    success_rate = (overall.successful / total * 100) if total > 0 else 100

    return {
        "period_hours": hours,
        "overall": {
            "total_executions": total,
            "success_rate": round(success_rate, 2),
            "avg_response_time_ms": round(overall.avg_duration_ms or 0, 0),
            "status": "healthy" if success_rate > 95 else "degraded"
        },
        "agents": agent_stats
    }


@router.get("/analytics/agent/{agent_id}")
async def get_agent_analytics(
    agent_id: str,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get analytics for specific agent"""
    # Daily execution counts
    daily_query = text("""
        SELECT
            DATE_TRUNC('day', created_at) as day,
            COUNT(*) as executions,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful
        FROM ai_agent_executions
        WHERE agent_id = :agent_id
        AND created_at > CURRENT_TIMESTAMP - INTERVAL ':days days'
        GROUP BY day
        ORDER BY day
    """)

    daily_results = db.execute(daily_query, {"agent_id": agent_id, "days": days}).fetchall()

    daily_stats = []
    for row in daily_results:
        success_rate = (row.successful / row.executions * 100) if row.executions > 0 else 0
        daily_stats.append({
            "date": row.day.isoformat() if row.day else None,
            "executions": row.executions,
            "success_rate": round(success_rate, 2)
        })

    return {
        "agent_id": agent_id,
        "period_days": days,
        "daily_stats": daily_stats
    }


# ============================================================================
# TOOLS
# ============================================================================

@router.get("/tools")
async def list_tools(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all available tools"""
    query = text("""
        SELECT name, description, category, allowed_agents,
               risk_level, requires_approval, is_active,
               execution_count, avg_duration_ms, success_rate
        FROM ai_tools
        WHERE (:category IS NULL OR category = :category)
        AND is_active = TRUE
        ORDER BY name
    """)

    results = db.execute(query, {"category": category}).fetchall()

    tools = []
    for row in results:
        tools.append({
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "allowed_agents": row.allowed_agents,
            "risk_level": row.risk_level,
            "requires_approval": row.requires_approval,
            "execution_count": row.execution_count,
            "avg_duration_ms": row.avg_duration_ms,
            "success_rate": row.success_rate
        })

    return {
        "tools": tools,
        "count": len(tools)
    }
