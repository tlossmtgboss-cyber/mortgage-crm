"""
Partner Portal Pydantic Schemas

Request/response models for the Realtor/Partner Portal API.
Partners see sanitized loan data — milestones and stage names only,
never financial details (rates, fees, credit scores).
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# AUTH
# =============================================================================

class PartnerLoginRequest(BaseModel):
    """Partner login via email + magic link token."""
    email: EmailStr
    token: Optional[str] = None  # magic link token; if absent, triggers link send


class PartnerLoginResponse(BaseModel):
    """Returned after successful partner authentication."""
    session_token: str
    partner_id: int
    name: str
    email: str
    expires_at: datetime


class MagicLinkSentResponse(BaseModel):
    """Returned when a magic link has been dispatched."""
    message: str = "Magic link sent to your email"
    email: str


# =============================================================================
# PARTNER PROFILE
# =============================================================================

class PartnerProfileResponse(BaseModel):
    """Partner profile visible to the partner themselves."""
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    business_name: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    photo_url: Optional[str] = None
    loyalty_tier: Optional[str] = None
    referrals_in: int = 0
    closed_loans: int = 0
    status: Optional[str] = None

    class Config:
        from_attributes = True


class PartnerProfileUpdate(BaseModel):
    """Updatable partner profile fields."""
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    business_name: Optional[str] = None
    title: Optional[str] = None


# =============================================================================
# LOAN STATUS (sanitized — no financials)
# =============================================================================

class LoanMilestone(BaseModel):
    """A single milestone in the loan timeline."""
    stage: str
    label: str
    reached: bool = False
    reached_at: Optional[datetime] = None


class PartnerLoanSummary(BaseModel):
    """Sanitized loan summary visible to partners — no financial details."""
    loan_id: int
    borrower_name: str
    property_address: Optional[str] = None
    stage: str
    stage_label: str
    loan_type: Optional[str] = None
    closing_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    days_in_stage: int = 0
    sla_status: Optional[str] = None


class LoanTimelineResponse(BaseModel):
    """Full milestone timeline for a single loan."""
    loan_id: int
    borrower_name: str
    current_stage: str
    current_stage_label: str
    milestones: List[LoanMilestone] = []


# =============================================================================
# LEAD REFERRAL
# =============================================================================

class ReferLeadRequest(BaseModel):
    """Partner refers a new buyer/lead to their LO."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    property_address: Optional[str] = None
    loan_type: Optional[str] = None
    estimated_purchase_price: Optional[str] = None  # string to keep it vague


class ReferLeadResponse(BaseModel):
    """Confirmation after a lead referral is created."""
    lead_id: int
    message: str = "Lead referred successfully"
    borrower_name: str


# =============================================================================
# PRE-APPROVAL LETTER
# =============================================================================

class PreApprovalLetterRequestCreate(BaseModel):
    """Partner requests a pre-approval letter for a buyer."""
    buyer_name: str = Field(..., min_length=1)
    buyer_email: Optional[EmailStr] = None
    property_address: Optional[str] = None
    requested_amount: Optional[str] = None
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    notes: Optional[str] = None


class PreApprovalLetterResponse(BaseModel):
    """Pre-approval letter request status."""
    id: int
    buyer_name: str
    status: str
    letter_url: Optional[str] = None
    property_address: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# CO-MARKETING
# =============================================================================

class MarketingTemplateResponse(BaseModel):
    """A co-marketing template available to the partner."""
    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    template_type: Optional[str] = None  # flyer, social_post, email, etc.
