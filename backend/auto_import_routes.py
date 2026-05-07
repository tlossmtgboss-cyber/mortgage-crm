"""
Auto Import Routes - Automatic field mapping and data import
Zero-configuration Excel/CSV imports using intelligent fuzzy matching
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional
import pandas as pd
import io
import json
import uuid
from datetime import datetime, timezone
import logging
import os

from field_mapping_service import (
    auto_map_fields,
    transform_data,
    MappingResult,
    FIELD_MAPPINGS,
)

from utils.pii_mask import mask_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auto-import", tags=["Auto Import"])

# Import database dependencies from database module (avoids circular import with main.py)
from database import get_db, SessionLocal

# Import get_current_user - catch any exception (not just ImportError) because
# running via `python3 main.py` causes __main__ vs main module name conflict
try:
    from auth.dependencies import get_current_user
except Exception as e:
    logger.exception(f"Failed to import get_current_user from main: {e}")
    from fastapi import HTTPException as _HTTPException
    async def get_current_user():
        raise _HTTPException(status_code=503, detail="Authentication service not initialized")


def get_db_connection():
    """Get a raw psycopg2 database connection for history queries.

    WARNING: This is a raw psycopg2 connection WITHOUT RLS tenant context.
    Only used for import-history queries that are already scoped by user_id
    in the SQL. For ORM operations, use get_db from db.py instead.
    """
    import psycopg2
    import os
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def parse_file_to_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    """Parse uploaded file (CSV or Excel) into a DataFrame"""
    try:
        if filename.endswith('.csv'):
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(content), encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode CSV file with any common encoding")
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise ValueError(f"Unsupported file format: {filename}")

        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]

        # Remove completely empty rows
        df = df.dropna(how='all').reset_index(drop=True)

        return df
    except Exception as e:
        logger.error(f"Error parsing file {filename}: {e}")
        raise ValueError(f"Error parsing file: {str(e)}")


def get_table_columns(db, table_name: str) -> set:
    """Get valid column names for a database table using SQLAlchemy"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        columns = inspector.get_columns(table_name)
        return {col['name'] for col in columns}
    except Exception as e:
        logger.warning(f"Error getting columns for {table_name}: {e}")
        return set()


# Whitelist of valid column names for each importable table
# This prevents SQL injection via malicious CSV column headers
VALID_IMPORT_COLUMNS = {
    'leads': {
        'id', 'first_name', 'last_name', 'name', 'email', 'phone', 'address',
        'city', 'state', 'zip_code', 'loan_amount', 'property_value', 'loan_type',
        'loan_officer', 'processor', 'credit_score', 'source', 'stage', 'loan_number',
        'ltv', 'cltv', 'dti_front', 'dti_back', 'organization_code', 'created_at',
        'updated_at', 'status_date', 'program', 'notes', 'organization_id', 'user_id',
        'lead_score', 'status', 'property_type', 'loan_purpose',
    },
    'loans': {
        'id', 'loan_number', 'organization_code', 'borrower_name', 'borrower_email',
        'borrower_phone', 'co_borrower_email', 'property_address', 'property_city',
        'property_state', 'property_zip', 'property_type', 'occupancy_type',
        'appraisal_value', 'purchase_price', 'amount', 'rate', 'stage', 'loan_purpose',
        'program', 'loan_program_code', 'lender', 'ltv', 'cltv', 'first_ratio',
        'second_ratio', 'credit_score', 'cash_to_borrower', 'lender_credit',
        'loan_officer_name', 'processor', 'processor_email', 'underwriter', 'closer',
        'realtor_agent', 'title_company', 'created_at', 'updated_at', 'loan_officer_id',
        'organization_id', 'status', 'notes', 'closing_date', 'lock_date', 'lock_expiration',
    },
    'mum_clients': {
        'id', 'client_name', 'email', 'phone', 'address', 'city', 'state', 'zip_code',
        'loan_number', 'original_loan_amount', 'current_loan_amount', 'interest_rate',
        'appraisal_value_at_closing', 'current_property_value', 'closing_date',
        'first_payment_date', 'created_at', 'updated_at', 'user_id', 'organization_id',
        'status', 'notes', 'loan_type', 'property_type', 'lender', 'servicer',
    },
}


def sanitize_column_name(column: str) -> str:
    """
    Sanitize a column name for safe SQL use.

    Only allows alphanumeric characters and underscores.
    Returns empty string if column contains invalid characters.
    """
    import re
    # Only allow alphanumeric and underscore, must start with letter or underscore
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column):
        return column
    return ''


