"""
CalendarRulesEngine -- Centralized scheduling rule enforcement.

All scheduling rules are defined and enforced in ONE place.
No more scattered business logic across routes, services, and models.

Rules:
1. Business hours (per-LO configurable, default 9:00-17:00)
2. Buffer time between appointments (configurable, default 15 min)
3. Lunch break blocking (configurable, default 12:00-13:00)
4. Daily capacity limits (max appointments per day)
5. Weekly capacity limits (max appointments per week)
6. Minimum booking notice (can't book same-day, configurable)
7. Maximum advance booking (can't book > 60 days out, configurable)
8. Appointment duration rules (min 15, max 120, increments of 15)
9. Blocked dates (holidays, PTO, custom)
10. Priority scheduling (VIP clients can override some rules)

Usage:
    from services.calendar_rules_engine import (
        validate_booking_request,
        is_bookable,
        get_next_available,
        get_rules_for_lo,
    )

    rules = await get_rules_for_lo(lo_id, db)
    bookable, violations = await is_bookable(lo_id, start, end, rules, db)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Day-of-week index mapping (Python weekday: Monday=0 ... Sunday=6)
_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_DEFAULT_WORKING_HOURS: Dict[str, Dict[str, Any]] = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
}


# =============================================================================
# MODELS
# =============================================================================

class RuleViolationType(str, Enum):
    OUTSIDE_BUSINESS_HOURS = "outside_business_hours"
    BUFFER_CONFLICT = "buffer_conflict"
    LUNCH_BREAK = "lunch_break"
    DAILY_CAPACITY_EXCEEDED = "daily_capacity_exceeded"
    WEEKLY_CAPACITY_EXCEEDED = "weekly_capacity_exceeded"
    INSUFFICIENT_NOTICE = "insufficient_notice"
    TOO_FAR_ADVANCE = "too_far_advance"
    INVALID_DURATION = "invalid_duration"
    BLOCKED_DATE = "blocked_date"
    TIME_CONFLICT = "time_conflict"
    NON_WORKING_DAY = "non_working_day"


class RuleViolation(BaseModel):
    """A single scheduling rule violation."""
    rule: RuleViolationType
    message: str
    severity: str = "error"  # "error" = hard block, "warning" = soft/overridable
    details: Dict[str, Any] = Field(default_factory=dict)
    overridable: bool = False


class DaySchedule(BaseModel):
    """Working hours for a single day of the week."""
    start: str = "09:00"  # HH:MM format
    end: str = "17:00"
    enabled: bool = True

    @validator("start", "end")
    def validate_time_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError(f"Invalid time format: '{v}'. Expected HH:MM.")
        return v


class SchedulingRules(BaseModel):
    """
    Complete scheduling rules configuration.

    This is the single source of truth for all scheduling constraints.
    Rules can be set at the org level (defaults) or per-LO (overrides).
    """
    # Business hours per day of week
    working_hours: Dict[str, DaySchedule] = Field(
        default_factory=lambda: {
            day: DaySchedule() if day not in ("saturday", "sunday")
            else DaySchedule(start="10:00", end="14:00", enabled=False)
            for day in _DAY_NAMES
        }
    )

    # Buffer time between appointments (minutes)
    buffer_before_minutes: int = Field(default=15, ge=0, le=60)
    buffer_after_minutes: int = Field(default=15, ge=0, le=60)

    # Lunch break
    lunch_break_start: str = Field(default="12:00")
    lunch_break_end: str = Field(default="13:00")
    enforce_lunch_break: bool = True

    # Capacity limits
    max_appointments_per_day: int = Field(default=8, ge=1, le=50)
    max_appointments_per_week: int = Field(default=40, ge=1, le=200)

    # Booking window
    min_notice_hours: int = Field(default=2, ge=0, le=168)  # 0 = allow immediate booking
    max_advance_days: int = Field(default=60, ge=1, le=365)

    # Duration rules
    min_duration_minutes: int = Field(default=15, ge=5, le=60)
    max_duration_minutes: int = Field(default=120, ge=15, le=480)
    duration_increment_minutes: int = Field(default=15, ge=5, le=60)
    default_duration_minutes: int = Field(default=30, ge=15, le=120)

    # VIP / priority override
    vip_can_override_notice: bool = False
    vip_can_override_capacity: bool = False
    vip_extended_hours_minutes: int = Field(default=0, ge=0, le=120)

    # Timezone
    timezone: str = DEFAULT_TIMEZONE

    # Source metadata (not a rule, just tracking)
    source: str = "defaults"  # "defaults", "org", "lo"
    lo_id: Optional[int] = None
    org_id: Optional[int] = None

    @validator("lunch_break_start", "lunch_break_end")
    def validate_lunch_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError(f"Invalid time format: '{v}'. Expected HH:MM.")
        return v

    @validator("default_duration_minutes")
    def validate_default_in_range(cls, v: int, values: dict) -> int:
        mn = values.get("min_duration_minutes", 15)
        mx = values.get("max_duration_minutes", 120)
        if v < mn or v > mx:
            raise ValueError(f"default_duration_minutes ({v}) must be between min ({mn}) and max ({mx})")
        return v

    def get_lunch_start_time(self) -> time:
        return datetime.strptime(self.lunch_break_start, "%H:%M").time()

    def get_lunch_end_time(self) -> time:
        return datetime.strptime(self.lunch_break_end, "%H:%M").time()


# =============================================================================
# RULE LOADING
# =============================================================================

async def get_rules_for_lo(
    lo_id: Optional[int],
    db: Session,
    org_id: Optional[int] = None,
) -> SchedulingRules:
    """
    Load scheduling rules for a specific loan officer.

    Resolution order:
    1. LO-specific config from scheduler_configs (user_id = lo_id)
    2. Org-level config from scheduler_configs (user_id IS NULL, organization_id = org_id)
    3. Fall back to hardcoded defaults

    Also checks scheduler_resources for capacity overrides.
    """
    config_row = None

    # DATA-013: Warn when org_id is missing — rules will fall back to defaults
    # without tenant scoping, which may return overly permissive scheduling rules.
    if org_id is None:
        logger.warning(
            "get_rules_for_lo called without org_id for lo_id=%s — "
            "rules will fall back to defaults without org-level scoping",
            lo_id,
        )

    # Try LO-specific config first
    if lo_id:
        try:
            query = (
                "SELECT * FROM scheduler_configs "
                "WHERE user_id = :user_id AND is_active = true"
            )
            params: Dict[str, Any] = {"user_id": lo_id}
            if org_id:
                query += " AND organization_id = :org_id"
                params["org_id"] = org_id
            query += " LIMIT 1"
            config_row = db.execute(text(query), params).mappings().first()
        except Exception as e:
            logger.debug(f"Could not query LO scheduler_configs: {e}")

    # Fall back to org-level config
    if not config_row and org_id:
        try:
            config_row = db.execute(text(
                "SELECT * FROM scheduler_configs "
                "WHERE user_id IS NULL AND organization_id = :org_id AND is_active = true "
                "LIMIT 1"
            ), {"org_id": org_id}).mappings().first()
        except Exception as e:
            logger.debug(f"Could not query org scheduler_configs: {e}")

    rules = _build_rules_from_config(config_row, lo_id=lo_id, org_id=org_id)

    # Check scheduler_resources for daily capacity override
    if lo_id and org_id:
        try:
            resource_row = db.execute(text(
                "SELECT max_daily_appointments FROM scheduler_resources "
                "WHERE user_id = :uid AND organization_id = :org_id AND status = 'active' "
                "LIMIT 1"
            ), {"uid": lo_id, "org_id": org_id}).mappings().first()
            if resource_row and resource_row["max_daily_appointments"]:
                rules.max_appointments_per_day = resource_row["max_daily_appointments"]
        except Exception as e:
            logger.debug(f"Could not query scheduler_resources: {e}")

    return rules


async def get_org_default_rules(
    org_id: int,
    db: Session,
) -> SchedulingRules:
    """Load org-level default scheduling rules (no LO override)."""
    config_row = None
    try:
        config_row = db.execute(text(
            "SELECT * FROM scheduler_configs "
            "WHERE user_id IS NULL AND organization_id = :org_id AND is_active = true "
            "LIMIT 1"
        ), {"org_id": org_id}).mappings().first()
    except Exception as e:
        logger.debug(f"Could not query org scheduler_configs: {e}")

    return _build_rules_from_config(config_row, org_id=org_id)


def _build_rules_from_config(
    config_row: Optional[Any],
    lo_id: Optional[int] = None,
    org_id: Optional[int] = None,
) -> SchedulingRules:
    """Build SchedulingRules from a scheduler_configs DB row."""
    if not config_row:
        return SchedulingRules(
            source="defaults",
            lo_id=lo_id,
            org_id=org_id,
        )

    # Parse working hours from JSON column
    raw_hours = config_row.get("working_hours") if hasattr(config_row, "get") else getattr(config_row, "working_hours", None)
    working_hours: Dict[str, DaySchedule] = {}
    if raw_hours and isinstance(raw_hours, dict):
        for day_name in _DAY_NAMES:
            day_data = raw_hours.get(day_name, {})
            working_hours[day_name] = DaySchedule(
                start=day_data.get("start", "09:00"),
                end=day_data.get("end", "17:00"),
                enabled=day_data.get("enabled", day_name not in ("saturday", "sunday")),
            )
    else:
        for day_name in _DAY_NAMES:
            working_hours[day_name] = DaySchedule(
                enabled=day_name not in ("saturday", "sunday"),
            )

    def _get(field: str, default: Any) -> Any:
        if hasattr(config_row, "get"):
            val = config_row.get(field)
        else:
            val = getattr(config_row, field, None)
        return val if val is not None else default

    # Parse lunch break times from Time objects or strings
    lunch_start_raw = _get("lunch_break_start", time(12, 0))
    lunch_end_raw = _get("lunch_break_end", time(13, 0))

    if isinstance(lunch_start_raw, time):
        lunch_start_str = lunch_start_raw.strftime("%H:%M")
    elif isinstance(lunch_start_raw, str):
        lunch_start_str = lunch_start_raw
    else:
        lunch_start_str = "12:00"

    if isinstance(lunch_end_raw, time):
        lunch_end_str = lunch_end_raw.strftime("%H:%M")
    elif isinstance(lunch_end_raw, str):
        lunch_end_str = lunch_end_raw
    else:
        lunch_end_str = "13:00"

    source = "lo" if lo_id and _get("user_id", None) else "org"

    return SchedulingRules(
        working_hours=working_hours,
        buffer_before_minutes=_get("buffer_before_minutes", 15),
        buffer_after_minutes=_get("buffer_after_minutes", 15),
        lunch_break_start=lunch_start_str,
        lunch_break_end=lunch_end_str,
        enforce_lunch_break=_get("enforce_lunch_break", True),
        max_appointments_per_day=_get("max_meetings_per_day", 8),
        max_appointments_per_week=_get("max_appointments_per_week", None) or _get("max_meetings_per_day", 8) * 5,
        min_notice_hours=_get("min_notice_hours", 2),
        max_advance_days=_get("max_advance_days", 60),
        min_duration_minutes=_get("min_duration_minutes", 15),
        max_duration_minutes=_get("max_duration_minutes", 120),
        default_duration_minutes=_get("default_duration_minutes", 30),
        timezone=_get("timezone", DEFAULT_TIMEZONE),
        source=source,
        lo_id=lo_id,
        org_id=_get("organization_id", org_id),
    )


# =============================================================================
# RULE VALIDATION
# =============================================================================

def validate_booking_request(
    rules: SchedulingRules,
    proposed_start: datetime,
    duration_minutes: int,
    is_vip: bool = False,
) -> List[RuleViolation]:
    """
    Validate a proposed booking time against all scheduling rules.

    This is a pure function that checks rules without DB access.
    For full validation including conflicts, use is_bookable().

    Returns a list of RuleViolation objects. Empty list = all rules pass.
    """
    violations: List[RuleViolation] = []
    proposed_end = proposed_start + timedelta(minutes=duration_minutes)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Rule 8: Duration constraints
    if duration_minutes < rules.min_duration_minutes:
        violations.append(RuleViolation(
            rule=RuleViolationType.INVALID_DURATION,
            message=f"Duration {duration_minutes}min is below minimum {rules.min_duration_minutes}min",
            details={"min": rules.min_duration_minutes, "requested": duration_minutes},
        ))
    if duration_minutes > rules.max_duration_minutes:
        violations.append(RuleViolation(
            rule=RuleViolationType.INVALID_DURATION,
            message=f"Duration {duration_minutes}min exceeds maximum {rules.max_duration_minutes}min",
            details={"max": rules.max_duration_minutes, "requested": duration_minutes},
        ))
    if duration_minutes % rules.duration_increment_minutes != 0:
        violations.append(RuleViolation(
            rule=RuleViolationType.INVALID_DURATION,
            message=f"Duration must be in {rules.duration_increment_minutes}-minute increments",
            severity="warning",
            details={"increment": rules.duration_increment_minutes, "requested": duration_minutes},
            overridable=True,
        ))

    # Rule 6: Minimum booking notice
    min_booking_time = now + timedelta(hours=rules.min_notice_hours)
    if proposed_start < min_booking_time:
        can_override = is_vip and rules.vip_can_override_notice
        violations.append(RuleViolation(
            rule=RuleViolationType.INSUFFICIENT_NOTICE,
            message=f"Booking requires at least {rules.min_notice_hours}h notice. "
                    f"Earliest bookable time: {min_booking_time.strftime('%Y-%m-%d %H:%M')}",
            severity="warning" if can_override else "error",
            details={
                "min_notice_hours": rules.min_notice_hours,
                "earliest_bookable": min_booking_time.isoformat(),
            },
            overridable=can_override,
        ))

    # Rule 7: Maximum advance booking
    max_booking_date = now + timedelta(days=rules.max_advance_days)
    if proposed_start > max_booking_date:
        violations.append(RuleViolation(
            rule=RuleViolationType.TOO_FAR_ADVANCE,
            message=f"Cannot book more than {rules.max_advance_days} days in advance",
            details={
                "max_advance_days": rules.max_advance_days,
                "latest_bookable": max_booking_date.isoformat(),
            },
        ))

    # Rule 1: Business hours
    day_name = _DAY_NAMES[proposed_start.weekday()]
    day_schedule = rules.working_hours.get(day_name)

    if not day_schedule or not day_schedule.enabled:
        violations.append(RuleViolation(
            rule=RuleViolationType.NON_WORKING_DAY,
            message=f"{day_name.capitalize()} is not a working day",
            details={"day": day_name},
        ))
    else:
        work_start = datetime.strptime(day_schedule.start, "%H:%M").time()
        work_end = datetime.strptime(day_schedule.end, "%H:%M").time()

        # Apply VIP extended hours
        if is_vip and rules.vip_extended_hours_minutes > 0:
            ext = timedelta(minutes=rules.vip_extended_hours_minutes)
            work_start_dt = datetime.combine(proposed_start.date(), work_start) - ext
            work_end_dt = datetime.combine(proposed_start.date(), work_end) + ext
            work_start = work_start_dt.time()
            work_end = work_end_dt.time()

        if proposed_start.time() < work_start or proposed_end.time() > work_end:
            violations.append(RuleViolation(
                rule=RuleViolationType.OUTSIDE_BUSINESS_HOURS,
                message=f"Outside business hours ({day_schedule.start}-{day_schedule.end})",
                details={
                    "business_start": day_schedule.start,
                    "business_end": day_schedule.end,
                    "proposed_start": proposed_start.strftime("%H:%M"),
                    "proposed_end": proposed_end.strftime("%H:%M"),
                },
            ))

    # Rule 3: Lunch break
    if rules.enforce_lunch_break:
        lunch_start = datetime.combine(proposed_start.date(), rules.get_lunch_start_time())
        lunch_end = datetime.combine(proposed_start.date(), rules.get_lunch_end_time())
        if proposed_start < lunch_end and proposed_end > lunch_start:
            violations.append(RuleViolation(
                rule=RuleViolationType.LUNCH_BREAK,
                message=f"Overlaps lunch break ({rules.lunch_break_start}-{rules.lunch_break_end})",
                details={
                    "lunch_start": rules.lunch_break_start,
                    "lunch_end": rules.lunch_break_end,
                },
            ))

    return violations


# =============================================================================
# SLOT FILTERING HELPERS
# =============================================================================

def apply_buffer_time(
    slots: List[Dict[str, Any]],
    buffer_minutes: int,
    existing_busy_blocks: List[Tuple[datetime, datetime]],
) -> List[Dict[str, Any]]:
    """
    Filter out slots that conflict with existing busy blocks after applying
    buffer time padding.

    Args:
        slots: List of slot dicts with "start" and "end" datetime keys
        buffer_minutes: Minutes of buffer to add before and after busy blocks
        existing_busy_blocks: List of (start, end) tuples for occupied time

    Returns:
        Filtered list of slots that respect buffer requirements
    """
    if not existing_busy_blocks or buffer_minutes == 0:
        return slots

    buffer = timedelta(minutes=buffer_minutes)
    filtered = []

    for slot in slots:
        slot_start = slot["start"] if isinstance(slot["start"], datetime) else datetime.fromisoformat(str(slot["start"]))
        slot_end = slot["end"] if isinstance(slot["end"], datetime) else datetime.fromisoformat(str(slot["end"]))

        has_conflict = False
        for busy_start, busy_end in existing_busy_blocks:
            buffered_start = busy_start - buffer
            buffered_end = busy_end + buffer
            if slot_start < buffered_end and slot_end > buffered_start:
                has_conflict = True
                break

        if not has_conflict:
            filtered.append(slot)

    return filtered


def apply_lunch_block(
    slots: List[Dict[str, Any]],
    lunch_start: time,
    lunch_end: time,
) -> List[Dict[str, Any]]:
    """
    Remove slots that overlap with the lunch break window.

    Args:
        slots: List of slot dicts with "start" and "end" datetime keys
        lunch_start: Lunch break start time
        lunch_end: Lunch break end time

    Returns:
        Filtered list of slots outside the lunch window
    """
    filtered = []
    for slot in slots:
        slot_start = slot["start"] if isinstance(slot["start"], datetime) else datetime.fromisoformat(str(slot["start"]))
        slot_end = slot["end"] if isinstance(slot["end"], datetime) else datetime.fromisoformat(str(slot["end"]))

        slot_date = slot_start.date()
        lunch_start_dt = datetime.combine(slot_date, lunch_start)
        lunch_end_dt = datetime.combine(slot_date, lunch_end)

        # Keep the slot if it does NOT overlap with lunch
        if not (slot_start < lunch_end_dt and slot_end > lunch_start_dt):
            filtered.append(slot)

    return filtered


# =============================================================================
# CAPACITY CHECKS (require DB)
# =============================================================================

async def check_capacity(
    lo_id: int,
    target_date: date,
    rules: SchedulingRules,
    db: Session,
) -> Tuple[bool, int]:
    """
    Check if LO has remaining appointment capacity for a given date.

    Returns:
        (has_capacity, remaining_slots) tuple
    """
    org_id = rules.org_id

    # Count existing appointments for the day
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    try:
        params: Dict[str, Any] = {"uid": lo_id, "start": day_start, "end_dt": day_end}
        query = (
            "SELECT COUNT(*) FROM scheduler_appointments "
            "WHERE assigned_user_id = :uid "
            "AND scheduled_start >= :start AND scheduled_start < :end_dt "
            "AND status IN ('booked', 'completed', 'tentative')"
        )
        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        daily_count = db.execute(text(query), params).scalar() or 0
    except Exception as e:
        logger.warning(f"Could not check daily capacity: {e}")
        daily_count = 0

    remaining = max(0, rules.max_appointments_per_day - daily_count)
    has_capacity = daily_count < rules.max_appointments_per_day

    return has_capacity, remaining


async def _check_weekly_capacity(
    lo_id: int,
    target_date: date,
    rules: SchedulingRules,
    db: Session,
) -> Tuple[bool, int]:
    """Check weekly appointment capacity."""
    org_id = rules.org_id

    # Find the Monday of the target week
    days_since_monday = target_date.weekday()
    week_start = datetime.combine(target_date - timedelta(days=days_since_monday), time.min)
    week_end = week_start + timedelta(days=7)

    try:
        params: Dict[str, Any] = {"uid": lo_id, "start": week_start, "end_dt": week_end}
        query = (
            "SELECT COUNT(*) FROM scheduler_appointments "
            "WHERE assigned_user_id = :uid "
            "AND scheduled_start >= :start AND scheduled_start < :end_dt "
            "AND status IN ('booked', 'completed', 'tentative')"
        )
        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        weekly_count = db.execute(text(query), params).scalar() or 0
    except Exception as e:
        logger.warning(f"Could not check weekly capacity: {e}")
        weekly_count = 0

    remaining = max(0, rules.max_appointments_per_week - weekly_count)
    has_capacity = weekly_count < rules.max_appointments_per_week

    return has_capacity, remaining


# =============================================================================
# BUSINESS HOURS
# =============================================================================

async def get_business_hours(
    lo_id: Optional[int],
    day_of_week: int,
    db: Session,
    org_id: Optional[int] = None,
) -> Tuple[time, time]:
    """
    Get business hours for a specific day of the week.

    Args:
        lo_id: Loan officer user ID (or None for org defaults)
        day_of_week: Python weekday integer (0=Monday ... 6=Sunday)
        db: Database session
        org_id: Organization ID

    Returns:
        (start_time, end_time) tuple. Returns (time(0,0), time(0,0)) if not a working day.
    """
    rules = await get_rules_for_lo(lo_id, db, org_id)
    day_name = _DAY_NAMES[day_of_week]
    day_schedule = rules.working_hours.get(day_name)

    if not day_schedule or not day_schedule.enabled:
        return time(0, 0), time(0, 0)

    start = datetime.strptime(day_schedule.start, "%H:%M").time()
    end = datetime.strptime(day_schedule.end, "%H:%M").time()
    return start, end


# =============================================================================
# BLOCKED DATES
# =============================================================================

async def get_blocked_dates(
    lo_id: int,
    start_date: date,
    end_date: date,
    db: Session,
    org_id: Optional[int] = None,
) -> List[date]:
    """
    Get all dates that are fully blocked for an LO within a date range.

    Checks the scheduler_blocked_times table for PTO, holidays, and custom blocks.
    Returns dates where all-day blocks exist.
    """
    blocked_dates: List[date] = []

    try:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        params: Dict[str, Any] = {
            "uid": lo_id,
            "start_dt": start_dt,
            "end_dt": end_dt,
        }
        query = (
            "SELECT start_datetime, end_datetime, all_day FROM scheduler_blocked_times "
            "WHERE is_active = true "
            "AND (user_id = :uid OR applies_to_all_users = true) "
            "AND start_datetime <= :end_dt AND end_datetime >= :start_dt"
        )
        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        rows = db.execute(text(query), params).fetchall()

        for row in rows:
            block_start = row[0]
            block_end = row[1]
            is_all_day = row[2]

            if is_all_day:
                # Add every date within the block range that overlaps our query range
                current = max(block_start.date() if isinstance(block_start, datetime) else block_start, start_date)
                block_end_date = block_end.date() if isinstance(block_end, datetime) else block_end
                while current <= min(block_end_date, end_date):
                    if current not in blocked_dates:
                        blocked_dates.append(current)
                    current += timedelta(days=1)
            else:
                # Non-all-day blocks: check if they span the full working day
                # (for simplicity, we just note the dates they touch)
                block_start_date = block_start.date() if isinstance(block_start, datetime) else block_start
                block_end_date = block_end.date() if isinstance(block_end, datetime) else block_end
                current = max(block_start_date, start_date)
                while current <= min(block_end_date, end_date):
                    if current not in blocked_dates:
                        blocked_dates.append(current)
                    current += timedelta(days=1)

    except Exception as e:
        logger.warning(f"Could not query blocked dates: {e}")

    return sorted(blocked_dates)


# =============================================================================
# CONFLICT DETECTION
# =============================================================================

def _get_busy_blocks(
    db: Session,
    lo_id: int,
    search_start: datetime,
    search_end: datetime,
    org_id: Optional[int] = None,
) -> List[Tuple[datetime, datetime]]:
    """
    Get all busy time blocks for an LO from all calendar sources.

    Sources checked:
    1. scheduler_appointments (canonical)
    2. calendar_events (manual entries)
    3. crm_calendar_events (Salesforce-synced)
    """
    conflicts: List[Tuple[datetime, datetime]] = []

    # Source 1: scheduler_appointments
    try:
        params: Dict[str, Any] = {
            "uid": lo_id,
            "start_dt": search_start,
            "end_dt": search_end,
        }
        query = (
            "SELECT scheduled_start, scheduled_end FROM scheduler_appointments "
            "WHERE assigned_user_id = :uid "
            "AND status IN ('booked', 'tentative', 'completed') "
            "AND scheduled_start <= :end_dt AND scheduled_end >= :start_dt"
        )
        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        rows = db.execute(text(query), params).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"scheduler_appointments conflict check failed: {e}")

    # Source 2: calendar_events (manual calendar entries)
    try:
        params2: Dict[str, Any] = {
            "uid": lo_id,
            "start_dt": search_start,
            "end_dt": search_end,
        }
        query2 = (
            "SELECT start_time, end_time FROM calendar_events "
            "WHERE user_id = :uid AND status != 'cancelled' "
            "AND start_time <= :end_dt AND end_time >= :start_dt"
        )
        if org_id:
            query2 += " AND organization_id = :org_id"
            params2["org_id"] = org_id

        rows = db.execute(text(query2), params2).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"calendar_events conflict check unavailable: {e}")

    # Source 3: crm_calendar_events (Salesforce-synced)
    try:
        params3: Dict[str, Any] = {
            "uid": lo_id,
            "start_dt": search_start,
            "end_dt": search_end,
        }
        query3 = (
            "SELECT start_at, end_at FROM crm_calendar_events "
            "WHERE owner_user_id = :uid AND status != 'canceled' "
            "AND start_at <= :end_dt AND end_at >= :start_dt"
        )
        if org_id:
            query3 += " AND organization_id = :org_id"
            params3["org_id"] = org_id

        rows = db.execute(text(query3), params3).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"crm_calendar_events conflict check unavailable: {e}")

    return conflicts


def _check_time_conflicts(
    proposed_start: datetime,
    proposed_end: datetime,
    busy_blocks: List[Tuple[datetime, datetime]],
    buffer_before: int,
    buffer_after: int,
) -> List[RuleViolation]:
    """Check for time conflicts with buffer applied around busy blocks."""
    violations: List[RuleViolation] = []

    for busy_start, busy_end in busy_blocks:
        buffered_start = busy_start - timedelta(minutes=buffer_before)
        buffered_end = busy_end + timedelta(minutes=buffer_after)

        if proposed_start < buffered_end and proposed_end > buffered_start:
            violations.append(RuleViolation(
                rule=RuleViolationType.TIME_CONFLICT,
                message=f"Conflicts with existing event ({busy_start.strftime('%H:%M')}-{busy_end.strftime('%H:%M')})",
                details={
                    "conflict_start": busy_start.isoformat(),
                    "conflict_end": busy_end.isoformat(),
                    "buffer_before": buffer_before,
                    "buffer_after": buffer_after,
                },
            ))
            break  # One conflict is enough

    return violations


# =============================================================================
# BLOCKED TIME CHECKS
# =============================================================================

def _check_blocked_times(
    db: Session,
    lo_id: int,
    proposed_start: datetime,
    proposed_end: datetime,
    org_id: Optional[int] = None,
) -> List[RuleViolation]:
    """Check if proposed time falls within a blocked period."""
    violations: List[RuleViolation] = []

    try:
        params: Dict[str, Any] = {
            "uid": lo_id,
            "start_dt": proposed_start,
            "end_dt": proposed_end,
        }
        query = (
            "SELECT id, title, block_type, start_datetime, end_datetime "
            "FROM scheduler_blocked_times "
            "WHERE is_active = true "
            "AND (user_id = :uid OR applies_to_all_users = true) "
            "AND start_datetime < :end_dt AND end_datetime > :start_dt"
        )
        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        rows = db.execute(text(query), params).fetchall()

        for row in rows:
            violations.append(RuleViolation(
                rule=RuleViolationType.BLOCKED_DATE,
                message=f"Blocked: {row[1]} ({row[2]})",
                details={
                    "block_id": row[0],
                    "block_title": row[1],
                    "block_type": row[2],
                    "block_start": row[3].isoformat() if row[3] else None,
                    "block_end": row[4].isoformat() if row[4] else None,
                },
            ))
            break  # One is enough
    except Exception as e:
        logger.debug(f"Could not check blocked times: {e}")

    return violations


# =============================================================================
# COMPOSITE VALIDATION (the main entry point for full booking validation)
# =============================================================================

async def is_bookable(
    lo_id: int,
    proposed_start: datetime,
    proposed_end: datetime,
    rules: SchedulingRules,
    db: Session,
    is_vip: bool = False,
) -> Tuple[bool, List[RuleViolation]]:
    """
    Full validation: check if a proposed timeslot is bookable for an LO.

    Combines:
    - Static rule validation (business hours, duration, notice, etc.)
    - Database checks (capacity, conflicts, blocked times)

    Returns:
        (is_valid, violations) tuple. is_valid is True only if zero
        non-overridable violations exist.
    """
    duration_minutes = int((proposed_end - proposed_start).total_seconds() / 60)
    all_violations: List[RuleViolation] = []

    # Static rule checks
    all_violations.extend(
        validate_booking_request(rules, proposed_start, duration_minutes, is_vip=is_vip)
    )

    # DB: Daily capacity check
    has_daily, remaining_daily = await check_capacity(lo_id, proposed_start.date(), rules, db)
    if not has_daily:
        can_override = is_vip and rules.vip_can_override_capacity
        all_violations.append(RuleViolation(
            rule=RuleViolationType.DAILY_CAPACITY_EXCEEDED,
            message=f"Daily appointment limit reached ({rules.max_appointments_per_day})",
            severity="warning" if can_override else "error",
            details={
                "max_daily": rules.max_appointments_per_day,
                "remaining": remaining_daily,
            },
            overridable=can_override,
        ))

    # DB: Weekly capacity check
    has_weekly, remaining_weekly = await _check_weekly_capacity(lo_id, proposed_start.date(), rules, db)
    if not has_weekly:
        all_violations.append(RuleViolation(
            rule=RuleViolationType.WEEKLY_CAPACITY_EXCEEDED,
            message=f"Weekly appointment limit reached ({rules.max_appointments_per_week})",
            details={
                "max_weekly": rules.max_appointments_per_week,
                "remaining": remaining_weekly,
            },
        ))

    # DB: Time conflict check with buffers
    search_start = proposed_start - timedelta(minutes=rules.buffer_before_minutes + 60)
    search_end = proposed_end + timedelta(minutes=rules.buffer_after_minutes + 60)
    busy_blocks = _get_busy_blocks(db, lo_id, search_start, search_end, rules.org_id)
    all_violations.extend(
        _check_time_conflicts(
            proposed_start, proposed_end, busy_blocks,
            rules.buffer_before_minutes, rules.buffer_after_minutes,
        )
    )

    # DB: Blocked time check
    all_violations.extend(
        _check_blocked_times(db, lo_id, proposed_start, proposed_end, rules.org_id)
    )

    # Determine overall validity: any non-overridable error = not bookable
    hard_violations = [v for v in all_violations if v.severity == "error" and not v.overridable]
    is_valid = len(hard_violations) == 0

    return is_valid, all_violations


# =============================================================================
# NEXT AVAILABLE SLOT FINDER
# =============================================================================

async def get_next_available(
    lo_id: int,
    after_datetime: datetime,
    duration_minutes: int,
    rules: SchedulingRules,
    db: Session,
    max_search_days: int = 30,
) -> Optional[datetime]:
    """
    Find the next available slot for an LO after a given datetime.

    Scans forward day-by-day through business hours, skipping lunch breaks,
    blocked times, and conflicts until a valid slot is found.

    Args:
        lo_id: Loan officer user ID
        after_datetime: Start searching after this time
        duration_minutes: Required appointment duration
        rules: Scheduling rules to apply
        db: Database session
        max_search_days: Maximum number of days to search forward

    Returns:
        The start datetime of the next available slot, or None if nothing found
        within the search window.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    min_booking_time = now + timedelta(hours=rules.min_notice_hours)
    search_start = max(after_datetime, min_booking_time)

    # Pre-fetch blocked dates for the search range
    search_end_date = (search_start + timedelta(days=max_search_days)).date()
    blocked_dates = await get_blocked_dates(
        lo_id, search_start.date(), search_end_date, db, rules.org_id
    )
    blocked_dates_set = set(blocked_dates)

    current_date = search_start.date()
    end_search = current_date + timedelta(days=max_search_days)

    while current_date <= end_search:
        # Skip blocked dates
        if current_date in blocked_dates_set:
            current_date += timedelta(days=1)
            continue

        # Skip non-working days
        day_name = _DAY_NAMES[current_date.weekday()]
        day_schedule = rules.working_hours.get(day_name)
        if not day_schedule or not day_schedule.enabled:
            current_date += timedelta(days=1)
            continue

        # Check daily capacity
        has_capacity, _ = await check_capacity(lo_id, current_date, rules, db)
        if not has_capacity:
            current_date += timedelta(days=1)
            continue

        # Parse work hours
        work_start = datetime.strptime(day_schedule.start, "%H:%M").time()
        work_end = datetime.strptime(day_schedule.end, "%H:%M").time()

        slot_start = datetime.combine(current_date, work_start)
        day_end = datetime.combine(current_date, work_end)

        # If searching on the start date, begin from the search_start time
        if current_date == search_start.date() and search_start > slot_start:
            # Round up to next slot increment
            slot_start = search_start
            minutes_past = slot_start.minute % rules.duration_increment_minutes
            if minutes_past > 0:
                slot_start += timedelta(minutes=rules.duration_increment_minutes - minutes_past)
                slot_start = slot_start.replace(second=0, microsecond=0)

        # Pre-fetch busy blocks for this day
        busy_blocks = _get_busy_blocks(
            db, lo_id,
            datetime.combine(current_date, time.min),
            datetime.combine(current_date, time.max),
            rules.org_id,
        )

        lunch_start = datetime.combine(current_date, rules.get_lunch_start_time())
        lunch_end = datetime.combine(current_date, rules.get_lunch_end_time())

        while slot_start + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = slot_start + timedelta(minutes=duration_minutes)

            # Skip if before minimum booking time
            if slot_start < min_booking_time:
                slot_start += timedelta(minutes=rules.duration_increment_minutes)
                continue

            # Skip lunch break
            if rules.enforce_lunch_break and slot_start < lunch_end and slot_end > lunch_start:
                slot_start = lunch_end
                continue

            # Check time conflicts with buffers
            conflict_violations = _check_time_conflicts(
                slot_start, slot_end, busy_blocks,
                rules.buffer_before_minutes, rules.buffer_after_minutes,
            )

            if not conflict_violations:
                return slot_start

            slot_start += timedelta(minutes=rules.duration_increment_minutes)

        current_date += timedelta(days=1)

    return None


