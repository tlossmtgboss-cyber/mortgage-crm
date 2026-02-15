"""
Twilio Status Callback Routes

Handles Twilio webhook callbacks for:
- Call status updates (queued, ringing, in-progress, completed, etc.)
- Recording status updates

All callbacks are:
- Form-encoded (application/x-www-form-urlencoded)
- Validated via X-Twilio-Signature
- Idempotent via processed_twilio_events table

Implements the status-to-disposition mapping per spec.
"""

import os
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/twilio", tags=["twilio-webhooks"])


# =============================================================================
# CONFIGURATION
# =============================================================================

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

# Status mapping: Twilio CallStatus -> call_attempts.status
STATUS_MAP = {
    "queued": "queued",
    "initiated": "dialing",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "completed": "completed",
    "busy": "completed",
    "failed": "failed",
    "no-answer": "completed",
    "canceled": "canceled",
}

# Terminal statuses that should set disposition
TERMINAL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}

# Dispositions that prevent further retries
TERMINAL_DISPOSITIONS = {"scheduled", "not_interested", "wrong_number", "dnc"}

# Status ordering: higher ordinal = later in call lifecycle.
# Callbacks may arrive out of order (e.g., 'completed' before 'ringing').
# Only update status if the new status has a higher ordinal than the current one.
STATUS_ORDER = {
    "queued": 1,
    "dialing": 2,
    "ringing": 3,
    "in_progress": 4,
    "completed": 5,
    "failed": 5,
    "canceled": 5,
}


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TwilioStatusCallback(BaseModel):
    """Model for Twilio status callback data."""
    call_sid: str
    call_status: str
    to: Optional[str] = None
    from_: Optional[str] = None
    direction: Optional[str] = None
    timestamp: Optional[str] = None
    call_duration: Optional[int] = None
    sip_response_code: Optional[str] = None
    api_version: Optional[str] = None


class TwilioRecordingCallback(BaseModel):
    """Model for Twilio recording callback data."""
    call_sid: str
    recording_sid: str
    recording_url: Optional[str] = None
    recording_duration: Optional[int] = None
    recording_status: Optional[str] = None


# =============================================================================
# SIGNATURE VALIDATION
# =============================================================================

def validate_twilio_signature(
    url: str,
    params: Dict[str, Any],
    signature: str,
    auth_token: str = None
) -> bool:
    """
    Validate X-Twilio-Signature header.

    Twilio signature is computed as:
    1. Sort POST parameters alphabetically by key
    2. Append key=value pairs to the full URL
    3. HMAC-SHA1 hash with auth token
    4. Base64 encode
    """
    if not auth_token:
        auth_token = TWILIO_AUTH_TOKEN

    if not auth_token:
        logger.error("TWILIO_AUTH_TOKEN not set — rejecting webhook")
        return False

    # Build signature data
    data = url
    for key in sorted(params.keys()):
        data += f"{key}{params[key]}"

    # Compute expected signature
    computed = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(computed, signature)


def get_full_url(request: Request) -> str:
    """Get the full URL including scheme, host, and path."""
    # Use X-Forwarded headers if behind a proxy
    scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host = request.headers.get("X-Forwarded-Host", request.url.netloc)
    return f"{scheme}://{host}{request.url.path}"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def check_idempotency(
    db: Session,
    call_sid: str,
    event_type: str,
    call_status: str = None,
    recording_sid: str = None,
    raw_payload: Dict = None
) -> bool:
    """
    Check and insert idempotency record.
    Returns True if this is a duplicate (already processed).
    """
    try:
        db.execute(text("""
            INSERT INTO processed_twilio_events
            (call_sid, event_type, call_status, recording_sid, raw_payload)
            VALUES (:call_sid, :event_type, :call_status, :recording_sid, :raw_payload)
        """), {
            "call_sid": call_sid,
            "event_type": event_type,
            "call_status": call_status,
            "recording_sid": recording_sid,
            "raw_payload": str(raw_payload) if raw_payload else None
        })
        db.commit()
        return False  # Not a duplicate, proceed
    except IntegrityError:
        db.rollback()
        logger.info(f"Duplicate event: {event_type} for call {call_sid} status={call_status}")
        return True  # Duplicate, skip processing


