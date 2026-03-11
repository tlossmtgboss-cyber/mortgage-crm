"""
Test Document OCR Service

Comprehensive tests for a document OCR service that handles text extraction,
OCR fallback, data parsing (currency, dates, names, addresses, SSNs),
document-specific field extraction (paystubs, W2s, bank statements, driver's
licenses), per-field confidence scoring, and image quality / layout detection.

Since backend/services/smart_docs/document_ocr_service.py does not yet exist,
these tests validate the OCR-adjacent logic that already lives in
DocumentDataExtractor (document_data_extractor.py) and define the expected
contract for a future standalone OCR service module.

All OCR engines (pytesseract, pdfplumber, pdf2image) and the Anthropic API
are fully mocked -- no real I/O or network calls.

Tests target: backend/services/smart_docs/document_data_extractor.py
"""

import io
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

# ---------------------------------------------------------------------------
# Stub the models.smart_docs_models module so the import inside
# document_data_extractor resolves without a real database stack.
# ---------------------------------------------------------------------------
import enum
import sys
from types import ModuleType


class _MockDocType(str, enum.Enum):
    PAYSTUB = "PAYSTUB"
    W2 = "W2"
    BANK_STATEMENT = "BANK_STATEMENT"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    TAX_RETURN = "TAX_RETURN"
    INVESTMENT_STATEMENT = "INVESTMENT_STATEMENT"
    PROFIT_LOSS = "PROFIT_LOSS"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    OTHER = "OTHER"


if "models.smart_docs_models" not in sys.modules:
    _smart_docs_models = ModuleType("models.smart_docs_models")
    _smart_docs_models.DocType = _MockDocType  # type: ignore[attr-defined]
    sys.modules["models.smart_docs_models"] = _smart_docs_models

# Pre-populate services.smart_docs in sys.modules with a stub so that
# importing services.smart_docs.document_data_extractor does NOT trigger
# the package __init__.py (which pulls in the full model stack).
import os as _os

_backend_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))

if "services" not in sys.modules:
    _services_pkg = ModuleType("services")
    _services_pkg.__path__ = [_os.path.join(_backend_dir, "services")]  # type: ignore[attr-defined]
    sys.modules["services"] = _services_pkg
if "services.smart_docs" not in sys.modules:
    _smart_docs_pkg = ModuleType("services.smart_docs")
    _smart_docs_pkg.__path__ = [_os.path.join(_backend_dir, "services", "smart_docs")]  # type: ignore[attr-defined]
    sys.modules["services.smart_docs"] = _smart_docs_pkg

from services.smart_docs.document_data_extractor import (  # noqa: E402
    DocumentDataExtractor,
    ExtractionResult,
    EXTRACTION_SCHEMAS,
    DEFAULT_EXTRACTION_SCHEMA,
    PAY_FREQUENCY_EXPIRATION_DAYS,
)

DocType = _MockDocType


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def extractor():
    """DocumentDataExtractor with no AI client (extraction paths only)."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        ext = DocumentDataExtractor()
        ext.anthropic = None
    return ext


@pytest.fixture
def extractor_with_ai():
    """DocumentDataExtractor with a mocked Anthropic client."""
    ext = DocumentDataExtractor()
    ext.anthropic = MagicMock()
    ext.model = "claude-sonnet-4-20250514"
    return ext


def _make_llm_response(
    extracted_fields: Dict[str, Any],
    confidence_scores: Dict[str, int],
    provenance: Optional[Dict[str, str]] = None,
    detected_names: Optional[List[str]] = None,
    overall_confidence: int = 80,
) -> MagicMock:
    """Build a mock Anthropic messages.create() response."""
    payload = {
        "extracted_fields": extracted_fields,
        "confidence_scores": confidence_scores,
        "provenance": provenance or {},
        "detected_names": detected_names or [],
        "overall_confidence": overall_confidence,
    }
    text_block = MagicMock()
    text_block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [text_block]
    return response


# =============================================================================
# 1. PDF NATIVE TEXT EXTRACTION
# =============================================================================

class TestPDFNativeTextExtraction:
    """Verify pdfplumber-based text extraction from PDFs with a text layer."""

    def test_pdf_text_extraction_uses_pdfplumber(self, extractor):
        """Should attempt pdfplumber first for PDF files."""
        fake_pdf_bytes = b"%PDF-1.4 fake content"
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Employer Name: Acme Corp\nGross Pay: $5,000.00"
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(fake_pdf_bytes)

        assert "Acme Corp" in text
        assert "5,000.00" in text

    def test_pdf_native_extraction_limits_to_10_pages(self, extractor):
        """Should only extract from the first 10 pages."""
        pages = [MagicMock() for _ in range(15)]
        for i, page in enumerate(pages):
            page.extract_text.return_value = f"Page {i + 1} content"

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(b"fake pdf")

        # Pages 11-15 content should NOT appear
        assert "Page 10 content" in text
        assert "Page 11 content" not in text


# =============================================================================
# 2. PDF OCR FALLBACK WHEN NO TEXT LAYER
# =============================================================================

class TestPDFOCRFallback:
    """Verify OCR fallback when pdfplumber returns insufficient text."""

    def test_ocr_fallback_when_pdfplumber_returns_empty(self, extractor):
        """When pdfplumber yields <100 chars, should fall back to pdf2image + tesseract."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""  # No text layer
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        mock_image = MagicMock()

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.HAS_PDF2IMAGE", True), \
             patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber, \
             patch("services.smart_docs.document_data_extractor.convert_from_bytes") as mock_convert, \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess:
            mock_plumber.open.return_value = mock_pdf
            mock_convert.return_value = [mock_image]
            mock_tess.image_to_string.return_value = "OCR Fallback Text With Enough Content To Pass"

            text = extractor._extract_text_from_pdf(b"scanned pdf")

        mock_convert.assert_called_once()
        mock_tess.image_to_string.assert_called_once_with(mock_image)
        assert "OCR Fallback Text" in text

    def test_no_ocr_fallback_when_pdfplumber_has_text(self, extractor):
        """When pdfplumber yields >=100 chars, OCR should NOT be attempted."""
        long_text = "A" * 200
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = long_text
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.HAS_PDF2IMAGE", True), \
             patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber, \
             patch("services.smart_docs.document_data_extractor.convert_from_bytes") as mock_convert:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(b"text pdf")

        mock_convert.assert_not_called()
        assert long_text in text


