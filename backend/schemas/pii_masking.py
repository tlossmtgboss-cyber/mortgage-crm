"""
PII Masking for API Responses
Enterprise Readiness Check 3.19 - SSN must never appear in plaintext in API responses

Usage in Pydantic models:
    ssn_display: Optional[str] = None  # Will contain masked SSN like ***-**-1234

Usage for sanitizing dicts (e.g., step_data):
    from schemas.pii_masking import sanitize_step_data
    clean_data = sanitize_step_data(application.step_data)
"""
import re
from typing import Any, Dict, Optional


def mask_ssn(ssn: Optional[str]) -> Optional[str]:
    """Mask SSN to show only last 4 digits: ***-**-1234"""
    if not ssn:
        return None
    # Remove any formatting
    digits = re.sub(r'[^0-9]', '', str(ssn))
    if len(digits) >= 4:
        return f"***-**-{digits[-4:]}"
    return "***-**-****"


def mask_email(email: Optional[str]) -> Optional[str]:
    """Partially mask email: j***@example.com"""
    if not email or '@' not in email:
        return email
    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask phone to show only last 4 digits: (***) ***-1234"""
    if not phone:
        return None
    digits = re.sub(r'[^0-9]', '', str(phone))
    if len(digits) >= 4:
        return f"(***) ***-{digits[-4:]}"
    return "***-****"


def mask_dob(dob: Optional[str]) -> Optional[str]:
    """Mask date of birth to show year only.

    Handles common formats:
      - MM/DD/YYYY  -> **/**/YYYY
      - YYYY-MM-DD  -> YYYY-**-**
      - ISO datetime -> YYYY-**-**T...
    """
    if not dob:
        return None
    value = str(dob)
    if value.startswith("**"):
        return value
    # ISO format: 1990-05-14 or 1990-05-14T00:00:00
    iso_match = re.match(r'^(\d{4})-\d{2}-\d{2}(T.*)?$', value)
    if iso_match:
        suffix = iso_match.group(2) or ""
        return f"{iso_match.group(1)}-**-**{suffix}"
    # US format: 05/14/1990
    us_match = re.match(r'^\d{1,2}/\d{1,2}/(\d{4})$', value)
    if us_match:
        return f"**/**/{us_match.group(1)}"
    return value


def mask_tax_id(tax_id: Optional[str]) -> Optional[str]:
    """Mask tax ID (EIN/TIN) to show only last 4 digits: ***-**-1234"""
    if not tax_id:
        return None
    value = str(tax_id)
    if value.startswith("***"):
        return value
    digits = re.sub(r'[^0-9]', '', value)
    if len(digits) >= 4:
        return f"***-**-{digits[-4:]}"
    return "***-**-****"


def mask_account_number(account: Optional[str]) -> Optional[str]:
    """Mask bank account number to show only last 4 digits: ****5678"""
    if not account:
        return None
    value = str(account)
    if value.startswith("****"):
        return value
    digits = re.sub(r'[^0-9]', '', value)
    if len(digits) >= 4:
        return f"****{digits[-4:]}"
    return "********"


def contains_ssn(text: str) -> bool:
    """Check if text contains an SSN pattern."""
    pattern = r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
    return bool(re.search(pattern, text))


def redact_ssn_from_text(text: str) -> str:
    """Replace SSN patterns in text with redacted version."""
    pattern = r'\b(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})\b'
    return re.sub(pattern, r'***-**-\3', text)


# Keys in step_data or nested dicts that must be scrubbed
_SSN_KEYS = {"ssn", "co_ssn", "full_ssn", "ssn_full", "social_security", "ssn_number",
             "social_security_number", "ssn_encrypted", "co_ssn_encrypted"}
_TAX_ID_KEYS = {"tax_id", "tax_id_number", "tin", "ein", "fein", "employer_tax_id"}
_ACCOUNT_KEYS = {"bank_account_number", "account_number", "bank_account",
                 "checking_account", "savings_account", "routing_number"}
_DOB_KEYS = {"date_of_birth", "dob", "birth_date", "birthdate",
             "borrower_dob", "co_borrower_dob"}
_ENCRYPTED_PLACEHOLDER = "***ENCRYPTED***"


def sanitize_step_data(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deep-scrub step_data dict to remove any raw PII values.

    - Keys matching SSN/tax-id field names are replaced with masked values
    - Bank account numbers are masked to show last 4 digits
    - Date of birth values are masked to show year only
    - String values matching SSN regex patterns are redacted
    - Nested dicts and lists are processed recursively
    """
    if not data:
        return {}
    return _sanitize_value(data)


def _sanitize_value(value: Any, key: Optional[str] = None) -> Any:
    """Recursively sanitize a value, redacting PII."""
    if isinstance(value, dict):
        return {k: _sanitize_value(v, key=k) for k, v in value.items()}
    elif isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    elif isinstance(value, str):
        lower_key = key.lower() if key else None
        # SSN fields
        if lower_key and lower_key in _SSN_KEYS and value != _ENCRYPTED_PLACEHOLDER:
            return mask_ssn(value) or _ENCRYPTED_PLACEHOLDER
        # Tax ID fields
        if lower_key and lower_key in _TAX_ID_KEYS:
            return mask_tax_id(value) or _ENCRYPTED_PLACEHOLDER
        # Bank account fields
        if lower_key and lower_key in _ACCOUNT_KEYS:
            return mask_account_number(value) or "********"
        # DOB fields
        if lower_key and lower_key in _DOB_KEYS:
            return mask_dob(value) or value
        # Check for SSN patterns in string values
        if contains_ssn(value):
            return redact_ssn_from_text(value)
        return value
    else:
        return value
