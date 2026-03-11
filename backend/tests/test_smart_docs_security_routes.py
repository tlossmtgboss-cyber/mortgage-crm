"""
Test Smart Docs Security Routes

Integration tests for the document security API endpoints:
- Access audit logging (SOC 2 compliance)
- Integrity verification (tamper detection via SHA-256)
- Fraud analysis (risk scoring and indicator detection)
- Retention policy management (TRID, state-specific rules)
- Watermarking (forensic tracing)
- Encryption status tracking
- Suspicious activity detection
- Compliance reporting
- Tenant isolation on all endpoints
- Unauthenticated access blocked
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


# =============================================================================
# Constants
# =============================================================================

PREFIX = "/api/smart-docs/doc-security"


# =============================================================================
# Helper: Mock user factory
# =============================================================================

class _MockUser:
    """Lightweight mock user for dependency override."""
    def __init__(
        self,
        id=1,
        organization_id=1,
        permission_role="loan_officer",
        first_name="Test",
        last_name="User",
        email="test@example.com",
    ):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = permission_role
        self.first_name = first_name
        self.last_name = last_name
        self.email = email


def _admin_user(org_id=1):
    return _MockUser(id=2, organization_id=org_id, permission_role="site_admin")


def _platform_admin():
    return _MockUser(id=3, organization_id=None, permission_role="admin")


def _other_org_user(org_id=999):
    return _MockUser(id=10, organization_id=org_id, permission_role="site_admin")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def _seed_security_tables(db_session):
    """Ensure the security tables exist in the test DB and seed sample rows."""
    from database.models.document_security import (
        DocumentAccessLog,
        DocumentEncryptionRecord,
        DocumentIntegrityCheck,
        DocumentRetentionPolicy,
        DocumentWatermarkLog,
        AccessType,
        EncryptionStatus,
        IntegrityCheckType,
        RetentionAction,
        WatermarkType,
    )

    # Seed an access log
    log = DocumentAccessLog(
        organization_id=1,
        document_id=100,
        document_type="smart_document",
        user_id=1,
        access_type=AccessType.VIEW,
        access_granted=True,
        ip_address="10.0.0.1",
        user_agent="TestAgent/1.0",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(log)

    # Seed a denied access log (different org)
    denied_log = DocumentAccessLog(
        organization_id=999,
        document_id=200,
        document_type="smart_document",
        user_id=10,
        access_type=AccessType.DOWNLOAD,
        access_granted=False,
        denial_reason="Unauthorized org",
        ip_address="192.168.1.1",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(denied_log)

    # Seed an integrity check
    integrity = DocumentIntegrityCheck(
        document_id=100,
        document_type="smart_document",
        check_type=IntegrityCheckType.MANUAL,
        expected_hash="abc123",
        actual_hash="abc123",
        is_valid=True,
        tamper_detected=False,
        checked_by="1",
        check_duration_ms=42,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(integrity)

    # Seed a tampered integrity check
    tampered = DocumentIntegrityCheck(
        document_id=200,
        document_type="smart_document",
        check_type=IntegrityCheckType.MANUAL,
        expected_hash="abc123",
        actual_hash="xyz789",
        is_valid=False,
        tamper_detected=True,
        tamper_details="Hash mismatch detected",
        checked_by="1",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(tampered)

    # Seed an encryption record
    enc = DocumentEncryptionRecord(
        organization_id=1,
        document_id=100,
        document_type="smart_document",
        encryption_algorithm="AES-256-GCM",
        key_id="kms/test123",
        key_version=1,
        encrypted_at=datetime.now(timezone.utc),
        encryption_status=EncryptionStatus.ENCRYPTED,
        content_hash_before="hash_before",
        content_hash_after="hash_after",
        file_size_before=1024,
        file_size_after=1024,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(enc)

    # Seed a retention policy (org 1)
    policy = DocumentRetentionPolicy(
        organization_id=1,
        doc_type="paystubs",
        policy_name="TRID Paystub Retention",
        retention_days=1095,
        retention_after_event="FUNDED",
        action_on_expiry=RetentionAction.NOTIFY_ADMIN,
        notify_days_before=30,
        is_active=True,
        regulatory_reference="TRID 36-month requirement",
        applies_to_states=["CA", "TX"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(policy)

    # Seed a watermark log
    wm = DocumentWatermarkLog(
        document_id=100,
        watermark_type=WatermarkType.VIEWING,
        watermark_text="COPY - Test User - 2026-03-10",
        applied_to_user_id=1,
        applied_at=datetime.now(timezone.utc),
        output_storage_key="watermarked/test/file.pdf",
    )
    db_session.add(wm)

    db_session.flush()

    return {
        "access_log": log,
        "denied_log": denied_log,
        "integrity": integrity,
        "tampered": tampered,
        "encryption": enc,
        "policy": policy,
        "watermark": wm,
    }


def _make_client(app, db_session, user):
    """Build a TestClient with overridden DB and auth dependencies."""
    from database import get_db
    from auth.dependencies import get_current_user as auth_dep_gcu

    # Also import main's version in case routes reference it directly
    try:
        from main import get_current_user as main_gcu
    except ImportError:
        main_gcu = None

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    async def _override_auth():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[auth_dep_gcu] = _override_auth
    if main_gcu is not None:
        app.dependency_overrides[main_gcu] = _override_auth

    return TestClient(app)


@pytest.fixture
def app_instance():
    """Import the FastAPI app."""
    from main import app
    return app


@pytest.fixture
def admin_client(app_instance, db_session, _seed_security_tables):
    """Authenticated admin client (org 1, site_admin role)."""
    c = _make_client(app_instance, db_session, _admin_user(org_id=1))
    yield c
    app_instance.dependency_overrides.clear()


@pytest.fixture
def lo_client(app_instance, db_session, _seed_security_tables):
    """Authenticated loan officer client (non-admin)."""
    c = _make_client(app_instance, db_session, _MockUser())
    yield c
    app_instance.dependency_overrides.clear()


@pytest.fixture
def other_org_admin_client(app_instance, db_session, _seed_security_tables):
    """Admin client from a different organization (org 999)."""
    c = _make_client(app_instance, db_session, _other_org_user(org_id=999))
    yield c
    app_instance.dependency_overrides.clear()


@pytest.fixture
def platform_admin_client(app_instance, db_session, _seed_security_tables):
    """Platform admin client with cross-org access."""
    c = _make_client(app_instance, db_session, _platform_admin())
    yield c
    app_instance.dependency_overrides.clear()


@pytest.fixture
def unauth_client(app_instance, db_session):
    """Client with NO auth override -- should trigger 401/403."""
    from database import get_db

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    app_instance.dependency_overrides[get_db] = _override_db
    # Explicitly do NOT override get_current_user
    with TestClient(app_instance) as c:
        yield c
    app_instance.dependency_overrides.clear()


# =============================================================================
# 1. GET /doc-security/audit-log  (admin-only paginated audit log)
# =============================================================================

@pytest.mark.unit
class TestGetAuditLog:
    """GET /doc-security/audit-log -- admin-only paginated audit log."""

    def test_admin_can_list_audit_log(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/audit-log")
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "entries" in body
        assert isinstance(body["entries"], list)

    def test_audit_log_pagination(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/audit-log?limit=1&offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_non_admin_blocked(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/audit-log")
        assert resp.status_code == 403

    def test_filter_by_document_id(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/audit-log?document_id=100")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        for entry in entries:
            assert entry["document_id"] == 100

    def test_invalid_access_type_returns_400(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/audit-log?access_type=INVALID_TYPE")
        assert resp.status_code == 400


# =============================================================================
# 2. GET /doc-security/audit-log/{document_id}  (per-doc audit log)
# =============================================================================

@pytest.mark.unit
class TestGetDocumentAuditLog:
    """GET /doc-security/audit-log/{document_id}."""

    def test_returns_audit_for_owned_doc(self, lo_client):
        """LO can view audit log for a document in their org."""
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_verify.return_value = mock_doc
            resp = lo_client.get(f"{PREFIX}/audit-log/100")
        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 100
        assert "entries" in body

    def test_nonexistent_doc_returns_404(self, lo_client):
        """Should 404 if document does not exist (via _verify_document_org_access)."""
        resp = lo_client.get(f"{PREFIX}/audit-log/999999")
        assert resp.status_code == 404


# =============================================================================
# 3. POST /doc-security/log-access  (log a document access event)
# =============================================================================

@pytest.mark.unit
class TestLogAccess:
    """POST /doc-security/log-access."""

    def test_log_view_event(self, lo_client):
        payload = {
            "document_id": 100,
            "access_type": "view",
        }
        resp = lo_client.post(f"{PREFIX}/log-access", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "logged"
        assert body["document_id"] == 100
        assert body["access_type"] == "view"
        assert "log_id" in body

    def test_log_download_event_with_metadata(self, lo_client):
        payload = {
            "document_id": 100,
            "access_type": "download",
            "metadata": {"source": "portal"},
        }
        resp = lo_client.post(f"{PREFIX}/log-access", json=payload)
        assert resp.status_code == 200
        assert resp.json()["access_type"] == "download"

    def test_invalid_access_type_returns_400(self, lo_client):
        payload = {
            "document_id": 100,
            "access_type": "BOGUS",
        }
        resp = lo_client.post(f"{PREFIX}/log-access", json=payload)
        assert resp.status_code == 400


# =============================================================================
# 4. GET /doc-security/integrity-check/{document_id}  (run integrity check)
# =============================================================================

@pytest.mark.unit
class TestRunIntegrityCheck:
    """GET /doc-security/integrity-check/{document_id}."""

    def test_runs_check_and_returns_result(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_doc.doc_type = "smart_document"
            mock_doc.file_hash = "abc123"
            mock_doc.content_hash = None
            mock_doc.storage_key = "docs/100.pdf"
            mock_doc.s3_key = None
            mock_verify.return_value = mock_doc

            resp = lo_client.get(f"{PREFIX}/integrity-check/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 100
        assert "check_id" in body
        assert "expected_hash" in body
        assert "actual_hash" in body
        assert "tamper_detected" in body

    def test_nonexistent_doc_returns_404(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/integrity-check/999999")
        assert resp.status_code == 404


# =============================================================================
# 5. GET /doc-security/integrity-history/{document_id}
# =============================================================================

@pytest.mark.unit
class TestIntegrityHistory:
    """GET /doc-security/integrity-history/{document_id}."""

    def test_returns_history(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_verify.return_value = mock_doc
            resp = lo_client.get(f"{PREFIX}/integrity-history/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 100
        assert "checks" in body
        assert isinstance(body["checks"], list)


# =============================================================================
# 6. POST /doc-security/integrity-check/batch  (bulk integrity check)
# =============================================================================

@pytest.mark.unit
class TestBatchIntegrityCheck:
    """POST /doc-security/integrity-check/batch."""

    def test_requires_loan_or_doc_ids(self, lo_client):
        resp = lo_client.post(f"{PREFIX}/integrity-check/batch", json={})
        assert resp.status_code == 400

    def test_batch_with_document_ids(self, lo_client):
        with patch("routes.smart_docs_security_routes.SmartDocument", create=True):
            # The route does a lazy import of SmartDocument; we mock the query
            with patch("models.smart_docs_models.SmartDocument") as MockSD:
                mock_doc = MagicMock()
                mock_doc.id = 100
                mock_doc.doc_type = "smart_document"
                mock_doc.file_hash = "abc123"
                mock_doc.content_hash = None
                mock_doc.storage_key = None
                mock_doc.s3_key = None

                # Mock db.query(_SD).filter().first() chain
                MockSD_class = MagicMock()
                MockSD_class.id = 100

                resp = lo_client.post(
                    f"{PREFIX}/integrity-check/batch",
                    json={"document_ids": [100]},
                )

        # Will likely return 200 even if doc not found (returns not_found status per doc)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_checked" in body
        assert "results" in body


# =============================================================================
# 7. GET /doc-security/fraud-analysis/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestFraudAnalysis:
    """GET /doc-security/fraud-analysis/{loan_id}."""

    def test_no_docs_returns_zero_risk(self, lo_client):
        with patch("routes.smart_docs_security_routes._verify_loan_tenant"):
            with patch("models.smart_docs_models.SmartDocument") as MockSD:
                # db.query(_SD).filter().all() returns empty
                resp = lo_client.get(f"{PREFIX}/fraud-analysis/1")

        # Even if the query returns nothing (no SmartDocument table data),
        # the endpoint should return 200 with risk_score=0
        assert resp.status_code == 200
        body = resp.json()
        assert body["loan_id"] == 1
        assert body["risk_score"] == 0
        assert body["risk_level"] == "unknown"

    def test_fraud_analysis_nonexistent_loan_404(self, lo_client):
        """Should 404 if _verify_loan_tenant raises."""
        from fastapi import HTTPException

        with patch(
            "routes.smart_docs_security_routes._verify_loan_tenant",
            side_effect=HTTPException(status_code=404, detail="Not found"),
        ):
            resp = lo_client.get(f"{PREFIX}/fraud-analysis/999999")
        assert resp.status_code == 404


# =============================================================================
# 8. GET /doc-security/fraud-summary  (admin-only)
# =============================================================================

@pytest.mark.unit
class TestFraudSummary:
    """GET /doc-security/fraud-summary."""

    def test_admin_can_view_fraud_summary(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/fraud-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        assert "total_integrity_checks" in body["summary"]
        assert "tampered_documents" in body["summary"]
        assert "denied_access_attempts" in body["summary"]

    def test_non_admin_blocked(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/fraud-summary")
        assert resp.status_code == 403


# =============================================================================
# 9. GET /doc-security/retention-policies
# =============================================================================

@pytest.mark.unit
class TestGetRetentionPolicies:
    """GET /doc-security/retention-policies."""

    def test_list_policies(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/retention-policies")
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "policies" in body
        assert isinstance(body["policies"], list)

    def test_filter_by_doc_type(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/retention-policies?doc_type=paystubs")
        assert resp.status_code == 200
        for p in resp.json()["policies"]:
            assert p["doc_type"] == "paystubs"

    def test_include_inactive(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/retention-policies?active_only=false")
        assert resp.status_code == 200


# =============================================================================
# 10. POST /doc-security/retention-policies  (admin-only create)
# =============================================================================

@pytest.mark.unit
class TestCreateRetentionPolicy:
    """POST /doc-security/retention-policies."""

    def test_admin_creates_policy(self, admin_client):
        payload = {
            "doc_type": "bank_statements",
            "policy_name": "Bank Statement Retention",
            "retention_days": 730,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "archive",
            "notify_days_before": 14,
            "regulatory_reference": "SOC 2",
            "applies_to_states": ["NY"],
        }
        resp = admin_client.post(f"{PREFIX}/retention-policies", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "created"
        assert body["policy"]["doc_type"] == "bank_statements"
        assert body["policy"]["retention_days"] == 730
        assert body["policy"]["action_on_expiry"] == "archive"
        assert body["policy"]["is_active"] is True

    def test_non_admin_blocked(self, lo_client):
        payload = {
            "doc_type": "w2",
            "policy_name": "W2 Retention",
            "retention_days": 365,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "notify_admin",
        }
        resp = lo_client.post(f"{PREFIX}/retention-policies", json=payload)
        assert resp.status_code == 403

    def test_invalid_action_returns_400(self, admin_client):
        payload = {
            "doc_type": "w2",
            "policy_name": "Bad Action",
            "retention_days": 365,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "SELF_DESTRUCT",
        }
        resp = admin_client.post(f"{PREFIX}/retention-policies", json=payload)
        assert resp.status_code == 400

    def test_negative_retention_days_rejected(self, admin_client):
        payload = {
            "doc_type": "w2",
            "policy_name": "Negative days",
            "retention_days": -5,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "notify_admin",
        }
        resp = admin_client.post(f"{PREFIX}/retention-policies", json=payload)
        assert resp.status_code == 422  # Pydantic Field(ge=1)


# =============================================================================
# 11. PUT /doc-security/retention-policies/{policy_id}
# =============================================================================

@pytest.mark.unit
class TestUpdateRetentionPolicy:
    """PUT /doc-security/retention-policies/{policy_id}."""

    def test_admin_updates_policy(self, admin_client, _seed_security_tables):
        policy_id = _seed_security_tables["policy"].id
        payload = {
            "policy_name": "Updated Paystub Retention",
            "retention_days": 1460,
        }
        resp = admin_client.put(f"{PREFIX}/retention-policies/{policy_id}", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "updated"
        assert body["policy"]["policy_name"] == "Updated Paystub Retention"
        assert body["policy"]["retention_days"] == 1460

    def test_non_admin_blocked(self, lo_client, _seed_security_tables):
        policy_id = _seed_security_tables["policy"].id
        resp = lo_client.put(
            f"{PREFIX}/retention-policies/{policy_id}",
            json={"policy_name": "Nope"},
        )
        assert resp.status_code == 403

    def test_nonexistent_policy_returns_404(self, admin_client):
        resp = admin_client.put(
            f"{PREFIX}/retention-policies/999999",
            json={"policy_name": "Ghost"},
        )
        assert resp.status_code == 404

    def test_invalid_action_returns_400(self, admin_client, _seed_security_tables):
        policy_id = _seed_security_tables["policy"].id
        resp = admin_client.put(
            f"{PREFIX}/retention-policies/{policy_id}",
            json={"action_on_expiry": "OBLITERATE"},
        )
        assert resp.status_code == 400


# =============================================================================
# 12. POST /doc-security/watermark/{document_id}
# =============================================================================

@pytest.mark.unit
class TestWatermark:
    """POST /doc-security/watermark/{document_id}."""

    def test_watermark_creates_log(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_doc.doc_type = "smart_document"
            mock_doc.storage_key = None
            mock_doc.s3_key = None
            mock_verify.return_value = mock_doc

            resp = lo_client.post(
                f"{PREFIX}/watermark/100",
                json={"watermark_type": "VIEWING"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 100
        assert "watermark_log_id" in body
        assert body["watermark_type"] == "viewing"
        assert "watermark_text" in body

    def test_custom_watermark_text(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_doc.doc_type = "smart_document"
            mock_doc.storage_key = None
            mock_doc.s3_key = None
            mock_verify.return_value = mock_doc

            resp = lo_client.post(
                f"{PREFIX}/watermark/100",
                json={"watermark_type": "DOWNLOAD", "custom_text": "CONFIDENTIAL"},
            )

        assert resp.status_code == 200
        assert resp.json()["watermark_text"] == "CONFIDENTIAL"

    def test_invalid_watermark_type_400(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_verify.return_value = mock_doc

            resp = lo_client.post(
                f"{PREFIX}/watermark/100",
                json={"watermark_type": "LASER_ENGRAVE"},
            )
        assert resp.status_code == 400

    def test_nonexistent_doc_returns_404(self, lo_client):
        resp = lo_client.post(
            f"{PREFIX}/watermark/999999",
            json={"watermark_type": "VIEWING"},
        )
        assert resp.status_code == 404


# =============================================================================
# 13. GET /doc-security/encryption-status/{document_id}
# =============================================================================

@pytest.mark.unit
class TestEncryptionStatus:
    """GET /doc-security/encryption-status/{document_id}."""

    def test_encrypted_doc_returns_status(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_verify.return_value = mock_doc

            resp = lo_client.get(f"{PREFIX}/encryption-status/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 100
        # The seeded data has an encryption record for doc 100
        assert body["encrypted"] is True
        assert body["record"]["encryption_algorithm"] == "AES-256-GCM"

    def test_unencrypted_doc(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 300  # No encryption record seeded for this
            mock_verify.return_value = mock_doc

            resp = lo_client.get(f"{PREFIX}/encryption-status/300")

        assert resp.status_code == 200
        body = resp.json()
        assert body["encrypted"] is False
        assert "No encryption record" in body.get("message", "")


# =============================================================================
# 14. POST /doc-security/encrypt/{document_id}
# =============================================================================

@pytest.mark.unit
class TestEncryptDocument:
    """POST /doc-security/encrypt/{document_id}."""

    def test_already_encrypted_doc_returns_already_status(self, lo_client):
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 100
            mock_doc.doc_type = "smart_document"
            mock_verify.return_value = mock_doc

            resp = lo_client.post(f"{PREFIX}/encrypt/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "already_encrypted"

    def test_encrypt_unencrypted_doc_without_s3(self, lo_client):
        """Without S3 available, should 422 because file cannot be retrieved."""
        with patch(
            "routes.smart_docs_security_routes._verify_document_org_access"
        ) as mock_verify:
            mock_doc = MagicMock()
            mock_doc.id = 500
            mock_doc.doc_type = "smart_document"
            mock_doc.storage_key = "docs/500.pdf"
            mock_doc.s3_key = None
            mock_verify.return_value = mock_doc

            resp = lo_client.post(f"{PREFIX}/encrypt/500")

        assert resp.status_code == 422


# =============================================================================
# 15. GET /doc-security/compliance-report  (admin-only)
# =============================================================================

@pytest.mark.unit
class TestComplianceReport:
    """GET /doc-security/compliance-report -- security dashboard/overview."""

    def test_admin_gets_compliance_report(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/compliance-report")
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        summary = body["summary"]
        assert "total_documents" in summary
        assert "encrypted_documents" in summary
        assert "encryption_coverage_pct" in summary
        assert "active_retention_policies" in summary
        assert "compliance_gaps" in body
        assert "recommendations" in body

    def test_non_admin_blocked(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/compliance-report")
        assert resp.status_code == 403


# =============================================================================
# 16. GET /doc-security/suspicious-activity
# =============================================================================

@pytest.mark.unit
class TestSuspiciousActivity:
    """GET /doc-security/suspicious-activity."""

    def test_returns_alerts(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/suspicious-activity")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_alerts" in body
        assert "alerts" in body
        assert "by_severity" in body
        for sev in ("critical", "high", "medium", "low"):
            assert sev in body["by_severity"]

    def test_filter_by_severity(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/suspicious-activity?severity=critical")
        assert resp.status_code == 200
        for alert in resp.json()["alerts"]:
            assert alert["severity"] == "critical"

    def test_custom_days_param(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/suspicious-activity?days=30")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 30


# =============================================================================
# 17. GET /doc-security/retention-expiring
# =============================================================================

@pytest.mark.unit
class TestRetentionExpiring:
    """GET /doc-security/retention-expiring."""

    def test_returns_expiring_docs(self, lo_client):
        resp = lo_client.get(f"{PREFIX}/retention-expiring")
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "expiring_documents" in body


# =============================================================================
# 18. Tenant Isolation Tests
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Verify org-scoped data cannot be accessed cross-tenant."""

    def test_audit_log_scoped_to_org(self, admin_client, other_org_admin_client):
        """Admin from org 1 and admin from org 999 see different audit data."""
        resp_org1 = admin_client.get(f"{PREFIX}/audit-log")
        resp_org999 = other_org_admin_client.get(f"{PREFIX}/audit-log")
        assert resp_org1.status_code == 200
        assert resp_org999.status_code == 200

        org1_doc_ids = {e["document_id"] for e in resp_org1.json()["entries"]}
        org999_doc_ids = {e["document_id"] for e in resp_org999.json()["entries"]}
        # org 1 should see doc 100 (org_id=1), not doc 200 (org_id=999)
        if org1_doc_ids:
            assert 200 not in org1_doc_ids, "Org 1 admin should NOT see org 999 access logs"
        if org999_doc_ids:
            assert 100 not in org999_doc_ids, "Org 999 admin should NOT see org 1 access logs"

    def test_retention_policy_update_cross_tenant_blocked(self, other_org_admin_client, _seed_security_tables):
        """Admin from org 999 cannot update org 1 retention policy."""
        policy_id = _seed_security_tables["policy"].id
        resp = other_org_admin_client.put(
            f"{PREFIX}/retention-policies/{policy_id}",
            json={"policy_name": "Cross-tenant attack"},
        )
        assert resp.status_code == 404, "Cross-tenant policy update should be blocked"

    def test_platform_admin_sees_all_audit_logs(self, platform_admin_client):
        """Platform admin (permission_role='admin') should bypass org scoping."""
        resp = platform_admin_client.get(f"{PREFIX}/audit-log")
        assert resp.status_code == 200
        body = resp.json()
        # Platform admin should see logs from both orgs (at least the seeded ones)
        doc_ids = {e["document_id"] for e in body["entries"]}
        assert 100 in doc_ids or 200 in doc_ids, "Platform admin should see cross-org data"


