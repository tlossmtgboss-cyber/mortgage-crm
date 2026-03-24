"""
Scheduler Labels Route Tests

Tests for the label CRUD and assignment endpoints in routes/scheduler/labels.py.
Covers:
  - POST   /labels                  Create a color label
  - GET    /labels                  List labels for org
  - PUT    /labels/{id}             Update label (name, color)
  - DELETE /labels/{id}             Delete label (soft-delete)
  - POST   /labels/assign           Assign label(s) to appointment
  - DELETE /labels/assign           Remove label(s) from appointment
  - Edge cases: duplicate name, invalid color, nonexistent appointment
  - Org isolation: can't see/modify other org's labels
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# MOCK OBJECTS
# =============================================================================

class MockUser:
    """Mock authenticated user."""
    def __init__(self, role="loan_officer", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "lo@test.com"
        self.is_active = True


class MockLabel:
    """Mock CalendarLabel model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", None)
        self.name = kwargs.get("name", "Test Label")
        self.color = kwargs.get("color", "#4A90D9")
        self.icon = kwargs.get("icon", None)
        self.is_default = kwargs.get("is_default", False)
        self.is_active = kwargs.get("is_active", True)
        self.sort_order = kwargs.get("sort_order", 0)
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))


class MockAppointment:
    """Mock Appointment model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.organization_id = kwargs.get("organization_id", 1)
        self.title = kwargs.get("title", "Test Appointment")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def auth_user():
    return MockUser()


@pytest.fixture
def other_org_user():
    return MockUser(org_id=999, user_id=99)


@pytest.fixture
def mock_label():
    return MockLabel()


# Shared patch targets
_LABELS = "routes.scheduler.labels"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _make_mock_db(query_side_effects=None):
    """Create a mock DB session with configurable query chains."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    return db


# =============================================================================
# POST /labels — Create label
# =============================================================================

