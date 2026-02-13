"""
Smart Docs Notification Service

Handles sending email notifications for document collection events:
- New document requests
- Document request reminders
- Document approval/rejection notifications
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from email_service import EmailService
from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority

logger = logging.getLogger(__name__)


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
    ) -> bool:
        """
        Send email notification for a new document request.

        Args:
            request: The document request object
            borrower_email: Email address of the borrower
            borrower_name: Name of the borrower
            loan_officer_name: Name of the loan officer
            portal_url: URL to the borrower portal (optional)

        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Format due date
            due_date_str = ""
            if request.due_date:
                due_date_str = request.due_date.strftime("%B %d, %Y")

            # Get priority styling
            priority_color = self._get_priority_color(request.priority)
            priority_label = request.priority.value if request.priority else "Normal"

            # Build email content
            subject = f"Document Needed: {request.title}"

            html_body = self._build_request_email_html(
                borrower_name=borrower_name,
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

            # Send the email
            success = self.email_service.send_html_email(
                to_email=borrower_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )

            if success:
                logger.info(f"Document request notification sent for request {request.id}")
            else:
                logger.warning("Failed to send document request notification")

            return success

        except Exception as e:
            logger.error(f"Error sending document request notification: {e}")
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
    ) -> str:
        """Build HTML email body for single document request."""
        portal_button = ""
        if portal_url:
            portal_button = f'''
            <div style="text-align: center; margin: 24px 0;">
                <a href="{portal_url}" style="display: inline-block; padding: 14px 28px; background: #2563eb; color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">
                    Upload Document Now
                </a>
            </div>
            '''

        due_date_section = ""
        if due_date:
            due_date_section = f'''
            <p style="margin: 12px 0; color: #6b7280;">
                <strong>Due Date:</strong> {due_date}
            </p>
            '''

        instructions_section = ""
        if instructions:
            instructions_section = f'''
            <div style="background: #f3f4f6; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <p style="margin: 0 0 8px; font-weight: 600; color: #374151;">Instructions:</p>
                <p style="margin: 0; color: #4b5563;">{instructions}</p>
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
                        <h1 style="margin: 0; color: white; font-size: 24px;">Document Request</h1>
                    </div>

                    <!-- Content -->
                    <div style="padding: 24px;">
                        <p style="margin: 0 0 16px; color: #374151;">Hi {borrower_name},</p>

                        <p style="margin: 0 0 20px; color: #4b5563;">
                            We need the following document to continue processing your loan application:
                        </p>

                        <!-- Document Card -->
                        <div style="border: 1px solid #e5e7eb; border-left: 4px solid {priority_color}; border-radius: 8px; padding: 16px; margin: 16px 0;">
                            <h2 style="margin: 0 0 8px; color: #1f2937; font-size: 18px;">{document_title}</h2>
                            <span style="display: inline-block; padding: 4px 12px; background: {priority_color}20; color: {priority_color}; border-radius: 4px; font-size: 12px; font-weight: 600;">
                                {priority} Priority
                            </span>
                            {f'<p style="margin: 12px 0 0; color: #6b7280;">{description}</p>' if description else ''}
                        </div>

                        {due_date_section}
                        {instructions_section}
                        {portal_button}

                        <p style="margin: 24px 0 0; color: #6b7280; font-size: 14px;">
                            If you have any questions, please reply to this email or contact your loan officer.
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
        text = f"""Hi {borrower_name},

We need the following document to continue processing your loan application:

DOCUMENT NEEDED: {document_title}
Priority: {priority}
"""
        if description:
            text += f"\n{description}\n"

        if due_date:
            text += f"\nDue Date: {due_date}\n"

        if instructions:
            text += f"\nInstructions:\n{instructions}\n"

        if portal_url:
            text += f"\nUpload your document here: {portal_url}\n"

        text += f"""
If you have any questions, please reply to this email or contact your loan officer.

Best regards,
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
