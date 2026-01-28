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
from datetime import datetime
import logging
import os

from field_mapping_service import (
    auto_map_fields,
    transform_data,
    MappingResult,
    FIELD_MAPPINGS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auto-import", tags=["Auto Import"])

# Import dependencies from main app
try:
    from main import get_current_user, get_db, SessionLocal
except ImportError:
    # Fallback: import from database module directly
    try:
        from database import get_db, SessionLocal
    except ImportError:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        _fallback_engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db"))
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_fallback_engine)

        def get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

    async def get_current_user():
        return {"email": "admin@perenniaai.com", "id": str(uuid.uuid4())}


def get_db_connection():
    """Get a raw psycopg2 database connection for history queries."""
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
                            row_data['created_at'] = datetime.utcnow()
                        if 'stage' not in row_data:
                            row_data['stage'] = 'NEW'
                        if 'source' not in row_data:
                            row_data['source'] = 'Auto Import'

                        # CRITICAL: Set owner_id for multi-tenancy
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'owner_id' not in row_data:
                            row_data['owner_id'] = user_id

                        # Check for existing by email
                        email = row_data.get('email')
                        if email:
                            result = db.execute(
                                text("SELECT id FROM leads WHERE LOWER(email) = LOWER(:email)"),
                                {"email": email}
                            )
                            existing = result.fetchone()
                            if existing:
                                # Update existing
                                update_data = {k: v for k, v in row_data.items() if k not in ['created_at']}
                                update_data['updated_at'] = datetime.utcnow()
                                set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
                                update_data['id'] = existing[0]
                                db.execute(
                                    text(f"UPDATE leads SET {set_clause} WHERE id = :id"),
                                    update_data
                                )
                                db.commit()
                                imported += 1
                                continue

                        # Insert new
                        columns = list(row_data.keys())
                        placeholders = ', '.join([f":{k}" for k in columns])
                        db.execute(
                            text(f"INSERT INTO leads ({', '.join(columns)}) VALUES ({placeholders})"),
                            row_data
                        )

                    elif destination == 'loans':
                        # Ensure required fields
                        if 'borrower_name' not in row_data:
                            row_data['borrower_name'] = 'Unknown Borrower'
                        if 'loan_number' not in row_data:
                            row_data['loan_number'] = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
                        if 'created_at' not in row_data:
                            row_data['created_at'] = datetime.utcnow()
                        if 'stage' not in row_data:
                            row_data['stage'] = 'PROCESSING'
                        if 'amount' not in row_data:
                            row_data['amount'] = 0  # Required field

                        # CRITICAL: Set loan_officer_id for multi-tenancy if not already mapped
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'loan_officer_id' not in row_data:
                            row_data['loan_officer_id'] = user_id

                        # Check for existing by loan_number
                        loan_number = row_data.get('loan_number')
                        if loan_number:
                            result = db.execute(
                                text("SELECT id FROM loans WHERE loan_number = :loan_number"),
                                {"loan_number": loan_number}
                            )
                            existing = result.fetchone()
                            if existing:
                                # Update existing
                                update_data = {k: v for k, v in row_data.items() if k not in ['loan_number', 'created_at']}
                                update_data['updated_at'] = datetime.utcnow()
                                set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
                                update_data['id'] = existing[0]
                                db.execute(
                                    text(f"UPDATE loans SET {set_clause} WHERE id = :id"),
                                    update_data
                                )
                                db.commit()
                                imported += 1
                                continue

                        # Insert new
                        columns = list(row_data.keys())
                        placeholders = ', '.join([f":{k}" for k in columns])
                        db.execute(
                            text(f"INSERT INTO loans ({', '.join(columns)}) VALUES ({placeholders})"),
                            row_data
                        )

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
                            row_data['closing_date'] = row_data.get('original_close_date', datetime.utcnow().date())
                        if 'first_payment_date' not in row_data:
                            row_data['first_payment_date'] = row_data.get('closing_date', datetime.utcnow().date())
                        if 'created_at' not in row_data:
                            row_data['created_at'] = datetime.utcnow()
                        if 'status' not in row_data:
                            row_data['status'] = 'active'

                        # CRITICAL: Set user_id for multi-tenancy
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'user_id' not in row_data:
                            row_data['user_id'] = user_id

                        # Filter to valid columns
                        row_data = {k: v for k, v in row_data.items() if k in valid_columns}

                        # Check for existing by loan_number
                        loan_number = row_data.get('loan_number')
                        if loan_number:
                            result = db.execute(
                                text("SELECT id FROM mum_clients WHERE loan_number = :ln"),
                                {"ln": loan_number}
                            )
                            existing = result.fetchone()
                            if existing:
                                # Update existing
                                update_data = {k: v for k, v in row_data.items() if k not in ['created_at', 'loan_number']}
                                update_data['updated_at'] = datetime.utcnow()
                                if update_data:
                                    set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
                                    update_data['id'] = existing[0]
                                    db.execute(
                                        text(f"UPDATE mum_clients SET {set_clause} WHERE id = :id"),
                                        update_data
                                    )
                                    db.commit()
                                    imported += 1
                                    continue

                        # Insert new
                        columns = list(row_data.keys())
                        placeholders = ', '.join([f":{k}" for k in columns])
                        db.execute(
                            text(f"INSERT INTO mum_clients ({', '.join(columns)}) VALUES ({placeholders})"),
                            row_data
                        )

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
                                "created_at": datetime.utcnow(),
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
            detail=f"Import failed: {str(e)}"
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
            detail=f"Failed to fetch import history: {str(e)}"
        )
    finally:
        # CRITICAL: Always close connections to prevent leaks
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
