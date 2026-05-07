"""
TRID Deadline Scheduling Service

Auto-calculates Loan Estimate (LE) and Closing Disclosure (CD) deadlines
with business-day awareness (excludes weekends and federal holidays).

TRID Rules (12 CFR 1026.19):
    - Loan Estimate: Must be delivered within 3 business days of application
    - Closing Disclosure: Must be delivered at least 3 business days before
      consummation (closing)

Business day definition for TRID purposes:
    All calendar days except Sundays and federal holidays (for LE delivery).
    For CD waiting period: all calendar days except Sundays and federal holidays.
    NOTE: Saturday IS a business day for TRID disclosure delivery/waiting
    period calculations under Regulation Z, EXCEPT for the "3 business day"
    application-to-LE rule which uses the general definition (Mon-Sat minus
    federal holidays). This implementation uses the general definition for
    both to be conservative.

Usage:
    from services.trid_deadline_service import TRIDDeadlineService

    service = TRIDDeadlineService()
    le_deadline = service.calculate_le_deadline(application_date)
    cd_deadline = service.calculate_cd_deadline(closing_date)
    alerts = service.check_trid_deadlines(db, org_id)
"""

import logging
from datetime import date, timedelta
from typing import List, Optional, Set

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Federal Holiday Calendar
# =============================================================================

def get_federal_holidays(year: int) -> Set[date]:
    """Return the set of observed federal holidays for a given year.

    Covers all 11 federally recognized holidays. When a holiday falls
    on Saturday it is observed on Friday; on Sunday, on Monday.

    Reference: 5 U.S.C. 6103
    """
    holidays: Set[date] = set()

    # New Year's Day — January 1
    holidays.add(_observed(date(year, 1, 1)))

    # Martin Luther King Jr. Day — 3rd Monday in January
    holidays.add(_nth_weekday(year, 1, 0, 3))  # 0 = Monday

    # Presidents' Day — 3rd Monday in February
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Memorial Day — Last Monday in May
    holidays.add(_last_weekday(year, 5, 0))

    # Juneteenth — June 19
    holidays.add(_observed(date(year, 6, 19)))

    # Independence Day — July 4
    holidays.add(_observed(date(year, 7, 4)))

    # Labor Day — 1st Monday in September
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Columbus Day — 2nd Monday in October
    holidays.add(_nth_weekday(year, 10, 0, 2))

    # Veterans Day — November 11
    holidays.add(_observed(date(year, 11, 11)))

    # Thanksgiving Day — 4th Thursday in November
    holidays.add(_nth_weekday(year, 11, 3, 4))  # 3 = Thursday

    # Christmas Day — December 25
    holidays.add(_observed(date(year, 12, 25)))

    return holidays


def _observed(d: date) -> date:
    """Shift a fixed-date holiday to its observed date.

    Saturday -> Friday, Sunday -> Monday.
    """
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a month.

    weekday: 0=Monday ... 6=Sunday
    n: 1-based (1st, 2nd, 3rd, etc.)
    """
    first_day = date(year, month, 1)
    # Days until the target weekday from the 1st
    days_ahead = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a month."""
    # Start from the last day of the month
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    days_behind = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_behind)


# =============================================================================
# Business Day Arithmetic
# =============================================================================

def _is_business_day(d: date, holidays: Set[date]) -> bool:
    """Check if a date is a business day (not Sunday, not federal holiday).

    NOTE: For TRID, Saturday is a business day. Only Sundays and federal
    holidays are excluded from the business-day count.
    """
    if d.weekday() == 6:  # Sunday
        return False
    if d in holidays:
        return False
    return True


def add_business_days(start: date, days: int) -> date:
    """Add N business days to a start date (exclusive of start).

    Returns the date that is exactly `days` business days after `start`.
    Used for LE deadline: 3 business days AFTER application date.
    """
    if days < 0:
        raise ValueError("days must be non-negative; use subtract_business_days for backward counting")

    # Collect holidays for the years we might traverse
    holidays = get_federal_holidays(start.year) | get_federal_holidays(start.year + 1)

    current = start
    counted = 0
    while counted < days:
        current += timedelta(days=1)
        if _is_business_day(current, holidays):
            counted += 1
        # Extend holiday set if we rolled into a new year
        if current.year > start.year + 1:
            holidays |= get_federal_holidays(current.year)

    return current


