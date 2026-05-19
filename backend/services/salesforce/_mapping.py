"""
Pure field/stage mapping helpers for Salesforce sync.

Extracted from sync_service.py. These are stateless utilities;
SalesforceSyncService instance methods delegate to them.
"""
from typing import Any, Dict, List


# CRM loan stage → Salesforce Opportunity stage
CRM_LOAN_STAGE_TO_SF = {
    'Application': 'Qualification',
    'Processing': 'Needs Analysis',
    'Submitted': 'Proposal/Price Quote',
    'Underwriting': 'Negotiation/Review',
    'Conditional Approval': 'Negotiation/Review',
    'Approved': 'Negotiation/Review',
    'CTC': 'Negotiation/Review',
    'Clear to Close': 'Negotiation/Review',
    'Docs Out': 'Negotiation/Review',
    'Closing': 'Negotiation/Review',
    'Funded': 'Closed Won',
    'Cancelled': 'Closed Lost',
    'Denied': 'Closed Lost',
}

# CRM lead stage → Salesforce Lead status
CRM_LEAD_STAGE_TO_SF = {
    'new': 'Open - Not Contacted',
    'contacted': 'Working - Contacted',
    'qualified': 'Closed - Converted',
    'unqualified': 'Closed - Not Converted',
    'converted': 'Closed - Converted',
}

# Loan-column → lead-column rename map (used when an SF record routed
# to leads was originally mapped against loan-shaped columns).
LOAN_TO_LEAD_FIELD_MAP = {
    'borrower_name': 'name',
    'borrower_email': 'email',
    'borrower_phone': 'phone',
    'amount': 'loan_amount',
    'property_city': 'city',
    'property_state': 'state',
    'property_zip': 'zip_code',
    'rate': 'interest_rate',
    'coborrower_name': 'co_applicant_name',
    'co_borrower_email': 'co_applicant_email',
    'purchase_price': 'property_value',
}


def map_crm_stage_to_salesforce(crm_stage: str) -> str:
    """Map CRM loan stage to Salesforce Opportunity stage."""
    return CRM_LOAN_STAGE_TO_SF.get(crm_stage, 'Qualification')


def map_crm_lead_stage_to_salesforce(crm_stage: str) -> str:
    """Map CRM lead stage to Salesforce Lead status."""
    return CRM_LEAD_STAGE_TO_SF.get(crm_stage, 'Open - Not Contacted')


def remap_loan_fields_for_lead(
    data: Dict[str, Any],
    valid_lead_columns: set,
) -> Dict[str, Any]:
    """
    Transform loan-shaped field names into lead-shaped field names.
    Used when a Salesforce record needs to go to the leads table but
    the field mappings targeted loan columns.
    """
    lead_data: Dict[str, Any] = {}

    for key, value in data.items():
        if value is None or value == '':
            continue
        if key in LOAN_TO_LEAD_FIELD_MAP:
            lead_data[LOAN_TO_LEAD_FIELD_MAP[key]] = value
        elif key in valid_lead_columns:
            # Field name is already valid for leads
            lead_data[key] = value
        # else: drop fields that have no lead equivalent

    # Build name from first/last if not set
    if not lead_data.get('name'):
        first = data.get('borrower_first_name', '') or lead_data.get('first_name', '')
        last = data.get('borrower_last_name', '') or lead_data.get('last_name', '')
        combined = f"{first} {last}".strip()
        if combined:
            lead_data['name'] = combined

    return lead_data


def group_mappings_by_object(mappings: List[Any]) -> Dict[str, List[Any]]:
    """Group field mappings by source object."""
    result: Dict[str, List[Any]] = {}
    for mapping in mappings:
        obj = mapping.source_object
        if obj not in result:
            result[obj] = []
        result[obj].append(mapping)
    return result


def group_mappings_by_entity(mappings: List[Any]) -> Dict[str, List[Any]]:
    """Group field mappings by target entity."""
    result: Dict[str, List[Any]] = {}
    for mapping in mappings:
        entity = mapping.target_entity
        if entity not in result:
            result[entity] = []
        result[entity].append(mapping)
    return result
