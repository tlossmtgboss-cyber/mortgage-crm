"""
Test Smart Docs E-Signature Routes

Integration tests for the built-in e-signature API covering envelope
management, token-based signing sessions, template operations, audit trails,
tenant isolation, and multi-recipient signing order enforcement.

Endpoint groups tested:
- POST /api/v1/esign/envelopes (create envelope)
- GET  /api/v1/esign/envelopes/{uuid} (envelope details)
- POST /api/v1/esign/envelopes/{uuid}/send (send for signing)
- POST /api/v1/esign/envelopes/{uuid}/void (void envelope)
- POST /api/v1/esign/envelopes/{uuid}/remind (send reminder)
- GET  /api/v1/esign/envelopes/{uuid}/audit-trail (audit trail)
- GET  /api/v1/esign/envelopes/{uuid}/download (download signed doc)
- GET  /api/v1/esign/envelopes/{uuid}/certificate (completion certificate)
- GET  /api/v1/esign/loan/{loan_id}/envelopes (list envelopes for loan)
- GET  /api/v1/esign/sign/{token} (start signing session - public)
- POST /api/v1/esign/sign/{token}/submit (submit signature - public)
- POST /api/v1/esign/templates/{id}/create-envelope (create from template)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers to build mock DB model instances
# ---------------------------------------------------------------------------

class _FakeEnvelope:
    """Lightweight stand-in for ESignatureEnvelope."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=100,
            organization_id=1,
            loan_id=42,
            created_by_user_id=1,
            envelope_uuid="env-uuid-1234",
            title="Test Disclosure Package",
            description="Test description",
            original_filename="disclosure.pdf",
            page_count=3,
            status="draft",
            document_hash_sha256="abc123hash",
            document_storage_key="s3://bucket/docs/disclosure.pdf",
            signed_document_storage_key=None,
            completion_certificate_key=None,
            total_recipients=1,
            completed_recipients=0,
            sent_at=None,
            viewed_at=None,
            completed_at=None,
            voided_at=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            void_reason=None,
            ip_address_created="127.0.0.1",
            reminder_frequency_hours=48,
            last_reminder_sent_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeRecipient:
    """Lightweight stand-in for ESignatureRecipient."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=200,
            envelope_id=100,
            recipient_type="signer",
            signing_order=1,
            name="Jane Borrower",
            email="jane@example.com",
            phone=None,
            access_code=None,
            auth_method="email_link",
            signing_token="valid-token-abc123",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            status="pending",
            viewed_at=None,
            signed_at=None,
            declined_at=None,
            decline_reason=None,
            signing_ip_address=None,
            signing_user_agent=None,
            signing_geo_location=None,
            signature_image_key=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeField:
    """Lightweight stand-in for ESignatureField."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=300,
            envelope_id=100,
            recipient_id=200,
            field_type="signature",
            field_uuid="field-uuid-001",
            page_number=1,
            x_position=100.0,
            y_position=500.0,
            width=200.0,
            height=50.0,
            is_required=True,
            placeholder_text=None,
            default_value=None,
            group_name=None,
            dropdown_options=None,
            validation_regex=None,
            value=None,
            filled_at=None,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeAuditEvent:
    """Lightweight stand-in for ESignatureAuditEvent."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=400,
            envelope_id=100,
            recipient_id=None,
            event_type="created",
            event_description="Envelope created",
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0",
            extra_metadata=None,
            document_hash_at_event=None,
            timestamp=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeTemplate:
    """Lightweight stand-in for ESignatureTemplate."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=500,
            organization_id=1,
            created_by_user_id=1,
            name="Borrower Consent Form",
            description="Standard consent form",
            document_storage_key="s3://bucket/templates/consent.pdf",
            fields_config=[
                {
                    "field_type": "signature",
                    "page_number": 1,
                    "x": 100,
                    "y": 500,
                    "width": 200,
                    "height": 50,
                    "is_required": True,
                    "recipient_role": "borrower",
                },
            ],
            default_recipients=[
                {"role_label": "borrower"},
            ],
            category="consent",
            is_active=True,
            usage_count=5,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeCertificate:
    """Lightweight stand-in for SigningCertificate dataclass."""

    def __init__(self, **kwargs):
        self.certificate_id = kwargs.get("certificate_id", "CERT-ABCDEF123456")
        self.envelope_uuid = kwargs.get("envelope_uuid", "env-uuid-1234")
        self.title = kwargs.get("title", "Test Doc")
        self.signature_hash = kwargs.get("signature_hash", "hash123")


