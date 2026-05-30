"""
Tax Return Analysis Service for Mortgage Underwriting

Comprehensive analysis of personal and business tax returns per Fannie Mae
Selling Guide (Chapter B3-3.3) and FHA/VA guidelines. Parses Form 1040,
Schedule C, Schedule E, K-1, and corporate returns (1120S/1065/1120) to
derive qualifying income with appropriate add-backs and exclusions.

Integrates with:
    - smart_documents / smart_document_extractions for document data
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items

Key analysis areas:
    1. Form 1040 income lines and schedule identification
    2. Schedule C self-employment income with add-backs
    3. Schedule E rental income per Fannie Mae 75% rule
    4. K-1 partnership/S-Corp income and loss limitations
    5. Corporate return analysis (1120S, 1065, 1120)
    6. Red flag detection (declining income, one-time gains, NOLs)
    7. Qualifying income calculation with 2-year averaging

Usage:
    from services.smart_docs.tax_return_analyzer_service import (
        get_tax_return_analyzer,
        TaxReturnAnalyzerService,
    )

    service = get_tax_return_analyzer(db)
    result = service.analyze_tax_returns(loan_id=42, borrower_id=7)
"""

import logging
import os
import json
import time
from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

# Fannie Mae rental income vacancy factor: only 75% of net rental counts
RENTAL_VACANCY_FACTOR = Decimal("0.75")

# Meals deduction add-back: IRS allows 50%, so 50% is added back for UW
MEALS_ADDBACK_PCT = Decimal("0.50")

# Number of months for annualization
MONTHS_PER_YEAR = 12

# Income trend thresholds
DECLINING_INCOME_WARN_PCT = Decimal("10")
DECLINING_INCOME_CRITICAL_PCT = Decimal("25")

# Minimum years of self-employment required by most guidelines
MIN_SE_YEARS = 2

# Capital gains threshold for one-time exclusion consideration
CAPITAL_GAINS_RECURRING_THRESHOLD = Decimal("5000.00")

# Tax return doc types matching smart_docs model DocType enum values
TAX_RETURN_DOC_TYPES = ("TAX_RETURN", "BUSINESS_TAX_RETURN")


class ReturnType(str, Enum):
    """Tax return form types."""
    FORM_1040 = "1040"
    SCHEDULE_C = "SCHEDULE_C"
    SCHEDULE_E = "SCHEDULE_E"
    SCHEDULE_K1 = "K-1"
    FORM_1120S = "1120S"
    FORM_1065 = "1065"
    FORM_1120 = "1120"


