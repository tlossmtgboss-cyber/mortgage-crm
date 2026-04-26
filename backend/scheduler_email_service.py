"""
Scheduler Email/SMS Notification Service
Extracted from smart_scheduler_routes.py

Provides:
- Appointment confirmation emails (SendGrid)
- Appointment confirmation SMS (Telnyx)
- Appointment update emails with calendar invite
- Appointment update SMS
- Team member notification emails
- Appointment cancellation emails
- Team member cancellation emails
- AI booking confirmation emails
- Pre-appointment prep reminder emails
- No-show recovery emails
- Async wrappers for all email functions (via asyncio.to_thread)
- Retry with exponential backoff (max 3 retries) for transient SMTP failures

ICS calendar generation has been extracted to ``services.ics_generator``.
SMS sending has been extracted to ``services.scheduler_sms_sender``.
Email HTML templates have been extracted to ``services.scheduler_email_templates``.
"""

import asyncio
import os
import base64
import html
import logging
import time as _time
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.notification_service import notification_service
from services.pii_masking import mask_email as _mask_email
from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL


def _resolve_organizer_name(team_member_name: Optional[str], organization_id: Optional[int] = None) -> str:
    """Resolve organizer/company name: team member → org branding → fallback."""
    if team_member_name:
        return team_member_name
    if organization_id:
        try:
            from database import SessionLocal
            from services.company_name_resolver import resolve_company_name
            with SessionLocal() as db:
                return resolve_company_name(db, organization_id)
        except Exception:
            pass
    return os.getenv("COMPANY_NAME", "The Tim Loss Team")


def _is_email_suppressed(email: str) -> bool:
    """Lazy wrapper to avoid circular import with routes.scheduler.email_events."""
    try:
        from routes.scheduler.email_events import is_email_suppressed
        return is_email_suppressed(email)
    except ImportError:
        return False

# --- Re-exports from extracted sub-modules (backward compatibility) ---
# SMS compliance: consent checking, contact hours (canonical source)
from services.sms_compliance import check_sms_consent, _check_contact_hours  # noqa: F401

# SMS sender: all SMS sending functions
from services.scheduler_sms_sender import (  # noqa: F401
    send_appointment_confirmation_sms,
    send_appointment_update_sms,
    send_appointment_reminder_sms,
)

# ICS calendar generation (canonical source: services.ics_generator)
from services.ics_generator import generate_ics_content  # noqa: F401

# Email templates: HTML builders, color constants, prep items
from services.scheduler_email_templates import (
    build_scheduler_email_html,
    video_button_html,
    calendar_notice_html,
    default_prep_items,
    HEADER_COLOR_TEAL,
    HEADER_COLOR_AMBER,
    HEADER_COLOR_RED,
    HEADER_COLOR_BLUE,
    HEADER_COLOR_GREEN,
    HEADER_COLOR_PURPLE,
)

try:
    from routes.scheduler.middleware import get_correlated_logger
    logger = get_correlated_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# --- Backward-compatible aliases for underscore-prefixed names ---
_HEADER_COLOR_TEAL = HEADER_COLOR_TEAL
_HEADER_COLOR_AMBER = HEADER_COLOR_AMBER
_HEADER_COLOR_RED = HEADER_COLOR_RED
_HEADER_COLOR_BLUE = HEADER_COLOR_BLUE
_HEADER_COLOR_GREEN = HEADER_COLOR_GREEN
_HEADER_COLOR_PURPLE = HEADER_COLOR_PURPLE


def _build_scheduler_email_html(header_color, heading, body_content, footer_text=None):
    """Backward-compatible wrapper for build_scheduler_email_html."""
    return build_scheduler_email_html(header_color, heading, body_content, footer_text)


def _video_button_html(safe_video_link, show_copy_link=False):
    """Backward-compatible wrapper for video_button_html."""
    return video_button_html(safe_video_link, show_copy_link)


def _calendar_notice_html(text=None):
    """Backward-compatible wrapper for calendar_notice_html."""
    return calendar_notice_html(text)


def _default_prep_items(meeting_type_key=None):
    """Backward-compatible wrapper for default_prep_items."""
    return default_prep_items(meeting_type_key)


# ============================================================================
# Per-recipient email throttle
# ============================================================================

