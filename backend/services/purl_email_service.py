"""
PURL Email Service
Perennia AI - Mortgage CRM

Handles email notifications for PURL system events:
- Welcome emails with portal links
- Application submission confirmations
- Document upload notifications
- Task assignments
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    if not email or '@' not in email:
        return '***'
    local, domain = email.rsplit('@', 1)
    return f"{local[:2]}***@{domain}" if len(local) > 2 else f"***@{domain}"


# =============================================================================
# TEMPLATE CONFIGURATION
# =============================================================================

# Get templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

# Initialize Jinja2 environment
template_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(['html', 'xml'])
)


# =============================================================================
# EMAIL SERVICE
# =============================================================================

class PURLEmailService:
    """Service for sending PURL-related emails."""

    def __init__(self):
        try:
            from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL
        except ImportError:
            DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", "sarah@reply.perenniaai.com")
        self.from_email = os.getenv("EMAIL_FROM", DEFAULT_ORGANIZER_EMAIL)
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Sarah from Perennia AI")
        self.company_name = os.getenv("COMPANY_NAME", "Perennia AI")
        self.purl_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")

    # =========================================================================
    # TEMPLATE RENDERING
    # =========================================================================

    def render_template(self, template_name: str, context: Dict[str, Any]) -> tuple:
        """
        Render both HTML and text versions of an email template.

        Args:
            template_name: Base name of template (e.g., 'welcome')
            context: Template context variables

        Returns:
            Tuple of (html_content, text_content)
        """
        # Add common context
        context.update({
            "company_name": self.company_name,
            "year": datetime.now().year
        })

        html_content = None
        text_content = None

        try:
            html_template = template_env.get_template(f"{template_name}.html")
            html_content = html_template.render(context)
        except Exception as e:
            logger.warning(f"Could not render HTML template {template_name}: {e}")

        try:
            text_template = template_env.get_template(f"{template_name}.txt")
            text_content = text_template.render(context)
        except Exception as e:
            logger.warning(f"Could not render text template {template_name}: {e}")

        return html_content, text_content

    # =========================================================================
    # EMAIL SENDING
    # =========================================================================

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> bool:
        """
        Send an email using the configured email provider.

        Supports SendGrid, AWS SES, or SMTP based on configuration.
        """
        provider = os.getenv("EMAIL_PROVIDER", "sendgrid").lower()

        try:
            if provider == "sendgrid":
                return await self._send_via_sendgrid(
                    to_email, subject, html_content, text_content, reply_to
                )
            elif provider == "ses":
                return await self._send_via_ses(
                    to_email, subject, html_content, text_content, reply_to
                )
            else:
                return await self._send_via_smtp(
                    to_email, subject, html_content, text_content, reply_to
                )
        except Exception as e:
            logger.error(f"Failed to send email to {_mask_email(to_email)}: {e}")
            return False

    async def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: Optional[str],
        text_content: Optional[str],
        reply_to: Optional[str]
    ) -> bool:
        """Send email via SendGrid."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, Content

            api_key = os.getenv("SENDGRID_API_KEY")
            if not api_key:
                logger.error("SENDGRID_API_KEY not configured")
                return False

            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(to_email),
                subject=subject
            )

            if html_content:
                message.add_content(Content("text/html", html_content))
            if text_content:
                message.add_content(Content("text/plain", text_content))

            if reply_to:
                message.reply_to = Email(reply_to)

            sg = SendGridAPIClient(api_key)
            response = sg.send(message)

            logger.info(f"Email sent to {_mask_email(to_email)}, status: {response.status_code}")
            return response.status_code in [200, 201, 202]

        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False

    async def _send_via_ses(
        self,
        to_email: str,
        subject: str,
        html_content: Optional[str],
        text_content: Optional[str],
        reply_to: Optional[str]
    ) -> bool:
        """Send email via AWS SES."""
        try:
            import boto3

            ses = boto3.client(
                'ses',
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )

            body = {}
            if html_content:
                body['Html'] = {'Charset': 'UTF-8', 'Data': html_content}
            if text_content:
                body['Text'] = {'Charset': 'UTF-8', 'Data': text_content}

            response = ses.send_email(
                Source=f"{self.from_name} <{self.from_email}>",
                Destination={'ToAddresses': [to_email]},
                Message={
                    'Subject': {'Charset': 'UTF-8', 'Data': subject},
                    'Body': body
                },
                ReplyToAddresses=[reply_to] if reply_to else []
            )

            logger.info(f"Email sent to {_mask_email(to_email)}, message ID: {response['MessageId']}")
            return True

        except Exception as e:
            logger.error(f"SES error: {e}")
            return False

    async def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: Optional[str],
        text_content: Optional[str],
        reply_to: Optional[str]
    ) -> bool:
        """Send email via SMTP."""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            if reply_to:
                msg['Reply-To'] = reply_to

            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            if html_content:
                msg.attach(MIMEText(html_content, 'html'))

            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_pass = os.getenv("SMTP_PASSWORD")

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            logger.info(f"Email sent to {_mask_email(to_email)} via SMTP")
            return True

        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False

    # =========================================================================
    # PURL-SPECIFIC EMAILS
    # =========================================================================

    async def send_welcome_email(
        self,
        to_email: str,
        first_name: str,
        workspace_slug: str,
        token: str,
        loan_officer_name: Optional[str] = None,
        loan_officer_email: Optional[str] = None
    ) -> bool:
        """Send welcome email with PURL to new borrower."""
        purl_url = f"https://{self.purl_domain}/portal/{workspace_slug}?token={token}"

        context = {
            "first_name": first_name,
            "purl_url": purl_url,
            "token": token,
            "loan_officer_name": loan_officer_name or "Your Loan Officer",
            "loan_officer_email": loan_officer_email or "support@perennia.ai"
        }

        html_content, text_content = self.render_template("welcome", context)

        return await self.send_email(
            to_email=to_email,
            subject="Welcome to Your Loan Portal",
            html_content=html_content,
            text_content=text_content,
            reply_to=loan_officer_email
        )

    async def send_application_submitted_email(
        self,
        to_email: str,
        first_name: str,
        workspace_slug: str,
        token: Optional[str] = None,
        loan_officer_name: Optional[str] = None,
        loan_officer_email: Optional[str] = None,
        loan_officer_phone: Optional[str] = None
    ) -> bool:
        """Send confirmation email when application is submitted."""
        # Include token in URL so borrower can access portal
        if token:
            portal_url = f"https://{self.purl_domain}/portal/{workspace_slug}?token={token}"
        else:
            portal_url = f"https://{self.purl_domain}/portal/{workspace_slug}"

        context = {
            "first_name": first_name,
            "portal_url": portal_url,
            "loan_officer_name": loan_officer_name or "Your Loan Officer",
            "loan_officer_email": loan_officer_email or "support@perennia.ai",
            "loan_officer_phone": loan_officer_phone or ""
        }

        html_content, text_content = self.render_template("application_submitted", context)

        return await self.send_email(
            to_email=to_email,
            subject="Application Submitted Successfully!",
            html_content=html_content,
            text_content=text_content,
            reply_to=loan_officer_email
        )

    async def send_document_uploaded_email(
        self,
        to_email: str,
        first_name: str,
        document_name: str,
        document_type: str,
        uploaded_at: str
    ) -> bool:
        """Send confirmation email when document is uploaded."""
        context = {
            "first_name": first_name,
            "document_name": document_name,
            "document_type": document_type,
            "uploaded_at": uploaded_at
        }

        html_content, text_content = self.render_template("document_uploaded", context)

        return await self.send_email(
            to_email=to_email,
            subject="Document Received",
            html_content=html_content,
            text_content=text_content
        )

    async def send_task_assigned_email(
        self,
        to_email: str,
        first_name: str,
        workspace_slug: str,
        task_title: str,
        task_description: str,
        due_date: str,
        priority: str = "medium"
    ) -> bool:
        """Send email when task is assigned to borrower."""
        portal_url = f"https://{self.purl_domain}/portal/{workspace_slug}"

        context = {
            "first_name": first_name,
            "portal_url": portal_url,
            "task_title": task_title,
            "task_description": task_description,
            "due_date": due_date,
            "priority": priority
        }

        html_content, text_content = self.render_template("task_assigned", context)

        return await self.send_email(
            to_email=to_email,
            subject=f"New Task: {task_title}",
            html_content=html_content,
            text_content=text_content
        )

    async def send_milestone_completed_email(
        self,
        to_email: str,
        first_name: str,
        workspace_slug: str,
        milestone_name: str
    ) -> bool:
        """Send email when loan milestone is completed."""
        portal_url = f"https://{self.purl_domain}/portal/{workspace_slug}"

        context = {
            "first_name": first_name,
            "portal_url": portal_url,
            "milestone_name": milestone_name
        }

        # Use application_submitted template as base (or create milestone template)
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: #10b981; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1>Milestone Complete!</h1>
                </div>
                <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
                    <p>Hi {first_name},</p>
                    <p>Great news! You've completed the <strong>{milestone_name}</strong> milestone in your loan process.</p>
                    <p>Check your portal for the next steps:</p>
                    <p style="text-align: center;">
                        <a href="{portal_url}" style="display: inline-block; background: #667eea; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px;">
                            View My Portal
                        </a>
                    </p>
                    <p>Best regards,<br>{self.company_name}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(
            to_email=to_email,
            subject=f"Milestone Complete: {milestone_name}",
            html_content=html_content
        )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

email_service = PURLEmailService()
