"""
Enterprise Endpoint Tests — Comprehensive coverage for new Perennia AI endpoints.

Covers:
  1. Security audit-log (POST /api/v1/security/audit-log)
  2. Certificate pins (GET /api/v1/security/certificate-pins, POST /api/v1/security/pin-failure)
  3. Dashboard summary (GET /api/v1/dashboard/summary)
  4. Rate alerts (GET /api/v1/rate-monitor/alerts/carplay, GET /api/v1/rate-alerts)
  5. Audit events service (audit_event(), PII sanitization, EventType)
  6. Tool router (classify_intents, intent patterns)
  7. Audit middleware (_normalize_path)

Uses fixtures from conftest.py: db_session, authenticated_client, client, mock_user.
"""

import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from database import get_db
from routes.auth_deps import require_auth, current_user_dep


# =============================================================================
# HELPERS
# =============================================================================

AUDIT_URL = "/api/v1/security/audit-log"
CERT_PINS_URL = "/api/v1/security/certificate-pins"
PIN_FAILURE_URL = "/api/v1/security/pin-failure"
DASHBOARD_SUMMARY_URL = "/api/v1/dashboard/summary"
RATE_MONITOR_ALERTS_URL = "/api/v1/rate-monitor/alerts/carplay"
RATE_ALERTS_URL = "/api/v1/rate-alerts"


class _MockUser:
    """Lightweight mock user for test fixtures."""

    def __init__(self, id=1, email="test@example.com", organization_id=1, role="loan_officer"):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.role = role
        self.is_active = True


DEVICE_INFO = {
    "model": "iPhone15,2",
    "osVersion": "17.4",
    "appVersion": "1.0.0",
}


def _compute_hash(entry_dict: dict) -> str:
    """Mirror the server-side hash computation."""
    dict_for_hash = {
        "id": entry_dict["id"],
        "timestamp": entry_dict["timestamp"],
        "event": entry_dict["event"],
        "details": entry_dict.get("details", {}),
        "deviceInfo": entry_dict["deviceInfo"],
        "previousHash": entry_dict["previousHash"],
    }
    serialized = json.dumps(dict_for_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _make_entry(event: str, previous_hash: str = "0" * 64, details: dict | None = None) -> dict:
    """Build a single audit entry with a correct hash."""
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": 1712764800.123,
        "event": event,
        "details": details or {},
        "deviceInfo": DEVICE_INFO,
        "synced": False,
        "previousHash": previous_hash,
    }
    entry["hash"] = _compute_hash(entry)
    return entry


