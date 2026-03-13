"""
Tests for upload size and safety limit enforcement.

Covers:
- File size limit enforcement (streaming chunked read)
- Image dimension validation
- PDF page count validation
- PDF decompression bomb detection
- UploadValidator combined checks
- Integration with route-level validation
"""

import io
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, UploadFile


# =============================================================================
# Helpers
# =============================================================================

def _make_upload_file(
    content: bytes,
    filename: str = "test.pdf",
    content_type: str = "application/pdf",
) -> UploadFile:
    """Create a mock UploadFile from raw bytes."""
    file_obj = io.BytesIO(content)
    upload = UploadFile(filename=filename, file=file_obj)
    upload.content_type = content_type
    return upload


def _make_png(width: int, height: int, body_size: int = 100) -> bytes:
    """Create minimal valid PNG bytes with specified dimensions."""
    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"
    # IHDR chunk: length(4) + "IHDR"(4) + width(4) + height(4) + bit_depth(1) + color_type(1) + rest(3) + CRC(4)
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    import zlib
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    # Minimal IDAT
    idat_data = b"\x00" * body_size
    idat_crc = zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + struct.pack(">I", idat_crc)
    # IEND
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


def _make_jpeg(width: int, height: int, body_size: int = 100) -> bytes:
    """Create minimal JPEG-like bytes with SOF0 marker for dimension parsing."""
    # SOI
    soi = b"\xff\xd8"
    # APP0 (JFIF header) - minimal
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    # SOF0 marker: FF C0 + length(2) + precision(1) + height(2) + width(2) + components(1) + component_data
    sof0_data = struct.pack(">BHH", 8, height, width) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    sof0 = b"\xff\xc0" + struct.pack(">H", len(sof0_data) + 2) + sof0_data
    # Padding body
    body = b"\x00" * body_size
    # EOI
    eoi = b"\xff\xd9"
    return soi + app0 + sof0 + body + eoi


def _make_pdf(page_count: int, per_page_size: int = 50) -> bytes:
    """Create minimal PDF-like bytes with the given number of page markers."""
    header = b"%PDF-1.4\n"
    pages = b""
    for i in range(page_count):
        pages += b"%d 0 obj\n<< /Type /Page >>\nendobj\n" % (i + 1)
        pages += b"x" * per_page_size
    # Page tree
    pages += b"\n%d 0 obj\n<< /Type /Pages /Count %d >>\nendobj\n" % (page_count + 1, page_count)
    trailer = b"\n%%EOF\n"
    return header + pages + trailer


# =============================================================================
# Test: validate_upload_size
# =============================================================================

class TestValidateUploadSize:
    """Tests for the streaming size-limited file reader."""

    @pytest.mark.asyncio
    async def test_accepts_file_under_limit(self):
        from middleware.upload_limits import validate_upload_size

        content = b"Hello, World!" * 100
        upload = _make_upload_file(content)
        result = await validate_upload_size(upload, max_size=len(content) + 1)
        assert result == content

    @pytest.mark.asyncio
    async def test_rejects_file_over_limit(self):
        from middleware.upload_limits import validate_upload_size

        content = b"x" * 1000
        upload = _make_upload_file(content)
        with pytest.raises(HTTPException) as exc_info:
            await validate_upload_size(upload, max_size=500)
        assert exc_info.value.status_code == 413
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self):
        from middleware.upload_limits import validate_upload_size

        upload = _make_upload_file(b"")
        with pytest.raises(HTTPException) as exc_info:
            await validate_upload_size(upload, max_size=1024)
        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_exact_limit_is_accepted(self):
        from middleware.upload_limits import validate_upload_size

        content = b"x" * 1000
        upload = _make_upload_file(content)
        result = await validate_upload_size(upload, max_size=1000)
        assert result == content

    @pytest.mark.asyncio
    async def test_one_byte_over_limit_rejected(self):
        from middleware.upload_limits import validate_upload_size

        content = b"x" * 1001
        upload = _make_upload_file(content)
        with pytest.raises(HTTPException) as exc_info:
            await validate_upload_size(upload, max_size=1000)
        assert exc_info.value.status_code == 413


