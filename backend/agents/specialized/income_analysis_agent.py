"""
Income Analysis Agent

AI agent specialized in mortgage income calculation and qualification analysis.
Capabilities:
- Calculate W2/salaried qualifying income from paystubs and W2s
- Calculate self-employment income from tax returns with depreciation add-backs
- Calculate commission/bonus income with 2-year trending
- Calculate rental income per Schedule E with vacancy factor
- Calculate retirement/pension/Social Security income
- Aggregate total qualifying income across all sources
- Calculate front-end and back-end DTI ratios
- Analyze income trends (increasing/stable/declining)
- Detect employment gaps in income history
- Gross up non-taxable income per agency guidelines
- Compare calculated income to application stated income
- Generate findings/tasks for underwriter review
- Check income documentation completeness
- Recommend best income calculation approach
- Create formatted income summary reports

This agent integrates with the IncomeCalculatorService for core math and
follows Fannie Mae Selling Guide (B3-3) income calculation rules.

15 Tools:
1.  calculate_w2_income - W2 employee qualifying income
2.  calculate_self_employment_income - Self-employment from tax returns
3.  calculate_commission_income - Commission/bonus with trending
4.  calculate_rental_income - Rental income per Schedule E
5.  calculate_retirement_income - Pension/SS/retirement income
6.  aggregate_total_qualifying_income - Sum all sources for a borrower
7.  calculate_dti_ratios - Front-end and back-end DTI
8.  analyze_income_trend - Increasing/decreasing/stable determination
9.  detect_income_gaps - Employment gap detection
10. gross_up_nontaxable_income - Non-taxable income gross-up
11. compare_income_to_stated - Calculated vs application stated
12. generate_income_findings - Findings/tasks for underwriter review
13. get_income_documentation_status - Income doc completeness check
14. recommend_income_approach - Best calculation approach recommendation
15. create_income_summary_report - Formatted income summary for the file
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry,
)

# ---------------------------------------------------------------------------
# Constants (aligned with income_calculator_service.py)
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

PAY_FREQUENCY_MULTIPLIERS = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

RENTAL_VACANCY_FACTOR = Decimal("0.25")

INCOME_DOC_TYPES = ("PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS")

PAYSTUB_STALENESS_DAYS = 30
DECLINING_INCOME_WARN_PCT = Decimal("10")
DECLINING_INCOME_CRITICAL_PCT = Decimal("20")
HIGH_COMMISSION_RATIO_PCT = Decimal("25")
DECLINING_COMMISSION_THRESHOLD_PCT = Decimal("25")

# Fannie Mae non-taxable income gross-up factor (B3-3.1-09)
NONTAXABLE_GROSSUP_FACTOR = Decimal("1.25")

# DTI thresholds per Fannie Mae
DTI_FRONT_END_LIMIT = Decimal("28")
DTI_BACK_END_CONVENTIONAL = Decimal("45")
DTI_BACK_END_FHA = Decimal("43")
DTI_BACK_END_VA = Decimal("41")
DTI_BACK_END_DU_MAXIMUM = Decimal("50")


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class LoanBorrowerInput(BaseModel):
    """Standard input for loan + borrower tools."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")


class LoanOnlyInput(BaseModel):
    """Input for tools that only need loan_id."""
    loan_id: int = Field(..., description="Loan ID")


class LoanBorrowerOptionalInput(BaseModel):
    """Input with optional borrower (defaults to primary)."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: Optional[int] = Field(None, description="Borrower ID (defaults to primary borrower)")


class GrossUpInput(BaseModel):
    """Input for non-taxable income gross-up."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")
    income_type: str = Field(
        ...,
        description="Type of non-taxable income: social_security, disability, "
                    "child_support, military_allowance, tax_exempt_interest",
    )
    monthly_amount: float = Field(..., description="Monthly non-taxable income amount")
    tax_rate: Optional[float] = Field(
        None,
        description="Borrower's tax rate as decimal (e.g., 0.25 for 25%). "
                    "If not provided, default 25% gross-up factor is used.",
    )


class CompareIncomeInput(BaseModel):
    """Input for comparing calculated vs stated income."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")
    stated_monthly_income: Optional[float] = Field(
        None,
        description="Stated monthly income from application. If not provided, "
                    "pulls from loan record.",
    )


class DTIInput(BaseModel):
    """Input for DTI calculation."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")
    proposed_housing_payment: Optional[float] = Field(
        None, description="Proposed PITIA payment. If not provided, pulls from loan record.",
    )
    total_monthly_obligations: Optional[float] = Field(
        None, description="Total monthly debt obligations. If not provided, pulls from loan record.",
    )


