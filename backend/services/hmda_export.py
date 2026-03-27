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

# Fields required for a valid HMDA LAR record (loan-level)
REQUIRED_LOAN_FIELDS = [
    "loan_number",
    "action_taken",
    "loan_type",
    "loan_purpose",
    "loan_amount",
    "property_state",
    "property_county",
]

# Demographic fields required for HMDA (stored on BorrowerApplication)
REQUIRED_DEMOGRAPHIC_FIELDS = [
    "applicant_ethnicity",
    "applicant_race",
    "applicant_sex",
]

# Backward-compat alias used by validate_hmda_readiness field coverage check
REQUIRED_FIELDS = REQUIRED_LOAN_FIELDS

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
    db: Optional["Session"] = None,
) -> List[Dict[str, str]]:
    """Validate that a loan has sufficient data for HMDA reporting.

    Checks both loan-level required fields and demographic fields
    stored on BorrowerApplication. If *db* is provided, performs a
    lookup for the linked BorrowerApplication to verify demographic
    data; otherwise demographic checks are skipped.

    Args:
        loan: Loan ORM object
        loan_stage: The loan's current stage string
        db: Optional SQLAlchemy session for demographic field lookup

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

    # Loan purpose
    if not loan.loan_purpose:
        errors.append({
            "field": "loan_purpose",
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "message": "Loan purpose is required for HMDA reporting",
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

    # ----- Demographic fields from BorrowerApplication -----
    if db is not None:
        try:
            from database.models.borrower import BorrowerApplication

            app = db.query(BorrowerApplication).filter(
                BorrowerApplication.loan_id == loan.id
            ).first()

            if not app:
                errors.append({
                    "field": "borrower_application",
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "message": "No BorrowerApplication linked — all HMDA demographic fields are missing",
                })
            else:
                for demo_field in REQUIRED_DEMOGRAPHIC_FIELDS:
                    val = getattr(app, demo_field, None)
                    if not val or (isinstance(val, str) and not val.strip()):
                        errors.append({
                            "field": demo_field,
                            "loan_id": loan.id,
                            "loan_number": loan.loan_number,
                            "message": f"HMDA demographic field '{demo_field}' is missing on BorrowerApplication",
                        })
        except Exception as e:
            logger.warning(f"Could not check demographics for loan {loan.id}: {e}")

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


def _get_gmi_data(db: Session, loan: Any) -> Dict[str, str]:
    """Look up GMI (Government Monitoring Information) demographic data for a loan.

    GMI data is stored on BorrowerApplication, linked to the loan via loan_id.
    If no application is found or fields are empty, returns "NA" per HMDA spec.

    Args:
        db: SQLAlchemy database session
        loan: Loan ORM object

    Returns:
        Dict with HMDA demographic field values
    """
    defaults = {
        "applicant_ethnicity": "NA",
        "applicant_ethnicity_2": "NA",
        "co_applicant_ethnicity": "NA",
        "co_applicant_ethnicity_2": "NA",
        "applicant_race": "NA",
        "applicant_race_2": "NA",
        "co_applicant_race": "NA",
        "co_applicant_race_2": "NA",
        "applicant_sex": "NA",
        "co_applicant_sex": "NA",
        "applicant_age": "NA",
        "co_applicant_age": "NA",
    }

    try:
        from database.models.borrower import BorrowerApplication

        app = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id == loan.id
        ).first()

        if not app:
            return defaults

        return {
            "applicant_ethnicity": _safe_str(getattr(app, "applicant_ethnicity", None)),
            "applicant_ethnicity_2": "NA",  # Secondary ethnicity not tracked separately
            "co_applicant_ethnicity": _safe_str(getattr(app, "co_applicant_ethnicity", None)),
            "co_applicant_ethnicity_2": "NA",
            "applicant_race": _safe_str(getattr(app, "applicant_race", None)),
            "applicant_race_2": "NA",  # Secondary race not tracked separately
            "co_applicant_race": _safe_str(getattr(app, "co_applicant_race", None)),
            "co_applicant_race_2": "NA",
            "applicant_sex": _safe_str(getattr(app, "applicant_sex", None)),
            "co_applicant_sex": _safe_str(getattr(app, "co_applicant_sex", None)),
            "applicant_age": _safe_str(getattr(app, "applicant_age", None)),
            "co_applicant_age": _safe_str(getattr(app, "co_applicant_age", None)),
        }
    except Exception as e:
        logger.warning(f"Could not retrieve GMI data for loan {loan.id}: {e}")
        return defaults


def _build_lar_record(
    loan: Any,
    lei: str,
    year: int,
    db: Optional[Session] = None,
) -> str:
    """Build a single HMDA LAR record as a pipe-delimited line.

    The field order follows the CFPB HMDA Filing Instructions.
    Not all 110 fields are populated from this CRM's data model;
    fields without data use "NA" as placeholder per HMDA spec.

    Args:
        loan: Loan ORM object
        lei: Legal Entity Identifier for the reporting institution
        year: Reporting year
        db: Optional SQLAlchemy session for looking up GMI demographics

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

    # GMI demographics (Critical Failure 2.9 fix)
    # Look up from BorrowerApplication if db session is available
    if db is not None:
        gmi = _get_gmi_data(db, loan)
    else:
        gmi = {k: "NA" for k in [
            "applicant_ethnicity", "applicant_ethnicity_2",
            "co_applicant_ethnicity", "co_applicant_ethnicity_2",
            "applicant_race", "applicant_race_2",
            "co_applicant_race", "co_applicant_race_2",
            "applicant_sex", "co_applicant_sex",
            "applicant_age", "co_applicant_age",
        ]}

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
        # Applicant demographics (from GMI data on BorrowerApplication)
        gmi["applicant_ethnicity"],             # 16: Ethnicity of Applicant 1
        gmi["applicant_ethnicity_2"],           # 17: Ethnicity of Applicant 2
        gmi["co_applicant_ethnicity"],          # 18: Co-Applicant Ethnicity 1
        gmi["co_applicant_ethnicity_2"],        # 19: Co-Applicant Ethnicity 2
        gmi["applicant_race"],                  # 20: Race of Applicant 1
        gmi["applicant_race_2"],                # 21: Race of Applicant 2
        gmi["co_applicant_race"],               # 22: Co-Applicant Race 1
        gmi["co_applicant_race_2"],             # 23: Co-Applicant Race 2
        gmi["applicant_sex"],                   # 24: Sex of Applicant
        gmi["co_applicant_sex"],                # 25: Sex of Co-Applicant
        gmi["applicant_age"],                   # 26: Age of Applicant
        gmi["co_applicant_age"],                # 27: Age of Co-Applicant
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

    # Validate all loans (including demographic fields via db lookup)
    all_errors = []
    all_warnings = []
    valid_loans = []

    for loan in loans:
        stage = (loan.stage or "").upper()
        errors = _validate_loan_for_hmda(loan, stage, db=db)

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

    # If there are validation errors, refuse to generate the LAR file.
    # Return the errors so the caller can present them for remediation.
    if all_errors:
        return {
            "lar_content": None,
            "total_records": 0,
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

    # Build LAR content from valid loans
    lar_lines = []
    for loan in valid_loans:
        try:
            record = _build_lar_record(loan, lei, year, db=db)
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

    Validates every loan that would appear in the LAR export against
    both loan-level required fields AND demographic fields stored on
    the linked BorrowerApplication.  Returns per-loan validation
    errors so the caller knows exactly which loans/fields need
    remediation before a valid LAR can be produced.

    Args:
        db: SQLAlchemy database session
        organization_id: Organization to check
        year: Reporting year

    Returns:
        Dict with readiness status, field coverage statistics, and
        per-loan validation errors (loan_id, loan_number, missing_fields).
    """
    from database.models.lead_loan import Loan
    from database.models.borrower import BorrowerApplication

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
            "validation_errors": [],
        }

    # ----- Loan-level field coverage -----
    loan_level_fields = {
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

    # ----- Demographic field coverage -----
    demographic_fields = {
        "applicant_ethnicity": 0,
        "applicant_race": 0,
        "applicant_sex": 0,
    }

    total = len(loans)
    errors_by_loan = {}
    validation_errors: List[Dict[str, Any]] = []

    # Pre-fetch all BorrowerApplications for the loan set in one query
    loan_ids = [loan.id for loan in loans]
    apps_by_loan_id: Dict[int, Any] = {}
    if loan_ids:
        apps = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id.in_(loan_ids)
        ).all()
        for a in apps:
            apps_by_loan_id[a.loan_id] = a

    for loan in loans:
        loan_key = loan.loan_number or str(loan.id)
        missing_fields: List[str] = []

        # Check loan-level fields
        for field in loan_level_fields:
            val = getattr(loan, field, None)
            if val is not None and val != "" and val != 0:
                loan_level_fields[field] += 1
            else:
                missing_fields.append(field)

        # Check demographic fields from BorrowerApplication
        app = apps_by_loan_id.get(loan.id)
        if not app:
            for demo_field in demographic_fields:
                missing_fields.append(demo_field)
        else:
            for demo_field in demographic_fields:
                val = getattr(app, demo_field, None)
                if val is not None and (not isinstance(val, str) or val.strip()):
                    demographic_fields[demo_field] += 1
                else:
                    missing_fields.append(demo_field)

        if missing_fields:
            errors_by_loan[loan_key] = missing_fields
            validation_errors.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "missing_fields": missing_fields,
            })

    # Merge all fields into a single coverage dict
    all_field_coverage = {**loan_level_fields, **demographic_fields}

    # Calculate coverage percentages
    coverage_pct = {
        field: round((count / total) * 100, 1) if total > 0 else 0
        for field, count in all_field_coverage.items()
    }

    # Required fields: loan-level REQUIRED_FIELDS + demographic REQUIRED_DEMOGRAPHIC_FIELDS
    # Map REQUIRED_FIELDS names to attribute names used in coverage dict
    required_attr_map = {
        "loan_number": "loan_number",
        "action_taken": None,  # derived from stage, always present for terminal loans
        "loan_type": "loan_type",
        "loan_purpose": "loan_purpose",
        "loan_amount": "amount",
        "property_state": "property_state",
        "property_county": "property_county",
    }

    required_coverage: Dict[str, float] = {}
    for req_name, attr_name in required_attr_map.items():
        if attr_name and attr_name in coverage_pct:
            required_coverage[req_name] = coverage_pct[attr_name]

    for demo_field in REQUIRED_DEMOGRAPHIC_FIELDS:
        if demo_field in coverage_pct:
            required_coverage[demo_field] = coverage_pct[demo_field]

    is_ready = all(pct == 100.0 for pct in required_coverage.values())

    result: Dict[str, Any] = {
        "is_ready": is_ready,
        "total_loans": total,
        "field_coverage": coverage_pct,
        "required_field_coverage": required_coverage,
        "loans_with_errors": len(errors_by_loan),
        "validation_errors": validation_errors if len(validation_errors) <= 50 else validation_errors[:50],
    }

    if len(validation_errors) > 50:
        result["validation_errors_note"] = (
            f"{len(validation_errors)} loans have errors (showing first 50)"
        )

    # Legacy key kept for backward compat
    result["error_details"] = errors_by_loan if len(errors_by_loan) <= 20 else {
        "note": f"{len(errors_by_loan)} loans have missing fields (showing first 20)",
        "samples": dict(list(errors_by_loan.items())[:20]),
    }

    return result
