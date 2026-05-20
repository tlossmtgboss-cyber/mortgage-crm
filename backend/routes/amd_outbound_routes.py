"""
AMD-Enabled Outbound Call Routes
Handles Answering Machine Detection for outbound AI calls.

Supports Telnyx telephony provider (configurable via TELEPHONY_PROVIDER environment variable).

Flow:
1. Initiate call with AMD enabled
2. Provider detects human vs machine
3. AMD callback routes to appropriate handler:
   - Human: Connect to Aria (WebSocket stream)
   - Machine: Play voicemail message (ElevenLabs TTS)
"""

import os
import uuid
import logging
import asyncio
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

# Import from database to avoid circular dependency
from database import get_db

logger = logging.getLogger(__name__)

# Determine telephony provider
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "telnyx").lower()


def _validate_webhook_signature(request: Request, form_data: dict) -> bool:
    """Validate webhook signature. Legacy webhook validator removed -- Telnyx webhook
    validation is handled in telnyx_webhook_routes.py. This function now logs a warning
    and returns True for backward compatibility."""
    logger.info("Webhook signature validation skipped (migrated to Telnyx)")
    return True

# Backward-compatible alias
_validate_twilio_signature = _validate_webhook_signature

router = APIRouter(prefix="/api/v1/voice/amd", tags=["AMD Outbound Calls"])

