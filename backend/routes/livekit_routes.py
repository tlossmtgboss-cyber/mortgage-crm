"""
LiveKit Token Provisioning Routes
Generates room tokens for Aria voice sessions over LiveKit WebRTC.

Endpoints:
  POST /api/v1/livekit/token  — Create a LiveKit room + access token for the current user
  GET  /api/v1/livekit/health — Check LiveKit connectivity
"""

import os
import re
import json
import uuid
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from livekit.api import AccessToken, VideoGrants, RoomAgentDispatch, RoomConfiguration
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/livekit", tags=["livekit"])

# ─── Configuration ───────────────────────────────────────────────────────────

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

AGENT_NAME = "aria-voice"  # Must match @server.rtc_session(agent_name=...) in voice_agent.py


# ─── Schemas ─────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    """Request body for token generation."""
    # Room name is auto-generated if not provided
    room_name: str = Field(default="", description="Optional room name. Auto-generated if empty.")


class TokenResponse(BaseModel):
    """Response with LiveKit connection details."""
    token: str
    url: str
    room_name: str
    participant_identity: str


# ─── Auth dependency ─────────────────────────────────────────────────────────
# Import get_current_user lazily to avoid circular imports

def _get_auth():
    from auth.dependencies import get_current_user
    return get_current_user


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse)
async def create_voice_token(
    body: TokenRequest = TokenRequest(),
    current_user=Depends(_get_auth()),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Generate a LiveKit access token for Aria voice session.

    Creates a new room (or joins existing) and returns a JWT token
    that the frontend uses to connect via WebRTC. The LiveKit agent
    worker auto-dispatches Aria into the room.
    """
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise HTTPException(
            status_code=503,
            detail="LiveKit not configured. Set LIVEKIT_API_KEY and LIVEKIT_API_SECRET.",
        )

    if not LIVEKIT_URL:
        raise HTTPException(
            status_code=503,
            detail="LiveKit URL not configured. Set LIVEKIT_URL.",
        )

    # Generate room name — always prefixed with user ID to prevent cross-user room access
    user_id = current_user.id if hasattr(current_user, "id") else "unknown"
    if body.room_name:
        # Sanitize user-provided room name: alphanumeric, dash, underscore only, max 64 chars
        if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', body.room_name):
            raise HTTPException(status_code=400, detail="Invalid room name. Use alphanumeric, dash, or underscore (max 64 chars).")
        # Prefix with user ID to prevent joining another user's room
        room_name = f"aria-{user_id}-{body.room_name}"
    else:
        room_name = f"aria-voice-{user_id}-{uuid.uuid4().hex[:8]}"
    participant_identity = f"user-{user_id}"

    try:
        token = AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        token.with_identity(participant_identity)
        token.with_name(
            getattr(current_user, "full_name", None)
            or getattr(current_user, "email", participant_identity)
        )
        token.with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        token.with_ttl(timedelta(hours=1))

        # Resolve company name for voice agent greeting
        from services.company_name_resolver import resolve_company_name
        org_id = getattr(current_user, "organization_id", None)
        company_name = resolve_company_name(db, org_id)

        # Add metadata so the agent knows who it's talking to
        metadata = {
            "user_id": str(user_id),
            "org_id": str(org_id or ""),
            "email": getattr(current_user, "email", ""),
            "company_name": company_name,
            "agent": AGENT_NAME,
        }
        token.with_metadata(json.dumps(metadata))

        # Dispatch the aria-voice agent into the room when this participant connects
        token.with_room_config(
            RoomConfiguration(
                agents=[RoomAgentDispatch(
                    agent_name=AGENT_NAME,
                    metadata=json.dumps(metadata),
                )]
            )
        )

        jwt_token = token.to_jwt()

        logger.info(
            f"[LiveKit] Token issued: user={user_id}, room={room_name}"
        )

        return TokenResponse(
            token=jwt_token,
            url=LIVEKIT_URL,
            room_name=room_name,
            participant_identity=participant_identity,
        )

    except Exception as e:
        logger.error(f"[LiveKit] Token generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate voice session token")


@router.get("/health")
async def livekit_health():
    """Check if LiveKit is configured and reachable."""
    configured = bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET and LIVEKIT_URL)
    return {
        "configured": configured,
        "url": LIVEKIT_URL if configured else None,
        "agent_name": AGENT_NAME,
    }
