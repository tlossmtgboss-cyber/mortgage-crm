"""
Test AI Document Review Service - Comprehensive tests for smart document AI review.

Tests the AIDocumentReviewService covering:
1.  Auto-approve flow for clean documents
2.  Auto-reject for expired documents
3.  Auto-reject for wrong document type
4.  Auto-reject for poor quality (blurry, too small, screenshots)
5.  Name mismatch detection
6.  Freshness checks per document type
7.  Completeness checks (all required fields present)
8.  Fraud indicator detection
9.  Manual review queue assignment for borderline cases
10. Review decision recording with reviewer info
11. Batch review processing
12. Review override by senior reviewer
13. Review metrics tracking
14. Cross-document validation triggers
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Optional, List, Dict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Stub the external dependencies so the service module can be imported
# without a real database, S3, Anthropic SDK, pdfplumber, or PIL.
# ---------------------------------------------------------------------------

# Provide a lightweight database.Base stub if the real one cannot be loaded
try:
    from models.smart_docs_models import (
        DocType,
        DocumentDecision,
        RejectionCategory,
        RequestStatus,
        DocPolicyEventType,
        SmartDocument,
        DocumentRequest,
        DocPolicyEvent,
    )
except Exception:
    # If models can't be imported (missing DB driver, etc.), define minimal stubs
    import enum

    class DocType(str, enum.Enum):
        PAYSTUB = "PAYSTUB"
        W2 = "W2"
        TAX_RETURN = "TAX_RETURN"
        BANK_STATEMENT = "BANK_STATEMENT"
        INVESTMENT_STATEMENT = "INVESTMENT_STATEMENT"
        DRIVERS_LICENSE = "DRIVERS_LICENSE"
        PROFIT_LOSS = "PROFIT_LOSS"
        BALANCE_SHEET = "BALANCE_SHEET"
        PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
        GIFT_LETTER = "GIFT_LETTER"
        APPRAISAL = "APPRAISAL"
        TITLE_REPORT = "TITLE_REPORT"
        HOMEOWNERS_INSURANCE = "HOMEOWNERS_INSURANCE"
        BUSINESS_TAX_RETURN = "BUSINESS_TAX_RETURN"
        OTHER = "OTHER"

    class DocumentDecision(str, enum.Enum):
        ACCEPT = "ACCEPT"
        REJECT = "REJECT"
        NEEDS_REVIEW = "NEEDS_REVIEW"

    class RejectionCategory(str, enum.Enum):
        SCREENSHOT = "SCREENSHOT"
        EXPIRED = "EXPIRED"
        POOR_QUALITY = "POOR_QUALITY"
        INCOMPLETE = "INCOMPLETE"
        WRONG_TYPE = "WRONG_TYPE"
        OTHER = "OTHER"

    class RequestStatus(str, enum.Enum):
        OPEN = "OPEN"
        PENDING_REVIEW = "PENDING_REVIEW"
        ACCEPTED = "ACCEPTED"
        REJECTED = "REJECTED"

    class DocPolicyEventType(str, enum.Enum):
        DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
        SCREENSHOT_REJECTED = "SCREENSHOT_REJECTED"
        FRESHNESS_REJECTED = "FRESHNESS_REJECTED"

    SmartDocument = None
    DocumentRequest = None
    DocPolicyEvent = None


# Import the service's data classes and constants directly (they have no
# heavy dependencies beyond the enums above).
from services.smart_docs.ai_review_service import (
    ReviewDecision,
    BatchReviewResult,
    AIDocumentReviewService,
    DOC_TYPE_KEYWORDS,
    REQUIRED_FIELDS,
    FRESHNESS_REQUIREMENTS,
    MIN_FILE_SIZES,
    MAX_FILE_SIZE,
)


# =============================================================================
# HELPERS
# =============================================================================

def _make_smart_document(**overrides):
    """Create a mock SmartDocument with sensible defaults."""
    doc = MagicMock()
    doc.id = overrides.get("id", 1)
    doc.loan_id = overrides.get("loan_id", 100)
    doc.request_id = overrides.get("request_id", None)
    doc.borrower_id = overrides.get("borrower_id", 10)
    doc.file_name = overrides.get("file_name", "paystub_jan2026.pdf")
    doc.mime_type = overrides.get("mime_type", "application/pdf")
    doc.file_size = overrides.get("file_size", 50_000)
    doc.storage_key = overrides.get("storage_key", "docs/100/paystub_jan2026.pdf")
    doc.doc_type = overrides.get("doc_type", DocType.PAYSTUB)
    doc.detected_doc_type = overrides.get("detected_doc_type", None)
    doc.detected_is_screenshot = overrides.get("detected_is_screenshot", False)
    doc.screenshot_confidence = overrides.get("screenshot_confidence", 0.0)
    doc.ocr_text = overrides.get("ocr_text", None)
    doc.doc_date = overrides.get("doc_date", datetime(2026, 2, 28))
    doc.is_expired = overrides.get("is_expired", False)
    doc.status = overrides.get("status", "UPLOADED")
    doc.decision = overrides.get("decision", None)
    doc.extracted_names = overrides.get("extracted_names", None)
    doc.extracted_employer = overrides.get("extracted_employer", None)
    doc.extracted_amount = overrides.get("extracted_amount", None)
    doc.page_count = overrides.get("page_count", 1)
    doc.reviewed_at = overrides.get("reviewed_at", None)
    doc.reviewed_by = overrides.get("reviewed_by", None)
    doc.decision_reasons = overrides.get("decision_reasons", None)
    doc.rejection_reason = overrides.get("rejection_reason", None)
    doc.rejection_category = overrides.get("rejection_category", None)
    doc.fix_instructions = overrides.get("fix_instructions", None)
    return doc


def _make_pdf_bytes(text_content: str = "dummy", size: int = 20_000) -> bytes:
    """Create fake PDF bytes that pass the %PDF- header check."""
    header = b"%PDF-1.4\n"
    body = text_content.encode("utf-8")
    padding = b"\x00" * max(0, size - len(header) - len(body))
    return header + body + padding


def _paystub_ocr_text():
    """Return OCR text that matches paystub keywords and required fields."""
    return (
        "ACME Corp\n"
        "Pay Stub\n"
        "Earnings Statement\n"
        "Employee: John Smith\n"
        "Pay Period: 02/01/2026 - 02/15/2026\n"
        "Gross Pay: $4,500.00\n"
        "Net Pay: $3,200.00\n"
        "Year to Date: $9,000.00\n"
        "Federal Tax: $650.00\n"
        "FICA: $344.25\n"
        "Medicare: $65.25\n"
        "Deductions: $540.50\n"
        "Employer Name: ACME Corp\n"
    )


def _w2_ocr_text():
    """Return OCR text matching W2 keywords."""
    return (
        "Form W-2 Wage and Tax Statement 2025\n"
        "Employer Identification Number (EIN): 12-3456789\n"
        "Employer Name: ACME Corp\n"
        "Employee: John Smith\n"
        "Wages Tips Other Compensation: $108,000.00\n"
        "Federal Income Tax Withheld: $15,600.00\n"
        "Social Security Wages: $108,000.00\n"
        "Medicare Wages: $108,000.00\n"
    )


def _bank_statement_ocr_text():
    """Return OCR text matching bank statement keywords."""
    return (
        "Bank of America\n"
        "Account Statement\n"
        "Statement Period: 01/01/2026 - 01/31/2026\n"
        "Account Number: ****1234\n"
        "Beginning Balance: $15,234.56\n"
        "Ending Balance: $18,992.33\n"
        "Total Deposits: $8,500.00\n"
        "Total Withdrawals: $4,742.23\n"
        "Checking Account\n"
    )


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.execute.return_value.fetchone.return_value = None
    db.execute.return_value.fetchall.return_value = []
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create an AIDocumentReviewService with mocked dependencies."""
    with patch.dict("os.environ", {
        "SMART_DOCS_AUTO_APPROVE_THRESHOLD": "80",
        "SMART_DOCS_AUTO_REJECT_THRESHOLD": "30",
    }):
        svc = AIDocumentReviewService(mock_db)
        # Replace sub-services with mocks
        svc._screenshot_detector = MagicMock()
        svc._freshness_validator = MagicMock()
        svc._owner_matcher = MagicMock()
        return svc


