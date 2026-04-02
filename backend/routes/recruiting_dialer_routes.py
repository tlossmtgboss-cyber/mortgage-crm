"""
Recruiting Dialer API Routes

Endpoints for:
- Click-to-call for candidates (Telnyx-integrated)
- Call history management
- Call notes and outcomes
- Telephony webhooks for call status
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Form, Response, Request
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import text
from database import SessionLocal
from auth.dependencies import get_current_user
from database.models import User
from contextlib import contextmanager
import os
import uuid
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

TELNYX_PUBLIC_KEY = os.getenv("TELNYX_PUBLIC_KEY")


async def _verify_telnyx_webhook(request: Request):
    """Validate Telnyx webhook signature. Fail-closed when key not configured."""
    if not TELNYX_PUBLIC_KEY:
        logger.error("TELNYX_PUBLIC_KEY not configured — rejecting recruiting dialer webhook")
        raise HTTPException(status_code=403, detail="Webhook validation not configured")

    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    if not signature or not timestamp:
        logger.warning("Missing Telnyx signature headers on recruiting dialer webhook")
        raise HTTPException(status_code=403, detail="Missing webhook signature")

    body = await request.body()

    try:
        from telephony.providers.telnyx.webhooks import validate_telnyx_webhook
        if not validate_telnyx_webhook(body, signature, timestamp, TELNYX_PUBLIC_KEY):
            logger.warning("Invalid Telnyx webhook signature on recruiting dialer")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
    except ImportError:
        logger.error("Telnyx webhook validation module not available")
        raise HTTPException(status_code=403, detail="Webhook validation unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telnyx signature validation error: {e}")
        raise HTTPException(status_code=403, detail="Webhook validation failed")

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

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
    caller_id: Optional[int] = None  # Deprecated: uses authenticated user
    whisper_context: Optional[str] = None


class CallNoteRequest(BaseModel):
    note: str
    outcome: Optional[str] = None  # answered, voicemail, no_answer, busy, callback
    callback_requested: bool = False
    callback_date: Optional[str] = None
    user_id: Optional[int] = None  # Deprecated: server uses current_user.id


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
    request: InitiateCallRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Initiate a click-to-call to a candidate via the telephony provider.

    The system will:
    1. Look up the candidate's phone number
    2. Generate a whisper context with candidate info
    3. Call the recruiter first
    4. Play whisper context to recruiter
    5. On recruiter confirmation, connect to candidate
    6. Record the call
    """
    org_id = current_user.organization_id

    # Get candidate details for whisper context
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT rc.id, rc.first_name, rc.last_name, rc.phone, rc.email,
                       rc.status, rc.current_company, rc.current_title,
                       rc.annual_volume, rc.annual_units,
                       (SELECT content FROM mm_candidate_notes
                        WHERE candidate_id = rc.id
                        ORDER BY created_at DESC LIMIT 1) as last_note
                FROM mm_candidates rc
                WHERE rc.id = :candidate_id AND rc.organization_id = :org_id
            """),
            {"candidate_id": candidate_id, "org_id": org_id}
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

    if row.last_note:
        # Truncate note for whisper
        note_preview = row.last_note[:100] + "..." if len(row.last_note) > 100 else row.last_note
        whisper_parts.append(f"Last note: {note_preview}")

    whisper_parts.append("Press 1 to connect now.")
    whisper_context = " ".join(whisper_parts)

    # Create call record
    call_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO recruiting_call_history
                (id, candidate_id, caller_user_id, direction, whisper_context,
                 phone_to, status, called_at)
                VALUES (:id, :candidate_id, :caller_id, 'outbound', :whisper,
                        :phone_to, 'initiated', NOW())
            """),
            {
                "id": call_id,
                "candidate_id": candidate_id,
                "caller_id": current_user.id,
                "whisper": whisper_context,
                "phone_to": row.phone,
            }
        )
        conn.commit()

    # Initiate call via telephony provider
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            result = service.initiate_call(
                call_id=call_id,
                candidate_id=candidate_id,
                caller_user_id=current_user.id,
                candidate_phone=row.phone,
                candidate_name=f"{row.first_name} {row.last_name}",
                whisper_context=whisper_context,
            )

        if result.success:
            return {
                "call_id": call_id,
                "call_sid": result.call_sid,
                "candidate_id": candidate_id,
                "candidate_name": f"{row.first_name} {row.last_name}",
                "phone": row.phone,
                "whisper_context": whisper_context,
                "status": result.status,
                "message": result.message,
            }
        else:
            # Return error but still have the call record for retry
            return {
                "call_id": call_id,
                "candidate_id": candidate_id,
                "candidate_name": f"{row.first_name} {row.last_name}",
                "phone": row.phone,
                "whisper_context": whisper_context,
                "status": "failed",
                "message": result.message,
                "error": result.error,
            }

    except Exception as e:
        logger.error(f"Failed to initiate telephony call: {e}")
        # Fall back to returning call record without telephony
        return {
            "call_id": call_id,
            "candidate_id": candidate_id,
            "candidate_name": f"{row.first_name} {row.last_name}",
            "phone": row.phone,
            "whisper_context": whisper_context,
            "status": "initiated",
            "message": "Call record created. Telephony integration error",
            "telephony_error": str(e),
        }


