"""
HMDA LAR Export Service

Provides CFPB-compliant HMDA Loan Application Register (LAR) export
capability for Domain 2 (Compliance).  Generates pipe-delimited LAR
file content per the CFPB 2018+ Filing Instructions Guide, validates
individual HMDA records for completeness, and produces summary
statistics for pre-export readiness checks.

Reference:
    CFPB HMDA Filing Instructions Guide (2018+)
    https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields
    12 CFR Part 1003 (Regulation C)

Functions:
    generate_hmda_lar(db, org_id, year) -> str
        Generate pipe-delimited LAR file content for a reporting year.

    validate_hmda_record(loan: dict) -> List[str]
        Validate a single record dict for HMDA field completeness.

    get_hmda_summary(db, org_id, year) -> dict
        Summary statistics: total reportable loans, valid/invalid counts,
        common missing fields.

Usage:
    from services.hmda_export_service import (
        generate_hmda_lar,
        validate_hmda_record,
        get_hmda_summary,
    )

    # Generate full LAR export
    lar_text = generate_hmda_lar(db, org_id=1, year=2026)

    # Validate a single record
    errors = validate_hmda_record({"loan_type": "FHA", "loan_amount": 250000, ...})

    # Get readiness summary
    summary = get_hmda_summary(db, org_id=1, year=2026)
"""

import logging
from collections import Counter
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# HMDA Code Mappings (CFPB 2018+ spec)
# ============================================================================

# Action Taken codes (HMDA spec field 11)
ACTION_TAKEN_MAP: Dict[str, str] = {
    "FUNDED": "1",              # 1 = Loan originated
    "APPROVED": "2",            # 2 = Application approved but not accepted
    "DENIED": "3",              # 3 = Application denied
    "WITHDRAWN": "4",           # 4 = Application withdrawn by applicant
    "CANCELLED": "5",           # 5 = File closed for incompleteness
    "DOES_NOT_QUALIFY": "3",    # Maps to denied
    "DEAD": "5",                # Maps to file closed
}

# Loan Type codes (HMDA spec field 5)
LOAN_TYPE_MAP: Dict[str, str] = {
    "conventional": "1",
    "Conventional": "1",
    "fha": "2",
    "FHA": "2",
    "va": "3",
    "VA": "3",
    "usda": "4",
    "USDA": "4",
    "rhs": "4",
    "RHS": "4",
}

# Loan Purpose codes (HMDA spec field 6)
LOAN_PURPOSE_MAP: Dict[str, str] = {
    "purchase": "1",
    "Purchase": "1",
    "home_improvement": "2",
    "Home Improvement": "2",
    "refinance": "31",
    "Refinance": "31",
    "cash_out": "32",
    "Cash Out": "32",
    "Cash-Out Refinance": "32",
    "other": "4",
    "Other": "4",
}

# Occupancy Type codes (HMDA spec field 9)
OCCUPANCY_MAP: Dict[str, str] = {
    "primary": "1",
    "Primary": "1",
    "primary_residence": "1",
    "second_home": "2",
    "Second Home": "2",
    "investment": "3",
    "Investment": "3",
}

# Construction Method codes (HMDA spec field 8)
CONSTRUCTION_MAP: Dict[str, str] = {
    "site_built": "1",
    "Site Built": "1",
    "single_family": "1",
    "Single Family": "1",
    "condo": "1",
    "Condo": "1",
    "townhouse": "1",
    "Townhouse": "1",
    "multi_family": "1",
    "Multi Family": "1",
    "manufactured": "2",
    "Manufactured": "2",
    "mobile": "2",
    "Mobile Home": "2",
}

