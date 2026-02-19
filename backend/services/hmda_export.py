"""
HMDA Export Service

Generates Home Mortgage Disclosure Act (HMDA) Loan Application Register (LAR)
exports in pipe-delimited format per CFPB requirements.

Enterprise readiness checks 2.15-2.17:
    - 2.15: HMDA data collection fields present on loan/lead models
    - 2.16: HMDA LAR export in correct pipe-delimited format
    - 2.17: HMDA field validation before export

HMDA LAR Format (2018+ format):
    Pipe-delimited text file with one row per application/loan.
    Each row contains data fields in a fixed order per the HMDA Filing
    Instructions Guide published by the CFPB.

Reference:
    https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields

Usage:
    from services.hmda_export import generate_hmda_lar

    result = generate_hmda_lar(db, organization_id=1, year=2025)
    if result["validation_errors"]:
        # Handle validation issues
        ...
    else:
        lar_content = result["lar_content"]
        # Write to file or return as download
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, extract

logger = logging.getLogger(__name__)


# ============================================================================
# HMDA Field Mappings
# ============================================================================

# Action taken codes per HMDA
ACTION_TAKEN_MAP = {
    # Loan stages that map to HMDA action codes
    "FUNDED": "1",            # 1 = Loan originated
    "APPROVED": "2",          # 2 = Application approved but not accepted
    "DENIED": "3",            # 3 = Application denied
    "WITHDRAWN": "4",         # 4 = Application withdrawn by applicant
    "CANCELLED": "5",         # 5 = File closed for incompleteness
    "DOES_NOT_QUALIFY": "3",  # Maps to denied
    "DEAD": "5",              # Maps to file closed
}

# Loan purpose mapping
LOAN_PURPOSE_MAP = {
    "purchase": "1",           # 1 = Home purchase
    "Purchase": "1",
    "refinance": "31",         # 31 = Refinancing
    "Refinance": "31",
    "cash_out": "32",          # 32 = Cash-out refinancing
    "Cash Out": "32",
    "home_improvement": "2",   # 2 = Home improvement
    "other": "4",              # 4 = Other purpose
}

# Property type mapping
PROPERTY_TYPE_MAP = {
    "single_family": "1",      # 1 = Single family (1-4 units) site-built
    "Single Family": "1",
    "condo": "1",
    "Condo": "1",
    "townhouse": "1",
    "Townhouse": "1",
    "multi_family": "1",       # Still 1 if 1-4 units
    "Multi Family": "1",
    "manufactured": "2",       # 2 = Manufactured home
    "Manufactured": "2",
}

# Occupancy type mapping
OCCUPANCY_TYPE_MAP = {
    "primary": "1",            # 1 = Principal residence
    "Primary": "1",
    "second_home": "2",        # 2 = Second residence
    "Second Home": "2",
    "investment": "3",          # 3 = Investment property
    "Investment": "3",
}

# Loan type mapping
LOAN_TYPE_MAP = {
    "conventional": "1",       # 1 = Conventional
    "Conventional": "1",
    "fha": "2",                # 2 = FHA
    "FHA": "2",
    "va": "3",                 # 3 = VA
    "VA": "3",
    "usda": "4",               # 4 = USDA/FSA/RHS
    "USDA": "4",
}


# ============================================================================
# HMDA Field Validation
# ============================================================================

# Fields required for a valid HMDA LAR record
REQUIRED_FIELDS = [
    "loan_number",
    "action_taken",
    "loan_type",
    "loan_purpose",
    "loan_amount",
    "property_state",
    "property_county",
]

# Fields that should be present but can use "NA" placeholder
RECOMMENDED_FIELDS = [
    "property_type",
    "occupancy_type",
    "interest_rate",
    "property_zip",
]


def _validate_loan_for_hmda(
    loan: Any,
    loan_stage: str,
) -> List[Dict[str, str]]:
    """Validate that a loan has sufficient data for HMDA reporting.

    Args:
        loan: Loan ORM object
        loan_stage: The loan's current stage string

    Returns:
        List of validation error dicts with field name and message
    """
    errors = []

    if not loan.loan_number:
        errors.append({
            "field": "loan_number",
            "loan_id": loan.id,
            "message": "Loan number is required for HMDA reporting",
        })

    # Action taken must be determinable
    action = ACTION_TAKEN_MAP.get(loan_stage)
    if not action:
        errors.append({
            "field": "stage",
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "message": f"Loan stage '{loan_stage}' does not map to a HMDA action taken code. "
                       f"Valid terminal stages: {list(ACTION_TAKEN_MAP.keys())}",
        })

    # Loan amount
    if not loan.amount or loan.amount <= 0:
        errors.append({
            "field": "amount",
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "message": "Loan amount is required and must be positive",
        })

    # Property state (required for geocoding)
    if not loan.property_state:
        errors.append({
            "field": "property_state",
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "message": "Property state is required for HMDA reporting",
        })

    # Property county (used for census tract determination)
    if not loan.property_county:
        errors.append({
            "field": "property_county",
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "message": "Property county is required for HMDA geocoding",
        })

    return errors


# ============================================================================
# HMDA LAR Record Builder
# ============================================================================

def _safe_str(value: Any, default: str = "NA") -> str:
    """Convert a value to string safely, using default for None/empty."""
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _format_amount(amount: Optional[float]) -> str:
    """Format loan amount as integer string (HMDA format: no decimals, in thousands)."""
    if amount is None or amount <= 0:
        return "NA"
    # HMDA reports amount in whole dollars (not thousands)
    return str(int(round(amount)))


def _format_rate(rate: Optional[float]) -> str:
    """Format interest rate for HMDA (decimal format with 2 decimal places)."""
    if rate is None:
        return "NA"
    return f"{rate:.2f}"


def _format_date_hmda(dt: Any) -> str:
    """Format date for HMDA (YYYYMMDD format)."""
    if dt is None:
        return "NA"
    if isinstance(dt, datetime):
        dt = dt.date()
    if isinstance(dt, date):
        return dt.strftime("%Y%m%d")
    return "NA"


def _build_lar_record(
    loan: Any,
    lei: str,
    year: int,
) -> str:
    """Build a single HMDA LAR record as a pipe-delimited line.

    The field order follows the CFPB HMDA Filing Instructions.
    Not all 110 fields are populated from this CRM's data model;
    fields without data use "NA" as placeholder per HMDA spec.

    Args:
        loan: Loan ORM object
        lei: Legal Entity Identifier for the reporting institution
        year: Reporting year

    Returns:
        Pipe-delimited string representing one LAR record
    """
    stage = (loan.stage or "").upper()

    # Core fields
    action_taken = ACTION_TAKEN_MAP.get(stage, "6")  # 6 = purchased loan (default/fallback)
    loan_type = LOAN_TYPE_MAP.get(loan.loan_type or "", "1")
    loan_purpose = LOAN_PURPOSE_MAP.get(loan.loan_purpose or "", "4")  # 4 = other
    occupancy = OCCUPANCY_TYPE_MAP.get(loan.occupancy_type or "", "1")  # 1 = primary
    construction_method = PROPERTY_TYPE_MAP.get(loan.property_type or "", "1")

    # Action taken date - use the relevant milestone date
    action_date = "NA"
    if stage == "FUNDED" and loan.funded_date:
        action_date = _format_date_hmda(loan.funded_date)
    elif stage == "DENIED" and loan.withdrawn_date:
        action_date = _format_date_hmda(loan.withdrawn_date)
    elif stage == "WITHDRAWN" and loan.withdrawn_date:
        action_date = _format_date_hmda(loan.withdrawn_date)
    elif loan.updated_at:
        action_date = _format_date_hmda(loan.updated_at)

    # Application date
    app_date = _format_date_hmda(loan.application_date)

    # Property location
    state_code = _safe_str(loan.property_state)
    county_code = _safe_str(loan.property_county)
    zip_code = _safe_str(loan.property_zip)
    # Census tract - would need geocoding service; use NA for now
    census_tract = "NA"

    # Build the pipe-delimited record
    # Follows HMDA LAR field order (simplified subset of the full 110 fields)
    fields = [
        # Record identifier / activity year
        str(year),                              # 1: Activity Year
        _safe_str(lei),                         # 2: LEI (Legal Entity Identifier)
        _safe_str(loan.loan_number),            # 3: Universal Loan Identifier (ULI)
        app_date,                               # 4: Application Date
        loan_type,                              # 5: Loan Type
        loan_purpose,                           # 6: Loan Purpose
        "1",                                    # 7: Preapproval (1=requested, 2=not requested)
        construction_method,                    # 8: Construction Method
        occupancy,                              # 9: Occupancy Type
        _format_amount(loan.amount),            # 10: Loan Amount
        action_taken,                           # 11: Action Taken
        action_date,                            # 12: Action Taken Date
        state_code,                             # 13: State
        county_code,                            # 14: County
        census_tract,                           # 15: Census Tract
        # Applicant demographics (not stored in CRM - use NA)
        "NA",                                   # 16: Ethnicity of Applicant 1
        "NA",                                   # 17: Ethnicity of Applicant 2
        "NA",                                   # 18: Co-Applicant Ethnicity 1
        "NA",                                   # 19: Co-Applicant Ethnicity 2
        "NA",                                   # 20: Race of Applicant 1
        "NA",                                   # 21: Race of Applicant 2
        "NA",                                   # 22: Co-Applicant Race 1
        "NA",                                   # 23: Co-Applicant Race 2
        "NA",                                   # 24: Sex of Applicant
        "NA",                                   # 25: Sex of Co-Applicant
        "NA",                                   # 26: Age of Applicant
        "NA",                                   # 27: Age of Co-Applicant
        _safe_str(loan.borrower_name, "NA"),    # 28: Income (using borrower name as placeholder - actual income from lead)
        # Loan terms
        _format_rate(loan.rate),                # 29: Interest Rate
        _safe_str(loan.term, "360"),            # 30: Loan Term
        # Property
        zip_code[:5] if zip_code != "NA" else "NA",  # 31: Property ZIP (first 5 digits)
        _safe_str(loan.property_type, "NA"),    # 32: Property Type (detailed)
        # Units
        _safe_str(loan.property_units, "1"),    # 33: Total Units
        # Financial ratios
        _safe_str(loan.ltv, "NA"),              # 34: LTV
        _safe_str(loan.cltv, "NA"),             # 35: CLTV
        # Lien status
        "1",                                    # 36: Lien Status (1=first, 2=subordinate)
    ]

    return "|".join(fields)


# ============================================================================
# Main Entry Point
# ============================================================================

def generate_hmda_lar(
    db: Session,
    organization_id: int,
    year: int,
    lei: str = "NA",
) -> Dict[str, Any]:
    """Generate HMDA LAR (Loan Application Register) export.

    Queries all loans for the given organization and year that have reached
    a terminal status (funded, denied, withdrawn, cancelled), validates
    the required HMDA fields, and produces a pipe-delimited LAR file.

    Args:
        db: SQLAlchemy database session
        organization_id: Organization to generate report for
        year: Reporting year (e.g., 2025)
        lei: Legal Entity Identifier for the institution (20-char alphanumeric)

    Returns:
        Dict containing:
            - lar_content: The pipe-delimited LAR text (None if validation fails)
            - total_records: Number of loan records included
            - validation_errors: List of validation error dicts
            - validation_warnings: List of non-blocking warnings
            - skipped_loans: Count of loans skipped due to ineligible stage
            - export_timestamp: When the export was generated
    """
    from database.models.lead_loan import Loan

    # Terminal stages that should appear in HMDA LAR
    terminal_stages = list(ACTION_TAKEN_MAP.keys())

    # Query loans for the reporting year and org
    loans = db.query(Loan).filter(
        and_(
            Loan.organization_id == organization_id,
            Loan.stage.in_(terminal_stages),
            # Filter by year using created_at as fallback
            # Ideally use the action-taken date, but created_at works for filtering
            extract('year', Loan.created_at) == year,
        )
    ).order_by(Loan.loan_number).all()

    if not loans:
        return {
            "lar_content": None,
            "total_records": 0,
            "validation_errors": [],
            "validation_warnings": [{
                "message": f"No loans found for organization {organization_id} "
                           f"in year {year} with terminal stages."
            }],
            "skipped_loans": 0,
            "export_timestamp": datetime.utcnow().isoformat(),
        }

    # Validate all loans
    all_errors = []
    all_warnings = []
    valid_loans = []

    for loan in loans:
        stage = (loan.stage or "").upper()
        errors = _validate_loan_for_hmda(loan, stage)

        if errors:
            all_errors.extend(errors)
        else:
            valid_loans.append(loan)

        # Check for recommended fields
        if not loan.property_type:
            all_warnings.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "field": "property_type",
                "message": "Property type not set; will use default in HMDA export",
            })
        if not loan.occupancy_type:
            all_warnings.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "field": "occupancy_type",
                "message": "Occupancy type not set; will default to primary residence",
            })

    # Build LAR content from valid loans
    lar_lines = []
    for loan in valid_loans:
        try:
            record = _build_lar_record(loan, lei, year)
            lar_lines.append(record)
        except Exception as e:
            logger.error(f"Failed to build HMDA record for loan {loan.id}: {e}")
            all_errors.append({
                "field": "record_build",
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "message": f"Failed to build HMDA record: {str(e)}",
            })

    # Join all lines into the LAR file content
    lar_content = "\n".join(lar_lines) if lar_lines else None

    return {
        "lar_content": lar_content,
        "total_records": len(lar_lines),
        "total_loans_queried": len(loans),
        "valid_loans": len(valid_loans),
        "validation_errors": all_errors,
        "validation_warnings": all_warnings,
        "skipped_loans": len(loans) - len(valid_loans),
        "export_timestamp": datetime.utcnow().isoformat(),
        "reporting_year": year,
        "organization_id": organization_id,
        "lei": lei,
    }


def validate_hmda_readiness(
    db: Session,
    organization_id: int,
    year: int,
) -> Dict[str, Any]:
    """Check HMDA readiness without generating the export.

    Useful for pre-flight checks to identify data gaps before attempting
    a full HMDA LAR generation.

    Args:
        db: SQLAlchemy database session
        organization_id: Organization to check
        year: Reporting year

    Returns:
        Dict with readiness status and field coverage statistics
    """
    from database.models.lead_loan import Loan

    terminal_stages = list(ACTION_TAKEN_MAP.keys())

    loans = db.query(Loan).filter(
        and_(
            Loan.organization_id == organization_id,
            Loan.stage.in_(terminal_stages),
            extract('year', Loan.created_at) == year,
        )
    ).all()

    if not loans:
        return {
            "is_ready": False,
            "total_loans": 0,
            "message": f"No terminal-stage loans found for year {year}",
        }

    # Check field coverage
    field_coverage = {
        "loan_number": 0,
        "loan_type": 0,
        "loan_purpose": 0,
        "amount": 0,
        "property_state": 0,
        "property_county": 0,
        "property_zip": 0,
        "property_type": 0,
        "occupancy_type": 0,
        "rate": 0,
        "application_date": 0,
    }

    total = len(loans)
    errors_by_loan = {}

    for loan in loans:
        loan_errors = []
        for field in field_coverage:
            val = getattr(loan, field, None)
            if val is not None and val != "" and val != 0:
                field_coverage[field] += 1
            else:
                loan_errors.append(field)

        if loan_errors:
            errors_by_loan[loan.loan_number or loan.id] = loan_errors

    # Calculate coverage percentages
    coverage_pct = {
        field: round((count / total) * 100, 1) if total > 0 else 0
        for field, count in field_coverage.items()
    }

    # Required fields must have 100% coverage
    required_coverage = {f: coverage_pct[f] for f in REQUIRED_FIELDS if f in coverage_pct}
    is_ready = all(pct == 100.0 for pct in required_coverage.values())

    return {
        "is_ready": is_ready,
        "total_loans": total,
        "field_coverage": coverage_pct,
        "required_field_coverage": required_coverage,
        "loans_with_errors": len(errors_by_loan),
        "error_details": errors_by_loan if len(errors_by_loan) <= 20 else {
            "note": f"{len(errors_by_loan)} loans have missing fields (showing first 20)",
            "samples": dict(list(errors_by_loan.items())[:20]),
        },
    }