@router.post("/calls/{call_id}/connect")
async def connect_call_via_telephony(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retry/reconnect a call via the telephony provider.

    Used when an initial call attempt fails and user wants to retry.
    """
    org_id = current_user.organization_id

    # Get call details
    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.id, ch.candidate_id, ch.caller_user_id, ch.whisper_context,
                       ch.phone_to, rc.first_name, rc.last_name, rc.phone
                FROM recruiting_call_history ch
                JOIN mm_candidates rc ON rc.id = ch.candidate_id
                WHERE ch.id = :call_id AND rc.organization_id = :org_id
            """),
            {"call_id": call_id, "org_id": org_id}
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Call record not found")

    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            result = service.initiate_call(
                call_id=call_id,
                candidate_id=row.candidate_id,
                caller_user_id=row.caller_user_id,
                candidate_phone=row.phone or row.phone_to,
                candidate_name=f"{row.first_name} {row.last_name}",
                whisper_context=row.whisper_context or "Press 1 to connect.",
            )

        return {
            "call_id": call_id,
            "call_sid": result.call_sid,
            "status": result.status,
            "message": result.message,
            "success": result.success,
            "error": result.error,
        }

    except Exception as e:
        logger.error(f"Failed to reconnect call: {e}")
        return {
            "call_id": call_id,
            "status": "failed",
            "message": "Failed to connect",
            "success": False,
            "error": "Internal server error",
        }


# =============================================================================
# Telephony Webhook Endpoints
# =============================================================================

@router.post("/telnyx/recruiter-answered/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_recruiter_answered(call_id: str):
    """
    Telephony webhook: Recruiter answered the call.

    Plays whisper context and prompts for confirmation.
    """
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            twiml = service.generate_recruiter_twiml(call_id)

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in recruiter-answered webhook: {e}")
        from telephony.providers.telnyx.texml import TeXMLResponse
        response = TeXMLResponse()
        response.say("Sorry, there was an error.", voice="Polly.Matthew")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/telnyx/recruiter-response/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_recruiter_response(
    call_id: str,
    Digits: str = Form("")
):
    """
    Telephony webhook: Recruiter pressed a digit.

    1 = Connect to candidate
    Other = Cancel
    """
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            twiml = service.generate_recruiter_response_twiml(call_id, Digits)

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in recruiter-response webhook: {e}")
        from telephony.providers.telnyx.texml import TeXMLResponse
        response = TeXMLResponse()
        response.say("Sorry, there was an error.", voice="Polly.Matthew")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/telnyx/call-complete/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_call_complete(
    call_id: str,
    DialCallStatus: str = Form("completed")
):
    """
    Telephony webhook: Call to candidate completed.

    Records the outcome and generates final TwiML.
    """
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            twiml = service.generate_call_complete_twiml(call_id, DialCallStatus)

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in call-complete webhook: {e}")
        from telephony.providers.telnyx.texml import TeXMLResponse
        response = TeXMLResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/telnyx/status/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_status_callback(
    call_id: str,
    CallStatus: str = Form(""),
    CallDuration: Optional[int] = Form(None),
    CallSid: str = Form("")
):
    """
    Telephony webhook: Call status update.

    Tracks call progress (initiated, ringing, answered, completed, etc.)
    """
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            service.handle_status_callback(
                call_id=call_id,
                call_status=CallStatus,
                call_duration=CallDuration,
                call_sid=CallSid,
            )

        return {"received": True, "call_id": call_id, "status": CallStatus}

    except Exception as e:
        logger.error(f"Error in status callback: {e}")
        return {"received": True, "error": "Internal server error"}


@router.post("/telnyx/candidate-status/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_candidate_status(
    call_id: str,
    CallStatus: str = Form(""),
    CallDuration: Optional[int] = Form(None)
):
    """
    Telephony webhook: Candidate leg status update.

    Tracks when candidate answers, hangs up, etc.
    """
    logger.info(f"Candidate status for {call_id}: {CallStatus}")

    # Update call record with candidate-specific status
    with get_db_connection() as conn:
        if CallStatus in ["answered", "in-progress"]:
            conn.execute(
                text("UPDATE recruiting_call_history SET status = 'in_progress' WHERE id = :id"),
                {"id": call_id}
            )
        conn.commit()

    return {"received": True, "call_id": call_id, "status": CallStatus}


@router.post("/telnyx/recording/{call_id}", dependencies=[Depends(_verify_telnyx_webhook)])
async def telephony_recording_callback(
    call_id: str,
    RecordingUrl: str = Form(""),
    RecordingSid: str = Form(""),
    RecordingDuration: int = Form(0)
):
    """
    Telephony webhook: Recording completed.

    Stores the recording URL for later playback.
    """
    try:
        from services.recruiting_dialer_service import get_recruiting_dialer_service

        with get_db_connection() as conn:
            service = get_recruiting_dialer_service(conn)
            service.handle_recording_callback(
                call_id=call_id,
                recording_url=RecordingUrl,
                recording_sid=RecordingSid,
                recording_duration=RecordingDuration,
            )

        return {"received": True, "call_id": call_id, "recording_sid": RecordingSid}

    except Exception as e:
        logger.error(f"Error in recording callback: {e}")
        return {"received": True, "error": "Internal server error"}


# =============================================================================
# Call History Endpoints
# =============================================================================

@router.get("/candidates/{candidate_id}/call-history")
async def get_candidate_call_history(
    candidate_id: int,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get call history for a specific candidate."""
    org_id = current_user.organization_id

    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.id, ch.candidate_id, ch.caller_user_id,
                       u.full_name as caller_name, ch.direction,
                       ch.duration_seconds, ch.outcome, ch.notes,
                       ch.called_at, ch.status, ch.recording_url,
                       ch.twilio_call_sid as call_sid
                FROM recruiting_call_history ch
                JOIN mm_candidates rc ON rc.id = ch.candidate_id
                LEFT JOIN users u ON u.id = ch.caller_user_id
                WHERE ch.candidate_id = :candidate_id AND rc.organization_id = :org_id
                ORDER BY ch.called_at DESC
                LIMIT :limit
            """),
            {"candidate_id": candidate_id, "limit": limit, "org_id": org_id}
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
            "status": row.status,
            "recording_url": getattr(row, 'recording_url', None),
        }
        for row in rows
    ]

    return {
        "candidate_id": candidate_id,
        "total": len(history),
        "history": history
    }


