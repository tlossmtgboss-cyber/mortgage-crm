"""
Test Document Validation Engine

Comprehensive tests for the rule-based document validation engine used for
mortgage document uploads. Tests cover file type validation, security checks,
filename sanitization, duplicate detection, page count validation, freshness,
completeness, PII detection, and overall result scoring.

Covers:
1. File type validation via magic bytes (PDF, JPEG, PNG, TIFF)
2. Blocked extension rejection (.exe, .bat, .js, .vbs)
3. File size validation (min/max limits)
4. PDF safety checks (no JavaScript, no embedded executables)
5. Image safety checks (dimensions, trailing data)
6. MIME type vs extension mismatch detection
7. Duplicate document detection (hash-based)
8. Filename sanitization (special chars, path traversal prevention)
9. Virus scan integration point (embedded executable detection)
10. Password-protected PDF handling
11. Corrupted file detection
12. Multi-page document validation (PDF + TIFF)
13. Image resolution / dimension requirements
14. File metadata stripping detection (EXIF)
15. Validation result reporting and scoring
"""

import hashlib
import io
import struct
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.smart_docs.document_validation_engine import (
    ALLOWED_MIME_TYPES,
    BLOCKED_EXTENSIONS,
    COMPLETENESS_RULES,
    EXPECTED_PAGE_COUNTS,
    FRESHNESS_RULES,
    MAGIC_BYTES,
    MAX_FILE_SIZES,
    MIN_FILE_SIZES,
    DocumentValidationEngine,
    ValidationIssue,
    ValidationResult,
    get_document_validation_engine,
)


# =============================================================================
# Test data generators -- build small valid binary files in memory
# =============================================================================

def make_minimal_pdf(page_count: int = 1, include_js: bool = False,
                     include_launch: bool = False,
                     include_embedded_exe: bool = False,
                     include_open_action_js: bool = False) -> bytes:
    """
    Build a tiny valid-enough PDF for validation testing.

    The engine does byte-level scanning (not full PDF parsing), so we just
    need the right magic header and structural markers.
    """
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")

    for i in range(page_count):
        buf.write(f"{i + 1} 0 obj\n".encode())
        buf.write(b"<< /Type /Page >>\n")
        buf.write(b"endobj\n")

    # Page tree
    buf.write(f"{page_count + 1} 0 obj\n".encode())
    buf.write(f"<< /Type /Pages /Count {page_count} >>\n".encode())
    buf.write(b"endobj\n")

    if include_js:
        buf.write(b"<< /JS (app.alert('hi')) /S /JavaScript >>\n")

    if include_launch:
        buf.write(b"<< /S /Launch /Type /Action >>\n")

    if include_embedded_exe:
        buf.write(b"/EmbeddedFile\n")
        buf.write(b"/Subtype /application/x-msdownload\n")

    if include_open_action_js:
        buf.write(b"<< /OpenAction << /JS (malicious()) /S /JavaScript >> >>\n")

    buf.write(b"%%EOF\n")

    content = buf.getvalue()
    # Pad to exceed MIN_FILE_SIZES for PDF (1024 bytes)
    if len(content) < 1100:
        content += b"\n%" + b"0" * (1100 - len(content))
    return content


def make_minimal_jpeg(width: int = 100, height: int = 80,
                      trailing_data: bytes = b"") -> bytes:
    """
    Build a minimal JPEG with valid SOI, SOF0, and EOI markers.

    The SOF0 marker encodes width/height so the engine can extract dimensions.
    """
    buf = io.BytesIO()
    # SOI
    buf.write(b"\xff\xd8")
    # APP0 (JFIF) -- minimal
    buf.write(b"\xff\xe0")
    app0_data = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    buf.write(struct.pack(">H", len(app0_data) + 2))
    buf.write(app0_data)
    # SOF0 (baseline)
    buf.write(b"\xff\xc0")
    # SOF0 length: 2 (length) + 1 (precision) + 2 (height) + 2 (width) + 1 (components) + 3*components
    components = 3  # YCbCr
    sof_len = 2 + 1 + 2 + 2 + 1 + 3 * components
    buf.write(struct.pack(">H", sof_len))
    buf.write(struct.pack("B", 8))  # precision
    buf.write(struct.pack(">H", height))
    buf.write(struct.pack(">H", width))
    buf.write(struct.pack("B", components))
    for comp_id in range(1, components + 1):
        buf.write(struct.pack("BBB", comp_id, 0x11, 0))
    # Pad with dummy scan data to reach a reasonable size
    buf.write(b"\xff\xda")  # SOS marker (start of scan)
    buf.write(struct.pack(">H", 8))
    buf.write(b"\x03\x01\x00\x02\x11\x03")  # dummy SOS header
    buf.write(b"\x00" * 2048)  # dummy image data
    # EOI
    buf.write(b"\xff\xd9")
    # Optional trailing data after EOI
    if trailing_data:
        buf.write(trailing_data)
    return buf.getvalue()


def make_minimal_png(width: int = 100, height: int = 80) -> bytes:
    """
    Build a minimal PNG with valid signature, IHDR, and IEND chunks.

    The engine reads dimensions from bytes 16-23 of the PNG.
    """
    import zlib

    buf = io.BytesIO()
    # PNG signature
    buf.write(b"\x89PNG\r\n\x1a\n")
    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    buf.write(struct.pack(">I", len(ihdr_data)))
    buf.write(b"IHDR")
    buf.write(ihdr_data)
    buf.write(struct.pack(">I", ihdr_crc))
    # Minimal IDAT chunk (1x1 scanline filtered with no-filter byte)
    raw_data = b"\x00" + b"\x00\x00\x00" * width  # one scanline
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    buf.write(struct.pack(">I", len(compressed)))
    buf.write(b"IDAT")
    buf.write(compressed)
    buf.write(struct.pack(">I", idat_crc))
    # IEND chunk
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    buf.write(struct.pack(">I", 0))
    buf.write(b"IEND")
    buf.write(struct.pack(">I", iend_crc))
    return buf.getvalue()


