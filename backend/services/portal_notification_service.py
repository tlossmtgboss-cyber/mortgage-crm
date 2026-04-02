"""
Portal Notification Service - Notification management for the Perennia Portal.

Handles notification templates, queue management, email/SMS delivery,
and notification preferences for borrowers and partners.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import re

from models.portal_models import (
    NotificationTemplate, NotificationQueue, NotificationChannel, NotificationPriority,
    PortalLoan, MilestoneInstance, MilestoneStatus, PortalUserRole
)
from services.notification_service import NotificationService
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class PortalNotificationService:
    """Service for managing portal notifications."""

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService()

    # =========================================================================
    # NOTIFICATION TEMPLATES
    # =========================================================================

    def get_templates(
        self,
        event_type: Optional[str] = None,
        channel: Optional[NotificationChannel] = None,
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get notification templates."""
        query = self.db.query(NotificationTemplate).filter(
            NotificationTemplate.is_active == is_active
        )

        if event_type:
            query = query.filter(NotificationTemplate.trigger_event == event_type)

        if channel:
            # channels is a JSON array, check if channel value is in the array
            query = query.filter(
                NotificationTemplate.channels.contains([channel.value])
            )

        templates = query.order_by(NotificationTemplate.trigger_event).all()

        return [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "trigger_event": t.trigger_event,
                "target_role": t.target_role.value if t.target_role else None,
                "channels": t.channels,
                "priority": t.priority.value if t.priority else None,
                "subject_template": t.subject_template,
                "body_template": t.body_template,
                "sms_template": t.sms_template,
                "is_active": t.is_active,
            }
            for t in templates
        ]

    def create_template(
        self,
        key: str,
        name: str,
        trigger_event: str,
        target_role: PortalUserRole,
        channels: List[str],
        body_template: str,
        subject_template: Optional[str] = None,
        sms_template: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a notification template."""
        template = NotificationTemplate(
            key=key,
            name=name,
            trigger_event=trigger_event,
            target_role=target_role,
            channels=channels,
            priority=priority,
            subject_template=subject_template,
            body_template=body_template,
            sms_template=sms_template,
            description=description,
            is_active=True,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        return {
            "success": True,
            "template_id": template.id,
            "key": template.key,
        }

    def update_template(
        self,
        template_id: int,
        **updates,
    ) -> Dict[str, Any]:
        """Update a notification template."""
        template = self.db.query(NotificationTemplate).filter(
            NotificationTemplate.id == template_id
        ).first()

        if not template:
            return {"success": False, "error": "Template not found"}

        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)

        self.db.commit()

        return {"success": True, "template_id": template_id}

    # =========================================================================
    # NOTIFICATION QUEUE
    # =========================================================================

    def queue_notification(
        self,
        loan_id: int,
        event_type: str,
        recipient_id: int,
        context: Optional[Dict[str, Any]] = None,
        channel: NotificationChannel = NotificationChannel.EMAIL,
        send_after: Optional[datetime] = None,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> Dict[str, Any]:
        """Queue a notification for delivery."""
        # Get template
        template = self.db.query(NotificationTemplate).filter(
            and_(
                NotificationTemplate.trigger_event == event_type,
                NotificationTemplate.channels.contains([channel.value]),
                NotificationTemplate.is_active == True
            )
        ).first()

        if not template:
            return {
                "success": False,
                "error": f"No active template found for event '{event_type}' and channel '{channel.value}'",
            }

        # Render content
        rendered_subject = self._render_template(template.subject_template or "", context or {})
        rendered_body = self._render_template(template.body_template, context or {})

        notification = NotificationQueue(
            loan_id=loan_id,
            template_id=template.id,
            channel=channel,
            recipient_id=recipient_id,
            subject=rendered_subject,
            body=rendered_body,
            context=context or {},
            status="pending",
            send_after=send_after or datetime.now(timezone.utc),
            priority=priority,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        logger.info(f"Queued {channel.value} notification for loan {loan_id}: {event_type}")

        return {
            "success": True,
            "notification_id": notification.id,
            "send_after": notification.send_after.isoformat() if notification.send_after else None,
        }

    def process_pending_notifications(self, limit: int = 50) -> Dict[str, Any]:
        """Process pending notifications in the queue."""
        pending = self.db.query(NotificationQueue).filter(
            and_(
                NotificationQueue.status == "pending",
                or_(
                    NotificationQueue.send_after == None,
                    NotificationQueue.send_after <= datetime.now(timezone.utc)
                )
            )
        ).order_by(
            NotificationQueue.priority.desc(),
            NotificationQueue.send_after
        ).limit(limit).all()

        results = {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "errors": [],
        }

        for notification in pending:
            results["processed"] += 1
            try:
                if notification.channel == NotificationChannel.EMAIL:
                    result = self._send_email(notification)
                elif notification.channel == NotificationChannel.SMS:
                    result = self._send_sms(notification)
                else:
                    result = {"success": False, "error": "Unknown channel"}

                if result.get("success"):
                    notification.status = "sent"
                    notification.sent_at = datetime.now(timezone.utc)
                    notification.external_message_id = result.get("message_id")
                    results["sent"] += 1
                else:
                    notification.status = "failed"
                    notification.delivery_error = result.get("error")
                    notification.retry_count += 1
                    results["failed"] += 1
                    results["errors"].append({
                        "notification_id": notification.id,
                        "error": result.get("error"),
                    })

            except Exception as e:
                notification.status = "failed"
                notification.delivery_error = str(e)
                notification.retry_count += 1
                results["failed"] += 1
                results["errors"].append({
                    "notification_id": notification.id,
                    "error": "Internal server error",
                })
                logger.error(f"Failed to process notification {notification.id}: {e}")

        self.db.commit()

        logger.info(f"Processed {results['processed']} notifications: {results['sent']} sent, {results['failed']} failed")

        return results

    def get_notification_history(
        self,
        loan_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get notification history for a loan."""
        notifications = self.db.query(NotificationQueue).filter(
            NotificationQueue.loan_id == loan_id
        ).order_by(NotificationQueue.created_at.desc()).limit(limit).all()

        return [
            {
                "id": n.id,
                "channel": n.channel.value if n.channel else None,
                "subject": n.subject,
                "status": n.status,
                "recipient_id": n.recipient_id,
                "send_after": n.send_after.isoformat() if n.send_after else None,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "delivery_error": n.delivery_error,
            }
            for n in notifications
        ]

    def retry_failed_notifications(self, max_retries: int = 3) -> Dict[str, Any]:
        """Retry failed notifications."""
        failed = self.db.query(NotificationQueue).filter(
            and_(
                NotificationQueue.status == "failed",
                NotificationQueue.retry_count < max_retries
            )
        ).all()

        for notification in failed:
            notification.status = "pending"
            notification.send_after = datetime.now(timezone.utc) + timedelta(minutes=5 * notification.retry_count)

        self.db.commit()

        return {"queued_for_retry": len(failed)}

    # =========================================================================
    # EVENT-BASED NOTIFICATIONS
    # =========================================================================

    def notify_milestone_completed(
        self,
        loan_id: int,
        milestone_id: int,
        recipient_id: int,
        borrower_name: str,
        lo_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send notification when a milestone is completed."""
        milestone = self.db.query(MilestoneInstance).filter(
            MilestoneInstance.id == milestone_id
        ).first()

        if not milestone:
            return {"success": False, "error": "Milestone not found"}

        context = {
            "borrower_name": borrower_name,
            "milestone_name": milestone.template.name if milestone.template else "Milestone",
            "milestone_description": milestone.template.description if milestone.template else "",
            "lo_name": lo_name or "Your Loan Officer",
            "completed_date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="milestone_completed",
            recipient_id=recipient_id,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def notify_document_needed(
        self,
        loan_id: int,
        document_type: str,
        recipient_id: int,
        borrower_name: str,
        due_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Send notification when a document is needed."""
        context = {
            "borrower_name": borrower_name,
            "document_type": document_type,
            "due_date": due_date.strftime("%B %d, %Y") if due_date else "as soon as possible",
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="document_needed",
            recipient_id=recipient_id,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.HIGH,
        )

    def notify_stage_change(
        self,
        loan_id: int,
        from_stage: str,
        to_stage: str,
        recipient_id: int,
        borrower_name: str,
    ) -> Dict[str, Any]:
        """Send notification when loan stage changes."""
        stage_messages = {
            "PREAPPROVAL": "Your pre-approval application is being processed",
            "UNDER_CONTRACT": "Congratulations! Your loan is now under contract",
            "PROCESSING": "Your loan is now in processing",
            "CLEAR_TO_CLOSE": "Great news! Your loan is clear to close",
            "FUNDED": "Congratulations! Your loan has been funded",
            "MUM": "Welcome to Member Until Maturity",
        }

        context = {
            "borrower_name": borrower_name,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "stage_message": stage_messages.get(to_stage, f"Your loan has moved to {to_stage}"),
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="stage_change",
            recipient_id=recipient_id,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.HIGH,
        )

    def notify_closing_reminder(
        self,
        loan_id: int,
        recipient_id: int,
        borrower_name: str,
        closing_date: datetime,
        business_days_remaining: int,
    ) -> Dict[str, Any]:
        """Send closing countdown reminder."""
        context = {
            "borrower_name": borrower_name,
            "closing_date": closing_date.strftime("%B %d, %Y"),
            "closing_day": closing_date.strftime("%A"),
            "business_days_remaining": business_days_remaining,
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="closing_reminder",
            recipient_id=recipient_id,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def notify_home_value_update(
        self,
        loan_id: int,
        recipient_id: int,
        borrower_name: str,
        current_value: float,
        appreciation_percent: float,
    ) -> Dict[str, Any]:
        """Send home value update notification."""
        context = {
            "borrower_name": borrower_name,
            "current_value": f"${current_value:,.0f}",
            "appreciation_percent": f"{appreciation_percent:.1f}%",
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="home_value_update",
            recipient_id=recipient_id,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.LOW,
        )

    # =========================================================================
    # PARTNER NOTIFICATIONS
    # =========================================================================

    def notify_partner(
        self,
        loan_id: int,
        partner_id: int,
        partner_name: str,
        event_type: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send notification to a partner (agent, title company, etc.)."""
        context["partner_name"] = partner_name

        return self.queue_notification(
            loan_id=loan_id,
            event_type=f"partner_{event_type}",
            recipient_id=partner_id,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def send_partner_portal_invite(
        self,
        loan_id: int,
        partner_id: int,
        partner_name: str,
        access_token: str,
        portal_url: str,
    ) -> Dict[str, Any]:
        """Send partner portal access invitation."""
        context = {
            "partner_name": partner_name,
            "portal_url": f"{portal_url}?token={access_token}",
            "access_token": access_token,
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="partner_portal_invite",
            recipient_id=partner_id,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.HIGH,
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """Render template with context variables."""
        if not template:
            return ""
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def _send_email(self, notification: NotificationQueue) -> Dict[str, Any]:
        """Send email notification using notification service."""
        # In a real implementation, we'd look up recipient email from recipient_id
        # For now, use the notification service with placeholder
        return self.notification_service.send_email(
            to_email="placeholder@example.com",  # Would lookup from recipient_id
            subject=notification.subject,
            html_content=notification.body,
        )

    def _send_sms(self, notification: NotificationQueue) -> Dict[str, Any]:
        """Send SMS notification using notification service."""
        # In a real implementation, we'd look up recipient phone from recipient_id
        return self.notification_service.send_sms(
            to_phone="+10000000000",  # Would lookup from recipient_id
            message=notification.body,
        )
