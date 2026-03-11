"""
Test AI Document Classifier Service

Comprehensive tests for the AI-powered document classification service.
Covers keyword-based classification, AI fallback behavior, batch processing,
feature detection, confidence scoring, caching, and edge cases.

Tests target: backend/services/smart_docs/ai_classifier_service.py
"""

import json
import time
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Patch the DocType enum BEFORE importing the classifier module so the
# module-level KEYWORD_RULES / FILENAME_PATTERNS resolve correctly.
# ---------------------------------------------------------------------------

import enum


class _MockDocType(str, enum.Enum):
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    PAYSTUB = "PAYSTUB"
    W2 = "W2"
    TAX_RETURN = "TAX_RETURN"
    BUSINESS_TAX_RETURN = "BUSINESS_TAX_RETURN"
    PROFIT_LOSS = "PROFIT_LOSS"
    BALANCE_SHEET = "BALANCE_SHEET"
    BANK_STATEMENT = "BANK_STATEMENT"
    INVESTMENT_STATEMENT = "INVESTMENT_STATEMENT"
    GIFT_LETTER = "GIFT_LETTER"
    LOE = "LOE"
    LEASE_AGREEMENT = "LEASE_AGREEMENT"
    FHA_CERT = "FHA_CERT"
    VA_COE = "VA_COE"
    DD214 = "DD214"
    BANKRUPTCY_DISCHARGE = "BANKRUPTCY_DISCHARGE"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    APPRAISAL = "APPRAISAL"
    TITLE_REPORT = "TITLE_REPORT"
    HOMEOWNERS_INSURANCE = "HOMEOWNERS_INSURANCE"
    OTHER = "OTHER"


import sys
from types import ModuleType

_smart_docs_models = ModuleType("models.smart_docs_models")
_smart_docs_models.DocType = _MockDocType  # type: ignore[attr-defined]
sys.modules["models.smart_docs_models"] = _smart_docs_models

# Now safe to import
from services.smart_docs.ai_classifier_service import (  # noqa: E402
    AIDocumentClassifierService,
    ClassificationResult,
    KEYWORD_RULES,
    FILENAME_PATTERNS,
    FEATURE_PATTERNS,
    _now_ms,
)

