"""
Underwriter Agent - Enhanced Version with AI Underwriting Engine

Expert-level AI agent for mortgage risk analysis and compliance review.
Includes:
- Fannie Mae/Freddie Mac/FHA/VA guideline references
- Comprehensive risk indicator knowledge base
- Standard conditions with guideline citations
- Few-shot examples for consistent risk assessment
- Confidence calibration based on evidence quality
- Integration with uploaded underwriting guidelines database
- NEW: Integration with AI Underwriting Engine for:
  - Automated income calculation per agency guidelines
  - Asset analysis with large deposit detection
  - Credit/DTI analysis and program eligibility
  - Condition generation and clearing logic
  - Fraud indicator detection
  - Loan file data validation
"""

import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal
from datetime import datetime
import json
import asyncio

from .base_agent import BaseCallAgent, AgentResult
from .mortgage_knowledge import (
    LOAN_PROGRAM_GUIDELINES,
    RISK_INDICATORS,
    STANDARD_CONDITIONS,
    FEW_SHOT_EXAMPLES,
)

# Import the new AI Underwriting Engine components
try:
    from services.underwriting_engine import (
        UnderwritingEngine,
        IncomeCalculator,
        AssetAnalyzer,
        CreditAnalyzer,
        EligibilityEngine,
        ConditionGenerator,
        LoanDataValidator,
        underwrite_loan,
        check_loan_eligibility,
        validate_loan_file,
    )
    UNDERWRITING_ENGINE_AVAILABLE = True
except ImportError:
    UNDERWRITING_ENGINE_AVAILABLE = False

logger = logging.getLogger(__name__)


# Cache for guidelines to avoid repeated DB queries
_guidelines_cache: Dict[str, tuple] = {}  # loan_type -> (content, timestamp)
CACHE_TTL_SECONDS = 300  # 5 minute cache