# =============================================================================
# RULES PERSISTENCE (save updated rules back to DB)
# =============================================================================

async def save_rules_for_lo(
    lo_id: int,
    org_id: int,
    rules: SchedulingRules,
    db: Session,
) -> bool:
    """
    Save scheduling rules for a specific LO to the scheduler_configs table.

    If a config already exists for this LO, update it. Otherwise, create a new one.
    Returns True on success.
    """
    # Build working_hours JSON from DaySchedule models
    working_hours_json = {
        day: {"start": sched.start, "end": sched.end, "enabled": sched.enabled}
        for day, sched in rules.working_hours.items()
    }

    try:
        existing = db.execute(text(
            "SELECT id FROM scheduler_configs "
            "WHERE user_id = :uid AND organization_id = :org_id AND is_active = true "
            "LIMIT 1"
        ), {"uid": lo_id, "org_id": org_id}).scalar()

        if existing:
            db.execute(text("""
                UPDATE scheduler_configs SET
                    working_hours = :working_hours,
                    buffer_before_minutes = :buffer_before,
                    buffer_after_minutes = :buffer_after,
                    lunch_break_start = :lunch_start,
                    lunch_break_end = :lunch_end,
                    enforce_lunch_break = :enforce_lunch,
                    max_meetings_per_day = :max_daily,
                    min_notice_hours = :min_notice,
                    max_advance_days = :max_advance,
                    min_duration_minutes = :min_duration,
                    max_duration_minutes = :max_duration,
                    default_duration_minutes = :default_duration,
                    timezone = :tz,
                    updated_at = NOW()
                WHERE id = :config_id
            """), {
                "config_id": existing,
                "working_hours": working_hours_json,
                "buffer_before": rules.buffer_before_minutes,
                "buffer_after": rules.buffer_after_minutes,
                "lunch_start": rules.lunch_break_start,
                "lunch_end": rules.lunch_break_end,
                "enforce_lunch": rules.enforce_lunch_break,
                "max_daily": rules.max_appointments_per_day,
                "min_notice": rules.min_notice_hours,
                "max_advance": rules.max_advance_days,
                "min_duration": rules.min_duration_minutes,
                "max_duration": rules.max_duration_minutes,
                "default_duration": rules.default_duration_minutes,
                "tz": rules.timezone,
            })
        else:
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    user_id, organization_id, config_name, working_hours,
                    buffer_before_minutes, buffer_after_minutes,
                    lunch_break_start, lunch_break_end, enforce_lunch_break,
                    max_meetings_per_day, min_notice_hours, max_advance_days,
                    min_duration_minutes, max_duration_minutes, default_duration_minutes,
                    timezone, is_active, created_at, updated_at
                ) VALUES (
                    :uid, :org_id, :config_name, :working_hours,
                    :buffer_before, :buffer_after,
                    :lunch_start, :lunch_end, :enforce_lunch,
                    :max_daily, :min_notice, :max_advance,
                    :min_duration, :max_duration, :default_duration,
                    :tz, true, NOW(), NOW()
                )
            """), {
                "uid": lo_id,
                "org_id": org_id,
                "config_name": f"LO {lo_id} rules",
                "working_hours": working_hours_json,
                "buffer_before": rules.buffer_before_minutes,
                "buffer_after": rules.buffer_after_minutes,
                "lunch_start": rules.lunch_break_start,
                "lunch_end": rules.lunch_break_end,
                "enforce_lunch": rules.enforce_lunch_break,
                "max_daily": rules.max_appointments_per_day,
                "min_notice": rules.min_notice_hours,
                "max_advance": rules.max_advance_days,
                "min_duration": rules.min_duration_minutes,
                "max_duration": rules.max_duration_minutes,
                "default_duration": rules.default_duration_minutes,
                "tz": rules.timezone,
            })

        db.flush()
        return True
    except Exception as e:
        logger.error(f"Failed to save rules for LO {lo_id}: {e}")
        return False


async def save_org_default_rules(
    org_id: int,
    rules: SchedulingRules,
    db: Session,
) -> bool:
    """
    Save org-level default scheduling rules (user_id IS NULL).
    """
    working_hours_json = {
        day: {"start": sched.start, "end": sched.end, "enabled": sched.enabled}
        for day, sched in rules.working_hours.items()
    }

    try:
        existing = db.execute(text(
            "SELECT id FROM scheduler_configs "
            "WHERE user_id IS NULL AND organization_id = :org_id AND is_active = true "
            "LIMIT 1"
        ), {"org_id": org_id}).scalar()

        if existing:
            db.execute(text("""
                UPDATE scheduler_configs SET
                    working_hours = :working_hours,
                    buffer_before_minutes = :buffer_before,
                    buffer_after_minutes = :buffer_after,
                    lunch_break_start = :lunch_start,
                    lunch_break_end = :lunch_end,
                    enforce_lunch_break = :enforce_lunch,
                    max_meetings_per_day = :max_daily,
                    min_notice_hours = :min_notice,
                    max_advance_days = :max_advance,
                    min_duration_minutes = :min_duration,
                    max_duration_minutes = :max_duration,
                    default_duration_minutes = :default_duration,
                    timezone = :tz,
                    updated_at = NOW()
                WHERE id = :config_id
            """), {
                "config_id": existing,
                "working_hours": working_hours_json,
                "buffer_before": rules.buffer_before_minutes,
                "buffer_after": rules.buffer_after_minutes,
                "lunch_start": rules.lunch_break_start,
                "lunch_end": rules.lunch_break_end,
                "enforce_lunch": rules.enforce_lunch_break,
                "max_daily": rules.max_appointments_per_day,
                "min_notice": rules.min_notice_hours,
                "max_advance": rules.max_advance_days,
                "min_duration": rules.min_duration_minutes,
                "max_duration": rules.max_duration_minutes,
                "default_duration": rules.default_duration_minutes,
                "tz": rules.timezone,
            })
        else:
            db.execute(text("""
                INSERT INTO scheduler_configs (
                    user_id, organization_id, config_name, working_hours,
                    buffer_before_minutes, buffer_after_minutes,
                    lunch_break_start, lunch_break_end, enforce_lunch_break,
                    max_meetings_per_day, min_notice_hours, max_advance_days,
                    min_duration_minutes, max_duration_minutes, default_duration_minutes,
                    timezone, is_active, created_at, updated_at
                ) VALUES (
                    NULL, :org_id, :config_name, :working_hours,
                    :buffer_before, :buffer_after,
                    :lunch_start, :lunch_end, :enforce_lunch,
                    :max_daily, :min_notice, :max_advance,
                    :min_duration, :max_duration, :default_duration,
                    :tz, true, NOW(), NOW()
                )
            """), {
                "org_id": org_id,
                "config_name": f"Org {org_id} defaults",
                "working_hours": working_hours_json,
                "buffer_before": rules.buffer_before_minutes,
                "buffer_after": rules.buffer_after_minutes,
                "lunch_start": rules.lunch_break_start,
                "lunch_end": rules.lunch_break_end,
                "enforce_lunch": rules.enforce_lunch_break,
                "max_daily": rules.max_appointments_per_day,
                "min_notice": rules.min_notice_hours,
                "max_advance": rules.max_advance_days,
                "min_duration": rules.min_duration_minutes,
                "max_duration": rules.max_duration_minutes,
                "default_duration": rules.default_duration_minutes,
                "tz": rules.timezone,
            })

        db.flush()
        return True
    except Exception as e:
        logger.error(f"Failed to save org default rules for org {org_id}: {e}")
        return False
