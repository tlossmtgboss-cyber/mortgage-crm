"""
ElevenLabs Integration Routes

Manages ElevenLabs API key storage, voice selection, and TTS settings
for the AI Receptionist feature.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import secrets
import httpx

import base64
import hashlib
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/elevenlabs", tags=["ElevenLabs"])


# =============================================================================
# API Key Encryption Helpers
# =============================================================================

def _get_fernet() -> Fernet:
    """Get Fernet cipher using SECRET_KEY from environment."""
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise ValueError("SECRET_KEY environment variable not configured")
    # Derive a valid 32-byte Fernet key from SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for storage."""
    return _get_fernet().encrypt(api_key.encode()).decode()


def _decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key from storage."""
    try:
        return _get_fernet().decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        # If decryption fails, key may be stored in plaintext (pre-migration)
        # Return as-is so existing keys still work
        logger.error(f"Error in _decrypt_api_key: {e}")
        return encrypted_key


def _mask_api_key(api_key: str) -> str:
    """Mask API key for display: show first 4 and last 4 chars."""
    if len(api_key) <= 12:
        return api_key[:2] + "..." + api_key[-2:]
    return api_key[:4] + "..." + api_key[-4:]

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy import text


def get_db():
    """Get database session."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
# =============================================================================
# Pydantic Models
# =============================================================================

class ConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="ElevenLabs API key")


class VoiceSettings(BaseModel):
    voice_id: str = Field(..., description="ElevenLabs voice ID")
    settings: Optional[Dict[str, Any]] = Field(default_factory=lambda: {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0,
        "use_speaker_boost": True
    })


class TestRequest(BaseModel):
    voice_id: str
    text: str = Field(..., max_length=500)
    settings: Optional[Dict[str, Any]] = None


# =============================================================================
# Helper Functions
# =============================================================================

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


async def verify_api_key(api_key: str) -> Dict:
    """Verify ElevenLabs API key and get subscription info."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ELEVENLABS_API_URL}/user/subscription",
            headers={"xi-api-key": api_key}
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid API key")
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to verify API key")


async def get_voices(api_key: str) -> List[Dict]:
    """Get available voices from ElevenLabs."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers={"xi-api-key": api_key}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("voices", [])
        else:
            logger.error(f"Failed to fetch voices: {response.status_code}")
            return []


async def generate_audio(api_key: str, voice_id: str, text: str, settings: Dict) -> bytes:
    """Generate audio using ElevenLabs TTS."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": settings.get("stability", 0.5),
                    "similarity_boost": settings.get("similarity_boost", 0.75),
                    "style": settings.get("style", 0),
                    "use_speaker_boost": settings.get("use_speaker_boost", True)
                }
            }
        )
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to generate audio: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Failed to generate audio")


def get_user_id(current_user) -> int:
    """Extract user ID from current_user object."""
    if isinstance(current_user, dict):
        return current_user.get("user_id") or current_user.get("id")
    return getattr(current_user, "id", None)


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get ElevenLabs connection status for current user."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Check for existing config
        result = db.execute(text("""
            SELECT api_key, voice_id, settings, subscription_tier,
                   character_limit, character_count, created_at, updated_at
            FROM user_elevenlabs_config
            WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if result and result[0]:  # Has API key
            return {
                "data": {
                    "connected": True,
                    "selected_voice_id": result[1],
                    "settings": result[2] if result[2] else {},
                    "subscription_tier": result[3],
                    "character_limit": result[4],
                    "character_count": result[5],
                    "connected_at": result[6].isoformat() if result[6] else None
                }
            }
        else:
            return {"data": {"connected": False}}

    except Exception as e:
        logger.warning(f"Could not fetch ElevenLabs status: {e}")
        # Table might not exist, return disconnected
        return {"data": {"connected": False}}


