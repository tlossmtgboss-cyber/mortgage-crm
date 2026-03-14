"""
Smart Docs Input Validators
============================
Specialized validators for the Smart Docs V2 system covering:

- ReDoS-safe regex pattern validation
- HTML sanitization (via nh3)
- Auto-review threshold pair validation
- DTI ratio constraints
- Filename sanitization (path traversal prevention)
- JSON payload size limits
- Loan amount and percentage range validation

These functions raise ``ValueError`` on invalid input so callers can
catch and translate to HTTP 400 responses.

Usage:
    from validation.smart_docs_validators import (
        validate_regex_safe,
        sanitize_html,
        validate_threshold_pair,
        validate_dti,
        sanitize_filename,
        validate_json_size,
        validate_loan_amount,
        validate_percentage,
        validate_phone,
        validate_email_safe,
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import threading
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# REGEX SAFETY (ReDoS Prevention)
# =============================================================================

# Patterns that indicate nested quantifiers — the primary cause of
# catastrophic backtracking.  We look for a quantifier (+, *, {m,n})
# applied to a group that itself contains a quantifier.
_NESTED_QUANTIFIER_RE = re.compile(
    r"""
    \(              # opening paren of a group
    [^)]*           # anything inside the group …
    [+*?]           # … that includes a quantifier
    [^)]*           # … possibly more
    \)              # closing paren
    [+*?{]          # followed by an outer quantifier
    """,
    re.VERBOSE,
)

# Alternation with quantifiers on both branches can also cause issues
_ALT_QUANTIFIER_RE = re.compile(
    r"""
    \(              # opening paren
    [^)]*           # inside group
    \|              # alternation
    [^)]*           # other branch
    \)              # close group
    [+*?{]          # outer quantifier
    """,
    re.VERBOSE,
)

# Maximum allowed regex pattern length
_MAX_REGEX_LENGTH = 200


def validate_regex_safe(pattern: str) -> bool:
    """Test whether a regex pattern is safe from catastrophic backtracking.

    Returns True if the pattern is safe, False if it is dangerous.
    Does NOT raise — callers should check the return value.

    Safety checks:
    1. Rejects patterns longer than 200 characters.
    2. Rejects patterns with nested quantifiers like ``(a+)+``.
    3. Rejects patterns with alternation under quantifiers like ``(a|b)*``.
    4. Attempts to compile the pattern with a 1-second timeout.
    """
    if not pattern or not isinstance(pattern, str):
        return False

    # 1. Length check
    if len(pattern) > _MAX_REGEX_LENGTH:
        logger.warning("Regex pattern rejected: exceeds %d chars (%d)", _MAX_REGEX_LENGTH, len(pattern))
        return False

    # 2. Nested quantifier check
    if _NESTED_QUANTIFIER_RE.search(pattern):
        logger.warning("Regex pattern rejected: nested quantifiers detected: %r", pattern[:80])
        return False

    # 3. Alternation with outer quantifier
    if _ALT_QUANTIFIER_RE.search(pattern):
        logger.warning("Regex pattern rejected: alternation under quantifier: %r", pattern[:80])
        return False

    # 4. Compilation check with timeout
    #    Use a thread with a timeout to prevent hangs during compilation.
    compile_error = [None]
    compile_success = [False]

    def _try_compile():
        try:
            re.compile(pattern)
            compile_success[0] = True
        except re.error as exc:
            compile_error[0] = str(exc)

    t = threading.Thread(target=_try_compile, daemon=True)
    t.start()
    t.join(timeout=1.0)

    if t.is_alive():
        logger.warning("Regex pattern rejected: compilation timed out: %r", pattern[:80])
        return False

    if compile_error[0]:
        logger.warning("Regex pattern rejected: compilation error: %s", compile_error[0])
        return False

    if not compile_success[0]:
        return False

    return True


# =============================================================================
# HTML SANITIZATION
# =============================================================================

def sanitize_html(text: str) -> str:
    """Strip all HTML tags from text using nh3.

    Falls back to a simple regex strip if nh3 is not installed.
    Returns plain text safe for embedding in HTML attributes or
    displaying in contexts where raw HTML is not expected.
    """
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)

    try:
        import nh3
        # Clean with no allowed tags → strips everything to plain text
        return nh3.clean(text, tags=set())
    except ImportError:
        # Fallback: regex-based tag stripping
        return re.sub(r"<[^>]+>", "", text)


# =============================================================================
# THRESHOLD PAIR VALIDATION
# =============================================================================

def validate_threshold_pair(
    approve_threshold: float,
    reject_threshold: float,
) -> None:
    """Validate that auto-review approve and reject thresholds form a valid pair.

    Rules:
    - Both must be in [0, 100].
    - approve_threshold must be strictly greater than reject_threshold.

    Raises:
        ValueError: With a descriptive message if the pair is invalid.
    """
    if not (0 <= approve_threshold <= 100):
        raise ValueError(
            f"Auto-approve threshold must be between 0 and 100, got {approve_threshold}"
        )
    if not (0 <= reject_threshold <= 100):
        raise ValueError(
            f"Auto-reject threshold must be between 0 and 100, got {reject_threshold}"
        )
    if reject_threshold >= approve_threshold:
        raise ValueError(
            "Auto-reject threshold must be lower than auto-approve threshold"
        )


# =============================================================================
# DTI VALIDATION
# =============================================================================

def validate_dti(value: float) -> float:
    """Validate a Debt-to-Income ratio value.

    DTI must be between 0 and 100 (inclusive).

    Returns:
        The validated float value.

    Raises:
        ValueError: If the value is outside [0, 100].
    """
    if value is None:
        raise ValueError("DTI value is required")
    val = float(value)
    if val < 0 or val > 100:
        raise ValueError(
            f"DTI ratio must be between 0 and 100, got {val}"
        )
    return val


# =============================================================================
# PHONE VALIDATION
# =============================================================================

_E164_RE = re.compile(r"^\+?[1-9]\d{1,14}$")


def validate_phone(phone: str) -> str:
    """Validate and normalize a phone number to E.164 format.

    Strips common formatting (spaces, dashes, parens, dots).
    Prepends +1 (US) if no country code is present.

    Returns:
        Normalized E.164 phone string.

    Raises:
        ValueError: If the phone number is invalid.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("Phone number is required")

    cleaned = re.sub(r"[\s\-().]+", "", phone.strip())
    if not cleaned.startswith("+"):
        cleaned = "+1" + cleaned

    if not _E164_RE.match(cleaned):
        raise ValueError(f"Invalid phone number format (expected E.164): {phone!r}")

    return cleaned


# =============================================================================
# EMAIL VALIDATION
# =============================================================================

_SAFE_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def validate_email_safe(email: str) -> str:
    """Validate an email address and strip dangerous characters.

    Returns:
        Lowercased, stripped email string.

    Raises:
        ValueError: If the email is missing or malformed.
    """
    if not email or not isinstance(email, str):
        raise ValueError("Email address is required")

    cleaned = email.strip().lower()

    # Remove null bytes and control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)

    if len(cleaned) > 254:
        raise ValueError("Email address exceeds maximum length (254 characters)")

    if not _SAFE_EMAIL_RE.match(cleaned):
        raise ValueError(f"Invalid email address format: {email!r}")

    if ".." in cleaned or cleaned.startswith(".") or cleaned.endswith("."):
        raise ValueError("Invalid email address format")

    return cleaned


# =============================================================================
# LOAN AMOUNT VALIDATION
# =============================================================================

_MAX_LOAN_AMOUNT = 50_000_000.0  # $50 million


def validate_loan_amount(amount: float) -> float:
    """Validate a loan amount.

    Must be positive and not exceed $50M.

    Returns:
        The validated float value.

    Raises:
        ValueError: If the amount is out of range.
    """
    if amount is None:
        raise ValueError("Loan amount is required")
    val = float(amount)
    if val <= 0:
        raise ValueError("Loan amount must be positive")
    if val > _MAX_LOAN_AMOUNT:
        raise ValueError(
            f"Loan amount must not exceed ${_MAX_LOAN_AMOUNT:,.0f}, got ${val:,.2f}"
        )
    return val


# =============================================================================
# PERCENTAGE VALIDATION
# =============================================================================

def validate_percentage(
    value: float,
    min_val: float = 0,
    max_val: float = 100,
) -> float:
    """Validate a percentage value is within a range.

    Returns:
        The validated float value.

    Raises:
        ValueError: If the value is outside [min_val, max_val].
    """
    if value is None:
        raise ValueError("Percentage value is required")
    val = float(value)
    if val < min_val or val > max_val:
        raise ValueError(
            f"Percentage must be between {min_val} and {max_val}, got {val}"
        )
    return val


# =============================================================================
# FILENAME SANITIZATION
# =============================================================================

# Characters allowed in sanitized filenames
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\- ]")

