"""
TCPA Compliance Service for Smart Docs Follow-Up

Gates every outbound SMS and call in the document follow-up automation system.
TCPA penalties are $500-$1,500 PER unconsented message. This service ensures
that no outbound touch occurs without verified consent.

Checks enforced by validate_outreach():
  1. Consent verification  - active SmartDocsConsentRecord for phone + channel
  2. DNC list              - InternalDNCEntry and ContactDNCStatus
  3. Quiet hours           - TCPA prohibits calls/texts before 8 AM and after
                             9 PM in the RECIPIENT's local timezone
  4. Frequency limiting    - configurable max contacts per day per channel

Usage in followup_automation_service.py:
    tcpa = TCPAComplianceService(db)
    validation = tcpa.validate_outreach(phone, org_id, "sms")
    if not validation.allowed:
        # Skip this step, log blockers
        ...
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

logger = logging.getLogger(__name__)

# Try pytz first, fall back to zoneinfo (same pattern as telephony/compliance.py)
try:
    import pytz

    HAS_PYTZ = True
except ImportError:
    from zoneinfo import ZoneInfo

    HAS_PYTZ = False


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TCPACheckResult:
    """Result of a single consent check (SMS or call)."""

    allowed: bool
    reason: str
    consent_date: Optional[datetime] = None
    consent_type: Optional[str] = None  # consent_source value


@dataclass
class OutreachValidation:
    """Comprehensive outreach validation result."""

    allowed: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    consent_info: Optional[dict] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# TCPA Safe Harbor calling/texting window
QUIET_HOURS_START = time(8, 0)  # 8:00 AM local
QUIET_HOURS_END = time(21, 0)  # 9:00 PM local

# Default timezone when recipient TZ is unknown (conservative: Eastern)
DEFAULT_TIMEZONE = "America/New_York"

# Area-code-to-timezone rough mapping (US only, covers major metro areas).
# This is a best-effort heuristic; production systems should use a proper
# phone-number-to-timezone service.
_AREA_CODE_TZ: dict = {
    # Eastern
    "201": "America/New_York",
    "202": "America/New_York",
    "203": "America/New_York",
    "212": "America/New_York",
    "215": "America/New_York",
    "301": "America/New_York",
    "302": "America/New_York",
    "305": "America/New_York",
    "312": "America/Chicago",
    "313": "America/New_York",
    "314": "America/Chicago",
    "404": "America/New_York",
    "407": "America/New_York",
    "410": "America/New_York",
    "412": "America/New_York",
    "414": "America/Chicago",
    "415": "America/Los_Angeles",
    "469": "America/Chicago",
    "503": "America/Los_Angeles",
    "504": "America/Chicago",
    "510": "America/Los_Angeles",
    "512": "America/Chicago",
    "513": "America/New_York",
    "516": "America/New_York",
    "602": "America/Phoenix",
    "603": "America/New_York",
    "609": "America/New_York",
    "612": "America/Chicago",
    "614": "America/New_York",
    "615": "America/Chicago",
    "617": "America/New_York",
    "619": "America/Los_Angeles",
    "626": "America/Los_Angeles",
    "650": "America/Los_Angeles",
    "702": "America/Los_Angeles",
    "703": "America/New_York",
    "704": "America/New_York",
    "708": "America/Chicago",
    "713": "America/Chicago",
    "714": "America/Los_Angeles",
    "718": "America/New_York",
    "720": "America/Denver",
    "727": "America/New_York",
    "732": "America/New_York",
    "770": "America/New_York",
    "786": "America/New_York",
    "801": "America/Denver",
    "802": "America/New_York",
    "803": "America/New_York",
    "804": "America/New_York",
    "808": "Pacific/Honolulu",
    "813": "America/New_York",
    "818": "America/Los_Angeles",
    "832": "America/Chicago",
    "843": "America/New_York",
    "847": "America/Chicago",
    "858": "America/Los_Angeles",
    "860": "America/New_York",
    "901": "America/Chicago",
    "904": "America/New_York",
    "907": "America/Anchorage",
    "908": "America/New_York",
    "909": "America/Los_Angeles",
    "910": "America/New_York",
    "913": "America/Chicago",
    "914": "America/New_York",
    "916": "America/Los_Angeles",
    "917": "America/New_York",
    "919": "America/New_York",
    "925": "America/Los_Angeles",
    "929": "America/New_York",
    "949": "America/Los_Angeles",
    "954": "America/New_York",
    "972": "America/Chicago",
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TCPAComplianceService:
    """
    TCPA compliance enforcement for the Smart Docs follow-up system.

    Every outbound SMS or call MUST pass validate_outreach() before sending.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_sms_consent(self, phone: str, org_id: int) -> TCPACheckResult:
        """Check whether the phone number has active SMS consent for this org.

        Args:
            phone: Recipient phone number (any format).
            org_id: Organization ID.

        Returns:
            TCPACheckResult with allowed=True if active consent exists.
        """
        return self._check_consent(phone, org_id, channel="sms")

    def check_call_consent(self, phone: str, org_id: int) -> TCPACheckResult:
        """Check whether the phone number has active call consent for this org.

        Args:
            phone: Recipient phone number (any format).
            org_id: Organization ID.

        Returns:
            TCPACheckResult with allowed=True if active consent exists.
        """
        return self._check_consent(phone, org_id, channel="call")

    def check_dnc_list(self, phone: str) -> bool:
        """Check internal DNC lists (Smart Docs + dialer ContactDNCStatus).

        Args:
            phone: Phone number to check.

        Returns:
            True if the number IS on a DNC list (i.e., blocked).
        """
        digits = self._normalize(phone)
        if not digits:
            return True  # Invalid phone => treat as blocked

        # 1. Check Smart Docs InternalDNCEntry
        from database.models.tcpa_smart_docs import InternalDNCEntry

        now = datetime.now(timezone.utc)
        dnc_hit = (
            self.db.query(InternalDNCEntry)
            .filter(
                InternalDNCEntry.phone == digits,
                # Entry is not expired
                (InternalDNCEntry.expires_at.is_(None))
                | (InternalDNCEntry.expires_at > now),
            )
            .first()
        )
        if dnc_hit:
            logger.info("Phone %s blocked by InternalDNCEntry id=%d", digits, dnc_hit.id)
            return True

        # 2. Check dialer ContactDNCStatus (global DNC)
        try:
            from database.models.dialer import ContactDNCStatus

            global_dnc = (
                self.db.query(ContactDNCStatus)
                .filter(ContactDNCStatus.phone_number == digits)
                .first()
            )
            if global_dnc:
                logger.info("Phone %s blocked by ContactDNCStatus id=%d", digits, global_dnc.id)
                return True
        except Exception as e:
            logger.warning("Failed to check ContactDNCStatus: %s", e)

        return False

    def record_consent(
        self,
        phone: str,
        org_id: int,
        borrower_id: int,
        channel: str,
        consent_source: str,
        ip_address: Optional[str] = None,
    ) -> dict:
        """Record a new consent grant with full audit trail.

        Args:
            phone: The phone number consented for.
            org_id: Organization ID.
            borrower_id: Lead/borrower ID.
            channel: "sms", "call", or "both".
            consent_source: How consent was obtained (web_form, verbal, etc.).
            ip_address: Optional IP address of the person granting consent.

        Returns:
            Dict with the new consent record details.
        """
        from database.models.tcpa_smart_docs import SmartDocsConsentRecord

        digits = self._normalize(phone)
        if not digits:
            return {"error": "Invalid phone number"}

        now = datetime.now(timezone.utc)

        record = SmartDocsConsentRecord(
            organization_id=org_id,
            borrower_id=borrower_id,
            phone=digits,
            channel=channel,
            consent_given=True,
            consent_source=consent_source,
            consent_ip_address=ip_address,
            consented_at=now,
        )
        self.db.add(record)
        self.db.flush()

        logger.info(
            "Recorded %s consent for phone %s (org=%d, borrower=%d, source=%s)",
            channel,
            digits,
            org_id,
            borrower_id,
            consent_source,
        )

        return {
            "consent_id": record.id,
            "phone": digits,
            "channel": channel,
            "consent_source": consent_source,
            "consented_at": now.isoformat(),
        }

    def revoke_consent(
        self,
        phone: str,
        org_id: int,
        channel: str,
        revocation_source: str,
    ) -> dict:
        """Revoke consent, effective immediately.

        Marks ALL active consent records for this phone + org + channel as
        revoked. TCPA requires revocation to be honoured immediately for
        automated systems.

        Args:
            phone: The phone number to revoke consent for.
            org_id: Organization ID.
            channel: "sms", "call", or "both".
            revocation_source: How revocation was received (text_reply, etc.).

        Returns:
            Dict with count of revoked records.
        """
        from database.models.tcpa_smart_docs import SmartDocsConsentRecord

        digits = self._normalize(phone)
        if not digits:
            return {"error": "Invalid phone number", "revoked_count": 0}

        now = datetime.now(timezone.utc)

        # Find all active consent records matching this phone + org + channel
        channels_to_revoke = [channel]
        if channel == "both":
            channels_to_revoke = ["sms", "call", "both"]
        else:
            # Also revoke "both" records since they cover this channel
            channels_to_revoke.append("both")

        active_records = (
            self.db.query(SmartDocsConsentRecord)
            .filter(
                SmartDocsConsentRecord.phone == digits,
                SmartDocsConsentRecord.organization_id == org_id,
                SmartDocsConsentRecord.channel.in_(channels_to_revoke),
                SmartDocsConsentRecord.consent_given == True,
                SmartDocsConsentRecord.revoked_at.is_(None),
            )
            .all()
        )

        for record in active_records:
            record.revoked_at = now
            record.revocation_source = revocation_source
            record.updated_at = now

        self.db.flush()

        revoked_count = len(active_records)
        logger.info(
            "Revoked %d consent record(s) for phone %s (org=%d, channel=%s, source=%s)",
            revoked_count,
            digits,
            org_id,
            channel,
            revocation_source,
        )

        return {
            "phone": digits,
            "channel": channel,
            "revoked_count": revoked_count,
            "revocation_source": revocation_source,
            "revoked_at": now.isoformat(),
        }

    def check_quiet_hours(
        self, phone: str, tz_name: Optional[str] = None
    ) -> bool:
        """Check whether current time falls within TCPA quiet hours for the
        recipient's timezone.

        TCPA prohibits automated calls/texts before 8 AM and after 9 PM in the
        RECIPIENT's local time. If timezone is unknown we default to Eastern
        (the most conservative US timezone for morning restrictions).

        Args:
            phone: Recipient phone number (used for area-code TZ inference).
            tz_name: Explicit IANA timezone name. If None, inferred from
                phone area code or defaults to America/New_York.

        Returns:
            True if it IS quiet hours (i.e., outreach is BLOCKED).
        """
        resolved_tz = self._resolve_timezone(phone, tz_name)
        now_local = self._now_in_tz(resolved_tz)
        local_time = now_local.time()

        is_quiet = local_time < QUIET_HOURS_START or local_time >= QUIET_HOURS_END

        if is_quiet:
            logger.info(
                "Quiet hours block for phone %s: local time %s in %s",
                self._normalize(phone),
                local_time.strftime("%H:%M"),
                resolved_tz,
            )

        return is_quiet

    def check_frequency_limit(
        self,
        phone: str,
        org_id: int,
        channel: str,
        max_per_day: int = 3,
    ) -> bool:
        """Check whether the daily outreach limit has been reached for this
        phone + channel combination.

        Args:
            phone: Recipient phone number.
            org_id: Organization ID.
            channel: "sms" or "call".
            max_per_day: Maximum allowed contacts per day per channel.

        Returns:
            True if the limit HAS BEEN REACHED (i.e., outreach is BLOCKED).
        """
        from database.models.tcpa_smart_docs import OutreachLog

        digits = self._normalize(phone)
        if not digits:
            return True  # Invalid phone => block

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        count = (
            self.db.query(func.count(OutreachLog.id))
            .filter(
                OutreachLog.phone == digits,
                OutreachLog.organization_id == org_id,
                OutreachLog.channel == channel,
                OutreachLog.sent_at >= today_start,
            )
            .scalar()
        ) or 0

        over_limit = count >= max_per_day

        if over_limit:
            logger.info(
                "Frequency limit reached for phone %s channel %s: %d/%d today",
                digits,
                channel,
                count,
                max_per_day,
            )

        return over_limit

    def get_consent_status(self, phone: str, org_id: int) -> dict:
        """Get the full consent status for a phone number within an org.

        Returns:
            Dict with sms_consent, call_consent, is_on_dnc, and details.
        """
        digits = self._normalize(phone)
        if not digits:
            return {
                "phone": phone,
                "error": "Invalid phone number",
                "sms_consent": False,
                "call_consent": False,
                "is_on_dnc": True,
            }

        sms_result = self.check_sms_consent(digits, org_id)
        call_result = self.check_call_consent(digits, org_id)
        is_on_dnc = self.check_dnc_list(digits)

        return {
            "phone": digits,
            "organization_id": org_id,
            "sms_consent": sms_result.allowed,
            "sms_consent_date": (
                sms_result.consent_date.isoformat() if sms_result.consent_date else None
            ),
            "sms_consent_source": sms_result.consent_type,
            "call_consent": call_result.allowed,
            "call_consent_date": (
                call_result.consent_date.isoformat() if call_result.consent_date else None
            ),
            "call_consent_source": call_result.consent_type,
            "is_on_dnc": is_on_dnc,
        }

    def validate_outreach(
        self,
        phone: str,
        org_id: int,
        channel: str,
        timezone_name: Optional[str] = None,
        max_per_day: int = 3,
    ) -> OutreachValidation:
        """Comprehensive pre-outreach validation.

        Runs ALL checks: consent, DNC, quiet hours, and frequency limit.
        Returns a single result indicating whether outreach is permitted.

        Args:
            phone: Recipient phone number.
            org_id: Organization ID.
            channel: "sms" or "call".
            timezone_name: Optional recipient timezone.
            max_per_day: Max daily contacts per channel.

        Returns:
            OutreachValidation with allowed=True only if ALL checks pass.
        """
        blockers: List[str] = []
        warnings: List[str] = []
        consent_info: Optional[dict] = None

        digits = self._normalize(phone)
        if not digits:
            return OutreachValidation(
                allowed=False,
                blockers=["Invalid phone number"],
            )

        # 1. Consent check
        consent_result = self._check_consent(digits, org_id, channel)
        if not consent_result.allowed:
            blockers.append(f"No {channel} consent: {consent_result.reason}")
        else:
            consent_info = {
                "consent_date": (
                    consent_result.consent_date.isoformat()
                    if consent_result.consent_date
                    else None
                ),
                "consent_source": consent_result.consent_type,
            }

        # 2. DNC check
        if self.check_dnc_list(digits):
            blockers.append("Phone number is on Do Not Contact list")

        # 3. Quiet hours check
        if self.check_quiet_hours(digits, timezone_name):
            resolved_tz = self._resolve_timezone(digits, timezone_name)
            now_local = self._now_in_tz(resolved_tz)
            blockers.append(
                f"TCPA quiet hours: recipient local time is "
                f"{now_local.strftime('%I:%M %p')} {resolved_tz} "
                f"(allowed 8:00 AM - 9:00 PM)"
            )

        # 4. Frequency limit check
        if self.check_frequency_limit(digits, org_id, channel, max_per_day):
            blockers.append(
                f"Daily {channel} limit reached ({max_per_day}/day)"
            )

        allowed = len(blockers) == 0

        if not allowed:
            logger.warning(
                "TCPA outreach BLOCKED for phone %s channel %s org %d: %s",
                digits,
                channel,
                org_id,
                "; ".join(blockers),
            )

        return OutreachValidation(
            allowed=allowed,
            blockers=blockers,
            warnings=warnings,
            consent_info=consent_info,
        )

    def log_outreach(
        self,
        phone: str,
        org_id: int,
        channel: str,
        campaign_id: Optional[int] = None,
    ) -> None:
        """Record an outreach event for frequency limiting.

        Call this AFTER a successful send so that subsequent checks
        count it toward the daily limit.

        Args:
            phone: The phone number contacted.
            org_id: Organization ID.
            channel: "sms" or "call".
            campaign_id: Optional follow-up campaign ID.
        """
        from database.models.tcpa_smart_docs import OutreachLog

        digits = self._normalize(phone)
        if not digits:
            return

        entry = OutreachLog(
            organization_id=org_id,
            phone=digits,
            channel=channel,
            campaign_id=campaign_id,
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(entry)
        # Do not flush here; let the caller's transaction handle it.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_consent(
        self, phone: str, org_id: int, channel: str
    ) -> TCPACheckResult:
        """Core consent lookup against SmartDocsConsentRecord.

        Looks for an active (not revoked) consent record whose channel
        matches or is "both".
        """
        from database.models.tcpa_smart_docs import SmartDocsConsentRecord

        digits = self._normalize(phone)
        if not digits:
            return TCPACheckResult(
                allowed=False, reason="Invalid phone number"
            )

        # Channels that satisfy this request
        matching_channels = [channel, "both"]

        record = (
            self.db.query(SmartDocsConsentRecord)
            .filter(
                SmartDocsConsentRecord.phone == digits,
                SmartDocsConsentRecord.organization_id == org_id,
                SmartDocsConsentRecord.channel.in_(matching_channels),
                SmartDocsConsentRecord.consent_given == True,
                SmartDocsConsentRecord.revoked_at.is_(None),
            )
            .order_by(SmartDocsConsentRecord.consented_at.desc())
            .first()
        )

        if record:
            return TCPACheckResult(
                allowed=True,
                reason="Active consent on file",
                consent_date=record.consented_at,
                consent_type=record.consent_source,
            )

        # Also check the existing TCPAConsent model (tcpa_consent.py)
        # as consent may have been recorded there by other subsystems.
        try:
            from database.models.tcpa_consent import TCPAConsent

            tcpa_record = (
                self.db.query(TCPAConsent)
                .filter(
                    TCPAConsent.phone_number == digits,
                    TCPAConsent.organization_id == str(org_id),
                    TCPAConsent.consent_channel.in_(matching_channels),
                    TCPAConsent.is_active == True,
                )
                .order_by(TCPAConsent.granted_at.desc())
                .first()
            )

            if tcpa_record:
                return TCPACheckResult(
                    allowed=True,
                    reason="Active consent on file (TCPAConsent)",
                    consent_date=tcpa_record.granted_at,
                    consent_type=tcpa_record.consent_source,
                )
        except Exception as e:
            # TCPAConsent table may not exist yet; that's OK
            logger.debug("TCPAConsent lookup skipped: %s", e)

        return TCPACheckResult(
            allowed=False,
            reason=f"No active {channel} consent found for this phone number",
        )

    def _normalize(self, phone: Optional[str]) -> str:
        """Normalize phone to digits-only E.164-ish format.

        Returns empty string if phone is None or has fewer than 10 digits.
        """
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        # Ensure US number has country code
        if len(digits) == 10:
            digits = "1" + digits
        if len(digits) < 10:
            return ""
        return digits

    def _resolve_timezone(
        self, phone: str, explicit_tz: Optional[str] = None
    ) -> str:
        """Resolve timezone: explicit > area code inference > default (ET)."""
        if explicit_tz:
            return explicit_tz

        digits = self._normalize(phone)
        if len(digits) >= 11 and digits[0] == "1":
            area_code = digits[1:4]
            tz = _AREA_CODE_TZ.get(area_code)
            if tz:
                return tz

        return DEFAULT_TIMEZONE

    def _now_in_tz(self, tz_name: str) -> datetime:
        """Get current datetime in the given timezone."""
        now_utc = datetime.now(timezone.utc)
        if HAS_PYTZ:
            local_tz = pytz.timezone(tz_name)
            return now_utc.astimezone(local_tz)
        else:
            local_tz = ZoneInfo(tz_name)
            return now_utc.astimezone(local_tz)
