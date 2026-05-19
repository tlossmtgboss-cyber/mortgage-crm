"""
Data Import Routes - CSV/Excel file upload and import functionality
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional
import pandas as pd
import io
import json
from datetime import datetime, timezone
import logging
import re

logger = logging.getLogger(__name__)


_ALLOWED_SQL_TYPES = frozenset({
    "TEXT", "INTEGER", "NUMERIC", "BOOLEAN", "VARCHAR",
    "TIMESTAMP", "DATE", "FLOAT", "JSONB", "UUID",
})


def _validate_sql_identifier(name: str) -> str:
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def _validate_sql_type(col_type: str) -> str:
    if col_type.upper() not in _ALLOWED_SQL_TYPES:
        raise ValueError(f"Disallowed SQL column type: {col_type!r}")
    return col_type


def _safe_column_name(col: str, allowed: set | None = None) -> str:
    """Validate column name against allowlist and safe character regex.

    If `allowed` is provided, the column must be in the allowlist AND pass
    the format check. If `allowed` is None, only the format check is applied
    (legacy behavior for non-lead/loan destinations).
    """
    col = col.strip().lower()
    if allowed is not None:
        if col not in allowed:
            return ''
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
        return col
    return ''


# ── Column allowlists (derived from Lead/Loan SQLAlchemy models) ──

_ALLOWED_LEAD_COLUMNS = frozenset({
    # Identity
    'name', 'first_name', 'last_name', 'email', 'phone',
    # Co-applicant
    'co_applicant_name', 'co_applicant_email', 'co_applicant_phone',
    # Communication
    'preferred_communication',
    # Pipeline
    'stage', 'source', 'organization_code', 'referral_partner_id',
    # AI scoring
    'ai_score', 'sentiment', 'next_action',
    # Loan qualification
    'loan_type', 'preapproval_amount', 'credit_score', 'debt_to_income',
    # Assignment
    'owner_id', 'last_contact', 'loan_number', 'notes',
    # Property
    'address', 'city', 'state', 'zip_code', 'property_type', 'property_value', 'down_payment',
    # Financial
    'employment_status', 'annual_income', 'monthly_debts', 'first_time_buyer',
    # Loan details
    'loan_amount', 'interest_rate', 'loan_term', 'apr', 'points',
    'lock_date', 'lock_expiration', 'closing_date', 'lender',
    'loan_officer', 'processor', 'underwriter', 'production_assistant',
    'appraisal_value', 'ltv', 'cltv', 'dti', 'dti_front', 'dti_back',
    'program', 'status_date',
    # SLA milestone dates
    'lead_received_date', 'first_contact_attempt_date', 'first_contact_successful_date',
    'lead_qualification_date', 'application_link_sent_date', 'application_started_date',
    'application_completed_date', 'credit_pulled_date', 'preapproval_submission_date',
    'preapproval_issued_date', 'preapproval_expiration_date', 'realtor_referral_date',
    'rate_watch_enrollment_date', 'initial_consultation_date', 'property_address',
    # Rate lock intelligence
    'buying_timeline_category', 'borrower_risk_profile', 'target_payment', 'expected_purchase_date',
    # Referral fields
    'referral_score', 'referral_source_score', 'employment_referral_flag',
    'manager_flag', 'employees_managed', 'leadership_level', 'company_size',
    'employer_name', 'industry',
    # Workflow tracking
    'current_workflow_id', 'workflow_day', 'last_workflow_action', 'nurture_month', 'stage_changed_at',
    'current_milestone_status', 'current_milestone_entered_at',
    # Salesforce sync
    'occupancy_type', 'property_county', 'property_ownership_type', 'property_units',
    'rate_type', 'monthly_payment', 'property_tax', 'hazard_insurance',
    'mortgage_insurance', 'hoa_amount', 'origination_fee', 'estimated_prepaid_interest',
    'index_rate', 'margin', 'loan_purpose', 'file_state',
    'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
    'present_housing_expense', 'proposed_housing_expense',
    'present_monthly_payment', 'proposed_monthly_payment',
    # Marketing
    'receive_marketing',
    # Integration
    'salesforce_id', 'fub_person_id', 'fub_last_synced_at',
    # Metadata
    'meta_data', 'user_metadata',
    # System-managed (allowed for import logic, protected set takes precedence)
    'created_at', 'updated_at',
})

_ALLOWED_LOAN_COLUMNS = frozenset({
    # Core
    'loan_number', 'borrower_name', 'borrower_email', 'borrower_phone',
    'preferred_communication', 'coborrower_name', 'co_borrower_email', 'co_borrower_phone',
    # Pipeline
    'stage', 'program', 'loan_type',
    # Financials
    'amount', 'purchase_price', 'down_payment', 'rate', 'term',
    # Property
    'property_address', 'property_city', 'property_state', 'property_zip',
    # Key dates
    'lock_date', 'closing_date', 'funded_date',
    # Team
    'loan_officer_id', 'processor', 'underwriter', 'realtor_agent', 'title_company',
    'lender', 'loan_officer_name', 'loan_officer_email', 'processor_email',
    'underwriter_email', 'closer', 'closer_email', 'production_assistant',
    # SLA tracking
    'days_in_stage', 'sla_status', 'milestones', 'ai_insights',
    'predicted_close_date', 'risk_score', 'user_metadata',
    # Appraisal
    'appraisal_ordered_date', 'appraisal_scheduled_date', 'appraisal_completed_date',
    'appraisal_value', 'appraisal_received_date', 'appraisal_docs_expire_date',
    # Title & Insurance
    'title_ordered_date', 'title_received_date', 'insurance_ordered_date', 'insurance_received_date',
    # Rate lock
    'lock_expiration_date', 'rate_lock_status', 'rate_lock_recommendation',
    'lock_term_days', 'float_down_available', 'float_down_terms',
    'extension_cost_estimate', 'volatility_score', 'borrower_risk_profile',
    'lock_score', 'lock_decision_date', 'lock_decision_notes', 'last_rate_check',
    # Disclosure dates
    'initial_disclosures_sent_date', 'initial_disclosures_signed_date',
    'cd_received_signed_date', 'final_closing_package_sent_date',
    # Under contract
    'contract_received_date', 'loan_estimate_sent_date', 'conditional_approval_date',
    # AMR
    'last_amr_date', 'next_amr_date', 'refi_opportunity_score',
    # Workflow
    'current_workflow_id', 'last_workflow_action', 'stage_changed_at',
    'current_milestone_status', 'current_milestone_entered_at', 'mum_date',
    # SLA dates
    'prospect_date', 'application_date', 'le_pending_date', 'credit_only_date',
    'file_received_date', 'preapproval_date', 'uw_received_date',
    'conditions_for_review_date', 'suspended_date', 'loan_approved_date',
    'approved_not_accepted_date', 'approval_expires_date', 'cd_requested_date',
    'cd_sent_to_borrower_date', 'cd_acknowledged_date', 'clear_to_close_date',
    'docs_ordered_date', 'docs_out_date', 'credit_docs_expire_date',
    'scheduled_closing_date', 'scheduled_funding_date', 'funds_ordered_date',
    'funds_sent_date', 'first_payment_date', 'investor_purchased_date', 'withdrawn_date',
    # Salesforce sync
    'property_type', 'occupancy_type', 'property_county', 'property_ownership_type',
    'property_units', 'rate_type', 'monthly_payment', 'property_tax',
    'hazard_insurance', 'mortgage_insurance', 'hoa_amount', 'origination_fee',
    'estimated_prepaid_interest', 'points', 'index_rate', 'margin',
    'ltv', 'cltv', 'loan_purpose', 'file_state',
    'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
    'present_housing_expense', 'proposed_housing_expense',
    'present_monthly_payment', 'proposed_monthly_payment',
    # Integration
    'salesforce_id', 'encompass_loan_id',
    # System-managed (allowed for import logic, protected set takes precedence)
    'created_at', 'updated_at',
})


_ALLOWED_MUM_COLUMNS = frozenset({
    # Identity
    'client_name', 'name', 'email', 'phone',
    # Loan details
    'loan_number', 'original_close_date', 'close_date', 'closing_date',
    'first_payment_date', 'days_since_funding',
    'original_rate', 'current_rate', 'interest_rate',
    'original_loan_amount', 'current_loan_amount',
    'appraisal_value_at_closing', 'current_property_value',
    'loan_balance', 'loan_type',
    # Refinance opportunity
    'refinance_opportunity', 'estimated_savings', 'engagement_score',
    # Status & notes
    'status', 'notes', 'last_contact', 'next_touchpoint',
    'referrals_sent', 'opportunity_notes',
    # Team
    'loan_officer', 'loan_officer_email', 'processor', 'processor_email',
    'underwriter', 'underwriter_email', 'closer', 'closer_email',
    # Valuation
    'term', 'maturity_date', 'estimated_equity', 'current_ltv',
    'refi_score', 'property_state', 'property_zip', 'property_type',
    'lender', 'servicer', 'address', 'city', 'state', 'zip_code',
    # Integration
    'salesforce_id',
    # System-managed (allowed for import logic, protected set takes precedence)
    'user_id', 'created_at', 'updated_at',
})

_ALLOWED_PORTFOLIO_COLUMNS = frozenset({
    # Core loan fields applicable to portfolio loans
    'loan_number', 'borrower_name', 'borrower_email', 'borrower_phone',
    'coborrower_name', 'co_borrower_email',
    'property_address', 'property_city', 'property_state', 'property_zip',
    'property_type', 'occupancy_type',
    'amount', 'purchase_price', 'rate', 'term', 'stage', 'program',
    'loan_type', 'loan_purpose', 'lender',
    'appraisal_value', 'ltv', 'cltv',
    'closing_date', 'funded_date', 'lock_date',
    'loan_officer_name', 'processor', 'underwriter',
    'loan_officer_id', 'status', 'notes',
    # System-managed (allowed for import logic, protected set takes precedence)
    'created_at', 'updated_at',
})

# Columns that must never be set via CSV import (security-sensitive or system-managed)
_IMPORT_PROTECTED_COLUMNS = frozenset({
    "id", "owner_id", "organization_id", "permission_role", "role",
    "is_admin", "is_superuser", "password", "hashed_password",
    "two_factor_secret", "created_at", "tenant_id",
})

router = APIRouter(prefix="/api/v1/data-import", tags=["Data Import"])

# Import dependencies with lazy loading to avoid circular imports
_get_db_connection = None

# Canonical auth dependency — replaces local lazy wrapper (auth-dedup-W3).
from auth.dependencies import get_current_user  # noqa: E402

def get_db_connection():
    global _get_db_connection
    if _get_db_connection is None:
        try:
            from auto_import_routes import get_db_connection as _gdbc
            _get_db_connection = _gdbc
        except Exception as e:
            logger.exception(f"Failed to import get_db_connection from auto_import_routes: {e}")
            import psycopg2
            import os
            def fallback():
                return psycopg2.connect(os.getenv("DATABASE_URL"))
            _get_db_connection = fallback
    return _get_db_connection()


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
        MAX_IMPORT_SIZE = 25 * 1024 * 1024  # 25MB
        content = await file.read(MAX_IMPORT_SIZE + 1)
        if len(content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size: 25MB")
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
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Error analyzing file: {e}")
        raise HTTPException(status_code=500, detail="Error analyzing file")


def normalize_stage_value(stage_value: str, destination: str) -> str:
    """
    Normalize stage values to match database enum NAMES (not values).
    PostgreSQL enum expects names like 'NEW', 'LONG_TERM_NURTURE', not 'New', 'Long-Term Nurture'.
    Handles common variations in how stages are written in CSV files.
    If stage is not recognized, defaults to 'NEW' for leads or 'PROCESSING' for loans.
    """
    if not stage_value or not isinstance(stage_value, str):
        return 'NEW' if destination == 'leads' else 'PROCESSING'

    stage_lower = stage_value.strip().lower()

    if destination == 'leads':
        # LeadStage enum mappings - normalize to enum NAMES (uppercase with underscores)
        lead_stage_map = {
            # New
            'new': 'NEW',
            'new lead': 'NEW',
            'lead': 'NEW',
            # Attempted Contact
            'attempted contact': 'ATTEMPTED_CONTACT',
            'attempted': 'ATTEMPTED_CONTACT',
            'contact attempted': 'ATTEMPTED_CONTACT',
            # Prospect
            'prospect': 'PROSPECT',
            'qualified': 'PROSPECT',
            'hot': 'PROSPECT',
            # Application
            'application': 'APPLICATION',
            'application started': 'APPLICATION',
            'app started': 'APPLICATION',
            'in application': 'APPLICATION',
            'app in progress': 'APPLICATION',
            # Pre-Qualified
            'pre-qualified': 'PRE_QUALIFIED',
            'pre qualified': 'PRE_QUALIFIED',
            'prequalified': 'PRE_QUALIFIED',
            'prequal': 'PRE_QUALIFIED',
            'credit only': 'PRE_QUALIFIED',  # Credit Only maps to Pre-Qualified
            'credit': 'PRE_QUALIFIED',
            # Pre-Approved
            'pre-approved': 'PRE_APPROVED',
            'pre approved': 'PRE_APPROVED',
            'preapproved': 'PRE_APPROVED',
            'preapproval': 'PRE_APPROVED',
            'approved': 'PRE_APPROVED',
            # Under Contract
            'under contract': 'UNDER_CONTRACT',
            'contract': 'UNDER_CONTRACT',
            'in contract': 'UNDER_CONTRACT',
            'ratified': 'UNDER_CONTRACT',
            # Long-Term Nurture
            'long-term nurture': 'LONG_TERM_NURTURE',
            'long term nurture': 'LONG_TERM_NURTURE',
            'nurture': 'LONG_TERM_NURTURE',
            'long term': 'LONG_TERM_NURTURE',
            'future': 'LONG_TERM_NURTURE',
            'not ready': 'LONG_TERM_NURTURE',
            # Closed
            'closed': 'CLOSED',
            'funded': 'CLOSED',
            'closed won': 'CLOSED',
            'won': 'CLOSED',
            # AMR
            'amr': 'AMR',
            'annual mortgage review': 'AMR',
            'past client': 'AMR',
            # Referral Source
            'referral source': 'REFERRAL_SOURCE',
            'referral': 'REFERRAL_SOURCE',
            'referral partner': 'REFERRAL_SOURCE',
            # Withdrawn
            'withdrawn': 'WITHDRAWN',
            'cancelled': 'WITHDRAWN',
            'canceled': 'WITHDRAWN',
            'dead': 'WITHDRAWN',
            'lost': 'WITHDRAWN',
            'closed lost': 'WITHDRAWN',
            # Does Not Qualify
            'does not qualify': 'DOES_NOT_QUALIFY',
            'dnq': 'DOES_NOT_QUALIFY',
            'not qualified': 'DOES_NOT_QUALIFY',
            'disqualified': 'DOES_NOT_QUALIFY',
            'unqualified': 'DOES_NOT_QUALIFY',
        }
        # Return mapped value, or default to 'NEW' if not found
        return lead_stage_map.get(stage_lower, 'NEW')

    elif destination == 'loans':
        # LoanStage enum mappings - comprehensive list of variants
        loan_stage_map = {
            # Application/Pre-disclosure
            'application': 'Application',
            'app': 'Application',
            'new application': 'Application',
            'disclosed': 'Disclosed',
            'le sent': 'Disclosed',
            'processing': 'Processing',
            'in processing': 'Processing',
            'proc': 'Processing',
            # Submission
            'submitted': 'Submitted',
            'uw submitted': 'Submitted',
            'submit': 'Submitted',
            # Underwriting
            'uw received': 'UW Received',
            'underwriting': 'UW Received',
            'uw': 'UW Received',
            'in uw': 'UW Received',
            'in underwriting': 'UW Received',
            'conditional approval': 'Conditional Approval',
            'conditional': 'Conditional Approval',
            'cond approval': 'Conditional Approval',
            'approved': 'Approved',
            'approved with conditions': 'Conditional Approval',
            'suspended': 'Suspended',
            'susp': 'Suspended',
            # Clear to Close - normalize all variants to 'CTC' (the established DB enum value)
            'clear to close': 'CTC',
            'ctc': 'CTC',
            'clearto close': 'CTC',
            'cleartoclose': 'CTC',
            'clear-to-close': 'CTC',
            'c.t.c.': 'CTC',
            'c.t.c': 'CTC',
            # Closing & funding
            'closing': 'Closing',
            'docs out': 'Docs Out',
            'docs': 'Docs Out',
            'documents out': 'Docs Out',
            'funded': 'Funded',
            'closed': 'Funded',
            'complete': 'Funded',
            'settled': 'Funded',
        }
        # Return mapped value, or default to 'Processing' if not found
        return loan_stage_map.get(stage_lower, 'Processing')

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

    elif destination == 'mum_clients':
        # Transform loan-style columns to MUM client columns
        column_transforms = {
            'borrower_name': 'name',
            'borrower_email': 'email',
            'borrower_phone': 'phone',
            'amount': 'loan_balance',
            'loan_amount': 'loan_balance',
            'rate': 'current_rate',
            'interest_rate': 'current_rate',
            'closing_date': 'original_close_date',
        }
        for old_col, new_col in column_transforms.items():
            if old_col in result and new_col not in result:
                result[new_col] = result.pop(old_col)
            elif old_col in result and new_col in result:
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
    """Filter row_dict to only include columns that exist in the table, pass sanitization, and are not protected"""
    return {
        k: v for k, v in row_dict.items()
        if k in valid_columns and _safe_column_name(k) and k not in _IMPORT_PROTECTED_COLUMNS
    }


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
            # SAFETY: table_name, col_name, col_type all come from the hardcoded
            # columns_to_add list above (never from user input). Additionally
            # validated through _validate_sql_identifier (alphanumeric regex) and
            # _validate_sql_type (frozenset allowlist).
            safe_table = _validate_sql_identifier(table_name)
            safe_col = _validate_sql_identifier(col_name)
            safe_type = _validate_sql_type(col_type)
            cursor.execute(f"ALTER TABLE {safe_table} ADD COLUMN IF NOT EXISTS {safe_col} {safe_type}")
            conn.commit()
        except ValueError as e:
            logger.error(f"Invalid identifier in column addition: {e}")
        except Exception as e:
            logger.exception(f"Failed to add column {col_name} to {table_name}: {e}")
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
    # Initialize connection variables for proper cleanup in finally block
    conn = None
    cursor = None
    try:
        # Parse JSON strings
        answers_dict = json.loads(answers)
        mappings_dict = json.loads(mappings)

        # Read file content
        MAX_IMPORT_SIZE = 25 * 1024 * 1024  # 25MB
        content = await file.read(MAX_IMPORT_SIZE + 1)
        if len(content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size: 25MB")
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

                        # Get name and email for duplicate checking
                        name_idx = columns.index('name')
                        lead_name = values[name_idx]
                        lead_email = row_dict.get('email')
                        lead_phone = row_dict.get('phone')

                        # Check for duplicate by email first (most reliable)
                        existing_lead = None
                        if lead_email:
                            cursor.execute("SELECT id FROM leads WHERE LOWER(email) = LOWER(%s)", (lead_email,))
                            existing_lead = cursor.fetchone()

                        # If no email match, check by name + phone
                        if not existing_lead and lead_name and lead_name != 'Unknown Lead':
                            if lead_phone:
                                # Normalize phone for comparison
                                phone_digits = ''.join(filter(str.isdigit, str(lead_phone)))
                                if len(phone_digits) >= 10:
                                    cursor.execute(
                                        "SELECT id FROM leads WHERE LOWER(name) = LOWER(%s) AND phone LIKE %s",
                                        (lead_name, f"%{phone_digits[-10:]}%")
                                    )
                                    existing_lead = cursor.fetchone()
                            else:
                                # Check by name only (less reliable, only for exact matches)
                                cursor.execute(
                                    "SELECT id FROM leads WHERE LOWER(name) = LOWER(%s)",
                                    (lead_name,)
                                )
                                existing_lead = cursor.fetchone()

                        if existing_lead:
                            if duplicate_handling == 'skip':
                                # Skip this record
                                continue
                            elif duplicate_handling == 'update':
                                # Update existing record
                                # SAFETY: safe_col is validated against _ALLOWED_LEAD_COLUMNS
                                # (hardcoded frozenset) AND passes ^[a-zA-Z_][a-zA-Z0-9_]*$
                                # regex via _safe_column_name(). Values use %s placeholders
                                # (parameterized by psycopg2) — never interpolated into SQL.
                                update_cols = []
                                update_vals = []
                                for col, val in zip(columns, values):
                                    safe_col = _safe_column_name(col, _ALLOWED_LEAD_COLUMNS)
                                    if safe_col and safe_col not in _IMPORT_PROTECTED_COLUMNS and val is not None:
                                        update_cols.append(f"{safe_col} = %s")
                                        update_vals.append(val)
                                if update_cols:
                                    update_vals.append(existing_lead[0])
                                    cursor.execute(
                                        f"UPDATE leads SET {', '.join(update_cols)}, updated_at = NOW() WHERE id = %s",
                                        update_vals
                                    )
                                imported += 1
                                continue
                            # else: duplicate_handling == 'create_new' - continue to create

                        # Add required fields if missing
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.now(timezone.utc))
                        if 'stage' not in columns:
                            columns.append('stage')
                            values.append('NEW')  # Must match LeadStage enum NAME (not value)
                        if 'source' not in columns:
                            columns.append('source')
                            values.append('Data Import')

                        # CRITICAL: Set owner_id for multi-tenancy
                        # Get user_id from current_user (User object from get_current_user)
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'owner_id' not in columns:
                            columns.append('owner_id')
                            values.append(user_id)

                        # SAFETY: Column names validated against _ALLOWED_LEAD_COLUMNS
                        # (hardcoded frozenset) + regex. Values use %s (parameterized).
                        safe_cols = [c for c in columns if _safe_column_name(c, _ALLOWED_LEAD_COLUMNS)]
                        safe_vals = [v for c, v in zip(columns, values) if _safe_column_name(c, _ALLOWED_LEAD_COLUMNS)]
                        placeholders = ', '.join(['%s'] * len(safe_cols))
                        columns_str = ', '.join(safe_cols)

                        cursor.execute(
                            f"INSERT INTO leads ({columns_str}) VALUES ({placeholders})",
                            safe_vals
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

                        # Get borrower_name for duplicate checking
                        borrower_name_idx = columns.index('borrower_name')
                        borrower_name = values[borrower_name_idx]
                        borrower_email = row_dict.get('borrower_email')
                        loan_number = row_dict.get('loan_number')

                        # Check for duplicate by loan_number first
                        existing_loan = None
                        if loan_number:
                            cursor.execute("SELECT id FROM loans WHERE loan_number = %s", (loan_number,))
                            existing_loan = cursor.fetchone()

                        # If no loan_number match, check by borrower_name + email
                        if not existing_loan and borrower_name and borrower_name != 'Unknown Borrower':
                            if borrower_email:
                                cursor.execute(
                                    "SELECT id FROM loans WHERE LOWER(borrower_name) = LOWER(%s) AND LOWER(borrower_email) = LOWER(%s)",
                                    (borrower_name, borrower_email)
                                )
                            else:
                                cursor.execute(
                                    "SELECT id FROM loans WHERE LOWER(borrower_name) = LOWER(%s)",
                                    (borrower_name,)
                                )
                            existing_loan = cursor.fetchone()

                        if existing_loan:
                            if duplicate_handling == 'skip':
                                # Skip this record
                                continue
                            elif duplicate_handling == 'update':
                                # Update existing record
                                # SAFETY: safe_col validated against _ALLOWED_LOAN_COLUMNS
                                # (hardcoded frozenset) + regex. Values use %s (parameterized).
                                update_cols = []
                                update_vals = []
                                for col, val in zip(columns, values):
                                    safe_col = _safe_column_name(col, _ALLOWED_LOAN_COLUMNS)
                                    if safe_col and safe_col not in _IMPORT_PROTECTED_COLUMNS and safe_col != 'loan_number' and val is not None:
                                        update_cols.append(f"{safe_col} = %s")
                                        update_vals.append(val)
                                if update_cols:
                                    update_vals.append(existing_loan[0])
                                    cursor.execute(
                                        f"UPDATE loans SET {', '.join(update_cols)}, updated_at = NOW() WHERE id = %s",
                                        update_vals
                                    )
                                imported += 1
                                continue
                            # else: duplicate_handling == 'create_new' - continue to create

                        # Generate loan_number if not provided
                        if 'loan_number' not in columns:
                            import uuid
                            columns.append('loan_number')
                            values.append(f"IMP-{uuid.uuid4().hex[:8].upper()}")

                        # Add required fields
                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.now(timezone.utc))
                        if 'stage' not in columns:
                            columns.append('stage')
                            values.append('processing')

                        # CRITICAL: Set loan_officer_id for multi-tenancy if not already mapped
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'loan_officer_id' not in columns:
                            columns.append('loan_officer_id')
                            values.append(user_id)

                        # SAFETY: Column names validated against _ALLOWED_LOAN_COLUMNS
                        # (hardcoded frozenset) + regex. Values use %s (parameterized).
                        safe_cols = [c for c in columns if _safe_column_name(c, _ALLOWED_LOAN_COLUMNS)]
                        safe_vals = [v for c, v in zip(columns, values) if _safe_column_name(c, _ALLOWED_LOAN_COLUMNS)]
                        placeholders = ', '.join(['%s'] * len(safe_cols))
                        columns_str = ', '.join(safe_cols)

                        cursor.execute(
                            f"INSERT INTO loans ({columns_str}) VALUES ({placeholders})",
                            safe_vals
                        )
                        imported += 1

                    elif destination == 'portfolio':
                        # Import as portfolio loan
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        if 'created_at' not in columns:
                            columns.append('created_at')
                            values.append(datetime.now(timezone.utc))

                        # SAFETY: Column names validated against _ALLOWED_PORTFOLIO_COLUMNS
                        # (hardcoded frozenset) + regex. Values use %s (parameterized).
                        safe_cols = [c for c in columns if _safe_column_name(c, _ALLOWED_PORTFOLIO_COLUMNS)]
                        safe_vals = [v for c, v in zip(columns, values) if _safe_column_name(c, _ALLOWED_PORTFOLIO_COLUMNS)]
                        placeholders = ', '.join(['%s'] * len(safe_cols))
                        columns_str = ', '.join(safe_cols)

                        cursor.execute(
                            f"INSERT INTO portfolio_loans ({columns_str}) VALUES ({placeholders})",
                            safe_vals
                        )
                        imported += 1

                    elif destination == 'mum_clients':
                        # Import as MUM (Mortgages Under Management) client - closed loans
                        columns = list(row_dict.keys())
                        values = list(row_dict.values())

                        # Map common loan fields to MUM client fields
                        field_mapping = {
                            'borrower_name': 'name',
                            'borrower_email': 'email',
                            'borrower_phone': 'phone',
                            'amount': 'loan_balance',
                            'rate': 'current_rate',
                            'interest_rate': 'current_rate',
                            'closing_date': 'original_close_date',
                        }

                        # Apply field mapping
                        mapped_columns = []
                        mapped_values = []
                        for col, val in zip(columns, values):
                            mapped_col = field_mapping.get(col, col)
                            mapped_columns.append(mapped_col)
                            mapped_values.append(val)
                        columns = mapped_columns
                        values = mapped_values

                        # Ensure 'name' exists
                        if 'name' not in columns:
                            name_val = row_dict.get('borrower_name') or row_dict.get('first_name', '') + ' ' + row_dict.get('last_name', '')
                            if name_val.strip():
                                columns.append('name')
                                values.append(name_val.strip())
                            else:
                                columns.append('name')
                                values.append('Unknown Client')

                        # Get name and loan_number for duplicate checking
                        client_name = values[columns.index('name')] if 'name' in columns else None
                        loan_number = row_dict.get('loan_number')

                        # Check for duplicate
                        existing_client = None
                        if loan_number:
                            cursor.execute("SELECT id FROM mum_clients WHERE loan_number = %s", (loan_number,))
                            existing_client = cursor.fetchone()

                        if not existing_client and client_name and client_name != 'Unknown Client':
                            cursor.execute(
                                "SELECT id FROM mum_clients WHERE LOWER(name) = LOWER(%s)",
                                (client_name,)
                            )
                            existing_client = cursor.fetchone()

                        if existing_client:
                            if duplicate_handling == 'skip':
                                continue
                            elif duplicate_handling == 'update':
                                # SAFETY: safe_col validated against _ALLOWED_MUM_COLUMNS
                                # (hardcoded frozenset) + regex. Values use %s (parameterized).
                                update_cols = []
                                update_vals = []
                                for col, val in zip(columns, values):
                                    safe_col = _safe_column_name(col, _ALLOWED_MUM_COLUMNS)
                                    if safe_col and safe_col not in _IMPORT_PROTECTED_COLUMNS and safe_col != 'loan_number' and val is not None:
                                        update_cols.append(f"{safe_col} = %s")
                                        update_vals.append(val)
                                if update_cols:
                                    update_vals.append(existing_client[0])
                                    cursor.execute(
                                        f"UPDATE mum_clients SET {', '.join(update_cols)}, updated_at = NOW() WHERE id = %s",
                                        update_vals
                                    )
                                imported += 1
                                continue

                        # Map 'name' to 'client_name' (required column)
                        if 'name' in columns and 'client_name' not in columns:
                            idx = columns.index('name')
                            columns[idx] = 'client_name'
                        elif 'client_name' not in columns:
                            columns.append('client_name')
                            values.append(client_name or 'Unknown Client')

                        # Add required NOT NULL fields with defaults
                        required_fields = {
                            'created_at': datetime.now(timezone.utc),
                            'status': 'active',
                            'original_loan_amount': 0,
                            'current_loan_amount': 0,
                            'interest_rate': 0,
                            'appraisal_value_at_closing': 0,
                            'current_property_value': 0,
                            'closing_date': datetime.now(timezone.utc).date(),
                            'first_payment_date': datetime.now(timezone.utc).date(),
                        }

                        # Map imported values to required fields
                        if 'loan_balance' in columns:
                            idx = columns.index('loan_balance')
                            lb_val = values[idx] or 0
                            if 'original_loan_amount' not in columns:
                                columns.append('original_loan_amount')
                                values.append(lb_val)
                            if 'current_loan_amount' not in columns:
                                columns.append('current_loan_amount')
                                values.append(lb_val)
                            if 'appraisal_value_at_closing' not in columns:
                                columns.append('appraisal_value_at_closing')
                                values.append(lb_val * 1.25 if lb_val else 0)
                            if 'current_property_value' not in columns:
                                columns.append('current_property_value')
                                values.append(lb_val * 1.25 if lb_val else 0)

                        if 'current_rate' in columns and 'interest_rate' not in columns:
                            idx = columns.index('current_rate')
                            columns.append('interest_rate')
                            values.append(values[idx] or 0)

                        if 'original_close_date' in columns and 'closing_date' not in columns:
                            idx = columns.index('original_close_date')
                            columns.append('closing_date')
                            values.append(values[idx] or datetime.now(timezone.utc).date())
                            if 'first_payment_date' not in columns:
                                columns.append('first_payment_date')
                                values.append(values[idx] or datetime.now(timezone.utc).date())

                        # Add any remaining required fields with defaults
                        for field, default in required_fields.items():
                            if field not in columns:
                                columns.append(field)
                                values.append(default)

                        # Set user_id for multi-tenancy
                        user_id = getattr(current_user, 'id', None)
                        if user_id and 'user_id' not in columns:
                            columns.append('user_id')
                            values.append(user_id)

                        # SAFETY: Column names validated against _ALLOWED_MUM_COLUMNS
                        # (hardcoded frozenset) + regex. Values use %s (parameterized).
                        safe_cols = [c for c in columns if _safe_column_name(c, _ALLOWED_MUM_COLUMNS)]
                        safe_vals = [v for c, v in zip(columns, values) if _safe_column_name(c, _ALLOWED_MUM_COLUMNS)]
                        placeholders = ', '.join(['%s'] * len(safe_cols))
                        columns_str = ', '.join(safe_cols)

                        # Log what we're about to insert for debugging
                        logger.info(f"MUM insert - columns: {columns_str[:200]}")
                        logger.info(f"MUM insert - values count: {len(safe_vals)}, client_name: {safe_vals[safe_cols.index('client_name')] if 'client_name' in safe_cols else 'N/A'}")

                        cursor.execute(
                            f"INSERT INTO mum_clients ({columns_str}) VALUES ({placeholders})",
                            safe_vals
                        )
                        imported += 1
                        logger.info(f"MUM insert successful - row {idx + 1}")

                    # Commit each successful row immediately to prevent cascade failures
                    conn.commit()

                except Exception as row_error:
                    # Rollback just this failed row and continue with the next
                    conn.rollback()
                    failed += 1
                    error_msg = f"Row {idx + 1}: {str(row_error)}"
                    errors.append(error_msg)
                    logger.error(f"Import error - {destination}: {error_msg}")
                    if len(errors) >= 100:  # Limit error messages
                        errors.append("... (additional errors truncated)")
                        break

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
        raise HTTPException(status_code=400, detail="Invalid JSON in form data")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Error executing import: {e}")
        raise HTTPException(status_code=500, detail="Error importing data")
    finally:
        # CRITICAL: Always close connections to prevent leaks
        # This handles cases where exception occurs after conn is created but before inner try
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close cursor during import cleanup: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close connection during import cleanup: {e}")


@router.get("/stage-values")
async def get_all_stage_values(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all unique stage values currently in the leads table.
    This helps identify invalid stage values that need to be fixed.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT stage, COUNT(*) as count FROM leads GROUP BY stage ORDER BY count DESC")
        results = cursor.fetchall()

        return {
            "stage_values": [{"stage": row[0], "count": row[1]} for row in results],
            "total_unique": len(results)
        }
    except Exception as e:
        logger.error(f"Error getting stage values: {e}")
        return {"error": "Internal server error"}
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close cursor during stage-values cleanup: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close connection during stage-values cleanup: {e}")


@router.post("/fix-stages")
async def fix_lead_stage_values(
    key: str = "",
    current_user: dict = Depends(get_current_user)
):
    """
    Fix invalid lead stage values in the database.
    Call with: POST /api/v1/data-import/fix-stages?key=fix-stages-now
    """
    if key != "fix-stages-now":
        raise HTTPException(status_code=403, detail="Invalid key. Use ?key=fix-stages-now")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Map of invalid values to valid LeadStage enum NAMES
        # PostgreSQL enum expects names like: NEW, ATTEMPTED_CONTACT, PROSPECT, APPLICATION,
        # PRE_QUALIFIED, PRE_APPROVED, UNDER_CONTRACT, LONG_TERM_NURTURE,
        # CLOSED, AMR, REFERRAL_SOURCE, WITHDRAWN, DOES_NOT_QUALIFY
        stage_fixes = {
            # CSV variations (human readable) -> enum NAMES
            'Credit Only': 'PRE_QUALIFIED',
            'credit only': 'PRE_QUALIFIED',
            'Pre Approved': 'PRE_APPROVED',
            'Pre Qualified': 'PRE_QUALIFIED',
            'Long Term Nurture': 'LONG_TERM_NURTURE',
            'Attempted': 'ATTEMPTED_CONTACT',
            'new': 'NEW',
            # Human readable enum VALUES (Title Case) -> enum NAMES
            'New': 'NEW',
            'Attempted Contact': 'ATTEMPTED_CONTACT',
            'Prospect': 'PROSPECT',
            'Application': 'APPLICATION',
            'Pre-Qualified': 'PRE_QUALIFIED',
            'Pre-Approved': 'PRE_APPROVED',
            'Under Contract': 'UNDER_CONTRACT',
            'Long-Term Nurture': 'LONG_TERM_NURTURE',
            'Closed': 'CLOSED',
            'Referral Source': 'REFERRAL_SOURCE',
            'Withdrawn': 'WITHDRAWN',
            'Does Not Qualify': 'DOES_NOT_QUALIFY',
        }

        fixed_count = 0
        for old_value, new_value in stage_fixes.items():
            try:
                # Use CAST to text for comparison since the stored value may not be a valid enum
                cursor.execute(
                    "UPDATE leads SET stage = %s WHERE stage::text = %s",
                    (new_value, old_value)
                )
                if cursor.rowcount > 0:
                    logger.info(f"Fixed {cursor.rowcount} leads: '{old_value}' -> '{new_value}'")
                    fixed_count += cursor.rowcount
                conn.commit()
            except Exception as e:
                logger.warning(f"Could not fix '{old_value}': {e}")
                conn.rollback()

        # Also set any NULL stages to 'NEW' (enum name)
        try:
            cursor.execute("UPDATE leads SET stage = 'NEW' WHERE stage IS NULL")
            if cursor.rowcount > 0:
                logger.info(f"Set {cursor.rowcount} NULL stages to 'New'")
                fixed_count += cursor.rowcount
            conn.commit()
        except Exception as e:
            logger.warning(f"Could not fix NULL stages: {e}")
            conn.rollback()

        return {
            "success": True,
            "message": f"Fixed {fixed_count} lead stage values",
            "fixed_count": fixed_count
        }
    except Exception as e:
        logger.error(f"Lead stage fix failed: {e}")
        return {
            "success": False,
            "message": "Fix failed",
            "error": "Internal server error"
        }
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close cursor during fix-stages cleanup: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close connection during fix-stages cleanup: {e}")


@router.post("/fix-owner-assignment")
async def fix_owner_assignment(
    user_id: int = 1,
    current_user: dict = Depends(get_current_user),
):
    """
    Fix leads and loans with NULL owner_id/loan_officer_id by assigning them to a specific user.
    Requires authentication. Admin-only operation.
    """

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        results = {
            "leads_fixed": 0,
            "loans_fixed": 0,
            "errors": []
        }

        # Verify user exists
        cursor.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")

        target_email = user[1]

        # Fix leads with NULL owner_id
        try:
            cursor.execute(
                "UPDATE leads SET owner_id = %s WHERE owner_id IS NULL",
                (user_id,)
            )
            results["leads_fixed"] = cursor.rowcount
            logger.info(f"Fixed {cursor.rowcount} leads - assigned to user {user_id} ({target_email})")
            conn.commit()
        except Exception as e:
            results["errors"].append(f"Failed to fix leads: {str(e)}")
            conn.rollback()

        # Fix loans with NULL loan_officer_id
        try:
            cursor.execute(
                "UPDATE loans SET loan_officer_id = %s WHERE loan_officer_id IS NULL",
                (user_id,)
            )
            results["loans_fixed"] = cursor.rowcount
            logger.info(f"Fixed {cursor.rowcount} loans - assigned to user {user_id} ({target_email})")
            conn.commit()
        except Exception as e:
            results["errors"].append(f"Failed to fix loans: {str(e)}")
            conn.rollback()

        return {
            "success": True,
            "message": f"Fixed {results['leads_fixed']} leads and {results['loans_fixed']} loans - assigned to {target_email}",
            "target_user_id": user_id,
            "target_email": target_email,
            **results
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Owner assignment fix failed: {e}")
        return {
            "success": False,
            "message": "Fix failed",
            "error": "Internal server error"
        }
    finally:
        # CRITICAL: Always close connections to prevent leaks
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close cursor during fix-owner cleanup: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close connection during fix-owner cleanup: {e}")


@router.get("/check-unassigned")
async def check_unassigned_records(
    current_user: dict = Depends(get_current_user),
):
    """
    Check for leads and loans without owner assignment.
    Useful for diagnosing multi-tenancy issues.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Count unassigned leads
        cursor.execute("SELECT COUNT(*) FROM leads WHERE owner_id IS NULL")
        unassigned_leads = cursor.fetchone()[0]

        # Count unassigned loans
        cursor.execute("SELECT COUNT(*) FROM loans WHERE loan_officer_id IS NULL")
        unassigned_loans = cursor.fetchone()[0]

        # Get sample of unassigned leads
        cursor.execute("""
            SELECT id, name, email, source, created_at
            FROM leads
            WHERE owner_id IS NULL
            ORDER BY created_at DESC
            LIMIT 10
        """)
        sample_leads = cursor.fetchall()

        # Get sample of unassigned loans
        cursor.execute("""
            SELECT id, loan_number, borrower_name, created_at
            FROM loans
            WHERE loan_officer_id IS NULL
            ORDER BY created_at DESC
            LIMIT 10
        """)
        sample_loans = cursor.fetchall()

        return {
            "success": True,
            "unassigned_leads_count": unassigned_leads,
            "unassigned_loans_count": unassigned_loans,
            "sample_unassigned_leads": [
                {"id": l[0], "name": l[1], "email": l[2], "source": l[3], "created_at": str(l[4]) if l[4] else None}
                for l in sample_leads
            ],
            "sample_unassigned_loans": [
                {"id": l[0], "loan_number": l[1], "borrower_name": l[2], "created_at": str(l[3]) if l[3] else None}
                for l in sample_loans
            ],
            "recommendation": "Run POST /api/v1/data-import/fix-owner-assignment?user_id=1 to fix (requires auth)" if (unassigned_leads > 0 or unassigned_loans > 0) else "All records have owner assignment"
        }
    except Exception as e:
        logger.error(f"Check unassigned failed: {e}")
        return {
            "success": False,
            "error": "Internal server error"
        }
    finally:
        # CRITICAL: Always close connections to prevent leaks
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.exception(f"Failed to close cursor during check-unassigned cleanup: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.exception(f"Failed to close connection during check-unassigned cleanup: {e}")
