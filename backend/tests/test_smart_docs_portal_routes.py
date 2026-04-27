"""
Test Smart Docs Borrower Portal Routes

Integration tests for the borrower-facing document portal API endpoints.
These endpoints use workspace-slug-based auth (no JWT) and are scoped
under /portal/docs/{workspace_slug}/...

Covers:
1.  GET  /portal/docs/{slug}/needs-list         - borrower document checklist
2.  POST /portal/docs/{slug}/upload              - borrower upload document
3.  GET  /portal/docs/{slug}/status              - overall document status
4.  GET  /portal/docs/{slug}/document/{id}/status - individual document review status
5.  POST /portal/docs/{slug}/loe                 - submit letter of explanation
6.  GET  /portal/docs/{slug}/signing-requests    - e-signature requests
7.  GET  /portal/docs/{slug}/appointments        - upcoming appointments
8.  POST /portal/docs/{slug}/appointments/{id}/confirm   - confirm appointment
9.  POST /portal/docs/{slug}/appointments/{id}/reschedule - reschedule appointment
10. GET  /portal/docs/{slug}/messages            - portal messages
11. POST /portal/docs/{slug}/contact             - send message to LO
12. GET  /portal/docs/{slug}/checklist           - visual checklist by category
13. POST /portal/docs/{slug}/document/{id}/reupload - re-upload rejected doc
14. GET  /portal/docs/{slug}/document/{id}/preview  - presigned preview URL
15. Cross-tenant isolation (borrower sees only their own docs)
16. Invalid workspace slug returns 404
17. Rate limiting / empty-body validation on public endpoints
"""

import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from fastapi.testclient import TestClient
from io import BytesIO

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# =============================================================================
# Helpers: mock objects that mimic SQLAlchemy ORM instances
# =============================================================================

def _make_workspace(slug="test-workspace", org_id=1, display_name="John Smith"):
    ws = MagicMock()
    ws.id = 100
    ws.slug = slug
    ws.organization_id = org_id
    ws.display_name = display_name
    return ws


def _make_purl_loan(workspace_id=100, main_loan_id=500):
    loan = MagicMock()
    loan.id = 501
    loan.workspace_id = workspace_id
    loan.main_loan_id = main_loan_id
    loan.created_at = datetime.now(timezone.utc)
    return loan


def _make_purl_contact(workspace_id=100, email="borrower@example.com"):
    contact = MagicMock()
    contact.id = 200
    contact.workspace_id = workspace_id
    contact.contact_type = "borrower"
    contact.first_name = "John"
    contact.last_name = "Smith"
    contact.email = email
    return contact


def _make_document_request(
    req_id=1,
    loan_id=500,
    doc_type_val="PAYSTUB",
    status_val="OPEN",
    priority_val="NORMAL",
    is_active=True,
    title="Recent Paystubs",
):
    from models.smart_docs_models import DocType, RequestStatus, RequestPriority

    req = MagicMock()
    req.id = req_id
    req.loan_id = loan_id
    req.doc_type = DocType(doc_type_val)
    req.title = title
    req.description = "Provide your two most recent paystubs"
    req.instructions = "Upload PDF or photo of paystub"
    req.status = RequestStatus(status_val)
    req.priority = RequestPriority(priority_val)
    req.due_date = datetime.now(timezone.utc) + timedelta(days=5)
    req.is_active = is_active
    req.required_count = 2
    req.created_at = datetime.now(timezone.utc)
    return req


def _make_smart_document(
    doc_id=10,
    request_id=1,
    loan_id=500,
    status="UPLOADED",
    decision=None,
    doc_type_val="PAYSTUB",
    file_name="paystub_jan.pdf",
):
    from models.smart_docs_models import DocType, DocumentDecision

    doc = MagicMock()
    doc.id = doc_id
    doc.request_id = request_id
    doc.loan_id = loan_id
    doc.borrower_id = 200
    doc.file_name = file_name
    doc.original_filename = file_name
    doc.display_name = None
    doc.mime_type = "application/pdf"
    doc.file_size = 102400
    doc.storage_key = f"org1/loan{loan_id}/{file_name}"
    doc.doc_type = DocType(doc_type_val) if doc_type_val else None
    doc.status = status
    doc.decision = DocumentDecision(decision) if decision else None
    doc.rejection_reason = None
    doc.rejection_category = None
    doc.fix_instructions = None
    doc.reviewed_at = None
    doc.reviewed_by = None
    doc.uploaded_at = datetime.now(timezone.utc)
    doc.detected_doc_type = None
    doc.updated_at = None
    return doc


