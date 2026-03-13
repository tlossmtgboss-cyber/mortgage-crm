"""
Non-Traditional Income Handling Service for Smart Docs V2

Handles income types that fall outside standard W-2 and self-employment
categories. These income streams are increasingly common due to the gig
economy, international workforce, and alternative investment structures,
but they require specialized documentation and calculation methods per
agency guidelines (Fannie Mae Selling Guide B3-3.1, FHA 4000.1, VA 26-7).

Supported income categories:
    1.  Gig economy / 1099 platform income
    2.  Seasonal employment
    3.  Foreign income (with currency conversion)
    4.  Trust distributions
    5.  Notes receivable
    6.  Royalty income
    7.  Capital gains (limited applicability)
    8.  Boarder income
    9.  Foster care income
    10. Non-borrower household income (compensating factor only)
    11. Cryptocurrency income (generally not qualifying)

Integrates with:
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items
    - smart_documents / smart_document_extractions for document data
    - IncomeCalculatorService for DTI recalculation

Usage:
    from services.smart_docs.income.non_traditional_income_service import (
        NonTraditionalIncomeService,
        get_non_traditional_income_service,
    )

    service = get_non_traditional_income_service(db, org_id=42)
    classification = await service.classify_income_type(income_data)
    gig_result = await service.calculate_gig_income(
        org_id=42, borrower_id=7, platforms=["uber", "doordash"], tax_data=tax_data,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
MONTHS_PER_YEAR = 12

# Minimum history (in years) required by most agencies
MIN_HISTORY_YEARS_GIG = 2
MIN_HISTORY_YEARS_SEASONAL = 2
MIN_HISTORY_YEARS_ROYALTY = 2
MIN_HISTORY_YEARS_TRUST = 3
MIN_HISTORY_YEARS_NOTES_RECEIVABLE = 3
MIN_HISTORY_YEARS_BOARDER = 1
MIN_HISTORY_YEARS_FOSTER = 1
MIN_HISTORY_YEARS_CAPITAL_GAINS_DAY_TRADER = 2

# Boarder income: max percentage of housing payment that can be offset
BOARDER_INCOME_MAX_OFFSET_PCT = Decimal("0.30")

# Foster care gross-up factor for tax-exempt income (standard 25% gross-up)
FOSTER_CARE_GROSSUP_FACTOR = Decimal("1.25")

# Declining income threshold percentages
DECLINING_WARN_PCT = Decimal("10")
DECLINING_CRITICAL_PCT = Decimal("25")

# Confidence thresholds
CONFIDENCE_HIGH = 80
CONFIDENCE_MEDIUM = 60
CONFIDENCE_LOW = 40

# Known gig platforms grouped by category
GIG_PLATFORMS: Dict[str, List[str]] = {
    "rideshare": ["uber", "lyft", "via", "juno"],
    "delivery": ["doordash", "grubhub", "uber_eats", "instacart", "postmates", "amazon_flex"],
    "freelance": ["upwork", "fiverr", "toptal", "freelancer", "99designs"],
    "marketplace": ["etsy", "amazon_fba", "ebay", "poshmark", "mercari"],
    "rental": ["airbnb", "vrbo", "turo"],
    "task": ["taskrabbit", "thumbtack", "handy"],
}

# IRS form types relevant to non-traditional income
RELEVANT_TAX_FORMS: Dict[str, List[str]] = {
    "gig": ["1099-K", "1099-NEC", "1099-MISC", "Schedule C", "Schedule SE"],
    "seasonal": ["W-2", "1099-G"],  # 1099-G for unemployment
    "foreign": ["Form 2555", "Form 1116", "W-2"],
    "trust": ["K-1", "1041 Schedule K-1"],
    "notes_receivable": ["1099-INT", "Schedule B"],
    "royalty": ["1099-MISC", "Schedule E Part I"],
    "capital_gains": ["Schedule D", "Form 8949", "1099-B"],
    "boarder": ["Schedule E", "Form 1040"],
    "foster_care": ["State payment records"],
}

# Currency codes supported for foreign income conversion
MAJOR_CURRENCIES = {
    "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "CNY", "INR",
    "MXN", "BRL", "KRW", "SGD", "HKD", "NZD", "SEK", "NOK", "DKK",
    "ZAR", "AED", "PHP", "THB", "TWD", "PLN", "CZK", "ILS", "TRY",
}


# =============================================================================
# Enums
# =============================================================================

class NonTraditionalIncomeType(str, Enum):
    """Classification of non-traditional income sources."""
    GIG_RIDESHARE = "gig_rideshare"
    GIG_DELIVERY = "gig_delivery"
    GIG_FREELANCE = "gig_freelance"
    GIG_MARKETPLACE = "gig_marketplace"
    GIG_RENTAL_PLATFORM = "gig_rental_platform"
    GIG_TASK = "gig_task"
    GIG_OTHER = "gig_other"
    SEASONAL = "seasonal"
    FOREIGN = "foreign"
    TRUST = "trust"
    NOTES_RECEIVABLE = "notes_receivable"
    ROYALTY = "royalty"
    CAPITAL_GAINS = "capital_gains"
    BOARDER = "boarder"
    FOSTER_CARE = "foster_care"
    NON_BORROWER_HOUSEHOLD = "non_borrower_household"
    CRYPTOCURRENCY = "cryptocurrency"
    UNCLASSIFIED = "unclassified"


class ContinuanceRisk(str, Enum):
    """Risk level that income will not continue."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNACCEPTABLE = "unacceptable"


class QualifyingStatus(str, Enum):
    """Whether income can be used for qualifying."""
    QUALIFYING = "qualifying"
    QUALIFYING_WITH_CONDITIONS = "qualifying_with_conditions"
    COMPENSATING_FACTOR_ONLY = "compensating_factor_only"
    NOT_QUALIFYING = "not_qualifying"
    NEEDS_REVIEW = "needs_review"


class DocumentationCompleteness(str, Enum):
    """How complete the documentation is for this income type."""
    COMPLETE = "complete"
    PARTIALLY_COMPLETE = "partially_complete"
    INSUFFICIENT = "insufficient"
    NOT_PROVIDED = "not_provided"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DocRequirement:
    """A single documentation requirement for an income type."""
    document_type: str
    description: str
    required: bool  # True = must have; False = recommended/conditional
    years_required: int  # How many years of this doc are needed
    notes: str = ""
    alternative_docs: List[str] = field(default_factory=list)


@dataclass
class IncomeClassification:
    """Result of classifying an income source."""
    income_type: NonTraditionalIncomeType
    qualifying_status: QualifyingStatus
    platform_category: Optional[str]  # e.g., "rideshare", "delivery"
    platform_name: Optional[str]
    confidence: int  # 0-100
    reasoning: str
    documentation_requirements: List[DocRequirement]
    flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TrendAnalysis:
    """Year-over-year trending for an income source."""
    year1_amount: Decimal  # Most recent
    year2_amount: Decimal  # Prior year
    year3_amount: Optional[Decimal] = None  # Two years prior (if available)
    yoy_change_pct: Optional[Decimal] = None
    two_year_avg: Optional[Decimal] = None
    three_year_avg: Optional[Decimal] = None
    direction: str = "stable"  # increasing, stable, declining, variable
    use_lower_year: bool = False  # True when declining income detected


@dataclass
class ExpenseAnalysis:
    """Business expense breakdown for gig/platform income."""
    gross_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal
    expense_ratio_pct: Decimal
    major_categories: Dict[str, Decimal] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)


