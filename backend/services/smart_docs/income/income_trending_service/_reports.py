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


class _ReportsMixin:

    def _build_chart_data(
        self,
        source_trends: List[SourceTrend],
        prediction: Optional[IncomePrediction],
        income_data: List[IncomeDataPoint],
    ) -> ChartData:
        """Build visualization-ready chart data."""
        series: List[ChartDataSeries] = []
        annotations: List[Dict[str, Any]] = []

        if not source_trends:
            return ChartData(
                series=[], annotations=[], summary_stats={"data_points": 0},
                date_range={"start": "", "end": ""},
            )

        # Series 1: Actual monthly income per source
        color_hints = ["primary", "secondary", "tertiary", "quaternary"]
        for idx, st in enumerate(source_trends):
            label = st.source_type
            if st.employer_name:
                label = f"{st.employer_name} ({st.source_type})"

            data_points = [
                {"x": m["month"], "y": m["amount"]}
                for m in st.monthly_data_points
            ]

            series.append(ChartDataSeries(
                label=label,
                data_points=data_points,
                line_type="solid",
                color_hint=color_hints[idx % len(color_hints)],
            ))

            # Trend line overlay
            if st.trend_line and st.trend_line.r_squared >= 0.3:
                trend_points = []
                for i, m in enumerate(st.monthly_data_points):
                    projected = st.trend_line.slope * i + st.trend_line.intercept
                    trend_points.append({
                        "x": m["month"],
                        "y": round(max(0, projected), 2),
                    })

                series.append(ChartDataSeries(
                    label=f"{label} (trend)",
                    data_points=trend_points,
                    line_type="dashed",
                    color_hint=color_hints[idx % len(color_hints)],
                ))

        # Series: Total income if multiple sources
        if len(source_trends) > 1:
            total_monthly = self._aggregate_monthly_series(source_trends)
            series.append(ChartDataSeries(
                label="Total Income",
                data_points=[
                    {"x": m["month"], "y": m["amount"]} for m in total_monthly
                ],
                line_type="solid",
                color_hint="accent",
            ))

        # Series: Prediction (future projection)
        if prediction and source_trends:
            last_trend = source_trends[0]
            if last_trend.monthly_data_points:
                last_month = last_trend.monthly_data_points[-1]["month"]
                projection_points = [
                    {"x": last_month, "y": float(prediction.projected_monthly_income)}
                ]
                proj_date = prediction.projection_date
                projection_points.append({
                    "x": proj_date.strftime("%Y-%m"),
                    "y": float(prediction.projected_monthly_income),
                })

                series.append(ChartDataSeries(
                    label="Projected Income",
                    data_points=projection_points,
                    line_type="dotted",
                    color_hint="info",
                ))

                # Confidence band
                series.append(ChartDataSeries(
                    label="Confidence Band (Low)",
                    data_points=[
                        {"x": last_month, "y": float(prediction.confidence_interval_low)},
                        {"x": proj_date.strftime("%Y-%m"), "y": float(prediction.confidence_interval_low)},
                    ],
                    line_type="dotted",
                    color_hint="muted",
                ))
                series.append(ChartDataSeries(
                    label="Confidence Band (High)",
                    data_points=[
                        {"x": last_month, "y": float(prediction.confidence_interval_high)},
                        {"x": proj_date.strftime("%Y-%m"), "y": float(prediction.confidence_interval_high)},
                    ],
                    line_type="dotted",
                    color_hint="muted",
                ))

        # Annotations
        for st in source_trends:
            if st.seasonal_pattern and st.seasonal_pattern.is_seasonal:
                annotations.append({
                    "type": "info",
                    "label": f"Seasonal pattern detected ({st.source_type})",
                    "description": st.seasonal_pattern.pattern_description,
                })

            if st.classification == TrendClassification.DECLINING:
                annotations.append({
                    "type": "warning",
                    "label": f"Declining trend ({st.source_type})",
                    "description": f"YoY change: {st.yoy_change_pct}%",
                })

        # Determine date range
        all_months = []
        for st in source_trends:
            for m in st.monthly_data_points:
                all_months.append(m["month"])
        all_months.sort()
        date_range = {
            "start": all_months[0] if all_months else "",
            "end": all_months[-1] if all_months else "",
        }

        # Summary stats
        all_amounts = []
        for st in source_trends:
            all_amounts.extend([m["amount"] for m in st.monthly_data_points])

        summary_stats = {
            "data_points": len(all_amounts),
            "sources": len(source_trends),
        }
        if all_amounts:
            summary_stats.update({
                "min_monthly": round(min(all_amounts), 2),
                "max_monthly": round(max(all_amounts), 2),
                "avg_monthly": round(statistics.mean(all_amounts), 2),
                "median_monthly": round(statistics.median(all_amounts), 2),
            })

        return ChartData(
            series=series,
            annotations=annotations,
            summary_stats=summary_stats,
            date_range=date_range,
        )


    def _aggregate_monthly_series(
        self,
        source_trends: List[SourceTrend],
    ) -> List[Dict[str, Any]]:
        """Aggregate monthly data across multiple sources."""
        month_totals: Dict[str, float] = {}

        for st in source_trends:
            for m in st.monthly_data_points:
                month_key = m["month"]
                month_totals[month_key] = month_totals.get(month_key, 0) + m["amount"]

        return [
            {"month": month, "amount": round(total, 2)}
            for month, total in sorted(month_totals.items())
        ]

    # =========================================================================
    # 15. ALERTS, FLAGS, AND TASKS
    # =========================================================================


    def _generate_source_alerts(
        self,
        trend: SourceTrend,
    ) -> List[IncomeAlert]:
        """Generate alerts for a single source trend."""
        alerts: List[IncomeAlert] = []

        source_label = trend.source_type
        if trend.employer_name:
            source_label = f"{trend.employer_name} ({trend.source_type})"

        if trend.classification == TrendClassification.DECLINING:
            decline_pct = abs(float(trend.yoy_change_pct)) if trend.yoy_change_pct else 0

            if decline_pct >= float(DECLINING_CRITICAL_PCT):
                alerts.append(IncomeAlert(
                    severity=AlertSeverity.CRITICAL,
                    alert_type="CRITICAL_INCOME_DECLINE",
                    title=f"Critical income decline: {source_label}",
                    description=(
                        f"Income from {source_label} has declined {decline_pct:.1f}% "
                        f"year-over-year (>{DECLINING_CRITICAL_PCT}%). "
                        f"Per guidelines, only the most recent 12 months of income "
                        f"may be used for qualification."
                    ),
                    source_type=trend.source_type,
                    recommended_action=(
                        "Obtain written explanation for income decline. "
                        "Use most recent 12-month income only. "
                        "Document whether decline is temporary or permanent."
                    ),
                    data={
                        "decline_pct": decline_pct,
                        "year1": float(trend.year1_income) if trend.year1_income else None,
                        "year2": float(trend.year2_income) if trend.year2_income else None,
                        "action": trend.decline_action.value,
                    },
                ))
            elif decline_pct >= float(DECLINING_WARN_PCT):
                alerts.append(IncomeAlert(
                    severity=AlertSeverity.HIGH,
                    alert_type="DECLINING_INCOME",
                    title=f"Declining income: {source_label}",
                    description=(
                        f"Income from {source_label} has declined {decline_pct:.1f}% "
                        f"year-over-year. Per guidelines, use the lower of the 2-year "
                        f"average or the most recent year."
                    ),
                    source_type=trend.source_type,
                    recommended_action=(
                        "Obtain written explanation for income decline. "
                        "Use lower of 2-year average or most recent year."
                    ),
                    data={
                        "decline_pct": decline_pct,
                        "action": trend.decline_action.value,
                    },
                ))

        if trend.classification == TrendClassification.VOLATILE:
            alerts.append(IncomeAlert(
                severity=AlertSeverity.MEDIUM,
                alert_type="VOLATILE_INCOME",
                title=f"Volatile income: {source_label}",
                description=(
                    f"Income from {source_label} shows high variance with no "
                    f"clear trend. Conservative income calculation will be used."
                ),
                source_type=trend.source_type,
                recommended_action=(
                    "Use 2-year average with conservative adjustments. "
                    "Document income variability reasons."
                ),
            ))

        if trend.seasonal_pattern and trend.seasonal_pattern.is_seasonal:
            alerts.append(IncomeAlert(
                severity=AlertSeverity.INFO,
                alert_type="SEASONAL_INCOME_DETECTED",
                title=f"Seasonal income pattern: {source_label}",
                description=trend.seasonal_pattern.pattern_description,
                source_type=trend.source_type,
                recommended_action=(
                    "Verify seasonal employment. "
                    "Use 12-month or 24-month average for qualification."
                ),
            ))

        if trend.classification == TrendClassification.INSUFFICIENT_DATA:
            alerts.append(IncomeAlert(
                severity=AlertSeverity.MEDIUM,
                alert_type="INSUFFICIENT_INCOME_HISTORY",
                title=f"Insufficient income history: {source_label}",
                description=(
                    f"Less than 2 years of income history available for "
                    f"{source_label}. Trend analysis is limited."
                ),
                source_type=trend.source_type,
                recommended_action=(
                    "Obtain additional income documentation. "
                    "At minimum, 2 years of W2s and most recent paystub required."
                ),
            ))

        return alerts


    def _collect_flags(
        self,
        source_trends: List[SourceTrend],
        alerts: List[IncomeAlert],
        reconciliation: Optional[ReconciliationResult],
    ) -> List[str]:
        """Collect all unique flags from analysis components."""
        flags: List[str] = []

        for st in source_trends:
            flags.extend(st.flags)

        for alert in alerts:
            flags.append(alert.alert_type)

        if reconciliation and not reconciliation.is_reconciled:
            flags.append("PAYSTUB_TAX_DISCREPANCY")

        # Deduplicate while preserving order
        seen = set()
        unique_flags = []
        for f in flags:
            if f not in seen:
                seen.add(f)
                unique_flags.append(f)

        return unique_flags


    def _generate_tasks(
        self,
        source_trends: List[SourceTrend],
        alerts: List[IncomeAlert],
        flags: List[str],
    ) -> List[Dict[str, Any]]:
        """Generate LO review tasks based on analysis findings."""
        tasks: List[Dict[str, Any]] = []

        if "DECLINING_INCOME" in flags or "CRITICAL_INCOME_DECLINE" in flags:
            tasks.append({
                "task_type": "income_review",
                "title": "Review declining income trend",
                "description": (
                    "Income is declining year-over-year. Obtain letter of "
                    "explanation from borrower documenting the reason for "
                    "decline and whether it is temporary or permanent."
                ),
                "priority": "high",
                "ai_recommendation": (
                    "Request written LOE. If decline is temporary (e.g., "
                    "medical leave, maternity), document the expected return "
                    "date. If permanent, use most recent income."
                ),
            })

        if "PAYSTUB_TAX_DISCREPANCY" in flags:
            tasks.append({
                "task_type": "income_verification",
                "title": "Reconcile paystub and tax return discrepancy",
                "description": (
                    "Significant discrepancy between paystub annualized income "
                    "and prior year tax return. Verify income changes and obtain "
                    "explanation."
                ),
                "priority": "high",
                "ai_recommendation": (
                    "Compare employer, position, and pay rate between documents. "
                    "Look for job changes, raises, or additional income sources."
                ),
            })

        if "VOLATILE_INCOME" in flags:
            tasks.append({
                "task_type": "income_review",
                "title": "Document volatile income pattern",
                "description": (
                    "Income shows high variability. Document the nature of the "
                    "income and verify it is likely to continue."
                ),
                "priority": "medium",
                "ai_recommendation": (
                    "For commission/bonus income, verify 2-year history. "
                    "For seasonal employment, confirm off-season income."
                ),
            })

        if "SEASONAL_INCOME" in flags:
            tasks.append({
                "task_type": "income_review",
                "title": "Verify seasonal income pattern",
                "description": "Seasonal income pattern detected. Verify employment terms.",
                "priority": "medium",
            })

        if "INSUFFICIENT_HISTORY" in flags:
            tasks.append({
                "task_type": "missing_documents",
                "title": "Additional income documentation needed",
                "description": (
                    "Less than 2 years of income history available. Request "
                    "additional W2s, tax returns, or employment verification."
                ),
                "priority": "medium",
            })

        if "PRIMARY_SOURCE_DECLINING" in flags:
            tasks.append({
                "task_type": "income_review",
                "title": "Primary income source declining",
                "description": (
                    "Primary income source is declining even though total income "
                    "may be stable. Investigate root cause and sustainability of "
                    "secondary income sources."
                ),
                "priority": "high",
            })

        return tasks

    # =========================================================================
    # 16. CONFIDENCE SCORING
    # =========================================================================


    def _calculate_confidence(
        self,
        source_trends: List[SourceTrend],
        income_data: List[IncomeDataPoint],
    ) -> int:
        """
        Calculate overall confidence score (0-100).

        Factors:
        - Number of data points
        - Source diversity (multiple doc types)
        - Trend line fit quality
        - Recency of data
        """
        if not source_trends:
            return 0

        # Base: weighted average of source confidences
        total_income = sum(
            float(s.qualifying_income_monthly) for s in source_trends
            if s.qualifying_income_monthly > ZERO
        )
        if total_income > 0:
            base_confidence = sum(
                s.confidence * (float(s.qualifying_income_monthly) / total_income)
                for s in source_trends
                if s.qualifying_income_monthly > ZERO
            )
        else:
            base_confidence = sum(s.confidence for s in source_trends) / len(source_trends)

        # Bonus: multiple document types increase confidence
        source_types = {p.source_type for p in income_data}
        if len(source_types) >= 3:
            base_confidence += 5
        elif len(source_types) >= 2:
            base_confidence += 3

        # Bonus: recent data (within 60 days)
        today = date.today()
        recent = any(
            (today - p.period_end).days <= 60
            for p in income_data
        )
        if recent:
            base_confidence += 5

        # Penalty: any declining source
        if any(s.classification == TrendClassification.DECLINING for s in source_trends):
            base_confidence -= 5

        return max(0, min(100, int(base_confidence)))


    def _source_confidence(
        self,
        classification: TrendClassification,
        data_point_count: int,
        trend_line: Optional[TrendLine],
        points: List[IncomeDataPoint],
    ) -> int:
        """Calculate confidence for a single source trend."""
        confidence = 50  # baseline

        # Data point count bonus
        if data_point_count >= 24:
            confidence += 25
        elif data_point_count >= 12:
            confidence += 20
        elif data_point_count >= 6:
            confidence += 10
        elif data_point_count >= 3:
            confidence += 5

        # Trend fit quality
        if trend_line and trend_line.r_squared >= 0.8:
            confidence += 15
        elif trend_line and trend_line.r_squared >= 0.5:
            confidence += 10
        elif trend_line and trend_line.r_squared >= 0.3:
            confidence += 5

        # Document type quality
        doc_types = {p.source_type for p in points}
        if "W2" in doc_types and "PAYSTUB" in doc_types:
            confidence += 10
        elif "TAX_RETURN" in doc_types:
            confidence += 8
        elif "W2" in doc_types:
            confidence += 5

        # Classification penalty
        if classification == TrendClassification.VOLATILE:
            confidence -= 10
        elif classification == TrendClassification.INSUFFICIENT_DATA:
            confidence -= 15

        return max(0, min(100, confidence))

    # =========================================================================
    # 17. PERSISTENCE
    # =========================================================================

