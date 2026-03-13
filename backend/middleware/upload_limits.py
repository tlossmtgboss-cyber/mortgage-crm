"""
Upload Size & Safety Limits Middleware

Provides reusable validation functions for file uploads across all Smart Docs
endpoints. Enforces size limits, image dimension checks, PDF page count limits,
and decompression bomb detection.

Usage:
    from middleware.upload_limits import validate_upload_size, UploadValidator

    # Simple size check (reads file in chunks, raises 413 if too large):
    file_bytes = await validate_upload_size(file)

    # Full validation (size + dimensions + page count + magic bytes):
    validator = UploadValidator()
    file_bytes = await validator.validate(file, max_size=MAX_IMAGE_SIZE)
"""

import io
import logging
import struct
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

MAX_DOCUMENT_SIZE = 25 * 1024 * 1024    # 25 MB general document limit
MAX_IMAGE_SIZE = 15 * 1024 * 1024       # 15 MB image limit
MAX_IMAGE_DIMENSIONS = (10000, 10000)   # pixels (width, height)
MAX_PDF_PAGES = 200                     # max pages in a single PDF upload
MAX_VISION_API_SIZE = 10 * 1024 * 1024  # 10 MB limit for Claude Vision API
MAX_OCR_OUTPUT_CHARS = 50_000           # max characters from OCR output
MAX_SIGNATURE_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB for base64-decoded signature images
PDF_BOMB_RATIO = 10                     # flag if decompressed > 10x compressed size

# Chunk size for streaming reads (64 KB)
_READ_CHUNK_SIZE = 64 * 1024

# MIME type to max size mapping (stricter than the validation engine defaults)
MIME_MAX_SIZES = {
    "application/pdf": MAX_DOCUMENT_SIZE,
    "image/jpeg": MAX_IMAGE_SIZE,
    "image/png": MAX_IMAGE_SIZE,
    "image/tiff": MAX_DOCUMENT_SIZE,
    "image/bmp": MAX_IMAGE_SIZE,
    "image/gif": MAX_IMAGE_SIZE,
    "image/webp": MAX_IMAGE_SIZE,
}

# Magic byte prefixes for file type verification
MAGIC_BYTES_MAP = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"II\x2a\x00": "image/tiff",
    b"MM\x00\x2a": "image/tiff",
    b"BM": "image/bmp",
    b"GIF8": "image/gif",
    b"RIFF": "image/webp",
}


# =============================================================================
# Core validation functions
# =============================================================================

async def validate_upload_size(
    file: UploadFile,
    max_size: int = MAX_DOCUMENT_SIZE,
) -> bytes:
    """
    Read an uploaded file in chunks and enforce a size limit.

    Reads the file incrementally so that an oversized upload is rejected
    without loading the entire file into memory first.

    Args:
        file: FastAPI UploadFile instance.
        max_size: Maximum allowed size in bytes.

    Returns:
        The complete file content as bytes.

    Raises:
        HTTPException(413): If the file exceeds max_size.
        HTTPException(400): If the file is empty.
    """
    chunks = []
    total_size = 0

    while True:
        chunk = await file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            max_mb = max_size / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum allowed size is {max_mb:.0f} MB.",
            )
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    return content


def validate_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """
    Check image dimensions without fully decoding the image.

    Parses headers for JPEG, PNG, and common formats to extract width/height
    without loading pixel data into memory.

    Args:
        image_bytes: Raw image bytes.

    Returns:
        Tuple of (width, height).

    Raises:
        HTTPException(413): If dimensions exceed MAX_IMAGE_DIMENSIONS.
    """
    width, height = 0, 0

    if not image_bytes or len(image_bytes) < 24:
        return (0, 0)

    # PNG: IHDR at bytes 16-23
    if image_bytes[:4] == b"\x89PNG":
        try:
            width = struct.unpack(">I", image_bytes[16:20])[0]
            height = struct.unpack(">I", image_bytes[20:24])[0]
        except (struct.error, IndexError):
            pass

    # JPEG: find SOF marker
    elif image_bytes[:3] == b"\xff\xd8\xff":
        width, height = _extract_jpeg_dimensions(image_bytes)

    # BMP: width/height at bytes 18-25 (little-endian)
    elif image_bytes[:2] == b"BM" and len(image_bytes) >= 26:
        try:
            width = struct.unpack("<I", image_bytes[18:22])[0]
            height = abs(struct.unpack("<i", image_bytes[22:26])[0])
        except (struct.error, IndexError):
            pass

    if width == 0 and height == 0:
        # Try PIL as fallback (does not load pixel data, just reads header)
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size
            img.close()
        except Exception:
            return (0, 0)

    max_w, max_h = MAX_IMAGE_DIMENSIONS
    if width > max_w or height > max_h:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image dimensions {width}x{height} exceed maximum "
                f"allowed {max_w}x{max_h} pixels."
            ),
        )

    # Also check total pixel count (decompression bomb protection)
    total_pixels = width * height
    if total_pixels > 100_000_000:  # 100 megapixels
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image has {total_pixels:,} pixels which could cause "
                f"memory exhaustion. Maximum is 100 megapixels."
            ),
        )

    return (width, height)