# In-memory throttle state: {email -> list of timestamps}
_email_throttle_store: OrderedDict = OrderedDict()
_email_throttle_lock = threading.Lock()
_EMAIL_THROTTLE_WINDOW = 3600  # 1 hour in seconds
_EMAIL_THROTTLE_MAX_KEYS = 10000
_email_throttle_cleanup_counter = 0
_EMAIL_THROTTLE_CLEANUP_INTERVAL = 100

# Lazy Redis connection for email throttle
_email_throttle_redis = None
_email_throttle_redis_checked = False


def _get_email_throttle_redis():
    """Get or create Redis connection for email throttle. Returns None if unavailable."""
    global _email_throttle_redis, _email_throttle_redis_checked
    if _email_throttle_redis_checked:
        return _email_throttle_redis
    _email_throttle_redis_checked = True
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.debug("Email throttle: REDIS_URL not set, using in-memory fallback")
        return None
    try:
        import redis as redis_lib
        _email_throttle_redis = redis_lib.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2
        )
        _email_throttle_redis.ping()
        logger.info("Email throttle connected to Redis")
    except Exception as e:
        logger.warning(f"Email throttle: Redis unavailable, using in-memory fallback: {e}")
        _email_throttle_redis = None
    return _email_throttle_redis


def _check_email_rate_limit(recipient_email: str, max_per_hour: int = 10, org_id: int = None) -> bool:
    """
    Check whether sending another email to recipient_email is allowed.

    Returns True if under the limit, False if throttled.
    Never raises -- email delivery should degrade gracefully, not crash.

    Uses Redis if REDIS_URL is set (key ``sched_email:{org}:{email}``, 1-hour TTL).
    Falls back to an in-memory dict with periodic cleanup otherwise.

    Rate limits are scoped per-org to prevent one tenant's burst from blocking others.
    """
    if not recipient_email:
        return True

    email_lower = recipient_email.lower().strip()
    # Scope rate limit key by org_id to isolate tenants
    org_prefix = str(org_id) if org_id else "global"

    # Try Redis first
    r = _get_email_throttle_redis()
    if r is not None:
        try:
            key = f"sched_email:{org_prefix}:{email_lower}"
            current = r.incr(key)
            if current == 1:
                r.expire(key, _EMAIL_THROTTLE_WINDOW)
            if current > max_per_hour:
                logger.warning(
                    f"Email throttle: Redis limit exceeded for {_mask_email(email_lower)} "
                    f"({current}/{max_per_hour} in last hour)"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Email throttle: Redis error, falling back to memory: {e}")
            # Fall through to in-memory

    # In-memory fallback (thread-safe via threading.Lock since email functions are sync)
    global _email_throttle_cleanup_counter
    now = _time.time()
    cutoff = now - _EMAIL_THROTTLE_WINDOW

    with _email_throttle_lock:
        # Periodic cleanup of expired entries
        _email_throttle_cleanup_counter += 1
        if _email_throttle_cleanup_counter >= _EMAIL_THROTTLE_CLEANUP_INTERVAL:
            _email_throttle_cleanup_counter = 0
            expired_keys = [
                k for k, timestamps in _email_throttle_store.items()
                if not timestamps or timestamps[-1] < cutoff
            ]
            for k in expired_keys:
                del _email_throttle_store[k]

        throttle_key = f"{org_prefix}:{email_lower}"
        if throttle_key in _email_throttle_store:
            timestamps = _email_throttle_store[throttle_key]
            _email_throttle_store.move_to_end(throttle_key)
        else:
            # Capacity check -- drop oldest if full (email throttle is less
            # security-critical than the IP rate limiter, so LRU eviction is OK)
            if len(_email_throttle_store) >= _EMAIL_THROTTLE_MAX_KEYS:
                _email_throttle_store.popitem(last=False)
            timestamps = []
            _email_throttle_store[throttle_key] = timestamps

        # Remove expired timestamps
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= max_per_hour:
            logger.warning(
                f"Email throttle: in-memory limit exceeded for {_mask_email(email_lower)} "
                f"({len(timestamps)}/{max_per_hour} in last hour)"
            )
            return False

        timestamps.append(now)
        return True


# ============================================================================
# R1: Email retry with SMS fallback
# ============================================================================

async def _retry_email_send(send_fn, max_retries=3, backoff_base=1.0):
    """
    Retry an email send function up to max_retries times with exponential backoff.
    send_fn: zero-arg callable returning {"success": bool, ...} or bool.
    Returns the result dict from the last attempt.
    Uses asyncio.sleep() to avoid blocking the event loop.

    Backoff schedule (with default backoff_base=1.0):
        Attempt 1: immediate
        Attempt 2: 1s delay
        Attempt 3: 2s delay
        Attempt 4: 4s delay
    """
    last_result = {"success": False, "error": "No attempts made"}
    total_attempts = 1 + max_retries
    for attempt in range(total_attempts):
        try:
            result = send_fn()
            if isinstance(result, bool):
                result = {"success": result}
            if isinstance(result, dict) and result.get("success"):
                if attempt > 0:
                    logger.info(
                        f"Email send succeeded on retry attempt {attempt + 1}/{total_attempts}"
                    )
                return result
            last_result = result if isinstance(result, dict) else {"success": False, "error": str(result)}
            logger.warning(
                f"Email send attempt {attempt + 1}/{total_attempts} returned failure: "
                f"{last_result.get('error', 'unknown')}"
            )
        except Exception as e:
            logger.warning(
                f"Email send attempt {attempt + 1}/{total_attempts} raised exception: {e}"
            )
            last_result = {"success": False, "error": str(e)}
        if attempt < max_retries:
            delay = backoff_base * (2 ** attempt)
            logger.info(f"Retrying email in {delay:.1f}s (attempt {attempt + 2}/{total_attempts})")
            await asyncio.sleep(delay)
    logger.error(f"Email send failed after all {total_attempts} attempts: {last_result.get('error')}")
    return last_result


async def send_with_sms_fallback(
    email_send_fn,
    sms_fallback_fn=None,
    max_retries=3,
    context_label="notification",
    escalation_fn=None,
):
    """
    Try sending email with retries. If all email attempts fail AND an SMS
    fallback function is provided, invoke the SMS fallback.
    If both fail and escalation_fn is provided, call it with the error message.
    Returns dict: {"email_sent": bool, "sms_sent": bool, "error": str|None}
    """
    email_result = await _retry_email_send(email_send_fn, max_retries=max_retries)
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
# ICS and URL helpers
# ============================================================================

def generate_reschedule_url(appointment_id: int, attendee_email: str, slug: str = None) -> str:
    """Generate a time-limited reschedule URL (valid 72 hours).

    SEC-010: Uses email_hash instead of plaintext email in the JWT payload.
    """
    import hashlib
    import jwt
    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY environment variable is required for reschedule URL generation")
    email_hash = hashlib.sha256(attendee_email.lower().strip().encode()).hexdigest()[:16] if attendee_email else ""
    payload = {
        "appt_id": appointment_id,
        "email_hash": email_hash,
        "action": "reschedule",
        "exp": datetime.now(timezone.utc) + timedelta(hours=72),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    frontend_base = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    book_path = f"/book/{slug}" if slug else "/reschedule"
    return f"{frontend_base}{book_path}?token={token}&action=reschedule"


# NOTE: generate_ics_content is imported from services.ics_generator (see imports above).
# The inline _ics_escape() and generate_ics_content() that previously lived here have been
# removed in favour of the canonical implementation in services/ics_generator.py which
# delegates to the RFC 5545-compliant primitives in utils/ics_generator.py.


# ============================================================================
# Email functions
# ============================================================================

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
    reschedule_url: str = None,
    organization_id: int = None,
):
    """Send appointment confirmation email with calendar invite using SendGrid"""
    if _is_email_suppressed(attendee_email):
        logger.info(f"Email suppressed (bounce/complaint): {_mask_email(attendee_email)}, skipping confirmation")
        return {"success": False, "error": "Email address suppressed"}

    if not _check_email_rate_limit(attendee_email, org_id=organization_id):
        logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping confirmation email")
        return {"success": False, "error": "Rate limit exceeded"}

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

        reschedule_section = ""
        if reschedule_url:
            reschedule_section = f'''
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{html.escape(reschedule_url)}" style="display: inline-block; background: #f3f4f6; color: #374151; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600; border: 1px solid #d1d5db;">
                                Reschedule Appointment
                            </a>
                        </div>'''

        body_content = f"""
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">Your appointment has been scheduled. Here are the details:</p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {_video_button_html(safe_video_link, show_copy_link=True)}
                        {_calendar_notice_html()}
                        <p style="font-size: 14px; color: #6b7280;">
                            We'll send you a reminder before your appointment.
                        </p>
                        {reschedule_section}

                        <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                            Looking forward to speaking with you!
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_TEAL,
            heading="Appointment Confirmed!",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

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

- The Tim Loss Team
        """

        # Generate ICS attachment if we have the scheduled_start datetime
        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL)
                organizer_name = _resolve_organizer_name(team_member_name, organization_id)

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
    reschedule_url: str = None,
    organization_id: int = None,
):
    """Send appointment update/reschedule email with updated calendar invite using SendGrid"""
    if not _check_email_rate_limit(attendee_email, org_id=organization_id):
        logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping update email")
        return {"success": False, "error": "Rate limit exceeded"}

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

        body_content = f"""
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
                        {_video_button_html(safe_video_link)}
                        {_calendar_notice_html("An updated calendar invite is attached. Please add it to replace the previous appointment.")}
                        <p style="font-size: 14px; color: #6b7280;">
                            If you have any questions about this change, please contact us.
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_AMBER,
            heading="Appointment Updated!",
            body_content=body_content,
        )

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

- The Tim Loss Team
        """

        # Generate ICS attachment
        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL)
                organizer_name = _resolve_organizer_name(team_member_name, organization_id)

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

        # Build video button with "Video link:" label for team member
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

        body_content = f"""
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
                        {_calendar_notice_html()}
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_TEAL,
            heading="New Appointment Scheduled",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

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

- The Tim Loss Team
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
                    organizer_email=os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL),
                    organizer_name=os.getenv("COMPANY_NAME", "The Tim Loss Team"),
                    description=f"Meeting with {attendee_name}\nEmail: {attendee_email}\nPhone: {attendee_phone or 'N/A'}",
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
    cancellation_reason: str = None,
    organization_id: int = None,
):
    """Send appointment cancellation email to attendee"""
    if not _check_email_rate_limit(attendee_email, org_id=organization_id):
        logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping cancellation email")
        return False

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

        body_content = f"""
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
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_RED,
            heading="Appointment Cancelled",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

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

