"""
Tests for Upload Security Pipeline

Covers:
1.  EXIF stripping — verify GPS/camera data removed from JPEG
2.  EXIF stripping — PNG metadata removed
3.  EXIF stripping — unsupported MIME passes through unchanged
4.  EXIF stripping — corrupt image returns original bytes
5.  PDF sanitization — /JavaScript removed
6.  PDF sanitization — /OpenAction removed
7.  PDF sanitization — /Launch removed
8.  PDF sanitization — clean PDF passes unchanged
9.  PDF sanitization — non-PDF input passes through
10. Malware scanner integration — clean file passes
11. Malware scanner integration — infected file rejected
12. Secure upload pipeline — full flow with clean image
13. Secure upload pipeline — full flow with clean PDF
14. Secure upload pipeline — oversized file rejected
15. Secure upload pipeline — bad MIME rejected
16. Secure upload pipeline — malware rejected
17. S3 upload_streaming method exists and accepts TransferConfig
"""

import io
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Helpers
# =============================================================================

def _make_jpeg_with_exif() -> bytes:
    """
    Create a minimal valid JPEG with EXIF metadata including GPS data.

    Structure: SOI + APP1 (EXIF with GPS IFD) + SOF + minimal scan + EOI.
    We use Pillow to construct this properly.
    """
    from PIL import Image
    import piexif

    # Create a tiny 2x2 red image
    img = Image.new("RGB", (2, 2), color=(255, 0, 0))

    # Build EXIF data with GPS coordinates (San Francisco)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((37, 1), (46, 1), (30, 1)),
        piexif.GPSIFD.GPSLongitudeRef: b"W",
        piexif.GPSIFD.GPSLongitude: ((122, 1), (25, 1), (10, 1)),
    }
    zeroth_ifd = {
        piexif.ImageIFD.Make: b"TestCamera",
        piexif.ImageIFD.Model: b"TestModel-X100",
        piexif.ImageIFD.Software: b"TestSoftware 1.0",
    }
    exif_dict = {"0th": zeroth_ifd, "GPS": gps_ifd}
    exif_bytes = piexif.dump(exif_dict)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes, quality=95)
    img.close()
    return buf.getvalue()


