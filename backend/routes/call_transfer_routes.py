"""
Call Transfer Routes
Implements cold and warm transfer functionality using Twilio
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
from enum import Enum
import logging
import json
import os
import uuid

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transfers", tags=["call-transfers"])


def safe_isoformat(dt_value) -> Optional[str]:
    """Safely convert datetime to ISO format string, handling both datetime objects and strings"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        return dt_value  # Already a string (SQLite returns strings)
    if hasattr(dt_value, 'isoformat'):
        return dt_value.isoformat()
    return str(dt_value)


def get_current_user_flexible():
    """Lazy import auth dependency"""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


def get_twilio_client():
    """Get Twilio client"""
    from twilio.rest import Client
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None
    return Client(account_sid, auth_token)


# ============================================================================
# ENUMS AND MODELS
# ============================================================================

class TransferType(str, Enum):
    COLD = "cold"
    WARM = "warm"
    BLIND = "blind"  # Alias for cold


class TransferStatus(str, Enum):
    INITIATED = "initiated"
    CONSULTING = "consulting"  # Warm transfer - talking to recipient
    PENDING_ACCEPT = "pending_accept"  # Warm transfer - recipient deciding
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class InitiateTransferRequest(BaseModel):
    """Request to initiate a call transfer"""
    call_sid: str  # The active call to transfer
    transfer_type: TransferType = TransferType.COLD
    to_user_id: Optional[int] = None  # Transfer to internal user
    to_phone: Optional[str] = None  # Transfer to external number
    whisper_message: Optional[str] = None  # Message to play to recipient (warm)
    announce_caller: bool = True  # Announce caller before connecting
    transfer_reason: Optional[str] = None  # Why the transfer is happening
    hold_music_id: Optional[int] = None  # Custom hold music while transferring


class CompleteWarmTransferRequest(BaseModel):
    """Request to complete a warm transfer"""
    transfer_id: int
    action: str  # 'complete' or 'cancel'


