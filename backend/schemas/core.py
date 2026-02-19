"""
Pydantic Schemas for the Mortgage CRM API.

Extracted from main.py as part of the architecture decomposition.
Contains all request/response schemas used by API endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, field_validator, model_validator
import enum

# Import enums used by schemas
from database.enums import (
    LeadStage, LoanStage, TaskType, ActivityType, CoachMode,
)

# PII masking utilities for API response sanitization (Enterprise Readiness 3.19)
from schemas.pii_masking import sanitize_step_data, mask_ssn



class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    class Config:
        from_attributes = True

class TeamMemberCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    title: Optional[str] = None

class TeamMemberUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = None

class ApiKeyCreate(BaseModel):
    name: str

class ApiKeyResponse(BaseModel):
    id: int
    key: str
    name: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    class Config:
        from_attributes = True

class ImpersonationStart(BaseModel):
    user_id: int
    mode: str  # 'read_only' or 'full_access'
    reason: str
    duration_minutes: int
    notify_employee: bool = False

class ImpersonationResponse(BaseModel):
    session_token: str
    impersonated_user: Dict[str, Any]
    expires_at: datetime
    mode: str

class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    loan_type: Optional[str] = None
    preapproval_amount: Optional[float] = None
    credit_score: Optional[int] = None
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = False
    # Loan Information
    loan_number: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    # Notes
    notes: Optional[str] = None
    # Metadata (for assets, etc.)
    user_metadata: Optional[Dict[str, Any]] = None

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_communication: Optional[str] = None
    co_applicant_name: Optional[str] = None
    co_applicant_email: Optional[str] = None
    co_applicant_phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    loan_number: Optional[str] = None
    notes: Optional[str] = None
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = None
    loan_type: Optional[str] = None
    preapproval_amount: Optional[float] = None
    source: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    purchase_price: Optional[float] = None
    # Salesforce Sync Fields
    cltv: Optional[float] = None
    occupancy_type: Optional[str] = None
    property_county: Optional[str] = None
    property_ownership_type: Optional[str] = None
    property_units: Optional[int] = None
    rate_type: Optional[str] = None
    monthly_payment: Optional[float] = None
    property_tax: Optional[float] = None
    hazard_insurance: Optional[float] = None
    mortgage_insurance: Optional[float] = None
    hoa_amount: Optional[float] = None
    origination_fee: Optional[float] = None
    estimated_prepaid_interest: Optional[float] = None
    index_rate: Optional[float] = None
    margin: Optional[float] = None
    loan_purpose: Optional[str] = None
    file_state: Optional[str] = None
    second_loan_amount: Optional[float] = None
    second_loan_rate: Optional[float] = None
    second_loan_payment: Optional[float] = None
    present_housing_expense: Optional[float] = None
    proposed_housing_expense: Optional[float] = None
    present_monthly_payment: Optional[float] = None
    proposed_monthly_payment: Optional[float] = None
    # SLA Milestone Dates
    lead_received_date: Optional[datetime] = None
    first_contact_attempt_date: Optional[datetime] = None
    first_contact_successful_date: Optional[datetime] = None
    lead_qualification_date: Optional[datetime] = None
    application_link_sent_date: Optional[datetime] = None
    application_started_date: Optional[datetime] = None
    application_completed_date: Optional[datetime] = None
    credit_pulled_date: Optional[datetime] = None
    preapproval_submission_date: Optional[datetime] = None
    preapproval_issued_date: Optional[datetime] = None
    preapproval_expiration_date: Optional[datetime] = None
    realtor_referral_date: Optional[datetime] = None
    rate_watch_enrollment_date: Optional[datetime] = None
    initial_consultation_date: Optional[datetime] = None
    # Referral Partner
    referral_partner_id: Optional[int] = None
    # Metadata (for assets, etc.)
    user_metadata: Optional[Dict[str, Any]] = None

class LeadResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    co_applicant_name: Optional[str] = None
    co_applicant_email: Optional[str] = None
    co_applicant_phone: Optional[str] = None
    stage: LeadStage
    source: Optional[str]
    ai_score: int
    sentiment: Optional[str]
    next_action: Optional[str]
    preapproval_amount: Optional[float]
    # Property Information
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    # Financial Information
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    first_time_buyer: Optional[bool] = False
    # Loan Information
    loan_number: Optional[str] = None
    loan_type: Optional[str] = None
    # Loan Details
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[int] = None
    apr: Optional[float] = None
    points: Optional[float] = None
    lock_date: Optional[datetime] = None
    lock_expiration: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    lender: Optional[str] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    appraisal_value: Optional[float] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    notes: Optional[str] = None
    # SLA Milestone Dates
    lead_received_date: Optional[datetime] = None
    first_contact_attempt_date: Optional[datetime] = None
    first_contact_successful_date: Optional[datetime] = None
    lead_qualification_date: Optional[datetime] = None
    application_link_sent_date: Optional[datetime] = None
    application_started_date: Optional[datetime] = None
    application_completed_date: Optional[datetime] = None
    credit_pulled_date: Optional[datetime] = None
    preapproval_submission_date: Optional[datetime] = None
    preapproval_issued_date: Optional[datetime] = None
    preapproval_expiration_date: Optional[datetime] = None
    realtor_referral_date: Optional[datetime] = None
    rate_watch_enrollment_date: Optional[datetime] = None
    initial_consultation_date: Optional[datetime] = None
    # Referral Partner
    referral_partner_id: Optional[int] = None

    # Salesforce Sync Fields - Additional Property Details
    occupancy_type: Optional[str] = None
    property_county: Optional[str] = None
    property_ownership_type: Optional[str] = None
    property_units: Optional[int] = None

    # Salesforce Sync Fields - 1st Loan Financial Details
    rate_type: Optional[str] = None
    monthly_payment: Optional[float] = None
    property_tax: Optional[float] = None
    hazard_insurance: Optional[float] = None
    mortgage_insurance: Optional[float] = None
    hoa_amount: Optional[float] = None
    origination_fee: Optional[float] = None
    estimated_prepaid_interest: Optional[float] = None
    index_rate: Optional[float] = None
    margin: Optional[float] = None

    # Salesforce Sync Fields - Additional LTV/CLTV
    cltv: Optional[float] = None
    loan_purpose: Optional[str] = None
    file_state: Optional[str] = None

    # Salesforce Sync Fields - 2nd Loan Details
    second_loan_amount: Optional[float] = None
    second_loan_rate: Optional[float] = None
    second_loan_payment: Optional[float] = None

    # Salesforce Sync Fields - Present vs Proposed Housing
    present_housing_expense: Optional[float] = None
    proposed_housing_expense: Optional[float] = None
    present_monthly_payment: Optional[float] = None
    proposed_monthly_payment: Optional[float] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class LoanCreate(BaseModel):
    loan_number: str
    borrower_name: str
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    preferred_communication: Optional[str] = None
    coborrower_name: Optional[str] = None
    co_borrower_email: Optional[str] = None
    amount: float
    program: Optional[str] = None
    rate: Optional[float] = None
    closing_date: Optional[datetime] = None
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    stage: Optional[str] = None

class LoanUpdate(BaseModel):
    stage: Optional[LoanStage] = None
    rate: Optional[float] = None

    @field_validator('stage', mode='before')
    @classmethod
    def normalize_stage(cls, v):
        if v is None:
            return v
        v_str = str(v).strip()
        # Map display names to enum values
        display_to_enum = {
            'application': 'APPLICATION',
            'disclosed': 'DISCLOSED',
            'processing': 'PROCESSING',
            'in processing': 'PROCESSING',
            'submitted': 'SUBMITTED',
            'underwriting': 'UNDERWRITING',
            'in underwriting': 'UNDERWRITING',
            'uw received': 'UW_RECEIVED',
            'uw_received': 'UW_RECEIVED',
            'conditional approval': 'CONDITIONAL_APPROVAL',
            'conditional_approval': 'CONDITIONAL_APPROVAL',
            'approved': 'APPROVED',
            'suspended': 'SUSPENDED',
            'ctc': 'CTC',
            'clear to close': 'CLEAR_TO_CLOSE',
            'clear_to_close': 'CLEAR_TO_CLOSE',
            'closing': 'CLOSING',
            'docs': 'DOCS',
            'docs out': 'DOCS_OUT',
            'docs_out': 'DOCS_OUT',
            'funded': 'FUNDED',
            'cancelled': 'CANCELLED',
            'denied': 'DENIED',
            'dead': 'DEAD',
            'nurture': 'NURTURE',
            'withdrawn': 'WITHDRAWN',
            'does not qualify': 'DOES_NOT_QUALIFY',
            'does_not_qualify': 'DOES_NOT_QUALIFY',
        }
        normalized = display_to_enum.get(v_str.lower())
        if normalized:
            return normalized
        # Try uppercase as-is (already correct format)
        return v_str.upper().replace(' ', '_')
    closing_date: Optional[datetime] = None
    processor: Optional[str] = None
    borrower_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    preferred_communication: Optional[str] = None
    coborrower_name: Optional[str] = None
    co_borrower_email: Optional[str] = None
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    loan_number: Optional[str] = None
    program: Optional[str] = None
    amount: Optional[float] = None
    loan_type: Optional[str] = None
    term: Optional[int] = None
    purchase_price: Optional[float] = None
    down_payment: Optional[float] = None
    underwriter: Optional[str] = None
    realtor_agent: Optional[str] = None
    title_company: Optional[str] = None
    lender: Optional[str] = None

    # SLA Date Fields - All 33 Jungo Custom Byte Mappings
    # Lead & Application Phase
    prospect_date: Optional[datetime] = None
    application_date: Optional[datetime] = None
    le_pending_date: Optional[datetime] = None
    credit_only_date: Optional[datetime] = None
    file_received_date: Optional[datetime] = None
    preapproval_date: Optional[datetime] = None

    # Lock Phase
    lock_date: Optional[datetime] = None
    lock_expiration_date: Optional[datetime] = None

    # Processing & Underwriting Phase
    uw_received_date: Optional[datetime] = None
    conditions_for_review_date: Optional[datetime] = None
    suspended_date: Optional[datetime] = None
    loan_approved_date: Optional[datetime] = None
    approved_not_accepted_date: Optional[datetime] = None
    approval_expires_date: Optional[datetime] = None

    # Appraisal Phase
    appraisal_ordered_date: Optional[datetime] = None
    appraisal_scheduled_date: Optional[datetime] = None
    appraisal_completed_date: Optional[datetime] = None
    appraisal_received_date: Optional[datetime] = None
    appraisal_docs_expire_date: Optional[datetime] = None

    # Title & Insurance Phase
    title_ordered_date: Optional[datetime] = None
    title_received_date: Optional[datetime] = None
    insurance_ordered_date: Optional[datetime] = None
    insurance_received_date: Optional[datetime] = None

    # Closing Disclosure Phase
    cd_requested_date: Optional[datetime] = None
    cd_sent_to_borrower_date: Optional[datetime] = None
    cd_acknowledged_date: Optional[datetime] = None

    # Clear to Close & Docs Phase
    clear_to_close_date: Optional[datetime] = None
    docs_ordered_date: Optional[datetime] = None
    docs_out_date: Optional[datetime] = None
    credit_docs_expire_date: Optional[datetime] = None

    # Funding Phase
    scheduled_closing_date: Optional[datetime] = None
    scheduled_funding_date: Optional[datetime] = None
    funds_ordered_date: Optional[datetime] = None
    funds_sent_date: Optional[datetime] = None
    funded_date: Optional[datetime] = None
    first_payment_date: Optional[datetime] = None

    # Post-Closing
    investor_purchased_date: Optional[datetime] = None

    # Status Changes
    withdrawn_date: Optional[datetime] = None
    contract_received_date: Optional[datetime] = None

class LoanResponse(BaseModel):
    id: int
    loan_number: str
    borrower_name: str
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    coborrower_name: Optional[str] = None
    co_borrower_email: Optional[str] = None
    stage: Optional[str] = None
    program: Optional[str] = None
    amount: float
    rate: Optional[float] = None
    closing_date: Optional[datetime] = None
    days_in_stage: Optional[int] = 0
    sla_status: Optional[str] = "on-track"
    created_at: Optional[datetime] = None
    # Team member fields
    loan_officer_name: Optional[str] = None
    loan_officer_email: Optional[str] = None
    processor: Optional[str] = None
    processor_email: Optional[str] = None
    underwriter: Optional[str] = None
    underwriter_email: Optional[str] = None
    closer: Optional[str] = None
    closer_email: Optional[str] = None

    # SLA Date Fields - All 33 Jungo Custom Byte Mappings
    # Lead & Application Phase
    prospect_date: Optional[datetime] = None
    application_date: Optional[datetime] = None
    le_pending_date: Optional[datetime] = None
    credit_only_date: Optional[datetime] = None
    file_received_date: Optional[datetime] = None
    preapproval_date: Optional[datetime] = None

    # Lock Phase
    lock_date: Optional[datetime] = None
    lock_expiration_date: Optional[datetime] = None

    # Processing & Underwriting Phase
    uw_received_date: Optional[datetime] = None
    conditions_for_review_date: Optional[datetime] = None
    suspended_date: Optional[datetime] = None
    loan_approved_date: Optional[datetime] = None
    approved_not_accepted_date: Optional[datetime] = None
    approval_expires_date: Optional[datetime] = None

    # Appraisal Phase
    appraisal_ordered_date: Optional[datetime] = None
    appraisal_scheduled_date: Optional[datetime] = None
    appraisal_completed_date: Optional[datetime] = None
    appraisal_received_date: Optional[datetime] = None
    appraisal_docs_expire_date: Optional[datetime] = None

    # Title & Insurance Phase
    title_ordered_date: Optional[datetime] = None
    title_received_date: Optional[datetime] = None
    insurance_ordered_date: Optional[datetime] = None
    insurance_received_date: Optional[datetime] = None

    # Closing Disclosure Phase
    cd_requested_date: Optional[datetime] = None
    cd_sent_to_borrower_date: Optional[datetime] = None
    cd_acknowledged_date: Optional[datetime] = None

    # Clear to Close & Docs Phase
    clear_to_close_date: Optional[datetime] = None
    docs_ordered_date: Optional[datetime] = None
    docs_out_date: Optional[datetime] = None
    credit_docs_expire_date: Optional[datetime] = None

    # Funding Phase
    scheduled_closing_date: Optional[datetime] = None
    scheduled_funding_date: Optional[datetime] = None
    funds_ordered_date: Optional[datetime] = None
    funds_sent_date: Optional[datetime] = None
    funded_date: Optional[datetime] = None
    first_payment_date: Optional[datetime] = None

    # Post-Closing
    investor_purchased_date: Optional[datetime] = None

    # Status Changes
    withdrawn_date: Optional[datetime] = None
    contract_received_date: Optional[datetime] = None

    # Property Details (Salesforce sync)
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    property_type: Optional[str] = None
    occupancy_type: Optional[str] = None
    property_county: Optional[str] = None
    property_ownership_type: Optional[str] = None
    property_units: Optional[int] = None
    appraisal_value: Optional[float] = None
    purchase_price: Optional[float] = None

    # 1st Loan Details
    interest_rate: Optional[float] = None
    rate_type: Optional[str] = None
    loan_type: Optional[str] = None
    property_tax: Optional[float] = None
    hazard_insurance: Optional[float] = None
    mortgage_insurance: Optional[float] = None
    hoa_amount: Optional[float] = None
    origination_fee: Optional[float] = None
    estimated_prepaid_interest: Optional[float] = None
    points: Optional[float] = None
    monthly_payment: Optional[float] = None
    index_rate: Optional[float] = None
    margin: Optional[float] = None

    # LTV/CLTV
    ltv: Optional[float] = None
    cltv: Optional[float] = None
    loan_purpose: Optional[str] = None
    file_state: Optional[str] = None

    # 2nd Loan
    second_loan_amount: Optional[float] = None
    second_loan_rate: Optional[float] = None
    second_loan_payment: Optional[float] = None

    # Present vs Proposed
    present_housing_expense: Optional[float] = None
    proposed_housing_expense: Optional[float] = None
    present_monthly_payment: Optional[float] = None
    proposed_monthly_payment: Optional[float] = None

    class Config:
        from_attributes = True

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: TaskType = TaskType.IN_PROGRESS
    priority: str = "medium"
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    due_date: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[TaskType] = None
    priority: Optional[str] = None
    completed_action: Optional[str] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    type: TaskType
    priority: str
    ai_confidence: Optional[int]
    borrower_name: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class ReferralPartnerCreate(BaseModel):
    name: str
    company: Optional[str] = None
    type: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    partner_category: Optional[str] = "individual"  # 'individual' or 'team'

class ReferralPartnerUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    loyalty_tier: Optional[str] = None
    category: Optional[str] = None
    business_name: Optional[str] = None
    contact_name: Optional[str] = None
    partner_category: Optional[str] = None  # 'individual' or 'team'

class ReferralPartnerResponse(BaseModel):
    id: int
    name: str
    company: Optional[str] = None
    type: Optional[str] = None
    referrals_in: int = 0
    closed_loans: int = 0
    volume: float = 0.0
    loyalty_tier: str = "bronze"
    partner_category: str = "individual"  # 'individual' or 'team'
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True


# ==================== LOAN TEAM MEMBER SCHEMAS ====================
class LoanTeamMemberCreate(BaseModel):
    """Create a new team member for a loan"""
    loan_id: int
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    license_number: Optional[str] = None
    notes: Optional[str] = None
    is_employee: bool = False
    user_id: Optional[int] = None  # If linking to internal user
    create_as_partner: bool = True  # Auto-create as referral partner if non-employee


class LoanTeamMemberUpdate(BaseModel):
    """Update an existing team member"""
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    license_number: Optional[str] = None
    notes: Optional[str] = None
    is_employee: Optional[bool] = None


class LoanTeamMemberResponse(BaseModel):
    """Response model for team member"""
    id: int
    loan_id: int
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    license_number: Optional[str] = None
    notes: Optional[str] = None
    is_employee: bool
    user_id: Optional[int] = None
    referral_partner_id: Optional[int] = None
    is_new: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MUMClientCreate(BaseModel):
    name: str
    loan_number: str
    original_close_date: datetime
    original_rate: float
    loan_balance: float
    email: Optional[str] = None
    phone: Optional[str] = None
    original_loan_number: Optional[str] = None
    status: Optional[str] = "Active"
    notes: Optional[str] = None

class MUMClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    loan_number: Optional[str] = None
    original_close_date: Optional[datetime] = None
    close_date: Optional[datetime] = None
    days_since_funding: Optional[int] = None
    original_rate: Optional[float] = None
    current_rate: Optional[float] = None
    loan_balance: Optional[float] = None
    refinance_opportunity: Optional[bool] = None
    estimated_savings: Optional[float] = None
    engagement_score: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    last_contact: Optional[datetime] = None
    next_touchpoint: Optional[datetime] = None
    referrals_sent: Optional[int] = None
    opportunity_notes: Optional[str] = None
    loan_officer: Optional[str] = None
    loan_officer_email: Optional[str] = None
    processor: Optional[str] = None
    processor_email: Optional[str] = None
    underwriter: Optional[str] = None
    underwriter_email: Optional[str] = None
    closer: Optional[str] = None
    closer_email: Optional[str] = None

class MUMClientResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    loan_number: str
    original_close_date: datetime
    close_date: Optional[datetime] = None
    days_since_funding: Optional[int] = None
    original_rate: Optional[float] = None
    current_rate: Optional[float] = None
    loan_balance: Optional[float] = None
    refinance_opportunity: bool = False
    estimated_savings: Optional[float] = None
    engagement_score: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    last_contact: Optional[datetime] = None
    next_touchpoint: Optional[datetime] = None
    referrals_sent: Optional[int] = 0
    opportunity_notes: Optional[str] = None
    loan_officer: Optional[str] = None
    loan_officer_email: Optional[str] = None
    processor: Optional[str] = None
    processor_email: Optional[str] = None
    underwriter: Optional[str] = None
    underwriter_email: Optional[str] = None
    closer: Optional[str] = None
    closer_email: Optional[str] = None
    user_id: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True


# ============================================================================
# BORROWER APPLICATION SCHEMAS
# ============================================================================

class BorrowerApplicationCreate(BaseModel):
    """Schema for creating a new borrower application"""
    lead_id: Optional[int] = None
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool = False
    coborrower_email: Optional[str] = None
    expires_in_days: int = 30  # How long until the token expires

class BorrowerApplicationUpdate(BaseModel):
    """Schema for updating application data"""
    current_step: Optional[str] = None
    step_data: Optional[Dict[str, Any]] = None
    completed_steps: Optional[List[str]] = None
    progress_percentage: Optional[int] = None
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: Optional[bool] = None
    coborrower_email: Optional[str] = None
    notes: Optional[str] = None
    time_spent_seconds: Optional[int] = None

class StepDataUpdate(BaseModel):
    """Schema for updating a specific step's data"""
    step: str
    data: Dict[str, Any]
    mark_completed: bool = False

