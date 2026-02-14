"""
FastAPI routes for the Profitability Intelligence System.
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from fastapi import Request

from models.profitability import (
    Expense, ExpenseCategory, EmployeeCost, ProfitabilityRole,
    ProfitabilityLoan, LoanAttribution, RevenueRecord,
    ProfitabilitySnapshot, ProfitabilityScenario, ProfitabilityInsight,
    ProfitabilityAudit
)
from schemas.profitability import (
    ExpenseCategoryCreate, ExpenseCategoryResponse,
    ExpenseCreate, ExpenseUpdate, ExpenseResponse,
    RoleCreate, RoleResponse,
    EmployeeCostCreate, EmployeeCostUpdate, EmployeeCostResponse,
    LoanCreate, LoanResponse, LoanAttributionCreate,
    RevenueRecordCreate, RevenueRecordResponse,
    ScenarioCreate, ScenarioResponse,
    DashboardResponse, InsightResponse, SnapshotResponse
)
from services.profitability_service import ProfitabilityService

router = APIRouter(prefix="/api/v1/profitability", tags=["profitability"])


# Helper to get current user's organization
def get_organization_id(db: Session, request: Request = None) -> int:
    """Get organization ID from authenticated user's context"""
    if request:
        from jose import jwt, JWTError
        import os
        SECRET_KEY = os.getenv("SECRET_KEY")
        if not SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable is not set")

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
                if "org_id" in payload:
                    return payload["org_id"]
                if "company_id" in payload:
                    return payload["company_id"]
            except JWTError:
                raise HTTPException(status_code=401, detail="Invalid authentication token")
    raise HTTPException(status_code=401, detail="Authentication required")


# ============ Dashboard Endpoints ============

