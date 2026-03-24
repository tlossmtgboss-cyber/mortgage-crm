"""
Scheduler Today Summary Route Tests

Tests for the today summary endpoint in routes/scheduler/today_summary.py.
Covers:
  - GET /today-summary — aggregated LO dashboard summary
  - Returns today's appointments count and list
  - Returns upcoming (next) appointment
  - Returns tasks due today and overdue tasks
  - Handles timezone correctly for "today"
  - Empty day (no appointments, tasks, leads, SLA) returns valid response
  - Org/user scoping — LO sees only their appointments
  - SLA alerts surface correctly
  - Leads needing follow-up
  - 503 when scheduler models are unavailable
  - Auth required
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, time, timedelta, timezone, date
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# MOCK OBJECTS
# =============================================================================

class MockUser:
    """Mock user for authenticated tests."""
    def __init__(self, role="loan_officer", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "lo@test.com"
        self.is_active = True


class MockAppointment:
    """Mock Appointment model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.assigned_user_id = kwargs.get("assigned_user_id", 10)
        self.created_by_user_id = kwargs.get("created_by_user_id", 10)
        self.title = kwargs.get("title", "Discovery Call")
        self.scheduled_start = kwargs.get("scheduled_start")
        self.scheduled_end = kwargs.get("scheduled_end")
        self.attendee_name = kwargs.get("attendee_name", "Jane Borrower")
        self.meeting_type = kwargs.get("meeting_type", MagicMock(value="discovery_call"))
        self.status = kwargs.get("status", MagicMock(value="booked"))
        self.meeting_mode = kwargs.get("meeting_mode", MagicMock(value="video"))
        self.video_link = kwargs.get("video_link", "https://zoom.us/j/123")
        self.lead_id = kwargs.get("lead_id", 100)
        self.loan_id = kwargs.get("loan_id", None)


class MockTask:
    """Mock Task model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.owner_id = kwargs.get("owner_id", 10)
        self.title = kwargs.get("title", "Follow up with borrower")
        self.description = kwargs.get("description", "Call regarding docs")
        self.status = kwargs.get("status", "pending")
        self.priority = kwargs.get("priority", "medium")
        self.due_date = kwargs.get("due_date")
        self.related_contact_name = kwargs.get("related_contact_name", "John Doe")
        self.lead_id = kwargs.get("lead_id", 100)
        self.loan_id = kwargs.get("loan_id", None)


class MockLead:
    """Mock Lead model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.owner_id = kwargs.get("owner_id", 10)
        self.name = kwargs.get("name", "Alice Smith")
        self.email = kwargs.get("email", "alice@example.com")
        self.phone = kwargs.get("phone", "555-1234")
        self.stage = kwargs.get("stage", "New")
        self.last_contact = kwargs.get("last_contact", None)
        self.ai_score = kwargs.get("ai_score", 72)


class MockLoan:
    """Mock Loan model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.loan_officer_id = kwargs.get("loan_officer_id", 10)
        self.loan_number = kwargs.get("loan_number", "LN-001")
        self.borrower_name = kwargs.get("borrower_name", "Bob Builder")
        self.stage = kwargs.get("stage", "APPLICATION")
        self.stage_changed_at = kwargs.get("stage_changed_at")


# =============================================================================
# HELPERS
# =============================================================================

_SUMMARY = "routes.scheduler.today_summary"

def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _make_mock_query(results):
    """Create a mock SQLAlchemy query chain that returns the given results."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = results
    return mock_query


# =============================================================================
# 1. EMPTY DAY — valid response with zeros
# =============================================================================

class TestTodaySummaryEmptyDay:
    """GET /api/v1/scheduler/today-summary with no data returns valid empty response."""

    @patch(f"{_SUMMARY}._fetch_sla_alerts")
    @patch(f"{_SUMMARY}._fetch_leads_needing_followup")
    @patch(f"{_SUMMARY}._fetch_today_tasks")
    @patch(f"{_SUMMARY}._fetch_today_appointments")
    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_empty_day_returns_valid_structure(
        self, mock_auth, mock_models, mock_appts, mock_tasks, mock_leads, mock_sla
    ):
        user = MockUser()
        mock_auth.return_value = user
        mock_models.return_value = {"Appointment": MagicMock()}

        from routes.scheduler.today_summary import AppointmentsSection, TasksSection, LeadsSection, SLAAlertsSection
        mock_appts.return_value = AppointmentsSection(count=0, items=[], next_appointment=None)
        mock_tasks.return_value = TasksSection(due_today=0, overdue=0, items=[])
        mock_leads.return_value = LeadsSection(need_follow_up=0, items=[])
        mock_sla.return_value = SLAAlertsSection(total=0, critical=0, items=[])

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["appointments"]["count"] == 0
        assert data["appointments"]["items"] == []
        assert data["appointments"]["next_appointment"] is None
        assert data["tasks"]["due_today"] == 0
        assert data["tasks"]["overdue"] == 0
        assert data["leads"]["need_follow_up"] == 0
        assert data["sla_alerts"]["total"] == 0
        assert "generated_at" in data


