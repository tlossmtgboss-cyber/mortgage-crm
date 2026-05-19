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
            return False, (
                f"I can't send that right now — it's {local_now.strftime('%I:%M %p')} "
                f"in the recipient's timezone ({tz_name}), which is outside the "
                f"allowed 8 AM - 9 PM window. Want me to schedule it for tomorrow morning?"
            )
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
            # TENANT-017: Set RLS context if org_id is known
            if organization_id:
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(db, organization_id)
                except Exception as _exc:  # noqa: BLE001
                    pass
        except Exception as e:
            logger.error(f"Cannot create DB session: {e}")
            return False, f"Consent check error: {e}"

    try:
        # 1-2. Unified consent resolution (replaces separate DNC + ChannelPreference checks).
        # The resolver checks ALL consent sources in strict priority order:
        #   sms_opt_outs > internal_dnc > contact_dnc_status > channel_prefs > consent records
        # See services/sms_consent_resolver.py for the full priority chain.
        from services.sms_consent_resolver import resolve_consent

        consent_resolution = resolve_consent(phone, organization_id=organization_id, db=db)

        if not consent_resolution.allowed:
            logger.warning(
                "SMS blocked by consent resolver: %s (source=%s)",
                consent_resolution.reason, consent_resolution.source,
            )
            return False, consent_resolution.reason

        # 3. TCPA: Check contact hours (8am-9pm recipient local time)
        # Resolve timezone from lead's channel_preferences or phone area code.
        recipient_tz = None
        try:
            from database.models.communication import ChannelPreference
            from database.models.lead_loan import Lead

            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) == 11 and digits.startswith('1'):
                digits = digits[1:]

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
                        recipient_tz = getattr(pref, 'timezone', None)
        except Exception as _exc:  # noqa: BLE001
            pass  # Timezone lookup is best-effort

        if not recipient_tz:
            try:
                from telephony.compliance import resolve_recipient_timezone
                recipient_tz = resolve_recipient_timezone(phone)
            except ImportError:
                pass  # Will default to Eastern in _check_contact_hours

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