class TransferResponse(BaseModel):
    """Transfer response"""
    id: int
    transfer_type: str
    status: str
    original_call_sid: str
    transfer_call_sid: Optional[str]
    from_user_id: Optional[int]
    to_user_id: Optional[int]
    to_phone: Optional[str]
    initiated_at: Optional[str]
    completed_at: Optional[str]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_phone(db: Session, user_id: int) -> Optional[str]:
    """Get user's phone number from database"""
    result = db.execute(text("""
        SELECT phone, work_phone, mobile_phone
        FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    if result:
        return result.mobile_phone or result.work_phone or result.phone
    return None


def get_user_name(db: Session, user_id: int) -> Optional[str]:
    """Get user's name from database"""
    result = db.execute(text("""
        SELECT name FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()
    return result.name if result else None


def format_phone(phone: str) -> str:
    """Format phone number to E.164"""
    import re
    phone = re.sub(r'[^\d+]', '', phone)
    if len(phone) == 10:
        return f"+1{phone}"
    elif not phone.startswith("+"):
        return f"+{phone}"
    return phone


def get_from_number() -> str:
    """Get Twilio from number"""
    return os.getenv("TWILIO_PHONE_NUMBER", "")


def _notify_agent_transfer_event(
    db: Session,
    transfer_id: int,
    event_type: str,
    details: Optional[str] = None
):
    """
    Notify the initiating agent about a transfer event (rejection, failure, etc.)

    Sends both:
    1. A real-time WebSocket notification for immediate alert
    2. A persistent notification record in the database

    Args:
        db: Database session
        transfer_id: The call_transfers record ID
        event_type: One of 'rejected', 'failed', 'consultation_failed'
        details: Optional extra detail (e.g. failure reason)
    """
    try:
        # Look up the transfer to get the initiating agent
        transfer = db.execute(text("""
            SELECT ct.from_user_id, ct.to_user_id, ct.to_phone,
                   ct.transfer_type, ct.original_call_sid, ct.transfer_reason,
                   u_to.name as to_name
            FROM call_transfers ct
            LEFT JOIN users u_to ON u_to.id = ct.to_user_id
            WHERE ct.id = :id
        """), {"id": transfer_id}).fetchone()

        if not transfer or not transfer.from_user_id:
            logger.debug(f"No initiating agent to notify for transfer {transfer_id}")
            return

        from_user_id = transfer.from_user_id
        to_name = transfer.to_name or transfer.to_phone or "Unknown"

        # Build notification message
        messages = {
            "rejected": f"Transfer to {to_name} was declined.",
            "failed": f"Transfer to {to_name} failed: {details or 'no answer'}.",
            "consultation_failed": f"Consultation with {to_name} failed: {details or 'unavailable'}. Caller is still on hold.",
        }
        message = messages.get(event_type, f"Transfer update: {event_type}")

        # 1. Send real-time WebSocket notification
        try:
            from services.workflow_websocket_events import WorkflowWebSocketNotifier
            notifier = WorkflowWebSocketNotifier()
            notifier.notify_user_sync(from_user_id, {
                "type": "transfer_update",
                "event": event_type,
                "transfer_id": transfer_id,
                "transfer_type": transfer.transfer_type,
                "to_name": to_name,
                "message": message,
                "original_call_sid": transfer.original_call_sid,
                "requires_action": event_type in ("rejected", "consultation_failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"WebSocket notification sent to agent {from_user_id}: {event_type}")
        except ImportError:
            logger.debug("WebSocket notifier not available")
        except Exception as e:
            logger.debug(f"WebSocket notification failed (non-critical): {e}")

        # 2. Store persistent notification in database
        try:
            db.execute(text("""
                INSERT INTO notifications (
                    user_id, type, title, message, data, is_read, created_at
                ) VALUES (
                    :user_id, :type, :title, :message, :data, FALSE, CURRENT_TIMESTAMP
                )
            """), {
                "user_id": from_user_id,
                "type": "transfer_update",
                "title": f"Transfer {event_type.replace('_', ' ').title()}",
                "message": message,
                "data": json.dumps({
                    "transfer_id": transfer_id,
                    "event": event_type,
                    "to_name": to_name,
                    "original_call_sid": transfer.original_call_sid,
                }),
            })
            db.commit()
        except Exception as e:
            # Notifications table may not exist yet - non-critical
            logger.debug(f"Could not store persistent notification: {e}")
            db.rollback()

        logger.info(f"Agent {from_user_id} notified: transfer {transfer_id} {event_type}")

    except Exception as e:
        logger.error(f"Failed to notify agent for transfer {transfer_id}: {e}")


def get_hold_music_url(db: Session, music_id: Optional[int] = None) -> str:
    """Get hold music URL"""
    if music_id:
        result = db.execute(text("""
            SELECT audio_url FROM hold_music
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id}).fetchone()
        if result and result.audio_url:
            return result.audio_url

    # Default
    result = db.execute(text("""
        SELECT audio_url FROM hold_music
        WHERE is_default = TRUE AND is_active = TRUE
        LIMIT 1
    """)).fetchone()

    if result and result.audio_url:
        return result.audio_url

    # Twilio default
    return "http://com.twilio.music.classical.s3.amazonaws.com/BussyStrings.mp3"


# ============================================================================
# COLD TRANSFER ENDPOINTS
# ============================================================================

@router.post("/cold")
async def initiate_cold_transfer(
    request: InitiateTransferRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Initiate a cold (blind) transfer.

    Cold transfer immediately redirects the caller to the new destination
    without any introduction or consultation with the recipient.

    The original agent is disconnected as soon as the transfer begins.
    """
    try:
        client = get_twilio_client()
        if not client:
            raise HTTPException(status_code=500, detail="Twilio not configured")

        # Determine destination
        to_phone = None
        to_user_id = request.to_user_id

        if request.to_phone:
            to_phone = format_phone(request.to_phone)
        elif request.to_user_id:
            to_phone = get_user_phone(db, request.to_user_id)
            if not to_phone:
                raise HTTPException(status_code=400, detail="User has no phone number")
            to_phone = format_phone(to_phone)
        else:
            raise HTTPException(status_code=400, detail="Must provide to_user_id or to_phone")

        logger.info(f"Initiating cold transfer: {request.call_sid} -> {to_phone}")

        # Create transfer record
        transfer_uuid = str(uuid.uuid4())[:8].upper()
        result = db.execute(text("""
            INSERT INTO call_transfers
            (original_call_sid, transfer_type, initiator_user_id,
             from_user_id, to_user_id, to_phone, status,
             announce_to_recipient, transfer_reason, initiated_at)
            VALUES
            (:call_sid, :transfer_type, :initiator_id,
             :from_user_id, :to_user_id, :to_phone, :status,
             :announce, :reason, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "call_sid": request.call_sid,
            "transfer_type": "cold",
            "initiator_id": current_user.id if current_user else None,
            "from_user_id": current_user.id if current_user else None,
            "to_user_id": to_user_id,
            "to_phone": to_phone,
            "status": "initiated",
            "announce": request.announce_caller,
            "reason": request.transfer_reason
        })

        try:
            transfer_id = result.fetchone()[0]
        except Exception:
            transfer_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        db.commit()

        # Build TwiML URL for the cold transfer
        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        transfer_url = f"{base_url}/api/v1/transfers/twiml/cold-connect?transfer_id={transfer_id}&to={to_phone}"

        # Update the call with new TwiML
        try:
            call = client.calls(request.call_sid).update(url=transfer_url, method="POST")

            # Update transfer with call info
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = :transfer_id
            """), {"transfer_id": transfer_id})
            db.commit()

            logger.info(f"Cold transfer initiated successfully: {transfer_id}")

            return {
                "success": True,
                "message": "Cold transfer initiated",
                "transfer_id": transfer_id,
                "to_phone": to_phone,
                "status": "completed"
            }

        except Exception as twilio_error:
            logger.error(f"Twilio error during cold transfer: {twilio_error}")

            # Update transfer as failed
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'failed', failure_reason = :error
                WHERE id = :transfer_id
            """), {"transfer_id": transfer_id, "error": str(twilio_error)})
            db.commit()

            raise HTTPException(status_code=500, detail=f"Transfer failed: {twilio_error}")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error initiating cold transfer: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/twiml/cold-connect")
