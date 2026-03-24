"""
Scheduler Reminder Route Tests

Tests for the reminder route handlers in routes/scheduler/reminders.py.
Covers:
  - GET    /reminders/templates          List org's reminder templates
  - POST   /reminders/templates          Create custom template
  - PUT    /reminders/templates/{id}     Update template
  - DELETE /reminders/templates/{id}     Delete template (soft-delete)
  - GET    /reminders/log                View reminder send history
  - POST   /reminders/test               Send test reminder
  - Validation: invalid channel, missing name, bad timing_minutes
  - Org isolation: templates from other orgs are not visible/editable
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
        self.first_name = "Test"
        self.last_name = "User"


class MockReminderTemplate:
    """Mock ReminderTemplate model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.name = kwargs.get("name", "24-Hour Email Reminder")
        self.channel = kwargs.get("channel", "email")
        self.timing_minutes = kwargs.get("timing_minutes", 1440)
        self.subject_template = kwargs.get("subject_template", "Reminder: {appointment_type} tomorrow")
        self.body_template = kwargs.get("body_template", "Hi {client_name}, your appointment is tomorrow.")
        self.is_active = kwargs.get("is_active", True)
        self.appointment_type_id = kwargs.get("appointment_type_id", None)
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))


class MockReminderLog:
    """Mock ReminderLog model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.appointment_id = kwargs.get("appointment_id", 100)
        self.template_id = kwargs.get("template_id", 1)
        self.channel = kwargs.get("channel", "email")
        self.status = kwargs.get("status", "sent")
        self.sent_at = kwargs.get("sent_at", datetime.now(timezone.utc))
        self.error_message = kwargs.get("error_message", None)
        self.external_id = kwargs.get("external_id", "msg_abc123")
        self.recipient_email = kwargs.get("recipient_email", "borrower@test.com")
        self.recipient_phone = kwargs.get("recipient_phone", None)


class MockAppointment:
    """Mock Appointment for org isolation on log queries."""
    id = 100
    organization_id = 1


@pytest.fixture
def auth_user():
    return MockUser()


@pytest.fixture
def other_org_user():
    return MockUser(org_id=999, user_id=99)


# Patch targets
_REMINDERS = "routes.scheduler.reminders"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# Mock query builder helpers
# =============================================================================

def _mock_query_returning(items, count=None):
    """
    Build a mock db.query(...) chain that supports
    .filter().order_by().offset().limit().all()/.count()/.first()
    """
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = items
    query.first.return_value = items[0] if items else None
    query.count.return_value = count if count is not None else len(items)
    return query


def _mock_db_with_template_query(templates, count=None):
    """Return a mock db session whose query() returns the given templates."""
    db = MagicMock()
    db.query.return_value = _mock_query_returning(templates, count)
    return db


# =============================================================================
# GET /reminders/templates -- List reminder templates
# =============================================================================

class TestListReminderTemplates:
    """GET /api/v1/scheduler/reminders/templates."""

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_list_templates_success(self, mock_auth, mock_get_db, auth_user):
        """Should return active templates for the org."""
        mock_auth.return_value = auth_user

        t1 = MockReminderTemplate(id=1, timing_minutes=1440, name="24h Email")
        t2 = MockReminderTemplate(id=2, timing_minutes=60, channel="sms", name="1h SMS")
        db = _mock_db_with_template_query([t1, t2])
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reminders/templates",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2
        assert data["templates"][0]["name"] == "24h Email"
        assert data["templates"][1]["name"] == "1h SMS"

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_list_templates_empty(self, mock_auth, mock_get_db, auth_user):
        """Should return empty list when org has no templates."""
        mock_auth.return_value = auth_user

        db = _mock_db_with_template_query([])
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reminders/templates",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["templates"] == []

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_list_templates_timing_label_days(self, mock_auth, mock_get_db, auth_user):
        """timing_label should show days for >= 1440 minutes."""
        mock_auth.return_value = auth_user

        t = MockReminderTemplate(timing_minutes=2880)  # 2 days
        db = _mock_db_with_template_query([t])
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reminders/templates",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["templates"][0]["timing_label"] == "2 days before"

    def test_list_templates_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/reminders/templates")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# POST /reminders/templates -- Create template
# =============================================================================

class TestCreateReminderTemplate:
    """POST /api/v1/scheduler/reminders/templates."""

    @patch(f"{_REMINDERS}._audit_log")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_success(self, mock_auth, mock_get_db, mock_audit, auth_user):
        """Should create a template and return 201."""
        mock_auth.return_value = auth_user

        db = MagicMock()
        # count() for the 50-template cap check
        count_query = MagicMock()
        count_query.filter.return_value = count_query
        count_query.count.return_value = 3

        db.query.return_value = count_query

        created_template = None

        def capture_add(obj):
            nonlocal created_template
            # Simulate ID assignment on flush
            obj.id = 42
            obj.created_at = datetime.now(timezone.utc)
            created_template = obj

        db.add.side_effect = capture_add
        db.flush.return_value = None
        db.commit.return_value = None
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "name": "2-Hour SMS Reminder",
                "channel": "sms",
                "timing_minutes": 120,
                "body_template": "Your appt with {lo_name} is in 2 hours!",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 42
        assert data["name"] == "2-Hour SMS Reminder"
        assert data["channel"] == "sms"
        assert data["timing_minutes"] == 120
        assert data["timing_label"] == "2 hours before"

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_missing_name(self, mock_auth, mock_get_db, auth_user):
        """Should return 400 when name is missing."""
        mock_auth.return_value = auth_user
        mock_get_db.return_value = MagicMock()

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "channel": "email",
                "timing_minutes": 60,
                "body_template": "Reminder body",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "name" in resp.json()["detail"].lower()

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_invalid_channel(self, mock_auth, mock_get_db, auth_user):
        """Should return 400 for invalid channel value."""
        mock_auth.return_value = auth_user
        mock_get_db.return_value = MagicMock()

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "name": "Bad Channel",
                "channel": "push_notification",
                "timing_minutes": 60,
                "body_template": "Test body",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "channel" in resp.json()["detail"].lower()

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_invalid_timing_zero(self, mock_auth, mock_get_db, auth_user):
        """timing_minutes must be a positive integer."""
        mock_auth.return_value = auth_user
        mock_get_db.return_value = MagicMock()

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "name": "Bad Timing",
                "channel": "email",
                "timing_minutes": 0,
                "body_template": "Test body",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "timing_minutes" in resp.json()["detail"]

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_missing_body(self, mock_auth, mock_get_db, auth_user):
        """Should return 400 when body_template is missing."""
        mock_auth.return_value = auth_user
        mock_get_db.return_value = MagicMock()

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "name": "No Body",
                "channel": "email",
                "timing_minutes": 60,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "body_template" in resp.json()["detail"]

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_create_template_cap_at_50(self, mock_auth, mock_get_db, auth_user):
        """Should reject creation when org already has 50 templates."""
        mock_auth.return_value = auth_user

        db = MagicMock()
        count_query = MagicMock()
        count_query.filter.return_value = count_query
        count_query.count.return_value = 50
        db.query.return_value = count_query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/templates",
            json={
                "name": "One Too Many",
                "channel": "email",
                "timing_minutes": 60,
                "body_template": "Some body",
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "50" in resp.json()["detail"]


# =============================================================================
# PUT /reminders/templates/{id} -- Update template
# =============================================================================

class TestUpdateReminderTemplate:
    """PUT /api/v1/scheduler/reminders/templates/{id}."""

    @patch(f"{_REMINDERS}._audit_log")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_update_template_success(self, mock_auth, mock_get_db, mock_audit, auth_user):
        """Should update template fields and return updated data."""
        mock_auth.return_value = auth_user

        existing = MockReminderTemplate(id=5, name="Old Name", channel="email", timing_minutes=60)
        db = MagicMock()
        query = _mock_query_returning([existing])
        db.query.return_value = query
        db.commit.return_value = None
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/reminders/templates/5",
            json={"name": "New Name", "timing_minutes": 120},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["timing_minutes"] == 120
        assert data["timing_label"] == "2 hours before"

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_update_template_not_found(self, mock_auth, mock_get_db, auth_user):
        """Should return 404 if template does not exist for this org."""
        mock_auth.return_value = auth_user

        db = MagicMock()
        query = _mock_query_returning([])
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/reminders/templates/999",
            json={"name": "Nope"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_update_template_invalid_channel(self, mock_auth, mock_get_db, auth_user):
        """Should return 400 for invalid channel on update."""
        mock_auth.return_value = auth_user

        existing = MockReminderTemplate(id=5)
        db = MagicMock()
        query = _mock_query_returning([existing])
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.put(
            "/api/v1/scheduler/reminders/templates/5",
            json={"channel": "carrier_pigeon"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "channel" in resp.json()["detail"].lower()


# =============================================================================
# DELETE /reminders/templates/{id} -- Soft-delete template
# =============================================================================

class TestDeleteReminderTemplate:
    """DELETE /api/v1/scheduler/reminders/templates/{id}."""

    @patch(f"{_REMINDERS}._audit_log")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_delete_template_success(self, mock_auth, mock_get_db, mock_audit, auth_user):
        """Should soft-delete (deactivate) the template."""
        mock_auth.return_value = auth_user

        existing = MockReminderTemplate(id=7, name="To Delete", is_active=True)
        db = MagicMock()
        query = _mock_query_returning([existing])
        db.query.return_value = query
        db.commit.return_value = None
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/reminders/templates/7",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["deleted_id"] == 7
        # Verify soft-delete: is_active set to False
        assert existing.is_active is False

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_delete_template_not_found(self, mock_auth, mock_get_db, auth_user):
        """Should return 404 for non-existent template."""
        mock_auth.return_value = auth_user

        db = MagicMock()
        query = _mock_query_returning([])
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/reminders/templates/999",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_delete_template_org_isolation(self, mock_auth, mock_get_db, other_org_user):
        """Template belonging to org 1 should not be deletable by org 999 user."""
        mock_auth.return_value = other_org_user

        # The query filters by organization_id, so it returns nothing for org 999
        db = MagicMock()
        query = _mock_query_returning([])
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/reminders/templates/7",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404


# =============================================================================
# GET /reminders/log -- View send history
# =============================================================================

class TestListReminderLogs:
    """GET /api/v1/scheduler/reminders/log."""

    @patch(f"{_REMINDERS}.get_models")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_list_logs_success(self, mock_auth, mock_get_db, mock_get_models, auth_user):
        """Should return paginated reminder send history."""
        mock_auth.return_value = auth_user

        mock_appointment_model = MagicMock()
        mock_appointment_model.id = 100
        mock_appointment_model.organization_id = 1
        mock_get_models.return_value = {"Appointment": mock_appointment_model}

        log1 = MockReminderLog(id=1, status="sent", channel="email")
        log2 = MockReminderLog(id=2, status="failed", channel="sms", error_message="Telnyx timeout")

        db = MagicMock()
        query = MagicMock()
        query.join.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = [log1, log2]
        query.count.return_value = 2
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reminders/log",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["logs"]) == 2
        assert data["logs"][0]["status"] == "sent"
        assert data["logs"][1]["error_message"] == "Telnyx timeout"

    @patch(f"{_REMINDERS}.get_models")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_list_logs_invalid_status_filter(self, mock_auth, mock_get_db, mock_get_models, auth_user):
        """Should return 400 for invalid status filter."""
        mock_auth.return_value = auth_user
        mock_get_models.return_value = {"Appointment": MagicMock()}

        db = MagicMock()
        query = MagicMock()
        query.join.return_value = query
        query.filter.return_value = query
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reminders/log?status=delivered",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "status" in resp.json()["detail"].lower()


# =============================================================================
# POST /reminders/test -- Send test reminder
# =============================================================================

class TestSendTestReminder:
    """POST /api/v1/scheduler/reminders/test."""

    @patch("services.reminder_service.ReminderService._send_email")
    @patch("services.reminder_service.ReminderService.render_template")
    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_send_test_email_success(self, mock_auth, mock_get_db, mock_render, mock_send_email, auth_user):
        """Should send test email and return preview."""
        mock_auth.return_value = auth_user

        template = MockReminderTemplate(
            id=3,
            channel="email",
            subject_template="Reminder: {appointment_type}",
            body_template="Hi {client_name}, your appt is tomorrow.",
        )

        db = MagicMock()
        query = _mock_query_returning([template])
        db.query.return_value = query
        mock_get_db.return_value = db

        # render_template is called twice: once for subject, once for body
        mock_render.side_effect = [
            "Reminder: Discovery Call",
            "Hi Jane Doe, your appt is tomorrow.",
        ]
        mock_send_email.return_value = {"success": True, "message_id": "test_msg_1"}

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/test",
            json={"template_id": 3, "email": "qa@test.com"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "preview" in data
        assert len(data["results"]) >= 1
        assert data["results"][0]["channel"] == "email"
        # Verify the email sending was actually called
        mock_send_email.assert_called_once()

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_send_test_missing_template_id(self, mock_auth, mock_get_db, auth_user):
        """Should return 400 when template_id is not provided."""
        mock_auth.return_value = auth_user
        mock_get_db.return_value = MagicMock()

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/test",
            json={"email": "test@test.com"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "template_id" in resp.json()["detail"].lower()

    @patch(f"{_REMINDERS}.get_db")
    @patch(f"{_REMINDERS}.get_current_user", new_callable=AsyncMock)
    def test_send_test_template_not_found(self, mock_auth, mock_get_db, auth_user):
        """Should return 404 when template does not exist for org."""
        mock_auth.return_value = auth_user

        db = MagicMock()
        query = _mock_query_returning([])
        db.query.return_value = query
        mock_get_db.return_value = db

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reminders/test",
            json={"template_id": 999},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404


# =============================================================================
# HELPER: _timing_label
# =============================================================================

class TestTimingLabel:
    """Unit tests for the _timing_label helper."""

    def test_minutes(self):
        from routes.scheduler.reminders import _timing_label
        assert _timing_label(15) == "15 minutes before"
        assert _timing_label(1) == "1 minute before"
        assert _timing_label(30) == "30 minutes before"

    def test_hours(self):
        from routes.scheduler.reminders import _timing_label
        assert _timing_label(60) == "1 hour before"
        assert _timing_label(120) == "2 hours before"

    def test_days(self):
        from routes.scheduler.reminders import _timing_label
        assert _timing_label(1440) == "1 day before"
        assert _timing_label(2880) == "2 days before"
        assert _timing_label(4320) == "3 days before"
