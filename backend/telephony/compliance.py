"""
Compliance checks for DNC, calling hours, and rate limits

Provides TCPA-compliant calling hour validation, Do Not Call list management,
rate limiting, and multi-agent collision prevention via soft locks.
"""

from datetime import datetime, time, timedelta
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
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


# Test mode bypass - set to True to skip calling hours check for testing
import os
BYPASS_CALLING_HOURS = os.getenv("BYPASS_CALLING_HOURS", "false").lower() == "true"
if BYPASS_CALLING_HOURS:
    _env = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "")).lower()
    if _env in ("production", "prod"):
        logger.critical("BYPASS_CALLING_HOURS=true in PRODUCTION — TCPA violation risk! Ignoring flag.")
        BYPASS_CALLING_HOURS = False
    else:
        logger.warning("BYPASS_CALLING_HOURS is enabled — calling hours checks will be skipped")


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

    def __init__(self, db: Session):
        self.db = db
        if HAS_PYTZ:
            self.default_timezone = pytz.timezone('America/New_York')
        else:
            self.default_timezone = ZoneInfo('America/New_York')

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
            # Fallback for different import paths
            logger.warning("Could not import ContactDNCStatus model")
            return False, None

        # Normalize phone number
        digits = self._normalize_phone(phone_number)

        # Check internal DNC list
        dnc_entry = self.db.query(ContactDNCStatus).filter(
            ContactDNCStatus.phone_number == digits
        ).first()

        if dnc_entry:
            return True, dnc_entry.reason

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
            contact = self.db.query(Lead).filter(Lead.id == contact_id).first()

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
            existing = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            ).first()

            if existing:
                existing.reason = reason
                existing.added_by_id = added_by_id
            else:
                dnc_entry = ContactDNCStatus(
                    phone_number=digits,
                    reason=reason,
                    added_by_id=added_by_id
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
            deleted = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            ).delete()
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
        Check if current time is within legal calling hours

        TCPA Safe Harbor: 8 AM - 9 PM local time

        Args:
            phone_number: Phone number to determine timezone

        Returns:
            Tuple of (is_allowed, reason_message)
        """
        # Check for test bypass
        if BYPASS_CALLING_HOURS:
            logger.warning("BYPASS_CALLING_HOURS is enabled - skipping calling hours check")
            return True, "Calling hours check bypassed for testing"

        contact_tz = self._get_timezone_for_phone(phone_number)
        now_utc = datetime.utcnow()

        if HAS_PYTZ:
            now_local = pytz.utc.localize(now_utc).astimezone(contact_tz)
        else:
            from datetime import timezone
            now_local = now_utc.replace(tzinfo=timezone.utc).astimezone(contact_tz)

        current_time = now_local.time()

        if current_time < self.CALLING_HOURS_START or current_time >= self.CALLING_HOURS_END:
            reason = (
                f"Outside calling hours - local time is {now_local.strftime('%I:%M %p')}. "
                f"Legal hours: 8 AM - 9 PM"
            )
            return False, reason

        return True, f"Within calling hours ({now_local.strftime('%I:%M %p')} local)"

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
        """Map area code to timezone string"""
        # Simplified mapping of major area codes
        area_code_map = {
            # Eastern
            '212': 'America/New_York', '646': 'America/New_York', '917': 'America/New_York',
            '718': 'America/New_York', '347': 'America/New_York', '516': 'America/New_York',
            '202': 'America/New_York', '301': 'America/New_York', '410': 'America/New_York',
            '215': 'America/New_York', '267': 'America/New_York', '610': 'America/New_York',
            '404': 'America/New_York', '678': 'America/New_York', '770': 'America/New_York',
            '305': 'America/New_York', '786': 'America/New_York', '954': 'America/New_York',
            '617': 'America/New_York', '857': 'America/New_York',
            # Central
            '312': 'America/Chicago', '773': 'America/Chicago', '872': 'America/Chicago',
            '214': 'America/Chicago', '469': 'America/Chicago', '972': 'America/Chicago',
            '713': 'America/Chicago', '832': 'America/Chicago', '281': 'America/Chicago',
            '512': 'America/Chicago', '737': 'America/Chicago',
            '314': 'America/Chicago', '636': 'America/Chicago',
            # Mountain
            '303': 'America/Denver', '720': 'America/Denver',
            '602': 'America/Phoenix', '480': 'America/Phoenix', '623': 'America/Phoenix',
            '801': 'America/Denver', '385': 'America/Denver',
            # Pacific
            '310': 'America/Los_Angeles', '323': 'America/Los_Angeles', '213': 'America/Los_Angeles',
            '818': 'America/Los_Angeles', '626': 'America/Los_Angeles', '424': 'America/Los_Angeles',
            '415': 'America/Los_Angeles', '628': 'America/Los_Angeles',
            '510': 'America/Los_Angeles', '650': 'America/Los_Angeles',
            '206': 'America/Los_Angeles', '425': 'America/Los_Angeles',
            '503': 'America/Los_Angeles', '971': 'America/Los_Angeles',
        }
        return area_code_map.get(area_code)

    # =========================================================================
    # Rate Limiting
    # =========================================================================

    def check_rate_limit(self, agent_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if agent has exceeded daily call limit

        Args:
            agent_id: Agent/User ID

        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        try:
            from database.models import AgentTelephonySettings, CallLog
        except ImportError:
            return True, None

        settings = self.db.query(AgentTelephonySettings).filter(
            AgentTelephonySettings.user_id == agent_id
        ).first()

        if not settings:
            return True, None

        max_calls = settings.max_calls_per_day or 100
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        calls_today = self.db.query(func.count(CallLog.id)).filter(
            and_(
                CallLog.agent_id == agent_id,
                CallLog.created_at >= today_start
            )
        ).scalar() or 0

        if calls_today >= max_calls:
            reason = f"Daily call limit reached ({calls_today}/{max_calls})"
            logger.warning(f"Rate limit exceeded for agent {agent_id}: {reason}")
            return False, reason

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
            return False, None

        digits = self._normalize_phone(phone_number)

        active_lock = self.db.query(ActiveCall).filter(
            and_(
                ActiveCall.contact_phone == digits,
                ActiveCall.expires_at > datetime.utcnow(),
                ActiveCall.agent_id != agent_id
            )
        ).first()

        if active_lock:
            locking_agent = self.db.query(User).filter(User.id == active_lock.agent_id).first()

            return True, {
                'agent_id': active_lock.agent_id,
                'agent_name': locking_agent.name if locking_agent else "Unknown",
                'locked_at': active_lock.locked_at,
                'call_sid': active_lock.call_sid
            }

        return False, None

    def acquire_soft_lock(
        self,
        phone_number: str,
        agent_id: int,
        call_sid: str,
        lock_duration_seconds: int = 300
    ) -> bool:
        """
        Acquire a soft lock for a phone number

        Args:
            phone_number: Phone number to lock
            agent_id: Agent acquiring the lock
            call_sid: Twilio call SID
            lock_duration_seconds: Lock duration (default 5 minutes)

        Returns:
            True if lock acquired
        """
        try:
            from database.models import ActiveCall
        except ImportError:
            return False

        digits = self._normalize_phone(phone_number)

        try:
            # Check if already locked by someone else
            is_locked, _ = self.check_soft_lock(digits, agent_id)
            if is_locked:
                return False

            # Remove any existing lock for this number
            self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits
            ).delete()

            # Create new lock
            now = datetime.utcnow()
            lock = ActiveCall(
                contact_phone=digits,
                agent_id=agent_id,
                call_sid=call_sid,
                locked_at=now,
                expires_at=now + timedelta(seconds=lock_duration_seconds)
            )
            self.db.add(lock)
            self.db.commit()

            logger.info(f"Acquired soft lock for {digits} by agent {agent_id}")
            return True

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
            deleted = self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits,
                ActiveCall.agent_id == agent_id
            ).delete()
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
            self.db.query(ActiveCall).filter(ActiveCall.call_sid == call_sid).delete()
            self.db.commit()
            logger.info(f"Released contact lock for call {call_sid}")
        except Exception as e:
            logger.error(f"Error releasing lock by call_sid: {e}")
            self.db.rollback()

    def cleanup_expired_locks(self):
        """Remove all expired locks"""
        try:
            from database.models import ActiveCall
        except ImportError:
            return

        try:
            deleted = self.db.query(ActiveCall).filter(
                ActiveCall.expires_at <= datetime.utcnow()
            ).delete()
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
                logger.warning(
                    "Could not import ChannelPreference model — "
                    "skipping call consent check"
                )
                return True, None

        lead_id = contact_id

        # If no explicit contact_id, try to resolve via Lead phone number
        if not lead_id:
            try:
                from database.models.lead_loan import Lead
            except ImportError:
                try:
                    from database.models import Lead
                except ImportError:
                    logger.warning(
                        "Could not import Lead model — "
                        "skipping call consent check"
                    )
                    return True, None

            digits = self._normalize_phone(phone_number)
            if digits:
                lead = self.db.query(Lead).filter(
                    Lead.phone.ilike(f"%{digits[-10:]}")
                ).first()
                if lead:
                    lead_id = lead.id

        if not lead_id:
            # No matching contact found — cannot verify consent, block the call.
            return False, (
                "No contact record found for this phone number. "
                "Cannot verify call consent — outbound call blocked."
            )

        # Look up ChannelPreference for this lead
        pref = self.db.query(ChannelPreference).filter(
            ChannelPreference.lead_id == lead_id
        ).first()

        if not pref:
            return False, (
                "No channel preference record found for contact. "
                "Call consent has not been granted — outbound call blocked."
            )

        if not pref.call_consent:
            return False, (
                "Contact has not granted call consent. "
                "Outbound call blocked per TCPA/FCC one-to-one consent rules."
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
