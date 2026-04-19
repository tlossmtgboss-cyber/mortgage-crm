"""
SMS Quiet Hours -- TCPA Compliance

Centralized enforcement of TCPA quiet hours (8 AM - 9 PM recipient local time).
Consolidates three prior implementations into one canonical checker:

  1. integrations/sms_compliance_gate.py  -- ZoneInfo + area code fallback
  2. services/sms_compliance.py           -- pytz (DST edge cases)
  3. routes/bulk_sms_routes.py            -- state-code-to-timezone map

All three used different timezone libraries and lookup strategies, which
meant the same message could be blocked by one but allowed by another
during DST transitions. This module standardizes on ``zoneinfo.ZoneInfo``
(stdlib since Python 3.9, no DST ambiguity) and provides a single
``is_quiet_hours()`` entry-point that accepts phone, state, or explicit TZ.

Usage::

    from services.sms_quiet_hours import is_quiet_hours, resolve_timezone

    if is_quiet_hours(phone="+12125551234"):
        # Block send -- outside TCPA window

    tz = resolve_timezone(phone="+12125551234", state="NY")
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TCPA window constants
# ---------------------------------------------------------------------------
QUIET_START_HOUR = 21  # 9 PM local -- first impermissible hour
QUIET_END_HOUR = 8     # 8 AM local -- first permissible hour
DEFAULT_TIMEZONE = "America/New_York"  # Most conservative US TZ (earliest 9 PM)

# ---------------------------------------------------------------------------
# Area code -> IANA timezone (comprehensive US mapping)
#
# Merged from telephony/compliance.py _AREA_CODE_TZ (authoritative, ~250
# entries) plus entries from integrations/sms_compliance_gate.py.  Arizona
# area codes (480, 520, 602, 623, 928) use America/Phoenix (no DST).
# ---------------------------------------------------------------------------
AREA_CODE_TIMEZONE = {
    # Eastern (America/New_York)
    "201": "America/New_York",
    "202": "America/New_York",
    "203": "America/New_York",
    "207": "America/New_York",
    "212": "America/New_York",
    "215": "America/New_York",
    "216": "America/New_York",
    "229": "America/New_York",
    "231": "America/New_York",
    "234": "America/New_York",
    "239": "America/New_York",
    "240": "America/New_York",
    "248": "America/New_York",
    "252": "America/New_York",
    "260": "America/New_York",
    "267": "America/New_York",
    "269": "America/New_York",
    "270": "America/New_York",
    "272": "America/New_York",
    "276": "America/New_York",
    "278": "America/New_York",
    "301": "America/New_York",
    "302": "America/New_York",
    "304": "America/New_York",
    "305": "America/New_York",
    "313": "America/New_York",
    "315": "America/New_York",
    "317": "America/New_York",
    "321": "America/New_York",
    "330": "America/New_York",
    "336": "America/New_York",
    "339": "America/New_York",
    "340": "America/New_York",
    "347": "America/New_York",
    "351": "America/New_York",
    "352": "America/New_York",
    "364": "America/New_York",
    "380": "America/New_York",
    "386": "America/New_York",
    "401": "America/New_York",
    "404": "America/New_York",
    "407": "America/New_York",
    "410": "America/New_York",
    "412": "America/New_York",
    "413": "America/New_York",
    "419": "America/New_York",
    "423": "America/New_York",
    "434": "America/New_York",
    "440": "America/New_York",
    "443": "America/New_York",
    "463": "America/New_York",
    "470": "America/New_York",
    "475": "America/New_York",
    "478": "America/New_York",
    "484": "America/New_York",
    "502": "America/New_York",
    "508": "America/New_York",
    "513": "America/New_York",
    "516": "America/New_York",
    "517": "America/New_York",
    "518": "America/New_York",
    "540": "America/New_York",
    "551": "America/New_York",
    "561": "America/New_York",
    "567": "America/New_York",
    "570": "America/New_York",
    "571": "America/New_York",
    "574": "America/New_York",
    "585": "America/New_York",
    "586": "America/New_York",
    "603": "America/New_York",
    "606": "America/New_York",
    "607": "America/New_York",
    "609": "America/New_York",
    "610": "America/New_York",
    "614": "America/New_York",
    "616": "America/New_York",
    "617": "America/New_York",
    "631": "America/New_York",
    "646": "America/New_York",
    "667": "America/New_York",
    "678": "America/New_York",
    "681": "America/New_York",
    "689": "America/New_York",
    "703": "America/New_York",
    "704": "America/New_York",
    "706": "America/New_York",
    "716": "America/New_York",
    "717": "America/New_York",
    "718": "America/New_York",
    "724": "America/New_York",
    "727": "America/New_York",
    "732": "America/New_York",
    "734": "America/New_York",
    "740": "America/New_York",
    "743": "America/New_York",
    "754": "America/New_York",
    "757": "America/New_York",
    "762": "America/New_York",
    "765": "America/New_York",
    "770": "America/New_York",
    "772": "America/New_York",
    "774": "America/New_York",
    "781": "America/New_York",
    "786": "America/New_York",
    "802": "America/New_York",
    "803": "America/New_York",
    "804": "America/New_York",
    "810": "America/New_York",
    "812": "America/New_York",
    "813": "America/New_York",
    "814": "America/New_York",
    "828": "America/New_York",
    "843": "America/New_York",
    "845": "America/New_York",
    "848": "America/New_York",
    "850": "America/New_York",
    "854": "America/New_York",
    "856": "America/New_York",
    "857": "America/New_York",
    "859": "America/New_York",
    "860": "America/New_York",
    "862": "America/New_York",
    "863": "America/New_York",
    "864": "America/New_York",
    "878": "America/New_York",
    "904": "America/New_York",
    "908": "America/New_York",
    "910": "America/New_York",
    "912": "America/New_York",
    "914": "America/New_York",
    "917": "America/New_York",
    "919": "America/New_York",
    "929": "America/New_York",
    "937": "America/New_York",
    "941": "America/New_York",
    "947": "America/New_York",
    "954": "America/New_York",
    "959": "America/New_York",
    "973": "America/New_York",
    "978": "America/New_York",
    "980": "America/New_York",
    "984": "America/New_York",

    # Central (America/Chicago)
    "205": "America/Chicago",
    "210": "America/Chicago",
    "214": "America/Chicago",
    "217": "America/Chicago",
    "218": "America/Chicago",
    "219": "America/Chicago",
    "224": "America/Chicago",
    "225": "America/Chicago",
    "228": "America/Chicago",
    "251": "America/Chicago",
    "254": "America/Chicago",
    "256": "America/Chicago",
    "281": "America/Chicago",
    "308": "America/Chicago",
    "309": "America/Chicago",
    "312": "America/Chicago",
    "314": "America/Chicago",
    "316": "America/Chicago",
    "318": "America/Chicago",
    "319": "America/Chicago",
    "320": "America/Chicago",
    "325": "America/Chicago",
    "331": "America/Chicago",
    "334": "America/Chicago",
    "337": "America/Chicago",
    "346": "America/Chicago",
    "361": "America/Chicago",
    "402": "America/Chicago",
    "405": "America/Chicago",
    "409": "America/Chicago",
    "414": "America/Chicago",
    "417": "America/Chicago",
    "430": "America/Chicago",
    "432": "America/Chicago",
    "469": "America/Chicago",
    "479": "America/Chicago",
    "501": "America/Chicago",
    "504": "America/Chicago",
    "507": "America/Chicago",
    "512": "America/Chicago",
    "515": "America/Chicago",
    "531": "America/Chicago",
    "534": "America/Chicago",
    "539": "America/Chicago",
    "563": "America/Chicago",
    "573": "America/Chicago",
    "580": "America/Chicago",
    "601": "America/Chicago",
    "605": "America/Chicago",
    "608": "America/Chicago",
    "612": "America/Chicago",
    "615": "America/Chicago",
    "618": "America/Chicago",
    "620": "America/Chicago",
    "629": "America/Chicago",
    "630": "America/Chicago",
    "636": "America/Chicago",
    "641": "America/Chicago",
    "651": "America/Chicago",
    "660": "America/Chicago",
    "662": "America/Chicago",
    "682": "America/Chicago",
    "701": "America/Chicago",
    "708": "America/Chicago",
    "712": "America/Chicago",
    "713": "America/Chicago",
    "715": "America/Chicago",
    "731": "America/Chicago",
    "737": "America/Chicago",
    "763": "America/Chicago",
    "769": "America/Chicago",
    "773": "America/Chicago",
    "779": "America/Chicago",
    "806": "America/Chicago",
    "815": "America/Chicago",
    "816": "America/Chicago",
    "817": "America/Chicago",
    "830": "America/Chicago",
    "832": "America/Chicago",
    "847": "America/Chicago",
    "870": "America/Chicago",
    "901": "America/Chicago",
    "903": "America/Chicago",
    "913": "America/Chicago",
    "918": "America/Chicago",
    "920": "America/Chicago",
    "931": "America/Chicago",
    "936": "America/Chicago",
    "940": "America/Chicago",
    "952": "America/Chicago",
    "956": "America/Chicago",
    "972": "America/Chicago",
    "979": "America/Chicago",
    "985": "America/Chicago",

    # Mountain (America/Denver)
    "303": "America/Denver",
    "307": "America/Denver",
    "385": "America/Denver",
    "406": "America/Denver",
    "435": "America/Denver",
    "505": "America/Denver",
    "575": "America/Denver",
    "719": "America/Denver",
    "720": "America/Denver",
    "801": "America/Denver",
    "915": "America/Denver",
    "970": "America/Denver",

    # Arizona (America/Phoenix -- no DST)
    "480": "America/Phoenix",
    "520": "America/Phoenix",
    "602": "America/Phoenix",
    "623": "America/Phoenix",
    "928": "America/Phoenix",

    # Pacific (America/Los_Angeles)
    "206": "America/Los_Angeles",
    "209": "America/Los_Angeles",
    "213": "America/Los_Angeles",
    "253": "America/Los_Angeles",
    "310": "America/Los_Angeles",
    "323": "America/Los_Angeles",
    "360": "America/Los_Angeles",
    "408": "America/Los_Angeles",
    "415": "America/Los_Angeles",
    "424": "America/Los_Angeles",
    "425": "America/Los_Angeles",
    "442": "America/Los_Angeles",
    "458": "America/Los_Angeles",
    "503": "America/Los_Angeles",
    "509": "America/Los_Angeles",
    "510": "America/Los_Angeles",
    "530": "America/Los_Angeles",
    "541": "America/Los_Angeles",
    "559": "America/Los_Angeles",
    "562": "America/Los_Angeles",
    "619": "America/Los_Angeles",
    "626": "America/Los_Angeles",
    "628": "America/Los_Angeles",
    "650": "America/Los_Angeles",
    "657": "America/Los_Angeles",
    "661": "America/Los_Angeles",
    "669": "America/Los_Angeles",
    "702": "America/Los_Angeles",
    "707": "America/Los_Angeles",
    "714": "America/Los_Angeles",
    "725": "America/Los_Angeles",
    "747": "America/Los_Angeles",
    "760": "America/Los_Angeles",
    "775": "America/Los_Angeles",
    "805": "America/Los_Angeles",
    "818": "America/Los_Angeles",
    "831": "America/Los_Angeles",
    "858": "America/Los_Angeles",
    "909": "America/Los_Angeles",
    "916": "America/Los_Angeles",
    "925": "America/Los_Angeles",
    "949": "America/Los_Angeles",
    "951": "America/Los_Angeles",
    "971": "America/Los_Angeles",

    # Alaska
    "907": "America/Anchorage",

    # Hawaii
    "808": "Pacific/Honolulu",
}

# ---------------------------------------------------------------------------
# State abbreviation -> IANA timezone (for bulk campaigns by lead state)
#
# Copied from routes/bulk_sms_routes.py STATE_TIMEZONE_MAP. Uses the primary
# timezone for each state; border counties may differ but this is the
# conservative default for TCPA compliance.
# ---------------------------------------------------------------------------
STATE_TIMEZONE = {
    "AL": "America/Chicago",
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DE": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "MT": "America/Denver",
    "NE": "America/Chicago",
    "NV": "America/Los_Angeles",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WA": "America/Los_Angeles",
    "WV": "America/New_York",
    "WI": "America/Chicago",
    "WY": "America/Denver",
    "DC": "America/New_York",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_timezone(
    phone: Optional[str] = None,
    state: Optional[str] = None,
    explicit_tz: Optional[str] = None,
) -> str:
    """Resolve recipient timezone from the best available signal.

    Priority order (first match wins):
        1. ``explicit_tz`` -- caller already knows the timezone (e.g. from
           ChannelPreference or lead record).
        2. ``phone`` area code -- most precise fallback for individual sends.
        3. ``state`` abbreviation -- useful for bulk campaigns where only
           the lead's state is known.
        4. ``DEFAULT_TIMEZONE`` (America/New_York) -- most conservative US TZ
           (earliest 9 PM cutoff).

    Returns an IANA timezone string that is guaranteed to be valid for
    ``ZoneInfo()``.
    """
    # 1. Explicit timezone (validated)
    if explicit_tz:
        try:
            ZoneInfo(explicit_tz)
            return explicit_tz
        except (KeyError, ValueError):
            logger.warning("Invalid explicit timezone '%s', falling back", explicit_tz)

    # 2. Area code lookup from phone number
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        area_code: Optional[str] = None
        if digits.startswith("1") and len(digits) == 11:
            area_code = digits[1:4]
        elif len(digits) >= 10:
            area_code = digits[:3]
        if area_code and area_code in AREA_CODE_TIMEZONE:
            return AREA_CODE_TIMEZONE[area_code]

    # 3. State abbreviation
    if state:
        upper_state = state.strip().upper()
        if upper_state in STATE_TIMEZONE:
            return STATE_TIMEZONE[upper_state]

    # 4. Conservative default
    return DEFAULT_TIMEZONE


def is_quiet_hours(
    phone: Optional[str] = None,
    state: Optional[str] = None,
    explicit_tz: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Check whether the current time falls outside the TCPA permitted window
    (8 AM -- 9 PM) in the recipient's local timezone.

    Returns ``True`` if it IS quiet hours (sending is NOT allowed).

    Parameters
    ----------
    phone : str, optional
        Recipient phone number (any format). Used for area-code TZ lookup.
    state : str, optional
        US state abbreviation. Fallback if phone is unavailable.
    explicit_tz : str, optional
        IANA timezone string if the caller already resolved it (e.g. from
        the lead's ChannelPreference record).
    now : datetime, optional
        Override the current UTC time (for testing). Must be timezone-aware.
        Defaults to ``datetime.now(timezone.utc)``.
    """
    tz_name = resolve_timezone(phone=phone, state=state, explicit_tz=explicit_tz)

    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ValueError):
        logger.warning("ZoneInfo failed for '%s', using default %s", tz_name, DEFAULT_TIMEZONE)
        tz = ZoneInfo(DEFAULT_TIMEZONE)

    recipient_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    hour = recipient_now.hour

    # Quiet hours: 9 PM (21:00) through 7:59 AM
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR
