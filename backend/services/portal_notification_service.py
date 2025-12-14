"""
Portal Notification Service - Notification management for the Perennia Portal.

Handles notification templates, queue management, email/SMS delivery,
and notification preferences for borrowers and partners.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import re

from models.portal_models import (
    NotificationTemplate, NotificationQueue, NotificationStatus, NotificationChannel,
    PortalLoan, MilestoneInstance, MilestoneStatus
)
from services.notification_service import NotificationService

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
            query = query.filter(NotificationTemplate.event_type == event_type)

        if channel:
            query = query.filter(NotificationTemplate.channel == channel)

        templates = query.order_by(NotificationTemplate.event_type).all()

        return [
            {
                "id": t.id,
                "event_type": t.event_type,
                "channel": t.channel.value,
                "subject": t.subject,
                "body_template": t.body_template,
                "variables": t.variables,
                "is_active": t.is_active,
            }
            for t in templates
        ]

    def create_template(
        self,
        event_type: str,
        channel: NotificationChannel,
        subject: str,
        body_template: str,
        variables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a notification template."""
        # Extract variables from template if not provided
        if not variables:
            variables = self._extract_variables(body_template)

        template = NotificationTemplate(
            event_type=event_type,
            channel=channel,
            subject=subject,
            body_template=body_template,
            variables=variables,
            is_active=True,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        return {
            "success": True,
            "template_id": template.id,
            "variables": variables,
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

        # Re-extract variables if body changed
        if "body_template" in updates:
            template.variables = self._extract_variables(updates["body_template"])

        self.db.commit()

        return {"success": True, "template_id": template_id}

    # =========================================================================
    # NOTIFICATION QUEUE
    # =========================================================================

    def queue_notification(
        self,
        loan_id: int,
        event_type: str,
        recipient_email: str,
        recipient_phone: Optional[str] = None,
        recipient_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        channel: NotificationChannel = NotificationChannel.EMAIL,
        scheduled_for: Optional[datetime] = None,
        priority: int = 5,
    ) -> Dict[str, Any]:
        """Queue a notification for delivery."""
        # Get template
        template = self.db.query(NotificationTemplate).filter(
            and_(
                NotificationTemplate.event_type == event_type,
                NotificationTemplate.channel == channel,
                NotificationTemplate.is_active == True
            )
        ).first()

        if not template:
            return {
                "success": False,
                "error": f"No active template found for event '{event_type}' and channel '{channel.value}'",
            }

        # Render content
        rendered_subject = self._render_template(template.subject, context or {})
        rendered_body = self._render_template(template.body_template, context or {})

        notification = NotificationQueue(
            loan_id=loan_id,
            template_id=template.id,
            channel=channel,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone,
            recipient_name=recipient_name,
            subject=rendered_subject,
            body=rendered_body,
            context=context,
            status=NotificationStatus.PENDING,
            scheduled_for=scheduled_for or datetime.utcnow(),
            priority=priority,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        logger.info(f"Queued {channel.value} notification for loan {loan_id}: {event_type}")

        return {
            "success": True,
            "notification_id": notification.id,
            "scheduled_for": notification.scheduled_for.isoformat(),
        }

    def process_pending_notifications(self, limit: int = 50) -> Dict[str, Any]:
        """Process pending notifications in the queue."""
        pending = self.db.query(NotificationQueue).filter(
            and_(
                NotificationQueue.status == NotificationStatus.PENDING,
                NotificationQueue.scheduled_for <= datetime.utcnow()
            )
        ).order_by(
            NotificationQueue.priority.desc(),
            NotificationQueue.scheduled_for
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
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.utcnow()
                    notification.external_id = result.get("message_id")
                    results["sent"] += 1
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.error_message = result.get("error")
                    notification.retry_count += 1
                    results["failed"] += 1
                    results["errors"].append({
                        "notification_id": notification.id,
                        "error": result.get("error"),
                    })

            except Exception as e:
                notification.status = NotificationStatus.FAILED
                notification.error_message = str(e)
                notification.retry_count += 1
                results["failed"] += 1
                results["errors"].append({
                    "notification_id": notification.id,
                    "error": str(e),
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
                "channel": n.channel.value,
                "subject": n.subject,
                "status": n.status.value,
                "recipient": n.recipient_email or n.recipient_phone,
                "scheduled_for": n.scheduled_for.isoformat() if n.scheduled_for else None,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "error_message": n.error_message,
            }
            for n in notifications
        ]

    def retry_failed_notifications(self, max_retries: int = 3) -> Dict[str, Any]:
        """Retry failed notifications."""
        failed = self.db.query(NotificationQueue).filter(
            and_(
                NotificationQueue.status == NotificationStatus.FAILED,
                NotificationQueue.retry_count < max_retries
            )
        ).all()

        for notification in failed:
            notification.status = NotificationStatus.PENDING
            notification.scheduled_for = datetime.utcnow() + timedelta(minutes=5 * notification.retry_count)

        self.db.commit()

        return {"queued_for_retry": len(failed)}

    # =========================================================================
    # EVENT-BASED NOTIFICATIONS
    # =========================================================================

    def notify_milestone_completed(
        self,
        loan_id: int,
        milestone_id: int,
        borrower_email: str,
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
            "milestone_name": milestone.template.name,
            "milestone_description": milestone.template.description,
            "lo_name": lo_name or "Your Loan Officer",
            "completed_date": datetime.utcnow().strftime("%B %d, %Y"),
        }

        return self.queue_notification(
            loan_id=loan_id,
            event_type="milestone_completed",
            recipient_email=borrower_email,
            recipient_name=borrower_name,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def notify_document_needed(
        self,
        loan_id: int,
        document_type: str,
        borrower_email: str,
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
            recipient_email=borrower_email,
            recipient_name=borrower_name,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=7,
        )

    def notify_stage_change(
        self,
        loan_id: int,
        from_stage: str,
        to_stage: str,
        borrower_email: str,
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
            recipient_email=borrower_email,
            recipient_name=borrower_name,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=8,
        )

    def notify_closing_reminder(
        self,
        loan_id: int,
        borrower_email: str,
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
            recipient_email=borrower_email,
            recipient_name=borrower_name,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def notify_home_value_update(
        self,
        loan_id: int,
        borrower_email: str,
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
            recipient_email=borrower_email,
            recipient_name=borrower_name,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=3,
        )

    # =========================================================================
    # PARTNER NOTIFICATIONS
    # =========================================================================

    def notify_partner(
        self,
        loan_id: int,
        partner_email: str,
        partner_name: str,
        event_type: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send notification to a partner (agent, title company, etc.)."""
        context["partner_name"] = partner_name

        return self.queue_notification(
            loan_id=loan_id,
            event_type=f"partner_{event_type}",
            recipient_email=partner_email,
            recipient_name=partner_name,
            context=context,
            channel=NotificationChannel.EMAIL,
        )

    def send_partner_portal_invite(
        self,
        loan_id: int,
        partner_email: str,
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
            recipient_email=partner_email,
            recipient_name=partner_name,
            context=context,
            channel=NotificationChannel.EMAIL,
            priority=8,
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _extract_variables(self, template: str) -> List[str]:
        """Extract variable names from template."""
        pattern = r'\{\{(\w+)\}\}'
        return list(set(re.findall(pattern, template)))

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """Render template with context variables."""
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def _send_email(self, notification: NotificationQueue) -> Dict[str, Any]:
        """Send email notification using notification service."""
        return self.notification_service.send_email(
            to_email=notification.recipient_email,
            subject=notification.subject,
            html_content=notification.body,
        )

    def _send_sms(self, notification: NotificationQueue) -> Dict[str, Any]:
        """Send SMS notification using notification service."""
        if not notification.recipient_phone:
            return {"success": False, "error": "No phone number provided"}

        return self.notification_service.send_sms(
            to_phone=notification.recipient_phone,
            message=notification.body,
        )


# Seed default notification templates
DEFAULT_TEMPLATES = [
    {
        "event_type": "milestone_completed",
        "channel": NotificationChannel.EMAIL,
        "subject": "Milestone Completed: {{milestone_name}}",
        "body_template": """
<h2>Great news, {{borrower_name}}!</h2>
<p>Your loan has reached a new milestone: <strong>{{milestone_name}}</strong></p>
<p>{{milestone_description}}</p>
<p>Completed on: {{completed_date}}</p>
<p>If you have any questions, please contact {{lo_name}}.</p>
""",
    },
    {
        "event_type": "document_needed",
        "channel": NotificationChannel.EMAIL,
        "subject": "Document Needed: {{document_type}}",
        "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>We need the following document to continue processing your loan:</p>
<p><strong>{{document_type}}</strong></p>
<p>Please upload this document by {{due_date}}.</p>
<p>You can upload documents through your borrower portal.</p>
""",
    },
    {
        "event_type": "stage_change",
        "channel": NotificationChannel.EMAIL,
        "subject": "Loan Update: {{stage_message}}",
        "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>{{stage_message}}!</p>
<p>Your loan has moved from <strong>{{from_stage}}</strong> to <strong>{{to_stage}}</strong>.</p>
<p>Log in to your portal to see your updated milestone journey.</p>
""",
    },
    {
        "event_type": "closing_reminder",
        "channel": NotificationChannel.EMAIL,
        "subject": "{{business_days_remaining}} Business Days Until Closing!",
        "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Your closing is coming up!</p>
<p><strong>Closing Date:</strong> {{closing_day}}, {{closing_date}}</p>
<p><strong>Business Days Remaining:</strong> {{business_days_remaining}}</p>
<p>Make sure you have completed all outstanding tasks in your portal.</p>
""",
    },
    {
        "event_type": "home_value_update",
        "channel": NotificationChannel.EMAIL,
        "subject": "Your Home Value Update",
        "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Here's your latest home value estimate:</p>
<p><strong>Estimated Value:</strong> {{current_value}}</p>
<p><strong>Appreciation:</strong> {{appreciation_percent}} since purchase</p>
<p>Log in to your portal to see detailed insights about your home's value.</p>
""",
    },
    {
        "event_type": "partner_portal_invite",
        "channel": NotificationChannel.EMAIL,
        "subject": "Access Your Partner Portal",
        "body_template": """
<h2>Hi {{partner_name}},</h2>
<p>You've been granted access to view loan progress.</p>
<p>Click the link below to access the partner portal:</p>
<p><a href="{{portal_url}}">Access Portal</a></p>
<p>This link is unique to you. Please do not share it.</p>
""",
    },
]
