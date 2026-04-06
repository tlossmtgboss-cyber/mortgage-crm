"""
Common Validation Utilities
============================
Reusable validators for sanitizing and validating user-supplied input
across the Mortgage CRM API.

These functions are intentionally dependency-free (no SQLAlchemy, no FastAPI)
so they can be used in any layer: routes, services, agents, or tests.

Usage examples:
    from validation.common import sanitize_string, validate_email_format

    name = sanitize_string(user_input, max_length=200)
    email = validate_email_format(user_input)       # raises ValueError if invalid
    phone = validate_phone_format(user_input)       # raises ValueError if invalid
    ssn = validate_ssn(user_input)                  # raises ValueError if invalid (NEVER logs SSN)
    amount = validate_loan_amount(user_input)       # raises ValueError if invalid -> Decimal
    score = validate_credit_score(user_input)       # raises ValueError if invalid -> int
    rate = validate_interest_rate(user_input)        # raises ValueError if invalid -> Decimal
    clean = sanitize_text(user_input, max_length=5000)  # strip HTML via nh3
    loan_num = validate_loan_number(user_input)     # raises ValueError if invalid
    uid = validate_uuid(user_input)                 # raises ValueError if invalid
    safe_col = safe_sql_identifier("column_name")   # raises ValueError if suspicious
"""

import re
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Set, Union

logger = logging.getLogger(__name__)


# =============================================================================
# COMPILED REGEX PATTERNS
# =============================================================================

# SQL identifier: letters, digits, underscores only. Must start with letter or underscore.
SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Email: RFC 5321-compatible subset (intentionally loose enough for real-world use)
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# E.164 phone: optional +, then 1-15 digits (ITU-T E.164 maximum)
_E164_RE = re.compile(r"^\+?[1-9]\d{1,14}$")

# Loan number: alphanumeric, dashes, dots, and underscores (covers all known formats)
_LOAN_NUMBER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-._]{0,49}$")

# UUID v4 (also accepts other UUID versions for flexibility)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# =============================================================================
# STRING SANITIZATION
# =============================================================================

def sanitize_string(value: Optional[str], max_length: int = 500) -> str:
    """Strip HTML tags, dangerous URL schemes, and null bytes from a string.

    Returns an empty string for None/empty input.  Always truncates to
    ``max_length`` characters.  This is a lightweight sanitizer intended
    for plain-text fields (names, titles, notes).  For rich HTML content
    use ``input_validation.sanitize_html`` instead.

    Args:
        value: The raw user-supplied string.
        max_length: Maximum allowed length (default 500).

    Returns:
        Cleaned, truncated string.
    """
    if not value:
        return ""

    if not isinstance(value, str):
        value = str(value)

    # Strip HTML tags (simple regex -- for full HTML use nh3 via input_validation.sanitize_html)
    cleaned = re.sub(r"<[^>]+>", "", value)

    # Remove dangerous URI schemes
    cleaned = re.sub(r"javascript\s*:", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"data\s*:", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"vbscript\s*:", "", cleaned, flags=re.IGNORECASE)

    # Remove null bytes
    cleaned = cleaned.replace("\x00", "")

    # Collapse excessive whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned[:max_length]


# =============================================================================
# FORMAT VALIDATORS (raise ValueError on invalid input)
# =============================================================================

def validate_email_format(value: Optional[str]) -> str:
    """Validate and normalize an email address.

    Returns the lowercased, stripped email if valid.

    Raises:
        ValueError: If the email is missing, too long, or malformed.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("Email address is required")

    email = value.strip().lower()

    if len(email) > 254:
        raise ValueError("Email address exceeds maximum length (254 characters)")

    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address format")

    # Reject obvious abuse patterns
    if ".." in email or email.startswith(".") or email.endswith("."):
        raise ValueError("Invalid email address format")

    return email


def validate_phone_format(value: Optional[str]) -> str:
    """Validate and normalize a phone number to E.164 format.

    Strips common formatting characters (spaces, dashes, parens, dots).
    Assumes US (+1) if no country code is present.

    Accepts: +1XXXXXXXXXX, 1XXXXXXXXXX, XXXXXXXXXX, (XXX) XXX-XXXX, XXX-XXX-XXXX
    Returns: +1XXXXXXXXXX format

    Returns:
        E.164-formatted phone string (e.g. ``+15551234567``).

    Raises:
        ValueError: If the phone number is missing or does not match E.164.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("Phone number is required")

    # Strip formatting
    phone = re.sub(r"[\s\-().]+", "", value.strip())

    # Handle leading +
    if phone.startswith("+"):
        digits = phone[1:]
    else:
        digits = phone

    # Must be all digits at this point
    if not digits.isdigit():
        raise ValueError("Invalid phone number: contains non-numeric characters")

    # Too short or too long
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError(
            "Invalid phone number: expected 10-15 digits "
            "(e.g., '(555) 123-4567' or '+15551234567')"
        )

    # Prepend US country code if 10 digits (no country code)
    if len(digits) == 10:
        digits = "1" + digits
    elif len(digits) == 11 and not digits.startswith("1"):
        # 11 digits but doesn't start with 1 — could be international
        pass

    return "+" + digits


