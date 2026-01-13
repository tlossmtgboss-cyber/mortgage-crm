"""
Google Calendar Integration Routes
Handles OAuth and calendar sync operations
"""
import os
import logging
from typing import Optional, Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from utils.responses import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/google-calendar", tags=["google-calendar"])

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


@router.get("/auth")
async def google_calendar_auth(
    current_user=Depends(get_current_user)
):
    """Initiate Google Calendar OAuth flow"""
    from integrations.google_calendar_service import google_calendar_client

    if not google_calendar_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("Google Calendar integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    state = f"{user_id}:{frontend_url}/settings/integrations"

    auth_url = google_calendar_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def google_calendar_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Google"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Google.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"Google Calendar OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=google_calendar_auth_failed&message={error_description or error}"
        )

    from integrations.google_calendar_service import google_calendar_client

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
        logger.error("Invalid state parameter in Google Calendar callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = google_calendar_client.exchange_code_for_token(code)

    if not token_data:
        logger.error("Failed to exchange Google Calendar authorization code")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=google_calendar_token_exchange_failed"
        )

    # Get user info
    user_info = google_calendar_client.get_user_info(token_data["access_token"])
    user_email = user_info.get("email") if user_info else None

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
                (user_id, provider, access_token, refresh_token, expires_at, email, scopes, extra_data, updated_at)
            VALUES
                (:user_id, 'google_calendar', :access_token, :refresh_token, :expires_at, :email, :scopes,
                 jsonb_build_object('token_type', :token_type), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                email = EXCLUDED.email,
                scopes = EXCLUDED.scopes,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "email": user_email,
            "scopes": token_data.get("scope"),
            "token_type": token_data.get("token_type", "Bearer")
        })
        db.commit()

        logger.info(f"Successfully stored Google Calendar tokens for user {user_id}")

    except Exception as e:
        logger.error(f"Error storing Google Calendar tokens: {e}")
        db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=google_calendar_storage_failed"
        )

    # Redirect back to integrations page with success
    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success=google_calendar_connected"
    )


@router.get("/status")
async def google_calendar_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check Google Calendar connection status"""
    from integrations.google_calendar_service import google_calendar_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, scopes
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({
                "connected": False,
                "enabled": google_calendar_client.enabled
            })

        # Check if token is expired
        is_expired = False
        if row.expires_at:
            is_expired = datetime.utcnow() > row.expires_at

        return success_response({
            "connected": True,
            "enabled": google_calendar_client.enabled,
            "email": row.email,
            "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })

    except Exception as e:
        logger.error(f"Error checking Google Calendar status: {e}")
        return success_response({
            "connected": False,
            "enabled": google_calendar_client.enabled,
            "error": str(e)
        })


@router.post("/refresh")
async def refresh_google_calendar_token(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Refresh Google Calendar access token"""
    from integrations.google_calendar_service import google_calendar_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get current refresh token
        result = db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail="No Google Calendar connection found")

        # Refresh the token
        token_data = google_calendar_client.refresh_access_token(row.refresh_token)

        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        # Update stored tokens
        db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token,
                refresh_token = :refresh_token,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = 'google_calendar'
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
    except Exception as e:
        logger.error(f"Error refreshing Google Calendar token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_google_calendar(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Google Calendar integration"""
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        db.commit()

        return success_response({
            "disconnected": True
        }, "Google Calendar integration disconnected")

    except Exception as e:
        logger.error(f"Error disconnecting Google Calendar: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Calendar API Endpoints

@router.get("/calendars")
async def list_calendars(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all calendars for the connected user"""
    from integrations.google_calendar_service import google_calendar_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'google_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.utcnow() > row.expires_at:
        token_data = google_calendar_client.refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'google_calendar'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    calendars = google_calendar_client.list_calendars(access_token)

    if calendars is None:
        raise HTTPException(status_code=500, detail="Failed to fetch calendars from Google")

    return success_response(calendars)


@router.get("/events")
async def list_events(
    calendar_id: str = Query("primary", description="Calendar ID"),
    days: int = Query(30, description="Number of days to fetch events for"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List events from a calendar"""
    from integrations.google_calendar_service import google_calendar_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'google_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")

    time_min = datetime.utcnow()
    time_max = datetime.utcnow() + timedelta(days=days)

    events = google_calendar_client.list_events(
        row.access_token,
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max
    )

    if events is None:
        raise HTTPException(status_code=500, detail="Failed to fetch events from Google Calendar")

    return success_response(events)