# =============================================================================
# 1. AUTO-APPROVE FLOW FOR CLEAN DOCUMENTS
# =============================================================================

@pytest.mark.unit
class TestAutoApproveFlow:
    """Documents that pass all checks should be auto-approved."""

    def test_clean_paystub_auto_approved(self, service, mock_db):
        """A paystub with good quality, matching type, fresh date, and matching
        name should receive ACCEPT decision with auto_approved=True."""
        doc = _make_smart_document(
            doc_type=DocType.PAYSTUB,
            doc_date=datetime(2026, 3, 1),
            ocr_text=_paystub_ocr_text(),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        # Screenshot detector: not a screenshot
        ss_result = MagicMock()
        ss_result.is_screenshot = False
        ss_result.confidence = 0.05
        service._screenshot_detector.detect.return_value = ss_result

        # Owner matcher: name matches borrower
        owner_result = MagicMock()
        owner_result.owner = "BORROWER"
        owner_result.confidence = 95
        owner_result.matched_name = "John Smith"
        service._owner_matcher.match_owner.return_value = owner_result

        # Loan info for name check
        mock_db.execute.return_value.fetchone.return_value = ("John Smith", None)

        file_content = _make_pdf_bytes(_paystub_ocr_text())

        decision = service.review_document(doc.id, file_content=file_content)

        assert decision.decision == DocumentDecision.ACCEPT.value
        assert decision.auto_approved is True
        assert decision.freshness_valid is True
        assert decision.type_match is True
        assert decision.name_match is True
        assert decision.confidence >= 80

    def test_auto_approve_sets_status_approved(self, service, mock_db):
        """Auto-approved documents should have status set to APPROVED on the record."""
        doc = _make_smart_document(
            doc_type=DocType.PAYSTUB,
            doc_date=datetime(2026, 3, 1),
            ocr_text=_paystub_ocr_text(),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        ss_result = MagicMock(is_screenshot=False, confidence=0.02)
        service._screenshot_detector.detect.return_value = ss_result
        owner_result = MagicMock(owner="BORROWER", confidence=95, matched_name="John Smith")
        service._owner_matcher.match_owner.return_value = owner_result
        mock_db.execute.return_value.fetchone.return_value = ("John Smith", None)

        file_content = _make_pdf_bytes(_paystub_ocr_text())
        service.review_document(doc.id, file_content=file_content)

        # The document status should have been set to APPROVED
        assert doc.status == "APPROVED" or doc.decision == DocumentDecision.ACCEPT


# =============================================================================
# 2. AUTO-REJECT FOR EXPIRED DOCUMENTS
# =============================================================================

@pytest.mark.unit
class TestAutoRejectExpired:
    """Documents that fail freshness checks should be auto-rejected."""

    def test_expired_paystub_rejected(self, service):
        """A paystub older than 30 days should be rejected with EXPIRED category."""
        # Paystub freshness limit: 30 days
        doc_date = date(2025, 12, 1)  # ~100 days old
        is_fresh, days_old = service._check_freshness(DocType.PAYSTUB.value, doc_date)

        assert is_fresh is False
        assert days_old is not None
        assert days_old > 30

    def test_expired_document_gets_reject_decision(self, service):
        """_make_decision with freshness=False should return REJECT."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=False,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
            screenshot_confidence=0.0,
            days_old=45,
        )

        assert decision.decision == DocumentDecision.REJECT.value
        assert decision.freshness_valid is False
        assert decision.rejection_category == RejectionCategory.EXPIRED.value
        assert "expired" in decision.reasons[0].lower()

    def test_expired_bank_statement_rejected(self, service):
        """A bank statement older than 60 days should fail freshness."""
        doc_date = date(2025, 11, 1)
        is_fresh, days_old = service._check_freshness(
            DocType.BANK_STATEMENT.value, doc_date
        )
        assert is_fresh is False
        assert days_old > 60

    def test_expired_fix_instructions_provided(self, service):
        """Rejected expired documents should include fix instructions."""
        decision = service._make_decision(
            quality=90, type_match=True, name_match=True,
            freshness=False, completeness=100,
            fraud_indicators=[], is_screenshot=False,
            days_old=90,
        )
        assert decision.fix_instructions is not None
        assert "recent" in decision.fix_instructions.lower()


# =============================================================================
# 3. AUTO-REJECT FOR WRONG DOCUMENT TYPE
# =============================================================================

@pytest.mark.unit
class TestAutoRejectWrongType:
    """Documents whose content doesn't match declared type should be rejected."""

    def test_wrong_type_high_confidence_rejected(self, service):
        """Type mismatch with >90% confidence should auto-reject."""
        decision = service._make_decision(
            quality=90,
            type_match=False,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
            type_confidence=95,
            detected_type="BANK_STATEMENT",
            declared_type="PAYSTUB",
        )

        assert decision.decision == DocumentDecision.REJECT.value
        assert decision.rejection_category == RejectionCategory.WRONG_TYPE.value
        assert "BANK_STATEMENT" in decision.reasons[0]
        assert "PAYSTUB" in decision.reasons[0]

    def test_type_mismatch_moderate_confidence_needs_review(self, service):
        """Type mismatch with 60-90% confidence should go to human review."""
        decision = service._make_decision(
            quality=90,
            type_match=False,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
            type_confidence=75,
            detected_type="W2",
            declared_type="PAYSTUB",
        )

        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.needs_human_review is True

    def test_type_match_keyword_detection_paystub(self, service):
        """Paystub OCR text should be detected as PAYSTUB type."""
        match, confidence, detected = service._check_type_match(
            document_id=1,
            declared_type=DocType.PAYSTUB.value,
            ocr_text=_paystub_ocr_text(),
        )
        assert match is True
        assert detected == DocType.PAYSTUB.value

    def test_type_match_keyword_detection_w2(self, service):
        """W2 OCR text should be detected as W2 type."""
        match, confidence, detected = service._check_type_match(
            document_id=1,
            declared_type=DocType.W2.value,
            ocr_text=_w2_ocr_text(),
        )
        assert match is True
        assert detected == DocType.W2.value

    def test_type_mismatch_w2_declared_as_paystub(self, service):
        """W2 content declared as PAYSTUB should be detected as mismatch."""
        match, confidence, detected = service._check_type_match(
            document_id=1,
            declared_type=DocType.PAYSTUB.value,
            ocr_text=_w2_ocr_text(),
        )
        # W2 keywords should score higher than paystub keywords for W2 text
        assert detected == DocType.W2.value
        assert match is False


# =============================================================================
# 4. AUTO-REJECT FOR POOR QUALITY
# =============================================================================

@pytest.mark.unit
class TestAutoRejectPoorQuality:
    """Documents with quality below the reject threshold should be rejected."""

    def test_tiny_file_low_quality_score(self, service):
        """A file smaller than minimum size should get a low quality score."""
        tiny_pdf = b"%PDF-1.4\n" + b"\x00" * 100
        score, issues = service._check_quality(tiny_pdf, "application/pdf")
        assert score < 60
        assert any("too small" in issue.lower() for issue in issues)

    def test_quality_below_reject_threshold_gives_reject(self, service):
        """Quality score below auto-reject threshold triggers REJECT."""
        decision = service._make_decision(
            quality=20,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
            quality_issues=["File too small", "Cannot read content"],
        )
        assert decision.decision == DocumentDecision.REJECT.value
        assert decision.rejection_category == RejectionCategory.POOR_QUALITY.value

    def test_screenshot_high_confidence_rejected(self, service):
        """Screenshot detected with >85% confidence should auto-reject."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=True,
            screenshot_confidence=0.92,
        )
        assert decision.decision == DocumentDecision.REJECT.value
        assert decision.rejection_category == RejectionCategory.SCREENSHOT.value
        assert "screenshot" in decision.reasons[0].lower()

    def test_invalid_pdf_header_reduces_quality(self, service):
        """A file claiming to be PDF but without %PDF- header gets penalized."""
        fake_pdf = b"NOT-A-PDF" + b"\x00" * 10_000
        score, issues = service._check_quality(fake_pdf, "application/pdf")
        assert score < 70
        assert any("valid pdf" in issue.lower() for issue in issues)

    def test_oversized_file_warning(self, service):
        """A file exceeding MAX_FILE_SIZE should get a quality deduction."""
        large_content = _make_pdf_bytes("test", size=MAX_FILE_SIZE + 1000)
        score, issues = service._check_quality(large_content, "application/pdf")
        assert score < 100
        assert any("maximum size" in issue.lower() for issue in issues)


# =============================================================================
# 5. NAME MISMATCH DETECTION
# =============================================================================

@pytest.mark.unit
class TestNameMismatch:
    """Documents where name doesn't match borrower should be flagged."""

    def test_name_mismatch_triggers_needs_review(self, service):
        """When name_match=False, decision should be NEEDS_REVIEW."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=False,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
        )
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.needs_human_review is True
        assert any("name" in r.lower() for r in decision.reasons)

    def test_name_mismatch_high_priority(self, service):
        """Name mismatch should set review priority to HIGH."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=False,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
        )
        assert decision.review_priority == "HIGH"


# =============================================================================
# 6. FRESHNESS CHECK PER DOCUMENT TYPE
# =============================================================================

@pytest.mark.unit
class TestFreshnessByDocType:
    """Freshness requirements vary by document type."""

    def test_paystub_30_day_limit(self, service):
        """Paystubs must be within 30 days."""
        assert FRESHNESS_REQUIREMENTS[DocType.PAYSTUB.value] == 30

        # 25 days old: valid
        recent_date = date.today() - timedelta(days=25)
        is_fresh, days_old = service._check_freshness(DocType.PAYSTUB.value, recent_date)
        assert is_fresh is True

        # 35 days old: expired
        old_date = date.today() - timedelta(days=35)
        is_fresh, days_old = service._check_freshness(DocType.PAYSTUB.value, old_date)
        assert is_fresh is False

    def test_bank_statement_60_day_limit(self, service):
        """Bank statements must be within 60 days."""
        assert FRESHNESS_REQUIREMENTS[DocType.BANK_STATEMENT.value] == 60

        recent = date.today() - timedelta(days=50)
        is_fresh, _ = service._check_freshness(DocType.BANK_STATEMENT.value, recent)
        assert is_fresh is True

        old = date.today() - timedelta(days=65)
        is_fresh, _ = service._check_freshness(DocType.BANK_STATEMENT.value, old)
        assert is_fresh is False

    def test_investment_statement_90_day_limit(self, service):
        """Investment statements must be within 90 days."""
        assert FRESHNESS_REQUIREMENTS[DocType.INVESTMENT_STATEMENT.value] == 90

        recent = date.today() - timedelta(days=80)
        is_fresh, _ = service._check_freshness(DocType.INVESTMENT_STATEMENT.value, recent)
        assert is_fresh is True

        old = date.today() - timedelta(days=95)
        is_fresh, _ = service._check_freshness(DocType.INVESTMENT_STATEMENT.value, old)
        assert is_fresh is False

    def test_profit_loss_90_day_limit(self, service):
        """P&L statements must be within 90 days."""
        assert FRESHNESS_REQUIREMENTS[DocType.PROFIT_LOSS.value] == 90

    def test_doc_without_freshness_requirement_always_valid(self, service):
        """Document types without freshness rules (e.g., GIFT_LETTER) are always fresh."""
        old_date = date.today() - timedelta(days=500)
        is_fresh, days_old = service._check_freshness(DocType.GIFT_LETTER.value, old_date)
        assert is_fresh is True

    def test_null_doc_date_treated_as_valid(self, service):
        """When doc_date is None, freshness should pass."""
        is_fresh, days_old = service._check_freshness(DocType.PAYSTUB.value, None)
        assert is_fresh is True
        assert days_old is None


# =============================================================================
# 7. COMPLETENESS CHECK
# =============================================================================

@pytest.mark.unit
class TestCompletenessCheck:
    """Documents must contain required fields for their type."""

    def test_paystub_with_all_fields_scores_100(self, service):
        """A paystub containing all required keywords gets 100% completeness."""
        score, missing = service._check_completeness(
            _paystub_ocr_text(), DocType.PAYSTUB.value
        )
        assert score == 100
        assert missing == []

    def test_paystub_missing_ytd_lowers_score(self, service):
        """A paystub without 'year to date' should have lower completeness."""
        text = (
            "Pay Stub\n"
            "Employer Name: ACME Corp\n"
            "Pay Period: 02/01 - 02/15\n"
            "Gross Pay: $4,500.00\n"
        )
        score, missing = service._check_completeness(text, DocType.PAYSTUB.value)
        assert score < 100
        assert "year to date" in missing

    def test_doc_type_without_required_fields_scores_100(self, service):
        """A doc type not in REQUIRED_FIELDS should default to 100%."""
        score, missing = service._check_completeness(
            "some random text", DocType.GIFT_LETTER.value
        )
        assert score == 100
        assert missing == []

    def test_low_completeness_triggers_needs_review(self, service):
        """Completeness < 50% should trigger NEEDS_REVIEW."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=40,
            fraud_indicators=[],
            is_screenshot=False,
            missing_fields=["employer name", "pay period", "gross pay"],
        )
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.needs_human_review is True

    def test_very_low_completeness_critical_priority(self, service):
        """Completeness < 30% should set review priority to CRITICAL."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=20,
            fraud_indicators=[],
            is_screenshot=False,
            missing_fields=["employer name", "pay period", "gross pay", "year to date"],
        )
        assert decision.review_priority == "CRITICAL"


