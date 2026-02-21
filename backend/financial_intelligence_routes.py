"""
Financial Intelligence API Routes
Perennia AI - IBMA

Executive-level financial analysis endpoints answering the 20 key questions
mortgage executives need answered for strategic decision-making.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.financial_intelligence_service import FinancialIntelligenceService

logger = logging.getLogger(__name__)


def _get_current_user_dep():
    """Lazy import to avoid circular imports."""
    import main
    return main.get_current_user


router = APIRouter(
    prefix="/api/v1/financial-intelligence",
    tags=["Financial Intelligence"],
    dependencies=[Depends(_get_current_user_dep())],
)


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def parse_month(month_str: Optional[str]) -> Optional[date]:
    """Parse month string in YYYY-MM format."""
    if not month_str:
        return None
    try:
        return datetime.strptime(month_str, "%Y-%m").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid month format. Use YYYY-MM (e.g., 2024-01)"
        )


# ================================================================
# PYDANTIC MODELS - Request Bodies
# ================================================================

class LoanSaleCreate(BaseModel):
    """Request model for recording a loan sale to secondary market."""
    loan_id: Optional[int] = Field(None, description="Reference to loan record")
    loan_number: str = Field(..., description="Loan number")
    sale_date: date = Field(..., description="Date of sale")
    sale_price: float = Field(..., gt=0, description="Sale price in dollars")
    original_amount: float = Field(..., gt=0, description="Original loan amount")
    gain_on_sale: Optional[float] = Field(None, description="Gain on sale amount")
    gain_on_sale_bps: Optional[float] = Field(None, description="Gain on sale in basis points")
    investor: Optional[str] = Field(None, description="Investor/purchaser name")
    product_type: Optional[str] = Field(None, description="Loan product type")
    note_rate: Optional[float] = Field(None, description="Note rate")
    servicing_retained: bool = Field(False, description="Whether servicing was retained")


class CashPositionCreate(BaseModel):
    """Request model for updating daily cash position."""
    position_date: date = Field(..., description="Date of cash position")
    operating_cash: float = Field(..., description="Operating cash balance")
    warehouse_cash: Optional[float] = Field(None, description="Cash in warehouse lines")
    restricted_cash: Optional[float] = Field(None, description="Restricted cash balance")
    total_cash: float = Field(..., description="Total cash position")
    daily_change: Optional[float] = Field(None, description="Change from previous day")
    notes: Optional[str] = Field(None, max_length=500, description="Additional notes")


class WarehouseLineCreate(BaseModel):
    """Request model for adding/updating warehouse line configuration."""
    line_name: str = Field(..., min_length=1, max_length=100, description="Warehouse line name")
    lender: str = Field(..., min_length=1, max_length=100, description="Lender name")
    total_capacity: float = Field(..., gt=0, description="Total line capacity")
    current_usage: float = Field(0, ge=0, description="Current usage amount")
    available_capacity: Optional[float] = Field(None, description="Available capacity")
    advance_rate: float = Field(0.98, ge=0, le=1, description="Advance rate (0-1)")
    interest_rate: Optional[float] = Field(None, description="Current interest rate")
    expiration_date: Optional[date] = Field(None, description="Line expiration date")
    is_active: bool = Field(True, description="Whether line is active")


class MSRValuationCreate(BaseModel):
    """Request model for updating MSR portfolio valuation."""
    valuation_date: date = Field(..., description="Date of valuation")
    total_upb: float = Field(..., ge=0, description="Total unpaid principal balance")
    msr_value: float = Field(..., description="MSR portfolio value")
    msr_multiple: Optional[float] = Field(None, description="MSR multiple")
    weighted_avg_note_rate: Optional[float] = Field(None, description="Weighted average note rate")
    weighted_avg_servicing_fee: Optional[float] = Field(None, description="Weighted avg servicing fee in bps")
    loan_count: Optional[int] = Field(None, ge=0, description="Number of loans in portfolio")
    prepayment_speed: Optional[float] = Field(None, description="Current prepayment speed (CPR)")


class ComplianceRiskCreate(BaseModel):
    """Request model for adding a compliance/regulatory risk item."""
    risk_name: str = Field(..., min_length=1, max_length=200, description="Risk name/title")
    risk_category: str = Field(..., description="Category: regulatory, operational, legal, financial")
    severity: str = Field(..., description="Severity: low, medium, high, critical")
    description: str = Field(..., description="Detailed description of the risk")
    potential_impact: Optional[float] = Field(None, description="Potential financial impact")
    mitigation_status: str = Field("identified", description="Status: identified, mitigating, resolved")
    mitigation_plan: Optional[str] = Field(None, description="Mitigation plan details")
    due_date: Optional[date] = Field(None, description="Due date for resolution")
    owner: Optional[str] = Field(None, description="Person responsible for mitigation")


class LostDealCreate(BaseModel):
    """Request model for recording a deal lost to competitor."""
    loan_amount: float = Field(..., gt=0, description="Loan amount")
    lost_date: date = Field(..., description="Date deal was lost")
    competitor: Optional[str] = Field(None, description="Competitor who won the deal")
    reason: str = Field(..., description="Primary reason for loss")
    rate_difference_bps: Optional[float] = Field(None, description="Rate difference in bps")
    product_type: Optional[str] = Field(None, description="Loan product type")
    borrower_type: Optional[str] = Field(None, description="Borrower type: purchase, refinance")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")


# ================================================================
# PYDANTIC MODELS - Responses
# ================================================================

class SuccessResponse(BaseModel):
    """Standard success response."""
    success: bool = Field(True)
    message: str
    id: Optional[int] = Field(None, description="ID of created record")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    generated_at: str


# ================================================================
# EXECUTIVE DASHBOARD ENDPOINT
# ================================================================

@router.get("/executive-dashboard")
async def get_executive_dashboard(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    Get complete executive dashboard with all 20 key metrics.

    **Answers all executive questions in one API call:**
    - Q1: Gain on sale margins
    - Q2: Hedge effectiveness
    - Q3: Product profitability
    - Q4: Cost per loan
    - Q5: Cash runway
    - Q6: Break-even analysis
    - Q7: Warehouse efficiency
    - Q8: Rate exposure
    - Q9: Branch profitability
    - Q10: MSR status
    - Q11: Pricing competitiveness
    - Q12: Cash forecast
    - Q13: Liquidity analysis
    - Q14: Capital requirements
    - Q15: Compliance risks
    - Q16: Tech ROI
    - Q17-19: Operational losses
    - Q20: Investment recommendations
    """
    try:
        org_id = get_organization_id(request)
        service = FinancialIntelligenceService(db, org_id)
        month_date = parse_month(month)
        return service.get_executive_dashboard(month_date)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Executive dashboard error: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "message": "Financial intelligence data unavailable",
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


