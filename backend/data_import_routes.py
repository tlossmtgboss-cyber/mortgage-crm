"""
Data Import Routes - CSV/Excel file upload and import functionality
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional
import pandas as pd
import io
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-import", tags=["Data Import"])

# Import dependencies from main app
try:
    from main import get_current_user, get_db_connection
except ImportError:
    # Fallback for standalone testing
    async def get_current_user():
        return {"email": "demo@example.com"}

    def get_db_connection():
        import psycopg2
        import os
        return psycopg2.connect(os.getenv("DATABASE_URL"))


def detect_header_row(file_content: bytes, filename: str) -> int:
    """
    Detect the actual header row in an Excel/CSV file.
    Some files have title/summary rows before the actual headers.
    Returns the row index (0-based) where headers are located.
    """
    try:
        # Read first 10 rows without header assumption
        if filename.endswith('.csv'):
            df_preview = pd.read_csv(io.BytesIO(file_content), header=None, nrows=10)
        else:
            df_preview = pd.read_excel(io.BytesIO(file_content), header=None, nrows=10)

        # Look for the row that most likely contains headers
        # Headers typically have: multiple non-empty cells, text values, unique values
        best_header_row = 0
        best_score = 0

        for idx, row in df_preview.iterrows():
            score = 0
            non_empty = 0
            unique_values = set()

            for val in row:
                if pd.notna(val) and str(val).strip():
                    non_empty += 1
                    val_str = str(val).strip().lower()
                    unique_values.add(val_str)

                    # Bonus points for common header keywords
                    header_keywords = [
                        'name', 'date', 'email', 'phone', 'address', 'loan', 'number',
                        'status', 'stage', 'amount', 'rate', 'type', 'code', 'id',
                        'borrower', 'property', 'city', 'state', 'zip', 'officer',
                        'processor', 'first', 'last', 'street', 'created', 'full'
                    ]
                    if any(kw in val_str for kw in header_keywords):
                        score += 2

                    # Penalty for very long text (likely a title/description row)
                    if len(val_str) > 50:
                        score -= 3

            # Score based on number of non-empty unique values
            score += non_empty
            score += len(unique_values) * 0.5

            # Penalty if most cells are empty (sparse row)
            if non_empty < len(row) * 0.3:
                score -= 5

            if score > best_score:
                best_score = score
                best_header_row = idx

        return best_header_row
    except Exception as e:
        logger.warning(f"Error detecting header row: {e}, defaulting to row 0")
        return 0


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean up column names by:
    - Replacing 'Unnamed: X' with better names based on position
    - Stripping whitespace
    - Handling duplicate column names
    """
    new_columns = []
    seen_names = {}

    for idx, col in enumerate(df.columns):
        col_str = str(col).strip()

        # Check if this is an unnamed column
        if col_str.startswith('Unnamed:') or not col_str:
            # Try to use the first non-empty value in that column as the header
            for row_idx in range(min(5, len(df))):
                cell_val = df.iloc[row_idx, idx]
                if pd.notna(cell_val) and str(cell_val).strip():
                    col_str = str(cell_val).strip()
                    break
            else:
                col_str = f"Column_{idx + 1}"

        # Handle duplicates
        if col_str in seen_names:
            seen_names[col_str] += 1
            col_str = f"{col_str}_{seen_names[col_str]}"
        else:
            seen_names[col_str] = 0

        new_columns.append(col_str)

    df.columns = new_columns
    return df


