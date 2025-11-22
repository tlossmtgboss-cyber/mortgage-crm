"""
Gmail Integration Routes

API endpoints for Gmail OAuth authentication and email operations.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import logging
import json

from database import get_db
import os
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from jose import jwt

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("JWT_SECRET", "your-secret-key")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        from sqlalchemy import text
        result = db.execute(text("SELECT id, email, name FROM users WHERE email = :email"), {"email": email})
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        # Return user dict
        return {
            "id": user_row[0],
            "email": user_row[1] if user_row[1] else email,
            "name": user_row[2] if user_row[2] else email.split("@")[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

from integrations.google_gmail import gmail_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gmail", tags=["gmail"])


@router.get("/auth-url")
async def get_gmail_auth_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Gmail OAuth authorization URL.

    Returns URL to redirect user for Gmail permission grant.
    """
    try:
        # Use user ID as state for CSRF protection
        state = f"user_{current_user.id}"
        auth_url = gmail_service.get_auth_url(state=state)

        return {
            "auth_url": auth_url,
            "state": state
        }
    except Exception as e:
        logger.error(f"Error generating Gmail auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def gmail_oauth_callback(
    code: str = Query(...),
    state: str = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle Gmail OAuth callback.

    Exchanges authorization code for tokens and stores them.
    """
    try:
        # Extract user ID from state
        if not state or not state.startswith("user_"):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        user_id = int(state.replace("user_", ""))

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Exchange code for tokens
        token_data = gmail_service.exchange_code(code)

        # Get user info from Gmail
        credentials = gmail_service.get_credentials(token_data)
        gmail_info = gmail_service.get_user_info(credentials)

        # Store tokens in user's settings
        if not user.settings:
            user.settings = {}

        user.settings['gmail_tokens'] = token_data
        user.settings['gmail_email'] = gmail_info.get('email')
        user.settings['gmail_connected'] = True
        user.settings['gmail_connected_at'] = datetime.utcnow().isoformat()

        # Mark settings as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, 'settings')

        db.commit()

        logger.info(f"Gmail connected for user {user_id}: {gmail_info.get('email')}")

        # Return HTML that closes the popup and notifies parent
        return f"""
        <html>
            <body>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'gmail_connected',
                            email: '{gmail_info.get('email')}'
                        }}, '*');
                        window.close();
                    }} else {{
                        window.location.href = '/settings?gmail=connected';
                    }}
                </script>
                <p>Gmail connected successfully! You can close this window.</p>
            </body>
        </html>
        """
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Gmail callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_gmail_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Gmail connection status for current user."""
    settings = current_user.settings or {}

    return {
        "connected": settings.get('gmail_connected', False),
        "email": settings.get('gmail_email'),
        "connected_at": settings.get('gmail_connected_at')
    }


@router.post("/disconnect")
async def disconnect_gmail(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Gmail account."""
    try:
        if not current_user.settings:
            current_user.settings = {}

        # Remove Gmail data
        current_user.settings.pop('gmail_tokens', None)
        current_user.settings.pop('gmail_email', None)
        current_user.settings['gmail_connected'] = False
        current_user.settings.pop('gmail_connected_at', None)

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(current_user, 'settings')

        db.commit()

        return {"success": True, "message": "Gmail disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting Gmail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails")
async def list_emails(
    query: str = Query(None, description="Gmail search query"),
    max_results: int = Query(50, le=100),
    page_token: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List emails from connected Gmail account."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        if not token_data:
            raise HTTPException(status_code=400, detail="Gmail tokens not found")

        credentials = gmail_service.get_credentials(token_data)

        # Check if tokens were refreshed
        if credentials.token != token_data.get('access_token'):
            # Update stored tokens
            current_user.settings['gmail_tokens']['access_token'] = credentials.token
            if credentials.expiry:
                current_user.settings['gmail_tokens']['expiry'] = credentials.expiry.isoformat()

            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(current_user, 'settings')
            db.commit()

        result = gmail_service.list_messages(
            credentials,
            query=query,
            max_results=max_results,
            page_token=page_token
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}")
async def get_email(
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full email details."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        credentials = gmail_service.get_credentials(token_data)

        message = gmail_service.get_message(credentials, message_id)

        return message

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def send_email(
    to: str,
    subject: str,
    body_text: str = None,
    body_html: str = None,
    cc: str = None,
    bcc: str = None,
    reply_to: str = None,
    thread_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send an email through Gmail."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        credentials = gmail_service.get_credentials(token_data)

        result = gmail_service.send_email(
            credentials,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            thread_id=thread_id
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts")
async def list_contacts(
    max_results: int = Query(100, le=500),
    page_token: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List contacts from connected Google account."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        credentials = gmail_service.get_credentials(token_data)

        result = gmail_service.get_contacts(
            credentials,
            max_results=max_results,
            page_token=page_token
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_emails(
    days_back: int = Query(7, le=30, description="Number of days to sync"),
    max_results: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync recent emails from Gmail."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        credentials = gmail_service.get_credentials(token_data)

        since_date = datetime.utcnow() - timedelta(days=days_back)

        emails = gmail_service.sync_emails(
            credentials,
            since_date=since_date,
            max_results=max_results
        )

        return {
            "synced_count": len(emails),
            "emails": emails
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))
