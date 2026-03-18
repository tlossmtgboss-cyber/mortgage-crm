"""
Scheduler AI Scheduling Route Tests

Tests for the AI scheduling route handlers in routes/scheduler/ai_scheduling.py.
Covers:
  - POST /ai-recommend-slots           AI-recommended time slots (auth required)
  - GET  /appointments/{id}/no-show-risk  No-show risk for one appointment (auth)
  - GET  /analytics/no-show-risks       Batch no-show risk for a date (auth)
  - Authentication required on all endpoints
  - 404 for non-existent appointments
  - Input validation
  - Empty results handling
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from datetime import datetime, date, time, timedelta, timezone
from fastapi.testclient import TestClient
from enum import Enum

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
    REVIEW = "review"


class MockAppointment:
    """Mock Appointment model instance."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.title = kwargs.get("title", "Test Consultation")
        self.attendee_name = kwargs.get("attendee_name", "John Doe")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 20, 14, 0))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 20, 14, 30))
        self.status = kwargs.get("status", MockAppointmentStatus.SCHEDULED)
        self.meeting_type = kwargs.get("meeting_type", MockMeetingType.CONSULTATION)
        self.lead_id = kwargs.get("lead_id", None)
        self.reschedule_count = kwargs.get("reschedule_count", 0)
        self.organization_id = kwargs.get("organization_id", 1)


@pytest.fixture
def auth_user():
    return MockUser()


@pytest.fixture
def mock_appointment():
    return MockAppointment()


# Shared patch targets
_AI = "routes.scheduler.ai_scheduling"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# POST /ai-recommend-slots — AI-recommended time slots
# =============================================================================

