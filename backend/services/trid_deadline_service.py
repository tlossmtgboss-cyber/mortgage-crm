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
# TRID Fee Tolerance Categories — 12 CFR 1026.19(e)(3)
# =============================================================================

# Zero-tolerance fees: Fees that cannot increase from the Loan Estimate to the
# Closing Disclosure.  12 CFR 1026.19(e)(3)(i).
_ZERO_TOLERANCE_FEES = frozenset({
    # Lender/broker charges
    "origination_fee",
    "origination_charge",
    "discount_points",
    "discount_fee",
    "processing_fee",
    "underwriting_fee",
    "application_fee",
    "commitment_fee",
    "rate_lock_fee",
    "lender_credits",
    "broker_fee",
    "admin_fee",
    "administration_fee",
    "wire_transfer_fee",
    "document_preparation_fee",
    "doc_prep_fee",
    # Transfer taxes (not affected by 10% aggregate rule)
    "transfer_tax",
    "transfer_taxes",
    "mortgage_tax",
    "deed_tax",
    "state_transfer_tax",
    "county_transfer_tax",
    "intangible_tax",
    # Services where lender selected the provider & borrower cannot shop
    # (when the provider is on the lender's "written list" and borrower did NOT shop)
    # These are zero-tolerance when borrower uses lender's chosen provider.
    # NOTE: if borrower shops and selects their own provider, these move to
    # unlimited tolerance.  The default classification here assumes lender-selected.
})

# Ten-percent aggregate tolerance fees: Fees that can increase, but the total
# of all 10%-bucket fees cannot increase by more than 10% in aggregate.
# 12 CFR 1026.19(e)(3)(ii).
_TEN_PERCENT_FEES = frozenset({
    # Third-party services the borrower CAN shop for (from lender's Written
    # List of Service Providers) but did NOT shop independently.
    "appraisal_fee",
    "appraisal",
    "credit_report_fee",
    "credit_report",
    "flood_certification_fee",
    "flood_cert",
    "flood_determination_fee",
    "tax_service_fee",
    "tax_certification_fee",
    "title_search_fee",
    "title_search",
    "title_examination_fee",
    "lenders_title_insurance",
    "lender_title_insurance",
    "title_insurance_lender",
    "title_lender_coverage",
    "pest_inspection_fee",
    "pest_inspection",
    "survey_fee",
    "survey",
    "settlement_fee",
    "settlement_agent_fee",
    "closing_fee",
    "escrow_fee",
    "notary_fee",
    "attorney_fee",
    "attorney_fees",
    "title_abstract_fee",
    "title_endorsement_fee",
    "courier_fee",
    "credit_supplement_fee",
})

# Unlimited tolerance fees: Fees that can increase without limit.
# 12 CFR 1026.19(e)(3)(iii) — includes:
#   - Prepaid interest, property insurance premiums, escrowed amounts
#   - Services borrower shopped for and selected their own provider
#   - Charges paid to unaffiliated third-party not on lender list
_UNLIMITED_TOLERANCE_FEES = frozenset({
    "prepaid_interest",
    "daily_interest",
    "per_diem_interest",
    "homeowners_insurance",
    "homeowner_insurance_premium",
    "hazard_insurance",
    "property_insurance",
    "flood_insurance",
    "flood_insurance_premium",
    "mortgage_insurance",
    "mortgage_insurance_premium",
    "pmi",
    "mip",
    "fha_mip",
    "va_funding_fee",
    "usda_guarantee_fee",
    "property_tax",
    "property_taxes",
    "real_estate_tax",
    "county_tax",
    "city_tax",
    "school_tax",
    "tax_escrow",
    "insurance_escrow",
    "escrow_deposit",
    "aggregate_escrow_adjustment",
    "hoa_dues",
    "homeowners_association_dues",
    "owners_title_insurance",
    "owner_title_insurance",
    "title_insurance_owner",
    "title_owner_coverage",
    "recording_fees",
    "recording_fee",
    "recording_charges",
    "government_recording_charges",
    "municipal_lien_search",
    "home_inspection_fee",
    "home_inspection",
    "home_warranty",
    "home_warranty_fee",
    "radon_test_fee",
    "well_test_fee",
    "septic_test_fee",
    "condo_questionnaire_fee",
    "hoa_certification_fee",
})


def classify_fee_tolerance(fee_type: str) -> str:
    """Classify a mortgage fee into its TRID tolerance category.

    Per 12 CFR 1026.19(e)(3), fees on the Loan Estimate fall into one of
    three tolerance buckets that govern how much the fee can increase
    between the LE and the Closing Disclosure:

      - **zero_tolerance**: Fee cannot increase at all.
      - **ten_percent**: Fee can increase, but the aggregate of all
        10%-bucket fees cannot exceed 10% of the original LE total for
        that bucket.
      - **unlimited**: Fee can increase without limit.

    Args:
        fee_type: A snake_case identifier for the fee (e.g.
            "appraisal_fee", "origination_fee", "recording_fees").

    Returns:
        One of "zero_tolerance", "ten_percent", or "unlimited".
        Defaults to "unlimited" for unrecognised fee types (safest
        assumption per TRID -- the creditor can cure a tolerance
        violation only if they refund the excess, so defaulting to
        "unlimited" avoids false compliance violations).
    """
    normalised = fee_type.strip().lower().replace(" ", "_").replace("-", "_")

    if normalised in _ZERO_TOLERANCE_FEES:
        return "zero_tolerance"
    if normalised in _TEN_PERCENT_FEES:
        return "ten_percent"
    if normalised in _UNLIMITED_TOLERANCE_FEES:
        return "unlimited"

    # Heuristic fallback: check partial matches for common patterns
    if any(z in normalised for z in ("origination", "discount_point", "lender_credit", "broker")):
        return "zero_tolerance"
    if "transfer_tax" in normalised or "deed_tax" in normalised or "intangible_tax" in normalised:
        return "zero_tolerance"
    if any(t in normalised for t in ("title_search", "title_exam", "lender_title", "title_lender")):
        return "ten_percent"
    if any(t in normalised for t in ("appraisal", "credit_report", "flood_cert", "tax_service")):
        return "ten_percent"
    if any(u in normalised for u in ("insurance", "escrow", "prepaid", "recording", "property_tax")):
        return "unlimited"

    # Default to unlimited for unknown fee types (conservative — avoids
    # false positives on tolerance violation checks)
    logger.debug("classify_fee_tolerance: unknown fee_type '%s', defaulting to unlimited", fee_type)
    return "unlimited"


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
