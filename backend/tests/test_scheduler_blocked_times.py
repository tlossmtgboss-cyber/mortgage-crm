"""
Tests for scheduler blocked times CRUD endpoints.

Covers:
  - POST   /blocked-times          Create a blocked time period
  - GET    /blocked-times          List blocked times with date range filters
  - DELETE /blocked-times/{id}     Soft-delete a blocked time period
  - Validation: end before start, applies_to_all_users permission gate
  - Blocked times affect availability (slots exclude blocked periods)

Uses an isolated SQLite in-memory DB with the same test infrastructure as
test_scheduler_public_booking_flow.py.  External services are mocked.
"""

import pytest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import patch, MagicMock

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables before any app imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-blocked-times")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
import base64
_key_material = b"test-key-blocked-times-testing-0"[:32].ljust(32, b"0")
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
# Import scheduler enums and model factory
# ---------------------------------------------------------------------------
from smart_scheduler_models import (
    AppointmentStatus,
    MeetingType,
    MeetingMode,
    RoutingStrategy,
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
# Mock users
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


_admin_user = MockUser(id=1, organization_id=1, role="admin")
_regular_user = MockUser(id=2, organization_id=1, role="loan_officer")


# ---------------------------------------------------------------------------
# FastAPI app + TestClient wiring
# ---------------------------------------------------------------------------
def _build_app(mock_user=None):
    """Build a minimal FastAPI app wired to the blocked times routes."""
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

    _active_user = mock_user or _admin_user

    async def mock_get_current_user(token=None, request=None, db=None):
        return _active_user

    from routes.scheduler._helpers import set_dependencies as helpers_set_deps
    helpers_set_deps(override_get_db, mock_get_current_user, _models_dict)

    from routes.scheduler.blocked_times import router as bt_router
    app.include_router(bt_router, prefix="/api/v1/scheduler")

    # Also wire up public booking for the availability integration test
    try:
        from routes.scheduler.public_booking import router as pb_router
        from routes.scheduler.public_booking import set_dependencies as pb_set_deps
        pb_set_deps(override_get_db, mock_get_current_user, _models_dict)
        app.include_router(pb_router, prefix="/api/v1/scheduler")
    except Exception:
        pass

    return app


# ---------------------------------------------------------------------------
# Patch external services globally
# ---------------------------------------------------------------------------
import routes.scheduler.constants  # noqa: E402, F401

_mock_patches = []
for mod_path in [
    "scheduler_email_service.send_appointment_confirmation_email",
    "scheduler_email_service.send_appointment_confirmation_sms",
    "scheduler_email_service.send_appointment_update_email",
    "scheduler_email_service.send_appointment_update_sms",
    "scheduler_email_service.send_appointment_cancellation_email",
    "scheduler_email_service.send_team_member_cancellation_email",
    "scheduler_email_service.send_team_member_notification_email",
    "scheduler_email_service.generate_reschedule_url",
]:
    p = patch(mod_path, return_value={"success": True, "message_id": "mock-bt-123"})
    _mock_patches.append(p)
    p.start()

_ns_patch = patch("services.notification_service.notification_service", new=MagicMock())
_ns_patch.start()
_mock_patches.append(_ns_patch)

_mg_patch = patch("services.microsoft_graph.create_event_via_graph", return_value=MagicMock(success=False, event_id=None))
_mg_patch.start()
_mock_patches.append(_mg_patch)


from fastapi.testclient import TestClient  # noqa: E402

_app = _build_app()
_client = TestClient(_app)

# Build a second app with a non-admin user for permission tests
_app_lo = _build_app(mock_user=_regular_user)
_client_lo = TestClient(_app_lo)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PREFIX = "/api/v1/scheduler"


def _future_monday(days_ahead=7):
    """Return a naive datetime for a future Monday at 10:00 AM."""
    now = datetime.utcnow()
    target = now + timedelta(days=days_ahead)
    while target.weekday() != 0:  # 0 = Monday
        target += timedelta(days=1)
    return target.replace(hour=10, minute=0, second=0, microsecond=0)


def _make_block_payload(
    title="Lunch Break",
    block_type="custom",
    start_dt=None,
    end_dt=None,
    all_day=False,
    is_recurring=False,
    recurrence_pattern=None,
    applies_to_all_users=False,
    description=None,
):
    """Build a blocked time creation payload."""
    if start_dt is None:
        start_dt = _future_monday()
    if end_dt is None:
        end_dt = start_dt + timedelta(hours=1)
    payload = {
        "title": title,
        "block_type": block_type,
        "start_datetime": start_dt.isoformat(),
        "end_datetime": end_dt.isoformat(),
        "all_day": all_day,
        "is_recurring": is_recurring,
        "applies_to_all_users": applies_to_all_users,
    }
    if recurrence_pattern is not None:
        payload["recurrence_pattern"] = recurrence_pattern
    if description is not None:
        payload["description"] = description
    return payload


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate scheduler tables between tests for isolation."""
    db = _TestSession()
    try:
        for model in [
            Appointment, BookingLink, BlockedTime, AvailabilitySlot,
            AppointmentType, SchedulerConfig, SchedulerAuditLog,
            Activity, Task, Lead,
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
def client_lo():
    """TestClient authenticated as a non-admin loan officer."""
    return _client_lo


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
def user_lo(db, org):
    """Create a non-admin loan officer user (id=2)."""
    existing = db.query(User).filter(User.id == 2).first()
    if not existing:
        db.add(User(
            id=2,
            organization_id=org,
            email="lo2@test.com",
            hashed_password="$2b$12$test_hashed_password_for_testing",
            first_name="Regular",
            last_name="LO",
            role="loan_officer",
            permission_role="loan_officer",
            is_active=True,
        ))
        db.commit()
    return 2


@pytest.fixture
def scheduler_config(db, org, user):
    config = SchedulerConfig(
        organization_id=org,
        user_id=user,
        config_name="Test Config",
        timezone="America/Chicago",
        default_duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        min_notice_hours=1,
        max_advance_days=60,
        max_meetings_per_day=8,
        working_hours=DEFAULT_WORKING_HOURS,
        is_active=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def appointment_type(db, org, scheduler_config):
    at = AppointmentType(
        organization_id=org,
        config_id=scheduler_config.id,
        type_key="discovery_call",
        type_name="Discovery Call",
        description="Initial consultation",
        meeting_type=MeetingType.DISCOVERY_CALL,
        default_duration_minutes=30,
        allowed_durations=[15, 30],
        is_public=True,
        is_active=True,
    )
    db.add(at)
    db.commit()
    db.refresh(at)
    return at


@pytest.fixture
def booking_link(db, org, user, appointment_type):
    link = BookingLink(
        organization_id=org,
        user_id=user,
        slug="blocked-time-test-link",
        link_name="Blocked Time Test Link",
        description="For blocked time integration testing",
        appointment_type_ids=[appointment_type.id],
        is_public=True,
        is_active=True,
        routing_strategy=RoutingStrategy.RELATIONSHIP,
        assigned_users=[user],
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# ============================================================================
# TEST: POST /blocked-times — Create blocked time
# ============================================================================

class TestCreateBlockedTime:
    """Tests for creating blocked time periods."""

    def test_create_lunch_break(self, client, org, user):
        """POST /blocked-times creates a lunch break successfully."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Lunch Break",
            block_type="custom",
            start_dt=start,
            end_dt=start + timedelta(hours=1),
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Blocked time created"
        assert "blocked_time_id" in data
        assert isinstance(data["blocked_time_id"], int)

    def test_create_ooo_all_day(self, client, org, user):
        """POST /blocked-times creates an all-day OOO block."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Out of Office - Vacation",
            block_type="pto",
            start_dt=start.replace(hour=0, minute=0),
            end_dt=start.replace(hour=23, minute=59),
            all_day=True,
            description="Family vacation day",
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Blocked time created"

    def test_create_recurring_block(self, client, org, user):
        """POST /blocked-times creates a recurring blocked time."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Weekly Team Meeting",
            block_type="meeting",
            start_dt=start.replace(hour=9, minute=0),
            end_dt=start.replace(hour=10, minute=0),
            is_recurring=True,
            recurrence_pattern={"frequency": "weekly", "days": ["monday"]},
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Blocked time created"

    def test_create_applies_to_all_users_as_admin(self, client, org, user):
        """Admin can create a block that applies to all users (company holiday)."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Company Holiday",
            block_type="holiday",
            start_dt=start.replace(hour=0, minute=0),
            end_dt=start.replace(hour=23, minute=59),
            all_day=True,
            applies_to_all_users=True,
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Blocked time created"

    def test_create_applies_to_all_users_as_non_admin_rejected(self, client_lo, org, user_lo):
        """Non-admin cannot create a block that applies to all users."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Unauthorized Holiday",
            start_dt=start,
            end_dt=start + timedelta(hours=8),
            applies_to_all_users=True,
        )
        resp = client_lo.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 403
        assert "Only admins" in resp.json()["detail"]


