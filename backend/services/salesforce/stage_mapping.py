"""
Canonical Salesforce → CRM Stage Mapping
=========================================

Single source of truth for mapping Salesforce opportunity/lead statuses
to CRM LoanStage enum values (UPPERCASE strings).

Both sync engines (legacy webhook-based and new field-mapping-based)
must import from this module to prevent divergence.
"""

# Valid LoanStage enum values for reference:
# APPLICATION, DISCLOSED, PROCESSING, SUBMITTED, UNDERWRITING,
# UW_RECEIVED, CONDITIONAL_APPROVAL, APPROVED, SUSPENDED,
# CTC, CLEAR_TO_CLOSE, CLOSING, DOCS, DOCS_OUT, FUNDED,
# CANCELLED, DENIED, DEAD, NURTURE, WITHDRAWN, DOES_NOT_QUALIFY

SALESFORCE_STAGE_MAPPING = {
    # --- Application / Early ---
    "New": "APPLICATION",
    "Application": "APPLICATION",
    "Application Received": "APPLICATION",
    "Started": "APPLICATION",
    "File Started": "APPLICATION",
    "Prospecting": "APPLICATION",
    "Qualification": "APPLICATION",
    "Needs Analysis": "APPLICATION",
    # --- Disclosed ---
    "Disclosed": "DISCLOSED",
    "LE Sent": "DISCLOSED",
    # --- Processing ---
    "Processing": "PROCESSING",
    "Processed": "PROCESSING",
    "In Processing": "PROCESSING",
    "Contract Received": "PROCESSING",
    "Submitted to Processing": "PROCESSING",
    "In Process": "PROCESSING",
    "Loan in Process": "PROCESSING",
    "Document Collection": "PROCESSING",
    "Documents Requested": "PROCESSING",
    "Documents Received": "PROCESSING",
    "Appraisal Ordered": "PROCESSING",
    "Appraisal Received": "PROCESSING",
    "Insurance Ordered": "PROCESSING",
    "Insurance Received": "PROCESSING",
    "Title Ordered": "PROCESSING",
    "Title Received": "PROCESSING",
    "Value Proposition": "PROCESSING",
    "Id. Decision Makers": "PROCESSING",
    "Perception Analysis": "PROCESSING",
    # --- Submitted to UW ---
    "Submitted": "SUBMITTED",
    "Submitted to UW": "SUBMITTED",
    "Submitted to Underwriting": "SUBMITTED",
    "Proposal/Price Quote": "SUBMITTED",
    # --- Underwriting ---
    "Underwriting": "UNDERWRITING",
    "In Underwriting": "UNDERWRITING",
    "Negotiation/Review": "UNDERWRITING",
    # --- UW Received ---
    "UW Review": "UW_RECEIVED",
    "Underwriting Decision": "UW_RECEIVED",
    "UW Received": "UW_RECEIVED",
    "Received": "UW_RECEIVED",
    # --- Conditional Approval ---
    "Conditionally Approved": "CONDITIONAL_APPROVAL",
    "Conditional Approval": "CONDITIONAL_APPROVAL",
    "Cond. Approved": "CONDITIONAL_APPROVAL",
    "Approved with Conditions": "CONDITIONAL_APPROVAL",
    # --- Approved ---
    "Conditions Cleared": "APPROVED",
    "Approved": "APPROVED",
    # --- Clear to Close ---
    "Clear to Close": "CLEAR_TO_CLOSE",
    "CTC": "CLEAR_TO_CLOSE",
    # --- Closing ---
    "Closing": "CLOSING",
    "Closing Scheduled": "CLOSING",
    "Closing Date": "CLOSING",
    # --- Docs ---
    "Docs Drawing": "DOCS",
    "Doc Preparation": "DOCS",
    # --- Docs Out ---
    "Closing Docs Out": "DOCS_OUT",
    "Docs Out": "DOCS_OUT",
    "Docs Signing": "DOCS_OUT",
    "Docs Signed": "DOCS_OUT",
    # --- Funded ---
    "Funded": "FUNDED",
    "Loan Funded": "FUNDED",
    "Closed": "FUNDED",
    "Closed Won": "FUNDED",
    "Closed - Converted": "FUNDED",
    "Post-Closing": "FUNDED",
    "Post-Funding": "FUNDED",
    "Purchased": "FUNDED",
    "Completed": "FUNDED",
    "File Complete": "FUNDED",
    "Loan Sold": "FUNDED",
    "Settled": "FUNDED",
    "Shipped": "FUNDED",
    "Loan Shipped": "FUNDED",
    # --- Terminal / Special ---
    "Closed Lost": "WITHDRAWN",
    "Closed - Not Converted": "WITHDRAWN",
    "Cancelled": "CANCELLED",
    "Withdrawn": "WITHDRAWN",
    "Denied": "DENIED",
    "Rejected": "DENIED",
    "Dead": "DEAD",
    "Inactive": "DEAD",
    "Does Not Qualify": "DOES_NOT_QUALIFY",
    "Suspended": "SUSPENDED",
    "Nurture": "NURTURE",
}


