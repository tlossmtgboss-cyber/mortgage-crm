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


def contains_ssn(text: str) -> bool:
    """Check if text contains an SSN pattern."""
    pattern = r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
    return bool(re.search(pattern, text))


def redact_ssn_from_text(text: str) -> str:
    """Replace SSN patterns in text with redacted version."""
    pattern = r'\b(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})\b'
    return re.sub(pattern, r'***-**-\3', text)


# Keys in step_data or nested dicts that must be scrubbed
_SSN_KEYS = {"ssn", "co_ssn", "full_ssn", "ssn_full", "social_security", "ssn_number"}
_ENCRYPTED_PLACEHOLDER = "***ENCRYPTED***"


def sanitize_step_data(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deep-scrub step_data dict to remove any raw SSN values.

    - Keys matching SSN field names are replaced with '***ENCRYPTED***'
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
        # If the key is a known SSN field and value is not already masked
        if key and key.lower() in _SSN_KEYS and value != _ENCRYPTED_PLACEHOLDER:
            return _ENCRYPTED_PLACEHOLDER
        # Check for SSN patterns in string values
        if contains_ssn(value):
            return redact_ssn_from_text(value)
        return value
    else:
        return value