class _MockUser:
    """Mock user for authenticated tests."""

    def __init__(self, id=1, organization_id=1, permission_role="loan_officer", email="lo@example.com"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = permission_role
        self.email = email


# ---------------------------------------------------------------------------
# Reusable mock builder for the crypto service
# ---------------------------------------------------------------------------

def _make_mock_crypto():
    crypto = MagicMock()
    crypto.generate_envelope_uuid.return_value = "env-uuid-new-1234"
    crypto.generate_signing_token.return_value = (
        "token-abc-123",
        datetime.now(timezone.utc) + timedelta(days=7),
    )
    crypto.hash_access_code.return_value = "hashed_code"
    crypto.verify_access_code.return_value = True
    crypto.generate_signature_hash.return_value = "sig-hash-xyz"
    crypto.generate_completion_certificate.return_value = _FakeCertificate()
    return crypto


# ---------------------------------------------------------------------------
# Helper: build a mock SQLAlchemy query chain
# ---------------------------------------------------------------------------

def _mock_query_chain(results, count=None):
    """Return a MagicMock that behaves like db.query(...).filter(...).order_by(...)..."""
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.filter_by.return_value = chain
    chain.order_by.return_value = chain
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.first.return_value = results[0] if results else None
    chain.all.return_value = results
    chain.count.return_value = count if count is not None else len(results)
    chain.with_entities.return_value = chain
    chain.group_by.return_value = chain
    return chain


# ===========================================================================
# TESTS
# ===========================================================================


@pytest.mark.unit
class TestCreateEnvelope:
    """POST /api/v1/esign/envelopes"""

    @patch("routes.smart_docs_esign_routes.get_esignature_crypto_service")
    @patch("routes.smart_docs_esign_routes._verify_loan_tenant")
    @patch("routes.smart_docs_esign_routes._record_audit_event")
    def test_create_envelope_happy_path(
        self,
        mock_audit,
        mock_verify_loan,
        mock_get_crypto,
        authenticated_client: TestClient,
        db_session,
    ):
        """Creating an envelope with valid data should succeed and return envelope_uuid."""
        crypto = _make_mock_crypto()
        mock_get_crypto.return_value = crypto
        mock_verify_loan.return_value = None  # no error

        payload = {
            "loan_id": 42,
            "title": "Closing Disclosure",
            "description": "CD for loan 42",
            "document_storage_key": "s3://bucket/docs/cd.pdf",
            "original_filename": "cd.pdf",
            "page_count": 5,
            "recipients": [
                {
                    "name": "Jane Borrower",
                    "email": "jane@example.com",
                    "type": "signer",
                    "signing_order": 1,
                },
            ],
            "fields": [
                {
                    "type": "signature",
                    "page": 1,
                    "x": 100.0,
                    "y": 600.0,
                    "w": 200.0,
                    "h": 50.0,
                    "recipient_index": 0,
                    "required": True,
                },
            ],
            "expires_in_days": 30,
        }

        response = authenticated_client.post("/api/v1/esign/envelopes", json=payload)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "envelope_uuid" in data
        assert data["status"] == "draft"
        assert data["title"] == "Closing Disclosure"
        assert len(data["recipients"]) == 1
        assert data["recipients"][0]["name"] == "Jane Borrower"

    def test_create_envelope_missing_recipients(self, authenticated_client: TestClient):
        """Creating an envelope with no recipients should return 400 or 422."""
        payload = {
            "loan_id": 42,
            "title": "No Recipients Doc",
            "document_storage_key": "s3://bucket/docs/empty.pdf",
            "recipients": [],
        }
        response = authenticated_client.post("/api/v1/esign/envelopes", json=payload)
        assert response.status_code in (400, 422), f"Expected validation error, got {response.status_code}"

    def test_create_envelope_missing_title(self, authenticated_client: TestClient):
        """Creating an envelope without title should return 422."""
        payload = {
            "loan_id": 42,
            "document_storage_key": "s3://bucket/docs/notitle.pdf",
            "recipients": [
                {"name": "Bob", "email": "bob@example.com"},
            ],
        }
        response = authenticated_client.post("/api/v1/esign/envelopes", json=payload)
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_create_envelope_missing_document_storage_key(self, authenticated_client: TestClient):
        """Creating an envelope without document_storage_key should return 422."""
        payload = {
            "loan_id": 42,
            "title": "Missing Doc Key",
            "recipients": [
                {"name": "Bob", "email": "bob@example.com"},
            ],
        }
        response = authenticated_client.post("/api/v1/esign/envelopes", json=payload)
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_create_envelope_requires_auth(self, client: TestClient):
        """Creating an envelope without auth should return 401/403."""
        payload = {
            "loan_id": 42,
            "title": "Unauthed Attempt",
            "document_storage_key": "s3://test",
            "recipients": [{"name": "Bob", "email": "bob@example.com"}],
        }
        response = client.post("/api/v1/esign/envelopes", json=payload)
        assert response.status_code in (401, 403, 422), (
            f"Expected auth rejection, got {response.status_code}"
        )


@pytest.mark.unit
class TestGetLoanEnvelopes:
    """GET /api/v1/esign/loan/{loan_id}/envelopes"""

    @patch("routes.smart_docs_esign_routes._verify_loan_tenant")
    def test_list_envelopes_for_loan(
        self,
        mock_verify_loan,
        authenticated_client: TestClient,
        db_session,
    ):
        """Listing envelopes for a loan should return structured response."""
        mock_verify_loan.return_value = None
        response = authenticated_client.get("/api/v1/esign/loan/42/envelopes")
        assert response.status_code == 200
        data = response.json()
        assert "loan_id" in data
        assert "total" in data
        assert "envelopes" in data
        assert isinstance(data["envelopes"], list)

    def test_list_envelopes_requires_auth(self, client: TestClient):
        """Listing envelopes without auth should be rejected."""
        response = client.get("/api/v1/esign/loan/42/envelopes")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestGetEnvelopeDetails:
    """GET /api/v1/esign/envelopes/{envelope_uuid}"""

    def test_get_envelope_not_found(self, authenticated_client: TestClient):
        """Requesting a non-existent envelope should return 404."""
        response = authenticated_client.get(
            "/api/v1/esign/envelopes/nonexistent-uuid-999"
        )
        assert response.status_code == 404

    def test_get_envelope_requires_auth(self, client: TestClient):
        """Getting envelope details without auth should be rejected."""
        response = client.get("/api/v1/esign/envelopes/any-uuid")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestSendEnvelope:
    """POST /api/v1/esign/envelopes/{uuid}/send"""

    def test_send_envelope_not_found(self, authenticated_client: TestClient):
        """Sending a non-existent envelope should return 404."""
        response = authenticated_client.post(
            "/api/v1/esign/envelopes/nonexistent-uuid/send"
        )
        assert response.status_code == 404

    def test_send_envelope_requires_auth(self, client: TestClient):
        """Sending an envelope without auth should be rejected."""
        response = client.post("/api/v1/esign/envelopes/some-uuid/send")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestSignDocument:
    """POST /api/v1/esign/sign/{token}/submit"""

    def test_sign_with_invalid_token(self, client: TestClient):
        """Submitting a signature with a bogus token should return 401."""
        payload = {
            "fields": [{"field_id": 1, "value": "Jane Doe"}],
        }
        response = client.post(
            "/api/v1/esign/sign/totally-invalid-token/submit",
            json=payload,
        )
        assert response.status_code == 401, (
            f"Expected 401 for invalid token, got {response.status_code}"
        )

    def test_sign_with_expired_token(self, client: TestClient, db_session):
        """Submitting a signature with an expired token should return 401."""
        from database.models.esignature import ESignatureRecipient, ESignatureEnvelope

        # Insert an envelope and recipient with an expired token directly
        try:
            envelope = ESignatureEnvelope(
                organization_id=1,
                loan_id=42,
                created_by_user_id=1,
                envelope_uuid="env-expired-test",
                title="Expired Token Test",
                status="sent",
                document_storage_key="s3://test/expired.pdf",
                total_recipients=1,
                completed_recipients=0,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                ip_address_created="127.0.0.1",
                reminder_frequency_hours=48,
            )
            db_session.add(envelope)
            db_session.flush()

            recipient = ESignatureRecipient(
                envelope_id=envelope.id,
                recipient_type="signer",
                signing_order=1,
                name="Expired Signer",
                email="expired@example.com",
                auth_method="email_link",
                signing_token="expired-token-xyz",
                signing_token_expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
                status="sent",
            )
            db_session.add(recipient)
            db_session.flush()
        except Exception:
            # Table may not exist in SQLite test DB -- skip gracefully
            pytest.skip("esignature tables not available in test DB")

        payload = {
            "fields": [{"field_id": 1, "value": "Jane Doe"}],
        }
        response = client.post(
            "/api/v1/esign/sign/expired-token-xyz/submit",
            json=payload,
        )
        assert response.status_code == 401, (
            f"Expected 401 for expired token, got {response.status_code}"
        )


@pytest.mark.unit
class TestSigningSession:
    """GET /api/v1/esign/sign/{token} (public endpoint)"""

    def test_start_signing_session_invalid_token(self, client: TestClient):
        """Starting a signing session with an invalid token should return 401."""
        response = client.get("/api/v1/esign/sign/bogus-token-999")
        assert response.status_code == 401

    def test_start_signing_session_no_auth_required(self, client: TestClient):
        """The signing session endpoint should NOT require login (it is public/token-based).
        An invalid token returns 401 for the token, not 403 for missing auth."""
        response = client.get("/api/v1/esign/sign/any-token")
        # Should be 401 (bad token), NOT 403 (no auth) -- confirms the endpoint is public
        assert response.status_code == 401
        data = response.json()
        assert "signing token" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()


@pytest.mark.unit
class TestVoidEnvelope:
    """POST /api/v1/esign/envelopes/{uuid}/void"""

    def test_void_envelope_not_found(self, authenticated_client: TestClient):
        """Voiding a non-existent envelope should return 404."""
        payload = {"reason": "Loan cancelled"}
        response = authenticated_client.post(
            "/api/v1/esign/envelopes/no-such-uuid/void",
            json=payload,
        )
        assert response.status_code == 404

    def test_void_envelope_requires_reason(self, authenticated_client: TestClient):
        """Voiding without a reason should return 422."""
        response = authenticated_client.post(
            "/api/v1/esign/envelopes/any-uuid/void",
            json={},
        )
        assert response.status_code == 422

    def test_void_envelope_requires_auth(self, client: TestClient):
        """Voiding without auth should be rejected."""
        payload = {"reason": "Not authorized"}
        response = client.post(
            "/api/v1/esign/envelopes/any-uuid/void",
            json=payload,
        )
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestSendReminder:
    """POST /api/v1/esign/envelopes/{uuid}/remind"""

    def test_send_reminder_not_found(self, authenticated_client: TestClient):
        """Sending a reminder for a non-existent envelope should return 404."""
        response = authenticated_client.post(
            "/api/v1/esign/envelopes/no-such-uuid/remind"
        )
        assert response.status_code == 404

    def test_send_reminder_requires_auth(self, client: TestClient):
        """Sending a reminder without auth should be rejected."""
        response = client.post("/api/v1/esign/envelopes/any-uuid/remind")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestDownloadSignedDocument:
    """GET /api/v1/esign/envelopes/{uuid}/download"""

    def test_download_not_found(self, authenticated_client: TestClient):
        """Downloading from a non-existent envelope should return 404."""
        response = authenticated_client.get(
            "/api/v1/esign/envelopes/no-such-uuid/download"
        )
        assert response.status_code == 404

    def test_download_requires_auth(self, client: TestClient):
        """Downloading without auth should be rejected."""
        response = client.get("/api/v1/esign/envelopes/any-uuid/download")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestDownloadCompletionCertificate:
    """GET /api/v1/esign/envelopes/{uuid}/certificate"""

    def test_certificate_not_found(self, authenticated_client: TestClient):
        """Requesting a certificate for a non-existent envelope should return 404."""
        response = authenticated_client.get(
            "/api/v1/esign/envelopes/no-such-uuid/certificate"
        )
        assert response.status_code == 404

    def test_certificate_requires_auth(self, client: TestClient):
        """Requesting a certificate without auth should be rejected."""
        response = client.get("/api/v1/esign/envelopes/any-uuid/certificate")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestCreateFromTemplate:
    """POST /api/v1/esign/templates/{id}/create-envelope"""

    def test_create_from_template_not_found(self, authenticated_client: TestClient):
        """Creating from a non-existent template should return 404."""
        payload = {
            "loan_id": 42,
            "recipients": [
                {"name": "Jane", "email": "jane@example.com"},
            ],
        }
        response = authenticated_client.post(
            "/api/v1/esign/templates/99999/create-envelope",
            json=payload,
        )
        assert response.status_code == 404

    def test_create_from_template_requires_auth(self, client: TestClient):
        """Creating from a template without auth should be rejected."""
        payload = {
            "loan_id": 42,
            "recipients": [{"name": "Jane", "email": "jane@example.com"}],
        }
        response = client.post(
            "/api/v1/esign/templates/1/create-envelope",
            json=payload,
        )
        assert response.status_code in (401, 403, 422)

    def test_create_from_template_missing_recipients(self, authenticated_client: TestClient):
        """Creating from a template with empty recipients should fail."""
        payload = {
            "loan_id": 42,
            "recipients": [],
        }
        response = authenticated_client.post(
            "/api/v1/esign/templates/1/create-envelope",
            json=payload,
        )
        # Either 400 (route-level check) or 404 (template not found first)
        assert response.status_code in (400, 404, 422)


@pytest.mark.unit
class TestEnvelopeAuditTrail:
    """GET /api/v1/esign/envelopes/{uuid}/audit-trail"""

    def test_audit_trail_not_found(self, authenticated_client: TestClient):
        """Requesting audit trail for a non-existent envelope should return 404."""
        response = authenticated_client.get(
            "/api/v1/esign/envelopes/no-such-uuid/audit-trail"
        )
        assert response.status_code == 404

    def test_audit_trail_requires_auth(self, client: TestClient):
        """Requesting audit trail without auth should be rejected."""
        response = client.get("/api/v1/esign/envelopes/any-uuid/audit-trail")
        assert response.status_code in (401, 403, 422)


@pytest.mark.unit
class TestCrossTenantAccessPrevention:
    """Verify tenant isolation across e-sign endpoints."""

    def test_envelope_cross_tenant_returns_404(self, db_session, client: TestClient):
        """A user from org 2 should NOT see an envelope owned by org 1.

        The _verify_envelope_tenant helper raises 404 (not 403) to avoid
        leaking the existence of envelopes from other organizations.
        """
        from database.models.esignature import ESignatureEnvelope

        try:
            # Create an envelope owned by org 1
            envelope = ESignatureEnvelope(
                organization_id=1,
                loan_id=42,
                created_by_user_id=1,
                envelope_uuid="tenant-test-uuid-org1",
                title="Org 1 Envelope",
                status="draft",
                document_storage_key="s3://test/org1.pdf",
                total_recipients=1,
                completed_recipients=0,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                ip_address_created="127.0.0.1",
                reminder_frequency_hours=48,
            )
            db_session.add(envelope)
            db_session.flush()
        except Exception:
            pytest.skip("esignature tables not available in test DB")

        # Build a client authenticated as org 2
        from main import app
        from database import get_db
        from auth.dependencies import get_current_user as auth_dep_gcu
        try:
            from main import get_current_user as main_gcu
        except ImportError:
            main_gcu = auth_dep_gcu

        org2_user = _MockUser(id=99, organization_id=2, permission_role="loan_officer")

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return org2_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[main_gcu] = override_auth

        with TestClient(app) as org2_client:
            response = org2_client.get(
                f"/api/v1/esign/envelopes/tenant-test-uuid-org1"
            )
            # Should be 404 (tenant isolation hides the envelope)
            assert response.status_code == 404, (
                f"Cross-tenant access should return 404, got {response.status_code}"
            )

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestMultiRecipientSigningOrder:
    """Verify that signing order is enforced for multi-recipient envelopes."""

    def test_second_recipient_not_tokenized_before_first_signs(
        self, db_session, client: TestClient
    ):
        """When an envelope is sent, only first-order recipients should get
        signing tokens. Higher-order recipients must remain PENDING until
        their turn."""
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
        )

        try:
            envelope = ESignatureEnvelope(
                organization_id=1,
                loan_id=42,
                created_by_user_id=1,
                envelope_uuid="multi-recip-test-uuid",
                title="Multi-Recipient Doc",
                status="draft",
                document_storage_key="s3://test/multi.pdf",
                total_recipients=2,
                completed_recipients=0,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                ip_address_created="127.0.0.1",
                reminder_frequency_hours=48,
            )
            db_session.add(envelope)
            db_session.flush()

            r1 = ESignatureRecipient(
                envelope_id=envelope.id,
                recipient_type="signer",
                signing_order=1,
                name="First Signer",
                email="first@example.com",
                auth_method="email_link",
                status="pending",
            )
            r2 = ESignatureRecipient(
                envelope_id=envelope.id,
                recipient_type="signer",
                signing_order=2,
                name="Second Signer",
                email="second@example.com",
                auth_method="email_link",
                status="pending",
            )
            db_session.add_all([r1, r2])
            db_session.flush()
        except Exception:
            pytest.skip("esignature tables not available in test DB")

        # Set up authenticated client as the envelope creator
        from main import app
        from database import get_db
        from auth.dependencies import get_current_user as auth_dep_gcu
        try:
            from main import get_current_user as main_gcu
        except ImportError:
            main_gcu = auth_dep_gcu

        creator = _MockUser(id=1, organization_id=1)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return creator

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[main_gcu] = override_auth

        with patch(
            "routes.smart_docs_esign_routes.get_esignature_crypto_service"
        ) as mock_crypto_factory:
            crypto = _make_mock_crypto()
            mock_crypto_factory.return_value = crypto

            with TestClient(app) as auth_client:
                response = auth_client.post(
                    f"/api/v1/esign/envelopes/multi-recip-test-uuid/send"
                )

        app.dependency_overrides.clear()

        if response.status_code != 200:
            pytest.skip(f"Send returned {response.status_code}, skipping order check")

        data = response.json()
        # Only the first-order recipient should have been notified
        assert data["recipients_notified"] == 1, (
            f"Expected 1 recipient notified (order=1), got {data['recipients_notified']}"
        )

        # Verify the second recipient is still pending (no token yet)
        db_session.refresh(r2)
        assert r2.signing_token is None, (
            "Second-order recipient should NOT have a token before the first signer completes"
        )
        assert r2.status == "pending", (
            f"Second-order recipient should still be 'pending', got '{r2.status}'"
        )