def validate_pdf_page_count(pdf_bytes: bytes) -> int:
    """
    Count pages in a PDF and enforce the page limit.

    Uses byte-level heuristics first, then falls back to PyPDF2
    if available.

    Args:
        pdf_bytes: Raw PDF bytes.

    Returns:
        The estimated page count.

    Raises:
        HTTPException(413): If page count exceeds MAX_PDF_PAGES.
    """
    page_count = _estimate_pdf_pages(pdf_bytes)

    if page_count > MAX_PDF_PAGES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"PDF has {page_count} pages. Maximum allowed is "
                f"{MAX_PDF_PAGES} pages. Split the document into "
                f"smaller parts and upload separately."
            ),
        )

    return page_count


def detect_pdf_bomb(pdf_bytes: bytes) -> bool:
    """
    Detect potential PDF decompression bombs.

    Checks if any stream in the PDF has a decompressed size significantly
    larger than the compressed stream, which could indicate a bomb designed
    to exhaust memory.

    Args:
        pdf_bytes: Raw PDF bytes.

    Returns:
        True if a potential bomb is detected.

    Raises:
        HTTPException(413): If a decompression bomb is detected.
    """
    compressed_size = len(pdf_bytes)

    # Quick heuristic: look for FlateDecode streams and check declared lengths
    # Search for /Length entries that seem disproportionate to file size
    try:
        import re
        # Find all /Length N entries in the PDF
        lengths = re.findall(rb"/Length\s+(\d+)", pdf_bytes)
        total_declared = sum(int(l) for l in lengths if int(l) < 1_000_000_000)

        if compressed_size > 0 and total_declared > compressed_size * PDF_BOMB_RATIO:
            raise HTTPException(
                status_code=413,
                detail=(
                    "PDF appears to contain compressed streams that would "
                    "decompress to an excessive size. This may indicate a "
                    "malformed or malicious document."
                ),
            )
            return True  # noqa: unreachable (for type checkers)

    except HTTPException:
        raise
    except Exception as e:
        logger.debug("PDF bomb detection skipped: %s", e)

    # Also try PyPDF2 if available for a more thorough check
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)

        # If the file is tiny but claims many pages, that is suspicious
        bytes_per_page = compressed_size / max(page_count, 1)
        if page_count > 10 and bytes_per_page < 100:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"PDF claims {page_count} pages but is only "
                    f"{compressed_size:,} bytes ({bytes_per_page:.0f} bytes/page). "
                    f"This may indicate a malicious document."
                ),
            )
    except HTTPException:
        raise
    except ImportError:
        pass
    except Exception as e:
        logger.debug("PyPDF2 bomb check skipped: %s", e)

    return False


def validate_magic_bytes(file_bytes: bytes, declared_mime: str) -> None:
    """
    Verify that file content matches the declared MIME type via magic bytes.

    Args:
        file_bytes: Raw file bytes (at least first 8 bytes needed).
        declared_mime: The declared Content-Type.

    Raises:
        HTTPException(400): If magic bytes do not match declared type.
    """
    if not file_bytes or len(file_bytes) < 4:
        return

    detected_mime = None
    for magic, mime in MAGIC_BYTES_MAP.items():
        if file_bytes[:len(magic)] == magic:
            detected_mime = mime
            break

    if detected_mime and detected_mime != declared_mime:
        # Allow compatible types (e.g., tiff variants)
        if not _mimes_compatible(detected_mime, declared_mime):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File content does not match declared type. "
                    f"Declared: {declared_mime}, detected: {detected_mime}."
                ),
            )


# =============================================================================
# UploadValidator class
# =============================================================================

