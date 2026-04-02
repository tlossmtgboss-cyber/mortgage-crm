"""
Employment Gap Analysis Service for Mortgage Underwriting

Identifies, classifies, and evaluates gaps in employment history — a critical
factor in mortgage qualification. Cross-references W-2 history, VOE data,
paystub dates, and tax return income to detect periods of unemployment, then
applies Fannie Mae (B3-3.1-09), FHA (4000.1 II.A.4.c), and VA guidelines
to determine impact on qualifying income.

Integrates with:
    - smart_documents / smart_document_extractions for W-2/paystub/VOE data
    - income_calculations / income_sources for persistence
    - income_verification_tasks for LO follow-up items
    - ai_resilience for AI call protection

Key analysis areas:
    1. Gap detection across W-2 history, VOE, and paystub timelines
    2. Gap classification (SHORT / MODERATE / SIGNIFICANT / EXTENDED)
    3. Explanation analysis — acceptable vs concerning reasons
    4. Income calculation impact per loan program guidelines
    5. Return-to-work stability assessment
    6. Multiple/concurrent job analysis
    7. Self-employment transition detection
    8. Industry continuity and career pattern evaluation

Usage:
    from services.smart_docs.income.employment_gap_service import (
        get_employment_gap_service,
        EmploymentGapService,
    )

    service = get_employment_gap_service(db)
    result = await service.analyze_employment_history(
        org_id=1, borrower_id=42, employment_data=data,
    )
"""

from __future__ import annotations

import logging
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
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


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

# Gap classification thresholds (calendar days)
SHORT_GAP_MAX_DAYS = 30
MODERATE_GAP_MAX_DAYS = 90
SIGNIFICANT_GAP_MAX_DAYS = 180

# Minimum employment duration thresholds
MIN_CURRENT_EMPLOYMENT_MONTHS = 6   # Preferred months in current role
MIN_RETURN_STABILITY_MONTHS = 3     # Minimum months to assess return-to-work

# Fannie Mae: generally 2 years in same line of work
FNMA_EMPLOYMENT_HISTORY_YEARS = 2
# FHA: 2 years employment history required
FHA_EMPLOYMENT_HISTORY_YEARS = 2
# Self-employment: 2 years SE history required
SE_HISTORY_YEARS = 2
# Second job: 2-year history required to count income
SECOND_JOB_HISTORY_YEARS = 2

# Income adjustment: gaps within this many years affect averaging
INCOME_IMPACT_LOOKBACK_YEARS = 2

# Document types relevant to employment gap analysis
EMPLOYMENT_DOC_TYPES = ("W2", "PAYSTUB", "VOE", "TAX_RETURN")

# LOE (Letter of Explanation) template types
LOE_TEMPLATE_MAP = {
    "education": "LOE_EDUCATION",
    "medical": "LOE_MEDICAL",
    "military_deployment": "LOE_MILITARY",
    "maternity_paternity": "LOE_FAMILY_LEAVE",
    "relocation": "LOE_RELOCATION",
    "termination": "LOE_TERMINATION",
    "industry_change": "LOE_CAREER_CHANGE",
    "unexplained": "LOE_GENERAL",
}


# =============================================================================
# ENUMS
# =============================================================================

class GapClassification(str, Enum):
    """Employment gap severity classification."""
    SHORT = "SHORT"                 # < 30 days: acceptable, likely between jobs
    MODERATE = "MODERATE"           # 30-90 days: requires LOE
    SIGNIFICANT = "SIGNIFICANT"     # 90-180 days: requires LOE + documentation
    EXTENDED = "EXTENDED"           # > 180 days: red flag, may disqualify income type


class GapReason(str, Enum):
    """Categorized reasons for employment gaps."""
    EDUCATION = "education"
    MEDICAL = "medical"
    MILITARY_DEPLOYMENT = "military_deployment"
    MATERNITY_PATERNITY = "maternity_paternity"
    RELOCATION = "relocation"
    TERMINATION = "termination"
    INDUSTRY_CHANGE = "industry_change"
    SEASONAL_EMPLOYMENT = "seasonal_employment"
    CAREGIVING = "caregiving"
    UNEXPLAINED = "unexplained"


class ReasonAcceptability(str, Enum):
    """How acceptable a gap reason is for underwriting."""
    ACCEPTABLE = "acceptable"
    CONDITIONAL = "conditional"     # Acceptable with documentation
    CONCERNING = "concerning"


class EmploymentTransition(str, Enum):
    """Type of employment transition across a gap."""
    SAME_EMPLOYER = "same_employer"         # Rehire or return from leave
    SAME_INDUSTRY = "same_industry"         # Changed employer, same field
    DIFFERENT_INDUSTRY = "different_industry"
    W2_TO_SELF_EMPLOYED = "w2_to_self_employed"
    SELF_EMPLOYED_TO_W2 = "self_employed_to_w2"
    PART_TIME_TO_FULL_TIME = "part_time_to_full_time"
    FULL_TIME_TO_PART_TIME = "full_time_to_part_time"
    UNKNOWN = "unknown"


class ContinuityRating(str, Enum):
    """Overall employment continuity rating."""
    STRONG = "strong"           # Continuous, same industry, advancement
    ADEQUATE = "adequate"       # Minor gaps, generally stable
    MARGINAL = "marginal"       # Notable gaps or industry changes
    WEAK = "weak"               # Extended gaps, frequent changes


# =============================================================================
# REASON ACCEPTABILITY MAPPING
# =============================================================================

_REASON_ACCEPTABILITY: Dict[GapReason, ReasonAcceptability] = {
    GapReason.EDUCATION: ReasonAcceptability.ACCEPTABLE,
    GapReason.MEDICAL: ReasonAcceptability.ACCEPTABLE,
    GapReason.MILITARY_DEPLOYMENT: ReasonAcceptability.ACCEPTABLE,
    GapReason.MATERNITY_PATERNITY: ReasonAcceptability.ACCEPTABLE,
    GapReason.RELOCATION: ReasonAcceptability.ACCEPTABLE,
    GapReason.SEASONAL_EMPLOYMENT: ReasonAcceptability.CONDITIONAL,
    GapReason.CAREGIVING: ReasonAcceptability.CONDITIONAL,
    GapReason.TERMINATION: ReasonAcceptability.CONCERNING,
    GapReason.INDUSTRY_CHANGE: ReasonAcceptability.CONCERNING,
    GapReason.UNEXPLAINED: ReasonAcceptability.CONCERNING,
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class EmploymentRecord:
    """A single period of employment derived from documents."""
    employer_name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None       # None means current/ongoing
    job_title: Optional[str] = None
    industry: Optional[str] = None
    employment_type: str = "full_time"     # full_time, part_time, self_employed
    is_current: bool = False
    annual_income: Optional[Decimal] = None
    source_doc_ids: List[int] = field(default_factory=list)
    source_doc_types: List[str] = field(default_factory=list)

    @property
    def duration_days(self) -> Optional[int]:
        if self.start_date is None:
            return None
        end = self.end_date or date.today()
        return (end - self.start_date).days

    @property
    def duration_months(self) -> Optional[float]:
        days = self.duration_days
        if days is None:
            return None
        return round(days / 30.44, 1)


@dataclass
class EmploymentGap:
    """A detected gap between two employment periods."""
    gap_start: date
    gap_end: date
    days: int
    classification: GapClassification
    employer_before: Optional[str] = None
    employer_after: Optional[str] = None
    industry_before: Optional[str] = None
    industry_after: Optional[str] = None
    transition_type: EmploymentTransition = EmploymentTransition.UNKNOWN
    reason: Optional[GapReason] = None
    reason_acceptability: Optional[ReasonAcceptability] = None
    explanation_text: Optional[str] = None
    explanation_adequate: Optional[bool] = None
    supporting_doc_ids: List[int] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    @property
    def months(self) -> float:
        return round(self.days / 30.44, 1)

    @property
    def in_last_two_years(self) -> bool:
        cutoff = date.today() - timedelta(days=INCOME_IMPACT_LOOKBACK_YEARS * 365)
        return self.gap_end >= cutoff


@dataclass
class GapEvaluation:
    """Result of evaluating a single employment gap."""
    gap: EmploymentGap
    requires_loe: bool
    requires_documentation: bool
    income_impact: str               # 'none', 'adjustment_needed', 'disqualifying'
    income_adjustment_factor: Optional[Decimal] = None
    documentation_requirements: List[str] = field(default_factory=list)
    underwriting_notes: List[str] = field(default_factory=list)
    risk_level: str = "low"          # low, medium, high, critical


@dataclass
class DocRequirement:
    """A specific document requirement generated from gap analysis."""
    doc_type: str                    # e.g. "LOE", "VOE", "school_transcript"
    description: str
    required: bool = True            # required vs recommended
    gap_reference: Optional[str] = None  # Which gap this relates to
    template_available: bool = False


@dataclass
class ReturnToWorkAssessment:
    """Assessment of a borrower who recently returned to the workforce."""
    is_return_to_work: bool
    months_in_current_position: Optional[float] = None
    prior_gap_months: Optional[float] = None
    income_stability: str = "unknown"    # stable, increasing, declining, insufficient_data
    meets_minimum_duration: bool = False
    same_field_as_education: Optional[bool] = None
    guideline_notes: List[str] = field(default_factory=list)


@dataclass
class ConcurrentEmployment:
    """Detection of overlapping employment periods."""
    employer_a: str
    employer_b: str
    overlap_start: date
    overlap_end: date
    overlap_days: int
    is_part_time_combo: bool = False
    combined_income: Optional[Decimal] = None


@dataclass
class ContinuityAssessment:
    """Overall employment continuity assessment."""
    rating: ContinuityRating
    total_employment_months: float
    total_gap_months: float
    employment_coverage_pct: float       # Percentage of lookback covered by employment
    industry_changes: int
    employer_count: int
    longest_tenure_months: float
    career_advancement: bool
    same_industry_throughout: bool
    notes: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)


