"""
Portal Close-On-Time Service - Business day calendar and deadline management.

Handles federal holiday tracking, business day calculations, close date
countdown, and milestone scheduling for on-time closings.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, extract

from models.portal_models import (
    FederalHoliday, CloseOnTimeSchedule, CloseOnTimeMilestone,
    PortalLoan, MilestoneInstance, MilestoneStatus
)

logger = logging.getLogger(__name__)


# Standard federal holidays (month, day) for fixed-date holidays
# Variable holidays are calculated dynamically
FIXED_HOLIDAYS = {
    "new_years_day": (1, 1),
    "juneteenth": (6, 19),
    "independence_day": (7, 4),
    "veterans_day": (11, 11),
    "christmas_day": (12, 25),
}


class PortalCloseOnTimeService:
    """Service for managing Close-On-Time calendar and scheduling."""

    def __init__(self, db: Session):
        self.db = db
        self._holiday_cache = {}

    # =========================================================================
    # FEDERAL HOLIDAY MANAGEMENT
    # =========================================================================

    def seed_federal_holidays(self, year: int) -> Dict[str, Any]:
        """
        Seed federal holidays for a given year.

        Federal holidays observed:
        - New Year's Day (Jan 1)
        - Martin Luther King Jr. Day (3rd Monday in January)
        - Presidents' Day (3rd Monday in February)
        - Memorial Day (Last Monday in May)
        - Juneteenth (June 19)
        - Independence Day (July 4)
        - Labor Day (1st Monday in September)
        - Columbus Day (2nd Monday in October)
        - Veterans Day (November 11)
        - Thanksgiving Day (4th Thursday in November)
        - Christmas Day (December 25)
        """
        holidays_created = []

        # Fixed date holidays
        fixed_holidays = [
            (f"{year}-01-01", "New Year's Day"),
            (f"{year}-06-19", "Juneteenth"),
            (f"{year}-07-04", "Independence Day"),
            (f"{year}-11-11", "Veterans Day"),
            (f"{year}-12-25", "Christmas Day"),
        ]

        # Variable holidays
        variable_holidays = [
            (self._get_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),  # 3rd Monday Jan
            (self._get_nth_weekday(year, 2, 0, 3), "Presidents' Day"),  # 3rd Monday Feb
            (self._get_last_weekday(year, 5, 0), "Memorial Day"),  # Last Monday May
            (self._get_nth_weekday(year, 9, 0, 1), "Labor Day"),  # 1st Monday Sep
            (self._get_nth_weekday(year, 10, 0, 2), "Columbus Day"),  # 2nd Monday Oct
            (self._get_nth_weekday(year, 11, 3, 4), "Thanksgiving Day"),  # 4th Thursday Nov
        ]

        all_holidays = fixed_holidays + variable_holidays

        for holiday_date_str, name in all_holidays:
            if isinstance(holiday_date_str, date):
                holiday_date = holiday_date_str
            else:
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()

            # Adjust for weekend observance
            observed_date = self._adjust_for_weekend(holiday_date)

            # Check if already exists (using the observed date as the holiday_date)
            existing = self.db.query(FederalHoliday).filter(
                FederalHoliday.holiday_date == observed_date
            ).first()

            if not existing:
                holiday = FederalHoliday(
                    holiday_date=observed_date,
                    holiday_name=name,
                    is_observed=True,
                    is_auto_generated=True,
                    notes=f"Actual date: {holiday_date.isoformat()}" if holiday_date != observed_date else None,
                )
                self.db.add(holiday)
                holidays_created.append(name)

        self.db.commit()

        # Clear cache
        self._holiday_cache.pop(year, None)

        logger.info(f"Seeded {len(holidays_created)} holidays for {year}")

        return {
            "year": year,
            "holidays_created": len(holidays_created),
            "holiday_names": holidays_created,
        }

    def get_holidays_for_year(self, year: int) -> List[Dict[str, Any]]:
        """Get all federal holidays for a year."""
        if year in self._holiday_cache:
            return self._holiday_cache[year]

        holidays = self.db.query(FederalHoliday).filter(
            extract('year', FederalHoliday.holiday_date) == year,
            FederalHoliday.is_observed == True
        ).order_by(FederalHoliday.holiday_date).all()

        result = [
            {
                "id": h.id,
                "name": h.holiday_name,
                "date": h.holiday_date.isoformat(),
                "is_observed": h.is_observed,
            }
            for h in holidays
        ]

        self._holiday_cache[year] = result
        return result

    def is_business_day(self, check_date: date) -> bool:
        """Check if a date is a business day."""
        # Weekend check
        if check_date.weekday() >= 5:
            return False

        # Holiday check
        holiday = self.db.query(FederalHoliday).filter(
            FederalHoliday.holiday_date == check_date,
            FederalHoliday.is_observed == True
        ).first()

        return holiday is None

    def is_holiday(self, check_date: date) -> Optional[str]:
        """Check if a date is a holiday. Returns holiday name or None."""
        holiday = self.db.query(FederalHoliday).filter(
            FederalHoliday.holiday_date == check_date,
            FederalHoliday.is_observed == True
        ).first()

        return holiday.holiday_name if holiday else None

    # =========================================================================
    # BUSINESS DAY CALCULATIONS
    # =========================================================================

    def add_business_days(self, start_date: date, days: int) -> date:
        """Add business days to a date, skipping weekends and holidays."""
        if days == 0:
            return start_date

        current_date = start_date
        direction = 1 if days > 0 else -1
        remaining = abs(days)

        while remaining > 0:
            current_date += timedelta(days=direction)
            if self.is_business_day(current_date):
                remaining -= 1

        return current_date

    def count_business_days(self, start_date: date, end_date: date) -> int:
        """Count business days between two dates (exclusive of end date)."""
        if start_date >= end_date:
            return 0

        count = 0
        current = start_date

        while current < end_date:
            if self.is_business_day(current):
                count += 1
            current += timedelta(days=1)

        return count

    def get_business_days_until(self, target_date: date) -> int:
        """Get business days from today until target date."""
        return self.count_business_days(date.today(), target_date)

    def get_next_business_day(self, from_date: date) -> date:
        """Get the next business day from a given date."""
        return self.add_business_days(from_date, 1)

    def get_previous_business_day(self, from_date: date) -> date:
        """Get the previous business day from a given date."""
        return self.add_business_days(from_date, -1)

    # =========================================================================
    # CLOSE-ON-TIME SCHEDULE MANAGEMENT
    # =========================================================================

    def create_close_schedule(
        self,
        loan_id: int,
        target_close_date: date,
        contract_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Create a Close-On-Time schedule for a loan."""
        # Check if schedule already exists
        existing = self.db.query(CloseOnTimeSchedule).filter(
            CloseOnTimeSchedule.loan_id == loan_id
        ).first()

        if existing:
            # Update existing
            existing.target_close_date = target_close_date
            existing.contract_date = contract_date
            existing.business_days_remaining = self.get_business_days_until(target_close_date)
            self.db.commit()
            schedule = existing
        else:
            schedule = CloseOnTimeSchedule(
                loan_id=loan_id,
                target_close_date=target_close_date,
                contract_date=contract_date or date.today(),
                business_days_remaining=self.get_business_days_until(target_close_date),
                is_on_track=True,
            )
            self.db.add(schedule)
            self.db.commit()
            self.db.refresh(schedule)

        # Generate milestone deadlines
        self._generate_milestone_deadlines(schedule)

        logger.info(f"Created Close-On-Time schedule for loan {loan_id}, close date: {target_close_date}")

        return {
            "schedule_id": schedule.id,
            "loan_id": loan_id,
            "target_close_date": target_close_date.isoformat(),
            "business_days_remaining": schedule.business_days_remaining,
        }

    def get_close_schedule(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Get Close-On-Time schedule for a loan."""
        schedule = self.db.query(CloseOnTimeSchedule).filter(
            CloseOnTimeSchedule.loan_id == loan_id
        ).first()

        if not schedule:
            return None

        # Update business days remaining
        schedule.business_days_remaining = self.get_business_days_until(schedule.target_close_date)
        self.db.commit()

        # Get milestones
        milestones = self.db.query(CloseOnTimeMilestone).filter(
            CloseOnTimeMilestone.schedule_id == schedule.id
        ).order_by(CloseOnTimeMilestone.deadline_date).all()

        return {
            "id": schedule.id,
            "loan_id": loan_id,
            "target_close_date": schedule.target_close_date.isoformat(),
            "contract_date": schedule.contract_date.isoformat() if schedule.contract_date else None,
            "business_days_remaining": schedule.business_days_remaining,
            "calendar_days_remaining": (schedule.target_close_date - date.today()).days,
            "is_on_track": schedule.is_on_track,
            "risk_level": schedule.risk_level,
            "milestones": [
                {
                    "id": m.id,
                    "name": m.milestone_name,
                    "deadline_date": m.deadline_date.isoformat(),
                    "business_days_before_close": m.business_days_before_close,
                    "is_completed": m.is_completed,
                    "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                    "is_overdue": not m.is_completed and m.deadline_date < date.today(),
                }
                for m in milestones
            ],
        }

    def update_schedule_tracking(self, loan_id: int) -> Dict[str, Any]:
        """Update tracking status for a Close-On-Time schedule."""
        schedule = self.db.query(CloseOnTimeSchedule).filter(
            CloseOnTimeSchedule.loan_id == loan_id
        ).first()

        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        # Update business days
        schedule.business_days_remaining = self.get_business_days_until(schedule.target_close_date)

        # Check for overdue milestones
        overdue_milestones = self.db.query(CloseOnTimeMilestone).filter(
            and_(
                CloseOnTimeMilestone.schedule_id == schedule.id,
                CloseOnTimeMilestone.is_completed == False,
                CloseOnTimeMilestone.deadline_date < date.today()
            )
        ).count()

        # Determine risk level
        if overdue_milestones >= 3:
            schedule.risk_level = "critical"
            schedule.is_on_track = False
        elif overdue_milestones >= 1:
            schedule.risk_level = "warning"
            schedule.is_on_track = False
        elif schedule.business_days_remaining <= 5:
            schedule.risk_level = "attention"
            schedule.is_on_track = True
        else:
            schedule.risk_level = "on_track"
            schedule.is_on_track = True

        self.db.commit()

        return {
            "success": True,
            "business_days_remaining": schedule.business_days_remaining,
            "is_on_track": schedule.is_on_track,
            "risk_level": schedule.risk_level,
            "overdue_milestones": overdue_milestones,
        }

    def complete_schedule_milestone(
        self,
        milestone_id: int,
        completed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark a Close-On-Time milestone as completed."""
        milestone = self.db.query(CloseOnTimeMilestone).filter(
            CloseOnTimeMilestone.id == milestone_id
        ).first()

        if not milestone:
            return {"success": False, "error": "Milestone not found"}

        milestone.is_completed = True
        milestone.completed_at = datetime.now(timezone.utc)
        milestone.completed_by = completed_by

        self.db.commit()

        # Update schedule tracking
        self.update_schedule_tracking(milestone.schedule.loan_id)

        return {
            "success": True,
            "milestone_name": milestone.milestone_name,
            "completed_at": milestone.completed_at.isoformat(),
        }

    # =========================================================================
    # COUNTDOWN & DISPLAY DATA
    # =========================================================================

    def get_countdown_data(self, loan_id: int) -> Dict[str, Any]:
        """Get countdown display data for a loan."""
        schedule = self.get_close_schedule(loan_id)

        if not schedule:
            return {
                "has_schedule": False,
                "message": "No closing date scheduled",
            }

        target_date = datetime.strptime(schedule["target_close_date"], "%Y-%m-%d").date()
        business_days = schedule["business_days_remaining"]
        calendar_days = schedule["calendar_days_remaining"]

        # Determine urgency level
        if business_days <= 0:
            urgency = "overdue"
            urgency_message = "Closing date has passed"
        elif business_days <= 3:
            urgency = "critical"
            urgency_message = "Closing imminent"
        elif business_days <= 7:
            urgency = "warning"
            urgency_message = "Final week"
        elif business_days <= 14:
            urgency = "attention"
            urgency_message = "Two weeks remaining"
        else:
            urgency = "normal"
            urgency_message = "On track"

        # Get upcoming deadlines
        upcoming_deadlines = [
            m for m in schedule["milestones"]
            if not m["is_completed"] and not m["is_overdue"]
        ][:3]

        return {
            "has_schedule": True,
            "target_close_date": schedule["target_close_date"],
            "target_close_date_formatted": target_date.strftime("%B %d, %Y"),
            "target_close_day": target_date.strftime("%A"),
            "business_days_remaining": business_days,
            "calendar_days_remaining": calendar_days,
            "urgency": urgency,
            "urgency_message": urgency_message,
            "is_on_track": schedule["is_on_track"],
            "risk_level": schedule["risk_level"],
            "upcoming_deadlines": upcoming_deadlines,
            "overdue_count": len([m for m in schedule["milestones"] if m["is_overdue"]]),
        }

    def get_calendar_view(
        self,
        loan_id: int,
        start_date: Optional[date] = None,
        weeks: int = 6,
    ) -> Dict[str, Any]:
        """Get calendar view data for Close-On-Time display."""
        if not start_date:
            start_date = date.today()

        # Start from beginning of week
        start_date = start_date - timedelta(days=start_date.weekday())
        end_date = start_date + timedelta(weeks=weeks)

        schedule = self.db.query(CloseOnTimeSchedule).filter(
            CloseOnTimeSchedule.loan_id == loan_id
        ).first()

        # Build calendar days
        calendar_days = []
        current = start_date

        while current < end_date:
            day_data = {
                "date": current.isoformat(),
                "day": current.day,
                "is_today": current == date.today(),
                "is_weekend": current.weekday() >= 5,
                "is_holiday": False,
                "holiday_name": None,
                "is_business_day": self.is_business_day(current),
                "is_close_date": False,
                "milestones": [],
            }

            # Check for holiday
            holiday_name = self.is_holiday(current)
            if holiday_name:
                day_data["is_holiday"] = True
                day_data["holiday_name"] = holiday_name

            # Check for close date
            if schedule and current == schedule.target_close_date:
                day_data["is_close_date"] = True

            # Check for milestone deadlines
            if schedule:
                milestones = self.db.query(CloseOnTimeMilestone).filter(
                    and_(
                        CloseOnTimeMilestone.schedule_id == schedule.id,
                        CloseOnTimeMilestone.deadline_date == current
                    )
                ).all()
                day_data["milestones"] = [
                    {"name": m.milestone_name, "completed": m.is_completed}
                    for m in milestones
                ]

            calendar_days.append(day_data)
            current += timedelta(days=1)

        # Group by week
        weeks_data = []
        for i in range(0, len(calendar_days), 7):
            weeks_data.append(calendar_days[i:i+7])

        return {
            "loan_id": loan_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weeks": weeks_data,
            "target_close_date": schedule.target_close_date.isoformat() if schedule else None,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_nth_weekday(self, year: int, month: int, weekday: int, n: int) -> date:
        """Get the nth occurrence of a weekday in a month."""
        # weekday: 0=Monday, 3=Thursday, etc.
        first_day = date(year, month, 1)
        first_weekday = first_day + timedelta(days=(weekday - first_day.weekday() + 7) % 7)
        return first_weekday + timedelta(weeks=n-1)

    def _get_last_weekday(self, year: int, month: int, weekday: int) -> date:
        """Get the last occurrence of a weekday in a month."""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        days_since_weekday = (last_day.weekday() - weekday + 7) % 7
        return last_day - timedelta(days=days_since_weekday)

    def _adjust_for_weekend(self, holiday_date: date) -> date:
        """Adjust holiday date for weekend observance."""
        if holiday_date.weekday() == 5:  # Saturday
            return holiday_date - timedelta(days=1)  # Observe Friday
        elif holiday_date.weekday() == 6:  # Sunday
            return holiday_date + timedelta(days=1)  # Observe Monday
        return holiday_date

    def _generate_milestone_deadlines(self, schedule: CloseOnTimeSchedule) -> None:
        """Generate standard milestone deadlines for a Close-On-Time schedule."""
        # Standard milestones with business days before close
        standard_milestones = [
            ("Appraisal Ordered", 25),
            ("Appraisal Received", 18),
            ("Underwriting Submitted", 15),
            ("Conditional Approval", 12),
            ("Final Conditions Cleared", 8),
            ("Clear to Close", 5),
            ("Closing Disclosure Sent", 3),
            ("Final Walkthrough", 1),
            ("Closing Day", 0),
        ]

        # Delete existing milestones
        self.db.query(CloseOnTimeMilestone).filter(
            CloseOnTimeMilestone.schedule_id == schedule.id
        ).delete()

        # Create new milestones
        for name, days_before in standard_milestones:
            deadline = self.add_business_days(schedule.target_close_date, -days_before)

            milestone = CloseOnTimeMilestone(
                schedule_id=schedule.id,
                milestone_name=name,
                deadline_date=deadline,
                business_days_before_close=days_before,
                is_completed=False,
            )
            self.db.add(milestone)

        self.db.commit()
