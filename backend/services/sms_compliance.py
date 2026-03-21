"""
SMS Compliance Module
Canonical location for TCPA/DNC consent checking before sending SMS.

Provides:
- check_sms_consent(): DNC list, ChannelPreference, and TCPA consent check
- _check_contact_hours(): TCPA 8am-9pm recipient local time enforcement

Previously lived in services.scheduler_sms_sender. Extracted here so all
SMS-sending modules can share a single compliance implementation.
"""

import logging
from datetime import datetime, timezone

import pytz

logger = logging.getLogger(__name__)


# ============================================================================
# TCPA contact hours enforcement
# ============================================================================

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
        # Unknown timezone -- fail closed to avoid TCPA violation
        logger.warning(f"Contact hours check failed, blocking SMS (fail-closed): {e}")
        return False, f"TCPA: Contact hours check failed ({e})"


# ============================================================================
# TCPA/DNC consent check before SMS
# ============================================================================

def check_sms_consent(phone: str, organization_id: int = None, db=None) -> tuple:
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
    - Model import error -> ALLOW with warning (transactional exemption)
    """
    if not phone:
        return False, "No phone number provided"

    # Use caller's session when available to avoid pool exhaustion
    owns_session = False
    if db is None:
        try:
            from database import SessionLocal
            db = SessionLocal()
            owns_session = True
        except Exception as e:
            logger.error(f"Cannot create DB session: {e}")
            return False, f"Consent check error: {e}"

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
        recipient_tz = None
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
                # Get timezone from channel_preferences (not leads table)
                pref = db.query(ChannelPreference).filter(
                    ChannelPreference.lead_id == lead.id
                ).first()
                if pref:
                    recipient_tz = getattr(pref, 'timezone', None)
                    if getattr(pref, 'do_not_sms', False):
                        logger.warning(f"SMS blocked - do_not_sms flag: {phone}")
                        return False, "Contact has opted out of SMS"
                    if hasattr(pref, 'sms_consent') and pref.sms_consent is False:
                        logger.warning(f"SMS blocked - no sms_consent: {phone}")
                        return False, "No SMS consent on file"
        except ImportError:
            # Model not available — allow with warning (transactional exemption)
            # Consistent with sms_compliance_gate.py behavior
            logger.warning("ChannelPreference model not available — allowing (transactional exemption)")

        # 3. TCPA: Check contact hours (8am-9pm recipient local time)
        # Done AFTER lead lookup so we can use the lead's actual timezone
        contact_hours_ok, hours_reason = _check_contact_hours(recipient_tz)
        if not contact_hours_ok:
            return False, hours_reason

        # No block found -- allow transactional SMS
        return True, "OK"
    except Exception as e:
        logger.error(f"SMS consent check failed, defaulting to BLOCK: {e}")
        return False, f"Consent check error: {e}"
    finally:
        if owns_session:
            db.close()
