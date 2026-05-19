"""Auto-generated mixin. See income_trending_service/__init__.py."""
from __future__ import annotations

import json
import logging
import math
import statistics
import time
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from ._types import (
    ZERO, TWO_PLACES, FOUR_PLACES,
    STABLE_VARIANCE_PCT, INCREASING_THRESHOLD_PCT,
    DECLINING_WARN_PCT, DECLINING_CRITICAL_PCT, VOLATILE_CV_THRESHOLD,
    PAYSTUB_TAX_DISCREPANCY_PCT, PAYSTUB_TAX_CRITICAL_PCT,
    DEFAULT_QUALIFYING_DTI, MINIMUM_INCOME_MONTHS_HISTORY,
    SEASONAL_AMPLITUDE_THRESHOLD, PAY_FREQUENCY_MULTIPLIERS,
    BLS_OCCUPATION_PATTERNS,
    TrendClassification, DeclineAction, AlertSeverity, IncomeSourceType,
    IncomeDataPoint, TrendLine, SeasonalPattern, IncomeAlert,
    ReconciliationDiscrepancy, ReconciliationResult, SourceTrend,
    IncomePrediction, ChartDataSeries, ChartData, TrendAnalysis,
)

logger = logging.getLogger(__name__)


class _AnalysisMixin:

    def _analyze_source_trend(
        self,
        source_type: str,
        employer: Optional[str],
        points: List[IncomeDataPoint],
    ) -> SourceTrend:
        """Analyze trend for a single income source."""
        # Convert to monthly series for consistent analysis
        monthly = self._to_monthly_series(points)
        amounts = [float(m["amount"]) for m in monthly]

        # Year-over-year data
        annual_amounts = self._to_annual_amounts(points)
        year1 = annual_amounts.get("year1")
        year2 = annual_amounts.get("year2")
        year3 = annual_amounts.get("year3")

        # YoY change
        yoy_pct = None
        if year1 is not None and year2 is not None and year2 > ZERO:
            yoy_pct = ((year1 - year2) / year2 * 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

        # Classify trend
        classification = self._classify_from_amounts(amounts)

        # Check for insufficient annual data
        if year2 is None and len(amounts) < MINIMUM_INCOME_MONTHS_HISTORY:
            classification = TrendClassification.INSUFFICIENT_DATA

        # Linear regression on monthly data
        trend_line = self._compute_regression(monthly) if len(monthly) >= 3 else None

        # Seasonal pattern detection
        seasonal = self._detect_seasonality(monthly) if len(monthly) >= 12 else None

        # Determine decline action per guidelines
        decline_action = self._determine_decline_action(yoy_pct, year1, year2, year3)

        # Calculate qualifying income for this source
        qualifying = self._source_qualifying_income(
            year1, year2, year3, yoy_pct, decline_action, monthly
        )

        # Build monthly data points for charting
        monthly_chart = [
            {"month": m["month"], "amount": float(m["amount"])}
            for m in monthly
        ]

        # Confidence for this source
        source_confidence = self._source_confidence(
            classification, len(monthly), trend_line, points
        )

        # Flags
        flags: List[str] = []
        if classification == TrendClassification.DECLINING:
            flags.append("DECLINING_INCOME")
        if classification == TrendClassification.VOLATILE:
            flags.append("VOLATILE_INCOME")
        if seasonal and seasonal.is_seasonal:
            flags.append("SEASONAL_INCOME")
        if classification == TrendClassification.INSUFFICIENT_DATA:
            flags.append("INSUFFICIENT_HISTORY")

        notes_parts: List[str] = []
        if decline_action == DeclineAction.USE_MOST_RECENT_12_MONTHS:
            notes_parts.append(
                f"Income declined >{DECLINING_CRITICAL_PCT}% YoY. "
                "Using most recent 12 months per guidelines."
            )
        elif decline_action == DeclineAction.USE_LOWER_OF_AVERAGE_OR_RECENT:
            notes_parts.append(
                f"Income declined {DECLINING_WARN_PCT}-{DECLINING_CRITICAL_PCT}% YoY. "
                "Using lower of 2-year average or most recent year."
            )

        return SourceTrend(
            source_type=source_type,
            employer_name=employer,
            classification=classification,
            trend_line=trend_line,
            seasonal_pattern=seasonal,
            year1_income=year1,
            year2_income=year2,
            year3_income=year3,
            yoy_change_pct=yoy_pct,
            monthly_data_points=monthly_chart,
            qualifying_income_monthly=qualifying,
            decline_action=decline_action,
            confidence=source_confidence,
            flags=flags,
            notes=" ".join(notes_parts),
        )

    # =========================================================================
    # 6. TREND CLASSIFICATION
    # =========================================================================


    def _classify_from_amounts(self, amounts: List[float]) -> TrendClassification:
        """
        Classify trend from a list of periodic income amounts.

        Uses coefficient of variation for volatility detection, and compares
        first-half vs second-half averages for direction.
        """
        if len(amounts) < 2:
            return TrendClassification.INSUFFICIENT_DATA

        mean_val = statistics.mean(amounts)
        if mean_val <= 0:
            return TrendClassification.INSUFFICIENT_DATA

        # Coefficient of variation for volatility
        if len(amounts) >= 3:
            stdev = statistics.stdev(amounts)
            cv = Decimal(str((stdev / mean_val) * 100))
            if cv > VOLATILE_CV_THRESHOLD:
                return TrendClassification.VOLATILE

        # Direction: compare first half vs second half
        midpoint = len(amounts) // 2
        if midpoint == 0:
            midpoint = 1

        first_half_avg = statistics.mean(amounts[:midpoint])
        second_half_avg = statistics.mean(amounts[midpoint:])

        if first_half_avg <= 0:
            return TrendClassification.INSUFFICIENT_DATA

        change_pct = Decimal(str(
            ((second_half_avg - first_half_avg) / first_half_avg) * 100
        ))

        if change_pct < -DECLINING_WARN_PCT:
            return TrendClassification.DECLINING
        elif change_pct > INCREASING_THRESHOLD_PCT:
            return TrendClassification.INCREASING
        else:
            return TrendClassification.STABLE


    def _classify_overall_trend(
        self,
        source_trends: List[SourceTrend],
    ) -> TrendClassification:
        """
        Determine overall trend classification from multiple source trends.

        Weighted by qualifying income contribution.
        """
        if not source_trends:
            return TrendClassification.INSUFFICIENT_DATA

        # If any source is declining, overall is declining (conservative)
        if any(s.classification == TrendClassification.DECLINING for s in source_trends):
            return TrendClassification.DECLINING

        # If all insufficient, overall is insufficient
        if all(s.classification == TrendClassification.INSUFFICIENT_DATA for s in source_trends):
            return TrendClassification.INSUFFICIENT_DATA

        # Weight by qualifying income
        total_qualifying = sum(
            float(s.qualifying_income_monthly) for s in source_trends
            if s.qualifying_income_monthly > ZERO
        )
        if total_qualifying <= 0:
            return TrendClassification.INSUFFICIENT_DATA

        weighted_score = 0.0
        classification_scores = {
            TrendClassification.INCREASING: 2.0,
            TrendClassification.STABLE: 1.0,
            TrendClassification.VOLATILE: -0.5,
            TrendClassification.DECLINING: -2.0,
            TrendClassification.INSUFFICIENT_DATA: 0.0,
        }

        for s in source_trends:
            weight = float(s.qualifying_income_monthly) / total_qualifying if total_qualifying > 0 else 0
            weighted_score += weight * classification_scores.get(s.classification, 0)

        if weighted_score >= 1.5:
            return TrendClassification.INCREASING
        elif weighted_score >= 0.5:
            return TrendClassification.STABLE
        elif weighted_score >= -0.5:
            return TrendClassification.VOLATILE
        else:
            return TrendClassification.DECLINING

    # =========================================================================
    # 7. DECLINING INCOME HANDLING
    # =========================================================================


    def _determine_decline_action(
        self,
        yoy_pct: Optional[Decimal],
        year1: Optional[Decimal],
        year2: Optional[Decimal],
        year3: Optional[Decimal],
    ) -> DeclineAction:
        """
        Determine required action for declining income per Fannie Mae guidelines.

        Rules:
        - 10-20% decline: use lower of 2-year average or most recent year
        - 20%+ decline: use most recent 12 months only
        """
        if yoy_pct is None:
            return DeclineAction.NO_ACTION

        if yoy_pct >= ZERO:
            return DeclineAction.NO_ACTION

        abs_decline = abs(yoy_pct)

        if abs_decline >= DECLINING_CRITICAL_PCT:
            return DeclineAction.USE_MOST_RECENT_12_MONTHS
        elif abs_decline >= DECLINING_WARN_PCT:
            return DeclineAction.USE_LOWER_OF_AVERAGE_OR_RECENT
        else:
            return DeclineAction.NO_ACTION


    def _source_qualifying_income(
        self,
        year1: Optional[Decimal],
        year2: Optional[Decimal],
        year3: Optional[Decimal],
        yoy_pct: Optional[Decimal],
        decline_action: DeclineAction,
        monthly: List[Dict[str, Any]],
    ) -> Decimal:
        """
        Calculate qualifying monthly income for a source, applying decline rules.
        """
        if decline_action == DeclineAction.USE_MOST_RECENT_12_MONTHS:
            # Use only most recent 12 months
            if year1 is not None:
                return (year1 / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            # Fall back to recent monthly data
            recent = monthly[-12:] if len(monthly) >= 12 else monthly
            if recent:
                avg = Decimal(str(statistics.mean([float(m["amount"]) for m in recent])))
                return avg.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            return ZERO

        elif decline_action == DeclineAction.USE_LOWER_OF_AVERAGE_OR_RECENT:
            # Use lower of 2-year average or most recent year
            if year1 is not None and year2 is not None:
                two_year_avg = ((year1 + year2) / 2 / 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                recent_monthly = (year1 / 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                return min(two_year_avg, recent_monthly)
            elif year1 is not None:
                return (year1 / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            return ZERO

        else:
            # Standard: 2-year average if available, else most recent
            if year1 is not None and year2 is not None:
                two_year_avg = (year1 + year2) / 2
                if year3 is not None:
                    # If 3 years available, use weighted: recent year 50%, prior years 25% each
                    three_year_weighted = (year1 * Decimal("0.5")
                                           + year2 * Decimal("0.25")
                                           + year3 * Decimal("0.25"))
                    # Use the higher of 2-year avg and 3-year weighted for stable/increasing
                    if yoy_pct is not None and yoy_pct > ZERO:
                        annual = max(two_year_avg, three_year_weighted)
                    else:
                        annual = two_year_avg
                else:
                    annual = two_year_avg
                return (annual / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            elif year1 is not None:
                return (year1 / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            elif monthly:
                avg = Decimal(str(statistics.mean([float(m["amount"]) for m in monthly])))
                return avg.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            return ZERO

    # =========================================================================
    # 8. LINEAR REGRESSION & PREDICTION
    # =========================================================================


    def _compute_regression(
        self,
        monthly_series: List[Dict[str, Any]],
    ) -> TrendLine:
        """
        Compute simple linear regression on monthly income data.

        Uses the ordinary least squares (OLS) method.
        x = month index (0, 1, 2, ...)
        y = monthly income amount
        """
        n = len(monthly_series)
        if n < 2:
            return TrendLine(
                slope=0.0, intercept=0.0, r_squared=0.0,
                std_error=0.0, slope_pct_per_year=0.0,
                data_point_count=n,
            )

        xs = list(range(n))
        ys = [float(m["amount"]) for m in monthly_series]

        x_mean = statistics.mean(xs)
        y_mean = statistics.mean(ys)

        # Covariance and variance
        ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        ss_yy = sum((y - y_mean) ** 2 for y in ys)

        if ss_xx == 0:
            return TrendLine(
                slope=0.0, intercept=y_mean, r_squared=0.0,
                std_error=0.0, slope_pct_per_year=0.0,
                data_point_count=n,
            )

        slope = ss_xy / ss_xx
        intercept = y_mean - slope * x_mean

        # R-squared
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r_squared = 1 - (ss_res / ss_yy) if ss_yy > 0 else 0.0
        r_squared = max(0.0, min(1.0, r_squared))

        # Standard error of the estimate
        if n > 2:
            std_error = math.sqrt(ss_res / (n - 2))
        else:
            std_error = 0.0

        # Slope as annual percentage change
        if y_mean > 0:
            slope_pct_per_year = (slope * 12 / y_mean) * 100
        else:
            slope_pct_per_year = 0.0

        return TrendLine(
            slope=round(slope, 4),
            intercept=round(intercept, 2),
            r_squared=round(r_squared, 4),
            std_error=round(std_error, 2),
            slope_pct_per_year=round(slope_pct_per_year, 2),
            data_point_count=n,
        )


    def _predict_income(
        self,
        income_data: List[IncomeDataPoint],
        months_forward: int,
        qualifying_monthly_payment: Optional[Decimal],
    ) -> Optional[IncomePrediction]:
        """
        Project future income using linear regression with confidence intervals.
        """
        monthly = self._to_monthly_series(income_data)
        if len(monthly) < 3:
            return None

        trend_line = self._compute_regression(monthly)
        n = len(monthly)
        amounts = [float(m["amount"]) for m in monthly]

        # Project forward from the last observed month
        last_month_idx = n - 1
        future_idx = last_month_idx + months_forward

        projected = trend_line.slope * future_idx + trend_line.intercept
        projected = max(0, projected)  # income cannot be negative for projection

        # Confidence interval using t-distribution approximation
        # For 90% CI with n-2 degrees of freedom
        confidence_level = 0.90
        if n > 2:
            # t-value approximation for 90% CI
            df = n - 2
            t_value = self._t_value_approx(confidence_level, df)
            x_mean = statistics.mean(range(n))
            ss_xx = sum((x - x_mean) ** 2 for x in range(n))

            # Prediction interval (wider than confidence interval)
            if ss_xx > 0:
                se_pred = trend_line.std_error * math.sqrt(
                    1 + 1 / n + (future_idx - x_mean) ** 2 / ss_xx
                )
            else:
                se_pred = trend_line.std_error

            margin = t_value * se_pred
        else:
            margin = abs(projected * 0.2)  # fallback 20% margin

        ci_low = max(0, projected - margin)
        ci_high = projected + margin

        # Determine projection date
        last_month_str = monthly[-1]["month"]  # "YYYY-MM"
        try:
            last_date = datetime.strptime(last_month_str, "%Y-%m").date()
        except (ValueError, TypeError):
            last_date = date.today()

        projection_date = _add_months(last_date, months_forward)

        # Break-even analysis
        break_even_months: Optional[int] = None
        if qualifying_monthly_payment and trend_line.slope < 0:
            # Calculate when projected income crosses below required DTI threshold
            # Assume maximum DTI of 50%: income_needed = payment / 0.50
            min_income_needed = float(qualifying_monthly_payment / DEFAULT_QUALIFYING_DTI * 100)
            if projected > min_income_needed:
                # Solve: slope * (last_month_idx + x) + intercept = min_income_needed
                if trend_line.slope != 0:
                    months_to_break_even = (
                        (min_income_needed - trend_line.intercept) / trend_line.slope
                    ) - last_month_idx
                    if months_to_break_even > 0:
                        break_even_months = int(math.ceil(months_to_break_even))

        # Determine trend basis
        classification = self._classify_from_amounts(amounts)

        return IncomePrediction(
            projected_monthly_income=Decimal(str(round(projected, 2))),
            projected_annual_income=Decimal(str(round(projected * 12, 2))),
            confidence_interval_low=Decimal(str(round(ci_low, 2))),
            confidence_interval_high=Decimal(str(round(ci_high, 2))),
            confidence_level=confidence_level,
            months_forward=months_forward,
            projection_date=projection_date,
            trend_basis=classification,
            break_even_months=break_even_months,
            r_squared=trend_line.r_squared,
            notes=self._prediction_notes(
                trend_line, break_even_months, classification
            ),
        )


    def _prediction_notes(
        self,
        trend_line: TrendLine,
        break_even_months: Optional[int],
        classification: TrendClassification,
    ) -> str:
        """Generate human-readable prediction notes."""
        parts: List[str] = []

        if trend_line.r_squared >= 0.8:
            parts.append("Strong trend fit (R-squared >= 0.80).")
        elif trend_line.r_squared >= 0.5:
            parts.append("Moderate trend fit. Projection has meaningful uncertainty.")
        else:
            parts.append("Weak trend fit. Projection should be treated with caution.")

        if classification == TrendClassification.VOLATILE:
            parts.append("Income is volatile; conservative projections recommended.")

        if break_even_months is not None:
            parts.append(
                f"At current trajectory, income may become insufficient for "
                f"qualification in approximately {break_even_months} months."
            )

        if trend_line.slope_pct_per_year > 5:
            parts.append(
                f"Income growing at {trend_line.slope_pct_per_year}% annually."
            )
        elif trend_line.slope_pct_per_year < -5:
            parts.append(
                f"Income declining at {abs(trend_line.slope_pct_per_year)}% annually."
            )

        return " ".join(parts)

    # =========================================================================
    # 9. PAYSTUB-TO-TAX RECONCILIATION
    # =========================================================================


    def _reconcile_paystub_to_tax(
        self,
        all_data: List[IncomeDataPoint],
    ) -> Optional[ReconciliationResult]:
        """
        Compare YTD paystub income to prior year tax return income.

        Identifies discrepancies > 15% that need explanation.
        """
        paystub_points = [
            p for p in all_data
            if p.source_type == "PAYSTUB" and p.annualized and p.income_component == "total"
        ]
        tax_points = [
            p for p in all_data
            if p.source_type == "TAX_RETURN" and p.annualized and p.income_component == "total"
        ]

        if not paystub_points or not tax_points:
            return None

        # Use most recent paystub annualized income
        paystub_points.sort(key=lambda p: p.period_end, reverse=True)
        latest_paystub = paystub_points[0]
        paystub_annual = latest_paystub.amount

        # Find the most recent prior-year tax return
        tax_points.sort(key=lambda p: p.period_end, reverse=True)
        latest_tax = tax_points[0]
        tax_annual = latest_tax.amount

        if tax_annual <= ZERO and paystub_annual <= ZERO:
            return None

        discrepancies: List[ReconciliationDiscrepancy] = []
        alerts: List[IncomeAlert] = []

        # Overall comparison
        reference = max(paystub_annual, tax_annual)
        if reference > ZERO:
            diff = paystub_annual - tax_annual
            diff_pct = (abs(diff) / reference * 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            diff = ZERO
            diff_pct = ZERO

        if diff_pct > PAYSTUB_TAX_CRITICAL_PCT:
            severity = AlertSeverity.CRITICAL
        elif diff_pct > PAYSTUB_TAX_DISCREPANCY_PCT:
            severity = AlertSeverity.HIGH
        elif diff_pct > Decimal("10"):
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        if diff_pct > PAYSTUB_TAX_DISCREPANCY_PCT:
            explanation = self._explain_discrepancy(
                paystub_annual, tax_annual, diff, latest_paystub, latest_tax
            )

            discrepancies.append(ReconciliationDiscrepancy(
                field="total_annual_income",
                paystub_value=paystub_annual,
                tax_return_value=tax_annual,
                difference=diff,
                difference_pct=diff_pct,
                severity=severity,
                explanation=explanation,
            ))

            if diff > ZERO:
                alert_desc = (
                    f"Paystub annualized income ({_fmt_currency(paystub_annual)}) "
                    f"exceeds tax return income ({_fmt_currency(tax_annual)}) by "
                    f"{diff_pct}%. This may indicate a recent raise, new position, "
                    f"or unreported tax return income."
                )
            else:
                alert_desc = (
                    f"Tax return income ({_fmt_currency(tax_annual)}) exceeds "
                    f"paystub annualized income ({_fmt_currency(paystub_annual)}) by "
                    f"{diff_pct}%. This may indicate additional income sources not "
                    f"reflected on current paystub, or a recent income decrease."
                )

            alerts.append(IncomeAlert(
                severity=severity,
                alert_type="PAYSTUB_TAX_DISCREPANCY",
                title="Income discrepancy between paystub and tax return",
                description=alert_desc,
                recommended_action=(
                    "Obtain letter of explanation from borrower. "
                    "Verify employment dates and income changes."
                ),
                data={
                    "paystub_annual": float(paystub_annual),
                    "tax_annual": float(tax_annual),
                    "difference_pct": float(diff_pct),
                },
            ))

        is_reconciled = diff_pct <= PAYSTUB_TAX_DISCREPANCY_PCT
        confidence = 95 if is_reconciled else max(30, 95 - int(diff_pct))

        return ReconciliationResult(
            is_reconciled=is_reconciled,
            overall_discrepancy_pct=diff_pct,
            discrepancies=discrepancies,
            paystub_annualized_income=paystub_annual,
            tax_return_income=tax_annual,
            alerts=alerts,
            confidence=confidence,
            notes=(
                f"Compared paystub YTD annualized ({_fmt_currency(paystub_annual)}, "
                f"ending {latest_paystub.period_end}) to tax return "
                f"({_fmt_currency(tax_annual)}, year {latest_tax.period_end.year})."
            ),
        )


    def _explain_discrepancy(
        self,
        paystub_val: Decimal,
        tax_val: Decimal,
        diff: Decimal,
        paystub_point: IncomeDataPoint,
        tax_point: IncomeDataPoint,
    ) -> str:
        """Generate a possible explanation for a paystub/tax discrepancy."""
        if diff > ZERO:
            # Paystub higher than tax return
            year_gap = paystub_point.period_end.year - tax_point.period_end.year
            if year_gap >= 2:
                return (
                    f"Paystub is from {paystub_point.period_end.year} but "
                    f"tax return is from {tax_point.period_end.year}. "
                    f"Income may have increased over {year_gap} years."
                )
            return (
                "Paystub annualized income exceeds prior year tax return. "
                "Possible causes: raise, promotion, bonus, or annualization "
                "artifacts from partial-year data."
            )
        else:
            return (
                "Tax return income exceeds current paystub annualized. "
                "Possible causes: job change, reduced hours, loss of "
                "secondary income source, or non-recurring prior year income."
            )

    # =========================================================================
    # 10. SEASONAL PATTERN DETECTION
    # =========================================================================


    def _detect_seasonality(
        self,
        monthly_series: List[Dict[str, Any]],
    ) -> SeasonalPattern:
        """
        Detect seasonal income patterns by comparing monthly deviations
        from the rolling mean.

        Requires at least 12 months of data for meaningful analysis.
        """
        if len(monthly_series) < 12:
            return SeasonalPattern(
                is_seasonal=False,
                peak_months=[],
                trough_months=[],
                amplitude_pct=ZERO,
                pattern_description="Insufficient data for seasonal analysis.",
            )

        # Group amounts by calendar month
        month_groups: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
        for entry in monthly_series:
            month_str = entry["month"]  # "YYYY-MM"
            try:
                month_num = int(month_str.split("-")[1])
                month_groups[month_num].append(float(entry["amount"]))
            except (ValueError, IndexError):
                continue

        # Calculate average per calendar month
        month_avgs: Dict[int, float] = {}
        for month_num, vals in month_groups.items():
            if vals:
                month_avgs[month_num] = statistics.mean(vals)

        if not month_avgs:
            return SeasonalPattern(
                is_seasonal=False,
                peak_months=[],
                trough_months=[],
                amplitude_pct=ZERO,
                pattern_description="No monthly data available.",
            )

        overall_mean = statistics.mean(month_avgs.values())
        if overall_mean <= 0:
            return SeasonalPattern(
                is_seasonal=False,
                peak_months=[],
                trough_months=[],
                amplitude_pct=ZERO,
                pattern_description="Income data is zero or negative.",
            )

        # Calculate deviation from mean per month
        deviations = {
            m: ((avg - overall_mean) / overall_mean) * 100
            for m, avg in month_avgs.items()
        }

        # Find peaks (>10% above mean) and troughs (>10% below mean)
        peak_months = sorted([m for m, d in deviations.items() if d > 10])
        trough_months = sorted([m for m, d in deviations.items() if d < -10])

        # Amplitude: peak-to-trough as % of mean
        if month_avgs:
            max_val = max(month_avgs.values())
            min_val = min(month_avgs.values())
            amplitude_pct = Decimal(str(
                ((max_val - min_val) / overall_mean) * 100
            )).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            amplitude_pct = ZERO

        is_seasonal = amplitude_pct > SEASONAL_AMPLITUDE_THRESHOLD and (
            len(peak_months) >= 1 or len(trough_months) >= 1
        )

        month_names = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]

        if is_seasonal:
            peak_str = ", ".join(month_names[m] for m in peak_months) if peak_months else "none"
            trough_str = ", ".join(month_names[m] for m in trough_months) if trough_months else "none"
            description = (
                f"Seasonal pattern detected (amplitude {amplitude_pct}%). "
                f"Peak months: {peak_str}. Trough months: {trough_str}."
            )
        else:
            description = "No significant seasonal pattern detected."

        return SeasonalPattern(
            is_seasonal=is_seasonal,
            peak_months=peak_months,
            trough_months=trough_months,
            amplitude_pct=amplitude_pct,
            pattern_description=description,
        )

    # =========================================================================
    # 11. INDUSTRY BENCHMARKING
    # =========================================================================


    def _compare_to_industry(
        self,
        source_trends: List[SourceTrend],
        income_data: List[IncomeDataPoint],
    ) -> Optional[Dict[str, Any]]:
        """
        Compare borrower income trends to industry/occupation averages
        using BLS-derived patterns.
        """
        if not source_trends:
            return None

        # Try to determine occupation category from employer names
        occupation = self._infer_occupation(source_trends, income_data)
        pattern = BLS_OCCUPATION_PATTERNS.get(
            occupation, BLS_OCCUPATION_PATTERNS["default"]
        )

        # Calculate borrower's actual metrics
        primary = source_trends[0]  # assume first is primary
        borrower_yoy = float(primary.yoy_change_pct) if primary.yoy_change_pct is not None else 0.0

        # Volatility comparison
        monthly_amounts = [float(m["amount"]) for m in primary.monthly_data_points]
        if len(monthly_amounts) >= 3 and statistics.mean(monthly_amounts) > 0:
            borrower_volatility = (
                statistics.stdev(monthly_amounts) / statistics.mean(monthly_amounts)
            ) * 100
        else:
            borrower_volatility = 0.0

        industry_yoy = pattern["avg_yoy_growth"]
        industry_volatility = pattern["volatility_pct"]

        below_industry_growth = borrower_yoy < industry_yoy - 2.0  # 2% tolerance
        above_industry_volatility = borrower_volatility > industry_volatility * 1.5

        flags: List[str] = []
        if below_industry_growth:
            flags.append("BELOW_INDUSTRY_GROWTH")
        if above_industry_volatility:
            flags.append("ABOVE_INDUSTRY_VOLATILITY")

        return {
            "occupation_category": occupation,
            "borrower_yoy_growth": round(borrower_yoy, 2),
            "industry_avg_yoy_growth": industry_yoy,
            "growth_comparison": "below" if below_industry_growth else "at_or_above",
            "borrower_volatility_pct": round(borrower_volatility, 2),
            "industry_volatility_pct": industry_volatility,
            "volatility_comparison": "above" if above_industry_volatility else "at_or_below",
            "flags": flags,
        }


    def _infer_occupation(
        self,
        source_trends: List[SourceTrend],
        income_data: List[IncomeDataPoint],
    ) -> str:
        """Infer occupation category from employer names and income patterns."""
        employer_names = set()
        for st in source_trends:
            if st.employer_name:
                employer_names.add(st.employer_name.lower())
        for dp in income_data:
            if dp.employer_name:
                employer_names.add(dp.employer_name.lower())

        combined = " ".join(employer_names)

        keyword_map = {
            "healthcare": ["hospital", "medical", "health", "clinic", "pharma", "nurse", "doctor"],
            "technology": ["tech", "software", "digital", "data", "cyber", "cloud", "ai"],
            "finance": ["bank", "capital", "financial", "investment", "credit", "insurance"],
            "education": ["school", "university", "college", "academy", "district"],
            "construction": ["construction", "builder", "contractor", "plumbing", "electric"],
            "sales": ["sales", "retail", "store", "commerce"],
            "real_estate": ["realty", "real estate", "property", "brokerage"],
            "manufacturing": ["manufacturing", "factory", "plant", "assembly"],
            "food_service": ["restaurant", "food", "catering", "hospitality", "hotel"],
            "transportation": ["transport", "logistics", "freight", "trucking", "airline"],
            "legal": ["law", "legal", "attorney", "paralegal"],
            "management": ["management", "consulting", "executive"],
        }

        for category, keywords in keyword_map.items():
            if any(kw in combined for kw in keywords):
                return category

        return "default"

    # =========================================================================
    # 12. MULTI-SOURCE ANALYSIS
    # =========================================================================


    def _calculate_qualifying_income(
        self,
        source_trends: List[SourceTrend],
        overall_classification: TrendClassification,
    ) -> Decimal:
        """
        Calculate total qualifying monthly income across all sources.
        """
        if not source_trends:
            return ZERO

        total = sum(
            (s.qualifying_income_monthly for s in source_trends), ZERO
        )

        # If overall is volatile, apply conservative factor
        if overall_classification == TrendClassification.VOLATILE:
            total = (total * Decimal("0.90")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

        return total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


    def _check_primary_source(
        self,
        source_trends: List[SourceTrend],
    ) -> List[IncomeAlert]:
        """
        Flag if primary income source is declining even if total is increasing.

        This is important because loss of primary income is a significant risk
        even if secondary sources compensate.
        """
        alerts: List[IncomeAlert] = []

        if len(source_trends) < 2:
            return alerts

        # Sort by qualifying income descending to find primary
        sorted_sources = sorted(
            source_trends,
            key=lambda s: s.qualifying_income_monthly,
            reverse=True,
        )
        primary = sorted_sources[0]
        total_qualifying = sum(
            float(s.qualifying_income_monthly) for s in sorted_sources
        )

        if total_qualifying <= 0:
            return alerts

        primary_pct = float(primary.qualifying_income_monthly) / total_qualifying * 100

        # Flag if primary source is declining but total is stable/increasing
        if (
            primary.classification == TrendClassification.DECLINING
            and primary_pct > 40  # primary contributes >40% of total
        ):
            secondary_total = sum(
                float(s.qualifying_income_monthly)
                for s in sorted_sources[1:]
            )
            alerts.append(IncomeAlert(
                severity=AlertSeverity.HIGH,
                alert_type="PRIMARY_SOURCE_DECLINING",
                title="Primary income source declining",
                description=(
                    f"Primary income source ({primary.source_type}"
                    f"{' - ' + primary.employer_name if primary.employer_name else ''}) "
                    f"is declining and represents {primary_pct:.0f}% of total income. "
                    f"Secondary sources ({_fmt_currency(Decimal(str(secondary_total)))}/mo) "
                    f"currently compensate, but primary decline is a risk factor."
                ),
                source_type=primary.source_type,
                recommended_action=(
                    "Verify reason for primary income decline. "
                    "Document whether secondary income sources are stable."
                ),
                data={
                    "primary_pct": round(primary_pct, 1),
                    "primary_classification": primary.classification.value,
                    "primary_yoy_pct": float(primary.yoy_change_pct) if primary.yoy_change_pct else None,
                },
            ))

        return alerts

    # =========================================================================
    # 13. QUALIFICATION RISK
    # =========================================================================


    def _check_qualification_risk(
        self,
        qualifying_monthly: Decimal,
        monthly_payment: Decimal,
        prediction: Optional[IncomePrediction],
    ) -> List[IncomeAlert]:
        """Generate alerts if income drops below qualifying threshold."""
        alerts: List[IncomeAlert] = []

        if qualifying_monthly <= ZERO or monthly_payment <= ZERO:
            return alerts

        # Current DTI check
        current_dti = (monthly_payment / qualifying_monthly * 100).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        if current_dti > DEFAULT_QUALIFYING_DTI:
            alerts.append(IncomeAlert(
                severity=AlertSeverity.CRITICAL,
                alert_type="DTI_EXCEEDS_LIMIT",
                title="DTI exceeds qualifying threshold",
                description=(
                    f"Current back-end DTI of {current_dti}% exceeds the "
                    f"{DEFAULT_QUALIFYING_DTI}% maximum. Monthly income: "
                    f"{_fmt_currency(qualifying_monthly)}, payment: "
                    f"{_fmt_currency(monthly_payment)}."
                ),
                recommended_action="Review income sources, consider additional documentation.",
                data={
                    "current_dti": float(current_dti),
                    "max_dti": float(DEFAULT_QUALIFYING_DTI),
                },
            ))
        elif current_dti > DEFAULT_QUALIFYING_DTI - Decimal("5"):
            alerts.append(IncomeAlert(
                severity=AlertSeverity.MEDIUM,
                alert_type="DTI_NEAR_LIMIT",
                title="DTI approaching qualifying threshold",
                description=(
                    f"Current back-end DTI of {current_dti}% is within 5% of "
                    f"the {DEFAULT_QUALIFYING_DTI}% maximum."
                ),
                recommended_action="Monitor income stability closely.",
                data={"current_dti": float(current_dti)},
            ))

        # Prediction-based alert
        if prediction and prediction.break_even_months is not None:
            severity = (
                AlertSeverity.CRITICAL if prediction.break_even_months <= 6
                else AlertSeverity.HIGH if prediction.break_even_months <= 12
                else AlertSeverity.MEDIUM
            )
            alerts.append(IncomeAlert(
                severity=severity,
                alert_type="INCOME_BREAK_EVEN_WARNING",
                title="Projected income may become insufficient",
                description=(
                    f"At the current income trajectory, income is projected "
                    f"to become insufficient for qualification in approximately "
                    f"{prediction.break_even_months} months."
                ),
                recommended_action=(
                    "Document income trend explanation. "
                    "Consider alternative income documentation."
                ),
                data={
                    "break_even_months": prediction.break_even_months,
                    "projected_monthly": float(prediction.projected_monthly_income),
                },
            ))

        return alerts

    # =========================================================================
    # 14. VISUALIZATION DATA
    # =========================================================================

