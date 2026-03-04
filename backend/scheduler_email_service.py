"""
Scheduler Email/SMS Notification Service
Extracted from smart_scheduler_routes.py

Provides:
- ICS calendar file generation
- Appointment confirmation emails (SendGrid)
- Appointment confirmation SMS (Telnyx)
- Appointment update emails with calendar invite
- Appointment update SMS
- Team member notification emails
- Appointment cancellation emails
- Team member cancellation emails
"""

import os
import base64
import html
import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

import pytz
import time as _time

from services.notification_service import notification_service

logger = logging.getLogger(__name__)


# ============================================================================
# R1: Email retry with SMS fallback
# ============================================================================

def _retry_email_send(send_fn, max_retries=2, backoff_base=1.0):
    """
    Retry an email send function up to max_retries times with exponential backoff.
    send_fn: zero-arg callable returning {"success": bool, ...} or bool.
    Returns the result dict from the last attempt.
    """
    last_result = {"success": False, "error": "No attempts made"}
    for attempt in range(1 + max_retries):
        try:
            result = send_fn()
            if isinstance(result, bool):
                result = {"success": result}
            if isinstance(result, dict) and result.get("success"):
                return result
            last_result = result if isinstance(result, dict) else {"success": False, "error": str(result)}
        except Exception as e:
            logger.warning(f"Email send attempt {attempt + 1} failed: {e}")
            last_result = {"success": False, "error": str(e)}
        if attempt < max_retries:
            delay = backoff_base * (2 ** attempt)
            logger.info(f"Retrying email in {delay}s (attempt {attempt + 2}/{max_retries + 1})")
            _time.sleep(delay)
    return last_result


def send_with_sms_fallback(
    email_send_fn,
    sms_fallback_fn=None,
    max_retries=2,
    context_label="notification",
    escalation_fn=None,
):
    """
    Try sending email with retries. If all email attempts fail AND an SMS
    fallback function is provided, invoke the SMS fallback.
    If both fail and escalation_fn is provided, call it with the error message.
    Returns dict: {"email_sent": bool, "sms_sent": bool, "error": str|None}
    """
    email_result = _retry_email_send(email_send_fn, max_retries=max_retries)
    email_sent = email_result.get("success", False)
    sms_sent = False
    error = None

    if not email_sent:
        error = email_result.get("error", "Unknown email failure")
        logger.warning(f"{context_label}: Email failed after {max_retries + 1} attempts: {error}")
        if sms_fallback_fn:
            try:
                sms_result = sms_fallback_fn()
                if isinstance(sms_result, bool):
                    sms_sent = sms_result
                elif isinstance(sms_result, dict):
                    sms_sent = sms_result.get("success", False)
                else:
                    sms_sent = bool(sms_result)
                if sms_sent:
                    logger.info(f"{context_label}: SMS fallback sent successfully")
                else:
                    logger.warning(f"{context_label}: SMS fallback also failed")
            except Exception as sms_err:
                logger.error(f"{context_label}: SMS fallback exception: {sms_err}")

    if not email_sent and not sms_sent and escalation_fn:
        try:
            escalation_fn(f"All communication channels failed for {context_label}: {error}")
        except Exception as esc_err:
            logger.error(f"Escalation creation failed: {esc_err}")

    return {"email_sent": email_sent, "sms_sent": sms_sent, "error": error}


# ============================================================================
# C1: TCPA/DNC consent check before SMS
# ============================================================================

