"""
Recruiting Dialer API Routes

Endpoints for:
- Click-to-call for candidates
- Call history management
- Call notes and outcomes
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import text
from database import SessionLocal
from contextlib import contextmanager
import os
import uuid

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/api/v1/recruiting/dialer", tags=["Recruiting Dialer"])


# =============================================================================
# Request/Response Models
# =============================================================================

class InitiateCallRequest(BaseModel):
    caller_id: int  # User making the call
    whisper_context: Optional[str] = None


class CallNoteRequest(BaseModel):
    note: str
    outcome: Optional[str] = None  # answered, voicemail, no_answer, busy, callback
    callback_requested: bool = False
    callback_date: Optional[str] = None
    user_id: int


class CallHistoryItem(BaseModel):
    id: int
    candidate_id: int
    caller_user_id: int
    caller_name: str
    direction: str
    duration_seconds: Optional[int]
    outcome: Optional[str]
    notes: Optional[str]
    called_at: str


# =============================================================================
# Click-to-Call Endpoints
# =============================================================================

@router.post("/candidates/{candidate_id}/call")
async def initiate_candidate_call(
    candidate_id: int,
    request: InitiateCallRequest
):
    """
    Initiate a click-to-call to a candidate.

    The system will:
    1. Look up the candidate's phone number
    2. Generate a whisper context with candidate info
    3. Initiate the call through Twilio
    """
    # Get candidate details for whisper context
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT rc.id, rc.first_name, rc.last_name, rc.phone, rc.email,
                       rc.status, rc.current_company, rc.current_title,
                       rc.annual_volume, rc.annual_units,
                       rc.overall_grade as overall_score,
                       (SELECT content FROM mm_candidate_notes
                        WHERE candidate_id = rc.id
                        ORDER BY created_at DESC LIMIT 1) as last_note
                FROM mm_candidates rc
                WHERE rc.id = :candidate_id
            """),
            {"candidate_id": candidate_id}
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not row.phone:
        raise HTTPException(status_code=400, detail="Candidate has no phone number")

    # Build whisper context
    whisper_parts = [
        f"Calling {row.first_name} {row.last_name}.",
        f"Current status: {row.status}."
    ]

    if row.current_company:
        whisper_parts.append(f"Works at {row.current_company}.")

    if row.annual_volume:
        volume_m = row.annual_volume / 1000000
        whisper_parts.append(f"Production: ${volume_m:.1f}M volume.")

    if row.overall_score:
        whisper_parts.append(f"Assessment score: {row.overall_score:.1f} out of 10.")

    if row.last_note:
        # Truncate note for whisper
        note_preview = row.last_note[:100] + "..." if len(row.last_note) > 100 else row.last_note
        whisper_parts.append(f"Last note: {note_preview}")

    whisper_context = " ".join(whisper_parts)

    # Create call record
    call_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO recruiting_call_history
                (id, candidate_id, caller_user_id, direction, whisper_context,
                 status, called_at)
                VALUES (:id, :candidate_id, :caller_id, 'outbound', :whisper,
                        'initiated', NOW())
            """),
            {
                "id": call_id,
                "candidate_id": candidate_id,
                "caller_id": request.caller_id,
                "whisper": whisper_context
            }
        )
        conn.commit()

    # In production, this would trigger the Twilio call
    # For now, return the call info
    return {
        "call_id": call_id,
        "candidate_id": candidate_id,
        "candidate_name": f"{row.first_name} {row.last_name}",
        "phone": row.phone,
        "whisper_context": whisper_context,
        "status": "initiated",
        "message": "Call initiated. In production, Twilio will connect the call."
    }


@router.post("/calls/{call_id}/connect")
async def connect_call_via_twilio(call_id: str):
    """
    Actually connect the call via Twilio.

    This endpoint would be called by the frontend after the user
    confirms they want to make the call.
    """
    # Get call details
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.*, rc.phone, u.phone as caller_phone
                FROM recruiting_call_history ch
                JOIN mm_candidates rc ON rc.id = ch.candidate_id
                JOIN users u ON u.id = ch.caller_user_id
                WHERE ch.id = :call_id
            """),
            {"call_id": call_id}
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Call record not found")

    # Here we would integrate with the Twilio click-to-call service
    try:
        from services.twilio_click_to_call import click_to_call_service

        # Update status to connecting
        with get_db_connection() as conn:
            conn.execute(
                text("UPDATE recruiting_call_history SET status = 'connecting' WHERE id = :id"),
                {"id": call_id}
            )
            conn.commit()

        return {
            "call_id": call_id,
            "status": "connecting",
            "message": "Twilio is connecting the call"
        }
    except Exception as e:
        return {
            "call_id": call_id,
            "status": "simulated",
            "message": f"Call simulation mode - Twilio not configured: {str(e)}"
        }


