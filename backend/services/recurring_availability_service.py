"""
Recurring Availability Service

Provides business logic for managing weekly recurring availability patterns,
date-specific exceptions, and org-level templates.

Slot computation pipeline:
  1. Start with recurring weekly schedule for the target date's day_of_week
  2. Apply date-specific exceptions (overrides/blocks)
  3. Subtract existing appointments (from scheduler_appointments table)
  4. Apply appointment type constraints (duration, buffer, max daily)
  5. Return available time slots

This service is used by both the authenticated availability endpoints
and the public booking slot generation engine.
"""

import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)


class RecurringAvailabilityService:
    """
    Service for managing recurring availability patterns and computing
    effective available time slots.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # IMPORTS (lazy to avoid circular imports at module load time)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_models():
        from database.models.recurring_availability import (
            RecurringAvailability,
            AvailabilityException,
            AvailabilityTemplate,
        )
        return RecurringAvailability, AvailabilityException, AvailabilityTemplate

    # ==================================================================
    # WEEKLY SCHEDULE MANAGEMENT
    # ==================================================================

    def get_weekly_schedule(self, user_id: int, org_id: int) -> List[dict]:
        """
        Get the current weekly recurring schedule for a user.

        Returns a list of dicts, one per active recurring availability row:
        [
            {"id": 1, "day_of_week": 0, "start_time": "09:00", "end_time": "12:00", ...},
            ...
        ]
        """
        RecurringAvailability, _, _ = self._get_models()

        rows = (
            self.db.query(RecurringAvailability)
            .filter(
                RecurringAvailability.user_id == user_id,
                RecurringAvailability.organization_id == org_id,
                RecurringAvailability.is_active == True,
            )
            .order_by(RecurringAvailability.day_of_week, RecurringAvailability.start_time)
            .all()
        )

        return [
            {
                "id": r.id,
                "day_of_week": r.day_of_week,
                "start_time": r.start_time.strftime("%H:%M") if r.start_time else None,
                "end_time": r.end_time.strftime("%H:%M") if r.end_time else None,
                "is_active": r.is_active,
                "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                "effective_until": r.effective_until.isoformat() if r.effective_until else None,
                "timezone": r.timezone,
            }
            for r in rows
        ]

    def set_weekly_schedule(
        self,
        user_id: int,
        org_id: int,
        schedule: Dict[int, List[Dict[str, str]]],
        tz: str = DEFAULT_TIMEZONE,
    ) -> List[dict]:
        """
        Bulk-replace the weekly recurring schedule for a user.

        Args:
            user_id: User ID
            org_id: Organization ID
            schedule: Dict mapping day_of_week (0-6) to list of time blocks.
                Example: {0: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}]}
            tz: Timezone string (e.g., "America/Chicago")

        Returns:
            The new schedule as a list of dicts.
        """
        RecurringAvailability, _, _ = self._get_models()

        # Validate schedule
        for dow, blocks in schedule.items():
            dow_int = int(dow)
            if dow_int < 0 or dow_int > 6:
                raise ValueError(f"Invalid day_of_week: {dow}. Must be 0-6.")
            parsed_blocks = []
            for block in blocks:
                start = datetime.strptime(block["start"], "%H:%M").time()
                end = datetime.strptime(block["end"], "%H:%M").time()
                if start >= end:
                    raise ValueError(
                        f"start_time ({block['start']}) must be before end_time ({block['end']}) "
                        f"on day {dow_int}"
                    )
                parsed_blocks.append((start, end))

            # M17 fix: Check for overlapping blocks on the same day
            parsed_blocks.sort(key=lambda b: b[0])
            for i in range(len(parsed_blocks) - 1):
                _, prev_end = parsed_blocks[i]
                next_start, _ = parsed_blocks[i + 1]
                if next_start < prev_end:
                    raise ValueError(
                        f"Overlapping availability blocks on day {dow_int}: "
                        f"block ending at {prev_end.strftime('%H:%M')} overlaps with "
                        f"block starting at {next_start.strftime('%H:%M')}"
                    )

        # Soft-delete existing schedule (deactivate, don't hard delete)
        self.db.query(RecurringAvailability).filter(
            RecurringAvailability.user_id == user_id,
            RecurringAvailability.organization_id == org_id,
            RecurringAvailability.is_active == True,
        ).update({"is_active": False}, synchronize_session="fetch")

        # Create new rows
        new_rows = []
        for dow, blocks in schedule.items():
            dow_int = int(dow)
            for block in blocks:
                start = datetime.strptime(block["start"], "%H:%M").time()
                end = datetime.strptime(block["end"], "%H:%M").time()
                row = RecurringAvailability(
                    user_id=user_id,
                    organization_id=org_id,
                    day_of_week=dow_int,
                    start_time=start,
                    end_time=end,
                    is_active=True,
                    timezone=tz,
                    effective_from=block.get("effective_from"),
                    effective_until=block.get("effective_until"),
                )
                self.db.add(row)
                new_rows.append(row)

        self.db.flush()

        return [
            {
                "id": r.id,
                "day_of_week": r.day_of_week,
                "start_time": r.start_time.strftime("%H:%M"),
                "end_time": r.end_time.strftime("%H:%M"),
                "is_active": r.is_active,
                "timezone": r.timezone,
            }
            for r in new_rows
        ]

    # ==================================================================
    # EXCEPTION MANAGEMENT
    # ==================================================================

    def get_exceptions(
        self,
        user_id: int,
        org_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """Get availability exceptions, optionally filtered by date range."""
        _, AvailabilityException, _ = self._get_models()

        query = self.db.query(AvailabilityException).filter(
            AvailabilityException.user_id == user_id,
            AvailabilityException.organization_id == org_id,
        )

        if start_date:
            query = query.filter(AvailabilityException.date >= start_date)
        if end_date:
            query = query.filter(AvailabilityException.date <= end_date)

        rows = query.order_by(AvailabilityException.date, AvailabilityException.start_time).all()

        return [
            {
                "id": r.id,
                "date": r.date.isoformat(),
                "start_time": r.start_time.strftime("%H:%M") if r.start_time else None,
                "end_time": r.end_time.strftime("%H:%M") if r.end_time else None,
                "is_blocked": r.is_blocked,
                "reason": r.reason,
            }
            for r in rows
        ]

    def add_exception(
        self,
        user_id: int,
        org_id: int,
        exc_date: date,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
        is_blocked: bool = True,
        reason: Optional[str] = None,
    ) -> dict:
        """
        Add a date-specific availability exception.

        Args:
            user_id: User ID
            org_id: Organization ID
            exc_date: The date for this exception
            start_time: Start of affected time range (None = full day)
            end_time: End of affected time range (None = full day)
            is_blocked: True = unavailable, False = extra availability
            reason: Human-readable reason
        """
        _, AvailabilityException, _ = self._get_models()

        # Validate time range if both provided
        if start_time and end_time and start_time >= end_time:
            raise ValueError("start_time must be before end_time")

        # If adding extra availability (is_blocked=False), times are required
        if not is_blocked and (start_time is None or end_time is None):
            raise ValueError("start_time and end_time are required for extra availability")

        exc = AvailabilityException(
            user_id=user_id,
            organization_id=org_id,
            date=exc_date,
            start_time=start_time,
            end_time=end_time,
            is_blocked=is_blocked,
            reason=reason,
        )
        self.db.add(exc)
        self.db.flush()

        return {
            "id": exc.id,
            "date": exc.date.isoformat(),
            "start_time": exc.start_time.strftime("%H:%M") if exc.start_time else None,
            "end_time": exc.end_time.strftime("%H:%M") if exc.end_time else None,
            "is_blocked": exc.is_blocked,
            "reason": exc.reason,
        }

    def remove_exception(self, exception_id: int, user_id: int, org_id: int) -> bool:
        """Remove an availability exception. Returns True if deleted, False if not found."""
        _, AvailabilityException, _ = self._get_models()

        deleted = (
            self.db.query(AvailabilityException)
            .filter(
                AvailabilityException.id == exception_id,
                AvailabilityException.user_id == user_id,
                AvailabilityException.organization_id == org_id,
            )
            .delete(synchronize_session="fetch")
        )
        return deleted > 0

    # ==================================================================
    # TEMPLATE MANAGEMENT
    # ==================================================================

    def get_templates(self, org_id: int) -> List[dict]:
        """Get all availability templates for an organization."""
        _, _, AvailabilityTemplate = self._get_models()

        rows = (
            self.db.query(AvailabilityTemplate)
            .filter(AvailabilityTemplate.organization_id == org_id)
            .order_by(AvailabilityTemplate.is_default.desc(), AvailabilityTemplate.name)
            .all()
        )

        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "schedule": r.schedule,
                "is_default": r.is_default,
                "timezone": r.timezone,
            }
            for r in rows
        ]

    def create_template(
        self,
        org_id: int,
        name: str,
        schedule: dict,
        description: Optional[str] = None,
        is_default: bool = False,
        tz: str = DEFAULT_TIMEZONE,
    ) -> dict:
        """Create a reusable availability template."""
        _, _, AvailabilityTemplate = self._get_models()

        # If marking as default, clear existing defaults
        if is_default:
            self.db.query(AvailabilityTemplate).filter(
                AvailabilityTemplate.organization_id == org_id,
                AvailabilityTemplate.is_default == True,
            ).update({"is_default": False}, synchronize_session="fetch")

        template = AvailabilityTemplate(
            organization_id=org_id,
            name=name,
            description=description,
            schedule=schedule,
            is_default=is_default,
            timezone=tz,
        )
        self.db.add(template)
        self.db.flush()

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "schedule": template.schedule,
            "is_default": template.is_default,
            "timezone": template.timezone,
        }

    def apply_template(self, user_id: int, org_id: int, template_id: int) -> List[dict]:
        """
        Apply an org template to a user's recurring schedule.

        Reads the template's schedule JSON and calls set_weekly_schedule.
        Returns the new schedule.
        """
        _, _, AvailabilityTemplate = self._get_models()

        template = (
            self.db.query(AvailabilityTemplate)
            .filter(
                AvailabilityTemplate.id == template_id,
                AvailabilityTemplate.organization_id == org_id,
            )
            .first()
        )

        if not template:
            raise ValueError(f"Template {template_id} not found in organization {org_id}")

        return self.set_weekly_schedule(
            user_id=user_id,
            org_id=org_id,
            schedule=template.schedule,
            tz=template.timezone,
        )

    # ==================================================================
    # EFFECTIVE SCHEDULE & SLOT COMPUTATION
    # ==================================================================

    def get_effective_schedule(self, user_id: int, org_id: int, target_date: date) -> List[dict]:
        """
        Get the effective availability schedule for a specific date.

        Merges recurring weekly schedule with date-specific exceptions:
        1. Get recurring blocks for the target day_of_week
        2. Apply full-day blocks (remove all recurring if blocked)
        3. Apply time-range blocks (subtract blocked ranges)
        4. Add extra availability blocks

        Returns list of available time ranges:
        [{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}]
        """
        RecurringAvailability, AvailabilityException, _ = self._get_models()

        day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday

        # Step 1: Get recurring blocks for this day
        recurring = (
            self.db.query(RecurringAvailability)
            .filter(
                RecurringAvailability.user_id == user_id,
                RecurringAvailability.organization_id == org_id,
                RecurringAvailability.day_of_week == day_of_week,
                RecurringAvailability.is_active == True,
                or_(
                    RecurringAvailability.effective_from.is_(None),
                    RecurringAvailability.effective_from <= target_date,
                ),
                or_(
                    RecurringAvailability.effective_until.is_(None),
                    RecurringAvailability.effective_until >= target_date,
                ),
            )
            .order_by(RecurringAvailability.start_time)
            .all()
        )

        # Convert to time range tuples
        available_ranges: List[Tuple[time, time]] = [
            (r.start_time, r.end_time) for r in recurring
        ]

        # Step 2: Get exceptions for this date
        exceptions = (
            self.db.query(AvailabilityException)
            .filter(
                AvailabilityException.user_id == user_id,
                AvailabilityException.organization_id == org_id,
                AvailabilityException.date == target_date,
            )
            .all()
        )

        # Process exceptions
        for exc in exceptions:
            if exc.is_blocked:
                if exc.start_time is None and exc.end_time is None:
                    # Full day block - remove all availability
                    available_ranges = []
                else:
                    # Partial block - subtract from ranges
                    available_ranges = self._subtract_range(
                        available_ranges, exc.start_time, exc.end_time
                    )
            else:
                # Extra availability - add to ranges
                if exc.start_time and exc.end_time:
                    available_ranges.append((exc.start_time, exc.end_time))
                    # Re-sort after adding
                    available_ranges.sort(key=lambda r: r[0])

        # Merge overlapping ranges
        available_ranges = self._merge_ranges(available_ranges)

        return [
            {"start": r[0].strftime("%H:%M"), "end": r[1].strftime("%H:%M")}
            for r in available_ranges
        ]

    def get_available_slots(
        self,
        user_id: int,
        org_id: int,
        start_date: date,
        end_date: date,
        duration_minutes: int = 30,
        buffer_before: int = 0,
        buffer_after: int = 0,
        max_per_day: Optional[int] = None,
        timezone_str: Optional[str] = None,
    ) -> List[dict]:
        """
        Compute actual available time slots by merging:
        1. Recurring weekly schedule
        2. Date-specific exceptions
        3. Existing appointments (subtracted)
        4. Appointment type constraints (duration, buffer, max daily)

        All time arithmetic is done in the user's local timezone to correctly
        handle DST transitions (spring-forward / fall-back). Slot datetimes
        are converted to UTC for storage and comparison.

        Args:
            user_id: User ID
            org_id: Organization ID
            start_date: Start of date range
            end_date: End of date range
            duration_minutes: Required slot duration
            buffer_before: Minutes before each appointment to keep free
            buffer_after: Minutes after each appointment to keep free
            max_per_day: Maximum slots per day (None = unlimited)
            timezone_str: IANA timezone for the user (e.g. "America/Chicago").
                Falls back to the recurring availability row's timezone,
                then DEFAULT_TIMEZONE.

        Returns:
            List of available slot dicts: [{"date": "2026-03-15", "start": "09:00", "end": "09:30"}, ...]
        """
        # H13 fix: Resolve the user's local timezone for DST-safe arithmetic.
        # Prefer explicit param, then look up from user's recurring availability
        # config, then fall back to DEFAULT_TIMEZONE.
        user_tz = self._resolve_user_timezone(user_id, org_id, timezone_str)
        utc_tz = ZoneInfo("UTC")

        # Get existing appointments for the date range
        existing_appointments = self._get_existing_appointments(
            user_id, org_id, start_date, end_date
        )

        all_slots = []
        current_date = start_date

        while current_date <= end_date:
            # Get effective schedule for this date (recurring + exceptions)
            day_schedule = self.get_effective_schedule(user_id, org_id, current_date)

            # Get appointments for this date
            day_appointments = [
                a for a in existing_appointments
                if a["date"] == current_date
            ]

            day_slots = []

            for block in day_schedule:
                block_start = datetime.strptime(block["start"], "%H:%M").time()
                block_end = datetime.strptime(block["end"], "%H:%M").time()

                # H13 fix: Build timezone-aware datetimes in the user's
                # local timezone so DST transitions are handled correctly.
                # datetime.combine with a ZoneInfo tzinfo correctly resolves
                # ambiguous/missing wall-clock times on DST boundaries.
                slot_start_dt = datetime.combine(current_date, block_start, tzinfo=user_tz)
                block_end_dt = datetime.combine(current_date, block_end, tzinfo=user_tz)

                while slot_start_dt + timedelta(minutes=duration_minutes) <= block_end_dt:
                    slot_end_dt = slot_start_dt + timedelta(minutes=duration_minutes)

                    # Convert to UTC for comparison with appointment times
                    slot_start_utc = slot_start_dt.astimezone(utc_tz)
                    slot_end_utc = slot_end_dt.astimezone(utc_tz)

                    # Check if slot conflicts with any appointment (including buffers)
                    has_conflict = False
                    for appt in day_appointments:
                        appt_start = appt["start"]
                        appt_end = appt["end"]
                        # Ensure appointment times are tz-aware for comparison
                        if appt_start.tzinfo is None:
                            appt_start = appt_start.replace(tzinfo=utc_tz)
                        if appt_end.tzinfo is None:
                            appt_end = appt_end.replace(tzinfo=utc_tz)
                        buffered_start = appt_start - timedelta(minutes=buffer_before)
                        buffered_end = appt_end + timedelta(minutes=buffer_after)

                        if slot_start_utc < buffered_end and slot_end_utc > buffered_start:
                            has_conflict = True
                            break

                    if not has_conflict:
                        day_slots.append({
                            "date": current_date.isoformat(),
                            "start": slot_start_dt.strftime("%H:%M"),
                            "end": slot_end_dt.strftime("%H:%M"),
                            "start_datetime": slot_start_utc.isoformat(),
                            "end_datetime": slot_end_utc.isoformat(),
                        })

                    # Advance by slot step (30-minute increments)
                    slot_start_dt += timedelta(minutes=30)

            # Apply max per day limit
            if max_per_day and len(day_slots) > max_per_day:
                day_slots = day_slots[:max_per_day]

            all_slots.extend(day_slots)
            current_date += timedelta(days=1)

        return all_slots

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================

    def _resolve_user_timezone(
        self,
        user_id: int,
        org_id: int,
        override: Optional[str] = None,
    ) -> ZoneInfo:
        """
        Resolve the IANA timezone for a user's availability.

        Priority:
        1. Explicit override parameter
        2. Timezone stored on the user's active recurring availability rows
        3. DEFAULT_TIMEZONE constant

        Returns a ZoneInfo instance.
        """
        if override:
            try:
                return ZoneInfo(override)
            except (KeyError, ValueError):
                logger.warning(
                    "Invalid timezone override '%s', falling back to default", override
                )

        # Look up from existing recurring availability rows
        RecurringAvailability, _, _ = self._get_models()
        row = (
            self.db.query(RecurringAvailability.timezone)
            .filter(
                RecurringAvailability.user_id == user_id,
                RecurringAvailability.organization_id == org_id,
                RecurringAvailability.is_active == True,
            )
            .first()
        )
        if row and row[0]:
            try:
                return ZoneInfo(row[0])
            except (KeyError, ValueError):
                logger.warning(
                    "Invalid timezone '%s' on recurring availability for user %s, "
                    "falling back to default",
                    row[0], user_id,
                )

        return ZoneInfo(DEFAULT_TIMEZONE)

    def _get_existing_appointments(
        self,
        user_id: int,
        org_id: int,
        start_date: date,
        end_date: date,
    ) -> List[dict]:
        """
        Get existing booked/tentative appointments for a user in a date range.
        Returns list of {date, start, end} dicts with datetime objects.
        """
        appointments = []

        # M16 fix: Separate ImportError (critical -- means the module is broken)
        # from runtime errors (which can be warned about and recovered from).
        try:
            from smart_scheduler_models import AppointmentStatus
            from routes.scheduler._helpers import get_models
        except ImportError:
            logger.error(
                "Failed to import scheduler models required for appointment "
                "conflict detection. Recurring availability slots will NOT "
                "account for existing appointments.",
                exc_info=True,
            )
            raise

        try:
            models = get_models()
            Appointment = models.get("Appointment") if models else None

            if Appointment:
                start_dt = datetime.combine(start_date, time.min)
                end_dt = datetime.combine(end_date, time.max)

                appts = (
                    self.db.query(Appointment)
                    .filter(
                        Appointment.assigned_user_id == user_id,
                        Appointment.organization_id == org_id,
                        Appointment.status.in_([
                            AppointmentStatus.BOOKED,
                            AppointmentStatus.TENTATIVE,
                        ]),
                        Appointment.scheduled_start >= start_dt,
                        Appointment.scheduled_start <= end_dt,
                    )
                    .all()
                )

                for a in appts:
                    if a.scheduled_start and a.scheduled_end:
                        appointments.append({
                            "date": a.scheduled_start.date(),
                            "start": a.scheduled_start,
                            "end": a.scheduled_end,
                        })
        except Exception as e:
            logger.warning(f"Could not load appointments for availability: {e}")

        return appointments

    @staticmethod
    def _subtract_range(
        ranges: List[Tuple[time, time]],
        block_start: time,
        block_end: time,
    ) -> List[Tuple[time, time]]:
        """
        Subtract a blocked time range from a list of available ranges.

        Example:
            ranges = [(09:00, 17:00)]
            block = (12:00, 13:00)
            result = [(09:00, 12:00), (13:00, 17:00)]
        """
        result = []
        for r_start, r_end in ranges:
            if block_end <= r_start or block_start >= r_end:
                # No overlap - keep the range
                result.append((r_start, r_end))
            else:
                # Overlap - split the range
                if r_start < block_start:
                    result.append((r_start, block_start))
                if r_end > block_end:
                    result.append((block_end, r_end))
        return result

    @staticmethod
    def _merge_ranges(ranges: List[Tuple[time, time]]) -> List[Tuple[time, time]]:
        """
        Merge overlapping or adjacent time ranges.

        Example:
            [(09:00, 12:00), (11:30, 14:00), (15:00, 17:00)]
            -> [(09:00, 14:00), (15:00, 17:00)]
        """
        if not ranges:
            return []

        sorted_ranges = sorted(ranges, key=lambda r: r[0])
        merged = [sorted_ranges[0]]

        for current_start, current_end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if current_start <= last_end:
                # Overlapping or adjacent - merge
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))

        return merged
