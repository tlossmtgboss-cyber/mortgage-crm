"""
Slot Matcher Service

Matches available calendar slots against parsed natural-language preferences
produced by ``nlp_datetime_parser.parse_datetime_expression``.

Usage::

    from services.nlp_datetime_parser import parse_datetime_expression
    from services.slot_matcher import match_slots_to_preference

    parsed = parse_datetime_expression("next Tuesday afternoon")
    ranked = match_slots_to_preference(available_slots, parsed, top_n=5)

Each *available_slot* is a dict with at least::

    {
        "start": "2026-03-15T14:00:00",   # ISO datetime
        "end":   "2026-03-15T14:30:00",   # ISO datetime
    }

Extra keys (``display``, ``available``, etc.) are passed through untouched.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional

from services.nlp_datetime_parser import ParsedDateRange

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

# Points awarded for various match criteria (higher = better)
_SCORE_EXACT_DATE = 100       # Slot date is in the preferred dates list
_SCORE_EXACT_TIME = 80        # Slot time falls entirely within preferred range
_SCORE_PARTIAL_TIME = 40      # Slot overlaps with preferred range
_SCORE_TIME_OF_DAY_MATCH = 60 # Slot is in the right half of the day
_SCORE_DATE_PROXIMITY = 50    # Slot is close to a preferred date (within 1 day)
_SCORE_WEEKDAY = 10           # Slot is on a weekday (small bonus)
_SCORE_BUSINESS_HOURS = 5     # Slot is within 9-5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(dt_str: str) -> Optional[datetime]:
    """Parse an ISO datetime string, tolerant of 'Z' suffix."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _time_in_range(t: time, start: time, end: time) -> bool:
    """Check if *t* falls within [start, end).

    Handles the simple case where start < end (no midnight wrap).
    """
    return start <= t < end


def _slot_overlaps_range(
    slot_start: time, slot_end: time, range_start: time, range_end: time
) -> bool:
    """Check if the slot time window overlaps with the preferred range."""
    return slot_start < range_end and slot_end > range_start


def _date_distance(d1: date, d2: date) -> int:
    """Absolute day distance between two dates."""
    return abs((d1 - d2).days)


# ---------------------------------------------------------------------------
# Constraint filtering
# ---------------------------------------------------------------------------

_DAY_CONSTRAINT_MAP = {
    "no_monday": 0,
    "no_tuesday": 1,
    "no_wednesday": 2,
    "no_thursday": 3,
    "no_friday": 4,
    "no_saturday": 5,
    "no_sunday": 6,
}