def make_minimal_tiff(page_count: int = 1, big_endian: bool = False) -> bytes:
    """
    Build a minimal TIFF with the requested number of IFD entries (pages).

    Each IFD has 0 tag entries and a pointer to the next IFD (or 0 to end).
    """
    buf = io.BytesIO()
    endian = ">" if big_endian else "<"
    # Header
    buf.write(b"MM" if big_endian else b"II")
    buf.write(struct.pack(endian + "H", 42))  # Magic number
    # First IFD offset (immediately after header = offset 8)
    first_ifd_offset = 8
    buf.write(struct.pack(endian + "I", first_ifd_offset))

    for i in range(page_count):
        # Number of directory entries: 1 (we need at least one tag to be valid)
        buf.write(struct.pack(endian + "H", 1))
        # Minimal tag entry (12 bytes): ImageWidth (tag 256), SHORT (type 3), count 1, value 100
        buf.write(struct.pack(endian + "HHI", 256, 3, 1))
        buf.write(struct.pack(endian + "I", 100))  # value
        # Next IFD offset
        if i < page_count - 1:
            # Calculate next IFD position: current pos + 4 (next offset bytes)
            next_offset = buf.tell() + 4
            buf.write(struct.pack(endian + "I", next_offset))
        else:
            buf.write(struct.pack(endian + "I", 0))  # No more IFDs

    content = buf.getvalue()
    # Pad to exceed minimum file size
    if len(content) < 1024:
        content += b"\x00" * (1024 - len(content))
    return content


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def engine():
    """Fresh DocumentValidationEngine instance (not the singleton)."""
    return DocumentValidationEngine()


@pytest.fixture
def valid_pdf():
    """A minimal valid PDF that passes all checks."""
    return make_minimal_pdf(page_count=2)


@pytest.fixture
def valid_jpeg():
    """A minimal valid JPEG that passes all checks."""
    return make_minimal_jpeg(width=800, height=600)


@pytest.fixture
def valid_png():
    """A minimal valid PNG that passes all checks."""
    return make_minimal_png(width=800, height=600)


# =============================================================================
# 1. File type validation via magic bytes
# =============================================================================

