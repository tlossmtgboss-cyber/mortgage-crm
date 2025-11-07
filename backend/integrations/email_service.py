"""
Email Service for Mortgage CRM

Handles email verification, password resets, and transactional emails.
"""

import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from sqlalchemy.orm import Session


class EmailService:
    """Service for sending emails"""

    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@mortgagecrm.com')
        self.from_name = os.getenv('FROM_NAME', 'Mortgage CRM')

    def _send_email(self, to_email: str, subject: str, html_content: str, text_content: str = None):
        """
        Send an email using SMTP

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text email body (optional)
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            # Add plain text version if provided
            if text_content:
                part1 = MIMEText(text_content, 'plain')
                msg.attach(part1)

            # Add HTML version
            part2 = MIMEText(html_content, 'html')
            msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            print(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_verification_email(self, to_email: str, verification_token: str, user_name: str = None):
        """
        Send email verification email

        Args:
            to_email: User's email address
            verification_token: Verification token
            user_name: User's name (optional)
        """
        verify_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/verify-email?token={verification_token}"

        subject = "Verify Your Email - Mortgage CRM"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #18a0a6;
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #18a0a6;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to Mortgage CRM!</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name or 'there'},</p>

                    <p>Thank you for signing up for Mortgage CRM! We're excited to have you on board.</p>

                    <p>To complete your registration and start using your account, please verify your email address by clicking the button below:</p>

                    <div style="text-align: center;">
                        <a href="{verify_url}" class="button">Verify Email Address</a>
                    </div>

                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #18a0a6;">{verify_url}</p>

                    <p><strong>This link will expire in 24 hours.</strong></p>

                    <p>If you didn't create an account with Mortgage CRM, you can safely ignore this email.</p>

                    <p>Best regards,<br>The Mortgage CRM Team</p>
                </div>
                <div class="footer">
                    <p>© 2025 Mortgage CRM. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
        Welcome to Mortgage CRM!

        Hi {user_name or 'there'},

        Thank you for signing up! Please verify your email address by visiting this link:

        {verify_url}

        This link will expire in 24 hours.

        If you didn't create an account, you can safely ignore this email.

        Best regards,
        The Mortgage CRM Team
        """

        return self._send_email(to_email, subject, html_content, text_content)

    def send_welcome_email(self, to_email: str, user_name: str):
        """
        Send welcome email after verification

        Args:
            to_email: User's email address
            user_name: User's name
        """
        subject = "Welcome to Mortgage CRM - Get Started!"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #18a0a6;
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #18a0a6;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .feature {{
                    margin: 15px 0;
                    padding: 15px;
                    background-color: white;
                    border-left: 4px solid #18a0a6;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 You're All Set!</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>

                    <p>Your account has been verified successfully! You're now ready to transform your mortgage business with AI-powered CRM.</p>

                    <h3>Here's what you can do next:</h3>

                    <div class="feature">
                        <strong>📋 Complete Onboarding</strong><br>
                        Upload your processes and team structure to let our AI build custom workflows
                    </div>

                    <div class="feature">
                        <strong>👥 Add Your Team</strong><br>
                        Invite team members and assign roles
                    </div>

                    <div class="feature">
                        <strong>🤖 Meet Your AI Assistant</strong><br>
                        Start automating tasks and getting intelligent insights
                    </div>

                    <div class="feature">
                        <strong>🔗 Connect Integrations</strong><br>
                        Link your email, calendar, and Microsoft Teams
                    </div>

                    <div style="text-align: center; margin-top: 30px;">
                        <a href="{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/onboarding" class="button">Start Onboarding</a>
                    </div>

                    <p>Need help? Our support team is here for you at support@mortgagecrm.com</p>

                    <p>Best regards,<br>The Mortgage CRM Team</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(to_email, subject, html_content)

    def send_password_reset_email(self, to_email: str, reset_token: str, user_name: str = None):
        """
        Send password reset email

        Args:
            to_email: User's email address
            reset_token: Password reset token
            user_name: User's name (optional)
        """
        reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={reset_token}"

        subject = "Reset Your Password - Mortgage CRM"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .content {{
                    background-color: #f9f9f9;
                    padding: 30px;
                    border-radius: 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #18a0a6;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="content">
                    <h2>Password Reset Request</h2>

                    <p>Hi {user_name or 'there'},</p>

                    <p>We received a request to reset your password for your Mortgage CRM account.</p>

                    <p>Click the button below to reset your password:</p>

                    <div style="text-align: center;">
                        <a href="{reset_url}" class="button">Reset Password</a>
                    </div>

                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #18a0a6;">{reset_url}</p>

                    <p><strong>This link will expire in 1 hour.</strong></p>

                    <p>If you didn't request a password reset, please ignore this email and your password will remain unchanged.</p>

                    <p>Best regards,<br>The Mortgage CRM Team</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(to_email, subject, html_content)


class VerificationTokenService:
    """Service for managing email verification tokens"""

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_verification_token(db: Session, user_id: int, email: str) -> str:
        """
        Create a verification token for a user

        Args:
            db: Database session
            user_id: User ID
            email: User's email

        Returns:
            Verification token string
        """
        from main import EmailVerificationToken  # Import here to avoid circular imports

        # Delete any existing tokens for this user
        db.query(EmailVerificationToken).filter(
            EmailVerificationToken.user_id == user_id
        ).delete()

        # Generate new token
        token = VerificationTokenService.generate_token()
        expires_at = datetime.utcnow() + timedelta(hours=24)

        # Create token record
        db_token = EmailVerificationToken(
            token=token,
            user_id=user_id,
            email=email,
            expires_at=expires_at
        )
        db.add(db_token)
        db.commit()

        return token

    @staticmethod
    def verify_token(db: Session, token: str) -> Optional[int]:
        """
        Verify a token and return the user ID if valid

        Args:
            db: Database session
            token: Verification token

        Returns:
            User ID if valid, None otherwise
        """
        from main import EmailVerificationToken

        token_record = db.query(EmailVerificationToken).filter(
            EmailVerificationToken.token == token
        ).first()

        if not token_record:
            return None

        # Check if expired
        if token_record.expires_at < datetime.utcnow():
            db.delete(token_record)
            db.commit()
            return None

        # Token is valid
        user_id = token_record.user_id

        # Delete the token (one-time use)
        db.delete(token_record)
        db.commit()

        return user_id
