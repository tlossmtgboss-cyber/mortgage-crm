"""
Holiday & PTO Management Service - Perennia AI Scheduler

Provides:
- Holiday model (org-level, seeded with US federal holidays)
- PTORequest model (user-level PTO with approval workflow)
- is_working_day() check for the availability/slot engine
- get_blocked_dates() for scheduling conflict detection
- Team availability calendar (who's in/out on any date range)

Integration points:
- Called by the slot-generation engine in scheduler_appointment_routes.py
- BlockedTime records are created automatically when PTO is approved
- Federal holidays auto-seeded per organization on first access
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, and_, or_,
)
from sqlalchemy.orm import Session, relationship

logger = logging.getLogger(__name__)


# ============================================================================
# MODEL FACTORY
# ============================================================================

def create_holiday_models(Base):
    """
    Factory to create Holiday and PTORequest models with the provided Base.
    Follows the same pattern as create_smart_scheduler_models().
    """

    class Holiday(Base):
        """
        Organization-level holidays.
        Can be federal, state, company, or custom holidays.
        """
        __tablename__ = "scheduler_holidays"
        __table_args__ = (
            UniqueConstraint(
                "organization_id", "holiday_date", "name",
                name="uq_holiday_org_date_name",
            ),
            Index("ix_holidays_org_date", "organization_id", "holiday_date"),
            {"extend_existing": True},
        )

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(
            Integer,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
        name = Column(String(150), nullable=False)
        holiday_date = Column(Date, nullable=False)
        holiday_type = Column(
            String(30), nullable=False, default="federal"
        )  # federal, state, company, custom
        is_half_day = Column(Boolean, default=False)
        half_day_end_time = Column(String(5), nullable=True)  # "13:00" — office closes at 1 PM

        # Observance details
        observed_date = Column(Date, nullable=True)  # Actual observed date if shifted
        notes = Column(Text, nullable=True)

        is_active = Column(Boolean, default=True)
        created_at = Column(
            DateTime, default=lambda: datetime.now(timezone.utc)
        )
        updated_at = Column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )
        created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    class PTORequest(Base):
        """
        User-level PTO / time-off requests with approval workflow.
        """
        __tablename__ = "scheduler_pto_requests"
        __table_args__ = (
            Index("ix_pto_user_dates", "user_id", "start_date", "end_date"),
            Index("ix_pto_org_status", "organization_id", "status"),
            {"extend_existing": True},
        )

        id = Column(Integer, primary_key=True, index=True)
        organization_id = Column(
            Integer,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
        user_id = Column(
            Integer,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

        # Date range
        start_date = Column(Date, nullable=False)
        end_date = Column(Date, nullable=False)

        # PTO classification
        pto_type = Column(
            String(30), nullable=False, default="vacation"
        )  # vacation, sick, personal, bereavement, jury_duty, parental, other
        reason = Column(Text, nullable=True)

        # Half-day support
        is_half_day_start = Column(Boolean, default=False)  # First day is half day
        is_half_day_end = Column(Boolean, default=False)    # Last day is half day

        # Approval workflow
        status = Column(
            String(20), nullable=False, default="pending"
        )  # pending, approved, denied, cancelled
        reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        reviewed_at = Column(DateTime, nullable=True)
        review_notes = Column(Text, nullable=True)

        # Link to blocked time (created on approval)
        blocked_time_id = Column(Integer, nullable=True)

        is_active = Column(Boolean, default=True)
        created_at = Column(
            DateTime, default=lambda: datetime.now(timezone.utc)
        )
        updated_at = Column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )

        # Relationships
        user = relationship("User", foreign_keys=[user_id], backref="pto_requests")
        reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

    return {
        "Holiday": Holiday,
        "PTORequest": PTORequest,
    }


# ============================================================================
# US FEDERAL HOLIDAYS
# ============================================================================

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    Return the nth occurrence of a weekday in a given month.
    weekday: 0=Monday ... 6=Sunday
    n: 1-based (1=first, 2=second, etc.)
    """
    first_day = date(year, month, 1)
    # Days until the target weekday
    days_ahead = weekday - first_day.weekday()
    if days_ahead < 0:
        days_ahead += 7
    first_occurrence = first_day + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a given month."""
    # Start from the last day of the month
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


def _observed_date(d: date) -> date:
    """
    If the holiday falls on Saturday, observe on Friday.
    If it falls on Sunday, observe on Monday.
    """
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    elif d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def get_us_federal_holidays(year: int) -> List[Dict[str, Any]]:
    """
    Return US federal holidays for a given year with observed dates.
    """
    holidays = []

    def _add(name: str, d: date):
        obs = _observed_date(d)
        holidays.append({
            "name": name,
            "holiday_date": d,
            "observed_date": obs if obs != d else None,
            "holiday_type": "federal",
            "is_half_day": False,
        })

    # Fixed-date holidays
    _add("New Year's Day", date(year, 1, 1))
    _add("Juneteenth", date(year, 6, 19))
    _add("Independence Day", date(year, 7, 4))
    _add("Veterans Day", date(year, 11, 11))
    _add("Christmas Day", date(year, 12, 25))

    # Floating holidays (nth weekday of month)
    _add(
        "Martin Luther King Jr. Day",
        _nth_weekday_of_month(year, 1, 0, 3),  # 3rd Monday of January
    )
    _add(
        "Presidents' Day",
        _nth_weekday_of_month(year, 2, 0, 3),  # 3rd Monday of February
    )
    _add(
        "Memorial Day",
        _last_weekday_of_month(year, 5, 0),  # Last Monday of May
    )
    _add(
        "Labor Day",
        _nth_weekday_of_month(year, 9, 0, 1),  # 1st Monday of September
    )
    _add(
        "Columbus Day",
        _nth_weekday_of_month(year, 10, 0, 2),  # 2nd Monday of October
    )

    # Thanksgiving: 4th Thursday of November
    _add(
        "Thanksgiving Day",
        _nth_weekday_of_month(year, 11, 3, 4),  # 4th Thursday of November
    )

    # Sort by date
    holidays.sort(key=lambda h: h["holiday_date"])
    return holidays


# ============================================================================
# SEEDING
# ============================================================================

def seed_federal_holidays(
    db: Session,
    organization_id: int,
    year: int,
    Holiday,
    created_by_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Seed US federal holidays for a given year and organization.
    Skips holidays that already exist (upsert-safe).

    Returns summary dict with counts.
    """
    federal = get_us_federal_holidays(year)
    created = 0
    skipped = 0

    for h in federal:
        existing = (
            db.query(Holiday)
            .filter(
                Holiday.organization_id == organization_id,
                Holiday.holiday_date == h["holiday_date"],
                Holiday.name == h["name"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        holiday = Holiday(
            organization_id=organization_id,
            name=h["name"],
            holiday_date=h["holiday_date"],
            observed_date=h["observed_date"],
            holiday_type=h["holiday_type"],
            is_half_day=h["is_half_day"],
            created_by_id=created_by_id,
        )
        db.add(holiday)
        created += 1

    if created > 0:
        db.flush()

    return {
        "year": year,
        "total_holidays": len(federal),
        "created": created,
        "skipped": skipped,
    }


# ============================================================================
# AVAILABILITY CHECKS
# ============================================================================

def is_working_day(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    check_date: date,
    Holiday,
    PTORequest,
    BlockedTime=None,
) -> Dict[str, Any]:
    """
    Determine if a given date is a working day for a user/org.

    Checks (in order):
    1. Weekend check (Saturday/Sunday)
    2. Organization holidays
    3. Approved PTO for the user
    4. All-day blocked times for the user

    Returns:
        {
            "is_working_day": bool,
            "reason": str or None,
            "is_half_day": bool,
            "half_day_end_time": str or None,
            "details": dict or None,
        }
    """
    result = {
        "is_working_day": True,
        "reason": None,
        "is_half_day": False,
        "half_day_end_time": None,
        "details": None,
    }

    # 1. Weekend check
    if check_date.weekday() >= 5:
        result["is_working_day"] = False
        result["reason"] = "weekend"
        return result

    # 2. Holiday check (check both actual date and observed date)
    holiday = (
        db.query(Holiday)
        .filter(
            Holiday.organization_id == organization_id,
            Holiday.is_active == True,
            or_(
                Holiday.holiday_date == check_date,
                Holiday.observed_date == check_date,
            ),
        )
        .first()
    )

    if holiday:
        if holiday.is_half_day:
            result["is_half_day"] = True
            result["half_day_end_time"] = holiday.half_day_end_time
            result["reason"] = f"half_day_holiday:{holiday.name}"
            result["details"] = {"holiday_name": holiday.name, "holiday_type": holiday.holiday_type}
        else:
            result["is_working_day"] = False
            result["reason"] = f"holiday:{holiday.name}"
            result["details"] = {"holiday_name": holiday.name, "holiday_type": holiday.holiday_type}
            return result

    # 3. PTO check (only if user_id provided)
    if user_id:
        pto = (
            db.query(PTORequest)
            .filter(
                PTORequest.organization_id == organization_id,
                PTORequest.user_id == user_id,
                PTORequest.status == "approved",
                PTORequest.is_active == True,
                PTORequest.start_date <= check_date,
                PTORequest.end_date >= check_date,
            )
            .first()
        )

        if pto:
            # Check if this specific day is a half day
            is_half = False
            if pto.start_date == check_date and pto.is_half_day_start:
                is_half = True
            elif pto.end_date == check_date and pto.is_half_day_end:
                is_half = True

            if is_half:
                result["is_half_day"] = True
                result["half_day_end_time"] = "13:00"
                result["reason"] = f"half_day_pto:{pto.pto_type}"
                result["details"] = {"pto_id": pto.id, "pto_type": pto.pto_type}
            else:
                result["is_working_day"] = False
                result["reason"] = f"pto:{pto.pto_type}"
                result["details"] = {"pto_id": pto.id, "pto_type": pto.pto_type}
                return result

    # 4. All-day blocked time check
    if user_id and BlockedTime is not None:
        check_dt_start = datetime.combine(check_date, time.min)
        check_dt_end = datetime.combine(check_date, time.max)

        blocked = (
            db.query(BlockedTime)
            .filter(
                BlockedTime.is_active == True,
                BlockedTime.all_day == True,
                BlockedTime.start_datetime <= check_dt_end,
                BlockedTime.end_datetime >= check_dt_start,
                or_(
                    BlockedTime.user_id == user_id,
                    and_(
                        BlockedTime.applies_to_all_users == True,
                        BlockedTime.organization_id == organization_id,
                    ),
                ),
            )
            .first()
        )

        if blocked:
            result["is_working_day"] = False
            result["reason"] = f"blocked:{blocked.block_type}"
            result["details"] = {"blocked_time_id": blocked.id, "title": blocked.title}
            return result

    return result


def get_blocked_dates(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    start_date: date,
    end_date: date,
    Holiday,
    PTORequest,
    BlockedTime=None,
) -> List[Dict[str, Any]]:
    """
    Get all blocked dates in a date range for a user/org.

    Returns a list of dicts, one per blocked date:
        [
            {"date": "2026-12-25", "reason": "holiday:Christmas Day", "is_half_day": False},
            {"date": "2026-03-15", "reason": "pto:vacation", "is_half_day": False},
            ...
        ]
    """
    blocked_dates = []
    current = start_date

    while current <= end_date:
        check = is_working_day(
            db, organization_id, user_id, current,
            Holiday, PTORequest, BlockedTime,
        )
        if not check["is_working_day"] or check["is_half_day"]:
            blocked_dates.append({
                "date": current.isoformat(),
                "reason": check["reason"],
                "is_half_day": check["is_half_day"],
                "half_day_end_time": check.get("half_day_end_time"),
                "details": check.get("details"),
            })
        current += timedelta(days=1)

    return blocked_dates


# ============================================================================
# TEAM AVAILABILITY
# ============================================================================

def get_team_availability(
    db: Session,
    organization_id: int,
    user_ids: List[int],
    start_date: date,
    end_date: date,
    Holiday,
    PTORequest,
    BlockedTime=None,
    User=None,
) -> Dict[str, Any]:
    """
    Build a team availability grid showing who's in/out for each date.

    Returns:
        {
            "start_date": "2026-03-10",
            "end_date": "2026-03-14",
            "team_members": [
                {"user_id": 1, "name": "Jane Smith", "dates": {
                    "2026-03-10": {"available": true},
                    "2026-03-11": {"available": false, "reason": "pto:vacation"},
                    ...
                }},
                ...
            ],
            "summary": {
                "2026-03-10": {"available_count": 5, "out_count": 1, "half_day_count": 0},
                ...
            }
        }
    """
    # Fetch user names if User model provided
    user_names = {}
    if User is not None:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        for u in users:
            first = getattr(u, "first_name", "") or ""
            last = getattr(u, "last_name", "") or ""
            user_names[u.id] = f"{first} {last}".strip() or f"User {u.id}"
    else:
        for uid in user_ids:
            user_names[uid] = f"User {uid}"

    team_members = []
    daily_summary: Dict[str, Dict[str, int]] = {}

    # Initialize daily summary
    current = start_date
    while current <= end_date:
        daily_summary[current.isoformat()] = {
            "available_count": 0,
            "out_count": 0,
            "half_day_count": 0,
        }
        current += timedelta(days=1)

    for uid in user_ids:
        dates_map = {}
        current = start_date

        while current <= end_date:
            check = is_working_day(
                db, organization_id, uid, current,
                Holiday, PTORequest, BlockedTime,
            )
            date_key = current.isoformat()

            if check["is_working_day"] and not check["is_half_day"]:
                dates_map[date_key] = {"available": True}
                daily_summary[date_key]["available_count"] += 1
            elif check["is_half_day"]:
                dates_map[date_key] = {
                    "available": True,
                    "is_half_day": True,
                    "half_day_end_time": check.get("half_day_end_time"),
                    "reason": check["reason"],
                }
                daily_summary[date_key]["half_day_count"] += 1
                daily_summary[date_key]["available_count"] += 1
            else:
                dates_map[date_key] = {
                    "available": False,
                    "reason": check["reason"],
                }
                daily_summary[date_key]["out_count"] += 1

            current += timedelta(days=1)

        team_members.append({
            "user_id": uid,
            "name": user_names.get(uid, f"User {uid}"),
            "dates": dates_map,
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "team_members": team_members,
        "summary": daily_summary,
    }


# ============================================================================
# PTO -> BLOCKED TIME BRIDGE
# ============================================================================

def create_blocked_time_for_pto(
    db: Session,
    pto: Any,
    BlockedTime,
) -> int:
    """
    Create a BlockedTime record for an approved PTO request.
    Returns the blocked_time_id.
    """
    start_dt = datetime.combine(pto.start_date, time.min)
    end_dt = datetime.combine(pto.end_date, time.max)

    # If half-day start, block from 13:00 onward on first day
    if pto.is_half_day_start and pto.start_date == pto.end_date:
        # Single half day: block afternoon only
        start_dt = datetime.combine(pto.start_date, time(13, 0))
        end_dt = datetime.combine(pto.start_date, time(23, 59))

    blocked = BlockedTime(
        organization_id=pto.organization_id,
        user_id=pto.user_id,
        title=f"PTO: {pto.pto_type.replace('_', ' ').title()}",
        description=pto.reason or "",
        block_type="pto",
        start_datetime=start_dt,
        end_datetime=end_dt,
        all_day=not (pto.is_half_day_start or pto.is_half_day_end),
        is_recurring=False,
        applies_to_all_users=False,
    )
    db.add(blocked)
    db.flush()
    return blocked.id
