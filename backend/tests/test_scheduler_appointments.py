"""
Tests for the scheduler appointments CRUD endpoints.

Covers:
  - GET    /appointments                          List with filters
  - GET    /appointments/{id}                     Get single appointment detail
  - GET    /appointments/{id}/timeline            Appointment status history
  - POST   /appointments                          Create appointment
  - PUT    /appointments/{id}                     Update appointment
  - POST   /appointments/{id}/cancel              Cancel appointment

Uses an isolated SQLite in-memory DB with the same infrastructure pattern as
test_scheduler_public_booking_flow.py.  External services (email, SMS,
calendar sync, audit logger, creation service) are mocked.
"""

import pytest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass, field as dc_field
from typing import Any, Optional, List

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables before any app imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-appointments")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
import base64
_key_material = b"test-key-appointments-crud-test0"[:32].ljust(32, b"0")
os.environ.setdefault("DATA_ENCRYPTION_KEY", base64.urlsafe_b64encode(_key_material).decode())

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


# ---------------------------------------------------------------------------
# Import scheduler enums
# ---------------------------------------------------------------------------
from smart_scheduler_models import (
    AppointmentStatus,
    MeetingType,
    MeetingMode,
    DEFAULT_WORKING_HOURS,
    create_smart_scheduler_models,
)


# ---------------------------------------------------------------------------
# Import real ORM models
# ---------------------------------------------------------------------------
from database.models import Organization, User, Lead, Loan
from database.models.communication import Activity
from database.models.task import Task


# ---------------------------------------------------------------------------
# Create scheduler models and tables
# ---------------------------------------------------------------------------
_scheduler_models = create_smart_scheduler_models()

SchedulerConfig = _scheduler_models["SchedulerConfig"]
AvailabilitySlot = _scheduler_models["AvailabilitySlot"]
AppointmentType = _scheduler_models["AppointmentType"]
Appointment = _scheduler_models["Appointment"]
BlockedTime = _scheduler_models["BlockedTime"]
BookingLink = _scheduler_models["BookingLink"]
SchedulerAuditLog = _scheduler_models["SchedulerAuditLog"]
AppointmentStatusHistory = _scheduler_models["AppointmentStatusHistory"]

