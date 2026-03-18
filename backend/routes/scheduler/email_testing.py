"""
Scheduler Email Testing - Email service status and test endpoints.

Endpoints:
  - GET    /email-service-status     Check if email service is configured
  - POST   /test-email               Send a test email (admin only)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import html
import logging
import os

from services.notification_service import notification_service

from routes.scheduler._helpers import (
    get_current_user, _is_scheduler_admin,
)
from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/email-service-status")
async def get_email_service_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if email service is properly configured (authenticated)"""
    sendgrid_configured = bool(os.getenv("SENDGRID_API_KEY"))
    sendgrid_from_email = os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL)

    return {
        "sendgrid_configured": sendgrid_configured,
        "from_email": sendgrid_from_email,
        "status": "ready" if sendgrid_configured else "not_configured",
        "message": "Email service is ready to send" if sendgrid_configured else "SendGrid API key not configured - emails will be logged only (dry run)"
    }


@router.post("/test-email")
async def test_email_send(
    to_email: str = Query(..., description="Email address to send test to"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test endpoint to send a test email (authenticated, admin-only)"""
    # Require admin role
    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        time_sent = datetime.now(timezone.utc).isoformat()
        result = notification_service.send_email(
            to_email=to_email,
            subject="Test Email from Perennia CRM",
            html_content=f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Test Email</h2>
                <p>This is a test email from Perennia CRM to verify SendGrid is working.</p>
                <p>Time sent: {html.escape(time_sent)}</p>
            </body>
            </html>
            """,
            plain_content=f"Test email from Perennia CRM. Time: {time_sent}"
        )

        return {
            "test_result": result,
            "to_email": to_email,
            "from_email": os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL),
            "sendgrid_key_present": bool(os.getenv("SENDGRID_API_KEY")),
        }
    except Exception as e:
        logger.exception(f"Test email failed: {e}")
        return {
            "test_result": {"success": False, "error": "Email send failed"},
            "to_email": to_email
        }
