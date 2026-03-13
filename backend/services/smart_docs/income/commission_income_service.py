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

class CommissionIncomeService:
    """
    Commission income calculation service for mortgage qualification.

    Implements Fannie Mae Selling Guide B3-3.1 and Freddie Mac requirements
    for commission-based income analysis. Handles W-2 commission earners,
    1099 independent contractors, and Schedule C self-employed agents.

    Key guideline points implemented:
    - Commission > 25% of total income requires 2-year history
    - 1-year exception allowed if stable/increasing and same employer >= 12 months
    - Declining income: use lower of 2-year average or most recent 12 months
    - Unreimbursed business expenses > 25% of income must be deducted
    - Employment gaps > 6 months require additional documentation

    All monetary calculations use Decimal arithmetic to avoid floating-point
    rounding errors in financial computations.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def calculate_commission_income(
        self,
        loan_id: int,
        borrower_id: int,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> CommissionIncomeResult:
        """
        Calculate qualifying commission income for a borrower.

        Gathers commission-related documents (or uses provided documents),
        groups them by employer/source, calculates per-source qualifying
        income, runs eligibility checks, and persists the result.

        Args:
            loan_id: The loan ID this calculation is for.
            borrower_id: The borrower whose income is being calculated.
            documents: Optional pre-gathered documents. If None, queries
                smart_documents for commission-related docs.

        Returns:
            CommissionIncomeResult with full calculation breakdown.
        """
        start_ms = _now_ms()
        audit_trail: List[Dict[str, Any]] = []
        _audit(audit_trail, "calculation_started", {
            "loan_id": loan_id,
            "borrower_id": borrower_id,
            "org_id": self.org_id,
            "user_id": self.user_id,
        })

        try:
            # Verify loan belongs to this org
            self._verify_loan_org(loan_id)

            # Step 1: Gather documents
            if documents is None:
                documents = self._gather_commission_documents(loan_id, borrower_id)

            _audit(audit_trail, "documents_gathered", {
                "document_count": len(documents),
                "doc_types": list({d.get("doc_type") for d in documents}),
            })

            if not documents:
                return CommissionIncomeResult(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    org_id=self.org_id,
                    confidence=0,
                    flags=["NO_COMMISSION_DOCUMENTS"],
                    recommendations=[
                        "No commission-related documents found. Upload W-2s, "
                        "paystubs, 1099-NEC/MISC forms, or tax returns showing "
                        "commission income to begin analysis."
                    ],
                    audit_trail=audit_trail,
                    success=False,
                    error="No commission income documents found for this borrower.",
                    duration_ms=_now_ms() - start_ms,
                )

            # Step 2: Parse and group documents by employer/source
            parsed_sources = self._parse_documents_into_sources(documents)
            _audit(audit_trail, "sources_parsed", {
                "source_count": len(parsed_sources),
                "employers": [s.get("employer_name") for s in parsed_sources],
            })

            if not parsed_sources:
                return CommissionIncomeResult(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    org_id=self.org_id,
                    confidence=0,
                    flags=["NO_COMMISSION_DATA_EXTRACTED"],
                    recommendations=[
                        "Documents were found but no commission income data could "
                        "be extracted. Verify document quality and completeness."
                    ],
                    audit_trail=audit_trail,
                    success=False,
                    error="Could not extract commission income data from provided documents.",
                    duration_ms=_now_ms() - start_ms,
                )

            # Step 3: Calculate per source
            commission_sources: List[CommissionSource] = []
            for parsed in parsed_sources:
                source = self._calculate_single_source(parsed, audit_trail)
                commission_sources.append(source)

            # Step 4: Run eligibility checks
            # Get total income from loan for commission-to-total ratio
            total_gross_income = self._get_borrower_total_income(loan_id, borrower_id)
            eligibility = self._validate_commission_eligibility(
                commission_sources, total_gross_income, audit_trail,
            )

            # Step 5: Aggregate across all sources
            total_monthly_commission = sum(
                (s.qualifying_monthly_commission for s in commission_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            total_monthly_base = sum(
                (s.qualifying_monthly_base for s in commission_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            total_monthly = (total_monthly_commission + total_monthly_base).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            total_annual = (total_monthly * MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

            # Commission as percentage of total income
            if total_gross_income > ZERO:
                commission_pct = (
                    total_monthly_commission / total_gross_income * ONE_HUNDRED
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                # If no other income data, commission IS the total income
                commission_pct = ONE_HUNDRED if total_monthly_commission > ZERO else ZERO

            # Determine primary method and overall trend
            primary_method = self._determine_primary_method(commission_sources)
            overall_trend = self._determine_overall_trend(commission_sources)

            # Confidence: weighted average by qualifying amount
            confidence = self._calculate_aggregate_confidence(commission_sources)

            # Step 6: Generate flags, recommendations, tasks
            all_flags = self._generate_flags(
                commission_sources, eligibility, commission_pct, overall_trend,
            )
            recommendations = self._generate_recommendations(all_flags, eligibility)
            tasks = self._generate_tasks(all_flags, eligibility, loan_id)

            _audit(audit_trail, "calculation_completed", {
                "total_monthly_commission": float(total_monthly_commission),
                "total_monthly_base": float(total_monthly_base),
                "total_qualifying_monthly": float(total_monthly),
                "commission_pct": float(commission_pct),
                "method": primary_method.value,
                "trend": overall_trend.value,
                "confidence": confidence,
                "flag_count": len(all_flags),
                "task_count": len(tasks),
            })

            result = CommissionIncomeResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                org_id=self.org_id,
                sources=commission_sources,
                eligibility=eligibility,
                total_qualifying_monthly_commission=total_monthly_commission,
                total_qualifying_monthly_base=total_monthly_base,
                total_qualifying_monthly=total_monthly,
                total_qualifying_annual=total_annual,
                commission_pct_of_total_income=commission_pct,
                primary_calculation_method=primary_method,
                overall_trend=overall_trend,
                confidence=confidence,
                flags=all_flags,
                recommendations=recommendations,
                tasks_to_create=tasks,
                audit_trail=audit_trail,
                duration_ms=_now_ms() - start_ms,
            )

            # Step 7: Persist
            self._save_calculation(result)

            return result

        except Exception as e:
            logger.exception(
                "Commission income calculation failed: loan=%s borrower=%s org=%s: %s",
                loan_id, borrower_id, self.org_id, e,
            )
            _audit(audit_trail, "calculation_error", {"error": str(e)})
            return CommissionIncomeResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                org_id=self.org_id,
                confidence=0,
                audit_trail=audit_trail,
                success=False,
                error=str(e),
                duration_ms=_now_ms() - start_ms,
            )

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

    # =========================================================================
    # 4. ELIGIBILITY VALIDATION (public API)
    # =========================================================================

    def validate_commission_eligibility(
        self,
        employment_data: Dict[str, Any],
    ) -> EligibilityResult:
        """
        Validate whether commission income is eligible for qualification.

        Checks employment continuity, history requirements, employer
        consistency, and income trajectory per agency guidelines.

        Args:
            employment_data: Dict with keys:
                - employer_name (str)
                - employer_ein (str, optional)
                - start_date (str or date): employment start date
                - current_employer (bool): still employed here
                - prior_employer_name (str, optional)
                - prior_employer_start_date (str or date, optional)
                - prior_employer_end_date (str or date, optional)
                - industry (str, optional)
                - prior_industry (str, optional)
                - years_commission_history (int)
                - commission_pct_of_total (Decimal or float)
                - year1_commission (Decimal or float)
                - year2_commission (Decimal or float, optional)
                - total_gross_income (Decimal or float)

        Returns:
            EligibilityResult with detailed assessment.
        """
        disqualifying: List[str] = []
        warnings: List[str] = []

        # Commission significance check
        commission_pct = _to_decimal(employment_data.get("commission_pct_of_total", 0))
        total_gross = _to_decimal(employment_data.get("total_gross_income", 0))
        year1_commission = _to_decimal(employment_data.get("year1_commission", 0))
        year2_commission_raw = employment_data.get("year2_commission")
        year2_commission = _to_decimal(year2_commission_raw) if year2_commission_raw is not None else None

        if total_gross > ZERO and commission_pct == ZERO:
            # Recalculate from raw amounts
            commission_pct = (year1_commission / total_gross * ONE_HUNDRED).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

        requires_two_year = commission_pct >= COMMISSION_SIGNIFICANCE_THRESHOLD_PCT

        # Employment duration
        start_date = _parse_date(employment_data.get("start_date"))
        today = date.today()
        if start_date:
            employment_days = (today - start_date).days
            employment_months = max(0, employment_days // 30)
        else:
            employment_months = int(employment_data.get("years_commission_history", 0)) * 12

        # History sufficiency
        has_year2 = year2_commission is not None and year2_commission > ZERO
        years_available = 2 if has_year2 else (1 if year1_commission > ZERO else 0)
        has_sufficient_history = years_available >= HISTORY_YEARS_REQUIRED

        # 1-year exception check
        can_use_one_year = False
        if not has_sufficient_history and years_available >= HISTORY_YEARS_MINIMUM:
            # Allowed if: stable/increasing AND >= 12 months with same employer
            is_current = employment_data.get("current_employer", True)
            if is_current and employment_months >= 12:
                # Check trend
                if has_year2:
                    if year1_commission >= year2_commission:
                        can_use_one_year = True
                else:
                    # Only 1 year of data -- allowed with 12+ months tenure
                    can_use_one_year = True

                if can_use_one_year:
                    warnings.append(
                        "Using 1-year commission history exception: income is "
                        "stable/increasing with 12+ months at current employer."
                    )
            else:
                if not is_current:
                    disqualifying.append(
                        "Commission income requires 2-year history. Borrower is no "
                        "longer with the commission-earning employer."
                    )
                elif employment_months < 12:
                    disqualifying.append(
                        f"Commission income requires 2-year history or 12+ months "
                        f"with current employer (currently {employment_months} months)."
                    )

        if requires_two_year and not has_sufficient_history and not can_use_one_year:
            disqualifying.append(
                f"Commission is {commission_pct}% of total income (>= 25% threshold). "
                f"2-year history required but only {years_available} year(s) available."
            )

        # Employer consistency
        employer_name = employment_data.get("employer_name", "")
        prior_employer = employment_data.get("prior_employer_name", "")
        employer_consistent = True

        if prior_employer and employer_name:
            if employer_name.lower().strip() != prior_employer.lower().strip():
                employer_consistent = False
                industry = (employment_data.get("industry") or "").lower()
                prior_industry = (employment_data.get("prior_industry") or "").lower()

                if industry and prior_industry and industry == prior_industry:
                    warnings.append(
                        f"Employer changed ({prior_employer} -> {employer_name}) "
                        f"but same industry ({industry}). May be acceptable with "
                        f"letter of explanation."
                    )
                else:
                    warnings.append(
                        f"Employer changed ({prior_employer} -> {employer_name}). "
                        "Different employer and/or industry may affect commission "
                        "income continuity assessment."
                    )

        # Employment gap detection
        has_gap = False
        gap_days = 0
        prior_end = _parse_date(employment_data.get("prior_employer_end_date"))
        if prior_end and start_date:
            gap_days = (start_date - prior_end).days
            if gap_days > EMPLOYMENT_GAP_THRESHOLD_DAYS:
                has_gap = True
                disqualifying.append(
                    f"Employment gap of {gap_days} days detected between prior "
                    f"employer and current position (threshold: {EMPLOYMENT_GAP_THRESHOLD_DAYS} days). "
                    f"Additional documentation required."
                )
            elif gap_days > 30:
                has_gap = True
                warnings.append(
                    f"Employment gap of {gap_days} days detected. Letter of "
                    f"explanation may be required."
                )

        # Income trajectory check
        if has_year2 and year2_commission > ZERO:
            decline_pct = ZERO
            if year1_commission < year2_commission:
                decline_pct = (
                    (year2_commission - year1_commission) / year2_commission * ONE_HUNDRED
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if decline_pct > DECLINE_CRITICAL_PCT:
                warnings.append(
                    f"Commission income declined {decline_pct}% year-over-year. "
                    "Use lower of 2-year average or most recent 12 months."
                )

        is_eligible = len(disqualifying) == 0

        notes = ""
        if is_eligible and requires_two_year:
            if has_sufficient_history:
                notes = "Commission qualifies with 2-year history. Use appropriate averaging method."
            elif can_use_one_year:
                notes = "Commission qualifies under 1-year exception (stable/increasing, 12+ months tenure)."
        elif is_eligible:
            notes = "Commission < 25% of total income. Standard employment verification sufficient."

        return EligibilityResult(
            is_eligible=is_eligible,
            requires_two_year_history=requires_two_year,
            has_sufficient_history=has_sufficient_history or can_use_one_year,
            commission_pct_of_total=commission_pct,
            employment_months=employment_months,
            employer_consistent=employer_consistent,
            has_employment_gap=has_gap,
            gap_days=gap_days,
            can_use_one_year_exception=can_use_one_year,
            disqualifying_reasons=disqualifying,
            warnings=warnings,
            notes=notes,
        )

    # =========================================================================
    # 5. OVERRIDE CAPABILITY
    # =========================================================================

    async def apply_override(
        self,
        calculation_id: str,
        loan_id: int,
        override_monthly_amount: Decimal,
        justification: str,
        approved_by_user_id: int,
    ) -> CommissionIncomeResult:
        """
        Apply a manual override to a commission income calculation.

        Requires justification text and records the override in the audit trail
        for compliance purposes. The original calculation is preserved and the
        override is layered on top.

        Args:
            calculation_id: The ID of the calculation to override.
            loan_id: The loan ID (for org verification).
            override_monthly_amount: The overridden qualifying monthly amount.
            justification: Required written justification for the override.
            approved_by_user_id: User ID of the person approving the override.

        Returns:
            Updated CommissionIncomeResult with override applied.

        Raises:
            ValueError: If justification is empty or amount is negative.
        """
        if not justification or len(justification.strip()) < 10:
            raise ValueError(
                "Override justification must be at least 10 characters. "
                "Provide a detailed explanation for compliance purposes."
            )

        if override_monthly_amount < ZERO:
            raise ValueError("Override amount cannot be negative.")

        self._verify_loan_org(loan_id)

        # Fetch existing calculation
        existing = self.db.execute(
            text("""
                SELECT
                    ic.loan_id, ic.borrower_id,
                    ic.total_qualifying_monthly_income,
                    ic.total_qualifying_annual_income,
                    ic.ai_flags, ic.ai_recommendations,
                    ic.ai_confidence_score,
                    ic.calculation_method
                FROM income_calculations ic
                JOIN loans l ON l.id = ic.loan_id
                WHERE ic.id = :calc_id
                  AND l.organization_id = :org_id
            """),
            {"calc_id": calculation_id, "org_id": self.org_id},
        ).fetchone()

        if not existing:
            raise ValueError(
                f"Calculation {calculation_id} not found or does not belong to this organization."
            )

        override_annual = (override_monthly_amount * MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        original_monthly = _to_decimal(existing.total_qualifying_monthly_income)
        variance_pct = ZERO
        if original_monthly > ZERO:
            variance_pct = (
                (override_monthly_amount - original_monthly) / original_monthly * ONE_HUNDRED
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Persist override
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE income_calculations
                SET total_qualifying_monthly_income = :monthly,
                    total_qualifying_annual_income = :annual,
                    calculation_method = 'override',
                    status = 'override_applied',
                    review_notes = :justification,
                    reviewed_by = :reviewer,
                    reviewed_at = :now,
                    updated_at = :now
                WHERE id = :calc_id
            """),
            {
                "monthly": float(override_monthly_amount),
                "annual": float(override_annual),
                "justification": justification,
                "reviewer": approved_by_user_id,
                "now": now,
                "calc_id": calculation_id,
            },
        )
        self.db.commit()

        logger.info(
            "Commission income override applied: calc_id=%s loan=%s "
            "original=%.2f override=%.2f variance=%.2f%% by_user=%s",
            calculation_id, loan_id,
            float(original_monthly), float(override_monthly_amount),
            float(variance_pct), approved_by_user_id,
        )

        # Build result reflecting the override
        existing_flags = []
        try:
            existing_flags = json.loads(existing.ai_flags) if existing.ai_flags else []
        except (json.JSONDecodeError, TypeError):
            pass

        override_flag = (
            f"OVERRIDE_APPLIED: Original ${float(original_monthly):,.2f}/mo "
            f"-> ${float(override_monthly_amount):,.2f}/mo "
            f"({'+' if variance_pct >= ZERO else ''}{float(variance_pct):.1f}%)"
        )

        return CommissionIncomeResult(
            loan_id=existing.loan_id,
            borrower_id=existing.borrower_id,
            org_id=self.org_id,
            calculation_id=calculation_id,
            total_qualifying_monthly_commission=override_monthly_amount,
            total_qualifying_monthly=override_monthly_amount,
            total_qualifying_annual=override_annual,
            primary_calculation_method=CalculationMethod.OVERRIDE,
            confidence=100,  # Manual override = full confidence
            flags=existing_flags + [override_flag],
            override_applied=True,
            audit_trail=[{
                "event": "override_applied",
                "timestamp": now.isoformat(),
                "user_id": approved_by_user_id,
                "original_monthly": float(original_monthly),
                "override_monthly": float(override_monthly_amount),
                "variance_pct": float(variance_pct),
                "justification": justification,
            }],
        )

    # =========================================================================
    # INTERNAL: DOCUMENT GATHERING
    # =========================================================================

    def _gather_commission_documents(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Query smart_documents for commission-relevant documents with
        extracted field data from smart_document_extractions.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    sd.id              AS doc_id,
                    sd.doc_type        AS doc_type,
                    sd.ocr_text        AS ocr_text,
                    sd.uploaded_at     AS uploaded_at,
                    sd.file_name       AS file_name,
                    sde.extracted_fields  AS extracted_fields,
                    sde.confidence_scores AS confidence_scores,
                    sde.overall_confidence AS overall_confidence
                FROM smart_documents sd
                LEFT JOIN smart_document_extractions sde
                    ON sde.document_id = sd.id
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.loan_id = :loan_id
                  AND sd.borrower_id = :borrower_id
                  AND sd.doc_type IN :doc_types
                  AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                  AND l.organization_id = :org_id
                ORDER BY sd.uploaded_at DESC
            """),
            {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "doc_types": tuple(COMMISSION_DOC_TYPES),
                "org_id": self.org_id,
            },
        ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            extracted = row.extracted_fields
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (json.JSONDecodeError, TypeError):
                    extracted = {}

            confidence_scores = row.confidence_scores
            if isinstance(confidence_scores, str):
                try:
                    confidence_scores = json.loads(confidence_scores)
                except (json.JSONDecodeError, TypeError):
                    confidence_scores = {}

            results.append({
                "doc_id": row.doc_id,
                "doc_type": str(row.doc_type) if row.doc_type else None,
                "ocr_text": row.ocr_text,
                "uploaded_at": row.uploaded_at,
                "file_name": row.file_name,
                "extracted_fields": extracted or {},
                "confidence_scores": confidence_scores or {},
                "overall_confidence": row.overall_confidence or 0,
            })

        return results

    # =========================================================================
    # INTERNAL: DOCUMENT PARSING & GROUPING
    # =========================================================================

    def _parse_documents_into_sources(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Parse documents and group by employer/source to build commission
        income sources. Each employer gets a separate source entry with
        all relevant year data aggregated.

        Returns list of dicts, each representing one commission source with:
            - employer_name, employer_ein, position_title
            - commission_type
            - yearly_data: {year: {commission, base, total_w2, ...}}
            - ytd_data: {commission, base, total_gross, months_elapsed, pay_date}
            - voe_data: {start_date, current_base, commission_frequency, ...}
            - doc_ids: list of contributing doc IDs
        """
        # Group by employer (normalized name)
        employer_groups: Dict[str, Dict[str, Any]] = {}

        for doc in documents:
            ef = doc.get("extracted_fields", {})
            doc_type = doc.get("doc_type", "")
            doc_id = doc.get("doc_id")

            employer = (
                ef.get("employer_name", "") or ""
            ).strip()
            employer_key = employer.lower() if employer else "_unknown_"

            if employer_key not in employer_groups:
                employer_groups[employer_key] = {
                    "employer_name": employer or None,
                    "employer_ein": ef.get("employer_ein") or ef.get("ein"),
                    "position_title": ef.get("job_title") or ef.get("position_title"),
                    "commission_type": CommissionType.W2_COMMISSION,
                    "yearly_data": {},
                    "ytd_data": None,
                    "voe_data": None,
                    "doc_ids": [],
                    "expense_data": [],
                }

            group = employer_groups[employer_key]
            group["doc_ids"].append(doc_id)

            # Update employer info if we get better data
            if not group["employer_ein"] and (ef.get("employer_ein") or ef.get("ein")):
                group["employer_ein"] = ef.get("employer_ein") or ef.get("ein")
            if not group["position_title"] and (ef.get("job_title") or ef.get("position_title")):
                group["position_title"] = ef.get("job_title") or ef.get("position_title")

            if doc_type == "PAYSTUB":
                self._parse_paystub_into_group(group, ef)

            elif doc_type == "W2":
                self._parse_w2_into_group(group, ef)

            elif doc_type in ("1099_NEC", "1099_MISC"):
                group["commission_type"] = CommissionType.INDEPENDENT_1099
                self._parse_1099_into_group(group, ef)

            elif doc_type in ("TAX_RETURN", "BUSINESS_TAX_RETURN"):
                self._parse_tax_return_into_group(group, ef)

            elif doc_type == "VOE":
                self._parse_voe_into_group(group, ef)

        # Filter out groups with no commission data at all
        result: List[Dict[str, Any]] = []
        for group in employer_groups.values():
            has_commission = False

            # Check yearly data for commission amounts
            for year_data in group["yearly_data"].values():
                if _to_decimal(year_data.get("commission")) > ZERO:
                    has_commission = True
                    break

            # Check YTD
            if not has_commission and group["ytd_data"]:
                if _to_decimal(group["ytd_data"].get("commission")) > ZERO:
                    has_commission = True

            # Check 1099 amounts (all income is commission)
            if not has_commission and group["commission_type"] == CommissionType.INDEPENDENT_1099:
                for year_data in group["yearly_data"].values():
                    if _to_decimal(year_data.get("total_w2")) > ZERO:
                        has_commission = True
                        break

            if has_commission:
                result.append(group)

        return result

    def _parse_paystub_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract YTD commission and base data from a paystub."""
        ytd_commission = _to_decimal(ef.get("ytd_commission"))
        ytd_gross = _to_decimal(ef.get("ytd_gross"))
        ytd_base = _to_decimal(
            ef.get("ytd_regular_earnings")
            or ef.get("ytd_base_salary")
            or ef.get("ytd_regular_pay")
        )
        pay_date_str = ef.get("pay_date")
        pay_freq = (ef.get("pay_frequency") or "MONTHLY").upper()

        # Current period commission
        current_commission = _to_decimal(ef.get("commission"))
        current_base = _to_decimal(
            ef.get("regular_earnings")
            or ef.get("base_salary")
            or ef.get("regular_pay")
            or ef.get("gross_pay")
        )

        months_elapsed = _months_elapsed_in_year(pay_date_str)

        existing_ytd = group["ytd_data"]
        if existing_ytd is None or (
            pay_date_str and (existing_ytd.get("pay_date") or "0000") < pay_date_str
        ):
            group["ytd_data"] = {
                "commission": ytd_commission,
                "base": ytd_base if ytd_base > ZERO else (ytd_gross - ytd_commission if ytd_gross > ytd_commission else ZERO),
                "total_gross": ytd_gross,
                "months_elapsed": months_elapsed or 0,
                "pay_date": pay_date_str,
                "pay_frequency": pay_freq,
                "current_period_commission": current_commission,
                "current_period_base": current_base,
            }

    def _parse_w2_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract annual commission and wage data from a W-2."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        total_wages = _to_decimal(ef.get("wages_tips_compensation"))
        # W-2 Box 1 includes all compensation. We need to separate commission.
        # Some W-2 extractions may have commission broken out; most do not.
        commission = _to_decimal(ef.get("commission_income") or ef.get("commission"))
        base_salary = _to_decimal(ef.get("base_salary") or ef.get("regular_wages"))

        # If commission not broken out but we have base, derive it
        if commission == ZERO and base_salary > ZERO and total_wages > base_salary:
            commission = (total_wages - base_salary).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        existing = group["yearly_data"].get(tax_year, {})
        group["yearly_data"][tax_year] = {
            "commission": max(commission, _to_decimal(existing.get("commission"))),
            "base": max(base_salary, _to_decimal(existing.get("base"))),
            "total_w2": max(total_wages, _to_decimal(existing.get("total_w2"))),
            "source": "W2",
        }

    def _parse_1099_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract commission data from 1099-NEC or 1099-MISC."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        # 1099-NEC Box 1: Nonemployee compensation (all is commission)
        nec_amount = _to_decimal(
            ef.get("nonemployee_compensation")
            or ef.get("box1_amount")
            or ef.get("total_compensation")
        )

        # 1099-MISC: various boxes, but typically Box 7 (pre-2020) or Box 1
        misc_amount = _to_decimal(
            ef.get("box7_nonemployee_compensation")
            or ef.get("rents")  # sometimes misclassified
        )

        total = nec_amount + misc_amount

        existing = group["yearly_data"].get(tax_year, {})
        group["yearly_data"][tax_year] = {
            "commission": total + _to_decimal(existing.get("commission")),
            "base": ZERO,  # 1099 has no base salary
            "total_w2": total + _to_decimal(existing.get("total_w2")),
            "source": "1099",
        }

        # Look for Schedule C expenses
        schedule_c_expenses = _to_decimal(ef.get("schedule_c_total_expenses"))
        if schedule_c_expenses > ZERO:
            group["expense_data"].append({
                "tax_year": tax_year,
                "schedule_c_expenses": schedule_c_expenses,
                "gross_commission": total,
            })

    def _parse_tax_return_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract commission-relevant data from tax returns."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        # Schedule C self-employment income (common for real estate agents)
        schedule_c_gross = _to_decimal(ef.get("schedule_c_gross_receipts"))
        schedule_c_net = _to_decimal(ef.get("net_profit_loss") or ef.get("net_profit"))
        schedule_c_expenses = _to_decimal(ef.get("schedule_c_total_expenses"))

        if schedule_c_gross > ZERO:
            group["commission_type"] = CommissionType.SCHEDULE_C
            existing = group["yearly_data"].get(tax_year, {})
            group["yearly_data"][tax_year] = {
                "commission": schedule_c_net if schedule_c_net > ZERO else schedule_c_gross,
                "base": ZERO,
                "total_w2": schedule_c_gross,
                "schedule_c_gross": schedule_c_gross,
                "schedule_c_net": schedule_c_net,
                "depreciation_addback": _to_decimal(ef.get("depreciation_addback")),
                "amortization_addback": _to_decimal(ef.get("amortization_addback")),
                "source": "SCHEDULE_C",
            }

            if schedule_c_expenses > ZERO:
                group["expense_data"].append({
                    "tax_year": tax_year,
                    "schedule_c_expenses": schedule_c_expenses,
                    "gross_commission": schedule_c_gross,
                })

        # Form 2106 unreimbursed employee expenses
        form_2106 = _to_decimal(ef.get("form_2106_expenses"))
        if form_2106 > ZERO:
            group["expense_data"].append({
                "tax_year": tax_year,
                "form_2106_expenses": form_2106,
                "gross_commission": _to_decimal(
                    group["yearly_data"].get(tax_year, {}).get("commission")
                ),
            })

        # Also check W-2 wages on tax return Line 1
        wages_line1 = _to_decimal(ef.get("wages_salaries_tips") or ef.get("line1_wages"))
        if wages_line1 > ZERO and tax_year not in group["yearly_data"]:
            group["yearly_data"][tax_year] = {
                "commission": ZERO,  # Cannot separate from tax return Line 1
                "base": ZERO,
                "total_w2": wages_line1,
                "source": "TAX_RETURN",
            }

    def _parse_voe_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract employment verification data from VOE."""
        start_date_str = ef.get("employment_start_date") or ef.get("hire_date")
        current_base = _to_decimal(ef.get("current_base_salary") or ef.get("base_rate"))
        commission_freq = ef.get("commission_frequency") or ef.get("commission_pay_frequency")
        probability_of_continuance = ef.get("probability_of_continuance")

        # VOE may have annual earnings history
        prior_year1_earnings = _to_decimal(ef.get("prior_year1_earnings") or ef.get("year1_earnings"))
        prior_year2_earnings = _to_decimal(ef.get("prior_year2_earnings") or ef.get("year2_earnings"))
        ytd_earnings = _to_decimal(ef.get("ytd_earnings"))

        group["voe_data"] = {
            "start_date": start_date_str,
            "current_base": current_base,
            "commission_frequency": commission_freq,
            "probability_of_continuance": probability_of_continuance,
            "prior_year1_earnings": prior_year1_earnings,
            "prior_year2_earnings": prior_year2_earnings,
            "ytd_earnings": ytd_earnings,
            "is_currently_employed": ef.get("currently_employed", True),
        }

    # =========================================================================
    # INTERNAL: SINGLE SOURCE CALCULATION
    # =========================================================================

    def _calculate_single_source(
        self,
        parsed: Dict[str, Any],
        audit_trail: List[Dict[str, Any]],
    ) -> CommissionSource:
        """
        Calculate qualifying commission income for a single employer/source.

        Applies the appropriate calculation method based on data availability
        and income trending:
        - 2-year simple average (default)
        - Weighted average (recent year weighted 60%)
        - YTD annualization (if insufficient prior year data)
        - Most-recent-12-months (declining income)
        """
        source_id = str(uuid.uuid4())[:12]
        employer_name = parsed.get("employer_name")
        employer_ein = parsed.get("employer_ein")
        position_title = parsed.get("position_title")
        commission_type = parsed.get("commission_type", CommissionType.W2_COMMISSION)
        yearly_data = parsed.get("yearly_data", {})
        ytd_data = parsed.get("ytd_data")
        voe_data = parsed.get("voe_data")
        expense_data = parsed.get("expense_data", [])
        doc_ids = parsed.get("doc_ids", [])
        flags: List[str] = []

        # Sort years descending
        sorted_years = sorted(yearly_data.keys(), reverse=True)

        # Extract year 1 (most recent) and year 2 (prior)
        year1_tax_year: Optional[int] = None
        year1_commission = ZERO
        year1_base = ZERO
        year1_total_w2 = ZERO

        year2_tax_year: Optional[int] = None
        year2_commission = ZERO
        year2_base = ZERO
        year2_total_w2 = ZERO

        if len(sorted_years) >= 1:
            year1_tax_year = sorted_years[0]
            yd1 = yearly_data[year1_tax_year]
            year1_commission = _to_decimal(yd1.get("commission"))
            year1_base = _to_decimal(yd1.get("base"))
            year1_total_w2 = _to_decimal(yd1.get("total_w2"))

            # If commission not separated, attempt derivation from W-2 total minus base
            if year1_commission == ZERO and year1_total_w2 > year1_base and year1_base > ZERO:
                year1_commission = (year1_total_w2 - year1_base).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                flags.append(
                    f"COMMISSION_DERIVED: {year1_tax_year} commission derived from "
                    f"W-2 total minus base salary"
                )

            # Schedule C add-backs
            depreciation = _to_decimal(yd1.get("depreciation_addback"))
            amortization = _to_decimal(yd1.get("amortization_addback"))
            if depreciation > ZERO or amortization > ZERO:
                year1_commission = (year1_commission + depreciation + amortization).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                flags.append(
                    f"ADDBACKS_APPLIED: {year1_tax_year} depreciation "
                    f"(${float(depreciation):,.2f}) and amortization "
                    f"(${float(amortization):,.2f}) added back per Fannie Mae"
                )

        if len(sorted_years) >= 2:
            year2_tax_year = sorted_years[1]
            yd2 = yearly_data[year2_tax_year]
            year2_commission = _to_decimal(yd2.get("commission"))
            year2_base = _to_decimal(yd2.get("base"))
            year2_total_w2 = _to_decimal(yd2.get("total_w2"))

            # Same derivation logic for year 2
            if year2_commission == ZERO and year2_total_w2 > year2_base and year2_base > ZERO:
                year2_commission = (year2_total_w2 - year2_base).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

            # Schedule C add-backs for year 2
            depreciation2 = _to_decimal(yd2.get("depreciation_addback"))
            amortization2 = _to_decimal(yd2.get("amortization_addback"))
            if depreciation2 > ZERO or amortization2 > ZERO:
                year2_commission = (year2_commission + depreciation2 + amortization2).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

        # YTD data
        ytd_commission = ZERO
        ytd_base = ZERO
        ytd_total_gross = ZERO
        ytd_months_elapsed = 0
        if ytd_data:
            ytd_commission = _to_decimal(ytd_data.get("commission"))
            ytd_base = _to_decimal(ytd_data.get("base"))
            ytd_total_gross = _to_decimal(ytd_data.get("total_gross"))
            ytd_months_elapsed = ytd_data.get("months_elapsed", 0)

        # VOE-derived start date and tenure
        start_date: Optional[date] = None
        years_in_role: Optional[Decimal] = None
        if voe_data:
            start_date = _parse_date(voe_data.get("start_date"))
            if start_date:
                tenure_days = (date.today() - start_date).days
                years_in_role = (Decimal(tenure_days) / Decimal("365.25")).quantize(
                    FOUR_PLACES, rounding=ROUND_HALF_UP,
                )

            # Supplement with VOE earnings if we lack W-2 data
            if not sorted_years:
                voe_yr1 = _to_decimal(voe_data.get("prior_year1_earnings"))
                voe_yr2 = _to_decimal(voe_data.get("prior_year2_earnings"))
                current_year = date.today().year
                if voe_yr1 > ZERO:
                    # Treat VOE prior year earnings as total (cannot split)
                    yearly_data[current_year - 1] = {
                        "commission": voe_yr1,
                        "base": ZERO,
                        "total_w2": voe_yr1,
                        "source": "VOE",
                    }
                    year1_tax_year = current_year - 1
                    year1_commission = voe_yr1
                    year1_total_w2 = voe_yr1
                    sorted_years.append(current_year - 1)
                    flags.append("VOE_EARNINGS_USED: Prior year earnings from VOE used (no W-2 available)")

                if voe_yr2 > ZERO:
                    yearly_data[current_year - 2] = {
                        "commission": voe_yr2,
                        "base": ZERO,
                        "total_w2": voe_yr2,
                        "source": "VOE",
                    }
                    year2_tax_year = current_year - 2
                    year2_commission = voe_yr2
                    year2_total_w2 = voe_yr2
                    sorted_years.append(current_year - 2)

        # --- Trending analysis ---
        income_history: List[Dict[str, Any]] = []
        if year1_commission > ZERO and year1_tax_year:
            entry1: Dict[str, Any] = {
                "tax_year": year1_tax_year,
                "commission_amount": year1_commission,
            }
            if ytd_commission > ZERO and ytd_months_elapsed > 0:
                entry1["ytd_amount"] = ytd_commission
                entry1["ytd_months"] = ytd_months_elapsed
            income_history.append(entry1)
        if year2_commission > ZERO and year2_tax_year:
            income_history.append({
                "tax_year": year2_tax_year,
                "commission_amount": year2_commission,
            })

        trend = self.analyze_trending(income_history)

        # --- Unreimbursed expense analysis ---
        expense_analysis: Optional[ExpenseAnalysis] = None
        if expense_data:
            expense_analysis = self.calculate_unreimbursed_expenses(expense_data)
            if expense_analysis.exceeds_threshold:
                flags.append(
                    f"UBE_DEDUCTION: Unreimbursed business expenses "
                    f"({expense_analysis.expense_ratio_pct}% of commission) "
                    f"exceed {UBE_DEDUCTION_THRESHOLD_PCT}% threshold. "
                    f"Monthly deduction: ${float(expense_analysis.deduction_amount):,.2f}"
                )

        # --- Determine calculation method and compute qualifying income ---
        method, monthly_commission, monthly_base = self._select_and_calculate(
            year1_commission=year1_commission,
            year2_commission=year2_commission,
            year1_base=year1_base,
            year2_base=year2_base,
            ytd_commission=ytd_commission,
            ytd_base=ytd_base,
            ytd_months_elapsed=ytd_months_elapsed,
            trend=trend,
            has_two_years=year2_tax_year is not None and year2_commission > ZERO,
            flags=flags,
        )

        # Apply UBE deduction if applicable
        if expense_analysis and expense_analysis.exceeds_threshold:
            monthly_commission = max(
                ZERO,
                (monthly_commission - expense_analysis.deduction_amount).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                ),
            )
            flags.append(
                f"UBE_APPLIED: Commission reduced by ${float(expense_analysis.deduction_amount):,.2f}/mo "
                f"for unreimbursed business expenses"
            )

        monthly_total = (monthly_commission + monthly_base).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        # Confidence scoring
        confidence = self._calculate_source_confidence(
            has_w2=any(yd.get("source") == "W2" for yd in yearly_data.values()),
            has_paystub=ytd_data is not None,
            has_voe=voe_data is not None,
            has_two_years=year2_tax_year is not None,
            trend=trend,
            commission_derived="COMMISSION_DERIVED" in " ".join(flags),
        )

        _audit(audit_trail, "source_calculated", {
            "source_id": source_id,
            "employer": employer_name,
            "method": method.value,
            "monthly_commission": float(monthly_commission),
            "monthly_base": float(monthly_base),
            "monthly_total": float(monthly_total),
            "trend": trend.direction.value,
            "confidence": confidence,
        })

        return CommissionSource(
            source_id=source_id,
            commission_type=commission_type,
            employer_name=employer_name,
            employer_ein=employer_ein,
            position_title=position_title,
            start_date=start_date,
            years_in_role=years_in_role,
            year1_commission=year1_commission,
            year1_base_salary=year1_base,
            year1_total_w2=year1_total_w2,
            year1_tax_year=year1_tax_year,
            year2_commission=year2_commission,
            year2_base_salary=year2_base,
            year2_total_w2=year2_total_w2,
            year2_tax_year=year2_tax_year,
            ytd_commission=ytd_commission,
            ytd_base_salary=ytd_base,
            ytd_total_gross=ytd_total_gross,
            ytd_months_elapsed=ytd_months_elapsed,
            qualifying_monthly_commission=monthly_commission,
            qualifying_monthly_base=monthly_base,
            qualifying_monthly_total=monthly_total,
            calculation_method=method,
            trend_analysis=trend,
            expense_analysis=expense_analysis,
            source_doc_ids=doc_ids,
            confidence=confidence,
            flags=flags,
            notes=f"Commission income from {employer_name or 'unknown employer'} "
                  f"calculated using {method.value} method.",
        )

    # =========================================================================
    # INTERNAL: METHOD SELECTION & CALCULATION
    # =========================================================================

    def _select_and_calculate(
        self,
        year1_commission: Decimal,
        year2_commission: Decimal,
        year1_base: Decimal,
        year2_base: Decimal,
        ytd_commission: Decimal,
        ytd_base: Decimal,
        ytd_months_elapsed: int,
        trend: TrendAnalysis,
        has_two_years: bool,
        flags: List[str],
    ) -> Tuple[CalculationMethod, Decimal, Decimal]:
        """
        Select the appropriate calculation method and compute monthly
        qualifying amounts for both commission and base salary.

        Per Fannie Mae B3-3.1:
        - Stable/increasing with 2 years: simple average (Y1+Y2)/24
        - Declining: use lower of 2-year average or most recent 12 months
        - Only 1 year (with exception): single year / 12
        - YTD only: annualize current YTD

        Returns:
            (method, monthly_commission, monthly_base)
        """
        if has_two_years:
            # --- 2-year data available ---

            # Simple average: (Year1 + Year2) / 24
            simple_avg_commission = (
                (year1_commission + year2_commission) / MONTHS_PER_TWO_YEARS
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            simple_avg_base = (
                (year1_base + year2_base) / MONTHS_PER_TWO_YEARS
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Check for declining income
            if trend.direction == TrendDirection.DECLINING:
                decline_pct = abs(trend.yoy_change_pct or ZERO)

                if decline_pct >= DECLINE_CRITICAL_PCT:
                    # Use most recent 12 months only
                    recent_monthly_commission = (year1_commission / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )
                    recent_monthly_base = (year1_base / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )

                    # Use the LOWER of 2-year average or most recent year
                    if recent_monthly_commission <= simple_avg_commission:
                        flags.append(
                            f"DECLINING_COMMISSION: Income declined {float(decline_pct):.1f}% "
                            f"YoY. Using most recent year (${float(recent_monthly_commission):,.2f}/mo) "
                            f"which is lower than 2-year average (${float(simple_avg_commission):,.2f}/mo)."
                        )
                        return (
                            CalculationMethod.MOST_RECENT_12_MONTHS,
                            recent_monthly_commission,
                            recent_monthly_base,
                        )
                    else:
                        flags.append(
                            f"DECLINING_COMMISSION: Income declined {float(decline_pct):.1f}% "
                            f"YoY. Using 2-year average (${float(simple_avg_commission):,.2f}/mo) "
                            f"which is lower than most recent year."
                        )
                        return (
                            CalculationMethod.SIMPLE_AVERAGE,
                            simple_avg_commission,
                            simple_avg_base,
                        )

                elif decline_pct >= DECLINE_WARNING_PCT:
                    flags.append(
                        f"COMMISSION_DECLINE_WARNING: Income declined {float(decline_pct):.1f}% "
                        f"YoY. Using 2-year average but flagged for LO review."
                    )

            # Stable or increasing: check if weighted average is more favorable
            if trend.direction == TrendDirection.INCREASING:
                # Weighted: 60% recent year, 40% prior year
                weighted_commission = (
                    year1_commission * Decimal("0.6") + year2_commission * Decimal("0.4")
                ) / MONTHS_PER_YEAR
                weighted_commission = weighted_commission.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                weighted_base = (
                    year1_base * Decimal("0.6") + year2_base * Decimal("0.4")
                ) / MONTHS_PER_YEAR
                weighted_base = weighted_base.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                # Use the LOWER of simple average or weighted (conservative per guidelines)
                if weighted_commission < simple_avg_commission:
                    return (CalculationMethod.WEIGHTED_AVERAGE, weighted_commission, weighted_base)

            # Default to simple average
            return (CalculationMethod.SIMPLE_AVERAGE, simple_avg_commission, simple_avg_base)

        elif year1_commission > ZERO:
            # --- Only 1 year of data ---

            # Check if YTD can supplement
            if ytd_commission > ZERO and ytd_months_elapsed >= 3:
                # Annualize YTD
                ytd_annualized_commission = (
                    ytd_commission / Decimal(ytd_months_elapsed) * MONTHS_PER_YEAR
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                ytd_annualized_base = ZERO
                if ytd_base > ZERO and ytd_months_elapsed > 0:
                    ytd_annualized_base = (
                        ytd_base / Decimal(ytd_months_elapsed) * MONTHS_PER_YEAR
                    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                # Use lower of prior year and YTD annualized (conservative)
                ytd_monthly = (ytd_annualized_commission / MONTHS_PER_YEAR).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
                year1_monthly = (year1_commission / MONTHS_PER_YEAR).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )

                if ytd_monthly < year1_monthly:
                    flags.append(
                        f"YTD_LOWER: YTD annualized commission "
                        f"(${float(ytd_monthly):,.2f}/mo) is lower than prior year "
                        f"(${float(year1_monthly):,.2f}/mo). Using YTD annualized."
                    )
                    monthly_base = (ytd_annualized_base / MONTHS_PER_YEAR).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP,
                    )
                    return (CalculationMethod.YTD_ANNUALIZED, ytd_monthly, monthly_base)
                else:
                    return (CalculationMethod.SINGLE_YEAR, year1_monthly, (year1_base / MONTHS_PER_YEAR).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))

            # Single year only
            flags.append(
                "SINGLE_YEAR_HISTORY: Only 1 year of commission data available. "
                "2-year history preferred per agency guidelines."
            )
            monthly_commission = (year1_commission / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            monthly_base = (year1_base / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            return (CalculationMethod.SINGLE_YEAR, monthly_commission, monthly_base)

        elif ytd_commission > ZERO and ytd_months_elapsed >= 3:
            # --- YTD only (no prior year) ---
            flags.append(
                "YTD_ONLY: No prior year data. Commission income annualized from "
                f"{ytd_months_elapsed} months of YTD data."
            )
            monthly_commission = (
                ytd_commission / Decimal(ytd_months_elapsed)
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            monthly_base = ZERO
            if ytd_base > ZERO:
                monthly_base = (
                    ytd_base / Decimal(ytd_months_elapsed)
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            return (CalculationMethod.YTD_ANNUALIZED, monthly_commission, monthly_base)

        else:
            # No usable data
            flags.append("INSUFFICIENT_DATA: No commission income data available for calculation.")
            return (CalculationMethod.SIMPLE_AVERAGE, ZERO, ZERO)

    # =========================================================================
    # INTERNAL: ELIGIBILITY VALIDATION (for internal pipeline use)
    # =========================================================================

    def _validate_commission_eligibility(
        self,
        sources: List[CommissionSource],
        total_gross_income: Decimal,
        audit_trail: List[Dict[str, Any]],
    ) -> EligibilityResult:
        """
        Run eligibility checks across all commission sources.
        Delegates to the public validate_commission_eligibility method
        after assembling employment data from parsed sources.
        """
        if not sources:
            return EligibilityResult(
                is_eligible=False,
                requires_two_year_history=False,
                has_sufficient_history=False,
                commission_pct_of_total=ZERO,
                employment_months=0,
                employer_consistent=True,
                has_employment_gap=False,
                disqualifying_reasons=["No commission sources found."],
            )

        # Use primary (highest-paying) source for eligibility
        primary = max(sources, key=lambda s: s.qualifying_monthly_commission)

        total_monthly_commission = sum(
            (s.qualifying_monthly_commission for s in sources), ZERO,
        )

        # Commission as % of total income
        if total_gross_income > ZERO:
            commission_pct = (
                total_monthly_commission / total_gross_income * ONE_HUNDRED
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            commission_pct = ONE_HUNDRED if total_monthly_commission > ZERO else ZERO

        employment_data: Dict[str, Any] = {
            "employer_name": primary.employer_name,
            "employer_ein": primary.employer_ein,
            "start_date": primary.start_date,
            "current_employer": True,
            "years_commission_history": HISTORY_YEARS_REQUIRED if primary.year2_tax_year else HISTORY_YEARS_MINIMUM,
            "commission_pct_of_total": commission_pct,
            "year1_commission": primary.year1_commission,
            "year2_commission": primary.year2_commission if primary.year2_commission > ZERO else None,
            "total_gross_income": total_gross_income if total_gross_income > ZERO else total_monthly_commission,
        }

        # Check for employer consistency across sources if multiple
        if len(sources) > 1:
            employers = [s.employer_name for s in sources if s.employer_name]
            unique_employers = set(e.lower().strip() for e in employers if e)
            if len(unique_employers) > 1:
                employment_data["prior_employer_name"] = sorted(unique_employers)[-1]

        eligibility = self.validate_commission_eligibility(employment_data)

        _audit(audit_trail, "eligibility_checked", eligibility.to_dict())

        return eligibility

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
    # INTERNAL: FLAG / RECOMMENDATION / TASK GENERATION
    # =========================================================================

    def _generate_flags(
        self,
        sources: List[CommissionSource],
        eligibility: EligibilityResult,
        commission_pct: Decimal,
        overall_trend: TrendDirection,
    ) -> List[str]:
        """Consolidate flags from all sources plus eligibility."""
        flags: List[str] = []

        # Collect per-source flags
        for source in sources:
            for flag in source.flags:
                if flag not in flags:
                    flags.append(flag)

        # Eligibility flags
        for reason in eligibility.disqualifying_reasons:
            flag = f"ELIGIBILITY_ISSUE: {reason}"
            if flag not in flags:
                flags.append(flag)

        for warning in eligibility.warnings:
            flag = f"ELIGIBILITY_WARNING: {warning}"
            if flag not in flags:
                flags.append(flag)

        # Overall commission ratio
        if commission_pct >= COMMISSION_SIGNIFICANCE_THRESHOLD_PCT:
            flag = (
                f"HIGH_COMMISSION_RATIO: Commission is {float(commission_pct):.1f}% "
                f"of total income (threshold: {float(COMMISSION_SIGNIFICANCE_THRESHOLD_PCT)}%)"
            )
            if flag not in flags:
                flags.append(flag)

        # Overall trend
        if overall_trend == TrendDirection.DECLINING:
            flag = "OVERALL_DECLINING_TREND: Commission income is declining across sources"
            if flag not in flags:
                flags.append(flag)

        return flags

    def _generate_recommendations(
        self,
        flags: List[str],
        eligibility: EligibilityResult,
    ) -> List[str]:
        """Generate LO-facing recommendations based on flags."""
        recs: List[str] = []

        flag_text = " ".join(flags)

        if "DECLINING_COMMISSION" in flag_text:
            recs.append(
                "Commission income is declining. Per Fannie Mae B3-3.1, use the "
                "lower of the 2-year average or the most recent 12 months. "
                "Request a written explanation from the borrower and verify "
                "current commission structure with the employer."
            )

        if "HIGH_COMMISSION_RATIO" in flag_text:
            recs.append(
                "Commission exceeds 25% of total income. Ensure 2-year history "
                "is documented with W-2s and tax returns. VOE should confirm "
                "the commission pay structure and probability of continuance."
            )

        if "SINGLE_YEAR_HISTORY" in flag_text or "INSUFFICIENT_DATA" in flag_text:
            recs.append(
                "Less than 2 years of commission history available. "
                "Request additional W-2s, 1099s, or tax returns. If borrower "
                "has 12+ months with current employer and income is stable, "
                "the 1-year exception may apply."
            )

        if "UBE_DEDUCTION" in flag_text:
            recs.append(
                "Unreimbursed business expenses exceed 25% of commission income. "
                "The monthly expense average has been deducted from qualifying "
                "income. Verify expenses with most recent tax returns and "
                "determine if the borrower has since changed to an expense "
                "reimbursement arrangement."
            )

        if "COMMISSION_DERIVED" in flag_text:
            recs.append(
                "Commission amount was derived from W-2 total minus base salary "
                "rather than being explicitly stated. Request VOE with commission "
                "breakdown or paystubs showing commission detail to confirm."
            )

        if "EMPLOYMENT_GAP" in flag_text or "ELIGIBILITY_ISSUE" in flag_text:
            recs.append(
                "Employment gap or eligibility concern detected. Obtain a "
                "letter of explanation from the borrower and VOE from both "
                "current and prior employers."
            )

        if eligibility.can_use_one_year_exception:
            recs.append(
                "1-year commission history exception applied. Document that "
                "income is stable/increasing and borrower has been with "
                "current employer for 12+ months. VOE required."
            )

        if "VOE_EARNINGS_USED" in flag_text:
            recs.append(
                "Prior year earnings from VOE were used due to lack of W-2 "
                "documentation. Obtain W-2s for the applicable tax years "
                "to strengthen the income calculation."
            )

        if not eligibility.is_eligible:
            recs.append(
                "Commission income does NOT currently qualify per agency "
                "guidelines. Review disqualifying reasons and determine if "
                "additional documentation can resolve the issues."
            )

        # Deduplicate
        seen: set = set()
        unique: List[str] = []
        for r in recs:
            key = r[:60]
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    def _generate_tasks(
        self,
        flags: List[str],
        eligibility: EligibilityResult,
        loan_id: int,
    ) -> List[Dict[str, Any]]:
        """Generate verification tasks for the LO queue."""
        tasks: List[Dict[str, Any]] = []
        flag_text = " ".join(flags)

        if "DECLINING_COMMISSION" in flag_text:
            tasks.append({
                "task_type": "review_commission_trend",
                "title": "Review declining commission income",
                "description": "Commission income shows a year-over-year decline. "
                               "Review trending data and determine appropriate calculation method.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Use the lower of 2-year average or most recent 12 months. "
                    "Request written explanation from borrower regarding the decline. "
                    "Consider whether commission should be excluded from qualifying income."
                ),
            })

        if "HIGH_COMMISSION_RATIO" in flag_text:
            tasks.append({
                "task_type": "verify_commission_history",
                "title": "Verify 2-year commission history",
                "description": "Commission exceeds 25% of total income. "
                               "2-year documentation required per Fannie Mae B3-3.1.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Obtain 2 years of W-2s showing commission earnings. "
                    "Request VOE confirming commission structure and probability of continuance."
                ),
            })

        if "SINGLE_YEAR_HISTORY" in flag_text:
            tasks.append({
                "task_type": "request_additional_docs",
                "title": "Obtain additional commission income documentation",
                "description": "Only 1 year of commission history available. "
                               "2-year history preferred.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Request prior year W-2 or 1099 forms. If unavailable, "
                    "document the 1-year exception criteria (stable income, "
                    "12+ months with employer)."
                ),
            })

        if "UBE_DEDUCTION" in flag_text:
            tasks.append({
                "task_type": "review_business_expenses",
                "title": "Review unreimbursed business expenses",
                "description": "Business expenses exceed 25% of commission income. "
                               "Deduction applied to qualifying income.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Verify expense amounts from most recent tax returns. "
                    "Check if borrower's expense reimbursement arrangement has changed."
                ),
            })

        if not eligibility.is_eligible:
            tasks.append({
                "task_type": "commission_eligibility_review",
                "title": "Commission income eligibility review required",
                "description": "Commission income does not currently meet agency "
                               "qualification requirements. Manual review needed.",
                "priority": "critical",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Review disqualifying reasons and determine if additional "
                    "documentation can resolve the issues. Consider restructuring "
                    "the income calculation to exclude commission if needed."
                ),
            })

        if "EMPLOYMENT_GAP" in flag_text or eligibility.has_employment_gap:
            tasks.append({
                "task_type": "verify_employment_continuity",
                "title": "Verify employment continuity for commission earner",
                "description": f"Employment gap of {eligibility.gap_days} days detected.",
                "priority": "high",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Obtain letter of explanation for the employment gap. "
                    "VOE from both current and prior employers may be required."
                ),
            })

        if "COMMISSION_DERIVED" in flag_text:
            tasks.append({
                "task_type": "request_voe",
                "title": "Obtain VOE with commission breakdown",
                "description": "Commission amount was derived (not explicitly documented). "
                               "VOE or detailed paystubs needed to confirm.",
                "priority": "medium",
                "loan_id": loan_id,
                "ai_recommendation": (
                    "Request VOE that itemizes base salary vs. commission earnings. "
                    "Alternatively, obtain paystubs showing commission detail."
                ),
            })

        return tasks

    # =========================================================================
    # INTERNAL: PERSISTENCE
    # =========================================================================

    def _save_calculation(self, result: CommissionIncomeResult) -> None:
        """
        Persist commission income calculation to income_calculations and
        income_sources tables.
        """
        try:
            now = datetime.now(timezone.utc)

            # Insert into income_calculations
            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        loan_id, borrower_id,
                        calculation_type, status,
                        total_qualifying_monthly_income,
                        total_qualifying_annual_income,
                        calculation_method,
                        ai_confidence_score,
                        ai_flags, ai_recommendations,
                        source_documents,
                        calculation_duration_ms,
                        created_at, updated_at
                    ) VALUES (
                        :loan_id, :borrower_id,
                        :calc_type, :status,
                        :total_monthly, :total_annual,
                        :method,
                        :confidence,
                        :flags, :recommendations,
                        :source_docs,
                        :duration,
                        :now, :now
                    )
                    RETURNING id
                """),
                {
                    "loan_id": result.loan_id,
                    "borrower_id": result.borrower_id,
                    "calc_type": "commission",
                    "status": "needs_review" if result.flags else "completed",
                    "total_monthly": float(result.total_qualifying_monthly),
                    "total_annual": float(result.total_qualifying_annual),
                    "method": result.primary_calculation_method.value,
                    "confidence": result.confidence,
                    "flags": json.dumps(result.flags),
                    "recommendations": json.dumps(result.recommendations),
                    "source_docs": json.dumps(
                        list({did for s in result.sources for did in s.source_doc_ids})
                    ),
                    "duration": result.duration_ms,
                    "now": now,
                },
            )
            db_calc_id = calc_row.fetchone()[0]

            # Insert income_sources for each commission source
            for idx, source in enumerate(result.sources):
                source_row = self.db.execute(
                    text("""
                        INSERT INTO income_sources (
                            calculation_id, borrower_id,
                            source_type, employer_name, position_title,
                            is_primary,
                            base_monthly_income, commission_monthly,
                            total_monthly_income, total_annual_income,
                            trending_direction,
                            year1_income, year2_income,
                            year_over_year_change_pct,
                            verification_status,
                            source_document_ids,
                            ai_confidence, ai_notes,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id, :borrower_id,
                            :source_type, :employer, :position,
                            :is_primary,
                            :base, :commission,
                            :total_monthly, :total_annual,
                            :trending,
                            :year1, :year2,
                            :yoy_pct,
                            :verification_status,
                            :doc_ids,
                            :confidence, :notes,
                            :now, :now
                        )
                        RETURNING id
                    """),
                    {
                        "calc_id": db_calc_id,
                        "borrower_id": result.borrower_id,
                        "source_type": source.commission_type.value,
                        "employer": source.employer_name,
                        "position": source.position_title,
                        "is_primary": idx == 0,
                        "base": float(source.qualifying_monthly_base),
                        "commission": float(source.qualifying_monthly_commission),
                        "total_monthly": float(source.qualifying_monthly_total),
                        "total_annual": float(source.qualifying_monthly_total * MONTHS_PER_YEAR),
                        "trending": source.trend_analysis.direction.value if source.trend_analysis else "unknown",
                        "year1": float(source.year1_commission) if source.year1_commission else None,
                        "year2": float(source.year2_commission) if source.year2_commission > ZERO else None,
                        "yoy_pct": float(source.trend_analysis.yoy_change_pct) if source.trend_analysis and source.trend_analysis.yoy_change_pct is not None else None,
                        "verification_status": "unverified",
                        "doc_ids": json.dumps(source.source_doc_ids),
                        "confidence": source.confidence,
                        "notes": source.notes,
                        "now": now,
                    },
                )
                source_id = source_row.fetchone()[0]

                # Insert verification tasks linked to this source
                for task in result.tasks_to_create:
                    self.db.execute(
                        text("""
                            INSERT INTO income_verification_tasks (
                                calculation_id, income_source_id,
                                loan_id, organization_id,
                                task_type, title, description,
                                priority, status,
                                ai_recommendation,
                                created_at, updated_at
                            ) VALUES (
                                :calc_id, :source_id,
                                :loan_id, :org_id,
                                :task_type, :title, :description,
                                :priority, 'open',
                                :ai_rec,
                                :now, :now
                            )
                        """),
                        {
                            "calc_id": db_calc_id,
                            "source_id": source_id,
                            "loan_id": result.loan_id,
                            "org_id": self.org_id,
                            "task_type": task["task_type"],
                            "title": task["title"],
                            "description": task["description"],
                            "priority": task["priority"],
                            "ai_rec": task.get("ai_recommendation", ""),
                            "now": now,
                        },
                    )

            self.db.commit()

            # Update result with DB ID
            result.calculation_id = str(db_calc_id)

            logger.info(
                "Commission income calculation saved: db_id=%s loan=%s borrower=%s "
                "org=%s monthly=%.2f sources=%d tasks=%d",
                db_calc_id, result.loan_id, result.borrower_id,
                self.org_id, float(result.total_qualifying_monthly),
                len(result.sources), len(result.tasks_to_create),
            )

        except Exception as e:
            self.db.rollback()
            logger.exception(
                "Failed to save commission income calculation: loan=%s borrower=%s org=%s: %s",
                result.loan_id, result.borrower_id, self.org_id, e,
            )
            result.flags.append(f"PERSISTENCE_ERROR: Failed to save calculation: {e}")

    # =========================================================================
    # INTERNAL: ORG VERIFICATION
    # =========================================================================

    def _verify_loan_org(self, loan_id: int) -> None:
        """Verify loan belongs to this organization."""
        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()

        if not row:
            raise ValueError(f"Loan {loan_id} not found.")

        if row.organization_id != self.org_id:
            from exceptions import TenantIsolationError
            raise TenantIsolationError(
                message=f"Loan {loan_id} belongs to org {row.organization_id}, not {self.org_id}",
                requesting_org_id=self.org_id,
                target_org_id=row.organization_id,
            )


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


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_commission_income_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> CommissionIncomeService:
    """
    Factory function returning a CommissionIncomeService for the given
    session and org context.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
        user_id: Optional authenticated user ID.

    Returns:
        A configured CommissionIncomeService instance.
    """
    return CommissionIncomeService(db=db, org_id=org_id, user_id=user_id)