def check_sms_consent(phone: str, organization_id: int = None) -> tuple:
    """
    Check DNC list, ChannelPreference, and TCPA contact hours before sending SMS.
    Returns (can_send: bool, reason: str).

    Policy:
    - Outside 8am-9pm recipient local time → BLOCK (TCPA)
    - DNC list match → BLOCK
    - DNC check error → BLOCK (fail-closed for compliance)
    - ChannelPreference.do_not_sms=True → BLOCK
    - ChannelPreference.sms_consent=False → BLOCK
    - No lead/preference found → ALLOW (transactional SMS exemption)
    - Consent check error → BLOCK (fail-safe)
    """
    if not phone:
        return False, "No phone number provided"

    # TCPA: Check contact hours (8am-9pm recipient local time)
    contact_hours_ok, hours_reason = _check_contact_hours()
    if not contact_hours_ok:
        return False, hours_reason

    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            # 1. DNC check using existing ComplianceChecker
            try:
                from telephony.compliance import ComplianceChecker
                checker = ComplianceChecker(db)
                is_dnc, dnc_reason = checker.check_dnc(phone)
                if is_dnc:
                    logger.warning(f"SMS blocked - DNC: {phone}")
                    return False, f"DNC: {dnc_reason}"
            except ImportError:
                logger.debug("telephony.compliance not available, skipping DNC check")
            except Exception as dnc_err:
                # CF-6: Fail-closed — block SMS when DNC check errors (TCPA compliance)
                logger.error(f"DNC check failed, blocking SMS for safety: {dnc_err}")
                return False, f"DNC check unavailable: {dnc_err}"

            # 2. ChannelPreference check (scoped by organization_id)
            try:
                from database.models.communication import ChannelPreference
                from database.models.lead_loan import Lead

                # Normalize phone to last 10 digits for matching
                digits = ''.join(c for c in phone if c.isdigit())
                if len(digits) == 11 and digits.startswith('1'):
                    digits = digits[1:]

                # Scope lead lookup by organization_id to prevent cross-tenant leakage
                lead = None
                if len(digits) >= 10:
                    lead_query = db.query(Lead).filter(
                        Lead.phone.ilike(f"%{digits[-10:]}")
                    )
                    if organization_id:
                        lead_query = lead_query.filter(Lead.organization_id == organization_id)
                    lead = lead_query.first()

                if lead:
                    pref = db.query(ChannelPreference).filter(
                        ChannelPreference.lead_id == lead.id
                    ).first()
                    if pref:
                        if getattr(pref, 'do_not_sms', False):
                            logger.warning(f"SMS blocked - do_not_sms flag: {phone}")
                            return False, "Contact has opted out of SMS"
                        if hasattr(pref, 'sms_consent') and pref.sms_consent is False:
                            logger.warning(f"SMS blocked - no sms_consent: {phone}")
                            return False, "No SMS consent on file"
            except ImportError:
                logger.debug("ChannelPreference model not available, skipping consent check")

            # No block found — allow transactional SMS
            return True, "OK"
        finally:
            db.close()
    except Exception as e:
        logger.error(f"SMS consent check failed, defaulting to BLOCK: {e}")
        return False, f"Consent check error: {e}"


def _check_contact_hours(recipient_tz_name: str = None) -> tuple:
    """
    CF-7: TCPA time-of-day restriction — block SMS outside 8am-9pm recipient local time.
    Returns (can_send: bool, reason: str).
    If recipient timezone is unknown, defaults to America/New_York (earliest US timezone = most conservative).
    """
    try:
        tz_name = recipient_tz_name or "America/New_York"
        tz = pytz.timezone(tz_name)
        local_now = datetime.now(timezone.utc).astimezone(tz)
        local_hour = local_now.hour

        if local_hour < 8 or local_hour >= 21:
            return False, f"TCPA: Outside contact hours (8am-9pm). Local time: {local_now.strftime('%I:%M %p %Z')}"
        return True, "OK"
    except Exception as e:
        # Unknown timezone — use conservative block during late/early hours UTC
        utc_hour = datetime.now(timezone.utc).hour
        if utc_hour >= 2 and utc_hour < 13:
            # 2am-1pm UTC = could be nighttime somewhere in the US
            return True, "OK"
        logger.warning(f"Contact hours check failed, allowing: {e}")
        return True, "OK"