class UploadValidator:
    """
    Combined upload validator that runs all checks in sequence.

    Provides a single-call interface for route handlers:
        validator = UploadValidator()
        file_bytes = await validator.validate(file)
    """

    def __init__(
        self,
        max_document_size: int = MAX_DOCUMENT_SIZE,
        max_image_size: int = MAX_IMAGE_SIZE,
        max_image_dimensions: Tuple[int, int] = MAX_IMAGE_DIMENSIONS,
        max_pdf_pages: int = MAX_PDF_PAGES,
        check_pdf_bomb: bool = True,
    ):
        self.max_document_size = max_document_size
        self.max_image_size = max_image_size
        self.max_image_dimensions = max_image_dimensions
        self.max_pdf_pages = max_pdf_pages
        self.check_pdf_bomb = check_pdf_bomb

    async def validate(
        self,
        file: UploadFile,
        max_size: Optional[int] = None,
    ) -> bytes:
        """
        Run all upload validations and return the file content.

        Checks performed (in order):
        1. Size limit (streaming read)
        2. Magic bytes vs declared MIME type
        3. Image dimensions (for image files)
        4. PDF page count (for PDFs)
        5. PDF decompression bomb detection (for PDFs)

        Args:
            file: FastAPI UploadFile.
            max_size: Override for the maximum file size. If None, the limit
                is determined by the file's MIME type.

        Returns:
            Complete file content as bytes.

        Raises:
            HTTPException: On any validation failure.
        """
        mime_type = file.content_type or "application/octet-stream"

        # Determine size limit
        if max_size is None:
            max_size = MIME_MAX_SIZES.get(mime_type, self.max_document_size)

        # 1. Read with size limit
        file_bytes = await validate_upload_size(file, max_size)

        # 2. Magic bytes check
        validate_magic_bytes(file_bytes, mime_type)

        # 3. Image dimension check
        if mime_type.startswith("image/"):
            validate_image_dimensions(file_bytes)

        # 4. PDF checks
        if mime_type == "application/pdf":
            validate_pdf_page_count(file_bytes)
            if self.check_pdf_bomb:
                detect_pdf_bomb(file_bytes)

        return file_bytes


# =============================================================================
# Private helpers
# =============================================================================

def _extract_jpeg_dimensions(content: bytes) -> Tuple[int, int]:
    """Extract width and height from a JPEG SOF marker."""
    idx = 2  # Skip SOI
    while idx < len(content) - 8:
        if content[idx] != 0xFF:
            idx += 1
            continue
        marker = content[idx + 1]
        # SOF markers: 0xC0-0xC3
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            try:
                height = struct.unpack(">H", content[idx + 5:idx + 7])[0]
                width = struct.unpack(">H", content[idx + 7:idx + 9])[0]
                return (width, height)
            except (struct.error, IndexError):
                return (0, 0)
        # Skip to next marker
        if marker == 0xFF:
            idx += 1
            continue
        if idx + 3 >= len(content):
            break
        try:
            seg_len = struct.unpack(">H", content[idx + 2:idx + 4])[0]
            idx += 2 + seg_len
        except (struct.error, IndexError):
            break
    return (0, 0)


def _estimate_pdf_pages(content: bytes) -> int:
    """Estimate PDF page count from byte-level heuristics."""
    if not content:
        return 0

    # Method 1: Count /Type /Page (excluding /Type /Pages)
    count = 0
    idx = 0
    search_term = b"/Type /Page"
    pages_term = b"/Type /Pages"

    while True:
        idx = content.find(search_term, idx)
        if idx == -1:
            break
        if content[idx:idx + len(pages_term)] != pages_term:
            count += 1
        idx += len(search_term)

    if count > 0:
        return count

    # Method 2: /Count in page tree
    count_idx = content.find(b"/Count ")
    if count_idx >= 0:
        num_start = count_idx + 7
        num_bytes = content[num_start:num_start + 10]
        try:
            num_str = (
                num_bytes.split(b" ")[0]
                .split(b"/")[0]
                .split(b"\n")[0]
                .split(b"\r")[0]
            )
            return int(num_str)
        except (ValueError, IndexError):
            pass

    # Method 3: Try PyPDF2 as fallback
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return len(reader.pages)
    except Exception:
        pass

    return 0


def _mimes_compatible(detected: str, declared: str) -> bool:
    """Check if two MIME types should be considered compatible."""
    if detected == declared:
        return True
    # TIFF variants
    if detected.startswith("image/tiff") and declared.startswith("image/tiff"):
        return True
    # WebP can be detected from RIFF container
    if "webp" in detected and "webp" in declared:
        return True
    return False
