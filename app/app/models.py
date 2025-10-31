"""Pydantic models for domain features (Leads, Tasks, Calendar, Active Loans, Portfolio)."""
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# ------ Leads ------
class LeadCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    status: str = "new"
    model_config = ConfigDict(from_attributes=True)

class LeadResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    user_id: int
    model_config = ConfigDict(from_attributes=True)

# ------ Tasks ------
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: bool
    created_at: datetime
    user_id: int
    model_config = ConfigDict(from_attributes=True)

# ------ Calendar Events ------
class CalendarEventCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    model_config = ConfigDict(from_attributes=True)

class CalendarEventResponse(BaseModel):
    id: int
    title: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    user_id: int
    model_config = ConfigDict(from_attributes=True)

# ------ Active Loans ------
class ActiveLoanCreate(BaseModel):
    client_name: str
    loan_amount: float
    loan_type: str
    status: str = "pending"
    notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ActiveLoanResponse(BaseModel):
    id: int
    client_name: str
    loan_amount: float
    loan_type: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    user_id: int
    model_config = ConfigDict(from_attributes=True)

# ------ Portfolio ------
class PortfolioStats(BaseModel):
    total_value: float
    active_loans: int
    pending_loans: int
    approved_loans: int
    revenue_this_month: float
    model_config = ConfigDict(from_attributes=True)
