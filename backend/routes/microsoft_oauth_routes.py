"""
Microsoft 365 OAuth Routes

Handles Microsoft 365 OAuth authentication and email sync functionality:
- OAuth authorization URL generation
- Token exchange and storage
- Connection status and management
- Email sync diagnostics and controls
- Microsoft app configuration management (multi-tenant)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import os
import re
import asyncio
import requests


async def _async_get(*args, **kwargs):
    """Run blocking requests.get() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.get, *args, **kwargs)


async def _async_post(*args, **kwargs):
    """Run blocking requests.post() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.post, *args, **kwargs)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/microsoft", tags=["Microsoft 365"])

# Runtime imports to avoid circular dependencies
# These will be imported from main.py when the router is included


def get_main_imports():
    """Get imports from main.py at runtime to avoid circular imports."""
    import main
    return main


# =============================================================================
# Pydantic Schemas
# =============================================================================

class MicrosoftOAuthConnect(BaseModel):
    """Request schema for connecting Microsoft 365."""
    authorization_code: str
    redirect_uri: str


class MicrosoftAppConfigRequest(BaseModel):
    """Request schema for saving Microsoft App configuration."""
    client_id: str
    client_secret: Optional[str] = None  # Optional when updating (won't change if not provided)
    tenant_id: str = "common"


class MicrosoftAppConfigResponse(BaseModel):
    """Response schema for Microsoft App configuration."""
    client_id: Optional[str] = None
    tenant_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    configured: bool = False
    has_client_secret: bool = False


# =============================================================================
# Helper Functions
# =============================================================================

def is_valid_client_id(cid: str) -> bool:
    """Validate that client_id looks like a valid Azure App ID (UUID format)."""
    if not cid or len(cid) < 20:
        return False
    # Basic UUID format check
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', cid.lower()))


def get_sync_recommendations(connection_status: dict, email_count: int) -> list:
    """Generate helpful recommendations based on sync status."""
    recommendations = []

    if not connection_status["connected"]:
        recommendations.append({
            "type": "error",
            "message": "Microsoft 365 not connected",
            "action": "Go to Settings -> Integrations -> Connect Microsoft 365"
        })
    elif not connection_status["sync_enabled"]:
        recommendations.append({
            "type": "warning",
            "message": "Email sync is disabled",
            "action": "Enable sync in Settings -> Integrations"
        })
    elif connection_status["last_sync_at"] is None:
        recommendations.append({
            "type": "info",
            "message": "No sync has occurred yet",
            "action": "Click 'Sync Now' in Settings or wait for auto-sync (every 5 min)"
        })
    elif email_count == 0:
        recommendations.append({
            "type": "info",
            "message": "No emails have been synced yet",
            "action": "Check your Microsoft 365 inbox has emails, then click 'Sync Now'"
        })
    else:
        recommendations.append({
            "type": "success",
            "message": f"System is working! {email_count} emails synced recently",
            "action": "Check Reconciliation tab to review processed emails"
        })

    return recommendations


# =============================================================================
# OAuth Endpoints
# =============================================================================

@router.get("/auth")
async def microsoft_auth_redirect(
    request: Request,
    integration_type: str = "calendar",
    token: Optional[str] = None,
):
    """Direct redirect to Microsoft OAuth login.

    The frontend calls this via window.location.href or window.open().
    Accepts JWT as ?token= query param (since this is a GET redirect,
    not an API call with Authorization header).
    """
    from fastapi.responses import RedirectResponse

    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        # Authenticate from query param token
        jwt_token = token or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not jwt_token:
            raise HTTPException(status_code=401, detail="Authentication required. Pass ?token=<jwt>")

        current_user = await main.get_current_user(
            token=jwt_token,
            request=request,
            db=db,
        )

        org_id = getattr(current_user, 'organization_id', None)

        # Get Microsoft app config (org-specific or env vars)
        db_config = None
        if org_id:
            db_config = db.query(main.MicrosoftAppConfig).filter(
                main.MicrosoftAppConfig.organization_id == org_id
            ).first()
        if not db_config:
            db_config = db.query(main.MicrosoftAppConfig).first()

        if db_config and db_config.client_id and is_valid_client_id(db_config.client_id):
            client_id = db_config.client_id
            tenant_id = db_config.tenant_id or "common"
        else:
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

        if not client_id:
            raise HTTPException(
                status_code=500,
                detail="Microsoft OAuth not configured. Set MICROSOFT_CLIENT_ID or configure in Settings.",
            )

        # Build redirect URI from Referer or env
        from urllib.parse import urlparse, quote

        frontend_origin = None
        referer = request.headers.get("referer", "")
        if referer:
            parsed = urlparse(referer)
            frontend_origin = f"{parsed.scheme}://{parsed.netloc}"

        if not frontend_origin:
            frontend_origin = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

        redirect_uri = f"{frontend_origin.rstrip('/')}/oauth/callback"

        scopes = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.ReadWrite offline_access"
        auth_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&scope={quote(scopes, safe='')}"
            f"&response_mode=query"
            f"&prompt=select_account"
        )

        logger.info(f"Redirecting user {current_user.id} to Microsoft OAuth (integration_type={integration_type})")
        return RedirectResponse(url=auth_url, status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Microsoft auth redirect: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate Microsoft OAuth")
    finally:
        db.close()


@router.get("/auth-url")
async def get_microsoft_auth_url(
    request: Request,
):
    """Get Microsoft OAuth authorization URL for the frontend to redirect to (multi-tenant)."""
    main = get_main_imports()
    from db import get_db

    # Get dependencies
    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Multi-tenant: Get config for user's organization
        org_id = getattr(current_user, 'organization_id', None)

        db_config = None
        if org_id:
            db_config = db.query(main.MicrosoftAppConfig).filter(
                main.MicrosoftAppConfig.organization_id == org_id
            ).first()

        # Fallback: check for any config (legacy single-tenant mode)
        if not db_config:
            db_config = db.query(main.MicrosoftAppConfig).first()

        if db_config and db_config.client_id and is_valid_client_id(db_config.client_id):
            client_id = db_config.client_id
            tenant_id = db_config.tenant_id or "common"
        else:
            # Fall back to environment variables (default/system config)
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

        # Dynamic redirect URI: Use frontend origin from query param or Referer header
        # Validate against allowlist to prevent open redirects
        from urllib.parse import urlparse
        _ALLOWED_ORIGINS = {"perenniaai.com", "www.perenniaai.com", "localhost", "127.0.0.1"}

        frontend_origin = None
        raw_origin = request.query_params.get('origin')
        if not raw_origin:
            referer = request.headers.get('referer', '')
            if referer:
                parsed = urlparse(referer)
                raw_origin = f"{parsed.scheme}://{parsed.netloc}"

        if raw_origin:
            parsed_origin = urlparse(raw_origin)
            hostname = parsed_origin.hostname or ""
            if hostname in _ALLOWED_ORIGINS or hostname.endswith(".perenniaai.com") or hostname.endswith(".railway.app"):
                frontend_origin = raw_origin.rstrip("/")
            else:
                logger.warning(f"Rejected OAuth origin: {hostname}")

        # Construct redirect URI from validated frontend origin, or fall back to default
        if frontend_origin:
            redirect_uri = f"{frontend_origin}/oauth/callback"
        else:
            redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "https://perenniaai.com/oauth/callback")

        if not client_id:
            raise HTTPException(status_code=500, detail="Microsoft OAuth not configured. Please configure in Settings > Outlook Email.")

        # Build the authorization URL
        scopes = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.ReadWrite offline_access"
        auth_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&response_mode=query"
            f"&prompt=select_account"
        )

        return {"auth_url": auth_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Microsoft auth URL: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/connect")
async def connect_microsoft365(
    auth_data: MicrosoftOAuthConnect,
    request: Request,
):
    """Exchange authorization code for access token and store (multi-tenant)."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Multi-tenant: Get config for user's organization
        org_id = getattr(current_user, 'organization_id', None)

        db_config = None
        if org_id:
            db_config = db.query(main.MicrosoftAppConfig).filter(
                main.MicrosoftAppConfig.organization_id == org_id
            ).first()

        # Fallback: check for any config (legacy single-tenant mode)
        if not db_config:
            db_config = db.query(main.MicrosoftAppConfig).first()

        if db_config and db_config.client_id and db_config.client_secret and is_valid_client_id(db_config.client_id):
            client_id = db_config.client_id
            client_secret = main.decrypt_token(db_config.client_secret)
            tenant_id = db_config.tenant_id or "common"
        else:
            # Fall back to environment variables (default/system config)
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="Microsoft OAuth not configured. Please configure in Settings > Outlook Email.")

        # Microsoft token endpoint
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        # Exchange authorization code for tokens
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_data.authorization_code,
            "redirect_uri": auth_data.redirect_uri,
            "grant_type": "authorization_code",
            "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.ReadWrite offline_access"
        }

        response = await _async_post(token_url, data=data)

        if response.status_code != 200:
            error_detail = "Failed to connect to Microsoft 365"
            try:
                error_data = response.json()
                error_desc = error_data.get("error_description", error_data.get("error", ""))
                logger.error(f"Microsoft token exchange failed: {error_desc[:200]}")
                if "AADSTS" in str(error_desc):
                    if "AADSTS65001" in str(error_desc):
                        error_detail = "Admin consent required. Please have an administrator approve this app in Azure AD."
                    elif "AADSTS50011" in str(error_desc):
                        error_detail = "Redirect URI mismatch. The redirect URI in Azure AD doesn't match the app configuration."
                    elif "AADSTS70008" in str(error_desc):
                        error_detail = "Authorization code expired. Please try connecting again."
                    elif "AADSTS54005" in str(error_desc):
                        error_detail = "Authorization code already used. Please try connecting again."
                    else:
                        error_detail = f"Microsoft error: {error_desc[:200]}"
                else:
                    error_detail = f"Microsoft error: {error_desc[:200]}" if error_desc else "Failed to connect to Microsoft 365"
            except Exception as parse_err:
                logger.error(f"Microsoft token exchange failed (non-JSON): status={response.status_code}")
            raise HTTPException(status_code=400, detail=error_detail)

        token_data = response.json()

        # Get user's email address from Microsoft
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = await _async_get("https://graph.microsoft.com/v1.0/me", headers=headers)

        email_address = None
        if profile_response.status_code == 200:
            profile = profile_response.json()
            email_address = profile.get("mail") or profile.get("userPrincipalName")

        # Check if user already has OAuth record
        existing = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if existing:
            # Update existing record
            existing.access_token = main.encrypt_token(token_data["access_token"])
            existing.refresh_token = main.encrypt_token(token_data["refresh_token"])
            existing.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            existing.email_address = email_address
            existing.sync_enabled = True
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Updated Microsoft OAuth for user {current_user.id}")
        else:
            # Create new OAuth record
            oauth_record = main.MicrosoftOAuthToken(
                user_id=current_user.id,
                access_token=main.encrypt_token(token_data["access_token"]),
                refresh_token=main.encrypt_token(token_data["refresh_token"]),
                token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"]),
                email_address=email_address,
                sync_enabled=True
            )
            db.add(oauth_record)
            db.commit()

            logger.info(f"Created Microsoft OAuth for user {current_user.id}")

        return {
            "status": "success",
            "message": "Microsoft 365 connected successfully",
            "email_address": email_address
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft connect error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.get("/status")
async def get_microsoft_status(
    request: Request,
):
    """Get Microsoft 365 connection status."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if oauth_record:
            return {
                "connected": True,
                "email_address": oauth_record.email_address,
                "sync_enabled": oauth_record.sync_enabled,
                "last_sync_at": oauth_record.last_sync_at,
                "sync_folder": oauth_record.sync_folder,
                "sync_frequency_minutes": oauth_record.sync_frequency_minutes
            }

        # Also check user_integrations table (microsoft_routes.py stores tokens here)
        try:
            ui_row = db.execute(
                text("""
                    SELECT email, expires_at, updated_at
                    FROM user_integrations
                    WHERE user_id = :user_id
                      AND provider IN ('outlook_calendar', 'outlook_email', 'microsoft', 'outlook')
                      AND access_token IS NOT NULL
                    LIMIT 1
                """),
                {"user_id": current_user.id}
            ).fetchone()

            if ui_row:
                return {
                    "connected": True,
                    "email_address": ui_row[0],
                    "sync_enabled": True,
                    "last_sync_at": None,
                    "connected_at": ui_row[2].isoformat() if ui_row[2] else None
                }
        except Exception as e:
            logger.warning(f"Could not check user_integrations: {e}")

        return {
            "connected": False,
            "email_address": None,
            "sync_enabled": False,
            "last_sync_at": None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/disconnect")
async def disconnect_microsoft365(
    request: Request,
):
    """Disconnect Microsoft 365 account."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        # Also clean up user_integrations table (tokens stored by microsoft_routes.py)
        try:
            db.execute(
                text("""
                    DELETE FROM user_integrations
                    WHERE user_id = :user_id
                      AND provider IN ('outlook_calendar', 'outlook_email', 'microsoft', 'outlook')
                """),
                {"user_id": current_user.id}
            )
        except Exception as e:
            logger.warning(f"Could not clean user_integrations: {e}")

        if not oauth_record:
            # Check if user_integrations had tokens (disconnect should succeed if any tokens existed)
            db.commit()
            return {
                "status": "success",
                "message": "Microsoft 365 disconnected successfully"
            }

        db.delete(oauth_record)
        db.commit()

        logger.info(f"Disconnected Microsoft 365 for user {current_user.id}")

        return {
            "status": "success",
            "message": "Microsoft 365 disconnected successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Microsoft disconnect error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.delete("/cleanup-oauth-by-email")
async def cleanup_microsoft_oauth_by_email(
    email: str,
    request: Request,
):
    """Delete all Microsoft OAuth records for a specific email address (for cleanup purposes)."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Find all records with this email address
        oauth_records = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.email_address == email
        ).all()

        if not oauth_records:
            return {
                "status": "not_found",
                "message": f"No Microsoft OAuth records found for email: {email}",
                "deleted_count": 0
            }

        deleted_count = len(oauth_records)
        for record in oauth_records:
            logger.info(f"Deleting Microsoft OAuth record for email {email}, user_id: {record.user_id}")
            db.delete(record)

        db.commit()

        logger.info(f"Cleanup deleted {deleted_count} Microsoft OAuth record(s) for email: {email}")

        return {
            "status": "success",
            "message": f"Successfully deleted {deleted_count} Microsoft OAuth record(s) for email: {email}",
            "deleted_count": deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup Microsoft OAuth error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


# =============================================================================
# OAuth Configuration Endpoints
# =============================================================================

@router.get("/oauth-config", response_model=MicrosoftAppConfigResponse)
async def get_microsoft_oauth_config(
    request: Request,
):
    """Get the current Microsoft OAuth configuration for user's organization (multi-tenant)."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Multi-tenant: Get config for user's organization
        org_id = getattr(current_user, 'organization_id', None)

        config = None
        if org_id:
            config = db.query(main.MicrosoftAppConfig).filter(
                main.MicrosoftAppConfig.organization_id == org_id
            ).first()

        # Fallback: check for any config (legacy single-tenant mode)
        if not config:
            config = db.query(main.MicrosoftAppConfig).first()

        if not config:
            # Check if there are environment variables configured (system default)
            env_client_id = os.getenv("MICROSOFT_CLIENT_ID")
            env_tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

            if env_client_id:
                return MicrosoftAppConfigResponse(
                    client_id=env_client_id[:8] + "..." if env_client_id else None,  # Mask for security
                    tenant_id=env_tenant_id,
                    redirect_uri=os.getenv("MICROSOFT_REDIRECT_URI", "https://perenniaai.com/oauth/callback"),
                    configured=True,
                    has_client_secret=bool(os.getenv("MICROSOFT_CLIENT_SECRET"))
                )

            return MicrosoftAppConfigResponse(
                configured=False,
                has_client_secret=False
            )

        return MicrosoftAppConfigResponse(
            client_id=config.client_id,
            tenant_id=config.tenant_id,
            redirect_uri=config.redirect_uri,
            configured=True,
            has_client_secret=bool(config.client_secret)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Microsoft OAuth config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/oauth-config", response_model=MicrosoftAppConfigResponse)
async def save_microsoft_oauth_config(
    config_data: MicrosoftAppConfigRequest,
    request: Request,
):
    """Save Microsoft OAuth configuration for user's organization (multi-tenant)."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Multi-tenant: Get or create config for user's organization
        org_id = getattr(current_user, 'organization_id', None)

        config = None
        if org_id:
            config = db.query(main.MicrosoftAppConfig).filter(
                main.MicrosoftAppConfig.organization_id == org_id
            ).first()

        redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "https://perenniaai.com/oauth/callback")

        if not config:
            # Create new config for this organization
            config = main.MicrosoftAppConfig(
                organization_id=org_id,  # Link to user's organization
                client_id=config_data.client_id,
                tenant_id=config_data.tenant_id,
                redirect_uri=redirect_uri,
                created_by=current_user.id
            )
            if config_data.client_secret:
                config.client_secret = main.encrypt_token(config_data.client_secret)
            db.add(config)
        else:
            # Update existing config
            config.client_id = config_data.client_id
            config.tenant_id = config_data.tenant_id
            config.redirect_uri = redirect_uri
            if config_data.client_secret:  # Only update secret if provided
                config.client_secret = main.encrypt_token(config_data.client_secret)

        db.commit()
        db.refresh(config)

        logger.info(f"Microsoft OAuth config saved by user {current_user.id} for org {org_id}")

        return MicrosoftAppConfigResponse(
            client_id=config.client_id,
            tenant_id=config.tenant_id,
            redirect_uri=config.redirect_uri,
            configured=True,
            has_client_secret=bool(config.client_secret)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Microsoft OAuth config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


# =============================================================================
# Sync and Diagnostics Endpoints
# =============================================================================

@router.get("/sync-diagnostics")
async def get_email_sync_diagnostics(
    request: Request,
):
    """Comprehensive email sync diagnostics - shows connection status, recent emails, and sync history."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        # Check Microsoft 365 connection
        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        connection_status = {
            "connected": False,
            "email_address": None,
            "sync_enabled": False,
            "last_sync_at": None,
            "sync_frequency_minutes": None,
            "minutes_since_last_sync": None
        }

        if oauth_record:
            connection_status = {
                "connected": True,
                "email_address": oauth_record.email_address,
                "sync_enabled": oauth_record.sync_enabled,
                "last_sync_at": oauth_record.last_sync_at.isoformat() if oauth_record.last_sync_at else None,
                "sync_frequency_minutes": oauth_record.sync_frequency_minutes,
                "sync_folder": oauth_record.sync_folder
            }

            # Calculate time since last sync
            if oauth_record.last_sync_at:
                last_sync = oauth_record.last_sync_at
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                time_diff = datetime.now(timezone.utc) - last_sync
                connection_status["minutes_since_last_sync"] = round(time_diff.total_seconds() / 60, 1)

        # Check recent incoming emails
        recent_emails = db.query(main.IncomingDataEvent).filter(
            main.IncomingDataEvent.user_id == current_user.id,
            main.IncomingDataEvent.source == "microsoft365"
        ).order_by(main.IncomingDataEvent.received_at.desc()).limit(10).all()

        email_data = []
        for email in recent_emails:
            email_data.append({
                "id": email.id,
                "subject": email.subject,
                "sender": email.sender,
                "received_at": email.received_at.isoformat() if email.received_at else None,
                "processed": email.processed,
                "created_at": email.created_at.isoformat() if email.created_at else None
            })

        # Check reconciliation items (extracted data)
        reconciliation_count = db.query(main.ExtractedData).filter(
            main.ExtractedData.status == "pending_review"
        ).join(main.IncomingDataEvent).filter(
            main.IncomingDataEvent.user_id == current_user.id
        ).count()

        # Auto-sync scheduler status
        scheduler_info = {
            "scheduler_running": main.scheduler.running,
            "next_auto_sync": "Every 5 minutes (when scheduler is running)"
        }

        return {
            "connection": connection_status,
            "recent_emails": {
                "count": len(email_data),
                "emails": email_data
            },
            "reconciliation_queue": {
                "pending_count": reconciliation_count
            },
            "scheduler": scheduler_info,
            "recommendations": get_sync_recommendations(connection_status, len(email_data))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync diagnostics error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.get("/test-fetch")
async def test_microsoft_fetch(
    request: Request,
):
    """Debug endpoint - test Microsoft API fetch and show raw results."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            return {"error": "Microsoft 365 not connected"}

        # Get token info
        token_info = {
            "email_address": oauth_record.email_address,
            "sync_folder": oauth_record.sync_folder or "Inbox",
            "sync_enabled": oauth_record.sync_enabled,
            "token_expires_at": oauth_record.token_expires_at.isoformat() if oauth_record.token_expires_at else None,
        }

        # Check if token is expired
        if oauth_record.token_expires_at:
            token_expiry = oauth_record.token_expires_at
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            token_info["token_expired"] = token_expiry < datetime.now(timezone.utc)
            token_info["expires_in_minutes"] = round((token_expiry - datetime.now(timezone.utc)).total_seconds() / 60, 1)

        # Try to fetch from Microsoft API directly
        api_result = {}
        try:
            access_token = main.decrypt_token(oauth_record.access_token)
            folder = oauth_record.sync_folder or "Inbox"
            graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages?$top=5&$orderby=receivedDateTime desc&$select=id,subject,from,receivedDateTime"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            response = await _async_get(graph_url, headers=headers, timeout=30)

            api_result = {
                "status_code": response.status_code,
                "url_called": graph_url.replace(access_token, "***"),
            }

            if response.status_code == 200:
                data = response.json()
                emails = data.get("value", [])
                api_result["email_count"] = len(emails)
                api_result["emails"] = [
                    {
                        "id": e.get("id", "")[:20] + "...",
                        "subject": e.get("subject", "")[:50],
                        "from": e.get("from", {}).get("emailAddress", {}).get("address", ""),
                        "received": e.get("receivedDateTime", "")
                    }
                    for e in emails[:5]
                ]
            else:
                api_result["error"] = response.text[:500]

        except Exception as api_error:
            api_result = {"error": str(api_error)}

        return {
            "token_info": token_info,
            "api_result": api_result
        }

    except Exception as e:
        logger.error(f"Test fetch error: {e}")
        return {"error": "Internal server error"}
    finally:
        db.close()


@router.post("/force-sync")
async def force_email_sync(
    request: Request,
):
    """Force an immediate email sync (bypasses frequency check)."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=404, detail="Microsoft 365 not connected. Please connect in Settings.")

        if not oauth_record.sync_enabled:
            raise HTTPException(status_code=400, detail="Email sync is disabled. Please enable it in Settings.")

        logger.info(f"Force sync triggered by user {current_user.id} ({current_user.email})")

        # Fetch emails
        result = await main.fetch_microsoft_emails(oauth_record, db, limit=50)

        if "error" in result:
            logger.error(f"Force sync error: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])

        # Process each email through DRE
        emails = result.get("emails", [])
        processed_count = 0
        new_emails = 0

        for email_data in emails:
            process_result = await main.process_microsoft_email_to_dre(email_data, current_user.id, db)
            if process_result.get("status") == "success":
                processed_count += 1
                if not process_result.get("already_processed"):
                    new_emails += 1

        # Update last_sync_at
        oauth_record.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Force sync complete: {processed_count}/{len(emails)} emails processed, {new_emails} new")

        return {
            "success": True,
            "total_emails": len(emails),
            "processed_count": processed_count,
            "new_emails": new_emails,
            "already_processed": processed_count - new_emails,
            "message": f"Synced {new_emails} new emails successfully" if new_emails > 0 else "No new emails found"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force sync error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


# =============================================================================
# Sync Aliases (match frontend endpoint names)
# =============================================================================

@router.post("/sync-now")
async def sync_now(request: Request):
    """Alias for /force-sync — frontend calls this endpoint name."""
    return await force_email_sync(request)


@router.post("/sync-calendar")
async def sync_calendar(request: Request):
    """Sync Outlook calendar events to Smart Calendar via outbound sync orchestrator."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        oauth_record = db.query(main.MicrosoftOAuthToken).filter(
            main.MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=404, detail="Microsoft 365 not connected. Please connect in Settings.")

        # Fetch Outlook calendar events and ensure they are reflected in availability
        from integrations.microsoft_outlook_service import microsoft_outlook_client
        from datetime import timedelta

        # Decrypt the access token
        access_token = main.decrypt_token(oauth_record.access_token) if oauth_record.access_token else None
        if not access_token:
            raise HTTPException(status_code=401, detail="Invalid access token. Please reconnect Microsoft 365.")

        # Check expiration and refresh if needed
        if oauth_record.token_expires_at and oauth_record.token_expires_at < datetime.now(timezone.utc):
            refresh_token = main.decrypt_token(oauth_record.refresh_token) if oauth_record.refresh_token else None
            if refresh_token:
                token_data = microsoft_outlook_client.refresh_access_token(refresh_token)
                if token_data:
                    access_token = token_data["access_token"]
                    oauth_record.access_token = main.encrypt_token(token_data["access_token"])
                    oauth_record.refresh_token = main.encrypt_token(token_data["refresh_token"])
                    oauth_record.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
                    db.commit()
                else:
                    raise HTTPException(status_code=401, detail="Token expired and refresh failed. Please reconnect.")
            else:
                raise HTTPException(status_code=401, detail="Token expired. Please reconnect Microsoft 365.")

        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(days=30)

        events = microsoft_outlook_client.list_events(access_token, start_time=start_time, end_time=end_time)

        if events is None:
            raise HTTPException(status_code=500, detail="Failed to fetch calendar events from Outlook")

        event_list = events.get("value", [])

        return {
            "success": True,
            "total_events": len(event_list),
            "message": f"Found {len(event_list)} calendar events from Outlook (next 30 days)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calendar sync error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


# =============================================================================
# Migration Endpoints
# =============================================================================

@router.post("/fix-oauth-config")
async def fix_microsoft_oauth_config(
    request: Request,
):
    """Fix Microsoft OAuth config by using environment variables."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        env_client_id = os.getenv("MICROSOFT_CLIENT_ID")
        env_client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        env_tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")
        env_redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI")

        if not env_client_id:
            return {"status": "error", "message": "MICROSOFT_CLIENT_ID not set in environment"}

        # Get existing config
        existing = db.query(main.MicrosoftAppConfig).first()

        if existing:
            old_client_id = existing.client_id
            existing.client_id = env_client_id
            if env_client_secret:
                existing.client_secret = env_client_secret
            existing.tenant_id = env_tenant_id
            if env_redirect_uri:
                existing.redirect_uri = env_redirect_uri
            db.commit()
            return {
                "status": "success",
                "message": f"Updated Microsoft OAuth config: changed client_id from '{old_client_id}' to '{env_client_id[:8]}...'"
            }
        else:
            return {"status": "info", "message": "No existing config found - system will use environment variables"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing Microsoft OAuth config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/create-app-config-table")
async def create_microsoft_app_config_table(
    request: Request,
):
    """Create the microsoft_app_config table."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS microsoft_app_config (
                id SERIAL PRIMARY KEY,
                client_id VARCHAR(255),
                client_secret TEXT,
                tenant_id VARCHAR(255) DEFAULT 'common',
                redirect_uri VARCHAR(500),
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        return {"status": "success", "message": "microsoft_app_config table created"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating microsoft_app_config table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/create-organizations-table")
async def create_organizations_table(
    request: Request,
):
    """Create the organizations table and add organization_id columns for multi-tenant support."""
    main = get_main_imports()
    from db import get_db

    db = next(get_db())
    try:
        current_user = await main.get_current_user(
            token=request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=request,
            db=db
        )

        results = []

        # 1. Create organizations table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(100) UNIQUE,
                domain VARCHAR(255) UNIQUE,
                settings JSONB DEFAULT '{}',
                subscription_tier VARCHAR(50) DEFAULT 'lead_management',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        results.append("Created organizations table")

        # 2. Create default organization for existing users
        db.execute(text("""
            INSERT INTO organizations (name, slug, subscription_tier)
            VALUES ('Default Organization', 'default', 'full_pipeline')
            ON CONFLICT (slug) DO NOTHING
        """))
        results.append("Created default organization")

        # 3. Add organization_id to users table if it doesn't exist
        try:
            db.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)
            """))
            results.append("Added organization_id to users table")
        except Exception as e:
            results.append(f"users.organization_id: {str(e)[:50]}")

        # 4. Add organization_id to branches table if it doesn't exist
        try:
            db.execute(text("""
                ALTER TABLE branches ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)
            """))
            results.append("Added organization_id to branches table")
        except Exception as e:
            results.append(f"branches.organization_id: {str(e)[:50]}")

        # 5. Add organization_id to microsoft_app_config table if it doesn't exist
        try:
            db.execute(text("""
                ALTER TABLE microsoft_app_config ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) UNIQUE
            """))
            results.append("Added organization_id to microsoft_app_config table")
        except Exception as e:
            results.append(f"microsoft_app_config.organization_id: {str(e)[:50]}")

        # 6. Assign all existing users to the default organization
        db.execute(text("""
            UPDATE users
            SET organization_id = (SELECT id FROM organizations WHERE slug = 'default')
            WHERE organization_id IS NULL
        """))
        results.append("Assigned existing users to default organization")

        # 7. Assign existing microsoft_app_config to default organization
        db.execute(text("""
            UPDATE microsoft_app_config
            SET organization_id = (SELECT id FROM organizations WHERE slug = 'default')
            WHERE organization_id IS NULL
        """))
        results.append("Assigned existing Microsoft config to default organization")

        # 8. Create index for faster lookups
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_microsoft_app_config_organization_id ON microsoft_app_config(organization_id)
            """))
            results.append("Created indexes")
        except Exception as e:
            results.append(f"Indexes: {str(e)[:50]}")

        db.commit()

        return {
            "status": "success",
            "message": "Multi-tenant organizations setup complete",
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating organizations table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
