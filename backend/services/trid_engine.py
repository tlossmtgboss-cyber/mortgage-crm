"""
TRID Compliance Engine

Implements automated TILA-RESPA Integrated Disclosure (TRID) compliance
checking for mortgage loans. Covers enterprise readiness checks 2.1-2.6.

Key regulations enforced:
    - 12 CFR 1026.19(e)(1)(iii): LE must be delivered within 3 business days
      of receiving an application
    - 12 CFR 1026.19(f)(1)(ii): CD must be provided at least 3 business days
      before consummation
    - 12 CFR 1026.19(e)(3): Fee tolerance categories (zero, 10%, unlimited)
    - 12 CFR 1026.19(e)(4): Changed circumstance documentation requirements

Usage:
    from services.trid_engine import check_loan_trid_compliance

    result = check_loan_trid_compliance(db, loan_id)
    # Returns dict with compliance status, issues, and alerts
"""

import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_

logger = logging.getLogger(__name__)


# ============================================================================
# Federal Holidays (US) for business day calculation
# ============================================================================

def _get_federal_holidays(year: int) -> set:
    """Get federal holidays for a given year.

    Returns a set of date objects for all federal holidays observed in the
    given year. Used to exclude non-business days from TRID deadline
    calculations.

    Note: Holidays that fall on weekends are observed on the nearest weekday
    (Saturday holidays observed Friday, Sunday holidays observed Monday).
    """
    holidays = set()

    # New Year's Day - January 1
    holidays.add(date(year, 1, 1))

    # MLK Day - Third Monday of January
    jan_first = date(year, 1, 1)
    # Find first Monday
    days_to_monday = (7 - jan_first.weekday()) % 7
    if jan_first.weekday() == 0:
        days_to_monday = 0
    first_monday = jan_first + timedelta(days=days_to_monday)
    holidays.add(first_monday + timedelta(weeks=2))

    # Presidents Day - Third Monday of February
    feb_first = date(year, 2, 1)
    days_to_monday = (7 - feb_first.weekday()) % 7
    if feb_first.weekday() == 0:
        days_to_monday = 0
    first_monday = feb_first + timedelta(days=days_to_monday)
    holidays.add(first_monday + timedelta(weeks=2))

    # Memorial Day - Last Monday of May
    may_last = date(year, 5, 31)
    days_back = (may_last.weekday() - 0) % 7  # 0 = Monday
    holidays.add(may_last - timedelta(days=days_back))

    # Juneteenth - June 19
    holidays.add(date(year, 6, 19))

    # Independence Day - July 4
    holidays.add(date(year, 7, 4))

    # Labor Day - First Monday of September
    sep_first = date(year, 9, 1)
    days_to_monday = (7 - sep_first.weekday()) % 7
    if sep_first.weekday() == 0:
        days_to_monday = 0
    holidays.add(sep_first + timedelta(days=days_to_monday))

    # Columbus Day - Second Monday of October
    oct_first = date(year, 10, 1)
    days_to_monday = (7 - oct_first.weekday()) % 7
    if oct_first.weekday() == 0:
        days_to_monday = 0
    first_monday = oct_first + timedelta(days=days_to_monday)
    holidays.add(first_monday + timedelta(weeks=1))

    # Veterans Day - November 11
    holidays.add(date(year, 11, 11))

    # Thanksgiving - Fourth Thursday of November
    nov_first = date(year, 11, 1)
    days_to_thurs = (3 - nov_first.weekday()) % 7
    first_thurs = nov_first + timedelta(days=days_to_thurs)
    holidays.add(first_thurs + timedelta(weeks=3))

    # Christmas Day - December 25
    holidays.add(date(year, 12, 25))

    # Adjust weekend holidays to observed date
    adjusted = set()
    for h in holidays:
        if h.weekday() == 5:  # Saturday -> Friday
            adjusted.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday -> Monday
            adjusted.add(h + timedelta(days=1))
        else:
            adjusted.add(h)

    return adjusted


