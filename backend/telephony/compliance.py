"""
Compliance checks for DNC, calling hours, and rate limits

Provides TCPA-compliant calling hour validation, Do Not Call list management,
rate limiting, and multi-agent collision prevention via soft locks.
"""

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Try to import pytz, fall back to zoneinfo if not available
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    from zoneinfo import ZoneInfo
    HAS_PYTZ = False
    logger.info("pytz not available, using zoneinfo")


class ComplianceError(Exception):
    """Raised when a compliance check fails"""
    pass


import os
import re


# ============================================================================
# Area code → timezone mapping (covers major US metro areas)
# Falls back to America/New_York (Eastern) for unknown codes — the most
# restrictive US timezone for TCPA purposes (earliest 9 PM cutoff).
# ============================================================================

_AREA_CODE_TZ: Dict[str, str] = {
    # Eastern
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "224": "America/Chicago",  "225": "America/Chicago",
    "229": "America/New_York", "231": "America/New_York", "234": "America/New_York",
    "239": "America/New_York", "240": "America/New_York", "248": "America/New_York",
    "251": "America/Chicago",  "252": "America/New_York", "253": "America/Los_Angeles",
    "256": "America/Chicago",  "260": "America/New_York", "267": "America/New_York",
    "269": "America/New_York", "270": "America/New_York", "272": "America/New_York",
    "276": "America/New_York", "278": "America/New_York", "281": "America/Chicago",
    "301": "America/New_York", "302": "America/New_York", "303": "America/Denver",
    "304": "America/New_York", "305": "America/New_York", "307": "America/Denver",
    "308": "America/Chicago",  "309": "America/Chicago",  "310": "America/Los_Angeles",
    "312": "America/Chicago",  "313": "America/New_York", "314": "America/Chicago",
    "315": "America/New_York", "316": "America/Chicago",  "317": "America/New_York",
    "318": "America/Chicago",  "319": "America/Chicago",  "320": "America/Chicago",
    "321": "America/New_York", "323": "America/Los_Angeles", "325": "America/Chicago",
    "330": "America/New_York", "331": "America/Chicago",  "334": "America/Chicago",
    "336": "America/New_York", "337": "America/Chicago",  "339": "America/New_York",
    "340": "America/New_York", "346": "America/Chicago",  "347": "America/New_York",
    "351": "America/New_York", "352": "America/New_York", "360": "America/Los_Angeles",
    "361": "America/Chicago",  "364": "America/New_York", "380": "America/New_York",
    "385": "America/Denver",   "386": "America/New_York", "401": "America/New_York",
    "402": "America/Chicago",  "404": "America/New_York", "405": "America/Chicago",
    "406": "America/Denver",   "407": "America/New_York", "408": "America/Los_Angeles",
    "409": "America/Chicago",  "410": "America/New_York", "412": "America/New_York",
    "413": "America/New_York", "414": "America/Chicago",  "415": "America/Los_Angeles",
    "417": "America/Chicago",  "419": "America/New_York", "423": "America/New_York",
    "424": "America/Los_Angeles", "425": "America/Los_Angeles",
    "430": "America/Chicago",  "432": "America/Chicago",  "434": "America/New_York",
    "435": "America/Denver",   "440": "America/New_York", "442": "America/Los_Angeles",
    "443": "America/New_York", "458": "America/Los_Angeles", "463": "America/New_York",
    "469": "America/Chicago",  "470": "America/New_York", "475": "America/New_York",
    "478": "America/New_York", "479": "America/Chicago",  "480": "America/Phoenix",
    "484": "America/New_York", "501": "America/Chicago",  "502": "America/New_York",
    "503": "America/Los_Angeles", "504": "America/Chicago",
    "505": "America/Denver",   "507": "America/Chicago",  "508": "America/New_York",
    "509": "America/Los_Angeles", "510": "America/Los_Angeles",
    "512": "America/Chicago",  "513": "America/New_York", "515": "America/Chicago",
    "516": "America/New_York", "517": "America/New_York", "518": "America/New_York",
    "520": "America/Phoenix",  "530": "America/Los_Angeles",
    "531": "America/Chicago",  "534": "America/Chicago",  "539": "America/Chicago",
    "540": "America/New_York", "541": "America/Los_Angeles",
    "551": "America/New_York", "559": "America/Los_Angeles",
    "561": "America/New_York", "562": "America/Los_Angeles",
    "563": "America/Chicago",  "567": "America/New_York", "570": "America/New_York",
    "571": "America/New_York", "573": "America/Chicago",  "574": "America/New_York",
    "575": "America/Denver",   "580": "America/Chicago",  "585": "America/New_York",
    "586": "America/New_York", "601": "America/Chicago",  "602": "America/Phoenix",
    "603": "America/New_York", "605": "America/Chicago",  "606": "America/New_York",
    "607": "America/New_York", "608": "America/Chicago",  "609": "America/New_York",
    "610": "America/New_York", "612": "America/Chicago",  "614": "America/New_York",
    "615": "America/Chicago",  "616": "America/New_York", "617": "America/New_York",
    "618": "America/Chicago",  "619": "America/Los_Angeles",
    "620": "America/Chicago",  "623": "America/Phoenix",
    "626": "America/Los_Angeles", "628": "America/Los_Angeles",
    "629": "America/Chicago",  "630": "America/Chicago",  "631": "America/New_York",
    "636": "America/Chicago",  "641": "America/Chicago",  "646": "America/New_York",
    "650": "America/Los_Angeles", "651": "America/Chicago",
    "657": "America/Los_Angeles", "660": "America/Chicago",
    "661": "America/Los_Angeles", "662": "America/Chicago",
    "667": "America/New_York", "669": "America/Los_Angeles",
    "678": "America/New_York", "681": "America/New_York",
    "682": "America/Chicago",  "689": "America/New_York",
    "701": "America/Chicago",  "702": "America/Los_Angeles",
    "703": "America/New_York", "704": "America/New_York", "706": "America/New_York",
    "707": "America/Los_Angeles", "708": "America/Chicago",
    "712": "America/Chicago",  "713": "America/Chicago",  "714": "America/Los_Angeles",
    "715": "America/Chicago",  "716": "America/New_York", "717": "America/New_York",
    "718": "America/New_York", "719": "America/Denver",   "720": "America/Denver",
    "724": "America/New_York", "725": "America/Los_Angeles",
    "727": "America/New_York", "731": "America/Chicago",  "732": "America/New_York",
    "734": "America/New_York", "737": "America/Chicago",  "740": "America/New_York",
    "743": "America/New_York", "747": "America/Los_Angeles",
    "754": "America/New_York", "757": "America/New_York", "760": "America/Los_Angeles",
    "762": "America/New_York", "763": "America/Chicago",  "765": "America/New_York",
    "769": "America/Chicago",  "770": "America/New_York", "772": "America/New_York",
    "773": "America/Chicago",  "774": "America/New_York", "775": "America/Los_Angeles",
    "779": "America/Chicago",  "781": "America/New_York", "786": "America/New_York",
    "801": "America/Denver",   "802": "America/New_York", "803": "America/New_York",
    "804": "America/New_York", "805": "America/Los_Angeles",
    "806": "America/Chicago",  "808": "Pacific/Honolulu",
    "810": "America/New_York", "812": "America/New_York", "813": "America/New_York",
    "814": "America/New_York", "815": "America/Chicago",  "816": "America/Chicago",
    "817": "America/Chicago",  "818": "America/Los_Angeles",
    "828": "America/New_York", "830": "America/Chicago",  "831": "America/Los_Angeles",
    "832": "America/Chicago",  "843": "America/New_York", "845": "America/New_York",
    "847": "America/Chicago",  "848": "America/New_York", "850": "America/New_York",
    "854": "America/New_York", "856": "America/New_York", "857": "America/New_York",
    "858": "America/Los_Angeles", "859": "America/New_York",
    "860": "America/New_York", "862": "America/New_York", "863": "America/New_York",
    "864": "America/New_York", "870": "America/Chicago",
    "878": "America/New_York", "901": "America/Chicago",  "903": "America/Chicago",
    "904": "America/New_York", "907": "America/Anchorage",
    "908": "America/New_York", "909": "America/Los_Angeles",
    "910": "America/New_York", "912": "America/New_York", "913": "America/Chicago",
    "914": "America/New_York", "915": "America/Denver",   "916": "America/Los_Angeles",
    "917": "America/New_York", "918": "America/Chicago",  "919": "America/New_York",
    "920": "America/Chicago",  "925": "America/Los_Angeles",
    "928": "America/Phoenix",  "929": "America/New_York",
    "931": "America/Chicago",  "936": "America/Chicago",  "937": "America/New_York",
    "940": "America/Chicago",  "941": "America/New_York", "947": "America/New_York",
    "949": "America/Los_Angeles", "951": "America/Los_Angeles",
    "952": "America/Chicago",  "954": "America/New_York", "956": "America/Chicago",
    "959": "America/New_York", "970": "America/Denver",   "971": "America/Los_Angeles",
    "972": "America/Chicago",  "973": "America/New_York", "978": "America/New_York",
    "979": "America/Chicago",  "980": "America/New_York", "984": "America/New_York",
    "985": "America/Chicago",
}