# API base URL for callbacks
API_BASE_URL = os.getenv("API_URL") or os.getenv("PRODUCTION_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if API_BASE_URL and not API_BASE_URL.startswith("http"):
    API_BASE_URL = f"https://{API_BASE_URL}"

# Default to production domain
if not API_BASE_URL:
    API_BASE_URL = "https://api.perenniaai.com"

# ElevenLabs configuration
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # Aria's voice ID


# =============================================================================
# Pydantic Models
# =============================================================================

class AMDOutboundCallRequest(BaseModel):
    """Request to initiate an AMD-enabled outbound call"""
    to_number: str = Field(..., description="Phone number to call (E.164 format preferred)")
    client_name: str = Field(..., description="Name of person being called")
    purpose: str = Field(..., description="Purpose of the call")
    lo_name: Optional[str] = Field(None, description="Loan officer name")
    agent_id: Optional[str] = Field(None, description="ElevenLabs agent ID for AI connection")
    phone_number_id: Optional[str] = Field(None, description="ElevenLabs phone number ID")
    voicemail_message: Optional[str] = Field(None, description="Custom voicemail message")
    first_message: Optional[str] = Field(None, description="Custom first message for human")


# =============================================================================
# Helper Functions
# =============================================================================

def format_e164(phone: str) -> str:
    """Format phone number to E.164 format"""
    # Remove all non-digit characters except leading +
    if phone.startswith('+'):
        digits = '+' + ''.join(filter(str.isdigit, phone[1:]))
    else:
        digits = ''.join(filter(str.isdigit, phone))

    # Add +1 for US numbers if not present
    if not digits.startswith('+'):
        if len(digits) == 10:
            digits = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith('1'):
            digits = f"+{digits}"

    return digits


async def get_user_telephony_config_legacy(user_id: int, db: Session) -> Optional[Dict]:
    """Get stored telephony config for a user (legacy table: user_twilio_config)"""
    try:
        result = db.execute(text("""
            SELECT subaccount_sid, account_sid, auth_token,
                   phone_number, phone_number_sid
            FROM user_twilio_config  -- Legacy table name
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        if row:
            return {
                "subaccount_sid": row[0],
                "account_sid": row[1] or row[0],  # Use account_sid or subaccount_sid
                "auth_token": row[2],
                "phone_number": row[3],
                "phone_number_sid": row[4],
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching telephony config: {e}")
        # Rollback to clear the failed transaction state
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass
        return None


async def get_user_telnyx_config(user_id: int, db: Session) -> Optional[Dict]:
    """Get stored Telnyx config for a user (or use system defaults)"""
    # First try user-specific config
    try:
        result = db.execute(text("""
            SELECT telnyx_api_key, telnyx_connection_id,
                   telnyx_phone_number, telnyx_messaging_profile_id
            FROM user_twilio_config  -- Legacy table name
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        if row and row[0]:  # If user has Telnyx config
            return {
                "api_key": row[0],
                "connection_id": row[1],
                "phone_number": row[2],
                "messaging_profile_id": row[3],
            }
    except Exception as e:
        logger.debug(f"No user Telnyx config found: {e}")
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass

    # Fall back to system config from environment
    api_key = os.getenv("TELNYX_API_KEY")
    phone_number = os.getenv("TELNYX_PHONE_NUMBER")
    connection_id = os.getenv("TELNYX_CONNECTION_ID")

    if api_key and phone_number:
        return {
            "api_key": api_key,
            "connection_id": connection_id,
            "phone_number": phone_number,
            "messaging_profile_id": os.getenv("TELNYX_MESSAGING_PROFILE_ID"),
        }

    return None


async def get_user_telephony_config(user_id: int, db: Session) -> Optional[Dict]:
    """Get telephony config for user based on current provider"""
    if TELEPHONY_PROVIDER == "telnyx":
        return await get_user_telnyx_config(user_id, db)
    else:
        return await get_user_telephony_config_legacy(user_id, db)

# Backward-compatible alias
get_user_twilio_config = get_user_telephony_config_legacy


def get_elevenlabs_config_sync() -> Optional[Dict]:
    """
    Get ElevenLabs config from environment variables.
    This avoids database queries to non-existent tables.
    """
    system_key = os.getenv("ELEVENLABS_API_KEY")
    if system_key:
        return {
            "api_key": system_key,
            "voice_id": os.getenv("ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_ID),
        }
    return None


async def generate_voicemail_audio(
    text: str,
    api_key: str,
    voice_id: str,
    tracking_id: str,
) -> Optional[str]:
    """
    Generate voicemail audio using ElevenLabs TTS.
    Stores the audio and returns a URL to play it.
    Creates its own database session to avoid transaction issues.
    """
    import httpx
    import base64
    from database import SessionLocal

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg"
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "style": 0.0,
                        "use_speaker_boost": True
                    }
                }
            )

            if response.status_code == 200:
                # Save audio to database (base64 encoded)
                # TODO: Migrate to S3/R2 object storage to avoid DB bloat
                audio_bytes = response.content
                MAX_AUDIO_BYTES = 512 * 1024  # 512KB limit
                if len(audio_bytes) > MAX_AUDIO_BYTES:
                    logger.warning(
                        f"Voicemail audio for {tracking_id} is {len(audio_bytes)} bytes "
                        f"(>{MAX_AUDIO_BYTES}). Truncating. Consider migrating to object storage."
                    )
                    audio_bytes = audio_bytes[:MAX_AUDIO_BYTES]
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                # Create a new session for the background task
                db_session = SessionLocal()
                try:
                    db_session.execute(text("""
                        UPDATE amd_outbound_calls
                        SET voicemail_audio = :audio
                        WHERE id = :tracking_id
                    """), {"audio": audio_base64, "tracking_id": tracking_id})
                    db_session.commit()
                    logger.info(f"Voicemail audio saved for {tracking_id} ({len(audio_base64)} chars)")
                finally:
                    db_session.close()

                # Return URL to serve the audio
                return f"{API_BASE_URL}/api/v1/voice/amd/audio/{tracking_id}"
            else:
                logger.error(f"ElevenLabs TTS failed: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Error generating voicemail audio: {e}")
        return None


def build_default_voicemail_message(client_name: str, lo_name: str, purpose: str) -> str:
    """Build default voicemail message"""
    first_name = client_name.split()[0] if client_name else ""
    greeting = f"Hi {first_name}" if first_name else "Hi"

    return (
        f"{greeting}, this is Aria calling on behalf of {lo_name or 'your loan officer'} "
        f"at CMG Home Loans regarding {purpose}. "
        f"Please give us a call back at your earliest convenience. "
        f"Thank you and have a great day!"
    )


# =============================================================================
# Database Functions
# =============================================================================

def ensure_amd_table_exists(db: Session):
    """Ensure the AMD tracking table exists"""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS amd_outbound_calls (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER,
                call_sid VARCHAR(34) UNIQUE,
                to_number VARCHAR(20),
                from_number VARCHAR(20),
                client_name VARCHAR(255),
                purpose VARCHAR(500),
                lo_name VARCHAR(255),

                -- AMD Results
                amd_status VARCHAR(50),
                answered_by VARCHAR(50),
                machine_detection_duration INTEGER,

                -- Call handling
                handling_method VARCHAR(50),
                elevenlabs_conversation_id VARCHAR(100),

                -- Agent config
                agent_id VARCHAR(100),
                phone_number_id VARCHAR(100),

                -- Voicemail
                voicemail_message TEXT,
                voicemail_audio TEXT,
                voicemail_audio_url VARCHAR(500),
                voicemail_duration INTEGER,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                amd_completed_at TIMESTAMP WITH TIME ZONE,
                call_ended_at TIMESTAMP WITH TIME ZONE,

                -- Status
                status VARCHAR(50) DEFAULT 'initiated'
            )
        """))
        db.commit()
    except Exception as e:
        logger.warning(f"Could not ensure AMD table exists (may already exist): {e}")
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


# =============================================================================
# ENDPOINT 1: Initiate AMD-Enabled Outbound Call
# =============================================================================

@router.post("/outbound-call")
async def initiate_amd_outbound_call(
    request: AMDOutboundCallRequest,
    admin_key: str = None,
    user_email: str = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Initiate outbound call with AMD (Answering Machine Detection).

    Flow:
    1. Create call with MachineDetection enabled via telephony provider
    2. Pre-generate voicemail audio (async)
    3. Provider detects human vs machine
    4. AMD callback routes to appropriate handler
    """
    from telephony.provider import get_telephony_provider

    # Determine user
    user_id = None
    expected_admin_key = os.getenv("ADMIN_API_KEY")
    if expected_admin_key and admin_key and secrets.compare_digest(admin_key, expected_admin_key) and user_email:
        user_result = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email}).fetchone()
        if not user_result:
            raise HTTPException(status_code=404, detail=f"User {user_email} not found")
        user_id = user_result[0]
    else:
        raise HTTPException(status_code=401, detail="Admin key and user_email required")

    # Ensure table exists
    ensure_amd_table_exists(db)

    # Get telephony config based on provider
    telephony_config = await get_user_telephony_config(user_id, db)
    if not telephony_config:
        raise HTTPException(
            status_code=400,
            detail=f"{TELEPHONY_PROVIDER.capitalize()} not configured for this user"
        )

    if TELEPHONY_PROVIDER == "telnyx":
        from_number = telephony_config.get("phone_number")
        account_sid = None
        auth_token = None
        if not from_number:
            raise HTTPException(status_code=400, detail="Incomplete Telnyx configuration")
    else:
        account_sid = telephony_config.get("account_sid")
        auth_token = telephony_config.get("auth_token")
        from_number = telephony_config.get("phone_number")
        if not all([account_sid, auth_token, from_number]):
            raise HTTPException(status_code=400, detail="Incomplete telephony configuration")

    # Format phone number
    to_number = format_e164(request.to_number)

    # Get LO name if not provided
    lo_name = request.lo_name
    if not lo_name:
        user_info = await db.execute(text("SELECT COALESCE(es.full_name, u.email) AS name FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id WHERE u.id = :user_id"), {"user_id": user_id}).fetchone()
        lo_name = user_info[0] if user_info else "your loan officer"

    # Generate tracking ID
    tracking_id = str(uuid.uuid4())

    # Build voicemail message
    voicemail_message = request.voicemail_message or build_default_voicemail_message(
        request.client_name, lo_name, request.purpose
    )

    # Store call tracking info (with provider for multi-provider support)
    await db.execute(text("""
        INSERT INTO amd_outbound_calls (
            id, user_id, to_number, from_number, client_name, purpose, lo_name,
            agent_id, phone_number_id, voicemail_message, status
        ) VALUES (
            :id, :user_id, :to_number, :from_number, :client_name, :purpose, :lo_name,
            :agent_id, :phone_number_id, :voicemail_message, 'initiated'
        )
    """), {
        "id": tracking_id,
        "user_id": user_id,
        "to_number": to_number,
        "from_number": from_number,
        "client_name": request.client_name,
        "purpose": request.purpose,
        "lo_name": lo_name,
        "agent_id": request.agent_id,
        "phone_number_id": request.phone_number_id,
        "voicemail_message": voicemail_message,
    })
    await db.commit()

    logger.info(f"Call tracking record created: {tracking_id} (provider: {TELEPHONY_PROVIDER})")

    # Start voicemail audio generation in background
    elevenlabs_config = get_elevenlabs_config_sync()
    if elevenlabs_config:
        asyncio.create_task(generate_voicemail_audio(
            voicemail_message,
            elevenlabs_config["api_key"],
            elevenlabs_config["voice_id"],
            tracking_id,
        ))

    # Create call with AMD based on provider
    try:
        if TELEPHONY_PROVIDER == "telnyx":
            call_sid = await _initiate_telnyx_amd_call(
                to_number, from_number, tracking_id, db
            )
        else:
            call_sid = await _initiate_legacy_amd_call(
                to_number, from_number, tracking_id, account_sid, auth_token
            )

        # Update with call SID
        await db.execute(text("""
            UPDATE amd_outbound_calls
            SET call_sid = :call_sid, status = 'amd_pending'
            WHERE id = :tracking_id
        """), {"call_sid": call_sid, "tracking_id": tracking_id})
        await db.commit()

        logger.info(f"AMD call initiated: {tracking_id} -> {to_number} (SID: {call_sid})")

        return {
            "success": True,
            "tracking_id": tracking_id,
            "call_sid": call_sid,
            "status": "amd_pending",
            "provider": TELEPHONY_PROVIDER,
            "message": f"AMD-enabled call initiated to {request.client_name} at {to_number}"
        }

    except Exception as e:
        logger.error(f"Failed to initiate AMD call: {e}")
        await db.rollback()
        try:
            await db.execute(text("""
                UPDATE amd_outbound_calls SET status = 'failed' WHERE id = :tracking_id
            """), {"tracking_id": tracking_id})
            await db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update call status: {db_error}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _initiate_legacy_amd_call(
    to_number: str,
    from_number: str,
    tracking_id: str,
    account_sid: str,
    auth_token: str,
) -> str:
    """Initiate AMD-enabled call via legacy telephony path (uses telephony provider)"""
    from telephony.provider import get_telephony_provider

    provider = get_telephony_provider()

    result = provider.place_call(
        to=to_number,
        from_=from_number,
        url=f"{API_BASE_URL}/api/v1/voice/amd/waiting/{tracking_id}",
        status_callback=f"{API_BASE_URL}/api/v1/voice/amd/call-status/{tracking_id}",
        machine_detection="detect",
        machine_detection_timeout=30,
    )

    return result.call_sid if hasattr(result, 'call_sid') else str(result)