async def get_or_create_attempt(
    db: Session,
    call_sid: str,
    to_number: str = None,
    from_number: str = None,
    direction: str = "outbound-api"
) -> Optional[Dict]:
    """Get existing attempt or create if callback arrives before we persisted."""
    result = db.execute(text("""
        SELECT id, call_target_id, status, disposition
        FROM call_attempts
        WHERE provider_call_id = :call_sid
    """), {"call_sid": call_sid})
    row = result.fetchone()

    if row:
        return {
            "id": row[0],
            "call_target_id": row[1],
            "status": row[2],
            "disposition": row[3]
        }

    # Create new attempt if we have enough info
    if to_number and from_number:
        result = db.execute(text("""
            INSERT INTO call_attempts
            (provider_call_id, to_number, from_number, direction, created_at)
            VALUES (:call_sid, :to_number, :from_number, :direction, NOW())
            RETURNING id
        """), {
            "call_sid": call_sid,
            "to_number": to_number,
            "from_number": from_number,
            "direction": direction
        })
        new_id = result.fetchone()[0]
        db.commit()
        return {"id": new_id, "call_target_id": None, "status": None, "disposition": None}

    return None


async def update_attempt_status(
    db: Session,
    attempt_id: str,
    new_status: str,
    call_duration: int = None,
    disposition: str = None,
    sip_code: str = None
):
    """Update call attempt status and optionally disposition.

    Guards against out-of-order Twilio callbacks by only updating the status
    if the new status has a higher ordinal than the current one (STATUS_ORDER).
    For example, a late 'ringing' callback will not overwrite 'completed'.
    """
    # Check current status to prevent out-of-order updates
    result = db.execute(text("""
        SELECT status FROM call_attempts WHERE id = :id
    """), {"id": attempt_id})
    row = result.fetchone()
    if row and row[0]:
        current_order = STATUS_ORDER.get(row[0], 0)
        new_order = STATUS_ORDER.get(new_status, 0)
        if new_order < current_order:
            logger.info(
                f"Ignoring out-of-order status update for attempt {attempt_id}: "
                f"current={row[0]} (order={current_order}), received={new_status} (order={new_order})"
            )
            return

    update_fields = ["status = :status", "updated_at = NOW()"]
    params = {"id": attempt_id, "status": new_status}

    if call_duration is not None:
        update_fields.append("duration_seconds = :duration")
        params["duration"] = call_duration

    if disposition:
        update_fields.append("disposition = :disposition")
        params["disposition"] = disposition

    if sip_code:
        update_fields.append("sip_response_code = :sip_code")
        params["sip_code"] = sip_code

    # Set timing fields based on status
    if new_status == "in_progress":
        update_fields.append("started_at = COALESCE(started_at, NOW())")
        update_fields.append("answered_at = COALESCE(answered_at, NOW())")
    elif new_status in ("completed", "failed", "canceled"):
        update_fields.append("ended_at = COALESCE(ended_at, NOW())")

    db.execute(text(f"""
        UPDATE call_attempts
        SET {', '.join(update_fields)}
        WHERE id = :id
    """), params)
    db.commit()


async def update_target_from_attempt(
    db: Session,
    call_target_id: str,
    disposition: str,
    twilio_status: str
):
    """Update call_target based on attempt outcome."""
    if not call_target_id:
        return

    # Get current target info
    result = db.execute(text("""
        SELECT attempt_count, max_attempts FROM call_targets WHERE id = :id
    """), {"id": call_target_id})
    target = result.fetchone()
    if not target:
        return

    attempt_count, max_attempts = target

    update_fields = ["last_attempt_at = NOW()", "updated_at = NOW()"]
    params = {"id": call_target_id}

    # Set disposition on terminal outcomes
    if disposition in TERMINAL_DISPOSITIONS:
        update_fields.append("disposition = :disposition")
        update_fields.append("callable = FALSE")
        update_fields.append("not_callable_reason = 'terminal_disposition'")
        params["disposition"] = disposition
    elif twilio_status == "no-answer":
        update_fields.append("disposition = :disposition")
        params["disposition"] = "no_answer"
    elif twilio_status == "busy":
        update_fields.append("disposition = :disposition")
        params["disposition"] = "busy"
    elif twilio_status == "failed":
        update_fields.append("disposition = :disposition")
        params["disposition"] = "failed"

    # Check max attempts
    if attempt_count >= max_attempts:
        update_fields.append("callable = FALSE")
        update_fields.append("not_callable_reason = 'max_attempts_reached'")

    db.execute(text(f"""
        UPDATE call_targets
        SET {', '.join(update_fields)}
        WHERE id = :id
    """), params)
    db.commit()