def validate_loan_number(value: Optional[str]) -> str:
    """Validate a loan number.

    Allowed characters: letters, digits, dashes, dots, underscores.
    Must start with a letter or digit.  Maximum 50 characters.

    Returns:
        The stripped, validated loan number.

    Raises:
        ValueError: If the loan number is missing or malformed.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("Loan number is required")

    loan_num = value.strip()

    if not _LOAN_NUMBER_RE.match(loan_num):
        raise ValueError(
            "Invalid loan number format. Only letters, digits, dashes, "
            "dots, and underscores are allowed (max 50 characters)."
        )

    return loan_num


def validate_uuid(value: Optional[str]) -> str:
    """Validate a UUID string.

    Returns:
        The lowercased UUID string.

    Raises:
        ValueError: If the value is missing or not a valid UUID.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("UUID is required")

    uid = value.strip().lower()

    if not _UUID_RE.match(uid):
        raise ValueError("Invalid UUID format")

    return uid


# =============================================================================
# SSN VALIDATION
# =============================================================================

# Area numbers that are invalid per SSA rules
_SSN_INVALID_AREAS = {"000", "666"} | {str(n) for n in range(900, 1000)}


def validate_ssn(value: Optional[str]) -> str:
    """Validate SSN format and normalize to XXX-XX-XXXX.

    Accepts: XXXXXXXXX, XXX-XX-XXXX, XXX XX XXXX
    Returns: XXX-XX-XXXX format (normalized)

    Rejects:
    - All zeros in any group (000-xx-xxxx, xxx-00-xxxx, xxx-xx-0000)
    - Area numbers 000, 666, or 900-999
    - Non-numeric content after stripping separators
    - Wrong digit count

    SECURITY: This function NEVER logs or includes SSN values in error
    messages.  Error messages describe the format problem without revealing
    the input.

    Returns:
        Formatted SSN string (XXX-XX-XXXX).

    Raises:
        ValueError: If the SSN is missing or invalid.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("SSN is required")

    # Strip formatting: dashes, spaces
    digits = re.sub(r"[\s\-]", "", value.strip())

    # Must be exactly 9 digits
    if len(digits) != 9 or not digits.isdigit():
        raise ValueError("SSN must be exactly 9 digits")

    area = digits[:3]
    group = digits[3:5]
    serial = digits[5:]

    # Reject all-zero groups
    if area == "000":
        raise ValueError("Invalid SSN: area number cannot be 000")
    if group == "00":
        raise ValueError("Invalid SSN: group number cannot be 00")
    if serial == "0000":
        raise ValueError("Invalid SSN: serial number cannot be 0000")

    # Reject invalid area numbers (666, 900-999)
    if area in _SSN_INVALID_AREAS:
        raise ValueError("Invalid SSN: area number is not valid")

    return f"{area}-{group}-{serial}"


# =============================================================================
# LOAN AMOUNT VALIDATION (Decimal precision)
# =============================================================================

_MIN_LOAN_AMOUNT = Decimal("1000")
_MAX_LOAN_AMOUNT = Decimal("50000000")  # $50 million


def validate_loan_amount_decimal(amount: Union[str, int, float, Decimal, None]) -> Decimal:
    """Validate loan amount is reasonable and return as Decimal(18,2).

    Must be at least $1,000 and at most $50,000,000.

    Args:
        amount: Loan amount as string, int, float, or Decimal.

    Returns:
        Decimal value rounded to 2 decimal places.

    Raises:
        ValueError: If the amount is missing, non-numeric, or out of range.
    """
    if amount is None:
        raise ValueError("Loan amount is required")

    try:
        val = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Loan amount must be a valid number")

    if val != val:  # NaN check
        raise ValueError("Loan amount must be a valid number")

    if val < _MIN_LOAN_AMOUNT:
        raise ValueError(
            f"Loan amount must be at least ${_MIN_LOAN_AMOUNT:,.0f}, "
            f"got ${val:,.2f}"
        )

    if val > _MAX_LOAN_AMOUNT:
        raise ValueError(
            f"Loan amount must not exceed ${_MAX_LOAN_AMOUNT:,.0f}, "
            f"got ${val:,.2f}"
        )

    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =============================================================================
# CREDIT SCORE VALIDATION
# =============================================================================

_MIN_CREDIT_SCORE = 300
_MAX_CREDIT_SCORE = 850


def validate_credit_score(score: Union[str, int, float, None]) -> int:
    """Validate FICO credit score range (300-850).

    Args:
        score: Credit score as string, int, or float.

    Returns:
        Integer credit score.

    Raises:
        ValueError: If the score is missing, non-numeric, or out of range.
    """
    if score is None:
        raise ValueError("Credit score is required")

    try:
        val = int(float(str(score)))
    except (ValueError, TypeError):
        raise ValueError("Credit score must be a valid number")

    if val < _MIN_CREDIT_SCORE or val > _MAX_CREDIT_SCORE:
        raise ValueError(
            f"Credit score must be between {_MIN_CREDIT_SCORE} and "
            f"{_MAX_CREDIT_SCORE} (FICO range), got {val}"
        )

    return val


# =============================================================================
# INTEREST RATE VALIDATION
# =============================================================================

_MIN_RATE_DECIMAL = Decimal("0.001")   # 0.1%
_MAX_RATE_DECIMAL = Decimal("0.30")    # 30%


def validate_interest_rate(rate: Union[str, int, float, Decimal, None]) -> Decimal:
    """Validate and normalize interest rate to decimal form.

    Auto-detects whether the rate is expressed as a percentage (e.g., 5.5
    meaning 5.5%) or as a decimal (e.g., 0.055 meaning 5.5%).

    Heuristic: if rate > 1.0, treat it as a percentage and divide by 100.

    Valid range: 0.1% to 30% (0.001 to 0.30 in decimal form).

    Args:
        rate: Interest rate as string, int, float, or Decimal.

    Returns:
        Decimal rate in decimal form (e.g., 0.055 for 5.5%), rounded to
        4 decimal places.

    Raises:
        ValueError: If the rate is missing, non-numeric, or out of range.
    """
    if rate is None:
        raise ValueError("Interest rate is required")

    try:
        val = Decimal(str(rate))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Interest rate must be a valid number")

    if val != val:  # NaN check
        raise ValueError("Interest rate must be a valid number")

    if val <= 0:
        raise ValueError("Interest rate must be positive")

    # Auto-detect percentage vs decimal
    if val > Decimal("1.0"):
        # Looks like a percentage (e.g., 5.5 means 5.5%)
        val = val / Decimal("100")

    if val < _MIN_RATE_DECIMAL:
        raise ValueError(
            f"Interest rate must be at least 0.1% (0.001), got {val}"
        )

    if val > _MAX_RATE_DECIMAL:
        raise ValueError(
            f"Interest rate must not exceed 30% (0.30), got {val}"
        )

    return val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# =============================================================================
# TEXT SANITIZATION (nh3-based)
# =============================================================================


def sanitize_text(text: Optional[str], max_length: int = 10000) -> str:
    """Sanitize free text input: strip HTML via nh3, remove null bytes, truncate.

    Uses the ``nh3`` library (Rust-based HTML sanitizer) when available,
    falling back to regex-based tag stripping otherwise.

    Args:
        text: Raw user-supplied text (may contain HTML).
        max_length: Maximum allowed length after cleaning (default 10,000).

    Returns:
        Cleaned, truncated string.  Returns empty string for None/empty input.
    """
    if not text:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Remove null bytes first
    cleaned = text.replace("\x00", "")

    # Strip HTML using nh3
    try:
        import nh3
        cleaned = nh3.clean(cleaned, tags=set())
    except ImportError:
        # Fallback: regex-based tag stripping
        cleaned = re.sub(r"<[^>]+>", "", cleaned)

    # Remove dangerous URI schemes
    cleaned = re.sub(r"javascript\s*:", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"data\s*:", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"vbscript\s*:", "", cleaned, flags=re.IGNORECASE)

    # Strip control characters (except newlines and tabs)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

    # Truncate to max_length
    return cleaned[:max_length]


# =============================================================================
# SQL IDENTIFIER SAFETY
# =============================================================================

def safe_sql_identifier(name: str) -> str:
    """Validate and double-quote a SQL identifier (table or column name).

    Only allows ``[a-zA-Z_][a-zA-Z0-9_]*`` with a maximum length of 128
    characters.  Returns the name wrapped in double-quotes for safe
    interpolation into SQL text fragments.

    This is the canonical implementation -- use it instead of per-file copies
    of ``_safe_identifier``.

    Args:
        name: The raw identifier string.

    Returns:
        Double-quoted identifier safe for SQL interpolation, e.g. ``"loans"``.

    Raises:
        ValueError: If the name contains disallowed characters or exceeds
            128 characters.
    """
    if not name or not isinstance(name, str):
        raise ValueError("SQL identifier must be a non-empty string")

    if len(name) > 128:
        raise ValueError(f"SQL identifier too long ({len(name)} > 128): {name!r}")

    if not SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")

    return f'"{name}"'


def validate_column_names(columns: Set[str], allowed: Set[str]) -> Set[str]:
    """Filter column names to an allowed whitelist and validate each identifier.

    Returns the intersection of ``columns`` and ``allowed``, after verifying
    that every column name in the result passes ``safe_sql_identifier``.

    This is useful in dynamic INSERT/UPDATE builders where column names
    originate from field-mapping dictionaries.

    Args:
        columns: Column names to check (e.g. from ``dict.keys()``).
        allowed: Whitelist of permissible column names.

    Returns:
        Set of validated column names that appear in both sets.

    Raises:
        ValueError: If any column in the intersection fails identifier
            validation (should never happen with a correct whitelist, but
            provides defense-in-depth).
    """
    valid = columns & allowed
    for col in valid:
        safe_sql_identifier(col)  # raises on invalid
    return valid