@router.post("/calls/{call_id}/notes")
async def add_call_notes(
    call_id: str,
    request: CallNoteRequest,
    current_user: User = Depends(get_current_user)
):
    """Add notes and outcome to a call."""
    org_id = current_user.organization_id

    with get_db_connection() as conn:
        # Update call record (tenant-scoped via JOIN)
        conn.execute(
            text("""
                UPDATE recruiting_call_history ch
                SET notes = :notes,
                    outcome = :outcome,
                    status = 'completed',
                    completed_at = NOW()
                FROM mm_candidates rc
                WHERE ch.candidate_id = rc.id
                    AND ch.id = :call_id
                    AND rc.organization_id = :org_id
            """),
            {
                "call_id": call_id,
                "notes": request.note,
                "outcome": request.outcome,
                "org_id": org_id
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
                         route_to, status, assigned_to, organization_id, created_at)
                        VALUES (:candidate_id, 'Callback requested',
                                :notes, :due_date, 'high',
                                'dialer_queue', 'pending', :user_id, :org_id, NOW())
                    """),
                    {
                        "candidate_id": row.candidate_id,
                        "notes": f"Callback requested: {request.note}",
                        "due_date": request.callback_date,
                        "user_id": current_user.id,
                        "org_id": org_id
                    }
                )

        conn.commit()

    return {"message": "Call notes saved", "call_id": call_id}


@router.get("/calls/{call_id}/status")
async def get_call_status(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the current status of a call."""
    org_id = current_user.organization_id

    with get_db_connection() as conn:
        result = conn.execute(
            text("""
                SELECT ch.*, rc.first_name, rc.last_name
                FROM recruiting_call_history ch
                JOIN mm_candidates rc ON rc.id = ch.candidate_id
                WHERE ch.id = :call_id AND rc.organization_id = :org_id
            """),
            {"call_id": call_id, "org_id": org_id}
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
    current_user: User = Depends(get_current_user)
):
    """
    Get the dialer queue with candidate details for calling.

    Combines workflow tasks routed to dialer with candidate contact info.
    """
    params = {"org_id": current_user.organization_id}
    user_filter = ""
    if assigned_to:
        user_filter = "AND rt.assigned_to = :assigned_to"
        params["assigned_to"] = assigned_to

    with get_db_connection() as conn:
        queue_sql = """
                SELECT rt.id as task_id, rt.candidate_id, rt.title as task_title,
                       rt.description as task_description, rt.due_date, rt.priority,
                       rc.first_name, rc.last_name, rc.phone, rc.email,
                       rc.status as candidate_status, rc.current_company,
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
                    """ + user_filter + """
                ORDER BY
                    rt.due_date ASC,
                    CASE rt.priority
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        ELSE 3
                    END
            """
        result = conn.execute(
            text(queue_sql),
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
# Migration endpoints removed — use backend/migrations/ scripts instead.
# =============================================================================
