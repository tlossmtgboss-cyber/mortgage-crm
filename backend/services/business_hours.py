"""
Business Hours Validator

Validates if current time is within business hours for:
- Click-to-call availability
- LO availability messaging
- After-hours handling
"""

import os
from datetime import datetime, time, timedelta
from typing import Optional, Tuple
import pytz

# Default timezone - can be overridden by LO settings
DEFAULT_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "America/New_York")


class BusinessHoursValidator:
    """Validate if current time is within business hours"""

    # Default business hours - can be customized per LO
    DEFAULT_HOURS = {
        0: (time(9, 0), time(18, 0)),   # Monday
        1: (time(9, 0), time(18, 0)),   # Tuesday
        2: (time(9, 0), time(18, 0)),   # Wednesday
        3: (time(9, 0), time(18, 0)),   # Thursday
        4: (time(9, 0), time(18, 0)),   # Friday
        5: (time(10, 0), time(16, 0)),  # Saturday (shorter hours)
        6: None,                         # Sunday - closed
    }

    def __init__(
        self,
        timezone_str: str = DEFAULT_TIMEZONE,
        custom_hours: Optional[dict] = None
    ):
        """
        Initialize with timezone and optional custom hours.

        Args:
            timezone_str: Timezone string (e.g., 'America/New_York')
            custom_hours: Dict of weekday -> (start_time, end_time) tuples
        """
        self.timezone = pytz.timezone(timezone_str)
        self.hours = custom_hours or self.DEFAULT_HOURS

    def is_business_hours(self) -> bool:
        """Check if current time is within business hours"""
        now = datetime.now(self.timezone)
        weekday = now.weekday()
        current_time = now.time()

        hours = self.hours.get(weekday)
        if hours is None:
            return False

        start, end = hours
        return start <= current_time <= end

    def get_availability_status(self) -> dict:
        """
        Get detailed availability status.

        Returns:
            Dict with status, next available time, message
        """
        now = datetime.now(self.timezone)
        is_available = self.is_business_hours()

        if is_available:
            return {
                'available': True,
                'message': 'Available now',
                'next_available': None,
                'call_option': 'call_now'
            }

        # Find next available time
        next_available = self._find_next_available(now)
        time_until = self._format_time_until(now, next_available)

        return {
            'available': False,
            'message': f'Available {time_until}',
            'next_available': next_available.isoformat(),
            'call_option': 'schedule'  # Default to schedule when not available
        }

    def _find_next_available(self, from_time: datetime) -> datetime:
        """Find the next available business time"""
        current = from_time

        # Check up to 7 days ahead
        for _ in range(7):
            weekday = current.weekday()
            hours = self.hours.get(weekday)

            if hours is not None:
                start_time, end_time = hours
                start_datetime = current.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0
                )

                # If we're before business hours on a business day
                if current.time() < start_time:
                    return start_datetime

                # If we're during business hours (shouldn't happen, but handle)
                if current.time() < end_time:
                    return current

            # Move to next day at midnight
            current = (current + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        # Fallback: next Monday at 9am
        return from_time + timedelta(days=(7 - from_time.weekday()))

    def _format_time_until(self, now: datetime, future: datetime) -> str:
        """Format time until next available slot"""
        diff = future - now

        if diff.days == 0:
            # Same day
            return f"at {future.strftime('%-I:%M %p')}"
        elif diff.days == 1:
            return f"tomorrow at {future.strftime('%-I:%M %p')}"
        else:
            return f"on {future.strftime('%A')} at {future.strftime('%-I:%M %p')}"

    def get_cta_guidance(self) -> dict:
        """
        Get CTA guidance based on business hours.

        Returns:
            Dict with recommended CTA type and messaging
        """
        status = self.get_availability_status()

        if status['available']:
            return {
                'primary_cta': 'call_now',
                'primary_label': 'Call Now',
                'primary_message': "Tim is available now. Tap to connect in about 30 seconds.",
                'secondary_cta': 'schedule',
                'secondary_label': 'Schedule for Later',
            }
        else:
            return {
                'primary_cta': 'schedule',
                'primary_label': 'Schedule a Call',
                'primary_message': f"Tim is {status['message']}. Schedule a time that works for you.",
                'secondary_cta': 'callback',
                'secondary_label': 'Request Callback',
            }

    @classmethod
    def for_loan_officer(cls, lo_id: int, db_session) -> 'BusinessHoursValidator':
        """
        Factory method to create validator with LO-specific hours.

        Args:
            lo_id: Loan officer ID
            db_session: Database session

        Returns:
            BusinessHoursValidator configured for LO
        """
        from sqlalchemy import text

        # Try to get LO-specific timezone and hours
        result = db_session.execute(text("""
            SELECT timezone, business_hours
            FROM users
            WHERE id = :lo_id
        """), {"lo_id": lo_id}).first()

        if result:
            timezone_str = result.timezone or DEFAULT_TIMEZONE
            custom_hours = result.business_hours  # Expect JSON
        else:
            timezone_str = DEFAULT_TIMEZONE
            custom_hours = None

        return cls(timezone_str=timezone_str, custom_hours=custom_hours)


class CallScheduleHelper:
    """Helper for scheduling callbacks"""

    @staticmethod
    def get_available_slots(
        validator: BusinessHoursValidator,
        days_ahead: int = 5,
        slot_duration_minutes: int = 30
    ) -> list:
        """
        Get available time slots for scheduling.

        Returns:
            List of available datetime slots
        """
        slots = []
        now = datetime.now(validator.timezone)

        for day_offset in range(days_ahead):
            check_date = now + timedelta(days=day_offset)
            weekday = check_date.weekday()
            hours = validator.hours.get(weekday)

            if hours is None:
                continue

            start_time, end_time = hours

            # Generate slots for this day
            current_slot = check_date.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )

            slot_end = check_date.replace(
                hour=end_time.hour,
                minute=end_time.minute,
                second=0,
                microsecond=0
            )

            while current_slot < slot_end:
                # Skip past slots
                if current_slot > now:
                    slots.append({
                        'datetime': current_slot.isoformat(),
                        'display': current_slot.strftime('%A, %B %-d at %-I:%M %p'),
                        'date': current_slot.strftime('%Y-%m-%d'),
                        'time': current_slot.strftime('%-I:%M %p')
                    })

                current_slot += timedelta(minutes=slot_duration_minutes)

        return slots[:20]  # Limit to 20 slots