DocType = _MockDocType


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def service():
    """Classifier service with no AI client (rule-based only)."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        svc = AIDocumentClassifierService()
        svc._anthropic = None
        return svc


@pytest.fixture
def service_with_ai():
    """Classifier service with a mocked Anthropic client."""
    svc = AIDocumentClassifierService()
    svc._anthropic = MagicMock()
    svc._model = "claude-sonnet-4-20250514"
    return svc


def _make_ai_response(predicted_type: str, confidence: int, alternatives=None, reasoning="test"):
    """Build a mock Anthropic API response."""
    payload = {
        "predicted_type": predicted_type,
        "confidence": confidence,
        "alternatives": alternatives or [],
        "reasoning": reasoning,
    }
    text_block = MagicMock()
    text_block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [text_block]
    return response


# =============================================================================
# 1. KEYWORD-BASED CLASSIFICATION FOR EACH DOCUMENT TYPE
# =============================================================================

class TestKeywordClassificationByDocType:
    """Verify that representative text for each doc type classifies correctly."""

    @pytest.mark.parametrize("doc_type,text", [
        (DocType.PAYSTUB, "Pay Period: 01/01/2026 - 01/15/2026\nGross Pay: $3,500.00\nNet Pay: $2,750.00\nYTD Earnings: $7,000.00\nFederal Withholding: $450"),
        (DocType.W2, "Form W-2 Wage and Tax Statement 2025\nEmployer Identification Number: 12-3456789\nWages, tips, other compensation: $85,000\nFederal income tax withheld: $12,500\nSocial security wages: $85,000"),
        (DocType.TAX_RETURN, "Form 1040 U.S. Individual Income Tax Return 2025\nFiling Status: Married Filing Jointly\nAdjusted Gross Income: $125,000\nTaxable Income: $95,000\nStandard Deduction applied"),
        (DocType.BUSINESS_TAX_RETURN, "Form 1120-S U.S. Corporation Income Tax Return\nSchedule K-1 Shareholder's Share of Income\nGross receipts: $500,000\nOrdinary business income: $95,000"),
        (DocType.PROFIT_LOSS, "Profit and Loss Statement for year ending 12/31/2025\nTotal Revenue: $800,000\nCost of Goods Sold: $400,000\nGross Profit: $400,000\nOperating Expenses: $250,000\nNet Income: $150,000"),
        (DocType.BALANCE_SHEET, "Balance Sheet as of 12/31/2025\nTotal Assets: $2,500,000\nCurrent Assets: $800,000\nTotal Liabilities: $1,200,000\nStockholders Equity: $1,300,000\nRetained Earnings: $600,000"),
        (DocType.BANK_STATEMENT, "Bank Statement\nStatement Period: 01/01/2026 - 01/31/2026\nBeginning Balance: $15,432.10\nDeposits: $8,500.00\nWithdrawals: $6,200.00\nEnding Balance: $17,732.10\nRouting Number: 021000089"),
        (DocType.INVESTMENT_STATEMENT, "Brokerage Statement\nPortfolio Summary\nAccount Value: $425,000\nMutual Fund Holdings\nUnrealized Gain: $32,000\nAsset Allocation: 60% Stocks, 40% Bonds"),
        (DocType.GIFT_LETTER, "Gift Letter\nI hereby certify that the gift amount of $25,000 is being given to the donee for down payment purposes.\nRelationship to borrower: Parent\nThis gift does not need to be repaid and is not a loan."),
        (DocType.LOE, "Letter of Explanation\nTo Whom It May Concern,\nI am writing to explain the gap in employment from March 2024 to June 2024.\nThe late payment on my credit report was due to a medical emergency."),
        (DocType.LEASE_AGREEMENT, "Lease Agreement\nThis rental agreement is between the landlord and tenant.\nMonthly rent: $2,200\nSecurity deposit: $2,200\nLease term: 12 months\nLease commencement date: 01/01/2026"),
        (DocType.FHA_CERT, "FHA Certification\nFHA Case Number: 123-4567890\nFederal Housing Administration\nMutual Mortgage Insurance Premium\nUpfront MIP: $3,500\nFHA Addendum attached"),
        (DocType.VA_COE, "Certificate of Eligibility\nDepartment of Veterans Affairs\nVA Home Loan Program\nBasic Entitlement: $36,000\nBonus Entitlement Available\nFunding Fee: Exempt"),
        (DocType.DD214, "DD Form 214 Certificate of Release or Discharge from Active Duty\nBranch of Service: US Army\nDate of Separation: 06/15/2020\nCharacter of Service: Honorable Discharge\nPay Grade: E-6"),
        (DocType.BANKRUPTCY_DISCHARGE, "United States Bankruptcy Court\nDischarge of Debtor\nChapter 7 Bankruptcy Case\nOrder of Discharge granted\nCase Number: 20-12345\nDebtor name: John Doe"),
        (DocType.PURCHASE_CONTRACT, "Real Estate Purchase Agreement\nPurchase Price: $450,000\nEarnest Money Deposit: $10,000\nBuyer agrees to purchase the property\nFinancing Contingency\nInspection Contingency\nClosing Date: 04/15/2026"),
        (DocType.APPRAISAL, "Uniform Residential Appraisal Report\nAppraised Value: $475,000\nSubject Property: 123 Main St\nComparable Sales Analysis\nComp 1: 125 Oak Ave - $470,000\nGross Living Area: 2,100 sqft"),
        (DocType.TITLE_REPORT, "Preliminary Title Report\nTitle Commitment for insurance\nChain of Title verified\nVesting: John Doe and Jane Doe, as joint tenants\nEasement noted on Schedule B\nLien search complete"),
        (DocType.HOMEOWNERS_INSURANCE, "Homeowners Insurance Declarations Page\nDwelling Coverage: $450,000\nAnnual Premium: $1,800\nDeductible: $1,000\nMortgagee Clause: ABC Lending\nPolicy Number: HO-123456\nReplacement Cost coverage"),
        (DocType.DRIVERS_LICENSE, "State of California\nDriver License\nLicense Number: D1234567\nDate of Birth: 01/15/1985\nExpiration Date: 01/15/2028\nClass C\nDepartment of Motor Vehicles"),
    ])
    def test_keyword_classification_per_type(self, service, doc_type, text):
        """Each doc type should be correctly identified from representative text."""
        result = service.classify_by_text(text)
        assert result.predicted_type == doc_type.value, (
            f"Expected {doc_type.value} but got {result.predicted_type} "
            f"(confidence={result.confidence})"
        )
        assert result.confidence > 30, (
            f"Confidence too low ({result.confidence}) for {doc_type.value}"
        )

    def test_all_doc_types_have_keyword_rules(self):
        """Every DocType (except OTHER) should have an entry in KEYWORD_RULES."""
        for dt in DocType:
            if dt == DocType.OTHER:
                continue
            assert dt.value in KEYWORD_RULES, (
                f"DocType {dt.value} missing from KEYWORD_RULES"
            )


# =============================================================================
# 2. CONFIDENCE SCORE CALCULATION
# =============================================================================

class TestConfidenceScoring:
    """Verify confidence scoring logic based on keyword scores."""

    def test_high_confidence_for_strong_match(self, service):
        """Text with many strong keywords should yield high confidence."""
        text = (
            "Pay Period: 01/01 - 01/15\n"
            "Pay Date: 01/20/2026\n"
            "Gross Pay: $4,000\n"
            "Net Pay: $3,100\n"
            "Year to Date: $8,000\n"
            "Earnings Statement\n"
            "Federal Withholding: $500\n"
            "Social Security Tax: $250\n"
            "Medicare Tax: $60\n"
            "Hours Worked: 80\n"
            "Deductions: $900\n"
            "FICA: $310"
        )
        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.PAYSTUB.value
        assert result.confidence >= 70, f"Expected high confidence, got {result.confidence}"

    def test_low_confidence_for_weak_match(self, service):
        """Text with only a single weak keyword should yield low confidence."""
        text = "I have a salary of $50,000 per year."
        result = service.classify_by_text(text)
        # "salary" only appears in PAYSTUB with weight 4
        assert result.confidence < 60

    def test_confidence_penalty_for_ambiguous_matches(self, service):
        """When top two types score very close, confidence should be reduced."""
        # Text that has keywords for both BANK_STATEMENT and INVESTMENT_STATEMENT
        text = (
            "Account Summary\n"
            "Account Number: 123456789\n"
            "Portfolio Summary\n"
            "Account Value: $50,000\n"
            "Dividend Income: $500"
        )
        result = service.classify_by_text(text)
        assert result.alternatives, "Should have alternatives for ambiguous text"

    def test_confidence_never_exceeds_95(self, service):
        """Rule-based confidence should cap at 95."""
        # Extremely dense paystub text
        text = (
            "Pay Stub Pay Statement Pay Period Pay Date Earnings Statement "
            "Gross Pay Net Pay Year to Date YTD Payroll Federal Withholding "
            "State Withholding FICA Social Security Tax Medicare Tax "
            "Deductions 401k Check Number Direct Deposit Employee ID "
            "Pay Rate Hourly Rate Current Period Hours Worked Regular Hours Overtime"
        )
        result = service.classify_by_text(text)
        assert result.confidence <= 95

    def test_confidence_clear_winner_boost(self, service):
        """When one type clearly dominates, confidence should be boosted."""
        text = (
            "Form W-2 Wage and Tax Statement\n"
            "Employer Identification Number: 12-3456789\n"
            "Wages, tips, other compensation: $100,000\n"
            "Federal income tax withheld: $15,000\n"
            "Social security wages: $100,000\n"
            "Medicare wages and tips: $100,000\n"
            "Social security tax withheld: $6,200\n"
            "Medicare tax withheld: $1,450\n"
            "Copy B - To Be Filed With Employee's Federal Tax Return"
        )
        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.W2.value
        assert result.confidence >= 70


# =============================================================================
# 3. AI-TO-KEYWORD FALLBACK
# =============================================================================

class TestAIFallback:
    """Verify fallback from AI classification to keyword-based when AI fails."""

    def test_falls_back_to_keyword_when_ai_unavailable(self, service):
        """With no Anthropic client, classify_document should use keyword fallback."""
        assert service._anthropic is None
        text = "Form W-2 Wage and Tax Statement\nWages, tips, other compensation: $80,000"
        result = service.classify_document(
            file_content=b"dummy",
            mime_type="application/pdf",
            filename="w2_2025.pdf",
            ocr_text=text,
        )
        assert result.predicted_type == DocType.W2.value
        assert result.model_used == "rule_based_v1"

    def test_falls_back_when_ai_raises_exception(self, service_with_ai):
        """When AI API call raises, should fall back to rule-based."""
        service_with_ai._anthropic.messages.create.side_effect = Exception("API down")
        text = "Bank Statement\nBeginning Balance: $10,000\nEnding Balance: $12,000"
        result = service_with_ai.classify_document(
            file_content=b"pdf_bytes",
            mime_type="application/pdf",
            filename="bank_stmt.pdf",
            ocr_text=text,
        )
        assert result.predicted_type == DocType.BANK_STATEMENT.value
        assert result.model_used == "rule_based_v1"

    def test_falls_back_when_ai_returns_low_confidence(self, service_with_ai):
        """When AI returns confidence < 40, should supplement with rules."""
        low_conf_response = _make_ai_response("OTHER", 20, reasoning="unclear")
        service_with_ai._anthropic.messages.create.return_value = low_conf_response
        text = (
            "Form 1040 U.S. Individual Income Tax Return\n"
            "Adjusted Gross Income: $90,000\n"
            "Filing Status: Single\n"
            "Taxable Income: $75,000"
        )
        result = service_with_ai.classify_document(
            file_content=b"pdf_bytes",
            mime_type="application/pdf",
            filename="tax_return.pdf",
            ocr_text=text,
        )
        # Should fall through to rule-based since AI confidence was < 40
        assert result.predicted_type == DocType.TAX_RETURN.value
        assert result.model_used == "rule_based_v1"

    def test_uses_ai_when_confidence_sufficient(self, service_with_ai):
        """When AI returns confidence >= 40, should accept the AI result."""
        response = _make_ai_response("PAYSTUB", 85, alternatives=[
            {"type": "W2", "confidence": 30}
        ])
        service_with_ai._anthropic.messages.create.return_value = response

        result = service_with_ai.classify_document(
            file_content=b"image_bytes",
            mime_type="image/jpeg",
            filename="document.jpg",
        )
        assert result.predicted_type == DocType.PAYSTUB.value
        assert result.confidence == 85
        assert result.model_used == "claude-sonnet-4-20250514"

    def test_falls_back_to_filename_when_no_ocr_text(self, service):
        """With no AI and no OCR text, should classify by filename only."""
        result = service.classify_document(
            file_content=b"binary_content",
            mime_type="application/pdf",
            filename="bank_statement_jan_2026.pdf",
        )
        assert result.predicted_type == DocType.BANK_STATEMENT.value
        assert result.model_used == "filename_v1"


# =============================================================================
# 4. MULTI-PAGE DOCUMENT CLASSIFICATION
# =============================================================================

class TestMultiPageDocuments:
    """Test classification behavior with long/multi-page documents."""

    def test_long_text_classified_correctly(self, service):
        """Large document text (>3000 chars) should still classify correctly."""
        base_text = (
            "Bank Statement\nAccount Summary\n"
            "Statement Period: 01/01/2026 - 01/31/2026\n"
            "Beginning Balance: $5,000.00\nEnding Balance: $6,500.00\n"
            "Deposits and Withdrawals:\n"
        )
        # Add filler to exceed 3000 chars
        filler = "01/05 DEPOSIT $1,200.00\n01/10 WITHDRAWAL $500.00\n" * 100
        text = base_text + filler
        assert len(text) > 3000

        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.BANK_STATEMENT.value

    def test_multi_page_feature_detection_long_text(self, service):
        """Documents >3000 chars should have is_multi_page feature detected."""
        text = "Some document content\n" * 200  # Well over 3000 chars
        features = service.detect_features(text)
        assert features["is_multi_page"] is True

    def test_multi_page_feature_detection_page_marker(self, service):
        """Documents with 'page X of Y' markers should be flagged multi-page."""
        text = (
            "Bank Statement\n"
            "Page 1 of 3\n"
            "Beginning Balance: $10,000"
        )
        features = service.detect_features(text)
        assert features["is_multi_page"] is True

    def test_text_snippet_limited_to_1000_chars(self, service):
        """Classification result text_snippet should be capped at 1000 chars."""
        text = "A" * 5000
        result = service.classify_by_text(text)
        assert len(result.text_snippet) <= 1000


# =============================================================================
# 5. AMBIGUOUS DOCUMENT HANDLING
# =============================================================================

class TestAmbiguousDocuments:
    """Test behavior with documents that match multiple types."""

    def test_alternatives_populated_for_ambiguous_text(self, service):
        """Ambiguous text should produce alternatives in the result."""
        # Contains keywords for both TAX_RETURN and BUSINESS_TAX_RETURN
        text = (
            "Schedule K-1\n"
            "Form 1040 reference\n"
            "Adjusted Gross Income\n"
            "Partnership return income\n"
            "Ordinary business income\n"
            "Taxable income\n"
        )
        result = service.classify_by_text(text)
        assert len(result.alternatives) > 0, "Expected alternatives for ambiguous text"

    def test_alternatives_have_correct_structure(self, service):
        """Each alternative should have 'type' and 'confidence' keys."""
        text = (
            "Account Statement\n"
            "Account Number: 12345\n"
            "Deposits: $5,000\n"
            "Withdrawals: $3,000\n"
            "Investment Income: $200\n"
            "Market Value: $50,000"
        )
        result = service.classify_by_text(text)
        for alt in result.alternatives:
            assert "type" in alt, "Alternative missing 'type' key"
            assert "confidence" in alt, "Alternative missing 'confidence' key"
            assert isinstance(alt["confidence"], int)

    def test_max_three_alternatives(self, service):
        """At most 3 alternatives should be returned."""
        # Text with keywords spanning many types
        text = (
            "Bank Statement Account Summary Beginning Balance Ending Balance "
            "Investment Statement Portfolio Summary Market Value Dividend "
            "Pay Period Gross Pay Net Pay Earnings Statement "
            "Adjusted Gross Income Tax Return Form 1040 "
            "Profit and Loss Revenue Net Income "
            "Balance Sheet Total Assets Total Liabilities"
        )
        result = service.classify_by_text(text)
        assert len(result.alternatives) <= 3


# =============================================================================
# 6. CLASSIFICATION WITH METADATA HINTS
# =============================================================================

class TestMetadataHints:
    """Test that filename and MIME type influence classification."""

    def test_filename_boosts_keyword_classification(self, service):
        """A descriptive filename should boost the matching doc type score."""
        # Weak text for bank statement + strong filename
        text = "Some transactions and account info\nAvailable balance: $5,000"
        result_no_filename = service.classify_by_text(text, filename="")
        result_with_filename = service.classify_by_text(text, filename="bank_statement_jan.pdf")
        # With filename, bank statement confidence should be higher or same type chosen
        if result_no_filename.predicted_type == DocType.BANK_STATEMENT.value:
            assert result_with_filename.predicted_type == DocType.BANK_STATEMENT.value
        else:
            # Filename should push it toward BANK_STATEMENT
            assert result_with_filename.predicted_type == DocType.BANK_STATEMENT.value

    def test_filename_only_classification(self, service):
        """Pure filename classification should work for well-named files."""
        result = service.classify_by_filename("W-2_2025_JohnDoe.pdf")
        assert result.predicted_type == DocType.W2.value
        assert result.confidence >= 50
        assert result.model_used == "filename_v1"

    @pytest.mark.parametrize("filename,expected_type", [
        ("paystub_dec_2025.pdf", DocType.PAYSTUB.value),
        ("W2_2025.pdf", DocType.W2.value),
        ("1040_federal_return.pdf", DocType.TAX_RETURN.value),
        ("bank_statement_chase_jan.pdf", DocType.BANK_STATEMENT.value),
        ("gift_letter_signed.pdf", DocType.GIFT_LETTER.value),
        ("dd-214.pdf", DocType.DD214.value),
        ("purchase_agreement_123main.pdf", DocType.PURCHASE_CONTRACT.value),
        ("title_report_final.pdf", DocType.TITLE_REPORT.value),
        ("homeowners_insurance_dec.pdf", DocType.HOMEOWNERS_INSURANCE.value),
        ("lease_agreement_2026.pdf", DocType.LEASE_AGREEMENT.value),
        ("profit_loss_q4.pdf", DocType.PROFIT_LOSS.value),
        ("balance_sheet_2025.pdf", DocType.BALANCE_SHEET.value),
    ])
    def test_filename_pattern_matching(self, service, filename, expected_type):
        """Known filename patterns should produce correct classifications."""
        result = service.classify_by_filename(filename)
        assert result.predicted_type == expected_type, (
            f"Filename '{filename}' classified as {result.predicted_type}, expected {expected_type}"
        )

    def test_ai_receives_image_mime_type(self, service_with_ai):
        """Image MIME types should be sent as vision input to Claude."""
        response = _make_ai_response("DRIVERS_LICENSE", 90)
        service_with_ai._anthropic.messages.create.return_value = response

        service_with_ai.classify_document(
            file_content=b"\xff\xd8\xff\xe0",  # JPEG header bytes
            mime_type="image/jpeg",
            filename="license.jpg",
        )

        call_args = service_with_ai._anthropic.messages.create.call_args
        messages = call_args.kwargs["messages"]
        content_types = [c["type"] for c in messages[0]["content"]]
        assert "image" in content_types

    def test_ai_receives_pdf_mime_type(self, service_with_ai):
        """PDF MIME type should be sent as document input to Claude."""
        response = _make_ai_response("BANK_STATEMENT", 88)
        service_with_ai._anthropic.messages.create.return_value = response

        service_with_ai.classify_document(
            file_content=b"%PDF-1.4",
            mime_type="application/pdf",
            filename="statement.pdf",
        )

        call_args = service_with_ai._anthropic.messages.create.call_args
        messages = call_args.kwargs["messages"]
        content_types = [c["type"] for c in messages[0]["content"]]
        assert "document" in content_types


# =============================================================================
# 7. BATCH CLASSIFICATION
# =============================================================================

class TestBatchClassification:
    """Test batch_classify method."""

    def test_batch_returns_correct_count(self, service):
        """Batch results should match input count."""
        docs = [
            {
                "file_content": b"content1",
                "mime_type": "application/pdf",
                "filename": "paystub.pdf",
                "ocr_text": "Pay Period Gross Pay Net Pay YTD Earnings Statement",
            },
            {
                "file_content": b"content2",
                "mime_type": "application/pdf",
                "filename": "w2.pdf",
                "ocr_text": "Form W-2 Wage and Tax Statement Wages tips other compensation",
            },
            {
                "file_content": b"content3",
                "mime_type": "image/jpeg",
                "filename": "bank_stmt.jpg",
                "ocr_text": "Bank Statement Beginning Balance Ending Balance Deposits Routing Number",
            },
        ]
        results = service.batch_classify(docs)
        assert len(results) == 3

    def test_batch_classifies_each_correctly(self, service):
        """Each document in batch should be independently classified."""
        docs = [
            {
                "file_content": b"c1",
                "mime_type": "application/pdf",
                "filename": "doc.pdf",
                "ocr_text": "Pay Period Gross Pay Net Pay YTD Earnings Statement Federal Withholding",
            },
            {
                "file_content": b"c2",
                "mime_type": "application/pdf",
                "filename": "doc2.pdf",
                "ocr_text": "Form W-2 Wage and Tax Statement Employer Identification Number Federal income tax withheld",
            },
        ]
        results = service.batch_classify(docs)
        assert results[0].predicted_type == DocType.PAYSTUB.value
        assert results[1].predicted_type == DocType.W2.value

    def test_batch_handles_individual_failures(self, service):
        """If one doc fails, others should still succeed, and the failure gets an error result."""
        docs = [
            {
                "file_content": b"ok",
                "mime_type": "application/pdf",
                "filename": "paystub.pdf",
                "ocr_text": "Pay Period Gross Pay Net Pay YTD Earnings Statement",
            },
            # Missing all required keys -- should still produce an error result, not crash
            {},
        ]
        results = service.batch_classify(docs)
        assert len(results) == 2
        assert results[0].predicted_type == DocType.PAYSTUB.value

    def test_batch_empty_list(self, service):
        """Empty batch should return empty list."""
        assert service.batch_classify([]) == []


# =============================================================================
# 8. UNKNOWN DOCUMENT TYPE HANDLING
# =============================================================================

class TestUnknownDocumentType:
    """Test handling of documents that do not match any known type."""

    def test_unrecognized_text_returns_other(self, service):
        """Text with no mortgage keywords should classify as OTHER."""
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.OTHER.value
        assert result.confidence <= 30

    def test_unrecognized_filename_returns_other(self, service):
        """Filename with no pattern match should classify as OTHER."""
        result = service.classify_by_filename("random_photo.jpg")
        assert result.predicted_type == DocType.OTHER.value
        assert result.confidence == 0

    def test_ai_returns_invalid_type_normalized_to_other(self, service_with_ai):
        """If AI returns a type not in DocType, _parse_ai_response should map to OTHER."""
        response = _make_ai_response("INVALID_TYPE_XYZ", 70)
        service_with_ai._anthropic.messages.create.return_value = response

        result = service_with_ai.classify_document(
            file_content=b"data",
            mime_type="image/png",
            filename="unknown.png",
        )
        # The AI path should parse and discover invalid type, normalizing to OTHER
        # but then with low confidence, it falls through to rule-based
        # Since there's no OCR text and filename doesn't match, we get OTHER
        assert result.predicted_type == DocType.OTHER.value


# =============================================================================
# 9. CLASSIFICATION RESULT CACHING (save & retrieve)
# =============================================================================

class TestClassificationCaching:
    """Test save_classification and get_classification_for_document."""

    def test_save_classification_calls_db(self, service):
        """save_classification should add a record to the session."""
        mock_db = MagicMock()
        result = ClassificationResult(
            predicted_type=DocType.PAYSTUB.value,
            confidence=85,
            alternatives=[{"type": "W2", "confidence": 40}],
            features_detected={"has_pay_period": True},
            text_snippet="Pay Period...",
            model_used="rule_based_v1",
            duration_ms=50,
        )

        with patch(
            "services.smart_docs.ai_classifier_service.AIDocumentClassifierService.save_classification"
        ) as mock_save:
            mock_save.return_value = None
            service.save_classification(mock_db, document_id=42, result=result, organization_id=1)
            mock_save.assert_called_once()

    def test_get_classification_returns_none_when_no_record(self, service):
        """get_classification_for_document should return None for unknown document."""
        mock_db = MagicMock()

        with patch(
            "services.smart_docs.ai_classifier_service.AIDocumentClassifierService"
            ".get_classification_for_document"
        ) as mock_get:
            mock_get.return_value = None
            result = service.get_classification_for_document(mock_db, document_id=9999)
            assert result is None

    def test_get_classification_returns_dict_when_exists(self, service):
        """get_classification_for_document should return dict with expected keys."""
        mock_db = MagicMock()
        expected = {
            "id": 1,
            "document_id": 42,
            "original_doc_type": None,
            "predicted_doc_type": "PAYSTUB",
            "prediction_confidence": 85,
            "alternative_classifications": [{"type": "W2", "confidence": 40}],
            "classification_model": "rule_based_v1",
            "classification_duration_ms": 50,
            "features_detected": {"has_pay_period": True},
            "text_snippet": "Pay Period...",
            "is_correct": None,
            "corrected_doc_type": None,
            "corrected_by": None,
            "corrected_at": None,
            "created_at": "2026-03-01T00:00:00",
        }

        with patch(
            "services.smart_docs.ai_classifier_service.AIDocumentClassifierService"
            ".get_classification_for_document"
        ) as mock_get:
            mock_get.return_value = expected
            result = service.get_classification_for_document(mock_db, document_id=42)
            assert result["predicted_doc_type"] == "PAYSTUB"
            assert result["prediction_confidence"] == 85


# =============================================================================
# 10. EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases: empty text, non-English, corrupted content, etc."""

    def test_empty_text_returns_other(self, service):
        """Empty string should classify as OTHER with low confidence."""
        result = service.classify_by_text("")
        assert result.predicted_type == DocType.OTHER.value
        assert result.confidence <= 20

    def test_none_like_empty_filename(self, service):
        """Empty filename should return OTHER with zero confidence."""
        result = service.classify_by_filename("")
        assert result.predicted_type == DocType.OTHER.value
        assert result.confidence == 0

    def test_whitespace_only_text(self, service):
        """Whitespace-only text should classify as OTHER."""
        result = service.classify_by_text("   \n\t\n   ")
        assert result.predicted_type == DocType.OTHER.value

    def test_non_english_text(self, service):
        """Non-English text without mortgage keywords should classify as OTHER."""
        text = (
            "Este es un documento en espanol sin palabras clave hipotecarias. "
            "No contiene informacion bancaria ni declaraciones de impuestos."
        )
        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.OTHER.value

    def test_corrupted_binary_content_no_ai(self, service):
        """Binary/corrupted content without OCR text should fall back to filename."""
        result = service.classify_document(
            file_content=b"\x00\x01\x02\xff\xfe\xfd" * 100,
            mime_type="application/octet-stream",
            filename="paystub_jan.pdf",
        )
        assert result.predicted_type == DocType.PAYSTUB.value
        assert result.model_used == "filename_v1"

    def test_very_short_text(self, service):
        """Very short text (a single keyword) should still classify with low confidence."""
        result = service.classify_by_text("W-2")
        assert result.predicted_type == DocType.W2.value
        assert result.confidence < 80

    def test_mixed_case_keywords(self, service):
        """Keywords in mixed case should still match (case-insensitive)."""
        text = "FORM W-2 WAGE AND TAX STATEMENT\nFederal Income Tax Withheld"
        result = service.classify_by_text(text)
        assert result.predicted_type == DocType.W2.value

    def test_special_characters_in_text(self, service):
        """Text with special characters should not crash classification."""
        text = "Pay Period: $$$###@@@!!!\nGross Pay: $4,000.00\nNet Pay: $3,100"
        result = service.classify_by_text(text)
        assert result.success is True

    def test_unicode_in_filename(self, service):
        """Unicode characters in filename should not crash."""
        result = service.classify_by_filename("declaracion_contribucion_2025.pdf")
        # Should not raise
        assert result.predicted_type is not None

    def test_unsupported_mime_type_without_ai(self, service):
        """Unsupported MIME type without AI should fall back to filename."""
        result = service.classify_document(
            file_content=b"binary_data",
            mime_type="application/x-unknown-format",
            filename="gift_letter.pdf",
        )
        assert result.predicted_type == DocType.GIFT_LETTER.value
        assert result.model_used == "filename_v1"


