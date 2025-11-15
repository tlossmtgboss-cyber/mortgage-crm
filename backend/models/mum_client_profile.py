"""
MUM Client Profile Model
MUM (Made-Up-My-Mind) / Portfolio clients - funded loans for ongoing relationship
Total fields: 22
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Text, Boolean, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class MUMClientProfile(Base):
    """
    MUM Client Profile - Portfolio clients for ongoing relationship management
    These are funded loans transitioned to servicing/relationship management
    Total fields: 22
    """
    __tablename__ = "mum_client_profiles"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Key to Active Loan
    original_loan_id = Column(UUID(as_uuid=True), ForeignKey('active_loan_profiles.id'), index=True)

    # ==================== PERSONAL INFORMATION (3 fields) ====================
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20))

    # ==================== LOAN INFORMATION (8 fields) ====================
    loan_number = Column(String(50), unique=True, index=True)
    original_close_date = Column(Date)
    original_rate = Column(Numeric(5, 3))  # Original interest rate
    current_rate = Column(Numeric(5, 3))  # Current market rate for comparison
    loan_balance = Column(Numeric(12, 2))  # Current outstanding balance
    estimated_savings = Column(Numeric(10, 2))  # Potential refinance savings
    refinance_opportunity = Column(Boolean, default=False)
    opportunity_notes = Column(Text)  # Details about refinance opportunity

    # ==================== TEAM MEMBERS (8 fields) ====================
    loan_officer = Column(String(255))
    loan_officer_email = Column(String(255))
    processor = Column(String(255))
    processor_email = Column(String(255))
    underwriter = Column(String(255))
    underwriter_email = Column(String(255))
    closer = Column(String(255))
    closer_email = Column(String(255))

    # ==================== ENGAGEMENT TRACKING (4 fields) ====================
    last_contact = Column(Date)
    next_touchpoint = Column(Date)
    engagement_score = Column(Integer)  # 0-100 score
    referrals_sent = Column(Integer, default=0)

    # ==================== ADDITIONAL TRACKING ====================
    notes = Column(Text)
    tags = Column(ARRAY(String))
    status = Column(String(50), default='active')  # 'active', 'refinanced', 'paid_off', 'inactive'

    # ==================== METADATA ====================
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_email_sync = Column(DateTime)
    last_rate_check = Column(DateTime)
    data_sources = Column(ARRAY(String))

    # Soft delete
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    # ==================== RELATIONSHIPS ====================
    original_loan = relationship("ActiveLoanProfile", back_populates="mum_client")
    email_interactions = relationship("EmailInteraction", back_populates="mum_client")

    def __repr__(self):
        return f"<MUMClientProfile {self.name} ({self.loan_number})>"

    def calculate_refinance_opportunity(self, current_market_rate: float):
        """
        Calculate if there's a refinance opportunity
        Typically if rate can drop by 0.5% or more
        """
        if self.original_rate and current_market_rate:
            rate_diff = float(self.original_rate) - current_market_rate
            if rate_diff >= 0.5:
                self.refinance_opportunity = True
                # Rough estimate: 0.5% drop saves ~$50/month per $100k
                if self.loan_balance:
                    monthly_savings = (rate_diff * float(self.loan_balance) / 100000) * 50
                    annual_savings = monthly_savings * 12
                    self.estimated_savings = round(annual_savings, 2)
            else:
                self.refinance_opportunity = False
                self.estimated_savings = 0

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'original_loan_id': str(self.original_loan_id) if self.original_loan_id else None,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'loan_number': self.loan_number,
            'original_close_date': self.original_close_date.isoformat() if self.original_close_date else None,
            'original_rate': float(self.original_rate) if self.original_rate else None,
            'current_rate': float(self.current_rate) if self.current_rate else None,
            'loan_balance': float(self.loan_balance) if self.loan_balance else None,
            'estimated_savings': float(self.estimated_savings) if self.estimated_savings else None,
            'refinance_opportunity': self.refinance_opportunity,
            'opportunity_notes': self.opportunity_notes,
            'loan_officer': self.loan_officer,
            'loan_officer_email': self.loan_officer_email,
            'processor': self.processor,
            'processor_email': self.processor_email,
            'underwriter': self.underwriter,
            'underwriter_email': self.underwriter_email,
            'closer': self.closer,
            'closer_email': self.closer_email,
            'last_contact': self.last_contact.isoformat() if self.last_contact else None,
            'next_touchpoint': self.next_touchpoint.isoformat() if self.next_touchpoint else None,
            'engagement_score': self.engagement_score,
            'referrals_sent': self.referrals_sent,
            'notes': self.notes,
            'tags': self.tags,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
