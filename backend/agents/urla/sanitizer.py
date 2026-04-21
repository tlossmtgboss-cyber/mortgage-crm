"""
Perennia AI — URLA Input Sanitizer
==================================
Strips HTML, control characters, and potential injection payloads from
free-text fields before they are persisted or forwarded to external systems.

Used by URLAAgent tool methods on all free-text inputs (names, employer
names, creditor names, descriptions, addresses).
"""
from __future__ import annotations

import re
from typing import Optional


# HTML tag stripper — removes all tags
_HTML_TAG = re.compile(r"<[^>]+>")

# Control characters (except common whitespace)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Common SQL injection fragments (for logging/alerting, not blocking)
_SQL_INJECTION_PATTERNS = re.compile(
    r"(?i)(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC)\b.*\b(FROM|INTO|TABLE|WHERE|SET)\b)"
    r"|(-{2})"      # SQL comments
    r"|(;[\s]*$)"    # Trailing semicolons
)

# Script/event handler patterns
_SCRIPT_PATTERNS = re.compile(
    r"(?i)(javascript:|on\w+\s*=|<script|<\/script|<img[^>]+onerror)"
)


def sanitize_text(value: Optional[str], field_name: str = "field", max_length: int = 500) -> Optional[str]:
    """
    Sanitize a free-text input string.

    - Strips HTML tags
    - Removes control characters
    - Truncates to max_length
    - Logs warning if injection patterns detected (does not block — the
      Pydantic model + BytePro API provide the actual defense)

    Returns the cleaned string, or None if input was None.
    """
    if value is None:
        return None

    import logging
    logger = logging.getLogger("urla.sanitizer")

    # Strip HTML
    cleaned = _HTML_TAG.sub("", value)

    # Remove control characters
    cleaned = _CONTROL_CHARS.sub("", cleaned)

    # Normalize whitespace
    cleaned = " ".join(cleaned.split())

    # Truncate
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]

    # Log suspicious patterns (don't block — could be legitimate business names)
    if _SQL_INJECTION_PATTERNS.search(cleaned):
        logger.warning(
            "Potential SQL injection in URLA input",
            extra={"field": field_name, "value_prefix": cleaned[:50]},
        )
    if _SCRIPT_PATTERNS.search(cleaned):
        logger.warning(
            "Potential XSS in URLA input",
            extra={"field": field_name, "value_prefix": cleaned[:50]},
        )

    return cleaned.strip()


def sanitize_name(value: Optional[str], field_name: str = "name") -> Optional[str]:
    """Sanitize a person or business name. More restrictive — names shouldn't contain special chars."""
    if value is None:
        return None
    cleaned = sanitize_text(value, field_name, max_length=200)
    if cleaned:
        # Names can contain letters, spaces, hyphens, apostrophes, periods, commas
        cleaned = re.sub(r"[^\w\s\-'.,]", "", cleaned)
    return cleaned


def sanitize_address(value: Optional[str], field_name: str = "address") -> Optional[str]:
    """Sanitize an address component. Allows #, /, digits."""
    if value is None:
        return None
    cleaned = sanitize_text(value, field_name, max_length=300)
    if cleaned:
        cleaned = re.sub(r"[^\w\s\-'.,#/]", "", cleaned)
    return cleaned


def sanitize_description(value: Optional[str], field_name: str = "description") -> Optional[str]:
    """Sanitize a free-text description. Most permissive."""
    return sanitize_text(value, field_name, max_length=1000)
