"""
Commission Income Calculation Service for Mortgage Qualification

Calculates qualifying commission-based income per Fannie Mae Selling Guide
(Chapter B3-3.1) and Freddie Mac guidelines. Handles the full complexity of
commission income analysis including:

    - 2-year history requirement with 1-year exception for stable/increasing
    - Multiple calculation methods (simple average, weighted, YTD annualization)
    - Year-over-year trending with declining income rules
    - Base salary vs. commission component separation
    - Unreimbursed business expense deductions (Form 2106)
    - Commission-to-total-income ratio threshold (25%)
    - Employment continuity and employer consistency validation
    - Multiple commission sources aggregation
    - Override capability with audit trail

Data sources:
    - W-2 Box 1 (wages, tips, other compensation)
    - Tax return Schedule C (self-employed commission agents)
    - 1099-NEC/MISC (independent contractor commission)
    - Paystubs (YTD commission breakdown)
    - VOE (Verification of Employment) data

Integrates with:
    - smart_documents / smart_document_extractions for document data
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items

Usage:
    from services.smart_docs.income.commission_income_service import (
        get_commission_income_service,
        CommissionIncomeService,
    )

    service = get_commission_income_service(db, org_id=42)
    result = await service.calculate_commission_income(
        loan_id=100, borrower_id=7, documents=docs,
    )
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
ONE_HUNDRED = Decimal("100")

# --- Agency guideline thresholds ---

# Commission is "significant" if >= 25% of total gross income (Fannie Mae B3-3.1)
COMMISSION_SIGNIFICANCE_THRESHOLD_PCT = Decimal("25")

# 2-year history required when commission >= 25% of total income
HISTORY_YEARS_REQUIRED = 2

# Can use 1-year history if income is stable or increasing AND >= 12 months on job
HISTORY_YEARS_MINIMUM = 1

# Decline thresholds
DECLINE_WARNING_PCT = Decimal("10")      # Flag for LO review
DECLINE_CRITICAL_PCT = Decimal("20")     # Use lower year / most-recent-12-months
DECLINE_SEVERE_PCT = Decimal("25")       # May need to exclude commission entirely

# Employment gap threshold in days
EMPLOYMENT_GAP_THRESHOLD_DAYS = 180

# Unreimbursed business expense threshold (% of gross commission)
UBE_DEDUCTION_THRESHOLD_PCT = Decimal("25")

# Pay-frequency annualization multipliers
PAY_FREQUENCY_MULTIPLIERS: Dict[str, int] = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

# Document types relevant to commission income analysis
COMMISSION_DOC_TYPES = (
    "PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN",
    "1099_NEC", "1099_MISC", "VOE",
)

# Months in a calendar year
MONTHS_PER_YEAR = Decimal("12")
MONTHS_PER_TWO_YEARS = Decimal("24")


# =============================================================================
# ENUMS
# =============================================================================

class CalculationMethod(str, Enum):
    """Method used to calculate qualifying commission income."""
    SIMPLE_AVERAGE = "simple_average"           # (Year1 + Year2) / 24
    WEIGHTED_AVERAGE = "weighted_average"       # Recent year weighted higher
    YTD_ANNUALIZED = "ytd_annualized"           # Current YTD projected to full year
    MOST_RECENT_12_MONTHS = "most_recent_12"    # Declining income: last 12 months only
    SINGLE_YEAR = "single_year"                 # 1-year history (stable/increasing exception)
    OVERRIDE = "override"                       # Manual override with justification


class CommissionType(str, Enum):
    """Type of commission arrangement."""
    W2_COMMISSION = "w2_commission"             # W-2 employee earning commission
    INDEPENDENT_1099 = "independent_1099"       # 1099 independent contractor
    SCHEDULE_C = "schedule_c"                   # Self-employed commission (Schedule C)
    MIXED = "mixed"                             # Multiple commission types


class TrendDirection(str, Enum):
    """Income trend direction."""
    INCREASING = "increasing"
    STABLE = "stable"
    DECLINING = "declining"
    VARIABLE = "variable"
    INSUFFICIENT_DATA = "insufficient_data"


# =============================================================================
# DATA CLASSES
# =============================================================================

class TrendAnalysis:
    """Year-over-year income trend analysis result."""

    __slots__ = (
        "direction", "year1_amount", "year2_amount", "ytd_amount",
        "ytd_annualized", "yoy_change_pct", "ytd_vs_prior_pct",
        "is_stable_or_increasing", "months_of_data", "notes",
    )

    def __init__(
        self,
        direction: TrendDirection,
        year1_amount: Decimal,
        year2_amount: Optional[Decimal],
        ytd_amount: Optional[Decimal] = None,
        ytd_annualized: Optional[Decimal] = None,
        yoy_change_pct: Optional[Decimal] = None,
        ytd_vs_prior_pct: Optional[Decimal] = None,
        is_stable_or_increasing: bool = False,
        months_of_data: int = 0,
        notes: str = "",
    ):
        self.direction = direction
        self.year1_amount = year1_amount
        self.year2_amount = year2_amount
        self.ytd_amount = ytd_amount
        self.ytd_annualized = ytd_annualized
        self.yoy_change_pct = yoy_change_pct
        self.ytd_vs_prior_pct = ytd_vs_prior_pct
        self.is_stable_or_increasing = is_stable_or_increasing
        self.months_of_data = months_of_data
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "year1_amount": float(self.year1_amount),
            "year2_amount": float(self.year2_amount) if self.year2_amount is not None else None,
            "ytd_amount": float(self.ytd_amount) if self.ytd_amount is not None else None,
            "ytd_annualized": float(self.ytd_annualized) if self.ytd_annualized is not None else None,
            "yoy_change_pct": float(self.yoy_change_pct) if self.yoy_change_pct is not None else None,
            "ytd_vs_prior_pct": float(self.ytd_vs_prior_pct) if self.ytd_vs_prior_pct is not None else None,
            "is_stable_or_increasing": self.is_stable_or_increasing,
            "months_of_data": self.months_of_data,
            "notes": self.notes,
        }


class ExpenseAnalysis:
    """Unreimbursed business expense (Form 2106) analysis result."""

    __slots__ = (
        "gross_commission", "total_expenses", "expense_ratio_pct",
        "exceeds_threshold", "deduction_amount", "expense_categories",
        "tax_years_analyzed", "notes",
    )

    def __init__(
        self,
        gross_commission: Decimal,
        total_expenses: Decimal,
        expense_ratio_pct: Decimal,
        exceeds_threshold: bool,
        deduction_amount: Decimal,
        expense_categories: Optional[Dict[str, Decimal]] = None,
        tax_years_analyzed: Optional[List[int]] = None,
        notes: str = "",
    ):
        self.gross_commission = gross_commission
        self.total_expenses = total_expenses
        self.expense_ratio_pct = expense_ratio_pct
        self.exceeds_threshold = exceeds_threshold
        self.deduction_amount = deduction_amount
        self.expense_categories = expense_categories or {}
        self.tax_years_analyzed = tax_years_analyzed or []
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gross_commission": float(self.gross_commission),
            "total_expenses": float(self.total_expenses),
            "expense_ratio_pct": float(self.expense_ratio_pct),
            "exceeds_threshold": self.exceeds_threshold,
            "deduction_amount": float(self.deduction_amount),
            "expense_categories": {k: float(v) for k, v in self.expense_categories.items()},
            "tax_years_analyzed": self.tax_years_analyzed,
            "notes": self.notes,
        }


class EligibilityResult:
    """Commission income eligibility determination result."""

    __slots__ = (
        "is_eligible", "requires_two_year_history", "has_sufficient_history",
        "commission_pct_of_total", "employment_months", "employer_consistent",
        "has_employment_gap", "gap_days", "can_use_one_year_exception",
        "disqualifying_reasons", "warnings", "notes",
    )

    def __init__(
        self,
        is_eligible: bool,
        requires_two_year_history: bool,
        has_sufficient_history: bool,
        commission_pct_of_total: Decimal,
        employment_months: int,
        employer_consistent: bool,
        has_employment_gap: bool,
        gap_days: int = 0,
        can_use_one_year_exception: bool = False,
        disqualifying_reasons: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        notes: str = "",
    ):
        self.is_eligible = is_eligible
        self.requires_two_year_history = requires_two_year_history
        self.has_sufficient_history = has_sufficient_history
        self.commission_pct_of_total = commission_pct_of_total
        self.employment_months = employment_months
        self.employer_consistent = employer_consistent
        self.has_employment_gap = has_employment_gap
        self.gap_days = gap_days
        self.can_use_one_year_exception = can_use_one_year_exception
        self.disqualifying_reasons = disqualifying_reasons or []
        self.warnings = warnings or []
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_eligible": self.is_eligible,
            "requires_two_year_history": self.requires_two_year_history,
            "has_sufficient_history": self.has_sufficient_history,
            "commission_pct_of_total": float(self.commission_pct_of_total),
            "employment_months": self.employment_months,
            "employer_consistent": self.employer_consistent,
            "has_employment_gap": self.has_employment_gap,
            "gap_days": self.gap_days,
            "can_use_one_year_exception": self.can_use_one_year_exception,
            "disqualifying_reasons": self.disqualifying_reasons,
            "warnings": self.warnings,
            "notes": self.notes,
        }


class CommissionSource:
    """A single source of commission income with full breakdown."""

    __slots__ = (
        "source_id", "commission_type", "employer_name", "employer_ein",
        "position_title", "start_date", "years_in_role",
        "year1_commission", "year1_base_salary", "year1_total_w2",
        "year1_tax_year",
        "year2_commission", "year2_base_salary", "year2_total_w2",
        "year2_tax_year",
        "ytd_commission", "ytd_base_salary", "ytd_total_gross",
        "ytd_months_elapsed",
        "qualifying_monthly_commission", "qualifying_monthly_base",
        "qualifying_monthly_total",
        "calculation_method", "trend_analysis", "expense_analysis",
        "source_doc_ids", "confidence", "flags", "notes",
    )

    def __init__(
        self,
        source_id: str,
        commission_type: CommissionType,
        employer_name: Optional[str] = None,
        employer_ein: Optional[str] = None,
        position_title: Optional[str] = None,
        start_date: Optional[date] = None,
        years_in_role: Optional[Decimal] = None,
        year1_commission: Decimal = ZERO,
        year1_base_salary: Decimal = ZERO,
        year1_total_w2: Decimal = ZERO,
        year1_tax_year: Optional[int] = None,
        year2_commission: Decimal = ZERO,
        year2_base_salary: Decimal = ZERO,
        year2_total_w2: Decimal = ZERO,
        year2_tax_year: Optional[int] = None,
        ytd_commission: Decimal = ZERO,
        ytd_base_salary: Decimal = ZERO,
        ytd_total_gross: Decimal = ZERO,
        ytd_months_elapsed: int = 0,
        qualifying_monthly_commission: Decimal = ZERO,
        qualifying_monthly_base: Decimal = ZERO,
        qualifying_monthly_total: Decimal = ZERO,
        calculation_method: CalculationMethod = CalculationMethod.SIMPLE_AVERAGE,
        trend_analysis: Optional[TrendAnalysis] = None,
        expense_analysis: Optional[ExpenseAnalysis] = None,
        source_doc_ids: Optional[List[int]] = None,
        confidence: int = 0,
        flags: Optional[List[str]] = None,
        notes: str = "",
    ):
        self.source_id = source_id
        self.commission_type = commission_type
        self.employer_name = employer_name
        self.employer_ein = employer_ein
        self.position_title = position_title
        self.start_date = start_date
        self.years_in_role = years_in_role
        self.year1_commission = year1_commission
        self.year1_base_salary = year1_base_salary
        self.year1_total_w2 = year1_total_w2
        self.year1_tax_year = year1_tax_year
        self.year2_commission = year2_commission
        self.year2_base_salary = year2_base_salary
        self.year2_total_w2 = year2_total_w2
        self.year2_tax_year = year2_tax_year
        self.ytd_commission = ytd_commission
        self.ytd_base_salary = ytd_base_salary
        self.ytd_total_gross = ytd_total_gross
        self.ytd_months_elapsed = ytd_months_elapsed
        self.qualifying_monthly_commission = qualifying_monthly_commission
        self.qualifying_monthly_base = qualifying_monthly_base
        self.qualifying_monthly_total = qualifying_monthly_total
        self.calculation_method = calculation_method
        self.trend_analysis = trend_analysis
        self.expense_analysis = expense_analysis
        self.source_doc_ids = source_doc_ids or []
        self.confidence = confidence
        self.flags = flags or []
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "commission_type": self.commission_type.value,
            "employer_name": self.employer_name,
            "employer_ein": self.employer_ein,
            "position_title": self.position_title,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "years_in_role": float(self.years_in_role) if self.years_in_role else None,
            "year1": {
                "tax_year": self.year1_tax_year,
                "commission": float(self.year1_commission),
                "base_salary": float(self.year1_base_salary),
                "total_w2": float(self.year1_total_w2),
            },
            "year2": {
                "tax_year": self.year2_tax_year,
                "commission": float(self.year2_commission),
                "base_salary": float(self.year2_base_salary),
                "total_w2": float(self.year2_total_w2),
            },
            "ytd": {
                "commission": float(self.ytd_commission),
                "base_salary": float(self.ytd_base_salary),
                "total_gross": float(self.ytd_total_gross),
                "months_elapsed": self.ytd_months_elapsed,
            },
            "qualifying": {
                "monthly_commission": float(self.qualifying_monthly_commission),
                "monthly_base": float(self.qualifying_monthly_base),
                "monthly_total": float(self.qualifying_monthly_total),
                "annual_total": float(self.qualifying_monthly_total * MONTHS_PER_YEAR),
            },
            "calculation_method": self.calculation_method.value,
            "trend_analysis": self.trend_analysis.to_dict() if self.trend_analysis else None,
            "expense_analysis": self.expense_analysis.to_dict() if self.expense_analysis else None,
            "source_doc_ids": self.source_doc_ids,
            "confidence": self.confidence,
            "flags": self.flags,
            "notes": self.notes,
        }


class CommissionIncomeResult:
    """Complete commission income calculation result across all sources."""

    __slots__ = (
        "loan_id", "borrower_id", "org_id", "calculation_id",
        "sources", "eligibility",
        "total_qualifying_monthly_commission", "total_qualifying_monthly_base",
        "total_qualifying_monthly", "total_qualifying_annual",
        "commission_pct_of_total_income",
        "primary_calculation_method",
        "overall_trend", "confidence",
        "flags", "recommendations", "tasks_to_create",
        "audit_trail", "override_applied",
        "success", "error", "calculated_at", "duration_ms",
    )

    def __init__(
        self,
        loan_id: int,
        borrower_id: int,
        org_id: int,
        calculation_id: Optional[str] = None,
        sources: Optional[List[CommissionSource]] = None,
        eligibility: Optional[EligibilityResult] = None,
        total_qualifying_monthly_commission: Decimal = ZERO,
        total_qualifying_monthly_base: Decimal = ZERO,
        total_qualifying_monthly: Decimal = ZERO,
        total_qualifying_annual: Decimal = ZERO,
        commission_pct_of_total_income: Decimal = ZERO,
        primary_calculation_method: CalculationMethod = CalculationMethod.SIMPLE_AVERAGE,
        overall_trend: TrendDirection = TrendDirection.INSUFFICIENT_DATA,
        confidence: int = 0,
        flags: Optional[List[str]] = None,
        recommendations: Optional[List[str]] = None,
        tasks_to_create: Optional[List[Dict[str, Any]]] = None,
        audit_trail: Optional[List[Dict[str, Any]]] = None,
        override_applied: bool = False,
        success: bool = True,
        error: Optional[str] = None,
        calculated_at: Optional[datetime] = None,
        duration_ms: int = 0,
    ):
        self.loan_id = loan_id
        self.borrower_id = borrower_id
        self.org_id = org_id
        self.calculation_id = calculation_id or str(uuid.uuid4())
        self.sources = sources or []
        self.eligibility = eligibility
        self.total_qualifying_monthly_commission = total_qualifying_monthly_commission
        self.total_qualifying_monthly_base = total_qualifying_monthly_base
        self.total_qualifying_monthly = total_qualifying_monthly
        self.total_qualifying_annual = total_qualifying_annual
        self.commission_pct_of_total_income = commission_pct_of_total_income
        self.primary_calculation_method = primary_calculation_method
        self.overall_trend = overall_trend
        self.confidence = confidence
        self.flags = flags or []
        self.recommendations = recommendations or []
        self.tasks_to_create = tasks_to_create or []
        self.audit_trail = audit_trail or []
        self.override_applied = override_applied
        self.success = success
        self.error = error
        self.calculated_at = calculated_at or datetime.now(timezone.utc)
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "borrower_id": self.borrower_id,
            "org_id": self.org_id,
            "calculation_id": self.calculation_id,
            "sources": [s.to_dict() for s in self.sources],
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "qualifying_income": {
                "monthly_commission": float(self.total_qualifying_monthly_commission),
                "monthly_base": float(self.total_qualifying_monthly_base),
                "monthly_total": float(self.total_qualifying_monthly),
                "annual_total": float(self.total_qualifying_annual),
            },
            "commission_pct_of_total_income": float(self.commission_pct_of_total_income),
            "primary_calculation_method": self.primary_calculation_method.value,
            "overall_trend": self.overall_trend.value,
            "confidence": self.confidence,
            "flags": self.flags,
            "recommendations": self.recommendations,
            "tasks_to_create": self.tasks_to_create,
            "audit_trail": self.audit_trail,
            "override_applied": self.override_applied,
            "success": self.success,
            "error": self.error,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
            "duration_ms": self.duration_ms,
        }


# =============================================================================
# SERVICE
# =============================================================================

# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================

def _to_decimal(value: Any) -> Decimal:
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


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    """Parse a date from string or date object."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _months_elapsed_in_year(pay_date_str: Optional[str]) -> Optional[int]:
    """
    Given a pay_date string (YYYY-MM-DD), return the number of months
    elapsed from Jan 1 of that year to the pay date (minimum 1).
    """
    if not pay_date_str:
        return None
    try:
        pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
        days = (pay_date - date(pay_date.year, 1, 1)).days + 1
        months = max(1, round(days / 30.44))
        return months
    except (ValueError, TypeError):
        return None


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


def _audit(
    trail: List[Dict[str, Any]],
    event: str,
    data: Dict[str, Any],
) -> None:
    """Append an entry to the audit trail."""
    trail.append({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    })