def parse_excel_or_csv(file_content: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or Excel file into DataFrame with smart header detection"""
    try:
        # First, detect where the actual header row is
        header_row = detect_header_row(file_content, filename)
        logger.info(f"Detected header row at index: {header_row}")

        if filename.endswith('.csv'):
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(
                        io.BytesIO(file_content),
                        encoding=encoding,
                        header=header_row,
                        skiprows=range(header_row) if header_row > 0 else None
                    )
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode CSV file with any common encoding")
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(
                io.BytesIO(file_content),
                header=header_row
            )
        else:
            raise ValueError(f"Unsupported file format: {filename}")

        # Clean up column names (handle any remaining 'Unnamed' columns)
        df = clean_column_names(df)

        # Remove any completely empty rows at the start (remnants of title rows)
        df = df.dropna(how='all').reset_index(drop=True)

        return df
    except Exception as e:
        logger.error(f"Error parsing file {filename}: {e}")
        raise ValueError(f"Error parsing file: {str(e)}")


def suggest_column_mappings(headers: list) -> dict:
    """AI-like column mapping suggestions based on header names"""
    mappings = {}

    # Column name patterns that map to ACTUAL database columns
    # These patterns map CSV headers to real columns in leads/loans tables
    patterns = {
        # === BORROWER/CONTACT INFO (leads: name/email/phone, loans: borrower_*) ===
        'name': ['borrower', 'borrower name', 'borrowername', 'client', 'client name', 'name', 'full name', 'borrower_name'],
        'first_name': ['first name', 'firstname', 'first', 'fname', 'given name', 'bor 1 first name', 'bor first name', 'borrower first name', 'borrower 1 first name'],
        'last_name': ['last name', 'lastname', 'last', 'lname', 'surname', 'family name', 'bor 1 last name', 'bor last name', 'borrower last name', 'borrower 1 last name'],
        'email': ['borrower email', 'email', 'e-mail', 'email address', 'emailaddress', 'client email', 'borrower_email'],
        'phone': ['borrower phone', 'phone', 'telephone', 'tel', 'mobile', 'cell', 'phone number', 'borrower_phone'],

        # === CO-APPLICANT (leads table columns) ===
        'co_applicant_name': ['co-borrower', 'coborrower', 'co borrower', 'co-borrower name', 'coborrower name', 'co-applicant', 'co applicant name'],
        'co_applicant_email': ['co-borrower email', 'coborrower email', 'co borrower email', 'co-applicant email', 'co applicant email'],
        'co_applicant_phone': ['co-borrower phone', 'coborrower phone', 'co borrower phone', 'co-applicant phone'],
        'preferred_communication': ['preferred communication', 'contact preference', 'communication preference'],

        # === LOAN IDENTIFIERS ===
        'loan_number': ['loan number', 'loannumber', 'loan #', 'loan id', 'loanid', 'file number', 'file #', 'file id', 'file name', 'filename'],
        'stage': ['stage', 'status', 'loan stage', 'loan status', 'pipeline stage'],

        # === LOAN DETAILS ===
        'loan_amount': ['loan amount', 'loanamount', 'amount', 'principal', 'loan value', 'base loan amount'],
        'interest_rate': ['rate', 'interest rate', 'interestrate', 'int rate', 'note rate', 'interest'],
        'loan_term': ['term', 'loan term', 'months', 'term months', 'loan term months'],
        'program': ['program', 'loan program', 'product name'],
        'loan_type': ['loan type', 'loantype', 'type', 'product', 'product type'],
        'down_payment': ['down payment', 'downpayment', 'down', 'cash to close'],
        'lender': ['lender', 'investor', 'bank', 'lending institution'],
        'preapproval_amount': ['preapproval amount', 'preapproval', 'pre-approval amount'],

        # === PROPERTY INFO (leads uses: address/city/state/zip_code) ===
        # Note: transform_columns_for_destination will convert property_* to leads columns
        'address': ['property address', 'address', 'street', 'street address', 'subject property', 'sub prop street', 'subject property street', 'prop street', 'property street'],
        'city': ['property city', 'city', 'town', 'sub prop city', 'subject property city'],
        'state': ['property state', 'state', 'province', 'st', 'sub prop state', 'subject property state', 'prop state'],
        'zip_code': ['property zip', 'zip', 'zipcode', 'zip code', 'postal', 'postal code', 'sub prop zip', 'subject property zip'],
        'property_type': ['property type', 'prop type', 'dwelling type'],
        'property_value': ['property value', 'home value', 'estimated value'],
        'appraisal_value': ['appraisal value', 'appraised value', 'appraisal'],

        # === TEAM MEMBERS (leads table columns) ===
        'loan_officer': ['loan officer', 'lo', 'lo name', 'loan officer name', 'originator', 'lo full name', 'loan officer full name'],
        'processor': ['processor', 'loan processor', 'processor name', 'lp', 'lp name', 'lp full name', 'loan processor full name'],
        'underwriter': ['underwriter', 'uw', 'underwriter name'],
        # Note: realtor_agent, title_company, closer are NOT in leads table - skip them

        # === IMPORTANT DATES ===
        'created_at': ['date created', 'created date', 'creation date', 'created at', 'date added'],
        'status_date': ['status date', 'status changed', 'last status date', 'stage date'],
        'closing_date': ['closing date', 'closingdate', 'close date', 'settlement date', 'closing'],
        'lock_date': ['lock date', 'rate lock date', 'locked date'],
        'lock_expiration': ['lock expiration', 'lock exp', 'lock expiration date', 'rate lock expiration'],

        # === FINANCIAL INFO ===
        'credit_score': ['credit score', 'creditscore', 'fico', 'fico score'],
        'annual_income': ['income', 'annual income', 'yearly income', 'salary', 'gross income'],
        'monthly_debts': ['monthly debts', 'debts', 'monthly obligations'],
        'debt_to_income': ['dti', 'debt to income', 'debt-to-income'],
        'dti': ['dti ratio', 'backend dti'],
        'ltv': ['ltv', 'loan to value', 'loan-to-value'],
        'cltv': ['cltv', 'combined ltv', 'combined loan to value'],
        'apr': ['apr', 'annual percentage rate'],
        'points': ['points', 'discount points', 'loan points'],

        # === OTHER LEAD FIELDS ===
        'source': ['source', 'lead source', 'referral source', 'how did you hear'],
        'employment_status': ['employment', 'employment status', 'job status', 'employed'],
        'employer_name': ['employer', 'employer name', 'company', 'company name'],
        'industry': ['industry', 'sector', 'business type'],
        'first_time_buyer': ['first time buyer', 'ftb', 'first time homebuyer'],
        'notes': ['notes', 'comments', 'remarks', 'additional notes'],
        'organization_code': ['organization code', 'org code', 'branch code', 'branch', 'branch id'],
    }

    for header in headers:
        header_lower = header.lower().strip()
        for field, patterns_list in patterns.items():
            if header_lower in patterns_list or any(p in header_lower for p in patterns_list):
                mappings[header] = field
                break

    return mappings


def detect_data_type(headers: list, sample_rows: list) -> str:
    """Detect whether data is leads, loans, or portfolio based on content"""
    headers_lower = [h.lower() for h in headers]

    # Check for loan-specific fields
    loan_indicators = ['loan number', 'loan #', 'loannumber', 'closing date', 'underwriter', 'processor']
    if any(indicator in ' '.join(headers_lower) for indicator in loan_indicators):
        return 'loans'

    # Check for portfolio-specific fields
    portfolio_indicators = ['current balance', 'upb', 'maturity date', 'payment status', 'last payment']
    if any(indicator in ' '.join(headers_lower) for indicator in portfolio_indicators):
        return 'portfolio'

    # Default to leads
    return 'leads'


@router.post("/analyze")
async def analyze_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze uploaded CSV/Excel file and return preview with AI questions
    """
    try:
        # Read file content
        content = await file.read()
        filename = file.filename or "upload.csv"

        # Parse file
        df = parse_excel_or_csv(content, filename)

        # Get headers and rows
        headers = df.columns.tolist()
        rows = df.fillna('').astype(str).values.tolist()

        # Detect data type
        detected_type = detect_data_type(headers, rows[:5] if rows else [])

        # Suggest column mappings
        suggested_mappings = suggest_column_mappings(headers)

        # Generate AI questions
        questions = [
            {
                "id": "destination",
                "question": "Where should this data be imported?",
                "type": "choice",
                "options": [
                    {
                        "value": "leads",
                        "label": "Leads",
                        "description": "New prospects and potential clients",
                        "icon": "👥"
                    },
                    {
                        "value": "loans",
                        "label": "Active Loans",
                        "description": "Loans currently in pipeline",
                        "icon": "📋"
                    },
                    {
                        "value": "portfolio",
                        "label": "Portfolio",
                        "description": "Closed/funded loans for servicing",
                        "icon": "💼"
                    }
                ]
            },
            {
                "id": "duplicate_handling",
                "question": "How should we handle duplicate records?",
                "type": "choice",
                "options": [
                    {
                        "value": "skip",
                        "label": "Skip Duplicates",
                        "description": "Don't import if record already exists",
                        "icon": "⏭️"
                    },
                    {
                        "value": "update",
                        "label": "Update Existing",
                        "description": "Update existing records with new data",
                        "icon": "🔄"
                    },
                    {
                        "value": "create_new",
                        "label": "Create New",
                        "description": "Always create new records",
                        "icon": "➕"
                    }
                ]
            }
        ]

        return {
            "preview": {
                "headers": headers,
                "rows": rows[:10],  # First 10 rows for preview
                "total_rows": len(rows)
            },
            "detected_type": detected_type,
            "suggested_mappings": suggested_mappings,
            "questions": questions
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing file: {str(e)}")


def normalize_stage_value(stage_value: str, destination: str) -> str:
    """
    Normalize stage values to match database enum values.
    Handles common variations in how stages are written in CSV files.
    """
    if not stage_value or not isinstance(stage_value, str):
        return stage_value

    stage_lower = stage_value.strip().lower()

    if destination == 'leads':
        # LeadStage enum mappings - normalize to exact enum values
        lead_stage_map = {
            # New
            'new': 'New',
            'new lead': 'New',
            # Attempted Contact
            'attempted contact': 'Attempted Contact',
            'attempted': 'Attempted Contact',
            'contact attempted': 'Attempted Contact',
            # Prospect
            'prospect': 'Prospect',
            'qualified': 'Prospect',
            # Application
            'application': 'Application',
            'application started': 'Application',
            'app started': 'Application',
            'in application': 'Application',
            # Pre-Qualified
            'pre-qualified': 'Pre-Qualified',
            'pre qualified': 'Pre-Qualified',
            'prequalified': 'Pre-Qualified',
            'prequal': 'Pre-Qualified',
            # Pre-Approved
            'pre-approved': 'Pre-Approved',
            'pre approved': 'Pre-Approved',
            'preapproved': 'Pre-Approved',
            'preapproval': 'Pre-Approved',
            # Under Contract
            'under contract': 'Under Contract',
            'contract': 'Under Contract',
            'in contract': 'Under Contract',
            # Long-Term Nurture
            'long-term nurture': 'Long-Term Nurture',
            'long term nurture': 'Long-Term Nurture',
            'nurture': 'Long-Term Nurture',
            'long term': 'Long-Term Nurture',
            # Closed
            'closed': 'Closed',
            'funded': 'Closed',
            'closed won': 'Closed',
            # AMR
            'amr': 'AMR',
            'annual mortgage review': 'AMR',
            # Referral Source
            'referral source': 'Referral Source',
            'referral': 'Referral Source',
            # Withdrawn
            'withdrawn': 'Withdrawn',
            'cancelled': 'Withdrawn',
            'canceled': 'Withdrawn',
            # Does Not Qualify
            'does not qualify': 'Does Not Qualify',
            'dnq': 'Does Not Qualify',
            'not qualified': 'Does Not Qualify',
            'disqualified': 'Does Not Qualify',
        }
        return lead_stage_map.get(stage_lower, stage_value)

    elif destination == 'loans':
        # LoanStage enum mappings
        loan_stage_map = {
            'disclosed': 'Disclosed',
            'processing': 'Processing',
            'in processing': 'Processing',
            'submitted': 'Submitted',
            'uw submitted': 'Submitted',
            'uw received': 'UW Received',
            'underwriting': 'UW Received',
            'approved': 'Approved',
            'clear to close': 'CTC',
            'ctc': 'CTC',
            'suspended': 'Suspended',
            'docs out': 'Docs Out',
            'docs': 'Docs Out',
            'funded': 'Funded',
            'closed': 'Funded',
        }
        return loan_stage_map.get(stage_lower, stage_value)

    return stage_value


def transform_columns_for_destination(row_dict: dict, destination: str) -> dict:
    """
    Transform column names based on destination table.
    - For leads: use 'name', 'email', 'phone', 'loan_officer'
    - For loans: use 'borrower_name', 'borrower_email', 'borrower_phone', 'loan_officer_name'

    Also combines first_name + last_name into the appropriate name field.
    Also normalizes stage values to match database enums.
    """
    result = row_dict.copy()

    # Normalize stage value if present
    if 'stage' in result and result['stage']:
        result['stage'] = normalize_stage_value(result['stage'], destination)

    # First, combine first_name + last_name if they exist
    first_name = result.pop('first_name', None) or ''
    last_name = result.pop('last_name', None) or ''

    if first_name or last_name:
        combined_name = f"{first_name} {last_name}".strip()
        if destination == 'leads' and 'name' not in result:
            result['name'] = combined_name
        elif destination == 'loans' and 'borrower_name' not in result:
            result['borrower_name'] = combined_name

    if destination == 'leads':
        # Transform loan-style columns to lead-style columns
        # Note: leads table uses 'state', 'city', 'address', 'zip_code' - NOT 'property_*' columns
        column_transforms = {
            'borrower_name': 'name',
            'borrower_email': 'email',
            'borrower_phone': 'phone',
            'loan_officer_name': 'loan_officer',  # leads uses 'loan_officer', not 'loan_officer_name'
            'property_state': 'state',  # leads table uses 'state' not 'property_state'
            'property_city': 'city',    # leads table uses 'city' not 'property_city'
            'property_zip': 'zip_code', # leads table uses 'zip_code' not 'property_zip'
            'property_address': 'address',  # leads table uses 'address' not 'property_address'
        }
        for old_col, new_col in column_transforms.items():
            if old_col in result and new_col not in result:
                result[new_col] = result.pop(old_col)
            elif old_col in result and new_col in result:
                # Both exist, prefer the transformed one and remove old
                result.pop(old_col)

    elif destination == 'loans':
        # Transform lead-style columns to loan-style columns
        column_transforms = {
            'name': 'borrower_name',
            'email': 'borrower_email',
            'phone': 'borrower_phone',
            'loan_officer': 'loan_officer_name',  # loans uses 'loan_officer_name'
        }
        for old_col, new_col in column_transforms.items():
            if old_col in result and new_col not in result:
                result[new_col] = result.pop(old_col)
            elif old_col in result and new_col in result:
                # Both exist, prefer the transformed one and remove old
                result.pop(old_col)

    return result


def get_table_columns(conn, table_name: str) -> set:
    """Get the set of valid column names for a table"""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))
        columns = {row[0] for row in cursor.fetchall()}
        return columns
    except Exception as e:
        logger.warning(f"Error getting columns for {table_name}: {e}")
        return set()
    finally:
        cursor.close()


