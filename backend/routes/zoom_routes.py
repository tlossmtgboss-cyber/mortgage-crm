"""
Zoom Integration Routes
Handles OAuth and meeting operations for Zoom
"""
import os
import logging
from typing import Optional, Callable
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zoom", tags=["zoom"])

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


from db import get_db


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# Request models
class CreateMeetingRequest(BaseModel):
    topic: str
    start_time: datetime
    duration: int = 60
    timezone: str = "UTC"
    agenda: Optional[str] = None


@router.get("/auth")
async def zoom_auth(
    current_user=Depends(get_current_user)
):
    """Initiate Zoom OAuth flow"""
    from integrations.zoom_service import zoom_client

    if not zoom_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("Zoom integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    state = f"{user_id}:{frontend_url}/settings/integrations"

    auth_url = zoom_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def zoom_callback(
    code: str = Query(..., description="Authorization code from Zoom"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Zoom"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Zoom.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"Zoom OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=zoom_auth_failed&message={error_description or error}"
        )

    from integrations.zoom_service import zoom_client

    # Parse state
    user_id = None
    redirect_url = None
    if state:
        parts = state.split(":", 1)
        try:
            user_id = int(parts[0])
        except ValueError:
            pass
        if len(parts) > 1:
            redirect_url = parts[1]

    if not user_id:
        logger.error("Invalid state parameter in Zoom callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = await zoom_client.async_exchange_code_for_token(code)

    if not token_data:
        logger.error("Failed to exchange Zoom authorization code")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=zoom_token_exchange_failed"
        )

    # Get user info
    user_info = await zoom_client.async_get_user_info(token_data["access_token"])
    user_email = user_info.get("email") if user_info else None
    zoom_user_id = user_info.get("id") if user_info else None

    # Store tokens in user_integrations table
    try:
        # Check if user_integrations table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'user_integrations'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            # Create table if it doesn't exist
            db.execute(text("""
                CREATE TABLE user_integrations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    access_token TEXT,
                    refresh_token TEXT,
                    expires_at TIMESTAMP,
                    scopes TEXT,
                    email VARCHAR(255),
                    provider_user_id VARCHAR(255),
                    instance_url TEXT,
                    extra_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            db.commit()

        # Upsert the integration record
        db.execute(text("""
            INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, expires_at, email, provider_user_id, scopes, extra_data, updated_at)
            VALUES
                (:user_id, 'zoom', :access_token, :refresh_token, :expires_at, :email, :zoom_user_id, :scopes,
                 jsonb_build_object('token_type', :token_type), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                email = EXCLUDED.email,
                provider_user_id = EXCLUDED.provider_user_id,
                scopes = EXCLUDED.scopes,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "email": user_email,
            "zoom_user_id": zoom_user_id,
            "scopes": token_data.get("scope"),
            "token_type": token_data.get("token_type", "bearer")
        })
        db.commit()

        logger.info(f"Successfully stored Zoom tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing Zoom tokens: {e}")
        db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=zoom_storage_failed"
        )

    # Redirect back to integrations page with success
    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success=zoom_connected"
    )


@router.get("/status")
async def zoom_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check Zoom connection status"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, provider_user_id, scopes
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'zoom'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({
                "connected": False,
                "enabled": zoom_client.enabled
            })

        # Check if token is expired
        is_expired = False
        if row.expires_at:
            is_expired = datetime.now(timezone.utc) > row.expires_at

        return success_response({
            "connected": True,
            "enabled": zoom_client.enabled,
            "email": row.email,
            "zoom_user_id": row.provider_user_id,
            "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })

    except Exception as e:
        logger.error(f"Error checking Zoom status: {e}")
        return success_response({
            "connected": False,
            "enabled": zoom_client.enabled,
            "error": "Internal server error"
        })


@router.post("/refresh")
async def refresh_zoom_token(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Refresh Zoom access token"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get current refresh token
        result = db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = 'zoom'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail="No Zoom connection found")

        # Refresh the token
        token_data = await zoom_client.async_refresh_access_token(row.refresh_token)

        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        # Update stored tokens
        db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token,
                refresh_token = :refresh_token,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = 'zoom'
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at")
        })
        db.commit()

        return success_response({
            "refreshed": True,
            "expires_at": token_data.get("expires_at")
        })

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error refreshing Zoom token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect_zoom(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Zoom integration"""
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'zoom'
        """), {"user_id": user_id})
        db.commit()

        return success_response({
            "disconnected": True
        }, "Zoom integration disconnected")

    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting Zoom: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# Meeting API Endpoints

@router.get("/meetings")
async def list_meetings(
    meeting_type: str = Query("scheduled", description="Meeting type: scheduled, live, upcoming"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List meetings for the connected user"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'zoom'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Zoom not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        token_data = await zoom_client.async_refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'zoom'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    meetings = await zoom_client.async_list_meetings(access_token, meeting_type=meeting_type)

    if meetings is None:
        raise HTTPException(status_code=500, detail="Failed to fetch meetings from Zoom")

    return success_response(meetings)


@router.post("/meetings")
async def create_meeting(
    meeting: CreateMeetingRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new Zoom meeting"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'zoom'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Zoom not connected")

    new_meeting = await zoom_client.async_create_meeting(
        row.access_token,
        topic=meeting.topic,
        start_time=meeting.start_time,
        duration=meeting.duration,
        timezone=meeting.timezone,
        agenda=meeting.agenda
    )

    if new_meeting is None:
        raise HTTPException(status_code=500, detail="Failed to create Zoom meeting")

    return success_response(new_meeting, "Meeting created successfully")


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific meeting"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'zoom'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Zoom not connected")

    meeting = await zoom_client.async_get_meeting(row.access_token, meeting_id)

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return success_response(meeting)


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a meeting"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'zoom'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Zoom not connected")

    success = await zoom_client.async_delete_meeting(row.access_token, meeting_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete meeting")

    return success_response({"deleted": True}, "Meeting deleted successfully")


@router.get("/recordings")
async def list_recordings(
    days: int = Query(30, description="Number of days to fetch recordings for"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List cloud recordings"""
    from integrations.zoom_service import zoom_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'zoom'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Zoom not connected")

    from_date = datetime.now(timezone.utc) - timedelta(days=days)
    to_date = datetime.now(timezone.utc)

    recordings = await zoom_client.async_list_recordings(
        row.access_token,
        from_date=from_date,
        to_date=to_date
    )

    if recordings is None:
        raise HTTPException(status_code=500, detail="Failed to fetch recordings from Zoom")

    return success_response(recordings)