# HMDA LAR field order (column positions in pipe-delimited output)
# Based on CFPB HMDA Filing Instructions Guide, 2018+ format.
LAR_FIELD_NAMES = [
    "record_identifier",          # 1:  Always "2" for LAR records
    "lei",                        # 2:  Legal Entity Identifier (20 chars)
    "uli",                        # 3:  Universal Loan Identifier
    "application_date",           # 4:  Application date (YYYYMMDD)
    "loan_type",                  # 5:  Loan type code
    "loan_purpose",               # 6:  Loan purpose code
    "preapproval",                # 7:  Preapproval (1=requested, 2=not requested)
    "construction_method",        # 8:  Construction method code
    "occupancy_type",             # 9:  Occupancy type code
    "loan_amount",                # 10: Loan amount (whole dollars)
    "action_taken",               # 11: Action taken code
    "action_taken_date",          # 12: Action taken date (YYYYMMDD)
    "state",                      # 13: State code
    "county",                     # 14: County code
    "census_tract",               # 15: Census tract
    "applicant_ethnicity_1",      # 16: Applicant ethnicity 1
    "applicant_ethnicity_2",      # 17: Applicant ethnicity 2
    "applicant_ethnicity_3",      # 18: Applicant ethnicity 3
    "applicant_ethnicity_4",      # 19: Applicant ethnicity 4
    "applicant_ethnicity_5",      # 20: Applicant ethnicity 5
    "co_applicant_ethnicity_1",   # 21: Co-applicant ethnicity 1
    "co_applicant_ethnicity_2",   # 22: Co-applicant ethnicity 2
    "co_applicant_ethnicity_3",   # 23: Co-applicant ethnicity 3
    "co_applicant_ethnicity_4",   # 24: Co-applicant ethnicity 4
    "co_applicant_ethnicity_5",   # 25: Co-applicant ethnicity 5
    "ethnicity_basis_applicant",  # 26: Ethnicity observed/not observed
    "ethnicity_basis_co",         # 27: Co-applicant ethnicity basis
    "applicant_race_1",           # 28: Applicant race 1
    "applicant_race_2",           # 29: Applicant race 2
    "applicant_race_3",           # 30: Applicant race 3
    "applicant_race_4",           # 31: Applicant race 4
    "applicant_race_5",           # 32: Applicant race 5
    "co_applicant_race_1",        # 33: Co-applicant race 1
    "co_applicant_race_2",        # 34: Co-applicant race 2
    "co_applicant_race_3",        # 35: Co-applicant race 3
    "co_applicant_race_4",        # 36: Co-applicant race 4
    "co_applicant_race_5",        # 37: Co-applicant race 5
    "race_basis_applicant",       # 38: Race observed/not observed
    "race_basis_co",              # 39: Co-applicant race basis
    "applicant_sex",              # 40: Applicant sex
    "co_applicant_sex",           # 41: Co-applicant sex
    "sex_basis_applicant",        # 42: Sex observed/not observed
    "sex_basis_co",               # 43: Co-applicant sex basis
    "applicant_age",              # 44: Applicant age
    "co_applicant_age",           # 45: Co-applicant age
    "income",                     # 46: Income (thousands)
    "purchaser_type",             # 47: Type of purchaser
    "rate_spread",                # 48: Rate spread
    "hoepa_status",               # 49: HOEPA status
    "lien_status",                # 50: Lien status
    "applicant_credit_score",     # 51: Applicant credit score
    "co_applicant_credit_score",  # 52: Co-applicant credit score
    "credit_score_model_applicant",   # 53: Credit score model
    "credit_score_model_co",          # 54: Co-applicant credit score model
    "denial_reason_1",            # 55: Denial reason 1
    "denial_reason_2",            # 56: Denial reason 2
    "denial_reason_3",            # 57: Denial reason 3
    "denial_reason_4",            # 58: Denial reason 4
    "total_loan_costs",           # 59: Total loan costs
    "total_points_and_fees",      # 60: Total points and fees
    "origination_charges",        # 61: Origination charges
    "discount_points",            # 62: Discount points
    "lender_credits",             # 63: Lender credits
    "interest_rate",              # 64: Interest rate
    "prepayment_penalty_term",    # 65: Prepayment penalty term
    "dti",                        # 66: DTI ratio
    "cltv",                       # 67: CLTV
    "loan_term",                  # 68: Loan term (months)
    "intro_rate_period",          # 69: Introductory rate period
    "balloon_payment",            # 70: Balloon payment flag
    "io_payment",                 # 71: Interest-only payment flag
    "negative_amortization",      # 72: Negative amortization flag
    "other_non_amortizing",       # 73: Other non-amortizing features
    "property_value",             # 74: Property value
    "manufactured_home_type",     # 75: Manufactured home type
    "manufactured_home_interest", # 76: Manufactured home land interest
    "total_units",                # 77: Total units
    "multifamily_units",          # 78: Multifamily affordable units
    "submission_of_application",  # 79: Submission of application
    "initially_payable",          # 80: Initially payable to institution
    "aus_1",                      # 81: AUS 1
    "aus_2",                      # 82: AUS 2
    "aus_3",                      # 83: AUS 3
    "aus_4",                      # 84: AUS 4
    "aus_5",                      # 85: AUS 5
    "aus_result_1",               # 86: AUS result 1
    "aus_result_2",               # 87: AUS result 2
    "aus_result_3",               # 88: AUS result 3
    "aus_result_4",               # 89: AUS result 4
    "aus_result_5",               # 90: AUS result 5
    "reverse_mortgage",           # 91: Reverse mortgage flag
    "open_end_line",              # 92: Open-end line of credit flag
    "business_or_commercial",     # 93: Business or commercial purpose flag
]

