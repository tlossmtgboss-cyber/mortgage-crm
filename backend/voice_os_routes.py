"""
Voice OS API Routes
CRUD operations for Voice OS agents, phone numbers, call sessions, and analytics
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logging
import uuid

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice-os"])

# Auth dependency - lazy loaded to avoid circular imports
# FAIL CLOSED - do not fall back to None
_get_current_user = None

def set_auth_dependency(get_current_user_func):
    """Set the auth dependency from main.py to avoid circular imports"""
    global _get_current_user
    if get_current_user_func is None:
        raise ValueError("Cannot set auth dependency to None")
    _get_current_user = get_current_user_func

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - raises 503 if auth not initialized, 401 if not authenticated"""
    if _get_current_user is None:
        logger.error("Voice OS auth dependency not initialized - rejecting request")
        raise HTTPException(status_code=503, detail="Auth not initialized")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    voice_id: str = "alloy"
    voice_stability: float = Field(default=0.5, ge=0, le=1)
    voice_similarity: float = Field(default=0.75, ge=0, le=1)
    voice_style: float = Field(default=0.5, ge=0, le=1)
    system_prompt: str
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=150, ge=1, le=4096)
    interrupt_enabled: bool = True
    filler_words_enabled: bool = True
    backchanneling_enabled: bool = True
    emotion_detection_enabled: bool = True
    tools_allowed: List[str] = Field(default_factory=lambda: [
        "get_contact_by_phone", "create_lead", "schedule_appointment"
    ])


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    voice_id: Optional[str] = None
    voice_stability: Optional[float] = None
    voice_similarity: Optional[float] = None
    voice_style: Optional[float] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    interrupt_enabled: Optional[bool] = None
    filler_words_enabled: Optional[bool] = None
    backchanneling_enabled: Optional[bool] = None
    emotion_detection_enabled: Optional[bool] = None
    tools_allowed: Optional[List[str]] = None


class PhoneNumberAssign(BaseModel):
    e164_number: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")
    friendly_name: Optional[str] = None
    agent_id: Optional[str] = None


class CallSessionUpdate(BaseModel):
    status: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    outcome: Optional[str] = None


# =============================================================================
# AGENTS ENDPOINTS
# =============================================================================