@router.get("/dashboard")
async def get_dashboard(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Get complete profitability dashboard data."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    # Parse month or use current
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    else:
        month_date = date.today().replace(day=1)

    # Get all dashboard data
    metrics = service.get_dashboard_metrics(month_date)
    role_profitability = service.get_role_profitability(month_date)
    top_performers = service.get_employee_performance(month_date, limit=10)
    trends = service.get_trends(months=12)
    gaps_gains = service.identify_gaps_and_gains(month_date)

    # Get recent insights
    insights = db.query(ProfitabilityInsight).filter(
        ProfitabilityInsight.organization_id == org_id,
        ProfitabilityInsight.is_acknowledged == False
    ).order_by(ProfitabilityInsight.created_at.desc()).limit(10).all()

    return {
        "metrics": metrics,
        "role_profitability": role_profitability,
        "top_performers": top_performers,
        "trends": trends,
        "gaps_and_gains": gaps_gains,
        "insights": [
            {
                "id": str(i.id),
                "insight_type": i.insight_type,
                "title": i.title,
                "description": i.description,
                "severity": i.severity,
                "data_json": i.data_json,
                "is_acknowledged": i.is_acknowledged,
                "created_at": i.created_at.isoformat()
            }
            for i in insights
        ]
    }


@router.get("/metrics")
async def get_metrics(
    month: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get just the key metrics for a month."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")
    else:
        month_date = date.today().replace(day=1)

    return service.get_dashboard_metrics(month_date)


@router.get("/trends")
async def get_trends(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db)
):
    """Get historical trend data."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)
    return service.get_trends(months)


# ============ Expense Endpoints ============

@router.get("/expense-categories", response_model=List[ExpenseCategoryResponse])
async def list_expense_categories(db: Session = Depends(get_db)):
    """List all expense categories."""
    return db.query(ExpenseCategory).filter(ExpenseCategory.is_active == True).all()


@router.post("/expense-categories", response_model=ExpenseCategoryResponse)
async def create_expense_category(
    data: ExpenseCategoryCreate,
    db: Session = Depends(get_db)
):
    """Create a new expense category."""
    category = ExpenseCategory(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/expenses", response_model=List[ExpenseResponse])
async def list_expenses(
    category_id: Optional[UUID] = None,
    expense_type: Optional[str] = None,
    is_active: bool = True,
    db: Session = Depends(get_db)
):
    """List expenses with optional filters."""
    org_id = get_organization_id(db)
    query = db.query(Expense).filter(
        Expense.organization_id == org_id,
        Expense.is_active == is_active
    )

    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if expense_type:
        query = query.filter(Expense.expense_type == expense_type)

    return query.order_by(Expense.effective_date.desc()).all()


@router.post("/expenses", response_model=ExpenseResponse)
async def create_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db)
):
    """Create a new expense."""
    org_id = get_organization_id(db)
    expense = Expense(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: UUID,
    data: ExpenseUpdate,
    db: Session = Depends(get_db)
):
    """Update an expense."""
    org_id = get_organization_id(db)
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.organization_id == org_id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in data.model_dump(exclude_unset=True).items():
        if key not in _protected:
            setattr(expense, key, value)

    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: UUID, db: Session = Depends(get_db)):
    """Soft delete an expense."""
    org_id = get_organization_id(db)
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.organization_id == org_id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.is_active = False
    db.commit()
    return {"status": "deleted"}


# ============ Role Endpoints ============

@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(db: Session = Depends(get_db)):
    """List all roles."""
    org_id = get_organization_id(db)
    return db.query(ProfitabilityRole).filter(
        ProfitabilityRole.organization_id == org_id,
        ProfitabilityRole.is_active == True
    ).all()


@router.post("/roles", response_model=RoleResponse)
async def create_role(data: RoleCreate, db: Session = Depends(get_db)):
    """Create a new role."""
    org_id = get_organization_id(db)
    role = ProfitabilityRole(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("/roles/{role_id}/profitability")
async def get_role_profitability(
    role_id: UUID,
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get profitability analysis for a specific role."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    if month:
        month_date = datetime.strptime(month, "%Y-%m").date()
    else:
        month_date = date.today().replace(day=1)

    all_roles = service.get_role_profitability(month_date)
    role_data = next((r for r in all_roles if r["role_id"] == str(role_id)), None)

    if not role_data:
        raise HTTPException(status_code=404, detail="Role not found")

    return role_data


# ============ Employee Cost Endpoints ============

@router.get("/employees", response_model=List[EmployeeCostResponse])
async def list_employee_costs(
    role_id: Optional[UUID] = None,
    is_active: bool = True,
    db: Session = Depends(get_db)
):
    """List employee costs."""
    org_id = get_organization_id(db)
    query = db.query(EmployeeCost).filter(
        EmployeeCost.organization_id == org_id,
        EmployeeCost.is_active == is_active
    )

    if role_id:
        query = query.filter(EmployeeCost.role_id == role_id)

    employees = query.all()

    # Add calculated fields
    results = []
    for emp in employees:
        emp_dict = {
            "id": emp.id,
            "organization_id": emp.organization_id,
            "user_id": emp.user_id,
            "role_id": emp.role_id,
            "employee_name": emp.employee_name,
            "base_salary": emp.base_salary,
            "benefits_cost": emp.benefits_cost,
            "taxes_cost": emp.taxes_cost,
            "equipment_cost": emp.equipment_cost,
            "training_cost": emp.training_cost,
            "other_costs": emp.other_costs,
            "hire_date": emp.hire_date,
            "termination_date": emp.termination_date,
            "is_active": emp.is_active,
            "fully_loaded_cost": emp.fully_loaded_cost,
            "monthly_cost": emp.monthly_cost,
            "created_at": emp.created_at,
            "role": emp.role
        }
        results.append(emp_dict)

    return results


@router.post("/employees", response_model=EmployeeCostResponse)
async def create_employee_cost(
    data: EmployeeCostCreate,
    db: Session = Depends(get_db)
):
    """Create employee cost record."""
    org_id = get_organization_id(db)
    employee = EmployeeCost(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return {
        **employee.__dict__,
        "fully_loaded_cost": employee.fully_loaded_cost,
        "monthly_cost": employee.monthly_cost
    }


@router.put("/employees/{employee_id}", response_model=EmployeeCostResponse)
async def update_employee_cost(
    employee_id: UUID,
    data: EmployeeCostUpdate,
    db: Session = Depends(get_db)
):
    """Update employee cost record."""
    org_id = get_organization_id(db)
    employee = db.query(EmployeeCost).filter(
        EmployeeCost.id == employee_id,
        EmployeeCost.organization_id == org_id
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in data.model_dump(exclude_unset=True).items():
        if key not in _protected:
            setattr(employee, key, value)

    db.commit()
    db.refresh(employee)

    return {
        **employee.__dict__,
        "fully_loaded_cost": employee.fully_loaded_cost,
        "monthly_cost": employee.monthly_cost
    }


@router.get("/employees/{employee_id}/performance")
async def get_employee_performance(
    employee_id: UUID,
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get performance metrics for a specific employee."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    if month:
        month_date = datetime.strptime(month, "%Y-%m").date()
    else:
        month_date = date.today().replace(day=1)

    all_employees = service.get_employee_performance(month_date, limit=100)
    employee_data = next(
        (e for e in all_employees if e["employee_id"] == str(employee_id)),
        None
    )

    if not employee_data:
        raise HTTPException(status_code=404, detail="Employee not found")

    return employee_data


# ============ Loan Endpoints ============

@router.get("/loans", response_model=List[LoanResponse])
async def list_loans(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """List closed loans."""
    org_id = get_organization_id(db)
    query = db.query(ProfitabilityLoan).filter(
        ProfitabilityLoan.organization_id == org_id
    )

    if start_date:
        query = query.filter(ProfitabilityLoan.close_date >= start_date)
    if end_date:
        query = query.filter(ProfitabilityLoan.close_date <= end_date)

    return query.order_by(ProfitabilityLoan.close_date.desc()).limit(limit).all()


@router.post("/loans", response_model=LoanResponse)
async def create_loan(data: LoanCreate, db: Session = Depends(get_db)):
    """Create a closed loan record with attributions."""
    org_id = get_organization_id(db)

    # Create loan
    loan_data = data.model_dump(exclude={"attributions"})
    loan = ProfitabilityLoan(
        organization_id=org_id,
        **loan_data
    )
    db.add(loan)
    db.flush()

    # Create attributions
    if data.attributions:
        for attr_data in data.attributions:
            attribution = LoanAttribution(
                loan_id=loan.id,
                **attr_data.model_dump()
            )
            db.add(attribution)

    # Create revenue record
    revenue = RevenueRecord(
        organization_id=org_id,
        loan_id=loan.id,
        revenue_type="origination_fee",
        amount=data.total_revenue,
        record_date=data.close_date
    )
    db.add(revenue)

    db.commit()
    db.refresh(loan)
    return loan


@router.post("/loans/{loan_id}/attributions")
async def add_loan_attribution(
    loan_id: UUID,
    data: LoanAttributionCreate,
    db: Session = Depends(get_db)
):
    """Add attribution to a loan."""
    org_id = get_organization_id(db)
    loan = db.query(ProfitabilityLoan).filter(
        ProfitabilityLoan.id == loan_id,
        ProfitabilityLoan.organization_id == org_id
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    attribution = LoanAttribution(
        loan_id=loan_id,
        **data.model_dump()
    )
    db.add(attribution)
    db.commit()
    db.refresh(attribution)
    return {"status": "created", "id": str(attribution.id)}


# ============ Revenue Endpoints ============

@router.get("/revenue", response_model=List[RevenueRecordResponse])
async def list_revenue(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    revenue_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List revenue records."""
    org_id = get_organization_id(db)
    query = db.query(RevenueRecord).filter(
        RevenueRecord.organization_id == org_id
    )

    if start_date:
        query = query.filter(RevenueRecord.record_date >= start_date)
    if end_date:
        query = query.filter(RevenueRecord.record_date <= end_date)
    if revenue_type:
        query = query.filter(RevenueRecord.revenue_type == revenue_type)

    return query.order_by(RevenueRecord.record_date.desc()).all()