@dataclass
class GigIncomeResult:
    """Result of gig economy income calculation."""
    borrower_id: int
    platforms: List[str]
    qualifying_status: QualifyingStatus
    gross_annual_income: Decimal
    total_expenses: Decimal
    net_annual_income: Decimal
    qualifying_monthly_income: Decimal
    trend: TrendAnalysis
    expense_analysis: ExpenseAnalysis
    documentation_completeness: DocumentationCompleteness
    history_years: int
    confidence: int
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SeasonalResult:
    """Result of seasonal income calculation."""
    borrower_id: int
    industry: Optional[str]
    qualifying_status: QualifyingStatus
    year1_earnings: Decimal
    year2_earnings: Decimal
    two_year_average_annual: Decimal
    qualifying_monthly_income: Decimal
    off_season_unemployment: Decimal
    unemployment_included: bool
    months_active_per_year: int
    trend: TrendAnalysis
    documentation_completeness: DocumentationCompleteness
    confidence: int
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ForeignIncomeResult:
    """Result of foreign income analysis."""
    borrower_id: int
    qualifying_status: QualifyingStatus
    original_currency: str
    original_annual_amount: Decimal
    exchange_rate: Decimal
    usd_annual_amount: Decimal
    qualifying_monthly_income: Decimal
    feie_exclusion_amount: Decimal  # Foreign Earned Income Exclusion
    net_taxable_usd: Decimal
    has_employment_contract: bool
    contract_remaining_months: Optional[int]
    tax_treaty_applicable: bool
    documentation_completeness: DocumentationCompleteness
    confidence: int
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of validating a non-traditional income source."""
    income_type: NonTraditionalIncomeType
    is_valid: bool
    qualifying_status: QualifyingStatus
    documentation_completeness: DocumentationCompleteness
    qualifying_monthly_income: Decimal
    continuance_risk: ContinuanceRisk
    missing_documents: List[str]
    issues: List[str]
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ContinuanceResult:
    """Result of assessing income continuance likelihood."""
    income_type: NonTraditionalIncomeType
    risk: ContinuanceRisk
    meets_minimum_history: bool
    history_years: int
    required_years: int
    remaining_term_months: Optional[int]  # For notes receivable, contracts
    evidence_summary: str
    flags: List[str] = field(default_factory=list)


# =============================================================================
# Service
# =============================================================================

class NonTraditionalIncomeService:
    """
    Handles income types outside standard W-2 and self-employment categories.

    All public methods enforce org_id isolation via SQL WHERE clauses.
    The service is async-ready for integration with FastAPI route handlers
    while keeping DB operations synchronous through SQLAlchemy.
    """

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id

    # =========================================================================
    # 1. INCOME CLASSIFICATION
    # =========================================================================

    async def classify_income_type(
        self,
        income_data: Dict[str, Any],
    ) -> IncomeClassification:
        """
        Classify an income source into a non-traditional category.

        Args:
            income_data: Dictionary containing at minimum:
                - source_name: str (employer/platform name)
                - description: str (free text description)
                - annual_amount: Decimal or float
                - tax_forms: list[str] (e.g., ["1099-NEC", "Schedule C"])
                Optional:
                - platform: str (e.g., "uber", "airbnb")
                - currency: str (ISO currency code)
                - is_tax_exempt: bool
                - country_of_origin: str

        Returns:
            IncomeClassification with type, qualifying status, and doc requirements.
        """
        source_name = (income_data.get("source_name") or "").lower().strip()
        description = (income_data.get("description") or "").lower().strip()
        platform = (income_data.get("platform") or "").lower().strip()
        tax_forms = [f.upper() for f in (income_data.get("tax_forms") or [])]
        currency = (income_data.get("currency") or "USD").upper()
        is_tax_exempt = income_data.get("is_tax_exempt", False)
        country = (income_data.get("country_of_origin") or "").upper()

        combined_text = f"{source_name} {description} {platform}"

        # --- Cryptocurrency: check first (always flag) ---
        if self._matches_crypto(combined_text):
            return self._classify_cryptocurrency()

        # --- Gig platform match ---
        platform_category, platform_match = self._identify_gig_platform(
            source_name, platform, combined_text,
        )
        if platform_category:
            income_type = self._gig_category_to_type(platform_category)
            return IncomeClassification(
                income_type=income_type,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=platform_category,
                platform_name=platform_match,
                confidence=85,
                reasoning=(
                    f"Identified as gig/{platform_category} income from "
                    f"platform '{platform_match}'. Requires 2-year history and "
                    f"Schedule C / 1099 documentation."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(income_type),
                flags=["GIG_INCOME_REQUIRES_2YR_HISTORY"],
            )

        # --- Foreign income ---
        if currency != "USD" or country not in ("", "US", "USA"):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.FOREIGN,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=75,
                reasoning=(
                    f"Foreign income detected (currency={currency}, country={country}). "
                    f"Requires employment contract verification, currency conversion, "
                    f"and Form 2555 analysis."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.FOREIGN,
                ),
                flags=["FOREIGN_INCOME_CURRENCY_CONVERSION_REQUIRED"],
            )

        # --- Tax-exempt / foster care ---
        if is_tax_exempt and self._matches_foster_care(combined_text):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.FOSTER_CARE,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=80,
                reasoning=(
                    "Tax-exempt foster care income identified. Can be grossed up "
                    "by 25% for qualifying. Requires 12-month continuance verification."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.FOSTER_CARE,
                ),
                flags=["TAX_EXEMPT_GROSSUP_ELIGIBLE"],
            )

        # --- Trust income ---
        if self._matches_trust(combined_text, tax_forms):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.TRUST,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=70,
                reasoning=(
                    "Trust distribution income identified. Must verify irrevocable "
                    "trust status and 3-year continuance from trust terms."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.TRUST,
                ),
                flags=["TRUST_IRREVOCABLE_VERIFICATION_REQUIRED"],
            )

        # --- Notes receivable ---
        if self._matches_notes_receivable(combined_text, tax_forms):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.NOTES_RECEIVABLE,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=70,
                reasoning=(
                    "Notes receivable income identified. Remaining term must cover "
                    "3+ years. 12-month payment history required."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.NOTES_RECEIVABLE,
                ),
                flags=["NOTES_RECEIVABLE_TERM_VERIFICATION_REQUIRED"],
            )

        # --- Royalty income ---
        if self._matches_royalty(combined_text, tax_forms):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.ROYALTY,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=75,
                reasoning=(
                    "Royalty income identified. Requires 2-year history and "
                    "Schedule E Part I analysis. Trending must be assessed."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.ROYALTY,
                ),
                flags=["ROYALTY_TRENDING_ANALYSIS_REQUIRED"],
            )

        # --- Capital gains ---
        if self._matches_capital_gains(combined_text, tax_forms):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.CAPITAL_GAINS,
                qualifying_status=QualifyingStatus.NOT_QUALIFYING,
                platform_category=None,
                platform_name=None,
                confidence=80,
                reasoning=(
                    "Capital gains income is generally NOT used for qualifying "
                    "because it is not reliable recurring income. Exception: "
                    "day traders with 2+ years of documented trading history."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.CAPITAL_GAINS,
                ),
                flags=["CAPITAL_GAINS_NOT_QUALIFYING_DEFAULT"],
                warnings=[
                    "Capital gains are not considered stable qualifying income "
                    "under standard agency guidelines."
                ],
            )

        # --- Boarder income ---
        if self._matches_boarder(combined_text):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.BOARDER,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=70,
                reasoning=(
                    "Boarder income (room rental in primary residence). Limited "
                    "to 30% of housing payment offset. Requires 12-month "
                    "documentation history."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.BOARDER,
                ),
                flags=["BOARDER_INCOME_30PCT_LIMIT"],
            )

        # --- Seasonal ---
        if self._matches_seasonal(combined_text):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.SEASONAL,
                qualifying_status=QualifyingStatus.QUALIFYING_WITH_CONDITIONS,
                platform_category=None,
                platform_name=None,
                confidence=70,
                reasoning=(
                    "Seasonal employment income identified. Must average over "
                    "2 years including off-season periods. Unemployment comp "
                    "may be included if consistent pattern."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.SEASONAL,
                ),
                flags=["SEASONAL_2YR_AVERAGE_REQUIRED"],
            )

        # --- Non-borrower household income ---
        if self._matches_non_borrower(combined_text):
            return IncomeClassification(
                income_type=NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD,
                qualifying_status=QualifyingStatus.COMPENSATING_FACTOR_ONLY,
                platform_category=None,
                platform_name=None,
                confidence=85,
                reasoning=(
                    "Non-borrower household income cannot be used for qualifying "
                    "but may serve as a compensating factor."
                ),
                documentation_requirements=self._get_doc_requirements_for_type(
                    NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD,
                ),
                flags=["NON_BORROWER_COMPENSATING_FACTOR_ONLY"],
            )

        # --- Fallback: unclassified ---
        return IncomeClassification(
            income_type=NonTraditionalIncomeType.UNCLASSIFIED,
            qualifying_status=QualifyingStatus.NEEDS_REVIEW,
            platform_category=None,
            platform_name=None,
            confidence=30,
            reasoning=(
                "Unable to automatically classify this income source. "
                "Manual underwriter review is required."
            ),
            documentation_requirements=[],
            flags=["UNCLASSIFIED_INCOME_MANUAL_REVIEW"],
        )

    # =========================================================================
    # 2. GIG INCOME CALCULATION
    # =========================================================================

    async def calculate_gig_income(
        self,
        org_id: int,
        borrower_id: int,
        platforms: List[str],
        tax_data: Dict[str, Any],
    ) -> GigIncomeResult:
        """
        Calculate qualifying income from gig economy / 1099 platform work.

        Args:
            org_id: Organization ID for tenant isolation.
            borrower_id: Borrower (lead) ID.
            platforms: List of platform names (e.g., ["uber", "doordash"]).
            tax_data: Tax return data containing:
                - year1: dict with gross_revenue, expenses (by category), net_income
                - year2: dict with same structure (prior year)
                - year3: (optional) dict for third year
                - form_types: list[str] (e.g., ["1099-K", "Schedule C"])

        Returns:
            GigIncomeResult with qualifying monthly income and analysis.
        """
        self._verify_org(org_id)

        year1_data = tax_data.get("year1", {})
        year2_data = tax_data.get("year2", {})
        year3_data = tax_data.get("year3")
        form_types = tax_data.get("form_types", [])

        flags: List[str] = []
        recommendations: List[str] = []
        tasks: List[Dict[str, Any]] = []

        # Parse income amounts
        y1_gross = self._to_decimal(year1_data.get("gross_revenue", 0))
        y1_expenses = self._to_decimal(year1_data.get("total_expenses", 0))
        y1_net = self._to_decimal(year1_data.get("net_income")) or (y1_gross - y1_expenses)

        y2_gross = self._to_decimal(year2_data.get("gross_revenue", 0))
        y2_expenses = self._to_decimal(year2_data.get("total_expenses", 0))
        y2_net = self._to_decimal(year2_data.get("net_income")) or (y2_gross - y2_expenses)

        y3_net: Optional[Decimal] = None
        if year3_data:
            y3_net = self._to_decimal(year3_data.get("net_income", 0))

        # Determine history length
        history_years = 2
        if y3_net is not None and y3_net > ZERO:
            history_years = 3
        if y2_net <= ZERO and y1_net > ZERO:
            history_years = 1
            flags.append("ONLY_1_YEAR_HISTORY")
            recommendations.append(
                "Only 1 year of gig income history available. Most agencies "
                "require 2 years. Consider obtaining prior year returns."
            )

        # Expense analysis
        expense_categories = year1_data.get("expense_categories", {})
        expense_ratio = (
            (y1_expenses / y1_gross * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if y1_gross > ZERO else ZERO
        )
        expense_analysis = ExpenseAnalysis(
            gross_revenue=y1_gross,
            total_expenses=y1_expenses,
            net_income=y1_net,
            expense_ratio_pct=expense_ratio,
            major_categories={
                k: self._to_decimal(v) for k, v in expense_categories.items()
            },
        )

        if expense_ratio > Decimal("70"):
            expense_analysis.flags.append("HIGH_EXPENSE_RATIO")
            flags.append("HIGH_EXPENSE_RATIO_OVER_70PCT")
            recommendations.append(
                "Expense ratio exceeds 70%. Verify business expenses are "
                "legitimate and ongoing. Consider requesting P&L statement."
            )

        # Trending analysis
        trend = self._analyze_trend(y1_net, y2_net, y3_net)
        if trend.direction == "declining":
            flags.append("DECLINING_GIG_INCOME")
            if trend.yoy_change_pct and abs(trend.yoy_change_pct) > DECLINING_CRITICAL_PCT:
                flags.append("SEVERE_INCOME_DECLINE")
                tasks.append({
                    "task_type": "review_declining_income",
                    "title": f"Review declining gig income ({trend.yoy_change_pct}% YoY)",
                    "priority": "high",
                    "description": (
                        f"Gig income from {', '.join(platforms)} declined "
                        f"{abs(trend.yoy_change_pct)}% year-over-year. "
                        f"Review for continuance likelihood."
                    ),
                })

        # Calculate qualifying income
        # Per FNMA guidelines: use 2-year average when stable/increasing,
        # use most recent year when declining
        if trend.use_lower_year:
            qualifying_annual = y1_net
            flags.append("USING_MOST_RECENT_YEAR_DECLINING")
        elif history_years >= 2:
            qualifying_annual = (
                trend.two_year_avg if trend.two_year_avg else
                ((y1_net + y2_net) / 2)
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            qualifying_annual = y1_net

        qualifying_monthly = (qualifying_annual / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        # Assess documentation completeness
        has_1099 = any(f in ("1099-K", "1099-NEC", "1099-MISC") for f in form_types)
        has_schedule_c = "SCHEDULE C" in [f.upper().replace(" ", "_") for f in form_types] or \
                         "Schedule C" in form_types
        doc_completeness = DocumentationCompleteness.COMPLETE
        if not has_1099:
            doc_completeness = DocumentationCompleteness.PARTIALLY_COMPLETE
            flags.append("MISSING_1099_FORMS")
            recommendations.append("Request 1099-K/1099-NEC from platform(s).")
        if not has_schedule_c:
            doc_completeness = DocumentationCompleteness.PARTIALLY_COMPLETE
            flags.append("MISSING_SCHEDULE_C")
            recommendations.append("Request Schedule C from tax returns.")

        if history_years < MIN_HISTORY_YEARS_GIG:
            doc_completeness = DocumentationCompleteness.INSUFFICIENT
            flags.append("INSUFFICIENT_HISTORY")

        # Negative qualifying income
        if qualifying_monthly <= ZERO:
            flags.append("NEGATIVE_OR_ZERO_QUALIFYING_INCOME")
            recommendations.append(
                "Net gig income is zero or negative. This income source "
                "cannot be used for qualifying."
            )
            qualifying_monthly = ZERO
            qualifying_annual = ZERO

        # Confidence
        confidence = self._compute_confidence(
            has_docs=(has_1099 and has_schedule_c),
            history_years=history_years,
            min_years=MIN_HISTORY_YEARS_GIG,
            trend_direction=trend.direction,
        )

        return GigIncomeResult(
            borrower_id=borrower_id,
            platforms=platforms,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if confidence >= CONFIDENCE_HIGH and history_years >= 2
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS
                if qualifying_monthly > ZERO
                else QualifyingStatus.NOT_QUALIFYING
            ),
            gross_annual_income=y1_gross,
            total_expenses=y1_expenses,
            net_annual_income=y1_net,
            qualifying_monthly_income=qualifying_monthly,
            trend=trend,
            expense_analysis=expense_analysis,
            documentation_completeness=doc_completeness,
            history_years=history_years,
            confidence=confidence,
            flags=flags,
            recommendations=recommendations,
            tasks_to_create=tasks,
        )

    # =========================================================================
    # 3. SEASONAL INCOME CALCULATION
    # =========================================================================

    async def calculate_seasonal_income(
        self,
        org_id: int,
        borrower_id: int,
        employment_data: Dict[str, Any],
    ) -> SeasonalResult:
        """
        Calculate qualifying income for seasonal workers.

        Args:
            org_id: Organization ID.
            borrower_id: Borrower (lead) ID.
            employment_data: Dictionary containing:
                - industry: str (e.g., "construction", "agriculture", "tourism")
                - year1_earnings: Decimal/float (most recent full year W-2)
                - year2_earnings: Decimal/float (prior year)
                - months_active_per_year: int (typical months of work)
                - unemployment_annual: Decimal/float (off-season unemployment comp)
                - unemployment_consistent: bool (has pattern over 2+ years)

        Returns:
            SeasonalResult with 2-year averaged qualifying income.
        """
        self._verify_org(org_id)

        industry = employment_data.get("industry", "unspecified")
        y1_earnings = self._to_decimal(employment_data.get("year1_earnings", 0))
        y2_earnings = self._to_decimal(employment_data.get("year2_earnings", 0))
        months_active = int(employment_data.get("months_active_per_year", 12))
        unemployment_annual = self._to_decimal(employment_data.get("unemployment_annual", 0))
        unemployment_consistent = employment_data.get("unemployment_consistent", False)

        flags: List[str] = []
        recommendations: List[str] = []
        tasks: List[Dict[str, Any]] = []

        # Validate inputs
        if months_active < 1 or months_active > 12:
            months_active = max(1, min(months_active, 12))
            flags.append("INVALID_MONTHS_ACTIVE_CLAMPED")

        # Determine if unemployment can be included
        # Per FNMA B3-3.1-09: Unemployment income can be used if borrower has
        # a 2-year history of receiving it as a seasonal worker
        include_unemployment = (
            unemployment_annual > ZERO
            and unemployment_consistent
        )

        if unemployment_annual > ZERO and not unemployment_consistent:
            flags.append("UNEMPLOYMENT_NOT_CONSISTENT_PATTERN")
            recommendations.append(
                "Unemployment compensation is present but does not show a "
                "consistent 2-year pattern. Cannot include in qualifying income."
            )

        # Calculate 2-year average including full year (work + off-season)
        y1_total = y1_earnings + (unemployment_annual if include_unemployment else ZERO)
        y2_total = y2_earnings + (unemployment_annual if include_unemployment else ZERO)

        two_year_avg = ((y1_total + y2_total) / 2).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        # Trending
        trend = self._analyze_trend(y1_earnings, y2_earnings)

        # When declining, use the lower (most recent) year per agency guidelines
        if trend.use_lower_year:
            qualifying_annual = y1_total
            flags.append("USING_MOST_RECENT_YEAR_DECLINING")
        else:
            qualifying_annual = two_year_avg

        qualifying_monthly = (qualifying_annual / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        if trend.direction == "declining":
            flags.append("DECLINING_SEASONAL_INCOME")
            tasks.append({
                "task_type": "review_declining_income",
                "title": f"Review declining seasonal income ({industry})",
                "priority": "medium",
                "description": (
                    f"Seasonal {industry} income declined "
                    f"{abs(trend.yoy_change_pct or ZERO)}% YoY. "
                    f"Verify employer status and rehire expectation."
                ),
            })

        # Documentation completeness
        has_both_years = y1_earnings > ZERO and y2_earnings > ZERO
        doc_completeness = (
            DocumentationCompleteness.COMPLETE if has_both_years
            else DocumentationCompleteness.PARTIALLY_COMPLETE
            if y1_earnings > ZERO
            else DocumentationCompleteness.INSUFFICIENT
        )

        if not has_both_years:
            flags.append("MISSING_SECOND_YEAR_EARNINGS")
            recommendations.append(
                "Two years of seasonal earnings required. Request prior year W-2."
            )

        confidence = self._compute_confidence(
            has_docs=has_both_years,
            history_years=2 if has_both_years else 1,
            min_years=MIN_HISTORY_YEARS_SEASONAL,
            trend_direction=trend.direction,
        )

        return SeasonalResult(
            borrower_id=borrower_id,
            industry=industry,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if has_both_years and confidence >= CONFIDENCE_MEDIUM
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS
            ),
            year1_earnings=y1_earnings,
            year2_earnings=y2_earnings,
            two_year_average_annual=two_year_avg,
            qualifying_monthly_income=qualifying_monthly,
            off_season_unemployment=unemployment_annual,
            unemployment_included=include_unemployment,
            months_active_per_year=months_active,
            trend=trend,
            documentation_completeness=doc_completeness,
            confidence=confidence,
            flags=flags,
            recommendations=recommendations,
            tasks_to_create=tasks,
        )

    # =========================================================================
    # 4. VALIDATE NON-TRADITIONAL SOURCE
    # =========================================================================

    async def validate_non_traditional_source(
        self,
        income_type: NonTraditionalIncomeType,
        documentation: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate documentation and calculate qualifying income for any
        non-traditional income type.

        Args:
            income_type: The classified income type.
            documentation: Dictionary containing income-type-specific fields:
                Common fields:
                    - annual_amount: Decimal/float
                    - history_years: int
                    - documents_provided: list[str] (doc type names on file)
                Type-specific fields vary (see individual handlers).

        Returns:
            ValidationResult with qualifying status and documentation assessment.
        """
        handler = self._get_validation_handler(income_type)
        return await handler(documentation)

    # =========================================================================
    # 5. DOCUMENTATION REQUIREMENTS
    # =========================================================================

    def get_documentation_requirements(
        self,
        income_type: NonTraditionalIncomeType,
    ) -> List[DocRequirement]:
        """
        Return the documentation requirements for a given income type.

        Args:
            income_type: The non-traditional income type.

        Returns:
            Ordered list of DocRequirement objects.
        """
        return self._get_doc_requirements_for_type(income_type)

    # =========================================================================
    # 6. CONTINUANCE ASSESSMENT
    # =========================================================================

    async def assess_continuance(
        self,
        income_type: NonTraditionalIncomeType,
        history: Dict[str, Any],
        documentation: Dict[str, Any],
    ) -> ContinuanceResult:
        """
        Assess the likelihood that a non-traditional income source will continue
        for at least 3 years (agency requirement).

        Args:
            income_type: The classified income type.
            history: Dictionary with:
                - years_of_history: int
                - amounts_by_year: dict[str, Decimal] (e.g., {"2024": 50000, "2023": 48000})
                - is_contract_based: bool
                - contract_end_date: str (ISO date, if applicable)
            documentation: Dictionary with:
                - documents_provided: list[str]
                - has_continuance_letter: bool
                - has_employment_contract: bool
                - trust_is_irrevocable: bool (for trust income)
                - note_remaining_months: int (for notes receivable)

        Returns:
            ContinuanceResult with risk assessment.
        """
        years = history.get("years_of_history", 0)
        amounts = history.get("amounts_by_year", {})
        is_contract = history.get("is_contract_based", False)
        contract_end = history.get("contract_end_date")
        docs_provided = documentation.get("documents_provided", [])
        has_continuance = documentation.get("has_continuance_letter", False)
        has_contract = documentation.get("has_employment_contract", False)

        required_years = self._get_required_history_years(income_type)
        meets_minimum = years >= required_years

        flags: List[str] = []
        remaining_months: Optional[int] = None

        # Check contract end date for remaining term
        if contract_end:
            try:
                end_date = date.fromisoformat(contract_end)
                remaining_months = max(
                    0,
                    (end_date.year - date.today().year) * 12
                    + (end_date.month - date.today().month),
                )
                if remaining_months < 36:
                    flags.append("CONTRACT_ENDS_WITHIN_3_YEARS")
            except (ValueError, TypeError):
                flags.append("INVALID_CONTRACT_END_DATE")

        # Notes receivable: check remaining term
        if income_type == NonTraditionalIncomeType.NOTES_RECEIVABLE:
            note_months = documentation.get("note_remaining_months")
            if note_months is not None:
                remaining_months = note_months
                if note_months < 36:
                    flags.append("NOTE_REMAINING_TERM_UNDER_3_YEARS")

        # Trust: check irrevocable status
        if income_type == NonTraditionalIncomeType.TRUST:
            if not documentation.get("trust_is_irrevocable", False):
                flags.append("TRUST_NOT_CONFIRMED_IRREVOCABLE")

        # Trending check across years
        sorted_years = sorted(amounts.keys())
        if len(sorted_years) >= 2:
            recent = self._to_decimal(amounts[sorted_years[-1]])
            prior = self._to_decimal(amounts[sorted_years[-2]])
            if prior > ZERO:
                change_pct = ((recent - prior) / prior * 100).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                if change_pct < -DECLINING_CRITICAL_PCT:
                    flags.append("SEVERE_DECLINING_TREND")
                elif change_pct < -DECLINING_WARN_PCT:
                    flags.append("DECLINING_TREND")

        # Determine risk level
        risk = self._assess_continuance_risk(
            income_type=income_type,
            meets_minimum=meets_minimum,
            remaining_months=remaining_months,
            has_continuance_letter=has_continuance,
            has_contract=has_contract or is_contract,
            flags=flags,
        )

        evidence_parts = []
        if meets_minimum:
            evidence_parts.append(f"{years} years of history (required: {required_years})")
        else:
            evidence_parts.append(
                f"Only {years} years of history (required: {required_years})"
            )
        if remaining_months is not None:
            evidence_parts.append(f"Remaining term: {remaining_months} months")
        if has_continuance:
            evidence_parts.append("Continuance letter on file")
        if has_contract:
            evidence_parts.append("Employment contract verified")

        return ContinuanceResult(
            income_type=income_type,
            risk=risk,
            meets_minimum_history=meets_minimum,
            history_years=years,
            required_years=required_years,
            remaining_term_months=remaining_months,
            evidence_summary="; ".join(evidence_parts) if evidence_parts else "No evidence provided",
            flags=flags,
        )

    # =========================================================================
    # PRIVATE: Classification helpers
    # =========================================================================

    def _identify_gig_platform(
        self,
        source_name: str,
        platform: str,
        combined_text: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Identify a gig platform from text, returning (category, platform_name)."""
        search_text = f"{source_name} {platform} {combined_text}"
        for category, platform_list in GIG_PLATFORMS.items():
            for p in platform_list:
                if p in search_text:
                    return category, p
        return None, None

    def _gig_category_to_type(self, category: str) -> NonTraditionalIncomeType:
        """Map a gig platform category to an income type enum."""
        mapping = {
            "rideshare": NonTraditionalIncomeType.GIG_RIDESHARE,
            "delivery": NonTraditionalIncomeType.GIG_DELIVERY,
            "freelance": NonTraditionalIncomeType.GIG_FREELANCE,
            "marketplace": NonTraditionalIncomeType.GIG_MARKETPLACE,
            "rental": NonTraditionalIncomeType.GIG_RENTAL_PLATFORM,
            "task": NonTraditionalIncomeType.GIG_TASK,
        }
        return mapping.get(category, NonTraditionalIncomeType.GIG_OTHER)

    def _matches_crypto(self, text: str) -> bool:
        crypto_keywords = [
            "bitcoin", "ethereum", "crypto", "cryptocurrency", "btc", "eth",
            "defi", "nft", "blockchain", "coinbase", "binance", "kraken",
            "mining", "staking", "yield farming",
        ]
        return any(kw in text for kw in crypto_keywords)

    def _matches_foster_care(self, text: str) -> bool:
        keywords = [
            "foster care", "foster parent", "foster child",
            "therapeutic foster", "dfcs", "dcfs", "dss",
        ]
        return any(kw in text for kw in keywords)

    def _matches_trust(self, text: str, tax_forms: List[str]) -> bool:
        text_match = any(
            kw in text for kw in [
                "trust", "irrevocable", "revocable trust", "family trust",
                "living trust", "testamentary",
            ]
        )
        form_match = any(
            f in ("K-1", "1041 SCHEDULE K-1", "1041") for f in tax_forms
        )
        return text_match or form_match

    def _matches_notes_receivable(self, text: str, tax_forms: List[str]) -> bool:
        keywords = [
            "note receivable", "notes receivable", "promissory note",
            "seller financing", "installment sale", "note income",
        ]
        return any(kw in text for kw in keywords) or "1099-INT" in tax_forms

    def _matches_royalty(self, text: str, tax_forms: List[str]) -> bool:
        keywords = [
            "royalty", "royalties", "patent", "copyright", "mineral rights",
            "oil gas", "oil & gas", "licensing fee", "intellectual property",
        ]
        form_match = "SCHEDULE E" in [f.upper().replace(" ", "_") for f in tax_forms]
        return any(kw in text for kw in keywords) or form_match

    def _matches_capital_gains(self, text: str, tax_forms: List[str]) -> bool:
        keywords = [
            "capital gain", "capital gains", "stock sale", "securities",
            "day trading", "day trader", "stock trading",
        ]
        form_match = any(f in ("SCHEDULE D", "FORM 8949", "1099-B") for f in tax_forms)
        return any(kw in text for kw in keywords) or form_match

    def _matches_boarder(self, text: str) -> bool:
        keywords = [
            "boarder", "room rental", "renting room", "roommate rent",
            "room and board", "house sharing",
        ]
        return any(kw in text for kw in keywords)

    def _matches_seasonal(self, text: str) -> bool:
        keywords = [
            "seasonal", "construction worker", "agricultural", "farm worker",
            "tourism", "ski instructor", "lifeguard", "camp counselor",
            "harvest", "fishing", "landscaping seasonal", "snow removal",
        ]
        return any(kw in text for kw in keywords)

    def _matches_non_borrower(self, text: str) -> bool:
        keywords = [
            "non-borrower", "non borrower", "household income",
            "spouse income", "partner income", "household member",
        ]
        return any(kw in text for kw in keywords)

    def _classify_cryptocurrency(self) -> IncomeClassification:
        """Cryptocurrency income is generally not acceptable."""
        return IncomeClassification(
            income_type=NonTraditionalIncomeType.CRYPTOCURRENCY,
            qualifying_status=QualifyingStatus.NOT_QUALIFYING,
            platform_category=None,
            platform_name=None,
            confidence=90,
            reasoning=(
                "Cryptocurrency income is generally NOT acceptable as "
                "qualifying income for mortgage purposes. It is too volatile "
                "and speculative. If the borrower has a 2+ year pattern of "
                "realized capital gains from crypto trading, it may be "
                "evaluated under capital gains guidelines (Schedule D)."
            ),
            documentation_requirements=self._get_doc_requirements_for_type(
                NonTraditionalIncomeType.CRYPTOCURRENCY,
            ),
            flags=["CRYPTOCURRENCY_NOT_QUALIFYING"],
            warnings=[
                "Cryptocurrency income cannot be used for qualifying. "
                "Document and flag for underwriter awareness."
            ],
        )

    # =========================================================================
    # PRIVATE: Validation handlers
    # =========================================================================

    def _get_validation_handler(self, income_type: NonTraditionalIncomeType):
        """Return the appropriate async validation handler for an income type."""
        handlers = {
            NonTraditionalIncomeType.GIG_RIDESHARE: self._validate_gig,
            NonTraditionalIncomeType.GIG_DELIVERY: self._validate_gig,
            NonTraditionalIncomeType.GIG_FREELANCE: self._validate_gig,
            NonTraditionalIncomeType.GIG_MARKETPLACE: self._validate_gig,
            NonTraditionalIncomeType.GIG_RENTAL_PLATFORM: self._validate_gig,
            NonTraditionalIncomeType.GIG_TASK: self._validate_gig,
            NonTraditionalIncomeType.GIG_OTHER: self._validate_gig,
            NonTraditionalIncomeType.SEASONAL: self._validate_seasonal,
            NonTraditionalIncomeType.FOREIGN: self._validate_foreign,
            NonTraditionalIncomeType.TRUST: self._validate_trust,
            NonTraditionalIncomeType.NOTES_RECEIVABLE: self._validate_notes_receivable,
            NonTraditionalIncomeType.ROYALTY: self._validate_royalty,
            NonTraditionalIncomeType.CAPITAL_GAINS: self._validate_capital_gains,
            NonTraditionalIncomeType.BOARDER: self._validate_boarder,
            NonTraditionalIncomeType.FOSTER_CARE: self._validate_foster_care,
            NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD: self._validate_non_borrower,
            NonTraditionalIncomeType.CRYPTOCURRENCY: self._validate_cryptocurrency,
        }
        return handlers.get(income_type, self._validate_generic)

    async def _validate_gig(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate gig economy income documentation."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])
        expenses = self._to_decimal(doc.get("total_expenses", 0))

        required_docs = ["1099-K", "1099-NEC", "Schedule C", "Tax Returns (2 years)"]
        missing = [d for d in required_docs if d not in docs_provided]

        net_income = annual_amount - expenses
        qualifying_monthly = max(
            ZERO,
            (net_income / MONTHS_PER_YEAR).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        )

        flags = []
        issues = []
        if history_years < MIN_HISTORY_YEARS_GIG:
            issues.append(f"Only {history_years} year(s) of history; {MIN_HISTORY_YEARS_GIG} required.")
            flags.append("INSUFFICIENT_HISTORY")
        if net_income <= ZERO:
            issues.append("Net income is zero or negative after expenses.")
            flags.append("NEGATIVE_NET_INCOME")
        if missing:
            issues.append(f"Missing documentation: {', '.join(missing)}")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = not issues or (history_years >= MIN_HISTORY_YEARS_GIG and net_income > ZERO)

        return ValidationResult(
            income_type=NonTraditionalIncomeType.GIG_OTHER,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NOT_QUALIFYING
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly,
            continuance_risk=ContinuanceRisk.MODERATE if history_years >= 2 else ContinuanceRisk.HIGH,
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                f"Obtain {d}" for d in missing
            ] if missing else [],
        )

    async def _validate_seasonal(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate seasonal employment income."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])

        required_docs = ["W-2 (2 years)", "Employer verification letter", "Tax Returns (2 years)"]
        missing = [d for d in required_docs if d not in docs_provided]

        qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        issues = []
        flags = []
        if history_years < MIN_HISTORY_YEARS_SEASONAL:
            issues.append(f"Only {history_years} year(s); {MIN_HISTORY_YEARS_SEASONAL} required.")
            flags.append("INSUFFICIENT_SEASONAL_HISTORY")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = history_years >= MIN_HISTORY_YEARS_SEASONAL and annual_amount > ZERO

        return ValidationResult(
            income_type=NonTraditionalIncomeType.SEASONAL,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NEEDS_REVIEW
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=ContinuanceRisk.LOW if history_years >= 2 else ContinuanceRisk.MODERATE,
            missing_documents=missing,
            issues=issues,
            flags=flags,
        )

    async def _validate_foreign(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate foreign income documentation."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])
        has_contract = doc.get("has_employment_contract", False)
        currency = doc.get("currency", "USD")

        required_docs = [
            "Employment contract", "Tax Returns (2 years)", "Form 2555",
            "Currency conversion documentation",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        issues = []
        flags = []
        if not has_contract:
            issues.append("Employment contract not provided for continuance verification.")
            flags.append("MISSING_EMPLOYMENT_CONTRACT")
        if currency != "USD":
            flags.append("REQUIRES_CURRENCY_CONVERSION")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE
        )

        is_valid = annual_amount > ZERO and has_contract

        return ValidationResult(
            income_type=NonTraditionalIncomeType.FOREIGN,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NEEDS_REVIEW
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=ContinuanceRisk.MODERATE if has_contract else ContinuanceRisk.HIGH,
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                "Verify employment contract for continuance.",
                "Obtain current exchange rate documentation.",
            ] if not has_contract else [],
        )

    async def _validate_trust(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate trust distribution income."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])
        is_irrevocable = doc.get("trust_is_irrevocable", False)

        required_docs = [
            "Trust agreement", "K-1 (3 years)", "Trust distribution statements",
            "CPA letter confirming distributions",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        issues = []
        flags = []
        if not is_irrevocable:
            issues.append(
                "Trust must be irrevocable for distributions to qualify. "
                "Revocable trust distributions are not guaranteed to continue."
            )
            flags.append("TRUST_NOT_IRREVOCABLE")
        if history_years < MIN_HISTORY_YEARS_TRUST:
            issues.append(
                f"Only {history_years} year(s) of trust distributions; "
                f"{MIN_HISTORY_YEARS_TRUST} required."
            )
            flags.append("INSUFFICIENT_TRUST_HISTORY")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = is_irrevocable and history_years >= MIN_HISTORY_YEARS_TRUST and annual_amount > ZERO

        return ValidationResult(
            income_type=NonTraditionalIncomeType.TRUST,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NOT_QUALIFYING
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=(
                ContinuanceRisk.LOW if is_irrevocable and history_years >= 3
                else ContinuanceRisk.MODERATE if is_irrevocable
                else ContinuanceRisk.UNACCEPTABLE
            ),
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                "Obtain trust agreement showing irrevocable status.",
                "Request 3 years of K-1 forms from trust.",
            ] if not is_irrevocable else [],
        )

    async def _validate_notes_receivable(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate notes receivable income."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])
        remaining_months = doc.get("note_remaining_months", 0)
        payment_history_months = doc.get("payment_history_months", 0)

        required_docs = [
            "Promissory note / loan agreement",
            "12 months payment history (bank statements)",
            "Amortization schedule",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        issues = []
        flags = []
        if remaining_months < 36:
            issues.append(
                f"Note remaining term is {remaining_months} months; "
                f"minimum 36 months required for qualifying income."
            )
            flags.append("NOTE_TERM_TOO_SHORT")
        if payment_history_months < 12:
            issues.append(
                f"Only {payment_history_months} months of payment history; "
                f"12 months required."
            )
            flags.append("INSUFFICIENT_PAYMENT_HISTORY")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = (
            remaining_months >= 36
            and payment_history_months >= 12
            and annual_amount > ZERO
        )

        return ValidationResult(
            income_type=NonTraditionalIncomeType.NOTES_RECEIVABLE,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NOT_QUALIFYING
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=(
                ContinuanceRisk.LOW if remaining_months >= 60
                else ContinuanceRisk.MODERATE if remaining_months >= 36
                else ContinuanceRisk.HIGH
            ),
            missing_documents=missing,
            issues=issues,
            flags=flags,
        )

    async def _validate_royalty(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate royalty income."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        docs_provided = doc.get("documents_provided", [])
        royalty_source = doc.get("royalty_source", "unspecified")

        required_docs = [
            "Schedule E Part I (2 years)",
            "Royalty agreement / contract",
            "1099-MISC (2 years)",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        issues = []
        flags = []
        if history_years < MIN_HISTORY_YEARS_ROYALTY:
            issues.append(
                f"Only {history_years} year(s) of royalty history; "
                f"{MIN_HISTORY_YEARS_ROYALTY} required."
            )
            flags.append("INSUFFICIENT_ROYALTY_HISTORY")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = history_years >= MIN_HISTORY_YEARS_ROYALTY and annual_amount > ZERO

        return ValidationResult(
            income_type=NonTraditionalIncomeType.ROYALTY,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NEEDS_REVIEW
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=ContinuanceRisk.MODERATE,
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                f"Trending analysis required for {royalty_source} royalties.",
                "Request Schedule E Part I for 2 most recent tax years.",
            ] if not is_valid else [],
        )

    async def _validate_capital_gains(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate capital gains income (generally not qualifying)."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_years = doc.get("history_years", 0)
        is_day_trader = doc.get("is_day_trader", False)
        docs_provided = doc.get("documents_provided", [])

        flags = ["CAPITAL_GAINS_NOT_QUALIFYING_DEFAULT"]
        issues = ["Capital gains are generally not used for qualifying income."]
        qualifying_monthly = ZERO

        # Exception: day traders with 2+ year consistent history
        if is_day_trader and history_years >= MIN_HISTORY_YEARS_CAPITAL_GAINS_DAY_TRADER:
            qualifying_monthly = (annual_amount / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            flags = ["DAY_TRADER_EXCEPTION_APPLIED"]
            issues = [
                "Day trader exception: 2+ years of consistent trading history. "
                "Manual underwriter review required."
            ]

        required_docs = ["Schedule D (2 years)", "Form 8949", "Brokerage statements (24 months)"]
        missing = [d for d in required_docs if d not in docs_provided]

        is_valid = is_day_trader and history_years >= MIN_HISTORY_YEARS_CAPITAL_GAINS_DAY_TRADER

        return ValidationResult(
            income_type=NonTraditionalIncomeType.CAPITAL_GAINS,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NOT_QUALIFYING
            ),
            documentation_completeness=(
                DocumentationCompleteness.COMPLETE if not missing and is_valid
                else DocumentationCompleteness.NOT_PROVIDED
            ),
            qualifying_monthly_income=qualifying_monthly,
            continuance_risk=ContinuanceRisk.HIGH,
            missing_documents=missing if is_valid else [],
            issues=issues,
            flags=flags,
            recommendations=[
                "Capital gains should not be used for qualifying unless "
                "borrower is a documented day trader with 2+ year history."
            ],
        )

    async def _validate_boarder(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate boarder income (room rental in primary residence)."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_months = doc.get("history_months", 0)
        docs_provided = doc.get("documents_provided", [])
        monthly_housing_payment = self._to_decimal(doc.get("monthly_housing_payment", 0))

        required_docs = [
            "Rental/boarder agreement",
            "12 months cancelled checks or bank statements",
            "Shared living documentation",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        # Boarder income limited to 30% of housing payment offset
        monthly_boarder = (annual_amount / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )
        if monthly_housing_payment > ZERO:
            max_offset = (monthly_housing_payment * BOARDER_INCOME_MAX_OFFSET_PCT).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            qualifying_monthly = min(monthly_boarder, max_offset)
        else:
            qualifying_monthly = monthly_boarder

        issues = []
        flags = []
        if history_months < 12:
            issues.append(
                f"Only {history_months} months of boarder history; 12 months required."
            )
            flags.append("INSUFFICIENT_BOARDER_HISTORY")
        if monthly_boarder > qualifying_monthly:
            flags.append("BOARDER_INCOME_CAPPED_AT_30PCT")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = history_months >= 12 and annual_amount > ZERO

        return ValidationResult(
            income_type=NonTraditionalIncomeType.BOARDER,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NOT_QUALIFYING
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=ContinuanceRisk.MODERATE,
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                "Boarder income is limited to 30% of housing payment offset.",
                "Obtain signed boarder agreement and 12 months of payment proof.",
            ] if not is_valid else [],
        )

    async def _validate_foster_care(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate foster care income (tax-exempt, can be grossed up)."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        history_months = doc.get("history_months", 0)
        docs_provided = doc.get("documents_provided", [])

        # Foster care income is tax-exempt; gross up by 25%
        grossed_up_annual = (annual_amount * FOSTER_CARE_GROSSUP_FACTOR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )
        qualifying_monthly = (grossed_up_annual / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        required_docs = [
            "State/agency foster care payment documentation",
            "Letter from agency confirming placement",
            "12 months payment history",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        issues = []
        flags = ["TAX_EXEMPT_GROSSED_UP_25PCT"]
        if history_months < 12:
            issues.append(
                f"Only {history_months} months of foster care history; "
                f"12 months required for continuance."
            )
            flags.append("INSUFFICIENT_FOSTER_HISTORY")

        doc_completeness = (
            DocumentationCompleteness.COMPLETE if not missing
            else DocumentationCompleteness.PARTIALLY_COMPLETE if len(missing) < len(required_docs)
            else DocumentationCompleteness.INSUFFICIENT
        )

        is_valid = history_months >= 12 and annual_amount > ZERO

        return ValidationResult(
            income_type=NonTraditionalIncomeType.FOSTER_CARE,
            is_valid=is_valid,
            qualifying_status=(
                QualifyingStatus.QUALIFYING if is_valid and not missing
                else QualifyingStatus.QUALIFYING_WITH_CONDITIONS if is_valid
                else QualifyingStatus.NEEDS_REVIEW
            ),
            documentation_completeness=doc_completeness,
            qualifying_monthly_income=qualifying_monthly if is_valid else ZERO,
            continuance_risk=ContinuanceRisk.MODERATE,
            missing_documents=missing,
            issues=issues,
            flags=flags,
            recommendations=[
                "Foster care income grossed up 25% (tax-exempt income).",
                "Verify continuance with foster care agency letter.",
            ] if not is_valid else [
                "Foster care income grossed up 25% (tax-exempt income).",
            ],
        )

    async def _validate_non_borrower(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate non-borrower household income (compensating factor only)."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        docs_provided = doc.get("documents_provided", [])

        required_docs = [
            "Non-borrower income documentation (paystubs, W-2)",
            "Proof of shared household (lease, utility bills)",
        ]
        missing = [d for d in required_docs if d not in docs_provided]

        # Non-borrower income is NOT qualifying; shown as $0
        return ValidationResult(
            income_type=NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD,
            is_valid=True,
            qualifying_status=QualifyingStatus.COMPENSATING_FACTOR_ONLY,
            documentation_completeness=(
                DocumentationCompleteness.COMPLETE if not missing
                else DocumentationCompleteness.PARTIALLY_COMPLETE
            ),
            qualifying_monthly_income=ZERO,
            continuance_risk=ContinuanceRisk.LOW,
            missing_documents=missing,
            issues=[
                "Non-borrower household income is a compensating factor only "
                "and cannot be used for DTI calculation."
            ],
            flags=["NON_BORROWER_COMPENSATING_FACTOR_ONLY"],
            recommendations=[
                "Document non-borrower income for compensating factor presentation.",
                f"Non-borrower contributes ${annual_amount:,.2f}/year to household.",
            ],
        )

    async def _validate_cryptocurrency(self, doc: Dict[str, Any]) -> ValidationResult:
        """Validate cryptocurrency income (generally not acceptable)."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))

        return ValidationResult(
            income_type=NonTraditionalIncomeType.CRYPTOCURRENCY,
            is_valid=False,
            qualifying_status=QualifyingStatus.NOT_QUALIFYING,
            documentation_completeness=DocumentationCompleteness.NOT_PROVIDED,
            qualifying_monthly_income=ZERO,
            continuance_risk=ContinuanceRisk.UNACCEPTABLE,
            missing_documents=[],
            issues=[
                "Cryptocurrency income is not acceptable as qualifying income. "
                "It is too volatile and speculative for mortgage qualification."
            ],
            flags=["CRYPTOCURRENCY_NOT_QUALIFYING"],
            recommendations=[
                "If borrower has 2+ years of consistent crypto trading gains, "
                "evaluate under capital gains guidelines (Schedule D).",
                "Document crypto holdings as assets, not income.",
            ],
        )

    async def _validate_generic(self, doc: Dict[str, Any]) -> ValidationResult:
        """Fallback validation for unclassified income types."""
        annual_amount = self._to_decimal(doc.get("annual_amount", 0))
        return ValidationResult(
            income_type=NonTraditionalIncomeType.UNCLASSIFIED,
            is_valid=False,
            qualifying_status=QualifyingStatus.NEEDS_REVIEW,
            documentation_completeness=DocumentationCompleteness.NOT_PROVIDED,
            qualifying_monthly_income=ZERO,
            continuance_risk=ContinuanceRisk.HIGH,
            missing_documents=["Manual review required — documentation needs TBD"],
            issues=["Income type could not be automatically classified."],
            flags=["UNCLASSIFIED_MANUAL_REVIEW_REQUIRED"],
            recommendations=[
                "Submit to underwriter for manual income classification and "
                "documentation requirements determination."
            ],
        )

    # =========================================================================
    # PRIVATE: Documentation requirements
    # =========================================================================

    def _get_doc_requirements_for_type(
        self,
        income_type: NonTraditionalIncomeType,
    ) -> List[DocRequirement]:
        """Return documentation requirements for a given income type."""

        requirements_map: Dict[NonTraditionalIncomeType, List[DocRequirement]] = {
            # --- Gig income types share the same requirements ---
            **{
                gig_type: [
                    DocRequirement(
                        document_type="1099-K / 1099-NEC",
                        description="Platform-issued tax forms showing gross payments",
                        required=True,
                        years_required=2,
                        notes="1099-K for payment card/third-party network transactions; 1099-NEC for direct payments",
                    ),
                    DocRequirement(
                        document_type="Schedule C (Form 1040)",
                        description="Profit or Loss from Business showing net income after expenses",
                        required=True,
                        years_required=2,
                    ),
                    DocRequirement(
                        document_type="Schedule SE",
                        description="Self-Employment Tax form",
                        required=True,
                        years_required=2,
                    ),
                    DocRequirement(
                        document_type="Tax Returns (Form 1040)",
                        description="Complete personal tax returns with all schedules",
                        required=True,
                        years_required=2,
                    ),
                    DocRequirement(
                        document_type="Profit & Loss Statement",
                        description="Year-to-date P&L if more than 3 months since last tax filing",
                        required=False,
                        years_required=1,
                        notes="Required if YTD period exceeds calendar quarter boundary",
                    ),
                    DocRequirement(
                        document_type="Bank Statements",
                        description="Business or personal bank statements showing platform deposits",
                        required=False,
                        years_required=1,
                        notes="Helpful for cross-referencing platform income",
                    ),
                ]
                for gig_type in [
                    NonTraditionalIncomeType.GIG_RIDESHARE,
                    NonTraditionalIncomeType.GIG_DELIVERY,
                    NonTraditionalIncomeType.GIG_FREELANCE,
                    NonTraditionalIncomeType.GIG_MARKETPLACE,
                    NonTraditionalIncomeType.GIG_RENTAL_PLATFORM,
                    NonTraditionalIncomeType.GIG_TASK,
                    NonTraditionalIncomeType.GIG_OTHER,
                ]
            },

            NonTraditionalIncomeType.SEASONAL: [
                DocRequirement(
                    document_type="W-2",
                    description="Wage and Tax Statements from seasonal employer",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Tax Returns (Form 1040)",
                    description="Complete personal tax returns",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Employer Verification Letter",
                    description="Letter from employer confirming seasonal nature and rehire expectation",
                    required=True,
                    years_required=1,
                    notes="Must confirm borrower is expected to return next season",
                ),
                DocRequirement(
                    document_type="1099-G",
                    description="Unemployment compensation statement (if claiming off-season income)",
                    required=False,
                    years_required=2,
                    notes="Required only if including unemployment compensation in qualifying income",
                ),
            ],

            NonTraditionalIncomeType.FOREIGN: [
                DocRequirement(
                    document_type="Employment Contract",
                    description="Current employment contract showing terms, compensation, and duration",
                    required=True,
                    years_required=1,
                    notes="Must show at least 3 years remaining or evidence of renewal",
                ),
                DocRequirement(
                    document_type="Tax Returns (Form 1040)",
                    description="U.S. tax returns or foreign equivalent",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Form 2555",
                    description="Foreign Earned Income Exclusion form",
                    required=True,
                    years_required=2,
                    notes="Determines amount of excluded foreign income",
                    alternative_docs=["Form 1116 (Foreign Tax Credit)"],
                ),
                DocRequirement(
                    document_type="Currency Conversion Documentation",
                    description="Official exchange rate documentation at time of conversion",
                    required=True,
                    years_required=1,
                ),
                DocRequirement(
                    document_type="Employer Verification",
                    description="VOE or equivalent from foreign employer",
                    required=True,
                    years_required=1,
                ),
            ],

            NonTraditionalIncomeType.TRUST: [
                DocRequirement(
                    document_type="Trust Agreement",
                    description="Complete trust document showing terms, beneficiaries, and distribution schedule",
                    required=True,
                    years_required=1,
                    notes="Must confirm trust is irrevocable",
                ),
                DocRequirement(
                    document_type="K-1 (Form 1041)",
                    description="Beneficiary's Share of Income from trust",
                    required=True,
                    years_required=3,
                ),
                DocRequirement(
                    document_type="Trust Distribution Statements",
                    description="Records of actual distributions received",
                    required=True,
                    years_required=3,
                ),
                DocRequirement(
                    document_type="CPA / Attorney Letter",
                    description="Letter confirming distribution amounts and continuance expectation",
                    required=False,
                    years_required=1,
                    notes="Strengthens file; confirms 3-year continuance",
                ),
            ],

            NonTraditionalIncomeType.NOTES_RECEIVABLE: [
                DocRequirement(
                    document_type="Promissory Note / Loan Agreement",
                    description="Original note showing terms, interest rate, payment schedule, and maturity date",
                    required=True,
                    years_required=1,
                    notes="Remaining term must cover 3+ years from closing",
                ),
                DocRequirement(
                    document_type="Payment History (Bank Statements)",
                    description="12 months of cancelled checks or bank statements showing receipt of payments",
                    required=True,
                    years_required=1,
                    notes="Minimum 12 months of consistent receipt required",
                ),
                DocRequirement(
                    document_type="Amortization Schedule",
                    description="Payment schedule showing remaining balance and term",
                    required=True,
                    years_required=1,
                ),
            ],

            NonTraditionalIncomeType.ROYALTY: [
                DocRequirement(
                    document_type="Schedule E Part I",
                    description="Supplemental Income from royalties",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Royalty Agreement / Contract",
                    description="Original contract showing royalty terms and duration",
                    required=True,
                    years_required=1,
                ),
                DocRequirement(
                    document_type="1099-MISC",
                    description="Miscellaneous Income showing royalty payments",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Tax Returns (Form 1040)",
                    description="Complete returns with Schedule E",
                    required=True,
                    years_required=2,
                ),
            ],

            NonTraditionalIncomeType.CAPITAL_GAINS: [
                DocRequirement(
                    document_type="Schedule D",
                    description="Capital Gains and Losses summary",
                    required=True,
                    years_required=2,
                    notes="Generally NOT qualifying; exception for documented day traders",
                ),
                DocRequirement(
                    document_type="Form 8949",
                    description="Sales and Dispositions of Capital Assets detail",
                    required=True,
                    years_required=2,
                ),
                DocRequirement(
                    document_type="Brokerage Statements",
                    description="24 months of brokerage account statements",
                    required=True,
                    years_required=2,
                    notes="Required for day trader exception evaluation",
                ),
                DocRequirement(
                    document_type="1099-B",
                    description="Proceeds from Broker and Barter Exchange Transactions",
                    required=True,
                    years_required=2,
                ),
            ],

            NonTraditionalIncomeType.BOARDER: [
                DocRequirement(
                    document_type="Boarder Agreement",
                    description="Signed rental/boarder agreement for room in primary residence",
                    required=True,
                    years_required=1,
                ),
                DocRequirement(
                    document_type="Payment Documentation",
                    description="12 months of cancelled checks, bank deposits, or payment receipts",
                    required=True,
                    years_required=1,
                    notes="Must show consistent monthly payments",
                ),
                DocRequirement(
                    document_type="Shared Living Proof",
                    description="Evidence borrower and boarder share primary residence",
                    required=True,
                    years_required=1,
                    notes="Utility bills, lease showing both names, etc.",
                ),
            ],

            NonTraditionalIncomeType.FOSTER_CARE: [
                DocRequirement(
                    document_type="Foster Care Payment Documentation",
                    description="State or agency payment records showing foster care compensation",
                    required=True,
                    years_required=1,
                    notes="Tax-exempt income; eligible for 25% gross-up",
                ),
                DocRequirement(
                    document_type="Agency Placement Letter",
                    description="Letter from fostering agency confirming active placement(s)",
                    required=True,
                    years_required=1,
                    notes="Must confirm continuance expectation",
                ),
                DocRequirement(
                    document_type="12-Month Payment History",
                    description="Bank statements or agency records showing 12 months of payments",
                    required=True,
                    years_required=1,
                ),
            ],

            NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD: [
                DocRequirement(
                    document_type="Non-Borrower Income Documentation",
                    description="Paystubs, W-2, or tax returns for household member",
                    required=True,
                    years_required=1,
                    notes="Used as compensating factor only; not for DTI calculation",
                ),
                DocRequirement(
                    document_type="Proof of Shared Household",
                    description="Lease, utility bills, or other proof of shared residence",
                    required=True,
                    years_required=1,
                ),
            ],

            NonTraditionalIncomeType.CRYPTOCURRENCY: [
                DocRequirement(
                    document_type="Exchange Account Statements",
                    description="Trading history from cryptocurrency exchange(s)",
                    required=False,
                    years_required=2,
                    notes="Cryptocurrency income is generally NOT qualifying; document for awareness only",
                ),
                DocRequirement(
                    document_type="Schedule D / Form 8949",
                    description="Capital gains reporting if realized gains pattern exists",
                    required=False,
                    years_required=2,
                    notes="Only relevant if evaluating under capital gains exception",
                    alternative_docs=["1099-B from exchange"],
                ),
            ],
        }

        return requirements_map.get(income_type, [])

    # =========================================================================
    # PRIVATE: Calculation helpers
    # =========================================================================

    def _analyze_trend(
        self,
        year1: Decimal,
        year2: Decimal,
        year3: Optional[Decimal] = None,
    ) -> TrendAnalysis:
        """Analyze year-over-year income trending."""
        yoy_change: Optional[Decimal] = None
        use_lower = False

        if year2 > ZERO:
            yoy_change = ((year1 - year2) / year2 * 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

        two_year_avg = ((year1 + year2) / 2).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        three_year_avg: Optional[Decimal] = None
        if year3 is not None and year3 > ZERO:
            three_year_avg = ((year1 + year2 + year3) / 3).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

        # Determine direction
        if yoy_change is None:
            direction = "variable"
        elif yoy_change < -DECLINING_WARN_PCT:
            direction = "declining"
            use_lower = True  # Use most recent (lower) year
        elif yoy_change > DECLINING_WARN_PCT:
            direction = "increasing"
        else:
            direction = "stable"

        return TrendAnalysis(
            year1_amount=year1,
            year2_amount=year2,
            year3_amount=year3,
            yoy_change_pct=yoy_change,
            two_year_avg=two_year_avg,
            three_year_avg=three_year_avg,
            direction=direction,
            use_lower_year=use_lower,
        )

    def _compute_confidence(
        self,
        has_docs: bool,
        history_years: int,
        min_years: int,
        trend_direction: str,
    ) -> int:
        """Compute confidence score (0-100) for an income calculation."""
        score = 50  # Base

        # Documentation
        if has_docs:
            score += 20
        else:
            score -= 10

        # History
        if history_years >= min_years:
            score += 15
            if history_years >= min_years + 1:
                score += 5  # Bonus for extra history
        else:
            score -= 20

        # Trend
        if trend_direction == "stable":
            score += 10
        elif trend_direction == "increasing":
            score += 10
        elif trend_direction == "declining":
            score -= 10
        elif trend_direction == "variable":
            score -= 5

        return max(0, min(100, score))

    def _get_required_history_years(self, income_type: NonTraditionalIncomeType) -> int:
        """Return the minimum history years required for a given income type."""
        type_years = {
            NonTraditionalIncomeType.TRUST: MIN_HISTORY_YEARS_TRUST,
            NonTraditionalIncomeType.NOTES_RECEIVABLE: MIN_HISTORY_YEARS_NOTES_RECEIVABLE,
            NonTraditionalIncomeType.BOARDER: MIN_HISTORY_YEARS_BOARDER,
            NonTraditionalIncomeType.FOSTER_CARE: MIN_HISTORY_YEARS_FOSTER,
            NonTraditionalIncomeType.CAPITAL_GAINS: MIN_HISTORY_YEARS_CAPITAL_GAINS_DAY_TRADER,
        }
        return type_years.get(income_type, 2)  # Default: 2 years

    def _assess_continuance_risk(
        self,
        income_type: NonTraditionalIncomeType,
        meets_minimum: bool,
        remaining_months: Optional[int],
        has_continuance_letter: bool,
        has_contract: bool,
        flags: List[str],
    ) -> ContinuanceRisk:
        """Determine continuance risk level."""
        # Cryptocurrency and capital gains are inherently high risk
        if income_type in (
            NonTraditionalIncomeType.CRYPTOCURRENCY,
            NonTraditionalIncomeType.CAPITAL_GAINS,
        ):
            return ContinuanceRisk.UNACCEPTABLE if income_type == NonTraditionalIncomeType.CRYPTOCURRENCY else ContinuanceRisk.HIGH

        # Non-borrower: N/A for qualifying, so low risk for its purpose
        if income_type == NonTraditionalIncomeType.NON_BORROWER_HOUSEHOLD:
            return ContinuanceRisk.LOW

        # Check for severe red flags
        if "SEVERE_DECLINING_TREND" in flags:
            return ContinuanceRisk.HIGH
        if "TRUST_NOT_CONFIRMED_IRREVOCABLE" in flags:
            return ContinuanceRisk.UNACCEPTABLE

        # Remaining term check
        if remaining_months is not None and remaining_months < 36:
            return ContinuanceRisk.HIGH

        if not meets_minimum:
            return ContinuanceRisk.HIGH

        # Positive factors
        positive_factors = sum([
            has_continuance_letter,
            has_contract,
            meets_minimum,
            "DECLINING_TREND" not in flags,
        ])

        if positive_factors >= 3:
            return ContinuanceRisk.LOW
        elif positive_factors >= 2:
            return ContinuanceRisk.MODERATE
        else:
            return ContinuanceRisk.HIGH

    def _verify_org(self, org_id: int) -> None:
        """Verify the org_id matches the service's configured org_id."""
        if org_id != self.org_id:
            raise ValueError(
                f"Organization mismatch: service configured for org {self.org_id}, "
                f"but request is for org {org_id}"
            )

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        """Safely convert a value to Decimal."""
        if value is None:
            return ZERO
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return ZERO


# =============================================================================
# Factory function
# =============================================================================

def get_non_traditional_income_service(
    db: Session,
    org_id: int,
) -> NonTraditionalIncomeService:
    """
    Factory function to create a NonTraditionalIncomeService instance.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.

    Returns:
        Configured NonTraditionalIncomeService.
    """
    return NonTraditionalIncomeService(db=db, org_id=org_id)