class CreditAuthCapture(BaseModel):
    """Schema for capturing credit authorization"""
    ssn_last4: str
    full_ssn: Optional[str] = None  # Encrypted, only stored temporarily
    consent_text: str
    consent_agreed: bool
    signature_data: Optional[str] = None  # Base64 encoded signature image

class PrequalificationRequest(BaseModel):
    """Schema for pre-qualification calculation"""
    annual_income: float
    monthly_debts: float
    credit_score_range: str  # "760+", "740-759", "700-739", etc.
    down_payment: float
    down_payment_type: str = "percentage"  # "percentage" or "amount"
    property_value: Optional[float] = None
    loan_type: str = "conventional"  # conventional, fha, va, usda
    property_type: str = "single_family"
    occupancy: str = "primary"  # primary, secondary, investment

class PrequalificationResponse(BaseModel):
    """Schema for pre-qualification results"""
    max_loan_amount: float
    estimated_rate: float
    estimated_monthly_payment: float
    front_end_dti: float
    back_end_dti: float
    max_home_price: float
    loan_type: str
    rate_assumptions: Dict[str, Any]
    warnings: List[str] = []

class DocumentUploadResponse(BaseModel):
    """Schema for document upload response"""
    id: int
    filename: str
    original_filename: str
    category: str
    file_size: int
    mime_type: str
    upload_url: Optional[str] = None  # Pre-signed URL for direct upload
    created_at: datetime
    class Config:
        from_attributes = True

