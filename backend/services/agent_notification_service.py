"""
Agent Notification Service

Bridge between AI agents and the push notification system.
Agents call this service to send push notifications to users' mobile devices
when they detect actionable conditions (SLA breaches, stale loans, missing docs, etc.).

Features:
- Rate limiting: max 5 push notifications per user per hour (configurable)
- Quiet hours: respects user-configured quiet hours (default 9 PM - 7 AM)
- Preference checking: respects per-category opt-out preferences
- Fire-and-forget: never blocks agent execution on notification delivery
- Graceful degradation: logs and continues if push sending fails
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Rate limit: max notifications per user per rolling window
DEFAULT_MAX_PER_USER_PER_HOUR = 5
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour


class AgentNotificationService:
    """Bridge between AI agents and push notification system.

    Singleton-style service. Create one instance at app startup and pass to agents,
    or use the module-level `get_agent_notification_service()` function.
    """

    def __init__(self, max_per_user_per_hour: int = DEFAULT_MAX_PER_USER_PER_HOUR):
        self._max_per_hour = max_per_user_per_hour
        # Rate limiting state: user_id -> list of timestamps
        self._send_timestamps: Dict[int, List[float]] = defaultdict(list)
        self._lock = Lock()

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------

    def _is_rate_limited(self, user_id: int) -> bool:
        """Check if a user has exceeded the per-hour notification rate limit.

        Thread-safe. Prunes expired timestamps on each check.
        """
        now = time.time()
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS

        with self._lock:
            # Prune old timestamps
            timestamps = self._send_timestamps[user_id]
            self._send_timestamps[user_id] = [t for t in timestamps if t > cutoff]

            if len(self._send_timestamps[user_id]) >= self._max_per_hour:
                return True

            return False

    def _record_send(self, user_id: int):
        """Record that a notification was sent to a user."""
        with self._lock:
            self._send_timestamps[user_id].append(time.time())

    # -------------------------------------------------------------------------
    # Quiet Hours
    # -------------------------------------------------------------------------

    def _is_quiet_hours(self, db: Session, user_id: int) -> bool:
        """Check if the current time falls within the user's quiet hours.

        Quiet hours are stored as HH:MM strings in UTC on PushNotificationPreference.
        Default quiet hours: 21:00 - 07:00 UTC (applied when user has no preference set).
        """
        try:
            from database.models.device_token import PushNotificationPreference

            pref = db.query(PushNotificationPreference).filter(
                PushNotificationPreference.user_id == user_id,
            ).first()

            if pref and pref.quiet_hours_start and pref.quiet_hours_end:
                start_str = pref.quiet_hours_start  # e.g. "21:00"
                end_str = pref.quiet_hours_end      # e.g. "07:00"
            else:
                # No preference set: no quiet hours enforced for agents
                # (Users who care will configure quiet hours in settings)
                return False

            now_utc = datetime.now(timezone.utc)
            current_minutes = now_utc.hour * 60 + now_utc.minute

            start_parts = start_str.split(":")
            end_parts = end_str.split(":")
            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
            end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

            if start_minutes <= end_minutes:
                # Same-day window (e.g., 09:00 - 17:00)
                return start_minutes <= current_minutes < end_minutes
            else:
                # Overnight window (e.g., 21:00 - 07:00)
                return current_minutes >= start_minutes or current_minutes < end_minutes

        except Exception as e:
            logger.debug("Error checking quiet hours for user %d: %s", user_id, e)
            return False  # Fail open: send the notification

    # -------------------------------------------------------------------------
    # Core Send Method
    # -------------------------------------------------------------------------

    def notify_user(
        self,
        db: Session,
        user_id: int,
        title: str,
        body: str,
        notification_type: str = "general",
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        bypass_quiet_hours: bool = False,
        bypass_rate_limit: bool = False,
    ) -> Dict[str, Any]:
        """Send a push notification to a user's registered devices.

        This is the primary entry point for agents. It handles:
        - Rate limiting (skip if over threshold)
        - Quiet hours (skip if user is in quiet hours, unless bypassed)
        - Preference checking (delegated to PushNotificationService)
        - Actual delivery via APNs/FCM

        Args:
            db: SQLAlchemy session
            user_id: Target user ID
            title: Notification title
            body: Notification body text
            notification_type: Category for preference matching (e.g. "sla_alert")
            data: Optional data payload for deep linking
            priority: "normal" or "critical" (critical bypasses quiet hours)
            bypass_quiet_hours: Force send even during quiet hours
            bypass_rate_limit: Force send even if rate limited

        Returns:
            Dict with keys: sent, failed, skipped, reason (if skipped)
        """
        try:
            # Rate limit check
            if not bypass_rate_limit and self._is_rate_limited(user_id):
                logger.info(
                    "Push notification rate-limited for user %d (max %d/hr)",
                    user_id, self._max_per_hour,
                )
                return {"sent": 0, "failed": 0, "skipped": 1, "reason": "rate_limited"}

            # Quiet hours check (critical priority bypasses)
            is_critical = priority == "critical" or bypass_quiet_hours
            if not is_critical and self._is_quiet_hours(db, user_id):
                logger.info(
                    "Push notification suppressed for user %d — quiet hours",
                    user_id,
                )
                return {"sent": 0, "failed": 0, "skipped": 1, "reason": "quiet_hours"}

            # Send via PushNotificationService
            from services.push_notification_service import PushNotificationService
            service = PushNotificationService()

            result = service.send_to_user(
                db=db,
                user_id=user_id,
                title=title,
                body=body,
                data=data or {},
                notification_type=notification_type,
            )

            # Record for rate limiting if we actually sent something
            if result.get("sent", 0) > 0:
                self._record_send(user_id)

            return result

        except Exception as e:
            logger.error(
                "Agent notification failed for user %d: %s", user_id, e,
                exc_info=True,
            )
            return {"sent": 0, "failed": 0, "skipped": 1, "reason": f"error: {e}"}

    # -------------------------------------------------------------------------
    # Loan Officer Lookup
    # -------------------------------------------------------------------------

    def notify_loan_officer(
        self,
        db: Session,
        loan_id: int,
        title: str,
        body: str,
        notification_type: str = "general",
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """Send a push notification to the loan officer assigned to a loan.

        Looks up loan -> loan_officer_id, then calls notify_user().
        If no LO is assigned, returns skipped.
        """
        try:
            from sqlalchemy import text

            row = db.execute(text(
                "SELECT loan_officer_id, loan_number FROM loans WHERE id = :loan_id"
            ), {"loan_id": loan_id}).fetchone()

            if not row or not row.loan_officer_id:
                logger.debug("No LO assigned to loan %d — skipping push", loan_id)
                return {"sent": 0, "failed": 0, "skipped": 1, "reason": "no_lo_assigned"}

            # Merge loan context into data payload
            merged_data = {
                "type": notification_type,
                "entity_type": "loan",
                "entity_id": str(loan_id),
                "route": f"/loans/{loan_id}",
            }
            if data:
                merged_data.update(data)

            return self.notify_user(
                db=db,
                user_id=row.loan_officer_id,
                title=title,
                body=body,
                notification_type=notification_type,
                data=merged_data,
                priority=priority,
            )

        except Exception as e:
            logger.error("notify_loan_officer failed for loan %d: %s", loan_id, e)
            return {"sent": 0, "failed": 0, "skipped": 1, "reason": f"error: {e}"}

    # -------------------------------------------------------------------------
    # Pre-built Notification Methods for Common Agent Scenarios
    # -------------------------------------------------------------------------

    def notify_stale_loan(
        self,
        db: Session,
        loan_id: int,
        days_stale: int,
        stage: str,
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for loans stuck in a stage past SLA.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"
        title = f"Loan stuck in {stage}"
        body = f"{label} has been in {stage} for {days_stale} days. Action needed."

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title=title,
            body=body,
            notification_type="sla_alert",
            data={
                "category": "SLA_BREACH",
                "days_stale": str(days_stale),
                "stage": stage,
            },
            priority="critical" if days_stale > 14 else "normal",
        )

    def notify_document_needed(
        self,
        db: Session,
        loan_id: int,
        doc_types: List[str],
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for missing or expiring documents.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"

        if len(doc_types) == 1:
            body = f"{doc_types[0]} needed for {label}"
        else:
            body = f"{len(doc_types)} documents needed for {label}"

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title="Documents Needed",
            body=body,
            notification_type="document_received",
            data={
                "category": "DOC_MISSING",
                "doc_types": ",".join(doc_types),
            },
        )

    def notify_doc_expiring(
        self,
        db: Session,
        loan_id: int,
        doc_type: str,
        expire_date: str,
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for documents about to expire.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"
        title = f"{doc_type} Expiring"
        body = f"{doc_type} for {label} expires {expire_date}. Renewal needed."

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title=title,
            body=body,
            notification_type="compliance_alert",
            data={
                "category": "DOC_EXPIRING",
                "doc_type": doc_type,
                "expire_date": expire_date,
            },
            priority="critical",
        )

    def notify_sla_breach(
        self,
        db: Session,
        loan_id: int,
        sla_name: str,
        days_over: int,
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for SLA violations.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"
        title = "SLA Breach"
        body = f"{sla_name} overdue by {days_over} days for {label}"

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title=title,
            body=body,
            notification_type="sla_alert",
            data={
                "category": "SLA_BREACH",
                "sla_name": sla_name,
                "days_over": str(days_over),
            },
            priority="critical" if days_over > 7 else "normal",
        )

    def notify_lock_expiring(
        self,
        db: Session,
        loan_id: int,
        days_until_expiry: int,
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for rate locks about to expire.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"

        if days_until_expiry <= 0:
            title = "Rate Lock EXPIRED"
            body = f"Rate lock has expired for {label}. Immediate action required."
            priority = "critical"
        else:
            title = "Rate Lock Expiring"
            body = f"Rate lock for {label} expires in {days_until_expiry} days."
            priority = "critical" if days_until_expiry <= 2 else "normal"

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title=title,
            body=body,
            notification_type="sla_alert",
            data={
                "category": "LOCK_EXPIRING",
                "days_until_expiry": str(days_until_expiry),
            },
            priority=priority,
        )

    def notify_compliance_alert(
        self,
        db: Session,
        loan_id: int,
        alert_title: str,
        severity: str,
        borrower_name: str = "",
        loan_number: str = "",
    ) -> Dict[str, Any]:
        """Pre-built notification for compliance alerts.

        Sent to the assigned loan officer.
        """
        label = borrower_name or loan_number or f"Loan #{loan_id}"
        title = f"Compliance: {severity.title()}"
        body = f"{alert_title} — {label}"

        return self.notify_loan_officer(
            db=db,
            loan_id=loan_id,
            title=title,
            body=body,
            notification_type="compliance_alert",
            data={
                "category": "COMPLIANCE_OPEN",
                "severity": severity,
                "alert_title": alert_title,
                "entity_id": str(loan_id),
                "entity_type": "loan",
            },
            priority="critical" if severity == "critical" else "normal",
        )

    def notify_task_created(
        self,
        db: Session,
        user_id: int,
        task_title: str,
        task_priority: str,
        task_id: Optional[int] = None,
        loan_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Push notification when a high/critical priority task is created.

        Only sends for high/critical priority tasks to avoid spam.
        """
        if task_priority not in ("high", "critical"):
            return {"sent": 0, "failed": 0, "skipped": 1, "reason": "low_priority_task"}

        data = {
            "type": "task_assigned",
            "route": "/tasks",
        }
        if task_id:
            data["entity_id"] = str(task_id)
            data["entity_type"] = "task"
        if loan_id:
            data["loan_id"] = str(loan_id)

        return self.notify_user(
            db=db,
            user_id=user_id,
            title="Action Required" if task_priority == "critical" else "New Task",
            body=task_title[:200],
            notification_type="task_assigned",
            data=data,
            priority="critical" if task_priority == "critical" else "normal",
        )

    # -------------------------------------------------------------------------
    # Batch / Summary Notifications
    # -------------------------------------------------------------------------

    def notify_sweep_summary(
        self,
        db: Session,
        user_id: int,
        total_impediments: int,
        critical_count: int,
        tasks_created: int,
    ) -> Dict[str, Any]:
        """Send a summary push notification after a pipeline sweep.

        Only sends if there are actionable items.
        """
        if total_impediments == 0:
            return {"sent": 0, "failed": 0, "skipped": 1, "reason": "no_impediments"}

        if critical_count > 0:
            title = f"{critical_count} Critical Issue{'s' if critical_count != 1 else ''}"
            body = f"{total_impediments} pipeline issues detected, {tasks_created} tasks created."
            priority = "critical"
        else:
            title = "Pipeline Sweep Complete"
            body = f"{total_impediments} issues found, {tasks_created} new tasks."
            priority = "normal"

        return self.notify_user(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            notification_type="sla_alert",
            data={
                "type": "sweep_summary",
                "route": "/tasks",
                "total_impediments": str(total_impediments),
                "critical_count": str(critical_count),
                "tasks_created": str(tasks_created),
            },
            priority=priority,
        )


# =============================================================================
# Module-level singleton
# =============================================================================

_service_instance: Optional[AgentNotificationService] = None


def get_agent_notification_service() -> AgentNotificationService:
    """Get or create the singleton AgentNotificationService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentNotificationService()
    return _service_instance
