"""
Important Dates Service — Perennia AI

Helper layer on top of the ImportantDatesMixin that reads/writes milestone
dates on any loan/lead/client profile object. Used by:

- SLA tracking engine — compute days_since(milestone) for breach detection
- Workflow task engine — find the next due milestone
- Pipeline analyst agent — milestone audit reports

Business-hour math delegates to HolidayCalendar so that "days since"
correctly skips weekends/holidays and respects state-specific rules.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

from database.models.important_dates import (
    IMPORTANT_DATE_COLUMNS,
    utc_now,
)

logger = logging.getLogger(__name__)


# Canonical milestone order — for next-due computation.
MILESTONE_ORDER = [name for name, _idx in IMPORTANT_DATE_COLUMNS]


def _resolve_state(obj: Any) -> Optional[str]:
    """Extract a US state code from a loan/lead/client object, if available."""
    for attr in ("property_state", "state", "borrower_state"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and len(val) == 2:
            return val.upper()
    return None


def get_important_dates(loan_or_lead: Any) -> Dict[str, Optional[datetime]]:
    """Return {milestone_name: datetime|None} for every canonical milestone."""
    out: Dict[str, Optional[datetime]] = {}
    for name, _idx in IMPORTANT_DATE_COLUMNS:
        out[name] = getattr(loan_or_lead, name, None)
    return out


def set_milestone_date(
    loan_or_lead: Any,
    milestone_name: str,
    when: Optional[datetime] = None,
) -> datetime:
    """
    Write a milestone date. ``when=None`` writes now() in UTC.

    Raises:
        ValueError: if milestone_name is not a recognized canonical milestone.
    """
    if milestone_name not in MILESTONE_ORDER:
        raise ValueError(
            f"Unknown milestone '{milestone_name}'. "
            f"Valid: {', '.join(MILESTONE_ORDER)}"
        )
    if when is None:
        when = utc_now()
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    setattr(loan_or_lead, milestone_name, when)
    return when


def days_since_milestone(
    loan_or_lead: Any,
    milestone_name: str,
    now: Optional[datetime] = None,
    use_business_days: bool = True,
) -> Optional[int]:
    """
    Whole business days since ``milestone_name`` was hit. Returns None if the
    milestone date is not set on the object.

    Uses HolidayCalendar (state-aware) when ``use_business_days`` is True.
    """
    if milestone_name not in MILESTONE_ORDER:
        raise ValueError(f"Unknown milestone '{milestone_name}'")
    when: Optional[datetime] = getattr(loan_or_lead, milestone_name, None)
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if now is None:
        now = utc_now()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if not use_business_days:
        return max(0, (now.date() - when.date()).days)

    # Use HolidayCalendar for state-aware business-day math
    try:
        from services.holiday_calendar import HolidayCalendar  # local import to avoid cycles
        cal = HolidayCalendar()
        state = _resolve_state(loan_or_lead)
        return cal.business_days_between(when.date(), now.date(), state=state)
    except Exception as exc:
        logger.warning(
            "HolidayCalendar unavailable, falling back to calendar days: %s",
            exc,
        )
        return max(0, (now.date() - when.date()).days)


def get_next_due_milestone(
    loan_or_lead: Any,
    sla_config: Optional[Dict[str, int]] = None,
    now: Optional[datetime] = None,
) -> Optional[Tuple[str, datetime]]:
    """
    Find the next milestone that is due-but-unset.

    Args:
        loan_or_lead: object with milestone date attributes.
        sla_config: optional {milestone_name: max_business_days_from_prev}
            map. If supplied, only milestones whose *previous* date has
            existed for >= the configured window are considered "due".
            If not supplied, the first unset milestone after the last set
            milestone is returned with the last-set date as anchor.
        now: override current time for testing.

    Returns:
        (milestone_name, anchor_datetime) or None if pipeline complete.
    """
    if now is None:
        now = utc_now()
    sla_config = sla_config or {}

    last_set_name: Optional[str] = None
    last_set_dt: Optional[datetime] = None

    for name in MILESTONE_ORDER:
        val = getattr(loan_or_lead, name, None)
        if val is not None:
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            last_set_name = name
            last_set_dt = val
            continue
        # First unset milestone after a set one — this is "next due"
        anchor = last_set_dt or now
        # If an SLA window is configured for this milestone, respect it
        window_days = sla_config.get(name)
        if window_days is not None and last_set_dt is not None:
            try:
                from services.holiday_calendar import HolidayCalendar
                cal = HolidayCalendar()
                state = _resolve_state(loan_or_lead)
                elapsed = cal.business_days_between(
                    last_set_dt.date(), now.date(), state=state
                )
                if elapsed < window_days:
                    # Not yet due — skip to the next unset milestone
                    continue
            except Exception:
                pass
        return name, anchor

    return None


__all__ = [
    "get_important_dates",
    "set_milestone_date",
    "days_since_milestone",
    "get_next_due_milestone",
    "MILESTONE_ORDER",
]
