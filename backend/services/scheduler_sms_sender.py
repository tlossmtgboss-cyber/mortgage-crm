"""
Scheduler SMS Sender
Extracted from scheduler_email_service.py

Provides:
- Appointment confirmation SMS via Telnyx
- Appointment update SMS via Telnyx
- Appointment reminder SMS via Telnyx

TCPA/DNC consent checking and contact hours enforcement have been extracted
to ``services.sms_compliance``. This module re-exports them for backward
compatibility.
"""

import logging
import os
import time as _time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# SMS retry configuration
_SMS_MAX_RETRIES = int(os.getenv("SMS_MAX_RETRIES", "3"))
_SMS_BASE_DELAY = float(os.getenv("SMS_BASE_DELAY", "1.0"))  # seconds


def _send_sms_with_retry(from_number: str, to_number: str, text: str,
                          max_retries: int = _SMS_MAX_RETRIES,
                          base_delay: float = _SMS_BASE_DELAY):
    """Send an SMS via Telnyx with exponential backoff retry.

    Returns (success: bool, message_id: str or None, error: str or None).
    """
    import telnyx

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            message = telnyx.Message.create(
                from_=from_number,
                to=to_number,
                text=text,
            )
            msg_id = (getattr(message, 'id', None)
                      or getattr(getattr(message, 'data', None), 'id', None)
                      or 'unknown')
            return True, msg_id, None
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                logger.warning(
                    f"SMS send attempt {attempt}/{max_retries} failed, "
                    f"retrying in {delay:.1f}s: {e}"
                )
                _time.sleep(delay)
            else:
                logger.error(f"SMS send failed after {max_retries} attempts: {e}")

    return False, None, last_error


def _mask_phone(phone):
    """OBS-004: Mask phone number for safe logging."""
    if not phone or len(phone) < 7:
        return "***"
    return phone[:2] + "***" + phone[-4:]


# --- Re-exports from shared compliance module (backward compatibility) ---
from services.sms_compliance import check_sms_consent, _check_contact_hours  # noqa: F401


# ============================================================================
# SMS sending functions
# ============================================================================

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
            logger.info(f"SMS consent check blocked confirmation to {_mask_phone(attendee_phone)}: {reason}")
            return False

        from_number = os.getenv("TELNYX_PHONE_NUMBER")

        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping SMS confirmation")
            return False

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} is confirmed for {appointment_date} at {appointment_time}. We'll send a reminder before your call. Reply HELP for assistance."

        if len(message_body) > 160:
            logger.warning(f"SMS body is {len(message_body)} chars (>160), will be sent as multi-segment")

        success, msg_id, error = _send_sms_with_retry(from_number, attendee_phone, message_body)
        if success:
            logger.info(f"Appointment confirmation SMS sent to {_mask_phone(attendee_phone)}, ID: {msg_id}")
        return success

    except Exception as e:
        logger.error(f"Failed to send appointment confirmation SMS: {e}")
        return False


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
            logger.info(f"SMS consent check blocked update to {_mask_phone(attendee_phone)}: {reason}")
            return False

        from_number = os.getenv("TELNYX_PHONE_NUMBER")

        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping SMS update")
            return False

        team_member_text = f" with {team_member_name}" if team_member_name else ""
        message_body = f"Hi {attendee_name}! Your appointment{team_member_text} has been UPDATED to {appointment_date} at {appointment_time}. Please check your email for the updated calendar invite."

        success, msg_id, error = _send_sms_with_retry(from_number, attendee_phone, message_body)
        if success:
            logger.info(f"Appointment update SMS sent to {_mask_phone(attendee_phone)}, ID: {msg_id}")
        return success

    except Exception as e:
        logger.error(f"Failed to send appointment update SMS: {e}")
        return False


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
            logger.info(f"SMS consent check blocked reminder to {_mask_phone(attendee_phone)}: {reason}")
            return {"success": False, "error": f"Consent blocked: {reason}"}

        from_number = os.getenv("TELNYX_PHONE_NUMBER")
        if not from_number:
            logger.warning("TELNYX_PHONE_NUMBER not configured - skipping reminder SMS")
            return {"success": False, "error": "SMS not configured"}

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

        success, msg_id, error = _send_sms_with_retry(from_number, attendee_phone, message_body)
        if success:
            logger.info(f"Appointment reminder SMS sent to {_mask_phone(attendee_phone)}, ID: {msg_id}")
            return {"success": True, "message_id": msg_id}
        return {"success": False, "error": error}

    except Exception as e:
        logger.error(f"Failed to send appointment reminder SMS: {e}")
        return {"success": False, "error": str(e)}
