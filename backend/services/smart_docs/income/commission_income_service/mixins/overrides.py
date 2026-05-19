"""Manual override capability with audit trail."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text

from .._shared import (
    CalculationMethod,
    CommissionIncomeResult,
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    ZERO,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class OverridesMixin:
    # =========================================================================
    # 5. OVERRIDE CAPABILITY
    # =========================================================================

    async def apply_override(
        self,
        calculation_id: str,
        loan_id: int,
        override_monthly_amount: Decimal,
        justification: str,
        approved_by_user_id: int,
    ) -> CommissionIncomeResult:
        """
        Apply a manual override to a commission income calculation.

        Requires justification text and records the override in the audit trail
        for compliance purposes. The original calculation is preserved and the
        override is layered on top.

        Args:
            calculation_id: The ID of the calculation to override.
            loan_id: The loan ID (for org verification).
            override_monthly_amount: The overridden qualifying monthly amount.
            justification: Required written justification for the override.
            approved_by_user_id: User ID of the person approving the override.

        Returns:
            Updated CommissionIncomeResult with override applied.

        Raises:
            ValueError: If justification is empty or amount is negative.
        """
        if not justification or len(justification.strip()) < 10:
            raise ValueError(
                "Override justification must be at least 10 characters. "
                "Provide a detailed explanation for compliance purposes."
            )

        if override_monthly_amount < ZERO:
            raise ValueError("Override amount cannot be negative.")

        self._verify_loan_org(loan_id)

        # Fetch existing calculation
        existing = self.db.execute(
            text("""
                SELECT
                    ic.loan_id, ic.borrower_id,
                    ic.total_qualifying_monthly_income,
                    ic.total_qualifying_annual_income,
                    ic.ai_flags, ic.ai_recommendations,
                    ic.ai_confidence_score,
                    ic.calculation_method
                FROM income_calculations ic
                JOIN loans l ON l.id = ic.loan_id
                WHERE ic.id = :calc_id
                  AND l.organization_id = :org_id
            """),
            {"calc_id": calculation_id, "org_id": self.org_id},
        ).fetchone()

        if not existing:
            raise ValueError(
                f"Calculation {calculation_id} not found or does not belong to this organization."
            )

        override_annual = (override_monthly_amount * MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        original_monthly = _to_decimal(existing.total_qualifying_monthly_income)
        variance_pct = ZERO
        if original_monthly > ZERO:
            variance_pct = (
                (override_monthly_amount - original_monthly) / original_monthly * ONE_HUNDRED
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Persist override
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE income_calculations
                SET total_qualifying_monthly_income = :monthly,
                    total_qualifying_annual_income = :annual,
                    calculation_method = 'override',
                    status = 'override_applied',
                    review_notes = :justification,
                    reviewed_by = :reviewer,
                    reviewed_at = :now,
                    updated_at = :now
                WHERE id = :calc_id
            """),
            {
                "monthly": float(override_monthly_amount),
                "annual": float(override_annual),
                "justification": justification,
                "reviewer": approved_by_user_id,
                "now": now,
                "calc_id": calculation_id,
            },
        )
        self.db.commit()

        logger.info(
            "Commission income override applied: calc_id=%s loan=%s "
            "by_user=%s",
            calculation_id, loan_id,
            approved_by_user_id,
        )

        # Build result reflecting the override
        existing_flags = []
        try:
            existing_flags = json.loads(existing.ai_flags) if existing.ai_flags else []
        except (json.JSONDecodeError, TypeError):
            pass

        override_flag = (
            f"OVERRIDE_APPLIED: Original ${float(original_monthly):,.2f}/mo "
            f"-> ${float(override_monthly_amount):,.2f}/mo "
            f"({'+' if variance_pct >= ZERO else ''}{float(variance_pct):.1f}%)"
        )

        return CommissionIncomeResult(
            loan_id=existing.loan_id,
            borrower_id=existing.borrower_id,
            org_id=self.org_id,
            calculation_id=calculation_id,
            total_qualifying_monthly_commission=override_monthly_amount,
            total_qualifying_monthly=override_monthly_amount,
            total_qualifying_annual=override_annual,
            primary_calculation_method=CalculationMethod.OVERRIDE,
            confidence=100,  # Manual override = full confidence
            flags=existing_flags + [override_flag],
            override_applied=True,
            audit_trail=[{
                "event": "override_applied",
                "timestamp": now.isoformat(),
                "user_id": approved_by_user_id,
                "original_monthly": float(original_monthly),
                "override_monthly": float(override_monthly_amount),
                "variance_pct": float(variance_pct),
                "justification": justification,
            }],
        )
