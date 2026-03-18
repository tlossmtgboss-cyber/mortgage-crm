"""
Tests for scheduler SLA routes.

Covers:
  - GET /sla/dashboard       SLA compliance dashboard (all metrics)
  - GET /sla/breaches        Recent SLA breaches with details
  - GET /sla/lo/{lo_id}      Per-LO SLA metrics
  - PUT /sla/targets         Update SLA targets (admin only)

All endpoints require authentication and are scoped to the user's organization
for tenant isolation.
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


SAMPLE_SLA_DASHBOARD = {
    "organization_id": 1,
    "period_days": 30,
    "overall_compliance_score": 85.0,
    "compliant_count": 4,
    "total_metrics": 5,
    "metrics": [
        {
            "metric": "time_to_first_appointment",
            "display_name": "Time to First Appointment",
            "target": "48 hours",
            "current_value": "36.2 hours",
            "compliant": True,
            "details": {},
        },
        {
            "metric": "appointment_completion_rate",
            "display_name": "Appointment Completion Rate",
            "target": "80%",
            "current_value": "87.5%",
            "compliant": True,
            "details": {},
        },
    ],
    "recent_breach_count": 2,
    "targets": {
        "time_to_first_appointment_hours": 48,
        "appointment_confirmation_minutes": 30,
        "reminder_lead_time_hours": 24,
        "reschedule_response_hours": 4,
        "post_appointment_followup_hours": 24,
    },
}

SAMPLE_SLA_BREACHES = [
    {
        "breach_type": "time_to_first_appointment",
        "severity": "critical",
        "entity_type": "lead",
        "entity_id": 100,
        "entity_name": "Jane Doe",
        "lo_id": 5,
        "target_hours": 48.0,
        "actual_hours": 72.5,
        "message": "Lead #100 waited 72.5 hours for first appointment (target: 48h)",
        "detected_at": "2026-03-16T14:00:00+00:00",
    },
    {
        "breach_type": "reschedule_response",
        "severity": "warning",
        "entity_type": "appointment",
        "entity_id": 250,
        "entity_name": "John Smith",
        "lo_id": 5,
        "target_hours": 4.0,
        "actual_hours": 6.2,
        "message": "Reschedule request for appointment #250 took 6.2 hours (target: 4h)",
        "detected_at": "2026-03-15T09:30:00+00:00",
    },
]


SAMPLE_LO_METRICS = {
    "lo_id": 5,
    "lo_name": "Sarah Johnson",
    "period_days": 30,
    "time_to_first_appointment": {
        "avg_hours": 36.2,
        "median_hours": 32.0,
        "target_hours": 48,
        "total_leads_with_appointments": 15,
        "compliant": True,
    },
    "completion_rate": {
        "rate": 87.5,
        "total": 24,
        "completed": 21,
    },
    "no_show_rate": {
        "rate": 8.3,
        "total": 24,
        "no_shows": 2,
        "trend": "improving",
    },
    "reschedule_response": {
        "avg_hours": 3.1,
        "target_hours": 4,
        "compliant": True,
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSLADashboard:
    """Tests for GET /sla/dashboard."""

    @pytest.mark.asyncio
    async def test_dashboard_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.sla import sla_dashboard

        with patch(
            "routes.scheduler.sla.get_current_user",
            new_callable=AsyncMock,
            side_effect=Exception("Not authenticated"),
        ):
            with pytest.raises(Exception, match="Not authenticated"):
                await sla_dashboard(MagicMock(), db=MagicMock())

    @pytest.mark.asyncio
    async def test_dashboard_returns_compliance_data(self):
        """Authenticated user should receive SLA dashboard data."""
        from routes.scheduler.sla import sla_dashboard

        user = MockUser()

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla.check_sla_compliance", return_value=SAMPLE_SLA_DASHBOARD):

            result = await sla_dashboard(MagicMock(), period="30d", db=MagicMock())

        assert result.organization_id == 1
        assert result.period_days == 30
        assert result.overall_compliance_score == 85.0
        assert result.compliant_count == 4
        assert result.total_metrics == 5
        assert len(result.metrics) == 2

    @pytest.mark.asyncio
    async def test_dashboard_503_when_models_unavailable(self):
        """Should return 503 when scheduler models are not loaded."""
        from routes.scheduler.sla import sla_dashboard

        user = MockUser()

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value=None):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await sla_dashboard(MagicMock(), period="30d", db=MagicMock())
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_dashboard_tenant_isolation(self):
        """Dashboard should use the authenticated user's org_id."""
        from routes.scheduler.sla import sla_dashboard

        user = MockUser(organization_id=42)

        dashboard_data = dict(SAMPLE_SLA_DASHBOARD)
        dashboard_data["organization_id"] = 42

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla.check_sla_compliance", return_value=dashboard_data) as mock_check:

            result = await sla_dashboard(MagicMock(), period="30d", db=MagicMock())

        # Verify org_id was passed to the service
        call_args = mock_check.call_args
        assert call_args[0][2] == 42  # org_id positional arg
        assert result.organization_id == 42