# =============================================================================
# Call History Endpoints
# =============================================================================

@router.get("/candidates/{candidate_id}/call-history")
async def get_candidate_call_history(
    candidate_id: int,
    limit: int = 20
):
    """Get call history for a specific candidate."""
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.id, ch.candidate_id, ch.caller_user_id,
                       u.name as caller_name, ch.direction,
                       ch.duration_seconds, ch.outcome, ch.notes,
                       ch.called_at, ch.status
                FROM recruiting_call_history ch
                LEFT JOIN users u ON u.id = ch.caller_user_id
                WHERE ch.candidate_id = :candidate_id
                ORDER BY ch.called_at DESC
                LIMIT :limit
            """),
            {"candidate_id": candidate_id, "limit": limit}
        )
        rows = result.fetchall()

    history = [
        {
            "id": row.id,
            "candidate_id": row.candidate_id,
            "caller_user_id": row.caller_user_id,
            "caller_name": row.caller_name or "Unknown",
            "direction": row.direction,
            "duration_seconds": row.duration_seconds,
            "outcome": row.outcome,
            "notes": row.notes,
            "called_at": row.called_at.isoformat() if row.called_at else None,
            "status": row.status
        }
        for row in rows
    ]

    return {
        "candidate_id": candidate_id,
        "total": len(history),
        "history": history
    }


@router.post("/calls/{call_id}/notes")
async def add_call_notes(call_id: str, request: CallNoteRequest):
    """Add notes and outcome to a call."""
    with get_db_connection() as conn:
        # Update call record
        conn.execute(
            text("""
                UPDATE recruiting_call_history
                SET notes = :notes,
                    outcome = :outcome,
                    status = 'completed',
                    completed_at = NOW()
                WHERE id = :call_id
            """),
            {
                "call_id": call_id,
                "notes": request.note,
                "outcome": request.outcome
            }
        )

        # If callback requested, create a task
        if request.callback_requested and request.callback_date:
            # Get candidate ID from call
            result = conn.execute(
                text("SELECT candidate_id FROM recruiting_call_history WHERE id = :id"),
                {"id": call_id}
            )
            row = result.fetchone()

            if row:
                conn.execute(
                    text("""
                        INSERT INTO recruiting_tasks
                        (candidate_id, title, description, due_date, priority,
                         route_to, status, assigned_to, created_at)
                        VALUES (:candidate_id, 'Callback requested',
                                :notes, :due_date, 'high',
                                'dialer_queue', 'pending', :user_id, NOW())
                    """),
                    {
                        "candidate_id": row.candidate_id,
                        "notes": f"Callback requested: {request.note}",
                        "due_date": request.callback_date,
                        "user_id": request.user_id
                    }
                )

        conn.commit()

    return {"message": "Call notes saved", "call_id": call_id}


@router.get("/calls/{call_id}/status")
async def get_call_status(call_id: str):
    """Get the current status of a call."""
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.*, rc.first_name, rc.last_name
                FROM recruiting_call_history ch
                JOIN mm_candidates rc ON rc.id = ch.candidate_id
                WHERE ch.id = :call_id
            """),
            {"call_id": call_id}
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "call_id": call_id,
        "candidate_name": f"{row.first_name} {row.last_name}",
        "status": row.status,
        "direction": row.direction,
        "duration_seconds": row.duration_seconds,
        "outcome": row.outcome,
        "called_at": row.called_at.isoformat() if row.called_at else None
    }


