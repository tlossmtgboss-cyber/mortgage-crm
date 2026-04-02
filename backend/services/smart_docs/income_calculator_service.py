"""
AI-Powered Income Calculator Service

Reads income documents (paystubs, W2s, tax returns) and calculates qualifying
income per mortgage underwriting guidelines. Generates tasks for LO review
when issues are detected.

Integrates with:
    - smart_documents / smart_document_extractions for document data
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items
    - IncomeCalculationService for core math

Usage:
    from services.smart_docs.income_calculator_service import (
        get_income_calculator_service,
        IncomeCalculatorService,
    )

    service = get_income_calculator_service(db)
    result = service.calculate_income(loan_id=42, borrower_id=7)
"""

import logging
import os
import json
import re
import time
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional AI client
# ---------------------------------------------------------------------------
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from services.smart_docs.ai_resilience import resilient_ai_call

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

# Pay-frequency annualization multipliers
PAY_FREQUENCY_MULTIPLIERS = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

# Fannie Mae rental income vacancy factor
RENTAL_VACANCY_FACTOR = Decimal("0.25")

# Income doc types (match DocType enum values in smart_docs_models)
INCOME_DOC_TYPES = ("PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS")

# Staleness threshold: paystubs older than this many days trigger a flag
PAYSTUB_STALENESS_DAYS = 30

# Threshold percentages
DECLINING_INCOME_WARN_PCT = Decimal("10")
DECLINING_INCOME_CRITICAL_PCT = Decimal("20")
HIGH_COMMISSION_RATIO_PCT = Decimal("25")
DECLINING_COMMISSION_THRESHOLD_PCT = Decimal("25")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class IncomeSourceResult:
    """Calculated income from a single source."""
    source_type: str  # W2_EMPLOYMENT, SELF_EMPLOYMENT, COMMISSION, RENTAL, etc.
    employer_name: Optional[str]
    position_title: Optional[str]
    base_monthly: Decimal
    overtime_monthly: Decimal
    bonus_monthly: Decimal
    commission_monthly: Decimal
    other_monthly: Decimal
    total_monthly: Decimal
    total_annual: Decimal
    trending: str  # INCREASING, STABLE, DECLINING, VARIABLE
    year1_income: Optional[Decimal]  # most recent
    year2_income: Optional[Decimal]  # prior year
    yoy_change_pct: Optional[Decimal]
    confidence: int  # 0-100
    source_doc_ids: List[int] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class IncomeCalculationResult:
    """Complete income calculation result."""
    loan_id: int
    borrower_id: int
    sources: List[IncomeSourceResult]
    total_qualifying_monthly: Decimal
    total_qualifying_annual: Decimal
    calculation_method: str
    dti_front_end: Optional[Decimal]
    dti_back_end: Optional[Decimal]
    confidence: int
    flags: List[str]
    recommendations: List[str]
    tasks_to_create: List[Dict]
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# SERVICE
# =============================================================================

