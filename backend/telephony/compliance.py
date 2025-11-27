"""
Compliance Module for Dialer System
Handles DNC checks, calling hours validation, and rate limiting
"""

import logging
from datetime import datetime, time
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# US state timezone mapping (simplified - uses most common timezone per state)
STATE_TIMEZONES = {
    # Eastern Time
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "IN": "America/New_York", "KY": "America/New_York",
    "ME": "America/New_York", "MD": "America/New_York", "MA": "America/New_York",
    "MI": "America/New_York", "NH": "America/New_York", "NJ": "America/New_York",
    "NY": "America/New_York", "NC": "America/New_York", "OH": "America/New_York",
    "PA": "America/New_York", "RI": "America/New_York", "SC": "America/New_York",
    "VT": "America/New_York", "VA": "America/New_York", "WV": "America/New_York",
    "DC": "America/New_York",
    # Central Time
    "AL": "America/Chicago", "AR": "America/Chicago", "IL": "America/Chicago",
    "IA": "America/Chicago", "KS": "America/Chicago", "LA": "America/Chicago",
    "MN": "America/Chicago", "MS": "America/Chicago", "MO": "America/Chicago",
    "NE": "America/Chicago", "ND": "America/Chicago", "OK": "America/Chicago",
    "SD": "America/Chicago", "TN": "America/Chicago", "TX": "America/Chicago",
    "WI": "America/Chicago",
    # Mountain Time
    "AZ": "America/Phoenix", "CO": "America/Denver", "ID": "America/Denver",
    "MT": "America/Denver", "NM": "America/Denver", "UT": "America/Denver",
    "WY": "America/Denver",
    # Pacific Time
    "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
    "OR": "America/Los_Angeles", "WA": "America/Los_Angeles",
    # Alaska/Hawaii
    "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
}

# Area code to state mapping (simplified - major area codes)
AREA_CODE_TO_STATE = {
    # California
    "209": "CA", "213": "CA", "310": "CA", "323": "CA", "408": "CA", "415": "CA",
    "510": "CA", "530": "CA", "559": "CA", "562": "CA", "619": "CA", "626": "CA",
    "650": "CA", "661": "CA", "707": "CA", "714": "CA", "760": "CA", "805": "CA",
    "818": "CA", "831": "CA", "858": "CA", "909": "CA", "916": "CA", "925": "CA",
    "949": "CA", "951": "CA",
    # Texas
    "210": "TX", "214": "TX", "254": "TX", "281": "TX", "325": "TX", "361": "TX",
    "409": "TX", "432": "TX", "469": "TX", "512": "TX", "682": "TX", "713": "TX",
    "737": "TX", "806": "TX", "817": "TX", "830": "TX", "832": "TX", "903": "TX",
    "915": "TX", "936": "TX", "940": "TX", "956": "TX", "972": "TX", "979": "TX",
    # New York
    "212": "NY", "315": "NY", "347": "NY", "516": "NY", "518": "NY", "585": "NY",
    "607": "NY", "631": "NY", "646": "NY", "716": "NY", "718": "NY", "845": "NY",
    "914": "NY", "917": "NY", "929": "NY",
    # Florida
    "239": "FL", "305": "FL", "321": "FL", "352": "FL", "386": "FL", "407": "FL",
    "561": "FL", "727": "FL", "754": "FL", "772": "FL", "786": "FL", "813": "FL",
    "850": "FL", "863": "FL", "904": "FL", "941": "FL", "954": "FL",
    # Illinois
    "217": "IL", "224": "IL", "309": "IL", "312": "IL", "331": "IL", "618": "IL",
    "630": "IL", "708": "IL", "773": "IL", "815": "IL", "847": "IL",
    # Pennsylvania
    "215": "PA", "267": "PA", "272": "PA", "412": "PA", "484": "PA", "570": "PA",
    "610": "PA", "717": "PA", "724": "PA", "814": "PA",
    # Ohio
    "216": "OH", "234": "OH", "330": "OH", "419": "OH", "440": "OH", "513": "OH",
    "567": "OH", "614": "OH", "740": "OH", "937": "OH",
    # Georgia
    "229": "GA", "404": "GA", "470": "GA", "478": "GA", "678": "GA", "706": "GA",
    "762": "GA", "770": "GA", "912": "GA",
    # North Carolina
    "252": "NC", "336": "NC", "704": "NC", "743": "NC", "828": "NC", "910": "NC",
    "919": "NC", "980": "NC",
    # Michigan
    "231": "MI", "248": "MI", "269": "MI", "313": "MI", "517": "MI", "586": "MI",
    "616": "MI", "734": "MI", "810": "MI", "906": "MI", "947": "MI", "989": "MI",
    # New Jersey
    "201": "NJ", "551": "NJ", "609": "NJ", "732": "NJ", "848": "NJ", "856": "NJ",
    "862": "NJ", "908": "NJ", "973": "NJ",
    # Virginia
    "276": "VA", "434": "VA", "540": "VA", "571": "VA", "703": "VA", "757": "VA",
    "804": "VA",
    # Washington
    "206": "WA", "253": "WA", "360": "WA", "425": "WA", "509": "WA",
    # Arizona
    "480": "AZ", "520": "AZ", "602": "AZ", "623": "AZ", "928": "AZ",
    # Massachusetts
    "339": "MA", "351": "MA", "413": "MA", "508": "MA", "617": "MA", "774": "MA",
    "781": "MA", "857": "MA", "978": "MA",
    # Tennessee
    "423": "TN", "615": "TN", "629": "TN", "731": "TN", "865": "TN", "901": "TN",
    # Missouri
    "314": "MO", "417": "MO", "573": "MO", "636": "MO", "660": "MO", "816": "MO",
    # Maryland
    "240": "MD", "301": "MD", "410": "MD", "443": "MD", "667": "MD",
    # Colorado
    "303": "CO", "719": "CO", "720": "CO", "970": "CO",
    # Alabama
    "205": "AL", "251": "AL", "256": "AL", "334": "AL",
    # South Carolina
    "803": "SC", "843": "SC", "864": "SC",
    # Louisiana
    "225": "LA", "318": "LA", "337": "LA", "504": "LA", "985": "LA",
    # Kentucky
    "270": "KY", "502": "KY", "606": "KY", "859": "KY",
    # Oregon
    "458": "OR", "503": "OR", "541": "OR", "971": "OR",
    # Oklahoma
    "405": "OK", "539": "OK", "580": "OK", "918": "OK",
    # Connecticut
    "203": "CT", "475": "CT", "860": "CT",
    # Iowa
    "319": "IA", "515": "IA", "563": "IA", "641": "IA", "712": "IA",
    # Mississippi
    "228": "MS", "601": "MS", "662": "MS", "769": "MS",
    # Arkansas
    "479": "AR", "501": "AR", "870": "AR",
    # Kansas
    "316": "KS", "620": "KS", "785": "KS", "913": "KS",
    # Utah
    "385": "UT", "435": "UT", "801": "UT",
    # Nevada
    "702": "NV", "725": "NV", "775": "NV",
    # New Mexico
    "505": "NM", "575": "NM",
    # West Virginia
    "304": "WV", "681": "WV",
    # Nebraska
    "308": "NE", "402": "NE", "531": "NE",
    # Idaho
    "208": "ID",
    # Hawaii
    "808": "HI",
    # Maine
    "207": "ME",
    # New Hampshire
    "603": "NH",
    # Rhode Island
    "401": "RI",
    # Montana
    "406": "MT",
    # Delaware
    "302": "DE",
    # South Dakota
    "605": "SD",
    # North Dakota
    "701": "ND",
    # Alaska
    "907": "AK",
    # Vermont
    "802": "VT",
    # Wyoming
    "307": "WY",
    # Washington DC
    "202": "DC",
}