async def cold_transfer_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML endpoint for cold transfer connection.
    Redirects the caller to dial the new destination.
    """
    from twilio.twiml.voice_response import VoiceResponse

    try:
        query_params = request.query_params
        transfer_id = query_params.get("transfer_id")
        to_phone = query_params.get("to")

        form_data = await request.form()
        caller = form_data.get("From", "Unknown")

        logger.info(f"Cold transfer TwiML: transfer_id={transfer_id}, to={to_phone}")

        # Get transfer details for any custom settings
        transfer = None
        announce = True
        whisper = None

        if transfer_id:
            result = db.execute(text("""
                SELECT announce_to_recipient, whisper_message, transfer_reason,
                       to_user_id
                FROM call_transfers WHERE id = :id
            """), {"id": transfer_id}).fetchone()

            if result:
                transfer = result
                announce = result.announce_to_recipient
                whisper = result.whisper_message

        response = VoiceResponse()

        # Brief message to caller
        response.say("Please hold while I transfer your call.", voice="Polly.Joanna")

        # Create dial with the destination
        dial = response.dial(
            caller_id=get_from_number(),
            timeout=30,
            action=f"/api/v1/transfers/twiml/transfer-status?transfer_id={transfer_id}"
        )

        # Add number with optional whisper for recipient
        if whisper:
            dial.number(
                to_phone,
                url=f"/api/v1/transfers/twiml/whisper?message={whisper}"
            )
        else:
            dial.number(to_phone)

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error generating cold transfer TwiML: {e}")
        response = VoiceResponse()
        response.say("We're sorry, the transfer could not be completed. Please try again later.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


# ============================================================================
# WARM TRANSFER ENDPOINTS
# ============================================================================

@router.post("/warm")
async def initiate_warm_transfer(
    request: InitiateTransferRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Initiate a warm (attended) transfer.

    Warm transfer puts the caller on hold, calls the recipient,
    allows the agent to introduce the caller, and then connects them.

    The agent stays on the line until they complete or cancel the transfer.
    """
    try:
        client = get_twilio_client()
        if not client:
            raise HTTPException(status_code=500, detail="Twilio not configured")

        # Determine destination
        to_phone = None
        to_user_id = request.to_user_id
        to_user_name = None

        if request.to_phone:
            to_phone = format_phone(request.to_phone)
        elif request.to_user_id:
            to_phone = get_user_phone(db, request.to_user_id)
            to_user_name = get_user_name(db, request.to_user_id)
            if not to_phone:
                raise HTTPException(status_code=400, detail="User has no phone number")
            to_phone = format_phone(to_phone)
        else:
            raise HTTPException(status_code=400, detail="Must provide to_user_id or to_phone")

        logger.info(f"Initiating warm transfer: {request.call_sid} -> {to_phone}")

        # Create a conference room for the warm transfer
        conference_name = f"warm-transfer-{uuid.uuid4().hex[:8]}"

        # Create transfer record
        result = db.execute(text("""
            INSERT INTO call_transfers
            (original_call_sid, transfer_type, initiator_user_id,
             from_user_id, to_user_id, to_phone, status,
             announce_to_recipient, whisper_message, transfer_reason,
             initiated_at, extra_data)
            VALUES
            (:call_sid, :transfer_type, :initiator_id,
             :from_user_id, :to_user_id, :to_phone, :status,
             :announce, :whisper, :reason, CURRENT_TIMESTAMP, :extra)
            RETURNING id
        """), {
            "call_sid": request.call_sid,
            "transfer_type": "warm",
            "initiator_id": current_user.id if current_user else None,
            "from_user_id": current_user.id if current_user else None,
            "to_user_id": to_user_id,
            "to_phone": to_phone,
            "status": "initiated",
            "announce": request.announce_caller,
            "whisper": request.whisper_message,
            "reason": request.transfer_reason,
            "extra": json.dumps({
                "conference_name": conference_name,
                "hold_music_id": request.hold_music_id,
                "to_user_name": to_user_name
            })
        })

        try:
            transfer_id = result.fetchone()[0]
        except Exception:
            transfer_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        db.commit()

        # Get hold music URL
        hold_music_url = get_hold_music_url(db, request.hold_music_id)

        # Build URLs
        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        # Step 1: Put caller on hold in conference
        hold_url = f"{base_url}/api/v1/transfers/twiml/warm-hold?transfer_id={transfer_id}&conf={conference_name}"

        try:
            # Update original call to hold in conference
            client.calls(request.call_sid).update(url=hold_url, method="POST")

            # Step 2: Call the recipient for consultation
            consult_url = f"{base_url}/api/v1/transfers/twiml/warm-consult?transfer_id={transfer_id}&conf={conference_name}"

            consult_call = client.calls.create(
                to=to_phone,
                from_=get_from_number(),
                url=consult_url,
                method="POST",
                status_callback=f"{base_url}/api/v1/transfers/webhook/consult-status?transfer_id={transfer_id}",
                status_callback_event=["completed", "no-answer", "busy", "failed"]
            )

            # Update transfer with consultation call SID
            db.execute(text("""
                UPDATE call_transfers
                SET consultation_call_sid = :consult_sid,
                    consultation_started_at = CURRENT_TIMESTAMP,
                    status = 'consulting'
                WHERE id = :transfer_id
            """), {"consult_sid": consult_call.sid, "transfer_id": transfer_id})
            db.commit()

            logger.info(f"Warm transfer consultation started: {consult_call.sid}")

            return {
                "success": True,
                "message": "Warm transfer initiated - caller on hold, calling recipient",
                "transfer_id": transfer_id,
                "consultation_call_sid": consult_call.sid,
                "conference_name": conference_name,
                "to_phone": to_phone,
                "to_user_name": to_user_name,
                "status": "consulting"
            }

        except Exception as twilio_error:
            logger.error(f"Twilio error during warm transfer: {twilio_error}")

            db.execute(text("""
                UPDATE call_transfers
                SET status = 'failed', failure_reason = :error
                WHERE id = :transfer_id
            """), {"transfer_id": transfer_id, "error": str(twilio_error)})
            db.commit()

            raise HTTPException(status_code=500, detail=f"Transfer failed: {twilio_error}")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error initiating warm transfer: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/warm/complete")
