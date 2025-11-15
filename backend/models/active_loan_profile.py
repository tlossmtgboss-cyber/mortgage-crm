"""
Active Loan Profile Model
Complete active loan profile with all 53 fields from specification
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Text, Boolean, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class ActiveLoanProfile(Base):
    """
    Active Loan Profile - Loans in process from contract to funding
    Total fields: 53
    """
    __tablename__ = "active_loan_profiles"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Key to Lead
    lead_profile_id = Column(UUID(as_uuid=True), ForeignKey('lead_profiles.id'), index=True)

    # ==================== LOAN DETAILS (13 fields) ====================
    loan_number = Column(String(50), unique=True, nullable=False, index=True)
    amount = Column(Numeric(12, 2))
    rate = Column(Numeric(5, 3))  # Interest rate e.g., 6.125
    term = Column(Integer)  # Loan term in years, e.g., 30
    program = Column(String(50))  # Loan program type
    lock_date = Column(Date)
    lock_expiration = Column(Date)
    apr = Column(Numeric(5, 3))
    points = Column(Numeric(5, 3))
    lender = Column(String(255))
    appraisal_value = Column(Numeric(12, 2))
    ltv = Column(Numeric(5, 2))  # Loan-to-value ratio
    dti = Column(Numeric(5, 2))  # Debt-to-income ratio

    # ==================== PROPERTY INFORMATION (4 fields) ====================
    property_address = Column(Text)
    property_city = Column(String(100))
    property_state = Column(String(2))
    property_zip = Column(String(10))

    # ==================== TEAM MEMBERS (8 fields) ====================
    loan_officer_name = Column(String(255))
    loan_officer_email = Column(String(255))
    processor = Column(String(255))
    processor_email = Column(String(255))
    underwriter = Column(String(255))
    underwriter_email = Column(String(255))
    closer = Column(String(255))
    closer_email = Column(String(255))

    # ==================== MILESTONE DATES (27 fields) ====================
    # Contract & Appraisal
    contract_received_date = Column(Date)
    appraisal_ordered_date = Column(Date)
    appraisal_scheduled_date = Column(Date)
    appraisal_completed_date = Column(Date)
    appraisal_received_date = Column(Date)

    # Title & Insurance
    title_ordered_date = Column(Date)
    title_received_date = Column(Date)
    insurance_ordered_date = Column(Date)
    insurance_received_date = Column(Date)

    # Disclosures
    initial_disclosures_sent_date = Column(Date)
    initial_disclosures_signed_date = Column(Date)

    # Processing & Underwriting
    processor_submission_date = Column(Date)
    underwriting_submission_date = Column(Date)
    conditional_approval_date = Column(Date)
    conditions_sent_date = Column(Date)
    conditions_received_date = Column(Date)
    resubmission_date = Column(Date)
    clear_to_close_date = Column(Date)

    # Rate Lock
    rate_lock_date = Column(Date)
    rate_lock_expiration_date = Column(Date)
    rate_lock_extension_date = Column(Date)
    float_down_trigger_date = Column(Date)

    # Closing Documents
    closing_disclosure_sent_date = Column(Date)
    cd_received_signed_date = Column(Date)
    cd_delivered_date = Column(Date)
    final_cd_issue_date = Column(Date)
    final_closing_package_sent_date = Column(Date)

    # Final Milestone
    closing_scheduled_date = Column(Date)
    funding_date = Column(Date)

    # ==================== STATUS & TRACKING ====================
    status = Column(String(50), default='active')  # 'active', 'funded_closed', 'cancelled', 'denied'
    current_milestone = Column(String(100))  # Current stage in loan process
    days_to_closing = Column(Integer)  # Calculated field
    notes = Column(Text)
    tags = Column(ARRAY(String))

    # ==================== METADATA ====================
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_email_sync = Column(DateTime)
    last_milestone_update = Column(DateTime)
    data_sources = Column(ARRAY(String))

    # Soft delete
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    # ==================== RELATIONSHIPS ====================
    lead = relationship("LeadProfile", back_populates="active_loan")
    mum_client = relationship("MUMClientProfile", back_populates="original_loan", uselist=False)
    email_interactions = relationship("EmailInteraction", back_populates="active_loan")

    def __repr__(self):
        return f"<ActiveLoanProfile {self.loan_number}>"

    def calculate_days_to_closing(self):
        """Calculate days until closing"""
        if self.closing_scheduled_date:
            delta = self.closing_scheduled_date - datetime.utcnow().date()
            self.days_to_closing = delta.days
        return self.days_to_closing

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'lead_profile_id': str(self.lead_profile_id) if self.lead_profile_id else None,
            'loan_number': self.loan_number,
            'amount': float(self.amount) if self.amount else None,
            'rate': float(self.rate) if self.rate else None,
            'term': self.term,
            'program': self.program,
            'lock_date': self.lock_date.isoformat() if self.lock_date else None,
            'lock_expiration': self.lock_expiration.isoformat() if self.lock_expiration else None,
            'apr': float(self.apr) if self.apr else None,
            'points': float(self.points) if self.points else None,
            'lender': self.lender,
            'appraisal_value': float(self.appraisal_value) if self.appraisal_value else None,
            'ltv': float(self.ltv) if self.ltv else None,
            'dti': float(self.dti) if self.dti else None,
            'property_address': self.property_address,
            'property_city': self.property_city,
            'property_state': self.property_state,
            'property_zip': self.property_zip,
            'loan_officer_name': self.loan_officer_name,
            'loan_officer_email': self.loan_officer_email,
            'processor': self.processor,
            'processor_email': self.processor_email,
            'underwriter': self.underwriter,
            'underwriter_email': self.underwriter_email,
            'closer': self.closer,
            'closer_email': self.closer_email,
            'status': self.status,
            'current_milestone': self.current_milestone,
            'days_to_closing': self.days_to_closing,
            'notes': self.notes,
            'tags': self.tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            # Include milestone dates
            'contract_received_date': self.contract_received_date.isoformat() if self.contract_received_date else None,
            'appraisal_ordered_date': self.appraisal_ordered_date.isoformat() if self.appraisal_ordered_date else None,
            'clear_to_close_date': self.clear_to_close_date.isoformat() if self.clear_to_close_date else None,
            'closing_scheduled_date': self.closing_scheduled_date.isoformat() if self.closing_scheduled_date else None,
            'funding_date': self.funding_date.isoformat() if self.funding_date else None
        }