def subtract_business_days(start: date, days: int) -> date:
    """Subtract N business days from a start date (exclusive of start).

    Returns the date that is exactly `days` business days before `start`.
    Used for CD deadline: 3 business days BEFORE closing date.
    """
    if days < 0:
        raise ValueError("days must be non-negative; use add_business_days for forward counting")

    holidays = get_federal_holidays(start.year) | get_federal_holidays(start.year - 1)

    current = start
    counted = 0
    while counted < days:
        current -= timedelta(days=1)
        if _is_business_day(current, holidays):
            counted += 1
        if current.year < start.year - 1:
            holidays |= get_federal_holidays(current.year)

    return current


# =============================================================================
# TRID Deadline Calculations
# =============================================================================

def calculate_le_deadline(application_date: date) -> date:
    """Calculate the Loan Estimate delivery deadline.

    TRID requires the initial LE to be delivered within 3 business days
    of receiving the borrower's application (the 6-piece trigger).

    Args:
        application_date: The date the application was received.

    Returns:
        The last business day by which the LE must be delivered.
    """
    return add_business_days(application_date, 3)


def calculate_cd_deadline(closing_date: date) -> date:
    """Calculate the Closing Disclosure delivery deadline.

    TRID requires the CD to be received by the borrower at least 3
    business days before consummation (closing).

    Args:
        closing_date: The scheduled closing/consummation date.

    Returns:
        The last business day by which the CD must be delivered.
    """
    return subtract_business_days(closing_date, 3)


# =============================================================================
# Pipeline Deadline Scanner
# =============================================================================

