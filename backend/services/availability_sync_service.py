"""
Availability Sync Service

Provides diagnostic and synchronization utilities for the dual availability
data sources: RecurringAvailability table rows and SchedulerConfig.working_hours
JSON blob.

Problem
~~~~~~~
The slot generator (_helpers._generate_available_slots) checks RecurringAvailability
rows FIRST, falling back to SchedulerConfig.working_hours JSON only when no rows
exist. The Settings UI writes to the JSON blob. Once RecurringAvailability rows
exist for a user, Settings UI changes are silently ignored by the slot generator.

This module provides:
- ``check_availability_divergence`` -- detect when the two sources contain
  different availability data
- ``sync_working_hours_to_recurring`` -- propagate JSON blob -> RecurringAvailability
- ``sync_recurring_to_working_hours`` -- propagate RecurringAvailability -> JSON blob
- ``get_availability_source`` -- report which source is active and whether divergence
  exists

These functions are designed to be called from settings endpoints, admin tools,
or migration scripts. They operate within the caller's existing DB session and
do NOT commit -- the caller is responsible for transaction management.

Data Format Reference
~~~~~~~~~~~~~~~~~~~~~
working_hours JSON (on SchedulerConfig):
    {
        "monday":    {"start": "09:00", "end": "17:00", "enabled": true},
        "tuesday":   {"start": "09:00", "end": "17:00", "enabled": true},
        ...
        "saturday":  {"start": "10:00", "end": "14:00", "enabled": false},
        "sunday":    {"start": "10:00", "end": "14:00", "enabled": false}
    }

RecurringAvailability rows:
    Each row has: user_id, organization_id, day_of_week (0=Mon .. 6=Sun),
    start_time (Time), end_time (Time), is_active (bool), timezone (str).
    Multiple rows per day are supported (e.g. morning + afternoon blocks).
"""

import logging
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)


# ============================================================================
# DAY-OF-WEEK MAPPINGS
# ============================================================================

# ISO day-of-week (0=Monday) <-> day name used by working_hours JSON
_DOW_TO_NAME: Dict[int, str] = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

_NAME_TO_DOW: Dict[str, int] = {v: k for k, v in _DOW_TO_NAME.items()}

# All 7 day-of-week indices
_ALL_DOWS = list(range(7))


# ============================================================================
# LAZY MODEL IMPORTS
# ============================================================================

def _get_recurring_model():
    """Lazy import of RecurringAvailability to avoid circular imports."""
    from database.models.recurring_availability import RecurringAvailability
    return RecurringAvailability


def _get_scheduler_config_model():
    """Lazy import of SchedulerConfig to avoid circular imports."""
    from database.models.scheduler import SchedulerConfig
    return SchedulerConfig


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _parse_time(time_str: str) -> Optional[dt_time]:
    """Parse an HH:MM string to a datetime.time object. Returns None on failure."""
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except (ValueError, TypeError):
        logger.warning(f"Invalid time format: {time_str!r}")
        return None


