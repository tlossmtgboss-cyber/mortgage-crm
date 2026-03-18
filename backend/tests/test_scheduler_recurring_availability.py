"""
Scheduler Recurring Availability Route Tests

Tests for the recurring availability route handlers in
routes/scheduler/recurring_availability.py.
Covers:
  - GET    /availability/schedule         Get weekly schedule (auth required)
  - PUT    /availability/schedule         Update weekly schedule (auth required)
  - GET    /availability/exceptions       List date exceptions
  - POST   /availability/exceptions       Add date exception
  - DELETE /availability/exceptions/{id}  Remove date exception
  - GET    /availability/templates        List org templates
  - POST   /availability/templates        Create template
  - POST   /availability/templates/{id}/apply  Apply template to user
  - GET    /availability/effective        Effective schedule for a date
  - GET    /availability/slots            Computed available slots
  - Input validation (bad date format, start > end date)
  - Auth required on all endpoints
  - 404 for non-existent resources
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date, time
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


# Shared patch targets
_RECURRING = "routes.scheduler.recurring_availability"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _mock_service(method_returns=None):
    """Create a mock RecurringAvailabilityService with optional method returns."""
    svc = MagicMock()
    if method_returns:
        for method, value in method_returns.items():
            getattr(svc, method).return_value = value
    return svc


# =============================================================================
# GET /availability/schedule — Get weekly schedule
# =============================================================================

class TestGetWeeklySchedule:
    """GET /api/v1/scheduler/availability/schedule."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_get_schedule_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_weekly_schedule": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
            {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/schedule",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "schedule" in data
        assert data["total_blocks"] == 2
        assert data["user_id"] == 10

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_get_schedule_empty(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_weekly_schedule": []})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/schedule",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["total_blocks"] == 0

    def test_get_schedule_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/availability/schedule")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# PUT /availability/schedule — Update weekly schedule
# =============================================================================

class TestUpdateWeeklySchedule:
    """PUT /api/v1/scheduler/availability/schedule."""

    @patch(f"{_RECURRING}._sync_recurring_to_working_hours_json")
    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_update_schedule_success(self, mock_auth, mock_svc_cls, mock_sync, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"set_weekly_schedule": [
            {"day_of_week": 0, "start_time": "08:00", "end_time": "16:00"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/availability/schedule",
            json={
                "schedule": {
                    "0": [{"start": "08:00", "end": "16:00"}],
                },
                "timezone": "America/Chicago",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Weekly schedule updated"
        assert data["total_blocks"] == 1

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_update_schedule_validation_error(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = MagicMock()
        mock_svc.set_weekly_schedule.side_effect = ValueError("Start time must be before end time")
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/availability/schedule",
            json={
                "schedule": {
                    "0": [{"start": "17:00", "end": "08:00"}],
                },
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400

    def test_update_schedule_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/availability/schedule",
            json={"schedule": {"0": [{"start": "09:00", "end": "17:00"}]}},
        )
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# Exceptions CRUD
# =============================================================================

class TestListExceptions:
    """GET /api/v1/scheduler/availability/exceptions."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_list_exceptions_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_exceptions": [
            {"id": 1, "date": "2026-03-25", "is_blocked": True, "reason": "PTO"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/exceptions",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_list_exceptions_empty(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_exceptions": []})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/exceptions",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestAddException:
    """POST /api/v1/scheduler/availability/exceptions."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_add_exception_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"add_exception": {"id": 5, "date": "2026-03-25"}})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/exceptions",
            json={
                "date": "2026-03-25",
                "is_blocked": True,
                "reason": "Day off",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Exception added"

    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_add_exception_invalid_date_format(self, mock_auth, auth_user):
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/exceptions",
            json={
                "date": "not-a-date",
                "is_blocked": True,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "Invalid date format" in resp.json()["detail"]

    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_add_exception_invalid_time_format(self, mock_auth, auth_user):
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/exceptions",
            json={
                "date": "2026-03-25",
                "start_time": "25:00",
                "end_time": "17:00",
                "is_blocked": False,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "Invalid start_time format" in resp.json()["detail"]


class TestRemoveException:
    """DELETE /api/v1/scheduler/availability/exceptions/{id}."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_remove_exception_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"remove_exception": True})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/availability/exceptions/5",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == 5

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_remove_exception_not_found(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"remove_exception": False})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/availability/exceptions/999",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404


# =============================================================================
# Templates
# =============================================================================

class TestListTemplates:
    """GET /api/v1/scheduler/availability/templates."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_list_templates_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_templates": [
            {"id": 1, "name": "Standard 9-5"},
            {"id": 2, "name": "Early Bird"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/templates",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 2


class TestCreateTemplate:
    """POST /api/v1/scheduler/availability/templates."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_create_template_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"create_template": {"id": 3, "name": "Custom Schedule"}})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/templates",
            json={
                "name": "Custom Schedule",
                "schedule": {
                    "0": [{"start": "08:00", "end": "16:00"}],
                    "1": [{"start": "08:00", "end": "16:00"}],
                },
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Template created"

    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_create_template_missing_name(self, mock_auth, auth_user):
        """Missing required field 'name' should return 422."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/templates",
            json={
                "schedule": {"0": [{"start": "08:00", "end": "16:00"}]},
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 422


class TestApplyTemplate:
    """POST /api/v1/scheduler/availability/templates/{id}/apply."""

    @patch(f"{_RECURRING}._sync_recurring_to_working_hours_json")
    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_apply_template_success(self, mock_auth, mock_svc_cls, mock_sync, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"apply_template": [
            {"day_of_week": 0, "start_time": "08:00", "end_time": "16:00"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/templates/1/apply",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Template applied"

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_apply_template_not_found(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = MagicMock()
        mock_svc.apply_template.side_effect = ValueError("Template not found")
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/availability/templates/999/apply",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404


# =============================================================================
# Effective Schedule & Slots
# =============================================================================

class TestGetEffectiveSchedule:
    """GET /api/v1/scheduler/availability/effective."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_effective_schedule_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_effective_schedule": [
            {"start_time": "09:00", "end_time": "12:00"},
            {"start_time": "13:00", "end_time": "17:00"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/effective?target_date=2026-03-20",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_blocks"] == 2
        assert data["date"] == "2026-03-20"

    def test_effective_schedule_missing_date(self):
        """Missing required 'target_date' should return 422."""
        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/effective",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422


class TestGetComputedSlots:
    """GET /api/v1/scheduler/availability/slots."""

    @patch(f"{_RECURRING}.RecurringAvailabilityService")
    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_get_slots_success(self, mock_auth, mock_svc_cls, auth_user):
        mock_auth.return_value = auth_user
        mock_svc = _mock_service({"get_available_slots": [
            {"start": "2026-03-20T09:00:00", "end": "2026-03-20T09:30:00"},
            {"start": "2026-03-20T09:30:00", "end": "2026-03-20T10:00:00"},
        ]})
        mock_svc_cls.return_value = mock_svc

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/slots?start_date=2026-03-20&end_date=2026-03-21",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_slots"] == 2

    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_get_slots_start_after_end(self, mock_auth, auth_user):
        """start_date after end_date should return 400."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/slots?start_date=2026-03-25&end_date=2026-03-20",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "before or equal" in resp.json()["detail"]

    @patch(f"{_RECURRING}.get_current_user", new_callable=AsyncMock)
    def test_get_slots_date_range_too_large(self, mock_auth, auth_user):
        """Date range exceeding 90 days should return 400."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/availability/slots?start_date=2026-01-01&end_date=2026-07-01",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "90 days" in resp.json()["detail"]