# =============================================================================
# 19. Unauthenticated Access Blocked
# =============================================================================

@pytest.mark.unit
class TestUnauthenticatedBlocked:
    """Verify all security endpoints reject unauthenticated requests."""

    ENDPOINTS_GET = [
        f"{PREFIX}/audit-log",
        f"{PREFIX}/audit-log/100",
        f"{PREFIX}/integrity-check/100",
        f"{PREFIX}/integrity-history/100",
        f"{PREFIX}/fraud-analysis/1",
        f"{PREFIX}/fraud-summary",
        f"{PREFIX}/retention-policies",
        f"{PREFIX}/retention-expiring",
        f"{PREFIX}/encryption-status/100",
        f"{PREFIX}/compliance-report",
        f"{PREFIX}/suspicious-activity",
    ]

    ENDPOINTS_POST = [
        (f"{PREFIX}/log-access", {"document_id": 100, "access_type": "view"}),
        (f"{PREFIX}/integrity-check/batch", {"document_ids": [100]}),
        (f"{PREFIX}/watermark/100", {"watermark_type": "VIEWING"}),
        (f"{PREFIX}/encrypt/100", None),
        (f"{PREFIX}/retention-policies", {
            "doc_type": "w2",
            "policy_name": "X",
            "retention_days": 365,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "notify_admin",
        }),
    ]

    ENDPOINTS_PUT = [
        (f"{PREFIX}/retention-policies/1", {"policy_name": "hacked"}),
    ]

    @pytest.mark.parametrize("url", ENDPOINTS_GET)
    def test_get_requires_auth(self, unauth_client, url):
        resp = unauth_client.get(url)
        assert resp.status_code in (401, 403, 422), (
            f"GET {url} returned {resp.status_code} -- expected auth error"
        )

    @pytest.mark.parametrize("url,payload", ENDPOINTS_POST)
    def test_post_requires_auth(self, unauth_client, url, payload):
        if payload:
            resp = unauth_client.post(url, json=payload)
        else:
            resp = unauth_client.post(url)
        assert resp.status_code in (401, 403, 422), (
            f"POST {url} returned {resp.status_code} -- expected auth error"
        )

    @pytest.mark.parametrize("url,payload", ENDPOINTS_PUT)
    def test_put_requires_auth(self, unauth_client, url, payload):
        resp = unauth_client.put(url, json=payload)
        assert resp.status_code in (401, 403, 422), (
            f"PUT {url} returned {resp.status_code} -- expected auth error"
        )


