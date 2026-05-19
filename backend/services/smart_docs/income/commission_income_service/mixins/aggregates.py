"""Aggregate helpers across sources (totals, confidence, trends, methods)."""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from sqlalchemy import text

from .._shared import (
    CalculationMethod,
    CommissionSource,
    MONTHS_PER_YEAR,
    TWO_PLACES,
    TrendDirection,
    ZERO,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class AggregatesMixin:
    # =========================================================================
    # INTERNAL: AGGREGATE HELPERS
    # =========================================================================

    def _get_borrower_total_income(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> Decimal:
        """
        Fetch the borrower's total qualifying monthly income from the most
        recent income_calculations record (if it exists). Used to calculate
        commission-to-total-income ratio.
        """
        row = self.db.execute(
            text("""
                SELECT total_qualifying_monthly_income
                FROM income_calculations
                WHERE loan_id = :loan_id
                  AND borrower_id = :borrower_id
                  AND status NOT IN ('rejected', 'superseded')
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id, "borrower_id": borrower_id},
        ).fetchone()

        if row and row.total_qualifying_monthly_income:
            return _to_decimal(row.total_qualifying_monthly_income)

        return ZERO

    def _determine_primary_method(
        self,
        sources: List[CommissionSource],
    ) -> CalculationMethod:
        """Determine the primary calculation method from all sources."""
        if not sources:
            return CalculationMethod.SIMPLE_AVERAGE

        # Use method of the source with the highest qualifying amount
        primary = max(sources, key=lambda s: s.qualifying_monthly_total)
        return primary.calculation_method

    def _determine_overall_trend(
        self,
        sources: List[CommissionSource],
    ) -> TrendDirection:
        """Determine overall trend from all sources."""
        if not sources:
            return TrendDirection.INSUFFICIENT_DATA

        directions = [
            s.trend_analysis.direction
            for s in sources
            if s.trend_analysis
        ]

        if not directions:
            return TrendDirection.INSUFFICIENT_DATA

        # If any source is declining, overall is declining
        if TrendDirection.DECLINING in directions:
            return TrendDirection.DECLINING

        if TrendDirection.VARIABLE in directions:
            return TrendDirection.VARIABLE

        if all(d == TrendDirection.INCREASING for d in directions):
            return TrendDirection.INCREASING

        if all(d in (TrendDirection.STABLE, TrendDirection.INCREASING) for d in directions):
            return TrendDirection.STABLE

        return TrendDirection.VARIABLE

    def _calculate_aggregate_confidence(
        self,
        sources: List[CommissionSource],
    ) -> int:
        """Calculate weighted average confidence across all sources."""
        if not sources:
            return 0

        total_weight = sum(
            float(s.qualifying_monthly_total)
            for s in sources
            if s.qualifying_monthly_total > ZERO
        ) or 1.0

        weighted = sum(
            s.confidence * (float(s.qualifying_monthly_total) / total_weight)
            for s in sources
            if s.qualifying_monthly_total > ZERO
        )

        return min(100, max(0, int(weighted)))

    def _calculate_source_confidence(
        self,
        has_w2: bool,
        has_paystub: bool,
        has_voe: bool,
        has_two_years: bool,
        trend: TrendAnalysis,
        commission_derived: bool,
    ) -> int:
        """
        Calculate confidence score (0-100) for a single commission source.

        Scoring:
        - Base: 30 (documents exist with extractable data)
        - W-2 present: +15
        - Paystub present: +10
        - VOE present: +10
        - 2-year history: +15
        - Stable/increasing trend: +10
        - Commission explicitly stated (not derived): +10
        """
        score = 30  # Base

        if has_w2:
            score += 15
        if has_paystub:
            score += 10
        if has_voe:
            score += 10
        if has_two_years:
            score += 15
        if trend.is_stable_or_increasing:
            score += 10
        if not commission_derived:
            score += 10

        # Penalties
        if trend.direction == TrendDirection.DECLINING:
            score -= 10
        if trend.direction == TrendDirection.VARIABLE:
            score -= 5

        return min(100, max(0, score))

    # =========================================================================
