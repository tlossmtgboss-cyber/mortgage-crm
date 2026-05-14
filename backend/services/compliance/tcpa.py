"""
TCPA Time-of-Day Restriction Checker

Deterministic, rule-based TCPA (Telephone Consumer Protection Act)
calling-window enforcement.  No LLM calls.

Regulation: 47 CFR 64.1200(c)(1) — Telephone solicitation calls
may only be made between 8:00 AM and 9:00 PM in the called party's
local time zone.

Usage:
    from services.compliance.tcpa import TCPAChecker

    checker = TCPAChecker()
    result = checker.can_contact_now("America/New_York")
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import zoneinfo
    _ZoneInfo = zoneinfo.ZoneInfo
except ImportError:
    # Python < 3.9 fallback
    try:
        from backports.zoneinfo import ZoneInfo as _ZoneInfo
    except ImportError:
        _ZoneInfo = None
        logger.warning(
            "zoneinfo not available — TCPA timezone checks will "
            "fall back to UTC offset estimation"
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# TCPA calling window (in the callee's local timezone)
TCPA_START_HOUR = 8   # 8:00 AM
TCPA_END_HOUR = 21    # 9:00 PM (21:00)

# Common US timezone mappings by area code prefix
# This is a fallback when only a phone number is available.
_AREA_CODE_TIMEZONE: dict[str, str] = {
    # Eastern
    "201": "America/New_York", "202": "America/New_York",
    "203": "America/New_York", "205": "America/Chicago",
    "206": "America/Los_Angeles", "207": "America/New_York",
    "208": "America/Boise", "209": "America/Los_Angeles",
    "210": "America/Chicago", "212": "America/New_York",
    "213": "America/Los_Angeles", "214": "America/Chicago",
    "215": "America/New_York", "216": "America/New_York",
    "217": "America/Chicago", "218": "America/Chicago",
    "219": "America/Chicago", "224": "America/Chicago",
    "225": "America/Chicago", "228": "America/Chicago",
    "229": "America/New_York", "231": "America/New_York",
    "234": "America/New_York", "239": "America/New_York",
    "240": "America/New_York", "248": "America/New_York",
    "251": "America/Chicago", "252": "America/New_York",
    "253": "America/Los_Angeles", "254": "America/Chicago",
    "256": "America/Chicago", "260": "America/New_York",
    "262": "America/Chicago", "267": "America/New_York",
    "269": "America/New_York", "270": "America/New_York",
    "276": "America/New_York", "281": "America/Chicago",
    "301": "America/New_York", "302": "America/New_York",
    "303": "America/Denver", "304": "America/New_York",
    "305": "America/New_York", "307": "America/Denver",
    "308": "America/Chicago", "309": "America/Chicago",
    "310": "America/Los_Angeles", "312": "America/Chicago",
    "313": "America/New_York", "314": "America/Chicago",
    "315": "America/New_York", "316": "America/Chicago",
    "317": "America/New_York", "318": "America/Chicago",
    "319": "America/Chicago", "320": "America/Chicago",
    "321": "America/New_York", "323": "America/Los_Angeles",
    "325": "America/Chicago", "330": "America/New_York",
    "331": "America/Chicago", "334": "America/Chicago",
    "336": "America/New_York", "337": "America/Chicago",
    "339": "America/New_York", "340": "America/Virgin",
    "341": "America/Los_Angeles",
    "346": "America/Chicago", "347": "America/New_York",
    "351": "America/New_York", "352": "America/New_York",
    "360": "America/Los_Angeles", "361": "America/Chicago",
    "385": "America/Denver", "386": "America/New_York",
    "401": "America/New_York", "402": "America/Chicago",
    "404": "America/New_York", "405": "America/Chicago",
    "406": "America/Denver", "407": "America/New_York",
    "408": "America/Los_Angeles", "409": "America/Chicago",
    "410": "America/New_York", "412": "America/New_York",
    "413": "America/New_York", "414": "America/Chicago",
    "415": "America/Los_Angeles", "417": "America/Chicago",
    "419": "America/New_York", "423": "America/New_York",
    "424": "America/Los_Angeles", "425": "America/Los_Angeles",
    "430": "America/Chicago", "432": "America/Chicago",
    "434": "America/New_York", "435": "America/Denver",
    "440": "America/New_York", "442": "America/Los_Angeles",
    "443": "America/New_York", "458": "America/Los_Angeles",
    "469": "America/Chicago", "470": "America/New_York",
    "475": "America/New_York", "478": "America/New_York",
    "479": "America/Chicago", "480": "America/Phoenix",
    "484": "America/New_York",
    "501": "America/Chicago", "502": "America/New_York",
    "503": "America/Los_Angeles", "504": "America/Chicago",
    "505": "America/Denver", "507": "America/Chicago",
    "508": "America/New_York", "509": "America/Los_Angeles",
    "510": "America/Los_Angeles", "512": "America/Chicago",
    "513": "America/New_York", "515": "America/Chicago",
    "516": "America/New_York", "517": "America/New_York",
    "518": "America/New_York", "520": "America/Phoenix",
    "530": "America/Los_Angeles", "531": "America/Chicago",
    "534": "America/Chicago", "539": "America/Chicago",
    "540": "America/New_York", "541": "America/Los_Angeles",
    "551": "America/New_York", "559": "America/Los_Angeles",
    "561": "America/New_York", "562": "America/Los_Angeles",
    "563": "America/Chicago", "567": "America/New_York",
    "570": "America/New_York", "571": "America/New_York",
    "573": "America/Chicago", "574": "America/New_York",
    "575": "America/Denver", "580": "America/Chicago",
    "585": "America/New_York", "586": "America/New_York",
    "601": "America/Chicago", "602": "America/Phoenix",
    "603": "America/New_York", "605": "America/Chicago",
    "606": "America/New_York", "607": "America/New_York",
    "608": "America/Chicago", "609": "America/New_York",
    "610": "America/New_York", "612": "America/Chicago",
    "614": "America/New_York", "615": "America/Chicago",
    "616": "America/New_York", "617": "America/New_York",
    "618": "America/Chicago", "619": "America/Los_Angeles",
    "620": "America/Chicago", "623": "America/Phoenix",
    "626": "America/Los_Angeles", "628": "America/Los_Angeles",
    "629": "America/Chicago", "630": "America/Chicago",
    "631": "America/New_York", "636": "America/Chicago",
    "641": "America/Chicago", "646": "America/New_York",
    "650": "America/Los_Angeles", "651": "America/Chicago",
    "657": "America/Los_Angeles", "660": "America/Chicago",
    "661": "America/Los_Angeles", "662": "America/Chicago",
    "667": "America/New_York",
    "678": "America/New_York", "681": "America/New_York",
    "682": "America/Chicago",
    "701": "America/Chicago", "702": "America/Los_Angeles",
    "703": "America/New_York", "704": "America/New_York",
    "706": "America/New_York", "707": "America/Los_Angeles",
    "708": "America/Chicago", "712": "America/Chicago",
    "713": "America/Chicago", "714": "America/Los_Angeles",
    "715": "America/Chicago", "716": "America/New_York",
    "717": "America/New_York", "718": "America/New_York",
    "719": "America/Denver", "720": "America/Denver",
    "724": "America/New_York", "725": "America/Los_Angeles",
    "727": "America/New_York", "731": "America/Chicago",
    "732": "America/New_York", "734": "America/New_York",
    "737": "America/Chicago", "740": "America/New_York",
    "743": "America/New_York",
    "747": "America/Los_Angeles",
    "754": "America/New_York", "757": "America/New_York",
    "760": "America/Los_Angeles", "762": "America/New_York",
    "763": "America/Chicago", "765": "America/New_York",
    "769": "America/Chicago", "770": "America/New_York",
    "772": "America/New_York", "773": "America/Chicago",
    "774": "America/New_York", "775": "America/Los_Angeles",
    "779": "America/Chicago", "781": "America/New_York",
    "785": "America/Chicago", "786": "America/New_York",
    "787": "America/Puerto_Rico",
    "801": "America/Denver", "802": "America/New_York",
    "803": "America/New_York", "804": "America/New_York",
    "805": "America/Los_Angeles", "806": "America/Chicago",
    "808": "Pacific/Honolulu", "810": "America/New_York",
    "812": "America/New_York", "813": "America/New_York",
    "814": "America/New_York", "815": "America/Chicago",
    "816": "America/Chicago", "817": "America/Chicago",
    "818": "America/Los_Angeles", "828": "America/New_York",
    "830": "America/Chicago", "831": "America/Los_Angeles",
    "832": "America/Chicago", "833": "America/New_York",
    "843": "America/New_York", "845": "America/New_York",
    "847": "America/Chicago", "848": "America/New_York",
    "850": "America/New_York",
    "856": "America/New_York", "857": "America/New_York",
    "858": "America/Los_Angeles", "859": "America/New_York",
    "860": "America/New_York", "862": "America/New_York",
    "863": "America/New_York", "864": "America/New_York",
    "865": "America/New_York",
    "870": "America/Chicago", "872": "America/Chicago",
    "878": "America/New_York",
    "901": "America/Chicago", "903": "America/Chicago",
    "904": "America/New_York", "906": "America/New_York",
    "907": "America/Anchorage", "908": "America/New_York",
    "909": "America/Los_Angeles", "910": "America/New_York",
    "912": "America/New_York", "913": "America/Chicago",
    "914": "America/New_York", "915": "America/Denver",
    "916": "America/Los_Angeles", "917": "America/New_York",
    "918": "America/Chicago", "919": "America/New_York",
    "920": "America/Chicago", "925": "America/Los_Angeles",
    "928": "America/Phoenix", "929": "America/New_York",
    "931": "America/Chicago", "936": "America/Chicago",
    "937": "America/New_York", "938": "America/Chicago",
    "940": "America/Chicago", "941": "America/New_York",
    "947": "America/New_York", "949": "America/Los_Angeles",
    "951": "America/Los_Angeles", "952": "America/Chicago",
    "954": "America/New_York", "956": "America/Chicago",
    "959": "America/New_York", "970": "America/Denver",
    "971": "America/Los_Angeles", "972": "America/Chicago",
    "973": "America/New_York", "978": "America/New_York",
    "979": "America/Chicago", "980": "America/New_York",
    "984": "America/New_York", "985": "America/Chicago",
    "989": "America/New_York",
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AuditMetadata(BaseModel):
    """Audit trail for every compliance calculation."""
    rule: str
    regulation: str
    inputs: dict
    calculated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ContactWindowResult(BaseModel):
    """Result of a TCPA contact window check."""
    can_contact: bool
    timezone_id: str
    local_time: str
    local_date: str
    window_start: str = f"{TCPA_START_HOUR:02d}:00"
    window_end: str = f"{TCPA_END_HOUR:02d}:00"
    minutes_until_window_opens: Optional[int] = None
    minutes_until_window_closes: Optional[int] = None
    next_window_open: Optional[str] = None
    message: str
    audit: AuditMetadata


class NextContactWindow(BaseModel):
    """The next available TCPA-compliant contact window."""
    timezone_id: str
    window_opens_utc: str
    window_opens_local: str
    window_closes_utc: str
    window_closes_local: str
    is_open_now: bool
    message: str


# ---------------------------------------------------------------------------
# TCPA Checker
# ---------------------------------------------------------------------------

class TCPAChecker:
    """Deterministic TCPA calling-window checker.

    All methods are stateless and produce audit-trailed results.
    No database access.
    """

    def _resolve_timezone(
        self,
        tz_id: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a timezone identifier from explicit tz_id or phone area code.

        Args:
            tz_id: Explicit IANA timezone (e.g., "America/New_York").
            phone: Phone number to extract area code from.

        Returns:
            IANA timezone string, or None if unresolvable.
        """
        if tz_id:
            return tz_id

        if phone:
            # Strip non-digits
            digits = "".join(c for c in phone if c.isdigit())
            # Handle +1 country code
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if len(digits) >= 3:
                area_code = digits[:3]
                return _AREA_CODE_TIMEZONE.get(area_code)

        return None

    def _get_local_now(self, tz_id: str) -> Optional[datetime]:
        """Get the current datetime in the specified timezone."""
        if _ZoneInfo is None:
            return None
        try:
            tz = _ZoneInfo(tz_id)
            return datetime.now(tz)
        except Exception as e:
            logger.warning(f"Failed to resolve timezone {tz_id}: {e}")
            return None

    def can_contact_now(
        self,
        tz_id: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> ContactWindowResult:
        """Check if an outbound contact is allowed right now.

        TCPA Rule: Telephone solicitation calls may only be made
        between 8:00 AM and 9:00 PM in the called party's local time.
        Regulation: 47 CFR 64.1200(c)(1)

        Args:
            tz_id: IANA timezone of the callee (e.g., "America/New_York").
            phone: Phone number (used to infer timezone from area code
                   if tz_id is not provided).

        Returns:
            ContactWindowResult with contact permission and timing details.
        """
        resolved_tz = self._resolve_timezone(tz_id, phone)

        if not resolved_tz:
            return ContactWindowResult(
                can_contact=False,
                timezone_id="unknown",
                local_time="unknown",
                local_date="unknown",
                message=(
                    "Cannot determine callee timezone. Contact blocked "
                    "as a precaution. Provide timezone or valid US phone number."
                ),
                audit=AuditMetadata(
                    rule="TCPA time-of-day restriction",
                    regulation="47 CFR 64.1200(c)(1)",
                    inputs={"tz_id": tz_id, "phone": phone},
                ),
            )

        local_now = self._get_local_now(resolved_tz)
        if local_now is None:
            return ContactWindowResult(
                can_contact=False,
                timezone_id=resolved_tz,
                local_time="unknown",
                local_date="unknown",
                message=(
                    f"Cannot determine local time for timezone {resolved_tz}. "
                    f"Contact blocked as a precaution."
                ),
                audit=AuditMetadata(
                    rule="TCPA time-of-day restriction",
                    regulation="47 CFR 64.1200(c)(1)",
                    inputs={"tz_id": tz_id, "phone": phone, "resolved_tz": resolved_tz},
                ),
            )

        local_hour = local_now.hour
        local_minute = local_now.minute
        in_window = TCPA_START_HOUR <= local_hour < TCPA_END_HOUR

        minutes_until_open = None
        minutes_until_close = None
        next_window_open = None

        if in_window:
            # Calculate minutes until window closes
            close_time = local_now.replace(
                hour=TCPA_END_HOUR, minute=0, second=0, microsecond=0
            )
            minutes_until_close = int((close_time - local_now).total_seconds() / 60)
            message = (
                f"Contact allowed. Local time: {local_now.strftime('%I:%M %p %Z')}. "
                f"Window closes in {minutes_until_close} minutes."
            )
        else:
            if local_hour < TCPA_START_HOUR:
                # Before window opens today
                open_time = local_now.replace(
                    hour=TCPA_START_HOUR, minute=0, second=0, microsecond=0
                )
            else:
                # After window closed — next window is tomorrow at 8 AM
                tomorrow = local_now + timedelta(days=1)
                open_time = tomorrow.replace(
                    hour=TCPA_START_HOUR, minute=0, second=0, microsecond=0
                )

            minutes_until_open = int((open_time - local_now).total_seconds() / 60)
            next_window_open = open_time.isoformat()
            message = (
                f"Contact NOT allowed. Local time: {local_now.strftime('%I:%M %p %Z')}. "
                f"Outside TCPA window (8:00 AM - 9:00 PM). "
                f"Next window opens in {minutes_until_open} minutes."
            )

        return ContactWindowResult(
            can_contact=in_window,
            timezone_id=resolved_tz,
            local_time=local_now.strftime("%H:%M:%S"),
            local_date=local_now.strftime("%Y-%m-%d"),
            minutes_until_window_opens=minutes_until_open,
            minutes_until_window_closes=minutes_until_close,
            next_window_open=next_window_open,
            message=message,
            audit=AuditMetadata(
                rule="TCPA time-of-day restriction",
                regulation="47 CFR 64.1200(c)(1)",
                inputs={
                    "tz_id": tz_id,
                    "phone": phone,
                    "resolved_tz": resolved_tz,
                    "local_hour": local_hour,
                    "local_minute": local_minute,
                },
            ),
        )

    def next_contact_window(
        self,
        tz_id: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> NextContactWindow:
        """Calculate the next available TCPA-compliant contact window.

        Args:
            tz_id: IANA timezone of the callee.
            phone: Phone number (fallback for timezone inference).

        Returns:
            NextContactWindow with UTC and local window times.
        """
        resolved_tz = self._resolve_timezone(tz_id, phone)

        if not resolved_tz:
            return NextContactWindow(
                timezone_id="unknown",
                window_opens_utc="unknown",
                window_opens_local="unknown",
                window_closes_utc="unknown",
                window_closes_local="unknown",
                is_open_now=False,
                message="Cannot determine timezone. Provide tz_id or valid US phone.",
            )

        local_now = self._get_local_now(resolved_tz)
        if local_now is None:
            return NextContactWindow(
                timezone_id=resolved_tz,
                window_opens_utc="unknown",
                window_opens_local="unknown",
                window_closes_utc="unknown",
                window_closes_local="unknown",
                is_open_now=False,
                message=f"Cannot resolve timezone {resolved_tz}.",
            )

        in_window = TCPA_START_HOUR <= local_now.hour < TCPA_END_HOUR

        if in_window:
            # Currently in window
            window_open = local_now.replace(
                hour=TCPA_START_HOUR, minute=0, second=0, microsecond=0
            )
            window_close = local_now.replace(
                hour=TCPA_END_HOUR, minute=0, second=0, microsecond=0
            )
            message = f"Window is currently open until {window_close.strftime('%I:%M %p %Z')}."
        elif local_now.hour < TCPA_START_HOUR:
            # Before today's window
            window_open = local_now.replace(
                hour=TCPA_START_HOUR, minute=0, second=0, microsecond=0
            )
            window_close = local_now.replace(
                hour=TCPA_END_HOUR, minute=0, second=0, microsecond=0
            )
            message = f"Window opens today at {window_open.strftime('%I:%M %p %Z')}."
        else:
            # After today's window — next window is tomorrow
            tomorrow = local_now + timedelta(days=1)
            window_open = tomorrow.replace(
                hour=TCPA_START_HOUR, minute=0, second=0, microsecond=0
            )
            window_close = tomorrow.replace(
                hour=TCPA_END_HOUR, minute=0, second=0, microsecond=0
            )
            message = f"Window opens tomorrow at {window_open.strftime('%I:%M %p %Z')}."

        return NextContactWindow(
            timezone_id=resolved_tz,
            window_opens_utc=window_open.astimezone(timezone.utc).isoformat(),
            window_opens_local=window_open.isoformat(),
            window_closes_utc=window_close.astimezone(timezone.utc).isoformat(),
            window_closes_local=window_close.isoformat(),
            is_open_now=in_window,
            message=message,
        )

    def check_contact_at_time(
        self,
        contact_time: datetime,
        tz_id: str,
    ) -> bool:
        """Check if a specific datetime falls within the TCPA window.

        Useful for scheduling future contacts.

        Args:
            contact_time: The proposed contact time (timezone-aware or naive UTC).
            tz_id: IANA timezone of the callee.

        Returns:
            True if the time is within the 8 AM - 9 PM window in the callee's timezone.
        """
        if _ZoneInfo is None:
            return False

        try:
            tz = _ZoneInfo(tz_id)
            if contact_time.tzinfo is None:
                # Assume UTC
                contact_time = contact_time.replace(tzinfo=timezone.utc)
            local_time = contact_time.astimezone(tz)
            return TCPA_START_HOUR <= local_time.hour < TCPA_END_HOUR
        except Exception as e:
            logger.warning(f"TCPA time check failed for tz {tz_id}: {e}")
            return False
