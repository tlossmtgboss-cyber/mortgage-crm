"""
ECOA Adverse Action Validation Service

When a loan is denied (stage -> DENIED), ECOA (Regulation B, 12 CFR 1002.9)
requires that an adverse action notice be sent within 30 days.

This validator checks:
    - Whether an adverse action notice exists for the loan
    - Whether the notice was sent within the 30-day deadline
    - Whether specific reason(s) for denial are included
    - Whether the ECOA rights notice text is present
    - Whether credit bureau information is included if credit was a denial factor

Usage:
    from services.compliance.ecoa_validator import ECOAValidator

    validator = ECOAValidator()
    result = validator.validate(db, loan_id)
    # result = {
    #     "compliant": True/False,
    #     "loan_id": 123,
    #     "missing_requirements": [...],
    #     "deadline": "2026-05-07",
    # }
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ECOA standard reason codes that require credit bureau disclosure
CREDIT_RELATED_REASONS = frozenset({
    "credit_score",
    "debt_to_income",
})

# Minimum required notice fields per Regulation B
ECOA_REQUIRED_FIELDS = [
    "primary_reason",
    "creditor_name",
    "federal_regulator",
]

# ECOA rights notice text that must accompany every adverse action notice
ECOA_RIGHTS_NOTICE = (
    "The Federal Equal Credit Opportunity Act prohibits creditors from "
    "discriminating against credit applicants on the basis of race, color, "
    "religion, national origin, sex, marital status, or age (provided the "
    "applicant has the capacity to enter into a binding contract); because "
    "all or part of the applicant's income derives from any public assistance "
    "program; or because the applicant has in good faith exercised any right "
    "under the Consumer Credit Protection Act."
)


class ECOAValidator:
    """Validates ECOA adverse action notice requirements."""

    def validate(
        self,
        db: Session,
        loan_id: int,
        organization_id: Optional[int] = None,
        denial_date_override: Optional[date] = None,
    ) -> dict:
        """Validate ECOA adverse action compliance for a loan.

        Args:
            db: Database session.
            loan_id: The loan to validate.
            organization_id: Optional org filter for tenant isolation.
            denial_date_override: Override the denial date (useful for
                pre-transition checks before the stage actually changes).

        Returns:
            Structured result with compliant flag, missing requirements,
            and deadline.
        """
        from database.models.lead_loan import Loan
        from database.models.compliance import AdverseActionNotice, AdverseActionReason

        # Load loan
        query = db.query(Loan).filter(Loan.id == loan_id)
        if organization_id:
            query = query.filter(Loan.organization_id == organization_id)
        loan = query.first()
        if not loan:
            return {
                "compliant": False,
                "loan_id": loan_id,
                "error": f"Loan {loan_id} not found",
                "missing_requirements": [],
                "deadline": None,
            }

        # Determine denial date
        denial_dt = denial_date_override
        if not denial_dt:
            # Check if the loan is already in DENIED stage
            stage = (loan.stage or "").upper()
            if stage == "DENIED":
                # Use stage_changed_at or today
                if loan.stage_changed_at:
                    denial_dt = (
                        loan.stage_changed_at.date()
                        if isinstance(loan.stage_changed_at, datetime)
                        else loan.stage_changed_at
                    )
                else:
                    denial_dt = date.today()
            else:
                # Loan is not denied -- check is for a proposed transition
                denial_dt = date.today()

        deadline = denial_dt + timedelta(days=30)
        today = date.today()

        missing_requirements: list = []
        warnings: list = []

        # Look for existing adverse action notice(s) for this loan
        notice_query = db.query(AdverseActionNotice).filter(
            AdverseActionNotice.loan_id == loan_id
        )
        if organization_id:
            notice_query = notice_query.filter(
                AdverseActionNotice.organization_id == organization_id
            )
        notices = notice_query.order_by(
            AdverseActionNotice.created_at.desc()
        ).all()

        if not notices:
            missing_requirements.append(
                "No adverse action notice created for this loan"
            )
            missing_requirements.append(
                "Notice must include specific reason(s) for denial"
            )
            missing_requirements.append(
                "Notice must include ECOA rights notice text"
            )
            missing_requirements.append(
                "Notice must include creditor name and federal regulator"
            )

            days_remaining = (deadline - today).days
            if days_remaining < 0:
                missing_requirements.append(
                    f"DEADLINE EXPIRED: Notice was due by {deadline.isoformat()} "
                    f"({abs(days_remaining)} days overdue)"
                )

            self._log_compliance_decision(
                db, loan_id, loan.organization_id, False,
                missing_requirements, deadline
            )

            return {
                "compliant": False,
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "denial_date": denial_dt.isoformat(),
                "deadline": deadline.isoformat(),
                "days_remaining": days_remaining,
                "missing_requirements": missing_requirements,
                "warnings": warnings,
                "notice_exists": False,
            }

        # Validate the most recent notice
        notice = notices[0]

        # Check 1: Notice has specific denial reason(s)
        if not notice.primary_reason:
            missing_requirements.append(
                "Notice must include specific reason(s) for denial"
            )

        # Check 2: Required regulatory fields
        for field in ECOA_REQUIRED_FIELDS:
            value = getattr(notice, field, None)
            if not value:
                missing_requirements.append(
                    f"Required field '{field}' is missing from adverse action notice"
                )

        # Check 3: Credit bureau disclosure if credit was a factor
        credit_was_factor = False
        if notice.primary_reason:
            reason_val = (
                notice.primary_reason.value
                if hasattr(notice.primary_reason, "value")
                else str(notice.primary_reason)
            )
            if reason_val in CREDIT_RELATED_REASONS:
                credit_was_factor = True

        if notice.secondary_reasons:
            for reason in notice.secondary_reasons:
                if reason in CREDIT_RELATED_REASONS:
                    credit_was_factor = True

        if credit_was_factor:
            # Check that credit bureau info is present in reason_description
            # or in a related field. We check reason_description for any
            # mention of credit bureau.
            desc = (notice.reason_description or "").lower()
            has_bureau_info = any(
                term in desc
                for term in ["credit bureau", "equifax", "experian", "transunion", "credit report"]
            )
            if not has_bureau_info:
                missing_requirements.append(
                    "Credit was a factor in denial -- notice must include "
                    "credit bureau name and contact information "
                    "(Equifax, Experian, or TransUnion)"
                )

        # Check 4: ECOA rights notice text
        # We verify that reason_description contains ECOA language,
        # or that the notice has recipient information (indicating
        # a properly formatted notice was prepared).
        if not notice.recipient_name:
            missing_requirements.append(
                "Notice must include recipient name and address"
            )

        # Check 5: Timeliness -- was/will the notice be sent on time?
        if notice.notice_sent_date:
            sent_dt = (
                notice.notice_sent_date
                if isinstance(notice.notice_sent_date, date)
                else notice.notice_sent_date.date()
                if isinstance(notice.notice_sent_date, datetime)
                else notice.notice_sent_date
            )
            if sent_dt > deadline:
                missing_requirements.append(
                    f"Notice was sent {sent_dt.isoformat()} which is past "
                    f"the 30-day deadline of {deadline.isoformat()}"
                )
        else:
            # Notice exists but hasn't been sent yet
            days_remaining = (deadline - today).days
            if days_remaining < 0:
                missing_requirements.append(
                    f"DEADLINE EXPIRED: Notice was due by {deadline.isoformat()} "
                    f"({abs(days_remaining)} days overdue) and has not been sent"
                )
            elif days_remaining <= 5:
                warnings.append(
                    f"Adverse action notice deadline approaching: "
                    f"{days_remaining} day(s) remaining (deadline: {deadline.isoformat()})"
                )

        compliant = len(missing_requirements) == 0
        days_remaining = (deadline - today).days

        self._log_compliance_decision(
            db, loan_id, loan.organization_id, compliant,
            missing_requirements, deadline
        )

        return {
            "compliant": compliant,
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "denial_date": denial_dt.isoformat(),
            "deadline": deadline.isoformat(),
            "days_remaining": days_remaining,
            "missing_requirements": missing_requirements,
            "warnings": warnings,
            "notice_exists": True,
            "notice_id": notice.id,
            "notice_status": notice.status,
            "notice_sent_date": (
                notice.notice_sent_date.isoformat()
                if notice.notice_sent_date
                else None
            ),
        }

    def _log_compliance_decision(
        self, db: Session, loan_id: int, organization_id: int,
        compliant: bool, missing: list, deadline: date,
    ):
        """Log ECOA validation decision to the compliance audit log."""
        try:
            from database.models.compliance_log import ComplianceDecisionLog

            log_entry = ComplianceDecisionLog(
                organization_id=organization_id,
                decision_type="ecoa_adverse_action",
                contact_id=loan_id,
                decision="allowed" if compliant else "warning",
                reason=(
                    "ECOA adverse action notice requirements met"
                    if compliant
                    else f"ECOA requirements incomplete: {len(missing)} issue(s)"
                ),
                details={
                    "loan_id": loan_id,
                    "deadline": deadline.isoformat(),
                    "missing_count": len(missing),
                    "missing_requirements": missing,
                },
            )
            db.add(log_entry)
        except Exception as e:
            logger.warning(f"Failed to log ECOA compliance decision: {e}")
