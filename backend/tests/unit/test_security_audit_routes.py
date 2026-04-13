"""
Tests for routes/security_audit_routes.py — Mobile Security Audit Log

Validates hash chain verification, event persistence, category derivation,
and the query endpoint.
"""

import pytest
import hashlib
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# 1. Hash chain helpers
# ---------------------------------------------------------------------------

class TestDeriveCategory:
    def test_auth_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("auth.success") == "auth"
        assert _derive_category("auth.failure") == "auth"

    def test_security_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("security.violation") == "security"
        assert _derive_category("security.pin_failure") == "security"

    def test_biometric_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("biometric.success") == "biometric"

    def test_data_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("data.access") == "data"

    def test_carplay_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("carplay.connected") == "carplay"

    def test_app_events(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("app.foreground") == "app"

    def test_unknown_prefix(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("custom.event") == "unknown"

    def test_no_dot_separator(self):
        from routes.security_audit_routes import _derive_category
        assert _derive_category("nodotshere") == "unknown"


class TestComputeEntryHash:
    def test_produces_sha256_hex(self):
        from routes.security_audit_routes import _compute_entry_hash, AuditEntry, DeviceInfo

        entry = AuditEntry(
            id="test-uuid",
            timestamp=1712764800.0,
            event="auth.success",
            details={"method": "biometric"},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="placeholder",
        )
        result = _compute_entry_hash(entry)
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        from routes.security_audit_routes import _compute_entry_hash, AuditEntry, DeviceInfo

        entry = AuditEntry(
            id="test-uuid",
            timestamp=1712764800.0,
            event="auth.success",
            details={},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="ignored",
        )
        assert _compute_entry_hash(entry) == _compute_entry_hash(entry)

    def test_different_inputs_produce_different_hashes(self):
        from routes.security_audit_routes import _compute_entry_hash, AuditEntry, DeviceInfo

        entry1 = AuditEntry(
            id="uuid-1",
            timestamp=1712764800.0,
            event="auth.success",
            details={},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="x",
        )
        entry2 = AuditEntry(
            id="uuid-2",
            timestamp=1712764800.0,
            event="auth.failure",
            details={},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="x",
        )
        assert _compute_entry_hash(entry1) != _compute_entry_hash(entry2)


class TestVerifyChain:
    def _make_entry(self, entry_id, event, prev_hash):
        from routes.security_audit_routes import AuditEntry, DeviceInfo, _compute_entry_hash

        entry = AuditEntry(
            id=entry_id,
            timestamp=1712764800.0,
            event=event,
            details={},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash=prev_hash,
            hash="placeholder",
        )
        # Set hash to the computed value for a valid chain
        entry.hash = _compute_entry_hash(entry)
        return entry

    def test_empty_chain_is_valid(self):
        from routes.security_audit_routes import _verify_chain
        assert _verify_chain([]) is True

    def test_single_entry_is_valid(self):
        from routes.security_audit_routes import _verify_chain
        entry = self._make_entry("e1", "auth.success", "0" * 64)
        assert _verify_chain([entry]) is True

    def test_valid_chain_passes(self):
        from routes.security_audit_routes import _verify_chain
        e1 = self._make_entry("e1", "auth.success", "0" * 64)
        e2 = self._make_entry("e2", "auth.logout", e1.hash)
        assert _verify_chain([e1, e2]) is True

    def test_broken_chain_fails(self):
        from routes.security_audit_routes import _verify_chain
        e1 = self._make_entry("e1", "auth.success", "0" * 64)
        e2 = self._make_entry("e2", "auth.logout", "wrong_hash")
        assert _verify_chain([e1, e2]) is False


# ---------------------------------------------------------------------------
# 2. Valid event types
# ---------------------------------------------------------------------------

class TestValidEventTypes:
    def test_auth_events_included(self):
        from routes.security_audit_routes import VALID_EVENT_TYPES
        assert "auth.attempt" in VALID_EVENT_TYPES
        assert "auth.success" in VALID_EVENT_TYPES
        assert "auth.failure" in VALID_EVENT_TYPES
        assert "auth.logout" in VALID_EVENT_TYPES

    def test_security_events_included(self):
        from routes.security_audit_routes import VALID_EVENT_TYPES
        assert "security.device_compromised" in VALID_EVENT_TYPES
        assert "security.pin_failure" in VALID_EVENT_TYPES

    def test_carplay_events_included(self):
        from routes.security_audit_routes import VALID_EVENT_TYPES
        assert "carplay.connected" in VALID_EVENT_TYPES
        assert "carplay.disconnected" in VALID_EVENT_TYPES

    def test_app_lifecycle_events_included(self):
        from routes.security_audit_routes import VALID_EVENT_TYPES
        assert "app.foreground" in VALID_EVENT_TYPES
        assert "app.background" in VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# 3. POST endpoint — receive audit log
# ---------------------------------------------------------------------------

class TestReceiveAuditLog:
    @pytest.mark.asyncio
    async def test_empty_entries_returns_ok(self):
        from routes.security_audit_routes import receive_audit_log, AuditLogRequest

        user = MagicMock()
        user.id = 1
        user.organization_id = 100

        payload = AuditLogRequest(entries=[])
        result = await receive_audit_log(payload=payload, current_user=user, db=MagicMock())

        assert result.status == "ok"
        assert result.received == 0
        assert result.chain_valid is True

    @pytest.mark.asyncio
    async def test_persists_events_to_database(self):
        from routes.security_audit_routes import (
            receive_audit_log,
            AuditLogRequest,
            AuditEntry,
            DeviceInfo,
        )

        user = MagicMock()
        user.id = 1
        user.organization_id = 100

        entry = AuditEntry(
            id="uuid-1",
            timestamp=1712764800.0,
            event="auth.success",
            details={"method": "password"},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="a" * 64,
        )

        mock_db = MagicMock()
        payload = AuditLogRequest(entries=[entry])

        with patch("database.models.audit.MobileAuditEvent") as MockModel:
            MockModel.return_value = MagicMock()
            result = await receive_audit_log(payload=payload, current_user=user, db=mock_db)

        assert result.status == "ok"
        assert result.received == 1
        assert result.persisted == 1
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_failure_still_returns_ok(self):
        """Endpoint should never fail the request on DB errors."""
        from routes.security_audit_routes import (
            receive_audit_log,
            AuditLogRequest,
            AuditEntry,
            DeviceInfo,
        )

        user = MagicMock()
        user.id = 1
        user.organization_id = 100

        entry = AuditEntry(
            id="uuid-1",
            timestamp=1712764800.0,
            event="auth.success",
            details={},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="a" * 64,
        )

        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("DB connection lost")

        payload = AuditLogRequest(entries=[entry])

        with patch("database.models.audit.MobileAuditEvent") as MockModel:
            MockModel.return_value = MagicMock()
            result = await receive_audit_log(payload=payload, current_user=user, db=mock_db)

        # Should still return OK — client needs to clear its queue
        assert result.status == "ok"
        assert result.received == 1
        assert result.persisted == 0


# ---------------------------------------------------------------------------
# 4. Pydantic models
# ---------------------------------------------------------------------------

class TestAuditModels:
    def test_device_info(self):
        from routes.security_audit_routes import DeviceInfo
        info = DeviceInfo(model="iPhone 15", osVersion="17.4", appVersion="1.0.0")
        assert info.model == "iPhone 15"

    def test_audit_entry(self):
        from routes.security_audit_routes import AuditEntry, DeviceInfo
        entry = AuditEntry(
            id="test",
            timestamp=1712764800.0,
            event="auth.success",
            details={"key": "value"},
            deviceInfo=DeviceInfo(model="iPhone", osVersion="17.4", appVersion="1.0.0"),
            previousHash="0" * 64,
            hash="a" * 64,
        )
        assert entry.event == "auth.success"
        assert entry.synced is False  # Default

    def test_audit_event_out(self):
        from routes.security_audit_routes import AuditEventOut
        event = AuditEventOut(
            id=1,
            user_id=5,
            event_type="auth.success",
            organization_id=100,
        )
        assert event.id == 1
        assert event.chain_valid is None  # Default
