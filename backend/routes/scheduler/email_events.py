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
from sqlalchemy import Column, Integer, String, DateTime, Text, and_
from datetime import datetime, timezone
from typing import Optional
import base64
import hashlib
import hmac
import logging
import os

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from routes.scheduler._rate_limiting import _check_rate_limit
from db import get_db, Base

logger = logging.getLogger(__name__)

router = APIRouter()

# SendGrid Event Webhook verification key
_SENDGRID_WEBHOOK_KEY = os.getenv("SENDGRID_WEBHOOK_VERIFICATION_KEY")


def _resolve_org_id_for_email(email: str, db: Session) -> Optional[int]:
    """Resolve organization_id from the most recent appointment matching this attendee email.

    Used when processing public-facing events (SendGrid webhooks, unsubscribe)
    where we have no authenticated user context. Returns None if no match found.
    """
    if not email:
        return None
    try:
        from database.models.scheduler import Appointment
        row = db.query(Appointment.organization_id).filter(
            Appointment.attendee_email == email.lower().strip()
        ).order_by(Appointment.created_at.desc()).first()
        if row:
            return row.organization_id
    except Exception as e:
        logger.warning("Could not resolve org_id for email event: %s", e)
    return None


# ============================================================================
# DB-BACKED EMAIL SUPPRESSION MODEL
# ============================================================================

class EmailSuppression(Base):
    """Persistent email suppression list — survives deploys."""
    __tablename__ = "email_suppressions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(320), nullable=False, index=True, unique=True)
    reason = Column(Text, nullable=True)
    event_type = Column(String(50), nullable=False)
    organization_id = Column(Integer, nullable=True, index=True)
    suppressed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def _ensure_suppression_table():
    """Create the email_suppressions table if it doesn't exist."""
    try:
        from db import engine
        EmailSuppression.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Could not create email_suppressions table: {e}")


# Auto-create on module load
_ensure_suppression_table()


def is_email_suppressed(email: str, db: Optional[Session] = None) -> bool:
    """Check if an email address is on the suppression list."""
    if not email:
        return False
    email_lower = email.lower().strip()

    if db is None:
        from db import SessionLocal
        session = SessionLocal()
        try:
            return session.query(EmailSuppression).filter(
                EmailSuppression.email == email_lower
            ).first() is not None
        finally:
            session.close()

    return db.query(EmailSuppression).filter(
        EmailSuppression.email == email_lower
    ).first() is not None


def add_email_suppression(email: str, reason: str, event_type: str, org_id: int = None, db: Optional[Session] = None):
    """Add an email to the suppression list (DB-backed, survives deploys)."""
    if not email:
        return
    email_lower = email.lower().strip()

    close_session = False
    if db is None:
        from db import SessionLocal
        db = SessionLocal()
        close_session = True

    try:
        existing = db.query(EmailSuppression).filter(
            EmailSuppression.email == email_lower
        ).first()

        if existing:
            existing.reason = reason[:500] if reason else event_type
            existing.event_type = event_type
            existing.suppressed_at = datetime.now(timezone.utc)
            if org_id is not None:
                existing.organization_id = org_id
        else:
            db.add(EmailSuppression(
                email=email_lower,
                reason=reason[:500] if reason else event_type,
                event_type=event_type,
                organization_id=org_id,
                suppressed_at=datetime.now(timezone.utc),
            ))

        db.commit()
        masked = f"{email_lower[:2]}***@{email_lower.split('@')[-1] if '@' in email_lower else '***'}"
        logger.info(f"Email suppressed: {masked} ({event_type})")
    except Exception as e:
        db.rollback()
        logger.exception("Failed to add email suppression: %s", e)
    finally:
        if close_session:
            db.close()


def remove_email_suppression(email: str, db: Optional[Session] = None) -> bool:
    """Remove an email from the suppression list. Returns True if it was present."""
    if not email:
        return False
    email_lower = email.lower().strip()

    close_session = False
    if db is None:
        from db import SessionLocal
        db = SessionLocal()
        close_session = True

    try:
        row = db.query(EmailSuppression).filter(
            EmailSuppression.email == email_lower
        ).first()
        if row:
            db.delete(row)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        logger.exception("Failed to remove email suppression: %s", e)
        return False
    finally:
        if close_session:
            db.close()


# ============================================================================
# HMAC-SIGNED UNSUBSCRIBE TOKENS
# ============================================================================

def _get_unsubscribe_secret() -> str:
    """Get the secret key for HMAC signing, reading at call time."""
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SECRET_KEY required for unsubscribe tokens")
    return secret


