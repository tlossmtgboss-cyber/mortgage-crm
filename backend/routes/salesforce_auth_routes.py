"""
Salesforce Integration - OAuth Auth Routes

OAuth flow endpoints: connect, callback, status, disconnect.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .salesforce_models import SalesforceConnectionStatus
from .salesforce_helpers import (
    get_db, get_current_user_id, _safe_redirect_url,
    parse_instance_url_from_scopes, encrypt_token, decrypt_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ OAuth Endpoints ============

@router.get("/connect")
async def salesforce_connect(
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL to redirect after auth"),
    db: Session = Depends(get_db)
):
    """
    Initiate Salesforce OAuth flow.
    Redirects user to Salesforce login page.

    DEPRECATED: Use /api/integrations/salesforce/connect instead for:
    - PKCE-secured OAuth flow
    - Better token management
    - Calendar sync settings initialization
    """
    logger.warning("DEPRECATED: /api/v1/salesforce/connect - Use /api/integrations/salesforce/connect instead")
    from integrations.salesforce_service import salesforce_client

    if not salesforce_client.enabled:
        raise HTTPException(
            status_code=503,
            detail="Salesforce integration not configured. Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET."
        )

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Create state parameter with user_id and optional redirect URL
    state = f"{user_id}"
    if redirect_url:
        state = f"{user_id}:{redirect_url}"

    auth_url = salesforce_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def salesforce_callback(
    code: str = Query(..., description="Authorization code from Salesforce"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Salesforce"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Salesforce.
    Exchanges authorization code for access token.
    Supports two state formats:
    1. Secure hex token stored in oauth_states table (from integration_settings_routes)
    2. Legacy format: user_id:redirect_url
    """
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    if error:
        logger.error(f"Salesforce OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_auth_failed&message={error_description or error}"
        )

    # First, try to handle state as a secure token from oauth_states table
    if state:
        try:
            from services.salesforce.oauth_service import salesforce_oauth

            # Ensure oauth_states table exists with correct schema
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS oauth_states (
                        id SERIAL PRIMARY KEY,
                        state_token VARCHAR(255) UNIQUE NOT NULL,
                        user_id INTEGER NOT NULL,
                        provider VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        used BOOLEAN DEFAULT FALSE,
                        return_url TEXT,
                        state_metadata JSONB
                    )
                """))
                db.commit()
            except Exception as table_err:
                logger.debug(f"oauth_states table check: {table_err}")
                try:
                    db.rollback()
                except Exception as e2:
                    logger.error(f"Error in salesforce_callback (rollback): {e2}")

            # Check if this state exists in oauth_states table
            logger.info(f"Looking up OAuth state in database: {state[:20]}...")
            oauth_state = db.execute(text("""
                SELECT id, user_id, return_url, state_metadata, expires_at, used
                FROM oauth_states
                WHERE state_token = :state AND provider = 'salesforce'
            """), {"state": state}).fetchone()

            if oauth_state:
                logger.info(f"Found OAuth state in database for state token")

                # Check if state has expired
                if oauth_state[4] and oauth_state[4] < datetime.now(timezone.utc):
                    logger.error(f"OAuth state has expired")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_expired&message=OAuth+session+expired.+Please+try+again."
                    )

                # Check if state was already used
                if oauth_state[5]:
                    logger.error(f"OAuth state has already been used")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_used&message=OAuth+state+already+used.+Please+try+again."
                    )

                # Use the oauth service to handle the callback
                try:
                    result = await salesforce_oauth.handle_callback(db, code, state)
                    return_url = _safe_redirect_url(result.get('return_url'), frontend_url)
                    logger.info(f"Salesforce OAuth successful for user {result['user_id']}")
                    return RedirectResponse(url=f"{return_url}?salesforce=connected")
                except ValueError as e:
                    logger.error(f"OAuth callback error: {e}")
                    from urllib.parse import urlencode
                    safe_msg = str(e)[:100].replace("\r", "").replace("\n", "")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=salesforce_auth_failed&{urlencode({'message': safe_msg})}"
                    )
            else:
                # State not found in oauth_states - check if it's a long hex token that should have been there
                if len(state) > 20 and all(c in '0123456789abcdefABCDEF' for c in state[:20]):
                    logger.error(f"Secure OAuth state not found in database - may have expired or been cleaned up")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_not_found&message=OAuth+session+not+found.+Please+try+again."
                    )
        except Exception as e:
            logger.error(f"OAuth state lookup failed with exception: {type(e).__name__}: {e}")
            # Check if state looks like a secure hex token - if so, it should be in the database
            # This prevents falling through to legacy format for secure states
            if state and len(state) >= 32:
                # Check if it's a hex string (secure state token format)
                try:
                    int(state[:32], 16)  # Will succeed for hex strings
                    # It's a hex token but wasn't found - return clear error
                    logger.error(f"Secure OAuth state token not found in database. State: {state[:20]}..., Error: {e}")

                    # Try to get more info about what's in the database
                    try:
                        count_result = db.execute(text("SELECT COUNT(*) FROM oauth_states WHERE provider = 'salesforce'")).fetchone()
                        logger.info(f"oauth_states table has {count_result[0]} salesforce entries")
                    except Exception as count_err:
                        logger.error(f"Could not query oauth_states table: {count_err}")

                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_not_found&message=OAuth+session+not+found.+Please+try+connecting+again."
                    )
                except ValueError:
                    logger.info(f"State is not a hex token, trying legacy format")
                    pass  # Not a hex string, continue to legacy format

    # Fall back to legacy format: user_id:redirect_url
    from integrations.salesforce_service import salesforce_client

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
        # Check one more time if this looks like a secure state that we couldn't handle
        if state and len(state) >= 32:
            try:
                int(state[:32], 16)
                logger.error(f"Cannot parse secure state token - database lookup failed")
                return RedirectResponse(
                    url=f"{frontend_url}/settings/integrations?error=state_lookup_failed&message=Could+not+look+up+OAuth+state.+Please+ensure+database+migrations+are+run."
                )
            except ValueError:
                pass
        logger.error(f"Invalid state parameter: {state[:50] if state else 'None'}...")
        # Return redirect with error instead of JSON HTTPException for OAuth callback flow
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state&message=Invalid+OAuth+state+parameter.+Please+try+connecting+again."
        )

    # Retrieve PKCE code_verifier using state
    code_verifier = salesforce_client.get_code_verifier(state) if state else None

    # Exchange code for tokens (with PKCE code_verifier)
    token_data = salesforce_client.exchange_code_for_token(code, code_verifier=code_verifier)

    if not token_data:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_token_exchange_failed"
        )

    # Get user info from Salesforce
    user_info = None
    if token_data.get("id"):
        user_info = salesforce_client.get_user_info(
            token_data["access_token"],
            token_data["id"]
        )

    # Store tokens in user_integrations table
    try:
        # Ensure table exists (create if not exists - safe operation)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_integrations (
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
        """))
        db.commit()

        # Encrypt tokens before storage
        encrypted_access = encrypt_token(token_data.get("access_token", ""))
        encrypted_refresh = encrypt_token(token_data.get("refresh_token", "")) if token_data.get("refresh_token") else None

        # Use atomic UPSERT to avoid race conditions
        # PostgreSQL: INSERT ... ON CONFLICT DO UPDATE
        db.execute(text("""
            INSERT INTO user_integrations
            (user_id, provider, access_token, refresh_token, scopes, instance_url, email, provider_user_id, created_at, updated_at)
            VALUES (:user_id, 'salesforce', :access_token, :refresh_token, :scopes, :instance_url, :email, :provider_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = NULL,
                scopes = EXCLUDED.scopes,
                instance_url = EXCLUDED.instance_url,
                email = EXCLUDED.email,
                provider_user_id = EXCLUDED.provider_user_id,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": int(user_id),
            "access_token": encrypted_access,
            "refresh_token": encrypted_refresh,
            "scopes": token_data.get("scope", ""),
            "instance_url": token_data.get("instance_url", ""),
            "email": user_info.get("email") if user_info else None,
            "provider_user_id": user_info.get("user_id") if user_info else None,
        })

        db.commit()
        logger.info(f"Stored Salesforce tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Failed to store Salesforce tokens: {e}")
        db.rollback()
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_storage_failed"
        )

    # Redirect to frontend (validate URL to prevent open redirect)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    final_redirect = _safe_redirect_url(redirect_url, frontend_url)

    return RedirectResponse(url=f"{final_redirect}?salesforce=connected")


@router.get("/status", response_model=SalesforceConnectionStatus)
async def salesforce_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check Salesforce connection status for current user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes, email, created_at, updated_at, instance_url
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return SalesforceConnectionStatus(connected=False)

    # Get instance_url from dedicated column, fall back to parsing from scopes for legacy data
    instance_url = integration[5] if len(integration) > 5 and integration[5] else None
    if not instance_url and integration[1] and "instance_url:" in str(integration[1]):
        instance_url = parse_instance_url_from_scopes(str(integration[1]))

    # Get last sync time (table may not exist yet)
    last_sync_time = None
    try:
        last_sync = db.execute(text("""
            SELECT MAX(completed_at) FROM salesforce_sync_logs
            WHERE user_id = :user_id AND status = 'success'
        """), {"user_id": user_id}).fetchone()
        if last_sync and last_sync[0]:
            last_sync_time = last_sync[0].isoformat()
    except Exception as e:
        # Table doesn't exist yet - that's ok
        logger.error(f"Error in salesforce_status (sync log query): {e}")

    return SalesforceConnectionStatus(
        connected=True,
        instance_url=instance_url,
        user_email=integration[2],
        connected_at=integration[3].isoformat() if integration[3] else None,
        last_sync_at=last_sync_time,
    )


@router.delete("/disconnect")
async def salesforce_disconnect(
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect Salesforce integration."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get current token to revoke
    integration = db.execute(text("""
        SELECT access_token, refresh_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if integration:
        from integrations.salesforce_service import salesforce_client

        # Try to revoke token
        if integration[0]:
            salesforce_client.revoke_token(decrypt_token(integration[0]))

        # Delete from database
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'salesforce'
        """), {"user_id": user_id})
        db.commit()

    return {"status": "disconnected", "message": "Salesforce integration disconnected"}
