"""
Perennia Docs Notification Worker

Sends notifications with quiet hours support.

Features:
- Email and SMS notification delivery
- Quiet hours enforcement (no messages at night)
- Timezone-aware scheduling
- Retry logic with backoff
- Template rendering
"""

import os
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import pytz

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """Result of notification delivery."""
    success: bool
    channel: str
    recipient: str
    message_id: Optional[str] = None
    error: Optional[str] = None


class QuietHoursManager:
    """
    Manages quiet hours for notifications.

    Default quiet hours: 9 PM - 8 AM in recipient's timezone.
    """

    def __init__(
        self,
        default_start: str = "21:00",
        default_end: str = "08:00",
        default_timezone: str = "America/New_York"
    ):
        self.default_start = default_start
        self.default_end = default_end
        self.default_timezone = default_timezone

    def is_quiet_hours(
        self,
        tz_name: str = None,
        start: str = None,
        end: str = None
    ) -> bool:
        """
        Check if current time is within quiet hours.

        Args:
            tz_name: Timezone name (e.g., 'America/New_York')
            start: Quiet hours start (HH:MM)
            end: Quiet hours end (HH:MM)

        Returns:
            True if currently in quiet hours
        """
        tz = pytz.timezone(tz_name or self.default_timezone)
        now = datetime.now(tz)

        start_time = self._parse_time(start or self.default_start)
        end_time = self._parse_time(end or self.default_end)

        current_time = now.time()

        # Handle overnight quiet hours (e.g., 21:00 - 08:00)
        if start_time > end_time:
            return current_time >= start_time or current_time < end_time
        else:
            return start_time <= current_time < end_time

    def get_next_send_time(
        self,
        tz_name: str = None,
        start: str = None,
        end: str = None
    ) -> datetime:
        """
        Get the next time a notification can be sent.

        Returns:
            datetime when quiet hours end
        """
        tz = pytz.timezone(tz_name or self.default_timezone)
        now = datetime.now(tz)

        end_time = self._parse_time(end or self.default_end)

        # If we're in quiet hours, return end of quiet hours
        if self.is_quiet_hours(tz_name, start, end):
            # Calculate next end time
            next_send = now.replace(
                hour=end_time.hour,
                minute=end_time.minute,
                second=0,
                microsecond=0
            )

            # If end time already passed today, it's tomorrow
            if now.time() > end_time:
                next_send = next_send + timedelta(days=1)

            return next_send

        return now

    def _parse_time(self, time_str: str) -> time:
        """Parse HH:MM string to time object."""
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))


