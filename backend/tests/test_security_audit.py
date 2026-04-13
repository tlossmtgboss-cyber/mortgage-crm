"""
Tests for POST /api/v1/security/audit-log

Validates authentication gating, payload validation, hash chain
verification, empty batch handling, and security-event log levels.

These tests do NOT require a running database -- the audit-log endpoint
is purely in-memory (validates payloads, checks hash chains, logs).
"""

import hashlib
import json
import logging
import os
import sys
import uuid

# Python 3.14 + FastAPI merged_lifespan recurse once per included router.
# This app has hundreds of routers, so the default limit (1000) is too low.
sys.setrecursionlimit(5000)

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import get_db
from routes.auth_deps import require_auth, current_user_dep


# =============================================================================
# HELPERS
# =============================================================================

AUDIT_URL = "/api/v1/security/audit-log"

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

class _MockUser:
    id = 1
    email = "test@example.com"
    organization_id = 1
    role = "loan_officer"
    is_active = True


def _noop_get_db():
    """Dummy get_db -- the audit endpoint never touches the database."""
    yield None


@pytest.fixture()
def authed_client():
    """Test client with auth overrides for the security audit router."""
    mock_user = _MockUser()

    async def override_require_auth():
        return mock_user

    async def override_current_user_dep():
        return mock_user

    app.dependency_overrides[get_db] = _noop_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[current_user_dep] = override_current_user_dep

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client():
    """Test client with NO auth overrides -- requests should be rejected."""
    app.dependency_overrides[get_db] = _noop_get_db
    # Intentionally NOT overriding auth dependencies
    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()


# =============================================================================
# TESTS
# =============================================================================


class TestSecurityAuditAuth:
    """Authentication gating."""

    def test_audit_log_requires_auth(self, unauthed_client):
        """Unauthenticated request returns 401 or 403."""
        response = unauthed_client.post(AUDIT_URL, json={"entries": []})
        assert response.status_code in (401, 403)


class TestSecurityAuditValidBatch:
    """Happy-path batch acceptance."""

    def test_audit_log_accepts_valid_batch(self, authed_client):
        """Valid entries return 200 with status ok and correct received count."""
        entries = _make_chain(["auth.success", "data.access", "app.foreground"])

        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["received"] == 3
        assert body["chain_valid"] is True


class TestSecurityAuditValidation:
    """Malformed payload handling."""

    def test_audit_log_validates_entries(self, authed_client):
        """Missing required fields in entries produce a 422 validation error."""
        bad_entries = [
            {
                "id": "abc",
                # missing timestamp, event, deviceInfo, previousHash, hash
            }
        ]

        response = authed_client.post(AUDIT_URL, json={"entries": bad_entries})
        assert response.status_code == 422


class TestSecurityAuditHashChain:
    """Hash chain integrity verification."""

    def test_audit_log_hash_chain_verification(self, authed_client):
        """A properly chained batch returns chain_valid: true."""
        entries = _make_chain(["auth.attempt", "auth.success"])

        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        assert response.json()["chain_valid"] is True

    def test_audit_log_broken_chain(self, authed_client):
        """A batch with broken chain linkage returns chain_valid: false."""
        entries = _make_chain(["auth.attempt", "auth.success", "data.access"])

        # Break the chain: overwrite the middle entry's hash so entry[2].previousHash
        # no longer matches entry[1].hash.
        entries[1]["hash"] = "bad_" + entries[1]["hash"][4:]

        response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200
        body = response.json()
        assert body["chain_valid"] is False
        assert body["received"] == 3


class TestSecurityAuditEmptyBatch:
    """Edge case: empty entries list."""

    def test_audit_log_empty_batch(self, authed_client):
        """Empty entries list returns 200 with received: 0 and chain_valid: true."""
        response = authed_client.post(AUDIT_URL, json={"entries": []})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["received"] == 0
        assert body["chain_valid"] is True


class TestSecurityAuditLogging:
    """Log-level categorization for security-critical events."""

    def test_audit_log_security_events_logged(self, authed_client, caplog):
        """Security-critical events (device_compromised, violation) are logged at WARNING."""
        entries = _make_chain([
            "security.device_compromised",
            "security.violation",
        ])

        with caplog.at_level(logging.WARNING, logger="routes.security_audit_routes"):
            response = authed_client.post(AUDIT_URL, json={"entries": entries})

        assert response.status_code == 200

        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        # Both security-critical events should have produced WARNING log lines
        compromised_logged = any("device_compromised" in m for m in warning_messages)
        violation_logged = any("violation" in m for m in warning_messages)
        assert compromised_logged, "Expected WARNING log for security.device_compromised"
        assert violation_logged, "Expected WARNING log for security.violation"