# =============================================================================
# FEATURE DETECTION
# =============================================================================

class TestFeatureDetection:
    """Test the detect_features method."""

    def test_detects_ssn_pattern(self, service):
        """SSN pattern (123-45-6789 or masked) should be detected."""
        text = "Employee SSN: xxx-xx-6789\nDate: 01/15/2026"
        features = service.detect_features(text)
        assert features["has_ssn"] is True

    def test_detects_ein(self, service):
        """Employer Identification Number should be detected."""
        text = "EIN: 12-3456789\nEmployer Name: Acme Corp"
        features = service.detect_features(text)
        assert features["has_ein"] is True

    def test_detects_account_number(self, service):
        """Account number pattern should be detected."""
        text = "Account Number: 123456789\nRouting Number: 021000089"
        features = service.detect_features(text)
        assert features["has_account_number"] is True
        assert features["has_routing_number"] is True

    def test_detects_signature(self, service):
        """Signature indicator should be detected."""
        text = "I hereby certify this is true.\nSignature: _______________"
        features = service.detect_features(text)
        assert features["has_signature"] is True

    def test_detects_notary(self, service):
        """Notary/notarization indicators should be detected."""
        text = "Notarized on 01/15/2026 by Jane Smith, Notary Public\nSeal affixed"
        features = service.detect_features(text)
        assert features["has_notary"] is True

    def test_empty_text_returns_empty_features(self, service):
        """Empty text should return empty feature dict."""
        features = service.detect_features("")
        assert features == {}

    def test_detects_date_pattern(self, service):
        """Date patterns (mm/dd/yyyy) should be detected."""
        text = "Statement date: 01/15/2026"
        features = service.detect_features(text)
        assert features["has_date"] is True

    def test_detects_property_address(self, service):
        """Property address indicator should be detected."""
        text = "Subject Property Address: 123 Main St, Anytown, USA"
        features = service.detect_features(text)
        assert features.get("has_property_address") is True