async def emit_event(
    db: Session,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: Dict
):
    """Emit an event to the outbox for async processing."""
    db.execute(text("""
        INSERT INTO event_outbox
        (event_type, aggregate_type, aggregate_id, payload, status, created_at)
        VALUES (:event_type, :aggregate_type, :aggregate_id, :payload::jsonb, 'pending', NOW())
    """), {
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "payload": str(payload).replace("'", '"')
    })
    db.commit()


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/status-callback")
async def handle_status_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Twilio call status callback handler (form-encoded).

    Receives at-least-once delivery from Twilio.
    - Validates X-Twilio-Signature
    - De-duplicates via processed_twilio_events
    - Updates call_attempts status and disposition
    - Updates call_targets for retry logic
    - Emits events for terminal states
    """
    try:
        # Parse form data
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid", "")
        call_status = params.get("CallStatus", "").lower()

        if not call_sid:
            logger.warning("Status callback missing CallSid")
            return Response(status_code=200)

        logger.info(f"Status callback: CallSid={call_sid}, Status={call_status}")

        # Validate Twilio signature
        signature = request.headers.get("X-Twilio-Signature", "")
        full_url = get_full_url(request)

        if not validate_twilio_signature(full_url, params, signature):
            logger.warning(f"Invalid Twilio signature for call {call_sid}")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Check idempotency
        is_duplicate = await check_idempotency(
            db, call_sid, "status", call_status, raw_payload=params
        )
        if is_duplicate:
            return Response(status_code=200)

        # Get or create attempt record
        attempt = await get_or_create_attempt(
            db,
            call_sid,
            to_number=params.get("To"),
            from_number=params.get("From"),
            direction=params.get("Direction", "outbound-api")
        )

        if not attempt:
            logger.warning(f"Could not find or create attempt for call {call_sid}")
            return Response(status_code=200)

        # Map Twilio status to internal status
        new_status = STATUS_MAP.get(call_status, call_status)

        # Determine disposition for terminal statuses
        disposition = None
        if call_status in TERMINAL_STATUSES:
            # Check for agent outcome first (set during call)
            result = db.execute(text("""
                SELECT agent_outcome FROM call_attempts WHERE id = :id
            """), {"id": attempt["id"]})
            row = result.fetchone()
            agent_outcome = row[0] if row else None

            if agent_outcome:
                disposition = agent_outcome
            elif call_status == "no-answer":
                disposition = "no_answer"
            elif call_status in ("busy", "failed"):
                disposition = "failed"
            # 'completed' without agent_outcome leaves disposition null

        # Update attempt
        await update_attempt_status(
            db,
            attempt["id"],
            new_status,
            call_duration=int(params.get("CallDuration", 0)) if params.get("CallDuration") else None,
            disposition=disposition,
            sip_code=params.get("SipResponseCode")
        )

        # Update target if terminal
        if call_status in TERMINAL_STATUSES and attempt.get("call_target_id"):
            await update_target_from_attempt(
                db,
                attempt["call_target_id"],
                disposition,
                call_status
            )

        # Emit event for terminal statuses
        if call_status in TERMINAL_STATUSES:
            await emit_event(
                db,
                event_type=f"call.{call_status.replace('-', '_')}",
                aggregate_type="call_attempt",
                aggregate_id=str(attempt["id"]),
                payload={
                    "call_sid": call_sid,
                    "status": new_status,
                    "disposition": disposition,
                    "duration": params.get("CallDuration"),
                    "to": params.get("To"),
                    "from": params.get("From")
                }
            )

        return Response(status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing status callback: {e}")
        # Return 200 anyway to prevent Twilio retries on our errors
        return Response(status_code=200)


@router.post("/recording-callback")
async def handle_recording_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Twilio recording status callback handler (form-encoded).

    Persists recording URL and duration to call_attempts.
    De-duplicates via processed_twilio_events using recording_sid.
    """
    try:
        # Parse form data
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid", "")
        recording_sid = params.get("RecordingSid", "")
        recording_url = params.get("RecordingUrl", "")
        recording_duration = params.get("RecordingDuration")

        if not call_sid or not recording_sid:
            logger.warning("Recording callback missing CallSid or RecordingSid")
            return Response(status_code=200)

        logger.info(f"Recording callback: CallSid={call_sid}, RecordingSid={recording_sid}")

        # Validate Twilio signature
        signature = request.headers.get("X-Twilio-Signature", "")
        full_url = get_full_url(request)

        if not validate_twilio_signature(full_url, params, signature):
            logger.warning(f"Invalid Twilio signature for recording {recording_sid}")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Check idempotency
        is_duplicate = await check_idempotency(
            db, call_sid, "recording", recording_sid=recording_sid, raw_payload=params
        )
        if is_duplicate:
            return Response(status_code=200)

        # Update call attempt with recording info
        db.execute(text("""
            UPDATE call_attempts
            SET
                recording_url = COALESCE(recording_url, :recording_url),
                recording_sid = COALESCE(recording_sid, :recording_sid),
                recording_duration = COALESCE(recording_duration, :recording_duration),
                updated_at = NOW()
            WHERE provider_call_id = :call_sid
        """), {
            "call_sid": call_sid,
            "recording_url": recording_url,
            "recording_sid": recording_sid,
            "recording_duration": int(recording_duration) if recording_duration else None
        })
        db.commit()

        logger.info(f"Updated recording info for call {call_sid}")
        return Response(status_code=200)

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error processing recording callback: {e}")
        return Response(status_code=200)


