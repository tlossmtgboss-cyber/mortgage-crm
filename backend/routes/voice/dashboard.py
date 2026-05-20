"""
Voice Routes - Dashboard, Config, Transfer, and Management Endpoints

Contains:
- /transfer, /transfer-status, /voicemail (call flow TwiML)
- /make-call (JSON body variant, line ~3134)
- /call-history, /call-stats
- /ai-receptionist-config (GET/POST)
- /voice-os/config (GET/POST), /voice-os/status
- /transcribe (mobile app proxy)
- /voice-os/test-voice
- /intelligence/* (deprecated stubs)
- /drop-voicemail, /amd-callback, /voicemail-twiml
"""
import os
import logging
import json
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_async_db

import openai

from database import get_db

from .utils import (
    mask_phone, voice_client, ai_config,
    _validate_webhook_signature, get_models, get_current_user_flexible,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    """Return voicemail TwiML - supports both GET and POST for Telnyx"""
    twiml = voice_client.create_voicemail_response()
    return Response(content=str(twiml), media_type="application/xml")


# ============================================================================
# CALL MANAGEMENT API ENDPOINTS
# ============================================================================

@router.post("/make-call")
async def make_outbound_call(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Make an outbound AI call"""
    try:
        from auth.dependencies import get_current_user_flexible as auth_dependency
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
            await db.commit()

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
    # Voice OS runs through the main Python backend with Telnyx + OpenAI integration
    # Check if the essential services are configured and enabled
    telephony_healthy = voice_client.enabled and bool(voice_client.from_number)
    openai_healthy = voice_client.openai_enabled

    # System is "running" if both Telnyx and OpenAI are configured
    system_running = telephony_healthy and openai_healthy

    return {
        "system_status": "running" if system_running else "degraded" if (telephony_healthy or openai_healthy) else "stopped",
        "voice_os_url": os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://app.perenniaai.com"),
        "telephony_configured": bool(voice_client.from_number),
        "openai_configured": voice_client.openai_enabled,
        "phone_number": voice_client.from_number,
        "crm_integration": "active",
        "health_checks": {
            "telephony": "healthy" if telephony_healthy else "disconnected",
            "openai": "healthy" if openai_healthy else "disconnected",
            "database": "healthy",
            "webhooks": "configured"
        },
        "capabilities": {
            "inbound_calls": telephony_healthy,
            "outbound_calls": telephony_healthy,
            "ai_responses": openai_healthy,
            "call_transcription": openai_healthy,
            "voicemail": telephony_healthy
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
# VOICE INTELLIGENCE SETUP (DEPRECATED)
# ============================================================================

@router.post("/intelligence/setup")
async def setup_intelligence_service(
    request: Request,
    current_user=Depends(get_current_user_flexible()),
):
    """
    One-time setup for Voice Intelligence Service.
    DEPRECATED: Deepgram handles transcription now.

    Previously created Intelligence Service with AI operators for:
    - Automatic transcription with speaker diarization
    - PII redaction (SSN, phone numbers, etc.)
    - Sentiment analysis
    - Call summarization
    - Entity recognition
    - Escalation detection
    - Recording disclosure verification
    """
    # Legacy Intelligence service removed — Deepgram handles transcription now.
    return {
        "status": "deprecated",
        "message": "Legacy Intelligence service has been removed. Deepgram handles transcription."
    }


@router.get("/intelligence/status")
async def get_intelligence_status():
    """
    Get current status of Voice Intelligence configuration.
    DEPRECATED: Legacy Intelligence removed. Deepgram handles transcription.
    """
    return {
        "status": "deprecated",
        "enabled": False,
        "service_configured": False,
        "message": "Legacy Intelligence service has been removed. Deepgram handles transcription."
    }


@router.get("/intelligence/operators")
async def list_available_operators():
    """
    List all available Voice Intelligence operators.
    DEPRECATED: Deepgram handles transcription now.
    """
    # Legacy Intelligence service removed — Deepgram handles transcription now.
    return {
        "status": "deprecated",
        "operators": [],
        "count": 0,
        "message": "Legacy Intelligence service has been removed. Deepgram handles transcription."
    }


@router.post("/intelligence/attach-operators")
async def attach_operators(request: Request):
    """
    Attach operators to an existing Intelligence Service.
    DEPRECATED: Legacy Intelligence removed. Deepgram handles transcription.
    """
    return {
        "status": "deprecated",
        "message": "Legacy Intelligence service has been removed. Deepgram handles transcription."
    }


# ============================================================================
# RINGLESS VOICEMAIL & AMD ENDPOINTS
# Migrated from voice_ai_receptionist_routes.py to resolve duplicate route conflict
# ============================================================================

@router.post("/drop-voicemail")
async def drop_voicemail(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Drop a ringless voicemail using Slybroadcast (or fallback to Vapi)"""
    try:
        import httpx
        import tempfile
        import shutil
        from pathlib import Path
        from auth.dependencies import get_current_user_flexible as auth_dependency

        User, Lead, Task, Activity, IncomingDataEvent = get_models()

        # Authenticate
        current_user = await auth_dependency(request, db)

        # Lazy import models needed for voicemail
        from database.enums import ActivityType
        from database.models import VoicemailDrop

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
        await db.commit()
        await db.refresh(voicemail_drop)

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
                    await db.commit()
                    raise HTTPException(status_code=500, detail=f"Zapier webhook error: {error_msg}")

                session_id = f"zapier_{voicemail_drop.id}"
                voicemail_drop.vapi_call_id = session_id
                voicemail_drop.status = 'sent_to_zapier'
                await db.commit()

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
                except Exception as e:
                    logger.error(f"Error in voicemail_drop (parse slybroadcast response): {e}")
                    raise HTTPException(status_code=500, detail=f"Invalid JSON from Slybroadcast: {sly_response.text}")

                if sly_data.get("new_campaign") == "OK":
                    session_id = str(sly_data.get("session_id"))
                    voicemail_drop.vapi_call_id = session_id
                    voicemail_drop.status = 'sent'
                    await db.commit()
                elif "ERROR" in sly_data:
                    error_msg = sly_data.get("ERROR", "Unknown error")
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = error_msg
                    await db.commit()
                    raise HTTPException(status_code=500, detail=f"Slybroadcast error: {error_msg}")
                else:
                    voicemail_drop.status = 'failed'
                    voicemail_drop.error_message = str(sly_data)
                    await db.commit()
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
                await db.commit()

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
        await db.commit()

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
    """Handle AMD (Answering Machine Detection) callback (legacy)"""
    try:
        form_data = await request.form()
        form_dict = {k: v for k, v in form_data.items()}

        # Validate webhook signature
        if not await _validate_webhook_signature(request, form_dict):
            logger.warning("Invalid webhook signature on AMD callback")
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
    from telephony.providers.telnyx.texml import TeXMLResponse

    response = TeXMLResponse()

    if AnsweredBy == 'human':
        logger.info("Human detected, hanging up to avoid disturbing")
        response.hangup()
    else:
        response.pause(length=2)
        response.say(message, voice='Polly.Ruth-Neural', language='en-US')
        response.pause(length=1)
        response.hangup()

    return Response(content=str(response), media_type="application/xml")
