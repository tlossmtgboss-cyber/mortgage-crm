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


def parse_excel_or_csv(file_content: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or Excel file into DataFrame"""
    try:
        if filename.endswith('.csv'):
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(file_content), encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode CSV file with any common encoding")
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError(f"Unsupported file format: {filename}")

        return df
    except Exception as e:
        logger.error(f"Error parsing file {filename}: {e}")
        raise ValueError(f"Error parsing file: {str(e)}")


def suggest_column_mappings(headers: list) -> dict:
    """AI-like column mapping suggestions based on header names"""
    mappings = {}

    # Comprehensive column name patterns for all entity types
    patterns = {
        # === BORROWER/CONTACT INFO ===
        'borrower_name': ['borrower', 'borrower name', 'borrowername', 'client', 'client name', 'name', 'full name'],
        'borrower_email': ['borrower email', 'email', 'e-mail', 'email address', 'emailaddress', 'client email'],
        'borrower_phone': ['borrower phone', 'phone', 'telephone', 'tel', 'mobile', 'cell', 'phone number'],
        'coborrower_name': ['co-borrower', 'coborrower', 'co borrower', 'co-borrower name', 'coborrower name', 'co-applicant'],
        'co_borrower_email': ['co-borrower email', 'coborrower email', 'co borrower email'],
        'preferred_communication': ['preferred communication', 'contact preference', 'communication preference'],

        # === LOAN IDENTIFIERS ===
        'loan_number': ['loan number', 'loannumber', 'loan #', 'loan id', 'loanid', 'file number', 'file #', 'file id'],
        'stage': ['stage', 'status', 'loan stage', 'loan status', 'pipeline stage'],

        # === LOAN DETAILS ===
        'amount': ['loan amount', 'loanamount', 'amount', 'principal', 'loan value', 'base loan amount'],
        'rate': ['rate', 'interest rate', 'interestrate', 'int rate', 'note rate', 'interest'],
        'term': ['term', 'loan term', 'months', 'term months', 'loan term months'],
        'program': ['program', 'loan program', 'product name'],
        'loan_type': ['loan type', 'loantype', 'type', 'product', 'product type'],
        'purchase_price': ['purchase price', 'sale price', 'sales price', 'contract price'],
        'down_payment': ['down payment', 'downpayment', 'down', 'cash to close'],
        'lender': ['lender', 'investor', 'bank', 'lending institution'],

        # === PROPERTY INFO ===
        'property_address': ['property address', 'address', 'street', 'street address', 'subject property'],
        'property_city': ['property city', 'city', 'town'],
        'property_state': ['property state', 'state', 'province', 'st'],
        'property_zip': ['property zip', 'zip', 'zipcode', 'zip code', 'postal', 'postal code'],
        'appraisal_value': ['appraisal value', 'appraised value', 'appraisal', 'property value', 'home value', 'value'],

        # === TEAM MEMBERS ===
        'loan_officer_name': ['loan officer', 'lo', 'lo name', 'loan officer name', 'originator'],
        'loan_officer_email': ['lo email', 'loan officer email'],
        'processor': ['processor', 'loan processor', 'processor name'],
        'processor_email': ['processor email'],
        'underwriter': ['underwriter', 'uw', 'underwriter name'],
        'underwriter_email': ['underwriter email', 'uw email'],
        'closer': ['closer', 'closing agent', 'closer name'],
        'closer_email': ['closer email'],
        'realtor_agent': ['realtor', 'agent', 'real estate agent', 'realtor name', 'buyer agent'],
        'title_company': ['title company', 'title', 'escrow company', 'settlement company'],

        # === IMPORTANT DATES ===
        'closing_date': ['closing date', 'closingdate', 'close date', 'settlement date', 'closing'],
        'lock_date': ['lock date', 'rate lock date', 'locked date'],
        'lock_expiration_date': ['lock expiration', 'lock exp', 'lock expiration date', 'rate lock expiration'],
        'funded_date': ['funded date', 'funding date', 'fund date', 'disbursement date'],
        'contract_received_date': ['contract date', 'contract received', 'purchase contract date', 'executed contract'],
        'loan_estimate_sent_date': ['le sent', 'loan estimate sent', 'le date', 'loan estimate date'],
        'initial_disclosures_sent_date': ['initial disclosures sent', 'disclosures sent', 'initial le sent'],
        'initial_disclosures_signed_date': ['initial disclosures signed', 'disclosures signed'],
        'cd_received_signed_date': ['cd signed', 'closing disclosure signed', 'cd received'],
        'conditional_approval_date': ['conditional approval', 'conditional', 'cond approval date'],
        'final_closing_package_sent_date': ['final package sent', 'closing package sent', 'docs to title'],

        # === APPRAISAL DATES ===
        'appraisal_ordered_date': ['appraisal ordered', 'appraisal order date', 'ordered appraisal'],
        'appraisal_scheduled_date': ['appraisal scheduled', 'appraisal appointment', 'inspection date'],
        'appraisal_completed_date': ['appraisal completed', 'appraisal received', 'appraisal done'],

        # === RATE LOCK FIELDS ===
        'lock_term_days': ['lock term', 'lock days', 'lock period', 'rate lock term'],
        'float_down_available': ['float down', 'float down available', 'renegotiation'],

        # === LEAD SPECIFIC FIELDS ===
        'first_name': ['first name', 'firstname', 'first', 'fname', 'given name'],
        'last_name': ['last name', 'lastname', 'last', 'lname', 'surname', 'family name'],
        'source': ['source', 'lead source', 'referral source', 'how did you hear'],
        'credit_score': ['credit score', 'creditscore', 'fico', 'fico score'],
        'annual_income': ['income', 'annual income', 'yearly income', 'salary', 'gross income'],
        'monthly_debts': ['monthly debts', 'debts', 'monthly obligations'],
        'debt_to_income': ['dti', 'debt to income', 'debt-to-income'],
        'employment_status': ['employment', 'employment status', 'job status', 'employed'],
        'property_type': ['property type', 'prop type', 'dwelling type'],
        'loan_purpose': ['purpose', 'loan purpose', 'transaction type'],
        'first_time_buyer': ['first time buyer', 'ftb', 'first time homebuyer'],
        'preapproval_amount': ['preapproval amount', 'preapproval', 'pre-approval amount'],
        'notes': ['notes', 'comments', 'remarks', 'additional notes'],

        # === PORTFOLIO FIELDS ===
        'original_loan_amount': ['original amount', 'original loan amount', 'orig amount', 'original balance'],
        'current_balance': ['current balance', 'balance', 'unpaid balance', 'upb', 'remaining balance'],
        'monthly_payment': ['monthly payment', 'payment', 'pmt', 'p&i', 'pi payment'],
        'origination_date': ['origination date', 'orig date', 'start date', 'note date'],
        'maturity_date': ['maturity date', 'maturity', 'end date', 'payoff date'],
        'last_payment_date': ['last payment', 'last payment date', 'last pmt', 'most recent payment'],
        'payment_status': ['payment status', 'loan status', 'current status', 'delinquency status'],
        'ltv': ['ltv', 'loan to value', 'loan-to-value'],
        'apr': ['apr', 'annual percentage rate'],
        'points': ['points', 'discount points', 'loan points'],
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
        cursor = conn.cursor()

        imported = 0
        failed = 0
        errors = []

        try:
            for idx, row in df_mapped.iterrows():
                try:
                    row_dict = row.to_dict()
                    # Clean up NaN values
                    row_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}

                    if destination == 'leads':
                        # Import as lead
                        # Build the insert statement dynamically
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        # Add required fields if missing
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.utcnow())
                        if 'user_email' not in columns:
                            columns.append('user_email')
                            values.append(current_user.get('email', current_user.get('sub', 'demo@example.com')))
                        if 'stage' not in columns:
                            columns.append('stage')
                            values.append('new')
                        if 'source' not in columns:
                            columns.append('source')
                            values.append('CSV Import')

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

                        # Add required fields
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.utcnow())
                        if 'user_email' not in columns:
                            columns.append('user_email')
                            values.append(current_user.get('email', current_user.get('sub', 'demo@example.com')))
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
                        if 'user_email' not in columns:
                            columns.append('user_email')
                            values.append(current_user.get('email', current_user.get('sub', 'demo@example.com')))

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

        return {
            "success": True,
            "total": len(df_mapped),
            "imported": imported,
            "failed": failed,
            "errors": errors,
            "destination": destination
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in form data: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing import: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing data: {str(e)}")
