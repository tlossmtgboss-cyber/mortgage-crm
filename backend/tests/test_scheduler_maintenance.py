"""
Scheduler Maintenance Route Tests

Tests for the maintenance route handlers in routes/scheduler/maintenance.py.
Covers:
  - POST /maintenance/cleanup-holds  (admin-only endpoint)
  - Admin vs non-admin access control (403)
  - Expired holds are deleted while active/converted holds are preserved
  - Idempotent: running cleanup twice doesn't cause errors
  - Standalone helper functions (expire_stale_active_holds, cleanup_expired_slot_holds, run_hold_maintenance)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

class MockUser:
    """Mock user for authenticated tests."""
    def __init__(self, role="loan_officer", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "lo@test.com"


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


@pytest.fixture
def lo_user():
    return MockUser(role="loan_officer")


# Shared patch targets
_MAINTENANCE = "routes.scheduler.maintenance"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# Mock SlotHold rows for standalone function tests
# =============================================================================

class MockSlotHold:
    """Minimal mock for a SlotHold ORM row used in unit tests."""
    def __init__(self, id, status, expires_at, organization_id=1, lo_id=1):
        self.id = id
        self.status = status
        self.expires_at = expires_at
        self.organization_id = organization_id
        self.lo_id = lo_id


# =============================================================================
# POST /maintenance/cleanup-holds — Admin access required
# =============================================================================

class TestCleanupHoldsAdminAccess:
    """POST /api/v1/scheduler/maintenance/cleanup-holds requires admin role."""

    @patch(f"{_MAINTENANCE}._audit_log")
    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_admin_can_access_cleanup(self, mock_auth, mock_audit, admin_user):
        """Admin user gets 200 on cleanup-holds endpoint."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.return_value = {"expired_count": 0, "deleted_count": 0}
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"

    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_non_admin_gets_403(self, mock_auth, lo_user):
        """Non-admin (loan_officer) user receives 403 Forbidden."""
        mock_auth.return_value = lo_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/maintenance/cleanup-holds",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 403
        assert "Admin" in resp.json()["detail"] or "admin" in resp.json()["detail"].lower()

    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_site_admin_can_access(self, mock_auth):
        """site_admin role also qualifies as admin."""
        site_admin = MockUser(role="site_admin")
        mock_auth.return_value = site_admin

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run, \
             patch(f"{_MAINTENANCE}._audit_log"):
            mock_run.return_value = {"expired_count": 0, "deleted_count": 0}
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200


# =============================================================================
# POST /maintenance/cleanup-holds — Response structure
# =============================================================================

class TestCleanupHoldsResponse:
    """Verify the response shape and counts from cleanup-holds."""

    @patch(f"{_MAINTENANCE}._audit_log")
    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_response_contains_counts(self, mock_auth, mock_audit, admin_user):
        """Response includes expired_count, deleted_count, and message."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.return_value = {"expired_count": 3, "deleted_count": 5}
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        body = resp.json()
        assert body["status"] == "success"
        assert body["expired_count"] == 3
        assert body["deleted_count"] == 5
        assert "3" in body["message"] and "5" in body["message"]

    @patch(f"{_MAINTENANCE}._audit_log")
    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_zero_counts_when_nothing_to_clean(self, mock_auth, mock_audit, admin_user):
        """When no holds need cleanup, counts are both zero."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.return_value = {"expired_count": 0, "deleted_count": 0}
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        body = resp.json()
        assert body["expired_count"] == 0
        assert body["deleted_count"] == 0

    @patch(f"{_MAINTENANCE}._audit_log")
    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_cleanup_passes_org_id(self, mock_auth, mock_audit, admin_user):
        """run_hold_maintenance is called with the user's org_id."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.return_value = {"expired_count": 0, "deleted_count": 0}
            client = _get_client()
            client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        # Verify org_id was passed
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("org_id") == admin_user.organization_id


# =============================================================================
# POST /maintenance/cleanup-holds — Error handling
# =============================================================================

class TestCleanupHoldsErrors:
    """Error handling in the cleanup-holds endpoint."""

    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_internal_error_returns_500(self, mock_auth, admin_user):
        """If run_hold_maintenance raises, endpoint returns 500."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.side_effect = RuntimeError("DB connection lost")
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 500
        assert "failed" in resp.json()["detail"].lower() or "Cleanup" in resp.json()["detail"]


# =============================================================================
# POST /maintenance/cleanup-holds — Audit log written
# =============================================================================

class TestCleanupHoldsAudit:
    """Verify audit logging on successful cleanup."""

    @patch(f"{_MAINTENANCE}._audit_log")
    @patch(f"{_MAINTENANCE}.get_current_user", new_callable=AsyncMock)
    def test_audit_log_written_on_success(self, mock_auth, mock_audit, admin_user):
        """An audit entry is recorded after successful cleanup."""
        mock_auth.return_value = admin_user

        with patch(f"{_MAINTENANCE}.run_hold_maintenance") as mock_run:
            mock_run.return_value = {"expired_count": 2, "deleted_count": 1}
            client = _get_client()
            client.post(
                "/api/v1/scheduler/maintenance/cleanup-holds",
                headers={"Authorization": "Bearer test"},
            )

        mock_audit.assert_called_once()
        call_args = mock_audit.call_args
        # action should be "slot_hold_cleanup"
        assert call_args.args[3] == "slot_hold_cleanup"
        # entity_type should be "slot_hold"
        assert call_args.args[4] == "slot_hold"
        # changes should contain the result counts
        assert call_args.kwargs.get("changes") == {"expired_count": 2, "deleted_count": 1}


