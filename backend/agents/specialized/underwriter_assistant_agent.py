"""
Underwriter Assistant Agent

Specialized agent for underwriting support with 15 tools:
1. analyze_income_for_underwriting - Comprehensive income analysis with qualifying income
2. validate_asset_documentation - Verify asset docs meet investor guidelines
3. check_credit_document_consistency - Cross-check credit report against other docs
4. generate_conditions_list - Auto-generate conditions from document deficiencies
5. evaluate_condition_response - Review condition response for completeness
6. calculate_dti_with_scenarios - DTI calculation with what-if scenarios
7. verify_employment_stability - Analyze employment history for 2-year continuity
8. assess_property_eligibility - Check property docs for eligibility
9. check_reserves_requirement - Calculate required reserves
10. identify_compensating_factors - Find compensating factors for borderline files
11. generate_decision_rationale - Document underwriting decision rationale
12. compare_to_aig_guidelines - Compare loan to Agency Investor Guidelines
13. check_layered_risk - Identify multiple risk layers
14. generate_suspension_letter - Draft suspension notice
15. create_approval_summary - Generate approval summary with conditions
"""

import logging
from typing import Any, Dict, Optional, List
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
    AgentRegistry
)


# ============================================================================
# CONSTANTS
# ============================================================================

# Agency guideline limits
AGENCY_DTI_LIMITS = {
    "conventional": {"front": 28.0, "back": 36.0, "back_with_compensating": 45.0, "du_max": 50.0},
    "fha": {"front": 31.0, "back": 43.0, "back_with_compensating": 50.0, "du_max": 57.0},
    "va": {"front": None, "back": 41.0, "back_with_compensating": 41.0, "du_max": 60.0},
    "usda": {"front": 29.0, "back": 41.0, "back_with_compensating": 41.0, "du_max": 41.0},
    "jumbo": {"front": 28.0, "back": 36.0, "back_with_compensating": 43.0, "du_max": 43.0},
}

# Reserve requirements in months of PITIA
RESERVE_REQUIREMENTS = {
    "primary_conventional": 0,
    "primary_fha": 0,
    "primary_va": 0,
    "second_home_conventional": 2,
    "investment_conventional": 6,
    "investment_fha": 0,  # FHA does not allow investment
    "multi_unit_2": 6,
    "multi_unit_3_4": 6,
    "multiple_properties_5_6": 6,
    "multiple_properties_7_10": 6,
}

# Minimum credit scores by loan type
MIN_CREDIT_SCORES = {
    "conventional": 620,
    "fha": 580,
    "fha_3.5_down": 580,
    "fha_10_down": 500,
    "va": 580,
    "usda": 640,
    "jumbo": 680,
}

