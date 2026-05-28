"""
Lead and Loan Models

Core CRM pipeline models for tracking leads and loans.
Extracted from main.py as part of the architecture decomposition.

NOTE: During migration, these models are duplicated in main.py.
Once main.py is updated to import from here, remove duplicates.

Usage:
    from database.models.lead_loan import Lead, Loan

    # Query leads
    leads = db.query(Lead).filter(Lead.stage == LeadStage.NEW).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, Numeric, text,
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates

# Import Base from the db module
from db import Base
from encryption_utils import EncryptedString

# Import enums from the database package
from database.enums import (
    LeadStage,
    LoanStage,
    RateLockStatus,
    RateLockRecommendation,
    BuyingTimelineCategory,
    BorrowerRiskProfile,
)


# ============================================================================
# LEAD MODEL
# ============================================================================

class Lead(Base):
    """Lead/prospect in the CRM pipeline"""
    __tablename__ = "leads"
    __table_args__ = (
        Index('ix_leads_owner_id', 'owner_id'),
        Index('ix_leads_stage', 'stage'),
        Index('ix_leads_created_at', 'created_at'),
        Index('ix_leads_referral_partner_id', 'referral_partner_id'),
        Index('ix_leads_owner_stage', 'owner_id', 'stage'),
        Index('ix_leads_organization_id', 'organization_id'),
        Index('ix_leads_org_stage', 'organization_id', 'stage'),
        Index('ix_leads_org_created', 'organization_id', 'created_at'),
        # Performance indexes (added via add_performance_indexes migration)
        Index('ix_leads_last_contact', 'last_contact'),
        Index('ix_leads_ai_score', 'ai_score'),
        Index('ix_leads_source', 'source'),
        Index('ix_leads_loan_number', 'loan_number'),
        Index('ix_leads_salesforce_id', 'salesforce_id'),
        Index('ix_leads_owner_last_contact', 'owner_id', 'last_contact'),
        Index('ix_leads_org_source', 'organization_id', 'source'),
        Index('ix_leads_org_ai_score', 'organization_id', 'ai_score'),
        # DATA-006: Unique email per organization (partial index needed for NULL emails;
        # deploy migration: CREATE UNIQUE INDEX uix_lead_email_org ON leads (email, organization_id) WHERE email IS NOT NULL)
        UniqueConstraint('email', 'organization_id', name='uix_lead_email_org'),
        # DATA-009: Every lead must have at least one contact method
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name='ck_lead_has_contact'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)  # Multi-tenant isolation
    name = Column(String(255), nullable=False, index=True)  # NOTE: Not encrypted — indexed for lookups.
    first_name = Column(String(255))  # NOTE: Not encrypted — used with name index for search.
    last_name = Column(String(255))  # NOTE: Not encrypted — used with name index for search.
    email = Column(String(255), index=True)  # NOTE: Not encrypted — indexed for lookups. Consider adding email_hash column.
    phone = Column(String(50), index=True)  # NOTE: Not encrypted — indexed for lookups.

    # Co-applicant
    co_applicant_name = Column(EncryptedString)  # PII: name
    co_applicant_email = Column(EncryptedString)  # PII: email address
    co_applicant_phone = Column(EncryptedString)  # PII: phone number

    # Communication
    preferred_communication = Column(String(50))  # email, phone, text, voicemail

    # Pipeline status
    stage = Column(String(50), default="New")
    workflow_definition_id = Column(String(36), ForeignKey("workflow_definitions.id", ondelete="SET NULL"), nullable=True, index=True)
    workflow_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(String(255))
    organization_code = Column(String(100))  # Branch/organization identifier
    referral_partner_id = Column(Integer, ForeignKey("referral_partners.id", ondelete="SET NULL"))

    # AI scoring
    ai_score = Column(Integer, default=50)
    sentiment = Column(String(50), default="neutral")
    next_action = Column(Text)

    # Loan qualification
    loan_type = Column(String(100))
    preapproval_amount = Column(Numeric(18, 2))
    credit_score = Column(Integer)
    debt_to_income = Column(Numeric(8, 4))

    # Assignment
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    last_contact = Column(DateTime)
    loan_number = Column(String(255))
    notes = Column(Text)

    # Property Information
    address = Column(EncryptedString)  # PII: physical address
    city = Column(EncryptedString)  # PII: physical address
    state = Column(EncryptedString)  # PII: physical address
    zip_code = Column(EncryptedString)  # PII: physical address
    property_type = Column(String(100))
    property_value = Column(Numeric(18, 2))
    down_payment = Column(Numeric(18, 2))

    # Financial Information
    employment_status = Column(String(100))
    annual_income = Column(Numeric(18, 2))
    monthly_debts = Column(Numeric(18, 2))
    first_time_buyer = Column(Boolean, default=False)

    # Loan Details
    loan_amount = Column(Numeric(18, 2))
    interest_rate = Column(Numeric(8, 4))
    loan_term = Column(Integer)
    apr = Column(Numeric(8, 4))
    points = Column(Numeric(8, 4))
    lock_date = Column(DateTime)
    lock_expiration = Column(DateTime)
    closing_date = Column(DateTime)
    lender = Column(String(255))
    loan_officer = Column(String(255))
    processor = Column(String(255))
    underwriter = Column(String(255))
    production_assistant = Column(String(255))
    appraisal_value = Column(Numeric(18, 2))
    ltv = Column(Numeric(8, 4))
    cltv = Column(Numeric(8, 4))
    dti = Column(Numeric(8, 4))
    dti_front = Column(Numeric(8, 4))
    dti_back = Column(Numeric(8, 4))
    program = Column(String(255))
    status_date = Column(DateTime)

    # SLA Milestone Dates
    lead_received_date = Column(DateTime)                # New Lead
    first_contact_attempt_date = Column(DateTime)        # Attempted Contact
    first_contact_successful_date = Column(DateTime)
    lead_qualification_date = Column(DateTime)           # Pre-Qualified
    application_link_sent_date = Column(DateTime)
    application_started_date = Column(DateTime)
    application_completed_date = Column(DateTime)        # Application Complete
    credit_pulled_date = Column(DateTime)
    preapproval_submission_date = Column(DateTime)
    preapproval_issued_date = Column(DateTime)           # Pre-Approved
    preapproval_expiration_date = Column(DateTime)
    realtor_referral_date = Column(DateTime)
    rate_watch_enrollment_date = Column(DateTime)
    initial_consultation_date = Column(DateTime)         # Initial Consultation
    property_address = Column(EncryptedString)  # PII: physical address

    # PRD Section 4.1 - Rate Lock Intelligence
    buying_timeline_category = Column(SQLEnum(BuyingTimelineCategory))
    borrower_risk_profile = Column(SQLEnum(BorrowerRiskProfile))
    target_payment = Column(Numeric(18, 2))
    expected_purchase_date = Column(DateTime)

    # PRD Section 4.3 - Referral Fields
    referral_score = Column(Integer, default=0)
    referral_source_score = Column(Integer, default=0)
    employment_referral_flag = Column(Boolean, default=False)
    manager_flag = Column(Boolean, default=False)
    employees_managed = Column(Integer, default=0)
    leadership_level = Column(String(100))
    company_size = Column(Integer)
    employer_name = Column(String(255))
    industry = Column(String(255))
    circle_of_cash_flow_map = Column(JSON)

    # Workflow tracking
    current_workflow_id = Column(String(36))
    workflow_day = Column(Integer, default=0)
    last_workflow_action = Column(DateTime)
    nurture_month = Column(Integer, default=0)
    stage_changed_at = Column(DateTime)

    # Current milestone state (fast reads for workflow engine)
    current_milestone_status = Column(String(50))
    current_milestone_entered_at = Column(DateTime)

    # Salesforce Sync - Property Details
    occupancy_type = Column(String(100))
    property_county = Column(String(255))
    property_ownership_type = Column(String(100))
    property_units = Column(Integer)

    # Salesforce Sync - Financial Details
    rate_type = Column(String(50))
    monthly_payment = Column(Numeric(18, 2))
    property_tax = Column(Numeric(18, 2))
    hazard_insurance = Column(Numeric(18, 2))
    mortgage_insurance = Column(Numeric(18, 2))
    hoa_amount = Column(Numeric(18, 2))
    origination_fee = Column(Numeric(18, 2))
    estimated_prepaid_interest = Column(Numeric(18, 2))
    index_rate = Column(Numeric(8, 4))
    margin = Column(Numeric(8, 4))

    # Salesforce Sync - LTV/Purpose
    loan_purpose = Column(String(100))
    file_state = Column(String(50))

    # Salesforce Sync - 2nd Loan
    second_loan_amount = Column(Numeric(18, 2))
    second_loan_rate = Column(Numeric(8, 4))
    second_loan_payment = Column(Numeric(18, 2))

    # Salesforce Sync - Housing Expenses
    present_housing_expense = Column(Numeric(18, 2))
    proposed_housing_expense = Column(Numeric(18, 2))
    present_monthly_payment = Column(Numeric(18, 2))
    proposed_monthly_payment = Column(Numeric(18, 2))

    # Marketing
    receive_marketing = Column(Boolean, default=False)

    # Salesforce Integration
    salesforce_id = Column(String(255))
    meta_data = Column(JSON)

    # Follow Up Boss Integration
    fub_person_id = Column(Integer)
    fub_last_synced_at = Column(DateTime)

    # AI tracking (COMP-001: mark AI-generated modifications)
    last_modified_by_ai = Column(Boolean, default=False, server_default="false")

    # GDPR retention (COMP-004: PII retention with automated expiry)
    data_retention_expires_at = Column(DateTime, nullable=True)

    # Metadata
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Valid lead stages (from LeadStage enum values)
    _VALID_LEAD_STAGES = frozenset(s.value for s in LeadStage)

    @validates('stage')
    def validate_stage(self, key, value):
        """Validate lead stage against LeadStage enum values."""
        if value is None:
            return value
        if hasattr(value, 'value'):
            value = value.value
        value = str(value)
        if value not in self._VALID_LEAD_STAGES:
            import logging
            logging.getLogger(__name__).warning(
                f"Lead stage '{value}' not in LeadStage enum — allowing for backward compat"
            )
        return value

    @validates('first_name', 'last_name')
    def validate_required_fields(self, key, value):
        """Warn on empty required fields (not enforced as NOT NULL to avoid migration breakage)."""
        if not value or not str(value).strip():
            import logging
            logging.getLogger(__name__).warning(f"Lead.{key} should not be empty")
        return value

    # Relationships
    organization = relationship("Organization", backref="leads")
    owner = relationship("User", back_populates="leads")
    referral_partner = relationship("ReferralPartner", back_populates="leads")
    activities = relationship("Activity", back_populates="lead")
    stage_history = relationship("StageHistory", back_populates="lead", foreign_keys="StageHistory.lead_id")


# ============================================================================
# LOAN MODEL
# ============================================================================

class Loan(Base):
    """Loan/application in the processing pipeline"""
    __tablename__ = "loans"
    __table_args__ = (
        Index('ix_loans_loan_officer_id', 'loan_officer_id'),
        Index('ix_loans_stage', 'stage'),
        Index('ix_loans_funded_date', 'funded_date'),
        Index('ix_loans_created_at', 'created_at'),
        Index('ix_loans_officer_stage', 'loan_officer_id', 'stage'),
        Index('ix_loans_organization_id', 'organization_id'),
        Index('ix_loans_org_stage', 'organization_id', 'stage'),
        Index('ix_loans_org_created', 'organization_id', 'created_at'),
        # Performance indexes (added via add_performance_indexes migration)
        Index('ix_loans_borrower_name', 'borrower_name'),
        Index('ix_loans_closing_date', 'closing_date'),
        Index('ix_loans_stage_changed_at', 'stage_changed_at'),
        Index('ix_loans_lock_expiration_date', 'lock_expiration_date'),
        Index('ix_loans_loan_type', 'loan_type'),
        Index('ix_loans_application_date', 'application_date'),
        Index('ix_loans_org_closing_date', 'organization_id', 'closing_date'),
        Index('ix_loans_org_funded_date', 'organization_id', 'funded_date'),
        Index('ix_loans_lo_funded_date', 'loan_officer_id', 'funded_date'),
        Index('ix_loans_org_lock_exp', 'organization_id', 'lock_expiration_date'),
        Index(
            'ix_loans_active_pipeline',
            'organization_id', 'stage', 'loan_officer_id',
            postgresql_where=text(
                "stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"
            ),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    loan_number = Column(String(255), unique=True, index=True, nullable=False)

    # Borrower info
    borrower_name = Column(String(255), nullable=False)  # NOTE: Not encrypted — indexed for lookups (ix_loans_borrower_name).
    borrower_email = Column(EncryptedString)  # PII: email address
    borrower_phone = Column(EncryptedString)  # PII: phone number
    preferred_communication = Column(String(50))
    coborrower_name = Column(EncryptedString)  # PII: name
    co_borrower_email = Column(EncryptedString)  # PII: email address
    co_borrower_phone = Column(EncryptedString)  # PII: phone number

    # Pipeline status
    stage = Column(String(50), default="DISCLOSED")
    program = Column(String(255))
    loan_type = Column(String(100))

    # Financials
    amount = Column(Numeric(18, 2), nullable=False)
    purchase_price = Column(Numeric(18, 2))
    down_payment = Column(Numeric(18, 2))
    rate = Column(Numeric(8, 4))
    term = Column(Integer, default=360)

    # Property
    property_address = Column(EncryptedString)  # PII: physical address
    property_city = Column(EncryptedString)  # PII: physical address
    property_state = Column(EncryptedString)  # PII: physical address
    property_zip = Column(EncryptedString)  # PII: physical address

    # Key dates
    lock_date = Column(DateTime)
    closing_date = Column(DateTime)
    funded_date = Column(DateTime)

    # Team
    loan_officer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    processor = Column(String(255))
    underwriter = Column(String(255))
    realtor_agent = Column(String(255))
    title_company = Column(String(255))
    lender = Column(String(255))
    loan_officer_name = Column(String(255))
    loan_officer_email = Column(String(255))
    processor_email = Column(String(255))
    underwriter_email = Column(String(255))
    closer = Column(String(255))
    closer_email = Column(String(255))
    production_assistant = Column(String(255))

    # SLA tracking
    days_in_stage = Column(Integer, default=0)
    sla_status = Column(String(50), default="on-track")
    milestones = Column(JSON)
    ai_insights = Column(Text)
    predicted_close_date = Column(DateTime)
    risk_score = Column(Integer, default=0)
    user_metadata = Column(JSON)

    # Appraisal tracking
    appraisal_ordered_date = Column(DateTime)
    appraisal_scheduled_date = Column(DateTime)
    appraisal_completed_date = Column(DateTime)
    appraisal_value = Column(Numeric(18, 2))
    appraisal_received_date = Column(DateTime)
    appraisal_docs_expire_date = Column(DateTime)

    # Title & Insurance tracking
    title_ordered_date = Column(DateTime)
    title_received_date = Column(DateTime)
    insurance_ordered_date = Column(DateTime)
    insurance_received_date = Column(DateTime)

    # Rate lock fields
    lock_expiration_date = Column(DateTime)
    rate_lock_status = Column(SQLEnum(RateLockStatus), default=RateLockStatus.NOT_ELIGIBLE)
    rate_lock_recommendation = Column(SQLEnum(RateLockRecommendation))
    lock_term_days = Column(Integer)
    float_down_available = Column(Boolean, default=False)
    float_down_terms = Column(String(500))
    extension_cost_estimate = Column(Numeric(18, 2))
    volatility_score = Column(Integer, default=50)
    borrower_risk_profile = Column(SQLEnum(BorrowerRiskProfile))
    lock_score = Column(Integer)
    lock_decision_date = Column(DateTime)
    lock_decision_notes = Column(Text)
    last_rate_check = Column(DateTime)
    rate_lock_history = Column(JSON)

    # Disclosure milestone dates
    initial_disclosures_sent_date = Column(DateTime)
    initial_disclosures_signed_date = Column(DateTime)
    cd_received_signed_date = Column(DateTime)
    final_closing_package_sent_date = Column(DateTime)

    # Under Contract Workflow Fields
    contract_received_date = Column(DateTime)
    loan_estimate_sent_date = Column(DateTime)
    conditional_approval_date = Column(DateTime)

    # AMR tracking
    last_amr_date = Column(DateTime)
    next_amr_date = Column(DateTime)
    refi_opportunity_score = Column(Integer, default=0)

    # Workflow tracking
    current_workflow_id = Column(String(36))
    last_workflow_action = Column(DateTime)
    stage_changed_at = Column(DateTime)

    # Current milestone state (fast reads for workflow engine)
    current_milestone_status = Column(String(50))
    current_milestone_entered_at = Column(DateTime)

    # MUM (Mortgage Update Monitoring) date
    mum_date = Column(DateTime)

    # SLA Date Fields - Jungo Custom Byte Mappings
    prospect_date = Column(DateTime)
    application_date = Column(DateTime)
    le_pending_date = Column(DateTime)
    credit_only_date = Column(DateTime)
    file_received_date = Column(DateTime)
    preapproval_date = Column(DateTime)
    uw_received_date = Column(DateTime)
    conditions_for_review_date = Column(DateTime)
    suspended_date = Column(DateTime)
    loan_approved_date = Column(DateTime)
    approved_not_accepted_date = Column(DateTime)
    approval_expires_date = Column(DateTime)
    cd_requested_date = Column(DateTime)
    cd_sent_to_borrower_date = Column(DateTime)
    cd_acknowledged_date = Column(DateTime)
    clear_to_close_date = Column(DateTime)
    docs_ordered_date = Column(DateTime)
    docs_out_date = Column(DateTime)
    credit_docs_expire_date = Column(DateTime)
    scheduled_closing_date = Column(DateTime)
    scheduled_funding_date = Column(DateTime)
    funds_ordered_date = Column(DateTime)
    funds_sent_date = Column(DateTime)
    first_payment_date = Column(DateTime)
    investor_purchased_date = Column(DateTime)
    withdrawn_date = Column(DateTime)

    # Salesforce Sync - Property
    property_type = Column(String(100))
    occupancy_type = Column(String(100))
    property_county = Column(String(255))
    property_ownership_type = Column(String(100))
    property_units = Column(Integer)

    # Salesforce Sync - Financials
    rate_type = Column(String(50))
    monthly_payment = Column(Numeric(18, 2))
    property_tax = Column(Numeric(18, 2))
    hazard_insurance = Column(Numeric(18, 2))
    mortgage_insurance = Column(Numeric(18, 2))
    hoa_amount = Column(Numeric(18, 2))
    origination_fee = Column(Numeric(18, 2))
    estimated_prepaid_interest = Column(Numeric(18, 2))
    points = Column(Numeric(8, 4))
    index_rate = Column(Numeric(8, 4))
    margin = Column(Numeric(8, 4))
    ltv = Column(Numeric(8, 4))
    cltv = Column(Numeric(8, 4))
    loan_purpose = Column(String(100))
    file_state = Column(String(50))

    # Salesforce Sync - 2nd Loan
    second_loan_amount = Column(Numeric(18, 2))
    second_loan_rate = Column(Numeric(8, 4))
    second_loan_payment = Column(Numeric(18, 2))

    # Salesforce Sync - Housing Expenses
    present_housing_expense = Column(Numeric(18, 2))
    proposed_housing_expense = Column(Numeric(18, 2))
    present_monthly_payment = Column(Numeric(18, 2))
    proposed_monthly_payment = Column(Numeric(18, 2))

    # Salesforce Integration
    salesforce_id = Column(String(255), index=True)

    # Encompass LOS Integration
    encompass_loan_id = Column(String(255), index=True, nullable=True)
    encompass_last_synced_at = Column(DateTime, nullable=True)
    encompass_sync_status = Column(String(50), nullable=True)  # "synced", "pending", "error"

    # AI tracking (COMP-001: mark AI-generated modifications)
    last_modified_by_ai = Column(Boolean, default=False, server_default="false")

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Valid loan stages (from LoanStage enum values)
    _VALID_LOAN_STAGES = frozenset(s.value for s in LoanStage)

    @validates('stage')
    def validate_stage(self, key, value):
        """Convert enum values to plain strings and validate against LoanStage."""
        if value is None:
            return value
        if hasattr(value, 'value'):
            value = value.value
        value = str(value).upper()
        if value not in self._VALID_LOAN_STAGES:
            import logging
            logging.getLogger(__name__).warning(
                f"Loan stage '{value}' not in LoanStage enum — allowing for backward compat"
            )
        return value

    # Relationships
    organization = relationship("Organization", backref="loans")
    loan_officer = relationship("User", back_populates="loans")
    tasks = relationship("AITask", back_populates="loan")
    activities = relationship("Activity", back_populates="loan")
    stage_history = relationship("StageHistory", back_populates="loan", foreign_keys="StageHistory.loan_id")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "Lead",
    "Loan",
]