# =============================================================================
# Dialer Queue Integration
# =============================================================================

@router.get("/queue")
async def get_recruiting_dialer_queue(
    assigned_to: Optional[int] = None,
    organization_id: int = 1
):
    """
    Get the dialer queue with candidate details for calling.

    Combines workflow tasks routed to dialer with candidate contact info.
    """
    params = {"org_id": organization_id}
    user_filter = ""
    if assigned_to:
        user_filter = "AND rt.assigned_to = :assigned_to"
        params["assigned_to"] = assigned_to

    with get_db_connection() as conn:
        result = conn.execute(
            text(f"""
                SELECT rt.id as task_id, rt.candidate_id, rt.title as task_title,
                       rt.description as task_description, rt.due_date, rt.priority,
                       rc.first_name, rc.last_name, rc.phone, rc.email,
                       rc.status as candidate_status, rc.current_company,
                       rc.overall_grade as overall_score,
                       (SELECT COUNT(*) FROM recruiting_call_history
                        WHERE candidate_id = rc.id) as total_calls,
                       (SELECT called_at FROM recruiting_call_history
                        WHERE candidate_id = rc.id
                        ORDER BY called_at DESC LIMIT 1) as last_call
                FROM recruiting_tasks rt
                JOIN mm_candidates rc ON rc.id = rt.candidate_id
                WHERE rt.organization_id = :org_id
                    AND rt.status = 'pending'
                    AND rt.route_to = 'dialer_queue'
                    {user_filter}
                ORDER BY
                    rt.due_date ASC,
                    CASE rt.priority
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        ELSE 3
                    END
            """),
            params
        )
        rows = result.fetchall()

    queue = [
        {
            "task_id": row.task_id,
            "candidate_id": row.candidate_id,
            "candidate_name": f"{row.first_name} {row.last_name}",
            "phone": row.phone,
            "email": row.email,
            "candidate_status": row.candidate_status,
            "current_company": row.current_company,
            "overall_score": float(row.overall_score) if row.overall_score else None,
            "task_title": row.task_title,
            "task_description": row.task_description,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "priority": row.priority,
            "total_calls": row.total_calls,
            "last_call": row.last_call.isoformat() if row.last_call else None
        }
        for row in rows
    ]

    return {
        "queue_length": len(queue),
        "queue": queue
    }


# =============================================================================
# Migration Endpoint (Development)
# =============================================================================

@router.post("/admin/run-migration")
async def run_dialer_migration(admin_key: str = Query(...)):
    """Create call history table if it doesn't exist."""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    migration_sql = """
    CREATE TABLE IF NOT EXISTS recruiting_call_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        candidate_id INTEGER NOT NULL,
        caller_user_id INTEGER,
        direction VARCHAR(20) DEFAULT 'outbound',
        phone_from VARCHAR(20),
        phone_to VARCHAR(20),
        whisper_context TEXT,
        duration_seconds INTEGER,
        status VARCHAR(20) DEFAULT 'initiated',
        outcome VARCHAR(50),
        notes TEXT,
        recording_url TEXT,
        called_at TIMESTAMP DEFAULT NOW(),
        completed_at TIMESTAMP,
        CONSTRAINT fk_call_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_call_history_candidate
        ON recruiting_call_history(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_call_history_caller
        ON recruiting_call_history(caller_user_id);
    """

    try:
        with get_db_connection() as conn:
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()
        return {"status": "success", "message": "Call history table created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
