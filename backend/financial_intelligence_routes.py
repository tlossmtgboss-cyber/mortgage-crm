"""
Phase 3: Financial Intelligence API Routes

Executive-level financial analysis endpoints answering the 20 key questions.
"""

import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db

from services.financial_intelligence_service import FinancialIntelligenceService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/financial-intelligence", tags=["financial-intelligence"])


def get_organization_id(db: Session) -> int:
    return 1


# ============ Executive Dashboard ============

@router.get("/executive-dashboard")
async def get_executive_dashboard(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    Get complete executive dashboard with all 20 key metrics.
    Answers all executive questions in one call.
    """
    try:
        org_id = get_organization_id(db)
        service = FinancialIntelligenceService(db, org_id)

        month_date = None
        if month:
            try:
                month_date = datetime.strptime(month, "%Y-%m").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid month format")

        return service.get_executive_dashboard(month_date)
    except Exception as e:
        logger.error(f"Executive dashboard error: {e}", exc_info=True)
        # Return graceful default with error message
        return {
            "error": str(e),
            "message": "Financial intelligence data unavailable",
            "generated_at": datetime.utcnow().isoformat()
        }


# ============ Individual Question Endpoints ============

@router.get("/gain-on-sale")
async def get_gain_on_sale(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q1: Current gain-on-sale margin vs last month and last year."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_gain_on_sale_metrics(month_date)


@router.get("/hedge-analysis")
async def get_hedge_analysis(db: Session = Depends(get_db)):
    """Q2: Hedge effectiveness and rate risk coverage."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_hedge_analysis()


@router.get("/product-profitability")
async def get_product_profitability(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q3: Profitability by loan product type."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_product_profitability(month_date)


@router.get("/cost-per-loan")
async def get_cost_per_loan(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q4: True cost per funded loan with full breakdown."""
    try:
        org_id = get_organization_id(db)
        service = FinancialIntelligenceService(db, org_id)

        month_date = datetime.strptime(month, "%Y-%m").date() if month else None
        return service.get_true_cost_per_loan(month_date)
    except Exception as e:
        logger.error(f"Cost per loan error: {e}", exc_info=True)
        return {
            "error": str(e),
            "total_cost_per_loan": 0,
            "breakdown": {"labor": 0, "tech_stack": 0, "fulfillment": 0, "overhead": 0},
            "loans_closed": 0,
            "total_expenses": 0
        }


@router.get("/cash-runway")
async def get_cash_runway(db: Session = Depends(get_db)):
    """Q5: Months of operating cash runway at current burn rate."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_cash_runway()


@router.get("/break-even")
async def get_break_even(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q6: Break-even production volume at current margins."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_break_even_analysis(month_date)


@router.get("/warehouse-efficiency")
async def get_warehouse_efficiency(db: Session = Depends(get_db)):
    """Q7: Warehouse line optimization and turn-time analysis."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_warehouse_efficiency()


@router.get("/rate-exposure")
async def get_rate_exposure(db: Session = Depends(get_db)):
    """Q8: Exposure to rate movements (Fed cuts/raises)."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_rate_exposure()


@router.get("/branch-profitability")
async def get_branch_profitability(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q9: Profitability by branch, team, or region."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_branch_profitability(month_date)


@router.get("/msr-status")
async def get_msr_status(db: Session = Depends(get_db)):
    """Q10: MSR portfolio value and status."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_msr_status()


@router.get("/pricing-analysis")
async def get_pricing_analysis(db: Session = Depends(get_db)):
    """Q11: Pricing competitiveness and lost deal analysis."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_pricing_analysis()


@router.get("/cash-forecast")
async def get_cash_forecast(db: Session = Depends(get_db)):
    """Q12: Cash flow forecast for 30, 60, 90 days."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_cash_forecast()


@router.get("/liquidity")
async def get_liquidity(db: Session = Depends(get_db)):
    """Q13: Liquidity analysis for volume increases."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_liquidity_analysis()


@router.get("/capital")
async def get_capital(db: Session = Depends(get_db)):
    """Q14: Capital requirements for production goals."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_capital_analysis()


@router.get("/compliance-risks")
async def get_compliance_risks(db: Session = Depends(get_db)):
    """Q15: Compliance and regulatory risk exposure."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_compliance_exposure()


@router.get("/tech-roi")
async def get_tech_roi(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q16: ROI on technology investments."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_tech_roi(month_date)


@router.get("/operational-losses")
async def get_operational_losses(db: Session = Depends(get_db)):
    """Q17-19: Losses from bottlenecks, lock extensions, and concessions."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)
    return service.get_operational_losses()


@router.get("/investment-recommendations")
async def get_investment_recommendations(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Q20: AI-powered investment and cost-cutting recommendations."""
    org_id = get_organization_id(db)
    service = FinancialIntelligenceService(db, org_id)

    month_date = datetime.strptime(month, "%Y-%m").date() if month else None
    return service.get_investment_recommendations(month_date)


# ============ Data Entry Endpoints ============

@router.post("/loan-sales")
async def create_loan_sale(
    loan_data: dict,
    db: Session = Depends(get_db)
):
    """Record a loan sale to secondary market."""
    from models.financial_intelligence import LoanSale

    org_id = get_organization_id(db)

    sale = LoanSale(
        organization_id=org_id,
        **loan_data
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)

    return {"id": sale.id, "message": "Loan sale recorded"}


@router.post("/cash-position")
async def update_cash_position(
    position_data: dict,
    db: Session = Depends(get_db)
):
    """Update daily cash position."""
    from models.financial_intelligence import CashPosition

    org_id = get_organization_id(db)

    position = CashPosition(
        organization_id=org_id,
        **position_data
    )
    db.add(position)
    db.commit()

    return {"message": "Cash position updated"}


@router.post("/warehouse-lines")
async def create_warehouse_line(
    line_data: dict,
    db: Session = Depends(get_db)
):
    """Add or update warehouse line configuration."""
    from models.financial_intelligence import WarehouseLine

    org_id = get_organization_id(db)

    line = WarehouseLine(
        organization_id=org_id,
        **line_data
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return {"id": line.id, "message": "Warehouse line created"}


@router.post("/msr-valuation")
async def update_msr_valuation(
    valuation_data: dict,
    db: Session = Depends(get_db)
):
    """Update MSR portfolio valuation."""
    from models.financial_intelligence import MSRPortfolio

    org_id = get_organization_id(db)

    valuation = MSRPortfolio(
        organization_id=org_id,
        **valuation_data
    )
    db.add(valuation)
    db.commit()

    return {"message": "MSR valuation updated"}


@router.post("/compliance-risk")
async def add_compliance_risk(
    risk_data: dict,
    db: Session = Depends(get_db)
):
    """Add a compliance or regulatory risk item."""
    from models.financial_intelligence import ComplianceRisk

    org_id = get_organization_id(db)

    risk = ComplianceRisk(
        organization_id=org_id,
        **risk_data
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)

    return {"id": risk.id, "message": "Compliance risk recorded"}


@router.post("/lost-deal")
async def record_lost_deal(
    deal_data: dict,
    db: Session = Depends(get_db)
):
    """Record a deal lost to competitor."""
    from models.financial_intelligence import LostDeal

    org_id = get_organization_id(db)

    deal = LostDeal(
        organization_id=org_id,
        **deal_data
    )
    db.add(deal)
    db.commit()

    return {"message": "Lost deal recorded"}