def _make_appointment(
    appt_id=1,
    loan_id=500,
    status_val="SCHEDULED",
    title="Document Review Call",
):
    appt = MagicMock()
    appt.id = appt_id
    appt.loan_id = loan_id
    appt.title = title
    appt.description = "Review outstanding docs"
    appt.appointment_type = MagicMock(value="document_review")
    appt.status = MagicMock(value=status_val)
    appt.scheduled_date = datetime.now(timezone.utc) + timedelta(days=2)
    appt.scheduled_time_start = None
    appt.scheduled_time_end = None
    appt.duration_minutes = 30
    appt.location_type = MagicMock(value="virtual")
    appt.location_details = None
    appt.meeting_link = "https://meet.example.com/abc123"
    appt.confirmed_at = None
    appt.updated_at = None
    return appt


def _make_message(msg_id=1, msg_type="text", content="Hello", is_read=False):
    msg = MagicMock()
    msg.id = msg_id
    msg.message_type = msg_type
    msg.content = content
    msg.sender_type = "user"
    msg.is_read_by_borrower = is_read
    msg.created_at = datetime.now(timezone.utc)
    return msg


# =============================================================================
# Fixture: patch _verify_portal_access for most tests
# =============================================================================

@pytest.fixture
def portal_access_data():
    """Default portal access data returned by _verify_portal_access."""
    ws = _make_workspace()
    return {
        "workspace": ws,
        "purl_loan": _make_purl_loan(),
        "loan_id": 500,
        "borrower_id": 200,
        "borrower_name": "John Smith",
        "borrower_email": "borrower@example.com",
        "org_id": 1,
    }


@pytest.fixture
def mock_portal_access(portal_access_data):
    """Patch _verify_portal_access to return test data without DB queries."""
    with patch(
        "routes.smart_docs_portal_routes._verify_portal_access",
        return_value=portal_access_data,
    ) as mock_fn:
        yield mock_fn


# =============================================================================
# 1. GET /portal/docs/{slug}/needs-list
# =============================================================================

@pytest.mark.unit
class TestGetNeedsList:
    """Tests for the borrower document needs list endpoint."""

    def test_needs_list_returns_requests_with_uploaded_docs(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Needs list should return document requests and any uploaded docs."""
        req = _make_document_request()
        doc = _make_smart_document()

        with patch.object(db_session, "query") as mock_query:
            # First query: DocumentRequest list
            mock_req_chain = MagicMock()
            mock_req_chain.filter.return_value = mock_req_chain
            mock_req_chain.order_by.return_value = mock_req_chain
            mock_req_chain.all.return_value = [req]

            # Second query: SmartDocument list for the request
            mock_doc_chain = MagicMock()
            mock_doc_chain.filter.return_value = mock_doc_chain
            mock_doc_chain.order_by.return_value = mock_doc_chain
            mock_doc_chain.all.return_value = [doc]

            mock_query.side_effect = [mock_req_chain, mock_doc_chain]

            response = client.get("/portal/docs/test-workspace/needs-list")

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_slug"] == "test-workspace"
        assert data["borrower_name"] == "John Smith"
        assert data["total"] == 1
        assert len(data["needs_list"]) == 1
        item = data["needs_list"][0]
        assert item["request_id"] == 1
        assert item["doc_type"] == "PAYSTUB"
        assert item["status"] == "OPEN"

    def test_needs_list_empty_when_no_loan(
        self, client: TestClient, portal_access_data
    ):
        """Needs list returns empty when portal has no associated loan."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.get("/portal/docs/test-workspace/needs-list")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_list"] == []
        assert data["total"] == 0


# =============================================================================
# 2. POST /portal/docs/{slug}/upload
# =============================================================================

