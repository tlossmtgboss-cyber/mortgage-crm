"""
Telnyx Webhook Routes

Handles all Telnyx webhook callbacks including:
- Call Control events (initiated, ringing, answered, hangup)
- AMD (Answering Machine Detection) events
- SMS delivery status events
- Recording events
"""

import os
import json
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db
from telephony.providers.telnyx.webhooks import (
    parse_telnyx_webhook,
    validate_telnyx_webhook,
    TelnyxCallEvent,
    TelnyxAMDEvent,
    TelnyxSMSEvent,
    TelnyxEventType,
    map_telnyx_status_to_legacy,
    map_telnyx_amd_to_legacy,
)
from telephony.providers.telnyx.texml import TeXMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telnyx", tags=["Telnyx Webhooks"])

# API base URL for callbacks
API_BASE_URL = os.getenv("API_URL") or os.getenv("PRODUCTION_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if API_BASE_URL and not API_BASE_URL.startswith("http"):
    API_BASE_URL = f"https://{API_BASE_URL}"
if not API_BASE_URL:
    API_BASE_URL = "https://api.perenniaai.com"

# Telnyx public key for webhook validation
TELNYX_PUBLIC_KEY = os.getenv("TELNYX_PUBLIC_KEY")


# =============================================================================
# Webhook Validation
# =============================================================================

async def validate_webhook(request: Request) -> bool:
    """Validate incoming Telnyx webhook signature. Fail-closed when key not configured."""
    if not TELNYX_PUBLIC_KEY:
        logger.error("TELNYX_PUBLIC_KEY not configured — rejecting webhook")
        return False

    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    if not signature or not timestamp:
        logger.warning("Missing Telnyx signature headers")
        return False

    body = await request.body()

    return validate_telnyx_webhook(body, signature, timestamp, TELNYX_PUBLIC_KEY)


# =============================================================================
# Main Webhook Handler
# =============================================================================

@router.post("/webhook")
async def handle_telnyx_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Main Telnyx webhook handler.
    Routes events to appropriate handlers based on event type.
    """
    # Validate webhook signature
    if not await validate_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse webhook payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Telnyx webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Parse into typed event
    event = parse_telnyx_webhook(payload)
    event_type = event.event_type

    logger.info(f"Telnyx webhook received: {event_type}")

    # Route to appropriate handler
    if event_type == TelnyxEventType.CALL_MACHINE_DETECTION_ENDED:
        return await handle_amd_event(event, db)

    elif event_type == TelnyxEventType.CALL_ANSWERED:
        return await handle_call_answered(event, db)

    elif event_type == TelnyxEventType.CALL_HANGUP:
        return await handle_call_hangup(event, db)

    elif event_type in [TelnyxEventType.MESSAGE_SENT, TelnyxEventType.MESSAGE_FINALIZED]:
        return await handle_sms_status(event, db)

    elif event_type == TelnyxEventType.MESSAGE_RECEIVED:
        return await handle_inbound_sms(event, db)

    elif event_type == TelnyxEventType.CALL_RECORDING_SAVED:
        return await handle_recording_saved(event, db)

    else:
        logger.info(f"Unhandled Telnyx event type: {event_type}")
        return {"status": "acknowledged", "event_type": event_type}


# =============================================================================
# AMD (Answering Machine Detection) Handler
# =============================================================================

@router.post("/amd/{tracking_id}")
async def handle_amd_callback(
    tracking_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Telnyx AMD callback for a specific call.

    Telnyx AMD result values:
    - "human": Human answered
    - "machine": Machine/voicemail detected
    - "not_sure": Could not determine
    - "unknown": Detection failed
    """
    if not await validate_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse AMD callback: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = parse_telnyx_webhook(payload)

    if not isinstance(event, TelnyxAMDEvent):
        logger.warning(f"Expected AMD event, got {type(event)}")
        return {"status": "ignored"}

    return await process_amd_result(tracking_id, event, db)


async def handle_amd_event(event: TelnyxAMDEvent, db: Session):
    """Handle AMD event from main webhook"""
    call_control_id = event.call_control_id

    # Look up tracking ID by call_control_id
    result = db.execute(sa_text("""
        SELECT id FROM amd_outbound_calls
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id}).fetchone()

    if not result:
        logger.warning(f"No tracking record for call {call_control_id}")
        return {"status": "ignored"}

    tracking_id = result[0]
    return await process_amd_result(str(tracking_id), event, db)


async def process_amd_result(tracking_id: str, event: TelnyxAMDEvent, db: Session):
    """Process AMD result and redirect call accordingly"""
    from telephony import get_telephony_provider

    amd_result = event.result
    call_control_id = event.call_control_id

    # Map to legacy-compatible format for database consistency
    legacy_format = map_telnyx_amd_to_legacy(event)
    answered_by = legacy_format["AnsweredBy"]

    logger.info(f"AMD Result for {tracking_id}: result={amd_result}, answered_by={answered_by}")

    # Determine category
    if amd_result == "human":
        answered_category = "human"
    elif amd_result == "machine":
        answered_category = "machine"
    else:
        answered_category = "unknown"

    # Update AMD results in database
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET amd_status = :amd_status,
            answered_by = :answered_by,
            amd_completed_at = NOW()
        WHERE id = :tracking_id
    """), {
        "amd_status": amd_result,
        "answered_by": answered_category,
        "tracking_id": tracking_id,
    })
    db.commit()

    # Determine redirect URL based on AMD result
    if answered_category == "human" or answered_category == "unknown":
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/connect-ai/{tracking_id}"
        action = "connect_ai"
    elif answered_category == "machine":
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/voicemail/{tracking_id}"
        action = "play_voicemail"
    else:
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/hangup/{tracking_id}"
        action = "hangup"

    # Redirect the call using Telnyx Call Control
    try:
        provider = get_telephony_provider()
        # Use Telnyx transfer command to redirect
        if hasattr(provider, 'client') and provider.client:
            provider.client.calls.transfer(
                call_control_id=call_control_id,
                audio_url=redirect_url,
            )
            logger.info(f"Redirected Telnyx call {call_control_id} to {redirect_url}")
    except Exception as e:
        logger.error(f"Failed to redirect Telnyx call: {e}")

    return {
        "status": "processed",
        "tracking_id": tracking_id,
        "amd_result": amd_result,
        "action": action,
    }


# =============================================================================
# Call Event Handlers
# =============================================================================

async def handle_call_answered(event: TelnyxCallEvent, db: Session):
    """Handle call answered event"""
    call_control_id = event.call_control_id

    logger.info(f"Call answered: {call_control_id}")

    # Update call status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'answered'
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id})
    db.commit()

    return {"status": "acknowledged", "call_id": call_control_id}


