"""
Smart Docs V2 Enterprise Field Mapping Service

Maps AI-extracted document fields to CRM lead/loan/custom fields with
configurable transforms, validations, and conflict resolution.

Supports:
- Built-in mappings for common mortgage document types
- Per-organization custom field definitions
- Transform pipelines (string, number, date, masking)
- Field-level validation rules
- Mapping preview and batch application
- Import/export of mapping configurations
- Mapping analytics (auto-fill success, correction rates)
- LOS integration mappings (Encompass, MISMO 3.6)
- Reverse mapping (CRM -> document pre-fill)

Usage:
    from services.smart_docs.enterprise.field_mapping_service import FieldMappingService

    service = FieldMappingService(db)
    result = await service.apply_mapping(org_id=1, source_type="DOCUMENT_EXTRACTION",
                                         source_data=extracted_fields, doc_type="PAYSTUB")
"""

import copy
import json
import logging
import re
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

__all__ = ["FieldMappingService"]


# =============================================================================
# ENUMS
# =============================================================================

class SourceType(str, Enum):
    DOCUMENT_EXTRACTION = "DOCUMENT_EXTRACTION"
    PLAID_DATA = "PLAID_DATA"
    AUS_RESPONSE = "AUS_RESPONSE"
    MISMO_IMPORT = "MISMO_IMPORT"
    MANUAL_ENTRY = "MANUAL_ENTRY"


class TargetType(str, Enum):
    LEAD_FIELD = "LEAD_FIELD"
    LOAN_FIELD = "LOAN_FIELD"
    CUSTOM_FIELD = "CUSTOM_FIELD"
    MISMO_FIELD = "MISMO_FIELD"
    LOS_FIELD = "LOS_FIELD"


class ConflictResolution(str, Enum):
    KEEP_EXISTING = "keep_existing"
    OVERWRITE = "overwrite"
    MANUAL_REVIEW = "manual_review"
    HIGHER_CONFIDENCE = "higher_confidence"


class FieldType(str, Enum):
    STRING = "STRING"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    CURRENCY = "CURRENCY"


# =============================================================================
# DATA CLASSES (plain dicts to avoid import complexity)
# =============================================================================

class MappingResult:
    """Result of applying a mapping to extracted data."""

    __slots__ = (
        "success", "mapped_fields", "skipped_fields", "validation_errors",
        "conflicts", "unmapped_source_fields", "mapping_id", "doc_type",
        "applied_count", "skipped_count", "error_count",
    )

    def __init__(self):
        self.success: bool = True
        self.mapped_fields: Dict[str, Any] = {}
        self.skipped_fields: List[Dict[str, Any]] = []
        self.validation_errors: List[Dict[str, Any]] = []
        self.conflicts: List[Dict[str, Any]] = []
        self.unmapped_source_fields: List[str] = []
        self.mapping_id: Optional[int] = None
        self.doc_type: Optional[str] = None
        self.applied_count: int = 0
        self.skipped_count: int = 0
        self.error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "mapped_fields": self.mapped_fields,
            "skipped_fields": self.skipped_fields,
            "validation_errors": self.validation_errors,
            "conflicts": self.conflicts,
            "unmapped_source_fields": self.unmapped_source_fields,
            "mapping_id": self.mapping_id,
            "doc_type": self.doc_type,
            "summary": {
                "applied": self.applied_count,
                "skipped": self.skipped_count,
                "errors": self.error_count,
            },
        }


class PreviewResult:
    """Result of previewing a mapping without applying it."""

    __slots__ = ("mapping_name", "preview_rows", "warnings", "coverage_pct")

    def __init__(self):
        self.mapping_name: str = ""
        self.preview_rows: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.coverage_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_name": self.mapping_name,
            "preview_rows": self.preview_rows,
            "warnings": self.warnings,
            "coverage_pct": self.coverage_pct,
        }


class MappingAnalytics:
    """Aggregate analytics for mapping performance."""

    __slots__ = (
        "total_mappings", "active_mappings", "total_applications",
        "auto_fill_rate", "correction_rate", "field_stats",
        "coverage_by_doc_type",
    )

    def __init__(self):
        self.total_mappings: int = 0
        self.active_mappings: int = 0
        self.total_applications: int = 0
        self.auto_fill_rate: float = 0.0
        self.correction_rate: float = 0.0
        self.field_stats: List[Dict[str, Any]] = []
        self.coverage_by_doc_type: Dict[str, float] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_mappings": self.total_mappings,
            "active_mappings": self.active_mappings,
            "total_applications": self.total_applications,
            "auto_fill_rate": self.auto_fill_rate,
            "correction_rate": self.correction_rate,
            "field_stats": self.field_stats,
            "coverage_by_doc_type": self.coverage_by_doc_type,
        }


class ImportResult:
    """Result of importing mapping configurations."""

    __slots__ = ("success", "imported_count", "skipped_count", "errors")

    def __init__(self):
        self.success: bool = True
        self.imported_count: int = 0
        self.skipped_count: int = 0
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "imported_count": self.imported_count,
            "skipped_count": self.skipped_count,
            "errors": self.errors,
        }


# =============================================================================
# TRANSFORM FUNCTIONS
# =============================================================================

_PHONE_PATTERN = re.compile(r"\D")
_SSN_PATTERN = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACCOUNT_MASK_KEEP = 4

# Date formats to try when parsing (most common first)
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]


def _transform_uppercase(value: Any) -> Any:
    """Convert string to uppercase."""
    if isinstance(value, str):
        return value.upper()
    return value


def _transform_lowercase(value: Any) -> Any:
    """Convert string to lowercase."""
    if isinstance(value, str):
        return value.lower()
    return value


def _transform_trim(value: Any) -> Any:
    """Strip leading/trailing whitespace."""
    if isinstance(value, str):
        return value.strip()
    return value


def _transform_titlecase(value: Any) -> Any:
    """Convert string to title case."""
    if isinstance(value, str):
        return value.title()
    return value