def validate_columns_for_table(columns: list, table_name: str) -> list:
    """
    Validate and filter column names against the whitelist for a table.

    Returns only columns that are in the whitelist and pass sanitization.
    Raises ValueError if no valid columns remain.
    """
    valid_columns = VALID_IMPORT_COLUMNS.get(table_name, set())
    if not valid_columns:
        raise ValueError(f"Unknown table for import: {table_name}")

    sanitized = []
    for col in columns:
        clean_col = sanitize_column_name(col)
        if clean_col and clean_col.lower() in {c.lower() for c in valid_columns}:
            # Use the original case if it matches whitelist
            matching = [c for c in valid_columns if c.lower() == clean_col.lower()]
            sanitized.append(matching[0] if matching else clean_col)
        else:
            logger.warning(f"Ignoring invalid/disallowed column '{col}' for table '{table_name}'")

    if not sanitized:
        raise ValueError(f"No valid columns found for table {table_name}")

    return sanitized


def build_safe_update_sql(table_name: str, update_data: dict) -> tuple:
    """
    Build a safe UPDATE SQL statement with validated column names.

    Returns (sql_string, params_dict) tuple.
    Raises ValueError if columns are invalid.

    SAFETY: table_name is validated against the VALID_IMPORT_COLUMNS dict
    (hardcoded server-side keys: 'leads', 'loans', 'mum_clients').
    Column names are validated against the per-table allowlist AND pass
    alphanumeric-only regex in sanitize_column_name(). Values use :param
    bind placeholders (never interpolated).
    """
    # Validate table_name against hardcoded allowlist (VALID_IMPORT_COLUMNS keys)
    if table_name not in VALID_IMPORT_COLUMNS:
        raise ValueError(f"Unknown table for import: {table_name}")

    validated_columns = validate_columns_for_table(list(update_data.keys()), table_name)

    # Filter update_data to only include validated columns
    safe_data = {k: v for k, v in update_data.items() if k in validated_columns}

    # SAFETY: col values come from validated_columns (allowlisted + regex-sanitized).
    # Values use SQLAlchemy :param bind syntax — never interpolated into SQL.
    set_clause = ', '.join([f"{col} = :{col}" for col in safe_data.keys()])
    sql = f"UPDATE {table_name} SET {set_clause} WHERE id = :id"

    return sql, safe_data


def build_safe_insert_sql(table_name: str, row_data: dict) -> tuple:
    """
    Build a safe INSERT SQL statement with validated column names.

    Returns (sql_string, params_dict) tuple.
    Raises ValueError if columns are invalid.

    SAFETY: table_name is validated against the VALID_IMPORT_COLUMNS dict
    (hardcoded server-side keys: 'leads', 'loans', 'mum_clients').
    Column names are validated against the per-table allowlist AND pass
    alphanumeric-only regex in sanitize_column_name(). Values use :param
    bind placeholders (never interpolated).
    """
    # Validate table_name against hardcoded allowlist (VALID_IMPORT_COLUMNS keys)
    if table_name not in VALID_IMPORT_COLUMNS:
        raise ValueError(f"Unknown table for import: {table_name}")

    validated_columns = validate_columns_for_table(list(row_data.keys()), table_name)

    # Filter row_data to only include validated columns
    safe_data = {k: v for k, v in row_data.items() if k in validated_columns}

    # SAFETY: col values come from validated_columns (allowlisted + regex-sanitized).
    # Values use SQLAlchemy :param bind syntax — never interpolated into SQL.
    columns_str = ', '.join(safe_data.keys())
    placeholders = ', '.join([f":{col}" for col in safe_data.keys()])
    sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

    return sql, safe_data