async def handle_call_hangup(event: TelnyxCallEvent, db: Session):
    """Handle call hangup event"""
    call_control_id = event.call_control_id
    hangup_cause = event.hangup_cause

    logger.info(f"Call hangup: {call_control_id}, cause: {hangup_cause}")

    # Update call status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'completed',
            call_ended_at = NOW()
        WHERE call_sid = :call_id
    """), {"call_id": call_control_id})
    db.commit()

    return {"status": "acknowledged", "call_id": call_control_id, "cause": hangup_cause}


# =============================================================================
# SMS Event Handlers
# =============================================================================

async def handle_sms_status(event: TelnyxSMSEvent, db: Session):
    """Handle SMS delivery status update"""
    message_id = event.message_id
    status = event.status

    logger.info(f"SMS status update: {message_id} -> {status}")

    # Update SMS status in database if we're tracking it
    try:
        db.execute(sa_text("""
            UPDATE sms_messages
            SET delivery_status = :status,
                updated_at = NOW()
            WHERE provider_message_id = :message_id
        """), {"status": status, "message_id": message_id})
        db.commit()
    except Exception as e:
        logger.debug(f"SMS message not found in tracking table: {e}")

    return {"status": "acknowledged", "message_id": message_id}


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format for matching."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif not digits.startswith('+'):
        return f"+{digits}"
    return phone


async def handle_inbound_sms(event: TelnyxSMSEvent, db: Session):
    """Handle inbound SMS message with full workflow triggers."""
    from_number = event.from_number
    to_number = event.to_number
    message_body = event.text
    normalized_from = _normalize_phone(from_number)
    normalized_to = _normalize_phone(to_number)

    logger.info(f"Inbound SMS from {from_number}: {message_body[:50]}...")

    # Store inbound SMS in sms_messages table
    try:
        db.execute(sa_text("""
            INSERT INTO sms_messages (
                direction, from_number, to_number, body,
                provider, provider_message_id, status, created_at
            ) VALUES (
                'inbound', :from_number, :to_number, :body,
                'telnyx', :message_id, 'received', NOW()
            )
        """), {
            "from_number": from_number,
            "to_number": to_number,
            "body": message_body,
            "message_id": event.message_id,
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to store inbound SMS: {e}")

    # ==========================================================================
    # Workflow Trigger: Feed into SMS Intelligence Queue for AI analysis,
    # entity matching, SLA tracking, and notification dispatching.
    # This mirrors the telephony webhook flow in sms_intelligence_routes.py.
    # ==========================================================================

    intelligence_queue_id = None
    try:
        # Insert into sms_intelligence_queue (same schema as telephony webhook path)
        result = db.execute(sa_text("""
            INSERT INTO sms_intelligence_queue (
                sms_provider, provider_message_id, from_phone, to_phone,
                direction, message_body, has_media, media_count,
                received_at, status
            ) VALUES (
                'telnyx', :message_id, :from_phone, :to_phone,
                'inbound', :body, :has_media, :media_count,
                CURRENT_TIMESTAMP, 'pending'
            )
            ON CONFLICT (sms_provider, provider_message_id) DO NOTHING
            RETURNING id
        """), {
            "message_id": event.message_id,
            "from_phone": normalized_from,
            "to_phone": normalized_to,
            "body": message_body,
            "has_media": False,  # Telnyx media handled separately if needed
            "media_count": 0,
        })
        row = result.fetchone()
        if row:
            intelligence_queue_id = row[0]
        db.commit()
        logger.info(f"Telnyx SMS queued for intelligence processing: id={intelligence_queue_id}")
    except Exception as e:
        logger.error(f"Failed to queue SMS for intelligence processing: {e}")
        db.rollback()

    # Trigger background AI analysis and workflow processing
    if intelligence_queue_id:
        try:
            from routes.sms_intelligence_routes import process_incoming_sms
            asyncio.create_task(process_incoming_sms(intelligence_queue_id))
            logger.info(f"Background SMS processing triggered for queue id {intelligence_queue_id}")
        except ImportError:
            logger.warning("sms_intelligence_routes not available, skipping AI analysis")
        except Exception as e:
            logger.error(f"Failed to trigger background SMS processing: {e}")

    # ==========================================================================
    # Real-time notification: Alert loan officer via WebSocket
    # ==========================================================================

    try:
        # Look up which user owns this phone number / is assigned to the contact
        lo_match = db.execute(sa_text("""
            SELECT DISTINCT l.loan_officer_id
            FROM loans l
            WHERE l.borrower_phone = :phone
            AND l.loan_officer_id IS NOT NULL
            LIMIT 1
        """), {"phone": normalized_from}).fetchone()

        if not lo_match:
            # Try matching via leads table
            lo_match = db.execute(sa_text("""
                SELECT DISTINCT l.assigned_to
                FROM leads l
                WHERE l.phone = :phone
                AND l.assigned_to IS NOT NULL
                LIMIT 1
            """), {"phone": normalized_from}).fetchone()

        if lo_match:
            lo_user_id = lo_match[0]
            try:
                from services.workflow_websocket_events import WorkflowWebSocketNotifier
                notifier = WorkflowWebSocketNotifier()
                notifier.notify_user_sync(lo_user_id, {
                    "type": "sms_received",
                    "from_phone": from_number,
                    "preview": message_body[:100] if message_body else "",
                    "provider": "telnyx",
                    "queue_id": intelligence_queue_id,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                logger.info(f"WebSocket notification sent to LO user_id={lo_user_id}")
            except ImportError:
                logger.debug("WebSocket notifier not available")
            except Exception as e:
                logger.debug(f"WebSocket notification failed (non-critical): {e}")
    except Exception as e:
        logger.debug(f"LO lookup for notification failed (non-critical): {e}")

    return {"status": "received", "from": from_number, "queue_id": intelligence_queue_id}


# =============================================================================
# Recording Handler
# =============================================================================

async def handle_recording_saved(event: TelnyxCallEvent, db: Session):
    """Handle call recording saved event"""
    call_control_id = event.call_control_id
    recording_url = event.payload.get("recording_urls", {}).get("mp3")

    logger.info(f"Recording saved for {call_control_id}: {recording_url}")

    if recording_url:
        # Store recording URL
        db.execute(sa_text("""
            UPDATE call_attempts
            SET recording_url = :url
            WHERE call_sid = :call_id
        """), {"url": recording_url, "call_id": call_control_id})
        db.commit()

    return {"status": "acknowledged", "recording_url": recording_url}


# =============================================================================
# TeXML Response Endpoints (for call control)
# =============================================================================

@router.post("/texml/waiting/{tracking_id}")
@router.get("/texml/waiting/{tracking_id}")
async def texml_waiting(tracking_id: str):
    """TeXML response while AMD is running - pause briefly"""
    response = TeXMLResponse()
    response.pause(length=3)
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/hangup")
@router.get("/texml/hangup")
async def texml_hangup():
    """TeXML response to hang up the call"""
    response = TeXMLResponse()
    response.hangup()
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/voicemail/{tracking_id}")
@router.get("/texml/voicemail/{tracking_id}")
async def texml_voicemail(
    tracking_id: str,
    db: Session = Depends(get_db)
):
    """TeXML response to play voicemail message"""
    # Get call info
    result = db.execute(sa_text("""
        SELECT voicemail_message, voicemail_audio, client_name, lo_name, purpose
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    response = TeXMLResponse()

    if not result:
        response.hangup()
        return Response(content=response.to_xml(), media_type="application/xml")

    voicemail_message, voicemail_audio, client_name, lo_name, purpose = result

    # Update status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'voicemail_left', handling_method = 'voicemail_tts'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    db.commit()

    response.pause(length=1)

    if voicemail_audio:
        # Use pre-generated audio
        audio_url = f"{API_BASE_URL}/api/v1/voice/amd/audio/{tracking_id}"
        response.play(audio_url)
    else:
        # Fall back to TTS
        first_name = client_name.split()[0] if client_name else ""
        greeting = f"Hi {first_name}" if first_name else "Hi"
        message = voicemail_message or (
            f"{greeting}, this is Sam calling on behalf of {lo_name or 'your loan officer'} "
            f"at CMG Home Loans regarding {purpose or 'your loan'}. "
            f"Please give us a call back at your earliest convenience. "
            f"Thank you and have a great day!"
        )
        response.say(message, voice="Polly.Joanna")

    response.pause(length=1)
    response.hangup()

    logger.info(f"Playing voicemail for {tracking_id}")
    return Response(content=response.to_xml(), media_type="application/xml")


