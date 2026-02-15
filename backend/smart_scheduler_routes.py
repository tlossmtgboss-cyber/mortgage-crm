"""
Smart Scheduler API Routes - Perennia AI AI-Native Appointment Scheduling

Comprehensive API endpoints for:
- Scheduler configuration management
- Availability slot management
- Appointment booking (internal + public)
- Routing rules
- Blocked time management
- Booking links
- AI-powered slot recommendations
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import logging
import pytz
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum
import base64
import uuid as uuid_lib

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode, RoutingStrategy,
    ReminderChannel, DayOfWeek, SlotPriority, DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_WORKING_HOURS
)
from services.notification_service import notification_service
from services.microsoft_graph import create_event_via_graph, CalendarResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Smart Scheduler"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user = None
_models = None  # Will hold all scheduler models


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# EMAIL SERVICE STATUS ENDPOINT
# ============================================================================

@router.get("/email-service-status")
async def get_email_service_status():
    """Check if email service is properly configured"""
    sendgrid_configured = bool(os.getenv("SENDGRID_API_KEY"))
    sendgrid_from_email = os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com")

    return {
        "sendgrid_configured": sendgrid_configured,
        "from_email": sendgrid_from_email,
        "status": "ready" if sendgrid_configured else "not_configured",
        "message": "Email service is ready to send" if sendgrid_configured else "SendGrid API key not configured - emails will be logged only (dry run)"
    }


@router.post("/test-email")
async def test_email_send(to_email: str = "tloss@me.com"):
    """Test endpoint to send a test email and see actual SendGrid response"""
    try:
        result = notification_service.send_email(
            to_email=to_email,
            subject="Test Email from Perennia CRM",
            html_content="""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Test Email</h2>
                <p>This is a test email from Perennia CRM to verify SendGrid is working.</p>
                <p>Time sent: """ + datetime.now().isoformat() + """</p>
            </body>
            </html>
            """,
            plain_content="Test email from Perennia CRM. Time: " + datetime.now().isoformat()
        )

        return {
            "test_result": result,
            "to_email": to_email,
            "from_email": os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com"),
            "sendgrid_key_present": bool(os.getenv("SENDGRID_API_KEY")),
            "sendgrid_key_length": len(os.getenv("SENDGRID_API_KEY", "")) if os.getenv("SENDGRID_API_KEY") else 0
        }
    except Exception as e:
        return {
            "test_result": {"success": False, "error": "Internal server error"},
            "exception_type": type(e).__name__,
            "to_email": to_email
        }


# ============================================================================
# APPOINTMENT NOTIFICATION HELPERS
# ============================================================================

def generate_ics_content(
    appointment_title: str,
    start_datetime: datetime,
    duration_minutes: int,
    attendee_email: str,
    attendee_name: str,
    organizer_email: str,
    organizer_name: str,
    description: str = "",
    location: str = "",
    video_link: str = None
):
    """Generate ICS calendar file content"""
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    uid = str(uuid_lib.uuid4())
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_datetime.strftime("%Y%m%dT%H%M%SZ")
    dtend = end_datetime.strftime("%Y%m%dT%H%M%SZ")

    # Add video link to description if provided
    full_description = description
    if video_link:
        full_description += "\\n\\nJoin Video Call: " + video_link
        if not location:
            location = video_link

    # Escape newlines for ICS format - must be done outside f-string
    ics_description = full_description.replace("\n", "\\n")

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Perennia AI//Perennia AI//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{appointment_title}
DESCRIPTION:{ics_description}
LOCATION:{location}
ORGANIZER;CN={organizer_name}:mailto:{organizer_email}
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN={attendee_name}:mailto:{attendee_email}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""

    return ics_content


def send_appointment_confirmation_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration: str,
    meeting_mode: str = "Phone Call",
    team_member_name: str = None,
    team_member_email: str = None,
    video_link: str = None,
    scheduled_start: datetime = None,
    duration_minutes: int = 30
):
    """Send appointment confirmation email with calendar invite using SendGrid"""
    try:
        logger.info(f"Attempting to send appointment email to {attendee_email}")

        team_member_section = f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {team_member_name}</p>" if team_member_name else ""

        # Add video call button if video link is provided
        video_button_section = ""
        if video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                        Or copy this link: <a href="{video_link}" style="color: #217F8D;">{video_link}</a>
                    </p>
            """

        # Add calendar reminder section
        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                📅 A calendar invite is attached to this email. Click on the attachment to add this appointment to your calendar.
                            </p>
                        </div>
        """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">Appointment Confirmed!</h1>
                    </div>

                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment has been scheduled. Here are the details:</p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {video_button_section}
                        {calendar_section}
                        <p style="font-size: 14px; color: #6b7280;">
                            We'll send you a reminder before your appointment. If you need to reschedule,
                            please contact us as soon as possible.
                        </p>

                        <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                            Looking forward to speaking with you!
                        </p>
                    </div>
                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    Sent from Perennia AI - Perennia AI
                </p>
            </div>
        </body>
        </html>
        """

        video_link_text = f"\nJoin Video Call: {video_link}" if video_link else ""
        text_content = f"""
Appointment Confirmed!

Hi {attendee_name},

Your appointment has been scheduled. Here are the details:

Date: {appointment_date}
Time: {appointment_time}
Duration: {duration}
Meeting Type: {meeting_mode}
{f'Meeting with: {team_member_name}' if team_member_name else ''}{video_link_text}

A calendar invite is attached to this email.

We'll send you a reminder before your appointment. If you need to reschedule, please contact us as soon as possible.

Looking forward to speaking with you!

- Perennia AI Team
        """

        # Generate ICS attachment if we have the scheduled_start datetime
        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com")
                organizer_name = team_member_name or "Perennia AI"

                ics_content = generate_ics_content(
                    appointment_title=appointment_title,
                    start_datetime=scheduled_start,
                    duration_minutes=duration_minutes,
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    organizer_email=organizer_email,
                    organizer_name=organizer_name,
                    description=f"Appointment: {appointment_title}",
                    video_link=video_link
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment.ics',
                    'type': 'text/calendar'
                })
                logger.info("ICS calendar attachment created successfully")
            except Exception as ics_error:
                logger.error(f"Failed to generate ICS attachment: {ics_error}")

        # Use SendGrid via NotificationService
        logger.info(f"Calling notification_service.send_email to {attendee_email}")
        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"Appointment Confirmed: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None
        )

        logger.info(f"SendGrid response: {result}")

        if result.get("success"):
            logger.info(f"Appointment confirmation email sent successfully to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', f"SendGrid returned status {result.get('status_code', 'unknown')}")
            logger.error(f"Failed to send appointment email to {attendee_email}: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_appointment_confirmation_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


def send_appointment_confirmation_sms(
    attendee_phone: str,
    attendee_name: str,
    appointment_date: str,
    appointment_time: str,
    team_member_name: str = None
):
    """Send appointment confirmation SMS via Twilio"""
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")

        if not account_sid or not auth_token or not from_number:
            logger.warning("Twilio credentials not configured - skipping SMS confirmation")
            return False

        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} is confirmed for {appointment_date} at {appointment_time}. We'll send a reminder before your call. Reply HELP for assistance."

        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=attendee_phone
        )

        logger.info(f"Appointment confirmation SMS sent to {attendee_phone}, SID: {message.sid}")
        return True

    except Exception as e:
        logger.error(f"Failed to send appointment confirmation SMS: {e}")
        return False


def send_appointment_update_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration: str,
    meeting_mode: str = "Phone Call",
    team_member_name: str = None,
    team_member_email: str = None,
    video_link: str = None,
    scheduled_start: datetime = None,
    duration_minutes: int = 30,
    old_date: str = None,
    old_time: str = None
):
    """Send appointment update/reschedule email with updated calendar invite using SendGrid"""
    try:
        logger.info(f"Attempting to send appointment update email to {attendee_email}")

        team_member_section = f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {team_member_name}</p>" if team_member_name else ""

        # Show what changed if we have old date/time
        change_section = ""
        if old_date and old_time:
            change_section = f"""
                        <div style="background: #fef3c7; border-radius: 8px; padding: 16px; margin: 20px 0;">
                            <p style="margin: 0 0 8px 0; color: #92400e; font-weight: bold;">📅 Appointment Rescheduled</p>
                            <p style="margin: 0; color: #92400e; font-size: 14px;">
                                <s>Previous: {old_date} at {old_time}</s><br>
                                <strong>New: {appointment_date} at {appointment_time}</strong>
                            </p>
                        </div>
            """

        video_button_section = ""
        if video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
            """

        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                📅 An updated calendar invite is attached. Please add it to replace the previous appointment.
                            </p>
                        </div>
        """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">Appointment Updated!</h1>
                    </div>

                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment has been updated. Here are the new details:</p>
                        {change_section}
                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {video_button_section}
                        {calendar_section}
                        <p style="font-size: 14px; color: #6b7280;">
                            If you have any questions about this change, please contact us.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Appointment Updated!

Hi {attendee_name},

Your appointment has been updated. Here are the new details:

Date: {appointment_date}
Time: {appointment_time}
Duration: {duration}
Meeting Type: {meeting_mode}
{f'Meeting with: {team_member_name}' if team_member_name else ''}

An updated calendar invite is attached to this email.