def _passes_constraints(
    slot_dt: datetime, constraints: List[str]
) -> bool:
    """Return False if the slot violates any hard constraint."""
    slot_weekday = slot_dt.weekday()
    slot_time = slot_dt.time()

    for c in constraints:
        # Day constraints
        if c in _DAY_CONSTRAINT_MAP:
            if slot_weekday == _DAY_CONSTRAINT_MAP[c]:
                return False

        # Weekend constraint
        if c == "no_weekends" and slot_weekday >= 5:
            return False

        # Time-of-day constraints
        if c == "no_mornings" and time(0, 0) <= slot_time < time(12, 0):
            return False
        if c == "no_afternoons" and time(12, 0) <= slot_time < time(17, 0):
            return False
        if c == "no_evenings" and slot_time >= time(17, 0):
            return False

        # "unavailable_before_HH:00"
        if c.startswith("unavailable_before_"):
            try:
                h = int(c.replace("unavailable_before_", "").replace(":00", ""))
                if slot_time < time(h, 0):
                    return False
            except ValueError:
                pass

    return True


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_slot(
    slot: Dict[str, Any],
    parsed: ParsedDateRange,
) -> float:
    """Compute a numeric score for how well *slot* matches *parsed* preferences."""
    start_dt = _parse_iso(slot.get("start", ""))
    if start_dt is None:
        return -1.0

    end_dt = _parse_iso(slot.get("end", ""))
    slot_date = start_dt.date()
    slot_time = start_dt.time()
    slot_end_time = end_dt.time() if end_dt else slot_time

    score = 0.0

    # --- Date scoring ---
    if parsed.dates:
        if slot_date in parsed.dates:
            score += _SCORE_EXACT_DATE
        else:
            # Proximity bonus: within 1 day of any preferred date
            min_dist = min(_date_distance(slot_date, d) for d in parsed.dates)
            if min_dist == 1:
                score += _SCORE_DATE_PROXIMITY
            elif min_dist <= 3:
                score += _SCORE_DATE_PROXIMITY * 0.3
    else:
        # No date preference: slight bonus for sooner slots
        # (lower distance from today = higher score)
        days_from_now = (slot_date - date.today()).days
        if 0 <= days_from_now <= 14:
            score += max(0, 30 - days_from_now * 2)

    # --- Time scoring ---
    if parsed.time_range:
        pref_start, pref_end = parsed.time_range
        if _time_in_range(slot_time, pref_start, pref_end):
            score += _SCORE_EXACT_TIME
        elif _slot_overlaps_range(slot_time, slot_end_time, pref_start, pref_end):
            score += _SCORE_PARTIAL_TIME
    else:
        # No time preference: prefer mid-morning / early-afternoon
        if time(10, 0) <= slot_time <= time(14, 0):
            score += _SCORE_TIME_OF_DAY_MATCH * 0.5

    # --- Minor bonuses ---
    if slot_date.weekday() < 5:
        score += _SCORE_WEEKDAY

    if time(9, 0) <= slot_time < time(17, 0):
        score += _SCORE_BUSINESS_HOURS

    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_slots_to_preference(
    available_slots: List[Dict[str, Any]],
    parsed_preference: ParsedDateRange,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Rank *available_slots* against *parsed_preference* and return the best matches.

    Parameters
    ----------
    available_slots : list of dict
        Each dict must have ``start`` and ``end`` keys (ISO datetime strings).
        Additional keys are preserved in the output.
    parsed_preference : ParsedDateRange
        The output from ``parse_datetime_expression()``.
    top_n : int
        Maximum number of results to return. Defaults to 5.

    Returns
    -------
    list of dict
        Each dict is the original slot dict augmented with:

        - ``match_score`` (float): numeric relevance score
        - ``match_reasons`` (list[str]): human-readable explanations
    """
    if not available_slots:
        return []

    constraints = parsed_preference.constraints if parsed_preference else []

    scored: List[Dict[str, Any]] = []
    for slot in available_slots:
        start_dt = _parse_iso(slot.get("start", ""))
        if start_dt is None:
            continue

        # Hard-filter by constraints
        if not _passes_constraints(start_dt, constraints):
            continue

        score = _score_slot(slot, parsed_preference)
        if score < 0:
            continue

        # Build match reasons
        reasons = _build_reasons(slot, parsed_preference)

        enriched = {**slot, "match_score": round(score, 1), "match_reasons": reasons}
        scored.append(enriched)

    # Sort descending by score, then ascending by start time for ties
    scored.sort(key=lambda s: (-s["match_score"], s.get("start", "")))

    return scored[:top_n]


def _build_reasons(slot: Dict[str, Any], parsed: ParsedDateRange) -> List[str]:
    """Build human-readable match reason strings."""
    reasons: List[str] = []
    start_dt = _parse_iso(slot.get("start", ""))
    if not start_dt:
        return reasons

    slot_date = start_dt.date()
    slot_time = start_dt.time()

    if parsed.dates and slot_date in parsed.dates:
        reasons.append("exact date match")
    elif parsed.dates:
        min_dist = min(_date_distance(slot_date, d) for d in parsed.dates)
        if min_dist <= 1:
            reasons.append("close to preferred date")

    if parsed.time_range:
        pref_start, pref_end = parsed.time_range
        if _time_in_range(slot_time, pref_start, pref_end):
            reasons.append("within preferred time window")
        elif _slot_overlaps_range(
            slot_time,
            _parse_iso(slot.get("end", "")).time() if _parse_iso(slot.get("end", "")) else slot_time,
            pref_start,
            pref_end,
        ):
            reasons.append("overlaps preferred time window")

    if not reasons:
        reasons.append("available slot")

    return reasons
