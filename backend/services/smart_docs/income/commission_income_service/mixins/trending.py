"""Year-over-year commission income trending analysis."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP
from typing import Any, Dict, List

from .._shared import (
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    TrendAnalysis,
    TrendDirection,
    ZERO,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class TrendingMixin:
    # =========================================================================
    # 2. TRENDING ANALYSIS (public API)
    # =========================================================================

    def analyze_trending(
        self,
        income_history: List[Dict[str, Any]],
    ) -> TrendAnalysis:
        """
        Analyze year-over-year commission income trend.

        Evaluates whether income is increasing, stable, declining, or variable.
        Used to determine whether the 1-year history exception applies and
        which calculation method to use.

        Args:
            income_history: List of dicts with keys:
                - tax_year (int)
                - commission_amount (Decimal or float)
                - total_income (Decimal or float, optional)
                - months_worked (int, optional, defaults to 12)

        Returns:
            TrendAnalysis with direction, percentages, and stability assessment.
        """
        if not income_history:
            return TrendAnalysis(
                direction=TrendDirection.INSUFFICIENT_DATA,
                year1_amount=ZERO,
                year2_amount=None,
                notes="No income history provided.",
            )

        # Sort by tax_year descending (most recent first)
        sorted_history = sorted(
            income_history,
            key=lambda h: h.get("tax_year", 0),
            reverse=True,
        )

        year1 = sorted_history[0]
        year1_amount = _to_decimal(year1.get("commission_amount"))
        year1_months = int(year1.get("months_worked", 12))
        year1_tax_year = year1.get("tax_year")

        # Annualize if partial year
        if 0 < year1_months < 12:
            year1_annualized = (year1_amount / Decimal(year1_months) * MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
        else:
            year1_annualized = year1_amount

        if len(sorted_history) < 2:
            return TrendAnalysis(
                direction=TrendDirection.INSUFFICIENT_DATA,
                year1_amount=year1_annualized,
                year2_amount=None,
                months_of_data=year1_months,
                notes=f"Only {year1_tax_year} data available. 2-year history required for trend.",
            )

        year2 = sorted_history[1]
        year2_amount = _to_decimal(year2.get("commission_amount"))
        year2_months = int(year2.get("months_worked", 12))

        # Annualize year2 if partial
        if 0 < year2_months < 12:
            year2_annualized = (year2_amount / Decimal(year2_months) * MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
        else:
            year2_annualized = year2_amount

        total_months = year1_months + year2_months

        # Year-over-year change percentage
        if year2_annualized > ZERO:
            yoy_pct = (
                (year1_annualized - year2_annualized) / year2_annualized * ONE_HUNDRED
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        elif year1_annualized > ZERO:
            yoy_pct = ONE_HUNDRED  # went from zero to positive
        else:
            yoy_pct = ZERO

        # Determine direction
        if yoy_pct > Decimal("5"):
            direction = TrendDirection.INCREASING
        elif yoy_pct >= Decimal("-5"):
            direction = TrendDirection.STABLE
        else:
            direction = TrendDirection.DECLINING

        # Check for variability (large swings in either direction)
        is_variable = abs(yoy_pct) > Decimal("30")
        if is_variable and direction != TrendDirection.DECLINING:
            direction = TrendDirection.VARIABLE

        is_stable_or_increasing = direction in (
            TrendDirection.INCREASING, TrendDirection.STABLE,
        )

        # YTD comparison if available
        ytd_amount = None
        ytd_annualized = None
        ytd_vs_prior_pct = None
        if len(sorted_history) >= 1:
            ytd_raw = _to_decimal(year1.get("ytd_amount"))
            ytd_months = int(year1.get("ytd_months", 0))
            if ytd_raw > ZERO and ytd_months > 0:
                ytd_amount = ytd_raw
                ytd_annualized = (ytd_raw / Decimal(ytd_months) * MONTHS_PER_YEAR).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                if year1_annualized > ZERO:
                    ytd_vs_prior_pct = (
                        (ytd_annualized - year1_annualized) / year1_annualized * ONE_HUNDRED
                    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        notes_parts = []
        if direction == TrendDirection.DECLINING:
            notes_parts.append(
                f"Commission declined {abs(yoy_pct)}% year-over-year. "
                "Per Fannie Mae B3-3.1, use lower of 2-year average or most recent 12 months."
            )
        if is_variable:
            notes_parts.append(
                "Commission income shows significant variability (>30% swing). "
                "Additional documentation may be required."
            )
        if is_stable_or_increasing:
            notes_parts.append(
                "Commission trend is stable/increasing. "
                "May qualify for 1-year history exception if >= 12 months with same employer."
            )

        return TrendAnalysis(
            direction=direction,
            year1_amount=year1_annualized,
            year2_amount=year2_annualized,
            ytd_amount=ytd_amount,
            ytd_annualized=ytd_annualized,
            yoy_change_pct=yoy_pct,
            ytd_vs_prior_pct=ytd_vs_prior_pct,
            is_stable_or_increasing=is_stable_or_increasing,
            months_of_data=total_months,
            notes=" ".join(notes_parts),
        )