def map_to_existing_columns(row_data: dict, destination: str) -> dict:
    """
    Map the auto-imported fields to existing database columns.
    This handles the translation between our generic field names and actual table columns.
    """
    result = {}

    if destination == 'leads':
        # Map from auto-import fields to leads table columns
        field_map = {
            'borrower_first_name': 'first_name',
            'borrower_last_name': 'last_name',
            'borrower_email': 'email',
            'borrower_mobile_phone': 'phone',
            'property_street': 'address',
            'property_city': 'city',
            'property_state': 'state',
            'property_zip': 'zip_code',
            'loan_amount': 'loan_amount',
            'purchase_price': 'property_value',
            'loan_purpose': 'loan_type',
            'loan_officer_name': 'loan_officer',
            'loan_processor_name': 'processor',
            'credit_score': 'credit_score',
            'referral_source': 'source',
            'loan_status': 'stage',
            'file_name': 'loan_number',
            'ltv': 'ltv',
            'cltv': 'cltv',
            'first_ratio': 'dti_front',
            'second_ratio': 'dti_back',
            'organization_code': 'organization_code',
            'date_created': 'created_at',
            'status_date': 'status_date',
            'loan_program_name': 'program',
        }

        for auto_field, db_field in field_map.items():
            if auto_field in row_data and row_data[auto_field] is not None:
                result[db_field] = row_data[auto_field]

        # Combine first and last name if both exist
        first_name = row_data.get('borrower_first_name', '')
        last_name = row_data.get('borrower_last_name', '')
        if first_name or last_name:
            result['name'] = f"{first_name or ''} {last_name or ''}".strip()

    elif destination == 'loans':
        # Map from auto-import fields to loans table columns
        field_map = {
            # Loan identifiers
            'file_name': 'loan_number',
            'organization_code': 'organization_code',

            # Borrower info
            'borrower_email': 'borrower_email',
            'borrower_mobile_phone': 'borrower_phone',
            'co_borrower_email': 'co_borrower_email',

            # Property info
            'property_street': 'property_address',
            'property_city': 'property_city',
            'property_state': 'property_state',
            'property_zip': 'property_zip',
            'property_type': 'property_type',
            'occupancy_type': 'occupancy_type',
            'appraised_value': 'appraisal_value',
            'purchase_price': 'purchase_price',

            # Loan details
            'loan_amount': 'amount',
            'interest_rate': 'rate',
            'loan_status': 'stage',
            'loan_purpose': 'loan_purpose',
            'loan_program_name': 'program',
            'loan_program_code': 'loan_program_code',
            'loan_with': 'lender',

            # Financial ratios
            'ltv': 'ltv',
            'cltv': 'cltv',
            'first_ratio': 'first_ratio',
            'second_ratio': 'second_ratio',
            'credit_score': 'credit_score',
            'cash_to_borrower': 'cash_to_borrower',
            'lender_credit': 'lender_credit',

            # Team members
            'loan_officer_name': 'loan_officer_name',
            'loan_processor_name': 'processor',
            'loan_processor_email': 'processor_email',
            'underwriter_name': 'underwriter',
            'closer_name': 'closer',

            # Agents and title
            'listing_agent_name': 'realtor_agent',
            'settlement_company': 'title_company',

            # Key dates
            'date_created': 'created_at',
            'status_date': 'stage_changed_at',
            'scheduled_closing_date': 'scheduled_closing_date',
            'lock_expiration_date': 'lock_expiration_date',
            'funded_date': 'funded_date',

            # SLA date fields
            'le_pending_date': 'le_pending_date',
            'le_initial_delivery_date': 'initial_disclosures_sent_date',
            'le_received_date': 'initial_disclosures_signed_date',
            'file_received_date': 'file_received_date',
            'uw_received_date': 'uw_received_date',
            'original_approved_date': 'loan_approved_date',
            'approved_date': 'loan_approved_date',
            'conditions_for_review_date': 'conditions_for_review_date',
            'suspended_date': 'suspended_date',
            'approved_not_accepted_date': 'approved_not_accepted_date',
            'withdrawn_date': 'withdrawn_date',
            'clear_to_close_date': 'clear_to_close_date',
            'cd_requested_date': 'cd_requested_date',
            'cd_initial_delivery_date': 'cd_sent_to_borrower_date',
            'cd_received_date': 'cd_acknowledged_date',
            'docs_ordered_date': 'docs_ordered_date',
            'docs_out_date': 'docs_out_date',
            'intent_to_proceed_date': 'contract_received_date',

            # Appraisal dates
            'appraisal_ordered_date': 'appraisal_ordered_date',
            'appraisal_received_date': 'appraisal_received_date',

            # Other
            'origination_channel': 'origination_channel',
            'referral_source': 'referral_source',
        }

        for auto_field, db_field in field_map.items():
            if auto_field in row_data and row_data[auto_field] is not None:
                result[db_field] = row_data[auto_field]

        # Combine first and last name for borrower_name
        first_name = row_data.get('borrower_first_name', '')
        last_name = row_data.get('borrower_last_name', '')
        if first_name or last_name:
            result['borrower_name'] = f"{first_name or ''} {last_name or ''}".strip()

    elif destination == 'mum_clients':
        # Map from auto-import fields to mum_clients table columns
        field_map = {
            # Client info - skip name fields, handled separately below
            'borrower_email': 'email',
            'borrower_mobile_phone': 'phone',
            'file_name': 'loan_number',

            # Loan details
            'loan_amount': 'loan_balance',
            'interest_rate': 'current_rate',
            'original_interest_rate': 'original_rate',

            # Property values
            'appraised_value': 'appraisal_value_at_closing',
            'current_value': 'current_property_value',

            # Dates
            'funded_date': 'original_close_date',
            'scheduled_closing_date': 'closing_date',
            'close_date': 'closing_date',

            # Team
            'loan_officer_name': 'loan_officer',
            'loan_officer_email': 'loan_officer_email',
            'loan_processor_name': 'processor',
            'loan_processor_email': 'processor_email',
            'underwriter_name': 'underwriter',
            'closer_name': 'closer',

            # Loan type
            'loan_program_name': 'loan_type',
        }

        for auto_field, db_field in field_map.items():
            if auto_field in row_data and row_data[auto_field] is not None:
                result[db_field] = row_data[auto_field]

        # Enhanced name extraction - try multiple sources
        client_name = None

        # Priority 1: Combine first and last name if both exist
        first_name = row_data.get('borrower_first_name', '') or ''
        last_name = row_data.get('borrower_last_name', '') or ''
        if first_name or last_name:
            client_name = f"{first_name} {last_name}".strip()

        # Priority 2: Use combined borrower_name field
        if not client_name and row_data.get('borrower_name'):
            client_name = str(row_data['borrower_name']).strip()

        # Priority 3: Check for direct name or client_name fields
        if not client_name and row_data.get('name'):
            client_name = str(row_data['name']).strip()
        if not client_name and row_data.get('client_name'):
            client_name = str(row_data['client_name']).strip()

        # Set the client_name if we found one
        if client_name:
            result['client_name'] = client_name
            result['name'] = client_name

    return result


