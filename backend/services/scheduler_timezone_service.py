"""
Scheduler Timezone Service - Centralized timezone handling for all scheduler operations.

Provides a single source of truth for:
  - Converting local datetimes to UTC for storage
  - Converting UTC datetimes to local timezones for display
  - Resolving user and borrower timezones from DB/heuristics
  - Validating IANA timezone strings
  - Converting stored business hours to local time (DST-aware)
  - Checking time-slot overlaps across timezone boundaries

All stored datetimes should be UTC. This service handles conversion on
input (normalize_to_utc) and output (convert_from_utc).

Uses pytz for timezone handling, consistent with the rest of the codebase.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta, timezone as _tz
from typing import Any, Dict, List, Optional, Tuple

import pytz

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Default timezone when nothing else is available.
# America/New_York is the most conservative US choice for TCPA compliance
# (earliest US timezone means contact-hours checks err on the side of caution).
DEFAULT_TIMEZONE = "America/New_York"

# Fallback for user configs that store no timezone. The scheduler UI and
# SchedulerConfig model historically default to America/Chicago.
DEFAULT_USER_TIMEZONE = "America/Chicago"

# US state code -> primary IANA timezone. For states that span multiple zones,
# this picks the zone covering the largest population or land area.
# Used by get_borrower_timezone() as a best-effort heuristic.
STATE_TO_TIMEZONE: Dict[str, str] = {
    # Eastern Time
    "CT": "America/New_York",
    "DC": "America/New_York",
    "DE": "America/New_York",
    "FL": "America/New_York",       # most of FL is Eastern
    "GA": "America/New_York",
    "IN": "America/Indiana/Indianapolis",  # most of IN is Eastern
    "KY": "America/New_York",       # eastern KY; western is Central
    "MA": "America/New_York",
    "MD": "America/New_York",
    "ME": "America/New_York",
    "MI": "America/Detroit",        # most of MI is Eastern
    "NC": "America/New_York",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NY": "America/New_York",
    "OH": "America/New_York",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "TN": "America/New_York",       # eastern TN; western is Central
    "VA": "America/New_York",
    "VT": "America/New_York",
    "WV": "America/New_York",
    # Central Time
    "AL": "America/Chicago",
    "AR": "America/Chicago",
    "IA": "America/Chicago",
    "IL": "America/Chicago",
    "KS": "America/Chicago",        # most of KS is Central
    "LA": "America/Chicago",
    "MN": "America/Chicago",
    "MO": "America/Chicago",
    "MS": "America/Chicago",
    "NE": "America/Chicago",        # most of NE is Central
    "ND": "America/Chicago",        # most of ND is Central
    "OK": "America/Chicago",
    "SD": "America/Chicago",        # most of SD is Central
    "TX": "America/Chicago",        # most of TX is Central
    "WI": "America/Chicago",
    # Mountain Time
    "AZ": "America/Phoenix",        # no DST (except Navajo Nation)
    "CO": "America/Denver",
    "ID": "America/Boise",
    "MT": "America/Denver",
    "NM": "America/Denver",
    "UT": "America/Denver",
    "WY": "America/Denver",
    # Pacific Time
    "CA": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "OR": "America/Los_Angeles",    # most of OR is Pacific
    "WA": "America/Los_Angeles",
    # Alaska / Hawaii
    "AK": "America/Anchorage",
    "HI": "Pacific/Honolulu",       # no DST
    # Territories
    "AS": "Pacific/Pago_Pago",      # American Samoa
    "GU": "Pacific/Guam",
    "MP": "Pacific/Guam",           # Northern Mariana Islands
    "PR": "America/Puerto_Rico",
    "VI": "America/Virgin",
}

# Days of week as used by SchedulerConfig.working_hours JSON keys.
_WEEKDAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


# ============================================================================
# SERVICE CLASS
# ============================================================================

class TimezoneService:
    """Centralized timezone handling for the scheduler system.

    All methods are static so callers can use them without instantiation:
        TimezoneService.normalize_to_utc(dt, "America/Chicago")

    Design principles:
    - Storage: always UTC (naive or aware, depending on column config).
    - Display: convert from UTC to user/borrower local timezone on output.
    - DST: handled transparently via pytz localize/normalize.
    - Validation: reject unknown IANA zone strings early.
    """

    # ------------------------------------------------------------------
    # Core conversion
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_to_utc(dt: datetime, source_timezone: str) -> datetime:
        """Convert any datetime to UTC.

        Handles three input forms:
        1. Naive datetime -- assumed to be in *source_timezone*.
        2. Timezone-aware datetime whose tzinfo matches source_timezone -- converted.
        3. Timezone-aware datetime with a *different* tzinfo (e.g., already UTC) --
           converted using its existing tzinfo (source_timezone is ignored).

        The returned datetime is always timezone-aware (tzinfo=pytz.UTC).

        Args:
            dt: The datetime to convert.
            source_timezone: IANA timezone string (e.g., "America/New_York").
                Used only when *dt* is naive.

        Returns:
            A timezone-aware datetime in UTC.

        Raises:
            pytz.UnknownTimeZoneError: If source_timezone is not a valid IANA zone.
            TypeError: If dt is not a datetime instance.
        """
        if not isinstance(dt, datetime):
            raise TypeError(f"Expected datetime, got {type(dt).__name__}")

        if dt.tzinfo is not None and dt.utcoffset() is not None:
            # Already timezone-aware -- convert directly to UTC.
            return dt.astimezone(pytz.UTC)

        # Naive datetime -- interpret as source_timezone.
        tz = pytz.timezone(source_timezone)
        try:
            # localize() correctly handles DST for the given date.
            # is_dst=None raises AmbiguousTimeError during fall-back overlap;
            # we catch that below and resolve conservatively.
            local_dt = tz.localize(dt, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            # During fall-back, the same wall-clock time occurs twice.
            # Choose the *first* occurrence (DST=True, i.e., the earlier UTC instant)
            # to avoid accidentally scheduling something an hour later than intended.
            local_dt = tz.localize(dt, is_dst=True)
        except pytz.exceptions.NonExistentTimeError:
            # During spring-forward, this wall-clock time does not exist.
            # Shift forward to the valid time (e.g., 2:30 AM -> 3:30 AM).
            local_dt = tz.localize(dt, is_dst=False)
            # normalize() moves it to the correct wall-clock time.
            local_dt = tz.normalize(local_dt)

        return local_dt.astimezone(pytz.UTC)

    @staticmethod
    def convert_from_utc(dt_utc: datetime, target_timezone: str) -> datetime:
        """Convert a UTC datetime to a specific timezone for display.

        Handles both aware and naive UTC inputs:
        - If naive, it is *assumed* to be UTC (consistent with the DB storage pattern
          where datetimes are stored as naive UTC).
        - If aware, it is converted from whatever its current tzinfo is.

        The returned datetime is timezone-aware in the target timezone.

        Args:
            dt_utc: A datetime in UTC (naive or aware).
            target_timezone: IANA timezone string to convert to.

        Returns:
            A timezone-aware datetime in the target timezone.

        Raises:
            pytz.UnknownTimeZoneError: If target_timezone is not valid.
            TypeError: If dt_utc is not a datetime instance.
        """
        if not isinstance(dt_utc, datetime):
            raise TypeError(f"Expected datetime, got {type(dt_utc).__name__}")

        tz = pytz.timezone(target_timezone)

        if dt_utc.tzinfo is None or dt_utc.utcoffset() is None:
            # Naive -- assume UTC.
            utc_aware = pytz.UTC.localize(dt_utc)
        else:
            utc_aware = dt_utc.astimezone(pytz.UTC)

        return utc_aware.astimezone(tz)

    # ------------------------------------------------------------------
    # Timezone resolution
    # ------------------------------------------------------------------

    @staticmethod
    def get_user_timezone(user_id, db) -> str:
        """Get user's configured timezone from SchedulerConfig.

        Lookup order:
        1. SchedulerConfig.timezone for this user.
        2. Organization-level default (if org has a default_timezone setting).
        3. DEFAULT_USER_TIMEZONE ("America/Chicago").

        Args:
            user_id: The user's integer ID.
            db: An active SQLAlchemy Session.

        Returns:
            A valid IANA timezone string.
        """
        if not user_id or not db:
            return DEFAULT_USER_TIMEZONE

        try:
            # Try SchedulerConfig first (matches _helpers._get_user_timezone logic)
            from sqlalchemy import text
            row = db.execute(
                text(
                    "SELECT timezone FROM scheduler_configs "
                    "WHERE user_id = :uid LIMIT 1"
                ),
                {"uid": int(user_id)},
            ).fetchone()
            if row and row[0] and TimezoneService.validate_timezone(row[0]):
                return row[0]
        except Exception as e:
            logger.debug(f"Could not query SchedulerConfig timezone for user {user_id}: {e}")

        # Fallback: organization default timezone
        try:
            from sqlalchemy import text
            org_row = db.execute(
                text(
                    "SELECT o.default_timezone "
                    "FROM organizations o "
                    "JOIN users u ON u.organization_id = o.id "
                    "WHERE u.id = :uid LIMIT 1"
                ),
                {"uid": int(user_id)},
            ).fetchone()
            if org_row and org_row[0] and TimezoneService.validate_timezone(org_row[0]):
                return org_row[0]
        except Exception as e:
            logger.debug(f"Could not query org timezone for user {user_id}: {e}")

        return DEFAULT_USER_TIMEZONE

    @staticmethod
    def get_borrower_timezone(borrower_email: str, db) -> str:
        """Infer borrower timezone from their property address state.

        Lookup order:
        1. Loan.property_state for the borrower's most recent active loan.
        2. Lead.state for the borrower's lead record.
        3. DEFAULT_TIMEZONE ("America/New_York").

        This is a best-effort heuristic: the borrower's phone timezone or
        explicit preference would be more accurate, but those are not
        always available.

        Args:
            borrower_email: The borrower's email address.
            db: An active SQLAlchemy Session.

        Returns:
            A valid IANA timezone string.
        """
        if not borrower_email or not db:
            return DEFAULT_TIMEZONE

        state_code = None

        # 1. Check most recent active loan's property_state
        try:
            from sqlalchemy import text
            loan_row = db.execute(
                text(
                    "SELECT property_state FROM loans "
                    "WHERE borrower_email = :email "
                    "AND property_state IS NOT NULL "
                    "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY') "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"email": borrower_email},
            ).fetchone()
            if loan_row and loan_row[0]:
                state_code = loan_row[0].strip().upper()[:2]
        except Exception as e:
            logger.debug(f"Could not query loan property_state for {borrower_email}: {e}")

        # 2. Fallback to lead's state field
        if not state_code:
            try:
                from sqlalchemy import text
                lead_row = db.execute(
                    text(
                        "SELECT state FROM leads "
                        "WHERE email = :email "
                        "AND state IS NOT NULL "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"email": borrower_email},
                ).fetchone()
                if lead_row and lead_row[0]:
                    state_code = lead_row[0].strip().upper()[:2]
            except Exception as e:
                logger.debug(f"Could not query lead state for {borrower_email}: {e}")

        if state_code and state_code in STATE_TO_TIMEZONE:
            return STATE_TO_TIMEZONE[state_code]

        return DEFAULT_TIMEZONE

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_timezone(tz_string: str) -> bool:
        """Validate that a string is a valid IANA timezone identifier.

        Args:
            tz_string: The timezone string to validate (e.g., "America/Chicago").

        Returns:
            True if valid, False otherwise. Returns False for None/empty.
        """
        if not tz_string or not isinstance(tz_string, str):
            return False
        try:
            pytz.timezone(tz_string)
            return True
        except pytz.UnknownTimeZoneError:
            return False

    # ------------------------------------------------------------------
    # Business hours conversion
    # ------------------------------------------------------------------

    @staticmethod
    def get_business_hours_in_timezone(
        schedule: Dict[str, Any],
        timezone_str: str,
        target_date: date,
    ) -> List[Dict[str, datetime]]:
        """Convert stored business hours to timezone-aware datetimes for a specific date.

        The scheduler stores working hours as local-time strings in the user's
        configured timezone (e.g., {"monday": {"start": "09:00", "end": "17:00", "enabled": True}}).
        This method returns the corresponding UTC-aware start/end datetimes for
        *target_date*, correctly handling DST transitions.

        Args:
            schedule: The working_hours JSON dict from SchedulerConfig. Keys are
                lowercase day names; values have "start", "end" (HH:MM), "enabled".
            timezone_str: The IANA timezone the schedule is expressed in.
            target_date: The calendar date to generate hours for.

        Returns:
            A list of dicts with keys:
                - "start_local": timezone-aware datetime in the user's local tz
                - "end_local": timezone-aware datetime in the user's local tz
                - "start_utc": timezone-aware datetime in UTC
                - "end_utc": timezone-aware datetime in UTC
            Empty list if the day is disabled or has no schedule entry.
        """
        if not schedule or not timezone_str:
            return []

        day_name = _WEEKDAY_NAMES[target_date.weekday()]
        day_config = schedule.get(day_name)

        if not day_config or not day_config.get("enabled"):
            return []

        start_str = day_config.get("start", "")
        end_str = day_config.get("end", "")

        if not start_str or not end_str:
            return []

        # Handle "00:00"/"00:00" as "day off" (common pattern in the UI)
        if start_str == "00:00" and end_str == "00:00":
            return []

        try:
            start_time = _parse_time(start_str)
            end_time = _parse_time(end_str)
        except ValueError as e:
            logger.warning(f"Invalid business hours format for {day_name}: {e}")
            return []

        if start_time >= end_time:
            # Invalid or overnight range -- skip (scheduler does not support overnight hours)
            return []

        tz = pytz.timezone(timezone_str)

        # Combine date + local time, then localize.
        # Use localize() to handle DST correctly for this specific date.
        start_naive = datetime.combine(target_date, start_time)
        end_naive = datetime.combine(target_date, end_time)

        try:
            start_local = tz.localize(start_naive, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            start_local = tz.localize(start_naive, is_dst=True)
        except pytz.exceptions.NonExistentTimeError:
            start_local = tz.normalize(tz.localize(start_naive, is_dst=False))

        try:
            end_local = tz.localize(end_naive, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            end_local = tz.localize(end_naive, is_dst=True)
        except pytz.exceptions.NonExistentTimeError:
            end_local = tz.normalize(tz.localize(end_naive, is_dst=False))

        return [{
            "start_local": start_local,
            "end_local": end_local,
            "start_utc": start_local.astimezone(pytz.UTC),
            "end_utc": end_local.astimezone(pytz.UTC),
        }]

    # ------------------------------------------------------------------
    # Overlap detection
    # ------------------------------------------------------------------

    @staticmethod
    def slots_overlap(
        slot1_start: datetime,
        slot1_end: datetime,
        slot2_start: datetime,
        slot2_end: datetime,
    ) -> bool:
        """Check if two time slots overlap, handling timezone differences.

        All four arguments can be in any timezone (or naive). If naive, they are
        assumed to be in the same timezone as each other. If aware, they are
        compared by their UTC instant (i.e., timezone is normalized away).

        Two slots overlap when one starts before the other ends AND the other
        starts before the first ends (standard interval overlap test).

        Adjacent slots (slot1_end == slot2_start) are NOT considered overlapping --
        this matches the scheduler's convention that a meeting ending at 10:00
        does not conflict with one starting at 10:00.

        Args:
            slot1_start: Start of the first slot.
            slot1_end: End of the first slot.
            slot2_start: Start of the second slot.
            slot2_end: End of the second slot.

        Returns:
            True if the slots overlap, False otherwise.
        """
        # Normalize to UTC for consistent comparison if any are tz-aware.
        s1s = _to_utc_for_compare(slot1_start)
        s1e = _to_utc_for_compare(slot1_end)
        s2s = _to_utc_for_compare(slot2_start)
        s2e = _to_utc_for_compare(slot2_end)

        # Standard open-interval overlap: (s1 < e2) and (s2 < e1)
        return s1s < s2e and s2s < s1e

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @staticmethod
    def now_in_timezone(timezone_str: str) -> datetime:
        """Get the current time in a specific timezone.

        Args:
            timezone_str: IANA timezone string.

        Returns:
            Timezone-aware datetime in the given timezone.
        """
        tz = pytz.timezone(timezone_str)
        return datetime.now(pytz.UTC).astimezone(tz)

    @staticmethod
    def now_utc() -> datetime:
        """Get the current time in UTC (timezone-aware).

        Returns:
            Timezone-aware datetime in UTC.
        """
        return datetime.now(pytz.UTC)

    @staticmethod
    def is_within_contact_hours(
        timezone_str: str,
        start_hour: int = 8,
        end_hour: int = 21,
    ) -> Tuple[bool, str]:
        """Check if the current time in the given timezone is within contact hours.

        Mirrors the logic of scheduler_email_service._check_contact_hours()
        but with configurable windows and proper timezone handling.

        Default window is 8 AM - 9 PM (TCPA safe harbor).

        Args:
            timezone_str: IANA timezone of the recipient.
            start_hour: Earliest hour (inclusive) contact is allowed. Default 8.
            end_hour: Latest hour (exclusive) contact is allowed. Default 21 (9 PM).

        Returns:
            Tuple of (can_contact: bool, reason: str).
        """
        tz_name = timezone_str or DEFAULT_TIMEZONE
        if not TimezoneService.validate_timezone(tz_name):
            tz_name = DEFAULT_TIMEZONE

        tz = pytz.timezone(tz_name)
        local_now = datetime.now(pytz.UTC).astimezone(tz)
        local_hour = local_now.hour

        if local_hour < start_hour or local_hour >= end_hour:
            return (
                False,
                f"Outside contact hours ({start_hour}:00-{end_hour}:00). "
                f"Local time: {local_now.strftime('%I:%M %p %Z')}"
            )

        return True, "OK"

    @staticmethod
    def format_for_display(
        dt_utc: datetime,
        timezone_str: str,
        fmt: str = "%B %d, %Y",
        time_fmt: str = "%I:%M %p %Z",
    ) -> Dict[str, str]:
        """Format a UTC datetime for display in a specific timezone.

        Convenience wrapper that returns both date and time strings, suitable
        for email templates and API responses.

        Args:
            dt_utc: Datetime in UTC (naive or aware).
            timezone_str: IANA timezone to display in.
            fmt: strftime format for the date portion.
            time_fmt: strftime format for the time portion.

        Returns:
            Dict with keys "date", "time", "datetime_iso", "timezone".
        """
        local_dt = TimezoneService.convert_from_utc(dt_utc, timezone_str)
        return {
            "date": local_dt.strftime(fmt),
            "time": local_dt.strftime(time_fmt),
            "datetime_iso": local_dt.isoformat(),
            "timezone": timezone_str,
        }


# ============================================================================
# PRIVATE HELPERS
# ============================================================================

def _parse_time(time_str: str) -> time:
    """Parse an HH:MM time string into a datetime.time object.

    Args:
        time_str: A string like "09:00" or "17:30".

    Returns:
        A datetime.time object.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str!r} (expected HH:MM)")
    hour, minute = int(parts[0]), int(parts[1])
    return time(hour, minute)


def _to_utc_for_compare(dt: datetime) -> datetime:
    """Normalize a datetime to UTC for comparison purposes.

    - If timezone-aware, convert to UTC.
    - If naive, return as-is (assumed to be in a consistent timezone
      relative to the other datetime being compared).
    """
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return dt.astimezone(pytz.UTC)
    return dt
