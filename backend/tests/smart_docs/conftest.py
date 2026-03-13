"""
Smart Docs V2 — Shared Test Fixtures

Provides database mocks, user fixtures, sample mortgage data, and service
mocks for all Smart Docs test modules. Every fixture is designed to be
realistic (matching actual column names and types from the real models)
and composable (combine freely across test categories).

Fixture families:
    mock_db_*       — SQLAlchemy session mocks
    mock_*_user     — User role fixtures (LO, processor, underwriter, admin, borrower, other-org)
    sample_*        — Realistic mortgage domain data
    mock_*_service  — Service-layer mocks with pre-wired return values

Usage:
    # In any test file under tests/smart_docs/
    def test_something(mock_db_session, mock_lo_user, sample_loan):
        ...
"""

import hashlib
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session for unit tests.

    Provides query(), add(), commit(), rollback(), close(), execute(),
    refresh(), and flush() — the methods used across Smart Docs route
    handlers and services.
    """
    session = MagicMock()

    # query() returns a chainable mock (filter, filter_by, first, all, etc.)
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.filter_by.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.offset.return_value = query_chain
    query_chain.join.return_value = query_chain
    query_chain.outerjoin.return_value = query_chain
    query_chain.options.return_value = query_chain
    query_chain.first.return_value = None
    query_chain.all.return_value = []
    query_chain.count.return_value = 0
    query_chain.one_or_none.return_value = None
    query_chain.scalar.return_value = 0
    session.query.return_value = query_chain

    # execute() returns a mock result proxy
    execute_result = MagicMock()
    execute_result.fetchall.return_value = []
    execute_result.fetchone.return_value = None
    execute_result.first.return_value = None
    execute_result.rowcount = 0
    execute_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute.return_value = execute_result

    # Track objects added to the session for assertion in tests
    session._added_objects = []
    original_add = session.add
    def _tracking_add(obj):
        session._added_objects.append(obj)
    session.add.side_effect = _tracking_add

    session._flushed = False
    def _tracking_flush(*args, **kwargs):
        session._flushed = True
    session.flush.side_effect = _tracking_flush

    session._committed = False
    def _tracking_commit():
        session._committed = True
    session.commit.side_effect = _tracking_commit

    return session


@pytest.fixture
def mock_db_with_data(mock_db_session, sample_loan, sample_lead, mock_lo_user):
    """Mock session pre-loaded with sample loan, lead, user, and org data.

    Configure the execute() mock so that common tenant verification
    queries return results consistent with the sample data.
    """
    session = mock_db_session

    # When routes call _verify_loan_tenant via:
    #   db.execute(sa_text("SELECT organization_id FROM loans WHERE id = :id"), ...)
    # return the sample org_id (1)
    def _execute_side_effect(stmt, params=None):
        query_str = str(stmt) if not isinstance(stmt, str) else stmt
        result = MagicMock()

        if "organization_id" in query_str and "loans" in query_str:
            # Tenant check: return org_id = 1
            row_mock = MagicMock()
            row_mock.__getitem__ = lambda self, idx: sample_loan["organization_id"]
            result.first.return_value = row_mock
        elif "organizations" in query_str and "is_active" in query_str:
            # Cron helper: _get_active_organizations()
            result.fetchall.return_value = [(1,), (2,)]
        else:
            result.first.return_value = None
            result.fetchall.return_value = []

        result.fetchone.return_value = result.first.return_value
        result.rowcount = 1 if result.first.return_value else 0
        return result

    session.execute.side_effect = _execute_side_effect
    return session


# =============================================================================
# USER FIXTURES
# =============================================================================

class _MockUser:
    """Lightweight mock user matching the attributes routes read via getattr()."""

    def __init__(
        self,
        id: int = 1,
        email: str = "lo@example.com",
        organization_id: int = 1,
        role: str = "loan_officer",
        permission_role: str = "loan_officer",
        is_active: bool = True,
        first_name: str = "Jane",
        last_name: str = "LoanOfficer",
        nmls_number: str = "MLO123456",
        **kwargs,
    ):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.role = role
        self.permission_role = permission_role
        self.is_active = is_active
        self.first_name = first_name
        self.last_name = last_name
        self.nmls_number = nmls_number
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<MockUser id={self.id} role={self.role} org={self.organization_id}>"


@pytest.fixture
def mock_lo_user():
    """Mock loan officer user with org_id=1."""
    return _MockUser(
        id=10,
        email="jane.lo@mortgage.com",
        organization_id=1,
        role="loan_officer",
        permission_role="loan_officer",
        first_name="Jane",
        last_name="Smith",
        nmls_number="MLO987654",
    )


@pytest.fixture
def mock_processor_user():
    """Mock processor user with org_id=1."""
    return _MockUser(
        id=20,
        email="bob.processor@mortgage.com",
        organization_id=1,
        role="processor",
        permission_role="processor",
        first_name="Bob",
        last_name="Processor",
        nmls_number="",
    )


@pytest.fixture
def mock_underwriter_user():
    """Mock underwriter user with org_id=1."""
    return _MockUser(
        id=30,
        email="carol.uw@mortgage.com",
        organization_id=1,
        role="underwriter",
        permission_role="underwriter",
        first_name="Carol",
        last_name="Underwriter",
        nmls_number="",
    )


@pytest.fixture
def mock_admin_user():
    """Mock platform admin user — has cross-org access."""
    return _MockUser(
        id=99,
        email="admin@perenniaai.com",
        organization_id=1,
        role="admin",
        permission_role="admin",
        first_name="Platform",
        last_name="Admin",
    )


@pytest.fixture
def mock_borrower_portal_user():
    """Mock borrower portal session (JWT claims extracted by portal_auth_service).

    Portal users are NOT _MockUser instances — they are dicts decoded from
    the JWT by get_current_portal_user().
    """
    return {
        "loan_id": 42,
        "borrower_email": "borrower@gmail.com",
        "org_id": 1,
        "scope": "read_write",
        "iss": "perennia-portal",
        "exp": (datetime.now(timezone.utc) + timedelta(hours=72)).timestamp(),
    }


@pytest.fixture
def mock_other_org_user():
    """Mock user from org_id=2 — used for tenant isolation tests.

    Any attempt by this user to access org_id=1 data should be blocked.
    """
    return _MockUser(
        id=200,
        email="rival@otherorg.com",
        organization_id=2,
        role="loan_officer",
        permission_role="loan_officer",
        first_name="Rival",
        last_name="OtherOrg",
    )


# =============================================================================
# DATA FIXTURES — LOAN & LEAD
# =============================================================================

@pytest.fixture
def sample_loan():
    """Sample loan with realistic columns matching database/models/lead_loan.py.

    Includes dates used for TRID compliance checks, document expiration,
    and pipeline metrics.
    """
    now = datetime.now(timezone.utc)
    return {
        "id": 42,
        "loan_number": "2026-005678",
        "organization_id": 1,
        "loan_officer_id": 10,
        "borrower_name": "Maria Gonzalez",
        "borrower_email": "maria@example.com",
        "borrower_phone": "+12125551234",
        "co_borrower_name": "Carlos Gonzalez",
        "property_address": "456 Oak Ave, Dallas, TX 75201",
        "property_type": "single_family",
        "amount": Decimal("485000.00"),
        "rate": Decimal("6.625"),
        "loan_type": "conventional",
        "occupancy_type": "primary",
        "stage": "PROCESSING",
        "stage_changed_at": now - timedelta(days=3),
        "application_date": now - timedelta(days=14),
        "initial_disclosures_sent_date": now - timedelta(days=12),
        "initial_disclosures_signed_date": now - timedelta(days=11),
        "loan_estimate_sent_date": now - timedelta(days=12),
        "cd_sent_to_borrower_date": None,
        "cd_acknowledged_date": None,
        "closing_date": now + timedelta(days=21),
        "lock_expiration_date": now + timedelta(days=30),
        "funded_date": None,
        "credit_docs_expire_date": now + timedelta(days=90),
        "appraisal_docs_expire_date": now + timedelta(days=120),
        "appraisal_ordered_date": now - timedelta(days=5),
        "appraisal_scheduled_date": now - timedelta(days=2),
        "appraisal_completed_date": None,
        "appraisal_received_date": None,
        "appraisal_value": None,
        "title_ordered_date": now - timedelta(days=4),
        "title_received_date": None,
        "insurance_ordered_date": None,
        "insurance_received_date": None,
        "created_at": now - timedelta(days=14),
        "updated_at": now,
    }


@pytest.fixture
def sample_lead():
    """Sample lead/borrower matching database/models/lead_loan.py Lead columns."""
    now = datetime.now(timezone.utc)
    return {
        "id": 100,
        "first_name": "Maria",
        "last_name": "Gonzalez",
        "email": "maria@example.com",
        "phone": "+12125551234",
        "stage": "Application",
        "source": "website",
        "owner_id": 10,
        "organization_id": 1,
        "ai_score": 78,
        "last_contact": now - timedelta(days=1),
        "loan_purpose": "purchase",
        "property_type": "single_family",
        "loan_amount": Decimal("485000.00"),
        "credit_score": 740,
        "preapproval_amount": Decimal("500000.00"),
        "preferred_communication": "email",
        "created_at": now - timedelta(days=20),
    }


# =============================================================================
# DATA FIXTURES — DOCUMENT EXTRACTION RESULTS
# =============================================================================

@pytest.fixture
def sample_paystub_data():
    """Extracted paystub data for income calculation tests.

    Matches the JSON structure stored in SmartDocument.extracted_dates,
    extracted_names, and extracted_amount fields.
    """
    return {
        "employer_name": "Acme Financial Corp",
        "employee_name": "Maria Gonzalez",
        "pay_date": "2026-02-28",
        "period_start": "2026-02-16",
        "period_end": "2026-02-28",
        "pay_frequency": "BIWEEKLY",
        "gross_pay": Decimal("4230.77"),
        "net_pay": Decimal("3125.42"),
        "ytd_gross": Decimal("16923.08"),
        "ytd_net": Decimal("12501.68"),
        "federal_tax": Decimal("634.62"),
        "state_tax": Decimal("211.54"),
        "social_security": Decimal("262.31"),
        "medicare": Decimal("61.35"),
        "retirement_401k": Decimal("211.54"),
        "health_insurance": Decimal("185.00"),
        "regular_hours": Decimal("80.00"),
        "overtime_hours": Decimal("0.00"),
        "regular_rate": Decimal("52.88"),
    }


@pytest.fixture
def sample_w2_data():
    """Two years of W-2 data for year-over-year trending analysis."""
    return {
        "current_year": {
            "tax_year": 2025,
            "employer_name": "Acme Financial Corp",
            "employer_ein": "12-3456789",
            "employee_name": "Maria Gonzalez",
            "employee_ssn_last4": "6789",
            "wages_tips_compensation": Decimal("110000.00"),
            "federal_tax_withheld": Decimal("16500.00"),
            "social_security_wages": Decimal("110000.00"),
            "social_security_tax": Decimal("6820.00"),
            "medicare_wages": Decimal("110000.00"),
            "medicare_tax": Decimal("1595.00"),
            "state": "TX",
            "state_wages": Decimal("110000.00"),
            "state_tax_withheld": Decimal("0.00"),
        },
        "prior_year": {
            "tax_year": 2024,
            "employer_name": "Acme Financial Corp",
            "employer_ein": "12-3456789",
            "employee_name": "Maria Gonzalez",
            "employee_ssn_last4": "6789",
            "wages_tips_compensation": Decimal("105000.00"),
            "federal_tax_withheld": Decimal("15750.00"),
            "social_security_wages": Decimal("105000.00"),
            "social_security_tax": Decimal("6510.00"),
            "medicare_wages": Decimal("105000.00"),
            "medicare_tax": Decimal("1522.50"),
            "state": "TX",
            "state_wages": Decimal("105000.00"),
            "state_tax_withheld": Decimal("0.00"),
        },
    }


@pytest.fixture
def sample_tax_return_data():
    """Schedule C self-employment data for complex income calculation."""
    return {
        "tax_year": 2025,
        "filing_status": "married_filing_jointly",
        "total_income": Decimal("165000.00"),
        "agi": Decimal("152000.00"),
        "schedule_c": {
            "business_name": "Gonzalez Consulting LLC",
            "ein": "98-7654321",
            "gross_receipts": Decimal("210000.00"),
            "cost_of_goods_sold": Decimal("12000.00"),
            "gross_profit": Decimal("198000.00"),
            "total_expenses": Decimal("53000.00"),
            "net_profit": Decimal("145000.00"),
            "depreciation": Decimal("8500.00"),
            "vehicle_expense": Decimal("4200.00"),
            "home_office_deduction": Decimal("3600.00"),
            "meals_deduction": Decimal("2100.00"),
        },
        "self_employment_tax": Decimal("20493.00"),
    }


@pytest.fixture
def sample_bank_statement_data():
    """Bank statement extracted data for asset verification."""
    now = datetime.now(timezone.utc)
    return {
        "institution_name": "First National Bank",
        "account_holder": "Maria Gonzalez",
        "account_number_last4": "4321",
        "account_type": "checking",
        "statement_period_start": (now - timedelta(days=30)).strftime("%Y-%m-%d"),
        "statement_period_end": now.strftime("%Y-%m-%d"),
        "beginning_balance": Decimal("24567.89"),
        "ending_balance": Decimal("31245.67"),
        "total_deposits": Decimal("12450.00"),
        "total_withdrawals": Decimal("5772.22"),
        "average_daily_balance": Decimal("27890.45"),
        "largest_deposit": Decimal("4230.77"),
        "nsf_count": 0,
        "large_deposits": [
            {
                "date": (now - timedelta(days=15)).strftime("%Y-%m-%d"),
                "amount": Decimal("4230.77"),
                "description": "ACME FINANCIAL PAYROLL",
            },
            {
                "date": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
                "amount": Decimal("4230.77"),
                "description": "ACME FINANCIAL PAYROLL",
            },
        ],
    }


# =============================================================================
# SERVICE MOCKS
# =============================================================================

@pytest.fixture
def mock_ai_service():
    """Mock AI classification/extraction service.

    Simulates the Anthropic API responses used by ai_classifier_service.py
    and ai_review_service.py. Returns realistic classification results
    without making actual API calls.
    """
    service = MagicMock()

    # Classification result
    service.classify_document.return_value = {
        "doc_type": "PAYSTUB",
        "confidence": 0.94,
        "detected_fields": {
            "employer_name": "Acme Financial Corp",
            "pay_date": "2026-02-28",
        },
        "model_version": "claude-sonnet-4-20250514",
    }

    # Review decision
    service.review_document.return_value = {
        "decision": "ACCEPT",
        "confidence": 0.91,
        "reasons": ["Document is clear and legible", "Dates are within freshness window"],
        "issues": [],
    }

    # OCR extraction
    service.extract_text.return_value = {
        "text": "ACME FINANCIAL CORP\nPay Date: 02/28/2026\nGross Pay: $4,230.77",
        "confidence": 0.95,
        "page_count": 1,
    }

    return service


@pytest.fixture
def mock_s3_service():
    """Mock S3 storage service matching s3_storage_service.py interface.

    Provides upload_file(), download_file(), generate_presigned_url(),
    and delete_file() with realistic return values.
    """
    service = MagicMock()

    # Upload returns S3 key
    service.upload_file.return_value = {
        "key": "orgs/1/loans/42/docs/abc123-paystub.pdf",
        "bucket": "perennia-smart-docs",
        "version_id": "v1_abc123",
        "etag": '"d41d8cd98f00b204e9800998ecf8427e"',
    }

    # Download returns bytes
    service.download_file.return_value = b"%PDF-1.4 mock content"

    # Presigned URL
    service.generate_presigned_url.return_value = (
        "https://perennia-smart-docs.s3.amazonaws.com/orgs/1/loans/42/docs/"
        "abc123-paystub.pdf?X-Amz-Signature=mock"
    )

    # Delete
    service.delete_file.return_value = True

    # File existence check
    service.file_exists.return_value = True

    return service


@pytest.fixture
def mock_email_service():
    """Mock email sending service for document reminder and notification tests."""
    service = MagicMock()

    service.send_email = AsyncMock(return_value={
        "message_id": f"msg-{uuid.uuid4().hex[:8]}",
        "status": "sent",
    })

    service.send_template_email = AsyncMock(return_value={
        "message_id": f"msg-{uuid.uuid4().hex[:8]}",
        "status": "sent",
    })

    service.send_reminder = AsyncMock(return_value={
        "message_id": f"msg-{uuid.uuid4().hex[:8]}",
        "status": "sent",
        "channel": "email",
    })

    return service


@pytest.fixture
def mock_sms_service():
    """Mock SMS service with TCPA consent checks baked in.

    The real tcpa_compliance_service.py validates consent before every send.
    This mock defaults to consent-granted; tests that need to verify TCPA
    blocking should override send_sms.side_effect.
    """
    service = MagicMock()

    service.send_sms = AsyncMock(return_value={
        "message_id": f"sms-{uuid.uuid4().hex[:8]}",
        "status": "delivered",
        "tcpa_validated": True,
    })

    service.check_consent.return_value = {
        "has_consent": True,
        "consent_date": datetime.now(timezone.utc) - timedelta(days=5),
        "consent_type": "express_written",
    }

    service.check_dnc.return_value = {
        "is_on_dnc": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    return service


# =============================================================================
# DOCUMENT MODEL FIXTURES
# =============================================================================

@pytest.fixture
def sample_smart_document(sample_loan):
    """A SmartDocument ORM-like mock matching models/smart_docs_models.py."""
    now = datetime.now(timezone.utc)
    doc = MagicMock()
    doc.id = 1001
    doc.request_id = 501
    doc.loan_id = sample_loan["id"]
    doc.borrower_id = 200
    doc.file_name = "paystub_feb_2026.pdf"
    doc.original_filename = "Paystub_Feb2026.pdf"
    doc.mime_type = "application/pdf"
    doc.file_size = 245_760  # ~240 KB
    doc.storage_key = "orgs/1/loans/42/docs/paystub_feb_2026.pdf"
    doc.page_count = 1
    doc.uploaded_at = now - timedelta(hours=2)
    doc.doc_type = "PAYSTUB"
    doc.detected_doc_type = "PAYSTUB"
    doc.detected_is_screenshot = False
    doc.screenshot_confidence = 0.02
    doc.screenshot_reasons = None
    doc.extracted_dates = {"payDate": "2026-02-28", "periodEnd": "2026-02-28"}
    doc.extracted_names = {"employee": "Maria Gonzalez", "employer": "Acme Financial Corp"}
    doc.extracted_employer = "Acme Financial Corp"
    doc.extracted_account_number = None
    doc.extracted_amount = Decimal("4230.77")
    doc.extraction_confidence = 0.94
    doc.ocr_text = "ACME FINANCIAL CORP\nPay Date: 02/28/2026\nGross Pay: $4,230.77"
    doc.doc_date = now - timedelta(days=1)
    doc.doc_expires_at = now + timedelta(days=29)
    doc.is_expired = False
    doc.days_until_expiration = 29
    doc.status = "APPROVED"
    doc.decision = "ACCEPT"
    doc.decision_reasons = ["Clear document", "Within freshness window"]
    doc.rejection_reason = None
    doc.rejection_category = None
    doc.fix_instructions = None
    doc.reviewed_at = now - timedelta(hours=1)
    doc.reviewed_by = "SYSTEM"
    doc.upload_source = "WEB"
    doc.user_agent = "Mozilla/5.0"
    doc.ip_address = "10.0.0.1"
    doc.display_name = "February 2026 Paystub"
    doc.assigned_owner = "BORROWER"
    doc.created_at = now - timedelta(hours=2)
    doc.updated_at = now - timedelta(hours=1)
    # PII encryption columns
    doc.ocr_text_encrypted = None
    doc.extracted_account_number_encrypted = None
    doc.ip_address_encrypted = None
    doc.pii_encrypted_at = None
    return doc


@pytest.fixture
def sample_document_request(sample_loan):
    """A DocumentRequest ORM-like mock matching models/smart_docs_models.py."""
    now = datetime.now(timezone.utc)
    req = MagicMock()
    req.id = 501
    req.loan_id = sample_loan["id"]
    req.borrower_id = 200
    req.doc_type = "PAYSTUB"
    req.title = "Most Recent Paystub"
    req.description = "Please provide your most recent paystub (within 30 days)"
    req.instructions = "Upload a clear scan or photo — no screenshots of banking apps."
    req.required_count = 1
    req.applies_to = "BORROWER"
    req.priority = "NORMAL"
    req.freshness_days = 30
    req.auto_renew = True
    req.next_expected_available_at = now + timedelta(days=14)
    req.payroll_frequency = "BIWEEKLY"
    req.status = "OPEN"
    req.due_date = now + timedelta(days=3)
    req.completed_at = None
    req.sla_due_at = now + timedelta(days=3)
    req.is_active = True
    req.superseded_by = None
    req.created_at = now - timedelta(days=1)
    req.updated_at = now - timedelta(days=1)
    return req


# =============================================================================
# HELPERS FOR TEST ASSERTIONS
# =============================================================================

@pytest.fixture
def compute_file_hash():
    """Helper to compute SHA-256 hash of file content (matches upload_pipeline.py)."""
    def _hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()
    return _hash


@pytest.fixture
def make_oversized_file():
    """Factory to generate a file of a specified size in bytes."""
    def _make(size_bytes: int, *, content_byte: int = 0x00) -> bytes:
        return bytes([content_byte]) * size_bytes
    return _make


@pytest.fixture
def make_pdf_bytes():
    """Factory to generate minimal valid PDF content."""
    def _make(text: str = "Test Document") -> bytes:
        # Minimal valid PDF that passes magic-byte checks
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
            b"startxref\n196\n%%EOF"
        )
    return _make
