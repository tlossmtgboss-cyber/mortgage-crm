"""
Shared validation helpers for the Perennia AI backend.

Usage:
    from utils.validators import validate_nmls

    # Returns cleaned NMLS string or raises ValueError
    cleaned = validate_nmls("  0012345  ")  # -> "12345"

    # Returns None for empty/None input (field is optional)
    result = validate_nmls(None)  # -> None
    result = validate_nmls("")    # -> None
"""

import re
from typing import Optional


def validate_nmls(value: Optional[str]) -> Optional[str]:
    """Validate and normalize an NMLS number for LO profiles.

    NMLS (Nationwide Multistate Licensing System) numbers are numeric
    identifiers assigned to mortgage loan originators. Valid format:
    5-12 digits, numeric only.

    Processing:
        1. Returns None for empty/None input (allows optional fields).
        2. Strips surrounding whitespace.
        3. Strips a leading '#' if present (common in copy-paste).
        4. Strips leading zeros.
        5. Rejects non-numeric characters.
        6. Rejects numbers outside 5-12 digit range.

    Args:
        value: Raw NMLS number string (may include whitespace, leading
               zeros, or a '#' prefix).

    Returns:
        Cleaned NMLS string (digits only, no leading zeros), or None
        if the input was empty/None.

    Raises:
        ValueError: If the value is non-numeric or outside the 5-12
                    digit range, with message:
                    "Invalid NMLS format. Must be 5-12 digits."
    """
    if value is None or str(value).strip() == "":
        return None

    cleaned = str(value).strip()

    # Strip leading '#' (common copy-paste artifact)
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]

    # Strip leading zeros
    cleaned = cleaned.lstrip("0")

    # After stripping zeros, empty string means input was all zeros
    if not cleaned:
        raise ValueError("Invalid NMLS format. Must be 5-12 digits.")

    # Must be digits only
    if not cleaned.isdigit():
        raise ValueError("Invalid NMLS format. Must be 5-12 digits.")

    # Must be 5-12 digits
    if len(cleaned) < 5 or len(cleaned) > 12:
        raise ValueError("Invalid NMLS format. Must be 5-12 digits.")

    return cleaned
