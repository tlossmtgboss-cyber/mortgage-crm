"""
Recruiting Email Service

Handles automated emails for recruiting workflows:
- Phone screen follow-up emails
- Candidate portal invitations
- Technical assessment emails
- Offer acceptance/welcome emails

Integrates with the recruiting workflow system to process
tasks with route_to='email_automation'.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy import text

from services.notification_service import notification_service

logger = logging.getLogger(__name__)

# Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Perennia")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RecruitingEmailResult:
    """Result of sending a recruiting email"""
    success: bool
    email_type: str
    recipient: str
    message: str = ""
    error: Optional[str] = None


# =============================================================================
# EMAIL TEMPLATES
# =============================================================================

class RecruitingEmailTemplates:
    """HTML email templates for recruiting workflows"""

    @staticmethod
    def phone_screen_followup(
        candidate_name: str,
        recruiter_name: str,
        recruiter_email: str,
        recruiter_phone: Optional[str] = None,
        next_steps: Optional[str] = None,
    ) -> Dict[str, str]:
        """Template for post-phone screen follow-up email"""

        phone_html = f"<br>{recruiter_phone}" if recruiter_phone else ""
        next_steps_text = next_steps or "We'll be reviewing your qualifications and will be in touch soon about next steps."

        subject = f"Thank You for Speaking With Us - {COMPANY_NAME}"

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
                <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #218D8D 0%, #1a7070 100%); border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: white; font-size: 28px;">&#128222;</span>
                </div>
                <h1 style="margin: 0; color: #111827; font-size: 24px;">Thanks for Speaking With Us!</h1>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Hi {candidate_name},
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Thank you for taking the time to speak with me today. It was great learning more about your background and experience in the mortgage industry.
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                {next_steps_text}
            </p>

            <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">Questions? Contact me directly:</p>
                <p style="margin: 0; color: #111827; font-size: 16px; font-weight: 600;">{recruiter_name}</p>
                <p style="margin: 4px 0 0; color: #218D8D;">
                    <a href="mailto:{recruiter_email}" style="color: #218D8D; text-decoration: none;">{recruiter_email}</a>
                    {phone_html}
                </p>
            </div>

            <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 32px;">
                We appreciate your interest in joining our team!
            </p>

        </div>

        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
            {COMPANY_NAME} Recruiting
        </p>
    </div>
</body>
</html>
"""

        plain_content = f"""Hi {candidate_name},

Thank you for taking the time to speak with me today. It was great learning more about your background and experience in the mortgage industry.

{next_steps_text}

Questions? Contact me directly:
{recruiter_name}
{recruiter_email}
{recruiter_phone or ''}

We appreciate your interest in joining our team!

{COMPANY_NAME} Recruiting
"""

        return {
            "subject": subject,
            "html_content": html_content,
            "plain_content": plain_content,
        }

    @staticmethod
    def portal_invitation(
        candidate_name: str,
        recruiter_name: str,
        portal_url: str,
        company_info: Optional[str] = None,
    ) -> Dict[str, str]:
        """Template for candidate portal invitation email"""

        company_text = company_info or f"Learn more about what makes {COMPANY_NAME} a great place to build your career."

        subject = f"Your Candidate Portal Access - {COMPANY_NAME}"

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
                <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%); border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: white; font-size: 28px;">&#128273;</span>
                </div>
                <h1 style="margin: 0; color: #111827; font-size: 24px;">Your Candidate Portal is Ready!</h1>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Hi {candidate_name},
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                As we move forward in the interview process, we've set up a personalized candidate portal for you. This portal gives you access to:
            </p>

            <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <ul style="margin: 0; padding-left: 20px; color: #374151;">
                    <li style="margin-bottom: 8px;">Information about our company culture and values</li>
                    <li style="margin-bottom: 8px;">Details about compensation and benefits</li>
                    <li style="margin-bottom: 8px;">Answers to frequently asked questions</li>
                    <li style="margin-bottom: 8px;">Direct messaging with your recruiter</li>
                </ul>
            </div>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{portal_url}" style="display: inline-block; background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%); color: white; text-decoration: none; padding: 16px 48px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Access Your Portal
                </a>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                {company_text}
            </p>

            <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">
                Best regards,<br>
                <strong>{recruiter_name}</strong>
            </p>

        </div>

        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
            {COMPANY_NAME} Recruiting
        </p>
    </div>
</body>
</html>
"""

        plain_content = f"""Hi {candidate_name},

As we move forward in the interview process, we've set up a personalized candidate portal for you. This portal gives you access to:

- Information about our company culture and values
- Details about compensation and benefits
- Answers to frequently asked questions
- Direct messaging with your recruiter

Access your portal here: {portal_url}

{company_text}

Best regards,
{recruiter_name}

