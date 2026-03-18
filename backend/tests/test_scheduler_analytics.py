"""
Scheduler Analytics Route Tests

Tests for the analytics route handlers in routes/scheduler/analytics.py.
Covers:
  - GET /analytics/overview       Key metrics (auth required, feature tier gated)
  - GET /analytics/trends         Time-series trend data (auth required)
  - GET /analytics/by-type        Breakdown by appointment type (auth, paginated)
  - GET /analytics/by-lo          Breakdown by loan officer (admin only, paginated)
  - Authentication required on all endpoints
  - Non-admin restriction on by-lo and user_id filters
  - Empty data handling
  - Pagination metadata
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
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
def auth_user():
    return MockUser()


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


@pytest.fixture
def lo_user():
    return MockUser(role="loan_officer")


# Shared patch targets
_ANALYTICS = "routes.scheduler.analytics"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# GET /analytics/overview — Key metrics
# =============================================================================

class TestAnalyticsOverview:
    """GET /api/v1/scheduler/analytics/overview."""

    @patch(f"{_ANALYTICS}.get_overview_metrics")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_overview_success(self, mock_auth, mock_models, mock_metrics, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            mock_metrics.return_value = {
                "period": "30d",
                "total_appointments": 50,
                "completed": 40,
                "cancelled": 5,
                "no_shows": 3,
                "rescheduled": 2,
                "completion_rate": 80.0,
                "avg_duration_minutes": 28.5,
                "utilization_rate": 65.0,
                "busiest_day_of_week": "Tuesday",
                "busiest_hour": 10,
                "busiest_hour_label": "10:00",
            }

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/overview?period=30d",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_appointments"] == 50
        assert data["completed"] == 40
        assert data["completion_rate"] == 80.0
        assert data["period"] == "30d"
        assert "start_date" in data
        assert "end_date" in data

    @patch(f"{_ANALYTICS}.get_overview_metrics")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_overview_empty_data(self, mock_auth, mock_models, mock_metrics, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            mock_metrics.return_value = {
                "period": "7d",
                "total_appointments": 0,
                "completed": 0,
                "cancelled": 0,
                "no_shows": 0,
                "rescheduled": 0,
                "completion_rate": 0.0,
                "avg_duration_minutes": 0.0,
                "utilization_rate": 0.0,
                "busiest_day_of_week": None,
                "busiest_hour": None,
                "busiest_hour_label": None,
            }

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/overview?period=7d",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["total_appointments"] == 0

    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_overview_models_unavailable(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = None

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/analytics/overview",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 503

    def test_overview_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/analytics/overview")
        assert resp.status_code in (401, 403, 500)

    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_overview_non_admin_cannot_view_other_users(self, mock_auth, mock_models, lo_user):
        """Non-admin trying to view another user's analytics should get 403."""
        mock_auth.return_value = lo_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/overview?user_id=999",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 403


# =============================================================================
# GET /analytics/trends — Time-series data
# =============================================================================

