"""
Salesforce Loan Sync
Handles upserting and creating CRM loans from Salesforce data,
lead-to-loan promotion, and MUM promotion.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .sync_utils import _get_org_id_for_user, SF_API_VERSION
from .stage_mapping import map_salesforce_stage

logger = logging.getLogger(__name__)

# Valid columns on the loans table that can be set from Salesforce sync
VALID_LOAN_COLUMNS = {
    # Core borrower info
    'borrower_name', 'borrower_email', 'borrower_phone',
    # Core loan details
    'amount', 'rate', 'loan_type', 'loan_purpose', 'program',
    'loan_number', 'ltv', 'term', 'stage',
    # Core property info
    'property_address', 'property_city', 'property_state',
    'property_zip', 'property_type', 'property_value',
    # Core dates
    'closing_date', 'funded_date', 'application_date', 'lock_expiration_date',
    # Extended - property details
    'occupancy_type', 'property_county', 'property_ownership_type',
    'property_units', 'appraisal_value', 'purchase_price',
    # Extended - financial details
    'rate_type', 'monthly_payment', 'property_tax', 'hazard_insurance',
    'mortgage_insurance', 'hoa_amount', 'origination_fee',
    'estimated_prepaid_interest', 'points', 'index_rate', 'margin',
    # Extended - loan ratios
    'cltv', 'dti', 'apr', 'file_state',
    # Extended - 2nd loan
    'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
    # Extended - housing expenses
    'present_monthly_payment', 'proposed_monthly_payment',
    'present_housing_expense', 'proposed_housing_expense',
    # Additional
    'down_payment', 'credit_score', 'lock_date', 'lender',
    # Audit / sync metadata
    'salesforce_raw_stage',
}

# Comprehensive SF Opportunity field → CRM loan column mapping
SF_OPPORTUNITY_FIELD_MAP = {
    # Borrower info
    'Name': 'borrower_name',
    'Contact_Email__c': 'borrower_email',
    'Contact_Phone__c': 'borrower_phone',
    # Core loan details
    'Amount': 'amount',
    'Interest_Rate__c': 'rate',
    'Type': 'loan_type',
    'Loan_Purpose__c': 'loan_purpose',
    'Loan_Program__c': 'program',
    'Loan_Number__c': 'loan_number',
    'LTV__c': 'ltv',
    'Loan_Term__c': 'term',
    # Property info
    'Property_Address__c': 'property_address',
    'Property_City__c': 'property_city',
    'Property_State__c': 'property_state',
    'Property_Zip__c': 'property_zip',
    'Property_Type__c': 'property_type',
    'Property_Value__c': 'property_value',
    'Occupancy_Type__c': 'occupancy_type',
    'Appraisal_Value__c': 'appraisal_value',
    'Purchase_Price__c': 'purchase_price',
    # Dates
    'CloseDate': 'closing_date',
    'Funded_Date__c': 'funded_date',
    'Application_Date__c': 'application_date',
    'Lock_Expiration__c': 'lock_expiration_date',
    'Lock_Date__c': 'lock_date',
    # Financial details
    'Monthly_Payment__c': 'monthly_payment',
    'Down_Payment__c': 'down_payment',
    'Credit_Score__c': 'credit_score',
    'DTI__c': 'dti',
    'APR__c': 'apr',
    'CLTV__c': 'cltv',
    'Points__c': 'points',
    'Origination_Fee__c': 'origination_fee',
    # Jungo / MtgPlanner custom fields (override standard if present)
    'MtgPlanner_CRM__Loan_Number__c': 'loan_number',
    'MtgPlanner_CRM__Loan_Amount__c': 'amount',
    'MtgPlanner_CRM__Interest_Rate__c': 'rate',
    'MtgPlanner_CRM__Property_Address__c': 'property_address',
    'MtgPlanner_CRM__Property_City__c': 'property_city',
    'MtgPlanner_CRM__Property_State__c': 'property_state',
    'MtgPlanner_CRM__Property_Zip__c': 'property_zip',
    'MtgPlanner_CRM__Close_Date__c': 'closing_date',
    'MtgPlanner_CRM__Credit_Score__c': 'credit_score',
}

# Numeric CRM columns that should be coerced from SF string values
_NUMERIC_LOAN_COLUMNS = {
    'amount', 'rate', 'ltv', 'property_value', 'appraisal_value',
    'purchase_price', 'monthly_payment', 'down_payment', 'credit_score',
    'dti', 'apr', 'cltv', 'points', 'origination_fee', 'term',
}


def _map_salesforce_stage(sf_stage: str) -> str:
    """Map Salesforce Opportunity stage to CRM loan stage (UPPERCASE enum values).

    Returns None for unmapped stages so callers can handle appropriately
    (preserve existing stage on updates, default to APPLICATION on creates).
    Uses the canonical shared mapping from stage_mapping.py.
    """
    return map_salesforce_stage(sf_stage)


async def upsert_loan(
    db: Session,
    user_id: int,
    salesforce_id: str,
    data: Dict[str, Any],
    _skip_cross_table: bool = False,
) -> Optional[int]:
    """Upsert a loan from Salesforce data (Opportunity or Transaction Property)."""

    # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
    org_id = _get_org_id_for_user(db, user_id)

    # Check if loan exists by salesforce_id (scoped to org for multi-tenant isolation)
    existing = None
    if salesforce_id:
        if org_id:
            existing = db.execute(text("""
                SELECT id FROM loans
                WHERE salesforce_id = :sf_id AND organization_id = :org_id
                LIMIT 1
            """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
        else:
            # Legacy fallback: no org assigned yet
            existing = db.execute(text("""
                SELECT id FROM loans
                WHERE salesforce_id = :sf_id
                LIMIT 1
            """), {"sf_id": salesforce_id}).fetchone()

    # Cross-table check: if not found in loans, check if it exists as a lead.
    # If so, promote the lead to a loan instead of creating a duplicate.
    # Skipped when called from promote_lead_to_loan to prevent recursion.
    if not existing and salesforce_id and not _skip_cross_table:
        if org_id:
            lead_row = db.execute(text("""
                SELECT id FROM leads
                WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                    AND organization_id = :org_id
                LIMIT 1
            """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
        else:
            lead_row = db.execute(text("""
                SELECT id FROM leads
                WHERE salesforce_id = :sf_id
                   OR meta_data->>'salesforce_id' = :sf_id
                LIMIT 1
            """), {"sf_id": salesforce_id}).fetchone()

        if lead_row:
            logger.info(
                f"SF record {salesforce_id} exists as lead {lead_row[0]} — "
                f"promoting to loan via _upsert_loan cross-table check"
            )
            return await promote_lead_to_loan(
                db, user_id, salesforce_id, lead_row[0], data
            )

    # Build borrower_name from first+last if not directly provided
    if not data.get('borrower_name'):
        first = data.get('borrower_first_name', '')
        last = data.get('borrower_last_name', '')
        combined = f"{first} {last}".strip()
        if combined:
            data['borrower_name'] = combined

    # Coerce amount to float
    if 'amount' in data:
        try:
            data['amount'] = float(data['amount'] or 0)
        except (TypeError, ValueError):
            data['amount'] = 0

    # Map stage from Salesforce — capture raw value for audit
    if data.get('stage'):
        raw_stage = data['stage']
        mapped = _map_salesforce_stage(raw_stage)
        data['salesforce_raw_stage'] = raw_stage
        if mapped:
            data['stage'] = mapped
        else:
            # Unmapped stage: remove from data so existing stage is preserved on updates,
            # or APPLICATION default applies on creates (line 1088)
            del data['stage']
            logger.warning(f"Unmapped Salesforce stage '{raw_stage}' — preserving existing CRM stage")

    # Filter to only valid loan columns, drop empty values (keep amount even if 0)
    loan_data = {}
    dropped = []
    for k, v in data.items():
        if k in VALID_LOAN_COLUMNS and (v or v == 0 or k == 'amount'):
            loan_data[k] = v
        elif k not in VALID_LOAN_COLUMNS and k not in (
            'borrower_first_name', 'borrower_last_name',
            'target_entity', 'mapping_category',
        ):
            dropped.append(k)

    if dropped:
        logger.warning(f"SF→Loan sync dropped unmapped fields: {dropped}")

    if existing:
        # Update existing loan — also backfill organization_id if missing
        loan_id = existing[0]

        # Capture old stage before update for SLA tracking
        old_stage_row = db.execute(text(
            "SELECT stage::text, loan_number FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
        old_stage = old_stage_row[0] if old_stage_row else None
        loan_number = old_stage_row[1] if old_stage_row else None

        # Pre-write reconciliation: validate stage transition before writing
        new_stage = loan_data.get('stage')
        reconciliation_result = None
        if new_stage and new_stage != old_stage:
            try:
                from services.loan_reconciliation_service import LoanReconciliationService, ReconciliationAction
                recon = LoanReconciliationService(db)
                reconciliation_result = recon.reconcile(
                    loan_id,
                    old_data={"stage": old_stage, "loan_number": loan_number},
                    new_data={"stage": new_stage, "salesforce_raw_stage": loan_data.get('salesforce_raw_stage')},
                )
                if reconciliation_result.action == ReconciliationAction.SKIP:
                    # Idempotent or duplicate — don't overwrite stage
                    loan_data.pop('stage', None)
                    new_stage = None
                    logger.info(f"Reconciliation SKIP for loan {loan_id}: {reconciliation_result.audit_metadata}")
                elif reconciliation_result.action == ReconciliationAction.FLAG_FOR_REVIEW:
                    # Don't apply stage change; disposition task already created by reconciliation
                    loan_data.pop('stage', None)
                    new_stage = None
                    logger.info(f"Reconciliation FLAG_FOR_REVIEW for loan {loan_id}")
            except Exception as e:
                logger.warning(f"Pre-write reconciliation failed for loan {loan_id}, proceeding with write: {e}")

        set_parts = [f"{k} = :{k}" for k in loan_data.keys()]
        set_parts.append("salesforce_id = :salesforce_id")
        set_parts.append("organization_id = COALESCE(organization_id, :org_id)")
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

        loan_data['loan_id'] = loan_id
        loan_data['salesforce_id'] = salesforce_id
        loan_data['org_id'] = org_id

        query = (
            "UPDATE loans SET " + ", ".join(set_parts)
            + " WHERE id = :loan_id"
        )
        db.execute(text(query), loan_data)
        logger.info(f"Updated loan {loan_id} from Salesforce {salesforce_id}")

        # Wire to SLA tracking — detect stage changes
        if new_stage and new_stage != old_stage:
            try:
                from services.sla_tracking_service import track_loan_stage_change
                track_loan_stage_change(
                    db, loan_id, old_stage, new_stage,
                    loan_number=loan_number, organization_id=org_id
                )
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for loan {loan_id} stage change: {e}")

            # MUM promotion: if stage just changed to FUNDED, promote to MUM client
            if new_stage == 'FUNDED' or (reconciliation_result and reconciliation_result.should_promote_mum):
                try_mum_promotion(db, loan_id, user_id)

        return loan_id
    else:
        # Create new loan — use INSERT ... ON CONFLICT to guard against race conditions
        # where two concurrent sync requests both pass the SELECT check above and
        # attempt to INSERT a loan with the same salesforce_id. (Fix 3b)
        # NOTE: Requires unique partial index on salesforce_id:
        #   CREATE UNIQUE INDEX IF NOT EXISTS idx_loans_salesforce_id
        #   ON loans(salesforce_id) WHERE salesforce_id IS NOT NULL;

        # Use loan_number from Salesforce if provided, else generate one
        if not loan_data.get('loan_number'):
            loan_data['loan_number'] = f"SF-{str(uuid.uuid4())[:8].upper()}"

        loan_data['loan_officer_id'] = user_id
        loan_data['salesforce_id'] = salesforce_id
        loan_data['organization_id'] = org_id

        # Ensure required fields have defaults
        if not loan_data.get('borrower_name'):
            loan_data['borrower_name'] = 'Unknown Borrower'
        if not loan_data.get('amount'):
            loan_data['amount'] = 0
        if not loan_data.get('stage'):
            loan_data['stage'] = 'APPLICATION'

        columns = ", ".join(loan_data.keys())
        placeholders = ", ".join([f":{k}" for k in loan_data.keys()])

        # Build SET clause for the ON CONFLICT update path — update all mapped
        # fields except loan_officer_id and organization_id (preserve originals)
        conflict_set_parts = []
        for k in loan_data.keys():
            if k not in ('loan_officer_id', 'organization_id', 'salesforce_id', 'loan_number'):
                conflict_set_parts.append(f"{k} = EXCLUDED.{k}")
        conflict_set_parts.append("updated_at = CURRENT_TIMESTAMP")
        conflict_set_clause = ", ".join(conflict_set_parts)

        query = (
            "INSERT INTO loans (" + columns + ", created_at, updated_at)"
            " VALUES (" + placeholders + ", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            " ON CONFLICT (salesforce_id) WHERE salesforce_id IS NOT NULL"
            " DO UPDATE SET " + conflict_set_clause
            + " RETURNING id, (xmax = 0) AS was_inserted"
        )
        result = db.execute(text(query), loan_data)

        row = result.fetchone()
        loan_id = row[0]
        was_inserted = row[1] if len(row) > 1 else True

        if was_inserted:
            logger.info(f"Created loan {loan_id} ({loan_data['loan_number']}) from Salesforce {salesforce_id}")

            # Wire to SLA tracking — create initial milestone for new loan
            try:
                from services.sla_tracking_service import track_loan_created
                track_loan_created(
                    db, loan_id, loan_data['loan_number'], organization_id=org_id
                )
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for new loan {loan_id}: {e}")

            # MUM promotion: if new loan is created with FUNDED stage, promote immediately
            if loan_data.get('stage') == 'FUNDED':
                try_mum_promotion(db, loan_id, user_id)
        else:
            logger.info(
                f"Loan {loan_id} already existed (race condition resolved via ON CONFLICT) "
                f"from Salesforce {salesforce_id}"
            )

        return loan_id


async def update_loan_from_salesforce(
    db: Session,
    loan_id: int,
    sf_record: Dict[str, Any],
    sf_id: str
) -> bool:
    """
    Update a CRM loan with ALL fields from Salesforce Opportunity.

    Maps all text, number, and date fields from Salesforce to CRM
    using SF_OPPORTUNITY_FIELD_MAP. Only writes columns that exist
    in VALID_LOAN_COLUMNS.
    """
    from decimal import Decimal, InvalidOperation

    update_fields = {}

    # Map all known SF fields to CRM columns
    for sf_field, crm_column in SF_OPPORTUNITY_FIELD_MAP.items():
        value = sf_record.get(sf_field)
        if value is None or value == '':
            continue
        if crm_column not in VALID_LOAN_COLUMNS:
            continue

        # Coerce numeric columns
        if crm_column in _NUMERIC_LOAN_COLUMNS:
            try:
                value = float(Decimal(str(value)))
            except (InvalidOperation, TypeError, ValueError):
                logger.warning(f"SF→Loan sync: invalid numeric value for {sf_field}={value!r}")
                continue

        update_fields[crm_column] = value

    # Stage mapping (special handling — None means unmapped, preserve existing)
    if sf_record.get('StageName'):
        raw_stage = sf_record['StageName']
        mapped_stage = _map_salesforce_stage(raw_stage)
        update_fields['salesforce_raw_stage'] = raw_stage
        if mapped_stage:
            update_fields['stage'] = mapped_stage
        else:
            logger.warning(f"Unmapped SF stage '{raw_stage}' for loan {loan_id} — preserving existing stage")

    # Always update salesforce_id
    update_fields['salesforce_id'] = sf_id

    if len(update_fields) <= 1:  # Only salesforce_id, no real data
        return False

    # Capture old stage for MUM promotion check
    old_stage_row = db.execute(text(
        "SELECT stage::text FROM loans WHERE id = :lid"
    ), {"lid": loan_id}).fetchone()
    old_stage = old_stage_row[0] if old_stage_row else None

    # Build dynamic UPDATE query
    set_clauses = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
    update_fields['loan_id'] = loan_id

    query = (
        "UPDATE loans SET " + set_clauses + ","
        "    updated_at = CURRENT_TIMESTAMP"
        " WHERE id = :loan_id"
    )
    db.execute(text(query), update_fields)

    logger.info(f"Updated loan {loan_id} with {len(update_fields) - 1} fields from Salesforce Opportunity {sf_id}")

    # MUM promotion: if stage just changed to FUNDED, promote
    new_stage = update_fields.get('stage')
    if new_stage == 'FUNDED' and old_stage != 'FUNDED':
        user_row = db.execute(text(
            "SELECT loan_officer_id FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
        if user_row and user_row[0]:
            try_mum_promotion(db, loan_id, user_row[0])

    # Compliance hook: check TRID timing when disclosure dates are synced
    disclosure_fields = {'initial_disclosures_sent_date', 'cd_sent_to_borrower_date'}
    if disclosure_fields & set(update_fields.keys()):
        try:
            from services.compliance_check_service import check_trid_timing_async
            check_trid_timing_async(loan_id)
        except ImportError:
            pass  # Compliance service not available
        except Exception as e:
            logger.warning(f"TRID compliance check failed for loan {loan_id}: {e}")

    # ACO hook: trigger completeness review on key stage transitions from SF
    ACO_TRIGGER_STAGES = (
        "APPLICATION", "DISCLOSED", "SUBMITTED",
        "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    )
    if new_stage and new_stage != old_stage and new_stage in ACO_TRIGGER_STAGES:
        try:
            from tasks.app_completion_tasks import trigger_application_review_task
            trigger_application_review_task.delay(
                loan_id=loan_id,
                triggered_by=f"SF_SYNC_{new_stage}",
            )
            logger.info(f"ACO review queued for loan {loan_id} via SF sync stage {new_stage}")
        except Exception as e:
            logger.warning(f"ACO review trigger failed for loan {loan_id}: {e}")

    return True


async def promote_lead_to_loan(
    db: Session,
    user_id: int,
    salesforce_id: Optional[str],
    lead_id: int,
    loan_data: Dict[str, Any],
) -> Optional[int]:
    """
    Promote an existing lead to a loan record.

    1. Fetch lead data and merge as fallbacks into loan_data
    2. Create/update the loan via upsert_loan()
    3. Mark the lead as 'Disclosed' (converted to active loan)

    Returns the loan ID on success, None on failure.
    """
    # Fetch existing lead data for fallback values
    lead_row = db.execute(text("""
        SELECT name, first_name, last_name, email, phone,
               property_type, property_address, city, state, zip_code,
               credit_score, loan_amount, loan_type, property_value,
               down_payment, annual_income, employer_name
        FROM leads WHERE id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    if lead_row:
        # Use lead data as fallbacks (SF data in loan_data takes precedence)
        fallbacks = {
            'borrower_name': lead_row.name,
            'borrower_email': lead_row.email,
            'borrower_phone': lead_row.phone,
            'property_type': lead_row.property_type,
            'property_address': lead_row.property_address,
            'property_city': lead_row.city,
            'property_state': lead_row.state,
            'property_zip': lead_row.zip_code,
            'loan_type': lead_row.loan_type,
            'purchase_price': lead_row.property_value,
            'down_payment': lead_row.down_payment,
        }
        if lead_row.loan_amount and not loan_data.get('amount'):
            fallbacks['amount'] = lead_row.loan_amount

        for key, fallback_val in fallbacks.items():
            if fallback_val and not loan_data.get(key):
                loan_data[key] = fallback_val

    # Create/update the loan (skip cross-table check to prevent recursion)
    loan_id = await upsert_loan(
        db, user_id, salesforce_id, loan_data, _skip_cross_table=True
    )

    if loan_id:
        # Mark the lead as 'Disclosed' (converted) and store conversion metadata
        # Use CAST() instead of :: to avoid SQLAlchemy text() parameter parsing issues
        db.execute(text("""
            UPDATE leads SET
                stage = 'Disclosed',
                stage_changed_at = CURRENT_TIMESTAMP,
                meta_data = COALESCE(meta_data, CAST('{}' AS jsonb)) ||
                    jsonb_build_object(
                        'converted_to_loan_id', CAST(:loan_id AS text),
                        'converted_at', CAST(CURRENT_TIMESTAMP AS text)
                    ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :lead_id
        """), {"loan_id": loan_id, "lead_id": lead_id})

        logger.info(
            f"Promoted lead {lead_id} to loan {loan_id} "
            f"(salesforce_id={salesforce_id})"
        )

    return loan_id