class RedFlagSeverity(str, Enum):
    """Severity levels for underwriting red flags."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Form1040Analysis:
    """Parsed Form 1040 data for a single tax year."""
    tax_year: int
    filing_status: Optional[str]

    # Income lines (Form 1040 line references)
    wages_line1: Decimal = ZERO  # Line 1: Wages, salaries, tips
    interest_income: Decimal = ZERO  # Line 2b: Taxable interest
    dividend_income: Decimal = ZERO  # Line 3b: Ordinary dividends
    qualified_dividends: Decimal = ZERO  # Line 3a
    business_income: Decimal = ZERO  # Line 8: Schedule 1 / Schedule C
    capital_gains: Decimal = ZERO  # Line 7: Capital gain or loss
    rental_income: Decimal = ZERO  # Schedule E total
    farm_income: Decimal = ZERO  # Schedule F
    unemployment_compensation: Decimal = ZERO
    social_security_income: Decimal = ZERO  # Line 6b
    other_income: Decimal = ZERO  # Line 8 (other)

    # Computed totals
    total_income: Decimal = ZERO  # Line 9
    adjustments: Decimal = ZERO  # Schedule 1 adjustments
    agi: Decimal = ZERO  # Line 11: Adjusted Gross Income
    taxable_income: Decimal = ZERO  # Line 15
    total_tax: Decimal = ZERO  # Line 24
    taxes_paid: Decimal = ZERO  # Withholdings + estimated payments

    # Schedules filed
    schedules_filed: List[str] = field(default_factory=list)

    # Extension or amended
    is_extension: bool = False
    is_amended: bool = False

    # Source document IDs
    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class ScheduleCAnalysis:
    """Schedule C (Profit or Loss from Business) analysis for a single year."""
    tax_year: int
    business_name: Optional[str]
    business_type: Optional[str]
    ein: Optional[str]

    gross_receipts: Decimal = ZERO  # Line 1
    returns_and_allowances: Decimal = ZERO  # Line 2
    cost_of_goods_sold: Decimal = ZERO  # Line 4
    gross_profit: Decimal = ZERO  # Line 7

    # Expenses
    advertising: Decimal = ZERO
    car_and_truck: Decimal = ZERO
    commissions_and_fees: Decimal = ZERO
    depreciation: Decimal = ZERO  # Line 13 — add-back for qualifying income
    insurance: Decimal = ZERO
    interest_mortgage: Decimal = ZERO
    interest_other: Decimal = ZERO
    legal_and_professional: Decimal = ZERO
    office_expense: Decimal = ZERO
    rent_or_lease: Decimal = ZERO
    repairs_and_maintenance: Decimal = ZERO
    supplies: Decimal = ZERO
    taxes_and_licenses: Decimal = ZERO
    travel: Decimal = ZERO
    meals: Decimal = ZERO  # 50% add-back
    utilities: Decimal = ZERO
    wages_paid: Decimal = ZERO
    other_expenses: Decimal = ZERO
    total_expenses: Decimal = ZERO  # Line 28

    # Business use of home
    business_use_of_home: Decimal = ZERO  # Form 8829

    # Net profit
    net_profit_or_loss: Decimal = ZERO  # Line 31

    # Amortization / casualty loss — add-back items
    amortization: Decimal = ZERO
    casualty_loss: Decimal = ZERO

    # Source
    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class RentalProperty:
    """Single rental property from Schedule E."""
    address: Optional[str]
    property_type: Optional[str]  # Single Family, Multi Family, etc.
    fair_rental_days: int = 0
    personal_use_days: int = 0

    # Income
    rents_received: Decimal = ZERO  # Line 3

    # Expenses
    advertising: Decimal = ZERO
    auto_and_travel: Decimal = ZERO
    cleaning_and_maintenance: Decimal = ZERO
    commissions: Decimal = ZERO
    insurance: Decimal = ZERO
    legal_and_professional: Decimal = ZERO
    management_fees: Decimal = ZERO
    mortgage_interest: Decimal = ZERO
    other_interest: Decimal = ZERO
    repairs: Decimal = ZERO
    supplies: Decimal = ZERO
    taxes: Decimal = ZERO
    utilities: Decimal = ZERO
    depreciation: Decimal = ZERO  # Add-back for qualifying income
    other_expenses: Decimal = ZERO
    total_expenses: Decimal = ZERO

    # Net
    net_rental_income: Decimal = ZERO


@dataclass
class ScheduleEAnalysis:
    """Schedule E (Supplemental Income and Loss) analysis for a single year."""
    tax_year: int
    properties: List[RentalProperty] = field(default_factory=list)
    total_rental_income: Decimal = ZERO
    total_rental_expenses: Decimal = ZERO
    total_depreciation: Decimal = ZERO
    net_rental_income: Decimal = ZERO
    fannie_mae_qualifying_rental: Decimal = ZERO  # 75% of net + depreciation
    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class K1Analysis:
    """K-1 (Partner's / Shareholder's Share of Income) analysis."""
    tax_year: int
    entity_name: Optional[str]
    ein: Optional[str]
    entity_type: str  # PARTNERSHIP, S_CORP
    ownership_pct: Optional[Decimal]

    ordinary_business_income: Decimal = ZERO  # Box 1
    guaranteed_payments: Decimal = ZERO  # Box 4 (partnerships)
    net_rental_income: Decimal = ZERO  # Box 2
    interest_income: Decimal = ZERO  # Box 5
    dividend_income: Decimal = ZERO  # Box 6a
    royalties: Decimal = ZERO  # Box 7
    capital_gains: Decimal = ZERO  # Box 8/9/10
    other_income: Decimal = ZERO  # Box 11

    # Distributions vs income
    distributions: Decimal = ZERO  # Box 16 (S-Corp) or Box 19 (Partnership)

    # Loss limitations
    at_risk_limitation: bool = False
    passive_activity_limitation: bool = False

    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class CorporateReturnAnalysis:
    """Business return analysis (1120S, 1065, or 1120)."""
    tax_year: int
    form_type: str  # 1120S, 1065, 1120
    entity_name: Optional[str]
    ein: Optional[str]

    # Income
    gross_receipts: Decimal = ZERO
    cost_of_goods_sold: Decimal = ZERO
    gross_profit: Decimal = ZERO
    ordinary_income: Decimal = ZERO
    net_income: Decimal = ZERO

    # Officer compensation (1120S)
    officer_compensation: Decimal = ZERO

    # Add-back items
    depreciation: Decimal = ZERO
    amortization: Decimal = ZERO
    depletion: Decimal = ZERO
    meals_entertainment: Decimal = ZERO  # Non-deductible portion

    # Retained earnings (C-Corp)
    retained_earnings: Decimal = ZERO
    dividends_paid: Decimal = ZERO

    # Guaranteed payments (1065)
    guaranteed_payments: Decimal = ZERO

    # Borrower's ownership percentage
    ownership_pct: Optional[Decimal] = None

    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class RedFlag:
    """Underwriting red flag identified during analysis."""
    flag_type: str  # DECLINING_INCOME, ONE_TIME_GAIN, NOL, etc.
    severity: RedFlagSeverity
    description: str
    impact_on_income: Optional[Decimal] = None
    recommendation: str = ""


@dataclass
class QualifyingIncomeBreakdown:
    """Detailed breakdown of qualifying income derivation."""
    source_label: str  # e.g., "Schedule C - ABC Consulting"
    year1_amount: Decimal = ZERO
    year2_amount: Decimal = ZERO
    addbacks: Dict[str, Decimal] = field(default_factory=dict)
    subtracted_items: Dict[str, Decimal] = field(default_factory=dict)
    year1_adjusted: Decimal = ZERO
    year2_adjusted: Decimal = ZERO
    two_year_total: Decimal = ZERO
    monthly_qualifying: Decimal = ZERO
    methodology: str = "2_YEAR_AVERAGE"
    notes: str = ""


@dataclass
class TaxReturnAnalysisResult:
    """Complete tax return analysis result."""
    loan_id: int
    borrower_id: int
    tax_years_analyzed: List[int]

    # Parsed data
    form_1040s: List[Form1040Analysis]
    schedule_cs: List[ScheduleCAnalysis]
    schedule_es: List[ScheduleEAnalysis]
    k1s: List[K1Analysis]
    corporate_returns: List[CorporateReturnAnalysis]

    # Qualifying income
    qualifying_income_breakdown: List[QualifyingIncomeBreakdown]
    total_monthly_qualifying_income: Decimal
    total_annual_qualifying_income: Decimal

    # Trending
    income_trend: str  # INCREASING, STABLE, DECLINING, INSUFFICIENT_DATA
    yoy_change_pct: Optional[Decimal]

    # Red flags
    red_flags: List[RedFlag]

    # Tasks for LO
    tasks_to_create: List[Dict]

    # Metadata
    confidence: int  # 0-100
    analysis_method: str
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# SERVICE
# =============================================================================

class TaxReturnAnalyzerService:
    """
    Analyzes personal and business tax returns for mortgage qualifying income.

    Implements Fannie Mae Selling Guide B3-3.3 methodology:
    - 2-year averaging for self-employment and variable income
    - Depreciation, amortization, and depletion add-backs
    - One-time income exclusions (capital gains, casualty loss)
    - Rental income at 75% of net after add-backs
    - K-1 and corporate return flow-through analysis

    Red flag detection:
    - Declining income trend (>10% YOY)
    - Net operating losses
    - Large non-recurring capital gains
    - IRS payment plans / amended returns
    - Extension filings
    """

    def __init__(self, db: Session):
        self.db = db
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    def analyze_tax_returns(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> TaxReturnAnalysisResult:
        """
        Main entry point: gather tax return documents, parse forms, calculate
        qualifying income per underwriting guidelines, detect red flags,
        generate LO tasks, and persist results.

        Args:
            loan_id: The loan being underwritten.
            borrower_id: The borrower whose returns to analyze.

        Returns:
            TaxReturnAnalysisResult with qualifying income, red flags, and tasks.
        """
        start_ms = int(time.time() * 1000)
        try:
            # Step 1: gather tax return documents with extracted data
            docs = self._gather_tax_documents(loan_id, borrower_id)

            if not docs:
                return self._empty_result(
                    loan_id, borrower_id,
                    error="No tax return documents found for this borrower.",
                    flags=[RedFlag(
                        flag_type="NO_TAX_RETURNS",
                        severity=RedFlagSeverity.CRITICAL,
                        description="No tax returns on file for income analysis.",
                        recommendation="Request 2 most recent years of personal tax returns (Form 1040) with all schedules.",
                    )],
                )

            # Step 2: parse documents into structured analysis objects
            form_1040s = self._parse_form_1040s(docs)
            schedule_cs = self._parse_schedule_cs(docs)
            schedule_es = self._parse_schedule_es(docs)
            k1s = self._parse_k1s(docs)
            corporate_returns = self._parse_corporate_returns(docs)

            # Step 3: determine tax years analyzed
            all_years = set()
            for f in form_1040s:
                all_years.add(f.tax_year)
            for sc in schedule_cs:
                all_years.add(sc.tax_year)
            for se in schedule_es:
                all_years.add(se.tax_year)
            for k in k1s:
                all_years.add(k.tax_year)
            for cr in corporate_returns:
                all_years.add(cr.tax_year)

            tax_years = sorted(all_years, reverse=True)

            # Step 4: calculate qualifying income per source
            breakdown = self._calculate_qualifying_income(
                form_1040s=form_1040s,
                schedule_cs=schedule_cs,
                schedule_es=schedule_es,
                k1s=k1s,
                corporate_returns=corporate_returns,
                tax_years=tax_years,
            )

            total_monthly = sum(
                (b.monthly_qualifying for b in breakdown), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            total_annual = (total_monthly * MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            # Step 5: income trend analysis
            income_trend, yoy_change = self._analyze_income_trend(
                form_1040s, schedule_cs, schedule_es, k1s, corporate_returns, tax_years
            )

            # Step 6: red flag detection
            red_flags = self._detect_red_flags(
                form_1040s=form_1040s,
                schedule_cs=schedule_cs,
                schedule_es=schedule_es,
                k1s=k1s,
                corporate_returns=corporate_returns,
                income_trend=income_trend,
                yoy_change=yoy_change,
                tax_years=tax_years,
            )

            # Step 7: confidence scoring
            confidence = self._calculate_confidence(
                form_1040s, schedule_cs, tax_years, red_flags
            )

            # Step 8: generate LO tasks
            tasks = self._generate_tasks(red_flags, tax_years, form_1040s)

            result = TaxReturnAnalysisResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                tax_years_analyzed=tax_years,
                form_1040s=form_1040s,
                schedule_cs=schedule_cs,
                schedule_es=schedule_es,
                k1s=k1s,
                corporate_returns=corporate_returns,
                qualifying_income_breakdown=breakdown,
                total_monthly_qualifying_income=total_monthly,
                total_annual_qualifying_income=total_annual,
                income_trend=income_trend,
                yoy_change_pct=yoy_change,
                red_flags=red_flags,
                tasks_to_create=tasks,
                confidence=confidence,
                analysis_method="2_YEAR_AVERAGE" if len(tax_years) >= 2 else "1_YEAR",
            )

            # Step 9: persist
            duration_ms = int(time.time() * 1000) - start_ms
            self._save_analysis(result, duration_ms)

            return result

        except Exception as e:
            logger.exception(
                f"Tax return analysis failed for loan={loan_id} borrower={borrower_id}: {e}"
            )
            return self._empty_result(loan_id, borrower_id, error=str(e))

    # =========================================================================
    # 2. GATHER TAX DOCUMENTS
    # =========================================================================

    def _gather_tax_documents(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> List[Dict]:
        """
        Query smart_documents for tax return documents, joined with
        smart_document_extractions for parsed field data.

        Returns list of dicts with keys: id, doc_type, tax_year,
        extracted_fields, raw_text, etc.
        """
        try:
            rows = self.db.execute(text("""
                SELECT
                    sd.id,
                    sd.doc_type,
                    sd.doc_sub_type,
                    sd.status,
                    sd.uploaded_at,
                    sd.filename,
                    sde.extracted_fields,
                    sde.raw_text,
                    sde.confidence_score,
                    sde.tax_year
                FROM smart_documents sd
                LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                WHERE sd.loan_id = :loan_id
                    AND sd.borrower_id = :borrower_id
                    AND sd.doc_type IN :doc_types
                    AND sd.status != 'DELETED'
                ORDER BY sde.tax_year DESC NULLS LAST, sd.uploaded_at DESC
            """), {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "doc_types": TAX_RETURN_DOC_TYPES,
            }).fetchall()

            docs = []
            for row in rows:
                extracted = row.extracted_fields
                if isinstance(extracted, str):
                    try:
                        extracted = json.loads(extracted)
                    except (json.JSONDecodeError, TypeError):
                        extracted = {}

                docs.append({
                    "id": row.id,
                    "doc_type": row.doc_type,
                    "doc_sub_type": row.doc_sub_type,
                    "status": row.status,
                    "filename": row.filename or "",
                    "extracted_fields": extracted or {},
                    "raw_text": row.raw_text or "",
                    "confidence_score": row.confidence_score,
                    "tax_year": row.tax_year,
                })

            return docs

        except Exception as e:
            logger.error(f"Failed to gather tax documents: {e}")
            return []

    # =========================================================================
    # 3. FORM 1040 PARSING
    # =========================================================================

    def _parse_form_1040s(self, docs: List[Dict]) -> List[Form1040Analysis]:
        """
        Parse Form 1040 data from extracted fields. Groups by tax year and
        populates income lines, schedules filed, and AGI.
        """
        results = []
        seen_years: Dict[int, Form1040Analysis] = {}

        for doc in docs:
            fields = doc.get("extracted_fields", {})
            form_type = fields.get("form_type", "").upper()

            # Only process 1040 forms
            if "1040" not in form_type and doc.get("doc_sub_type", "") != "1040":
                continue

            tax_year = self._extract_tax_year(doc)
            if not tax_year:
                continue

            if tax_year in seen_years:
                # Merge additional data into existing year
                existing = seen_years[tax_year]
                existing.source_doc_ids.append(doc["id"])
                self._merge_1040_fields(existing, fields)
                continue

            analysis = Form1040Analysis(
                tax_year=tax_year,
                filing_status=fields.get("filing_status"),
                wages_line1=self._to_decimal(fields.get("wages", fields.get("line_1"))),
                interest_income=self._to_decimal(fields.get("interest_income", fields.get("line_2b"))),
                dividend_income=self._to_decimal(fields.get("dividend_income", fields.get("line_3b"))),
                qualified_dividends=self._to_decimal(fields.get("qualified_dividends", fields.get("line_3a"))),
                business_income=self._to_decimal(fields.get("business_income", fields.get("line_8_sched1"))),
                capital_gains=self._to_decimal(fields.get("capital_gains", fields.get("line_7"))),
                rental_income=self._to_decimal(fields.get("rental_income")),
                farm_income=self._to_decimal(fields.get("farm_income")),
                unemployment_compensation=self._to_decimal(fields.get("unemployment")),
                social_security_income=self._to_decimal(fields.get("social_security", fields.get("line_6b"))),
                other_income=self._to_decimal(fields.get("other_income")),
                total_income=self._to_decimal(fields.get("total_income", fields.get("line_9"))),
                adjustments=self._to_decimal(fields.get("adjustments", fields.get("line_10"))),
                agi=self._to_decimal(fields.get("agi", fields.get("line_11"))),
                taxable_income=self._to_decimal(fields.get("taxable_income", fields.get("line_15"))),
                total_tax=self._to_decimal(fields.get("total_tax", fields.get("line_24"))),
                taxes_paid=self._to_decimal(fields.get("taxes_paid")),
                schedules_filed=self._extract_schedules_filed(fields),
                is_extension=bool(fields.get("is_extension", False)),
                is_amended=bool(fields.get("is_amended", False)),
                source_doc_ids=[doc["id"]],
            )

            # Recompute AGI if missing but components are present
            if analysis.agi == ZERO and analysis.total_income > ZERO:
                analysis.agi = analysis.total_income - abs(analysis.adjustments)

            seen_years[tax_year] = analysis

        results = sorted(seen_years.values(), key=lambda x: x.tax_year, reverse=True)
        return results

    def _merge_1040_fields(self, existing: Form1040Analysis, fields: Dict) -> None:
        """Merge additional extracted fields into an existing 1040 analysis."""
        # Only overwrite zero values with non-zero extracted data
        field_mapping = {
            "wages": "wages_line1",
            "line_1": "wages_line1",
            "interest_income": "interest_income",
            "dividend_income": "dividend_income",
            "business_income": "business_income",
            "capital_gains": "capital_gains",
            "agi": "agi",
            "taxable_income": "taxable_income",
        }
        for extract_key, attr_name in field_mapping.items():
            val = self._to_decimal(fields.get(extract_key))
            if val != ZERO and getattr(existing, attr_name) == ZERO:
                setattr(existing, attr_name, val)

    def _extract_schedules_filed(self, fields: Dict) -> List[str]:
        """Extract list of schedules filed from extracted fields."""
        schedules = fields.get("schedules_filed", [])
        if isinstance(schedules, str):
            # Handle comma-separated or space-separated strings
            schedules = [s.strip() for s in schedules.replace(",", " ").split() if s.strip()]
        if isinstance(schedules, list):
            return [s.upper() for s in schedules if s]
        return []

    # =========================================================================
    # 4. SCHEDULE C PARSING (Self-Employment)
    # =========================================================================

    def _parse_schedule_cs(self, docs: List[Dict]) -> List[ScheduleCAnalysis]:
        """
        Parse Schedule C data from extracted fields. Handles multiple
        businesses across multiple years.
        """
        results = []

        for doc in docs:
            fields = doc.get("extracted_fields", {})
            form_type = fields.get("form_type", "").upper()

            # Detect Schedule C data
            sched_c_data = fields.get("schedule_c", {})
            if not sched_c_data and "SCHEDULE_C" not in form_type:
                # Check if it is a business tax return with C data
                if doc.get("doc_sub_type", "") not in ("SCHEDULE_C", "schedule_c"):
                    continue
                sched_c_data = fields

            if isinstance(sched_c_data, list):
                # Multiple Schedule Cs in one return
                for sc_item in sched_c_data:
                    parsed = self._parse_single_schedule_c(doc, sc_item)
                    if parsed:
                        results.append(parsed)
            elif isinstance(sched_c_data, dict) and sched_c_data:
                parsed = self._parse_single_schedule_c(doc, sched_c_data)
                if parsed:
                    results.append(parsed)

        return sorted(results, key=lambda x: x.tax_year, reverse=True)

    def _parse_single_schedule_c(
        self, doc: Dict, sc_fields: Dict
    ) -> Optional[ScheduleCAnalysis]:
        """Parse a single Schedule C from extracted fields."""
        tax_year = self._extract_tax_year(doc, sc_fields)
        if not tax_year:
            return None

        gross_receipts = self._to_decimal(sc_fields.get("gross_receipts", sc_fields.get("line_1")))
        returns_allowances = self._to_decimal(sc_fields.get("returns_and_allowances", sc_fields.get("line_2")))
        cogs = self._to_decimal(sc_fields.get("cost_of_goods_sold", sc_fields.get("line_4")))
        gross_profit = self._to_decimal(sc_fields.get("gross_profit", sc_fields.get("line_7")))

        # If gross_profit not extracted, compute it
        if gross_profit == ZERO and gross_receipts > ZERO:
            gross_profit = gross_receipts - returns_allowances - cogs

        depreciation = self._to_decimal(sc_fields.get("depreciation", sc_fields.get("line_13")))
        meals = self._to_decimal(sc_fields.get("meals", sc_fields.get("line_24b")))
        total_expenses = self._to_decimal(sc_fields.get("total_expenses", sc_fields.get("line_28")))
        net_profit = self._to_decimal(sc_fields.get("net_profit", sc_fields.get("line_31")))
        business_use_home = self._to_decimal(sc_fields.get("business_use_of_home", sc_fields.get("line_30")))
        amortization = self._to_decimal(sc_fields.get("amortization"))
        casualty_loss = self._to_decimal(sc_fields.get("casualty_loss"))

        # If net_profit not extracted, compute from gross - expenses
        if net_profit == ZERO and gross_profit > ZERO and total_expenses > ZERO:
            net_profit = gross_profit - total_expenses

        analysis = ScheduleCAnalysis(
            tax_year=tax_year,
            business_name=sc_fields.get("business_name"),
            business_type=sc_fields.get("business_type", sc_fields.get("principal_business")),
            ein=sc_fields.get("ein"),
            gross_receipts=gross_receipts,
            returns_and_allowances=returns_allowances,
            cost_of_goods_sold=cogs,
            gross_profit=gross_profit,
            advertising=self._to_decimal(sc_fields.get("advertising")),
            car_and_truck=self._to_decimal(sc_fields.get("car_and_truck", sc_fields.get("vehicle_expenses"))),
            commissions_and_fees=self._to_decimal(sc_fields.get("commissions_and_fees")),
            depreciation=depreciation,
            insurance=self._to_decimal(sc_fields.get("insurance")),
            interest_mortgage=self._to_decimal(sc_fields.get("interest_mortgage")),
            interest_other=self._to_decimal(sc_fields.get("interest_other")),
            legal_and_professional=self._to_decimal(sc_fields.get("legal_and_professional")),
            office_expense=self._to_decimal(sc_fields.get("office_expense")),
            rent_or_lease=self._to_decimal(sc_fields.get("rent_or_lease")),
            repairs_and_maintenance=self._to_decimal(sc_fields.get("repairs_and_maintenance")),
            supplies=self._to_decimal(sc_fields.get("supplies")),
            taxes_and_licenses=self._to_decimal(sc_fields.get("taxes_and_licenses")),
            travel=self._to_decimal(sc_fields.get("travel")),
            meals=meals,
            utilities=self._to_decimal(sc_fields.get("utilities")),
            wages_paid=self._to_decimal(sc_fields.get("wages_paid")),
            other_expenses=self._to_decimal(sc_fields.get("other_expenses")),
            total_expenses=total_expenses,
            business_use_of_home=business_use_home,
            net_profit_or_loss=net_profit,
            amortization=amortization,
            casualty_loss=casualty_loss,
            source_doc_ids=[doc["id"]],
        )
        return analysis

    def calculate_schedule_c_qualifying(
        self, sc: ScheduleCAnalysis
    ) -> Tuple[Decimal, Dict[str, Decimal]]:
        """
        Calculate qualifying income from a Schedule C with add-backs.

        Per Fannie Mae B3-3.3-03:
        - Start with net profit/loss (Line 31)
        - Add back: depreciation (Line 13)
        - Add back: amortization/casualty loss
        - Add back: 50% of meals deduction (non-deductible portion)
        - Add back: business use of home deduction
        - Subtract: non-recurring income if identified

        Returns (adjusted_income, addbacks_dict).
        """
        addbacks: Dict[str, Decimal] = {}

        adjusted = sc.net_profit_or_loss

        # Depreciation add-back
        if sc.depreciation > ZERO:
            addbacks["depreciation"] = sc.depreciation
            adjusted += sc.depreciation

        # Amortization add-back
        if sc.amortization > ZERO:
            addbacks["amortization"] = sc.amortization
            adjusted += sc.amortization

        # Casualty loss add-back (non-recurring)
        if sc.casualty_loss > ZERO:
            addbacks["casualty_loss"] = sc.casualty_loss
            adjusted += sc.casualty_loss

        # Meals 50% add-back: the deduction is already at 50% on the return,
        # but underwriting adds back the full deducted amount for some lenders.
        # Standard practice: add back the 50% that was deducted.
        if sc.meals > ZERO:
            meals_addback = (sc.meals * MEALS_ADDBACK_PCT).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            addbacks["meals_50pct"] = meals_addback
            adjusted += meals_addback

        # Business use of home add-back
        if sc.business_use_of_home > ZERO:
            addbacks["business_use_of_home"] = sc.business_use_of_home
            adjusted += sc.business_use_of_home

        return adjusted.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), addbacks

    # =========================================================================
    # 5. SCHEDULE E PARSING (Rental Income)
    # =========================================================================

    def _parse_schedule_es(self, docs: List[Dict]) -> List[ScheduleEAnalysis]:
        """
        Parse Schedule E data. Handles multiple properties per year and
        calculates Fannie Mae qualifying rental income.
        """
        results_by_year: Dict[int, ScheduleEAnalysis] = {}

        for doc in docs:
            fields = doc.get("extracted_fields", {})
            sched_e_data = fields.get("schedule_e", {})

            if not sched_e_data:
                if doc.get("doc_sub_type", "") not in ("SCHEDULE_E", "schedule_e"):
                    continue
                sched_e_data = fields

            tax_year = self._extract_tax_year(doc, sched_e_data if isinstance(sched_e_data, dict) else {})
            if not tax_year:
                continue

            properties_data = sched_e_data.get("properties", [])
            if isinstance(properties_data, dict):
                properties_data = [properties_data]

            properties: List[RentalProperty] = []
            total_income = ZERO
            total_expenses = ZERO
            total_depreciation = ZERO

            for prop_data in properties_data:
                if not isinstance(prop_data, dict):
                    continue

                rents = self._to_decimal(prop_data.get("rents_received", prop_data.get("line_3")))
                depreciation = self._to_decimal(prop_data.get("depreciation"))
                prop_total_exp = self._to_decimal(prop_data.get("total_expenses"))
                net = self._to_decimal(prop_data.get("net_rental_income", prop_data.get("net_income")))

                if net == ZERO and rents > ZERO and prop_total_exp > ZERO:
                    net = rents - prop_total_exp

                prop = RentalProperty(
                    address=prop_data.get("address"),
                    property_type=prop_data.get("property_type"),
                    fair_rental_days=int(prop_data.get("fair_rental_days", 0)),
                    personal_use_days=int(prop_data.get("personal_use_days", 0)),
                    rents_received=rents,
                    advertising=self._to_decimal(prop_data.get("advertising")),
                    auto_and_travel=self._to_decimal(prop_data.get("auto_and_travel")),
                    cleaning_and_maintenance=self._to_decimal(prop_data.get("cleaning_and_maintenance")),
                    commissions=self._to_decimal(prop_data.get("commissions")),
                    insurance=self._to_decimal(prop_data.get("insurance")),
                    legal_and_professional=self._to_decimal(prop_data.get("legal_and_professional")),
                    management_fees=self._to_decimal(prop_data.get("management_fees")),
                    mortgage_interest=self._to_decimal(prop_data.get("mortgage_interest")),
                    other_interest=self._to_decimal(prop_data.get("other_interest")),
                    repairs=self._to_decimal(prop_data.get("repairs")),
                    supplies=self._to_decimal(prop_data.get("supplies")),
                    taxes=self._to_decimal(prop_data.get("taxes")),
                    utilities=self._to_decimal(prop_data.get("utilities")),
                    depreciation=depreciation,
                    other_expenses=self._to_decimal(prop_data.get("other_expenses")),
                    total_expenses=prop_total_exp,
                    net_rental_income=net,
                )
                properties.append(prop)
                total_income += rents
                total_expenses += prop_total_exp
                total_depreciation += depreciation

            net_rental = total_income - total_expenses

            # Fannie Mae qualifying: (net_rental + depreciation) * 75%
            fannie_qualifying = ((net_rental + total_depreciation) * RENTAL_VACANCY_FACTOR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            if tax_year in results_by_year:
                existing = results_by_year[tax_year]
                existing.properties.extend(properties)
                existing.total_rental_income += total_income
                existing.total_rental_expenses += total_expenses
                existing.total_depreciation += total_depreciation
                existing.net_rental_income += net_rental
                existing.fannie_mae_qualifying_rental += fannie_qualifying
                existing.source_doc_ids.append(doc["id"])
            else:
                results_by_year[tax_year] = ScheduleEAnalysis(
                    tax_year=tax_year,
                    properties=properties,
                    total_rental_income=total_income,
                    total_rental_expenses=total_expenses,
                    total_depreciation=total_depreciation,
                    net_rental_income=net_rental,
                    fannie_mae_qualifying_rental=fannie_qualifying,
                    source_doc_ids=[doc["id"]],
                )

        return sorted(results_by_year.values(), key=lambda x: x.tax_year, reverse=True)

    # =========================================================================
    # 6. K-1 PARSING (Partnership / S-Corp)
    # =========================================================================

    def _parse_k1s(self, docs: List[Dict]) -> List[K1Analysis]:
        """Parse K-1 forms from extracted data."""
        results = []

        for doc in docs:
            fields = doc.get("extracted_fields", {})
            k1_data = fields.get("k1", fields.get("schedule_k1", {}))

            if not k1_data:
                if doc.get("doc_sub_type", "") not in ("K-1", "K1", "SCHEDULE_K1"):
                    continue
                k1_data = fields

            if isinstance(k1_data, list):
                for item in k1_data:
                    parsed = self._parse_single_k1(doc, item)
                    if parsed:
                        results.append(parsed)
            elif isinstance(k1_data, dict) and k1_data:
                parsed = self._parse_single_k1(doc, k1_data)
                if parsed:
                    results.append(parsed)

        return sorted(results, key=lambda x: x.tax_year, reverse=True)

    def _parse_single_k1(self, doc: Dict, k1_fields: Dict) -> Optional[K1Analysis]:
        """Parse a single K-1 form."""
        tax_year = self._extract_tax_year(doc, k1_fields)
        if not tax_year:
            return None

        entity_type_raw = k1_fields.get("entity_type", "").upper()
        if "1120S" in entity_type_raw or "S_CORP" in entity_type_raw or "S-CORP" in entity_type_raw:
            entity_type = "S_CORP"
        elif "1065" in entity_type_raw or "PARTNERSHIP" in entity_type_raw:
            entity_type = "PARTNERSHIP"
        else:
            entity_type = entity_type_raw or "UNKNOWN"

        return K1Analysis(
            tax_year=tax_year,
            entity_name=k1_fields.get("entity_name", k1_fields.get("partnership_name")),
            ein=k1_fields.get("ein"),
            entity_type=entity_type,
            ownership_pct=self._to_decimal(k1_fields.get("ownership_pct", k1_fields.get("ownership_percentage"))),
            ordinary_business_income=self._to_decimal(k1_fields.get("ordinary_income", k1_fields.get("box_1"))),
            guaranteed_payments=self._to_decimal(k1_fields.get("guaranteed_payments", k1_fields.get("box_4"))),
            net_rental_income=self._to_decimal(k1_fields.get("net_rental_income", k1_fields.get("box_2"))),
            interest_income=self._to_decimal(k1_fields.get("interest_income", k1_fields.get("box_5"))),
            dividend_income=self._to_decimal(k1_fields.get("dividend_income", k1_fields.get("box_6a"))),
            royalties=self._to_decimal(k1_fields.get("royalties", k1_fields.get("box_7"))),
            capital_gains=self._to_decimal(k1_fields.get("capital_gains")),
            other_income=self._to_decimal(k1_fields.get("other_income", k1_fields.get("box_11"))),
            distributions=self._to_decimal(k1_fields.get("distributions", k1_fields.get("box_16", k1_fields.get("box_19")))),
            at_risk_limitation=bool(k1_fields.get("at_risk_limitation", False)),
            passive_activity_limitation=bool(k1_fields.get("passive_activity_limitation", False)),
            source_doc_ids=[doc["id"]],
        )

    # =========================================================================
    # 7. CORPORATE RETURN PARSING (1120S / 1065 / 1120)
    # =========================================================================

    def _parse_corporate_returns(self, docs: List[Dict]) -> List[CorporateReturnAnalysis]:
        """Parse corporate/partnership returns from extracted data."""
        results = []

        for doc in docs:
            if doc.get("doc_type") != "BUSINESS_TAX_RETURN":
                continue

            fields = doc.get("extracted_fields", {})
            form_type_raw = fields.get("form_type", doc.get("doc_sub_type", "")).upper()

            # Determine form type
            if "1120S" in form_type_raw or "1120-S" in form_type_raw:
                form_type = "1120S"
            elif "1065" in form_type_raw:
                form_type = "1065"
            elif "1120" in form_type_raw:
                form_type = "1120"
            else:
                continue

            tax_year = self._extract_tax_year(doc, fields)
            if not tax_year:
                continue

            analysis = CorporateReturnAnalysis(
                tax_year=tax_year,
                form_type=form_type,
                entity_name=fields.get("entity_name", fields.get("business_name")),
                ein=fields.get("ein"),
                gross_receipts=self._to_decimal(fields.get("gross_receipts", fields.get("line_1a"))),
                cost_of_goods_sold=self._to_decimal(fields.get("cost_of_goods_sold")),
                gross_profit=self._to_decimal(fields.get("gross_profit")),
                ordinary_income=self._to_decimal(fields.get("ordinary_income", fields.get("ordinary_business_income"))),
                net_income=self._to_decimal(fields.get("net_income", fields.get("taxable_income"))),
                officer_compensation=self._to_decimal(fields.get("officer_compensation", fields.get("compensation_of_officers"))),
                depreciation=self._to_decimal(fields.get("depreciation")),
                amortization=self._to_decimal(fields.get("amortization")),
                depletion=self._to_decimal(fields.get("depletion")),
                meals_entertainment=self._to_decimal(fields.get("meals_entertainment", fields.get("meals"))),
                retained_earnings=self._to_decimal(fields.get("retained_earnings")),
                dividends_paid=self._to_decimal(fields.get("dividends_paid")),
                guaranteed_payments=self._to_decimal(fields.get("guaranteed_payments")),
                ownership_pct=self._to_decimal(fields.get("ownership_pct", fields.get("ownership_percentage"))),
                source_doc_ids=[doc["id"]],
            )

            # Compute gross_profit if missing
            if analysis.gross_profit == ZERO and analysis.gross_receipts > ZERO:
                analysis.gross_profit = analysis.gross_receipts - analysis.cost_of_goods_sold

            results.append(analysis)

        return sorted(results, key=lambda x: x.tax_year, reverse=True)

    # =========================================================================
    # 8. QUALIFYING INCOME CALCULATION
    # =========================================================================

    def _calculate_qualifying_income(
        self,
        form_1040s: List[Form1040Analysis],
        schedule_cs: List[ScheduleCAnalysis],
        schedule_es: List[ScheduleEAnalysis],
        k1s: List[K1Analysis],
        corporate_returns: List[CorporateReturnAnalysis],
        tax_years: List[int],
    ) -> List[QualifyingIncomeBreakdown]:
        """
        Calculate qualifying income from all sources using 2-year average
        methodology per Fannie Mae Selling Guide.

        For each income source:
        1. Get Year 1 and Year 2 amounts
        2. Apply add-backs (depreciation, amortization, meals, etc.)
        3. Subtract non-recurring items (one-time capital gains)
        4. Compute 2-year average and derive monthly qualifying
        """
        breakdowns: List[QualifyingIncomeBreakdown] = []

        # W-2 wage income from 1040 (simple, no add-backs needed)
        breakdowns.extend(self._qualify_w2_income(form_1040s, tax_years))

        # Schedule C self-employment income
        breakdowns.extend(self._qualify_schedule_c_income(schedule_cs, tax_years))

        # Schedule E rental income
        breakdowns.extend(self._qualify_schedule_e_income(schedule_es, tax_years))

        # K-1 income
        breakdowns.extend(self._qualify_k1_income(k1s, tax_years))

        # Corporate return income (owner's share)
        breakdowns.extend(self._qualify_corporate_income(corporate_returns, tax_years))

        return breakdowns

    def _qualify_w2_income(
        self, form_1040s: List[Form1040Analysis], tax_years: List[int]
    ) -> List[QualifyingIncomeBreakdown]:
        """Derive W-2 qualifying income from 1040 wage lines."""
        if not form_1040s:
            return []

        year1_1040 = self._get_for_year(form_1040s, tax_years, 0)
        year2_1040 = self._get_for_year(form_1040s, tax_years, 1)

        year1_wages = year1_1040.wages_line1 if year1_1040 else ZERO
        year2_wages = year2_1040.wages_line1 if year2_1040 else ZERO

        if year1_wages == ZERO and year2_wages == ZERO:
            return []

        monthly = self._two_year_average_monthly(year1_wages, year2_wages, len(tax_years) >= 2)

        return [QualifyingIncomeBreakdown(
            source_label="W-2 Wage Income",
            year1_amount=year1_wages,
            year2_amount=year2_wages,
            year1_adjusted=year1_wages,
            year2_adjusted=year2_wages,
            two_year_total=year1_wages + year2_wages,
            monthly_qualifying=monthly,
            methodology="2_YEAR_AVERAGE" if len(tax_years) >= 2 else "1_YEAR",
            notes="Wages, salaries, and tips from Form 1040 Line 1.",
        )]

    def _qualify_schedule_c_income(
        self, schedule_cs: List[ScheduleCAnalysis], tax_years: List[int]
    ) -> List[QualifyingIncomeBreakdown]:
        """Derive self-employment qualifying income from Schedule C with add-backs."""
        if not schedule_cs:
            return []

        # Group by business name to handle multiple businesses
        businesses: Dict[str, List[ScheduleCAnalysis]] = {}
        for sc in schedule_cs:
            key = sc.business_name or sc.ein or "Unknown Business"
            businesses.setdefault(key, []).append(sc)

        results = []
        for biz_name, biz_schedules in businesses.items():
            year1_sc = self._get_for_year(biz_schedules, tax_years, 0)
            year2_sc = self._get_for_year(biz_schedules, tax_years, 1)

            year1_adjusted = ZERO
            year1_addbacks: Dict[str, Decimal] = {}
            if year1_sc:
                year1_adjusted, year1_addbacks = self.calculate_schedule_c_qualifying(year1_sc)

            year2_adjusted = ZERO
            year2_addbacks: Dict[str, Decimal] = {}
            if year2_sc:
                year2_adjusted, year2_addbacks = self.calculate_schedule_c_qualifying(year2_sc)

            # Merge addback dicts for display
            all_addbacks: Dict[str, Decimal] = {}
            for key, val in year1_addbacks.items():
                all_addbacks[f"yr1_{key}"] = val
            for key, val in year2_addbacks.items():
                all_addbacks[f"yr2_{key}"] = val

            monthly = self._two_year_average_monthly(
                year1_adjusted, year2_adjusted, len(tax_years) >= 2
            )

            results.append(QualifyingIncomeBreakdown(
                source_label=f"Schedule C - {biz_name}",
                year1_amount=year1_sc.net_profit_or_loss if year1_sc else ZERO,
                year2_amount=year2_sc.net_profit_or_loss if year2_sc else ZERO,
                addbacks=all_addbacks,
                year1_adjusted=year1_adjusted,
                year2_adjusted=year2_adjusted,
                two_year_total=year1_adjusted + year2_adjusted,
                monthly_qualifying=monthly,
                methodology="2_YEAR_AVERAGE" if len(tax_years) >= 2 else "1_YEAR",
                notes="Net profit + depreciation, amortization, casualty loss, 50% meals, and home office add-backs.",
            ))

        return results

    def _qualify_schedule_e_income(
        self, schedule_es: List[ScheduleEAnalysis], tax_years: List[int]
    ) -> List[QualifyingIncomeBreakdown]:
        """Derive rental qualifying income from Schedule E using Fannie Mae 75% rule."""
        if not schedule_es:
            return []

        year1_se = self._get_for_year(schedule_es, tax_years, 0)
        year2_se = self._get_for_year(schedule_es, tax_years, 1)

        year1_qualifying = year1_se.fannie_mae_qualifying_rental if year1_se else ZERO
        year2_qualifying = year2_se.fannie_mae_qualifying_rental if year2_se else ZERO

        if year1_qualifying == ZERO and year2_qualifying == ZERO:
            return []

        addbacks: Dict[str, Decimal] = {}
        if year1_se and year1_se.total_depreciation > ZERO:
            addbacks["yr1_depreciation"] = year1_se.total_depreciation
        if year2_se and year2_se.total_depreciation > ZERO:
            addbacks["yr2_depreciation"] = year2_se.total_depreciation

        monthly = self._two_year_average_monthly(
            year1_qualifying, year2_qualifying, len(tax_years) >= 2
        )

        # Negative rental income reduces qualifying income (impacts DTI)
        notes = "Fannie Mae 75% rule: (net rental + depreciation) * 75%."
        if monthly < ZERO:
            notes += " Negative rental income will increase DTI."

        return [QualifyingIncomeBreakdown(
            source_label="Schedule E - Rental Income",
            year1_amount=year1_se.net_rental_income if year1_se else ZERO,
            year2_amount=year2_se.net_rental_income if year2_se else ZERO,
            addbacks=addbacks,
            year1_adjusted=year1_qualifying,
            year2_adjusted=year2_qualifying,
            two_year_total=year1_qualifying + year2_qualifying,
            monthly_qualifying=monthly,
            methodology="FANNIE_MAE_75PCT",
            notes=notes,
        )]

    def _qualify_k1_income(
        self, k1s: List[K1Analysis], tax_years: List[int]
    ) -> List[QualifyingIncomeBreakdown]:
        """Derive qualifying income from K-1 forms."""
        if not k1s:
            return []

        # Group by entity
        entities: Dict[str, List[K1Analysis]] = {}
        for k1 in k1s:
            key = k1.entity_name or k1.ein or "Unknown Entity"
            entities.setdefault(key, []).append(k1)

        results = []
        for entity_name, entity_k1s in entities.items():
            year1_k1 = self._get_for_year(entity_k1s, tax_years, 0)
            year2_k1 = self._get_for_year(entity_k1s, tax_years, 1)

            def k1_qualifying(k1: Optional[K1Analysis]) -> Decimal:
                if not k1:
                    return ZERO
                # Ordinary business income + guaranteed payments
                total = k1.ordinary_business_income + k1.guaranteed_payments
                # Add net rental from K-1 if positive
                if k1.net_rental_income > ZERO:
                    total += k1.net_rental_income
                return total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            year1_adj = k1_qualifying(year1_k1)
            year2_adj = k1_qualifying(year2_k1)

            monthly = self._two_year_average_monthly(year1_adj, year2_adj, len(tax_years) >= 2)

            subtracted: Dict[str, Decimal] = {}
            # Flag if distributions significantly exceed income (potential concern)
            if year1_k1 and year1_k1.distributions > ZERO:
                if year1_k1.distributions > year1_adj * Decimal("1.5") and year1_adj > ZERO:
                    subtracted["yr1_excess_distributions_note"] = year1_k1.distributions - year1_adj

            notes = f"K-1 ({entity_k1s[0].entity_type}): ordinary income + guaranteed payments."
            if any(k.at_risk_limitation for k in entity_k1s):
                notes += " At-risk limitation applies."
            if any(k.passive_activity_limitation for k in entity_k1s):
                notes += " Passive activity limitation applies."

            results.append(QualifyingIncomeBreakdown(
                source_label=f"K-1 - {entity_name}",
                year1_amount=year1_adj,
                year2_amount=year2_adj,
                subtracted_items=subtracted,
                year1_adjusted=year1_adj,
                year2_adjusted=year2_adj,
                two_year_total=year1_adj + year2_adj,
                monthly_qualifying=monthly,
                methodology="2_YEAR_AVERAGE" if len(tax_years) >= 2 else "1_YEAR",
                notes=notes,
            ))

        return results

    def _qualify_corporate_income(
        self, corporate_returns: List[CorporateReturnAnalysis], tax_years: List[int]
    ) -> List[QualifyingIncomeBreakdown]:
        """
        Derive qualifying income from corporate returns.

        For 1120S: borrower's share of (ordinary_income + depreciation + amortization
                   + depletion + meals) based on ownership percentage.
        For 1065:  borrower's share + guaranteed payments.
        For 1120:  dividends_paid or retained earnings analysis (C-Corp).
        """
        if not corporate_returns:
            return []

        # Group by entity
        entities: Dict[str, List[CorporateReturnAnalysis]] = {}
        for cr in corporate_returns:
            key = cr.entity_name or cr.ein or f"Unknown ({cr.form_type})"
            entities.setdefault(key, []).append(cr)

        results = []
        for entity_name, entity_returns in entities.items():
            year1_cr = self._get_for_year(entity_returns, tax_years, 0)
            year2_cr = self._get_for_year(entity_returns, tax_years, 1)

            def corp_qualifying(cr: Optional[CorporateReturnAnalysis]) -> Tuple[Decimal, Dict[str, Decimal]]:
                if not cr:
                    return ZERO, {}

                addbacks: Dict[str, Decimal] = {}
                ownership = cr.ownership_pct / Decimal("100") if cr.ownership_pct and cr.ownership_pct > ZERO else Decimal("1")

                if cr.form_type == "1120S":
                    base = cr.ordinary_income
                    if cr.depreciation > ZERO:
                        addbacks["depreciation"] = cr.depreciation
                        base += cr.depreciation
                    if cr.amortization > ZERO:
                        addbacks["amortization"] = cr.amortization
                        base += cr.amortization
                    if cr.depletion > ZERO:
                        addbacks["depletion"] = cr.depletion
                        base += cr.depletion
                    if cr.meals_entertainment > ZERO:
                        addbacks["meals_entertainment"] = cr.meals_entertainment
                        base += cr.meals_entertainment
                    adjusted = (base * ownership).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                elif cr.form_type == "1065":
                    base = cr.ordinary_income + cr.guaranteed_payments
                    if cr.depreciation > ZERO:
                        addbacks["depreciation"] = cr.depreciation
                        base += cr.depreciation
                    if cr.amortization > ZERO:
                        addbacks["amortization"] = cr.amortization
                        base += cr.amortization
                    adjusted = (base * ownership).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                elif cr.form_type == "1120":
                    # C-Corp: use net income; dividends are separate
                    base = cr.net_income
                    if cr.depreciation > ZERO:
                        addbacks["depreciation"] = cr.depreciation
                        base += cr.depreciation
                    adjusted = (base * ownership).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    if cr.dividends_paid > ZERO:
                        addbacks["dividends_paid_info"] = cr.dividends_paid
                else:
                    adjusted = ZERO

                return adjusted, addbacks

            year1_adj, yr1_ab = corp_qualifying(year1_cr)
            year2_adj, yr2_ab = corp_qualifying(year2_cr)

            all_addbacks: Dict[str, Decimal] = {}
            for k, v in yr1_ab.items():
                all_addbacks[f"yr1_{k}"] = v
            for k, v in yr2_ab.items():
                all_addbacks[f"yr2_{k}"] = v

            monthly = self._two_year_average_monthly(year1_adj, year2_adj, len(tax_years) >= 2)

            form_type = entity_returns[0].form_type
            results.append(QualifyingIncomeBreakdown(
                source_label=f"Form {form_type} - {entity_name}",
                year1_amount=year1_cr.ordinary_income if year1_cr else ZERO,
                year2_amount=year2_cr.ordinary_income if year2_cr else ZERO,
                addbacks=all_addbacks,
                year1_adjusted=year1_adj,
                year2_adjusted=year2_adj,
                two_year_total=year1_adj + year2_adj,
                monthly_qualifying=monthly,
                methodology="2_YEAR_AVERAGE" if len(tax_years) >= 2 else "1_YEAR",
                notes=f"Form {form_type}: ordinary income with depreciation/amortization add-backs, ownership-adjusted.",
            ))

        return results

    # =========================================================================
    # 9. INCOME TREND ANALYSIS
    # =========================================================================

    def _analyze_income_trend(
        self,
        form_1040s: List[Form1040Analysis],
        schedule_cs: List[ScheduleCAnalysis],
        schedule_es: List[ScheduleEAnalysis],
        k1s: List[K1Analysis],
        corporate_returns: List[CorporateReturnAnalysis],
        tax_years: List[int],
    ) -> Tuple[str, Optional[Decimal]]:
        """
        Analyze year-over-year income trend across all sources.

        Returns (trend_label, yoy_change_pct).
        """
        if len(tax_years) < 2:
            return "INSUFFICIENT_DATA", None

        # Use AGI from 1040 as the primary trend indicator
        year1_1040 = self._get_for_year(form_1040s, tax_years, 0)
        year2_1040 = self._get_for_year(form_1040s, tax_years, 1)

        if year1_1040 and year2_1040 and year2_1040.agi != ZERO:
            year1_agi = year1_1040.agi
            year2_agi = year2_1040.agi

            if year2_agi != ZERO:
                yoy_pct = ((year1_agi - year2_agi) / abs(year2_agi) * Decimal("100")).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                yoy_pct = None

            if yoy_pct is not None:
                if yoy_pct < -DECLINING_INCOME_CRITICAL_PCT:
                    return "DECLINING", yoy_pct
                elif yoy_pct < -DECLINING_INCOME_WARN_PCT:
                    return "DECLINING", yoy_pct
                elif yoy_pct > DECLINING_INCOME_WARN_PCT:
                    return "INCREASING", yoy_pct
                else:
                    return "STABLE", yoy_pct

        # Fallback: check Schedule C trend for self-employed
        if schedule_cs:
            year1_sc = self._get_for_year(schedule_cs, tax_years, 0)
            year2_sc = self._get_for_year(schedule_cs, tax_years, 1)
            if year1_sc and year2_sc and year2_sc.net_profit_or_loss != ZERO:
                yoy_pct = (
                    (year1_sc.net_profit_or_loss - year2_sc.net_profit_or_loss)
                    / abs(year2_sc.net_profit_or_loss)
                    * Decimal("100")
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                if yoy_pct < -DECLINING_INCOME_WARN_PCT:
                    return "DECLINING", yoy_pct
                elif yoy_pct > DECLINING_INCOME_WARN_PCT:
                    return "INCREASING", yoy_pct
                else:
                    return "STABLE", yoy_pct

        return "INSUFFICIENT_DATA", None

    # =========================================================================
    # 10. RED FLAG DETECTION
    # =========================================================================

    def _detect_red_flags(
        self,
        form_1040s: List[Form1040Analysis],
        schedule_cs: List[ScheduleCAnalysis],
        schedule_es: List[ScheduleEAnalysis],
        k1s: List[K1Analysis],
        corporate_returns: List[CorporateReturnAnalysis],
        income_trend: str,
        yoy_change: Optional[Decimal],
        tax_years: List[int],
    ) -> List[RedFlag]:
        """
        Detect underwriting red flags across all tax return data.

        Checks for:
        - Declining income trend
        - Large one-time capital gains
        - Net operating losses
        - IRS payment plans (from 1040 data)
        - Amended returns
        - Extension filings
        - Business losses
        - Excessive depreciation vs income
        """
        flags: List[RedFlag] = []

        # --- Declining Income ---
        if income_trend == "DECLINING" and yoy_change is not None:
            severity = (
                RedFlagSeverity.CRITICAL
                if yoy_change < -DECLINING_INCOME_CRITICAL_PCT
                else RedFlagSeverity.WARNING
            )
            flags.append(RedFlag(
                flag_type="DECLINING_INCOME",
                severity=severity,
                description=f"Income declined {abs(yoy_change)}% year-over-year.",
                impact_on_income=yoy_change,
                recommendation=(
                    "Obtain letter of explanation for income decline. "
                    "If decline is >25%, most guidelines require using the lower year only."
                ),
            ))

        # --- Only 1 year of returns ---
        if len(tax_years) < 2:
            flags.append(RedFlag(
                flag_type="INSUFFICIENT_HISTORY",
                severity=RedFlagSeverity.WARNING,
                description="Only 1 year of tax returns available. Most guidelines require 2 years.",
                recommendation="Request prior year tax return. If self-employed < 2 years, verify with CPA letter.",
            ))

        # --- Capital Gains (non-recurring) ---
        for f1040 in form_1040s:
            if f1040.capital_gains > CAPITAL_GAINS_RECURRING_THRESHOLD:
                flags.append(RedFlag(
                    flag_type="ONE_TIME_CAPITAL_GAINS",
                    severity=RedFlagSeverity.WARNING,
                    description=(
                        f"Capital gains of {self._fmt_currency(f1040.capital_gains)} in {f1040.tax_year}. "
                        "Large capital gains may not be recurring and should be excluded from qualifying income."
                    ),
                    impact_on_income=-f1040.capital_gains,
                    recommendation=(
                        "Verify if capital gains are recurring (3-year pattern) or one-time. "
                        "One-time gains must be subtracted from qualifying income."
                    ),
                ))

        # --- Amended Returns ---
        for f1040 in form_1040s:
            if f1040.is_amended:
                flags.append(RedFlag(
                    flag_type="AMENDED_RETURN",
                    severity=RedFlagSeverity.WARNING,
                    description=f"Tax year {f1040.tax_year} is an amended return (Form 1040-X).",
                    recommendation="Obtain IRS transcript to verify. Amended returns require additional scrutiny.",
                ))

        # --- Extension Filings ---
        for f1040 in form_1040s:
            if f1040.is_extension:
                flags.append(RedFlag(
                    flag_type="EXTENSION_FILED",
                    severity=RedFlagSeverity.INFO,
                    description=f"Tax year {f1040.tax_year} was filed on extension.",
                    recommendation="Verify return was actually filed. Obtain IRS tax transcript for confirmation.",
                ))

        # --- Net Operating Losses (Schedule C) ---
        for sc in schedule_cs:
            if sc.net_profit_or_loss < ZERO:
                flags.append(RedFlag(
                    flag_type="BUSINESS_LOSS",
                    severity=RedFlagSeverity.CRITICAL if sc.net_profit_or_loss < Decimal("-10000") else RedFlagSeverity.WARNING,
                    description=(
                        f"Schedule C loss of {self._fmt_currency(sc.net_profit_or_loss)} "
                        f"for {sc.business_name or 'business'} in {sc.tax_year}."
                    ),
                    impact_on_income=sc.net_profit_or_loss,
                    recommendation=(
                        "Business losses reduce qualifying income. If loss is in most recent year, "
                        "it must be counted. Obtain YTD P&L and explain business viability."
                    ),
                ))

        # --- Negative Rental Income ---
        for se in schedule_es:
            if se.fannie_mae_qualifying_rental < ZERO:
                flags.append(RedFlag(
                    flag_type="NEGATIVE_RENTAL_INCOME",
                    severity=RedFlagSeverity.WARNING,
                    description=(
                        f"Net negative rental income of {self._fmt_currency(se.fannie_mae_qualifying_rental)} "
                        f"in {se.tax_year} (after Fannie Mae 75% calculation)."
                    ),
                    impact_on_income=se.fannie_mae_qualifying_rental,
                    recommendation="Negative rental income must be added to monthly obligations in DTI calculation.",
                ))

        # --- K-1 Loss Limitations ---
        for k1 in k1s:
            if k1.at_risk_limitation or k1.passive_activity_limitation:
                flags.append(RedFlag(
                    flag_type="K1_LOSS_LIMITATION",
                    severity=RedFlagSeverity.INFO,
                    description=(
                        f"K-1 for {k1.entity_name or 'entity'} in {k1.tax_year} "
                        f"has loss limitations (at-risk: {k1.at_risk_limitation}, "
                        f"passive: {k1.passive_activity_limitation})."
                    ),
                    recommendation="Verify losses are not being used to offset other income improperly.",
                ))

            # Distributions significantly exceeding income
            if k1.distributions > ZERO and k1.ordinary_business_income > ZERO:
                if k1.distributions > k1.ordinary_business_income * Decimal("2"):
                    flags.append(RedFlag(
                        flag_type="EXCESS_DISTRIBUTIONS",
                        severity=RedFlagSeverity.INFO,
                        description=(
                            f"K-1 distributions ({self._fmt_currency(k1.distributions)}) "
                            f"exceed ordinary income ({self._fmt_currency(k1.ordinary_business_income)}) "
                            f"by more than 2x in {k1.tax_year}."
                        ),
                        recommendation=(
                            "Large distributions relative to income may indicate capital being returned. "
                            "Verify business sustainability."
                        ),
                    ))

        # --- IRS Payment Plans (detected from 1040 data) ---
        for f1040 in form_1040s:
            if f1040.total_tax > ZERO and f1040.taxes_paid > ZERO:
                underpayment = f1040.total_tax - f1040.taxes_paid
                if underpayment > Decimal("5000"):
                    flags.append(RedFlag(
                        flag_type="TAX_UNDERPAYMENT",
                        severity=RedFlagSeverity.WARNING,
                        description=(
                            f"Potential tax underpayment of {self._fmt_currency(underpayment)} "
                            f"in {f1040.tax_year}. May indicate IRS payment plan."
                        ),
                        recommendation=(
                            "Request IRS payment plan documentation. "
                            "Monthly payments must be included in DTI."
                        ),
                    ))

        return flags

    # =========================================================================
    # 11. CONFIDENCE SCORING
    # =========================================================================

    def _calculate_confidence(
        self,
        form_1040s: List[Form1040Analysis],
        schedule_cs: List[ScheduleCAnalysis],
        tax_years: List[int],
        red_flags: List[RedFlag],
    ) -> int:
        """
        Calculate confidence score (0-100) for the analysis.

        Higher confidence when:
        - 2 full years of returns available
        - AGI is populated and consistent
        - Few or no red flags
        - Income is stable or increasing

        Lower confidence when:
        - Only 1 year available
        - Missing key data
        - Multiple critical red flags
        """
        score = 50  # Base score

        # 2 years of returns: +20
        if len(tax_years) >= 2:
            score += 20
        # Only 1 year: -10
        elif len(tax_years) == 1:
            score -= 10

        # AGI populated on both years: +10
        agi_years = sum(1 for f in form_1040s if f.agi > ZERO)
        if agi_years >= 2:
            score += 10
        elif agi_years == 1:
            score += 5

        # Schedules parsed successfully: +10
        if schedule_cs:
            score += 5
        if form_1040s:
            score += 5

        # Deductions for red flags
        critical_flags = sum(1 for f in red_flags if f.severity == RedFlagSeverity.CRITICAL)
        warning_flags = sum(1 for f in red_flags if f.severity == RedFlagSeverity.WARNING)
        score -= critical_flags * 10
        score -= warning_flags * 5

        return max(0, min(100, score))

    # =========================================================================
    # 12. TASK GENERATION
    # =========================================================================

    def _generate_tasks(
        self,
        red_flags: List[RedFlag],
        tax_years: List[int],
        form_1040s: List[Form1040Analysis],
    ) -> List[Dict]:
        """
        Generate LO follow-up tasks based on red flags and analysis gaps.
        """
        tasks: List[Dict] = []

        # Task for each critical red flag
        for flag in red_flags:
            if flag.severity in (RedFlagSeverity.CRITICAL, RedFlagSeverity.WARNING):
                tasks.append({
                    "type": "REVIEW_TAX_RETURN_FLAG",
                    "priority": "HIGH" if flag.severity == RedFlagSeverity.CRITICAL else "MEDIUM",
                    "title": f"Tax Return: {flag.flag_type.replace('_', ' ').title()}",
                    "description": flag.description,
                    "recommendation": flag.recommendation,
                    "auto_generated": True,
                })

        # Request missing year
        if len(tax_years) < 2:
            tasks.append({
                "type": "REQUEST_DOCUMENT",
                "priority": "HIGH",
                "title": "Request Prior Year Tax Return",
                "description": "Only 1 year of tax returns on file. Request the prior year for 2-year average calculation.",
                "recommendation": "Upload the borrower's second most recent year Form 1040 with all schedules.",
                "auto_generated": True,
            })

        # Request IRS transcripts for amended returns
        for f1040 in form_1040s:
            if f1040.is_amended:
                tasks.append({
                    "type": "REQUEST_DOCUMENT",
                    "priority": "HIGH",
                    "title": f"Request IRS Transcript for {f1040.tax_year}",
                    "description": f"Amended return filed for {f1040.tax_year}. IRS transcript required for verification.",
                    "recommendation": "Order IRS Form 4506-C transcript to verify amended return was processed.",
                    "auto_generated": True,
                })

        return tasks

    # =========================================================================
    # 13. PERSISTENCE
    # =========================================================================

    def _save_analysis(self, result: TaxReturnAnalysisResult, duration_ms: int) -> None:
        """
        Persist the analysis result to the income_calculations table and
        create income_verification_tasks for LO review.
        """
        try:
            # Save to income_calculations
            self.db.execute(text("""
                INSERT INTO income_calculations (
                    loan_id, borrower_id, calculation_type,
                    total_monthly_income, total_annual_income,
                    calculation_method, confidence_score,
                    income_trend, yoy_change_pct,
                    red_flags, analysis_details,
                    processing_time_ms, created_at
                ) VALUES (
                    :loan_id, :borrower_id, 'TAX_RETURN_ANALYSIS',
                    :monthly, :annual,
                    :method, :confidence,
                    :trend, :yoy,
                    :flags, :details,
                    :duration, CURRENT_TIMESTAMP
                )
                ON CONFLICT (loan_id, borrower_id, calculation_type)
                DO UPDATE SET
                    total_monthly_income = EXCLUDED.total_monthly_income,
                    total_annual_income = EXCLUDED.total_annual_income,
                    calculation_method = EXCLUDED.calculation_method,
                    confidence_score = EXCLUDED.confidence_score,
                    income_trend = EXCLUDED.income_trend,
                    yoy_change_pct = EXCLUDED.yoy_change_pct,
                    red_flags = EXCLUDED.red_flags,
                    analysis_details = EXCLUDED.analysis_details,
                    processing_time_ms = EXCLUDED.processing_time_ms,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "loan_id": result.loan_id,
                "borrower_id": result.borrower_id,
                "monthly": float(result.total_monthly_qualifying_income),
                "annual": float(result.total_annual_qualifying_income),
                "method": result.analysis_method,
                "confidence": result.confidence,
                "trend": result.income_trend,
                "yoy": float(result.yoy_change_pct) if result.yoy_change_pct is not None else None,
                "flags": json.dumps([{
                    "type": f.flag_type,
                    "severity": f.severity.value,
                    "description": f.description,
                    "impact": float(f.impact_on_income) if f.impact_on_income else None,
                    "recommendation": f.recommendation,
                } for f in result.red_flags]),
                "details": json.dumps({
                    "tax_years": result.tax_years_analyzed,
                    "breakdown": [{
                        "source": b.source_label,
                        "yr1": float(b.year1_amount),
                        "yr2": float(b.year2_amount),
                        "yr1_adj": float(b.year1_adjusted),
                        "yr2_adj": float(b.year2_adjusted),
                        "monthly": float(b.monthly_qualifying),
                        "method": b.methodology,
                    } for b in result.qualifying_income_breakdown],
                }),
                "duration": duration_ms,
            })

            # Create tasks
            for task_def in result.tasks_to_create:
                self.db.execute(text("""
                    INSERT INTO income_verification_tasks (
                        loan_id, borrower_id, task_type, priority,
                        title, description, recommendation,
                        status, auto_generated, created_at
                    ) VALUES (
                        :loan_id, :borrower_id, :task_type, :priority,
                        :title, :description, :recommendation,
                        'OPEN', :auto_gen, CURRENT_TIMESTAMP
                    )
                """), {
                    "loan_id": result.loan_id,
                    "borrower_id": result.borrower_id,
                    "task_type": task_def["type"],
                    "priority": task_def["priority"],
                    "title": task_def["title"],
                    "description": task_def["description"],
                    "recommendation": task_def.get("recommendation", ""),
                    "auto_gen": task_def.get("auto_generated", True),
                })

            self.db.commit()
            logger.info(
                f"Tax return analysis saved: loan={result.loan_id} "
                f"monthly={result.total_monthly_qualifying_income} "
                f"flags={len(result.red_flags)} tasks={len(result.tasks_to_create)} "
                f"duration={duration_ms}ms"
            )

        except Exception as e:
            logger.error(f"Failed to save tax return analysis: {e}")
            self.db.rollback()

    # =========================================================================
    # 14. UTILITY METHODS
    # =========================================================================

    def _to_decimal(self, value: Any) -> Decimal:
        """Safely convert a value to Decimal, returning ZERO on failure."""
        if value is None:
            return ZERO
        try:
            if isinstance(value, Decimal):
                return value
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
                if not value or value == "-":
                    return ZERO
            return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return ZERO

    def _extract_tax_year(self, doc: Dict, fields: Optional[Dict] = None) -> Optional[int]:
        """
        Extract tax year from document metadata or extracted fields.
        Tries multiple locations: extraction tax_year column, extracted_fields,
        filename patterns.
        """
        # From extraction table column
        if doc.get("tax_year"):
            try:
                return int(doc["tax_year"])
            except (ValueError, TypeError):
                pass

        # From extracted fields
        if fields is None:
            fields = doc.get("extracted_fields", {})

        for key in ("tax_year", "year", "taxYear", "tax_period"):
            val = fields.get(key)
            if val:
                try:
                    year = int(str(val).strip()[:4])
                    if 2000 <= year <= 2099:
                        return year
                except (ValueError, TypeError):
                    pass

        # From filename (e.g., "2024_1040.pdf")
        filename = doc.get("filename", "")
        import re
        year_match = re.search(r'(20[0-9]{2})', filename)
        if year_match:
            return int(year_match.group(1))

        return None

    def _get_for_year(self, items: List, tax_years: List[int], index: int) -> Optional[Any]:
        """
        Get item for a specific year index (0 = most recent, 1 = prior).
        Items must have a .tax_year attribute.
        """
        if index >= len(tax_years):
            return None
        target_year = tax_years[index]
        for item in items:
            if item.tax_year == target_year:
                return item
        return None

    def _two_year_average_monthly(
        self, year1: Decimal, year2: Decimal, has_two_years: bool
    ) -> Decimal:
        """
        Calculate monthly qualifying income using 2-year average.

        If only 1 year available, use that year divided by 12.
        If declining and year1 < year2, some guidelines require using lower year only.
        Standard: (year1 + year2) / 24 months.
        """
        if has_two_years and year2 != ZERO:
            # Standard 2-year average: total / 24 months
            total = year1 + year2
            monthly = (total / Decimal("24")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            # Single year: divide by 12
            monthly = (year1 / Decimal("12")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return monthly

    def _fmt_currency(self, amount: Decimal) -> str:
        """Format a Decimal as a currency string."""
        if amount < ZERO:
            return f"-${abs(float(amount)):,.2f}"
        return f"${float(amount):,.2f}"

    def _empty_result(
        self,
        loan_id: int,
        borrower_id: int,
        error: Optional[str] = None,
        flags: Optional[List[RedFlag]] = None,
    ) -> TaxReturnAnalysisResult:
        """Create an empty/error result."""
        return TaxReturnAnalysisResult(
            loan_id=loan_id,
            borrower_id=borrower_id,
            tax_years_analyzed=[],
            form_1040s=[],
            schedule_cs=[],
            schedule_es=[],
            k1s=[],
            corporate_returns=[],
            qualifying_income_breakdown=[],
            total_monthly_qualifying_income=ZERO,
            total_annual_qualifying_income=ZERO,
            income_trend="INSUFFICIENT_DATA",
            yoy_change_pct=None,
            red_flags=flags or [],
            tasks_to_create=[],
            confidence=0,
            analysis_method="none",
            success=error is None,
            error=error,
        )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_tax_return_analyzer(db: Session) -> TaxReturnAnalyzerService:
    """
    Factory function returning a TaxReturnAnalyzerService for the given
    database session.

    Not a true singleton because each request may have a different DB session,
    but the service itself is lightweight and stateless beyond the session.
    """
    return TaxReturnAnalyzerService(db)