class TestAiRecommendSlots:
    """POST /api/v1/scheduler/ai-recommend-slots."""

    @patch(f"{_AI}._generate_available_slots")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_recommend_slots_success(self, mock_auth, mock_gen_slots, auth_user):
        mock_auth.return_value = auth_user
        mock_gen_slots.return_value = [
            {"start": "2026-03-20T10:00:00", "end": "2026-03-20T10:30:00", "day": "friday", "user_id": 10},
            {"start": "2026-03-20T14:00:00", "end": "2026-03-20T14:30:00", "day": "friday", "user_id": 10},
            {"start": "2026-03-21T09:00:00", "end": "2026-03-21T09:30:00", "day": "saturday", "user_id": 10},
        ]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/ai-recommend-slots",
            json={
                "start_date": "2026-03-20",
                "end_date": "2026-03-25",
                "duration_minutes": 30,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "total_available" in data
        assert data["total_available"] == 3
        # Each recommendation should have score and reasons
        for rec in data["recommendations"]:
            assert "slot" in rec
            assert "score" in rec
            assert "reasons" in rec

    @patch(f"{_AI}._generate_available_slots")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_recommend_slots_empty_results(self, mock_auth, mock_gen_slots, auth_user):
        mock_auth.return_value = auth_user
        mock_gen_slots.return_value = []

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/ai-recommend-slots",
            json={
                "start_date": "2026-03-20",
                "end_date": "2026-03-25",
                "duration_minutes": 30,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendations"] == []
        assert "No available slots" in data.get("message", "")

    @patch(f"{_AI}._generate_available_slots")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_recommend_slots_sorted_by_score(self, mock_auth, mock_gen_slots, auth_user):
        """Recommendations should be sorted by score descending."""
        mock_auth.return_value = auth_user
        # Mid-morning slots should score higher than late afternoon
        mock_gen_slots.return_value = [
            {"start": "2026-03-20T17:00:00", "end": "2026-03-20T17:30:00", "day": "friday", "user_id": 10},
            {"start": "2026-03-20T10:00:00", "end": "2026-03-20T10:30:00", "day": "friday", "user_id": 10},
            {"start": "2026-03-21T10:00:00", "end": "2026-03-21T10:30:00", "day": "wednesday", "user_id": 10},
        ]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/ai-recommend-slots",
            json={
                "start_date": "2026-03-20",
                "end_date": "2026-03-25",
                "duration_minutes": 30,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        recs = data["recommendations"]
        # Verify descending score order
        scores = [r["score"] for r in recs]
        assert scores == sorted(scores, reverse=True)

    @patch(f"{_AI}._generate_available_slots")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_recommend_slots_max_five(self, mock_auth, mock_gen_slots, auth_user):
        """At most 5 recommendations should be returned."""
        mock_auth.return_value = auth_user
        # Generate 10 slots
        mock_gen_slots.return_value = [
            {"start": f"2026-03-{20+i}T10:00:00", "end": f"2026-03-{20+i}T10:30:00", "day": "tuesday", "user_id": 10}
            for i in range(10)
        ]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/ai-recommend-slots",
            json={
                "start_date": "2026-03-20",
                "end_date": "2026-03-30",
                "duration_minutes": 30,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recommendations"]) <= 5

    def test_recommend_slots_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/ai-recommend-slots",
            json={
                "start_date": "2026-03-20",
                "end_date": "2026-03-25",
                "duration_minutes": 30,
            },
        )
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /appointments/{id}/no-show-risk — single appointment risk
# =============================================================================

class TestGetNoShowRisk:
    """GET /api/v1/scheduler/appointments/{id}/no-show-risk."""

    @patch(f"{_AI}._calculate_no_show_risk")
    @patch(f"{_AI}.get_models")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_no_show_risk_success(self, mock_auth, mock_models, mock_calc, auth_user, mock_appointment):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_appointment
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}
        mock_calc.return_value = {
            "score": 35,
            "risk_level": "medium",
            "factors": [{"factor": "baseline", "impact": 20}],
        }

        with patch(f"{_AI}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/appointments/1/no-show-risk",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_id"] == 1
        assert data["score"] == 35
        assert data["risk_level"] == "medium"
        assert "factors" in data

    @patch(f"{_AI}.get_models")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_no_show_risk_appointment_not_found(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_AI}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/appointments/999/no-show-risk",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 404

    @patch(f"{_AI}.get_models")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_no_show_risk_models_not_initialized(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user
        mock_models.return_value = None

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/appointments/1/no-show-risk",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 500

    def test_no_show_risk_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/appointments/1/no-show-risk")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /analytics/no-show-risks — batch no-show risk for a date
# =============================================================================

class TestBatchNoShowRisks:
    """GET /api/v1/scheduler/analytics/no-show-risks."""

    @patch(f"{_AI}._calculate_no_show_risk")
    @patch(f"{_AI}.get_models")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_batch_risks_success(self, mock_auth, mock_models, mock_calc, auth_user):
        mock_auth.return_value = auth_user

        appt1 = MockAppointment(id=1, title="Morning Call", attendee_name="Alice")
        appt2 = MockAppointment(id=2, title="Afternoon Review", attendee_name="Bob")

        MockApptModel = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [appt1, appt2]
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        # Return different risks for each appointment
        mock_calc.side_effect = [
            {"score": 60, "risk_level": "high", "factors": []},
            {"score": 15, "risk_level": "low", "factors": []},
        ]

        with patch(f"{_AI}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/no-show-risks?date=2026-03-20",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_appointments"] == 2
        assert data["risk_summary"]["high"] == 1
        assert data["risk_summary"]["low"] == 1
        assert data["date"] == "2026-03-20"
        # Results should be sorted by score descending
        assert data["appointments"][0]["score"] >= data["appointments"][1]["score"]

    @patch(f"{_AI}.get_models")
    @patch(f"{_AI}.get_current_user", new_callable=AsyncMock)
    def test_batch_risks_no_appointments(self, mock_auth, mock_models, auth_user):
        mock_auth.return_value = auth_user

        MockApptModel = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        mock_models.return_value = {"Appointment": MockApptModel}

        with patch(f"{_AI}.get_db", return_value=mock_db):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/analytics/no-show-risks?date=2026-03-20",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_appointments"] == 0
        assert data["avg_risk_score"] == 0

    def test_batch_risks_missing_date_param(self):
        """Missing required 'date' query param should return 422."""
        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/analytics/no-show-risks",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_batch_risks_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/analytics/no-show-risks?date=2026-03-20")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# _calculate_no_show_risk — internal helper unit tests
# =============================================================================

class TestCalculateNoShowRisk:
    """Unit tests for the _calculate_no_show_risk helper function."""

    def test_baseline_score(self):
        """A fresh appointment with no signals should get baseline score."""
        from routes.scheduler.ai_scheduling import _calculate_no_show_risk

        appt = MockAppointment(
            lead_id=None,
            attendee_email=None,
            scheduled_start=datetime.now() + timedelta(days=3),
            reschedule_count=0,
        )
        db = MagicMock()
        Appointment = MagicMock()

        result = _calculate_no_show_risk(appt, db, Appointment, MockAppointmentStatus, 1)
        assert "score" in result
        assert "risk_level" in result
        assert "factors" in result
        assert 0 <= result["score"] <= 100

    def test_multiple_reschedules_increase_risk(self):
        """Multiple reschedules should increase the risk score."""
        from routes.scheduler.ai_scheduling import _calculate_no_show_risk

        appt = MockAppointment(
            lead_id=None,
            attendee_email=None,
            scheduled_start=datetime.now() + timedelta(days=3),
            reschedule_count=3,
        )
        db = MagicMock()
        Appointment = MagicMock()

        result = _calculate_no_show_risk(appt, db, Appointment, MockAppointmentStatus, 1)
        # Multiple reschedules add +15
        assert result["score"] >= 35
        factors = [f["factor"] for f in result["factors"]]
        assert "multiple_reschedules" in factors

    def test_score_clamped_to_range(self):
        """Score should always be between 0 and 100."""
        from routes.scheduler.ai_scheduling import _calculate_no_show_risk

        # Create conditions that would push score very high
        appt = MockAppointment(
            lead_id=None,
            attendee_email=None,
            scheduled_start=datetime.now() + timedelta(days=14),
            reschedule_count=10,
        )
        db = MagicMock()
        Appointment = MagicMock()

        result = _calculate_no_show_risk(appt, db, Appointment, MockAppointmentStatus, 1)
        assert 0 <= result["score"] <= 100