def resolve_recipient_timezone(phone: str) -> str:
    """
    Resolve the IANA timezone for a US phone number from its area code.

    Falls back to America/New_York (Eastern) when the area code is unknown,
    which is the most restrictive US timezone for TCPA purposes (earliest
    9 PM cutoff relative to UTC).

    This function is the canonical timezone resolver for TCPA compliance
    and should be used by all modules that need to check quiet hours
    against a recipient's phone number.

    Args:
        phone: Phone number in any format (+1XXXXXXXXXX, (XXX) XXX-XXXX, etc.)

    Returns:
        IANA timezone string (e.g. 'America/New_York', 'America/Los_Angeles')
    """
    if not phone:
        return "America/New_York"

    digits = re.sub(r'\D', '', phone)
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]

    if len(digits) >= 10:
        area_code = digits[:3]
        return _AREA_CODE_TZ.get(area_code, "America/New_York")

    return "America/New_York"


def verify_voice_consent(
    phone_number: str,
    org_id: int,
    db: Session,
    actor_user_id: Optional[int] = None,
    actor_ip: Optional[str] = None,
) -> Tuple[bool, Optional[Any]]:
    """
    Check whether a phone number has active TCPA voice consent for AI calls.

    Queries the VoiceConsent table for a consent record that is:
      - Scoped to the given organization
      - Not revoked (revoked_at IS NULL)
      - Not expired (retention_expires_at > now OR NULL)
      - consent_type is NOT 'REVOKED'

    Every verification (pass or fail) is logged to both VoiceConsentAudit AND
    the unified ConsentAuditLog so there is a provable record that consent was
    checked before each AI voice call.

    Args:
        phone_number: The phone number to verify consent for (any format).
        org_id:       Organization ID for tenant isolation.
        db:           SQLAlchemy session.
        actor_user_id: Optional user ID performing the verification.
        actor_ip:      Optional IP address of the actor.

    Returns:
        Tuple of (has_consent, consent_record).
        has_consent=True means an active consent record exists.
        consent_record is the VoiceConsent instance if found, else None.
    """
    try:
        from database.models.voice_consent import (
            VoiceConsent,
            VoiceConsentAudit,
            CONSENT_TYPE_REVOKED,
            AUDIT_ACTION_VERIFIED,
        )
    except ImportError:
        logger.error(
            "Could not import VoiceConsent models — "
            "blocking call (fail-closed)"
        )
        return False, None

    # Normalize phone to digits only
    digits = re.sub(r'\D', '', phone_number or '')
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]

    if not digits:
        logger.warning("verify_voice_consent called with empty phone number")
        return False, None

    now = datetime.now(timezone.utc)

    try:
        # Find active consent: not revoked, not expired, not REVOKED type
        consent = db.query(VoiceConsent).filter(
            and_(
                VoiceConsent.organization_id == org_id,
                VoiceConsent.phone_number.ilike(f"%{digits[-10:]}"),
                VoiceConsent.consent_type != CONSENT_TYPE_REVOKED,
                VoiceConsent.revoked_at.is_(None),
            )
        ).filter(
            # retention_expires_at is NULL (no expiry) or in the future
            (VoiceConsent.retention_expires_at.is_(None)) |
            (VoiceConsent.retention_expires_at > now)
        ).order_by(
            VoiceConsent.consented_at.desc()
        ).first()

        # Log the verification attempt (pass or fail)
        audit_details = {
            "phone_digits_last4": digits[-4:] if len(digits) >= 4 else digits,
            "has_consent": consent is not None,
        }
        if consent:
            audit_details["consent_type"] = consent.consent_type
            audit_details["consent_channel"] = consent.consent_channel
            audit_details["consented_at"] = consent.consented_at.isoformat() if consent.consented_at else None

            audit_entry = VoiceConsentAudit(
                voice_consent_id=consent.id,
                action=AUDIT_ACTION_VERIFIED,
                actor_user_id=actor_user_id,
                actor_ip=actor_ip,
                details=audit_details,
            )
            db.add(audit_entry)
            # Don't commit — let the caller's transaction handle it

        # Also log to unified ConsentAuditLog
        try:
            from telephony.consent_audit import log_consent_verified
            log_consent_verified(
                db,
                organization_id=org_id,
                contact_id=consent.lead_id if consent else None,
                consent_type="voice_ai",
                verification_result="passed" if consent else "failed",
                phone=phone_number,
                actor_user_id=actor_user_id,
                source_table="voice_consents",
                source_record_id=str(consent.id) if consent else None,
                reason="Voice consent verified" if consent else "No active voice consent found",
                details=audit_details,
            )
        except Exception as e:
            logger.debug(f"ConsentAuditLog write skipped: {e}")

        if consent:
            logger.info(
                f"Voice consent verified for ***{digits[-4:]}, "
                f"type={consent.consent_type}, org={org_id}"
            )
            return True, consent
        else:
            logger.warning(
                f"No active voice consent found for ***{digits[-4:]}, org={org_id}"
            )
            return False, None

    except Exception as e:
        logger.error(f"Error verifying voice consent for ***{digits[-4:]}: {e}")
        # Fail closed: no consent verification = no call
        return False, None