# =============================================================================
# 8. FRAUD INDICATOR DETECTION
# =============================================================================

@pytest.mark.unit
class TestFraudDetection:
    """Fraud patterns in documents should be flagged."""

    def test_round_dollar_amounts_flagged(self, service):
        """Multiple round $X,000 amounts should trigger a fraud indicator."""
        text = (
            "Gross Pay: $5,000.00\n"
            "Net Pay: $4,000.00\n"
            "YTD: $10,000.00\n"
            "Bonus: $2,000.00\n"
        )
        file_content = _make_pdf_bytes(text)
        fraud, indicators = service._detect_fraud_indicators(file_content, text)
        assert len(indicators) > 0
        assert any("round" in ind.lower() for ind in indicators)

    def test_mixed_currency_formatting_flagged(self, service):
        """Inconsistent currency formatting (comma vs no-comma) should be noted."""
        text = (
            "Gross Pay: $5,000.00\n"
            "Deduction: $1500.00\n"  # no comma
            "Net: $3,500.00\n"
            "Tax: $12345\n"  # no comma, no cents
        )
        file_content = _make_pdf_bytes(text)
        _, indicators = service._detect_fraud_indicators(file_content, text)
        assert any("formatting" in ind.lower() for ind in indicators)

    def test_very_short_text_flagged(self, service):
        """Documents with very little text should get a fraud indicator."""
        text = "Pay $5,000"
        file_content = _make_pdf_bytes(text)
        _, indicators = service._detect_fraud_indicators(file_content, text)
        assert any("little text" in ind.lower() for ind in indicators)

    def test_fraud_indicators_trigger_needs_review(self, service):
        """Presence of fraud indicators should send document to review with
        CRITICAL priority."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[
                "Multiple round dollar amounts",
                "Inconsistent formatting",
            ],
            is_screenshot=False,
        )
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.review_priority == "CRITICAL"
        assert decision.needs_human_review is True

    def test_no_fraud_when_amounts_not_round(self, service):
        """Normal non-round amounts should not trigger fraud indicators."""
        text = (
            "Gross Pay: $4,583.33\n"
            "Net Pay: $3,247.19\n"
            "YTD: $9,166.66\n"
        )
        file_content = _make_pdf_bytes(text)
        fraud, indicators = service._detect_fraud_indicators(file_content, text)
        round_indicator = [i for i in indicators if "round" in i.lower()]
        assert len(round_indicator) == 0


# =============================================================================
# 9. MANUAL REVIEW QUEUE ASSIGNMENT
# =============================================================================

@pytest.mark.unit
class TestManualReviewQueue:
    """Borderline cases should be sent for human review."""

    def test_moderate_screenshot_confidence_needs_review(self, service):
        """Screenshot with 40-85% confidence should go to NEEDS_REVIEW, not reject."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=True,
            screenshot_confidence=0.60,
        )
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.review_priority == "HIGH"

    def test_borderline_overall_score_needs_review(self, service):
        """Overall score just below auto-approve threshold should need review."""
        # quality=70 * 0.3 + completeness=70 * 0.3 + name_conf=70 * 0.2 + type_conf=70 * 0.2 = 70
        decision = service._make_decision(
            quality=70,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=70,
            fraud_indicators=[],
            is_screenshot=False,
            type_confidence=70,
            name_confidence=70,
        )
        # Overall score = 70, threshold = 80 -> NEEDS_REVIEW
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.needs_human_review is True

    def test_review_queue_returns_prioritized_list(self, service, mock_db):
        """review_queue should return documents ordered by priority."""
        rows = [
            # doc_id, file_name, doc_type, status, decision, decision_reasons,
            # rejection_reason, rejection_category, fix_instructions,
            # detected_is_screenshot, screenshot_confidence,
            # is_expired, loan_id, borrower_id, uploaded_at, reviewed_at,
            # loan_number, borrower_name
            (1, "doc1.pdf", "PAYSTUB", "UPLOADED", None, None,
             None, None, None,
             True, 0.92,
             False, 100, 10, datetime(2026, 3, 1), None,
             "LN-001", "John Smith"),
            (2, "doc2.pdf", "W2", "PROCESSING", None, None,
             None, None, None,
             False, 0.1,
             True, 100, 10, datetime(2026, 3, 2), None,
             "LN-001", "John Smith"),
            (3, "doc3.pdf", "BANK_STATEMENT", "UPLOADED", None, None,
             None, None, None,
             False, 0.0,
             False, 100, 10, datetime(2026, 3, 3), None,
             "LN-001", "John Smith"),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        queue = service.review_queue(organization_id=1, limit=50)

        assert len(queue) == 3
        # First item should be the screenshot (CRITICAL priority)
        assert queue[0]["priority"] == "CRITICAL"
        # Second item should be the expired one (HIGH priority)
        assert queue[1]["priority"] == "HIGH"
        # Third is normal
        assert queue[2]["priority"] == "NORMAL"


# =============================================================================
# 10. REVIEW DECISION RECORDING
# =============================================================================

@pytest.mark.unit
class TestReviewDecisionRecording:
    """Review decisions should be persisted with reviewer info."""

    def test_update_document_status_accept(self, service, mock_db):
        """Accepted document should have status=APPROVED and reviewed_by=SYSTEM."""
        doc = _make_smart_document()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        decision = ReviewDecision(
            decision=DocumentDecision.ACCEPT.value,
            confidence=92,
            reasons=["All checks passed"],
            quality_score=95,
            completeness_score=100,
            readability_score=95,
            auto_approved=True,
        )

        service._update_document_status(doc.id, decision)

        assert doc.decision == DocumentDecision.ACCEPT
        assert doc.status == "APPROVED"
        assert doc.reviewed_by == "SYSTEM"
        assert doc.reviewed_at is not None

    def test_update_document_status_reject(self, service, mock_db):
        """Rejected document should have status=REJECTED with rejection details."""
        doc = _make_smart_document()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        decision = ReviewDecision(
            decision=DocumentDecision.REJECT.value,
            confidence=90,
            reasons=["Document is expired (45 days old)"],
            rejection_category=RejectionCategory.EXPIRED.value,
            fix_instructions="Upload a recent version",
            quality_score=90,
        )

        service._update_document_status(doc.id, decision)

        assert doc.decision == DocumentDecision.REJECT
        assert doc.status == "REJECTED"
        assert doc.rejection_reason is not None
        assert doc.fix_instructions == "Upload a recent version"

    def test_log_review_event_created(self, service, mock_db):
        """_log_review_event should add a DocPolicyEvent to the session."""
        doc = _make_smart_document(loan_id=100, request_id=5)

        decision = ReviewDecision(
            decision=DocumentDecision.ACCEPT.value,
            confidence=95,
            reasons=["All checks passed"],
            auto_approved=True,
        )

        service._log_review_event(doc, decision)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called()

    def test_log_review_event_screenshot_rejection(self, service, mock_db):
        """Screenshot rejection should log SCREENSHOT_REJECTED event type."""
        doc = _make_smart_document()

        decision = ReviewDecision(
            decision=DocumentDecision.REJECT.value,
            confidence=92,
            reasons=["Screenshot detected"],
            rejection_category=RejectionCategory.SCREENSHOT.value,
        )

        service._log_review_event(doc, decision)

        # Verify the event was created with the correct type
        call_args = mock_db.add.call_args
        event = call_args[0][0]
        assert event.event_type == DocPolicyEventType.SCREENSHOT_REJECTED


# =============================================================================
# 11. BATCH REVIEW PROCESSING
# =============================================================================

@pytest.mark.unit
class TestBatchReview:
    """Batch review should process all unreviewed documents for a loan."""

    def test_batch_review_processes_all_documents(self, service, mock_db):
        """batch_review should process each unreviewed document."""
        docs = [
            _make_smart_document(id=1, status="UPLOADED"),
            _make_smart_document(id=2, status="PROCESSING"),
            _make_smart_document(id=3, status="UPLOADED"),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = docs

        # Mock review_document to return auto-approve for each
        with patch.object(service, "review_document") as mock_review:
            mock_review.return_value = ReviewDecision(
                decision=DocumentDecision.ACCEPT.value,
                confidence=95,
                reasons=["All checks passed"],
                auto_approved=True,
            )

            result = service.batch_review(loan_id=100)

            assert result.total == 3
            assert result.approved == 3
            assert result.rejected == 0
            assert result.needs_review == 0
            assert mock_review.call_count == 3

    def test_batch_review_mixed_results(self, service, mock_db):
        """Batch review should correctly tally mixed results."""
        docs = [
            _make_smart_document(id=1),
            _make_smart_document(id=2),
            _make_smart_document(id=3),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = docs

        decisions = [
            ReviewDecision(decision=DocumentDecision.ACCEPT.value, confidence=95,
                           reasons=["OK"], auto_approved=True),
            ReviewDecision(decision=DocumentDecision.REJECT.value, confidence=90,
                           reasons=["Expired"]),
            ReviewDecision(decision=DocumentDecision.NEEDS_REVIEW.value, confidence=60,
                           reasons=["Borderline"], needs_human_review=True),
        ]

        with patch.object(service, "review_document", side_effect=decisions):
            result = service.batch_review(loan_id=100)

            assert result.total == 3
            assert result.approved == 1
            assert result.rejected == 1
            assert result.needs_review == 1

    def test_batch_review_handles_errors_gracefully(self, service, mock_db):
        """If review_document throws for one doc, it should not stop the batch."""
        docs = [
            _make_smart_document(id=1),
            _make_smart_document(id=2),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = docs

        with patch.object(service, "review_document") as mock_review:
            mock_review.side_effect = [
                ReviewDecision(decision=DocumentDecision.ACCEPT.value, confidence=95,
                               reasons=["OK"], auto_approved=True),
                Exception("S3 timeout"),
            ]

            result = service.batch_review(loan_id=100)

            assert result.total == 2
            assert result.approved == 1
            assert result.needs_review == 1  # Error counted as needs_review

    def test_batch_review_commits_at_end(self, service, mock_db):
        """batch_review should commit the session after processing."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        service.batch_review(loan_id=100)

        mock_db.commit.assert_called_once()


# =============================================================================
# 12. REVIEW OVERRIDE BY SENIOR REVIEWER
# =============================================================================

@pytest.mark.unit
class TestReviewOverride:
    """Senior reviewers can override AI decisions."""

    def test_override_reject_to_accept(self, service, mock_db):
        """A human reviewer can override a REJECT to ACCEPT."""
        doc = _make_smart_document(
            decision=DocumentDecision.REJECT,
            status="REJECTED",
            reviewed_by="SYSTEM",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        # Simulate manual override by updating decision fields
        override_decision = ReviewDecision(
            decision=DocumentDecision.ACCEPT.value,
            confidence=100,
            reasons=["Manual override by senior reviewer: document verified"],
            auto_approved=False,
        )

        service._update_document_status(doc.id, override_decision)

        assert doc.decision == DocumentDecision.ACCEPT
        assert doc.status == "APPROVED"

    def test_override_accept_to_reject(self, service, mock_db):
        """A human reviewer can override an ACCEPT to REJECT."""
        doc = _make_smart_document(
            decision=DocumentDecision.ACCEPT,
            status="APPROVED",
            reviewed_by="SYSTEM",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        override_decision = ReviewDecision(
            decision=DocumentDecision.REJECT.value,
            confidence=100,
            reasons=["Manual override: document is fraudulent"],
            rejection_category=RejectionCategory.OTHER.value,
            fix_instructions="Contact compliance team",
        )

        service._update_document_status(doc.id, override_decision)

        assert doc.decision == DocumentDecision.REJECT
        assert doc.status == "REJECTED"
        assert doc.fix_instructions == "Contact compliance team"


# =============================================================================
# 13. REVIEW METRICS TRACKING
# =============================================================================

@pytest.mark.unit
class TestReviewMetrics:
    """Review statistics should be accurately computed."""

    def test_get_review_stats_calculations(self, service, mock_db):
        """get_review_stats should compute approval/rejection rates correctly."""
        # Mock stats query: total=10, approved=6, rejected=3, needs_review=1,
        #                   auto_approved=5, auto_rejected=2, avg_seconds=120
        mock_db.execute.return_value.fetchone.return_value = (
            10, 6, 3, 1, 5, 2, 120.0
        )
        # Mock rejection reasons query
        mock_db.execute.return_value.fetchall.return_value = [
            ("EXPIRED", 2),
            ("SCREENSHOT", 1),
        ]

        stats = service.get_review_stats(organization_id=1, days=30)

        assert stats["total_reviewed"] == 10
        assert stats["approved"] == 6
        assert stats["rejected"] == 3
        assert stats["approval_rate_pct"] == 60.0
        assert stats["rejection_rate_pct"] == 30.0
        assert stats["auto_rate_pct"] == 70.0  # (5+2)/10 = 70%
        assert stats["avg_review_time_seconds"] == 120.0

    def test_get_review_stats_zero_total(self, service, mock_db):
        """Stats with zero documents should return 0% rates without division error."""
        mock_db.execute.return_value.fetchone.return_value = (
            0, 0, 0, 0, 0, 0, None
        )
        mock_db.execute.return_value.fetchall.return_value = []

        stats = service.get_review_stats(organization_id=1, days=30)

        assert stats["total_reviewed"] == 0
        assert stats["approval_rate_pct"] == 0
        assert stats["rejection_rate_pct"] == 0
        assert stats["auto_rate_pct"] == 0
        assert stats["avg_review_time_seconds"] is None

    def test_review_stats_include_common_rejection_reasons(self, service, mock_db):
        """Stats should include the top rejection categories."""
        mock_db.execute.return_value.fetchone.return_value = (
            20, 12, 6, 2, 10, 4, 90.5
        )
        mock_db.execute.return_value.fetchall.return_value = [
            ("EXPIRED", 3),
            ("SCREENSHOT", 2),
            ("WRONG_TYPE", 1),
        ]

        stats = service.get_review_stats(organization_id=1, days=30)

        assert len(stats["common_rejection_reasons"]) == 3
        assert stats["common_rejection_reasons"][0]["category"] == "EXPIRED"
        assert stats["common_rejection_reasons"][0]["count"] == 3


# =============================================================================
# 14. CROSS-DOCUMENT VALIDATION TRIGGERS
# =============================================================================

@pytest.mark.unit
class TestCrossDocumentValidation:
    """Cross-document consistency checks should detect mismatches."""

    def test_employer_mismatch_between_paystub_and_w2(self, service, mock_db):
        """Different employer names on paystub vs W2 should flag inconsistency."""
        current_doc = _make_smart_document(
            id=1, doc_type=DocType.PAYSTUB,
            extracted_employer="ACME Corp",
            extracted_names=["John Smith"],
        )
        other_doc = _make_smart_document(
            id=2, doc_type=DocType.W2,
            extracted_employer="Totally Different Inc",
            extracted_names=["John Smith"],
            decision=DocumentDecision.ACCEPT,
        )

        mock_db.query.return_value.filter.return_value.first.return_value = current_doc
        mock_db.query.return_value.filter.return_value.all.return_value = [other_doc]

        # Configure fuzzy ratio to return low score for mismatch
        service._owner_matcher._fuzzy_ratio.return_value = 20

        issues = service._check_cross_document_consistency(
            document_id=1, loan_id=100,
        )

        assert len(issues) > 0
        assert any("employer" in issue.lower() for issue in issues)

    def test_income_variance_flagged(self, service, mock_db):
        """Large income variance between paystub and W2 should be flagged."""
        current_doc = _make_smart_document(
            id=1, doc_type=DocType.PAYSTUB,
            extracted_employer="ACME Corp",
            extracted_amount=Decimal("150000"),
            extracted_names=[],
        )
        other_doc = _make_smart_document(
            id=2, doc_type=DocType.W2,
            extracted_employer="ACME Corp",
            extracted_amount=Decimal("80000"),
            extracted_names=[],
            decision=DocumentDecision.ACCEPT,
        )

        mock_db.query.return_value.filter.return_value.first.return_value = current_doc
        mock_db.query.return_value.filter.return_value.all.return_value = [other_doc]
        service._owner_matcher._fuzzy_ratio.return_value = 95  # employers match

        issues = service._check_cross_document_consistency(
            document_id=1, loan_id=100,
        )

        assert len(issues) > 0
        assert any("income" in issue.lower() or "variance" in issue.lower()
                    for issue in issues)

    def test_no_issues_when_no_other_approved_docs(self, service, mock_db):
        """If no other approved docs exist, cross-doc check returns empty."""
        current_doc = _make_smart_document(id=1, doc_type=DocType.PAYSTUB)
        mock_db.query.return_value.filter.return_value.first.return_value = current_doc
        mock_db.query.return_value.filter.return_value.all.return_value = []

        issues = service._check_cross_document_consistency(
            document_id=1, loan_id=100,
        )
        assert issues == []

    def test_consistency_issues_trigger_needs_review(self, service):
        """Consistency issues should set NEEDS_REVIEW with HIGH priority."""
        decision = service._make_decision(
            quality=90,
            type_match=True,
            name_match=True,
            freshness=True,
            completeness=100,
            fraud_indicators=[],
            is_screenshot=False,
            consistency_issues=["Employer mismatch: ACME vs Widget Co"],
        )
        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.needs_human_review is True


# =============================================================================
# ADDITIONAL EDGE CASE TESTS
# =============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Edge cases and error handling."""

    def test_document_not_found_returns_needs_review(self, service, mock_db):
        """review_document with nonexistent document ID should return NEEDS_REVIEW."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        decision = service.review_document(99999)

        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.review_priority == "CRITICAL"

    def test_s3_fetch_failure_returns_needs_review(self, service, mock_db):
        """When file content cannot be fetched from S3, result is NEEDS_REVIEW."""
        doc = _make_smart_document(storage_key="docs/missing.pdf")
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch.object(service, "_fetch_from_s3", return_value=None):
            decision = service.review_document(doc.id, file_content=None)

        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.review_priority == "HIGH"

    def test_review_exception_recovers_gracefully(self, service, mock_db):
        """If an exception occurs during review, document status reverts to
        PROCESSING and NEEDS_REVIEW is returned."""
        doc = _make_smart_document()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch.object(service, "_check_quality", side_effect=RuntimeError("boom")):
            decision = service.review_document(doc.id, file_content=_make_pdf_bytes())

        assert decision.decision == DocumentDecision.NEEDS_REVIEW.value
        assert decision.review_priority == "HIGH"
        assert "error" in decision.reasons[0].lower()

    def test_no_ocr_text_still_processes(self, service, mock_db):
        """Document without OCR text should still run quality and screenshot checks."""
        doc = _make_smart_document(ocr_text=None, doc_type=DocType.PAYSTUB)
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        ss_result = MagicMock(is_screenshot=False, confidence=0.0)
        service._screenshot_detector.detect.return_value = ss_result

        file_content = _make_pdf_bytes("", size=20_000)

        # Should not raise; text extraction will return empty string
        with patch.object(service, "_extract_text", return_value=""):
            decision = service.review_document(doc.id, file_content=file_content)

        # Should complete without error
        assert decision.decision in (
            DocumentDecision.ACCEPT.value,
            DocumentDecision.REJECT.value,
            DocumentDecision.NEEDS_REVIEW.value,
        )

    def test_update_linked_request_on_accept(self, service, mock_db):
        """When document is accepted, linked DocumentRequest should be updated."""
        doc = _make_smart_document(request_id=42)
        request = MagicMock()
        request.id = 42

        # First call returns doc, second call returns request
        mock_db.query.return_value.filter.return_value.first.side_effect = [doc, request]

        decision = ReviewDecision(
            decision=DocumentDecision.ACCEPT.value,
            confidence=95,
            reasons=["All checks passed"],
            auto_approved=True,
        )

        service._update_document_status(doc.id, decision)

        assert request.status == RequestStatus.ACCEPTED

    def test_review_decision_dataclass_defaults(self):
        """ReviewDecision should have sensible defaults."""
        rd = ReviewDecision(
            decision="ACCEPT",
            confidence=90,
            reasons=["OK"],
        )
        assert rd.freshness_valid is True
        assert rd.type_match is True
        assert rd.name_match is True
        assert rd.auto_approved is False
        assert rd.needs_human_review is False
        assert rd.review_priority == "NORMAL"

    def test_batch_review_result_dataclass(self):
        """BatchReviewResult should hold aggregate counts."""
        br = BatchReviewResult(
            total=10,
            approved=7,
            rejected=2,
            needs_review=1,
            results=[],
        )
        assert br.total == 10
        assert br.approved == 7
        assert br.rejected + br.needs_review == 3