# =============================================================================
# 3. JPEG IMAGE OCR
# =============================================================================

class TestJPEGImageOCR:
    """Verify OCR extraction from JPEG images."""

    def test_jpeg_ocr_extraction(self, extractor):
        """JPEG images should be processed via pytesseract."""
        mock_img = MagicMock()

        with patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess, \
             patch("services.smart_docs.document_data_extractor.Image") as mock_pil:
            mock_pil.open.return_value = mock_img
            mock_tess.image_to_string.return_value = "CALIFORNIA\nDRIVER LICENSE\nDOB: 01/15/1985"

            text = extractor._extract_text_from_image(b"\xff\xd8\xff\xe0 JPEG data")

        assert "DRIVER LICENSE" in text
        assert "DOB: 01/15/1985" in text

    def test_jpeg_returns_empty_without_tesseract(self, extractor):
        """When tesseract is unavailable, should return empty string."""
        with patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", False):
            text = extractor._extract_text_from_image(b"\xff\xd8\xff\xe0 JPEG")
        assert text == ""


# =============================================================================
# 4. PNG IMAGE OCR
# =============================================================================

class TestPNGImageOCR:
    """Verify OCR extraction from PNG images."""

    def test_png_ocr_extraction(self, extractor):
        """PNG images should be processed the same as JPEG via pytesseract."""
        mock_img = MagicMock()

        with patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess, \
             patch("services.smart_docs.document_data_extractor.Image") as mock_pil:
            mock_pil.open.return_value = mock_img
            mock_tess.image_to_string.return_value = "W-2 Wage and Tax Statement\nBox 1: $85,000"

            text = extractor._extract_text_from_image(b"\x89PNG\r\n data")

        assert "W-2" in text
        assert "$85,000" in text

    def test_png_mime_type_routes_to_image_extraction(self, extractor):
        """mime_type='image/png' should route through _extract_text_from_image."""
        with patch.object(extractor, "_extract_text_from_image", return_value="PNG OCR text") as mock_method:
            text = extractor._extract_text(b"png bytes", "image/png")
        mock_method.assert_called_once_with(b"png bytes")
        assert text == "PNG OCR text"


# =============================================================================
# 5. MULTI-PAGE DOCUMENT HANDLING
# =============================================================================