def _is_business_day(d: date) -> bool:
    """Check if a date is a business day (not weekend, not federal holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    holidays = _get_federal_holidays(d.year)
    return d not in holidays


def add_business_days(start: date, num_days: int) -> date:
    """Add N business days to a date (excludes weekends and federal holidays).

    Args:
        start: Starting date
        num_days: Number of business days to add (positive = forward)

    Returns:
        The date that is num_days business days after start
    """
    current = start
    added = 0
    while added < num_days:
        current += timedelta(days=1)
        if _is_business_day(current):
            added += 1
    return current


def subtract_business_days(end: date, num_days: int) -> date:
    """Subtract N business days from a date (excludes weekends and federal holidays).

    Args:
        end: Ending date
        num_days: Number of business days to subtract

    Returns:
        The date that is num_days business days before end
    """
    current = end
    subtracted = 0
    while subtracted < num_days:
        current -= timedelta(days=1)
        if _is_business_day(current):
            subtracted += 1
    return current


def count_business_days(start: date, end: date) -> int:
    """Count business days between two dates (exclusive of start, inclusive of end).

    Args:
        start: Start date (not counted)
        end: End date (counted if business day)

    Returns:
        Number of business days between the dates
    """
    if end <= start:
        return 0
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if _is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count


# ============================================================================
# TRID Compliance Checks
# ============================================================================

def _check_le_deadline(
    application_date: Optional[date],
    le_sent_date: Optional[date],
    today: date,
) -> List[Dict[str, Any]]:
    """Check Loan Estimate delivery deadline (3 business days from application).

    Per 12 CFR 1026.19(e)(1)(iii), the creditor must deliver or place in
    the mail the Loan Estimate no later than the third business day after
    receiving the consumer's application.

    Returns a list of compliance issue dicts.
    """
    issues = []

    if application_date is None:
        return issues

    # Calculate the LE deadline: 3 business days after application
    le_deadline = add_business_days(application_date, 3)

    if le_sent_date is not None:
        # LE was sent - check if it was on time
        bdays_used = count_business_days(application_date, le_sent_date)
        if bdays_used > 3:
            issues.append({
                "check": "trid_le_timing",
                "severity": "critical",
                "title": "LE delivered late",
                "description": (
                    f"Loan Estimate sent on {le_sent_date.isoformat()} "
                    f"({bdays_used} business days after application on "
                    f"{application_date.isoformat()}). TRID requires delivery "
                    f"within 3 business days. Deadline was {le_deadline.isoformat()}."
                ),
                "deadline": le_deadline.isoformat(),
                "actual_date": le_sent_date.isoformat(),
                "business_days_used": bdays_used,
                "is_violation": True,
            })
    else:
        # LE not yet sent - check if deadline is approaching or past
        bdays_since_app = count_business_days(application_date, today)
        days_remaining = count_business_days(today, le_deadline) if today < le_deadline else 0

        if today > le_deadline:
            issues.append({
                "check": "trid_le_timing",
                "severity": "critical",
                "title": "LE deadline MISSED",
                "description": (
                    f"Loan Estimate has NOT been sent. Application received "
                    f"{application_date.isoformat()}. Deadline was "
                    f"{le_deadline.isoformat()} ({bdays_since_app} business days ago). "
                    f"IMMEDIATE ACTION REQUIRED."
                ),
                "deadline": le_deadline.isoformat(),
                "business_days_elapsed": bdays_since_app,
                "is_violation": True,
            })
        elif days_remaining <= 1:
            issues.append({
                "check": "trid_le_timing",
                "severity": "high",
                "title": "LE deadline imminent",
                "description": (
                    f"Loan Estimate must be delivered by {le_deadline.isoformat()} "
                    f"({days_remaining} business day(s) remaining). Application "
                    f"received {application_date.isoformat()}."
                ),
                "deadline": le_deadline.isoformat(),
                "days_remaining": days_remaining,
                "is_violation": False,
            })

    return issues


def _check_cd_deadline(
    closing_date: Optional[date],
    cd_sent_date: Optional[date],
    today: date,
) -> List[Dict[str, Any]]:
    """Check Closing Disclosure delivery deadline (3 business days before closing).

    Per 12 CFR 1026.19(f)(1)(ii), the creditor must ensure the consumer
    receives the Closing Disclosure no later than 3 business days before
    consummation.

    Returns a list of compliance issue dicts.
    """
    issues = []

    if closing_date is None:
        return issues

    # CD must be received 3 business days before closing
    cd_deadline = subtract_business_days(closing_date, 3)

    if cd_sent_date is not None:
        # CD was sent - check if it was on time
        if cd_sent_date > cd_deadline:
            issues.append({
                "check": "trid_cd_timing",
                "severity": "critical",
                "title": "CD delivered too late",
                "description": (
                    f"Closing Disclosure sent on {cd_sent_date.isoformat()}, "
                    f"but must be received by {cd_deadline.isoformat()} "
                    f"(3 business days before closing on {closing_date.isoformat()}). "
                    f"Closing may need to be rescheduled."
                ),
                "deadline": cd_deadline.isoformat(),
                "actual_date": cd_sent_date.isoformat(),
                "closing_date": closing_date.isoformat(),
                "is_violation": True,
            })
    else:
        # CD not yet sent - check urgency
        if today >= cd_deadline:
            issues.append({
                "check": "trid_cd_timing",
                "severity": "critical",
                "title": "CD deadline MISSED",
                "description": (
                    f"Closing Disclosure has NOT been sent. Must be received by "
                    f"{cd_deadline.isoformat()} (3 business days before closing on "
                    f"{closing_date.isoformat()}). "
                    f"CLOSING MUST BE RESCHEDULED unless CD is sent immediately."
                ),
                "deadline": cd_deadline.isoformat(),
                "closing_date": closing_date.isoformat(),
                "is_violation": True,
            })
        else:
            days_until_deadline = count_business_days(today, cd_deadline)
            if days_until_deadline <= 2:
                issues.append({
                    "check": "trid_cd_timing",
                    "severity": "high",
                    "title": "CD deadline approaching",
                    "description": (
                        f"Closing Disclosure must be sent by {cd_deadline.isoformat()} "
                        f"({days_until_deadline} business day(s) remaining). Closing "
                        f"scheduled for {closing_date.isoformat()}."
                    ),
                    "deadline": cd_deadline.isoformat(),
                    "days_remaining": days_until_deadline,
                    "closing_date": closing_date.isoformat(),
                    "is_violation": False,
                })

    return issues


def _check_tolerance_violations(
    db: Session,
    loan_id: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Check fee tolerance violations between LE and CD amounts.

    TRID tolerance categories (12 CFR 1026.19(e)(3)):
        - Zero tolerance: Individual fees cannot increase at all
        - 10% tolerance: Aggregate of category fees can increase up to 10%
        - Unlimited: No restriction on increases

    Returns:
        Tuple of (issues list, tolerance summary dict)
    """
    from database.models.compliance import LoanFee, ToleranceCategory

    issues = []
    fees = db.query(LoanFee).filter(LoanFee.loan_id == loan_id).all()

    if not fees:
        return issues, {"has_fee_data": False}

    zero_violations = []
    ten_pct_le_total = Decimal("0")
    ten_pct_cd_total = Decimal("0")
    total_cure = Decimal("0")

    for fee in fees:
        le_amt = fee.le_amount or Decimal("0")
        cd_amt = fee.cd_amount or Decimal("0")
        variance = cd_amt - le_amt

        if fee.tolerance_category == ToleranceCategory.ZERO:
            if variance > 0:
                cure = variance
                total_cure += cure
                zero_violations.append({
                    "fee_name": fee.fee_name,
                    "le_amount": float(le_amt),
                    "cd_amount": float(cd_amt),
                    "variance": float(variance),
                    "cure_amount": float(cure),
                })

        elif fee.tolerance_category == ToleranceCategory.TEN_PERCENT:
            ten_pct_le_total += le_amt
            ten_pct_cd_total += cd_amt

    # Check 10% aggregate tolerance
    ten_pct_variance = ten_pct_cd_total - ten_pct_le_total
    ten_pct_allowed = ten_pct_le_total * Decimal("0.10")
    ten_pct_violation = None

    if ten_pct_variance > ten_pct_allowed and ten_pct_le_total > 0:
        cure = ten_pct_variance - ten_pct_allowed
        total_cure += cure
        ten_pct_violation = {
            "le_total": float(ten_pct_le_total),
            "cd_total": float(ten_pct_cd_total),
            "variance": float(ten_pct_variance),
            "allowed_increase": float(ten_pct_allowed),
            "cure_amount": float(cure),
        }

    # Build issues
    if zero_violations:
        issues.append({
            "check": "trid_zero_tolerance",
            "severity": "critical",
            "title": f"{len(zero_violations)} zero-tolerance fee violation(s)",
            "description": (
                f"{len(zero_violations)} fee(s) in the zero-tolerance category "
                f"increased from LE to CD. Lender must cure "
                f"${float(sum(Decimal(str(v['cure_amount'])) for v in zero_violations)):.2f}."
            ),
            "violations": zero_violations,
            "is_violation": True,
        })

    if ten_pct_violation:
        issues.append({
            "check": "trid_ten_percent_tolerance",
            "severity": "critical",
            "title": "10% tolerance category exceeded",
            "description": (
                f"10% tolerance category fees increased by "
                f"${float(ten_pct_variance):.2f} (allowed: "
                f"${float(ten_pct_allowed):.2f}). Cure required: "
                f"${float(ten_pct_violation['cure_amount']):.2f}."
            ),
            "violation": ten_pct_violation,
            "is_violation": True,
        })

    summary = {
        "has_fee_data": True,
        "total_fees": len(fees),
        "zero_tolerance_violations": len(zero_violations),
        "ten_percent_exceeded": ten_pct_violation is not None,
        "total_cure_amount": float(total_cure),
    }

    return issues, summary


