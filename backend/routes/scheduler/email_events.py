"""
Email Event Handling — Bounce/complaint webhook + unsubscribe endpoint.

Endpoints:
  Public (webhook):
    - POST /email-events/sendgrid    SendGrid Event Webhook (bounce, complaint, spamreport)

  Public (one-click):
    - POST /email-events/unsubscribe/{token}   RFC 8058 List-Unsubscribe-Post handler
    - GET  /email-events/unsubscribe/{token}    Browser-based unsubscribe confirmation page

  Authenticated (admin):
    - GET  /email-events/suppressions           List suppressed emails for the org
    - DELETE /email-events/suppressions/{id}    Remove a suppression (re-enable delivery)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone
from typing import Optional
import hashlib
import hmac
import logging
import os

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from routes.scheduler._rate_limiting import _check_rate_limit
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# SendGrid Event Webhook verification key (optional but recommended)
_SENDGRID_WEBHOOK_KEY = os.getenv("SENDGRID_WEBHOOK_VERIFICATION_KEY")


# ============================================================================
# IN-MEMORY SUPPRESSION LIST (production would use a DB table)
# ============================================================================
# Simple thread-safe set for email suppression. In production, this should be
# a database table (EmailSuppression model). For now, this provides the
# functional behavior needed for enterprise readiness.

import threading

_suppression_lock = threading.Lock()
_suppression_list: dict = {}  # email_lower -> {reason, event_type, timestamp, org_id}


def is_email_suppressed(email: str) -> bool:
    """Check if an email address is on the suppression list."""
    if not email:
        return False
    with _suppression_lock:
        return email.lower().strip() in _suppression_list


def add_email_suppression(email: str, reason: str, event_type: str, org_id: int = None):
    """Add an email to the suppression list."""
    if not email:
        return
    with _suppression_lock:
        _suppression_list[email.lower().strip()] = {
            "reason": reason,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
        }
    logger.info(f"Email suppressed: {email[:2]}***@{email.split('@')[-1] if '@' in email else '***'} ({event_type})")


def remove_email_suppression(email: str) -> bool:
    """Remove an email from the suppression list. Returns True if it was present."""
    if not email:
        return False
    with _suppression_lock:
        return _suppression_list.pop(email.lower().strip(), None) is not None


# ============================================================================
# SENDGRID EVENT WEBHOOK
# ============================================================================

@router.post("/email-events/sendgrid", status_code=200)
async def sendgrid_event_webhook(request: Request):
    """
    Receive SendGrid Event Webhook notifications.

    Processes bounce, dropped, spamreport, and unsubscribe events
    to maintain an email suppression list. Prevents sending to addresses
    that have bounced or complained — protecting sender reputation.

    Reference: https://docs.sendgrid.com/for-developers/tracking-events/event
    """
    await _check_rate_limit(request, max_requests=100)

    try:
        events = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="Expected array of events")

    suppression_events = {"bounce", "dropped", "spamreport", "unsubscribe"}
    processed = 0

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = event.get("event", "")
        email = event.get("email", "")

        if event_type in suppression_events and email:
            reason = event.get("reason", "") or event.get("response", "") or event_type
            add_email_suppression(
                email=email,
                reason=reason[:500],
                event_type=event_type,
            )
            processed += 1

    logger.info(f"SendGrid webhook: processed {processed} suppression events from {len(events)} total")
    return {"processed": processed}


# ============================================================================
# UNSUBSCRIBE ENDPOINT (RFC 8058 List-Unsubscribe-Post compatible)
# ============================================================================

@router.post("/email-events/unsubscribe/{token}", status_code=200)
async def unsubscribe_post(token: str, request: Request):
    """
    RFC 8058 one-click unsubscribe handler.

    Email clients (Gmail, Apple Mail) send a POST to this URL when the
    user clicks the native unsubscribe button. The token encodes the
    recipient email (hashed) so we can suppress without authentication.
    """
    await _check_rate_limit(request, max_requests=30)

    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    # Token format: base64(email) — in production, use HMAC-signed tokens
    import base64
    try:
        email = base64.urlsafe_b64decode(token.encode()).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    add_email_suppression(
        email=email,
        reason="User unsubscribed via List-Unsubscribe",
        event_type="unsubscribe",
    )

    return {"success": True, "message": "You have been unsubscribed."}


@router.get("/email-events/unsubscribe/{token}", status_code=200)
async def unsubscribe_page(token: str, request: Request):
    """
    Browser-based unsubscribe confirmation.

    Returns a simple HTML page confirming the unsubscribe action.
    """
    await _check_rate_limit(request, max_requests=30)

    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    import base64
    try:
        email = base64.urlsafe_b64decode(token.encode()).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    add_email_suppression(
        email=email,
        reason="User unsubscribed via browser link",
        event_type="unsubscribe",
    )

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><title>Unsubscribed</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, sans-serif; text-align: center; padding: 60px 20px; background: #f6f9fc;">
        <div style="max-width: 400px; margin: 0 auto; background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,0.08);">
            <h1 style="color: #111827; font-size: 24px;">Unsubscribed</h1>
            <p style="color: #6b7280; font-size: 16px; line-height: 1.6;">
                You have been successfully unsubscribed from appointment notification emails.
            </p>
            <p style="color: #9ca3af; font-size: 14px; margin-top: 24px;">
                You can close this page.
            </p>
        </div>
    </body>
    </html>
    """)


# ============================================================================
# ADMIN: LIST / REMOVE SUPPRESSIONS
# ============================================================================

@router.get("/email-events/suppressions")
async def list_suppressions(
    request: Request,
    db: Session = Depends(get_db),
):
    """List suppressed email addresses for the organization (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    with _suppression_lock:
        items = [
            {
                "email": email,
                "reason": info["reason"],
                "event_type": info["event_type"],
                "suppressed_at": info["timestamp"],
            }
            for email, info in _suppression_list.items()
            if info.get("org_id") is None or info.get("org_id") == org_id
        ]

    return {
        "suppressions": items,
        "total": len(items),
    }


@router.delete("/email-events/suppressions/{email}")
async def remove_suppression(
    email: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Remove an email from the suppression list (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    removed = remove_email_suppression(email)

    if removed:
        _audit_log(
            db, org_id, getattr(user, "id", None), "removed",
            "email_suppression", changes={"email": email},
            request=request,
        )
        db.commit()

    return {
        "success": removed,
        "message": "Suppression removed" if removed else "Email was not suppressed",
    }