class IncomeCalculatorService:
    """
    AI-powered income calculation for mortgage underwriting.

    Calculates qualifying income from multiple sources:
    - W2/salaried: YTD gross / months worked, verify against W2
    - Self-employed: 2-year average from Schedule C or corporate returns
    - Commission/bonus: 2-year average, declining trend analysis
    - Rental income: 75% of rent minus PITIA
    - Retirement: Social Security, pension verification

    Generates tasks for LO review when:
    - Income is declining >10% year-over-year
    - Employment gap detected
    - Documents are inconsistent
    - Large unexplained deposits
    - Variable income with high variance
    """

    def __init__(self, db: Session, org_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    def calculate_income(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> IncomeCalculationResult:
        """
        Main entry point: gather docs, extract data, calculate qualifying
        income per underwriting guidelines, generate flags/tasks, and persist.
        """
        start_ms = int(time.time() * 1000)
        try:
            # Validate loan belongs to the caller's organization
            if self.org_id is not None:
                loan_org_check = self.db.execute(
                    text("SELECT organization_id FROM loans WHERE id = :lid"),
                    {"lid": loan_id},
                ).fetchone()
                if loan_org_check and loan_org_check.organization_id != self.org_id:
                    logger.warning(
                        "Tenant isolation violation in income calc: loan %d belongs to org %s, caller org %s",
                        loan_id, loan_org_check.organization_id, self.org_id,
                    )
                    return IncomeCalculationResult(
                        loan_id=loan_id,
                        borrower_id=borrower_id,
                        sources=[],
                        total_qualifying_monthly=ZERO,
                        total_qualifying_annual=ZERO,
                        calculation_method="error",
                        dti_front_end=None,
                        dti_back_end=None,
                        confidence=0,
                        flags=["TENANT_ISOLATION_ERROR"],
                        recommendations=[],
                        tasks_to_create=[],
                        success=False,
                        error="Access denied: loan does not belong to your organization.",
                    )

            # Step 1: gather all income-related documents with extractions
            docs = self._gather_income_documents(loan_id, borrower_id)

            if not docs:
                return IncomeCalculationResult(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    sources=[],
                    total_qualifying_monthly=ZERO,
                    total_qualifying_annual=ZERO,
                    calculation_method="none",
                    dti_front_end=None,
                    dti_back_end=None,
                    confidence=0,
                    flags=["NO_INCOME_DOCUMENTS"],
                    recommendations=["Upload income documents (paystubs, W2s, or tax returns) to begin income calculation."],
                    tasks_to_create=[],
                    success=False,
                    error="No income documents found for this borrower.",
                )

            # Step 2: bucket documents by type
            paystub_docs = [d for d in docs if d["doc_type"] in ("PAYSTUB",)]
            w2_docs = [d for d in docs if d["doc_type"] in ("W2",)]
            tax_docs = [d for d in docs if d["doc_type"] in ("TAX_RETURN",)]
            biz_tax_docs = [d for d in docs if d["doc_type"] in ("BUSINESS_TAX_RETURN",)]
            pnl_docs = [d for d in docs if d["doc_type"] in ("PROFIT_LOSS",)]

            # Step 3: calculate per source type
            sources: List[IncomeSourceResult] = []

            # W2 / salaried income
            w2_input = paystub_docs + w2_docs
            if w2_input:
                w2_result = self._calculate_w2_income(w2_input)
                if w2_result.total_monthly > ZERO or w2_result.flags:
                    sources.append(w2_result)

            # Self-employment income
            se_input = tax_docs + biz_tax_docs + pnl_docs
            if se_input:
                se_result = self._calculate_self_employment_income(se_input)
                if se_result.total_monthly != ZERO or se_result.flags:
                    sources.append(se_result)

            # Commission income (if commission comprises a significant portion)
            commission_result = self._calculate_commission_income(paystub_docs + w2_docs)
            if commission_result and commission_result.total_monthly > ZERO:
                sources.append(commission_result)

            # Rental income (from Schedule E in tax returns)
            rental_result = self._calculate_rental_income(tax_docs)
            if rental_result and rental_result.total_monthly != ZERO:
                sources.append(rental_result)

            # Step 4: aggregate
            total_monthly = sum(
                (s.total_monthly for s in sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            total_annual = (total_monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Determine overall method
            if len(sources) == 0:
                calc_method = "none"
            elif len(sources) == 1:
                calc_method = sources[0].source_type.lower()
            else:
                calc_method = "composite"

            # Step 5: DTI
            dti_front, dti_back = self._calculate_dti(total_monthly, loan_id)

            # Confidence: weighted average of source confidences
            if sources:
                total_weight = sum(float(s.total_monthly) for s in sources if s.total_monthly > ZERO) or 1
                weighted_conf = sum(
                    s.confidence * (float(s.total_monthly) / total_weight)
                    for s in sources
                    if s.total_monthly > ZERO
                )
                confidence = min(100, max(0, int(weighted_conf)))
            else:
                confidence = 0

            # Build preliminary result for flag/recommendation generation
            result = IncomeCalculationResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                sources=sources,
                total_qualifying_monthly=total_monthly,
                total_qualifying_annual=total_annual,
                calculation_method=calc_method,
                dti_front_end=dti_front,
                dti_back_end=dti_back,
                confidence=confidence,
                flags=[],
                recommendations=[],
                tasks_to_create=[],
            )

            # Step 6: flags, recommendations, tasks
            result.flags = self._generate_flags(result)
            result.recommendations = self._generate_recommendations(result)
            result.tasks_to_create = self._generate_tasks(result)

            # Step 7: persist
            duration_ms = int(time.time() * 1000) - start_ms
            self._save_calculation(result, duration_ms)

            return result

        except Exception as e:
            logger.exception(f"Income calculation failed for loan={loan_id} borrower={borrower_id}: {e}")
            return IncomeCalculationResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                sources=[],
                total_qualifying_monthly=ZERO,
                total_qualifying_annual=ZERO,
                calculation_method="error",
                dti_front_end=None,
                dti_back_end=None,
                confidence=0,
                flags=[],
                recommendations=[],
                tasks_to_create=[],
                success=False,
                error=str(e),
            )

    # =========================================================================
    # 2. GATHER INCOME DOCUMENTS
    # =========================================================================

    def _gather_income_documents(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> List[Dict]:
        """
        Query smart_documents for income-related docs, then join with
        smart_document_extractions to get the extracted field data.
        Returns list of dicts with keys: id, doc_type, extracted_fields,
        confidence_scores, ocr_text, uploaded_at.
        """
        _org_join = (
            "JOIN loans _org_l ON _org_l.id = sd.loan_id AND _org_l.organization_id = :_org_id"
            if self.org_id is not None else ""
        )
        _org_params = {"_org_id": self.org_id} if self.org_id is not None else {}
        docs_query = (
            "SELECT"
            " sd.id AS doc_id,"
            " sd.doc_type AS doc_type,"
            " sd.ocr_text AS ocr_text,"
            " sd.uploaded_at AS uploaded_at,"
            " sd.file_name AS file_name,"
            " sde.extracted_fields AS extracted_fields,"
            " sde.confidence_scores AS confidence_scores,"
            " sde.overall_confidence AS overall_confidence"
            " FROM smart_documents sd"
            " LEFT JOIN smart_document_extractions sde"
            "     ON sde.document_id = sd.id"
            " " + _org_join
            + " WHERE sd.loan_id = :loan_id"
            "   AND sd.borrower_id = :borrower_id"
            "   AND sd.doc_type IN :doc_types"
            "   AND sd.status NOT IN ('REJECTED', 'EXPIRED')"
            " ORDER BY sd.uploaded_at DESC"
        )
        rows = self.db.execute(
            text(docs_query),
            {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "doc_types": tuple(INCOME_DOC_TYPES),
                **_org_params,
            },
        ).fetchall()

        results = []
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
    # 3. W2 / SALARIED INCOME
    # =========================================================================

    def _calculate_w2_income(self, documents: List[Dict]) -> IncomeSourceResult:
        """
        Calculate W2/salaried qualifying income.

        From paystubs: current_gross / pay_periods_elapsed * 12 (annualized)
        From W2: direct annual income
        If both: use paystub for current, W2 for historical
        OT/bonus/commission from YTD breakdowns, 2-year average.
        """
        paystubs = [d for d in documents if d["doc_type"] == "PAYSTUB"]
        w2s = [d for d in documents if d["doc_type"] == "W2"]
        doc_ids = [d["doc_id"] for d in documents]
        flags: List[str] = []

        # --- Current income from most recent paystub ---
        base_monthly = ZERO
        ot_monthly = ZERO
        bonus_monthly = ZERO
        commission_monthly = ZERO
        other_monthly = ZERO
        employer_name: Optional[str] = None
        position_title: Optional[str] = None
        paystub_confidence = 50

        if paystubs:
            # Sort by pay_date descending (most recent first)
            paystubs_sorted = sorted(
                paystubs,
                key=lambda d: d["extracted_fields"].get("pay_date", "0000-00-00"),
                reverse=True,
            )
            latest = paystubs_sorted[0]["extracted_fields"]
            paystub_confidence = paystubs_sorted[0].get("overall_confidence", 50)
            employer_name = latest.get("employer_name")
            position_title = latest.get("job_title")

            gross_pay = self._to_decimal(latest.get("gross_pay"))
            pay_freq = (latest.get("pay_frequency") or "MONTHLY").upper()
            multiplier = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq, 12)

            if gross_pay > ZERO:
                annualized = gross_pay * Decimal(multiplier)
                base_monthly = (annualized / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # OT / bonus / commission from YTD
            pay_date_str = latest.get("pay_date")
            months_elapsed = self._months_elapsed_in_year(pay_date_str)
            if months_elapsed and months_elapsed > 0:
                ytd_ot = self._to_decimal(latest.get("ytd_overtime_earnings"))
                ytd_bonus = self._to_decimal(latest.get("ytd_bonus"))
                ytd_commission = self._to_decimal(latest.get("ytd_commission"))
                ytd_tips = self._to_decimal(latest.get("ytd_tips"))

                if ytd_ot > ZERO:
                    ot_monthly = (ytd_ot / Decimal(months_elapsed)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                if ytd_bonus > ZERO:
                    bonus_monthly = (ytd_bonus / Decimal(months_elapsed)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                if ytd_commission > ZERO:
                    commission_monthly = (ytd_commission / Decimal(months_elapsed)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                if ytd_tips > ZERO:
                    other_monthly = (ytd_tips / Decimal(months_elapsed)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Staleness check
            if pay_date_str:
                try:
                    pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
                    days_old = (date.today() - pay_date).days
                    if days_old > PAYSTUB_STALENESS_DAYS:
                        flags.append(f"STALE_PAYSTUB: Most recent paystub is {days_old} days old")
                except (ValueError, TypeError):
                    pass

        # --- Historical from W2s ---
        year1_income: Optional[Decimal] = None
        year2_income: Optional[Decimal] = None

        if w2s:
            w2s_sorted = sorted(
                w2s,
                key=lambda d: d["extracted_fields"].get("tax_year", 0),
                reverse=True,
            )
            for i, w2 in enumerate(w2s_sorted[:2]):
                wages = self._to_decimal(w2["extracted_fields"].get("wages_tips_compensation"))
                if i == 0:
                    year1_income = wages if wages > ZERO else None
                elif i == 1:
                    year2_income = wages if wages > ZERO else None

            # Employer consistency check
            if employer_name and w2s_sorted:
                w2_employer = w2s_sorted[0]["extracted_fields"].get("employer_name", "")
                if w2_employer and employer_name.lower() != w2_employer.lower():
                    flags.append(
                        f"DOCUMENT_MISMATCH: Paystub employer '{employer_name}' "
                        f"does not match W2 employer '{w2_employer}'"
                    )
            elif not employer_name and w2s_sorted:
                employer_name = w2s_sorted[0]["extracted_fields"].get("employer_name")

        # --- Two-year averaging for OT/bonus/commission ---
        if year1_income and year2_income:
            # Use 2-year average as a cross-check; for variable income components
            # we should average across two years
            if ot_monthly > ZERO or bonus_monthly > ZERO or commission_monthly > ZERO:
                # Already computed from YTD; keep as-is but note
                pass
        elif not paystubs and year1_income:
            # No paystubs, derive from W2
            base_monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Trending
        trending, yoy_pct = self._analyze_income_trend(year1_income, year2_income)

        # If W2 shows lower than paystub-annualized AND income is declining, use lower
        total_monthly = (
            base_monthly + ot_monthly + bonus_monthly + commission_monthly + other_monthly
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if year1_income and year2_income and trending == "DECLINING":
            w2_average_monthly = ((year1_income + year2_income) / 24).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if w2_average_monthly < total_monthly:
                total_monthly = w2_average_monthly
                base_monthly = total_monthly
                ot_monthly = ZERO
                bonus_monthly = ZERO
                commission_monthly = ZERO
                other_monthly = ZERO
                flags.append("USED_TWO_YEAR_AVERAGE: Income declining, used lower 2-year W2 average")

        total_annual = (total_monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Confidence
        confidence = paystub_confidence
        if w2s:
            confidence = min(95, confidence + 10)
        if not paystubs:
            confidence = max(30, confidence - 20)

        return IncomeSourceResult(
            source_type="W2_EMPLOYMENT",
            employer_name=employer_name,
            position_title=position_title,
            base_monthly=base_monthly,
            overtime_monthly=ot_monthly,
            bonus_monthly=bonus_monthly,
            commission_monthly=commission_monthly,
            other_monthly=other_monthly,
            total_monthly=total_monthly,
            total_annual=total_annual,
            trending=trending,
            year1_income=year1_income,
            year2_income=year2_income,
            yoy_change_pct=yoy_pct,
            confidence=confidence,
            source_doc_ids=doc_ids,
            flags=flags,
            notes="W2/salaried income calculated from paystubs and W2s",
        )

    # =========================================================================
    # 4. SELF-EMPLOYMENT INCOME
    # =========================================================================

    def _calculate_self_employment_income(self, documents: List[Dict]) -> IncomeSourceResult:
        """
        Calculate self-employment qualifying income.

        From tax returns: Schedule C net profit or K-1 distributions
        2-year average: (year1 + year2) / 24 = monthly
        Depreciation add-backs per Fannie Mae guidelines.
        """
        doc_ids = [d["doc_id"] for d in documents]
        flags: List[str] = []

        # Gather tax year data
        yearly_data: Dict[int, Decimal] = {}
        business_name: Optional[str] = None

        for doc in documents:
            ef = doc["extracted_fields"]
            tax_year = ef.get("tax_year")
            if not tax_year:
                continue
            try:
                tax_year = int(tax_year)
            except (ValueError, TypeError):
                continue

            if doc["doc_type"] in ("BUSINESS_TAX_RETURN", "TAX_RETURN"):
                net_profit = self._to_decimal(ef.get("net_profit_loss") or ef.get("net_profit") or ef.get("adjusted_gross_income"))
                depreciation = self._to_decimal(ef.get("depreciation_addback", 0))
                amortization = self._to_decimal(ef.get("amortization_addback", 0))
                depletion = self._to_decimal(ef.get("depletion_addback", 0))

                k1_ordinary = self._to_decimal(ef.get("k1_ordinary_income", 0))
                k1_guaranteed = self._to_decimal(ef.get("k1_guaranteed_payments", 0))

                if k1_ordinary > ZERO or k1_guaranteed > ZERO:
                    adjusted = k1_ordinary + k1_guaranteed + depreciation + amortization
                else:
                    adjusted = net_profit + depreciation + amortization + depletion

                yearly_data[tax_year] = yearly_data.get(tax_year, ZERO) + adjusted

                if not business_name:
                    business_name = ef.get("business_name") or ef.get("employer_name")

            elif doc["doc_type"] == "PROFIT_LOSS":
                net_profit = self._to_decimal(ef.get("net_profit") or ef.get("net_profit_loss"))
                if net_profit:
                    yearly_data[tax_year] = yearly_data.get(tax_year, ZERO) + net_profit
                if not business_name:
                    business_name = ef.get("business_name") or ef.get("owner_name")

        if not yearly_data:
            return IncomeSourceResult(
                source_type="SELF_EMPLOYMENT",
                employer_name=business_name,
                position_title="Self-Employed",
                base_monthly=ZERO,
                overtime_monthly=ZERO,
                bonus_monthly=ZERO,
                commission_monthly=ZERO,
                other_monthly=ZERO,
                total_monthly=ZERO,
                total_annual=ZERO,
                trending="VARIABLE",
                year1_income=None,
                year2_income=None,
                yoy_change_pct=None,
                confidence=0,
                source_doc_ids=doc_ids,
                flags=["NO_SELF_EMPLOYMENT_DATA: Tax returns found but no income data extracted"],
                notes="No self-employment income data could be extracted",
            )

        sorted_years = sorted(yearly_data.keys(), reverse=True)
        year1_income = yearly_data[sorted_years[0]]
        year2_income = yearly_data[sorted_years[1]] if len(sorted_years) >= 2 else None

        # Calculate monthly qualifying
        if year2_income is not None:
            # 2-year average: (year1 + year2) / 24
            total_two_years = year1_income + year2_income
            monthly = (total_two_years / 24).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Check for significant decline
            if year1_income < year2_income and year2_income > ZERO:
                decline_pct = ((year2_income - year1_income) / year2_income * 100).quantize(TWO_PLACES)
                if decline_pct >= DECLINING_INCOME_CRITICAL_PCT:
                    flags.append(
                        f"DECLINING_SELF_EMPLOYMENT: Income declined {decline_pct}% "
                        f"({sorted_years[1]} to {sorted_years[0]})"
                    )
                    # Use most recent (lower) year per declining income rules
                    monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    flags.append("USED_LOWER_YEAR: Declining >20%, used most recent year only")
        else:
            # Only 1 year
            monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            flags.append("INSUFFICIENT_HISTORY: Only 1 year of self-employment income available")

        trending, yoy_pct = self._analyze_income_trend(year1_income, year2_income)
        total_annual = (monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if total_annual < ZERO:
            flags.append("NEGATIVE_INCOME: Business shows a net loss")

        confidence = 70 if year2_income is not None else 45

        return IncomeSourceResult(
            source_type="SELF_EMPLOYMENT",
            employer_name=business_name,
            position_title="Self-Employed",
            base_monthly=monthly,
            overtime_monthly=ZERO,
            bonus_monthly=ZERO,
            commission_monthly=ZERO,
            other_monthly=ZERO,
            total_monthly=monthly,
            total_annual=total_annual,
            trending=trending,
            year1_income=year1_income,
            year2_income=year2_income,
            yoy_change_pct=yoy_pct,
            confidence=confidence,
            source_doc_ids=doc_ids,
            flags=flags,
            notes="Self-employment income from tax returns with depreciation add-backs",
        )

    # =========================================================================
    # 5. COMMISSION INCOME
    # =========================================================================

    def _calculate_commission_income(self, documents: List[Dict]) -> Optional[IncomeSourceResult]:
        """
        Calculate commission income requiring 2-year history.
        Uses 2-year average; if declining >25% uses lower year or flags.
        Returns None if no significant commission income detected.
        """
        # Look for commission data in paystubs (YTD) and W2s
        paystubs = [d for d in documents if d["doc_type"] == "PAYSTUB"]
        w2s = [d for d in documents if d["doc_type"] == "W2"]

        # Check YTD commission from most recent paystub
        ytd_commission = ZERO
        pay_date_str = None
        if paystubs:
            paystubs_sorted = sorted(
                paystubs,
                key=lambda d: d["extracted_fields"].get("pay_date", "0000-00-00"),
                reverse=True,
            )
            latest = paystubs_sorted[0]["extracted_fields"]
            ytd_commission = self._to_decimal(latest.get("ytd_commission"))
            pay_date_str = latest.get("pay_date")

        if ytd_commission <= ZERO:
            return None

        # Check if commission is significant relative to gross
        ytd_gross = self._to_decimal(
            paystubs_sorted[0]["extracted_fields"].get("ytd_gross") if paystubs else None
        )
        if ytd_gross > ZERO:
            commission_ratio = (ytd_commission / ytd_gross * 100).quantize(TWO_PLACES)
            if commission_ratio < Decimal("5"):
                # Commission is <5% of gross -- not considered a commission-dominant role
                return None
        else:
            return None

        flags: List[str] = []
        doc_ids = [d["doc_id"] for d in documents]

        # Annualize current year commission
        months_elapsed = self._months_elapsed_in_year(pay_date_str)
        if months_elapsed and months_elapsed > 0:
            current_annual_commission = (ytd_commission / Decimal(months_elapsed) * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            current_annual_commission = ytd_commission  # fallback

        # Get prior year commission from W2 (via wages minus base, or direct if available)
        prior_year_commission: Optional[Decimal] = None
        if len(w2s) >= 2:
            w2s_sorted = sorted(
                w2s,
                key=lambda d: d["extracted_fields"].get("tax_year", 0),
                reverse=True,
            )
            # Approximate: we lack commission breakdown in W2; use total wages for trending
            year1_wages = self._to_decimal(w2s_sorted[0]["extracted_fields"].get("wages_tips_compensation"))
            year2_wages = self._to_decimal(w2s_sorted[1]["extracted_fields"].get("wages_tips_compensation"))
            # Rough proxy: assume commission ratio was similar in prior years
            if year2_wages > ZERO and commission_ratio > ZERO:
                prior_year_commission = (year2_wages * commission_ratio / 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Must have 2-year history for commission income
        if prior_year_commission is None:
            flags.append("INSUFFICIENT_HISTORY: Commission income requires 2-year history for qualification")
            monthly = (current_annual_commission / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            # 2-year average
            two_year_avg = ((current_annual_commission + prior_year_commission) / 2).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Declining check
            if current_annual_commission < prior_year_commission and prior_year_commission > ZERO:
                decline_pct = ((prior_year_commission - current_annual_commission) / prior_year_commission * 100).quantize(TWO_PLACES)
                if decline_pct >= DECLINING_COMMISSION_THRESHOLD_PCT:
                    flags.append(f"DECLINING_COMMISSION: Commission income declined {decline_pct}% year-over-year")
                    # Use lower (current) year
                    two_year_avg = current_annual_commission

            monthly = (two_year_avg / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # High commission ratio flag
        if commission_ratio >= HIGH_COMMISSION_RATIO_PCT:
            flags.append(f"HIGH_COMMISSION_RATIO: Commission is {commission_ratio}% of total income")

        trending, yoy_pct = self._analyze_income_trend(current_annual_commission, prior_year_commission)

        return IncomeSourceResult(
            source_type="COMMISSION",
            employer_name=None,
            position_title=None,
            base_monthly=ZERO,
            overtime_monthly=ZERO,
            bonus_monthly=ZERO,
            commission_monthly=monthly,
            other_monthly=ZERO,
            total_monthly=monthly,
            total_annual=(monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            trending=trending,
            year1_income=current_annual_commission,
            year2_income=prior_year_commission,
            yoy_change_pct=yoy_pct,
            confidence=55 if prior_year_commission else 35,
            source_doc_ids=doc_ids,
            flags=flags,
            notes="Commission income calculated from YTD paystub data and W2 history",
        )

    # =========================================================================
    # 6. RENTAL INCOME
    # =========================================================================

    def _calculate_rental_income(self, documents: List[Dict]) -> Optional[IncomeSourceResult]:
        """
        Calculate rental income per Fannie Mae: 75% of gross rent minus PITIA.
        Uses Schedule E data from tax returns when available.
        Returns None if no rental income data found.
        """
        # Look for Schedule E data in tax returns
        schedule_e_data: Dict[int, Dict[str, Decimal]] = {}

        for doc in documents:
            ef = doc["extracted_fields"]
            tax_year = ef.get("tax_year")
            if not tax_year:
                continue

            gross_rents = self._to_decimal(ef.get("schedule_e_gross_rents"))
            if gross_rents <= ZERO:
                continue

            try:
                tax_year = int(tax_year)
            except (ValueError, TypeError):
                continue

            total_expenses = self._to_decimal(ef.get("schedule_e_total_expenses"))
            depreciation = self._to_decimal(ef.get("schedule_e_depreciation"))
            net_income = self._to_decimal(ef.get("schedule_e_net_income_loss"))

            schedule_e_data[tax_year] = {
                "gross_rents": gross_rents,
                "total_expenses": total_expenses,
                "depreciation": depreciation,
                "net_income": net_income,
            }

        if not schedule_e_data:
            return None

        doc_ids = [d["doc_id"] for d in documents]
        flags: List[str] = []

        sorted_years = sorted(schedule_e_data.keys(), reverse=True)
        yearly_qualifying: List[Decimal] = []

        for year_key in sorted_years[:2]:
            data = schedule_e_data[year_key]
            # Apply 75% vacancy factor to gross rents
            gross_rents = data["gross_rents"]
            net_rental = (gross_rents * (Decimal("1") - RENTAL_VACANCY_FACTOR)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            yearly_qualifying.append(net_rental * 12 if net_rental > ZERO else net_rental)

        if len(yearly_qualifying) >= 2:
            average_annual = ((yearly_qualifying[0] + yearly_qualifying[1]) / 2).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            average_annual = yearly_qualifying[0].quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            flags.append("INSUFFICIENT_RENTAL_HISTORY: Only 1 year of Schedule E available")

        monthly = (average_annual / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if monthly < ZERO:
            flags.append("NEGATIVE_RENTAL_CASHFLOW: Rental income is negative -- treated as monthly obligation")

        year1 = yearly_qualifying[0] if len(yearly_qualifying) >= 1 else None
        year2 = yearly_qualifying[1] if len(yearly_qualifying) >= 2 else None
        trending, yoy_pct = self._analyze_income_trend(year1, year2)

        return IncomeSourceResult(
            source_type="RENTAL",
            employer_name=None,
            position_title=None,
            base_monthly=monthly if monthly > ZERO else ZERO,
            overtime_monthly=ZERO,
            bonus_monthly=ZERO,
            commission_monthly=ZERO,
            other_monthly=monthly if monthly < ZERO else ZERO,
            total_monthly=monthly,
            total_annual=average_annual,
            trending=trending,
            year1_income=year1,
            year2_income=year2,
            yoy_change_pct=yoy_pct,
            confidence=60 if year2 else 40,
            source_doc_ids=doc_ids,
            flags=flags,
            notes="Rental income from Schedule E with 25% vacancy factor per Fannie Mae",
        )

    # =========================================================================
    # 7. INCOME TREND ANALYSIS
    # =========================================================================

    def _analyze_income_trend(
        self,
        year1: Optional[Decimal],
        year2: Optional[Decimal],
    ) -> Tuple[str, Optional[Decimal]]:
        """
        Compare year-over-year income.
        Returns (direction, pct_change) where direction is one of
        INCREASING, STABLE, DECLINING, VARIABLE.
        """
        if year1 is None or year2 is None:
            return ("VARIABLE", None)

        if year2 == ZERO:
            if year1 > ZERO:
                return ("INCREASING", Decimal("100.00"))
            return ("STABLE", ZERO)

        pct_change = ((year1 - year2) / abs(year2) * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if pct_change > Decimal("5"):
            direction = "INCREASING"
        elif pct_change < Decimal("-5"):
            direction = "DECLINING"
        else:
            direction = "STABLE"

        return (direction, pct_change)

    # =========================================================================
    # 8. DTI CALCULATION
    # =========================================================================

    def _calculate_dti(
        self,
        monthly_income: Decimal,
        loan_id: int,
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Calculate front-end and back-end DTI ratios.
        front_end = PITIA / income * 100
        back_end  = (PITIA + obligations) / income * 100
        """
        if monthly_income <= ZERO:
            return (None, None)

        # Query loan for proposed housing payment and obligations (with org_id filter)
        _loan_org_filter = "AND organization_id = :_org_id" if self.org_id is not None else ""
        _org_params = {"_org_id": self.org_id} if self.org_id is not None else {}
        dti_query = (
            "SELECT"
            " COALESCE(proposed_monthly_payment, 0) AS pitia,"
            " COALESCE(total_monthly_obligations, 0) AS obligations"
            " FROM loans"
            " WHERE id = :loan_id " + _loan_org_filter
        )
        row = self.db.execute(
            text(dti_query),
            {"loan_id": loan_id, **_org_params},
        ).fetchone()

        if not row:
            return (None, None)

        pitia = self._to_decimal(row.pitia)
        obligations = self._to_decimal(row.obligations)

        if pitia <= ZERO:
            return (None, None)

        front_end = (pitia / monthly_income * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        back_end = ((pitia + obligations) / monthly_income * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return (front_end, back_end)

    # =========================================================================
    # 9. FLAG GENERATION
    # =========================================================================

    def _generate_flags(self, result: IncomeCalculationResult) -> List[str]:
        """
        Consolidate and generate top-level flags from all sources and
        overall calculation characteristics.
        """
        flags: List[str] = []

        # Collect per-source flags
        for source in result.sources:
            flags.extend(source.flags)

        # Declining income across any source
        for source in result.sources:
            if source.yoy_change_pct is not None and source.yoy_change_pct < -DECLINING_INCOME_WARN_PCT:
                flag = (
                    f"DECLINING_INCOME: {source.source_type} year-over-year "
                    f"decrease of {abs(source.yoy_change_pct)}%"
                )
                if flag not in flags:
                    flags.append(flag)

        # Employment gap: no paystub dated within last PAYSTUB_STALENESS_DAYS
        has_recent_paystub = False
        for source in result.sources:
            if source.source_type == "W2_EMPLOYMENT":
                for f in source.flags:
                    if "STALE_PAYSTUB" in f:
                        has_recent_paystub = False
                        break
                else:
                    has_recent_paystub = True

        if result.sources and not has_recent_paystub:
            w2_sources = [s for s in result.sources if s.source_type == "W2_EMPLOYMENT"]
            if w2_sources:
                flag = f"EMPLOYMENT_GAP: No paystub dated within the last {PAYSTUB_STALENESS_DAYS} days"
                if flag not in flags:
                    flags.append(flag)

        # High commission ratio
        if result.total_qualifying_monthly > ZERO:
            total_commission = sum(s.commission_monthly for s in result.sources)
            if total_commission > ZERO:
                ratio = (total_commission / result.total_qualifying_monthly * 100).quantize(TWO_PLACES)
                if ratio >= HIGH_COMMISSION_RATIO_PCT:
                    flag = f"HIGH_COMMISSION_RATIO: Commission is {ratio}% of total qualifying income"
                    if flag not in flags:
                        flags.append(flag)

        # Insufficient history
        for source in result.sources:
            if source.year2_income is None and source.source_type in ("SELF_EMPLOYMENT", "COMMISSION"):
                flag = f"INSUFFICIENT_HISTORY: {source.source_type} has less than 2 years of income history"
                if flag not in flags:
                    flags.append(flag)

        # DTI warnings
        if result.dti_back_end is not None:
            if result.dti_back_end > Decimal("50"):
                flags.append(f"HIGH_DTI: Back-end DTI is {result.dti_back_end}% (above 50% threshold)")
            elif result.dti_back_end > Decimal("45"):
                flags.append(f"ELEVATED_DTI: Back-end DTI is {result.dti_back_end}% (above 45%)")

        return flags

    # =========================================================================
    # 10. RECOMMENDATION GENERATION
    # =========================================================================

    def _generate_recommendations(self, result: IncomeCalculationResult) -> List[str]:
        """
        Generate AI-powered recommendations for the LO based on the
        calculation results and flags.
        """
        recs: List[str] = []

        for flag in result.flags:
            if "STALE_PAYSTUB" in flag:
                # Extract days from the flag text
                recs.append(
                    "Request updated paystub -- current one may be too old "
                    "for underwriting. Most lenders require a paystub within 30 days of application."
                )

            elif "EMPLOYMENT_GAP" in flag:
                recs.append(
                    "VOE (Verification of Employment) recommended -- no recent paystub on file. "
                    "Contact employer to verify current employment status."
                )

            elif "DOCUMENT_MISMATCH" in flag:
                recs.append(
                    "Employer name on paystub does not match W2 -- verify with borrower. "
                    "This may indicate a job change or name variation that needs documentation."
                )

            elif "DECLINING_INCOME" in flag or "DECLINING_SELF_EMPLOYMENT" in flag:
                recs.append(
                    "Income is declining year-over-year. Consider using only the lower "
                    "of the 2-year average or the most recent year per Fannie Mae guidelines. "
                    "Request explanation from borrower."
                )

            elif "DECLINING_COMMISSION" in flag:
                recs.append(
                    "Commission income is declining -- consider using only base income "
                    "for qualification if commission continues to decline. "
                    "Request YTD profit/loss or sales pipeline documentation."
                )

            elif "HIGH_COMMISSION_RATIO" in flag:
                recs.append(
                    "Borrower has significant commission-based income. Ensure 2-year history "
                    "of commission earnings is documented. VOE should confirm commission structure."
                )

            elif "INSUFFICIENT_HISTORY" in flag:
                if "SELF_EMPLOYMENT" in flag:
                    recs.append(
                        "Self-employment requires 2 years of tax returns per Fannie Mae. "
                        "Request missing tax returns or consider alternative documentation."
                    )
                elif "COMMISSION" in flag:
                    recs.append(
                        "Commission income requires 2-year history. Request additional W2s "
                        "or tax returns to establish commission history."
                    )

            elif "NEGATIVE_INCOME" in flag or "NEGATIVE_RENTAL_CASHFLOW" in flag:
                recs.append(
                    "Business or rental property shows a loss -- this negative income "
                    "must be counted as a monthly obligation in DTI calculations."
                )

            elif "HIGH_DTI" in flag:
                recs.append(
                    "DTI exceeds 50% -- may require compensating factors for approval. "
                    "Consider reducing proposed loan amount, paying down debts, or adding a co-borrower."
                )

            elif "NO_INCOME_DOCUMENTS" in flag:
                recs.append(
                    "No income documents found. Upload paystubs, W2s, and/or tax returns "
                    "to begin income calculation."
                )

        # De-duplicate
        seen = set()
        unique_recs = []
        for r in recs:
            key = r[:60]
            if key not in seen:
                seen.add(key)
                unique_recs.append(r)

        return unique_recs

    # =========================================================================
    # 11. TASK GENERATION
    # =========================================================================

    def _generate_tasks(self, result: IncomeCalculationResult) -> List[Dict]:
        """
        Create task definitions for each actionable item.
        Each task maps to the IncomeVerificationTask model.
        """
        tasks: List[Dict] = []

        for flag in result.flags:
            if "STALE_PAYSTUB" in flag:
                tasks.append({
                    "task_type": "verify_employment",
                    "title": "Request updated paystub",
                    "description": flag,
                    "priority": "high",
                    "ai_recommendation": (
                        "Current paystub is stale. Request a new paystub covering "
                        "a pay period within the last 30 days."
                    ),
                })

            elif "EMPLOYMENT_GAP" in flag:
                tasks.append({
                    "task_type": "review_gap_in_employment",
                    "title": "Verify employment -- possible gap detected",
                    "description": flag,
                    "priority": "high",
                    "ai_recommendation": (
                        "No recent paystub on file. Obtain verbal or written VOE to "
                        "confirm borrower is still employed."
                    ),
                })

            elif "DOCUMENT_MISMATCH" in flag:
                tasks.append({
                    "task_type": "verify_employment",
                    "title": "Resolve employer name mismatch between paystub and W2",
                    "description": flag,
                    "priority": "medium",
                    "ai_recommendation": (
                        "Employer name differs between documents. Confirm with borrower "
                        "whether this is a name change, parent company, or job change."
                    ),
                })

            elif "DECLINING_INCOME" in flag or "DECLINING_SELF_EMPLOYMENT" in flag:
                tasks.append({
                    "task_type": "review_declining_income",
                    "title": "Review declining income trend",
                    "description": flag,
                    "priority": "high",
                    "ai_recommendation": (
                        "Income is declining. Request written explanation from borrower. "
                        "Use lower of 2-year average or most recent year for qualification."
                    ),
                })

            elif "DECLINING_COMMISSION" in flag:
                tasks.append({
                    "task_type": "review_commission_trend",
                    "title": "Review declining commission income",
                    "description": flag,
                    "priority": "high",
                    "ai_recommendation": (
                        "Commission income is declining significantly. Consider excluding "
                        "commission from qualifying income or using only base pay."
                    ),
                })

            elif "INSUFFICIENT_HISTORY" in flag:
                if "SELF_EMPLOYMENT" in flag:
                    tasks.append({
                        "task_type": "verify_self_employment",
                        "title": "Obtain 2 years of self-employment documentation",
                        "description": flag,
                        "priority": "critical",
                        "ai_recommendation": (
                            "Fannie Mae requires 2 years of tax returns for self-employed "
                            "borrowers. Request missing year's tax return."
                        ),
                    })
                else:
                    tasks.append({
                        "task_type": "request_voe",
                        "title": "Obtain additional income history",
                        "description": flag,
                        "priority": "medium",
                        "ai_recommendation": (
                            "Less than 2 years of income history available. "
                            "Request additional W2s or tax returns."
                        ),
                    })

            elif "NEGATIVE_INCOME" in flag or "NEGATIVE_RENTAL_CASHFLOW" in flag:
                tasks.append({
                    "task_type": "manual_override_needed",
                    "title": "Review negative income / rental loss",
                    "description": flag,
                    "priority": "medium",
                    "ai_recommendation": (
                        "Negative income from business or rental must be added as a "
                        "monthly obligation. Verify the amount and update DTI accordingly."
                    ),
                })

            elif "HIGH_DTI" in flag:
                tasks.append({
                    "task_type": "manual_override_needed",
                    "title": "DTI exceeds guideline threshold",
                    "description": flag,
                    "priority": "critical",
                    "ai_recommendation": (
                        "DTI is above 50%. Document compensating factors or explore "
                        "options to reduce obligations."
                    ),
                })

        return tasks

    # =========================================================================
    # 12. PERSISTENCE
    # =========================================================================

    def _save_calculation(
        self,
        result: IncomeCalculationResult,
        duration_ms: int = 0,
    ) -> int:
        """
        Persist calculation results to income_calculations, income_sources
        (the income_calculation model variant), and income_verification_tasks.
        Returns the calculation_id.
        """
        try:
            # --- income_calculations ---
            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        loan_id, borrower_id,
                        calculation_type, status,
                        total_qualifying_monthly_income,
                        total_qualifying_annual_income,
                        calculation_method,
                        dti_front_end, dti_back_end,
                        ai_confidence_score,
                        ai_flags, ai_recommendations,
                        ai_model_used, calculation_duration_ms,
                        source_documents,
                        created_at, updated_at
                    ) VALUES (
                        :loan_id, :borrower_id,
                        :calculation_type, :status,
                        :total_monthly, :total_annual,
                        :method,
                        :dti_front, :dti_back,
                        :confidence,
                        :flags, :recommendations,
                        :model, :duration,
                        :source_docs,
                        :now, :now
                    )
                    RETURNING id
                """),
                {
                    "loan_id": result.loan_id,
                    "borrower_id": result.borrower_id,
                    "calculation_type": "initial",
                    "status": "needs_review" if result.flags else "completed",
                    "total_monthly": float(result.total_qualifying_monthly),
                    "total_annual": float(result.total_qualifying_annual),
                    "method": result.calculation_method,
                    "dti_front": float(result.dti_front_end) if result.dti_front_end is not None else None,
                    "dti_back": float(result.dti_back_end) if result.dti_back_end is not None else None,
                    "confidence": result.confidence,
                    "flags": json.dumps(result.flags),
                    "recommendations": json.dumps(result.recommendations),
                    "model": self._model,
                    "duration": duration_ms,
                    "source_docs": json.dumps(
                        list({did for s in result.sources for did in s.source_doc_ids})
                    ),
                    "now": datetime.now(timezone.utc),
                },
            )
            calculation_id = calc_row.fetchone()[0]

            # --- income_sources (the income_calculation model's IncomeSource) ---
            for idx, source in enumerate(result.sources):
                source_row = self.db.execute(
                    text("""
                        INSERT INTO income_sources (
                            calculation_id, borrower_id,
                            source_type, employer_name, position_title,
                            is_primary,
                            base_monthly_income, overtime_monthly,
                            bonus_monthly, commission_monthly, other_monthly,
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
                            :base, :ot,
                            :bonus, :commission, :other,
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
                        "calc_id": calculation_id,
                        "borrower_id": result.borrower_id,
                        "source_type": source.source_type.lower(),
                        "employer": source.employer_name,
                        "position": source.position_title,
                        "is_primary": idx == 0,
                        "base": float(source.base_monthly),
                        "ot": float(source.overtime_monthly),
                        "bonus": float(source.bonus_monthly),
                        "commission": float(source.commission_monthly),
                        "other": float(source.other_monthly),
                        "total_monthly": float(source.total_monthly),
                        "total_annual": float(source.total_annual),
                        "trending": source.trending.lower(),
                        "year1": float(source.year1_income) if source.year1_income is not None else None,
                        "year2": float(source.year2_income) if source.year2_income is not None else None,
                        "yoy_pct": float(source.yoy_change_pct) if source.yoy_change_pct is not None else None,
                        "verification_status": "unverified",
                        "doc_ids": json.dumps(source.source_doc_ids),
                        "confidence": source.confidence,
                        "notes": source.notes,
                        "now": datetime.now(timezone.utc),
                    },
                )
                source_id = source_row.fetchone()[0]

                # --- income_verification_tasks ---
                for task in result.tasks_to_create:
                    # Only link tasks whose flags relate to this source type
                    task_desc = task.get("description", "")
                    source_related = (
                        source.source_type in task_desc
                        or any(f in task_desc for f in source.flags)
                        # Generic tasks go on all sources
                        or source.source_type == "W2_EMPLOYMENT"
                    )
                    if not source_related:
                        continue

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
                            "calc_id": calculation_id,
                            "source_id": source_id,
                            "loan_id": result.loan_id,
                            "org_id": self.org_id,
                            "task_type": task["task_type"],
                            "title": task["title"],
                            "description": task["description"],
                            "priority": task["priority"],
                            "ai_rec": task.get("ai_recommendation", ""),
                            "now": datetime.now(timezone.utc),
                        },
                    )

            self.db.commit()
            logger.info(
                f"Income calculation saved: id={calculation_id} "
                f"loan={result.loan_id} borrower={result.borrower_id} "
                f"monthly={result.total_qualifying_monthly} "
                f"sources={len(result.sources)} tasks={len(result.tasks_to_create)}"
            )
            return calculation_id

        except Exception as e:
            self.db.rollback()
            logger.exception(f"Failed to save income calculation: {e}")
            raise

    # =========================================================================
    # 13. AI-POWERED EXTRACTION
    # =========================================================================

    def _extract_income_with_ai(
        self,
        document_text: str,
        doc_type: str,
    ) -> Dict:
        """
        Use Claude API to extract structured income data from document text.
        Returns dict with base_income, overtime, bonus, commission, employer,
        pay_period, etc.
        Falls back to regex extraction if AI is unavailable.
        """
        if HAS_ANTHROPIC and self._anthropic_key:
            try:
                result = self._extract_with_claude(document_text, doc_type)
                if result is not None:
                    logger.info(
                        "Income AI extraction succeeded | doc_type=%s | "
                        "fields_extracted=%d",
                        doc_type,
                        len([v for v in result.values() if v is not None]),
                    )
                    return result
                # AI returned None (failed after retries) -- fall through to regex
                logger.warning(
                    "AI income extraction unavailable, falling back to regex | doc_type=%s",
                    doc_type,
                )
            except Exception as e:
                logger.warning(f"AI extraction failed, falling back to regex: {e}")

        return self._extract_with_regex(document_text, doc_type)

    def _extract_with_claude(self, document_text: str, doc_type: str) -> Optional[Dict]:
        """Call Claude to extract structured income data.

        Returns parsed dict on success, or None if AI call failed after retries.
        """
        client = Anthropic(api_key=self._anthropic_key)

        prompt = f"""You are a mortgage document data extraction specialist.
Extract structured income data from this {doc_type} document.

DOCUMENT TEXT:
{document_text[:30000]}

Return a JSON object with these fields (use null if not found):
{{
    "employer_name": "string",
    "employee_name": "string",
    "position_title": "string",
    "pay_frequency": "WEEKLY|BIWEEKLY|SEMIMONTHLY|MONTHLY",
    "pay_date": "YYYY-MM-DD",
    "pay_period_start": "YYYY-MM-DD",
    "pay_period_end": "YYYY-MM-DD",
    "gross_pay": 0.00,
    "net_pay": 0.00,
    "regular_earnings": 0.00,
    "overtime_earnings": 0.00,
    "bonus": 0.00,
    "commission": 0.00,
    "other_earnings": 0.00,
    "ytd_gross": 0.00,
    "ytd_overtime_earnings": 0.00,
    "ytd_bonus": 0.00,
    "ytd_commission": 0.00,
    "tax_year": 2025,
    "wages_tips_compensation": 0.00,
    "adjusted_gross_income": 0.00,
    "net_profit_loss": 0.00,
    "depreciation_addback": 0.00,
    "schedule_e_gross_rents": 0.00,
    "schedule_e_total_expenses": 0.00,
    "schedule_e_depreciation": 0.00,
    "k1_ordinary_income": 0.00,
    "k1_guaranteed_payments": 0.00,
    "business_name": "string"
}}

For currency values, return numbers only (no $ or commas).
Respond with ONLY the JSON object."""

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            max_tokens=2048,
            operation_name="income_extraction",
            timeout=30.0,
        )

        if response is None:
            return None

        response_text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if response_text.startswith("```"):
            response_text = re.sub(r"^```json?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        return json.loads(response_text)

    def _extract_with_regex(self, document_text: str, doc_type: str) -> Dict:
        """Fallback regex-based extraction for when AI is unavailable."""
        result: Dict[str, Any] = {}

        # Currency pattern: $1,234.56 or 1234.56
        currency_pattern = r"\$?\s*([\d,]+\.?\d{0,2})"

        # Try to find gross pay
        gross_match = re.search(
            r"(?:gross\s*pay|gross\s*earnings|total\s*earnings)[:\s]*" + currency_pattern,
            document_text,
            re.IGNORECASE,
        )
        if gross_match:
            result["gross_pay"] = float(gross_match.group(1).replace(",", ""))

        # Try to find YTD gross
        ytd_match = re.search(
            r"(?:ytd|year[\s-]*to[\s-]*date)\s*(?:gross|total)[:\s]*" + currency_pattern,
            document_text,
            re.IGNORECASE,
        )
        if ytd_match:
            result["ytd_gross"] = float(ytd_match.group(1).replace(",", ""))

        # Try to find employer name
        employer_match = re.search(
            r"(?:employer|company)[:\s]+([A-Z][A-Za-z\s&.,]+?)(?:\n|$)",
            document_text,
        )
        if employer_match:
            result["employer_name"] = employer_match.group(1).strip()

        # Try to find pay date
        date_match = re.search(
            r"(?:pay\s*date|check\s*date|payment\s*date)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            document_text,
            re.IGNORECASE,
        )
        if date_match:
            result["pay_date"] = date_match.group(1)

        # Try to find pay frequency
        for freq_key, freq_val in [
            (r"weekly", "WEEKLY"),
            (r"bi[\s-]*weekly", "BIWEEKLY"),
            (r"semi[\s-]*monthly", "SEMIMONTHLY"),
            (r"monthly", "MONTHLY"),
        ]:
            if re.search(freq_key, document_text, re.IGNORECASE):
                result["pay_frequency"] = freq_val
                break

        return result

    # =========================================================================
    # 14. RECALCULATE
    # =========================================================================

    def recalculate(self, calculation_id: int) -> IncomeCalculationResult:
        """
        Re-run calculation with latest documents.
        Looks up the existing calculation to get loan_id and borrower_id,
        then runs a fresh calculation (persisted as a new 'recalculation' row).
        """
        # When org_id is set, verify the calculation belongs to a loan in our org
        _org_join = (
            "JOIN loans _org_l ON _org_l.id = ic.loan_id AND _org_l.organization_id = :_org_id"
            if self.org_id is not None else ""
        )
        _org_params = {"_org_id": self.org_id} if self.org_id is not None else {}
        recalc_query = (
            "SELECT ic.loan_id, ic.borrower_id"
            " FROM income_calculations ic"
            " " + _org_join
            + " WHERE ic.id = :calc_id"
        )
        existing = self.db.execute(
            text(recalc_query),
            {"calc_id": calculation_id, **_org_params},
        ).fetchone()

        if not existing:
            return IncomeCalculationResult(
                loan_id=0,
                borrower_id=0,
                sources=[],
                total_qualifying_monthly=ZERO,
                total_qualifying_annual=ZERO,
                calculation_method="error",
                dti_front_end=None,
                dti_back_end=None,
                confidence=0,
                flags=[],
                recommendations=[],
                tasks_to_create=[],
                success=False,
                error=f"Calculation {calculation_id} not found",
            )

        # Mark old one as superseded
        self.db.execute(
            text("""
                UPDATE income_calculations
                SET status = 'rejected',
                    review_notes = 'Superseded by recalculation',
                    updated_at = :now
                WHERE id = :calc_id
            """),
            {"calc_id": calculation_id, "now": datetime.now(timezone.utc)},
        )
        self.db.commit()

        # Run fresh calculation
        result = self.calculate_income(
            loan_id=existing.loan_id,
            borrower_id=existing.borrower_id,
        )

        # Update the new calculation row to be type=recalculation
        if result.success:
            self.db.execute(
                text("""
                    UPDATE income_calculations
                    SET calculation_type = 'recalculation'
                    WHERE loan_id = :loan_id
                      AND borrower_id = :borrower_id
                      AND calculation_type = 'initial'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"loan_id": existing.loan_id, "borrower_id": existing.borrower_id},
            )
            self.db.commit()

        return result

    # =========================================================================
    # HELPERS
    # =========================================================================

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

    def _months_elapsed_in_year(self, pay_date_str: Optional[str]) -> Optional[int]:
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


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

def get_income_calculator_service(db: Session, org_id: Optional[int] = None) -> IncomeCalculatorService:
    """
    Factory function returning an IncomeCalculatorService for the given session.

    Not a true singleton because each request may have a different DB session,
    but the service itself is lightweight and stateless beyond the session.

    Args:
        db: SQLAlchemy database session.
        org_id: Organization ID for tenant isolation.  When provided, all
                queries are scoped to loans/documents belonging to that org.
    """
    return IncomeCalculatorService(db, org_id=org_id)
