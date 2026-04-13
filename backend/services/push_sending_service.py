"""
Push Sending Service — APNs Integration Facade

Thin orchestration layer that makes it trivial for any backend service to send
push notifications. Delegates to PushNotificationService (APNs HTTP/2 + FCM)
and AgentNotificationService (rate limiting + quiet hours).

Usage from any service or route handler:

    from services.push_sending_service import push_service

    # Single user
    push_service.send_push(token, "Title", "Body")

    # All of a user's devices
    push_service.send_push_to_user(user_id, "Title", "Body", db=db)

    # All users in an org
    push_service.send_push_to_org(org_id, "Title", "Body", db=db)

    # Combined in-app notification + push
    await push_service.send_notification_with_push(user_id, "Title", "Body", db=db)

All methods degrade gracefully if APNs credentials are not configured.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PushSendingService:
    """Facade over PushNotificationService and AgentNotificationService.

    Provides a clean API surface for push notification delivery.  All methods
    are safe to call even when APNs is not configured (they log and return).
    """

    def __init__(self):
        self._push_svc = None
        self._agent_svc = None

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_push_service(self):
        if self._push_svc is None:
            from services.push_notification_service import PushNotificationService
            self._push_svc = PushNotificationService()
        return self._push_svc

    def _get_agent_service(self):
        if self._agent_svc is None:
            from services.agent_notification_service import get_agent_notification_service
            self._agent_svc = get_agent_notification_service()
        return self._agent_svc

    def _get_or_create_session(self, db: Optional[Session]):
        """Return (session, owns_it) tuple."""
        if db is not None:
            return db, False
        from db import SessionLocal
        return SessionLocal(), True

    # ------------------------------------------------------------------
    # send_push — send to a single device token
    # ------------------------------------------------------------------

    def send_push(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        sound: str = "default",
        db: Optional[Session] = None,
    ) -> bool:
        """Send a push notification to a single APNs device token.

        Returns True on successful delivery, False otherwise.
        If APNs is not configured, logs a warning and returns False.
        """
        session, owns = self._get_or_create_session(db)
        try:
            svc = self._get_push_service()
            return svc._send_ios(
                db=session,
                device_token=token,
                title=title,
                body=body,
                data=data,
                badge=badge,
            )
        except Exception as e:
            logger.error("send_push failed for token %s...: %s", token[:8], e)
            return False
        finally:
            if owns:
                session.close()

    # ------------------------------------------------------------------
    # send_push_to_user — look up all active tokens and send
    # ------------------------------------------------------------------

    def send_push_to_user(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        notification_type: str = "general",
        db: Optional[Session] = None,
        respect_rate_limit: bool = True,
        respect_quiet_hours: bool = True,
    ) -> Dict[str, int]:
        """Send a push notification to all of a user's registered devices.

        When ``respect_rate_limit`` or ``respect_quiet_hours`` are True (the
        default), delegates through AgentNotificationService which enforces
        max 5 pushes/user/hour and user-configured quiet windows.

        Returns dict: {"sent": N, "failed": N, "skipped": N}
        """
        session, owns = self._get_or_create_session(db)
        try:
            if respect_rate_limit or respect_quiet_hours:
                agent_svc = self._get_agent_service()
                return agent_svc.notify_user(
                    db=session,
                    user_id=user_id,
                    title=title,
                    body=body,
                    notification_type=notification_type,
                    data=data,
                    bypass_quiet_hours=not respect_quiet_hours,
                    bypass_rate_limit=not respect_rate_limit,
                )
            else:
                svc = self._get_push_service()
                return svc.send_to_user(
                    db=session,
                    user_id=user_id,
                    title=title,
                    body=body,
                    data=data or {},
                    badge=badge,
                    notification_type=notification_type,
                )
        except Exception as e:
            logger.error("send_push_to_user failed for user %d: %s", user_id, e)
            return {"sent": 0, "failed": 0, "skipped": 0}
        finally:
            if owns:
                session.close()

    # ------------------------------------------------------------------
    # send_push_to_org — broadcast to all users in an organization
    # ------------------------------------------------------------------

    def send_push_to_org(
        self,
        org_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_type: str = "general",
        db: Optional[Session] = None,
    ) -> Dict[str, int]:
        """Send a push notification to every user with active tokens in an org.

        Returns aggregated dict: {"sent": N, "failed": N, "skipped": N}
        """
        session, owns = self._get_or_create_session(db)
        try:
            from database.models.device_token import DeviceToken
            user_ids = [
                row[0] for row in session.query(DeviceToken.user_id).filter(
                    DeviceToken.organization_id == org_id,
                    DeviceToken.is_active == True,
                ).distinct().all()
            ]

            if not user_ids:
                return {"sent": 0, "failed": 0, "skipped": 0}

            svc = self._get_push_service()
            return svc.send_to_users(
                db=session,
                user_ids=user_ids,
                title=title,
                body=body,
                data=data or {},
                notification_type=notification_type,
            )
        except Exception as e:
            logger.error("send_push_to_org failed for org %d: %s", org_id, e)
            return {"sent": 0, "failed": 0, "skipped": 0}
        finally:
            if owns:
                session.close()

    # ------------------------------------------------------------------
    # send_notification_with_push — in-app record + device push
    # ------------------------------------------------------------------

    async def send_notification_with_push(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
        notification_type: str = "general",
    ) -> Dict[str, Any]:
        """Create an in-app notification AND send a push to the user's devices.

        Returns {"in_app": bool, "push": {"sent": N, "failed": N, "skipped": N}}
        """
        from services.push_notification_service import send_notification_with_push
        return await send_notification_with_push(
            user_id=user_id,
            title=title,
            body=body,
            data=data,
            db=db,
            notification_type=notification_type,
        )

    # ------------------------------------------------------------------
    # Convenience: domain-specific senders
    # ------------------------------------------------------------------

    def notify_new_lead(
        self,
        db: Session,
        user_id: int,
        lead_name: str,
        amount: float = 0,
        loan_purpose: str = "",
    ) -> Dict[str, int]:
        """Push notification for a new lead assignment."""
        body = f"{lead_name}"
        if amount:
            body += f" -- ${amount:,.0f}"
        if loan_purpose:
            body += f" {loan_purpose}"

        return self.send_push_to_user(
            user_id=user_id,
            title="New Lead Assigned",
            body=body,
            data={"type": "lead_assigned", "route": "/leads"},
            notification_type="lead_assigned",
            db=db,
        )

    def notify_stage_change(
        self,
        db: Session,
        user_id: int,
        borrower_name: str,
        new_stage: str,
        loan_id: int,
    ) -> Dict[str, int]:
        """Push notification for a loan stage change."""
        return self.send_push_to_user(
            user_id=user_id,
            title="Loan Update",
            body=f"{borrower_name} moved to {new_stage}",
            data={
                "type": "loan_update",
                "entity_id": str(loan_id),
                "entity_type": "loan",
                "action": "stage_changed",
                "route": f"/loans/{loan_id}",
            },
            notification_type="loan_update",
            db=db,
        )

    def notify_task(
        self,
        db: Session,
        user_id: int,
        task_title: str,
        task_id: Optional[int] = None,
    ) -> Dict[str, int]:
        """Push notification for a task assignment."""
        data: Dict[str, Any] = {"type": "task_assigned", "route": "/tasks"}
        if task_id:
            data["entity_id"] = str(task_id)
            data["entity_type"] = "task"

        return self.send_push_to_user(
            user_id=user_id,
            title="New Task",
            body=task_title[:200],
            data=data,
            notification_type="task_assigned",
            db=db,
        )

    def notify_appointment_reminder(
        self,
        db: Session,
        user_id: int,
        contact_name: str,
        time_str: str,
    ) -> Dict[str, int]:
        """Push notification for an upcoming appointment."""
        return self.send_push_to_user(
            user_id=user_id,
            title="Upcoming Appointment",
            body=f"{contact_name} at {time_str}",
            data={"type": "appointment_reminder", "route": "/calendar"},
            notification_type="appointment_reminder",
            db=db,
        )

    def notify_rate_alert(
        self,
        db: Session,
        user_id: int,
        message: str,
    ) -> Dict[str, int]:
        """Push notification for rate change alerts."""
        return self.send_push_to_user(
            user_id=user_id,
            title="Rate Alert",
            body=message,
            data={"type": "rate_alert", "route": "/rate-monitor"},
            notification_type="general",
            db=db,
        )

    def close(self):
        """Clean up underlying HTTP clients."""
        if self._push_svc:
            self._push_svc.close()
            self._push_svc = None


# =============================================================================
# Module-level singleton
# =============================================================================

_instance: Optional[PushSendingService] = None


def get_push_sending_service() -> PushSendingService:
    """Get or create the singleton PushSendingService."""
    global _instance
    if _instance is None:
        _instance = PushSendingService()
    return _instance


# Convenience alias for quick imports:
#   from services.push_sending_service import push_service
push_service = get_push_sending_service()
