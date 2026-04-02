"""
Salesforce Lead Sync
Handles upserting and creating CRM leads from Salesforce data.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .sync_utils import _get_org_id_for_user, _sanitize_soql_email, SF_API_VERSION
from .stage_mapping import map_salesforce_lead_stage

logger = logging.getLogger(__name__)

# Valid columns on the leads table that can be set from Salesforce sync
VALID_LEAD_COLUMNS = {
    # Core identity
    'first_name', 'last_name', 'name', 'email', 'phone',
    'co_applicant_name', 'co_applicant_email', 'co_applicant_phone',
    'preferred_communication',
    # Pipeline
    'stage', 'source',
    # Loan qualification
    'loan_type', 'preapproval_amount', 'credit_score', 'debt_to_income',
    # Assignment
    'loan_number', 'notes',
    # Property
    'address', 'city', 'state', 'zip_code', 'property_type',
    'property_value', 'down_payment', 'property_address',
    # Financial
    'employment_status', 'annual_income', 'monthly_debts', 'first_time_buyer',
    'employer_name', 'industry',
    # Loan details
    'loan_amount', 'interest_rate', 'loan_term', 'apr', 'points',
    'lock_date', 'lock_expiration', 'closing_date', 'lender',
    'loan_officer', 'processor', 'underwriter', 'appraisal_value',
    'ltv', 'cltv', 'dti', 'dti_front', 'dti_back', 'program',
    'loan_purpose', 'file_state',
    # SLA milestones
    'lead_received_date', 'first_contact_attempt_date',
    'first_contact_successful_date', 'lead_qualification_date',
    'application_link_sent_date', 'application_started_date',
    'application_completed_date', 'credit_pulled_date',
    'preapproval_submission_date', 'preapproval_issued_date',
    'preapproval_expiration_date', 'realtor_referral_date',
    'rate_watch_enrollment_date', 'initial_consultation_date',
    # Property details (extended)
    'occupancy_type', 'property_county', 'property_ownership_type',
    'property_units',
    # Financial details (extended)
    'rate_type', 'monthly_payment', 'property_tax', 'hazard_insurance',
    'mortgage_insurance', 'hoa_amount', 'origination_fee',
    'estimated_prepaid_interest', 'index_rate', 'margin',
    # 2nd loan
    'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
    # Housing expenses
    'present_housing_expense', 'proposed_housing_expense',
    'present_monthly_payment', 'proposed_monthly_payment',
    # Referral
    'referral_score',
}


async def upsert_lead(
    db: Session,
    user_id: int,
    salesforce_id: str,
    data: Dict[str, Any]
) -> Optional[int]:
    """Upsert a lead from Salesforce"""

    # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
    org_id = _get_org_id_for_user(db, user_id)

    # Check if lead exists by salesforce_id or email (org-scoped)
    existing = None
    if salesforce_id:
        if org_id:
            existing = db.execute(text("""
                SELECT id FROM leads
                WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                    AND organization_id = :org_id
                LIMIT 1
            """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
        else:
            existing = db.execute(text("""
                SELECT id FROM leads
                WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
                LIMIT 1
            """), {"sf_id": salesforce_id}).fetchone()

    if not existing and data.get('email'):
        existing = db.execute(text("""
            SELECT id FROM leads
            WHERE LOWER(email) = LOWER(:email) AND owner_id = :user_id
            LIMIT 1
        """), {"email": data.get('email'), "user_id": user_id}).fetchone()

    # Build core identity fields with Salesforce fallbacks
    first_name = data.get('first_name') or data.get('FirstName', '')
    last_name = data.get('last_name') or data.get('LastName', '')
    data['first_name'] = first_name
    data['last_name'] = last_name
    data['name'] = f"{first_name} {last_name}".strip() or 'Unknown'
    if not data.get('email'):
        data['email'] = data.get('Email', '')
    if not data.get('phone'):
        data['phone'] = data.get('Phone', '')
    if not data.get('source'):
        data['source'] = data.get('LeadSource', 'Salesforce')

    # Filter to valid lead columns, drop empty values (keep 'name')
    lead_data = {}
    dropped = []
    for k, v in data.items():
        if k in VALID_LEAD_COLUMNS and (v or v == 0 or k == 'name'):
            lead_data[k] = v
        elif k not in VALID_LEAD_COLUMNS and k not in (
            'FirstName', 'LastName', 'Email', 'Phone', 'Company',
            'LeadSource', 'target_entity', 'mapping_category',
        ):
            dropped.append(k)

    if dropped:
        logger.warning(f"SF→Lead sync dropped unmapped fields: {dropped}")

    if existing:
        # Update existing lead — also backfill organization_id if missing
        lead_id = existing[0]

        # Capture old stage before update for SLA tracking
        old_stage_row = db.execute(text(
            "SELECT stage::text FROM leads WHERE id = :lid"
        ), {"lid": lead_id}).fetchone()
        old_stage = old_stage_row[0] if old_stage_row else None

        set_clauses = ", ".join([f"{k} = :{k}" for k in lead_data.keys()])
        if set_clauses:
            lead_data['lead_id'] = lead_id
            lead_data['salesforce_id'] = salesforce_id
            lead_data['org_id'] = org_id
            query = (
                "UPDATE leads SET " + set_clauses + ","
                "    salesforce_id = :salesforce_id,"
                "    organization_id = COALESCE(organization_id, :org_id),"
                "    updated_at = CURRENT_TIMESTAMP"
                " WHERE id = :lead_id"
            )
            db.execute(text(query), lead_data)
        logger.info(f"Updated lead {lead_id} from Salesforce {salesforce_id} ({len(lead_data)} fields)")

        # Wire to SLA tracking — detect stage changes
        new_stage = lead_data.get('stage')
        if new_stage and new_stage != old_stage:
            try:
                from services.sla_tracking_service import track_lead_stage_change
                track_lead_stage_change(db, lead_id, old_stage, new_stage, organization_id=org_id)
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for lead {lead_id} stage change: {e}")

        return lead_id
    else:
        # Create new lead — use INSERT ... ON CONFLICT to guard against race conditions
        # where two concurrent sync requests both pass the SELECT check above and
        # attempt to INSERT a lead with the same salesforce_id. (Fix 3b)
        # NOTE: Requires unique partial index on salesforce_id:
        #   CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_salesforce_id
        #   ON leads(salesforce_id) WHERE salesforce_id IS NOT NULL;
        lead_data['owner_id'] = user_id
        lead_data['salesforce_id'] = salesforce_id
        if not lead_data.get('stage'):
            lead_data['stage'] = 'New'
        lead_data['organization_id'] = org_id

        columns = ", ".join(lead_data.keys())
        placeholders = ", ".join([f":{k}" for k in lead_data.keys()])

        # Build SET clause for the ON CONFLICT update path — update all mapped
        # fields except owner_id and organization_id (preserve originals)
        conflict_set_parts = []
        for k in lead_data.keys():
            if k not in ('owner_id', 'organization_id', 'salesforce_id'):
                conflict_set_parts.append(f"{k} = EXCLUDED.{k}")
        conflict_set_parts.append("updated_at = CURRENT_TIMESTAMP")
        conflict_set_clause = ", ".join(conflict_set_parts)

        query = (
            "INSERT INTO leads (" + columns + ", created_at, updated_at)"
            " VALUES (" + placeholders + ", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            " ON CONFLICT (salesforce_id) WHERE salesforce_id IS NOT NULL"
            " DO UPDATE SET " + conflict_set_clause
            + " RETURNING id, (xmax = 0) AS was_inserted"
        )
        result = db.execute(text(query), lead_data)

        row = result.fetchone()
        lead_id = row[0]
        was_inserted = row[1] if len(row) > 1 else True

        if was_inserted:
            logger.info(f"Created lead {lead_id} from Salesforce {salesforce_id} ({len(lead_data)} fields)")
            # Wire to SLA tracking — create initial milestone for new lead
            try:
                from services.sla_tracking_service import track_lead_created
                track_lead_created(db, lead_id, organization_id=org_id)
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for new lead {lead_id}: {e}")
        else:
            logger.info(
                f"Lead {lead_id} already existed (race condition resolved via ON CONFLICT) "
                f"from Salesforce {salesforce_id}"
            )

        return lead_id


async def update_lead_from_salesforce(
    db: Session,
    lead_id: int,
    sf_record: Dict[str, Any],
    sf_type: str,
    sf_id: str,
    map_sf_lead_status_to_crm_fn
) -> bool:
    """
    Update a CRM lead with ALL fields from Salesforce Lead/Contact.

    Maps all text, number, and date fields from Salesforce to CRM.
    """
    # Build update data from Salesforce record
    update_fields = {}

    # Text fields
    if sf_record.get('FirstName'):
        update_fields['first_name'] = sf_record['FirstName']
    if sf_record.get('LastName'):
        update_fields['last_name'] = sf_record['LastName']
    if sf_record.get('Email'):
        update_fields['email'] = sf_record['Email']
    if sf_record.get('Phone'):
        update_fields['phone'] = sf_record['Phone']
    if sf_record.get('Company'):
        update_fields['employer_name'] = sf_record['Company']
    if sf_record.get('Industry'):
        update_fields['industry'] = sf_record['Industry']

    # Address fields
    street = sf_record.get('Street') or sf_record.get('MailingStreet')
    city = sf_record.get('City') or sf_record.get('MailingCity')
    state = sf_record.get('State') or sf_record.get('MailingState')
    postal = sf_record.get('PostalCode') or sf_record.get('MailingPostalCode')

    if street:
        update_fields['address'] = street
    if city:
        update_fields['city'] = city
    if state:
        update_fields['state'] = state
    if postal:
        update_fields['zip_code'] = postal

    # Source and status
    if sf_record.get('LeadSource'):
        update_fields['source'] = sf_record['LeadSource']
    if sf_record.get('Status'):
        update_fields['stage'] = map_sf_lead_status_to_crm_fn(sf_record['Status'])
    if sf_record.get('Description'):
        update_fields['notes'] = sf_record['Description']

    # Number fields
    if sf_record.get('AnnualRevenue'):
        update_fields['annual_income'] = float(sf_record['AnnualRevenue'])

    # Always update salesforce_id and sync timestamp
    update_fields['salesforce_id'] = sf_id

    if not update_fields:
        return False

    # Build dynamic UPDATE query
    set_clauses = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
    update_fields['lead_id'] = lead_id
    update_fields['sf_type'] = sf_type

    query = (
        "UPDATE leads SET " + set_clauses + ","
        "    meta_data = COALESCE(meta_data, '{}'::jsonb) ||"
        "        jsonb_build_object("
        "            'salesforce_type', :sf_type,"
        "            'salesforce_synced_at', CURRENT_TIMESTAMP"
        "        ),"
        "    updated_at = CURRENT_TIMESTAMP"
        " WHERE id = :lead_id"
    )
    db.execute(text(query), update_fields)

    logger.info(f"Updated lead {lead_id} with {len(update_fields)} fields from Salesforce {sf_type} {sf_id}")
    return True


async def create_crm_lead_if_new(
    db: Session,
    sf_record: Dict[str, Any],
    sf_type: str,
    user_id: int,
    map_sf_lead_status_to_crm_fn
) -> bool:
    """
    Create a CRM lead from a Salesforce Lead/Contact if it doesn't already exist.

    Returns True if a new lead was created, False if it already existed.
    """
    sf_id = sf_record.get('Id')
    email = sf_record.get('Email')

    if not sf_id:
        return False

    # Check if already exists by salesforce_id
    existing = db.execute(text("""
        SELECT id FROM leads
        WHERE salesforce_id = :sf_id AND owner_id = :user_id
        LIMIT 1
    """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

    if existing:
        return False

    # Cross-entity dedup: check if a LOAN already exists with this SF ID.
    # This prevents creating a duplicate lead when the legacy webhook
    # already created a loan from the same Salesforce record.
    existing_loan = db.execute(text("""
        SELECT id, stage FROM loans
        WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
        LIMIT 1
    """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

    if existing_loan:
        logger.info(
            f"Skipping lead creation for SF {sf_type} {sf_id}: "
            f"already exists as loan {existing_loan[0]} (stage={existing_loan[1]})"
        )
        return False

    # Check if already exists by email (for this user)
    if email:
        existing_by_email = db.execute(text("""
            SELECT id FROM leads
            WHERE email = :email AND owner_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()

        if existing_by_email:
            # Update salesforce_id on the existing record
            db.execute(text("""
                UPDATE leads SET salesforce_id = :sf_id,
                    meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                        jsonb_build_object('salesforce_type', :sf_type,
                                          'salesforce_synced_at', CURRENT_TIMESTAMP::text),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :lead_id
            """), {"sf_id": sf_id, "sf_type": sf_type, "lead_id": existing_by_email.id})
            return False

        # Cross-entity dedup by email: check if a LOAN exists with this email
        existing_loan_by_email = db.execute(text("""
            SELECT id, stage FROM loans
            WHERE LOWER(borrower_email) = LOWER(:email) AND loan_officer_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()

        if existing_loan_by_email:
            logger.info(
                f"Skipping lead creation for SF {sf_type} {sf_id}: "
                f"loan {existing_loan_by_email[0]} already exists with matching email"
            )
            return False

    # Build new lead record
    first_name = sf_record.get('FirstName') or ''
    last_name = sf_record.get('LastName') or 'Unknown'
    full_name = f"{first_name} {last_name}".strip() or 'Unknown'

    # Address fields differ between Lead and Contact
    street = sf_record.get('Street') or sf_record.get('MailingStreet')
    city = sf_record.get('City') or sf_record.get('MailingCity')
    state = sf_record.get('State') or sf_record.get('MailingState')
    zip_code = sf_record.get('PostalCode') or sf_record.get('MailingPostalCode')

    source = sf_record.get('LeadSource') or 'Salesforce'
    # Check MtgPlanner_CRM__Status__c first (Jungo custom), then standard Status
    sf_status = (
        sf_record.get('MtgPlanner_CRM__Status__c')
        or sf_record.get('Status')
        or ''
    )
    stage = map_sf_lead_status_to_crm_fn(sf_status)
    phone = sf_record.get('Phone') or sf_record.get('MobilePhone')
    employer_name = sf_record.get('Company') or ''
    industry = sf_record.get('Industry') or ''
    notes = sf_record.get('Description') or ''

    # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
    org_id = _get_org_id_for_user(db, user_id)

    result = db.execute(text("""
        INSERT INTO leads (
            name, first_name, last_name, email, phone, employer_name,
            industry, source, stage, address, city, state, zip_code,
            notes, salesforce_id, owner_id, organization_id,
            meta_data, created_at, updated_at
        ) VALUES (
            :name, :first_name, :last_name, :email, :phone, :employer_name,
            :industry, :source, :stage, :address, :city, :state, :zip_code,
            :notes, :sf_id, :owner_id, :org_id,
            jsonb_build_object('salesforce_type', :sf_type,
                               'salesforce_imported_at', CURRENT_TIMESTAMP::text,
                               'salesforce_source', 'auto_import'),
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING id
    """), {
        "name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "employer_name": employer_name,
        "industry": industry,
        "source": source,
        "stage": stage,
        "address": street,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "notes": notes,
        "sf_id": sf_id,
        "owner_id": user_id,
        "org_id": org_id,
        "sf_type": sf_type,
    })

    lead_id = result.fetchone()[0]
    logger.info(f"Created CRM lead {lead_id} from Salesforce {sf_type} {sf_id}")

    # Wire to SLA tracking — create initial milestone for new lead
    try:
        from services.sla_tracking_service import track_lead_created
        track_lead_created(db, lead_id, organization_id=org_id)
    except Exception as e:
        logger.warning(f"SLA tracking hook failed for new SF lead {lead_id}: {e}")

    return True


def remap_loan_fields_for_lead(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform loan-shaped field names into lead-shaped field names.
    Used when a Salesforce record needs to go to the leads table but
    the field mappings targeted loan columns.
    """
    lead_data = {}

    # Direct column name mappings (loan → lead)
    field_map = {
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

    for key, value in data.items():
        if value is None or value == '':
            continue
        if key in field_map:
            lead_data[field_map[key]] = value
        elif key in VALID_LEAD_COLUMNS:
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