@router.post("/revenue", response_model=RevenueRecordResponse)
async def create_revenue(
    data: RevenueRecordCreate,
    db: Session = Depends(get_db)
):
    """Create a revenue record."""
    org_id = get_organization_id(db)
    revenue = RevenueRecord(
        organization_id=org_id,
        **data.model_dump()
    )
    db.add(revenue)
    db.commit()
    db.refresh(revenue)
    return revenue


# ============ Scenario Endpoints ============

@router.get("/scenarios", response_model=List[ScenarioResponse])
async def list_scenarios(
    saved_only: bool = False,
    db: Session = Depends(get_db)
):
    """List saved scenarios."""
    org_id = get_organization_id(db)
    query = db.query(ProfitabilityScenario).filter(
        ProfitabilityScenario.organization_id == org_id
    )

    if saved_only:
        query = query.filter(ProfitabilityScenario.is_saved == True)

    return query.order_by(ProfitabilityScenario.created_at.desc()).all()


@router.post("/scenarios")
async def create_scenario(
    data: ScenarioCreate,
    db: Session = Depends(get_db)
):
    """Create and run a what-if scenario."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    # Run scenario
    results = service.run_scenario(
        data.base_month,
        data.parameters.model_dump()
    )

    # Save scenario
    scenario = ProfitabilityScenario(
        organization_id=org_id,
        name=data.name,
        description=data.description,
        base_month=data.base_month,
        parameters=data.parameters.model_dump(),
        results=results
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    return {
        "scenario_id": str(scenario.id),
        "results": results
    }


@router.post("/scenarios/run")
async def run_scenario(
    parameters: dict,
    base_month: str = Query(..., description="Base month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Run a scenario without saving."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    try:
        month_date = datetime.strptime(base_month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format")

    return service.run_scenario(month_date, parameters)


@router.put("/scenarios/{scenario_id}/save")
async def save_scenario(scenario_id: UUID, db: Session = Depends(get_db)):
    """Mark a scenario as saved."""
    org_id = get_organization_id(db)
    scenario = db.query(ProfitabilityScenario).filter(
        ProfitabilityScenario.id == scenario_id,
        ProfitabilityScenario.organization_id == org_id
    ).first()

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario.is_saved = True
    db.commit()
    return {"status": "saved"}


# ============ Snapshot Endpoints ============

@router.get("/snapshots", response_model=List[SnapshotResponse])
async def list_snapshots(
    limit: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db)
):
    """List historical snapshots."""
    org_id = get_organization_id(db)
    return db.query(ProfitabilitySnapshot).filter(
        ProfitabilitySnapshot.organization_id == org_id
    ).order_by(ProfitabilitySnapshot.snapshot_month.desc()).limit(limit).all()


@router.post("/snapshots")
async def create_snapshot(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Create or update a monthly snapshot."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    try:
        month_date = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format")

    snapshot = service.create_snapshot(month_date)
    return {
        "status": "created",
        "snapshot_id": str(snapshot.id),
        "month": snapshot.snapshot_month.strftime("%Y-%m")
    }


# ============ Insight Endpoints ============

@router.get("/insights", response_model=List[InsightResponse])
async def list_insights(
    acknowledged: Optional[bool] = None,
    insight_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List profitability insights."""
    org_id = get_organization_id(db)
    query = db.query(ProfitabilityInsight).filter(
        ProfitabilityInsight.organization_id == org_id
    )

    if acknowledged is not None:
        query = query.filter(ProfitabilityInsight.is_acknowledged == acknowledged)
    if insight_type:
        query = query.filter(ProfitabilityInsight.insight_type == insight_type)

    return query.order_by(ProfitabilityInsight.created_at.desc()).limit(limit).all()


