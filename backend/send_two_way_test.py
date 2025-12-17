#!/usr/bin/env python3
"""
Send Test Email for Two-Way Conversation Demo

Sends a test email to demonstrate the AI qualification agent.
"""

import sys
sys.path.insert(0, '.')

from email_service import EmailService
from datetime import datetime


def send_test_email():
    """Send a test email demonstrating two-way conversation."""

    to_email = "tloss@me.com"
    subject = f"Perennia AI - Two-Way Email Test ({datetime.now().strftime('%H:%M')})"

    html_body = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .header { background: #2563eb; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; }
        .highlight { background: #f0f9ff; padding: 15px; border-radius: 8px; margin: 15px 0; }
        .cta { background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 10px 0; }
        .footer { background: #f3f4f6; padding: 15px; text-align: center; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Perennia AI</h1>
        <p>Two-Way Email Conversation Test</p>
    </div>

    <div class="content">
        <p>Hi Tim,</p>

        <p>This is a test of the <strong>two-way email conversation system</strong> we just built!</p>

        <div class="highlight">
            <h3>What This Tests:</h3>
            <ul>
                <li><strong>Tone Analysis</strong> - Detects emotion, sentiment, urgency</li>
                <li><strong>Qualification Agent</strong> - Progressively collects loan data</li>
                <li><strong>Objection Handling</strong> - Uses SPIN Selling techniques</li>
                <li><strong>Escalation</strong> - Routes angry customers to humans</li>
            </ul>
        </div>

        <p><strong>Try replying with different scenarios:</strong></p>

        <ol>
            <li><em>"I'm interested in refinancing my home worth $500,000"</em> - Tests qualification</li>
            <li><em>"I'm not interested, stop contacting me"</em> - Tests objection handling</li>
            <li><em>"This is URGENT! I want to speak to a supervisor NOW!"</em> - Tests escalation</li>
        </ol>

        <p>The AI agent will analyze your response and generate an appropriate reply using the unified ConversationIntelligence service.</p>

        <div class="highlight">
            <p><strong>Built Today:</strong></p>
            <ul>
                <li>ConversationIntelligence service (shared for email + SMS)</li>
                <li>QualificationAgent with progressive data collection</li>
                <li>API routes for both channels</li>
                <li>White-label organization support</li>
            </ul>
        </div>

        <p>Best regards,<br>
        <strong>Sarah</strong><br>
        Senior Mortgage Consultant<br>
        Perennia AI</p>
    </div>

    <div class="footer">
        <p>This is a test email from the Perennia AI Mortgage CRM</p>
        <p>Sent: {timestamp}</p>
    </div>
</body>
</html>
""".replace('{timestamp}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    plain_text = """
Perennia AI - Two-Way Email Conversation Test

Hi Tim,

This is a test of the two-way email conversation system we just built!

What This Tests:
- Tone Analysis - Detects emotion, sentiment, urgency
- Qualification Agent - Progressively collects loan data
- Objection Handling - Uses SPIN Selling techniques
- Escalation - Routes angry customers to humans

Try replying with different scenarios:
1. "I'm interested in refinancing my home worth $500,000" - Tests qualification
2. "I'm not interested, stop contacting me" - Tests objection handling
3. "This is URGENT! I want to speak to a supervisor NOW!" - Tests escalation

Best regards,
Sarah
Senior Mortgage Consultant
Perennia AI
"""

    print("=" * 60)
    print("SENDING TWO-WAY EMAIL TEST")
    print("=" * 60)
    print(f"\nTo: {to_email}")
    print(f"Subject: {subject}")
    print("-" * 60)

    # Try to send
    service = EmailService()

    if not service.use_sendgrid and not service.smtp_user:
        print("\n WARNING: No email credentials configured!")
        print("   Set SENDGRID_API_KEY or SMTP_USER/SMTP_PASSWORD")
        print("\n To configure SendGrid:")
        print("   export SENDGRID_API_KEY='your-api-key'")
        print("\n To configure SMTP:")
        print("   export SMTP_USER='your-email@gmail.com'")
        print("   export SMTP_PASSWORD='your-app-password'")
        print("\n" + "=" * 60)
        print("EMAIL CONTENT (copy and send manually):")
        print("=" * 60)
        print(plain_text)
        return False

    try:
        success = service.send_html_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text
        )

        if success:
            print("\n Test email sent successfully!")
            print(f"   Check {to_email} for the message")
        else:
            print("\n Failed to send email")
            print("   Check logs for details")

        return success

    except Exception as e:
        print(f"\n Error sending email: {e}")
        return False


if __name__ == "__main__":
    send_test_email()
