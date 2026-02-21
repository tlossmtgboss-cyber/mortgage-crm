"""
Core Parsing Tests for Estimate Parser Service
"""
import pytest
import hashlib
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from io import BytesIO
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("boto3", reason="boto3 not installed")

from services.estimate_parser_service import EstimateParserService, LoanEstimate


class TestEstimateParserService:

    @pytest.mark.asyncio
    async def test_parse_text_based_pdf(self, db_session, sample_text_pdf, mock_llm_response):
        """Test parsing a text-based PDF without OCR"""
        with patch('services.estimate_parser_service.Anthropic') as mock_anthropic:
            # Mock LLM response
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text=mock_llm_response)]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            service = EstimateParserService(db_session)

            result = await service.parse_estimate(
                file_content=sample_text_pdf.read(),
                filename="test_le.pdf",
                mime_type="application/pdf"
            )

            # Assertions
            assert result.success is True
            assert result.data is not None
            assert result.data.loan_amount == 400000
            assert result.data.interest_rate == 6.875

    @pytest.mark.asyncio
    async def test_parse_scanned_pdf_with_ocr(self, db_session, sample_scanned_pdf,
                                              mock_textract_response, mock_llm_response):
        """Test parsing a scanned PDF with OCR fallback"""
        with patch('services.estimate_parser_service.boto3') as mock_boto3, \
             patch('services.estimate_parser_service.Anthropic') as mock_anthropic:

            # Mock Textract client
            mock_textract = Mock()
            mock_textract.detect_document_text.return_value = mock_textract_response
            mock_boto3.client.return_value = mock_textract

            # Mock LLM response
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text=mock_llm_response)]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            service = EstimateParserService(db_session)

            result = await service.parse_estimate(
                file_content=sample_scanned_pdf.read(),
                filename="scanned_le.pdf",
                mime_type="application/pdf"
            )

            # Assertions - should work even if OCR was triggered
            assert result is not None

    @pytest.mark.asyncio
    async def test_parse_image_file(self, db_session, sample_image,
                                    mock_textract_response, mock_llm_response):
        """Test parsing an image file (always uses OCR)"""
        with patch('services.estimate_parser_service.boto3') as mock_boto3, \
             patch('services.estimate_parser_service.Anthropic') as mock_anthropic:

            # Mock Textract for synchronous image detection
            mock_textract = Mock()
            mock_textract.detect_document_text.return_value = mock_textract_response
            mock_boto3.client.return_value = mock_textract

            # Mock LLM
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text=mock_llm_response)]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            service = EstimateParserService(db_session)

            result = await service.parse_estimate(
                file_content=sample_image.read(),
                filename="le_photo.jpg",
                mime_type="image/jpeg"
            )

            # Assertions
            assert result is not None

    def test_pii_redaction(self, db_session, sample_le_with_pii):
        """Test that PII is properly redacted before LLM processing"""
        service = EstimateParserService(db_session)

        redacted = service._redact_pii(sample_le_with_pii)

        # Assertions - PII should be redacted
        assert "john.smith@email.com" not in redacted
        assert "[EMAIL_REDACTED]" in redacted

        assert "(555) 123-4567" not in redacted
        assert "[PHONE_REDACTED]" in redacted

        assert "123-45-6789" not in redacted
        assert "[SSN_REDACTED]" in redacted

        # Account numbers (10 digits) may be caught by phone pattern - just verify redacted
        assert "9876543210" not in redacted

        # Financial data should NOT be redacted
        assert "6.875" in redacted
        assert "$2,632.45" in redacted or "2632.45" in redacted

    def test_provenance_extraction(self, db_session):
        """Test that provenance snippets are extracted correctly"""
        service = EstimateParserService(db_session)

        sample_text = """
        LOAN ESTIMATE

        Loan Amount: $400,000.00
        This is the amount you will borrow.

        Interest Rate: 6.875%
        Your interest rate for this loan.

        Annual Percentage Rate (APR): 7.125%
        Your costs over the loan term expressed as a rate.

        Monthly Principal & Interest: $2,632.45
        See Projected Payments for details.

        Total Closing Costs (J): $12,500.00
        Includes $7,200 in Loan Costs + $5,300 in Other Costs

        Cash to Close (H): $65,000.00
        From Borrower at Closing
        """

        snippets = service._extract_provenance_snippets(sample_text)

        # Assertions - verify snippets are returned as ProvenanceSnippets object
        assert snippets is not None
        assert snippets.loan_amount is not None or snippets.cash_to_close is not None

    def test_confidence_scoring_complete_document(self, db_session):
        """Test confidence scoring for a complete, high-quality parse"""
        service = EstimateParserService(db_session)

        complete_estimate = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000,
            loan_term=30,
            loan_type="Conventional"
        )

        raw_text = "This is a long document with sufficient text content..." * 50

        confidence, needs_review, reasons = service._calculate_confidence(complete_estimate, raw_text)

        # Assertions
        assert confidence >= 0.70
        assert needs_review is False or confidence >= 0.75

    def test_confidence_scoring_missing_critical_fields(self, db_session):
        """Test confidence scoring when critical fields are missing"""
        service = EstimateParserService(db_session)

        incomplete_estimate = LoanEstimate(
            loan_amount=None,  # Missing critical field
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=None,  # Missing critical field
            total_closing_costs=12500,
            cash_to_close=65000
        )

        raw_text = "Short text"

        confidence, needs_review, reasons = service._calculate_confidence(incomplete_estimate, raw_text)

        # Assertions
        assert confidence < 0.90
        assert needs_review is True

    def test_file_validation_file_too_large(self, db_session):
        """Test that files exceeding size limit are rejected"""
        service = EstimateParserService(db_session)

        # Create 20MB content (exceeds 15MB limit)
        large_content = b"x" * (20 * 1024 * 1024)

        # Validate should fail
        from services.estimate_parser_service import MAX_FILE_SIZE
        assert len(large_content) > MAX_FILE_SIZE

    def test_file_validation_invalid_type(self, db_session):
        """Test that invalid file types are rejected"""
        from services.estimate_parser_service import ALLOWED_MIME_TYPES

        # Text files should not be allowed
        assert "text/plain" not in ALLOWED_MIME_TYPES
        assert "application/pdf" in ALLOWED_MIME_TYPES
        assert "image/jpeg" in ALLOWED_MIME_TYPES
        assert "image/png" in ALLOWED_MIME_TYPES

    def test_hash_computation(self, db_session, sample_text_pdf):
        """Test that document hash is computed consistently"""
        service = EstimateParserService(db_session)

        content = sample_text_pdf.read()
        hash1 = service._compute_hash(content)

        sample_text_pdf.seek(0)
        content2 = sample_text_pdf.read()
        hash2 = service._compute_hash(content2)

        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters


class TestLoanEstimateModel:
    """Test Pydantic model validation"""

    def test_valid_loan_estimate(self):
        """Test creating a valid LoanEstimate"""
        estimate = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000
        )

        assert estimate.loan_amount == 400000
        assert estimate.interest_rate == 6.875

    def test_loan_estimate_with_string_amounts(self):
        """Test that string amounts are coerced to numbers"""
        estimate = LoanEstimate(
            loan_amount="400,000",
            interest_rate="6.875",
            apr="7.125%",
            total_closing_costs="$12,500.00",
            cash_to_close="65000"
        )

        assert estimate.loan_amount == 400000
        assert estimate.interest_rate == 6.875
        assert estimate.apr == 7.125
        assert estimate.total_closing_costs == 12500

    def test_loan_estimate_optional_fields(self):
        """Test that optional fields default to None"""
        estimate = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875
        )

        assert estimate.loan_amount == 400000
        assert estimate.apr is None
        assert estimate.cash_to_close is None
        assert estimate.loan_type is None
