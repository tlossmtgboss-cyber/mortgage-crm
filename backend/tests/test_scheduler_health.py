"""
Tests for scheduler health check routes.

Covers:
  - GET /health    Smart Calendar subsystem health check

Each individual check (database, calendar_sync, email_service, scheduler_config,
tenant_isolation, upcoming_appointments) is exercised via mocking so the tests
remain purely unit-level with no database or external-service requirements.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    """Mock authenticated user."""
    def __init__(self, id=1, organization_id=1, role="loan_officer", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockAdminUser(MockUser):
    """Mock admin user."""
    def __init__(self, **kwargs):
        defaults = {"id": 2, "role": "admin", "email": "admin@test.com"}
        defaults.update(kwargs)
        super().__init__(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /health."""

    @pytest.mark.asyncio
    async def test_health_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.health import scheduler_health

        with patch(
            "routes.scheduler.health.get_current_user",
            new_callable=AsyncMock,
            side_effect=Exception("Not authenticated"),
        ):
            with pytest.raises(Exception, match="Not authenticated"):
                await scheduler_health(MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_health_returns_healthy_when_all_checks_pass(self):
        """All checks OK should produce 'healthy' status."""
        from routes.scheduler.health import scheduler_health

        user = MockUser()
        db = MagicMock()

        with patch("routes.scheduler.health.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.health._check_database", return_value={"status": "ok", "latency_ms": 1.2}), \
             patch("routes.scheduler.health._check_calendar_sync", return_value={"status": "ok", "last_sync": None, "synced_calendars": 0}), \
             patch("routes.scheduler.health._check_email_service", return_value={"status": "ok", "configured": True}), \
             patch("routes.scheduler.health._check_pending_reminders", return_value={"status": "ok", "pending_reminders": 0, "active_templates": 0}), \
             patch("routes.scheduler.health._check_scheduler_config", return_value={"status": "ok", "active_appointment_types": 2, "configs_found": 1}), \
             patch("routes.scheduler.health._check_tenant_isolation", return_value={"status": "ok", "organization_id": "1"}), \
             patch("routes.scheduler.health._check_upcoming_appointments", return_value={"count": 5, "next_24h": 2}), \
             patch("routes.scheduler.health._count_registered_modules", return_value=26):

            result = await scheduler_health(MagicMock(), db)

        assert result.status == "healthy"
        assert result.version == "2.0"
        assert result.registered_modules == 26
        assert "database" in result.checks
        assert "tenant_isolation" in result.checks

    @pytest.mark.asyncio
    async def test_health_returns_degraded_on_warning(self):
        """A warning-level check should produce 'degraded' status."""
        from routes.scheduler.health import scheduler_health

        user = MockUser()
        db = MagicMock()

        with patch("routes.scheduler.health.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.health._check_database", return_value={"status": "ok", "latency_ms": 1.0}), \
             patch("routes.scheduler.health._check_calendar_sync", return_value={"status": "warning", "last_sync": None, "synced_calendars": 1}), \
             patch("routes.scheduler.health._check_email_service", return_value={"status": "ok", "configured": True}), \
             patch("routes.scheduler.health._check_pending_reminders", return_value={"status": "ok", "pending_reminders": 0, "active_templates": 0}), \
             patch("routes.scheduler.health._check_scheduler_config", return_value={"status": "ok", "active_appointment_types": 1, "configs_found": 1}), \
             patch("routes.scheduler.health._check_tenant_isolation", return_value={"status": "ok", "organization_id": "1"}), \
             patch("routes.scheduler.health._check_upcoming_appointments", return_value={"count": 0, "next_24h": 0}), \
             patch("routes.scheduler.health._count_registered_modules", return_value=26):

            result = await scheduler_health(MagicMock(), db)

        assert result.status == "degraded"

    @pytest.mark.asyncio
    async def test_health_returns_unhealthy_on_database_failure(self):
        """Database check failure should produce 'unhealthy' status."""
        from routes.scheduler.health import scheduler_health

        user = MockUser()
        db = MagicMock()

        with patch("routes.scheduler.health.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.health._check_database", side_effect=Exception("Connection refused")), \
             patch("routes.scheduler.health._check_calendar_sync", return_value={"status": "ok", "last_sync": None, "synced_calendars": 0}), \
             patch("routes.scheduler.health._check_email_service", return_value={"status": "ok", "configured": True}), \
             patch("routes.scheduler.health._check_pending_reminders", return_value={"status": "ok", "pending_reminders": 0, "active_templates": 0}), \
             patch("routes.scheduler.health._check_scheduler_config", return_value={"status": "ok", "active_appointment_types": 1, "configs_found": 1}), \
             patch("routes.scheduler.health._check_tenant_isolation", return_value={"status": "ok", "organization_id": "1"}), \
             patch("routes.scheduler.health._check_upcoming_appointments", return_value={"count": 0, "next_24h": 0}), \
             patch("routes.scheduler.health._count_registered_modules", return_value=26):

            result = await scheduler_health(MagicMock(), db)

        assert result.status == "unhealthy"
        assert result.checks["database"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_health_returns_unhealthy_on_tenant_isolation_failure(self):
        """Tenant isolation error should produce 'unhealthy' status."""
        from routes.scheduler.health import scheduler_health

        user = MockUser(organization_id=None)
        db = MagicMock()

        with patch("routes.scheduler.health.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.health._get_org_id", return_value=None), \
             patch("routes.scheduler.health._check_database", return_value={"status": "ok", "latency_ms": 0.5}), \
             patch("routes.scheduler.health._check_calendar_sync", return_value={"status": "ok", "last_sync": None, "synced_calendars": 0}), \
             patch("routes.scheduler.health._check_email_service", return_value={"status": "ok", "configured": True}), \
             patch("routes.scheduler.health._check_pending_reminders", return_value={"status": "ok", "pending_reminders": 0, "active_templates": 0}), \
             patch("routes.scheduler.health._check_scheduler_config", return_value={"status": "ok", "active_appointment_types": 0, "configs_found": 0}), \
             patch("routes.scheduler.health._check_tenant_isolation", return_value={"status": "error", "organization_id": None}), \
             patch("routes.scheduler.health._check_upcoming_appointments", return_value={"count": 0, "next_24h": 0}), \
             patch("routes.scheduler.health._count_registered_modules", return_value=26):

            result = await scheduler_health(MagicMock(), db)

        assert result.status == "unhealthy"
        assert result.checks["tenant_isolation"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_health_response_includes_all_expected_fields(self):
        """Response should include status, checks, version, registered_modules, uptime_seconds."""
        from routes.scheduler.health import scheduler_health

        user = MockUser()
        db = MagicMock()

        with patch("routes.scheduler.health.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.health._check_database", return_value={"status": "ok", "latency_ms": 0.8}), \
             patch("routes.scheduler.health._check_calendar_sync", return_value={"status": "ok", "last_sync": None, "synced_calendars": 0}), \
             patch("routes.scheduler.health._check_email_service", return_value={"status": "ok", "configured": True}), \
             patch("routes.scheduler.health._check_pending_reminders", return_value={"status": "ok", "pending_reminders": 0, "active_templates": 0}), \
             patch("routes.scheduler.health._check_scheduler_config", return_value={"status": "ok", "active_appointment_types": 1, "configs_found": 1}), \
             patch("routes.scheduler.health._check_tenant_isolation", return_value={"status": "ok", "organization_id": "1"}), \
             patch("routes.scheduler.health._check_upcoming_appointments", return_value={"count": 3, "next_24h": 1}), \
             patch("routes.scheduler.health._count_registered_modules", return_value=26):

            result = await scheduler_health(MagicMock(), db)

        # Verify top-level structure
        assert hasattr(result, "status")
        assert hasattr(result, "checks")
        assert hasattr(result, "version")
        assert hasattr(result, "registered_modules")
        assert hasattr(result, "uptime_seconds")
        assert result.uptime_seconds >= 0

        # Verify all six check keys
        expected_checks = {
            "database", "calendar_sync", "email_service",
            "scheduler_config", "tenant_isolation", "upcoming_appointments",
        }
        assert expected_checks.issubset(set(result.checks.keys()))

    @pytest.mark.asyncio
    async def test_health_email_service_warning_without_sendgrid(self):
        """Email service should report warning when SENDGRID_API_KEY is absent."""
        from routes.scheduler.health import _check_email_service

        with patch.dict("os.environ", {}, clear=True):
            result = _check_email_service()

        assert result["status"] == "warning"
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_health_email_service_ok_with_sendgrid(self):
        """Email service should report ok when SENDGRID_API_KEY is set."""
        from routes.scheduler.health import _check_email_service

        with patch.dict("os.environ", {"SENDGRID_API_KEY": "SG.test_key_123"}):
            result = _check_email_service()

        assert result["status"] == "ok"
        assert result["configured"] is True


class TestHealthCheckHelpers:
    """Tests for individual health check helper functions."""

    def test_check_database_returns_ok_and_latency(self):
        """Database check should return ok with latency_ms."""
        from routes.scheduler.health import _check_database

        db = MagicMock()
        db.execute = MagicMock()

        result = _check_database(db)

        assert result["status"] == "ok"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], float)

    def test_check_tenant_isolation_ok_with_org_id(self):
        """Tenant isolation check should return ok when org_id is present."""
        from routes.scheduler.health import _check_tenant_isolation

        result = _check_tenant_isolation(org_id=1)

        assert result["status"] == "ok"
        assert result["organization_id"] == "1"

    def test_check_tenant_isolation_error_without_org_id(self):
        """Tenant isolation check should return error when org_id is None."""
        from routes.scheduler.health import _check_tenant_isolation

        result = _check_tenant_isolation(org_id=None)

        assert result["status"] == "error"
        assert result["organization_id"] is None
