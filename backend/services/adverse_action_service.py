"""
Adverse Action Notice Service

Automates ECOA-compliant adverse action notice generation when a loan
transitions to a terminal denial stage (DENIED, DOES_NOT_QUALIFY).

Regulation B (12 CFR 1002.9) requires:
    - Written notice within 30 days of the credit decision
    - Specific reason(s) for the adverse action (up to 4)
    - Name and address of the federal regulator
    - Creditor identification
    - ECOA rights notice

Enterprise Readiness: Domain 2, Check 2.7-2.8
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# ECOA Standard Reason Codes (Regulation B, Appendix C)
# =============================================================================

ECOA_REASON_CODES: Dict[str, Dict[str, str]] = {
    "credit_score": {
        "code": "CR001",
        "description": "Credit score does not meet minimum requirements",
        "category": "credit_history",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "debt_to_income": {
        "code": "CR002",
        "description": "Excessive obligations in relation to income (debt-to-income ratio)",
        "category": "financial",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "employment_history": {
        "code": "CR003",
        "description": "Insufficient length or stability of employment",
        "category": "employment",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "insufficient_income": {
        "code": "CR004",
        "description": "Income insufficient for the amount of credit requested",
        "category": "financial",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "collateral_value": {
        "code": "CR005",
        "description": "Value or type of collateral is not sufficient",
        "category": "collateral",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "incomplete_application": {
        "code": "CR006",
        "description": "Application incomplete — required information not provided",
        "category": "application",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "residency_status": {
        "code": "CR007",
        "description": "Temporary or irregular residency status",
        "category": "residency",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "credit_history_length": {
        "code": "CR008",
        "description": "Insufficient length of credit history",
        "category": "credit_history",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "delinquent_accounts": {
        "code": "CR009",
        "description": "Delinquent past or present credit obligations",
        "category": "credit_history",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "bankruptcy": {
        "code": "CR010",
        "description": "Bankruptcy, judgment, or collection action on credit report",
        "category": "credit_history",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "too_many_inquiries": {
        "code": "CR011",
        "description": "Too many recent credit inquiries",
        "category": "credit_history",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "insufficient_cash_reserves": {
        "code": "CR012",
        "description": "Insufficient cash reserves after closing",
        "category": "financial",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "property_type_ineligible": {
        "code": "CR013",
        "description": "Property type does not qualify for the loan program",
        "category": "collateral",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
    "other": {
        "code": "CR099",
        "description": "Other (see reason description for details)",
        "category": "other",
        "regulation_ref": "12 CFR 1002.9(a)(2)(i)",
    },
}


def get_ecoa_reason_codes() -> Dict[str, Dict[str, str]]:
    """Return the standard ECOA/Regulation B adverse action reason codes.

    Returns:
        Dictionary mapping reason code keys to their details (code, description,
        category, regulation reference).
    """
    return ECOA_REASON_CODES


def generate_adverse_action_notice(
    db: Session,
    loan,
    denial_reason_codes: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate an AdverseActionNotice record when a loan is denied.

    Per Regulation B (12 CFR 1002.9), the creditor must:
    1. Provide an adverse action notice within 30 days
    2. Include specific reason(s) for the adverse action
    3. Include ECOA rights notice and creditor/regulator info

    Args:
        db: Database session
        loan: Loan ORM object that was denied
        denial_reason_codes: List of ECOA reason code keys (e.g., ["credit_score", "debt_to_income"]).
            If not provided, defaults to ["other"].
        user_id: User who triggered the denial
        organization_id: Organization ID for the loan

    Returns:
        Dict with notice details including ID, deadline, and status.
    """
    from database.models.compliance import AdverseActionNotice, AdverseActionReason, ComplianceAlert

    loan_id = loan.id
    org_id = organization_id or getattr(loan, "organization_id", None)
    lead_id = getattr(loan, "lead_id", None)

    # Check if an adverse action notice already exists for this loan
    existing = db.query(AdverseActionNotice).filter(
        AdverseActionNotice.loan_id == loan_id,
    ).first()

    if existing:
        logger.info(
            "Adverse action notice already exists for loan %s (notice ID: %s)",
            loan_id, existing.id,
        )
        return {
            "notice_id": existing.id,
            "loan_id": loan_id,
            "already_existed": True,
            "status": existing.status,
            "notice_deadline": existing.notice_deadline.isoformat() if existing.notice_deadline else None,
        }

    # Determine reason codes
    if not denial_reason_codes:
        denial_reason_codes = ["other"]

    primary_reason_key = denial_reason_codes[0]
    secondary_reason_keys = denial_reason_codes[1:] if len(denial_reason_codes) > 1 else []

    # Map to AdverseActionReason enum (best-effort)
    try:
        primary_enum = AdverseActionReason(primary_reason_key)
    except ValueError:
        primary_enum = AdverseActionReason.OTHER

    # Calculate deadline (30 days from denial)
    denial_date = date.today()
    notice_deadline = denial_date + timedelta(days=30)

    # Get borrower info for the notice
    borrower_name = getattr(loan, "borrower_name", None) or "Applicant"
    borrower_address = getattr(loan, "property_address", None)

    # Build reason description from standard codes
    reason_parts = []
    for code_key in denial_reason_codes:
        reason_info = ECOA_REASON_CODES.get(code_key)
        if reason_info:
            reason_parts.append(f"{reason_info['code']}: {reason_info['description']}")
        else:
            reason_parts.append(f"Reason: {code_key}")
    reason_description = "; ".join(reason_parts)

    # Create the AdverseActionNotice record
    notice = AdverseActionNotice(
        organization_id=org_id,
        loan_id=loan_id,
        lead_id=lead_id,
        denial_date=denial_date,
        notice_deadline=notice_deadline,
        primary_reason=primary_enum,
        secondary_reasons=secondary_reason_keys or None,
        reason_description=reason_description,
        delivery_method="mail",
        recipient_name=borrower_name,
        recipient_address=borrower_address,
        federal_regulator="CFPB",
        status="pending",
        created_by_id=user_id,
    )
    db.add(notice)
    db.flush()

    # Create a ComplianceAlert for visibility
    try:
        alert = ComplianceAlert(
            organization_id=org_id,
            loan_id=loan_id,
            lead_id=lead_id,
            alert_type="ecoa_adverse_action_deadline",
            severity="critical",
            title=f"Adverse Action Notice Required - Loan {getattr(loan, 'loan_number', loan_id)}",
            description=(
                f"Loan denied on {denial_date.strftime('%m/%d/%Y')}. "
                f"ECOA Regulation B requires adverse action notice by "
                f"{notice_deadline.strftime('%m/%d/%Y')} (30 days). "
                f"Reason(s): {reason_description}"
            ),
            deadline_date=notice_deadline,
            days_remaining=(notice_deadline - date.today()).days,
            status="open",
        )
        db.add(alert)
    except Exception as e:
        logger.warning("Could not create compliance alert for adverse action: %s", e)

    # Audit trail entry
    try:
        from services.audit_service import create_audit_entry
        create_audit_entry(
            db=db,
            user_id=user_id or 0,
            changed_by_id=user_id or 0,
            change_type="compliance",
            entity_type="adverse_action_notice",
            entity_id=notice.id,
            before_state=None,
            after_state={
                "notice_id": notice.id,
                "loan_id": loan_id,
                "denial_date": denial_date.isoformat(),
                "notice_deadline": notice_deadline.isoformat(),
                "primary_reason": primary_reason_key,
                "secondary_reasons": secondary_reason_keys,
                "borrower_name": borrower_name,
                "loan_number": getattr(loan, "loan_number", None),
                "auto_generated": True,
            },
            reason="ECOA adverse action notice auto-generated on loan denial",
            organization_id=org_id,
        )
    except Exception as e:
        logger.warning("Audit entry creation failed for adverse action notice: %s", e)

    logger.info(
        "ADVERSE_ACTION_NOTICE_GENERATED: loan=%s, notice=%s, deadline=%s, reasons=%s",
        loan_id, notice.id, notice_deadline.isoformat(), denial_reason_codes,
    )

    return {
        "notice_id": notice.id,
        "loan_id": loan_id,
        "already_existed": False,
        "denial_date": denial_date.isoformat(),
        "notice_deadline": notice_deadline.isoformat(),
        "days_until_deadline": (notice_deadline - date.today()).days,
        "primary_reason": primary_reason_key,
        "secondary_reasons": secondary_reason_keys,
        "status": "pending",
    }