def generate_reschedule_url(appointment_id: int, attendee_email: str, slug: str = None) -> str:
    """Generate a time-limited reschedule URL (valid 72 hours)."""
    import jwt
    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY environment variable is required for reschedule URL generation")
    payload = {
        "appt_id": appointment_id,
        "email": attendee_email,
        "action": "reschedule",
        "exp": datetime.now(timezone.utc) + timedelta(hours=72),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    frontend_base = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    book_path = f"/book/{slug}" if slug else "/reschedule"
    return f"{frontend_base}{book_path}?token={token}&action=reschedule"


def _ics_escape(value: str) -> str:
    """Escape a string for safe embedding in ICS fields (RFC 5545).
    Prevents injection of new ICS properties via newline or special chars."""
    if not value:
        return ""
    # Remove any CR/LF that could inject new ICS properties
    value = value.replace("\r\n", " ").replace("\r", " ").replace("\n", "\\n")
    # Escape backslashes, semicolons, and commas per RFC 5545
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;")
    value = value.replace(",", "\\,")
    return value


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
    video_link: str = None,
    appointment_id: int = None
):
    """Generate ICS calendar file content with proper field escaping."""
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    # Deterministic UID: use appointment_id if available to prevent duplicate calendar events
    if appointment_id:
        uid = f"appt-{appointment_id}@perenniaai.com"
    else:
        uid = f"{uuid_lib.uuid4()}@perenniaai.com"
    from datetime import timezone as tz
    dtstamp = datetime.now(tz.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_datetime.strftime("%Y%m%dT%H%M%SZ")
    dtend = end_datetime.strftime("%Y%m%dT%H%M%SZ")

    # Build and escape description
    full_description = description or ""
    if video_link:
        full_description += "\\nJoin Video Call: " + video_link
        if not location:
            location = video_link

    # Escape all user-supplied fields to prevent ICS injection
    safe_title = _ics_escape(appointment_title)
    safe_description = _ics_escape(full_description)
    safe_location = _ics_escape(location)
    safe_organizer_name = _ics_escape(organizer_name)
    safe_attendee_name = _ics_escape(attendee_name)
    # Email addresses: strip any newlines/special chars
    safe_organizer_email = organizer_email.replace("\n", "").replace("\r", "").strip() if organizer_email else ""
    safe_attendee_email = attendee_email.replace("\n", "").replace("\r", "").strip() if attendee_email else ""

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
SUMMARY:{safe_title}
DESCRIPTION:{safe_description}
LOCATION:{safe_location}
ORGANIZER;CN={safe_organizer_name}:mailto:{safe_organizer_email}
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN={safe_attendee_name}:mailto:{safe_attendee_email}
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
    duration_minutes: int = 30,
    reschedule_url: str = None
):
    """Send appointment confirmation email with calendar invite using SendGrid"""
    try:
        logger.info(f"Attempting to send appointment email to {attendee_email}")

        # Escape all user-controlled data for HTML context
        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_duration = html.escape(str(duration) if duration else '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_video_link = html.escape(video_link) if video_link else None

        team_member_section = f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {safe_team_member_name}</p>" if safe_team_member_name else ""

        # Add video call button if video link is provided
        video_button_section = ""
        if safe_video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{safe_video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                        Or copy this link: <a href="{safe_video_link}" style="color: #217F8D;">{safe_video_link}</a>
                    </p>
            """

        # Add calendar reminder section
        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                A calendar invite is attached to this email. Click on the attachment to add this appointment to your calendar.
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
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment has been scheduled. Here are the details:</p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {video_button_section}
                        {calendar_section}
                        <p style="font-size: 14px; color: #6b7280;">
                            We'll send you a reminder before your appointment.
                        </p>
                        {"" if not reschedule_url else f'''
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{html.escape(reschedule_url)}" style="display: inline-block; background: #f3f4f6; color: #374151; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600; border: 1px solid #d1d5db;">
                                Reschedule Appointment
                            </a>
                        </div>'''}

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

We'll send you a reminder before your appointment.{f" To reschedule, visit: {reschedule_url}" if reschedule_url else ""}

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
    team_member_name: str = None,
    organization_id: int = None,
):
    """Send appointment confirmation SMS via Telnyx"""
    try:
        # TCPA/DNC consent check (scoped by org)
        can_send, reason = check_sms_consent(attendee_phone, organization_id=organization_id)
        if not can_send:
            logger.info(f"SMS consent check blocked confirmation to {attendee_phone}: {reason}")
            return False

        from_number = os.getenv("TELNYX_PHONE_NUMBER")

        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping SMS confirmation")
            return False

        import telnyx

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} is confirmed for {appointment_date} at {appointment_time}. We'll send a reminder before your call. Reply HELP for assistance."

        if len(message_body) > 160:
            logger.warning(f"SMS body is {len(message_body)} chars (>160), will be sent as multi-segment")

        message = telnyx.Message.create(
            from_=from_number,
            to=attendee_phone,
            text=message_body,
        )

        msg_id = getattr(message, 'id', None) or getattr(getattr(message, 'data', None), 'id', None) or 'unknown'
        logger.info(f"Appointment confirmation SMS sent to {attendee_phone}, ID: {msg_id}")
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
    old_time: str = None,
    reschedule_url: str = None
):
    """Send appointment update/reschedule email with updated calendar invite using SendGrid"""
    try:
        logger.info(f"Attempting to send appointment update email to {attendee_email}")

        # Escape all user-controlled data for HTML context
        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_duration = html.escape(str(duration) if duration else '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_old_date = html.escape(old_date or '') if old_date else None
        safe_old_time = html.escape(old_time or '') if old_time else None
        safe_video_link = html.escape(video_link) if video_link else None

        team_member_section = f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {safe_team_member_name}</p>" if safe_team_member_name else ""

        # Show what changed if we have old date/time
        change_section = ""
        if old_date and old_time:
            change_section = f"""
                        <div style="background: #fef3c7; border-radius: 8px; padding: 16px; margin: 20px 0;">
                            <p style="margin: 0 0 8px 0; color: #92400e; font-weight: bold;">Appointment Rescheduled</p>
                            <p style="margin: 0; color: #92400e; font-size: 14px;">
                                <s>Previous: {safe_old_date} at {safe_old_time}</s><br>
                                <strong>New: {safe_appointment_date} at {safe_appointment_time}</strong>
                            </p>
                        </div>
            """

        video_button_section = ""
        if safe_video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{safe_video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
            """

        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                An updated calendar invite is attached. Please add it to replace the previous appointment.
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
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment has been updated. Here are the new details:</p>
                        {change_section}
                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
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
    team_member_name: str = None,
    organization_id: int = None,
):
    """Send appointment update SMS via Telnyx"""
    try:
        # TCPA/DNC consent check (scoped by org)
        can_send, reason = check_sms_consent(attendee_phone, organization_id=organization_id)
        if not can_send:
            logger.info(f"SMS consent check blocked update to {attendee_phone}: {reason}")
            return False

        from_number = os.getenv("TELNYX_PHONE_NUMBER")

        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping SMS update")
            return False

        import telnyx

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} has been UPDATED to {appointment_date} at {appointment_time}. Please check your email for the updated calendar invite."

        message = telnyx.Message.create(
            from_=from_number,
            to=attendee_phone,
            text=message_body,
        )

        msg_id = getattr(message, 'id', None) or getattr(getattr(message, 'data', None), 'id', None) or 'unknown'
        logger.info(f"Appointment update SMS sent to {attendee_phone}, ID: {msg_id}")
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

        # Escape all user-controlled data for HTML context
        safe_team_member_name = html.escape(team_member_name or '')
        safe_attendee_name = html.escape(attendee_name or '')
        safe_attendee_email = html.escape(attendee_email or '')
        safe_attendee_phone = html.escape(attendee_phone or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_duration = html.escape(str(duration) if duration else '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_video_link = html.escape(video_link) if video_link else None

        # Add video call button if video link is provided
        video_button_section = ""
        if safe_video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{safe_video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                        Video link: <a href="{safe_video_link}" style="color: #217F8D;">{safe_video_link}</a>
                    </p>
            """

        # Add calendar reminder section
        calendar_section = """
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                A calendar invite is attached to this email. Click on the attachment to add this appointment to your calendar.
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
                        <p style="font-size: 16px; color: #374151;">Hi {safe_team_member_name},</p>

                        <p style="font-size: 16px; color: #374151;">A new appointment has been scheduled for you:</p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Client:</strong> {safe_attendee_name}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Email:</strong> <a href="mailto:{safe_attendee_email}" style="color: #217F8D;">{safe_attendee_email}</a></p>
                            {f'<p style="margin: 8px 0; color: #111827;"><strong>Phone:</strong> <a href="tel:{safe_attendee_phone}" style="color: #217F8D;">{safe_attendee_phone}</a></p>' if attendee_phone else ''}
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
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

        # Escape all user-controlled data for HTML context
        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_cancellation_reason = html.escape(cancellation_reason or '') if cancellation_reason else None

        reason_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Reason:</strong> {safe_cancellation_reason}</p>" if safe_cancellation_reason else ""
        team_member_section = f" with {safe_team_member_name}" if safe_team_member_name else ""
        text_team_member_section = f" with {team_member_name}" if team_member_name else ""

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
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment{team_member_section} has been cancelled.</p>

                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #991b1b;"><strong>Cancelled Appointment:</strong></p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Title:</strong> {safe_appointment_title}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
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

Your appointment{text_team_member_section} has been cancelled.

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
            plain_content=text_content
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

        # Escape all user-controlled data for HTML context
        safe_team_member_name = html.escape(team_member_name or '')
        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_cancellation_reason = html.escape(cancellation_reason or '') if cancellation_reason else None
        safe_cancelled_by = html.escape(cancelled_by or '') if cancelled_by else None

        reason_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Reason:</strong> {safe_cancellation_reason}</p>" if safe_cancellation_reason else ""
        cancelled_by_section = f"<p style='margin: 8px 0; color: #6b7280;'><strong>Cancelled by:</strong> {safe_cancelled_by}</p>" if safe_cancelled_by else ""

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
                        <p style="font-size: 16px; color: #374151;">Hi {safe_team_member_name},</p>

                        <p style="font-size: 16px; color: #374151;">An appointment with <strong>{safe_attendee_name}</strong> has been cancelled.</p>

                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #991b1b;"><strong>Cancelled Appointment:</strong></p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Client:</strong> {safe_attendee_name}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Title:</strong> {safe_appointment_title}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
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
            plain_content=text_content
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


def send_appointment_reminder_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration_minutes: int = 30,
    hours_before: int = 24,
    meeting_mode: str = "Phone Call",
    team_member_name: str = None,
    team_member_email: str = None,
    video_link: str = None,
    scheduled_start: datetime = None,
):
    """Send appointment reminder email with ICS calendar attachment."""
    try:
        if hours_before >= 24:
            subject_prefix = "Reminder: Tomorrow"
            heading = "Your Appointment is Tomorrow!"
            message = "This is a friendly reminder about your upcoming appointment."
        else:
            subject_prefix = "Starting Soon"
            heading = "Your Appointment Starts Soon!"
            message = "Your appointment is coming up shortly. Please be ready."

        # Escape all user-controlled data for HTML context
        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_duration_minutes = html.escape(str(duration_minutes) if duration_minutes else '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_video_link = html.escape(video_link) if video_link else None

        team_member_section = f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {safe_team_member_name}</p>" if safe_team_member_name else ""

        video_button_section = ""
        if safe_video_link:
            video_button_section = f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{safe_video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
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
                        <h1 style="color: white; margin: 0; font-size: 24px;">{heading}</h1>
                    </div>
                    <div style="padding: 30px;">
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>
                        <p style="font-size: 16px; color: #374151;">{message}</p>
                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration_minutes} minutes</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {video_button_section}
                        <p style="font-size: 14px; color: #6b7280;">
                            If you need to reschedule or cancel, please contact us as soon as possible.
                        </p>
                    </div>
                </div>
                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    Sent from Perennia AI
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
{heading}

Hi {attendee_name},

{message}

Date: {appointment_date}
Time: {appointment_time}
Duration: {duration_minutes} minutes
Meeting Type: {meeting_mode}
{f'Meeting with: {team_member_name}' if team_member_name else ''}
{f'Join Video Call: {video_link}' if video_link else ''}

If you need to reschedule or cancel, please contact us as soon as possible.

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
                    description=f"Reminder: {appointment_title}",
                    video_link=video_link
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment.ics',
                    'type': 'text/calendar'
                })
            except Exception as ics_error:
                logger.error(f"Failed to generate reminder ICS attachment: {ics_error}")

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"{subject_prefix}: {appointment_title} - {appointment_date} at {appointment_time}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None
        )

        if result.get("success"):
            logger.info(f"Appointment reminder email sent to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to send reminder email to {attendee_email}: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_appointment_reminder_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


def send_appointment_reminder_sms(
    attendee_phone: str,
    attendee_name: str,
    appointment_date: str,
    appointment_time: str,
    hours_before: int = 24,
    team_member_name: str = None,
    video_link: str = None,
    organization_id: int = None,
):
    """Send appointment reminder SMS via Telnyx."""
    try:
        # TCPA/DNC consent check (scoped by org)
        can_send, reason = check_sms_consent(attendee_phone, organization_id=organization_id)
        if not can_send:
            logger.info(f"SMS consent check blocked reminder to {attendee_phone}: {reason}")
            return {"success": False, "error": f"Consent blocked: {reason}"}

        from_number = os.getenv("TELNYX_PHONE_NUMBER")
        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping reminder SMS")
            return {"success": False, "error": "SMS not configured"}

        import telnyx

        if hours_before >= 24:
            time_msg = "tomorrow"
        else:
            time_msg = "soon"

        team_msg = f" with {team_member_name}" if team_member_name else ""
        link_msg = f"\nJoin: {video_link}" if video_link else ""

        message_body = (
            f"Hi {attendee_name}! Reminder: Your appointment{team_msg} is {time_msg} "
            f"on {appointment_date} at {appointment_time}.{link_msg} "
            f"Reply HELP for assistance."
        )

        message = telnyx.Message.create(
            from_=from_number,
            to=attendee_phone,
            text=message_body,
        )

        msg_id = getattr(message, 'id', None) or getattr(getattr(message, 'data', None), 'id', None) or 'unknown'
        logger.info(f"Appointment reminder SMS sent to {attendee_phone}, ID: {msg_id}")
        return {"success": True, "message_id": msg_id}

    except Exception as e:
        logger.error(f"Failed to send appointment reminder SMS: {e}")
        return {"success": False, "error": str(e)}
