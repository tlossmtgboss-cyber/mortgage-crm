"""
Push Notification Routes

Internal API endpoints for triggering push notifications.
All endpoints require authentication.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/push", tags=["Push Notifications"])


class SendNotificationRequest(BaseModel):
    user_id: int
    notification_type: str = "general"
    title: Optional[str] = None
    body: Optional[str] = None
    data: Optional[dict] = None


def setup_push_routes(app, get_current_user):
    """Register push notification routes requiring auth."""

    @app.post("/api/v1/push/send")
    async def send_push_notification(
        request: SendNotificationRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Send a push notification to a specific user. Requires admin/manager role."""
        if current_user.permission_role not in (
            "admin", "site_admin", "platform_admin", "management",
            "branch_manager", "regional_manager", "leadership",
        ):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()
        result = service.send_to_user(
            db=db,
            user_id=request.user_id,
            notification_type=request.notification_type,
            custom_title=request.title,
            custom_body=request.body,
            extra_data=request.data,
        )
        return {"success": True, **result}

    @app.post("/api/v1/push/test")
    async def send_test_notification(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Send a test notification to the current user's devices."""
        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()
        result = service.send_to_user(
            db=db,
            user_id=current_user.id,
            notification_type="general",
            template_data={"title": "Test Notification", "body": "Push notifications are working!"},
        )
        return {"success": True, **result}


# Module-level singleton to preserve lazy-init APNS/FCM clients across calls
_push_service = None


def _get_push_service():
    global _push_service
    if _push_service is None:
        from services.push_notification_service import PushNotificationService
        _push_service = PushNotificationService()
    return _push_service


# Convenience functions for internal use (called from other services)
def notify_lead_assigned(db: Session, user_id: int, lead_name: str, amount: float, loan_purpose: str):
    """Send push notification when a lead is assigned."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id, notification_type="lead_assigned",
        template_data={"lead_name": lead_name, "amount": amount, "loan_purpose": loan_purpose},
        extra_data={"screen": "/leads"},
    )


def notify_appointment_reminder(db: Session, user_id: int, contact_name: str, time: str):
    """Send push notification for upcoming appointment."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id, notification_type="appointment_reminder",
        template_data={"contact_name": contact_name, "time": time},
        extra_data={"screen": "/calendar"},
    )


def notify_briefing_ready(db: Session, user_id: int, active_count: int, at_risk_count: int):
    """Send push notification when morning briefing is ready."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id, notification_type="briefing_ready",
        template_data={"active_count": active_count, "at_risk_count": at_risk_count},
        extra_data={"screen": "/dashboard"},
    )


def notify_document_received(db: Session, user_id: int, doc_type: str, borrower_name: str):
    """Send push notification when a document is received."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id, notification_type="document_received",
        template_data={"doc_type": doc_type, "borrower_name": borrower_name},
        extra_data={"screen": "/documents"},
    )


def notify_sla_alert(db: Session, user_id: int, loan_name: str, milestone: str, hours_remaining: int):
    """Send push notification for SLA warning."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id, notification_type="sla_alert",
        template_data={"loan_name": loan_name, "milestone": milestone, "hours_remaining": hours_remaining},
        extra_data={"screen": "/loans"},
    )