def normalize_stage(stage_value: str, destination: str) -> str:
    """Normalize stage values to match database enums (uppercase for loans)"""
    if not stage_value:
        return 'NEW' if destination == 'leads' else 'PROCESSING'

    stage_lower = str(stage_value).lower().strip()

    if destination == 'leads':
        lead_stage_map = {
            'new': 'NEW',
            'new lead': 'NEW',
            'attempted contact': 'ATTEMPTED_CONTACT',
            'attempted': 'ATTEMPTED_CONTACT',
            'prospect': 'PROSPECT',
            'qualified': 'PROSPECT',
            'application': 'APPLICATION',
            'pre-qualified': 'PRE_QUALIFIED',
            'prequalified': 'PRE_QUALIFIED',
            'pre-approved': 'PRE_APPROVED',
            'preapproved': 'PRE_APPROVED',
            'approved': 'PRE_APPROVED',
            'under contract': 'UNDER_CONTRACT',
            'contract': 'UNDER_CONTRACT',
            'long-term nurture': 'LONG_TERM_NURTURE',
            'nurture': 'LONG_TERM_NURTURE',
            'closed': 'CLOSED',
            'funded': 'CLOSED',
            'withdrawn': 'WITHDRAWN',
            'cancelled': 'WITHDRAWN',
        }
        return lead_stage_map.get(stage_lower, 'NEW')

    elif destination == 'loans':
        # LoanStage enum mappings - all values UPPERCASE to match LoanStage enum
        loan_stage_map = {
            # Application/Pre-disclosure
            'application': 'APPLICATION',
            'app': 'APPLICATION',
            'new application': 'APPLICATION',
            'disclosed': 'DISCLOSED',
            'le sent': 'DISCLOSED',
            'processing': 'PROCESSING',
            'in processing': 'PROCESSING',
            'proc': 'PROCESSING',
            # Submission
            'submitted': 'SUBMITTED',
            'uw submitted': 'SUBMITTED',
            'submit': 'SUBMITTED',
            # Underwriting
            'underwriting': 'UNDERWRITING',
            'uw received': 'UW_RECEIVED',
            'uw': 'UW_RECEIVED',
            'in uw': 'UW_RECEIVED',
            'in underwriting': 'UW_RECEIVED',
            'conditional approval': 'CONDITIONAL_APPROVAL',
            'conditional': 'CONDITIONAL_APPROVAL',
            'cond approval': 'CONDITIONAL_APPROVAL',
            'approved': 'APPROVED',
            'approved with conditions': 'CONDITIONAL_APPROVAL',
            'suspended': 'SUSPENDED',
            'susp': 'SUSPENDED',
            # Clear to Close
            'ctc': 'CTC',
            'clear to close': 'CLEAR_TO_CLOSE',
            'clearto close': 'CLEAR_TO_CLOSE',
            'cleartoclose': 'CLEAR_TO_CLOSE',
            'clear-to-close': 'CLEAR_TO_CLOSE',
            'c.t.c.': 'CTC',
            'c.t.c': 'CTC',
            # Closing & funding
            'closing': 'CLOSING',
            'docs out': 'DOCS_OUT',
            'docs': 'DOCS',
            'documents out': 'DOCS_OUT',
            'funded': 'FUNDED',
            'closed': 'FUNDED',
            'complete': 'FUNDED',
            'settled': 'FUNDED',
            # Inactive
            'cancelled': 'CANCELLED',
            'canceled': 'CANCELLED',
            'denied': 'DENIED',
            'dead': 'DEAD',
            'nurture': 'NURTURE',
            'withdrawn': 'WITHDRAWN',
            'does not qualify': 'DOES_NOT_QUALIFY',
            'dnq': 'DOES_NOT_QUALIFY',
        }
        return loan_stage_map.get(stage_lower, 'PROCESSING')

    return stage_value