- Perennia AI Team
        """

        # Generate ICS attachment
        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com")
                organizer_name = team_member_name or "Perennia AI"

                ics_content = generate_ics_content(
                    appointment_title=appointment_title,
                    start_datetime=scheduled_start,
                    duration_minutes=duration_minutes,
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    organizer_email=organizer_email,
                    organizer_name=organizer_name,
                    description=f"Updated Appointment: {appointment_title}",
                    video_link=video_link
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment_updated.ics',
                    'type': 'text/calendar'
                })
            except Exception as ics_error:
                logger.error(f"Failed to generate ICS attachment for update: {ics_error}")

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"Appointment Updated: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None
        )

        if result.get("success"):
            logger.info(f"Appointment update email sent successfully to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to send appointment update email: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_appointment_update_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


def send_appointment_update_sms(
    attendee_phone: str,
    attendee_name: str,
    appointment_date: str,
    appointment_time: str,
    team_member_name: str = None
):
    """Send appointment update SMS via Twilio"""
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")

        if not account_sid or not auth_token or not from_number:
            logger.warning("Twilio credentials not configured - skipping SMS update")
            return False

        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} has been UPDATED to {appointment_date} at {appointment_time}. Please check your email for the updated calendar invite."

        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=attendee_phone
        )

        logger.info(f"Appointment update SMS sent to {attendee_phone}, SID: {message.sid}")
        return True

    except Exception as e:
        logger.error(f"Failed to send appointment update SMS: {e}")
        return False


def send_team_member_notification_email(
    team_member_email: str,
    team_member_name: str,
    attendee_name: str,
    attendee_email: str,
    attendee_phone: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration: str,
    meeting_mode: str = "Phone Call",
    video_link: str = None,
    scheduled_start: datetime = None,
    duration_minutes: int = 30
):
    """Send notification email to the assigned team member about a new appointment with calendar invite"""
    try:
        logger.info(f"Sending team member notification to {team_member_email}")

        # Add video call button if video link is provided
        video_button_section = ""
        if video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                        Video link: <a href="{video_link}" style="color: #217F8D;">{video_link}</a>
                    </p>
            """

        # Add calendar reminder section
        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                📅 A calendar invite is attached to this email. Click on the attachment to add this appointment to your calendar.
                            </p>
                        </div>
        """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">New Appointment Scheduled</h1>
                    </div>

                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {team_member_name},</p>

                        <p style="font-size: 16px; color: #374151;">A new appointment has been scheduled for you:</p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Client:</strong> {attendee_name}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Email:</strong> <a href="mailto:{attendee_email}" style="color: #217F8D;">{attendee_email}</a></p>
                            {f'<p style="margin: 8px 0; color: #111827;"><strong>Phone:</strong> <a href="tel:{attendee_phone}" style="color: #217F8D;">{attendee_phone}</a></p>' if attendee_phone else ''}
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {meeting_mode}</p>
                        </div>
                        {video_button_section}
                        {calendar_section}
                    </div>
                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    Sent from Perennia AI - Perennia AI
                </p>
            </div>
        </body>
        </html>
        """

        video_link_text = f"\nVideo Call Link: {video_link}" if video_link else ""
        text_content = f"""
New Appointment Scheduled

Hi {team_member_name},

A new appointment has been scheduled for you:

Client: {attendee_name}
Email: {attendee_email}
{f'Phone: {attendee_phone}' if attendee_phone else ''}
Date: {appointment_date}
Time: {appointment_time}
Duration: {duration}
Meeting Type: {meeting_mode}{video_link_text}

A calendar invite is attached to this email.

- Perennia AI Team
        """

        # Generate ICS attachment if we have the scheduled_start datetime
        attachments = []
        if scheduled_start:
            try:
                ics_content = generate_ics_content(
                    appointment_title=f"Meeting with {attendee_name}: {appointment_title}",
                    start_datetime=scheduled_start,
                    duration_minutes=duration_minutes,
                    attendee_email=team_member_email,
                    attendee_name=team_member_name,
                    organizer_email=os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com"),
                    organizer_name="Perennia AI",
                    description=f"Meeting with {attendee_name}\\nEmail: {attendee_email}\\nPhone: {attendee_phone or 'N/A'}",
                    video_link=video_link
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment.ics',
                    'type': 'text/calendar'
                })
                logger.info("ICS calendar attachment created for team member")
            except Exception as ics_error:
                logger.error(f"Failed to generate ICS attachment for team member: {ics_error}")

        # Use SendGrid via NotificationService
        result = notification_service.send_email(
            to_email=team_member_email,
            subject=f"New Appointment: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None
        )

        logger.info(f"Team member email SendGrid response: {result}")

        if result.get("success"):
            logger.info(f"Team member notification email sent successfully to {team_member_email}")
            return True
        else:
            logger.warning(f"Failed to send team member notification: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        logger.error(f"Failed to send team member notification email: {e}", exc_info=True)
        return False


def send_appointment_cancellation_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    team_member_name: str = None,
    cancellation_reason: str = None
):
    """Send appointment cancellation email to attendee"""
    try:
        logger.info(f"Sending cancellation email to {attendee_email}")

        reason_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Reason:</strong> {cancellation_reason}</p>" if cancellation_reason else ""
        team_member_section = f" with {team_member_name}" if team_member_name else ""

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">Appointment Cancelled</h1>
                    </div>

                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment{team_member_section} has been cancelled.</p>

                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #991b1b;"><strong>Cancelled Appointment:</strong></p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Title:</strong> {appointment_title}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {appointment_time}</p>
                            {reason_section}
                        </div>

                        <p style="font-size: 14px; color: #6b7280;">
                            If you would like to reschedule, please contact us or book a new appointment.
                        </p>

                        <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                            We apologize for any inconvenience.
                        </p>
                    </div>
                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    Sent from Perennia AI - Perennia AI
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Appointment Cancelled

Hi {attendee_name},

Your appointment{team_member_section} has been cancelled.

Cancelled Appointment:
Title: {appointment_title}
Date: {appointment_date}
Time: {appointment_time}
{f'Reason: {cancellation_reason}' if cancellation_reason else ''}

If you would like to reschedule, please contact us or book a new appointment.

We apologize for any inconvenience.

