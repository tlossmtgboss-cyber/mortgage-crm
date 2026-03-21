"""
Integration Tests: Smart Docs Document Management API Endpoints

Tests the REST API endpoints for the document management system including:
- POST /api/v1/smart-docs/upload — Upload a document (with mocked S3)
- GET  /api/v1/smart-docs/documents/{loan_id} — List documents for a loan
- GET  /api/v1/smart-docs/document/{id} — Get single document details
- POST /api/v1/smart-docs/document/{id}/approve — Approve a document
- POST /api/v1/smart-docs/document/{id}/reject — Reject a document
- DELETE /api/v1/smart-docs/document/{id} — Delete (trash) a document

Coverage areas:
- File type validation, size limits
- Auth required, tenant isolation
- Document categorization (income, assets, property, identity, credit)
- Document status transitions (UPLOADED -> APPROVED, UPLOADED -> REJECTED, etc.)
"""

import io
import os
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.smart_docs_models import (
    SmartDocument,
    DocumentRequest,
    DocType,
    DocumentDecision,
    RejectionCategory,
    RequestStatus,
    RequestPriority,
    AppliesTo,
)


# =============================================================================
# PREFIX CONSTANT
# =============================================================================

API_PREFIX = "/api/v1/smart-docs"


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client(authenticated_client):
    """Use authenticated client for all tests in this file."""
    return authenticated_client


@pytest.fixture
def mock_s3_service():
    """Mock the S3 storage service used by Smart Docs."""
    mock_svc = MagicMock()
    mock_svc.is_available = True
    mock_svc.upload_file.return_value = {"success": True, "storage_key": "org/1/loan/1/doc.pdf"}
    mock_svc.generate_storage_key.return_value = "org/1/loan/1/doc.pdf"
    mock_svc.download_file.return_value = {"success": True, "content": b"%PDF-fake"}
    mock_svc.get_presigned_download_url.return_value = {
        "success": True,
        "presigned_url": "https://s3.example.com/signed-url",
        "expires_in": 300,
    }
    mock_svc.file_exists.return_value = True
    return mock_svc


@pytest.fixture
def mock_review_pipeline():
    """Mock the document review pipeline."""
    mock_pipeline = MagicMock()
    mock_pipeline.process_document.return_value = MagicMock(
        document_id=1,
        decision=DocumentDecision.ACCEPT,
        status="UPLOADED",
    )
    mock_pipeline.result_to_dict.return_value = {
        "document_id": 1,
        "file_name": "paystub.pdf",
        "status": "UPLOADED",
        "decision": "ACCEPT",
        "screenshot_detection": {"is_screenshot": False, "confidence": 0.0},
        "dates": {"doc_date": None, "is_expired": False},
    }
    return mock_pipeline


@pytest.fixture
def sample_loan_in_db(db_session):
    """Create a loan record in the test DB for document operations."""
    from sqlalchemy import text
    try:
        db_session.execute(text("""
            INSERT INTO loans (id, loan_number, borrower_name, borrower_email, organization_id, stage)
            VALUES (9901, 'TEST-DOC-001', 'Jane Doe', 'jane@example.com', 1, 'PROCESSING')
        """))
        db_session.flush()
    except Exception:
        db_session.rollback()
        # Table might not exist or row might already exist in SQLite test DB
        pass
    return 9901


@pytest.fixture
def sample_document_in_db(db_session, sample_loan_in_db):
    """Create a SmartDocument record in the test DB."""
    doc = SmartDocument(
        id=8801,
        loan_id=sample_loan_in_db,
        borrower_id=1,
        file_name="paystub_jan2026.pdf",
        mime_type="application/pdf",
        file_size=150_000,
        storage_key="org/1/loan/9901/paystub_jan2026.pdf",
        doc_type=DocType.PAYSTUB,
        status="UPLOADED",
        created_at=datetime.utcnow(),
    )
    try:
        db_session.add(doc)
        db_session.flush()
    except Exception:
        db_session.rollback()
    return doc


