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
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/elevenlabs", tags=["ElevenLabs"])

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


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


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
            "api_key": request.api_key,
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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

        return {
            "data": {
                "configured": True,
                "api_key": result[0],
                "voice_id": result[1],
                "settings": result[2] or {}
            }
        }

    except Exception as e:
        logger.warning(f"Could not get ElevenLabs config: {e}")
        return {"data": {"configured": False}}