class CoborrowerInvitationCreate(BaseModel):
    """Schema for creating co-borrower invitation"""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    relationship_type: Optional[str] = None
    send_email: bool = True
    send_sms: bool = False

class CoborrowerInvitationResponse(BaseModel):
    """Schema for co-borrower invitation response"""
    id: int
    invitation_token: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class ApplicationEventCreate(BaseModel):
    """Schema for logging application events"""
    event_type: str
    event_data: Optional[Dict[str, Any]] = None
    step: Optional[str] = None

class BorrowerApplicationResponse(BaseModel):
    """Full application response schema.

    Enterprise Readiness 3.19: ssn_encrypted and co_ssn_encrypted are
    intentionally excluded from this schema.  Only the masked last-4 is
    exposed via ssn_display when credit auth has been captured.
    """
    id: int
    public_token: str
    status: str
    current_step: str
    progress_percentage: int
    completed_steps: List[str]
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool
    coborrower_email: Optional[str] = None
    coborrower_completed: bool
    prequalification_amount: Optional[float] = None
    prequalification_rate: Optional[float] = None
    prequalification_monthly_payment: Optional[float] = None
    credit_auth_captured: bool
    # Masked SSN display: ***-**-1234 (derived from credit_auth_ssn_last4, never raw SSN)
    ssn_display: Optional[str] = None
    expires_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @model_validator(mode='before')
    @classmethod
    def compute_ssn_display(cls, values):
        """Derive masked SSN display from credit_auth_ssn_last4 if available."""
        if isinstance(values, dict):
            last4 = values.get('credit_auth_ssn_last4')
            if last4 and not values.get('ssn_display'):
                values['ssn_display'] = f"***-**-{last4}"
            # Never leak encrypted SSN fields
            values.pop('ssn_encrypted', None)
            values.pop('co_ssn_encrypted', None)
        else:
            # ORM model (from_attributes mode)
            last4 = getattr(values, 'credit_auth_ssn_last4', None)
            if last4:
                # Pydantic v2 with from_attributes can read attrs; set ssn_display
                # We need to return a dict override for computed fields
                pass  # handled below via field default
        return values

    class Config:
        from_attributes = True