@router.post("/connect")
async def connect(
    request: ConnectRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Connect ElevenLabs account with API key."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Verify API key with ElevenLabs
        subscription = await verify_api_key(request.api_key)

        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_elevenlabs_config (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                api_key VARCHAR(255) NOT NULL,
                voice_id VARCHAR(100),
                settings JSONB DEFAULT '{}',
                subscription_tier VARCHAR(50),
                character_limit INTEGER,
                character_count INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))

        # Encrypt API key before storing
        encrypted_key = _encrypt_api_key(request.api_key)

        # Upsert config
        db.execute(text("""
            INSERT INTO user_elevenlabs_config
                (user_id, api_key, subscription_tier, character_limit, character_count, created_at, updated_at)
            VALUES
                (:user_id, :api_key, :tier, :char_limit, :char_count, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                api_key = :api_key,
                subscription_tier = :tier,
                character_limit = :char_limit,
                character_count = :char_count,
                updated_at = NOW()
        """), {
            "user_id": user_id,
            "api_key": encrypted_key,
            "tier": subscription.get("tier"),
            "char_limit": subscription.get("character_limit"),
            "char_count": subscription.get("character_count")
        })
        db.commit()

        logger.info(f"User {user_id} connected ElevenLabs account")

        return {
            "data": {
                "connected": True,
                "subscription_tier": subscription.get("tier"),
                "character_limit": subscription.get("character_limit"),
                "character_count": subscription.get("character_count")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to connect ElevenLabs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect ElevenLabs account."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_elevenlabs_config WHERE user_id = :user_id
        """), {"user_id": user_id})
        db.commit()

        logger.info(f"User {user_id} disconnected ElevenLabs account")
        return {"data": {"disconnected": True}}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to disconnect ElevenLabs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/voices")
async def list_voices(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available voices from ElevenLabs."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get API key
        result = db.execute(text("""
            SELECT api_key FROM user_elevenlabs_config WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result or not result[0]:
            raise HTTPException(status_code=400, detail="ElevenLabs not connected")

        voices = await get_voices(result[0])

        # Format voices for frontend
        formatted_voices = [
            {
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "category": v.get("category"),
                "description": v.get("description"),
                "preview_url": v.get("preview_url"),
                "labels": v.get("labels", {})
            }
            for v in voices
        ]

        return {"data": {"voices": formatted_voices}}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch voices: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/settings")
async def update_settings(
    request: VoiceSettings,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update voice selection and settings."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        import json
        db.execute(text("""
            UPDATE user_elevenlabs_config
            SET voice_id = :voice_id,
                settings = :settings::jsonb,
                updated_at = NOW()
            WHERE user_id = :user_id
        """), {
            "user_id": user_id,
            "voice_id": request.voice_id,
            "settings": json.dumps(request.settings or {})
        })
        db.commit()

        logger.info(f"User {user_id} updated ElevenLabs settings")
        return {"data": {"updated": True}}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test")
async def test_voice(
    request: TestRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test voice synthesis and return audio."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get API key
        result = db.execute(text("""
            SELECT api_key FROM user_elevenlabs_config WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result or not result[0]:
            raise HTTPException(status_code=400, detail="ElevenLabs not connected")

        settings = request.settings or {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0,
            "use_speaker_boost": True
        }

        audio_content = await generate_audio(
            result[0],
            request.voice_id,
            request.text,
            settings
        )

        return Response(
            content=audio_content,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=test.mp3"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test voice: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/config")
async def get_config(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get ElevenLabs configuration for AI Receptionist use."""
    user_id = get_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT api_key, voice_id, settings
            FROM user_elevenlabs_config
            WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result or not result[0]:
            return {"data": {"configured": False}}

        # Decrypt and mask key — never return raw key to frontend
        decrypted_key = _decrypt_api_key(result[0])
        return {
            "data": {
                "configured": True,
                "api_key_masked": _mask_api_key(decrypted_key),
                "voice_id": result[1],
                "settings": result[2] or {}
            }
        }

    except Exception as e:
        logger.warning(f"Could not get ElevenLabs config: {e}")
        return {"data": {"configured": False}}


# =============================================================================
# Conversational AI - Outbound Calls
# =============================================================================

class OutboundCallRequest(BaseModel):
    """Request to make an outbound AI call via ElevenLabs"""
    to_number: str = Field(..., description="Phone number to call (E.164 format)")
    client_name: str = Field(..., description="Name of the person being called")
    purpose: str = Field(..., description="Purpose of the call")
    lo_name: Optional[str] = Field(None, description="Loan officer name")
    first_message: Optional[str] = Field(None, description="Custom first message")
    use_amd: bool = Field(False, description="Enable AMD (Answering Machine Detection) to detect voicemail vs human")
    voicemail_message: Optional[str] = Field(None, description="Custom voicemail message if AMD detects machine")


class AgentConfig(BaseModel):
    """Configuration for creating an ElevenLabs agent"""
    name: str = Field(..., description="Agent name")
    voice_id: str = Field(..., description="ElevenLabs voice ID to use")
    system_prompt: str = Field(..., description="System prompt for the agent")
    first_message: str = Field(..., description="First message when call connects")


@router.get("/agents")
async def list_agents(
    admin_key: str = None,
    user_email: str = None,
    current_user=None,
    db: Session = Depends(get_db)
):
    """List ElevenLabs Conversational AI agents."""
    # Get API key
    api_key = await _get_elevenlabs_api_key(admin_key, user_email, current_user, db)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ELEVENLABS_API_URL}/convai/agents",
                headers={"xi-api-key": api_key}
            )
            if response.status_code == 200:
                return {"data": response.json()}
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/agents")
async def create_agent(
    config: AgentConfig,
    admin_key: str = None,
    user_email: str = None,
    current_user=None,
    db: Session = Depends(get_db)
):
    """Create an ElevenLabs Conversational AI agent."""
    api_key = await _get_elevenlabs_api_key(admin_key, user_email, current_user, db)

    agent_payload = {
        "name": config.name,
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": config.system_prompt
                },
                "first_message": config.first_message,
                "language": "en"
            },
            "tts": {
                "voice_id": config.voice_id
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/convai/agents/create",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json=agent_payload
            )
            if response.status_code in [200, 201]:
                return {"data": response.json()}
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/phone-numbers")
async def list_phone_numbers(
    admin_key: str = None,
    user_email: str = None,
    current_user=None,
    db: Session = Depends(get_db)
):
    """List phone numbers registered with ElevenLabs."""
    api_key = await _get_elevenlabs_api_key(admin_key, user_email, current_user, db)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ELEVENLABS_API_URL}/convai/phone-numbers",
                headers={"xi-api-key": api_key}
            )
            if response.status_code == 200:
                return {"data": response.json()}
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class ImportTelephonyNumberRequest(BaseModel):
    """Request body for importing a phone number — keeps secrets out of query params.

    Note: Field names 'twilio_account_sid' and 'twilio_auth_token' are required by
    the ElevenLabs Conversational AI API — these are external API field names, not ours.
    """
    phone_number: str = Field(..., description="Phone number to import")
    twilio_account_sid: str = Field(..., description="Telephony provider Account SID (required by ElevenLabs API)")
    twilio_auth_token: str = Field(..., description="Telephony provider Auth Token (required by ElevenLabs API)")
    label: str = Field("The Tim Loss Team", description="Label for this number")


# Route path matches ElevenLabs API naming convention (external requirement)
@router.post("/phone-numbers/import-twilio")
async def import_telephony_number(
    request_body: ImportTelephonyNumberRequest,
    admin_key: str = None,
    user_email: str = None,
    current_user=None,
    db: Session = Depends(get_db)
):
    """Import a phone number into ElevenLabs for Conversational AI."""
    api_key = await _get_elevenlabs_api_key(admin_key, user_email, current_user, db)

    # ElevenLabs API requires "twilio_config" key — external API field name
    payload = {
        "phone_number": request_body.phone_number,
        "label": request_body.label,
        "twilio_config": {
            "account_sid": request_body.twilio_account_sid,
            "auth_token": request_body.twilio_auth_token
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/convai/phone-numbers/create",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json=payload
            )
            if response.status_code in [200, 201]:
                return {"data": response.json()}
            else:
                logger.error(f"Failed to import phone number: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import phone number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/outbound-call")
async def make_outbound_call(
    request: OutboundCallRequest,
    agent_id: str = None,
    phone_number_id: str = None,
    admin_key: str = None,
    user_email: str = None,
    current_user=None,
    db: Session = Depends(get_db)
):
    """
    Make an outbound AI call using ElevenLabs Conversational AI.

    Requires:
    - ElevenLabs API key configured
    - An agent_id (create one via /agents endpoint)
    - A phone_number_id (import phone number via /phone-numbers/import-twilio — ElevenLabs API path)

    Optional:
    - use_amd=true: Enable AMD (Answering Machine Detection) to detect voicemail vs human
      - Human answers: Connects to AI conversation
      - Voicemail detected: Plays TTS message using Aria's voice
    """
    # If AMD is enabled, redirect to AMD flow
    if request.use_amd:
        from routes.amd_outbound_routes import initiate_amd_outbound_call, AMDOutboundCallRequest

        amd_request = AMDOutboundCallRequest(
            to_number=request.to_number,
            client_name=request.client_name,
            purpose=request.purpose,
            lo_name=request.lo_name,
            agent_id=agent_id,
            phone_number_id=phone_number_id,
            voicemail_message=request.voicemail_message,
            first_message=request.first_message
        )
        return await initiate_amd_outbound_call(
            request=amd_request,
            admin_key=admin_key,
            user_email=user_email,
            db=db
        )

    api_key = await _get_elevenlabs_api_key(admin_key, user_email, current_user, db)

    # Format phone number
    to_number = request.to_number
    if not to_number.startswith('+'):
        to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

    # Build conversation initiation data
    first_name = request.client_name.split()[0] if request.client_name else "there"
    lo_name = request.lo_name or "your loan officer"

    conversation_data = {
        "dynamic_variables": {
            "client_name": request.client_name,
            "first_name": first_name,
            "lo_name": lo_name,
            "purpose": request.purpose
        }
    }

    if request.first_message:
        conversation_data["first_message"] = request.first_message

    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": conversation_data
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/convai/twilio/outbound-call",  # ElevenLabs API endpoint path
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json=payload
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    "success": True,
                    "data": result,
                    "message": f"AI call initiated to {request.client_name} at {to_number}"
                }
            else:
                logger.error(f"ElevenLabs outbound call failed: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to make outbound call: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _get_elevenlabs_api_key(admin_key: str, user_email: str, current_user, db: Session) -> str:
    """Get ElevenLabs API key for the specified user."""
    user_id = None

    expected_admin_key = os.getenv("ADMIN_API_KEY")
    if expected_admin_key and admin_key and secrets.compare_digest(admin_key, expected_admin_key) and user_email:
        # Admin mode - look up user by email
        user_result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email}).fetchone()
        if not user_result:
            raise HTTPException(status_code=404, detail=f"User {user_email} not found")
        user_id = user_result[0]
    elif current_user:
        user_id = get_user_id(current_user)
    else:
        # Try to use system-wide ElevenLabs API key
        system_key = os.getenv("ELEVENLABS_API_KEY")
        if system_key:
            return system_key
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get user's ElevenLabs API key
    result = db.execute(text("""
        SELECT api_key FROM user_elevenlabs_config WHERE user_id = :user_id
    """), {"user_id": user_id}).fetchone()

    if not result or not result[0]:
        # Fall back to system key
        system_key = os.getenv("ELEVENLABS_API_KEY")
        if system_key:
            return system_key
        raise HTTPException(status_code=400, detail="ElevenLabs not configured for this user")

    return _decrypt_api_key(result[0])