class TestCreateLabel:
    """POST /api/v1/scheduler/labels."""

    @patch(f"{_LABELS}._audit_log")
    @patch(f"{_LABELS}.get_db")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_success(self, mock_auth, mock_get_db, mock_audit, auth_user):
        """Creating a label with valid name and color returns 201."""
        mock_auth.return_value = auth_user
        mock_db = MagicMock()
        # count() for max labels
        mock_db.query.return_value.filter.return_value.count.return_value = 5
        # duplicate check: no existing label
        mock_db.query.return_value.filter.return_value.first.return_value = None
        # max sort_order query
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (3,)
        mock_get_db.return_value = mock_db

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/labels",
            json={"name": "Urgent", "color": "#FF0000"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Urgent"
        assert data["color"] == "#FF0000"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_missing_name(self, mock_auth, auth_user):
        """Omitting name returns 400 validation error."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/labels",
            json={"color": "#FF0000"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_invalid_color(self, mock_auth, auth_user):
        """Invalid hex color returns 400."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/labels",
            json={"name": "Bad Color", "color": "not-a-color"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "hex color" in resp.json()["detail"]["error"].lower()

    @patch(f"{_LABELS}.get_db")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_duplicate_name_returns_409(self, mock_auth, mock_get_db, auth_user):
        """Creating a label with a name that already exists returns 409."""
        mock_auth.return_value = auth_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 5
        # Duplicate check returns an existing label
        mock_db.query.return_value.filter.return_value.first.return_value = MockLabel(name="Urgent")
        mock_get_db.return_value = mock_db

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/labels",
            json={"name": "Urgent", "color": "#FF0000"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 409

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_name_too_long(self, mock_auth, auth_user):
        """Name over 50 characters returns 400."""
        mock_auth.return_value = auth_user

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/labels",
            json={"name": "A" * 51, "color": "#FF0000"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_create_label_short_hex_color_accepted(self, mock_auth, auth_user):
        """3-digit hex color (#RGB) is valid."""
        mock_auth.return_value = auth_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch(f"{_LABELS}.get_db", return_value=mock_db), \
             patch(f"{_LABELS}._audit_log"):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/labels",
                json={"name": "Short Color", "color": "#F00"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 201


# =============================================================================
# GET /labels — List labels
# =============================================================================

class TestListLabels:
    """GET /api/v1/scheduler/labels."""

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_list_labels_success(self, mock_auth, auth_user):
        """List returns labels array and total count."""
        mock_auth.return_value = auth_user

        label1 = MockLabel(id=1, name="Pre-Approval", color="#4A90D9")
        label2 = MockLabel(id=2, name="Closing", color="#8E44AD")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [label1, label2]

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/labels",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["labels"]) == 2
        assert data["labels"][0]["name"] == "Pre-Approval"
        assert data["labels"][1]["name"] == "Closing"

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_list_labels_empty(self, mock_auth, auth_user):
        """Empty org returns zero labels."""
        mock_auth.return_value = auth_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/labels",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["labels"] == []

    def test_list_labels_no_auth(self):
        """Unauthenticated request is rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/labels")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# PUT /labels/{id} — Update label
# =============================================================================

class TestUpdateLabel:
    """PUT /api/v1/scheduler/labels/{id}."""

    @patch(f"{_LABELS}._audit_log")
    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_update_label_name_and_color(self, mock_auth, mock_get_label, mock_audit, auth_user):
        """Updating name and color succeeds."""
        mock_auth.return_value = auth_user
        label = MockLabel(id=5, name="Old Name", color="#000000")
        mock_get_label.return_value = label

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.put(
                "/api/v1/scheduler/labels/5",
                json={"name": "New Name", "color": "#FFFFFF"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["color"] == "#FFFFFF"
        mock_db.commit.assert_called_once()

    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_update_label_not_found(self, mock_auth, mock_get_label, auth_user):
        """Updating a nonexistent label returns 404."""
        mock_auth.return_value = auth_user
        mock_get_label.return_value = None

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.put(
                "/api/v1/scheduler/labels/999",
                json={"name": "Nope"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404

    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_update_label_invalid_color(self, mock_auth, mock_get_label, auth_user):
        """Updating with invalid color returns 400."""
        mock_auth.return_value = auth_user
        mock_get_label.return_value = MockLabel(id=5)

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.put(
                "/api/v1/scheduler/labels/5",
                json={"color": "red"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400


# =============================================================================
# DELETE /labels/{id} — Soft-delete label
# =============================================================================

class TestDeleteLabel:
    """DELETE /api/v1/scheduler/labels/{id}."""

    @patch(f"{_LABELS}._audit_log")
    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_delete_label_success(self, mock_auth, mock_get_label, mock_audit, auth_user):
        """Deleting a label soft-deletes it and cleans up assignments."""
        mock_auth.return_value = auth_user
        label = MockLabel(id=7, name="To Delete")
        mock_get_label.return_value = label

        mock_db = MagicMock()
        # Mock the orphan cleanup delete query
        mock_db.query.return_value.filter.return_value.delete.return_value = 2

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.delete(
                "/api/v1/scheduler/labels/7",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["deleted_id"] == 7
        # Label should be soft-deleted (is_active = False)
        assert label.is_active is False
        mock_db.commit.assert_called_once()

    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_delete_label_not_found(self, mock_auth, mock_get_label, auth_user):
        """Deleting nonexistent label returns 404."""
        mock_auth.return_value = auth_user
        mock_get_label.return_value = None

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.delete(
                "/api/v1/scheduler/labels/999",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404


# =============================================================================
# POST /labels/assign — Assign labels to appointment
# =============================================================================

class TestAssignLabels:
    """POST /api/v1/scheduler/labels/assign."""

    @patch(f"{_LABELS}.get_models")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_assign_label_to_appointment(self, mock_auth, mock_get_models, auth_user):
        """Assigning a valid label to a valid appointment succeeds."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()
        # Appointment lookup: found
        appt = MockAppointment(id=100, organization_id=1)
        # Label lookup: found
        label = MockLabel(id=1, organization_id=1)

        # We need to set up query chains carefully.
        # The route does multiple db.query() calls. We'll use side_effect.
        appointment_query = MagicMock()
        appointment_query.filter.return_value.first.return_value = appt

        label_query = MagicMock()
        label_query.filter.return_value.all.return_value = [label]

        existing_query = MagicMock()
        existing_query.filter.return_value.all.return_value = []  # no existing assignments

        mock_db.query.side_effect = [appointment_query, label_query, existing_query]

        # Mock the Appointment model in get_models
        MockAppointmentModel = MagicMock()
        MockAppointmentModel.id = MagicMock()
        MockAppointmentModel.organization_id = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointmentModel}

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/labels/assign",
                json={"appointment_id": 100, "label_ids": [1]},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["assigned"] == 1
        assert data["appointment_id"] == 100

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_assign_label_missing_appointment_id(self, mock_auth, auth_user):
        """Missing appointment_id returns 400."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/labels/assign",
                json={"label_ids": [1]},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400

    @patch(f"{_LABELS}.get_models")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_assign_label_nonexistent_appointment(self, mock_auth, mock_get_models, auth_user):
        """Assigning to a nonexistent appointment returns 404."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()
        # Appointment not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        MockAppointmentModel = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointmentModel}

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/labels/assign",
                json={"appointment_id": 9999, "label_ids": [1]},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404

    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_assign_label_empty_label_ids(self, mock_auth, auth_user):
        """Empty label_ids list returns 400."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/labels/assign",
                json={"appointment_id": 100, "label_ids": []},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400


# =============================================================================
# DELETE /labels/assign — Unassign labels from appointment
# =============================================================================

class TestUnassignLabels:
    """DELETE /api/v1/scheduler/labels/assign."""

    @patch(f"{_LABELS}.get_models")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_unassign_label_from_appointment(self, mock_auth, mock_get_models, auth_user):
        """Removing a label assignment succeeds."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()
        appt = MockAppointment(id=100, organization_id=1)

        # Appointment query -> found
        appt_query = MagicMock()
        appt_query.filter.return_value.first.return_value = appt

        # Valid label IDs query
        label_ids_query = MagicMock()
        label_ids_query.filter.return_value.all.return_value = [(1,)]

        # Delete query returns count of deleted rows
        delete_query = MagicMock()
        delete_query.filter.return_value.delete.return_value = 1

        mock_db.query.side_effect = [appt_query, label_ids_query, delete_query]

        MockAppointmentModel = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointmentModel}

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.request(
                "DELETE",
                "/api/v1/scheduler/labels/assign",
                json={"appointment_id": 100, "label_ids": [1]},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["removed"] == 1

    @patch(f"{_LABELS}.get_models")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_unassign_from_nonexistent_appointment(self, mock_auth, mock_get_models, auth_user):
        """Unassigning from nonexistent appointment returns 404."""
        mock_auth.return_value = auth_user

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        MockAppointmentModel = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointmentModel}

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.request(
                "DELETE",
                "/api/v1/scheduler/labels/assign",
                json={"appointment_id": 9999, "label_ids": [1]},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404


# =============================================================================
# ORG ISOLATION — Cross-org access denied
# =============================================================================

class TestOrgIsolation:
    """Verify labels are scoped to the user's organization."""

    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_update_other_orgs_label_returns_404(self, mock_auth, mock_get_label, other_org_user):
        """User from org 999 cannot update a label from org 1 (returns 404)."""
        mock_auth.return_value = other_org_user
        # _get_label_for_user filters by org_id, so label is not found
        mock_get_label.return_value = None

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.put(
                "/api/v1/scheduler/labels/1",
                json={"name": "Hijacked"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404

    @patch(f"{_LABELS}._get_label_for_user")
    @patch(f"{_LABELS}.get_current_user", new_callable=AsyncMock)
    def test_delete_other_orgs_label_returns_404(self, mock_auth, mock_get_label, other_org_user):
        """User from org 999 cannot delete a label from org 1."""
        mock_auth.return_value = other_org_user
        mock_get_label.return_value = None

        mock_db = MagicMock()

        with patch(f"{_LABELS}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.delete(
                "/api/v1/scheduler/labels/1",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404


# =============================================================================
# HELPER UNIT TESTS
# =============================================================================

class TestHelpers:
    """Unit tests for label helper functions."""

    def test_is_valid_hex_color_6_digit(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("#4A90D9") is True

    def test_is_valid_hex_color_3_digit(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("#F00") is True

    def test_is_valid_hex_color_no_hash(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("4A90D9") is False

    def test_is_valid_hex_color_invalid_chars(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("#ZZZZZZ") is False

    def test_is_valid_hex_color_wrong_length(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("#12345") is False

    def test_is_valid_hex_color_empty(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color("") is False

    def test_is_valid_hex_color_none(self):
        from routes.scheduler.labels import _is_valid_hex_color
        assert _is_valid_hex_color(None) is False

    def test_serialize_label(self):
        from routes.scheduler.labels import _serialize_label
        label = MockLabel(
            id=3, name="Closing", color="#8E44AD", icon=None,
            is_default=True, user_id=None, sort_order=2,
        )
        result = _serialize_label(label)
        assert result["id"] == 3
        assert result["name"] == "Closing"
        assert result["color"] == "#8E44AD"
        assert result["is_default"] is True
        assert result["is_personal"] is False
        assert result["sort_order"] == 2

    def test_serialize_personal_label(self):
        from routes.scheduler.labels import _serialize_label
        label = MockLabel(id=4, name="My Label", user_id=10)
        result = _serialize_label(label)
        assert result["is_personal"] is True