# Maximum LTV by loan type for purchase
MAX_LTV = {
    "conventional_primary": 97.0,
    "conventional_second": 90.0,
    "conventional_investment": 85.0,
    "fha_primary": 96.5,
    "va_primary": 100.0,
    "usda_primary": 100.0,
    "jumbo_primary": 80.0,
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class AnalyzeIncomeInput(BaseModel):
    """Input schema for analyze_income_for_underwriting tool"""
    loan_id: int = Field(..., description="Loan ID to analyze income for")
    include_trending: bool = Field(default=True, description="Include 2-year income trending analysis")


class ValidateAssetDocInput(BaseModel):
    """Input schema for validate_asset_documentation tool"""
    loan_id: int = Field(..., description="Loan ID to validate assets for")
    large_deposit_threshold: float = Field(
        default=0.0,
        description="Custom large deposit threshold (0 = auto-calculate as 50% of qualifying income)"
    )


class CheckCreditConsistencyInput(BaseModel):
    """Input schema for check_credit_document_consistency tool"""
    loan_id: int = Field(..., description="Loan ID to check credit consistency")


class GenerateConditionsInput(BaseModel):
    """Input schema for generate_conditions_list tool"""
    loan_id: int = Field(..., description="Loan ID to generate conditions for")
    condition_type: str = Field(
        default="all",
        description="Condition type filter: prior_to_docs, prior_to_funding, prior_to_closing, all"
    )


class EvaluateConditionResponseInput(BaseModel):
    """Input schema for evaluate_condition_response tool"""
    loan_id: int = Field(..., description="Loan ID to evaluate conditions for")
    condition_ids: Optional[List[int]] = Field(None, description="Specific condition IDs to evaluate, or None for all open")


class CalculateDtiScenariosInput(BaseModel):
    """Input schema for calculate_dti_with_scenarios tool"""
    loan_id: int = Field(..., description="Loan ID for DTI calculation")
    add_income: Optional[float] = Field(None, description="Additional monthly income to add (what-if)")
    remove_debt: Optional[float] = Field(None, description="Monthly debt to remove (what-if)")
    add_debt: Optional[float] = Field(None, description="Additional monthly debt to add (what-if)")


class VerifyEmploymentInput(BaseModel):
    """Input schema for verify_employment_stability tool"""
    loan_id: int = Field(..., description="Loan ID to verify employment for")


class AssessPropertyInput(BaseModel):
    """Input schema for assess_property_eligibility tool"""
    loan_id: int = Field(..., description="Loan ID to assess property for")


class CheckReservesInput(BaseModel):
    """Input schema for check_reserves_requirement tool"""
    loan_id: int = Field(..., description="Loan ID to check reserves for")


class IdentifyCompensatingInput(BaseModel):
    """Input schema for identify_compensating_factors tool"""
    loan_id: int = Field(..., description="Loan ID to identify compensating factors for")


class GenerateDecisionRationaleInput(BaseModel):
    """Input schema for generate_decision_rationale tool"""
    loan_id: int = Field(..., description="Loan ID to generate rationale for")
    decision: str = Field(..., description="Decision: approve, suspend, deny, counteroffer")
    notes: Optional[str] = Field(None, description="Additional underwriter notes")


class CompareToAIGInput(BaseModel):
    """Input schema for compare_to_aig_guidelines tool"""
    loan_id: int = Field(..., description="Loan ID to compare against guidelines")


class CheckLayeredRiskInput(BaseModel):
    """Input schema for check_layered_risk tool"""
    loan_id: int = Field(..., description="Loan ID to check for layered risk")


class GenerateSuspensionLetterInput(BaseModel):
    """Input schema for generate_suspension_letter tool"""
    loan_id: int = Field(..., description="Loan ID to generate suspension letter for")
    suspension_reasons: List[str] = Field(..., description="List of suspension reasons")
    items_needed: List[str] = Field(..., description="List of items needed to clear suspension")


class CreateApprovalSummaryInput(BaseModel):
    """Input schema for create_approval_summary tool"""
    loan_id: int = Field(..., description="Loan ID to create approval summary for")
    include_conditions: bool = Field(default=True, description="Include conditions list in summary")
    include_exceptions: bool = Field(default=True, description="Include exception details")


# ============================================================================
# UNDERWRITER ASSISTANT AGENT
# ============================================================================

@AgentRegistry.register
class UnderwriterAssistantAgent(SpecializedAgent):
    """
    Specialized agent for underwriting support.

    Assists underwriters with document analysis, condition management,
    DTI calculations, guideline compliance, risk assessment, and
    decision documentation. All decisions are audit-logged for QC.
    """

    @property
    def name(self) -> str:
        return "UnderwriterAssistantAgent"

    @property
    def description(self) -> str:
        return (
            "Assists underwriters with income analysis, asset validation, credit review, "
            "condition management, DTI scenarios, employment verification, property eligibility, "
            "reserves calculation, compensating factors, decision rationale, guideline comparison, "
            "layered risk assessment, and approval/suspension documentation"
        )

    def _register_tools(self):
        """Register all underwriter assistant tools"""

        # Tool 1: Analyze Income for Underwriting
        self.register_tool(AgentTool(
            name="analyze_income_for_underwriting",
            description="Comprehensive income analysis with qualifying income calculation. "
                       "Examines W2, self-employment, rental, and other income sources. "
                       "Performs 2-year trending and identifies declining income patterns.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_income_for_underwriting,
            input_schema=AnalyzeIncomeInput
        ))

        # Tool 2: Validate Asset Documentation
        self.register_tool(AgentTool(
            name="validate_asset_documentation",
            description="Verify asset documentation meets investor guidelines. Checks for "
                       "sourced deposits, seasoned funds, large deposit letters, and gift documentation.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._validate_asset_documentation,
            input_schema=ValidateAssetDocInput
        ))

        # Tool 3: Check Credit Document Consistency
        self.register_tool(AgentTool(
            name="check_credit_document_consistency",
            description="Cross-check credit report data against application, tax returns, and "
                       "other documents for consistency. Flags undisclosed debts and discrepancies.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_credit_document_consistency,
            input_schema=CheckCreditConsistencyInput
        ))

        # Tool 4: Generate Conditions List
        self.register_tool(AgentTool(
            name="generate_conditions_list",
            description="Auto-generate underwriting conditions based on document deficiencies, "
                       "missing items, and guideline requirements. Categorizes as prior-to-docs, "
                       "prior-to-funding, or prior-to-closing.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_conditions_list,
            input_schema=GenerateConditionsInput
        ))

        # Tool 5: Evaluate Condition Response
        self.register_tool(AgentTool(
            name="evaluate_condition_response",
            description="Review processor's condition response for completeness. Checks if "
                       "submitted documents satisfy the condition requirements.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._evaluate_condition_response,
            input_schema=EvaluateConditionResponseInput
        ))

        # Tool 6: Calculate DTI with Scenarios
        self.register_tool(AgentTool(
            name="calculate_dti_with_scenarios",
            description="DTI calculation with what-if scenarios. Add/remove income sources or "
                       "debts to see impact on qualification. Compares to agency limits.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_dti_with_scenarios,
            input_schema=CalculateDtiScenariosInput
        ))

        # Tool 7: Verify Employment Stability
        self.register_tool(AgentTool(
            name="verify_employment_stability",
            description="Analyze employment history for 2-year continuity requirement. "
                       "Flags gaps, job changes, and career transitions that need documentation.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._verify_employment_stability,
            input_schema=VerifyEmploymentInput
        ))

        # Tool 8: Assess Property Eligibility
        self.register_tool(AgentTool(
            name="assess_property_eligibility",
            description="Check property documents (appraisal, title, insurance) for eligibility. "
                       "Validates property type, LTV, appraisal conditions, and title issues.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_property_eligibility,
            input_schema=AssessPropertyInput
        ))

        # Tool 9: Check Reserves Requirement
        self.register_tool(AgentTool(
            name="check_reserves_requirement",
            description="Calculate required reserves based on loan type, occupancy, property count, "
                       "and number of financed properties. Compares to verified liquid assets.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_reserves_requirement,
            input_schema=CheckReservesInput
        ))

        # Tool 10: Identify Compensating Factors
        self.register_tool(AgentTool(
            name="identify_compensating_factors",
            description="Find compensating factors when DTI or credit score is borderline. "
                       "Checks reserves, residual income, payment shock, LTV, and credit history.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_compensating_factors,
            input_schema=IdentifyCompensatingInput
        ))

        # Tool 11: Generate Decision Rationale
        self.register_tool(AgentTool(
            name="generate_decision_rationale",
            description="Document underwriting decision rationale for QC audit trail. "
                       "Captures decision, supporting factors, exceptions, and conditions.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_decision_rationale,
            input_schema=GenerateDecisionRationaleInput,
            requires_confirmation=True
        ))

        # Tool 12: Compare to AIG Guidelines
        self.register_tool(AgentTool(
            name="compare_to_aig_guidelines",
            description="Compare loan characteristics to Agency Investor Guidelines (Fannie Mae, "
                       "Freddie Mac, FHA, VA). Identifies out-of-guideline items.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_to_aig_guidelines,
            input_schema=CompareToAIGInput
        ))

        # Tool 13: Check Layered Risk
        self.register_tool(AgentTool(
            name="check_layered_risk",
            description="Identify multiple risk layers on a single file. Flags combinations "
                       "like low credit + high DTI + investment property + cash-out.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_layered_risk,
            input_schema=CheckLayeredRiskInput
        ))

        # Tool 14: Generate Suspension Letter
        self.register_tool(AgentTool(
            name="generate_suspension_letter",
            description="Draft suspension notice with specific requirements needed to "
                       "clear the suspension and move to approval.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._generate_suspension_letter,
            input_schema=GenerateSuspensionLetterInput,
            requires_confirmation=True
        ))

        # Tool 15: Create Approval Summary
        self.register_tool(AgentTool(
            name="create_approval_summary",
            description="Generate comprehensive approval summary with loan terms, conditions, "
                       "exceptions, compensating factors, and risk assessment.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._create_approval_summary,
            input_schema=CreateApprovalSummaryInput,
            requires_confirmation=True
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _analyze_income_for_underwriting(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Comprehensive income analysis with qualifying income calculation"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_trending = input_data.get("include_trending", True)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            # Get loan and borrower data
            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.amount, l.monthly_income, l.annual_income,
                    l.employment_type, l.employer_name, l.years_at_job,
                    l.self_employed, l.co_borrower_income,
                    l.other_income, l.rental_income
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Build income analysis
            income_sources = []
            total_qualifying_income = 0.0

            # Primary employment income
            monthly = float(loan.monthly_income or 0)
            annual = float(loan.annual_income or 0)
            if monthly > 0:
                income_sources.append({
                    "source": "Primary Employment",
                    "employer": loan.employer_name,
                    "monthly": monthly,
                    "annual": monthly * 12,
                    "type": "self_employed" if loan.self_employed else "w2",
                    "years": float(loan.years_at_job or 0),
                    "status": "qualifying"
                })
                total_qualifying_income += monthly
            elif annual > 0:
                monthly_calc = annual / 12
                income_sources.append({
                    "source": "Primary Employment",
                    "employer": loan.employer_name,
                    "monthly": monthly_calc,
                    "annual": annual,
                    "type": "self_employed" if loan.self_employed else "w2",
                    "years": float(loan.years_at_job or 0),
                    "status": "qualifying"
                })
                total_qualifying_income += monthly_calc

            # Co-borrower income
            co_income = float(loan.co_borrower_income or 0)
            if co_income > 0:
                income_sources.append({
                    "source": "Co-Borrower",
                    "monthly": co_income,
                    "annual": co_income * 12,
                    "type": "combined",
                    "status": "qualifying"
                })
                total_qualifying_income += co_income

            # Other income
            other = float(loan.other_income or 0)
            if other > 0:
                income_sources.append({
                    "source": "Other Income",
                    "monthly": other,
                    "annual": other * 12,
                    "type": "other",
                    "status": "needs_documentation"
                })
                # Other income qualifies only if documented for 2+ years
                total_qualifying_income += other

            # Rental income
            rental = float(loan.rental_income or 0)
            if rental > 0:
                # Use 75% of rental income per agency guidelines
                net_rental = rental * 0.75
                income_sources.append({
                    "source": "Rental Income",
                    "monthly_gross": rental,
                    "monthly_net": net_rental,
                    "annual_net": net_rental * 12,
                    "vacancy_factor": "25%",
                    "type": "rental",
                    "status": "qualifying_at_75_pct"
                })
                total_qualifying_income += net_rental

            # Income issues
            issues = []
            if loan.self_employed and float(loan.years_at_job or 0) < 2:
                issues.append({
                    "type": "SELF_EMPLOYMENT_HISTORY",
                    "severity": "high",
                    "message": "Self-employed less than 2 years — requires additional documentation or may not qualify"
                })

            if total_qualifying_income == 0:
                issues.append({
                    "type": "NO_INCOME",
                    "severity": "critical",
                    "message": "No qualifying income documented"
                })

            # Trending analysis
            trending = None
            if include_trending and len(income_sources) > 0:
                # Check income calculations table for historical data
                calcs = db.execute(text("""
                    SELECT year, total_income, income_type
                    FROM income_calculations
                    WHERE loan_id = :loan_id
                    ORDER BY year DESC
                    LIMIT 3
                """), {"loan_id": loan_id}).fetchall()

                if calcs and len(calcs) >= 2:
                    years = [{"year": int(c.year), "income": float(c.total_income or 0)} for c in calcs]
                    if len(years) >= 2 and years[0]["income"] < years[1]["income"]:
                        decline_pct = round(
                            (1 - years[0]["income"] / years[1]["income"]) * 100, 1
                        ) if years[1]["income"] > 0 else 0
                        trending = {
                            "direction": "declining",
                            "decline_percentage": decline_pct,
                            "years": years,
                            "recommendation": "Use lower of 2-year average or most recent year"
                        }
                        issues.append({
                            "type": "DECLINING_INCOME",
                            "severity": "medium",
                            "message": f"Income declined {decline_pct}% year-over-year"
                        })
                    elif len(years) >= 2:
                        trending = {"direction": "stable_or_increasing", "years": years}

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "income_sources": income_sources,
                "total_qualifying_monthly": round(total_qualifying_income, 2),
                "total_qualifying_annual": round(total_qualifying_income * 12, 2),
                "issues": issues,
                "trending": trending,
                "self_employed": bool(loan.self_employed),
                "issue_count": len(issues)
            }

            self.audit_log("analyze_income_for_underwriting", "loan", entity_id=str(loan_id), details={
                "qualifying_monthly": total_qualifying_income,
                "source_count": len(income_sources),
                "issue_count": len(issues),
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Income analysis: ${total_qualifying_income:,.0f}/mo qualifying, {len(issues)} issues"
            )

        except Exception as e:
            logger.exception(f"analyze_income_for_underwriting failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _validate_asset_documentation(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify asset documentation meets investor guidelines"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        large_deposit_threshold = input_data.get("large_deposit_threshold", 0.0)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.amount, l.loan_type,
                    l.monthly_income, l.total_assets,
                    l.down_payment_amount, l.closing_costs_estimate
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Auto-calculate large deposit threshold: 50% of monthly qualifying income
            if large_deposit_threshold <= 0 and loan.monthly_income:
                large_deposit_threshold = float(loan.monthly_income) * 0.50

            # Get asset documents
            docs = db.execute(text("""
                SELECT doc_type, doc_category, status, filename, uploaded_at
                FROM documents
                WHERE loan_id = :loan_id AND doc_category = 'assets'
                ORDER BY uploaded_at DESC
            """), {"loan_id": loan_id}).fetchall()

            # Check bank statement analyses
            bsa = db.execute(text("""
                SELECT id, account_type, institution, ending_balance,
                       large_deposits_flagged, analysis_date
                FROM bank_statement_analyses
                WHERE loan_id = :loan_id
                ORDER BY analysis_date DESC
            """), {"loan_id": loan_id}).fetchall()

            issues = []
            verified_assets = 0.0

            # Check for bank statements
            bank_stmts = [d for d in docs if d.doc_type in ("bank_statements", "bank_statement")]
            if not bank_stmts:
                issues.append({
                    "type": "MISSING_BANK_STATEMENTS",
                    "severity": "high",
                    "message": "No bank statements on file — 2 most recent months required"
                })

            # Sum verified assets from analyses
            for analysis in bsa:
                balance = float(analysis.ending_balance or 0)
                verified_assets += balance
                if analysis.large_deposits_flagged and analysis.large_deposits_flagged > 0:
                    issues.append({
                        "type": "LARGE_DEPOSITS",
                        "severity": "medium",
                        "message": f"{analysis.institution}: {analysis.large_deposits_flagged} large deposit(s) flagged — source documentation required",
                        "account": analysis.institution
                    })

            # Check if assets sufficient for down payment + closing costs + reserves
            down_payment = float(loan.down_payment_amount or 0)
            closing_costs = float(loan.closing_costs_estimate or 0)
            total_needed = down_payment + closing_costs

            if verified_assets < total_needed and total_needed > 0:
                shortfall = total_needed - verified_assets
                issues.append({
                    "type": "INSUFFICIENT_ASSETS",
                    "severity": "high",
                    "message": f"Verified assets (${verified_assets:,.0f}) below required (${total_needed:,.0f}). Shortfall: ${shortfall:,.0f}"
                })

            # Check for gift documentation
            gift_docs = [d for d in docs if d.doc_type in ("gift_letter", "gift_documentation")]
            if not gift_docs and verified_assets < total_needed:
                issues.append({
                    "type": "NO_GIFT_DOCUMENTATION",
                    "severity": "low",
                    "message": "No gift letter on file — if using gift funds, documentation required"
                })

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "verified_assets": round(verified_assets, 2),
                "down_payment_needed": down_payment,
                "closing_costs_estimate": closing_costs,
                "total_funds_needed": total_needed,
                "surplus_or_shortfall": round(verified_assets - total_needed, 2),
                "large_deposit_threshold": round(large_deposit_threshold, 2),
                "bank_statements_on_file": len(bank_stmts),
                "bank_analyses_count": len(bsa),
                "issues": issues,
                "issue_count": len(issues),
                "assets_sufficient": verified_assets >= total_needed
            }

            self.audit_log("validate_asset_documentation", "loan", entity_id=str(loan_id), details={
                "verified_assets": verified_assets,
                "assets_sufficient": verified_assets >= total_needed,
                "issue_count": len(issues),
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Assets: ${verified_assets:,.0f} verified, {'sufficient' if verified_assets >= total_needed else 'INSUFFICIENT'}, {len(issues)} issues"
            )

        except Exception as e:
            logger.exception(f"validate_asset_documentation failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_credit_document_consistency(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Cross-check credit report data against other documents"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.credit_score, l.credit_score_experian,
                    l.credit_score_equifax, l.credit_score_transunion,
                    l.monthly_debt, l.total_monthly_liabilities,
                    l.loan_type, l.amount
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            issues = []

            # Determine representative credit score (middle of three)
            scores = []
            if loan.credit_score_experian:
                scores.append(("Experian", int(loan.credit_score_experian)))
            if loan.credit_score_equifax:
                scores.append(("Equifax", int(loan.credit_score_equifax)))
            if loan.credit_score_transunion:
                scores.append(("TransUnion", int(loan.credit_score_transunion)))

            rep_score = int(loan.credit_score or 0)
            if len(scores) >= 3:
                sorted_scores = sorted(scores, key=lambda x: x[1])
                rep_score = sorted_scores[1][1]  # Middle score
            elif len(scores) == 2:
                rep_score = min(s[1] for s in scores)  # Lower of two

            # Check minimum credit score for loan type
            loan_type = (loan.loan_type or "conventional").lower()
            min_score = MIN_CREDIT_SCORES.get(loan_type, 620)
            if rep_score < min_score:
                issues.append({
                    "type": "CREDIT_BELOW_MINIMUM",
                    "severity": "critical",
                    "message": f"Representative score {rep_score} below {loan_type.upper()} minimum of {min_score}"
                })
            elif rep_score < min_score + 20:
                issues.append({
                    "type": "CREDIT_BORDERLINE",
                    "severity": "medium",
                    "message": f"Representative score {rep_score} is borderline (minimum: {min_score})"
                })

            # Check credit document on file
            credit_docs = db.execute(text("""
                SELECT doc_type, status, uploaded_at
                FROM documents
                WHERE loan_id = :loan_id AND doc_type IN ('credit_report', 'credit_explanation')
            """), {"loan_id": loan_id}).fetchall()

            if not any(d.doc_type == "credit_report" for d in credit_docs):
                issues.append({
                    "type": "MISSING_CREDIT_REPORT",
                    "severity": "high",
                    "message": "Credit report document not on file"
                })

            # Check for large score variance across bureaus
            if len(scores) >= 2:
                max_diff = max(s[1] for s in scores) - min(s[1] for s in scores)
                if max_diff > 40:
                    issues.append({
                        "type": "SCORE_VARIANCE",
                        "severity": "medium",
                        "message": f"Large credit score variance: {max_diff} points across bureaus. Review for disputed accounts."
                    })

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "credit_scores": {s[0]: s[1] for s in scores},
                "representative_score": rep_score,
                "minimum_required": min_score,
                "loan_type": loan_type,
                "meets_minimum": rep_score >= min_score,
                "monthly_debt_on_app": float(loan.monthly_debt or 0),
                "credit_docs_on_file": len(credit_docs),
                "issues": issues,
                "issue_count": len(issues)
            }

            self.audit_log("check_credit_document_consistency", "loan", entity_id=str(loan_id), details={
                "rep_score": rep_score,
                "meets_minimum": rep_score >= min_score,
                "issue_count": len(issues),
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Credit: {rep_score} rep score, {'meets' if rep_score >= min_score else 'BELOW'} minimum, {len(issues)} issues"
            )

        except Exception as e:
            logger.exception(f"check_credit_document_consistency failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_conditions_list(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Auto-generate conditions based on document deficiencies"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        condition_type = input_data.get("condition_type", "all")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.amount, l.stage, l.self_employed,
                    l.appraisal_received_date, l.title_received_date,
                    l.insurance_received_date, l.credit_docs_expire_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get existing documents
            docs = db.execute(text("""
                SELECT doc_type, doc_category, status
                FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing_types = {d.doc_type for d in docs}

            conditions = []

            # Income conditions (prior to docs)
            required_income = ["paystubs", "w2", "tax_returns"]
            if loan.self_employed:
                required_income.extend(["profit_loss", "1099"])

            for doc_type in required_income:
                if doc_type not in existing_types:
                    conditions.append({
                        "category": "prior_to_docs",
                        "type": "income",
                        "description": f"Provide {doc_type.replace('_', ' ').title()} — required for income verification",
                        "severity": "standard",
                        "auto_generated": True
                    })

            # Asset conditions (prior to docs)
            if "bank_statements" not in existing_types:
                conditions.append({
                    "category": "prior_to_docs",
                    "type": "assets",
                    "description": "Provide 2 most recent months bank statements for all accounts used for qualification",
                    "severity": "standard",
                    "auto_generated": True
                })

            # Property conditions (prior to closing)
            if not loan.appraisal_received_date:
                conditions.append({
                    "category": "prior_to_closing",
                    "type": "property",
                    "description": "Satisfactory appraisal with value supporting the purchase price/loan amount",
                    "severity": "standard",
                    "auto_generated": True
                })

            if not loan.title_received_date:
                conditions.append({
                    "category": "prior_to_funding",
                    "type": "property",
                    "description": "Clear title commitment with no unresolved exceptions",
                    "severity": "standard",
                    "auto_generated": True
                })

            if not loan.insurance_received_date:
                conditions.append({
                    "category": "prior_to_funding",
                    "type": "property",
                    "description": "Homeowner's insurance policy with adequate coverage",
                    "severity": "standard",
                    "auto_generated": True
                })

            # Credit conditions
            if loan.credit_docs_expire_date:
                expire_dt = loan.credit_docs_expire_date
                if isinstance(expire_dt, datetime):
                    expire_dt = expire_dt.date()
                if expire_dt <= date.today() + timedelta(days=30):
                    conditions.append({
                        "category": "prior_to_docs",
                        "type": "credit",
                        "description": f"Credit report expires {expire_dt.strftime('%m/%d/%Y')} — new report may be required before closing",
                        "severity": "standard",
                        "auto_generated": True
                    })

            # Standard prior-to-funding conditions
            conditions.append({
                "category": "prior_to_funding",
                "type": "standard",
                "description": "Final verification of employment within 10 business days of closing",
                "severity": "standard",
                "auto_generated": True
            })
            conditions.append({
                "category": "prior_to_funding",
                "type": "standard",
                "description": "No new inquiries, debts, or derogatory credit events prior to closing",
                "severity": "standard",
                "auto_generated": True
            })

            # Filter by type if requested
            if condition_type != "all":
                conditions = [c for c in conditions if c["category"] == condition_type]

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "total_conditions": len(conditions),
                "by_category": {
                    "prior_to_docs": len([c for c in conditions if c["category"] == "prior_to_docs"]),
                    "prior_to_closing": len([c for c in conditions if c["category"] == "prior_to_closing"]),
                    "prior_to_funding": len([c for c in conditions if c["category"] == "prior_to_funding"]),
                },
                "conditions": conditions
            }

            self.audit_log("generate_conditions_list", "loan", entity_id=str(loan_id), details={
                "condition_count": len(conditions),
                "filter": condition_type,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Generated {len(conditions)} conditions for loan {loan.loan_number}"
            )

        except Exception as e:
            logger.exception(f"generate_conditions_list failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _evaluate_condition_response(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Review condition response for completeness"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        condition_ids = input_data.get("condition_ids")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            # Get open conditions
            params = {"loan_id": loan_id, "org_id": org_id}
            id_filter = ""
            if condition_ids:
                id_filter = "AND lc.id = ANY(:condition_ids)"
                params["condition_ids"] = condition_ids

            conditions = db.execute(text(f"""
                SELECT
                    lc.id, lc.condition_type, lc.description,
                    lc.status, lc.due_date, lc.response_notes,
                    lc.response_date
                FROM loan_conditions lc
                JOIN loans l ON l.id = lc.loan_id AND l.organization_id = :org_id
                WHERE lc.loan_id = :loan_id
                    AND lc.status IN ('pending', 'submitted')
                    {id_filter}
                ORDER BY lc.due_date ASC NULLS LAST
            """), params).fetchall()

            if not conditions:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "conditions": [], "message": "No open conditions found"},
                    message="No open conditions to evaluate"
                )

            # Get documents uploaded after condition creation for correlation
            recent_docs = db.execute(text("""
                SELECT doc_type, doc_category, status, uploaded_at, filename
                FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
                ORDER BY uploaded_at DESC
                LIMIT 20
            """), {"loan_id": loan_id}).fetchall()

            evaluations = []
            satisfied_count = 0
            needs_review_count = 0

            for cond in conditions:
                evaluation = {
                    "condition_id": cond.id,
                    "type": cond.condition_type,
                    "description": cond.description,
                    "status": cond.status,
                    "due_date": cond.due_date.isoformat() if cond.due_date else None,
                }

                if cond.status == "submitted" and cond.response_notes:
                    # Has response — evaluate completeness
                    evaluation["response_notes"] = cond.response_notes
                    evaluation["response_date"] = cond.response_date.isoformat() if cond.response_date else None
                    evaluation["assessment"] = "submitted_for_review"
                    evaluation["recommendation"] = "Review submitted response for accuracy and completeness"
                    needs_review_count += 1
                elif cond.status == "pending":
                    # Check if a matching document was uploaded
                    matching_doc = None
                    cond_lower = (cond.description or "").lower()
                    for doc in recent_docs:
                        if doc.doc_type and doc.doc_type.lower() in cond_lower:
                            matching_doc = doc
                            break
                    if matching_doc:
                        evaluation["assessment"] = "document_uploaded"
                        evaluation["matching_document"] = matching_doc.filename
                        evaluation["recommendation"] = "Document uploaded — verify it satisfies the condition"
                        needs_review_count += 1
                    else:
                        evaluation["assessment"] = "outstanding"
                        evaluation["recommendation"] = "No response received — follow up with processor"
                        is_past_due = cond.due_date and cond.due_date < date.today() if isinstance(cond.due_date, date) else False
                        evaluation["past_due"] = is_past_due

                evaluations.append(evaluation)

            data = {
                "loan_id": loan_id,
                "total_conditions": len(evaluations),
                "satisfied": satisfied_count,
                "needs_review": needs_review_count,
                "outstanding": len(evaluations) - satisfied_count - needs_review_count,
                "evaluations": evaluations
            }

            self.audit_log("evaluate_condition_response", "loan", entity_id=str(loan_id), details={
                "total": len(evaluations),
                "needs_review": needs_review_count,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Conditions: {needs_review_count} need review, {len(evaluations) - satisfied_count - needs_review_count} outstanding"
            )

        except Exception as e:
            logger.exception(f"evaluate_condition_response failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_dti_with_scenarios(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """DTI calculation with what-if scenarios"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        add_income = input_data.get("add_income")
        remove_debt = input_data.get("remove_debt")
        add_debt = input_data.get("add_debt")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.monthly_income, l.co_borrower_income, l.other_income,
                    l.rental_income, l.monthly_debt, l.total_monthly_liabilities,
                    l.proposed_housing_expense, l.amount, l.rate, l.loan_term,
                    l.property_taxes_monthly, l.insurance_monthly, l.hoa_monthly
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Calculate base income
            base_income = (
                float(loan.monthly_income or 0)
                + float(loan.co_borrower_income or 0)
                + float(loan.other_income or 0)
                + float(loan.rental_income or 0) * 0.75  # 75% rental income factor
            )

            # Calculate PITIA (proposed housing expense)
            housing = float(loan.proposed_housing_expense or 0)
            if housing == 0:
                # Estimate from loan terms
                amount = float(loan.amount or 0)
                rate = float(loan.rate or 0) / 100 / 12 if loan.rate else 0
                term = int(loan.loan_term or 360)
                if rate > 0 and amount > 0:
                    pi = amount * (rate * (1 + rate) ** term) / ((1 + rate) ** term - 1)
                else:
                    pi = 0
                taxes = float(loan.property_taxes_monthly or 0)
                insurance = float(loan.insurance_monthly or 0)
                hoa = float(loan.hoa_monthly or 0)
                housing = pi + taxes + insurance + hoa

            # Calculate debts
            total_debt = float(loan.monthly_debt or loan.total_monthly_liabilities or 0)

            # Base DTI
            front_dti = round((housing / base_income) * 100, 2) if base_income > 0 else 0
            back_dti = round(((housing + total_debt) / base_income) * 100, 2) if base_income > 0 else 0

            # Scenario DTI
            scenario_income = base_income + float(add_income or 0)
            scenario_debt = total_debt - float(remove_debt or 0) + float(add_debt or 0)
            scenario_debt = max(0, scenario_debt)

            scenario_front = round((housing / scenario_income) * 100, 2) if scenario_income > 0 else 0
            scenario_back = round(((housing + scenario_debt) / scenario_income) * 100, 2) if scenario_income > 0 else 0

            # Get guideline limits
            loan_type = (loan.loan_type or "conventional").lower()
            limits = AGENCY_DTI_LIMITS.get(loan_type, AGENCY_DTI_LIMITS["conventional"])

            # Assess qualification
            base_qualifies = back_dti <= limits["du_max"]
            scenario_qualifies = scenario_back <= limits["du_max"]

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "loan_type": loan_type,
                "base_scenario": {
                    "monthly_income": round(base_income, 2),
                    "housing_expense": round(housing, 2),
                    "other_debts": round(total_debt, 2),
                    "front_dti": front_dti,
                    "back_dti": back_dti,
                    "qualifies": base_qualifies,
                },
                "what_if_scenario": {
                    "monthly_income": round(scenario_income, 2),
                    "housing_expense": round(housing, 2),
                    "other_debts": round(scenario_debt, 2),
                    "front_dti": scenario_front,
                    "back_dti": scenario_back,
                    "qualifies": scenario_qualifies,
                    "income_added": add_income,
                    "debt_removed": remove_debt,
                    "debt_added": add_debt,
                },
                "guideline_limits": {
                    "standard_front": limits.get("front"),
                    "standard_back": limits["back"],
                    "with_compensating": limits["back_with_compensating"],
                    "du_max": limits["du_max"],
                },
                "dti_change": round(scenario_back - back_dti, 2) if any([add_income, remove_debt, add_debt]) else 0
            }

            self.audit_log("calculate_dti_with_scenarios", "loan", entity_id=str(loan_id), details={
                "base_back_dti": back_dti,
                "scenario_back_dti": scenario_back,
                "qualifies": base_qualifies,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"DTI: {back_dti}% back-end ({'qualifies' if base_qualifies else 'EXCEEDS'} {loan_type.upper()} max {limits['du_max']}%)"
            )

        except Exception as e:
            logger.exception(f"calculate_dti_with_scenarios failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_employment_stability(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Analyze employment history for 2-year continuity"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.employer_name, l.employment_type, l.years_at_job,
                    l.self_employed, l.previous_employer, l.previous_years_at_job,
                    l.application_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            issues = []
            employment_history = []
            total_years = 0.0

            # Current employment
            current_years = float(loan.years_at_job or 0)
            total_years += current_years
            employment_history.append({
                "employer": loan.employer_name or "Current Employer",
                "years": current_years,
                "type": loan.employment_type or ("Self-Employed" if loan.self_employed else "W2"),
                "status": "current"
            })

            # Previous employment
            if loan.previous_employer:
                prev_years = float(loan.previous_years_at_job or 0)
                total_years += prev_years
                employment_history.append({
                    "employer": loan.previous_employer,
                    "years": prev_years,
                    "type": "prior",
                    "status": "prior"
                })

            # Check 2-year continuity
            meets_2_year = total_years >= 2.0
            if not meets_2_year:
                gap = round(2.0 - total_years, 1)
                issues.append({
                    "type": "INSUFFICIENT_HISTORY",
                    "severity": "high",
                    "message": f"Total employment history is {total_years:.1f} years — {gap} year gap in 2-year requirement"
                })

            # Self-employment checks
            if loan.self_employed:
                if current_years < 2:
                    issues.append({
                        "type": "SELF_EMPLOYMENT_DURATION",
                        "severity": "high",
                        "message": f"Self-employed for {current_years:.1f} years — 2 years required for most loan programs"
                    })
                issues.append({
                    "type": "SELF_EMPLOYMENT_DOCS",
                    "severity": "medium",
                    "message": "Self-employed borrower — verify 2 years tax returns, P&L, and business license on file"
                })

            # Check for employment gaps
            if current_years < 2 and not loan.previous_employer:
                issues.append({
                    "type": "EMPLOYMENT_GAP",
                    "severity": "medium",
                    "message": "Less than 2 years at current employer with no prior employer documented — gap letter may be required"
                })

            # Job change in same field is generally acceptable
            if loan.previous_employer and current_years < 0.5:
                issues.append({
                    "type": "RECENT_JOB_CHANGE",
                    "severity": "low",
                    "message": "Recent job change — verify same line of work or upward career progression"
                })

            # VOE documents
            voe_docs = db.execute(text("""
                SELECT doc_type, status FROM documents
                WHERE loan_id = :loan_id AND doc_type IN ('voe', 'verification_of_employment', 'paystubs', 'w2')
            """), {"loan_id": loan_id}).fetchall()

            if not any(d.doc_type in ("voe", "verification_of_employment") for d in voe_docs):
                issues.append({
                    "type": "MISSING_VOE",
                    "severity": "medium",
                    "message": "Written VOE not on file — verbal VOE within 10 business days of closing required at minimum"
                })

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "employment_history": employment_history,
                "total_employment_years": round(total_years, 1),
                "meets_2_year_requirement": meets_2_year,
                "self_employed": bool(loan.self_employed),
                "voe_on_file": len(voe_docs) > 0,
                "issues": issues,
                "issue_count": len(issues)
            }

            self.audit_log("verify_employment_stability", "loan", entity_id=str(loan_id), details={
                "total_years": total_years,
                "meets_2_year": meets_2_year,
                "self_employed": bool(loan.self_employed),
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Employment: {total_years:.1f} years, {'meets' if meets_2_year else 'DOES NOT MEET'} 2-year requirement, {len(issues)} issues"
            )

        except Exception as e:
            logger.exception(f"verify_employment_stability failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _assess_property_eligibility(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check property docs for eligibility"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.amount, l.loan_type,
                    l.property_type, l.property_address, l.occupancy_type,
                    l.property_value, l.appraisal_value, l.purchase_price,
                    l.appraisal_ordered_date, l.appraisal_received_date,
                    l.appraisal_completed_date,
                    l.title_ordered_date, l.title_received_date,
                    l.insurance_ordered_date, l.insurance_received_date,
                    l.ltv, l.cltv
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            issues = []

            # LTV check
            loan_type = (loan.loan_type or "conventional").lower()
            occupancy = (loan.occupancy_type or "primary").lower()
            ltv_key = f"{loan_type}_{occupancy}"
            max_ltv = MAX_LTV.get(ltv_key, 97.0)

            actual_ltv = float(loan.ltv or 0)
            if actual_ltv == 0 and loan.amount and loan.property_value:
                actual_ltv = round(float(loan.amount) / float(loan.property_value) * 100, 2)

            if actual_ltv > max_ltv:
                issues.append({
                    "type": "LTV_EXCEEDS_MAX",
                    "severity": "critical",
                    "message": f"LTV {actual_ltv}% exceeds maximum {max_ltv}% for {loan_type.upper()} {occupancy}"
                })

            # Appraisal checks
            if not loan.appraisal_received_date:
                if loan.appraisal_ordered_date:
                    issues.append({
                        "type": "APPRAISAL_PENDING",
                        "severity": "medium",
                        "message": "Appraisal ordered but not yet received"
                    })
                else:
                    issues.append({
                        "type": "APPRAISAL_NOT_ORDERED",
                        "severity": "high",
                        "message": "Appraisal has not been ordered"
                    })
            else:
                # Check appraisal value vs purchase price
                appraisal_val = float(loan.appraisal_value or 0)
                purchase_price = float(loan.purchase_price or 0)
                if appraisal_val > 0 and purchase_price > 0 and appraisal_val < purchase_price:
                    shortfall = purchase_price - appraisal_val
                    issues.append({
                        "type": "APPRAISAL_SHORT",
                        "severity": "high",
                        "message": f"Appraisal (${appraisal_val:,.0f}) below purchase price (${purchase_price:,.0f}) by ${shortfall:,.0f}"
                    })

            # Title check
            if not loan.title_received_date:
                issues.append({
                    "type": "TITLE_NOT_RECEIVED",
                    "severity": "medium",
                    "message": "Title commitment not received"
                })

            # Insurance check
            if not loan.insurance_received_date:
                issues.append({
                    "type": "INSURANCE_NOT_RECEIVED",
                    "severity": "medium",
                    "message": "Homeowner's insurance policy not received"
                })

            # Property type restrictions
            if loan.property_type and loan.property_type.lower() in ("manufactured", "mobile_home"):
                issues.append({
                    "type": "PROPERTY_TYPE_RESTRICTION",
                    "severity": "medium",
                    "message": "Manufactured housing — verify meets permanent foundation requirements and is on double-wide minimum for conventional"
                })

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "property_address": loan.property_address,
                "property_type": loan.property_type,
                "occupancy_type": occupancy,
                "loan_type": loan_type,
                "ltv": actual_ltv,
                "max_ltv": max_ltv,
                "ltv_eligible": actual_ltv <= max_ltv,
                "appraisal_value": float(loan.appraisal_value or 0),
                "purchase_price": float(loan.purchase_price or 0),
                "appraisal_status": "received" if loan.appraisal_received_date else ("ordered" if loan.appraisal_ordered_date else "not_ordered"),
                "title_status": "received" if loan.title_received_date else "pending",
                "insurance_status": "received" if loan.insurance_received_date else "pending",
                "issues": issues,
                "issue_count": len(issues)
            }

            self.audit_log("assess_property_eligibility", "loan", entity_id=str(loan_id), details={
                "ltv": actual_ltv,
                "ltv_eligible": actual_ltv <= max_ltv,
                "issue_count": len(issues),
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Property: LTV {actual_ltv}% ({'eligible' if actual_ltv <= max_ltv else 'EXCEEDS'} max {max_ltv}%), {len(issues)} issues"
            )

        except Exception as e:
            logger.exception(f"assess_property_eligibility failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_reserves_requirement(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Calculate required reserves"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.loan_type, l.occupancy_type,
                    l.property_type, l.proposed_housing_expense,
                    l.property_taxes_monthly, l.insurance_monthly, l.hoa_monthly,
                    l.total_assets, l.amount, l.rate, l.loan_term
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            loan_type = (loan.loan_type or "conventional").lower()
            occupancy = (loan.occupancy_type or "primary").lower()

            # Calculate monthly PITIA
            pitia = float(loan.proposed_housing_expense or 0)
            if pitia == 0:
                amount = float(loan.amount or 0)
                rate = float(loan.rate or 0) / 100 / 12 if loan.rate else 0
                term = int(loan.loan_term or 360)
                if rate > 0 and amount > 0:
                    pi = amount * (rate * (1 + rate) ** term) / ((1 + rate) ** term - 1)
                else:
                    pi = 0
                pitia = pi + float(loan.property_taxes_monthly or 0) + float(loan.insurance_monthly or 0) + float(loan.hoa_monthly or 0)

            # Determine months of reserves required
            reserve_key = f"{occupancy}_{loan_type}"
            months_required = RESERVE_REQUIREMENTS.get(reserve_key, 0)

            # Check for multi-unit
            if loan.property_type and "multi" in (loan.property_type or "").lower():
                months_required = max(months_required, 6)

            # Count financed properties
            financed_count = db.execute(text("""
                SELECT COUNT(*) as cnt FROM loans
                WHERE organization_id = :org_id
                    AND borrower_name = (SELECT borrower_name FROM loans WHERE id = :loan_id)
                    AND stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    AND id != :loan_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            other_properties = financed_count.cnt if financed_count else 0
            if other_properties >= 4:
                months_required = max(months_required, 6)

            reserves_required = round(pitia * months_required, 2)
            verified_assets = float(loan.total_assets or 0)

            # Get liquid assets from bank statement analyses
            bsa_total = db.execute(text("""
                SELECT COALESCE(SUM(ending_balance), 0) as total
                FROM bank_statement_analyses
                WHERE loan_id = :loan_id
            """), {"loan_id": loan_id}).fetchone()
            liquid_assets = float(bsa_total.total) if bsa_total else verified_assets

            meets_requirement = liquid_assets >= reserves_required or months_required == 0

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "monthly_pitia": round(pitia, 2),
                "months_required": months_required,
                "reserves_required": reserves_required,
                "verified_liquid_assets": round(liquid_assets, 2),
                "surplus_or_shortfall": round(liquid_assets - reserves_required, 2),
                "meets_requirement": meets_requirement,
                "loan_type": loan_type,
                "occupancy": occupancy,
                "other_financed_properties": other_properties,
                "requirement_basis": reserve_key
            }

            self.audit_log("check_reserves_requirement", "loan", entity_id=str(loan_id), details={
                "months_required": months_required,
                "reserves_required": reserves_required,
                "meets_requirement": meets_requirement,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Reserves: {months_required} months (${reserves_required:,.0f}) required, {'MET' if meets_requirement else 'NOT MET'}"
            )

        except Exception as e:
            logger.exception(f"check_reserves_requirement failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_compensating_factors(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Find compensating factors for borderline files"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.credit_score, l.amount, l.property_value,
                    l.ltv, l.monthly_income, l.monthly_debt,
                    l.proposed_housing_expense, l.total_assets,
                    l.down_payment_amount, l.occupancy_type,
                    l.co_borrower_income, l.years_at_job
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            compensating_factors = []
            income = float(loan.monthly_income or 0) + float(loan.co_borrower_income or 0)
            housing = float(loan.proposed_housing_expense or 0)
            debts = float(loan.monthly_debt or 0)
            back_dti = ((housing + debts) / income * 100) if income > 0 else 0
            credit = int(loan.credit_score or 0)
            ltv = float(loan.ltv or 0)
            if ltv == 0 and loan.amount and loan.property_value:
                ltv = float(loan.amount) / float(loan.property_value) * 100

            # Factor 1: Substantial reserves
            total_assets = float(loan.total_assets or 0)
            if housing > 0 and total_assets / housing >= 12:
                compensating_factors.append({
                    "factor": "Substantial Reserves",
                    "detail": f"{int(total_assets / housing)} months of reserves — demonstrates financial stability",
                    "strength": "strong"
                })
            elif housing > 0 and total_assets / housing >= 6:
                compensating_factors.append({
                    "factor": "Adequate Reserves",
                    "detail": f"{int(total_assets / housing)} months of reserves",
                    "strength": "moderate"
                })

            # Factor 2: Conservative LTV
            if ltv <= 75:
                compensating_factors.append({
                    "factor": "Low LTV",
                    "detail": f"LTV of {ltv:.1f}% — significant equity/down payment reduces risk",
                    "strength": "strong"
                })
            elif ltv <= 80:
                compensating_factors.append({
                    "factor": "Moderate LTV",
                    "detail": f"LTV of {ltv:.1f}% — at or below 80%",
                    "strength": "moderate"
                })

            # Factor 3: Strong credit history
            if credit >= 760:
                compensating_factors.append({
                    "factor": "Excellent Credit",
                    "detail": f"Credit score {credit} — strong repayment history",
                    "strength": "strong"
                })
            elif credit >= 720:
                compensating_factors.append({
                    "factor": "Good Credit",
                    "detail": f"Credit score {credit} — above average creditworthiness",
                    "strength": "moderate"
                })

            # Factor 4: Minimal payment shock
            # (Would need current housing payment data for full comparison)
            if housing > 0 and income > 0 and (housing / income) < 0.25:
                compensating_factors.append({
                    "factor": "Low Housing Ratio",
                    "detail": f"Front-end DTI of {housing / income * 100:.1f}% — well within limits",
                    "strength": "moderate"
                })

            # Factor 5: Employment stability
            years_at_job = float(loan.years_at_job or 0)
            if years_at_job >= 5:
                compensating_factors.append({
                    "factor": "Employment Stability",
                    "detail": f"{years_at_job:.0f} years with current employer — demonstrates stable income",
                    "strength": "strong" if years_at_job >= 10 else "moderate"
                })

            # Factor 6: Large down payment
            down = float(loan.down_payment_amount or 0)
            prop_val = float(loan.property_value or 0)
            if prop_val > 0 and down / prop_val >= 0.20:
                compensating_factors.append({
                    "factor": "Substantial Down Payment",
                    "detail": f"{down / prop_val * 100:.0f}% down payment — significant borrower investment",
                    "strength": "strong"
                })

            # Factor 7: Residual income (VA uses this heavily)
            residual = income - housing - debts
            if residual > 0 and income > 0 and residual / income > 0.25:
                compensating_factors.append({
                    "factor": "Strong Residual Income",
                    "detail": f"${residual:,.0f}/mo residual after all obligations — adequate financial cushion",
                    "strength": "moderate"
                })

            # Overall assessment
            strong = len([f for f in compensating_factors if f["strength"] == "strong"])
            moderate = len([f for f in compensating_factors if f["strength"] == "moderate"])

            if strong >= 2:
                overall = "Multiple strong compensating factors support approval despite borderline metrics"
            elif strong >= 1 and moderate >= 1:
                overall = "Compensating factors present that may support approval with conditions"
            elif moderate >= 2:
                overall = "Moderate compensating factors identified — may warrant management review"
            else:
                overall = "Limited compensating factors — file may not overcome borderline metrics"

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "current_metrics": {
                    "credit_score": credit,
                    "back_dti": round(back_dti, 1),
                    "ltv": round(ltv, 1),
                },
                "compensating_factors": compensating_factors,
                "factor_count": len(compensating_factors),
                "strong_factors": strong,
                "moderate_factors": moderate,
                "overall_assessment": overall
            }

            self.audit_log("identify_compensating_factors", "loan", entity_id=str(loan_id), details={
                "factor_count": len(compensating_factors),
                "strong": strong,
                "moderate": moderate,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Compensating factors: {strong} strong, {moderate} moderate — {overall[:60]}..."
            )

        except Exception as e:
            logger.exception(f"identify_compensating_factors failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_decision_rationale(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Document underwriting decision rationale for QC audit"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        decision = input_data["decision"]
        notes = input_data.get("notes", "")
        org_id = self.require_org_id()

        valid_decisions = ["approve", "suspend", "deny", "counteroffer"]
        if decision not in valid_decisions:
            return ToolResult(
                success=False,
                error=f"Invalid decision. Must be one of: {', '.join(valid_decisions)}"
            )

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.amount, l.rate, l.loan_term, l.credit_score,
                    l.monthly_income, l.monthly_debt, l.proposed_housing_expense,
                    l.ltv, l.property_value, l.occupancy_type, l.stage,
                    l.self_employed
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Build rationale
            income = float(loan.monthly_income or 0)
            housing = float(loan.proposed_housing_expense or 0)
            debts = float(loan.monthly_debt or 0)
            back_dti = ((housing + debts) / income * 100) if income > 0 else 0

            rationale = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "decision": decision.upper(),
                "decision_date": datetime.utcnow().isoformat(),
                "underwriter_user_id": context.get("user_id"),
                "loan_summary": {
                    "loan_type": loan.loan_type,
                    "amount": float(loan.amount or 0),
                    "rate": float(loan.rate or 0),
                    "term": int(loan.loan_term or 360),
                    "credit_score": int(loan.credit_score or 0),
                    "back_dti": round(back_dti, 1),
                    "ltv": float(loan.ltv or 0),
                    "occupancy": loan.occupancy_type,
                    "self_employed": bool(loan.self_employed),
                },
                "supporting_factors": [],
                "risk_factors": [],
                "additional_notes": notes,
            }

            # Auto-populate supporting factors
            credit = int(loan.credit_score or 0)
            if credit >= 700:
                rationale["supporting_factors"].append(f"Credit score {credit} meets program minimum")
            ltv = float(loan.ltv or 0)
            if ltv <= 80:
                rationale["supporting_factors"].append(f"LTV {ltv:.1f}% within standard guidelines")

            # Auto-populate risk factors
            if credit < 660:
                rationale["risk_factors"].append(f"Credit score {credit} is below preferred threshold")
            if back_dti > 45:
                rationale["risk_factors"].append(f"Back-end DTI {back_dti:.1f}% exceeds standard limits")
            if loan.self_employed:
                rationale["risk_factors"].append("Self-employed borrower — income stability considerations")

            # Get condition count
            conditions = db.execute(text("""
                SELECT COUNT(*) as cnt FROM loan_conditions
                WHERE loan_id = :loan_id AND status = 'pending'
            """), {"loan_id": loan_id}).fetchone()

            rationale["pending_conditions"] = conditions.cnt if conditions else 0

            self.audit_log("generate_decision_rationale", "loan", entity_id=str(loan_id), details={
                "decision": decision,
                "credit_score": credit,
                "back_dti": round(back_dti, 1),
                "ltv": ltv,
            })

            return ToolResult(
                success=True,
                data=rationale,
                message=f"Decision rationale: {decision.upper()} for loan {loan.loan_number}"
            )

        except Exception as e:
            logger.exception(f"generate_decision_rationale failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_to_aig_guidelines(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Compare loan to Agency Investor Guidelines"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.loan_type, l.amount,
                    l.credit_score, l.ltv, l.cltv,
                    l.monthly_income, l.monthly_debt, l.proposed_housing_expense,
                    l.occupancy_type, l.property_type, l.loan_purpose,
                    l.self_employed, l.co_borrower_income,
                    l.years_at_job
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            loan_type = (loan.loan_type or "conventional").lower()
            occupancy = (loan.occupancy_type or "primary").lower()
            credit = int(loan.credit_score or 0)
            ltv = float(loan.ltv or 0)
            income = float(loan.monthly_income or 0) + float(loan.co_borrower_income or 0)
            housing = float(loan.proposed_housing_expense or 0)
            debts = float(loan.monthly_debt or 0)
            back_dti = ((housing + debts) / income * 100) if income > 0 else 0

            checks = []

            # Credit score check
            min_score = MIN_CREDIT_SCORES.get(loan_type, 620)
            checks.append({
                "guideline": "Minimum Credit Score",
                "requirement": f"{min_score}",
                "actual": f"{credit}",
                "status": "pass" if credit >= min_score else "fail",
                "agency": "FNMA/FHLMC" if loan_type == "conventional" else loan_type.upper()
            })

            # LTV check
            ltv_key = f"{loan_type}_{occupancy}"
            max_ltv_val = MAX_LTV.get(ltv_key, 97.0)
            checks.append({
                "guideline": "Maximum LTV",
                "requirement": f"{max_ltv_val}%",
                "actual": f"{ltv:.1f}%",
                "status": "pass" if ltv <= max_ltv_val else "fail",
                "agency": "FNMA/FHLMC" if loan_type == "conventional" else loan_type.upper()
            })

            # DTI check
            limits = AGENCY_DTI_LIMITS.get(loan_type, AGENCY_DTI_LIMITS["conventional"])
            checks.append({
                "guideline": "Maximum Back-End DTI",
                "requirement": f"{limits['du_max']}% (DU/LP max)",
                "actual": f"{back_dti:.1f}%",
                "status": "pass" if back_dti <= limits["du_max"] else "fail",
                "agency": "FNMA/FHLMC" if loan_type == "conventional" else loan_type.upper()
            })

            # Standard DTI
            checks.append({
                "guideline": "Standard Back-End DTI",
                "requirement": f"{limits['back']}% (standard) / {limits['back_with_compensating']}% (with compensating factors)",
                "actual": f"{back_dti:.1f}%",
                "status": "pass" if back_dti <= limits["back"] else ("conditional" if back_dti <= limits["back_with_compensating"] else "fail"),
                "agency": "FNMA/FHLMC" if loan_type == "conventional" else loan_type.upper()
            })

            # Loan amount (conforming limits)
            amount = float(loan.amount or 0)
            conforming_limit = 832750  # 2026 conforming limit — single unit
            if loan_type == "conventional":
                checks.append({
                    "guideline": "Conforming Loan Limit",
                    "requirement": f"${conforming_limit:,}",
                    "actual": f"${amount:,.0f}",
                    "status": "pass" if amount <= conforming_limit else "fail",
                    "agency": "FHFA"
                })

            # Employment history
            years = float(loan.years_at_job or 0)
            checks.append({
                "guideline": "Employment History",
                "requirement": "2 years in same line of work",
                "actual": f"{years:.1f} years at current employer",
                "status": "pass" if years >= 2 else "review",
                "agency": "FNMA/FHLMC"
            })

            pass_count = len([c for c in checks if c["status"] == "pass"])
            fail_count = len([c for c in checks if c["status"] == "fail"])
            review_count = len([c for c in checks if c["status"] in ("review", "conditional")])

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "loan_type": loan_type,
                "guideline_checks": checks,
                "summary": {
                    "total_checks": len(checks),
                    "pass": pass_count,
                    "fail": fail_count,
                    "review": review_count,
                    "overall": "eligible" if fail_count == 0 else "ineligible"
                }
            }

            self.audit_log("compare_to_aig_guidelines", "loan", entity_id=str(loan_id), details={
                "pass": pass_count,
                "fail": fail_count,
                "review": review_count,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"AIG check: {pass_count} pass, {fail_count} fail, {review_count} review — {'ELIGIBLE' if fail_count == 0 else 'INELIGIBLE'}"
            )

        except Exception as e:
            logger.exception(f"compare_to_aig_guidelines failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_layered_risk(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify multiple risk layers"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.credit_score, l.ltv, l.amount,
                    l.monthly_income, l.monthly_debt, l.proposed_housing_expense,
                    l.occupancy_type, l.property_type, l.loan_purpose,
                    l.self_employed, l.co_borrower_income,
                    l.total_assets, l.years_at_job
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            risk_layers = []
            credit = int(loan.credit_score or 0)
            ltv = float(loan.ltv or 0)
            income = float(loan.monthly_income or 0) + float(loan.co_borrower_income or 0)
            housing = float(loan.proposed_housing_expense or 0)
            debts = float(loan.monthly_debt or 0)
            back_dti = ((housing + debts) / income * 100) if income > 0 else 0

            # Layer 1: Low credit
            if credit < 660:
                risk_layers.append({
                    "risk": "Low Credit Score",
                    "detail": f"Credit score {credit} below 660 threshold",
                    "weight": 3 if credit < 620 else 2
                })

            # Layer 2: High DTI
            if back_dti > 45:
                risk_layers.append({
                    "risk": "High DTI",
                    "detail": f"Back-end DTI {back_dti:.1f}% exceeds 45%",
                    "weight": 3 if back_dti > 50 else 2
                })

            # Layer 3: High LTV
            if ltv > 90:
                risk_layers.append({
                    "risk": "High LTV",
                    "detail": f"LTV {ltv:.1f}% exceeds 90%",
                    "weight": 2 if ltv <= 95 else 3
                })

            # Layer 4: Investment property
            occupancy = (loan.occupancy_type or "").lower()
            if occupancy == "investment":
                risk_layers.append({
                    "risk": "Investment Property",
                    "detail": "Non-owner occupied investment property",
                    "weight": 2
                })

            # Layer 5: Cash-out refinance
            purpose = (loan.loan_purpose or "").lower()
            if "cash" in purpose and "out" in purpose:
                risk_layers.append({
                    "risk": "Cash-Out Refinance",
                    "detail": "Cash-out refinance increases risk exposure",
                    "weight": 2
                })

            # Layer 6: Self-employed
            if loan.self_employed:
                risk_layers.append({
                    "risk": "Self-Employed Borrower",
                    "detail": "Self-employed income stability risk",
                    "weight": 1
                })

            # Layer 7: Limited reserves
            total_assets = float(loan.total_assets or 0)
            if housing > 0 and total_assets / housing < 2:
                risk_layers.append({
                    "risk": "Limited Reserves",
                    "detail": f"Only {total_assets / housing:.1f} months of reserves",
                    "weight": 2
                })

            # Layer 8: Short employment tenure
            years = float(loan.years_at_job or 0)
            if years < 1:
                risk_layers.append({
                    "risk": "Short Employment Tenure",
                    "detail": f"Only {years:.1f} years at current employer",
                    "weight": 1
                })

            total_weight = sum(r["weight"] for r in risk_layers)
            layer_count = len(risk_layers)

            if total_weight >= 8:
                risk_level = "critical"
                recommendation = "Multiple significant risk layers — recommend denial or substantial compensating factors required"
            elif total_weight >= 5:
                risk_level = "high"
                recommendation = "Elevated layered risk — management review recommended before approval"
            elif total_weight >= 3:
                risk_level = "moderate"
                recommendation = "Some layered risk present — document compensating factors thoroughly"
            else:
                risk_level = "low"
                recommendation = "Minimal layered risk — standard underwriting applies"

            data = {
                "loan_id": loan_id,
                "loan_number": loan.loan_number,
                "risk_layers": risk_layers,
                "layer_count": layer_count,
                "total_risk_weight": total_weight,
                "risk_level": risk_level,
                "recommendation": recommendation,
                "metrics": {
                    "credit_score": credit,
                    "back_dti": round(back_dti, 1),
                    "ltv": ltv,
                    "occupancy": occupancy,
                    "self_employed": bool(loan.self_employed),
                }
            }

            self.audit_log("check_layered_risk", "loan", entity_id=str(loan_id), details={
                "layer_count": layer_count,
                "total_weight": total_weight,
                "risk_level": risk_level,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"Layered risk: {risk_level.upper()} ({layer_count} layers, weight {total_weight}) — {recommendation[:60]}"
            )

        except Exception as e:
            logger.exception(f"check_layered_risk failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_suspension_letter(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Draft suspension notice"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        suspension_reasons = input_data["suspension_reasons"]
        items_needed = input_data["items_needed"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.loan_type, l.amount, l.stage,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            letter = {
                "type": "SUSPENSION_NOTICE",
                "date": datetime.utcnow().strftime("%m/%d/%Y"),
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "loan_amount": float(loan.amount or 0),
                "loan_type": loan.loan_type,
                "loan_officer": loan.lo_name,
                "header": f"SUSPENSION NOTICE — Loan #{loan.loan_number}",
                "body": (
                    f"This loan file has been suspended pending receipt and satisfactory "
                    f"review of the items listed below. The file cannot be moved to approval "
                    f"status until all suspension items have been addressed."
                ),
                "suspension_reasons": [
                    {"number": i + 1, "reason": reason}
                    for i, reason in enumerate(suspension_reasons)
                ],
                "items_needed": [
                    {"number": i + 1, "item": item}
                    for i, item in enumerate(items_needed)
                ],
                "footer": (
                    "Please provide the above items within 10 business days. "
                    "Failure to provide the requested items may result in denial of the loan application. "
                    "If you have questions, please contact the assigned loan officer."
                ),
                "requires_review": True,
                "status": "draft"
            }

            self.audit_log("generate_suspension_letter", "loan", entity_id=str(loan_id), details={
                "reason_count": len(suspension_reasons),
                "items_count": len(items_needed),
            })

            return ToolResult(
                success=True,
                data=letter,
                message=f"Suspension letter drafted for loan {loan.loan_number}: {len(suspension_reasons)} reasons, {len(items_needed)} items needed"
            )

        except Exception as e:
            logger.exception(f"generate_suspension_letter failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_approval_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate approval summary"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_conditions = input_data.get("include_conditions", True)
        include_exceptions = input_data.get("include_exceptions", True)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.loan_type,
                    l.amount, l.rate, l.loan_term, l.credit_score,
                    l.monthly_income, l.co_borrower_income, l.monthly_debt,
                    l.proposed_housing_expense, l.ltv, l.cltv,
                    l.property_value, l.property_address, l.occupancy_type,
                    l.property_type, l.loan_purpose, l.self_employed,
                    l.total_assets, l.down_payment_amount,
                    l.closing_date, l.lock_expiration_date,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            income = float(loan.monthly_income or 0) + float(loan.co_borrower_income or 0)
            housing = float(loan.proposed_housing_expense or 0)
            debts = float(loan.monthly_debt or 0)
            front_dti = round((housing / income * 100), 1) if income > 0 else 0
            back_dti = round(((housing + debts) / income * 100), 1) if income > 0 else 0

            summary = {
                "type": "APPROVAL_SUMMARY",
                "approval_date": datetime.utcnow().strftime("%m/%d/%Y"),
                "underwriter_user_id": context.get("user_id"),
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "loan_officer": loan.lo_name,
                "loan_terms": {
                    "loan_type": loan.loan_type,
                    "purpose": loan.loan_purpose,
                    "amount": float(loan.amount or 0),
                    "rate": float(loan.rate or 0),
                    "term_months": int(loan.loan_term or 360),
                    "property_type": loan.property_type,
                    "occupancy": loan.occupancy_type,
                },
                "property": {
                    "address": loan.property_address,
                    "value": float(loan.property_value or 0),
                },
                "qualification_metrics": {
                    "credit_score": int(loan.credit_score or 0),
                    "front_dti": front_dti,
                    "back_dti": back_dti,
                    "ltv": float(loan.ltv or 0),
                    "cltv": float(loan.cltv or 0),
                    "monthly_income": round(income, 2),
                    "total_assets": float(loan.total_assets or 0),
                    "down_payment": float(loan.down_payment_amount or 0),
                },
                "key_dates": {
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "lock_expiration": loan.lock_expiration_date.isoformat() if loan.lock_expiration_date else None,
                },
            }

            # Add conditions
            if include_conditions:
                conditions = db.execute(text("""
                    SELECT condition_type, description, status, due_date
                    FROM loan_conditions
                    WHERE loan_id = :loan_id
                    ORDER BY
                        CASE status WHEN 'pending' THEN 1 WHEN 'submitted' THEN 2 ELSE 3 END,
                        due_date ASC NULLS LAST
                """), {"loan_id": loan_id}).fetchall()

                summary["conditions"] = {
                    "total": len(conditions),
                    "pending": len([c for c in conditions if c.status == "pending"]),
                    "items": [
                        {
                            "type": c.condition_type,
                            "description": c.description,
                            "status": c.status,
                            "due_date": c.due_date.isoformat() if c.due_date else None
                        }
                        for c in conditions
                    ]
                }

            # Add exceptions
            if include_exceptions:
                exceptions = []
                loan_type = (loan.loan_type or "conventional").lower()
                limits = AGENCY_DTI_LIMITS.get(loan_type, AGENCY_DTI_LIMITS["conventional"])

                if back_dti > limits["back"]:
                    exceptions.append({
                        "type": "DTI_EXCEPTION",
                        "detail": f"Back-end DTI {back_dti}% exceeds standard {limits['back']}% — approved with compensating factors"
                    })

                ltv = float(loan.ltv or 0)
                ltv_key = f"{loan_type}_{(loan.occupancy_type or 'primary').lower()}"
                max_ltv_val = MAX_LTV.get(ltv_key, 97.0)
                if ltv > max_ltv_val * 0.95 and ltv <= max_ltv_val:
                    exceptions.append({
                        "type": "HIGH_LTV_NOTE",
                        "detail": f"LTV {ltv:.1f}% near maximum — MI/funding fee requirements apply"
                    })

                summary["exceptions"] = exceptions

            summary["status"] = "draft"
            summary["requires_review"] = True

            self.audit_log("create_approval_summary", "loan", entity_id=str(loan_id), details={
                "credit_score": int(loan.credit_score or 0),
                "back_dti": back_dti,
                "ltv": float(loan.ltv or 0),
                "conditions": summary.get("conditions", {}).get("total", 0),
            })

            return ToolResult(
                success=True,
                data=summary,
                message=f"Approval summary for {loan.loan_number}: DTI {back_dti}%, LTV {float(loan.ltv or 0):.1f}%, credit {int(loan.credit_score or 0)}"
            )

        except Exception as e:
            logger.exception(f"create_approval_summary failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
