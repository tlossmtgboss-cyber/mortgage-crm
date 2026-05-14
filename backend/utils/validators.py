"""
Shared validation helpers for the Perennia AI backend.

Usage:
    from utils.validators import validate_nmls, validate_upload_mime_type

    # Returns cleaned NMLS string or raises ValueError
    cleaned = validate_nmls("  0012345  ")  # -> "12345"

    # Returns None for empty/None input (field is optional)
    result = validate_nmls(None)  # -> None
    result = validate_nmls("")    # -> None

    # Validate file upload MIME type
    validate_upload_mime_type("report.pdf", "application/pdf")  # -> True
    validate_upload_mime_type("virus.exe", "application/x-msdownload")  # -> False
"""

import logging
import mimetypes
import re
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File upload MIME validation (SEC-004)
# ---------------------------------------------------------------------------

# Default allowed MIME types for general file uploads (documents + images).
# Route-specific handlers may define narrower sets.
ALLOWED_UPLOAD_MIME_TYPES: Set[str] = {
    # Documents
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv',
    # Images
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/tiff',
    'image/bmp',
    'image/webp',
}

# Audio MIME types (for voice samples, hold music, etc.)
ALLOWED_AUDIO_MIME_TYPES: Set[str] = {
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/x-wav',
    'audio/ogg',
    'audio/webm',
    'audio/aac',
    'audio/mp4',
    'audio/x-m4a',
    'audio/flac',
}

# Data import MIME types (CSV/Excel)
ALLOWED_IMPORT_MIME_TYPES: Set[str] = {
    'text/csv',
    'text/plain',
    'application/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def validate_upload_mime_type(
    filename: str,
    claimed_content_type: str,
    allowed_types: Set[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate that a file upload's MIME type is allowed.

    Cross-checks the claimed Content-Type against the extension-guessed type
    and the allowed set. Returns (is_valid, error_message).

    Args:
        filename: Original filename from the upload.
        claimed_content_type: Content-Type header from the upload.
        allowed_types: Set of allowed MIME types. Defaults to ALLOWED_UPLOAD_MIME_TYPES.

    Returns:
        (True, None) if valid, (False, error_message) if not.
    """
    if allowed_types is None:
        allowed_types = ALLOWED_UPLOAD_MIME_TYPES

    # Guess MIME type from file extension
    guessed_type, _ = mimetypes.guess_type(filename or "")

    # Check claimed type against allowlist
    if claimed_content_type and claimed_content_type not in allowed_types:
        logger.warning(
            "Upload MIME rejected: filename=%s, claimed=%s, guessed=%s",
            filename, claimed_content_type, guessed_type,
        )
        return False, (
            f"File type '{claimed_content_type}' is not allowed. "
            f"Accepted types: {', '.join(sorted(allowed_types))}"
        )

    # Cross-check: if we can guess the type from extension and it doesn't match claimed
    if guessed_type and claimed_content_type and guessed_type != claimed_content_type:
        # Allow common mismatches (e.g., text/plain for .csv)
        _benign_mismatches = {
            ('text/plain', 'text/csv'),
            ('text/csv', 'text/plain'),
            ('text/plain', 'application/csv'),
            ('audio/x-wav', 'audio/wav'),
            ('audio/wav', 'audio/x-wav'),
        }
        if (guessed_type, claimed_content_type) not in _benign_mismatches:
            # Guessed type must also be in the allowed set
            if guessed_type not in allowed_types:
                logger.warning(
                    "Upload extension/MIME mismatch: filename=%s, claimed=%s, guessed=%s",
                    filename, claimed_content_type, guessed_type,
                )
                return False, (
                    f"File extension does not match declared type "
                    f"(extension suggests '{guessed_type}', header says '{claimed_content_type}')"
                )

    return True, None


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