def check_overdue_notices(
    db: Session,
    org_id: int,
) -> Dict[str, Any]:
    """Find adverse action notices that are past their 30-day deadline and unsent.

    Regulation B requires notice within 30 days of the credit decision.
    This function identifies notices where the deadline has passed but
    the notice has not been sent (status still 'pending').

    Args:
        db: Database session
        org_id: Organization ID to check

    Returns:
        Dict containing:
            - overdue_count: Number of overdue notices
            - overdue_notices: List of overdue notice details
            - compliant_count: Number of notices sent on time
            - pending_count: Notices still pending but not yet overdue
    """
    from database.models.compliance import AdverseActionNotice

    today = date.today()

    all_notices = db.query(AdverseActionNotice).filter(
        AdverseActionNotice.organization_id == org_id,
    ).all()

    overdue = []
    compliant = 0
    pending = 0
    total = len(all_notices)

    for notice in all_notices:
        if notice.status == "sent" or notice.status == "acknowledged":
            if notice.is_on_time is True:
                compliant += 1
            elif notice.is_on_time is False:
                # Sent but late
                overdue.append({
                    "notice_id": notice.id,
                    "loan_id": notice.loan_id,
                    "denial_date": notice.denial_date.isoformat() if notice.denial_date else None,
                    "notice_deadline": notice.notice_deadline.isoformat() if notice.notice_deadline else None,
                    "notice_sent_date": notice.notice_sent_date.isoformat() if notice.notice_sent_date else None,
                    "days_late": (notice.notice_sent_date - notice.notice_deadline).days if notice.notice_sent_date and notice.notice_deadline else None,
                    "status": notice.status,
                    "severity": "violation",
                    "primary_reason": notice.primary_reason.value if notice.primary_reason else None,
                })
            else:
                compliant += 1  # Sent, is_on_time not yet set
        elif notice.status == "pending":
            if notice.notice_deadline and notice.notice_deadline < today:
                # Deadline has passed and notice was never sent
                days_overdue = (today - notice.notice_deadline).days
                overdue.append({
                    "notice_id": notice.id,
                    "loan_id": notice.loan_id,
                    "denial_date": notice.denial_date.isoformat() if notice.denial_date else None,
                    "notice_deadline": notice.notice_deadline.isoformat() if notice.notice_deadline else None,
                    "notice_sent_date": None,
                    "days_overdue": days_overdue,
                    "status": "overdue",
                    "severity": "critical" if days_overdue > 7 else "high",
                    "primary_reason": notice.primary_reason.value if notice.primary_reason else None,
                })
            else:
                pending += 1

    return {
        "organization_id": org_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_notices": total,
        "overdue_count": len(overdue),
        "compliant_count": compliant,
        "pending_count": pending,
        "overdue_notices": overdue,
        "compliance_rate": round(compliant / total * 100, 1) if total > 0 else 100.0,
    }
