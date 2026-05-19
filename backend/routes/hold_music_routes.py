"""
Hold Music Routes
Manage hold music library for call queues, transfers, and conferences
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
import logging
import os
import json

from database import get_db
from db import get_async_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/hold-music", tags=["hold-music"])


def _validate_audio_url(url: str) -> bool:
    """Validate audio URL is safe for redirect (no open redirect / SSRF)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        # Must be HTTPS
        if parsed.scheme != "https":
            return False
        # Block private/internal IPs
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", ""):
            return False
        if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
            return False
        if host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31:
            return False
        return True
    except Exception as e:
        logger.error(f"Error in _validate_audio_url: {e}")
        return False


def safe_isoformat(dt_value) -> Optional[str]:
    """Safely convert datetime to ISO format string, handling both datetime objects and strings"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        return dt_value  # Already a string (SQLite returns strings)
    if hasattr(dt_value, 'isoformat'):
        return dt_value.isoformat()
    return str(dt_value)


async def get_current_user_optional(request: Request):
    """
    Optional authentication - returns user if authenticated, None otherwise.
    Lazy imports from main to avoid circular imports.

    Uses its own short-lived sync session so this dependency does not pin a
    shared `db` parameter; route handlers are free to use `get_async_db()`.
    """
    try:
        from auth.dependencies import get_current_user_flexible as auth_func
        from database import SessionLocal
        # Use a dedicated sync session for the auth check only — released before
        # the handler runs. The route's own (async) db session is independent.
        local_db = SessionLocal()
        try:
            return await auth_func(request, local_db)
        finally:
            local_db.close()
    except Exception as e:
        logger.debug(f"Auth failed (optional): {e}")
        return None


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class HoldMusicCreate(BaseModel):
    """Create hold music entry"""
    name: str
    description: Optional[str] = None
    source_type: str = "url"  # 'url', 'upload', 'default_library'
    audio_url: Optional[str] = None
    twilio_music_name: Optional[str] = None  # legacy field name for DB compat
    duration_seconds: Optional[int] = None
    is_default: bool = False
    comfort_messages: Optional[List[str]] = None
    comfort_message_interval: int = 30


class HoldMusicUpdate(BaseModel):
    """Update hold music entry"""
    name: Optional[str] = None
    description: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    comfort_messages: Optional[List[str]] = None
    comfort_message_interval: Optional[int] = None


class HoldMusicResponse(BaseModel):
    """Hold music response"""
    id: int
    name: str
    description: Optional[str]
    source_type: str
    audio_url: Optional[str]
    twilio_music_name: Optional[str]  # legacy field name for DB compat
    duration_seconds: Optional[int]
    is_default: bool
    is_active: bool
    comfort_messages: Optional[List[str]]
    comfort_message_interval: int
    created_at: Optional[str]


# ============================================================================
# DEFAULT MUSIC LIBRARY OPTIONS
# ============================================================================

DEFAULT_HOLD_MUSIC = {
    "classical": {
        "name": "Classical",
        "url": "/static/hold-music/default.mp3"
    },
    "ambient": {
        "name": "Ambient",
        "url": "/static/hold-music/default.mp3"
    },
    "electronica": {
        "name": "Electronica",
        "url": "/static/hold-music/default.mp3"
    },
    "guitars": {
        "name": "Guitars",
        "url": "/static/hold-music/default.mp3"
    },
    "rock": {
        "name": "Rock",
        "url": "/static/hold-music/default.mp3"
    },
    "soft_rock": {
        "name": "Soft Rock",
        "url": "/static/hold-music/default.mp3"
    }
}

# Backward-compatible alias
TWILIO_DEFAULT_MUSIC = DEFAULT_HOLD_MUSIC


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.post("")
async def create_hold_music(
    music: HoldMusicCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Create a new hold music entry"""
    try:
        # If setting as default, unset other defaults
        if music.is_default:
            await db.execute(text("UPDATE hold_music SET is_default = FALSE WHERE is_default = TRUE"))

        # Validate audio URL if provided
        audio_url = music.audio_url
        if audio_url and not _validate_audio_url(audio_url):
            raise HTTPException(status_code=400, detail="Invalid audio URL. Must be HTTPS and point to an external host.")

        # Handle default library music
        if music.source_type in ("twilio_default", "default_library") and music.twilio_music_name:
            default_music = DEFAULT_HOLD_MUSIC.get(music.twilio_music_name)
            if default_music:
                audio_url = default_music["url"]

        # Serialize comfort messages
        comfort_json = json.dumps(music.comfort_messages) if music.comfort_messages else None

        result = await db.execute(text("""
            INSERT INTO hold_music
            (name, description, source_type, audio_url, twilio_music_name,
             duration_seconds, is_default, comfort_messages, comfort_message_interval,
             created_by, is_active)
            VALUES (:name, :description, :source_type, :audio_url, :twilio_music_name,
                    :duration_seconds, :is_default, :comfort_messages, :comfort_interval,
                    :created_by, TRUE)
            RETURNING id
        """), {
            "name": music.name,
            "description": music.description,
            "source_type": music.source_type,
            "audio_url": audio_url,
            "twilio_music_name": music.twilio_music_name,
            "duration_seconds": music.duration_seconds,
            "is_default": music.is_default,
            "comfort_messages": comfort_json,
            "comfort_interval": music.comfort_message_interval,
            "created_by": current_user.id if current_user else None
        })

        # PostgreSQL RETURNING id
        try:
            music_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in create_hold_music: {e}")
            music_id = None

        await db.commit()

        return {
            "success": True,
            "message": "Hold music created",
            "music_id": music_id
        }

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating hold music: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_hold_music(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """List all hold music entries"""
    try:
        where_clause = "" if include_inactive else "WHERE is_active = TRUE"

        sql = (
            "SELECT id, name, description, source_type, audio_url, twilio_music_name,"
            " duration_seconds, is_default, is_active, comfort_messages,"
            " comfort_message_interval, created_at"
            " FROM hold_music"
            " " + where_clause +
            " ORDER BY is_default DESC, name ASC"
        )
        results = (await db.execute(text(sql))).fetchall()

        music_list = []
        for row in results:
            comfort_msgs = None
            if hasattr(row, 'comfort_messages') and row.comfort_messages:
                try:
                    comfort_msgs = json.loads(row.comfort_messages)
                except Exception as e:
                    logger.error(f"Error parsing comfort_messages JSON in list_hold_music: {e}")
                    comfort_msgs = None

            music_list.append({
                "id": row.id,
                "name": row.name,
                "description": getattr(row, 'description', None),
                "source_type": getattr(row, 'source_type', 'url'),
                "audio_url": row.audio_url,
                "twilio_music_name": getattr(row, 'twilio_music_name', None),
                "duration_seconds": getattr(row, 'duration_seconds', None),
                "is_default": row.is_default,
                "is_active": getattr(row, 'is_active', True),
                "comfort_messages": comfort_msgs,
                "comfort_message_interval": getattr(row, 'comfort_message_interval', 30),
                "created_at": safe_isoformat(getattr(row, 'created_at', None))
            })

        return {
            "music": music_list,
            "count": len(music_list),
            "default_library": list(DEFAULT_HOLD_MUSIC.keys())
        }

    except SQLAlchemyError as e:
        # Table might not exist or have different schema
        logger.warning(f"Database error listing hold music (table may not exist): {e}")
        return {
            "music": [],
            "count": 0,
            "default_library": list(DEFAULT_HOLD_MUSIC.keys())
        }
    except Exception as e:
        logger.error(f"Error listing hold music: {e}")
        return {
            "music": [],
            "count": 0,
            "default_library": list(DEFAULT_HOLD_MUSIC.keys())
        }


@router.get("/defaults")
async def get_default_hold_music_library():
    """Get list of built-in hold music options"""
    return {
        "options": [
            {"key": key, "name": val["name"], "url": val["url"]}
            for key, val in DEFAULT_HOLD_MUSIC.items()
        ]
    }

# Backward-compatible alias
get_twilio_defaults = get_default_hold_music_library


@router.get("/{music_id}")
async def get_hold_music(
    music_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Get a specific hold music entry"""
    try:
        result = (await db.execute(text("""
            SELECT id, name, description, source_type, audio_url, twilio_music_name,
                   duration_seconds, is_default, is_active, comfort_messages,
                   comfort_message_interval, created_at
            FROM hold_music
            WHERE id = :music_id
        """), {"music_id": music_id})).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Hold music not found")

        comfort_msgs = None
        if result.comfort_messages:
            try:
                comfort_msgs = json.loads(result.comfort_messages)
            except Exception as e:
                logger.error(f"Error parsing comfort_messages JSON in get_hold_music: {e}")
                comfort_msgs = None

        return {
            "id": result.id,
            "name": result.name,
            "description": result.description,
            "source_type": result.source_type,
            "audio_url": result.audio_url,
            "twilio_music_name": result.twilio_music_name,
            "duration_seconds": result.duration_seconds,
            "is_default": result.is_default,
            "is_active": result.is_active,
            "comfort_messages": comfort_msgs,
            "comfort_message_interval": result.comfort_message_interval,
            "created_at": safe_isoformat(result.created_at)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hold music: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{music_id}")
async def update_hold_music(
    music_id: int,
    music: HoldMusicUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Update a hold music entry"""
    try:
        # Check if exists
        existing = (await db.execute(text(
            "SELECT id FROM hold_music WHERE id = :music_id"
        ), {"music_id": music_id})).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Hold music not found")

        # If setting as default, unset other defaults
        if music.is_default:
            await db.execute(text(
                "UPDATE hold_music SET is_default = FALSE WHERE is_default = TRUE AND id != :music_id"
            ), {"music_id": music_id})

        # Build update query dynamically
        updates = []
        params = {"music_id": music_id}

        if music.name is not None:
            updates.append("name = :name")
            params["name"] = music.name
        if music.description is not None:
            updates.append("description = :description")
            params["description"] = music.description
        if music.audio_url is not None:
            updates.append("audio_url = :audio_url")
            params["audio_url"] = music.audio_url
        if music.duration_seconds is not None:
            updates.append("duration_seconds = :duration_seconds")
            params["duration_seconds"] = music.duration_seconds
        if music.is_default is not None:
            updates.append("is_default = :is_default")
            params["is_default"] = music.is_default
        if music.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = music.is_active
        if music.comfort_messages is not None:
            updates.append("comfort_messages = :comfort_messages")
            params["comfort_messages"] = json.dumps(music.comfort_messages)
        if music.comfort_message_interval is not None:
            updates.append("comfort_message_interval = :comfort_interval")
            params["comfort_interval"] = music.comfort_message_interval

        updates.append("updated_at = CURRENT_TIMESTAMP")

        if updates:
            sql = "UPDATE hold_music SET " + ", ".join(updates) + " WHERE id = :music_id"
            await db.execute(text(sql), params)
            await db.commit()

        return {"success": True, "message": "Hold music updated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error updating hold music: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{music_id}")
async def delete_hold_music(
    music_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Delete (deactivate) a hold music entry"""
    try:
        result = await db.execute(text("""
            UPDATE hold_music SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :music_id
        """), {"music_id": music_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Hold music not found")

        return {"success": True, "message": "Hold music deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error deleting hold music: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{music_id}/set-default")
async def set_default_hold_music(
    music_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Set a hold music entry as the default"""
    try:
        # Unset all defaults
        await db.execute(text("UPDATE hold_music SET is_default = FALSE"))

        # Set new default
        result = await db.execute(text("""
            UPDATE hold_music SET is_default = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Hold music not found or inactive")

        return {"success": True, "message": "Default hold music set"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error setting default: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# STREAMING ENDPOINT (for TwiML <Play>)
# ============================================================================

@router.get("/stream/default")
async def stream_default_hold_music(db: AsyncSession = Depends(get_async_db)):
    """
    Redirect to the default hold music URL.
    Used in TwiML: <Play>/api/v1/hold-music/stream/default</Play>
    """
    try:
        result = (await db.execute(text("""
            SELECT audio_url FROM hold_music
            WHERE is_default = TRUE AND is_active = TRUE
            LIMIT 1
        """))).fetchone()

        if result and result.audio_url and _validate_audio_url(result.audio_url):
            return RedirectResponse(url=result.audio_url)

        # Fallback to default hold music
        return RedirectResponse(url=DEFAULT_HOLD_MUSIC["classical"]["url"])

    except SQLAlchemyError as e:
        logger.error(f"Error streaming default music: {e}")
        return RedirectResponse(url=DEFAULT_HOLD_MUSIC["classical"]["url"])


@router.get("/stream/{music_id}")
async def stream_hold_music(
    music_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Redirect to a specific hold music URL.
    Used in TwiML: <Play>/api/v1/hold-music/stream/{music_id}</Play>
    """
    try:
        result = (await db.execute(text("""
            SELECT audio_url FROM hold_music
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id})).fetchone()

        if result and result.audio_url and _validate_audio_url(result.audio_url):
            return RedirectResponse(url=result.audio_url)

        # Fallback to default
        return RedirectResponse(url=DEFAULT_HOLD_MUSIC["classical"]["url"])

    except SQLAlchemyError as e:
        logger.error(f"Error streaming music {music_id}: {e}")
        return RedirectResponse(url=DEFAULT_HOLD_MUSIC["classical"]["url"])


# ============================================================================
# TWIML HELPER ENDPOINT
# ============================================================================

@router.get("/twiml/hold")
async def get_hold_twiml(
    music_id: Optional[int] = None,
    message: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate TwiML for hold music with optional comfort message.
    Returns XML that can be used as wait_url in TeXML/TwiML.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    response = TeXMLResponse()

    # Add comfort message if provided
    if message:
        response.say(message, voice="Polly.Joanna")

    # Get music URL
    if music_id:
        result = (await db.execute(text("""
            SELECT audio_url, comfort_messages, comfort_message_interval
            FROM hold_music
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id})).fetchone()
    else:
        result = (await db.execute(text("""
            SELECT audio_url, comfort_messages, comfort_message_interval
            FROM hold_music
            WHERE is_default = TRUE AND is_active = TRUE
            LIMIT 1
        """))).fetchone()

    music_url = DEFAULT_HOLD_MUSIC["classical"]["url"]
    if result and result.audio_url:
        music_url = result.audio_url

    # Play music
    response.play(music_url, loop=0)

    return Response(content=str(response), media_type="application/xml")
