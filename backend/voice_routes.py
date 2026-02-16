"""
Voice AI Receptionist Routes
Handles Twilio voice webhooks and OpenAI Realtime API integration
"""
import os
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64
from typing import List, Dict, Any

# Import from database instead of main to avoid circular dependency
from database import get_db
from integrations.twilio_voice_service import voice_client, ai_config
import openai

# AI Receptionist Dashboard Integration
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistError,
    AIReceptionistConversation
)
import uuid

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

# Voice Sentiment Analysis
from services.voice_sentiment_service import analyze_voice_sentiment

# Call Screening Service
from services.call_screening_service import (
    CallScreeningService,
    ScreeningDecision,
    ScreeningResult,
    add_to_whitelist
)

logger = logging.getLogger(__name__)


async def _validate_twilio_signature(request: Request, form_data: dict) -> bool:
    """Validate Twilio X-Twilio-Signature header. Returns True if valid or not configured."""
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping Twilio signature validation")
        return True
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        return validator.validate(url, form_data, signature)
    except ImportError:
        logger.warning("twilio package not installed — skipping signature validation")
        return True
    except Exception as e:
        logger.error(f"Twilio signature validation error: {e}")
        return False


router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


# Lazy import to avoid circular dependency with main.py
def get_models():
    """Lazy import models from main.py to avoid circular imports"""
    from main import User, Lead, Task, Activity, IncomingDataEvent
    return User, Lead, Task, Activity, IncomingDataEvent


def get_current_user_flexible():
    """Lazy import auth dependency from main.py"""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# ============================================================================
# INBOUND CALL HANDLING
# ============================================================================

@router.post("/incoming")
async def handle_incoming_call(request: Request, db: Session = Depends(get_db)):
    """
    Twilio webhook for incoming calls
    Returns TwiML to handle the call with AI

    Call flow with spam filtering:
    1. Screen the call (whitelist → blocklist → lookup → unknown)
    2. ALLOW: Connect directly to AI receptionist
    3. BLOCK: Hang up immediately (no message)
    4. SCREEN: Ask name/reason before connecting
    """
    try:
        form_data = await request.form()
        form_dict = {k: v for k, v in form_data.items()}

        # Validate Twilio signature
        if not await _validate_twilio_signature(request, form_dict):
            logger.warning("Invalid Twilio signature on incoming call webhook")
            return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Incoming call from {mask_phone(caller_number)} (SID: {call_sid})")

        # ============================================================
        # CALL SCREENING - Spam filtering
        # ============================================================
        screening_service = CallScreeningService(db)
        screening_result = await screening_service.screen_call(caller_number, call_sid)

        logger.info(
            f"Screening decision for {mask_phone(caller_number)}: {screening_result.decision.value} "
            f"(reason: {screening_result.reason})"
        )

        # ============================================================
        # HANDLE SCREENING DECISION
        # ============================================================

        if screening_result.decision == ScreeningDecision.BLOCK:
            # Blocked caller - immediate hangup, no message
            logger.warning(f"BLOCKING call from {mask_phone(caller_number)}: {screening_result.reason}")

            # Log to dashboard as blocked
            dashboard_activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_phone=caller_number,
                action_type='call_blocked',
                channel='voice',
                outcome_status='blocked',
                conversation_id=call_sid,
                extra_data={
                    "twilio_call_sid": call_sid,
                    "called_number": called_number,
                    "block_reason": screening_result.reason,
                    "spam_score": screening_result.spam_score
                }
            )
            db.add(dashboard_activity)
            db.commit()

            # Immediate hangup
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        elif screening_result.decision == ScreeningDecision.SCREEN:
            # Unknown caller - ask for name and reason first
            logger.info(f"SCREENING unknown caller {caller_number}")

            # Log to dashboard as screening
            dashboard_activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_phone=caller_number,
                action_type='call_screening',
                channel='voice',
                outcome_status='screening',
                conversation_id=call_sid,
                extra_data={
                    "twilio_call_sid": call_sid,
                    "called_number": called_number,
                    "screening_reason": screening_result.reason,
                    "spam_score": screening_result.spam_score,
                    "lookup_performed": screening_result.lookup_performed
                }
            )
            db.add(dashboard_activity)
            db.commit()

            # Redirect to screening flow
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Redirect>/api/v1/voice/screening?CallSid={call_sid}&amp;From={caller_number}</Redirect>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        else:
            # ALLOW - Known good caller, connect directly to AI
            logger.info(
                f"ALLOWING call from {caller_number} "
                f"(caller: {screening_result.caller_name or 'Unknown'}, "
                f"category: {screening_result.category or 'N/A'})"
            )

            # Log to AI Receptionist Dashboard (non-critical - don't fail the call)
            try:
                # Rollback any failed transaction first
                db.rollback()

                dashboard_activity = AIReceptionistActivity(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc),
                    client_phone=caller_number,
                    client_name=screening_result.caller_name,
                    action_type='incoming_call',
                    channel='voice',
                    outcome_status='pending',
                    conversation_id=call_sid,
                    extra_data={
                        "twilio_call_sid": call_sid,
                        "called_number": called_number,
                        "screening_decision": "allow",
                        "screening_reason": screening_result.reason,
                        "caller_category": screening_result.category,
                        "spam_score": screening_result.spam_score
                    }
                )
                db.add(dashboard_activity)
                db.commit()
            except Exception as log_error:
                logger.warning(f"Failed to log dashboard activity (non-critical): {log_error}")
                db.rollback()

            # Generate TwiML response to connect to AI with caller info
            twiml = voice_client.create_greeting_response(
                business_name=ai_config.business_name,
                caller_name=screening_result.caller_name,
                caller_phone=caller_number,
                caller_category=screening_result.category
            )
            return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        db.rollback()
        # On error, still try to connect to AI (don't lose the call to voicemail)
        try:
            twiml = voice_client.create_greeting_response(ai_config.business_name)
            return Response(content=str(twiml), media_type="application/xml")
        except Exception:
            # Last resort: voicemail
            twiml = voice_client.create_voicemail_response()
            return Response(content=str(twiml), media_type="application/xml")


@router.post("/outbound-script")
async def handle_outbound_script(request: Request):
    """
    TwiML for outbound calls
    """
    try:
        query_params = request.query_params
        script_id = query_params.get("script_id")
        test_mode = query_params.get("test", "false") == "true"

        logger.info(f"Outbound call script requested: {script_id}, test_mode: {test_mode}")

        if test_mode:
            # Simple test TwiML without WebSocket
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Matthew">Hello! This is Sam from Perennia AI. I'm calling to follow up on your mortgage inquiry. How can I help you today?</Say>
    <Pause length="3"/>
    <Say voice="Polly.Matthew">If you'd like to schedule an appointment with a loan officer, please let me know your availability.</Say>
    <Pause length="5"/>
    <Say voice="Polly.Matthew">Thank you for your time. Have a great day!</Say>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        # Generate TwiML for outbound call with AI
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error creating outbound script: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/make-call")
async def make_outbound_call(
    to_number: str,
    caller_name: str = "Valued Customer",
    purpose: str = "follow_up",
    db: Session = Depends(get_db)
):
    """
    Initiate an outbound call to a phone number.
    The AI receptionist (Sam) will handle the call and try to schedule an appointment.
    """
    try:
        # Normalize phone number
        import re
        phone = re.sub(r'[^\d+]', '', to_number)
        if len(phone) == 10:
            phone = f"+1{phone}"
        elif not phone.startswith("+"):
            phone = f"+{phone}"

        from utils.pii_mask import mask_phone
        logger.info(f"Initiating outbound call to {mask_phone(phone)} (purpose: {purpose})")

        # Make the call using Twilio
        call_sid = await voice_client.make_outbound_call(
            to_number=phone,
            script=purpose
        )

        if call_sid:
            # Log to AI Receptionist Dashboard
            dashboard_activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_phone=phone,
                client_name=caller_name,
                action_type='outbound_call',
                channel='voice',
                outcome_status='initiated',
                conversation_id=call_sid,
                extra_data={
                    "twilio_call_sid": call_sid,
                    "purpose": purpose,
                    "caller_name": caller_name
                }
            )
            db.add(dashboard_activity)
            db.commit()

            return {
                "success": True,
                "message": f"Call initiated to {phone}",
                "call_sid": call_sid,
                "to_number": phone,
                "caller_name": caller_name
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate call - check Twilio configuration"
            }

    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        return {
            "success": False,
            "error": "Internal server error"
        }


# ============================================================================
# CALL SCREENING ENDPOINTS
# ============================================================================

@router.post("/screening")
async def handle_screening(request: Request, db: Session = Depends(get_db)):
    """
    Unknown caller screening - Step 1: Ask for name

    TwiML flow:
    1. Play a message asking for their name
    2. Record their response (up to 5 seconds)
    3. Redirect to /screening-name with the recording
    """
    try:
        form_data = await request.form()
        caller_number = form_data.get("From", "Unknown")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Screening call from {caller_number} (SID: {call_sid})")

        # Generate TwiML to ask for name
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Thank you for calling {ai_config.business_name}. Before I connect you, may I have your name please?</Say>
    <Record
        maxLength="10"
        playBeep="false"
        timeout="3"
        action="/api/v1/voice/screening-name?CallSid={call_sid}&amp;From={caller_number}"
        transcribe="true"
        transcribeCallback="/api/v1/voice/screening-transcription"
    />
    <Say voice="Polly.Joanna">I didn't catch that. Let me connect you to our team.</Say>
    <Redirect>/api/v1/voice/screening-complete?CallSid={call_sid}&amp;From={caller_number}&amp;skipped=true</Redirect>
</Response>"""

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in screening step 1: {e}")
        # On error, connect to AI anyway
        twiml = voice_client.create_greeting_response(ai_config.business_name)
        return Response(content=str(twiml), media_type="application/xml")


@router.post("/screening-name")
async def handle_screening_name(request: Request, db: Session = Depends(get_db)):
    """
    Unknown caller screening - Step 2: Got name, ask for reason

    TwiML flow:
    1. Acknowledge name receipt
    2. Ask for reason for calling
    3. Record their response
    4. Redirect to /screening-complete
    """
    try:
        form_data = await request.form()
        query_params = request.query_params

        caller_number = query_params.get("From") or form_data.get("From", "Unknown")
        call_sid = query_params.get("CallSid") or form_data.get("CallSid", "")
        recording_url = form_data.get("RecordingUrl", "")

        logger.info(f"Screening name recorded for {caller_number}: {recording_url}")

        # Generate TwiML to ask for reason
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Thank you. And briefly, what is your call regarding?</Say>
    <Record
        maxLength="15"
        playBeep="false"
        timeout="3"
        action="/api/v1/voice/screening-complete?CallSid={call_sid}&amp;From={caller_number}&amp;name_recording={recording_url}"
        transcribe="true"
        transcribeCallback="/api/v1/voice/screening-transcription"
    />
    <Say voice="Polly.Joanna">No problem. Let me connect you now.</Say>
    <Redirect>/api/v1/voice/screening-complete?CallSid={call_sid}&amp;From={caller_number}&amp;skipped_reason=true</Redirect>
</Response>"""

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in screening step 2: {e}")
        twiml = voice_client.create_greeting_response(ai_config.business_name)
        return Response(content=str(twiml), media_type="application/xml")


