"""
Natural Language Date/Time Parser for AI Scheduling

Parses conversational date/time expressions into structured datetime objects.
Designed for phone conversations where callers say things like:
- "tomorrow afternoon"
- "next Tuesday at 2"
- "sometime this week"
- "Monday or Wednesday, I'm flexible"
- "as soon as possible"
- "after 3pm any day"
- "not mornings, I work until noon"
- "the week of the 15th"
- "in about two weeks"

No external dependencies (no dateparser, no parsedatetime).
Uses Python's datetime + regex for reliable parsing.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "twenty": 20, "thirty": 30,
}

ORDINALS = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9, "10th": 10,
    "11th": 11, "12th": 12, "13th": 13, "14th": 14, "15th": 15,
    "16th": 16, "17th": 17, "18th": 18, "19th": 19, "20th": 20,
    "21st": 21, "22nd": 22, "23rd": 23, "24th": 24, "25th": 25,
    "26th": 26, "27th": 27, "28th": 28, "29th": 29, "30th": 30,
    "31st": 31,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25,
    "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28,
    "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31,
}

# Time-of-day windows (hour ranges in 24h format)
TIME_OF_DAY = {
    "morning": (9, 12),
    "late morning": (10, 12),
    "early morning": (8, 10),
    "afternoon": (12, 17),
    "early afternoon": (12, 14),
    "late afternoon": (15, 17),
    "evening": (17, 20),
    "early evening": (17, 19),
    "late evening": (19, 21),
    "lunch": (11, 13),
    "lunchtime": (11, 13),
    "noon": (12, 13),
    "midday": (11, 13),
    "end of day": (16, 18),
    "close of business": (16, 18),
    "eod": (16, 18),
    "cob": (16, 18),
}

# Patterns that signal urgency / ASAP
ASAP_PATTERNS = [
    r"\bas\s+soon\s+as\s+possible\b",
    r"\basap\b",
    r"\bfirst\s+available\b",
    r"\bearliest\b",
    r"\bsoonest\b",
    r"\bright\s+away\b",
    r"\bimmediately\b",
    r"\btoday\s+if\s+possible\b",
    r"\bnext\s+opening\b",
    r"\bfirst\s+opening\b",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedDateRange:
    """Structured result from parsing a natural language date/time expression."""

    dates: List[date] = field(default_factory=list)
    time_range: Optional[Tuple[time, time]] = None
    flexibility: str = "flexible"          # 'exact', 'flexible', 'very_flexible'
    constraints: List[str] = field(default_factory=list)
    confidence: float = 0.5
    raw_text: str = ""

    @property
    def has_dates(self) -> bool:
        return len(self.dates) > 0

    @property
    def has_time(self) -> bool:
        return self.time_range is not None

    def to_dict(self) -> dict:
        return {
            "dates": [d.isoformat() for d in self.dates],
            "time_range": (
                [self.time_range[0].strftime("%H:%M"), self.time_range[1].strftime("%H:%M")]
                if self.time_range else None
            ),
            "flexibility": self.flexibility,
            "constraints": self.constraints,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
        }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _word_to_number(word: str) -> Optional[int]:
    """Convert a word like 'three' or '3' to an integer."""
    word = word.strip().lower()
    if word in WORD_NUMBERS:
        return WORD_NUMBERS[word]
    try:
        return int(word)
    except (ValueError, TypeError):
        return None


def _next_weekday(ref: date, weekday: int) -> date:
    """Return the next occurrence of *weekday* (0=Mon) on or after *ref* + 1 day.

    If today IS the requested weekday we still advance to the following week
    because callers saying "Tuesday" during a conversation on Tuesday almost
    certainly mean *next* Tuesday.
    """
    days_ahead = weekday - ref.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return ref + timedelta(days=days_ahead)


def _weekdays_in_range(start: date, end: date) -> List[date]:
    """Return all weekdays (Mon-Fri) in [start, end] inclusive."""
    days: List[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _localize_now(timezone: str) -> datetime:
    """Get timezone-aware 'now'."""
    tz = ZoneInfo(timezone)
    return datetime.now(tz)


# ---------------------------------------------------------------------------
# Core parsing helpers
# ---------------------------------------------------------------------------


def _parse_specific_time(text: str) -> Optional[Tuple[time, time, float]]:
    """Try to extract a specific clock time from *text*.

    Returns ``(start_time, end_time, confidence)`` or ``None``.
    A specific time like "at 2:30 pm" produces a 30-min window.
    """
    text_lower = text.lower().strip()

    # Skip bare numbers that are preceded by a month name (they're date components)
    # e.g., "March 15" — the "15" is a day, not a time.
    month_pat = "|".join(MONTH_NAMES.keys())
    if re.search(rf"(?:{month_pat})\s+\d{{1,2}}\b", text_lower):
        # Only continue if there's also an explicit time marker (at, @, am, pm, :)
        if not re.search(r"(?:at\s+|@\s*)\d{1,2}|:\d{2}|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)", text_lower):
            return None

    # "at HH:MM am/pm" or "at H am/pm" or just "H:MM pm" etc.
    # Require either "at"/"@" prefix OR am/pm suffix OR colon for minutes
    # to avoid matching bare numbers like ordinals or day-of-month.
    pat = (
        r"(?:at\s+|@\s*)"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*"
        r"(a\.?m\.?|p\.?m\.?|am|pm)?"
    )
    m = re.search(pat, text_lower)
    if not m:
        # Try matching number with explicit am/pm (no "at" required)
        pat2 = r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)"
        m = re.search(pat2, text_lower)
    if not m:
        # Try matching HH:MM (colon required, no am/pm needed)
        pat3 = r"(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?"
        m = re.search(pat3, text_lower)
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)

    if ampm:
        ampm_clean = ampm.replace(".", "").lower()
        if ampm_clean == "pm" and hour < 12:
            hour += 12
        elif ampm_clean == "am" and hour == 12:
            hour = 0
    else:
        # No am/pm: apply heuristic -- if hour <= 7, likely PM for business
        if 1 <= hour <= 7:
            hour += 12

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    start = time(hour, minute)
    # 30-min window
    end_dt = datetime.combine(date.today(), start) + timedelta(minutes=30)
    end = end_dt.time()

    conf = 0.9 if ampm else 0.7
    return (start, end, conf)


def _parse_around_time(text: str) -> Optional[Tuple[time, time, float]]:
    """Parse "around 3pm", "about 2:30"."""
    m = re.search(
        r"(?:around|about|roughly|approximately)\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm)?",
        text.lower(),
    )
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)

    if ampm:
        ampm_clean = ampm.replace(".", "").lower()
        if ampm_clean == "pm" and hour < 12:
            hour += 12
        elif ampm_clean == "am" and hour == 12:
            hour = 0
    else:
        if 1 <= hour <= 7:
            hour += 12

    if hour < 0 or hour > 23:
        return None

    # +/- 1 hour window
    start_dt = datetime.combine(date.today(), time(hour, minute)) - timedelta(hours=1)
    end_dt = datetime.combine(date.today(), time(hour, minute)) + timedelta(hours=1)
    return (start_dt.time(), end_dt.time(), 0.6)


def _parse_time_range(text: str) -> Optional[Tuple[time, time, float]]:
    """Parse "between 1 and 4", "from 2 to 5 pm", "1-3pm"."""
    patterns = [
        r"between\s+(\d{1,2})(?::(\d{2}))?\s*(?:am|pm|a\.m\.|p\.m\.)?\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?",
        r"from\s+(\d{1,2})(?::(\d{2}))?\s*(?:am|pm|a\.m\.|p\.m\.)?\s+(?:to|until|till)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?",
        r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?",
    ]

    text_lower = text.lower()
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            h1 = int(m.group(1))
            m1 = int(m.group(2)) if m.group(2) else 0
            h2 = int(m.group(3))
            m2 = int(m.group(4)) if m.group(4) else 0
            ampm = m.group(5)

            if ampm:
                ampm_clean = ampm.replace(".", "").lower()
                if ampm_clean == "pm":
                    if h2 < 12:
                        h2 += 12
                    # Also adjust h1 if it looks like same half-day
                    if h1 < 12 and h1 < h2 - 12:
                        h1 += 12
                    elif h1 < 12 and h1 <= 7:
                        h1 += 12
            else:
                # Heuristic: business hours
                if 1 <= h1 <= 7:
                    h1 += 12
                if 1 <= h2 <= 7:
                    h2 += 12

            if 0 <= h1 <= 23 and 0 <= h2 <= 23:
                return (time(h1, m1), time(h2, m2), 0.8)

    return None


def _parse_time_of_day(text: str) -> Optional[Tuple[time, time, float]]:
    """Parse time-of-day keywords like 'morning', 'afternoon', 'evening'."""
    text_lower = text.lower()

    # Check longer phrases first to avoid partial matches
    for phrase in sorted(TIME_OF_DAY.keys(), key=len, reverse=True):
        if phrase in text_lower:
            h_start, h_end = TIME_OF_DAY[phrase]
            return (time(h_start, 0), time(h_end, 0), 0.7)

    return None


def _parse_time_of_day_safe(text: str) -> Optional[Tuple[time, time, float]]:
    """Like _parse_time_of_day but skip when the keyword is in negation context.

    "not mornings" or "can't do afternoons" should NOT produce a time range;
    instead the constraint parser handles those.
    """
    text_lower = text.lower()

    negation_prefixes = [
        r"not?\s+(?:in\s+the\s+)?",
        r"(?:can'?t|cannot|don'?t|won'?t)\s+(?:do|make)\s+",
        r"no\s+",
    ]

    for phrase in sorted(TIME_OF_DAY.keys(), key=len, reverse=True):
        if phrase in text_lower:
            # Check if preceded by a negation
            is_negated = False
            for neg in negation_prefixes:
                if re.search(neg + re.escape(phrase), text_lower):
                    is_negated = True
                    break
            if is_negated:
                return None
            h_start, h_end = TIME_OF_DAY[phrase]
            return (time(h_start, 0), time(h_end, 0), 0.7)

    return None


def _parse_after_before(text: str) -> Optional[Tuple[time, time, float]]:
    """Parse 'after 3pm', 'before noon', 'before 2'."""
    text_lower = text.lower()

    # "after <time>"
    m = re.search(r"after\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3)
        if ampm and "pm" in ampm.replace(".", "") and hour < 12:
            hour += 12
        elif ampm and "am" in ampm.replace(".", "") and hour == 12:
            hour = 0
        elif not ampm and 1 <= hour <= 7:
            hour += 12
        if 0 <= hour <= 23:
            return (time(hour, minute), time(20, 0), 0.7)

    # "after noon" / "after lunch"
    if "after noon" in text_lower or "after lunch" in text_lower:
        return (time(12, 0), time(17, 0), 0.7)

    # "before noon"
    if "before noon" in text_lower:
        return (time(9, 0), time(12, 0), 0.7)

    # "before <time>"
    m = re.search(r"before\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3)
        if ampm and "pm" in ampm.replace(".", "") and hour < 12:
            hour += 12
        elif ampm and "am" in ampm.replace(".", "") and hour == 12:
            hour = 0
        elif not ampm and 1 <= hour <= 7:
            hour += 12
        if 0 <= hour <= 23:
            return (time(9, 0), time(hour, minute), 0.7)

    return None


# ---------------------------------------------------------------------------
# Constraint parsing
# ---------------------------------------------------------------------------


def _parse_constraints(text: str) -> List[str]:
    """Extract scheduling constraints (negations, preferences)."""
    constraints: List[str] = []
    text_lower = text.lower()

    negation_patterns = [
        (r"not?\s+(?:in\s+the\s+)?mornings?", "no_mornings"),
        (r"not?\s+(?:in\s+the\s+)?afternoons?", "no_afternoons"),
        (r"not?\s+(?:in\s+the\s+)?evenings?", "no_evenings"),
        (r"(?:i\s+)?(?:can'?t|cannot|don'?t|won'?t)\s+(?:do|make)\s+mornings?", "no_mornings"),
        (r"(?:i\s+)?(?:can'?t|cannot|don'?t|won'?t)\s+(?:do|make)\s+afternoons?", "no_afternoons"),
        (r"(?:i\s+)?(?:can'?t|cannot|don'?t|won'?t)\s+(?:do|make)\s+evenings?", "no_evenings"),
        (r"(?:i\s+)?work\s+until\s+noon", "no_mornings"),
        (r"(?:i\s+)?work\s+until\s+(\d{1,2})\s*(am|pm)?", "unavailable_until"),
        (r"not?\s+(?:on\s+)?mondays?", "no_monday"),
        (r"not?\s+(?:on\s+)?tuesdays?", "no_tuesday"),
        (r"not?\s+(?:on\s+)?wednesdays?", "no_wednesday"),
        (r"not?\s+(?:on\s+)?thursdays?", "no_thursday"),
        (r"not?\s+(?:on\s+)?fridays?", "no_friday"),
        (r"not?\s+(?:on\s+)?weekends?", "no_weekends"),
    ]

    for pattern, constraint in negation_patterns:
        if re.search(pattern, text_lower):
            if constraint == "unavailable_until":
                m = re.search(r"work\s+until\s+(\d{1,2})\s*(am|pm)?", text_lower)
                if m:
                    h = int(m.group(1))
                    ampm = m.group(2)
                    if ampm and "pm" in ampm and h < 12:
                        h += 12
                    elif not ampm and 1 <= h <= 7:
                        h += 12
                    constraints.append(f"unavailable_before_{h}:00")
            else:
                constraints.append(constraint)

    # Flexibility keywords
    if re.search(r"\bflexible\b|\bi'?m\s+open\b|\bany\s*time\b|\bwhenever\b", text_lower):
        constraints.append("caller_flexible")

    return constraints


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _parse_dates(text: str, ref: date) -> Tuple[List[date], float, str]:
    """Parse date expressions. Returns (dates, confidence, flexibility)."""
    text_lower = text.lower().strip()
    dates: List[date] = []
    confidence = 0.5
    flexibility = "flexible"

    # --- ASAP ---
    for pat in ASAP_PATTERNS:
        if re.search(pat, text_lower):
            # Today + next 3 business days
            dates = _weekdays_in_range(ref, ref + timedelta(days=5))[:4]
            if ref.weekday() < 5:
                dates = [ref] + [d for d in dates if d != ref]
            return (dates[:4], 0.8, "very_flexible")

    # --- "today" ---
    if re.search(r"\btoday\b", text_lower):
        dates.append(ref)
        confidence = 0.95
        flexibility = "exact"

    # --- "tomorrow" ---
    if re.search(r"\btomorrow\b", text_lower):
        dates.append(ref + timedelta(days=1))
        confidence = 0.95
        flexibility = "exact"

    # --- "day after tomorrow" ---
    if re.search(r"\bday\s+after\s+tomorrow\b", text_lower):
        dates.append(ref + timedelta(days=2))
        confidence = 0.9
        flexibility = "exact"

    # --- "in N days/weeks" ---
    m = re.search(r"in\s+(?:about\s+)?(\d+|" + "|".join(WORD_NUMBERS.keys()) + r")\s+(days?|weeks?)", text_lower)
    if m:
        n = _word_to_number(m.group(1))
        unit = m.group(2)
        if n is not None:
            if "week" in unit:
                target = ref + timedelta(weeks=n)
                # Return weekdays of that week
                week_start = target - timedelta(days=target.weekday())
                dates = _weekdays_in_range(week_start, week_start + timedelta(days=4))
                confidence = 0.7
                flexibility = "flexible"
            else:
                dates.append(ref + timedelta(days=n))
                confidence = 0.85
                flexibility = "exact"

    # --- "next week" / "this week" ---
    if re.search(r"\bnext\s+week\b", text_lower) and not dates:
        # Monday-Friday of next week
        next_monday = ref + timedelta(days=(7 - ref.weekday()))
        dates = _weekdays_in_range(next_monday, next_monday + timedelta(days=4))
        confidence = 0.75
        flexibility = "very_flexible"

    if re.search(r"\bthis\s+week\b", text_lower) and not dates:
        # Remaining weekdays this week
        remaining = _weekdays_in_range(ref, ref + timedelta(days=(4 - ref.weekday())))
        dates = [d for d in remaining if d >= ref]
        if not dates:
            # If it's late in the week, include next Monday
            dates = [ref + timedelta(days=1)]
        confidence = 0.7
        flexibility = "flexible"

    # --- "the week of the 15th" / "week of March 20" ---
    m = re.search(
        r"(?:the\s+)?week\s+of\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        text_lower,
    )
    if m and not dates:
        day_num = int(m.group(1))
        # Figure out which month: current or next
        try:
            target = ref.replace(day=day_num)
            if target < ref:
                # Move to next month
                if ref.month == 12:
                    target = target.replace(year=ref.year + 1, month=1)
                else:
                    target = target.replace(month=ref.month + 1)
            week_start = target - timedelta(days=target.weekday())
            dates = _weekdays_in_range(week_start, week_start + timedelta(days=4))
            confidence = 0.7
            flexibility = "flexible"
        except ValueError:
            pass

    # --- Month + day: "March 15", "March 15th", "the 15th" ---
    if not dates:
        m = re.search(
            r"(?:(" + "|".join(MONTH_NAMES.keys()) + r")\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
            text_lower,
        )
        if m and m.group(2):
            month_str = m.group(1)
            day_num = int(m.group(2))
            if month_str:
                month = MONTH_NAMES.get(month_str)
                if month and 1 <= day_num <= 31:
                    year = ref.year
                    try:
                        target = date(year, month, day_num)
                        if target < ref:
                            target = date(year + 1, month, day_num)
                        dates.append(target)
                        confidence = 0.9
                        flexibility = "exact"
                    except ValueError:
                        pass
            elif 1 <= day_num <= 31:
                # Just "the 15th" — assume current or next month
                # But only if the text looks like it's referring to a date
                # (has ordinal or "the" prefix)
                if re.search(r"(?:the\s+)?\d{1,2}(?:st|nd|rd|th)", text_lower):
                    try:
                        target = ref.replace(day=day_num)
                        if target < ref:
                            if ref.month == 12:
                                target = target.replace(year=ref.year + 1, month=1)
                            else:
                                target = target.replace(month=ref.month + 1)
                        dates.append(target)
                        confidence = 0.75
                        flexibility = "exact"
                    except ValueError:
                        pass

    # --- Ordinal lookup (e.g., "the fifteenth") ---
    if not dates:
        for word, day_num in ORDINALS.items():
            if word in text_lower and 1 <= day_num <= 31:
                # Only match if it looks like a date context
                if re.search(rf"\b{re.escape(word)}\b", text_lower):
                    try:
                        target = ref.replace(day=day_num)
                        if target < ref:
                            if ref.month == 12:
                                target = target.replace(year=ref.year + 1, month=1)
                            else:
                                target = target.replace(month=ref.month + 1)
                        dates.append(target)
                        confidence = 0.7
                        flexibility = "exact"
                        break
                    except ValueError:
                        pass

    # --- Named days: "Monday", "next Tuesday", "this Friday" ---
    # Handle multi-option: "Monday or Wednesday"
    day_matches = []
    for day_name, weekday_num in DAY_NAMES.items():
        if re.search(rf"\b{day_name}\b", text_lower):
            # Avoid duplicates (e.g., "mon" inside "monday")
            if not any(wn == weekday_num for wn in day_matches):
                day_matches.append(weekday_num)

    if day_matches and not dates:
        is_next = bool(re.search(r"\bnext\b", text_lower))
        for weekday_num in day_matches:
            target = _next_weekday(ref, weekday_num)
            if is_next and target - ref <= timedelta(days=7):
                target += timedelta(days=7)
            dates.append(target)

        confidence = 0.85
        flexibility = "exact" if len(day_matches) == 1 else "flexible"

    # --- "sometime" / vague ---
    if not dates:
        if re.search(r"\bsometime\b|\bwhenever\b|\bany\s*day\b|\bopen\b", text_lower):
            # Default: next 5 business days
            dates = _weekdays_in_range(ref + timedelta(days=1), ref + timedelta(days=9))[:5]
            confidence = 0.4
            flexibility = "very_flexible"

    return (dates, confidence, flexibility)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_datetime_expression(
    text: str,
    reference_date: Optional[datetime] = None,
    timezone: str = "America/New_York",
) -> ParsedDateRange:
    """Parse a natural language date/time expression into a structured result.

    Parameters
    ----------
    text : str
        The raw conversational text, e.g. "next Tuesday afternoon".
    reference_date : datetime, optional
        The reference point for relative expressions. Defaults to *now*
        in the given timezone.
    timezone : str
        IANA timezone name. Defaults to ``America/New_York``.

    Returns
    -------
    ParsedDateRange
    """
    if not text or not text.strip():
        return ParsedDateRange(raw_text=text or "", confidence=0.0)

    if reference_date is None:
        reference_date = _localize_now(timezone)

    ref_date = (
        reference_date.date()
        if isinstance(reference_date, datetime)
        else reference_date
    )

    result = ParsedDateRange(raw_text=text.strip())

    # 1. Parse dates
    dates, date_conf, flexibility = _parse_dates(text, ref_date)
    result.dates = dates
    result.flexibility = flexibility

    # 2. Parse time expressions (try most specific first)
    #    - after/before must come before specific_time so "after 3pm" is not
    #      consumed as a bare "3pm" time.
    #    - time_of_day is skipped when the keyword appears in negation context
    #      (e.g. "not mornings") because constraints handle that instead.
    time_result = (
        _parse_time_range(text)
        or _parse_around_time(text)
        or _parse_after_before(text)
        or _parse_specific_time(text)
        or _parse_time_of_day_safe(text)
    )

    time_conf = 0.0
    if time_result:
        result.time_range = (time_result[0], time_result[1])
        time_conf = time_result[2]

    # 3. Parse constraints
    result.constraints = _parse_constraints(text)

    # Apply constraint-based time adjustments if no explicit time was parsed
    if not result.time_range:
        if "no_mornings" in result.constraints:
            result.time_range = (time(12, 0), time(20, 0))
            time_conf = 0.6
        elif "no_afternoons" in result.constraints:
            result.time_range = (time(9, 0), time(12, 0))
            time_conf = 0.6
        elif "no_evenings" in result.constraints:
            result.time_range = (time(9, 0), time(17, 0))
            time_conf = 0.6
        # Check for "unavailable_before_X:00" constraints
        for c in result.constraints:
            if c.startswith("unavailable_before_"):
                h_str = c.replace("unavailable_before_", "").replace(":00", "")
                try:
                    h = int(h_str)
                    result.time_range = (time(h, 0), time(20, 0))
                    time_conf = 0.65
                except ValueError:
                    pass

    # 4. Compute overall confidence
    if result.dates and result.time_range:
        result.confidence = round(min(date_conf, time_conf) * 1.1, 2)
    elif result.dates:
        result.confidence = round(date_conf * 0.9, 2)
    elif result.time_range:
        result.confidence = round(time_conf * 0.7, 2)
    else:
        result.confidence = 0.2

    # Clamp
    result.confidence = min(result.confidence, 1.0)

    # 5. If flexibility was set by constraints, override
    if "caller_flexible" in result.constraints and result.flexibility != "very_flexible":
        result.flexibility = "very_flexible"

    # Filter out past dates for today
    if result.dates:
        today = ref_date
        result.dates = [d for d in result.dates if d >= today]
        # Deduplicate while preserving order
        seen = set()
        unique: List[date] = []
        for d in result.dates:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        result.dates = unique

    return result