# =============================================================================
# 2. TODAY'S APPOINTMENTS — count and list
# =============================================================================

class TestTodaySummaryAppointments:
    """Appointments section returns correct count and items."""

    def test_fetch_today_appointments_returns_items(self):
        """Unit test of _fetch_today_appointments helper."""
        from routes.scheduler.today_summary import _fetch_today_appointments

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)
        appt1 = MockAppointment(
            id=1,
            scheduled_start=datetime(2026, 3, 23, 10, 0, 0),
            scheduled_end=datetime(2026, 3, 23, 10, 30, 0),
            attendee_name="Alice",
        )
        appt2 = MockAppointment(
            id=2,
            scheduled_start=datetime(2026, 3, 23, 15, 0, 0),
            scheduled_end=datetime(2026, 3, 23, 15, 30, 0),
            attendee_name="Bob",
        )

        MockAppointmentModel = MagicMock()
        mock_db = MagicMock()
        mock_query = _make_mock_query([appt1, appt2])
        mock_db.query.return_value = mock_query

        models = {"Appointment": MockAppointmentModel}
        result = _fetch_today_appointments(mock_db, models, user_id=10, org_id=1, now=now)

        assert result.count == 2
        assert len(result.items) == 2
        assert result.items[0].client_name == "Alice"
        assert result.items[1].client_name == "Bob"

    def test_fetch_today_appointments_no_model_returns_empty(self):
        """If Appointment model is not available, return empty section."""
        from routes.scheduler.today_summary import _fetch_today_appointments

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)
        mock_db = MagicMock()

        result = _fetch_today_appointments(mock_db, {}, user_id=10, org_id=1, now=now)
        assert result.count == 0
        assert result.items == []


# =============================================================================
# 3. NEXT APPOINTMENT — upcoming (not past)
# =============================================================================