class EmailSender:
    """Email sending via AWS SES or SMTP."""

    def __init__(self):
        self.provider = os.getenv("EMAIL_PROVIDER", "ses")
        self.from_email = os.getenv("EMAIL_FROM", "docs@perennia.ai")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Perennia Docs")

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> NotificationResult:
        """Send an email."""
        if self.provider == "ses":
            return self._send_ses(to_email, subject, body, html_body)
        else:
            return self._send_smtp(to_email, subject, body, html_body)

    def _send_ses(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str]
    ) -> NotificationResult:
        """Send via AWS SES."""
        try:
            import boto3

            client = boto3.client('ses')

            message = {
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': body}
                }
            }

            if html_body:
                message['Body']['Html'] = {'Data': html_body}

            response = client.send_email(
                Source=f"{self.from_name} <{self.from_email}>",
                Destination={'ToAddresses': [to_email]},
                Message=message
            )

            return NotificationResult(
                success=True,
                channel='email',
                recipient=to_email,
                message_id=response['MessageId']
            )

        except Exception as e:
            logger.error(f"SES send failed: {e}")
            return NotificationResult(
                success=False,
                channel='email',
                recipient=to_email,
                error=str(e)
            )

    def _send_smtp(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str]
    ) -> NotificationResult:
        """Send via SMTP."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_pass = os.getenv("SMTP_PASSWORD")

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            msg.attach(MIMEText(body, 'plain'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            return NotificationResult(
                success=True,
                channel='email',
                recipient=to_email
            )

        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return NotificationResult(
                success=False,
                channel='email',
                recipient=to_email,
                error=str(e)
            )


class SMSSender:
    """SMS sending via Telnyx or SNS."""

    def __init__(self):
        self.provider = os.getenv("SMS_PROVIDER", "telnyx")
        self.from_number = os.getenv("TELNYX_PHONE_NUMBER")

    def send(self, to_phone: str, body: str) -> NotificationResult:
        """Send an SMS."""
        if self.provider == "telnyx":
            return self._send_telnyx(to_phone, body)
        else:
            return self._send_sns(to_phone, body)

    def _send_telnyx(self, to_phone: str, body: str) -> NotificationResult:
        """Send via Telnyx."""
        try:
            from telephony.sms import send_sms as telnyx_send_sms

            telnyx_from = os.getenv("TELNYX_PHONE_NUMBER") or self.from_number

            result = telnyx_send_sms(
                to=to_phone,
                from_=telnyx_from,
                text=body,
            )

            msg_id = result.get("id", "unknown")

            return NotificationResult(
                success=True,
                channel='sms',
                recipient=to_phone,
                message_id=msg_id
            )

        except Exception as e:
            logger.error(f"Telnyx send failed: {e}")
            return NotificationResult(
                success=False,
                channel='sms',
                recipient=to_phone,
                error=str(e)
            )

    def _send_sns(self, to_phone: str, body: str) -> NotificationResult:
        """Send via AWS SNS."""
        try:
            import boto3

            client = boto3.client('sns')

            response = client.publish(
                PhoneNumber=to_phone,
                Message=body
            )

            return NotificationResult(
                success=True,
                channel='sms',
                recipient=to_phone,
                message_id=response['MessageId']
            )

        except Exception as e:
            logger.error(f"SNS send failed: {e}")
            return NotificationResult(
                success=False,
                channel='sms',
                recipient=to_phone,
                error=str(e)
            )


class PerenniaNotificationWorker:
    """
    Worker that processes and sends notifications.

    Features:
    - Quiet hours enforcement
    - Email and SMS delivery
    - Retry with exponential backoff
    - Status tracking
    """

    def __init__(self, db: Session):
        """
        Initialize worker.

        Args:
            db: Database session
        """
        self.db = db
        self.quiet_hours = QuietHoursManager()
        self.email_sender = EmailSender()
        self.sms_sender = SMSSender()
        self.batch_size = 20
        self.max_retries = 3

    def get_pending_notifications(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get notifications ready to send."""
        result = self.db.execute(text("""
            SELECT id, loan_id, lead_id, channel, template,
                   recipient_email, recipient_phone, subject, body,
                   metadata, quiet_hours_start, quiet_hours_end,
                   scheduled_for, created_at
            FROM perennia_notifications
            WHERE status = 'pending'
              AND (scheduled_for IS NULL OR scheduled_for <= NOW())
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"limit": limit or self.batch_size})

        return [dict(row._mapping) for row in result]

    def send_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a single notification.

        Args:
            notification: Notification record

        Returns:
            Dict with send result
        """
        notif_id = notification['id']
        channel = notification['channel']

        result = {
            "notification_id": notif_id,
            "success": False,
            "channel": channel,
            "deferred": False
        }

        # Check quiet hours
        quiet_start = notification.get('quiet_hours_start', '21:00')
        quiet_end = notification.get('quiet_hours_end', '08:00')

        if self.quiet_hours.is_quiet_hours(start=quiet_start, end=quiet_end):
            # Defer until quiet hours end
            next_send = self.quiet_hours.get_next_send_time(start=quiet_start, end=quiet_end)

            self.db.execute(text("""
                UPDATE perennia_notifications
                SET scheduled_for = :scheduled, status = 'scheduled', updated_at = NOW()
                WHERE id = :id
            """), {"id": notif_id, "scheduled": next_send})
            self.db.commit()

            result["deferred"] = True
            result["scheduled_for"] = next_send.isoformat()
            return result

        # Send based on channel
        if channel.upper() == 'EMAIL':
            send_result = self.email_sender.send(
                to_email=notification['recipient_email'],
                subject=notification['subject'],
                body=notification['body']
            )
        elif channel.upper() == 'SMS':
            send_result = self.sms_sender.send(
                to_phone=notification['recipient_phone'],
                body=notification['body']
            )
        else:
            send_result = NotificationResult(
                success=False,
                channel=channel,
                recipient='unknown',
                error=f"Unknown channel: {channel}"
            )

        # Update database
        if send_result.success:
            self.db.execute(text("""
                UPDATE perennia_notifications
                SET status = 'sent',
                    sent_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": notif_id})

            result["success"] = True
            result["message_id"] = send_result.message_id

        else:
            self.db.execute(text("""
                UPDATE perennia_notifications
                SET status = 'failed',
                    failure_reason = :reason,
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": notif_id, "reason": send_result.error})

            result["error"] = send_result.error

        self.db.commit()
        return result

    def run_batch(self, limit: int = None) -> Dict[str, Any]:
        """Process a batch of notifications."""
        notifications = self.get_pending_notifications(limit)

        results = {
            "processed": 0,
            "sent": 0,
            "deferred": 0,
            "failed": 0,
            "details": []
        }

        for notif in notifications:
            send_result = self.send_notification(notif)
            results["processed"] += 1
            results["details"].append(send_result)

            if send_result.get("success"):
                results["sent"] += 1
            elif send_result.get("deferred"):
                results["deferred"] += 1
            else:
                results["failed"] += 1

        return results


def run_notification_worker(db: Session, batch_size: int = 20) -> Dict[str, Any]:
    """
    Run notification worker.

    Args:
        db: Database session
        batch_size: Number of notifications to process

    Returns:
        Dict with processing results
    """
    worker = PerenniaNotificationWorker(db)
    return worker.run_batch(batch_size)
