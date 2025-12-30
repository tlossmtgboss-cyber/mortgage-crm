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
    Total fields: 120+ (expanded with processing log and milestone fields)
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

    # ==================== IMPORTANT DATES ====================
    date_file_created = Column(DateTime)
    preapproval_application_date = Column(Date)
    application_date = Column(Date)
    scheduled_approval_date = Column(Date)
    signing_appt_confirmed = Column(Boolean, default=False)
    signing_location = Column(String(255))
    signing_date = Column(Date)
    signing_time = Column(String(20))  # Time as string e.g., "2:00pm"
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

    # ==================== LEGACY MILESTONE DATES (kept for compatibility) ====================
    contract_received_date = Column(Date)
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

    # Rate Lock (legacy fields)
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

    # Final Milestone (legacy)
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
        def date_to_iso(d):
            return d.isoformat() if d else None

        def datetime_to_iso(dt):
            return dt.isoformat() if dt else None

        return {
            'id': str(self.id),
            'lead_profile_id': str(self.lead_profile_id) if self.lead_profile_id else None,
            'loan_number': self.loan_number,
            'amount': float(self.amount) if self.amount else None,
            'rate': float(self.rate) if self.rate else None,
            'term': self.term,
            'program': self.program,
            'lock_date': date_to_iso(self.lock_date),
            'lock_expiration': date_to_iso(self.lock_expiration),
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
            'created_at': datetime_to_iso(self.created_at),
            'updated_at': datetime_to_iso(self.updated_at),

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