@dataclass
class EmploymentAnalysis:
    """Complete employment gap analysis result."""
    org_id: int
    borrower_id: int
    employment_records: List[EmploymentRecord]
    gaps: List[EmploymentGap]
    gap_evaluations: List[GapEvaluation]
    continuity: ContinuityAssessment
    return_to_work: Optional[ReturnToWorkAssessment]
    concurrent_employment: List[ConcurrentEmployment]
    self_employment_transitions: List[Dict[str, Any]]
    documentation_requirements: List[DocRequirement]
    income_impact_summary: Dict[str, Any]
    flags: List[str]
    recommendations: List[str]
    confidence: int                  # 0-100
    analysis_timestamp: str = ""

    def __post_init__(self):
        if not self.analysis_timestamp:
            self.analysis_timestamp = datetime.now(timezone.utc).isoformat()


# =============================================================================
# SERVICE
# =============================================================================

class EmploymentGapService:
    """
    Analyzes employment history for gaps that impact mortgage qualification.

    Combines data from W-2s, VOE (Verification of Employment), paystubs,
    and tax returns to build a complete employment timeline, detect gaps,
    classify their severity, and determine documentation requirements per
    Fannie Mae/FHA/VA guidelines.
    """

    def __init__(self, db: Session):
        self.db = db
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def analyze_employment_history(
        self,
        org_id: int,
        borrower_id: int,
        employment_data: Optional[Dict[str, Any]] = None,
        loan_id: Optional[int] = None,
        loan_type: Optional[str] = None,
    ) -> EmploymentAnalysis:
        """
        Analyze complete employment history for a borrower.

        If ``employment_data`` is provided, it is used directly. Otherwise,
        employment records are gathered from smart_documents extractions
        for the given borrower within the organization.

        Args:
            org_id: Organization ID for tenant isolation.
            borrower_id: Borrower/lead ID.
            employment_data: Optional pre-assembled employment data dict with
                keys ``w2_history``, ``voe_data``, ``paystub_data``,
                ``tax_return_data``.
            loan_id: Optional loan ID for linking tasks.
            loan_type: Loan program (conventional, fha, va, usda) for
                guideline-specific rules.

        Returns:
            EmploymentAnalysis with gaps, evaluations, continuity, and
            documentation requirements.
        """
        try:
            # Step 1: build employment records
            if employment_data:
                records = self._build_records_from_data(employment_data)
            else:
                records = await self._gather_employment_records(
                    org_id, borrower_id, loan_id,
                )

            if not records:
                return self._empty_analysis(org_id, borrower_id)

            # Step 2: sort by start date
            records = self._sort_records(records)

            # Step 3: detect gaps
            gaps = self.detect_gaps_from_records(records)

            # Step 4: detect concurrent employment
            concurrent = self._detect_concurrent_employment(records)

            # Step 5: detect self-employment transitions
            se_transitions = self._detect_self_employment_transitions(records)

            # Step 6: evaluate each gap
            gap_evaluations = []
            for gap in gaps:
                evaluation = await self.evaluate_gap(
                    gap=gap,
                    explanation=gap.explanation_text,
                    supporting_docs=gap.supporting_doc_ids,
                    loan_type=loan_type,
                )
                gap_evaluations.append(evaluation)

            # Step 7: assess return-to-work if applicable
            return_to_work = self._assess_return_to_work(records, gaps)

            # Step 8: assess overall continuity
            continuity = self.assess_continuity(records, gaps)

            # Step 9: generate documentation requirements
            doc_requirements = self.get_documentation_requirements(
                gaps, gap_evaluations,
            )

            # Step 10: calculate income impact
            income_impact = self._calculate_income_impact(
                gaps, gap_evaluations, records, loan_type,
            )

            # Step 11: generate flags and recommendations
            flags = self._generate_flags(
                gaps, gap_evaluations, continuity, return_to_work,
                se_transitions, concurrent, loan_type,
            )
            recommendations = self._generate_recommendations(
                gaps, gap_evaluations, continuity, return_to_work,
                se_transitions, loan_type,
            )

            # Step 12: calculate confidence
            confidence = self._calculate_confidence(
                records, gaps, gap_evaluations, continuity,
            )

            # Step 13: persist tasks for LO review
            if loan_id:
                await self._persist_verification_tasks(
                    org_id, loan_id, borrower_id, gaps, gap_evaluations,
                    flags,
                )

            return EmploymentAnalysis(
                org_id=org_id,
                borrower_id=borrower_id,
                employment_records=records,
                gaps=gaps,
                gap_evaluations=gap_evaluations,
                continuity=continuity,
                return_to_work=return_to_work,
                concurrent_employment=concurrent,
                self_employment_transitions=se_transitions,
                documentation_requirements=doc_requirements,
                income_impact_summary=income_impact,
                flags=flags,
                recommendations=recommendations,
                confidence=confidence,
            )

        except Exception as e:
            logger.exception(
                "Employment gap analysis failed for org=%s borrower=%s: %s",
                org_id, borrower_id, e,
            )
            return self._empty_analysis(
                org_id, borrower_id, error=str(e),
            )

    # =========================================================================
    # 2. GATHER EMPLOYMENT RECORDS FROM DB
    # =========================================================================

    async def _gather_employment_records(
        self,
        org_id: int,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[EmploymentRecord]:
        """
        Query smart_documents + smart_document_extractions for W-2, paystub,
        VOE, and tax return documents, then extract employment periods.
        """
        filters = [
            "sd.organization_id = :org_id",
            "sd.borrower_id = :borrower_id",
            "sd.doc_type IN :doc_types",
            "sd.status NOT IN ('REJECTED', 'EXPIRED')",
        ]
        params: Dict[str, Any] = {
            "org_id": org_id,
            "borrower_id": borrower_id,
            "doc_types": tuple(EMPLOYMENT_DOC_TYPES),
        }

        if loan_id:
            filters.append("sd.loan_id = :loan_id")
            params["loan_id"] = loan_id

        where_sql = " AND ".join(filters)

        emp_query = (
            "SELECT"
            " sd.id AS doc_id,"
            " sd.doc_type AS doc_type,"
            " sd.uploaded_at AS uploaded_at,"
            " sde.extracted_fields AS extracted_fields,"
            " sde.overall_confidence AS overall_confidence"
            " FROM smart_documents sd"
            " LEFT JOIN smart_document_extractions sde"
            "     ON sde.document_id = sd.id"
            " WHERE " + where_sql
            + " ORDER BY sd.uploaded_at DESC"
        )
        rows = self.db.execute(text(emp_query), params).fetchall()

        records: List[EmploymentRecord] = []
        seen_employers: Dict[str, EmploymentRecord] = {}

        for row in rows:
            ef = row.extracted_fields
            if isinstance(ef, str):
                try:
                    ef = json.loads(ef)
                except (json.JSONDecodeError, TypeError):
                    ef = {}
            if not ef:
                continue

            doc_type = str(row.doc_type) if row.doc_type else None
            doc_id = row.doc_id

            if doc_type == "W2":
                record = self._extract_from_w2(ef, doc_id)
            elif doc_type == "PAYSTUB":
                record = self._extract_from_paystub(ef, doc_id)
            elif doc_type == "VOE":
                record = self._extract_from_voe(ef, doc_id)
            elif doc_type == "TAX_RETURN":
                record = self._extract_from_tax_return(ef, doc_id)
            else:
                continue

            if record is None:
                continue

            # Merge with existing record for the same employer to build
            # the most complete picture (e.g. W-2 gives dates, VOE gives
            # start/end, paystub gives current status).
            key = (record.employer_name or "").strip().lower()
            if key and key in seen_employers:
                self._merge_records(seen_employers[key], record)
            elif key:
                seen_employers[key] = record
                records.append(record)
            else:
                records.append(record)

        return records

    # =========================================================================
    # 3. DOCUMENT EXTRACTION HELPERS
    # =========================================================================

    def _extract_from_w2(
        self, ef: Dict[str, Any], doc_id: int,
    ) -> Optional[EmploymentRecord]:
        """Extract employment record from W-2 extracted fields."""
        employer = ef.get("employer_name")
        if not employer:
            return None

        tax_year = self._safe_int(ef.get("tax_year"))
        wages = self._to_decimal(ef.get("wages_tips_compensation"))

        # W-2 covers Jan 1 to Dec 31 of the tax year (or partial if mid-year)
        start = date(tax_year, 1, 1) if tax_year else None
        end = date(tax_year, 12, 31) if tax_year else None

        return EmploymentRecord(
            employer_name=employer,
            start_date=start,
            end_date=end,
            job_title=ef.get("job_title"),
            industry=ef.get("industry"),
            employment_type="full_time",
            is_current=False,
            annual_income=wages if wages and wages > ZERO else None,
            source_doc_ids=[doc_id],
            source_doc_types=["W2"],
        )

    def _extract_from_paystub(
        self, ef: Dict[str, Any], doc_id: int,
    ) -> Optional[EmploymentRecord]:
        """Extract employment record from paystub extracted fields."""
        employer = ef.get("employer_name")
        if not employer:
            return None

        hire_date = self._safe_date(ef.get("hire_date") or ef.get("employment_start_date"))
        pay_date = self._safe_date(ef.get("pay_date") or ef.get("pay_period_end"))

        return EmploymentRecord(
            employer_name=employer,
            start_date=hire_date,
            end_date=None,  # Paystub implies current employment
            job_title=ef.get("job_title"),
            industry=ef.get("industry"),
            employment_type=self._infer_employment_type(ef),
            is_current=True,
            annual_income=self._annualize_paystub(ef),
            source_doc_ids=[doc_id],
            source_doc_types=["PAYSTUB"],
        )

    def _extract_from_voe(
        self, ef: Dict[str, Any], doc_id: int,
    ) -> Optional[EmploymentRecord]:
        """Extract employment record from VOE (Verification of Employment)."""
        employer = ef.get("employer_name")
        if not employer:
            return None

        start = self._safe_date(
            ef.get("hire_date")
            or ef.get("employment_start_date")
            or ef.get("start_date")
        )
        end = self._safe_date(
            ef.get("termination_date")
            or ef.get("employment_end_date")
            or ef.get("end_date")
        )
        is_current = ef.get("currently_employed", False)
        if isinstance(is_current, str):
            is_current = is_current.lower() in ("true", "yes", "y", "1")

        if is_current:
            end = None

        annual = self._to_decimal(
            ef.get("annual_salary")
            or ef.get("base_annual_salary")
            or ef.get("current_base_pay")
        )

        return EmploymentRecord(
            employer_name=employer,
            start_date=start,
            end_date=end,
            job_title=ef.get("job_title") or ef.get("position"),
            industry=ef.get("industry"),
            employment_type=self._infer_employment_type(ef),
            is_current=is_current,
            annual_income=annual if annual and annual > ZERO else None,
            source_doc_ids=[doc_id],
            source_doc_types=["VOE"],
        )

    def _extract_from_tax_return(
        self, ef: Dict[str, Any], doc_id: int,
    ) -> Optional[EmploymentRecord]:
        """Extract employment hints from tax return (Schedule C self-employment)."""
        # Tax returns give us self-employment signals from Schedule C
        business_name = ef.get("business_name")
        schedule_c_income = self._to_decimal(
            ef.get("net_profit_loss") or ef.get("net_profit")
        )

        if not business_name and not schedule_c_income:
            return None

        tax_year = self._safe_int(ef.get("tax_year"))
        name = business_name or ef.get("taxpayer_name") or "Self-Employed"

        return EmploymentRecord(
            employer_name=name,
            start_date=date(tax_year, 1, 1) if tax_year else None,
            end_date=date(tax_year, 12, 31) if tax_year else None,
            job_title="Self-Employed / Business Owner",
            industry=ef.get("industry") or ef.get("business_type"),
            employment_type="self_employed",
            is_current=False,
            annual_income=schedule_c_income if schedule_c_income and schedule_c_income > ZERO else None,
            source_doc_ids=[doc_id],
            source_doc_types=["TAX_RETURN"],
        )

    # =========================================================================
    # 4. BUILD RECORDS FROM CALLER-PROVIDED DATA
    # =========================================================================

    def _build_records_from_data(
        self, data: Dict[str, Any],
    ) -> List[EmploymentRecord]:
        """
        Build EmploymentRecord list from pre-assembled employment data.

        Expected keys in ``data``:
            - w2_history: list of dicts with employer_name, tax_year,
              wages_tips_compensation, etc.
            - voe_data: list of dicts with employer_name, hire_date,
              termination_date, currently_employed, etc.
            - paystub_data: list of dicts with employer_name, hire_date,
              pay_date, gross_pay, pay_frequency, etc.
            - tax_return_data: list of dicts with business_name, tax_year,
              net_profit_loss, etc.
        """
        records: List[EmploymentRecord] = []
        seen: Dict[str, EmploymentRecord] = {}

        # W-2 history
        for w2 in data.get("w2_history", []):
            rec = self._extract_from_w2(w2, w2.get("doc_id", 0))
            if rec:
                key = rec.employer_name.strip().lower()
                if key in seen:
                    self._merge_records(seen[key], rec)
                else:
                    seen[key] = rec
                    records.append(rec)

        # VOE data (authoritative for start/end dates)
        for voe in data.get("voe_data", []):
            rec = self._extract_from_voe(voe, voe.get("doc_id", 0))
            if rec:
                key = rec.employer_name.strip().lower()
                if key in seen:
                    self._merge_records(seen[key], rec)
                else:
                    seen[key] = rec
                    records.append(rec)

        # Paystub data
        for ps in data.get("paystub_data", []):
            rec = self._extract_from_paystub(ps, ps.get("doc_id", 0))
            if rec:
                key = rec.employer_name.strip().lower()
                if key in seen:
                    self._merge_records(seen[key], rec)
                else:
                    seen[key] = rec
                    records.append(rec)

        # Tax return / self-employment
        for tr in data.get("tax_return_data", []):
            rec = self._extract_from_tax_return(tr, tr.get("doc_id", 0))
            if rec:
                key = rec.employer_name.strip().lower()
                if key in seen:
                    self._merge_records(seen[key], rec)
                else:
                    seen[key] = rec
                    records.append(rec)

        return records

    # =========================================================================
    # 5. GAP DETECTION
    # =========================================================================

    def detect_gaps(
        self,
        w2_history: List[Dict[str, Any]],
        voe_data: List[Dict[str, Any]],
    ) -> List[EmploymentGap]:
        """
        Public convenience method: detect gaps from W-2 + VOE data.

        Builds employment records internally, then delegates to
        ``detect_gaps_from_records``.
        """
        records = self._build_records_from_data({
            "w2_history": w2_history,
            "voe_data": voe_data,
        })
        records = self._sort_records(records)
        return self.detect_gaps_from_records(records)

    def detect_gaps_from_records(
        self, records: List[EmploymentRecord],
    ) -> List[EmploymentGap]:
        """
        Detect gaps > 30 days between sequential (non-overlapping)
        employment records.

        Records must be sorted by start_date ascending before calling.
        Overlapping records are not treated as gaps; they are handled
        separately by ``_detect_concurrent_employment``.
        """
        if len(records) < 2:
            return []

        gaps: List[EmploymentGap] = []
        # Filter to records with dates
        dated = [r for r in records if r.start_date is not None]
        if len(dated) < 2:
            return gaps

        # Sort again to be safe
        dated.sort(key=lambda r: r.start_date)

        for i in range(len(dated) - 1):
            current = dated[i]
            next_rec = dated[i + 1]

            # Determine end of current employment
            current_end = current.end_date or date.today()

            # Gap = next start - current end
            gap_days = (next_rec.start_date - current_end).days

            if gap_days <= 0:
                # Overlapping or contiguous; no gap
                continue

            classification = self._classify_gap(gap_days)

            # Determine transition type
            transition = self._determine_transition(current, next_rec)

            gap = EmploymentGap(
                gap_start=current_end,
                gap_end=next_rec.start_date,
                days=gap_days,
                classification=classification,
                employer_before=current.employer_name,
                employer_after=next_rec.employer_name,
                industry_before=current.industry,
                industry_after=next_rec.industry,
                transition_type=transition,
            )

            # Flag generation for the gap itself
            if classification in (GapClassification.SIGNIFICANT, GapClassification.EXTENDED):
                gap.flags.append(
                    f"EMPLOYMENT_GAP_{classification.value}: "
                    f"{gap_days} day gap between "
                    f"'{current.employer_name}' and '{next_rec.employer_name}'"
                )

            if transition == EmploymentTransition.DIFFERENT_INDUSTRY:
                gap.flags.append(
                    "INDUSTRY_CHANGE: Borrower changed industries across gap"
                )

            gaps.append(gap)

        return gaps

    # =========================================================================
    # 6. GAP EVALUATION
    # =========================================================================

    async def evaluate_gap(
        self,
        gap: EmploymentGap,
        explanation: Optional[str] = None,
        supporting_docs: Optional[List[int]] = None,
        loan_type: Optional[str] = None,
    ) -> GapEvaluation:
        """
        Evaluate a single employment gap for underwriting impact.

        Determines:
            - Whether an LOE is required
            - What supporting documentation is needed
            - How the gap affects income calculation
            - Risk level

        If an explanation is provided, uses AI to assess reasonableness.
        """
        requires_loe = gap.classification in (
            GapClassification.MODERATE,
            GapClassification.SIGNIFICANT,
            GapClassification.EXTENDED,
        )
        requires_docs = gap.classification in (
            GapClassification.SIGNIFICANT,
            GapClassification.EXTENDED,
        )

        # Determine reason if explanation is provided
        reason = gap.reason
        if explanation and not reason:
            reason = await self._classify_explanation(explanation)
            gap.reason = reason
            gap.reason_acceptability = _REASON_ACCEPTABILITY.get(
                reason, ReasonAcceptability.CONCERNING,
            )

        if reason:
            gap.reason_acceptability = _REASON_ACCEPTABILITY.get(
                reason, ReasonAcceptability.CONCERNING,
            )

        # AI evaluation of explanation adequacy
        if explanation and requires_loe:
            gap.explanation_adequate = await self._assess_explanation_adequacy(
                gap, explanation,
            )

        # Income impact
        income_impact, adjustment_factor = self._assess_income_impact(
            gap, loan_type,
        )

        # Documentation requirements for this gap
        doc_reqs = self._gap_documentation_requirements(gap)

        # Underwriting notes
        uw_notes = self._generate_underwriting_notes(gap, loan_type)

        # Risk level
        risk_level = self._assess_gap_risk(gap)

        return GapEvaluation(
            gap=gap,
            requires_loe=requires_loe,
            requires_documentation=requires_docs,
            income_impact=income_impact,
            income_adjustment_factor=adjustment_factor,
            documentation_requirements=[d.description for d in doc_reqs],
            underwriting_notes=uw_notes,
            risk_level=risk_level,
        )

    # =========================================================================
    # 7. CONTINUITY ASSESSMENT
    # =========================================================================

    def assess_continuity(
        self,
        employment_history: Optional[List[EmploymentRecord]] = None,
        gaps: Optional[List[EmploymentGap]] = None,
    ) -> ContinuityAssessment:
        """
        Assess overall employment continuity across the history.

        Evaluates:
            - Total employment vs gap time
            - Industry consistency
            - Career advancement indicators
            - Number of employers
        """
        records = employment_history or []
        gap_list = gaps or []

        if not records:
            return ContinuityAssessment(
                rating=ContinuityRating.WEAK,
                total_employment_months=0.0,
                total_gap_months=0.0,
                employment_coverage_pct=0.0,
                industry_changes=0,
                employer_count=0,
                longest_tenure_months=0.0,
                career_advancement=False,
                same_industry_throughout=True,
                notes=["No employment records available"],
                risk_factors=["NO_EMPLOYMENT_HISTORY"],
            )

        # Calculate total employment months
        total_emp_days = sum(
            (r.duration_days or 0) for r in records
        )
        total_emp_months = round(total_emp_days / 30.44, 1)

        # Total gap months
        total_gap_days = sum(g.days for g in gap_list)
        total_gap_months = round(total_gap_days / 30.44, 1)

        # Coverage percentage over lookback window
        lookback_days = FNMA_EMPLOYMENT_HISTORY_YEARS * 365
        total_span = total_emp_days + total_gap_days
        if total_span > 0:
            coverage_pct = round(
                (total_emp_days / max(total_span, lookback_days)) * 100, 1,
            )
        else:
            coverage_pct = 0.0

        # Industry analysis
        industries = [
            r.industry for r in records
            if r.industry is not None
        ]
        unique_industries = set(i.lower().strip() for i in industries if i)
        industry_changes = max(0, len(unique_industries) - 1)
        same_industry = len(unique_industries) <= 1

        # Employer count
        unique_employers = set(
            r.employer_name.strip().lower()
            for r in records if r.employer_name
        )
        employer_count = len(unique_employers)

        # Longest tenure
        tenures = [r.duration_months for r in records if r.duration_months is not None]
        longest_tenure = max(tenures) if tenures else 0.0

        # Career advancement heuristic: job titles suggest progression
        career_advancement = self._detect_career_advancement(records)

        # Generate notes and risk factors
        notes: List[str] = []
        risk_factors: List[str] = []

        if total_emp_months < FNMA_EMPLOYMENT_HISTORY_YEARS * 12:
            risk_factors.append(
                f"INSUFFICIENT_HISTORY: {total_emp_months} months "
                f"(need {FNMA_EMPLOYMENT_HISTORY_YEARS * 12})"
            )

        if len([g for g in gap_list if g.classification == GapClassification.EXTENDED]) > 0:
            risk_factors.append("EXTENDED_GAP_PRESENT")

        if industry_changes >= 2:
            risk_factors.append(
                f"MULTIPLE_INDUSTRY_CHANGES: {industry_changes} changes"
            )

        if employer_count >= 4 and total_emp_months < 36:
            risk_factors.append("FREQUENT_JOB_CHANGES")

        if career_advancement:
            notes.append("Career advancement pattern detected")
        if same_industry:
            notes.append("Consistent employment within same industry")
        if longest_tenure >= 24:
            notes.append(f"Strong tenure: {longest_tenure} months at longest position")

        # Determine rating
        rating = self._determine_continuity_rating(
            coverage_pct, industry_changes, gap_list,
            career_advancement, total_emp_months,
        )

        return ContinuityAssessment(
            rating=rating,
            total_employment_months=total_emp_months,
            total_gap_months=total_gap_months,
            employment_coverage_pct=coverage_pct,
            industry_changes=industry_changes,
            employer_count=employer_count,
            longest_tenure_months=longest_tenure,
            career_advancement=career_advancement,
            same_industry_throughout=same_industry,
            notes=notes,
            risk_factors=risk_factors,
        )

    # =========================================================================
    # 8. LOE TEMPLATE GENERATION
    # =========================================================================

    def generate_loe_template(self, gap: EmploymentGap) -> str:
        """
        Generate a Letter of Explanation template for an employment gap.

        The template is pre-filled with gap dates and employer names and
        includes prompts for the borrower to complete.
        """
        reason = gap.reason or GapReason.UNEXPLAINED
        template_key = LOE_TEMPLATE_MAP.get(reason.value, "LOE_GENERAL")

        gap_start_str = gap.gap_start.strftime("%B %d, %Y")
        gap_end_str = gap.gap_end.strftime("%B %d, %Y")
        employer_before = gap.employer_before or "[Previous Employer]"
        employer_after = gap.employer_after or "[Next Employer]"

        header = (
            "LETTER OF EXPLANATION - EMPLOYMENT GAP\n"
            "=" * 50 + "\n\n"
            f"Date: {date.today().strftime('%B %d, %Y')}\n\n"
            "To Whom It May Concern,\n\n"
            "I am writing to explain a gap in my employment history.\n\n"
            f"Gap Period: {gap_start_str} to {gap_end_str} "
            f"({gap.days} days)\n"
            f"Previous Employer: {employer_before}\n"
            f"Subsequent Employer: {employer_after}\n\n"
        )

        body_map = {
            "LOE_EDUCATION": (
                "During this period, I was enrolled in [SCHOOL/PROGRAM NAME] "
                "pursuing [DEGREE/CERTIFICATE]. I completed my studies on "
                "[COMPLETION DATE] and subsequently obtained employment at "
                f"{employer_after}.\n\n"
                "Supporting documentation: [Transcripts, enrollment verification, "
                "degree/certificate]\n"
            ),
            "LOE_MEDICAL": (
                "During this period, I was unable to work due to a medical "
                "condition. I have since fully recovered and returned to the "
                f"workforce at {employer_after}.\n\n"
                "Supporting documentation: [Doctor's letter confirming ability "
                "to return to work; note: specific diagnosis not required]\n"
            ),
            "LOE_MILITARY": (
                "During this period, I was on active military deployment / "
                "military orders to [LOCATION/UNIT]. I returned from deployment "
                f"on [DATE] and began employment at {employer_after}.\n\n"
                "Supporting documentation: [Military orders, DD-214, "
                "discharge papers]\n"
            ),
            "LOE_FAMILY_LEAVE": (
                "During this period, I took family leave for "
                "[maternity/paternity/family caregiving] purposes. I returned "
                f"to the workforce at {employer_after} upon completing my "
                "leave.\n\n"
                "Supporting documentation: [Birth certificate, FMLA "
                "documentation if applicable]\n"
            ),
            "LOE_RELOCATION": (
                "During this period, I was in the process of relocating from "
                "[PREVIOUS CITY/STATE] to [NEW CITY/STATE]. The relocation "
                "was due to [REASON: spouse's job transfer, family, etc.]. "
                f"Upon completing the move, I obtained employment at "
                f"{employer_after}.\n\n"
                "Supporting documentation: [Moving receipts, prior/new lease "
                "or mortgage statements]\n"
            ),
            "LOE_TERMINATION": (
                "My employment at {employer_before} ended on "
                f"{gap_start_str} due to [REASON: layoff, company "
                "restructuring, position elimination, etc.]. I actively "
                "searched for new employment and began working at "
                f"{employer_after} on {gap_end_str}.\n\n"
                "Supporting documentation: [Severance agreement, "
                "unemployment benefits documentation, offer letter from "
                "new employer]\n"
            ),
            "LOE_CAREER_CHANGE": (
                "During this period, I transitioned careers from "
                "[PREVIOUS INDUSTRY/ROLE] to [NEW INDUSTRY/ROLE]. "
                "[I completed training/certification in the new field.] "
                f"I began employment at {employer_after} in my new "
                "career path.\n\n"
                "Supporting documentation: [Training certificates, "
                "professional licenses, course completion records]\n"
            ),
            "LOE_GENERAL": (
                "During this period, I [EXPLAIN REASON FOR GAP]. "
                f"I subsequently obtained employment at {employer_after}.\n\n"
                "Supporting documentation: [Any relevant documentation "
                "supporting explanation]\n"
            ),
        }

        body = body_map.get(template_key, body_map["LOE_GENERAL"])

        footer = (
            "\nI certify that the above information is true and accurate "
            "to the best of my knowledge.\n\n"
            "Sincerely,\n\n"
            "____________________________\n"
            "Borrower Signature\n\n"
            "____________________________\n"
            "Printed Name\n\n"
            "____________________________\n"
            "Date\n"
        )

        return header + body + footer

    # =========================================================================
    # 9. DOCUMENTATION REQUIREMENTS
    # =========================================================================

    def get_documentation_requirements(
        self,
        gaps: List[EmploymentGap],
        evaluations: Optional[List[GapEvaluation]] = None,
    ) -> List[DocRequirement]:
        """
        Generate the complete list of documentation requirements based on
        all detected gaps.
        """
        requirements: List[DocRequirement] = []
        seen_types: set = set()

        for gap in gaps:
            gap_reqs = self._gap_documentation_requirements(gap)
            for req in gap_reqs:
                # Deduplicate by doc_type + gap_reference
                key = (req.doc_type, req.gap_reference)
                if key not in seen_types:
                    seen_types.add(key)
                    requirements.append(req)

        # If any gap is SIGNIFICANT or EXTENDED, ensure VOE is required
        has_serious_gap = any(
            g.classification in (GapClassification.SIGNIFICANT, GapClassification.EXTENDED)
            for g in gaps
        )
        if has_serious_gap and "VOE" not in seen_types:
            requirements.append(DocRequirement(
                doc_type="VOE",
                description=(
                    "Verification of Employment required for all employers "
                    "within the last 2 years due to significant employment gap(s)"
                ),
                required=True,
                gap_reference="all_gaps",
                template_available=False,
            ))

        return requirements

    # =========================================================================
    # 10. CONCURRENT EMPLOYMENT DETECTION
    # =========================================================================

    def _detect_concurrent_employment(
        self, records: List[EmploymentRecord],
    ) -> List[ConcurrentEmployment]:
        """
        Detect overlapping employment periods (multiple jobs at the same
        time).
        """
        concurrent: List[ConcurrentEmployment] = []
        dated = [r for r in records if r.start_date is not None]
        dated.sort(key=lambda r: r.start_date)

        for i in range(len(dated)):
            for j in range(i + 1, len(dated)):
                a = dated[i]
                b = dated[j]

                a_end = a.end_date or date.today()
                b_end = b.end_date or date.today()

                # Check for overlap
                overlap_start = max(a.start_date, b.start_date)
                overlap_end = min(a_end, b_end)

                if overlap_start < overlap_end:
                    overlap_days = (overlap_end - overlap_start).days
                    if overlap_days >= 14:  # Ignore trivial overlaps
                        is_pt_combo = (
                            a.employment_type == "part_time"
                            or b.employment_type == "part_time"
                        )
                        combined = None
                        if a.annual_income and b.annual_income:
                            combined = a.annual_income + b.annual_income

                        concurrent.append(ConcurrentEmployment(
                            employer_a=a.employer_name,
                            employer_b=b.employer_name,
                            overlap_start=overlap_start,
                            overlap_end=overlap_end,
                            overlap_days=overlap_days,
                            is_part_time_combo=is_pt_combo,
                            combined_income=combined,
                        ))

        return concurrent

    # =========================================================================
    # 11. SELF-EMPLOYMENT TRANSITION DETECTION
    # =========================================================================

    def _detect_self_employment_transitions(
        self, records: List[EmploymentRecord],
    ) -> List[Dict[str, Any]]:
        """
        Detect transitions between W-2 employment and self-employment.

        Key rules:
            - W-2 -> Self-employed: need 2 years SE history
            - Self-employed -> W-2: generally acceptable immediately
        """
        transitions: List[Dict[str, Any]] = []
        dated = [r for r in records if r.start_date is not None]
        dated.sort(key=lambda r: r.start_date)

        for i in range(len(dated) - 1):
            current = dated[i]
            next_rec = dated[i + 1]

            current_is_se = current.employment_type == "self_employed"
            next_is_se = next_rec.employment_type == "self_employed"

            if current_is_se == next_is_se:
                continue

            if not current_is_se and next_is_se:
                # W-2 -> Self-employed
                se_duration_months = next_rec.duration_months or 0
                meets_requirement = se_duration_months >= SE_HISTORY_YEARS * 12

                transitions.append({
                    "type": "w2_to_self_employed",
                    "from_employer": current.employer_name,
                    "to_business": next_rec.employer_name,
                    "transition_date": str(next_rec.start_date),
                    "se_duration_months": se_duration_months,
                    "meets_2_year_requirement": meets_requirement,
                    "impact": (
                        "acceptable" if meets_requirement
                        else "2_year_se_history_required"
                    ),
                    "notes": (
                        "Self-employment income requires 2-year history. "
                        f"Current SE duration: {se_duration_months} months."
                        if not meets_requirement else
                        "Self-employment history meets 2-year requirement."
                    ),
                })

            elif current_is_se and not next_is_se:
                # Self-employed -> W-2
                transitions.append({
                    "type": "self_employed_to_w2",
                    "from_business": current.employer_name,
                    "to_employer": next_rec.employer_name,
                    "transition_date": str(next_rec.start_date),
                    "impact": "generally_acceptable",
                    "notes": (
                        "Transition from self-employment to W-2 is generally "
                        "acceptable. W-2 income can be used immediately."
                    ),
                })

        return transitions

    # =========================================================================
    # 12. RETURN-TO-WORK ASSESSMENT
    # =========================================================================

    def _assess_return_to_work(
        self,
        records: List[EmploymentRecord],
        gaps: List[EmploymentGap],
    ) -> Optional[ReturnToWorkAssessment]:
        """
        Assess whether the borrower recently returned to the workforce
        after a significant gap.
        """
        current_jobs = [r for r in records if r.is_current]
        if not current_jobs:
            return None

        current = current_jobs[0]
        months_current = current.duration_months

        if months_current is None:
            return None

        # Find gap immediately preceding current employment
        prior_gap = None
        for gap in reversed(gaps):
            if (
                gap.employer_after
                and current.employer_name
                and gap.employer_after.strip().lower()
                == current.employer_name.strip().lower()
            ):
                prior_gap = gap
                break

        if prior_gap is None or prior_gap.classification == GapClassification.SHORT:
            return None  # Not a return-to-work scenario

        is_rtw = prior_gap.classification in (
            GapClassification.MODERATE,
            GapClassification.SIGNIFICANT,
            GapClassification.EXTENDED,
        )

        if not is_rtw:
            return None

        # Income stability: check if income has been consistent since return
        income_stability = "insufficient_data"
        if current.annual_income and current.annual_income > ZERO:
            if months_current >= MIN_RETURN_STABILITY_MONTHS:
                income_stability = "stable"
            else:
                income_stability = "too_early_to_assess"

        meets_minimum = months_current >= MIN_CURRENT_EMPLOYMENT_MONTHS

        # Check if current employment is in the field of study (if gap was
        # for education). This is heuristic -- exact matching would require
        # transcript analysis.
        same_field = None
        if prior_gap.reason == GapReason.EDUCATION:
            same_field = (
                prior_gap.industry_after is not None
                and current.industry is not None
                and prior_gap.industry_after.lower() == current.industry.lower()
            )

        # Guideline notes
        notes: List[str] = []
        if prior_gap.classification == GapClassification.EXTENDED:
            notes.append(
                "Extended gap before current employment. Underwriter will "
                "scrutinize income stability and employment duration."
            )
        if not meets_minimum:
            notes.append(
                f"Only {months_current} months in current position "
                f"(recommended minimum: {MIN_CURRENT_EMPLOYMENT_MONTHS} months)."
            )
        if prior_gap.reason == GapReason.EDUCATION and same_field:
            notes.append(
                "Gap was for education and current employment is in the "
                "field of study. Per Fannie Mae B3-3.1-09, this is "
                "generally acceptable."
            )
        if prior_gap.reason == GapReason.EDUCATION and same_field is False:
            notes.append(
                "Gap was for education but current employment appears to "
                "be in a different field. Additional scrutiny may apply."
            )

        return ReturnToWorkAssessment(
            is_return_to_work=True,
            months_in_current_position=months_current,
            prior_gap_months=prior_gap.months,
            income_stability=income_stability,
            meets_minimum_duration=meets_minimum,
            same_field_as_education=same_field,
            guideline_notes=notes,
        )

    # =========================================================================
    # 13. INCOME IMPACT CALCULATION
    # =========================================================================

    def _calculate_income_impact(
        self,
        gaps: List[EmploymentGap],
        evaluations: List[GapEvaluation],
        records: List[EmploymentRecord],
        loan_type: Optional[str],
    ) -> Dict[str, Any]:
        """
        Calculate how employment gaps affect the income used for
        qualifying.
        """
        recent_gaps = [g for g in gaps if g.in_last_two_years]
        total_gap_days_recent = sum(g.days for g in recent_gaps)
        total_gap_months_recent = round(total_gap_days_recent / 30.44, 1)

        # Income adjustment factor: reduce qualifying income proportionally
        # to gap time within the 2-year lookback.
        months_in_lookback = INCOME_IMPACT_LOOKBACK_YEARS * 12
        employed_months = months_in_lookback - total_gap_months_recent
        if employed_months < 0:
            employed_months = 0

        adjustment_factor = Decimal(str(
            round(employed_months / months_in_lookback, 4)
        )) if months_in_lookback > 0 else Decimal("1.0")

        # Determine if any gap is disqualifying
        disqualifying_gaps = [
            e for e in evaluations
            if e.income_impact == "disqualifying"
        ]

        # Determine overall impact
        if disqualifying_gaps:
            overall_impact = "disqualifying"
        elif total_gap_months_recent > 6:
            overall_impact = "significant_adjustment"
        elif total_gap_months_recent > 2:
            overall_impact = "moderate_adjustment"
        elif total_gap_months_recent > 0:
            overall_impact = "minor_adjustment"
        else:
            overall_impact = "none"

        # Loan type specifics
        program_notes: List[str] = []
        lt = (loan_type or "").lower()

        if lt == "fha":
            program_notes.append(
                "FHA requires 2 years of employment history. Gaps must be "
                "documented with LOE."
            )
            if total_gap_months_recent > 6:
                program_notes.append(
                    "FHA: Extended gap may require additional compensating "
                    "factors (reserves, low DTI)."
                )
        elif lt == "va":
            program_notes.append(
                "VA: Military service gaps are automatically acceptable. "
                "Other gaps follow standard guidelines."
            )
        elif lt in ("conventional", ""):
            program_notes.append(
                "Fannie Mae B3-3.1-09: Generally need 2 years in same "
                "line of work. Gaps require LOE."
            )

        return {
            "overall_impact": overall_impact,
            "gaps_in_last_2_years": len(recent_gaps),
            "total_gap_months_recent": total_gap_months_recent,
            "income_adjustment_factor": str(adjustment_factor),
            "adjusted_months_employed": employed_months,
            "disqualifying_gap_count": len(disqualifying_gaps),
            "program_notes": program_notes,
        }

    # =========================================================================
    # 14. AI-ASSISTED ANALYSIS
    # =========================================================================

    async def _classify_explanation(
        self, explanation: str,
    ) -> GapReason:
        """Use AI to classify the reason for an employment gap from LOE text."""
        if not HAS_ANTHROPIC or not self._anthropic_key:
            return self._rule_based_classification(explanation)

        client = Anthropic(api_key=self._anthropic_key)
        prompt = (
            "Classify the following employment gap explanation into exactly "
            "one of these categories. Respond with ONLY the category name:\n\n"
            "Categories:\n"
            "- education (enrolled in school, training, certification)\n"
            "- medical (illness, injury, recovery, disability)\n"
            "- military_deployment (active duty, deployment, military orders)\n"
            "- maternity_paternity (parental leave, birth of child)\n"
            "- relocation (moved to new area, spouse transfer)\n"
            "- termination (laid off, fired, company closed)\n"
            "- industry_change (career change, new field)\n"
            "- seasonal_employment (seasonal work pattern)\n"
            "- caregiving (caring for family member)\n"
            "- unexplained (cannot determine from text)\n\n"
            f"Explanation:\n{explanation}\n\n"
            "Category:"
        )

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            max_tokens=50,
            operation_name="classify_employment_gap",
        )

        if response is None:
            return self._rule_based_classification(explanation)

        try:
            text_content = response.content[0].text.strip().lower()
            # Try to match to enum
            for reason in GapReason:
                if reason.value in text_content:
                    return reason
            return GapReason.UNEXPLAINED
        except (IndexError, AttributeError):
            return self._rule_based_classification(explanation)

    async def _assess_explanation_adequacy(
        self,
        gap: EmploymentGap,
        explanation: str,
    ) -> bool:
        """Use AI to assess whether an LOE explanation is adequate."""
        if not HAS_ANTHROPIC or not self._anthropic_key:
            return self._rule_based_adequacy(gap, explanation)

        client = Anthropic(api_key=self._anthropic_key)
        prompt = (
            "You are a mortgage underwriter reviewing a Letter of Explanation "
            "for an employment gap. Assess whether the explanation is adequate.\n\n"
            f"Gap Duration: {gap.days} days ({gap.months} months)\n"
            f"Gap Period: {gap.gap_start} to {gap.gap_end}\n"
            f"Previous Employer: {gap.employer_before}\n"
            f"Next Employer: {gap.employer_after}\n"
            f"Gap Classification: {gap.classification.value}\n\n"
            f"Explanation:\n{explanation}\n\n"
            "Is this explanation adequate for underwriting purposes? "
            "Consider:\n"
            "1. Does it explain the full gap period?\n"
            "2. Is the reason reasonable and verifiable?\n"
            "3. Does it address how the borrower supported themselves?\n"
            "4. Is it consistent with the timeline?\n\n"
            "Respond with ONLY 'YES' or 'NO' followed by a brief reason."
        )

        response = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            max_tokens=100,
            operation_name="assess_loe_adequacy",
        )

        if response is None:
            return self._rule_based_adequacy(gap, explanation)

        try:
            text_content = response.content[0].text.strip().upper()
            return text_content.startswith("YES")
        except (IndexError, AttributeError):
            return self._rule_based_adequacy(gap, explanation)

    # =========================================================================
    # 15. RULE-BASED FALLBACKS (when AI is unavailable)
    # =========================================================================

    def _rule_based_classification(self, explanation: str) -> GapReason:
        """Classify gap reason using keyword matching."""
        text_lower = explanation.lower()

        keyword_map = {
            GapReason.EDUCATION: [
                "school", "university", "college", "degree", "enrolled",
                "student", "training", "certification", "coursework",
                "classes", "graduated", "studied",
            ],
            GapReason.MEDICAL: [
                "medical", "illness", "sick", "hospital", "surgery",
                "recovery", "health", "disability", "treatment",
                "diagnosed", "injury",
            ],
            GapReason.MILITARY_DEPLOYMENT: [
                "military", "deployed", "deployment", "active duty",
                "army", "navy", "marines", "air force", "coast guard",
                "national guard", "reserve",
            ],
            GapReason.MATERNITY_PATERNITY: [
                "maternity", "paternity", "baby", "newborn", "birth",
                "pregnant", "pregnancy", "child", "parental leave",
                "fmla",
            ],
            GapReason.RELOCATION: [
                "relocated", "relocation", "moved", "moving",
                "transferred", "new city", "new state",
            ],
            GapReason.TERMINATION: [
                "laid off", "layoff", "terminated", "downsized",
                "restructuring", "position eliminated", "fired",
                "company closed", "reduction in force", "rif",
            ],
            GapReason.INDUSTRY_CHANGE: [
                "career change", "new career", "new field",
                "changed industries", "transition", "new profession",
            ],
            GapReason.SEASONAL_EMPLOYMENT: [
                "seasonal", "off-season", "construction season",
                "winter layoff",
            ],
            GapReason.CAREGIVING: [
                "caregiving", "caregiver", "caring for",
                "family member", "elderly parent", "hospice",
            ],
        }

        best_match = GapReason.UNEXPLAINED
        best_count = 0

        for reason, keywords in keyword_map.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_match = reason

        return best_match

    def _rule_based_adequacy(
        self, gap: EmploymentGap, explanation: str,
    ) -> bool:
        """Assess LOE adequacy using heuristic rules."""
        if not explanation or len(explanation.strip()) < 20:
            return False

        # Must mention dates or timeframe
        has_date_reference = any(
            term in explanation.lower()
            for term in [
                "month", "year", "week", "day", "january", "february",
                "march", "april", "may", "june", "july", "august",
                "september", "october", "november", "december",
                "2020", "2021", "2022", "2023", "2024", "2025", "2026",
            ]
        )

        # Must provide a reason
        has_reason = gap.reason is not None and gap.reason != GapReason.UNEXPLAINED

        # Length check: more serious gaps need more explanation
        min_length = {
            GapClassification.MODERATE: 50,
            GapClassification.SIGNIFICANT: 100,
            GapClassification.EXTENDED: 150,
        }
        meets_length = len(explanation.strip()) >= min_length.get(
            gap.classification, 50,
        )

        return has_date_reference and has_reason and meets_length

    # =========================================================================
    # 16. PERSISTENCE
    # =========================================================================

    async def _persist_verification_tasks(
        self,
        org_id: int,
        loan_id: int,
        borrower_id: int,
        gaps: List[EmploymentGap],
        evaluations: List[GapEvaluation],
        flags: List[str],
    ) -> None:
        """
        Create income_verification_tasks for LO review of employment gaps.
        """
        try:
            for evaluation in evaluations:
                gap = evaluation.gap
                if gap.classification == GapClassification.SHORT:
                    continue

                # Determine priority
                priority = "medium"
                if gap.classification == GapClassification.EXTENDED:
                    priority = "critical"
                elif gap.classification == GapClassification.SIGNIFICANT:
                    priority = "high"

                title = (
                    f"Review {gap.classification.value.lower()} employment gap: "
                    f"{gap.days} days ({gap.gap_start} to {gap.gap_end})"
                )

                description_parts = [
                    f"Gap between '{gap.employer_before}' and '{gap.employer_after}'.",
                    f"Classification: {gap.classification.value}",
                    f"Risk Level: {evaluation.risk_level}",
                    f"Income Impact: {evaluation.income_impact}",
                ]
                if evaluation.requires_loe:
                    description_parts.append("ACTION: Letter of Explanation required.")
                if evaluation.documentation_requirements:
                    description_parts.append(
                        "Required docs: " + "; ".join(evaluation.documentation_requirements)
                    )

                description = "\n".join(description_parts)

                self.db.execute(
                    text("""
                        INSERT INTO income_verification_tasks (
                            organization_id, loan_id, calculation_id,
                            task_type, title, description,
                            priority, status, ai_recommendation,
                            created_at, updated_at
                        ) VALUES (
                            :org_id, :loan_id, NULL,
                            :task_type, :title, :description,
                            :priority, 'open', :ai_rec,
                            NOW(), NOW()
                        )
                    """),
                    {
                        "org_id": org_id,
                        "loan_id": loan_id,
                        "task_type": "review_gap_in_employment",
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "ai_rec": (
                            evaluation.underwriting_notes[0]
                            if evaluation.underwriting_notes
                            else "Review employment gap documentation."
                        ),
                    },
                )

            self.db.flush()
        except Exception as e:
            logger.exception(
                "Failed to persist employment gap tasks for loan=%s: %s",
                loan_id, e,
            )

    # =========================================================================
    # 17. INTERNAL HELPERS
    # =========================================================================

    def _sort_records(
        self, records: List[EmploymentRecord],
    ) -> List[EmploymentRecord]:
        """Sort employment records by start date, undated last."""
        return sorted(
            records,
            key=lambda r: r.start_date or date.max,
        )

    def _classify_gap(self, days: int) -> GapClassification:
        """Classify a gap by its duration in days."""
        if days <= SHORT_GAP_MAX_DAYS:
            return GapClassification.SHORT
        elif days <= MODERATE_GAP_MAX_DAYS:
            return GapClassification.MODERATE
        elif days <= SIGNIFICANT_GAP_MAX_DAYS:
            return GapClassification.SIGNIFICANT
        else:
            return GapClassification.EXTENDED

    def _determine_transition(
        self,
        before: EmploymentRecord,
        after: EmploymentRecord,
    ) -> EmploymentTransition:
        """Determine the type of employment transition across a gap."""
        before_name = (before.employer_name or "").strip().lower()
        after_name = (after.employer_name or "").strip().lower()

        if before_name and after_name and before_name == after_name:
            return EmploymentTransition.SAME_EMPLOYER

        before_se = before.employment_type == "self_employed"
        after_se = after.employment_type == "self_employed"

        if not before_se and after_se:
            return EmploymentTransition.W2_TO_SELF_EMPLOYED
        if before_se and not after_se:
            return EmploymentTransition.SELF_EMPLOYED_TO_W2

        before_pt = before.employment_type == "part_time"
        after_pt = after.employment_type == "part_time"

        if before_pt and not after_pt:
            return EmploymentTransition.PART_TIME_TO_FULL_TIME
        if not before_pt and after_pt:
            return EmploymentTransition.FULL_TIME_TO_PART_TIME

        before_ind = (before.industry or "").strip().lower()
        after_ind = (after.industry or "").strip().lower()

        if before_ind and after_ind:
            if before_ind == after_ind:
                return EmploymentTransition.SAME_INDUSTRY
            else:
                return EmploymentTransition.DIFFERENT_INDUSTRY

        return EmploymentTransition.UNKNOWN

    def _merge_records(
        self,
        existing: EmploymentRecord,
        new: EmploymentRecord,
    ) -> None:
        """Merge a new record into an existing one, filling missing fields."""
        # VOE dates are most authoritative, then paystub, then W-2
        if new.start_date and (
            existing.start_date is None
            or "VOE" in new.source_doc_types
        ):
            existing.start_date = new.start_date

        if new.end_date is not None and existing.end_date is None:
            existing.end_date = new.end_date

        if new.is_current:
            existing.is_current = True
            existing.end_date = None

        if new.job_title and not existing.job_title:
            existing.job_title = new.job_title

        if new.industry and not existing.industry:
            existing.industry = new.industry

        if new.annual_income and (
            existing.annual_income is None
            or new.annual_income > existing.annual_income
        ):
            existing.annual_income = new.annual_income

        existing.source_doc_ids.extend(new.source_doc_ids)
        existing.source_doc_types.extend(new.source_doc_types)

    def _assess_income_impact(
        self,
        gap: EmploymentGap,
        loan_type: Optional[str],
    ) -> Tuple[str, Optional[Decimal]]:
        """
        Determine income impact and adjustment factor for a single gap.

        Returns:
            Tuple of (impact_type, adjustment_factor).
        """
        if gap.classification == GapClassification.SHORT:
            return "none", None

        if not gap.in_last_two_years:
            return "none", None

        if gap.classification == GapClassification.EXTENDED:
            # Extended gaps with concerning reasons may disqualify income type
            if gap.reason_acceptability == ReasonAcceptability.CONCERNING:
                return "disqualifying", Decimal("0.00")

            # Extended gap with acceptable reason still needs adjustment
            factor = Decimal(str(
                max(0.0, 1.0 - (gap.days / (INCOME_IMPACT_LOOKBACK_YEARS * 365)))
            )).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            return "adjustment_needed", factor

        if gap.classification == GapClassification.SIGNIFICANT:
            factor = Decimal(str(
                max(0.0, 1.0 - (gap.days / (INCOME_IMPACT_LOOKBACK_YEARS * 365)))
            )).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            return "adjustment_needed", factor

        if gap.classification == GapClassification.MODERATE:
            # Moderate gaps with acceptable reasons: minimal impact
            if gap.reason_acceptability in (
                ReasonAcceptability.ACCEPTABLE,
                ReasonAcceptability.CONDITIONAL,
            ):
                return "minor_adjustment", Decimal("0.95")
            return "adjustment_needed", Decimal("0.90")

        return "none", None

    def _assess_gap_risk(self, gap: EmploymentGap) -> str:
        """Determine risk level for a single gap."""
        if gap.classification == GapClassification.SHORT:
            return "low"

        if gap.classification == GapClassification.EXTENDED:
            if gap.reason_acceptability == ReasonAcceptability.CONCERNING:
                return "critical"
            return "high"

        if gap.classification == GapClassification.SIGNIFICANT:
            if gap.reason_acceptability == ReasonAcceptability.CONCERNING:
                return "high"
            return "medium"

        if gap.classification == GapClassification.MODERATE:
            if gap.reason_acceptability == ReasonAcceptability.CONCERNING:
                return "medium"
            return "low"

        return "low"

    def _gap_documentation_requirements(
        self, gap: EmploymentGap,
    ) -> List[DocRequirement]:
        """Generate documentation requirements for a single gap."""
        reqs: List[DocRequirement] = []
        gap_ref = f"{gap.gap_start}_to_{gap.gap_end}"

        if gap.classification == GapClassification.SHORT:
            return reqs

        # All non-short gaps require LOE
        reqs.append(DocRequirement(
            doc_type="LOE",
            description=(
                f"Letter of Explanation for {gap.days}-day employment gap "
                f"({gap.gap_start} to {gap.gap_end})"
            ),
            required=True,
            gap_reference=gap_ref,
            template_available=True,
        ))

        # VOE for employer before and after the gap
        if gap.employer_before:
            reqs.append(DocRequirement(
                doc_type="VOE",
                description=(
                    f"Verification of Employment for '{gap.employer_before}' "
                    f"(employer before gap)"
                ),
                required=gap.classification != GapClassification.MODERATE,
                gap_reference=gap_ref,
            ))

        if gap.employer_after:
            reqs.append(DocRequirement(
                doc_type="VOE",
                description=(
                    f"Verification of Employment for '{gap.employer_after}' "
                    f"(employer after gap)"
                ),
                required=gap.classification != GapClassification.MODERATE,
                gap_reference=gap_ref,
            ))

        # Reason-specific documentation
        reason = gap.reason or GapReason.UNEXPLAINED
        reason_docs = {
            GapReason.EDUCATION: [
                DocRequirement(
                    doc_type="school_transcript",
                    description="Official transcript or enrollment verification",
                    required=True, gap_reference=gap_ref,
                ),
                DocRequirement(
                    doc_type="degree_certificate",
                    description="Degree or certificate (if completed)",
                    required=False, gap_reference=gap_ref,
                ),
            ],
            GapReason.MEDICAL: [
                DocRequirement(
                    doc_type="medical_clearance",
                    description=(
                        "Doctor's letter confirming ability to return to work "
                        "(specific diagnosis not required)"
                    ),
                    required=True, gap_reference=gap_ref,
                ),
            ],
            GapReason.MILITARY_DEPLOYMENT: [
                DocRequirement(
                    doc_type="military_orders",
                    description="Military orders or DD-214",
                    required=True, gap_reference=gap_ref,
                ),
            ],
            GapReason.MATERNITY_PATERNITY: [
                DocRequirement(
                    doc_type="birth_certificate",
                    description="Birth certificate or adoption documentation",
                    required=False, gap_reference=gap_ref,
                ),
            ],
            GapReason.TERMINATION: [
                DocRequirement(
                    doc_type="severance_agreement",
                    description="Severance agreement or termination letter",
                    required=False, gap_reference=gap_ref,
                ),
                DocRequirement(
                    doc_type="unemployment_benefits",
                    description="Unemployment benefits documentation",
                    required=False, gap_reference=gap_ref,
                ),
            ],
        }

        extra = reason_docs.get(reason, [])
        reqs.extend(extra)

        return reqs

    def _generate_underwriting_notes(
        self,
        gap: EmploymentGap,
        loan_type: Optional[str],
    ) -> List[str]:
        """Generate underwriting guidance notes for a gap."""
        notes: List[str] = []
        lt = (loan_type or "").lower()

        if gap.classification == GapClassification.SHORT:
            notes.append(
                f"Short gap ({gap.days} days) between employers. "
                "Generally acceptable without LOE."
            )
            return notes

        notes.append(
            f"{gap.classification.value} gap: {gap.days} days "
            f"({gap.gap_start} to {gap.gap_end})"
        )

        if gap.reason:
            acceptability = _REASON_ACCEPTABILITY.get(
                gap.reason, ReasonAcceptability.CONCERNING,
            )
            notes.append(
                f"Reason: {gap.reason.value} "
                f"(acceptability: {acceptability.value})"
            )

        if gap.transition_type == EmploymentTransition.DIFFERENT_INDUSTRY:
            notes.append(
                "Industry change detected across gap. Per Fannie Mae "
                "B3-3.1-09, 2 years in same line of work is preferred."
            )

        if lt == "fha":
            notes.append(
                "FHA 4000.1 II.A.4.c: Borrower must have 2-year "
                "employment history. Document any gaps with LOE."
            )
        elif lt == "va":
            if gap.reason == GapReason.MILITARY_DEPLOYMENT:
                notes.append(
                    "VA: Military deployment gap is automatically acceptable."
                )
            else:
                notes.append(
                    "VA: Standard gap documentation requirements apply."
                )

        if gap.in_last_two_years:
            notes.append(
                "Gap falls within 2-year lookback period. "
                "Income averaging may need adjustment."
            )

        if gap.explanation_adequate is False:
            notes.append(
                "WARNING: LOE explanation assessed as inadequate. "
                "Request revised letter from borrower."
            )

        return notes

    def _generate_flags(
        self,
        gaps: List[EmploymentGap],
        evaluations: List[GapEvaluation],
        continuity: ContinuityAssessment,
        return_to_work: Optional[ReturnToWorkAssessment],
        se_transitions: List[Dict[str, Any]],
        concurrent: List[ConcurrentEmployment],
        loan_type: Optional[str],
    ) -> List[str]:
        """Generate analysis-level flags."""
        flags: List[str] = []

        # Gap-level flags
        for gap in gaps:
            flags.extend(gap.flags)

        # Evaluation-level flags
        for ev in evaluations:
            if ev.risk_level == "critical":
                flags.append(
                    f"CRITICAL_GAP: {ev.gap.days}-day gap "
                    f"({ev.gap.gap_start} to {ev.gap.gap_end})"
                )
            if ev.income_impact == "disqualifying":
                flags.append(
                    f"DISQUALIFYING_GAP: {ev.gap.days}-day gap may "
                    f"disqualify this income type"
                )

        # Continuity flags
        flags.extend(continuity.risk_factors)

        # Return-to-work flags
        if return_to_work and not return_to_work.meets_minimum_duration:
            flags.append(
                f"SHORT_TENURE: Only {return_to_work.months_in_current_position} "
                f"months in current position after gap"
            )

        # Self-employment transition flags
        for tr in se_transitions:
            if tr.get("impact") == "2_year_se_history_required":
                flags.append(
                    f"SE_HISTORY_SHORT: Self-employment duration "
                    f"({tr.get('se_duration_months', 0)} months) does not "
                    f"meet 2-year requirement"
                )

        # Concurrent employment flags
        for ce in concurrent:
            if not ce.is_part_time_combo:
                flags.append(
                    f"CONCURRENT_FULL_TIME: Overlapping full-time employment "
                    f"at '{ce.employer_a}' and '{ce.employer_b}' "
                    f"({ce.overlap_days} days) — verify accuracy"
                )

        # Missing LOE flags
        for ev in evaluations:
            if ev.requires_loe and ev.gap.explanation_text is None:
                flags.append(
                    f"LOE_MISSING: Letter of Explanation needed for "
                    f"{ev.gap.days}-day gap "
                    f"({ev.gap.gap_start} to {ev.gap.gap_end})"
                )

        return flags

    def _generate_recommendations(
        self,
        gaps: List[EmploymentGap],
        evaluations: List[GapEvaluation],
        continuity: ContinuityAssessment,
        return_to_work: Optional[ReturnToWorkAssessment],
        se_transitions: List[Dict[str, Any]],
        loan_type: Optional[str],
    ) -> List[str]:
        """Generate actionable recommendations for the LO."""
        recs: List[str] = []

        # LOE recommendations
        loe_needed = [
            ev for ev in evaluations
            if ev.requires_loe and ev.gap.explanation_text is None
        ]
        if loe_needed:
            recs.append(
                f"Obtain Letter(s) of Explanation for {len(loe_needed)} "
                f"employment gap(s). Use the LOE template generator for "
                f"pre-filled templates."
            )

        # Documentation recommendations
        docs_needed = [
            ev for ev in evaluations
            if ev.requires_documentation
        ]
        if docs_needed:
            recs.append(
                f"Collect supporting documentation for {len(docs_needed)} "
                f"gap(s) requiring verification."
            )

        # Inadequate explanation
        inadequate = [
            ev for ev in evaluations
            if ev.gap.explanation_adequate is False
        ]
        if inadequate:
            recs.append(
                f"Request revised LOE for {len(inadequate)} gap(s) where "
                f"the current explanation was assessed as inadequate."
            )

        # Return-to-work
        if return_to_work and not return_to_work.meets_minimum_duration:
            recs.append(
                f"Borrower has only {return_to_work.months_in_current_position} "
                f"months in current position. Consider waiting until "
                f"{MIN_CURRENT_EMPLOYMENT_MONTHS} months for stronger file, "
                f"or document compensating factors."
            )

        # Self-employment
        for tr in se_transitions:
            if tr.get("impact") == "2_year_se_history_required":
                recs.append(
                    f"Self-employment history of {tr.get('se_duration_months', 0)} "
                    f"months does not meet the 2-year requirement. Collect "
                    f"2 years of business tax returns to support SE income."
                )

        # Continuity
        if continuity.rating == ContinuityRating.WEAK:
            recs.append(
                "Employment continuity is weak. Consider documenting "
                "compensating factors: reserves, low DTI, or co-borrower "
                "income stability."
            )
        elif continuity.rating == ContinuityRating.MARGINAL:
            recs.append(
                "Employment continuity is marginal. Ensure all gaps are "
                "fully documented with LOEs and supporting materials."
            )

        # VOE recommendation
        serious_gaps = [
            g for g in gaps
            if g.classification in (
                GapClassification.SIGNIFICANT, GapClassification.EXTENDED,
            )
        ]
        if serious_gaps:
            recs.append(
                "Order Verification of Employment (VOE) for all employers "
                "within the last 2 years to confirm employment dates."
            )

        # Second job income
        if any(
            ev.gap.transition_type == EmploymentTransition.PART_TIME_TO_FULL_TIME
            for ev in evaluations
        ):
            recs.append(
                "Part-time to full-time transition detected. If using "
                "prior part-time income, ensure 2-year history is documented."
            )

        return recs

    def _calculate_confidence(
        self,
        records: List[EmploymentRecord],
        gaps: List[EmploymentGap],
        evaluations: List[GapEvaluation],
        continuity: ContinuityAssessment,
    ) -> int:
        """
        Calculate overall confidence score (0-100) for the analysis.

        Starts at 100 and deducts for data quality issues.
        """
        score = 100

        # Deduct for records without dates
        dateless = [r for r in records if r.start_date is None]
        score -= len(dateless) * 10

        # Deduct for single-source records (only W-2, no VOE confirmation)
        single_source = [
            r for r in records if len(set(r.source_doc_types)) == 1
        ]
        score -= len(single_source) * 3

        # Deduct for unexplained gaps
        unexplained = [
            g for g in gaps
            if g.classification != GapClassification.SHORT
            and g.reason is None
        ]
        score -= len(unexplained) * 8

        # Deduct for critical evaluations
        critical = [
            e for e in evaluations if e.risk_level == "critical"
        ]
        score -= len(critical) * 15

        # Deduct for weak continuity
        if continuity.rating == ContinuityRating.WEAK:
            score -= 15
        elif continuity.rating == ContinuityRating.MARGINAL:
            score -= 8

        # Bonus for VOE-confirmed records
        voe_confirmed = [
            r for r in records if "VOE" in r.source_doc_types
        ]
        score += min(10, len(voe_confirmed) * 5)

        return max(0, min(100, score))

    def _detect_career_advancement(
        self, records: List[EmploymentRecord],
    ) -> bool:
        """
        Heuristic detection of career advancement pattern based on
        job title progression and income growth.
        """
        dated = [r for r in records if r.start_date is not None]
        dated.sort(key=lambda r: r.start_date)

        if len(dated) < 2:
            return False

        # Check income progression
        incomes = [
            r.annual_income for r in dated
            if r.annual_income is not None and r.annual_income > ZERO
        ]
        if len(incomes) >= 2:
            # If at least 2/3 of transitions show income growth, consider it
            # advancement
            growth_count = sum(
                1 for i in range(len(incomes) - 1)
                if incomes[i + 1] > incomes[i]
            )
            if growth_count >= (len(incomes) - 1) * 0.6:
                return True

        # Check title progression keywords
        advancement_keywords = [
            "senior", "lead", "principal", "manager", "director",
            "vp", "vice president", "head", "chief", "executive",
        ]
        titles = [
            (r.job_title or "").lower() for r in dated
            if r.job_title
        ]
        if len(titles) >= 2:
            later_titles = titles[len(titles) // 2:]
            early_titles = titles[:len(titles) // 2]
            later_has_senior = any(
                kw in t for t in later_titles for kw in advancement_keywords
            )
            early_has_senior = any(
                kw in t for t in early_titles for kw in advancement_keywords
            )
            if later_has_senior and not early_has_senior:
                return True

        return False

    def _determine_continuity_rating(
        self,
        coverage_pct: float,
        industry_changes: int,
        gaps: List[EmploymentGap],
        career_advancement: bool,
        total_emp_months: float,
    ) -> ContinuityRating:
        """Determine overall continuity rating."""
        extended_gaps = [
            g for g in gaps if g.classification == GapClassification.EXTENDED
        ]
        significant_gaps = [
            g for g in gaps if g.classification == GapClassification.SIGNIFICANT
        ]

        if extended_gaps:
            return ContinuityRating.WEAK

        if significant_gaps or industry_changes >= 2:
            if career_advancement and coverage_pct >= 80:
                return ContinuityRating.ADEQUATE
            return ContinuityRating.MARGINAL

        if coverage_pct >= 90 and industry_changes <= 1:
            if career_advancement or total_emp_months >= 36:
                return ContinuityRating.STRONG
            return ContinuityRating.ADEQUATE

        if coverage_pct >= 75:
            return ContinuityRating.ADEQUATE

        return ContinuityRating.MARGINAL

    def _infer_employment_type(self, ef: Dict[str, Any]) -> str:
        """Infer employment type from extracted fields."""
        emp_type = (ef.get("employment_type") or "").lower()
        if emp_type in ("part_time", "part-time"):
            return "part_time"
        if emp_type in ("self_employed", "self-employed", "1099"):
            return "self_employed"

        hours = self._safe_int(ef.get("hours_per_week"))
        if hours is not None and hours < 30:
            return "part_time"

        return "full_time"

    def _annualize_paystub(self, ef: Dict[str, Any]) -> Optional[Decimal]:
        """Annualize gross pay from paystub fields."""
        gross = self._to_decimal(ef.get("gross_pay"))
        if not gross or gross <= ZERO:
            return None

        freq = (ef.get("pay_frequency") or "MONTHLY").upper()
        multipliers = {
            "WEEKLY": 52,
            "BIWEEKLY": 26,
            "SEMIMONTHLY": 24,
            "MONTHLY": 12,
        }
        multiplier = multipliers.get(freq, 12)
        return (gross * Decimal(multiplier)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def _empty_analysis(
        self,
        org_id: int,
        borrower_id: int,
        error: Optional[str] = None,
    ) -> EmploymentAnalysis:
        """Return an empty analysis result."""
        flags = ["NO_EMPLOYMENT_RECORDS"]
        if error:
            flags.append(f"ANALYSIS_ERROR: {error}")

        return EmploymentAnalysis(
            org_id=org_id,
            borrower_id=borrower_id,
            employment_records=[],
            gaps=[],
            gap_evaluations=[],
            continuity=ContinuityAssessment(
                rating=ContinuityRating.WEAK,
                total_employment_months=0.0,
                total_gap_months=0.0,
                employment_coverage_pct=0.0,
                industry_changes=0,
                employer_count=0,
                longest_tenure_months=0.0,
                career_advancement=False,
                same_industry_throughout=True,
                notes=["No employment records to analyze"],
                risk_factors=["NO_EMPLOYMENT_HISTORY"],
            ),
            return_to_work=None,
            concurrent_employment=[],
            self_employment_transitions=[],
            documentation_requirements=[],
            income_impact_summary={
                "overall_impact": "unknown",
                "gaps_in_last_2_years": 0,
            },
            flags=flags,
            recommendations=[
                "Upload employment documents (W-2s, paystubs, VOE) to "
                "begin employment gap analysis."
            ],
            confidence=0,
        )

    # =========================================================================
    # 18. TYPE CONVERSION UTILITIES
    # =========================================================================

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        """Safely convert a value to Decimal."""
        if value is None:
            return ZERO
        try:
            if isinstance(value, Decimal):
                return value
            cleaned = str(value).replace(",", "").replace("$", "").strip()
            if not cleaned or cleaned == "":
                return ZERO
            return Decimal(cleaned).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except Exception:
            return ZERO

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Safely convert to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_date(value: Any) -> Optional[date]:
        """Safely parse a date from various formats."""
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
                except (ValueError, TypeError):
                    continue
        return None


# =============================================================================
# FACTORY
# =============================================================================

def get_employment_gap_service(db: Session) -> EmploymentGapService:
    """Factory function compatible with FastAPI dependency injection."""
    return EmploymentGapService(db)
