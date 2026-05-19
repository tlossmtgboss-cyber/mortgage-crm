"""Unreimbursed business expense analysis (Form 2106 / Schedule C)."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from .._shared import (
    ExpenseAnalysis,
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    UBE_DEDUCTION_THRESHOLD_PCT,
    ZERO,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class ExpensesMixin:
    # =========================================================================
    # 3. UNREIMBURSED BUSINESS EXPENSES (public API)
    # =========================================================================

    def calculate_unreimbursed_expenses(
        self,
        tax_data: List[Dict[str, Any]],
    ) -> ExpenseAnalysis:
        """
        Analyze unreimbursed business expenses from Form 2106 / Schedule A.

        Per Fannie Mae guidelines, if unreimbursed business expenses exceed
        25% of gross commission income, the excess must be deducted from
        qualifying income.

        For tax years 2018+ (TCJA), employee business expenses on 2106 are
        no longer deductible on Schedule A. However, self-employed commission
        agents still deduct on Schedule C. This method handles both scenarios.

        Args:
            tax_data: List of dicts with keys:
                - tax_year (int)
                - gross_commission (Decimal or float)
                - form_2106_expenses (Decimal or float, optional)
                - schedule_c_expenses (Decimal or float, optional)
                - schedule_a_employee_expenses (Decimal or float, optional)
                - expense_categories (dict of category->amount, optional)

        Returns:
            ExpenseAnalysis with deduction amount and breakdown.
        """
        if not tax_data:
            return ExpenseAnalysis(
                gross_commission=ZERO,
                total_expenses=ZERO,
                expense_ratio_pct=ZERO,
                exceeds_threshold=False,
                deduction_amount=ZERO,
                notes="No tax data provided for expense analysis.",
            )

        # Aggregate across all provided tax years using 2-year average
        total_gross = ZERO
        total_expenses = ZERO
        all_categories: Dict[str, Decimal] = {}
        years_analyzed: List[int] = []

        for entry in tax_data:
            tax_year = entry.get("tax_year")
            if tax_year:
                years_analyzed.append(int(tax_year))

            gross = _to_decimal(entry.get("gross_commission"))
            total_gross += gross

            # Gather expenses from all possible sources
            form_2106 = _to_decimal(entry.get("form_2106_expenses"))
            schedule_c = _to_decimal(entry.get("schedule_c_expenses"))
            schedule_a = _to_decimal(entry.get("schedule_a_employee_expenses"))

            year_expenses = form_2106 + schedule_c + schedule_a
            total_expenses += year_expenses

            # Aggregate categories
            cats = entry.get("expense_categories", {})
            if isinstance(cats, dict):
                for cat_name, cat_amount in cats.items():
                    cat_dec = _to_decimal(cat_amount)
                    all_categories[cat_name] = all_categories.get(cat_name, ZERO) + cat_dec

        num_years = max(1, len(years_analyzed))
        avg_gross = (total_gross / Decimal(num_years)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        avg_expenses = (total_expenses / Decimal(num_years)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Calculate expense ratio
        if avg_gross > ZERO:
            expense_ratio = (avg_expenses / avg_gross * ONE_HUNDRED).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
        else:
            expense_ratio = ZERO

        exceeds_threshold = expense_ratio > UBE_DEDUCTION_THRESHOLD_PCT

        # Calculate monthly deduction amount
        # Deduct the average annual expenses / 12 from qualifying income
        if exceeds_threshold:
            deduction_amount = (avg_expenses / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
        else:
            deduction_amount = ZERO

        notes_parts = []
        if exceeds_threshold:
            notes_parts.append(
                f"Unreimbursed business expenses are {expense_ratio}% of gross commission "
                f"(threshold: {UBE_DEDUCTION_THRESHOLD_PCT}%). Monthly deduction of "
                f"${float(deduction_amount):,.2f} applied to qualifying income."
            )
        else:
            notes_parts.append(
                f"Unreimbursed business expenses are {expense_ratio}% of gross commission "
                f"(below {UBE_DEDUCTION_THRESHOLD_PCT}% threshold). No deduction required."
            )

        if any(y >= 2018 for y in years_analyzed):
            notes_parts.append(
                "Note: For tax years 2018+, employee Form 2106 expenses are not "
                "deductible under TCJA. Only Schedule C expenses apply for self-employed."
            )

        # Average categories for reporting
        avg_categories = {
            k: (v / Decimal(num_years)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            for k, v in all_categories.items()
        }

        return ExpenseAnalysis(
            gross_commission=avg_gross,
            total_expenses=avg_expenses,
            expense_ratio_pct=expense_ratio,
            exceeds_threshold=exceeds_threshold,
            deduction_amount=deduction_amount,
            expense_categories=avg_categories,
            tax_years_analyzed=sorted(years_analyzed),
            notes=" ".join(notes_parts),
        )
