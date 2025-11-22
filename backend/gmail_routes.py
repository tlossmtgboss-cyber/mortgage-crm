"""
Gmail Integration Routes

API endpoints for Gmail OAuth authentication and email operations.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse
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
    from sqlalchemy import text

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user with settings
        result = db.execute(
            text("SELECT id, email, full_name, user_metadata FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        # Create a proxy object to hold user data
        class UserProxy:
            def __init__(self, row, session):
                self.id = row[0]
                self.email = row[1]
                self.name = row[2]
                # Settings stored in user_metadata
                raw_metadata = row[3] if row[3] else {}
                # Handle both dict and JSON string
                if isinstance(raw_metadata, str):
                    try:
                        metadata = json.loads(raw_metadata)
                    except:
                        metadata = {}
                else:
                    metadata = raw_metadata
                self.settings = metadata.get('settings', {}) if isinstance(metadata, dict) else {}
                self._db = session
                self._user_id = row[0]

            def save_settings(self):
                """Save settings back to database in user_metadata"""
                # Get current metadata
                result = self._db.execute(
                    text("SELECT user_metadata FROM users WHERE id = :id"),
                    {"id": self._user_id}
                )
                row = result.fetchone()
                metadata = row[0] if row and row[0] else {}
                metadata['settings'] = self.settings
                self._db.execute(
                    text("UPDATE users SET user_metadata = :metadata WHERE id = :id"),
                    {"metadata": json.dumps(metadata), "id": self._user_id}
                )
                self._db.commit()

        return UserProxy(user_row, db)

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
    current_user= Depends(get_current_user),
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
        from sqlalchemy import text

        # Extract user ID from state
        if not state or not state.startswith("user_"):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        user_id = int(state.replace("user_", ""))

        # Get user metadata
        result = db.execute(
            text("SELECT user_metadata FROM users WHERE id = :id"),
            {"id": user_id}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        # Exchange code for tokens
        token_data = gmail_service.exchange_code(code)

        # Get user info from Gmail
        credentials = gmail_service.get_credentials(token_data)
        gmail_info = gmail_service.get_user_info(credentials)

        # Update settings in user_metadata
        metadata = row[0] if row[0] else {}
        settings = metadata.get('settings', {}) if isinstance(metadata, dict) else {}
        settings['gmail_tokens'] = token_data
        settings['gmail_email'] = gmail_info.get('email')
        settings['gmail_connected'] = True
        settings['gmail_connected_at'] = datetime.utcnow().isoformat()
        metadata['settings'] = settings

        # Save metadata back to database
        db.execute(
            text("UPDATE users SET user_metadata = :metadata WHERE id = :id"),
            {"metadata": json.dumps(metadata), "id": user_id}
        )
        db.commit()

        logger.info(f"Gmail connected for user {user_id}: {gmail_info.get('email')}")

        # Return HTML that closes the popup and notifies parent
        html_content = f"""
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
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Gmail callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_gmail_status(
    current_user= Depends(get_current_user),
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
    current_user= Depends(get_current_user),
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

        # Save settings
        current_user.save_settings()

        return {"success": True, "message": "Gmail disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting Gmail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails")
async def list_emails(
    query: str = Query(None, description="Gmail search query"),
    max_results: int = Query(50, le=100),
    page_token: str = Query(None),
    current_user= Depends(get_current_user),
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

            # Save settings
            current_user.save_settings()

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
    current_user= Depends(get_current_user),
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
    current_user= Depends(get_current_user),
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
    current_user= Depends(get_current_user),
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
    force: bool = Query(False, description="Force reprocess existing emails"),
    current_user= Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync recent emails from Gmail and process them for reconciliation."""
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

        # Process emails through extraction pipeline for reconciliation
        from main import process_microsoft_email_to_dre, IncomingDataEvent, ExtractedData
        from sqlalchemy import text

        processed_count = 0
        for email in emails:
            try:
                email_id = email.get("id", "")

                # If force=True, delete existing records for this email
                if force and email_id:
                    existing = db.query(IncomingDataEvent).filter(
                        IncomingDataEvent.external_message_id == email_id,
                        IncomingDataEvent.user_id == current_user.id
                    ).first()
                    if existing:
                        # Delete associated ExtractedData first
                        db.query(ExtractedData).filter(
                            ExtractedData.event_id == existing.id
                        ).delete()
                        db.delete(existing)
                        db.commit()

                # Convert Gmail format to Microsoft-like format for processing
                email_data = {
                    "id": email_id,
                    "subject": email.get("subject", ""),
                    "from": {
                        "emailAddress": {
                            "address": email.get("from", "")
                        }
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": email.get("to", "")}}
                    ] if email.get("to") else [],
                    "receivedDateTime": email.get("date", ""),
                    "body": {
                        "contentType": "text" if email.get("body_text") else "html",
                        "content": email.get("body_text") or email.get("body_html", "")
                    }
                }

                result = await process_microsoft_email_to_dre(email_data, current_user.id, db)
                if result.get("status") != "skipped":
                    processed_count += 1

            except Exception as e:
                logger.warning(f"Error processing email {email.get('id', 'unknown')}: {e}")
                continue

        return {
            "synced_count": len(emails),
            "processed_count": processed_count,
            "emails": emails
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))
