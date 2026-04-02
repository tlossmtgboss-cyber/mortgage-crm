"""
Rate Sheet Models
SQLAlchemy models for rate sheet upload, parsing, and refinance opportunity tracking.
"""

from sqlalchemy import (
    Column, String, Integer, Numeric, Date, DateTime, Text,
    Boolean, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

from database import Base


class RateSheet(Base):
    """
    Uploaded rate sheet tracking.
    Stores metadata about uploaded PDF/Excel rate sheets.
    """
    __tablename__ = "rate_sheets"

    id = Column(Integer, primary_key=True, index=True)

    # File info
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), unique=True)
    s3_key = Column(String(500))

    # Processing status
    status = Column(String(50), default='pending')  # pending, processing, parsed, failed
    error_message = Column(Text)

    # Parsed metadata
    parsed_data = Column(JSON)
    effective_date = Column(Date)
    lender_name = Column(String(255))

    # Audit
    uploaded_by = Column(Integer)  # Reference to users table
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    rates = relationship("RateSheetRate", back_populates="rate_sheet", cascade="all, delete-orphan")
    opportunities = relationship("RefinanceOpportunity", back_populates="rate_sheet")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'filename': self.filename,
            'file_hash': self.file_hash,
            's3_key': self.s3_key,
            'status': self.status,
            'error_message': self.error_message,
            'parsed_data': self.parsed_data,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'lender_name': self.lender_name,
            'uploaded_by': self.uploaded_by,
            'rates_count': len(self.rates) if self.rates else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class RateSheetRate(Base):
    """
    Parsed rates from a rate sheet.
    Each row represents a specific rate for a loan type/term combination.
    """
    __tablename__ = "rate_sheet_rates"

    id = Column(Integer, primary_key=True, index=True)
    rate_sheet_id = Column(Integer, ForeignKey('rate_sheets.id', ondelete='CASCADE'), nullable=False, index=True)

    # Loan parameters
    loan_type = Column(String(50), nullable=False)  # conventional, fha, va, usda, jumbo
    loan_term = Column(Integer, nullable=False)     # 15, 20, 30

    # Rate data
    rate = Column(Numeric(5, 3), nullable=False)
    apr = Column(Numeric(5, 3))
    points = Column(Numeric(5, 3))

    # Eligibility criteria
    min_credit_score = Column(Integer)
    max_credit_score = Column(Integer)
    min_ltv = Column(Numeric(5, 2))
    max_ltv = Column(Numeric(5, 2))
    occupancy = Column(String(50))      # primary, second_home, investment
    property_type = Column(String(50))  # single_family, condo, townhouse, multi_family

    # Parsing confidence
    confidence_score = Column(Numeric(3, 2))

    # Timestamp
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    rate_sheet = relationship("RateSheet", back_populates="rates")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'rate_sheet_id': self.rate_sheet_id,
            'loan_type': self.loan_type,
            'loan_term': self.loan_term,
            'rate': float(self.rate) if self.rate else None,
            'apr': float(self.apr) if self.apr else None,
            'points': float(self.points) if self.points else None,
            'min_credit_score': self.min_credit_score,
            'max_credit_score': self.max_credit_score,
            'min_ltv': float(self.min_ltv) if self.min_ltv else None,
            'max_ltv': float(self.max_ltv) if self.max_ltv else None,
            'occupancy': self.occupancy,
            'property_type': self.property_type,
            'confidence_score': float(self.confidence_score) if self.confidence_score else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class RefinanceOpportunity(Base):
    """
    Identified refinance opportunities.
    Created when a client's current rate exceeds available rates by threshold.
    """
    __tablename__ = "refinance_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, index=True)  # Reference to loans table (no FK for SQLite compatibility)
    rate_sheet_id = Column(Integer, ForeignKey('rate_sheets.id'), index=True)

    # Client info (denormalized for quick access)
    client_name = Column(String(255))
    client_phone = Column(String(50))
    client_email = Column(String(255))

    # Current loan details
    current_rate = Column(Numeric(5, 3), nullable=False)
    current_loan_amount = Column(Numeric(12, 2), nullable=False)
    loan_type = Column(String(50))
    loan_term = Column(Integer)
    funded_date = Column(Date)

    # New rate opportunity
    new_rate = Column(Numeric(5, 3), nullable=False)
    rate_difference = Column(Numeric(5, 3), nullable=False)
    monthly_savings = Column(Numeric(10, 2))
    annual_savings = Column(Numeric(12, 2))

    # Scoring
    priority = Column(String(20), default='medium', index=True)  # low, medium, high, urgent
    opportunity_score = Column(Numeric(5, 2))

    # Outreach tracking
    status = Column(String(50), default='identified', index=True)
    sms_sent_at = Column(DateTime)
    sms_message_sid = Column(String(100))
    call_initiated_at = Column(DateTime)
    vapi_call_id = Column(String(100))
    call_status = Column(String(50))
    call_outcome = Column(String(100))
    call_duration = Column(Integer)
    call_summary = Column(Text)
    appointment_scheduled_at = Column(DateTime)

    # Metadata
    notes = Column(Text)
    created_by = Column(Integer)  # Reference to users table
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    rate_sheet = relationship("RateSheet", back_populates="opportunities")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'loan_id': self.loan_id,
            'rate_sheet_id': self.rate_sheet_id,
            'client_name': self.client_name,
            'client_phone': self.client_phone,
            'client_email': self.client_email,
            'current_rate': float(self.current_rate) if self.current_rate else None,
            'current_loan_amount': float(self.current_loan_amount) if self.current_loan_amount else None,
            'loan_type': self.loan_type,
            'loan_term': self.loan_term,
            'funded_date': self.funded_date.isoformat() if self.funded_date else None,
            'new_rate': float(self.new_rate) if self.new_rate else None,
            'rate_difference': float(self.rate_difference) if self.rate_difference else None,
            'monthly_savings': float(self.monthly_savings) if self.monthly_savings else None,
            'annual_savings': float(self.annual_savings) if self.annual_savings else None,
            'priority': self.priority,
            'opportunity_score': float(self.opportunity_score) if self.opportunity_score else None,
            'status': self.status,
            'sms_sent_at': self.sms_sent_at.isoformat() if self.sms_sent_at else None,
            'call_initiated_at': self.call_initiated_at.isoformat() if self.call_initiated_at else None,
            'vapi_call_id': self.vapi_call_id,
            'call_status': self.call_status,
            'call_outcome': self.call_outcome,
            'call_duration': self.call_duration,
            'call_summary': self.call_summary,
            'appointment_scheduled_at': self.appointment_scheduled_at.isoformat() if self.appointment_scheduled_at else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def calculate_priority(self) -> str:
        """Calculate priority based on savings potential."""
        monthly = float(self.monthly_savings) if self.monthly_savings else 0
        rate_drop = float(self.rate_difference) if self.rate_difference else 0

        if monthly >= 400 or rate_drop >= 1.0:
            return 'urgent'
        elif monthly >= 300 or rate_drop >= 0.75:
            return 'high'
        elif monthly >= 200 or rate_drop >= 0.5:
            return 'medium'
        else:
            return 'low'


def calculate_monthly_savings(
    current_rate: float,
    new_rate: float,
    loan_balance: float
) -> float:
    """
    Calculate estimated monthly savings from refinancing.

    Uses simple interest difference calculation.
    Actual savings depend on many factors including closing costs.
    """
    rate_difference = current_rate - new_rate
    if rate_difference <= 0:
        return 0.0

    monthly_savings = (rate_difference / 100 / 12) * loan_balance
    return round(monthly_savings, 2)


def calculate_annual_savings(monthly_savings: float) -> float:
    """Calculate annual savings from monthly savings."""
    return round(monthly_savings * 12, 2)
