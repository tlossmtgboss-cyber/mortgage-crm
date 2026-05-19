"""
Holiday Calendar — Perennia AI

State-aware US holiday calendar with business-day and business-hour math.
Supersedes the inline FEDERAL_HOLIDAYS set in
``services.smart_docs.enterprise.sla_enforcement_service``.

Public surface::

    cal = HolidayCalendar(custom_closures=[date(2026, 12, 24)])
    cal.is_holiday(date(2026, 7, 4))                 # True (Independence Day)
    cal.is_holiday(date(2026, 3, 31), state="CA")    # True (Cesar Chavez Day)
    cal.next_business_day(date(2026, 7, 3))          # date(2026, 7, 6)
    cal.business_days_between(date(2026, 7, 1), date(2026, 7, 8))
    cal.business_hours_between(dt1, dt2, state="CA")

Tenant-configurable: custom_closures, business hours/day.

Federal holiday count: 11 (10 federal + Juneteenth)
State holiday coverage: CA (2), NY (1), TX (2), FL (0), IL (2)
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ============================================================================
# HOLIDAY DEFINITIONS
# ============================================================================

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """nth occurrence of ``weekday`` (0=Mon) in ``month``. Use n=-1 for last."""
    if n == -1:
        last = calendar.monthrange(year, month)[1]
        d = date(year, month, last)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _us_federal_holidays(year: int) -> List[Tuple[date, str]]:
    """11 US federal holidays for ``year`` (includes Juneteenth)."""
    return [
        (date(year, 1, 1), "New Year's Day"),
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (_nth_weekday(year, 2, 0, 3), "Presidents' Day"),
        (_nth_weekday(year, 5, 0, -1), "Memorial Day"),
        (date(year, 6, 19), "Juneteenth"),
        (date(year, 7, 4), "Independence Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (_nth_weekday(year, 10, 0, 2), "Columbus Day"),
        (date(year, 11, 11), "Veterans Day"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving Day"),
        (date(year, 12, 25), "Christmas Day"),
    ]


# Pre-computed 2026 federal holidays for quick reference / tests
FEDERAL_HOLIDAYS_2026: List[Tuple[date, str]] = _us_federal_holidays(2026)


def _ca_state_holidays(year: int) -> List[Tuple[date, str]]:
    """California state-specific bank holidays."""
    return [
        (date(year, 3, 31), "Cesar Chavez Day"),
        # Day after Thanksgiving (Black Friday) — observed by CA state offices
        (_nth_weekday(year, 11, 3, 4) + timedelta(days=1), "Day After Thanksgiving"),
    ]


def _ny_state_holidays(year: int) -> List[Tuple[date, str]]:
    """New York state-specific holidays. Election Day = 1st Tue after 1st Mon of Nov."""
    nov_1 = date(year, 11, 1)
    first_mon_offset = (0 - nov_1.weekday()) % 7
    first_mon = nov_1 + timedelta(days=first_mon_offset)
    election_day = first_mon + timedelta(days=1)
    return [
        (election_day, "Election Day"),
    ]


def _tx_state_holidays(year: int) -> List[Tuple[date, str]]:
    """Texas state-specific holidays."""
    return [
        (date(year, 3, 2), "Texas Independence Day"),
        (date(year, 4, 21), "Battle of San Jacinto Day"),
    ]


def _fl_state_holidays(year: int) -> List[Tuple[date, str]]:
    """Florida adds no extra closures beyond federal calendar."""
    return []


def _il_state_holidays(year: int) -> List[Tuple[date, str]]:
    """Illinois state-specific holidays."""
    return [
        (date(year, 2, 12), "Lincoln's Birthday"),
        (date(year, 3, 6), "Casimir Pulaski Day"),
    ]


_STATE_HOLIDAY_FNS = {
    "CA": _ca_state_holidays,
    "NY": _ny_state_holidays,
    "TX": _tx_state_holidays,
    "FL": _fl_state_holidays,
    "IL": _il_state_holidays,
}

# Pre-computed 2026 state holidays (used by docs / tests).
STATE_HOLIDAYS: Dict[str, List[Dict]] = {
    code: [{"date": d, "name": n} for d, n in fn(2026)]
    for code, fn in _STATE_HOLIDAY_FNS.items()
}


# ============================================================================
# HOLIDAY CALENDAR
# ============================================================================

class HolidayCalendar:
    """State-aware holiday calendar with business-day/business-hour math."""

    def __init__(
        self,
        custom_closures: Optional[Iterable[date]] = None,
        business_start_hour: int = 8,
        business_end_hour: int = 18,
        hours_per_day: Optional[float] = None,
    ):
        self.custom_closures: Set[date] = set(custom_closures or [])
        self.business_start_hour = business_start_hour
        self.business_end_hour = business_end_hour
        self.hours_per_day = (
            float(hours_per_day)
            if hours_per_day is not None
            else float(business_end_hour - business_start_hour)
        )
        # Cache of {(year, state|None): set(date)}
        self._cache: Dict[Tuple[int, Optional[str]], Set[date]] = {}

    # ------------------------------------------------------------------
    def _holidays_for(self, year: int, state: Optional[str] = None) -> Set[date]:
        state = state.upper() if state else None
        key = (year, state)
        if key in self._cache:
            return self._cache[key]
        days: Set[date] = {d for d, _n in _us_federal_holidays(year)}
        if state and state in _STATE_HOLIDAY_FNS:
            days |= {d for d, _n in _STATE_HOLIDAY_FNS[state](year)}
        self._cache[key] = days
        return days

    # ------------------------------------------------------------------
    def is_holiday(self, d: date, state: Optional[str] = None) -> bool:
        """True if ``d`` is a federal holiday, state holiday, or custom closure."""
        if isinstance(d, datetime):
            d = d.date()
        if d in self.custom_closures:
            return True
        return d in self._holidays_for(d.year, state)

    def is_weekend(self, d: date) -> bool:
        if isinstance(d, datetime):
            d = d.date()
        return d.weekday() >= 5

    def is_business_day(self, d: date, state: Optional[str] = None) -> bool:
        if isinstance(d, datetime):
            d = d.date()
        return not (self.is_weekend(d) or self.is_holiday(d, state))

    # ------------------------------------------------------------------
    def next_business_day(self, d: date, state: Optional[str] = None) -> date:
        """Smallest business day strictly *after* ``d``."""
        if isinstance(d, datetime):
            d = d.date()
        candidate = d + timedelta(days=1)
        # Safety bound: at most ~14 days of skipping (long weekend + holiday)
        for _ in range(20):
            if self.is_business_day(candidate, state):
                return candidate
            candidate += timedelta(days=1)
        return candidate  # pragma: no cover — defensive

    def previous_business_day(self, d: date, state: Optional[str] = None) -> date:
        if isinstance(d, datetime):
            d = d.date()
        candidate = d - timedelta(days=1)
        for _ in range(20):
            if self.is_business_day(candidate, state):
                return candidate
            candidate -= timedelta(days=1)
        return candidate  # pragma: no cover

    # ------------------------------------------------------------------
    def business_days_between(
        self,
        start: date,
        end: date,
        state: Optional[str] = None,
    ) -> int:
        """
        Count of business days in [start, end). Half-open interval — the
        start day counts if it's a business day; the end day does not. This
        matches "days elapsed since milestone" semantics.
        """
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        if end <= start:
            return 0
        count = 0
        current = start
        while current < end:
            if self.is_business_day(current, state):
                count += 1
            current += timedelta(days=1)
        return count

    # ------------------------------------------------------------------
    def business_hours_between(
        self,
        start: datetime,
        end: datetime,
        state: Optional[str] = None,
        hours_per_day: Optional[float] = None,
    ) -> float:
        """
        Approximate business hours between two timestamps. Uses
        ``hours_per_day`` per full business day; partial days are pro-rated
        within the configured window.
        """
        if end <= start:
            return 0.0
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        hpd = float(hours_per_day) if hours_per_day is not None else self.hours_per_day
        s_hour = self.business_start_hour
        e_hour = self.business_end_hour
        full_day_window = max(1e-9, float(e_hour - s_hour))

        def _hours_in_day(d: date, win_start: float, win_end: float) -> float:
            if not self.is_business_day(d, state):
                return 0.0
            lo = max(win_start, float(s_hour))
            hi = min(win_end, float(e_hour))
            if hi <= lo:
                return 0.0
            return (hi - lo) * (hpd / full_day_window)

        total = 0.0
        current = start.date()
        end_date = end.date()
        while current <= end_date:
            if current == start.date() == end_date:
                total += _hours_in_day(
                    current,
                    start.hour + start.minute / 60.0,
                    end.hour + end.minute / 60.0,
                )
            elif current == start.date():
                total += _hours_in_day(
                    current,
                    start.hour + start.minute / 60.0,
                    float(e_hour),
                )
            elif current == end_date:
                total += _hours_in_day(
                    current,
                    float(s_hour),
                    end.hour + end.minute / 60.0,
                )
            else:
                if self.is_business_day(current, state):
                    total += hpd
            current += timedelta(days=1)
        return total

    # ------------------------------------------------------------------
    def list_holidays(
        self,
        year: int,
        state: Optional[str] = None,
    ) -> List[Tuple[date, str]]:
        """All holidays for ``year`` (federal + state if provided), sorted."""
        out = list(_us_federal_holidays(year))
        if state and state.upper() in _STATE_HOLIDAY_FNS:
            out.extend(_STATE_HOLIDAY_FNS[state.upper()](year))
        out.sort(key=lambda t: t[0])
        return out


__all__ = [
    "HolidayCalendar",
    "FEDERAL_HOLIDAYS_2026",
    "STATE_HOLIDAYS",
]