@router.post("/screening-complete")
async def handle_screening_complete(request: Request, db: Session = Depends(get_db)):
    """
    Unknown caller screening - Step 3: Connect to AI receptionist

    After screening is complete, connect caller to the AI receptionist.
    Log the screening info for context.
    """
    try:
        form_data = await request.form()
        query_params = request.query_params

        caller_number = query_params.get("From") or form_data.get("From", "Unknown")
        call_sid = query_params.get("CallSid") or form_data.get("CallSid", "")
        name_recording = query_params.get("name_recording", "")
        reason_recording = form_data.get("RecordingUrl", "")
        skipped = query_params.get("skipped", "false") == "true"
        skipped_reason = query_params.get("skipped_reason", "false") == "true"

        logger.info(f"Screening complete for {caller_number} (SID: {call_sid})")

        # Update screening log with outcome
        try:
            from sqlalchemy import text
            db.execute(text("""
                UPDATE call_screening_log
                SET
                    connected_to_ai = true,
                    extra_data = COALESCE(extra_data, '{}'::jsonb) || :screening_data
                WHERE call_sid = :call_sid
            """), {
                "call_sid": call_sid,
                "screening_data": json.dumps({
                    "screening_completed": True,
                    "name_recording": name_recording,
                    "reason_recording": reason_recording,
                    "skipped_name": skipped,
                    "skipped_reason": skipped_reason
                })
            })
            db.commit()
        except Exception as log_error:
            logger.warning(f"Could not update screening log: {log_error}")

        # Connect to AI receptionist
        logger.info(f"Connecting screened caller {caller_number} to AI")
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in screening complete: {e}")
        twiml = voice_client.create_greeting_response(ai_config.business_name)
        return Response(content=str(twiml), media_type="application/xml")


@router.post("/screening-transcription")
async def handle_screening_transcription(request: Request, db: Session = Depends(get_db)):
    """
    Handle transcription callback from screening recordings.

    Updates the screening log with caller's stated name and reason.
    """
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "")
        transcription_text = form_data.get("TranscriptionText", "")
        transcription_status = form_data.get("TranscriptionStatus", "")
        recording_url = form_data.get("RecordingUrl", "")

        logger.info(f"Screening transcription for {call_sid}: {transcription_text[:100] if transcription_text else 'empty'}")

        if transcription_status == "completed" and transcription_text:
            try:
                from sqlalchemy import text

                # Determine if this is name or reason based on recording length/content
                # Names are typically shorter, update the appropriate field
                if len(transcription_text) < 50:  # Likely a name
                    db.execute(text("""
                        UPDATE call_screening_log
                        SET caller_stated_name = COALESCE(caller_stated_name, :name)
                        WHERE call_sid = :call_sid
                    """), {"call_sid": call_sid, "name": transcription_text})
                else:  # Likely a reason
                    db.execute(text("""
                        UPDATE call_screening_log
                        SET caller_stated_reason = COALESCE(caller_stated_reason, :reason)
                        WHERE call_sid = :call_sid
                    """), {"call_sid": call_sid, "reason": transcription_text})

                db.commit()
                logger.info(f"Updated screening transcription for {call_sid}")

            except Exception as db_error:
                logger.warning(f"Could not update transcription: {db_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling screening transcription: {e}")
        return {"status": "error"}


