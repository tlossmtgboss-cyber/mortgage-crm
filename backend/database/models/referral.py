"""
Referral Partner Models

Models for managing referral partners and loan team members.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.referral import ReferralPartner, LoanTeamMember

    # Query referral partners
    partners = db.query(ReferralPartner).filter(ReferralPartner.status == "active").all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Numeric,
    Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base


# ============================================================================
# REFERRAL PARTNER
# ============================================================================

class ReferralPartner(Base):
    """Referral partners (realtors, financial advisors, etc.)"""
    __tablename__ = "referral_partners"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    name = Column(String, nullable=False, index=True)
    business_name = Column(String, nullable=False, default="")  # Required by DB schema
    contact_name = Column(String, nullable=False, default="")  # Required by DB schema
    category = Column(String, nullable=False, default="realtor")  # Required by DB schema
    company = Column(String)
    type = Column(String)
    phone = Column(String)
    phone_hash = Column(String(64), index=True)  # SHA-256 of normalized E.164 phone
    email = Column(String)
    referrals_in = Column(Integer, default=0)
    referrals_out = Column(Integer, default=0)
    closed_loans = Column(Integer, default=0)
    volume = Column(Numeric(18, 2), default=0.0)
    reciprocity_score = Column(Float, default=0.0)
    status = Column(String, default="active")
    loyalty_tier = Column(String, default="bronze")
    partner_category = Column(String, default="individual")  # 'individual' or 'team'
    last_interaction = Column(DateTime)
    notes = Column(Text)

    # Address fields
    street_address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    title = Column(String)  # Job title

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Owner of this referral partner

    # Relationships
    leads = relationship("Lead", back_populates="referral_partner")


# ============================================================================
# LOAN TEAM MEMBER
# ============================================================================

class LoanTeamMember(Base):
    """Team members assigned to a loan transaction (employees and external partners)"""
    __tablename__ = "loan_team_members"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # e.g., 'Realtor', 'Title Agent', 'Insurance Agent', 'Attorney', etc.
    email = Column(String)
    phone = Column(String)
    phone_hash = Column(String(64), index=True)  # SHA-256 of normalized E.164 phone
    company = Column(String)
    license_number = Column(String)
    notes = Column(Text)
    is_employee = Column(Boolean, default=False)  # True if internal employee, False if external partner
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Link to user if employee
    referral_partner_id = Column(Integer, ForeignKey("referral_partners.id"), nullable=True)  # Link to partner if external
    is_new = Column(Boolean, default=True)  # NEW badge - set to False after first view
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"))


# ============================================================================
# MUM CLIENT (Marketing/Mortgage Under Management)
# ============================================================================

class MUMClient(Base):
    """Clients in the Mortgage Under Management program"""
    __tablename__ = "mum_clients"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    # Map 'name' property to 'client_name' column in the database
    client_name = Column("client_name", String, nullable=False)
    email = Column(String)
    phone = Column(String)
    phone_hash = Column(String(64), index=True)  # SHA-256 of normalized E.164 phone
    loan_number = Column(String, unique=True, index=True)
    original_close_date = Column(DateTime, nullable=False)
    close_date = Column(DateTime)  # Alias for original_close_date
    closing_date = Column("closing_date", DateTime, nullable=False)  # NOT NULL in DB
    first_payment_date = Column("first_payment_date", DateTime, nullable=False)  # NOT NULL in DB
    days_since_funding = Column(Integer)
    original_rate = Column(Numeric(8, 4))
    current_rate = Column(Numeric(8, 4))
    # Database has several NOT NULL columns that we need to map to
    interest_rate = Column("interest_rate", Numeric(8, 4), nullable=False)  # NOT NULL in DB
    original_loan_amount = Column("original_loan_amount", Numeric(18, 2), nullable=False)  # NOT NULL in DB
    current_loan_amount = Column("current_loan_amount", Numeric(18, 2), nullable=False)  # NOT NULL in DB
    appraisal_value_at_closing = Column("appraisal_value_at_closing", Numeric(18, 2), nullable=False)  # NOT NULL in DB
    current_property_value = Column("current_property_value", Numeric(18, 2), nullable=False)  # NOT NULL in DB
    loan_balance = Column(Numeric(18, 2))  # Keep as separate column for compatibility
    refinance_opportunity = Column(Boolean, default=False)
    estimated_savings = Column(Numeric(18, 2))
    engagement_score = Column(Integer)
    status = Column(String)
    notes = Column(Text)
    last_contact = Column(DateTime)
    next_touchpoint = Column(DateTime)
    referrals_sent = Column(Integer, default=0)
    opportunity_notes = Column(Text)

    # Team members
    loan_officer = Column(String)
    loan_officer_email = Column(String)
    processor = Column(String)
    processor_email = Column(String)
    underwriter = Column(String)
    underwriter_email = Column(String)
    closer = Column(String)
    closer_email = Column(String)

    user_id = Column(Integer, ForeignKey("users.id"))
    # Valuation & Refinance fields (computed by agents)
    term = Column(Integer, default=360)
    maturity_date = Column(DateTime)
    estimated_equity = Column(Numeric(18, 2))
    current_ltv = Column(Numeric(8, 4))
    refi_score = Column(Integer, default=0)
    property_state = Column(String)
    property_zip = Column(String)

    salesforce_id = Column(String(100), index=True, nullable=True)  # Salesforce record ID
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Property to access client_name as 'name' for backwards compatibility
    @property
    def name(self):
        return self.client_name

    @name.setter
    def name(self, value):
        self.client_name = value


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ReferralPartner",
    "LoanTeamMember",
    "MUMClient",
]
