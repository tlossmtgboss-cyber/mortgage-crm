"""
Disclosure Trigger Service

Automated compliance enforcement for TRID changed circumstances and CD waiting period.

Critical Failure 2.3: Auto-trigger re-disclosure on changed circumstances
Critical Failure 2.5: CD waiting period enforcement (block closing if < 3 business days)

When a loan's rate, amount, program type, or property address changes, this service
automatically creates a Revised LE DisclosureEvent and a ComplianceAlert, ensuring
TRID compliance is maintained without manual intervention.

Usage:
    from services.disclosure_trigger import check_changed_circumstances, validate_cd_waiting_period

    # After loan update:
    check_changed_circumstances(db, loan_id, old_values, new_values)

    # Before setting closing date:
    validate_cd_waiting_period(db, loan, closing_date)
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Optional, List, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# Business Day Calculation
# ============================================================================

def add_business_days(start_date: date, days: int) -> date:
    """Add business days to a date, skipping weekends (Sat=5, Sun=6).

    Federal holidays are not considered here; a production system should
    integrate a holiday calendar. TRID regulations reference business days
    as days on which the creditor's offices are open to the public.

    Args:
        start_date: The starting date.
        days: Number of business days to add.

    Returns:
        The resulting date after adding the specified business days.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()

    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        # Skip weekends (Monday=0 ... Sunday=6)
        if current.weekday() < 5:
            added += 1
    return current