def filter_valid_columns(row_dict: dict, valid_columns: set) -> dict:
    """Filter row_dict to only include columns that exist in the table"""
    return {k: v for k, v in row_dict.items() if k in valid_columns}


def ensure_import_columns_exist(conn, destination: str):
    """Ensure all import columns exist in the target table"""
    cursor = conn.cursor()

    if destination == 'leads':
        columns_to_add = [
            ("first_name", "VARCHAR"),
            ("last_name", "VARCHAR"),
            ("organization_code", "VARCHAR"),
            ("cltv", "FLOAT"),
            ("dti_front", "FLOAT"),
            ("dti_back", "FLOAT"),
            ("program", "VARCHAR"),
            ("status_date", "TIMESTAMP"),
        ]
        table_name = "leads"
    else:
        return  # Only leads need this for now

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            conn.commit()
        except Exception:
            conn.rollback()

    cursor.close()


@router.post("/execute")
async def execute_import(
    file: UploadFile = File(...),
    answers: str = Form(...),
    mappings: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Execute the data import based on user answers and column mappings
    """
    try:
        # Parse JSON strings
        answers_dict = json.loads(answers)
        mappings_dict = json.loads(mappings)

        # Read file content
        content = await file.read()
        filename = file.filename or "upload.csv"

        # Parse file
        df = parse_excel_or_csv(content, filename)

        # Get destination
        destination = answers_dict.get('destination', 'leads')
        duplicate_handling = answers_dict.get('duplicate_handling', 'skip')

        # Filter out empty mappings and apply column renaming
        valid_mappings = {k: v for k, v in mappings_dict.items() if v}

        # Select and rename columns
        columns_to_use = list(valid_mappings.keys())
        df_mapped = df[columns_to_use].rename(columns=valid_mappings)

        # Get database connection
        conn = get_db_connection()

        # Ensure all import columns exist in target table
        ensure_import_columns_exist(conn, destination)

        # Get valid columns for the target table to filter out unmapped columns
        table_name = destination if destination != 'portfolio' else 'portfolio_loans'
        valid_columns = get_table_columns(conn, table_name)
        logger.info(f"Valid columns for {table_name}: {len(valid_columns)} columns found")

        cursor = conn.cursor()

        imported = 0
        failed = 0
        skipped_columns = set()  # Track columns that were skipped
        errors = []

        try:
            for idx, row in df_mapped.iterrows():
                try:
                    row_dict = row.to_dict()
                    # Clean up NaN values
                    row_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}

                    # Transform column names based on destination table
                    row_dict = transform_columns_for_destination(row_dict, destination)

                    # Filter to only valid columns that exist in the target table
                    invalid_cols = set(row_dict.keys()) - valid_columns
                    if invalid_cols:
                        skipped_columns.update(invalid_cols)
                    row_dict = filter_valid_columns(row_dict, valid_columns)

                    if destination == 'leads':
                        # Import as lead
                        # Build the insert statement dynamically
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        # Ensure 'name' exists (transform_columns_for_destination handles first_name/last_name combo)
                        if 'name' not in columns:
                            # Use email or loan_number as fallback for name
                            fallback_name = row_dict.get('email') or row_dict.get('loan_number') or 'Unknown Lead'
                            columns.append('name')
                            values.append(fallback_name)

                        # Add required fields if missing
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.utcnow())
                        if 'stage' not in columns:
                            columns.append('stage')
                            values.append('new')
                        if 'source' not in columns:
                            columns.append('source')
                            values.append('Data Import')

                        # Create placeholders
                        placeholders = ', '.join(['%s'] * len(columns))
                        columns_str = ', '.join(columns)

                        cursor.execute(
                            f"INSERT INTO leads ({columns_str}) VALUES ({placeholders})",
                            values
                        )
                        imported += 1

                    elif destination == 'loans':
                        # Import as loan
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        # Ensure 'borrower_name' exists (transform_columns_for_destination handles first_name/last_name combo)
                        if 'borrower_name' not in columns:
                            columns.append('borrower_name')
                            values.append('Unknown Borrower')

                        # Generate loan_number if not provided
                        if 'loan_number' not in columns:
                            import uuid
                            columns.append('loan_number')
                            values.append(f"IMP-{uuid.uuid4().hex[:8].upper()}")

                        # Add required fields
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.utcnow())
                        if 'stage' not in columns:
                            columns.append('stage')
                            values.append('processing')

                        placeholders = ', '.join(['%s'] * len(columns))
                        columns_str = ', '.join(columns)

                        cursor.execute(
                            f"INSERT INTO loans ({columns_str}) VALUES ({placeholders})",
                            values
                        )
                        imported += 1

                    elif destination == 'portfolio':
                        # Import as portfolio loan
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.utcnow())

                        placeholders = ', '.join(['%s'] * len(columns))
                        columns_str = ', '.join(columns)

                        cursor.execute(
                            f"INSERT INTO portfolio_loans ({columns_str}) VALUES ({placeholders})",
                            values
                        )
                        imported += 1

                except Exception as row_error:
                    failed += 1
                    errors.append(f"Row {idx + 1}: {str(row_error)}")
                    if len(errors) >= 100:  # Limit error messages
                        errors.append("... (additional errors truncated)")
                        break

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

        # Log skipped columns if any
        if skipped_columns:
            logger.info(f"Skipped columns not in {table_name} table: {skipped_columns}")

        return {
            "success": True,
            "total": len(df_mapped),
            "imported": imported,
            "failed": failed,
            "errors": errors,
            "destination": destination,
            "skipped_columns": list(skipped_columns) if skipped_columns else []
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in form data: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing import: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing data: {str(e)}")