# Required fields for HMDA record validation (field name -> human label)
REQUIRED_HMDA_FIELDS: Dict[str, str] = {
    "lei": "Legal Entity Identifier",
    "loan_type": "Loan Type",
    "loan_purpose": "Loan Purpose",
    "loan_amount": "Loan Amount",
    "action_taken": "Action Taken",
    "action_taken_date": "Action Taken Date",
    "state": "Property State",
    "county": "Property County",
    "occupancy_type": "Occupancy Type",
    "applicant_ethnicity": "Applicant Ethnicity",
    "applicant_race": "Applicant Race",
    "applicant_sex": "Applicant Sex",
}

# Terminal loan stages that generate reportable HMDA records
TERMINAL_STAGES = frozenset(ACTION_TAKEN_MAP.keys())


# ============================================================================
# Formatting Helpers
# ============================================================================

def _safe(val: Any, default: str = "NA") -> str:
    """Safely convert a value to string for LAR output."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _format_date(dt: Any) -> str:
    """Format date as YYYYMMDD per HMDA spec."""
    if dt is None:
        return "NA"
    if isinstance(dt, datetime):
        dt = dt.date()
    if isinstance(dt, date):
        return dt.strftime("%Y%m%d")
    return "NA"


def _format_amount(amount: Any) -> str:
    """Format loan amount as whole-dollar integer string per HMDA spec."""
    if amount is None:
        return "NA"
    try:
        val = float(amount)
        if val <= 0:
            return "NA"
        return str(int(round(val)))
    except (TypeError, ValueError):
        return "NA"


def _format_rate(rate: Any) -> str:
    """Format interest rate with two decimal places per HMDA spec."""
    if rate is None:
        return "NA"
    try:
        return f"{float(rate):.2f}"
    except (TypeError, ValueError):
        return "NA"


def _map_code(value: Optional[str], mapping: Dict[str, str], default: str = "NA") -> str:
    """Map a string value to its HMDA code via a lookup dict."""
    if not value:
        return default
    # Try exact match first, then case-insensitive key search
    if value in mapping:
        return mapping[value]
    for key, code in mapping.items():
        if key.lower() == value.lower():
            return code
    # Fallback: try substring matching for common patterns
    vl = value.lower()
    if mapping is LOAN_TYPE_MAP:
        if "fha" in vl:
            return "2"
        if "va" in vl:
            return "3"
        if "usda" in vl or "rhs" in vl:
            return "4"
        return "1"  # Default to conventional
    if mapping is LOAN_PURPOSE_MAP:
        if "purchase" in vl:
            return "1"
        if "improvement" in vl:
            return "2"
        if "cash" in vl and "out" in vl:
            return "32"
        if "refi" in vl:
            return "31"
        return "4"  # Other
    return default


# ============================================================================
# Action Date & Code Resolution
# ============================================================================

def _resolve_action_date(loan) -> Optional[datetime]:
    """Determine the HMDA action-taken date for a Loan ORM object.

    Priority:
        1. funded_date (for originated loans)
        2. withdrawn_date (for withdrawn/denied)
        3. stage_changed_at (terminal stage transition)
        4. updated_at (last-resort fallback)
    """
    stage = (getattr(loan, "stage", "") or "").upper()

    if stage == "FUNDED" and getattr(loan, "funded_date", None):
        return loan.funded_date
    if stage in ("WITHDRAWN", "CANCELLED") and getattr(loan, "withdrawn_date", None):
        return loan.withdrawn_date
    if stage == "DENIED":
        # Denied loans may use withdrawn_date or stage_changed_at
        for attr in ("withdrawn_date", "stage_changed_at", "updated_at"):
            val = getattr(loan, attr, None)
            if val:
                return val

    # Fallback for any terminal stage
    if stage in TERMINAL_STAGES:
        for attr in ("stage_changed_at", "updated_at"):
            val = getattr(loan, attr, None)
            if val:
                return val

    return None


def _resolve_action_code(loan) -> str:
    """Map loan stage to HMDA Action Taken code.

    Codes:
        1 = Loan originated
        2 = Application approved but not accepted
        3 = Application denied
        4 = Application withdrawn by applicant
        5 = File closed for incompleteness
        6 = Purchased loan
    """
    stage = (getattr(loan, "stage", "") or "").upper()
    return ACTION_TAKEN_MAP.get(stage, "")


# ============================================================================
# Single-Record LAR Builder
# ============================================================================

def _build_lar_row(
    loan,
    lei: str,
    year: int,
    borrower_app=None,
) -> str:
    """Build a single pipe-delimited HMDA LAR row from a Loan ORM object.

    Produces all 93 fields per the CFPB 2018+ spec. Fields not available
    from the data model output "NA" or "Exempt" as appropriate.

    Args:
        loan: Loan SQLAlchemy model instance
        lei: Legal Entity Identifier for the reporting institution
        year: Reporting year
        borrower_app: Optional BorrowerApplication for demographic data

    Returns:
        Pipe-delimited string (one LAR record)
    """
    stage = (getattr(loan, "stage", "") or "").upper()

    # Core identifiers
    action_taken = ACTION_TAKEN_MAP.get(stage, "6")
    action_date = _resolve_action_date(loan)
    app_date = getattr(loan, "application_date", None)

    # Loan classification codes
    loan_type_code = _map_code(getattr(loan, "loan_type", None), LOAN_TYPE_MAP, "1")
    loan_purpose_code = _map_code(getattr(loan, "loan_purpose", None), LOAN_PURPOSE_MAP, "4")
    construction_code = _map_code(getattr(loan, "property_type", None), CONSTRUCTION_MAP, "1")
    occupancy_code = _map_code(getattr(loan, "occupancy_type", None), OCCUPANCY_MAP, "1")

    # Preapproval: 1=requested, 2=not requested
    preapproval = "1" if getattr(loan, "preapproval_date", None) else "2"

    # Demographics from BorrowerApplication
    app_ethnicity = "3"       # 3 = Information not provided
    co_app_ethnicity = "5"    # 5 = No co-applicant
    app_race = "7"            # 7 = Information not provided
    co_app_race = "8"         # 8 = No co-applicant
    app_sex = "4"             # 4 = Information not provided
    co_app_sex = "5"          # 5 = No co-applicant
    app_age = "8888"          # 8888 = Not applicable
    co_app_age = "8888"

    if borrower_app:
        if getattr(borrower_app, "applicant_ethnicity", None):
            app_ethnicity = _safe(borrower_app.applicant_ethnicity, "3")
        if getattr(borrower_app, "co_applicant_ethnicity", None):
            co_app_ethnicity = _safe(borrower_app.co_applicant_ethnicity, "5")
        if getattr(borrower_app, "applicant_race", None):
            app_race = _safe(borrower_app.applicant_race, "7")
        if getattr(borrower_app, "co_applicant_race", None):
            co_app_race = _safe(borrower_app.co_applicant_race, "8")
        if getattr(borrower_app, "applicant_sex", None):
            app_sex = _safe(borrower_app.applicant_sex, "4")
        if getattr(borrower_app, "co_applicant_sex", None):
            co_app_sex = _safe(borrower_app.co_applicant_sex, "5")
        if getattr(borrower_app, "applicant_age", None):
            app_age = _safe(borrower_app.applicant_age, "8888")
        if getattr(borrower_app, "co_applicant_age", None):
            co_app_age = _safe(borrower_app.co_applicant_age, "8888")

    # Property location
    prop_state = _safe(getattr(loan, "property_state", None))
    prop_county = _safe(getattr(loan, "property_county", None))
    prop_zip = _safe(getattr(loan, "property_zip", None))

    # Financial fields
    orig_charges = _format_amount(getattr(loan, "origination_fee", None))
    prop_value = _format_amount(getattr(loan, "purchase_price", None))
    points = _safe(getattr(loan, "points", None), "NA")
    loan_term = _safe(getattr(loan, "term", None), "360")

    # Build the 93-field LAR row
    # Fields with no data source output "NA" or "Exempt" per CFPB spec
    fields = [
        "2",                                        # 1:  Record Identifier (always "2" for LAR)
        _safe(lei, "NA"),                           # 2:  LEI
        _safe(getattr(loan, "loan_number", None)),  # 3:  Universal Loan Identifier (ULI)
        _format_date(app_date),                     # 4:  Application Date
        loan_type_code,                             # 5:  Loan Type
        loan_purpose_code,                          # 6:  Loan Purpose
        preapproval,                                # 7:  Preapproval
        construction_code,                          # 8:  Construction Method
        occupancy_code,                             # 9:  Occupancy Type
        _format_amount(getattr(loan, "amount", None)),  # 10: Loan Amount
        action_taken,                               # 11: Action Taken
        _format_date(action_date),                  # 12: Action Taken Date
        prop_state,                                 # 13: State
        prop_county,                                # 14: County
        "NA",                                       # 15: Census Tract (not stored)
        app_ethnicity,                              # 16: Applicant Ethnicity 1
        "NA",                                       # 17: Applicant Ethnicity 2
        "NA",                                       # 18: Applicant Ethnicity 3
        "NA",                                       # 19: Applicant Ethnicity 4
        "NA",                                       # 20: Applicant Ethnicity 5
        co_app_ethnicity,                           # 21: Co-Applicant Ethnicity 1
        "NA",                                       # 22: Co-Applicant Ethnicity 2
        "NA",                                       # 23: Co-Applicant Ethnicity 3
        "NA",                                       # 24: Co-Applicant Ethnicity 4
        "NA",                                       # 25: Co-Applicant Ethnicity 5
        "3",                                        # 26: Ethnicity Basis (3=not applicable)
        "3",                                        # 27: Co-Applicant Ethnicity Basis
        app_race,                                   # 28: Applicant Race 1
        "NA",                                       # 29: Applicant Race 2
        "NA",                                       # 30: Applicant Race 3
        "NA",                                       # 31: Applicant Race 4
        "NA",                                       # 32: Applicant Race 5
        co_app_race,                                # 33: Co-Applicant Race 1
        "NA",                                       # 34: Co-Applicant Race 2
        "NA",                                       # 35: Co-Applicant Race 3
        "NA",                                       # 36: Co-Applicant Race 4
        "NA",                                       # 37: Co-Applicant Race 5
        "3",                                        # 38: Race Basis (3=not applicable)
        "3",                                        # 39: Co-Applicant Race Basis
        app_sex,                                    # 40: Applicant Sex
        co_app_sex,                                 # 41: Co-Applicant Sex
        "3",                                        # 42: Sex Basis (3=not applicable)
        "3",                                        # 43: Co-Applicant Sex Basis
        app_age,                                    # 44: Applicant Age
        co_app_age,                                 # 45: Co-Applicant Age
        "NA",                                       # 46: Income (not on Loan model)
        "0",                                        # 47: Purchaser Type (0=not applicable)
        "NA",                                       # 48: Rate Spread (requires APOR calc)
        "3",                                        # 49: HOEPA Status (3=not applicable)
        "1",                                        # 50: Lien Status (1=first lien)
        "NA",                                       # 51: Applicant Credit Score
        "NA",                                       # 52: Co-Applicant Credit Score
        "9",                                        # 53: Credit Score Model (9=not applicable)
        "9",                                        # 54: Co-Applicant Credit Score Model
        "NA",                                       # 55: Denial Reason 1
        "NA",                                       # 56: Denial Reason 2
        "NA",                                       # 57: Denial Reason 3
        "NA",                                       # 58: Denial Reason 4
        "NA",                                       # 59: Total Loan Costs
        "NA",                                       # 60: Total Points and Fees
        orig_charges,                               # 61: Origination Charges
        points,                                     # 62: Discount Points
        "NA",                                       # 63: Lender Credits
        _format_rate(getattr(loan, "rate", None)),  # 64: Interest Rate
        "NA",                                       # 65: Prepayment Penalty Term
        "NA",                                       # 66: DTI Ratio
        _safe(getattr(loan, "cltv", None), "NA"),   # 67: CLTV
        loan_term,                                  # 68: Loan Term (months)
        "NA",                                       # 69: Introductory Rate Period
        "2",                                        # 70: Balloon Payment (2=no)
        "2",                                        # 71: Interest-Only Payment (2=no)
        "2",                                        # 72: Negative Amortization (2=no)
        "2",                                        # 73: Other Non-Amortizing (2=no)
        prop_value,                                 # 74: Property Value
        "3",                                        # 75: Manufactured Home Type (3=NA)
        "5",                                        # 76: Manufactured Home Interest (5=NA)
        _safe(getattr(loan, "property_units", None), "1"),  # 77: Total Units
        "NA",                                       # 78: Multifamily Affordable Units
        "1",                                        # 79: Submission of Application (1=direct)
        "1",                                        # 80: Initially Payable (1=yes)
        "NA",                                       # 81: AUS 1
        "NA",                                       # 82: AUS 2
        "NA",                                       # 83: AUS 3
        "NA",                                       # 84: AUS 4
        "NA",                                       # 85: AUS 5
        "NA",                                       # 86: AUS Result 1
        "NA",                                       # 87: AUS Result 2
        "NA",                                       # 88: AUS Result 3
        "NA",                                       # 89: AUS Result 4
        "NA",                                       # 90: AUS Result 5
        "2",                                        # 91: Reverse Mortgage (2=no)
        "2",                                        # 92: Open-End Line of Credit (2=no)
        "2",                                        # 93: Business/Commercial Purpose (2=no)
    ]

    return "|".join(fields)


# ============================================================================
# Public API: validate_hmda_record
# ============================================================================

def validate_hmda_record(loan: dict) -> List[str]:
    """Validate a single HMDA record dict for field completeness.

    Checks that all CFPB-required fields are present and non-empty.
    Fields that do not exist in the loan dict are reported as missing.
    Fields with empty/None values are reported as invalid.

    This function works on plain dicts so it can be used with both
    ORM objects (converted via ``vars(loan)`` or ``loan.__dict__``)
    and raw dict data from API payloads or imports.

    Args:
        loan: Dict of field name -> value.  Expected keys follow the
              Loan model attribute names:
              - loan_type, loan_purpose, amount (or loan_amount),
                property_state, property_county, occupancy_type,
                stage (or action_taken), funded_date/withdrawn_date
                (or action_taken_date), rate, property_type,
                applicant_ethnicity, applicant_race, applicant_sex

    Returns:
        List of human-readable error strings.  Empty list = valid record.
    """
    errors: List[str] = []

    def _present(key: str, alt_key: str = None) -> bool:
        """Check if a field is present and non-empty."""
        val = loan.get(key)
        if val is None and alt_key:
            val = loan.get(alt_key)
        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        if isinstance(val, (int, float)) and val == 0:
            return False
        return True

    # --- Required loan-level fields ---

    # LEI (Legal Entity Identifier)
    if not _present("lei"):
        errors.append("Missing LEI (Legal Entity Identifier)")

    # Loan/Application ID
    if not _present("loan_number") and not _present("uli"):
        errors.append("Missing loan number / Universal Loan Identifier (ULI)")

    # Loan type
    if not _present("loan_type"):
        errors.append("Missing loan type (Conventional, FHA, VA, USDA)")

    # Loan purpose
    if not _present("loan_purpose"):
        errors.append("Missing loan purpose (Purchase, Refinance, etc.)")

    # Loan amount
    if not _present("amount", "loan_amount"):
        errors.append("Missing or zero loan amount")

    # Action taken (derived from stage or explicit)
    has_action = _present("action_taken")
    if not has_action:
        stage = loan.get("stage", "")
        if isinstance(stage, str) and stage.upper() in TERMINAL_STAGES:
            has_action = True
    if not has_action:
        errors.append(
            "Missing action taken code. Loan must be in a terminal stage "
            "(FUNDED, DENIED, WITHDRAWN, CANCELLED) or have an explicit action_taken value"
        )

    # Action taken date
    has_date = _present("action_taken_date")
    if not has_date:
        # Check for stage-specific date fields
        for dt_field in ("funded_date", "withdrawn_date", "stage_changed_at"):
            if _present(dt_field):
                has_date = True
                break
    if not has_date:
        errors.append("Missing action taken date (funded_date, withdrawn_date, or stage_changed_at)")

    # Property location
    if not _present("property_state") and not _present("state"):
        errors.append("Missing property state")

    if not _present("property_county") and not _present("county"):
        errors.append("Missing property county (required for HMDA geocoding)")

    # Occupancy type
    if not _present("occupancy_type"):
        errors.append("Missing occupancy type (primary, second home, investment)")

    # --- Demographic fields (ECOA-required for HMDA) ---

    if not _present("applicant_ethnicity"):
        errors.append("Missing applicant ethnicity (HMDA demographic data)")

    if not _present("applicant_race"):
        errors.append("Missing applicant race (HMDA demographic data)")

    if not _present("applicant_sex"):
        errors.append("Missing applicant sex (HMDA demographic data)")

    return errors


# ============================================================================
# Public API: generate_hmda_lar
# ============================================================================

def generate_hmda_lar(
    db: Session,
    org_id: int,
    year: int,
    lei: str = "NA",
) -> str:
    """Generate pipe-delimited HMDA LAR file content per CFPB spec.

    Queries all loans for the organization in the given reporting year
    that have reached a terminal stage (funded, denied, withdrawn,
    cancelled), and produces one pipe-delimited row per loan application
    action in the CFPB 2018+ LAR format.

    Fields not available from the Loan model output "NA" or "Exempt".
    Demographic data (ethnicity, race, sex) is pulled from the linked
    BorrowerApplication record when available.

    Args:
        db: SQLAlchemy database session
        org_id: Organization ID to generate the LAR for
        year: HMDA reporting year (e.g., 2026)
        lei: 20-character Legal Entity Identifier.  Defaults to "NA"
             if the organization has not configured one.

    Returns:
        Pipe-delimited LAR text content (newline-separated rows).
        Returns empty string if no reportable loans exist.
    """
    from database.models.lead_loan import Loan
    from database.models.borrower import BorrowerApplication

    # Query all loans for the org
    loans = db.query(Loan).filter(
        Loan.organization_id == org_id,
    ).order_by(Loan.loan_number).all()

    if not loans:
        logger.info(f"HMDA LAR: No loans found for org {org_id}")
        return ""

    # Filter to reportable loans: terminal stage + action date in reporting year
    reportable: List = []
    for loan in loans:
        stage = (loan.stage or "").upper()
        if stage not in TERMINAL_STAGES:
            continue
        action_date = _resolve_action_date(loan)
        if action_date:
            ad = action_date.date() if isinstance(action_date, datetime) else action_date
            if ad.year == year:
                reportable.append(loan)

    if not reportable:
        logger.info(
            f"HMDA LAR: No reportable loans for org {org_id} in year {year} "
            f"(checked {len(loans)} total loans)"
        )
        return ""

    # Pre-fetch BorrowerApplications for all reportable loans in one query
    loan_ids = [loan.id for loan in reportable]
    apps_by_loan: Dict[int, Any] = {}
    if loan_ids:
        apps = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id.in_(loan_ids)
        ).all()
        for app in apps:
            apps_by_loan[app.loan_id] = app

    # Build LAR rows
    rows: List[str] = []
    for loan in reportable:
        try:
            borrower_app = apps_by_loan.get(loan.id)
            row = _build_lar_row(loan, lei, year, borrower_app)
            rows.append(row)
        except Exception as e:
            logger.error(f"HMDA LAR: Failed to build row for loan {loan.id}: {e}")

    logger.info(
        f"HMDA LAR: Generated {len(rows)} records for org {org_id}, year {year}"
    )

    return "\n".join(rows)


# ============================================================================
# Public API: get_hmda_summary
# ============================================================================

def get_hmda_summary(
    db: Session,
    org_id: int,
    year: int,
) -> dict:
    """Generate HMDA readiness summary statistics.

    Examines all reportable loans for the organization and year,
    validates each one against HMDA requirements, and returns
    aggregate statistics including valid/invalid counts and the
    most common missing fields.

    Args:
        db: SQLAlchemy database session
        org_id: Organization ID
        year: HMDA reporting year

    Returns:
        Dict with:
            - year: Reporting year
            - total_reportable: Count of loans in terminal stages for the year
            - valid_count: Loans passing all HMDA validation checks
            - invalid_count: Loans failing one or more checks
            - completeness_rate: Percentage of valid loans (0-100)
            - common_missing_fields: List of (field_name, count) tuples
                                     sorted by frequency (most common first)
            - invalid_loans: List of dicts with loan_id, loan_number,
                             and missing field names (capped at 100)
    """
    from database.models.lead_loan import Loan
    from database.models.borrower import BorrowerApplication

    # Fetch all loans for the org
    loans = db.query(Loan).filter(
        Loan.organization_id == org_id,
    ).order_by(Loan.loan_number).all()

    # Filter reportable loans
    reportable: List = []
    for loan in loans:
        stage = (loan.stage or "").upper()
        if stage not in TERMINAL_STAGES:
            continue
        action_date = _resolve_action_date(loan)
        if action_date:
            ad = action_date.date() if isinstance(action_date, datetime) else action_date
            if ad.year == year:
                reportable.append(loan)

    if not reportable:
        return {
            "year": year,
            "total_reportable": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "completeness_rate": 0.0,
            "common_missing_fields": [],
            "invalid_loans": [],
        }

    # Pre-fetch BorrowerApplications
    loan_ids = [loan.id for loan in reportable]
    apps_by_loan: Dict[int, Any] = {}
    if loan_ids:
        apps = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id.in_(loan_ids)
        ).all()
        for app in apps:
            apps_by_loan[app.loan_id] = app

    # Validate each loan
    valid_count = 0
    invalid_count = 0
    missing_counter: Counter = Counter()
    invalid_loans: List[dict] = []

    for loan in reportable:
        # Build a dict representation for validate_hmda_record
        record = _loan_to_hmda_dict(loan, apps_by_loan.get(loan.id))
        errors = validate_hmda_record(record)

        if not errors:
            valid_count += 1
        else:
            invalid_count += 1
            # Extract field names from error messages
            field_names = _extract_field_names_from_errors(errors)
            for field_name in field_names:
                missing_counter[field_name] += 1

            if len(invalid_loans) < 100:
                invalid_loans.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "errors": errors,
                    "missing_fields": field_names,
                })

    total = len(reportable)
    completeness_rate = round((valid_count / total) * 100, 1) if total > 0 else 0.0

    return {
        "year": year,
        "total_reportable": total,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "completeness_rate": completeness_rate,
        "common_missing_fields": missing_counter.most_common(20),
        "invalid_loans": invalid_loans,
    }


# ============================================================================
# Internal Helpers
# ============================================================================

def _loan_to_hmda_dict(loan, borrower_app=None) -> dict:
    """Convert a Loan ORM object (+ optional BorrowerApplication) to a
    flat dict suitable for validate_hmda_record().
    """
    record: Dict[str, Any] = {
        "loan_number": getattr(loan, "loan_number", None),
        "loan_type": getattr(loan, "loan_type", None),
        "loan_purpose": getattr(loan, "loan_purpose", None),
        "amount": getattr(loan, "amount", None),
        "rate": getattr(loan, "rate", None),
        "term": getattr(loan, "term", None),
        "stage": getattr(loan, "stage", None),
        "property_state": getattr(loan, "property_state", None),
        "property_county": getattr(loan, "property_county", None),
        "property_type": getattr(loan, "property_type", None),
        "occupancy_type": getattr(loan, "occupancy_type", None),
        "property_units": getattr(loan, "property_units", None),
        "funded_date": getattr(loan, "funded_date", None),
        "withdrawn_date": getattr(loan, "withdrawn_date", None),
        "stage_changed_at": getattr(loan, "stage_changed_at", None),
        "purchase_price": getattr(loan, "purchase_price", None),
        "origination_fee": getattr(loan, "origination_fee", None),
        "ltv": getattr(loan, "ltv", None),
        "cltv": getattr(loan, "cltv", None),
        "points": getattr(loan, "points", None),
    }

    # Organization LEI -- not stored on Loan, caller should set if available
    record["lei"] = None

    if borrower_app:
        record["applicant_ethnicity"] = getattr(borrower_app, "applicant_ethnicity", None)
        record["applicant_race"] = getattr(borrower_app, "applicant_race", None)
        record["applicant_sex"] = getattr(borrower_app, "applicant_sex", None)
        record["co_applicant_ethnicity"] = getattr(borrower_app, "co_applicant_ethnicity", None)
        record["co_applicant_race"] = getattr(borrower_app, "co_applicant_race", None)
        record["co_applicant_sex"] = getattr(borrower_app, "co_applicant_sex", None)
        record["applicant_age"] = getattr(borrower_app, "applicant_age", None)
        record["co_applicant_age"] = getattr(borrower_app, "co_applicant_age", None)

    return record


def _extract_field_names_from_errors(errors: List[str]) -> List[str]:
    """Extract standardized field names from validation error messages."""
    field_map = {
        "LEI": "lei",
        "loan number": "loan_number",
        "Universal Loan Identifier": "loan_number",
        "loan type": "loan_type",
        "loan purpose": "loan_purpose",
        "loan amount": "loan_amount",
        "action taken code": "action_taken",
        "action taken date": "action_taken_date",
        "property state": "property_state",
        "property county": "property_county",
        "occupancy type": "occupancy_type",
        "applicant ethnicity": "applicant_ethnicity",
        "applicant race": "applicant_race",
        "applicant sex": "applicant_sex",
    }
    fields = []
    for error in errors:
        error_lower = error.lower()
        for key, field_name in field_map.items():
            if key.lower() in error_lower:
                fields.append(field_name)
                break
        else:
            # Could not match -- use the full error as field name
            fields.append(error)
    return fields