from db import Base as _ProdBase
for _table in _ProdBase.metadata.tables.values():
    try:
        _table.create(bind=_test_engine, checkfirst=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Models dict
# ---------------------------------------------------------------------------
_models_dict = {
    "SchedulerConfig": SchedulerConfig,
    "AvailabilitySlot": AvailabilitySlot,
    "AppointmentType": AppointmentType,
    "Appointment": Appointment,
    "BlockedTime": BlockedTime,
    "BookingLink": BookingLink,
    "SchedulerAuditLog": SchedulerAuditLog,
    "AppointmentStatusHistory": AppointmentStatusHistory,
    "User": User,
    "Lead": Lead,
    "Activity": Activity,
    "Task": Task,
}


# ---------------------------------------------------------------------------
# Mock users for auth
# ---------------------------------------------------------------------------
class MockUser:
    def __init__(self, id=1, organization_id=1, role="admin"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = role
        self.role = role
        self.first_name = "Test"
        self.last_name = "LO"
        self.email = "lo@test.com"
        self.full_name = "Test LO"


class MockNonAdminUser:
    def __init__(self, id=2, organization_id=1, role="loan_officer"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = role
        self.role = role
        self.first_name = "Other"
        self.last_name = "LO"
        self.email = "other@test.com"
        self.full_name = "Other LO"


class MockOtherOrgUser:
    def __init__(self, id=99, organization_id=99, role="admin"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = role
        self.role = role
        self.first_name = "Foreign"
        self.last_name = "User"
        self.email = "foreign@other.com"
        self.full_name = "Foreign User"


# Current mock user — swappable per test via _set_mock_user()
_current_mock_user = MockUser()


def _set_mock_user(user):
    global _current_mock_user
    _current_mock_user = user


# ---------------------------------------------------------------------------
# Mock appointment creation service result
# ---------------------------------------------------------------------------
@dataclass
class MockCreationResult:
    success: bool = True
    appointment: Any = None
    appointment_id: Optional[int] = None
    lead_id: Optional[int] = None
    video_link: Optional[str] = None
    warnings: List[str] = dc_field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI app + TestClient wiring
# ---------------------------------------------------------------------------
def _build_app():
    """Build a minimal FastAPI app wired to the appointments routes."""
    from fastapi import FastAPI
    app = FastAPI()

    def override_get_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()

    from db import get_db as _prod_get_db
    app.dependency_overrides[_prod_get_db] = override_get_db

    async def mock_get_current_user(token=None, request=None, db=None):
        return _current_mock_user

    # Wire up sub-modules
    from routes.scheduler._helpers import set_dependencies as helpers_set_deps
    helpers_set_deps(override_get_db, mock_get_current_user, _models_dict)

    from routes.scheduler.appointments import router as appt_router
    prefix = "/api/v1/scheduler"
    app.include_router(appt_router, prefix=prefix)

    return app


# ---------------------------------------------------------------------------
# Patch external services globally
# ---------------------------------------------------------------------------
import routes.scheduler.constants  # noqa: E402, F401
import scheduler_email_service as _ses  # noqa: E402, F401
import services.notification_service as _ns  # noqa: E402, F401

_mock_audit = MagicMock()
_mock_audit.log_appointment_created = MagicMock()
_mock_audit.log_appointment_updated = MagicMock()
_mock_audit.log_appointment_cancelled = MagicMock()
_mock_audit.log_appointment_rescheduled = MagicMock()
_mock_audit.log_no_show = MagicMock()
_mock_audit.write_audit_entry = MagicMock()

_patches = [
    patch("scheduler_email_service.send_appointment_confirmation_email", return_value={"success": True, "message_id": "mock-123"}),
    patch("scheduler_email_service.send_appointment_confirmation_sms", return_value={"success": True}),
    patch("scheduler_email_service.send_appointment_update_email", return_value={"success": True}),
    patch("scheduler_email_service.send_appointment_update_sms", return_value={"success": True}),
    patch("scheduler_email_service.send_appointment_cancellation_email", return_value={"success": True}),
    patch("scheduler_email_service.send_team_member_cancellation_email", return_value={"success": True}),
    patch("scheduler_email_service.send_team_member_notification_email", return_value={"success": True}),
    patch("scheduler_email_service.generate_reschedule_url", return_value="https://test.com/reschedule/1"),
    patch("services.notification_service.notification_service", new=MagicMock()),
    patch("routes.scheduler.appointments.scheduler_audit", _mock_audit),
    patch("routes.scheduler.appointments.get_appointment_audit_trail", return_value=[]),
    # Mock the _audit_log helper
    patch("routes.scheduler._audit._audit_log", return_value=None),
    patch("routes.scheduler.appointments._audit_log", return_value=None),
    # Mock CRM integration helpers
    patch("routes.scheduler.appointments._log_appointment_activity", return_value=None),
    patch("routes.scheduler.appointments._create_followup_task", return_value=None),
    # Mock _convert_utc_to_user_tz to return the datetime unchanged
    patch("routes.scheduler.appointments._convert_utc_to_user_tz", side_effect=lambda dt, *a, **kw: dt),
    # Mock _check_appointment_conflict — no-op by default (no conflict)
    patch("routes.scheduler.appointments._check_appointment_conflict", new_callable=AsyncMock),
    # Mock calendar outbound sync
    patch("services.calendar_outbound_sync.push_appointment_created", new_callable=AsyncMock),
    patch("services.calendar_outbound_sync.push_appointment_updated", new_callable=AsyncMock),
    patch("services.calendar_outbound_sync.push_appointment_cancelled", new_callable=AsyncMock),
]

for p in _patches:
    try:
        p.start()
    except Exception:
        pass  # Some patches may fail if the module path is not importable


from fastapi.testclient import TestClient  # noqa: E402

_app = _build_app()
_client = TestClient(_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _future_dt(days_ahead=7, hour=10):
    """Return a naive datetime in the near future."""
    now = datetime.utcnow()
    target = now + timedelta(days=days_ahead)
    return target.replace(hour=hour, minute=0, second=0, microsecond=0)


def _make_appointment(db, **overrides):
    """Insert an Appointment row directly and return it."""
    start = _future_dt()
    defaults = {
        "organization_id": 1,
        "assigned_user_id": 1,
        "created_by_user_id": 1,
        "title": "Test Appointment",
        "scheduled_start": start,
        "scheduled_end": start + timedelta(minutes=30),
        "duration_minutes": 30,
        "status": AppointmentStatus.BOOKED,
        "attendee_name": "Jane Doe",
        "attendee_email": "jane@example.com",
        "meeting_type": MeetingType.DISCOVERY_CALL,
        "meeting_mode": MeetingMode.VIDEO,
        "timezone": "America/Chicago",
    }
    defaults.update(overrides)
    appt = Appointment(**defaults)
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate scheduler tables between tests for isolation."""
    _set_mock_user(MockUser())  # Reset to admin user
    db = _TestSession()
    try:
        for model in [
            AppointmentStatusHistory, Appointment, BookingLink, BlockedTime,
            AvailabilitySlot, AppointmentType, SchedulerConfig,
            SchedulerAuditLog, Activity, Task, Lead,
        ]:
            try:
                db.query(model).delete()
            except Exception:
                db.rollback()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def db():
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return _client


@pytest.fixture
def org(db):
    existing = db.query(Organization).filter(Organization.id == 1).first()
    if not existing:
        db.add(Organization(id=1, name="Test Mortgage Co"))
        db.commit()
    return 1


@pytest.fixture
def user(db, org):
    existing = db.query(User).filter(User.id == 1).first()
    if not existing:
        db.add(User(
            id=1,
            organization_id=org,
            email="lo@test.com",
            hashed_password="$2b$12$test_hashed_password_for_testing",
            first_name="Test",
            last_name="LO",
            role="admin",
            permission_role="admin",
            is_active=True,
        ))
        db.commit()
    return 1


@pytest.fixture
def second_user(db, org):
    """A non-admin user in the same org."""
    existing = db.query(User).filter(User.id == 2).first()
    if not existing:
        db.add(User(
            id=2,
            organization_id=org,
            email="other@test.com",
            hashed_password="$2b$12$test_hashed_password_for_testing",
            first_name="Other",
            last_name="LO",
            role="loan_officer",
            permission_role="loan_officer",
            is_active=True,
        ))
        db.commit()
    return 2


@pytest.fixture
def sample_appointment(db, org, user):
    """A single booked appointment owned by user 1."""
    return _make_appointment(db)


@pytest.fixture
def multiple_appointments(db, org, user):
    """Create several appointments with different statuses and dates."""
    now = datetime.utcnow()
    appts = []

    # Booked for next week
    appts.append(_make_appointment(db, title="Booked Appt", status=AppointmentStatus.BOOKED,
                                   scheduled_start=now + timedelta(days=7)))

    # Confirmed for next week
    start2 = now + timedelta(days=8)
    appts.append(_make_appointment(db, title="Confirmed Appt", status=AppointmentStatus.CONFIRMED,
                                   scheduled_start=start2,
                                   scheduled_end=start2 + timedelta(minutes=30)))

    # Cancelled last week
    start3 = now - timedelta(days=3)
    appts.append(_make_appointment(db, title="Cancelled Appt", status=AppointmentStatus.CANCELLED,
                                   scheduled_start=start3,
                                   scheduled_end=start3 + timedelta(minutes=30)))

    # Completed yesterday
    start4 = now - timedelta(days=1)
    appts.append(_make_appointment(db, title="Completed Appt", status=AppointmentStatus.COMPLETED,
                                   scheduled_start=start4,
                                   scheduled_end=start4 + timedelta(minutes=30)))

    return appts


# ===========================================================================
# TESTS — LIST APPOINTMENTS
# ===========================================================================

class TestListAppointments:
    """GET /api/v1/scheduler/appointments"""

    def test_list_appointments_empty(self, client, org, user):
        """Returns empty list when no appointments exist."""
        resp = client.get("/api/v1/scheduler/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["appointments"] == []
        assert data["total"] == 0

    def test_list_appointments_returns_all(self, client, multiple_appointments):
        """Returns all appointments for the admin user."""
        resp = client.get("/api/v1/scheduler/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert len(data["appointments"]) == 4

    def test_list_appointments_filter_by_status(self, client, multiple_appointments):
        """Filters appointments by status query param."""
        resp = client.get("/api/v1/scheduler/appointments", params={"status": "booked"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["status"] == "booked" for a in data["appointments"])
        assert data["total"] >= 1

    def test_list_appointments_invalid_status_returns_400(self, client, org, user):
        """Invalid status filter returns 400."""
        resp = client.get("/api/v1/scheduler/appointments", params={"status": "nonexistent"})
        assert resp.status_code == 400

    def test_list_appointments_filter_by_date_range(self, client, multiple_appointments):
        """Filters appointments by start_date and end_date."""
        future_date = (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d")
        far_future = (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d")
        resp = client.get("/api/v1/scheduler/appointments",
                          params={"start_date": future_date, "end_date": far_future})
        assert resp.status_code == 200
        data = resp.json()
        # Only future appointments should be included
        for appt in data["appointments"]:
            assert appt["status"] in ("booked", "confirmed")

    def test_list_appointments_pagination(self, client, multiple_appointments):
        """Pagination with limit and offset works."""
        resp = client.get("/api/v1/scheduler/appointments", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["appointments"]) == 2
        assert data["total"] == 4
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_list_appointments_non_admin_sees_own_only(self, client, db, org, user, second_user):
        """Non-admin user only sees appointments assigned to or created by them."""
        # Create appointment owned by user 1
        _make_appointment(db, title="User1 Appt", assigned_user_id=1, created_by_user_id=1)
        # Create appointment owned by user 2
        _make_appointment(db, title="User2 Appt", assigned_user_id=2, created_by_user_id=2)

        _set_mock_user(MockNonAdminUser())
        resp = client.get("/api/v1/scheduler/appointments")
        assert resp.status_code == 200
        data = resp.json()
        # Non-admin user 2 should only see their own appointment
        for appt in data["appointments"]:
            assert "User2" in appt["title"]


# ===========================================================================
# TESTS — GET APPOINTMENT DETAIL
# ===========================================================================

class TestGetAppointment:
    """GET /api/v1/scheduler/appointments/{id}"""

    def test_get_appointment_success(self, client, sample_appointment):
        """Retrieves full appointment detail by ID."""
        appt_id = sample_appointment.id
        resp = client.get(f"/api/v1/scheduler/appointments/{appt_id}")
        assert resp.status_code == 200
        data = resp.json()
        appt = data["appointment"]
        assert appt["id"] == appt_id
        assert appt["title"] == "Test Appointment"
        assert appt["attendee_name"] == "Jane Doe"
        assert appt["attendee_email"] == "jane@example.com"
        assert appt["status"] == "booked"
        assert appt["meeting_type"] == "discovery_call"

    def test_get_appointment_not_found(self, client, org, user):
        """Returns 404 for nonexistent appointment ID."""
        resp = client.get("/api/v1/scheduler/appointments/999999")
        assert resp.status_code == 404

    def test_get_appointment_other_org_returns_404(self, client, db, org, user):
        """Appointment from a different org is not visible (tenant isolation)."""
        appt = _make_appointment(db, organization_id=99, assigned_user_id=1)
        resp = client.get(f"/api/v1/scheduler/appointments/{appt.id}")
        assert resp.status_code == 404

    def test_get_appointment_non_admin_cannot_see_others(self, client, db, org, user, second_user):
        """Non-admin cannot view appointment assigned to another user."""
        appt = _make_appointment(db, assigned_user_id=1, created_by_user_id=1)
        _set_mock_user(MockNonAdminUser())
        resp = client.get(f"/api/v1/scheduler/appointments/{appt.id}")
        assert resp.status_code == 404


# ===========================================================================
# TESTS — CREATE APPOINTMENT
# ===========================================================================

class TestCreateAppointment:
    """POST /api/v1/scheduler/appointments"""

    def _create_payload(self, **overrides):
        """Build a valid appointment creation payload."""
        start = _future_dt()
        defaults = {
            "title": "New Discovery Call",
            "scheduled_start": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "Bob Smith",
            "attendee_email": "bob@example.com",
            "meeting_type": "discovery_call",
            "meeting_mode": "video",
            "timezone": "America/Chicago",
        }
        defaults.update(overrides)
        return defaults

    def test_create_appointment_success(self, client, db, org, user):
        """Creates an appointment via the shared service and returns success."""
        payload = self._create_payload()
        start_dt = datetime.fromisoformat(payload["scheduled_start"])

        # Build a mock appointment object that the creation service would return
        mock_appt = MagicMock()
        mock_appt.id = 42
        mock_appt.title = payload["title"]
        mock_appt.scheduled_start = start_dt
        mock_appt.scheduled_end = start_dt + timedelta(minutes=30)
        mock_appt.duration_minutes = 30
        mock_appt.meeting_mode = MeetingMode.VIDEO
        mock_appt.video_link = None
        mock_appt.assigned_user_id = 1
        mock_appt.booked_by_ai = False

        mock_result = MockCreationResult(
            success=True,
            appointment=mock_appt,
            appointment_id=42,
            warnings=[],
        )

        with patch(
            "routes.scheduler.appointments.create_appointment_service",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_create:
            resp = client.post("/api/v1/scheduler/appointments", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Appointment created"
        assert data["appointment_id"] == 42

    def test_create_appointment_conflict_returns_409(self, client, db, org, user):
        """Returns 409 when the creation service reports a conflict."""
        payload = self._create_payload()

        mock_result = MockCreationResult(
            success=False,
            error="Time slot already booked by another appointment",
        )

        with patch(
            "routes.scheduler.appointments.create_appointment_service",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post("/api/v1/scheduler/appointments", json=payload)

        assert resp.status_code == 409

    def test_create_appointment_missing_title_returns_422(self, client, org, user):
        """Validation error for missing required field."""
        payload = self._create_payload()
        del payload["title"]
        resp = client.post("/api/v1/scheduler/appointments", json=payload)
        assert resp.status_code == 422

    def test_create_appointment_invalid_duration_returns_422(self, client, org, user):
        """Duration below minimum (5 min) returns validation error."""
        payload = self._create_payload(duration_minutes=2)
        resp = client.post("/api/v1/scheduler/appointments", json=payload)
        assert resp.status_code == 422


# ===========================================================================
# TESTS — UPDATE APPOINTMENT
# ===========================================================================

class TestUpdateAppointment:
    """PUT /api/v1/scheduler/appointments/{id}"""

    def test_update_appointment_title(self, client, sample_appointment):
        """Updates a simple field (title) on an appointment."""
        appt_id = sample_appointment.id
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt_id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_id"] == appt_id
        assert data["message"] == "Appointment updated"

    def test_update_appointment_status_confirmed(self, client, sample_appointment):
        """Transition from booked -> confirmed is allowed."""
        appt_id = sample_appointment.id
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt_id}",
            json={"status": "confirmed"},
        )
        assert resp.status_code == 200

    def test_update_appointment_cancel_via_put_blocked(self, client, sample_appointment):
        """Cannot cancel via PUT -- must use dedicated cancel endpoint."""
        appt_id = sample_appointment.id
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt_id}",
            json={"status": "cancelled"},
        )
        assert resp.status_code == 400

    def test_update_appointment_invalid_status_transition(self, client, db, org, user):
        """Invalid status transition returns 400 (e.g., booked -> completed)."""
        appt = _make_appointment(db, status=AppointmentStatus.BOOKED)
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"status": "completed"},
        )
        assert resp.status_code == 400

    def test_update_appointment_not_found(self, client, org, user):
        """Returns 404 for nonexistent appointment."""
        resp = client.put(
            "/api/v1/scheduler/appointments/999999",
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_update_appointment_forbidden_for_non_owner(self, client, db, org, user, second_user):
        """Non-admin user cannot update another user's appointment."""
        appt = _make_appointment(db, assigned_user_id=1, created_by_user_id=1)
        _set_mock_user(MockNonAdminUser())
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"title": "Hijacked"},
        )
        assert resp.status_code == 403

    def test_update_appointment_reschedule(self, client, sample_appointment):
        """Rescheduling sets is_reschedule=True and increments reschedule_count."""
        appt_id = sample_appointment.id
        new_start = _future_dt(days_ahead=14)
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt_id}",
            json={"scheduled_start": new_start.isoformat()},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_reschedule"] is True

    def test_update_appointment_invalid_meeting_mode(self, client, sample_appointment):
        """Invalid meeting_mode returns 400."""
        resp = client.put(
            f"/api/v1/scheduler/appointments/{sample_appointment.id}",
            json={"meeting_mode": "teleport"},
        )
        assert resp.status_code == 400


# ===========================================================================
# TESTS — CANCEL APPOINTMENT
# ===========================================================================

class TestCancelAppointment:
    """POST /api/v1/scheduler/appointments/{id}/cancel"""

    def test_cancel_appointment_success(self, client, sample_appointment):
        """Cancels a booked appointment."""
        appt_id = sample_appointment.id

        with patch("routes.scheduler.appointments.WaitlistService", side_effect=ImportError):
            resp = client.post(
                f"/api/v1/scheduler/appointments/{appt_id}/cancel",
                json={"reason": "Borrower requested reschedule"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Appointment cancelled"

    def test_cancel_appointment_not_found(self, client, org, user):
        """Returns 404 for nonexistent appointment."""
        resp = client.post(
            "/api/v1/scheduler/appointments/999999/cancel",
            json={"reason": "test"},
        )
        assert resp.status_code == 404

    def test_cancel_already_cancelled_returns_409(self, client, db, org, user):
        """Cannot cancel an already-cancelled appointment."""
        appt = _make_appointment(db, status=AppointmentStatus.CANCELLED)
        resp = client.post(
            f"/api/v1/scheduler/appointments/{appt.id}/cancel",
            json={"reason": "double cancel"},
        )
        assert resp.status_code == 409

    def test_cancel_completed_appointment_returns_409(self, client, db, org, user):
        """Cannot cancel a completed appointment."""
        appt = _make_appointment(db, status=AppointmentStatus.COMPLETED)
        resp = client.post(
            f"/api/v1/scheduler/appointments/{appt.id}/cancel",
        )
        assert resp.status_code == 409

    def test_cancel_appointment_forbidden_for_non_owner(self, client, db, org, user, second_user):
        """Non-admin user cannot cancel another user's appointment."""
        appt = _make_appointment(db, assigned_user_id=1, created_by_user_id=1)
        _set_mock_user(MockNonAdminUser())
        resp = client.post(
            f"/api/v1/scheduler/appointments/{appt.id}/cancel",
            json={"reason": "Not my appointment"},
        )
        assert resp.status_code == 404  # Filtered out by query — appears as 404


# ===========================================================================
# TESTS — APPOINTMENT TIMELINE
# ===========================================================================

class TestAppointmentTimeline:
    """GET /api/v1/scheduler/appointments/{id}/timeline"""

    def test_timeline_synthetic_for_new_appointment(self, client, sample_appointment):
        """Returns synthetic timeline entries when no status history rows exist."""
        appt_id = sample_appointment.id
        resp = client.get(f"/api/v1/scheduler/appointments/{appt_id}/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_id"] == appt_id
        assert data["current_status"] == "booked"
        assert "standard_progression" in data
        assert isinstance(data["history"], list)
        # Synthetic timeline should have at least the initial "booked" entry
        assert len(data["history"]) >= 1
        assert data["history"][0]["new_status"] == "booked"
        # Appointment summary should be present
        assert data["appointment_summary"]["title"] == "Test Appointment"
        assert data["appointment_summary"]["attendee_name"] == "Jane Doe"

    def test_timeline_not_found(self, client, org, user):
        """Returns 404 for nonexistent appointment."""
        resp = client.get("/api/v1/scheduler/appointments/999999/timeline")
        assert resp.status_code == 404

    def test_timeline_non_admin_cannot_see_others(self, client, db, org, user, second_user):
        """Non-admin user cannot view timeline for another user's appointment."""
        appt = _make_appointment(db, assigned_user_id=1, created_by_user_id=1)
        _set_mock_user(MockNonAdminUser())
        resp = client.get(f"/api/v1/scheduler/appointments/{appt.id}/timeline")
        assert resp.status_code == 404