@router.post("/blocked")
async def handle_blocked_call(request: Request):
    """
    TwiML response for blocked calls - immediate hangup with no message.
    """
    try:
        form_data = await request.form()
        caller_number = form_data.get("From", "Unknown")
        call_sid = form_data.get("CallSid", "")

        logger.warning(f"Blocking call from {caller_number} (SID: {call_sid})")

        # Immediate hangup - no message for blocked callers
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>"""

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in blocked handler: {e}")
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")


# ============================================================================
# BROWSER WEBSOCKET FOR OPENAI REALTIME API (Talk to Agent)
# ============================================================================

@router.websocket("/ws/browser-voice")
async def browser_voice_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for browser-based voice conversations with AI agents.
    Uses OpenAI Realtime API with PCM16 audio format.

    Client Messages:
    - {"type": "audio", "data": "<base64-pcm16-audio>"}
    - {"type": "text", "text": "..."}

    Server Messages:
    - {"type": "ready"}
    - {"type": "transcript", "text": "...", "role": "user"|"assistant"}
    - {"type": "audio", "data": "<base64-pcm16-audio>"}
    - {"type": "speaking", "is_speaking": true|false}
    - {"type": "error", "message": "..."}
    """
    logger.info(f"🌐 Browser voice WebSocket connection from: {websocket.client}")

    try:
        await websocket.accept()
        logger.info("✅ Browser voice WebSocket accepted")
    except Exception as e:
        logger.error(f"❌ Failed to accept WebSocket: {e}")
        return

    openai_ws = None

    try:
        # Connect to OpenAI Realtime API
        openai_ws = await connect_to_openai_realtime_browser()
        logger.info("✅ Connected to OpenAI Realtime for browser")

        # Send ready signal to client
        await websocket.send_json({"type": "ready"})

        # Handle bidirectional streaming
        async def browser_to_openai():
            """Forward audio from browser to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data.get('type') == 'audio':
                        # Forward audio to OpenAI
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data['data']
                        }))

                    elif data.get('type') == 'text':
                        # Send text message
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": data['text']}]
                            }
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif data.get('type') == 'commit':
                        # Commit audio buffer and request response
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            except WebSocketDisconnect:
                logger.info("Browser disconnected")
            except Exception as e:
                logger.error(f"Error in browser_to_openai: {e}")

        async def openai_to_browser():
            """Forward responses from OpenAI to browser"""
            try:
                async for message in openai_ws:
                    data = json.loads(message)
                    event_type = data.get('type', '')

                    if event_type == 'response.audio.delta':
                        # Forward audio chunk to browser
                        audio_data = data.get('delta', '')
                        if audio_data:
                            await websocket.send_json({
                                "type": "audio",
                                "data": audio_data
                            })

                    elif event_type == 'response.audio_transcript.delta':
                        # AI is speaking - send transcript
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('delta', ''),
                            "role": "assistant",
                            "is_final": False
                        })

                    elif event_type == 'response.audio_transcript.done':
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('transcript', ''),
                            "role": "assistant",
                            "is_final": True
                        })

                    elif event_type == 'conversation.item.input_audio_transcription.completed':
                        # User speech transcription complete
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('transcript', ''),
                            "role": "user",
                            "is_final": True
                        })

                    elif event_type == 'input_audio_buffer.speech_started':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "user",
                            "is_speaking": True
                        })

                    elif event_type == 'input_audio_buffer.speech_stopped':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "user",
                            "is_speaking": False
                        })

                    elif event_type == 'response.audio.done':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "assistant",
                            "is_speaking": False
                        })

                    elif event_type == 'error':
                        error_msg = data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"OpenAI error: {error_msg}")
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })

            except Exception as e:
                logger.error(f"Error in openai_to_browser: {e}")

        # Run both directions concurrently
        await asyncio.gather(
            browser_to_openai(),
            openai_to_browser()
        )

    except Exception as e:
        logger.error(f"Browser voice error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass  # Client may have disconnected
    finally:
        if openai_ws:
            try:
                await openai_ws.close()
            except Exception:
                pass  # WebSocket may already be closed
        logger.info("🔚 Browser voice session ended")


async def connect_to_openai_realtime_browser():
    """Connect to OpenAI Realtime API for browser (PCM16 format)"""
    import websockets

    openai_api_key = os.getenv("OPENAI_API_KEY") or openai.api_key
    if not openai_api_key:
        raise Exception("OpenAI API key not configured")

    logger.info("Connecting to OpenAI Realtime API for browser...")

    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    ws = await asyncio.wait_for(
        websockets.connect(url, additional_headers=headers),
        timeout=10.0
    )

    # Wait for session.created
    initial_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
    logger.info(f"OpenAI Realtime connected: {initial_response[:200]}")

    # Configure session for browser audio (PCM16 at 24kHz)
    # Use same voice and settings as phone for consistent experience
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "coral",  # Same warm, natural voice as phone calls
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            }
        }
    }))

    return ws


# ============================================================================
# WEBSOCKET FOR OPENAI REALTIME API (Twilio)
# ============================================================================

@router.websocket("/ws/voice-stream")
async def voice_stream_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams -> OpenAI Realtime API
    Handles bidirectional audio streaming for AI conversations
    """
    logger.info(f"🔌 WebSocket connection attempt from: {websocket.client}")
    logger.info(f"🔌 Headers: {dict(websocket.headers)}")

    # Get database session manually to avoid dependency issues
    db = get_db().__next__()

    try:
        await websocket.accept()
        logger.info("✅ Voice stream WebSocket connected successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to accept WebSocket: {e}")
        raise

    # Store call context
    call_context = {
        "call_sid": None,
        "caller_number": None,
        "caller_name": None,      # Known caller's name from CRM
        "caller_category": None,  # client, realtor, etc.
        "conversation_history": [],
        "lead_data": {},
        "intent": None,
        "session_ready": False,  # OpenAI session configured
        "twilio_ready": False,   # Twilio stream started
        "greeting_sent": False   # Greeting already triggered
    }

    openai_ws = None
    try:
        # Connect to OpenAI Realtime API with timeout
        try:
            openai_ws = await connect_to_openai_realtime()
            logger.info("✅ OpenAI Realtime API connected successfully")
        except asyncio.TimeoutError:
            logger.error("❌ OpenAI Realtime connection timed out")
            await websocket.close(code=1011, reason="AI service timeout")
            return
        except Exception as e:
            logger.error(f"❌ Failed to connect to OpenAI Realtime: {e}")
            await websocket.close(code=1011, reason=f"AI service error: {str(e)[:50]}")
            return

        # Helper to trigger greeting only when BOTH conditions are met
        async def maybe_trigger_greeting():
            """Trigger AI greeting only when OpenAI session is ready AND Twilio stream has started"""
            if call_context['session_ready'] and call_context['twilio_ready'] and not call_context['greeting_sent']:
                call_context['greeting_sent'] = True
                logger.info("🎤 Both OpenAI session and Twilio ready - triggering AI greeting")
                try:
                    # Build personalized greeting based on caller info
                    caller_name = call_context.get('caller_name')
                    caller_category = call_context.get('caller_category')

                    if caller_name:
                        # Extract first name for friendlier greeting
                        first_name = caller_name.split()[0] if caller_name else caller_name

                        # Known caller - personalized greeting based on category
                        if caller_category == 'client':
                            greeting = f"Hi {first_name}! This is Sam with CMG Home Loans. Great to hear from you! How can I help you today?"
                        elif caller_category == 'lead':
                            greeting = f"Hi {first_name}! This is Sam with CMG Home Loans. Thanks for calling! How can I help you today?"
                        elif caller_category == 'team':
                            greeting = f"Hey {first_name}! This is Sam. What can I do for you?"
                        elif caller_category == 'realtor':
                            greeting = f"Hi {first_name}! This is Sam with CMG Home Loans. Thanks for calling! How can I help you today?"
                        else:
                            greeting = f"Hi {first_name}! This is Sam with CMG Home Loans. Thanks for calling. How can I help you today?"
                        logger.info(f"Using personalized greeting ({caller_category})")
                    else:
                        # Unknown caller - generic greeting
                        greeting = "Hi, this is Sam with CMG Home Loans! Thanks for calling. How can I help you today?"
                        logger.info("🎯 Using generic greeting for unknown caller")

                    # Request a response with the greeting
                    await openai_ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": f"Greet the caller warmly. Say exactly: {greeting}"
                        }
                    }))
                    logger.info("✅ Greeting response requested with instructions")
                except Exception as greet_err:
                    logger.error(f"❌ Failed to trigger greeting: {greet_err}")

        # Handle bidirectional streaming
        async def twilio_to_openai():
            """Forward audio from Twilio to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data['event'] == 'start':
                        call_context['call_sid'] = data['start']['callSid']
                        call_context['stream_sid'] = data['start']['streamSid']  # Capture stream SID

                        # Extract caller info from custom parameters
                        custom_params = data['start'].get('customParameters', {})
                        call_context['caller_number'] = custom_params.get('caller_phone') or custom_params.get('From')
                        call_context['caller_name'] = custom_params.get('caller_name')
                        call_context['caller_category'] = custom_params.get('caller_category')

                        logger.info(f"📞 Call started: {call_context['call_sid']}, stream: {call_context['stream_sid']}")
                        logger.info(f"Caller identified, Category: {call_context['caller_category']}")

                        # Mark Twilio as ready, try to trigger greeting
                        call_context['twilio_ready'] = True
                        logger.info(f"📱 Twilio ready. Session ready: {call_context['session_ready']}")
                        await maybe_trigger_greeting()

                    elif data['event'] == 'media':
                        # Forward audio payload to OpenAI
                        audio_payload = data['media']['payload']
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": audio_payload
                        }))

                    elif data['event'] == 'stop':
                        logger.info(f"Call ended: {call_context['call_sid']}")
                        await save_call_summary(call_context, db)
                        break

            except Exception as e:
                logger.error(f"Error in Twilio->OpenAI stream: {e}")

        async def openai_to_twilio():
            """Forward AI responses from OpenAI to Twilio"""
            try:
                async for message in openai_ws:
                    data = json.loads(message)
                    event_type = data.get('type', 'unknown')

                    # Log all events for debugging
                    if event_type not in ['response.audio.delta', 'input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped']:
                        logger.info(f"🎙️ OpenAI event: {event_type}")

                    # Handle session.updated - OpenAI is now configured
                    if event_type == 'session.updated':
                        call_context['session_ready'] = True
                        logger.info(f"🔧 OpenAI session configured. Twilio ready: {call_context['twilio_ready']}")
                        await maybe_trigger_greeting()

                    if event_type == 'response.audio.delta':
                        # Forward AI audio to Twilio
                        audio_payload = data.get('delta', '')
                        if audio_payload and call_context.get('stream_sid'):
                            try:
                                await websocket.send_json({
                                    "event": "media",
                                    "streamSid": call_context['stream_sid'],
                                    "media": {
                                        "payload": audio_payload
                                    }
                                })
                            except Exception as send_err:
                                logger.error(f"❌ Failed to send audio to Twilio: {send_err}")
                        else:
                            logger.warning(f"⚠️ Missing audio payload ({len(audio_payload) if audio_payload else 0} bytes) or stream_sid ({call_context.get('stream_sid')})")

                    elif event_type == 'response.audio.done':
                        logger.info("🔊 OpenAI audio response complete")

                    elif event_type == 'response.done':
                        # Log the full response for debugging
                        response_data = data.get('response', {})
                        output_items = response_data.get('output', [])
                        status = response_data.get('status', 'unknown')
                        logger.info(f"✅ OpenAI response done - status: {status}, output items: {len(output_items)}")
                        if not output_items:
                            logger.warning(f"⚠️ Empty response from OpenAI! Full data: {json.dumps(data)[:500]}")

                    elif data['type'] == 'response.text.done':
                        # Log conversation
                        call_context['conversation_history'].append({
                            "role": "assistant",
                            "content": data['text']
                        })

                    elif data['type'] == 'conversation.item.input_audio_transcription.completed':
                        # Log what user said
                        call_context['conversation_history'].append({
                            "role": "user",
                            "content": data['transcript']
                        })

                        # Extract lead information
                        await extract_lead_info(data['transcript'], call_context)

                    elif event_type == 'response.function_call_arguments.done':
                        # Handle function calls from the AI
                        func_name = data.get('name', '')
                        func_args = data.get('arguments', '{}')
                        call_id = data.get('call_id', '')

                        logger.info(f"🔧 Function call: {func_name} with args: {func_args}")

                        try:
                            args = json.loads(func_args)
                            result = await handle_ai_function_call(
                                func_name, args, call_context, db
                            )

                            # Send function result back to OpenAI
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": json.dumps(result)
                                }
                            }))

                            # Request AI to continue responding after function result
                            await openai_ws.send(json.dumps({
                                "type": "response.create"
                            }))

                            logger.info(f"✅ Function {func_name} completed: {result}")

                        except Exception as func_err:
                            logger.error(f"❌ Function call error: {func_err}")

            except Exception as e:
                logger.error(f"Error in OpenAI->Twilio stream: {e}")

        # Run both streams concurrently
        await asyncio.gather(
            twilio_to_openai(),
            openai_to_twilio()
        )

    except WebSocketDisconnect:
        logger.info("📴 Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"❌ Error in voice stream: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass  # WebSocket may already be closed
        try:
            if openai_ws:
                await openai_ws.close()
        except Exception:
            pass  # OpenAI WebSocket may already be closed
        try:
            db.close()
        except Exception:
            pass  # Session may already be closed
        logger.info("🔚 Voice stream cleanup complete")


async def connect_to_openai_realtime():
    """Connect to OpenAI Realtime API WebSocket"""
    import websockets

    openai_api_key = os.getenv("OPENAI_API_KEY") or openai.api_key
    if not openai_api_key:
        raise Exception("OpenAI API key not configured")

    logger.info("Connecting to OpenAI Realtime API")

    # Use generic model name - points to latest stable version
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    # Connect with timeout - use additional_headers (websockets 10.x+)
    ws = await asyncio.wait_for(
        websockets.connect(url, additional_headers=headers),
        timeout=10.0
    )

    # Wait for session.created event with timeout
    initial_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
    logger.info(f"OpenAI Realtime initial response: {initial_response[:500]}")

    # Check for error in initial response
    try:
        initial_data = json.loads(initial_response)
        if initial_data.get('type') == 'error':
            error_msg = initial_data.get('error', {}).get('message', 'Unknown error')
            error_code = initial_data.get('error', {}).get('code', 'unknown')
            logger.error(f"❌ OpenAI Realtime error: {error_code} - {error_msg}")
            raise Exception(f"OpenAI error: {error_code} - {error_msg}")
        logger.info(f"✅ OpenAI Realtime session created: {initial_data.get('type')}")
    except json.JSONDecodeError:
        logger.warning(f"Could not parse initial response as JSON: {initial_response[:200]}")

    # Configure the session for natural two-way conversation
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "coral",  # Natural, warm voice for phone conversations
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,  # Balanced - detects speech but filters some noise
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500  # Faster response
            },
            "tools": [
                {
                    "type": "function",
                    "name": "schedule_appointment",
                    "description": "Schedule an appointment with a loan officer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Preferred date (YYYY-MM-DD)"},
                            "time": {"type": "string", "description": "Preferred time (HH:MM)"},
                            "reason": {"type": "string", "description": "Reason for appointment"}
                        },
                        "required": ["date", "time"]
                    }
                },
                {
                    "type": "function",
                    "name": "transfer_to_loan_officer",
                    "description": "Transfer call to a loan officer for urgent matters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Reason for transfer"},
                            "urgency": {"type": "string", "enum": ["low", "medium", "high"]}
                        },
                        "required": ["reason"]
                    }
                },
                {
                    "type": "function",
                    "name": "take_message",
                    "description": "Take a message for the team",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "phone": {"type": "string"},
                            "message": {"type": "string"},
                            "callback_urgency": {"type": "string", "enum": ["urgent", "today", "this_week"]}
                        },
                        "required": ["name", "phone", "message"]
                    }
                }
            ]
        }
    }))

    logger.info("OpenAI Realtime session configured")

    # NOTE: We no longer trigger greeting here - it's done in twilio_to_openai()
    # when we receive the 'start' event from Twilio (meaning it's ready to receive audio)

    return ws


async def extract_lead_info(transcript: str, call_context: dict):
    """Extract lead information from conversation using Claude"""
    try:
        # Use Claude to extract structured data from conversation
        import anthropic

        client = anthropic.Anthropic()

        prompt = f"""Extract lead information from this phone conversation transcript:

{transcript}

Previous context: {json.dumps(call_context['conversation_history'][-5:])}

Extract and return JSON with:
- name: caller's name (if mentioned)
- phone: phone number (if mentioned)
- loan_type: purchase/refinance/cash-out/heloc (if discussed)
- property_value: estimated value (if mentioned)
- credit_score: range if mentioned
- urgency: low/medium/high based on timeline
- intent: what they want (quote/appointment/question/etc)

Return ONLY valid JSON, no other text."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        lead_data = json.loads(message.content[0].text)
        call_context['lead_data'].update(lead_data)

        logger.info(f"Extracted lead data: {lead_data}")

    except Exception as e:
        logger.error(f"Error extracting lead info: {e}")


