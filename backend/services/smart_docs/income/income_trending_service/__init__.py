"""
Income Trending & Prediction Service for Smart Docs V2

Analyzes income trends from historical document data (paystubs, W2s, tax
returns, bank deposits) to predict future income stability and flag declining
income patterns per Fannie Mae Selling Guide B3-3.1-01.

Key capabilities:
    1. Multi-period trend analysis (YoY, QoQ, MoM, seasonal)
    2. Trend classification per underwriting guidelines
    3. Declining income handling per Fannie Mae / agency rules
    4. Linear-regression-based income prediction with confidence intervals
    5. Industry benchmarking against BLS occupation patterns
    6. Paystub-to-tax-return reconciliation
    7. Multi-income-source trending with weighted aggregation
    8. Visualization data points for charting
    9. Alert thresholds for qualification risk

Integrates with:
    - smart_documents / smart_document_extractions for extracted income data
    - income_calculations / income_sources for historical results
    - income_verification_tasks for LO follow-up items

Usage:
    from services.smart_docs.income.income_trending_service import (
        get_income_trending_service,
        IncomeTrendingService,
    )

    service = get_income_trending_service(db)
    analysis = await service.analyze_trend(
        org_id="org-123",
        borrower_id=42,
        income_data=income_data,
    )
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# Trend classification thresholds (per Fannie Mae guidelines)
STABLE_VARIANCE_PCT = Decimal("5")           # < 5% variation = stable
INCREASING_THRESHOLD_PCT = Decimal("5")      # > 5% increase = increasing
DECLINING_WARN_PCT = Decimal("10")           # > 10% decrease = declining
DECLINING_CRITICAL_PCT = Decimal("20")       # > 20% decrease = use most recent 12 months
VOLATILE_CV_THRESHOLD = Decimal("15")        # coefficient of variation > 15% = volatile

# Reconciliation thresholds
PAYSTUB_TAX_DISCREPANCY_PCT = Decimal("15")  # > 15% discrepancy flagged
PAYSTUB_TAX_CRITICAL_PCT = Decimal("25")     # > 25% critical flag

# Qualification alert defaults
DEFAULT_QUALIFYING_DTI = Decimal("50")       # max DTI for alert threshold
MINIMUM_INCOME_MONTHS_HISTORY = 6            # minimum months for meaningful trend

# Seasonal detection
SEASONAL_AMPLITUDE_THRESHOLD = Decimal("20")  # > 20% seasonal swing = seasonal

# Pay-frequency annualization multipliers (shared with income_calculator_service)
PAY_FREQUENCY_MULTIPLIERS: Dict[str, int] = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

# BLS occupation category codes for benchmarking
BLS_OCCUPATION_PATTERNS: Dict[str, Dict[str, float]] = {
    "management": {"avg_yoy_growth": 3.8, "volatility_pct": 6.2},
    "sales": {"avg_yoy_growth": 2.1, "volatility_pct": 18.5},
    "construction": {"avg_yoy_growth": 3.2, "volatility_pct": 22.0},
    "healthcare": {"avg_yoy_growth": 4.1, "volatility_pct": 4.8},
    "technology": {"avg_yoy_growth": 5.2, "volatility_pct": 9.3},
    "education": {"avg_yoy_growth": 2.5, "volatility_pct": 3.9},
    "finance": {"avg_yoy_growth": 3.6, "volatility_pct": 12.1},
    "manufacturing": {"avg_yoy_growth": 2.8, "volatility_pct": 10.5},
    "food_service": {"avg_yoy_growth": 1.9, "volatility_pct": 15.7},
    "transportation": {"avg_yoy_growth": 3.0, "volatility_pct": 11.8},
    "real_estate": {"avg_yoy_growth": 2.4, "volatility_pct": 25.3},
    "legal": {"avg_yoy_growth": 3.3, "volatility_pct": 7.6},
    "default": {"avg_yoy_growth": 3.0, "volatility_pct": 10.0},
}


# =============================================================================
# ENUMS
# =============================================================================

class TrendClassification(str, Enum):
    """Income trend classification per underwriting guidelines."""
    STABLE = "STABLE"
    INCREASING = "INCREASING"
    DECLINING = "DECLINING"
    VOLATILE = "VOLATILE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DeclineAction(str, Enum):
    """Required action for declining income per guidelines."""
    USE_LOWER_OF_AVERAGE_OR_RECENT = "USE_LOWER_OF_AVERAGE_OR_RECENT"  # 10-20% decline
    USE_MOST_RECENT_12_MONTHS = "USE_MOST_RECENT_12_MONTHS"            # 20%+ decline
    NO_ACTION = "NO_ACTION"


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class IncomeSourceType(str, Enum):
    W2_EMPLOYMENT = "W2_EMPLOYMENT"
    SELF_EMPLOYMENT = "SELF_EMPLOYMENT"
    COMMISSION = "COMMISSION"
    BONUS = "BONUS"
    OVERTIME = "OVERTIME"
    RENTAL = "RENTAL"
    RETIREMENT = "RETIREMENT"
    OTHER = "OTHER"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class IncomeDataPoint:
    """A single income observation."""
    period_start: date
    period_end: date
    amount: Decimal
    source_type: str             # W2, PAYSTUB, TAX_RETURN, BANK_DEPOSIT
    source_doc_id: Optional[int] = None
    employer_name: Optional[str] = None
    income_component: str = "total"  # base, overtime, commission, bonus, total
    annualized: bool = False     # whether this is already annualized
    confidence: int = 100


@dataclass
class TrendLine:
    """Linear regression result for a set of data points."""
    slope: float                 # monthly income change per month
    intercept: float             # income at t=0
    r_squared: float             # coefficient of determination
    std_error: float             # standard error of the estimate
    slope_pct_per_year: float    # slope as annual percentage change
    data_point_count: int


@dataclass
class SeasonalPattern:
    """Detected seasonal income pattern."""
    is_seasonal: bool
    peak_months: List[int]       # 1-12
    trough_months: List[int]     # 1-12
    amplitude_pct: Decimal       # peak-to-trough as percentage of mean
    pattern_description: str


@dataclass
class IncomeAlert:
    """Generated alert for income-related concerns."""
    severity: AlertSeverity
    alert_type: str
    title: str
    description: str
    source_type: Optional[str] = None
    recommended_action: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconciliationDiscrepancy:
    """A discrepancy found during paystub-to-tax reconciliation."""
    field: str
    paystub_value: Decimal
    tax_return_value: Decimal
    difference: Decimal
    difference_pct: Decimal
    severity: AlertSeverity
    explanation: str


@dataclass
class ReconciliationResult:
    """Result of paystub-to-tax-return reconciliation."""
    is_reconciled: bool
    overall_discrepancy_pct: Decimal
    discrepancies: List[ReconciliationDiscrepancy]
    paystub_annualized_income: Decimal
    tax_return_income: Decimal
    alerts: List[IncomeAlert]
    confidence: int
    notes: str = ""


@dataclass
class SourceTrend:
    """Trend analysis for a single income source."""
    source_type: str
    employer_name: Optional[str]
    classification: TrendClassification
    trend_line: Optional[TrendLine]
    seasonal_pattern: Optional[SeasonalPattern]
    year1_income: Optional[Decimal]       # most recent year
    year2_income: Optional[Decimal]       # prior year
    year3_income: Optional[Decimal]       # two years prior
    yoy_change_pct: Optional[Decimal]
    monthly_data_points: List[Dict[str, Any]]
    qualifying_income_monthly: Decimal
    decline_action: DeclineAction
    confidence: int
    flags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class IncomePrediction:
    """Projected income with confidence intervals."""
    projected_monthly_income: Decimal
    projected_annual_income: Decimal
    confidence_interval_low: Decimal
    confidence_interval_high: Decimal
    confidence_level: float              # e.g., 0.90 for 90% CI
    months_forward: int
    projection_date: date
    trend_basis: TrendClassification
    break_even_months: Optional[int]     # months until income < qualifying threshold
    r_squared: float
    notes: str = ""


@dataclass
class ChartDataSeries:
    """A single data series for visualization."""
    label: str
    data_points: List[Dict[str, Any]]    # [{x: "2024-01", y: 5000.00}, ...]
    line_type: str = "solid"             # solid, dashed, dotted
    color_hint: str = "primary"          # primary, secondary, warning, danger


@dataclass
class ChartData:
    """Complete visualization data for income trending."""
    series: List[ChartDataSeries]
    annotations: List[Dict[str, Any]]    # vertical lines, bands, etc.
    summary_stats: Dict[str, Any]
    date_range: Dict[str, str]           # {start: "2023-01", end: "2026-03"}


@dataclass
class TrendAnalysis:
    """Complete income trend analysis result."""
    org_id: str
    borrower_id: int
    loan_id: Optional[int]
    analysis_date: datetime
    overall_classification: TrendClassification
    overall_qualifying_monthly: Decimal
    overall_qualifying_annual: Decimal
    source_trends: List[SourceTrend]
    prediction: Optional[IncomePrediction]
    reconciliation: Optional[ReconciliationResult]
    industry_comparison: Optional[Dict[str, Any]]
    alerts: List[IncomeAlert]
    chart_data: Optional[ChartData]
    confidence: int
    calculation_method: str
    flags: List[str]
    tasks_to_create: List[Dict[str, Any]]
    duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# SERVICE
# =============================================================================


from ._data import _DataMixin
from ._analysis import _AnalysisMixin
from ._reports import _ReportsMixin

# =============================================================================
# SERVICE
# =============================================================================

class IncomeTrendingService(_DataMixin, _AnalysisMixin, _ReportsMixin):
    """
    Analyzes income trends to predict future income stability and flag
    declining patterns per Fannie Mae Selling Guide and agency requirements.

    All public methods enforce org_id tenant isolation.
    """

    def __init__(self, db: Session):
        self.db = db

    async def analyze_trend(
        self,
        org_id: str,
        borrower_id: int,
        income_data: Optional[List[IncomeDataPoint]] = None,
        loan_id: Optional[int] = None,
        months_forward: int = 12,
        qualifying_monthly_payment: Optional[Decimal] = None,
    ) -> TrendAnalysis:
        """
        Main entry point: analyze income trends for a borrower.

        If income_data is not provided, it will be loaded from the database
        (smart_documents, income_calculations, income_sources).

        Args:
            org_id: Organization ID for tenant isolation.
            borrower_id: Borrower to analyze.
            income_data: Optional pre-parsed income data points.
            loan_id: Optional loan to scope the analysis.
            months_forward: How many months to project forward.
            qualifying_monthly_payment: Monthly payment for break-even analysis.

        Returns:
            TrendAnalysis with classification, predictions, alerts, and chart data.
        """
        start_ms = int(time.time() * 1000)
        try:
            # Step 1: Load income data if not provided
            if income_data is None:
                income_data = await self._load_income_data(org_id, borrower_id, loan_id)

            if not income_data:
                return TrendAnalysis(
                    org_id=org_id,
                    borrower_id=borrower_id,
                    loan_id=loan_id,
                    analysis_date=datetime.now(timezone.utc),
                    overall_classification=TrendClassification.INSUFFICIENT_DATA,
                    overall_qualifying_monthly=ZERO,
                    overall_qualifying_annual=ZERO,
                    source_trends=[],
                    prediction=None,
                    reconciliation=None,
                    industry_comparison=None,
                    alerts=[IncomeAlert(
                        severity=AlertSeverity.HIGH,
                        alert_type="NO_INCOME_DATA",
                        title="No income data available",
                        description="No income documents or calculations found for this borrower.",
                        recommended_action="Upload income documentation (paystubs, W2s, tax returns).",
                    )],
                    chart_data=None,
                    confidence=0,
                    calculation_method="none",
                    flags=["NO_INCOME_DATA"],
                    tasks_to_create=[{
                        "task_type": "missing_documents",
                        "title": "Income documents needed for trend analysis",
                        "description": "No income data available. Upload paystubs, W2s, and tax returns.",
                        "priority": "high",
                    }],
                    duration_ms=int(time.time() * 1000) - start_ms,
                )

            # Step 2: Group data by income source
            source_groups = self._group_by_source(income_data)

            # Step 3: Analyze each source independently
            source_trends: List[SourceTrend] = []
            all_alerts: List[IncomeAlert] = []

            for source_key, points in source_groups.items():
                source_type, employer = source_key
                trend = self._analyze_source_trend(source_type, employer, points)
                source_trends.append(trend)

                # Generate source-level alerts
                source_alerts = self._generate_source_alerts(trend)
                all_alerts.extend(source_alerts)

            # Step 4: Classify overall trend
            overall_classification = self._classify_overall_trend(source_trends)

            # Step 5: Calculate qualifying income per guidelines
            qualifying_monthly = self._calculate_qualifying_income(
                source_trends, overall_classification
            )
            qualifying_annual = (qualifying_monthly * 12).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            # Step 6: Predict future income
            prediction = self._predict_income(
                income_data, months_forward, qualifying_monthly_payment
            )

            # Step 7: Reconcile paystub vs tax return if both exist
            reconciliation = self._reconcile_paystub_to_tax(income_data)
            if reconciliation:
                all_alerts.extend(reconciliation.alerts)

            # Step 8: Industry benchmarking
            industry_comparison = self._compare_to_industry(
                source_trends, income_data
            )

            # Step 9: Check primary source health
            primary_alerts = self._check_primary_source(source_trends)
            all_alerts.extend(primary_alerts)

            # Step 10: Qualification risk alerts
            if qualifying_monthly_payment:
                qual_alerts = self._check_qualification_risk(
                    qualifying_monthly, qualifying_monthly_payment, prediction
                )
                all_alerts.extend(qual_alerts)

            # Step 11: Build chart data
            chart_data = self._build_chart_data(
                source_trends, prediction, income_data
            )

            # Step 12: Generate flags and tasks
            flags = self._collect_flags(source_trends, all_alerts, reconciliation)
            tasks = self._generate_tasks(source_trends, all_alerts, flags)

            # Step 13: Calculate overall confidence
            confidence = self._calculate_confidence(source_trends, income_data)

            duration_ms = int(time.time() * 1000) - start_ms

            result = TrendAnalysis(
                org_id=org_id,
                borrower_id=borrower_id,
                loan_id=loan_id,
                analysis_date=datetime.now(timezone.utc),
                overall_classification=overall_classification,
                overall_qualifying_monthly=qualifying_monthly,
                overall_qualifying_annual=qualifying_annual,
                source_trends=source_trends,
                prediction=prediction,
                reconciliation=reconciliation,
                industry_comparison=industry_comparison,
                alerts=all_alerts,
                chart_data=chart_data,
                confidence=confidence,
                calculation_method=self._determine_method(source_trends),
                flags=flags,
                tasks_to_create=tasks,
                duration_ms=duration_ms,
            )

            # Step 14: Persist analysis
            await self._save_analysis(result)

            return result

        except Exception as e:
            logger.exception(
                f"Income trend analysis failed for org={org_id} borrower={borrower_id}: {e}"
            )
            return TrendAnalysis(
                org_id=org_id,
                borrower_id=borrower_id,
                loan_id=loan_id,
                analysis_date=datetime.now(timezone.utc),
                overall_classification=TrendClassification.INSUFFICIENT_DATA,
                overall_qualifying_monthly=ZERO,
                overall_qualifying_annual=ZERO,
                source_trends=[],
                prediction=None,
                reconciliation=None,
                industry_comparison=None,
                alerts=[],
                chart_data=None,
                confidence=0,
                calculation_method="error",
                flags=["ANALYSIS_ERROR"],
                tasks_to_create=[],
                duration_ms=int(time.time() * 1000) - start_ms,
                success=False,
                error=str(e),
            )

    async def predict_income(
        self,
        income_history: List[IncomeDataPoint],
        months_forward: int = 12,
        qualifying_monthly_payment: Optional[Decimal] = None,
    ) -> IncomePrediction:
        """
        Predict future income from historical data points.

        Uses linear regression on monthly income amounts with confidence
        intervals based on standard error of the estimate.

        Args:
            income_history: Historical income data points.
            months_forward: Number of months to project.
            qualifying_monthly_payment: For break-even analysis.

        Returns:
            IncomePrediction with projected amounts and confidence bands.
        """
        return self._predict_income(
            income_history, months_forward, qualifying_monthly_payment
        )

    async def reconcile_paystub_to_tax(
        self,
        paystub_data: List[IncomeDataPoint],
        tax_data: List[IncomeDataPoint],
    ) -> ReconciliationResult:
        """
        Compare YTD paystub income to prior year tax return income.

        Flags significant discrepancies that may indicate unreported income,
        over-reported income, or data entry errors.

        Args:
            paystub_data: Income data points from paystubs.
            tax_data: Income data points from tax returns.

        Returns:
            ReconciliationResult with discrepancies and alerts.
        """
        combined = paystub_data + tax_data
        result = self._reconcile_paystub_to_tax(combined)
        if result is None:
            return ReconciliationResult(
                is_reconciled=True,
                overall_discrepancy_pct=ZERO,
                discrepancies=[],
                paystub_annualized_income=ZERO,
                tax_return_income=ZERO,
                alerts=[],
                confidence=0,
                notes="Insufficient data for reconciliation.",
            )
        return result

    async def classify_trend(
        self,
        income_points: List[IncomeDataPoint],
    ) -> TrendClassification:
        """
        Classify an income trend from raw data points.

        Args:
            income_points: Income observations over time.

        Returns:
            TrendClassification enum value.
        """
        if len(income_points) < 2:
            return TrendClassification.INSUFFICIENT_DATA

        monthly = self._to_monthly_series(income_points)
        if len(monthly) < 2:
            return TrendClassification.INSUFFICIENT_DATA

        amounts = [float(m["amount"]) for m in monthly]
        return self._classify_from_amounts(amounts)

    async def get_visualization_data(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> ChartData:
        """
        Get visualization-ready data for income trending charts.

        Args:
            org_id: Organization ID for tenant isolation.
            borrower_id: Borrower to get chart data for.
            loan_id: Optional loan scope.

        Returns:
            ChartData with series, annotations, and summary stats.
        """
        income_data = await self._load_income_data(org_id, borrower_id, loan_id)
        if not income_data:
            return ChartData(
                series=[],
                annotations=[],
                summary_stats={"data_points": 0},
                date_range={"start": "", "end": ""},
            )

        source_groups = self._group_by_source(income_data)
        source_trends = []
        for (source_type, employer), points in source_groups.items():
            trend = self._analyze_source_trend(source_type, employer, points)
            source_trends.append(trend)

        prediction = self._predict_income(income_data, 12, None)
        return self._build_chart_data(source_trends, prediction, income_data)

    def _group_by_source(
        self,
        data_points: List[IncomeDataPoint],
    ) -> Dict[Tuple[str, Optional[str]], List[IncomeDataPoint]]:
        """Group income data points by (source_type, employer_name)."""
        groups: Dict[Tuple[str, Optional[str]], List[IncomeDataPoint]] = {}
        for dp in data_points:
            # Normalize source type for grouping
            source = dp.source_type
            if source in ("PAYSTUB", "W2"):
                source = "W2_EMPLOYMENT"
            elif source == "TAX_RETURN" and dp.income_component == "self_employment":
                source = "SELF_EMPLOYMENT"
            elif source == "TAX_RETURN" and dp.income_component == "rental":
                source = "RENTAL"

            key = (source, dp.employer_name)
            if key not in groups:
                groups[key] = []
            groups[key].append(dp)
        return groups


    def _to_monthly_series(
        self,
        points: List[IncomeDataPoint],
    ) -> List[Dict[str, Any]]:
        """
        Convert irregular data points to a monthly series.

        For annualized data points, divide by 12 to get monthly.
        For pay-period data, accumulate per month.
        """
        monthly_buckets: Dict[str, List[float]] = {}

        for dp in points:
            if dp.income_component != "total":
                continue

            month_key = dp.period_end.strftime("%Y-%m")

            if dp.annualized:
                monthly_amount = float(dp.amount / 12)
            else:
                monthly_amount = float(dp.amount)

            if month_key not in monthly_buckets:
                monthly_buckets[month_key] = []
            monthly_buckets[month_key].append(monthly_amount)

        # Average multiple observations in the same month
        result = []
        for month, amounts in sorted(monthly_buckets.items()):
            avg = statistics.mean(amounts)
            result.append({"month": month, "amount": round(avg, 2)})

        return result


    def _to_annual_amounts(
        self,
        points: List[IncomeDataPoint],
    ) -> Dict[str, Optional[Decimal]]:
        """
        Extract annual income amounts for the most recent 3 years.

        Returns dict with keys: year1 (most recent), year2, year3.
        """
        annual_data: Dict[int, List[Decimal]] = {}

        for dp in points:
            if dp.income_component != "total":
                continue

            year = dp.period_end.year

            if dp.annualized:
                amount = dp.amount
            else:
                # Skip non-annualized for annual comparison
                continue

            if year not in annual_data:
                annual_data[year] = []
            annual_data[year].append(amount)

        if not annual_data:
            return {"year1": None, "year2": None, "year3": None}

        # Average multiple observations per year, sort descending
        year_avgs: Dict[int, Decimal] = {}
        for year, amounts in annual_data.items():
            avg = sum(amounts) / len(amounts)
            year_avgs[year] = avg.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        sorted_years = sorted(year_avgs.keys(), reverse=True)

        return {
            "year1": year_avgs.get(sorted_years[0]) if len(sorted_years) > 0 else None,
            "year2": year_avgs.get(sorted_years[1]) if len(sorted_years) > 1 else None,
            "year3": year_avgs.get(sorted_years[2]) if len(sorted_years) > 2 else None,
        }


    def _deduplicate_points(
        self,
        points: List[IncomeDataPoint],
    ) -> List[IncomeDataPoint]:
        """
        Remove duplicate income data points, preferring higher-confidence
        observations for the same period and source.
        """
        # Key: (source_type, employer, period_end_year_month, component)
        best: Dict[Tuple, IncomeDataPoint] = {}

        for dp in points:
            key = (
                dp.source_type,
                dp.employer_name,
                dp.period_end.strftime("%Y-%m"),
                dp.income_component,
            )
            if key not in best or dp.confidence > best[key].confidence:
                best[key] = dp

        return list(best.values())


    def _determine_method(self, source_trends: List[SourceTrend]) -> str:
        """Determine the calculation method label."""
        if not source_trends:
            return "none"

        methods = set()
        for st in source_trends:
            if st.decline_action == DeclineAction.USE_MOST_RECENT_12_MONTHS:
                methods.add("recent_12_month")
            elif st.decline_action == DeclineAction.USE_LOWER_OF_AVERAGE_OR_RECENT:
                methods.add("lower_of_avg_or_recent")
            elif st.year2_income is not None:
                methods.add("2_year_average")
            else:
                methods.add("current")

        if len(methods) == 1:
            return methods.pop()
        return "composite"


    def _parse_json_field(self, value: Any) -> Dict[str, Any]:
        """Safely parse a JSON field from the database."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}


    def _to_decimal(self, value: Any) -> Decimal:
        """Safely convert a value to Decimal, returning ZERO on failure."""
        if value is None:
            return ZERO
        try:
            if isinstance(value, Decimal):
                return value
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return ZERO
            return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return ZERO


    def _parse_date(self, date_str: str) -> date:
        """Parse a date string in common formats."""
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
        raise ValueError(f"Unable to parse date: {date_str}")


    def _months_elapsed_in_year(self, pay_date: date) -> int:
        """Calculate months elapsed from Jan 1 to the pay date (minimum 1)."""
        days = (pay_date - date(pay_date.year, 1, 1)).days + 1
        months = max(1, round(days / 30.44))
        return months

    @staticmethod

    @staticmethod
    def _t_value_approx(confidence: float, df: int) -> float:
        """
        Approximate t-value for a given confidence level and degrees of freedom.

        Uses a lookup table for common values with linear interpolation.
        For production, consider scipy.stats.t.ppf.
        """
        # Two-tailed alpha
        alpha = 1 - confidence

        # Common t-values for alpha/2 (two-tailed)
        # df -> t-value for 90% CI (alpha=0.10, alpha/2=0.05)
        t_table_90: Dict[int, float] = {
            1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015,
            6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812,
            15: 1.753, 20: 1.725, 25: 1.708, 30: 1.697,
            40: 1.684, 60: 1.671, 120: 1.658,
        }

        if abs(alpha - 0.10) < 0.01:
            table = t_table_90
        else:
            # Fallback: use z-value approximation for large df
            if alpha == 0.05:
                return 1.960
            return 1.645  # 90% CI default

        # Find closest df
        if df in table:
            return table[df]

        # Interpolate between closest values
        dfs = sorted(table.keys())
        if df < dfs[0]:
            return table[dfs[0]]
        if df > dfs[-1]:
            return table[dfs[-1]]

        for i in range(len(dfs) - 1):
            if dfs[i] <= df <= dfs[i + 1]:
                # Linear interpolation
                t_low = table[dfs[i]]
                t_high = table[dfs[i + 1]]
                frac = (df - dfs[i]) / (dfs[i + 1] - dfs[i])
                return t_low + frac * (t_high - t_low)

        return 1.645  # fallback



# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================

def _fmt_currency(amount: Decimal) -> str:
    """Format a Decimal as currency string."""
    return f"${float(amount):,.2f}"


def _add_months(d: date, months: int) -> date:
    """Add months to a date, handling month-end overflow."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(d.day, max_day)
    return date(year, month, day)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_income_trending_service(db: Session) -> IncomeTrendingService:
    """
    Factory function returning an IncomeTrendingService for the given session.

    Not a true singleton because each request may have a different DB session,
    but the service itself is lightweight and stateless beyond the session.
    """
    return IncomeTrendingService(db)