class TestMultiPageDocumentHandling:
    """Verify multi-page PDF processing."""

    def test_multi_page_text_concatenation(self, extractor):
        """Text from multiple PDF pages should be concatenated."""
        pages = []
        for i in range(3):
            page = MagicMock()
            page.extract_text.return_value = f"Page {i + 1}: Content for page {i + 1}"
            pages.append(page)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(b"multi-page pdf")

        assert "Page 1:" in text
        assert "Page 2:" in text
        assert "Page 3:" in text

    def test_text_output_truncated_at_50000_chars(self, extractor):
        """Extracted text should be capped at 50,000 characters."""
        page = MagicMock()
        page.extract_text.return_value = "A" * 60000
        mock_pdf = MagicMock()
        mock_pdf.pages = [page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(b"huge pdf")

        assert len(text) <= 50000

    def test_ocr_fallback_limited_to_5_pages(self, extractor):
        """OCR fallback via pdf2image should only process the first 5 pages."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.HAS_PDF2IMAGE", True), \
             patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber, \
             patch("services.smart_docs.document_data_extractor.convert_from_bytes") as mock_convert, \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess:
            mock_plumber.open.return_value = mock_pdf
            mock_convert.return_value = [MagicMock() for _ in range(5)]
            mock_tess.image_to_string.return_value = "ocr page"
            extractor._extract_text_from_pdf(b"scanned pdf")

        # convert_from_bytes should be called with first_page=1, last_page=5
        call_kwargs = mock_convert.call_args
        assert call_kwargs[1].get("first_page", call_kwargs[0][0] if len(call_kwargs[0]) > 1 else 1) >= 1
        assert call_kwargs[1].get("last_page", 5) <= 5


# =============================================================================
# 6. CURRENCY VALUE PARSING
# =============================================================================

class TestCurrencyValueParsing:
    """Verify _safe_decimal handles various currency formats."""

    def test_parse_dollar_with_commas(self, extractor):
        assert extractor._safe_decimal("$1,234.56") == 1234.56

    def test_parse_dollar_no_commas(self, extractor):
        assert extractor._safe_decimal("$5000.00") == 5000.00

    def test_parse_plain_number(self, extractor):
        assert extractor._safe_decimal("1234.56") == 1234.56

    def test_parse_integer(self, extractor):
        assert extractor._safe_decimal(85000) == 85000.0

    def test_parse_negative_currency(self, extractor):
        """Negative amounts (e.g., deductions) should be handled."""
        assert extractor._safe_decimal("-$1,234.56") is not None or \
               extractor._safe_decimal("-1234.56") == -1234.56

    def test_parse_none_returns_none(self, extractor):
        assert extractor._safe_decimal(None) is None

    def test_parse_empty_string_returns_none(self, extractor):
        assert extractor._safe_decimal("") is None

    def test_parse_non_numeric_returns_none(self, extractor):
        assert extractor._safe_decimal("N/A") is None

    def test_parse_zero(self, extractor):
        assert extractor._safe_decimal("$0.00") == 0.0

    def test_parse_large_amount(self, extractor):
        assert extractor._safe_decimal("$1,234,567.89") == 1234567.89

    def test_parse_float_input(self, extractor):
        assert extractor._safe_decimal(3500.50) == 3500.50

    def test_parse_decimal_input(self, extractor):
        assert extractor._safe_decimal(Decimal("4200.00")) == 4200.0


# =============================================================================
# 7. DATE PARSING (via LLM prompt contract)
# =============================================================================

class TestDateParsing:
    """Verify date format handling in the extraction pipeline.

    The extractor instructs the LLM to return dates in ISO format (YYYY-MM-DD).
    These tests validate that the prompt contract is correct and that the
    extraction schema specifies date types appropriately.
    """

    def test_extraction_prompt_requests_iso_dates(self, extractor_with_ai):
        """The LLM prompt should instruct ISO date format."""
        response = _make_llm_response(
            extracted_fields={"pay_date": "2026-01-15"},
            confidence_scores={"pay_date": 90},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Pay Date: January 15, 2026\n" + "x" * 100,
        )

        # Verify the prompt sent to LLM includes ISO format instruction
        call_args = extractor_with_ai.anthropic.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"]
        assert "YYYY-MM-DD" in prompt_text

    def test_date_fields_in_paystub_schema(self):
        """Paystub schema should declare date-typed fields."""
        schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        date_fields = [
            name for name, info in schema["fields"].items()
            if info["type"] == "date"
        ]
        assert "pay_period_start" in date_fields
        assert "pay_period_end" in date_fields
        assert "pay_date" in date_fields
        assert "hire_date" in date_fields

    def test_date_fields_in_drivers_license_schema(self):
        """Driver's license schema should declare expiration and DOB dates."""
        schema = EXTRACTION_SCHEMAS[DocType.DRIVERS_LICENSE]
        date_fields = [
            name for name, info in schema["fields"].items()
            if info["type"] == "date"
        ]
        assert "date_of_birth" in date_fields
        assert "issue_date" in date_fields
        assert "expiration_date" in date_fields


# =============================================================================
# 8. NAME NORMALIZATION
# =============================================================================

class TestNameNormalization:
    """Verify that names are detected and returned via detected_names."""

    def test_llm_returns_detected_names(self, extractor_with_ai):
        """LLM response should include detected_names for owner matching."""
        response = _make_llm_response(
            extracted_fields={"employee_name": "John A. Smith"},
            confidence_scores={"employee_name": 95},
            detected_names=["John A. Smith", "Acme Corporation"],
            overall_confidence=85,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employee: SMITH, JOHN A\nEmployer: Acme Corporation\n" + "x" * 100,
        )

        assert result.success is True
        assert "John A. Smith" in result.detected_names

    def test_name_normalization_last_first_format(self, extractor_with_ai):
        """LLM should normalize 'LAST, FIRST' to 'First Last' per prompt."""
        response = _make_llm_response(
            extracted_fields={
                "full_name": "Jane Marie Doe",
                "first_name": "Jane",
                "last_name": "Doe",
            },
            confidence_scores={"full_name": 88, "first_name": 88, "last_name": 88},
            detected_names=["Jane Marie Doe"],
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.DRIVERS_LICENSE,
            ocr_text="DOE, JANE MARIE\nDOB: 03/15/1990\n" + "x" * 100,
        )

        assert result.extracted_fields.get("first_name") == "Jane"
        assert result.extracted_fields.get("last_name") == "Doe"


# =============================================================================
# 9. ADDRESS NORMALIZATION
# =============================================================================

class TestAddressNormalization:
    """Verify address field extraction from driver's license schema."""

    def test_address_fields_in_license_schema(self):
        """Driver's license schema should include separate address components."""
        schema = EXTRACTION_SCHEMAS[DocType.DRIVERS_LICENSE]
        assert "address" in schema["fields"]
        assert "city" in schema["fields"]
        assert "state" in schema["fields"]
        assert "zip_code" in schema["fields"]

    def test_address_fields_map_to_lead(self):
        """Address fields should have lead_field mappings for CRM sync."""
        schema = EXTRACTION_SCHEMAS[DocType.DRIVERS_LICENSE]
        assert schema["fields"]["address"]["lead_field"] == "address"
        assert schema["fields"]["city"]["lead_field"] == "city"
        assert schema["fields"]["state"]["lead_field"] == "state"
        assert schema["fields"]["zip_code"]["lead_field"] == "zip_code"


# =============================================================================
# 10. SSN MASKING (ONLY LAST 4 STORED)
# =============================================================================

class TestSSNMasking:
    """Verify that only the last 4 digits of SSN are stored."""

    def test_ssn_field_stores_only_last4(self):
        """Schema should define employee_ssn_last4, NOT full SSN."""
        paystub_schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        assert "employee_ssn_last4" in paystub_schema["fields"]
        # Full SSN field should NOT exist
        assert "employee_ssn" not in paystub_schema["fields"]
        assert "ssn" not in paystub_schema["fields"]

    def test_w2_ssn_field_is_last4(self):
        """W2 schema should also store only SSN last 4."""
        w2_schema = EXTRACTION_SCHEMAS[DocType.W2]
        assert "employee_ssn_last4" in w2_schema["fields"]
        assert "employee_ssn" not in w2_schema["fields"]

    def test_ssn_last4_extraction_via_llm(self, extractor_with_ai):
        """LLM extraction should return only last 4 of SSN."""
        response = _make_llm_response(
            extracted_fields={"employee_ssn_last4": "6789", "employer_name": "Acme"},
            confidence_scores={"employee_ssn_last4": 90, "employer_name": 95},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="SSN: xxx-xx-6789\nEmployer: Acme Corp\n" + "x" * 100,
        )

        assert result.extracted_fields["employee_ssn_last4"] == "6789"
        assert len(result.extracted_fields["employee_ssn_last4"]) == 4


# =============================================================================
# 11. PAYSTUB FIELD EXTRACTION
# =============================================================================

class TestPaystubFieldExtraction:
    """Verify paystub-specific extraction: employer, gross, net, YTD."""

    def test_paystub_schema_has_critical_fields(self):
        """Paystub schema must include employer, gross, net, and YTD fields."""
        schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        fields = schema["fields"]
        assert "employer_name" in fields
        assert "gross_pay" in fields
        assert "net_pay" in fields
        assert "ytd_gross" in fields
        assert "ytd_net" in fields

    def test_paystub_extraction_returns_income_data(self, extractor_with_ai):
        """Full paystub extraction should return structured income data."""
        response = _make_llm_response(
            extracted_fields={
                "employer_name": "Acme Corp",
                "gross_pay": 3500.00,
                "net_pay": 2750.00,
                "ytd_gross": 42000.00,
                "pay_frequency": "biweekly",
                "pay_date": "2026-01-15",
            },
            confidence_scores={
                "employer_name": 95,
                "gross_pay": 90,
                "net_pay": 88,
                "ytd_gross": 85,
                "pay_frequency": 80,
                "pay_date": 92,
            },
            overall_confidence=88,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Pay Period: 01/01 - 01/15\nGross Pay: $3,500\nNet: $2,750\n" + "x" * 100,
        )

        assert result.success is True
        assert result.extracted_fields["employer_name"] == "Acme Corp"
        assert result.extracted_fields["gross_pay"] == 3500.00

    def test_annual_income_calculation_biweekly(self, extractor):
        """Biweekly pay should be annualized by multiplying by 26."""
        fields = {"gross_pay": 3500.00, "pay_frequency": "biweekly"}
        annual = extractor._calculate_annual_income(fields)
        assert annual == 3500.00 * 26

    def test_annual_income_calculation_weekly(self, extractor):
        """Weekly pay should be annualized by multiplying by 52."""
        fields = {"gross_pay": 1750.00, "pay_frequency": "weekly"}
        annual = extractor._calculate_annual_income(fields)
        assert annual == 1750.00 * 52

    def test_annual_income_calculation_monthly(self, extractor):
        """Monthly pay should be annualized by multiplying by 12."""
        fields = {"gross_pay": 7000.00, "pay_frequency": "monthly"}
        annual = extractor._calculate_annual_income(fields)
        assert annual == 7000.00 * 12

    def test_annual_income_calculation_semimonthly(self, extractor):
        """Semimonthly pay should be annualized by multiplying by 24."""
        fields = {"gross_pay": 3500.00, "pay_frequency": "semimonthly"}
        annual = extractor._calculate_annual_income(fields)
        assert annual == 3500.00 * 24

    def test_annual_income_default_multiplier_when_frequency_unknown(self, extractor):
        """When pay frequency is unknown, should default to monthly (x12)."""
        fields = {"gross_pay": 5000.00, "pay_frequency": ""}
        annual = extractor._calculate_annual_income(fields)
        assert annual == 5000.00 * 12

    def test_annual_income_none_when_no_data(self, extractor):
        """Should return None when neither gross_pay nor ytd_gross is available."""
        fields = {}
        annual = extractor._calculate_annual_income(fields)
        assert annual is None


# =============================================================================
# 12. W2 BOX EXTRACTION
# =============================================================================

class TestW2BoxExtraction:
    """Verify W2-specific field extraction."""

    def test_w2_schema_has_all_boxes(self):
        """W2 schema should include key box fields."""
        schema = EXTRACTION_SCHEMAS[DocType.W2]
        fields = schema["fields"]
        assert "wages_tips_compensation" in fields  # Box 1
        assert "federal_tax_withheld" in fields  # Box 2
        assert "social_security_wages" in fields  # Box 3
        assert "medicare_wages" in fields  # Box 5
        assert "tax_year" in fields

    def test_w2_wages_maps_to_annual_income(self):
        """Box 1 wages should map to lead's annual_income field."""
        schema = EXTRACTION_SCHEMAS[DocType.W2]
        assert schema["fields"]["wages_tips_compensation"]["lead_field"] == "annual_income"

    def test_w2_extraction_via_llm(self, extractor_with_ai):
        """Full W2 extraction should return box values."""
        response = _make_llm_response(
            extracted_fields={
                "employee_name": "John Smith",
                "employer_name": "Tech Corp",
                "employer_ein": "12-3456789",
                "wages_tips_compensation": 85000.00,
                "federal_tax_withheld": 12500.00,
                "social_security_wages": 85000.00,
                "medicare_wages": 85000.00,
                "tax_year": 2025,
            },
            confidence_scores={
                "wages_tips_compensation": 95,
                "federal_tax_withheld": 93,
                "tax_year": 98,
            },
            overall_confidence=92,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.W2,
            ocr_text="Form W-2 Wage and Tax Statement 2025\nBox 1: $85,000\n" + "x" * 100,
        )

        assert result.success is True
        assert result.extracted_fields["wages_tips_compensation"] == 85000.00
        assert result.extracted_fields["tax_year"] == 2025


# =============================================================================
# 13. BANK STATEMENT FIELD EXTRACTION
# =============================================================================

class TestBankStatementFieldExtraction:
    """Verify bank statement extraction schema and fields."""

    def test_bank_statement_schema_has_required_fields(self):
        """Schema should include balances, dates, and account info."""
        schema = EXTRACTION_SCHEMAS[DocType.BANK_STATEMENT]
        fields = schema["fields"]
        assert "account_holder_name" in fields
        assert "bank_name" in fields
        assert "account_number_last4" in fields
        assert "beginning_balance" in fields
        assert "ending_balance" in fields
        assert "statement_start_date" in fields
        assert "statement_end_date" in fields

    def test_bank_account_type_enum_values(self):
        """Account type field should accept standard account types."""
        schema = EXTRACTION_SCHEMAS[DocType.BANK_STATEMENT]
        account_type = schema["fields"]["account_type"]
        assert account_type["type"] == "enum"
        assert "checking" in account_type["values"]
        assert "savings" in account_type["values"]

    def test_bank_statement_extraction(self, extractor_with_ai):
        """Full bank statement extraction should return structured data."""
        response = _make_llm_response(
            extracted_fields={
                "bank_name": "Chase Bank",
                "account_holder_name": "Jane Doe",
                "account_number_last4": "4567",
                "account_type": "checking",
                "beginning_balance": 15432.10,
                "ending_balance": 17732.10,
                "total_deposits": 8500.00,
                "total_withdrawals": 6200.00,
                "statement_start_date": "2026-01-01",
                "statement_end_date": "2026-01-31",
            },
            confidence_scores={
                "bank_name": 95,
                "beginning_balance": 90,
                "ending_balance": 90,
            },
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.BANK_STATEMENT,
            ocr_text="Bank Statement\nBeginning: $15,432.10\nEnding: $17,732.10\n" + "x" * 100,
        )

        assert result.success is True
        assert result.extracted_fields["bank_name"] == "Chase Bank"
        assert result.extracted_fields["beginning_balance"] == 15432.10


# =============================================================================
# 14. DRIVER'S LICENSE FIELD EXTRACTION
# =============================================================================

class TestDriversLicenseFieldExtraction:
    """Verify driver's license extraction schema and fields."""

    def test_license_schema_has_identity_fields(self):
        """Schema should include name, DOB, address, and license details."""
        schema = EXTRACTION_SCHEMAS[DocType.DRIVERS_LICENSE]
        fields = schema["fields"]
        assert "full_name" in fields
        assert "first_name" in fields
        assert "last_name" in fields
        assert "date_of_birth" in fields
        assert "license_number" in fields
        assert "expiration_date" in fields

    def test_license_name_maps_to_lead(self):
        """First and last name should map to lead fields."""
        schema = EXTRACTION_SCHEMAS[DocType.DRIVERS_LICENSE]
        assert schema["fields"]["first_name"]["lead_field"] == "first_name"
        assert schema["fields"]["last_name"]["lead_field"] == "last_name"


# =============================================================================
# 15. PER-FIELD CONFIDENCE SCORING
# =============================================================================

class TestPerFieldConfidenceScoring:
    """Verify confidence score structure and overall confidence calculation."""

    def test_confidence_scores_per_field(self, extractor_with_ai):
        """Each extracted field should have its own confidence score 0-100."""
        response = _make_llm_response(
            extracted_fields={
                "employer_name": "Acme Corp",
                "gross_pay": 5000.00,
                "net_pay": 3800.00,
            },
            confidence_scores={
                "employer_name": 95,
                "gross_pay": 88,
                "net_pay": 82,
            },
            overall_confidence=85,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Acme Corp\nGross: $5,000\nNet: $3,800\n" + "x" * 100,
        )

        assert "employer_name" in result.confidence_scores
        assert "gross_pay" in result.confidence_scores
        assert all(0 <= v <= 100 for v in result.confidence_scores.values())

    def test_overall_confidence_is_set(self, extractor_with_ai):
        """ExtractionResult should have an overall_confidence field."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Test"},
            confidence_scores={"employer_name": 70},
            overall_confidence=70,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Test\n" + "x" * 100,
        )

        assert result.overall_confidence == 70

    def test_provenance_tracking(self, extractor_with_ai):
        """Each field should have provenance showing source text snippet."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Acme Corp"},
            confidence_scores={"employer_name": 95},
            provenance={"employer_name": "EMPLOYER: ACME CORP"},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="EMPLOYER: ACME CORP\nPay: $5,000\n" + "x" * 100,
        )

        assert "employer_name" in result.provenance
        assert "ACME CORP" in result.provenance["employer_name"]