class TestSLABreaches:
    """Tests for GET /sla/breaches."""

    @pytest.mark.asyncio
    async def test_breaches_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.sla import sla_breaches

        with patch(
            "routes.scheduler.sla.get_current_user",
            new_callable=AsyncMock,
            side_effect=Exception("Not authenticated"),
        ):
            with pytest.raises(Exception, match="Not authenticated"):
                await sla_breaches(MagicMock(), db=MagicMock())

    @pytest.mark.asyncio
    async def test_breaches_returns_empty_state(self):
        """No breaches should return empty list with zero counts."""
        from routes.scheduler.sla import sla_breaches

        user = MockUser()

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla.get_sla_breaches", return_value=[]):

            result = await sla_breaches(MagicMock(), days=7, severity=None, breach_type=None, db=MagicMock())

        assert result.total_breaches == 0
        assert result.critical_count == 0
        assert result.warning_count == 0
        assert result.breaches == []

    @pytest.mark.asyncio
    async def test_breaches_returns_breach_details(self):
        """Breaches should include severity counts and detail items."""
        from routes.scheduler.sla import sla_breaches

        user = MockUser()

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla.get_sla_breaches", return_value=SAMPLE_SLA_BREACHES):

            result = await sla_breaches(MagicMock(), days=7, severity=None, breach_type=None, db=MagicMock())

        assert result.total_breaches == 2
        assert result.critical_count == 1
        assert result.warning_count == 1
        assert result.breaches[0].breach_type == "time_to_first_appointment"
        assert result.breaches[0].actual_hours == 72.5

    @pytest.mark.asyncio
    async def test_breaches_filters_by_severity(self):
        """Severity filter should restrict results."""
        from routes.scheduler.sla import sla_breaches

        user = MockUser()

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla.get_sla_breaches", return_value=SAMPLE_SLA_BREACHES):

            result = await sla_breaches(MagicMock(), days=7, severity="critical", breach_type=None, db=MagicMock())

        assert result.total_breaches == 1
        assert result.critical_count == 1
        assert result.warning_count == 0


class TestLOSLAMetrics:
    """Tests for GET /sla/lo/{lo_id}."""

    @pytest.mark.asyncio
    async def test_lo_metrics_own_data_allowed(self):
        """LO should be able to view their own SLA metrics."""
        from routes.scheduler.sla import sla_lo_metrics

        user = MockUser(id=5)

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla._is_scheduler_admin", return_value=False), \
             patch("routes.scheduler.sla.get_lo_sla_metrics", return_value=SAMPLE_LO_METRICS):

            result = await sla_lo_metrics(MagicMock(), lo_id=5, period="30d", db=MagicMock())

        assert result.lo_id == 5
        assert result.lo_name == "Sarah Johnson"
        assert result.time_to_first_appointment.compliant is True
        assert result.completion_rate.rate == 87.5

    @pytest.mark.asyncio
    async def test_lo_metrics_403_for_other_lo(self):
        """Non-admin should get 403 when viewing another LO's metrics."""
        from routes.scheduler.sla import sla_lo_metrics

        user = MockUser(id=5)

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"Appointment": MagicMock()}), \
             patch("routes.scheduler.sla._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await sla_lo_metrics(MagicMock(), lo_id=99, period="30d", db=MagicMock())
            assert exc_info.value.status_code == 403


class TestUpdateSLATargets:
    """Tests for PUT /sla/targets."""

    @pytest.mark.asyncio
    async def test_update_targets_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.sla import update_sla_targets, SLATargetsUpdate

        user = MockUser(role="loan_officer")
        body = SLATargetsUpdate(time_to_first_appointment_hours=24)

        with patch("routes.scheduler.sla.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.sla.get_models", return_value={"SchedulerConfig": MagicMock()}), \
             patch("routes.scheduler.sla._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await update_sla_targets(MagicMock(), body=body, db=MagicMock())
            assert exc_info.value.status_code == 403