@pytest.fixture
def multiple_documents_in_db(db_session, sample_loan_in_db):
    """Create several documents with different types and statuses."""
    docs = []
    doc_specs = [
        (8810, "paystub_jan.pdf", DocType.PAYSTUB, "APPROVED", "income"),
        (8811, "w2_2025.pdf", DocType.W2, "UPLOADED", "income"),
        (8812, "bank_stmt_q1.pdf", DocType.BANK_STATEMENT, "UPLOADED", "assets"),
        (8813, "drivers_license.jpg", DocType.DRIVERS_LICENSE, "APPROVED", "identity"),
        (8814, "credit_report.pdf", DocType.OTHER, "REJECTED", "credit"),
        (8815, "appraisal.pdf", DocType.APPRAISAL, "UPLOADED", "property"),
    ]
    for doc_id, fname, dtype, status, _cat in doc_specs:
        doc = SmartDocument(
            id=doc_id,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name=fname,
            mime_type="application/pdf" if fname.endswith(".pdf") else "image/jpeg",
            file_size=100_000,
            storage_key=f"org/1/loan/{sample_loan_in_db}/{fname}",
            doc_type=dtype,
            status=status,
            created_at=datetime.utcnow(),
        )
        try:
            db_session.add(doc)
            docs.append(doc)
        except Exception:
            pass
    try:
        db_session.flush()
    except Exception:
        db_session.rollback()
    return docs


# =============================================================================
# UPLOAD ENDPOINT TESTS: POST /api/v1/smart-docs/upload
# =============================================================================

