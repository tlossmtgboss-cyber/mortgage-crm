"""
PII Utilities for Call Intelligence

Provides secure handling of Personally Identifiable Information (PII)
such as Social Security Numbers (SSN).

SECURITY NOTES:
- Full SSNs should NEVER be stored, logged, or transmitted
- Only the last 4 digits may be stored for verification purposes
- All SSN redaction happens at the earliest possible point
- This module should be used anywhere PII might appear in text
"""

import re
from typing import Tuple, Optional


# SSN Patterns - designed to detect but NOT capture full SSN
# These patterns identify SSN locations without exposing the full number

# Pattern for full SSN format: XXX-XX-XXXX or XXX XX XXXX or XXXXXXXXX
SSN_FULL_PATTERN = re.compile(
    r'\b(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})\b'
)

# Pattern for partial SSN mentions (last 4 only)
SSN_LAST_FOUR_PATTERN = re.compile(
    r'(?:last\s*(?:four|4)|ssn|social(?:\s*security)?)\s*(?:is|:)?\s*(\d{4})\b',
    re.IGNORECASE
)

# Redaction placeholder
SSN_REDACTED = "***-**-"


def redact_ssn(text: str) -> str:
    """
    Redact all SSN occurrences in text, preserving only last 4 digits.

    Args:
        text: Text that may contain SSN

    Returns:
        Text with SSNs redacted to format "***-**-XXXX"

    Example:
        >>> redact_ssn("My SSN is 123-45-6789")
        "My SSN is ***-**-6789"
    """
    if not text:
        return text

    def replace_ssn(match):
        last_four = match.group(3)
        return f"{SSN_REDACTED}{last_four}"

    return SSN_FULL_PATTERN.sub(replace_ssn, text)


def extract_ssn_last_four(text: str) -> Tuple[Optional[str], bool]:
    """
    Safely extract last 4 digits of SSN from text.

    This function extracts the last 4 digits WITHOUT ever storing
    or returning the full SSN. It handles both:
    - Full SSN format (extracts last 4 only)
    - Partial SSN mentions ("last four is 1234")

    Args:
        text: Text that may contain SSN

    Returns:
        Tuple of (last_four_digits, was_full_ssn_detected)
        - last_four_digits: String of 4 digits or None if not found
        - was_full_ssn_detected: True if a full SSN was found (security alert)

    Example:
        >>> extract_ssn_last_four("My SSN is 123-45-6789")
        ("6789", True)
        >>> extract_ssn_last_four("Last four is 6789")
        ("6789", False)
    """
    if not text:
        return None, False

    # First, check for full SSN (security concern - we detect but don't capture full)
    full_match = SSN_FULL_PATTERN.search(text)
    if full_match:
        # Only extract the last 4 digits (group 3)
        last_four = full_match.group(3)
        return last_four, True

    # Check for partial SSN mentions (last 4 only)
    partial_match = SSN_LAST_FOUR_PATTERN.search(text)
    if partial_match:
        return partial_match.group(1), False

    # Check for standalone 4 digits after SSN context words
    context_pattern = re.compile(
        r'(?:social|ssn|social\s*security)\s*(?:number)?[^0-9]*(\d{4})\b',
        re.IGNORECASE
    )
    context_match = context_pattern.search(text)
    if context_match:
        return context_match.group(1), False

    return None, False


def contains_ssn(text: str) -> bool:
    """
    Check if text contains what appears to be a full SSN.

    Args:
        text: Text to check

    Returns:
        True if a full SSN pattern is detected
    """
    if not text:
        return False
    return bool(SSN_FULL_PATTERN.search(text))


def mask_pii_for_logging(text: str) -> str:
    """
    Mask all PII in text for safe logging.

    This should be called before logging any text that might contain PII.
    Currently handles:
    - SSN (full 9-digit and variations)

    Future enhancements could add:
    - Credit card numbers
    - Bank account numbers
    - Driver's license numbers

    Args:
        text: Text to mask

    Returns:
        Text with PII masked
    """
    if not text:
        return text

    # Redact SSNs
    masked = redact_ssn(text)

    return masked


def validate_ssn_last_four(value: str) -> bool:
    """
    Validate that a value is a valid SSN last 4 digits.

    Args:
        value: String to validate

    Returns:
        True if value is exactly 4 digits
    """
    if not value:
        return False
    return bool(re.match(r'^\d{4}$', str(value)))


def sanitize_source_text(text: str, max_length: int = 200) -> str:
    """
    Sanitize source text for storage in extraction results.

    - Redacts all PII
    - Truncates to max_length
    - Safe for logging and storage

    Args:
        text: Source text from transcript
        max_length: Maximum length of returned text

    Returns:
        Sanitized, truncated text
    """
    if not text:
        return ""

    # First redact all PII
    sanitized = mask_pii_for_logging(text)

    # Truncate if needed
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length - 3] + "..."

    return sanitized