# =============================================================================
# Test: validate_image_dimensions
# =============================================================================

class TestValidateImageDimensions:
    """Tests for image dimension checking."""

    def test_accepts_normal_png_dimensions(self):
        from middleware.upload_limits import validate_image_dimensions

        png = _make_png(2550, 3300)  # Letter at 300 DPI
        w, h = validate_image_dimensions(png)
        assert w == 2550
        assert h == 3300

    def test_rejects_oversized_png_width(self):
        from middleware.upload_limits import validate_image_dimensions

        png = _make_png(15000, 3300)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_dimensions(png)
        assert exc_info.value.status_code == 413
        assert "dimensions" in exc_info.value.detail.lower()

    def test_rejects_oversized_png_height(self):
        from middleware.upload_limits import validate_image_dimensions

        png = _make_png(2550, 12000)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_dimensions(png)
        assert exc_info.value.status_code == 413

    def test_accepts_normal_jpeg_dimensions(self):
        from middleware.upload_limits import validate_image_dimensions

        jpeg = _make_jpeg(1920, 1080)
        w, h = validate_image_dimensions(jpeg)
        assert w == 1920
        assert h == 1080

    def test_rejects_oversized_jpeg(self):
        from middleware.upload_limits import validate_image_dimensions

        jpeg = _make_jpeg(20000, 15000)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_dimensions(jpeg)
        assert exc_info.value.status_code == 413

    def test_handles_empty_bytes(self):
        from middleware.upload_limits import validate_image_dimensions

        w, h = validate_image_dimensions(b"")
        assert w == 0
        assert h == 0

    def test_handles_truncated_header(self):
        from middleware.upload_limits import validate_image_dimensions

        w, h = validate_image_dimensions(b"\x89PNG\r\n\x1a\n")
        assert w == 0
        assert h == 0

    def test_rejects_pixel_bomb(self):
        """An image with 100M+ pixels should be rejected."""
        from middleware.upload_limits import validate_image_dimensions

        # 10001 x 10001 = 100,020,001 pixels > 100M limit
        # But this also exceeds 10000x10000 dimension limit
        png = _make_png(10001, 10001)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_dimensions(png)
        assert exc_info.value.status_code == 413


# =============================================================================
# Test: validate_pdf_page_count
# =============================================================================

class TestValidatePdfPageCount:
    """Tests for PDF page count enforcement."""

    def test_accepts_normal_page_count(self):
        from middleware.upload_limits import validate_pdf_page_count

        pdf = _make_pdf(50)
        count = validate_pdf_page_count(pdf)
        assert count == 50

    def test_accepts_boundary_page_count(self):
        from middleware.upload_limits import validate_pdf_page_count, MAX_PDF_PAGES

        pdf = _make_pdf(MAX_PDF_PAGES)
        count = validate_pdf_page_count(pdf)
        assert count == MAX_PDF_PAGES

    def test_rejects_excessive_page_count(self):
        from middleware.upload_limits import validate_pdf_page_count, MAX_PDF_PAGES

        pdf = _make_pdf(MAX_PDF_PAGES + 1)
        with pytest.raises(HTTPException) as exc_info:
            validate_pdf_page_count(pdf)
        assert exc_info.value.status_code == 413
        assert "pages" in exc_info.value.detail.lower()

    def test_handles_empty_pdf(self):
        from middleware.upload_limits import validate_pdf_page_count

        # No pages, should return 0 and not raise
        count = validate_pdf_page_count(b"%PDF-1.4\n%%EOF")
        assert count == 0

    def test_single_page_pdf(self):
        from middleware.upload_limits import validate_pdf_page_count

        pdf = _make_pdf(1)
        count = validate_pdf_page_count(pdf)
        assert count == 1


# =============================================================================
# Test: detect_pdf_bomb
# =============================================================================