class IncomeTrendInput(BaseModel):
    """Input for income trend analysis."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")
    source_type: Optional[str] = Field(
        None,
        description="Specific source type to analyze: w2, self_employment, "
                    "commission, rental. If omitted, analyzes all sources.",
    )


class IncomeApproachInput(BaseModel):
    """Input for recommending income calculation approach."""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID")
    loan_program: Optional[str] = Field(
        None,
        description="Loan program: conventional, fha, va, usda, jumbo, non_qm",
    )


# ============================================================================
# INCOME ANALYSIS AGENT
# ============================================================================

@AgentRegistry.register
class IncomeAnalysisAgent(SpecializedAgent):
    """
    Income Analysis AI Agent for mortgage underwriting.

    I am the specialized income analysis engine. I calculate qualifying income
    from all sources per Fannie Mae Selling Guide (B3-3) rules and generate
    underwriter-ready findings. I can:

    1. CALCULATE W2 INCOME: Annualize from paystubs, cross-check against W2s,
       handle overtime/bonus/commission breakdowns, detect staleness.

    2. CALCULATE SELF-EMPLOYMENT INCOME: 2-year average from Schedule C / K-1,
       apply depreciation/amortization/depletion add-backs per B3-3.4.

    3. CALCULATE COMMISSION INCOME: 2-year history required, declining trend
       analysis, high commission ratio detection per B3-3.1-09.

    4. CALCULATE RENTAL INCOME: 75% of gross rent per Schedule E minus PITIA,
       vacancy factor per B3-3.1-08.

    5. CALCULATE RETIREMENT INCOME: Social Security, pension, IRA/401k
       distributions with continuity verification per B3-3.1-09.

    6. AGGREGATE INCOME: Sum all qualifying sources, weighted confidence,
       composite method determination.

    7. DTI RATIOS: Front-end (housing) and back-end (total) DTI with
       program-specific threshold warnings.

    8. TREND ANALYSIS: Year-over-year direction, declining income triggers,
       variable income flagging.

    9. GAP DETECTION: Employment history gaps, stale documentation,
       VOE recommendations.

    10. GROSS-UP: Non-taxable income gross-up at 25% (or actual tax rate)
        per Fannie Mae B3-3.1-09.

    11. STATED VS CALCULATED: Compare application stated income to
        document-calculated income, flag material variances.

    12. FINDINGS GENERATION: Create underwriter review tasks for all
        flagged issues with AI recommendations.

    13. DOC STATUS: Check which income documents are present, missing,
        expired, or need refresh.

    14. APPROACH RECOMMENDATION: Based on available docs and borrower
        profile, recommend the optimal income calculation method.

    15. SUMMARY REPORT: Create formatted income summary suitable for
        the loan file and underwriter review.
    """

    @property
    def name(self) -> str:
        return "IncomeAnalysisAgent"

    @property
    def description(self) -> str:
        return (
            "AI-powered income analysis agent for mortgage underwriting. "
            "Calculates qualifying income from W2, self-employment, commission, "
            "rental, and retirement sources per Fannie Mae Selling Guide rules. "
            "Generates DTI ratios, trend analysis, gap detection, gross-up "
            "calculations, and underwriter-ready findings."
        )

    def _register_tools(self):
        """Register all income analysis tools."""

        # Tool 1: Calculate W2 Income
        self.register_tool(AgentTool(
            name="calculate_w2_income",
            description=(
                "Calculate W2/salaried employee qualifying income from paystubs and W2s. "
                "Annualizes current pay from paystubs, cross-checks against W2 history, "
                "breaks down base/OT/bonus/commission, applies 2-year averaging for "
                "variable components, and detects declining trends per Fannie Mae B3-3.1."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_w2_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 2: Calculate Self-Employment Income
        self.register_tool(AgentTool(
            name="calculate_self_employment_income",
            description=(
                "Calculate self-employment qualifying income from personal and business "
                "tax returns. Uses 2-year average from Schedule C net profit or K-1 "
                "distributions with depreciation/amortization/depletion add-backs per "
                "Fannie Mae B3-3.4. Flags declining income and insufficient history."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_self_employment_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 3: Calculate Commission Income
        self.register_tool(AgentTool(
            name="calculate_commission_income",
            description=(
                "Calculate commission and bonus qualifying income with 2-year trending. "
                "Requires 2-year history per Fannie Mae B3-3.1-09. Detects high commission "
                "ratio (>25% of total income) and declining commission trends. Uses lower "
                "of 2-year average or most recent year when declining >25%."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_commission_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 4: Calculate Rental Income
        self.register_tool(AgentTool(
            name="calculate_rental_income",
            description=(
                "Calculate rental income per Schedule E from tax returns. Applies Fannie Mae "
                "75% factor (25% vacancy/maintenance) to gross rents per B3-3.1-08. Uses "
                "2-year average when available. Flags negative rental cash flow which must "
                "be counted as a monthly obligation."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_rental_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 5: Calculate Retirement Income
        self.register_tool(AgentTool(
            name="calculate_retirement_income",
            description=(
                "Calculate pension, Social Security, and retirement distribution qualifying "
                "income. Verifies 3-year continuity requirement per Fannie Mae B3-3.1-09. "
                "Handles Social Security award letters, pension statements, and IRA/401k "
                "distributions. Non-taxable portions eligible for gross-up."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_retirement_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 6: Aggregate Total Qualifying Income
        self.register_tool(AgentTool(
            name="aggregate_total_qualifying_income",
            description=(
                "Sum all income sources for a borrower to produce total qualifying monthly "
                "and annual income. Calculates weighted confidence score, determines composite "
                "calculation method, and runs the full IncomeCalculatorService pipeline "
                "including flag generation and task creation."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._aggregate_total_qualifying_income,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 7: Calculate DTI Ratios
        self.register_tool(AgentTool(
            name="calculate_dti_ratios",
            description=(
                "Calculate front-end (housing) and back-end (total) debt-to-income ratios. "
                "Front-end = PITIA / qualifying income. Back-end = (PITIA + obligations) / "
                "qualifying income. Includes program-specific threshold warnings for "
                "conventional (45%), FHA (43%), VA (41%), and DU maximum (50%)."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_dti_ratios,
            input_schema=DTIInput,
        ))

        # Tool 8: Analyze Income Trend
        self.register_tool(AgentTool(
            name="analyze_income_trend",
            description=(
                "Analyze year-over-year income trend for a borrower. Determines if income "
                "is INCREASING (>5% YoY), STABLE (+/-5%), DECLINING (>5% decrease), or "
                "VARIABLE (insufficient data). Critical for underwriting -- declining income "
                "requires use of lower figure per Fannie Mae guidelines."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_income_trend,
            input_schema=IncomeTrendInput,
        ))

        # Tool 9: Detect Income Gaps
        self.register_tool(AgentTool(
            name="detect_income_gaps",
            description=(
                "Detect employment gaps in income history by analyzing paystub dates, "
                "W2 tax years, and VOE records. Identifies periods of unemployment, "
                "stale paystubs (>30 days old), and missing tax years. Gaps >6 months "
                "require LOE (Letter of Explanation) per Fannie Mae B3-3.1-01."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._detect_income_gaps,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 10: Gross Up Non-Taxable Income
        self.register_tool(AgentTool(
            name="gross_up_nontaxable_income",
            description=(
                "Apply non-taxable income gross-up per Fannie Mae B3-3.1-09. Default "
                "factor is 25% (multiply by 1.25). If borrower's actual tax rate is known, "
                "uses that rate instead. Applicable to Social Security, disability, child "
                "support, military allowances, and tax-exempt interest income."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._gross_up_nontaxable_income,
            input_schema=GrossUpInput,
        ))

        # Tool 11: Compare Income to Stated
        self.register_tool(AgentTool(
            name="compare_income_to_stated",
            description=(
                "Compare document-calculated qualifying income to the income stated on the "
                "loan application (1003). Flags material variances (>10%) which may indicate "
                "data entry errors, undisclosed income sources, or misrepresentation. "
                "Critical for QC and compliance."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_income_to_stated,
            input_schema=CompareIncomeInput,
        ))

        # Tool 12: Generate Income Findings
        self.register_tool(AgentTool(
            name="generate_income_findings",
            description=(
                "Generate findings and verification tasks for underwriter review based on "
                "income calculation results. Creates tasks for declining income, employment "
                "gaps, document mismatches, high DTI, insufficient history, and other "
                "flags requiring human review or additional documentation."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_income_findings,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 13: Get Income Documentation Status
        self.register_tool(AgentTool(
            name="get_income_documentation_status",
            description=(
                "Check if all required income documents are present for a borrower. "
                "Evaluates paystubs (within 30 days), W2s (most recent 2 years), tax "
                "returns (2 years for SE), and VOE status. Returns completeness percentage "
                "and list of missing/expired documents."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_income_documentation_status,
            input_schema=LoanBorrowerInput,
        ))

        # Tool 14: Recommend Income Approach
        self.register_tool(AgentTool(
            name="recommend_income_approach",
            description=(
                "Recommend the best income calculation approach based on available documents "
                "and borrower employment profile. Considers W2 vs self-employed vs mixed, "
                "available doc types, loan program requirements, and suggests which "
                "calculation method will produce the most favorable qualifying income."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_income_approach,
            input_schema=IncomeApproachInput,
        ))

        # Tool 15: Create Income Summary Report
        self.register_tool(AgentTool(
            name="create_income_summary_report",
            description=(
                "Create a formatted income summary report suitable for the loan file and "
                "underwriter review. Includes all income sources with breakdowns, DTI "
                "ratios, trend analysis, flags, recommendations, and document inventory. "
                "Output is structured for display or PDF generation."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._create_income_summary_report,
            input_schema=LoanBorrowerInput,
        ))

    # ========================================================================
    # HELPERS
    # ========================================================================

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
        """Given a YYYY-MM-DD pay date, return months elapsed in that year."""
        if not pay_date_str:
            return None
        try:
            pay_date = datetime.strptime(str(pay_date_str)[:10], "%Y-%m-%d").date()
            month = pay_date.month
            day = pay_date.day
            # Partial month: if past the 15th, count the full month
            if day >= 15:
                return month
            return max(1, month - 1) if month > 1 else 1
        except (ValueError, TypeError):
            return None

    def _compute_trend(
        self,
        year1: Optional[Decimal],
        year2: Optional[Decimal],
    ) -> Tuple[str, Optional[Decimal]]:
        """Compute income trend direction and YoY percentage change."""
        if year1 is None or year2 is None:
            return ("VARIABLE", None)
        if year2 == ZERO:
            if year1 > ZERO:
                return ("INCREASING", Decimal("100.00"))
            return ("STABLE", ZERO)
        pct = ((year1 - year2) / abs(year2) * 100).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        if pct > Decimal("5"):
            return ("INCREASING", pct)
        elif pct < Decimal("-5"):
            return ("DECLINING", pct)
        return ("STABLE", pct)

    def _verify_loan_ownership(self, db, loan_id: int, org_id: str):
        """Verify loan belongs to organization. Returns loan row or None.

        Logs a tenant isolation warning if the loan is not found for this org.
        """
        row = db.execute(
            text(
                "SELECT id, loan_number, borrower_name, loan_type, stage, "
                "proposed_monthly_payment, total_monthly_obligations, "
                "borrower_stated_income "
                "FROM loans "
                "WHERE id = :loan_id AND organization_id = :org_id"
            ),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: loan %s access denied for org %s by agent %s",
                loan_id, org_id, self.name,
            )
        return row

    def _gather_income_docs(
        self, db, loan_id: int, borrower_id: int, doc_types: Optional[tuple] = None,
    ) -> List[Dict]:
        """Gather income documents with extracted field data."""
        if doc_types is None:
            doc_types = INCOME_DOC_TYPES

        rows = db.execute(
            text("""
                SELECT
                    sd.id AS doc_id,
                    sd.doc_type,
                    sd.uploaded_at,
                    sd.file_name,
                    sde.extracted_fields,
                    sde.confidence_scores,
                    sde.overall_confidence
                FROM smart_documents sd
                LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                WHERE sd.loan_id = :loan_id
                  AND sd.borrower_id = :borrower_id
                  AND sd.doc_type IN :doc_types
                  AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                ORDER BY sd.uploaded_at DESC
            """),
            {"loan_id": loan_id, "borrower_id": borrower_id, "doc_types": doc_types},
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
                "uploaded_at": row.uploaded_at,
                "file_name": row.file_name,
                "extracted_fields": extracted or {},
                "confidence_scores": confidence_scores or {},
                "overall_confidence": row.overall_confidence or 0,
            })
        return results

    def _get_latest_calculation(self, db, loan_id: int, borrower_id: int) -> Optional[Dict]:
        """Get most recent income calculation result from DB."""
        row = db.execute(
            text("""
                SELECT
                    ic.id, ic.total_qualifying_monthly_income,
                    ic.total_qualifying_annual_income,
                    ic.calculation_method, ic.dti_front_end, ic.dti_back_end,
                    ic.ai_confidence_score, ic.ai_flags, ic.ai_recommendations,
                    ic.status, ic.created_at
                FROM income_calculations ic
                WHERE ic.loan_id = :loan_id AND ic.borrower_id = :borrower_id
                  AND ic.status NOT IN ('rejected', 'superseded')
                ORDER BY ic.created_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id, "borrower_id": borrower_id},
        ).fetchone()

        if not row:
            return None

        flags = row.ai_flags
        if isinstance(flags, str):
            try:
                flags = json.loads(flags)
            except (json.JSONDecodeError, TypeError):
                flags = []

        recs = row.ai_recommendations
        if isinstance(recs, str):
            try:
                recs = json.loads(recs)
            except (json.JSONDecodeError, TypeError):
                recs = []

        return {
            "calculation_id": row.id,
            "total_qualifying_monthly": float(row.total_qualifying_monthly_income or 0),
            "total_qualifying_annual": float(row.total_qualifying_annual_income or 0),
            "calculation_method": row.calculation_method,
            "dti_front_end": float(row.dti_front_end) if row.dti_front_end else None,
            "dti_back_end": float(row.dti_back_end) if row.dti_back_end else None,
            "confidence": row.ai_confidence_score or 0,
            "flags": flags or [],
            "recommendations": recs or [],
            "status": row.status,
            "calculated_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _get_income_sources(self, db, calculation_id: int) -> List[Dict]:
        """Get income sources for a calculation."""
        rows = db.execute(
            text("""
                SELECT
                    id, source_type, employer_name, position_title,
                    is_primary,
                    base_monthly_income, overtime_monthly,
                    bonus_monthly, commission_monthly, other_monthly,
                    total_monthly_income, total_annual_income,
                    trending_direction,
                    year1_income, year2_income,
                    year_over_year_change_pct,
                    verification_status,
                    source_document_ids,
                    ai_confidence, ai_notes
                FROM income_sources
                WHERE calculation_id = :calc_id
                ORDER BY is_primary DESC, total_monthly_income DESC
            """),
            {"calc_id": calculation_id},
        ).fetchall()

        sources = []
        for r in rows:
            doc_ids = r.source_document_ids
            if isinstance(doc_ids, str):
                try:
                    doc_ids = json.loads(doc_ids)
                except (json.JSONDecodeError, TypeError):
                    doc_ids = []
            sources.append({
                "source_id": r.id,
                "source_type": r.source_type,
                "employer_name": r.employer_name,
                "position_title": r.position_title,
                "is_primary": r.is_primary,
                "base_monthly": float(r.base_monthly_income or 0),
                "overtime_monthly": float(r.overtime_monthly or 0),
                "bonus_monthly": float(r.bonus_monthly or 0),
                "commission_monthly": float(r.commission_monthly or 0),
                "other_monthly": float(r.other_monthly or 0),
                "total_monthly": float(r.total_monthly_income or 0),
                "total_annual": float(r.total_annual_income or 0),
                "trending": r.trending_direction,
                "year1_income": float(r.year1_income) if r.year1_income else None,
                "year2_income": float(r.year2_income) if r.year2_income else None,
                "yoy_change_pct": float(r.year_over_year_change_pct) if r.year_over_year_change_pct else None,
                "verification_status": r.verification_status,
                "confidence": r.ai_confidence or 0,
                "notes": r.ai_notes,
                "source_doc_ids": doc_ids or [],
            })
        return sources

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _calculate_w2_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate W2/salaried employee qualifying income."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(
                db, loan_id, borrower_id, doc_types=("PAYSTUB", "W2")
            )
            paystubs = [d for d in docs if d["doc_type"] == "PAYSTUB"]
            w2s = [d for d in docs if d["doc_type"] == "W2"]

            if not paystubs and not w2s:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_documents",
                        "message": "No paystubs or W2s found for this borrower.",
                    },
                    message="No W2/paystub documents found",
                )

            flags: List[str] = []
            base_monthly = ZERO
            ot_monthly = ZERO
            bonus_monthly = ZERO
            commission_monthly = ZERO
            other_monthly = ZERO
            employer_name = None
            position_title = None
            confidence = 50

            # Current income from most recent paystub
            if paystubs:
                paystubs_sorted = sorted(
                    paystubs,
                    key=lambda d: d["extracted_fields"].get("pay_date", "0000-00-00"),
                    reverse=True,
                )
                latest = paystubs_sorted[0]["extracted_fields"]
                confidence = paystubs_sorted[0].get("overall_confidence", 50)
                employer_name = latest.get("employer_name")
                position_title = latest.get("job_title")

                gross_pay = self._to_decimal(latest.get("gross_pay"))
                pay_freq = (latest.get("pay_frequency") or "MONTHLY").upper()
                multiplier = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq, 12)

                if gross_pay > ZERO:
                    annualized = gross_pay * Decimal(multiplier)
                    base_monthly = (annualized / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                # OT/bonus/commission from YTD
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
                        pay_date = datetime.strptime(str(pay_date_str)[:10], "%Y-%m-%d").date()
                        days_old = (date.today() - pay_date).days
                        if days_old > PAYSTUB_STALENESS_DAYS:
                            flags.append(f"STALE_PAYSTUB: Most recent paystub is {days_old} days old")
                    except (ValueError, TypeError):
                        pass

            # Historical from W2s
            year1_income = None
            year2_income = None
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

            # Derive from W2 if no paystubs
            if not paystubs and year1_income:
                base_monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            trending, yoy_pct = self._compute_trend(year1_income, year2_income)

            total_monthly = (
                base_monthly + ot_monthly + bonus_monthly + commission_monthly + other_monthly
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Declining income: use 2-year W2 average if lower
            if year1_income and year2_income and trending == "DECLINING":
                w2_avg_monthly = ((year1_income + year2_income) / 24).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                if w2_avg_monthly < total_monthly:
                    total_monthly = w2_avg_monthly
                    base_monthly = total_monthly
                    ot_monthly = bonus_monthly = commission_monthly = other_monthly = ZERO
                    flags.append("USED_TWO_YEAR_AVERAGE: Income declining, used lower 2-year W2 average")

            total_annual = (total_monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if w2s:
                confidence = min(95, confidence + 10)
            if not paystubs:
                confidence = max(30, confidence - 20)

            self.audit_log(
                "calculate_w2_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "total_monthly": float(total_monthly),
                    "paystubs": len(paystubs),
                    "w2s": len(w2s),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "source_type": "W2_EMPLOYMENT",
                    "employer_name": employer_name,
                    "position_title": position_title,
                    "base_monthly": float(base_monthly),
                    "overtime_monthly": float(ot_monthly),
                    "bonus_monthly": float(bonus_monthly),
                    "commission_monthly": float(commission_monthly),
                    "other_monthly": float(other_monthly),
                    "total_monthly": float(total_monthly),
                    "total_annual": float(total_annual),
                    "trending": trending,
                    "yoy_change_pct": float(yoy_pct) if yoy_pct is not None else None,
                    "year1_income": float(year1_income) if year1_income else None,
                    "year2_income": float(year2_income) if year2_income else None,
                    "confidence": confidence,
                    "flags": flags,
                    "documents_used": {
                        "paystubs": len(paystubs),
                        "w2s": len(w2s),
                    },
                },
                message=(
                    f"W2 income: ${float(total_monthly):,.2f}/mo "
                    f"(${float(total_annual):,.2f}/yr) - {trending}"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_w2_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_self_employment_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate self-employment qualifying income from tax returns."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(
                db, loan_id, borrower_id,
                doc_types=("TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS"),
            )

            if not docs:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_documents",
                        "message": "No tax returns or P&L statements found.",
                    },
                    message="No self-employment income documents found",
                )

            flags: List[str] = []
            yearly_data: Dict[int, Decimal] = {}
            business_name = None
            addback_details: Dict[int, Dict] = {}

            for doc in docs:
                ef = doc["extracted_fields"]
                tax_year = ef.get("tax_year")
                if not tax_year:
                    continue
                try:
                    tax_year = int(tax_year)
                except (ValueError, TypeError):
                    continue

                if doc["doc_type"] in ("BUSINESS_TAX_RETURN", "TAX_RETURN"):
                    net_profit = self._to_decimal(
                        ef.get("net_profit_loss") or ef.get("net_profit") or ef.get("adjusted_gross_income")
                    )
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
                    addback_details[tax_year] = {
                        "net_profit": float(net_profit),
                        "depreciation": float(depreciation),
                        "amortization": float(amortization),
                        "depletion": float(depletion),
                        "k1_ordinary": float(k1_ordinary),
                        "k1_guaranteed": float(k1_guaranteed),
                        "adjusted_total": float(adjusted),
                    }

                    if not business_name:
                        business_name = ef.get("business_name") or ef.get("employer_name")

                elif doc["doc_type"] == "PROFIT_LOSS":
                    net_profit = self._to_decimal(ef.get("net_profit") or ef.get("net_profit_loss"))
                    if net_profit:
                        yearly_data[tax_year] = yearly_data.get(tax_year, ZERO) + net_profit
                    if not business_name:
                        business_name = ef.get("business_name") or ef.get("owner_name")

            if not yearly_data:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_data_extracted",
                        "message": "Tax returns found but no income data could be extracted.",
                        "flags": ["NO_SELF_EMPLOYMENT_DATA"],
                    },
                    message="No self-employment income data extracted",
                )

            sorted_years = sorted(yearly_data.keys(), reverse=True)
            year1_income = yearly_data[sorted_years[0]]
            year2_income = yearly_data[sorted_years[1]] if len(sorted_years) >= 2 else None

            if year2_income is not None:
                total_two = year1_income + year2_income
                monthly = (total_two / 24).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                if year1_income < year2_income and year2_income > ZERO:
                    decline_pct = ((year2_income - year1_income) / year2_income * 100).quantize(TWO_PLACES)
                    if decline_pct >= DECLINING_INCOME_CRITICAL_PCT:
                        flags.append(
                            f"DECLINING_SELF_EMPLOYMENT: Income declined {decline_pct}% "
                            f"({sorted_years[1]} to {sorted_years[0]})"
                        )
                        monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                        flags.append("USED_LOWER_YEAR: Declining >20%, used most recent year only")
            else:
                monthly = (year1_income / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                flags.append("INSUFFICIENT_HISTORY: Only 1 year of self-employment income available")

            trending, yoy_pct = self._compute_trend(year1_income, year2_income)
            total_annual = (monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if total_annual < ZERO:
                flags.append("NEGATIVE_INCOME: Business shows a net loss")

            confidence = 70 if year2_income is not None else 45

            self.audit_log(
                "calculate_self_employment_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "total_monthly": float(monthly),
                    "years_available": len(sorted_years),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "source_type": "SELF_EMPLOYMENT",
                    "business_name": business_name,
                    "total_monthly": float(monthly),
                    "total_annual": float(total_annual),
                    "trending": trending,
                    "yoy_change_pct": float(yoy_pct) if yoy_pct is not None else None,
                    "year1_income": float(year1_income),
                    "year1_year": sorted_years[0],
                    "year2_income": float(year2_income) if year2_income else None,
                    "year2_year": sorted_years[1] if len(sorted_years) >= 2 else None,
                    "addback_details": addback_details,
                    "confidence": confidence,
                    "flags": flags,
                    "guideline_reference": "Fannie Mae B3-3.4 (Self-Employment Income)",
                },
                message=(
                    f"SE income: ${float(monthly):,.2f}/mo "
                    f"({len(sorted_years)}-year {'average' if len(sorted_years) >= 2 else 'single year'}) - {trending}"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_self_employment_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_commission_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate commission/bonus income with 2-year trending."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(
                db, loan_id, borrower_id, doc_types=("PAYSTUB", "W2")
            )
            paystubs = [d for d in docs if d["doc_type"] == "PAYSTUB"]
            w2s = [d for d in docs if d["doc_type"] == "W2"]

            if not paystubs:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_paystubs",
                        "message": "Paystubs required to identify commission income.",
                    },
                    message="No paystubs found for commission analysis",
                )

            paystubs_sorted = sorted(
                paystubs,
                key=lambda d: d["extracted_fields"].get("pay_date", "0000-00-00"),
                reverse=True,
            )
            latest = paystubs_sorted[0]["extracted_fields"]
            ytd_commission = self._to_decimal(latest.get("ytd_commission"))
            pay_date_str = latest.get("pay_date")

            if ytd_commission <= ZERO:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_commission",
                        "message": "No commission income found on paystubs.",
                    },
                    message="No commission income detected",
                )

            ytd_gross = self._to_decimal(latest.get("ytd_gross"))
            if ytd_gross <= ZERO:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_gross_data",
                        "message": "Cannot determine commission ratio without YTD gross.",
                    },
                    message="Insufficient data for commission analysis",
                )

            commission_ratio = (ytd_commission / ytd_gross * 100).quantize(TWO_PLACES)
            if commission_ratio < Decimal("5"):
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "immaterial",
                        "commission_ratio": float(commission_ratio),
                        "message": f"Commission is {commission_ratio}% of gross -- below 5% materiality threshold.",
                    },
                    message=f"Commission is {commission_ratio}% of gross (immaterial)",
                )

            flags: List[str] = []
            months_elapsed = self._months_elapsed_in_year(pay_date_str)
            if months_elapsed and months_elapsed > 0:
                current_annual = (ytd_commission / Decimal(months_elapsed) * 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                current_annual = ytd_commission

            prior_year_commission = None
            if len(w2s) >= 2:
                w2s_sorted = sorted(
                    w2s,
                    key=lambda d: d["extracted_fields"].get("tax_year", 0),
                    reverse=True,
                )
                year2_wages = self._to_decimal(
                    w2s_sorted[1]["extracted_fields"].get("wages_tips_compensation")
                )
                if year2_wages > ZERO and commission_ratio > ZERO:
                    prior_year_commission = (year2_wages * commission_ratio / 100).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP
                    )

            if prior_year_commission is None:
                flags.append("INSUFFICIENT_HISTORY: Commission income requires 2-year history for qualification")
                monthly = (current_annual / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                two_year_avg = ((current_annual + prior_year_commission) / 2).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                if current_annual < prior_year_commission and prior_year_commission > ZERO:
                    decline_pct = (
                        (prior_year_commission - current_annual) / prior_year_commission * 100
                    ).quantize(TWO_PLACES)
                    if decline_pct >= DECLINING_COMMISSION_THRESHOLD_PCT:
                        flags.append(f"DECLINING_COMMISSION: Commission declined {decline_pct}% year-over-year")
                        two_year_avg = current_annual
                monthly = (two_year_avg / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if commission_ratio >= HIGH_COMMISSION_RATIO_PCT:
                flags.append(f"HIGH_COMMISSION_RATIO: Commission is {commission_ratio}% of total income")

            trending, yoy_pct = self._compute_trend(current_annual, prior_year_commission)

            self.audit_log(
                "calculate_commission_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "monthly": float(monthly),
                    "commission_ratio": float(commission_ratio),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "source_type": "COMMISSION",
                    "commission_monthly": float(monthly),
                    "commission_annual": float(monthly * 12),
                    "commission_ratio_pct": float(commission_ratio),
                    "current_year_annualized": float(current_annual),
                    "prior_year_estimated": float(prior_year_commission) if prior_year_commission else None,
                    "trending": trending,
                    "yoy_change_pct": float(yoy_pct) if yoy_pct is not None else None,
                    "confidence": 55 if prior_year_commission else 35,
                    "flags": flags,
                    "guideline_reference": "Fannie Mae B3-3.1-09 (Commission Income)",
                },
                message=(
                    f"Commission: ${float(monthly):,.2f}/mo "
                    f"({float(commission_ratio)}% of gross) - {trending}"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_commission_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_rental_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate rental income per Schedule E."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(
                db, loan_id, borrower_id, doc_types=("TAX_RETURN",)
            )

            schedule_e_data: Dict[int, Dict[str, Decimal]] = {}

            for doc in docs:
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

                schedule_e_data[tax_year] = {
                    "gross_rents": gross_rents,
                    "total_expenses": self._to_decimal(ef.get("schedule_e_total_expenses")),
                    "depreciation": self._to_decimal(ef.get("schedule_e_depreciation")),
                    "net_income": self._to_decimal(ef.get("schedule_e_net_income_loss")),
                }

            if not schedule_e_data:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_rental_data",
                        "message": "No Schedule E rental income data found in tax returns.",
                    },
                    message="No rental income data found",
                )

            flags: List[str] = []
            sorted_years = sorted(schedule_e_data.keys(), reverse=True)
            yearly_qualifying: List[Decimal] = []
            property_details = []

            for year_key in sorted_years[:2]:
                data = schedule_e_data[year_key]
                # 75% of gross rents (25% vacancy factor)
                net_rental = (data["gross_rents"] * (Decimal("1") - RENTAL_VACANCY_FACTOR)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                annual_qualifying = net_rental * 12 if net_rental > ZERO else net_rental
                yearly_qualifying.append(annual_qualifying)
                property_details.append({
                    "tax_year": year_key,
                    "gross_rents_monthly": float(data["gross_rents"]),
                    "after_vacancy_monthly": float(net_rental),
                    "annual_qualifying": float(annual_qualifying),
                    "total_expenses": float(data["total_expenses"]),
                    "depreciation": float(data["depreciation"]),
                    "net_income_reported": float(data["net_income"]),
                })

            if len(yearly_qualifying) >= 2:
                avg_annual = ((yearly_qualifying[0] + yearly_qualifying[1]) / 2).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                avg_annual = yearly_qualifying[0].quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                flags.append("INSUFFICIENT_RENTAL_HISTORY: Only 1 year of Schedule E available")

            monthly = (avg_annual / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if monthly < ZERO:
                flags.append("NEGATIVE_RENTAL_CASHFLOW: Rental income is negative -- treated as monthly obligation")

            year1 = yearly_qualifying[0] if len(yearly_qualifying) >= 1 else None
            year2 = yearly_qualifying[1] if len(yearly_qualifying) >= 2 else None
            trending, yoy_pct = self._compute_trend(year1, year2)

            self.audit_log(
                "calculate_rental_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "monthly": float(monthly),
                    "properties": len(property_details),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "source_type": "RENTAL",
                    "total_monthly": float(monthly),
                    "total_annual": float(avg_annual),
                    "vacancy_factor": float(RENTAL_VACANCY_FACTOR),
                    "trending": trending,
                    "yoy_change_pct": float(yoy_pct) if yoy_pct is not None else None,
                    "property_details": property_details,
                    "confidence": 60 if year2 else 40,
                    "flags": flags,
                    "guideline_reference": "Fannie Mae B3-3.1-08 (Rental Income)",
                },
                message=(
                    f"Rental income: ${float(monthly):,.2f}/mo "
                    f"(75% of gross after vacancy factor) - {trending}"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_rental_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_retirement_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate pension/SS/retirement distribution income."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Check for retirement income documents
            # These may be typed as TAX_RETURN (1099-R) or custom doc types
            retirement_docs = db.execute(
                text("""
                    SELECT
                        sd.id AS doc_id, sd.doc_type, sd.file_name,
                        sde.extracted_fields, sde.overall_confidence
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                      AND sd.borrower_id = :borrower_id
                      AND sd.doc_type IN ('SSA_AWARD_LETTER', 'PENSION_STATEMENT',
                                          '1099_R', 'TAX_RETURN', 'RETIREMENT_STATEMENT')
                      AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                    ORDER BY sd.uploaded_at DESC
                """),
                {"loan_id": loan_id, "borrower_id": borrower_id},
            ).fetchall()

            sources: List[Dict] = []
            flags: List[str] = []
            total_monthly = ZERO

            for doc in retirement_docs:
                ef = doc.extracted_fields
                if isinstance(ef, str):
                    try:
                        ef = json.loads(ef)
                    except (json.JSONDecodeError, TypeError):
                        ef = {}
                if not ef:
                    continue

                doc_type = str(doc.doc_type)

                if doc_type == "SSA_AWARD_LETTER":
                    ss_monthly = self._to_decimal(ef.get("monthly_benefit_amount"))
                    if ss_monthly > ZERO:
                        sources.append({
                            "type": "social_security",
                            "monthly_amount": float(ss_monthly),
                            "is_nontaxable": True,
                            "grossed_up_monthly": float(
                                (ss_monthly * NONTAXABLE_GROSSUP_FACTOR).quantize(TWO_PLACES)
                            ),
                            "doc_id": doc.doc_id,
                            "continuity_verified": True,
                        })
                        total_monthly += ss_monthly

                elif doc_type == "PENSION_STATEMENT":
                    pension_monthly = self._to_decimal(ef.get("monthly_pension_amount"))
                    if pension_monthly > ZERO:
                        sources.append({
                            "type": "pension",
                            "monthly_amount": float(pension_monthly),
                            "is_nontaxable": False,
                            "doc_id": doc.doc_id,
                            "continuity_verified": bool(ef.get("continuity_confirmed")),
                        })
                        total_monthly += pension_monthly

                elif doc_type in ("1099_R", "TAX_RETURN"):
                    distribution = self._to_decimal(
                        ef.get("retirement_distribution") or ef.get("1099r_gross_distribution")
                    )
                    if distribution > ZERO:
                        dist_monthly = (distribution / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                        sources.append({
                            "type": "retirement_distribution",
                            "annual_amount": float(distribution),
                            "monthly_amount": float(dist_monthly),
                            "is_nontaxable": False,
                            "doc_id": doc.doc_id,
                            "tax_year": ef.get("tax_year"),
                        })
                        total_monthly += dist_monthly

            if not sources:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_retirement_income",
                        "message": "No retirement income documents found.",
                    },
                    message="No retirement income found",
                )

            # Check 3-year continuity requirement
            for src in sources:
                if src["type"] == "retirement_distribution":
                    flags.append(
                        "VERIFY_CONTINUITY: Retirement distributions must be verified "
                        "to continue for at least 3 years per Fannie Mae B3-3.1-09"
                    )
                    break

            total_annual = (total_monthly * 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            self.audit_log(
                "calculate_retirement_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "total_monthly": float(total_monthly),
                    "source_count": len(sources),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "source_type": "RETIREMENT",
                    "total_monthly": float(total_monthly),
                    "total_annual": float(total_annual),
                    "sources": sources,
                    "confidence": 75 if len(sources) >= 2 else 55,
                    "flags": flags,
                    "guideline_reference": "Fannie Mae B3-3.1-09 (Retirement Income)",
                },
                message=(
                    f"Retirement income: ${float(total_monthly):,.2f}/mo "
                    f"from {len(sources)} source(s)"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_retirement_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _aggregate_total_qualifying_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Aggregate all income sources using the IncomeCalculatorService."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.income_calculator_service import (
                get_income_calculator_service,
            )
            service = get_income_calculator_service(db)
            result = service.calculate_income(loan_id=loan_id, borrower_id=borrower_id)

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "Income calculation failed",
                )

            sources_data = []
            for src in result.sources:
                sources_data.append({
                    "source_type": src.source_type,
                    "employer_name": src.employer_name,
                    "position_title": src.position_title,
                    "base_monthly": float(src.base_monthly),
                    "overtime_monthly": float(src.overtime_monthly),
                    "bonus_monthly": float(src.bonus_monthly),
                    "commission_monthly": float(src.commission_monthly),
                    "other_monthly": float(src.other_monthly),
                    "total_monthly": float(src.total_monthly),
                    "total_annual": float(src.total_annual),
                    "trending": src.trending,
                    "yoy_change_pct": float(src.yoy_change_pct) if src.yoy_change_pct else None,
                    "confidence": src.confidence,
                    "flags": src.flags,
                })

            self.audit_log(
                "aggregate_total_qualifying_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "total_monthly": float(result.total_qualifying_monthly),
                    "source_count": len(result.sources),
                    "flag_count": len(result.flags),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "total_qualifying_monthly": float(result.total_qualifying_monthly),
                    "total_qualifying_annual": float(result.total_qualifying_annual),
                    "calculation_method": result.calculation_method,
                    "dti_front_end": float(result.dti_front_end) if result.dti_front_end else None,
                    "dti_back_end": float(result.dti_back_end) if result.dti_back_end else None,
                    "confidence": result.confidence,
                    "sources": sources_data,
                    "flags": result.flags,
                    "recommendations": result.recommendations,
                    "tasks_created": len(result.tasks_to_create),
                },
                message=(
                    f"Total qualifying: ${float(result.total_qualifying_monthly):,.2f}/mo "
                    f"({len(result.sources)} sources, {len(result.flags)} flags)"
                ),
            )

        except Exception as e:
            logger.exception(f"aggregate_total_qualifying_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_dti_ratios(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate front-end and back-end DTI ratios."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get qualifying income
            calc = self._get_latest_calculation(db, loan_id, borrower_id)
            if not calc or calc["total_qualifying_monthly"] <= 0:
                return ToolResult(
                    success=False,
                    error="No qualifying income calculated. Run aggregate_total_qualifying_income first.",
                )

            monthly_income = self._to_decimal(calc["total_qualifying_monthly"])

            # Get housing payment and obligations
            pitia = self._to_decimal(
                input_data.get("proposed_housing_payment") or loan.proposed_monthly_payment
            )
            obligations = self._to_decimal(
                input_data.get("total_monthly_obligations") or loan.total_monthly_obligations
            )

            if pitia <= ZERO:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "missing_housing_payment",
                        "qualifying_monthly_income": float(monthly_income),
                        "message": "Proposed housing payment not available. Cannot calculate DTI.",
                    },
                    message="Proposed housing payment needed for DTI calculation",
                )

            front_end = (pitia / monthly_income * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            back_end = ((pitia + obligations) / monthly_income * 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            # Program-specific thresholds
            loan_type = (loan.loan_type or "conventional").lower()
            warnings: List[str] = []

            if loan_type == "fha":
                back_end_limit = DTI_BACK_END_FHA
                if front_end > Decimal("31"):
                    warnings.append(f"FHA front-end DTI {front_end}% exceeds 31% guideline")
            elif loan_type == "va":
                back_end_limit = DTI_BACK_END_VA
            else:
                back_end_limit = DTI_BACK_END_CONVENTIONAL
                if front_end > DTI_FRONT_END_LIMIT:
                    warnings.append(f"Front-end DTI {front_end}% exceeds 28% guideline")

            if back_end > DTI_BACK_END_DU_MAXIMUM:
                warnings.append(f"Back-end DTI {back_end}% exceeds DU maximum of 50%")
            elif back_end > back_end_limit:
                warnings.append(
                    f"Back-end DTI {back_end}% exceeds {loan_type.upper()} guideline of {back_end_limit}%"
                )

            self.audit_log(
                "calculate_dti_ratios", "loan",
                entity_id=str(loan_id),
                details={
                    "front_end": float(front_end),
                    "back_end": float(back_end),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "qualifying_monthly_income": float(monthly_income),
                    "proposed_housing_payment": float(pitia),
                    "total_monthly_obligations": float(obligations),
                    "total_monthly_debt": float(pitia + obligations),
                    "front_end_dti": float(front_end),
                    "back_end_dti": float(back_end),
                    "loan_program": loan_type,
                    "guideline_limits": {
                        "front_end": float(DTI_FRONT_END_LIMIT),
                        "back_end": float(back_end_limit),
                        "du_maximum": float(DTI_BACK_END_DU_MAXIMUM),
                    },
                    "within_guidelines": len(warnings) == 0,
                    "warnings": warnings,
                },
                message=(
                    f"DTI: {float(front_end)}% / {float(back_end)}% "
                    f"({'within' if not warnings else 'exceeds'} {loan_type.upper()} guidelines)"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_dti_ratios failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_income_trend(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Analyze year-over-year income trend."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        source_type_filter = input_data.get("source_type")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            calc = self._get_latest_calculation(db, loan_id, borrower_id)
            if not calc:
                return ToolResult(
                    success=False,
                    error="No income calculation found. Run aggregate_total_qualifying_income first.",
                )

            sources = self._get_income_sources(db, calc["calculation_id"])
            if source_type_filter:
                sources = [s for s in sources if s["source_type"].lower() == source_type_filter.lower()]

            if not sources:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_sources",
                        "message": f"No {'matching ' if source_type_filter else ''}income sources found.",
                    },
                    message="No income sources to analyze",
                )

            trend_results = []
            overall_direction = "STABLE"
            has_declining = False

            for src in sources:
                year1 = self._to_decimal(src["year1_income"]) if src["year1_income"] else None
                year2 = self._to_decimal(src["year2_income"]) if src["year2_income"] else None
                direction, pct = self._compute_trend(year1, year2)

                if direction == "DECLINING":
                    has_declining = True

                trend_results.append({
                    "source_type": src["source_type"],
                    "employer_name": src["employer_name"],
                    "direction": direction,
                    "yoy_change_pct": float(pct) if pct is not None else None,
                    "year1_income": src["year1_income"],
                    "year2_income": src["year2_income"],
                    "underwriting_impact": (
                        "Must use lower of 2-year average or most recent year"
                        if direction == "DECLINING"
                        else "Standard calculation applies"
                    ),
                })

            if has_declining:
                overall_direction = "DECLINING"
            elif all(t["direction"] == "INCREASING" for t in trend_results):
                overall_direction = "INCREASING"
            elif any(t["direction"] == "VARIABLE" for t in trend_results):
                overall_direction = "VARIABLE"

            self.audit_log(
                "analyze_income_trend", "loan",
                entity_id=str(loan_id),
                details={"overall_direction": overall_direction},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "overall_direction": overall_direction,
                    "sources_analyzed": len(trend_results),
                    "has_declining_source": has_declining,
                    "trends": trend_results,
                    "guideline_note": (
                        "Per Fannie Mae B3-3.1, when income is declining, the lender must "
                        "use the lower of the 2-year average or the most recent year's income."
                    ),
                },
                message=f"Income trend: {overall_direction} across {len(trend_results)} source(s)",
            )

        except Exception as e:
            logger.exception(f"analyze_income_trend failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _detect_income_gaps(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Detect employment gaps in income history."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(db, loan_id, borrower_id)
            paystubs = [d for d in docs if d["doc_type"] == "PAYSTUB"]
            w2s = [d for d in docs if d["doc_type"] == "W2"]

            gaps: List[Dict] = []
            flags: List[str] = []

            # Check paystub recency
            if paystubs:
                paystubs_sorted = sorted(
                    paystubs,
                    key=lambda d: d["extracted_fields"].get("pay_date", "0000-00-00"),
                    reverse=True,
                )
                latest_pay_date_str = paystubs_sorted[0]["extracted_fields"].get("pay_date")
                if latest_pay_date_str:
                    try:
                        latest_pay_date = datetime.strptime(
                            str(latest_pay_date_str)[:10], "%Y-%m-%d"
                        ).date()
                        days_since = (date.today() - latest_pay_date).days
                        if days_since > PAYSTUB_STALENESS_DAYS:
                            gaps.append({
                                "type": "stale_paystub",
                                "description": f"Most recent paystub is {days_since} days old",
                                "last_pay_date": latest_pay_date_str,
                                "days_gap": days_since,
                                "severity": "high" if days_since > 60 else "medium",
                                "action_required": "Request current paystub or VOE",
                            })
                            flags.append(f"STALE_PAYSTUB: {days_since} days old")
                    except (ValueError, TypeError):
                        pass
            else:
                if w2s:
                    gaps.append({
                        "type": "no_current_employment",
                        "description": "W2s found but no paystubs -- cannot verify current employment",
                        "severity": "high",
                        "action_required": "Obtain current paystub or verbal VOE",
                    })
                    flags.append("NO_PAYSTUBS: W2 history exists but no current paystubs")

            # Check W2 year gaps
            if w2s:
                w2_years = set()
                for w2 in w2s:
                    ty = w2["extracted_fields"].get("tax_year")
                    if ty:
                        try:
                            w2_years.add(int(ty))
                        except (ValueError, TypeError):
                            pass

                if w2_years:
                    current_year = date.today().year
                    expected_years = set(range(current_year - 2, current_year))
                    missing_years = expected_years - w2_years

                    for missing_year in sorted(missing_years):
                        gaps.append({
                            "type": "missing_w2_year",
                            "description": f"No W2 found for tax year {missing_year}",
                            "missing_year": missing_year,
                            "severity": "high",
                            "action_required": f"Request {missing_year} W2 or tax return",
                        })
                        flags.append(f"MISSING_W2: Tax year {missing_year}")

            # Check for employer changes between W2s
            if len(w2s) >= 2:
                w2s_sorted = sorted(
                    w2s,
                    key=lambda d: d["extracted_fields"].get("tax_year", 0),
                    reverse=True,
                )
                employers = []
                for w2 in w2s_sorted[:3]:
                    emp = w2["extracted_fields"].get("employer_name", "").strip().lower()
                    year = w2["extracted_fields"].get("tax_year")
                    if emp:
                        employers.append({"employer": emp, "year": year})

                if len(set(e["employer"] for e in employers)) > 1:
                    gaps.append({
                        "type": "employer_change",
                        "description": "Multiple employers across W2 history",
                        "employers": [
                            {"name": e["employer"], "year": e["year"]} for e in employers
                        ],
                        "severity": "low",
                        "action_required": "Verify employment timeline and request LOE if gap >6 months",
                    })
                    flags.append("EMPLOYER_CHANGE: Multiple employers detected in W2 history")

            has_significant_gap = any(
                g["severity"] in ("high", "critical") for g in gaps
            )

            self.audit_log(
                "detect_income_gaps", "loan",
                entity_id=str(loan_id),
                details={"gap_count": len(gaps), "has_significant": has_significant_gap},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "gaps_detected": len(gaps),
                    "has_significant_gap": has_significant_gap,
                    "gaps": gaps,
                    "flags": flags,
                    "documents_analyzed": {
                        "paystubs": len(paystubs),
                        "w2s": len(w2s),
                    },
                    "guideline_note": (
                        "Per Fannie Mae B3-3.1-01, employment gaps >6 months within the "
                        "past 2 years require a Letter of Explanation (LOE)."
                    ),
                },
                message=(
                    f"Gap analysis: {len(gaps)} issue(s) detected"
                    f"{' (significant)' if has_significant_gap else ''}"
                ),
            )

        except Exception as e:
            logger.exception(f"detect_income_gaps failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _gross_up_nontaxable_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Apply non-taxable income gross-up per Fannie Mae B3-3.1-09."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        income_type = input_data["income_type"]
        monthly_amount = input_data["monthly_amount"]
        tax_rate = input_data.get("tax_rate")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            amount = self._to_decimal(monthly_amount)
            if amount <= ZERO:
                return ToolResult(
                    success=False,
                    error="Monthly amount must be greater than zero.",
                )

            eligible_types = [
                "social_security", "disability", "child_support",
                "military_allowance", "tax_exempt_interest",
            ]
            if income_type not in eligible_types:
                return ToolResult(
                    success=False,
                    error=f"Income type '{income_type}' is not eligible for gross-up. "
                          f"Eligible types: {', '.join(eligible_types)}",
                )

            if tax_rate is not None:
                rate = self._to_decimal(tax_rate)
                if rate <= ZERO or rate >= Decimal("1"):
                    return ToolResult(
                        success=False,
                        error="Tax rate must be between 0 and 1 (e.g., 0.25 for 25%)",
                    )
                gross_up_factor = Decimal("1") / (Decimal("1") - rate)
                method = f"actual_tax_rate_{float(rate)*100:.0f}pct"
            else:
                gross_up_factor = NONTAXABLE_GROSSUP_FACTOR
                method = "standard_25pct"

            grossed_up = (amount * gross_up_factor).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            increase = grossed_up - amount

            self.audit_log(
                "gross_up_nontaxable_income", "loan",
                entity_id=str(loan_id),
                details={
                    "income_type": income_type,
                    "original": float(amount),
                    "grossed_up": float(grossed_up),
                    "method": method,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "income_type": income_type,
                    "original_monthly": float(amount),
                    "grossed_up_monthly": float(grossed_up),
                    "increase_amount": float(increase),
                    "gross_up_factor": float(gross_up_factor),
                    "method": method,
                    "original_annual": float(amount * 12),
                    "grossed_up_annual": float(grossed_up * 12),
                    "guideline_reference": "Fannie Mae B3-3.1-09 (Non-Taxable Income Gross-Up)",
                },
                message=(
                    f"Gross-up: ${float(amount):,.2f} -> ${float(grossed_up):,.2f}/mo "
                    f"(+${float(increase):,.2f}, factor {float(gross_up_factor):.4f})"
                ),
            )

        except Exception as e:
            logger.exception(f"gross_up_nontaxable_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_income_to_stated(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Compare calculated income to application stated income."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        stated_override = input_data.get("stated_monthly_income")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            calc = self._get_latest_calculation(db, loan_id, borrower_id)
            if not calc or calc["total_qualifying_monthly"] <= 0:
                return ToolResult(
                    success=False,
                    error="No qualifying income calculated. Run aggregate_total_qualifying_income first.",
                )

            calculated_monthly = self._to_decimal(calc["total_qualifying_monthly"])

            stated_monthly = self._to_decimal(
                stated_override if stated_override is not None
                else getattr(loan, "borrower_stated_income", None)
            )

            if stated_monthly <= ZERO:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "status": "no_stated_income",
                        "calculated_monthly": float(calculated_monthly),
                        "message": "No stated income available on application for comparison.",
                    },
                    message="No stated income available for comparison",
                )

            variance = calculated_monthly - stated_monthly
            if stated_monthly > ZERO:
                variance_pct = (variance / stated_monthly * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                variance_pct = ZERO

            flags: List[str] = []
            if abs(variance_pct) > Decimal("25"):
                flags.append(
                    f"MATERIAL_INCOME_VARIANCE: Calculated income differs from stated by {variance_pct}%"
                )
                severity = "critical"
            elif abs(variance_pct) > Decimal("10"):
                flags.append(
                    f"INCOME_VARIANCE: Calculated income differs from stated by {variance_pct}%"
                )
                severity = "high"
            elif abs(variance_pct) > Decimal("5"):
                severity = "medium"
            else:
                severity = "low"

            assessment = "matches" if severity == "low" else "review_needed"
            if variance < ZERO:
                direction = "calculated_lower"
                impact = "Qualification may be affected -- calculated income is lower than stated"
            elif variance > ZERO:
                direction = "calculated_higher"
                impact = "Favorable -- calculated income exceeds stated amount"
            else:
                direction = "exact_match"
                impact = "Exact match between stated and calculated income"

            self.audit_log(
                "compare_income_to_stated", "loan",
                entity_id=str(loan_id),
                details={
                    "variance_pct": float(variance_pct),
                    "severity": severity,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "stated_monthly": float(stated_monthly),
                    "calculated_monthly": float(calculated_monthly),
                    "variance_monthly": float(variance),
                    "variance_pct": float(variance_pct),
                    "direction": direction,
                    "severity": severity,
                    "assessment": assessment,
                    "impact": impact,
                    "flags": flags,
                },
                message=(
                    f"Income comparison: stated ${float(stated_monthly):,.2f} vs "
                    f"calculated ${float(calculated_monthly):,.2f} "
                    f"({'+' if variance_pct > 0 else ''}{float(variance_pct)}%)"
                ),
            )

        except Exception as e:
            logger.exception(f"compare_income_to_stated failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_income_findings(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate findings and tasks for underwriter review."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            calc = self._get_latest_calculation(db, loan_id, borrower_id)
            if not calc:
                return ToolResult(
                    success=False,
                    error="No income calculation found. Run aggregate_total_qualifying_income first.",
                )

            # Get existing verification tasks
            existing_tasks = db.execute(
                text("""
                    SELECT id, task_type, title, status, priority
                    FROM income_verification_tasks
                    WHERE loan_id = :loan_id AND status NOT IN ('completed', 'cancelled')
                    ORDER BY
                        CASE priority
                            WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                            WHEN 'medium' THEN 3 ELSE 4
                        END
                """),
                {"loan_id": loan_id},
            ).fetchall()

            tasks = []
            for t in existing_tasks:
                tasks.append({
                    "task_id": t.id,
                    "task_type": t.task_type,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                })

            # Generate additional findings from flags
            findings: List[Dict] = []
            for flag in calc.get("flags", []):
                severity = "medium"
                if any(kw in flag for kw in ["DECLINING", "HIGH_DTI", "NEGATIVE"]):
                    severity = "high"
                elif any(kw in flag for kw in ["STALE", "MISMATCH", "INSUFFICIENT"]):
                    severity = "medium"
                elif "GAP" in flag:
                    severity = "high"

                finding_type = flag.split(":")[0] if ":" in flag else flag
                findings.append({
                    "flag": flag,
                    "type": finding_type,
                    "severity": severity,
                    "requires_action": severity in ("high", "critical"),
                })

            # Build recommendations
            recommendations = calc.get("recommendations", [])

            self.audit_log(
                "generate_income_findings", "loan",
                entity_id=str(loan_id),
                details={
                    "finding_count": len(findings),
                    "task_count": len(tasks),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "calculation_id": calc["calculation_id"],
                    "total_qualifying_monthly": calc["total_qualifying_monthly"],
                    "findings": findings,
                    "findings_count": len(findings),
                    "high_severity_count": len([f for f in findings if f["severity"] in ("high", "critical")]),
                    "verification_tasks": tasks,
                    "task_count": len(tasks),
                    "recommendations": recommendations,
                    "overall_status": (
                        "needs_review" if findings else "clean"
                    ),
                },
                message=(
                    f"Findings: {len(findings)} issues, {len(tasks)} verification tasks "
                    f"({len([f for f in findings if f['severity'] in ('high', 'critical')])} high severity)"
                ),
            )

        except Exception as e:
            logger.exception(f"generate_income_findings failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_income_documentation_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check if all required income documents are present."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = self._gather_income_docs(db, loan_id, borrower_id)

            doc_types_present = {}
            for d in docs:
                dt = d["doc_type"]
                if dt not in doc_types_present:
                    doc_types_present[dt] = []
                doc_types_present[dt].append({
                    "doc_id": d["doc_id"],
                    "file_name": d["file_name"],
                    "uploaded_at": d["uploaded_at"].isoformat() if d["uploaded_at"] else None,
                    "confidence": d["overall_confidence"],
                })

            current_year = date.today().year
            required_docs = {
                "PAYSTUB": {
                    "description": "Most recent paystub (within 30 days)",
                    "required": True,
                    "freshness_days": 30,
                },
                "W2": {
                    "description": f"W2s for {current_year - 1} and {current_year - 2}",
                    "required": True,
                    "count_needed": 2,
                },
            }

            # Check if self-employed (any SE docs present or loan metadata)
            has_se_docs = any(
                d["doc_type"] in ("TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS")
                for d in docs
            )
            if has_se_docs:
                required_docs["TAX_RETURN"] = {
                    "description": f"Personal tax returns for {current_year - 1} and {current_year - 2}",
                    "required": True,
                    "count_needed": 2,
                }
                required_docs["BUSINESS_TAX_RETURN"] = {
                    "description": f"Business tax returns for {current_year - 1} and {current_year - 2}",
                    "required": True,
                    "count_needed": 2,
                }

            checklist: List[Dict] = []
            total_required = 0
            total_satisfied = 0

            for doc_type, req in required_docs.items():
                present = doc_types_present.get(doc_type, [])
                count_needed = req.get("count_needed", 1)
                is_satisfied = len(present) >= count_needed

                # Freshness check for paystubs
                if doc_type == "PAYSTUB" and present:
                    freshness_days = req.get("freshness_days")
                    if freshness_days:
                        latest = present[0]
                        if latest["uploaded_at"]:
                            try:
                                uploaded = datetime.fromisoformat(latest["uploaded_at"])
                                if (datetime.now() - uploaded).days > freshness_days:
                                    is_satisfied = False
                            except (ValueError, TypeError):
                                pass

                total_required += 1
                if is_satisfied:
                    total_satisfied += 1

                checklist.append({
                    "doc_type": doc_type,
                    "description": req["description"],
                    "required": req["required"],
                    "count_needed": count_needed,
                    "count_present": len(present),
                    "is_satisfied": is_satisfied,
                    "documents": present,
                })

            completeness_pct = round(
                (total_satisfied / total_required) * 100, 1
            ) if total_required > 0 else 0

            missing = [c for c in checklist if not c["is_satisfied"] and c["required"]]

            self.audit_log(
                "get_income_documentation_status", "loan",
                entity_id=str(loan_id),
                details={
                    "completeness_pct": completeness_pct,
                    "missing_count": len(missing),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "completeness_pct": completeness_pct,
                    "total_required": total_required,
                    "total_satisfied": total_satisfied,
                    "missing_count": len(missing),
                    "missing_documents": [
                        {"doc_type": m["doc_type"], "description": m["description"]}
                        for m in missing
                    ],
                    "checklist": checklist,
                    "is_complete": len(missing) == 0,
                },
                message=(
                    f"Income docs: {completeness_pct}% complete "
                    f"({total_satisfied}/{total_required}, {len(missing)} missing)"
                ),
            )

        except Exception as e:
            logger.exception(f"get_income_documentation_status failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_income_approach(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Recommend the best income calculation approach."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        loan_program = input_data.get("loan_program")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            if not loan_program:
                loan_program = (loan.loan_type or "conventional").lower()

            docs = self._gather_income_docs(db, loan_id, borrower_id)

            has_paystubs = any(d["doc_type"] == "PAYSTUB" for d in docs)
            has_w2s = any(d["doc_type"] == "W2" for d in docs)
            has_tax_returns = any(d["doc_type"] == "TAX_RETURN" for d in docs)
            has_biz_tax = any(d["doc_type"] == "BUSINESS_TAX_RETURN" for d in docs)
            has_pnl = any(d["doc_type"] == "PROFIT_LOSS" for d in docs)

            is_self_employed = has_biz_tax or has_pnl
            has_commission = False
            if has_paystubs:
                for d in docs:
                    if d["doc_type"] == "PAYSTUB":
                        ytd_comm = self._to_decimal(
                            d["extracted_fields"].get("ytd_commission")
                        )
                        ytd_gross = self._to_decimal(
                            d["extracted_fields"].get("ytd_gross")
                        )
                        if ytd_comm > ZERO and ytd_gross > ZERO:
                            ratio = ytd_comm / ytd_gross * 100
                            if ratio >= Decimal("5"):
                                has_commission = True
                        break

            recommendations: List[Dict] = []

            if is_self_employed:
                recommendations.append({
                    "approach": "self_employment",
                    "priority": 1,
                    "description": (
                        "Self-employment income calculation using 2-year average from "
                        "Schedule C / K-1 with depreciation add-backs"
                    ),
                    "docs_available": {
                        "tax_returns": has_tax_returns,
                        "business_tax_returns": has_biz_tax,
                        "profit_loss": has_pnl,
                    },
                    "missing": (
                        [] if (has_tax_returns and has_biz_tax) else
                        (["2 years personal tax returns"] if not has_tax_returns else []) +
                        (["2 years business tax returns"] if not has_biz_tax else [])
                    ),
                    "guideline": "Fannie Mae B3-3.4",
                })

            if has_paystubs or has_w2s:
                recommendations.append({
                    "approach": "w2_salaried",
                    "priority": 2 if is_self_employed else 1,
                    "description": (
                        "W2/salaried income from paystubs (current) and W2s (historical)"
                    ),
                    "docs_available": {
                        "paystubs": has_paystubs,
                        "w2s": has_w2s,
                    },
                    "missing": (
                        (["Current paystub (within 30 days)"] if not has_paystubs else []) +
                        (["2 years of W2s"] if not has_w2s else [])
                    ),
                    "guideline": "Fannie Mae B3-3.1",
                })

            if has_commission:
                recommendations.append({
                    "approach": "commission",
                    "priority": 3,
                    "description": (
                        "Commission income analysis with 2-year trending (supplemental to W2)"
                    ),
                    "requires_2_year_history": True,
                    "guideline": "Fannie Mae B3-3.1-09",
                })

            if not recommendations:
                recommendations.append({
                    "approach": "upload_documents",
                    "priority": 1,
                    "description": (
                        "No income documents found. Upload paystubs, W2s, and/or tax returns "
                        "to begin income analysis."
                    ),
                    "suggested_docs": [
                        "Most recent 30-day paystub",
                        "2 most recent years W2",
                        "2 most recent years tax returns (if self-employed)",
                    ],
                })

            # Program-specific notes
            program_notes = {
                "conventional": "Standard Fannie Mae income guidelines apply.",
                "fha": "FHA allows 2-year average for variable income; back-end DTI limit 43%.",
                "va": "VA allows residual income analysis as alternative to DTI.",
                "usda": "USDA has household income limits -- verify total household income.",
                "jumbo": "Jumbo may require additional months of reserves and income documentation.",
                "non_qm": "Non-QM may accept bank statements (12-24 months) in lieu of tax returns.",
            }

            self.audit_log(
                "recommend_income_approach", "loan",
                entity_id=str(loan_id),
                details={
                    "recommended": recommendations[0]["approach"] if recommendations else "none",
                    "loan_program": loan_program,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "loan_program": loan_program,
                    "primary_recommendation": recommendations[0] if recommendations else None,
                    "all_recommendations": recommendations,
                    "borrower_profile": {
                        "is_self_employed": is_self_employed,
                        "has_commission": has_commission,
                        "docs_on_file": len(docs),
                    },
                    "program_note": program_notes.get(loan_program, "Standard guidelines apply."),
                },
                message=(
                    f"Recommended: {recommendations[0]['approach'] if recommendations else 'upload documents'} "
                    f"({loan_program.upper()} program)"
                ),
            )

        except Exception as e:
            logger.exception(f"recommend_income_approach failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_income_summary_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create formatted income summary report for the file."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = self._verify_loan_ownership(db, loan_id, org_id)
            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            calc = self._get_latest_calculation(db, loan_id, borrower_id)
            if not calc:
                return ToolResult(
                    success=False,
                    error="No income calculation found. Run aggregate_total_qualifying_income first.",
                )

            sources = self._get_income_sources(db, calc["calculation_id"])

            # Build summary sections
            source_summaries = []
            for src in sources:
                breakdown = {}
                if src["base_monthly"] > 0:
                    breakdown["base"] = f"${src['base_monthly']:,.2f}"
                if src["overtime_monthly"] > 0:
                    breakdown["overtime"] = f"${src['overtime_monthly']:,.2f}"
                if src["bonus_monthly"] > 0:
                    breakdown["bonus"] = f"${src['bonus_monthly']:,.2f}"
                if src["commission_monthly"] > 0:
                    breakdown["commission"] = f"${src['commission_monthly']:,.2f}"
                if src["other_monthly"] > 0:
                    breakdown["other"] = f"${src['other_monthly']:,.2f}"

                source_summaries.append({
                    "source_type": src["source_type"],
                    "employer": src["employer_name"] or "N/A",
                    "position": src["position_title"] or "N/A",
                    "monthly_income": f"${src['total_monthly']:,.2f}",
                    "annual_income": f"${src['total_annual']:,.2f}",
                    "breakdown": breakdown,
                    "trending": src["trending"] or "N/A",
                    "yoy_change": (
                        f"{src['yoy_change_pct']:+.1f}%"
                        if src["yoy_change_pct"] is not None else "N/A"
                    ),
                    "confidence": f"{src['confidence']}%",
                    "verification": src["verification_status"] or "unverified",
                })

            # DTI section
            dti_section = None
            if calc["dti_front_end"] is not None:
                dti_section = {
                    "front_end": f"{calc['dti_front_end']:.2f}%",
                    "back_end": f"{calc['dti_back_end']:.2f}%" if calc["dti_back_end"] else "N/A",
                }

            # Verification tasks
            tasks = db.execute(
                text("""
                    SELECT task_type, title, priority, status
                    FROM income_verification_tasks
                    WHERE loan_id = :loan_id AND status NOT IN ('completed', 'cancelled')
                    ORDER BY CASE priority
                        WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3 ELSE 4
                    END
                """),
                {"loan_id": loan_id},
            ).fetchall()

            open_tasks = [
                {"type": t.task_type, "title": t.title, "priority": t.priority, "status": t.status}
                for t in tasks
            ]

            report = {
                "header": {
                    "title": "Income Analysis Summary",
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "loan_type": loan.loan_type,
                    "report_date": date.today().isoformat(),
                    "calculation_date": calc.get("calculated_at"),
                },
                "totals": {
                    "total_qualifying_monthly": f"${calc['total_qualifying_monthly']:,.2f}",
                    "total_qualifying_annual": f"${calc['total_qualifying_annual']:,.2f}",
                    "calculation_method": calc["calculation_method"],
                    "confidence_score": f"{calc['confidence']}%",
                    "source_count": len(sources),
                },
                "income_sources": source_summaries,
                "dti_ratios": dti_section,
                "flags": calc.get("flags", []),
                "recommendations": calc.get("recommendations", []),
                "open_verification_tasks": open_tasks,
                "status": calc["status"],
            }

            self.audit_log(
                "create_income_summary_report", "loan",
                entity_id=str(loan_id),
                details={"source_count": len(sources)},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "report": report,
                },
                message=(
                    f"Income summary: ${calc['total_qualifying_monthly']:,.2f}/mo "
                    f"from {len(sources)} source(s), "
                    f"{len(calc.get('flags', []))} flags, "
                    f"{len(open_tasks)} open tasks"
                ),
            )

        except Exception as e:
            logger.exception(f"create_income_summary_report failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