class TestNextAppointment:
    """next_appointment field picks the first appointment still in the future."""

    def test_next_appointment_is_future_only(self):
        """Past appointments should not be selected as next_appointment."""
        from routes.scheduler.today_summary import _fetch_today_appointments

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        # Past appointment (10 AM, already happened)
        past_appt = MockAppointment(
            id=1,
            scheduled_start=datetime(2026, 3, 23, 10, 0, 0),
            scheduled_end=datetime(2026, 3, 23, 10, 30, 0),
        )
        # Future appointment (15:00, hasn't started)
        future_appt = MockAppointment(
            id=2,
            scheduled_start=datetime(2026, 3, 23, 15, 0, 0),
            scheduled_end=datetime(2026, 3, 23, 15, 30, 0),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([past_appt, future_appt])
        mock_db.query.return_value = mock_query

        models = {"Appointment": MagicMock()}
        result = _fetch_today_appointments(mock_db, models, user_id=10, org_id=1, now=now)

        assert result.next_appointment is not None
        assert result.next_appointment.id == 2

    def test_no_future_appointments_next_is_none(self):
        """When all appointments are in the past, next_appointment is None."""
        from routes.scheduler.today_summary import _fetch_today_appointments

        now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)

        past_appt = MockAppointment(
            id=1,
            scheduled_start=datetime(2026, 3, 23, 10, 0, 0),
            scheduled_end=datetime(2026, 3, 23, 10, 30, 0),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([past_appt])
        mock_db.query.return_value = mock_query

        models = {"Appointment": MagicMock()}
        result = _fetch_today_appointments(mock_db, models, user_id=10, org_id=1, now=now)

        assert result.count == 1
        assert result.next_appointment is None


# =============================================================================
# 4. TASKS DUE TODAY AND OVERDUE
# =============================================================================

class TestTodaySummaryTasks:
    """Tasks section counts due_today and overdue correctly."""

    @patch("routes.scheduler.today_summary.Task", create=True)
    def test_fetch_today_tasks_separates_due_and_overdue(self, mock_task_cls):
        """Tasks before today_start are overdue, tasks within today are due_today."""
        from routes.scheduler.today_summary import _fetch_today_tasks

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)
        today_start = datetime.combine(now.date(), time.min)

        # Overdue task (yesterday)
        overdue_task = MockTask(
            id=1,
            title="Overdue task",
            due_date=datetime(2026, 3, 22, 10, 0, 0),
        )
        # Due today task
        today_task = MockTask(
            id=2,
            title="Today task",
            due_date=datetime(2026, 3, 23, 16, 0, 0),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([overdue_task, today_task])
        mock_db.query.return_value = mock_query

        with patch("database.models.task.Task", mock_task_cls):
            result = _fetch_today_tasks(mock_db, user_id=10, org_id=1, now=now)

        assert result.overdue == 1
        assert result.due_today == 1
        assert len(result.items) == 2
        # The overdue item should have is_overdue=True
        overdue_items = [item for item in result.items if item.is_overdue]
        assert len(overdue_items) == 1
        assert overdue_items[0].id == 1


# =============================================================================
# 5. TIMEZONE HANDLING — "today" boundary
# =============================================================================

class TestTimezoneHandling:
    """The endpoint uses UTC now for determining today's date boundaries."""

    @patch(f"{_SUMMARY}._fetch_sla_alerts")
    @patch(f"{_SUMMARY}._fetch_leads_needing_followup")
    @patch(f"{_SUMMARY}._fetch_today_tasks")
    @patch(f"{_SUMMARY}._fetch_today_appointments")
    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_generated_at_is_utc_iso_format(
        self, mock_auth, mock_models, mock_appts, mock_tasks, mock_leads, mock_sla
    ):
        """generated_at should be an ISO 8601 UTC timestamp."""
        user = MockUser()
        mock_auth.return_value = user
        mock_models.return_value = {"Appointment": MagicMock()}

        from routes.scheduler.today_summary import AppointmentsSection, TasksSection, LeadsSection, SLAAlertsSection
        mock_appts.return_value = AppointmentsSection()
        mock_tasks.return_value = TasksSection()
        mock_leads.return_value = LeadsSection()
        mock_sla.return_value = SLAAlertsSection()

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        generated_at = resp.json()["generated_at"]
        # Should be parseable as ISO datetime and contain UTC offset
        parsed = datetime.fromisoformat(generated_at)
        assert parsed.tzinfo is not None


# =============================================================================
# 6. ORG/USER SCOPING — LO sees only their data
# =============================================================================

class TestOrgUserScoping:
    """Verify org_id and user_id are passed through to all query helpers."""

    @patch(f"{_SUMMARY}._fetch_sla_alerts")
    @patch(f"{_SUMMARY}._fetch_leads_needing_followup")
    @patch(f"{_SUMMARY}._fetch_today_tasks")
    @patch(f"{_SUMMARY}._fetch_today_appointments")
    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_queries_use_correct_user_and_org(
        self, mock_auth, mock_models, mock_appts, mock_tasks, mock_leads, mock_sla
    ):
        """Each helper receives the authenticated user's id and org_id."""
        user = MockUser(user_id=42, org_id=7)
        mock_auth.return_value = user
        mock_models.return_value = {"Appointment": MagicMock()}

        from routes.scheduler.today_summary import AppointmentsSection, TasksSection, LeadsSection, SLAAlertsSection
        mock_appts.return_value = AppointmentsSection()
        mock_tasks.return_value = TasksSection()
        mock_leads.return_value = LeadsSection()
        mock_sla.return_value = SLAAlertsSection()

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200

        # Verify appointments helper was called with correct user_id and org_id
        mock_appts.assert_called_once()
        call_kwargs = mock_appts.call_args
        # Positional args: (db, models, user_id, org_id, now)
        assert call_kwargs[0][2] == 42   # user_id
        assert call_kwargs[0][3] == 7    # org_id

        # Verify tasks helper was called with correct user_id and org_id
        mock_tasks.assert_called_once()
        task_args = mock_tasks.call_args[0]
        assert task_args[1] == 42  # user_id
        assert task_args[2] == 7   # org_id

        # Verify leads helper
        mock_leads.assert_called_once()
        lead_args = mock_leads.call_args[0]
        assert lead_args[1] == 42  # user_id
        assert lead_args[2] == 7   # org_id

        # Verify SLA alerts helper
        mock_sla.assert_called_once()
        sla_args = mock_sla.call_args[0]
        assert sla_args[1] == 42  # user_id
        assert sla_args[2] == 7   # org_id


# =============================================================================
# 7. SLA ALERTS
# =============================================================================

class TestSLAAlerts:
    """SLA alerts section identifies loans approaching or past SLA targets."""

    def test_fetch_sla_alerts_critical_severity(self):
        """Loan over 2x SLA target should be marked critical."""
        from routes.scheduler.today_summary import _fetch_sla_alerts

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        # APPLICATION stage has SLA target of 3 days; 10 days in stage => 7 days over => critical (7 >= 3)
        loan = MockLoan(
            id=1,
            loan_number="LN-001",
            borrower_name="Bob",
            stage="APPLICATION",
            loan_officer_id=10,
            stage_changed_at=now - timedelta(days=10),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([loan])
        mock_db.query.return_value = mock_query

        result = _fetch_sla_alerts(mock_db, user_id=10, org_id=1, now=now)

        assert result.total >= 1
        alert = result.items[0]
        assert alert.loan_id == 1
        assert alert.stage == "APPLICATION"
        assert alert.days_in_stage == 10
        assert alert.sla_target_days == 3
        assert alert.days_over_sla == 7
        assert alert.severity == "critical"

    def test_fetch_sla_alerts_skips_no_sla_stage(self):
        """Stages without an SLA target defined should be skipped."""
        from routes.scheduler.today_summary import _fetch_sla_alerts

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        # PROCESSING has no SLA target in _STAGE_SLA_DAYS
        loan = MockLoan(
            id=2,
            stage="PROCESSING",
            stage_changed_at=now - timedelta(days=20),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([loan])
        mock_db.query.return_value = mock_query

        result = _fetch_sla_alerts(mock_db, user_id=10, org_id=1, now=now)

        assert result.total == 0

    def test_fetch_sla_alerts_warning_severity(self):
        """Loan just over SLA target but less than 2x should be warning."""
        from routes.scheduler.today_summary import _fetch_sla_alerts

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        # APPLICATION SLA target is 3 days; 4 days in stage => 1 day over => warning (1 < 3)
        loan = MockLoan(
            id=3,
            loan_number="LN-003",
            borrower_name="Carol",
            stage="APPLICATION",
            loan_officer_id=10,
            stage_changed_at=now - timedelta(days=4),
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([loan])
        mock_db.query.return_value = mock_query

        result = _fetch_sla_alerts(mock_db, user_id=10, org_id=1, now=now)

        assert result.total == 1
        alert = result.items[0]
        assert alert.severity == "warning"
        assert alert.days_over_sla == 1


# =============================================================================
# 8. LEADS NEEDING FOLLOW-UP
# =============================================================================

class TestLeadsFollowUp:
    """Leads section surfaces stale leads needing follow-up."""

    def test_fetch_leads_with_no_contact(self):
        """Leads with last_contact=None should be included."""
        from routes.scheduler.today_summary import _fetch_leads_needing_followup

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        lead = MockLead(id=1, name="No Contact Lead", last_contact=None)

        mock_db = MagicMock()
        mock_query = _make_mock_query([lead])
        mock_db.query.return_value = mock_query

        result = _fetch_leads_needing_followup(mock_db, user_id=10, org_id=1, now=now)

        assert result.need_follow_up == 1
        assert result.items[0].days_since_contact is None

    def test_fetch_leads_calculates_days_since_contact(self):
        """days_since_contact should be the number of days since last_contact."""
        from routes.scheduler.today_summary import _fetch_leads_needing_followup

        now = datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)

        lead = MockLead(
            id=2,
            name="Stale Lead",
            last_contact=datetime(2026, 3, 18, 10, 0, 0),  # 5 days ago
        )

        mock_db = MagicMock()
        mock_query = _make_mock_query([lead])
        mock_db.query.return_value = mock_query

        result = _fetch_leads_needing_followup(mock_db, user_id=10, org_id=1, now=now)

        assert result.need_follow_up == 1
        assert result.items[0].days_since_contact == 5


# =============================================================================
# 9. MODELS NOT AVAILABLE — 503
# =============================================================================

class TestModelsUnavailable:
    """When scheduler models are not loaded, endpoint returns 503."""

    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_no_models_returns_503(self, mock_auth, mock_models):
        mock_auth.return_value = MockUser()
        mock_models.return_value = None

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 503


    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_empty_models_dict_returns_503(self, mock_auth, mock_models):
        """An empty dict is falsy, should also return 503."""
        mock_auth.return_value = MockUser()
        mock_models.return_value = {}

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 503


# =============================================================================
# 10. AUTH REQUIRED
# =============================================================================

class TestAuthRequired:
    """Unauthenticated requests should be rejected."""

    def test_no_auth_header_fails(self):
        client = _get_client()
        resp = client.get("/api/v1/scheduler/today-summary")
        # Could be 401, 403, or 500 depending on auth middleware behavior
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# 11. INTERNAL ERROR HANDLING
# =============================================================================

class TestInternalErrorHandling:
    """When a query helper raises, endpoint returns 500."""

    @patch(f"{_SUMMARY}._fetch_today_appointments", side_effect=RuntimeError("DB gone"))
    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_query_failure_returns_500(self, mock_auth, mock_models, mock_appts):
        mock_auth.return_value = MockUser()
        mock_models.return_value = {"Appointment": MagicMock()}

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 500


# =============================================================================
# 12. FULL RESPONSE INTEGRATION — all sections populated
# =============================================================================

class TestFullResponse:
    """Verify all four sections are present and populated in a single response."""

    @patch(f"{_SUMMARY}._fetch_sla_alerts")
    @patch(f"{_SUMMARY}._fetch_leads_needing_followup")
    @patch(f"{_SUMMARY}._fetch_today_tasks")
    @patch(f"{_SUMMARY}._fetch_today_appointments")
    @patch(f"{_SUMMARY}.get_models")
    @patch(f"{_SUMMARY}.get_current_user", new_callable=AsyncMock)
    def test_all_sections_present_and_populated(
        self, mock_auth, mock_models, mock_appts, mock_tasks, mock_leads, mock_sla
    ):
        user = MockUser()
        mock_auth.return_value = user
        mock_models.return_value = {"Appointment": MagicMock()}

        from routes.scheduler.today_summary import (
            AppointmentsSection, AppointmentSummaryItem,
            TasksSection, TaskSummaryItem,
            LeadsSection, LeadFollowUpItem,
            SLAAlertsSection, SLAAlertItem,
        )

        mock_appts.return_value = AppointmentsSection(
            count=1,
            next_appointment=AppointmentSummaryItem(id=1, title="Call", start_time="2026-03-23T15:00:00"),
            items=[AppointmentSummaryItem(id=1, title="Call", start_time="2026-03-23T15:00:00")],
        )
        mock_tasks.return_value = TasksSection(
            due_today=2,
            overdue=1,
            items=[
                TaskSummaryItem(id=1, title="Send docs", is_overdue=True),
                TaskSummaryItem(id=2, title="Review app"),
                TaskSummaryItem(id=3, title="Rate lock"),
            ],
        )
        mock_leads.return_value = LeadsSection(
            need_follow_up=1,
            items=[LeadFollowUpItem(id=10, name="Carol", days_since_contact=5)],
        )
        mock_sla.return_value = SLAAlertsSection(
            total=1,
            critical=1,
            items=[SLAAlertItem(
                loan_id=100,
                loan_number="LN-100",
                stage="APPLICATION",
                days_in_stage=10,
                sla_target_days=3,
                days_over_sla=7,
                severity="critical",
            )],
        )

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/today-summary",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()

        # Appointments
        assert data["appointments"]["count"] == 1
        assert data["appointments"]["next_appointment"]["title"] == "Call"

        # Tasks
        assert data["tasks"]["due_today"] == 2
        assert data["tasks"]["overdue"] == 1
        assert len(data["tasks"]["items"]) == 3

        # Leads
        assert data["leads"]["need_follow_up"] == 1
        assert data["leads"]["items"][0]["name"] == "Carol"

        # SLA Alerts
        assert data["sla_alerts"]["total"] == 1
        assert data["sla_alerts"]["critical"] == 1
        assert data["sla_alerts"]["items"][0]["severity"] == "critical"

        # Generated timestamp
        assert "generated_at" in data
