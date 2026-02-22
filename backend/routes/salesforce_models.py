"""
Salesforce Integration - Pydantic Models & Constants

Shared Pydantic schemas and configuration constants used across
all Salesforce route modules.
"""
from typing import Optional
from pydantic import BaseModel


# =============================================================================
# Deprecation Configuration
# =============================================================================

DEPRECATION_DATE = "2025-06-01"  # Date when these endpoints will be removed
SUNSET_LINK = "/api/integrations/salesforce"  # New endpoint location


# =============================================================================
# Whitelist of allowed column names for loans table to prevent SQL injection
# =============================================================================

ALLOWED_LOAN_COLUMNS = frozenset([
    'id', 'loan_number', 'borrower_name', 'borrower_email', 'borrower_phone',
    'preferred_communication', 'coborrower_name', 'co_borrower_email', 'stage',
    'program', 'loan_type', 'amount', 'loan_amount', 'purchase_price', 'down_payment',
    'rate', 'term', 'property_address', 'property_city', 'property_state', 'property_zip',
    'lock_date', 'closing_date', 'funded_date', 'loan_officer_id', 'processor',
    'underwriter', 'realtor_agent', 'title_company', 'days_in_stage', 'sla_status',
    'milestones', 'ai_insights', 'predicted_close_date', 'risk_score', 'user_metadata',
    'appraisal_ordered_date', 'appraisal_scheduled_date', 'appraisal_completed_date',
    'appraisal_value', 'lock_expiration_date', 'rate_lock_status', 'rate_lock_recommendation',
    'lock_term_days', 'salesforce_id', 'salesforce_last_synced_at', 'salesforce_sync_status',
    'prospect_date', 'application_date', 'le_pending_date', 'credit_only_date',
    'file_received_date', 'preapproval_date', 'uw_received_date', 'conditions_for_review_date',
    'suspended_date', 'loan_approved_date', 'approved_not_accepted_date', 'approval_expires_date',
    'appraisal_docs_expire_date', 'clear_to_close_date', 'cd_requested_date',
    'cd_sent_to_borrower_date', 'cd_acknowledged_date', 'docs_ordered_date', 'docs_out_date',
    'signing_date', 'wire_ordered_date', 'funding_date', 'funding_verified_date',
    'contract_received_date', 'earnest_money_verified_date', 'lender', 'origination_channel',
    'referral_source', 'created_at', 'updated_at', 'notes', 'ltv', 'cltv', 'dti',
])


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class SalesforceConnectionStatus(BaseModel):
    connected: bool
    instance_url: Optional[str] = None
    user_email: Optional[str] = None
    connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None


class SalesforceWebhookPayload(BaseModel):
    records: Optional[list] = None
    event_type: Optional[str] = None
    # Allow arbitrary fields for single-record format
    class Config:
        extra = "allow"


class SyncResponse(BaseModel):
    status: str
    records_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    errors: list = []
    message: str


class FieldMappingRequest(BaseModel):
    salesforce_field: str
    crm_field: str
    transform_type: Optional[str] = None


class PushLoanRequest(BaseModel):
    loan_id: int
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"


class PushBatchRequest(BaseModel):
    loan_ids: list
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"