# Backward-compatible alias
_initiate_twilio_amd_call = _initiate_legacy_amd_call


async def _initiate_telnyx_amd_call(
    to_number: str,
    from_number: str,
    tracking_id: str,
    db: Session,
) -> str:
    """Initiate AMD-enabled call via Telnyx"""
    from telephony import get_telephony_provider

    provider = get_telephony_provider()

    # Telnyx AMD configuration
    result = provider.place_call(
        to=to_number,
        from_=from_number,
        url=f"{API_BASE_URL}/api/v1/telnyx/texml/waiting/{tracking_id}",
        status_callback=f"{API_BASE_URL}/api/v1/telnyx/webhook",
        timeout=30,
        record=True,
        machine_detection="detect",
        machine_detection_timeout=30,
    )

    if not result.success:
        raise Exception(result.error_message or "Failed to place Telnyx call")

    return result.call_sid


# =============================================================================
# ENDPOINT 2: AMD Status Callback (telephony provider calls this with AMD result)
# =============================================================================

@router.post("/status/{tracking_id}")
async def handle_amd_status(
    tracking_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle AMD callback from telephony provider.

    AnsweredBy values:
    - "human": Human answered
    - "machine_start": Machine detected, didn't wait for beep
    - "machine_end_beep": Machine detected, waited for beep
    - "machine_end_silence": Machine detected via silence
    - "machine_end_other": Machine detected by other means
    - "fax": Fax machine detected
    - "unknown": Could not determine
    """
    from telephony.provider import get_telephony_provider

    form_data = await request.form()
    form_dict = dict(form_data)

    # Validate webhook signature
    if not _validate_webhook_signature(request, form_dict):
        logger.warning(f"Invalid webhook signature on AMD callback for {tracking_id}")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    call_sid = form_data.get("CallSid")
    answered_by = form_data.get("AnsweredBy", "unknown")
    machine_detection_duration = form_data.get("MachineDetectionDuration")

    logger.info(f"AMD Result for {tracking_id}: AnsweredBy={answered_by}, Duration={machine_detection_duration}ms")

    # Get call tracking record
    result = await db.execute(text("""
        SELECT user_id, call_sid, client_name, purpose, lo_name
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    if not result:
        logger.error(f"AMD call tracking not found: {tracking_id}")
        return {"error": "Call not found"}

    user_id = result[0]

    # Determine answered_by category
    if answered_by == "human":
        answered_category = "human"
    elif answered_by.startswith("machine"):
        answered_category = "machine"
    elif answered_by == "fax":
        answered_category = "fax"
    else:
        answered_category = "unknown"

    # Update AMD results
    await db.execute(text("""
        UPDATE amd_outbound_calls
        SET amd_status = :amd_status,
            answered_by = :answered_by,
            machine_detection_duration = :duration,
            amd_completed_at = NOW()
        WHERE id = :tracking_id
    """), {
        "amd_status": answered_by,
        "answered_by": answered_category,
        "duration": int(machine_detection_duration) if machine_detection_duration else None,
        "tracking_id": tracking_id,
    })
    await db.commit()

    # Get telephony provider
    provider = get_telephony_provider()

    # Route based on AMD result
    if answered_category == "human" or answered_category == "unknown":
        # Human or unknown - connect to AI
        logger.info(f"Connecting to AI for {tracking_id} (answered_by: {answered_by})")
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/connect-ai/{tracking_id}"

    elif answered_category == "machine":
        # Voicemail - play message
        logger.info(f"Playing voicemail for {tracking_id} (answered_by: {answered_by})")
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/voicemail/{tracking_id}"

    elif answered_category == "fax":
        # Fax - hangup
        logger.info(f"Fax detected for {tracking_id} - hanging up")
        redirect_url = f"{API_BASE_URL}/api/v1/voice/amd/hangup/{tracking_id}"

    # Update the call to redirect to appropriate handler
    try:
        provider.update_call(call_sid, url=redirect_url)
        logger.info(f"Redirected call {call_sid} to {redirect_url}")
    except Exception as e:
        logger.error(f"Failed to redirect call: {e}")

    return {"status": "processed", "answered_by": answered_by, "action": redirect_url}


# =============================================================================
# ENDPOINT 3: Initial Waiting TwiML (while AMD runs)
# =============================================================================

@router.post("/waiting/{tracking_id}")
@router.get("/waiting/{tracking_id}")
async def amd_waiting_twiml(tracking_id: str):
    """
    TwiML response while AMD is running.
    Plays brief silence to give AMD time to work.
    """
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="3"/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# ENDPOINT 4: Connect to AI (Human Answered)
# =============================================================================

@router.post("/connect-ai/{tracking_id}")
@router.get("/connect-ai/{tracking_id}")
async def connect_to_ai(
    tracking_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    TwiML to connect call to AI via WebSocket stream.
    Uses the existing voice-stream endpoint that powers Aria.
    """
    # Get call info
    result = await db.execute(text("""
        SELECT client_name, to_number, purpose, lo_name
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    if not result:
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

    client_name, to_number, purpose, lo_name = result

    # Update status
    await db.execute(text("""
        UPDATE amd_outbound_calls
        SET status = 'connected', handling_method = 'ai_stream'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    await db.commit()

    # Get domain for WebSocket
    domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'api.perenniaai.com'

    # Build TwiML to connect to voice stream
    # Escape XML special characters
    client_name_safe = (client_name or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    purpose_safe = (purpose or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    lo_name_safe = (lo_name or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{domain}/api/v1/voice/ws/voice-stream">
            <Parameter name="caller_name" value="{client_name_safe}"/>
            <Parameter name="caller_phone" value="{to_number or ''}"/>
            <Parameter name="call_direction" value="outbound"/>
            <Parameter name="call_purpose" value="{purpose_safe}"/>
            <Parameter name="lo_name" value="{lo_name_safe}"/>
            <Parameter name="tracking_id" value="{tracking_id}"/>
        </Stream>
    </Connect>
</Response>"""

    logger.info(f"Connecting call {tracking_id} to AI stream")
    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# ENDPOINT 5: Play Voicemail Message (Machine Answered)
# =============================================================================

@router.post("/voicemail/{tracking_id}")
@router.get("/voicemail/{tracking_id}")
async def play_voicemail_message(
    tracking_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    TwiML to play voicemail message after machine detection.
    Uses ElevenLabs-generated audio if available, falls back to Polly TTS.
    """
    # Get call info
    result = await db.execute(text("""
        SELECT voicemail_message, voicemail_audio, client_name, lo_name, purpose
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    if not result:
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

    voicemail_message, voicemail_audio, client_name, lo_name, purpose = result

    # Update status
    await db.execute(text("""
        UPDATE amd_outbound_calls
        SET status = 'voicemail_left', handling_method = 'voicemail_tts'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    await db.commit()

    # Check if ElevenLabs audio is available
    if voicemail_audio:
        # Use pre-generated audio
        audio_url = f"{API_BASE_URL}/api/v1/voice/amd/audio/{tracking_id}"
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="1"/>
    <Play>{audio_url}</Play>
    <Pause length="1"/>
    <Hangup/>
</Response>"""
    else:
        # Fall back to Polly TTS
        message = voicemail_message or build_default_voicemail_message(client_name, lo_name, purpose)
        # Escape XML special characters
        message_safe = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="1"/>
    <Say voice="Polly.Joanna">{message_safe}</Say>
    <Pause length="1"/>
    <Hangup/>
</Response>"""

    logger.info(f"Playing voicemail for {tracking_id}")
    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# ENDPOINT 6: Serve Voicemail Audio
# =============================================================================

@router.get("/audio/{tracking_id}")
async def serve_voicemail_audio(
    tracking_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Serve the pre-generated ElevenLabs voicemail audio.
    """
    import base64

    result = await db.execute(text("""
        SELECT voicemail_audio FROM amd_outbound_calls WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    if not result or not result[0]:
        raise HTTPException(status_code=404, detail="Audio not found")

    # Decode base64 audio
    audio_data = base64.b64decode(result[0])

    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename=voicemail_{tracking_id}.mp3"}
    )


# =============================================================================
# ENDPOINT 7: Hangup (Fax detected)
# =============================================================================

@router.post("/hangup/{tracking_id}")
@router.get("/hangup/{tracking_id}")
async def hangup_call(
    tracking_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """TwiML to hangup the call (used for fax detection)"""
    await db.execute(text("""
        UPDATE amd_outbound_calls
        SET status = 'hangup_fax', handling_method = 'fax_detected'
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id})
    await db.commit()

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
        media_type="application/xml"
    )


# =============================================================================
# ENDPOINT 8: Call Status Callback
# =============================================================================

@router.post("/call-status/{tracking_id}")
async def handle_call_status(
    tracking_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Handle call status updates from telephony provider"""
    form_data = await request.form()
    form_dict = dict(form_data)

    # Validate webhook signature
    if not _validate_webhook_signature(request, form_dict):
        logger.warning(f"Invalid webhook signature on call-status callback for {tracking_id}")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    call_status = form_data.get("CallStatus")
    call_duration = form_data.get("CallDuration", "0")

    logger.info(f"Call status for {tracking_id}: {call_status}, duration: {call_duration}s")

    if call_status == "completed":
        await db.execute(text("""
            UPDATE amd_outbound_calls
            SET call_ended_at = NOW(),
                voicemail_duration = CASE WHEN answered_by = 'machine' THEN :duration ELSE NULL END,
                status = CASE WHEN status != 'failed' THEN 'completed' ELSE status END
            WHERE id = :tracking_id
        """), {"duration": int(call_duration), "tracking_id": tracking_id})
        await db.commit()

    elif call_status in ["busy", "no-answer", "failed", "canceled"]:
        await db.execute(text("""
            UPDATE amd_outbound_calls
            SET call_ended_at = NOW(), status = :status
            WHERE id = :tracking_id
        """), {"status": call_status, "tracking_id": tracking_id})
        await db.commit()

    return {"status": "ok"}


# =============================================================================
# ENDPOINT 9: Get Call Status
# =============================================================================

@router.get("/call/{tracking_id}")
async def get_call_status(
    tracking_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """Get the status of an AMD-enabled call"""
    result = await db.execute(text("""
        SELECT id, call_sid, to_number, client_name, purpose,
               amd_status, answered_by, handling_method, status,
               created_at, amd_completed_at, call_ended_at
        FROM amd_outbound_calls
        WHERE id = :tracking_id
    """), {"tracking_id": tracking_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "tracking_id": result[0],
        "call_sid": result[1],
        "to_number": result[2],
        "client_name": result[3],
        "purpose": result[4],
        "amd_status": result[5],
        "answered_by": result[6],
        "handling_method": result[7],
        "status": result[8],
        "created_at": result[9].isoformat() if result[9] else None,
        "amd_completed_at": result[10].isoformat() if result[10] else None,
        "call_ended_at": result[11].isoformat() if result[11] else None,
    }
