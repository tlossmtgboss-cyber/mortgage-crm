"""
Aria Trend Analysis Tools
==========================
Utility helpers used by trend analysis agents.  These are intentionally
thin wrappers so they can be unit-tested without a live database session.

Public helpers (imported by tests and other modules)
-----------------------------------------------------
- _get_period_dates(time_window)  -> (start, end, prior_start, prior_end)
- _make_insight(domain, metric, label, current, prior, higher_is_better, unit) -> dict
- _owner_filter(scope, user_id, col) -> (sql_fragment, params)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_WINDOW_DAYS: Dict[str, int] = {
    "week": 7,
    "month": 30,
    "quarter": 90,
}


def _get_period_dates(time_window: str) -> Tuple[str, str, str, str]:
    """
    Return (start, end, prior_start, prior_end) as YYYY-MM-DD strings.

    ``end`` is today.  ``start`` is ``end - window_days``.
    The prior period covers the same length immediately before start.
    """
    days = _WINDOW_DAYS.get(time_window, 30)
    now = datetime.now()
    end = now
    start = now - timedelta(days=days)
    prior_end = start
    prior_start = start - timedelta(days=days)
    fmt = "%Y-%m-%d"
    return (
        start.strftime(fmt),
        end.strftime(fmt),
        prior_start.strftime(fmt),
        prior_end.strftime(fmt),
    )


# ---------------------------------------------------------------------------
# Insight builder
# ---------------------------------------------------------------------------

_FLAT_THRESHOLD = 2.0  # delta_pct below which direction is "flat"


def _make_insight(
    domain: str,
    metric: str,
    label: str,
    current_value: float,
    prior_value: float,
    higher_is_better: bool,
    unit: str = "count",
    context: str = "",
) -> Dict[str, Any]:
    """
    Build a normalised insight dict from raw current/prior values.

    ``higher_is_better`` controls whether an upward move is positive.
    """
    if prior_value == 0:
        delta_pct = 100.0 if current_value > 0 else 0.0
    else:
        delta_pct = ((current_value - prior_value) / abs(prior_value)) * 100.0

    abs_delta = abs(delta_pct)

    if abs_delta < _FLAT_THRESHOLD:
        direction = "flat"
        is_positive = True  # neutral
    elif current_value > prior_value:
        direction = "up"
        is_positive = higher_is_better
    else:
        direction = "down"
        is_positive = not higher_is_better

    return {
        "domain": domain,
        "metric": metric,
        "label": label,
        "current_value": current_value,
        "prior_value": prior_value,
        "delta_pct": round(delta_pct, 2),
        "direction": direction,
        "significance": round(abs_delta, 2),
        "context": context,
        "is_positive": is_positive,
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# Scope / owner filter
# ---------------------------------------------------------------------------


def _owner_filter(
    scope: str,
    user_id: int,
    col: str = "owner_id",
) -> Tuple[str, Dict[str, Any]]:
    """
    Return a (sql_fragment, params) pair for filtering rows by owner.

    scope="admin"  → no filter (see all records).
    scope="sales"  → filter to the given user_id.
    """
    if scope == "admin":
        return ("", {})
    return (f"{col} = :scope_user_id", {"scope_user_id": user_id})
