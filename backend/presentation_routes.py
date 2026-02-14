"""
Presentation Engine API Routes

FastAPI router for PresentationEngine endpoints:
- Get loan data for presentation scenarios
- Save/retrieve scenarios
- Submit quote requests
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from datetime import datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, Field
import math

from database import get_db
from routes.auth_deps import require_auth

# Import models - these will be created by migration
try:
    from models.presentation import PresentationScenario, QuoteRequest, ScenarioType, QuoteRequestStatus
except ImportError:
    # Models not yet created - will work after migration
    pass

router = APIRouter(prefix="/api/presentation", tags=["Presentation Engine"], dependencies=[Depends(require_auth)])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class PresentationDataResponse(BaseModel):
    """Response with loan data for PresentationEngine component"""
    loan_id: int
    home_value: float
    loan_balance: float
    current_rate: float
    monthly_payment: float
    equity: float
    ltv: float
    borrower_name: Optional[str] = None


class ScenarioInputs(BaseModel):
    """Base inputs for any scenario"""
    home_value: float
    loan_balance: float
    current_rate: Optional[float] = None
    current_payment: Optional[float] = None


class RefinanceInputs(ScenarioInputs):
    """Inputs for refinance scenario"""
    new_rate: float
    new_term: int = 30


class CashOutInputs(ScenarioInputs):
    """Inputs for cash-out refinance scenario"""
    cash_out_amount: float
    new_rate: float
    new_term: int = 30


class HelocInputs(ScenarioInputs):
    """Inputs for HELOC scenario"""
    credit_line: float
    draw_amount: Optional[float] = 0
    heloc_rate: Optional[float] = 8.5


class SellInputs(ScenarioInputs):
    """Inputs for sell analysis scenario"""
    sale_price: float
    agent_commission: float = 5.5
    repair_credits: float = 0


class SaveScenarioRequest(BaseModel):
    """Request to save a scenario"""
    scenario_type: str  # refinance, cashOut, heloc, sell
    scenario_inputs: dict
    calculated_results: Optional[dict] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    is_favorite: bool = False


class QuoteRequestCreate(BaseModel):
    """Request to submit a quote request"""
    quote_type: str  # refinance, cashOut, heloc, sell
    request_data: dict
    scenario_id: Optional[str] = None
    preferred_contact_method: Optional[str] = "email"
    preferred_contact_time: Optional[str] = None
    borrower_notes: Optional[str] = None


class QuoteResponseUpdate(BaseModel):
    """Update quote with response data"""
    status: str
    quote_data: Optional[dict] = None
    internal_notes: Optional[str] = None
    expires_at: Optional[datetime] = None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_monthly_payment(principal: float, annual_rate: float, term_years: int) -> float:
    """Calculate monthly mortgage payment using standard amortization formula"""
    if annual_rate <= 0 or principal <= 0:
        return 0

    monthly_rate = annual_rate / 100 / 12
    num_payments = term_years * 12

    if monthly_rate == 0:
        return principal / num_payments

    payment = (principal * monthly_rate) / (1 - math.pow(1 + monthly_rate, -num_payments))
    return round(payment, 2)


def calculate_refinance_results(
    loan_balance: float,
    current_rate: float,
    current_payment: float,
    new_rate: float,
    new_term: int
) -> dict:
    """Calculate refinance scenario results"""
    new_payment = calculate_monthly_payment(loan_balance, new_rate, new_term)
    monthly_savings = current_payment - new_payment
    yearly_savings = monthly_savings * 12

    # Assume ~$3000 closing costs for break-even calculation
    closing_costs = 3000
    break_even_months = math.ceil(closing_costs / monthly_savings) if monthly_savings > 0 else 999

    # Calculate total interest over life of loan
    current_remaining_months = 25 * 12  # Assume 25 years remaining
    current_total_interest = (current_payment * current_remaining_months) - loan_balance
    new_total_payments = new_payment * (new_term * 12)
    new_total_interest = new_total_payments - loan_balance
    interest_savings = current_total_interest - new_total_interest

    return {
        "new_payment": round(new_payment, 2),
        "monthly_savings": round(monthly_savings, 2),
        "yearly_savings": round(yearly_savings, 2),
        "break_even_months": break_even_months,
        "interest_savings": round(interest_savings, 2),
        "new_total_interest": round(new_total_interest, 2),
    }


def calculate_cashout_results(
    home_value: float,
    loan_balance: float,
    cash_out_amount: float,
    new_rate: float,
    new_term: int = 30
) -> dict:
    """Calculate cash-out refinance scenario results"""
    max_ltv = 0.80
    max_loan_amount = home_value * max_ltv
    max_cash_out = max(0, max_loan_amount - loan_balance)

    effective_cash_out = min(cash_out_amount, max_cash_out)
    new_loan_amount = loan_balance + effective_cash_out
    new_ltv = (new_loan_amount / home_value) * 100

    new_payment = calculate_monthly_payment(new_loan_amount, new_rate, new_term)

    return {
        "max_cash_out": round(max_cash_out, 2),
        "effective_cash_out": round(effective_cash_out, 2),
        "new_loan_amount": round(new_loan_amount, 2),
        "new_ltv": round(new_ltv, 1),
        "new_payment": round(new_payment, 2),
    }


def calculate_heloc_results(
    home_value: float,
    loan_balance: float,
    draw_amount: float = 0,
    heloc_rate: float = 8.5
) -> dict:
    """Calculate HELOC scenario results"""
    max_cltv = 0.85
    max_combined_loan = home_value * max_cltv
    max_heloc_line = max(0, max_combined_loan - loan_balance)

    monthly_interest = (draw_amount * (heloc_rate / 100)) / 12
    annual_interest = monthly_interest * 12

    return {
        "max_heloc_line": round(max_heloc_line, 2),
        "monthly_interest_only": round(monthly_interest, 2),
        "annual_interest": round(annual_interest, 2),
    }


def calculate_sell_results(
    sale_price: float,
    loan_balance: float,
    agent_commission: float = 5.5,
    repair_credits: float = 0
) -> dict:
    """Calculate sell analysis scenario results"""
    commission = (sale_price * agent_commission) / 100
    closing_costs = sale_price * 0.015  # ~1.5% seller closing costs
    total_costs = commission + closing_costs + repair_credits
    net_proceeds = sale_price - loan_balance - total_costs

    return {
        "commission": round(commission, 2),
        "closing_costs": round(closing_costs, 2),
        "total_costs": round(total_costs, 2),
        "net_proceeds": round(net_proceeds, 2),
    }


# =============================================================================
# LOAN DATA ENDPOINTS
# =============================================================================

@router.get("/loans/{loan_id}/data", response_model=PresentationDataResponse)
def get_presentation_data(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """
    Get loan data formatted for PresentationEngine component.
    Returns home value, loan balance, current rate, and calculated monthly payment.
    """
    # Import here to avoid circular imports
    from main import Loan

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get home value from appraisal or purchase price
    home_value = loan.appraisal_value or loan.purchase_price or 0
    loan_balance = loan.amount or 0
    current_rate = loan.rate or 0
    term_years = (loan.term or 360) // 12

    # Calculate monthly payment
    monthly_payment = calculate_monthly_payment(loan_balance, current_rate, term_years)

    # Calculate equity and LTV
    equity = home_value - loan_balance if home_value > 0 else 0
    ltv = (loan_balance / home_value * 100) if home_value > 0 else 0

    return PresentationDataResponse(
        loan_id=loan_id,
        home_value=home_value,
        loan_balance=loan_balance,
        current_rate=current_rate,
        monthly_payment=monthly_payment,
        equity=equity,
        ltv=round(ltv, 1),
        borrower_name=loan.borrower_name,
    )


# =============================================================================
# CALCULATION ENDPOINTS
# =============================================================================

@router.post("/calculate/refinance")
def calculate_refinance(
    inputs: RefinanceInputs,
):
    """Calculate refinance scenario without saving"""
    current_payment = inputs.current_payment
    if not current_payment:
        # Estimate current payment if not provided
        current_payment = calculate_monthly_payment(inputs.loan_balance, inputs.current_rate or 6.5, 30)

    results = calculate_refinance_results(
        loan_balance=inputs.loan_balance,
        current_rate=inputs.current_rate or 6.5,
        current_payment=current_payment,
        new_rate=inputs.new_rate,
        new_term=inputs.new_term,
    )

    return {"status": "success", "results": results}


@router.post("/calculate/cash-out")
def calculate_cash_out(
    inputs: CashOutInputs,
):
    """Calculate cash-out refinance scenario without saving"""
    results = calculate_cashout_results(
        home_value=inputs.home_value,
        loan_balance=inputs.loan_balance,
        cash_out_amount=inputs.cash_out_amount,
        new_rate=inputs.new_rate,
        new_term=inputs.new_term,
    )

    return {"status": "success", "results": results}


@router.post("/calculate/heloc")
def calculate_heloc(
    inputs: HelocInputs,
):
    """Calculate HELOC scenario without saving"""
    results = calculate_heloc_results(
        home_value=inputs.home_value,
        loan_balance=inputs.loan_balance,
        draw_amount=inputs.draw_amount or 0,
        heloc_rate=inputs.heloc_rate or 8.5,
    )

    return {"status": "success", "results": results}


@router.post("/calculate/sell")
def calculate_sell(
    inputs: SellInputs,
):
    """Calculate sell analysis scenario without saving"""
    results = calculate_sell_results(
        sale_price=inputs.sale_price,
        loan_balance=inputs.loan_balance,
        agent_commission=inputs.agent_commission,
        repair_credits=inputs.repair_credits,
    )

    return {"status": "success", "results": results}


# =============================================================================
# SCENARIO CRUD ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/scenarios")
def save_scenario(
    loan_id: int = Path(..., description="Loan ID"),
    request: SaveScenarioRequest = Body(...),
    borrower_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Save a presentation scenario for future reference"""
    try:
        from models.presentation import PresentationScenario, ScenarioType
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    # Map string to enum
    scenario_type_map = {
        "refinance": ScenarioType.REFINANCE,
        "cashOut": ScenarioType.CASH_OUT,
        "heloc": ScenarioType.HELOC,
        "sell": ScenarioType.SELL,
    }

    scenario_type = scenario_type_map.get(request.scenario_type)
    if not scenario_type:
        raise HTTPException(status_code=400, detail=f"Invalid scenario type: {request.scenario_type}")

    # Calculate results if not provided
    calculated_results = request.calculated_results
    if not calculated_results:
        inputs = request.scenario_inputs
        home_value = inputs.get("homeValue", inputs.get("home_value", 0))
        loan_balance = inputs.get("loanBalance", inputs.get("loan_balance", 0))

        if request.scenario_type == "refinance":
            calculated_results = calculate_refinance_results(
                loan_balance=loan_balance,
                current_rate=inputs.get("currentRate", inputs.get("current_rate", 6.5)),
                current_payment=inputs.get("currentPayment", inputs.get("current_payment", 2200)),
                new_rate=inputs.get("newRate", inputs.get("new_rate", 5.5)),
                new_term=inputs.get("newTerm", inputs.get("new_term", 30)),
            )
        elif request.scenario_type == "cashOut":
            calculated_results = calculate_cashout_results(
                home_value=home_value,
                loan_balance=loan_balance,
                cash_out_amount=inputs.get("cashOutAmount", inputs.get("cash_out_amount", 50000)),
                new_rate=inputs.get("newRate", inputs.get("new_rate", 6.5)),
            )
        elif request.scenario_type == "heloc":
            calculated_results = calculate_heloc_results(
                home_value=home_value,
                loan_balance=loan_balance,
                draw_amount=inputs.get("drawAmount", inputs.get("draw_amount", 0)),
                heloc_rate=inputs.get("helocRate", inputs.get("heloc_rate", 8.5)),
            )
        elif request.scenario_type == "sell":
            calculated_results = calculate_sell_results(
                sale_price=inputs.get("salePrice", inputs.get("sale_price", home_value)),
                loan_balance=loan_balance,
                agent_commission=inputs.get("agentCommission", inputs.get("agent_commission", 5.5)),
                repair_credits=inputs.get("repairCredits", inputs.get("repair_credits", 0)),
            )

    # Get base loan data
    inputs = request.scenario_inputs
    home_value = inputs.get("homeValue", inputs.get("home_value", 0))
    loan_balance = inputs.get("loanBalance", inputs.get("loan_balance", 0))
    current_rate = inputs.get("currentRate", inputs.get("current_rate"))
    current_payment = inputs.get("currentPayment", inputs.get("current_payment"))

    scenario = PresentationScenario(
        loan_id=loan_id,
        borrower_id=borrower_id,
        scenario_type=scenario_type,
        home_value=Decimal(str(home_value)) if home_value else None,
        loan_balance=Decimal(str(loan_balance)) if loan_balance else None,
        current_rate=Decimal(str(current_rate)) if current_rate else None,
        current_payment=Decimal(str(current_payment)) if current_payment else None,
        scenario_inputs=request.scenario_inputs,
        calculated_results=calculated_results,
        name=request.name,
        notes=request.notes,
        is_favorite=request.is_favorite,
    )

    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    return {"status": "success", "scenario": scenario.to_dict()}