def _generate_unsubscribe_token(email: str) -> str:
    """Generate an HMAC-signed unsubscribe token for an email address."""
    secret = _get_unsubscribe_secret()
    email_b64 = base64.urlsafe_b64encode(email.lower().strip().encode()).decode()
    sig = hmac.new(secret.encode(), email_b64.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{email_b64}.{sig}"


def _verify_unsubscribe_token(token: str) -> str:
    """Verify an HMAC-signed unsubscribe token. Returns the email address."""
    secret = _get_unsubscribe_secret()
    if not token or "." not in token:
        raise ValueError("Invalid unsubscribe token")

    parts = token.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError("Invalid unsubscribe token")

    email_b64, received_sig = parts

    expected_sig = hmac.new(secret.encode(), email_b64.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(received_sig, expected_sig):
        raise ValueError("Invalid unsubscribe token")

    try:
        email = base64.urlsafe_b64decode(email_b64.encode()).decode("utf-8")
    except Exception as e:
        logger.debug(f"Failed to decode unsubscribe token: {e}")
        raise ValueError("Invalid unsubscribe token")

    if not email or "@" not in email:
        raise ValueError("Invalid unsubscribe token")

    return email


# ============================================================================
# SENDGRID EVENT WEBHOOK (with verification)
# ============================================================================

@router.post("/email-events/sendgrid", status_code=200)
async def sendgrid_event_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive SendGrid Event Webhook notifications.

    Processes bounce, dropped, spamreport, and unsubscribe events
    to maintain an email suppression list. Prevents sending to addresses
    that have bounced or complained — protecting sender reputation.

    Reference: https://docs.sendgrid.com/for-developers/tracking-events/event
    """
    await _check_rate_limit(request, max_requests=100)

    # Verify SendGrid webhook signature if verification key is configured
    if _SENDGRID_WEBHOOK_KEY:
        sg_signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        sg_timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")

        if not sg_signature or not sg_timestamp:
            logger.warning("SendGrid webhook missing verification headers")
            raise HTTPException(status_code=401, detail="Missing webhook signature")

        # Verify the timestamp + payload signature
        body = await request.body()
        verification_payload = sg_timestamp.encode() + body
        expected_sig = hmac.new(
            _SENDGRID_WEBHOOK_KEY.encode(),
            verification_payload,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(sg_signature, expected_sig):
            logger.warning("SendGrid webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # Parse the verified body
        import json
        try:
            events = json.loads(body)
        except Exception as e:
            logger.debug(f"Failed to parse SendGrid webhook JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
    else:
        # No verification key configured — accept but log warning
        logger.warning("SENDGRID_WEBHOOK_VERIFICATION_KEY not set — webhook not verified")
        try:
            events = await request.json()
        except Exception as e:
            logger.debug(f"Failed to parse SendGrid webhook JSON (unverified): {e}")
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
            org_id = _resolve_org_id_for_email(email, db)
            if org_id is None:
                logger.warning("Could not resolve org_id for SendGrid %s event (email: %s)",
                               event_type, email[:3] + "***")
            add_email_suppression(
                email=email,
                reason=reason[:500],
                event_type=event_type,
                org_id=org_id,
                db=db,
            )
            processed += 1

    logger.info(f"SendGrid webhook: processed {processed} suppression events from {len(events)} total")
    return {"processed": processed}


# ============================================================================
# UNSUBSCRIBE ENDPOINT (RFC 8058 List-Unsubscribe-Post compatible)
# ============================================================================

@router.post("/email-events/unsubscribe/{token}", status_code=200)
async def unsubscribe_post(token: str, request: Request, db: Session = Depends(get_db)):
    """
    RFC 8058 one-click unsubscribe handler.

    Email clients (Gmail, Apple Mail) send a POST to this URL when the
    user clicks the native unsubscribe button. The token is HMAC-signed
    to prevent forgery.
    """
    await _check_rate_limit(request, max_requests=30)

    try:
        email = _verify_unsubscribe_token(token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    org_id = _resolve_org_id_for_email(email, db)
    if org_id is None:
        logger.warning("Could not resolve org_id for List-Unsubscribe event (email: %s)",
                        email[:3] + "***")
    add_email_suppression(
        email=email,
        reason="User unsubscribed via List-Unsubscribe",
        event_type="unsubscribe",
        org_id=org_id,
        db=db,
    )

    return {"success": True, "message": "You have been unsubscribed."}


@router.get("/email-events/unsubscribe/{token}", status_code=200)
async def unsubscribe_page(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Browser-based unsubscribe confirmation.

    Returns a simple HTML page confirming the unsubscribe action.
    """
    await _check_rate_limit(request, max_requests=30)

    try:
        email = _verify_unsubscribe_token(token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    org_id = _resolve_org_id_for_email(email, db)
    if org_id is None:
        logger.warning("Could not resolve org_id for browser unsubscribe event (email: %s)",
                        email[:3] + "***")
    add_email_suppression(
        email=email,
        reason="User unsubscribed via browser link",
        event_type="unsubscribe",
        org_id=org_id,
        db=db,
    )

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content="""
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

    query = db.query(EmailSuppression)
    if org_id:
        query = query.filter(
            (EmailSuppression.organization_id == org_id) |
            (EmailSuppression.organization_id.is_(None))
        )

    suppressions = query.order_by(EmailSuppression.suppressed_at.desc()).limit(500).all()

    items = [
        {
            "id": s.id,
            "email": s.email,
            "reason": s.reason,
            "event_type": s.event_type,
            "suppressed_at": s.suppressed_at.isoformat() if s.suppressed_at else None,
        }
        for s in suppressions
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

    removed = remove_email_suppression(email, db=db)

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
