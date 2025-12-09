"""
Notification Service - Email and SMS notifications for borrower applications.

Uses SendGrid for email and Twilio for SMS.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType
from twilio.rest import Client as TwilioClient
import base64

logger = logging.getLogger(__name__)

# SendGrid configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "noreply@perennia.ai")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "Perennia Mortgage")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# Application URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


class NotificationService:
    """Service for sending email and SMS notifications."""

    def __init__(self):
        self.sendgrid_client = None
        self.twilio_client = None

        if SENDGRID_API_KEY:
            self.sendgrid_client = SendGridAPIClient(SENDGRID_API_KEY)
            logger.info("SendGrid client initialized")
        else:
            logger.warning("SendGrid API key not configured - emails will be logged only")

        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            self.twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            logger.info("Twilio client initialized")
        else:
            logger.warning("Twilio credentials not configured - SMS will be logged only")

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
                logger.info(f"[DRY RUN] Would send email to {to_email}: {subject}")
                return {"success": True, "dry_run": True}

            response = self.sendgrid_client.send(message)

            logger.info(f"Email sent to {to_email}: {subject} (status: {response.status_code})")

            return {
                "success": response.status_code in [200, 201, 202],
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id"),
            }

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return {"success": False, "error": str(e)}

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
    ) -> Dict[str, Any]:
        """Send appointment confirmation to borrower."""

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

        return self.send_email(
            to_email=borrower_email,
            subject=subject,
            html_content=html_content,
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

    # =========================================================================
    # SMS METHODS
    # =========================================================================

    def send_sms(
        self,
        to_phone: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Send an SMS via Twilio.

        Args:
            to_phone: Recipient phone number (E.164 format preferred)
            message: SMS message content (max 1600 chars)

        Returns:
            Dict with 'success' boolean and 'message_sid' or 'error'
        """
        try:
            # Format phone number if needed
            if not to_phone.startswith('+'):
                # Assume US number
                to_phone = '+1' + to_phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

            if not self.twilio_client:
                logger.info(f"[DRY RUN] Would send SMS to {to_phone}: {message[:50]}...")
                return {"success": True, "dry_run": True}

            sms = self.twilio_client.messages.create(
                body=message,
                from_=TWILIO_FROM_NUMBER,
                to=to_phone,
            )

            logger.info(f"SMS sent to {to_phone}: {sms.sid}")

            return {
                "success": True,
                "message_sid": sms.sid,
                "status": sms.status,
            }

        except Exception as e:
            logger.error(f"Failed to send SMS to {to_phone}: {str(e)}")
            return {"success": False, "error": str(e)}

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


# Create singleton instance
notification_service = NotificationService()