- The Tim Loss Team
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

        body_content = f"""
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
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_RED,
            heading="Appointment Cancelled",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

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

- The Tim Loss Team
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
    organization_id: int = None,
):
    """Send appointment reminder email with ICS calendar attachment."""
    if not _check_email_rate_limit(attendee_email, org_id=organization_id):
        logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping reminder email")
        return {"success": False, "error": "Rate limit exceeded"}

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

        body_content = f"""
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>
                        <p style="font-size: 16px; color: #374151;">{message}</p>
                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration_minutes} minutes</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
                            {team_member_section}
                        </div>
                        {_video_button_html(safe_video_link)}
                        <p style="font-size: 14px; color: #6b7280;">
                            If you need to reschedule or cancel, please contact us as soon as possible.
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_AMBER,
            heading=heading,
            body_content=body_content,
        )

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

- The Tim Loss Team
        """

        # Generate ICS attachment if we have the scheduled_start datetime
        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL)
                organizer_name = _resolve_organizer_name(team_member_name, organization_id)

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


# ============================================================================
# New email templates: AI booking, pre-appointment prep, no-show recovery
# ============================================================================

def send_ai_booking_confirmation_email(
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
    ai_context: str = None,
    reschedule_url: str = None,
    organization_id: int = None,
):
    """Send confirmation email for an AI-booked appointment.

    Similar to send_appointment_confirmation_email but includes messaging
    that the appointment was intelligently scheduled by The Tim Loss Team and
    optionally includes AI context (e.g., why this time was chosen).
    """
    try:
        # DATA-011: Rate limit AI booking confirmation emails per-org
        if not _check_email_rate_limit(attendee_email, org_id=organization_id):
            logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping AI booking confirmation email")
            return {"success": False, "error": "Rate limit exceeded"}

        logger.info(
            f"Sending AI booking confirmation to {attendee_email} "
            f"for '{appointment_title}' on {appointment_date}"
        )

        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_duration = html.escape(str(duration) if duration else '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_video_link = html.escape(video_link) if video_link else None
        safe_ai_context = html.escape(ai_context or '') if ai_context else None

        team_section = (
            f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {safe_team_member_name}</p>"
            if safe_team_member_name else ""
        )

        ai_section = ""
        if safe_ai_context:
            ai_section = f"""
                        <div style="background: #ede9fe; border-radius: 8px; padding: 16px; margin: 20px 0;">
                            <p style="margin: 0 0 4px 0; color: #5b21b6; font-weight: bold; font-size: 13px;">
                                Why this time was selected
                            </p>
                            <p style="margin: 0; color: #6d28d9; font-size: 14px;">
                                {safe_ai_context}
                            </p>
                        </div>
            """

        reschedule_section = ""
        if reschedule_url:
            reschedule_section = f'''
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{html.escape(reschedule_url)}" style="display: inline-block; background: #f3f4f6; color: #374151; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600; border: 1px solid #d1d5db;">
                                Reschedule Appointment
                            </a>
                        </div>'''

        body_content = f"""
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">
                            Great news! The Tim Loss Team has scheduled your appointment.
                            Here are the details:
                        </p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_duration}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Meeting Type:</strong> {safe_meeting_mode}</p>
                            {team_section}
                        </div>
                        {ai_section}
                        {_video_button_html(safe_video_link, show_copy_link=True)}
                        {_calendar_notice_html()}
                        <p style="font-size: 14px; color: #6b7280;">
                            We'll send you a reminder before your appointment.
                        </p>
                        {reschedule_section}

                        <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                            Looking forward to speaking with you!
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_BLUE,
            heading="AI-Scheduled Appointment Confirmed!",
            body_content=body_content,
            footer_text="Intelligently scheduled by The Tim Loss Team",
        )

        video_link_text = f"\nJoin Video Call: {video_link}" if video_link else ""
        ai_context_text = f"\nWhy this time: {ai_context}" if ai_context else ""
        text_content = f"""
AI-Scheduled Appointment Confirmed!

Hi {attendee_name},

The Tim Loss Team has scheduled your appointment. Here are the details:

Date: {appointment_date}
Time: {appointment_time}
Duration: {duration}
Meeting Type: {meeting_mode}
{f'Meeting with: {team_member_name}' if team_member_name else ''}{video_link_text}{ai_context_text}

A calendar invite is attached to this email.

We'll send you a reminder before your appointment.{f" To reschedule, visit: {reschedule_url}" if reschedule_url else ""}

Looking forward to speaking with you!

- The Tim Loss Team
        """

        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv(
                    "SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL
                )
                organizer_name = _resolve_organizer_name(team_member_name, organization_id)

                ics_content = generate_ics_content(
                    appointment_title=appointment_title,
                    start_datetime=scheduled_start,
                    duration_minutes=duration_minutes,
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    organizer_email=organizer_email,
                    organizer_name=organizer_name,
                    description=f"AI-Scheduled: {appointment_title}",
                    video_link=video_link,
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment.ics',
                    'type': 'text/calendar',
                })
                logger.info("ICS attachment created for AI booking confirmation")
            except Exception as ics_error:
                logger.error(f"Failed to generate ICS for AI booking: {ics_error}")

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"Appointment Confirmed: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None,
        )

        if result.get("success"):
            logger.info(f"AI booking confirmation email sent to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to send AI booking confirmation to {attendee_email}: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_ai_booking_confirmation_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


def send_pre_appointment_prep_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    duration_minutes: int = 30,
    meeting_mode: str = "Phone Call",
    team_member_name: str = None,
    team_member_email: str = None,
    video_link: str = None,
    scheduled_start: datetime = None,
    prep_items: list = None,
    meeting_type_key: str = None,
    organization_id: int = None,
):
    """Send a pre-appointment preparation reminder email.

    Sent ~24h before the appointment with a checklist of items the borrower
    should gather/review before the meeting (e.g., documents, questions).
    """
    try:
        # DATA-011: Rate limit prep emails per-org
        if not _check_email_rate_limit(attendee_email, org_id=organization_id):
            logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping prep email")
            return {"success": False, "error": "Rate limit exceeded"}

        logger.info(
            f"Sending pre-appointment prep email to {attendee_email} "
            f"for '{appointment_title}' on {appointment_date}"
        )

        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_meeting_mode = html.escape(meeting_mode or 'Phone Call')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None
        safe_video_link = html.escape(video_link) if video_link else None

        # Build preparation checklist based on meeting type or custom items
        if prep_items:
            checklist_items = prep_items
        else:
            checklist_items = _default_prep_items(meeting_type_key)

        checklist_html = ""
        if checklist_items:
            items_html = "".join(
                f'<li style="margin: 8px 0; color: #374151;">{html.escape(item)}</li>'
                for item in checklist_items
            )
            checklist_html = f"""
                        <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 0 0 12px 0; color: #065f46; font-weight: bold; font-size: 15px;">
                                Preparation Checklist
                            </p>
                            <ul style="margin: 0; padding-left: 20px;">
                                {items_html}
                            </ul>
                        </div>
            """

        team_section = (
            f"<p style='margin: 8px 0;'><strong>Meeting with:</strong> {safe_team_member_name}</p>"
            if safe_team_member_name else ""
        )

        body_content = f"""
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">
                            Your appointment is coming up tomorrow! Here is a quick reminder
                            with some tips to help you prepare.
                        </p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Duration:</strong> {safe_meeting_mode} ({duration_minutes} min)</p>
                            {team_section}
                        </div>
                        {checklist_html}
                        {_video_button_html(safe_video_link)}
                        <p style="font-size: 14px; color: #6b7280;">
                            Having these items ready will help us make the most of our time together.
                            If you have questions beforehand, feel free to reply to this email.
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_GREEN,
            heading="Prepare for Your Appointment",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

        checklist_text = ""
        if checklist_items:
            checklist_text = "\nPreparation Checklist:\n" + "\n".join(
                f"  - {item}" for item in checklist_items
            ) + "\n"

        text_content = f"""