- Perennia AI Team
        """

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"Appointment Cancelled: {appointment_title}",
            html_content=html_content,
            text_content=text_content
        )

        if result.get("success"):
            logger.info(f"Cancellation email sent successfully to {attendee_email}")
            return True
        else:
            logger.warning(f"Failed to send cancellation email: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        logger.error(f"Failed to send cancellation email: {e}", exc_info=True)
        return False


def send_team_member_cancellation_email(
    team_member_email: str,
    team_member_name: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    cancellation_reason: str = None,
    cancelled_by: str = None
):
    """Send cancellation notification to team member"""
    try:
        logger.info(f"Sending cancellation notification to team member {team_member_email}")

        reason_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Reason:</strong> {cancellation_reason}</p>" if cancellation_reason else ""
        cancelled_by_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Cancelled by:</strong> {cancelled_by}</p>" if cancelled_by else ""

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">Appointment Cancelled</h1>
                    </div>

                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {team_member_name},</p>

                        <p style="font-size: 16px; color: #374151;">An appointment with <strong>{attendee_name}</strong> has been cancelled.</p>

                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #991b1b;"><strong>Cancelled Appointment:</strong></p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Client:</strong> {attendee_name}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Title:</strong> {appointment_title}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {appointment_time}</p>
                            {reason_section}
                            {cancelled_by_section}
                        </div>

                        <p style="font-size: 14px; color: #6b7280;">
                            This time slot is now available in your calendar.
                        </p>
                    </div>
                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    Sent from Perennia AI - Perennia AI
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Appointment Cancelled

Hi {team_member_name},

An appointment with {attendee_name} has been cancelled.

Cancelled Appointment:
Client: {attendee_name}
Title: {appointment_title}
Date: {appointment_date}
Time: {appointment_time}
{f'Reason: {cancellation_reason}' if cancellation_reason else ''}
{f'Cancelled by: {cancelled_by}' if cancelled_by else ''}

This time slot is now available in your calendar.

- Perennia AI Team
        """

        result = notification_service.send_email(
            to_email=team_member_email,
            subject=f"Appointment Cancelled: {attendee_name} - {appointment_title}",
            html_content=html_content,
            text_content=text_content
        )

        if result.get("success"):
            logger.info(f"Team member cancellation notification sent to {team_member_email}")
            return True
        else:
            logger.warning(f"Failed to send team member cancellation: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        logger.error(f"Failed to send team member cancellation email: {e}", exc_info=True)
        return False


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class WorkingHoursDay(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"
    enabled: bool = True


class SchedulerConfigCreate(BaseModel):
    config_name: str
    description: Optional[str] = None
    timezone: str = "America/Chicago"
    default_duration_minutes: int = 30
    buffer_before_minutes: int = 5
    buffer_after_minutes: int = 5
    min_notice_hours: int = 2
    max_advance_days: int = 60
    max_meetings_per_day: int = 8
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = "relationship"
    ai_scheduling_enabled: bool = True


class SchedulerConfigUpdate(BaseModel):
    config_name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    min_notice_hours: Optional[int] = None
    max_advance_days: Optional[int] = None
    max_meetings_per_day: Optional[int] = None
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = None
    ai_scheduling_enabled: Optional[bool] = None
    auto_reschedule_enabled: Optional[bool] = None
    smart_reminders_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class LandingPageSettings(BaseModel):
    logo_url: Optional[str] = ''
    profile_picture_url: Optional[str] = ''
    video_url: Optional[str] = ''
    video_type: Optional[str] = 'youtube'  # youtube, vimeo, loom, custom
    headline: Optional[str] = 'Schedule a Meeting'
    subheadline: Optional[str] = 'Choose a time that works for you'
    description: Optional[str] = ''
    show_profile: Optional[bool] = True
    profile_name: Optional[str] = ''
    profile_title: Optional[str] = ''
    profile_bio: Optional[str] = ''
    accent_color: Optional[str] = '#217F8D'
    background_style: Optional[str] = 'white'  # white, light, gradient
    show_company_logo: Optional[bool] = True
    show_social_proof: Optional[bool] = False
    testimonial_text: Optional[str] = ''
    testimonial_author: Optional[str] = ''


class AppointmentTypeCreate(BaseModel):
    type_key: str
    type_name: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    default_duration_minutes: int = 30
    allowed_durations: List[int] = [15, 30, 45, 60]
    allowed_modes: List[str] = ["video", "phone"]
    requires_loan_id: bool = False
    requires_lead_id: bool = False
    intake_questions: List[Dict] = []
    color: str = "#3b82f6"
    icon: str = "calendar"
    is_public: bool = True
    public_slug: Optional[str] = None


class AppointmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    allowed_durations: Optional[List[int]] = None
    allowed_modes: Optional[List[str]] = None
    intake_questions: Optional[List[Dict]] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class AvailabilitySlotCreate(BaseModel):
    day_of_week: Optional[str] = None
    specific_date: Optional[date] = None
    start_time: str  # "09:00"
    end_time: str    # "17:00"
    priority: str = "standard"
    is_recurring: bool = True
    allowed_meeting_types: List[str] = []
    max_bookings: int = 1


class AvailabilitySlotUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_meeting_types: Optional[List[str]] = None


class AppointmentCreate(BaseModel):
    appointment_type_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = "video"
    scheduled_start: datetime
    duration_minutes: int = 30
    timezone: str = "America/Chicago"

    # Attendee info (for external bookings)
    attendee_name: Optional[str] = None
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None

    # Related entities
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None

    # Intake responses
    intake_responses: Dict = {}

    # AI context
    booked_by_ai: bool = False
    ai_booking_context: Optional[Dict] = None


class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    meeting_mode: Optional[str] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    status: Optional[str] = None
    cancellation_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    send_notification: Optional[bool] = True  # Send email/SMS on update


class BlockedTimeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    block_type: str = "custom"
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool = False
    is_recurring: bool = False
    recurrence_pattern: Optional[Dict] = None
    applies_to_all_users: bool = False


class BookingLinkCreate(BaseModel):
    slug: str
    link_name: str
    description: Optional[str] = None
    appointment_type_ids: List[int] = []
    single_appointment_type_id: Optional[int] = None
    is_public: bool = True
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    routing_strategy: str = "relationship"
    assigned_users: List[int] = []


class AvailableSlotsRequest(BaseModel):
    appointment_type_id: Optional[int] = None
    meeting_type: Optional[str] = None
    duration_minutes: int = 30
    start_date: date
    end_date: date
    timezone: str = "America/Chicago"


class PublicBookingConfirmRequest(BaseModel):
    appointment_type_id: int
    start_time: datetime
    duration_minutes: int = 30
    attendee_name: str
    attendee_email: EmailStr
    attendee_phone: Optional[str] = None
    notes: Optional[str] = None
    user_ids: List[int] = []  # Empty = any available user
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    meeting_mode: Optional[str] = None  # video, phone, in_person
    team_member_id: Optional[int] = None
    team_member_name: Optional[str] = None


class PublicAvailableSlotsRequest(BaseModel):
    """Request model for website demo scheduler"""
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    duration_minutes: int = 30
    appointment_type: str = "platform-demo"


class SlotRecommendation(BaseModel):
    slot_start: datetime
    slot_end: datetime
    user_id: int
    user_name: str
    score: float  # AI-calculated score
    reasons: List[str]  # Why this slot is recommended


# ============================================================================
# SCHEDULER CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_scheduler_config(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the current user's scheduler configuration"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Return default config structure
        return {
            "config": None,
            "defaults": {
                "timezone": "America/Chicago",
                "default_duration_minutes": 30,
                "buffer_before_minutes": 5,
                "buffer_after_minutes": 5,
                "min_notice_hours": 2,
                "max_advance_days": 60,
                "max_meetings_per_day": 8,
                "working_hours": DEFAULT_WORKING_HOURS
            }
        }

    return {
        "config": {
            "id": config.id,
            "config_name": config.config_name,
            "description": config.description,
            "timezone": config.timezone,
            "default_duration_minutes": config.default_duration_minutes,
            "buffer_before_minutes": config.buffer_before_minutes,
            "buffer_after_minutes": config.buffer_after_minutes,
            "min_notice_hours": config.min_notice_hours,
            "max_advance_days": config.max_advance_days,
            "max_meetings_per_day": config.max_meetings_per_day,
            "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
            "routing_strategy": config.routing_strategy.value if config.routing_strategy else "relationship",
            "ai_scheduling_enabled": config.ai_scheduling_enabled,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }
    }


@router.post("/config")
async def create_scheduler_config(
    config_data: SchedulerConfigCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create scheduler configuration for the current user"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    # Check if config already exists
    existing = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Configuration already exists. Use PUT to update.")

    # Parse routing strategy
    routing_strategy = None
    if config_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(config_data.routing_strategy)
        except ValueError:
            routing_strategy = RoutingStrategy.RELATIONSHIP

    config = SchedulerConfig(
        user_id=user.id,
        config_name=config_data.config_name,
        description=config_data.description,
        timezone=config_data.timezone,
        default_duration_minutes=config_data.default_duration_minutes,
        buffer_before_minutes=config_data.buffer_before_minutes,
        buffer_after_minutes=config_data.buffer_after_minutes,
        min_notice_hours=config_data.min_notice_hours,
        max_advance_days=config_data.max_advance_days,
        max_meetings_per_day=config_data.max_meetings_per_day,
        working_hours=config_data.working_hours or DEFAULT_WORKING_HOURS,
        routing_strategy=routing_strategy,
        ai_scheduling_enabled=config_data.ai_scheduling_enabled
    )

    db.add(config)
    db.commit()
    db.refresh(config)

    return {"message": "Scheduler configuration created", "config_id": config.id}


@router.put("/config")
async def update_scheduler_config(
    config_data: SchedulerConfigUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update scheduler configuration"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Update fields
    update_fields = config_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if field == "routing_strategy" and value:
            try:
                value = RoutingStrategy(value)
            except ValueError:
                continue
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"message": "Configuration updated", "config_id": config.id}


# ============================================================================
# LANDING PAGE SETTINGS ENDPOINTS
# ============================================================================

@router.get("/landing-page-settings")
async def get_landing_page_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get landing page customization settings"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    # Return default settings if no config exists
    default_settings = {
        "logo_url": "",
        "profile_picture_url": "",
        "video_url": "",
        "video_type": "youtube",
        "headline": "Schedule a Meeting",
        "subheadline": "Choose a time that works for you",
        "description": "",
        "show_profile": True,
        "profile_name": user.first_name or "",
        "profile_title": "Loan Officer",
        "profile_bio": "",
        "accent_color": "#217F8D",
        "background_style": "white",
        "show_company_logo": True,
        "show_social_proof": False,
        "testimonial_text": "",
        "testimonial_author": ""
    }

    if not config:
        return {"settings": default_settings}

    # Get landing page settings from config (stored as JSON)
    stored_settings = getattr(config, 'landing_page_settings', None) or {}

    # Merge with defaults
    settings = {**default_settings, **stored_settings}

    return {"settings": settings}


@router.put("/landing-page-settings")
async def update_landing_page_settings(
    settings_data: LandingPageSettings,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update landing page customization settings"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Auto-create config with landing page settings
        config = SchedulerConfig(
            user_id=user.id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS,
            landing_page_settings=settings_data.model_dump()
        )
        db.add(config)
    else:
        # Update existing config
        config.landing_page_settings = settings_data.model_dump()

    db.commit()

    logger.info(f"Landing page settings updated for user {user.id}")

    return {"message": "Landing page settings saved successfully"}


# ============================================================================
# APPOINTMENT TYPE ENDPOINTS
# ============================================================================

@router.get("/appointment-types")
async def list_appointment_types(
    request: Request,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """List all appointment types"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get user's config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Return default types
        return {"appointment_types": DEFAULT_APPOINTMENT_TYPES, "source": "defaults"}

    query = db.query(AppointmentType).filter(AppointmentType.config_id == config.id)

    if not include_inactive:
        query = query.filter(AppointmentType.is_active == True)

    types = query.order_by(AppointmentType.display_order).all()

    return {
        "appointment_types": [
            {
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "meeting_type": t.meeting_type.value if t.meeting_type else "custom",
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": t.allowed_durations,
                "allowed_modes": t.allowed_modes,
                "requires_loan_id": t.requires_loan_id,
                "requires_lead_id": t.requires_lead_id,
                "intake_questions": t.intake_questions,
                "color": t.color,
                "icon": t.icon,
                "is_public": t.is_public,
                "public_slug": t.public_slug,
                "is_active": t.is_active
            }
            for t in types
        ],
        "source": "database"
    }


@router.post("/appointment-types")
async def create_appointment_type(
    type_data: AppointmentTypeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment type"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        # Auto-create config
        config = SchedulerConfig(
            user_id=user.id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    # Check for duplicate type_key
    existing = db.query(AppointmentType).filter(
        AppointmentType.config_id == config.id,
        AppointmentType.type_key == type_data.type_key
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Appointment type with this key already exists")

    # Parse meeting type
    meeting_type = MeetingType.CUSTOM
    if type_data.meeting_type:
        try:
            meeting_type = MeetingType(type_data.meeting_type)
        except ValueError:
            pass

    appt_type = AppointmentType(
        config_id=config.id,
        type_key=type_data.type_key,
        type_name=type_data.type_name,
        description=type_data.description,
        meeting_type=meeting_type,
        default_duration_minutes=type_data.default_duration_minutes,
        allowed_durations=type_data.allowed_durations,
        allowed_modes=type_data.allowed_modes,
        requires_loan_id=type_data.requires_loan_id,
        requires_lead_id=type_data.requires_lead_id,
        intake_questions=type_data.intake_questions,
        color=type_data.color,
        icon=type_data.icon,
        is_public=type_data.is_public,
        public_slug=type_data.public_slug
    )

    db.add(appt_type)
    db.commit()
    db.refresh(appt_type)

    return {"message": "Appointment type created", "type_id": appt_type.id}


@router.put("/appointment-types/{type_id}")
async def update_appointment_type(
    type_id: int,
    type_data: AppointmentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment type"""
    user = await get_current_user(request, db)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    # Verify ownership
    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    update_fields = type_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(appt_type, field, value)

    db.commit()

    return {"message": "Appointment type updated"}


@router.delete("/appointment-types/{type_id}")
async def delete_appointment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete (deactivate) an appointment type"""
    user = await get_current_user(request, db)

    AppointmentType = _models['AppointmentType']
    SchedulerConfig = _models['SchedulerConfig']

    appt_type = db.query(AppointmentType).join(SchedulerConfig).filter(
        AppointmentType.id == type_id,
        SchedulerConfig.user_id == user.id
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    appt_type.is_active = False
    db.commit()

    return {"message": "Appointment type deactivated"}


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@router.get("/availability")
async def get_availability(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get availability slots for a date range"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    target_user_id = user_id or user.id

    # Get config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == target_user_id
    ).first()

    if not config:
        # Return default working hours
        return {
            "availability": [],
            "working_hours": DEFAULT_WORKING_HOURS,
            "blocked_times": [],
            "existing_appointments": []
        }

    # Get custom availability slots
    slots = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.config_id == config.id,
        AvailabilitySlot.is_active == True,
        or_(
            AvailabilitySlot.is_recurring == True,
            and_(
                AvailabilitySlot.specific_date >= start_date,
                AvailabilitySlot.specific_date <= end_date
            )
        )
    ).all()

    # Get blocked times
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    blocked = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        or_(
            BlockedTime.user_id == target_user_id,
            BlockedTime.applies_to_all_users == True
        ),
        BlockedTime.start_datetime <= end_dt,
        BlockedTime.end_datetime >= start_dt
    ).all()

    # Get existing appointments
    appointments = db.query(Appointment).filter(
        Appointment.assigned_user_id == target_user_id,
        Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    ).all()

    return {
        "availability": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week.value if s.day_of_week else None,
                "specific_date": s.specific_date.isoformat() if s.specific_date else None,
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "priority": s.priority.value if s.priority else "standard",
                "is_recurring": s.is_recurring
            }
            for s in slots
        ],
        "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "start": b.start_datetime.isoformat(),
                "end": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "block_type": b.block_type
            }
            for b in blocked
        ],
        "existing_appointments": [
            {
                "id": a.id,
                "title": a.title,
                "start": a.scheduled_start.isoformat(),
                "end": a.scheduled_end.isoformat(),
                "status": a.status.value if a.status else "booked"
            }
            for a in appointments
        ]
    }


@router.post("/availability/slots")
async def create_availability_slot(
    slot_data: AvailabilitySlotCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a custom availability slot"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        raise HTTPException(status_code=400, detail="Please create scheduler config first")

    # Parse times
    try:
        start_time = datetime.strptime(slot_data.start_time, "%H:%M").time()
        end_time = datetime.strptime(slot_data.end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    # Parse day of week
    day_of_week = None
    if slot_data.day_of_week:
        try:
            day_of_week = DayOfWeek(slot_data.day_of_week.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid day of week")

    # Parse priority
    priority = SlotPriority.STANDARD
    if slot_data.priority:
        try:
            priority = SlotPriority(slot_data.priority.lower())
        except ValueError:
            pass

    slot = AvailabilitySlot(
        config_id=config.id,
        user_id=user.id,
        day_of_week=day_of_week,
        specific_date=slot_data.specific_date,
        start_time=start_time,
        end_time=end_time,
        priority=priority,
        is_recurring=slot_data.is_recurring,
        allowed_meeting_types=slot_data.allowed_meeting_types,
        max_bookings=slot_data.max_bookings
    )

    db.add(slot)
    db.commit()
    db.refresh(slot)

    return {"message": "Availability slot created", "slot_id": slot.id}


@router.delete("/availability/slots/{slot_id}")
async def delete_availability_slot(
    slot_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete an availability slot"""
    user = await get_current_user(request, db)

    AvailabilitySlot = _models['AvailabilitySlot']

    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.user_id == user.id
    ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    db.delete(slot)
    db.commit()

    return {"message": "Slot deleted"}


# ============================================================================
# APPOINTMENT ENDPOINTS
# ============================================================================

@router.get("/appointments")
async def list_appointments(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List appointments with filters - includes both Appointment and ScheduledAppointment tables"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    # Query main Appointment table
    query = db.query(Appointment).filter(
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    )

    if start_date:
        query = query.filter(Appointment.scheduled_start >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(Appointment.scheduled_start <= datetime.combine(end_date, time.max))

    if status:
        try:
            status_enum = AppointmentStatus(status)
            query = query.filter(Appointment.status == status_enum)
        except ValueError:
            pass

    if lead_id:
        query = query.filter(Appointment.lead_id == lead_id)

    if loan_id:
        query = query.filter(Appointment.loan_id == loan_id)

    appointments = query.order_by(Appointment.scheduled_start.desc()).offset(offset).limit(limit).all()

    # Convert main appointments to response format
    result_appointments = [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "meeting_type": a.meeting_type.value if a.meeting_type else None,
            "meeting_mode": a.meeting_mode.value if a.meeting_mode else None,
            "scheduled_start": a.scheduled_start.isoformat(),
            "scheduled_end": a.scheduled_end.isoformat(),
            "duration_minutes": a.duration_minutes,
            "status": a.status.value if a.status else None,
            "attendee_name": a.attendee_name,
            "attendee_email": a.attendee_email,
            "video_link": a.video_link,
            "lead_id": a.lead_id,
            "loan_id": a.loan_id,
            "booked_by_ai": a.booked_by_ai,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in appointments
    ]

    # Also query ScheduledAppointment table (AI-booked appointments)
    try:
        from services.smart_scheduler_service import ScheduledAppointment

        ai_query = db.query(ScheduledAppointment).filter(
            ScheduledAppointment.loan_officer_id == user.id
        )

        if start_date:
            ai_query = ai_query.filter(ScheduledAppointment.start_time >= datetime.combine(start_date, time.min))

        if end_date:
            ai_query = ai_query.filter(ScheduledAppointment.start_time <= datetime.combine(end_date, time.max))

        if status:
            ai_query = ai_query.filter(ScheduledAppointment.status == status)

        ai_appointments = ai_query.order_by(ScheduledAppointment.start_time.desc()).all()

        # Convert AI appointments to same response format
        for a in ai_appointments:
            result_appointments.append({
                "id": f"ai-{a.id}",
                "appointment_id": a.appointment_id,
                "title": f"Appointment with {a.contact_name}",
                "description": a.notes,
                "meeting_type": a.appointment_type,
                "meeting_mode": "PHONE",
                "scheduled_start": a.start_time.isoformat() if a.start_time else None,
                "scheduled_end": a.end_time.isoformat() if a.end_time else None,
                "start_time": a.start_time.isoformat() if a.start_time else None,
                "end_time": a.end_time.isoformat() if a.end_time else None,
                "duration_minutes": a.duration_minutes,
                "status": a.status.upper() if a.status else "BOOKED",
                "attendee_name": a.contact_name,
                "contact_name": a.contact_name,
                "attendee_email": a.contact_email,
                "contact_email": a.contact_email,
                "contact_phone": a.contact_phone,
                "video_link": a.meeting_link,
                "lead_id": a.contact_id,
                "loan_id": None,
                "booked_by_ai": True,
                "booked_via": a.booked_via,
                "created_at": a.created_at.isoformat() if a.created_at else None
            })
    except Exception as e:
        logger.warning(f"Could not fetch ScheduledAppointments: {e}")

    # Sort combined results by scheduled_start
    result_appointments.sort(
        key=lambda x: x.get('scheduled_start') or x.get('start_time') or '',
        reverse=True
    )

    total = len(result_appointments)

    return {
        "appointments": result_appointments,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get appointment details"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {
        "appointment": {
            "id": appointment.id,
            "appointment_type_id": appointment.appointment_type_id,
            "title": appointment.title,
            "description": appointment.description,
            "meeting_type": appointment.meeting_type.value if appointment.meeting_type else None,
            "meeting_mode": appointment.meeting_mode.value if appointment.meeting_mode else None,
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
            "duration_minutes": appointment.duration_minutes,
            "timezone": appointment.timezone,
            "location": appointment.location,
            "video_link": appointment.video_link,
            "phone_number": appointment.phone_number,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
            "attendee_phone": appointment.attendee_phone,
            "attendee_notes": appointment.attendee_notes,
            "intake_responses": appointment.intake_responses,
            "status": appointment.status.value if appointment.status else None,
            "lead_id": appointment.lead_id,
            "loan_id": appointment.loan_id,
            "contact_id": appointment.contact_id,
            "assigned_user_id": appointment.assigned_user_id,
            "booked_by_ai": appointment.booked_by_ai,
            "ai_booking_context": appointment.ai_booking_context,
            "internal_notes": appointment.internal_notes,
            "meeting_notes": appointment.meeting_notes,
            "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
            "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None
        }
    }


@router.post("/appointments")
async def create_appointment(
    appt_data: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']

    # Calculate end time
    scheduled_end = appt_data.scheduled_start + timedelta(minutes=appt_data.duration_minutes)

    # Parse enums
    meeting_type = MeetingType.CUSTOM
    if appt_data.meeting_type:
        try:
            meeting_type = MeetingType(appt_data.meeting_type)
        except ValueError:
            pass

    meeting_mode = MeetingMode.VIDEO
    if appt_data.meeting_mode:
        try:
            meeting_mode = MeetingMode(appt_data.meeting_mode)
        except ValueError:
            pass

    appointment = Appointment(
        appointment_type_id=appt_data.appointment_type_id,
        assigned_user_id=appt_data.assigned_user_id or user.id,
        created_by_user_id=user.id,
        lead_id=appt_data.lead_id,
        loan_id=appt_data.loan_id,
        contact_id=appt_data.contact_id,
        title=appt_data.title,
        description=appt_data.description,
        meeting_type=meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=appt_data.scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=appt_data.duration_minutes,
        timezone=appt_data.timezone,
        attendee_name=appt_data.attendee_name,
        attendee_email=appt_data.attendee_email,
        attendee_phone=appt_data.attendee_phone,
        attendee_notes=appt_data.attendee_notes,
        intake_responses=appt_data.intake_responses,
        status=AppointmentStatus.BOOKED,
        booked_by_ai=appt_data.booked_by_ai,
        ai_booking_context=appt_data.ai_booking_context
    )

    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    logger.info(f"Appointment created: {appointment.id} by user {user.id}")

    # Send confirmation email if attendee email is provided
    email_sent = False
    email_error = None
    if appt_data.attendee_email:
        try:
            # Format date and time for email
            appointment_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
            appointment_time = appointment.scheduled_start.strftime("%I:%M %p")
            duration_str = f"{appointment.duration_minutes} minutes"

            # Get meeting mode display name
            meeting_mode_str = "Phone Call"
            if appointment.meeting_mode:
                mode_display = {
                    "VIDEO": "Video Call",
                    "PHONE": "Phone Call",
                    "IN_PERSON": "In Person",
                    "SCREEN_SHARE": "Screen Share"
                }
                meeting_mode_str = mode_display.get(appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode), "Phone Call")

            # Get team member info
            team_member_name = None
            team_member_email = None
            User = _models.get('User')
            if appointment.assigned_user_id and User:
                assigned_user = db.query(User).filter(User.id == appointment.assigned_user_id).first()
                if assigned_user:
                    team_member_name = assigned_user.first_name
                    if assigned_user.last_name:
                        team_member_name += f" {assigned_user.last_name}"
                    team_member_email = assigned_user.email

            # Get video link if this is a video call
            video_link = None
            if appointment.video_link:
                video_link = appointment.video_link

            logger.info(f"Sending confirmation email to {appt_data.attendee_email}")
            # Send confirmation email to attendee (borrower) with calendar invite
            email_result = send_appointment_confirmation_email(
                attendee_email=appt_data.attendee_email,
                attendee_name=appt_data.attendee_name or "there",
                appointment_title=appointment.title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                team_member_name=team_member_name,
                team_member_email=team_member_email,
                video_link=video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes
            )

            email_sent = email_result.get("success", False)
            if not email_sent:
                email_error = email_result.get("error", "Unknown email error")
                logger.warning(f"Email send failed for {appt_data.attendee_email}: {email_error}")

                # Fallback: try sending via Salesforce if SendGrid failed
                try:
                    from services.salesforce.email_sync_service import SalesforceEmailSyncService
                    from salesforce_integration_models import IntegrationProfile
                    sf_email_service = SalesforceEmailSyncService()
                    # Find user's active SF integration
                    sf_profile = db.query(IntegrationProfile).filter(
                        IntegrationProfile.user_id == user.id,
                        IntegrationProfile.provider == "salesforce",
                        IntegrationProfile.is_active == True
                    ).first()
                    if sf_profile:
                        sf_html = (
                            f"<p>Hi {appt_data.attendee_name or 'there'},</p>"
                            f"<p>Your appointment has been confirmed!</p>"
                            f"<p><strong>Date:</strong> {appointment_date}<br>"
                            f"<strong>Time:</strong> {appointment_time}<br>"
                            f"<strong>Duration:</strong> {duration_str}<br>"
                            f"<strong>Meeting Type:</strong> {meeting_mode_str}</p>"
                            + (f"<p><strong>With:</strong> {team_member_name}</p>" if team_member_name else "")
                            + (f"<p><a href='{video_link}'>Join Video Call</a></p>" if video_link else "")
                            + "<p>We'll send you a reminder before your appointment.</p>"
                        )
                        sf_result = await sf_email_service.send_email_via_salesforce(
                            db=db,
                            integration_profile_id=sf_profile.id,
                            to_email=appt_data.attendee_email,
                            subject=f"Appointment Confirmed: {appointment.title}",
                            html_body=sf_html
                        )
                        if sf_result.get("success"):
                            email_sent = True
                            email_error = None
                            logger.info(f"Appointment email sent via Salesforce to {appt_data.attendee_email}")
                        else:
                            logger.warning(f"Salesforce email fallback also failed: {sf_result.get('message')}")
                    else:
                        logger.info("No active Salesforce integration for appointment email fallback")
                except Exception as sf_err:
                    logger.warning(f"Salesforce email fallback error: {sf_err}")

            # Send notification email to team member (loan officer) with calendar invite
            if team_member_email:
                try:
                    team_result = send_team_member_notification_email(
                        team_member_email=team_member_email,
                        team_member_name=team_member_name or "Team Member",
                        attendee_name=appt_data.attendee_name or "Client",
                        attendee_email=appt_data.attendee_email or "",
                        attendee_phone=appt_data.attendee_phone or "",
                        appointment_title=appointment.title,
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        duration=duration_str,
                        meeting_mode=meeting_mode_str,
                        video_link=video_link,
                        scheduled_start=appointment.scheduled_start,
                        duration_minutes=appointment.duration_minutes
                    )
                    if not team_result:
                        logger.warning(f"Failed to send team member notification via SendGrid")
                        # Fallback: try Salesforce for team member notification too
                        try:
                            from services.salesforce.email_sync_service import SalesforceEmailSyncService
                            from salesforce_integration_models import IntegrationProfile
                            sf_svc = SalesforceEmailSyncService()
                            sf_prof = db.query(IntegrationProfile).filter(
                                IntegrationProfile.user_id == user.id,
                                IntegrationProfile.provider == "salesforce",
                                IntegrationProfile.is_active == True
                            ).first()
                            if sf_prof:
                                tm_subject = f"New Appointment: {appointment.title}"
                                tm_body = f"<p>New appointment with {appt_data.attendee_name or 'Client'} on {appointment_date} at {appointment_time} ({duration_str}).</p>"
                                sf_tm_result = await sf_svc.send_email_via_salesforce(
                                    db=db, integration_profile_id=sf_prof.id,
                                    to_email=team_member_email, subject=tm_subject, html_body=tm_body
                                )
                                if sf_tm_result.get("success"):
                                    logger.info(f"Team member notification sent via Salesforce to {team_member_email}")
                        except Exception as sf_tm_err:
                            logger.warning(f"SF fallback for team member email failed: {sf_tm_err}")
                    else:
                        logger.info(f"Team member notification sent to {team_member_email}")
                except Exception as team_email_error:
                    logger.error(f"Error sending team member notification: {team_email_error}")
        except Exception as e:
            email_error = str(e)
            logger.error(f"Error sending confirmation email: {e}")

    # Auto-create calendar event in team member's Outlook calendar
    calendar_event_created = False
    outlook_event_id = None

    # Get video_link from appointment (set earlier in the flow)
    calendar_video_link = appointment.video_link if appointment.video_link else None

    # Get meeting mode string for calendar event
    calendar_meeting_mode = "Phone Call"
    if appointment.meeting_mode:
        mode_display_map = {
            "VIDEO": "Video Call",
            "PHONE": "Phone Call",
            "IN_PERSON": "In Person",
            "SCREEN_SHARE": "Screen Share"
        }
        mode_val = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
        calendar_meeting_mode = mode_display_map.get(mode_val, "Phone Call")

    if appointment.assigned_user_id:
        try:
            # Build event description
            event_description = f"""
            <h3>Client Meeting</h3>
            <p><strong>Client:</strong> {appt_data.attendee_name or 'Not specified'}</p>
            <p><strong>Email:</strong> {appt_data.attendee_email or 'Not specified'}</p>
            <p><strong>Phone:</strong> {appt_data.attendee_phone or 'Not specified'}</p>
            <p><strong>Meeting Type:</strong> {calendar_meeting_mode}</p>
            """
            if appointment.description:
                event_description += f"<p><strong>Notes:</strong> {appointment.description}</p>"
            if calendar_video_link:
                event_description += f"<p><strong>Video Link:</strong> <a href='{calendar_video_link}'>{calendar_video_link}</a></p>"

            # Create calendar event via Microsoft Graph
            calendar_result: CalendarResult = await create_event_via_graph(
                user_id=appointment.assigned_user_id,
                subject=f"Meeting: {appt_data.attendee_name or 'Client'} - {appointment.title}",
                start=appointment.scheduled_start,
                end=appointment.scheduled_end,
                db=db,
                attendees=[appt_data.attendee_email] if appt_data.attendee_email else None,
                location=calendar_video_link if calendar_video_link else None,
                add_teams_link=False,  # Don't add Teams link since we may already have a video link
                body=event_description
            )

            if calendar_result.success:
                calendar_event_created = True
                outlook_event_id = calendar_result.event_id
                # Store the event ID in the appointment for future updates/deletions
                appointment.outlook_event_id = outlook_event_id
                db.commit()
                logger.info(f"Outlook calendar event created for appointment {appointment.id}: {outlook_event_id}")
            else:
                logger.warning(f"Could not create Outlook calendar event: {calendar_result.error}")

        except Exception as cal_error:
            logger.error(f"Error creating Outlook calendar event: {cal_error}")

    return {
        "message": "Appointment created",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "email_sent": email_sent,
        "email_error": email_error,
        "calendar_event_created": calendar_event_created,
        "outlook_event_id": outlook_event_id
    }


@router.put("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: int,
    appt_data: AppointmentUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment and send notification emails/SMS"""
    user = await get_current_user(request, db)

    Appointment = _models['Appointment']
    User = _models['User']

    # First try to find the appointment
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Check permission - allow if user is admin, assigned to the appointment, or created it
    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    is_admin = user_role.lower() in ['admin', 'leadership', 'management'] or user.id == 1
    is_owner = (
        appointment.assigned_user_id == user.id or
        appointment.created_by_user_id == user.id
    )

    if not is_admin and not is_owner:
        logger.warning(f"User {user.id} attempted to update appointment {appointment_id} without permission")
        raise HTTPException(status_code=403, detail="You don't have permission to update this appointment")

    update_fields = appt_data.model_dump(exclude_unset=True)
    is_cancellation = False
    is_reschedule = False
    send_notification = update_fields.pop('send_notification', True)  # Remove from fields, default to True

    # Store OLD date/time before any updates for comparison
    old_date = None
    old_time = None
    tz = pytz.timezone('America/Chicago')
    if appointment.scheduled_start:
        old_local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
        old_date = old_local_start.strftime('%B %d, %Y')
        old_time = old_local_start.strftime('%I:%M %p %Z')

    # Handle status changes
    if "status" in update_fields:
        try:
            new_status = AppointmentStatus(update_fields["status"])
            update_fields["status"] = new_status
            update_fields["status_changed_at"] = datetime.utcnow()
            update_fields["status_changed_by"] = user.id

            if new_status == AppointmentStatus.COMPLETED:
                update_fields["completed_at"] = datetime.utcnow()
            elif new_status == AppointmentStatus.NO_SHOW:
                update_fields["no_show_at"] = datetime.utcnow()
            elif new_status == AppointmentStatus.CANCELLED:
                update_fields["cancelled_at"] = datetime.utcnow()
                is_cancellation = True
        except ValueError:
            del update_fields["status"]

    # Handle meeting mode
    if "meeting_mode" in update_fields:
        try:
            update_fields["meeting_mode"] = MeetingMode(update_fields["meeting_mode"])
        except ValueError:
            del update_fields["meeting_mode"]

    # Handle rescheduling - check if date/time changed
    if "scheduled_start" in update_fields:
        new_start = update_fields["scheduled_start"]
        # Check if scheduled_end was also provided, otherwise calculate it
        if "scheduled_end" in update_fields:
            # Use the provided scheduled_end
            pass
        else:
            # Calculate from duration
            duration = appt_data.duration_minutes or appointment.duration_minutes or 30
            update_fields["scheduled_end"] = new_start + timedelta(minutes=duration)
        update_fields["reschedule_count"] = (appointment.reschedule_count or 0) + 1
        is_reschedule = True

    # Apply all updates
    for field, value in update_fields.items():
        if hasattr(appointment, field):
            setattr(appointment, field, value)

    db.commit()
    db.refresh(appointment)

    # Get updated appointment details for notifications
    attendee_email = appointment.attendee_email
    attendee_name = appointment.attendee_name or 'Valued Client'
    attendee_phone = getattr(appointment, 'attendee_phone', None)
    appointment_title = appointment.title or 'Appointment'
    duration_minutes = appointment.duration_minutes or 30
    duration_str = f"{duration_minutes} minutes" if duration_minutes < 60 else f"{duration_minutes // 60} hour{'s' if duration_minutes >= 120 else ''}"
    meeting_mode = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode or 'PHONE')
    video_link = getattr(appointment, 'video_link', None)

    # Format NEW date and time for emails
    new_date = 'TBD'
    new_time = 'TBD'
    if appointment.scheduled_start:
        new_local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
        new_date = new_local_start.strftime('%B %d, %Y')
        new_time = new_local_start.strftime('%I:%M %p %Z')

    # Get assigned team member info
    team_member = None
    team_member_name = None
    team_member_email = None
    if appointment.assigned_user_id:
        team_member = db.query(User).filter(User.id == appointment.assigned_user_id).first()
        if team_member:
            team_member_name = team_member.full_name or team_member.email
            team_member_email = team_member.email

    # Send notifications
    emails_sent = []
    sms_sent = []

    if is_cancellation and send_notification:
        logger.info(f"Appointment {appointment_id} cancelled via PUT, sending cancellation notifications")

        if attendee_email:
            try:
                success = send_appointment_cancellation_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    team_member_name=team_member_name,
                    cancellation_reason=None
                )
                if success:
                    emails_sent.append(attendee_email)
            except Exception as e:
                logger.error(f"Failed to send attendee cancellation email: {e}")

        if team_member_email and team_member and team_member.id != user.id:
            try:
                success = send_team_member_cancellation_email(
                    team_member_email=team_member_email,
                    team_member_name=team_member_name,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    cancellation_reason=None,
                    cancelled_by=user.full_name or user.email
                )
                if success:
                    emails_sent.append(team_member_email)
            except Exception as e:
                logger.error(f"Failed to send team member cancellation email: {e}")

    elif send_notification and (is_reschedule or update_fields):
        # Send update notifications for reschedule or other updates
        logger.info(f"Appointment {appointment_id} updated, sending update notifications")

        # Send update email to attendee
        if attendee_email:
            try:
                result = send_appointment_update_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    duration=duration_str,
                    meeting_mode=meeting_mode.replace('_', ' ').title(),
                    team_member_name=team_member_name,
                    team_member_email=team_member_email,
                    video_link=video_link,
                    scheduled_start=appointment.scheduled_start,
                    duration_minutes=duration_minutes,
                    old_date=old_date if is_reschedule else None,
                    old_time=old_time if is_reschedule else None
                )
                if result.get("success"):
                    emails_sent.append(attendee_email)
            except Exception as e:
                logger.error(f"Failed to send attendee update email: {e}")

        # Send update SMS to attendee
        if attendee_phone:
            try:
                success = send_appointment_update_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=attendee_name,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    team_member_name=team_member_name
                )
                if success:
                    sms_sent.append(attendee_phone)
            except Exception as e:
                logger.error(f"Failed to send attendee update SMS: {e}")

    return {
        "message": "Appointment updated",
        "appointment_id": appointment_id,
        "emails_sent": emails_sent,
        "sms_sent": sms_sent,
        "is_reschedule": is_reschedule,
        "new_date": new_date,
        "new_time": new_time
    }


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = None

@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    cancel_data: Optional[CancelAppointmentRequest] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """Cancel an appointment and send cancellation notifications"""
    user = await get_current_user(request, db)
    reason = cancel_data.reason if cancel_data else None

    Appointment = _models['Appointment']
    User = _models['User']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Store appointment details before cancellation for email notifications
    attendee_email = getattr(appointment, 'attendee_email', None)
    attendee_name = getattr(appointment, 'attendee_name', None) or 'Valued Client'
    appointment_title = appointment.title or 'Appointment'

    # Format date and time for emails
    if appointment.scheduled_start:
        tz = pytz.timezone('America/Chicago')
        local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
        appointment_date = local_start.strftime('%B %d, %Y')
        appointment_time = local_start.strftime('%I:%M %p %Z')
    else:
        appointment_date = 'TBD'
        appointment_time = 'TBD'

    # Get assigned team member info
    team_member = None
    team_member_name = None
    team_member_email = None
    if appointment.assigned_user_id:
        team_member = db.query(User).filter(User.id == appointment.assigned_user_id).first()
        if team_member:
            team_member_name = team_member.full_name or team_member.email
            team_member_email = team_member.email

    # Cancel the appointment
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.utcnow()
    appointment.cancellation_reason = reason
    appointment.status_changed_by = user.id
    appointment.status_changed_at = datetime.utcnow()

    db.commit()

    logger.info(f"Appointment {appointment_id} cancelled by user {user.id}")

    # Send cancellation emails
    emails_sent = []

    # Send to attendee if they have an email
    if attendee_email:
        try:
            success = send_appointment_cancellation_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name,
                cancellation_reason=reason
            )
            if success:
                emails_sent.append(attendee_email)
        except Exception as e:
            logger.error(f"Failed to send attendee cancellation email: {e}")

    # Send to assigned team member if different from canceller
    if team_member_email and team_member and team_member.id != user.id:
        try:
            success = send_team_member_cancellation_email(
                team_member_email=team_member_email,
                team_member_name=team_member_name,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                cancellation_reason=reason,
                cancelled_by=user.full_name or user.email
            )
            if success:
                emails_sent.append(team_member_email)
        except Exception as e:
            logger.error(f"Failed to send team member cancellation email: {e}")

    return {
        "message": "Appointment cancelled",
        "emails_sent": emails_sent
    }


# ============================================================================
# BLOCKED TIME ENDPOINTS
# ============================================================================

@router.get("/blocked-times")
async def list_blocked_times(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """List blocked time periods"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    query = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        or_(
            BlockedTime.user_id == user.id,
            BlockedTime.applies_to_all_users == True
        )
    )

    if start_date:
        query = query.filter(BlockedTime.end_datetime >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(BlockedTime.start_datetime <= datetime.combine(end_date, time.max))

    blocked = query.order_by(BlockedTime.start_datetime).all()

    return {
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "block_type": b.block_type,
                "start_datetime": b.start_datetime.isoformat(),
                "end_datetime": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "is_recurring": b.is_recurring,
                "recurrence_pattern": b.recurrence_pattern,
                "applies_to_all_users": b.applies_to_all_users
            }
            for b in blocked
        ]
    }


@router.post("/blocked-times")
async def create_blocked_time(
    block_data: BlockedTimeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a blocked time period"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    blocked = BlockedTime(
        user_id=user.id,
        title=block_data.title,
        description=block_data.description,
        block_type=block_data.block_type,
        start_datetime=block_data.start_datetime,
        end_datetime=block_data.end_datetime,
        all_day=block_data.all_day,
        is_recurring=block_data.is_recurring,
        recurrence_pattern=block_data.recurrence_pattern,
        applies_to_all_users=block_data.applies_to_all_users,
        created_by_id=user.id
    )

    db.add(blocked)
    db.commit()
    db.refresh(blocked)

    return {"message": "Blocked time created", "blocked_time_id": blocked.id}


@router.delete("/blocked-times/{block_id}")
async def delete_blocked_time(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a blocked time period"""
    user = await get_current_user(request, db)

    BlockedTime = _models['BlockedTime']

    blocked = db.query(BlockedTime).filter(
        BlockedTime.id == block_id,
        BlockedTime.user_id == user.id
    ).first()

    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked time not found")

    db.delete(blocked)
    db.commit()

    return {"message": "Blocked time deleted"}


# ============================================================================
# BOOKING LINK ENDPOINTS
# ============================================================================

@router.get("/booking-links/all")
async def list_all_booking_links(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all active booking links for admin use (calendar assignment)"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']
    User = _models.get('User')

    links = db.query(BookingLink).filter(
        BookingLink.is_active == True
    ).all()

    result = []
    for link in links:
        link_data = {
            "id": link.id,
            "slug": link.slug,
            "link_name": link.link_name,
            "description": link.description,
            "url": f"/book/{link.slug}",
            "is_public": link.is_public,
            "user_id": link.user_id,
            "owner_name": None,
            "created_at": link.created_at.isoformat() if link.created_at else None
        }
        if link.user_id and User:
            owner = db.query(User).filter(User.id == link.user_id).first()
            if owner:
                link_data["owner_name"] = owner.full_name
        result.append(link_data)

    return {"booking_links": result}


@router.get("/booking-links")
async def list_booking_links(
    request: Request,
    db: Session = Depends(get_db)
):
    """List user's booking links"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    links = db.query(BookingLink).filter(
        BookingLink.user_id == user.id,
        BookingLink.is_active == True
    ).all()

    return {
        "booking_links": [
            {
                "id": link.id,
                "slug": link.slug,
                "link_name": link.link_name,
                "description": link.description,
                "url": f"/book/{link.slug}",
                "is_public": link.is_public,
                "view_count": link.view_count,
                "booking_count": link.booking_count,
                "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
                "created_at": link.created_at.isoformat() if link.created_at else None
            }
            for link in links
        ]
    }


@router.post("/booking-links")
async def create_booking_link(
    link_data: BookingLinkCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a booking link"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    # Check for duplicate slug
    existing = db.query(BookingLink).filter(BookingLink.slug == link_data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already in use")

    # Parse routing strategy
    routing_strategy = RoutingStrategy.RELATIONSHIP
    if link_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(link_data.routing_strategy)
        except ValueError:
            pass

    link = BookingLink(
        user_id=user.id,
        slug=link_data.slug,
        link_name=link_data.link_name,
        description=link_data.description,
        appointment_type_ids=link_data.appointment_type_ids,
        single_appointment_type_id=link_data.single_appointment_type_id,
        is_public=link_data.is_public,
        custom_title=link_data.custom_title,
        custom_description=link_data.custom_description,
        routing_strategy=routing_strategy,
        assigned_users=link_data.assigned_users
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "message": "Booking link created",
        "link_id": link.id,
        "url": f"/book/{link.slug}"
    }


@router.delete("/booking-links/{link_id}")
async def delete_booking_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a booking link"""
    user = await get_current_user(request, db)

    BookingLink = _models['BookingLink']

    link = db.query(BookingLink).filter(
        BookingLink.id == link_id,
        BookingLink.user_id == user.id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    link.is_active = False
    db.commit()

    return {"message": "Booking link deactivated"}


# ============================================================================
# SLOT AVAILABILITY ENGINE
# ============================================================================

@router.post("/available-slots")
async def get_available_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get available time slots for booking.
    This is the core slot calculation engine.
    """
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    # Determine which users to check
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    available_slots = []

    for target_user_id in user_ids:
        # Get user's config
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == target_user_id
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        max_per_day = config.max_meetings_per_day if config else 8
        min_notice = config.min_notice_hours if config else 2

        # Get blocked times for this user
        start_dt = datetime.combine(slot_request.start_date, time.min)
        end_dt = datetime.combine(slot_request.end_date, time.max)

        blocked_times = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == target_user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        ).all()

        # Get existing appointments
        existing_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == target_user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        ).all()

        # Generate slots for each day
        current_date = slot_request.start_date
        now = datetime.utcnow()
        min_booking_time = now + timedelta(hours=min_notice)

        while current_date <= slot_request.end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            # Count appointments for this day
            day_appts = [a for a in existing_appts
                        if a.scheduled_start.date() == current_date]
            if len(day_appts) >= max_per_day:
                current_date += timedelta(days=1)
                continue

            # Parse working hours
            try:
                start_time = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                end_time = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            # Generate slots at 30-minute intervals
            slot_start = datetime.combine(current_date, start_time)
            day_end = datetime.combine(current_date, end_time)

            while slot_start + timedelta(minutes=slot_request.duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=slot_request.duration_minutes)

                # Check if slot is in the past or within min notice
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check for conflicts with blocked time
                blocked = False
                for bt in blocked_times:
                    if (slot_start < bt.end_datetime and slot_end > bt.start_datetime):
                        blocked = True
                        break

                if blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check for conflicts with existing appointments (including buffers)
                conflict = False
                for appt in existing_appts:
                    appt_start_with_buffer = appt.scheduled_start - timedelta(minutes=buffer_before)
                    appt_end_with_buffer = appt.scheduled_end + timedelta(minutes=buffer_after)

                    if (slot_start < appt_end_with_buffer and slot_end > appt_start_with_buffer):
                        conflict = True
                        break

                if not conflict:
                    available_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "user_id": target_user_id,
                        "date": current_date.isoformat(),
                        "day": day_name
                    })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Sort by datetime
    available_slots.sort(key=lambda x: x["start"])

    return {
        "available_slots": available_slots,
        "total_slots": len(available_slots),
        "request": {
            "start_date": slot_request.start_date.isoformat(),
            "end_date": slot_request.end_date.isoformat(),
            "duration_minutes": slot_request.duration_minutes,
            "user_ids": user_ids
        }
    }


# ============================================================================
# AI SLOT RECOMMENDATIONS
# ============================================================================

@router.post("/ai-recommend-slots")
async def ai_recommend_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get AI-recommended time slots based on:
    - User preferences
    - Lead/loan context
    - Historical patterns
    - Optimal meeting times
    """
    user = await get_current_user(request, db)

    # First get available slots
    available_response = await get_available_slots(slot_request, request, db)
    available_slots = available_response.get("available_slots", [])

    if not available_slots:
        return {
            "recommendations": [],
            "message": "No available slots found in the requested range"
        }

    # Score each slot
    recommendations = []

    for slot in available_slots[:20]:  # Limit to first 20 for performance
        score = 1.0
        reasons = []

        # Parse the slot time
        slot_dt = datetime.fromisoformat(slot["start"])
        hour = slot_dt.hour
        day_name = slot["day"]

        # Score based on time of day (prefer mid-morning and early afternoon)
        if 9 <= hour <= 11:
            score += 0.3
            reasons.append("Optimal morning time slot")
        elif 14 <= hour <= 16:
            score += 0.2
            reasons.append("Good afternoon time slot")
        elif hour < 9 or hour > 17:
            score -= 0.2
            reasons.append("Outside peak hours")

        # Score based on day of week
        if day_name in ["tuesday", "wednesday", "thursday"]:
            score += 0.1
            reasons.append("Mid-week availability")
        elif day_name == "monday":
            score -= 0.1
            reasons.append("Monday may have competing priorities")
        elif day_name == "friday":
            score -= 0.1
            reasons.append("Friday afternoon may have lower engagement")

        # Bonus for sooner availability
        days_from_now = (slot_dt.date() - datetime.now().date()).days
        if days_from_now <= 2:
            score += 0.2
            reasons.append("Soon availability - strike while hot")
        elif days_from_now > 7:
            score -= 0.1
            reasons.append("Further out - lead may cool")

        recommendations.append({
            "slot": slot,
            "score": round(score, 2),
            "reasons": reasons
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return {
        "recommendations": recommendations[:5],  # Top 5
        "total_available": len(available_slots)
    }


# ============================================================================
# PUBLIC BOOKING ENDPOINTS (No auth required)
# ============================================================================

@router.get("/public/book/{slug}")
async def get_public_booking_page(
    slug: str,
    db: Session = Depends(get_db)
):
    """Get public booking page data"""
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']
    User = _models.get('User')

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    # Auto-create booking link if it doesn't exist
    if not link:
        try:
            SchedulerConfig = _models['SchedulerConfig']

            if User:
                # Check if slug matches a user's slug (for microsite booking)
                target_user = db.query(User).filter(User.slug == slug).first()

                # Fallback: for demo slug, use admin user
                if not target_user and slug == "demo":
                    target_user = db.query(User).filter(User.is_admin == True).first()
                    if not target_user:
                        target_user = db.query(User).first()

                if target_user:
                    user_name = getattr(target_user, 'full_name', None) or getattr(target_user, 'name', 'Loan Officer')
                    first_name = user_name.split()[0] if user_name else 'Loan Officer'

                    # Get or create SchedulerConfig for this user
                    user_config = db.query(SchedulerConfig).filter(
                        SchedulerConfig.user_id == target_user.id
                    ).first()

                    if not user_config:
                        user_config = SchedulerConfig(
                            user_id=target_user.id,
                            config_name=f"{first_name}'s Schedule",
                            description=f"Availability settings for {user_name}",
                            timezone="America/New_York",
                            default_duration_minutes=30,
                            min_notice_hours=2,
                            max_advance_days=60,
                            is_active=True
                        )
                        db.add(user_config)
                        db.flush()

                    # Get or create appointment type for this user
                    user_type = db.query(AppointmentType).filter(
                        AppointmentType.config_id == user_config.id,
                        AppointmentType.is_active == True
                    ).first()

                    if not user_type:
                        type_key = f"{slug}_consultation" if slug != "demo" else "demo_consultation"

                        user_type = AppointmentType(
                            config_id=user_config.id,
                            type_name="Discovery Call" if slug != "demo" else "Product Demo",
                            type_key=type_key,
                            description=f"Schedule a call with {first_name}" if slug != "demo" else "Schedule a personalized demo of our platform",
                            default_duration_minutes=30,
                            allowed_durations=[15, 30, 45, 60],
                            meeting_type="consultation",
                            default_mode="phone",
                            color="#2563eb",
                            icon="phone",
                            is_public=True,
                            is_active=True,
                            requires_confirmation=False,
                            buffer_before_minutes=5,
                            buffer_after_minutes=5
                        )
                        db.add(user_type)
                        db.flush()

                    link = BookingLink(
                        user_id=target_user.id,
                        slug=slug,
                        link_name=f"Schedule with {first_name}" if slug != "demo" else "Schedule a Demo",
                        description=f"Book a call with {user_name}" if slug != "demo" else "Book a personalized demo of Perennia AI",
                        is_active=True,
                        is_public=True,
                        appointment_type_ids=[user_type.id],
                        custom_title=f"Schedule a Call" if slug != "demo" else "Schedule Your Demo",
                        custom_description=f"Choose a time that works for you to speak with {first_name}." if slug != "demo" else "See how Perennia AI can transform your mortgage operations."
                    )
                    db.add(link)
                    db.commit()
                    logger.info(f"Auto-created booking link for slug: {slug}")
        except Exception as e:
            logger.error(f"Error auto-creating booking link for {slug}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # Increment view count
    link.view_count += 1
    db.commit()

    # Get available appointment types
    appointment_types = []
    if link.single_appointment_type_id:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == link.single_appointment_type_id,
            AppointmentType.is_active == True
        ).first()
        if appt_type:
            appointment_types.append({
                "id": appt_type.id,
                "type_key": appt_type.type_key,
                "type_name": appt_type.type_name,
                "description": appt_type.description,
                "default_duration_minutes": appt_type.default_duration_minutes,
                "allowed_durations": appt_type.allowed_durations,
                "intake_questions": appt_type.intake_questions,
                "color": appt_type.color
            })
    elif link.appointment_type_ids:
        types = db.query(AppointmentType).filter(
            AppointmentType.id.in_(link.appointment_type_ids),
            AppointmentType.is_active == True
        ).all()
        for t in types:
            appointment_types.append({
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": t.allowed_durations,
                "intake_questions": t.intake_questions,
                "color": t.color
            })

    return {
        "booking_page": {
            "title": link.custom_title or link.link_name,
            "description": link.custom_description or link.description,
            "logo_url": link.custom_logo_url,
            "color": link.custom_color,
            "appointment_types": appointment_types
        }
    }


@router.get("/public/book/{slug}/slots")
async def get_public_available_slots(
    slug: str,
    appointment_type_id: int = Query(...),
    date: date = Query(..., description="Date to get slots for"),
    duration_minutes: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get available slots for public booking"""
    # Use same date for start and end (single day)
    start_date = date
    end_date = date
    BookingLink = _models['BookingLink']
    SchedulerConfig = _models['SchedulerConfig']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # Get user IDs to check
    user_ids = link.assigned_users if link.assigned_users else [link.user_id]

    all_slots = []

    for target_user_id in user_ids:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == target_user_id
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        min_notice = config.min_notice_hours if config else 2

        # Get blocked times
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        blocked_times = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == target_user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        ).all()

        # Get existing appointments
        existing_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == target_user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        ).all()

        # Generate slots
        current_date = start_date
        now = datetime.utcnow()
        min_booking_time = now + timedelta(hours=min_notice)

        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            try:
                start_time = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                end_time = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, start_time)
            day_end = datetime.combine(current_date, end_time)

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check conflicts
                blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )

                if not blocked:
                    conflict = any(
                        slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                        slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                        for appt in existing_appts
                    )

                    if not conflict:
                        all_slots.append({
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": current_date.isoformat()
                        })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Remove duplicates and sort
    unique_slots = list({s["start"]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x["start"])

    return {"available_slots": unique_slots}


@router.post("/public/book/{slug}/confirm")
async def confirm_public_booking(
    slug: str,
    booking_data: PublicBookingConfirmRequest,
    db: Session = Depends(get_db)
):
    """Confirm a public booking"""
    # Extract data from request body
    appointment_type_id = booking_data.appointment_type_id
    slot_start = booking_data.start_time
    duration_minutes = booking_data.duration_minutes
    attendee_name = booking_data.attendee_name
    attendee_email = booking_data.attendee_email
    attendee_phone = booking_data.attendee_phone
    intake_responses = {"notes": booking_data.notes} if booking_data.notes else {}
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']
    Appointment = _models['Appointment']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    appt_type = db.query(AppointmentType).filter(
        AppointmentType.id == appointment_type_id,
        AppointmentType.is_active == True
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    # Determine assigned user - use team_member_id if provided, otherwise link owner
    assigned_user_id = booking_data.team_member_id or link.user_id

    # Determine meeting mode from request or default to VIDEO
    meeting_mode = MeetingMode.VIDEO
    if booking_data.meeting_mode:
        mode_map = {"video": MeetingMode.VIDEO, "phone": MeetingMode.PHONE, "in_person": MeetingMode.IN_PERSON}
        meeting_mode = mode_map.get(booking_data.meeting_mode.lower(), MeetingMode.VIDEO)

    # Create appointment
    slot_end = slot_start + timedelta(minutes=duration_minutes)

    appointment = Appointment(
        appointment_type_id=appointment_type_id,
        assigned_user_id=assigned_user_id,
        title=f"{appt_type.type_name} with {attendee_name}",
        description=appt_type.description,
        meeting_type=appt_type.meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=slot_start,
        scheduled_end=slot_end,
        duration_minutes=duration_minutes,
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        intake_responses=intake_responses,
        status=AppointmentStatus.BOOKED,
        external_source="booking_link"
    )

    db.add(appointment)

    # Update link stats
    link.booking_count += 1
    link.current_bookings += 1
    link.last_booked_at = datetime.utcnow()

    # Create video meeting room if meeting mode is VIDEO
    video_link = None
    room_code = None
    if meeting_mode == MeetingMode.VIDEO:
        try:
            # Try to create a video meeting room
            VideoMeetingRoom = _models.get('VideoMeetingRoom')
            if VideoMeetingRoom:
                import secrets
                import string

                # Generate room code
                chars = string.ascii_uppercase + string.digits
                code = ''.join(secrets.choice(chars) for _ in range(9))
                room_code = f"MTG-{code[:3]}-{code[3:6]}-{code[6:]}"

                video_room = VideoMeetingRoom(
                    room_code=room_code,
                    room_name=f"Video Call - {attendee_name}",
                    room_description=f"Scheduled video call with {attendee_name}",
                    provider="internal",
                    host_user_id=assigned_user_id,
                    scheduled_start=slot_start,
                    scheduled_end=slot_end,
                    duration_minutes=duration_minutes,
                    status="scheduled",
                    waiting_room_enabled=True,
                    recording_enabled=True,
                    transcription_enabled=True,
                    ai_assistant_enabled=True,
                    meeting_type="scheduled_call",
                    created_by=assigned_user_id
                )
                db.add(video_room)
                db.flush()  # Get the video room ID

                # Update appointment with video link
                base_url = os.getenv("FRONTEND_URL", "https://perenniaai.com")
                video_link = f"{base_url}/meeting/{room_code}"
                appointment.video_link = video_link
                appointment.video_meeting_id = video_room.id

                logger.info(f"Created video meeting room {room_code} for appointment")
        except Exception as e:
            logger.warning(f"Could not create video meeting room: {e}")
            # Continue without video room - appointment still gets created

    db.commit()
    db.refresh(appointment)

    logger.info(f"Public booking confirmed: {appointment.id} via link {slug}")

    # Prepare confirmation details
    appointment_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
    appointment_time = appointment.scheduled_start.strftime("%I:%M %p")
    duration_str = f"{duration_minutes} minutes"

    # Get meeting mode display string
    meeting_mode_str = "Video Call"
    if meeting_mode == MeetingMode.PHONE:
        meeting_mode_str = "Phone Call"
    elif meeting_mode == MeetingMode.IN_PERSON:
        meeting_mode_str = "In Person"

    # Get team member name and email - prefer explicit parameter, then try to fetch from user
    team_member_name = booking_data.team_member_name
    team_member_email = None

    User = _models.get('User')
    if assigned_user_id and User:
        assigned_user = db.query(User).filter(User.id == assigned_user_id).first()
        if assigned_user:
            if not team_member_name:
                team_member_name = assigned_user.first_name
                if assigned_user.last_name:
                    team_member_name += f" {assigned_user.last_name}"
            team_member_email = assigned_user.email

    if not team_member_name and intake_responses and intake_responses.get("notes"):
        notes = intake_responses.get("notes", "")
        if "Appointment with:" in notes:
            team_member_name = notes.split("Appointment with:")[-1].strip()

    # Send email confirmation with calendar invite
    email_sent = False
    sms_sent = False

    if attendee_email:
        try:
            email_sent = send_appointment_confirmation_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment.title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                team_member_name=team_member_name,
                team_member_email=team_member_email,
                video_link=video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes
            )
            logger.info(f"Confirmation email sent to {attendee_email}, email_sent={email_sent}, video_link={video_link}")
        except Exception as e:
            logger.error(f"Error sending confirmation email: {e}")

    # Also send notification to team member
    if team_member_email:
        try:
            send_team_member_notification_email(
                team_member_email=team_member_email,
                team_member_name=team_member_name or "Team Member",
                attendee_name=attendee_name,
                attendee_email=attendee_email or "",
                attendee_phone=attendee_phone or "",
                appointment_title=appointment.title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                video_link=video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes
            )
            logger.info(f"Team member notification sent to {team_member_email}")
        except Exception as team_email_error:
            logger.error(f"Error sending team member notification: {team_email_error}")

    # Auto-create calendar event in team member's Outlook calendar
    calendar_event_created = False
    outlook_event_id = None
    if assigned_user_id:
        try:
            # Build event description
            event_description = f"""
            <h3>Client Meeting</h3>
            <p><strong>Client:</strong> {attendee_name or 'Not specified'}</p>
            <p><strong>Email:</strong> {attendee_email or 'Not specified'}</p>
            <p><strong>Phone:</strong> {attendee_phone or 'Not specified'}</p>
            <p><strong>Meeting Type:</strong> {meeting_mode_str}</p>
            """
            if appointment.description:
                event_description += f"<p><strong>Notes:</strong> {appointment.description}</p>"
            if video_link:
                event_description += f"<p><strong>Video Link:</strong> <a href='{video_link}'>{video_link}</a></p>"

            # Create calendar event via Microsoft Graph
            calendar_result: CalendarResult = await create_event_via_graph(
                user_id=assigned_user_id,
                subject=f"Meeting: {attendee_name or 'Client'} - {appointment.title}",
                start=appointment.scheduled_start,
                end=appointment.scheduled_end,
                db=db,
                attendees=[attendee_email] if attendee_email else None,
                location=video_link if video_link else None,
                add_teams_link=False,
                body=event_description
            )

            if calendar_result.success:
                calendar_event_created = True
                outlook_event_id = calendar_result.event_id
                # Store the event ID in the appointment for future updates/deletions
                appointment.outlook_event_id = outlook_event_id
                db.commit()
                logger.info(f"Outlook calendar event created for public booking {appointment.id}: {outlook_event_id}")
            else:
                logger.warning(f"Could not create Outlook calendar event for public booking: {calendar_result.error}")

        except Exception as cal_error:
            logger.error(f"Error creating Outlook calendar event for public booking: {cal_error}")

    if attendee_phone:
        try:
            sms_sent = send_appointment_confirmation_sms(
                attendee_phone=attendee_phone,
                attendee_name=attendee_name,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name
            )
        except Exception as e:
            logger.error(f"Error sending confirmation SMS: {e}")

    return {
        "message": "Appointment booked successfully",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "video_link": video_link,
        "room_code": room_code,
        "confirmation_details": {
            "title": appointment.title,
            "date": appointment_date,
            "time": appointment_time,
            "duration": duration_str,
            "meeting_mode": meeting_mode_str,
            "team_member": team_member_name
        },
        "notifications": {
            "email_sent": email_sent,
            "sms_sent": sms_sent,
            "calendar_event_created": calendar_event_created
        },
        "outlook_event_id": outlook_event_id
    }


# ============================================================================
# SEED DEFAULT APPOINTMENT TYPES
# ============================================================================

@router.post("/seed-defaults")
async def seed_default_appointment_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """Seed default appointment types for the user"""
    user = await get_current_user(request, db)

    SchedulerConfig = _models['SchedulerConfig']
    AppointmentType = _models['AppointmentType']

    # Get or create config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id
    ).first()

    if not config:
        config = SchedulerConfig(
            user_id=user.id,
            config_name=f"{user.email}'s Schedule",
            working_hours=DEFAULT_WORKING_HOURS
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    created_count = 0

    for default_type in DEFAULT_APPOINTMENT_TYPES:
        # Check if already exists
        existing = db.query(AppointmentType).filter(
            AppointmentType.config_id == config.id,
            AppointmentType.type_key == default_type["type_key"]
        ).first()

        if not existing:
            appt_type = AppointmentType(
                config_id=config.id,
                type_key=default_type["type_key"],
                type_name=default_type["type_name"],
                description=default_type["description"],
                meeting_type=default_type["meeting_type"],
                default_duration_minutes=default_type["default_duration_minutes"],
                allowed_durations=default_type["allowed_durations"],
                requires_loan_id=default_type["requires_loan_id"],
                requires_lead_id=default_type["requires_lead_id"],
                intake_questions=default_type["intake_questions"],
                color=default_type["color"],
                icon=default_type["icon"],
                is_public=True,
                public_slug=f"{user.id}-{default_type['type_key']}"
            )
            db.add(appt_type)
            created_count += 1

    db.commit()

    return {
        "message": f"Seeded {created_count} default appointment types",
        "config_id": config.id
    }


# ============================================================================
# MIGRATION ENDPOINT
# ============================================================================

@router.post("/migrate")
async def run_scheduler_migration(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create all scheduler tables if they don't exist.
    This is safe to call multiple times.
    """
    user = await get_current_user(request, db)

    try:
        # Get all model classes
        SchedulerConfig = _models['SchedulerConfig']
        AvailabilitySlot = _models['AvailabilitySlot']
        AppointmentType = _models['AppointmentType']
        Appointment = _models['Appointment']
        RoutingRule = _models['RoutingRule']
        BlockedTime = _models['BlockedTime']
        BookingLink = _models['BookingLink']
        AppointmentReminder = _models['AppointmentReminder']

        # Get the metadata from any model
        metadata = SchedulerConfig.__table__.metadata

        # Create all tables
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        existing_tables = inspector.get_table_names()

        tables_to_create = [
            'scheduler_configs',
            'availability_slots',
            'appointment_types',
            'scheduler_appointments',
            'scheduler_routing_rules',
            'scheduler_blocked_times',
            'scheduler_booking_links',
            'scheduler_reminders'
        ]

        created = []
        for table_name in tables_to_create:
            if table_name not in existing_tables:
                created.append(table_name)

        # Create tables
        metadata.create_all(bind=db.bind, checkfirst=True)

        # Add landing_page_settings column if it doesn't exist
        try:
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'scheduler_configs' AND column_name = 'landing_page_settings'
            """))
            if not result.fetchone():
                db.execute(text("ALTER TABLE scheduler_configs ADD COLUMN landing_page_settings JSONB DEFAULT '{}'::jsonb"))
                db.commit()
                logger.info("Added landing_page_settings column to scheduler_configs")
        except Exception as col_e:
            logger.warning(f"Could not add landing_page_settings column: {col_e}")

        logger.info(f"Scheduler migration complete. Created tables: {created}")

        # Ensure demo booking link exists
        demo_link = db.query(BookingLink).filter(BookingLink.slug == "demo").first()
        if not demo_link:
            # Create default appointment types first
            demo_type = db.query(AppointmentType).filter(AppointmentType.type_key == "demo_consultation").first()
            if not demo_type:
                demo_type = AppointmentType(
                    user_id=user.id,
                    type_name="Demo Consultation",
                    type_key="demo_consultation",
                    description="Schedule a demo of our mortgage production management platform",
                    default_duration_minutes=30,
                    allowed_durations=[15, 30, 45, 60],
                    meeting_type="consultation",
                    meeting_mode="video",
                    color="#667eea",
                    icon="calendar",
                    is_public=True,
                    is_active=True,
                    requires_confirmation=False,
                    buffer_before_minutes=5,
                    buffer_after_minutes=5
                )
                db.add(demo_type)
                db.flush()

            demo_link = BookingLink(
                user_id=user.id,
                slug="demo",
                link_name="Schedule a Demo",
                description="Book a personalized demo of Perennia AI - Intelligent Mortgage Production Manager",
                is_active=True,
                is_public=True,
                appointment_type_ids=[demo_type.id],
                custom_title="Schedule Your Demo",
                custom_description="See how Perennia AI can transform your mortgage operations with AI-powered automation.",
                routing_strategy="round_robin",
                max_bookings_per_day=10
            )
            db.add(demo_link)
            db.commit()
            logger.info("Created demo booking link")

        return {
            "message": "Scheduler migration complete",
            "created_tables": created,
            "existing_tables": [t for t in tables_to_create if t in existing_tables],
            "demo_link_exists": True
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")


# ============================================================================
# PUBLIC WEBSITE DEMO SCHEDULER ENDPOINT
# ============================================================================

@router.post("/public/available-slots")
async def get_website_demo_available_slots(
    request: PublicAvailableSlotsRequest,
    db: Session = Depends(get_db)
):
    """
    Get available slots for website demo scheduling.

    This endpoint looks up the calendar assignment for 'website_demo' purpose
    and returns available slots from the assigned user's calendar.

    Used by the public website demo scheduler.
    """
    from sqlalchemy import text

    try:
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Look up calendar assignment for website_demo purpose
    assignment_result = db.execute(text("""
        SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,
               u.full_name as user_name, u.email as user_email
        FROM calendar_assignments ca
        LEFT JOIN users u ON u.id = ca.assigned_user_id
        WHERE ca.purpose = 'website_demo' AND ca.is_active = true
        LIMIT 1
    """)).fetchone()

    if not assignment_result:
        # No assignment configured - return empty slots with helpful message
        logger.warning("No calendar assignment found for website_demo purpose")
        return {
            "available_slots": [],
            "message": "Website demo calendar not configured. Please assign a team member in Calendar Management.",
            "configured": False
        }

    assigned_user_id = assignment_result.assigned_user_id
    calendly_url = assignment_result.calendly_url
    booking_link_id = assignment_result.booking_link_id

    # If there's a booking link configured, use it
    if booking_link_id and _models:
        BookingLink = _models.get('BookingLink')
        if BookingLink:
            link = db.query(BookingLink).filter(
                BookingLink.id == booking_link_id,
                BookingLink.is_active == True
            ).first()
            if link:
                # Use the booking link's assigned users
                user_ids = link.assigned_users if link.assigned_users else [link.user_id]
                return await _generate_slots_for_users(
                    db, user_ids, start_date, end_date, request.duration_minutes
                )

    # If there's an assigned user, get their availability
    if assigned_user_id:
        return await _generate_slots_for_users(
            db, [assigned_user_id], start_date, end_date, request.duration_minutes
        )

    # If there's a Calendly URL, redirect to Calendly
    if calendly_url:
        return {
            "available_slots": [],
            "calendly_url": calendly_url,
            "message": "Please use the Calendly link to schedule",
            "configured": True
        }

    return {
        "available_slots": [],
        "message": "No calendar configuration found",
        "configured": False
    }


async def _generate_slots_for_users(
    db: Session,
    user_ids: List[int],
    start_date: date,
    end_date: date,
    duration_minutes: int = 30
) -> dict:
    """Generate available slots for a list of users."""
    SchedulerConfig = _models.get('SchedulerConfig') if _models else None
    BlockedTime = _models.get('BlockedTime') if _models else None
    Appointment = _models.get('Appointment') if _models else None

    if not SchedulerConfig or not BlockedTime or not Appointment:
        logger.error("Scheduler models not available")
        return {"available_slots": [], "configured": True, "error": "Scheduler not initialized"}

    all_slots = []
    now = datetime.utcnow()
    min_notice_hours = 2  # Default minimum notice

    for user_id in user_ids:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user_id
        ).first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        if config and config.min_notice_hours:
            min_notice_hours = config.min_notice_hours

        min_booking_time = now + timedelta(hours=min_notice_hours)

        # Get blocked times
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        blocked_times = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        ).all()

        # Get existing appointments
        existing_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        ).all()

        # Generate slots for each day
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            try:
                work_start = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                work_end = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, work_start)
            day_end = datetime.combine(current_date, work_end)

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Skip if too soon
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check for blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )

                if not is_blocked:
                    # Check for appointment conflicts
                    has_conflict = any(
                        slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                        slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                        for appt in existing_appts
                    )

                    if not has_conflict:
                        all_slots.append({
                            "start_time": slot_start.isoformat() + "Z",
                            "end_time": slot_end.isoformat() + "Z",
                            "date": current_date.isoformat(),
                            "user_id": user_id
                        })

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Remove duplicates and sort
    unique_slots = list({s["start_time"]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x["start_time"])

    return {
        "available_slots": unique_slots,
        "configured": True,
        "slot_count": len(unique_slots)
    }


class WebsiteDemoBookingRequest(BaseModel):
    """Request model for website demo booking confirmation"""
    start_time: str  # ISO datetime
    duration_minutes: int = 30
    attendee_name: str
    attendee_email: EmailStr
    attendee_phone: Optional[str] = None
    notes: Optional[str] = None
    meeting_mode: str = "video"


@router.post("/public/book-demo/confirm")
async def confirm_website_demo_booking(
    request: WebsiteDemoBookingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Confirm a website demo booking.

    This endpoint creates an appointment using the calendar assignment
    for 'website_demo' purpose.
    """
    from sqlalchemy import text

    # Look up calendar assignment for website_demo purpose
    assignment_result = db.execute(text("""
        SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,
               u.full_name as user_name, u.email as user_email
        FROM calendar_assignments ca
        LEFT JOIN users u ON u.id = ca.assigned_user_id
        WHERE ca.purpose = 'website_demo' AND ca.is_active = true
        LIMIT 1
    """)).fetchone()

    if not assignment_result or not assignment_result.assigned_user_id:
        raise HTTPException(
            status_code=400,
            detail="Website demo calendar not configured. Please assign a team member in Calendar Management."
        )

    assigned_user_id = assignment_result.assigned_user_id
    user_name = assignment_result.user_name or "Team Member"
    user_email = assignment_result.user_email

    try:
        # Parse the start time
        start_time_str = request.start_time.replace("Z", "+00:00")
        start_time = datetime.fromisoformat(start_time_str)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=pytz.UTC)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid start_time format")

    end_time = start_time + timedelta(minutes=request.duration_minutes)

    # Create the appointment
    Appointment = _models.get('Appointment') if _models else None
    if not Appointment:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    appointment_id = f"demo-{uuid_lib.uuid4().hex[:8]}"

    new_appointment = Appointment(
        appointment_id=appointment_id,
        assigned_user_id=assigned_user_id,
        scheduled_start=start_time,
        scheduled_end=end_time,
        duration_minutes=request.duration_minutes,
        attendee_name=request.attendee_name,
        attendee_email=request.attendee_email,
        attendee_phone=request.attendee_phone,
        appointment_type="platform-demo",
        meeting_type=MeetingType.DEMO,
        meeting_mode=MeetingMode.VIDEO if request.meeting_mode == "video" else MeetingMode.PHONE,
        status=AppointmentStatus.BOOKED,
        notes=request.notes,
        booked_via="website",
        lo_name=user_name,
        lo_email=user_email
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    # Format confirmation details
    local_tz = pytz.timezone("America/Chicago")
    local_start = start_time.astimezone(local_tz)
    date_str = local_start.strftime("%A, %B %d, %Y")
    time_str = local_start.strftime("%-I:%M %p %Z")

    # Send confirmation email in background
    try:
        background_tasks.add_task(
            notification_service.send_appointment_confirmation,
            borrower_email=request.attendee_email,
            borrower_name=request.attendee_name,
            appointment_type="Platform Demo",
            appointment_time=start_time,
            lo_name=user_name,
            phone_number=request.attendee_phone,
            appointment_id=appointment_id,
            duration_minutes=request.duration_minutes,
            lo_email=user_email
        )
    except Exception as e:
        logger.warning(f"Failed to queue confirmation email: {e}")

    logger.info(f"Website demo booked: {appointment_id} for {request.attendee_email}")

    return {
        "success": True,
        "appointment_id": appointment_id,
        "confirmation_details": {
            "date": date_str,
            "time": time_str,
            "duration": f"{request.duration_minutes} minutes",
            "meeting_mode": request.meeting_mode.title(),
            "host_name": user_name
        },
        "message": f"Demo scheduled with {user_name}"
    }