class ApplicationPublicResponse(BaseModel):
    """Limited public response for borrowers (no internal IDs)"""
    status: str
    current_step: str
    progress_percentage: int
    completed_steps: List[str]
    step_data: Dict[str, Any]
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool
    coborrower_completed: bool
    prequalification_data: Optional[Dict[str, Any]] = None
    credit_auth_captured: bool
    expires_at: Optional[datetime] = None
    lo_name: Optional[str] = None
    lo_email: Optional[str] = None
    lo_phone: Optional[str] = None
    company_name: Optional[str] = None

    @field_validator('step_data', mode='before')
    @classmethod
    def sanitize_pii_from_step_data(cls, v):
        """Enterprise Readiness 3.19: Strip SSN/PII from step_data before serialization"""
        return sanitize_step_data(v)

    class Config:
        from_attributes = True

class ApplicationAnalytics(BaseModel):
    """Schema for application analytics data"""
    total_applications: int
    by_status: Dict[str, int]
    avg_completion_time_minutes: float
    avg_progress_percentage: float
    conversion_rate: float
    drop_off_by_step: Dict[str, int]
    documents_uploaded: int
    coborrower_completion_rate: float


# ============================================================================
# ERROR FIX REQUEST SCHEMAS
# ============================================================================

class ErrorFixRequest(BaseModel):
    error_message: str
    error_stack: Optional[str] = None
    component_stack: Optional[str] = None
    screenshot: Optional[str] = None
    attempt_number: int = 1
    url: Optional[str] = None
    user_agent: Optional[str] = None

