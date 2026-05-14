"""
Business Day Calendar for Compliance Calculations

Deterministic business day arithmetic for TRID, ECOA, and other
regulatory deadline computations.  No LLM calls — pure rule-based.

Federal holidays follow OPM (Office of Personnel Management) rules:
  - If a holiday falls on Saturday, the preceding Friday is observed.
  - If a holiday falls on Sunday, the following Monday is observed.

Supports custom org-level holiday calendars via an optional parameter.

Usage:
    from services.compliance.business_days import (
        add_business_days,
        subtract_business_days,
        count_business_days,
        is_business_day,
        get_federal_holidays,
    )

    deadline = add_business_days(date(2026, 5, 14), 3)
"""

import logging
from datetime import date, timedelta
from typing import FrozenSet, List, Optional, Set

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Federal Holiday Definitions (static, 2025-2028)
# ---------------------------------------------------------------------------

def _observed(d: date) -> date:
    """Apply OPM observed-holiday rules.

    If the actual holiday falls on Saturday, the preceding Friday is
    the observed holiday.  If it falls on Sunday, the following Monday
    is observed.
    """
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a given month.

    weekday: 0=Monday, 6=Sunday
    n: 1-based (1st, 2nd, 3rd, 4th)
    """
    first = date(year, month, 1)
    # Days until the target weekday
    delta = (weekday - first.weekday()) % 7
    first_occurrence = first + timedelta(days=delta)
    return first_occurrence + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a given month."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = next_month_first - timedelta(days=1)
    delta = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=delta)


def compute_federal_holidays(year: int) -> FrozenSet[date]:
    """Compute the set of observed federal holidays for a given year.

    Holidays included:
        - New Year's Day (Jan 1)
        - Martin Luther King Jr. Day (3rd Monday in January)
        - Presidents' Day (3rd Monday in February)
        - Memorial Day (last Monday in May)
        - Juneteenth (Jun 19)
        - Independence Day (Jul 4)
        - Labor Day (1st Monday in September)
        - Columbus Day (2nd Monday in October)
        - Veterans Day (Nov 11)
        - Thanksgiving Day (4th Thursday in November)
        - Christmas Day (Dec 25)
    """
    holidays: Set[date] = set()

    # New Year's Day
    holidays.add(_observed(date(year, 1, 1)))

    # MLK Day — 3rd Monday in January
    holidays.add(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day — 3rd Monday in February
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Memorial Day — last Monday in May
    holidays.add(_last_weekday(year, 5, 0))

    # Juneteenth — Jun 19
    holidays.add(_observed(date(year, 6, 19)))

    # Independence Day — Jul 4
    holidays.add(_observed(date(year, 7, 4)))

    # Labor Day — 1st Monday in September
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Columbus Day — 2nd Monday in October
    holidays.add(_nth_weekday(year, 10, 0, 2))

    # Veterans Day — Nov 11
    holidays.add(_observed(date(year, 11, 11)))

    # Thanksgiving — 4th Thursday in November
    holidays.add(_nth_weekday(year, 11, 3, 4))

    # Christmas Day — Dec 25
    holidays.add(_observed(date(year, 12, 25)))

    return frozenset(holidays)


# Pre-computed for the years we care about most.  Other years are
# computed on demand and cached at module level.
_HOLIDAY_CACHE: dict[int, FrozenSet[date]] = {}


def get_federal_holidays(year: int) -> FrozenSet[date]:
    """Return the set of observed federal holidays for a given year.

    Results are cached for the lifetime of the process.
    """
    if year not in _HOLIDAY_CACHE:
        _HOLIDAY_CACHE[year] = compute_federal_holidays(year)
    return _HOLIDAY_CACHE[year]


def get_holidays_for_range(start: date, end: date) -> FrozenSet[date]:
    """Return all federal holidays in the date range [start, end]."""
    all_holidays: Set[date] = set()
    for year in range(start.year, end.year + 1):
        all_holidays.update(get_federal_holidays(year))
    return frozenset(h for h in all_holidays if start <= h <= end)


# ---------------------------------------------------------------------------
# Business Day Arithmetic
# ---------------------------------------------------------------------------

def is_business_day(
    d: date,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> bool:
    """Return True if d is a business day (not weekend, not holiday).

    Args:
        d: The date to check.
        custom_holidays: Optional additional holidays (org-level calendar).
            These are merged with federal holidays — they do not replace them.
    """
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    holidays = get_federal_holidays(d.year)
    if d in holidays:
        return False
    if custom_holidays and d in custom_holidays:
        return False
    return True


def _next_business_day(
    d: date,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> date:
    """Return d if it is a business day, otherwise advance to the next one."""
    while not is_business_day(d, custom_holidays):
        d += timedelta(days=1)
    return d


def _prev_business_day(
    d: date,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> date:
    """Return d if it is a business day, otherwise retreat to the previous one."""
    while not is_business_day(d, custom_holidays):
        d -= timedelta(days=1)
    return d


def add_business_days(
    start_date: date,
    num_days: int,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> date:
    """Add num_days business days to start_date.

    The start_date itself is NOT counted; the count begins on the
    next calendar day.  This matches TRID's "3 business days from
    application" interpretation (CFPB FAQ).

    Args:
        start_date: The reference date (e.g. application date).
        num_days: Number of business days to add (must be >= 0).
        custom_holidays: Optional additional holidays.

    Returns:
        The resulting business day.
    """
    if num_days < 0:
        raise ValueError("num_days must be >= 0; use subtract_business_days for reverse")
    if num_days == 0:
        return _next_business_day(start_date, custom_holidays)

    current = start_date
    counted = 0
    while counted < num_days:
        current += timedelta(days=1)
        if is_business_day(current, custom_holidays):
            counted += 1
    return current


def subtract_business_days(
    end_date: date,
    num_days: int,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> date:
    """Subtract num_days business days from end_date.

    Counts backward — the end_date itself is NOT counted.

    Args:
        end_date: The reference date (e.g. closing date).
        num_days: Number of business days to subtract (must be >= 0).
        custom_holidays: Optional additional holidays.

    Returns:
        The resulting business day.
    """
    if num_days < 0:
        raise ValueError("num_days must be >= 0; use add_business_days for forward")
    if num_days == 0:
        return _prev_business_day(end_date, custom_holidays)

    current = end_date
    counted = 0
    while counted < num_days:
        current -= timedelta(days=1)
        if is_business_day(current, custom_holidays):
            counted += 1
    return current


def count_business_days(
    start: date,
    end: date,
    custom_holidays: Optional[FrozenSet[date]] = None,
) -> int:
    """Count business days between start and end (exclusive of both endpoints).

    If start == end, returns 0.
    If end < start, returns a negative count.

    Args:
        start: Start date (not counted).
        end: End date (not counted).
        custom_holidays: Optional additional holidays.

    Returns:
        Number of business days strictly between start and end.
    """
    if start == end:
        return 0

    if end < start:
        return -count_business_days(end, start, custom_holidays)

    count = 0
    current = start + timedelta(days=1)
    while current < end:
        if is_business_day(current, custom_holidays):
            count += 1
        current += timedelta(days=1)
    return count


# ---------------------------------------------------------------------------
# Pydantic Models for API Responses
# ---------------------------------------------------------------------------

class HolidayInfo(BaseModel):
    """A single federal holiday."""
    date: date
    name: str
    observed: bool  # True if the observed date differs from the actual date


class HolidayCalendar(BaseModel):
    """Holiday calendar for a given year."""
    year: int
    holidays: List[HolidayInfo]


# Holiday name lookup (actual date -> name)
_HOLIDAY_NAMES = {
    (1, 1): "New Year's Day",
    (1, "mlk"): "Martin Luther King Jr. Day",
    (2, "pres"): "Presidents' Day",
    (5, "mem"): "Memorial Day",
    (6, 19): "Juneteenth National Independence Day",
    (7, 4): "Independence Day",
    (9, "labor"): "Labor Day",
    (10, "col"): "Columbus Day",
    (11, 11): "Veterans Day",
    (11, "thanks"): "Thanksgiving Day",
    (12, 25): "Christmas Day",
}


def get_holiday_calendar(year: int) -> HolidayCalendar:
    """Return a structured holiday calendar with names for a given year."""
    holidays_list: List[HolidayInfo] = []

    # Build each holiday with its name and observed status
    _entries = [
        ("New Year's Day", date(year, 1, 1)),
        ("Martin Luther King Jr. Day", _nth_weekday(year, 1, 0, 3)),
        ("Presidents' Day", _nth_weekday(year, 2, 0, 3)),
        ("Memorial Day", _last_weekday(year, 5, 0)),
        ("Juneteenth National Independence Day", date(year, 6, 19)),
        ("Independence Day", date(year, 7, 4)),
        ("Labor Day", _nth_weekday(year, 9, 0, 1)),
        ("Columbus Day", _nth_weekday(year, 10, 0, 2)),
        ("Veterans Day", date(year, 11, 11)),
        ("Thanksgiving Day", _nth_weekday(year, 11, 3, 4)),
        ("Christmas Day", date(year, 12, 25)),
    ]

    for name, actual in _entries:
        obs = _observed(actual)
        holidays_list.append(HolidayInfo(
            date=obs,
            name=name,
            observed=(obs != actual),
        ))

    holidays_list.sort(key=lambda h: h.date)

    return HolidayCalendar(year=year, holidays=holidays_list)
