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
    Total fields: 150+ (expanded with processing log and milestone fields to match ActiveLoanProfile)
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

    # ==================== IMPORTANT DATES (Original Lead Dates) ====================
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

    # ==================== PROCESSING LOG ITEMS ====================
    # Appraisal Processing
    appraisal_ordered_date = Column(Date)
    appraisal_due_date = Column(Date)
    appraisal_received_date = Column(Date)
    appraisal_submitted_date = Column(Date)
    appraisal_cleared_date = Column(Date)
    appraisal_days = Column(Integer)
    appraisal_expiration_date = Column(Date)
    appraisal_scheduled_date = Column(Date)
    appraisal_completed_date = Column(Date)

    # Title Processing
    title_ordered_date = Column(Date)
    title_due_date = Column(Date)
    title_received_date = Column(Date)
    title_submitted_date = Column(Date)
    title_cleared_date = Column(Date)
    title_days = Column(Integer)
    title_expiration_date = Column(Date)

    # Hazard Insurance Processing
    hazard_insurance_ordered_date = Column(Date)
    hazard_insurance_due_date = Column(Date)
    hazard_insurance_received_date = Column(Date)
    hazard_insurance_submitted_date = Column(Date)
    hazard_insurance_cleared_date = Column(Date)
    hazard_insurance_days = Column(Integer)
    hazard_insurance_expiration_date = Column(Date)

    # Flood Insurance Processing (NEW)
    flood_insurance_ordered_date = Column(Date)
    flood_insurance_due_date = Column(Date)
    flood_insurance_received_date = Column(Date)
    flood_insurance_submitted_date = Column(Date)
    flood_insurance_cleared_date = Column(Date)
    flood_insurance_days = Column(Integer)
    flood_insurance_expiration_date = Column(Date)

    # Credit Processing
    credit_ordered_date = Column(Date)
    credit_due_date = Column(Date)
    credit_received_date = Column(Date)
    credit_submitted_date = Column(Date)
    credit_cleared_date = Column(Date)
    credit_days = Column(Integer)
    credit_expiration_date = Column(Date)

    # ==================== IMPORTANT DATES (Matching Active Loan Dates) ====================
    date_file_created = Column(DateTime)
    preapproval_application_date = Column(Date)
    application_date = Column(Date)
    scheduled_approval_date = Column(Date)
    signing_appt_confirmed = Column(Boolean, default=False)
    signing_location = Column(String(255))
    signing_date = Column(Date)
    signing_time = Column(String(20))
    scheduled_closing_date = Column(Date)
    scheduled_funding_date = Column(Date)
    approval_expires_date = Column(Date)
    credit_docs_expire_date = Column(Date)
    appraisal_docs_expire_date = Column(Date)

    # ==================== MILESTONE STATUS DATES ====================
    registered_date = Column(Date)
    advance_lock_date = Column(Date)
    prospect_date = Column(Date)
    le_pending_date = Column(Date)
    credit_only_date = Column(Date)
    disclosed_date = Column(Date)
    file_received_date = Column(Date)
    canceled_for_incompleteness_date = Column(Date)
    corr_incomplete_submission_date = Column(Date)
    uw_received_date = Column(Date)
    pre_approved_date = Column(Date)
    withdrawn_date = Column(Date)
    approved_date = Column(Date)
    approved_not_accepted_date = Column(Date)
    corr_credit_audit_in_process_date = Column(Date)
    corr_credit_only_completed_date = Column(Date)
    corr_legal_audit_in_process_date = Column(Date)
    suspended_date = Column(Date)
    corr_audit_complete_conditions_date = Column(Date)
    conditions_for_review_date = Column(Date)
    clear_to_close_date = Column(Date)
    docs_ordered_date = Column(Date)
    docs_out_date = Column(Date)
    docs_back_date = Column(Date)
    corr_ready_for_purchase_date = Column(Date)
    funds_ordered_date = Column(Date)
    funds_sent_date = Column(Date)
    funded_date = Column(Date)
    purchased_date = Column(Date)
    investor_purchased_date = Column(Date)
    shipped_date = Column(Date)
    post_closing_completed_date = Column(Date)
    changes_to_uw_date = Column(Date)
    loan_restructure_date = Column(Date)
    msr_date = Column(Date)
    private_loan_funded_date = Column(Date)
    asset_loan_date = Column(Date)
    lock_and_list_date = Column(Date)
    sandbox_date = Column(Date)
    declined_date = Column(Date)

    # ==================== FOLLOW UP ====================
    follow_up_date = Column(Date)
    follow_up_flag = Column(String(100))
    exclude_from_custom_reports = Column(Boolean, default=False)

    # ==================== LOCK INFORMATION ====================
    lock_days = Column(Integer)
    lock_ext_1_date = Column(Date)
    lock_ext_2_date = Column(Date)
    lock_ext_3_date = Column(Date)
    date_locked = Column(DateTime)
    lock_exp_date = Column(Date)
    floating = Column(Boolean, default=False)
    date_canceled = Column(Date)

    # ==================== ADDITIONAL DATES ====================
    cd_requested_date = Column(Date)
    original_approved_date = Column(Date)
    le_pending_details = Column(String(255))
    disbursement_date = Column(Date)
    commitment_date = Column(Date)
    commitment_date_met = Column(Date)
    original_disclosed_date = Column(Date)
    has_six_app_data_points = Column(Boolean, default=False)
    cancelled_denied_coronavirus = Column(Boolean, default=False)

    # ==================== LEGACY MILESTONE DATES (for compatibility) ====================
    contract_received_date = Column(Date)
    insurance_ordered_date = Column(Date)
    insurance_received_date = Column(Date)
    initial_disclosures_sent_date = Column(Date)
    initial_disclosures_signed_date = Column(Date)
    processor_submission_date = Column(Date)
    underwriting_submission_date = Column(Date)
    conditional_approval_date = Column(Date)
    conditions_sent_date = Column(Date)
    conditions_received_date = Column(Date)
    resubmission_date = Column(Date)
    rate_lock_date = Column(Date)
    rate_lock_expiration_date = Column(Date)
    rate_lock_extension_date = Column(Date)
    float_down_trigger_date = Column(Date)
    closing_disclosure_sent_date = Column(Date)
    cd_received_signed_date = Column(Date)
    cd_delivered_date = Column(Date)
    final_cd_issue_date = Column(Date)
    final_closing_package_sent_date = Column(Date)
    closing_scheduled_date = Column(Date)
    funding_date = Column(Date)

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
        def date_to_iso(d):
            return d.isoformat() if d else None

        def datetime_to_iso(dt):
            return dt.isoformat() if dt else None

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
            'lock_date': date_to_iso(self.lock_date),
            'lock_expiration': date_to_iso(self.lock_expiration),
            'apr': float(self.apr) if self.apr else None,
            'points': float(self.points) if self.points else None,
            'lender': self.lender,
            'loan_officer': self.loan_officer,
            'processor': self.processor,
            'underwriter': self.underwriter,
            'closing_date': date_to_iso(self.closing_date),
            'appraisal_value': float(self.appraisal_value) if self.appraisal_value else None,
            'ltv': float(self.ltv) if self.ltv else None,
            'dti': float(self.dti) if self.dti else None,
            'stage': self.stage,
            'status': self.status,
            'notes': self.notes,
            'tags': self.tags,
            'source': self.source,
            'referral_source': self.referral_source,
            'created_at': datetime_to_iso(self.created_at),
            'updated_at': datetime_to_iso(self.updated_at),

            # Original Lead Dates
            'lead_created_date': datetime_to_iso(self.lead_created_date),
            'first_contact_attempt_date': datetime_to_iso(self.first_contact_attempt_date),
            'first_contact_successful_date': datetime_to_iso(self.first_contact_successful_date),
            'lead_qualification_date': datetime_to_iso(self.lead_qualification_date),
            'application_link_sent_date': datetime_to_iso(self.application_link_sent_date),
            'application_started_date': datetime_to_iso(self.application_started_date),
            'application_completed_date': datetime_to_iso(self.application_completed_date),
            'credit_pulled_date': datetime_to_iso(self.credit_pulled_date),
            'preapproval_submission_date': datetime_to_iso(self.preapproval_submission_date),
            'preapproval_issued_date': datetime_to_iso(self.preapproval_issued_date),
            'realtor_referral_date': datetime_to_iso(self.realtor_referral_date),
            'preapproval_expiration_date': date_to_iso(self.preapproval_expiration_date),
            'rate_watch_enrollment_date': datetime_to_iso(self.rate_watch_enrollment_date),

            # Processing Log Items - Appraisal
            'appraisal_ordered_date': date_to_iso(self.appraisal_ordered_date),
            'appraisal_due_date': date_to_iso(self.appraisal_due_date),
            'appraisal_received_date': date_to_iso(self.appraisal_received_date),
            'appraisal_submitted_date': date_to_iso(self.appraisal_submitted_date),
            'appraisal_cleared_date': date_to_iso(self.appraisal_cleared_date),
            'appraisal_days': self.appraisal_days,
            'appraisal_expiration_date': date_to_iso(self.appraisal_expiration_date),
            'appraisal_scheduled_date': date_to_iso(self.appraisal_scheduled_date),
            'appraisal_completed_date': date_to_iso(self.appraisal_completed_date),

            # Processing Log Items - Title
            'title_ordered_date': date_to_iso(self.title_ordered_date),
            'title_due_date': date_to_iso(self.title_due_date),
            'title_received_date': date_to_iso(self.title_received_date),
            'title_submitted_date': date_to_iso(self.title_submitted_date),
            'title_cleared_date': date_to_iso(self.title_cleared_date),
            'title_days': self.title_days,
            'title_expiration_date': date_to_iso(self.title_expiration_date),

            # Processing Log Items - Hazard Insurance
            'hazard_insurance_ordered_date': date_to_iso(self.hazard_insurance_ordered_date),
            'hazard_insurance_due_date': date_to_iso(self.hazard_insurance_due_date),
            'hazard_insurance_received_date': date_to_iso(self.hazard_insurance_received_date),
            'hazard_insurance_submitted_date': date_to_iso(self.hazard_insurance_submitted_date),
            'hazard_insurance_cleared_date': date_to_iso(self.hazard_insurance_cleared_date),
            'hazard_insurance_days': self.hazard_insurance_days,
            'hazard_insurance_expiration_date': date_to_iso(self.hazard_insurance_expiration_date),

            # Processing Log Items - Flood Insurance (NEW)
            'flood_insurance_ordered_date': date_to_iso(self.flood_insurance_ordered_date),
            'flood_insurance_due_date': date_to_iso(self.flood_insurance_due_date),
            'flood_insurance_received_date': date_to_iso(self.flood_insurance_received_date),
            'flood_insurance_submitted_date': date_to_iso(self.flood_insurance_submitted_date),
            'flood_insurance_cleared_date': date_to_iso(self.flood_insurance_cleared_date),
            'flood_insurance_days': self.flood_insurance_days,
            'flood_insurance_expiration_date': date_to_iso(self.flood_insurance_expiration_date),

            # Processing Log Items - Credit
            'credit_ordered_date': date_to_iso(self.credit_ordered_date),
            'credit_due_date': date_to_iso(self.credit_due_date),
            'credit_received_date': date_to_iso(self.credit_received_date),
            'credit_submitted_date': date_to_iso(self.credit_submitted_date),
            'credit_cleared_date': date_to_iso(self.credit_cleared_date),
            'credit_days': self.credit_days,
            'credit_expiration_date': date_to_iso(self.credit_expiration_date),

            # Important Dates
            'date_file_created': datetime_to_iso(self.date_file_created),
            'preapproval_application_date': date_to_iso(self.preapproval_application_date),
            'application_date': date_to_iso(self.application_date),
            'scheduled_approval_date': date_to_iso(self.scheduled_approval_date),
            'signing_appt_confirmed': self.signing_appt_confirmed,
            'signing_location': self.signing_location,
            'signing_date': date_to_iso(self.signing_date),
            'signing_time': self.signing_time,
            'scheduled_closing_date': date_to_iso(self.scheduled_closing_date),
            'scheduled_funding_date': date_to_iso(self.scheduled_funding_date),
            'approval_expires_date': date_to_iso(self.approval_expires_date),
            'credit_docs_expire_date': date_to_iso(self.credit_docs_expire_date),
            'appraisal_docs_expire_date': date_to_iso(self.appraisal_docs_expire_date),

            # Milestone Status Dates
            'registered_date': date_to_iso(self.registered_date),
            'advance_lock_date': date_to_iso(self.advance_lock_date),
            'prospect_date': date_to_iso(self.prospect_date),
            'le_pending_date': date_to_iso(self.le_pending_date),
            'credit_only_date': date_to_iso(self.credit_only_date),
            'disclosed_date': date_to_iso(self.disclosed_date),
            'file_received_date': date_to_iso(self.file_received_date),
            'canceled_for_incompleteness_date': date_to_iso(self.canceled_for_incompleteness_date),
            'corr_incomplete_submission_date': date_to_iso(self.corr_incomplete_submission_date),
            'uw_received_date': date_to_iso(self.uw_received_date),
            'pre_approved_date': date_to_iso(self.pre_approved_date),
            'withdrawn_date': date_to_iso(self.withdrawn_date),
            'approved_date': date_to_iso(self.approved_date),
            'approved_not_accepted_date': date_to_iso(self.approved_not_accepted_date),
            'corr_credit_audit_in_process_date': date_to_iso(self.corr_credit_audit_in_process_date),
            'corr_credit_only_completed_date': date_to_iso(self.corr_credit_only_completed_date),
            'corr_legal_audit_in_process_date': date_to_iso(self.corr_legal_audit_in_process_date),
            'suspended_date': date_to_iso(self.suspended_date),
            'corr_audit_complete_conditions_date': date_to_iso(self.corr_audit_complete_conditions_date),
            'conditions_for_review_date': date_to_iso(self.conditions_for_review_date),
            'clear_to_close_date': date_to_iso(self.clear_to_close_date),
            'docs_ordered_date': date_to_iso(self.docs_ordered_date),
            'docs_out_date': date_to_iso(self.docs_out_date),
            'docs_back_date': date_to_iso(self.docs_back_date),
            'corr_ready_for_purchase_date': date_to_iso(self.corr_ready_for_purchase_date),
            'funds_ordered_date': date_to_iso(self.funds_ordered_date),
            'funds_sent_date': date_to_iso(self.funds_sent_date),
            'funded_date': date_to_iso(self.funded_date),
            'purchased_date': date_to_iso(self.purchased_date),
            'investor_purchased_date': date_to_iso(self.investor_purchased_date),
            'shipped_date': date_to_iso(self.shipped_date),
            'post_closing_completed_date': date_to_iso(self.post_closing_completed_date),
            'changes_to_uw_date': date_to_iso(self.changes_to_uw_date),
            'loan_restructure_date': date_to_iso(self.loan_restructure_date),
            'msr_date': date_to_iso(self.msr_date),
            'private_loan_funded_date': date_to_iso(self.private_loan_funded_date),
            'asset_loan_date': date_to_iso(self.asset_loan_date),
            'lock_and_list_date': date_to_iso(self.lock_and_list_date),
            'sandbox_date': date_to_iso(self.sandbox_date),
            'declined_date': date_to_iso(self.declined_date),

            # Follow Up
            'follow_up_date': date_to_iso(self.follow_up_date),
            'follow_up_flag': self.follow_up_flag,
            'exclude_from_custom_reports': self.exclude_from_custom_reports,

            # Lock Information
            'lock_days': self.lock_days,
            'lock_ext_1_date': date_to_iso(self.lock_ext_1_date),
            'lock_ext_2_date': date_to_iso(self.lock_ext_2_date),
            'lock_ext_3_date': date_to_iso(self.lock_ext_3_date),
            'date_locked': datetime_to_iso(self.date_locked),
            'lock_exp_date': date_to_iso(self.lock_exp_date),
            'floating': self.floating,
            'date_canceled': date_to_iso(self.date_canceled),

            # Additional Dates
            'cd_requested_date': date_to_iso(self.cd_requested_date),
            'original_approved_date': date_to_iso(self.original_approved_date),
            'le_pending_details': self.le_pending_details,
            'disbursement_date': date_to_iso(self.disbursement_date),
            'commitment_date': date_to_iso(self.commitment_date),
            'commitment_date_met': date_to_iso(self.commitment_date_met),
            'original_disclosed_date': date_to_iso(self.original_disclosed_date),
            'has_six_app_data_points': self.has_six_app_data_points,
            'cancelled_denied_coronavirus': self.cancelled_denied_coronavirus,

            # Legacy Milestone Dates
            'contract_received_date': date_to_iso(self.contract_received_date),
            'insurance_ordered_date': date_to_iso(self.insurance_ordered_date),
            'insurance_received_date': date_to_iso(self.insurance_received_date),
            'initial_disclosures_sent_date': date_to_iso(self.initial_disclosures_sent_date),
            'initial_disclosures_signed_date': date_to_iso(self.initial_disclosures_signed_date),
            'processor_submission_date': date_to_iso(self.processor_submission_date),
            'underwriting_submission_date': date_to_iso(self.underwriting_submission_date),
            'conditional_approval_date': date_to_iso(self.conditional_approval_date),
            'conditions_sent_date': date_to_iso(self.conditions_sent_date),
            'conditions_received_date': date_to_iso(self.conditions_received_date),
            'resubmission_date': date_to_iso(self.resubmission_date),
            'rate_lock_date': date_to_iso(self.rate_lock_date),
            'rate_lock_expiration_date': date_to_iso(self.rate_lock_expiration_date),
            'rate_lock_extension_date': date_to_iso(self.rate_lock_extension_date),
            'float_down_trigger_date': date_to_iso(self.float_down_trigger_date),
            'closing_disclosure_sent_date': date_to_iso(self.closing_disclosure_sent_date),
            'cd_received_signed_date': date_to_iso(self.cd_received_signed_date),
            'cd_delivered_date': date_to_iso(self.cd_delivered_date),
            'final_cd_issue_date': date_to_iso(self.final_cd_issue_date),
            'final_closing_package_sent_date': date_to_iso(self.final_closing_package_sent_date),
            'closing_scheduled_date': date_to_iso(self.closing_scheduled_date),
            'funding_date': date_to_iso(self.funding_date),
        }