# ============================================================================
# TEST: Validation — end before start
# ============================================================================

class TestBlockedTimeValidation:
    """Tests for blocked time input validation."""

    def test_end_before_start_rejected(self, client, org, user):
        """end_datetime before start_datetime is rejected by Pydantic validator."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Invalid Block",
            start_dt=start,
            end_dt=start - timedelta(hours=1),
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 422

    def test_end_equals_start_rejected(self, client, org, user):
        """end_datetime equal to start_datetime is rejected (zero-duration)."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Zero Duration Block",
            start_dt=start,
            end_dt=start,  # same time
        )
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 422

    def test_empty_title_rejected(self, client, org, user):
        """Empty title is rejected by Pydantic min_length=1."""
        start = _future_monday()
        payload = _make_block_payload(title="", start_dt=start, end_dt=start + timedelta(hours=1))
        resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        assert resp.status_code == 422


# ============================================================================
# TEST: GET /blocked-times — List blocked times
# ============================================================================

class TestListBlockedTimes:
    """Tests for listing blocked time periods."""

    def test_list_empty(self, client, org, user):
        """GET /blocked-times returns empty list when no blocks exist."""
        resp = client.get(f"{PREFIX}/blocked-times")
        assert resp.status_code == 200
        data = resp.json()
        assert "blocked_times" in data
        assert len(data["blocked_times"]) == 0

    def test_list_returns_created_blocks(self, client, org, user):
        """GET /blocked-times returns blocks after creation."""
        start = _future_monday()
        # Create two blocks
        for title in ["Morning Block", "Afternoon Block"]:
            payload = _make_block_payload(
                title=title,
                start_dt=start,
                end_dt=start + timedelta(hours=1),
            )
            client.post(f"{PREFIX}/blocked-times", json=payload)
            start = start + timedelta(hours=3)

        resp = client.get(f"{PREFIX}/blocked-times")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["blocked_times"]) == 2
        titles = [b["title"] for b in data["blocked_times"]]
        assert "Morning Block" in titles
        assert "Afternoon Block" in titles

    def test_list_with_date_range_filter(self, client, org, user):
        """GET /blocked-times with start_date/end_date filters correctly."""
        monday = _future_monday(days_ahead=14)
        next_monday = monday + timedelta(days=7)

        # Block on first Monday
        payload1 = _make_block_payload(
            title="Week 1 Block",
            start_dt=monday,
            end_dt=monday + timedelta(hours=1),
        )
        client.post(f"{PREFIX}/blocked-times", json=payload1)

        # Block on second Monday
        payload2 = _make_block_payload(
            title="Week 2 Block",
            start_dt=next_monday,
            end_dt=next_monday + timedelta(hours=1),
        )
        client.post(f"{PREFIX}/blocked-times", json=payload2)

        # Filter to only first Monday's week
        resp = client.get(
            f"{PREFIX}/blocked-times",
            params={
                "start_date": monday.date().isoformat(),
                "end_date": (monday + timedelta(days=6)).date().isoformat(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["blocked_times"]) == 1
        assert data["blocked_times"][0]["title"] == "Week 1 Block"

    def test_list_includes_applies_to_all_blocks(self, client, org, user):
        """GET /blocked-times includes org-wide blocks (applies_to_all_users)."""
        start = _future_monday()

        # Create a personal block
        payload1 = _make_block_payload(
            title="Personal Block",
            start_dt=start,
            end_dt=start + timedelta(hours=1),
        )
        client.post(f"{PREFIX}/blocked-times", json=payload1)

        # Create an org-wide block (admin)
        payload2 = _make_block_payload(
            title="Company Holiday",
            start_dt=start + timedelta(hours=3),
            end_dt=start + timedelta(hours=11),
            applies_to_all_users=True,
        )
        client.post(f"{PREFIX}/blocked-times", json=payload2)

        resp = client.get(f"{PREFIX}/blocked-times")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["blocked_times"]) == 2

    def test_list_response_fields(self, client, org, user):
        """GET /blocked-times response contains all expected fields."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Focus Time",
            block_type="focus",
            start_dt=start,
            end_dt=start + timedelta(hours=2),
            description="Deep work block",
        )
        client.post(f"{PREFIX}/blocked-times", json=payload)

        resp = client.get(f"{PREFIX}/blocked-times")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["blocked_times"]) == 1

        block = data["blocked_times"][0]
        assert "id" in block
        assert block["title"] == "Focus Time"
        assert block["block_type"] == "focus"
        assert "start_datetime" in block
        assert "end_datetime" in block
        assert "all_day" in block
        assert "is_recurring" in block
        assert "recurrence_pattern" in block
        assert "applies_to_all_users" in block


# ============================================================================
# TEST: DELETE /blocked-times/{id} — Remove blocked time
# ============================================================================

class TestDeleteBlockedTime:
    """Tests for deleting (soft-delete) blocked time periods."""

    def test_delete_own_block(self, client, org, user):
        """DELETE /blocked-times/{id} soft-deletes the block."""
        start = _future_monday()
        payload = _make_block_payload(
            title="Temporary Block",
            start_dt=start,
            end_dt=start + timedelta(hours=1),
        )
        create_resp = client.post(f"{PREFIX}/blocked-times", json=payload)
        block_id = create_resp.json()["blocked_time_id"]

        # Delete it
        del_resp = client.delete(f"{PREFIX}/blocked-times/{block_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["message"] == "Blocked time deleted"

        # Verify it no longer appears in list (soft-deleted via is_active=False)
        list_resp = client.get(f"{PREFIX}/blocked-times")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["blocked_times"]) == 0

    def test_delete_nonexistent_block_returns_404(self, client, org, user):
        """DELETE /blocked-times/{id} returns 404 for non-existent block."""
        resp = client.delete(f"{PREFIX}/blocked-times/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_other_users_block_returns_404(self, client, db, org, user, user_lo):
        """Cannot delete a block owned by another user (returns 404)."""
        start = _future_monday()
        # Directly insert a block owned by user_lo (id=2) in the DB
        block = BlockedTime(
            organization_id=org,
            user_id=user_lo,
            title="Other User Block",
            block_type="custom",
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            is_active=True,
            created_by_id=user_lo,
        )
        db.add(block)
        db.commit()
        db.refresh(block)

        # Admin client (user_id=1) tries to delete user_lo's (user_id=2) block
        # The endpoint filters by user_id == current_user.id, so this returns 404
        resp = client.delete(f"{PREFIX}/blocked-times/{block.id}")
        assert resp.status_code == 404


# ============================================================================
# TEST: Blocked times affect availability slot generation
# ============================================================================

class TestBlockedTimesAffectAvailability:
    """Verify that blocked times are excluded from available slot generation."""

    def test_blocked_period_removes_slots(self, db, org, user, scheduler_config):
        """Slots overlapping a blocked time period are excluded from generation."""
        from routes.scheduler._availability import _generate_available_slots

        monday = _future_monday(days_ahead=14)
        monday_date = monday.date()

        # Block 10:00-12:00 on that Monday
        block = BlockedTime(
            organization_id=org,
            user_id=user,
            title="Morning Block",
            block_type="custom",
            start_datetime=monday.replace(hour=10, minute=0),
            end_datetime=monday.replace(hour=12, minute=0),
            is_active=True,
            created_by_id=user,
        )
        db.add(block)
        db.commit()

        # Generate slots for that single day
        slots = _generate_available_slots(
            db=db,
            user_ids=[user],
            start_date=monday_date,
            end_date=monday_date,
            duration_minutes=30,
            org_id=org,
            check_cross_source=False,
        )

        # Verify no slot starts within the blocked period [10:00, 12:00)
        for slot in slots:
            slot_start = slot["start"] if isinstance(slot["start"], datetime) else datetime.fromisoformat(slot["start"])
            slot_end = slot["end"] if isinstance(slot["end"], datetime) else datetime.fromisoformat(slot["end"])
            # A slot that overlaps the blocked range [10:00, 12:00) should not appear
            block_start = monday.replace(hour=10, minute=0)
            block_end = monday.replace(hour=12, minute=0)
            overlaps = slot_start < block_end and slot_end > block_start
            assert not overlaps, (
                f"Slot {slot_start.isoformat()}-{slot_end.isoformat()} overlaps "
                f"blocked period {block_start.isoformat()}-{block_end.isoformat()}"
            )

    def test_all_day_block_removes_all_slots(self, db, org, user, scheduler_config):
        """An all-day block removes every slot for that day."""
        from routes.scheduler._availability import _generate_available_slots

        monday = _future_monday(days_ahead=14)
        monday_date = monday.date()

        # Block the entire day
        block = BlockedTime(
            organization_id=org,
            user_id=user,
            title="All Day PTO",
            block_type="pto",
            start_datetime=monday.replace(hour=0, minute=0),
            end_datetime=monday.replace(hour=23, minute=59),
            all_day=True,
            is_active=True,
            created_by_id=user,
        )
        db.add(block)
        db.commit()

        slots = _generate_available_slots(
            db=db,
            user_ids=[user],
            start_date=monday_date,
            end_date=monday_date,
            duration_minutes=30,
            org_id=org,
            check_cross_source=False,
        )

        # Should have zero slots for that day since it is entirely blocked
        assert len(slots) == 0, f"Expected 0 slots on blocked day, got {len(slots)}"