@pytest.mark.unit
class TestMagicBytesDetection:
    """Verify that magic byte detection correctly identifies file types."""

    def test_detect_pdf_magic_bytes(self, engine):
        """PDF magic bytes (%PDF) should be detected as application/pdf."""
        pdf = make_minimal_pdf()
        detected = engine._detect_mime_from_magic(pdf)
        assert detected == "application/pdf"

    def test_detect_jpeg_magic_bytes(self, engine):
        """JPEG magic bytes (FF D8 FF) should be detected as image/jpeg."""
        jpeg = make_minimal_jpeg()
        detected = engine._detect_mime_from_magic(jpeg)
        assert detected == "image/jpeg"

    def test_detect_png_magic_bytes(self, engine):
        """PNG magic bytes (89 50 4E 47) should be detected as image/png."""
        png = make_minimal_png()
        detected = engine._detect_mime_from_magic(png)
        assert detected == "image/png"

    def test_detect_tiff_le_magic_bytes(self, engine):
        """Little-endian TIFF (II) should be detected as image/tiff."""
        tiff = make_minimal_tiff(big_endian=False)
        detected = engine._detect_mime_from_magic(tiff)
        assert detected == "image/tiff"

    def test_detect_tiff_be_magic_bytes(self, engine):
        """Big-endian TIFF (MM) should be detected as image/tiff."""
        tiff = make_minimal_tiff(big_endian=True)
        detected = engine._detect_mime_from_magic(tiff)
        assert detected == "image/tiff"

    def test_unknown_magic_bytes_returns_none(self, engine):
        """Random bytes should return None for MIME detection."""
        random_data = b"\x01\x02\x03\x04\x05\x06\x07\x08" * 200
        detected = engine._detect_mime_from_magic(random_data)
        assert detected is None

    def test_magic_mismatch_creates_issue(self, engine):
        """Declaring a JPEG as PDF should produce a FILE_TYPE_MAGIC_MISMATCH issue."""
        jpeg = make_minimal_jpeg()
        issues = engine.validate_file_type(jpeg, "scan.pdf", "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MAGIC_MISMATCH" in rules


# =============================================================================
# 2. Blocked extension rejection
# =============================================================================

@pytest.mark.unit
class TestBlockedExtensions:
    """Verify that dangerous file extensions are rejected."""

    @pytest.mark.parametrize("ext", [".exe", ".bat", ".cmd", ".vbs", ".js", ".ps1", ".sh"])
    def test_blocked_extensions_rejected(self, engine, ext):
        """Each blocked extension must produce a FILE_TYPE_BLOCKED issue."""
        filename = f"document{ext}"
        # Use valid PDF bytes to isolate the extension check
        pdf = make_minimal_pdf()
        issues = engine.validate_file_type(pdf, filename, "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_BLOCKED" in rules, f"Extension {ext} was not blocked"

    def test_double_extension_detected(self, engine):
        """A double extension like report.pdf.exe should be caught."""
        pdf = make_minimal_pdf()
        issues = engine.validate_file_type(pdf, "report.pdf.exe", "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_BLOCKED" in rules or "FILE_TYPE_DOUBLE_EXT" in rules

    def test_safe_extension_allowed(self, engine):
        """A .pdf extension should not trigger any blocked extension issues."""
        pdf = make_minimal_pdf()
        issues = engine.validate_file_type(pdf, "document.pdf", "application/pdf")
        blocked_issues = [i for i in issues if i.rule in ("FILE_TYPE_BLOCKED", "FILE_TYPE_DOUBLE_EXT")]
        assert len(blocked_issues) == 0


# =============================================================================
# 3. File size validation
# =============================================================================

@pytest.mark.unit
class TestFileSizeValidation:
    """Verify minimum and maximum file size enforcement."""

    def test_empty_file_rejected(self, engine):
        """A zero-byte file must produce FILE_SIZE_EMPTY."""
        issues = engine.validate_file_size(b"", "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_EMPTY" in rules

    def test_too_small_file_rejected(self, engine):
        """A file smaller than MIN_FILE_SIZES must produce FILE_SIZE_TOO_SMALL."""
        # PDF minimum is 1024 bytes; send 100 bytes
        tiny = b"%PDF-1.4" + b"\x00" * 92
        issues = engine.validate_file_size(tiny, "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_TOO_SMALL" in rules

    def test_too_large_file_rejected(self, engine):
        """A file exceeding MAX_FILE_SIZES must produce FILE_SIZE_TOO_LARGE."""
        # PDF max is 50 MB; simulate by checking the logic with a large size
        max_pdf = MAX_FILE_SIZES["application/pdf"]
        oversized = b"%PDF" + b"\x00" * (max_pdf + 1)
        issues = engine.validate_file_size(oversized, "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_TOO_LARGE" in rules

    def test_valid_size_passes(self, engine, valid_pdf):
        """A file within the acceptable range should produce no size issues."""
        issues = engine.validate_file_size(valid_pdf, "application/pdf")
        assert len(issues) == 0

    def test_jpeg_min_size_enforced(self, engine):
        """JPEG min is 2048 bytes; a 500-byte file should fail."""
        tiny_jpeg = b"\xff\xd8\xff" + b"\x00" * 497
        issues = engine.validate_file_size(tiny_jpeg, "image/jpeg")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_TOO_SMALL" in rules

    def test_default_min_used_for_unknown_type(self, engine):
        """An unknown MIME type should use the 'default' size thresholds."""
        # Default min is 512, so 100 bytes should fail
        issues = engine.validate_file_size(b"\x00" * 100, "image/bmp")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_TOO_SMALL" in rules


# =============================================================================
# 4. PDF safety checks
# =============================================================================

@pytest.mark.unit
class TestPdfSafety:
    """Verify detection of dangerous PDF content."""

    def test_pdf_with_javascript_flagged(self, engine):
        """A PDF containing /JS or /JavaScript should produce PDF_JAVASCRIPT."""
        pdf = make_minimal_pdf(include_js=True)
        issues = engine.validate_pdf_safety(pdf)
        rules = [i.rule for i in issues]
        assert "PDF_JAVASCRIPT" in rules

    def test_pdf_with_launch_action_flagged(self, engine):
        """A PDF with /Launch action should produce PDF_LAUNCH_ACTION."""
        pdf = make_minimal_pdf(include_launch=True)
        issues = engine.validate_pdf_safety(pdf)
        rules = [i.rule for i in issues]
        assert "PDF_LAUNCH_ACTION" in rules

    def test_pdf_with_embedded_executable_flagged(self, engine):
        """A PDF with /EmbeddedFile and dangerous MIME type should produce PDF_EMBEDDED_EXECUTABLE."""
        pdf = make_minimal_pdf(include_embedded_exe=True)
        issues = engine.validate_pdf_safety(pdf)
        rules = [i.rule for i in issues]
        assert "PDF_EMBEDDED_EXECUTABLE" in rules

    def test_pdf_with_open_action_js_flagged(self, engine):
        """A PDF with /OpenAction containing /JS should produce PDF_AUTOOPEN_SCRIPT."""
        pdf = make_minimal_pdf(include_open_action_js=True)
        issues = engine.validate_pdf_safety(pdf)
        rules = [i.rule for i in issues]
        assert "PDF_AUTOOPEN_SCRIPT" in rules

    def test_clean_pdf_passes_safety(self, engine, valid_pdf):
        """A clean PDF with no scripts should produce no safety issues."""
        issues = engine.validate_pdf_safety(valid_pdf)
        assert len(issues) == 0

    def test_non_pdf_content_skipped(self, engine):
        """Non-PDF content should return empty issues from validate_pdf_safety."""
        jpeg = make_minimal_jpeg()
        issues = engine.validate_pdf_safety(jpeg)
        assert len(issues) == 0

    def test_excessive_page_count_flagged(self, engine):
        """A PDF with > 500 pages should be flagged."""
        pdf = make_minimal_pdf(page_count=600)
        issues = engine.validate_pdf_safety(pdf)
        rules = [i.rule for i in issues]
        assert "PDF_EXCESSIVE_PAGES" in rules


# =============================================================================
# 5. Image safety checks
# =============================================================================

@pytest.mark.unit
class TestImageSafety:
    """Verify image-specific safety validations."""

    def test_jpeg_trailing_data_detected(self, engine):
        """JPEG with >4096 bytes after EOI should produce IMAGE_TRAILING_DATA."""
        trailing = b"\x00" * 5000
        jpeg = make_minimal_jpeg(trailing_data=trailing)
        issues = engine.validate_image_safety(jpeg)
        rules = [i.rule for i in issues]
        assert "IMAGE_TRAILING_DATA" in rules

    def test_jpeg_no_trailing_data_passes(self, engine, valid_jpeg):
        """A clean JPEG should not trigger trailing data detection."""
        issues = engine.validate_image_safety(valid_jpeg)
        trailing_issues = [i for i in issues if i.rule == "IMAGE_TRAILING_DATA"]
        assert len(trailing_issues) == 0

    def test_png_absurd_dimensions_detected(self, engine):
        """A PNG claiming dimensions > 20000 should produce IMAGE_ABSURD_DIMENSIONS."""
        png = make_minimal_png(width=25000, height=25000)
        issues = engine.validate_image_safety(png)
        rules = [i.rule for i in issues]
        assert "IMAGE_ABSURD_DIMENSIONS" in rules

    def test_jpeg_absurd_dimensions_detected(self, engine):
        """A JPEG claiming dimensions > 20000 should produce IMAGE_ABSURD_DIMENSIONS."""
        jpeg = make_minimal_jpeg(width=30000, height=30000)
        issues = engine.validate_image_safety(jpeg)
        rules = [i.rule for i in issues]
        assert "IMAGE_ABSURD_DIMENSIONS" in rules

    def test_png_pixel_bomb_detected(self, engine):
        """A PNG with > 200M total pixels should produce IMAGE_PIXEL_BOMB."""
        # 15000 * 15000 = 225,000,000 > 200M threshold
        png = make_minimal_png(width=15000, height=15000)
        issues = engine.validate_image_safety(png)
        rules = [i.rule for i in issues]
        assert "IMAGE_PIXEL_BOMB" in rules

    def test_normal_image_dimensions_pass(self, engine, valid_jpeg):
        """Standard dimensions should not trigger dimension issues."""
        issues = engine.validate_image_safety(valid_jpeg)
        dim_issues = [i for i in issues if "DIMENSION" in i.rule or "PIXEL_BOMB" in i.rule]
        assert len(dim_issues) == 0


# =============================================================================
# 6. MIME type vs extension mismatch
# =============================================================================

@pytest.mark.unit
class TestMimeMismatch:
    """Verify MIME-to-magic-bytes mismatch detection."""

    def test_pdf_declared_as_jpeg_flagged(self, engine):
        """PDF bytes declared as image/jpeg should produce a mismatch issue."""
        pdf = make_minimal_pdf()
        issues = engine.validate_file_type(pdf, "scan.jpg", "image/jpeg")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MAGIC_MISMATCH" in rules

    def test_jpeg_declared_as_png_flagged(self, engine):
        """JPEG bytes declared as image/png should produce a mismatch issue."""
        jpeg = make_minimal_jpeg()
        issues = engine.validate_file_type(jpeg, "photo.png", "image/png")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MAGIC_MISMATCH" in rules

    def test_correct_mime_no_mismatch(self, engine, valid_pdf):
        """Correct MIME+magic combination should produce no mismatch."""
        issues = engine.validate_file_type(valid_pdf, "doc.pdf", "application/pdf")
        mismatch_issues = [i for i in issues if i.rule == "FILE_TYPE_MAGIC_MISMATCH"]
        assert len(mismatch_issues) == 0

    def test_disallowed_mime_type_flagged(self, engine):
        """A MIME type not in ALLOWED_MIME_TYPES should produce FILE_TYPE_MIME_NOT_ALLOWED."""
        pdf = make_minimal_pdf()
        issues = engine.validate_file_type(pdf, "doc.docx",
                                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MIME_NOT_ALLOWED" in rules

    def test_unknown_magic_bytes_flagged(self, engine):
        """File with unrecognized magic bytes should produce FILE_TYPE_MAGIC_UNKNOWN."""
        random_data = b"\x01\x02\x03\x04" + b"\x00" * 2000
        issues = engine.validate_file_type(random_data, "mystery.pdf", "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MAGIC_UNKNOWN" in rules


# =============================================================================
# 7. Duplicate document detection
# =============================================================================

@pytest.mark.unit
class TestDuplicateDetection:
    """Verify hash-based and type-based duplicate detection."""

    def test_exact_size_duplicate_detected(self, engine, valid_pdf):
        """When a file with the same size exists, DUPLICATE_EXACT_SIZE should be raised."""
        mock_db = MagicMock(spec=["execute"])
        file_size = len(valid_pdf)

        # Simulate DB returning a matching row
        mock_row = MagicMock()
        mock_row.file_name = "existing_doc.pdf"
        mock_row.uploaded_at = datetime(2026, 3, 1)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        # First call: size match query; second call: recent same type query
        mock_db.execute.side_effect = [mock_result, MagicMock(fetchall=MagicMock(return_value=[]))]

        issues = engine.detect_duplicates(
            loan_id=1, file_content=valid_pdf, doc_type="PAYSTUB", db=mock_db
        )
        rules = [i.rule for i in issues]
        assert "DUPLICATE_EXACT_SIZE" in rules

    def test_recent_same_type_duplicate_detected(self, engine, valid_pdf):
        """Uploading same doc type within 24h should produce DUPLICATE_RECENT_SAME_TYPE."""
        mock_db = MagicMock(spec=["execute"])

        # First query (size match): no results
        mock_no_match = MagicMock()
        mock_no_match.fetchall.return_value = []

        # Second query (recent same type): one result
        mock_recent_row = MagicMock()
        mock_recent_row.file_name = "paystub_v1.pdf"
        mock_recent_result = MagicMock()
        mock_recent_result.fetchall.return_value = [mock_recent_row]

        mock_db.execute.side_effect = [mock_no_match, mock_recent_result]

        issues = engine.detect_duplicates(
            loan_id=1, file_content=valid_pdf, doc_type="PAYSTUB", db=mock_db
        )
        rules = [i.rule for i in issues]
        assert "DUPLICATE_RECENT_SAME_TYPE" in rules

    def test_no_duplicate_when_db_empty(self, engine, valid_pdf):
        """No duplicates should be raised when DB has no matching records."""
        mock_db = MagicMock(spec=["execute"])
        mock_empty = MagicMock()
        mock_empty.fetchall.return_value = []
        mock_db.execute.return_value = mock_empty

        issues = engine.detect_duplicates(
            loan_id=1, file_content=valid_pdf, doc_type="W2", db=mock_db
        )
        assert len(issues) == 0

    def test_db_failure_non_fatal(self, engine, valid_pdf):
        """If the DB query fails, duplicate detection should silently skip."""
        mock_db = MagicMock(spec=["execute"])
        mock_db.execute.side_effect = Exception("Connection refused")

        issues = engine.detect_duplicates(
            loan_id=1, file_content=valid_pdf, doc_type="PAYSTUB", db=mock_db
        )
        # Should return empty, not raise
        assert len(issues) == 0


# =============================================================================
# 8. Filename sanitization
# =============================================================================

@pytest.mark.unit
class TestFilenameSanitization:
    """Verify dangerous characters and path traversal are stripped from filenames."""

    def test_path_traversal_removed(self, engine):
        """../ sequences should be stripped from filenames."""
        result = engine.sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_backslash_traversal_removed(self, engine):
        r"""..\ sequences should be stripped from filenames."""
        result = engine.sanitize_filename("..\\..\\windows\\system32\\config.pdf")
        assert "..\\" not in result

    def test_null_bytes_removed(self, engine):
        """Null bytes should be stripped."""
        result = engine.sanitize_filename("document\x00.pdf")
        assert "\x00" not in result
        assert result.endswith(".pdf")

    def test_control_characters_removed(self, engine):
        """Control characters (0x00-0x1f, 0x7f) should be stripped."""
        result = engine.sanitize_filename("doc\x01\x02\x0a\x7f.pdf")
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x7f" not in result

    def test_special_chars_replaced(self, engine):
        """Characters <, >, :, |, ?, * should be replaced with underscores."""
        result = engine.sanitize_filename('file<name>:with|bad?chars*.pdf')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result
        assert result.endswith(".pdf")

    def test_empty_filename_gets_default(self, engine):
        """An empty filename after sanitization should become 'document'."""
        result = engine.sanitize_filename("...")
        assert result == "document"

    def test_length_limited_to_255(self, engine):
        """Filenames exceeding 255 chars should be truncated (preserving extension)."""
        long_name = "a" * 300 + ".pdf"
        result = engine.sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    def test_multiple_underscores_collapsed(self, engine):
        """Consecutive underscores should be collapsed to a single one."""
        result = engine.sanitize_filename("doc___name___final.pdf")
        assert "___" not in result

    def test_leading_trailing_dots_stripped(self, engine):
        """Leading/trailing dots and spaces should be stripped."""
        result = engine.sanitize_filename("  ..hidden.pdf.. ")
        assert not result.startswith(".")
        assert not result.startswith(" ")

    def test_validate_upload_records_sanitized_filename(self, engine, valid_pdf):
        """If the filename is changed by sanitization, an INFO issue should appear."""
        result = engine.validate_upload(valid_pdf, "../evil.pdf", "application/pdf")
        info_issues = [i for i in result.issues if i.rule == "FILENAME_SANITIZED"]
        assert len(info_issues) == 1
        assert result.metadata["sanitized_filename"] != "../evil.pdf"


# =============================================================================
# 9. Virus scan integration / embedded executable detection
# =============================================================================

@pytest.mark.unit
class TestVirusScanIntegration:
    """Verify that embedded executable indicators in PDFs are caught (proxy for virus scan)."""

    def test_embedded_exe_in_pdf_caught(self, engine):
        """PDF with /EmbeddedFile and .exe indicator should be flagged CRITICAL."""
        pdf = make_minimal_pdf(include_embedded_exe=True)
        issues = engine.validate_pdf_safety(pdf)
        exe_issues = [i for i in issues if i.rule == "PDF_EMBEDDED_EXECUTABLE"]
        assert len(exe_issues) == 1
        assert exe_issues[0].severity == "CRITICAL"

    def test_pdf_with_multiple_threats_all_reported(self, engine):
        """A PDF with JS, Launch, and embedded exe should report all threats."""
        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n")
        buf.write(b"1 0 obj\n<< /Type /Page >>\nendobj\n")
        buf.write(b"<< /JS (alert('x')) >>\n")
        buf.write(b"<< /S /Launch >>\n")
        buf.write(b"/EmbeddedFile /Subtype .exe\n")
        buf.write(b"%%EOF\n")
        content = buf.getvalue()
        content += b"\x00" * max(0, 1200 - len(content))

        issues = engine.validate_pdf_safety(content)
        rules = {i.rule for i in issues}
        assert "PDF_JAVASCRIPT" in rules
        assert "PDF_LAUNCH_ACTION" in rules
        assert "PDF_EMBEDDED_EXECUTABLE" in rules


# =============================================================================
# 10. Password-protected PDF handling
# =============================================================================

@pytest.mark.unit
class TestPasswordProtectedPdf:
    """Verify behavior with password-protected / encrypted PDFs."""

    def test_encrypted_pdf_structure_detected(self, engine):
        """
        An encrypted PDF typically has /Encrypt in its trailer.
        The engine does not parse full PDF structure, but we verify
        it does not crash on encrypted PDFs and that page count
        estimation may fail gracefully.
        """
        buf = io.BytesIO()
        buf.write(b"%PDF-1.6\n")
        buf.write(b"1 0 obj\n<< /Type /Page >>\nendobj\n")
        buf.write(b"2 0 obj\n<< /Type /Pages /Count 1 >>\nendobj\n")
        buf.write(b"3 0 obj\n<< /Encrypt /Standard >>\nendobj\n")
        buf.write(b"%%EOF\n")
        content = buf.getvalue()
        content += b"\x00" * max(0, 1200 - len(content))

        # Should not crash
        issues = engine.validate_pdf_safety(content)
        # No JavaScript or launch, so no critical issues from safety check
        critical_issues = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical_issues) == 0

    def test_encrypted_pdf_page_count_estimation(self, engine):
        """Page count estimation on an encrypted PDF should return a count or None, not crash."""
        buf = io.BytesIO()
        buf.write(b"%PDF-1.6\n")
        # Simulate encrypted content stream (garbled)
        buf.write(b"1 0 obj\n<< /Type /Page >>\nendobj\n")
        buf.write(b"%%EOF\n")
        content = buf.getvalue()
        content += b"\x00" * max(0, 1200 - len(content))

        page_count = engine._estimate_pdf_page_count(content)
        assert page_count is None or isinstance(page_count, int)


# =============================================================================
# 11. Corrupted file detection
# =============================================================================

@pytest.mark.unit
class TestCorruptedFileDetection:
    """Verify detection of corrupted or truncated files."""

    def test_truncated_pdf_detected_by_size(self, engine):
        """A truncated PDF (valid header but too small) should fail size check."""
        truncated = b"%PDF-1.4\n%%EOF"  # 14 bytes -- below 1024 min
        issues = engine.validate_file_size(truncated, "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_SIZE_TOO_SMALL" in rules

    def test_corrupted_jpeg_no_sof_handled(self, engine):
        """A JPEG with valid SOI but no SOF0 should not crash dimension extraction."""
        # SOI + random data + EOI
        corrupted = b"\xff\xd8\xff" + b"\x00" * 2048 + b"\xff\xd9"
        dims = engine._extract_jpeg_dimensions(corrupted)
        # Should return None gracefully, not crash
        assert dims is None

    def test_corrupted_png_truncated_ihdr(self, engine):
        """A PNG with truncated IHDR (< 24 bytes) should not crash dimension check."""
        truncated = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8  # Only 16 bytes, need >= 24
        issues = engine.validate_image_safety(truncated)
        # Should not crash; dimension check requires >= 24 bytes
        assert isinstance(issues, list)

    def test_random_bytes_with_pdf_mime_flagged(self, engine):
        """Random bytes declared as PDF should trigger magic mismatch."""
        random_data = b"\x01\x02\x03\x04" + b"\x00" * 2000
        issues = engine.validate_file_type(random_data, "data.pdf", "application/pdf")
        rules = [i.rule for i in issues]
        assert "FILE_TYPE_MAGIC_UNKNOWN" in rules or "FILE_TYPE_MAGIC_MISMATCH" in rules


# =============================================================================
# 12. Multi-page document validation
# =============================================================================

@pytest.mark.unit
class TestMultiPageValidation:
    """Verify page count estimation and validation for multi-page documents."""

    def test_pdf_page_count_estimation(self, engine):
        """_estimate_pdf_page_count should return the correct count for our test PDFs."""
        pdf_5 = make_minimal_pdf(page_count=5)
        count = engine._estimate_pdf_page_count(pdf_5)
        assert count == 5

    def test_pdf_single_page_estimation(self, engine):
        """Single-page PDF estimation."""
        pdf_1 = make_minimal_pdf(page_count=1)
        count = engine._estimate_pdf_page_count(pdf_1)
        assert count == 1

    def test_tiff_multi_page_estimation(self, engine):
        """Multi-page TIFF IFD chain should be correctly counted."""
        tiff_3 = make_minimal_tiff(page_count=3)
        count = engine._estimate_tiff_page_count(tiff_3)
        assert count == 3

    def test_page_count_too_few_for_doc_type(self, engine):
        """A 1-page PDF declared as BANK_STATEMENT (min 2) should flag PAGE_COUNT_TOO_FEW."""
        pdf = make_minimal_pdf(page_count=1)
        issues = engine.validate_page_count(pdf, "application/pdf", "BANK_STATEMENT")
        rules = [i.rule for i in issues]
        assert "PAGE_COUNT_TOO_FEW" in rules

    def test_page_count_too_many_for_doc_type(self, engine):
        """A 10-page PDF declared as W2 (max 4) should flag PAGE_COUNT_TOO_MANY."""
        pdf = make_minimal_pdf(page_count=10)
        issues = engine.validate_page_count(pdf, "application/pdf", "W2")
        rules = [i.rule for i in issues]
        assert "PAGE_COUNT_TOO_MANY" in rules

    def test_page_count_within_range_passes(self, engine):
        """A 2-page PDF declared as W2 (range 1-4) should pass."""
        pdf = make_minimal_pdf(page_count=2)
        issues = engine.validate_page_count(pdf, "application/pdf", "W2")
        assert len(issues) == 0

    def test_image_counts_as_single_page(self, engine):
        """Non-TIFF images should count as 1 page for page validation."""
        jpeg = make_minimal_jpeg()
        issues = engine.validate_page_count(jpeg, "image/jpeg", "DRIVERS_LICENSE")
        # DRIVERS_LICENSE expects 1-2 pages, single JPEG = 1 page, should pass
        assert len(issues) == 0

    def test_unknown_doc_type_skips_page_validation(self, engine):
        """A doc type with no entry in EXPECTED_PAGE_COUNTS should skip the check."""
        pdf = make_minimal_pdf(page_count=50)
        issues = engine.validate_page_count(pdf, "application/pdf", "UNKNOWN_TYPE")
        assert len(issues) == 0


# =============================================================================
# 13. Image resolution / dimension requirements
# =============================================================================

@pytest.mark.unit
class TestImageResolution:
    """Verify image dimension and resolution checks."""

    def test_jpeg_dimensions_extracted(self, engine):
        """JPEG dimension extraction should return correct width and height."""
        jpeg = make_minimal_jpeg(width=1920, height=1080)
        dims = engine._extract_jpeg_dimensions(jpeg)
        assert dims is not None
        assert dims == (1920, 1080)

    def test_png_dimensions_from_ihdr(self, engine):
        """PNG dimensions are read from IHDR at bytes 16-23."""
        png = make_minimal_png(width=2400, height=3200)
        # Manually verify bytes 16-23 encode the dimensions
        width = struct.unpack(">I", png[16:20])[0]
        height = struct.unpack(">I", png[20:24])[0]
        assert width == 2400
        assert height == 3200

    def test_very_small_image_no_crash(self, engine):
        """An image smaller than 20 bytes should not crash dimension extraction."""
        tiny = b"\xff\xd8\xff\xe0" + b"\x00" * 5
        dims = engine._extract_jpeg_dimensions(tiny)
        assert dims is None


# =============================================================================
# 14. File metadata / EXIF detection
# =============================================================================

@pytest.mark.unit
class TestMetadataDetection:
    """Verify detection of excessive or suspicious EXIF/metadata in images."""

    def test_large_exif_metadata_detected(self, engine):
        """JPEG with metadata > 50% of file size (and > 100KB) should be flagged."""
        buf = io.BytesIO()
        buf.write(b"\xff\xd8")
        # APP1 (Exif) segment with 150KB of data
        exif_data = b"\x00" * 150_000
        buf.write(b"\xff\xe1")
        buf.write(struct.pack(">H", len(exif_data) + 2))
        buf.write(exif_data)
        # SOS + minimal image data + EOI
        buf.write(b"\xff\xda")
        buf.write(struct.pack(">H", 8))
        buf.write(b"\x03\x01\x00\x02\x11\x03")
        buf.write(b"\x00" * 100)
        buf.write(b"\xff\xd9")
        content = buf.getvalue()

        issues = engine.validate_image_safety(content)
        rules = [i.rule for i in issues]
        assert "IMAGE_EXCESSIVE_METADATA" in rules

    def test_normal_metadata_not_flagged(self, engine, valid_jpeg):
        """A standard JPEG with small JFIF APP0 should not flag excessive metadata."""
        issues = engine.validate_image_safety(valid_jpeg)
        metadata_issues = [i for i in issues if i.rule == "IMAGE_EXCESSIVE_METADATA"]
        assert len(metadata_issues) == 0

    def test_jpeg_metadata_size_estimation(self, engine):
        """_estimate_jpeg_metadata_size should return a reasonable number."""
        jpeg = make_minimal_jpeg()
        size = engine._estimate_jpeg_metadata_size(jpeg)
        assert isinstance(size, int)
        assert size >= 0


# =============================================================================
# 15. Validation result reporting and scoring
# =============================================================================

@pytest.mark.unit
class TestValidationResultReporting:
    """Verify the overall validation result structure and scoring."""

    def test_clean_pdf_gets_high_score(self, engine, valid_pdf):
        """A clean, valid PDF should get a score near 100 and is_valid=True."""
        result = engine.validate_upload(valid_pdf, "paystub.pdf", "application/pdf", "PAYSTUB")
        assert result.is_valid is True
        assert result.score >= 80
        assert result.critical_count == 0

    def test_critical_issue_makes_invalid(self, engine):
        """Any CRITICAL issue should make is_valid=False."""
        exe_content = b"MZ" + b"\x00" * 2000  # DOS header magic
        result = engine.validate_upload(exe_content, "malware.exe", "application/pdf")
        assert result.is_valid is False
        assert result.critical_count > 0

    def test_score_deductions_correct(self, engine):
        """Verify the scoring formula: CRITICAL=-30, HIGH=-15, MEDIUM=-5, LOW=-2."""
        result = engine._build_result(
            issues=[
                ValidationIssue(rule="A", severity="CRITICAL", message="critical issue"),
                ValidationIssue(rule="B", severity="HIGH", message="high issue"),
                ValidationIssue(rule="C", severity="MEDIUM", message="medium issue"),
            ],
            passed_rules=["RULE_X"],
            metadata={},
        )
        # 100 - 30 - 15 - 5 = 50
        assert result.score == 50
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.is_valid is False  # has a CRITICAL

    def test_info_issues_dont_affect_score(self, engine):
        """INFO severity should not reduce the score."""
        result = engine._build_result(
            issues=[
                ValidationIssue(rule="INFO_TEST", severity="INFO", message="just info"),
            ],
            passed_rules=[],
            metadata={},
        )
        assert result.score == 100
        assert result.is_valid is True

    def test_to_dict_serialization(self, engine, valid_pdf):
        """ValidationResult.to_dict() should produce a valid serializable dict."""
        result = engine.validate_upload(valid_pdf, "doc.pdf", "application/pdf")
        d = result.to_dict()
        assert "is_valid" in d
        assert "score" in d
        assert "issues" in d
        assert "passed_rules" in d
        assert "metadata" in d
        assert isinstance(d["issues"], list)

    def test_metadata_includes_file_hash(self, engine, valid_pdf):
        """validate_upload should include SHA-256 hash in metadata."""
        result = engine.validate_upload(valid_pdf, "doc.pdf", "application/pdf")
        expected_hash = hashlib.sha256(valid_pdf).hexdigest()
        assert result.metadata["file_hash_sha256"] == expected_hash

    def test_metadata_includes_file_size(self, engine, valid_pdf):
        """validate_upload metadata should include the file size."""
        result = engine.validate_upload(valid_pdf, "doc.pdf", "application/pdf")
        assert result.metadata["file_size"] == len(valid_pdf)

    def test_passed_rules_tracked(self, engine, valid_pdf):
        """Passed validation rules should be recorded in the result."""
        result = engine.validate_upload(valid_pdf, "doc.pdf", "application/pdf")
        assert "FILE_TYPE" in result.passed_rules
        assert "FILE_SIZE" in result.passed_rules
        assert "CONTENT_SAFETY" in result.passed_rules

    def test_score_clamped_to_zero(self, engine):
        """Score should never go below 0 even with many critical issues."""
        issues = [
            ValidationIssue(rule=f"C{i}", severity="CRITICAL", message=f"critical {i}")
            for i in range(10)
        ]
        result = engine._build_result(issues=issues, passed_rules=[], metadata={})
        assert result.score == 0


# =============================================================================
# Freshness validation
# =============================================================================

@pytest.mark.unit
class TestFreshnessValidation:
    """Verify document age/freshness enforcement."""

    def test_fresh_paystub_passes(self, engine):
        """A paystub dated 10 days ago should pass (max 30 days)."""
        doc_date = datetime.now() - timedelta(days=10)
        issues = engine.validate_freshness("PAYSTUB", doc_date)
        assert len(issues) == 0

    def test_expired_paystub_flagged(self, engine):
        """A paystub dated 45 days ago should produce FRESHNESS_EXPIRED."""
        doc_date = datetime.now() - timedelta(days=45)
        issues = engine.validate_freshness("PAYSTUB", doc_date)
        rules = [i.rule for i in issues]
        assert "FRESHNESS_EXPIRED" in rules

    def test_expiring_soon_warning(self, engine):
        """A paystub dated 25 days ago (5 days from expiry) should warn."""
        doc_date = datetime.now() - timedelta(days=25)
        issues = engine.validate_freshness("PAYSTUB", doc_date)
        rules = [i.rule for i in issues]
        assert "FRESHNESS_EXPIRING_SOON" in rules

    def test_no_date_produces_warning(self, engine):
        """If doc_date is None, FRESHNESS_NO_DATE should be raised."""
        issues = engine.validate_freshness("PAYSTUB", None)
        rules = [i.rule for i in issues]
        assert "FRESHNESS_NO_DATE" in rules

    def test_unknown_doc_type_skips_freshness(self, engine):
        """A doc type not in FRESHNESS_RULES should produce no issues."""
        issues = engine.validate_freshness("UNKNOWN_TYPE", datetime.now())
        assert len(issues) == 0


# =============================================================================
# Completeness validation
# =============================================================================

@pytest.mark.unit
class TestCompletenessValidation:
    """Verify OCR text completeness checks for required fields."""

    def test_complete_paystub_passes(self, engine):
        """OCR text with all required paystub fields should pass."""
        ocr_text = """
        ACME Corporation
        Pay Period: 01/01/2026 - 01/15/2026
        Gross Pay: $5,000.00
        Net Pay: $3,750.00
        YTD Earnings: $10,000.00
        """
        issues = engine.validate_completeness("PAYSTUB", ocr_text)
        assert len(issues) == 0

    def test_missing_field_flagged(self, engine):
        """A paystub OCR missing 'net pay' should produce a completeness issue."""
        ocr_text = """
        ACME Corporation
        Pay Period: 01/01/2026 - 01/15/2026
        Gross Pay: $5,000.00
        YTD Earnings: $10,000.00
        """
        issues = engine.validate_completeness("PAYSTUB", ocr_text)
        rules = [i.rule for i in issues]
        assert "COMPLETENESS_MISSING_NET_PAY" in rules

    def test_empty_ocr_text_flagged(self, engine):
        """Empty OCR text should produce COMPLETENESS_NO_TEXT."""
        issues = engine.validate_completeness("PAYSTUB", "")
        rules = [i.rule for i in issues]
        assert "COMPLETENESS_NO_TEXT" in rules

    def test_none_ocr_text_flagged(self, engine):
        """None OCR text should produce COMPLETENESS_NO_TEXT."""
        issues = engine.validate_completeness("W2", None)
        rules = [i.rule for i in issues]
        assert "COMPLETENESS_NO_TEXT" in rules


# =============================================================================
# PII detection
# =============================================================================

@pytest.mark.unit
class TestPiiDetection:
    """Verify PII pattern detection in OCR text."""

    def test_full_ssn_detected(self, engine):
        """A full SSN (123-45-6789) should produce PII_FULL_SSN."""
        ocr_text = "Borrower SSN: 123-45-6789"
        issues = engine.validate_pii_handling(ocr_text)
        rules = [i.rule for i in issues]
        assert "PII_FULL_SSN" in rules

    def test_masked_ssn_not_flagged(self, engine):
        """A masked SSN (xxx-xx-6789) should still match the full_ssn pattern per regex."""
        # The pattern \d{3}-\d{2}-\d{4} would NOT match xxx-xx-6789
        ocr_text = "SSN: xxx-xx-6789"
        issues = engine.validate_pii_handling(ocr_text)
        ssn_issues = [i for i in issues if i.rule == "PII_FULL_SSN"]
        assert len(ssn_issues) == 0

    def test_empty_text_no_pii(self, engine):
        """Empty text should produce no PII issues."""
        issues = engine.validate_pii_handling("")
        assert len(issues) == 0


# =============================================================================
# Batch validation
# =============================================================================

@pytest.mark.unit
class TestBatchValidation:
    """Verify batch validation processes multiple documents."""

    def test_batch_returns_one_result_per_document(self, engine, valid_pdf, valid_jpeg):
        """batch_validate should return one ValidationResult per input document."""
        docs = [
            {"file_content": valid_pdf, "filename": "doc1.pdf", "mime_type": "application/pdf"},
            {"file_content": valid_jpeg, "filename": "photo.jpg", "mime_type": "image/jpeg"},
        ]
        results = engine.batch_validate(docs)
        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)


# =============================================================================
# Singleton factory
# =============================================================================

@pytest.mark.unit
class TestSingleton:
    """Verify the singleton factory function."""

    def test_get_document_validation_engine_returns_instance(self):
        """get_document_validation_engine should return a DocumentValidationEngine."""
        engine = get_document_validation_engine()
        assert isinstance(engine, DocumentValidationEngine)

    def test_singleton_returns_same_instance(self):
        """Repeated calls should return the same instance."""
        e1 = get_document_validation_engine()
        e2 = get_document_validation_engine()
        assert e1 is e2


# =============================================================================
# Rule introspection
# =============================================================================

@pytest.mark.unit
class TestRuleIntrospection:
    """Verify the get_validation_rules_for_type endpoint."""

    def test_rules_for_paystub(self, engine):
        """get_validation_rules_for_type should return freshness, pages, and fields for PAYSTUB."""
        rules = engine.get_validation_rules_for_type("PAYSTUB")
        assert rules["doc_type"] == "PAYSTUB"
        assert rules["freshness_days"] == 30
        assert rules["expected_page_range"]["min"] == 1
        assert rules["expected_page_range"]["max"] == 4
        assert len(rules["required_fields"]) > 0
        assert len(rules["allowed_mime_types"]) > 0

    def test_rules_for_unknown_type(self, engine):
        """Unknown doc type should return None for freshness and pages."""
        rules = engine.get_validation_rules_for_type("RANDOM_TYPE")
        assert rules["freshness_days"] is None
        assert rules["expected_page_range"]["min"] is None