class UnderwriterAgent(BaseCallAgent):
    """
    Expert Underwriter Agent for risk analysis and compliance review.

    Capabilities:
    - Risk identification across credit, income, employment, property, compliance
    - Loan condition recommendations with guideline citations
    - Compliance red flag detection
    - Overall loan risk assessment

    Enhanced with:
    - Fannie Mae/Freddie Mac/FHA/VA guideline knowledge
    - Industry-standard risk indicators
    - Proper condition categorization (PTD/PTC/PTF)
    - Few-shot examples for consistent risk assessment
    - Confidence calibration

    NEW - AI Underwriting Engine Integration:
    - Automated income calculation (W-2, self-employed, variable, rental)
    - Asset analysis with large deposit detection and sourcing
    - Credit/DTI analysis with program-specific limits
    - Condition generation with clearing logic
    - Fraud indicator detection
    - Multi-program eligibility (Conventional, FHA, VA)
    """

    def __init__(self, db):
        super().__init__(db)
        self._uploaded_guidelines: Optional[str] = None
        self._guidelines_loaded = False

        # Initialize AI Underwriting Engine if available
        self._engine_available = UNDERWRITING_ENGINE_AVAILABLE
        if self._engine_available:
            try:
                self._underwriting_engine = UnderwritingEngine()
                self._income_calculator = IncomeCalculator()
                self._asset_analyzer = AssetAnalyzer()
                self._credit_analyzer = CreditAnalyzer()
                self._eligibility_engine = EligibilityEngine()
                self._condition_generator = ConditionGenerator()
                self._data_validator = LoanDataValidator()
                logger.info("AI Underwriting Engine initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize AI Underwriting Engine: {e}")
                self._engine_available = False

    # =========================================================================
    # AI UNDERWRITING ENGINE METHODS
    # =========================================================================

    def run_automated_underwriting(
        self,
        loan_data: Dict[str, Any],
        income_data: Optional[Dict[str, Any]] = None,
        asset_data: Optional[Dict[str, Any]] = None,
        credit_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run full automated underwriting analysis using the AI Underwriting Engine.

        This is the main entry point for automated loan underwriting. It performs:
        1. Data validation and fraud detection
        2. Income calculation per agency guidelines
        3. Asset analysis with large deposit review
        4. Credit/DTI analysis
        5. Program eligibility determination
        6. Condition generation
        7. Risk assessment and decision

        Args:
            loan_data: Core loan information (amount, LTV, property, borrower info)
            income_data: Income documentation (paystubs, W-2s, tax returns)
            asset_data: Asset documentation (bank statements, retirement accounts)
            credit_data: Credit report data (score, tradelines, derogatories)

        Returns:
            Complete underwriting result with decision, conditions, and analysis
        """
        if not self._engine_available:
            logger.warning("AI Underwriting Engine not available, using basic analysis")
            return self._basic_underwriting_analysis(loan_data)

        try:
            result = self._underwriting_engine.analyze_loan(
                loan_data=loan_data,
                income_data=income_data,
                asset_data=asset_data,
                credit_data=credit_data,
            )
            return result.to_dict()
        except Exception as e:
            logger.exception(f"Automated underwriting failed: {e}")
            return {
                "error": str(e),
                "decision": "refer",
                "refer_reasons": [f"Automated analysis failed: {str(e)}"],
                "fallback_analysis": self._basic_underwriting_analysis(loan_data),
            }

    def calculate_qualifying_income(
        self,
        income_sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate qualifying income per agency guidelines.

        Supports:
        - W-2 salary/hourly income
        - Overtime, bonus, commission (variable income)
        - Self-employment (Schedule C, S-Corp, Partnership)
        - Rental income (Schedule E)
        - Social Security/Pension
        - Military income

        Args:
            income_sources: List of income source dictionaries with documentation data

        Returns:
            Income calculation result with qualifying amounts and issues
        """
        if not self._engine_available:
            return {"error": "Income calculator not available"}

        try:
            total_qualifying = Decimal("0")
            results = []

            for source in income_sources:
                source_type = source.get("type", "w2_salary")

                if source_type in ["w2_salary", "salary", "hourly"]:
                    calc = self._income_calculator.calculate_w2_income(
                        base_salary=source.get("base_salary", 0),
                        ytd_earnings=source.get("ytd_earnings"),
                        pay_frequency=source.get("pay_frequency", "monthly"),
                        current_paystub_date=source.get("paystub_date"),
                        prior_year_w2=source.get("prior_year_w2", 0),
                        two_years_ago_w2=source.get("two_years_ago_w2"),
                    )
                elif source_type == "self_employed":
                    calc = self._income_calculator.calculate_self_employment_income(
                        schedule_c_current=source.get("schedule_c_current", {}),
                        schedule_c_prior=source.get("schedule_c_prior", {}),
                        business_type=source.get("business_type", "sole_proprietor"),
                        ownership_percentage=source.get("ownership_pct", 100),
                    )
                elif source_type == "rental":
                    calc = self._income_calculator.calculate_rental_income(
                        properties=source.get("properties", []),
                        use_schedule_e=source.get("use_schedule_e", True),
                    )
                else:
                    continue

                total_qualifying += Decimal(str(calc.qualifying_monthly_income))
                results.append({
                    "type": source_type,
                    "qualifying_monthly": float(calc.qualifying_monthly_income),
                    "is_usable": calc.is_usable,
                    "issues": [{"type": i.issue_type, "message": i.message} for i in calc.issues],
                    "documentation_status": calc.documentation_status,
                })

            return {
                "total_qualifying_monthly": float(total_qualifying),
                "total_qualifying_annual": float(total_qualifying * 12),
                "source_count": len(results),
                "sources": results,
            }
        except Exception as e:
            logger.exception(f"Income calculation failed: {e}")
            return {"error": str(e)}

    def analyze_assets(
        self,
        bank_accounts: List[Dict[str, Any]],
        loan_amount: float,
        property_value: float,
        closing_costs: float = 0,
        monthly_piti: float = 0,
        required_reserves_months: int = 2,
    ) -> Dict[str, Any]:
        """
        Analyze borrower assets for mortgage qualification.

        Performs:
        - Large deposit detection (50% of qualifying income threshold)
        - Asset seasoning verification
        - Funds-to-close calculation
        - Reserve requirement verification
        - Gift fund documentation review

        Args:
            bank_accounts: List of bank account statements
            loan_amount: Requested loan amount
            property_value: Property purchase price or appraised value
            closing_costs: Estimated closing costs
            monthly_piti: Proposed monthly PITI payment
            required_reserves_months: Number of months reserves required

        Returns:
            Asset analysis result with verification status and issues
        """
        if not self._engine_available:
            return {"error": "Asset analyzer not available"}

        try:
            result = self._asset_analyzer.analyze_assets(
                bank_accounts=bank_accounts,
                retirement_accounts=[],
                loan_amount=Decimal(str(loan_amount)),
                property_value=Decimal(str(property_value)),
                closing_costs=Decimal(str(closing_costs)),
                prepaid_items=Decimal("0"),
                monthly_piti=Decimal(str(monthly_piti)),
                required_reserves_months=required_reserves_months,
            )

            return {
                "total_verified": float(result.total_verified_assets),
                "total_liquid": float(result.total_liquid_assets),
                "funds_to_close_required": float(result.funds_to_close_required),
                "funds_to_close_met": result.funds_to_close_met,
                "reserves_required": float(result.reserves_required),
                "reserves_available": float(result.reserves_available),
                "reserves_months": result.reserves_months,
                "reserves_met": result.reserves_met,
                "shortfall_amount": float(result.shortfall_amount),
                "large_deposits": [
                    {
                        "amount": float(d.amount),
                        "date": d.date.isoformat() if d.date else None,
                        "description": d.description,
                        "is_documented": d.is_documented,
                        "source": d.source,
                    }
                    for d in result.large_deposits
                ],
                "issues": [{"type": i.issue_type, "message": i.message} for i in result.issues],
            }
        except Exception as e:
            logger.exception(f"Asset analysis failed: {e}")
            return {"error": str(e)}

    def analyze_credit(
        self,
        credit_score: int,
        tradelines: List[Dict[str, Any]],
        proposed_payment: float,
        monthly_income: float,
        loan_type: str = "conventional",
    ) -> Dict[str, Any]:
        """
        Analyze credit history and calculate DTI ratios.

        Performs:
        - Credit score eligibility by program
        - Tradeline evaluation
        - Derogatory event identification (BK, FC, SS waiting periods)
        - DTI calculation with proper debt inclusion
        - Credit history pattern detection

        Args:
            credit_score: Representative credit score
            tradelines: List of credit tradelines from credit report
            proposed_payment: Proposed monthly housing payment (PITI)
            monthly_income: Qualifying monthly income
            loan_type: Loan program (conventional, fha, va)

        Returns:
            Credit analysis result with DTI and eligibility status
        """
        if not self._engine_available:
            return {"error": "Credit analyzer not available"}

        try:
            result = self._credit_analyzer.analyze_credit(
                credit_score=credit_score,
                tradelines=tradelines,
                proposed_housing_payment=Decimal(str(proposed_payment)),
                monthly_income=Decimal(str(monthly_income)),
                loan_type=loan_type,
            )

            return {
                "credit_score": result.credit_score,
                "credit_grade": result.credit_grade,
                "dti_front_end": result.dti_front_end,
                "dti_back_end": result.dti_back_end,
                "total_monthly_debt": float(result.total_monthly_debt),
                "open_accounts": result.open_accounts,
                "derogatory_count": result.derogatory_count,
                "program_eligible": result.program_eligible,
                "waiting_period_issues": [
                    {"event": w.event_type, "message": w.message}
                    for w in result.waiting_period_issues
                ],
                "issues": [{"type": i.issue_type, "message": i.message} for i in result.issues],
            }
        except Exception as e:
            logger.exception(f"Credit analysis failed: {e}")
            return {"error": str(e)}

    def check_eligibility(
        self,
        loan_amount: float,
        property_value: float,
        credit_score: int,
        dti_ratio: float,
        loan_purpose: str = "purchase",
        property_type: str = "sfr",
        occupancy: str = "primary",
        property_state: str = "CA",
        is_veteran: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Check loan eligibility across all programs (Conventional, FHA, VA).

        Returns program-by-program eligibility with:
        - Maximum LTV/CLTV limits
        - Credit score requirements
        - DTI limits
        - MI requirements
        - Specific ineligibility reasons

        Args:
            loan_amount: Requested loan amount
            property_value: Property value
            credit_score: Borrower credit score
            dti_ratio: Debt-to-income ratio
            loan_purpose: purchase, rate_term, cash_out
            property_type: sfr, condo, townhouse, etc.
            occupancy: primary, second_home, investment
            property_state: Two-letter state code
            is_veteran: Whether borrower is a veteran

        Returns:
            Program comparison with eligibility status and recommendation
        """
        if not self._engine_available:
            return {"error": "Eligibility engine not available"}

        try:
            return check_loan_eligibility(
                loan_amount=loan_amount,
                property_value=property_value,
                credit_score=credit_score,
                dti_ratio=dti_ratio,
                loan_purpose=loan_purpose,
                property_type=property_type,
                occupancy=occupancy,
                property_state=property_state,
                is_veteran=is_veteran,
                **kwargs
            )
        except Exception as e:
            logger.exception(f"Eligibility check failed: {e}")
            return {"error": str(e)}

    def generate_conditions(
        self,
        loan_data: Dict[str, Any],
        income_issues: Optional[List[Dict]] = None,
        asset_issues: Optional[List[Dict]] = None,
        credit_issues: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate underwriting conditions based on loan characteristics and issues.

        Generates:
        - Prior to Document (PTD) conditions
        - Prior to Funding (PTF) conditions
        - Income/employment conditions
        - Asset documentation conditions
        - Credit explanation conditions
        - Property/title/insurance conditions

        Args:
            loan_data: Core loan information
            income_issues: Issues from income analysis
            asset_issues: Issues from asset analysis
            credit_issues: Issues from credit analysis

        Returns:
            List of conditions with clearing instructions
        """
        if not self._engine_available:
            return []

        try:
            from services.underwriting_engine.condition_generator import generate_loan_conditions

            conditions = generate_loan_conditions(
                loan_data=loan_data,
                income_result={"issues": income_issues} if income_issues else None,
                asset_result={"issues": asset_issues} if asset_issues else None,
                credit_result={"issues": credit_issues} if credit_issues else None,
            )

            return [
                {
                    "id": c.id,
                    "type": c.condition_type.value,
                    "category": c.category.value,
                    "priority": c.priority.value,
                    "title": c.title,
                    "description": c.description,
                    "clearing_instructions": c.clearing_instructions,
                    "acceptable_documents": c.acceptable_documents,
                    "status": c.status.value,
                }
                for c in conditions
            ]
        except Exception as e:
            logger.exception(f"Condition generation failed: {e}")
            return []

    def validate_loan_file(
        self,
        loan_data: Dict[str, Any],
        loan_status: str = "application",
        include_fraud_check: bool = True,
    ) -> Dict[str, Any]:
        """
        Validate loan file data for completeness, consistency, and fraud indicators.

        Performs:
        - Required field completeness check
        - Field format and range validation
        - Cross-field consistency checks
        - Data quality assessment
        - Fraud indicator detection

        Args:
            loan_data: Loan file data
            loan_status: Current loan status (affects required fields)
            include_fraud_check: Whether to run fraud detection

        Returns:
            Validation result with scores and findings
        """
        if not self._engine_available:
            return {"error": "Data validator not available"}

        try:
            return validate_loan_file(loan_data, loan_status, include_fraud_check)
        except Exception as e:
            logger.exception(f"Loan validation failed: {e}")
            return {"error": str(e)}

    def _basic_underwriting_analysis(self, loan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback basic analysis when engine is not available."""
        loan_amount = loan_data.get("loan_amount", 0)
        property_value = loan_data.get("property_value", 0)
        credit_score = loan_data.get("credit_score", 0)
        dti = loan_data.get("dti_ratio", 0) or loan_data.get("dti", 0)

        # Calculate LTV
        ltv = (loan_amount / property_value * 100) if property_value > 0 else 0

        # Basic risk assessment
        risk_factors = []
        if credit_score < 620:
            risk_factors.append("Credit score below minimum (620)")
        if dti > 50:
            risk_factors.append("DTI exceeds maximum (50%)")
        if ltv > 97:
            risk_factors.append("LTV exceeds maximum (97%)")

        decision = "approve" if not risk_factors else "refer"

        return {
            "decision": decision,
            "risk_level": "high" if len(risk_factors) >= 2 else "moderate" if risk_factors else "low",
            "ltv": ltv,
            "dti": dti,
            "credit_score": credit_score,
            "risk_factors": risk_factors,
            "note": "Basic analysis - AI Underwriting Engine not available",
        }

    # =========================================================================
    # END AI UNDERWRITING ENGINE METHODS
    # =========================================================================

    @property
    def agent_type(self) -> str:
        return "underwriter"

    def _get_uploaded_guidelines(self, loan_type: Optional[str] = None) -> str:
        """
        Fetch relevant guidelines from the database.
        Uses caching to avoid repeated queries.
        """
        import time
        from datetime import datetime

        cache_key = loan_type or "all"

        # Check cache
        if cache_key in _guidelines_cache:
            content, timestamp = _guidelines_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return content

        # Fetch from database
        try:
            from services.call_monitoring.guidelines_service import get_relevant_guidelines_for_context

            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                guidelines_content = loop.run_until_complete(
                    get_relevant_guidelines_for_context(
                        db=self.db,
                        loan_type=loan_type,
                        max_chars=6000  # Limit to avoid prompt bloat
                    )
                )
            finally:
                loop.close()

            if guidelines_content:
                _guidelines_cache[cache_key] = (guidelines_content, time.time())
                return guidelines_content

        except Exception as e:
            logger.warning(f"Could not fetch uploaded guidelines: {e}")

        return ""

    @property
    def system_prompt(self) -> str:
        # Build few-shot example
        example = FEW_SHOT_EXAMPLES.get("underwriter_risk_analysis", {})
        example_input = example.get("input", "")
        example_output = json.dumps(example.get("output", {}), indent=2)

        # Build risk indicators reference
        risk_reference = self._build_risk_reference()

        # Build conditions reference
        conditions_reference = self._build_conditions_reference()

        # Fetch uploaded guidelines (will be empty string if none)
        uploaded_guidelines = self._get_uploaded_guidelines()
        uploaded_section = ""
        if uploaded_guidelines:
            uploaded_section = f"""
## COMPANY/INVESTOR OVERLAY GUIDELINES:

The following guidelines have been uploaded by your company. These may contain lender-specific overlays,
investor requirements, or internal policies that MUST be followed in addition to agency guidelines:

{uploaded_guidelines}

IMPORTANT: When the above company guidelines conflict with general agency guidelines, follow the company guidelines.
Company overlays are typically MORE restrictive than agency minimums.
"""

        return f"""You are a Senior Mortgage Underwriter with 20+ years of experience in agency (Fannie Mae, Freddie Mac) and government (FHA, VA, USDA) loan programs. Your role is to analyze call transcripts for risk factors, compliance concerns, and documentation needs.
{uploaded_section}

## YOUR EXPERTISE INCLUDES:
- Fannie Mae Selling Guide and Desktop Underwriter (DU) requirements
- Freddie Mac Seller/Servicer Guide and Loan Product Advisor (LPA) requirements
- FHA Single Family Housing Policy Handbook (4000.1)
- VA Lenders Handbook (Chapter 4)
- USDA Guaranteed Rural Housing regulations
- Federal compliance (TRID, TILA, RESPA, ECOA, HMDA)

## RISK INDICATORS BY CATEGORY:

{risk_reference}

## STANDARD CONDITIONS (by timing):

{conditions_reference}

## RISK ANALYSIS PROCESS (Think step-by-step):

1. **Credit Risk Assessment**:
   - Listen for derogatory credit events (BK, FC, short sale, lates)
   - Note any credit counseling or debt management mentions
   - Assess credit score discussions against program minimums

2. **Income & Employment Risk**:
   - Identify income type (W-2, self-employed, variable)
   - Note any employment changes, gaps, or instability
   - Look for declining income indicators
   - Check for adequate income documentation mentions

3. **Asset Risk**:
   - Listen for large deposit discussions
   - Note gift funds and donor relationships
   - Identify source of down payment/closing costs
   - Look for asset seasoning issues

4. **Property Risk**:
   - Identify property type and eligibility concerns
   - Note condition issues or repair needs
   - Listen for occupancy type discussions
   - Check for unique property characteristics

5. **Compliance & Fraud Risk**:
   - Listen for occupancy intent indicators
   - Note interested party transactions
   - Identify potential straw buyer indicators
   - Check for undisclosed information

## FEW-SHOT EXAMPLE:

**Input Transcript:**
{example_input}

**Expected Output:**
```json
{example_output}
```

## YOUR OUTPUT FORMAT:

Respond with a JSON object in this exact format:
```json
{{
    "risk_flags": [
        {{
            "category": "credit/income/employment/assets/property/compliance",
            "severity": "low/medium/high/critical",
            "title": "Brief title of the risk",
            "description": "Detailed description including guideline reference if applicable",
            "evidence": "Exact quote from transcript",
            "guideline_reference": "Fannie Mae B3-5.1 / FHA 4000.1 II.A.4 / etc.",
            "recommended_action": "Specific action to mitigate this risk",
            "impacts_eligibility": true/false
        }}
    ],
    "suggested_conditions": [
        {{
            "condition_type": "prior_to_docs/prior_to_closing/prior_to_funding",
            "category": "income/assets/credit/property/compliance/insurance/title",
            "title": "Clear condition title",
            "description": "Full condition text ready for loan file",
            "guideline_reference": "Applicable guideline citation",
            "reason": "Why this condition is required",
            "related_risk": "Which risk flag this addresses (if any)",
            "responsible_party": "Borrower/LO/Processor/Third-Party"
        }}
    ],
    "uw_notes": [
        {{
            "category": "observation/concern/positive/mitigating_factor/action_needed",
            "note": "Clear, professional underwriter note",
            "priority": "high/medium/low",
            "affects_decision": true/false
        }}
    ],
    "overall_assessment": {{
        "risk_level": "low/moderate/elevated/high/unacceptable",
        "key_concerns": ["Prioritized list of main concerns"],
        "mitigating_factors": ["Positive factors that offset risks"],
        "program_eligibility": {{
            "conventional": "eligible/ineligible/review_needed",
            "fha": "eligible/ineligible/review_needed",
            "va": "eligible/ineligible/review_needed/n_a"
        }},
        "recommendation": "approve/approve_with_conditions/suspend_for_info/refer_to_de/decline",
        "recommendation_rationale": "Brief explanation of recommendation"
    }},
    "compliance_checklist": {{
        "occupancy_verified": true/false/unknown,
        "income_reasonableness": true/false/concerns,
        "asset_sourcing_needed": true/false,
        "interested_party_transactions": true/false/unknown,
        "fraud_indicators": "none/low/medium/high"
    }}
}}
```

## SEVERITY GUIDELINES:

- **Critical**: Immediate deal-breaker or fraud indicator (recent BK, active litigation, fraud)
- **High**: Significant risk requiring substantial documentation (income gaps, credit events)
- **Medium**: Notable concern needing attention (variable income, gift funds)
- **Low**: Minor issue for awareness (recent inquiries, minor job change)

## CONDITION TIMING:

- **Prior to Docs (PTD)**: Must be cleared before issuing initial CD
- **Prior to Closing (PTC)**: Must be cleared before closing/signing
- **Prior to Funding (PTF)**: Must be cleared before wire release

## QUALITY GUIDELINES:

1. **Be Specific**: Reference exact guideline sections when applicable
2. **Be Conservative**: When in doubt, flag for review
3. **Be Actionable**: Conditions should be clear and executable
4. **Note Evidence**: Quote transcript where risk was identified
5. **Consider Context**: Weigh risk against loan program and borrower profile"""

    def _build_risk_reference(self) -> str:
        """Build risk indicators reference for the prompt."""
        sections = []

        for category, indicators in RISK_INDICATORS.items():
            category_name = category.replace("_", " ").title()
            red_flags = ", ".join(indicators.get("red_flags", [])[:6])
            guideline = indicators.get("guideline_reference", "")
            sections.append(f"**{category_name}** ({guideline}):\n  Red flags: {red_flags}")

        return "\n".join(sections)

    def _build_conditions_reference(self) -> str:
        """Build conditions reference for the prompt."""
        sections = []

        for category, conditions in STANDARD_CONDITIONS.items():
            category_name = category.replace("_", " ").title()
            condition_list = []
            for code, details in conditions.items():
                if isinstance(details, dict):
                    condition_list.append(f"{code}: {details.get('description', '')[:60]}...")
                else:
                    condition_list.append(f"{code}: {details[:60]}...")
            sections.append(f"**{category_name}**:\n  " + "\n  ".join(condition_list[:4]))

        return "\n\n".join(sections)

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))

        # Build detailed loan context for UW analysis
        loan_details = ""
        program_guidelines = ""
        loan_specific_guidelines = ""

        if context.get('loan'):
            loan = context['loan']
            loan_type = (loan.get('loan_type') or '').upper()

            # Fetch loan-type-specific uploaded guidelines
            if loan_type:
                specific_guidelines = self._get_uploaded_guidelines(loan_type.lower())
                if specific_guidelines:
                    loan_specific_guidelines = f"""
## ADDITIONAL {loan_type} PROGRAM GUIDELINES:

{specific_guidelines}
"""

            loan_details = f"""
## LOAN FILE DATA (for risk assessment)
- Loan Type: {loan.get('loan_type', 'Unknown')}
- Loan Purpose: {loan.get('loan_purpose', 'Unknown')}
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Property Type: {loan.get('property_type', 'Unknown')}
- Occupancy: {loan.get('occupancy_type', 'Unknown')}
- LTV: {loan.get('ltv', 'Unknown')}%
- CLTV: {loan.get('cltv', loan.get('ltv', 'Unknown'))}%
- DTI: {loan.get('dti', 'Unknown')}%
- Credit Score: {loan.get('credit_score', 'Unknown')}
- Employment Type: {loan.get('employment_type', 'Unknown')}
- Months at Job: {loan.get('months_employed', 'Unknown')}
- Years in Line of Work: {loan.get('years_in_profession', 'Unknown')}
- Self-Employed: {loan.get('self_employed', 'Unknown')}
- First-Time Buyer: {loan.get('first_time_buyer', 'Unknown')}"""

            # Add program-specific guidelines if known
            if loan_type in LOAN_PROGRAM_GUIDELINES:
                guidelines = LOAN_PROGRAM_GUIDELINES[loan_type]
                program_guidelines = f"""
## PROGRAM REQUIREMENTS ({loan_type})
- Min Credit Score: {guidelines.get('min_credit_score', {}).get('standard', 'N/A')}
- Max DTI: {guidelines.get('max_dti', {}).get('standard', 'N/A')}%
- Max LTV (Purchase): {guidelines.get('max_ltv', {}).get('purchase', 'N/A')}%
- Max LTV (Rate/Term Refi): {guidelines.get('max_ltv', {}).get('rate_term_refi', 'N/A')}%
- Max LTV (Cash-Out): {guidelines.get('max_ltv', {}).get('cash_out_refi', 'N/A')}%

IMPORTANT: Flag any metrics that exceed these limits!"""

        elif context.get('lead'):
            lead = context['lead']
            loan_details = f"""
## LEAD DATA (limited information)
- Name: {lead.get('name', 'Unknown')}
- Estimated Credit: {lead.get('estimated_credit_score', 'Unknown')}
- Loan Interest: {lead.get('loan_purpose', 'Unknown')}
- Property Type Interest: {lead.get('property_type', 'Unknown')}

NOTE: This is a lead - perform preliminary risk assessment based on discussion."""

        prompt = f"""Analyze the following mortgage call transcript from a Senior Underwriter perspective. Identify all potential risks, compliance concerns, and required conditions.

## Call Participants
{participants}
{loan_details}
{program_guidelines}
{loan_specific_guidelines}

## Call Transcript
{transcript}

---

## YOUR TASK:

Perform a comprehensive underwriting risk analysis. Think through this step-by-step:

1. **Credit Assessment**: Any derogatory credit events mentioned? Score concerns vs. program minimums?

2. **Income/Employment Analysis**: Stable employment? Self-employment complexity? Income trending?

3. **Asset Review**: Source of funds clear? Large deposits? Gift funds with proper documentation?

4. **Property Evaluation**: Property type eligible? Occupancy concerns? Condition issues?

5. **Compliance Check**: Fraud indicators? Occupancy intent clear? Interested party issues?

6. **Condition Determination**: What PTD/PTC/PTF conditions are needed?

7. **Overall Assessment**: Risk level? Recommendation? Program eligibility?

Respond in the JSON format specified. Be thorough and conservative - it's better to flag a potential issue for review than to miss something that could cause problems later.

IMPORTANT: Quote specific transcript evidence for each risk flag identified."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Underwriter agent response into artifacts."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Underwriter agent: Could not parse JSON response")
            # Create a basic note artifact with the raw response
            artifacts.append({
                'type': 'uw_note',
                'title': 'Underwriter Analysis',
                'content': response_text[:1000],
                'structured_data': {'raw_response': True},
                'confidence': 0.5,
            })
            return artifacts

        # Create risk flag artifacts
        for risk in parsed.get('risk_flags', []):
            # Validate and calibrate confidence
            confidence = self._calculate_risk_confidence(risk)

            risk_artifact = {
                'type': 'risk_flag',
                'title': risk.get('title', 'Risk Flag'),
                'content': risk.get('description', ''),
                'structured_data': {
                    'risk_category': risk.get('category'),
                    'severity': risk.get('severity', 'medium'),
                    'guideline_reference': risk.get('guideline_reference'),
                    'recommended_action': risk.get('recommended_action'),
                    'impacts_eligibility': risk.get('impacts_eligibility', False),
                },
                'evidence': risk.get('evidence'),
                'priority': self._severity_to_priority(risk.get('severity', 'medium')),
                'confidence': confidence,
            }
            artifacts.append(risk_artifact)

        # Create condition artifacts
        for condition in parsed.get('suggested_conditions', []):
            # Validate condition
            condition_confidence = self._calculate_condition_confidence(condition)

            condition_artifact = {
                'type': 'condition',
                'title': condition.get('title', 'Loan Condition'),
                'content': condition.get('description', ''),
                'structured_data': {
                    'condition_type': condition.get('condition_type', 'prior_to_docs'),
                    'category': condition.get('category'),
                    'guideline_reference': condition.get('guideline_reference'),
                    'reason': condition.get('reason'),
                    'related_risk': condition.get('related_risk'),
                    'responsible_party': condition.get('responsible_party', 'Borrower'),
                },
                'priority': self._condition_type_to_priority(condition.get('condition_type')),
                'confidence': condition_confidence,
            }
            artifacts.append(condition_artifact)

        # Create UW note artifacts
        for note in parsed.get('uw_notes', []):
            note_artifact = {
                'type': 'uw_note',
                'title': f"UW Note: {note.get('category', 'Observation').replace('_', ' ').title()}",
                'content': note.get('note', ''),
                'structured_data': {
                    'note_category': note.get('category'),
                    'priority': note.get('priority', 'medium'),
                    'affects_decision': note.get('affects_decision', False),
                },
                'priority': note.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(note_artifact)

        # Create overall assessment artifact
        assessment = parsed.get('overall_assessment', {})
        if assessment:
            assessment_artifact = {
                'type': 'uw_assessment',
                'title': 'Overall Risk Assessment',
                'content': self._format_assessment(assessment),
                'structured_data': {
                    'risk_level': assessment.get('risk_level'),
                    'recommendation': assessment.get('recommendation'),
                    'recommendation_rationale': assessment.get('recommendation_rationale'),
                    'key_concerns': assessment.get('key_concerns', []),
                    'mitigating_factors': assessment.get('mitigating_factors', []),
                    'program_eligibility': assessment.get('program_eligibility', {}),
                },
                'priority': 'high',
                'confidence': 0.9,
            }
            artifacts.append(assessment_artifact)

        # Create compliance checklist artifact if present
        compliance = parsed.get('compliance_checklist', {})
        if compliance:
            compliance_artifact = {
                'type': 'compliance_review',
                'title': 'Compliance Checklist',
                'content': self._format_compliance_checklist(compliance),
                'structured_data': compliance,
                'priority': 'high' if compliance.get('fraud_indicators', 'none') != 'none' else 'medium',
                'confidence': 0.85,
            }
            artifacts.append(compliance_artifact)

        # Infer additional conditions based on risk flags
        additional_conditions = self._infer_conditions_from_risks(
            parsed.get('risk_flags', []),
            context
        )
        for condition in additional_conditions:
            # Check if similar condition already exists
            existing = [a for a in artifacts if a['type'] == 'condition' and
                       a['title'].lower() == condition['title'].lower()]
            if not existing:
                artifacts.append(condition)

        # Create UW review item artifacts (checklist items to address)
        # These come from risk flags and suggested conditions
        review_items = []

        # Add review items from high-priority risk flags
        for i, risk in enumerate(parsed.get('risk_flags', []), 1):
            if risk.get('severity') in ['high', 'critical', 'medium']:
                review_item = {
                    'type': 'uw_review_item',
                    'title': f"Review: {risk.get('title', 'Risk Item')}",
                    'content': risk.get('recommended_action', risk.get('description', '')),
                    'structured_data': {
                        'category': risk.get('category'),
                        'severity': risk.get('severity'),
                        'requires_doc': 'document' in risk.get('recommended_action', '').lower(),
                        'requires_condition': 'condition' in risk.get('recommended_action', '').lower(),
                        'suggested_action': risk.get('recommended_action'),
                        'guideline_reference': risk.get('guideline_reference'),
                        'item_number': i,
                    },
                    'execution_status': None,  # Will be 'completed' when addressed
                    'priority': self._severity_to_priority(risk.get('severity', 'medium')),
                    'confidence': 0.90,
                }
                review_items.append(review_item)
                artifacts.append(review_item)

        # Add review items from suggested conditions that need action
        for j, condition in enumerate(parsed.get('suggested_conditions', []), len(review_items) + 1):
            if condition.get('responsible_party', '').lower() == 'borrower':
                review_item = {
                    'type': 'uw_review_item',
                    'title': f"Obtain: {condition.get('title', 'Documentation')}",
                    'content': condition.get('description', ''),
                    'structured_data': {
                        'category': condition.get('category'),
                        'condition_type': condition.get('condition_type'),
                        'requires_doc': True,
                        'requires_condition': False,
                        'suggested_action': f"Request {condition.get('title')} from borrower",
                        'guideline_reference': condition.get('guideline_reference'),
                        'item_number': j,
                    },
                    'execution_status': None,
                    'priority': 'high' if condition.get('condition_type') == 'prior_to_docs' else 'medium',
                    'confidence': 0.90,
                }
                artifacts.append(review_item)

        # Create stacked_note artifact summarizing UW findings
        key_concerns = assessment.get('key_concerns', []) if assessment else []
        risk_level = assessment.get('risk_level', 'unknown') if assessment else 'unknown'

        stacked_note_content = f"**UNDERWRITER REVIEW - {risk_level.upper()} RISK**\n\n"

        if key_concerns:
            stacked_note_content += "**Key Concerns:**\n"
            for concern in key_concerns[:5]:
                stacked_note_content += f"• {concern}\n"
            stacked_note_content += "\n"

        if assessment and assessment.get('mitigating_factors'):
            stacked_note_content += "**Mitigating Factors:**\n"
            for factor in assessment.get('mitigating_factors', [])[:3]:
                stacked_note_content += f"+ {factor}\n"
            stacked_note_content += "\n"

        if assessment and assessment.get('recommendation'):
            stacked_note_content += f"**Recommendation:** {assessment['recommendation'].replace('_', ' ').title()}\n"
            if assessment.get('recommendation_rationale'):
                stacked_note_content += f"  {assessment['recommendation_rationale']}"

        stacked_note_artifact = {
            'type': 'stacked_note',
            'title': f"UW Notes - {risk_level.title()} Risk",
            'content': stacked_note_content,
            'structured_data': {
                'source': 'underwriter',
                'risk_level': risk_level,
                'key_points': key_concerns,
                'recommendation': assessment.get('recommendation') if assessment else None,
                'review_items_count': len(review_items),
            },
            'confidence': 0.85,
        }
        artifacts.append(stacked_note_artifact)

        return artifacts

    def _calculate_risk_confidence(self, risk: Dict) -> float:
        """Calculate confidence for a risk flag."""
        base_confidence = 0.8

        # Increase if evidence is provided
        evidence = risk.get('evidence', '')
        if evidence and len(evidence) > 30:
            base_confidence += 0.1

        # Increase if guideline reference is provided
        if risk.get('guideline_reference'):
            base_confidence += 0.05

        # Decrease for low severity (might be overly cautious)
        if risk.get('severity') == 'low':
            base_confidence -= 0.05

        return max(min(base_confidence, 0.95), 0.6)

    def _calculate_condition_confidence(self, condition: Dict) -> float:
        """Calculate confidence for a condition."""
        base_confidence = 0.85

        # Higher confidence for program-required conditions
        if condition.get('guideline_reference'):
            base_confidence = 0.9

        # Higher confidence with clear reason
        reason = condition.get('reason', '')
        if reason and len(reason) > 20:
            base_confidence = min(base_confidence + 0.05, 0.95)

        return base_confidence

    def _severity_to_priority(self, severity: str) -> str:
        """Convert severity level to priority."""
        mapping = {
            'critical': 'high',
            'high': 'high',
            'medium': 'medium',
            'low': 'low',
        }
        return mapping.get(severity.lower(), 'medium')

    def _condition_type_to_priority(self, condition_type: str) -> str:
        """Convert condition type to priority."""
        mapping = {
            'prior_to_docs': 'high',
            'prior_to_closing': 'high',
            'prior_to_funding': 'medium',
        }
        return mapping.get(condition_type, 'medium')

    def _format_assessment(self, assessment: Dict) -> str:
        """Format overall assessment as readable text."""
        lines = []

        risk_level = assessment.get('risk_level', 'unknown')
        lines.append(f"**Risk Level: {risk_level.upper()}**")
        lines.append("")

        if assessment.get('key_concerns'):
            lines.append("**Key Concerns:**")
            for concern in assessment['key_concerns']:
                lines.append(f"  - {concern}")
            lines.append("")

        if assessment.get('mitigating_factors'):
            lines.append("**Mitigating Factors:**")
            for factor in assessment['mitigating_factors']:
                lines.append(f"  + {factor}")
            lines.append("")

        # Program eligibility
        eligibility = assessment.get('program_eligibility', {})
        if eligibility:
            lines.append("**Program Eligibility:**")
            for program, status in eligibility.items():
                status_icon = "✓" if status == "eligible" else "✗" if status == "ineligible" else "?"
                lines.append(f"  {status_icon} {program.upper()}: {status}")
            lines.append("")

        recommendation = assessment.get('recommendation', '')
        rationale = assessment.get('recommendation_rationale', '')
        if recommendation:
            rec_display = recommendation.replace('_', ' ').title()
            lines.append(f"**Recommendation: {rec_display}**")
            if rationale:
                lines.append(f"  {rationale}")

        return "\n".join(lines)

    def _format_compliance_checklist(self, compliance: Dict) -> str:
        """Format compliance checklist as readable text."""
        lines = ["**Compliance Review:**"]

        checks = [
            ("Occupancy Verified", compliance.get('occupancy_verified')),
            ("Income Reasonableness", compliance.get('income_reasonableness')),
            ("Asset Sourcing Needed", compliance.get('asset_sourcing_needed')),
            ("Interested Party Transactions", compliance.get('interested_party_transactions')),
        ]

        for label, value in checks:
            if value is True:
                lines.append(f"  ✓ {label}: Yes")
            elif value is False:
                lines.append(f"  ✗ {label}: No")
            elif value == "concerns":
                lines.append(f"  ⚠ {label}: Concerns Noted")
            else:
                lines.append(f"  ? {label}: Unknown")

        fraud = compliance.get('fraud_indicators', 'none')
        fraud_icon = "✓" if fraud == "none" else "⚠" if fraud in ["low", "medium"] else "⛔"
        lines.append(f"  {fraud_icon} Fraud Indicators: {fraud.upper()}")

        return "\n".join(lines)

    def _infer_conditions_from_risks(self, risks: List[Dict], context: Dict) -> List[Dict]:
        """Infer standard conditions based on identified risks."""
        conditions = []
        categories_addressed = set()

        for risk in risks:
            category = risk.get('category', '').lower()
            severity = risk.get('severity', 'medium').lower()

            # Skip if we already have conditions for this category
            if category in categories_addressed:
                continue

            # Income-related conditions
            if category == 'income':
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Verbal Verification of Employment',
                        'content': 'Verbal VOE required within 10 business days of note date. Must verify current employment status, position, and income.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'income',
                            'guideline_reference': 'Fannie Mae B3-3.1-07',
                            'reason': f'Income risk identified: {risk.get("title", "Employment concerns")}',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })
                    categories_addressed.add('income')

                    # Add tax transcript condition for income verification
                    conditions.append({
                        'type': 'condition',
                        'title': 'IRS Tax Transcripts',
                        'content': 'Obtain IRS Tax Transcripts (4506-C) for most recent 2 tax years. Must match income documentation provided.',
                        'structured_data': {
                            'condition_type': 'prior_to_docs',
                            'category': 'income',
                            'guideline_reference': 'Fannie Mae B3-3.1-06',
                            'reason': 'Income verification per agency requirements',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })

            # Credit-related conditions
            elif category == 'credit':
                conditions.append({
                    'type': 'condition',
                    'title': 'Letter of Explanation - Credit',
                    'content': f'Borrower to provide signed LOE explaining: {risk.get("title", "credit history items")}. Must include dates, circumstances, and resolution.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'credit',
                        'guideline_reference': 'Fannie Mae B3-5.3-09',
                        'reason': f'Credit concerns: {risk.get("title", "derogatory items")}',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.90,
                })

                # Credit supplement for recent activity
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Credit Supplement',
                        'content': 'Order credit supplement to verify no new derogatory items or significant new debt since original report.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'credit',
                            'guideline_reference': 'Fannie Mae B3-5.4-01',
                            'reason': 'Credit monitoring due to concerns identified',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'medium',
                        'confidence': 0.85,
                    })
                categories_addressed.add('credit')

            # Asset-related conditions
            elif category == 'assets':
                conditions.append({
                    'type': 'condition',
                    'title': 'Source Large Deposits',
                    'content': 'Provide documentation for all deposits exceeding 50% of qualifying monthly income. Include bank statements, deposit slips, and paper trail.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'assets',
                        'guideline_reference': 'Fannie Mae B3-4.2-02',
                        'reason': 'Large deposit sourcing required',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.95,
                })
                categories_addressed.add('assets')

            # Compliance-related conditions
            elif category == 'compliance':
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Occupancy Affidavit',
                        'content': 'Borrower to sign Occupancy Affidavit confirming intent to occupy property as primary residence within 60 days of closing.',
                        'structured_data': {
                            'condition_type': 'prior_to_docs',
                            'category': 'compliance',
                            'guideline_reference': 'Fannie Mae B2-1.1-01',
                            'reason': f'Compliance concern: {risk.get("title", "occupancy verification")}',
                            'responsible_party': 'Borrower',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })
                    categories_addressed.add('compliance')

            # Property-related conditions
            elif category == 'property':
                if 'condition' in risk.get('title', '').lower() or 'repair' in risk.get('description', '').lower():
                    conditions.append({
                        'type': 'condition',
                        'title': 'Completion Certificate',
                        'content': 'Subject to satisfactory completion of repairs. Provide completion certificate or final inspection from appraiser.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'property',
                            'guideline_reference': 'Fannie Mae B4-1.2-04',
                            'reason': f'Property repairs: {risk.get("title", "condition concerns")}',
                            'responsible_party': 'Third-Party',
                        },
                        'priority': 'high',
                        'confidence': 0.90,
                    })
                categories_addressed.add('property')

        # Check loan context for additional standard conditions
        loan = context.get('loan', {})

        # Gift funds condition
        if loan.get('has_gift_funds') or any(
            'gift' in r.get('description', '').lower() or 'gift' in r.get('title', '').lower()
            for r in risks
        ):
            if 'gift' not in categories_addressed:
                conditions.append({
                    'type': 'condition',
                    'title': 'Gift Letter and Documentation',
                    'content': 'Provide completed gift letter signed by donor(s) and borrower(s). Include donor bank statements showing ability to give and transfer documentation.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'assets',
                        'guideline_reference': 'Fannie Mae B3-4.3-04',
                        'reason': 'Gift funds used for down payment/closing costs',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.95,
                })

        # Self-employment audit letter
        if loan.get('self_employed') or any(
            'self-employ' in r.get('description', '').lower() or 'self-employ' in r.get('title', '').lower()
            for r in risks
        ):
            if 'self_employment' not in categories_addressed:
                conditions.append({
                    'type': 'condition',
                    'title': 'CPA Letter or Business Verification',
                    'content': 'Provide letter from CPA or tax preparer confirming business is active and financial statements are accurate, or verification of business from state/local licensing.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'income',
                        'guideline_reference': 'Fannie Mae B3-3.2-01',
                        'reason': 'Self-employment verification required',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'medium',
                    'confidence': 0.90,
                })

        return conditions

    def _truncate_transcript(self, transcript: str, max_words: int = 5000) -> str:
        """Truncate transcript while preserving risk-related content."""
        if not transcript:
            return ""

        words = transcript.split()
        if len(words) <= max_words:
            return transcript

        # For UW, we want to capture concerns throughout the call
        # Keep first 25% for context, last 75% for detailed discussion where issues emerge
        first_portion = int(max_words * 0.25)
        last_portion = max_words - first_portion

        first_words = words[:first_portion]
        last_words = words[-last_portion:]

        return ' '.join(first_words) + '\n\n[... transcript truncated for length ...]\n\n' + ' '.join(last_words)