{COMPANY_NAME} Recruiting
"""

        return {
            "subject": subject,
            "html_content": html_content,
            "plain_content": plain_content,
        }

    @staticmethod
    def assessment_invitation(
        candidate_name: str,
        recruiter_name: str,
        assessment_url: str,
        assessment_type: str = "Skills Assessment",
        deadline_days: int = 3,
        instructions: Optional[str] = None,
    ) -> Dict[str, str]:
        """Template for technical/skills assessment invitation"""

        instructions_text = instructions or """
The assessment consists of questions about mortgage lending, sales strategies, and customer service scenarios.
Please complete it in one sitting - it typically takes 20-30 minutes.
"""

        subject = f"Complete Your {assessment_type} - {COMPANY_NAME}"

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
                <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: white; font-size: 28px;">&#128221;</span>
                </div>
                <h1 style="margin: 0; color: #111827; font-size: 24px;">{assessment_type}</h1>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Hi {candidate_name},
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Congratulations on making it to the assessment phase! As the next step in our process, we'd like you to complete a brief {assessment_type.lower()}.
            </p>

            <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px 20px; margin: 24px 0; border-radius: 0 8px 8px 0;">
                <p style="margin: 0; color: #92400e; font-weight: 600;">
                    Please complete within {deadline_days} days
                </p>
            </div>

            <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px; font-weight: 600;">Instructions:</p>
                <p style="margin: 0; color: #374151; font-size: 14px; line-height: 1.6;">
                    {instructions_text}
                </p>
            </div>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{assessment_url}" style="display: inline-block; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; text-decoration: none; padding: 16px 48px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Start Assessment
                </a>
            </div>

            <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">
                If you have any questions or need accommodations, please reach out to me directly.
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                Best regards,<br>
                <strong>{recruiter_name}</strong>
            </p>

        </div>

        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
            {COMPANY_NAME} Recruiting
        </p>
    </div>
</body>
</html>
"""

        plain_content = f"""Hi {candidate_name},

Congratulations on making it to the assessment phase! As the next step in our process, we'd like you to complete a brief {assessment_type.lower()}.

DEADLINE: Please complete within {deadline_days} days

INSTRUCTIONS:
{instructions_text}

Start your assessment here: {assessment_url}

If you have any questions or need accommodations, please reach out to me directly.

Best regards,
{recruiter_name}

{COMPANY_NAME} Recruiting
"""

        return {
            "subject": subject,
            "html_content": html_content,
            "plain_content": plain_content,
        }

    @staticmethod
    def offer_acceptance_welcome(
        candidate_name: str,
        recruiter_name: str,
        start_date: Optional[str] = None,
        onboarding_url: Optional[str] = None,
        next_steps: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Template for offer acceptance/welcome email"""

        start_date_html = ""
        if start_date:
            start_date_html = f"""
            <div style="background: #dcfce7; border-radius: 12px; padding: 20px; margin: 24px 0; text-align: center;">
                <p style="margin: 0 0 4px; color: #166534; font-size: 14px;">Your Start Date</p>
                <p style="margin: 0; color: #166534; font-size: 24px; font-weight: 700;">{start_date}</p>
            </div>
            """

        steps = next_steps or [
            "Complete your background check authorization",
            "Submit required onboarding documents",
            "Review our company handbook",
            "Set up your equipment and accounts",
        ]

        steps_html = "".join([f'<li style="margin-bottom: 8px;">{step}</li>' for step in steps])

        onboarding_button = ""
        if onboarding_url:
            onboarding_button = f"""
            <div style="text-align: center; margin: 32px 0;">
                <a href="{onboarding_url}" style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; text-decoration: none; padding: 16px 48px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Start Onboarding
                </a>
            </div>
            """

        subject = f"Welcome to {COMPANY_NAME}! 🎉"

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
                <div style="font-size: 64px; margin-bottom: 16px;">🎉</div>
                <h1 style="margin: 0; color: #111827; font-size: 28px;">Welcome to the Team!</h1>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Hi {candidate_name},
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                <strong>Congratulations!</strong> We're thrilled to officially welcome you to {COMPANY_NAME}. Your offer has been accepted, and we couldn't be more excited to have you join our team.
            </p>

            {start_date_html}

            <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <p style="margin: 0 0 12px; color: #111827; font-size: 16px; font-weight: 600;">Next Steps:</p>
                <ul style="margin: 0; padding-left: 20px; color: #374151;">
                    {steps_html}
                </ul>
            </div>

            {onboarding_button}

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                If you have any questions before your start date, don't hesitate to reach out. We're here to help make your transition as smooth as possible.
            </p>

            <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">
                Welcome aboard!<br>
                <strong>{recruiter_name}</strong><br>
                {COMPANY_NAME} Recruiting Team
            </p>

        </div>

        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 24px;">
            {COMPANY_NAME} - Building Careers, One Hire at a Time
        </p>
    </div>
</body>
</html>
"""

        plain_content = f"""Welcome to the Team, {candidate_name}!

Congratulations! We're thrilled to officially welcome you to {COMPANY_NAME}. Your offer has been accepted, and we couldn't be more excited to have you join our team.

{f"YOUR START DATE: {start_date}" if start_date else ""}

NEXT STEPS:
{chr(10).join([f"- {step}" for step in steps])}

{f"Start your onboarding here: {onboarding_url}" if onboarding_url else ""}

If you have any questions before your start date, don't hesitate to reach out. We're here to help make your transition as smooth as possible.

Welcome aboard!
{recruiter_name}
{COMPANY_NAME} Recruiting Team
"""

        return {
            "subject": subject,
            "html_content": html_content,
            "plain_content": plain_content,
        }


# =============================================================================
# RECRUITING EMAIL SERVICE
# =============================================================================

class RecruitingEmailService:
    """
    Service for sending automated recruiting emails.

    Processes workflow tasks with route_to='email_automation' and
    sends the appropriate email based on task title/context.
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self.templates = RecruitingEmailTemplates()

    def send_phone_screen_followup(
        self,
        candidate_email: str,
        candidate_name: str,
        recruiter_name: str,
        recruiter_email: str,
        recruiter_phone: Optional[str] = None,
        next_steps: Optional[str] = None,
    ) -> RecruitingEmailResult:
        """Send phone screen follow-up email to candidate"""

        template = self.templates.phone_screen_followup(
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            recruiter_phone=recruiter_phone,
            next_steps=next_steps,
        )

        result = notification_service.send_email(
            to_email=candidate_email,
            subject=template["subject"],
            html_content=template["html_content"],
            plain_content=template["plain_content"],
        )

        if result.get("success"):
            logger.info(f"Phone screen follow-up sent to {candidate_email}")
            return RecruitingEmailResult(
                success=True,
                email_type="phone_screen_followup",
                recipient=candidate_email,
                message=f"Follow-up email sent to {candidate_name}",
            )
        else:
            logger.error(f"Failed to send phone screen follow-up: {result.get('error')}")
            return RecruitingEmailResult(
                success=False,
                email_type="phone_screen_followup",
                recipient=candidate_email,
                error=result.get("error"),
            )

    def send_portal_invitation(
        self,
        candidate_email: str,
        candidate_name: str,
        recruiter_name: str,
        portal_url: str,
        company_info: Optional[str] = None,
    ) -> RecruitingEmailResult:
        """Send candidate portal invitation email"""

        template = self.templates.portal_invitation(
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            portal_url=portal_url,
            company_info=company_info,
        )

        result = notification_service.send_email(
            to_email=candidate_email,
            subject=template["subject"],
            html_content=template["html_content"],
            plain_content=template["plain_content"],
        )

        if result.get("success"):
            logger.info(f"Portal invitation sent to {candidate_email}")
            return RecruitingEmailResult(
                success=True,
                email_type="portal_invitation",
                recipient=candidate_email,
                message=f"Portal invitation sent to {candidate_name}",
            )
        else:
            logger.error(f"Failed to send portal invitation: {result.get('error')}")
            return RecruitingEmailResult(
                success=False,
                email_type="portal_invitation",
                recipient=candidate_email,
                error=result.get("error"),
            )

    def send_assessment_invitation(
        self,
        candidate_email: str,
        candidate_name: str,
        recruiter_name: str,
        assessment_url: str,
        assessment_type: str = "Skills Assessment",
        deadline_days: int = 3,
        instructions: Optional[str] = None,
    ) -> RecruitingEmailResult:
        """Send technical/skills assessment invitation email"""

        template = self.templates.assessment_invitation(
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            assessment_url=assessment_url,
            assessment_type=assessment_type,
            deadline_days=deadline_days,
            instructions=instructions,
        )

        result = notification_service.send_email(
            to_email=candidate_email,
            subject=template["subject"],
            html_content=template["html_content"],
            plain_content=template["plain_content"],
        )

        if result.get("success"):
            logger.info(f"Assessment invitation sent to {candidate_email}")
            return RecruitingEmailResult(
                success=True,
                email_type="assessment_invitation",
                recipient=candidate_email,
                message=f"Assessment invitation sent to {candidate_name}",
            )
        else:
            logger.error(f"Failed to send assessment invitation: {result.get('error')}")
            return RecruitingEmailResult(
                success=False,
                email_type="assessment_invitation",
                recipient=candidate_email,
                error=result.get("error"),
            )

    def send_welcome_email(
        self,
        candidate_email: str,
        candidate_name: str,
        recruiter_name: str,
        start_date: Optional[str] = None,
        onboarding_url: Optional[str] = None,
        next_steps: Optional[List[str]] = None,
    ) -> RecruitingEmailResult:
        """Send offer acceptance/welcome email"""

        template = self.templates.offer_acceptance_welcome(
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            start_date=start_date,
            onboarding_url=onboarding_url,
            next_steps=next_steps,
        )

        result = notification_service.send_email(
            to_email=candidate_email,
            subject=template["subject"],
            html_content=template["html_content"],
            plain_content=template["plain_content"],
        )

        if result.get("success"):
            logger.info(f"Welcome email sent to {candidate_email}")
            return RecruitingEmailResult(
                success=True,
                email_type="welcome_email",
                recipient=candidate_email,
                message=f"Welcome email sent to {candidate_name}",
            )
        else:
            logger.error(f"Failed to send welcome email: {result.get('error')}")
            return RecruitingEmailResult(
                success=False,
                email_type="welcome_email",
                recipient=candidate_email,
                error=result.get("error"),
            )

    def process_workflow_email_task(
        self,
        task_id: int,
        db_session,
    ) -> RecruitingEmailResult:
        """
        Process an email automation task from the recruiting workflow.

        Determines email type from task title and sends appropriate email.
        """
        # Get task details
        task = db_session.execute(
            text("""
                SELECT rt.id, rt.candidate_id, rt.title, rt.description,
                       rt.assigned_to, rt.organization_id,
                       rc.first_name, rc.last_name, rc.email as candidate_email,
                       rc.phone as candidate_phone
                FROM recruiting_tasks rt
                JOIN mm_candidates rc ON rc.id = rt.candidate_id
                WHERE rt.id = :task_id
            """),
            {"task_id": task_id}
        ).fetchone()

        if not task:
            return RecruitingEmailResult(
                success=False,
                email_type="unknown",
                recipient="",
                error=f"Task {task_id} not found",
            )

        candidate_name = f"{task.first_name} {task.last_name}"
        candidate_email = task.candidate_email

        if not candidate_email:
            return RecruitingEmailResult(
                success=False,
                email_type="unknown",
                recipient="",
                error=f"Candidate has no email address",
            )

        # Get recruiter info
        recruiter = db_session.execute(
            text("SELECT full_name, email, phone FROM users WHERE id = :user_id"),
            {"user_id": task.assigned_to}
        ).fetchone()

        recruiter_name = recruiter.full_name if recruiter else "Recruiting Team"
        recruiter_email = recruiter.email if recruiter else "recruiting@perenniaai.com"
        recruiter_phone = recruiter.phone if recruiter else None

        # Get candidate's portal URL if exists
        portal = db_session.execute(
            text("""
                SELECT slug FROM recruit_portal_workspaces
                WHERE candidate_id = :candidate_id AND is_active = true
                LIMIT 1
            """),
            {"candidate_id": task.candidate_id}
        ).fetchone()

        portal_url = f"{FRONTEND_URL}/recruit/{portal.slug}" if portal else f"{FRONTEND_URL}/recruit"

        # Determine email type from task title and send
        title_lower = task.title.lower()

        if "follow-up email" in title_lower or "followup" in title_lower:
            # Phone screen follow-up
            return self.send_phone_screen_followup(
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                recruiter_email=recruiter_email,
                recruiter_phone=recruiter_phone,
            )

        elif "portal invitation" in title_lower or "portal" in title_lower and "send" in title_lower:
            # Candidate portal invitation
            return self.send_portal_invitation(
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                portal_url=portal_url,
            )

        elif "assessment" in title_lower or "technical" in title_lower:
            # Technical assessment invitation
            assessment_url = f"{FRONTEND_URL}/recruit/{portal.slug}/assessment" if portal else f"{FRONTEND_URL}/recruit"
            return self.send_assessment_invitation(
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                assessment_url=assessment_url,
            )

        elif "welcome" in title_lower or "offer acceptance" in title_lower or "confirmation" in title_lower:
            # Welcome/offer acceptance email
            onboarding_url = f"{FRONTEND_URL}/recruit/{portal.slug}/onboarding" if portal else None
            return self.send_welcome_email(
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                onboarding_url=onboarding_url,
            )

        else:
            # Unknown email type - log warning
            logger.warning(f"Unknown email task type: {task.title}")
            return RecruitingEmailResult(
                success=False,
                email_type="unknown",
                recipient=candidate_email,
                error=f"Unknown email task type: {task.title}",
            )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

recruiting_email_service = RecruitingEmailService()


def get_recruiting_email_service(db_session=None) -> RecruitingEmailService:
    """Get recruiting email service instance"""
    if db_session:
        return RecruitingEmailService(db_session)
    return recruiting_email_service
