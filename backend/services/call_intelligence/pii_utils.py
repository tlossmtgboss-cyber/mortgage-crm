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


# =============================================================================
# SSN PATTERNS
# =============================================================================
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


# =============================================================================
# CREDIT CARD PATTERNS
# =============================================================================
# Matches major credit card formats (Visa, MC, Amex, Discover)
# Preserves last 4 digits for reference

CREDIT_CARD_PATTERN = re.compile(
    r'\b(?:'
    r'4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?(\d{4})|'  # Visa (starts with 4)
    r'5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?(\d{4})|'  # Mastercard (51-55)
    r'3[47]\d{2}[-\s]?\d{6}[-\s]?(\d{5})|'  # Amex (34, 37) - 15 digits
    r'6(?:011|5\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?(\d{4})'  # Discover
    r')\b'
)

CREDIT_CARD_REDACTED = "****-****-****-"


# =============================================================================
# BANK ACCOUNT PATTERNS
# =============================================================================
# Matches common bank account number formats (8-17 digits)
# Only matches when preceded by account-related keywords to avoid false positives

BANK_ACCOUNT_PATTERN = re.compile(
    r'(?:account|acct|routing|aba)[\s#:]*(\d{4,8})[-\s]?(\d{4,9})\b',
    re.IGNORECASE
)

BANK_ACCOUNT_REDACTED = "****"


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


def redact_credit_card(text: str) -> str:
    """
    Redact credit card numbers, preserving only last 4 digits.

    Args:
        text: Text that may contain credit card numbers

    Returns:
        Text with credit cards redacted to format "****-****-****-XXXX"

    Example:
        >>> redact_credit_card("Card is 4111-1111-1111-1234")
        "Card is ****-****-****-1234"
    """
    if not text:
        return text

    def replace_cc(match):
        # Find the last 4 digits from whichever group matched
        last_four = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        if last_four:
            return f"{CREDIT_CARD_REDACTED}{last_four}"
        return match.group(0)

    return CREDIT_CARD_PATTERN.sub(replace_cc, text)


def redact_bank_account(text: str) -> str:
    """
    Redact bank account numbers, preserving only last 4 digits.

    Args:
        text: Text that may contain bank account numbers

    Returns:
        Text with account numbers redacted

    Example:
        >>> redact_bank_account("Account 123456789")
        "Account ****6789"
    """
    if not text:
        return text

    def replace_account(match):
        # Preserve only last 4 digits
        full_number = match.group(1) + (match.group(2) or "")
        if len(full_number) >= 4:
            last_four = full_number[-4:]
            return f"account {BANK_ACCOUNT_REDACTED}{last_four}"
        return match.group(0)

    return BANK_ACCOUNT_PATTERN.sub(replace_account, text)


def mask_pii_for_logging(text: str) -> str:
    """
    Mask all PII in text for safe logging.

    This should be called before logging any text that might contain PII.
    Handles:
    - SSN (full 9-digit and variations)
    - Credit card numbers (Visa, MC, Amex, Discover)
    - Bank account numbers (when preceded by account-related keywords)

    Args:
        text: Text to mask

    Returns:
        Text with PII masked
    """
    if not text:
        return text

    # Apply all PII redaction in sequence
    masked = redact_ssn(text)
    masked = redact_credit_card(masked)
    masked = redact_bank_account(masked)

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