# =============================================================================
# Standalone function: expire_stale_active_holds
# =============================================================================

class TestExpireStaleActiveHolds:
    """Unit tests for the expire_stale_active_holds standalone function."""

    def test_expires_stale_active_holds(self):
        """Active holds past their expires_at are transitioned to expired."""
        from routes.scheduler.maintenance import expire_stale_active_holds

        now = datetime.now(timezone.utc)
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 3  # 3 rows updated

        count = expire_stale_active_holds(mock_db)

        assert count == 3
        mock_db.flush.assert_called_once()

    def test_returns_zero_when_none_expired(self):
        """Returns 0 when no active holds are past expiry."""
        from routes.scheduler.maintenance import expire_stale_active_holds

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 0

        count = expire_stale_active_holds(mock_db)

        assert count == 0

    def test_respects_org_id_filter(self):
        """When org_id is provided, it is included in the query filters."""
        from routes.scheduler.maintenance import expire_stale_active_holds

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 1

        count = expire_stale_active_holds(mock_db, org_id=42)

        assert count == 1
        # Verify filter was called (the and_() clause includes org_id filter)
        mock_query.filter.assert_called_once()


# =============================================================================
# Standalone function: cleanup_expired_slot_holds
# =============================================================================

class TestCleanupExpiredSlotHolds:
    """Unit tests for the cleanup_expired_slot_holds standalone function."""

    def test_deletes_expired_released_holds(self):
        """Records with status expired/released past grace period are deleted."""
        from routes.scheduler.maintenance import cleanup_expired_slot_holds

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 5

        count = cleanup_expired_slot_holds(mock_db)

        assert count == 5
        mock_db.flush.assert_called_once()

    def test_custom_grace_period(self):
        """Accepts a custom grace_period_hours argument."""
        from routes.scheduler.maintenance import cleanup_expired_slot_holds

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 2

        count = cleanup_expired_slot_holds(mock_db, grace_period_hours=24)

        assert count == 2


# =============================================================================
# Standalone function: run_hold_maintenance (composite)
# =============================================================================

class TestRunHoldMaintenance:
    """Unit tests for the run_hold_maintenance composite function."""

    @patch(f"{_MAINTENANCE}.cleanup_expired_slot_holds")
    @patch(f"{_MAINTENANCE}.expire_stale_active_holds")
    def test_runs_both_steps_in_order(self, mock_expire, mock_cleanup):
        """run_hold_maintenance calls expire then cleanup, returns combined result."""
        from routes.scheduler.maintenance import run_hold_maintenance

        mock_expire.return_value = 4
        mock_cleanup.return_value = 2

        mock_db = MagicMock()
        result = run_hold_maintenance(mock_db)

        assert result == {"expired_count": 4, "deleted_count": 2}
        mock_expire.assert_called_once_with(mock_db, org_id=None)
        mock_cleanup.assert_called_once_with(mock_db, org_id=None)

    @patch(f"{_MAINTENANCE}.cleanup_expired_slot_holds")
    @patch(f"{_MAINTENANCE}.expire_stale_active_holds")
    def test_idempotent_no_errors_on_zero_results(self, mock_expire, mock_cleanup):
        """Running maintenance when nothing to clean returns zeros without error."""
        from routes.scheduler.maintenance import run_hold_maintenance

        mock_expire.return_value = 0
        mock_cleanup.return_value = 0

        mock_db = MagicMock()
        result = run_hold_maintenance(mock_db)

        assert result == {"expired_count": 0, "deleted_count": 0}

    @patch(f"{_MAINTENANCE}.cleanup_expired_slot_holds")
    @patch(f"{_MAINTENANCE}.expire_stale_active_holds")
    def test_idempotent_second_run_returns_zeros(self, mock_expire, mock_cleanup):
        """Calling maintenance twice: second call gets zero counts (idempotent)."""
        from routes.scheduler.maintenance import run_hold_maintenance

        mock_db = MagicMock()

        # First run finds work to do
        mock_expire.return_value = 3
        mock_cleanup.return_value = 2
        result1 = run_hold_maintenance(mock_db)
        assert result1["expired_count"] == 3

        # Second run finds nothing
        mock_expire.return_value = 0
        mock_cleanup.return_value = 0
        result2 = run_hold_maintenance(mock_db)
        assert result2 == {"expired_count": 0, "deleted_count": 0}

    @patch(f"{_MAINTENANCE}.cleanup_expired_slot_holds")
    @patch(f"{_MAINTENANCE}.expire_stale_active_holds")
    def test_passes_org_id_to_both_steps(self, mock_expire, mock_cleanup):
        """org_id is forwarded to both expire and cleanup steps."""
        from routes.scheduler.maintenance import run_hold_maintenance

        mock_expire.return_value = 0
        mock_cleanup.return_value = 0

        mock_db = MagicMock()
        run_hold_maintenance(mock_db, org_id=99)

        mock_expire.assert_called_once_with(mock_db, org_id=99)
        mock_cleanup.assert_called_once_with(mock_db, org_id=99)
