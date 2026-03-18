"""
Tests for scheduler metrics routes.

Covers:
  - GET  /metrics               JSON metrics summary (admin only)
  - GET  /metrics/prometheus    Prometheus text exposition format (admin only)
  - POST /metrics/reset         Reset all counters (platform admin only)

All three endpoints require admin authentication. The /metrics/reset endpoint
is further restricted to platform_admin role only.
"""

import pytest
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


class MockPlatformAdmin(MockUser):
    """Mock platform admin user."""
    def __init__(self, **kwargs):
        defaults = {"id": 3, "role": "platform_admin", "email": "platform@test.com"}
        defaults.update(kwargs)
        super().__init__(**defaults)


SAMPLE_METRICS_SUMMARY = {
    "collected_at": "2026-03-17T10:00:00+00:00",
    "uptime_seconds": 3600.5,
    "counters": {
        "appointments.created": 42,
        "appointments.cancelled": 3,
        "appointments.completed": 35,
        "appointments.no_show": 2,
        "booking.views": 150,
        "booking.conversions": 28,
        "errors": 1,
    },
    "timings": {
        "api.latency.book": {
            "count": 28,
            "min_ms": 45.2,
            "max_ms": 312.1,
            "avg_ms": 98.4,
            "p50_ms": 85.0,
            "p95_ms": 250.0,
            "p99_ms": None,
        }
    },
    "derived": {
        "booking_conversion_rate_pct": 18.67,
        "cancellation_rate_pct": 7.14,
        "total_appointments_created": 42,
        "total_appointments_cancelled": 3,
        "total_no_shows": 2,
        "total_errors": 1,
    },
}

SAMPLE_PROMETHEUS_TEXT = (
    '# HELP scheduler_appointments_created Total appointments created\n'
    '# TYPE scheduler_appointments_created counter\n'
    'scheduler_appointments_created 42\n'
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetMetrics:
    """Tests for GET /metrics."""

    @pytest.mark.asyncio
    async def test_metrics_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.metrics import get_scheduler_metrics

        with patch(
            "routes.scheduler.metrics.get_current_user",
            new_callable=AsyncMock,
            side_effect=Exception("Not authenticated"),
        ):
            with pytest.raises(Exception, match="Not authenticated"):
                await get_scheduler_metrics(MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_metrics_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.metrics import get_scheduler_metrics

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=non_admin), \
             patch("routes.scheduler.metrics._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_scheduler_metrics(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_metrics_returns_summary_for_admin(self):
        """Admin users should receive the full metrics summary."""
        from routes.scheduler.metrics import get_scheduler_metrics

        admin = MockAdminUser()
        mock_metrics = MagicMock()
        mock_metrics.get_summary.return_value = SAMPLE_METRICS_SUMMARY

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.metrics._is_scheduler_admin", return_value=True), \
             patch("routes.scheduler.metrics.scheduler_metrics", mock_metrics, create=True), \
             patch.dict("sys.modules", {"services.scheduler_metrics_service": MagicMock(scheduler_metrics=mock_metrics)}):

            result = await get_scheduler_metrics(MagicMock(), MagicMock())

        assert result == SAMPLE_METRICS_SUMMARY
        assert "counters" in result
        assert "derived" in result
        assert result["derived"]["total_appointments_created"] == 42

    @pytest.mark.asyncio
    async def test_metrics_response_has_expected_structure(self):
        """Verify the metrics summary contains all expected top-level keys."""
        from routes.scheduler.metrics import get_scheduler_metrics

        admin = MockAdminUser()
        mock_metrics = MagicMock()
        mock_metrics.get_summary.return_value = SAMPLE_METRICS_SUMMARY

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.metrics._is_scheduler_admin", return_value=True), \
             patch.dict("sys.modules", {"services.scheduler_metrics_service": MagicMock(scheduler_metrics=mock_metrics)}):

            result = await get_scheduler_metrics(MagicMock(), MagicMock())

        expected_keys = {"collected_at", "uptime_seconds", "counters", "timings", "derived"}
        assert expected_keys.issubset(set(result.keys()))


class TestGetMetricsPrometheus:
    """Tests for GET /metrics/prometheus."""

    @pytest.mark.asyncio
    async def test_prometheus_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.metrics import get_scheduler_metrics_prometheus

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=non_admin), \
             patch("routes.scheduler.metrics._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_scheduler_metrics_prometheus(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_prometheus_returns_text_for_admin(self):
        """Admin users should receive Prometheus-format text."""
        from routes.scheduler.metrics import get_scheduler_metrics_prometheus

        admin = MockAdminUser()
        mock_metrics = MagicMock()
        mock_metrics.get_prometheus_text.return_value = SAMPLE_PROMETHEUS_TEXT

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.metrics._is_scheduler_admin", return_value=True), \
             patch.dict("sys.modules", {"services.scheduler_metrics_service": MagicMock(scheduler_metrics=mock_metrics)}):

            result = await get_scheduler_metrics_prometheus(MagicMock(), MagicMock())

        assert result.body == SAMPLE_PROMETHEUS_TEXT.encode()
        assert "text/plain" in result.media_type


class TestResetMetrics:
    """Tests for POST /metrics/reset."""

    @pytest.mark.asyncio
    async def test_reset_requires_platform_admin(self):
        """Regular admin should get 403 on /metrics/reset."""
        from routes.scheduler.metrics import reset_scheduler_metrics

        admin = MockAdminUser()  # role="admin", not "platform_admin"

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await reset_scheduler_metrics(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_reset_succeeds_for_platform_admin(self):
        """Platform admin should be able to reset metrics."""
        from routes.scheduler.metrics import reset_scheduler_metrics

        platform_admin = MockPlatformAdmin()
        mock_metrics = MagicMock()

        with patch("routes.scheduler.metrics.get_current_user", new_callable=AsyncMock, return_value=platform_admin), \
             patch.dict("sys.modules", {"services.scheduler_metrics_service": MagicMock(scheduler_metrics=mock_metrics)}):

            result = await reset_scheduler_metrics(MagicMock(), MagicMock())

        mock_metrics.reset.assert_called_once()
        assert result["message"] == "Scheduler metrics reset"
        assert result["reset_by"] == platform_admin.id