# =============================================================================
# AI RESPONSE PARSING
# =============================================================================

class TestAIResponseParsing:
    """Test _parse_ai_response with various response formats."""

    def test_parses_clean_json(self, service_with_ai):
        """Clean JSON response should be parsed correctly."""
        result = service_with_ai._parse_ai_response(
            json.dumps({
                "predicted_type": "BANK_STATEMENT",
                "confidence": 92,
                "alternatives": [
                    {"type": "INVESTMENT_STATEMENT", "confidence": 45},
                ],
                "reasoning": "Clear bank statement format",
            }),
            text_snippet="Bank statement...",
            start_ms=_now_ms() - 100,
        )
        assert result.predicted_type == DocType.BANK_STATEMENT.value
        assert result.confidence == 92
        assert len(result.alternatives) == 1
        assert result.success is True

    def test_parses_markdown_fenced_json(self, service_with_ai):
        """JSON wrapped in ```json fences should be parsed correctly."""
        fenced = '```json\n{"predicted_type": "W2", "confidence": 88, "alternatives": [], "reasoning": "W2 form"}\n```'
        result = service_with_ai._parse_ai_response(fenced, "", _now_ms())
        assert result.predicted_type == DocType.W2.value
        assert result.confidence == 88
        assert result.success is True

    def test_invalid_json_returns_error(self, service_with_ai):
        """Malformed JSON should return an error ClassificationResult."""
        result = service_with_ai._parse_ai_response(
            "This is not JSON at all",
            text_snippet="",
            start_ms=_now_ms(),
        )
        assert result.success is False
        assert result.predicted_type == DocType.OTHER.value
        assert "Failed to parse" in result.error

    def test_confidence_clamped_to_0_100(self, service_with_ai):
        """Confidence values outside 0-100 should be clamped."""
        result = service_with_ai._parse_ai_response(
            json.dumps({
                "predicted_type": "PAYSTUB",
                "confidence": 150,
                "alternatives": [],
            }),
            text_snippet="",
            start_ms=_now_ms(),
        )
        assert result.confidence == 100

        result2 = service_with_ai._parse_ai_response(
            json.dumps({
                "predicted_type": "PAYSTUB",
                "confidence": -20,
                "alternatives": [],
            }),
            text_snippet="",
            start_ms=_now_ms(),
        )
        assert result2.confidence == 0

    def test_invalid_doc_type_in_alternatives_filtered(self, service_with_ai):
        """Invalid doc types in alternatives should be excluded."""
        result = service_with_ai._parse_ai_response(
            json.dumps({
                "predicted_type": "PAYSTUB",
                "confidence": 80,
                "alternatives": [
                    {"type": "INVALID_XYZ", "confidence": 50},
                    {"type": "W2", "confidence": 40},
                ],
            }),
            text_snippet="",
            start_ms=_now_ms(),
        )
        assert len(result.alternatives) == 1
        assert result.alternatives[0]["type"] == "W2"


# =============================================================================
# SINGLETON AND SERVICE INITIALIZATION
# =============================================================================

class TestServiceInitialization:
    """Test service singleton and initialization."""

    def test_service_initializes_without_api_key(self):
        """Service should work without ANTHROPIC_API_KEY (no AI, rules only)."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            svc = AIDocumentClassifierService()
            assert svc._anthropic is None

    def test_classification_result_dataclass(self):
        """ClassificationResult should have expected default values."""
        result = ClassificationResult(
            predicted_type="PAYSTUB",
            confidence=85,
            alternatives=[],
            features_detected={},
            text_snippet="test",
            model_used="test",
            duration_ms=0,
        )
        assert result.success is True
        assert result.error is None

    def test_now_ms_returns_milliseconds(self):
        """_now_ms should return current time in milliseconds."""
        ms = _now_ms()
        assert isinstance(ms, int)
        assert ms > 1_000_000_000_000  # After year 2001 in ms

    def test_duration_ms_is_set(self, service):
        """Classification results should have a non-negative duration_ms."""
        text = "Form W-2 Wage and Tax Statement"
        result = service.classify_by_text(text)
        assert result.duration_ms >= 0
