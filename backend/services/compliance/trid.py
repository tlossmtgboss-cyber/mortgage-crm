"""
TRID Deadline Calculation Engine

Deterministic, rule-based TRID (TILA-RESPA Integrated Disclosure)
deadline calculations.  No LLM calls.

Regulations implemented:
    - 12 CFR 1026.19(e)(1)(iii): LE must be delivered within 3 business
      days of receiving a loan application.
    - 12 CFR 1026.19(f)(1)(ii): CD must be delivered at least 3 business
      days before consummation (closing).
    - 12 CFR 1026.19(e)(4): Changed circumstance re-disclosure rules.
    - 12 CFR 1026.19(e)(3): Fee tolerance buckets.

All calculations return structured results with full audit metadata:
what rule was applied, what inputs were used, and when the calculation
was performed.

Usage:
    from services.compliance.trid import TRIDEngine

    engine = TRIDEngine()
    result = engine.calculate_le_deadline(application_date=date(2026, 5, 14))
"""

import logging
from datetime import date, datetime, timezone
from enum import Enum
from typing import FrozenSet, List, Optional

from pydantic import BaseModel, Field

from services.compliance.business_days import (
    add_business_days,
    count_business_days,
    is_business_day,
    subtract_business_days,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and Constants
# ---------------------------------------------------------------------------

class ToleranceBucket(str, Enum):
    """TRID fee tolerance categories per 12 CFR 1026.19(e)(3)."""
    ZERO = "zero_tolerance"
    TEN_PERCENT = "ten_percent_cumulative"
    UNLIMITED = "unlimited"


class ChangedCircumstanceType(str, Enum):
    """Valid changed circumstance triggers for LE re-disclosure."""
    RATE_CHANGE = "rate_change"
    LOAN_AMOUNT_CHANGE = "loan_amount_change"
    PROGRAM_CHANGE = "program_change"
    PROPERTY_VALUE_CHANGE = "property_value_change"
    BORROWER_REQUESTED = "borrower_requested"
    CREDIT_CHANGE = "credit_change"
    REGULATORY_CHANGE = "regulatory_change"
    NATURAL_DISASTER = "natural_disaster"
    OTHER = "other"


# Fee classifications per TRID
ZERO_TOLERANCE_FEES = frozenset({
    "origination_charge",
    "origination_fee",
    "discount_points",
    "lender_credits",
    "transfer_taxes_seller",
    "broker_fee",
    "processing_fee_lender",
    "underwriting_fee_lender",
    "administration_fee_lender",
    "application_fee_lender",
    "commitment_fee",
})

TEN_PERCENT_TOLERANCE_FEES = frozenset({
    "appraisal_fee",
    "credit_report_fee",
    "flood_certification",
    "tax_service_fee",
    "title_search_fee",
    "title_insurance_lender",
    "survey_fee",
    "pest_inspection",
    "recording_fee",
})

UNLIMITED_TOLERANCE_FEES = frozenset({
    "homeowners_insurance",
    "title_insurance_owner",
    "property_inspection",
    "home_warranty",
    "borrower_shopped_service",
    "prepaid_interest",
    "prepaid_taxes",
    "prepaid_insurance",
})


# ---------------------------------------------------------------------------
# Pydantic Models — Inputs & Outputs
# ---------------------------------------------------------------------------

class AuditMetadata(BaseModel):
    """Audit trail for every compliance calculation."""
    rule: str
    regulation: str
    inputs: dict
    calculated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LEDeadlineResult(BaseModel):
    """Result of LE (Loan Estimate) deadline calculation."""
    application_date: date
    le_deadline: date
    le_delivered_date: Optional[date] = None
    is_compliant: Optional[bool] = None
    days_remaining: Optional[int] = None
    message: str
    audit: AuditMetadata


class CDDeadlineResult(BaseModel):
    """Result of CD (Closing Disclosure) deadline calculation."""
    closing_date: date
    cd_delivery_deadline: date
    earliest_closing_after_cd: Optional[date] = None
    cd_delivered_date: Optional[date] = None
    is_compliant: Optional[bool] = None
    business_days_gap: Optional[int] = None
    message: str
    audit: AuditMetadata


class CDWaitingPeriodResult(BaseModel):
    """Result of CD 3-business-day waiting period check."""
    cd_delivery_date: date
    proposed_closing_date: date
    earliest_allowed_closing: date
    can_close: bool
    business_days_between: int
    required_business_days: int = 3
    message: str
    audit: AuditMetadata


class ReDisclosureResult(BaseModel):
    """Result of changed circumstance re-disclosure check."""
    circumstance_type: str
    circumstance_date: date
    re_disclosure_deadline: date
    original_le_date: Optional[date] = None
    message: str
    audit: AuditMetadata


class FeeToleranceClassification(BaseModel):
    """Classification of a fee into a TRID tolerance bucket."""
    fee_name: str
    bucket: ToleranceBucket
    description: str


class TRIDComplianceReport(BaseModel):
    """Combined TRID compliance report for a loan."""
    loan_id: Optional[int] = None
    le_deadline: Optional[LEDeadlineResult] = None
    cd_deadline: Optional[CDDeadlineResult] = None
    cd_waiting_period: Optional[CDWaitingPeriodResult] = None
    re_disclosures: List[ReDisclosureResult] = Field(default_factory=list)
    overall_compliant: bool = True
    issues: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TRID Engine
# ---------------------------------------------------------------------------

class TRIDEngine:
    """Deterministic TRID deadline calculation engine.

    All methods are stateless and produce audit-trailed results.
    No database access — callers pass in the relevant dates.
    """

    def calculate_le_deadline(
        self,
        application_date: date,
        le_delivered_date: Optional[date] = None,
        custom_holidays: Optional[FrozenSet[date]] = None,
    ) -> LEDeadlineResult:
        """Calculate the Loan Estimate delivery deadline.

        TRID Rule: LE must be delivered no later than 3 business days
        after receipt of the loan application.
        Regulation: 12 CFR 1026.19(e)(1)(iii)

        Args:
            application_date: Date the loan application was received.
            le_delivered_date: Actual LE delivery date (for compliance check).
            custom_holidays: Optional org-level holidays.

        Returns:
            LEDeadlineResult with deadline, compliance status, and audit trail.
        """
        deadline = add_business_days(application_date, 3, custom_holidays)

        is_compliant = None
        days_remaining = None
        message = f"LE must be delivered by {deadline.isoformat()}"

        if le_delivered_date is not None:
            is_compliant = le_delivered_date <= deadline
            if is_compliant:
                message = (
                    f"LE delivered on {le_delivered_date.isoformat()}, "
                    f"within deadline of {deadline.isoformat()}. Compliant."
                )
            else:
                message = (
                    f"LE delivered on {le_delivered_date.isoformat()}, "
                    f"AFTER deadline of {deadline.isoformat()}. VIOLATION."
                )
        else:
            today = date.today()
            if today <= deadline:
                days_remaining = count_business_days(today, deadline, custom_holidays)
                # count_business_days is exclusive of endpoints; add 1 if deadline is a bday
                if is_business_day(deadline, custom_holidays):
                    days_remaining += 1
                message = (
                    f"LE due by {deadline.isoformat()}. "
                    f"Approximately {days_remaining} business day(s) remaining."
                )
            else:
                days_remaining = 0
                message = (
                    f"LE was due by {deadline.isoformat()}. "
                    f"OVERDUE — no delivery recorded."
                )

        return LEDeadlineResult(
            application_date=application_date,
            le_deadline=deadline,
            le_delivered_date=le_delivered_date,
            is_compliant=is_compliant,
            days_remaining=days_remaining,
            message=message,
            audit=AuditMetadata(
                rule="LE 3-business-day delivery",
                regulation="12 CFR 1026.19(e)(1)(iii)",
                inputs={
                    "application_date": application_date.isoformat(),
                    "le_delivered_date": le_delivered_date.isoformat() if le_delivered_date else None,
                },
            ),
        )

    def calculate_cd_deadline(
        self,
        closing_date: date,
        cd_delivered_date: Optional[date] = None,
        custom_holidays: Optional[FrozenSet[date]] = None,
    ) -> CDDeadlineResult:
        """Calculate the Closing Disclosure delivery deadline.

        TRID Rule: CD must be delivered at least 3 business days before
        consummation (closing date).
        Regulation: 12 CFR 1026.19(f)(1)(ii)

        Args:
            closing_date: The scheduled closing/consummation date.
            cd_delivered_date: Actual CD delivery date (for compliance check).
            custom_holidays: Optional org-level holidays.

        Returns:
            CDDeadlineResult with deadline, compliance, and audit trail.
        """
        # CD must be delivered by this date (3 bdays before closing)
        cd_delivery_deadline = subtract_business_days(closing_date, 3, custom_holidays)

        is_compliant = None
        business_days_gap = None
        earliest_closing = None
        message = f"CD must be delivered by {cd_delivery_deadline.isoformat()}"

        if cd_delivered_date is not None:
            # Count business days between CD delivery and closing
            business_days_gap = count_business_days(
                cd_delivered_date, closing_date, custom_holidays
            )
            is_compliant = business_days_gap >= 3

            # Calculate earliest allowed closing after this CD delivery
            earliest_closing = add_business_days(cd_delivered_date, 3, custom_holidays)

            if is_compliant:
                message = (
                    f"CD delivered {cd_delivered_date.isoformat()}, "
                    f"{business_days_gap} business days before closing "
                    f"{closing_date.isoformat()}. Compliant."
                )
            else:
                message = (
                    f"CD delivered {cd_delivered_date.isoformat()}, "
                    f"only {business_days_gap} business days before closing "
                    f"{closing_date.isoformat()}. VIOLATION — "
                    f"earliest allowed closing: {earliest_closing.isoformat()}."
                )
        else:
            today = date.today()
            if today <= cd_delivery_deadline:
                message = (
                    f"CD must be delivered by {cd_delivery_deadline.isoformat()} "
                    f"for closing on {closing_date.isoformat()}."
                )
            else:
                message = (
                    f"CD delivery deadline of {cd_delivery_deadline.isoformat()} "
                    f"has passed. CD must be delivered immediately and closing "
                    f"may need to be rescheduled."
                )

        return CDDeadlineResult(
            closing_date=closing_date,
            cd_delivery_deadline=cd_delivery_deadline,
            earliest_closing_after_cd=earliest_closing,
            cd_delivered_date=cd_delivered_date,
            is_compliant=is_compliant,
            business_days_gap=business_days_gap,
            message=message,
            audit=AuditMetadata(
                rule="CD 3-business-day waiting period",
                regulation="12 CFR 1026.19(f)(1)(ii)",
                inputs={
                    "closing_date": closing_date.isoformat(),
                    "cd_delivered_date": cd_delivered_date.isoformat() if cd_delivered_date else None,
                },
            ),
        )

    def check_cd_waiting_period(
        self,
        cd_delivery_date: date,
        proposed_closing_date: date,
        custom_holidays: Optional[FrozenSet[date]] = None,
    ) -> CDWaitingPeriodResult:
        """Check whether the CD 3-business-day waiting period is satisfied.

        This is the core TRID gate: after CD delivery, the borrower must
        have at least 3 full business days before closing.

        Args:
            cd_delivery_date: When the CD was delivered to the borrower.
            proposed_closing_date: The proposed closing date.
            custom_holidays: Optional org-level holidays.

        Returns:
            CDWaitingPeriodResult indicating whether closing is allowed.
        """
        earliest_closing = add_business_days(cd_delivery_date, 3, custom_holidays)
        business_days_between = count_business_days(
            cd_delivery_date, proposed_closing_date, custom_holidays
        )
        can_close = proposed_closing_date >= earliest_closing

        if can_close:
            message = (
                f"Waiting period satisfied. {business_days_between} business days "
                f"between CD delivery ({cd_delivery_date.isoformat()}) and "
                f"closing ({proposed_closing_date.isoformat()})."
            )
        else:
            message = (
                f"WAITING PERIOD NOT MET. Only {business_days_between} business "
                f"days between CD delivery ({cd_delivery_date.isoformat()}) and "
                f"closing ({proposed_closing_date.isoformat()}). "
                f"Earliest allowed closing: {earliest_closing.isoformat()}."
            )

        return CDWaitingPeriodResult(
            cd_delivery_date=cd_delivery_date,
            proposed_closing_date=proposed_closing_date,
            earliest_allowed_closing=earliest_closing,
            can_close=can_close,
            business_days_between=business_days_between,
            message=message,
            audit=AuditMetadata(
                rule="CD 3-business-day waiting period",
                regulation="12 CFR 1026.19(f)(1)(ii)",
                inputs={
                    "cd_delivery_date": cd_delivery_date.isoformat(),
                    "proposed_closing_date": proposed_closing_date.isoformat(),
                },
            ),
        )

    def check_re_disclosure(
        self,
        circumstance_type: ChangedCircumstanceType,
        circumstance_date: date,
        original_le_date: Optional[date] = None,
        custom_holidays: Optional[FrozenSet[date]] = None,
    ) -> ReDisclosureResult:
        """Calculate re-disclosure deadline for a changed circumstance.

        TRID Rule: When a valid changed circumstance occurs, a revised LE
        must be provided within 3 business days of learning of the change.
        Regulation: 12 CFR 1026.19(e)(4)

        Args:
            circumstance_type: The type of changed circumstance.
            circumstance_date: When the change was identified.
            original_le_date: Date of the original LE (for context).
            custom_holidays: Optional org-level holidays.

        Returns:
            ReDisclosureResult with the re-disclosure deadline.
        """
        deadline = add_business_days(circumstance_date, 3, custom_holidays)

        message = (
            f"Revised LE must be delivered by {deadline.isoformat()} "
            f"due to {circumstance_type.value} on {circumstance_date.isoformat()}."
        )

        return ReDisclosureResult(
            circumstance_type=circumstance_type.value,
            circumstance_date=circumstance_date,
            re_disclosure_deadline=deadline,
            original_le_date=original_le_date,
            message=message,
            audit=AuditMetadata(
                rule="Changed circumstance re-disclosure",
                regulation="12 CFR 1026.19(e)(4)",
                inputs={
                    "circumstance_type": circumstance_type.value,
                    "circumstance_date": circumstance_date.isoformat(),
                    "original_le_date": original_le_date.isoformat() if original_le_date else None,
                },
            ),
        )

    def classify_fee(self, fee_name: str) -> FeeToleranceClassification:
        """Classify a fee into a TRID tolerance bucket.

        Args:
            fee_name: The fee identifier (snake_case or descriptive).

        Returns:
            FeeToleranceClassification with bucket and description.
        """
        normalized = fee_name.lower().strip().replace(" ", "_").replace("-", "_")

        if normalized in ZERO_TOLERANCE_FEES:
            return FeeToleranceClassification(
                fee_name=fee_name,
                bucket=ToleranceBucket.ZERO,
                description=(
                    "Zero tolerance — no increase allowed from LE to CD. "
                    "Lender-controlled fees."
                ),
            )

        if normalized in TEN_PERCENT_TOLERANCE_FEES:
            return FeeToleranceClassification(
                fee_name=fee_name,
                bucket=ToleranceBucket.TEN_PERCENT,
                description=(
                    "10% cumulative tolerance — aggregate increase across "
                    "all fees in this bucket cannot exceed 10% of LE total. "
                    "Third-party fees where lender selected provider."
                ),
            )

        if normalized in UNLIMITED_TOLERANCE_FEES:
            return FeeToleranceClassification(
                fee_name=fee_name,
                bucket=ToleranceBucket.UNLIMITED,
                description=(
                    "Unlimited tolerance — no cap on increase. "
                    "Borrower-shopped services and prepaid items."
                ),
            )

        # Default: if not recognized, classify as unlimited (conservative)
        return FeeToleranceClassification(
            fee_name=fee_name,
            bucket=ToleranceBucket.UNLIMITED,
            description=(
                "Fee not in standard classification — defaulting to "
                "unlimited tolerance. Review manually."
            ),
        )

    def full_trid_check(
        self,
        application_date: Optional[date] = None,
        closing_date: Optional[date] = None,
        le_delivered_date: Optional[date] = None,
        cd_delivered_date: Optional[date] = None,
        custom_holidays: Optional[FrozenSet[date]] = None,
        loan_id: Optional[int] = None,
    ) -> TRIDComplianceReport:
        """Run all applicable TRID checks for a loan's dates.

        Args:
            application_date: When the application was received.
            closing_date: Scheduled closing date.
            le_delivered_date: When the LE was delivered.
            cd_delivered_date: When the CD was delivered.
            custom_holidays: Optional org-level holidays.
            loan_id: Optional loan ID for the report.

        Returns:
            TRIDComplianceReport with all check results.
        """
        report = TRIDComplianceReport(loan_id=loan_id)
        issues: List[str] = []

        # LE deadline check
        if application_date:
            le_result = self.calculate_le_deadline(
                application_date, le_delivered_date, custom_holidays
            )
            report.le_deadline = le_result
            if le_result.is_compliant is False:
                issues.append(f"LE VIOLATION: {le_result.message}")

        # CD deadline check
        if closing_date:
            cd_result = self.calculate_cd_deadline(
                closing_date, cd_delivered_date, custom_holidays
            )
            report.cd_deadline = cd_result
            if cd_result.is_compliant is False:
                issues.append(f"CD VIOLATION: {cd_result.message}")

        # CD waiting period check
        if cd_delivered_date and closing_date:
            waiting = self.check_cd_waiting_period(
                cd_delivered_date, closing_date, custom_holidays
            )
            report.cd_waiting_period = waiting
            if not waiting.can_close:
                issues.append(f"WAITING PERIOD: {waiting.message}")

        report.issues = issues
        report.overall_compliant = len(issues) == 0

        return report
