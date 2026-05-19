"""
OAuth callback endpoints for Microsoft (and future Google) integration.
Handles the OAuth flow and stores tokens in user_integrations table.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import httpx
from datetime import datetime, timedelta, timezone
import uuid
import logging
from urllib.parse import urlencode
import os

# Use relative imports for backend modules
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database import get_db
from models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth", tags=["oauth"])

# Microsoft OAuth Configuration
MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_SCOPES = "Mail.Send Mail.ReadWrite Calendars.ReadWrite Contacts.Read User.Read offline_access"

# Get settings from environment
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")


def get_current_user_from_token(db: Session, token: str):
    """Helper to get user from JWT token - implement based on your auth system."""
    # This should match your existing auth implementation
    from auth import get_current_user as auth_get_current_user
    return auth_get_current_user


# =============================================================================
# MICROSOFT OAUTH
# =============================================================================

@router.get("/microsoft/connect")
async def microsoft_connect(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    redirect_uri: str = Query(None, description="Where to redirect after auth (for mobile)")
):
    """
    Initiate Microsoft OAuth flow.

    For web: Redirects to Microsoft login
    For mobile: Returns the auth URL for the app to open in browser
    """
    # Get user from auth header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Extract user_id from token (simplified - adjust to your auth system)
    token = auth_header.replace("Bearer ", "")

    # Store state for CSRF protection and to identify user in callback
    # In production, you'd want to decode the JWT to get user_id
    state = f"user:{redirect_uri or 'web'}"

    if not MICROSOFT_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Microsoft OAuth not configured")

    params = {
        "client_id": MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": MICROSOFT_REDIRECT_URI,
        "scope": MICROSOFT_SCOPES,
        "state": state,
        "response_mode": "query",
        "prompt": "consent",  # Always show consent to get refresh token
    }

    auth_url = f"{MICROSOFT_AUTH_URL}?{urlencode(params)}"

    # For mobile apps, return the URL instead of redirecting
    if request.headers.get("X-Client-Type") == "mobile":
        return JSONResponse({
            "auth_url": auth_url,
            "message": "Open this URL in browser to connect Microsoft account"
        })

    return RedirectResponse(url=auth_url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    error_description: str = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Handle Microsoft OAuth callback.
    Exchanges auth code for tokens and stores in database.
    """
    from sqlalchemy import text

    # Handle errors from Microsoft
    if error:
        logger.error(f"Microsoft OAuth error: {error} - {error_description}")
        safe_msg = (error_description or "Authentication failed")[:100].replace("\r", "").replace("\n", "")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings?integration=microsoft&status=error&{urlencode({'message': safe_msg})}"
        )

    # Parse state to get user_id and redirect info
    try:
        user_id, redirect_type = state.split(":", 1)
    except ValueError:
        user_id = state
        redirect_type = "web"

    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MICROSOFT_TOKEN_URL,
                data={
                    "client_id": MICROSOFT_CLIENT_ID,
                    "client_secret": MICROSOFT_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": MICROSOFT_REDIRECT_URI,
                    "grant_type": "authorization_code",
                    "scope": MICROSOFT_SCOPES,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )

            if response.status_code != 200:
                error_data = response.json()
                logger.error(f"Token exchange failed: {error_data}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to get tokens: {error_data.get('error_description', 'Unknown error')}"
                )

            tokens = response.json()

        # Get user info from Microsoft to verify
        ms_email = None
        async with httpx.AsyncClient() as client:
            me_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=10.0,
            )
            if me_response.status_code == 200:
                ms_user = me_response.json()
                ms_email = ms_user.get("mail") or ms_user.get("userPrincipalName")
                logger.info(f"Connected Microsoft account: {ms_email}")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

        # Store or update integration using raw SQL (since model may not be loaded)
        integration_id = str(uuid.uuid4())

        # Check if integration exists
        existing = await db.execute(text("""
            SELECT id FROM user_integrations
            WHERE user_id = :user_id AND provider = 'microsoft'
        """), {"user_id": user_id}).fetchone()

        if existing:
            # Update existing
            await db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    scopes = :scopes,
                    updated_at = :updated_at
                WHERE user_id = :user_id AND provider = 'microsoft'
            """), {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": expires_at,
                "scopes": MICROSOFT_SCOPES,
                "updated_at": datetime.now(timezone.utc),
                "user_id": user_id,
            })
            logger.info(f"Updated Microsoft integration for user {user_id}")
        else:
            # Create new
            await db.execute(text("""
                INSERT INTO user_integrations (id, user_id, provider, access_token, refresh_token, expires_at, scopes, created_at, updated_at)
                VALUES (:id, :user_id, 'microsoft', :access_token, :refresh_token, :expires_at, :scopes, :created_at, :updated_at)
            """), {
                "id": integration_id,
                "user_id": user_id,
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": expires_at,
                "scopes": MICROSOFT_SCOPES,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            logger.info(f"Created new Microsoft integration for user {user_id}")

        await db.commit()

        # Handle redirect based on client type
        if redirect_type == "mobile":
            # For mobile, redirect to custom URL scheme
            return RedirectResponse(url="perennia://oauth/success?provider=microsoft")
        else:
            # For web, redirect to settings page
            return RedirectResponse(
                url=f"{FRONTEND_URL}/settings?integration=microsoft&status=success"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft OAuth callback error: {e}")
        await db.rollback()
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings?integration=microsoft&status=error&message=Connection failed"
        )


@router.delete("/microsoft/disconnect")
async def microsoft_disconnect(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Disconnect Microsoft account."""
    from sqlalchemy import text

    # Get user from auth header (simplified)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # In production, decode JWT to get user_id
    user_id = "current_user"  # Replace with actual user ID extraction

    result = await db.execute(text("""
        DELETE FROM user_integrations
        WHERE user_id = :user_id AND provider = 'microsoft'
    """), {"user_id": user_id})

    await db.commit()

    if result.rowcount > 0:
        return {"status": "disconnected", "provider": "microsoft"}

    return {"status": "not_connected", "provider": "microsoft"}


@router.get("/microsoft/status")
async def microsoft_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Check if Microsoft account is connected."""
    from sqlalchemy import text

    # Get user from auth header (simplified)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # In production, decode JWT to get user_id
    user_id = "current_user"  # Replace with actual user ID extraction

    result = await db.execute(text("""
        SELECT expires_at, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'microsoft'
    """), {"user_id": user_id}).fetchone()

    if result:
        return {
            "connected": True,
            "provider": "microsoft",
            "expires_at": result[0].isoformat() if result[0] else None,
            "scopes": result[1],
        }

    return {"connected": False, "provider": "microsoft"}


# =============================================================================
# INTEGRATIONS STATUS (all providers)
# =============================================================================

@router.get("/status")
async def all_integrations_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get status of all connected integrations."""
    from sqlalchemy import text

    # Get user from auth header (simplified)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # In production, decode JWT to get user_id
    user_id = "current_user"  # Replace with actual user ID extraction

    integrations = await db.execute(text("""
        SELECT provider, expires_at, scopes FROM user_integrations
        WHERE user_id = :user_id
    """), {"user_id": user_id}).fetchall()

    result = {
        "microsoft": {"connected": False},
        "google": {"connected": False},
    }

    for integration in integrations:
        result[integration[0]] = {
            "connected": True,
            "expires_at": integration[1].isoformat() if integration[1] else None,
            "scopes": integration[2],
        }

    return result