async def complete_warm_transfer(
    request: CompleteWarmTransferRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Complete or cancel a warm transfer.

    - complete: Connects caller and recipient, drops agent
    - cancel: Brings caller back, hangs up on recipient
    """
    try:
        client = get_twilio_client()
        if not client:
            raise HTTPException(status_code=500, detail="Twilio not configured")

        # Get transfer details
        transfer = db.execute(text("""
            SELECT id, original_call_sid, consultation_call_sid, extra_data, status
            FROM call_transfers WHERE id = :id
        """), {"id": request.transfer_id}).fetchone()

        if not transfer:
            raise HTTPException(status_code=404, detail="Transfer not found")

        if transfer.status not in ['consulting', 'pending_accept']:
            raise HTTPException(status_code=400, detail=f"Cannot complete transfer in status: {transfer.status}")

        extra_data = json.loads(transfer.extra_data) if transfer.extra_data else {}
        conference_name = extra_data.get("conference_name")

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        if request.action == "complete":
            # Complete the transfer - connect caller and recipient
            logger.info(f"Completing warm transfer {request.transfer_id}")

            # Update recipient call to join the conference as participant
            if transfer.consultation_call_sid:
                connect_url = f"{base_url}/api/v1/transfers/twiml/warm-connect?transfer_id={request.transfer_id}&conf={conference_name}"
                client.calls(transfer.consultation_call_sid).update(url=connect_url, method="POST")

            # Update transfer status
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    consultation_ended_at = CURRENT_TIMESTAMP
                WHERE id = :transfer_id
            """), {"transfer_id": request.transfer_id})
            db.commit()

            return {
                "success": True,
                "message": "Transfer completed - caller and recipient connected",
                "transfer_id": request.transfer_id,
                "status": "completed"
            }

        elif request.action == "cancel":
            # Cancel the transfer - hang up on recipient, return to caller
            logger.info(f"Cancelling warm transfer {request.transfer_id}")

            # Hang up the consultation call
            if transfer.consultation_call_sid:
                try:
                    client.calls(transfer.consultation_call_sid).update(status="completed")
                except Exception:
                    pass  # Call may already be ended

            # Update original call to return from hold
            return_url = f"{base_url}/api/v1/transfers/twiml/warm-cancel?transfer_id={request.transfer_id}"
            client.calls(transfer.original_call_sid).update(url=return_url, method="POST")

            # Update transfer status
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP,
                    consultation_ended_at = CURRENT_TIMESTAMP
                WHERE id = :transfer_id
            """), {"transfer_id": request.transfer_id})
            db.commit()

            return {
                "success": True,
                "message": "Transfer cancelled - returning to caller",
                "transfer_id": request.transfer_id,
                "status": "cancelled"
            }

        else:
            raise HTTPException(status_code=400, detail="Action must be 'complete' or 'cancel'")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error completing warm transfer: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# WARM TRANSFER TWIML ENDPOINTS
# ============================================================================

@router.post("/twiml/warm-hold")
async def warm_transfer_hold_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML for putting caller on hold during warm transfer.
    Plays hold music while agent consults with recipient.
    """
    from twilio.twiml.voice_response import VoiceResponse, Dial

    try:
        query_params = request.query_params
        transfer_id = query_params.get("transfer_id")
        conference_name = query_params.get("conf")

        logger.info(f"Warm transfer hold TwiML: transfer_id={transfer_id}")

        # Get hold music
        hold_music_id = None
        if transfer_id:
            result = db.execute(text("""
                SELECT extra_data FROM call_transfers WHERE id = :id
            """), {"id": transfer_id}).fetchone()
            if result and result.extra_data:
                extra = json.loads(result.extra_data)
                hold_music_id = extra.get("hold_music_id")

        hold_music_url = get_hold_music_url(db, hold_music_id)

        response = VoiceResponse()
        response.say("Please hold while I connect you with someone who can help.", voice="Polly.Joanna")

        # Put caller in conference with hold music
        dial = response.dial()
        dial.conference(
            conference_name,
            wait_url=hold_music_url,
            start_conference_on_enter=False,  # Wait for recipient
            end_conference_on_exit=True,
            beep=False
        )

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in warm hold TwiML: {e}")
        response = VoiceResponse()
        response.say("Please wait while we connect your call.")
        response.pause(length=30)
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/warm-consult")
async def warm_transfer_consult_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML for the consultation call to the recipient.
    Announces the caller info and gives options to accept or reject.
    """
    from twilio.twiml.voice_response import VoiceResponse, Gather

    try:
        query_params = request.query_params
        transfer_id = query_params.get("transfer_id")
        conference_name = query_params.get("conf")

        logger.info(f"Warm transfer consult TwiML: transfer_id={transfer_id}")

        # Get transfer info for announcement
        caller_info = "a caller"
        reason = ""

        if transfer_id:
            result = db.execute(text("""
                SELECT ct.caller_name, ct.caller_phone, ct.transfer_reason,
                       ct.whisper_message, ct.extra_data,
                       u.full_name as from_user_name
                FROM call_transfers ct
                LEFT JOIN users u ON u.id = ct.from_user_id
                WHERE ct.id = :id
            """), {"id": transfer_id}).fetchone()

            if result:
                if result.caller_name:
                    caller_info = result.caller_name
                elif result.caller_phone:
                    caller_info = f"a caller from {result.caller_phone}"

                if result.transfer_reason:
                    reason = f" regarding {result.transfer_reason}"

                if result.whisper_message:
                    caller_info = result.whisper_message

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        response = VoiceResponse()

        # Announce the transfer
        response.say(
            f"Incoming transfer from {caller_info}{reason}. "
            f"Press 1 to accept the call, or press 2 to decline.",
            voice="Polly.Joanna"
        )

        # Gather response
        gather = response.gather(
            num_digits=1,
            action=f"{base_url}/api/v1/transfers/twiml/warm-decision?transfer_id={transfer_id}&conf={conference_name}",
            method="POST",
            timeout=15
        )
        gather.say("Press 1 to accept or 2 to decline.", voice="Polly.Joanna")

        # Default to accept if no response
        response.redirect(
            f"{base_url}/api/v1/transfers/twiml/warm-decision?transfer_id={transfer_id}&conf={conference_name}&Digits=1"
        )

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in warm consult TwiML: {e}")
        response = VoiceResponse()
        response.say("Error processing transfer. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/warm-decision")
async def warm_transfer_decision_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle recipient's decision to accept or reject the transfer.
    """
    from twilio.twiml.voice_response import VoiceResponse

    try:
        query_params = request.query_params
        form_data = await request.form()

        transfer_id = query_params.get("transfer_id")
        conference_name = query_params.get("conf")
        digits = form_data.get("Digits") or query_params.get("Digits", "1")

        logger.info(f"Warm transfer decision: transfer_id={transfer_id}, digits={digits}")

        response = VoiceResponse()

        if digits == "1":
            # Accept - connect to the conference
            response.say("Connecting you now.", voice="Polly.Joanna")

            dial = response.dial()
            dial.conference(
                conference_name,
                start_conference_on_enter=True,  # Start when recipient joins
                end_conference_on_exit=False,
                beep=True
            )

            # Update transfer status
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": transfer_id})
            db.commit()

        else:
            # Reject - decline the transfer
            response.say("Transfer declined. Goodbye.", voice="Polly.Joanna")
            response.hangup()

            # Update transfer as rejected and notify original caller
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'rejected', completed_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": transfer_id})
            db.commit()

            # Notify the initiating agent that the transfer was declined
            _notify_agent_transfer_event(db, int(transfer_id), "rejected")

        return Response(content=str(response), media_type="application/xml")

    except SQLAlchemyError as e:
        logger.error(f"Error in warm decision TwiML: {e}")
        response = VoiceResponse()
        response.say("Error processing. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/warm-connect")
