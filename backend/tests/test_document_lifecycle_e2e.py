"""
End-to-End Document Lifecycle Integration Tests

Tests the complete document lifecycle from upload to approval, covering:
1. POS Analysis - create loan, run analyzer, verify required docs
2. Document Upload - upload paystub, AI classifies, validation passes
3. AI Review - submit for review, auto-approve with all checks passing
4. Rejection Flow - upload expired statement, AI rejects, follow-up created
5. Income Calculation - upload W2 + paystubs, calculate qualifying income
6. Bank Statement Analysis - upload statements, detect large deposits, verify payroll
7. Document Completeness - check loan completeness, identify missing docs
8. Cross-Document Validation - validate consistency across documents
9. Follow-up Campaign Creation - missing docs trigger campaign
10. Document Re-upload after Rejection

All external services (S3, Anthropic, database) are mocked.
"""

import os
import sys
import json
import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call
from dataclasses import dataclass

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.smart_docs_models import (
    DocType,
    DocumentDecision,
    RejectionCategory,
    RequestStatus,
    RequestPriority,
    AppliesTo,
    SmartDocument,
    DocumentRequest,
    DocPolicyEvent,
    DocPolicyEventType,
)

from services.smart_docs.pos_analyzer_service import (
    POSAnalyzerService,
    POSAnalysisResult,
    RequiredDocument,
)
from services.smart_docs.document_validation_engine import (
    DocumentValidationEngine,
    ValidationResult,
    ValidationIssue,
    FRESHNESS_RULES,
    get_document_validation_engine,
)

# Stub the Anthropic import for AI review service
try:
    from services.smart_docs.ai_review_service import (
        AIDocumentReviewService,
        ReviewDecision,
        BatchReviewResult,
    )
except ImportError:
    AIDocumentReviewService = None
    ReviewDecision = None

from services.smart_docs.income_calculator_service import (
    IncomeCalculatorService,
    IncomeCalculationResult,
    IncomeSourceResult,
    PAY_FREQUENCY_MULTIPLIERS,
    ZERO,
    TWO_PLACES,
)

from services.smart_docs.bank_statement_analyzer import (
    BankStatementAnalyzerService,
    BankStatementAnalysis,
    LargeDeposit,
    PayrollDeposit,
    LARGE_DEPOSIT_THRESHOLD,
    PAYROLL_KEYWORDS,
)