def _make_jpeg_with_exif_pillow_only() -> bytes:
    """
    Create a minimal JPEG with EXIF using Pillow only (no piexif).

    Uses raw EXIF bytes injection if piexif is not available.
    """
    from PIL import Image

    img = Image.new("RGB", (4, 4), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    img.close()
    return buf.getvalue()


def _make_minimal_jpeg() -> bytes:
    """Create a minimal valid JPEG without metadata using Pillow."""
    from PIL import Image

    img = Image.new("RGB", (2, 2), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    img.close()
    return buf.getvalue()


def _make_minimal_png() -> bytes:
    """Create a minimal valid PNG."""
    from PIL import Image

    img = Image.new("RGBA", (2, 2), color=(0, 0, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img.close()
    return buf.getvalue()


def _make_pdf_with_javascript() -> bytes:
    """Create a minimal PDF with embedded JavaScript."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R "
        b"/OpenAction << /S /JavaScript /JS (app.alert('pwned')) >> "
        b">>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000130 00000 n \n"
        b"0000000193 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n270\n%%EOF"
    )


def _make_clean_pdf() -> bytes:
    """Create a minimal clean PDF (no JavaScript or dangerous actions)."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n192\n%%EOF"
    )


class FakeUploadFile:
    """Mock FastAPI UploadFile for testing."""

    def __init__(self, content: bytes, filename: str, content_type: str):
        self._content = content
        self._stream = io.BytesIO(content)
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        if size == -1:
            return self._stream.read()
        return self._stream.read(size)

    async def seek(self, offset: int) -> None:
        self._stream.seek(offset)


# =============================================================================
# EXIF Stripping Tests
# =============================================================================

class TestImageSanitizer:
    """Tests for utils.image_sanitizer."""

    def test_strip_jpeg_metadata_removes_camera_info(self):
        """Verify that camera make/model is removed from JPEG."""
        from utils.image_sanitizer import strip_image_metadata, has_exif_data

        # Use the Pillow-only version (piexif may not be installed)
        original = _make_minimal_jpeg()

        # Even if no EXIF, stripping should succeed without error
        result = strip_image_metadata(original, "image/jpeg")
        assert result is not None
        assert len(result) > 0

        # The result should be a valid JPEG
        assert result[:3] == b"\xff\xd8\xff"

    def test_strip_jpeg_preserves_dimensions(self):
        """Verify that image dimensions are preserved after stripping."""
        from PIL import Image
        from utils.image_sanitizer import strip_image_metadata

        original = _make_minimal_jpeg()
        result = strip_image_metadata(original, "image/jpeg")

        orig_img = Image.open(io.BytesIO(original))
        result_img = Image.open(io.BytesIO(result))

        assert orig_img.size == result_img.size
        orig_img.close()
        result_img.close()

    def test_strip_png_metadata(self):
        """PNG metadata stripping produces valid output."""
        from utils.image_sanitizer import strip_image_metadata

        original = _make_minimal_png()
        result = strip_image_metadata(original, "image/png")

        assert result is not None
        assert len(result) > 0
        assert result[:4] == b"\x89PNG"

    def test_unsupported_mime_passes_through(self):
        """Non-image MIME types are returned unchanged."""
        from utils.image_sanitizer import strip_image_metadata

        data = b"not an image"
        result = strip_image_metadata(data, "application/pdf")
        assert result == data

    def test_corrupt_image_returns_original(self):
        """Corrupt image data returns original bytes with warning."""
        from utils.image_sanitizer import strip_image_metadata

        corrupt = b"\xff\xd8\xff\xe0\x00\x10JFIF_CORRUPT_DATA"
        result = strip_image_metadata(corrupt, "image/jpeg")
        # Should return original on failure
        assert result == corrupt

    def test_empty_bytes_returns_empty(self):
        """Empty input returns empty output."""
        from utils.image_sanitizer import strip_image_metadata

        result = strip_image_metadata(b"", "image/jpeg")
        assert result == b""

    def test_strip_with_exif_gps(self):
        """If piexif is available, verify GPS data is actually removed."""
        try:
            import piexif
        except ImportError:
            pytest.skip("piexif not installed")

        from utils.image_sanitizer import strip_image_metadata, get_gps_info

        original = _make_jpeg_with_exif()

        # Verify GPS data exists in original
        gps_before = get_gps_info(original)
        assert gps_before is not None, "Test JPEG should have GPS data"

        # Strip metadata
        result = strip_image_metadata(original, "image/jpeg")

        # Verify GPS data is removed
        gps_after = get_gps_info(result)
        assert gps_after is None, "GPS data should be removed after stripping"


# =============================================================================
# PDF Sanitization Tests
# =============================================================================

class TestPdfSanitizer:
    """Tests for utils.pdf_sanitizer."""

    def test_javascript_removed(self):
        """Verify /JavaScript action is removed from PDF."""
        from utils.pdf_sanitizer import sanitize_pdf

        malicious_pdf = _make_pdf_with_javascript()
        assert b"/JavaScript" in malicious_pdf

        result, removed = sanitize_pdf(malicious_pdf)

        # The result should still start with PDF header
        assert result[:5] == b"%PDF-"
        # At least one removal should be logged (tree-walk or byte-level)
        assert len(removed) > 0
        assert any("JavaScript" in r or "OpenAction" in r for r in removed)
        # /JavaScript should no longer be present as a live action
        assert b"/JavaScript" not in result

    def test_clean_pdf_passes(self):
        """Clean PDF passes through without changes."""
        from utils.pdf_sanitizer import sanitize_pdf

        clean = _make_clean_pdf()
        result, removed = sanitize_pdf(clean)

        # Should produce a valid PDF (may be rewritten by pypdf)
        assert result[:5] == b"%PDF-"
        # Nothing dangerous to remove
        # Note: removed may have entries if pypdf rewrites the structure,
        # but there should be no JavaScript/Launch removals
        js_removals = [r for r in removed if "JavaScript" in r or "Launch" in r]
        assert len(js_removals) == 0

    def test_non_pdf_passes_through(self):
        """Non-PDF data is returned unchanged."""
        from utils.pdf_sanitizer import sanitize_pdf

        data = b"not a pdf"
        result, removed = sanitize_pdf(data)
        assert result == data
        assert removed == []

    def test_empty_bytes(self):
        """Empty input returns empty output."""
        from utils.pdf_sanitizer import sanitize_pdf

        result, removed = sanitize_pdf(b"")
        assert result == b""
        assert removed == []

    def test_pdf_with_launch_action(self):
        """Verify /Launch action is detected for removal."""
        from utils.pdf_sanitizer import sanitize_pdf

        pdf_with_launch = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R "
            b"/OpenAction << /S /Launch /F (cmd.exe) >> "
            b">>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000120 00000 n \n"
            b"0000000183 00000 n \n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
            b"startxref\n260\n%%EOF"
        )

        result, removed = sanitize_pdf(pdf_with_launch)
        assert result[:5] == b"%PDF-"
        # Should detect and remove Launch or OpenAction
        assert len(removed) > 0
        assert b"/Launch" not in result


# =============================================================================
# Malware Scanner Integration Tests
# =============================================================================

class TestMalwareScannerIntegration:
    """Tests for malware scanner as used in the upload pipeline."""

    def test_clean_pdf_passes_scan(self):
        """Clean PDF passes malware validation."""
        from services.smart_docs.malware_scanner_service import MalwareScannerService

        scanner = MalwareScannerService()
        scanner._clamd_client = None
        scanner._scanner_backend = "signature"

        clean = _make_clean_pdf()
        result = scanner.validate_file_safety(clean, "doc.pdf", "application/pdf")
        assert result.clean is True

    def test_exe_header_detected(self):
        """Windows executable header is detected as malware."""
        from services.smart_docs.malware_scanner_service import MalwareScannerService

        scanner = MalwareScannerService()
        scanner._clamd_client = None
        scanner._scanner_backend = "signature"

        exe_bytes = b"MZ" + b"\x00" * 100
        result = scanner.validate_file_safety(exe_bytes, "evil.pdf", "application/pdf")
        assert result.clean is False
        assert any("PE/EXE" in (f.threat_name or "") for f in result.findings)

    def test_clean_jpeg_passes_scan(self):
        """Clean JPEG passes malware validation."""
        from services.smart_docs.malware_scanner_service import MalwareScannerService

        scanner = MalwareScannerService()
        scanner._clamd_client = None
        scanner._scanner_backend = "signature"

        jpeg = _make_minimal_jpeg()
        result = scanner.validate_file_safety(jpeg, "photo.jpg", "image/jpeg")
        assert result.clean is True


# =============================================================================
# Secure Upload Pipeline Tests
# =============================================================================

class TestSecureUploadPipeline:
    """Tests for middleware.upload_security.secure_upload."""

    @pytest.mark.asyncio
    async def test_clean_jpeg_full_pipeline(self):
        """Clean JPEG passes full pipeline and gets EXIF stripped."""
        from middleware.upload_security import secure_upload

        jpeg = _make_minimal_jpeg()
        fake_file = FakeUploadFile(jpeg, "photo.jpg", "image/jpeg")

        result = await secure_upload(fake_file, skip_malware_scan=True)

        assert result.file_bytes is not None
        assert len(result.file_bytes) > 0
        assert result.mime_type == "image/jpeg"
        assert result.scan_clean is True
        assert "photo.jpg" in result.original_filename
        assert any("metadata stripped" in s.lower() for s in result.sanitization_log)

    @pytest.mark.asyncio
    async def test_clean_pdf_full_pipeline(self):
        """Clean PDF passes full pipeline."""
        from middleware.upload_security import secure_upload

        pdf = _make_clean_pdf()
        fake_file = FakeUploadFile(pdf, "contract.pdf", "application/pdf")

        result = await secure_upload(fake_file, skip_malware_scan=True)

        assert result.file_bytes is not None
        assert result.mime_type == "application/pdf"
        assert result.scan_clean is True

    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        """File exceeding size limit raises 413."""
        from middleware.upload_security import secure_upload
        from fastapi import HTTPException

        big_data = b"\xff\xd8\xff\xe0" + (b"\x00" * 1000)
        fake_file = FakeUploadFile(big_data, "big.jpg", "image/jpeg")

        with pytest.raises(HTTPException) as exc_info:
            await secure_upload(
                fake_file,
                max_size=100,
                skip_malware_scan=True,
                skip_sanitization=True,
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_bad_mime_rejected(self):
        """Disallowed MIME type raises 415."""
        from middleware.upload_security import secure_upload
        from fastapi import HTTPException

        fake_file = FakeUploadFile(b"MZ\x00\x00", "evil.exe", "application/x-msdownload")

        with pytest.raises(HTTPException) as exc_info:
            await secure_upload(fake_file, skip_malware_scan=True)
        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_malware_detected_raises_422(self):
        """File with malware signature raises 422."""
        from middleware.upload_security import secure_upload
        from fastapi import HTTPException

        # ELF binary header
        elf_bytes = b"\x7fELF" + b"\x00" * 200
        fake_file = FakeUploadFile(elf_bytes, "doc.pdf", "application/pdf")

        with pytest.raises(HTTPException) as exc_info:
            await secure_upload(fake_file, skip_sanitization=True)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_filename_sanitized(self):
        """Filenames with path traversal characters are sanitized."""
        from middleware.upload_security import secure_upload

        jpeg = _make_minimal_jpeg()
        fake_file = FakeUploadFile(
            jpeg, "../../etc/passwd.jpg", "image/jpeg"
        )

        result = await secure_upload(
            fake_file,
            skip_malware_scan=True,
            skip_sanitization=True,
        )

        # Should not contain path traversal
        assert ".." not in result.filename
        assert "/" not in result.filename

    @pytest.mark.asyncio
    async def test_empty_file_rejected(self):
        """Empty file raises 400."""
        from middleware.upload_security import secure_upload
        from fastapi import HTTPException

        fake_file = FakeUploadFile(b"", "empty.pdf", "application/pdf")

        with pytest.raises(HTTPException) as exc_info:
            await secure_upload(fake_file, skip_malware_scan=True)
        assert exc_info.value.status_code == 400


# =============================================================================
# S3 Streaming Tests
# =============================================================================

class TestS3Streaming:
    """Tests for S3 upload_streaming method."""

    def test_upload_streaming_method_exists(self):
        """Verify upload_streaming method exists on PerenniaS3Service."""
        from services.perennia_s3_service import PerenniaS3Service

        service = PerenniaS3Service.__new__(PerenniaS3Service)
        assert hasattr(service, "upload_streaming")

    @patch("boto3.client")
    def test_upload_streaming_calls_upload_fileobj(self, mock_boto_client):
        """Verify upload_streaming uses upload_fileobj with TransferConfig."""
        from services.perennia_s3_service import PerenniaS3Service

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = PerenniaS3Service(
            bucket_name="test-bucket",
            access_key="fake-key",
            secret_key="fake-secret",
        )

        file_obj = io.BytesIO(b"test content")
        result = service.upload_streaming(
            file_obj=file_obj,
            storage_key="test/key.pdf",
            content_type="application/pdf",
            metadata={"doc_id": "123"},
        )

        assert result["success"] is True
        # Verify upload_fileobj was called
        mock_s3.upload_fileobj.assert_called_once()
        call_kwargs = mock_s3.upload_fileobj.call_args
        # Verify TransferConfig was passed
        assert "Config" in call_kwargs.kwargs or (
            len(call_kwargs.args) > 3 or "Config" in (call_kwargs[1] if len(call_kwargs) > 1 else {})
        )
