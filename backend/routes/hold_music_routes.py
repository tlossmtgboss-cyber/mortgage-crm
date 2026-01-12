"""
Hold Music Routes
Manage hold music library for call queues, transfers, and conferences
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
import logging
import os
import json

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/hold-music", tags=["hold-music"])


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


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class HoldMusicCreate(BaseModel):
    """Create hold music entry"""
    name: str
    description: Optional[str] = None
    source_type: str = "url"  # 'url', 'upload', 'twilio_default'
    audio_url: Optional[str] = None
    twilio_music_name: Optional[str] = None
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
    twilio_music_name: Optional[str]
    duration_seconds: Optional[int]
    is_default: bool
    is_active: bool
    comfort_messages: Optional[List[str]]
    comfort_message_interval: int
    created_at: Optional[str]


# ============================================================================
# TWILIO DEFAULT MUSIC OPTIONS
# ============================================================================

TWILIO_DEFAULT_MUSIC = {
    "classical": {
        "name": "Classical",
        "url": "http://com.twilio.music.classical.s3.amazonaws.com/BussyStrings.mp3"
    },
    "ambient": {
        "name": "Ambient",
        "url": "http://com.twilio.music.ambient.s3.amazonaws.com/Midnight_Drive_LOOP.mp3"
    },
    "electronica": {
        "name": "Electronica",
        "url": "http://com.twilio.music.electronica.s3.amazonaws.com/Electronica.mp3"
    },
    "guitars": {
        "name": "Guitars",
        "url": "http://com.twilio.music.guitars.s3.amazonaws.com/Guitars.mp3"
    },
    "rock": {
        "name": "Rock",
        "url": "http://com.twilio.music.rock.s3.amazonaws.com/Rock.mp3"
    },
    "soft_rock": {
        "name": "Soft Rock",
        "url": "http://com.twilio.music.soft-rock.s3.amazonaws.com/SoftRock.mp3"
    }
}


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.post("")
async def create_hold_music(
    music: HoldMusicCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create a new hold music entry"""
    try:
        # If setting as default, unset other defaults
        if music.is_default:
            db.execute(text("UPDATE hold_music SET is_default = FALSE WHERE is_default = TRUE"))

        # Handle twilio default music
        audio_url = music.audio_url
        if music.source_type == "twilio_default" and music.twilio_music_name:
            twilio_music = TWILIO_DEFAULT_MUSIC.get(music.twilio_music_name)
            if twilio_music:
                audio_url = twilio_music["url"]

        # Serialize comfort messages
        comfort_json = json.dumps(music.comfort_messages) if music.comfort_messages else None

        result = db.execute(text("""
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

        # For SQLite compatibility
        try:
            music_id = result.fetchone()[0]
        except:
            music_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        db.commit()

        return {
            "success": True,
            "message": "Hold music created",
            "music_id": music_id
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating hold music: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_hold_music(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """List all hold music entries"""
    try:
        where_clause = "" if include_inactive else "WHERE is_active = TRUE"

        results = db.execute(text(f"""
            SELECT id, name, description, source_type, audio_url, twilio_music_name,
                   duration_seconds, is_default, is_active, comfort_messages,
                   comfort_message_interval, created_at
            FROM hold_music
            {where_clause}
            ORDER BY is_default DESC, name ASC
        """)).fetchall()

        music_list = []
        for row in results:
            comfort_msgs = None
            if row.comfort_messages:
                try:
                    comfort_msgs = json.loads(row.comfort_messages)
                except:
                    comfort_msgs = None

            music_list.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "source_type": row.source_type,
                "audio_url": row.audio_url,
                "twilio_music_name": row.twilio_music_name,
                "duration_seconds": row.duration_seconds,
                "is_default": row.is_default,
                "is_active": row.is_active,
                "comfort_messages": comfort_msgs,
                "comfort_message_interval": row.comfort_message_interval,
                "created_at": safe_isoformat(row.created_at)
            })

        return {
            "music": music_list,
            "count": len(music_list),
            "twilio_defaults": list(TWILIO_DEFAULT_MUSIC.keys())
        }

    except Exception as e:
        logger.error(f"Error listing hold music: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twilio-defaults")
async def get_twilio_defaults():
    """Get list of Twilio's built-in hold music options"""
    return {
        "options": [
            {"key": key, "name": val["name"], "url": val["url"]}
            for key, val in TWILIO_DEFAULT_MUSIC.items()
        ]
    }


@router.get("/{music_id}")
async def get_hold_music(
    music_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get a specific hold music entry"""
    try:
        result = db.execute(text("""
            SELECT id, name, description, source_type, audio_url, twilio_music_name,
                   duration_seconds, is_default, is_active, comfort_messages,
                   comfort_message_interval, created_at
            FROM hold_music
            WHERE id = :music_id
        """), {"music_id": music_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Hold music not found")

        comfort_msgs = None
        if result.comfort_messages:
            try:
                comfort_msgs = json.loads(result.comfort_messages)
            except:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{music_id}")
async def update_hold_music(
    music_id: int,
    music: HoldMusicUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Update a hold music entry"""
    try:
        # Check if exists
        existing = db.execute(text(
            "SELECT id FROM hold_music WHERE id = :music_id"
        ), {"music_id": music_id}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Hold music not found")

        # If setting as default, unset other defaults
        if music.is_default:
            db.execute(text(
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
            db.execute(text(f"""
                UPDATE hold_music SET {', '.join(updates)} WHERE id = :music_id
            """), params)
            db.commit()

        return {"success": True, "message": "Hold music updated"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating hold music: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{music_id}")
async def delete_hold_music(
    music_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Delete (deactivate) a hold music entry"""
    try:
        result = db.execute(text("""
            UPDATE hold_music SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :music_id
        """), {"music_id": music_id})

        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Hold music not found")

        return {"success": True, "message": "Hold music deleted"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting hold music: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{music_id}/set-default")
async def set_default_hold_music(
    music_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Set a hold music entry as the default"""
    try:
        # Unset all defaults
        db.execute(text("UPDATE hold_music SET is_default = FALSE"))

        # Set new default
        result = db.execute(text("""
            UPDATE hold_music SET is_default = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id})

        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Hold music not found or inactive")

        return {"success": True, "message": "Default hold music set"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting default: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STREAMING ENDPOINT (for TwiML <Play>)
# ============================================================================

@router.get("/stream/default")
async def stream_default_hold_music(db: Session = Depends(get_db)):
    """
    Redirect to the default hold music URL.
    Used in TwiML: <Play>/api/v1/hold-music/stream/default</Play>
    """
    try:
        result = db.execute(text("""
            SELECT audio_url FROM hold_music
            WHERE is_default = TRUE AND is_active = TRUE
            LIMIT 1
        """)).fetchone()

        if result and result.audio_url:
            return RedirectResponse(url=result.audio_url)

        # Fallback to Twilio default
        return RedirectResponse(url=TWILIO_DEFAULT_MUSIC["classical"]["url"])

    except Exception as e:
        logger.error(f"Error streaming default music: {e}")
        return RedirectResponse(url=TWILIO_DEFAULT_MUSIC["classical"]["url"])


@router.get("/stream/{music_id}")
async def stream_hold_music(
    music_id: int,
    db: Session = Depends(get_db)
):
    """
    Redirect to a specific hold music URL.
    Used in TwiML: <Play>/api/v1/hold-music/stream/{music_id}</Play>
    """
    try:
        result = db.execute(text("""
            SELECT audio_url FROM hold_music
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id}).fetchone()

        if result and result.audio_url:
            return RedirectResponse(url=result.audio_url)

        # Fallback to default
        return RedirectResponse(url=TWILIO_DEFAULT_MUSIC["classical"]["url"])

    except Exception as e:
        logger.error(f"Error streaming music {music_id}: {e}")
        return RedirectResponse(url=TWILIO_DEFAULT_MUSIC["classical"]["url"])


# ============================================================================
# TWIML HELPER ENDPOINT
# ============================================================================

@router.get("/twiml/hold")
async def get_hold_twiml(
    music_id: Optional[int] = None,
    message: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Generate TwiML for hold music with optional comfort message.
    Returns XML that can be used as wait_url in Twilio.
    """
    from twilio.twiml.voice_response import VoiceResponse

    response = VoiceResponse()

    # Add comfort message if provided
    if message:
        response.say(message, voice="Polly.Joanna")

    # Get music URL
    if music_id:
        result = db.execute(text("""
            SELECT audio_url, comfort_messages, comfort_message_interval
            FROM hold_music
            WHERE id = :music_id AND is_active = TRUE
        """), {"music_id": music_id}).fetchone()
    else:
        result = db.execute(text("""
            SELECT audio_url, comfort_messages, comfort_message_interval
            FROM hold_music
            WHERE is_default = TRUE AND is_active = TRUE
            LIMIT 1
        """)).fetchone()

    music_url = TWILIO_DEFAULT_MUSIC["classical"]["url"]
    if result and result.audio_url:
        music_url = result.audio_url

    # Play music
    response.play(music_url, loop=0)

    return Response(content=str(response), media_type="application/xml")
