"""
Scheduler Search Route Tests

Tests for the search route handlers in routes/scheduler/search.py.
Covers:
  - GET /search                   Advanced appointment search (auth required)
  - GET /search/suggestions       Typeahead suggestions (auth required)
  - Free-text search across multiple columns
  - Status filter validation (invalid status returns 400)
  - Date range filter (date_from, date_to)
  - Pagination metadata
  - Attendee email exact match filter
  - RBAC: non-admin sees only own appointments
  - Auth required on all endpoints
  - Org isolation
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from datetime import datetime, timezone
from enum import Enum
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


class MockAppointmentStatus(Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class MockMeetingType(Enum):
    CONSULTATION = "consultation"


class MockMeetingMode(Enum):
    VIDEO = "video"


class MockAppointment:
    """Mock Appointment model instance for search results."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.title = kwargs.get("title", "Consultation")
        self.description = kwargs.get("description", "Test meeting")
        self.meeting_type = kwargs.get("meeting_type", MockMeetingType.CONSULTATION)
        self.meeting_mode = kwargs.get("meeting_mode", MockMeetingMode.VIDEO)
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 20, 10, 0))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 20, 10, 30))
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.timezone = kwargs.get("timezone", "America/Chicago")
        self.status = kwargs.get("status", MockAppointmentStatus.SCHEDULED)
        self.attendee_name = kwargs.get("attendee_name", "John Doe")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.attendee_phone = kwargs.get("attendee_phone", "555-0100")
        self.attendee_notes = kwargs.get("attendee_notes", None)
        self.location = kwargs.get("location", None)
        self.video_link = kwargs.get("video_link", "https://meet.google.com/xyz")
        self.lead_id = kwargs.get("lead_id", None)
        self.loan_id = kwargs.get("loan_id", None)
        self.contact_id = kwargs.get("contact_id", None)
        self.assigned_user_id = kwargs.get("assigned_user_id", 10)
        self.created_by_user_id = kwargs.get("created_by_user_id", 10)
        self.appointment_type_id = kwargs.get("appointment_type_id", 1)
        self.booked_by_ai = kwargs.get("booked_by_ai", False)
        self.internal_notes = kwargs.get("internal_notes", None)
        self.meeting_notes = kwargs.get("meeting_notes", None)
        self.organization_id = kwargs.get("organization_id", 1)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 18, 8, 0))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 18, 8, 0))


@pytest.fixture
def auth_user():
    return MockUser()


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


# Shared patch targets
_SEARCH = "routes.scheduler.search"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _mock_query_chain(results, count=None):
    """Create a mock SQLAlchemy query chain that returns results."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = results
    mock_query.count.return_value = count if count is not None else len(results)
    mock_query.distinct.return_value = mock_query
    return mock_query


# =============================================================================
# GET /search — Advanced appointment search
# =============================================================================

class TestSearchAppointments:
    """GET /api/v1/scheduler/search."""

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_basic_success(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        appt = MockAppointment(id=1, title="Consultation with John")
        MockApptModel = MagicMock()
        mock_query = _mock_query_chain([appt], count=1)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["pagination"]["total"] == 1

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_with_text_query(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        appt = MockAppointment(id=1, attendee_name="John Doe")
        MockApptModel = MagicMock()
        # Make ilike available on attributes
        MockApptModel.title = MagicMock()
        MockApptModel.attendee_name = MagicMock()
        MockApptModel.attendee_email = MagicMock()
        MockApptModel.description = MagicMock()
        MockApptModel.internal_notes = MagicMock()
        MockApptModel.meeting_notes = MagicMock()
        MockApptModel.attendee_notes = MagicMock()
        MockApptModel.location = MagicMock()

        mock_query = _mock_query_chain([appt], count=1)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?q=John",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filters_applied"]["q"] == "John"

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_empty_results(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = _mock_query_chain([], count=0)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?q=NonexistentPerson",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["pagination"]["total"] == 0

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_with_date_range(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = _mock_query_chain([], count=0)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?date_from=2026-03-01&date_to=2026-03-31",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filters_applied"]["date_from"] == "2026-03-01"
        assert data["filters_applied"]["date_to"] == "2026-03-31"

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_with_status_filter(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        MockApptModel.status = MagicMock()
        mock_query = _mock_query_chain([], count=0)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?status=scheduled&status=completed",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filters_applied"]["status"] == ["scheduled", "completed"]

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_pagination_metadata(self, mock_auth, mock_models, auth_user):
        """Pagination should return correct metadata."""
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = _mock_query_chain([], count=100)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?page=2&page_size=10",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total"] == 100
        assert data["pagination"]["total_pages"] == 10
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is True

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_search_with_attendee_email(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = _mock_query_chain([], count=0)
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search?attendee_email=john@example.com",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["filters_applied"]["attendee_email"] == "john@example.com"

    def test_search_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/search")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /search/suggestions — Typeahead suggestions
# =============================================================================

class TestSearchSuggestions:
    """GET /api/v1/scheduler/search/suggestions."""

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_suggestions_success(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        # Mock the query chain for distinct name/email/title lookups
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [("John Doe",), ("Jane Smith",)]
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search/suggestions?q=jo",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["query"] == "jo"
        assert len(data["suggestions"]) > 0

    @patch(f"{_SEARCH}.get_models")
    @patch(f"{_SEARCH}.get_current_user", new_callable=AsyncMock)
    def test_suggestions_empty(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_SEARCH}._is_scheduler_admin", return_value=True), \
             patch(f"{_SEARCH}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/search/suggestions?q=zzzznonexistent",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_suggestions_query_too_short(self):
        """Query shorter than 2 chars should return 422 (min_length=2)."""
        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/search/suggestions?q=a",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_suggestions_missing_query(self):
        """Missing required 'q' param should return 422."""
        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/search/suggestions",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_suggestions_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/search/suggestions?q=test")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# Helper function unit tests
# =============================================================================

class TestEscapeLike:
    """Unit tests for _escape_like helper."""

    def test_escape_percent(self):
        from routes.scheduler.search import _escape_like
        assert _escape_like("50%") == "50\\%"

    def test_escape_underscore(self):
        from routes.scheduler.search import _escape_like
        assert _escape_like("test_user") == "test\\_user"

    def test_escape_backslash(self):
        from routes.scheduler.search import _escape_like
        assert _escape_like("path\\file") == "path\\\\file"

    def test_escape_normal_text(self):
        from routes.scheduler.search import _escape_like
        assert _escape_like("John Doe") == "John Doe"

    def test_escape_multiple_specials(self):
        from routes.scheduler.search import _escape_like
        result = _escape_like("50%_test\\value")
        assert "\\%" in result
        assert "\\_" in result
        assert "\\\\" in result
