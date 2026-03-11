"""
Test Smart Docs Review Routes

Integration tests for the AI document review API endpoints at
/api/v1/smart-docs/doc-review/*.

Covers:
1.  POST ai-review/{document_id} - Submit document for AI review
2.  GET queue - Review queue (pending reviews)
3.  GET queue/stats - Review queue statistics
4.  POST queue/{document_id}/claim - Claim document for review
5.  POST queue/{document_id}/release - Release claimed document
6.  POST validate-upload - Pre-upload file validation
7.  GET validation-rules/{doc_type} - Validation rules for a doc type
8.  POST cross-validate/{loan_id} - Cross-document validation
9.  GET document/{document_id}/review-history - Review history
10. POST auto-review-settings - Update auto-review settings
11. GET auto-review-settings - Get auto-review settings
12. GET stats - Review statistics / quality metrics dashboard
13. POST document/{document_id}/ai-extract-and-review - Combined extract + review
14. GET loan/{loan_id}/completeness - Loan document completeness check
15. Review queue ordering by priority
16. Tenant isolation on review endpoints
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import List, Optional

from fastapi.testclient import TestClient


# =============================================================================
# Base URL for all review routes
# =============================================================================

BASE = "/api/v1/smart-docs/doc-review"


# =============================================================================
# Mock helpers
# =============================================================================

class MockUser:
    """Mock user with configurable attributes."""

    def __init__(
        self,
        id=1,
        email="lo@example.com",
        organization_id=100,
        permission_role="loan_officer",
        first_name="Jane",
        last_name="Doe",
        is_active=True,
    ):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.permission_role = permission_role
        self.first_name = first_name
        self.last_name = last_name
        self.is_active = is_active


class MockAdminUser(MockUser):
    def __init__(self, **kwargs):
        defaults = dict(id=2, email="admin@example.com", permission_role="admin")
        defaults.update(kwargs)
        super().__init__(**defaults)


class MockOtherOrgUser(MockUser):
    """User from a different organization for tenant isolation tests."""

    def __init__(self, **kwargs):
        defaults = dict(id=99, email="other@other-org.com", organization_id=999)
        defaults.update(kwargs)
        super().__init__(**defaults)


@dataclass
class MockReviewResult:
    """Mimics the result object returned by ai_review_service.review_document()."""
    decision: str = "ACCEPT"
    confidence: int = 92
    reasons: List[str] = None
    quality_score: int = 85
    completeness_score: int = 90
    fix_instructions: Optional[str] = None
    auto_approved: bool = True
    needs_human_review: bool = False
    review_priority: str = "NORMAL"
    freshness_valid: bool = True
    type_match: bool = True
    name_match: bool = True

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = ["Document passed all quality checks"]


@dataclass
class MockBatchResult:
    """Mimics the result object returned by ai_review_service.batch_review()."""
    total: int = 3
    approved: int = 2
    rejected: int = 0
    needs_review: int = 1
    results: List[dict] = None

    def __post_init__(self):
        if self.results is None:
            self.results = [
                {"document_id": 10, "decision": "ACCEPT"},
                {"document_id": 11, "decision": "ACCEPT"},
                {"document_id": 12, "decision": "NEEDS_REVIEW"},
            ]


@dataclass
class MockValidationResult:
    """Mimics the result from document_validation_engine.validate_upload()."""
    is_valid: bool = True
    score: int = 95
    issues: List[dict] = None
    passed_rules: List[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.passed_rules is None:
            self.passed_rules = ["file_type", "file_size", "no_malware"]

    def to_dict(self):
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "issues": self.issues,
            "passed_rules": self.passed_rules,
        }


def _make_smart_document(
    id=1,
    loan_id=10,
    borrower_id=5,
    file_name="paystub.pdf",
    mime_type="application/pdf",
    file_size=102400,
    storage_key="org-100/loan-10/paystub.pdf",
    doc_type=None,
    status="UPLOADED",
    decision=None,
    reviewed_by=None,
    reviewed_at=None,
    rejection_reason=None,
    rejection_category=None,
    screenshot_confidence=None,
    is_expired=False,
    detected_is_screenshot=False,
    request_id=None,
    uploaded_at=None,
    updated_at=None,
    ocr_text=None,
):
    """Create a mock SmartDocument ORM object."""
    doc = MagicMock()
    doc.id = id
    doc.loan_id = loan_id
    doc.borrower_id = borrower_id
    doc.file_name = file_name
    doc.original_filename = file_name
    doc.mime_type = mime_type
    doc.file_size = file_size
    doc.storage_key = storage_key
    doc.page_count = 2
    doc.uploaded_at = uploaded_at or datetime.utcnow()
    doc.doc_type = doc_type
    doc.detected_doc_type = None
    doc.detected_is_screenshot = detected_is_screenshot
    doc.screenshot_confidence = screenshot_confidence
    doc.screenshot_reasons = None
    doc.status = status
    doc.decision = decision
    doc.rejection_reason = rejection_reason
    doc.rejection_category = rejection_category
    doc.fix_instructions = None
    doc.reviewed_at = reviewed_at
    doc.reviewed_by = reviewed_by
    doc.is_expired = is_expired
    doc.request_id = request_id
    doc.updated_at = updated_at or datetime.utcnow()
    doc.ocr_text = ocr_text
    return doc


def _setup_app_overrides(app, db_session, user):
    """Wire up dependency overrides for db + auth on the FastAPI app."""
    from database import get_db
    from auth.dependencies import get_current_user as auth_dep_gcu

    # Also import from main to cover both dependency references
    try:
        from main import get_current_user as main_gcu, get_current_user_flexible as main_gcuf
    except ImportError:
        main_gcu = None
        main_gcuf = None

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_dep_gcu] = override_auth
    if main_gcu:
        app.dependency_overrides[main_gcu] = override_auth
    if main_gcuf:
        app.dependency_overrides[main_gcuf] = override_auth


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def lo_user():
    return MockUser()


@pytest.fixture
def admin_user():
    return MockAdminUser()


@pytest.fixture
def other_org_user():
    return MockOtherOrgUser()


@pytest.fixture
def mock_db():
    """A lightweight mock db session for tests that don't need real tables."""
    db = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def review_client(mock_db, lo_user):
    """TestClient with LO user auth and mock DB wired up."""
    from main import app

    _setup_app_overrides(app, mock_db, lo_user)
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def admin_review_client(mock_db, admin_user):
    """TestClient with admin user auth."""
    from main import app

    _setup_app_overrides(app, mock_db, admin_user)
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def other_org_client(mock_db, other_org_user):
    """TestClient with a user from a different org."""
    from main import app

    _setup_app_overrides(app, mock_db, other_org_user)
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


