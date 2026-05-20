"""
Push Notification Routes

API endpoints for push notification token management, preferences, and sending.
Includes both public-facing endpoints (register/unregister/preferences) and
internal convenience functions used by other services.

All user-facing endpoints require authentication.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import get_db, get_async_db

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class RegisterTokenRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=500)
    platform: str = Field(default="ios", pattern="^(ios|android|web)$")
    device_name: Optional[str] = Field(default=None, max_length=200)
    app_version: Optional[str] = Field(default=None, max_length=50)


class UnregisterTokenRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=500)


class UpdatePreferencesRequest(BaseModel):
    categories: Optional[Dict[str, bool]] = None
    muted: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(default=None, pattern="^[0-2][0-9]:[0-5][0-9]$")
    quiet_hours_end: Optional[str] = Field(default=None, pattern="^[0-2][0-9]:[0-5][0-9]$")


class SendNotificationRequest(BaseModel):
    user_id: int
    notification_type: str = "general"
    title: Optional[str] = None
    body: Optional[str] = None
    data: Optional[dict] = None


class TestNotificationRequest(BaseModel):
    title: Optional[str] = "Test Notification"
    body: Optional[str] = "Push notifications are working!"


# =============================================================================
# Route setup (called from _register_auth_security.py)
# =============================================================================

def setup_push_routes(app, get_current_user):
    """Register push notification routes that require authentication.

    This function creates route handlers as closures over get_current_user
    to avoid circular import issues with auth dependencies.
    """

    # -----------------------------------------------------------------
    # GET /api/v1/notifications/vapid-key — VAPID public key for web push
    # -----------------------------------------------------------------
    @app.get("/api/v1/notifications/vapid-key")
    async def get_vapid_key():
        """Return VAPID public key for web push subscriptions.

        Returns null key when VAPID is not configured — frontend falls
        back to basic web notifications.
        """
        import os
        vapid_key = os.getenv("VAPID_PUBLIC_KEY")
        return {"vapid_public_key": vapid_key}

    # -----------------------------------------------------------------
    # POST /api/v1/push/register — Register device token
    # -----------------------------------------------------------------
    @app.post("/api/v1/push/register")
    async def register_device_token(
        request: RegisterTokenRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Register a device token for push notifications.

        Called from the mobile app after obtaining an APNs or FCM token.
        If the token already exists for this user, it is reactivated.
        """
        from database.models.device_token import DeviceToken

        try:
            # Check if token already exists for this user
            existing = db.query(DeviceToken).filter(
                DeviceToken.user_id == current_user.id,
                DeviceToken.device_token == request.device_token,
            ).first()

            if existing:
                existing.is_active = True
                existing.platform = request.platform
                existing.failure_count = 0
                existing.device_name = request.device_name or existing.device_name
                existing.app_version = request.app_version or existing.app_version
                existing.organization_id = getattr(current_user, "organization_id", None)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Deactivate any other tokens with the same device_token
                # (handles token reassignment to a different user)
                db.query(DeviceToken).filter(
                    DeviceToken.device_token == request.device_token,
                    DeviceToken.user_id != current_user.id,
                ).update({"is_active": False})

                new_token = DeviceToken(
                    user_id=current_user.id,
                    organization_id=getattr(current_user, "organization_id", None),
                    device_token=request.device_token,
                    platform=request.platform,
                    device_name=request.device_name,
                    app_version=request.app_version,
                    is_active=True,
                    failure_count=0,
                )
                db.add(new_token)

            db.commit()
            logger.info(
                "Push token registered for user %d on %s",
                current_user.id, request.platform,
            )

            return {
                "success": True,
                "message": "Device token registered successfully",
            }

        except Exception as e:
            logger.error("Error registering push token: %s", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to register device token")

    # -----------------------------------------------------------------
    # POST /api/v1/push/unregister — Unregister device token
    # -----------------------------------------------------------------
    @app.post("/api/v1/push/unregister")
    async def unregister_device_token(
        request: UnregisterTokenRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Unregister a device token (e.g., on logout or app uninstall).

        Marks the token as inactive rather than deleting it, preserving
        the audit trail.
        """
        from database.models.device_token import DeviceToken

        try:
            updated = db.query(DeviceToken).filter(
                DeviceToken.user_id == current_user.id,
                DeviceToken.device_token == request.device_token,
            ).update({
                "is_active": False,
                "updated_at": datetime.now(timezone.utc),
            })
            db.commit()

            if updated == 0:
                return {"success": True, "message": "Token not found (already unregistered)"}

            logger.info("Push token unregistered for user %d", current_user.id)
            return {"success": True, "message": "Device token unregistered"}

        except Exception as e:
            logger.error("Error unregistering push token: %s", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to unregister device token")

    # -----------------------------------------------------------------
    # GET /api/v1/push/preferences — Get notification preferences
    # -----------------------------------------------------------------
    @app.get("/api/v1/push/preferences")
    async def get_push_preferences(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Get the current user's push notification preferences.

        Returns default preferences if the user hasn't customized them.
        """
        from database.models.device_token import PushNotificationPreference, DeviceToken
        from services.push_notification_service import DEFAULT_CATEGORIES

        try:
            pref = db.query(PushNotificationPreference).filter(
                PushNotificationPreference.user_id == current_user.id,
            ).first()

            # Count active devices
            device_count = db.query(DeviceToken).filter(
                DeviceToken.user_id == current_user.id,
                DeviceToken.is_active == True,
            ).count()

            if pref:
                # Merge stored categories with defaults (new categories get enabled)
                merged_categories = {**DEFAULT_CATEGORIES}
                if pref.categories:
                    merged_categories.update(pref.categories)

                return {
                    "success": True,
                    "preferences": {
                        "categories": merged_categories,
                        "muted": pref.muted,
                        "quiet_hours_start": pref.quiet_hours_start,
                        "quiet_hours_end": pref.quiet_hours_end,
                    },
                    "active_devices": device_count,
                }
            else:
                return {
                    "success": True,
                    "preferences": {
                        "categories": DEFAULT_CATEGORIES.copy(),
                        "muted": False,
                        "quiet_hours_start": None,
                        "quiet_hours_end": None,
                    },
                    "active_devices": device_count,
                }

        except Exception as e:
            logger.error("Error fetching push preferences: %s", e)
            raise HTTPException(status_code=500, detail="Failed to fetch preferences")

    # -----------------------------------------------------------------
    # PUT /api/v1/push/preferences — Update notification preferences
    # -----------------------------------------------------------------
    @app.put("/api/v1/push/preferences")
    async def update_push_preferences(
        request: UpdatePreferencesRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Update the current user's push notification preferences.

        Only provided fields are updated; omitted fields remain unchanged.
        """
        from database.models.device_token import PushNotificationPreference

        try:
            pref = db.query(PushNotificationPreference).filter(
                PushNotificationPreference.user_id == current_user.id,
            ).first()

            if not pref:
                pref = PushNotificationPreference(
                    user_id=current_user.id,
                    organization_id=getattr(current_user, "organization_id", None),
                    categories={},
                    muted=False,
                )
                db.add(pref)

            if request.categories is not None:
                # Merge with existing categories
                existing = pref.categories or {}
                existing.update(request.categories)
                pref.categories = existing

            if request.muted is not None:
                pref.muted = request.muted

            if request.quiet_hours_start is not None:
                pref.quiet_hours_start = request.quiet_hours_start

            if request.quiet_hours_end is not None:
                pref.quiet_hours_end = request.quiet_hours_end

            pref.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info("Push preferences updated for user %d", current_user.id)
            return {
                "success": True,
                "message": "Preferences updated",
                "preferences": {
                    "categories": pref.categories,
                    "muted": pref.muted,
                    "quiet_hours_start": pref.quiet_hours_start,
                    "quiet_hours_end": pref.quiet_hours_end,
                },
            }

        except Exception as e:
            logger.error("Error updating push preferences: %s", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update preferences")

    # -----------------------------------------------------------------
    # POST /api/v1/push/test — Send test notification to current user
    # -----------------------------------------------------------------
    @app.post("/api/v1/push/test")
    async def send_test_notification(
        request: TestNotificationRequest = None,
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db),
    ):
        """Send a test notification to the current user's registered devices.

        Requires admin, site_admin, platform_admin, management, or leadership role.
        """
        admin_roles = (
            "admin", "site_admin", "platform_admin", "management",
            "branch_manager", "regional_manager", "leadership",
        )
        user_role = getattr(current_user, "permission_role", "sales")
        if user_role not in admin_roles:
            raise HTTPException(status_code=403, detail="Admin role required to send test notifications")

        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()

        title = (request.title if request else None) or "Test Notification"
        body = (request.body if request else None) or "Push notifications are working!"

        result = service.send_to_user(
            db=db,
            user_id=current_user.id,
            title=title,
            body=body,
            data={"type": "test", "route": "/settings"},
            notification_type="general",
        )
        return {"success": True, **result}

    # -----------------------------------------------------------------
    # POST /api/v1/push/send — Send notification to a user (admin)
    # -----------------------------------------------------------------
    @app.post("/api/v1/push/send")
    async def send_push_notification(
        request: SendNotificationRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Send a push notification to a specific user. Requires admin/manager role."""
        admin_roles = (
            "admin", "site_admin", "platform_admin", "management",
            "branch_manager", "regional_manager", "leadership",
        )
        user_role = getattr(current_user, "permission_role", "sales")
        if user_role not in admin_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Tenant isolation: ensure target user is in same org
        org_id = getattr(current_user, "organization_id", None)
        if org_id:
            from database.models.core import User
            target_user = db.query(User).filter(
                User.id == request.user_id,
                User.organization_id == org_id,
            ).first()
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found in your organization")

        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()

        result = service.send_to_user(
            db=db,
            user_id=request.user_id,
            title=request.title or "",
            body=request.body or "",
            data=request.data,
            notification_type=request.notification_type,
        )
        return {"success": True, **result}

    # -----------------------------------------------------------------
    # GET /api/v1/push/devices — List registered devices for current user
    # -----------------------------------------------------------------
    @app.get("/api/v1/push/devices")
    async def list_devices(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """List all registered device tokens for the current user."""
        from database.models.device_token import DeviceToken

        tokens = db.query(DeviceToken).filter(
            DeviceToken.user_id == current_user.id,
        ).order_by(DeviceToken.updated_at.desc()).all()

        return {
            "success": True,
            "devices": [
                {
                    "id": t.id,
                    "platform": t.platform,
                    "device_name": t.device_name,
                    "app_version": t.app_version,
                    "is_active": t.is_active,
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "token_prefix": t.device_token[:8] + "..." if t.device_token else None,
                }
                for t in tokens
            ],
            "active_count": sum(1 for t in tokens if t.is_active),
            "total_count": len(tokens),
        }

    logger.info("Push notification routes registered (register, unregister, preferences, test, send, devices)")


# =============================================================================
# Module-level singleton for internal use
# =============================================================================

_push_service = None


def _get_push_service():
    global _push_service
    if _push_service is None:
        from services.push_notification_service import PushNotificationService
        _push_service = PushNotificationService()
    return _push_service


# =============================================================================
# Convenience functions for internal use (called from other services)
# =============================================================================

def notify_lead_assigned(db: Session, user_id: int, lead_name: str, amount: float, loan_purpose: str):
    """Send push notification when a lead is assigned."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="New Lead Assigned",
        body=f"{lead_name} — ${amount:,.0f} {loan_purpose}",
        notification_type="lead_assigned",
        data={"type": "lead_assigned", "route": "/leads"},
    )


def notify_loan_update(db: Session, user_id: int, borrower_name: str, stage: str, loan_id: str):
    """Send push notification when a loan stage changes."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="Loan Update",
        body=f"{borrower_name} moved to {stage}",
        notification_type="loan_update",
        data={
            "type": "loan_update",
            "entity_id": loan_id,
            "entity_type": "loan",
            "action": "stage_changed",
            "route": f"/loans/{loan_id}",
        },
    )


def notify_appointment_reminder(db: Session, user_id: int, contact_name: str, time: str):
    """Send push notification for upcoming appointment."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="Upcoming Appointment",
        body=f"{contact_name} at {time}",
        notification_type="appointment_reminder",
        data={"type": "appointment_reminder", "route": "/calendar"},
    )


def notify_briefing_ready(db: Session, user_id: int, active_count: int, at_risk_count: int):
    """Send push notification when morning briefing is ready."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="Morning Briefing Ready",
        body=f"{active_count} active loans, {at_risk_count} at risk",
        notification_type="briefing_ready",
        data={"type": "briefing_ready", "route": "/dashboard"},
    )


def notify_document_received(db: Session, user_id: int, doc_type: str, borrower_name: str):
    """Send push notification when a document is received."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="Document Received",
        body=f"{doc_type} from {borrower_name}",
        notification_type="document_received",
        data={"type": "document_received", "route": "/documents"},
    )


def notify_sla_alert(db: Session, user_id: int, loan_name: str, milestone: str, hours_remaining: int):
    """Send push notification for SLA warning."""
    service = _get_push_service()
    return service.send_to_user(
        db=db, user_id=user_id,
        title="SLA Warning",
        body=f"{loan_name} — {milestone} due in {hours_remaining}h",
        notification_type="sla_alert",
        data={"type": "sla_alert", "route": "/loans"},
    )


def notify_compliance_alert(db: Session, user_id: int, alert_type: str, description: str, loan_id: str = None):
    """Send push notification for compliance alert."""
    service = _get_push_service()
    data = {"type": "compliance_alert", "route": "/compliance"}
    if loan_id:
        data["entity_id"] = loan_id
        data["entity_type"] = "loan"
    return service.send_to_user(
        db=db, user_id=user_id,
        title="Compliance Alert",
        body=f"{alert_type}: {description}",
        notification_type="compliance_alert",
        data=data,
    )


def notify_task_assigned(db: Session, user_id: int, task_title: str, task_id: str = None):
    """Send push notification when a task is assigned."""
    service = _get_push_service()
    data = {"type": "task_assigned", "route": "/tasks"}
    if task_id:
        data["entity_id"] = task_id
        data["entity_type"] = "task"
    return service.send_to_user(
        db=db, user_id=user_id,
        title="New Task",
        body=task_title,
        notification_type="task_assigned",
        data=data,
    )


def notify_esign_completed(db: Session, user_id: int, borrower_name: str, document_name: str, envelope_id: str = None):
    """Send push notification when an eSign envelope is completed."""
    service = _get_push_service()
    data = {"type": "esign_completed", "route": "/smart-docs"}
    if envelope_id:
        data["entity_id"] = envelope_id
        data["entity_type"] = "esign_envelope"
    return service.send_to_user(
        db=db, user_id=user_id,
        title="eSign Complete",
        body=f"{borrower_name} signed {document_name}",
        notification_type="esign_completed",
        data=data,
    )


# =============================================================================
# Agent Notification Bridge — convenience accessor
# =============================================================================

def get_agent_push_service():
    """Get the AgentNotificationService singleton for use by other services.

    This is a convenience accessor so callers don't need to know the import path.
    Usage:
        from routes.push_notification_routes import get_agent_push_service
        svc = get_agent_push_service()
        svc.notify_stale_loan(db, loan_id, days_stale=12, stage="PROCESSING")
    """
    from services.agent_notification_service import get_agent_notification_service
    return get_agent_notification_service()
