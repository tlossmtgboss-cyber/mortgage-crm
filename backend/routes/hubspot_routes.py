"""
HubSpot Integration Routes
Handles OAuth and CRM sync operations
"""
import os
import logging
from typing import Optional, Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError
from db import get_async_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/hubspot", tags=["hubspot"])

# Dependency injection placeholders
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py.
    get_db_func is accepted for API compatibility but ignored; get_db is imported from db.py.
    """
    global _get_current_user
    _get_current_user = get_current_user_func


from auth.dependencies import get_current_user  # dedup: was local wrapper
@router.get("/auth")
async def hubspot_auth(
    current_user=Depends(get_current_user)
):
    """Initiate HubSpot OAuth flow"""
    from integrations.hubspot_service import hubspot_client

    if not hubspot_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("HubSpot integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    state = f"{user_id}:{frontend_url}/settings/integrations"

    auth_url = hubspot_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def hubspot_callback(
    code: str = Query(..., description="Authorization code from HubSpot"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from HubSpot"),
    error_description: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle OAuth callback from HubSpot.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"HubSpot OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=hubspot_auth_failed&message={error_description or error}"
        )

    from integrations.hubspot_service import hubspot_client

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
        logger.error("Invalid state parameter in HubSpot callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = hubspot_client.exchange_code_for_token(code)

    if not token_data:
        logger.error("Failed to exchange HubSpot authorization code")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=hubspot_token_exchange_failed"
        )

    # Get token info to get hub_id and user email
    token_info = hubspot_client.get_access_token_info(token_data["access_token"])
    hub_id = token_info.get("hub_id") if token_info else None
    user_email = token_info.get("user") if token_info else None

    # Store tokens in user_integrations table
    try:
        # Check if user_integrations table exists
        result = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'user_integrations'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            # Create table if it doesn't exist
            await db.execute(text("""
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
            await db.commit()

        # Upsert the integration record
        await db.execute(text("""
            INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, expires_at, email, provider_user_id, extra_data, updated_at)
            VALUES
                (:user_id, 'hubspot', :access_token, :refresh_token, :expires_at, :email, :hub_id,
                 jsonb_build_object('token_type', :token_type), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                email = EXCLUDED.email,
                provider_user_id = EXCLUDED.provider_user_id,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "email": user_email,
            "hub_id": str(hub_id) if hub_id else None,
            "token_type": token_data.get("token_type", "bearer")
        })
        await db.commit()

        logger.info(f"Successfully stored HubSpot tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing HubSpot tokens: {e}")
        await db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=hubspot_storage_failed"
        )

    # Redirect back to integrations page with success
    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success=hubspot_connected"
    )


@router.get("/status")
async def hubspot_status(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Check HubSpot connection status"""
    from integrations.hubspot_service import hubspot_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = await db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, provider_user_id
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'hubspot'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({
                "connected": False,
                "enabled": hubspot_client.enabled
            })

        # Check if token is expired
        is_expired = False
        if row.expires_at:
            is_expired = datetime.now(timezone.utc) > row.expires_at

        return success_response({
            "connected": True,
            "enabled": hubspot_client.enabled,
            "email": row.email,
            "hub_id": row.provider_user_id,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })

    except Exception as e:
        logger.error(f"Error checking HubSpot status: {e}")
        return success_response({
            "connected": False,
            "enabled": hubspot_client.enabled,
            "error": "Internal server error"
        })


@router.post("/refresh")
async def refresh_hubspot_token(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Refresh HubSpot access token"""
    from integrations.hubspot_service import hubspot_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get current refresh token
        result = await db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = 'hubspot'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail="No HubSpot connection found")

        # Refresh the token
        token_data = hubspot_client.refresh_access_token(row.refresh_token)

        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        # Update stored tokens
        await db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token,
                refresh_token = :refresh_token,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = 'hubspot'
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at")
        })
        await db.commit()

        return success_response({
            "refreshed": True,
            "expires_at": token_data.get("expires_at")
        })

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error refreshing HubSpot token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect_hubspot(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Disconnect HubSpot integration"""
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        await db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'hubspot'
        """), {"user_id": user_id})
        await db.commit()

        return success_response({
            "disconnected": True
        }, "HubSpot integration disconnected")

    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting HubSpot: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# CRM Sync Endpoints

@router.get("/contacts")
async def get_hubspot_contacts(
    limit: int = Query(100, le=100),
    after: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get contacts from HubSpot"""
    from integrations.hubspot_service import hubspot_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = await db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'hubspot'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="HubSpot not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        token_data = hubspot_client.refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            # Update stored token
            await db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'hubspot'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            await db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    contacts = hubspot_client.get_contacts(access_token, limit=limit, after=after)

    if contacts is None:
        raise HTTPException(status_code=500, detail="Failed to fetch contacts from HubSpot")

    return success_response(contacts)


@router.get("/deals")
async def get_hubspot_deals(
    limit: int = Query(100, le=100),
    after: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get deals from HubSpot"""
    from integrations.hubspot_service import hubspot_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = await db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'hubspot'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="HubSpot not connected")

    deals = hubspot_client.get_deals(row.access_token, limit=limit, after=after)

    if deals is None:
        raise HTTPException(status_code=500, detail="Failed to fetch deals from HubSpot")

    return success_response(deals)