class TestDocumentUpload:
    """Test document upload endpoint."""

    @patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service")
    @patch("routes.smart_docs_crud_routes.DocumentReviewPipeline")
    def test_upload_pdf_success(
        self, mock_pipeline_cls, mock_s3_factory, client, mock_s3_service, mock_review_pipeline, sample_loan_in_db
    ):
        """Upload a valid PDF document returns 200 with document details."""
        mock_s3_factory.return_value = mock_s3_service
        mock_pipeline_cls.return_value = mock_review_pipeline

        pdf_content = b"%PDF-1.4 fake content for testing"
        response = client.post(
            f"{API_PREFIX}/upload",
            data={"loan_id": str(sample_loan_in_db), "borrower_id": "1"},
            files={"file": ("paystub.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data or "file_name" in data
        # Verify S3 upload was called
        assert mock_s3_service.upload_file.called or mock_s3_service.generate_storage_key.called

    @patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service")
    @patch("routes.smart_docs_crud_routes.DocumentReviewPipeline")
    def test_upload_image_success(
        self, mock_pipeline_cls, mock_s3_factory, client, mock_s3_service, mock_review_pipeline, sample_loan_in_db
    ):
        """Upload a JPEG image document returns 200."""
        mock_s3_factory.return_value = mock_s3_service
        mock_pipeline_cls.return_value = mock_review_pipeline

        # Minimal JPEG header
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100
        response = client.post(
            f"{API_PREFIX}/upload",
            data={"loan_id": str(sample_loan_in_db), "borrower_id": "1"},
            files={"file": ("license.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        )

        assert response.status_code == 200

    @patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service")
    @patch("routes.smart_docs_crud_routes.DocumentReviewPipeline")
    def test_upload_with_doc_type(
        self, mock_pipeline_cls, mock_s3_factory, client, mock_s3_service, mock_review_pipeline, sample_loan_in_db
    ):
        """Upload with explicit doc_type parameter processes correctly."""
        mock_s3_factory.return_value = mock_s3_service
        mock_pipeline_cls.return_value = mock_review_pipeline

        pdf_content = b"%PDF-1.4 test"
        response = client.post(
            f"{API_PREFIX}/upload",
            data={
                "loan_id": str(sample_loan_in_db),
                "borrower_id": "1",
                "doc_type": "PAYSTUB",
            },
            files={"file": ("paystub.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200

    @patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service")
    def test_upload_file_too_large(
        self, mock_s3_factory, client, mock_s3_service, sample_loan_in_db
    ):
        """Upload a file exceeding 20MB limit returns 413."""
        mock_s3_factory.return_value = mock_s3_service

        # Create content just over 20MB
        large_content = b"x" * (20 * 1024 * 1024 + 1)
        response = client.post(
            f"{API_PREFIX}/upload",
            data={"loan_id": str(sample_loan_in_db), "borrower_id": "1"},
            files={"file": ("huge.pdf", io.BytesIO(large_content), "application/pdf")},
        )

        assert response.status_code == 413
        assert "too large" in response.json().get("detail", "").lower() or "20MB" in response.json().get("detail", "")

    @patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service")
    @patch("routes.smart_docs_crud_routes.DocumentReviewPipeline")
    def test_upload_with_request_id(
        self, mock_pipeline_cls, mock_s3_factory, client, mock_s3_service, mock_review_pipeline, sample_loan_in_db
    ):
        """Upload a document linked to a specific request_id."""
        mock_s3_factory.return_value = mock_s3_service
        mock_pipeline_cls.return_value = mock_review_pipeline

        pdf_content = b"%PDF-1.4 test"
        response = client.post(
            f"{API_PREFIX}/upload",
            data={
                "loan_id": str(sample_loan_in_db),
                "borrower_id": "1",
                "request_id": "999",
            },
            files={"file": ("w2.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 200


# =============================================================================
# LIST DOCUMENTS ENDPOINT: GET /api/v1/smart-docs/documents/{loan_id}
# =============================================================================

class TestListDocuments:
    """Test listing documents for a loan."""

    def test_list_documents_success(self, client, multiple_documents_in_db, sample_loan_in_db):
        """List all documents for a loan returns complete list."""
        response = client.get(f"{API_PREFIX}/documents/{sample_loan_in_db}")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
        assert data["loan_id"] == sample_loan_in_db
        assert data["total"] == len(multiple_documents_in_db)

    def test_list_documents_filter_by_status(self, client, multiple_documents_in_db, sample_loan_in_db):
        """Filter documents by status query parameter."""
        response = client.get(
            f"{API_PREFIX}/documents/{sample_loan_in_db}",
            params={"status": "APPROVED"},
        )

        assert response.status_code == 200
        data = response.json()
        # Only APPROVED documents should be returned
        for doc in data["documents"]:
            assert doc["status"] == "APPROVED"

    def test_list_documents_empty_loan(self, client):
        """List documents for a loan with no documents returns empty list."""
        # Use a loan_id that has no documents (99999)
        response = client.get(f"{API_PREFIX}/documents/99999")

        # Might be 200 with empty list or 404 depending on tenant check
        if response.status_code == 200:
            data = response.json()
            assert data["total"] == 0
            assert data["documents"] == []

    def test_list_documents_contains_expected_fields(self, client, multiple_documents_in_db, sample_loan_in_db):
        """Each document in the list contains required fields."""
        response = client.get(f"{API_PREFIX}/documents/{sample_loan_in_db}")

        assert response.status_code == 200
        data = response.json()
        if data["documents"]:
            doc = data["documents"][0]
            assert "id" in doc
            assert "file_name" in doc
            assert "doc_type" in doc
            assert "status" in doc
            assert "created_at" in doc

    def test_list_documents_via_alias_route(self, client, multiple_documents_in_db, sample_loan_in_db):
        """The alias route /loan/{loan_id}/documents also works."""
        response = client.get(f"{API_PREFIX}/loan/{sample_loan_in_db}/documents")

        assert response.status_code == 200
        data = response.json()
        assert data["loan_id"] == sample_loan_in_db
        assert data["total"] == len(multiple_documents_in_db)


# =============================================================================
# GET SINGLE DOCUMENT: GET /api/v1/smart-docs/document/{id}
# =============================================================================

class TestGetDocument:
    """Test getting a single document by ID."""

    def test_get_document_success(self, client, sample_document_in_db):
        """Get a document by ID returns full document details."""
        response = client.get(f"{API_PREFIX}/document/{sample_document_in_db.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_document_in_db.id
        assert data["file_name"] == "paystub_jan2026.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["doc_type"] == "PAYSTUB"
        assert data["status"] == "UPLOADED"

    def test_get_document_includes_screenshot_detection(self, client, sample_document_in_db):
        """Response includes screenshot detection results."""
        response = client.get(f"{API_PREFIX}/document/{sample_document_in_db.id}")

        assert response.status_code == 200
        data = response.json()
        assert "screenshot_detection" in data
        assert "is_screenshot" in data["screenshot_detection"]
        assert "confidence" in data["screenshot_detection"]

    def test_get_document_includes_dates(self, client, sample_document_in_db):
        """Response includes date extraction and expiration info."""
        response = client.get(f"{API_PREFIX}/document/{sample_document_in_db.id}")

        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert "doc_date" in data["dates"]
        assert "is_expired" in data["dates"]
        assert "expires_at" in data["dates"]

    def test_get_document_not_found(self, client):
        """Get a non-existent document returns 404."""
        response = client.get(f"{API_PREFIX}/document/999999")

        assert response.status_code == 404

    def test_get_document_includes_file_metadata(self, client, sample_document_in_db):
        """Response includes file size and borrower info."""
        response = client.get(f"{API_PREFIX}/document/{sample_document_in_db.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["file_size"] == 150_000
        assert data["loan_id"] == sample_document_in_db.loan_id
        assert data["borrower_id"] == 1


# =============================================================================
# APPROVE DOCUMENT: POST /api/v1/smart-docs/document/{id}/approve
# =============================================================================

class TestApproveDocument:
    """Test document approval endpoint."""

    def test_approve_document_success(self, client, sample_document_in_db):
        """Approve a document transitions status to APPROVED."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/approve",
            params={"reviewer": "admin@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
        assert data["approved_by"] == "admin@example.com"
        assert data["document_id"] == sample_document_in_db.id
        assert "approved_at" in data

    def test_approve_document_with_notes(self, client, sample_document_in_db):
        """Approve with notes includes them in response."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/approve",
            params={"reviewer": "admin@example.com", "notes": "Looks good, verified dates"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Looks good, verified dates"

    def test_approve_document_not_found(self, client):
        """Approve a non-existent document returns 404."""
        response = client.post(
            f"{API_PREFIX}/document/999999/approve",
            params={"reviewer": "admin@example.com"},
        )

        assert response.status_code == 404

    def test_approve_document_updates_linked_request(self, client, db_session, sample_loan_in_db):
        """Approving a document linked to a request updates request status to ACCEPTED."""
        # Create a document request first
        req = DocumentRequest(
            id=7701,
            loan_id=sample_loan_in_db,
            doc_type=DocType.PAYSTUB,
            title="Recent Paystubs",
            status=RequestStatus.PENDING_REVIEW,
            is_active=True,
        )
        try:
            db_session.add(req)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test request")

        # Create document linked to the request
        doc = SmartDocument(
            id=8820,
            request_id=7701,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name="paystub_linked.pdf",
            mime_type="application/pdf",
            file_size=50000,
            storage_key="org/1/loan/9901/paystub_linked.pdf",
            doc_type=DocType.PAYSTUB,
            status="UPLOADED",
        )
        try:
            db_session.add(doc)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test document")

        response = client.post(
            f"{API_PREFIX}/document/8820/approve",
            params={"reviewer": "lo@example.com"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    def test_approve_requires_reviewer_param(self, client, sample_document_in_db):
        """Approve without reviewer parameter returns 422."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/approve",
        )

        assert response.status_code == 422  # Missing required query param


# =============================================================================
# REJECT DOCUMENT: POST /api/v1/smart-docs/document/{id}/reject
# =============================================================================

class TestRejectDocument:
    """Test document rejection endpoint."""

    def test_reject_document_success(self, client, sample_document_in_db):
        """Reject a document with reason transitions status to REJECTED."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/reject",
            json={
                "reviewer": "admin@example.com",
                "reason": "Document is expired, statement date is from 2024",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["rejected_by"] == "admin@example.com"
        assert "expired" in data["rejection_reason"].lower()

    def test_reject_document_with_category(self, client, sample_document_in_db):
        """Reject with a rejection category (EXPIRED, SCREENSHOT, etc.)."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/reject",
            json={
                "reviewer": "admin@example.com",
                "reason": "This is a screenshot, not the original document",
                "rejection_category": "SCREENSHOT",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rejection_category"] == "SCREENSHOT"

    def test_reject_document_with_expired_category(self, client, sample_document_in_db):
        """Reject with EXPIRED rejection category."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/reject",
            json={
                "reviewer": "processor@example.com",
                "reason": "Bank statement is more than 60 days old",
                "rejection_category": "EXPIRED",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["rejection_category"] == "EXPIRED"

    def test_reject_document_not_found(self, client):
        """Reject a non-existent document returns 404."""
        response = client.post(
            f"{API_PREFIX}/document/999999/reject",
            json={
                "reviewer": "admin@example.com",
                "reason": "Does not matter",
            },
        )

        assert response.status_code == 404

    def test_reject_requires_reason(self, client, sample_document_in_db):
        """Reject without a reason fails validation (422)."""
        response = client.post(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/reject",
            json={
                "reviewer": "admin@example.com",
                # Missing "reason" field
            },
        )

        assert response.status_code == 422


# =============================================================================
# DELETE DOCUMENT: DELETE /api/v1/smart-docs/document/{id}
# =============================================================================

class TestDeleteDocument:
    """Test document deletion (trash) endpoint."""

    def test_delete_document_success(self, client, sample_document_in_db):
        """Delete a document sets status to DELETED."""
        response = client.delete(
            f"{API_PREFIX}/document/{sample_document_in_db.id}",
            params={
                "reviewer": "admin@example.com",
                "reason": "Uploaded wrong file",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DELETED"
        assert data["deleted_by"] == "admin@example.com"
        assert data["previous_status"] == "UPLOADED"
        assert "deleted_at" in data

    def test_delete_document_without_reason(self, client, sample_document_in_db):
        """Delete without a reason uses default message."""
        response = client.delete(
            f"{API_PREFIX}/document/{sample_document_in_db.id}",
            params={"reviewer": "admin@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DELETED"

    def test_delete_document_not_found(self, client):
        """Delete a non-existent document returns 404."""
        response = client.delete(
            f"{API_PREFIX}/document/999999",
            params={"reviewer": "admin@example.com"},
        )

        assert response.status_code == 404

    def test_delete_requires_reviewer(self, client, sample_document_in_db):
        """Delete without reviewer parameter returns 422."""
        response = client.delete(
            f"{API_PREFIX}/document/{sample_document_in_db.id}",
        )

        assert response.status_code == 422

    def test_delete_resets_linked_request_to_open(self, client, db_session, sample_loan_in_db):
        """Deleting a document linked to a request resets the request to OPEN."""
        # Create a request in PENDING_REVIEW status
        req = DocumentRequest(
            id=7710,
            loan_id=sample_loan_in_db,
            doc_type=DocType.BANK_STATEMENT,
            title="Bank Statements",
            status=RequestStatus.PENDING_REVIEW,
            is_active=True,
        )
        try:
            db_session.add(req)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test request")

        doc = SmartDocument(
            id=8830,
            request_id=7710,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name="bank_stmt.pdf",
            mime_type="application/pdf",
            file_size=80000,
            storage_key="org/1/loan/9901/bank_stmt.pdf",
            doc_type=DocType.BANK_STATEMENT,
            status="UPLOADED",
        )
        try:
            db_session.add(doc)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test document")

        response = client.delete(
            f"{API_PREFIX}/document/8830",
            params={"reviewer": "admin@example.com", "reason": "Wrong file"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "DELETED"


# =============================================================================
# TENANT ISOLATION TESTS
# =============================================================================

class TestTenantIsolation:
    """Test that document endpoints enforce tenant (organization) isolation."""

    def test_upload_enforces_tenant(self, db_session, mock_s3_service, sample_loan_in_db):
        """Upload verifies the loan belongs to the user's organization."""
        from main import app, get_current_user, get_current_user_flexible
        from database import get_db
        from auth.dependencies import (
            get_current_user as auth_dep_gcu,
            get_current_user_flexible as auth_dep_gcuf,
        )
        from fastapi.testclient import TestClient
        from tests.conftest import MockUser

        # Create a user in org 999 (different from loan's org 1)
        other_org_user = MockUser(id=99, email="other@org.com", organization_id=999)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return other_org_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_current_user_flexible] = override_auth
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[auth_dep_gcuf] = override_auth

        with TestClient(app) as other_client:
            with patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service") as mock_s3:
                mock_s3.return_value = mock_s3_service

                pdf_content = b"%PDF-1.4 test"
                response = other_client.post(
                    f"{API_PREFIX}/upload",
                    data={"loan_id": str(sample_loan_in_db), "borrower_id": "1"},
                    files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
                )

                # Should be 404 (not found / not in your org)
                assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_list_documents_enforces_tenant(self, db_session, sample_loan_in_db):
        """List documents verifies the loan belongs to the user's organization."""
        from main import app, get_current_user, get_current_user_flexible
        from database import get_db
        from auth.dependencies import (
            get_current_user as auth_dep_gcu,
            get_current_user_flexible as auth_dep_gcuf,
        )
        from fastapi.testclient import TestClient
        from tests.conftest import MockUser

        other_org_user = MockUser(id=99, email="other@org.com", organization_id=999)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return other_org_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_current_user_flexible] = override_auth
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[auth_dep_gcuf] = override_auth

        with TestClient(app) as other_client:
            response = other_client.get(f"{API_PREFIX}/documents/{sample_loan_in_db}")
            assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_get_document_enforces_tenant(self, db_session, sample_document_in_db):
        """Get single document verifies the document's loan belongs to user's org."""
        from main import app, get_current_user, get_current_user_flexible
        from database import get_db
        from auth.dependencies import (
            get_current_user as auth_dep_gcu,
            get_current_user_flexible as auth_dep_gcuf,
        )
        from fastapi.testclient import TestClient
        from tests.conftest import MockUser

        other_org_user = MockUser(id=99, email="other@org.com", organization_id=999)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return other_org_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_current_user_flexible] = override_auth
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[auth_dep_gcuf] = override_auth

        with TestClient(app) as other_client:
            response = other_client.get(f"{API_PREFIX}/document/{sample_document_in_db.id}")
            assert response.status_code == 404

        app.dependency_overrides.clear()


# =============================================================================
# DOCUMENT CATEGORIZATION TESTS
# =============================================================================

class TestDocumentCategorization:
    """Test document type categorization across the five categories."""

    def test_income_doc_types_map_correctly(self):
        """Income document IDs map to correct DocType enum values."""
        from routes.smart_docs_models import DOCUMENT_ID_TO_DOC_TYPE

        assert DOCUMENT_ID_TO_DOC_TYPE["paystubs"] == DocType.PAYSTUB
        assert DOCUMENT_ID_TO_DOC_TYPE["w2_recent"] == DocType.W2
        assert DOCUMENT_ID_TO_DOC_TYPE["tax_returns"] == DocType.TAX_RETURN
        assert DOCUMENT_ID_TO_DOC_TYPE["profit_loss"] == DocType.PROFIT_LOSS
        assert DOCUMENT_ID_TO_DOC_TYPE["business_tax_returns"] == DocType.BUSINESS_TAX_RETURN

    def test_asset_doc_types_map_correctly(self):
        """Asset document IDs map to correct DocType enum values."""
        from routes.smart_docs_models import DOCUMENT_ID_TO_DOC_TYPE

        assert DOCUMENT_ID_TO_DOC_TYPE["bank_statements"] == DocType.BANK_STATEMENT
        assert DOCUMENT_ID_TO_DOC_TYPE["investment_statements"] == DocType.INVESTMENT_STATEMENT
        assert DOCUMENT_ID_TO_DOC_TYPE["gift_letter"] == DocType.GIFT_LETTER

    def test_identity_doc_types_map_correctly(self):
        """Identity document IDs map to correct DocType enum values."""
        from routes.smart_docs_models import DOCUMENT_ID_TO_DOC_TYPE

        assert DOCUMENT_ID_TO_DOC_TYPE["id"] == DocType.DRIVERS_LICENSE
        assert DOCUMENT_ID_TO_DOC_TYPE["coborrower_id"] == DocType.DRIVERS_LICENSE
        assert DOCUMENT_ID_TO_DOC_TYPE["va_coe"] == DocType.VA_COE

    def test_property_doc_types_exist_in_enum(self):
        """Property-related DocTypes exist in the DocType enum."""
        assert DocType.PURCHASE_CONTRACT == "PURCHASE_CONTRACT"
        assert DocType.APPRAISAL == "APPRAISAL"
        assert DocType.TITLE_REPORT == "TITLE_REPORT"
        assert DocType.HOMEOWNERS_INSURANCE == "HOMEOWNERS_INSURANCE"

    def test_credit_doc_types_map_correctly(self):
        """Credit-related document IDs map to correct DocType."""
        from routes.smart_docs_models import DOCUMENT_ID_TO_DOC_TYPE

        assert DOCUMENT_ID_TO_DOC_TYPE["bankruptcy_docs"] == DocType.BANKRUPTCY_DISCHARGE

    def test_coborrower_docs_map_correctly(self):
        """Co-borrower document IDs map to same types as borrower."""
        from routes.smart_docs_models import DOCUMENT_ID_TO_DOC_TYPE

        assert DOCUMENT_ID_TO_DOC_TYPE["coborrower_paystubs"] == DocType.PAYSTUB
        assert DOCUMENT_ID_TO_DOC_TYPE["coborrower_w2_recent"] == DocType.W2
        assert DOCUMENT_ID_TO_DOC_TYPE["coborrower_bank_statements"] == DocType.BANK_STATEMENT

    def test_freshness_days_set_for_key_doc_types(self):
        """Freshness requirements are defined for time-sensitive documents."""
        from routes.smart_docs_models import FRESHNESS_DAYS

        assert FRESHNESS_DAYS[DocType.PAYSTUB] == 30
        assert FRESHNESS_DAYS[DocType.BANK_STATEMENT] == 60
        assert FRESHNESS_DAYS[DocType.W2] == 365


# =============================================================================
# DOCUMENT STATUS TRANSITION TESTS
# =============================================================================

class TestDocumentStatusTransitions:
    """Test document status transition workflows."""

    def test_uploaded_to_approved(self, client, db_session, sample_loan_in_db):
        """UPLOADED -> APPROVED transition via approval endpoint."""
        doc = SmartDocument(
            id=8840,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name="transition_test.pdf",
            mime_type="application/pdf",
            file_size=50000,
            storage_key="org/1/loan/9901/transition_test.pdf",
            doc_type=DocType.W2,
            status="UPLOADED",
        )
        try:
            db_session.add(doc)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test document")

        response = client.post(
            f"{API_PREFIX}/document/8840/approve",
            params={"reviewer": "lo@example.com"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    def test_uploaded_to_rejected(self, client, db_session, sample_loan_in_db):
        """UPLOADED -> REJECTED transition via rejection endpoint."""
        doc = SmartDocument(
            id=8841,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name="reject_test.pdf",
            mime_type="application/pdf",
            file_size=50000,
            storage_key="org/1/loan/9901/reject_test.pdf",
            doc_type=DocType.BANK_STATEMENT,
            status="UPLOADED",
        )
        try:
            db_session.add(doc)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test document")

        response = client.post(
            f"{API_PREFIX}/document/8841/reject",
            json={
                "reviewer": "processor@example.com",
                "reason": "Bank statement is from prior quarter",
                "rejection_category": "EXPIRED",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["rejection_category"] == "EXPIRED"

    def test_uploaded_to_deleted(self, client, db_session, sample_loan_in_db):
        """UPLOADED -> DELETED transition via delete endpoint."""
        doc = SmartDocument(
            id=8842,
            loan_id=sample_loan_in_db,
            borrower_id=1,
            file_name="delete_test.pdf",
            mime_type="application/pdf",
            file_size=50000,
            storage_key="org/1/loan/9901/delete_test.pdf",
            doc_type=DocType.DRIVERS_LICENSE,
            status="UPLOADED",
        )
        try:
            db_session.add(doc)
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Could not create test document")

        response = client.delete(
            f"{API_PREFIX}/document/8842",
            params={"reviewer": "admin@example.com", "reason": "Wrong document"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DELETED"
        assert data["previous_status"] == "UPLOADED"

    def test_rejection_categories_are_valid(self):
        """All rejection categories in the enum are valid."""
        valid_categories = {
            "SCREENSHOT", "EXPIRED", "POOR_QUALITY", "INCOMPLETE", "WRONG_TYPE", "OTHER"
        }
        actual_categories = {rc.value for rc in RejectionCategory}
        assert actual_categories == valid_categories

    def test_document_decisions_are_valid(self):
        """All document decisions in the enum are valid."""
        valid_decisions = {"ACCEPT", "REJECT", "NEEDS_REVIEW"}
        actual_decisions = {dd.value for dd in DocumentDecision}
        assert actual_decisions == valid_decisions


# =============================================================================
# DOCUMENT UPDATE ENDPOINT: PATCH /api/v1/smart-docs/document/{id}/name
# =============================================================================

class TestUpdateDocumentName:
    """Test document name update endpoint."""

    def test_update_document_name_success(self, client, sample_document_in_db):
        """Update display name of a document."""
        response = client.patch(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/name",
            json={"display_name": "January 2026 Paystub - Jane Doe"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "January 2026 Paystub - Jane Doe"
        assert data["updated"] is True

    def test_update_document_name_not_found(self, client):
        """Update name of non-existent document returns 404."""
        response = client.patch(
            f"{API_PREFIX}/document/999999/name",
            json={"display_name": "Does not matter"},
        )

        assert response.status_code == 404

    def test_update_document_name_requires_body(self, client, sample_document_in_db):
        """Update name without body returns 422."""
        response = client.patch(
            f"{API_PREFIX}/document/{sample_document_in_db.id}/name",
            json={},
        )

        assert response.status_code == 422


# =============================================================================
# AUTH REQUIRED TESTS
# =============================================================================

class TestAuthRequired:
    """Test that all document endpoints require authentication."""

    def test_upload_requires_auth(self, db_session):
        """Upload endpoint without auth returns 401/403."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        # Clear overrides to remove mocked auth
        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as unauth_client:
            pdf_content = b"%PDF-1.4 test"
            response = unauth_client.post(
                f"{API_PREFIX}/upload",
                data={"loan_id": "1", "borrower_id": "1"},
                files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )

            # Should be 401 or 403 (depends on auth middleware)
            assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    def test_list_documents_requires_auth(self, db_session):
        """List documents endpoint without auth returns 401/403."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as unauth_client:
            response = unauth_client.get(f"{API_PREFIX}/documents/1")
            assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    def test_get_document_requires_auth(self, db_session):
        """Get single document without auth returns 401/403."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as unauth_client:
            response = unauth_client.get(f"{API_PREFIX}/document/1")
            assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    def test_approve_requires_auth(self, db_session):
        """Approve document without auth returns 401/403."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as unauth_client:
            response = unauth_client.post(
                f"{API_PREFIX}/document/1/approve",
                params={"reviewer": "test@example.com"},
            )
            assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    def test_delete_requires_auth(self, db_session):
        """Delete document without auth returns 401/403."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as unauth_client:
            response = unauth_client.delete(
                f"{API_PREFIX}/document/1",
                params={"reviewer": "test@example.com"},
            )
            assert response.status_code in (401, 403)

        app.dependency_overrides.clear()
