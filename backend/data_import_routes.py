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

    # Common column name patterns
    patterns = {
        # Lead/Contact fields
        'first_name': ['first name', 'firstname', 'first', 'fname', 'given name'],
        'last_name': ['last name', 'lastname', 'last', 'lname', 'surname', 'family name'],
        'email': ['email', 'e-mail', 'email address', 'emailaddress'],
        'phone': ['phone', 'telephone', 'tel', 'mobile', 'cell', 'phone number', 'phonenumber'],
        'address': ['address', 'street', 'street address', 'property address', 'home address'],
        'city': ['city', 'town'],
        'state': ['state', 'province', 'st'],
        'zip_code': ['zip', 'zipcode', 'zip code', 'postal', 'postal code'],
        'credit_score': ['credit score', 'creditscore', 'fico', 'fico score'],
        'annual_income': ['income', 'annual income', 'yearly income', 'salary'],
        'notes': ['notes', 'comments', 'remarks'],

        # Loan fields
        'loan_number': ['loan number', 'loannumber', 'loan #', 'loan id', 'loanid', 'file number'],
        'borrower_name': ['borrower', 'borrower name', 'borrowername', 'client', 'client name'],
        'co_borrower_name': ['co-borrower', 'coborrower', 'co borrower', 'co-borrower name'],
        'loan_amount': ['loan amount', 'loanamount', 'amount', 'principal', 'loan value'],
        'interest_rate': ['rate', 'interest rate', 'interestrate', 'int rate', 'note rate'],
        'loan_term': ['term', 'loan term', 'months', 'term months'],
        'loan_type': ['loan type', 'loantype', 'type', 'product', 'program'],
        'loan_purpose': ['purpose', 'loan purpose', 'transaction type'],
        'closing_date': ['closing date', 'closingdate', 'close date', 'settlement date', 'funding date'],
        'lender': ['lender', 'investor', 'bank'],
        'processor': ['processor', 'loan processor'],
        'underwriter': ['underwriter', 'uw'],

        # Portfolio fields
        'original_loan_amount': ['original amount', 'original loan amount', 'orig amount'],
        'current_balance': ['current balance', 'balance', 'unpaid balance', 'upb'],
        'monthly_payment': ['monthly payment', 'payment', 'pmt', 'p&i'],
        'origination_date': ['origination date', 'orig date', 'start date'],
        'maturity_date': ['maturity date', 'maturity', 'end date'],
        'last_payment_date': ['last payment', 'last payment date', 'last pmt'],
        'payment_status': ['status', 'payment status', 'loan status'],
        'property_value': ['property value', 'value', 'appraisal', 'appraised value', 'home value'],
        'down_payment': ['down payment', 'downpayment', 'down'],
        'employment_status': ['employment', 'employment status', 'job status'],
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
