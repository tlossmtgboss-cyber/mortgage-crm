"""
Salesforce Record Routing
Smart routing logic to classify Salesforce records into the correct CRM table
(leads, loans, or mum_clients) based on status/stage values.
"""
import logging
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .stage_mapping import map_salesforce_stage

logger = logging.getLogger(__name__)

# SF statuses that indicate a prospect/lead (not yet an active loan)
LEAD_STATUSES = {
    'New', 'Prospecting', 'Qualification', 'Pre-Qualified', 'Pre-Approved',
    'Nurture', 'Open - Not Contacted', 'Working - Contacted',
    'Needs Analysis', 'Long-Term Nurture',
}

# SF statuses that indicate a funded/closed loan (MUM candidate)
FUNDED_STATUSES = {
    'Funded', 'Closed', 'Closed Won', 'Closed - Converted',
    'Loan Funded', 'Completed', 'Purchased', 'File Complete',
    'Post-Closing', 'Post-Funding', 'Loan Sold', 'Settled',
}


def classify_record_bucket(data: Dict[str, Any]) -> str:
    """
    Classify a Salesforce record into 'lead', 'loan', or 'loan_funded'
    based on the SF status value.

    Returns:
        'lead' - prospect/pre-approved, goes to leads table
        'loan' - active loan (application through CTC), goes to loans table
        'loan_funded' - funded/closed, goes to loans table + MUM promotion
    """
    # Check the stage/status field — could be in 'stage' (from field mapping),
    # raw SF field names, or '_sf_status' (injected from raw record)
    sf_status = (
        data.get('stage')
        or data.get('StageName')
        or data.get('Status')
        or data.get('_sf_status')
        or ''
    )

    if not sf_status:
        # No stage info — route based on data shape
        if data.get('amount') or data.get('loan_number'):
            return 'loan'
        return 'lead'

    # Check lead statuses first (exact match)
    if sf_status in LEAD_STATUSES:
        return 'lead'

    # Check funded statuses
    if sf_status in FUNDED_STATUSES:
        return 'loan_funded'

    # Check if map_salesforce_stage maps this to FUNDED
    mapped_stage = map_salesforce_stage(sf_status)
    if mapped_stage == 'FUNDED':
        return 'loan_funded'
    if mapped_stage == 'CANCELLED':
        return 'loan'  # Keep cancelled loans in loans table

    # Everything else with a recognized loan stage goes to loans
    # (APPLICATION, PROCESSING, SUBMITTED, UNDERWRITING, CTC, etc.)
    return 'loan'


def find_existing_record(
    db: Session,
    salesforce_id: Optional[str],
    email: Optional[str],
    user_id: int,
    organization_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Search across leads, loans, and mum_clients for an existing record
    matching the given salesforce_id or email.

    All salesforce_id lookups are scoped by organization_id when available
    to prevent cross-tenant data leakage.

    Returns:
        Dict with {'table': 'leads'|'loans'|'mum_clients', 'id': int, 'stage': str}
        or None if not found.
    """
    # Build org filter clause for salesforce_id lookups
    org_filter = "AND organization_id = :org_id" if organization_id else ""
    params_base = {"org_id": organization_id} if organization_id else {}

    # 1. Check loans by salesforce_id (org-scoped)
    if salesforce_id:
        params = {"sf_id": salesforce_id, **params_base}
        row = db.execute(text(f"""
            SELECT id, stage FROM loans
            WHERE salesforce_id = :sf_id {org_filter}
            LIMIT 1
        """), params).fetchone()
        if row:
            return {"table": "loans", "id": row[0], "stage": row[1]}

    # 2. Check leads by salesforce_id (org-scoped)
    if salesforce_id:
        params = {"sf_id": salesforce_id, **params_base}
        row = db.execute(text(f"""
            SELECT id, stage FROM leads
            WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                {org_filter}
            LIMIT 1
        """), params).fetchone()
        if row:
            return {"table": "leads", "id": row[0], "stage": row[1]}

    # 3. Check mum_clients by salesforce_id (org-scoped)
    if salesforce_id:
        params = {"sf_id": salesforce_id, **params_base}
        row = db.execute(text(f"""
            SELECT id FROM mum_clients
            WHERE salesforce_id = :sf_id {org_filter}
            LIMIT 1
        """), params).fetchone()
        if row:
            return {"table": "mum_clients", "id": row[0], "stage": None}

    # 4. Fallback: leads by email (scoped to user)
    if email:
        row = db.execute(text("""
            SELECT id, stage FROM leads
            WHERE LOWER(email) = LOWER(:email) AND owner_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()
        if row:
            return {"table": "leads", "id": row[0], "stage": row[1]}

    # 5. Fallback: loans by borrower_email (scoped to user)
    if email:
        row = db.execute(text("""
            SELECT id, stage FROM loans
            WHERE LOWER(borrower_email) = LOWER(:email) AND loan_officer_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()
        if row:
            return {"table": "loans", "id": row[0], "stage": row[1]}

    return None
