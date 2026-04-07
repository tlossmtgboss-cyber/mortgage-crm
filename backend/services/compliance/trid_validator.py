"""
TRID Fee Tolerance Validation Service

Validates fee changes between the initial Loan Estimate (LE) and final
Closing Disclosure (CD) per TILA-RESPA Integrated Disclosure rules
(12 CFR 1026.19(e)(3)).

Three tolerance buckets:
    - Zero tolerance (0%): Fees the lender controls -- origination charges,
      points, transfer taxes when seller pays.
    - 10% tolerance: Third-party fees where lender selected the provider
      AND borrower did not shop.  This is an AGGREGATE cap across all fees
      in the bucket, not per-line-item.
    - Unlimited tolerance: Fees the borrower shopped for, insurance
      premiums, owner's title insurance.

Usage:
    from services.compliance.trid_validator import TRIDValidator

    validator = TRIDValidator()
    result = validator.validate(db, loan_id)
    # result = {
    #     "compliant": True/False,
    #     "loan_id": 123,
    #     "violations": [...],
    #     "summary": {...},
    # }
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TRIDValidator:
    """Validates TRID fee tolerance between LE and CD."""

    def validate(self, db: Session, loan_id: int, organization_id: Optional[int] = None) -> dict:
        """Run full TRID fee tolerance validation for a loan.

        Args:
            db: Database session.
            loan_id: The loan to validate.
            organization_id: Optional org filter for tenant isolation.

        Returns:
            Structured result with compliant flag, violations list, and summary.
        """
        from database.models.lead_loan import Loan
        from database.models.compliance import LoanFee, ToleranceCategory

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
                "violations": [],
                "summary": {},
            }

        # Load all fees for this loan
        fees = db.query(LoanFee).filter(LoanFee.loan_id == loan_id).all()
        if not fees:
            return {
                "compliant": True,
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "message": "No fee records found for TRID validation",
                "violations": [],
                "summary": {
                    "total_fees": 0,
                    "zero_tolerance_fees": 0,
                    "ten_percent_fees": 0,
                    "unlimited_fees": 0,
                },
            }

        violations = []

        # Categorize fees by tolerance bucket
        zero_fees = []
        ten_pct_fees = []
        unlimited_fees = []

        for fee in fees:
            cat = fee.tolerance_category
            if cat == ToleranceCategory.ZERO:
                zero_fees.append(fee)
            elif cat == ToleranceCategory.TEN_PERCENT:
                ten_pct_fees.append(fee)
            elif cat == ToleranceCategory.UNLIMITED:
                unlimited_fees.append(fee)

        # -----------------------------------------------------------------
        # Zero-tolerance bucket: NO increase allowed per line item
        # -----------------------------------------------------------------
        for fee in zero_fees:
            le_amount = self._to_decimal(fee.le_amount)
            # Use revised LE amount if a valid changed-circumstance revision exists
            if fee.le_revision_amount is not None and fee.le_revision_reason:
                le_amount = self._to_decimal(fee.le_revision_amount)
            cd_amount = self._to_decimal(fee.cd_amount)

            if cd_amount is None:
                # CD not yet issued -- skip
                continue

            variance = cd_amount - le_amount
            if variance > Decimal("0"):
                violations.append({
                    "fee_name": fee.fee_name,
                    "fee_id": fee.id,
                    "le_amount": float(le_amount),
                    "cd_amount": float(cd_amount),
                    "tolerance_bucket": "zero",
                    "allowed_increase": 0.0,
                    "exceeded_by": float(variance),
                    "cure_amount": float(variance),
                    "message": (
                        f"Zero-tolerance violation: '{fee.fee_name}' increased "
                        f"by ${variance:.2f} (LE: ${le_amount:.2f}, CD: ${cd_amount:.2f})"
                    ),
                })

                # Mark violation on the fee record
                fee.variance = variance
                fee.cure_amount = variance
                fee.is_violation = True

        # -----------------------------------------------------------------
        # 10% tolerance bucket: AGGREGATE increase capped at 10% of LE total
        # -----------------------------------------------------------------
        ten_pct_le_total = Decimal("0")
        ten_pct_cd_total = Decimal("0")
        ten_pct_items = []

        for fee in ten_pct_fees:
            le_amount = self._to_decimal(fee.le_amount)
            if fee.le_revision_amount is not None and fee.le_revision_reason:
                le_amount = self._to_decimal(fee.le_revision_amount)
            cd_amount = self._to_decimal(fee.cd_amount)

            if cd_amount is None:
                continue

            ten_pct_le_total += le_amount
            ten_pct_cd_total += cd_amount
            ten_pct_items.append({
                "fee_name": fee.fee_name,
                "fee_id": fee.id,
                "le_amount": float(le_amount),
                "cd_amount": float(cd_amount),
            })

            # Track variance on each fee
            fee.variance = cd_amount - le_amount

        aggregate_variance = ten_pct_cd_total - ten_pct_le_total
        ten_pct_threshold = ten_pct_le_total * Decimal("0.10")

        if aggregate_variance > ten_pct_threshold and ten_pct_le_total > 0:
            exceeded_by = aggregate_variance - ten_pct_threshold
            violations.append({
                "fee_name": "__aggregate_10pct__",
                "tolerance_bucket": "ten_percent",
                "le_total": float(ten_pct_le_total),
                "cd_total": float(ten_pct_cd_total),
                "aggregate_variance": float(aggregate_variance),
                "allowed_increase": float(ten_pct_threshold),
                "exceeded_by": float(exceeded_by),
                "cure_amount": float(exceeded_by),
                "items": ten_pct_items,
                "message": (
                    f"10% aggregate tolerance violated: total increase "
                    f"${aggregate_variance:.2f} exceeds 10% cap of "
                    f"${ten_pct_threshold:.2f} (LE total: ${ten_pct_le_total:.2f})"
                ),
            })

            # Mark all 10% bucket fees as violations
            for fee in ten_pct_fees:
                fee.is_violation = True
                if fee.variance and fee.variance > 0:
                    # Distribute cure proportionally
                    if aggregate_variance > 0:
                        fee.cure_amount = (fee.variance / aggregate_variance) * exceeded_by

        # -----------------------------------------------------------------
        # Unlimited tolerance bucket: just track, no violations
        # -----------------------------------------------------------------
        unlimited_items = []
        for fee in unlimited_fees:
            le_amount = self._to_decimal(fee.le_amount)
            cd_amount = self._to_decimal(fee.cd_amount)
            if cd_amount is not None:
                fee.variance = cd_amount - le_amount
                fee.is_violation = False
                unlimited_items.append({
                    "fee_name": fee.fee_name,
                    "fee_id": fee.id,
                    "le_amount": float(le_amount),
                    "cd_amount": float(cd_amount),
                    "variance": float(fee.variance),
                })

        compliant = len(violations) == 0

        # Log compliance decision
        self._log_compliance_decision(
            db, loan_id, loan.organization_id, compliant, violations
        )

        return {
            "compliant": compliant,
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "violations": violations,
            "summary": {
                "total_fees": len(fees),
                "zero_tolerance_fees": len(zero_fees),
                "ten_percent_fees": len(ten_pct_fees),
                "unlimited_fees": len(unlimited_fees),
                "zero_tolerance_violations": sum(
                    1 for v in violations if v.get("tolerance_bucket") == "zero"
                ),
                "ten_percent_aggregate_violated": any(
                    v.get("tolerance_bucket") == "ten_percent" for v in violations
                ),
                "ten_percent_le_total": float(ten_pct_le_total),
                "ten_percent_cd_total": float(ten_pct_cd_total),
                "ten_percent_threshold": float(ten_pct_threshold),
                "total_cure_amount": sum(
                    v.get("cure_amount", 0) for v in violations
                ),
                "unlimited_items": unlimited_items,
            },
        }

    def _to_decimal(self, value) -> Decimal:
        """Safely convert a fee value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def _log_compliance_decision(
        self, db: Session, loan_id: int, organization_id: int,
        compliant: bool, violations: list,
    ):
        """Log TRID validation decision to the compliance audit log."""
        try:
            from database.models.compliance_log import ComplianceDecisionLog

            log_entry = ComplianceDecisionLog(
                organization_id=organization_id,
                decision_type="trid_fee_tolerance",
                contact_id=loan_id,
                decision="allowed" if compliant else "blocked",
                reason=(
                    "TRID fee tolerance validation passed"
                    if compliant
                    else f"TRID violations found: {len(violations)} issue(s)"
                ),
                details={
                    "loan_id": loan_id,
                    "violation_count": len(violations),
                    "violations": [
                        {
                            "fee_name": v.get("fee_name"),
                            "bucket": v.get("tolerance_bucket"),
                            "exceeded_by": v.get("exceeded_by"),
                        }
                        for v in violations
                    ],
                },
            )
            db.add(log_entry)
        except Exception as e:
            logger.warning(f"Failed to log TRID compliance decision: {e}")
