"""
Upload Security Pipeline

Unified security pipeline for all file upload endpoints. Runs the full
chain of validations and sanitizations in a single call:

    1. MIME type validation
    2. Magic bytes verification
    3. Malware scan (ClamAV / signature fallback)
    4. EXIF metadata stripping (images)
    5. PDF sanitization (remove JS / Launch actions)

Usage:
    from middleware.upload_security import secure_upload

    # In a FastAPI route handler:
    result = await secure_upload(file)
    # result.file_bytes  — sanitized content ready for S3
    # result.mime_type   — validated MIME type
    # result.filename    — sanitized filename
    # result.scan_result — malware scan details
    # result.sanitization_log — list of actions taken
"""

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Set

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)


# =============================================================================
# Result data class
# =============================================================================

@dataclass
class SecureUploadResult:
    """Result from the secure upload pipeline."""

    file_bytes: bytes
    """Sanitized file content."""

    mime_type: str
    """Validated MIME type."""

    filename: str
    """Sanitized filename (path-traversal safe, truncated)."""

    original_filename: str
    """Original filename as uploaded."""

    file_size: int
    """Size in bytes after sanitization."""

    scan_clean: bool
    """True if all malware scans passed."""

    sanitization_log: List[str] = field(default_factory=list)
    """Human-readable log of sanitization actions taken."""

    scan_details: Optional[dict] = None
    """Full malware scan result dict (for audit logging)."""


# =============================================================================
# Configuration
# =============================================================================

# Default maximum file size (25 MB)
DEFAULT_MAX_SIZE = 25 * 1024 * 1024

# Chunk size for streaming reads
_READ_CHUNK = 64 * 1024


# =============================================================================
# Main pipeline
# =============================================================================

async def secure_upload(
    file: UploadFile,
    *,
    max_size: int = DEFAULT_MAX_SIZE,
    allowed_mimes: Optional[Set[str]] = None,
    skip_malware_scan: bool = False,
    skip_sanitization: bool = False,
) -> SecureUploadResult:
    """
    Run the full upload security pipeline.

    Reads the file in chunks (to enforce size limits without loading
    oversized files), validates type, scans for malware, and sanitizes
    content (EXIF stripping for images, JS/action removal for PDFs).

    Args:
        file: FastAPI UploadFile instance.
        max_size: Maximum allowed file size in bytes.
        allowed_mimes: Optional set of allowed MIME types. If None,
            uses the default set from utils.validators.
        skip_malware_scan: Skip malware scanning (for testing only).
        skip_sanitization: Skip EXIF/PDF sanitization (for testing only).

    Returns:
        SecureUploadResult with sanitized file bytes and metadata.

    Raises:
        HTTPException(400): Invalid file type or content mismatch.
        HTTPException(413): File too large.
        HTTPException(415): MIME type not allowed.
        HTTPException(422): Malware detected.
    """
    sanitization_log: List[str] = []
    original_filename = file.filename or "upload"
    mime_type = file.content_type or "application/octet-stream"

    # ---- Step 0: Sanitize filename ----
    safe_filename = _sanitize_filename(original_filename)
    sanitization_log.append(f"Filename sanitized: {original_filename!r} -> {safe_filename!r}")

    # ---- Step 1: MIME type validation ----
    if allowed_mimes is None:
        from utils.validators import ALLOWED_UPLOAD_MIME_TYPES
        allowed_mimes = ALLOWED_UPLOAD_MIME_TYPES

    if mime_type not in allowed_mimes:
        raise HTTPException(
            status_code=415,
            detail=(
                f"File type '{mime_type}' is not allowed. "
                f"Accepted types: {', '.join(sorted(allowed_mimes))}"
            ),
        )

    # ---- Step 2: Read with size limit (chunked) ----
    file_bytes = await _read_with_limit(file, max_size)
    file_size = len(file_bytes)

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # ---- Step 3: Magic bytes verification ----
    from middleware.upload_limits import validate_magic_bytes
    try:
        validate_magic_bytes(file_bytes, mime_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Magic bytes check error: %s", e)
        # Non-fatal — continue with other checks

    # ---- Step 4: Malware scan ----
    scan_result_dict = None
    scan_clean = True

    if not skip_malware_scan:
        try:
            from services.smart_docs.malware_scanner_service import get_malware_scanner

            scanner = get_malware_scanner()
            scan_result = scanner.validate_file_safety(
                file_bytes, safe_filename, mime_type
            )
            scan_clean = scan_result.clean
            scan_result_dict = scan_result.to_dict()

            if not scan_clean:
                findings = scan_result_dict.get("findings", [])
                threat_names = [f.get("threat_name", "unknown") for f in findings]
                logger.warning(
                    "Upload rejected by malware scan: file=%s threats=%s",
                    safe_filename, threat_names,
                )
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"File failed security scan. "
                        f"Detected threats: {', '.join(threat_names)}"
                    ),
                )

            sanitization_log.append(
                f"Malware scan passed ({scan_result.scan_duration_ms}ms, "
                f"scanners: {', '.join(scan_result.scanners_used)})"
            )

        except HTTPException:
            raise
        except Exception as e:
            # Scanner failure should not block uploads — log and continue
            logger.error("Malware scanner error (non-blocking): %s", e)
            sanitization_log.append(f"Malware scan skipped due to error: {e}")

    # ---- Step 5: Content sanitization ----
    if not skip_sanitization:
        file_bytes, sanitization_log = _sanitize_content(
            file_bytes, mime_type, sanitization_log
        )

    return SecureUploadResult(
        file_bytes=file_bytes,
        mime_type=mime_type,
        filename=safe_filename,
        original_filename=original_filename,
        file_size=len(file_bytes),
        scan_clean=scan_clean,
        sanitization_log=sanitization_log,
        scan_details=scan_result_dict,
    )