Prepare for Your Appointment

Hi {attendee_name},

Your appointment is coming up tomorrow! Here is a quick reminder.

Date: {appointment_date}
Time: {appointment_time}
Duration: {duration_minutes} minutes ({meeting_mode})
{f'Meeting with: {team_member_name}' if team_member_name else ''}
{checklist_text}
{f'Join Video Call: {video_link}' if video_link else ''}

Having these items ready will help us make the most of our time together.

- The Tim Loss Team
        """

        attachments = []
        if scheduled_start:
            try:
                organizer_email = team_member_email or os.getenv(
                    "SENDGRID_FROM_EMAIL", DEFAULT_ORGANIZER_EMAIL
                )
                organizer_name = _resolve_organizer_name(team_member_name, organization_id)

                ics_content = generate_ics_content(
                    appointment_title=appointment_title,
                    start_datetime=scheduled_start,
                    duration_minutes=duration_minutes,
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    organizer_email=organizer_email,
                    organizer_name=organizer_name,
                    description=f"Prep Reminder: {appointment_title}",
                    video_link=video_link,
                )

                attachments.append({
                    'content': base64.b64encode(ics_content.encode('utf-8')).decode('utf-8'),
                    'filename': 'appointment.ics',
                    'type': 'text/calendar',
                })
            except Exception as ics_error:
                logger.error(f"Failed to generate ICS for prep email: {ics_error}")

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"Prepare for Tomorrow: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
            attachments=attachments if attachments else None,
        )

        if result.get("success"):
            logger.info(f"Pre-appointment prep email sent to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to send prep email to {attendee_email}: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_pre_appointment_prep_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


def send_no_show_recovery_email(
    attendee_email: str,
    attendee_name: str,
    appointment_title: str,
    appointment_date: str,
    appointment_time: str,
    team_member_name: str = None,
    reschedule_url: str = None,
    meeting_type_key: str = None,
    organization_id: int = None,
):
    """Send a no-show recovery email to encourage the borrower to rebook.

    Sent after an appointment is marked as no-show. The tone is warm and
    non-judgmental, offering an easy way to reschedule.
    """
    try:
        # DATA-011: Rate limit no-show recovery emails per-org
        if not _check_email_rate_limit(attendee_email, org_id=organization_id):
            logger.warning(f"Email rate limit exceeded for {_mask_email(attendee_email)}, skipping no-show recovery email")
            return {"success": False, "error": "Rate limit exceeded"}

        logger.info(
            f"Sending no-show recovery email to {attendee_email} "
            f"for missed appointment '{appointment_title}' on {appointment_date}"
        )

        safe_attendee_name = html.escape(attendee_name or '')
        safe_appointment_title = html.escape(appointment_title or '')
        safe_appointment_date = html.escape(appointment_date or '')
        safe_appointment_time = html.escape(appointment_time or '')
        safe_team_member_name = html.escape(team_member_name or '') if team_member_name else None

        team_section = (
            f" with {safe_team_member_name}" if safe_team_member_name else ""
        )

        reschedule_button = ""
        if reschedule_url:
            reschedule_button = f"""
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{html.escape(reschedule_url)}" style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 16px 36px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                Reschedule Now
                            </a>
                        </div>
                        <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                            Or copy this link: <a href="{html.escape(reschedule_url)}" style="color: #217F8D;">{html.escape(reschedule_url)}</a>
                        </p>
            """

        body_content = f"""
                        <p style="font-size: 16px; color: #374151;">Hi {safe_attendee_name},</p>

                        <p style="font-size: 16px; color: #374151;">
                            We missed you at your appointment{team_section} today. We hope everything is okay!
                        </p>

                        <div style="background: #fff7ed; border: 1px solid #fed7aa; border-radius: 12px; padding: 20px; margin: 20px 0;">
                            <p style="margin: 8px 0; color: #9a3412;"><strong>Missed Appointment:</strong></p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Title:</strong> {safe_appointment_title}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Date:</strong> {safe_appointment_date}</p>
                            <p style="margin: 8px 0; color: #111827;"><strong>Time:</strong> {safe_appointment_time}</p>
                        </div>

                        <p style="font-size: 16px; color: #374151;">
                            Life happens, and we completely understand. We would love to find a
                            time that works better for you. Rescheduling only takes a moment:
                        </p>
                        {reschedule_button}
                        <p style="font-size: 14px; color: #6b7280; margin-top: 20px;">
                            If you are no longer interested or have any questions, just reply to
                            this email and we will be happy to help.
                        </p>
        """

        html_content = _build_scheduler_email_html(
            header_color=_HEADER_COLOR_AMBER,
            heading="We Missed You!",
            body_content=body_content,
            footer_text="Sent from The Tim Loss Team",
        )

        text_team = f" with {team_member_name}" if team_member_name else ""
        text_content = f"""
