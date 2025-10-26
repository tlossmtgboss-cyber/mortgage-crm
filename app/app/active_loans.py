from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
import sys
sys.path.append('..')
from app.db import get_db

router = APIRouter(
    prefix="/api/active-loans",
    tags=["active_loans"]
)

# Pydantic schemas for Active Loans
class ActiveLoanBase(BaseModel):
    lead_id: int
    loan_amount: float
    loan_type: Optional[str] = None  # e.g., 'conventional', 'FHA', 'VA'
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None  # in months
    status: Optional[str] = "processing"  # e.g., 'processing', 'approved', 'funded', 'closed'
    property_address: Optional[str] = None
    estimated_close_date: Optional[datetime] = None
    notes: Optional[str] = None

class ActiveLoanCreate(ActiveLoanBase):
    pass

class ActiveLoanUpdate(BaseModel):
    lead_id: Optional[int] = None
    loan_amount: Optional[float] = None
    loan_type: Optional[str] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    status: Optional[str] = None
    property_address: Optional[str] = None
    estimated_close_date: Optional[datetime] = None
    notes: Optional[str] = None

class ActiveLoanResponse(ActiveLoanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Note: ActiveLoan model needs to be added to app/models.py
# Placeholder for now - will be functional once model is created

@router.post("/", response_model=ActiveLoanResponse, status_code=status.HTTP_201_CREATED)
def create_active_loan(loan: ActiveLoanCreate, db: Session = Depends(get_db)):
    """Create a new active loan"""
    # This will work once ActiveLoan model is added to app/models.py
    try:
        from app.models import ActiveLoan
        db_loan = ActiveLoan(**loan.dict())
        db.add(db_loan)
        db.commit()
        db.refresh(db_loan)
        return db_loan
    except ImportError:
        raise HTTPException(status_code=501, detail="ActiveLoan model not yet implemented. Please add to app/models.py")

@router.get("/", response_model=List[ActiveLoanResponse])
def get_active_loans(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    lead_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all active loans with optional filters"""
    try:
        from app.models import ActiveLoan
        query = db.query(ActiveLoan)
        
        if status_filter:
            query = query.filter(ActiveLoan.status == status_filter)
        if lead_id:
            query = query.filter(ActiveLoan.lead_id == lead_id)
        
        loans = query.offset(skip).limit(limit).all()
        return loans
    except ImportError:
        raise HTTPException(status_code=501, detail="ActiveLoan model not yet implemented. Please add to app/models.py")

@router.get("/{loan_id}", response_model=ActiveLoanResponse)
def get_active_loan(loan_id: int, db: Session = Depends(get_db)):
    """Get a specific active loan by ID"""
    try:
        from app.models import ActiveLoan
        loan = db.query(ActiveLoan).filter(ActiveLoan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Active loan not found")
        return loan
    except ImportError:
        raise HTTPException(status_code=501, detail="ActiveLoan model not yet implemented. Please add to app/models.py")

@router.put("/{loan_id}", response_model=ActiveLoanResponse)
def update_active_loan(loan_id: int, loan_update: ActiveLoanUpdate, db: Session = Depends(get_db)):
    """Update an active loan"""
    try:
        from app.models import ActiveLoan
        db_loan = db.query(ActiveLoan).filter(ActiveLoan.id == loan_id).first()
        if not db_loan:
            raise HTTPException(status_code=404, detail="Active loan not found")
        
        update_data = loan_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_loan, field, value)
        
        db.commit()
        db.refresh(db_loan)
        return db_loan
    except ImportError:
        raise HTTPException(status_code=501, detail="ActiveLoan model not yet implemented. Please add to app/models.py")

@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_active_loan(loan_id: int, db: Session = Depends(get_db)):
    """Delete an active loan"""
    try:
        from app.models import ActiveLoan
        db_loan = db.query(ActiveLoan).filter(ActiveLoan.id == loan_id).first()
        if not db_loan:
            raise HTTPException(status_code=404, detail="Active loan not found")
        
        db.delete(db_loan)
        db.commit()
        return None
    except ImportError:
        raise HTTPException(status_code=501, detail="ActiveLoan model not yet implemented. Please add to app/models.py")
