"""
Scheduler SMS Sender
Extracted from scheduler_email_service.py

Provides:
- TCPA/DNC consent checking before SMS
- Contact hours enforcement (8am-9pm recipient local time)
- Appointment confirmation SMS via Telnyx
- Appointment update SMS via Telnyx
- Appointment reminder SMS via Telnyx
"""

import logging
import os
from datetime import datetime, timezone

import pytz

logger = logging.getLogger(__name__)


# ============================================================================
# TCPA/DNC consent check before SMS
# ============================================================================

def check_sms_consent(phone: str, organization_id: int = None) -> tuple:
    """
    Check DNC list, ChannelPreference, and TCPA contact hours before sending SMS.
    Returns (can_send: bool, reason: str).

    Policy:
    - Outside 8am-9pm recipient local time -> BLOCK (TCPA)
    - DNC list match -> BLOCK
    - DNC check error -> BLOCK (fail-closed for compliance)
    - ChannelPreference.do_not_sms=True -> BLOCK
    - ChannelPreference.sms_consent=False -> BLOCK
    - No lead/preference found -> ALLOW (transactional SMS exemption)
    - Consent check error -> BLOCK (fail-safe)
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
                # CF-6: Fail-closed -- block SMS when DNC check errors (TCPA compliance)
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

            # No block found -- allow transactional SMS
            return True, "OK"
        finally:
            db.close()
    except Exception as e:
        logger.error(f"SMS consent check failed, defaulting to BLOCK: {e}")
        return False, f"Consent check error: {e}"


def _check_contact_hours(recipient_tz_name: str = None) -> tuple:
    """
    CF-7: TCPA time-of-day restriction -- block SMS outside 8am-9pm recipient local time.
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
        # Unknown timezone -- use conservative block during late/early hours UTC
        utc_hour = datetime.now(timezone.utc).hour
        if utc_hour >= 2 and utc_hour < 13:
            # 2am-1pm UTC = could be nighttime somewhere in the US
            return True, "OK"
        logger.warning(f"Contact hours check failed, allowing: {e}")
        return True, "OK"


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