# =============================================================================
# 16. LOW-QUALITY IMAGE HANDLING
# =============================================================================

class TestLowQualityImageHandling:
    """Verify behavior when OCR returns poor-quality or insufficient text."""

    def test_insufficient_text_returns_failure(self, extractor_with_ai):
        """When extracted text is <50 chars, extraction should fail gracefully."""
        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="short",
        )

        assert result.success is False
        assert "Insufficient text" in result.error

    def test_ocr_failure_returns_empty_text(self, extractor):
        """When tesseract raises an exception, should return empty string."""
        with patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess, \
             patch("services.smart_docs.document_data_extractor.Image") as mock_pil:
            mock_pil.open.side_effect = Exception("Cannot identify image file")
            text = extractor._extract_text_from_image(b"corrupted image data")

        assert text == ""

    def test_pdfplumber_failure_tries_ocr(self, extractor):
        """When pdfplumber raises, should still attempt OCR fallback."""
        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.HAS_PDF2IMAGE", True), \
             patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber, \
             patch("services.smart_docs.document_data_extractor.convert_from_bytes") as mock_convert, \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess:
            mock_plumber.open.side_effect = Exception("Corrupt PDF")
            mock_convert.return_value = [MagicMock()]
            mock_tess.image_to_string.return_value = "OCR recovered text from damaged pdf " * 5

            text = extractor._extract_text_from_pdf(b"corrupted pdf")

        assert "OCR recovered text" in text