# =============================================================================
# 1. POST /doc-review/ai-review/{document_id}
# =============================================================================

@pytest.mark.unit
class TestAIReviewDocument:
    """POST /doc-review/ai-review/{document_id}"""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_ai_review_returns_decision(self, mock_get_svc, mock_verify, review_client):
        """AI review returns decision, confidence, scores, and flags."""
        mock_verify.return_value = _make_smart_document(id=1)
        mock_svc = MagicMock()
        mock_svc.review_document.return_value = MockReviewResult()
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/ai-review/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == 1
        assert data["decision"] == "ACCEPT"
        assert data["confidence"] == 92
        assert data["quality_score"] == 85
        assert data["completeness_score"] == 90
        assert data["auto_approved"] is True
        assert data["freshness_valid"] is True
        assert data["type_match"] is True
        assert data["name_match"] is True

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_ai_review_reject_with_instructions(self, mock_get_svc, mock_verify, review_client):
        """Rejected documents include fix_instructions."""
        mock_verify.return_value = _make_smart_document(id=2)
        mock_svc = MagicMock()
        mock_svc.review_document.return_value = MockReviewResult(
            decision="REJECT",
            confidence=88,
            reasons=["Screenshot detected"],
            quality_score=20,
            fix_instructions="Re-upload a direct download from your bank portal",
            auto_approved=False,
            needs_human_review=False,
        )
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/ai-review/2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "REJECT"
        assert data["fix_instructions"] is not None
        assert "Re-upload" in data["fix_instructions"]

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_ai_review_document_not_found(self, mock_verify, review_client):
        """Returns 404 when document does not exist."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = review_client.post(f"{BASE}/ai-review/9999")
        assert resp.status_code == 404


# =============================================================================
# 2. GET /doc-review/queue
# =============================================================================

@pytest.mark.unit
class TestReviewQueue:
    """GET /doc-review/queue"""

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_get_review_queue_returns_items(self, mock_get_svc, review_client):
        """Queue endpoint returns paginated items with priority and doc_type."""
        mock_svc = MagicMock()
        mock_svc.review_queue.return_value = [
            {"document_id": 1, "priority": "CRITICAL", "doc_type": "PAYSTUB", "file_name": "pay.pdf"},
            {"document_id": 2, "priority": "HIGH", "doc_type": "W2", "file_name": "w2.pdf"},
            {"document_id": 3, "priority": "NORMAL", "doc_type": "BANK_STATEMENT", "file_name": "bank.pdf"},
        ]
        mock_get_svc.return_value = mock_svc

        resp = review_client.get(f"{BASE}/queue")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_queue_filter_by_priority(self, mock_get_svc, review_client):
        """Queue supports priority filter."""
        mock_svc = MagicMock()
        mock_svc.review_queue.return_value = [
            {"document_id": 1, "priority": "CRITICAL", "doc_type": "PAYSTUB"},
            {"document_id": 2, "priority": "HIGH", "doc_type": "W2"},
            {"document_id": 3, "priority": "NORMAL", "doc_type": "BANK_STATEMENT"},
        ]
        mock_get_svc.return_value = mock_svc

        resp = review_client.get(f"{BASE}/queue", params={"priority": "CRITICAL"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["priority"] == "CRITICAL"

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_queue_filter_by_doc_type(self, mock_get_svc, review_client):
        """Queue supports doc_type filter."""
        mock_svc = MagicMock()
        mock_svc.review_queue.return_value = [
            {"document_id": 1, "priority": "NORMAL", "doc_type": "PAYSTUB"},
            {"document_id": 2, "priority": "NORMAL", "doc_type": "W2"},
        ]
        mock_get_svc.return_value = mock_svc

        resp = review_client.get(f"{BASE}/queue", params={"doc_type": "W2"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["doc_type"] == "W2"

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_queue_pagination(self, mock_get_svc, review_client):
        """Queue supports offset and limit."""
        items = [{"document_id": i, "priority": "NORMAL", "doc_type": "PAYSTUB"} for i in range(10)]
        mock_svc = MagicMock()
        mock_svc.review_queue.return_value = items
        mock_get_svc.return_value = mock_svc

        resp = review_client.get(f"{BASE}/queue", params={"offset": 3, "limit": 2})

        assert resp.status_code == 200
        data = resp.json()
        assert data["offset"] == 3
        assert data["limit"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["document_id"] == 3


# =============================================================================
# 3. GET /doc-review/queue/stats  (review metrics / stats)
# =============================================================================

@pytest.mark.unit
class TestQueueStats:
    """GET /doc-review/queue/stats"""

    def test_queue_stats_returns_breakdown(self, review_client, mock_db):
        """Queue stats returns priority breakdown, SLA compliance, and avg hours."""
        # Mock the three SQL queries the endpoint issues
        stats_row = MagicMock()
        stats_row.__getitem__ = lambda self, i: [12, 2, 3, 5.5][i]

        by_type_rows = [
            MagicMock(__getitem__=lambda self, i, vals=("PAYSTUB", 5): vals[i]),
            MagicMock(__getitem__=lambda self, i, vals=("W2", 4): vals[i]),
        ]

        sla_row = MagicMock()
        sla_row.__getitem__ = lambda self, i: [50, 45][i]

        execute_results = iter([
            MagicMock(fetchone=MagicMock(return_value=stats_row)),
            MagicMock(fetchall=MagicMock(return_value=by_type_rows)),
            MagicMock(fetchone=MagicMock(return_value=sla_row)),
        ])
        mock_db.execute = MagicMock(side_effect=lambda *a, **kw: next(execute_results))

        resp = review_client.get(f"{BASE}/queue/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_in_queue"] == 12
        assert data["by_priority"]["critical"] == 2
        assert data["by_priority"]["high"] == 3
        assert data["by_priority"]["normal"] == 7  # 12 - 2 - 3
        assert data["avg_hours_in_queue"] == 5.5
        assert data["sla_compliance"]["total_reviewed_30d"] == 50
        assert data["sla_compliance"]["within_sla"] == 45
        assert data["sla_compliance"]["compliance_pct"] == 90.0


# =============================================================================
# 4. POST /doc-review/queue/{document_id}/claim
# =============================================================================

@pytest.mark.unit
class TestClaimDocument:
    """POST /doc-review/queue/{document_id}/claim"""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_claim_document_success(self, mock_verify, review_client, mock_db):
        """Claiming an unclaimed document succeeds and returns details."""
        doc = _make_smart_document(id=5, status="UPLOADED", reviewed_by=None)
        doc.doc_type = MagicMock()
        doc.doc_type.value = "PAYSTUB"
        doc.decision = None
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/claim")

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == 5
        assert data["claimed_by"] == "Jane Doe"
        assert data["status"] == "NEEDS_REVIEW"
        mock_db.commit.assert_called()

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_claim_already_claimed_by_other_returns_409(self, mock_verify, review_client):
        """Claiming a document already claimed by another user returns 409."""
        doc = _make_smart_document(id=5, status="UPLOADED", reviewed_by="42")
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/claim")

        assert resp.status_code == 409
        assert "already claimed" in resp.json()["detail"].lower()

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_claim_own_document_succeeds(self, mock_verify, review_client, mock_db):
        """Re-claiming a document already claimed by the same user succeeds."""
        doc = _make_smart_document(id=5, status="NEEDS_REVIEW", reviewed_by="1")
        doc.doc_type = MagicMock()
        doc.doc_type.value = "W2"
        doc.decision = None
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/claim")

        assert resp.status_code == 200


# =============================================================================
# 5. POST /doc-review/queue/{document_id}/release
# =============================================================================

@pytest.mark.unit
class TestReleaseDocument:
    """POST /doc-review/queue/{document_id}/release"""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_release_claimed_document(self, mock_verify, review_client, mock_db):
        """Releasing a claimed document returns it to queue."""
        doc = _make_smart_document(id=5, status="NEEDS_REVIEW", reviewed_by="1")
        doc.decision = None
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/release")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UPLOADED"
        assert data["previous_reviewer"] == "1"
        mock_db.commit.assert_called()

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_release_by_non_claimer_returns_403(self, mock_verify, review_client):
        """Non-claimer non-admin cannot release a document."""
        doc = _make_smart_document(id=5, status="NEEDS_REVIEW", reviewed_by="42")
        doc.decision = None
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/release")

        assert resp.status_code == 403

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_release_decided_document_returns_400(self, mock_verify, review_client):
        """Cannot release a document that has already been decided."""
        from models.smart_docs_models import DocumentDecision

        doc = _make_smart_document(id=5, status="APPROVED", reviewed_by="1")
        doc.decision = DocumentDecision.ACCEPT
        mock_verify.return_value = doc

        resp = review_client.post(f"{BASE}/queue/5/release")

        assert resp.status_code == 400

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_admin_can_release_others_claim(self, mock_verify, admin_review_client, mock_db):
        """Admin can release any claimed document."""
        doc = _make_smart_document(id=5, status="NEEDS_REVIEW", reviewed_by="42")
        doc.decision = None
        mock_verify.return_value = doc

        resp = admin_review_client.post(f"{BASE}/queue/5/release")

        assert resp.status_code == 200
        mock_db.commit.assert_called()


# =============================================================================
# 6. POST /doc-review/validate-upload
# =============================================================================

@pytest.mark.unit
class TestValidateUpload:
    """POST /doc-review/validate-upload"""

    @patch("services.smart_docs.document_validation_engine.get_document_validation_engine")
    def test_validate_upload_valid_file(self, mock_get_engine, review_client):
        """Valid file returns is_valid=True with passed rules."""
        mock_engine = MagicMock()
        mock_engine.validate_upload.return_value = MockValidationResult()
        mock_get_engine.return_value = mock_engine

        resp = review_client.post(
            f"{BASE}/validate-upload",
            files={"file": ("paystub.pdf", b"fake-pdf-content", "application/pdf")},
            data={"doc_type": "PAYSTUB"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["score"] == 95
        assert "file_type" in data["passed_rules"]

    @patch("services.smart_docs.document_validation_engine.get_document_validation_engine")
    def test_validate_upload_invalid_file(self, mock_get_engine, review_client):
        """Invalid file returns is_valid=False with issues."""
        mock_engine = MagicMock()
        mock_engine.validate_upload.return_value = MockValidationResult(
            is_valid=False,
            score=15,
            issues=[{"rule": "file_type", "message": "Unsupported file type: .exe"}],
            passed_rules=[],
        )
        mock_get_engine.return_value = mock_engine

        resp = review_client.post(
            f"{BASE}/validate-upload",
            files={"file": ("malware.exe", b"\x00\x01", "application/octet-stream")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is False
        assert len(data["issues"]) > 0

    def test_validate_upload_empty_file(self, review_client):
        """Empty file upload returns 400."""
        resp = review_client.post(
            f"{BASE}/validate-upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

        assert resp.status_code == 400


# =============================================================================
# 7. POST /doc-review/cross-validate/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestCrossValidation:
    """POST /doc-review/cross-validate/{loan_id}"""

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_cross_validate_no_inconsistencies(self, mock_get_svc, mock_verify, review_client, mock_db):
        """Cross-validation with consistent docs returns LOW risk."""
        from models.smart_docs_models import DocumentDecision

        mock_verify.return_value = None

        doc1 = _make_smart_document(id=10, decision=DocumentDecision.ACCEPT)
        doc1.doc_type = MagicMock()
        doc1.doc_type.value = "PAYSTUB"
        doc2 = _make_smart_document(id=11, decision=DocumentDecision.ACCEPT)
        doc2.doc_type = MagicMock()
        doc2.doc_type.value = "W2"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [doc1, doc2]
        mock_db.query.return_value = mock_query

        mock_svc = MagicMock()
        mock_svc._check_cross_document_consistency.return_value = []
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/cross-validate/10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "LOW"
        assert data["inconsistency_count"] == 0
        assert data["document_count"] == 2

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_cross_validate_with_inconsistencies(self, mock_get_svc, mock_verify, review_client, mock_db):
        """Cross-validation with inconsistencies returns elevated risk."""
        from models.smart_docs_models import DocumentDecision

        mock_verify.return_value = None

        doc1 = _make_smart_document(id=10, decision=DocumentDecision.ACCEPT)
        doc1.doc_type = MagicMock()
        doc1.doc_type.value = "PAYSTUB"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [doc1]
        mock_db.query.return_value = mock_query

        mock_svc = MagicMock()
        mock_svc._check_cross_document_consistency.return_value = [
            "Employer name mismatch: 'Acme Corp' vs 'ACME Inc'",
            "Income amount differs by more than 10%",
            "Borrower name variation detected",
        ]
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/cross-validate/10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "HIGH"
        assert data["inconsistency_count"] == 3

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_cross_validate_no_approved_docs(self, mock_verify, review_client, mock_db):
        """Cross-validation with no approved docs returns LOW risk with message."""
        mock_verify.return_value = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        resp = review_client.post(f"{BASE}/cross-validate/10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "LOW"
        assert data["document_count"] == 0


# =============================================================================
# 8. GET /doc-review/loan/{loan_id}/completeness
# =============================================================================

@pytest.mark.unit
class TestLoanCompleteness:
    """GET /doc-review/loan/{loan_id}/completeness"""

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_completeness_all_approved(self, mock_verify, review_client, mock_db):
        """100% completeness when all required docs are approved."""
        from models.smart_docs_models import DocumentDecision, RequestStatus, RequestPriority, DocType

        mock_verify.return_value = None

        # Build mock DocumentRequests
        req1 = MagicMock()
        req1.id = 1
        req1.doc_type = DocType.PAYSTUB
        req1.title = "Most Recent Paystub"
        req1.priority = RequestPriority.HIGH
        req1.status = RequestStatus.ACCEPTED
        req1.due_date = None
        req1.is_active = True

        req2 = MagicMock()
        req2.id = 2
        req2.doc_type = DocType.W2
        req2.title = "W-2 Form"
        req2.priority = RequestPriority.NORMAL
        req2.status = RequestStatus.ACCEPTED
        req2.due_date = None
        req2.is_active = True

        # Build mock SmartDocuments
        doc1 = _make_smart_document(id=100, request_id=1, decision=DocumentDecision.ACCEPT)
        doc1.uploaded_at = datetime.utcnow()
        doc1.rejection_reason = None

        doc2 = _make_smart_document(id=101, request_id=2, decision=DocumentDecision.ACCEPT)
        doc2.uploaded_at = datetime.utcnow()
        doc2.rejection_reason = None

        # Wire up query mocks
        # First query: DocumentRequest
        req_query = MagicMock()
        req_query.filter.return_value = req_query
        req_query.all.return_value = [req1, req2]

        # Second query: SmartDocument
        doc_query = MagicMock()
        doc_query.filter.return_value = doc_query
        doc_query.all.return_value = [doc1, doc2]

        # db.query() is called twice: once for DocumentRequest, once for SmartDocument
        from models.smart_docs_models import DocumentRequest, SmartDocument

        def route_query(model):
            if model is DocumentRequest:
                return req_query
            elif model is SmartDocument:
                return doc_query
            return MagicMock()

        mock_db.query = MagicMock(side_effect=route_query)

        # Mock the estimated_days SQL query
        mock_db.execute = MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))

        resp = review_client.get(f"{BASE}/loan/10/completeness")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required"] == 2
        assert data["approved"] == 2
        assert data["missing"] == 0
        assert data["completeness_pct"] == 100.0

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_completeness_with_missing_docs(self, mock_verify, review_client, mock_db):
        """Partial completeness when some docs are missing."""
        from models.smart_docs_models import DocumentDecision, RequestStatus, RequestPriority, DocType

        mock_verify.return_value = None

        req1 = MagicMock()
        req1.id = 1
        req1.doc_type = DocType.PAYSTUB
        req1.title = "Most Recent Paystub"
        req1.priority = RequestPriority.HIGH
        req1.status = RequestStatus.OPEN
        req1.due_date = None
        req1.is_active = True

        req2 = MagicMock()
        req2.id = 2
        req2.doc_type = DocType.BANK_STATEMENT
        req2.title = "Bank Statements"
        req2.priority = RequestPriority.NORMAL
        req2.status = RequestStatus.OPEN
        req2.due_date = None
        req2.is_active = True

        from models.smart_docs_models import DocumentRequest, SmartDocument

        req_query = MagicMock()
        req_query.filter.return_value = req_query
        req_query.all.return_value = [req1, req2]

        doc_query = MagicMock()
        doc_query.filter.return_value = doc_query
        doc_query.all.return_value = []

        def route_query(model):
            if model is DocumentRequest:
                return req_query
            elif model is SmartDocument:
                return doc_query
            return MagicMock()

        mock_db.query = MagicMock(side_effect=route_query)
        mock_db.execute = MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))

        resp = review_client.get(f"{BASE}/loan/10/completeness")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required"] == 2
        assert data["missing"] == 2
        assert data["completeness_pct"] == 0.0

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_completeness_no_requirements(self, mock_verify, review_client, mock_db):
        """Loan with no document requirements returns 100% completeness."""
        mock_verify.return_value = None

        from models.smart_docs_models import DocumentRequest

        req_query = MagicMock()
        req_query.filter.return_value = req_query
        req_query.all.return_value = []
        mock_db.query = MagicMock(return_value=req_query)

        resp = review_client.get(f"{BASE}/loan/10/completeness")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required"] == 0
        assert data["completeness_pct"] == 100.0


# =============================================================================
# 9. GET /doc-review/document/{document_id}/review-history
# =============================================================================

@pytest.mark.unit
class TestReviewHistory:
    """GET /doc-review/document/{document_id}/review-history"""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_review_history_returns_events(self, mock_verify, review_client, mock_db):
        """Review history endpoint returns policy events and current state."""
        from models.smart_docs_models import DocumentDecision, SmartDocument

        mock_verify.return_value = None

        # Mock the SmartDocument query
        doc = _make_smart_document(
            id=7,
            status="APPROVED",
            reviewed_by="1",
            reviewed_at=datetime(2026, 3, 5, 12, 0, 0),
            file_name="w2_2025.pdf",
        )
        doc.decision = DocumentDecision.ACCEPT
        doc.doc_type = MagicMock()
        doc.doc_type.value = "W2"
        doc.rejection_reason = None
        doc.rejection_category = None

        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = doc
        mock_db.query = MagicMock(return_value=query_mock)

        # Mock the policy events SQL query
        now = datetime(2026, 3, 5, 12, 0, 0)
        event_rows = [
            MagicMock(__getitem__=lambda self, i, vals=(1, "DOCUMENT_UPLOADED", {"decision": "NEEDS_REVIEW", "reason": "New upload"}, now): vals[i]),
            MagicMock(__getitem__=lambda self, i, vals=(2, "DOCUMENT_UPLOADED", {"decision": "ACCEPT", "reviewer": "SYSTEM"}, now): vals[i]),
        ]
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=event_rows))
        )

        resp = review_client.get(f"{BASE}/document/7/review-history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == 7
        assert data["file_name"] == "w2_2025.pdf"
        assert data["doc_type"] == "W2"
        assert data["total_events"] == 2
        assert len(data["history"]) == 2
        assert data["current_state"]["current_decision"] == "ACCEPT"

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_review_history_document_not_found(self, mock_verify, review_client, mock_db):
        """Review history returns 404 when document does not exist."""
        from models.smart_docs_models import SmartDocument

        mock_verify.return_value = None

        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = None
        mock_db.query = MagicMock(return_value=query_mock)

        resp = review_client.get(f"{BASE}/document/9999/review-history")

        assert resp.status_code == 404


# =============================================================================
# 10. POST /doc-review/auto-review-settings (update)
# =============================================================================

@pytest.mark.unit
class TestUpdateAutoReviewSettings:
    """POST /doc-review/auto-review-settings"""

    def test_update_settings_requires_admin(self, review_client):
        """Non-admin users cannot update auto-review settings."""
        resp = review_client.post(
            f"{BASE}/auto-review-settings",
            json={"auto_approve_threshold": 85},
        )
        assert resp.status_code == 403

    def test_update_settings_admin_success(self, admin_review_client, mock_db):
        """Admin can update auto-review settings."""
        # Mock the SELECT for existing settings
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=None))
        )

        resp = admin_review_client.post(
            f"{BASE}/auto-review-settings",
            json={
                "auto_approve_threshold": 85,
                "auto_reject_threshold": 25,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["auto_approve_threshold"] == 85
        assert data["settings"]["auto_reject_threshold"] == 25
        mock_db.commit.assert_called()

    def test_update_settings_invalid_threshold_range(self, admin_review_client):
        """Reject threshold >= approve threshold returns 400."""
        resp = admin_review_client.post(
            f"{BASE}/auto-review-settings",
            json={
                "auto_approve_threshold": 50,
                "auto_reject_threshold": 70,
            },
        )
        assert resp.status_code == 400

    def test_update_settings_threshold_out_of_bounds(self, admin_review_client):
        """Threshold outside 0-100 returns 400."""
        resp = admin_review_client.post(
            f"{BASE}/auto-review-settings",
            json={"auto_approve_threshold": 150},
        )
        assert resp.status_code == 400


# =============================================================================
# 11. GET /doc-review/auto-review-settings
# =============================================================================

@pytest.mark.unit
class TestGetAutoReviewSettings:
    """GET /doc-review/auto-review-settings"""

    def test_get_settings_returns_defaults_when_none(self, review_client, mock_db):
        """Returns default settings when none are configured."""
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=None))
        )

        resp = review_client.get(f"{BASE}/auto-review-settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["auto_approve_threshold"] == 80
        assert data["settings"]["auto_reject_threshold"] == 30
        assert "quality" in data["settings"]["enabled_checks"]

    def test_get_settings_returns_stored_values(self, review_client, mock_db):
        """Returns stored settings when they exist."""
        stored = json.dumps({
            "auto_approve_threshold": 90,
            "auto_reject_threshold": 20,
            "enabled_checks": ["quality", "freshness"],
        })
        row = MagicMock()
        row.__getitem__ = lambda self, i: stored
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=row))
        )

        resp = review_client.get(f"{BASE}/auto-review-settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["auto_approve_threshold"] == 90
        assert data["settings"]["auto_reject_threshold"] == 20


# =============================================================================
# 12. GET /doc-review/stats (quality metrics dashboard)
# =============================================================================

@pytest.mark.unit
class TestReviewStats:
    """GET /doc-review/stats"""

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_stats_returns_accuracy_and_overrides(self, mock_get_svc, review_client, mock_db):
        """Stats endpoint returns AI accuracy and human override data."""
        mock_svc = MagicMock()
        mock_svc.get_review_stats.return_value = {
            "total_reviewed": 100,
            "auto_approved": 60,
            "rejected": 15,
            "needs_review": 25,
        }
        mock_get_svc.return_value = mock_svc

        # Mock the human override SQL query
        override_row = MagicMock()
        override_row.__getitem__ = lambda self, i: [80, 5][i]
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=override_row))
        )

        resp = review_client.get(f"{BASE}/stats", params={"days": 30})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_reviewed"] == 100
        assert data["human_reviews"] == 80
        assert data["ai_overrides"] == 5
        # AI accuracy = ((80 - 5) / 80) * 100 = 93.8%
        assert data["ai_accuracy_pct"] == 93.8


# =============================================================================
# 13. POST /doc-review/document/{document_id}/ai-extract-and-review
# =============================================================================

@pytest.mark.unit
class TestAIExtractAndReview:
    """POST /doc-review/document/{document_id}/ai-extract-and-review"""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_extract_and_review_returns_both(self, mock_get_svc, mock_verify, review_client, mock_db):
        """Combined endpoint returns both extraction result and review decision."""
        doc = _make_smart_document(id=20, storage_key="org-100/loan-10/pay.pdf")
        mock_verify.return_value = doc

        mock_svc = MagicMock()
        mock_svc.review_document.return_value = MockReviewResult(decision="ACCEPT", confidence=90)
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/document/20/ai-extract-and-review")

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == 20
        assert data["review"]["decision"] == "ACCEPT"
        assert data["review"]["confidence"] == 90
        mock_db.commit.assert_called()


# =============================================================================
# 14. GET /doc-review/validation-rules/{doc_type}
# =============================================================================

@pytest.mark.unit
class TestValidationRules:
    """GET /doc-review/validation-rules/{doc_type}"""

    @patch("services.smart_docs.document_validation_engine.get_document_validation_engine")
    def test_get_validation_rules(self, mock_get_engine, review_client):
        """Returns validation rules for a specific doc type."""
        mock_engine = MagicMock()
        mock_engine.get_validation_rules_for_type.return_value = {
            "doc_type": "PAYSTUB",
            "freshness_days": 30,
            "allowed_formats": ["pdf", "jpg", "png"],
            "max_size_mb": 25,
            "rules": [
                {"name": "quality_check", "description": "Image quality > 72 DPI"},
                {"name": "freshness_check", "description": "Document within 30 days"},
            ],
        }
        mock_get_engine.return_value = mock_engine

        resp = review_client.get(f"{BASE}/validation-rules/PAYSTUB")

        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_type"] == "PAYSTUB"
        assert data["freshness_days"] == 30


# =============================================================================
# 15. Review queue ordering by priority
# =============================================================================

@pytest.mark.unit
class TestQueuePriorityOrdering:
    """Verify review queue returns items ordered by priority."""

    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_queue_critical_first(self, mock_get_svc, review_client):
        """CRITICAL priority items appear before NORMAL in queue."""
        mock_svc = MagicMock()
        mock_svc.review_queue.return_value = [
            {"document_id": 1, "priority": "CRITICAL", "doc_type": "PAYSTUB"},
            {"document_id": 2, "priority": "HIGH", "doc_type": "W2"},
            {"document_id": 3, "priority": "NORMAL", "doc_type": "BANK_STATEMENT"},
            {"document_id": 4, "priority": "LOW", "doc_type": "OTHER"},
        ]
        mock_get_svc.return_value = mock_svc

        resp = review_client.get(f"{BASE}/queue")

        assert resp.status_code == 200
        items = resp.json()["items"]
        priorities = [item["priority"] for item in items]
        # Ensure CRITICAL comes before LOW
        assert priorities.index("CRITICAL") < priorities.index("LOW")


# =============================================================================
# 16. Tenant isolation on review endpoints
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Verify review endpoints enforce tenant isolation."""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_ai_review_rejects_wrong_tenant(self, mock_verify, other_org_client):
        """AI review returns 404 when document belongs to different org."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = other_org_client.post(f"{BASE}/ai-review/1")
        assert resp.status_code == 404

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_cross_validate_rejects_wrong_tenant(self, mock_verify, other_org_client):
        """Cross-validation returns 404 for loans in a different org."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = other_org_client.post(f"{BASE}/cross-validate/10")
        assert resp.status_code == 404

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_completeness_rejects_wrong_tenant(self, mock_verify, other_org_client):
        """Completeness check returns 404 for loans in a different org."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = other_org_client.get(f"{BASE}/loan/10/completeness")
        assert resp.status_code == 404

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    def test_claim_rejects_wrong_tenant(self, mock_verify, other_org_client):
        """Claim returns 404 for documents in a different org."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = other_org_client.post(f"{BASE}/queue/1/claim")
        assert resp.status_code == 404

    def test_queue_stats_requires_org_id(self, mock_db):
        """Queue stats returns 400 when user has no organization_id."""
        from main import app

        no_org_user = MockUser(organization_id=None)
        _setup_app_overrides(app, mock_db, no_org_user)

        with TestClient(app) as tc:
            resp = tc.get(f"{BASE}/queue/stats")
            assert resp.status_code == 400
            assert "Organization ID required" in resp.json()["detail"]

        app.dependency_overrides.clear()


