"""
PII Utilities for Call Intelligence

Provides secure handling of Personally Identifiable Information (PII)
such as Social Security Numbers (SSN).

SECURITY NOTES:
- Full SSNs should NEVER be stored, logged, or transmitted
- Only the last 4 digits may be stored for verification purposes
- All SSN redaction happens at the earliest possible point
- This module should be used anywhere PII might appear in text

IMPORTANT: redact_transcript_for_llm() MUST be called before sending
any transcript text to external LLM APIs (Anthropic, OpenAI, etc.)
"""

import re
import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


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
    r'(?:account|acct|routing|aba)[\s#:]*(?:number|num|no\.?)?[\s#:]*(\d{4,8})[-\s]?(\d{4,9})\b',
    re.IGNORECASE
)

BANK_ACCOUNT_REDACTED = "****"


# =============================================================================
# DATE OF BIRTH PATTERNS
# =============================================================================
# Matches common DOB formats in transcripts

# Written dates: "March 15, 1985", "03/15/1985", "1985-03-15"
DOB_WRITTEN_PATTERN = re.compile(
    r'(?:born|birthday|birth\s*date|date\s*of\s*birth|dob)[^0-9]*'
    r'('
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}|'
    r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|'
    r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'
    r')',
    re.IGNORECASE
)

# Numeric date formats anywhere (more aggressive)
DOB_NUMERIC_PATTERN = re.compile(
    r'\b(\d{1,2})[-/](\d{1,2})[-/](19\d{2}|20[0-2]\d)\b'
)

DOB_REDACTED = "[DOB REDACTED]"


# =============================================================================
# PHONE NUMBER PATTERNS
# =============================================================================
# Matches phone numbers in various formats

PHONE_PATTERN = re.compile(
    r'(?:'
    r'\+?1?[-.\s]?'  # Optional country code
    r')?'
    r'\(?([2-9]\d{2})\)?'  # Area code (2-9 start)
    r'[-.\s]?'
    r'(\d{3})'  # Exchange
    r'[-.\s]?'
    r'(\d{4})'  # Subscriber
    r'\b'
)

PHONE_REDACTED = "[PHONE]"


# =============================================================================
# EMAIL PATTERNS
# =============================================================================

EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

EMAIL_REDACTED = "[EMAIL]"


# =============================================================================
# ADDRESS PATTERNS (for full street addresses)
# =============================================================================

# Full street address pattern
ADDRESS_PATTERN = re.compile(
    r'\b(\d{1,5})\s+'
    r'((?:North|South|East|West|N\.?|S\.?|E\.?|W\.?)\s+)?'
    r'([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+'
    r'(Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|Way|Circle|Cir\.?|Place|Pl\.?)'
    r'(?:\s*(?:#|Apt\.?|Suite|Ste\.?|Unit)\s*\d+[A-Za-z]?)?',
    re.IGNORECASE
)

ADDRESS_REDACTED = "[ADDRESS]"


# =============================================================================
# SPOKEN NUMBER PATTERNS
# =============================================================================
# Patterns for numbers spoken as words in transcripts

SPOKEN_SSN_PATTERN = re.compile(
    r'(?:social|ssn|social\s*security)[^.]*?'
    r'(?:'
    r'(\b(?:zero|one|two|three|four|five|six|seven|eight|nine)\b[,\s]*){9,}'
    r')',
    re.IGNORECASE
)

# Common spoken number words
SPOKEN_NUMBERS = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'oh': '0', 'o': '0',
}


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


# =============================================================================
# ADDITIONAL REDACTION FUNCTIONS
# =============================================================================

def redact_dob(text: str) -> str:
    """
    Redact dates of birth from text.

    Args:
        text: Text that may contain DOB

    Returns:
        Text with DOB redacted

    Example:
        >>> redact_dob("I was born March 15, 1985")
        "I was born [DOB REDACTED]"
    """
    if not text:
        return text

    # First redact DOB with context words
    redacted = DOB_WRITTEN_PATTERN.sub(
        lambda m: m.group(0).replace(m.group(1), DOB_REDACTED) if m.group(1) else m.group(0),
        text
    )

    # Then redact standalone date patterns that look like birth dates (1950-2010 range)
    def replace_dob(match):
        year = int(match.group(3))
        # Only redact if year suggests a birth date (not a recent transaction date)
        if 1940 <= year <= 2010:
            return DOB_REDACTED
        return match.group(0)

    redacted = DOB_NUMERIC_PATTERN.sub(replace_dob, redacted)

    return redacted


def redact_phone(text: str) -> str:
    """
    Redact phone numbers from text.

    Args:
        text: Text that may contain phone numbers

    Returns:
        Text with phone numbers redacted

    Example:
        >>> redact_phone("Call me at 555-123-4567")
        "Call me at [PHONE]"
    """
    if not text:
        return text

    return PHONE_PATTERN.sub(PHONE_REDACTED, text)


def redact_email(text: str) -> str:
    """
    Redact email addresses from text.

    Args:
        text: Text that may contain email addresses

    Returns:
        Text with emails redacted

    Example:
        >>> redact_email("Email me at john@example.com")
        "Email me at [EMAIL]"
    """
    if not text:
        return text

    return EMAIL_PATTERN.sub(EMAIL_REDACTED, text)