class ComplianceChecker:
    """
    Handles compliance checks for outbound calling
    - Do Not Call (DNC) list checking
    - Calling hours validation by timezone
    - Rate limiting
    """

    # TCPA Safe Harbor calling hours (8 AM - 9 PM local time)
    CALLING_START_HOUR = 8  # 8 AM
    CALLING_END_HOUR = 21   # 9 PM

    def __init__(self, db_session):
        """
        Initialize compliance checker with database session

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def extract_area_code(self, phone_number: str) -> Optional[str]:
        """
        Extract area code from a phone number

        Args:
            phone_number: Phone number in any format

        Returns:
            3-digit area code or None
        """
        # Remove non-digits
        digits = ''.join(c for c in phone_number if c.isdigit())

        # Handle +1 country code
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        if len(digits) >= 10:
            return digits[:3]

        return None

    def get_timezone_for_phone(self, phone_number: str) -> str:
        """
        Determine timezone for a phone number based on area code

        Args:
            phone_number: Phone number to lookup

        Returns:
            Timezone string (defaults to America/New_York if not found)
        """
        area_code = self.extract_area_code(phone_number)

        if area_code and area_code in AREA_CODE_TO_STATE:
            state = AREA_CODE_TO_STATE[area_code]
            return STATE_TIMEZONES.get(state, "America/New_York")

        # Default to Eastern Time if we can't determine
        return "America/New_York"

    def is_within_calling_hours(
        self,
        phone_number: str,
        check_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if current time is within legal calling hours for phone number's timezone

        TCPA Safe Harbor: 8 AM - 9 PM local time

        Args:
            phone_number: The phone number to check
            check_time: Time to check (defaults to now)

        Returns:
            Tuple of (is_allowed, reason_message)
        """
        if check_time is None:
            check_time = datetime.now()

        # Get timezone for phone number
        tz_name = self.get_timezone_for_phone(phone_number)

        try:
            tz = ZoneInfo(tz_name)
            local_time = check_time.astimezone(tz)
            local_hour = local_time.hour

            if self.CALLING_START_HOUR <= local_hour < self.CALLING_END_HOUR:
                return True, f"Within calling hours ({local_time.strftime('%I:%M %p')} {tz_name})"
            else:
                return False, f"Outside calling hours - local time is {local_time.strftime('%I:%M %p')} {tz_name}. Legal hours: 8 AM - 9 PM"

        except Exception as e:
            logger.error(f"Error checking calling hours: {e}")
            # Default to allowing the call if we can't determine
            return True, "Could not determine timezone - proceeding with caution"

    def check_dnc_status(self, phone_number: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a phone number is on the Do Not Call list

        Args:
            phone_number: The phone number to check

        Returns:
            Tuple of (is_on_dnc, reason) - True if on DNC list
        """
        from backend.main import ContactDNCStatus

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        # Check internal DNC list
        dnc_entry = self.db.query(ContactDNCStatus).filter(
            ContactDNCStatus.phone_number == digits
        ).first()

        if dnc_entry:
            return True, dnc_entry.reason

        return False, None

    def add_to_dnc(
        self,
        phone_number: str,
        reason: str,
        added_by_id: int
    ) -> bool:
        """
        Add a phone number to the Do Not Call list

        Args:
            phone_number: Phone number to add
            reason: Reason for adding to DNC
            added_by_id: User ID who added it

        Returns:
            True if added successfully
        """
        from backend.main import ContactDNCStatus

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        try:
            # Check if already exists
            existing = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            ).first()

            if existing:
                # Update reason
                existing.reason = reason
                existing.added_by_id = added_by_id
            else:
                # Create new entry
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
        """
        Remove a phone number from the Do Not Call list

        Args:
            phone_number: Phone number to remove

        Returns:
            True if removed successfully
        """
        from backend.main import ContactDNCStatus

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        try:
            deleted = self.db.query(ContactDNCStatus).filter(
                ContactDNCStatus.phone_number == digits
            ).delete()

            self.db.commit()

            if deleted:
                logger.info(f"Removed {digits} from DNC list")
                return True
            return False

        except Exception as e:
            logger.error(f"Error removing from DNC: {e}")
            self.db.rollback()
            return False

    def check_soft_lock(self, phone_number: str) -> Tuple[bool, Optional[int]]:
        """
        Check if a phone number has an active soft lock (another agent calling)

        Args:
            phone_number: Phone number to check

        Returns:
            Tuple of (is_locked, locking_agent_id)
        """
        from backend.main import ActiveCall

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        # Check for active lock that hasn't expired
        active_call = self.db.query(ActiveCall).filter(
            ActiveCall.contact_phone == digits,
            ActiveCall.expires_at > datetime.utcnow()
        ).first()

        if active_call:
            return True, active_call.agent_id

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
            lock_duration_seconds: How long the lock lasts (default 5 minutes)

        Returns:
            True if lock acquired
        """
        from backend.main import ActiveCall
        from datetime import timedelta

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        try:
            # Check if already locked by someone else
            is_locked, locking_agent = self.check_soft_lock(digits)
            if is_locked and locking_agent != agent_id:
                return False

            # Remove any existing lock for this number
            self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits
            ).delete()

            # Create new lock
            now = datetime.utcnow()
            active_call = ActiveCall(
                contact_phone=digits,
                agent_id=agent_id,
                call_sid=call_sid,
                locked_at=now,
                expires_at=now + timedelta(seconds=lock_duration_seconds)
            )
            self.db.add(active_call)
            self.db.commit()

            logger.info(f"Acquired soft lock for {digits} by agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Error acquiring soft lock: {e}")
            self.db.rollback()
            return False

    def release_soft_lock(self, phone_number: str, agent_id: int) -> bool:
        """
        Release a soft lock for a phone number

        Args:
            phone_number: Phone number to unlock
            agent_id: Agent releasing the lock

        Returns:
            True if lock released
        """
        from backend.main import ActiveCall

        # Normalize phone number
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        try:
            deleted = self.db.query(ActiveCall).filter(
                ActiveCall.contact_phone == digits,
                ActiveCall.agent_id == agent_id
            ).delete()

            self.db.commit()

            if deleted:
                logger.info(f"Released soft lock for {digits} by agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Error releasing soft lock: {e}")
            self.db.rollback()
            return False

    def full_compliance_check(
        self,
        phone_number: str,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Run all compliance checks for a phone number

        Args:
            phone_number: Phone number to check
            agent_id: Agent attempting to call

        Returns:
            Dict with compliance status and any issues
        """
        result = {
            "can_call": True,
            "issues": [],
            "warnings": [],
            "phone_number": phone_number
        }

        # Check DNC status
        is_dnc, dnc_reason = self.check_dnc_status(phone_number)
        if is_dnc:
            result["can_call"] = False
            result["issues"].append(f"On Do Not Call list: {dnc_reason}")

        # Check calling hours
        within_hours, hours_msg = self.is_within_calling_hours(phone_number)
        if not within_hours:
            result["can_call"] = False
            result["issues"].append(hours_msg)
        else:
            result["timezone_info"] = hours_msg

        # Check soft lock
        is_locked, locking_agent = self.check_soft_lock(phone_number)
        if is_locked and locking_agent != agent_id:
            result["can_call"] = False
            result["issues"].append(f"Number currently being called by another agent (ID: {locking_agent})")

        return result