async def warm_transfer_connect_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML to connect recipient to the conference (after agent completes transfer).
    """
    from twilio.twiml.voice_response import VoiceResponse

    try:
        query_params = request.query_params
        transfer_id = query_params.get("transfer_id")
        conference_name = query_params.get("conf")

        logger.info(f"Warm transfer connect: transfer_id={transfer_id}")

        response = VoiceResponse()
        response.say("Connecting you now.", voice="Polly.Joanna")

        dial = response.dial()
        dial.conference(
            conference_name,
            start_conference_on_enter=True,
            end_conference_on_exit=True,
            beep=False
        )

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in warm connect TwiML: {e}")
        response = VoiceResponse()
        response.say("Error connecting. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/warm-cancel")
async def warm_transfer_cancel_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML when warm transfer is cancelled - return to caller.
    """
    from twilio.twiml.voice_response import VoiceResponse

    try:
        query_params = request.query_params
        transfer_id = query_params.get("transfer_id")

        logger.info(f"Warm transfer cancelled: transfer_id={transfer_id}")

        response = VoiceResponse()
        response.say(
            "The person you were being transferred to is not available. "
            "Let me connect you back to our team.",
            voice="Polly.Joanna"
        )

        # Could redirect back to AI or queue here
        # For now, just end the call
        response.say("Thank you for your patience. Goodbye.")
        response.hangup()

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in warm cancel TwiML: {e}")
        response = VoiceResponse()
        response.say("Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


# ============================================================================
# TRANSFER TWIML HELPERS
# ============================================================================

@router.post("/twiml/whisper")
async def whisper_twiml(request: Request):
    """
    Play a whisper message to the recipient before connecting.
    Used for cold transfers with announcement.
    """
    from twilio.twiml.voice_response import VoiceResponse

    query_params = request.query_params
    message = query_params.get("message", "Incoming call transfer")

    response = VoiceResponse()
    response.say(message, voice="Polly.Joanna")

    return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/transfer-status")
async def transfer_status_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle transfer dial result (success/failure).
    """
    from twilio.twiml.voice_response import VoiceResponse

    try:
        form_data = await request.form()
        query_params = request.query_params

        transfer_id = query_params.get("transfer_id")
        dial_status = form_data.get("DialCallStatus", "completed")

        logger.info(f"Transfer status: transfer_id={transfer_id}, status={dial_status}")

        response = VoiceResponse()

        if dial_status in ["completed", "answered"]:
            # Transfer successful - update and end
            if transfer_id:
                db.execute(text("""
                    UPDATE call_transfers
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {"id": transfer_id})
                db.commit()

        elif dial_status in ["no-answer", "busy", "failed"]:
            # Transfer failed - update and provide fallback
            if transfer_id:
                db.execute(text("""
                    UPDATE call_transfers
                    SET status = 'failed', failure_reason = :reason
                    WHERE id = :id
                """), {"id": transfer_id, "reason": dial_status})
                db.commit()

                # Notify the initiating agent that the transfer failed
                _notify_agent_transfer_event(
                    db, int(transfer_id), "failed", details=dial_status
                )

            response.say(
                "We were unable to complete your transfer. Please try again later.",
                voice="Polly.Joanna"
            )

        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    except SQLAlchemyError as e:
        logger.error(f"Error in transfer status TwiML: {e}")
        response = VoiceResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


# ============================================================================
# WEBHOOK ENDPOINTS
# ============================================================================

@router.post("/webhook/consult-status")
async def consultation_status_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook for consultation call status updates.
    """
    from services.webhook_security import verify_twilio_webhook
    await verify_twilio_webhook(request)

    try:
        form_data = await request.form()
        query_params = request.query_params

        transfer_id = query_params.get("transfer_id")
        call_status = form_data.get("CallStatus", "")

        logger.info(f"Consultation status: transfer_id={transfer_id}, status={call_status}")

        if call_status in ["no-answer", "busy", "failed", "canceled"]:
            # Consultation failed - handle fallback
            db.execute(text("""
                UPDATE call_transfers
                SET status = 'failed',
                    failure_reason = :reason,
                    consultation_ended_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'consulting'
            """), {"id": transfer_id, "reason": f"Consultation {call_status}"})
            db.commit()

            # Notify the initiating agent that the consultation failed
            if transfer_id:
                _notify_agent_transfer_event(
                    db, int(transfer_id), "consultation_failed",
                    details=f"Consultation {call_status}"
                )

        elif call_status == "completed":
            db.execute(text("""
                UPDATE call_transfers
                SET consultation_ended_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": transfer_id})
            db.commit()

        return {"status": "ok"}

    except SQLAlchemyError as e:
        logger.error(f"Error in consultation status webhook: {e}")
        return {"status": "error", "message": "Internal server error"}