def map_salesforce_stage(sf_stage: str) -> str:
    """Map a Salesforce stage/status string to CRM LoanStage enum value.

    Returns None for unmapped stages so callers can handle appropriately
    (e.g., preserve existing stage on updates, default to APPLICATION on creates).
    """
    if not sf_stage:
        return None
    return SALESFORCE_STAGE_MAPPING.get(sf_stage)


def infer_stage_from_dates(loan_data: dict) -> str:
    """Infer loan stage from date fields when Salesforce status is missing.

    Uses the highest-watermark date to determine where the loan actually is
    in the pipeline. Dates are the source of truth — if funded_date is set,
    the loan is funded regardless of what the status field says.

    Checked from most advanced stage to least, so the first match wins.
    """
    # Funded / post-closing
    if loan_data.get("funded_date"):
        return "FUNDED"
    # Docs phase
    if loan_data.get("docs_out_date"):
        return "DOCS_OUT"
    if loan_data.get("docs_ordered_date"):
        return "DOCS"
    # Clear to close
    if loan_data.get("clear_to_close_date"):
        return "CLEAR_TO_CLOSE"
    # Closing disclosure sent → at least in closing
    if loan_data.get("cd_sent_to_borrower_date"):
        return "CLOSING"
    # Approval
    if loan_data.get("loan_approved_date"):
        return "APPROVED"
    # Conditional approval
    if loan_data.get("conditions_for_review_date"):
        return "CONDITIONAL_APPROVAL"
    # Underwriting received
    if loan_data.get("uw_received_date"):
        return "UW_RECEIVED"
    # Processing indicators (appraisal, title, insurance, lock)
    if any(loan_data.get(f) for f in (
        "appraisal_received_date", "appraisal_completed_date",
        "appraisal_scheduled_date", "appraisal_ordered_date",
        "title_ordered_date", "insurance_ordered_date", "lock_date",
    )):
        return "PROCESSING"
    # Disclosed / LE sent
    if loan_data.get("le_pending_date"):
        return "DISCLOSED"
    # Application
    if loan_data.get("application_date"):
        return "APPLICATION"
    # No dates at all — genuinely new
    return "APPLICATION"


# Mapping from UPPERCASE LoanStage values to mixed-case LeadStage values.
# Used when a Salesforce status needs to be mapped to a lead stage instead
# of a loan stage (e.g., when the record is routed to the leads table).
_LOAN_STAGE_TO_LEAD_STAGE = {
    "APPLICATION": "Application",
    "DISCLOSED": "Disclosed",
    "PROCESSING": "Disclosed",
    "SUBMITTED": "Disclosed",
    "UNDERWRITING": "Disclosed",
    "UW_RECEIVED": "Disclosed",
    "CONDITIONAL_APPROVAL": "Disclosed",
    "APPROVED": "Disclosed",
    "SUSPENDED": "Disclosed",
    "CTC": "Disclosed",
    "CLEAR_TO_CLOSE": "Disclosed",
    "CLOSING": "Disclosed",
    "DOCS": "Disclosed",
    "DOCS_OUT": "Disclosed",
    "FUNDED": "Closed",
    "CANCELLED": "Withdrawn",
    "DENIED": "Does Not Qualify",
    "DEAD": "Withdrawn",
    "NURTURE": "Long-Term Nurture",
    "WITHDRAWN": "Withdrawn",
    "DOES_NOT_QUALIFY": "Does Not Qualify",
}

# Additional SF-specific lead statuses not in SALESFORCE_STAGE_MAPPING
# (standard SF Lead Status values that have no loan-stage equivalent)
_SF_LEAD_ONLY_STATUSES = {
    "New": "New",
    "Prospecting": "Prospect",
    "Open - Not Contacted": "New",
    "Working - Contacted": "Attempted Contact",
    "Qualified": "Pre-Qualified",
    "Pre-Qualified": "Pre-Qualified",
    "Pre-Approved": "Pre-Approved",
    "Long-Term Nurture": "Long-Term Nurture",
    "Closed - Not Converted": "Withdrawn",
    "Closed Lost": "Withdrawn",
    "Shipped": "Closed",
    "Complete": "Closed",
    "Loan Shipped": "Closed",
}


def map_salesforce_lead_stage(sf_status: str) -> str:
    """Map a Salesforce status to a valid CRM LeadStage enum string.

    Uses the canonical SALESFORCE_STAGE_MAPPING as the source of truth,
    then converts the UPPERCASE LoanStage to the equivalent LeadStage value.

    Falls back to SF-specific lead statuses for values that don't appear
    in the loan stage mapping (e.g., 'Open - Not Contacted').

    Returns 'New' for unmapped statuses.
    """
    if not sf_status:
        return "New"

    # First check SF-specific lead statuses
    if sf_status in _SF_LEAD_ONLY_STATUSES:
        return _SF_LEAD_ONLY_STATUSES[sf_status]

    # Then try the canonical loan stage mapping and convert to lead stage
    loan_stage = SALESFORCE_STAGE_MAPPING.get(sf_status)
    if loan_stage:
        return _LOAN_STAGE_TO_LEAD_STAGE.get(loan_stage, "New")

    return "New"