We Missed You!

Hi {attendee_name},

We missed you at your appointment{text_team} today. We hope everything is okay!

Missed Appointment:
Title: {appointment_title}
Date: {appointment_date}
Time: {appointment_time}

Life happens, and we completely understand. We would love to find a time that works better for you.
{f'Reschedule here: {reschedule_url}' if reschedule_url else 'Please reply to this email to reschedule.'}

If you are no longer interested or have any questions, just reply to this email.

- The Tim Loss Team
        """

        result = notification_service.send_email(
            to_email=attendee_email,
            subject=f"We Missed You - Let's Reschedule: {appointment_title}",
            html_content=html_content,
            plain_content=text_content,
        )

        if result.get("success"):
            logger.info(f"No-show recovery email sent to {attendee_email}")
            return {"success": True, "error": None}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to send no-show recovery email to {attendee_email}: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Exception in send_no_show_recovery_email: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# Async wrappers
# ============================================================================
# All sync email functions are wrapped via asyncio.to_thread() so they can be
# awaited from async route handlers without blocking the event loop.
# The sync functions are preserved unchanged for backward compatibility.
# ============================================================================

async def async_send_appointment_confirmation_email(**kwargs) -> dict:
    """Async wrapper for send_appointment_confirmation_email with retry."""
    return await _async_email_with_retry(
        send_appointment_confirmation_email,
        "appointment_confirmation",
        **kwargs,
    )


async def async_send_appointment_update_email(**kwargs) -> dict:
    """Async wrapper for send_appointment_update_email with retry."""
    return await _async_email_with_retry(
        send_appointment_update_email,
        "appointment_update",
        **kwargs,
    )


async def async_send_appointment_cancellation_email(**kwargs) -> dict:
    """Async wrapper for send_appointment_cancellation_email with retry.

    The sync version returns bool; this normalizes to dict.
    """
    def _send():
        result = send_appointment_cancellation_email(**kwargs)
        if isinstance(result, bool):
            return {"success": result, "error": None if result else "Send failed"}
        return result

    return await _retry_email_send(_send, max_retries=3)


async def async_send_team_member_notification_email(**kwargs) -> dict:
    """Async wrapper for send_team_member_notification_email with retry.

    The sync version returns bool; this normalizes to dict.
    """
    def _send():
        result = send_team_member_notification_email(**kwargs)
        if isinstance(result, bool):
            return {"success": result, "error": None if result else "Send failed"}
        return result

    return await _retry_email_send(_send, max_retries=3)


async def async_send_team_member_cancellation_email(**kwargs) -> dict:
    """Async wrapper for send_team_member_cancellation_email with retry.

    The sync version returns bool; this normalizes to dict.
    """
    def _send():
        result = send_team_member_cancellation_email(**kwargs)
        if isinstance(result, bool):
            return {"success": result, "error": None if result else "Send failed"}
        return result

    return await _retry_email_send(_send, max_retries=3)


async def async_send_appointment_reminder_email(**kwargs) -> dict:
    """Async wrapper for send_appointment_reminder_email with retry."""
    return await _async_email_with_retry(
        send_appointment_reminder_email,
        "appointment_reminder",
        **kwargs,
    )


async def async_send_ai_booking_confirmation_email(**kwargs) -> dict:
    """Async wrapper for send_ai_booking_confirmation_email with retry."""
    return await _async_email_with_retry(
        send_ai_booking_confirmation_email,
        "ai_booking_confirmation",
        **kwargs,
    )


async def async_send_pre_appointment_prep_email(**kwargs) -> dict:
    """Async wrapper for send_pre_appointment_prep_email with retry."""
    return await _async_email_with_retry(
        send_pre_appointment_prep_email,
        "pre_appointment_prep",
        **kwargs,
    )


async def async_send_no_show_recovery_email(**kwargs) -> dict:
    """Async wrapper for send_no_show_recovery_email with retry."""
    return await _async_email_with_retry(
        send_no_show_recovery_email,
        "no_show_recovery",
        **kwargs,
    )


async def _async_email_with_retry(
    sync_fn,
    label: str,
    max_retries: int = 3,
    **kwargs,
) -> dict:
    """Run a sync email function in a thread with retry + exponential backoff.

    This is the core async retry helper. It wraps the sync function via
    asyncio.to_thread and feeds it into _retry_email_send.
    """
    def _send():
        return sync_fn(**kwargs)

    result = await _retry_email_send(_send, max_retries=max_retries)
    if not result.get("success"):
        logger.error(f"Async {label} email failed after retries: {result.get('error')}")
    return result


# ============================================================================
# Fire-and-forget helper
# ============================================================================

def schedule_email_task(coro) -> None:
    """Schedule an async email coroutine as a fire-and-forget background task.

    Email failures are logged but never propagate to the caller, ensuring
    appointment operations are never interrupted by notification issues.

    Usage from a sync context::

        schedule_email_task(async_send_appointment_confirmation_email(
            attendee_email="...",
            ...
        ))

    Usage from an async context::

        asyncio.ensure_future(async_send_appointment_confirmation_email(...))
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        task = loop.create_task(coro)
        task.add_done_callback(_email_task_done_callback)
    else:
        # No running loop -- run synchronously in a new loop (fallback).
        # This path is only hit in non-async contexts like CLI scripts.
        # DATA-015: Use get_event_loop() + run_until_complete() when possible,
        # falling back to asyncio.run() only when no loop exists at all.
        try:
            try:
                fallback_loop = asyncio.get_event_loop()
                if fallback_loop.is_running():
                    # Shouldn't reach here (caught above), but guard anyway
                    asyncio.ensure_future(coro, loop=fallback_loop)
                else:
                    fallback_loop.run_until_complete(coro)
            except RuntimeError:
                # No event loop at all -- create one
                asyncio.run(coro)
        except Exception as e:
            logger.error(f"Fire-and-forget email task failed (sync fallback): {e}")


def _email_task_done_callback(task: asyncio.Task) -> None:
    """Callback for fire-and-forget email tasks -- logs exceptions."""
    try:
        exc = task.exception()
        if exc:
            logger.error(f"Background email task failed: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        logger.warning("Background email task was cancelled")
    except Exception as e:
        logger.error(f"Error in email task done callback: {e}")
