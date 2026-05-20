"""
Voice Routes - Inbound Call Handling

Contains:
- /incoming endpoint (Telnyx webhook)
- /outbound-script endpoint
- /make-call (simple outbound, line ~421)
- Call screening endpoints (/screening, /screening-name, /screening-complete, /screening-transcription, /blocked)
- _lookup_org_by_phone (C-3 fix)
"""
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

from database import get_db
from middleware.webhook_verification import require_telnyx_webhook as _require_telnyx_webhook
from ai_receptionist_dashboard_models import AIReceptionistActivity
from services.call_screening_service import (
    CallScreeningService,
    ScreeningDecision,
    ScreeningResult,
    add_to_whitelist
)

from .utils import (
    mask_phone, voice_client, ai_config,
    get_models, require_telnyx_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PHONE-TO-ORG LOOKUP (C-3 fix: populate organization_id on inbound calls)
# ============================================================================

def _lookup_org_by_phone(db: Session, called_number: str) -> Optional[int]:
    """Look up organization_id from the called phone number (the DID that was called).

    Checks verified_caller_ids -> agent_telephony_settings -> ai_receptionist_activity.
    Returns None if no mapping is found (logs warning but does not break call flow).
    """
    if not called_number:
        return None

    normalized = called_number.strip()

    try:
        # Primary: verified_caller_ids
        result = db.execute(
            sa_text(
                "SELECT organization_id FROM verified_caller_ids "
                "WHERE phone_number = :phone AND verification_status = 'verified' "
                "AND organization_id IS NOT NULL LIMIT 1"
            ),
            {"phone": normalized},
        ).fetchone()
        if result and result[0]:
            logger.info(f"Resolved org_id={result[0]} for called number {mask_phone(normalized)} via verified_caller_ids")
            return result[0]

        # Fallback: agent_telephony_settings
        result = db.execute(
            sa_text(
                "SELECT organization_id FROM agent_telephony_settings "
                "WHERE business_caller_id = :phone AND organization_id IS NOT NULL LIMIT 1"
            ),
            {"phone": normalized},
        ).fetchone()
        if result and result[0]:
            logger.info(f"Resolved org_id={result[0]} for called number {mask_phone(normalized)} via agent_telephony_settings")
            return result[0]

        # Last resort: recent ai_receptionist_activity
        result = db.execute(
            sa_text(
                "SELECT organization_id FROM ai_receptionist_activity "
                "WHERE extra_data->>'called_number' = :phone AND organization_id IS NOT NULL "
                "ORDER BY timestamp DESC LIMIT 1"
            ),
            {"phone": normalized},
        ).fetchone()
        if result and result[0]:
            logger.info(f"Resolved org_id={result[0]} for called number {mask_phone(normalized)} via recent activity")
            return result[0]

        logger.warning(f"Could not resolve organization_id for called number {mask_phone(normalized)}")
        return None

    except Exception as e:
        logger.warning(f"Error looking up org_id for called number {mask_phone(normalized)}: {e}")
        return None


# ============================================================================
# INBOUND CALL HANDLING
# ============================================================================

@router.post("/incoming")
async def handle_incoming_call(
    request: Request,
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(_require_telnyx_webhook)
):
    """
    Telnyx webhook for incoming calls
    Returns TeXML to handle the call with AI

    Call flow with spam filtering:
    1. Screen the call (whitelist -> blocklist -> lookup -> unknown)
    2. ALLOW: Connect directly to AI receptionist
    3. BLOCK: Hang up immediately (no message)
    4. SCREEN: Ask name/reason before connecting
    """
    try:
        form_data = await request.form()

        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_sid = form_data.get("CallSid", "")

        # C-3 fix: Resolve organization_id from the called DID
        organization_id = _lookup_org_by_phone(db, called_number)

        logger.info(f"Incoming call from {mask_phone(caller_number)} to {mask_phone(called_number)} (SID: {call_sid}, org_id: {organization_id})")

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
                organization_id=organization_id,
                extra_data={
                    "call_sid": call_sid,
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
                organization_id=organization_id,
                extra_data={
                    "call_sid": call_sid,
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
                    organization_id=organization_id,
                    extra_data={
                        "call_sid": call_sid,
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
        except Exception as e:
            # Last resort: voicemail
            logger.error(f"Error in handle_incoming_call (greeting fallback): {e}")
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
    <Say voice="Polly.Joanna">Hello! This is Aria from The Tim Loss Team. I'm calling to follow up on your mortgage inquiry. How can I help you today?</Say>
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
    db: AsyncSession = Depends(get_async_db)
):
    """
    Initiate an outbound call to a phone number.
    The AI receptionist (Aria) will handle the call and try to schedule an appointment.
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

        # Make the call using Telnyx
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
                    "call_sid": call_sid,
                    "purpose": purpose,
                    "caller_name": caller_name
                }
            )
            db.add(dashboard_activity)
            await db.commit()

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
                "error": "Failed to initiate call - check telephony provider configuration"
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
async def handle_screening(request: Request, db: AsyncSession = Depends(get_async_db)):
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
async def handle_screening_name(request: Request, db: AsyncSession = Depends(get_async_db)):
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
async def handle_screening_complete(request: Request, db: AsyncSession = Depends(get_async_db)):
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
            await db.execute(text("""
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
            await db.commit()
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
async def handle_screening_transcription(request: Request, db: AsyncSession = Depends(get_async_db)):
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
                    await db.execute(text("""
                        UPDATE call_screening_log
                        SET caller_stated_name = COALESCE(caller_stated_name, :name)
                        WHERE call_sid = :call_sid
                    """), {"call_sid": call_sid, "name": transcription_text})
                else:  # Likely a reason
                    await db.execute(text("""
                        UPDATE call_screening_log
                        SET caller_stated_reason = COALESCE(caller_stated_reason, :reason)
                        WHERE call_sid = :call_sid
                    """), {"call_sid": call_sid, "reason": transcription_text})

                await db.commit()
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
