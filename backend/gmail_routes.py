"""
Gmail Integration Routes

API endpoints for Gmail OAuth authentication and email operations.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timedelta, timezone
import logging
import json

from database import get_db
import os
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

# Auth dependency
from auth.dependencies import get_current_user  # dedup: was local wrapper
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        settings['gmail_connected_at'] = datetime.now(timezone.utc).isoformat()
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        # Make a copy to avoid in-place mutation issues
        settings = dict(current_user.settings or {})
        settings.pop('gmail_tokens', None)
        settings.pop('gmail_email', None)
        settings['gmail_connected'] = False
        settings.pop('gmail_connected_at', None)

        # Read current metadata, update settings, write back
        result = db.execute(
            text("SELECT user_metadata FROM users WHERE id = :id"),
            {"id": current_user.id}
        )
        row = result.fetchone()
        metadata = row[0] if row and row[0] else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        metadata['settings'] = settings
        db.execute(
            text("UPDATE users SET user_metadata = :metadata WHERE id = :id"),
            {"metadata": json.dumps(metadata), "id": current_user.id}
        )
        db.commit()

        return {"success": True, "message": "Gmail disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting Gmail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
            # Make a copy to avoid in-place mutation issues
            settings = dict(current_user.settings or {})
            tokens = dict(settings.get('gmail_tokens', {}))
            tokens['access_token'] = credentials.token
            if credentials.expiry:
                tokens['expiry'] = credentials.expiry.isoformat()
            settings['gmail_tokens'] = tokens

            # Read current metadata, update settings, write back
            result = db.execute(
                text("SELECT user_metadata FROM users WHERE id = :id"),
                {"id": current_user.id}
            )
            row = result.fetchone()
            metadata = row[0] if row and row[0] else {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata['settings'] = settings
            db.execute(
                text("UPDATE users SET user_metadata = :metadata WHERE id = :id"),
                {"metadata": json.dumps(metadata), "id": current_user.id}
            )
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
    include_signature: bool = True,
    current_user= Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send an email through Gmail with automatic signature."""
    try:
        settings = current_user.settings or {}

        if not settings.get('gmail_connected'):
            raise HTTPException(status_code=400, detail="Gmail not connected")

        token_data = settings.get('gmail_tokens')
        credentials = gmail_service.get_credentials(token_data)

        # Append email signature if enabled
        final_body_html = body_html
        final_body_text = body_text

        if include_signature:
            try:
                # Get user's email signature from main app
                from database.models import EmailSignature
                from utils.email_signature import generate_email_signature_html
                signature = db.execute(
                    text("SELECT * FROM email_signatures WHERE user_id = :user_id"),
                    {"user_id": current_user._user_id}
                ).fetchone()

                if signature:
                    # Convert row to dict-like object for generate_email_signature_html
                    class SigProxy:
                        def __init__(self, row):
                            cols = ['id', 'user_id', 'full_name', 'title', 'team_name', 'headshot_url',
                                   'company_logo_url', 'email', 'office_phone', 'cell_phone', 'fax',
                                   'address', 'website_url', 'apply_now_url', 'doc_upload_url',
                                   'schedule_url', 'linkedin_url', 'facebook_url', 'instagram_url',
                                   'twitter_url', 'nmls_id', 'branch_nmls_id', 'corporate_nmls_id',
                                   'primary_color', 'secondary_color', 'tagline', 'is_active',
                                   'created_at', 'updated_at']
                            for i, col in enumerate(cols):
                                if i < len(row):
                                    setattr(self, col, row[i])
                                else:
                                    setattr(self, col, None)

                    sig_obj = SigProxy(signature)
                    signature_html = generate_email_signature_html(sig_obj)

                    if final_body_html:
                        final_body_html = f"{final_body_html}<br><br>{signature_html}"
                    elif final_body_text:
                        # Wrap text in HTML and add signature
                        final_body_html = f"<div>{final_body_text.replace(chr(10), '<br>')}</div><br><br>{signature_html}"
                        final_body_text = None  # Use HTML version instead
            except Exception as sig_error:
                logger.warning(f"Could not append signature: {sig_error}")
                # Continue without signature

        result = gmail_service.send_email(
            credentials,
            to=to,
            subject=subject,
            body_text=final_body_text,
            body_html=final_body_html,
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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

        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        emails = gmail_service.sync_emails(
            credentials,
            since_date=since_date,
            max_results=max_results
        )

        # Process emails through extraction pipeline for reconciliation
        from database.models import IncomingDataEvent, ExtractedData
        from services.dre_helpers import process_microsoft_email_to_dre
        from sqlalchemy import text

        processed_count = 0
        errors = []
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
                        try:
                            # Delete ai_training_events that reference extracted_data first
                            db.execute(
                                text("""
                                    DELETE FROM ai_training_events
                                    WHERE extracted_data_id IN (
                                        SELECT id FROM extracted_data WHERE event_id = :event_id
                                    )
                                """),
                                {"event_id": existing.id}
                            )
                            # Delete associated ExtractedData
                            db.query(ExtractedData).filter(
                                ExtractedData.event_id == existing.id
                            ).delete()
                            db.delete(existing)
                            db.commit()
                        except Exception as del_error:
                            logger.warning(f"Error deleting existing email {email_id}: {del_error}")
                            db.rollback()
                            continue  # Skip this email and continue with others

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
                if result.get("status") == "error":
                    errors.append(f"{email_id}: {result.get('error', 'unknown')}")
                elif result.get("status") != "skipped":
                    processed_count += 1

            except Exception as e:
                logger.error(f"Error processing email {email.get('id', 'unknown')}: {e}")
                errors.append(f"{email.get('id', 'unknown')}: {str(e)}")
                continue

        return {
            "synced_count": len(emails),
            "processed_count": processed_count,
            "user_id": current_user.id,
            "errors": errors if errors else None,
            "emails": emails
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing emails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cron-sync")
async def cron_sync_all_gmail(
    api_key: str = Query(..., description="API key for cron authentication"),
    days_back: int = Query(1, le=7, description="Number of days to sync"),
    max_results: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """
    Cron job endpoint to sync Gmail for all connected users.
    Called by Railway cron service every minute.

    Requires CRON_API_KEY environment variable for authentication.
    """
    from sqlalchemy import text

    # Verify API key
    expected_key = os.getenv("CRON_API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Find all users with Gmail connected
        result = db.execute(
            text("""
                SELECT id, email, full_name, user_metadata
                FROM users
                WHERE user_metadata::jsonb ->> 'gmail_connected' = 'true'
                   OR user_metadata::text LIKE :pattern1
                   OR user_metadata::text LIKE :pattern2
            """),
            {"pattern1": '%"gmail_connected": true%', "pattern2": '%"gmail_connected":true%'}
        )
        users_with_gmail = result.fetchall()

        if not users_with_gmail:
            return {
                "status": "success",
                "message": "No users with Gmail connected",
                "users_synced": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        sync_results = []
        total_emails_synced = 0
        total_processed = 0

        for user_row in users_with_gmail:
            user_id = user_row[0]
            user_email = user_row[1]
            settings = user_row[3] or {}

            if isinstance(settings, str):
                try:
                    settings = json.loads(settings)
                except Exception as e:
                    logger.exception(f"Failed to parse Gmail settings JSON: {e}")
                    settings = {}

            token_data = settings.get('gmail_tokens')
            if not token_data:
                sync_results.append({
                    "user_id": user_id,
                    "email": user_email,
                    "status": "skipped",
                    "reason": "No Gmail tokens found"
                })
                continue

            try:
                credentials = gmail_service.get_credentials(token_data)
                since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

                emails = gmail_service.sync_emails(
                    credentials,
                    since_date=since_date,
                    max_results=max_results
                )

                # Process emails through extraction pipeline
                from database.models import IncomingDataEvent, ExtractedData
                from services.dre_helpers import process_microsoft_email_to_dre

                # Also queue ALL emails to Email Intelligence system
                queued_to_intelligence = 0
                try:
                    from routes.email_intelligence_routes import queue_email_for_intelligence
                    for email in emails:
                        intel_email_data = {
                            "email_provider": "gmail",
                            "provider_message_id": email.get("id", ""),
                            "thread_id": email.get("thread_id"),
                            "from_email": email.get("from", ""),
                            "from_name": email.get("from_name", ""),
                            "to_emails": [email.get("to", "")] if email.get("to") else [],
                            "cc_emails": email.get("cc", []),
                            "subject": email.get("subject", ""),
                            "body_preview": (email.get("body_text") or email.get("body_html", ""))[:500],
                            "body_full": email.get("body_text"),
                            "body_html": email.get("body_html"),
                            "sent_date": email.get("date"),
                            "received_date": email.get("date"),
                            "has_attachments": bool(email.get("attachments")),
                            "attachment_count": len(email.get("attachments", [])),
                            "attachment_names": [a.get("filename", "") for a in email.get("attachments", [])],
                            "direction": "inbound"  # Gmail sync is typically inbox
                        }
                        result = await queue_email_for_intelligence(
                            db=db,
                            user_id=user_id,
                            email_data=intel_email_data,
                            auto_analyze=False,  # Don't auto-analyze during sync (too slow)
                            source="gmail_sync"
                        )
                        if result.get("status") == "queued":
                            queued_to_intelligence += 1
                except Exception as intel_error:
                    logger.warning(f"Email Intelligence queue error for user {user_id}: {intel_error}")

                processed_count = 0
                for email in emails:
                    try:
                        email_id = email.get("id", "")

                        # Check if already processed
                        existing = db.execute(
                            text("""
                                SELECT id FROM incoming_data_events
                                WHERE external_message_id = :email_id AND user_id = :user_id
                            """),
                            {"email_id": email_id, "user_id": user_id}
                        ).fetchone()

                        if existing:
                            continue  # Skip already processed

                        # Convert Gmail format to Microsoft-like format
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

                        result = await process_microsoft_email_to_dre(email_data, user_id, db)
                        if result.get("status") not in ["error", "skipped"]:
                            processed_count += 1

                    except Exception as e:
                        logger.warning(f"Error processing email for user {user_id}: {e}")
                        continue

                total_emails_synced += len(emails)
                total_processed += processed_count

                # Update last sync time
                db.execute(
                    text("""
                        UPDATE users
                        SET user_metadata = jsonb_set(
                            COALESCE(user_metadata, '{}'::jsonb),
                            '{gmail_last_sync}',
                            to_jsonb(:sync_time::text)
                        )
                        WHERE id = :user_id
                    """),
                    {"user_id": user_id, "sync_time": datetime.now(timezone.utc).isoformat()}
                )
                db.commit()

                sync_results.append({
                    "user_id": user_id,
                    "email": user_email,
                    "status": "success",
                    "emails_fetched": len(emails),
                    "emails_processed": processed_count,
                    "emails_queued_to_intelligence": queued_to_intelligence
                })

            except Exception as e:
                logger.error(f"Error syncing Gmail for user {user_id}: {e}")
                sync_results.append({
                    "user_id": user_id,
                    "email": user_email,
                    "status": "error",
                    "error": "Internal server error"
                })
                db.rollback()
                continue

        return {
            "status": "success",
            "users_synced": len([r for r in sync_results if r["status"] == "success"]),
            "total_users": len(users_with_gmail),
            "total_emails_fetched": total_emails_synced,
            "total_emails_processed": total_processed,
            "results": sync_results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Cron Gmail sync error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