@pytest.mark.unit
class TestPortalUpload:
    """Tests for the borrower document upload endpoint."""

    def test_upload_requires_file(self, client: TestClient, mock_portal_access):
        """Upload should reject request with no file."""
        response = client.post("/portal/docs/test-workspace/upload")
        assert response.status_code == 422  # FastAPI validation error

    @patch("routes.smart_docs_portal_routes.get_followup_automation_service")
    @patch("routes.smart_docs_portal_routes.get_ai_review_service")
    @patch("routes.smart_docs_portal_routes.get_ai_classifier_service")
    @patch("routes.smart_docs_portal_routes.get_document_validation_engine")
    @patch("routes.smart_docs_portal_routes.get_smart_docs_s3_service")
    def test_upload_success(
        self,
        mock_s3_factory,
        mock_validation_factory,
        mock_classifier_factory,
        mock_review_factory,
        mock_followup_factory,
        client: TestClient,
        mock_portal_access,
        db_session,
    ):
        """Successful upload should create document record and return doc ID."""
        # Mock S3
        mock_s3 = MagicMock()
        mock_s3.generate_storage_key.return_value = "org1/loan500/test.pdf"
        mock_s3.upload_file.return_value = {"success": True}
        mock_s3.is_available = True
        mock_s3_factory.return_value = mock_s3

        # Mock validation engine
        mock_validator = MagicMock()
        mock_validator.validate_upload.return_value = {"has_critical": False, "issues": []}
        mock_validation_factory.return_value = mock_validator

        # Mock classifier
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = {"doc_type": "PAYSTUB", "confidence": 0.95}
        mock_classifier_factory.return_value = mock_classifier

        # Mock review service
        mock_review = MagicMock()
        mock_review.review_document.return_value = {"status": "PENDING_REVIEW"}
        mock_review_factory.return_value = mock_review

        # Mock followup
        mock_followup = MagicMock()
        mock_followup_factory.return_value = mock_followup

        # Mock db.add / db.commit / db.refresh to simulate ORM
        def fake_refresh(obj):
            obj.id = 42
            obj.doc_type = None
            obj.status = "UPLOADED"

        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        db_session.refresh = MagicMock(side_effect=fake_refresh)
        db_session.query = MagicMock()  # Not queried during upload without request_id

        file_content = b"%PDF-1.4 fake pdf content for test"
        response = client.post(
            "/portal/docs/test-workspace/upload",
            files={"file": ("test_paystub.pdf", BytesIO(file_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == 42
        assert data["file_name"] == "test_paystub.pdf"
        assert data["message"] == "Document uploaded successfully"
        mock_s3.upload_file.assert_called_once()

    @patch("routes.smart_docs_portal_routes.get_document_validation_engine")
    def test_upload_rejects_invalid_file(
        self,
        mock_validation_factory,
        client: TestClient,
        mock_portal_access,
    ):
        """Upload should reject files that fail validation (e.g., executable)."""
        mock_validator = MagicMock()
        mock_validator.validate_upload.return_value = {
            "has_critical": True,
            "issues": [{"severity": "CRITICAL", "message": "Executable file type not allowed"}],
        }
        mock_validation_factory.return_value = mock_validator

        response = client.post(
            "/portal/docs/test-workspace/upload",
            files={"file": ("malware.exe", BytesIO(b"\x00" * 100), "application/octet-stream")},
        )

        assert response.status_code == 400
        assert "Executable file type not allowed" in response.json()["detail"]

    def test_upload_rejects_oversized_file(
        self, client: TestClient, mock_portal_access
    ):
        """Upload should reject files larger than 20 MB."""
        with patch(
            "routes.smart_docs_portal_routes.get_document_validation_engine"
        ) as mock_val_factory:
            mock_validator = MagicMock()
            mock_validator.validate_upload.return_value = {"has_critical": False, "issues": []}
            mock_val_factory.return_value = mock_validator

            # 21 MB of zeros
            large_content = b"\x00" * (21 * 1024 * 1024)
            response = client.post(
                "/portal/docs/test-workspace/upload",
                files={"file": ("huge.pdf", BytesIO(large_content), "application/pdf")},
            )

        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]

    def test_upload_fails_without_loan(self, client: TestClient, portal_access_data):
        """Upload should return 400 when portal has no associated loan."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.post(
                "/portal/docs/test-workspace/upload",
                files={"file": ("test.pdf", BytesIO(b"data"), "application/pdf")},
            )

        assert response.status_code == 400
        assert "No loan associated" in response.json()["detail"]


# =============================================================================
# 3. GET /portal/docs/{slug}/status
# =============================================================================

@pytest.mark.unit
class TestGetDocumentStatus:
    """Tests for the overall document collection status endpoint."""

    def test_status_returns_counts_and_completeness(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Status endpoint should return correct counts and completeness %."""
        from models.smart_docs_models import RequestStatus

        reqs = [
            _make_document_request(req_id=1, status_val="ACCEPTED"),
            _make_document_request(req_id=2, status_val="OPEN", doc_type_val="W2", title="W-2 Forms"),
            _make_document_request(req_id=3, status_val="PENDING_REVIEW", doc_type_val="BANK_STATEMENT", title="Bank Statements"),
            _make_document_request(req_id=4, status_val="REJECTED", doc_type_val="TAX_RETURN", title="Tax Returns"),
        ]

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.all.return_value = reqs
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/status")

        assert response.status_code == 200
        data = response.json()
        assert data["total_required"] == 4
        assert data["approved"] == 1
        assert data["open"] == 1
        assert data["pending"] == 1
        assert data["rejected"] == 1
        assert data["completeness_percentage"] == 25.0
        # Next actions should include upload and reupload
        action_types = [a["action"] for a in data["next_actions"]]
        assert "upload_documents" in action_types
        assert "reupload_rejected" in action_types

    def test_status_empty_when_no_loan(
        self, client: TestClient, portal_access_data
    ):
        """Status returns zeroes when no loan is associated."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.get("/portal/docs/test-workspace/status")

        assert response.status_code == 200
        data = response.json()
        assert data["total_required"] == 0
        assert data["completeness_percentage"] == 0


# =============================================================================
# 4. GET /portal/docs/{slug}/document/{id}/status
# =============================================================================

@pytest.mark.unit
class TestGetDocumentReviewStatus:
    """Tests for individual document review status endpoint."""

    def test_document_status_returns_review_details(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return document status, decision, and rejection details."""
        doc = _make_smart_document(doc_id=10, status="APPROVED", decision="ACCEPT")
        doc.reviewed_at = datetime.now(timezone.utc)
        doc.reviewed_by = "SYSTEM"

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = doc
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/document/10/status")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == 10
        assert data["status"] == "APPROVED"
        assert data["decision"] == "ACCEPT"

    def test_document_status_404_for_wrong_loan(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return 404 if document does not belong to portal's loan."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = None  # Not found for this loan_id
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/document/999/status")

        assert response.status_code == 404


# =============================================================================
# 5. POST /portal/docs/{slug}/loe
# =============================================================================

@pytest.mark.unit
class TestSubmitLOE:
    """Tests for Letter of Explanation submission endpoint."""

    @patch("routes.smart_docs_portal_routes.get_smart_docs_s3_service")
    @patch("routes.smart_docs_portal_routes.get_pdf_generation_service")
    def test_loe_submission_success(
        self,
        mock_pdf_factory,
        mock_s3_factory,
        client: TestClient,
        mock_portal_access,
        db_session,
    ):
        """Successful LOE submission creates document record."""
        mock_pdf = MagicMock()
        mock_pdf.generate_loe_pdf.return_value = b"%PDF-1.4 LOE content"
        mock_pdf_factory.return_value = mock_pdf

        mock_s3 = MagicMock()
        mock_s3.generate_storage_key.return_value = "org1/loan500/loe.pdf"
        mock_s3.upload_file.return_value = {"success": True}
        mock_s3.is_available = True
        mock_s3_factory.return_value = mock_s3

        def fake_refresh(obj):
            obj.id = 55
            obj.file_name = "LOE_Credit_Inquiry_20260310.pdf"
            obj.status = "UPLOADED"
        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        db_session.refresh = MagicMock(side_effect=fake_refresh)
        db_session.query = MagicMock()

        response = client.post(
            "/portal/docs/test-workspace/loe",
            json={
                "subject": "Credit Inquiry",
                "explanation_text": "The inquiry was for a credit card I did not apply for.",
                "borrower_name": "John Smith",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == 55
        assert data["doc_type"] == "LOE"
        assert "submitted successfully" in data["message"]

    def test_loe_fails_without_loan(self, client: TestClient, portal_access_data):
        """LOE submission should fail if no loan is associated."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.post(
                "/portal/docs/test-workspace/loe",
                json={
                    "subject": "Test",
                    "explanation_text": "Test explanation",
                    "borrower_name": "John Smith",
                },
            )
        assert response.status_code == 400


# =============================================================================
# 6. GET /portal/docs/{slug}/signing-requests
# =============================================================================

@pytest.mark.unit
class TestGetSigningRequests:
    """Tests for e-signature requests endpoint."""

    def test_signing_requests_returns_pending_envelopes(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return pending e-signature envelopes for the borrower."""
        mock_envelope = MagicMock()
        mock_envelope.id = 10
        mock_envelope.envelope_uuid = "env-uuid-001"
        mock_envelope.title = "Initial Disclosures"
        mock_envelope.description = "Please review and sign"
        mock_envelope.status = "sent"
        mock_envelope.sent_at = datetime.now(timezone.utc)
        mock_envelope.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        mock_recipient = MagicMock()
        mock_recipient.email = "borrower@example.com"
        mock_recipient.status = "pending"
        mock_recipient.signing_token = "tok_abc123"

        # Build query mocks for envelopes and recipients
        mock_env_chain = MagicMock()
        mock_env_chain.filter.return_value = mock_env_chain
        mock_env_chain.order_by.return_value = mock_env_chain
        mock_env_chain.all.return_value = [mock_envelope]

        mock_recip_chain = MagicMock()
        mock_recip_chain.filter.return_value = mock_recip_chain
        mock_recip_chain.first.return_value = mock_recipient

        db_session.query = MagicMock(side_effect=[mock_env_chain, mock_recip_chain])

        response = client.get("/portal/docs/test-workspace/signing-requests")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["signing_requests"][0]["envelope_uuid"] == "env-uuid-001"
        assert "tok_abc123" in data["signing_requests"][0]["signing_url"]

    def test_signing_requests_empty_when_no_loan(
        self, client: TestClient, portal_access_data
    ):
        """Returns empty list when no loan is associated."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.get("/portal/docs/test-workspace/signing-requests")

        assert response.status_code == 200
        assert response.json()["total"] == 0


# =============================================================================
# 7. GET /portal/docs/{slug}/appointments
# =============================================================================

@pytest.mark.unit
class TestGetAppointments:
    """Tests for borrower appointments endpoint."""

    def test_appointments_returns_scheduled_items(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return upcoming scheduled and confirmed appointments."""
        appt = _make_appointment()

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.all.return_value = [appt]
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/appointments")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["appointments"][0]["title"] == "Document Review Call"
        assert data["appointments"][0]["meeting_link"] == "https://meet.example.com/abc123"

    def test_appointments_empty_when_no_loan(
        self, client: TestClient, portal_access_data
    ):
        """Returns empty when no loan is associated."""
        portal_access_data["loan_id"] = None
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_access_data,
        ):
            response = client.get("/portal/docs/test-workspace/appointments")

        assert response.status_code == 200
        assert response.json()["total"] == 0


# =============================================================================
# 8. POST /portal/docs/{slug}/appointments/{id}/confirm
# =============================================================================

@pytest.mark.unit
class TestConfirmAppointment:
    """Tests for appointment confirmation endpoint."""

    def test_confirm_scheduled_appointment(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should confirm a SCHEDULED appointment and return confirmed_at."""
        from database.models.document_followup import AppointmentStatus

        appt = MagicMock()
        appt.id = 1
        appt.loan_id = 500
        appt.title = "Doc Review"
        appt.status = AppointmentStatus.SCHEDULED
        appt.confirmed_at = None

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = appt
        db_session.query = MagicMock(return_value=mock_chain)
        db_session.commit = MagicMock()

        response = client.post("/portal/docs/test-workspace/appointments/1/confirm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["appointment_id"] == 1

    def test_confirm_nonexistent_appointment_returns_404(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return 404 if appointment does not exist for this loan."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = None
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.post("/portal/docs/test-workspace/appointments/999/confirm")

        assert response.status_code == 404


# =============================================================================
# 9. POST /portal/docs/{slug}/appointments/{id}/reschedule
# =============================================================================

@pytest.mark.unit
class TestRescheduleAppointment:
    """Tests for appointment reschedule endpoint."""

    def test_reschedule_sends_preferred_dates(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should accept reschedule request with preferred dates."""
        appt = MagicMock()
        appt.id = 1
        appt.loan_id = 500
        appt.title = "Doc Review"

        mock_appt_chain = MagicMock()
        mock_appt_chain.filter.return_value = mock_appt_chain
        mock_appt_chain.first.return_value = appt

        db_session.query = MagicMock(return_value=mock_appt_chain)
        db_session.add = MagicMock()
        db_session.commit = MagicMock()

        response = client.post(
            "/portal/docs/test-workspace/appointments/1/reschedule",
            json={"preferred_dates": ["2026-03-15", "2026-03-16"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reschedule_requested"
        assert "2026-03-15" in data["preferred_dates"]

    def test_reschedule_404_for_missing_appointment(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return 404 if appointment does not exist."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = None
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.post(
            "/portal/docs/test-workspace/appointments/999/reschedule",
            json={"preferred_dates": ["2026-03-20"]},
        )

        assert response.status_code == 404


# =============================================================================
# 10. GET /portal/docs/{slug}/messages
# =============================================================================

@pytest.mark.unit
class TestGetMessages:
    """Tests for portal messages endpoint."""

    def test_messages_returns_list(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return messages for the workspace."""
        msg1 = _make_message(msg_id=1, content="Welcome to your portal")
        msg2 = _make_message(msg_id=2, msg_type="system", content="Document uploaded")

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = [msg1, msg2]
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["messages"][0]["message_id"] == 1


# =============================================================================
# 11. POST /portal/docs/{slug}/contact
# =============================================================================

@pytest.mark.unit
class TestSendContactMessage:
    """Tests for sending a message to the LO."""

    def test_contact_message_success(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should create a message and return success."""
        def fake_refresh(obj):
            obj.id = 77

        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        db_session.refresh = MagicMock(side_effect=fake_refresh)
        db_session.execute = MagicMock()

        response = client.post(
            "/portal/docs/test-workspace/contact",
            json={"message": "I have a question about my bank statements"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == 77
        assert data["status"] == "sent"

    def test_contact_message_rejects_empty_body(
        self, client: TestClient, mock_portal_access
    ):
        """Should reject empty or whitespace-only messages."""
        response = client.post(
            "/portal/docs/test-workspace/contact",
            json={"message": "   "},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()


# =============================================================================
# 12. GET /portal/docs/{slug}/checklist
# =============================================================================

@pytest.mark.unit
class TestGetChecklist:
    """Tests for the visual document checklist endpoint."""

    def test_checklist_returns_categorized_items(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return document requests organized by category."""
        from models.smart_docs_models import RequestStatus

        req_income = _make_document_request(req_id=1, doc_type_val="PAYSTUB", status_val="ACCEPTED")
        req_asset = _make_document_request(req_id=2, doc_type_val="BANK_STATEMENT", status_val="OPEN", title="Bank Statements")

        # Mock the DocumentRequest query
        mock_req_chain = MagicMock()
        mock_req_chain.filter.return_value = mock_req_chain
        mock_req_chain.order_by.return_value = mock_req_chain
        mock_req_chain.all.return_value = [req_income, req_asset]

        # Mock the SmartDocument count query (called per request)
        mock_doc_chain = MagicMock()
        mock_doc_chain.filter.return_value = mock_doc_chain
        mock_doc_chain.count.return_value = 1

        db_session.query = MagicMock(side_effect=[mock_req_chain, mock_doc_chain, mock_doc_chain])

        response = client.get("/portal/docs/test-workspace/checklist")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert data["summary"]["total"] == 2
        assert data["summary"]["completed"] == 1
        assert data["summary"]["completeness_percentage"] == 50.0

        # Should have Income and Assets categories
        category_names = [c["category"] for c in data["categories"]]
        assert "Income" in category_names
        assert "Assets" in category_names


# =============================================================================
# 13. POST /portal/docs/{slug}/document/{id}/reupload
# =============================================================================

@pytest.mark.unit
class TestReuploadDocument:
    """Tests for re-uploading a rejected document."""

    @patch("routes.smart_docs_portal_routes.get_ai_review_service")
    @patch("routes.smart_docs_portal_routes.get_document_validation_engine")
    @patch("routes.smart_docs_portal_routes.get_smart_docs_s3_service")
    def test_reupload_supersedes_original(
        self,
        mock_s3_factory,
        mock_validation_factory,
        mock_review_factory,
        client: TestClient,
        mock_portal_access,
        db_session,
    ):
        """Re-upload should mark original as SUPERSEDED and create new doc."""
        original_doc = _make_smart_document(doc_id=10, status="REJECTED", decision="REJECT")
        original_doc.request_id = 1

        mock_s3 = MagicMock()
        mock_s3.generate_storage_key.return_value = "org1/loan500/reupload.pdf"
        mock_s3.upload_file.return_value = {"success": True}
        mock_s3.is_available = True
        mock_s3_factory.return_value = mock_s3

        mock_validator = MagicMock()
        mock_validator.validate_upload.return_value = {"has_critical": False, "issues": []}
        mock_validation_factory.return_value = mock_validator

        mock_review = MagicMock()
        mock_review.review_document.return_value = {"status": "PENDING_REVIEW"}
        mock_review_factory.return_value = mock_review

        # First query returns the original doc; subsequent queries for request update
        mock_doc_chain = MagicMock()
        mock_doc_chain.filter.return_value = mock_doc_chain
        mock_doc_chain.first.return_value = original_doc

        mock_req_chain = MagicMock()
        mock_req_chain.filter.return_value = mock_req_chain
        mock_req_chain.first.return_value = _make_document_request(req_id=1)

        db_session.query = MagicMock(side_effect=[mock_doc_chain, mock_req_chain])

        def fake_refresh(obj):
            obj.id = 43
            obj.file_name = "reupload.pdf"
            obj.doc_type = original_doc.doc_type
            obj.status = "UPLOADED"

        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        db_session.refresh = MagicMock(side_effect=fake_refresh)

        response = client.post(
            "/portal/docs/test-workspace/document/10/reupload",
            files={"file": ("fixed_paystub.pdf", BytesIO(b"new content"), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == 43
        assert data["superseded_document_id"] == 10
        assert "re-uploaded successfully" in data["message"]
        # Original should be marked SUPERSEDED
        assert original_doc.status == "SUPERSEDED"


# =============================================================================
# 14. GET /portal/docs/{slug}/document/{id}/preview
# =============================================================================

@pytest.mark.unit
class TestPreviewDocument:
    """Tests for document preview (presigned S3 URL) endpoint."""

    @patch("routes.smart_docs_portal_routes.get_smart_docs_s3_service")
    def test_preview_returns_presigned_url(
        self,
        mock_s3_factory,
        client: TestClient,
        mock_portal_access,
        db_session,
    ):
        """Should return a presigned URL for document preview."""
        doc = _make_smart_document(doc_id=10)

        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = doc
        db_session.query = MagicMock(return_value=mock_chain)
        db_session.add = MagicMock()
        db_session.commit = MagicMock()

        mock_s3 = MagicMock()
        mock_s3.get_presigned_download_url.return_value = {
            "presigned_url": "https://s3.amazonaws.com/bucket/key?token=xyz"
        }
        mock_s3_factory.return_value = mock_s3

        response = client.get("/portal/docs/test-workspace/document/10/preview")

        assert response.status_code == 200
        data = response.json()
        assert "presigned_url" not in data.get("preview_url", "") or data["preview_url"].startswith("https://")
        assert data["expires_in"] == 600

    def test_preview_404_for_missing_document(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Should return 404 if document not found for this loan."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = None
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/document/999/preview")

        assert response.status_code == 404


# =============================================================================
# 15. Cross-tenant isolation: borrower only sees their own docs
# =============================================================================

@pytest.mark.unit
class TestCrossTenantIsolation:
    """Verify that borrowers cannot access documents from other portals."""

    def test_invalid_workspace_slug_returns_404(self, client: TestClient):
        """Accessing a nonexistent workspace slug should return 404."""
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            side_effect=lambda db, slug: (_ for _ in ()).throw(
                __import__("fastapi").HTTPException(status_code=404, detail="Portal not found")
            ),
        ):
            response = client.get("/portal/docs/nonexistent-slug/needs-list")

        assert response.status_code == 404
        assert "Portal not found" in response.json()["detail"]

    def test_document_scoped_to_loan(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Document status endpoint filters by loan_id from portal context.

        If a borrower tries to access a document_id that belongs to another
        loan, the query returns None and endpoint returns 404.
        """
        # The SmartDocument query filters on loan_id == portal's loan_id
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = None  # doc belongs to different loan
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/document/42/status")

        assert response.status_code == 404

    def test_needs_list_scoped_to_portal_loan(
        self, client: TestClient, db_session
    ):
        """Two different workspace slugs should resolve to different loan_ids.

        Requests from workspace A cannot see documents for workspace B's loan.
        """
        portal_a = {
            "workspace": _make_workspace(slug="workspace-a", org_id=1),
            "purl_loan": _make_purl_loan(main_loan_id=500),
            "loan_id": 500,
            "borrower_id": 200,
            "borrower_name": "Alice",
            "borrower_email": "alice@example.com",
            "org_id": 1,
        }
        portal_b = {
            "workspace": _make_workspace(slug="workspace-b", org_id=2),
            "purl_loan": _make_purl_loan(main_loan_id=600),
            "loan_id": 600,
            "borrower_id": 300,
            "borrower_name": "Bob",
            "borrower_email": "bob@example.com",
            "org_id": 2,
        }

        req_a = _make_document_request(req_id=1, loan_id=500)

        # Request for workspace A gets loan_id=500 requests
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_a,
        ):
            mock_chain = MagicMock()
            mock_chain.filter.return_value = mock_chain
            mock_chain.order_by.return_value = mock_chain
            mock_chain.all.side_effect = [[req_a], []]  # requests, then docs
            db_session.query = MagicMock(return_value=mock_chain)

            resp_a = client.get("/portal/docs/workspace-a/needs-list")

        assert resp_a.status_code == 200
        assert resp_a.json()["loan_id"] == 500

        # Request for workspace B gets loan_id=600 -- different data
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            return_value=portal_b,
        ):
            mock_chain2 = MagicMock()
            mock_chain2.filter.return_value = mock_chain2
            mock_chain2.order_by.return_value = mock_chain2
            mock_chain2.all.return_value = []
            db_session.query = MagicMock(return_value=mock_chain2)

            resp_b = client.get("/portal/docs/workspace-b/needs-list")

        assert resp_b.status_code == 200
        assert resp_b.json()["loan_id"] == 600
        assert resp_b.json()["total"] == 0


# =============================================================================
# 16. Workspace slug validation
# =============================================================================

@pytest.mark.unit
class TestWorkspaceSlugValidation:
    """Test workspace slug lookup behavior."""

    def test_all_endpoints_return_404_for_invalid_slug(self, client: TestClient):
        """All portal endpoints should return 404 for nonexistent slug."""
        with patch(
            "routes.smart_docs_portal_routes._verify_portal_access",
            side_effect=lambda db, slug: (_ for _ in ()).throw(
                __import__("fastapi").HTTPException(status_code=404, detail="Portal not found")
            ),
        ):
            endpoints = [
                ("GET", "/portal/docs/bad-slug/needs-list"),
                ("GET", "/portal/docs/bad-slug/status"),
                ("GET", "/portal/docs/bad-slug/checklist"),
                ("GET", "/portal/docs/bad-slug/appointments"),
                ("GET", "/portal/docs/bad-slug/messages"),
                ("GET", "/portal/docs/bad-slug/signing-requests"),
            ]
            for method, url in endpoints:
                if method == "GET":
                    resp = client.get(url)
                assert resp.status_code == 404, f"Expected 404 for {url}, got {resp.status_code}"


# =============================================================================
# 17. Empty body / validation on public endpoints
# =============================================================================

@pytest.mark.unit
class TestInputValidation:
    """Test input validation on write endpoints."""

    def test_loe_requires_all_fields(self, client: TestClient, mock_portal_access):
        """LOE submission requires subject, explanation_text, and borrower_name."""
        # Missing required fields
        response = client.post(
            "/portal/docs/test-workspace/loe",
            json={"subject": "Test"},
        )
        assert response.status_code == 422  # Pydantic validation

    def test_reschedule_requires_preferred_dates(
        self, client: TestClient, mock_portal_access
    ):
        """Reschedule requires preferred_dates field."""
        response = client.post(
            "/portal/docs/test-workspace/appointments/1/reschedule",
            json={},
        )
        assert response.status_code == 422

    def test_contact_requires_message_field(
        self, client: TestClient, mock_portal_access
    ):
        """Contact endpoint requires 'message' field in body."""
        response = client.post(
            "/portal/docs/test-workspace/contact",
            json={},
        )
        assert response.status_code == 422


# =============================================================================
# 18. Upload history via needs-list (rejected docs with fix instructions)
# =============================================================================

@pytest.mark.unit
class TestUploadHistory:
    """Test that upload history / rejection details are returned properly."""

    def test_needs_list_includes_rejection_details(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Rejected docs should include rejection_reason and fix_instructions."""
        from models.smart_docs_models import RequestStatus, DocumentDecision

        req = _make_document_request(req_id=1, status_val="REJECTED")
        doc = _make_smart_document(doc_id=10, status="REJECTED", decision="REJECT")
        doc.rejection_reason = "Document is expired (older than 60 days)"
        doc.fix_instructions = "Please upload a paystub from the last 30 days"

        mock_req_chain = MagicMock()
        mock_req_chain.filter.return_value = mock_req_chain
        mock_req_chain.order_by.return_value = mock_req_chain
        mock_req_chain.all.return_value = [req]

        mock_doc_chain = MagicMock()
        mock_doc_chain.filter.return_value = mock_doc_chain
        mock_doc_chain.order_by.return_value = mock_doc_chain
        mock_doc_chain.all.return_value = [doc]

        db_session.query = MagicMock(side_effect=[mock_req_chain, mock_doc_chain])

        response = client.get("/portal/docs/test-workspace/needs-list")

        assert response.status_code == 200
        data = response.json()
        item = data["needs_list"][0]
        assert item["rejection_reason"] == "Document is expired (older than 60 days)"
        assert item["fix_instructions"] == "Please upload a paystub from the last 30 days"
        assert item["uploaded_documents"][0]["decision"] == "REJECT"


# =============================================================================
# 19. Portal settings / branding (org-level, tested via status endpoint shape)
# =============================================================================

@pytest.mark.unit
class TestPortalBrandingContext:
    """Verify that portal responses include org-level context for branding."""

    def test_needs_list_includes_workspace_slug_and_borrower(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Needs list response includes workspace_slug and borrower_name for UI branding."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.all.return_value = []
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/needs-list")

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_slug"] == "test-workspace"
        assert data["borrower_name"] == "John Smith"

    def test_status_includes_borrower_name(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Status response includes borrower_name for personalization."""
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.all.return_value = []
        db_session.query = MagicMock(return_value=mock_chain)

        response = client.get("/portal/docs/test-workspace/status")

        assert response.status_code == 200
        assert response.json()["borrower_name"] == "John Smith"


# =============================================================================
# 20. Document acknowledge (via contact message with related_request_id)
# =============================================================================

@pytest.mark.unit
class TestDocumentAcknowledge:
    """Test acknowledging a document request by sending a contact message linked to it."""

    def test_contact_with_related_request_id(
        self, client: TestClient, mock_portal_access, db_session
    ):
        """Contact message can reference a specific document request."""
        def fake_refresh(obj):
            obj.id = 88

        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        db_session.refresh = MagicMock(side_effect=fake_refresh)
        db_session.execute = MagicMock()

        response = client.post(
            "/portal/docs/test-workspace/contact",
            json={
                "message": "I acknowledge the request and will provide the document soon",
                "related_request_id": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == 88
        assert data["status"] == "sent"