# =============================================================================
# Internal helpers
# =============================================================================

def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe storage.

    - Strips path components (prevent path traversal)
    - Replaces unsafe characters with underscores
    - Truncates to 100 characters
    - Prepends a short UUID for uniqueness
    """
    # Strip any path components
    name = os.path.basename(filename)

    # Replace unsafe characters
    name = re.sub(r'[^\w.\-]', '_', name)

    # Truncate
    if len(name) > 100:
        name = name[:100]

    # Prepend short UUID
    prefix = uuid.uuid4().hex[:12]
    return f"{prefix}_{name}"


async def _read_with_limit(file: UploadFile, max_size: int) -> bytes:
    """Read an uploaded file in chunks, enforcing a size limit."""
    chunks = []
    total = 0

    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            max_mb = max_size / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum allowed size is {max_mb:.0f} MB.",
            )
        chunks.append(chunk)

    return b"".join(chunks)


def _sanitize_content(
    file_bytes: bytes,
    mime_type: str,
    log: List[str],
) -> tuple:
    """Apply content-specific sanitization (EXIF stripping, PDF cleaning)."""

    # ---- Image: strip EXIF metadata ----
    if mime_type.startswith("image/"):
        try:
            from utils.image_sanitizer import strip_image_metadata

            original_size = len(file_bytes)
            file_bytes = strip_image_metadata(file_bytes, mime_type)
            new_size = len(file_bytes)
            log.append(
                f"Image metadata stripped: {original_size} -> {new_size} bytes"
            )
        except Exception as e:
            logger.warning("Image sanitization error (non-blocking): %s", e)
            log.append(f"Image sanitization skipped: {e}")

    # ---- PDF: remove dangerous actions ----
    elif mime_type == "application/pdf":
        try:
            from utils.pdf_sanitizer import sanitize_pdf

            file_bytes, removed = sanitize_pdf(file_bytes)
            if removed:
                log.append(
                    f"PDF sanitized: {len(removed)} elements removed "
                    f"({'; '.join(removed)})"
                )
            else:
                log.append("PDF scanned, no dangerous elements found")
        except Exception as e:
            logger.warning("PDF sanitization error (non-blocking): %s", e)
            log.append(f"PDF sanitization skipped: {e}")

    return file_bytes, log