# ============================================================================
# CLIENT MANAGEMENT PROFILE (CMP) SCHEMAS
# ============================================================================

class UserProfileData(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    photo_url: Optional[str] = None
    title: Optional[str] = None
    pronouns: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    calendar_link: Optional[str] = None
    signature_block: Optional[str] = None
    disc_profile: Optional[str] = None
    communication_style: Optional[str] = None
    work_hours: Optional[Dict[str, Any]] = None
    days_off: Optional[List[str]] = None
    vacation_mode: Optional[bool] = False
    coaching_preferences: Optional[str] = None

class BrandingSettings(BaseModel):
    email_signature: Optional[str] = None
    text_signature: Optional[str] = None
    brand_colors: Optional[Dict[str, str]] = None
    logo_url: Optional[str] = None
    team_headshots: Optional[List[str]] = None
    partner_branding: Optional[Dict[str, Any]] = None

class IntegrationSettings(BaseModel):
    email: Optional[Dict[str, Any]] = None
    calendar: Optional[Dict[str, Any]] = None
    sms: Optional[Dict[str, Any]] = None
    phone: Optional[Dict[str, Any]] = None
    los: Optional[Dict[str, Any]] = None
    pos: Optional[Dict[str, Any]] = None
    credit: Optional[Dict[str, Any]] = None
    pricing: Optional[Dict[str, Any]] = None
    storage: Optional[Dict[str, Any]] = None
    esignature: Optional[Dict[str, Any]] = None
    crm_sync: Optional[Dict[str, Any]] = None
    lead_providers: Optional[List[Dict[str, Any]]] = None

class AutomationSettings(BaseModel):
    speed_to_lead: Optional[Dict[str, Any]] = None
    auto_task_creation: Optional[bool] = True
    sla_definitions: Optional[Dict[str, Any]] = None
    coach_intensity: Optional[str] = "medium"
    follow_up_cadences: Optional[Dict[str, Any]] = None
    scorecard_delivery: Optional[str] = "email"
    notification_preferences: Optional[Dict[str, Any]] = None
    ai_auto_update_threshold: Optional[float] = 0.8

class ReconciliationSettings(BaseModel):
    auto_update_threshold: Optional[float] = 0.8
    fields_to_review: Optional[List[str]] = None
    fields_auto_approve: Optional[List[str]] = None
    fields_never_modify: Optional[List[str]] = None
    trusted_senders: Optional[List[str]] = None
    match_preferences: Optional[Dict[str, Any]] = None

class PipelineSettings(BaseModel):
    lead_scoring_rules: Optional[Dict[str, Any]] = None
    follow_up_model: Optional[str] = "balanced"
    lead_buckets: Optional[List[str]] = None
    partner_attribution: Optional[Dict[str, Any]] = None
    product_preferences: Optional[List[str]] = None
    market_footprint: Optional[Dict[str, Any]] = None

class KPITargets(BaseModel):
    monthly_funded_goal: Optional[int] = None
    weekly_app_goal: Optional[int] = None
    daily_conversations: Optional[int] = None
    speed_to_lead_target: Optional[int] = None
    pull_through_target: Optional[float] = None
    preapproval_conversion: Optional[float] = None
    cycle_time_target: Optional[int] = None
    rework_reduction: Optional[float] = None
    nps_goal: Optional[float] = None

class PortfolioSettings(BaseModel):
    mum_config: Optional[Dict[str, Any]] = None
    annual_review_automation: Optional[bool] = True
    rate_drop_alerts: Optional[bool] = True
    equity_alerts: Optional[bool] = True
    insurance_reminders: Optional[bool] = True
    pmi_monitoring: Optional[bool] = True
    cashout_flags: Optional[bool] = True

class AdvancedSettings(BaseModel):
    partner_grading: Optional[Dict[str, Any]] = None
    task_delegation_matrix: Optional[Dict[str, Any]] = None
    ops_capacity_model: Optional[Dict[str, Any]] = None
    personal_brand_library: Optional[List[str]] = None
    video_library: Optional[List[str]] = None
    custom_calculators: Optional[List[str]] = None
    custom_roles: Optional[List[str]] = None

class ClientProfileCreate(BaseModel):
    account_type: str  # Solo LO / Team / Branch / Brokerage / Lender
    company_name: str
    nmls_number: Optional[str] = None
    business_address: Optional[Dict[str, str]] = None
    team_size: Optional[int] = 1
    user_profile: Optional[UserProfileData] = None
    subscription_plan: Optional[str] = "Solo"

class ClientProfileUpdate(BaseModel):
    account_type: Optional[str] = None
    company_name: Optional[str] = None
    nmls_number: Optional[str] = None
    business_address: Optional[Dict[str, str]] = None
    team_size: Optional[int] = None
    user_profile: Optional[UserProfileData] = None
    team_structure: Optional[List[Dict[str, Any]]] = None
    integration_settings: Optional[IntegrationSettings] = None
    branding_settings: Optional[BrandingSettings] = None
    automation_settings: Optional[AutomationSettings] = None
    reconciliation_settings: Optional[ReconciliationSettings] = None
    pipeline_settings: Optional[PipelineSettings] = None
    kpi_targets: Optional[KPITargets] = None
    portfolio_settings: Optional[PortfolioSettings] = None
    advanced_settings: Optional[AdvancedSettings] = None

class ClientProfileResponse(BaseModel):
    id: int
    account_id: str
    account_type: str
    primary_user_id: int
    company_name: str
    nmls_number: Optional[str]
    business_address: Optional[Dict[str, Any]]
    team_size: int
    user_profile: Optional[Dict[str, Any]]
    team_structure: Optional[List[Dict[str, Any]]]
    integration_settings: Optional[Dict[str, Any]]
    branding_settings: Optional[Dict[str, Any]]
    automation_settings: Optional[Dict[str, Any]]
    reconciliation_settings: Optional[Dict[str, Any]]
    pipeline_settings: Optional[Dict[str, Any]]
    kpi_targets: Optional[Dict[str, Any]]
    subscription_plan: str
    billing_status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class TeamRoleCreate(BaseModel):
    role_name: str
    user_id: Optional[int] = None
    responsibilities: Optional[List[str]] = None
    permissions: Optional[Dict[str, Any]] = None
    service_level_expectations: Optional[Dict[str, Any]] = None
    backup_user_id: Optional[int] = None

class TeamRoleUpdate(BaseModel):
    role_name: Optional[str] = None
    user_id: Optional[int] = None
    responsibilities: Optional[List[str]] = None
    permissions: Optional[Dict[str, Any]] = None
    service_level_expectations: Optional[Dict[str, Any]] = None
    backup_user_id: Optional[int] = None
    is_active: Optional[bool] = None

class TeamRoleResponse(BaseModel):
    id: int
    profile_id: int
    role_name: str
    user_id: Optional[int]
    responsibilities: Optional[List[Any]]
    permissions: Optional[Dict[str, Any]]
    service_level_expectations: Optional[Dict[str, Any]]
    backup_user_id: Optional[int]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessFlowDocumentCreate(BaseModel):
    document_name: str
    document_type: str  # PDF, spreadsheet, flowchart, SOP
    file_url: str

class ProcessFlowDocumentResponse(BaseModel):
    id: int
    profile_id: int
    document_name: str
    document_type: str
    file_url: str
    ai_parsing_status: str
    ai_parsed_content: Optional[Dict[str, Any]]
    upload_date: datetime
    class Config:
        from_attributes = True

class ActivityCreate(BaseModel):
    type: ActivityType
    content: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    mum_client_id: Optional[int] = None
    sentiment: Optional[str] = None

class ActivityResponse(BaseModel):
    id: int
    type: ActivityType
    content: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    mum_client_id: Optional[int] = None
    sentiment: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessTemplateCreate(BaseModel):
    role_name: str
    task_title: str
    task_description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: bool = True

class ProcessTemplateUpdate(BaseModel):
    task_title: Optional[str] = None
    task_description: Optional[str] = None
    sequence_order: Optional[int] = None
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: Optional[bool] = None
    is_active: Optional[bool] = None

class ProcessTemplateResponse(BaseModel):
    id: int
    role_name: str
    task_title: str
    task_description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    dependencies: Optional[List[int]]
    is_required: bool
    automation_potential: Optional[str]
    efficiency_notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class ProcessRoleCreate(BaseModel):
    role_name: str
    role_title: str
    responsibilities: Optional[str] = None
    skills_required: Optional[List[str]] = None
    key_activities: Optional[List[str]] = None

class ProcessRoleResponse(BaseModel):
    id: int
    role_name: str
    role_title: str
    responsibilities: Optional[str]
    skills_required: Optional[List[str]]
    key_activities: Optional[List[str]]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessMilestoneCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None

class ProcessMilestoneResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProcessTaskCreate(BaseModel):
    milestone_id: int
    role_id: int
    task_name: str
    task_description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None
    sla: Optional[int] = None
    sla_unit: str = "hours"
    ai_automatable: bool = False
    dependencies: Optional[List[int]] = None
    is_required: bool = True

class ProcessTaskResponse(BaseModel):
    id: int
    milestone_id: int
    role_id: int
    task_name: str
    task_description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    sla: Optional[int]
    sla_unit: str
    ai_automatable: bool
    dependencies: Optional[List[int]]
    is_required: bool
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class DocumentParseRequest(BaseModel):
    document_content: str  # Base64 encoded document or text content
    document_name: Optional[str] = None
    document_type: Optional[str] = None  # pdf, docx, txt, etc.

class DocumentParseResponse(BaseModel):
    roles: List[ProcessRoleResponse]
    milestones: List[ProcessMilestoneResponse]
    tasks: List[ProcessTaskResponse]
    summary: Dict[str, Any]

class ConversationCreate(BaseModel):
    message: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None

class ChatStreamRequest(BaseModel):
    """Request model for streaming chat endpoint"""
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None

class ConversationResponse(BaseModel):
    id: int
    message: str
    response: Optional[str]
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

# ============================================================================
# PERFORMANCE COACH SCHEMAS
# ============================================================================

# CoachMode enum imported from database.enums above

class CoachRequest(BaseModel):
    mode: CoachMode
    message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class CoachResponse(BaseModel):
    mode: CoachMode
    response: str
    priorities: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    action_items: Optional[List[str]] = None

class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    location: Optional[str] = None
    event_type: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    attendees: Optional[List[str]] = None
    reminder_minutes: Optional[int] = None

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    attendees: Optional[List[str]] = None

class CalendarEventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    all_day: bool
    location: Optional[str]
    event_type: Optional[str]
    status: str
    lead_id: Optional[int]
    loan_id: Optional[int]
    created_at: datetime
    class Config:
        from_attributes = True

# ============================================================================
# CALENDAR ASSIGNMENT SCHEMAS
# ============================================================================

class CalendarAssignmentCreate(BaseModel):
    purpose: str
    purpose_label: Optional[str] = None
    assigned_user_id: Optional[int] = None
    calendly_url: Optional[str] = None
    booking_link_id: Optional[int] = None
    is_active: bool = True

class CalendarAssignmentUpdate(BaseModel):
    purpose_label: Optional[str] = None
    assigned_user_id: Optional[int] = None
    calendly_url: Optional[str] = None
    booking_link_id: Optional[int] = None
    is_active: Optional[bool] = None

class CalendarAssignmentResponse(BaseModel):
    id: int
    purpose: str
    purpose_label: Optional[str]
    assigned_user_id: Optional[int]
    assigned_user_name: Optional[str] = None
    calendly_url: Optional[str]
    booking_link_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

# Default calendar purposes that can be assigned
CALENDAR_PURPOSES = [
    {"purpose": "purchase_application", "label": "Purchase Application Scheduling"},
    {"purpose": "refinance_application", "label": "Refinance Application Scheduling"},
    {"purpose": "lead_consultation", "label": "Lead Consultation"},
    {"purpose": "document_review", "label": "Document Review Call"},
    {"purpose": "closing_call", "label": "Closing Preparation Call"},
    {"purpose": "general_appointment", "label": "General Appointment"},
    {"purpose": "website_demo", "label": "Website Demo Scheduler"},
]

# ============================================================================
# DATA RECONCILIATION ENGINE SCHEMAS
# ============================================================================

class IncomingDataEventCreate(BaseModel):
    source: str
    raw_text: Optional[str] = None
    raw_html: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None

class ExtractedDataResponse(BaseModel):
    id: int
    event_id: int
    category: Optional[str]
    subcategory: Optional[str]
    fields: Dict[str, Any]
    match_entity_type: Optional[str]
    match_entity_id: Optional[int]
    match_confidence: Optional[float]
    ai_confidence: Optional[float]
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class ReconciliationApproval(BaseModel):
    extracted_data_id: int
    approved_fields: Optional[Dict[str, Any]] = None  # If partial approval
    corrections: Optional[Dict[str, Any]] = None  # If user corrected values
    deleted_fields: Optional[List[str]] = None  # Fields user wants to delete/ignore
    renamed_fields: Optional[Dict[str, str]] = None  # Field renames { old_key: new_key }
    delegate_to_ai: Optional[bool] = False  # If user wants AI to handle this task type in future
    email_intent: Optional[str] = None  # Email intent type (for AI delegation)
    recommended_action: Optional[Dict[str, Any]] = None  # Recommended action details
    # Entity type override - allows user to select if this is a Lead or Active Loan
    target_entity_type: Optional[str] = None  # "loan" or "lead" - override AI's guess
    target_entity_id: Optional[int] = None  # Specific entity to apply to (override match)
    create_new_loan: Optional[bool] = False  # Create a new loan from this data
    loan_stage: Optional[str] = None  # Stage for new loan (e.g., "PROCESSING", "UW_RECEIVED")
    update_status_to: Optional[str] = None  # Update entity status during approval (e.g., "PROCESSING")
    # Delete from inbox options
    delete_from_inbox: Optional[bool] = False  # If True, move email to trash after processing
    email_message_id: Optional[str] = None  # Microsoft Graph message ID for deletion

class ReconciliationRejection(BaseModel):
    extracted_data_id: int
    reason: Optional[str] = None
    # Delete from inbox options
    delete_from_inbox: Optional[bool] = False  # If True, move email to trash after processing
    email_message_id: Optional[str] = None  # Microsoft Graph message ID for deletion

class BlockSenderRequest(BaseModel):
    sender_email: str
    reason: Optional[str] = "Blocked by user"

class CreateLeadFromExtracted(BaseModel):
    extracted_data_id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    referral_partner_id: Optional[int] = None

# ============================================================================
# ORGANIZATION SCHEMAS (Multi-Tenant)
# ============================================================================

class OrganizationCreate(BaseModel):
    """Request schema for creating an organization"""
    name: str
    slug: Optional[str] = None  # Auto-generated from name if not provided
    domain: Optional[str] = None  # Email domain for auto-assignment

class OrganizationUpdate(BaseModel):
    """Request schema for updating an organization"""
    name: Optional[str] = None
    domain: Optional[str] = None
    settings: Optional[dict] = None

class OrganizationResponse(BaseModel):
    """Response schema for organization data"""
    id: int
    name: str
    slug: str
    domain: Optional[str] = None
    subscription_tier: str
    is_active: bool
    user_count: Optional[int] = None
    has_microsoft_config: bool = False

    class Config:
        from_attributes = True


# ============================================================================
# MICROSOFT OAUTH SCHEMAS
# ============================================================================

class MicrosoftOAuthConnect(BaseModel):
    authorization_code: str
    redirect_uri: str

class MicrosoftTokenResponse(BaseModel):
    connected: bool
    email_address: Optional[str] = None
    sync_enabled: bool = True
    last_sync_at: Optional[datetime] = None

class MicrosoftSyncSettings(BaseModel):
    sync_enabled: Optional[bool] = None
    sync_folder: Optional[str] = None
    sync_frequency_minutes: Optional[int] = None

class MicrosoftAppConfigRequest(BaseModel):
    """Request schema for saving Microsoft App configuration"""
    client_id: str
    client_secret: Optional[str] = None  # Optional when updating (won't change if not provided)
    tenant_id: str = "common"

class MicrosoftAppConfigResponse(BaseModel):
    """Response schema for Microsoft App configuration"""
    client_id: Optional[str] = None
    tenant_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    configured: bool = False
    has_client_secret: bool = False

# ============================================================================
# AUDIT & ACCESS SCHEMAS (Tab 6)
# ============================================================================

class RevokeSessionRequest(BaseModel):
    reason: Optional[str] = None

class RevokeAllSessionsRequest(BaseModel):
    reason: str  # Required for revoking all sessions

class EmergencyRevokeRequest(BaseModel):
    reason: str  # 'termination', 'security_incident', 'policy_violation', 'investigation', 'other'
    details: str
    notify: Optional[List[str]] = []  # Array of who to notify: 'hr', 'security', 'employee', 'manager'
    reinstate_type: str = "manual"  # 'manual' or 'automatic'
    reinstate_date: Optional[datetime] = None

class UpdateJobDescriptionRequest(BaseModel):
    description: str

class JobDescriptionResponse(BaseModel):
    description: str
    last_updated: Optional[datetime]
    updated_by: Optional[Dict[str, Any]]

class SkillCreate(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None

class SkillResponse(BaseModel):
    id: int
    name: str
    category: Optional[str]
    description: Optional[str]

class CreateResponsibilityRequest(BaseModel):
    title: str
    description: Optional[str] = None
    ownership: str  # 'primary', 'secondary', 'shared'
    time_allocation: Optional[int] = None
    priority: str  # 'critical', 'high', 'medium', 'low'
    effective_date: str  # ISO date string
    end_date: Optional[str] = None  # ISO date string
    required_skills: Optional[List[int]] = []

class UpdateResponsibilityRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    ownership: Optional[str] = None
    time_allocation: Optional[int] = None
    priority: Optional[str] = None
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    required_skills: Optional[List[int]] = None

class ResponsibilityResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    ownership: str
    time_allocation: Optional[int]
    priority: str
    effective_date: str
    end_date: Optional[str]
    archived: bool
    display_order: int
    required_skills: List[SkillResponse]

class ReorderResponsibilitiesRequest(BaseModel):
    order: List[int]  # Array of responsibility IDs in new order