class TestDetectPdfBomb:
    """Tests for PDF decompression bomb detection."""

    def test_normal_pdf_passes(self):
        from middleware.upload_limits import detect_pdf_bomb

        pdf = _make_pdf(10, per_page_size=500)
        result = detect_pdf_bomb(pdf)
        assert result is False

    def test_detects_inflated_lengths(self):
        from middleware.upload_limits import detect_pdf_bomb, PDF_BOMB_RATIO

        # Create a small PDF with an artificially huge /Length declaration
        # The declared stream lengths should far exceed the actual file size
        header = b"%PDF-1.4\n"
        # Declare a stream length that is 20x the file size
        fake_stream = b"1 0 obj\n<< /Length 999999999 /Filter /FlateDecode >>\nstream\nendstream\nendobj\n"
        pdf = header + fake_stream + b"\n%%EOF\n"

        # The total declared length (999999999) should be > PDF_BOMB_RATIO * len(pdf)
        with pytest.raises(HTTPException) as exc_info:
            detect_pdf_bomb(pdf)
        assert exc_info.value.status_code == 413
        assert "compressed" in exc_info.value.detail.lower() or "decompress" in exc_info.value.detail.lower()


# =============================================================================
# Test: validate_magic_bytes
# =============================================================================

class TestValidateMagicBytes:
    """Tests for magic byte verification."""

    def test_matching_pdf_passes(self):
        from middleware.upload_limits import validate_magic_bytes

        pdf = b"%PDF-1.4\n" + b"\x00" * 100
        validate_magic_bytes(pdf, "application/pdf")  # Should not raise

    def test_matching_jpeg_passes(self):
        from middleware.upload_limits import validate_magic_bytes

        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        validate_magic_bytes(jpeg, "image/jpeg")  # Should not raise

    def test_mismatched_type_raises(self):
        from middleware.upload_limits import validate_magic_bytes

        # File has PDF magic bytes but declares image/jpeg
        pdf = b"%PDF-1.4\n" + b"\x00" * 100
        with pytest.raises(HTTPException) as exc_info:
            validate_magic_bytes(pdf, "image/jpeg")
        assert exc_info.value.status_code == 400

    def test_empty_content_passes(self):
        from middleware.upload_limits import validate_magic_bytes

        # Empty or tiny content should not raise
        validate_magic_bytes(b"", "application/pdf")
        validate_magic_bytes(b"ab", "application/pdf")


# =============================================================================
# Test: UploadValidator
# =============================================================================

