"""
Lead Profile Model
Complete lead profile with all 52 fields from specification
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Text, Boolean, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class LeadProfile(Base):
    """
    Lead Profile - Prospective borrowers in the pipeline
    Total fields: 52
    """
    __tablename__ = "lead_profiles"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # ==================== PERSONAL INFORMATION (5 fields) ====================
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    loan_number = Column(String(50), unique=True, index=True)

    # ==================== EMPLOYMENT INFORMATION (8 fields) ====================
    employment_status = Column(String(50))  # 'employed', 'self_employed', 'retired', 'unemployed'
    employer_name = Column(String(255))
    job_title = Column(String(255))
    years_at_job = Column(Numeric(4, 2))  # e.g., 3.5 years
    annual_income = Column(Numeric(12, 2))
    monthly_income = Column(Numeric(12, 2))
    other_income = Column(Numeric(12, 2))
    income_source = Column(String(100))  # Source of other income

    # ==================== LOAN INFORMATION (26 fields) ====================
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(2))
    zip_code = Column(String(10))
    property_type = Column(String(50))  # 'single_family', 'condo', 'townhouse', 'multi_family'
    property_value = Column(Numeric(12, 2))
    down_payment = Column(Numeric(12, 2))
    credit_score = Column(Integer)
    loan_amount = Column(Numeric(12, 2))
    interest_rate = Column(Numeric(5, 3))  # e.g., 6.125
    loan_term = Column(Integer)  # Years, e.g., 30
    loan_type = Column(String(50))  # 'conventional', 'fha', 'va', 'usda'
    lock_date = Column(Date)
    lock_expiration = Column(Date)
    apr = Column(Numeric(5, 3))
    points = Column(Numeric(5, 3))
    lender = Column(String(255))
    loan_officer = Column(String(255))
    processor = Column(String(255))
    underwriter = Column(String(255))
    closing_date = Column(Date)
    appraisal_value = Column(Numeric(12, 2))
    ltv = Column(Numeric(5, 2))  # Loan-to-value ratio (percentage)
    dti = Column(Numeric(5, 2))  # Debt-to-income ratio (percentage)

    # Stage tracking
    stage = Column(String(50), default='new')  # 'new', 'contacted', 'qualified', 'application', 'pre-approved'
    status = Column(String(50), default='active')  # 'active', 'converted', 'lost', 'archived'

    # ==================== IMPORTANT DATES (13 fields) ====================
    lead_created_date = Column(DateTime, default=datetime.utcnow)
    first_contact_attempt_date = Column(DateTime)
    first_contact_successful_date = Column(DateTime)
    lead_qualification_date = Column(DateTime)
    application_link_sent_date = Column(DateTime)
    application_started_date = Column(DateTime)
    application_completed_date = Column(DateTime)
    credit_pulled_date = Column(DateTime)
    preapproval_submission_date = Column(DateTime)
    preapproval_issued_date = Column(DateTime)
    realtor_referral_date = Column(DateTime)
    preapproval_expiration_date = Column(Date)
    rate_watch_enrollment_date = Column(DateTime)

    # ==================== METADATA & TRACKING ====================
    notes = Column(Text)
    tags = Column(ARRAY(String))  # Array of tags
    source = Column(String(100))  # 'website', 'referral', 'email', 'phone', 'social_media'
    referral_source = Column(String(255))  # Specific referral source name
    data_sources = Column(ARRAY(String))  # Which sources contributed data: ['email', 'manual_entry', 'import']

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_email_sync = Column(DateTime)
    last_activity_date = Column(DateTime)

    # Soft delete
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    # ==================== RELATIONSHIPS ====================
    active_loan = relationship("ActiveLoanProfile", back_populates="lead", uselist=False)
    email_interactions = relationship("EmailInteraction", back_populates="lead_profile")

    def __repr__(self):
        return f"<LeadProfile {self.first_name} {self.last_name} ({self.email})>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'loan_number': self.loan_number,
            'employment_status': self.employment_status,
            'employer_name': self.employer_name,
            'job_title': self.job_title,
            'years_at_job': float(self.years_at_job) if self.years_at_job else None,
            'annual_income': float(self.annual_income) if self.annual_income else None,
            'monthly_income': float(self.monthly_income) if self.monthly_income else None,
            'other_income': float(self.other_income) if self.other_income else None,
            'income_source': self.income_source,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'zip_code': self.zip_code,
            'property_type': self.property_type,
            'property_value': float(self.property_value) if self.property_value else None,
            'down_payment': float(self.down_payment) if self.down_payment else None,
            'credit_score': self.credit_score,
            'loan_amount': float(self.loan_amount) if self.loan_amount else None,
            'interest_rate': float(self.interest_rate) if self.interest_rate else None,
            'loan_term': self.loan_term,
            'loan_type': self.loan_type,
            'lock_date': self.lock_date.isoformat() if self.lock_date else None,
            'lock_expiration': self.lock_expiration.isoformat() if self.lock_expiration else None,
            'apr': float(self.apr) if self.apr else None,
            'points': float(self.points) if self.points else None,
            'lender': self.lender,
            'loan_officer': self.loan_officer,
            'processor': self.processor,
            'underwriter': self.underwriter,
            'closing_date': self.closing_date.isoformat() if self.closing_date else None,
            'appraisal_value': float(self.appraisal_value) if self.appraisal_value else None,
            'ltv': float(self.ltv) if self.ltv else None,
            'dti': float(self.dti) if self.dti else None,
            'stage': self.stage,
            'status': self.status,
            'notes': self.notes,
            'tags': self.tags,
            'source': self.source,
            'referral_source': self.referral_source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