class TRIDDeadlineService:
    """Scans active loans for approaching or overdue TRID deadlines."""

    # Stages that are terminal — no TRID tracking needed
    TERMINAL_STAGES = frozenset({
        "FUNDED", "CANCELLED", "DENIED", "DEAD",
        "WITHDRAWN", "DOES_NOT_QUALIFY",
    })

    def check_trid_deadlines(
        self,
        db: Session,
        org_id: int,
        lookahead_days: int = 7,
    ) -> List[dict]:
        """Scan all active loans for approaching or overdue TRID deadlines.

        Returns a list of deadline alert dicts sorted by urgency (overdue
        first, then by days remaining ascending).

        Args:
            db: Database session (RLS-scoped).
            org_id: Organization to scan.
            lookahead_days: How far ahead to look for upcoming deadlines.

        Returns:
            List of dicts with keys: loan_id, loan_number, borrower_name,
            deadline_type, deadline_date, days_remaining, severity, status,
            disclosure_sent, stage.
        """
        from database.models.lead_loan import Loan
        from database.models.compliance import DisclosureEvent, DisclosureType

        today = date.today()

        # Fetch all active (non-terminal) loans for the org
        loans = (
            db.query(Loan)
            .filter(
                Loan.organization_id == org_id,
                Loan.stage.notin_(list(self.TERMINAL_STAGES)),
            )
            .all()
        )

        alerts: List[dict] = []

        for loan in loans:
            # --- LE Deadline ---
            app_date = self._to_date(loan.application_date)
            if app_date:
                le_deadline = calculate_le_deadline(app_date)

                # Check if LE was already sent
                le_sent = self._disclosure_sent(
                    db, loan.id, DisclosureType.LOAN_ESTIMATE,
                )
                le_sent_date = self._disclosure_sent_date(
                    db, loan.id, DisclosureType.LOAN_ESTIMATE,
                )

                # Also check the loan model field as fallback
                if not le_sent and loan.initial_disclosures_sent_date:
                    le_sent = True
                    le_sent_date = self._to_date(loan.initial_disclosures_sent_date)

                days_remaining = (le_deadline - today).days

                # Only alert if LE not yet sent and deadline is within window
                if not le_sent and days_remaining <= lookahead_days:
                    severity = self._severity(days_remaining)
                    alerts.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "deadline_type": "loan_estimate",
                        "deadline_date": le_deadline.isoformat(),
                        "application_date": app_date.isoformat(),
                        "days_remaining": days_remaining,
                        "severity": severity,
                        "status": "overdue" if days_remaining < 0 else "approaching",
                        "disclosure_sent": False,
                        "stage": loan.stage,
                    })
                elif le_sent:
                    # Include sent LE info for completeness (no alert)
                    was_on_time = le_sent_date <= le_deadline if le_sent_date else None
                    if le_sent_date and not was_on_time:
                        alerts.append({
                            "loan_id": loan.id,
                            "loan_number": loan.loan_number,
                            "borrower_name": loan.borrower_name,
                            "deadline_type": "loan_estimate",
                            "deadline_date": le_deadline.isoformat(),
                            "application_date": app_date.isoformat(),
                            "days_remaining": days_remaining,
                            "severity": "critical",
                            "status": "violation",
                            "disclosure_sent": True,
                            "disclosure_sent_date": le_sent_date.isoformat() if le_sent_date else None,
                            "was_on_time": False,
                            "stage": loan.stage,
                        })

            # --- CD Deadline ---
            closing = self._to_date(
                loan.scheduled_closing_date or loan.closing_date
            )
            if closing:
                cd_deadline = calculate_cd_deadline(closing)
                cd_sent = self._disclosure_sent(
                    db, loan.id, DisclosureType.CLOSING_DISCLOSURE,
                )
                cd_sent_date = self._disclosure_sent_date(
                    db, loan.id, DisclosureType.CLOSING_DISCLOSURE,
                )

                # Fallback to loan model field
                if not cd_sent and loan.cd_sent_to_borrower_date:
                    cd_sent = True
                    cd_sent_date = self._to_date(loan.cd_sent_to_borrower_date)

                days_remaining = (cd_deadline - today).days

                if not cd_sent and days_remaining <= lookahead_days:
                    severity = self._severity(days_remaining)
                    alerts.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "deadline_type": "closing_disclosure",
                        "deadline_date": cd_deadline.isoformat(),
                        "closing_date": closing.isoformat(),
                        "days_remaining": days_remaining,
                        "severity": severity,
                        "status": "overdue" if days_remaining < 0 else "approaching",
                        "disclosure_sent": False,
                        "stage": loan.stage,
                    })
                elif cd_sent:
                    was_on_time = cd_sent_date <= cd_deadline if cd_sent_date else None
                    if cd_sent_date and not was_on_time:
                        alerts.append({
                            "loan_id": loan.id,
                            "loan_number": loan.loan_number,
                            "borrower_name": loan.borrower_name,
                            "deadline_type": "closing_disclosure",
                            "deadline_date": cd_deadline.isoformat(),
                            "closing_date": closing.isoformat(),
                            "days_remaining": days_remaining,
                            "severity": "critical",
                            "status": "violation",
                            "disclosure_sent": True,
                            "disclosure_sent_date": cd_sent_date.isoformat() if cd_sent_date else None,
                            "was_on_time": False,
                            "stage": loan.stage,
                        })

        # Sort: overdue first, then by days_remaining ascending
        alerts.sort(key=lambda a: (
            0 if a["status"] == "violation" else (1 if a["status"] == "overdue" else 2),
            a["days_remaining"],
        ))

        return alerts

    def get_loan_deadlines(
        self,
        db: Session,
        loan_id: int,
        org_id: int,
    ) -> Optional[dict]:
        """Get TRID deadline details for a specific loan.

        Returns:
            Dict with le_deadline, cd_deadline, disclosure history,
            and compliance status. None if loan not found.
        """
        from database.models.lead_loan import Loan
        from database.models.compliance import DisclosureEvent, DisclosureType

        loan = (
            db.query(Loan)
            .filter(Loan.id == loan_id, Loan.organization_id == org_id)
            .first()
        )
        if not loan:
            return None

        today = date.today()
        result: dict = {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "stage": loan.stage,
            "le": None,
            "cd": None,
            "disclosure_history": [],
        }

        # --- LE ---
        app_date = self._to_date(loan.application_date)
        if app_date:
            le_deadline = calculate_le_deadline(app_date)
            le_sent = self._disclosure_sent(db, loan.id, DisclosureType.LOAN_ESTIMATE)
            le_sent_date = self._disclosure_sent_date(db, loan.id, DisclosureType.LOAN_ESTIMATE)
            if not le_sent and loan.initial_disclosures_sent_date:
                le_sent = True
                le_sent_date = self._to_date(loan.initial_disclosures_sent_date)

            days_remaining = (le_deadline - today).days
            was_on_time = le_sent_date <= le_deadline if le_sent and le_sent_date else None

            result["le"] = {
                "application_date": app_date.isoformat(),
                "deadline_date": le_deadline.isoformat(),
                "days_remaining": days_remaining,
                "disclosure_sent": le_sent,
                "disclosure_sent_date": le_sent_date.isoformat() if le_sent_date else None,
                "was_on_time": was_on_time,
                "status": self._deadline_status(days_remaining, le_sent, was_on_time),
            }

        # --- CD ---
        closing = self._to_date(loan.scheduled_closing_date or loan.closing_date)
        if closing:
            cd_deadline = calculate_cd_deadline(closing)
            cd_sent = self._disclosure_sent(db, loan.id, DisclosureType.CLOSING_DISCLOSURE)
            cd_sent_date = self._disclosure_sent_date(db, loan.id, DisclosureType.CLOSING_DISCLOSURE)
            if not cd_sent and loan.cd_sent_to_borrower_date:
                cd_sent = True
                cd_sent_date = self._to_date(loan.cd_sent_to_borrower_date)

            days_remaining = (cd_deadline - today).days
            was_on_time = cd_sent_date <= cd_deadline if cd_sent and cd_sent_date else None

            result["cd"] = {
                "closing_date": closing.isoformat(),
                "deadline_date": cd_deadline.isoformat(),
                "days_remaining": days_remaining,
                "disclosure_sent": cd_sent,
                "disclosure_sent_date": cd_sent_date.isoformat() if cd_sent_date else None,
                "was_on_time": was_on_time,
                "status": self._deadline_status(days_remaining, cd_sent, was_on_time),
            }

        # Disclosure event history from the audit table
        events = (
            db.query(DisclosureEvent)
            .filter(DisclosureEvent.loan_id == loan_id)
            .order_by(DisclosureEvent.created_at.desc())
            .all()
        )
        result["disclosure_history"] = [
            {
                "id": e.id,
                "type": e.disclosure_type.value if hasattr(e.disclosure_type, "value") else e.disclosure_type,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "delivery_method": e.delivery_method,
                "is_on_time": e.is_on_time,
                "change_reason": e.change_reason,
            }
            for e in events
        ]

        return result

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_date(dt) -> Optional[date]:
        """Convert a datetime or date to a date object."""
        if dt is None:
            return None
        if isinstance(dt, date) and not hasattr(dt, "hour"):
            return dt
        if hasattr(dt, "date"):
            return dt.date()
        return None

    @staticmethod
    def _severity(days_remaining: int) -> str:
        """Map days remaining to severity level."""
        if days_remaining < 0:
            return "critical"  # Overdue
        if days_remaining == 0:
            return "critical"  # Due today
        if days_remaining <= 1:
            return "high"
        if days_remaining <= 3:
            return "medium"
        return "low"

    @staticmethod
    def _deadline_status(days_remaining: int, sent: bool, was_on_time: Optional[bool]) -> str:
        """Determine the deadline status string."""
        if sent and was_on_time is True:
            return "compliant"
        if sent and was_on_time is False:
            return "violation"
        if sent:
            return "sent"  # Sent but can't determine timeliness
        if days_remaining < 0:
            return "overdue"
        if days_remaining <= 1:
            return "urgent"
        if days_remaining <= 3:
            return "approaching"
        return "on_track"

    @staticmethod
    def _disclosure_sent(
        db: Session, loan_id: int, disclosure_type
    ) -> bool:
        """Check if a disclosure of the given type has been sent."""
        from database.models.compliance import DisclosureEvent

        return (
            db.query(DisclosureEvent)
            .filter(
                DisclosureEvent.loan_id == loan_id,
                DisclosureEvent.disclosure_type == disclosure_type,
                DisclosureEvent.sent_at.isnot(None),
            )
            .first()
        ) is not None

    @staticmethod
    def _disclosure_sent_date(
        db: Session, loan_id: int, disclosure_type
    ) -> Optional[date]:
        """Get the date a disclosure was sent (earliest send)."""
        from database.models.compliance import DisclosureEvent

        event = (
            db.query(DisclosureEvent)
            .filter(
                DisclosureEvent.loan_id == loan_id,
                DisclosureEvent.disclosure_type == disclosure_type,
                DisclosureEvent.sent_at.isnot(None),
            )
            .order_by(DisclosureEvent.sent_at.asc())
            .first()
        )
        if event and event.sent_at:
            if hasattr(event.sent_at, "date"):
                return event.sent_at.date()
            return event.sent_at
        return None
