"""
AI Underwriting Engine API Routes

Endpoints for automated loan underwriting, including:
- Full automated underwriting analysis
- Income calculation per agency guidelines
- Asset analysis with large deposit detection
- Credit/DTI analysis
- Program eligibility determination
- Condition generation and clearing
- Loan file validation and fraud detection
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/underwriting-engine", tags=["AI Underwriting Engine"], dependencies=[Depends(require_auth)])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class IncomeSourceType(str, Enum):
    W2 = "w2"
    SELF_EMPLOYED = "self_employed"
    VARIABLE = "variable"
    RENTAL = "rental"
    SOCIAL_SECURITY = "social_security"
    PENSION = "pension"
    ALIMONY = "alimony"
    CHILD_SUPPORT = "child_support"
    INVESTMENT = "investment"
    OTHER = "other"


class AssetAccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    RETIREMENT_401K = "retirement_401k"
    RETIREMENT_IRA = "retirement_ira"
    INVESTMENT = "investment"
    STOCKS = "stocks"
    GIFT = "gift"
    OTHER = "other"


class LoanPurposeType(str, Enum):
    PURCHASE = "purchase"
    RATE_TERM_REFINANCE = "rate_term_refinance"
    CASH_OUT_REFINANCE = "cash_out_refinance"


class PropertyTypeOption(str, Enum):
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY_2_4 = "multi_family_2_4"
    MANUFACTURED = "manufactured"
    PUD = "pud"


class OccupancyTypeOption(str, Enum):
    PRIMARY = "primary"
    SECOND_HOME = "second_home"
    INVESTMENT = "investment"


class AgencyType(str, Enum):
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"


# --- Income Models ---

class IncomeSource(BaseModel):
    type: IncomeSourceType
    employer_name: Optional[str] = None
    annual_amount: float
    monthly_amount: Optional[float] = None
    years_employed: Optional[float] = None
    months_employed: Optional[int] = None
    ytd_earnings: Optional[float] = None
    prior_year_income: Optional[float] = None
    two_years_prior_income: Optional[float] = None
    is_variable: bool = False
    documentation: Optional[List[str]] = None


class IncomeCalculationRequest(BaseModel):
    borrower_id: Optional[str] = None
    loan_id: Optional[str] = None
    income_sources: List[IncomeSource]
    calculate_trending: bool = True
    agency: AgencyType = AgencyType.CONVENTIONAL


class IncomeCalculationResponse(BaseModel):
    total_qualifying_income: float
    monthly_qualifying_income: float
    income_breakdown: List[Dict[str, Any]]
    trending_applied: bool
    issues: List[str]
    recommendations: List[str]


# --- Asset Models ---

class AssetAccount(BaseModel):
    type: AssetAccountType
    institution_name: str
    account_number_last4: Optional[str] = None
    current_balance: float
    two_month_avg_balance: Optional[float] = None
    statement_date: Optional[date] = None
    is_joint: bool = False
    owner: Optional[str] = None


class LargeDepositItem(BaseModel):
    date: date
    amount: float
    description: Optional[str] = None
    source_documented: bool = False
    source_explanation: Optional[str] = None


class AssetAnalysisRequest(BaseModel):
    borrower_id: Optional[str] = None
    loan_id: Optional[str] = None
    accounts: List[AssetAccount]
    large_deposits: Optional[List[LargeDepositItem]] = None
    loan_amount: float
    closing_costs: float = 0
    down_payment: float = 0
    reserves_required_months: int = 2


class AssetAnalysisResponse(BaseModel):
    total_liquid_assets: float
    total_retirement_assets: float
    total_verifiable_assets: float
    funds_to_close: float
    reserves_available: float
    reserves_months: int
    large_deposits_to_source: List[Dict[str, Any]]
    asset_issues: List[str]
    sufficient_assets: bool


# --- Credit Models ---

class TradelineItem(BaseModel):
    creditor_name: str
    account_type: str
    balance: float
    monthly_payment: float
    high_credit: Optional[float] = None
    credit_limit: Optional[float] = None
    date_opened: Optional[date] = None
    status: str = "current"
    late_30_count: int = 0
    late_60_count: int = 0
    late_90_count: int = 0


class CreditEventItem(BaseModel):
    event_type: str  # bankruptcy, foreclosure, short_sale, deed_in_lieu
    date_filed: Optional[date] = None
    date_discharged: Optional[date] = None
    chapter: Optional[str] = None  # For bankruptcy: 7, 13


class CreditAnalysisRequest(BaseModel):
    borrower_id: Optional[str] = None
    loan_id: Optional[str] = None
    credit_score: int
    credit_score_source: str = "experian"  # experian, equifax, transunion
    tradelines: List[TradelineItem]
    credit_events: Optional[List[CreditEventItem]] = None
    inquiries_last_90_days: int = 0
    proposed_housing_payment: float
    agency: AgencyType = AgencyType.CONVENTIONAL


class CreditAnalysisResponse(BaseModel):
    credit_score: int
    representative_score: int
    total_monthly_obligations: float
    housing_expense: float
    front_end_dti: float
    back_end_dti: float
    credit_grade: str  # A, B, C, D
    derogatory_items: List[Dict[str, Any]]
    waiting_periods_met: bool
    credit_issues: List[str]
    recommendations: List[str]


# --- Eligibility Models ---

class LoanScenarioRequest(BaseModel):
    loan_amount: float
    property_value: float
    loan_purpose: LoanPurposeType
    property_type: PropertyTypeOption
    occupancy: OccupancyTypeOption
    credit_score: int
    dti_ratio: float
    ltv: Optional[float] = None
    cltv: Optional[float] = None
    is_first_time_buyer: bool = False
    property_state: str
    property_county: Optional[str] = None
    has_subordinate_financing: bool = False
    subordinate_amount: float = 0


class EligibilityCheckRequest(BaseModel):
    scenario: LoanScenarioRequest
    check_agencies: List[AgencyType] = [AgencyType.CONVENTIONAL, AgencyType.FHA, AgencyType.VA]


class ProgramEligibility(BaseModel):
    agency: str
    is_eligible: bool
    max_loan_amount: Optional[float] = None
    max_ltv: Optional[float] = None
    max_dti: Optional[float] = None
    required_reserves: Optional[int] = None
    mi_required: bool = False
    mi_estimated: Optional[float] = None
    ineligibility_reasons: List[str] = []
    conditions: List[str] = []


class EligibilityCheckResponse(BaseModel):
    scenario_summary: Dict[str, Any]
    eligible_programs: List[ProgramEligibility]
    recommended_program: Optional[str] = None
    recommendation_reason: Optional[str] = None


# --- Condition Models ---

class ConditionTypeOption(str, Enum):
    PTD = "prior_to_docs"
    PTC = "prior_to_closing"
    PTF = "prior_to_funding"


class ConditionPriorityOption(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GenerateConditionsRequest(BaseModel):
    loan_id: Optional[str] = None
    loan_data: Dict[str, Any]
    income_issues: Optional[List[str]] = None
    asset_issues: Optional[List[str]] = None
    credit_issues: Optional[List[str]] = None
    property_issues: Optional[List[str]] = None
    include_standard_conditions: bool = True


class ConditionItem(BaseModel):
    condition_type: ConditionTypeOption
    category: str
    title: str
    description: str
    priority: ConditionPriorityOption
    required_documents: List[str] = []
    clearing_instructions: Optional[str] = None


class GenerateConditionsResponse(BaseModel):
    loan_id: Optional[str]
    total_conditions: int
    conditions_by_type: Dict[str, int]
    conditions: List[ConditionItem]


# --- Validation Models ---

class ValidationSeverityOption(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidateLoanRequest(BaseModel):
    loan_id: Optional[str] = None
    loan_data: Dict[str, Any]
    income_data: Optional[Dict[str, Any]] = None
    asset_data: Optional[Dict[str, Any]] = None
    credit_data: Optional[Dict[str, Any]] = None
    check_fraud_indicators: bool = True
    check_data_consistency: bool = True


class ValidationFinding(BaseModel):
    category: str
    severity: ValidationSeverityOption
    field: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None


class ValidateLoanResponse(BaseModel):
    loan_id: Optional[str]
    is_valid: bool
    total_findings: int
    critical_count: int
    error_count: int
    warning_count: int
    findings: List[ValidationFinding]
    fraud_indicators: List[Dict[str, Any]]
    data_quality_score: float


# --- Full Underwriting Models ---

class UnderwritingDecisionType(str, Enum):
    APPROVE = "approve"
    APPROVE_ELIGIBLE = "approve_eligible"
    REFER = "refer"
    SUSPEND = "suspend"
    DENY = "deny"
    COUNTER = "counter"


class RiskLevelType(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class FullUnderwritingRequest(BaseModel):
    loan_id: Optional[str] = None
    loan_data: Dict[str, Any] = Field(..., description="Core loan data including amount, property value, purpose, etc.")
    income_data: Optional[Dict[str, Any]] = Field(None, description="Income documentation and sources")
    asset_data: Optional[Dict[str, Any]] = Field(None, description="Asset accounts and large deposits")
    credit_data: Optional[Dict[str, Any]] = Field(None, description="Credit report data")
    generate_conditions: bool = True
    check_all_programs: bool = True


class FullUnderwritingResponse(BaseModel):
    loan_id: Optional[str]
    decision: UnderwritingDecisionType
    risk_level: RiskLevelType
    confidence_score: float
    analysis_timestamp: datetime

    # Calculated metrics
    qualifying_income: Optional[float] = None
    calculated_dti: Optional[float] = None
    calculated_ltv: Optional[float] = None
    reserves_months: Optional[int] = None

    # Approval details (if approved)
    approved_loan_amount: Optional[float] = None
    approved_program: Optional[str] = None

    # Issues
    denial_reasons: List[str] = []
    refer_reasons: List[str] = []
    critical_issues: List[str] = []

    # Conditions
    conditions_count: int = 0
    conditions_by_type: Dict[str, int] = {}

    # Detailed results
    income_analysis: Optional[Dict[str, Any]] = None
    asset_analysis: Optional[Dict[str, Any]] = None
    credit_analysis: Optional[Dict[str, Any]] = None
    eligibility_results: Optional[Dict[str, Any]] = None
    validation_results: Optional[Dict[str, Any]] = None


# =============================================================================
# LAZY ENGINE INITIALIZATION
# =============================================================================

_underwriting_engine = None
_income_calculator = None
_asset_analyzer = None
_credit_analyzer = None
_eligibility_engine = None
_condition_generator = None
_data_validator = None


def get_underwriting_engine():
    """Lazy load underwriting engine."""
    global _underwriting_engine
    if _underwriting_engine is None:
        try:
            from services.underwriting_engine import UnderwritingEngine
            _underwriting_engine = UnderwritingEngine()
        except ImportError as e:
            logger.error(f"Could not import UnderwritingEngine: {e}")
            raise HTTPException(status_code=503, detail="Underwriting engine not available")
    return _underwriting_engine


def get_income_calculator():
    """Lazy load income calculator."""
    global _income_calculator
    if _income_calculator is None:
        try:
            from services.underwriting_engine import IncomeCalculator
            _income_calculator = IncomeCalculator()
        except ImportError as e:
            logger.error(f"Could not import IncomeCalculator: {e}")
            raise HTTPException(status_code=503, detail="Income calculator not available")
    return _income_calculator


def get_asset_analyzer():
    """Lazy load asset analyzer."""
    global _asset_analyzer
    if _asset_analyzer is None:
        try:
            from services.underwriting_engine import AssetAnalyzer
            _asset_analyzer = AssetAnalyzer()
        except ImportError as e:
            logger.error(f"Could not import AssetAnalyzer: {e}")
            raise HTTPException(status_code=503, detail="Asset analyzer not available")
    return _asset_analyzer


def get_credit_analyzer():
    """Lazy load credit analyzer."""
    global _credit_analyzer
    if _credit_analyzer is None:
        try:
            from services.underwriting_engine import CreditAnalyzer
            _credit_analyzer = CreditAnalyzer()
        except ImportError as e:
            logger.error(f"Could not import CreditAnalyzer: {e}")
            raise HTTPException(status_code=503, detail="Credit analyzer not available")
    return _credit_analyzer


def get_eligibility_engine():
    """Lazy load eligibility engine."""
    global _eligibility_engine
    if _eligibility_engine is None:
        try:
            from services.underwriting_engine import EligibilityEngine
            _eligibility_engine = EligibilityEngine()
        except ImportError as e:
            logger.error(f"Could not import EligibilityEngine: {e}")
            raise HTTPException(status_code=503, detail="Eligibility engine not available")
    return _eligibility_engine


def get_condition_generator():
    """Lazy load condition generator."""
    global _condition_generator
    if _condition_generator is None:
        try:
            from services.underwriting_engine import ConditionGenerator
            _condition_generator = ConditionGenerator()
        except ImportError as e:
            logger.error(f"Could not import ConditionGenerator: {e}")
            raise HTTPException(status_code=503, detail="Condition generator not available")
    return _condition_generator


def get_data_validator():
    """Lazy load data validator."""
    global _data_validator
    if _data_validator is None:
        try:
            from services.underwriting_engine import LoanDataValidator
            _data_validator = LoanDataValidator()
        except ImportError as e:
            logger.error(f"Could not import LoanDataValidator: {e}")
            raise HTTPException(status_code=503, detail="Data validator not available")
    return _data_validator


# =============================================================================
# FULL UNDERWRITING ENDPOINT
# =============================================================================

@router.post("/underwrite", response_model=FullUnderwritingResponse)
async def run_automated_underwriting(
    request: FullUnderwritingRequest,
    db: Session = Depends(get_db),
):
    """
    Run full automated underwriting analysis.

    This is the main endpoint for automated loan underwriting. It performs:
    1. Data validation and fraud detection
    2. Income calculation per agency guidelines
    3. Asset analysis with large deposit review
    4. Credit/DTI analysis
    5. Program eligibility determination
    6. Condition generation
    7. Risk assessment and decision

    Returns a comprehensive underwriting result with decision, conditions, and analysis.
    """
    try:
        engine = get_underwriting_engine()

        result = engine.analyze_loan(
            loan_data=request.loan_data,
            income_data=request.income_data,
            asset_data=request.asset_data,
            credit_data=request.credit_data,
        )

        return FullUnderwritingResponse(
            loan_id=request.loan_id,
            decision=UnderwritingDecisionType(result.decision.value),
            risk_level=RiskLevelType(result.risk_level.value),
            confidence_score=result.confidence_score,
            analysis_timestamp=result.analysis_timestamp,
            qualifying_income=result.qualifying_income,
            calculated_dti=result.calculated_dti,
            calculated_ltv=result.calculated_ltv,
            reserves_months=result.reserves_months,
            approved_loan_amount=result.approved_loan_amount,
            approved_program=result.approved_program,
            denial_reasons=result.denial_reasons,
            refer_reasons=result.refer_reasons,
            critical_issues=result.critical_issues,
            conditions_count=len(result.conditions),
            conditions_by_type=result.conditions_by_type,
            income_analysis=result.income_result,
            asset_analysis=result.asset_result,
            credit_analysis=result.credit_result,
            eligibility_results=result.eligibility_result,
            validation_results=result.validation_result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Automated underwriting failed: {e}")
        raise HTTPException(status_code=500, detail="Underwriting analysis failed")


# =============================================================================
# INCOME CALCULATION ENDPOINT
# =============================================================================

@router.post("/income/calculate", response_model=IncomeCalculationResponse)
async def calculate_qualifying_income(
    request: IncomeCalculationRequest,
    db: Session = Depends(get_db),
):
    """
    Calculate qualifying income per agency guidelines.

    Supports:
    - W-2 income (base, overtime, bonus, commission)
    - Self-employment income (Schedule C, K-1, S-Corp)
    - Variable income with trending
    - Rental income
    - Non-employment income (SS, pension, alimony, etc.)
    """
    try:
        calculator = get_income_calculator()

        # Convert request to engine format
        income_sources = []
        for source in request.income_sources:
            income_sources.append({
                "type": source.type.value,
                "employer_name": source.employer_name,
                "annual_amount": source.annual_amount,
                "monthly_amount": source.monthly_amount,
                "years_employed": source.years_employed,
                "months_employed": source.months_employed,
                "ytd_earnings": source.ytd_earnings,
                "prior_year_income": source.prior_year_income,
                "two_years_prior_income": source.two_years_prior_income,
                "is_variable": source.is_variable,
                "documentation": source.documentation,
            })

        result = calculator.calculate_qualifying_income(
            income_sources=income_sources,
            agency=request.agency.value,
            apply_trending=request.calculate_trending,
        )

        return IncomeCalculationResponse(
            total_qualifying_income=result.total_annual_income,
            monthly_qualifying_income=result.total_monthly_income,
            income_breakdown=[item.to_dict() for item in result.income_items],
            trending_applied=result.trending_applied,
            issues=result.issues,
            recommendations=result.recommendations,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Income calculation failed: {e}")
        raise HTTPException(status_code=500, detail="Income calculation failed")


# =============================================================================
# ASSET ANALYSIS ENDPOINT
# =============================================================================

@router.post("/assets/analyze", response_model=AssetAnalysisResponse)
async def analyze_assets(
    request: AssetAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze assets for loan qualification.

    Includes:
    - Liquid asset calculation
    - Large deposit detection and sourcing requirements
    - Reserves calculation
    - Gift fund handling
    - Retirement asset discounting
    """
    try:
        analyzer = get_asset_analyzer()

        # Convert request to engine format
        accounts = []
        for acct in request.accounts:
            accounts.append({
                "type": acct.type.value,
                "institution_name": acct.institution_name,
                "account_number_last4": acct.account_number_last4,
                "current_balance": acct.current_balance,
                "two_month_avg_balance": acct.two_month_avg_balance,
                "statement_date": acct.statement_date.isoformat() if acct.statement_date else None,
                "is_joint": acct.is_joint,
                "owner": acct.owner,
            })

        large_deposits = None
        if request.large_deposits:
            large_deposits = [
                {
                    "date": dep.date.isoformat(),
                    "amount": dep.amount,
                    "description": dep.description,
                    "source_documented": dep.source_documented,
                    "source_explanation": dep.source_explanation,
                }
                for dep in request.large_deposits
            ]

        result = analyzer.analyze_assets(
            accounts=accounts,
            large_deposits=large_deposits,
            loan_amount=request.loan_amount,
            closing_costs=request.closing_costs,
            down_payment=request.down_payment,
            reserves_required_months=request.reserves_required_months,
        )

        return AssetAnalysisResponse(
            total_liquid_assets=result.total_liquid_assets,
            total_retirement_assets=result.total_retirement_assets,
            total_verifiable_assets=result.total_verifiable_assets,
            funds_to_close=result.funds_to_close,
            reserves_available=result.reserves_available,
            reserves_months=result.reserves_months,
            large_deposits_to_source=[dep.to_dict() for dep in result.large_deposits_requiring_source],
            asset_issues=result.issues,
            sufficient_assets=result.sufficient_assets,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Asset analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Asset analysis failed")


# =============================================================================
# CREDIT ANALYSIS ENDPOINT
# =============================================================================

@router.post("/credit/analyze", response_model=CreditAnalysisResponse)
async def analyze_credit(
    request: CreditAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze credit for loan qualification.

    Includes:
    - DTI calculation (front-end and back-end)
    - Credit event waiting period verification
    - Derogatory item analysis
    - Credit grade assignment
    - Program-specific limits check
    """
    try:
        analyzer = get_credit_analyzer()

        # Convert tradelines
        tradelines = []
        for tl in request.tradelines:
            tradelines.append({
                "creditor_name": tl.creditor_name,
                "account_type": tl.account_type,
                "balance": tl.balance,
                "monthly_payment": tl.monthly_payment,
                "high_credit": tl.high_credit,
                "credit_limit": tl.credit_limit,
                "date_opened": tl.date_opened.isoformat() if tl.date_opened else None,
                "status": tl.status,
                "late_30_count": tl.late_30_count,
                "late_60_count": tl.late_60_count,
                "late_90_count": tl.late_90_count,
            })

        # Convert credit events
        credit_events = None
        if request.credit_events:
            credit_events = [
                {
                    "event_type": evt.event_type,
                    "date_filed": evt.date_filed.isoformat() if evt.date_filed else None,
                    "date_discharged": evt.date_discharged.isoformat() if evt.date_discharged else None,
                    "chapter": evt.chapter,
                }
                for evt in request.credit_events
            ]

        result = analyzer.analyze_credit(
            credit_score=request.credit_score,
            tradelines=tradelines,
            credit_events=credit_events,
            proposed_housing_payment=request.proposed_housing_payment,
            agency=request.agency.value,
        )

        return CreditAnalysisResponse(
            credit_score=result.credit_score,
            representative_score=result.representative_score,
            total_monthly_obligations=result.total_monthly_obligations,
            housing_expense=result.housing_expense,
            front_end_dti=result.front_end_dti,
            back_end_dti=result.back_end_dti,
            credit_grade=result.credit_grade,
            derogatory_items=[item.to_dict() for item in result.derogatory_items],
            waiting_periods_met=result.waiting_periods_met,
            credit_issues=result.issues,
            recommendations=result.recommendations,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Credit analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Credit analysis failed")


# =============================================================================
# ELIGIBILITY CHECK ENDPOINT
# =============================================================================

@router.post("/eligibility/check", response_model=EligibilityCheckResponse)
async def check_loan_eligibility(
    request: EligibilityCheckRequest,
    db: Session = Depends(get_db),
):
    """
    Check loan eligibility across multiple programs.

    Checks:
    - Conventional (Fannie Mae / Freddie Mac)
    - FHA
    - VA
    - USDA (if applicable)

    Returns eligibility status, limits, and requirements for each program.
    """
    try:
        engine = get_eligibility_engine()

        scenario = {
            "loan_amount": request.scenario.loan_amount,
            "property_value": request.scenario.property_value,
            "loan_purpose": request.scenario.loan_purpose.value,
            "property_type": request.scenario.property_type.value,
            "occupancy": request.scenario.occupancy.value,
            "credit_score": request.scenario.credit_score,
            "dti_ratio": request.scenario.dti_ratio,
            "ltv": request.scenario.ltv or (request.scenario.loan_amount / request.scenario.property_value * 100),
            "cltv": request.scenario.cltv,
            "is_first_time_buyer": request.scenario.is_first_time_buyer,
            "property_state": request.scenario.property_state,
            "property_county": request.scenario.property_county,
            "has_subordinate_financing": request.scenario.has_subordinate_financing,
            "subordinate_amount": request.scenario.subordinate_amount,
        }

        agencies = [a.value for a in request.check_agencies]

        result = engine.check_eligibility(
            scenario=scenario,
            agencies=agencies,
        )

        eligible_programs = []
        for prog in result.program_results:
            eligible_programs.append(ProgramEligibility(
                agency=prog.agency,
                is_eligible=prog.is_eligible,
                max_loan_amount=prog.max_loan_amount,
                max_ltv=prog.max_ltv,
                max_dti=prog.max_dti,
                required_reserves=prog.required_reserves,
                mi_required=prog.mi_required,
                mi_estimated=prog.mi_estimated,
                ineligibility_reasons=prog.ineligibility_reasons,
                conditions=prog.conditions,
            ))

        return EligibilityCheckResponse(
            scenario_summary=scenario,
            eligible_programs=eligible_programs,
            recommended_program=result.recommended_program,
            recommendation_reason=result.recommendation_reason,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Eligibility check failed: {e}")
        raise HTTPException(status_code=500, detail="Eligibility check failed")


# =============================================================================
# CONDITION GENERATION ENDPOINT
# =============================================================================

@router.post("/conditions/generate", response_model=GenerateConditionsResponse)
async def generate_conditions(
    request: GenerateConditionsRequest,
    db: Session = Depends(get_db),
):
    """
    Generate underwriting conditions for a loan.

    Creates conditions based on:
    - Loan characteristics
    - Income issues requiring documentation
    - Asset verification needs
    - Credit items to address
    - Property concerns

    Conditions are categorized as PTD (Prior to Docs), PTC (Prior to Closing), or PTF (Prior to Funding).
    """
    try:
        generator = get_condition_generator()

        result = generator.generate_conditions(
            loan_data=request.loan_data,
            income_issues=request.income_issues,
            asset_issues=request.asset_issues,
            credit_issues=request.credit_issues,
            property_issues=request.property_issues,
            include_standard=request.include_standard_conditions,
        )

        conditions = []
        for cond in result.conditions:
            conditions.append(ConditionItem(
                condition_type=ConditionTypeOption(cond.condition_type.value),
                category=cond.category,
                title=cond.title,
                description=cond.description,
                priority=ConditionPriorityOption(cond.priority.value),
                required_documents=cond.required_documents,
                clearing_instructions=cond.clearing_instructions,
            ))

        return GenerateConditionsResponse(
            loan_id=request.loan_id,
            total_conditions=len(conditions),
            conditions_by_type=result.conditions_by_type,
            conditions=conditions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Condition generation failed: {e}")
        raise HTTPException(status_code=500, detail="Condition generation failed")


# =============================================================================
# LOAN VALIDATION ENDPOINT
# =============================================================================

@router.post("/validate", response_model=ValidateLoanResponse)
async def validate_loan_file(
    request: ValidateLoanRequest,
    db: Session = Depends(get_db),
):
    """
    Validate loan file data for completeness and consistency.

    Checks:
    - Required field presence
    - Data consistency across documents
    - Fraud indicators
    - Regulatory compliance items
    - Document matching
    """
    try:
        validator = get_data_validator()

        result = validator.validate_loan(
            loan_data=request.loan_data,
            income_data=request.income_data,
            asset_data=request.asset_data,
            credit_data=request.credit_data,
            check_fraud=request.check_fraud_indicators,
            check_consistency=request.check_data_consistency,
        )

        findings = []
        for finding in result.findings:
            findings.append(ValidationFinding(
                category=finding.category,
                severity=ValidationSeverityOption(finding.severity.value),
                field=finding.field,
                message=finding.message,
                details=finding.details,
                recommendation=finding.recommendation,
            ))

        return ValidateLoanResponse(
            loan_id=request.loan_id,
            is_valid=result.is_valid,
            total_findings=len(findings),
            critical_count=result.critical_count,
            error_count=result.error_count,
            warning_count=result.warning_count,
            findings=findings,
            fraud_indicators=result.fraud_indicators,
            data_quality_score=result.data_quality_score,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Loan validation failed: {e}")
        raise HTTPException(status_code=500, detail="Loan validation failed")


# =============================================================================
# QUICK ANALYSIS ENDPOINTS
# =============================================================================

@router.post("/quick/dti")
async def quick_dti_calculation(
    monthly_income: float = Query(..., description="Total monthly qualifying income"),
    proposed_housing_payment: float = Query(..., description="PITI payment"),
    monthly_debts: float = Query(..., description="Total monthly debt obligations"),
):
    """Quick DTI calculation without full analysis."""
    front_end = round((proposed_housing_payment / monthly_income) * 100, 2) if monthly_income > 0 else 0
    back_end = round(((proposed_housing_payment + monthly_debts) / monthly_income) * 100, 2) if monthly_income > 0 else 0

    return {
        "monthly_income": monthly_income,
        "housing_payment": proposed_housing_payment,
        "monthly_debts": monthly_debts,
        "front_end_dti": front_end,
        "back_end_dti": back_end,
        "conventional_max_dti": 50.0,
        "fha_max_dti": 56.9,
        "meets_conventional": back_end <= 50.0,
        "meets_fha": back_end <= 56.9,
    }


@router.post("/quick/ltv")
async def quick_ltv_calculation(
    loan_amount: float = Query(..., description="Loan amount"),
    property_value: float = Query(..., description="Property value or purchase price"),
    subordinate_amount: float = Query(0, description="Subordinate financing amount"),
):
    """Quick LTV/CLTV calculation without full analysis."""
    ltv = round((loan_amount / property_value) * 100, 2) if property_value > 0 else 0
    cltv = round(((loan_amount + subordinate_amount) / property_value) * 100, 2) if property_value > 0 else 0

    return {
        "loan_amount": loan_amount,
        "property_value": property_value,
        "subordinate_amount": subordinate_amount,
        "ltv": ltv,
        "cltv": cltv,
        "mi_required": ltv > 80,
        "max_conventional_ltv": 97.0,
        "max_fha_ltv": 96.5,
        "max_va_ltv": 100.0,
    }


@router.get("/health")
async def underwriting_engine_health():
    """Check health status of underwriting engine components."""
    status = {
        "status": "healthy",
        "components": {},
        "timestamp": datetime.now().isoformat(),
    }

    components = [
        ("underwriting_engine", get_underwriting_engine),
        ("income_calculator", get_income_calculator),
        ("asset_analyzer", get_asset_analyzer),
        ("credit_analyzer", get_credit_analyzer),
        ("eligibility_engine", get_eligibility_engine),
        ("condition_generator", get_condition_generator),
        ("data_validator", get_data_validator),
    ]

    all_healthy = True
    for name, getter in components:
        try:
            getter()
            status["components"][name] = "available"
        except Exception as e:
            status["components"][name] = "unavailable"
            all_healthy = False

    if not all_healthy:
        status["status"] = "degraded"

    return status