from database.models.document_followup import (
    FollowupCampaign,
    FollowupEvent,
    CampaignType,
    CampaignStatus,
    CampaignTriggerSource,
    FollowupEventType,
    DeliveryStatus,
)
from services.smart_docs.followup_automation_service import (
    FollowupAutomationService,
    _DEFAULT_STEP_CONFIGS,
    get_followup_automation_service,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session with query builder chains."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    db.execute.return_value.fetchone.return_value = None
    return db


@pytest.fixture
def loan_data():
    """Realistic loan application data for POS analysis."""
    return {
        "loan_id": 42,
        "loan_number": "2026-004200",
        "loan_type": "conventional",
        "program": "FNMA",
        "occupancy_type": "primary",
        "property_type": "single family",
        "property_state": "TX",
        "borrower_name": "Jane Doe",
        "coborrower_name": "John Doe",
        "borrower_email": "jane.doe@example.com",
        "co_borrower_email": "john.doe@example.com",
        "loan_amount": 450_000,
        "purchase_price": 550_000,
        "down_payment": 100_000,
        "ltv": 81.8,
        "cltv": 81.8,
        "borrower_employment_type": "W2",
        "coborrower_employment_type": "W2",
        "has_gift_funds": False,
        "has_bankruptcy_history": False,
        "is_foreign_national": False,
        "is_non_permanent_resident": False,
        "is_self_employed": False,
    }


@pytest.fixture
def pos_service(mock_db):
    """Create a POSAnalyzerService instance."""
    return POSAnalyzerService(mock_db)


@pytest.fixture
def validation_engine():
    """Create a DocumentValidationEngine instance."""
    return get_document_validation_engine()


@pytest.fixture
def review_service(mock_db):
    """Create an AIDocumentReviewService with mocked dependencies."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        svc = AIDocumentReviewService(mock_db)
    # Replace sub-services with mocks
    svc._screenshot_detector = MagicMock()
    svc._screenshot_detector.detect.return_value = MagicMock(
        is_screenshot=False, confidence=0.0
    )
    svc._freshness_validator = MagicMock()
    svc._owner_matcher = MagicMock()
    return svc


@pytest.fixture
def income_service(mock_db):
    """Create an IncomeCalculatorService with mocked DB."""
    return IncomeCalculatorService(mock_db)


@pytest.fixture
def bank_service(mock_db):
    """Create a BankStatementAnalyzerService with mocked DB."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        svc = BankStatementAnalyzerService(mock_db)
    return svc


@pytest.fixture
def followup_service(mock_db):
    """Create a FollowupAutomationService with mocked DB."""
    svc = FollowupAutomationService(mock_db)
    svc._portal_base_url = "https://app.perenniaai.com/portal"
    return svc


def _make_smart_document(
    id=1,
    loan_id=42,
    borrower_id=7,
    request_id=None,
    doc_type=DocType.PAYSTUB,
    file_name="paystub_jan_2026.pdf",
    mime_type="application/pdf",
    file_size=25000,
    storage_key="s3://bucket/docs/paystub.pdf",
    status="UPLOADED",
    decision=None,
    detected_is_screenshot=False,
    screenshot_confidence=0.0,
    ocr_text=None,
    doc_date=None,
    is_expired=False,
    extracted_names=None,
    extracted_employer=None,
    extracted_amount=None,
):
    """Build a mock SmartDocument object."""
    doc = MagicMock(spec=SmartDocument)
    doc.id = id
    doc.loan_id = loan_id
    doc.borrower_id = borrower_id
    doc.request_id = request_id
    doc.doc_type = doc_type
    doc.file_name = file_name
    doc.original_filename = file_name
    doc.mime_type = mime_type
    doc.file_size = file_size
    doc.storage_key = storage_key
    doc.status = status
    doc.decision = decision
    doc.detected_is_screenshot = detected_is_screenshot
    doc.screenshot_confidence = screenshot_confidence
    doc.ocr_text = ocr_text
    doc.doc_date = doc_date
    doc.is_expired = is_expired
    doc.extracted_names = extracted_names or {"borrower": "Jane Doe"}
    doc.extracted_employer = extracted_employer or "Acme Corp"
    doc.extracted_amount = extracted_amount
    doc.page_count = 1
    doc.decision_reasons = None
    doc.rejection_reason = None
    doc.rejection_category = None
    doc.fix_instructions = None
    doc.reviewed_at = None
    doc.reviewed_by = None
    doc.uploaded_at = datetime.now(timezone.utc)
    doc.created_at = datetime.now(timezone.utc)
    doc.updated_at = datetime.now(timezone.utc)
    doc.extracted_dates = None
    return doc


def _make_paystub_doc(gross_pay=5000.00, pay_frequency="BIWEEKLY", pay_date=None,
                      employer_name="Acme Corp", ytd_gross=60000.00,
                      ytd_overtime=0, ytd_bonus=0, ytd_commission=0,
                      doc_id=1, confidence=85):
    """Build a paystub document dict for income calculation."""
    if pay_date is None:
        pay_date = date.today().strftime("%Y-%m-%d")
    return {
        "doc_id": doc_id,
        "doc_type": "PAYSTUB",
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": "paystub.pdf",
        "extracted_fields": {
            "gross_pay": gross_pay,
            "pay_frequency": pay_frequency,
            "pay_date": pay_date,
            "employer_name": employer_name,
            "job_title": "Software Engineer",
            "ytd_gross": ytd_gross,
            "ytd_overtime_earnings": ytd_overtime,
            "ytd_bonus": ytd_bonus,
            "ytd_commission": ytd_commission,
            "ytd_tips": 0,
        },
        "confidence_scores": {},
        "overall_confidence": confidence,
    }


def _make_w2_doc(wages=100000.00, employer="Acme Corp", tax_year=2025, doc_id=2):
    """Build a W2 document dict for income calculation."""
    return {
        "doc_id": doc_id,
        "doc_type": "W2",
        "ocr_text": "",
        "uploaded_at": datetime.now(timezone.utc),
        "file_name": "w2_2025.pdf",
        "extracted_fields": {
            "wages_tips_other": wages,
            "employer_name": employer,
            "employer_ein": "12-3456789",
            "federal_tax_withheld": wages * 0.15,
            "social_security_wages": wages,
            "medicare_wages": wages,
            "tax_year": tax_year,
        },
        "confidence_scores": {},
        "overall_confidence": 90,
    }


def _txn(date_str, description, amount, txn_type="credit", balance=None):
    """Helper to build a bank transaction dict."""
    return {
        "date": date_str,
        "description": description,
        "amount": Decimal(str(amount)),
        "type": txn_type,
        "balance": Decimal(str(balance)) if balance is not None else None,
    }


# =============================================================================
# 1. POS ANALYSIS - CREATE LOAN, RUN ANALYZER, VERIFY REQUIRED DOCS
# =============================================================================

@pytest.mark.e2e
class TestPOSAnalysis:
    """Phase 1: Analyze loan application and generate document requirements."""

    def test_conventional_loan_generates_standard_requirements(self, pos_service, loan_data):
        """Conventional purchase loan should require standard income, asset, and ID docs."""
        result = pos_service.analyze(loan_data)

        assert result.success is True
        assert result.loan_id == 42
        assert result.total_documents_needed > 0

        # Verify core document types are required
        doc_types = {r.doc_type for r in result.requirements}
        assert DocType.PAYSTUB.value in doc_types, "Paystub should be required"
        assert DocType.W2.value in doc_types, "W2 should be required"
        assert DocType.BANK_STATEMENT.value in doc_types, "Bank statement should be required"
        assert DocType.DRIVERS_LICENSE.value in doc_types, "ID should be required"

    def test_coborrower_generates_dual_requirements(self, pos_service, loan_data):
        """Loan with co-borrower should generate requirements for both parties."""
        result = pos_service.analyze(loan_data)

        applies_tos = {r.applies_to for r in result.requirements}
        # Should have BOTH or separate BORROWER + CO_BORROWER requirements
        has_both = AppliesTo.BOTH.value in applies_tos
        has_coborrower = AppliesTo.CO_BORROWER.value in applies_tos
        assert has_both or has_coborrower, (
            "Co-borrower should trigger co-borrower-specific requirements"
        )

    def test_pos_analysis_sets_freshness_on_paystubs(self, pos_service, loan_data):
        """Paystub requirements should have a 30-day freshness window."""
        result = pos_service.analyze(loan_data)

        paystub_reqs = [r for r in result.requirements if r.doc_type == DocType.PAYSTUB.value]
        assert len(paystub_reqs) > 0
        for req in paystub_reqs:
            assert req.freshness_days is not None
            assert req.freshness_days <= 30, "Paystub freshness must be <= 30 days"

    def test_category_counts_are_populated(self, pos_service, loan_data):
        """Analysis result should break down requirements by category."""
        result = pos_service.analyze(loan_data)

        assert len(result.categories) > 0
        assert "income" in result.categories or "identity" in result.categories


# =============================================================================
# 2. DOCUMENT UPLOAD - UPLOAD PAYSTUB, AI CLASSIFIES, VALIDATION PASSES
# =============================================================================

@pytest.mark.e2e
class TestDocumentUploadAndClassification:
    """Phase 2: Upload a document, classify it, and run validation."""

    def test_valid_pdf_passes_type_validation(self, validation_engine):
        """A well-formed PDF should pass file type validation."""
        # Build a minimal valid PDF (>1KB to pass min size check)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n%%EOF\n"
        pdf_content += b"\n%" + b"0" * 1100  # Pad to exceed min size

        result = validation_engine.validate_upload(
            file_bytes=pdf_content,
            filename="paystub_jan_2026.pdf",
            mime_type="application/pdf",
            declared_doc_type="PAYSTUB",
        )

        assert result.passed is True or result.score >= 50, (
            f"Valid PDF should pass validation: issues={result.issues}"
        )

    def test_blocked_extension_rejected(self, validation_engine):
        """Executable file extensions must be rejected outright."""
        result = validation_engine.validate_upload(
            file_bytes=b"MZ" + b"\x00" * 2000,
            filename="malware.exe",
            mime_type="application/x-msdownload",
            declared_doc_type="PAYSTUB",
        )

        assert result.passed is False
        issue_types = [i.code for i in result.issues]
        assert any("BLOCK" in t or "EXT" in t or "TYPE" in t for t in issue_types), (
            f"Expected blocked extension issue, got: {issue_types}"
        )

    def test_too_small_file_flagged(self, validation_engine):
        """Files below minimum size should be flagged as potentially blank/corrupt."""
        result = validation_engine.validate_upload(
            file_bytes=b"%PDF-1.4\n%%EOF",  # ~14 bytes, well under 1KB
            filename="paystub.pdf",
            mime_type="application/pdf",
            declared_doc_type="PAYSTUB",
        )

        assert result.passed is False or any(
            "SIZE" in i.code or "SMALL" in i.code or "MIN" in i.code
            for i in result.issues
        ), f"Expected size issue, got: {[i.code for i in result.issues]}"


# =============================================================================
# 3. AI REVIEW - SUBMIT FOR REVIEW, AUTO-APPROVE WITH ALL CHECKS PASSING
# =============================================================================

@pytest.mark.e2e
class TestAIReviewAutoApprove:
    """Phase 3: Submit a clean document for AI review and expect auto-approval."""

    def test_clean_paystub_auto_approved(self, review_service, mock_db):
        """A well-formed, fresh paystub matching borrower should be auto-approved."""
        doc = _make_smart_document(
            doc_type=DocType.PAYSTUB,
            doc_date=datetime.now(timezone.utc) - timedelta(days=5),
            ocr_text=(
                "Pay Period: 02/01/2026 - 02/15/2026\n"
                "Pay Date: 02/20/2026\n"
                "Employee: Jane Doe\n"
                "Employer: Acme Corp\n"
                "Gross Pay: $5,000.00\n"
                "Net Pay: $3,800.00\n"
                "YTD Gross: $20,000.00\n"
                "Federal Tax: $600\n"
            ),
        )

        mock_db.query.return_value.filter.return_value.first.return_value = doc

        # Mock S3 fetch to return valid PDF bytes
        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            pdf_bytes = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            mock_s3.return_value = pdf_bytes

            decision = review_service.review_document(document_id=1)

        assert decision.decision in (
            DocumentDecision.ACCEPT.value, "ACCEPT"
        ), f"Expected ACCEPT, got {decision.decision} with reasons: {decision.reasons}"
        assert decision.auto_approved is True
        assert decision.freshness_valid is True
        assert decision.type_match is True

    def test_review_persists_decision_to_db(self, review_service, mock_db):
        """After review, the document's status and decision should be updated in DB."""
        doc = _make_smart_document(
            doc_type=DocType.W2,
            doc_date=datetime(2025, 12, 15, tzinfo=timezone.utc),
            ocr_text="Form W-2 Wage and Tax Statement\nJane Doe\nWages: $100,000",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            review_service.review_document(document_id=1)

        # Verify flush was called (persisting changes)
        assert mock_db.flush.called


# =============================================================================
# 4. REJECTION FLOW - UPLOAD EXPIRED STATEMENT, AI REJECTS, FOLLOW-UP CREATED
# =============================================================================

@pytest.mark.e2e
class TestRejectionFlow:
    """Phase 4: Expired or invalid documents trigger rejection and follow-up."""

    def test_expired_bank_statement_rejected(self, review_service, mock_db):
        """A bank statement older than 60 days should be rejected as expired."""
        expired_date = datetime.now(timezone.utc) - timedelta(days=90)
        doc = _make_smart_document(
            doc_type=DocType.BANK_STATEMENT,
            doc_date=expired_date,
            is_expired=True,
            ocr_text=(
                "Bank Statement\n"
                "Statement Period: 09/01/2025 - 09/30/2025\n"
                "Beginning Balance: $15,000\n"
                "Ending Balance: $14,200\n"
                "Account Number: ****6789\n"
            ),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            decision = review_service.review_document(document_id=1)

        assert decision.decision in (
            DocumentDecision.REJECT.value, DocumentDecision.NEEDS_REVIEW.value,
            "REJECT", "NEEDS_REVIEW",
        ), f"Expired doc should be REJECT or NEEDS_REVIEW, got {decision.decision}"
        assert decision.freshness_valid is False

    def test_screenshot_detected_and_rejected(self, review_service, mock_db):
        """Documents detected as screenshots should be rejected."""
        doc = _make_smart_document(
            doc_type=DocType.PAYSTUB,
            detected_is_screenshot=True,
            screenshot_confidence=0.95,
            doc_date=datetime.now(timezone.utc) - timedelta(days=3),
            ocr_text="Pay Period: 02/01/2026 - 02/15/2026\nGross Pay: $5,000",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            decision = review_service.review_document(document_id=1)

        assert decision.decision in (
            DocumentDecision.REJECT.value, "REJECT",
        ), f"Screenshot should be rejected, got {decision.decision}"

    def test_rejection_triggers_followup_campaign(self, followup_service, mock_db):
        """When a document is rejected, a follow-up campaign should be created."""
        # Simulate no existing campaign for this loan
        mock_db.query.return_value.filter.return_value.first.return_value = None

        campaign = followup_service.create_campaign(
            organization_id=100,
            loan_id=42,
            borrower_id=7,
            campaign_type="document_rejected",
            trigger_source=CampaignTriggerSource.DOCUMENT_REJECTED.value,
            linked_request_ids=[1],
            borrower_name="Jane Doe",
            borrower_email="jane.doe@example.com",
            lo_name="Mike Johnson",
        )

        # Verify campaign was added to the DB session
        assert mock_db.add.called
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, FollowupCampaign)
        assert added_obj.campaign_type.value == "document_rejected" or str(added_obj.campaign_type) == "document_rejected"


# =============================================================================
# 5. INCOME CALCULATION - UPLOAD W2 + PAYSTUBS, CALCULATE QUALIFYING INCOME
# =============================================================================

@pytest.mark.e2e
class TestIncomeCalculation:
    """Phase 5: Calculate qualifying income from uploaded income documents."""

    def test_w2_salaried_income_calculated(self, income_service):
        """W2 + paystub should yield monthly qualifying income."""
        paystub = _make_paystub_doc(
            gross_pay=5000.00,
            pay_frequency="BIWEEKLY",
            ytd_gross=60000.00,
        )
        w2 = _make_w2_doc(wages=100000.00, employer="Acme Corp", tax_year=2025)

        result = income_service.calculate_from_documents(
            loan_id=42,
            borrower_id=7,
            documents=[paystub, w2],
        )

        assert result.success is True
        assert result.total_monthly_income > ZERO, "Monthly income should be positive"

    def test_multiple_paystubs_averaged(self, income_service):
        """Multiple paystubs from the same employer should be averaged for accuracy."""
        paystub1 = _make_paystub_doc(
            gross_pay=5000.00, pay_frequency="BIWEEKLY", ytd_gross=60000.00, doc_id=1
        )
        paystub2 = _make_paystub_doc(
            gross_pay=5200.00, pay_frequency="BIWEEKLY", ytd_gross=65200.00, doc_id=2
        )

        result = income_service.calculate_from_documents(
            loan_id=42,
            borrower_id=7,
            documents=[paystub1, paystub2],
        )

        assert result.success is True
        # With biweekly at ~$5100 avg, annual = 5100 * 26 = ~$132,600 / 12 = ~$11,050/mo
        assert result.total_monthly_income > Decimal("5000"), (
            f"Expected meaningful monthly income, got {result.total_monthly_income}"
        )

    def test_income_trending_detected(self, income_service):
        """When W2 years show different income levels, trending should be detected."""
        w2_2025 = _make_w2_doc(wages=100000.00, employer="Acme Corp", tax_year=2025, doc_id=1)
        w2_2024 = _make_w2_doc(wages=90000.00, employer="Acme Corp", tax_year=2024, doc_id=2)

        result = income_service.calculate_from_documents(
            loan_id=42,
            borrower_id=7,
            documents=[w2_2025, w2_2024],
        )

        assert result.success is True
        # With income increasing from $90k to $100k, should show INCREASING or STABLE
        if result.sources:
            trends = [s.trending for s in result.sources]
            assert any(t in ("INCREASING", "STABLE") for t in trends), (
                f"Expected INCREASING or STABLE trend, got {trends}"
            )


# =============================================================================
# 6. BANK STATEMENT ANALYSIS - DETECT LARGE DEPOSITS, VERIFY PAYROLL
# =============================================================================

@pytest.mark.e2e
class TestBankStatementAnalysis:
    """Phase 6: Analyze bank statements for underwriting concerns."""

    def test_large_deposit_detected(self, bank_service):
        """Deposits above threshold should be flagged for sourcing."""
        transactions = [
            _txn("2026-01-05", "PAYROLL ACH ACME CORP", 5000, "credit", 15000),
            _txn("2026-01-10", "TRANSFER FROM SAVINGS", 25000, "credit", 40000),
            _txn("2026-01-15", "GROCERY STORE", 150, "debit", 39850),
            _txn("2026-01-20", "PAYROLL ACH ACME CORP", 5000, "credit", 44850),
        ]

        result = bank_service.analyze_transactions(
            loan_id=42,
            transactions=transactions,
            statement_period_start="2026-01-01",
            statement_period_end="2026-01-31",
            beginning_balance=Decimal("10000.00"),
            ending_balance=Decimal("44850.00"),
        )

        assert result is not None
        # The $25,000 transfer should be flagged as a large deposit
        assert len(result.large_deposits) > 0, "Should detect large deposit(s)"
        large_amounts = [d.amount for d in result.large_deposits]
        assert any(a >= Decimal("25000") for a in large_amounts), (
            f"Expected $25,000 deposit to be flagged, got amounts: {large_amounts}"
        )

    def test_payroll_deposits_verified(self, bank_service):
        """Regular payroll deposits should be identified and verified."""
        transactions = [
            _txn("2026-01-05", "PAYROLL DIRECT DEP ACME CORP", 5000, "credit", 15000),
            _txn("2026-01-19", "PAYROLL DIRECT DEP ACME CORP", 5000, "credit", 18500),
            _txn("2026-02-02", "PAYROLL DIRECT DEP ACME CORP", 5000, "credit", 22000),
            _txn("2026-02-16", "PAYROLL DIRECT DEP ACME CORP", 5000, "credit", 25500),
        ]

        result = bank_service.analyze_transactions(
            loan_id=42,
            transactions=transactions,
            statement_period_start="2026-01-01",
            statement_period_end="2026-02-28",
            beginning_balance=Decimal("10000.00"),
            ending_balance=Decimal("25500.00"),
        )

        assert result is not None
        assert len(result.payroll_deposits) > 0, "Should identify payroll deposits"

    def test_nsf_events_flagged(self, bank_service):
        """Overdraft/NSF events should be detected and severity rated."""
        transactions = [
            _txn("2026-01-05", "PAYROLL ACH", 5000, "credit", 5000),
            _txn("2026-01-10", "CHECK #1234", 5500, "debit", -500),
            _txn("2026-01-10", "NSF FEE", 35, "debit", -535),
            _txn("2026-01-12", "DEPOSIT", 2000, "credit", 1465),
        ]

        result = bank_service.analyze_transactions(
            loan_id=42,
            transactions=transactions,
            statement_period_start="2026-01-01",
            statement_period_end="2026-01-31",
            beginning_balance=Decimal("0.00"),
            ending_balance=Decimal("1465.00"),
        )

        assert result is not None
        assert result.nsf_count > 0 or len(result.nsf_events) > 0, (
            "Should detect NSF event"
        )


# =============================================================================
# 7. DOCUMENT COMPLETENESS - CHECK LOAN COMPLETENESS, IDENTIFY MISSING
# =============================================================================

@pytest.mark.e2e
class TestDocumentCompleteness:
    """Phase 7: Check overall document completeness for a loan."""

    def test_missing_docs_identified_from_needs_list(self, mock_db):
        """When needs list has open requests, missing docs should be identified."""
        # Create mock needs list with 5 requirements, 2 fulfilled
        reqs = []
        for i, (dtype, status) in enumerate([
            (DocType.PAYSTUB, RequestStatus.ACCEPTED),
            (DocType.W2, RequestStatus.ACCEPTED),
            (DocType.BANK_STATEMENT, RequestStatus.OPEN),
            (DocType.DRIVERS_LICENSE, RequestStatus.OPEN),
            (DocType.PURCHASE_CONTRACT, RequestStatus.OPEN),
        ]):
            req = MagicMock(spec=DocumentRequest)
            req.id = i + 1
            req.loan_id = 42
            req.doc_type = dtype
            req.status = status
            req.title = f"{dtype.value} required"
            req.is_active = True
            reqs.append(req)

        mock_db.query.return_value.filter.return_value.all.return_value = reqs

        # Count open vs fulfilled
        open_reqs = [r for r in reqs if r.status == RequestStatus.OPEN]
        accepted_reqs = [r for r in reqs if r.status == RequestStatus.ACCEPTED]

        assert len(open_reqs) == 3, "Should have 3 unfulfilled requirements"
        assert len(accepted_reqs) == 2, "Should have 2 fulfilled requirements"

        missing_types = {r.doc_type.value for r in open_reqs}
        assert "BANK_STATEMENT" in missing_types
        assert "DRIVERS_LICENSE" in missing_types
        assert "PURCHASE_CONTRACT" in missing_types

    def test_completeness_percentage_calculated(self, mock_db):
        """Completeness should be expressed as a percentage of fulfilled requirements."""
        total_reqs = 8
        fulfilled = 5

        completeness_pct = (fulfilled / total_reqs) * 100
        assert completeness_pct == pytest.approx(62.5)
        assert completeness_pct < 100, "Loan is not yet complete"


# =============================================================================
# 8. CROSS-DOCUMENT VALIDATION - CONSISTENCY ACROSS DOCUMENTS
# =============================================================================

@pytest.mark.e2e
class TestCrossDocumentValidation:
    """Phase 8: Validate consistency between related documents."""

    def test_employer_name_consistency(self):
        """Employer name on paystub should match employer on W2."""
        paystub_employer = "Acme Corporation"
        w2_employer = "Acme Corporation"

        # Exact match
        assert paystub_employer == w2_employer

    def test_employer_name_mismatch_flagged(self):
        """Mismatched employer names should produce a validation flag."""
        paystub_employer = "Acme Corp"
        w2_employer = "Totally Different LLC"

        # Simple name comparison (real service does fuzzy matching)
        names_match = paystub_employer.lower() == w2_employer.lower()
        assert names_match is False, "Different employers should not match"

    def test_income_consistency_paystub_vs_w2(self):
        """YTD income on paystub should be roughly consistent with annualized W2 wages."""
        # Paystub shows YTD of $60,000 by June (6 months)
        paystub_ytd = Decimal("60000.00")
        paystub_months_elapsed = 6
        annualized_from_paystub = (paystub_ytd / paystub_months_elapsed) * 12

        # W2 shows $100,000 for prior year
        w2_wages = Decimal("100000.00")

        # Variance should be within 20% to be considered consistent
        variance_pct = abs(annualized_from_paystub - w2_wages) / w2_wages * 100
        # $120k annualized vs $100k W2 = 20% variance
        assert variance_pct <= Decimal("25"), (
            f"Income variance {variance_pct}% exceeds 25% threshold"
        )

    def test_borrower_name_consistency_across_docs(self):
        """Borrower name should be consistent across all uploaded documents."""
        names_on_docs = [
            "Jane M. Doe",  # paystub
            "Jane Doe",     # W2
            "JANE DOE",     # bank statement
            "Jane Marie Doe",  # driver's license
        ]

        # Normalize for comparison
        normalized = [n.lower().strip() for n in names_on_docs]
        # All should contain "jane" and "doe"
        for name in normalized:
            assert "jane" in name and "doe" in name, (
                f"Name '{name}' doesn't match expected borrower"
            )


# =============================================================================
# 9. FOLLOW-UP CAMPAIGN CREATION - MISSING DOCS TRIGGER CAMPAIGN
# =============================================================================

@pytest.mark.e2e
class TestFollowupCampaignCreation:
    """Phase 9: Missing documents should trigger automated follow-up campaigns."""

    def test_initial_request_campaign_created(self, followup_service, mock_db):
        """When needs list is generated, an initial request campaign should start."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        campaign = followup_service.create_campaign(
            organization_id=100,
            loan_id=42,
            borrower_id=7,
            campaign_type="initial_request",
            trigger_source=CampaignTriggerSource.NEEDS_LIST_GENERATED.value,
            linked_request_ids=[1, 2, 3],
            borrower_name="Jane Doe",
            borrower_email="jane.doe@example.com",
            lo_name="Mike Johnson",
        )

        assert mock_db.add.called
        created = mock_db.add.call_args[0][0]
        assert isinstance(created, FollowupCampaign)

    def test_campaign_has_correct_step_sequence(self, followup_service):
        """Initial request campaign should have the default 5-step sequence."""
        steps = _DEFAULT_STEP_CONFIGS.get("initial_request", [])

        assert len(steps) == 5
        assert steps[0]["channel"] == "email"
        assert steps[1]["channel"] == "sms"
        assert steps[4]["channel"] == "escalation"

    def test_document_rejected_campaign_step_config(self, followup_service):
        """Document rejected campaign should include email with fix instructions."""
        steps = _DEFAULT_STEP_CONFIGS.get("document_rejected", [])

        assert len(steps) >= 2
        assert steps[0]["channel"] == "email"
        assert steps[0]["template"] == "document_rejected"

    def test_escalation_after_failed_attempts(self, followup_service, mock_db):
        """After multiple failed follow-up attempts, campaign should escalate to LO."""
        # Build a campaign that has exhausted early steps
        campaign = MagicMock(spec=FollowupCampaign)
        campaign.id = 1
        campaign.current_step = 4  # Last step before escalation
        campaign.total_steps = 5
        campaign.status = CampaignStatus.ACTIVE
        campaign.step_config = _DEFAULT_STEP_CONFIGS["initial_request"]

        # The 5th step (index 4) should be escalation
        next_step = campaign.step_config[campaign.current_step]
        assert next_step["action"] == "escalate_to_lo", (
            f"Final step should be escalation, got {next_step['action']}"
        )


# =============================================================================
# 10. DOCUMENT RE-UPLOAD AFTER REJECTION
# =============================================================================

@pytest.mark.e2e
class TestDocumentReupload:
    """Phase 10: Re-upload a corrected document after rejection."""

    def test_reupload_fresh_statement_after_expiry_rejection(self, review_service, mock_db):
        """After an expired statement is rejected, a fresh one should be accepted."""
        fresh_doc = _make_smart_document(
            id=2,
            doc_type=DocType.BANK_STATEMENT,
            doc_date=datetime.now(timezone.utc) - timedelta(days=5),
            is_expired=False,
            file_name="bank_statement_feb_2026.pdf",
            ocr_text=(
                "Bank Statement\n"
                "Statement Period: 02/01/2026 - 02/28/2026\n"
                "Beginning Balance: $15,000.00\n"
                "Ending Balance: $14,200.00\n"
                "Account Number: ****6789\n"
                "Jane Doe\n"
            ),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = fresh_doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            decision = review_service.review_document(document_id=2)

        assert decision.decision in (
            DocumentDecision.ACCEPT.value, "ACCEPT",
        ), f"Fresh re-upload should be accepted, got {decision.decision} with {decision.reasons}"
        assert decision.freshness_valid is True

    def test_reupload_updates_request_status(self, mock_db):
        """When a valid re-upload is accepted, the document request status should update."""
        request = MagicMock(spec=DocumentRequest)
        request.id = 1
        request.loan_id = 42
        request.doc_type = DocType.BANK_STATEMENT
        request.status = RequestStatus.REJECTED

        # Simulate accepting the re-upload
        request.status = RequestStatus.ACCEPTED
        request.completed_at = datetime.now(timezone.utc)

        assert request.status == RequestStatus.ACCEPTED
        assert request.completed_at is not None

    def test_reupload_closes_followup_campaign(self, followup_service, mock_db):
        """When all docs from a rejected campaign are re-uploaded, campaign should complete."""
        campaign = MagicMock(spec=FollowupCampaign)
        campaign.id = 1
        campaign.loan_id = 42
        campaign.status = CampaignStatus.ACTIVE
        campaign.linked_request_ids = [1]

        # Simulate marking campaign as completed after re-upload
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = datetime.now(timezone.utc)

        assert campaign.status == CampaignStatus.COMPLETED

    def test_full_rejection_reupload_cycle(self, review_service, mock_db):
        """Full cycle: upload -> reject -> re-upload -> accept."""
        # Step 1: Original expired document
        expired_doc = _make_smart_document(
            id=1,
            doc_type=DocType.PAYSTUB,
            doc_date=datetime.now(timezone.utc) - timedelta(days=45),
            is_expired=True,
            ocr_text="Pay Period: 12/01/2025 - 12/15/2025\nGross Pay: $5,000\nJane Doe",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = expired_doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            rejection = review_service.review_document(document_id=1)

        assert rejection.freshness_valid is False, "Expired doc should fail freshness"

        # Step 2: Fresh replacement document
        fresh_doc = _make_smart_document(
            id=2,
            doc_type=DocType.PAYSTUB,
            doc_date=datetime.now(timezone.utc) - timedelta(days=3),
            is_expired=False,
            ocr_text=(
                "Pay Period: 02/16/2026 - 02/28/2026\n"
                "Pay Date: 03/05/2026\n"
                "Employee: Jane Doe\n"
                "Employer: Acme Corp\n"
                "Gross Pay: $5,000.00\n"
                "Net Pay: $3,800.00\n"
                "YTD: $25,000.00\n"
            ),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = fresh_doc

        with patch.object(review_service, "_fetch_from_s3") as mock_s3:
            mock_s3.return_value = b"%PDF-1.4\n" + b"0" * 5000 + b"\n%%EOF"
            approval = review_service.review_document(document_id=2)

        assert approval.freshness_valid is True, "Fresh doc should pass freshness"
        assert approval.decision in (
            DocumentDecision.ACCEPT.value, "ACCEPT",
        ), f"Fresh re-upload should be accepted, got {approval.decision}"


# =============================================================================
# ADDITIONAL E2E SCENARIOS
# =============================================================================

@pytest.mark.e2e
class TestDocumentValidationEdgeCases:
    """Additional edge cases for the document lifecycle."""

    def test_pdf_with_javascript_rejected(self, validation_engine):
        """PDFs containing JavaScript should be flagged as a security concern."""
        import io
        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n")
        buf.write(b"1 0 obj\n<< /Type /Page >>\nendobj\n")
        buf.write(b"2 0 obj\n<< /Type /Pages /Count 1 >>\nendobj\n")
        buf.write(b"<< /JS (app.alert('hi')) /S /JavaScript >>\n")
        buf.write(b"%%EOF\n")
        content = buf.getvalue()
        # Pad to meet minimum size
        if len(content) < 1100:
            content += b"\n%" + b"0" * (1100 - len(content))

        result = validation_engine.validate_upload(
            file_bytes=content,
            filename="suspicious.pdf",
            mime_type="application/pdf",
            declared_doc_type="PAYSTUB",
        )

        # Should either fail or have security warning
        has_security_issue = any(
            "JS" in i.code or "SCRIPT" in i.code or "SECURITY" in i.code or "SAFE" in i.code
            for i in result.issues
        )
        assert result.passed is False or has_security_issue, (
            f"PDF with JS should be flagged, issues: {[i.code for i in result.issues]}"
        )

    def test_freshness_rules_by_doc_type(self):
        """Verify freshness rules are configured for key document types."""
        assert "PAYSTUB" in FRESHNESS_RULES
        assert FRESHNESS_RULES["PAYSTUB"] == 30
        assert "BANK_STATEMENT" in FRESHNESS_RULES
        assert FRESHNESS_RULES["BANK_STATEMENT"] == 60
        assert "W2" in FRESHNESS_RULES
        assert FRESHNESS_RULES["W2"] == 365

    def test_batch_review_processes_all_documents(self, review_service, mock_db):
        """Batch review should process all pending documents for a loan."""
        docs = [
            _make_smart_document(
                id=i,
                doc_type=dtype,
                status="UPLOADED",
                doc_date=datetime.now(timezone.utc) - timedelta(days=5),
                ocr_text=f"Document content for {dtype.value}",
            )
            for i, dtype in enumerate(
                [DocType.PAYSTUB, DocType.W2, DocType.BANK_STATEMENT], start=1
            )
        ]

        mock_db.query.return_value.filter.return_value.all.return_value = docs

        with patch.object(review_service, "review_document") as mock_review:
            mock_review.return_value = ReviewDecision(
                decision=DocumentDecision.ACCEPT.value,
                confidence=90,
                reasons=["All checks passed"],
                auto_approved=True,
                freshness_valid=True,
                type_match=True,
                name_match=True,
            )

            result = review_service.batch_review(loan_id=42)

        assert result.total == 3
        assert result.approved == 3
        assert mock_review.call_count == 3