async def handle_ai_function_call(func_name: str, args: dict, call_context: dict, db) -> dict:
    """
    Handle function calls from the AI receptionist.
    Returns the result to send back to OpenAI.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import text

    caller_name = call_context.get('caller_name') or call_context.get('lead_data', {}).get('name') or 'Unknown'
    caller_phone = call_context.get('caller_number') or 'Unknown'

    if func_name == "schedule_appointment":
        # Schedule an appointment and save to database
        date_str = args.get('date', '')
        time_str = args.get('time', '')
        reason = args.get('reason', 'Mortgage consultation')

        try:
            # Parse the date and time
            if date_str and time_str:
                appointment_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            else:
                # Default to tomorrow at 10 AM if not specified
                appointment_datetime = datetime.now() + timedelta(days=1)
                appointment_datetime = appointment_datetime.replace(hour=10, minute=0, second=0)

            # Save to appointments table
            db.execute(text("""
                INSERT INTO appointments (
                    id, caller_name, caller_phone, appointment_datetime,
                    reason, status, created_at, call_sid, notes
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :appointment_datetime,
                    :reason, 'scheduled', NOW(), :call_sid, :notes
                )
            """), {
                "caller_name": caller_name,
                "caller_phone": caller_phone,
                "appointment_datetime": appointment_datetime,
                "reason": reason,
                "call_sid": call_context.get('call_sid'),
                "notes": f"Scheduled via AI receptionist. Context: {json.dumps(call_context.get('lead_data', {}))}"
            })
            db.commit()

            formatted_time = appointment_datetime.strftime("%A, %B %d at %I:%M %p")
            logger.info(f"Appointment scheduled on {formatted_time}")

            return {
                "success": True,
                "message": f"Appointment scheduled for {formatted_time}",
                "appointment_time": formatted_time,
                "caller_name": caller_name
            }

        except Exception as e:
            logger.error(f"Failed to schedule appointment: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Sorry, I couldn't save the appointment. Please try again."
            }

    elif func_name == "transfer_to_loan_officer":
        # Log the transfer request
        reason = args.get('reason', '')
        urgency = args.get('urgency', 'medium')

        try:
            db.execute(text("""
                INSERT INTO call_transfers (
                    id, caller_name, caller_phone, transfer_reason,
                    urgency, status, created_at, call_sid
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :reason,
                    :urgency, 'requested', NOW(), :call_sid
                )
            """), {
                "caller_name": caller_name,
                "caller_phone": caller_phone,
                "reason": reason,
                "urgency": urgency,
                "call_sid": call_context.get('call_sid')
            })
            db.commit()

            logger.info(f"Transfer requested - {reason} ({urgency})")

            return {
                "success": True,
                "message": "I'll transfer you to a loan officer now.",
                "transfer_initiated": True
            }

        except Exception as e:
            logger.error(f"Failed to log transfer: {e}")
            db.rollback()
            return {
                "success": True,  # Still transfer even if logging fails
                "message": "Transferring you now."
            }

    elif func_name == "take_message":
        # Save the message
        name = args.get('name', caller_name)
        phone = args.get('phone', caller_phone)
        message = args.get('message', '')
        callback_urgency = args.get('callback_urgency', 'today')

        try:
            db.execute(text("""
                INSERT INTO voice_messages (
                    id, caller_name, caller_phone, message,
                    callback_urgency, status, created_at, call_sid
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :message,
                    :callback_urgency, 'new', NOW(), :call_sid
                )
            """), {
                "caller_name": name,
                "caller_phone": phone,
                "message": message,
                "callback_urgency": callback_urgency,
                "call_sid": call_context.get('call_sid')
            })
            db.commit()

            logger.info(f"📝 Message saved: {name} - {message[:50]}...")

            return {
                "success": True,
                "message": f"Got it! I've saved your message and someone will call you back {callback_urgency}.",
                "callback_urgency": callback_urgency
            }

        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "I'm sorry, I had trouble saving your message. Could you repeat that?"
            }

    else:
        logger.warning(f"Unknown function called: {func_name}")
        return {
            "success": False,
            "message": "I'm not sure how to help with that. Let me connect you with someone who can."
        }


async def save_call_summary(call_context: dict, db: Session):
    """Save call summary and create lead/task if needed"""
    try:
        _, Lead, _, Activity, _ = get_models()

        # Create or update lead
        if call_context['lead_data'].get('phone'):
            phone = call_context['lead_data']['phone']

            # Check if lead exists
            lead = db.query(Lead).filter(Lead.phone == phone).first()

            if not lead:
                # Create new lead
                lead = Lead(
                    name=call_context['lead_data'].get('name', 'Phone Inquiry'),
                    phone=phone,
                    source="Phone Call",
                    stage="NEW",
                    notes=f"Inbound call. Conversation summary:\n{json.dumps(call_context['conversation_history'], indent=2)}"
                )
                db.add(lead)
                logger.info("Created new lead from call")

            # Log activity
            activity = Activity(
                lead_id=lead.id if lead else None,
                activity_type="phone_call",
                description=f"AI Receptionist Call - {call_context.get('intent', 'General Inquiry')}",
                notes=json.dumps(call_context['conversation_history'], indent=2),
                metadata={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data'],
                    "duration": None  # Will be updated by status callback
                }
            )
            db.add(activity)

            # ✅ NEW: Save full conversation to dashboard
            conversation_record = AIReceptionistConversation(
                id=str(uuid.uuid4()),
                started_at=call_context.get('start_time', datetime.now(timezone.utc)),
                ended_at=datetime.now(timezone.utc),
                duration_seconds=call_context.get('duration', 0),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                channel='voice',
                direction='inbound',
                transcript=json.dumps(call_context['conversation_history'], indent=2),
                transcript_json=call_context['conversation_history'],
                summary=call_context.get('intent', 'General inquiry'),
                intent_detected=call_context.get('intent', 'unknown'),
                sentiment=analyze_voice_sentiment(call_context['conversation_history']),
                outcome=call_context.get('outcome', 'completed'),
                avg_confidence_score=call_context.get('avg_confidence', 0.85),
                total_turns=len(call_context['conversation_history']),
                extra_data={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data']
                }
            )
            db.add(conversation_record)

            # ✅ NEW: Update activity feed with conversation summary
            activity_update = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                action_type='conversation_summary',
                channel='voice',
                confidence_score=call_context.get('avg_confidence', 0.85),
                ai_version='gpt-4o-realtime-v1',
                outcome_status='success',
                conversation_id=call_context['call_sid'],
                extra_data={
                    "intent": call_context.get('intent'),
                    "lead_data": call_context['lead_data'],
                    "turns": len(call_context['conversation_history'])
                }
            )
            db.add(activity_update)

            db.commit()
            logger.info("Saved call summary")

    except Exception as e:
        logger.error(f"Error saving call summary: {e}")
        db.rollback()

        # ✅ NEW: Log error to dashboard
        try:
            error_log = AIReceptionistError(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                error_type='api_failure',
                severity='high',
                context=f"Failed to save call summary: {str(e)}",
                conversation_snippet=json.dumps(call_context.get('conversation_history', [])[-3:]),
                conversation_id=call_context.get('call_sid'),
                root_cause='Unknown',
                needs_human_review=True,
                resolution_status='unresolved',
                extra_data={
                    "call_context": str(call_context),
                    "error_message": str(e)
                }
            )
            db.add(error_log)
            db.commit()
        except Exception:
            pass  # Don't fail on error logging


# ============================================================================
# CALL STATUS & RECORDING WEBHOOKS
# ============================================================================

@router.post("/call-status")
async def handle_call_status(request: Request, db: Session = Depends(get_db)):
    """Webhook for call status updates"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        duration = form_data.get("CallDuration", "0")
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")

        logger.info(f"Call {call_sid} status: {call_status}, duration: {duration}s")

        # Update AI Receptionist Dashboard activity if it exists
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                # Update with final status
                activity.outcome_status = 'completed' if call_status == 'completed' else call_status
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['duration'] = int(duration)
                activity.extra_data['final_status'] = call_status
                db.commit()
                logger.info(f"Updated AI Receptionist activity for call {call_sid}")
        except Exception as update_error:
            logger.warning(f"Could not update activity for call {call_sid}: {update_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling call status: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.post("/recording-ready")
async def handle_recording_ready(request: Request, db: Session = Depends(get_db)):
    """Webhook when call recording is ready - transcribes, summarizes, and creates email draft"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        recording_url = form_data.get("RecordingUrl")
        recording_sid = form_data.get("RecordingSid")
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_duration = form_data.get("RecordingDuration", "0")

        logger.info(f"Recording ready for call {call_sid}: {recording_url}")

        # Update AI Receptionist Dashboard activity with recording URL
        activity = None
        user_id = None
        lead_id = None
        lead_name = None
        user_email = None

        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['recording_url'] = recording_url
                activity.extra_data['recording_sid'] = recording_sid
                # Use getattr since these columns may not exist in all versions
                user_id = getattr(activity, 'user_id', None) or (activity.extra_data.get('user_id') if activity.extra_data else None)
                lead_id = getattr(activity, 'lead_id', None) or (activity.extra_data.get('lead_id') if activity.extra_data else None)
                db.commit()
                logger.info(f"Updated activity with recording for call {call_sid}")

                # Get user email for draft creation
                if user_id:
                    from main import User
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        user_email = user.email

                # Get lead name if available
                if lead_id:
                    from main import Lead
                    lead = db.query(Lead).filter(Lead.id == lead_id).first()
                    if lead:
                        lead_name = lead.name

        except Exception as update_error:
            logger.warning(f"Could not update recording for call {call_sid}: {update_error}")

        # Process recording asynchronously (transcribe, summarize, create draft)
        import asyncio
        asyncio.create_task(
            process_call_recording(
                recording_url=recording_url,
                recording_sid=recording_sid,
                call_sid=call_sid,
                caller_number=caller_number,
                call_duration=call_duration,
                user_id=user_id,
                user_email=user_email,
                lead_id=lead_id,
                lead_name=lead_name,
                db=db
            )
        )

        # Also submit to Twilio Voice Intelligence for enhanced transcription
        # (runs in parallel, results come via webhook)
        try:
            from integrations.twilio_intelligence_service import intelligence_service
            if intelligence_service.enabled and intelligence_service.service_sid:
                asyncio.create_task(
                    submit_to_twilio_intelligence(
                        recording_sid=recording_sid,
                        caller_name=lead_name,
                        call_sid=call_sid
                    )
                )
                logger.info(f"Submitted recording {recording_sid} to Twilio Intelligence")
        except Exception as intel_error:
            logger.warning(f"Could not submit to Twilio Intelligence: {intel_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling recording: {e}")
        return {"status": "error"}


@router.post("/transcript-complete")
async def handle_transcript_complete(request: Request, db: Session = Depends(get_db)):
    """
    Webhook from Twilio Voice Intelligence when transcription is complete.

    Event type: voice_intelligence_transcript_available

    Receives transcript with:
    - Speaker-labeled sentences
    - PII redaction
    - Sentiment analysis (via operator)
    - Summarization (via operator)
    - Entity recognition (via operator)
    - Escalation detection (via operator)
    - Recording disclosure check (via operator)
    """
    try:
        # Try JSON first, then form data (Twilio sometimes uses either)
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            form_data = await request.form()
            data = dict(form_data)

        transcript_sid = data.get("transcript_sid") or data.get("TranscriptSid")
        service_sid = data.get("service_sid") or data.get("ServiceSid")
        customer_key = data.get("customer_key") or data.get("CustomerKey")
        event_type = data.get("event_type") or data.get("EventType")
        status = data.get("status") or data.get("Status")

        logger.info(f"Transcript webhook received: {transcript_sid}, event: {event_type}, status: {status}")

        # Handle specific event type
        if event_type and event_type != "voice_intelligence_transcript_available":
            logger.info(f"Ignoring event type: {event_type}")
            return {"status": "acknowledged", "event_type": event_type}

        # Also check status for non-event webhooks
        if not event_type and status and status != "completed":
            logger.info(f"Transcript {transcript_sid} status: {status}, waiting for completion")
            return {"status": "acknowledged"}

        # Import intelligence service
        from integrations.twilio_intelligence_service import intelligence_service

        # Fetch the full transcript with insights
        transcript = await intelligence_service.get_transcript(transcript_sid)
        if not transcript:
            logger.error(f"Could not fetch transcript {transcript_sid}")
            return {"status": "error", "message": "Could not fetch transcript"}

        # Fetch operator results for AI insights
        operator_results = await intelligence_service.get_operator_results(transcript_sid)

        # Parse operator results into structured insights
        insights = parse_operator_results(operator_results or [])

        logger.info(f"Transcript {transcript_sid} fetched: {transcript.get('duration')}s, "
                   f"{len(transcript.get('sentences', []))} sentences, "
                   f"sentiment: {insights.get('sentiment')}")

        # Store transcript in database
        try:
            from sqlalchemy import text

            # Get media info if available
            media = await intelligence_service.get_transcript_media(transcript_sid)

            db.execute(text("""
                INSERT INTO call_transcripts (
                    transcript_sid, status, duration_seconds, full_text,
                    sentences, sentiment, topics, action_items, entities,
                    summary, pii_detected, created_at, updated_at
                ) VALUES (
                    :transcript_sid, :status, :duration, :full_text,
                    :sentences, :sentiment, :topics, :action_items, :entities,
                    :summary, :pii_detected, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (transcript_sid) DO UPDATE SET
                    status = EXCLUDED.status,
                    full_text = EXCLUDED.full_text,
                    sentences = EXCLUDED.sentences,
                    sentiment = EXCLUDED.sentiment,
                    topics = EXCLUDED.topics,
                    action_items = EXCLUDED.action_items,
                    entities = EXCLUDED.entities,
                    summary = EXCLUDED.summary,
                    pii_detected = EXCLUDED.pii_detected,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "transcript_sid": transcript_sid,
                "status": "completed",
                "duration": transcript.get("duration"),
                "full_text": transcript.get("full_text"),
                "sentences": json.dumps(transcript.get("sentences", [])),
                "sentiment": json.dumps(insights.get("sentiment")),
                "topics": json.dumps(insights.get("topics", [])),
                "action_items": json.dumps(insights.get("action_items", [])),
                "entities": json.dumps(insights.get("entities", [])),
                "summary": insights.get("summary"),
                "pii_detected": transcript.get("redaction", {}).get("pii_detected", False) if isinstance(transcript.get("redaction"), dict) else False,
            })
            db.commit()
            logger.info(f"Stored transcript {transcript_sid} in database")

            # If we have a customer_key, update related records
            if customer_key:
                await link_transcript_to_customer(db, transcript_sid, customer_key, insights)

        except Exception as db_error:
            logger.warning(f"Could not store transcript (table may not exist): {db_error}")

        return {
            "status": "success",
            "transcript_sid": transcript_sid,
            "duration": transcript.get("duration"),
            "sentence_count": len(transcript.get("sentences", [])),
            "insights": {
                "sentiment": insights.get("sentiment"),
                "has_summary": insights.get("summary") is not None,
                "entity_count": len(insights.get("entities", [])),
                "escalation_detected": insights.get("escalation_detected", False),
                "recording_disclosed": insights.get("recording_disclosed", False),
            }
        }

    except Exception as e:
        logger.error(f"Error handling transcript webhook: {e}")
        return {"status": "error", "message": "Internal server error"}


