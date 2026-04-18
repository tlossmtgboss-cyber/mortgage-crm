"""
Phone Number Hashing Utilities

Provides consistent phone number normalization (E.164 format) and SHA-256
hashing for privacy-preserving lookups.  Plaintext phone columns are kept
for display; the hash columns enable indexed lookups without exposing PII.

Usage:
    from utils.phone_hash import normalize_phone, hash_phone

    normalized = normalize_phone("(843) 383-8956")   # "+18438838956"
    digest     = hash_phone("(843) 383-8956")         # "a1b2c3..." (64-char hex)
"""

import hashlib
import re


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US/CA).

    Rules:
      1. Strip everything except digits and a leading '+'.
      2. If the result is 10 digits, prepend '+1' (assume US/CA).
      3. If the result is 11 digits starting with '1', prepend '+'.
      4. Otherwise return '+' + digits (international numbers pass through).
      5. Return empty string for empty/None input.

    Examples:
        normalize_phone("(843) 383-8956")  -> "+18438838956"
        normalize_phone("+1-843-383-8956") -> "+18438838956"
        normalize_phone("8438838956")      -> "+18438838956"
        normalize_phone("18438838956")     -> "+18438838956"
        normalize_phone("")                -> ""
        normalize_phone(None)              -> ""
    """
    if not phone:
        return ""

    # Strip to digits only
    digits = re.sub(r"[^\d]", "", str(phone))

    if not digits:
        return ""

    # US/CA: 10 digits -> +1XXXXXXXXXX
    if len(digits) == 10:
        return f"+1{digits}"

    # US/CA: 11 digits starting with 1 -> +1XXXXXXXXXX
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"

    # International or other: prefix with + if not already
    return f"+{digits}"


def hash_phone(phone: str) -> str:
    """Normalize a phone number and return its SHA-256 hex digest.

    Returns empty string for empty/None input (no hash for missing data).
    The normalization step ensures that "(843) 383-8956", "+18438838956",
    and "843-383-8956" all produce the same hash.

    Args:
        phone: Raw phone number string in any common format.

    Returns:
        64-character lowercase hex SHA-256 digest, or "" if phone is empty.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return ""

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
