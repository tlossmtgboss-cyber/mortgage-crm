"""
Smart Docs Notification Service

Handles sending email + SMS notifications for document collection events:
- New document requests
- Document request reminders
- Document approval/rejection notifications
"""

import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from email_service import EmailService
from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority

logger = logging.getLogger(__name__)

_APP_URL = os.getenv("APP_URL", "https://app.perenniaai.com")


class SmartDocsNotificationService:
    """Service for sending Smart Docs related notifications."""

    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()

    def send_document_request_notification(
        self,
        request: DocumentRequest,
        borrower_email: str,
        borrower_name: str,
        loan_officer_name: str = "Your Loan Officer",
        portal_url: Optional[str] = None,
        borrower_phone: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> bool:
        """
        Send email + SMS notification for a new document request.

        Returns:
            bool: True if at least one notification was sent successfully
        """
        email_sent = False
        sms_sent = False

        first_name = (borrower_name or "").split()[0] if borrower_name else "there"

        if not portal_url and loan_id:
            portal_url = f"{_APP_URL}/portal/documents/{loan_id}"

        try:
            due_date_str = ""
            if request.due_date:
                due_date_str = request.due_date.strftime("%B %d, %Y")

            priority_color = self._get_priority_color(request.priority)
            priority_label = request.priority.value if request.priority else "Normal"

            subject = f"Quick action needed: {request.title}"

            html_body = self._build_request_email_html(
                borrower_name=borrower_name,
                first_name=first_name,
                document_title=request.title,
                description=request.description,
                instructions=request.instructions,
                due_date=due_date_str,
                priority=priority_label,
                priority_color=priority_color,
                loan_officer_name=loan_officer_name,
                portal_url=portal_url,
            )

            plain_text = self._build_request_email_plain_text(
                borrower_name=borrower_name,
                document_title=request.title,
                description=request.description,
                instructions=request.instructions,
                due_date=due_date_str,
                priority=priority_label,
                loan_officer_name=loan_officer_name,
                portal_url=portal_url,
            )

            email_sent = self.email_service.send_html_email(
                to_email=borrower_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )

            if email_sent:
                logger.info("Document request email sent for request %s", request.id)
            else:
                logger.warning("Failed to send document request email for request %s", request.id)

        except Exception as e:
            logger.error("Error sending document request email: %s", e)

        if borrower_phone:
            sms_sent = self._send_sms_notification(
                phone=borrower_phone,
                first_name=first_name,
                document_title=request.title,
                loan_officer_name=loan_officer_name,
                portal_url=portal_url,
                loan_id=loan_id,
            )

        return email_sent or sms_sent

    def _send_sms_notification(
        self,
        phone: str,
        first_name: str,
        document_title: str,
        loan_officer_name: str,
        portal_url: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> bool:
        """Send an SMS notification for a document request."""
        try:
            from telephony.sms import send_sms

            link = portal_url or f"{_APP_URL}/portal/documents/{loan_id}" if loan_id else ""
            lo_first = loan_officer_name.split()[0] if loan_officer_name and loan_officer_name != "Your Loan Officer" else ""

            msg = (
                f"Hey {first_name}! "
                f"Your loan is moving along nicely — we just need one thing from you: "
                f"{document_title}. "
            )
            if lo_first:
                msg += f"{lo_first} is waiting on this to keep things on track. "
            if link:
                msg += f"Upload it here in seconds: {link}"

            result = send_sms(to=phone, text=msg)

            if result.get("status") == "sent":
                logger.info("Document request SMS sent to ...%s", phone[-4:])
                return True
            else:
                logger.warning("SMS blocked or failed: %s", result.get("reason", "unknown"))
                return False

        except Exception as e:
            logger.error("Error sending document request SMS: %s", e)
            return False

    def send_bulk_request_notification(
        self,
        requests: List[DocumentRequest],
        borrower_email: str,
        borrower_name: str,
        loan_officer_name: str = "Your Loan Officer",
        portal_url: Optional[str] = None,
    ) -> bool:
        """
        Send email notification for multiple new document requests (e.g., initial needs list).

        Args:
            requests: List of document request objects
            borrower_email: Email address of the borrower
            borrower_name: Name of the borrower
            loan_officer_name: Name of the loan officer
            portal_url: URL to the borrower portal

        Returns:
            bool: True if email was sent successfully
        """
        try:
            if not requests:
                return True

            # Group requests by priority
            critical = [r for r in requests if r.priority == RequestPriority.CRITICAL]
            high = [r for r in requests if r.priority == RequestPriority.HIGH]
            normal = [r for r in requests if r.priority == RequestPriority.NORMAL]
            low = [r for r in requests if r.priority == RequestPriority.LOW]

            subject = f"Documents Needed for Your Loan Application ({len(requests)} items)"

            html_body = self._build_bulk_request_email_html(
                borrower_name=borrower_name,
                critical_requests=critical,
                high_requests=high,
                normal_requests=normal,
                low_requests=low,
                loan_officer_name=loan_officer_name,
                portal_url=portal_url,
            )

            plain_text = self._build_bulk_request_email_plain_text(
                borrower_name=borrower_name,
                requests=requests,
                loan_officer_name=loan_officer_name,
                portal_url=portal_url,
            )

            success = self.email_service.send_html_email(
                to_email=borrower_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )

            if success:
                logger.info(f"Bulk document request notification sent ({len(requests)} requests)")

            return success

        except Exception as e:
            logger.error(f"Error sending bulk document request notification: {e}")
            return False

    def _get_priority_color(self, priority: Optional[RequestPriority]) -> str:
        """Get color code for priority level."""
        if not priority:
            return "#3b82f6"  # Blue for normal

        colors = {
            RequestPriority.CRITICAL: "#dc2626",  # Red
            RequestPriority.HIGH: "#f97316",      # Orange
            RequestPriority.NORMAL: "#3b82f6",    # Blue
            RequestPriority.LOW: "#10b981",       # Green
        }
        return colors.get(priority, "#3b82f6")

    def _build_request_email_html(
        self,
        borrower_name: str,
        document_title: str,
        description: Optional[str],
        instructions: Optional[str],
        due_date: str,
        priority: str,
        priority_color: str,
        loan_officer_name: str,
        portal_url: Optional[str],
        first_name: str = "",
    ) -> str:
        """Build HTML email body for single document request — warm, friendly tone."""
        first = first_name or (borrower_name or "").split()[0] or "there"

        portal_button = ""
        if portal_url:
            portal_button = f'''
            <div style="text-align: center; margin: 28px 0;">
                <a href="{portal_url}" style="display: inline-block; padding: 16px 36px; background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; text-decoration: none; border-radius: 30px; font-weight: 700; font-size: 16px; letter-spacing: 0.3px; box-shadow: 0 4px 14px rgba(37,99,235,0.3);">
                    Upload Now — Takes 30 Seconds
                </a>
            </div>
            '''

        due_date_section = ""
        if due_date:
            due_date_section = f'''
            <p style="margin: 12px 0; color: #6b7280; font-size: 14px;">
                <strong>Ideally by:</strong> {due_date}
            </p>
            '''

        instructions_section = ""
        if instructions:
            instructions_section = f'''
            <div style="background: #fef9ec; padding: 16px; border-radius: 10px; margin: 16px 0; border-left: 4px solid #f59e0b;">
                <p style="margin: 0 0 6px; font-weight: 600; color: #92400e; font-size: 13px;">QUICK TIP</p>
                <p style="margin: 0; color: #78350f; line-height: 1.5;">{instructions}</p>
            </div>
            '''

        lo_first = loan_officer_name.split()[0] if loan_officer_name and loan_officer_name != "Your Loan Officer" else ""
        sign_off = f"{lo_first}, your loan officer" if lo_first else loan_officer_name

        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f4ff;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
                <div style="background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); padding: 32px 24px; text-align: center;">
                        <p style="margin: 0 0 6px; color: rgba(255,255,255,0.85); font-size: 14px;">Your loan is moving forward!</p>
                        <h1 style="margin: 0; color: white; font-size: 26px; font-weight: 700;">Just one thing we need</h1>
                    </div>

                    <!-- Content -->
                    <div style="padding: 28px 24px;">
                        <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">
                            Hey {first}! Great news — your application is coming along.
                            We just need one document to keep everything on schedule:
                        </p>

                        <!-- Document Card -->
                        <div style="border: 2px solid {priority_color}30; border-left: 5px solid {priority_color}; border-radius: 12px; padding: 20px; margin: 20px 0; background: {priority_color}08;">
                            <h2 style="margin: 0 0 10px; color: #1f2937; font-size: 20px;">{document_title}</h2>
                            {f'<p style="margin: 0; color: #6b7280; line-height: 1.5;">{description}</p>' if description else ''}
                        </div>

                        {due_date_section}
                        {instructions_section}
                        {portal_button}

                        <p style="margin: 24px 0 0; color: #6b7280; font-size: 14px; line-height: 1.6;">
                            You can snap a photo with your phone or upload from your computer — it only takes a moment.
                            Questions? Just reply to this email and I'll get right back to you.
                        </p>

                        <p style="margin: 20px 0 0; color: #374151; font-size: 15px;">
                            Talk soon,<br>
                            <strong>{sign_off}</strong>
                        </p>
                    </div>

                    <!-- Footer -->
                    <div style="background: #f9fafb; padding: 16px 24px; text-align: center; border-top: 1px solid #e5e7eb;">
                        <p style="margin: 0; color: #9ca3af; font-size: 11px;">
                            Sent with care by your team at Perennia AI
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        '''

    def _build_request_email_plain_text(
        self,
        borrower_name: str,
        document_title: str,
        description: Optional[str],
        instructions: Optional[str],
        due_date: str,
        priority: str,
        loan_officer_name: str,
        portal_url: Optional[str],
    ) -> str:
        """Build plain text email body for single document request."""
        first = (borrower_name or "").split()[0] or "there"
        text = f"""Hey {first}!

Great news — your application is coming along. We just need one document to keep everything on schedule:

DOCUMENT NEEDED: {document_title}
"""
        if description:
            text += f"\n{description}\n"

        if due_date:
            text += f"\nIdeally by: {due_date}\n"

        if instructions:
            text += f"\nQuick tip:\n{instructions}\n"

        if portal_url:
            text += f"\nUpload it here (takes 30 seconds): {portal_url}\n"

        text += f"""
You can snap a photo with your phone or upload from your computer.
Questions? Just reply to this email and I'll get right back to you.

Talk soon,
{loan_officer_name}
"""
        return text

    def _build_bulk_request_email_html(
        self,
        borrower_name: str,
        critical_requests: List[DocumentRequest],
        high_requests: List[DocumentRequest],
        normal_requests: List[DocumentRequest],
        low_requests: List[DocumentRequest],
        loan_officer_name: str,
        portal_url: Optional[str],
    ) -> str:
        """Build HTML email body for bulk document requests."""

        def render_request_list(requests: List[DocumentRequest], priority_label: str, color: str) -> str:
            if not requests:
                return ""
            items = "".join([
                f'<li style="margin: 8px 0; color: #374151;">{r.title}</li>'
                for r in requests
            ])
            return f'''
            <div style="margin: 16px 0;">
                <h3 style="margin: 0 0 8px; color: {color}; font-size: 14px; text-transform: uppercase;">
                    {priority_label} ({len(requests)})
                </h3>
                <ul style="margin: 0; padding-left: 20px;">{items}</ul>
            </div>
            '''

        sections = (
            render_request_list(critical_requests, "Critical Priority", "#dc2626") +
            render_request_list(high_requests, "High Priority", "#f97316") +
            render_request_list(normal_requests, "Normal Priority", "#3b82f6") +
            render_request_list(low_requests, "Low Priority", "#10b981")
        )

        total = len(critical_requests) + len(high_requests) + len(normal_requests) + len(low_requests)

        portal_button = ""
        if portal_url:
            portal_button = f'''
            <div style="text-align: center; margin: 24px 0;">
                <a href="{portal_url}" style="display: inline-block; padding: 14px 28px; background: #2563eb; color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">
                    View & Upload Documents
                </a>
            </div>
            '''

        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f9fafb;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
                <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <div style="background: #1e3a5f; padding: 24px; text-align: center;">
                        <h1 style="margin: 0; color: white; font-size: 24px;">Documents Needed</h1>
                        <p style="margin: 8px 0 0; color: rgba(255,255,255,0.8);">{total} documents required</p>
                    </div>

                    <!-- Content -->
                    <div style="padding: 24px;">
                        <p style="margin: 0 0 16px; color: #374151;">Hi {borrower_name},</p>

                        <p style="margin: 0 0 20px; color: #4b5563;">
                            To continue processing your loan application, we need the following documents.
                            Please upload them at your earliest convenience.
                        </p>

                        {sections}

                        {portal_button}

                        <p style="margin: 24px 0 0; color: #6b7280; font-size: 14px;">
                            If you have any questions about these documents, please reply to this email
                            or contact your loan officer.
                        </p>

                        <p style="margin: 16px 0 0; color: #374151;">
                            Best regards,<br>
                            <strong>{loan_officer_name}</strong>
                        </p>
                    </div>

                    <!-- Footer -->
                    <div style="background: #f9fafb; padding: 16px 24px; text-align: center; border-top: 1px solid #e5e7eb;">
                        <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                            This is an automated message from your loan processing team.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        '''

    def _build_bulk_request_email_plain_text(
        self,
        borrower_name: str,
        requests: List[DocumentRequest],
        loan_officer_name: str,
        portal_url: Optional[str],
    ) -> str:
        """Build plain text email body for bulk document requests."""
        text = f"""Hi {borrower_name},

To continue processing your loan application, we need the following documents:

"""
        for i, req in enumerate(requests, 1):
            priority = req.priority.value if req.priority else "Normal"
            text += f"{i}. {req.title} ({priority} Priority)\n"

        if portal_url:
            text += f"\nView and upload documents here: {portal_url}\n"

        text += f"""
If you have any questions, please reply to this email or contact your loan officer.

Best regards,
{loan_officer_name}
"""
        return text


# Convenience function for quick notifications
def send_document_request_email(
    db: Session,
    request: DocumentRequest,
    borrower_email: str,
    borrower_name: str,
    loan_officer_name: str = "Your Loan Officer",
    portal_url: Optional[str] = None,
) -> bool:
    """Quick helper to send a document request notification."""
    service = SmartDocsNotificationService(db)
    return service.send_document_request_notification(
        request=request,
        borrower_email=borrower_email,
        borrower_name=borrower_name,
        loan_officer_name=loan_officer_name,
        portal_url=portal_url,
    )
