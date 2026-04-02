"""
Microsoft Integration Routes
Handles OAuth callback and operations for Outlook Calendar and Email via Microsoft Graph API
"""
import os
import logging
from typing import Optional, Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import List

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/microsoft", tags=["microsoft"])

# Dependency injection placeholders
from db import get_db
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time.
    Supports token from Authorization header OR query parameter (for browser redirect flows like OAuth initiation).
    """
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    # Fallback: token from query param (for window.location.href OAuth initiation)
    if not token:
        token = request.query_params.get("token", "")
    return await _get_current_user(token=token, request=request, db=db)


# Request models
class CreateEventRequest(BaseModel):
    subject: str
    start_time: datetime
    end_time: datetime
    attendees: Optional[List[str]] = None
    location: Optional[str] = None
    body: Optional[str] = None
    is_online_meeting: bool = False


class SendEmailRequest(BaseModel):
    to_recipients: List[str]
    subject: str
    body: str
    cc_recipients: Optional[List[str]] = None
    is_html: bool = True


@router.get("/auth")
async def microsoft_auth(
    integration_type: str = Query("calendar", description="Type: calendar, email, or all"),
    current_user=Depends(get_current_user)
):
    """Initiate Microsoft OAuth flow"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    if not microsoft_outlook_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("Microsoft integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    state = f"{user_id}|{frontend_url}/settings/integrations|{integration_type}"

    auth_url = microsoft_outlook_client.get_authorization_url(state=state, integration_type=integration_type)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def microsoft_callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: Optional[str] = Query(None, description="State parameter with user_id and integration type"),
    error: Optional[str] = Query(None, description="Error from Microsoft"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Microsoft.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

    if error:
        logger.error(f"Microsoft OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=microsoft_auth_failed&message={error_description or error}"
        )

    from integrations.microsoft_outlook_service import microsoft_outlook_client

    # Parse state (format: user_id|redirect_url|integration_type)
    # Using | as delimiter because : conflicts with https://
    user_id = None
    redirect_url = None
    integration_type = "calendar"  # default

    logger.info(f"Microsoft callback received - state: {state}, code length: {len(code) if code else 0}")

    if state:
        parts = state.split("|")
        logger.info(f"State parts: {parts}")
        try:
            user_id = int(parts[0])
        except ValueError:
            logger.error(f"Failed to parse user_id from state: {parts[0] if parts else 'empty'}")
            pass
        if len(parts) > 1:
            redirect_url = parts[1]
        if len(parts) > 2:
            integration_type = parts[2]

    logger.info(f"Parsed state - user_id: {user_id}, redirect_url: {redirect_url}, integration_type: {integration_type}")

    if not user_id:
        logger.error("Invalid state parameter in Microsoft callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = microsoft_outlook_client.exchange_code_for_token(code)

    if not token_data:
        error_detail = getattr(microsoft_outlook_client, 'last_token_error', None) or "Unknown token exchange error"
        logger.error(f"Failed to exchange Microsoft authorization code: {error_detail}")
        from urllib.parse import quote
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=microsoft_token_exchange_failed&message={quote(error_detail)}"
        )

    # Get user info
    user_info = microsoft_outlook_client.get_user_info(token_data["access_token"])
    user_email = user_info.get("mail") or user_info.get("userPrincipalName") if user_info else None
    ms_user_id = user_info.get("id") if user_info else None

    # Determine provider name based on integration type
    provider = "outlook_calendar" if integration_type == "calendar" else "outlook_email"
    logger.info(f"Integration type '{integration_type}' -> provider '{provider}'")

    # Store tokens in user_integrations table
    try:
        import json as json_module

        # Parse expires_at - could be ISO string or datetime
        expires_at_value = token_data.get("expires_at")
        if isinstance(expires_at_value, str):
            try:
                expires_at_value = datetime.fromisoformat(expires_at_value.replace('Z', '+00:00'))
            except ValueError:
                expires_at_value = datetime.now(timezone.utc) + timedelta(hours=1)

        # Prepare extra_data as JSON string
        extra_data_json = json_module.dumps({
            "token_type": token_data.get("token_type", "Bearer"),
            "integration_type": integration_type
        })

        # Try upsert first (table should exist)
        try:
            db.execute(text("""
                INSERT INTO user_integrations
                    (user_id, provider, access_token, refresh_token, expires_at, email, provider_user_id, scopes, extra_data, updated_at)
                VALUES
                    (:user_id, :provider, :access_token, :refresh_token, :expires_at, :email, :ms_user_id, :scopes,
                     :extra_data::jsonb, CURRENT_TIMESTAMP)
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
                "provider": provider,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": expires_at_value,
                "email": user_email,
                "ms_user_id": ms_user_id,
                "scopes": token_data.get("scope"),
                "extra_data": extra_data_json
            })
            db.commit()
        except Exception as insert_err:
            db.rollback()
            logger.warning(f"Upsert failed, trying simple insert/update: {insert_err}")

            # Try simple approach - check if exists then insert or update
            result = db.execute(text("""
                SELECT id FROM user_integrations WHERE user_id = :user_id AND provider = :provider
            """), {"user_id": user_id, "provider": provider})
            existing = result.fetchone()

            if existing:
                db.execute(text("""
                    UPDATE user_integrations SET
                        access_token = :access_token,
                        refresh_token = :refresh_token,
                        expires_at = :expires_at,
                        email = :email,
                        provider_user_id = :ms_user_id,
                        scopes = :scopes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND provider = :provider
                """), {
                    "user_id": user_id,
                    "provider": provider,
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_at": expires_at_value,
                    "email": user_email,
                    "ms_user_id": ms_user_id,
                    "scopes": token_data.get("scope")
                })
            else:
                db.execute(text("""
                    INSERT INTO user_integrations
                        (user_id, provider, access_token, refresh_token, expires_at, email, provider_user_id, scopes)
                    VALUES
                        (:user_id, :provider, :access_token, :refresh_token, :expires_at, :email, :ms_user_id, :scopes)
                """), {
                    "user_id": user_id,
                    "provider": provider,
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_at": expires_at_value,
                    "email": user_email,
                    "ms_user_id": ms_user_id,
                    "scopes": token_data.get("scope")
                })
            db.commit()

        logger.info(f"Successfully stored Microsoft {provider} tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing Microsoft tokens: {e}")
        db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=microsoft_storage_failed"
        )

    # Redirect back to integrations page with success
    success_param = f"{provider}_connected"
    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success={success_param}"
    )


@router.get("/status/{provider}")
async def microsoft_status(
    provider: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check Microsoft Outlook connection status (provider: outlook_calendar or outlook_email)"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    if provider not in ["outlook_calendar", "outlook_email"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Use 'outlook_calendar' or 'outlook_email'")

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, provider_user_id, scopes
            FROM user_integrations
            WHERE user_id = :user_id AND provider = :provider
        """), {"user_id": user_id, "provider": provider})
        row = result.fetchone()

        if not row:
            return success_response("Not connected", {
                "connected": False,
                "enabled": microsoft_outlook_client.enabled
            })

        # Check if token is expired
        is_expired = False
        if row.expires_at:
            is_expired = datetime.now(timezone.utc) > row.expires_at

        return success_response("Connected", {
            "connected": True,
            "enabled": microsoft_outlook_client.enabled,
            "email": row.email,
            "microsoft_user_id": row.provider_user_id,
            "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })

    except Exception as e:
        logger.error(f"Error checking Microsoft {provider} status: {e}")
        return success_response("Error checking status", {
            "connected": False,
            "enabled": microsoft_outlook_client.enabled,
            "error": "Internal server error"
        })


@router.post("/refresh/{provider}")
async def refresh_microsoft_token(
    provider: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Refresh Microsoft access token"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    if provider not in ["outlook_calendar", "outlook_email"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get current refresh token
        result = db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = :provider
        """), {"user_id": user_id, "provider": provider})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail=f"No {provider} connection found")

        # Refresh the token
        token_data = microsoft_outlook_client.refresh_access_token(row.refresh_token)

        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        # Update stored tokens
        db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token,
                refresh_token = :refresh_token,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = :provider
        """), {
            "user_id": user_id,
            "provider": provider,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at")
        })
        db.commit()

        return success_response("Token refreshed", {
            "refreshed": True,
            "expires_at": token_data.get("expires_at")
        })

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error refreshing Microsoft {provider} token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect/{provider}")
async def disconnect_microsoft(
    provider: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Microsoft integration"""
    if provider not in ["outlook_calendar", "outlook_email"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = :provider
        """), {"user_id": user_id, "provider": provider})
        db.commit()

        return success_response(f"{provider} integration disconnected", {
            "disconnected": True
        })

    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting Microsoft {provider}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# Calendar API Endpoints

@router.get("/calendar/events")
async def list_calendar_events(
    days: int = Query(30, description="Number of days to fetch events for"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List calendar events from Outlook"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'outlook_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Outlook Calendar not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        token_data = microsoft_outlook_client.refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'outlook_calendar'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(days=days)

    events = microsoft_outlook_client.list_events(access_token, start_time=start_time, end_time=end_time)

    if events is None:
        raise HTTPException(status_code=500, detail="Failed to fetch events from Outlook")

    return success_response("Events retrieved", events)


@router.post("/calendar/events")
async def create_calendar_event(
    event: CreateEventRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new calendar event in Outlook"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'outlook_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Outlook Calendar not connected")

    new_event = microsoft_outlook_client.create_event(
        row.access_token,
        subject=event.subject,
        start_time=event.start_time,
        end_time=event.end_time,
        attendees=event.attendees,
        location=event.location,
        body=event.body,
        is_online_meeting=event.is_online_meeting
    )

    if new_event is None:
        raise HTTPException(status_code=500, detail="Failed to create calendar event")

    return success_response("Event created successfully", new_event)


# Email API Endpoints

@router.get("/email/messages")
async def list_email_messages(
    folder: str = Query("inbox", description="Mail folder to fetch from"),
    top: int = Query(25, description="Number of messages to fetch"),
    unread_only: bool = Query(False, description="Only fetch unread messages"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List email messages from Outlook"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'outlook_email'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Outlook Email not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        token_data = microsoft_outlook_client.refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'outlook_email'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    messages = microsoft_outlook_client.list_messages(access_token, folder=folder, top=top, filter_unread=unread_only)

    if messages is None:
        raise HTTPException(status_code=500, detail="Failed to fetch messages from Outlook")

    return success_response("Messages retrieved", messages)


@router.post("/email/send")
async def send_email(
    email: SendEmailRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send an email via Outlook"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'outlook_email'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Outlook Email not connected")

    success = microsoft_outlook_client.send_message(
        row.access_token,
        to_recipients=email.to_recipients,
        subject=email.subject,
        body=email.body,
        cc_recipients=email.cc_recipients,
        is_html=email.is_html
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return success_response("Email sent successfully", {"sent": True})


@router.post("/email/sync")
async def sync_outlook_emails(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync emails from Outlook for the Reconciliation Center"""
    from integrations.microsoft_outlook_service import microsoft_outlook_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    # Get access token
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'outlook_email'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Outlook Email not connected")

    access_token = row.access_token

    # Check if token is expired and refresh if needed
    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        token_data = microsoft_outlook_client.refresh_access_token(row.refresh_token)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = :expires_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'outlook_email'
            """), {
                "user_id": user_id,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    # Fetch recent emails (last 50 unread + recent)
    messages = microsoft_outlook_client.list_messages(access_token, folder="inbox", top=50)

    if messages is None:
        raise HTTPException(status_code=500, detail="Failed to fetch emails from Outlook")

    email_list = messages.get("value", [])
    processed_count = 0
    skipped_count = 0
    errors = []

    # Import the DRE processing function (same pattern as gmail_routes.py)
    from main import process_microsoft_email_to_dre

    for email_data in email_list:
        try:
            result = await process_microsoft_email_to_dre(email_data, user_id, db)
            if result and result.get("status") == "skipped":
                skipped_count += 1
            else:
                processed_count += 1
        except Exception as e:
            logger.error(f"Error processing email {email_data.get('id', 'unknown')}: {e}")
            errors.append(str(e))
            continue

    return success_response(f"Synced {processed_count} emails from Outlook", {
        "synced": True,
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "total_fetched": len(email_list),
        "errors": errors[:5] if errors else []
    })