@router.post("/insights/generate")
async def generate_insights(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Generate AI insights for a month."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    try:
        month_date = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format")

    insights = service.generate_insights(month_date)
    return {
        "status": "generated",
        "count": len(insights),
        "insights": [
            {
                "id": str(i.id),
                "type": i.insight_type,
                "title": i.title,
                "severity": i.severity
            }
            for i in insights
        ]
    }


@router.put("/insights/{insight_id}/acknowledge")
async def acknowledge_insight(
    insight_id: UUID,
    db: Session = Depends(get_db)
):
    """Acknowledge an insight."""
    org_id = get_organization_id(db)
    insight = db.query(ProfitabilityInsight).filter(
        ProfitabilityInsight.id == insight_id,
        ProfitabilityInsight.organization_id == org_id
    ).first()

    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    insight.is_acknowledged = True
    insight.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"status": "acknowledged"}


# ============ Analysis Endpoints ============

@router.get("/analysis/gaps-gains")
async def get_gaps_and_gains(
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get gap and gain analysis."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    if month:
        month_date = datetime.strptime(month, "%Y-%m").date()
    else:
        month_date = date.today().replace(day=1)

    return service.identify_gaps_and_gains(month_date)


@router.get("/analysis/break-even")
async def get_break_even_analysis(
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get break-even analysis."""
    org_id = get_organization_id(db)
    service = ProfitabilityService(db, org_id)

    if month:
        month_date = datetime.strptime(month, "%Y-%m").date()
    else:
        month_date = date.today().replace(day=1)

    metrics = service.get_dashboard_metrics(month_date)

    return {
        "break_even_loans": metrics["break_even_loans"],
        "current_loans": metrics["loans_closed"],
        "gap": max(0, metrics["break_even_loans"] - metrics["loans_closed"]),
        "surplus": max(0, metrics["loans_closed"] - metrics["break_even_loans"]),
        "total_expenses": metrics["total_expenses"],
        "avg_revenue_per_loan": metrics["revenue_per_loan"],
        "status": "profitable" if metrics["loans_closed"] >= metrics["break_even_loans"] else "below_break_even"
    }