# ================================================================
# INDIVIDUAL METRIC ENDPOINTS (Q1-Q20)
# ================================================================

@router.get("/gain-on-sale")
async def get_gain_on_sale(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q1: Gain on Sale Analysis**

    Current gain-on-sale margin vs last month and last year.
    Critical for understanding pricing power and market conditions.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_gain_on_sale_metrics(month_date)


@router.get("/hedge-analysis")
async def get_hedge_analysis(request: Request, db: Session = Depends(get_db)):
    """
    **Q2: Hedge Effectiveness**

    Analysis of hedge effectiveness and rate risk coverage.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_hedge_analysis()


@router.get("/product-profitability")
async def get_product_profitability(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q3: Product Profitability**

    Profitability breakdown by loan product type (Conventional, FHA, VA, etc.)
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_product_profitability(month_date)


@router.get("/cost-per-loan")
async def get_cost_per_loan(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q4: True Cost Per Loan**

    Full breakdown of cost per funded loan including:
    - Labor costs
    - Tech stack costs
    - Fulfillment costs
    - Overhead allocation
    """
    try:
        org_id = get_organization_id(request)
        service = FinancialIntelligenceService(db, org_id)
        month_date = parse_month(month)
        return service.get_true_cost_per_loan(month_date)
    except Exception as e:
        logger.error(f"Cost per loan error: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "total_cost_per_loan": 0,
            "breakdown": {"labor": 0, "tech_stack": 0, "fulfillment": 0, "overhead": 0},
            "loans_closed": 0,
            "total_expenses": 0
        }


@router.get("/cash-runway")
async def get_cash_runway(request: Request, db: Session = Depends(get_db)):
    """
    **Q5: Cash Runway**

    Months of operating cash runway at current burn rate.
    Critical for financial planning and survival analysis.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_cash_runway()


@router.get("/break-even")
async def get_break_even(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q6: Break-Even Analysis**

    Break-even production volume at current margins.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_break_even_analysis(month_date)


@router.get("/warehouse-efficiency")
async def get_warehouse_efficiency(request: Request, db: Session = Depends(get_db)):
    """
    **Q7: Warehouse Efficiency**

    Warehouse line optimization and turn-time analysis.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_warehouse_efficiency()


@router.get("/rate-exposure")
async def get_rate_exposure(request: Request, db: Session = Depends(get_db)):
    """
    **Q8: Rate Exposure**

    Exposure to rate movements (Fed cuts/raises).
    Scenario analysis for rate changes.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_rate_exposure()


@router.get("/branch-profitability")
async def get_branch_profitability(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q9: Branch Profitability**

    Profitability breakdown by branch, team, or region.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_branch_profitability(month_date)


@router.get("/msr-status")
async def get_msr_status(request: Request, db: Session = Depends(get_db)):
    """
    **Q10: MSR Status**

    MSR portfolio value, performance, and status.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_msr_status()


@router.get("/pricing-analysis")
async def get_pricing_analysis(request: Request, db: Session = Depends(get_db)):
    """
    **Q11: Pricing Analysis**

    Pricing competitiveness and lost deal analysis.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_pricing_analysis()


@router.get("/cash-forecast")
async def get_cash_forecast(request: Request, db: Session = Depends(get_db)):
    """
    **Q12: Cash Forecast**

    Cash flow forecast for 30, 60, 90 days.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_cash_forecast()


@router.get("/liquidity")
async def get_liquidity(request: Request, db: Session = Depends(get_db)):
    """
    **Q13: Liquidity Analysis**

    Liquidity analysis for potential volume increases.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_liquidity_analysis()


@router.get("/capital")
async def get_capital(request: Request, db: Session = Depends(get_db)):
    """
    **Q14: Capital Requirements**

    Capital requirements for production goals.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_capital_analysis()


@router.get("/compliance-risks")
async def get_compliance_risks(request: Request, db: Session = Depends(get_db)):
    """
    **Q15: Compliance Risks**

    Compliance and regulatory risk exposure assessment.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_compliance_exposure()


@router.get("/tech-roi")
async def get_tech_roi(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q16: Technology ROI**

    ROI analysis on technology investments.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_tech_roi(month_date)


@router.get("/operational-losses")
async def get_operational_losses(request: Request, db: Session = Depends(get_db)):
    """
    **Q17-19: Operational Losses**

    Losses from:
    - Pipeline bottlenecks
    - Lock extensions
    - Pricing concessions
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_operational_losses()


@router.get("/investment-recommendations")
async def get_investment_recommendations(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    **Q20: Investment Recommendations**

    AI-powered investment and cost-cutting recommendations.
    """
    org_id = get_organization_id(request)
    service = FinancialIntelligenceService(db, org_id)
    month_date = parse_month(month)
    return service.get_investment_recommendations(month_date)


# ================================================================
# DATA ENTRY ENDPOINTS
# ================================================================

@router.post("/loan-sales", response_model=SuccessResponse)
async def create_loan_sale(
    request: Request,
    loan_sale: LoanSaleCreate,
    db: Session = Depends(get_db)
):
    """
    Record a loan sale to secondary market.

    Used to track gain-on-sale metrics and investor relationships.
    """
    try:
        from models.financial_intelligence import LoanSale

        org_id = get_organization_id(request)

        sale = LoanSale(
            organization_id=org_id,
            **loan_sale.model_dump()
        )
        db.add(sale)
        db.commit()
        db.refresh(sale)

        logger.info(f"Loan sale recorded: {sale.id}")
        return SuccessResponse(
            success=True,
            message="Loan sale recorded successfully",
            id=sale.id
        )

    except Exception as e:
        logger.error(f"Error recording loan sale: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cash-position", response_model=SuccessResponse)
async def update_cash_position(
    request: Request,
    position: CashPositionCreate,
    db: Session = Depends(get_db)
):
    """
    Update daily cash position.

    Critical for cash runway and liquidity analysis.
    """
    try:
        from models.financial_intelligence import CashPosition

        org_id = get_organization_id(request)

        cash_position = CashPosition(
            organization_id=org_id,
            **position.model_dump()
        )
        db.add(cash_position)
        db.commit()

        logger.info(f"Cash position updated for {position.position_date}")
        return SuccessResponse(
            success=True,
            message="Cash position updated successfully"
        )

    except Exception as e:
        logger.error(f"Error updating cash position: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/warehouse-lines", response_model=SuccessResponse)
async def create_warehouse_line(
    request: Request,
    line: WarehouseLineCreate,
    db: Session = Depends(get_db)
):
    """
    Add or update warehouse line configuration.

    Used for warehouse efficiency and capacity analysis.
    """
    try:
        from models.financial_intelligence import WarehouseLine

        org_id = get_organization_id(request)

        warehouse_line = WarehouseLine(
            organization_id=org_id,
            **line.model_dump()
        )
        db.add(warehouse_line)
        db.commit()
        db.refresh(warehouse_line)

        logger.info(f"Warehouse line created: {warehouse_line.id}")
        return SuccessResponse(
            success=True,
            message="Warehouse line created successfully",
            id=warehouse_line.id
        )

    except Exception as e:
        logger.error(f"Error creating warehouse line: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/msr-valuation", response_model=SuccessResponse)
async def update_msr_valuation(
    request: Request,
    valuation: MSRValuationCreate,
    db: Session = Depends(get_db)
):
    """
    Update MSR portfolio valuation.

    Used for MSR status reporting and asset tracking.
    """
    try:
        from models.financial_intelligence import MSRPortfolio

        org_id = get_organization_id(request)

        msr_valuation = MSRPortfolio(
            organization_id=org_id,
            **valuation.model_dump()
        )
        db.add(msr_valuation)
        db.commit()

        logger.info(f"MSR valuation updated for {valuation.valuation_date}")
        return SuccessResponse(
            success=True,
            message="MSR valuation updated successfully"
        )

    except Exception as e:
        logger.error(f"Error updating MSR valuation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/compliance-risk", response_model=SuccessResponse)
async def add_compliance_risk(
    request: Request,
    risk: ComplianceRiskCreate,
    db: Session = Depends(get_db)
):
    """
    Add a compliance or regulatory risk item.

    Used for compliance risk tracking and mitigation planning.
    """
    try:
        from models.financial_intelligence import ComplianceRisk

        org_id = get_organization_id(request)

        compliance_risk = ComplianceRisk(
            organization_id=org_id,
            **risk.model_dump()
        )
        db.add(compliance_risk)
        db.commit()
        db.refresh(compliance_risk)

        logger.info(f"Compliance risk recorded: {compliance_risk.id}")
        return SuccessResponse(
            success=True,
            message="Compliance risk recorded successfully",
            id=compliance_risk.id
        )

    except Exception as e:
        logger.error(f"Error recording compliance risk: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/lost-deal", response_model=SuccessResponse)
async def record_lost_deal(
    request: Request,
    deal: LostDealCreate,
    db: Session = Depends(get_db)
):
    """
    Record a deal lost to competitor.

    Used for pricing competitiveness analysis and market intelligence.
    """
    try:
        from models.financial_intelligence import LostDeal

        org_id = get_organization_id(request)

        lost_deal = LostDeal(
            organization_id=org_id,
            **deal.model_dump()
        )
        db.add(lost_deal)
        db.commit()

        logger.info(f"Lost deal recorded: {deal.reason}")
        return SuccessResponse(
            success=True,
            message="Lost deal recorded successfully"
        )

    except Exception as e:
        logger.error(f"Error recording lost deal: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================================================
# HEALTH CHECK
# ================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint for financial intelligence service."""
    return {
        "status": "healthy",
        "service": "financial-intelligence",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