@router.post("/texml/connect-ai/{tracking_id}")
@router.get("/texml/connect-ai/{tracking_id}")
async def texml_connect_ai(
    tracking_id: str,
    db: Session = Depends(get_db)
):
    """TeXML response to connect call to AI via WebSocket stream"""
    # Get call info
    result = db.execute(sa_text("""
        SELECT client_name, to_number, purpose, lo_name
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    response = TeXMLResponse()

    if not result:
        response.hangup()
        return Response(content=response.to_xml(), media_type="application/xml")

    client_name, to_number, purpose, lo_name = result

    # Update status
    db.execute(sa_text("""
        UPDATE amd_outbound_calls
        SET status = 'connected', handling_method = 'ai_stream'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    db.commit()

    # Get domain for WebSocket
    domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'api.perenniaai.com'

    # Connect to voice stream via WebSocket
    # Note: Telnyx uses the same Connect/Stream structure as TwiML
    ws_url = f"wss://{domain}/api/v1/voice/ws/voice-stream"

    connect_ctx = response.connect()
    connect_ctx.stream(
        url=ws_url,
        track="both_tracks",
    )
    connect_ctx.end_connect()

    logger.info(f"Connecting call {tracking_id} to AI stream")
    return Response(content=response.to_xml(), media_type="application/xml")
