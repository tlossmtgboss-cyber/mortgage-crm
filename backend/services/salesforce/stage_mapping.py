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
    # --- Terminal / Special ---
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