def _make_chain(events: list[str]) -> list[dict]:
    """Build a list of hash-chained audit entries."""
    entries = []
    prev_hash = "0" * 64
    for event in events:
        entry = _make_entry(event, previous_hash=prev_hash)
        entries.append(entry)
        prev_hash = entry["hash"]
    return entries


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture()
def authed_client(db_session):
    """Test client with full auth overrides (security audit + dashboard)."""
    user = _MockUser()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_require_auth():
        return user

    async def override_current_user_dep():
        return user

    # Override auth deps used by routes
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[current_user_dep] = override_current_user_dep

    # Also override get_current_user_flexible for security_audit_routes
    try:
        from auth.dependencies import (
            get_current_user_flexible as auth_gcuf,
            get_current_user as auth_gcu,
        )

        async def override_gcuf(*args, **kwargs):
            return user

        async def override_gcu(*args, **kwargs):
            return user

        app.dependency_overrides[auth_gcuf] = override_gcuf
        app.dependency_overrides[auth_gcu] = override_gcu
    except ImportError:
        pass

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client(db_session):
    """Test client with NO auth overrides."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


# Need this import here (after sys.path manipulation)
from fastapi.testclient import TestClient


# =============================================================================
# 1. SECURITY AUDIT-LOG TESTS
# =============================================================================


@pytest.mark.unit
class TestSecurityAuditLogEndpoint:
    """POST /api/v1/security/audit-log — batch audit event ingestion."""

    def test_audit_log_valid_batch_returns_200(self, authed_client):
        """POST with valid hash-chained entries returns 200 and correct counts."""
        entries = _make_chain(["auth.success", "data.access", "app.foreground"])
        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["received"] == 3
        assert body["chain_valid"] is True

    def test_audit_log_requires_auth(self, unauthed_client):
        """POST without authentication returns 401 or 403."""
        entries = _make_chain(["auth.success"])
        response = unauthed_client.post(AUDIT_URL, json={"entries": entries})
        assert response.status_code in (401, 403)

    def test_audit_log_malformed_payload_returns_422(self, authed_client):
        """POST with entries missing required fields returns 422."""
        bad_entries = [
            {
                "id": "abc",
                # missing timestamp, event, deviceInfo, previousHash, hash
            }
        ]
        response = authed_client.post(AUDIT_URL, json={"entries": bad_entries})
        assert response.status_code == 422

    def test_audit_log_empty_entries_succeeds(self, authed_client):
        """POST with empty entries list returns 200 with received=0."""
        response = authed_client.post(AUDIT_URL, json={"entries": []})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["received"] == 0
        assert body["chain_valid"] is True

    def test_audit_log_broken_hash_chain(self, authed_client):
        """Entries with broken chain linkage return chain_valid=false."""
        entries = _make_chain(["auth.attempt", "auth.success", "data.access"])
        # Break the chain at index 1
        entries[1]["hash"] = "bad_" + entries[1]["hash"][4:]

        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        body = response.json()
        assert body["chain_valid"] is False
        assert body["received"] == 3

    def test_audit_log_security_events_logged_at_warning(self, authed_client, caplog):
        """Security-critical events produce WARNING log lines."""
        entries = _make_chain([
            "security.device_compromised",
            "security.violation",
        ])

        with caplog.at_level(logging.WARNING, logger="routes.security_audit_routes"):
            response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("device_compromised" in m for m in warning_messages), \
            "Expected WARNING log for security.device_compromised"
        assert any("violation" in m for m in warning_messages), \
            "Expected WARNING log for security.violation"

    def test_audit_log_single_entry(self, authed_client):
        """A single-entry batch is accepted with chain_valid=true."""
        entries = _make_chain(["auth.success"])
        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 1
        assert body["chain_valid"] is True

    def test_audit_log_with_details(self, authed_client):
        """Entries with non-empty details dict are accepted."""
        entries = _make_chain(["data.access"])
        entries[0]["details"] = {"resource": "loan_123", "action": "viewed"}
        # Recompute hash after modifying details
        entries[0]["hash"] = _compute_hash(entries[0])

        response = authed_client.post(AUDIT_URL, json={"entries": entries})
        assert response.status_code == 200
        assert response.json()["received"] == 1

    def test_audit_log_missing_entries_key(self, authed_client):
        """POST without 'entries' key returns 422."""
        response = authed_client.post(AUDIT_URL, json={"not_entries": []})
        assert response.status_code == 422

    def test_audit_log_invalid_json(self, authed_client):
        """POST with non-JSON body returns 422."""
        response = authed_client.post(
            AUDIT_URL,
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422


# =============================================================================
# 2. CERTIFICATE PINS TESTS
# =============================================================================


@pytest.mark.unit
class TestCertificatePinsEndpoint:
    """GET /api/v1/security/certificate-pins — public SPKI pin retrieval."""

    def test_get_certificate_pins_returns_200(self, client):
        """Endpoint returns 200 without any auth headers."""
        resp = client.get(CERT_PINS_URL)
        assert resp.status_code == 200

    def test_get_certificate_pins_has_valid_pin_format(self, client):
        """Response contains base64-encoded SHA-256 hashes for each domain."""
        import base64

        resp = client.get(CERT_PINS_URL)
        assert resp.status_code == 200
        data = resp.json()

        # Must contain both production domains
        assert "api.perenniaai.com" in data
        assert "app.perenniaai.com" in data

        for domain in ("api.perenniaai.com", "app.perenniaai.com"):
            entry = data[domain]
            assert "spkiHashes" in entry
            hashes = entry["spkiHashes"]
            assert isinstance(hashes, list)
            assert len(hashes) >= 3

            # Each hash should be valid base64 decoding to 32 bytes (SHA-256)
            for h in hashes:
                assert isinstance(h, str)
                assert len(h) > 0
                decoded = base64.b64decode(h)
                assert len(decoded) == 32, (
                    f"Hash for {domain} decoded to {len(decoded)} bytes, expected 32"
                )

    def test_get_certificate_pins_has_subdomains_and_notafter(self, client):
        """Each domain entry has includeSubdomains and notAfter fields."""
        resp = client.get(CERT_PINS_URL)
        data = resp.json()

        for domain in ("api.perenniaai.com", "app.perenniaai.com"):
            entry = data[domain]
            assert "includeSubdomains" in entry
            assert isinstance(entry["includeSubdomains"], bool)
            assert "notAfter" in entry

    def test_get_certificate_pins_no_auth_required(self, client):
        """The pins endpoint does not require authentication."""
        # Already uses the unauthenticated 'client' fixture
        resp = client.get(CERT_PINS_URL)
        assert resp.status_code == 200


@pytest.mark.unit
class TestPinFailureReportEndpoint:
    """POST /api/v1/security/pin-failure — pin failure reporting."""

    def _valid_payload(self):
        return {
            "reports": [
                {
                    "domain": "api.perenniaai.com",
                    "reason": "pin_mismatch",
                    "receivedHashes": ["abc123="],
                    "timestamp": "2026-04-10T12:00:00Z",
                    "platform": "iOS",
                    "appVersion": "1.0.0",
                }
            ],
            "deviceInfo": {
                "platform": "iOS",
                "isNative": True,
                "osVersion": "19.0",
                "model": "iPhone16,1",
            },
        }

    def test_pin_failure_accepts_valid_report(self, client):
        """Valid pin failure report returns 200 with success=True."""
        # Clear rate limit state before this test
        from routes.security_certificate_routes import _rate_limit_buckets
        _rate_limit_buckets.clear()

        resp = client.post(PIN_FAILURE_URL, json=self._valid_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_pin_failure_requires_no_auth(self, client):
        """Pin failure reporting does not require authentication (fire-and-forget)."""
        from routes.security_certificate_routes import _rate_limit_buckets
        _rate_limit_buckets.clear()

        resp = client.post(PIN_FAILURE_URL, json=self._valid_payload())
        assert resp.status_code == 200

    def test_pin_failure_validates_missing_fields(self, client):
        """Missing required fields return 422."""
        # Empty body
        resp = client.post(PIN_FAILURE_URL, json={})
        assert resp.status_code == 422

        # Empty reports array
        resp = client.post(PIN_FAILURE_URL, json={"reports": []})
        assert resp.status_code == 422

        # Report missing required 'domain'
        resp = client.post(
            PIN_FAILURE_URL,
            json={"reports": [{"reason": "pin_mismatch"}]},
        )
        assert resp.status_code == 422


# =============================================================================
# 3. DASHBOARD SUMMARY TESTS
# =============================================================================


def _seed_org(db_session, org_id=1, name="Test Org"):
    """Insert an Organization row if it doesn't already exist."""
    from database.models.core import Organization
    existing = db_session.get(Organization, org_id)
    if existing:
        return existing
    org = Organization(id=org_id, name=name)
    db_session.add(org)
    db_session.flush()
    return org


