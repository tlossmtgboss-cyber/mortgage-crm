"""
MUM (Mortgages Under Management) Database Models
"""
from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, Text, DECIMAL, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class MUMClient(Base):
    """MUM Client - Represents a client with a mortgage under management"""
    __tablename__ = "mum_clients"

    id = Column(Integer, primary_key=True, index=True)

    # Client Information
    client_name = Column(String(200), nullable=False)
    email = Column(String(200))
    phone = Column(String(50))

    # Loan Information
    original_loan_amount = Column(DECIMAL(12, 2), nullable=False)  # Loan amount at closing
    current_loan_amount = Column(DECIMAL(12, 2), nullable=False)   # Current amortized balance
    interest_rate = Column(DECIMAL(6, 4), nullable=False)          # e.g., 6.5000 for 6.5%

    # Loan Identifiers
    servicing_loan_number = Column(String(100))
    origination_loan_number = Column(String(100))

    # Property Information
    appraisal_value_at_closing = Column(DECIMAL(12, 2), nullable=False)
    current_property_value = Column(DECIMAL(12, 2), nullable=False)

    # Servicing Information
    current_servicer = Column(String(200))
    has_escrow = Column(Boolean, default=False)

    # Payment Information
    current_principal_payment = Column(DECIMAL(10, 2))
    monthly_taxes = Column(DECIMAL(10, 2))
    monthly_insurance = Column(DECIMAL(10, 2))
    monthly_pmi = Column(DECIMAL(10, 2), nullable=True)  # Optional

    # Loan Details
    loan_type = Column(String(100))  # e.g., "30-Year Fixed", "FHA", "VA", "Jumbo"
    is_veteran = Column(Boolean, default=False)
    ltv = Column(DECIMAL(6, 4))  # Loan to Value ratio

    # Important Dates
    closing_date = Column(Date, nullable=False)
    first_payment_date = Column(Date, nullable=False)

    # Engagement & Opportunities
    last_contact_date = Column(Date)
    next_touchpoint_date = Column(Date)
    engagement_score = Column(Integer, default=0)  # 0-100

    # Opportunity Flags
    refinance_opportunity = Column(Boolean, default=False)
    heloc_opportunity = Column(Boolean, default=False)
    rate_rebound_opportunity = Column(Boolean, default=False)
    high_equity_opportunity = Column(Boolean, default=False)

    # Referrals
    referrals_sent = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)
    status = Column(String(50), default='active')  # active, paid_off, refinanced, sold

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Calculated fields (stored for performance)
    equity_amount = Column(DECIMAL(12, 2))
    equity_percentage = Column(DECIMAL(6, 4))
    days_since_funding = Column(Integer)
    portfolio_age_months = Column(Integer)

    # Revenue tracking
    annual_servicing_revenue = Column(DECIMAL(10, 2))
    lifetime_value = Column(DECIMAL(10, 2))

    def __repr__(self):
        return f"<MUMClient {self.client_name} - ${self.current_loan_amount}>"


class MUMTransaction(Base):
    """Track MUM portfolio changes over time"""
    __tablename__ = "mum_transactions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey('mum_clients.id'))

    transaction_type = Column(String(50))  # added, lost, refinanced, paid_off
    transaction_date = Column(Date, nullable=False)
    loan_amount = Column(DECIMAL(12, 2))

    notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    client = relationship("MUMClient", backref="transactions")
