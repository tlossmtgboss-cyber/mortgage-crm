from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Lead(Base):
    __tablename__ = 'leads'
    
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, index=True)
    phone = Column(String, index=True)
    status = Column(String, default='new')  # e.g., 'new', 'contacted', 'qualified', 'closed'
    source = Column(String)  # e.g., 'web', 'referral', 'zapier'
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Activity(Base):
    __tablename__ = 'activities'
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, index=True)  # Foreign key to Lead
    activity_type = Column(String, index=True)  # e.g., 'call', 'email', 'meeting', 'note'
    subject = Column(String)
    description = Column(Text)
    status = Column(String)  # e.g., 'scheduled', 'completed', 'cancelled'
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EventLog(Base):
    __tablename__ = 'event_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, index=True)  # "SMS", "CALL", "EMAIL"
    from_number = Column(String)
    body_or_status = Column(String)
    ts = Column(DateTime, default=datetime.datetime.utcnow)

class ActiveLoan(Base):
    __tablename__ = 'active_loans'
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, index=True)  # Foreign key to Lead
    loan_amount = Column(Float)
    loan_type = Column(String)  # e.g., 'conventional', 'FHA', 'VA'
    interest_rate = Column(Float)
    loan_term = Column(Integer)  # in months
    status = Column(String, default='processing')  # e.g., 'processing', 'approved', 'funded', 'closed'
    property_address = Column(String)
    estimated_close_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Portfolio(Base):
    __tablename__ = 'portfolio'
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, index=True)  # Foreign key to Lead
    loan_id = Column(Integer, index=True)  # Foreign key to ActiveLoan
    property_value = Column(Float)
    outstanding_balance = Column(Float)
    monthly_payment = Column(Float)
    status = Column(String, default='active')  # e.g., 'active', 'closed', 'defaulted'
    performance_rating = Column(String)  # e.g., 'excellent', 'good', 'fair', 'poor'
    last_payment_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
