"""
Slack Integration Routes
Handles OAuth and messaging operations for Slack
"""
import os
import logging
from typing import Optional, Callable, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ALLOWED_REDIRECT_HOSTS = {"perenniaai.com", "www.perenniaai.com", "app.perenniaai.com", "localhost", "127.0.0.1"}

router = APIRouter(prefix="/api/v1/slack", tags=["slack"])

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
class SendMessageRequest(BaseModel):
    channel: str
    text: str
    thread_ts: Optional[str] = None


class SendDirectMessageRequest(BaseModel):
    user_id: str
    text: str


class SendNotificationRequest(BaseModel):
    channel: str
    title: str
    message: str
    color: Optional[str] = "#36a64f"
    fields: Optional[List[dict]] = None


@router.get("/auth")
async def slack_auth(
    current_user=Depends(get_current_user)
):
    """Initiate Slack OAuth flow"""
    from integrations.slack_service import slack_client

    if not slack_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("Slack integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    state = f"{user_id}:{frontend_url}/settings/integrations"

    auth_url = slack_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def slack_callback(
    code: str = Query(..., description="Authorization code from Slack"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Slack"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Slack.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"Slack OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=slack_auth_failed&message={error_description or error}"
        )

    from integrations.slack_service import slack_client

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
        logger.error("Invalid state parameter in Slack callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = slack_client.exchange_code_for_token(code)

    if not token_data:
        logger.error("Failed to exchange Slack authorization code")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=slack_token_exchange_failed"
        )

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
                (user_id, provider, access_token, refresh_token, expires_at, provider_user_id, scopes, extra_data, updated_at)
            VALUES
                (:user_id, 'slack', :access_token, :refresh_token, :expires_at, :slack_user_id, :scopes,
                 jsonb_build_object(
                     'team_id', :team_id,
                     'team_name', :team_name,
                     'bot_user_id', :bot_user_id,
                     'user_access_token', :user_access_token
                 ), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                provider_user_id = EXCLUDED.provider_user_id,
                scopes = EXCLUDED.scopes,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "slack_user_id": token_data.get("user_id"),
            "scopes": token_data.get("scope"),
            "team_id": token_data.get("team_id"),
            "team_name": token_data.get("team_name"),
            "bot_user_id": token_data.get("bot_user_id"),
            "user_access_token": token_data.get("user_access_token"),
        })
        db.commit()

        logger.info(f"Successfully stored Slack tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing Slack tokens: {e}")
        db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=slack_storage_failed"
        )

    # Validate redirect_url to prevent open redirect
    safe_redirect = frontend_url + "/settings/integrations"
    if redirect_url:
        try:
            parsed = urlparse(redirect_url)
            hostname = (parsed.hostname or "").lower()
            if hostname in _ALLOWED_REDIRECT_HOSTS or hostname.endswith(".perenniaai.com") or hostname.endswith(".railway.app"):
                safe_redirect = redirect_url
            else:
                logger.warning(f"Rejected Slack OAuth redirect to: {hostname}")
        except Exception as e:
            logger.error(f"Error validating Slack OAuth redirect URL: {e}")

    return RedirectResponse(
        url=f"{safe_redirect}?success=slack_connected"
    )


@router.get("/status")
async def slack_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check Slack connection status"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, provider_user_id, scopes, extra_data
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'slack'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({
                "connected": False,
                "enabled": slack_client.enabled
            })

        extra_data = row.extra_data or {}

        return success_response({
            "connected": True,
            "enabled": slack_client.enabled,
            "slack_user_id": row.provider_user_id,
            "team_id": extra_data.get("team_id"),
            "team_name": extra_data.get("team_name"),
            "scopes": row.scopes,
        })

    except Exception as e:
        logger.error(f"Error checking Slack status: {e}")
        return success_response({
            "connected": False,
            "enabled": slack_client.enabled,
            "error": "Internal server error"
        })


@router.post("/disconnect")
async def disconnect_slack(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Slack integration"""
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'slack'
        """), {"user_id": user_id})
        db.commit()

        return success_response({
            "disconnected": True
        }, "Slack integration disconnected")

    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting Slack: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# Slack API Endpoints

@router.get("/team")
async def get_team_info(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Slack team/workspace info"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    team_info = slack_client.get_team_info(row.access_token)

    if team_info is None:
        raise HTTPException(status_code=500, detail="Failed to fetch team info from Slack")

    return success_response(team_info)


@router.get("/channels")
async def list_channels(
    limit: int = Query(100, le=1000),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List Slack channels"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    channels = slack_client.list_channels(row.access_token, limit=limit)

    if channels is None:
        raise HTTPException(status_code=500, detail="Failed to fetch channels from Slack")

    return success_response(channels)


@router.get("/users")
async def list_users(
    limit: int = Query(100, le=1000),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List Slack workspace users"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    users = slack_client.list_users(row.access_token, limit=limit)

    if users is None:
        raise HTTPException(status_code=500, detail="Failed to fetch users from Slack")

    return success_response(users)


@router.post("/messages")
async def send_message(
    message: SendMessageRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message to a Slack channel"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    response = slack_client.send_message(
        row.access_token,
        channel=message.channel,
        text=message.text,
        thread_ts=message.thread_ts
    )

    if response is None:
        raise HTTPException(status_code=500, detail="Failed to send message")

    return success_response(response, "Message sent successfully")


@router.post("/direct-messages")
async def send_direct_message(
    message: SendDirectMessageRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a direct message to a Slack user"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    response = slack_client.send_direct_message(
        row.access_token,
        user_id=message.user_id,
        text=message.text
    )

    if response is None:
        raise HTTPException(status_code=500, detail="Failed to send direct message")

    return success_response(response, "Direct message sent successfully")


@router.post("/notifications")
async def send_notification(
    notification: SendNotificationRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a rich notification to a Slack channel"""
    from integrations.slack_service import slack_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'slack'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Slack not connected")

    response = slack_client.send_notification(
        row.access_token,
        channel_or_user=notification.channel,
        title=notification.title,
        message=notification.message,
        color=notification.color,
        fields=notification.fields
    )

    if response is None:
        raise HTTPException(status_code=500, detail="Failed to send notification")

    return success_response(response, "Notification sent successfully")