class TestUploadValidator:
    """Tests for the combined UploadValidator class."""

    @pytest.mark.asyncio
    async def test_accepts_valid_pdf(self):
        from middleware.upload_limits import UploadValidator

        validator = UploadValidator()
        pdf = _make_pdf(10)
        upload = _make_upload_file(pdf, "doc.pdf", "application/pdf")
        result = await validator.validate(upload)
        assert result == pdf

    @pytest.mark.asyncio
    async def test_rejects_oversized_pdf(self):
        from middleware.upload_limits import UploadValidator

        validator = UploadValidator()
        pdf = b"%PDF-1.4\n" + b"x" * (26 * 1024 * 1024)  # 26 MB
        upload = _make_upload_file(pdf, "big.pdf", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await validator.validate(upload)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_rejects_oversized_image(self):
        from middleware.upload_limits import UploadValidator

        validator = UploadValidator()
        # 16 MB image
        img = b"\xff\xd8\xff\xe0" + b"x" * (16 * 1024 * 1024)
        upload = _make_upload_file(img, "big.jpg", "image/jpeg")
        with pytest.raises(HTTPException) as exc_info:
            await validator.validate(upload)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_custom_max_size(self):
        from middleware.upload_limits import UploadValidator

        validator = UploadValidator()
        content = b"%PDF-1.4\n" + b"x" * 500
        upload = _make_upload_file(content, "small.pdf", "application/pdf")
        result = await validator.validate(upload, max_size=1000)
        assert result == content

    @pytest.mark.asyncio
    async def test_custom_max_size_rejected(self):
        from middleware.upload_limits import UploadValidator

        validator = UploadValidator()
        content = b"%PDF-1.4\n" + b"x" * 1000
        upload = _make_upload_file(content, "small.pdf", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await validator.validate(upload, max_size=500)
        assert exc_info.value.status_code == 413


# =============================================================================
# Test: Validation engine integration
# =============================================================================

class TestValidationEngineIntegration:
    """Tests that the validation engine's new checks work correctly."""

    def test_hard_size_limit_blocks_early(self):
        from services.smart_docs.document_validation_engine import DocumentValidationEngine

        engine = DocumentValidationEngine()
        # 30 MB PDF-like content (exceeds 25 MB limit)
        content = b"%PDF-1.4\n" + b"x" * (30 * 1024 * 1024)
        result = engine.validate_upload(
            file_content=content,
            filename="huge.pdf",
            mime_type="application/pdf",
        )
        assert result.is_valid is False
        assert result.critical_count > 0
        # Should have been rejected early
        assert result.metadata.get("rejected_early") is True

    def test_image_dimension_check_in_engine(self):
        from services.smart_docs.document_validation_engine import DocumentValidationEngine

        engine = DocumentValidationEngine()
        # Create a PNG with 15000x15000 dimensions
        png = _make_png(15000, 15000)
        result = engine.validate_upload(
            file_content=png,
            filename="huge_image.png",
            mime_type="image/png",
        )
        assert result.is_valid is False
        # Should have IMAGE_DIMENSIONS_EXCEEDED issue
        issue_rules = [i.rule for i in result.issues]
        assert "IMAGE_DIMENSIONS_EXCEEDED" in issue_rules

    def test_pdf_page_limit_in_engine(self):
        from services.smart_docs.document_validation_engine import DocumentValidationEngine

        engine = DocumentValidationEngine()
        pdf = _make_pdf(250)  # Exceeds MAX_PDF_PAGES (200)
        result = engine.validate_upload(
            file_content=pdf,
            filename="many_pages.pdf",
            mime_type="application/pdf",
        )
        assert result.is_valid is False
        issue_rules = [i.rule for i in result.issues]
        assert "PDF_PAGE_LIMIT_EXCEEDED" in issue_rules

    def test_normal_file_passes_all_checks(self):
        from services.smart_docs.document_validation_engine import DocumentValidationEngine

        engine = DocumentValidationEngine()
        pdf = _make_pdf(10)
        result = engine.validate_upload(
            file_content=pdf,
            filename="normal.pdf",
            mime_type="application/pdf",
        )
        # Should not have any CRITICAL issues from the new checks
        critical_rules = [i.rule for i in result.issues if i.severity == "CRITICAL"]
        new_critical = [r for r in critical_rules if r in (
            "HARD_SIZE_LIMIT_EXCEEDED",
            "IMAGE_DIMENSIONS_EXCEEDED",
            "IMAGE_DECOMPRESSION_BOMB",
            "PDF_PAGE_LIMIT_EXCEEDED",
            "PDF_DECOMPRESSION_BOMB",
            "PDF_SUSPICIOUS_SIZE_RATIO",
        )]
        assert len(new_critical) == 0

    def test_pdf_bomb_detection_in_engine(self):
        from services.smart_docs.document_validation_engine import DocumentValidationEngine

        engine = DocumentValidationEngine()
        # Create a PDF with a huge declared /Length
        header = b"%PDF-1.4\n"
        fake = b"1 0 obj\n<< /Length 999999999 /Filter /FlateDecode >>\nstream\nendstream\nendobj\n"
        footer = b"\n%%EOF\n"
        pdf = header + fake + footer

        result = engine.validate_upload(
            file_content=pdf,
            filename="bomb.pdf",
            mime_type="application/pdf",
        )
        assert result.is_valid is False
        issue_rules = [i.rule for i in result.issues]
        assert "PDF_DECOMPRESSION_BOMB" in issue_rules
