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

class IncomeTrendingService:
    """
    Analyzes income trends to predict future income stability and flag
    declining patterns per Fannie Mae Selling Guide and agency requirements.

    All public methods enforce org_id tenant isolation.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

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

    # =========================================================================
    # 2. STANDALONE PUBLIC METHODS
    # =========================================================================

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

    # =========================================================================
    # 3. DATA LOADING
    # =========================================================================

    async def _load_income_data(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """
        Load income data from multiple DB sources:
        1. smart_documents / smart_document_extractions (paystubs, W2s, tax returns)
        2. income_sources from prior income_calculations
        3. Bank deposit patterns (from bank_statement_extractions if available)

        Enforces org_id tenant isolation on all queries.
        """
        data_points: List[IncomeDataPoint] = []

        # --- Source 1: Extracted document data ---
        doc_points = await self._load_from_documents(org_id, borrower_id, loan_id)
        data_points.extend(doc_points)

        # --- Source 2: Prior income calculations ---
        calc_points = await self._load_from_calculations(org_id, borrower_id, loan_id)
        data_points.extend(calc_points)

        # Deduplicate: prefer higher-confidence points for the same period/source
        data_points = self._deduplicate_points(data_points)

        return data_points

    async def _load_from_documents(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """Load income data points from smart_documents + extractions."""
        points: List[IncomeDataPoint] = []

        loan_filter = "AND sd.loan_id = :loan_id" if loan_id else ""
        params: Dict[str, Any] = {
            "org_id": org_id,
            "borrower_id": borrower_id,
        }
        if loan_id:
            params["loan_id"] = loan_id

        trend_query = (
            "SELECT"
            " sd.id AS doc_id,"
            " sd.doc_type,"
            " sd.uploaded_at,"
            " sde.extracted_fields,"
            " sde.overall_confidence"
            " FROM smart_documents sd"
            " LEFT JOIN smart_document_extractions sde"
            "     ON sde.document_id = sd.id"
            " WHERE sd.organization_id = :org_id"
            "   AND sd.borrower_id = :borrower_id"
            "   AND sd.doc_type IN ('PAYSTUB', 'W2', 'TAX_RETURN')"
            "   AND sd.status NOT IN ('REJECTED', 'EXPIRED')"
            "   " + loan_filter
            + " ORDER BY sd.uploaded_at ASC"
        )
        rows = self.db.execute(text(trend_query), params).fetchall()

        for row in rows:
            extracted = self._parse_json_field(row.extracted_fields)
            if not extracted:
                continue

            confidence = int(row.overall_confidence or 70)
            doc_type = str(row.doc_type) if row.doc_type else "UNKNOWN"

            try:
                if doc_type == "PAYSTUB":
                    pts = self._parse_paystub_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
                elif doc_type == "W2":
                    pts = self._parse_w2_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
                elif doc_type == "TAX_RETURN":
                    pts = self._parse_tax_return_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
            except Exception as e:
                logger.warning(
                    f"Failed to parse income data from doc {row.doc_id} "
                    f"(type={doc_type}): {e}"
                )

        return points

    async def _load_from_calculations(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """Load income data from prior income_sources records."""
        points: List[IncomeDataPoint] = []

        loan_filter = "AND ic.loan_id = :loan_id" if loan_id else ""
        params: Dict[str, Any] = {"borrower_id": borrower_id}
        if loan_id:
            params["loan_id"] = loan_id

        # income_sources joined through income_calculations for tenant isolation
        # income_calculations links to loan which has organization_id
        isrc_query = (
            "SELECT"
            " isrc.source_type,"
            " isrc.employer_name,"
            " isrc.total_monthly_income,"
            " isrc.total_annual_income,"
            " isrc.year1_income,"
            " isrc.year2_income,"
            " isrc.year_over_year_change_pct,"
            " isrc.trending_direction,"
            " isrc.ai_confidence,"
            " isrc.created_at,"
            " ic.loan_id"
            " FROM income_sources isrc"
            " JOIN income_calculations ic ON ic.id = isrc.calculation_id"
            " JOIN loans l ON l.id = ic.loan_id"
            " WHERE isrc.borrower_id = :borrower_id"
            "   AND l.organization_id = :org_id"
            "   AND ic.status NOT IN ('rejected', 'error')"
            "   " + loan_filter
            + " ORDER BY isrc.created_at ASC"
        )
        rows = self.db.execute(
            text(isrc_query),
            {**params, "org_id": org_id},
        ).fetchall()

        for row in rows:
            created = row.created_at
            if isinstance(created, datetime):
                period_date = created.date()
            elif isinstance(created, date):
                period_date = created
            else:
                continue

            # Year 1 (most recent)
            if row.year1_income is not None:
                year1_end = date(period_date.year - 1, 12, 31)
                year1_start = date(period_date.year - 1, 1, 1)
                points.append(IncomeDataPoint(
                    period_start=year1_start,
                    period_end=year1_end,
                    amount=self._to_decimal(row.year1_income),
                    source_type=row.source_type or "W2",
                    employer_name=row.employer_name,
                    income_component="total",
                    annualized=True,
                    confidence=int(row.ai_confidence or 70),
                ))

            # Year 2 (prior year)
            if row.year2_income is not None:
                year2_end = date(period_date.year - 2, 12, 31)
                year2_start = date(period_date.year - 2, 1, 1)
                points.append(IncomeDataPoint(
                    period_start=year2_start,
                    period_end=year2_end,
                    amount=self._to_decimal(row.year2_income),
                    source_type=row.source_type or "W2",
                    employer_name=row.employer_name,
                    income_component="total",
                    annualized=True,
                    confidence=int(row.ai_confidence or 70),
                ))

        return points

    # =========================================================================
    # 4. DOCUMENT PARSERS
    # =========================================================================

    def _parse_paystub_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from paystub extracted fields."""
        points: List[IncomeDataPoint] = []

        pay_date_str = extracted.get("pay_date") or extracted.get("pay_period_end")
        if not pay_date_str:
            return points

        try:
            pay_date = self._parse_date(pay_date_str)
        except ValueError:
            return points

        employer = extracted.get("employer_name")
        period_start_str = extracted.get("pay_period_start")
        period_start = self._parse_date(period_start_str) if period_start_str else pay_date

        # YTD gross is most useful for trending
        ytd_gross = self._to_decimal(extracted.get("ytd_gross") or extracted.get("ytd_gross_pay"))
        current_gross = self._to_decimal(extracted.get("gross_pay") or extracted.get("current_gross"))

        if ytd_gross > ZERO:
            # YTD data point: annualize based on pay date position in year
            months_elapsed = self._months_elapsed_in_year(pay_date)
            if months_elapsed and months_elapsed > 0:
                annualized = (ytd_gross / months_elapsed * 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                points.append(IncomeDataPoint(
                    period_start=date(pay_date.year, 1, 1),
                    period_end=pay_date,
                    amount=annualized,
                    source_type="PAYSTUB",
                    source_doc_id=doc_id,
                    employer_name=employer,
                    income_component="total",
                    annualized=True,
                    confidence=confidence,
                ))

        if current_gross > ZERO:
            # Individual pay period data point (not annualized)
            points.append(IncomeDataPoint(
                period_start=period_start,
                period_end=pay_date,
                amount=current_gross,
                source_type="PAYSTUB",
                source_doc_id=doc_id,
                employer_name=employer,
                income_component="total",
                annualized=False,
                confidence=confidence,
            ))

        # Component-level data if available
        for component, field_names in [
            ("base", ["base_pay", "regular_pay", "salary"]),
            ("overtime", ["overtime_pay", "ot_pay"]),
            ("commission", ["commission", "commission_pay"]),
            ("bonus", ["bonus", "bonus_pay"]),
        ]:
            for field_name in field_names:
                val = self._to_decimal(extracted.get(f"ytd_{field_name}") or extracted.get(field_name))
                if val > ZERO:
                    points.append(IncomeDataPoint(
                        period_start=period_start,
                        period_end=pay_date,
                        amount=val,
                        source_type="PAYSTUB",
                        source_doc_id=doc_id,
                        employer_name=employer,
                        income_component=component,
                        annualized=False,
                        confidence=confidence - 5,  # component-level slightly lower confidence
                    ))
                    break  # take first match per component

        return points

    def _parse_w2_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from W2 extracted fields."""
        points: List[IncomeDataPoint] = []

        tax_year = extracted.get("tax_year")
        if not tax_year:
            return points

        try:
            year = int(tax_year)
        except (ValueError, TypeError):
            return points

        employer = extracted.get("employer_name")
        wages = self._to_decimal(
            extracted.get("wages_tips_compensation")
            or extracted.get("box_1")
            or extracted.get("total_wages")
        )

        if wages > ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=wages,
                source_type="W2",
                source_doc_id=doc_id,
                employer_name=employer,
                income_component="total",
                annualized=True,
                confidence=confidence,
            ))

        return points

    def _parse_tax_return_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from tax return extracted fields."""
        points: List[IncomeDataPoint] = []

        tax_year = extracted.get("tax_year")
        if not tax_year:
            return points

        try:
            year = int(tax_year)
        except (ValueError, TypeError):
            return points

        # Total income from 1040
        total_income = self._to_decimal(
            extracted.get("total_income")
            or extracted.get("line_9")  # 1040 total income line
            or extracted.get("adjusted_gross_income")
        )
        if total_income > ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=total_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="total",
                annualized=True,
                confidence=confidence,
            ))

        # Wages from W2 reported on 1040
        wages = self._to_decimal(
            extracted.get("wages_salaries_tips")
            or extracted.get("line_1")
        )
        if wages > ZERO and wages != total_income:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=wages,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="base",
                annualized=True,
                confidence=confidence,
            ))

        # Self-employment income (Schedule C)
        se_income = self._to_decimal(
            extracted.get("schedule_c_net_profit")
            or extracted.get("self_employment_income")
        )
        if se_income != ZERO:  # can be negative
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=se_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="self_employment",
                annualized=True,
                confidence=confidence - 5,
            ))

        # Rental income (Schedule E)
        rental_income = self._to_decimal(
            extracted.get("schedule_e_net")
            or extracted.get("rental_income")
        )
        if rental_income != ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=rental_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="rental",
                annualized=True,
                confidence=confidence - 5,
            ))

        return points

    # =========================================================================
    # 5. TREND ANALYSIS (PER SOURCE)
    # =========================================================================

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

    async def _save_analysis(self, result: TrendAnalysis) -> None:
        """
        Persist trend analysis results to income_trend_analyses table.

        Creates the table if it does not exist (first-run safety).
        """
        try:
            # Ensure table exists
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS income_trend_analyses (
                    id SERIAL PRIMARY KEY,
                    organization_id VARCHAR(255) NOT NULL,
                    borrower_id INTEGER NOT NULL,
                    loan_id INTEGER,
                    analysis_date TIMESTAMP WITH TIME ZONE NOT NULL,
                    overall_classification VARCHAR(50) NOT NULL,
                    qualifying_monthly_income NUMERIC(18,2),
                    qualifying_annual_income NUMERIC(18,2),
                    source_count INTEGER DEFAULT 0,
                    prediction_json JSONB,
                    reconciliation_json JSONB,
                    industry_comparison_json JSONB,
                    alerts_json JSONB,
                    chart_data_json JSONB,
                    confidence INTEGER DEFAULT 0,
                    calculation_method VARCHAR(50),
                    flags JSONB,
                    tasks_json JSONB,
                    duration_ms INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Serialize complex objects
            prediction_json = None
            if result.prediction:
                prediction_json = json.dumps({
                    "projected_monthly": float(result.prediction.projected_monthly_income),
                    "projected_annual": float(result.prediction.projected_annual_income),
                    "ci_low": float(result.prediction.confidence_interval_low),
                    "ci_high": float(result.prediction.confidence_interval_high),
                    "confidence_level": result.prediction.confidence_level,
                    "months_forward": result.prediction.months_forward,
                    "projection_date": result.prediction.projection_date.isoformat(),
                    "trend_basis": result.prediction.trend_basis.value,
                    "break_even_months": result.prediction.break_even_months,
                    "r_squared": result.prediction.r_squared,
                    "notes": result.prediction.notes,
                })

            reconciliation_json = None
            if result.reconciliation:
                reconciliation_json = json.dumps({
                    "is_reconciled": result.reconciliation.is_reconciled,
                    "discrepancy_pct": float(result.reconciliation.overall_discrepancy_pct),
                    "paystub_annual": float(result.reconciliation.paystub_annualized_income),
                    "tax_annual": float(result.reconciliation.tax_return_income),
                    "confidence": result.reconciliation.confidence,
                    "notes": result.reconciliation.notes,
                    "discrepancy_count": len(result.reconciliation.discrepancies),
                })

            alerts_json = json.dumps([
                {
                    "severity": a.severity.value,
                    "type": a.alert_type,
                    "title": a.title,
                    "description": a.description,
                    "source_type": a.source_type,
                    "recommended_action": a.recommended_action,
                }
                for a in result.alerts
            ])

            industry_json = json.dumps(result.industry_comparison) if result.industry_comparison else None

            # Serialize chart data
            chart_json = None
            if result.chart_data:
                chart_json = json.dumps({
                    "series": [
                        {
                            "label": s.label,
                            "data_points": s.data_points,
                            "line_type": s.line_type,
                            "color_hint": s.color_hint,
                        }
                        for s in result.chart_data.series
                    ],
                    "annotations": result.chart_data.annotations,
                    "summary_stats": result.chart_data.summary_stats,
                    "date_range": result.chart_data.date_range,
                })

            self.db.execute(
                text("""
                    INSERT INTO income_trend_analyses (
                        organization_id, borrower_id, loan_id,
                        analysis_date, overall_classification,
                        qualifying_monthly_income, qualifying_annual_income,
                        source_count,
                        prediction_json, reconciliation_json,
                        industry_comparison_json,
                        alerts_json, chart_data_json,
                        confidence, calculation_method,
                        flags, tasks_json,
                        duration_ms, created_at, updated_at
                    ) VALUES (
                        :org_id, :borrower_id, :loan_id,
                        :analysis_date, :classification,
                        :monthly, :annual,
                        :source_count,
                        :prediction, :reconciliation,
                        :industry,
                        :alerts, :chart_data,
                        :confidence, :method,
                        :flags, :tasks,
                        :duration, :now, :now
                    )
                """),
                {
                    "org_id": result.org_id,
                    "borrower_id": result.borrower_id,
                    "loan_id": result.loan_id,
                    "analysis_date": result.analysis_date,
                    "classification": result.overall_classification.value,
                    "monthly": float(result.overall_qualifying_monthly),
                    "annual": float(result.overall_qualifying_annual),
                    "source_count": len(result.source_trends),
                    "prediction": prediction_json,
                    "reconciliation": reconciliation_json,
                    "industry": industry_json,
                    "alerts": alerts_json,
                    "chart_data": chart_json,
                    "confidence": result.confidence,
                    "method": result.calculation_method,
                    "flags": json.dumps(result.flags),
                    "tasks": json.dumps(result.tasks_to_create),
                    "duration": result.duration_ms,
                    "now": datetime.now(timezone.utc),
                },
            )
            self.db.commit()
            logger.info(
                f"Income trend analysis saved: org={result.org_id} "
                f"borrower={result.borrower_id} "
                f"classification={result.overall_classification.value}"
            )

        except Exception as e:
            logger.exception(f"Failed to save income trend analysis: {e}")
            self.db.rollback()

    # =========================================================================
    # 18. UTILITY METHODS
    # =========================================================================

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
