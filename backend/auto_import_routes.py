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
    from main import get_current_user, get_db_connection
except ImportError:
    # Fallback for standalone testing
    async def get_current_user():
        return {"email": "admin@perenniaai.com", "id": str(uuid.uuid4())}

    def get_db_connection():
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


def get_table_columns(conn, table_name: str) -> set:
    """Get valid column names for a database table"""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.warning(f"Error getting columns for {table_name}: {e}")
        return set()
    finally:
        cursor.close()


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
            'file_name': 'loan_number',
            'borrower_first_name': 'borrower_first_name',
            'borrower_last_name': 'borrower_last_name',
            'borrower_email': 'borrower_email',
            'borrower_mobile_phone': 'borrower_phone',
            'property_street': 'property_address',
            'property_city': 'property_city',
            'property_state': 'property_state',
            'property_zip': 'property_zip',
            'loan_amount': 'amount',
            'interest_rate': 'rate',
            'loan_status': 'stage',
            'loan_purpose': 'loan_type',
            'loan_program_name': 'program',
            'loan_officer_name': 'loan_officer_name',
            'loan_processor_name': 'processor',
            'underwriter_name': 'underwriter',
            'credit_score': 'credit_score',
            'ltv': 'ltv',
            'scheduled_closing_date': 'closing_date',
            'lock_expiration_date': 'lock_expiration_date',
            'funded_date': 'funded_date',
            'appraised_value': 'appraisal_value',
            'purchase_price': 'purchase_price',
            'listing_agent_name': 'realtor_agent',
            'settlement_company': 'title_company',
        }

        for auto_field, db_field in field_map.items():
            if auto_field in row_data and row_data[auto_field] is not None:
                result[db_field] = row_data[auto_field]

        # Combine first and last name for borrower_name
        first_name = row_data.get('borrower_first_name', '')
        last_name = row_data.get('borrower_last_name', '')
        if first_name or last_name:
            result['borrower_name'] = f"{first_name or ''} {last_name or ''}".strip()

    return result


def normalize_stage(stage_value: str, destination: str) -> str:
    """Normalize stage values to match database enums"""
    if not stage_value:
        return 'NEW' if destination == 'leads' else 'Processing'

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
        loan_stage_map = {
            'disclosed': 'Disclosed',
            'processing': 'Processing',
            'submitted': 'Submitted',
            'underwriting': 'UW Received',
            'approved': 'Approved',
            'clear to close': 'CTC',
            'ctc': 'CTC',
            'docs out': 'Docs Out',
            'funded': 'Funded',
            'closed': 'Funded',
        }
        return loan_stage_map.get(stage_lower, 'Processing')

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
        destination = 'loans' if table_name == 'loans' else 'leads'

        # Get database connection
        conn = get_db_connection()
        valid_columns = get_table_columns(conn, destination)

        cursor = conn.cursor()
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

                        # Check for existing by email
                        email = row_data.get('email')
                        if email:
                            cursor.execute(
                                "SELECT id FROM leads WHERE LOWER(email) = LOWER(%s)",
                                (email,)
                            )
                            existing = cursor.fetchone()
                            if existing:
                                # Update existing
                                update_cols = [f"{k} = %s" for k in row_data.keys() if k not in ['created_at']]
                                update_vals = [v for k, v in row_data.items() if k not in ['created_at']]
                                update_vals.append(existing[0])
                                cursor.execute(
                                    f"UPDATE leads SET {', '.join(update_cols)}, updated_at = NOW() WHERE id = %s",
                                    update_vals
                                )
                                imported += 1
                                conn.commit()
                                continue

                        # Insert new
                        columns = list(row_data.keys())
                        values = list(row_data.values())
                        placeholders = ', '.join(['%s'] * len(columns))
                        cursor.execute(
                            f"INSERT INTO leads ({', '.join(columns)}) VALUES ({placeholders})",
                            values
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
                            row_data['stage'] = 'Processing'

                        # Check for existing by loan_number
                        loan_number = row_data.get('loan_number')
                        if loan_number:
                            cursor.execute(
                                "SELECT id FROM loans WHERE loan_number = %s",
                                (loan_number,)
                            )
                            existing = cursor.fetchone()
                            if existing:
                                # Update existing
                                update_cols = [f"{k} = %s" for k in row_data.keys() if k not in ['loan_number', 'created_at']]
                                update_vals = [v for k, v in row_data.items() if k not in ['loan_number', 'created_at']]
                                update_vals.append(existing[0])
                                cursor.execute(
                                    f"UPDATE loans SET {', '.join(update_cols)}, updated_at = NOW() WHERE id = %s",
                                    update_vals
                                )
                                imported += 1
                                conn.commit()
                                continue

                        # Insert new
                        columns = list(row_data.keys())
                        values = list(row_data.values())
                        placeholders = ', '.join(['%s'] * len(columns))
                        cursor.execute(
                            f"INSERT INTO loans ({', '.join(columns)}) VALUES ({placeholders})",
                            values
                        )

                    imported += 1
                    conn.commit()

                except Exception as row_error:
                    conn.rollback()
                    failed += 1
                    import_errors.append(f"Row {idx + 2}: {str(row_error)}")
                    if len(import_errors) >= 50:
                        import_errors.append("... (additional errors truncated)")
                        break

            # Log import to history
            try:
                user_id = current_user.get('id')
                if user_id:
                    cursor.execute("""
                        INSERT INTO import_history (
                            user_id, file_name, file_size, records_imported,
                            records_total, records_failed, mapping_confidence,
                            table_name, status, details, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        user_id,
                        filename,
                        len(content),
                        imported,
                        transform_result['stats']['total_rows'],
                        failed,
                        transform_result['stats']['confidence_average'],
                        destination,
                        'completed' if failed == 0 else 'partial',
                        json.dumps({
                            'mappings': transform_result['mappings'],
                            'warnings': transform_result.get('warnings'),
                            'errors': import_errors,
                        })
                    ))
                    conn.commit()
            except Exception as history_error:
                logger.warning(f"Failed to log import history: {history_error}")

        finally:
            cursor.close()
            conn.close()

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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        user_id = current_user.get('id')
        if not user_id:
            return {"success": True, "imports": []}

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

        cursor.close()
        conn.close()

        return {"success": True, "imports": imports}

    except Exception as e:
        logger.error(f"Failed to fetch import history: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch import history: {str(e)}"
        )


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