@router.get("/agents")
async def list_agents(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (active/inactive)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all Voice OS agents with optional filtering"""
    try:
        params = {"limit": limit, "offset": offset}
        where_clause = ""

        if status:
            where_clause = "WHERE status = :status"
            params["status"] = status

        result = db.execute(text(f"""
            SELECT
                id, name, description, status,
                voice_id, voice_stability, voice_similarity, voice_style,
                system_prompt, temperature, max_tokens,
                interrupt_enabled, filler_words_enabled,
                backchanneling_enabled, emotion_detection_enabled,
                tools_allowed,
                total_calls, successful_calls, avg_duration_seconds, avg_satisfaction,
                created_at, updated_at
            FROM voice_os_agents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params)

        agents = []
        for row in result.fetchall():
            agents.append({
                "id": str(row[0]),
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "voice_id": row[4],
                "voice_stability": float(row[5]) if row[5] else 0.5,
                "voice_similarity": float(row[6]) if row[6] else 0.75,
                "voice_style": float(row[7]) if row[7] else 0.5,
                "system_prompt": row[8],
                "temperature": float(row[9]) if row[9] else 0.7,
                "max_tokens": row[10] or 150,
                "interrupt_enabled": row[11],
                "filler_words_enabled": row[12],
                "backchanneling_enabled": row[13],
                "emotion_detection_enabled": row[14],
                "tools_allowed": row[15] or [],
                "total_calls": row[16] or 0,
                "successful_calls": row[17] or 0,
                "avg_duration_seconds": row[18] or 0,
                "avg_satisfaction": float(row[19]) if row[19] else None,
                "created_at": row[20].isoformat() if row[20] else None,
                "updated_at": row[21].isoformat() if row[21] else None
            })

        # Get total count
        count_result = db.execute(text(f"""
            SELECT COUNT(*) FROM voice_os_agents {where_clause}
        """), params if status else {})
        total = count_result.scalar()

        return {
            "agents": agents,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/agents/{agent_id}")
async def get_agent(request: Request, agent_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Get a single Voice OS agent by ID"""
    try:
        result = db.execute(text("""
            SELECT
                id, name, description, status,
                voice_id, voice_stability, voice_similarity, voice_style,
                system_prompt, temperature, max_tokens,
                interrupt_enabled, filler_words_enabled,
                backchanneling_enabled, emotion_detection_enabled,
                tools_allowed,
                total_calls, successful_calls, avg_duration_seconds, avg_satisfaction,
                created_at, updated_at
            FROM voice_os_agents
            WHERE id = :agent_id
        """), {"agent_id": agent_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "status": row[3],
            "voice_id": row[4],
            "voice_stability": float(row[5]) if row[5] else 0.5,
            "voice_similarity": float(row[6]) if row[6] else 0.75,
            "voice_style": float(row[7]) if row[7] else 0.5,
            "system_prompt": row[8],
            "temperature": float(row[9]) if row[9] else 0.7,
            "max_tokens": row[10] or 150,
            "interrupt_enabled": row[11],
            "filler_words_enabled": row[12],
            "backchanneling_enabled": row[13],
            "emotion_detection_enabled": row[14],
            "tools_allowed": row[15] or [],
            "total_calls": row[16] or 0,
            "successful_calls": row[17] or 0,
            "avg_duration_seconds": row[18] or 0,
            "avg_satisfaction": float(row[19]) if row[19] else None,
            "created_at": row[20].isoformat() if row[20] else None,
            "updated_at": row[21].isoformat() if row[21] else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/agents")
async def create_agent(request: Request, agent: AgentCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Create a new Voice OS agent"""
    try:
        import json

        result = db.execute(text("""
            INSERT INTO voice_os_agents (
                name, description, status,
                voice_id, voice_stability, voice_similarity, voice_style,
                system_prompt, temperature, max_tokens,
                interrupt_enabled, filler_words_enabled,
                backchanneling_enabled, emotion_detection_enabled,
                tools_allowed
            ) VALUES (
                :name, :description, 'active',
                :voice_id, :voice_stability, :voice_similarity, :voice_style,
                :system_prompt, :temperature, :max_tokens,
                :interrupt_enabled, :filler_words_enabled,
                :backchanneling_enabled, :emotion_detection_enabled,
                :tools_allowed::jsonb
            )
            RETURNING id, created_at
        """), {
            "name": agent.name,
            "description": agent.description,
            "voice_id": agent.voice_id,
            "voice_stability": agent.voice_stability,
            "voice_similarity": agent.voice_similarity,
            "voice_style": agent.voice_style,
            "system_prompt": agent.system_prompt,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "interrupt_enabled": agent.interrupt_enabled,
            "filler_words_enabled": agent.filler_words_enabled,
            "backchanneling_enabled": agent.backchanneling_enabled,
            "emotion_detection_enabled": agent.emotion_detection_enabled,
            "tools_allowed": json.dumps(agent.tools_allowed)
        })

        row = result.fetchone()
        db.commit()

        logger.info(f"Created Voice OS agent: {agent.name} (ID: {row[0]})")

        return {
            "id": str(row[0]),
            "name": agent.name,
            "status": "active",
            "created_at": row[1].isoformat() if row[1] else None,
            "message": "Agent created successfully"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/agents/{agent_id}")
async def update_agent(request: Request, agent_id: str, updates: AgentUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Update a Voice OS agent"""
    try:
        import json

        # Build dynamic update query
        update_fields = []
        params = {"agent_id": agent_id}

        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is not None:
                if field == "tools_allowed":
                    update_fields.append(f"{field} = :{field}::jsonb")
                    params[field] = json.dumps(value)
                else:
                    update_fields.append(f"{field} = :{field}")
                    params[field] = value

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_fields.append("updated_at = NOW()")

        result = db.execute(text(f"""
            UPDATE voice_os_agents
            SET {', '.join(update_fields)}
            WHERE id = :agent_id
            RETURNING id, name, status, updated_at
        """), params)

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")

        db.commit()

        logger.info(f"Updated Voice OS agent: {row[1]} (ID: {row[0]})")

        return {
            "id": str(row[0]),
            "name": row[1],
            "status": row[2],
            "updated_at": row[3].isoformat() if row[3] else None,
            "message": "Agent updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/agents/{agent_id}")
async def delete_agent(request: Request, agent_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Delete a Voice OS agent"""
    try:
        # Check if agent has active calls
        active_calls = db.execute(text("""
            SELECT COUNT(*) FROM voice_os_call_sessions
            WHERE agent_id = :agent_id AND status IN ('ringing', 'in_progress')
        """), {"agent_id": agent_id}).scalar()

        if active_calls > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete agent with {active_calls} active calls"
            )

        result = db.execute(text("""
            DELETE FROM voice_os_agents WHERE id = :agent_id
            RETURNING name
        """), {"agent_id": agent_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")

        db.commit()

        logger.info(f"Deleted Voice OS agent: {row[0]} (ID: {agent_id})")

        return {"message": f"Agent '{row[0]}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PHONE NUMBERS ENDPOINTS
# =============================================================================

@router.get("/phone-numbers")
async def list_phone_numbers(
    request: Request,
    enabled: Optional[bool] = None,
    agent_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all Voice OS phone numbers"""
    try:
        params = {}
        where_clauses = []

        if enabled is not None:
            where_clauses.append("p.enabled = :enabled")
            params["enabled"] = enabled

        if agent_id:
            where_clauses.append("p.agent_id = :agent_id")
            params["agent_id"] = agent_id

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        result = db.execute(text(f"""
            SELECT
                p.id, p.e164_number, p.friendly_name, p.agent_id, p.enabled, p.created_at,
                a.name as agent_name
            FROM voice_os_phone_numbers p
            LEFT JOIN voice_os_agents a ON a.id = p.agent_id
            {where_sql}
            ORDER BY p.created_at DESC
        """), params)

        phone_numbers = []
        for row in result.fetchall():
            phone_numbers.append({
                "id": str(row[0]),
                "e164_number": row[1],
                "friendly_name": row[2],
                "agent_id": str(row[3]) if row[3] else None,
                "agent_name": row[6],
                "enabled": row[4],
                "created_at": row[5].isoformat() if row[5] else None
            })

        return {"phone_numbers": phone_numbers, "total": len(phone_numbers)}

    except Exception as e:
        logger.error(f"Error listing phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/phone-numbers")
async def assign_phone_number(request: Request, data: PhoneNumberAssign, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Assign a phone number to a Voice OS agent"""
    try:
        result = db.execute(text("""
            INSERT INTO voice_os_phone_numbers (e164_number, friendly_name, agent_id, enabled)
            VALUES (:e164_number, :friendly_name, :agent_id, true)
            ON CONFLICT (e164_number) DO UPDATE
            SET agent_id = :agent_id, friendly_name = COALESCE(:friendly_name, voice_os_phone_numbers.friendly_name)
            RETURNING id, e164_number, agent_id
        """), {
            "e164_number": data.e164_number,
            "friendly_name": data.friendly_name,
            "agent_id": data.agent_id
        })

        row = result.fetchone()
        db.commit()

        return {
            "id": str(row[0]),
            "e164_number": row[1],
            "agent_id": str(row[2]) if row[2] else None,
            "message": "Phone number assigned successfully"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning phone number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/phone-numbers/{phone_id}")
async def unassign_phone_number(request: Request, phone_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Remove a phone number from Voice OS"""
    try:
        result = db.execute(text("""
            DELETE FROM voice_os_phone_numbers WHERE id = :phone_id
            RETURNING e164_number
        """), {"phone_id": phone_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Phone number not found")

        db.commit()

        return {"message": f"Phone number {row[0]} removed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing phone number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CALL SESSIONS ENDPOINTS
# =============================================================================

@router.get("/calls")
async def list_call_sessions(
    request: Request,
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    from_number: Optional[str] = None,
    outcome: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List Voice OS call sessions with filtering"""
    try:
        params = {"days": days, "limit": limit, "offset": offset}
        where_clauses = ["cs.start_time >= NOW() - :days * INTERVAL '1 day'"]

        if status:
            where_clauses.append("cs.status = :status")
            params["status"] = status

        if agent_id:
            where_clauses.append("cs.agent_id = :agent_id")
            params["agent_id"] = agent_id

        if from_number:
            where_clauses.append("cs.from_number LIKE :from_number")
            params["from_number"] = f"%{from_number}%"

        if outcome:
            where_clauses.append("cs.outcome = :outcome")
            params["outcome"] = outcome

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        result = db.execute(text(f"""
            SELECT
                cs.id, cs.call_sid, cs.agent_id, cs.direction,
                cs.from_number, cs.to_number, cs.status,
                cs.start_time, cs.answer_time, cs.end_time, cs.duration_seconds,
                cs.contact_id, cs.contact_name, cs.contact_email,
                cs.summary, cs.sentiment, cs.emotion_detected, cs.outcome,
                cs.escalated, cs.recording_url,
                a.name as agent_name
            FROM voice_os_call_sessions cs
            LEFT JOIN voice_os_agents a ON a.id = cs.agent_id
            {where_sql}
            ORDER BY cs.start_time DESC
            LIMIT :limit OFFSET :offset
        """), params)

        calls = []
        for row in result.fetchall():
            calls.append({
                "id": str(row[0]),
                "call_sid": row[1],
                "agent_id": str(row[2]) if row[2] else None,
                "agent_name": row[20],
                "direction": row[3],
                "from_number": row[4],
                "to_number": row[5],
                "status": row[6],
                "start_time": row[7].isoformat() if row[7] else None,
                "answer_time": row[8].isoformat() if row[8] else None,
                "end_time": row[9].isoformat() if row[9] else None,
                "duration_seconds": row[10],
                "contact_id": str(row[11]) if row[11] else None,
                "contact_name": row[12],
                "contact_email": row[13],
                "summary": row[14],
                "sentiment": row[15],
                "emotion_detected": row[16],
                "outcome": row[17],
                "escalated": row[18],
                "recording_url": row[19]
            })

        # Get total count
        count_result = db.execute(text(f"""
            SELECT COUNT(*) FROM voice_os_call_sessions cs {where_sql}
        """), params)
        total = count_result.scalar()

        return {
            "calls": calls,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing call sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/calls/live")
async def get_live_calls(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Get currently active calls for live monitoring"""
    try:
        result = db.execute(text("""
            SELECT
                cs.id, cs.call_sid, cs.agent_id, cs.direction,
                cs.from_number, cs.to_number, cs.status,
                cs.start_time, cs.answer_time,
                cs.contact_name, cs.emotion_detected,
                cs.transcript, cs.interruptions_count,
                a.name as agent_name
            FROM voice_os_call_sessions cs
            LEFT JOIN voice_os_agents a ON a.id = cs.agent_id
            WHERE cs.status IN ('ringing', 'in_progress')
            ORDER BY cs.start_time DESC
        """))

        live_calls = []
        for row in result.fetchall():
            start_time = row[7]
            duration = None
            if start_time:
                duration = int((datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds())

            live_calls.append({
                "id": str(row[0]),
                "call_sid": row[1],
                "agent_id": str(row[2]) if row[2] else None,
                "agent_name": row[13],
                "direction": row[3],
                "from_number": row[4],
                "to_number": row[5],
                "status": row[6],
                "start_time": row[7].isoformat() if row[7] else None,
                "answer_time": row[8].isoformat() if row[8] else None,
                "duration_seconds": duration,
                "contact_name": row[9],
                "emotion_detected": row[10],
                "transcript": row[11] or [],
                "interruptions_count": row[12] or 0
            })

        return {
            "live_calls": live_calls,
            "total_active": len(live_calls)
        }

    except Exception as e:
        logger.error(f"Error getting live calls: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/calls/{call_id}")
async def get_call_session(request: Request, call_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Get detailed call session including full transcript"""
    try:
        result = db.execute(text("""
            SELECT
                cs.id, cs.call_sid, cs.agent_id, cs.direction,
                cs.from_number, cs.to_number, cs.status,
                cs.start_time, cs.answer_time, cs.end_time, cs.duration_seconds,
                cs.contact_id, cs.contact_name, cs.contact_email,
                cs.transcript, cs.summary, cs.sentiment, cs.emotion_detected,
                cs.outcome, cs.intent_detected, cs.actions_taken,
                cs.interruptions_count, cs.avg_response_latency_ms,
                cs.escalated, cs.escalation_reason, cs.recording_url,
                cs.created_at,
                a.name as agent_name
            FROM voice_os_call_sessions cs
            LEFT JOIN voice_os_agents a ON a.id = cs.agent_id
            WHERE cs.id = :call_id
        """), {"call_id": call_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call session not found")

        return {
            "id": str(row[0]),
            "call_sid": row[1],
            "agent_id": str(row[2]) if row[2] else None,
            "agent_name": row[27],
            "direction": row[3],
            "from_number": row[4],
            "to_number": row[5],
            "status": row[6],
            "start_time": row[7].isoformat() if row[7] else None,
            "answer_time": row[8].isoformat() if row[8] else None,
            "end_time": row[9].isoformat() if row[9] else None,
            "duration_seconds": row[10],
            "contact": {
                "id": str(row[11]) if row[11] else None,
                "name": row[12],
                "email": row[13]
            },
            "transcript": row[14] or [],
            "summary": row[15],
            "sentiment": row[16],
            "emotion_detected": row[17],
            "outcome": row[18],
            "intent_detected": row[19],
            "actions_taken": row[20] or [],
            "quality_metrics": {
                "interruptions_count": row[21] or 0,
                "avg_response_latency_ms": row[22]
            },
            "escalation": {
                "escalated": row[23],
                "reason": row[24]
            },
            "recording_url": row[25],
            "created_at": row[26].isoformat() if row[26] else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/calls/{call_id}")
async def update_call_session(request: Request, call_id: str, updates: CallSessionUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Update a call session (for manual annotations)"""
    try:
        update_fields = []
        params = {"call_id": call_id}

        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = :{field}")
                params[field] = value

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = db.execute(text(f"""
            UPDATE voice_os_call_sessions
            SET {', '.join(update_fields)}
            WHERE id = :call_id
            RETURNING id
        """), params)

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call session not found")

        db.commit()

        return {"message": "Call session updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating call session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@router.get("/analytics")
async def get_voice_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    agent_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get Voice OS analytics and metrics"""
    try:
        params = {"days": days}
        agent_filter = ""

        if agent_id:
            agent_filter = "AND agent_id = :agent_id"
            params["agent_id"] = agent_id

        # Overall metrics
        metrics = db.execute(text(f"""
            SELECT
                COUNT(*) as total_calls,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_calls,
                COUNT(CASE WHEN outcome IN ('appointment_booked', 'lead_created', 'info_provided') THEN 1 END) as successful_calls,
                COUNT(CASE WHEN escalated = true THEN 1 END) as escalated_calls,
                AVG(duration_seconds) as avg_duration,
                AVG(avg_response_latency_ms) as avg_latency,
                COUNT(CASE WHEN direction = 'inbound' THEN 1 END) as inbound_calls,
                COUNT(CASE WHEN direction = 'outbound' THEN 1 END) as outbound_calls
            FROM voice_os_call_sessions
            WHERE start_time >= NOW() - :days * INTERVAL '1 day'
            {agent_filter}
        """), params).fetchone()

        # Calls by day
        daily_calls = db.execute(text(f"""
            SELECT
                DATE(start_time) as date,
                COUNT(*) as calls,
                COUNT(CASE WHEN outcome IN ('appointment_booked', 'lead_created', 'info_provided') THEN 1 END) as successful
            FROM voice_os_call_sessions
            WHERE start_time >= NOW() - :days * INTERVAL '1 day'
            {agent_filter}
            GROUP BY DATE(start_time)
            ORDER BY date DESC
            LIMIT 30
        """), params).fetchall()

        # Outcomes breakdown
        outcomes = db.execute(text(f"""
            SELECT
                outcome,
                COUNT(*) as count
            FROM voice_os_call_sessions
            WHERE start_time >= NOW() - :days * INTERVAL '1 day'
            AND outcome IS NOT NULL
            {agent_filter}
            GROUP BY outcome
            ORDER BY count DESC
        """), params).fetchall()

        # Sentiment breakdown
        sentiments = db.execute(text(f"""
            SELECT
                sentiment,
                COUNT(*) as count
            FROM voice_os_call_sessions
            WHERE start_time >= NOW() - :days * INTERVAL '1 day'
            AND sentiment IS NOT NULL
            {agent_filter}
            GROUP BY sentiment
        """), params).fetchall()

        total_calls = metrics[0] or 0
        completed_calls = metrics[1] or 0
        successful_calls = metrics[2] or 0

        return {
            "period_days": days,
            "summary": {
                "total_calls": total_calls,
                "completed_calls": completed_calls,
                "successful_calls": successful_calls,
                "success_rate": round((successful_calls / completed_calls * 100), 1) if completed_calls > 0 else 0,
                "escalated_calls": metrics[3] or 0,
                "escalation_rate": round((metrics[3] or 0) / total_calls * 100, 1) if total_calls > 0 else 0,
                "avg_duration_seconds": round(float(metrics[4] or 0), 1),
                "avg_response_latency_ms": round(float(metrics[5] or 0), 0),
                "inbound_calls": metrics[6] or 0,
                "outbound_calls": metrics[7] or 0
            },
            "daily_calls": [
                {"date": str(row[0]), "calls": row[1], "successful": row[2]}
                for row in daily_calls
            ],
            "outcomes": {row[0]: row[1] for row in outcomes},
            "sentiments": {row[0]: row[1] for row in sentiments}
        }

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/agents/{agent_id}/analytics")
async def get_agent_analytics(request: Request, agent_id: str, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Get analytics for a specific agent"""
    try:
        # Get agent info
        agent = db.execute(text("""
            SELECT name, total_calls, successful_calls, avg_duration_seconds, avg_satisfaction
            FROM voice_os_agents WHERE id = :agent_id
        """), {"agent_id": agent_id}).fetchone()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Get period metrics
        params = {"agent_id": agent_id, "days": days}

        period_metrics = db.execute(text("""
            SELECT
                COUNT(*) as calls,
                COUNT(CASE WHEN outcome IN ('appointment_booked', 'lead_created', 'info_provided') THEN 1 END) as successful,
                AVG(duration_seconds) as avg_duration,
                AVG(avg_response_latency_ms) as avg_latency,
                COUNT(CASE WHEN escalated = true THEN 1 END) as escalated
            FROM voice_os_call_sessions
            WHERE agent_id = :agent_id
            AND start_time >= NOW() - :days * INTERVAL '1 day'
        """), params).fetchone()

        # Top intents
        intents = db.execute(text("""
            SELECT intent_detected, COUNT(*) as count
            FROM voice_os_call_sessions
            WHERE agent_id = :agent_id
            AND start_time >= NOW() - :days * INTERVAL '1 day'
            AND intent_detected IS NOT NULL
            GROUP BY intent_detected
            ORDER BY count DESC
            LIMIT 10
        """), params).fetchall()

        # Hourly distribution
        hourly = db.execute(text("""
            SELECT
                EXTRACT(HOUR FROM start_time) as hour,
                COUNT(*) as calls
            FROM voice_os_call_sessions
            WHERE agent_id = :agent_id
            AND start_time >= NOW() - :days * INTERVAL '1 day'
            GROUP BY EXTRACT(HOUR FROM start_time)
            ORDER BY hour
        """), params).fetchall()

        period_calls = period_metrics[0] or 0
        period_successful = period_metrics[1] or 0

        return {
            "agent": {
                "id": agent_id,
                "name": agent[0],
                "lifetime_calls": agent[1] or 0,
                "lifetime_successful": agent[2] or 0,
                "lifetime_avg_duration": agent[3] or 0,
                "avg_satisfaction": float(agent[4]) if agent[4] else None
            },
            "period": {
                "days": days,
                "calls": period_calls,
                "successful": period_successful,
                "success_rate": round((period_successful / period_calls * 100), 1) if period_calls > 0 else 0,
                "avg_duration_seconds": round(float(period_metrics[2] or 0), 1),
                "avg_response_latency_ms": round(float(period_metrics[3] or 0), 0),
                "escalated": period_metrics[4] or 0
            },
            "top_intents": [{"intent": row[0], "count": row[1]} for row in intents],
            "hourly_distribution": {int(row[0]): row[1] for row in hourly}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/performance")
async def get_agent_performance_view(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Get agent performance from the materialized view"""
    try:
        result = db.execute(text("""
            SELECT * FROM voice_os_agent_performance
            ORDER BY total_calls DESC
        """))

        performance = []
        for row in result.fetchall():
            performance.append({
                "id": str(row[0]),
                "name": row[1],
                "status": row[2],
                "total_calls": row[3] or 0,
                "successful_calls": row[4] or 0,
                "success_rate_percent": float(row[5]) if row[5] else 0,
                "avg_duration_seconds": row[6] or 0,
                "avg_satisfaction": float(row[7]) if row[7] else None,
                "active_calls_now": row[8] or 0
            })

        return {"agents": performance}

    except Exception as e:
        logger.error(f"Error getting performance view: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