class ComplianceChecker:
    """
    Handles compliance checks for outbound calling

    - Do Not Call (DNC) list checking
    - TCPA calling hours validation (8 AM - 9 PM local time)
    - Daily rate limiting per agent
    - Soft locks to prevent multi-agent collision
    """

    # TCPA Safe Harbor calling hours
    CALLING_HOURS_START = time(8, 0)   # 8 AM
    CALLING_HOURS_END = time(21, 0)    # 9 PM

    def __init__(self, db: Session, organization_id: Optional[int] = None):
        self.db = db
        self.organization_id = organization_id
        if HAS_PYTZ:
            self.default_timezone = pytz.timezone('America/New_York')
        else:
            self.default_timezone = ZoneInfo('America/New_York')

    # =========================================================================
    # Compliance Decision Logging
    # =========================================================================

    def _log_decision(
        self,
        decision_type: str,
        phone_number: str,
        decision: str,
        reason: str = None,
        details: dict = None,
        contact_id: int = None,
        lead_id: int = None,
        user_id: int = None,
    ):
        """Log a compliance decision to the immutable audit log."""
        try:
            from database.models.compliance_log import ComplianceDecisionLog

            # Mask phone number for PII protection
            masked_phone = f"***{phone_number[-4:]}" if phone_number and len(phone_number) >= 4 else "unknown"

            log_entry = ComplianceDecisionLog(
                organization_id=self.organization_id,
                user_id=user_id,
                decision_type=decision_type,
                phone_number=masked_phone,
                contact_id=contact_id,
                lead_id=lead_id,
                decision=decision,
                reason=reason,
                details=details,
            )
            self.db.add(log_entry)
            # Don't commit here -- let the caller's transaction handle it
        except Exception as e:
            logger.error(f"Failed to log compliance decision: {e}")

    def _log_consent_audit(
        self,
        consent_type: str,
        action: str,
        verification_result: Optional[str] = None,
        contact_id: Optional[int] = None,
        phone: Optional[str] = None,
        method: Optional[str] = None,
        source_table: Optional[str] = None,
        source_record_id: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[dict] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ):
        """Log a consent event to the immutable ConsentAuditLog."""
        try:
            from telephony.consent_audit import log_consent_event
            log_consent_event(
                self.db,
                organization_id=self.organization_id,
                contact_id=contact_id,
                consent_type=consent_type,
                action=action,
                verification_result=verification_result,
                method=method,
                ip_address=ip_address,
                source_table=source_table,
                source_record_id=source_record_id,
                actor_user_id=actor_user_id,
                phone=phone,
                reason=reason,
                details=details,
            )
        except Exception as e:
            logger.debug(f"ConsentAuditLog write skipped: {e}")

    # =========================================================================
    # DNC Checks
    # =========================================================================

    def check_dnc(self, phone_number: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a phone number is on the Do Not Call list

        Args:
            phone_number: Phone number to check

        Returns:
            Tuple of (is_on_dnc, reason)
        """
        # Import here to avoid circular imports
        try:
            from database.models import ContactDNCStatus
        except ImportError:
            # Fail closed: treat as ON the DNC list to prevent compliance bypass
            logger.error("Could not import ContactDNCStatus model — blocking call (fail-closed)")
            return True, "DNC check unavailable (import failure) — call blocked"

        # Normalize phone number
        digits = self._normalize_phone(phone_number)

        # Check internal DNC list (always scoped to organization)
        dnc_query = self.db.query(ContactDNCStatus).filter(
            ContactDNCStatus.phone_number == digits
        )
        if self.organization_id:
            dnc_query = dnc_query.filter(
                ContactDNCStatus.organization_id == self.organization_id
            )
        dnc_entry = dnc_query.first()

        if dnc_entry:
            self._log_decision(
                decision_type="dnc_check",
                phone_number=digits,
                decision="blocked",
                reason=f"On DNC list: {dnc_entry.reason}",
                details={"dnc_reason": dnc_entry.reason},
            )
            return True, dnc_entry.reason

        self._log_decision(
            decision_type="dnc_check",
            phone_number=digits,
            decision="allowed",
            reason="Not on DNC list",
        )
        return False, None

    def check_dnc_by_contact(self, contact_id: int) -> bool:
        """
        Check if a contact has DNC flag set

        Args:
            contact_id: Contact/Lead ID

        Returns:
            True if on DNC list
        """
        try:
            from database.models import Lead
            lead_query = self.db.query(Lead).filter(Lead.id == contact_id)
            if self.organization_id:
                lead_query = lead_query.filter(Lead.organization_id == self.organization_id)
            contact = lead_query.first()

            if not contact:
                return False

            # Check for DNC flags on the contact
            if hasattr(contact, 'dnc_flag') and contact.dnc_flag:
                return True
            if hasattr(contact, 'phone_opt_out') and contact.phone_opt_out:
                return True

            # Also check the phone number against DNC list
            if contact.phone:
                is_dnc, _ = self.check_dnc(contact.phone)
                return is_dnc

        except Exception as e:
            logger.error(f"Error checking DNC for contact {contact_id}: {e}")

        return False

    def add_to_dnc(self, phone_number: str, reason: str, added_by_id: int) -> bool:
        """Add a phone number to the Do Not Call list"""
        try:
            from database.models import ContactDNCStatus
        except ImportError:
            logger.error("Could not import ContactDNCStatus model")
            return False

        digits = self._normalize_phone(phone_number)

        try:
            # Scope DNC query to organization
            existing_query = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            )
            if self.organization_id:
                existing_query = existing_query.filter(
                    ContactDNCStatus.organization_id == self.organization_id
                )
            existing = existing_query.first()

            if existing:
                existing.reason = reason
                existing.added_by_id = added_by_id
            else:
                dnc_entry = ContactDNCStatus(
                    phone_number=digits,
                    reason=reason,
                    added_by_id=added_by_id,
                    organization_id=self.organization_id,
                )
                self.db.add(dnc_entry)

            self.db.commit()
            logger.info(f"Added {digits} to DNC list: {reason}")
            return True

        except Exception as e:
            logger.error(f"Error adding to DNC: {e}")
            self.db.rollback()
            return False

    def remove_from_dnc(self, phone_number: str) -> bool:
        """Remove a phone number from the Do Not Call list"""
        try:
            from database.models import ContactDNCStatus
        except ImportError:
            return False

        digits = self._normalize_phone(phone_number)

        try:
            remove_query = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            )
            if self.organization_id:
                remove_query = remove_query.filter(
                    ContactDNCStatus.organization_id == self.organization_id
                )
            deleted = remove_query.delete()
            self.db.commit()
            if deleted:
                logger.info(f"Removed {digits} from DNC list")
            return deleted > 0
        except Exception as e:
            logger.error(f"Error removing from DNC: {e}")
            self.db.rollback()
            return False

    # =========================================================================
    # Calling Hours
    # =========================================================================

    def check_calling_hours(self, phone_number: str) -> Tuple[bool, Optional[str]]:
        """
        Check if current time is within legal calling hours in the
        RECIPIENT's timezone.

        TCPA Safe Harbor: 8 AM - 9 PM recipient local time.
        Timezone is resolved from the phone number's area code.
        Falls back to US/Eastern (most restrictive) if unknown.

        Args:
            phone_number: Recipient phone number (any format)

        Returns:
            Tuple of (is_allowed, reason_message)
        """
        contact_tz = self._get_timezone_for_phone(phone_number)
        now_utc = datetime.now(timezone.utc)

        if HAS_PYTZ:
            now_local = now_utc.astimezone(contact_tz)
        else:
            now_local = now_utc.astimezone(contact_tz)

        current_time = now_local.time()
        digits = self._normalize_phone(phone_number)
        tz_name = str(contact_tz)

        if current_time < self.CALLING_HOURS_START or current_time >= self.CALLING_HOURS_END:
            if current_time < self.CALLING_HOURS_START:
                schedule_hint = "Want me to queue it for 8 AM this morning?"
            else:
                schedule_hint = "Want me to queue it for 8 AM tomorrow morning?"
            reason = (
                f"I can't send that right now — it's {now_local.strftime('%I:%M %p')} "
                f"in the recipient's timezone ({tz_name}), which is outside "
                f"the allowed 8 AM - 9 PM window. "
                f"{schedule_hint}"
            )
            self._log_decision(
                decision_type="calling_hours",
                phone_number=digits,
                decision="blocked",
                reason=reason,
                details={
                    "local_time": now_local.strftime('%H:%M'),
                    "timezone": tz_name,
                    "recipient_local_time": now_local.isoformat(),
                },
            )
            return False, reason

        allowed_msg = (
            f"Within calling hours — recipient local time is "
            f"{now_local.strftime('%I:%M %p')} {tz_name}"
        )
        self._log_decision(
            decision_type="calling_hours",
            phone_number=digits,
            decision="allowed",
            reason=allowed_msg,
            details={
                "local_time": now_local.strftime('%H:%M'),
                "timezone": tz_name,
            },
        )
        return True, allowed_msg

    def _get_timezone_for_phone(self, phone_number: str):
        """Determine timezone from phone number area code"""
        digits = self._normalize_phone(phone_number)

        if len(digits) >= 10:
            # Get area code (skip country code if present)
            if len(digits) == 11 and digits.startswith('1'):
                area_code = digits[1:4]
            else:
                area_code = digits[:3]

            tz_str = self._area_code_to_timezone(area_code)
            if tz_str:
                if HAS_PYTZ:
                    return pytz.timezone(tz_str)
                else:
                    return ZoneInfo(tz_str)

        return self.default_timezone

    def _area_code_to_timezone(self, area_code: str) -> Optional[str]:
        """Map US area code to IANA timezone string.

        Uses the shared _AREA_CODE_TZ mapping which covers all major US
        metro areas. Falls back to None (caller defaults to Eastern,
        the most restrictive US timezone for TCPA).
        """
        return _AREA_CODE_TZ.get(area_code)

    # =========================================================================
    # Rate Limiting
    # =========================================================================

    def check_rate_limit(self, agent_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if agent has exceeded daily call limit.

        Uses SELECT ... FOR UPDATE to lock the matching call_logs rows so
        concurrent transactions block until this check + the caller's
        subsequent INSERT complete. Without this, two concurrent calls
        could both read count=199 (limit 200), both pass, and both insert
        — exceeding the TCPA-critical daily limit.

        Args:
            agent_id: Agent/User ID

        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        try:
            from database.models import AgentTelephonySettings, CallLog
        except ImportError:
            logger.error("Could not import AgentTelephonySettings/CallLog models — blocking call (fail-closed)")
            return False, "Rate limit check unavailable (import failure) — call blocked"

        settings = self.db.query(AgentTelephonySettings).filter(
            AgentTelephonySettings.user_id == agent_id
        ).first()

        if not settings:
            return True, None

        max_calls = settings.max_calls_per_day or 100
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Atomic rate-limit check: FOR UPDATE locks matching rows so concurrent
        # transactions serialize through this critical section.
        rate_query = self.db.query(func.count(CallLog.id)).filter(
            and_(
                CallLog.agent_id == agent_id,
                CallLog.created_at >= today_start
            )
        )
        if self.organization_id:
            rate_query = rate_query.filter(CallLog.organization_id == self.organization_id)
        rate_query = rate_query.with_for_update()
        calls_today = rate_query.scalar() or 0

        if calls_today >= max_calls:
            reason = f"Daily call limit reached ({calls_today}/{max_calls})"
            logger.warning(f"Rate limit exceeded for agent {agent_id}: {reason}")
            self._log_decision(
                decision_type="rate_limit",
                phone_number="",
                decision="blocked",
                reason=reason,
                user_id=agent_id,
                details={
                    "calls_today": calls_today,
                    "max_calls": max_calls,
                },
            )
            return False, reason

        self._log_decision(
            decision_type="rate_limit",
            phone_number="",
            decision="allowed",
            reason=f"Within daily limit ({calls_today}/{max_calls})",
            user_id=agent_id,
            details={
                "calls_today": calls_today,
                "max_calls": max_calls,
            },
        )
        return True, None

    # =========================================================================
    # Soft Locks (Multi-Agent Collision Prevention)
    # =========================================================================

    def check_soft_lock(self, phone_number: str, agent_id: int) -> Tuple[bool, Optional[Dict]]:
        """
        Check if a phone number has an active soft lock

        Args:
            phone_number: Phone number to check
            agent_id: Current agent ID

        Returns:
            Tuple of (is_locked, lock_info)
        """
        try:
            from database.models import ActiveCall, User
        except ImportError:
            logger.error("Could not import ActiveCall/User models — treating as locked (fail-closed)")
            return True, {"agent_name": "unknown", "reason": "Soft lock check unavailable (import failure)"}

        digits = self._normalize_phone(phone_number)

        lock_query = self.db.query(ActiveCall).filter(
            and_(
                ActiveCall.contact_phone == digits,
                ActiveCall.expires_at > datetime.now(timezone.utc),
                ActiveCall.agent_id != agent_id
            )
        )
        if self.organization_id:
            lock_query = lock_query.filter(ActiveCall.organization_id == self.organization_id)
        active_lock = lock_query.first()

        if active_lock:
            locking_agent = self.db.query(User).filter(User.id == active_lock.agent_id).first()

            lock_info = {
                'agent_id': active_lock.agent_id,
                'agent_name': locking_agent.name if locking_agent else "Unknown",
                'locked_at': active_lock.locked_at,
                'call_sid': active_lock.call_sid
            }
            self._log_decision(
                decision_type="soft_lock",
                phone_number=digits,
                decision="blocked",
                reason=f"Number locked by agent {lock_info['agent_name']}",
                user_id=agent_id,
                details={
                    "locking_agent_id": active_lock.agent_id,
                    "locking_agent_name": lock_info['agent_name'],
                    "call_sid": active_lock.call_sid,
                },
            )
            return True, lock_info

        return False, None

    def acquire_soft_lock(
        self,
        phone_number: str,
        agent_id: int,
        call_sid: str,
        lock_duration_seconds: int = 300
    ) -> bool:
        """
        Atomically acquire a soft lock for a phone number.

        Uses a two-step atomic approach:
        1. DELETE any expired locks for this phone+org (cleanup).
        2. INSERT ... ON CONFLICT DO NOTHING against the unique constraint
           (contact_phone, organization_id). If another agent holds a
           non-expired lock, the INSERT is a no-op and we return False.

        This prevents the race where two concurrent agents both see "no lock"
        and both acquire it (the old check-then-insert pattern).

        Args:
            phone_number: Phone number to lock
            agent_id: Agent acquiring the lock
            call_sid: Telnyx call SID
            lock_duration_seconds: Lock duration (default 5 minutes)

        Returns:
            True if lock acquired
        """
        try:
            from database.models import ActiveCall
        except ImportError:
            return False

        digits = self._normalize_phone(phone_number)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lock_duration_seconds)

        try:
            # Step 1: Clean up expired locks for this phone+org atomically.
            # This also removes our own prior lock (e.g., updating call_sid).
            delete_query = self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits
            )
            if self.organization_id:
                delete_query = delete_query.filter(ActiveCall.organization_id == self.organization_id)
            # Only delete expired locks OR locks held by the same agent
            # (agent re-acquiring with a new call_sid).
            delete_query = delete_query.filter(
                (ActiveCall.expires_at <= now) | (ActiveCall.agent_id == agent_id)
            )
            delete_query.delete(synchronize_session='fetch')

            # Step 2: Atomic INSERT ... ON CONFLICT DO NOTHING.
            # If another non-expired lock exists for a different agent,
            # the unique constraint (contact_phone, organization_id) fires
            # and the INSERT silently does nothing.
            org_id_val = self.organization_id if self.organization_id else None
            result = self.db.execute(
                text("""
                    INSERT INTO active_calls
                        (contact_phone, agent_id, call_sid, locked_at, expires_at, organization_id)
                    VALUES
                        (:phone, :agent_id, :call_sid, :locked_at, :expires_at, :org_id)
                    ON CONFLICT (contact_phone, organization_id) DO NOTHING
                """),
                {
                    "phone": digits,
                    "agent_id": agent_id,
                    "call_sid": call_sid,
                    "locked_at": now,
                    "expires_at": expires_at,
                    "org_id": org_id_val,
                },
            )
            self.db.commit()

            # rowcount == 1 means we inserted; 0 means conflict (another agent holds it)
            acquired = result.rowcount > 0

            if acquired:
                self._log_decision(
                    decision_type="soft_lock",
                    phone_number=digits,
                    decision="acquired",
                    reason=f"Lock acquired for {lock_duration_seconds}s",
                    user_id=agent_id,
                    details={
                        "call_sid": call_sid,
                        "lock_duration_seconds": lock_duration_seconds,
                    },
                )
                logger.info(f"Acquired soft lock for {digits} by agent {agent_id}")
            else:
                logger.info(f"Soft lock NOT acquired for {digits} by agent {agent_id} — held by another agent")

            return acquired

        except Exception as e:
            logger.error(f"Error acquiring soft lock: {e}")
            self.db.rollback()
            return False

    def release_soft_lock(self, phone_number: str, agent_id: int) -> bool:
        """Release a soft lock for a phone number"""
        try:
            from database.models import ActiveCall
        except ImportError:
            return False

        digits = self._normalize_phone(phone_number)

        try:
            release_query = self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits,
                ActiveCall.agent_id == agent_id
            )
            if self.organization_id:
                release_query = release_query.filter(ActiveCall.organization_id == self.organization_id)
            deleted = release_query.delete()
            self.db.commit()
            if deleted:
                logger.info(f"Released soft lock for {digits}")
            return True
        except Exception as e:
            logger.error(f"Error releasing soft lock: {e}")
            self.db.rollback()
            return False

    def release_lock_by_call_sid(self, call_sid: str):
        """Release lock by call SID (used in webhooks)"""
        try:
            from database.models import ActiveCall
        except ImportError:
            return

        try:
            release_q = self.db.query(ActiveCall).filter(ActiveCall.call_sid == call_sid)
            if self.organization_id:
                release_q = release_q.filter(ActiveCall.organization_id == self.organization_id)
            release_q.delete()
            self.db.commit()
            logger.info(f"Released contact lock for call {call_sid}")
        except Exception as e:
            logger.error(f"Error releasing lock by call_sid: {e}")
            self.db.rollback()

    def cleanup_expired_locks(self):
        """Remove expired locks (scoped to organization if set)"""
        try:
            from database.models import ActiveCall
        except ImportError:
            return

        try:
            cleanup_q = self.db.query(ActiveCall).filter(
                ActiveCall.expires_at <= datetime.now(timezone.utc)
            )
            if self.organization_id:
                cleanup_q = cleanup_q.filter(ActiveCall.organization_id == self.organization_id)
            deleted = cleanup_q.delete()
            if deleted > 0:
                self.db.commit()
                logger.info(f"Cleaned up {deleted} expired contact locks")
        except Exception as e:
            logger.error(f"Error cleaning up locks: {e}")
            self.db.rollback()

    # =========================================================================
    # Call Consent Check
    # =========================================================================

    def check_call_consent(
        self,
        phone_number: str,
        contact_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if the contact has granted call consent via ChannelPreference.

        TCPA / FCC one-to-one consent rule (Jan 2025) requires explicit prior
        consent before placing outbound calls.  We look up the contact's
        ChannelPreference record (by lead_id or by matching Lead phone number)
        and verify call_consent is True.

        Args:
            phone_number: The phone number being called (used for Lead lookup
                          when contact_id is not provided).
            contact_id:   Optional lead/contact ID for direct lookup.

        Returns:
            Tuple of (has_consent, denial_reason).
            has_consent=True means the call may proceed.
        """
        try:
            from database.models.communication import ChannelPreference
        except ImportError:
            try:
                from database.models import ChannelPreference
            except ImportError:
                logger.error(
                    "Could not import ChannelPreference model — "
                    "blocking call (fail-closed)"
                )
                return False, "Consent check unavailable (import failure) — call blocked"

        lead_id = contact_id

        # If no explicit contact_id, try to resolve via Lead phone number
        if not lead_id:
            try:
                from database.models.lead_loan import Lead
            except ImportError:
                try:
                    from database.models import Lead
                except ImportError:
                    logger.error(
                        "Could not import Lead model — "
                        "blocking call (fail-closed)"
                    )
                    return False, "Consent check unavailable (import failure) — call blocked"

            digits = self._normalize_phone(phone_number)
            if digits:
                lead_query = self.db.query(Lead).filter(
                    Lead.phone.ilike(f"%{digits[-10:]}")
                )
                if self.organization_id:
                    lead_query = lead_query.filter(Lead.organization_id == self.organization_id)
                lead = lead_query.first()
                if lead:
                    lead_id = lead.id

        digits = self._normalize_phone(phone_number)

        if not lead_id:
            # No matching contact found — cannot verify consent, block the call.
            no_contact_reason = (
                "No contact record found for this phone number. "
                "Cannot verify call consent — outbound call blocked."
            )
            self._log_decision(
                decision_type="consent_check",
                phone_number=digits,
                decision="blocked",
                reason=no_contact_reason,
                details={"failure": "no_contact_record"},
            )
            # Log to unified consent audit trail
            self._log_consent_audit(
                consent_type="call",
                action="verified",
                verification_result="not_found",
                phone=phone_number,
                reason=no_contact_reason,
                details={"failure": "no_contact_record"},
            )
            return False, no_contact_reason

        # Look up ChannelPreference for this lead.
        # TENANT SAFETY: lead_id is already org-validated -- either passed as
        # contact_id (caller responsibility) or resolved via Lead phone lookup
        # above which filters by self.organization_id.
        pref = self.db.query(ChannelPreference).filter(
            ChannelPreference.lead_id == lead_id
        ).first()

        if not pref:
            no_pref_reason = (
                "No channel preference record found for contact. "
                "Call consent has not been granted — outbound call blocked."
            )
            self._log_decision(
                decision_type="consent_check",
                phone_number=digits,
                decision="blocked",
                reason=no_pref_reason,
                lead_id=lead_id,
                details={"failure": "no_channel_preference"},
            )
            self._log_consent_audit(
                contact_id=lead_id,
                consent_type="call",
                action="verified",
                verification_result="not_found",
                phone=phone_number,
                reason=no_pref_reason,
                details={"failure": "no_channel_preference"},
            )
            return False, no_pref_reason

        if not pref.call_consent:
            no_consent_reason = (
                "Contact has not granted call consent. "
                "Outbound call blocked per TCPA/FCC one-to-one consent rules."
            )
            self._log_decision(
                decision_type="consent_check",
                phone_number=digits,
                decision="blocked",
                reason=no_consent_reason,
                lead_id=lead_id,
                details={"failure": "consent_not_granted"},
            )
            self._log_consent_audit(
                contact_id=lead_id,
                consent_type="call",
                action="verified",
                verification_result="failed",
                phone=phone_number,
                source_table="channel_preferences",
                source_record_id=str(pref.id),
                reason=no_consent_reason,
                details={"failure": "consent_not_granted", "call_consent": False},
            )
            return False, no_consent_reason

        self._log_decision(
            decision_type="consent_check",
            phone_number=digits,
            decision="allowed",
            reason="Call consent verified",
            lead_id=lead_id,
        )
        self._log_consent_audit(
            contact_id=lead_id,
            consent_type="call",
            action="verified",
            verification_result="passed",
            phone=phone_number,
            source_table="channel_preferences",
            source_record_id=str(pref.id),
            reason="Call consent verified via ChannelPreference",
            details={"call_consent": True, "consent_date": pref.call_consent_date.isoformat() if pref.call_consent_date else None},
        )
        return True, None

    # =========================================================================
    # Full Compliance Check
    # =========================================================================

    def full_compliance_check(
        self,
        phone_number: str,
        agent_id: int,
        contact_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run all compliance checks for a phone number

        Args:
            phone_number: Phone number to check
            agent_id: Agent attempting to call
            contact_id: Optional lead/contact ID for consent lookup

        Returns:
            Dict with compliance status and any issues
        """
        result = {
            "can_call": True,
            "issues": [],
            "warnings": [],
            "phone_number": phone_number
        }

        # Check call consent (TCPA/FCC one-to-one consent requirement)
        has_consent, consent_reason = self.check_call_consent(phone_number, contact_id)
        if not has_consent:
            result["can_call"] = False
            result["issues"].append(f"No call consent: {consent_reason}")

        # Check DNC status
        is_dnc, dnc_reason = self.check_dnc(phone_number)
        if is_dnc:
            result["can_call"] = False
            result["issues"].append(f"On Do Not Call list: {dnc_reason}")

        # Check calling hours
        within_hours, hours_msg = self.check_calling_hours(phone_number)
        if not within_hours:
            result["can_call"] = False
            result["issues"].append(hours_msg)
        else:
            result["timezone_info"] = hours_msg

        # Check rate limit
        within_limit, limit_msg = self.check_rate_limit(agent_id)
        if not within_limit:
            result["can_call"] = False
            result["issues"].append(limit_msg)

        # Check soft lock
        is_locked, lock_info = self.check_soft_lock(phone_number, agent_id)
        if is_locked:
            result["can_call"] = False
            result["issues"].append(
                f"Number currently being called by {lock_info.get('agent_name', 'another agent')}"
            )

        return result

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _normalize_phone(self, phone_number: str) -> str:
        """Normalize phone number to digits only"""
        if not phone_number:
            return ""
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        return digits