class TestAnalyticsTrends:
    """GET /api/v1/scheduler/analytics/trends."""

    @patch(f"{_ANALYTICS}.get_cancellation_rate")
    @patch(f"{_ANALYTICS}.get_peak_hours")
    @patch(f"{_ANALYTICS}.get_appointment_trends")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_trends_success(self, mock_auth, mock_models, mock_trends, mock_peak, mock_cancel, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            mock_trends.return_value = {
                "period": "30d",
                "granularity": "daily",
                "labels": ["2026-03-01", "2026-03-02"],
                "datasets": {
                    "total": [5, 3],
                    "completed": [4, 2],
                    "cancelled": [1, 0],
                    "no_shows": [0, 1],
                },
            }
            mock_peak.return_value = {
                "period": "30d",
                "grid": [],
                "max_count": 0,
            }
            mock_cancel.return_value = {
                "period": "30d",
                "total_appointments": 8,
                "cancelled": 1,
                "rate": 12.5,
                "reasons": [],
            }

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/trends?period=30d&granularity=daily",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "30d"
        assert data["granularity"] == "daily"
        assert len(data["labels"]) == 2
        assert "peak_hours" in data
        assert "cancellation" in data

    def test_trends_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/analytics/trends")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /analytics/by-type — Breakdown by appointment type (paginated)
# =============================================================================

class TestAnalyticsByType:
    """GET /api/v1/scheduler/analytics/by-type."""

    @patch(f"{_ANALYTICS}.get_by_type_breakdown")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_by_type_success(self, mock_auth, mock_models, mock_breakdown, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            mock_breakdown.return_value = {
                "period": "30d",
                "types": [
                    {
                        "type_id": 1,
                        "type_name": "Consultation",
                        "color": "#3b82f6",
                        "total": 20,
                        "completed": 18,
                        "cancelled": 1,
                        "no_shows": 1,
                        "avg_duration": 30.0,
                        "percentage": 66.7,
                    },
                    {
                        "type_id": 2,
                        "type_name": "Follow-up",
                        "color": "#10b981",
                        "total": 10,
                        "completed": 9,
                        "cancelled": 0,
                        "no_shows": 1,
                        "avg_duration": 15.0,
                        "percentage": 33.3,
                    },
                ],
            }

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/by-type?period=30d",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["types"]) == 2
        assert data["pagination"]["total"] == 2
        assert data["pagination"]["page"] == 1

    @patch(f"{_ANALYTICS}.get_by_type_breakdown")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_by_type_empty(self, mock_auth, mock_models, mock_breakdown, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            mock_breakdown.return_value = {"period": "30d", "types": []}

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/by-type",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 0


# =============================================================================
# GET /analytics/by-lo — Breakdown by loan officer (admin only, paginated)
# =============================================================================

class TestAnalyticsByLO:
    """GET /api/v1/scheduler/analytics/by-lo."""

    @patch(f"{_ANALYTICS}.get_by_lo_breakdown")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_by_lo_admin_success(self, mock_auth, mock_models, mock_breakdown, admin_user):
        mock_auth.return_value = admin_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=True):
            mock_breakdown.return_value = {
                "period": "30d",
                "loan_officers": [
                    {
                        "user_id": 10,
                        "name": "Alice Smith",
                        "total": 30,
                        "completed": 25,
                        "cancelled": 3,
                        "no_shows": 2,
                        "avg_duration": 28.0,
                        "completion_rate": 83.3,
                        "utilization_rate": 70.0,
                        "percentage": 60.0,
                    },
                    {
                        "user_id": 11,
                        "name": "Bob Jones",
                        "total": 20,
                        "completed": 18,
                        "cancelled": 1,
                        "no_shows": 1,
                        "avg_duration": 25.0,
                        "completion_rate": 90.0,
                        "utilization_rate": 55.0,
                        "percentage": 40.0,
                    },
                ],
            }

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/by-lo?period=30d",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["loan_officers"]) == 2
        assert data["pagination"]["total"] == 2

    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_by_lo_non_admin_forbidden(self, mock_auth, mock_models, lo_user):
        """Non-admin users should be forbidden from accessing by-lo endpoint."""
        mock_auth.return_value = lo_user
        mock_models.return_value = {"Appointment": MagicMock()}

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=False):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/by-lo",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 403

    @patch(f"{_ANALYTICS}.get_by_lo_breakdown")
    @patch(f"{_ANALYTICS}.get_models")
    @patch(f"{_ANALYTICS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_ANALYTICS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_by_lo_pagination(self, mock_auth, mock_models, mock_breakdown, admin_user):
        """Pagination should correctly slice results."""
        mock_auth.return_value = admin_user
        mock_models.return_value = {"Appointment": MagicMock()}

        # Generate 5 LOs
        all_los = [
            {
                "user_id": i,
                "name": f"LO {i}",
                "total": 10,
                "completed": 8,
                "cancelled": 1,
                "no_shows": 1,
                "avg_duration": 25.0,
                "completion_rate": 80.0,
                "utilization_rate": 50.0,
                "percentage": 20.0,
            }
            for i in range(5)
        ]

        with patch(f"{_ANALYTICS}._is_scheduler_admin", return_value=True):
            mock_breakdown.return_value = {"period": "30d", "loan_officers": all_los}

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/by-lo?page=1&page_size=2",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["loan_officers"]) == 2
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["total_pages"] == 3
        assert data["pagination"]["has_next"] is True

    def test_by_lo_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/analytics/by-lo")
        assert resp.status_code in (401, 403, 500)