def try_mum_promotion(db: Session, loan_id: int, user_id: int) -> Optional[int]:
    """
    Attempt to promote a funded loan to MUM client.
    Wrapped in try/except so failures don't block the sync.

    Returns MUM client ID if promoted, None otherwise.
    """
    try:
        from services.mum_promotion_service import maybe_promote_loan_to_mum
        mum_id = maybe_promote_loan_to_mum(db, loan_id, user_id)
        if mum_id:
            logger.info(f"Smart routing auto-promoted loan {loan_id} to MUM client {mum_id}")
        return mum_id
    except Exception as e:
        logger.warning(f"MUM promotion failed for loan {loan_id} (non-fatal): {e}")
        return None


async def create_crm_loan_if_new(
    db: Session,
    sf_opp: Dict[str, Any],
    user_id: int,
    get_contact_for_account_fn=None
) -> bool:
    """
    Create a CRM loan from a Salesforce Opportunity if it doesn't already exist.

    Returns True if a new loan was created, False if it already existed.
    """
    sf_id = sf_opp.get('Id')

    if not sf_id:
        return False

    # Check if already exists by salesforce_id
    existing = db.execute(text("""
        SELECT id FROM loans
        WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
        LIMIT 1
    """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

    if existing:
        return False

    # Cross-entity dedup: check if a LEAD already exists with this SF ID.
    # If so, we'll still create the loan but mark the lead as converted afterward.
    existing_lead_sf_id = db.execute(text("""
        SELECT id FROM leads
        WHERE salesforce_id = :sf_id AND owner_id = :user_id
        LIMIT 1
    """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

    # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
    org_id = _get_org_id_for_user(db, user_id)

    # Build new loan record from Opportunity
    name = sf_opp.get('Name') or 'Salesforce Opportunity'
    amount = float(sf_opp.get('Amount') or 0)
    # Fix 6: Default to APPLICATION when map_salesforce_stage returns None
    stage = _map_salesforce_stage(sf_opp.get('StageName', '')) or 'APPLICATION'
    close_date = sf_opp.get('CloseDate')
    loan_type = sf_opp.get('Type') or ''

    # Generate loan number (required NOT NULL field)
    loan_number = f"SF-{str(uuid.uuid4())[:8].upper()}"

    # Set funded_date if the stage is FUNDED (needed for MUM page)
    funded_date = close_date if stage == 'FUNDED' else None

    # Try to get borrower contact info from related Account/Contact
    borrower_email = None
    borrower_phone = None
    borrower_name = None
    account_id = sf_opp.get('AccountId')
    if account_id and get_contact_for_account_fn:
        try:
            contact_info = await get_contact_for_account_fn(
                db, sf_id, account_id, user_id
            )
            borrower_email = contact_info.get('email')
            borrower_phone = contact_info.get('phone')
            borrower_name = contact_info.get('full_name')
        except Exception as e:
            logger.exception(f"Failed to get contact info for account {account_id}: {e}")

    # Use contact name if available, otherwise fall back to Opportunity Name
    if not borrower_name:
        borrower_name = name

    db.execute(text("""
        INSERT INTO loans (
            loan_number, borrower_name, borrower_email, borrower_phone,
            amount, stage, closing_date, funded_date, loan_type,
            salesforce_id, loan_officer_id, organization_id,
            created_at, updated_at
        ) VALUES (
            :loan_number, :borrower_name, :borrower_email, :borrower_phone,
            :amount, :stage, :close_date, :funded_date, :loan_type,
            :sf_id, :user_id, :org_id,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {
        "loan_number": loan_number,
        "borrower_name": borrower_name,
        "borrower_email": borrower_email,
        "borrower_phone": borrower_phone,
        "amount": amount,
        "stage": stage,
        "close_date": close_date,
        "funded_date": funded_date,
        "loan_type": loan_type,
        "sf_id": sf_id,
        "user_id": user_id,
        "org_id": org_id,
    })

    # Get the new loan's ID for SLA tracking
    new_loan_row = db.execute(text("""
        SELECT id FROM loans WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
        LIMIT 1
    """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

    # Fix 4: removed PII (borrower_name, amount) from info log
    new_loan_id = new_loan_row[0] if new_loan_row else "unknown"
    logger.info(f"Created CRM loan {new_loan_id} from Salesforce Opportunity {sf_id} (stage={stage})")

    # Wire to SLA tracking — create initial milestone for new loan
    if new_loan_row:
        try:
            from services.sla_tracking_service import track_loan_created
            track_loan_created(
                db, new_loan_row[0], loan_number, organization_id=org_id
            )
        except Exception as e:
            logger.warning(f"SLA tracking hook failed for new SF loan {sf_id}: {e}")

    # Mark existing lead as converted (cross-entity cleanup)
    if existing_lead_sf_id:
        try:
            db.execute(text("""
                UPDATE leads SET
                    stage = 'Disclosed',
                    meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                        jsonb_build_object(
                            'converted_to_loan', 'true',
                            'converted_at', CURRENT_TIMESTAMP::text
                        ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :lead_id
            """), {"lead_id": existing_lead_sf_id[0]})
            logger.info(
                f"Marked lead {existing_lead_sf_id[0]} as converted "
                f"after loan creation from SF Opportunity {sf_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to mark lead as converted for SF {sf_id}: {e}")

    return True
