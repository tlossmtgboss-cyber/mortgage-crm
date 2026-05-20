"""Action Dispatcher — replay held actions after human approval.

When an autonomous agent proposes an action that requires approval, the
ActionGateway holds it as a pending AgentAction record.  The execute_fn
lambda is lost when the agent's DB session closes.

The dispatcher reconstructs and executes actions from the serialized
payload stored in AgentAction.payload.  Each action_type maps to a
replay function that knows the correct SQL / ORM operation.

Usage from the approve endpoint::

    from services.autonomous.action_dispatcher import ActionDispatcher
    dispatcher = ActionDispatcher(db, action.organization_id)
    dispatcher.replay(action)  # executes the business operation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """Reconstruct and execute agent actions from stored payload."""

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id

    def replay(self, action) -> bool:
        """Replay a held action using its action_type and payload.

        Returns True if the action was successfully executed.
        """
        if not action.payload:
            logger.warning(
                "Cannot replay action %s (type=%s): no payload stored. "
                "The action was approved but the original operation cannot "
                "be reconstructed.",
                action.id, action.action_type,
            )
            return False

        handler = self._REPLAY_MAP.get(action.action_type)
        if not handler:
            logger.warning(
                "No replay handler for action_type=%s (action %s). "
                "Action approved but not executed.",
                action.action_type, action.id,
            )
            return False

        try:
            handler(self, action.payload)
            return True
        except Exception as e:
            logger.error(
                "Failed to replay action %s (type=%s): %s",
                action.id, action.action_type, e,
            )
            return False

    @staticmethod
    def _resolve_assignee(payload: dict) -> str | None:
        for key in ("assigned_to_id", "lo_id", "assigned", "assigned_to", "owner_id"):
            val = payload.get(key)
            if val is not None:
                return str(val)
        return None

    @staticmethod
    def _resolve_user(payload: dict) -> str | None:
        for key in ("user_id", "lo_id", "uid", "owner_id", "assigned_to_id"):
            val = payload.get(key)
            if val is not None:
                return str(val)
        return None

    def _replay_create_task(self, payload: dict) -> None:
        """Replay a create_task action by inserting into the tasks table."""
        p = {
            "title": payload.get("title", "AI-created task"),
            "description": payload.get("description") or payload.get("desc", ""),
            "assigned_to_id": self._resolve_assignee(payload),
            "loan_id": payload.get("loan_id"),
            "lead_id": payload.get("lead_id"),
            "priority": payload.get("priority", "medium"),
            "status": payload.get("status", "pending"),
            "org_id": self.org_id,
        }
        due = payload.get("due_date") or payload.get("due")

        cols = [
            "title", "description", "assigned_to_id", "priority",
            "status", "created_at", "organization_id",
        ]
        vals = [
            ":title", ":description", ":assigned_to_id", ":priority",
            ":status", "CURRENT_TIMESTAMP", ":org_id",
        ]

        if p["loan_id"]:
            cols.append("loan_id")
            vals.append(":loan_id")
        if p["lead_id"]:
            cols.append("lead_id")
            vals.append(":lead_id")
        if due:
            cols.append("due_date")
            vals.append(":due")
            p["due"] = due
        else:
            cols.append("due_date")
            vals.append("CURRENT_DATE")

        sql = f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        self.db.execute(text(sql), p)

    def _replay_create_notification(self, payload: dict) -> None:
        """Replay a create_notification action."""
        p = {
            "user_id": self._resolve_user(payload),
            "org_id": self.org_id,
            "type": payload.get("type", "agent_alert"),
            "title": payload.get("title", "AI Agent Notification"),
            "message": payload.get("message") or payload.get("desc", ""),
            "link": payload.get("link"),
            "is_read": False,
        }
        if not p["user_id"]:
            logger.warning("Cannot replay create_notification: no user_id in payload")
            return

        self.db.execute(text("""
            INSERT INTO notifications (user_id, organization_id, type, title,
                                       message, link, is_read, created_at)
            VALUES (:user_id, :org_id, :type, :title,
                    :message, :link, :is_read, CURRENT_TIMESTAMP)
        """), p)

    def _replay_create_activity(self, payload: dict) -> None:
        """Replay a create_activity action."""
        p = {
            "org_id": self.org_id,
            "type": payload.get("type", "note"),
            "content": payload.get("content") or payload.get("desc", ""),
            "loan_id": payload.get("loan_id"),
            "lead_id": payload.get("lead_id"),
            "user_id": self._resolve_user(payload),
        }

        cols = ["organization_id", "type", "content", "created_at"]
        vals = [":org_id", ":type", ":content", "CURRENT_TIMESTAMP"]

        for optional in ("loan_id", "lead_id", "user_id"):
            if p.get(optional):
                cols.append(optional)
                vals.append(f":{optional}")

        sql = f"INSERT INTO activities ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        self.db.execute(text(sql), p)

    def _replay_send_sms(self, payload: dict) -> None:
        """Replay a send_sms action — send via Telnyx."""
        phone = payload.get("phone") or payload.get("to")
        message = payload.get("message") or payload.get("text", "")
        logger.info(
            "SMS replay for action: to=%s, message preview=%s",
            phone, message[:50],
        )
        if not phone or not message:
            logger.warning("SMS replay missing phone or message in payload")
            return
        try:
            from telephony.sms import send_sms
            send_sms(
                to=phone,
                text=message,
                organization_id=self.org_id,
            )
        except ImportError:
            logger.warning("telephony.sms not available for replay")
        except Exception as e:
            logger.warning("SMS replay failed: %s", e)

    def _replay_send_email(self, payload: dict) -> None:
        """Replay a send_email action via NotificationService."""
        to_email = payload.get("to_email") or payload.get("email")
        subject = payload.get("subject", "")
        body = payload.get("body") or payload.get("message") or payload.get("html_content", "")
        logger.info(
            "Email replay for action: to=%s, subject=%s",
            to_email, subject[:50],
        )
        if not to_email:
            logger.warning("Email replay missing to_email in payload")
            return
        try:
            from services.notification_service import NotificationService
            svc = NotificationService()
            svc.send_email(
                to_email=to_email,
                subject=subject,
                html_content=body,
                org_id=self.org_id,
            )
        except ImportError:
            logger.warning("NotificationService not available for replay")
        except Exception as e:
            logger.warning("Email replay failed: %s", e)

    def _replay_create_compliance_alert(self, payload: dict) -> None:
        """Replay a create_compliance_alert action."""
        p = {
            "org_id": self.org_id,
            "title": payload.get("title", "Compliance Alert"),
            "description": payload.get("description") or payload.get("desc", ""),
            "severity": payload.get("severity", "medium"),
            "alert_type": payload.get("alert_type", "general"),
            "loan_id": payload.get("loan_id"),
            "lead_id": payload.get("lead_id"),
            "status": payload.get("status", "open"),
        }

        cols = ["organization_id", "title", "description", "severity",
                "alert_type", "status", "created_at"]
        vals = [":org_id", ":title", ":description", ":severity",
                ":alert_type", ":status", "CURRENT_TIMESTAMP"]

        for optional in ("loan_id", "lead_id"):
            if p.get(optional):
                cols.append(optional)
                vals.append(f":{optional}")

        sql = f"INSERT INTO compliance_alerts ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        self.db.execute(text(sql), p)

    _REPLAY_MAP = {
        "create_task": _replay_create_task,
        "create_notification": _replay_create_notification,
        "create_activity": _replay_create_activity,
        "create_compliance_alert": _replay_create_compliance_alert,
        "send_sms": _replay_send_sms,
        "send_email": _replay_send_email,
    }
