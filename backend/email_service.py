"""
Email Service for sending reports and notifications
Supports SendGrid (primary) with SMTP fallback
"""

import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
    import base64
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid not installed. Install with: pip install sendgrid")

# SMTP fallback imports
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


class EmailService:
    """Service for sending emails via SendGrid (primary) or SMTP (fallback)"""

    def __init__(self):
        # SendGrid configuration
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY', '')
        self.use_sendgrid = bool(self.sendgrid_api_key) and SENDGRID_AVAILABLE

        # SMTP fallback configuration
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')

        # Common configuration
        self.from_email = os.getenv('FROM_EMAIL', 'sarah@reply.perenniaai.com')
        self.from_name = os.getenv('FROM_NAME', 'Sarah from Perennia AI')

        if self.use_sendgrid:
            logger.info("Email service initialized with SendGrid")
        elif self.smtp_user:
            logger.info("Email service initialized with SMTP fallback")
        else:
            logger.warning("No email credentials configured (SENDGRID_API_KEY or SMTP_USER)")

    def send_html_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        reply_to: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        """Send an HTML email with optional attachments and custom headers

        Args:
            from_email: Override the default from_email address. Useful for AI conversations
                       where replies need to go to a specific inbound parse address.
        """
        if self.use_sendgrid:
            return self._send_via_sendgrid(to_email, subject, html_body, plain_text_body, attachments, headers, reply_to, from_email)
        else:
            return self._send_via_smtp(to_email, subject, html_body, plain_text_body, attachments, headers, reply_to, from_email)

    def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        reply_to: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        """Send email via SendGrid API"""
        try:
            from sendgrid.helpers.mail import ReplyTo, Header

            # Use provided from_email or fall back to default
            sender_email = from_email or self.from_email

            message = Mail(
                from_email=(sender_email, self.from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_body
            )

            if plain_text_body:
                message.plain_text_content = plain_text_body

            # Add reply-to address if specified
            if reply_to:
                message.reply_to = ReplyTo(reply_to)

            # Add custom headers (only supported ones - SendGrid doesn't support arbitrary X- headers)
            # Supported: Message-ID, In-Reply-To, References, List-Unsubscribe
            if headers:
                supported_headers = ['Message-ID', 'In-Reply-To', 'References', 'List-Unsubscribe']
                for key, value in headers.items():
                    if key in supported_headers:
                        message.add_header(Header(key, value))
                    else:
                        # Log skipped headers but don't fail
                        logger.debug(f"Skipping unsupported SendGrid header: {key}")

            # Add attachments if any
            if attachments:
                for att in attachments:
                    encoded_content = base64.b64encode(att['content']).decode() if isinstance(att['content'], bytes) else att['content']
                    attachment = Attachment(
                        FileContent(encoded_content),
                        FileName(att['filename']),
                        FileType(att.get('type', 'application/octet-stream')),
                        Disposition('attachment')
                    )
                    message.add_attachment(attachment)

            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)

            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully via SendGrid (status: {response.status_code})")
                return True
            else:
                logger.error(f"SendGrid returned status {response.status_code}: {response.body}")
                return False

        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {type(e).__name__}")
            # Try SMTP fallback if SendGrid fails
            if self.smtp_user:
                logger.info("Attempting SMTP fallback...")
                return self._send_via_smtp(to_email, subject, html_body, plain_text_body, attachments, headers, reply_to, from_email)
            return False

    def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        reply_to: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        """Send email via SMTP (fallback method)"""
        if not self.smtp_user or not self.smtp_password:
            logger.error("SMTP credentials not configured")
            return False

        try:
            # Use provided from_email or fall back to default
            sender_email = from_email or self.from_email

            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = f'{self.from_name} <{sender_email}>'
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')

            # Add reply-to header if specified
            if reply_to:
                msg['Reply-To'] = reply_to

            # Add custom headers
            if headers:
                for key, value in headers.items():
                    msg[key] = value

            # Add plain text version if provided
            if plain_text_body:
                part1 = MIMEText(plain_text_body, 'plain')
                msg.attach(part1)

            # Add HTML version
            part2 = MIMEText(html_body, 'html')
            msg.attach(part2)

            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f"attachment; filename= {attachment['filename']}"
                    )
                    msg.attach(part)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info("Email sent successfully via SMTP")
            return True

        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {type(e).__name__}")
            return False

    def format_daily_priorities_email(
        self,
        user_name: str,
        priorities: List[Dict[str, Any]]
    ) -> str:
        """Format daily priorities data as HTML email"""

        # Separate tasks and loans
        tasks = [p for p in priorities if p['type'] == 'task']
        loans = [p for p in priorities if p['type'] == 'loan']

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .priority-item {{
            background: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .priority-high {{
            border-left-color: #e74c3c;
            background: #ffebee;
        }}
        .priority-medium {{
            border-left-color: #f39c12;
            background: #fff3e0;
        }}
        .urgency-label {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .urgency-overdue {{
            background: #e74c3c;
            color: white;
        }}
        .urgency-due-today {{
            background: #f39c12;
            color: white;
        }}
        .urgency-high {{
            background: #9b59b6;
            color: white;
        }}
        .urgency-pending {{
            background: #95a5a6;
            color: white;
        }}
        .urgency-closing {{
            background: #e74c3c;
            color: white;
        }}
        .urgency-active {{
            background: #3498db;
            color: white;
        }}
        .item-title {{
            font-size: 18px;
            font-weight: 600;
            margin: 5px 0;
        }}
        .item-details {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        .summary {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <h1>📋 Daily Priorities Report</h1>
    <p>Hello {user_name},</p>
    <p>Here's your prioritized action list for today:</p>

    <div class="summary">
        <strong>Summary:</strong>
        <ul>
            <li><strong>{len(tasks)}</strong> pending tasks</li>
            <li><strong>{len(loans)}</strong> loans requiring attention</li>
            <li><strong>{len(priorities)}</strong> total action items</li>
        </ul>
    </div>
"""

        # Add tasks section
        if tasks:
            html += "<h2>📌 Your Tasks</h2>"
            for i, task in enumerate(tasks[:20], 1):
                priority_class = 'priority-high' if task['priority_score'] >= 90 else 'priority-medium' if task['priority_score'] >= 70 else 'priority-item'
                urgency_class = 'urgency-overdue' if task['urgency_label'] == 'Overdue' else \
                                'urgency-due-today' if task['urgency_label'] == 'Due Today' else \
                                'urgency-high' if task['urgency_label'] == 'High Priority' else 'urgency-pending'

                html += f"""
    <div class="{priority_class}">
        <span class="urgency-label {urgency_class}">{task['urgency_label']}</span>
        <div class="item-title">{i}. {task['title']}</div>
        <div class="item-details">
            Priority Score: {task['priority_score']}
            {f" | Due: {task['due_date'][:10] if task['due_date'] else 'No date'}" if task.get('due_date') else ''}
        </div>
    </div>
"""

        # Add loans section
        if loans:
            html += "<h2>💼 Loans Requiring Attention</h2>"
            for i, loan in enumerate(loans[:20], 1):
                priority_class = 'priority-high' if loan['priority_score'] >= 90 else 'priority-medium' if loan['priority_score'] >= 70 else 'priority-item'
                urgency_class = 'urgency-closing' if 'Closing' in loan['urgency_label'] else \
                                'urgency-high' if 'Risk' in loan['urgency_label'] else 'urgency-active'

                html += f"""
    <div class="{priority_class}">
        <span class="urgency-label {urgency_class}">{loan['urgency_label']}</span>
        <div class="item-title">{i}. {loan['title']}</div>
        <div class="item-details">
            Value: ${loan['value']:,.0f} | Priority Score: {loan['priority_score']}
            {f" | Closing: {loan['due_date'][:10]}" if loan.get('due_date') else ''}
        </div>
    </div>
"""

        html += """
    <div class="footer">
        <p>This report was automatically generated by Perennia AI CRM</p>
        <p>Generated on """ + datetime.now().strftime('%B %d, %Y at %I:%M %p') + """</p>
    </div>
</body>
</html>
"""
        return html

    def send_daily_priorities_report(
        self,
        to_email: str,
        user_name: str,
        priorities: List[Dict[str, Any]]
    ) -> bool:
        """Send daily priorities report via email"""
        subject = f"📋 Your Daily Priorities - {datetime.now().strftime('%B %d, %Y')}"
        html_body = self.format_daily_priorities_email(user_name, priorities)

        # Create plain text version
        plain_text = f"""
Daily Priorities Report - {datetime.now().strftime('%B %d, %Y')}

Hello {user_name},

Here's your prioritized action list for today:

SUMMARY:
- {len([p for p in priorities if p['type'] == 'task'])} pending tasks
- {len([p for p in priorities if p['type'] == 'loan'])} loans requiring attention
- {len(priorities)} total action items

"""

        # Add tasks
        tasks = [p for p in priorities if p['type'] == 'task']
        if tasks:
            plain_text += "YOUR TASKS:\n\n"
            for i, task in enumerate(tasks[:20], 1):
                plain_text += f"{i}. [{task['urgency_label']}] {task['title']}\n"
                plain_text += f"   Priority: {task['priority_score']}"
                if task.get('due_date'):
                    plain_text += f" | Due: {task['due_date'][:10]}"
                plain_text += "\n\n"

        # Add loans
        loans = [p for p in priorities if p['type'] == 'loan']
        if loans:
            plain_text += "LOANS REQUIRING ATTENTION:\n\n"
            for i, loan in enumerate(loans[:20], 1):
                plain_text += f"{i}. [{loan['urgency_label']}] {loan['title']}\n"
                plain_text += f"   Value: ${loan['value']:,.0f} | Priority: {loan['priority_score']}"
                if loan.get('due_date'):
                    plain_text += f" | Closing: {loan['due_date'][:10]}"
                plain_text += "\n\n"

        plain_text += f"\nGenerated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n"
        plain_text += "This report was automatically generated by Perennia AI CRM\n"

        return self.send_html_email(to_email, subject, html_body, plain_text)


    def format_activation_email(
        self,
        user_name: str,
        activation_url: str,
        expires_days: int = 7
    ) -> str:
        """Format user activation email as HTML"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo h1 {{
            color: #3b82f6;
            font-size: 28px;
            margin: 0;
        }}
        h2 {{
            color: #1a1a2e;
            margin-top: 0;
        }}
        p {{
            color: #4b5563;
            font-size: 16px;
        }}
        .btn-activate {{
            display: inline-block;
            background: #3b82f6;
            color: white !important;
            padding: 14px 32px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            margin: 24px 0;
        }}
        .btn-activate:hover {{
            background: #2563eb;
        }}
        .info-box {{
            background: #f0f9ff;
            border-left: 4px solid #3b82f6;
            padding: 16px;
            margin: 24px 0;
            border-radius: 4px;
        }}
        .info-box h4 {{
            margin: 0 0 8px 0;
            color: #1e40af;
        }}
        .info-box ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .info-box li {{
            margin: 8px 0;
            color: #4b5563;
        }}
        .expires {{
            font-size: 14px;
            color: #6b7280;
            background: #fef3c7;
            padding: 12px 16px;
            border-radius: 8px;
            text-align: center;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 13px;
        }}
        .footer a {{
            color: #3b82f6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>Perennia AI</h1>
        </div>

        <h2>Welcome to the Team, {user_name}!</h2>

        <p>Your Perennia AI account has been created. Click the button below to set your password and activate your account.</p>

        <div style="text-align: center;">
            <a href="{activation_url}" class="btn-activate">Activate Your Account</a>
        </div>

        <div class="info-box">
            <h4>What's Next?</h4>
            <ul>
                <li>Set your secure password</li>
                <li>Review your assigned responsibilities</li>
                <li>Access your personalized KPI scorecard</li>
                <li>Start managing your pipeline</li>
            </ul>
        </div>

        <div class="expires">
            ⏰ This activation link expires in <strong>{expires_days} days</strong>
        </div>

        <div class="footer">
            <p>If you didn't expect this email, please ignore it or contact your administrator.</p>
            <p>This email was sent by Perennia AI CRM</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def send_activation_email(
        self,
        to_email: str,
        user_name: str,
        activation_token: str,
        base_url: str = None
    ) -> bool:
        """Send user activation email"""
        if not base_url:
            base_url = os.getenv('FRONTEND_URL', 'https://perenniaai.com')

        activation_url = f"{base_url}/activate?token={activation_token}"
        subject = "🔐 Activate Your Perennia AI Account"
        html_body = self.format_activation_email(user_name, activation_url)

        plain_text = f"""
Welcome to Perennia AI, {user_name}!

Your account has been created. To activate your account and set your password, visit:

{activation_url}

This link will expire in 7 days.

What's Next?
- Set your secure password
- Review your assigned responsibilities
- Access your personalized KPI scorecard
- Start managing your pipeline

If you didn't expect this email, please ignore it or contact your administrator.

This email was sent by Perennia AI CRM
"""

        return self.send_html_email(to_email, subject, html_body, plain_text)


    def format_meeting_invite_email(
        self,
        participant_name: str,
        host_name: str,
        meeting_name: str,
        join_url: str,
        scheduled_time: Optional[datetime] = None
    ) -> str:
        """Format meeting invite email as HTML"""
        time_str = scheduled_time.strftime('%B %d, %Y at %I:%M %p') if scheduled_time else "Now"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo h1 {{
            color: #3b82f6;
            font-size: 28px;
            margin: 0;
        }}
        h2 {{
            color: #1a1a2e;
            margin-top: 0;
        }}
        p {{
            color: #4b5563;
            font-size: 16px;
        }}
        .meeting-card {{
            background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin: 24px 0;
            text-align: center;
        }}
        .meeting-card h3 {{
            margin: 0 0 8px 0;
            font-size: 22px;
        }}
        .meeting-card .host {{
            opacity: 0.9;
            font-size: 14px;
            margin-bottom: 16px;
        }}
        .meeting-card .time {{
            font-size: 16px;
            background: rgba(255,255,255,0.2);
            padding: 8px 16px;
            border-radius: 6px;
            display: inline-block;
        }}
        .btn-join {{
            display: inline-block;
            background: #10b981;
            color: white !important;
            padding: 16px 48px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 18px;
            margin: 24px 0;
        }}
        .btn-join:hover {{
            background: #059669;
        }}
        .info-box {{
            background: #f0f9ff;
            border-left: 4px solid #3b82f6;
            padding: 16px;
            margin: 24px 0;
            border-radius: 4px;
        }}
        .info-box h4 {{
            margin: 0 0 8px 0;
            color: #1e40af;
        }}
        .info-box ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .info-box li {{
            margin: 8px 0;
            color: #4b5563;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>📹 Video Meeting Invite</h1>
        </div>

        <h2>Hi {participant_name},</h2>

        <p>You've been invited to join a video meeting!</p>

        <div class="meeting-card">
            <h3>{meeting_name}</h3>
            <p class="host">Hosted by {host_name}</p>
            <div class="time">🕐 {time_str}</div>
        </div>

        <div style="text-align: center;">
            <a href="{join_url}" class="btn-join">Join Meeting</a>
        </div>

        <div class="info-box">
            <h4>Before You Join</h4>
            <ul>
                <li>Make sure your camera and microphone are working</li>
                <li>Find a quiet, well-lit space</li>
                <li>Use a stable internet connection</li>
                <li>Click the button above when you're ready to join</li>
            </ul>
        </div>

        <p style="text-align: center; color: #6b7280; font-size: 14px;">
            Or copy this link:<br>
            <a href="{join_url}" style="color: #3b82f6;">{join_url}</a>
        </p>

        <div class="footer">
            <p>This meeting invite was sent via Perennia AI CRM</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def send_meeting_invite(
        self,
        to_email: str,
        participant_name: str,
        host_name: str,
        meeting_name: str,
        join_url: str,
        scheduled_time: Optional[datetime] = None
    ) -> bool:
        """Send meeting invite email"""
        time_str = scheduled_time.strftime('%B %d, %Y at %I:%M %p') if scheduled_time else "Now"
        subject = f"📹 Video Meeting: {meeting_name}"
        html_body = self.format_meeting_invite_email(
            participant_name, host_name, meeting_name, join_url, scheduled_time
        )

        plain_text = f"""
Hi {participant_name},

You've been invited to join a video meeting!

MEETING: {meeting_name}
HOST: {host_name}
TIME: {time_str}

Click here to join:
{join_url}

Before you join:
- Make sure your camera and microphone are working
- Find a quiet, well-lit space
- Use a stable internet connection

This meeting invite was sent via Perennia AI CRM
"""

        return self.send_html_email(to_email, subject, html_body, plain_text)

    def format_new_lead_notification(
        self,
        lo_name: str,
        lead_name: str,
        lead_email: str,
        lead_phone: Optional[str],
        loan_type: str,
        source: str,
        message: Optional[str] = None,
        lead_id: Optional[int] = None
    ) -> str:
        """Format new lead notification email as HTML"""
        phone_html = f"<strong>Phone:</strong> <a href='tel:{lead_phone}'>{lead_phone}</a>" if lead_phone else "<strong>Phone:</strong> Not provided"
        message_html = f"""
            <div style="margin-top: 16px; padding: 16px; background: #f9fafb; border-radius: 8px; border-left: 4px solid #c9a227;">
                <strong>Message from lead:</strong>
                <p style="margin: 8px 0 0 0; color: #4b5563; font-style: italic;">"{message}"</p>
            </div>
        """ if message else ""

        crm_link = os.getenv('FRONTEND_URL', 'https://perenniaai.com')
        lead_link = f"{crm_link}/leads/{lead_id}" if lead_id else crm_link

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
            padding-bottom: 24px;
            border-bottom: 1px solid #e5e7eb;
        }}
        .header h1 {{
            color: #c9a227;
            font-size: 24px;
            margin: 0;
        }}
        .alert-badge {{
            display: inline-block;
            background: #fef3c7;
            color: #92400e;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        h2 {{
            color: #1a1a2e;
            margin: 0 0 16px 0;
            font-size: 20px;
        }}
        .lead-card {{
            background: #f0f9ff;
            border: 1px solid #bae6fd;
            border-radius: 12px;
            padding: 20px;
            margin: 20px 0;
        }}
        .lead-card p {{
            margin: 8px 0;
            color: #374151;
        }}
        .lead-card a {{
            color: #2563eb;
        }}
        .loan-type {{
            display: inline-block;
            background: #2563eb;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            text-transform: capitalize;
        }}
        .btn-primary {{
            display: inline-block;
            background: #c9a227;
            color: white !important;
            padding: 14px 28px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            margin: 16px 0;
        }}
        .btn-primary:hover {{
            background: #a68820;
        }}
        .tips {{
            background: #f9fafb;
            border-radius: 8px;
            padding: 16px;
            margin-top: 20px;
        }}
        .tips h4 {{
            margin: 0 0 12px 0;
            color: #374151;
            font-size: 14px;
        }}
        .tips ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .tips li {{
            margin: 6px 0;
            color: #6b7280;
            font-size: 13px;
        }}
        .footer {{
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="alert-badge">New Lead Alert</span>
            <h1>You Have a New Lead!</h1>
        </div>

        <p>Hi {lo_name},</p>
        <p>Great news! Someone just submitted a lead form on your microsite.</p>

        <div class="lead-card">
            <h2>{lead_name}</h2>
            <p><strong>Email:</strong> <a href="mailto:{lead_email}">{lead_email}</a></p>
            <p>{phone_html}</p>
            <p><strong>Loan Type:</strong> <span class="loan-type">{loan_type.replace('_', ' ')}</span></p>
            <p><strong>Source:</strong> {source}</p>
        </div>

        {message_html}

        <div style="text-align: center;">
            <a href="{lead_link}" class="btn-primary">View Lead in CRM</a>
        </div>

        <div class="tips">
            <h4>Quick Tips for Following Up:</h4>
            <ul>
                <li>Respond within the first 5 minutes for best results</li>
                <li>Call first, then follow up with an email</li>
                <li>Reference their specific loan type in your outreach</li>
                <li>Prepare rate quotes before your call</li>
            </ul>
        </div>

        <div class="footer">
            <p>This notification was sent by Perennia AI CRM</p>
            <p>Lead captured at {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def send_new_lead_notification(
        self,
        to_email: str,
        lo_name: str,
        lead_name: str,
        lead_email: str,
        lead_phone: Optional[str] = None,
        loan_type: str = "purchase",
        source: str = "microsite",
        message: Optional[str] = None,
        lead_id: Optional[int] = None
    ) -> bool:
        """Send new lead notification email to loan officer"""
        subject = f"New Lead Alert: {lead_name} - {loan_type.replace('_', ' ').title()}"
        html_body = self.format_new_lead_notification(
            lo_name, lead_name, lead_email, lead_phone, loan_type, source, message, lead_id
        )

        plain_text = f"""
New Lead Alert!

Hi {lo_name},

Great news! Someone just submitted a lead form on your microsite.

LEAD DETAILS:
- Name: {lead_name}
- Email: {lead_email}
- Phone: {lead_phone or 'Not provided'}
- Loan Type: {loan_type.replace('_', ' ').title()}
- Source: {source}
{f'- Message: "{message}"' if message else ''}

Log in to your CRM to view and follow up with this lead.

Quick Tips:
- Respond within the first 5 minutes for best results
- Call first, then follow up with an email
- Reference their specific loan type in your outreach

This notification was sent by Perennia AI CRM
"""

        return self.send_html_email(to_email, subject, html_body, plain_text)

    def format_subscription_invite_email(
        self,
        company_name: str,
        contact_name: Optional[str],
        plan: str,
        seats: int,
        signup_url: str,
        personal_message: Optional[str] = None,
        expires_days: int = 7
    ) -> str:
        """Format subscription invitation email as HTML"""
        greeting = f"Hi {contact_name}" if contact_name else "Hello"

        plan_features = {
            'starter': ['Up to 3 users', 'Basic CRM features', 'Email support'],
            'professional': ['Up to 25 users', 'Full CRM suite', 'AI-powered automation', 'Priority support'],
            'enterprise': ['Unlimited users', 'Custom integrations', 'Dedicated success manager', 'SLA guarantee'],
            'custom': ['Tailored to your needs', 'Volume pricing', 'Custom features', 'White-glove onboarding']
        }

        features = plan_features.get(plan, plan_features['professional'])
        features_html = ''.join([f'<li>{f}</li>' for f in features])

        personal_msg_html = f'''
            <div style="margin: 24px 0; padding: 20px; background: #f0f9ff; border-left: 4px solid #3b82f6; border-radius: 4px;">
                <p style="margin: 0; color: #1e40af; font-style: italic;">"{personal_message}"</p>
            </div>
        ''' if personal_message else ''

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo h1 {{
            color: #3b82f6;
            font-size: 28px;
            margin: 0;
        }}
        h2 {{
            color: #1a1a2e;
            margin-top: 0;
        }}
        p {{
            color: #4b5563;
            font-size: 16px;
        }}
        .plan-card {{
            background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin: 24px 0;
            text-align: center;
        }}
        .plan-card h3 {{
            margin: 0 0 8px 0;
            font-size: 24px;
            text-transform: capitalize;
        }}
        .plan-card .seats {{
            font-size: 16px;
            opacity: 0.9;
        }}
        .btn-signup {{
            display: inline-block;
            background: #10b981;
            color: white !important;
            padding: 16px 48px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 18px;
            margin: 24px 0;
        }}
        .btn-signup:hover {{
            background: #059669;
        }}
        .features {{
            background: #f9fafb;
            border-radius: 8px;
            padding: 20px;
            margin: 24px 0;
        }}
        .features h4 {{
            margin: 0 0 12px 0;
            color: #374151;
        }}
        .features ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .features li {{
            margin: 8px 0;
            color: #4b5563;
        }}
        .expires {{
            font-size: 14px;
            color: #6b7280;
            background: #fef3c7;
            padding: 12px 16px;
            border-radius: 8px;
            text-align: center;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 13px;
        }}
        .footer a {{
            color: #3b82f6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>Perennia AI</h1>
        </div>

        <h2>You're Invited to Join Perennia AI!</h2>

        <p>{greeting},</p>

        <p>You've been invited to set up <strong>{company_name}</strong> on Perennia AI, the intelligent CRM platform that helps mortgage professionals close more loans with AI-powered automation.</p>

        {personal_msg_html}

        <div class="plan-card">
            <h3>{plan} Plan</h3>
            <div class="seats">{seats} seats included</div>
        </div>

        <div style="text-align: center;">
            <a href="{signup_url}" class="btn-signup">Accept Invitation</a>
        </div>

        <div class="features">
            <h4>Your plan includes:</h4>
            <ul>
                {features_html}
            </ul>
        </div>

        <div class="expires">
            ⏰ This invitation expires in <strong>{expires_days} days</strong>
        </div>

        <p style="text-align: center; color: #6b7280; font-size: 14px; margin-top: 24px;">
            Or copy this link:<br>
            <a href="{signup_url}" style="color: #3b82f6;">{signup_url}</a>
        </p>

        <div class="footer">
            <p>If you didn't expect this invitation, you can safely ignore this email.</p>
            <p>This invitation was sent by Perennia AI</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def send_subscription_invite(
        self,
        to_email: str,
        company_name: str,
        contact_name: Optional[str],
        plan: str,
        seats: int,
        invitation_token: str,
        personal_message: Optional[str] = None,
        expires_days: int = 7,
        base_url: str = None,
        promo_code: Optional[str] = None
    ) -> bool:
        """Send subscription invitation email"""
        if not base_url:
            base_url = os.getenv('FRONTEND_URL', 'https://perenniaai.com')

        signup_url = f"{base_url}/signup?invite={invitation_token}"
        if promo_code:
            signup_url += f"&promo={promo_code}"
        subject = f"🎉 You're Invited to Join Perennia AI - {company_name}"
        html_body = self.format_subscription_invite_email(
            company_name, contact_name, plan, seats, signup_url, personal_message, expires_days
        )

        greeting = f"Hi {contact_name}" if contact_name else "Hello"
        plain_text = f"""
{greeting},

You're Invited to Join Perennia AI!

You've been invited to set up {company_name} on Perennia AI, the intelligent CRM platform that helps mortgage professionals close more loans with AI-powered automation.

{f'Message: "{personal_message}"' if personal_message else ''}

YOUR PLAN: {plan.upper()}
SEATS: {seats}

Click here to accept your invitation:
{signup_url}

This invitation expires in {expires_days} days.

If you didn't expect this invitation, you can safely ignore this email.

This invitation was sent by Perennia AI
"""

        return self.send_html_email(to_email, subject, html_body, plain_text)

    async def send_html_email_sf(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        db=None,
        user_id: Optional[int] = None,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        reply_to: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send an email with Salesforce-first routing.
        If user has a connected Salesforce integration, sends through SF emailSimple
        (appears in SF Activity History, sent from user's SF address).
        Falls back to SendGrid/SMTP if SF not connected or fails.

        Note: SF emailSimple does not support attachments or custom headers.
        When attachments or custom headers are provided, sends via SendGrid directly.
        """
        # If we have attachments or custom threading headers, skip SF
        # (SF emailSimple doesn't support these)
        skip_sf = bool(attachments) or bool(headers)

        if db is not None and user_id is not None and not skip_sf:
            try:
                from salesforce_integration_models import IntegrationProfile
                from services.salesforce.email_sync_service import salesforce_email_sync

                sf_profile = db.query(IntegrationProfile).filter(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"])
                ).first()

                if sf_profile:
                    sf_result = await salesforce_email_sync.send_email_via_salesforce(
                        db=db,
                        integration_profile_id=sf_profile.id,
                        to_email=to_email,
                        subject=subject,
                        html_body=html_body,
                    )

                    if sf_result.get("success"):
                        logger.info(f"Email to {to_email} sent via Salesforce (user_id={user_id})")
                        return True
                    else:
                        logger.warning(
                            f"SF email failed, falling back to SendGrid: {sf_result.get('message')}"
                        )
            except Exception as sf_err:
                logger.warning(f"SF email routing error, falling back to SendGrid: {sf_err}")

        # Fallback to SendGrid/SMTP — run in thread to avoid blocking event loop
        return await asyncio.to_thread(
            self.send_html_email,
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text_body,
            attachments=attachments,
            headers=headers,
            reply_to=reply_to,
            from_email=from_email,
        )


# Global instance
email_service = EmailService()


# Async wrapper function for use in video meeting routes
async def send_meeting_invite_email(
    to_email: str,
    participant_name: str,
    host_name: str,
    meeting_name: str,
    join_url: str,
    scheduled_time: Optional[datetime] = None
) -> bool:
    """Async wrapper for sending meeting invite emails"""
    return email_service.send_meeting_invite(
        to_email=to_email,
        participant_name=participant_name,
        host_name=host_name,
        meeting_name=meeting_name,
        join_url=join_url,
        scheduled_time=scheduled_time
    )


async def send_lead_notification_email(
    to_email: str,
    lo_name: str,
    lead_name: str,
    lead_email: str,
    lead_phone: Optional[str] = None,
    loan_type: str = "purchase",
    source: str = "microsite",
    message: Optional[str] = None,
    lead_id: Optional[int] = None
) -> bool:
    """Async wrapper for sending lead notification emails"""
    return email_service.send_new_lead_notification(
        to_email=to_email,
        lo_name=lo_name,
        lead_name=lead_name,
        lead_email=lead_email,
        lead_phone=lead_phone,
        loan_type=loan_type,
        source=source,
        message=message,
        lead_id=lead_id
    )


async def send_subscription_invite_email(
    to_email: str,
    company_name: str,
    contact_name: Optional[str],
    plan: str,
    seats: int,
    invitation_token: str,
    personal_message: Optional[str] = None,
    expires_days: int = 7,
    promo_code: Optional[str] = None
) -> bool:
    """Send subscription invitation email"""
    return email_service.send_subscription_invite(
        to_email=to_email,
        company_name=company_name,
        contact_name=contact_name,
        plan=plan,
        seats=seats,
        invitation_token=invitation_token,
        personal_message=personal_message,
        expires_days=expires_days,
        promo_code=promo_code
    )