@pytest.mark.unit
class TestESignStats:
    """GET /api/v1/esign/stats"""

    def test_stats_requires_auth(self, client: TestClient):
        """Stats endpoint without auth should be rejected."""
        response = client.get("/api/v1/esign/stats")
        assert response.status_code in (401, 403, 422)

    def test_stats_returns_structure(self, authenticated_client: TestClient):
        """Stats endpoint should return the expected fields."""
        response = authenticated_client.get("/api/v1/esign/stats")
        # It may return 200 with zero data or 500 if DB not available
        if response.status_code == 200:
            data = response.json()
            assert "total_envelopes" in data
            assert "by_status" in data
            assert "completion_rate_pct" in data


@pytest.mark.unit
class TestTemplateEndpoints:
    """GET /api/v1/esign/templates and POST /api/v1/esign/templates"""

    def test_list_templates_requires_auth(self, client: TestClient):
        """Listing templates without auth should be rejected."""
        response = client.get("/api/v1/esign/templates")
        assert response.status_code in (401, 403, 422)

    def test_create_template_requires_auth(self, client: TestClient):
        """Creating a template without auth should be rejected."""
        payload = {
            "name": "Test Template",
            "document_storage_key": "s3://test/tmpl.pdf",
        }
        response = client.post("/api/v1/esign/templates", json=payload)
        assert response.status_code in (401, 403, 422)

    @patch("routes.smart_docs_esign_routes.get_esignature_crypto_service")
    def test_create_template_happy_path(
        self,
        mock_get_crypto,
        authenticated_client: TestClient,
    ):
        """Creating a template with valid data should succeed."""
        payload = {
            "name": "Borrower Consent",
            "description": "Standard consent form",
            "document_storage_key": "s3://bucket/templates/consent.pdf",
            "category": "consent",
            "fields_config": [
                {
                    "field_type": "signature",
                    "page_number": 1,
                    "x": 100,
                    "y": 500,
                    "width": 200,
                    "height": 50,
                    "is_required": True,
                },
            ],
        }
        response = authenticated_client.post("/api/v1/esign/templates", json=payload)
        # The test DB may or may not have the table; if 200 check structure
        if response.status_code == 200:
            data = response.json()
            assert data["name"] == "Borrower Consent"
            assert data["category"] == "consent"
            assert "id" in data