def _seed_loan(db_session, *, org_id, stage, loan_number, borrower="Test Borrower"):
    from database.models.lead_loan import Loan
    loan = Loan(
        organization_id=org_id,
        stage=stage,
        loan_number=loan_number,
        borrower_name=borrower,
        amount=400000,
    )
    db_session.add(loan)
    db_session.flush()
    return loan


def _seed_lead(db_session, *, org_id, created_at=None, name="Lead Test", email=None):
    from database.models.lead_loan import Lead
    lead = Lead(
        organization_id=org_id,
        name=name,
        email=email or f"{name.lower().replace(' ', '.')}@example.com",
        phone="+15550001234",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(lead)
    db_session.flush()
    return lead


def _seed_task(db_session, *, org_id, status="pending", due_date=None):
    from database.models.task import Task
    task = Task(
        organization_id=org_id,
        title="Follow up",
        status=status,
        due_date=due_date or datetime.now(timezone.utc),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.mark.integration
class TestDashboardSummaryEndpoint:
    """GET /api/v1/dashboard/summary — pipeline summary for iOS widgets."""

    def test_dashboard_summary_returns_200(self, authed_client, db_session):
        """Authenticated GET returns 200 with expected response shape."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        assert resp.status_code == 200

        data = resp.json()
        expected_keys = {
            "urgentTaskCount", "activeLoanCount", "rateAlertCount",
            "newLeadCount", "todayAppointmentCount", "pipelineSummary",
        }
        assert set(data.keys()) == expected_keys

    def test_dashboard_summary_requires_auth(self, unauthed_client):
        """GET without auth returns 401 or 403."""
        resp = unauthed_client.get(DASHBOARD_SUMMARY_URL)
        assert resp.status_code in (401, 403)

    def test_dashboard_summary_reflects_active_loans(self, authed_client, db_session):
        """Active loans (non-terminal stages) are counted correctly."""
        _seed_org(db_session, org_id=1)
        _seed_loan(db_session, org_id=1, stage="APPLICATION", loan_number="ENT-001")
        _seed_loan(db_session, org_id=1, stage="PROCESSING", loan_number="ENT-002")
        _seed_loan(db_session, org_id=1, stage="UNDERWRITING", loan_number="ENT-003")
        _seed_loan(db_session, org_id=1, stage="CTC", loan_number="ENT-004")
        db_session.commit()

        # Invalidate the in-memory cache to ensure fresh query
        try:
            from routes.dashboard_summary_routes import _cache_invalidate
            _cache_invalidate(1)
        except ImportError:
            pass

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 4
        pipeline = data["pipelineSummary"]
        assert pipeline["applicationCount"] == 1
        assert pipeline["processingCount"] == 1
        assert pipeline["underwritingCount"] == 1
        assert pipeline["clearToCloseCount"] == 1

    def test_dashboard_summary_excludes_terminal_stages(self, authed_client, db_session):
        """FUNDED, CANCELLED, DENIED, etc. are excluded from activeLoanCount."""
        _seed_org(db_session, org_id=1)
        _seed_loan(db_session, org_id=1, stage="FUNDED", loan_number="TERM-001")
        _seed_loan(db_session, org_id=1, stage="CANCELLED", loan_number="TERM-002")
        _seed_loan(db_session, org_id=1, stage="DENIED", loan_number="TERM-003")
        _seed_loan(db_session, org_id=1, stage="DEAD", loan_number="TERM-004")
        _seed_loan(db_session, org_id=1, stage="WITHDRAWN", loan_number="TERM-005")
        # One active for contrast
        _seed_loan(db_session, org_id=1, stage="APPLICATION", loan_number="ACT-001")
        db_session.commit()

        try:
            from routes.dashboard_summary_routes import _cache_invalidate
            _cache_invalidate(1)
        except ImportError:
            pass

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 1

    def test_dashboard_summary_empty_org_returns_zeros(self, authed_client, db_session):
        """An org with no data returns all-zero counts, not errors."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        try:
            from routes.dashboard_summary_routes import _cache_invalidate
            _cache_invalidate(1)
        except ImportError:
            pass

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 0
        assert data["urgentTaskCount"] == 0
        assert data["newLeadCount"] == 0
        assert data["rateAlertCount"] == 0
        assert data["todayAppointmentCount"] == 0

        pipeline = data["pipelineSummary"]
        for key in ("applicationCount", "processingCount", "underwritingCount", "clearToCloseCount"):
            assert pipeline[key] == 0

    def test_dashboard_summary_camel_case_keys(self, authed_client, db_session):
        """All keys are camelCase — no snake_case at top level (iOS Codable compat)."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        try:
            from routes.dashboard_summary_routes import _cache_invalidate
            _cache_invalidate(1)
        except ImportError:
            pass

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        data = resp.json()

        for key in data:
            assert "_" not in key, f"Snake-case key found at top level: {key}"

    def test_dashboard_summary_pipeline_structure(self, authed_client, db_session):
        """pipelineSummary contains exactly the four expected count fields."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        try:
            from routes.dashboard_summary_routes import _cache_invalidate
            _cache_invalidate(1)
        except ImportError:
            pass

        resp = authed_client.get(DASHBOARD_SUMMARY_URL)
        data = resp.json()
        pipeline = data["pipelineSummary"]

        expected_pipeline_keys = {
            "applicationCount", "processingCount",
            "underwritingCount", "clearToCloseCount",
        }
        assert set(pipeline.keys()) == expected_pipeline_keys

        for key, val in pipeline.items():
            assert isinstance(val, int), f"{key} should be int, got {type(val)}"


# =============================================================================
# 4. RATE ALERTS TESTS
# =============================================================================


@pytest.mark.unit
class TestRateMonitorAlertsEndpoint:
    """GET /api/v1/rate-monitor/alerts/carplay and GET /api/v1/rate-alerts."""

    def test_rate_monitor_alerts_returns_array(self, authenticated_client):
        """Response is a plain JSON array, not wrapped in an object."""
        response = authenticated_client.get(RATE_MONITOR_ALERTS_URL)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_rate_monitor_alerts_empty_returns_empty_list(self, authenticated_client):
        """Empty state returns [] not a 500 error."""
        response = authenticated_client.get(RATE_MONITOR_ALERTS_URL)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_rate_alerts_alias_returns_200(self, authenticated_client):
        """GET /api/v1/rate-alerts (alias) returns 200 with a JSON array."""
        response = authenticated_client.get(RATE_ALERTS_URL)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_rate_alerts_alias_empty_returns_empty_list(self, authenticated_client):
        """Alias endpoint returns [] when no alerts exist."""
        response = authenticated_client.get(RATE_ALERTS_URL)
        assert response.status_code == 200
        assert response.json() == []

    def test_rate_monitor_alerts_requires_auth(self, client):
        """GET /api/v1/rate-monitor/alerts/carplay without auth returns 401/403."""
        response = client.get(RATE_MONITOR_ALERTS_URL)
        assert response.status_code in (401, 403)

    def test_rate_alerts_alias_requires_auth(self, client):
        """GET /api/v1/rate-alerts without auth returns 401/403."""
        response = client.get(RATE_ALERTS_URL)
        assert response.status_code in (401, 403)

    def test_rate_monitor_alerts_limit_param(self, authenticated_client):
        """limit query param is accepted and validated (le=100)."""
        # Valid limit
        response = authenticated_client.get(f"{RATE_MONITOR_ALERTS_URL}?limit=5")
        assert response.status_code == 200

        # Limit exceeding max should return 422
        response_over = authenticated_client.get(f"{RATE_MONITOR_ALERTS_URL}?limit=200")
        assert response_over.status_code == 422

    def test_rate_alerts_limit_param(self, authenticated_client):
        """limit query param on alias endpoint is validated."""
        response = authenticated_client.get(f"{RATE_ALERTS_URL}?limit=3")
        assert response.status_code == 200

        response_over = authenticated_client.get(f"{RATE_ALERTS_URL}?limit=150")
        assert response_over.status_code == 422


# =============================================================================
# 5. AUDIT EVENTS SERVICE TESTS
# =============================================================================


@pytest.mark.unit
class TestAuditEventService:
    """Unit tests for services/audit_events.py."""

    def test_event_type_constants_are_correct_strings(self):
        """EventType constants are uppercase string values."""
        from services.audit_events import EventType

        assert EventType.USER_LOGIN == "USER_LOGIN"
        assert EventType.USER_LOGOUT == "USER_LOGOUT"
        assert EventType.LOAN_CREATED == "LOAN_CREATED"
        assert EventType.LOAN_STAGE_CHANGED == "LOAN_STAGE_CHANGED"
        assert EventType.DOCUMENT_UPLOADED == "DOCUMENT_UPLOADED"
        assert EventType.PII_VIEWED == "PII_VIEWED"
        assert EventType.PII_EXPORTED == "PII_EXPORTED"
        assert EventType.INTEGRATION_CONNECTED == "INTEGRATION_CONNECTED"
        assert EventType.CONFIG_CHANGED == "CONFIG_CHANGED"
        assert EventType.SECRET_ROTATED == "SECRET_ROTATED"
        assert EventType.PASSWORD_CHANGED == "PASSWORD_CHANGED"
        assert EventType.SESSION_REVOKED == "SESSION_REVOKED"

    def test_pii_sanitization_redacts_sensitive_keys(self):
        """_sanitize_metadata redacts PII-bearing keys."""
        from services.audit_events import _sanitize_metadata

        metadata = {
            "ssn": "123-45-6789",
            "password": "secret123",
            "api_key": "sk-abc123",
            "credit_card": "4111-1111-1111-1111",
            "bank_account": "9876543210",
            "routing_number": "021000021",
            "safe_field": "this stays",
            "user_action": "login",
        }

        sanitized = _sanitize_metadata(metadata)

        # PII keys must be redacted
        assert sanitized["ssn"] == "[REDACTED]"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["credit_card"] == "[REDACTED]"
        assert sanitized["bank_account"] == "[REDACTED]"
        assert sanitized["routing_number"] == "[REDACTED]"

        # Safe keys must be preserved
        assert sanitized["safe_field"] == "this stays"
        assert sanitized["user_action"] == "login"

    def test_pii_sanitization_nested_dicts(self):
        """_sanitize_metadata redacts PII in nested dicts."""
        from services.audit_events import _sanitize_metadata

        metadata = {
            "user": {
                "ssn": "123-45-6789",
                "name": "John Smith",
            },
            "context": "test",
        }

        sanitized = _sanitize_metadata(metadata)
        assert sanitized["user"]["ssn"] == "[REDACTED]"
        assert sanitized["user"]["name"] == "John Smith"
        assert sanitized["context"] == "test"

    def test_pii_sanitization_empty_dict(self):
        """_sanitize_metadata handles empty dict."""
        from services.audit_events import _sanitize_metadata

        assert _sanitize_metadata({}) == {}

    def test_pii_sanitization_case_insensitive(self):
        """_sanitize_metadata is case-insensitive for blocked keys."""
        from services.audit_events import _sanitize_metadata

        metadata = {
            "SSN": "123-45-6789",
            "Password": "secret",
            "API_KEY": "key123",
        }

        sanitized = _sanitize_metadata(metadata)
        assert sanitized["SSN"] == "[REDACTED]"
        assert sanitized["Password"] == "[REDACTED]"
        assert sanitized["API_KEY"] == "[REDACTED]"

    def test_audit_event_creates_record(self, db_session):
        """audit_event() creates an AuditEvent record in the database."""
        from services.audit_events import audit_event, EventType
        from database.models.audit_event import AuditEvent

        audit_event(
            db_session,
            event_type=EventType.USER_LOGIN,
            outcome="success",
            actor_id=None,
            actor_email="test@example.com",
            actor_role="loan_officer",
            org_id=None,
            resource_type="auth",
            resource_id="session_123",
            ip="127.0.0.1",
            user_agent="TestAgent/1.0",
            metadata={"source": "unit_test"},
        )
        db_session.flush()

        events = db_session.query(AuditEvent).filter(
            AuditEvent.event_type == EventType.USER_LOGIN,
        ).all()

        assert len(events) >= 1
        event = events[-1]
        assert event.event_type == "USER_LOGIN"
        assert event.outcome == "success"
        assert event.actor_email == "test@example.com"
        assert event.actor_role == "loan_officer"
        assert event.resource_type == "auth"
        assert event.resource_id == "session_123"

    def test_audit_event_persists_metadata(self, db_session):
        """audit_event() stores metadata as JSON, with PII redacted."""
        from services.audit_events import audit_event
        from database.models.audit_event import AuditEvent

        audit_event(
            db_session,
            event_type="TEST_META",
            metadata={
                "action": "test",
                "ssn": "123-45-6789",
                "loan_id": "loan_abc",
            },
        )
        db_session.flush()

        event = db_session.query(AuditEvent).filter(
            AuditEvent.event_type == "TEST_META",
        ).first()

        assert event is not None
        meta = event.metadata_json
        assert meta["action"] == "test"
        assert meta["ssn"] == "[REDACTED]"
        assert meta["loan_id"] == "loan_abc"

    def test_audit_event_does_not_raise_on_failure(self, db_session):
        """audit_event() logs but does not raise on failure."""
        from services.audit_events import audit_event

        # Mock db.add to raise an exception
        original_add = db_session.add
        db_session.add = MagicMock(side_effect=Exception("DB error"))

        # Should not raise
        audit_event(
            db_session,
            event_type="SHOULD_FAIL",
            metadata={"test": True},
        )

        db_session.add = original_add

    def test_coerce_uuid_handles_various_types(self):
        """_coerce_uuid handles None, UUID, int, and string inputs."""
        from services.audit_events import _coerce_uuid

        # None
        assert _coerce_uuid(None) is None

        # Already a UUID
        test_uuid = uuid.uuid4()
        assert _coerce_uuid(test_uuid) == test_uuid

        # Valid UUID string
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = _coerce_uuid(uuid_str)
        assert result == uuid.UUID(uuid_str)

        # Integer (non-UUID format) returns None
        assert _coerce_uuid(12345) is None

        # Invalid string returns None
        assert _coerce_uuid("not-a-uuid") is None

    def test_blocked_keys_completeness(self):
        """_BLOCKED_KEYS covers critical PII and credential fields."""
        from services.audit_events import _BLOCKED_KEYS

        critical_keys = {
            "ssn", "password", "api_key", "credit_card",
            "bank_account", "routing_number", "date_of_birth",
            "drivers_license", "secret", "token", "cvv",
        }
        assert critical_keys.issubset(_BLOCKED_KEYS), (
            f"Missing blocked keys: {critical_keys - _BLOCKED_KEYS}"
        )


# =============================================================================
# 6. TOOL ROUTER TESTS
# =============================================================================


@pytest.mark.unit
class TestToolRouter:
    """Unit tests for agents/tools/tool_router.py — intent classification."""

    def test_classify_intents_loan_query(self):
        """'show me loan pipeline' includes 'loan_query' intent."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("show me loan pipeline")
        assert "loan_query" in intents

    def test_classify_intents_borrower_contact(self):
        """'call the borrower' includes 'borrower_contact' intent."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("call the borrower")
        assert "borrower_contact" in intents

    def test_classify_intents_document_handling(self):
        """Document-related messages classify as 'document_handling'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("upload the W-2 document")
        assert "document_handling" in intents

    def test_classify_intents_guidelines_lookup(self):
        """'what are FHA guidelines' includes 'guidelines_lookup'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("what are FHA guidelines for DTI")
        assert "guidelines_lookup" in intents

    def test_classify_intents_calculation(self):
        """'calculate the monthly payment' includes 'calculation'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("calculate the monthly payment for $450,000")
        assert "calculation" in intents

    def test_classify_intents_scheduling(self):
        """'schedule a meeting' includes 'scheduling'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("schedule a meeting with the client")
        assert "scheduling" in intents

    def test_classify_intents_pipeline_mgmt(self):
        """'assign the lead' includes 'pipeline_mgmt'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("assign this lead to John")
        assert "pipeline_mgmt" in intents

    def test_classify_intents_reporting(self):
        """'show me the dashboard' includes 'reporting'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("show me the dashboard metrics")
        assert "reporting" in intents

    def test_classify_intents_outreach(self):
        """'send a mass campaign' includes 'outreach'."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("send a mass outreach campaign")
        assert "outreach" in intents

    def test_classify_intents_empty_message(self):
        """Empty message returns empty set."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("")
        assert intents == set()

    def test_classify_intents_unrelated_message(self):
        """Generic message with no mortgage keywords returns empty set."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents("hello how are you today")
        assert intents == set()

    def test_classify_intents_multiple_intents(self):
        """A complex message can match multiple intents."""
        from agents.tools.tool_router import classify_intents

        intents = classify_intents(
            "call the borrower and schedule a meeting to discuss the loan application"
        )
        assert "borrower_contact" in intents
        assert "scheduling" in intents
        assert "loan_query" in intents

    def test_classify_intents_case_insensitive(self):
        """Intent classification is case-insensitive."""
        from agents.tools.tool_router import classify_intents

        intents_lower = classify_intents("show me the loan pipeline")
        intents_upper = classify_intents("Show Me The LOAN Pipeline")
        assert intents_lower == intents_upper

    def test_intent_patterns_dict_has_expected_keys(self):
        """INTENT_PATTERNS covers all expected intent categories."""
        from agents.tools.tool_router import INTENT_PATTERNS

        expected_intents = {
            "loan_query", "borrower_contact", "document_handling",
            "guidelines_lookup", "calculation", "scheduling",
            "pipeline_mgmt", "reporting", "outreach",
        }
        assert expected_intents == set(INTENT_PATTERNS.keys())

    def test_always_on_tools_exist(self):
        """ALWAYS_ON_TOOL_NAMES contains essential utility tools."""
        from agents.tools.tool_router import ALWAYS_ON_TOOL_NAMES

        assert "get_current_user" in ALWAYS_ON_TOOL_NAMES
        assert "get_current_datetime" in ALWAYS_ON_TOOL_NAMES
        assert "search_across_all" in ALWAYS_ON_TOOL_NAMES

    def test_agent_domain_map_has_aria(self):
        """AGENT_DOMAIN_MAP includes the Aria agent."""
        from agents.tools.tool_router import AGENT_DOMAIN_MAP

        assert "aria" in AGENT_DOMAIN_MAP
        aria_domains = AGENT_DOMAIN_MAP["aria"]
        assert "pipeline" in aria_domains
        assert "borrower" in aria_domains
        assert "communication" in aria_domains

    def test_route_tools_returns_tools(self):
        """route_tools_for_agent returns a list of tools."""
        from agents.tools.tool_router import route_tools_for_agent

        mock_tools = [{"name": "tool1"}, {"name": "tool2"}]
        result = route_tools_for_agent(
            agent_type="aria",
            user_role="loan_officer",
            user_message="show me loan pipeline",
            all_tools=mock_tools,
        )
        assert isinstance(result, list)
        assert len(result) > 0

    def test_recent_use_count(self):
        """_recent_use_count correctly counts tool usage."""
        from agents.tools.tool_router import _recent_use_count

        recent = ["tool_a", "tool_b", "tool_a", "tool_c", "tool_a"]
        assert _recent_use_count("tool_a", recent) == 3
        assert _recent_use_count("tool_b", recent) == 1
        assert _recent_use_count("tool_d", recent) == 0


# =============================================================================
# 7. AUDIT MIDDLEWARE TESTS
# =============================================================================


@pytest.mark.unit
class TestAuditMiddleware:
    """Unit tests for middleware/audit_middleware.py — path normalization."""

    def test_normalize_path_replaces_uuids(self):
        """_normalize_path replaces UUID path segments with :id."""
        from middleware.audit_middleware import _normalize_path

        uuid_val = "550e8400-e29b-41d4-a716-446655440000"
        path = f"/api/v1/loans/{uuid_val}/stage"
        normalized = _normalize_path(path)

        assert ":id" in normalized
        assert uuid_val not in normalized
        assert normalized == "/api/v1/loans/:id/stage"

    def test_normalize_path_replaces_numeric_ids(self):
        """_normalize_path replaces numeric path segments with :id."""
        from middleware.audit_middleware import _normalize_path

        path = "/api/v1/leads/12345/notes"
        normalized = _normalize_path(path)

        assert ":id" in normalized
        assert "12345" not in normalized
        assert normalized == "/api/v1/leads/:id/notes"

    def test_normalize_path_preserves_non_id_segments(self):
        """_normalize_path keeps non-ID text segments unchanged."""
        from middleware.audit_middleware import _normalize_path

        path = "/api/v1/dashboard/summary"
        normalized = _normalize_path(path)
        assert normalized == "/api/v1/dashboard/summary"

    def test_normalize_path_multiple_ids(self):
        """_normalize_path replaces multiple IDs in one path."""
        from middleware.audit_middleware import _normalize_path

        uuid1 = "550e8400-e29b-41d4-a716-446655440000"
        path = f"/api/v1/orgs/{uuid1}/users/42/roles"
        normalized = _normalize_path(path)

        assert normalized == "/api/v1/orgs/:id/users/:id/roles"

    def test_normalize_path_empty_path(self):
        """_normalize_path handles root path."""
        from middleware.audit_middleware import _normalize_path

        normalized = _normalize_path("/")
        assert normalized == "/"

    def test_normalize_path_no_ids(self):
        """_normalize_path returns path unchanged when no IDs present."""
        from middleware.audit_middleware import _normalize_path

        path = "/api/v1/health"
        normalized = _normalize_path(path)
        assert normalized == "/api/v1/health"

    def test_normalize_path_uuid_at_end(self):
        """_normalize_path handles UUID at the end of the path."""
        from middleware.audit_middleware import _normalize_path

        uuid_val = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{uuid_val}"
        normalized = _normalize_path(path)
        assert normalized == "/api/v1/documents/:id"

    def test_normalize_path_numeric_at_end(self):
        """_normalize_path handles numeric ID at the end of the path."""
        from middleware.audit_middleware import _normalize_path

        path = "/api/v1/tasks/99"
        normalized = _normalize_path(path)
        assert normalized == "/api/v1/tasks/:id"

    def test_exempt_paths_defined(self):
        """EXEMPT_PATHS includes expected webhook/health/auth paths."""
        from middleware.audit_middleware import EXEMPT_PATHS

        assert "/health" in EXEMPT_PATHS
        assert "/auth/" in EXEMPT_PATHS
        assert "/docs" in EXEMPT_PATHS
        assert "/webhooks/" in EXEMPT_PATHS

    def test_mutating_methods_defined(self):
        """MUTATING_METHODS includes POST, PUT, PATCH, DELETE."""
        from middleware.audit_middleware import MUTATING_METHODS

        assert MUTATING_METHODS == {"POST", "PUT", "PATCH", "DELETE"}


# =============================================================================
# 8. USAGE TRACKER TESTS (unit — mocked Redis)
# =============================================================================


@pytest.mark.unit
class TestUsageTracker:
    """Unit tests for agents/tools/usage_tracker.py."""

    def test_tool_usage_stats_call_rate(self):
        """ToolUsageStats.call_rate computes correctly."""
        from agents.tools.usage_tracker import ToolUsageStats

        stats = ToolUsageStats(tool_name="test_tool", month="2026-04", routed=100, called=75)
        assert stats.call_rate == 0.75

    def test_tool_usage_stats_call_rate_zero_routed(self):
        """call_rate returns 0.0 when routed is 0 (avoid division by zero)."""
        from agents.tools.usage_tracker import ToolUsageStats

        stats = ToolUsageStats(tool_name="test_tool", month="2026-04", routed=0, called=0)
        assert stats.call_rate == 0.0

    def test_usage_tracker_no_redis_record_routing_noop(self):
        """record_routing is a no-op when redis is None."""
        import asyncio
        from agents.tools.usage_tracker import UsageTracker

        tracker = UsageTracker(redis_client=None)
        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            tracker.record_routing(
                agent_type="aria",
                role="loan_officer",
                intents={"loan_query"},
                selected=["tool_a", "tool_b"],
            )
        )

    def test_usage_tracker_no_redis_record_call_noop(self):
        """record_call is a no-op when redis is None."""
        import asyncio
        from agents.tools.usage_tracker import UsageTracker

        tracker = UsageTracker(redis_client=None)
        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            tracker.record_call(agent_type="aria", tool_name="test_tool")
        )

    def test_usage_tracker_no_redis_monthly_stats_empty(self):
        """monthly_stats returns [] when redis is None."""
        import asyncio
        from agents.tools.usage_tracker import UsageTracker

        tracker = UsageTracker(redis_client=None)
        result = asyncio.get_event_loop().run_until_complete(tracker.monthly_stats())
        assert result == []

    def test_month_key_format(self):
        """_month_key returns YYYY-MM format."""
        from agents.tools.usage_tracker import _month_key

        key = _month_key()
        assert len(key) == 7  # "2026-04"
        assert key[4] == "-"
        year, month = key.split("-")
        assert year.isdigit()
        assert month.isdigit()
        assert 1 <= int(month) <= 12


# =============================================================================
# 9. RATE MONITOR TRANSFORM HELPER TESTS
# =============================================================================


@pytest.mark.unit
class TestRateMonitorTransformHelpers:
    """Unit tests for rate_monitor_routes.py transform functions."""

    def test_loan_type_to_rate_type_conventional_30(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("conventional", 30) == "30yr_fixed"

    def test_loan_type_to_rate_type_conventional_15(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("conventional", 15) == "15yr_fixed"

    def test_loan_type_to_rate_type_fha(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("fha", 30) == "fha"

    def test_loan_type_to_rate_type_va(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("VA", 30) == "va"

    def test_loan_type_to_rate_type_none_defaults(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type(None, 30) == "30yr_fixed"

    def test_alert_to_carplay_dict_direction_down(self):
        """Market rate lower than client rate = 'down' direction."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict

        row = {
            "id": 42,
            "client_rate": 7.25,
            "market_rate": 6.50,
            "loan_type": "conventional",
            "loan_term": 30,
            "created_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
        result = _alert_to_carplay_dict(row)

        assert result["id"] == 42
        assert result["rate_type"] == "30yr_fixed"
        assert result["current_rate"] == 6.50
        assert result["previous_rate"] == 7.25
        assert result["change_direction"] == "down"

    def test_alert_to_carplay_dict_direction_up(self):
        """Market rate higher than client rate = 'up' direction."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict

        row = {
            "id": 43,
            "client_rate": 6.00,
            "market_rate": 6.75,
            "loan_type": "conventional",
            "loan_term": 30,
            "created_at": None,
        }
        result = _alert_to_carplay_dict(row)
        assert result["change_direction"] == "up"

    def test_alert_to_carplay_dict_none_row(self):
        """None row returns None."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict
        assert _alert_to_carplay_dict(None) is None

    def test_alert_to_carplay_dict_missing_id(self):
        """Row without id returns None."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict
        assert _alert_to_carplay_dict({"client_rate": 7.0}) is None

    def test_alert_to_background_dict_shape(self):
        """Background sync dict has correct shape with string id."""
        from routes.rate_monitor_routes import _alert_to_background_dict

        row = {
            "id": 55,
            "client_rate": 7.00,
            "market_rate": 6.25,
            "loan_type": "fha",
            "loan_term": 30,
            "created_at": datetime(2026, 4, 2, 14, 0, 0, tzinfo=timezone.utc),
        }
        result = _alert_to_background_dict(row)

        assert result["id"] == "55"
        assert result["product_name"] == "FHA"
        assert result["current_rate"] == 6.25
        assert result["previous_rate"] == 7.00
        assert result["change_direction"] == "down"

    def test_alert_to_background_dict_product_names(self):
        """Product names map correctly for all loan types."""
        from routes.rate_monitor_routes import _alert_to_background_dict

        cases = {
            ("conventional", 30): "30-Year Fixed",
            ("conventional", 15): "15-Year Fixed",
            ("fha", 30): "FHA",
            ("va", 30): "VA",
            ("usda", 30): "USDA",
            ("jumbo", 30): "Jumbo",
        }
        for (loan_type, loan_term), expected_name in cases.items():
            row = {
                "id": 1,
                "client_rate": 7.0,
                "market_rate": 6.5,
                "loan_type": loan_type,
                "loan_term": loan_term,
                "created_at": None,
            }
            result = _alert_to_background_dict(row)
            assert result["product_name"] == expected_name, (
                f"loan_type={loan_type}, loan_term={loan_term}: "
                f"expected '{expected_name}', got '{result['product_name']}'"
            )

    def test_safe_float_handles_none(self):
        """_safe_float returns default for None."""
        from routes.rate_monitor_routes import _safe_float
        assert _safe_float(None) == 0.0
        assert _safe_float(None, 5.0) == 5.0

    def test_safe_float_handles_invalid(self):
        """_safe_float returns default for non-numeric strings."""
        from routes.rate_monitor_routes import _safe_float
        assert _safe_float("not_a_number") == 0.0

    def test_safe_float_handles_valid(self):
        """_safe_float converts valid values."""
        from routes.rate_monitor_routes import _safe_float
        assert _safe_float(6.5) == 6.5
        assert _safe_float("7.25") == 7.25
        assert _safe_float(0) == 0.0


# =============================================================================
# 10. SECURITY AUDIT ROUTE — DERIVE OUTCOME TESTS
# =============================================================================


@pytest.mark.unit
class TestDeriveOutcome:
    """Unit tests for _derive_outcome in security_audit_routes."""

    def test_derive_outcome_failure_events(self):
        """Events containing 'failure', 'compromised', 'violation' return 'failure'."""
        from routes.security_audit_routes import _derive_outcome

        assert _derive_outcome("auth.failure") == "failure"
        assert _derive_outcome("biometric.failure") == "failure"
        assert _derive_outcome("security.device_compromised") == "failure"
        assert _derive_outcome("security.violation") == "failure"

    def test_derive_outcome_blocked_events(self):
        """Events containing 'blocked' return 'denied'."""
        from routes.security_audit_routes import _derive_outcome

        assert _derive_outcome("feature.blocked") == "denied"

    def test_derive_outcome_success_events(self):
        """Normal events return 'success'."""
        from routes.security_audit_routes import _derive_outcome

        assert _derive_outcome("auth.success") == "success"
        assert _derive_outcome("data.access") == "success"
        assert _derive_outcome("app.foreground") == "success"
        assert _derive_outcome("carplay.connected") == "success"

    def test_valid_event_types_set(self):
        """VALID_EVENT_TYPES includes all expected iOS event types."""
        from routes.security_audit_routes import VALID_EVENT_TYPES

        # Authentication events
        assert "auth.attempt" in VALID_EVENT_TYPES
        assert "auth.success" in VALID_EVENT_TYPES
        assert "auth.failure" in VALID_EVENT_TYPES
        assert "auth.logout" in VALID_EVENT_TYPES

        # Security events
        assert "security.device_compromised" in VALID_EVENT_TYPES
        assert "security.violation" in VALID_EVENT_TYPES
        assert "security.pin_failure" in VALID_EVENT_TYPES

        # CarPlay events
        assert "carplay.connected" in VALID_EVENT_TYPES
        assert "carplay.disconnected" in VALID_EVENT_TYPES

        # App lifecycle events
        assert "app.foreground" in VALID_EVENT_TYPES
        assert "app.background" in VALID_EVENT_TYPES

    def test_verify_chain_empty_list(self):
        """_verify_chain with empty list returns True."""
        from routes.security_audit_routes import _verify_chain
        assert _verify_chain([]) is True


# =============================================================================
# 11. DASHBOARD CACHE TESTS
# =============================================================================


@pytest.mark.unit
class TestDashboardCache:
    """Unit tests for the in-memory cache in dashboard_summary_routes."""

    def test_cache_set_and_get(self):
        """_cache_set stores data, _cache_get retrieves it."""
        from routes.dashboard_summary_routes import _cache_set, _cache_get, _cache_invalidate

        _cache_invalidate(99999)  # Ensure clean state
        test_data = {"activeLoanCount": 5, "urgentTaskCount": 2}
        _cache_set(99999, test_data)

        result = _cache_get(99999)
        assert result is not None
        assert result["activeLoanCount"] == 5

        # Cleanup
        _cache_invalidate(99999)

    def test_cache_invalidate(self):
        """_cache_invalidate removes the cached entry."""
        from routes.dashboard_summary_routes import _cache_set, _cache_get, _cache_invalidate

        _cache_set(99998, {"test": True})
        assert _cache_get(99998) is not None

        removed = _cache_invalidate(99998)
        assert removed is True
        assert _cache_get(99998) is None

    def test_cache_invalidate_nonexistent(self):
        """_cache_invalidate returns False for non-existent keys."""
        from routes.dashboard_summary_routes import _cache_invalidate

        removed = _cache_invalidate(77777)
        assert removed is False