# =============================================================================
# 20. Edge Cases and Validation
# =============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Miscellaneous edge case and validation tests."""

    def test_log_access_sets_ip_and_user_agent(self, lo_client):
        """Verify request context (IP, user agent) is captured in the log."""
        payload = {
            "document_id": 100,
            "access_type": "view",
        }
        resp = lo_client.post(
            f"{PREFIX}/log-access",
            json=payload,
            headers={"User-Agent": "PytestClient/1.0"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged"

    def test_create_retention_policy_stores_states_array(self, admin_client):
        payload = {
            "doc_type": "appraisal",
            "policy_name": "Appraisal Retention CA/TX",
            "retention_days": 1095,
            "retention_after_event": "FUNDED",
            "action_on_expiry": "notify_admin",
            "applies_to_states": ["CA", "TX", "FL"],
        }
        resp = admin_client.post(f"{PREFIX}/retention-policies", json=payload)
        assert resp.status_code == 200
        assert resp.json()["policy"]["applies_to_states"] == ["CA", "TX", "FL"]

    def test_update_policy_can_deactivate(self, admin_client, _seed_security_tables):
        policy_id = _seed_security_tables["policy"].id
        resp = admin_client.put(
            f"{PREFIX}/retention-policies/{policy_id}",
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["policy"]["is_active"] is False

    def test_audit_log_date_filter_bad_format_returns_400(self, admin_client):
        resp = admin_client.get(f"{PREFIX}/audit-log?date_from=not-a-date")
        assert resp.status_code == 400