def count_business_days(start_date: date, end_date: date) -> int:
    """Count business days between two dates (exclusive of start, inclusive of end).

    Args:
        start_date: The start date.
        end_date: The end date.

    Returns:
        Number of business days between the two dates.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    if end_date <= start_date:
        return 0

    count = 0
    current = start_date
    while current < end_date:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count


# ============================================================================
# Fields tracked for changed circumstances
# ============================================================================

TRACKED_FIELDS = {
    "rate": "interest_rate",
    "amount": "loan_amount",
    "loan_type": "loan_type",
    "program": "program_type",
    "property_address": "property_address",
}


def _describe_change(field: str, old_val, new_val) -> str:
    """Generate a human-readable description of a changed field."""
    display_name = TRACKED_FIELDS.get(field, field)
    if field == "rate":
        return f"Interest rate changed from {old_val}% to {new_val}%"
    elif field == "amount":
        old_fmt = f"${float(old_val):,.2f}" if old_val else "N/A"
        new_fmt = f"${float(new_val):,.2f}" if new_val else "N/A"
        return f"Loan amount changed from {old_fmt} to {new_fmt}"
    elif field == "loan_type":
        return f"Loan type changed from '{old_val}' to '{new_val}'"
    elif field == "program":
        return f"Program type changed from '{old_val}' to '{new_val}'"
    elif field == "property_address":
        return f"Property address changed from '{old_val}' to '{new_val}'"
    else:
        return f"{display_name} changed from '{old_val}' to '{new_val}'"


def _change_reason_code(field: str) -> str:
    """Map a field name to a TRID change reason code."""
    mapping = {
        "rate": "rate_change",
        "amount": "loan_amount_change",
        "loan_type": "program_change",
        "program": "program_change",
        "property_address": "property_change",
    }
    return mapping.get(field, "other_change")


# ============================================================================
# Changed Circumstance Detection (Critical Failure 2.3)
# ============================================================================

def check_changed_circumstances(
    db: Session,
    loan_id: int,
    old_values: Dict,
    new_values: Dict,
    organization_id: Optional[int] = None,
    triggered_by_user_id: Optional[int] = None,
) -> List[Dict]:
    """Detect changes in tracked fields and auto-create re-disclosure events.

    When a loan's rate, amount, program type, or property address changes,
    this function creates:
        1. A DisclosureEvent record with disclosure_type='revised_le',
           sent_at=None (pending), and deadline_date = 3 business days from now
        2. A ComplianceAlert with alert_type='changed_circumstance', severity='high'

    Args:
        db: SQLAlchemy database session.
        loan_id: The ID of the loan being updated.
        old_values: Dict of field values BEFORE the update.
        new_values: Dict of field values AFTER the update.
        organization_id: Optional organization ID for multi-tenant scoping.
        triggered_by_user_id: Optional user ID who made the change.

    Returns:
        List of dicts describing each detected change and the actions taken.
    """
    from database.models.compliance import DisclosureEvent, ComplianceAlert

    changes_detected = []
    today = date.today()
    now = datetime.now(timezone.utc)
    deadline = add_business_days(today, 3)

    for field in TRACKED_FIELDS:
        old_val = old_values.get(field)
        new_val = new_values.get(field)

        # Skip if field was not in the update payload
        if field not in new_values:
            continue

        # Skip if values are the same (handle None comparison)
        if old_val == new_val:
            continue

        # Skip if both are falsy (None -> None, None -> "", etc.)
        if not old_val and not new_val:
            continue

        # For numeric fields, compare with tolerance
        if field in ("rate", "amount"):
            try:
                old_num = float(old_val) if old_val is not None else None
                new_num = float(new_val) if new_val is not None else None
                if old_num is not None and new_num is not None:
                    if abs(old_num - new_num) < 0.001:
                        continue
            except (ValueError, TypeError):
                pass

        # Change detected - create disclosure event and alert
        change_reason = _change_reason_code(field)
        change_description = _describe_change(field, old_val, new_val)

        logger.info(
            f"Changed circumstance detected on loan {loan_id}: "
            f"{change_description} (reason: {change_reason})"
        )

        # 1. Create Revised LE DisclosureEvent (sent_at=None means pending)
        disclosure_event = DisclosureEvent(
            organization_id=organization_id,
            loan_id=loan_id,
            disclosure_type="revised_le",
            prepared_at=now,
            sent_at=None,  # Pending - must be sent by deadline
            deadline_date=deadline,
            is_on_time=None,  # Will be determined when sent
            change_reason=change_reason,
            change_description=change_description,
            created_by_id=triggered_by_user_id,
        )
        db.add(disclosure_event)

        # 2. Create ComplianceAlert
        alert = ComplianceAlert(
            organization_id=organization_id,
            loan_id=loan_id,
            alert_type="changed_circumstance",
            severity="high",
            title=f"Re-disclosure required: {change_description}",
            description=(
                f"A changed circumstance has been detected on this loan. "
                f"A Revised Loan Estimate must be sent to the borrower within "
                f"3 business days (by {deadline.strftime('%m/%d/%Y')}). "
                f"Change: {change_description}"
            ),
            deadline_date=deadline,
            days_remaining=count_business_days(today, deadline),
            status="open",
        )
        db.add(alert)

        changes_detected.append({
            "field": field,
            "old_value": old_val,
            "new_value": new_val,
            "change_reason": change_reason,
            "description": change_description,
            "deadline": deadline.isoformat(),
            "disclosure_type": "revised_le",
            "alert_severity": "high",
        })

    if changes_detected:
        logger.info(
            f"Created {len(changes_detected)} re-disclosure event(s) and alert(s) "
            f"for loan {loan_id}"
        )

    return changes_detected


# ============================================================================
# CD Waiting Period Enforcement (Critical Failure 2.5)
# ============================================================================

def validate_cd_waiting_period(
    db: Session,
    loan,
    new_closing_date: datetime,
    force_closing: bool = False,
    user_role: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict]:
    """Validate that the CD waiting period is met before allowing closing.

    TRID requires that the Closing Disclosure be delivered at least 3 business
    days before consummation. This function BLOCKS closing if the requirement
    is not met, unless an authorized user (admin/site_admin) explicitly
    overrides with force_closing=True.

    Args:
        db: SQLAlchemy database session.
        loan: Loan ORM object with cd_sent_to_borrower_date.
        new_closing_date: The proposed closing/consummation date.
        force_closing: If True and user is authorized, bypass the check.
        user_role: The role of the user making the change (for override auth).
        user_id: The ID of the user making the change (for audit logging).

    Returns:
        None if the closing date is valid.
        Dict with error details if the closing date violates the waiting period.

    Raises:
        Nothing - returns error dict instead of raising, so the caller
        can raise the appropriate HTTP exception.
    """
    from database.models.security import AuditLog

    # Get the CD sent date from the loan
    cd_sent_date = getattr(loan, "cd_sent_to_borrower_date", None)

    # If no CD has been sent, block closing
    if cd_sent_date is None:
        if force_closing and user_role in ("admin", "site_admin"):
            # Log the override
            _log_cd_override(db, loan, user_id, "No CD sent - forced closing override")
            return None

        return {
            "error": "cd_not_sent",
            "message": (
                "Cannot schedule closing: Closing Disclosure has not been sent to the borrower. "
                "The CD must be delivered at least 3 business days before consummation (TRID requirement)."
            ),
            "cd_sent_date": None,
            "closing_date": new_closing_date.isoformat() if isinstance(new_closing_date, datetime) else str(new_closing_date),
            "business_days_gap": 0,
            "required_business_days": 3,
        }

    # Calculate business days between CD sent and closing
    if isinstance(new_closing_date, datetime):
        closing_as_date = new_closing_date.date()
    elif isinstance(new_closing_date, date):
        closing_as_date = new_closing_date
    else:
        # Try to parse string
        try:
            closing_as_date = datetime.fromisoformat(str(new_closing_date)).date()
        except (ValueError, TypeError):
            return {
                "error": "invalid_date",
                "message": f"Invalid closing date format: {new_closing_date}",
            }

    if isinstance(cd_sent_date, datetime):
        cd_sent_as_date = cd_sent_date.date()
    else:
        cd_sent_as_date = cd_sent_date

    business_days = count_business_days(cd_sent_as_date, closing_as_date)

    if business_days >= 3:
        # Compliant - no issue
        return None

    # Violation detected
    earliest_allowed = add_business_days(cd_sent_as_date, 3)

    if force_closing and user_role in ("admin", "site_admin"):
        # Authorized override - log it and allow
        _log_cd_override(
            db, loan, user_id,
            f"CD waiting period override: {business_days} business days "
            f"(required 3). CD sent {cd_sent_as_date}, closing {closing_as_date}."
        )
        logger.warning(
            f"CD waiting period OVERRIDDEN for loan {loan.id} by user {user_id} "
            f"(role: {user_role}). {business_days} business days, required 3."
        )
        return None

    # Block the closing
    error_detail = {
        "error": "cd_waiting_period_violation",
        "message": (
            f"Cannot schedule closing for {closing_as_date.strftime('%m/%d/%Y')}: "
            f"Closing Disclosure was sent on {cd_sent_as_date.strftime('%m/%d/%Y')}, "
            f"which is only {business_days} business day(s) before the proposed closing date. "
            f"TRID requires at least 3 business days. "
            f"Earliest allowed closing date: {earliest_allowed.strftime('%m/%d/%Y')}. "
            f"To override, an admin or site admin must set force_closing=true."
        ),
        "cd_sent_date": cd_sent_as_date.isoformat(),
        "closing_date": closing_as_date.isoformat(),
        "business_days_gap": business_days,
        "required_business_days": 3,
        "earliest_allowed_closing": earliest_allowed.isoformat(),
    }

    logger.warning(
        f"CD waiting period BLOCKED for loan {loan.id}: "
        f"{business_days} business days (required 3)"
    )

    return error_detail


def _log_cd_override(
    db: Session,
    loan,
    user_id: Optional[int],
    details: str,
) -> None:
    """Log a CD waiting period override to the audit trail."""
    try:
        from database.models.security import AuditLog

        audit_entry = AuditLog(
            user_id=getattr(loan, "loan_officer_id", None) or user_id or 0,
            changed_by_id=user_id or 0,
            change_type="compliance_override",
            entity_type="loan",
            entity_id=loan.id,
            before_state={"cd_waiting_period_enforced": True},
            after_state={"cd_waiting_period_overridden": True, "details": details},
            reason=details,
        )
        db.add(audit_entry)
        logger.info(f"Audit log: CD waiting period override for loan {loan.id}")
    except Exception as e:
        # Don't fail the operation if audit logging fails
        logger.error(f"Failed to create audit log for CD override: {e}")