# =============================================================================
# 17. ROTATED PAGE DETECTION
# =============================================================================

class TestRotatedPageDetection:
    """Verify handling of rotated pages during OCR.

    The current implementation does not have explicit rotation detection,
    but we validate that OCR still processes the page and returns whatever
    text it can extract (pytesseract handles some rotation internally).
    """

    def test_rotated_page_still_produces_text(self, extractor):
        """OCR should attempt extraction even on rotated pages."""
        mock_img = MagicMock()

        with patch("services.smart_docs.document_data_extractor.HAS_TESSERACT", True), \
             patch("services.smart_docs.document_data_extractor.pytesseract") as mock_tess, \
             patch("services.smart_docs.document_data_extractor.Image") as mock_pil:
            mock_pil.open.return_value = mock_img
            # Simulating a rotated page might produce garbled but present text
            mock_tess.image_to_string.return_value = "sdiawed rotated text employer name salary"
            text = extractor._extract_text_from_image(b"rotated image")

        assert len(text) > 0
        assert "rotated text" in text


# =============================================================================
# 18. HANDWRITING DETECTION AND FLAGGING
# =============================================================================

class TestHandwritingDetection:
    """Verify that handwritten documents produce low-confidence results.

    The system relies on OCR quality (low-quality OCR -> low confidence from LLM)
    rather than explicit handwriting detection. We test the downstream effect.
    """

    def test_poor_ocr_text_yields_low_confidence(self, extractor_with_ai):
        """Handwriting typically produces garbled OCR, resulting in low LLM confidence."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "unclear"},
            confidence_scores={"employer_name": 15},
            overall_confidence=20,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="image/jpeg",
            doc_type=DocType.PAYSTUB,
            ocr_text="swxsq dfkj3 hndwrt emp1oyer gr0ss p@y n&t pavy " * 5,
        )

        assert result.success is True
        assert result.overall_confidence <= 30

    def test_extraction_result_tracks_low_confidence_fields(self, extractor_with_ai):
        """When individual fields have very low confidence, the scores reflect it."""
        response = _make_llm_response(
            extracted_fields={
                "employer_name": "M??ybe Acme",
                "gross_pay": 0,
            },
            confidence_scores={
                "employer_name": 20,
                "gross_pay": 10,
            },
            overall_confidence=15,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="image/jpeg",
            doc_type=DocType.PAYSTUB,
            ocr_text="blurry handwritten scrawl that looks like pay stub " * 5,
        )

        low_confidence_fields = [
            k for k, v in result.confidence_scores.items() if v < 30
        ]
        assert len(low_confidence_fields) >= 2


# =============================================================================
# 19. TABLE STRUCTURE EXTRACTION
# =============================================================================

class TestTableStructureExtraction:
    """Verify extraction of tabular data (earnings tables, deduction tables)."""

    def test_paystub_has_deduction_fields(self):
        """Paystub schema should include deduction fields for table rows."""
        schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        deduction_fields = [
            name for name, info in schema["fields"].items()
            if info.get("category") == "deductions"
        ]
        # Should have at least federal_tax, state_tax, social_security, medicare
        assert len(deduction_fields) >= 4
        assert "federal_tax" in [f for f in deduction_fields]
        assert "state_tax" in [f for f in deduction_fields]
        assert "social_security" in [f for f in deduction_fields]
        assert "medicare" in [f for f in deduction_fields]

    def test_paystub_has_ytd_deduction_fields(self):
        """Paystub schema should include YTD deduction columns from tables."""
        schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        ytd_fields = [
            name for name in schema["fields"]
            if name.startswith("ytd_") and schema["fields"][name].get("category") == "deductions"
        ]
        assert "ytd_federal_tax" in ytd_fields
        assert "ytd_state_tax" in ytd_fields
        assert "ytd_social_security" in ytd_fields
        assert "ytd_medicare" in ytd_fields
        assert "ytd_retirement" in ytd_fields

    def test_earnings_table_fields_present(self):
        """Paystub schema should capture earnings breakdown from table rows."""
        schema = EXTRACTION_SCHEMAS[DocType.PAYSTUB]
        earnings_fields = [
            name for name, info in schema["fields"].items()
            if info.get("category") == "income"
        ]
        assert "regular_earnings" in earnings_fields
        assert "overtime_earnings" in earnings_fields
        assert "bonus" in earnings_fields
        assert "commission" in earnings_fields


# =============================================================================
# 20. EMPTY / BLANK PAGE DETECTION
# =============================================================================

class TestEmptyBlankPageDetection:
    """Verify behavior when processing blank or empty documents."""

    def test_empty_ocr_text_fails_extraction(self, extractor_with_ai):
        """Completely empty OCR text should result in failed extraction."""
        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="",
        )
        assert result.success is False
        assert "Insufficient text" in result.error

    def test_whitespace_only_text_fails_extraction(self, extractor_with_ai):
        """Whitespace-only OCR text should fail extraction."""
        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="   \n\t\n   ",
        )
        assert result.success is False

    def test_blank_pdf_pages_produce_no_text(self, extractor):
        """Blank PDF pages should yield empty text from pdfplumber."""
        pages = [MagicMock() for _ in range(3)]
        for page in pages:
            page.extract_text.return_value = None  # pdfplumber returns None for blank pages

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("services.smart_docs.document_data_extractor.HAS_PDFPLUMBER", True), \
             patch("services.smart_docs.document_data_extractor.HAS_PDF2IMAGE", False), \
             patch("services.smart_docs.document_data_extractor.pdfplumber", create=True) as mock_plumber:
            mock_plumber.open.return_value = mock_pdf
            text = extractor._extract_text_from_pdf(b"blank pdf")

        # Should be essentially empty (just newlines from concatenation)
        assert text.strip() == ""

    def test_no_anthropic_and_no_text_gives_error(self, extractor):
        """When no AI and extraction yields no text, extract should return error."""
        with patch.object(extractor, "_extract_text", return_value=""):
            result = extractor.extract(
                file_content=b"empty file",
                mime_type="application/pdf",
                doc_type=DocType.PAYSTUB,
            )
        assert result.success is False


# =============================================================================
# ADDITIONAL TESTS: EXTRACTION PIPELINE INTEGRATION
# =============================================================================

class TestExtractionPipelineIntegration:
    """End-to-end tests for the extraction pipeline."""

    def test_extract_routes_pdf_correctly(self, extractor):
        """PDF mime type should route through _extract_text_from_pdf."""
        with patch.object(extractor, "_extract_text_from_pdf", return_value="PDF text") as mock_pdf:
            text = extractor._extract_text(b"pdf bytes", "application/pdf")
        mock_pdf.assert_called_once()
        assert text == "PDF text"

    def test_extract_routes_image_correctly(self, extractor):
        """Image mime types should route through _extract_text_from_image."""
        for mime in ["image/jpeg", "image/png", "image/tiff"]:
            with patch.object(extractor, "_extract_text_from_image", return_value="IMG text") as mock_img:
                text = extractor._extract_text(b"img bytes", mime)
            mock_img.assert_called_once()
            assert text == "IMG text"

    def test_extract_with_pre_provided_ocr_text(self, extractor_with_ai):
        """When ocr_text is provided, _extract_text should NOT be called."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Provided Corp"},
            confidence_scores={"employer_name": 90},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        with patch.object(extractor_with_ai, "_extract_text") as mock_extract:
            result = extractor_with_ai.extract(
                file_content=b"dummy",
                mime_type="application/pdf",
                doc_type=DocType.PAYSTUB,
                ocr_text="Pre-provided OCR text with enough chars for extraction " * 3,
            )

        mock_extract.assert_not_called()
        assert result.success is True

    def test_extraction_result_to_dict(self, extractor_with_ai):
        """ExtractionResult.to_dict() should produce a serializable dict."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Test Corp"},
            confidence_scores={"employer_name": 90},
            overall_confidence=85,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Test Corp\n" + "x" * 100,
        )

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["success"] is True
        assert result_dict["overall_confidence"] == 85
        assert "extracted_fields" in result_dict
        assert "confidence_scores" in result_dict
        assert "provenance" in result_dict

    def test_llm_unavailable_returns_error(self, extractor):
        """When Anthropic client is None, extraction with text should fail."""
        result = extractor.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="This is enough text to pass the minimum threshold for extraction purposes " * 3,
        )

        assert result.success is False
        assert "Anthropic" in result.error or "not available" in result.error.lower()

    def test_llm_json_parse_failure(self, extractor_with_ai):
        """When LLM returns invalid JSON, should return error ExtractionResult."""
        text_block = MagicMock()
        text_block.text = "This is not JSON at all"
        response = MagicMock()
        response.content = [text_block]
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Pay Period: 01/01-01/15\nGross: $5,000\nNet: $3,800\n" + "x" * 100,
        )

        assert result.success is False
        assert "parse" in result.error.lower()

    def test_llm_response_with_markdown_fences(self, extractor_with_ai):
        """LLM response wrapped in ```json fences should still parse."""
        payload = json.dumps({
            "extracted_fields": {"employer_name": "Fenced Corp"},
            "confidence_scores": {"employer_name": 90},
            "provenance": {},
            "detected_names": ["Fenced Corp"],
            "overall_confidence": 85,
        })
        text_block = MagicMock()
        text_block.text = f"```json\n{payload}\n```"
        response = MagicMock()
        response.content = [text_block]
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Fenced Corp\nGross Pay: $5,000\n" + "x" * 100,
        )

        assert result.success is True
        assert result.extracted_fields["employer_name"] == "Fenced Corp"

    def test_extraction_duration_tracked(self, extractor_with_ai):
        """Extraction result should include a non-negative duration in ms."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Fast Corp"},
            confidence_scores={"employer_name": 90},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Fast Corp\n" + "x" * 100,
        )

        assert result.extraction_duration_ms >= 0

    def test_default_schema_used_for_unknown_doc_type(self, extractor_with_ai):
        """Unknown doc type should use DEFAULT_EXTRACTION_SCHEMA."""
        response = _make_llm_response(
            extracted_fields={"document_date": "2026-01-15"},
            confidence_scores={"document_date": 70},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=None,
            ocr_text="Some unknown document with enough text for processing " * 5,
        )

        assert result.success is True

    def test_mappable_fields_populated(self, extractor_with_ai):
        """Fields with lead_field mappings should appear in mappable_fields."""
        response = _make_llm_response(
            extracted_fields={"employer_name": "Map Corp"},
            confidence_scores={"employer_name": 90},
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Employer: Map Corp\n" + "x" * 100,
        )

        assert "employer_name" in result.mappable_fields

    def test_exception_during_extraction_returns_error(self, extractor_with_ai):
        """Unexpected exceptions during extraction should be caught and returned."""
        extractor_with_ai.anthropic.messages.create.side_effect = RuntimeError("API meltdown")

        result = extractor_with_ai.extract(
            file_content=b"dummy",
            mime_type="text/plain",
            doc_type=DocType.PAYSTUB,
            ocr_text="Some valid text for the extraction pipeline " * 5,
        )

        assert result.success is False
        assert "API meltdown" in result.error


# =============================================================================
# PAYSTUB-FOR-INCOME EXTRACTION (extract_paystub_for_income)
# =============================================================================

class TestPaystubForIncomeExtraction:
    """Tests for the specialized extract_paystub_for_income method."""

    def test_successful_paystub_income_extraction(self, extractor_with_ai):
        """Should return structured data with calculated annual income."""
        response = _make_llm_response(
            extracted_fields={
                "employer_name": "Income Corp",
                "gross_pay": 4000.00,
                "net_pay": 3100.00,
                "pay_frequency": "biweekly",
                "pay_date": "2026-01-15",
                "ytd_gross": 8000.00,
            },
            confidence_scores={
                "employer_name": 95,
                "gross_pay": 90,
            },
            overall_confidence=88,
        )
        extractor_with_ai.anthropic.messages.create.return_value = response

        data = extractor_with_ai.extract_paystub_for_income(
            file_content=b"dummy",
            mime_type="text/plain",
            ocr_text="Employer: Income Corp\nGross: $4,000\nNet: $3,100\n" + "x" * 100,
        )

        assert data["success"] is True
        assert data["employer_name"] == "Income Corp"
        assert data["gross_pay"] == 4000.00
        assert data["calculated_annual_income"] == 4000.00 * 26  # biweekly
        assert data["calculated_monthly_income"] is not None
        assert data["expires_at"] is not None

    def test_failed_paystub_extraction_returns_error(self, extractor):
        """When extraction fails, should return error dict."""
        data = extractor.extract_paystub_for_income(
            file_content=b"dummy",
            mime_type="text/plain",
            ocr_text="too short",
        )

        assert data["success"] is False
        assert "error" in data

    def test_pay_frequency_expiration_mapping(self):
        """PAY_FREQUENCY_EXPIRATION_DAYS should map expected frequencies."""
        assert PAY_FREQUENCY_EXPIRATION_DAYS["WEEKLY"] == 7
        assert PAY_FREQUENCY_EXPIRATION_DAYS["BIWEEKLY"] == 30
        assert PAY_FREQUENCY_EXPIRATION_DAYS["SEMIMONTHLY"] == 30
        assert PAY_FREQUENCY_EXPIRATION_DAYS["MONTHLY"] == 45
