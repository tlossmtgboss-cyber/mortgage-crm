from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import sys
sys.path.append('..')
from app.db import get_db

router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"]
)

# Pydantic schemas for Portfolio
class PortfolioBase(BaseModel):
    lead_id: int
    loan_id: Optional[int] = None
    property_value: Optional[float] = None
    outstanding_balance: Optional[float] = None
    monthly_payment: Optional[float] = None
    status: Optional[str] = "active"  # e.g., 'active', 'closed', 'defaulted'
    performance_rating: Optional[str] = None  # e.g., 'excellent', 'good', 'fair', 'poor'
    last_payment_date: Optional[datetime] = None
    notes: Optional[str] = None

class PortfolioCreate(PortfolioBase):
    pass

class PortfolioUpdate(BaseModel):
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    property_value: Optional[float] = None
    outstanding_balance: Optional[float] = None
    monthly_payment: Optional[float] = None
    status: Optional[str] = None
    performance_rating: Optional[str] = None
    last_payment_date: Optional[datetime] = None
    notes: Optional[str] = None

class PortfolioResponse(PortfolioBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Note: Portfolio model needs to be added to app/models.py
# Placeholder for now - will be functional once model is created

@router.post("/", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio_item(item: PortfolioCreate, db: Session = Depends(get_db)):
    """Create a new portfolio item"""
    try:
        from app.models import Portfolio
        db_item = Portfolio(**item.dict())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")

@router.get("/", response_model=List[PortfolioResponse])
def get_portfolio_items(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    lead_id: Optional[int] = None,
    performance_rating: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all portfolio items with optional filters"""
    try:
        from app.models import Portfolio
        query = db.query(Portfolio)
        
        if status_filter:
            query = query.filter(Portfolio.status == status_filter)
        if lead_id:
            query = query.filter(Portfolio.lead_id == lead_id)
        if performance_rating:
            query = query.filter(Portfolio.performance_rating == performance_rating)
        
        items = query.offset(skip).limit(limit).all()
        return items
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")

@router.get("/{item_id}", response_model=PortfolioResponse)
def get_portfolio_item(item_id: int, db: Session = Depends(get_db)):
    """Get a specific portfolio item by ID"""
    try:
        from app.models import Portfolio
        item = db.query(Portfolio).filter(Portfolio.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Portfolio item not found")
        return item
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")

@router.put("/{item_id}", response_model=PortfolioResponse)
def update_portfolio_item(item_id: int, item_update: PortfolioUpdate, db: Session = Depends(get_db)):
    """Update a portfolio item"""
    try:
        from app.models import Portfolio
        db_item = db.query(Portfolio).filter(Portfolio.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="Portfolio item not found")
        
        update_data = item_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_item, field, value)
        
        db.commit()
        db.refresh(db_item)
        return db_item
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a portfolio item"""
    try:
        from app.models import Portfolio
        db_item = db.query(Portfolio).filter(Portfolio.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="Portfolio item not found")
        
        db.delete(db_item)
        db.commit()
        return None
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")

@router.get("/analytics/summary")
def get_portfolio_summary(db: Session = Depends(get_db)):
    """Get summary analytics for the portfolio"""
    try:
        from app.models import Portfolio
        from sqlalchemy import func
        
        total_items = db.query(func.count(Portfolio.id)).scalar()
        total_value = db.query(func.sum(Portfolio.property_value)).scalar() or 0
        total_balance = db.query(func.sum(Portfolio.outstanding_balance)).scalar() or 0
        
        return {
            "total_items": total_items,
            "total_property_value": float(total_value),
            "total_outstanding_balance": float(total_balance),
            "equity": float(total_value - total_balance)
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="Portfolio model not yet implemented. Please add to app/models.py")
