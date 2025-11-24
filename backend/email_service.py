"""
Email Service for sending reports and notifications
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""

    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.from_name = os.getenv('FROM_NAME', 'Pipeline 360 CRM')

    def send_html_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send an HTML email with optional attachments"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = f'{self.from_name} <{self.from_email}>'
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')

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

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
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
        <p>This report was automatically generated by Pipeline 360 CRM</p>
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
        plain_text += "This report was automatically generated by Pipeline 360 CRM\n"

        return self.send_html_email(to_email, subject, html_body, plain_text)


# Global instance
email_service = EmailService()