# ============================================================================
# Main Entry Point
# ============================================================================

def check_loan_trid_compliance(
    db: Session,
    loan_id: int,
) -> Dict[str, Any]:
    """Check comprehensive TRID compliance for a loan.

    This is the main entry point for TRID compliance checking. It examines:
        1. Loan Estimate delivery timing (3 business days from application)
        2. Closing Disclosure delivery timing (3 business days before closing)
        3. Fee tolerance violations between LE and CD
        4. Generates compliance alerts for any issues found

    Args:
        db: SQLAlchemy database session
        loan_id: ID of the loan to check

    Returns:
        Dict containing:
            - loan_id: The loan ID checked
            - loan_number: Loan number for display
            - is_compliant: Boolean - True if no violations found
            - issues: List of compliance issue dicts
            - tolerance_summary: Fee tolerance analysis summary
            - deadlines: Computed TRID deadlines
            - alerts_created: Number of new compliance alerts generated
    """
    from database.models.lead_loan import Loan
    from database.models.compliance import ComplianceAlert

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return {
            "loan_id": loan_id,
            "error": f"Loan {loan_id} not found",
            "is_compliant": None,
        }

    today = date.today()
    all_issues = []

    # Extract dates from loan model
    # application_date can be a datetime or date
    app_date = None
    if loan.application_date:
        app_date = loan.application_date.date() if isinstance(loan.application_date, datetime) else loan.application_date

    # LE sent date - use loan_estimate_sent_date or initial_disclosures_sent_date
    le_sent = None
    for field_name in ['loan_estimate_sent_date', 'initial_disclosures_sent_date']:
        val = getattr(loan, field_name, None)
        if val is not None:
            le_sent = val.date() if isinstance(val, datetime) else val
            break

    # CD sent date
    cd_sent = None
    for field_name in ['cd_sent_to_borrower_date', 'final_closing_package_sent_date']:
        val = getattr(loan, field_name, None)
        if val is not None:
            cd_sent = val.date() if isinstance(val, datetime) else val
            break

    # Closing date
    close_date = None
    for field_name in ['closing_date', 'scheduled_closing_date']:
        val = getattr(loan, field_name, None)
        if val is not None:
            close_date = val.date() if isinstance(val, datetime) else val
            break

    # --- Check 1: LE Timing ---
    le_issues = _check_le_deadline(app_date, le_sent, today)
    all_issues.extend(le_issues)

    # --- Check 2: CD Timing ---
    cd_issues = _check_cd_deadline(close_date, cd_sent, today)
    all_issues.extend(cd_issues)

    # --- Check 3: Tolerance Violations ---
    tolerance_issues, tolerance_summary = _check_tolerance_violations(db, loan_id)
    all_issues.extend(tolerance_issues)

    # --- Compute deadlines ---
    deadlines = {}
    if app_date:
        deadlines["le_deadline"] = add_business_days(app_date, 3).isoformat()
        deadlines["application_date"] = app_date.isoformat()
    if close_date:
        deadlines["cd_deadline"] = subtract_business_days(close_date, 3).isoformat()
        deadlines["closing_date"] = close_date.isoformat()
    if le_sent:
        deadlines["le_sent_date"] = le_sent.isoformat()
    if cd_sent:
        deadlines["cd_sent_date"] = cd_sent.isoformat()

    # --- Generate compliance alerts for violations ---
    alerts_created = 0
    violations = [i for i in all_issues if i.get("is_violation")]
    for issue in violations:
        # Check if alert already exists for this loan + check type
        existing = db.query(ComplianceAlert).filter(
            and_(
                ComplianceAlert.loan_id == loan_id,
                ComplianceAlert.alert_type == issue["check"],
                ComplianceAlert.status.in_(["open", "acknowledged"]),
            )
        ).first()

        if existing is None:
            alert = ComplianceAlert(
                organization_id=loan.organization_id,
                loan_id=loan_id,
                alert_type=issue["check"],
                severity=issue["severity"],
                title=issue["title"],
                description=issue["description"],
                deadline_date=date.fromisoformat(issue["deadline"]) if issue.get("deadline") else None,
                status="open",
            )
            db.add(alert)
            alerts_created += 1

    # Also create alerts for approaching deadlines (non-violation warnings)
    warnings = [i for i in all_issues if not i.get("is_violation") and i["severity"] in ("high",)]
    for warning in warnings:
        existing = db.query(ComplianceAlert).filter(
            and_(
                ComplianceAlert.loan_id == loan_id,
                ComplianceAlert.alert_type == warning["check"],
                ComplianceAlert.status.in_(["open", "acknowledged"]),
            )
        ).first()

        if existing is None:
            alert = ComplianceAlert(
                organization_id=loan.organization_id,
                loan_id=loan_id,
                alert_type=warning["check"],
                severity=warning["severity"],
                title=warning["title"],
                description=warning["description"],
                deadline_date=date.fromisoformat(warning["deadline"]) if warning.get("deadline") else None,
                days_remaining=warning.get("days_remaining"),
                status="open",
            )
            db.add(alert)
            alerts_created += 1

    if alerts_created > 0:
        try:
            db.flush()
        except Exception as e:
            logger.error(f"Failed to create compliance alerts for loan {loan_id}: {e}")

    is_compliant = len(violations) == 0

    return {
        "loan_id": loan_id,
        "loan_number": loan.loan_number,
        "is_compliant": is_compliant,
        "issues": all_issues,
        "violation_count": len(violations),
        "warning_count": len([i for i in all_issues if not i.get("is_violation")]),
        "tolerance_summary": tolerance_summary,
        "deadlines": deadlines,
        "alerts_created": alerts_created,
    }