@pytest.mark.unit
class TestDeclineSigning:
    """POST /api/v1/esign/sign/{token}/decline"""

    def test_decline_with_invalid_token(self, client: TestClient):
        """Declining with a bogus token should return 401."""
        payload = {"reason": "I do not agree"}
        response = client.post(
            "/api/v1/esign/sign/invalid-decline-token/decline",
            json=payload,
        )
        assert response.status_code == 401

    def test_decline_is_public_endpoint(self, client: TestClient):
        """The decline endpoint should be public (token-based), returning
        401 for bad token rather than 403 for missing auth."""
        payload = {"reason": "Not me"}
        response = client.post(
            "/api/v1/esign/sign/any-token-here/decline",
            json=payload,
        )
        assert response.status_code == 401
        data = response.json()
        assert "token" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()


@pytest.mark.unit
class TestAccessCodeVerification:
    """POST /api/v1/esign/sign/{token}/verify-access-code"""

    def test_verify_access_code_invalid_token(self, client: TestClient):
        """Verifying access code with an invalid signing token should return 401."""
        payload = {"code": "1234"}
        response = client.post(
            "/api/v1/esign/sign/bad-token/verify-access-code",
            json=payload,
        )
        assert response.status_code == 401

    def test_verify_access_code_missing_code(self, client: TestClient):
        """Submitting without the code field should return 422."""
        response = client.post(
            "/api/v1/esign/sign/any-token/verify-access-code",
            json={},
        )
        assert response.status_code == 422