def _format_time(t: Optional[dt_time]) -> Optional[str]:
    """Format a datetime.time as HH:MM. Returns None if input is None."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def _get_config(db: Session, user_id: int, org_id: int):
    """Fetch the SchedulerConfig for a user. Returns None if not found."""
    SchedulerConfig = _get_scheduler_config_model()
    return (
        db.query(SchedulerConfig)
        .filter(
            SchedulerConfig.user_id == user_id,
            SchedulerConfig.organization_id == org_id,
        )
        .first()
    )


def _get_active_recurring_rows(db: Session, user_id: int, org_id: int) -> list:
    """Fetch all active RecurringAvailability rows for a user, ordered by day + time."""
    RecurringAvailability = _get_recurring_model()
    return (
        db.query(RecurringAvailability)
        .filter(
            RecurringAvailability.user_id == user_id,
            RecurringAvailability.organization_id == org_id,
            RecurringAvailability.is_active == True,  # noqa: E712
        )
        .order_by(
            RecurringAvailability.day_of_week,
            RecurringAvailability.start_time,
        )
        .all()
    )


def _recurring_rows_to_schedule_dict(
    rows: list,
) -> Dict[int, List[Dict[str, str]]]:
    """
    Convert RecurringAvailability ORM rows to a schedule dict.

    Returns: {day_of_week_int: [{"start": "HH:MM", "end": "HH:MM"}, ...], ...}
    Only includes days that have at least one active block.
    """
    schedule: Dict[int, List[Dict[str, str]]] = {}
    for row in rows:
        dow = row.day_of_week
        start_str = _format_time(row.start_time)
        end_str = _format_time(row.end_time)
        if start_str and end_str:
            schedule.setdefault(dow, []).append({
                "start": start_str,
                "end": end_str,
            })
    return schedule


def _working_hours_to_schedule_dict(
    working_hours: Dict[str, Any],
) -> Dict[int, List[Dict[str, str]]]:
    """
    Convert a working_hours JSON blob to a schedule dict.

    The JSON format uses day names as keys:
        {"monday": {"start": "09:00", "end": "17:00", "enabled": true}, ...}

    Returns: {day_of_week_int: [{"start": "HH:MM", "end": "HH:MM"}], ...}
    Only includes days that are enabled.
    """
    schedule: Dict[int, List[Dict[str, str]]] = {}
    if not working_hours or not isinstance(working_hours, dict):
        return schedule

    for day_name, day_config in working_hours.items():
        day_name_lower = day_name.lower()
        dow = _NAME_TO_DOW.get(day_name_lower)
        if dow is None:
            continue
        if not isinstance(day_config, dict):
            continue
        if not day_config.get("enabled", False):
            continue

        start_str = day_config.get("start")
        end_str = day_config.get("end")
        if start_str and end_str:
            schedule[dow] = [{"start": start_str, "end": end_str}]

    return schedule


def _schedule_dict_to_working_hours(
    schedule: Dict[int, List[Dict[str, str]]],
) -> Dict[str, Dict[str, Any]]:
    """
    Convert a schedule dict to working_hours JSON format.

    Because the JSON blob only supports a SINGLE start/end per day (no
    multi-block), we approximate multi-block days by using the earliest
    start and latest end across all blocks. Days with no blocks are marked
    enabled=false with default times.

    Returns: {"monday": {"start": "09:00", "end": "17:00", "enabled": true}, ...}
    """
    working_hours: Dict[str, Dict[str, Any]] = {}

    for dow in _ALL_DOWS:
        day_name = _DOW_TO_NAME[dow]
        blocks = schedule.get(dow, [])

        if blocks:
            starts = [b["start"] for b in blocks]
            ends = [b["end"] for b in blocks]
            working_hours[day_name] = {
                "start": min(starts),
                "end": max(ends),
                "enabled": True,
            }
        else:
            # No blocks -- disabled day with default placeholder times
            working_hours[day_name] = {
                "start": "09:00",
                "end": "17:00",
                "enabled": False,
            }

    return working_hours


def _schedules_are_equivalent(
    sched_a: Dict[int, List[Dict[str, str]]],
    sched_b: Dict[int, List[Dict[str, str]]],
) -> bool:
    """
    Compare two schedule dicts for semantic equivalence.

    Two schedules are equivalent if every day has the same set of time
    blocks (same start/end pairs, in sorted order). Days absent from
    a dict are treated as having zero blocks (disabled).
    """
    for dow in _ALL_DOWS:
        blocks_a = sorted(sched_a.get(dow, []), key=lambda b: b["start"])
        blocks_b = sorted(sched_b.get(dow, []), key=lambda b: b["start"])

        if len(blocks_a) != len(blocks_b):
            return False

        for ba, bb in zip(blocks_a, blocks_b):
            if ba.get("start") != bb.get("start") or ba.get("end") != bb.get("end"):
                return False

    return True


def _describe_divergence(
    json_sched: Dict[int, List[Dict[str, str]]],
    recurring_sched: Dict[int, List[Dict[str, str]]],
) -> List[Dict[str, Any]]:
    """
    Build a human-readable list of per-day differences between two schedules.

    Returns: [{"day": "monday", "day_of_week": 0,
               "json_blocks": [...], "recurring_blocks": [...]}, ...]
    Only includes days with differences.
    """
    differences = []

    for dow in _ALL_DOWS:
        blocks_json = sorted(json_sched.get(dow, []), key=lambda b: b["start"])
        blocks_recur = sorted(recurring_sched.get(dow, []), key=lambda b: b["start"])

        if blocks_json == blocks_recur:
            continue

        differences.append({
            "day": _DOW_TO_NAME[dow],
            "day_of_week": dow,
            "json_blocks": blocks_json,
            "recurring_blocks": blocks_recur,
        })

    return differences


# ============================================================================
# PUBLIC API
# ============================================================================

def get_availability_source(
    db: Session,
    user_id: int,
    org_id: int,
) -> Dict[str, Any]:
    """
    Determine which availability source is active for the slot generator
    and whether the two sources have diverged.

    Returns a dict with:
        - source: "recurring" | "json" | "none"
            "recurring" = RecurringAvailability rows exist and will be used
            "json" = no recurring rows; JSON blob will be used as fallback
            "none" = neither source has data
        - has_recurring: bool
        - has_json: bool
        - diverged: bool (True if both sources exist with different data)
        - differences: list of per-day differences (only if diverged)
        - recurring_block_count: int
        - json_day_count: int (number of enabled days in JSON)
    """
    config = _get_config(db, user_id, org_id)
    recurring_rows = _get_active_recurring_rows(db, user_id, org_id)

    has_recurring = len(recurring_rows) > 0
    working_hours = config.working_hours if config else None
    has_json = bool(
        working_hours
        and isinstance(working_hours, dict)
        and any(
            isinstance(v, dict) and v.get("enabled", False)
            for v in working_hours.values()
        )
    )

    # Determine active source (mirrors _generate_available_slots logic)
    if has_recurring:
        source = "recurring"
    elif has_json:
        source = "json"
    else:
        source = "none"

    # Check divergence
    diverged = False
    differences: List[Dict[str, Any]] = []

    if has_recurring and has_json:
        recurring_sched = _recurring_rows_to_schedule_dict(recurring_rows)
        json_sched = _working_hours_to_schedule_dict(working_hours)

        if not _schedules_are_equivalent(json_sched, recurring_sched):
            diverged = True
            differences = _describe_divergence(json_sched, recurring_sched)

    # Count enabled days in JSON
    json_day_count = 0
    if has_json:
        json_day_count = sum(
            1 for v in working_hours.values()
            if isinstance(v, dict) and v.get("enabled", False)
        )

    return {
        "source": source,
        "has_recurring": has_recurring,
        "has_json": has_json,
        "diverged": diverged,
        "differences": differences,
        "recurring_block_count": len(recurring_rows),
        "json_day_count": json_day_count,
    }


def check_availability_divergence(
    db: Session,
    user_id: int,
    org_id: int,
) -> bool:
    """
    Quick check: do both availability sources exist with different data?

    Returns True if RecurringAvailability rows AND working_hours JSON both
    exist and contain different availability information. This means the
    Settings UI is showing stale data that does not match what the slot
    generator actually uses.

    Returns False if:
    - Only one source exists (no conflict possible)
    - Both sources exist but contain equivalent data
    - Neither source exists
    """
    config = _get_config(db, user_id, org_id)
    recurring_rows = _get_active_recurring_rows(db, user_id, org_id)

    if not recurring_rows:
        return False

    working_hours = config.working_hours if config else None
    if not working_hours or not isinstance(working_hours, dict):
        return False

    # Check if any day is actually enabled in the JSON
    has_enabled = any(
        isinstance(v, dict) and v.get("enabled", False)
        for v in working_hours.values()
    )
    if not has_enabled:
        return False

    recurring_sched = _recurring_rows_to_schedule_dict(recurring_rows)
    json_sched = _working_hours_to_schedule_dict(working_hours)

    return not _schedules_are_equivalent(json_sched, recurring_sched)


def sync_working_hours_to_recurring(
    db: Session,
    user_id: int,
    org_id: int,
    timezone_str: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    """
    Sync: SchedulerConfig.working_hours JSON -> RecurringAvailability rows.

    Reads the working_hours JSON blob from SchedulerConfig, deactivates all
    existing RecurringAvailability rows for the user, and creates new rows
    matching the JSON blob.

    This is the "Settings UI wins" direction: use when the user explicitly
    saves availability through the Settings UI and you want the structured
    table to match.

    Edge cases:
    - No SchedulerConfig exists: returns early with no changes.
    - working_hours is empty/null: deactivates all existing recurring rows.
    - A day is enabled but has invalid times: skips that day with a warning.

    Does NOT commit. The caller manages the transaction.

    Args:
        db: SQLAlchemy session.
        user_id: User whose availability to sync.
        org_id: Organization ID for tenant isolation.
        timezone_str: Timezone for new RecurringAvailability rows.

    Returns:
        Summary dict with counts of created, deactivated, and skipped days.
    """
    RecurringAvailability = _get_recurring_model()

    config = _get_config(db, user_id, org_id)
    if not config:
        logger.debug(
            f"sync_working_hours_to_recurring: no SchedulerConfig for "
            f"user {user_id}, org {org_id}"
        )
        return {"created": 0, "deactivated": 0, "skipped": 0, "source": "no_config"}

    working_hours = config.working_hours
    if not working_hours or not isinstance(working_hours, dict):
        # No JSON data -- deactivate all existing recurring rows
        deactivated = (
            db.query(RecurringAvailability)
            .filter(
                RecurringAvailability.user_id == user_id,
                RecurringAvailability.organization_id == org_id,
                RecurringAvailability.is_active == True,  # noqa: E712
            )
            .update({"is_active": False}, synchronize_session="fetch")
        )
        db.flush()
        return {
            "created": 0,
            "deactivated": deactivated,
            "skipped": 0,
            "source": "empty_json",
        }

    # Use the timezone from the config if available
    tz = config.timezone or timezone_str

    # Deactivate all existing active rows
    deactivated = (
        db.query(RecurringAvailability)
        .filter(
            RecurringAvailability.user_id == user_id,
            RecurringAvailability.organization_id == org_id,
            RecurringAvailability.is_active == True,  # noqa: E712
        )
        .update({"is_active": False}, synchronize_session="fetch")
    )

    created = 0
    skipped = 0

    for day_name, day_config in working_hours.items():
        day_name_lower = day_name.lower()
        dow = _NAME_TO_DOW.get(day_name_lower)
        if dow is None:
            continue

        if not isinstance(day_config, dict):
            skipped += 1
            continue

        if not day_config.get("enabled", False):
            # Day is disabled -- no row needed (already deactivated above)
            continue

        start_str = day_config.get("start")
        end_str = day_config.get("end")

        if not start_str or not end_str:
            logger.warning(
                f"sync_working_hours_to_recurring: {day_name_lower} enabled but "
                f"missing start/end for user {user_id}, skipping"
            )
            skipped += 1
            continue

        start_time = _parse_time(start_str)
        end_time = _parse_time(end_str)

        if start_time is None or end_time is None:
            logger.warning(
                f"sync_working_hours_to_recurring: invalid time format for "
                f"{day_name_lower} (start={start_str!r}, end={end_str!r}) "
                f"for user {user_id}, skipping"
            )
            skipped += 1
            continue

        if start_time >= end_time:
            logger.warning(
                f"sync_working_hours_to_recurring: start >= end for "
                f"{day_name_lower} ({start_str} >= {end_str}) "
                f"for user {user_id}, skipping"
            )
            skipped += 1
            continue

        new_row = RecurringAvailability(
            user_id=user_id,
            organization_id=org_id,
            day_of_week=dow,
            start_time=start_time,
            end_time=end_time,
            is_active=True,
            timezone=tz,
        )
        db.add(new_row)
        created += 1

    db.flush()

    logger.info(
        f"sync_working_hours_to_recurring for user {user_id}: "
        f"created={created}, deactivated={deactivated}, skipped={skipped}"
    )

    return {
        "created": created,
        "deactivated": deactivated,
        "skipped": skipped,
        "source": "json_to_recurring",
    }


def sync_recurring_to_working_hours(
    db: Session,
    user_id: int,
    org_id: int,
) -> Dict[str, Any]:
    """
    Sync: RecurringAvailability rows -> SchedulerConfig.working_hours JSON.

    Reads the active RecurringAvailability rows and writes an equivalent
    working_hours JSON blob to SchedulerConfig.

    This is the "Recurring table wins" direction: use when the user has
    updated their schedule via the recurring availability endpoints and
    you want the JSON blob (and thus the Settings UI display) to match.

    Because the JSON blob only supports a SINGLE start/end per day,
    multi-block days are approximated by using the earliest start and
    latest end. This is a known limitation documented in the migration plan.

    Edge cases:
    - No SchedulerConfig exists: returns early with no changes.
    - No recurring rows exist: sets all days to enabled=false in JSON.

    Does NOT commit. The caller manages the transaction.

    Args:
        db: SQLAlchemy session.
        user_id: User whose availability to sync.
        org_id: Organization ID for tenant isolation.

    Returns:
        Summary dict with the new working_hours and metadata.
    """
    config = _get_config(db, user_id, org_id)
    if not config:
        logger.debug(
            f"sync_recurring_to_working_hours: no SchedulerConfig for "
            f"user {user_id}, org {org_id}"
        )
        return {
            "updated": False,
            "reason": "no_config",
            "working_hours": None,
        }

    recurring_rows = _get_active_recurring_rows(db, user_id, org_id)
    recurring_sched = _recurring_rows_to_schedule_dict(recurring_rows)
    new_working_hours = _schedule_dict_to_working_hours(recurring_sched)

    # Check if anything actually changed
    old_json_sched = _working_hours_to_schedule_dict(config.working_hours or {})
    already_in_sync = _schedules_are_equivalent(
        old_json_sched, recurring_sched
    )

    if already_in_sync:
        logger.debug(
            f"sync_recurring_to_working_hours for user {user_id}: already in sync"
        )
        return {
            "updated": False,
            "reason": "already_in_sync",
            "working_hours": new_working_hours,
        }

    config.working_hours = new_working_hours
    db.flush()

    # Count multi-block days that lost fidelity in the conversion
    multi_block_days = [
        _DOW_TO_NAME[dow]
        for dow, blocks in recurring_sched.items()
        if len(blocks) > 1
    ]

    logger.info(
        f"sync_recurring_to_working_hours for user {user_id}: "
        f"updated JSON blob, {len(recurring_rows)} rows -> 7 day entries"
        + (f", multi-block approximation on: {multi_block_days}" if multi_block_days else "")
    )

    return {
        "updated": True,
        "reason": "synced",
        "working_hours": new_working_hours,
        "recurring_block_count": len(recurring_rows),
        "multi_block_days": multi_block_days,
    }