@router.get("/loans/{loan_id}/scenarios")
def get_scenarios(
    loan_id: int = Path(..., description="Loan ID"),
    scenario_type: Optional[str] = Query(None),
    favorites_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get saved scenarios for a loan"""
    try:
        from models.presentation import PresentationScenario, ScenarioType
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    query = db.query(PresentationScenario).filter(PresentationScenario.loan_id == loan_id)

    if scenario_type:
        scenario_type_map = {
            "refinance": ScenarioType.REFINANCE,
            "cashOut": ScenarioType.CASH_OUT,
            "heloc": ScenarioType.HELOC,
            "sell": ScenarioType.SELL,
        }
        if scenario_type in scenario_type_map:
            query = query.filter(PresentationScenario.scenario_type == scenario_type_map[scenario_type])

    if favorites_only:
        query = query.filter(PresentationScenario.is_favorite == True)

    scenarios = query.order_by(desc(PresentationScenario.created_at)).limit(limit).all()

    return {
        "status": "success",
        "count": len(scenarios),
        "scenarios": [s.to_dict() for s in scenarios],
    }


@router.get("/scenarios/{scenario_id}")
def get_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
):
    """Get a specific scenario by ID"""
    try:
        from models.presentation import PresentationScenario
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    scenario = db.query(PresentationScenario).filter(
        PresentationScenario.id == scenario_id
    ).first()

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {"status": "success", "scenario": scenario.to_dict()}


@router.patch("/scenarios/{scenario_id}")
def update_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    name: Optional[str] = Body(None),
    notes: Optional[str] = Body(None),
    is_favorite: Optional[bool] = Body(None),
    db: Session = Depends(get_db),
):
    """Update a saved scenario"""
    try:
        from models.presentation import PresentationScenario
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    scenario = db.query(PresentationScenario).filter(
        PresentationScenario.id == scenario_id
    ).first()

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if name is not None:
        scenario.name = name
    if notes is not None:
        scenario.notes = notes
    if is_favorite is not None:
        scenario.is_favorite = is_favorite

    db.commit()
    db.refresh(scenario)

    return {"status": "success", "scenario": scenario.to_dict()}


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
):
    """Delete a saved scenario"""
    try:
        from models.presentation import PresentationScenario
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    scenario = db.query(PresentationScenario).filter(
        PresentationScenario.id == scenario_id
    ).first()

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    db.delete(scenario)
    db.commit()

    return {"status": "success", "message": "Scenario deleted"}


# =============================================================================
# QUOTE REQUEST ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/quote-requests")
def submit_quote_request(
    loan_id: int = Path(..., description="Loan ID"),
    request: QuoteRequestCreate = Body(...),
    borrower_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Submit a quote request from the PresentationEngine"""
    try:
        from models.presentation import QuoteRequest, ScenarioType, QuoteRequestStatus
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    # Map string to enum
    quote_type_map = {
        "refinance": ScenarioType.REFINANCE,
        "cashOut": ScenarioType.CASH_OUT,
        "heloc": ScenarioType.HELOC,
        "sell": ScenarioType.SELL,
    }

    quote_type = quote_type_map.get(request.quote_type)
    if not quote_type:
        raise HTTPException(status_code=400, detail=f"Invalid quote type: {request.quote_type}")

    # Get loan officer from loan for assignment
    from main import Loan
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    assigned_to = loan.loan_officer_id if loan else None

    quote_request = QuoteRequest(
        loan_id=loan_id,
        borrower_id=borrower_id,
        scenario_id=request.scenario_id,
        assigned_to_user_id=assigned_to,
        quote_type=quote_type,
        status=QuoteRequestStatus.PENDING,
        request_data=request.request_data,
        preferred_contact_method=request.preferred_contact_method,
        preferred_contact_time=request.preferred_contact_time,
        borrower_notes=request.borrower_notes,
    )

    db.add(quote_request)
    db.commit()
    db.refresh(quote_request)

    return {"status": "success", "quote_request": quote_request.to_dict()}


@router.get("/loans/{loan_id}/quote-requests")
def get_quote_requests(
    loan_id: int = Path(..., description="Loan ID"),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get quote requests for a loan"""
    try:
        from models.presentation import QuoteRequest, QuoteRequestStatus
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    query = db.query(QuoteRequest).filter(QuoteRequest.loan_id == loan_id)

    if status:
        status_map = {
            "pending": QuoteRequestStatus.PENDING,
            "in_progress": QuoteRequestStatus.IN_PROGRESS,
            "quoted": QuoteRequestStatus.QUOTED,
            "accepted": QuoteRequestStatus.ACCEPTED,
            "declined": QuoteRequestStatus.DECLINED,
            "expired": QuoteRequestStatus.EXPIRED,
        }
        if status in status_map:
            query = query.filter(QuoteRequest.status == status_map[status])

    requests = query.order_by(desc(QuoteRequest.created_at)).limit(limit).all()

    return {
        "status": "success",
        "count": len(requests),
        "quote_requests": [r.to_dict() for r in requests],
    }


@router.get("/quote-requests/{quote_id}")
def get_quote_request(
    quote_id: str = Path(..., description="Quote Request ID"),
    db: Session = Depends(get_db),
):
    """Get a specific quote request"""
    try:
        from models.presentation import QuoteRequest
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    quote = db.query(QuoteRequest).filter(QuoteRequest.id == quote_id).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote request not found")

    return {"status": "success", "quote_request": quote.to_dict()}


@router.patch("/quote-requests/{quote_id}")
def update_quote_request(
    quote_id: str = Path(..., description="Quote Request ID"),
    update: QuoteResponseUpdate = Body(...),
    db: Session = Depends(get_db),
):
    """Update a quote request (for LO to respond)"""
    try:
        from models.presentation import QuoteRequest, QuoteRequestStatus
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    quote = db.query(QuoteRequest).filter(QuoteRequest.id == quote_id).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote request not found")

    status_map = {
        "pending": QuoteRequestStatus.PENDING,
        "in_progress": QuoteRequestStatus.IN_PROGRESS,
        "quoted": QuoteRequestStatus.QUOTED,
        "accepted": QuoteRequestStatus.ACCEPTED,
        "declined": QuoteRequestStatus.DECLINED,
        "expired": QuoteRequestStatus.EXPIRED,
    }

    if update.status in status_map:
        quote.status = status_map[update.status]
        if update.status == "quoted":
            quote.quoted_at = datetime.utcnow()

    if update.quote_data:
        quote.quote_data = update.quote_data

    if update.internal_notes:
        quote.internal_notes = update.internal_notes

    if update.expires_at:
        quote.expires_at = update.expires_at

    db.commit()
    db.refresh(quote)

    return {"status": "success", "quote_request": quote.to_dict()}


# =============================================================================
# DASHBOARD / SUMMARY ENDPOINTS
# =============================================================================

@router.get("/users/{user_id}/pending-quotes")
def get_pending_quotes_for_user(
    user_id: int = Path(..., description="User ID (Loan Officer)"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get pending quote requests assigned to a specific loan officer"""
    try:
        from models.presentation import QuoteRequest, QuoteRequestStatus
    except ImportError:
        raise HTTPException(status_code=501, detail="Presentation models not yet migrated")

    from main import Loan

    requests = db.query(QuoteRequest).filter(
        QuoteRequest.assigned_to_user_id == user_id,
        QuoteRequest.status.in_([QuoteRequestStatus.PENDING, QuoteRequestStatus.IN_PROGRESS])
    ).order_by(desc(QuoteRequest.created_at)).limit(limit).all()

    return {
        "status": "success",
        "count": len(requests),
        "quote_requests": [r.to_dict() for r in requests],
    }