# ============================================================================
# TRANSFER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("")
async def list_transfers(
    status: Optional[str] = None,
    transfer_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """List call transfers"""
    try:
        params = {"limit": limit, "offset": offset}
        conditions = ["1=1"]

        if status:
            conditions.append("ct.status = :status")
            params["status"] = status

        if transfer_type:
            conditions.append("ct.transfer_type = :type")
            params["type"] = transfer_type

        where_clause = " AND ".join(conditions)

        results = db.execute(text(f"""
            SELECT ct.id, ct.transfer_type, ct.status, ct.original_call_sid,
                   ct.transfer_call_sid, ct.to_phone, ct.to_user_id,
                   ct.from_user_id, ct.transfer_reason, ct.initiated_at, ct.completed_at,
                   fu.full_name as from_user_name, tu.full_name as to_user_name
            FROM call_transfers ct
            LEFT JOIN users fu ON fu.id = ct.from_user_id
            LEFT JOIN users tu ON tu.id = ct.to_user_id
            WHERE {where_clause}
            ORDER BY ct.initiated_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

        transfers = []
        for row in results:
            transfers.append({
                "id": row.id,
                "transfer_type": row.transfer_type,
                "status": row.status,
                "original_call_sid": row.original_call_sid,
                "transfer_call_sid": row.transfer_call_sid,
                "to_phone": row.to_phone,
                "to_user_id": row.to_user_id,
                "to_user_name": row.to_user_name,
                "from_user_id": row.from_user_id,
                "from_user_name": row.from_user_name,
                "transfer_reason": row.transfer_reason,
                "initiated_at": safe_isoformat(row.initiated_at),
                "completed_at": safe_isoformat(row.completed_at)
            })

        return {
            "transfers": transfers,
            "count": len(transfers),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing transfers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/available-recipients")
async def get_available_recipients(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get list of users available for transfer"""
    try:
        results = db.execute(text("""
            SELECT id, full_name, email, phone, role, is_active
            FROM users
            WHERE is_active = TRUE
                AND phone IS NOT NULL
            ORDER BY full_name
        """)).fetchall()

        recipients = []
        for row in results:
            recipients.append({
                "id": row.id,
                "name": row.full_name,
                "email": row.email,
                "phone": row.phone,
                "role": row.role
            })

        return {
            "recipients": recipients,
            "count": len(recipients)
        }

    except Exception as e:
        logger.error(f"Error getting recipients: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{transfer_id}")
async def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get transfer details"""
    try:
        result = db.execute(text("""
            SELECT ct.*, fu.full_name as from_user_name, tu.full_name as to_user_name
            FROM call_transfers ct
            LEFT JOIN users fu ON fu.id = ct.from_user_id
            LEFT JOIN users tu ON tu.id = ct.to_user_id
            WHERE ct.id = :id
        """), {"id": transfer_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Transfer not found")

        return {
            "id": result.id,
            "transfer_type": result.transfer_type,
            "status": result.status,
            "original_call_sid": result.original_call_sid,
            "transfer_call_sid": result.transfer_call_sid,
            "consultation_call_sid": result.consultation_call_sid,
            "to_phone": result.to_phone,
            "to_user_id": result.to_user_id,
            "to_user_name": result.to_user_name,
            "from_user_id": result.from_user_id,
            "from_user_name": result.from_user_name,
            "caller_phone": result.caller_phone,
            "caller_name": result.caller_name,
            "transfer_reason": result.transfer_reason,
            "whisper_message": result.whisper_message,
            "failure_reason": result.failure_reason,
            "initiated_at": safe_isoformat(result.initiated_at),
            "completed_at": safe_isoformat(result.completed_at),
            "consultation_started_at": safe_isoformat(result.consultation_started_at),
            "consultation_ended_at": safe_isoformat(result.consultation_ended_at)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transfer: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
