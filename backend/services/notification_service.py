"""
Notification Service - Email and SMS notifications for borrower applications.

Uses SendGrid for email and Telnyx for SMS.
"""

import os
import logging
import threading
import time as _time
from typing import Optional, Dict, Any, List
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType
from telephony.provider import get_telephony_provider
import base64
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================================
# CIRCUIT BREAKER — protects SendGrid calls from cascading failures
# ============================================================================

class SendGridCircuitBreaker:
    """Thread-safe circuit breaker for SendGrid API calls.

    States:
        CLOSED   — normal operation, requests pass through
        OPEN     — too many failures, requests short-circuited
        HALF_OPEN — recovery probe: one request allowed through

    Transitions:
        CLOSED  -> OPEN      when failure_count >= failure_threshold
        OPEN    -> HALF_OPEN when recovery_timeout seconds have elapsed
        HALF_OPEN -> CLOSED  when a probe request succeeds
        HALF_OPEN -> OPEN    when a probe request fails
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self._state = self.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if _time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = self.HALF_OPEN
                    logger.info("SendGrid circuit breaker: OPEN -> HALF_OPEN (recovery probe)")
            return self._state

    def allow_request(self) -> bool:
        """Return True if the request should be attempted."""
        return self.state != self.OPEN

    def record_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == self.HALF_OPEN:
                logger.info("SendGrid circuit breaker: HALF_OPEN -> CLOSED (probe succeeded)")
            self._state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = _time.time()
            if self._failure_count >= self._failure_threshold:
                if self._state != self.OPEN:
                    logger.warning(
                        f"SendGrid circuit breaker: {self._state} -> OPEN "
                        f"({self._failure_count} consecutive failures)"
                    )
                self._state = self.OPEN


# Module-level singleton
_sendgrid_circuit_breaker = SendGridCircuitBreaker(
    failure_threshold=int(os.getenv("SENDGRID_CB_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("SENDGRID_CB_TIMEOUT", "60")),
)

# SendGrid configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _DEFAULT_EMAIL
except ImportError:
    _DEFAULT_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", "sarah@reply.perenniaai.com")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", _DEFAULT_EMAIL)
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "Sarah from Perennia AI")

# Telnyx configuration
TELNYX_API_KEY = (os.getenv("TELNYX_API_KEY") or "").strip()
TELNYX_FROM_NUMBER = os.getenv("TELNYX_PHONE_NUMBER") or os.getenv("TELNYX_FROM_NUMBER")

# Application URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


class NotificationService:
    """Service for sending email and SMS notifications."""

    def __init__(self):
        self.sendgrid_client = None
        self.telephony_provider = None

        if SENDGRID_API_KEY:
            self.sendgrid_client = SendGridAPIClient(SENDGRID_API_KEY)
            # Set a 30-second timeout on the underlying HTTP client to prevent
            # indefinite hangs when SendGrid is slow or unreachable.
            if hasattr(self.sendgrid_client, 'client'):
                self.sendgrid_client.client.timeout = 30
            logger.info("SendGrid client initialized")
        else:
            logger.warning("SendGrid API key not configured - emails will be logged only")

        try:
            self.telephony_provider = get_telephony_provider()
            logger.info("Telnyx telephony provider initialized for SMS")
        except Exception as e:
            self.telephony_provider = None
            logger.warning(f"Telephony provider not configured - SMS will be logged only: {e}")

    # =========================================================================
    # EMAIL METHODS
    # =========================================================================

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: Optional[str] = None,
        attachments: Optional[List[Dict]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via SendGrid.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML body content
            plain_content: Plain text fallback (optional)
            attachments: List of attachment dicts with 'content', 'filename', 'type'
            cc: List of CC email addresses
            bcc: List of BCC email addresses

        Returns:
            Dict with 'success' boolean and 'message_id' or 'error'
        """
        try:
            message = Mail(
                from_email=Email(SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME),
                to_emails=To(to_email),
                subject=subject,
                html_content=html_content,
            )

            if plain_content:
                message.add_content(Content("text/plain", plain_content))

            if cc:
                for cc_email in cc:
                    message.add_cc(cc_email)

            if bcc:
                for bcc_email in bcc:
                    message.add_bcc(bcc_email)

            if attachments:
                for att in attachments:
                    attachment = Attachment(
                        FileContent(att.get('content', '')),
                        FileName(att.get('filename', 'attachment')),
                        FileType(att.get('type', 'application/octet-stream')),
                    )
                    message.add_attachment(attachment)

            if not self.sendgrid_client:
                logger.info(f"[DRY RUN] Would send email to {self._mask_email(to_email)}: {subject}")
                return {"success": True, "dry_run": True}

            # Circuit breaker: short-circuit if SendGrid is known-down
            if not _sendgrid_circuit_breaker.allow_request():
                logger.warning(f"SendGrid circuit breaker OPEN — email to {self._mask_email(to_email)} deferred")
                return {"success": False, "error": "Email service temporarily unavailable", "circuit_open": True}

            response = self.sendgrid_client.send(message)

            if response.status_code in [200, 201, 202]:
                _sendgrid_circuit_breaker.record_success()
            else:
                _sendgrid_circuit_breaker.record_failure()

            logger.info(f"Email sent to {self._mask_email(to_email)}: {subject} (status: {response.status_code})")

            return {
                "success": response.status_code in [200, 201, 202],
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id"),
            }

        except Exception as e:
            _sendgrid_circuit_breaker.record_failure()
            logger.error(f"Failed to send email to {self._mask_email(to_email)}: {str(e)}")
            return {"success": False, "error": "Internal server error"}

    def send_application_confirmation(
        self,
        borrower_email: str,
        borrower_name: str,
        application_id: str,
        lo_name: str,
        lo_email: str,
        lo_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send application submission confirmation to borrower."""

        subject = "Your Mortgage Application Has Been Received"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <div style="text-align: center; margin-bottom: 32px;">
                        <div style="width: 64px; height: 64px; background: #10b981; border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                            <span style="color: white; font-size: 32px;">✓</span>
                        </div>
                        <h1 style="margin: 0; color: #111827; font-size: 24px;">Application Submitted!</h1>
                    </div>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Hi {borrower_name},
                    </p>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Thank you for submitting your mortgage application. We've received all your information and our team is already reviewing it.
                    </p>

                    <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0;">
                        <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">Application Reference</p>
                        <p style="margin: 0; color: #111827; font-size: 18px; font-weight: 600;">{application_id[:8].upper()}</p>
                    </div>

                    <h2 style="color: #111827; font-size: 18px; margin: 32px 0 16px;">What happens next?</h2>

                    <div style="margin-bottom: 16px;">
                        <div style="display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px;">
                            <span style="color: #218D8D; font-weight: bold;">1.</span>
                            <span style="color: #374151;">Your loan officer will review your application within 24 hours</span>
                        </div>
                        <div style="display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px;">
                            <span style="color: #218D8D; font-weight: bold;">2.</span>
                            <span style="color: #374151;">You'll receive a call to discuss your loan options</span>
                        </div>
                        <div style="display: flex; align-items: flex-start; gap: 12px;">
                            <span style="color: #218D8D; font-weight: bold;">3.</span>
                            <span style="color: #374151;">We'll guide you through the approval process</span>
                        </div>
                    </div>

                    <div style="background: linear-gradient(135deg, #218D8D 0%, #1a7070 100%); border-radius: 12px; padding: 24px; margin: 32px 0; color: white;">
                        <p style="margin: 0 0 8px; font-size: 14px; opacity: 0.9;">Your Loan Officer</p>
                        <p style="margin: 0 0 4px; font-size: 18px; font-weight: 600;">{lo_name}</p>
                        <p style="margin: 0; font-size: 14px;">
                            <a href="mailto:{lo_email}" style="color: white;">{lo_email}</a>
                            {f'<br>{lo_phone}' if lo_phone else ''}
                        </p>
                    </div>

                    <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 32px;">
                        Questions? Reply to this email or call your loan officer directly.
                    </p>

                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
                    This is an automated message from Perennia Mortgage.
                </p>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
        )

    def send_document_request(
        self,
        borrower_email: str,
        borrower_name: str,
        documents_needed: List[str],
        upload_link: str,
        lo_name: str,
    ) -> Dict[str, Any]:
        """Send document request email to borrower."""

        subject = "Documents Needed for Your Mortgage Application"

        docs_list = "".join([
            f'<li style="margin-bottom: 8px; color: #374151;">{doc}</li>'
            for doc in documents_needed
        ])

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <h1 style="margin: 0 0 24px; color: #111827; font-size: 24px;">Documents Needed</h1>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Hi {borrower_name},
                    </p>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        To continue processing your mortgage application, we need the following documents:
                    </p>

                    <div style="background: #fef3cd; border-left: 4px solid #f59e0b; padding: 16px 20px; margin: 24px 0; border-radius: 0 8px 8px 0;">
                        <ul style="margin: 0; padding-left: 20px;">
                            {docs_list}
                        </ul>
                    </div>

                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{upload_link}" style="display: inline-block; background: #218D8D; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            Upload Documents
                        </a>
                    </div>

                    <p style="color: #6b7280; font-size: 14px; text-align: center;">
                        Need help? Contact {lo_name} for assistance.
                    </p>

                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
        )

    def send_application_reminder(
        self,
        borrower_email: str,
        borrower_name: str,
        resume_link: str,
        progress_percent: int,
        lo_name: str,
    ) -> Dict[str, Any]:
        """Send reminder to complete incomplete application."""

        subject = "Continue Your Mortgage Application"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <h1 style="margin: 0 0 24px; color: #111827; font-size: 24px;">You're Almost There!</h1>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Hi {borrower_name},
                    </p>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Your mortgage application is {progress_percent}% complete. Just a few more steps and you'll be done!
                    </p>

                    <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 24px 0;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span style="color: #374151; font-weight: 500;">Progress</span>
                            <span style="color: #218D8D; font-weight: 600;">{progress_percent}%</span>
                        </div>
                        <div style="background: #e5e7eb; border-radius: 9999px; height: 8px; overflow: hidden;">
                            <div style="background: linear-gradient(90deg, #218D8D, #10b981); height: 100%; width: {progress_percent}%; border-radius: 9999px;"></div>
                        </div>
                    </div>

                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{resume_link}" style="display: inline-block; background: #218D8D; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            Continue Application
                        </a>
                    </div>

                    <p style="color: #6b7280; font-size: 14px; text-align: center;">
                        Your progress has been saved. Pick up right where you left off.
                    </p>

                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
        )

    def send_status_update(
        self,
        borrower_email: str,
        borrower_name: str,
        new_status: str,
        status_message: str,
        lo_name: str,
        lo_email: str,
    ) -> Dict[str, Any]:
        """Send application status update to borrower."""

        status_colors = {
            "approved": "#10b981",
            "conditionally_approved": "#f59e0b",
            "submitted": "#3b82f6",
            "processing": "#8b5cf6",
            "clear_to_close": "#10b981",
            "funded": "#10b981",
            "denied": "#ef4444",
        }

        status_icons = {
            "approved": "✓",
            "conditionally_approved": "!",
            "submitted": "→",
            "processing": "⟳",
            "clear_to_close": "✓",
            "funded": "🎉",
            "denied": "✗",
        }

        color = status_colors.get(new_status.lower(), "#6b7280")
        icon = status_icons.get(new_status.lower(), "•")

        subject = f"Application Update: {new_status.replace('_', ' ').title()}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <div style="text-align: center; margin-bottom: 32px;">
                        <div style="width: 64px; height: 64px; background: {color}; border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                            <span style="color: white; font-size: 32px;">{icon}</span>
                        </div>
                        <h1 style="margin: 0; color: #111827; font-size: 24px;">Status Update</h1>
                    </div>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Hi {borrower_name},
                    </p>

                    <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0; text-align: center;">
                        <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">Current Status</p>
                        <p style="margin: 0; color: {color}; font-size: 20px; font-weight: 700;">
                            {new_status.replace('_', ' ').title()}
                        </p>
                    </div>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        {status_message}
                    </p>

                    <div style="border-top: 1px solid #e5e7eb; margin-top: 32px; padding-top: 24px;">
                        <p style="color: #6b7280; font-size: 14px; margin: 0 0 8px;">Your Loan Officer</p>
                        <p style="color: #111827; font-size: 16px; margin: 0;">
                            {lo_name} - <a href="mailto:{lo_email}" style="color: #218D8D;">{lo_email}</a>
                        </p>
                    </div>

                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
        )

    def send_appointment_confirmation(
        self,
        borrower_email: str,
        borrower_name: str,
        appointment_type: str,
        appointment_time: datetime,
        lo_name: str,
        meeting_link: Optional[str] = None,
        phone_number: Optional[str] = None,
        appointment_id: Optional[str] = None,
        duration_minutes: int = 30,
        lo_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send appointment confirmation to borrower with calendar invite attachment."""
        import base64
        from utils.calendar_invite import generate_appointment_ics

        formatted_time = appointment_time.strftime("%A, %B %d, %Y at %I:%M %p")

        meeting_info = ""
        if meeting_link:
            meeting_info = f'''
            <div style="text-align: center; margin: 24px 0;">
                <a href="{meeting_link}" style="display: inline-block; background: #218D8D; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Join Video Call
                </a>
            </div>
            '''
        elif phone_number:
            meeting_info = f'''
            <p style="color: #374151; font-size: 16px; text-align: center;">
                We'll call you at: <strong>{phone_number}</strong>
            </p>
            '''

        subject = f"Appointment Confirmed: {appointment_type}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <div style="text-align: center; margin-bottom: 32px;">
                        <div style="font-size: 48px; margin-bottom: 16px;">📅</div>
                        <h1 style="margin: 0; color: #111827; font-size: 24px;">Appointment Confirmed</h1>
                    </div>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Hi {borrower_name},
                    </p>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Your {appointment_type} with {lo_name} has been confirmed.
                    </p>

                    <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0; text-align: center;">
                        <p style="margin: 0 0 4px; color: #6b7280; font-size: 14px;">When</p>
                        <p style="margin: 0; color: #111827; font-size: 18px; font-weight: 600;">
                            {formatted_time}
                        </p>
                    </div>

                    {meeting_info}

                    <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 32px;">
                        Need to reschedule? Reply to this email or contact {lo_name}.
                    </p>

                </div>
            </div>
        </body>
        </html>
        """

        # Generate ICS calendar invite attachment
        attachments = None
        if appointment_id:
            try:
                ics_content = generate_appointment_ics(
                    appointment_id=appointment_id,
                    contact_name=borrower_name,
                    contact_email=borrower_email,
                    start_time=appointment_time,
                    duration_minutes=duration_minutes,
                    appointment_type=appointment_type.lower().replace(" ", "_") if appointment_type else "consultation",
                    meeting_link=meeting_link,
                    loan_officer_name=lo_name,
                    loan_officer_email=lo_email,
                )
                # Base64 encode the ICS content
                ics_base64 = base64.b64encode(ics_content.encode('utf-8')).decode('utf-8')
                attachments = [{
                    'content': ics_base64,
                    'filename': f'appointment-{appointment_id}.ics',
                    'type': 'text/calendar',
                }]
                logger.info(f"Generated calendar invite for appointment {appointment_id}")
            except Exception as e:
                logger.warning(f"Failed to generate calendar invite: {e}")

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
            attachments=attachments,
        )

    def send_lo_new_application_alert(
        self,
        lo_email: str,
        lo_name: str,
        borrower_name: str,
        borrower_email: str,
        borrower_phone: Optional[str],
        loan_purpose: str,
        loan_amount: float,
        application_id: str,
    ) -> Dict[str, Any]:
        """Send new application alert to loan officer."""

        subject = f"New Application: {borrower_name}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <div style="background: #218D8D; color: white; padding: 16px 24px; margin: -40px -40px 32px; border-radius: 16px 16px 0 0;">
                        <h1 style="margin: 0; font-size: 20px;">🎉 New Application Received</h1>
                    </div>

                    <h2 style="color: #111827; font-size: 24px; margin: 0 0 24px;">{borrower_name}</h2>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Email</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                <a href="mailto:{borrower_email}" style="color: #218D8D;">{borrower_email}</a>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Phone</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                {borrower_phone or 'Not provided'}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Purpose</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                {loan_purpose.replace('_', ' ').title()}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; color: #6b7280;">Loan Amount</td>
                            <td style="padding: 12px 0; color: #111827; text-align: right; font-weight: 600;">
                                ${loan_amount:,.0f}
                            </td>
                        </tr>
                    </table>

                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{FRONTEND_URL}/applications/{application_id}" style="display: inline-block; background: #218D8D; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            View Application
                        </a>
                    </div>

                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=lo_email,
            subject=subject,
            html_content=html_content,
        )

    def send_lo_new_lead_alert(
        self,
        lo_email: str,
        lo_name: str,
        lead_name: str,
        lead_email: str,
        lead_phone: Optional[str],
        lead_source: str,
        intent_type: Optional[str] = None,
        lead_id: Optional[int] = None,
        microsite_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send new lead alert to loan officer from microsite or other sources."""

        subject = f"🔔 New Lead: {lead_name}"
        intent_display = (intent_type or "General Inquiry").replace("_", " ").title()

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                    <div style="background: #218D8D; color: white; padding: 16px 24px; margin: -40px -40px 32px; border-radius: 16px 16px 0 0;">
                        <h1 style="margin: 0; font-size: 20px;">🔔 New Lead from {lead_source}</h1>
                    </div>

                    <p style="color: #6b7280; margin: 0 0 8px;">Hi {lo_name.split()[0] if lo_name else 'there'},</p>
                    <p style="color: #111827; margin: 0 0 24px;">You have a new lead! Here are the details:</p>

                    <h2 style="color: #111827; font-size: 24px; margin: 0 0 24px;">{lead_name}</h2>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Email</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                <a href="mailto:{lead_email}" style="color: #218D8D;">{lead_email}</a>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Phone</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                {lead_phone or 'Not provided'}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #6b7280;">Interest</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #e5e7eb; color: #111827; text-align: right;">
                                {intent_display}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; color: #6b7280;">Source</td>
                            <td style="padding: 12px 0; color: #111827; text-align: right;">
                                {microsite_name or lead_source}
                            </td>
                        </tr>
                    </table>

                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{FRONTEND_URL}/leads{f'/{lead_id}' if lead_id else ''}" style="display: inline-block; background: #218D8D; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            View Lead
                        </a>
                    </div>

                    <p style="color: #6b7280; font-size: 14px; margin: 24px 0 0; text-align: center;">
                        Respond quickly to maximize conversion! 🚀
                    </p>

                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(
            to_email=lo_email,
            subject=subject,
            html_content=html_content,
        )

    # =========================================================================
    # SMS METHODS
    # =========================================================================

    @staticmethod
    def _mask_phone(phone):
        """OBS-004: Mask phone number for safe logging."""
        if not phone or len(phone) < 7:
            return "***"
        return phone[:2] + "***" + phone[-4:]

    @staticmethod
    def _mask_email(email):
        """OBS-008: Mask email address for safe logging."""
        if not email or '@' not in email:
            return '***'
        local, domain = email.rsplit('@', 1)
        return f"{local[:2]}***@{domain}" if len(local) > 2 else f"***@{domain}"

    def send_sms(
        self,
        to_phone: str,
        message: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send an SMS via Telnyx.

        Args:
            to_phone: Recipient phone number (E.164 format preferred)
            message: SMS message content (max 1600 chars)
            skip_consent_check: If True, bypass TCPA consent gate (default False)

        Returns:
            Dict with 'success' boolean and 'message_sid' or 'error'
        """
        # COMP-003: TCPA consent gate
        skip_consent = kwargs.pop('skip_consent_check', False)
        if not skip_consent:
            try:
                from services.scheduler_sms_sender import check_sms_consent
                can_send, reason = check_sms_consent(to_phone)
                if not can_send:
                    logger.info("SMS to %s blocked by TCPA consent: %s", self._mask_phone(to_phone), reason)
                    return {"success": False, "error": f"TCPA consent blocked: {reason}"}
            except ImportError:
                pass  # Module may not exist yet - allow sending
            except Exception as e:
                logger.error("TCPA consent check error, blocking SMS: %s", e)
                return {"success": False, "error": "consent check failed"}

        try:
            # Format phone number if needed
            if not to_phone.startswith('+'):
                # Assume US number
                to_phone = '+1' + to_phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

            if not self.telephony_provider:
                logger.info("[DRY RUN] Would send SMS to %s: %s...", self._mask_phone(to_phone), message[:50])
                return {"success": True, "dry_run": True}

            import telnyx
            telnyx_from = os.getenv("TELNYX_PHONE_NUMBER") or TELNYX_FROM_NUMBER
            sms = telnyx.Message.create(
                from_=telnyx_from,
                to=to_phone,
                text=message,
            )

            msg_id = getattr(sms, 'id', None) or getattr(getattr(sms, 'data', None), 'id', None) or 'unknown'
            logger.info("SMS sent to %s: %s", self._mask_phone(to_phone), msg_id)

            return {
                "success": True,
                "message_sid": msg_id,
                "status": "sent",
            }

        except Exception as e:
            logger.error("Failed to send SMS to %s: %s", self._mask_phone(to_phone), str(e))
            return {"success": False, "error": "Internal server error"}

    def send_application_confirmation_sms(
        self,
        borrower_phone: str,
        borrower_name: str,
        lo_name: str,
    ) -> Dict[str, Any]:
        """Send application confirmation SMS."""

        message = (
            f"Hi {borrower_name}! Your mortgage application has been received. "
            f"{lo_name} will review it within 24 hours and be in touch. "
            f"Reply STOP to opt out."
        )

        return self.send_sms(borrower_phone, message)

    def send_document_request_sms(
        self,
        borrower_phone: str,
        borrower_name: str,
        doc_count: int,
        upload_link: str,
    ) -> Dict[str, Any]:
        """Send document request SMS."""

        message = (
            f"Hi {borrower_name}, we need {doc_count} document(s) for your mortgage application. "
            f"Upload here: {upload_link}"
        )

        return self.send_sms(borrower_phone, message)

    def send_reminder_sms(
        self,
        borrower_phone: str,
        borrower_name: str,
        resume_link: str,
    ) -> Dict[str, Any]:
        """Send application reminder SMS."""

        message = (
            f"Hi {borrower_name}, your mortgage application is incomplete. "
            f"Continue where you left off: {resume_link}"
        )

        return self.send_sms(borrower_phone, message)

    def send_appointment_reminder_sms(
        self,
        borrower_phone: str,
        borrower_name: str,
        appointment_time: datetime,
        lo_name: str,
        meeting_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send appointment reminder SMS."""

        time_str = appointment_time.strftime("%I:%M %p")
        date_str = appointment_time.strftime("%B %d")

        if meeting_link:
            message = (
                f"Reminder: Your call with {lo_name} is tomorrow at {time_str}. "
                f"Join here: {meeting_link}"
            )
        else:
            message = (
                f"Reminder: {lo_name} will call you tomorrow at {time_str} ({date_str}) "
                f"to discuss your mortgage application."
            )

        return self.send_sms(borrower_phone, message)

    # =========================================================================
    # TEMPLATE BUILDER METHODS
    # These methods return content dictionaries for testing and customization
    # =========================================================================

    def _build_welcome_email(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build welcome email content.

        Args:
            data: Dict with 'first_name', 'application_id', optional 'lo_name'

        Returns:
            Dict with 'subject', 'body', 'html_body'
        """
        first_name = data.get("first_name", "there")
        application_id = data.get("application_id", "")
        lo_name = data.get("lo_name", "your loan officer")

        subject = "Welcome to Your Mortgage Application"

        body = f"""Hi {first_name},

Thank you for starting your mortgage application with us! We're excited to help you on your journey to homeownership.

Your application reference: {application_id}

Next Steps:
1. Complete your application if you haven't already
2. Upload any required documents
3. {lo_name} will review and reach out within 24 hours

We're here to make this process as smooth as possible.

Best regards,
The Perennia Team"""

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h1 style="color: #218D8D;">Welcome, {first_name}!</h1>
            <p>Thank you for starting your mortgage application with us! We're excited to help you on your journey to homeownership.</p>
            <p><strong>Application Reference:</strong> {application_id}</p>
            <h2>Next Steps:</h2>
            <ol>
                <li>Complete your application if you haven't already</li>
                <li>Upload any required documents</li>
                <li>{lo_name} will review and reach out within 24 hours</li>
            </ol>
            <p>We're here to make this process as smooth as possible.</p>
        </div>
        """

        return {
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }

    def _build_document_confirmation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build document upload confirmation content.

        Args:
            data: Dict with 'first_name', 'document_type', 'document_name',
                  optional 'remaining_documents'

        Returns:
            Dict with 'subject', 'body', 'html_body'
        """
        first_name = data.get("first_name", "there")
        document_type = data.get("document_type", "document")
        document_name = data.get("document_name", "your document")
        remaining = data.get("remaining_documents", [])

        subject = f"Document Received: {document_type.replace('_', ' ').title()}"

        remaining_text = ""
        if remaining:
            remaining_text = f"\n\nStill needed:\n" + "\n".join(f"- {doc}" for doc in remaining)
        elif remaining is not None:
            remaining_text = "\n\nAll required documents have been received!"

        body = f"""Hi {first_name},

We've received your {document_type.replace('_', ' ')}: {document_name}

Thank you for submitting this document. Our team will review it shortly.{remaining_text}

Best regards,
The Perennia Team"""

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h1 style="color: #10b981;">✓ Document Received</h1>
            <p>Hi {first_name},</p>
            <p>We've received your <strong>{document_type.replace('_', ' ')}</strong>: {document_name}</p>
            <p>Thank you for submitting this document. Our team will review it shortly.</p>
            {"<h3>Still needed:</h3><ul>" + "".join(f"<li>{doc}</li>" for doc in remaining) + "</ul>" if remaining else "<p style='color: #10b981;'><strong>All required documents have been received!</strong></p>" if remaining is not None else ""}
        </div>
        """

        return {
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }

    def _build_reminder_email(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build application reminder email content.

        Args:
            data: Dict with 'first_name', 'completion_percentage', 'application_id',
                  'resume_link', optional 'missing_sections'

        Returns:
            Dict with 'subject', 'body', 'html_body'
        """
        first_name = data.get("first_name", "there")
        completion = data.get("completion_percentage", 0)
        app_id = data.get("application_id", "")
        resume_link = data.get("resume_link", FRONTEND_URL)
        missing = data.get("missing_sections", [])

        subject = "Continue Your Mortgage Application"

        missing_text = ""
        if missing:
            missing_text = f"\n\nSections to complete:\n" + "\n".join(f"- {section}" for section in missing)

        body = f"""Hi {first_name},

Your mortgage application is {completion}% complete! You're making great progress.

Continue where you left off: {resume_link}{missing_text}

Your application has been saved, so you can pick up right where you left off.

Questions? Just reply to this email.

Best regards,
The Perennia Team"""

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h1 style="color: #218D8D;">You're {completion}% There!</h1>
            <p>Hi {first_name},</p>
            <p>Your mortgage application is almost complete. Just a few more steps!</p>
            <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <div style="background: #e5e7eb; border-radius: 9999px; height: 10px;">
                    <div style="background: #218D8D; height: 10px; width: {completion}%; border-radius: 9999px;"></div>
                </div>
                <p style="text-align: center; margin-top: 10px;"><strong>{completion}% Complete</strong></p>
            </div>
            {"<h3>Sections to complete:</h3><ul>" + "".join(f"<li>{s}</li>" for s in missing) + "</ul>" if missing else ""}
            <p style="text-align: center;">
                <a href="{resume_link}" style="background: #218D8D; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Continue Application</a>
            </p>
        </div>
        """

        return {
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "resume_link": resume_link,
        }

    def _build_submission_confirmation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build submission confirmation email content.

        Args:
            data: Dict with 'first_name', 'application_id', 'submission_date',
                  optional 'estimated_review_days', 'lo_name'

        Returns:
            Dict with 'subject', 'body', 'html_body'
        """
        first_name = data.get("first_name", "there")
        app_id = data.get("application_id", "")
        submission_date = data.get("submission_date", datetime.now())
        review_days = data.get("estimated_review_days", 1)
        lo_name = data.get("lo_name", "Your loan officer")

        if isinstance(submission_date, datetime):
            date_str = submission_date.strftime("%B %d, %Y")
        else:
            date_str = str(submission_date)

        subject = "Application Submitted Successfully!"

        body = f"""Hi {first_name},

Congratulations! Your mortgage application has been successfully submitted.

Application Reference: {app_id}
Submitted: {date_str}

What happens next:
- {lo_name} will review your application within {review_days} business day(s)
- You'll receive updates as your application progresses
- We may reach out if we need any additional information

Thank you for choosing us for your mortgage needs!

Best regards,
The Perennia Team"""

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="width: 64px; height: 64px; background: #10b981; border-radius: 50%; margin: 0 auto; display: flex; align-items: center; justify-content: center;">
                    <span style="color: white; font-size: 32px;">✓</span>
                </div>
            </div>
            <h1 style="color: #111827; text-align: center;">Application Submitted!</h1>
            <p>Hi {first_name},</p>
            <p>Congratulations! Your mortgage application has been successfully submitted.</p>
            <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center;">
                <p style="margin: 0; color: #6b7280;">Application Reference</p>
                <p style="margin: 8px 0 0; font-size: 20px; font-weight: bold; color: #111827;">{app_id}</p>
            </div>
            <h3>What happens next:</h3>
            <ul>
                <li>{lo_name} will review your application within {review_days} business day(s)</li>
                <li>You'll receive updates as your application progresses</li>
                <li>We may reach out if we need any additional information</li>
            </ul>
        </div>
        """

        return {
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "reference": app_id,
        }

    def _build_lo_alert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build new application alert for loan officer.

        Args:
            data: Dict with 'borrower_name', 'loan_amount', 'loan_purpose',
                  'application_id', 'dashboard_link', optional 'property_address',
                  'estimated_credit_score', 'property_type'

        Returns:
            Dict with 'subject', 'body', 'html_body'
        """
        borrower_name = data.get("borrower_name", "New Borrower")
        loan_amount = data.get("loan_amount", 0)
        loan_purpose = data.get("loan_purpose", "")
        app_id = data.get("application_id", "")
        dashboard_link = data.get("dashboard_link", FRONTEND_URL)
        property_address = data.get("property_address", "")
        credit_score = data.get("estimated_credit_score", "")
        property_type = data.get("property_type", "")

        subject = f"New Application: {borrower_name}"

        details = []
        if loan_purpose:
            details.append(f"- Purpose: {loan_purpose.replace('_', ' ').title()}")
        if loan_amount:
            details.append(f"- Loan Amount: ${loan_amount:,.0f}")
        if property_type:
            details.append(f"- Property Type: {property_type}")
        if property_address:
            details.append(f"- Property: {property_address}")
        if credit_score:
            details.append(f"- Est. Credit Score: {credit_score}")

        details_text = "\n".join(details) if details else "Details in dashboard"

        body = f"""New Application Received!

Borrower: {borrower_name}

{details_text}

View application: {dashboard_link}"""

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #218D8D; color: white; padding: 16px 24px; border-radius: 8px 8px 0 0;">
                <h1 style="margin: 0; font-size: 18px;">🎉 New Application Received</h1>
            </div>
            <div style="border: 1px solid #e5e7eb; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
                <h2 style="margin: 0 0 16px; color: #111827;">{borrower_name}</h2>
                <table style="width: 100%;">
                    {"".join(f'<tr><td style="padding: 8px 0; color: #6b7280;">{d.split(":")[0].replace("- ", "")}</td><td style="padding: 8px 0; text-align: right; color: #111827;">{d.split(":")[1].strip() if ":" in d else ""}</td></tr>' for d in details)}
                </table>
                <p style="text-align: center; margin-top: 24px;">
                    <a href="{dashboard_link}" style="background: #218D8D; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">View Application</a>
                </p>
            </div>
        </div>
        """

        return {
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "link": dashboard_link,
        }

    def _build_html_email(self, data: Dict[str, Any]) -> str:
        """
        Build a generic HTML email from content data.

        Args:
            data: Dict with 'subject', 'body', optional 'cta_text', 'cta_link'

        Returns:
            HTML string
        """
        subject = data.get("subject", "")
        body = data.get("body", "")
        cta_text = data.get("cta_text", "")
        cta_link = data.get("cta_link", "")

        cta_html = ""
        if cta_text and cta_link:
            cta_html = f'''
            <p style="text-align: center; margin: 24px 0;">
                <a href="{cta_link}" style="background: #218D8D; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">{cta_text}</a>
            </p>
            '''

        # Convert body newlines to HTML paragraphs
        body_html = "".join(f"<p>{line}</p>" for line in body.split("\n\n") if line.strip())

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">
            {body_html}
            {cta_html}
        </div>
        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
            <a href="#" style="color: #9ca3af;">Unsubscribe</a> from these emails
        </p>
    </div>
</body>
</html>"""

    def _calculate_reminder_time(self, last_activity: datetime) -> datetime:
        """
        Calculate when a reminder should be sent based on last activity.

        Args:
            last_activity: Datetime of last user activity

        Returns:
            Datetime when reminder should be sent (24 hours after last activity)
        """
        from datetime import timedelta
        return last_activity + timedelta(hours=24)

    # =========================================================================
    # SMS HELPER METHODS
    # =========================================================================

    def _format_sms_message(self, template_name: str, data: Dict[str, Any]) -> str:
        """
        Format an SMS message from a template.

        Args:
            template_name: Name of the template (welcome, submission_confirmation, reminder)
            data: Template variables

        Returns:
            Formatted SMS message string
        """
        templates = {
            "welcome": "Hi {name}! Welcome to Perennia Mortgage. We've received your application and will be in touch soon.",
            "submission_confirmation": "Your mortgage application ({ref}) has been submitted! We'll review it within 24 hours.",
            "reminder": "Hi {name}, your mortgage application is waiting. Continue where you left off at {link}",
            "document_received": "Thanks {name}! We received your {doc_type}. We'll let you know if we need anything else.",
            "appointment": "Reminder: Your call with {lo_name} is at {time}. {link}",
        }

        template = templates.get(template_name, "")
        if not template:
            return ""

        try:
            return template.format(**data)
        except KeyError:
            # Return template with available data
            for key, value in data.items():
                template = template.replace(f"{{{key}}}", str(value))
            return template

    def _format_phone_number(self, phone: str) -> str:
        """
        Format a phone number to E.164 format.

        Args:
            phone: Phone number in various formats

        Returns:
            Phone number in E.164 format (+1XXXXXXXXXX)
        """
        # Remove all non-digit characters
        digits = "".join(c for c in phone if c.isdigit())

        # Handle different lengths
        if len(digits) == 10:
            # US number without country code
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            # US number with country code
            return f"+{digits}"
        elif phone.startswith("+"):
            # Already has country code
            return f"+{digits}"
        else:
            # Default to US
            return f"+1{digits[-10:]}" if len(digits) >= 10 else f"+1{digits}"

    def _is_opted_out(self, phone: str) -> bool:
        """
        Check if a phone number has opted out of SMS.

        Args:
            phone: Phone number to check

        Returns:
            True if opted out, False otherwise
        """
        try:
            from database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                normalized_phone = self._normalize_phone(phone)
                result = db.execute(text("""
                    SELECT 1 FROM sms_opt_outs WHERE phone_number = :phone LIMIT 1
                """), {"phone": normalized_phone}).fetchone()
                return result is not None
            finally:
                db.close()
        except SQLAlchemyError as e:
            logger.warning(f"Error checking opt-out status for {phone}: {e}")
            # Fail open - allow sending if we can't check
            return False


# Create singleton instance
notification_service = NotificationService()
