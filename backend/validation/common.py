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
    loan_num = validate_loan_number(user_input)     # raises ValueError if invalid
    uid = validate_uuid(user_input)                 # raises ValueError if invalid
    safe_col = safe_sql_identifier("column_name")   # raises ValueError if suspicious
"""

import re
import logging
from typing import Optional, Set

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

    Returns:
        E.164-formatted phone string (e.g. ``+15551234567``).

    Raises:
        ValueError: If the phone number is missing or does not match E.164.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError("Phone number is required")

    # Strip formatting
    phone = re.sub(r"[\s\-().]+", "", value.strip())

    # Prepend US country code if missing
    if not phone.startswith("+"):
        phone = "+1" + phone

    if not _E164_RE.match(phone):
        raise ValueError("Invalid phone number format (expected E.164)")

    return phone


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
