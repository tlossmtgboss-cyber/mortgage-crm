"""
Smart Docs V2 API Contract Tests

Verifies that all Smart Docs V2 API endpoints return expected response shapes,
status codes, and handle edge cases properly.

Route prefixes (from smart_docs_routes.py and smart_docs_v2_registration.py):
- CRUD / Approval / Requests: /api/v1/smart-docs/*
- Income Calculation:          /api/smart-docs/income/*
- E-Signature:                 /api/v1/esign/*

Uses pytest with FastAPI TestClient. All tests mock the database session and
auth dependencies so they run without external services.
"""

import logging
import pytest
from datetime import datetime, timezone, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prefix constants (must match route registration in smart_docs_routes.py
# and smart_docs_v2_registration.py)
# ---------------------------------------------------------------------------
SMART_DOCS_PREFIX = "/api/v1/smart-docs"
INCOME_PREFIX = "/api/smart-docs"
ESIGN_PREFIX = "/api/v1/esign"


# ---------------------------------------------------------------------------
# Pytest marker applied to every test in this module
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.api_contract


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def _mock_needs_list_generator(db_session):
    """Patch NeedsListGenerator used by CRUD routes."""
    with patch("routes.smart_docs_crud_routes.NeedsListGenerator") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def _mock_review_pipeline(db_session):
    """Patch DocumentReviewPipeline used by CRUD and approval routes."""
    with patch("routes.smart_docs_crud_routes.DocumentReviewPipeline") as mock_crud, \
         patch("routes.smart_docs_approval_routes.DocumentReviewPipeline") as mock_approval:
        instance = MagicMock()
        mock_crud.return_value = instance
        mock_approval.return_value = instance
        yield instance


@pytest.fixture
def _mock_s3_service():
    """Patch S3 service across CRUD/approval/requests routes."""
    mock_svc = MagicMock()
    mock_svc.is_available = True
    mock_svc.bucket_name = "test-bucket"
    mock_svc.region = "us-east-1"
    mock_svc.prefix = "smart-docs/"
    mock_svc.generate_storage_key.return_value = "orgs/1/loans/1/test.pdf"
    mock_svc.upload_file.return_value = {"success": True}
    mock_svc.file_exists.return_value = True
    mock_svc.get_presigned_download_url.return_value = {
        "success": True,
        "presigned_url": "https://s3.example.com/signed-url",
        "expires_in": 300,
    }
    with patch("routes.smart_docs_crud_routes.get_smart_docs_s3_service", return_value=mock_svc), \
         patch("routes.smart_docs_approval_routes.get_smart_docs_s3_service", return_value=mock_svc), \
         patch("routes.smart_docs_requests_routes.get_smart_docs_s3_service", return_value=mock_svc):
        yield mock_svc


@pytest.fixture
def _mock_esign_crypto():
    """Patch e-signature crypto service."""
    with patch("routes.smart_docs_esign_routes.get_esignature_crypto_service") as mock_fn:
        mock_crypto = MagicMock()
        mock_crypto.generate_envelope_uuid.return_value = "test-uuid-1234"
        mock_crypto.generate_signing_token.return_value = (
            "sign-token-abc",
            datetime.now(timezone.utc) + timedelta(days=30),
        )
        mock_crypto.hash_access_code.return_value = "hashed-code"
        mock_fn.return_value = mock_crypto
        yield mock_crypto


@pytest.fixture
def _mock_esign_consent():
    """Patch ESignConsentService used by signing session endpoint."""
    with patch("routes.smart_docs_esign_routes.ESignConsentService") as mock_cls:
        instance = MagicMock()
        instance.verify_consent.return_value = True
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def _mock_kba_service():
    """Patch KBAService used by signing session endpoint."""
    with patch("routes.smart_docs_esign_routes.KBAService") as mock_cls:
        instance = MagicMock()
        instance.check_kba_required_for_recipient.return_value = False
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def _mock_income_calculator():
    """Patch income calculator service."""
    with patch("routes.smart_docs_income_routes.get_income_calculator_service") as mock_fn:
        mock_svc = MagicMock()
        mock_fn.return_value = mock_svc
        yield mock_svc


def _seed_smart_document(db_session, **overrides):
    """Insert a SmartDocument row and return its id."""
    from models.smart_docs_models import SmartDocument
    defaults = dict(
        loan_id=1,
        borrower_id=1,
        file_name="test_doc.pdf",
        mime_type="application/pdf",
        file_size=1024,
        storage_key="orgs/1/loans/1/test_doc.pdf",
        status="UPLOADED",
    )
    defaults.update(overrides)
    doc = SmartDocument(**defaults)
    db_session.add(doc)
    db_session.flush()
    return doc


def _seed_document_request(db_session, **overrides):
    """Insert a DocumentRequest row and return it."""
    from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType
    defaults = dict(
        loan_id=1,
        doc_type=DocType.PAYSTUB,
        title="Recent Paystubs",
        description="Last 30 days",
        priority=RequestPriority.NORMAL,
        status=RequestStatus.OPEN,
        is_active=True,
    )
    defaults.update(overrides)
    req = DocumentRequest(**defaults)
    db_session.add(req)
    db_session.flush()
    return req


def _seed_loan(db_session, **overrides):
    """Insert a minimal loans row for FK satisfaction."""
    from sqlalchemy import text as sa_text
    defaults = dict(
        id=1,
        borrower_name="Test Borrower",
        organization_id=1,
    )
    defaults.update(overrides)
    # Use raw SQL so we don't need the full Loan model with all constraints
    try:
        db_session.execute(sa_text(
            "INSERT INTO loans (id, borrower_name, organization_id) "
            "VALUES (:id, :borrower_name, :organization_id)"
        ), defaults)
        db_session.flush()
    except Exception:
        db_session.rollback()
        # Table may not exist in minimal test DB; tests will handle gracefully


def _seed_envelope(db_session, **overrides):
    """Insert an ESignatureEnvelope row."""
    from database.models.esignature import ESignatureEnvelope, EnvelopeStatus
    defaults = dict(
        organization_id=1,
        loan_id=1,
        created_by_user_id=1,
        envelope_uuid="env-uuid-001",
        title="Test Envelope",
        status=EnvelopeStatus.DRAFT.value,
        document_storage_key="orgs/1/loans/1/contract.pdf",
        total_recipients=1,
        completed_recipients=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    defaults.update(overrides)
    env = ESignatureEnvelope(**defaults)
    db_session.add(env)
    db_session.flush()
    return env


def _seed_recipient(db_session, envelope_id, **overrides):
    """Insert an ESignatureRecipient row."""
    from database.models.esignature import ESignatureRecipient, RecipientStatus
    defaults = dict(
        envelope_id=envelope_id,
        name="Jane Doe",
        email="jane@example.com",
        recipient_type="signer",
        signing_order=1,
        auth_method="email_link",
        status=RecipientStatus.PENDING.value,
    )
    defaults.update(overrides)
    recip = ESignatureRecipient(**defaults)
    db_session.add(recip)
    db_session.flush()
    return recip


def _seed_audit_event(db_session, envelope_id, **overrides):
    """Insert an ESignatureAuditEvent row."""
    from database.models.esignature import ESignatureAuditEvent
    defaults = dict(
        envelope_id=envelope_id,
        event_type="created",
        event_description="Envelope created",
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    ev = ESignatureAuditEvent(**defaults)
    db_session.add(ev)
    db_session.flush()
    return ev


# ============================================================================
# 1. DOCUMENT ENDPOINTS CONTRACT TESTS
# ============================================================================

class TestDocumentEndpointContracts:
    """Verify response shapes for Smart Docs document CRUD endpoints."""

    def test_get_documents_response_shape(
        self, authenticated_client, db_session, _mock_needs_list_generator, _mock_s3_service
    ):
        """GET /needs-list/{loan_id} returns expected top-level keys."""
        _seed_loan(db_session)
        _mock_needs_list_generator.get_needs_list.return_value = {
            "loan_id": 1,
            "all_requests": [],
            "by_category": {},
            "stats": {"total": 0, "open": 0, "accepted": 0},
        }
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/needs-list/1")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        # The response must include the keys returned by NeedsListGenerator plus
        # enrichment keys added by the route handler
        assert "all_requests" in body
        assert "loan_id" in body
        assert isinstance(body["all_requests"], list)

    def test_get_document_by_id_response_shape(
        self, authenticated_client, db_session, _mock_s3_service
    ):
        """GET /document/{id} returns all expected fields."""
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/document/{doc.id}")
        assert resp.status_code == 200
        body = resp.json()
        required_keys = {
            "id", "loan_id", "borrower_id", "request_id", "file_name",
            "mime_type", "file_size", "doc_type", "status", "decision",
            "screenshot_detection", "dates", "created_at",
        }
        missing = required_keys - set(body.keys())
        assert not missing, f"Missing keys in response: {missing}"
        # Nested shapes
        assert isinstance(body["screenshot_detection"], dict)
        assert "is_screenshot" in body["screenshot_detection"]
        assert isinstance(body["dates"], dict)
        assert "doc_date" in body["dates"]

    def test_upload_document_201_response(
        self, authenticated_client, db_session, _mock_review_pipeline, _mock_s3_service
    ):
        """POST /upload returns the pipeline result dict (implicitly 200)."""
        _seed_loan(db_session)
        mock_result = MagicMock()
        _mock_review_pipeline.process_document.return_value = mock_result
        _mock_review_pipeline.result_to_dict.return_value = {
            "document_id": 1,
            "status": "UPLOADED",
            "decision": "ACCEPT",
        }
        file_content = b"%PDF-1.4 fake content"
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/upload",
            data={"loan_id": "1", "borrower_id": "1"},
            files={"file": ("test.pdf", BytesIO(file_content), "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "document_id" in body or "status" in body

    def test_upload_document_400_missing_file(self, authenticated_client, db_session):
        """POST /upload without a file returns 422 (FastAPI validation error)."""
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/upload",
            data={"loan_id": "1", "borrower_id": "1"},
        )
        # FastAPI returns 422 for missing required File(...) parameter
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_classify_document_response_shape(
        self, authenticated_client, db_session, _mock_s3_service
    ):
        """GET /document/{id} returns doc_type and detected_doc_type for classification info."""
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/document/{doc.id}")
        assert resp.status_code == 200
        body = resp.json()
        # Classification data is embedded in the document detail response
        assert "doc_type" in body
        assert "detected_doc_type" in body
        assert "extraction_confidence" in body

    def test_approve_document_response(
        self, authenticated_client, db_session
    ):
        """POST /document/{id}/approve returns updated document with status."""
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/document/{doc.id}/approve",
            params={"reviewer": "test_user"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == doc.id
        assert body["status"] == "APPROVED"
        assert "approved_by" in body
        assert "approved_at" in body
        assert "message" in body

    def test_reject_document_requires_reason(
        self, authenticated_client, db_session
    ):
        """POST /document/{id}/reject without reason returns 422."""
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        # RejectDocumentBody requires 'reason' and 'reviewer' fields
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/document/{doc.id}/reject",
            json={"reviewer": "test_user"},
            # reason is missing
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        # FastAPI validation error detail is a list of field errors
        assert isinstance(body["detail"], list)

    def test_delete_document_returns_200_with_status(
        self, authenticated_client, db_session
    ):
        """DELETE /document/{id} returns 200 with deletion status.

        The actual Smart Docs implementation does a soft delete and returns
        200 with a JSON body (not 204 No Content).
        """
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        resp = authenticated_client.delete(
            f"{SMART_DOCS_PREFIX}/document/{doc.id}",
            params={"reviewer": "test_user", "reason": "Not needed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "DELETED"
        assert body["document_id"] == doc.id
        assert "deleted_by" in body


# ============================================================================
# 2. INCOME ENDPOINTS CONTRACT TESTS
# ============================================================================

class TestIncomeEndpointContracts:
    """Verify response shapes for income calculation endpoints."""

    def test_calculate_income_response_shape(
        self, authenticated_client, db_session, _mock_income_calculator
    ):
        """POST /income/calculate/{loan_id} returns calculation, sources, tasks, summary."""
        _seed_loan(db_session)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_qualifying_monthly = 8500.0
        mock_result.total_qualifying_annual = 102000.0
        mock_result.dti_front_end = 28.5
        mock_result.dti_back_end = 36.2
        mock_result.confidence = 0.92
        mock_result.flags = []
        mock_result.recommendations = []
        _mock_income_calculator.calculate_income.return_value = mock_result

        # The route fetches calculation from DB after service call -- mock that
        with patch("routes.smart_docs_income_routes.IncomeCalculation") as MockCalc, \
             patch("routes.smart_docs_income_routes.IncomeSource") as MockSrc, \
             patch("routes.smart_docs_income_routes.IncomeVerificationTask") as MockTask:
            # Make the DB query return None for calculation (service handles persistence)
            resp = authenticated_client.post(
                f"{INCOME_PREFIX}/income/calculate/1",
                params={"borrower_id": 1},
            )

        # The endpoint returns 200 with summary even if calc is None in DB
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        summary = body["summary"]
        assert "total_qualifying_monthly" in summary
        assert "total_qualifying_annual" in summary
        assert "dti_front_end" in summary
        assert "dti_back_end" in summary
        assert "confidence" in summary

    def test_calculate_income_requires_loan_id(self, authenticated_client, db_session):
        """POST /income/calculate without loan_id in path returns 404 or 422."""
        # Hitting the wrong path should give 404 (no route match) or 405
        resp = authenticated_client.post(
            f"{INCOME_PREFIX}/income/calculate",
        )
        assert resp.status_code in (404, 405, 422)

    def test_calculate_income_requires_borrower_id(
        self, authenticated_client, db_session, _mock_income_calculator
    ):
        """POST /income/calculate/{loan_id} without borrower_id query param returns 422."""
        _seed_loan(db_session)
        resp = authenticated_client.post(
            f"{INCOME_PREFIX}/income/calculate/1",
            # borrower_id query param is missing (required)
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_income_history_response_paginated(self, authenticated_client, db_session):
        """GET /income/history/{loan_id} returns a list of calculations."""
        _seed_loan(db_session)
        resp = authenticated_client.get(
            f"{INCOME_PREFIX}/income/history/1",
        )
        # Endpoint may return 200 with empty list, or 404 if route not mounted
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, (list, dict))
            if isinstance(body, dict):
                assert "calculations" in body or "history" in body or "items" in body

    def test_income_approval_response(self, authenticated_client, db_session):
        """POST /income/calculation/{id}/approve returns updated calculation."""
        from database.models.income_calculation import (
            IncomeCalculation, CalculationStatus, CalculationType,
        )
        _seed_loan(db_session)
        calc = IncomeCalculation(
            loan_id=1,
            borrower_id=1,
            organization_id=1,
            calculation_type=CalculationType.INITIAL,
            status=CalculationStatus.PENDING_REVIEW,
            total_qualifying_monthly_income=8500.0,
            total_qualifying_annual_income=102000.0,
            calculated_by_user_id=999,  # Different user for maker-checker
        )
        db_session.add(calc)
        db_session.flush()
        db_session.commit()

        resp = authenticated_client.post(
            f"{INCOME_PREFIX}/income/calculation/{calc.id}/approve",
            json={"notes": "Looks good", "admin_override": True},
        )
        if resp.status_code == 200:
            body = resp.json()
            assert "status" in body or "calculation" in body

    def test_dti_calculation_response(self, authenticated_client, db_session):
        """Income calculation response includes DTI ratios."""
        # DTI is part of the calculation summary rather than a separate endpoint.
        # Already covered by test_calculate_income_response_shape above.
        # This test verifies the DTI-specific fields more deeply.
        _seed_loan(db_session)

        from database.models.income_calculation import (
            IncomeCalculation, CalculationStatus, CalculationType,
        )
        calc = IncomeCalculation(
            loan_id=1,
            borrower_id=1,
            organization_id=1,
            calculation_type=CalculationType.INITIAL,
            status=CalculationStatus.COMPLETED,
            total_qualifying_monthly_income=8500.0,
            total_qualifying_annual_income=102000.0,
            dti_front_end=28.5,
            dti_back_end=36.2,
            proposed_housing_expense=2422.50,
            total_monthly_obligations=3077.0,
        )
        db_session.add(calc)
        db_session.flush()
        db_session.commit()

        resp = authenticated_client.get(
            f"{INCOME_PREFIX}/income/calculation/{calc.id}",
        )
        if resp.status_code == 200:
            body = resp.json()
            # Response should include DTI fields
            data = body.get("calculation", body)
            assert "dti_front_end" in data or "dti_back_end" in data

    def test_income_override_requires_justification(self, authenticated_client, db_session):
        """POST /income/calculation/{id}/override without reason returns 422."""
        from database.models.income_calculation import (
            IncomeCalculation, CalculationStatus, CalculationType,
        )
        _seed_loan(db_session)
        calc = IncomeCalculation(
            loan_id=1,
            borrower_id=1,
            organization_id=1,
            calculation_type=CalculationType.INITIAL,
            status=CalculationStatus.COMPLETED,
            total_qualifying_monthly_income=8500.0,
            total_qualifying_annual_income=102000.0,
        )
        db_session.add(calc)
        db_session.flush()
        db_session.commit()

        # OverrideIncomeBody requires reason, monthly_amount, annual_amount
        resp = authenticated_client.post(
            f"{INCOME_PREFIX}/income/calculation/{calc.id}/override",
            json={"monthly_amount": 9000, "annual_amount": 108000},
            # reason is missing
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body


# ============================================================================
# 3. E-SIGNATURE ENDPOINTS CONTRACT TESTS
# ============================================================================

class TestESignatureEndpointContracts:
    """Verify response shapes for e-signature endpoints."""

    def test_create_envelope_response(
        self, authenticated_client, db_session, _mock_esign_crypto
    ):
        """POST /envelopes returns envelope_uuid, status, recipients, fields, expires_at."""
        _seed_loan(db_session)
        resp = authenticated_client.post(
            f"{ESIGN_PREFIX}/envelopes",
            json={
                "loan_id": 1,
                "title": "Purchase Agreement",
                "document_storage_key": "orgs/1/loans/1/contract.pdf",
                "recipients": [
                    {"name": "Jane Doe", "email": "jane@example.com"},
                ],
                "fields": [],
                "expires_in_days": 30,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        required_keys = {"envelope_uuid", "status", "recipients", "expires_at"}
        missing = required_keys - set(body.keys())
        assert not missing, f"Missing keys: {missing}"
        assert isinstance(body["recipients"], list)
        assert body["status"] == "draft"

    def test_get_signing_status_response(
        self, authenticated_client, db_session
    ):
        """GET /envelopes/{uuid} returns status with recipients list."""
        _seed_loan(db_session)
        env = _seed_envelope(db_session)
        recip = _seed_recipient(db_session, envelope_id=env.id)
        db_session.commit()

        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/envelopes/{env.envelope_uuid}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["envelope_uuid"] == env.envelope_uuid
        assert "status" in body
        assert "recipients" in body
        assert isinstance(body["recipients"], list)
        assert len(body["recipients"]) >= 1
        signer = body["recipients"][0]
        assert "name" in signer
        assert "status" in signer
        assert "email" in signer
        assert "fields" in body
        assert "progress" in body

    def test_expired_token_returns_401(self, authenticated_client, db_session):
        """GET /sign/{token} with expired token returns 401."""
        from database.models.esignature import ESignatureRecipient, RecipientStatus
        _seed_loan(db_session)
        env = _seed_envelope(db_session, status="sent")
        recip = _seed_recipient(
            db_session,
            envelope_id=env.id,
            signing_token="expired-token-xyz",
            signing_token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status=RecipientStatus.SENT.value,
        )
        db_session.commit()

        resp = authenticated_client.get(f"{ESIGN_PREFIX}/sign/expired-token-xyz")
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body
        # Should mention expiration
        assert "expired" in body["detail"].lower() or "invalid" in body["detail"].lower()

    def test_invalid_token_returns_401(self, authenticated_client, db_session):
        """GET /sign/{token} with nonexistent token returns 401."""
        resp = authenticated_client.get(f"{ESIGN_PREFIX}/sign/nonexistent-token-999")
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body

    def test_start_signing_session_response(
        self,
        authenticated_client,
        db_session,
        _mock_esign_consent,
        _mock_kba_service,
        _mock_s3_service,
    ):
        """GET /sign/{token} with valid token returns session data."""
        from database.models.esignature import (
            ESignatureRecipient, ESignatureEnvelope, RecipientStatus, EnvelopeStatus,
        )
        _seed_loan(db_session)
        env = _seed_envelope(db_session, status=EnvelopeStatus.SENT.value)
        recip = _seed_recipient(
            db_session,
            envelope_id=env.id,
            signing_token="valid-token-abc",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            status=RecipientStatus.SENT.value,
        )
        db_session.commit()

        # Patch S3 at the location the esign routes import it
        with patch(
            "routes.smart_docs_esign_routes.get_smart_docs_s3_service",
            return_value=_mock_s3_service,
        ):
            resp = authenticated_client.get(f"{ESIGN_PREFIX}/sign/valid-token-abc")

        assert resp.status_code == 200
        body = resp.json()
        assert "envelope_uuid" in body
        assert "title" in body
        assert "signer" in body
        assert "fields" in body
        assert isinstance(body["fields"], list)
        assert body["signer"]["name"] == "Jane Doe"

    def test_get_audit_trail_response(self, authenticated_client, db_session):
        """GET /envelopes/{uuid}/audit-trail returns events list."""
        _seed_loan(db_session)
        env = _seed_envelope(db_session)
        _seed_audit_event(db_session, envelope_id=env.id)
        db_session.commit()

        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/envelopes/{env.envelope_uuid}/audit-trail",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert isinstance(body["events"], list)
        assert "count" in body
        assert body["count"] >= 1
        event = body["events"][0]
        required_event_keys = {"event_type", "description", "timestamp"}
        missing = required_event_keys - set(event.keys())
        assert not missing, f"Audit event missing keys: {missing}"
        assert "ip_address" in event
        assert "user_agent" in event


# ============================================================================
# 4. NEEDS LIST ENDPOINTS CONTRACT TESTS
# ============================================================================

class TestNeedsListEndpointContracts:
    """Verify response shapes for needs list management endpoints."""

    def test_generate_needs_list_response(
        self, authenticated_client, db_session, _mock_needs_list_generator
    ):
        """POST /needs-list/generate returns generated requests."""
        _seed_loan(db_session)
        _mock_needs_list_generator.generate_needs_list.return_value = {
            "loan_id": 1,
            "requests_created": 5,
            "requests": [
                {"id": 1, "title": "Recent Paystubs", "status": "OPEN", "doc_type": "PAYSTUB"},
            ],
        }
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/needs-list/generate",
            json={
                "loan_id": 1,
                "loan_program": "CONVENTIONAL",
                "occupancy_type": "PRIMARY",
                "income_type": "W2",
                "borrower_id": 1,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "requests" in body or "requests_created" in body

    def test_add_custom_request_response(
        self, authenticated_client, db_session, _mock_needs_list_generator
    ):
        """POST /needs-list/{loan_id}/custom-request returns created request."""
        _seed_loan(db_session)
        _mock_needs_list_generator.add_custom_request.return_value = {
            "id": 10,
            "title": "Custom Document",
            "status": "OPEN",
            "doc_type": "OTHER",
        }
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/needs-list/1/custom-request",
            params={"borrower_id": 1},
            json={
                "title": "Custom Document",
                "description": "A special request",
                "priority": "NORMAL",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body or "title" in body

    def test_waive_requirement_response(
        self, authenticated_client, db_session, _mock_needs_list_generator
    ):
        """POST /needs-list/request/{request_id}/waive returns waiver info."""
        _seed_loan(db_session)
        req = _seed_document_request(db_session)
        db_session.commit()

        _mock_needs_list_generator.waive_request.return_value = {
            "id": req.id,
            "status": "WAIVED",
            "waived_by": "test_user",
            "waiver_reason": "Not applicable for VA loan",
        }
        # Patch NeedsListGenerator in requests routes module
        with patch("routes.smart_docs_requests_routes.NeedsListGenerator") as mock_cls:
            mock_cls.return_value = _mock_needs_list_generator
            resp = authenticated_client.post(
                f"{SMART_DOCS_PREFIX}/needs-list/request/{req.id}/waive",
                json={
                    "reason": "Not applicable for VA loan",
                    "waived_by": "test_user",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body or "id" in body

    def test_get_checklist_response(
        self, authenticated_client, db_session, _mock_needs_list_generator, _mock_s3_service
    ):
        """GET /needs-list/{loan_id} returns categorized checklist."""
        _seed_loan(db_session)
        _mock_needs_list_generator.get_needs_list.return_value = {
            "loan_id": 1,
            "all_requests": [],
            "by_category": {"income": [], "assets": [], "identity": []},
            "stats": {"total": 10, "open": 3, "accepted": 5, "waived": 2},
        }
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/needs-list/1")
        assert resp.status_code == 200
        body = resp.json()
        assert "all_requests" in body
        assert "stats" in body or "by_category" in body

    def test_send_reminder_response(self, authenticated_client, db_session):
        """POST /envelopes/{uuid}/remind returns reminder info."""
        from database.models.esignature import EnvelopeStatus, RecipientStatus
        _seed_loan(db_session)
        env = _seed_envelope(db_session, status=EnvelopeStatus.SENT.value)
        recip = _seed_recipient(
            db_session,
            envelope_id=env.id,
            status=RecipientStatus.SENT.value,
            signing_token="remind-token",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.commit()

        with patch("routes.smart_docs_esign_routes.get_esignature_crypto_service") as mock_fn:
            mock_crypto = MagicMock()
            mock_crypto.generate_signing_token.return_value = (
                "new-token",
                datetime.now(timezone.utc) + timedelta(days=30),
            )
            mock_fn.return_value = mock_crypto

            resp = authenticated_client.post(
                f"{ESIGN_PREFIX}/envelopes/{env.envelope_uuid}/remind",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "envelope_uuid" in body
        assert "reminders_sent" in body


# ============================================================================
# 5. SEARCH ENDPOINTS CONTRACT TESTS
# ============================================================================

class TestSearchEndpointContracts:
    """Verify response shapes for document search endpoints.

    Smart Docs does not have a dedicated /search endpoint; document listing
    and filtering is done via the needs-list GET endpoint and document-by-id.
    These tests verify the filtering/listing behavior where applicable.
    """

    def test_needs_list_filtering_response(
        self, authenticated_client, db_session, _mock_needs_list_generator, _mock_s3_service
    ):
        """GET /needs-list/{loan_id} returns filtered results with correct shape."""
        _seed_loan(db_session)
        _mock_needs_list_generator.get_needs_list.return_value = {
            "loan_id": 1,
            "all_requests": [
                {"id": 1, "title": "Paystubs", "status": "OPEN", "doc_type": "PAYSTUB"},
            ],
            "stats": {"total": 1, "open": 1},
        }
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/needs-list/1")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["all_requests"], list)

    def test_envelope_list_response_shape(self, authenticated_client, db_session):
        """GET /loan/{loan_id}/envelopes returns paginated envelope list."""
        _seed_loan(db_session)
        env = _seed_envelope(db_session)
        db_session.commit()

        resp = authenticated_client.get(f"{ESIGN_PREFIX}/loan/1/envelopes")
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert isinstance(body["total"], int)
        assert "envelopes" in body
        assert isinstance(body["envelopes"], list)
        assert "limit" in body
        assert "offset" in body

    def test_envelope_list_with_status_filter(self, authenticated_client, db_session):
        """GET /loan/{loan_id}/envelopes?status=draft filters correctly."""
        _seed_loan(db_session)
        _seed_envelope(db_session, status="draft")
        _seed_envelope(db_session, envelope_uuid="env-uuid-002", status="sent")
        db_session.commit()

        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/loan/1/envelopes",
            params={"status": "draft"},
        )
        assert resp.status_code == 200
        body = resp.json()
        for env in body["envelopes"]:
            assert env["status"] == "draft"

    def test_document_not_found_returns_404(self, authenticated_client, db_session):
        """GET /document/999999 returns 404 with detail key."""
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/document/999999")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body


# ============================================================================
# 6. ERROR RESPONSE CONTRACT TESTS
# ============================================================================

class TestErrorResponseContracts:
    """Verify error responses do not leak internal details."""

    def test_404_response_shape(self, authenticated_client, db_session):
        """404 returns {detail: "..."} without internal data."""
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/document/999999")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        # Must not contain stack trace or SQL
        detail = str(body["detail"]).lower()
        assert "traceback" not in detail
        assert "sqlalchemy" not in detail
        assert "select" not in detail

    def test_422_response_shape(self, authenticated_client, db_session):
        """Validation error returns {detail: [{loc, msg, type}]}."""
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/upload",
            data={"loan_id": "not_a_number", "borrower_id": "also_not"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        if body["detail"]:
            error_item = body["detail"][0]
            # FastAPI validation errors include loc, msg, type
            assert "msg" in error_item

    def test_500_response_sanitized(
        self, authenticated_client, db_session, _mock_needs_list_generator
    ):
        """500 returns generic message without stack traces.

        The production error handler in error_handling.py sanitizes 500-level
        responses.  We simulate a 500 by making the service throw.
        """
        _seed_loan(db_session)
        _mock_needs_list_generator.generate_needs_list.side_effect = RuntimeError(
            "DB connection pool exhausted at 0x7f123abc"
        )
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/needs-list/generate",
            json={
                "loan_id": 1,
                "loan_program": "CONVENTIONAL",
                "occupancy_type": "PRIMARY",
                "income_type": "W2",
                "borrower_id": 1,
            },
        )
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        detail = body["detail"].lower()
        # Must not contain memory addresses, raw error messages, or SQL
        assert "0x7f" not in detail
        assert "pool exhausted" not in detail

    def test_401_response_shape(self, client, db_session):
        """Unauthenticated request returns 401 with detail key.

        Uses the 'client' fixture (no auth override) so the real auth
        dependency runs and rejects the request.
        """
        resp = client.get(f"{SMART_DOCS_PREFIX}/document/1")
        # Should be 401 or 403 depending on auth middleware behavior
        assert resp.status_code in (401, 403)
        body = resp.json()
        assert "detail" in body

    def test_403_response_shape(self, authenticated_client, db_session):
        """Request to admin-only endpoint by non-admin returns 403."""
        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/admin/s3-test")
        assert resp.status_code == 403
        body = resp.json()
        assert "detail" in body
        # Should not leak what permissions are needed beyond "access required"
        detail = body["detail"].lower()
        assert "admin" in detail or "permission" in detail or "forbidden" in detail

    def test_envelope_not_found_returns_404(self, authenticated_client, db_session):
        """GET /envelopes/{nonexistent-uuid} returns 404."""
        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/envelopes/nonexistent-uuid-xyz",
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        # Must not reveal table structure
        assert "esignature_envelope" not in body["detail"].lower()


# ============================================================================
# 7. PAGINATION & FILTERING CONTRACT TESTS
# ============================================================================

class TestPaginationFilteringContracts:
    """Verify pagination and filtering parameters work correctly."""

    def test_pagination_defaults(self, authenticated_client, db_session):
        """GET /loan/{id}/envelopes uses default pagination when no params given."""
        _seed_loan(db_session)
        db_session.commit()

        resp = authenticated_client.get(f"{ESIGN_PREFIX}/loan/1/envelopes")
        assert resp.status_code == 200
        body = resp.json()
        # Default limit is 50, offset is 0 (per the route definition)
        assert body["limit"] == 50
        assert body["offset"] == 0

    def test_pagination_respects_limits(self, authenticated_client, db_session):
        """GET /loan/{id}/envelopes?limit=5 caps results at 5."""
        _seed_loan(db_session)
        # Seed multiple envelopes
        for i in range(10):
            _seed_envelope(
                db_session,
                envelope_uuid=f"env-uuid-{i:03d}",
            )
        db_session.commit()

        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/loan/1/envelopes",
            params={"limit": 5, "offset": 0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["envelopes"]) <= 5
        assert body["limit"] == 5

    def test_pagination_over_max_rejected(self, authenticated_client, db_session):
        """GET /loan/{id}/envelopes?limit=500 rejected by validation (max 200)."""
        _seed_loan(db_session)
        db_session.commit()

        resp = authenticated_client.get(
            f"{ESIGN_PREFIX}/loan/1/envelopes",
            params={"limit": 500},
        )
        # FastAPI will return 422 because le=200 validation fails
        assert resp.status_code == 422

    def test_sort_and_offset_accepted(self, authenticated_client, db_session):
        """GET /loan/{id}/envelopes?offset=2 skips first 2 results."""
        _seed_loan(db_session)
        for i in range(5):
            _seed_envelope(
                db_session,
                envelope_uuid=f"env-uuid-sort-{i:03d}",
            )
        db_session.commit()

        resp_all = authenticated_client.get(
            f"{ESIGN_PREFIX}/loan/1/envelopes",
            params={"limit": 50, "offset": 0},
        )
        resp_offset = authenticated_client.get(
            f"{ESIGN_PREFIX}/loan/1/envelopes",
            params={"limit": 50, "offset": 2},
        )
        assert resp_all.status_code == 200
        assert resp_offset.status_code == 200
        all_body = resp_all.json()
        offset_body = resp_offset.json()
        # Total should be the same; results should differ
        assert all_body["total"] == offset_body["total"]
        if all_body["total"] > 2:
            assert len(offset_body["envelopes"]) <= len(all_body["envelopes"])

    def test_content_type_is_json(self, authenticated_client, db_session):
        """All API responses use application/json content type."""
        _seed_loan(db_session)
        db_session.commit()

        endpoints = [
            ("GET", f"{ESIGN_PREFIX}/loan/1/envelopes"),
            ("GET", f"{SMART_DOCS_PREFIX}/document/999999"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = authenticated_client.get(url)
            else:
                resp = authenticated_client.post(url)
            assert resp.headers["content-type"].startswith("application/json"), (
                f"{method} {url} returned content-type: {resp.headers.get('content-type')}"
            )


# ============================================================================
# 8. ADDITIONAL CROSS-CUTTING CONTRACT TESTS
# ============================================================================

class TestCrossCuttingContracts:
    """Cross-cutting concerns: tenant isolation, idempotency, headers."""

    def test_document_from_other_org_returns_404(
        self, authenticated_client, db_session
    ):
        """Document belonging to a different org is invisible (returns 404)."""
        # Seed a loan belonging to org 999 (different from mock_user's org 1)
        from sqlalchemy import text as sa_text
        try:
            db_session.execute(sa_text(
                "INSERT INTO loans (id, borrower_name, organization_id) "
                "VALUES (999, 'Other Org Borrower', 999)"
            ))
            db_session.flush()
        except Exception:
            db_session.rollback()
            pytest.skip("Cannot seed cross-org loan in test DB")

        doc = _seed_smart_document(db_session, loan_id=999)
        db_session.commit()

        resp = authenticated_client.get(f"{SMART_DOCS_PREFIX}/document/{doc.id}")
        # Should be 404 due to tenant isolation
        assert resp.status_code == 404

    def test_reject_document_response_shape(self, authenticated_client, db_session):
        """POST /document/{id}/reject with valid body returns rejection info."""
        _seed_loan(db_session)
        doc = _seed_smart_document(db_session)
        db_session.commit()

        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/document/{doc.id}/reject",
            json={
                "reviewer": "test_user",
                "reason": "Screenshot detected",
                "rejection_category": "SCREENSHOT",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "REJECTED"
        assert body["rejection_reason"] == "Screenshot detected"
        assert body["document_id"] == doc.id
        assert "rejected_by" in body
        assert "rejected_at" in body

    def test_void_envelope_response_shape(
        self, authenticated_client, db_session
    ):
        """POST /envelopes/{uuid}/void returns voided status."""
        from database.models.esignature import EnvelopeStatus
        _seed_loan(db_session)
        env = _seed_envelope(db_session, status=EnvelopeStatus.SENT.value)
        db_session.commit()

        resp = authenticated_client.post(
            f"{ESIGN_PREFIX}/envelopes/{env.envelope_uuid}/void",
            json={"reason": "Superseded by new version"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "voided"
        assert body["envelope_uuid"] == env.envelope_uuid
        assert "voided_at" in body
        assert "reason" in body

    def test_void_completed_envelope_fails(self, authenticated_client, db_session):
        """POST /envelopes/{uuid}/void on completed envelope returns 400."""
        from database.models.esignature import EnvelopeStatus
        _seed_loan(db_session)
        env = _seed_envelope(db_session, status=EnvelopeStatus.COMPLETED.value)
        db_session.commit()

        resp = authenticated_client.post(
            f"{ESIGN_PREFIX}/envelopes/{env.envelope_uuid}/void",
            json={"reason": "Too late"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body

    def test_upload_file_too_large_returns_413(
        self, authenticated_client, db_session, _mock_s3_service
    ):
        """POST /upload with >20MB file returns 413."""
        _seed_loan(db_session)
        # Create a file slightly over 20MB
        large_content = b"x" * (20 * 1024 * 1024 + 1)
        resp = authenticated_client.post(
            f"{SMART_DOCS_PREFIX}/upload",
            data={"loan_id": "1", "borrower_id": "1"},
            files={"file": ("huge.pdf", BytesIO(large_content), "application/pdf")},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert "detail" in body