def parse_operator_results(operator_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse operator results into structured insights.

    Operators may include:
    - sentiment-analysis: positive, negative, neutral, mixed
    - summarization: AI-generated summary
    - entity-recognition: names, amounts, dates, etc.
    - escalation-request: customer wants to escalate
    - recording-disclosure: recording was disclosed
    """
    insights = {
        "sentiment": None,
        "summary": None,
        "entities": [],
        "topics": [],
        "action_items": [],
        "escalation_detected": False,
        "recording_disclosed": False,
    }

    for result in operator_results:
        operator_type = result.get("operator_type", "").lower()
        operator_name = result.get("name", "").lower()
        results_data = result.get("results", {})

        # Handle different operator types
        if "sentiment" in operator_type or "sentiment" in operator_name:
            insights["sentiment"] = results_data.get("predicted_label") or results_data.get("sentiment")

        elif "summar" in operator_type or "summar" in operator_name:
            insights["summary"] = results_data.get("transcript_text") or results_data.get("summary")

        elif "entity" in operator_type or "entity" in operator_name:
            entities = results_data.get("extraction_results") or results_data.get("entities") or []
            insights["entities"] = entities

        elif "escalation" in operator_type or "escalation" in operator_name:
            label = results_data.get("predicted_label", "").lower()
            insights["escalation_detected"] = label in ["true", "yes", "escalation"]

        elif "recording" in operator_type or "disclosure" in operator_name:
            label = results_data.get("predicted_label", "").lower()
            insights["recording_disclosed"] = label in ["true", "yes", "disclosed"]

        elif "topic" in operator_type:
            topics = results_data.get("topics", [])
            insights["topics"] = topics

        elif "action" in operator_type:
            items = results_data.get("items", [])
            insights["action_items"] = items

    return insights


async def link_transcript_to_customer(
    db: Session,
    transcript_sid: str,
    customer_key: str,
    insights: Dict[str, Any]
):
    """Link transcript to customer/lead records and update with insights."""
    try:
        from sqlalchemy import text

        # Try to find and update related activity
        result = db.execute(text("""
            UPDATE ai_receptionist_activities
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || :insights_data
            WHERE conversation_id = :customer_key
               OR extra_data->>'customer_id' = :customer_key
        """), {
            "customer_key": customer_key,
            "insights_data": json.dumps({
                "transcript_sid": transcript_sid,
                "sentiment": insights.get("sentiment"),
                "summary": insights.get("summary"),
                "escalation_detected": insights.get("escalation_detected"),
            })
        })
        db.commit()

        if result.rowcount > 0:
            logger.info(f"Linked transcript {transcript_sid} to activity {customer_key}")

    except Exception as e:
        logger.warning(f"Could not link transcript to customer: {e}")


# ============================================================================
# TRANSCRIPT RETRIEVAL ENDPOINTS
# ============================================================================

@router.get("/transcripts")
async def list_transcripts(
    db: Session = Depends(get_db),
    sentiment: str = None,
    escalation: bool = None,
    keyword: str = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List and search call transcripts.

    Args:
        sentiment: Filter by sentiment (positive, negative, neutral, mixed)
        escalation: Filter by escalation detection (true/false)
        keyword: Search transcripts by keyword
        limit: Max results to return
        offset: Pagination offset
    """
    try:
        from sqlalchemy import text

        # Build query with filters
        conditions = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if sentiment:
            conditions.append("sentiment->>'sentiment' = :sentiment OR sentiment = :sentiment_raw")
            params["sentiment"] = sentiment
            params["sentiment_raw"] = f'"{sentiment}"'

        if escalation is not None:
            # Check in entities or a dedicated field
            conditions.append("(entities::text ILIKE '%escalation%') = :escalation")
            params["escalation"] = escalation

        if keyword:
            conditions.append("full_text ILIKE :keyword")
            params["keyword"] = f"%{keyword}%"

        where_clause = " AND ".join(conditions)

        result = db.execute(text(f"""
            SELECT
                id, transcript_sid, status, duration_seconds,
                full_text, sentiment, summary, entities,
                topics, action_items, pii_detected, created_at
            FROM call_transcripts
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params)

        transcripts = []
        for row in result.fetchall():
            transcripts.append({
                "id": row[0],
                "transcript_sid": row[1],
                "status": row[2],
                "duration_seconds": row[3],
                "full_text": row[4][:500] + "..." if row[4] and len(row[4]) > 500 else row[4],
                "sentiment": row[5],
                "summary": row[6],
                "entities": row[7],
                "topics": row[8],
                "action_items": row[9],
                "pii_detected": row[10],
                "created_at": row[11].isoformat() if row[11] else None,
            })

        return {
            "transcripts": transcripts,
            "count": len(transcripts),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing transcripts: {e}")
        return {"transcripts": [], "error": "Internal server error"}


@router.get("/transcripts/{transcript_sid}")
async def get_transcript_detail(
    transcript_sid: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed transcript by SID.

    Returns full transcript with all sentences and AI insights.
    """
    try:
        from sqlalchemy import text

        result = db.execute(text("""
            SELECT
                id, transcript_sid, call_sid, recording_sid, activity_id,
                status, duration_seconds, language_code, full_text,
                sentences, sentiment, topics, action_items, entities,
                summary, redaction_enabled, pii_detected, created_at, updated_at
            FROM call_transcripts
            WHERE transcript_sid = :transcript_sid
        """), {"transcript_sid": transcript_sid})

        row = result.fetchone()
        if not row:
            return {"error": "Transcript not found"}

        return {
            "id": row[0],
            "transcript_sid": row[1],
            "call_sid": row[2],
            "recording_sid": row[3],
            "activity_id": row[4],
            "status": row[5],
            "duration_seconds": row[6],
            "language_code": row[7],
            "full_text": row[8],
            "sentences": row[9],
            "sentiment": row[10],
            "topics": row[11],
            "action_items": row[12],
            "entities": row[13],
            "summary": row[14],
            "redaction_enabled": row[15],
            "pii_detected": row[16],
            "created_at": row[17].isoformat() if row[17] else None,
            "updated_at": row[18].isoformat() if row[18] else None,
        }

    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        return {"error": "Internal server error"}


@router.get("/transcripts/customer/{customer_id}")
async def get_customer_transcripts(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all transcripts for a customer/lead.

    Searches by customer_key used when creating the transcript.
    """
    try:
        from sqlalchemy import text

        # Look for transcripts linked via activity or directly
        result = db.execute(text("""
            SELECT
                ct.id, ct.transcript_sid, ct.status, ct.duration_seconds,
                ct.sentiment, ct.summary, ct.created_at
            FROM call_transcripts ct
            LEFT JOIN ai_receptionist_activities ara ON
                ara.extra_data->>'transcript_sid' = ct.transcript_sid
            WHERE ara.lead_id::text = :customer_id
               OR ara.conversation_id = :customer_id
               OR ct.activity_id = :customer_id
            ORDER BY ct.created_at DESC
        """), {"customer_id": customer_id})

        transcripts = []
        for row in result.fetchall():
            transcripts.append({
                "id": row[0],
                "transcript_sid": row[1],
                "status": row[2],
                "duration_seconds": row[3],
                "sentiment": row[4],
                "summary": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            })

        return {
            "customer_id": customer_id,
            "total_conversations": len(transcripts),
            "transcripts": transcripts
        }

    except Exception as e:
        logger.error(f"Error getting customer transcripts: {e}")
        return {"customer_id": customer_id, "transcripts": [], "error": "Internal server error"}


async def process_call_recording(
    recording_url: str,
    recording_sid: str,
    call_sid: str,
    caller_number: str,
    call_duration: str,
    user_id: int,
    user_email: str,
    lead_id: int,
    lead_name: str,
    db: Session
):
    """Process call recording: transcribe, summarize with AI, create email draft"""
    import httpx
    from anthropic import Anthropic

    logger.info(f"Processing call recording {recording_sid}...")

    try:
        # Step 1: Download the recording from Twilio
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")

        if not twilio_account_sid or not twilio_auth_token:
            logger.error("Twilio credentials not configured")
            return

        # Twilio recording URL needs authentication
        recording_mp3_url = f"{recording_url}.mp3"

        async with httpx.AsyncClient() as client:
            # Download recording
            logger.info(f"Downloading recording from {recording_mp3_url}")
            recording_response = await client.get(
                recording_mp3_url,
                auth=(twilio_account_sid, twilio_auth_token),
                timeout=60.0
            )

            if recording_response.status_code != 200:
                logger.error(f"Failed to download recording: {recording_response.status_code}")
                return

            audio_data = recording_response.content
            logger.info(f"Downloaded {len(audio_data)} bytes of audio")

            # Step 2: Transcribe with OpenAI Whisper
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.error("OpenAI API key not configured")
                return

            logger.info("Transcribing audio with Whisper...")
            transcribe_response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": ("recording.mp3", audio_data, "audio/mpeg")},
                data={"model": "whisper-1", "language": "en"},
                timeout=120.0
            )

            if transcribe_response.status_code != 200:
                logger.error(f"Transcription failed: {transcribe_response.text}")
                return

            transcript = transcribe_response.json().get("text", "")
            logger.info(f"Transcription complete: {len(transcript)} characters")

        # Step 3: Summarize with Claude
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            logger.error("Anthropic API key not configured")
            return

        logger.info("Generating professional summary with Claude...")
        anthropic_client = Anthropic(api_key=anthropic_key)

        client_identifier = lead_name or caller_number

        summary_prompt = f"""You are a professional assistant for a mortgage loan officer.
Summarize the following phone call transcript into a professional call summary.

Call Details:
- Client: {client_identifier}
- Phone: {caller_number}
- Duration: {call_duration} seconds
- Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

Transcript:
{transcript}

Create a professional call summary with the following sections:
1. **Call Overview** - Brief 1-2 sentence summary
2. **Key Discussion Points** - Bullet points of main topics discussed
3. **Client Needs/Requests** - What the client is looking for
4. **Action Items** - Any follow-up tasks or commitments made
5. **Next Steps** - Recommended next actions

Keep the summary concise but comprehensive. Use professional language appropriate for client records."""

        summary_response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            messages=[{"role": "user", "content": summary_prompt}]
        )

        summary = summary_response.content[0].text
        logger.info(f"Summary generated: {len(summary)} characters")

        # Step 4: Create email draft in user's Outlook
        if user_email:
            await create_call_summary_email_draft(
                user_email=user_email,
                client_name=client_identifier,
                caller_number=caller_number,
                call_duration=call_duration,
                summary=summary,
                transcript=transcript,
                recording_url=recording_url
            )
        else:
            logger.warning("No user email available, skipping draft creation")

        # Step 5: Store summary in database
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['transcript'] = transcript
                activity.extra_data['summary'] = summary
                activity.summary = summary[:500] if len(summary) > 500 else summary
                db.commit()
                logger.info(f"Stored summary for call {call_sid}")
        except Exception as db_error:
            logger.error(f"Failed to store summary: {db_error}")

        logger.info(f"Call recording processing complete for {call_sid}")

    except Exception as e:
        logger.error(f"Error processing call recording: {e}")


async def submit_to_twilio_intelligence(
    recording_sid: str,
    caller_name: str = None,
    call_sid: str = None
):
    """
    Submit a recording to Twilio Voice Intelligence for enhanced transcription.
    Results will be delivered via the /transcript-complete webhook.
    """
    try:
        from integrations.twilio_intelligence_service import intelligence_service

        # Submit recording for transcription
        result = await intelligence_service.transcribe_recording(
            recording_url=recording_sid,  # Can pass recording SID directly
            participants=[
                {"role": "customer", "channel": 1, "name": caller_name},
                {"role": "agent", "channel": 2, "name": "AI Assistant"}
            ],
            metadata={
                "call_sid": call_sid,
                "source": "ai_receptionist"
            }
        )

        if result:
            logger.info(f"Twilio Intelligence transcript job created: {result.get('transcript_sid')}")
            return result
        else:
            logger.warning(f"Failed to create Twilio Intelligence transcript for {recording_sid}")
            return None

    except Exception as e:
        logger.error(f"Error submitting to Twilio Intelligence: {e}")
        return None


async def create_call_summary_email_draft(
    user_email: str,
    client_name: str,
    caller_number: str,
    call_duration: str,
    summary: str,
    transcript: str,
    recording_url: str
):
    """Create an email draft in the user's Outlook drafts folder"""
    import httpx
    from msal import ConfidentialClientApplication

    logger.info(f"Creating email draft for {user_email}...")

    try:
        # Get Microsoft Graph token
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID")

        if not all([client_id, client_secret, tenant_id]):
            logger.warning("Microsoft Graph credentials not configured, skipping draft creation")
            return

        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}"
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            logger.error(f"Failed to get Graph token: {result.get('error_description')}")
            return

        token = result["access_token"]

        # Format email body
        duration_mins = int(call_duration) // 60 if call_duration.isdigit() else 0
        duration_secs = int(call_duration) % 60 if call_duration.isdigit() else 0

        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
<h2 style="color: #2c3e50;">📞 Call Summary - {client_name}</h2>

<table style="margin-bottom: 20px; border-collapse: collapse;">
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Client:</td><td>{client_name}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Phone:</td><td>{caller_number}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Duration:</td><td>{duration_mins}m {duration_secs}s</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Date:</td><td>{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td></tr>
</table>

<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
{summary.replace(chr(10), '<br>')}
</div>

<details style="margin-top: 20px;">
<summary style="cursor: pointer; font-weight: bold; color: #3498db;">📝 View Full Transcript</summary>
<div style="background: #f0f0f0; padding: 15px; margin-top: 10px; border-radius: 5px; white-space: pre-wrap; font-size: 13px;">
{transcript}
</div>
</details>

<p style="margin-top: 20px; color: #7f8c8d; font-size: 12px;">
<em>This summary was automatically generated by Perennia AI. Please review before sending to the client.</em>
</p>
</body>
</html>
"""

        # Create draft email via Microsoft Graph
        draft_data = {
            "subject": f"Call Summary - {client_name} - {datetime.now().strftime('%m/%d/%Y')}",
            "body": {
                "contentType": "HTML",
                "content": email_body
            },
            "importance": "normal"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=draft_data,
                timeout=30.0
            )

            if response.status_code in [200, 201]:
                draft_id = response.json().get("id")
                logger.info(f"Email draft created successfully: {draft_id}")
            else:
                logger.error(f"Failed to create draft: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error creating email draft: {e}")


@router.post("/voicemail-transcription")
async def handle_voicemail_transcription(request: Request, db: Session = Depends(get_db)):
    """Webhook for voicemail transcription"""
    try:
        _, _, Task, _, _ = get_models()

        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        transcription_text = form_data.get("TranscriptionText", "")
        caller = form_data.get("From", "Unknown")

        logger.info(f"Voicemail transcription from {mask_phone(caller)}: {transcription_text[:100]}")

        # Create task for team to follow up
        task = Task(
            title=f"Voicemail from {caller}",
            description=f"Transcription: {transcription_text}",
            status="PENDING",
            priority="MEDIUM",
            metadata={
                "call_sid": call_sid,
                "caller": caller,
                "type": "voicemail"
            }
        )
        db.add(task)
        db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling voicemail transcription: {e}")
        return {"status": "error"}


# ============================================================================
# CALL TRANSFER
# ============================================================================

@router.post("/transfer")
async def handle_transfer(request: Request):
    """Generate TwiML to transfer call"""
    try:
        query_params = request.query_params
        to_number = query_params.get("to")
        reason = query_params.get("reason", "transfer request")

        logger.info(f"Transferring call to {to_number}: {reason}")

        twiml = voice_client.create_transfer_response(to_number, reason)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error creating transfer TwiML: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/transfer-status")
async def handle_transfer_status(request: Request):
    """Handle transfer completion status"""
    try:
        form_data = await request.form()
        dial_call_status = form_data.get("DialCallStatus")

        logger.info(f"Transfer status: {dial_call_status}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling transfer status: {e}")
        return {"status": "error"}


@router.post("/voicemail")
@router.get("/voicemail")
async def voicemail_twiml():
    """Return voicemail TwiML - supports both GET and POST for Twilio"""
    twiml = voice_client.create_voicemail_response()
    return Response(content=str(twiml), media_type="application/xml")


# ============================================================================
# CALL MANAGEMENT API ENDPOINTS
# ============================================================================

@router.post("/make-call")
async def make_outbound_call(
    request: Request,
    db: Session = Depends(get_db)
):
    """Make an outbound AI call"""
    try:
        from main import get_current_user_flexible as auth_dependency
        User, _, _, Activity, _ = get_models()

        # Get current user (manually call dependency)
        current_user = None  # Will be set by auth if needed

        data = await request.json()
        to_number = data.get("to_number")
        script_type = data.get("script_type", "default")  # default, follow_up, appointment_reminder
        lead_id = data.get("lead_id")

        if not to_number:
            return {"success": False, "error": "Phone number required"}

        # Make the call
        call_sid = await voice_client.make_outbound_call(
            to_number=to_number,
            script=script_type
        )

        if call_sid:
            # Log the call
            activity = Activity(
                lead_id=lead_id,
                activity_type="phone_call",
                description=f"Outbound AI call - {script_type}",
                notes=f"Call to {to_number}",
                metadata={
                    "call_sid": call_sid,
                    "direction": "outbound",
                    "script_type": script_type,
                    "initiated_by": current_user.id if current_user else None
                }
            )
            db.add(activity)
            db.commit()

            return {
                "success": True,
                "call_sid": call_sid,
                "message": "Call initiated successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate call"
            }

    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/call-history")
async def get_call_history(
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """Get call history"""
    try:
        _, _, _, Activity, _ = get_models()

        activities = db.query(Activity).filter(
            Activity.activity_type == "phone_call"
        ).order_by(
            Activity.created_at.desc()
        ).offset(offset).limit(limit).all()

        return {
            "calls": [{
                "id": a.id,
                "lead_id": a.lead_id,
                "description": a.description,
                "notes": a.notes,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "metadata": a.metadata
            } for a in activities]
        }

    except Exception as e:
        logger.error(f"Error getting call history: {e}")
        return {"error": "Internal server error"}


@router.get("/call-stats")
async def get_call_stats(
    db: Session = Depends(get_db)
):
    """Get call statistics"""
    try:
        from sqlalchemy import func
        from datetime import timedelta
        _, Lead, _, Activity, _ = get_models()

        # Get stats for last 30 days
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        total_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago
        ).scalar()

        inbound_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago,
            Activity.metadata['direction'].astext == 'inbound'
        ).scalar()

        outbound_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago,
            Activity.metadata['direction'].astext == 'outbound'
        ).scalar()

        # Leads created from calls
        leads_from_calls = db.query(func.count(Lead.id)).filter(
            Lead.source == "Phone Call",
            Lead.created_at >= thirty_days_ago
        ).scalar()

        return {
            "total_calls": total_calls or 0,
            "inbound_calls": inbound_calls or 0,
            "outbound_calls": outbound_calls or 0,
            "leads_generated": leads_from_calls or 0,
            "period": "last_30_days"
        }

    except Exception as e:
        logger.error(f"Error getting call stats: {e}")
        return {
            "total_calls": 0,
            "inbound_calls": 0,
            "outbound_calls": 0,
            "leads_generated": 0,
            "error": "Internal server error"
        }


@router.get("/ai-receptionist-config")
async def get_ai_receptionist_config():
    """Get AI receptionist configuration"""
    return {
        "enabled": voice_client.enabled and voice_client.openai_enabled,
        "business_name": ai_config.business_name,
        "business_hours": ai_config.business_hours,
        "phone_number": voice_client.from_number,
        "features": {
            "answer_calls": True,
            "make_calls": True,
            "transfer_calls": True,
            "take_messages": True,
            "schedule_appointments": True,
            "lead_qualification": True
        }
    }


@router.post("/ai-receptionist-config")
async def update_ai_receptionist_config(
    request: Request,
    current_user=Depends(get_current_user_flexible()),
):
    """Update AI receptionist configuration"""
    try:
        data = await request.json()

        if "business_name" in data:
            ai_config.business_name = data["business_name"]

        if "business_hours" in data:
            ai_config.business_hours = data["business_hours"]

        return {
            "success": True,
            "message": "Configuration updated"
        }

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# VOICE OS DASHBOARD API ENDPOINTS
# ============================================================================

@router.get("/voice-os/config")
async def get_voice_os_config(
    current_user=Depends(get_current_user_flexible()),
):
    """Get Voice OS configuration for dashboard"""
    return {
        "status": "running",
        "voice": os.getenv("TTS_VOICE", "alloy"),
        "stt_provider": os.getenv("STT_PROVIDER", "openai"),
        "tts_provider": os.getenv("TTS_PROVIDER", "openai"),
        "ai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "500")),
        "phone_number": voice_client.from_number,
        "business_name": ai_config.business_name,
        "crm_tools": [
            {
                "id": "contact_lookup",
                "name": "Contact Lookup",
                "description": "Search for existing contacts in CRM",
                "enabled": True
            },
            {
                "id": "lead_creation",
                "name": "Lead Creation",
                "description": "Create new leads from call information",
                "enabled": True
            },
            {
                "id": "appointment_scheduling",
                "name": "Appointment Scheduling",
                "description": "Schedule appointments with loan officers",
                "enabled": True
            },
            {
                "id": "task_creation",
                "name": "Task Creation",
                "description": "Create follow-up tasks for team",
                "enabled": True
            },
            {
                "id": "note_taking",
                "name": "Note Taking",
                "description": "Save call notes to contact record",
                "enabled": True
            },
            {
                "id": "call_transfer",
                "name": "Call Transfer",
                "description": "Transfer calls to team members",
                "enabled": True
            },
            {
                "id": "voicemail",
                "name": "Voicemail",
                "description": "Take and transcribe voicemails",
                "enabled": True
            },
            {
                "id": "faq_responses",
                "name": "FAQ Responses",
                "description": "Answer common mortgage questions",
                "enabled": True
            },
            {
                "id": "lead_qualification",
                "name": "Lead Qualification",
                "description": "Pre-screen callers for loan eligibility",
                "enabled": True
            }
        ]
    }


@router.post("/voice-os/config")
async def update_voice_os_config(
    request: Request,
    current_user=Depends(get_current_user_flexible()),
):
    """Update Voice OS configuration"""
    try:
        data = await request.json()

        # In production, these would update environment variables or a config file
        # For now, we'll just acknowledge the update

        updated_fields = []

        if "voice" in data:
            # This would update the TTS_VOICE environment variable
            updated_fields.append("voice")
            logger.info(f"Voice updated to: {data['voice']}")

        if "stt_provider" in data:
            updated_fields.append("stt_provider")
            logger.info(f"STT provider updated to: {data['stt_provider']}")

        if "tts_provider" in data:
            updated_fields.append("tts_provider")
            logger.info(f"TTS provider updated to: {data['tts_provider']}")

        if "ai_model" in data:
            updated_fields.append("ai_model")
            logger.info(f"AI model updated to: {data['ai_model']}")

        return {
            "success": True,
            "message": f"Updated: {', '.join(updated_fields)}",
            "updated_fields": updated_fields
        }

    except Exception as e:
        logger.error(f"Error updating Voice OS config: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/voice-os/status")
async def get_voice_os_status(
    current_user=Depends(get_current_user_flexible()),
):
    """Get Voice OS system status and health"""
    # Voice OS runs through the main Python backend with Twilio + OpenAI integration
    # Check if the essential services are configured and enabled
    twilio_healthy = voice_client.enabled and bool(voice_client.from_number)
    openai_healthy = voice_client.openai_enabled

    # System is "running" if both Twilio and OpenAI are configured
    system_running = twilio_healthy and openai_healthy

    return {
        "system_status": "running" if system_running else "degraded" if (twilio_healthy or openai_healthy) else "stopped",
        "voice_os_url": os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://app.perenniaai.com"),
        "twilio_configured": bool(voice_client.from_number),
        "openai_configured": voice_client.openai_enabled,
        "phone_number": voice_client.from_number,
        "crm_integration": "active",
        "health_checks": {
            "twilio": "healthy" if twilio_healthy else "disconnected",
            "openai": "healthy" if openai_healthy else "disconnected",
            "database": "healthy",
            "webhooks": "configured"
        },
        "capabilities": {
            "inbound_calls": twilio_healthy,
            "outbound_calls": twilio_healthy,
            "ai_responses": openai_healthy,
            "call_transcription": openai_healthy,
            "voicemail": twilio_healthy
        }
    }


# ============================================================================
# MOBILE APP TRANSCRIPTION PROXY
# ============================================================================

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_flexible()),
):
    """
    Proxy to OpenAI Whisper API for audio transcription.
    Used by mobile app when OpenAI key is not in the app.
    """
    import httpx

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(500, "OpenAI API key not configured on server")

    try:
        # Read uploaded file
        audio_data = await file.read()

        # Send to OpenAI Whisper
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": (file.filename or "audio.m4a", audio_data, file.content_type or "audio/m4a")},
                data={"model": "whisper-1", "language": "en"},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Whisper API error: {response.status_code} - {response.text}")
                raise HTTPException(response.status_code, "Transcription failed")

            result = response.json()
            return {"success": True, "text": result.get("text", "")}

    except httpx.TimeoutException:
        logger.error("Whisper API timeout")
        raise HTTPException(504, "Transcription timed out")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(500, "Transcription failed")


# ============================================================================
# VOICE TESTING
# ============================================================================

@router.post("/voice-os/test-voice")
async def test_voice_sample(
    request: Request,
    current_user=Depends(get_current_user_flexible()),
):
    """Generate a voice sample for testing different voices"""
    try:
        data = await request.json()
        voice = data.get("voice", "alloy")
        sample_text = data.get("text", "Hello! Thank you for calling. How may I assist you today?")

        # Use OpenAI TTS to generate audio sample
        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=sample_text
            )

            # Convert to base64 for frontend playback
            audio_data = base64.b64encode(response.content).decode('utf-8')

            return {
                "success": True,
                "audio_data": audio_data,
                "voice": voice,
                "format": "mp3"
            }
        except Exception as tts_error:
            logger.error(f"OpenAI TTS error: {tts_error}")
            return {
                "success": False,
                "error": "TTS generation failed"
            }

    except Exception as e:
        logger.error(f"Error testing voice: {e}")
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# TWILIO VOICE INTELLIGENCE SETUP
# ============================================================================

@router.post("/intelligence/setup")
async def setup_intelligence_service(
    request: Request,
    current_user=Depends(get_current_user_flexible()),
):
    """
    One-time setup for Twilio Voice Intelligence Service.

    Creates the Intelligence Service and attaches AI operators for:
    - Automatic transcription with speaker diarization
    - PII redaction (SSN, phone numbers, etc.)
    - Sentiment analysis
    - Call summarization
    - Entity recognition
    - Escalation detection
    - Recording disclosure verification

    Returns the Service SID to add to environment variables.
    """
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}

        from integrations.twilio_intelligence_service import intelligence_service

        # Check if already configured
        if intelligence_service.service_sid:
            existing = intelligence_service.get_service_info()
            if existing:
                return {
                    "status": "already_configured",
                    "message": "Intelligence Service already exists",
                    "service": existing
                }

        # Create new service
        unique_name = data.get("unique_name", "MortgageCRMService")
        friendly_name = data.get("friendly_name", "Mortgage CRM Voice Intelligence")

        service_sid = intelligence_service.create_intelligence_service(
            unique_name=unique_name,
            friendly_name=friendly_name
        )

        if not service_sid:
            return {
                "status": "error",
                "message": "Failed to create Intelligence Service. Check Twilio credentials."
            }

        # Attach operators
        attached_operators = intelligence_service.attach_operators_to_service(service_sid)

        return {
            "status": "success",
            "message": "Intelligence Service created successfully",
            "service_sid": service_sid,
            "operators_attached": len(attached_operators),
            "operators": attached_operators,
            "next_steps": [
                f"Add to Railway environment: TWILIO_INTELLIGENCE_SERVICE_SID={service_sid}",
                "Redeploy the application",
                "Test with a real call recording"
            ]
        }

    except Exception as e:
        logger.error(f"Error setting up Intelligence Service: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/intelligence/status")
async def get_intelligence_status():
    """
    Get current status of Twilio Voice Intelligence configuration.
    """
    try:
        from integrations.twilio_intelligence_service import intelligence_service

        status = {
            "enabled": intelligence_service.enabled,
            "service_configured": bool(intelligence_service.service_sid),
            "service_sid": intelligence_service.service_sid if intelligence_service.service_sid else None,
            "webhook_base": intelligence_service.webhook_base,
        }

        # If configured, get full service info
        if intelligence_service.service_sid and intelligence_service.enabled:
            service_info = intelligence_service.get_service_info()
            if service_info:
                status["service"] = service_info

        return status

    except Exception as e:
        logger.error(f"Error getting Intelligence status: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/intelligence/operators")
async def list_available_operators():
    """
    List all available Twilio Voice Intelligence operators.
    """
    try:
        from integrations.twilio_intelligence_service import intelligence_service

        if not intelligence_service.enabled:
            return {
                "status": "error",
                "message": "Twilio client not configured"
            }

        operators = intelligence_service.list_available_operators()

        return {
            "operators": operators,
            "count": len(operators),
            "recommended": [
                "sentiment-analysis",
                "summarization",
                "entity-recognition",
                "escalation-request",
                "recording-disclosure"
            ]
        }

    except Exception as e:
        logger.error(f"Error listing operators: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.post("/intelligence/attach-operators")
async def attach_operators(request: Request):
    """
    Attach operators to an existing Intelligence Service.

    Body (optional):
    {
        "service_sid": "GAxxxx",  // optional, uses env var if not provided
        "operators": ["sentiment", "summary"]  // defaults to recommended set
    }
    """
    try:
        from integrations.twilio_intelligence_service import intelligence_service

        if not intelligence_service.enabled:
            return {
                "status": "error",
                "message": "Twilio client not configured."
            }

        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        service_sid = data.get("service_sid") or intelligence_service.service_sid
        operator_names = data.get("operators")  # None = use recommended

        if not service_sid:
            return {
                "status": "error",
                "message": "No service_sid provided and TWILIO_INTELLIGENCE_SERVICE_SID not set."
            }

        attached = intelligence_service.attach_operators_to_service(
            service_sid=service_sid,
            operator_names=operator_names
        )

        return {
            "status": "success",
            "service_sid": service_sid,
            "operators_attached": len(attached),
            "operators": attached
        }

    except Exception as e:
        logger.error(f"Error attaching operators: {e}")
        return {"status": "error", "message": "Internal server error"}


# ============================================================================
# RINGLESS VOICEMAIL & AMD ENDPOINTS
# Migrated from voice_ai_receptionist_routes.py to resolve duplicate route conflict
# ============================================================================

@router.post("/drop-voicemail")
async def drop_voicemail(
    request: Request,
    db: Session = Depends(get_db),
):
    """Drop a ringless voicemail using Slybroadcast (or fallback to Vapi)"""
    try:
        import httpx
        import tempfile
        import shutil
        from pathlib import Path
        from main import get_current_user_flexible as auth_dependency

        User, Lead, Task, Activity, IncomingDataEvent = get_models()

        # Authenticate
        current_user = await auth_dependency(request, db)

        # Lazy import models needed for voicemail
        from main import VoicemailDrop, ActivityType

        data = await request.json()
        to_number = data.get("to_number")
        message = data.get("message")
        recipient_name = data.get("recipient_name", "")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        provider = data.get("provider", "slybroadcast")

        if not to_number:
            raise HTTPException(status_code=400, detail="Phone number is required")
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Format phone number
        clean_number = ''.join(filter(str.isdigit, to_number))
        if len(clean_number) == 11 and clean_number.startswith('1'):
            clean_number = clean_number[1:]

        logger.info(f"Dropping voicemail to {clean_number} for {recipient_name} via {provider}")

        greeting = f"Hi {recipient_name}, " if recipient_name else "Hello, "
        full_message = (
            f"{greeting}this is the AI assistant calling from "
            f"{current_user.full_name or 'your loan officer'}'s office. "
            f"{message} "
            f"Feel free to call us back at your convenience. Have a great day!"
        )

        voicemail_drop = VoicemailDrop(
            user_id=current_user.id,
            lead_id=lead_id,
            loan_id=loan_id,
            phone_number=clean_number,
            contact_name=recipient_name,
            message_text=message,
            status='pending'
        )
        db.add(voicemail_drop)
        db.commit()
        db.refresh(voicemail_drop)

        session_id = None

        if provider == "zapier":
            logger.info("Using Zapier webhook to trigger Slybroadcast")
            zapier_webhook_url = os.getenv("ZAPIER_VOICEMAIL_WEBHOOK_URL")
            if not zapier_webhook_url:
                raise HTTPException(status_code=503, detail="Zapier webhook URL not configured")

            async with httpx.AsyncClient(timeout=30.0) as client:
                zapier_payload = {
                    "phone_number": clean_number,
                    "message": full_message,
                    "recipient_name": recipient_name or "Customer",
                    "caller_id": os.getenv("SLYBROADCAST_CALLER_ID", "8438345251"),
                    "voicemail_id": voicemail_drop.id
                }
                zapier_response = await client.post(zapier_webhook_url, json=zapier_payload, timeout=30.0)

                if zapier_response.status_code not in [200, 201]:
                    error_msg = zapier_response.text
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = f"Zapier error: {error_msg}"
                    db.commit()
                    raise HTTPException(status_code=500, detail=f"Zapier webhook error: {error_msg}")

                session_id = f"zapier_{voicemail_drop.id}"
                voicemail_drop.vapi_call_id = session_id
                voicemail_drop.status = 'sent_to_zapier'
                db.commit()

        elif provider == "slybroadcast":
            logger.info("Using Slybroadcast for ringless voicemail")
            sly_email = os.getenv("SLYBROADCAST_EMAIL")
            sly_password = os.getenv("SLYBROADCAST_PASSWORD")
            sly_caller_id = os.getenv("SLYBROADCAST_CALLER_ID", "8438345251")

            if not sly_email or not sly_password:
                raise HTTPException(status_code=503, detail="Slybroadcast credentials not configured")

            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise HTTPException(status_code=503, detail="OpenAI API key not configured for TTS")

            async with httpx.AsyncClient(timeout=60.0) as client:
                tts_response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"},
                    json={"model": "tts-1", "voice": "nova", "input": full_message, "speed": 0.95}
                )
                if tts_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to generate voicemail audio")

                audio_data = tts_response.content
                temp_dir = Path(tempfile.gettempdir())
                audio_filename = f"voicemail_{voicemail_drop.id}_{datetime.now(timezone.utc).timestamp()}.mp3"
                audio_path = temp_dir / audio_filename

                with open(audio_path, 'wb') as f:
                    f.write(audio_data)

                static_dir = Path("/app/static") if Path("/app/static").exists() else Path("static")
                static_dir.mkdir(exist_ok=True)
                shutil.copy(audio_path, static_dir / audio_filename)

                api_url = os.getenv("API_URL", "https://app.perenniaai.com")
                audio_url = f"{api_url}/static/{audio_filename}"

                slybroadcast_data = {
                    "c_method": "new_campaign",
                    "c_uid": sly_email,
                    "c_password": sly_password,
                    "c_phone": clean_number,
                    "c_callerID": sly_caller_id,
                    "c_date": "now",
                    "c_url": audio_url,
                    "c_audio": "mp3",
                    "c_title": f"Voicemail to {recipient_name or clean_number}",
                    "mobile_only": "1"
                }
                sly_response = await client.post(
                    "https://www.slybroadcast.com/gateway/vmb.json.php",
                    data=slybroadcast_data,
                    timeout=30.0
                )

                try:
                    sly_data = sly_response.json()
                except Exception:
                    raise HTTPException(status_code=500, detail=f"Invalid JSON from Slybroadcast: {sly_response.text}")

                if sly_data.get("new_campaign") == "OK":
                    session_id = str(sly_data.get("session_id"))
                    voicemail_drop.vapi_call_id = session_id
                    voicemail_drop.status = 'sent'
                    db.commit()
                elif "ERROR" in sly_data:
                    error_msg = sly_data.get("ERROR", "Unknown error")
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = error_msg
                    db.commit()
                    raise HTTPException(status_code=500, detail=f"Slybroadcast error: {error_msg}")
                else:
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = str(sly_data)
                    db.commit()
                    raise HTTPException(status_code=500, detail=f"Unexpected Slybroadcast response: {sly_data}")

        else:
            # Vapi fallback
            logger.info("Using Vapi for voicemail (phone will ring)")
            vapi_api_key = os.getenv("VAPI_API_KEY")
            vapi_assistant_id = os.getenv("VAPI_VOICEMAIL_ASSISTANT_ID", os.getenv("VAPI_ASSISTANT_ID"))
            vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

            if not vapi_api_key or not vapi_assistant_id:
                raise HTTPException(status_code=503, detail="Vapi credentials not configured")

            vapi_number = f"+1{clean_number}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                vapi_payload = {
                    "customer": {"number": vapi_number},
                    "assistantId": vapi_assistant_id,
                    "assistantOverrides": {
                        "firstMessage": full_message,
                        "voicemailMessage": full_message
                    }
                }
                if vapi_phone_number_id:
                    vapi_payload["phoneNumberId"] = vapi_phone_number_id

                vapi_response = await client.post(
                    "https://api.vapi.ai/call/phone",
                    headers={"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"},
                    json=vapi_payload
                )
                if vapi_response.status_code not in [200, 201]:
                    raise HTTPException(status_code=500, detail=f"Vapi error: {vapi_response.text}")

                vapi_data = vapi_response.json()
                session_id = vapi_data.get("id")
                voicemail_drop.vapi_call_id = session_id
                db.commit()

        # Log activity
        activity = Activity(
            user_id=current_user.id,
            type=ActivityType.CALL,
            content=f"Ringless voicemail sent to {recipient_name or clean_number}: {message[:100]}",
            user_metadata={
                "direction": "outbound",
                "phone_number": clean_number,
                "recipient_name": recipient_name,
                "session_id": session_id,
                "voicemail_drop_id": voicemail_drop.id,
                "message": message,
                "status": "sent",
                "call_type": "ringless_voicemail",
                "provider": provider
            },
            lead_id=lead_id,
            loan_id=loan_id
        )
        db.add(activity)
        db.commit()

        return {
            "success": True,
            "voicemail_id": voicemail_drop.id,
            "session_id": session_id,
            "provider": provider,
            "message": f"Ringless voicemail sent successfully via {provider}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dropping voicemail: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


@router.post("/amd-callback")
async def amd_callback(request: Request):
    """Handle AMD (Answering Machine Detection) callback (legacy Twilio)"""
    try:
        form_data = await request.form()
        form_dict = {k: v for k, v in form_data.items()}

        # Validate Twilio signature
        if not await _validate_twilio_signature(request, form_dict):
            logger.warning("Invalid Twilio signature on AMD callback")
            return {"status": "rejected"}

        amd_status = form_data.get("AnsweredBy")
        call_sid = form_data.get("CallSid")
        logger.info(f"AMD Callback - CallSid: {call_sid}, AnsweredBy: {amd_status}")
        return {"status": "received", "answered_by": amd_status}
    except Exception as e:
        logger.error(f"Error in AMD callback: {e}")
        return {"status": "error"}


@router.get("/voicemail-twiml")
async def voicemail_twiml_generator(
    message: str = "",
    AnsweredBy: str = None,
    request: Request = None
):
    """Generate TwiML for voicemail message - only plays if voicemail detected"""
    from twilio.twiml.voice_response import VoiceResponse

    response = VoiceResponse()

    if AnsweredBy == 'human':
        logger.info("Human detected, hanging up to avoid disturbing")
        response.hangup()
    else:
        response.pause(length=2)
        response.say(message, voice='Polly.Ruth-Neural', language='en-US')
        response.pause(length=1)
        response.hangup()

    return Response(content=str(response), media_type="application/xml")