@router.post("")
async def auto_import(
    file: UploadFile = File(...),
    use_ai: bool = Form(False),
    table_name: str = Form("loans"),
    current_user: dict = Depends(get_current_user)
):
    """
    Automatically import Excel/CSV file with intelligent field mapping.

    No manual field mapping required - fields are automatically detected and mapped
    using fuzzy matching with 70%+ confidence threshold.
    """
    from sqlalchemy import text

    try:
        # Read and parse file
        content = await file.read()
        filename = file.filename or "upload.csv"

        # Validate file type
        if not filename.endswith(('.csv', '.xlsx', '.xls')):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload Excel (.xlsx, .xls) or CSV file."
            )

        logger.info(f"Processing auto-import for file: {filename}")

        # Parse file to DataFrame
        df = parse_file_to_dataframe(content, filename)

        if df.empty:
            raise HTTPException(status_code=400, detail="Excel file is empty")

        # Get column names
        excel_columns = df.columns.tolist()
        logger.info(f"Found {len(excel_columns)} columns in file")

        # Auto-map fields
        mappings = auto_map_fields(excel_columns)
        logger.info(f"Auto-mapped {len(mappings)} fields")

        if not mappings:
            raise HTTPException(
                status_code=400,
                detail="Could not automatically map any fields. Please check your Excel file format."
            )

        # Convert DataFrame to list of dicts
        excel_data = df.to_dict('records')

        # Transform data using mappings
        transform_result = transform_data(excel_data, mappings)

        if not transform_result['data']:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Failed to transform any data",
                    "details": transform_result.get('errors'),
                    "warnings": transform_result.get('warnings'),
                    "stats": transform_result.get('stats'),
                }
            )

        # Determine destination
        if table_name == 'loans':
            destination = 'loans'
        elif table_name == 'mum_clients':
            destination = 'mum_clients'
        else:
            destination = 'leads'

        # Get database session
        db = SessionLocal()
        valid_columns = get_table_columns(db, destination)

        imported = 0
        failed = 0
        import_errors = []

        try:
            for idx, transformed_row in enumerate(transform_result['data']):
                try:
                    # Remove import_metadata before inserting
                    transformed_row.pop('import_metadata', None)

                    # Map to existing database columns
                    row_data = map_to_existing_columns(transformed_row, destination)

                    # Normalize stage
                    if 'stage' in row_data:
                        row_data['stage'] = normalize_stage(row_data['stage'], destination)

                    # Filter to valid columns only
                    row_data = {k: v for k, v in row_data.items() if k in valid_columns}

                    if not row_data:
                        continue

                    if destination == 'leads':
                        # Ensure required fields
                        if 'name' not in row_data:
                            row_data['name'] = row_data.get('email', f'Lead {idx + 1}')
                        if 'created_at' not in row_data:
                            row_data['created_at'] = datetime.now(timezone.utc)
                        if 'stage' not in row_data:
                            row_data['stage'] = 'NEW'
                        if 'source' not in row_data:
                            row_data['source'] = 'Auto Import'

                        # CRITICAL: Set owner_id for multi-tenancy
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'owner_id' not in row_data:
                            row_data['owner_id'] = user_id

                        # Check for existing by email (case-insensitive)
                        email = row_data.get('email')
                        if email:
                            email_normalized = str(email).strip().lower()
                            result = db.execute(
                                text("SELECT id FROM leads WHERE LOWER(TRIM(email)) = :email"),
                                {"email": email_normalized}
                            )
                            existing = result.fetchone()
                            if existing:
                                logger.info(f"Matched lead email '{mask_email(email_normalized)}' to existing lead ID {existing[0]}")
                                # Update existing - use safe SQL builder
                                update_data = {k: v for k, v in row_data.items() if k not in ['created_at']}
                                update_data['updated_at'] = datetime.now(timezone.utc)
                                update_data['id'] = existing[0]
                                sql, safe_data = build_safe_update_sql('leads', update_data)
                                safe_data['id'] = existing[0]
                                db.execute(text(sql), safe_data)
                                db.commit()
                                imported += 1
                                continue

                        # Insert new - use safe SQL builder
                        sql, safe_data = build_safe_insert_sql('leads', row_data)
                        db.execute(text(sql), safe_data)

                    elif destination == 'loans':
                        # Ensure required fields
                        if 'borrower_name' not in row_data:
                            row_data['borrower_name'] = 'Unknown Borrower'
                        if 'loan_number' not in row_data:
                            row_data['loan_number'] = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
                        if 'created_at' not in row_data:
                            row_data['created_at'] = datetime.now(timezone.utc)
                        if 'stage' not in row_data:
                            row_data['stage'] = 'PROCESSING'
                        if 'amount' not in row_data:
                            row_data['amount'] = 0  # Required field

                        # CRITICAL: Set loan_officer_id for multi-tenancy if not already mapped
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'loan_officer_id' not in row_data:
                            row_data['loan_officer_id'] = user_id

                        # Check for existing by loan_number (case-insensitive, trimmed)
                        loan_number = row_data.get('loan_number')
                        if loan_number:
                            # Normalize the loan number for matching
                            loan_number_normalized = str(loan_number).strip()
                            result = db.execute(
                                text("""
                                    SELECT id FROM loans
                                    WHERE UPPER(TRIM(loan_number)) = UPPER(TRIM(:loan_number))
                                """),
                                {"loan_number": loan_number_normalized}
                            )
                            existing = result.fetchone()

                            # Log matching attempt for debugging
                            if existing:
                                logger.info(f"✅ Matched loan_number '{loan_number_normalized}' to existing loan ID {existing[0]}")
                            else:
                                logger.info(f"ℹ️ No existing loan found for loan_number '{loan_number_normalized}' - will create new")
                            if existing:
                                # Update existing - use safe SQL builder
                                update_data = {k: v for k, v in row_data.items() if k not in ['loan_number', 'created_at']}
                                update_data['updated_at'] = datetime.now(timezone.utc)
                                update_data['id'] = existing[0]
                                sql, safe_data = build_safe_update_sql('loans', update_data)
                                safe_data['id'] = existing[0]
                                db.execute(text(sql), safe_data)
                                db.commit()
                                imported += 1
                                continue

                        # Insert new - use safe SQL builder
                        sql, safe_data = build_safe_insert_sql('loans', row_data)
                        db.execute(text(sql), safe_data)

                    elif destination == 'mum_clients':
                        # Ensure client_name is set from various sources
                        if 'client_name' not in row_data:
                            # Try to get name from various sources in priority order
                            name_sources = [
                                row_data.get('name'),
                                row_data.get('borrower_name'),
                                # Last resort: create from first/last from original transformed data
                                f"{transformed_row.get('borrower_first_name', '')} {transformed_row.get('borrower_last_name', '')}".strip() if transformed_row.get('borrower_first_name') or transformed_row.get('borrower_last_name') else None,
                                transformed_row.get('borrower_name'),
                                transformed_row.get('name'),
                            ]
                            for name_source in name_sources:
                                if name_source and str(name_source).strip():
                                    row_data['client_name'] = str(name_source).strip()
                                    break
                            else:
                                # No name found - use loan number as identifier instead of generic Client N
                                loan_num = row_data.get('loan_number', '')
                                row_data['client_name'] = f'Client (Loan #{loan_num})' if loan_num else f'Client {idx + 1}'
                        # Remove 'name' if it exists since mum_clients uses 'client_name'
                        if 'name' in row_data:
                            row_data.pop('name')

                        # Ensure required NOT NULL fields
                        if 'original_loan_amount' not in row_data:
                            row_data['original_loan_amount'] = row_data.get('loan_balance', row_data.get('amount', 0)) or 0
                        if 'current_loan_amount' not in row_data:
                            row_data['current_loan_amount'] = row_data.get('loan_balance', row_data.get('amount', 0)) or 0
                        if 'interest_rate' not in row_data:
                            row_data['interest_rate'] = row_data.get('current_rate', row_data.get('rate', 0)) or 0
                        if 'appraisal_value_at_closing' not in row_data:
                            lb = row_data.get('loan_balance', row_data.get('amount', 0)) or 0
                            row_data['appraisal_value_at_closing'] = lb * 1.25 if lb else 0
                        if 'current_property_value' not in row_data:
                            lb = row_data.get('loan_balance', row_data.get('amount', 0)) or 0
                            row_data['current_property_value'] = lb * 1.25 if lb else 0
                        if 'closing_date' not in row_data:
                            row_data['closing_date'] = row_data.get('original_close_date', datetime.now(timezone.utc).date())
                        if 'first_payment_date' not in row_data:
                            row_data['first_payment_date'] = row_data.get('closing_date', datetime.now(timezone.utc).date())
                        if 'created_at' not in row_data:
                            row_data['created_at'] = datetime.now(timezone.utc)
                        if 'status' not in row_data:
                            row_data['status'] = 'active'

                        # CRITICAL: Set user_id for multi-tenancy
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'user_id' not in row_data:
                            row_data['user_id'] = user_id

                        # Filter to valid columns
                        row_data = {k: v for k, v in row_data.items() if k in valid_columns}

                        # Check for existing by loan_number (case-insensitive, trimmed)
                        loan_number = row_data.get('loan_number')
                        if loan_number:
                            loan_number_normalized = str(loan_number).strip()
                            result = db.execute(
                                text("""
                                    SELECT id FROM mum_clients
                                    WHERE UPPER(TRIM(loan_number)) = UPPER(TRIM(:ln))
                                """),
                                {"ln": loan_number_normalized}
                            )
                            existing = result.fetchone()
                            if existing:
                                logger.info(f"✅ Matched MUM client loan_number '{loan_number_normalized}' to ID {existing[0]}")
                                # Update existing - use safe SQL builder
                                update_data = {k: v for k, v in row_data.items() if k not in ['created_at', 'loan_number']}
                                update_data['updated_at'] = datetime.now(timezone.utc)
                                if update_data:
                                    update_data['id'] = existing[0]
                                    sql, safe_data = build_safe_update_sql('mum_clients', update_data)
                                    safe_data['id'] = existing[0]
                                    db.execute(text(sql), safe_data)
                                    db.commit()
                                    imported += 1
                                    continue

                        # Insert new - use safe SQL builder
                        sql, safe_data = build_safe_insert_sql('mum_clients', row_data)
                        db.execute(text(sql), safe_data)

                    imported += 1
                    db.commit()

                except Exception as row_error:
                    db.rollback()
                    failed += 1
                    import_errors.append(f"Row {idx + 2}: {str(row_error)}")
                    if len(import_errors) >= 50:
                        import_errors.append("... (additional errors truncated)")
                        break

            # Log import to history (skip if table doesn't exist)
            try:
                if 'import_history' in get_table_columns(db, 'import_history'):
                    user_id = current_user.get('id')
                    if user_id:
                        db.execute(
                            text("""
                                INSERT INTO import_history (
                                    user_id, file_name, file_size, records_imported,
                                    records_total, records_failed, mapping_confidence,
                                    table_name, status, details, created_at
                                ) VALUES (:user_id, :file_name, :file_size, :records_imported,
                                    :records_total, :records_failed, :mapping_confidence,
                                    :table_name, :status, :details, :created_at)
                            """),
                            {
                                "user_id": user_id,
                                "file_name": filename,
                                "file_size": len(content),
                                "records_imported": imported,
                                "records_total": transform_result['stats']['total_rows'],
                                "records_failed": failed,
                                "mapping_confidence": transform_result['stats']['confidence_average'],
                                "table_name": destination,
                                "status": 'completed' if failed == 0 else 'partial',
                                "details": json.dumps({
                                    'mappings': transform_result['mappings'],
                                    'warnings': transform_result.get('warnings'),
                                    'errors': import_errors,
                                }),
                                "created_at": datetime.now(timezone.utc),
                            }
                        )
                        db.commit()
            except Exception as history_error:
                logger.warning(f"Failed to log import history: {history_error}")

        finally:
            db.close()

        # Build response
        response = {
            "success": True,
            "message": f"Successfully imported {imported} of {transform_result['stats']['total_rows']} records",
            "stats": {
                **transform_result['stats'],
                "imported": imported,
                "failed_import": failed,
                "mappingConfidence": f"{transform_result['stats']['confidence_average']}%",
            },
            "mappings": transform_result['mappings'],
            "warnings": transform_result.get('warnings'),
            "errors": import_errors if import_errors else transform_result.get('errors'),
        }

        status_code = 200 if failed == 0 else 207  # 207 = Multi-Status
        return JSONResponse(status_code=status_code, content=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-import error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Import failed"
        )