# =============================================================================
# ADMIN/DEBUG ENDPOINTS
# =============================================================================

@router.get("/callback-logs")
async def get_callback_logs(
    db: Session = Depends(get_db),
    call_sid: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get processed Twilio event logs for debugging."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if call_sid:
            filters.append("call_sid = :call_sid")
            params["call_sid"] = call_sid

        if event_type:
            filters.append("event_type = :event_type")
            params["event_type"] = event_type

        where_clause = " AND ".join(filters)

        result = db.execute(text(f"""
            SELECT
                id, call_sid, event_type, call_status, recording_sid,
                received_at, raw_payload
            FROM processed_twilio_events
            WHERE {where_clause}
            ORDER BY received_at DESC
            LIMIT :limit OFFSET :offset
        """), params)

        entries = []
        for row in result.fetchall():
            entries.append({
                "id": str(row[0]),
                "call_sid": row[1],
                "event_type": row[2],
                "call_status": row[3],
                "recording_sid": row[4],
                "received_at": row[5].isoformat() if row[5] else None,
                "raw_payload": row[6]
            })

        return {
            "entries": entries,
            "count": len(entries),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error getting callback logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/call-attempts/{call_sid}")
async def get_call_attempt(
    call_sid: str,
    db: Session = Depends(get_db)
):
    """Get call attempt details by provider call ID."""
    try:
        result = db.execute(text("""
            SELECT
                id, call_target_id, provider_call_id, from_number, to_number,
                direction, status, disposition, started_at, answered_at, ended_at,
                duration_seconds, recording_url, sip_response_code, agent_outcome,
                agent_notes, scorecard, created_at, updated_at
            FROM call_attempts
            WHERE provider_call_id = :call_sid
        """), {"call_sid": call_sid})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call attempt not found")

        return {
            "id": str(row[0]),
            "call_target_id": str(row[1]) if row[1] else None,
            "provider_call_id": row[2],
            "from_number": row[3],
            "to_number": row[4],
            "direction": row[5],
            "status": row[6],
            "disposition": row[7],
            "started_at": row[8].isoformat() if row[8] else None,
            "answered_at": row[9].isoformat() if row[9] else None,
            "ended_at": row[10].isoformat() if row[10] else None,
            "duration_seconds": row[11],
            "recording_url": row[12],
            "sip_response_code": row[13],
            "agent_outcome": row[14],
            "agent_notes": row[15],
            "scorecard": row[16],
            "created_at": row[17].isoformat() if row[17] else None,
            "updated_at": row[18].isoformat() if row[18] else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call attempt: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/call-attempts/{attempt_id}/outcome")
async def set_agent_outcome(
    attempt_id: str,
    outcome: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Set agent outcome for a call attempt.
    Used during/after call to record agent's disposition.

    Valid outcomes:
    - scheduled: Appointment booked
    - not_interested: Prospect declined
    - voicemail_left: Left voicemail message
    - wrong_number: Number doesn't belong to contact
    - dnc: Do not call request
    - callback_requested: Prospect asked to call back later
    """
    try:
        valid_outcomes = {
            "scheduled", "not_interested", "voicemail_left",
            "wrong_number", "dnc", "callback_requested"
        }

        if outcome not in valid_outcomes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid outcome. Must be one of: {', '.join(valid_outcomes)}"
            )

        result = db.execute(text("""
            UPDATE call_attempts
            SET agent_outcome = :outcome, agent_notes = :notes, updated_at = NOW()
            WHERE id = :id
            RETURNING id, call_target_id
        """), {"id": attempt_id, "outcome": outcome, "notes": notes})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call attempt not found")

        # Update target if terminal disposition
        if row[1] and outcome in TERMINAL_DISPOSITIONS:
            await update_target_from_attempt(db, str(row[1]), outcome, "completed")

        db.commit()

        return {
            "success": True,
            "attempt_id": attempt_id,
            "outcome": outcome,
            "message": f"Agent outcome set to {outcome}"
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error setting agent outcome: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
