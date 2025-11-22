"""
Pydantic schemas for the Profitability Intelligence System.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, validator


# ============ Expense Schemas ============

class ExpenseCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_category_id: Optional[UUID] = None


class ExpenseCategoryCreate(ExpenseCategoryBase):
    pass


class ExpenseCategoryResponse(ExpenseCategoryBase):
    id: UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ExpenseBase(BaseModel):
    category_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    amount: Decimal = Field(..., gt=0)
    expense_type: str = Field(..., pattern="^(fixed|variable|one_time)$")
    recurrence: str = Field(default="monthly", pattern="^(daily|weekly|monthly|quarterly|annually|one_time)$")
    effective_date: date
    end_date: Optional[date] = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    expense_type: Optional[str] = None
    recurrence: Optional[str] = None
    effective_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None


class ExpenseResponse(ExpenseBase):
    id: UUID
    organization_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    category: Optional[ExpenseCategoryResponse] = None

    class Config:
        from_attributes = True


# ============ Role Schemas ============

class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    department: Optional[str] = None
    is_revenue_generating: bool = False
    base_salary_range_min: Optional[Decimal] = None
    base_salary_range_max: Optional[Decimal] = None
    typical_benefits_percentage: Decimal = Field(default=Decimal("25.00"))
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: UUID
    organization_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Employee Cost Schemas ============

class EmployeeCostBase(BaseModel):
    user_id: Optional[int] = None
    role_id: Optional[UUID] = None
    employee_name: str = Field(..., min_length=1, max_length=255)
    base_salary: Decimal = Field(..., gt=0)
    benefits_cost: Decimal = Field(default=Decimal("0"))
    taxes_cost: Decimal = Field(default=Decimal("0"))
    equipment_cost: Decimal = Field(default=Decimal("0"))
    training_cost: Decimal = Field(default=Decimal("0"))
    other_costs: Decimal = Field(default=Decimal("0"))
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None


class EmployeeCostCreate(EmployeeCostBase):
    pass


class EmployeeCostUpdate(BaseModel):
    role_id: Optional[UUID] = None
    employee_name: Optional[str] = None
    base_salary: Optional[Decimal] = None
    benefits_cost: Optional[Decimal] = None
    taxes_cost: Optional[Decimal] = None
    equipment_cost: Optional[Decimal] = None
    training_cost: Optional[Decimal] = None
    other_costs: Optional[Decimal] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    is_active: Optional[bool] = None


class EmployeeCostResponse(EmployeeCostBase):
    id: UUID
    organization_id: int
    is_active: bool
    fully_loaded_cost: Decimal
    monthly_cost: Decimal
    created_at: datetime
    role: Optional[RoleResponse] = None

    class Config:
        from_attributes = True


# ============ Loan Schemas ============

class LoanAttributionBase(BaseModel):
    employee_cost_id: UUID
    attribution_percentage: Decimal = Field(..., gt=0, le=100)
    role_at_time: Optional[str] = None
    notes: Optional[str] = None


class LoanAttributionCreate(LoanAttributionBase):
    pass


class LoanAttributionResponse(LoanAttributionBase):
    id: UUID
    loan_id: UUID
    created_at: datetime
    employee_name: Optional[str] = None

    class Config:
        from_attributes = True


class LoanBase(BaseModel):
    loan_number: str = Field(..., min_length=1, max_length=100)
    borrower_name: Optional[str] = None
    loan_amount: Decimal = Field(..., gt=0)
    loan_type: Optional[str] = None
    close_date: date
    total_revenue: Decimal = Field(..., gt=0)
    processing_days: Optional[int] = None
    lead_source: Optional[str] = None
    notes: Optional[str] = None


class LoanCreate(LoanBase):
    attributions: Optional[List[LoanAttributionCreate]] = None


class LoanResponse(LoanBase):
    id: UUID
    organization_id: int
    created_at: datetime
    attributions: List[LoanAttributionResponse] = []

    class Config:
        from_attributes = True


# ============ Revenue Schemas ============

class RevenueRecordBase(BaseModel):
    loan_id: Optional[UUID] = None
    revenue_type: str = Field(..., pattern="^(origination_fee|processing_fee|admin_fee|commission|rebate|other)$")
    amount: Decimal = Field(..., gt=0)
    description: Optional[str] = None
    record_date: date


class RevenueRecordCreate(RevenueRecordBase):
    pass


class RevenueRecordResponse(RevenueRecordBase):
    id: UUID
    organization_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Dashboard & Analysis Schemas ============

class DashboardMetrics(BaseModel):
    """Main dashboard metrics."""
    total_revenue: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    profit_margin: Decimal
    loans_closed: int
    cost_per_loan: Decimal
    revenue_per_loan: Decimal
    profit_per_loan: Decimal
    break_even_loans: int
    employee_count: int
    month: str


class RoleProfitability(BaseModel):
    """Profitability analysis by role."""
    role_id: UUID
    role_name: str
    department: Optional[str]
    employee_count: int
    total_cost: Decimal
    total_revenue: Decimal
    net_contribution: Decimal
    roi_percentage: Decimal
    loans_attributed: int
    cost_per_loan: Decimal
    is_profitable: bool


class EmployeePerformance(BaseModel):
    """Individual employee performance metrics."""
    employee_id: UUID
    employee_name: str
    role_name: Optional[str]
    monthly_cost: Decimal
    total_revenue: Decimal
    net_contribution: Decimal
    roi_percentage: Decimal
    loans_closed: int
    avg_loan_size: Decimal
    revenue_per_loan: Decimal


class TrendData(BaseModel):
    """Historical trend data point."""
    month: str
    revenue: Decimal
    expenses: Decimal
    profit: Decimal
    loans: int
    cost_per_loan: Decimal


class GapGainItem(BaseModel):
    """Gap or gain identification."""
    type: str  # 'gap' or 'gain'
    category: str
    title: str
    description: str
    impact: Decimal
    priority: str  # 'high', 'medium', 'low'
    action: str


# ============ Scenario Schemas ============

class ScenarioParameters(BaseModel):
    """Parameters for what-if scenario modeling."""
    staff_changes: Optional[Dict[str, int]] = None  # role_id: change_count
    expense_changes: Optional[Dict[str, Decimal]] = None  # category: percentage_change
    loan_volume_change: Optional[Decimal] = None  # percentage change
    revenue_per_loan_change: Optional[Decimal] = None  # percentage change
    new_expenses: Optional[List[Dict[str, Any]]] = None


class ScenarioResults(BaseModel):
    """Results from scenario analysis."""
    baseline: DashboardMetrics
    projected: DashboardMetrics
    revenue_change: Decimal
    expense_change: Decimal
    profit_change: Decimal
    break_even_change: int
    recommendation: str


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    base_month: date
    parameters: ScenarioParameters


class ScenarioResponse(BaseModel):
    id: UUID
    organization_id: int
    name: str
    description: Optional[str]
    base_month: date
    parameters: Dict[str, Any]
    results: Optional[Dict[str, Any]]
    is_saved: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Insight Schemas ============

class InsightResponse(BaseModel):
    id: UUID
    insight_type: str
    title: str
    description: str
    severity: str
    data_json: Optional[Dict[str, Any]]
    is_acknowledged: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Snapshot Schemas ============

class SnapshotResponse(BaseModel):
    id: UUID
    snapshot_month: date
    total_revenue: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    loans_closed: int
    cost_per_loan: Optional[Decimal]
    revenue_per_loan: Optional[Decimal]
    profit_per_loan: Optional[Decimal]
    employee_count: Optional[int]
    break_even_loans: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Combined Dashboard Response ============

class DashboardResponse(BaseModel):
    """Complete dashboard data response."""
    metrics: DashboardMetrics
    role_profitability: List[RoleProfitability]
    top_performers: List[EmployeePerformance]
    trends: List[TrendData]
    gaps_and_gains: List[GapGainItem]
    insights: List[InsightResponse]