@router.get("/history")
async def get_import_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get import history for the current user"""
    # Check user_id before creating connection to avoid leak on early return
    user_id = current_user.get('id')
    if not user_id:
        return {"success": True, "imports": []}

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, file_name, file_size, records_imported, records_total,
                   records_failed, mapping_confidence, table_name, status,
                   details, created_at
            FROM import_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))

        columns = ['id', 'file_name', 'file_size', 'records_imported', 'records_total',
                   'records_failed', 'mapping_confidence', 'table_name', 'status',
                   'details', 'created_at']

        imports = []
        for row in cursor.fetchall():
            import_dict = dict(zip(columns, row))
            # Convert datetime to ISO string
            if import_dict.get('created_at'):
                import_dict['created_at'] = import_dict['created_at'].isoformat()
            imports.append(import_dict)

        return {"success": True, "imports": imports}

    except Exception as e:
        logger.error(f"Failed to fetch import history: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch import history"
        )
    finally:
        # CRITICAL: Always close connections to prevent leaks
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close database cursor: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close database connection: {e}")


@router.get("/field-mappings")
async def get_field_mappings(
    current_user: dict = Depends(get_current_user)
):
    """Get all available field mappings"""
    return {
        "success": True,
        "total_fields": len(FIELD_MAPPINGS),
        "fields": [
            {
                "crm_field": f.crm_field,
                "patterns": f.excel_patterns,
                "data_type": f.data_type,
                "required": f.required,
            }
            for f in FIELD_MAPPINGS
        ]
    }


# =============================================================================
# ADMIN: TEST ACCOUNT SEEDING
# =============================================================================

@router.post("/bootstrap/seed-test-account")
async def seed_test_account_bootstrap(
    secret_key: str = Form(...)
):
    """
    Bootstrap endpoint to seed the test account - NO AUTH REQUIRED.
    Only requires the secret key. Use this for initial setup when no users exist.

    curl -X POST https://your-app.railway.app/api/v1/auto-import/bootstrap/seed-test-account \
         -F "secret_key=YOUR_SECRET_KEY"
    """
    import os

    # Verify secret key (remove ALL whitespace as Railway env vars can have embedded newlines)
    import re
    import hmac as _hmac
    expected_key = re.sub(r'\s+', '', os.getenv("SECRET_KEY", ""))
    provided_key = re.sub(r'\s+', '', secret_key)
    if not expected_key or not _hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid secret key"
        )

    try:
        from seed_test_account import seed_test_account

        result = seed_test_account()

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Seeding failed: {result.get('error', 'Unknown error')}"
            )

        return {
            "success": True,
            "message": "Test account seeded successfully",
            "credentials": result.get("credentials"),
            "data_created": result.get("data"),
        }

    except ImportError as e:
        logger.error(f"Failed to import seed_test_account: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to import seeding module"
        )
    except Exception as e:
        logger.error(f"Error seeding test account: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error seeding test account"
        )


@router.post("/admin/seed-test-account")
async def seed_test_account_endpoint(
    secret_key: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Admin endpoint to seed the test account with comprehensive demo data.

    Requires a secret key for additional protection. The key should match
    the SECRET_KEY environment variable.

    Creates:
    - Test user account (testuser@perenniaai.com / TestAccount2026!)
    - 13 leads across various stages
    - 10 pipeline loans
    - 8 MUM clients
    - 8 referral partners
    - 15+ tasks
    - Activities, calendar events, documents
    - SMS/email messages, call logs
    - Stage history, goals, notifications
    """
    import os

    # Verify secret key (remove ALL whitespace as Railway env vars can have embedded newlines)
    import re
    import hmac as _hmac
    expected_key = re.sub(r'\s+', '', os.getenv("SECRET_KEY", ""))
    provided_key = re.sub(r'\s+', '', secret_key)
    if not expected_key or not _hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid secret key"
        )

    # Verify user is admin
    user_email = current_user.get("email", "")
    user_role = current_user.get("role", "")
    if user_role not in ["site_admin", "admin"] and not user_email.endswith("@perenniaai.com"):
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    try:
        # Import and run the seed function
        from seed_test_account import seed_test_account

        result = seed_test_account()

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Seeding failed: {result.get('error', 'Unknown error')}"
            )

        return {
            "success": True,
            "message": "Test account seeded successfully",
            "credentials": result.get("credentials"),
            "data_created": result.get("data"),
        }

    except ImportError as e:
        logger.error(f"Failed to import seed_test_account: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to import seeding module"
        )
    except Exception as e:
        logger.error(f"Error seeding test account: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error seeding test account"
        )