def redact_address(text: str) -> str:
    """
    Redact full street addresses from text.

    Note: This is aggressive and may have false positives.
    Property addresses may need to be preserved in some contexts.

    Args:
        text: Text that may contain addresses

    Returns:
        Text with addresses redacted
    """
    if not text:
        return text

    return ADDRESS_PATTERN.sub(ADDRESS_REDACTED, text)


def redact_spoken_ssn(text: str) -> str:
    """
    Redact SSNs spoken as words (e.g., "one two three four five six seven eight nine").

    Args:
        text: Text that may contain spoken SSN

    Returns:
        Text with spoken SSN redacted
    """
    if not text:
        return text

    def replace_spoken(match):
        return match.group(0).split()[0] + " " + SSN_REDACTED + "XXXX"

    return SPOKEN_SSN_PATTERN.sub(replace_spoken, text)


# =============================================================================
# TRANSCRIPT REDACTION FOR LLM
# =============================================================================

def redact_transcript_for_llm(
    transcript: str,
    redact_addresses: bool = False,
    preserve_names: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    Redact PII from transcript before sending to external LLM APIs.

    IMPORTANT: This function MUST be called before sending any transcript
    to Anthropic, OpenAI, or other external LLM providers. This prevents
    sensitive borrower data from being transmitted to third parties.

    Redacts:
    - SSN (full and spoken as words)
    - Date of birth
    - Phone numbers
    - Email addresses
    - Credit card numbers
    - Bank account numbers
    - Optionally: Street addresses

    Does NOT redact (needed for extraction):
    - Names (needed for identity extraction)
    - Employer names
    - Property details (unless redact_addresses=True)

    Args:
        transcript: Raw transcript text
        redact_addresses: If True, also redact street addresses
        preserve_names: If True, preserve names (default for extraction)

    Returns:
        Tuple of (redacted_transcript, redaction_stats)
        - redacted_transcript: Safe for LLM transmission
        - redaction_stats: Dict with counts of each redaction type

    Example:
        >>> text = "My SSN is 123-45-6789 and I was born 03/15/1985"
        >>> redacted, stats = redact_transcript_for_llm(text)
        >>> print(redacted)
        "My SSN is ***-**-6789 and I was born [DOB REDACTED]"
        >>> print(stats)
        {"ssn": 1, "dob": 1, "phone": 0, ...}
    """
    if not transcript:
        return "", {"total": 0}

    stats = {
        "ssn": 0,
        "ssn_spoken": 0,
        "dob": 0,
        "phone": 0,
        "email": 0,
        "credit_card": 0,
        "bank_account": 0,
        "address": 0,
    }

    redacted = transcript

    # Count and redact SSN
    stats["ssn"] = len(SSN_FULL_PATTERN.findall(redacted))
    redacted = redact_ssn(redacted)

    # Count and redact spoken SSN
    stats["ssn_spoken"] = len(SPOKEN_SSN_PATTERN.findall(redacted))
    redacted = redact_spoken_ssn(redacted)

    # Count and redact DOB
    stats["dob"] = len(DOB_WRITTEN_PATTERN.findall(redacted)) + len(DOB_NUMERIC_PATTERN.findall(redacted))
    redacted = redact_dob(redacted)

    # Count and redact phone
    stats["phone"] = len(PHONE_PATTERN.findall(redacted))
    redacted = redact_phone(redacted)

    # Count and redact email
    stats["email"] = len(EMAIL_PATTERN.findall(redacted))
    redacted = redact_email(redacted)

    # Count and redact credit card
    stats["credit_card"] = len(CREDIT_CARD_PATTERN.findall(redacted))
    redacted = redact_credit_card(redacted)

    # Count and redact bank account
    stats["bank_account"] = len(BANK_ACCOUNT_PATTERN.findall(redacted))
    redacted = redact_bank_account(redacted)

    # Optionally redact addresses
    if redact_addresses:
        stats["address"] = len(ADDRESS_PATTERN.findall(redacted))
        redacted = redact_address(redacted)

    stats["total"] = sum(stats.values())

    if stats["total"] > 0:
        logger.info(
            f"Redacted {stats['total']} PII items from transcript: "
            f"SSN={stats['ssn']}, DOB={stats['dob']}, Phone={stats['phone']}, "
            f"Email={stats['email']}"
        )

        # Track PII redaction metrics
        try:
            from .metrics import track_pii_stats
            track_pii_stats(stats)
        except ImportError:
            pass  # Metrics module not available

    return redacted, stats


def get_redaction_warning_for_llm() -> str:
    """
    Get a warning message to include in LLM prompts about redacted content.

    This helps the LLM understand that some fields may show redaction placeholders
    instead of actual values.

    Returns:
        Warning text to append to extraction prompts
    """
    return """
NOTE: Some sensitive information has been redacted from this transcript for privacy:
- SSN appears as "***-**-XXXX" (last 4 preserved)
- Dates of birth appear as "[DOB REDACTED]"
- Phone numbers appear as "[PHONE]"
- Email addresses appear as "[EMAIL]"

When you see these placeholders, note that the information was present but redacted.
Set confidence to 50 for fields where you can only see a redaction placeholder.
"""
