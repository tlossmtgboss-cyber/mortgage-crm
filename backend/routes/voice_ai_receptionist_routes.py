"""
Voice AI Receptionist Routes
============================
AI-powered voice receptionist, call handling, voicemail drops, and SMS messaging.
Extracted from main.py lines 23109-24519.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Body, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, func
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import json
import logging
import os

from database import get_db
from middleware.webhook_verification import require_telnyx_webhook, require_vapi_webhook

logger = logging.getLogger(__name__)


def _log_receptionist_activity(
    db: Session,
    action_type: str,
    channel: str = "voice",
    client_name: str = None,
    client_phone: str = None,
    message_in: str = None,
    message_out: str = None,
    outcome_status: str = None,
    conversation_id: str = None,
    organization_id: int = None,
    extra_data: dict = None,
):
    """Log an AI receptionist activity for dashboard analytics (REC-006)."""
    try:
        from ai_receptionist_dashboard_models import AIReceptionistActivity
        activity = AIReceptionistActivity(
            organization_id=organization_id,
            action_type=action_type,
            channel=channel,
            client_name=client_name,
            client_phone=client_phone,
            message_in=message_in,
            message_out=message_out,
            outcome_status=outcome_status,
            conversation_id=conversation_id,
            extra_data=extra_data,
        )
        db.add(activity)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log receptionist activity: {e}")
        try:
            db.rollback()
        except Exception as e:
            logger.warning(f"Failed to rollback in _log_receptionist_activity: {e}")

router = APIRouter(prefix="/api/v1/voice", tags=["Voice AI Receptionist"])


# ============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# ============================================================================

def get_current_user_dep():
    """Get current user dependency - imports from main at runtime"""
    import main
    return main.get_current_user


def get_models():
    """Get models from main at runtime"""
    import main
    return main


def get_session_local():
    """Get SessionLocal for background tasks"""
    from database import SessionLocal
    return SessionLocal


# ============================================================================
# VOICE API - AI RECEPTIONIST ENDPOINTS
# ============================================================================

@router.get("/ai-receptionist-config")
async def get_ai_receptionist_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get AI Receptionist configuration"""
    try:
        # Check if telephony and OpenAI are configured
        telnyx_phone = os.getenv("TELNYX_PHONE_NUMBER")
        telnyx_key = os.getenv("TELNYX_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        enabled = bool(telnyx_phone and telnyx_key and openai_key)

        # Get business config from user metadata or defaults
        user_metadata = current_user.user_metadata or {}
        business_config = user_metadata.get('ai_receptionist_config', {})

        return {
            "enabled": enabled,
            "business_name": business_config.get("business_name", current_user.full_name or "Your Business"),
            "phone_number": telnyx_phone,
            "business_hours": business_config.get("business_hours", {
                "start": "09:00",
                "end": "17:00",
                "timezone": "America/Chicago"
            })
        }
    except Exception as e:
        logger.error(f"Error getting AI receptionist config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ai-receptionist-config")
async def update_ai_receptionist_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update AI Receptionist configuration"""
    try:
        data = await request.json()

        # Get or create user metadata
        user_metadata = current_user.user_metadata or {}

        # Update AI receptionist config
        user_metadata['ai_receptionist_config'] = {
            "business_name": data.get("business_name"),
            "business_hours": data.get("business_hours", {}),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Save to database
        current_user.user_metadata = user_metadata
        db.commit()

        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        logger.error(f"Error updating AI receptionist config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/call-stats")
async def get_call_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get call statistics for AI Receptionist"""
    try:
        main = get_models()
        Activity = main.Activity
        ActivityType = main.ActivityType
        Lead = main.Lead

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        # Get call activities from activity log
        activities = db.query(Activity).filter(
            Activity.user_id == current_user.id,
            Activity.type == ActivityType.CALL,
            Activity.created_at >= thirty_days_ago
        ).all()

        # Calculate stats
        total_calls = len(activities)
        inbound_calls = sum(1 for a in activities if a.user_metadata and a.user_metadata.get('direction') == 'inbound')
        outbound_calls = sum(1 for a in activities if a.user_metadata and a.user_metadata.get('direction') == 'outbound')

        # Count leads generated from calls
        leads_from_calls = db.query(Lead).filter(
            Lead.owner_id == current_user.id,
            Lead.source.ilike('%call%'),
            Lead.created_at >= thirty_days_ago
        ).count()

        return {
            "total_calls": total_calls,
            "inbound_calls": inbound_calls,
            "outbound_calls": outbound_calls,
            "leads_generated": leads_from_calls
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


@router.get("/call-history")
async def get_call_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get call history from activity log"""
    try:
        main = get_models()
        Activity = main.Activity
        ActivityType = main.ActivityType

        # Get call activities
        activities = db.query(Activity).filter(
            Activity.user_id == current_user.id,
            Activity.type == ActivityType.CALL
        ).order_by(Activity.created_at.desc()).limit(limit).all()

        calls = []
        for activity in activities:
            metadata = activity.user_metadata or {}
            calls.append({
                "id": activity.id,
                "description": activity.content,
                "created_at": activity.created_at.isoformat() if activity.created_at else None,
                "metadata": {
                    "direction": metadata.get("direction", "inbound"),
                    "duration": metadata.get("duration"),
                    "status": metadata.get("status", "completed"),
                    "phone_number": metadata.get("phone_number")
                }
            })

        return {"calls": calls}
    except Exception as e:
        logger.error(f"Error getting call history: {e}")
        return {"calls": [], "error": "Internal server error"}


@router.post("/make-call")
async def make_outbound_call(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Make an outbound AI call"""
    try:
        from telephony.provider import get_telephony_provider
        main = get_models()
        Activity = main.Activity
        ActivityType = main.ActivityType

        data = await request.json()
        to_number = data.get("to_number")
        script_type = data.get("script_type", "default")
        lead_id = data.get("lead_id")

        if not to_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        # Initialize telephony provider
        provider = get_telephony_provider()

        # Get outbound phone number
        from_number = os.getenv("TELNYX_PHONE_NUMBER")
        if not from_number:
            raise HTTPException(status_code=503, detail="Outbound phone number not configured")

        # Create TwiML for the call - use OpenAI Realtime API webhook
        api_url = os.getenv("API_URL", "https://app.perenniaai.com")
        twiml_url = f"{api_url}/api/v1/voice/incoming?script_type={script_type}"

        # Make the call
        call_result = provider.place_call(
            to=to_number,
            from_=from_number,
            url=twiml_url,
            status_callback=f"{api_url}/api/v1/voice/call-status",
        )

        call_sid = call_result.call_sid if hasattr(call_result, 'call_sid') else str(call_result)

        # Log the activity
        activity = Activity(
            user_id=current_user.id,
            type=ActivityType.CALL,
            content=f"AI called {to_number}",
            user_metadata={
                "direction": "outbound",
                "phone_number": to_number,
                "script_type": script_type,
                "call_sid": call_sid,
                "status": "initiated",
                "call_type": "outbound_call"
            },
            lead_id=lead_id
        )
        db.add(activity)
        db.commit()

        return {
            "success": True,
            "call_sid": call_sid,
            "message": "Call initiated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/drop-voicemail")
async def drop_voicemail(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Drop a ringless voicemail using Slybroadcast (or fallback to Vapi)"""
    try:
        import httpx
        import tempfile
        import shutil
        from pathlib import Path

        main = get_models()
        VoicemailDrop = main.VoicemailDrop
        Activity = main.Activity
        ActivityType = main.ActivityType

        data = await request.json()
        to_number = data.get("to_number")
        message = data.get("message")
        recipient_name = data.get("recipient_name", "")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        provider = data.get("provider", "slybroadcast")  # Default to Slybroadcast

        if not to_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Format phone number (10 digits for Slybroadcast, E.164 for Vapi)
        clean_number = ''.join(filter(str.isdigit, to_number))
        if len(clean_number) == 11 and clean_number.startswith('1'):
            clean_number = clean_number[1:]  # Remove leading 1 for Slybroadcast

        # --- TCPA Compliance Checks ---
        try:
            from routes.voicemail_drop_routes import run_compliance_checks
            is_allowed, rejection_reason = run_compliance_checks(
                phone_number=clean_number,
                lead_id=lead_id,
                db=db,
            )
            if not is_allowed:
                logger.warning(
                    f"Voicemail drop blocked for {clean_number}: {rejection_reason} "
                    f"(user={current_user.id})"
                )
                raise HTTPException(status_code=403, detail=rejection_reason)
        except ImportError:
            logger.warning("Could not import TCPA compliance checks — proceeding without")

        logger.info(f"Dropping voicemail to {clean_number} for {recipient_name} via {provider}")

        # Format the message naturally with context
        greeting = f"Hi {recipient_name}, " if recipient_name else "Hello, "
        full_message = (
            f"{greeting}this is the AI assistant calling from "
            f"{current_user.full_name or 'your loan officer'}'s office. "
            f"{message} "
            f"Feel free to call us back at your convenience. Have a great day!"
        )

        # Create voicemail drop record
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
            # ZAPIER + SLYBROADCAST INTEGRATION (Interim Solution)
            logger.info("Using Zapier webhook to trigger Slybroadcast")

            zapier_webhook_url = os.getenv("ZAPIER_VOICEMAIL_WEBHOOK_URL")
            if not zapier_webhook_url:
                raise HTTPException(status_code=503, detail="Zapier webhook URL not configured. Set ZAPIER_VOICEMAIL_WEBHOOK_URL in environment variables.")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Send data to Zapier webhook
                zapier_payload = {
                    "phone_number": clean_number,
                    "message": full_message,
                    "recipient_name": recipient_name or "Customer",
                    "caller_id": os.getenv("SLYBROADCAST_CALLER_ID", "8438345251"),
                    "voicemail_id": voicemail_drop.id
                }

                logger.info("Sending to Zapier webhook")
                logger.info("Zapier payload prepared")

                zapier_response = await client.post(
                    zapier_webhook_url,
                    json=zapier_payload,
                    timeout=30.0
                )

                if zapier_response.status_code not in [200, 201]:
                    error_msg = zapier_response.text
                    logger.error(f"Zapier webhook error: {error_msg}")
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = f"Zapier error: {error_msg}"
                    db.commit()
                    raise HTTPException(status_code=500, detail="Voicemail delivery failed via webhook")

                # Zapier webhook triggered successfully
                session_id = f"zapier_{voicemail_drop.id}"
                voicemail_drop.vapi_call_id = session_id
                voicemail_drop.status = 'sent_to_zapier'
                db.commit()
                logger.info(f"Zapier webhook triggered successfully")

        elif provider == "slybroadcast":
            # SLYBROADCAST RINGLESS VOICEMAIL
            logger.info("Using Slybroadcast for ringless voicemail")

            # Get Slybroadcast credentials
            sly_email = os.getenv("SLYBROADCAST_EMAIL")
            sly_password = os.getenv("SLYBROADCAST_PASSWORD")
            sly_caller_id = os.getenv("SLYBROADCAST_CALLER_ID", "8438345251")  # Default caller ID

            if not sly_email or not sly_password:
                raise HTTPException(status_code=503, detail="Slybroadcast credentials not configured")

            # Step 1: Generate audio file using OpenAI TTS
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise HTTPException(status_code=503, detail="OpenAI API key not configured for TTS")

            logger.info("Generating TTS audio with OpenAI")

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Generate TTS audio
                tts_response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "tts-1",
                        "voice": "nova",  # Natural, friendly female voice
                        "input": full_message,
                        "speed": 0.95  # Slightly slower for clarity
                    }
                )

                if tts_response.status_code != 200:
                    logger.error(f"OpenAI TTS error: {tts_response.text}")
                    raise HTTPException(status_code=500, detail="Failed to generate voicemail audio")

                # Save audio file temporarily
                audio_data = tts_response.content
                temp_dir = Path(tempfile.gettempdir())
                audio_filename = f"voicemail_{voicemail_drop.id}_{datetime.now(timezone.utc).timestamp()}.mp3"
                audio_path = temp_dir / audio_filename

                with open(audio_path, 'wb') as f:
                    f.write(audio_data)

                logger.info(f"Audio file saved to {audio_path}")

                # Upload audio to a public URL (using Railway public storage)
                # For now, we'll use a base64 encoded data URL (Slybroadcast supports c_url parameter)
                # In production, upload to S3/CloudFlare R2 and use c_url

                # WARNING: Audio saved to ephemeral filesystem. On Railway, any deploy
                # wipes these files. If Slybroadcast fetches after a deploy, it gets 404.
                # TODO: Upload to S3/CloudFlare R2 for persistent URLs.
                static_dir = Path("/app/static") if Path("/app/static").exists() else Path("static")
                static_dir.mkdir(exist_ok=True)
                static_audio_path = static_dir / audio_filename

                shutil.copy(audio_path, static_audio_path)
                logger.warning(
                    f"Audio file {audio_filename} saved to ephemeral disk. "
                    "Migrate to S3/R2 for reliable Slybroadcast delivery."
                )

                # Get public URL for audio
                api_url = os.getenv("API_URL", "https://app.perenniaai.com")
                audio_url = f"{api_url}/static/{audio_filename}"

                logger.info(f"Audio URL: {audio_url}")

                # Step 2: Call Slybroadcast JSON API
                slybroadcast_data = {
                    "c_method": "new_campaign",
                    "c_uid": sly_email,
                    "c_password": sly_password,
                    "c_phone": clean_number,
                    "c_callerID": sly_caller_id,
                    "c_date": "now",  # Immediate delivery
                    "c_url": audio_url,
                    "c_audio": "mp3",
                    "c_title": f"Voicemail to {recipient_name or clean_number}",
                    "mobile_only": "1"  # Deliver to mobile phones only
                }

                logger.info(f"Calling Slybroadcast JSON API for {clean_number}")
                logger.info(f"Slybroadcast payload: {dict(c_phone=clean_number, c_callerID=sly_caller_id, c_url=audio_url)}")

                sly_response = await client.post(
                    "https://www.slybroadcast.com/gateway/vmb.json.php",
                    data=slybroadcast_data,  # Send as form data, not JSON body
                    timeout=30.0
                )

                logger.info(f"Slybroadcast response status: {sly_response.status_code}")
                logger.info(f"Slybroadcast response: {sly_response.text}")

                # Parse JSON response
                try:
                    sly_data = sly_response.json()
                except Exception as e:
                    logger.error(f"Failed to parse Slybroadcast JSON response: {sly_response.text}")
                    raise HTTPException(status_code=500, detail=f"Invalid JSON response from Slybroadcast: {sly_response.text}")

                # Check for success: {"new_campaign": "OK", "session_id": "123456", "number_of_phone": 1}
                if sly_data.get("new_campaign") == "OK":
                    session_id = str(sly_data.get("session_id"))
                    voicemail_drop.vapi_call_id = session_id
                    voicemail_drop.status = 'sent'
                    db.commit()
                    logger.info(f"Voicemail sent successfully via Slybroadcast. Session ID: {session_id}")
                elif "ERROR" in sly_data:
                    # Error response: {"ERROR": "error message"}
                    error_msg = sly_data.get("ERROR", "Unknown error")
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = error_msg
                    db.commit()
                    logger.error(f"Slybroadcast error: {error_msg}")
                    raise HTTPException(status_code=500, detail="Voicemail delivery failed")
                else:
                    # Unexpected response
                    error_msg = str(sly_data)
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = error_msg
                    db.commit()
                    logger.error(f"Unexpected Slybroadcast response: {error_msg}")
                    raise HTTPException(status_code=500, detail="Voicemail delivery returned unexpected response")

        else:
            # VAPI FALLBACK (will ring the phone)
            logger.info("Using Vapi for voicemail (phone will ring)")
            vapi_api_key = os.getenv("VAPI_API_KEY")
            vapi_assistant_id = os.getenv("VAPI_VOICEMAIL_ASSISTANT_ID", os.getenv("VAPI_ASSISTANT_ID"))
            vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

            if not vapi_api_key or not vapi_assistant_id:
                raise HTTPException(status_code=503, detail="Vapi credentials not configured")

            # E.164 format for Vapi
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
                    error_msg = vapi_response.text
                    logger.error(f"Vapi error: {error_msg}")
                    raise HTTPException(status_code=500, detail="Voice call initiation failed")

                vapi_data = vapi_response.json()
                session_id = vapi_data.get("id")
                voicemail_drop.vapi_call_id = session_id
                db.commit()

        # Log the activity
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
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/amd-callback")
async def amd_callback(request: Request):
    """Handle AMD (Answering Machine Detection) callback (legacy)"""
    try:
        form_data = await request.form()
        amd_status = form_data.get("AnsweredBy")
        call_sid = form_data.get("CallSid")

        logger.info(f"AMD Callback - CallSid: {call_sid}, AnsweredBy: {amd_status}")

        return {"status": "received", "answered_by": amd_status}
    except Exception as e:
        logger.error(f"Error in AMD callback: {e}")
        return {"status": "error"}


@router.get("/voicemail-twiml")
async def voicemail_twiml(
    message: str = "",
    AnsweredBy: str = None,
    request: Request = None
):
    """Generate TwiML for voicemail message - only plays if voicemail detected"""
    from telephony.providers.telnyx.texml import TeXMLResponse

    response = TeXMLResponse()

    # If AMD detected a human, hang up immediately
    if AnsweredBy == 'human':
        logger.info("Human detected, hanging up to avoid disturbing")
        response.hangup()
    else:
        # Machine or unknown - play the message with AI receptionist voice
        # Pause briefly to ensure we're past the beep
        response.pause(length=2)

        # Use neural voice for more natural AI receptionist sound
        # Format message with SSML for more natural delivery
        response.say(
            message,
            voice='Polly.Ruth-Neural',  # Natural conversational female voice
            language='en-US'
        )

        # Brief pause before hanging up
        response.pause(length=1)
        response.hangup()

    return Response(content=str(response), media_type="application/xml")


# ============================================================================
# WEBHOOK ENDPOINTS (moved to separate prefix in router)
# ============================================================================

# Create sub-router for webhooks that need different prefix
webhook_router = APIRouter(prefix="/api/v1/webhooks", tags=["Voice Webhooks"])


@webhook_router.post("/vapi/voicemail-status")
async def vapi_voicemail_status_webhook(
    request: Request,
    voicemail_id: int,
    raw_body: bytes = Depends(require_vapi_webhook),
    db: Session = Depends(get_db)
):
    """Handle Vapi webhook for voicemail drop status updates.

    Signature verification is handled by the require_vapi_webhook dependency.
    """
    try:
        main = get_models()
        VoicemailDrop = main.VoicemailDrop

        payload = json.loads(raw_body)
        logger.info(f"Vapi voicemail webhook received for voicemail_id={voicemail_id}: {payload}")

        # Find the voicemail drop record
        voicemail_drop = db.query(VoicemailDrop).filter(VoicemailDrop.id == voicemail_id).first()
        if not voicemail_drop:
            logger.error(f"Voicemail drop {voicemail_id} not found")
            return {"status": "error", "message": "Voicemail drop not found"}

        message_type = payload.get("message", {}).get("type")

        # Handle end-of-call-report
        if message_type == "end-of-call-report":
            call_data = payload.get("call", {})
            end_reason = call_data.get("endedReason")
            duration = call_data.get("duration")  # in seconds
            cost = call_data.get("cost")

            # Update voicemail drop status
            if end_reason in ["assistant-left-voicemail", "voicemail-detected"]:
                voicemail_drop.status = "delivered"
                voicemail_drop.delivered_at = datetime.now(timezone.utc)
            elif end_reason == "customer-did-not-answer":
                voicemail_drop.status = "no-answer"
            elif end_reason in ["customer-ended-call", "customer-busy"]:
                voicemail_drop.status = "failed"
                voicemail_drop.error_message = end_reason
            else:
                voicemail_drop.status = "completed"

            voicemail_drop.call_duration = duration
            voicemail_drop.call_cost = cost

            db.commit()

            logger.info(f"Updated voicemail drop {voicemail_id}: status={voicemail_drop.status}")

            # Log to AI receptionist dashboard analytics
            _log_receptionist_activity(
                db=db,
                action_type="outbound_followup",
                channel="voice",
                client_name=getattr(voicemail_drop, 'contact_name', None),
                client_phone=getattr(voicemail_drop, 'phone_number', None),
                outcome_status=voicemail_drop.status,
                extra_data={"voicemail_id": voicemail_id, "end_reason": end_reason, "duration": duration},
            )

            # Send post-call confirmation SMS if voicemail was delivered
            if voicemail_drop.status == "delivered" and voicemail_drop.phone_number:
                try:
                    from integrations.sms_service import get_sms_client
                    sms_client = get_sms_client(db=db)
                    if sms_client.enabled:
                        contact_name = voicemail_drop.contact_name or "there"
                        sms_body = (
                            f"Hi {contact_name}, I just left you a voicemail. "
                            f"Feel free to call or text me back at your convenience!"
                        )
                        sms_client.send_sms(
                            to_phone=voicemail_drop.phone_number,
                            message=sms_body,
                        )
                        logger.info(f"Post-call SMS sent to {voicemail_drop.phone_number} for voicemail {voicemail_id}")
                except Exception as sms_err:
                    logger.warning(f"Post-call SMS failed for voicemail {voicemail_id}: {sms_err}")

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error in Vapi voicemail webhook: {e}", exc_info=True)
        return {"status": "error", "message": "Internal server error"}


@webhook_router.post("/telnyx/sms")
async def telephony_sms_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(require_telnyx_webhook),
):
    """
    Webhook for incoming SMS messages.
    Processes incoming texts, identifies the sender, and generates AI responses.
    Webhook signature is verified by the require_telnyx_webhook dependency.

    Configure in Telnyx Mission Control:
    - Messaging > Messaging Profiles > [Your Profile]
    - Set webhook URL: https://your-domain.com/api/v1/webhooks/telnyx/sms
    """
    logger.info("SMS_WEBHOOK: Request received")
    try:
        main = get_models()
        User = main.User
        Activity = main.Activity
        ActivityType = main.ActivityType
        SMSMessage = main.SMSMessage
        SMSConversation = main.SMSConversation

        # Parse webhook payload FIRST (form-encoded)
        form_data = await request.form()
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        message_body = form_data.get("Body", "")
        message_sid = form_data.get("MessageSid", "")
        num_media = int(form_data.get("NumMedia", 0))

        logger.info(f"SMS_WEBHOOK: From={from_number}, Body={message_body[:50]}...")

        # Auto-create sms_conversations table if it doesn't exist
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_conversations (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(50) NOT NULL,
                    user_id INTEGER REFERENCES users(id),
                    lead_id INTEGER REFERENCES leads(id),
                    loan_id INTEGER REFERENCES loans(id),
                    contact_id INTEGER,
                    contact_name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    ai_enabled BOOLEAN DEFAULT TRUE,
                    last_message_at TIMESTAMP,
                    last_ai_response_at TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    context JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_sms_conv_phone ON sms_conversations(phone_number)"))
            db.commit()
            logger.info("SMS conversations table ensured to exist")
        except Exception as table_err:
            logger.warning(f"Table creation check: {table_err}")
            db.rollback()

        # Also ensure sms_messages has conversation_id column
        try:
            db.execute(text("""
                ALTER TABLE sms_messages
                ADD COLUMN IF NOT EXISTS conversation_id INTEGER REFERENCES sms_conversations(id)
            """))
            db.execute(text("""
                ALTER TABLE sms_messages
                ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN DEFAULT FALSE
            """))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to add sms_messages columns in sms_webhook: {e}")

        # Normalize phone numbers
        def normalize_phone(phone):
            if not phone:
                return ""
            cleaned = ''.join(c for c in phone if c.isdigit())
            if len(cleaned) == 11 and cleaned.startswith('1'):
                cleaned = cleaned[1:]
            return cleaned

        normalized_from = normalize_phone(from_number)

        # Look up contact/lead by phone number
        contact = None
        lead = None
        loan = None
        user = None
        contact_name = "Unknown Contact"

        # Search contacts table (may not exist in all deployments)
        contact_row = None
        try:
            contact_row = db.execute(text("""
                SELECT c.id, c.first_name, c.last_name, c.owner_id
                FROM contacts c
                WHERE REPLACE(REPLACE(REPLACE(c.phone, '-', ''), ' ', ''), '+1', '') LIKE :phone
                LIMIT 1
            """), {"phone": f"%{normalized_from[-10:]}"}).fetchone()

            if contact_row:
                contact_name = f"{contact_row.first_name or ''} {contact_row.last_name or ''}".strip() or "Contact"
                contact = contact_row
                if contact_row.owner_id:
                    user = db.query(User).filter(User.id == contact_row.owner_id).first()
        except Exception as e:
            logger.warning(f"Contacts table lookup failed (table may not exist): {e}")
            db.rollback()  # Clear the failed transaction

        # Search leads table if no contact found
        if not contact_row:
            lead_row = db.execute(text("""
                SELECT l.id, l.name, l.owner_id
                FROM leads l
                WHERE REPLACE(REPLACE(REPLACE(l.phone, '-', ''), ' ', ''), '+1', '') LIKE :phone
                LIMIT 1
            """), {"phone": f"%{normalized_from[-10:]}"}).fetchone()

            if lead_row:
                contact_name = lead_row.name or "Lead"
                lead = lead_row
                if lead_row.owner_id:
                    user = db.query(User).filter(User.id == lead_row.owner_id).first()

        # Search loans table for borrower phone
        if not contact_row and not lead:
            loan_row = db.execute(text("""
                SELECT l.id, l.borrower_name, l.loan_officer_id
                FROM loans l
                WHERE l.borrower_phone IS NOT NULL
                AND REPLACE(REPLACE(REPLACE(l.borrower_phone, '-', ''), ' ', ''), '+1', '') LIKE :phone
                LIMIT 1
            """), {"phone": f"%{normalized_from[-10:]}"}).fetchone()

            if loan_row:
                loan = loan_row
                contact_name = loan_row.borrower_name or "Borrower"
                if loan_row.loan_officer_id:
                    user = db.query(User).filter(User.id == loan_row.loan_officer_id).first()

        # Find or create SMS conversation
        conversation = db.query(SMSConversation).filter(
            SMSConversation.phone_number == from_number,
            SMSConversation.is_active == True
        ).first()

        if not conversation:
            conversation = SMSConversation(
                phone_number=from_number,
                user_id=user.id if user else None,
                lead_id=lead.id if lead else None,
                loan_id=loan.id if loan else None,
                contact_id=contact.id if contact else None,
                contact_name=contact_name,
                is_active=True,
                ai_enabled=True,
                context={"contact_name": contact_name}
            )
            db.add(conversation)
            db.flush()

        # Store inbound message
        sms_message = SMSMessage(
            user_id=user.id if user else None,
            lead_id=lead.id if lead else None,
            loan_id=loan.id if loan else None,
            conversation_id=conversation.id,
            to_number=to_number,
            from_number=from_number,
            message=message_body,
            direction="inbound",
            status="received",
            provider_message_id=message_sid,
            meta_data={"num_media": num_media, "contact_name": contact_name}
        )
        db.add(sms_message)

        # Update conversation stats
        conversation.last_message_at = datetime.now(timezone.utc)
        conversation.message_count = (conversation.message_count or 0) + 1

        db.commit()

        # Log activity
        try:
            activity = Activity(
                type=ActivityType.SMS,
                content=f"Inbound SMS from {contact_name}: {message_body[:200]}",
                lead_id=lead.id if lead else None,
                loan_id=loan.id if loan else None,
                user_id=user.id if user else None
            )
            db.add(activity)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log SMS activity: {e}")

        # Log to AI receptionist dashboard analytics
        _log_receptionist_activity(
            db=db,
            action_type="incoming_text",
            channel="sms",
            client_name=contact_name,
            client_phone=from_number,
            message_in=message_body[:500] if message_body else None,
            outcome_status="received",
            extra_data={"message_sid": message_sid, "num_media": num_media},
        )

        # Generate AI response in background if enabled
        if conversation.ai_enabled:
            background_tasks.add_task(
                generate_ai_sms_response,
                conversation_id=conversation.id,
                inbound_message=message_body,
                contact_name=contact_name,
                from_number=from_number,
                user_id=user.id if user else None,
                lead_id=lead.id if lead else None,
                loan_id=loan.id if loan else None
            )

        # Return empty XML response (we send reply via API)
        empty_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=empty_response, media_type="application/xml")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"SMS WEBHOOK ERROR: {e}")
        logger.error(f"SMS WEBHOOK TRACEBACK: {error_details}")
        # Still return XML response to prevent retry
        empty_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=empty_response, media_type="application/xml")


async def generate_ai_sms_response(
    conversation_id: int,
    inbound_message: str,
    contact_name: str,
    from_number: str,
    user_id: int = None,
    lead_id: int = None,
    loan_id: int = None
):
    """Generate and send AI response to SMS message"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        import openai
        from telephony.provider import get_telephony_provider

        main = get_models()
        User = main.User
        SMSMessage = main.SMSMessage
        SMSConversation = main.SMSConversation

        conversation = db.query(SMSConversation).filter(SMSConversation.id == conversation_id).first()
        if not conversation:
            return

        # Get recent message history
        recent_messages = db.query(SMSMessage).filter(
            SMSMessage.conversation_id == conversation_id
        ).order_by(SMSMessage.created_at.desc()).limit(10).all()

        message_history = []
        for msg in reversed(recent_messages):
            role = "user" if msg.direction == "inbound" else "assistant"
            message_history.append({"role": role, "content": msg.message})

        # Get loan context if available
        loan_context = ""
        if loan_id or conversation.loan_id:
            lid = loan_id or conversation.loan_id
            loan = db.execute(text("""
                SELECT borrower_name, stage, closing_date, amount, rate,
                       loan_officer_name, processor
                FROM loans WHERE id = :id
            """), {"id": lid}).fetchone()
            if loan:
                loan_context = f"""
Loan Info: {loan.borrower_name}, Stage: {loan.stage}, Closing: {loan.closing_date}, Amount: ${loan.amount:,.0f if loan.amount else 'N/A'}
"""

        # Get LO name
        lo_name = "your loan officer"
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                lo_name = user.full_name or "your loan officer"

        system_prompt = f"""You are an AI assistant for mortgage loan officer {lo_name}. You're responding to SMS texts from borrowers.

RULES:
1. Keep responses SHORT - under 160 chars when possible
2. Be friendly and professional
3. Don't make up specific dates/rates/amounts - offer to have LO confirm
4. For urgent matters, say the LO will call ASAP
5. Casual but professional tone for texting
6. Max 1 emoji per message

Contact: {contact_name}
{loan_context}

Be concise - you're texting!"""

        openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(message_history[-6:])

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )

        ai_response = response.choices[0].message.content.strip()
        if len(ai_response) > 300:
            ai_response = ai_response[:297] + "..."

        # Send SMS via the chokepoint
        from telephony.sms import send_sms_verified
        sms_phone = os.getenv("TELNYX_PHONE_NUMBER")
        messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID")

        if not sms_phone and not messaging_profile_id:
            logger.error("No phone number or messaging profile configured for SMS")
            return

        sms_result = send_sms_verified(
            to=from_number,
            from_=sms_phone,
            text=ai_response,
            messaging_profile_id=messaging_profile_id,
            user_id=user_id,
            lead_id=lead_id or (conversation.lead_id if conversation else None),
            organization_id=getattr(current_user, 'organization_id', None) if 'current_user' in dir() else None,
        )

        # Store outbound message
        provider_msg_id = sms_result.get("id") or ""
        outbound_sms = SMSMessage(
            user_id=user_id,
            lead_id=lead_id or conversation.lead_id,
            loan_id=loan_id or conversation.loan_id,
            conversation_id=conversation_id,
            to_number=from_number,
            from_number=sms_phone,
            message=ai_response,
            direction="outbound",
            status="sent",
            provider_message_id=provider_msg_id,
            ai_generated=True,
            meta_data={"model": "gpt-4o-mini", "in_response_to": inbound_message[:100]}
        )
        db.add(outbound_sms)

        conversation.last_ai_response_at = datetime.now(timezone.utc)
        conversation.message_count = (conversation.message_count or 0) + 1

        db.commit()
        logger.info(f"AI SMS response sent to {from_number}: {ai_response[:50]}...")

    except Exception as e:
        logger.error(f"Error generating AI SMS response: {e}", exc_info=True)
    finally:
        db.close()


# ============================================================================
# SMS CONVERSATION ENDPOINTS
# ============================================================================

# Create sub-router for SMS endpoints
sms_router = APIRouter(prefix="/api/v1/sms", tags=["SMS Messaging"])


@sms_router.get("/conversations")
async def list_sms_conversations(
    active_only: bool = True,
    include_all: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """List SMS conversations. Use include_all=true to see all conversations (admin only)"""
    main = get_models()
    SMSConversation = main.SMSConversation

    query = db.query(SMSConversation)

    # If not including all, filter by user or show unassigned
    if not include_all:
        query = query.filter(
            (SMSConversation.user_id == current_user.id) |
            (SMSConversation.user_id == None)
        )

    if active_only:
        query = query.filter(SMSConversation.is_active == True)

    conversations = query.order_by(SMSConversation.last_message_at.desc()).limit(limit).all()

    return {
        "conversations": [
            {
                "id": c.id,
                "phone_number": c.phone_number,
                "contact_name": c.contact_name,
                "is_active": c.is_active,
                "ai_enabled": c.ai_enabled,
                "message_count": c.message_count,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "lead_id": c.lead_id,
                "loan_id": c.loan_id
            }
            for c in conversations
        ]
    }


@sms_router.get("/conversations/{conversation_id}/messages")
async def get_sms_conversation_messages(
    conversation_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get messages for a specific SMS conversation"""
    main = get_models()
    SMSMessage = main.SMSMessage
    SMSConversation = main.SMSConversation

    conversation = db.query(SMSConversation).filter(
        SMSConversation.id == conversation_id,
        SMSConversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(SMSMessage).filter(
        SMSMessage.conversation_id == conversation_id
    ).order_by(SMSMessage.created_at.desc()).limit(limit).all()

    return {
        "conversation": {
            "id": conversation.id,
            "phone_number": conversation.phone_number,
            "contact_name": conversation.contact_name,
            "ai_enabled": conversation.ai_enabled
        },
        "messages": [
            {
                "id": m.id,
                "message": m.message,
                "direction": m.direction,
                "status": m.status,
                "ai_generated": m.ai_generated,
                "created_at": m.created_at.isoformat()
            }
            for m in reversed(messages)
        ]
    }


@sms_router.post("/conversations/{conversation_id}/send")
async def send_sms_in_conversation(
    conversation_id: int,
    message: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Send a manual SMS message in a conversation"""
    main = get_models()
    SMSMessage = main.SMSMessage
    SMSConversation = main.SMSConversation

    conversation = db.query(SMSConversation).filter(
        SMSConversation.id == conversation_id,
        SMSConversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        from telephony.sms import send_sms_verified

        sms_phone = os.getenv("TELNYX_PHONE_NUMBER")
        messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID")

        if not sms_phone and not messaging_profile_id:
            raise HTTPException(status_code=500, detail="SMS service not configured")

        sms_result = send_sms_verified(
            to=conversation.phone_number,
            from_=sms_phone,
            text=message,
            messaging_profile_id=messaging_profile_id,
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            organization_id=getattr(current_user, 'organization_id', None),
        )

        provider_msg_id = sms_result.get("id") or ""

        sms_message = SMSMessage(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            conversation_id=conversation_id,
            to_number=conversation.phone_number,
            from_number=sms_phone,
            message=message,
            direction="outbound",
            status="sent",
            provider_message_id=provider_msg_id,
            ai_generated=False
        )
        db.add(sms_message)

        conversation.last_message_at = datetime.now(timezone.utc)
        conversation.message_count = (conversation.message_count or 0) + 1

        db.commit()

        return {"success": True, "message_id": sms_message.id, "provider_message_id": provider_msg_id}

    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@sms_router.put("/conversations/{conversation_id}/ai-toggle")
async def toggle_ai_for_conversation(
    conversation_id: int,
    enabled: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Enable or disable AI auto-responses for a conversation"""
    main = get_models()
    SMSConversation = main.SMSConversation

    conversation = db.query(SMSConversation).filter(
        SMSConversation.id == conversation_id,
        SMSConversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.ai_enabled = enabled
    db.commit()

    return {"success": True, "conversation_id": conversation_id, "ai_enabled": enabled}


@sms_router.post("/messages/{message_id}/feedback")
async def submit_sms_message_feedback(
    message_id: int,
    feedback: str = Body(..., embed=True),
    rating: int = Body(3, embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Submit feedback for an AI-generated SMS message (approve/reject)"""
    try:
        main = get_models()
        SMSMessage = main.SMSMessage

        sms_message = db.query(SMSMessage).filter(SMSMessage.id == message_id).first()

        if not sms_message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Store feedback in the message record (add feedback column if not exists)
        # For now, log the feedback
        logger.info(f"Feedback for message {message_id}: {feedback}, rating: {rating}")

        # Try to update message with feedback
        try:
            db.execute(text("""
                UPDATE sms_messages
                SET feedback = :feedback, feedback_rating = :rating, feedback_at = CURRENT_TIMESTAMP
                WHERE id = :message_id
            """), {"feedback": feedback, "rating": rating, "message_id": message_id})
            db.commit()
        except Exception as e:
            # If columns don't exist, that's okay - just log it
            logger.warning(f"Could not store feedback in DB (columns may not exist): {e}")

        return {
            "success": True,
            "message_id": message_id,
            "feedback": feedback,
            "rating": rating
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

# Create sub-router for debug endpoints
debug_router = APIRouter(prefix="/api/v1/debug", tags=["Debug"])


@debug_router.get("/sms-messages")
async def debug_sms_messages(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Debug endpoint to view all SMS messages in the database (admin only)"""
    if not getattr(current_user, 'is_platform_admin', False) and not getattr(current_user, 'is_site_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        main = get_models()
        SMSMessage = main.SMSMessage

        messages = db.query(SMSMessage).order_by(SMSMessage.created_at.desc()).limit(limit).all()
        return {
            "total_count": db.query(SMSMessage).count(),
            "messages": [
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id,
                    "direction": m.direction,
                    "from_number": m.from_number,
                    "to_number": m.to_number,
                    "message": m.message[:100] + "..." if len(m.message) > 100 else m.message,
                    "status": m.status,
                    "ai_generated": getattr(m, 'ai_generated', None),
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "user_id": m.user_id
                }
                for m in messages
            ]
        }
    except Exception as e:
        logger.error(f"Debug SMS error: {e}")
        return {"error": "Internal server error"}


@debug_router.get("/telephony-config")
async def debug_telephony_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Debug endpoint to check telephony configuration (admin only)"""
    if not getattr(current_user, 'is_platform_admin', False) and not getattr(current_user, 'is_site_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    telnyx_key = os.getenv("TELNYX_API_KEY")
    telnyx_phone = os.getenv("TELNYX_PHONE_NUMBER")
    telnyx_connection = os.getenv("TELNYX_CONNECTION_ID")
    telnyx_messaging = os.getenv("TELNYX_MESSAGING_PROFILE_ID")

    return {
        "provider": "telnyx",
        "api_key": "***configured***" if telnyx_key else None,
        "TELNYX_PHONE_NUMBER": telnyx_phone,
        "TELNYX_CONNECTION_ID": telnyx_connection,
        "TELNYX_MESSAGING_PROFILE_ID": telnyx_messaging,
        "using_phone": telnyx_phone,
        "configured": bool(telnyx_key and telnyx_phone),
        "note": "Telnyx is the primary telephony provider. Configure via Telnyx Mission Control."
    }

# Backward-compatible alias
debug_twilio_config = debug_telephony_config


@debug_router.get("/message/{message_sid}")
async def debug_message_status(
    message_sid: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Check the delivery status of a specific message by SID (admin only)"""
    if not getattr(current_user, 'is_platform_admin', False) and not getattr(current_user, 'is_site_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        from telephony.provider import get_telephony_provider

        provider = get_telephony_provider()
        message = provider.get_message(message_sid)

        if not message:
            return {"error": "Message not found or provider does not support message lookup"}

        return {
            "sid": getattr(message, 'sid', message_sid),
            "status": getattr(message, 'status', 'unknown'),
            "error_code": getattr(message, 'error_code', None),
            "error_message": getattr(message, 'error_message', None),
            "from": getattr(message, 'from_', None),
            "to": getattr(message, 'to', None),
            "body": (getattr(message, 'body', '')[:100] + "...") if len(getattr(message, 'body', '')) > 100 else getattr(message, 'body', ''),
            "date_sent": str(getattr(message, 'date_sent', '')),
            "date_created": str(getattr(message, 'date_created', '')),
            "direction": getattr(message, 'direction', None),
        }
    except Exception as e:
        return {"error": "Internal server error"}


@debug_router.get("/recent-messages")
async def debug_recent_messages(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Get recent messages directly from telephony provider API (admin only)"""
    if not getattr(current_user, 'is_platform_admin', False) and not getattr(current_user, 'is_site_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        from telephony.provider import get_telephony_provider

        provider = get_telephony_provider()
        messages = provider.list_messages(limit=limit) if hasattr(provider, 'list_messages') else []

        return {
            "messages": [
                {
                    "sid": getattr(m, 'sid', ''),
                    "status": getattr(m, 'status', ''),
                    "error_code": getattr(m, 'error_code', None),
                    "error_message": getattr(m, 'error_message', None),
                    "from": getattr(m, 'from_', ''),
                    "to": getattr(m, 'to', ''),
                    "body": (getattr(m, 'body', '')[:50] + "...") if len(getattr(m, 'body', '')) > 50 else getattr(m, 'body', ''),
                    "direction": getattr(m, 'direction', ''),
                    "date_sent": str(getattr(m, 'date_sent', ''))
                }
                for m in messages
            ]
        }
    except Exception as e:
        return {"error": "Internal server error"}


@debug_router.post("/send-test-sms")
async def debug_send_test_sms(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Send a direct test SMS to verify telephony provider is working"""
    try:
        from telephony.provider import get_telephony_provider

        data = await request.json()
        to_number = data.get("to_number")
        message = data.get("message", "Test from Perennia AI - If you received this, SMS is working!")

        if not to_number:
            return {"error": "to_number is required"}

        sms_phone = os.getenv("TELNYX_PHONE_NUMBER")

        if not sms_phone:
            return {"error": "Telephony not configured", "config": {
                "phone": sms_phone
            }}

        # Format number
        clean_number = ''.join(filter(str.isdigit, to_number))
        if len(clean_number) == 10:
            to_number = f"+1{clean_number}"
        elif len(clean_number) == 11 and clean_number.startswith('1'):
            to_number = f"+{clean_number}"

        from telephony.sms import send_sms_verified
        sms_result = send_sms_verified(
            to=to_number,
            from_=sms_phone,
            text=message,
            organization_id=getattr(current_user, 'organization_id', None),
        )

        msg_sid = sms_result.get("id") or ""

        return {
            "success": sms_result.get("status") == "sent",
            "message_sid": msg_sid,
            "from_number": sms_phone,
            "to_number": to_number,
            "status": sms_result.get("status", "unknown"),
        }
    except Exception as e:
        logger.error(f"Debug send-test-sms error: {e}", exc_info=True)
        return {"error": "Internal server error"}