def _transform_to_decimal(value: Any) -> Optional[Decimal]:
    """Convert to Decimal, stripping currency symbols and commas."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
            if not cleaned:
                return None
            return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None
    return None


def _transform_round(value: Any, decimals: int = 2) -> Optional[float]:
    """Round numeric value to specified decimal places."""
    try:
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None


def _transform_abs(value: Any) -> Optional[float]:
    """Return absolute value."""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return None


def _transform_parse_date(value: Any) -> Optional[str]:
    """Parse date from various formats, return ISO format (YYYY-MM-DD)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if not isinstance(value, str):
        return None

    value_str = value.strip()
    if not value_str:
        return None

    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(value_str, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue

    # Try ISO parse as last resort
    try:
        parsed = datetime.fromisoformat(value_str.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except (ValueError, TypeError):
        return None


def _transform_format_date(value: Any, output_format: str = "%m/%d/%Y") -> Optional[str]:
    """Format a date value to a specific output format."""
    iso = _transform_parse_date(value)
    if iso is None:
        return None
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return dt.strftime(output_format)
    except ValueError:
        return None


def _transform_age_from_dob(value: Any) -> Optional[int]:
    """Calculate age from date of birth."""
    iso = _transform_parse_date(value)
    if iso is None:
        return None
    try:
        dob = datetime.strptime(iso, "%Y-%m-%d").date()
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except (ValueError, TypeError):
        return None


def _transform_mask_ssn(value: Any) -> Optional[str]:
    """Mask SSN to show only last 4 digits: ***-**-1234."""
    if value is None:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    if len(cleaned) < 4:
        return None
    return f"***-**-{cleaned[-4:]}"


def _transform_mask_account(value: Any) -> Optional[str]:
    """Mask account number, showing only last 4 digits."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) <= _ACCOUNT_MASK_KEEP:
        return s
    masked_len = len(s) - _ACCOUNT_MASK_KEEP
    return ("*" * masked_len) + s[-_ACCOUNT_MASK_KEEP:]


def _transform_format_phone(value: Any) -> Optional[str]:
    """Format phone number as (XXX) XXX-XXXX."""
    if value is None:
        return None
    digits = _PHONE_PATTERN.sub("", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return str(value)


# Transform registry
TRANSFORMS: Dict[str, Any] = {
    # String
    "uppercase": _transform_uppercase,
    "lowercase": _transform_lowercase,
    "trim": _transform_trim,
    "titlecase": _transform_titlecase,
    # Number
    "to_decimal": _transform_to_decimal,
    "round": _transform_round,
    "abs": _transform_abs,
    # Date
    "parse_date": _transform_parse_date,
    "format_date": _transform_format_date,
    "age_from_dob": _transform_age_from_dob,
    # Masking
    "mask_ssn": _transform_mask_ssn,
    "mask_account": _transform_mask_account,
    # Phone
    "format_phone": _transform_format_phone,
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_not_empty(value: Any) -> Tuple[bool, str]:
    """Validate that value is not empty/None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return False, "Value is empty"
    return True, ""


def _validate_ssn_format(value: Any) -> Tuple[bool, str]:
    """Validate SSN format (NNN-NN-NNNN or NNNNNNNNN)."""
    if value is None:
        return True, ""  # None is valid (field just not present)
    cleaned = re.sub(r"\D", "", str(value))
    if len(cleaned) != 9:
        return False, f"SSN must be 9 digits, got {len(cleaned)}"
    # Check for obviously invalid SSNs
    if cleaned.startswith("000") or cleaned.startswith("666") or cleaned.startswith("9"):
        return False, "Invalid SSN prefix"
    return True, ""


def _validate_phone_format(value: Any) -> Tuple[bool, str]:
    """Validate US phone number (10 digits)."""
    if value is None:
        return True, ""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return False, f"Phone must be 10 digits, got {len(digits)}"
    return True, ""


def _validate_email_format(value: Any) -> Tuple[bool, str]:
    """Validate email format."""
    if value is None:
        return True, ""
    if not _EMAIL_PATTERN.match(str(value)):
        return False, "Invalid email format"
    return True, ""


def _validate_positive_number(value: Any) -> Tuple[bool, str]:
    """Validate that number is positive."""
    if value is None:
        return True, ""
    try:
        num = float(value)
        if num < 0:
            return False, f"Value must be positive, got {num}"
        return True, ""
    except (ValueError, TypeError):
        return False, f"Cannot parse as number: {value}"


VALIDATIONS: Dict[str, Any] = {
    "not_empty": _validate_not_empty,
    "ssn_format": _validate_ssn_format,
    "phone_format": _validate_phone_format,
    "email_format": _validate_email_format,
    "positive_number": _validate_positive_number,
}


# =============================================================================
# BUILT-IN MAPPING TEMPLATES
# =============================================================================

# Maps document extraction fields to Loan model columns
BUILTIN_PAYSTUB_TO_LOAN = {
    "mapping_name": "Paystub → Loan (Built-in)",
    "source_type": SourceType.DOCUMENT_EXTRACTION.value,
    "target_type": TargetType.LOAN_FIELD.value,
    "doc_types": ["PAYSTUB"],
    "is_system": True,
    "mappings": [
        {
            "source_field": "employer_name",
            "target_field": "employer_name",
            "transform": "titlecase",
            "validation": "not_empty",
            "confidence_threshold": 60,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "gross_pay",
            "target_field": "monthly_income",
            "transform": "to_decimal",
            "validation": "positive_number",
            "confidence_threshold": 70,
            "conflict_resolution": "higher_confidence",
        },
        {
            "source_field": "ytd_gross",
            "target_field": "ytd_income",
            "transform": "to_decimal",
            "validation": "positive_number",
            "confidence_threshold": 70,
            "conflict_resolution": "overwrite",
        },
        {
            "source_field": "pay_frequency",
            "target_field": "pay_frequency",
            "transform": "uppercase",
            "validation": None,
            "confidence_threshold": 60,
            "conflict_resolution": "overwrite",
        },
        {
            "source_field": "hire_date",
            "target_field": "employment_start_date",
            "transform": "parse_date",
            "validation": None,
            "confidence_threshold": 60,
            "conflict_resolution": "keep_existing",
        },
    ],
}

BUILTIN_W2_TO_LOAN = {
    "mapping_name": "W-2 → Loan (Built-in)",
    "source_type": SourceType.DOCUMENT_EXTRACTION.value,
    "target_type": TargetType.LOAN_FIELD.value,
    "doc_types": ["W2"],
    "is_system": True,
    "mappings": [
        {
            "source_field": "wages_tips_compensation",
            "target_field": "annual_income",
            "transform": "to_decimal",
            "validation": "positive_number",
            "confidence_threshold": 80,
            "conflict_resolution": "higher_confidence",
        },
        {
            "source_field": "employer_name",
            "target_field": "employer_name",
            "transform": "titlecase",
            "validation": "not_empty",
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "employer_ein",
            "target_field": "employer_ein",
            "transform": "trim",
            "validation": None,
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "tax_year",
            "target_field": "income_tax_year",
            "transform": None,
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "overwrite",
        },
    ],
}

BUILTIN_BANK_STATEMENT_TO_LOAN = {
    "mapping_name": "Bank Statement → Loan (Built-in)",
    "source_type": SourceType.DOCUMENT_EXTRACTION.value,
    "target_type": TargetType.LOAN_FIELD.value,
    "doc_types": ["BANK_STATEMENT"],
    "is_system": True,
    "mappings": [
        {
            "source_field": "ending_balance",
            "target_field": "verified_assets",
            "transform": "to_decimal",
            "validation": "positive_number",
            "confidence_threshold": 80,
            "conflict_resolution": "overwrite",
        },
        {
            "source_field": "bank_name",
            "target_field": "depository_name",
            "transform": "titlecase",
            "validation": "not_empty",
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "account_type",
            "target_field": "account_type",
            "transform": "lowercase",
            "validation": None,
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "account_number_last4",
            "target_field": "account_last4",
            "transform": "mask_account",
            "validation": None,
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
    ],
}

BUILTIN_TAX_RETURN_TO_LOAN = {
    "mapping_name": "Tax Return → Loan (Built-in)",
    "source_type": SourceType.DOCUMENT_EXTRACTION.value,
    "target_type": TargetType.LOAN_FIELD.value,
    "doc_types": ["TAX_RETURN"],
    "is_system": True,
    "mappings": [
        {
            "source_field": "adjusted_gross_income",
            "target_field": "annual_income",
            "transform": "to_decimal",
            "validation": "positive_number",
            "confidence_threshold": 85,
            "conflict_resolution": "higher_confidence",
        },
        {
            "source_field": "filing_status",
            "target_field": "filing_status",
            "transform": "lowercase",
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "overwrite",
        },
        {
            "source_field": "tax_year",
            "target_field": "income_tax_year",
            "transform": None,
            "validation": None,
            "confidence_threshold": 90,
            "conflict_resolution": "overwrite",
        },
        {
            "source_field": "total_income",
            "target_field": "total_income",
            "transform": "to_decimal",
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "overwrite",
        },
    ],
}

BUILTIN_DRIVERS_LICENSE_TO_LEAD = {
    "mapping_name": "Driver's License → Lead (Built-in)",
    "source_type": SourceType.DOCUMENT_EXTRACTION.value,
    "target_type": TargetType.LEAD_FIELD.value,
    "doc_types": ["DRIVERS_LICENSE"],
    "is_system": True,
    "mappings": [
        {
            "source_field": "first_name",
            "target_field": "first_name",
            "transform": "titlecase",
            "validation": "not_empty",
            "confidence_threshold": 80,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "last_name",
            "target_field": "last_name",
            "transform": "titlecase",
            "validation": "not_empty",
            "confidence_threshold": 80,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "address",
            "target_field": "property_address",
            "transform": "titlecase",
            "validation": None,
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "city",
            "target_field": "property_city",
            "transform": "titlecase",
            "validation": None,
            "confidence_threshold": 70,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "state",
            "target_field": "property_state",
            "transform": "uppercase",
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "zip_code",
            "target_field": "property_zip",
            "transform": "trim",
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "keep_existing",
        },
        {
            "source_field": "date_of_birth",
            "target_field": "date_of_birth",
            "transform": "parse_date",
            "validation": None,
            "confidence_threshold": 80,
            "conflict_resolution": "keep_existing",
        },
    ],
}

# All built-in mapping templates keyed by doc_type
BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "PAYSTUB": BUILTIN_PAYSTUB_TO_LOAN,
    "W2": BUILTIN_W2_TO_LOAN,
    "BANK_STATEMENT": BUILTIN_BANK_STATEMENT_TO_LOAN,
    "TAX_RETURN": BUILTIN_TAX_RETURN_TO_LOAN,
    "DRIVERS_LICENSE": BUILTIN_DRIVERS_LICENSE_TO_LEAD,
}


# =============================================================================
# LOS / MISMO FIELD MAPPING TEMPLATES
# =============================================================================

# Encompass canonical field IDs for common CRM fields
ENCOMPASS_FIELD_MAP: Dict[str, str] = {
    # Borrower
    "first_name": "4000",
    "last_name": "4002",
    "email": "1240",
    "phone": "66",
    "ssn": "65",
    "date_of_birth": "1402",
    # Employment
    "employer_name": "BE0115",
    "employer_ein": "FE0117",
    "employment_start_date": "FE0104",
    # Income
    "monthly_income": "736",
    "annual_income": "HMDA.X73",
    # Loan
    "loan_amount": "1109",
    "purchase_price": "136",
    "rate": "3",
    "term": "4",
    "loan_type": "1172",
    "loan_purpose": "19",
    "ltv": "353",
    "cltv": "976",
    "dti": "742",
    # Property
    "property_address": "11",
    "property_city": "12",
    "property_state": "14",
    "property_zip": "15",
    "property_type": "1041",
    "occupancy_type": "1811",
    "property_county": "13",
    # Assets
    "verified_assets": "VEND.X263",
    "depository_name": "URLA.X120",
}

# MISMO 3.6 field paths for common CRM fields
MISMO_FIELD_MAP: Dict[str, str] = {
    "first_name": "DEAL/PARTIES/PARTY/INDIVIDUAL/NAME/FirstName",
    "last_name": "DEAL/PARTIES/PARTY/INDIVIDUAL/NAME/LastName",
    "email": "DEAL/PARTIES/PARTY/INDIVIDUAL/CONTACT_POINTS/CONTACT_POINT/ContactPointEmailValue",
    "phone": "DEAL/PARTIES/PARTY/INDIVIDUAL/CONTACT_POINTS/CONTACT_POINT/ContactPointTelephoneValue",
    "employer_name": "DEAL/PARTIES/PARTY/ROLES/ROLE/BORROWER/EMPLOYERS/EMPLOYER/EmployerName",
    "annual_income": "DEAL/PARTIES/PARTY/ROLES/ROLE/BORROWER/CURRENT_INCOME/CurrentIncomeMonthlyTotalAmount",
    "loan_amount": "DEAL/LOANS/LOAN/LoanAmountType",
    "rate": "DEAL/LOANS/LOAN/NoteRatePercent",
    "loan_type": "DEAL/LOANS/LOAN/MortgageType",
    "property_address": "DEAL/COLLATERALS/COLLATERAL/SUBJECT_PROPERTY/ADDRESS/AddressLineText",
    "property_city": "DEAL/COLLATERALS/COLLATERAL/SUBJECT_PROPERTY/ADDRESS/CityName",
    "property_state": "DEAL/COLLATERALS/COLLATERAL/SUBJECT_PROPERTY/ADDRESS/StateCode",
    "property_zip": "DEAL/COLLATERALS/COLLATERAL/SUBJECT_PROPERTY/ADDRESS/PostalCode",
    "purchase_price": "DEAL/COLLATERALS/COLLATERAL/SUBJECT_PROPERTY/SALES_CONTRACTS/SALES_CONTRACT/SalesContractAmount",
    "verified_assets": "DEAL/ASSETS/ASSET/ASSET_DETAIL/AssetAmount",
}


# =============================================================================
# SERVICE
# =============================================================================

class FieldMappingService:
    """
    Enterprise field mapping service for Smart Docs V2.

    Provides configurable, per-organization field mapping between document
    extraction output and CRM entity fields (leads, loans, custom fields).
    All methods enforce organization_id isolation.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model_classes(self):
        """Lazy import to avoid circular dependency at module load time."""
        from database.models.doc_field_mapping import FieldMappingConfig, CustomField
        return FieldMappingConfig, CustomField

    def _apply_transform(self, value: Any, transform_name: Optional[str]) -> Any:
        """Apply a named transform function to a value."""
        if transform_name is None or value is None:
            return value
        transform_fn = TRANSFORMS.get(transform_name)
        if transform_fn is None:
            logger.warning("Unknown transform '%s', returning value as-is", transform_name)
            return value
        try:
            return transform_fn(value)
        except Exception as e:
            logger.warning("Transform '%s' failed on value '%s': %s", transform_name, value, e)
            return value

    def _apply_validation(self, value: Any, validation_name: Optional[str]) -> Tuple[bool, str]:
        """Apply a named validation function to a value."""
        if validation_name is None:
            return True, ""
        validate_fn = VALIDATIONS.get(validation_name)
        if validate_fn is None:
            logger.warning("Unknown validation '%s', skipping", validation_name)
            return True, ""
        try:
            return validate_fn(value)
        except Exception as e:
            logger.warning("Validation '%s' failed: %s", validation_name, e)
            return False, f"Validation error: {e}"

    def _resolve_conflict(
        self,
        rule: Dict[str, Any],
        new_value: Any,
        existing_value: Any,
        new_confidence: Optional[int] = None,
        existing_confidence: Optional[int] = None,
    ) -> Tuple[Any, str]:
        """
        Resolve a field conflict between new and existing values.

        Returns (resolved_value, resolution_reason).
        """
        resolution = rule.get("conflict_resolution", ConflictResolution.KEEP_EXISTING.value)

        if existing_value is None or (isinstance(existing_value, str) and not existing_value.strip()):
            return new_value, "target_empty"

        if resolution == ConflictResolution.OVERWRITE.value:
            return new_value, "overwrite"
        elif resolution == ConflictResolution.KEEP_EXISTING.value:
            return existing_value, "keep_existing"
        elif resolution == ConflictResolution.HIGHER_CONFIDENCE.value:
            new_conf = new_confidence or 0
            exist_conf = existing_confidence or 50  # default existing confidence
            if new_conf > exist_conf:
                return new_value, "higher_confidence_new"
            return existing_value, "higher_confidence_existing"
        elif resolution == ConflictResolution.MANUAL_REVIEW.value:
            return None, "manual_review"
        else:
            return existing_value, "unknown_resolution"

    def _find_mapping_config(
        self,
        org_id: int,
        source_type: str,
        doc_type: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Find the best matching FieldMappingConfig for the given parameters.

        Priority: org-specific active config > system config > built-in template.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        # Try org-specific mapping first
        query = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.source_type == source_type,
            FieldMappingConfig.is_active == True,  # noqa: E712
        )
        if doc_type:
            # Filter for mappings that include this doc_type in their doc_types JSON array
            query = query.filter(
                FieldMappingConfig.doc_types.op("@>")(json.dumps([doc_type]))
            )
        config = query.order_by(
            FieldMappingConfig.is_system.asc(),  # org-specific first
            FieldMappingConfig.version.desc(),
        ).first()

        return config

    def _get_builtin_mappings(self, doc_type: str) -> Optional[List[Dict[str, Any]]]:
        """Get built-in mapping rules for a doc type (fallback when no DB config exists)."""
        template = BUILTIN_TEMPLATES.get(doc_type)
        if template:
            return template.get("mappings", [])
        return None

    def _serialize_value(self, value: Any) -> Any:
        """Convert value to JSON-serializable form."""
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    # ------------------------------------------------------------------
    # Core mapping execution
    # ------------------------------------------------------------------

    async def apply_mapping(
        self,
        org_id: int,
        source_type: str,
        source_data: Dict[str, Any],
        doc_type: Optional[str] = None,
        confidence_scores: Optional[Dict[str, int]] = None,
        existing_values: Optional[Dict[str, Any]] = None,
    ) -> MappingResult:
        """
        Apply field mappings to extracted source data and produce target field updates.

        Args:
            org_id: Organization ID (tenant isolation).
            source_type: Source data type (DOCUMENT_EXTRACTION, PLAID_DATA, etc.).
            source_data: Dict of extracted field name -> value.
            doc_type: Document type for mapping selection (PAYSTUB, W2, etc.).
            confidence_scores: Optional per-field confidence scores from extraction.
            existing_values: Optional current values of target fields (for conflict resolution).

        Returns:
            MappingResult with mapped fields, skipped fields, and validation errors.
        """
        result = MappingResult()
        result.doc_type = doc_type
        confidence_scores = confidence_scores or {}
        existing_values = existing_values or {}

        # Find mapping config
        config = self._find_mapping_config(org_id, source_type, doc_type)
        mapping_rules: List[Dict[str, Any]]

        if config is not None:
            result.mapping_id = config.id
            mapping_rules = config.mappings or []
        else:
            # Fall back to built-in template
            mapping_rules = self._get_builtin_mappings(doc_type) if doc_type else None
            if mapping_rules is None:
                result.success = False
                result.unmapped_source_fields = list(source_data.keys())
                return result

        mapped_source_fields: set = set()

        for rule in mapping_rules:
            source_field = rule.get("source_field", "")
            target_field = rule.get("target_field", "")

            if not source_field or not target_field:
                continue

            # Check if source field is present
            if source_field not in source_data:
                result.skipped_fields.append({
                    "source_field": source_field,
                    "target_field": target_field,
                    "reason": "source_field_missing",
                })
                result.skipped_count += 1
                continue

            raw_value = source_data[source_field]
            mapped_source_fields.add(source_field)

            # Check confidence threshold
            threshold = rule.get("confidence_threshold", 0)
            field_confidence = confidence_scores.get(source_field, 100)
            if field_confidence < threshold:
                result.skipped_fields.append({
                    "source_field": source_field,
                    "target_field": target_field,
                    "reason": "below_confidence_threshold",
                    "confidence": field_confidence,
                    "threshold": threshold,
                })
                result.skipped_count += 1
                continue

            # Apply transform
            transform_name = rule.get("transform")
            transformed_value = self._apply_transform(raw_value, transform_name)

            # Apply validation
            validation_name = rule.get("validation")
            is_valid, validation_msg = self._apply_validation(transformed_value, validation_name)

            if not is_valid:
                result.validation_errors.append({
                    "source_field": source_field,
                    "target_field": target_field,
                    "value": self._serialize_value(raw_value),
                    "transformed_value": self._serialize_value(transformed_value),
                    "validation": validation_name,
                    "error": validation_msg,
                })
                result.error_count += 1
                continue

            # Resolve conflicts with existing values
            existing_val = existing_values.get(target_field)
            if existing_val is not None:
                resolved_value, resolution_reason = self._resolve_conflict(
                    rule,
                    transformed_value,
                    existing_val,
                    new_confidence=field_confidence,
                )
                if resolution_reason == "manual_review":
                    result.conflicts.append({
                        "target_field": target_field,
                        "existing_value": self._serialize_value(existing_val),
                        "new_value": self._serialize_value(transformed_value),
                        "source_field": source_field,
                        "confidence": field_confidence,
                    })
                    result.skipped_count += 1
                    continue
                elif resolution_reason in ("keep_existing", "higher_confidence_existing"):
                    result.skipped_fields.append({
                        "source_field": source_field,
                        "target_field": target_field,
                        "reason": resolution_reason,
                    })
                    result.skipped_count += 1
                    continue
                transformed_value = resolved_value

            # Store mapped value
            result.mapped_fields[target_field] = self._serialize_value(transformed_value)
            result.applied_count += 1

        # Track unmapped source fields
        result.unmapped_source_fields = [
            f for f in source_data.keys() if f not in mapped_source_fields
        ]

        return result

    async def preview_mapping(
        self,
        org_id: int,
        source_data: Dict[str, Any],
        mapping_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        confidence_scores: Optional[Dict[str, int]] = None,
    ) -> PreviewResult:
        """
        Preview mapping results without applying changes.

        Shows what each source field would map to, including transform output
        and any validation warnings.

        Args:
            org_id: Organization ID.
            source_data: Extracted field data.
            mapping_id: Specific mapping config to preview (optional).
            doc_type: Document type for automatic mapping selection.
            confidence_scores: Optional per-field confidence scores.

        Returns:
            PreviewResult with row-by-row preview of each mapping rule.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        preview = PreviewResult()
        confidence_scores = confidence_scores or {}

        # Get mapping rules
        mapping_rules: List[Dict[str, Any]]
        if mapping_id is not None:
            config = self.db.query(FieldMappingConfig).filter(
                FieldMappingConfig.id == mapping_id,
                FieldMappingConfig.organization_id == org_id,
            ).first()
            if config is None:
                preview.warnings.append(f"Mapping config {mapping_id} not found for org {org_id}")
                return preview
            preview.mapping_name = config.mapping_name
            mapping_rules = config.mappings or []
        elif doc_type:
            config = self._find_mapping_config(org_id, SourceType.DOCUMENT_EXTRACTION.value, doc_type)
            if config:
                preview.mapping_name = config.mapping_name
                mapping_rules = config.mappings or []
            else:
                mapping_rules = self._get_builtin_mappings(doc_type) or []
                preview.mapping_name = f"Built-in {doc_type} mapping"
        else:
            preview.warnings.append("No mapping_id or doc_type specified")
            return preview

        if not mapping_rules:
            preview.warnings.append("No mapping rules found")
            return preview

        matched_count = 0
        total_rules = len(mapping_rules)

        for rule in mapping_rules:
            source_field = rule.get("source_field", "")
            target_field = rule.get("target_field", "")
            raw_value = source_data.get(source_field)
            field_confidence = confidence_scores.get(source_field)

            row: Dict[str, Any] = {
                "source_field": source_field,
                "target_field": target_field,
                "raw_value": self._serialize_value(raw_value),
                "transform": rule.get("transform"),
                "validation": rule.get("validation"),
                "confidence": field_confidence,
                "confidence_threshold": rule.get("confidence_threshold", 0),
                "conflict_resolution": rule.get("conflict_resolution", "keep_existing"),
                "status": "pending",
                "transformed_value": None,
                "validation_result": None,
            }

            if raw_value is None:
                row["status"] = "no_source_value"
            else:
                matched_count += 1
                # Apply transform
                transformed = self._apply_transform(raw_value, rule.get("transform"))
                row["transformed_value"] = self._serialize_value(transformed)

                # Check confidence
                threshold = rule.get("confidence_threshold", 0)
                if field_confidence is not None and field_confidence < threshold:
                    row["status"] = "below_confidence"
                else:
                    # Apply validation
                    is_valid, msg = self._apply_validation(transformed, rule.get("validation"))
                    row["validation_result"] = {"valid": is_valid, "message": msg}
                    row["status"] = "valid" if is_valid else "validation_failed"

            preview.preview_rows.append(row)

        preview.coverage_pct = round((matched_count / total_rules) * 100, 1) if total_rules > 0 else 0.0
        return preview

    async def apply_batch_mapping(
        self,
        org_id: int,
        source_type: str,
        documents: List[Dict[str, Any]],
        doc_type: Optional[str] = None,
    ) -> List[MappingResult]:
        """
        Apply mapping to multiple documents in batch.

        Args:
            org_id: Organization ID.
            source_type: Source data type.
            documents: List of dicts, each with 'source_data', optional 'confidence_scores'
                       and optional 'existing_values'.
            doc_type: Document type for mapping selection.

        Returns:
            List of MappingResult, one per document.
        """
        results: List[MappingResult] = []
        for doc in documents:
            result = await self.apply_mapping(
                org_id=org_id,
                source_type=source_type,
                source_data=doc.get("source_data", {}),
                doc_type=doc_type,
                confidence_scores=doc.get("confidence_scores"),
                existing_values=doc.get("existing_values"),
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Reverse mapping (CRM -> document pre-fill)
    # ------------------------------------------------------------------

    async def reverse_map(
        self,
        org_id: int,
        target_type: str,
        entity_data: Dict[str, Any],
        doc_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverse-map CRM entity data back to document extraction field names.

        Useful for pre-filling document templates with existing CRM data.

        Args:
            org_id: Organization ID.
            target_type: CRM target type (LEAD_FIELD, LOAN_FIELD).
            entity_data: Current entity field values.
            doc_type: Document type to determine which mapping to reverse.

        Returns:
            Dict mapping extraction field names to values from the CRM entity.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        reversed_data: Dict[str, Any] = {}

        # Find applicable mapping config
        config = self._find_mapping_config(
            org_id, SourceType.DOCUMENT_EXTRACTION.value, doc_type
        )
        mapping_rules: List[Dict[str, Any]]
        if config is not None:
            mapping_rules = config.mappings or []
        elif doc_type:
            mapping_rules = self._get_builtin_mappings(doc_type) or []
        else:
            return reversed_data

        for rule in mapping_rules:
            target_field = rule.get("target_field", "")
            source_field = rule.get("source_field", "")
            if target_field in entity_data and entity_data[target_field] is not None:
                reversed_data[source_field] = self._serialize_value(entity_data[target_field])

        return reversed_data

    # ------------------------------------------------------------------
    # Custom field CRUD
    # ------------------------------------------------------------------

    async def create_custom_field(
        self,
        org_id: int,
        field_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new custom field definition for an organization.

        Args:
            org_id: Organization ID.
            field_config: Dict with field_name, display_name, field_type, entity_type,
                          and optional enum_values, is_required, validation_rules,
                          default_value, is_searchable, sort_order.

        Returns:
            Dict representation of the created CustomField.
        """
        _, CustomField = self._get_model_classes()

        # Validate required params
        field_name = field_config.get("field_name", "").strip()
        display_name = field_config.get("display_name", "").strip()
        field_type = field_config.get("field_type", "").upper()
        entity_type = field_config.get("entity_type", "").upper()

        if not field_name:
            raise ValueError("field_name is required")
        if not display_name:
            raise ValueError("display_name is required")
        if field_type not in [ft.value for ft in FieldType]:
            raise ValueError(f"Invalid field_type: {field_type}. Must be one of {[ft.value for ft in FieldType]}")
        if entity_type not in ("LOAN", "LEAD", "DOCUMENT"):
            raise ValueError(f"Invalid entity_type: {entity_type}. Must be LOAN, LEAD, or DOCUMENT")

        # Validate uniqueness within org + entity_type
        existing = self.db.query(CustomField).filter(
            CustomField.organization_id == org_id,
            CustomField.entity_type == entity_type,
            CustomField.field_name == field_name,
            CustomField.is_active == True,  # noqa: E712
        ).first()
        if existing:
            raise ValueError(
                f"Custom field '{field_name}' already exists for {entity_type} in this organization"
            )

        # Validate enum_values if ENUM type
        enum_values = field_config.get("enum_values")
        if field_type == FieldType.ENUM.value:
            if not enum_values or not isinstance(enum_values, list) or len(enum_values) < 1:
                raise ValueError("ENUM field_type requires at least one enum_values entry")

        custom_field = CustomField(
            organization_id=org_id,
            field_name=field_name,
            display_name=display_name,
            field_type=field_type,
            entity_type=entity_type,
            enum_values=enum_values,
            is_required=field_config.get("is_required", False),
            validation_rules=field_config.get("validation_rules"),
            default_value=field_config.get("default_value"),
            is_searchable=field_config.get("is_searchable", True),
            sort_order=field_config.get("sort_order", 0),
            is_active=True,
        )
        self.db.add(custom_field)
        self.db.flush()

        return self._custom_field_to_dict(custom_field)

    async def get_custom_fields(
        self,
        org_id: int,
        entity_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get custom field definitions for an organization.

        Args:
            org_id: Organization ID.
            entity_type: Optional filter (LOAN, LEAD, DOCUMENT).
            include_inactive: Include soft-deleted fields.

        Returns:
            List of custom field dicts.
        """
        _, CustomField = self._get_model_classes()

        query = self.db.query(CustomField).filter(
            CustomField.organization_id == org_id,
        )
        if entity_type:
            query = query.filter(CustomField.entity_type == entity_type.upper())
        if not include_inactive:
            query = query.filter(CustomField.is_active == True)  # noqa: E712

        fields = query.order_by(CustomField.sort_order, CustomField.field_name).all()
        return [self._custom_field_to_dict(f) for f in fields]

    async def update_custom_field(
        self,
        org_id: int,
        field_id: int,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update a custom field definition.

        Args:
            org_id: Organization ID.
            field_id: Custom field ID.
            updates: Dict of fields to update (display_name, is_required,
                     validation_rules, default_value, is_searchable, sort_order,
                     enum_values, is_active).

        Returns:
            Updated custom field dict.
        """
        _, CustomField = self._get_model_classes()

        field = self.db.query(CustomField).filter(
            CustomField.id == field_id,
            CustomField.organization_id == org_id,
        ).first()
        if field is None:
            raise ValueError(f"Custom field {field_id} not found for org {org_id}")

        # Whitelist of updateable attributes
        updateable = {
            "display_name", "is_required", "validation_rules",
            "default_value", "is_searchable", "sort_order",
            "enum_values", "is_active",
        }
        for key, value in updates.items():
            if key in updateable:
                setattr(field, key, value)

        self.db.flush()
        return self._custom_field_to_dict(field)

    async def delete_custom_field(self, org_id: int, field_id: int) -> bool:
        """
        Soft-delete a custom field (set is_active=False).

        Args:
            org_id: Organization ID.
            field_id: Custom field ID.

        Returns:
            True if deleted.
        """
        _, CustomField = self._get_model_classes()

        field = self.db.query(CustomField).filter(
            CustomField.id == field_id,
            CustomField.organization_id == org_id,
        ).first()
        if field is None:
            raise ValueError(f"Custom field {field_id} not found for org {org_id}")

        field.is_active = False
        self.db.flush()
        return True

    def _custom_field_to_dict(self, field) -> Dict[str, Any]:
        """Serialize a CustomField model instance to dict."""
        return {
            "id": field.id,
            "organization_id": field.organization_id,
            "field_name": field.field_name,
            "display_name": field.display_name,
            "field_type": field.field_type,
            "entity_type": field.entity_type,
            "enum_values": field.enum_values,
            "is_required": field.is_required,
            "validation_rules": field.validation_rules,
            "default_value": field.default_value,
            "is_searchable": field.is_searchable,
            "sort_order": field.sort_order,
            "is_active": field.is_active,
            "created_at": field.created_at.isoformat() if field.created_at else None,
        }

    # ------------------------------------------------------------------
    # Mapping config CRUD
    # ------------------------------------------------------------------

    async def create_mapping_config(
        self,
        org_id: int,
        mapping_name: str,
        source_type: str,
        target_type: str,
        mappings: List[Dict[str, Any]],
        doc_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new field mapping configuration.

        Args:
            org_id: Organization ID.
            mapping_name: Human-readable mapping name.
            source_type: Source data type.
            target_type: Target field type.
            mappings: List of mapping rules.
            doc_types: Document types this mapping applies to.

        Returns:
            Dict representation of created FieldMappingConfig.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        # Validate source_type and target_type
        if source_type not in [st.value for st in SourceType]:
            raise ValueError(f"Invalid source_type: {source_type}")
        if target_type not in [tt.value for tt in TargetType]:
            raise ValueError(f"Invalid target_type: {target_type}")

        # Validate mapping rules
        self._validate_mapping_rules(mappings)

        config = FieldMappingConfig(
            organization_id=org_id,
            mapping_name=mapping_name,
            source_type=source_type,
            target_type=target_type,
            mappings=mappings,
            doc_types=doc_types,
            is_active=True,
            is_system=False,
            version=1,
        )
        self.db.add(config)
        self.db.flush()

        return self._mapping_config_to_dict(config)

    async def get_mapping_configs(
        self,
        org_id: int,
        source_type: Optional[str] = None,
        target_type: Optional[str] = None,
        include_system: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get mapping configurations for an organization.

        Args:
            org_id: Organization ID.
            source_type: Optional source type filter.
            target_type: Optional target type filter.
            include_system: Include system-provided mappings.

        Returns:
            List of mapping config dicts.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        query = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.is_active == True,  # noqa: E712
        )
        if source_type:
            query = query.filter(FieldMappingConfig.source_type == source_type)
        if target_type:
            query = query.filter(FieldMappingConfig.target_type == target_type)
        if not include_system:
            query = query.filter(FieldMappingConfig.is_system == False)  # noqa: E712

        configs = query.order_by(FieldMappingConfig.mapping_name).all()
        return [self._mapping_config_to_dict(c) for c in configs]

    async def update_mapping_config(
        self,
        org_id: int,
        mapping_id: int,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update a mapping configuration. Creates a new version.

        System mappings cannot be updated; instead, a copy is created
        as an org-specific override.

        Args:
            org_id: Organization ID.
            mapping_id: Mapping config ID.
            updates: Fields to update (mapping_name, mappings, doc_types, is_active).

        Returns:
            Updated mapping config dict.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        config = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.id == mapping_id,
            FieldMappingConfig.organization_id == org_id,
        ).first()
        if config is None:
            raise ValueError(f"Mapping config {mapping_id} not found for org {org_id}")

        if config.is_system:
            raise ValueError(
                "System mappings cannot be modified. Use create_mapping_config to create "
                "an org-specific override."
            )

        updateable = {"mapping_name", "mappings", "doc_types", "is_active"}
        for key, value in updates.items():
            if key in updateable:
                if key == "mappings":
                    self._validate_mapping_rules(value)
                setattr(config, key, value)

        config.version += 1
        config.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        return self._mapping_config_to_dict(config)

    async def delete_mapping_config(self, org_id: int, mapping_id: int) -> bool:
        """
        Soft-delete a mapping configuration (set is_active=False).

        System mappings cannot be deleted.

        Args:
            org_id: Organization ID.
            mapping_id: Mapping config ID.

        Returns:
            True if deleted.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        config = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.id == mapping_id,
            FieldMappingConfig.organization_id == org_id,
        ).first()
        if config is None:
            raise ValueError(f"Mapping config {mapping_id} not found for org {org_id}")
        if config.is_system:
            raise ValueError("System mappings cannot be deleted")

        config.is_active = False
        config.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return True

    def _mapping_config_to_dict(self, config) -> Dict[str, Any]:
        """Serialize a FieldMappingConfig to dict."""
        return {
            "id": config.id,
            "organization_id": config.organization_id,
            "mapping_name": config.mapping_name,
            "source_type": config.source_type,
            "target_type": config.target_type,
            "mappings": config.mappings,
            "doc_types": config.doc_types,
            "is_active": config.is_active,
            "is_system": config.is_system,
            "version": config.version,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def _validate_mapping_rules(self, rules: List[Dict[str, Any]]) -> None:
        """Validate a list of mapping rules."""
        if not isinstance(rules, list):
            raise ValueError("mappings must be a list")

        seen_targets: set = set()
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(f"Mapping rule at index {i} must be a dict")
            if not rule.get("source_field"):
                raise ValueError(f"Mapping rule at index {i} missing source_field")
            if not rule.get("target_field"):
                raise ValueError(f"Mapping rule at index {i} missing target_field")

            # Warn on duplicate target fields (not an error, but usually unintended)
            target = rule["target_field"]
            if target in seen_targets:
                logger.warning(
                    "Duplicate target_field '%s' in mapping rules at index %d", target, i
                )
            seen_targets.add(target)

            # Validate transform name if provided
            transform = rule.get("transform")
            if transform and transform not in TRANSFORMS:
                raise ValueError(
                    f"Unknown transform '{transform}' in rule at index {i}. "
                    f"Valid transforms: {list(TRANSFORMS.keys())}"
                )

            # Validate validation name if provided
            validation = rule.get("validation")
            if validation and validation not in VALIDATIONS:
                raise ValueError(
                    f"Unknown validation '{validation}' in rule at index {i}. "
                    f"Valid validations: {list(VALIDATIONS.keys())}"
                )

            # Validate conflict_resolution if provided
            cr = rule.get("conflict_resolution")
            valid_cr = {e.value for e in ConflictResolution}
            if cr and cr not in valid_cr:
                raise ValueError(
                    f"Unknown conflict_resolution '{cr}' in rule at index {i}. "
                    f"Valid options: {valid_cr}"
                )

    # ------------------------------------------------------------------
    # Mapping import / export
    # ------------------------------------------------------------------

    async def export_mappings(self, org_id: int) -> Dict[str, Any]:
        """
        Export all mapping configurations and custom fields for an organization.

        Returns a portable JSON-serializable dict that can be imported into another org.

        Args:
            org_id: Organization ID.

        Returns:
            Dict with 'mapping_configs' and 'custom_fields' keys.
        """
        configs = await self.get_mapping_configs(org_id, include_system=False)
        custom_fields = await self.get_custom_fields(org_id, include_inactive=False)

        # Strip org-specific IDs for portability
        exported_configs = []
        for cfg in configs:
            exported = {
                "mapping_name": cfg["mapping_name"],
                "source_type": cfg["source_type"],
                "target_type": cfg["target_type"],
                "mappings": cfg["mappings"],
                "doc_types": cfg["doc_types"],
                "version": cfg["version"],
            }
            exported_configs.append(exported)

        exported_fields = []
        for f in custom_fields:
            exported = {
                "field_name": f["field_name"],
                "display_name": f["display_name"],
                "field_type": f["field_type"],
                "entity_type": f["entity_type"],
                "enum_values": f["enum_values"],
                "is_required": f["is_required"],
                "validation_rules": f["validation_rules"],
                "default_value": f["default_value"],
                "is_searchable": f["is_searchable"],
                "sort_order": f["sort_order"],
            }
            exported_fields.append(exported)

        return {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_org_id": org_id,
            "mapping_configs": exported_configs,
            "custom_fields": exported_fields,
        }

    async def import_mappings(
        self,
        org_id: int,
        mapping_data: Dict[str, Any],
        overwrite_existing: bool = False,
    ) -> ImportResult:
        """
        Import mapping configurations and custom fields into an organization.

        Args:
            org_id: Target organization ID.
            mapping_data: Export dict from export_mappings().
            overwrite_existing: If True, deactivate existing mappings with the same name.

        Returns:
            ImportResult with counts and any errors.
        """
        FieldMappingConfig, CustomField = self._get_model_classes()
        result = ImportResult()

        # Import mapping configs
        for cfg in mapping_data.get("mapping_configs", []):
            try:
                mapping_name = cfg.get("mapping_name", "")

                # Check for existing mapping with same name
                if overwrite_existing:
                    existing = self.db.query(FieldMappingConfig).filter(
                        FieldMappingConfig.organization_id == org_id,
                        FieldMappingConfig.mapping_name == mapping_name,
                        FieldMappingConfig.is_system == False,  # noqa: E712
                        FieldMappingConfig.is_active == True,  # noqa: E712
                    ).first()
                    if existing:
                        existing.is_active = False
                        existing.updated_at = datetime.now(timezone.utc)

                await self.create_mapping_config(
                    org_id=org_id,
                    mapping_name=mapping_name,
                    source_type=cfg.get("source_type", SourceType.DOCUMENT_EXTRACTION.value),
                    target_type=cfg.get("target_type", TargetType.LOAN_FIELD.value),
                    mappings=cfg.get("mappings", []),
                    doc_types=cfg.get("doc_types"),
                )
                result.imported_count += 1
            except Exception as e:
                result.errors.append(f"Failed to import mapping '{cfg.get('mapping_name')}': {e}")
                result.skipped_count += 1

        # Import custom fields
        for field_cfg in mapping_data.get("custom_fields", []):
            try:
                await self.create_custom_field(org_id, field_cfg)
                result.imported_count += 1
            except ValueError as e:
                # Likely duplicate - skip
                if "already exists" in str(e):
                    result.skipped_count += 1
                else:
                    result.errors.append(f"Failed to import field '{field_cfg.get('field_name')}': {e}")
                    result.skipped_count += 1
            except Exception as e:
                result.errors.append(f"Failed to import field '{field_cfg.get('field_name')}': {e}")
                result.skipped_count += 1

        result.success = len(result.errors) == 0
        return result

    # ------------------------------------------------------------------
    # Mapping analytics
    # ------------------------------------------------------------------

    async def get_mapping_analytics(self, org_id: int) -> MappingAnalytics:
        """
        Get mapping analytics for an organization.

        Computes auto-fill success rate, correction rate, and per-field stats
        from the mapping_analytics_events table (if populated). Falls back to
        configuration-level stats when event data is unavailable.

        Args:
            org_id: Organization ID.

        Returns:
            MappingAnalytics with aggregate metrics.
        """
        FieldMappingConfig, CustomField = self._get_model_classes()

        analytics = MappingAnalytics()

        # Get mapping config counts
        total = self.db.query(func.count(FieldMappingConfig.id)).filter(
            FieldMappingConfig.organization_id == org_id,
        ).scalar() or 0
        active = self.db.query(func.count(FieldMappingConfig.id)).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.is_active == True,  # noqa: E712
        ).scalar() or 0

        analytics.total_mappings = total
        analytics.active_mappings = active

        # Compute per-doc-type coverage from active mappings
        configs = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.is_active == True,  # noqa: E712
        ).all()

        doc_type_rules: Dict[str, int] = {}
        all_field_stats: Dict[str, Dict[str, int]] = {}

        for config in configs:
            rules = config.mappings or []
            doc_types = config.doc_types or ["UNKNOWN"]

            for dt in doc_types:
                doc_type_rules[dt] = doc_type_rules.get(dt, 0) + len(rules)

            for rule in rules:
                target = rule.get("target_field", "")
                if target not in all_field_stats:
                    all_field_stats[target] = {"mapped_in_configs": 0}
                all_field_stats[target]["mapped_in_configs"] += 1

        # Estimate coverage as ratio of configured rules to known extraction fields
        # (using built-in templates as the baseline)
        for dt, rule_count in doc_type_rules.items():
            builtin = self._get_builtin_mappings(dt)
            builtin_count = len(builtin) if builtin else 5  # assume 5 if unknown
            coverage = min(100.0, round((rule_count / max(builtin_count, 1)) * 100, 1))
            analytics.coverage_by_doc_type[dt] = coverage

        analytics.field_stats = [
            {"target_field": field, **stats}
            for field, stats in sorted(all_field_stats.items())
        ]

        # Try to get event-level stats from the analytics table
        try:
            event_stats = self.db.execute(text("""
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(CASE WHEN was_auto_filled = true THEN 1 END) AS auto_filled,
                    COUNT(CASE WHEN was_manually_corrected = true THEN 1 END) AS corrected
                FROM smart_docs_mapping_analytics_events
                WHERE organization_id = :org_id
                  AND created_at >= CURRENT_DATE - INTERVAL '90 days'
            """), {"org_id": org_id}).fetchone()

            if event_stats and event_stats.total_events > 0:
                analytics.total_applications = event_stats.total_events
                analytics.auto_fill_rate = round(
                    (event_stats.auto_filled / event_stats.total_events) * 100, 1
                )
                analytics.correction_rate = round(
                    (event_stats.corrected / event_stats.total_events) * 100, 1
                )
        except Exception as _exc:  # noqa: BLE001
            # Table may not exist yet; analytics are best-effort
            logger.debug("Mapping analytics events table not available; skipping event stats")

        return analytics

    # ------------------------------------------------------------------
    # LOS integration helpers
    # ------------------------------------------------------------------

    async def get_encompass_field_map(self) -> Dict[str, str]:
        """
        Return the built-in CRM field -> Encompass field ID mapping.

        Returns:
            Dict mapping CRM field names to Encompass canonical field IDs.
        """
        return copy.deepcopy(ENCOMPASS_FIELD_MAP)

    async def get_mismo_field_map(self) -> Dict[str, str]:
        """
        Return the built-in CRM field -> MISMO 3.6 data point path mapping.

        Returns:
            Dict mapping CRM field names to MISMO 3.6 XPath-style paths.
        """
        return copy.deepcopy(MISMO_FIELD_MAP)

    async def map_to_encompass(
        self,
        org_id: int,
        crm_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Map CRM field values to Encompass field IDs.

        Uses the built-in ENCOMPASS_FIELD_MAP plus any org-specific LOS_FIELD
        mapping overrides.

        Args:
            org_id: Organization ID.
            crm_data: Dict of CRM field name -> value.

        Returns:
            Dict of Encompass field ID -> value.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        # Start with built-in map
        field_map = copy.deepcopy(ENCOMPASS_FIELD_MAP)

        # Apply org-specific LOS_FIELD overrides
        override = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.target_type == TargetType.LOS_FIELD.value,
            FieldMappingConfig.is_active == True,  # noqa: E712
        ).first()

        if override and override.mappings:
            for rule in override.mappings:
                src = rule.get("source_field", "")
                tgt = rule.get("target_field", "")
                if src and tgt:
                    field_map[src] = tgt

        # Map values
        encompass_data: Dict[str, Any] = {}
        for crm_field, value in crm_data.items():
            encompass_id = field_map.get(crm_field)
            if encompass_id and value is not None:
                encompass_data[encompass_id] = self._serialize_value(value)

        return encompass_data

    async def map_to_mismo(
        self,
        org_id: int,
        crm_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Map CRM field values to MISMO 3.6 data point paths.

        Args:
            org_id: Organization ID.
            crm_data: Dict of CRM field name -> value.

        Returns:
            Dict of MISMO path -> value.
        """
        FieldMappingConfig, _ = self._get_model_classes()

        field_map = copy.deepcopy(MISMO_FIELD_MAP)

        # Apply org-specific MISMO_FIELD overrides
        override = self.db.query(FieldMappingConfig).filter(
            FieldMappingConfig.organization_id == org_id,
            FieldMappingConfig.target_type == TargetType.MISMO_FIELD.value,
            FieldMappingConfig.is_active == True,  # noqa: E712
        ).first()

        if override and override.mappings:
            for rule in override.mappings:
                src = rule.get("source_field", "")
                tgt = rule.get("target_field", "")
                if src and tgt:
                    field_map[src] = tgt

        mismo_data: Dict[str, Any] = {}
        for crm_field, value in crm_data.items():
            mismo_path = field_map.get(crm_field)
            if mismo_path and value is not None:
                mismo_data[mismo_path] = self._serialize_value(value)

        return mismo_data

    # ------------------------------------------------------------------
    # Built-in template seeding
    # ------------------------------------------------------------------

    async def seed_builtin_mappings(self, org_id: int) -> int:
        """
        Seed built-in system mapping templates for an organization.

        Idempotent: skips templates that already exist for the org.

        Args:
            org_id: Organization ID.

        Returns:
            Number of templates created.
        """
        FieldMappingConfig, _ = self._get_model_classes()
        created = 0

        for doc_type, template in BUILTIN_TEMPLATES.items():
            existing = self.db.query(FieldMappingConfig).filter(
                FieldMappingConfig.organization_id == org_id,
                FieldMappingConfig.mapping_name == template["mapping_name"],
                FieldMappingConfig.is_system == True,  # noqa: E712
            ).first()

            if existing:
                continue

            config = FieldMappingConfig(
                organization_id=org_id,
                mapping_name=template["mapping_name"],
                source_type=template["source_type"],
                target_type=template["target_type"],
                mappings=template["mappings"],
                doc_types=template.get("doc_types"),
                is_active=True,
                is_system=True,
                version=1,
            )
            self.db.add(config)
            created += 1

        if created > 0:
            self.db.flush()

        return created

    # ------------------------------------------------------------------
    # Mapping LOS templates
    # ------------------------------------------------------------------

    def get_los_templates(self) -> Dict[str, Dict[str, str]]:
        """
        Return available LOS integration mapping templates.

        Returns:
            Dict keyed by LOS name with field ID mappings.
        """
        return {
            "encompass": copy.deepcopy(ENCOMPASS_FIELD_MAP),
            "mismo_3_6": copy.deepcopy(MISMO_FIELD_MAP),
        }
