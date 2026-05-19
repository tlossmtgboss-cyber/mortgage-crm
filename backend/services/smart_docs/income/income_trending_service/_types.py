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