_MAX_FILENAME_LENGTH = 255


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and other attacks.

    - Strips directory components (path traversal).
    - Removes dangerous characters.
    - Limits length to 255 characters.
    - Replaces empty results with 'unnamed'.

    Returns:
        Sanitized filename string.
    """
    if not filename or not isinstance(filename, str):
        return "unnamed"

    # Remove null bytes
    name = filename.replace("\x00", "")

    # Strip absolute path prefixes (e.g., "C:\", "/")
    name = re.sub(r'^([a-zA-Z]:)?[\\/]+', '', name)

    # Remove path traversal sequences in a loop to defeat bypass
    # patterns like "....//", "....\\", "..../\" etc.
    prev = None
    while prev != name:
        prev = name
        name = name.replace("../", "").replace("..\\", "").replace("..", "")

    # Strip any remaining directory components
    name = os.path.basename(name)

    # Remove any leftover slashes/backslashes
    name = name.replace("/", "").replace("\\", "")

    # Remove dangerous characters
    name = _SAFE_FILENAME_RE.sub("", name)

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()

    # Limit length
    if len(name) > _MAX_FILENAME_LENGTH:
        # Preserve file extension when truncating
        base, ext = os.path.splitext(name)
        max_base = _MAX_FILENAME_LENGTH - len(ext)
        name = base[:max_base] + ext

    return name or "unnamed"


# =============================================================================
# JSON SIZE VALIDATION
# =============================================================================

_DEFAULT_MAX_JSON_BYTES = 1_048_576  # 1 MB


def validate_json_size(
    data: dict,
    max_bytes: int = _DEFAULT_MAX_JSON_BYTES,
) -> dict:
    """Validate that a JSON-serializable dict does not exceed a size limit.

    Serializes the data to JSON to measure its byte length. This prevents
    oversized payloads from consuming excessive memory or storage.

    Returns:
        The original dict if within limits.

    Raises:
        ValueError: If the serialized data exceeds max_bytes.
    """
    if data is None:
        return {}

    try:
        serialized = json.dumps(data, default=str)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Data is not JSON-serializable: {exc}") from exc

    size = len(serialized.encode("utf-8"))
    if size > max_bytes:
        raise ValueError(
            f"JSON payload too large: {size:,} bytes (max {max_bytes:,})"
        )

    return data