# =============================================================================
# 17. POST /doc-review/ai-review/batch/{loan_id}  (batch AI review)
# =============================================================================

@pytest.mark.unit
class TestBatchAIReview:
    """POST /doc-review/ai-review/batch/{loan_id}"""

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_batch_review_returns_summary(self, mock_get_svc, mock_verify, review_client):
        """Batch review returns aggregate counts and per-document results."""
        mock_verify.return_value = None
        mock_svc = MagicMock()
        mock_svc.batch_review.return_value = MockBatchResult()
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/ai-review/batch/10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 10
        assert data["total"] == 3
        assert data["approved"] == 2
        assert data["rejected"] == 0
        assert data["needs_review"] == 1
        assert len(data["results"]) == 3

    @patch("routes.smart_docs_review_routes._verify_loan_tenant")
    def test_batch_review_tenant_isolation(self, mock_verify, other_org_client):
        """Batch review returns 404 for loans in a different org."""
        from fastapi import HTTPException

        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")

        resp = other_org_client.post(f"{BASE}/ai-review/batch/10")
        assert resp.status_code == 404


# =============================================================================
# 18. POST /doc-review/document/{document_id}/ai-extract-and-review
#     (re-review scenario)
# =============================================================================

@pytest.mark.unit
class TestReReview:
    """Test re-reviewing a document that was previously reviewed."""

    @patch("routes.smart_docs_review_routes._verify_document_tenant")
    @patch("services.smart_docs.ai_review_service.get_ai_review_service")
    def test_re_review_updates_decision(self, mock_get_svc, mock_verify, review_client, mock_db):
        """Re-reviewing a document updates the decision from the latest review."""
        from models.smart_docs_models import DocumentDecision

        doc = _make_smart_document(
            id=30,
            decision=DocumentDecision.REJECT,
            status="REJECTED",
            reviewed_by="SYSTEM",
        )
        mock_verify.return_value = doc

        mock_svc = MagicMock()
        mock_svc.review_document.return_value = MockReviewResult(
            decision="ACCEPT",
            confidence=88,
            auto_approved=True,
        )
        mock_get_svc.return_value = mock_svc

        resp = review_client.post(f"{BASE}/ai-review/30")

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "ACCEPT"
        assert data["auto_approved"] is True
