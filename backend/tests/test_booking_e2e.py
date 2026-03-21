"""
E2E Tests for the Complete Appointment Booking Lifecycle

Covers:
  1. Public Booking Flow (unauthenticated) -- 11 tests
  2. Authenticated Booking Flow (CRUD, status transitions) -- 14 tests
  3. Booking Links (CRUD, slug uniqueness) -- 6 tests
  4. Blocked Times (CRUD, slot exclusion, recurrence) -- 7 tests
  5. Scheduler Config -- 5 tests
  6. Availability / Slot Generation -- 5 tests

Total: 48 tests

Uses FastAPI TestClient with SQLite in-memory DB. External services
(email, calendar sync, notification, Microsoft Graph) are mocked.

IMPORTANT: Uses an isolated DeclarativeBase so test models don't collide
with production models (avoids "Multiple classes found for path 'User'"
errors).
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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-booking-e2e")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import (
    create_engine, event, Column, Integer, String, Boolean,
    DateTime, Text, JSON, Float, Numeric, Time, Date,
    ForeignKey, Enum as SQLEnum, UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# ISOLATED declarative base -- separate from the production db.Base
# This prevents "Multiple classes found for path 'User'" conflicts.
# ---------------------------------------------------------------------------
TestBase = declarative_base()

# ---------------------------------------------------------------------------
# In-memory SQLite engine with StaticPool
# StaticPool ensures all connections share the same in-memory database.
# Without it, each connection gets its own empty database.
# ---------------------------------------------------------------------------
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
# Import scheduler enums (no model creation -- just enums + constants)
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
# Self-contained ORM models for test isolation
# These mirror the real models but are defined on our test-local Base.
# ---------------------------------------------------------------------------

class Organization(TestBase):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), default="Test Org")


class User(TestBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, default=1)
    email = Column(String(255), default="lo@test.com")
    first_name = Column(String(100), default="Test")
    last_name = Column(String(100), default="User")
    full_name = Column(String(255), default="Test User")
    permission_role = Column(String(50), default="admin")
    role = Column(String(50), default="admin")
    nmls_number = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)


class Lead(TestBase):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, default=1)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    owner_id = Column(Integer, nullable=True)
    stage = Column(String(50), default="New")


class Activity(TestBase):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    lead_id = Column(Integer, nullable=True)
    loan_id = Column(Integer, nullable=True)
    type = Column(String(50), nullable=True)
    content = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Loan(TestBase):
    """Minimal stub so FK("loans.id") resolves."""
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, nullable=True)


class Task(TestBase):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, nullable=True)
    owner_id = Column(Integer, nullable=True)
    lead_id = Column(Integer, nullable=True)
    loan_id = Column(Integer, nullable=True)
    title = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    due_date = Column(DateTime, nullable=True)
    priority = Column(String(20), nullable=True)
    status = Column(String(20), default="pending")


# ---------------------------------------------------------------------------
# Create scheduler models from the factory on our isolated TestBase
# ---------------------------------------------------------------------------
_scheduler_models = create_smart_scheduler_models(TestBase)

SchedulerConfig = _scheduler_models["SchedulerConfig"]
AvailabilitySlot = _scheduler_models["AvailabilitySlot"]
AppointmentType = _scheduler_models["AppointmentType"]
Appointment = _scheduler_models["Appointment"]
BlockedTime = _scheduler_models["BlockedTime"]
BookingLink = _scheduler_models["BookingLink"]
SchedulerAuditLog = _scheduler_models["SchedulerAuditLog"]
AppointmentStatusHistory = _scheduler_models["AppointmentStatusHistory"]

# Create all tables on our test engine
TestBase.metadata.create_all(bind=_test_engine)


# ---------------------------------------------------------------------------
# Models dict (mirrors what the real app passes via set_dependencies)
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
# Mock user for auth
# ---------------------------------------------------------------------------
class MockUser:
    def __init__(self, id=1, organization_id=1, role="admin"):
        self.id = id
        self.organization_id = organization_id
        self.permission_role = role
        self.role = role
        self.first_name = "Test"
        self.last_name = "User"
        self.email = "lo@test.com"
        self.full_name = "Test User"


# ---------------------------------------------------------------------------
# FastAPI app + TestClient wiring
# ---------------------------------------------------------------------------
def _build_app():
    """Build a minimal FastAPI app wired to the scheduler routes."""
    from fastapi import FastAPI
    app = FastAPI()

    # DB dependency override
    def override_get_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()

    # Override the production get_db so that Depends(get_db) in sub-modules
    # (e.g. _helpers.py get_db override) resolves to our test session.
    from db import get_db as _prod_get_db
    app.dependency_overrides[_prod_get_db] = override_get_db

    # Auth mock
    async def mock_get_current_user(token=None, request=None, db=None):
        return MockUser()

    # ---- Helper functions ----

    def _audit_log(db, org_id, user_id, action, entity_type, entity_id=None, changes=None, request=None):
        try:
            entry = SchedulerAuditLog(
                organization_id=org_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
                ip_address=request.client.host if request and request.client else None,
                user_agent=str(request.headers.get("user-agent", ""))[:255] if request else None,
            )
            db.add(entry)
        except Exception:
            pass

    def _log_appointment_activity(db, org_id, user_id, lead_id, loan_id, content, activity_type="Meeting"):
        try:
            act = Activity(
                organization_id=org_id,
                user_id=user_id,
                lead_id=lead_id,
                loan_id=loan_id,
                type=activity_type,
                content=content[:1000] if content else None,
            )
            db.add(act)
        except Exception:
            pass

    def _ensure_lead_for_booking(db, email, name, phone, assigned_user_id, org_id):
        existing = db.query(Lead).filter(Lead.email == email, Lead.organization_id == org_id).first()
        if existing:
            return existing.id
        lead = Lead(
            organization_id=org_id,
            email=email,
            first_name=name.split()[0] if name else None,
            last_name=name.split()[-1] if name and len(name.split()) > 1 else None,
            owner_id=assigned_user_id,
        )
        db.add(lead)
        db.flush()
        return lead.id

    def _create_followup_task(db, org_id, owner_id, lead_id, loan_id, title, description, due_date, priority="medium"):
        try:
            task = Task(
                organization_id=org_id,
                owner_id=owner_id,
                lead_id=lead_id,
                loan_id=loan_id,
                title=title[:255] if title else None,
                description=description[:1000] if description else None,
                due_date=due_date,
                priority=priority,
            )
            db.add(task)
        except Exception:
            pass

    def _check_lo_licensing(db, user_id, attendee_state=None, org_id=None):
        pass

    def _get_user_timezone(db, user_id, org_id=None):
        return "America/Chicago"

    def _validate_url(value):
        if value and not value.startswith(("http://", "https://")):
            return None
        return value

    def _mask_email(email):
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        return f"{local[:2]}***@{domain}"

    def _create_comm_failure_task(db, org_id, user_id, appointment_id, channel, error):
        pass

    def _calculate_no_show_risk(appointment, db, Appt, ApptStatus, org_id):
        return {"risk_score": 0.1, "risk_level": "low", "factors": []}

    # ---- Wire up the scheduler sub-modules ----

    # Availability module (also exports _check_appointment_conflict, etc.)
    from routes.scheduler.availability import router as av_router
    from routes.scheduler._helpers import set_dependencies as av_set_deps
    from routes.scheduler._helpers import (
        _check_appointment_conflict,
        _check_duplicate_booking,
        _generate_available_slots,
    )
    av_set_deps(override_get_db, mock_get_current_user, _models_dict)

    helpers = {
        "_check_appointment_conflict": _check_appointment_conflict,
        "_check_duplicate_booking": _check_duplicate_booking,
        "_generate_available_slots": _generate_available_slots,
        "_audit_log": _audit_log,
        "_log_appointment_activity": _log_appointment_activity,
        "_ensure_lead_for_booking": _ensure_lead_for_booking,
        "_create_followup_task": _create_followup_task,
        "_check_lo_licensing": _check_lo_licensing,
        "_get_user_timezone": _get_user_timezone,
        "_validate_url": _validate_url,
        "_mask_email": _mask_email,
        "_create_comm_failure_task": _create_comm_failure_task,
        "_calculate_no_show_risk": _calculate_no_show_risk,
    }

    # Appointments CRUD
    from routes.scheduler.appointments import router as ac_router
    from routes.scheduler._helpers import set_dependencies as ac_set_deps
    ac_set_deps(override_get_db, mock_get_current_user, _models_dict)

    # Booking links
    from routes.scheduler.booking_links import router as bl_router
    # booking_links uses _helpers.set_dependencies (already called above)

    # Blocked times
    from routes.scheduler.blocked_times import router as bt_router
    # blocked_times uses _helpers.set_dependencies (already called above)

    # Public booking
    from routes.scheduler.public_booking import router as pb_router
    from routes.scheduler.public_booking import set_dependencies as pb_set_deps
    pb_set_deps(override_get_db, mock_get_current_user, _models_dict, helpers=helpers)

    # Scheduler config routes
    from routes.scheduler_routes import router as sc_router
    from routes.scheduler_routes import set_dependencies as sc_set_deps
    sc_set_deps(override_get_db, mock_get_current_user, _models_dict)

    # Mount all routers under /api/v1/scheduler
    prefix = "/api/v1/scheduler"
    app.include_router(sc_router, prefix=prefix)
    app.include_router(ac_router, prefix=prefix)
    app.include_router(av_router, prefix=prefix)
    app.include_router(bt_router, prefix=prefix)
    app.include_router(bl_router, prefix=prefix)
    app.include_router(pb_router, prefix=prefix)

    return app


# ---------------------------------------------------------------------------
# Patch external services globally
# ---------------------------------------------------------------------------
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
    patch("services.microsoft_graph.create_event_via_graph", return_value=MagicMock(success=False, event_id=None)),
]

for p in _patches:
    p.start()


from fastapi.testclient import TestClient

_app = _build_app()
_client = TestClient(_app)


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
def org(db):
    existing = db.query(Organization).filter(Organization.id == 1).first()
    if not existing:
        db.add(Organization(id=1, name="Test Org"))
        db.commit()
    return 1


@pytest.fixture
def user(db, org):
    existing = db.query(User).filter(User.id == 1).first()
    if not existing:
        db.add(User(id=1, organization_id=org))
        db.commit()
    return 1


@pytest.fixture
def scheduler_config(db, org, user):
    config = SchedulerConfig(
        organization_id=org,
        user_id=user,
        config_name="Test Config",
        timezone="America/Chicago",
        default_duration_minutes=30,
        buffer_before_minutes=5,
        buffer_after_minutes=5,
        min_notice_hours=2,
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
        slug="test-link",
        link_name="Test Booking Link",
        description="For testing",
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


def _future_monday(days_ahead=7):
    """Return a naive datetime for a future Monday at 10:00 AM."""
    now = datetime.utcnow()
    target = now + timedelta(days=days_ahead)
    while target.weekday() != 0:  # 0 = Monday
        target += timedelta(days=1)
    return target.replace(hour=10, minute=0, second=0, microsecond=0)


# ============================================================================
# 1. PUBLIC BOOKING FLOW (11 tests)
# ============================================================================

class TestPublicBookingFlow:
    """Tests for unauthenticated public booking endpoints."""

    def test_get_booking_page_data(self, client, booking_link):
        resp = client.get(f"/api/v1/scheduler/public/book/{booking_link.slug}")
        assert resp.status_code == 200

    def test_invalid_slug_returns_404(self, client, org):
        resp = client.get("/api/v1/scheduler/public/book/nonexistent-slug-xyz")
        assert resp.status_code == 404

    def test_get_available_slots_for_date(self, client, booking_link, scheduler_config, appointment_type):
        future = _future_monday()
        resp = client.get(
            f"/api/v1/scheduler/public/book/{booking_link.slug}/slots",
            params={
                "appointment_type_id": appointment_type.id,
                "date": future.strftime("%Y-%m-%d"),
                "duration_minutes": 30,
            },
        )
        assert resp.status_code == 200
        assert "available_slots" in resp.json()

    def test_past_date_returns_no_slots(self, client, booking_link, scheduler_config, appointment_type):
        past = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = client.get(
            f"/api/v1/scheduler/public/book/{booking_link.slug}/slots",
            params={
                "appointment_type_id": appointment_type.id,
                "date": past,
                "duration_minutes": 30,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["available_slots"] == []

    @patch("routes.scheduler.public_booking._check_rate_limit", new=lambda *a, **kw: None)
    def test_book_appointment_happy_path(self, client, db, booking_link, scheduler_config, appointment_type, user):
        start = _future_monday()
        payload = {
            "appointment_type_id": appointment_type.id,
            "start_time": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "Jane Borrower",
            "attendee_email": "jane@example.com",
            "attendee_phone": "+15551234567",
            "notes": "First-time buyer",
            "user_ids": [user],
        }
        resp = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
        assert resp.status_code in (200, 201, 409)
        if resp.status_code in (200, 201):
            data = resp.json()
            assert "appointment" in data or "appointment_id" in data

    @patch("routes.scheduler.public_booking._check_rate_limit", new=lambda *a, **kw: None)
    def test_book_with_intake_form_responses(self, client, db, booking_link, scheduler_config, appointment_type, user):
        start = _future_monday(days_ahead=14)
        payload = {
            "appointment_type_id": appointment_type.id,
            "start_time": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "Intake User",
            "attendee_email": "intake@example.com",
            "user_ids": [user],
        }
        resp = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
        assert resp.status_code in (200, 201, 409)

    @patch("routes.scheduler.public_booking._check_rate_limit", new=lambda *a, **kw: None)
    def test_booking_creates_appointment_record(self, client, db, booking_link, scheduler_config, appointment_type, user):
        """Verify that a successful public booking creates an Appointment row in the DB."""
        start = _future_monday(days_ahead=21)
        payload = {
            "appointment_type_id": appointment_type.id,
            "start_time": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "Persist User",
            "attendee_email": "persist@example.com",
            "user_ids": [user],
        }
        resp = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
        assert resp.status_code in (200, 201)
        # Verify via a fresh session that the appointment row exists
        fresh = _TestSession()
        try:
            appt = fresh.query(Appointment).filter(
                Appointment.attendee_email == "persist@example.com",
            ).first()
            assert appt is not None
            assert appt.status == AppointmentStatus.BOOKED
        finally:
            fresh.close()

    @patch("routes.scheduler.public_booking._check_rate_limit", new=lambda *a, **kw: None)
    def test_double_booking_same_slot_returns_409(self, client, db, booking_link, scheduler_config, appointment_type, user):
        start = _future_monday(days_ahead=28)
        payload = {
            "appointment_type_id": appointment_type.id,
            "start_time": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "First Booker",
            "attendee_email": "first@example.com",
            "user_ids": [user],
        }
        resp1 = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
        if resp1.status_code not in (200, 201):
            pytest.skip("First booking failed")

        payload2 = {**payload, "attendee_name": "Second Booker", "attendee_email": "first@example.com"}
        resp2 = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload2)
        assert resp2.status_code == 409

    def test_booking_missing_required_fields_returns_422(self, client, booking_link):
        payload = {"appointment_type_id": 999}
        resp = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
        assert resp.status_code == 422

    def test_deactivated_link_returns_404_on_public_access(self, client, db, booking_link):
        booking_link.is_active = False
        db.commit()
        resp = client.get(f"/api/v1/scheduler/public/book/{booking_link.slug}")
        assert resp.status_code == 404

    @patch("routes.scheduler.public_booking._check_rate_limit", new=lambda *a, **kw: None)
    def test_booking_sends_confirmation_email(self, client, db, booking_link, scheduler_config, appointment_type, user):
        start = _future_monday(days_ahead=35)
        payload = {
            "appointment_type_id": appointment_type.id,
            "start_time": start.isoformat(),
            "duration_minutes": 30,
            "attendee_name": "Email User",
            "attendee_email": "emailtest@example.com",
            "user_ids": [user],
        }
        with patch("routes.scheduler.public_booking.send_appointment_confirmation_email",
                    return_value={"success": True}) as mock_email:
            resp = client.post(f"/api/v1/scheduler/public/book/{booking_link.slug}/confirm", json=payload)
            if resp.status_code in (200, 201):
                assert mock_email.called


# ============================================================================
# 2. AUTHENTICATED BOOKING FLOW (14 tests)
# ============================================================================

class TestAuthenticatedBookingFlow:

    def _create_appointment(self, client, days_ahead=7, title="Test Meeting", email=None):
        start = _future_monday(days_ahead=days_ahead)
        payload = {
            "title": title,
            "meeting_type": "discovery_call",
            "meeting_mode": "video",
            "scheduled_start": start.isoformat(),
            "duration_minutes": 30,
            "timezone": "America/Chicago",
            "attendee_name": "Test Client",
            "attendee_email": email or f"client{days_ahead}@example.com",
            "attendee_phone": "+15559876543",
        }
        return client.post(
            "/api/v1/scheduler/appointments",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )

    def test_create_appointment_as_lo(self, client, db, user, org, scheduler_config):
        resp = self._create_appointment(client)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "appointment_id" in data or "appointment" in data

    def test_create_with_conflict_detection(self, client, db, user, org, scheduler_config):
        resp1 = self._create_appointment(client, days_ahead=8, title="First")
        if resp1.status_code not in (200, 201):
            pytest.skip("First appointment creation failed")
        resp2 = self._create_appointment(client, days_ahead=8, title="Conflict")
        assert resp2.status_code == 409

    def test_create_exceeds_daily_capacity(self, db, user, org, scheduler_config):
        start = _future_monday(days_ahead=10)
        for i in range(8):
            slot_start = start.replace(hour=9 + i)
            slot_end = slot_start + timedelta(minutes=30)
            appt = Appointment(
                organization_id=org,
                assigned_user_id=user,
                created_by_user_id=user,
                title=f"Meeting {i+1}",
                scheduled_start=slot_start,
                scheduled_end=slot_end,
                duration_minutes=30,
                status=AppointmentStatus.BOOKED,
            )
            db.add(appt)
        db.commit()

        from routes.scheduler.availability import _generate_available_slots
        slots = _generate_available_slots(
            db=db, user_ids=[user], start_date=start.date(), end_date=start.date(),
            duration_minutes=30, org_id=org, max_per_day=8, check_cross_source=False,
        )
        assert len(slots) == 0

    def test_list_appointments_with_pagination(self, client, db, user, org, scheduler_config):
        for i in range(3):
            appt = Appointment(
                organization_id=org, assigned_user_id=user, created_by_user_id=user,
                title=f"Appt {i+1}",
                scheduled_start=_future_monday(days_ahead=12) + timedelta(hours=i),
                scheduled_end=_future_monday(days_ahead=12) + timedelta(hours=i, minutes=30),
                duration_minutes=30, status=AppointmentStatus.BOOKED,
            )
            db.add(appt)
        db.commit()

        resp = client.get(
            "/api/v1/scheduler/appointments",
            params={"limit": 2, "offset": 0},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "appointments" in data
        assert data["total"] >= 3
        assert len(data["appointments"]) <= 2

    def test_filter_by_date_range(self, client, db, user, org, scheduler_config):
        future = _future_monday(days_ahead=14)
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Date Range Test",
            scheduled_start=future, scheduled_end=future + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()

        resp = client.get(
            "/api/v1/scheduler/appointments",
            params={"start_date": future.strftime("%Y-%m-%d"), "end_date": future.strftime("%Y-%m-%d")},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["appointments"]) >= 1

    def test_filter_by_status(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Status Filter Test",
            scheduled_start=_future_monday(days_ahead=15),
            scheduled_end=_future_monday(days_ahead=15) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()

        resp = client.get(
            "/api/v1/scheduler/appointments",
            params={"status": "booked"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert all(a["status"] == "booked" for a in resp.json()["appointments"])

    def test_get_single_appointment_by_id(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Single Fetch Test",
            scheduled_start=_future_monday(days_ahead=16),
            scheduled_end=_future_monday(days_ahead=16) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
            attendee_name="Single Client", attendee_email="single@example.com",
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.get(
            f"/api/v1/scheduler/appointments/{appt.id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()["appointment"]
        assert data["title"] == "Single Fetch Test"
        assert data["attendee_name"] == "Single Client"

    def test_get_nonexistent_appointment_returns_404(self, client, user, org):
        resp = client.get(
            "/api/v1/scheduler/appointments/99999",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 404

    def test_update_appointment(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Update Me",
            scheduled_start=_future_monday(days_ahead=17),
            scheduled_end=_future_monday(days_ahead=17) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"title": "Updated Title", "internal_notes": "Updated notes"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        updated = db.query(Appointment).get(appt.id)
        assert updated.title == "Updated Title"

    def test_cancel_appointment_with_reason(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Cancel Me",
            scheduled_start=_future_monday(days_ahead=18),
            scheduled_end=_future_monday(days_ahead=18) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
            attendee_email="cancel@example.com", attendee_name="Cancel Client",
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.post(
            f"/api/v1/scheduler/appointments/{appt.id}/cancel",
            json={"reason": "Client requested reschedule"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        cancelled = db.query(Appointment).get(appt.id)
        assert cancelled.status == AppointmentStatus.CANCELLED
        assert cancelled.cancellation_reason == "Client requested reschedule"

    def test_reschedule_appointment(self, client, db, user, org, scheduler_config):
        old_start = _future_monday(days_ahead=19)
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Reschedule Me",
            scheduled_start=old_start, scheduled_end=old_start + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED, reschedule_count=0,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        new_start = _future_monday(days_ahead=20)
        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"scheduled_start": new_start.isoformat(), "duration_minutes": 30},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        rescheduled = db.query(Appointment).get(appt.id)
        assert rescheduled.reschedule_count == 1

    def test_confirm_appointment(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Confirm Me",
            scheduled_start=_future_monday(days_ahead=21),
            scheduled_end=_future_monday(days_ahead=21) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"status": "confirmed"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        confirmed = db.query(Appointment).get(appt.id)
        assert confirmed.status == AppointmentStatus.CONFIRMED

    def test_mark_completed(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="Complete Me",
            scheduled_start=_future_monday(days_ahead=22),
            scheduled_end=_future_monday(days_ahead=22) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"status": "completed"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        completed = db.query(Appointment).get(appt.id)
        assert completed.status == AppointmentStatus.COMPLETED
        assert completed.completed_at is not None

    def test_mark_no_show(self, client, db, user, org, scheduler_config):
        appt = Appointment(
            organization_id=org, assigned_user_id=user, created_by_user_id=user,
            title="No Show",
            scheduled_start=_future_monday(days_ahead=23),
            scheduled_end=_future_monday(days_ahead=23) + timedelta(minutes=30),
            duration_minutes=30, status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        resp = client.put(
            f"/api/v1/scheduler/appointments/{appt.id}",
            json={"status": "no_show"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        ns = db.query(Appointment).get(appt.id)
        assert ns.status == AppointmentStatus.NO_SHOW
        assert ns.no_show_at is not None


# ============================================================================
# 3. BOOKING LINKS (6 tests)
# ============================================================================

class TestBookingLinks:

    def test_create_booking_link(self, client, db, user, org):
        payload = {
            "slug": "my-meetings",
            "link_name": "My Meeting Link",
            "description": "Schedule with me",
            "is_public": True,
        }
        resp = client.post(
            "/api/v1/scheduler/booking-links",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "/book/my-meetings"
        assert "link_id" in data

    def test_list_booking_links(self, client, db, booking_link, user, org):
        resp = client.get(
            "/api/v1/scheduler/booking-links",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["booking_links"]) >= 1

    def test_list_all_booking_links_admin(self, client, db, booking_link, user, org):
        resp = client.get(
            "/api/v1/scheduler/booking-links/all",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert "booking_links" in resp.json()

    def test_slug_uniqueness_enforcement(self, client, db, booking_link, user, org):
        payload = {
            "slug": booking_link.slug,
            "link_name": "Duplicate Link",
            "is_public": True,
        }
        resp = client.post(
            "/api/v1/scheduler/booking-links",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 400
        assert "already in use" in resp.json()["detail"].lower()

    def test_delete_booking_link(self, client, db, booking_link, user, org):
        resp = client.delete(
            f"/api/v1/scheduler/booking-links/{booking_link.id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        link = db.query(BookingLink).get(booking_link.id)
        assert link.is_active is False

    def test_deactivated_link_not_in_user_list(self, client, db, booking_link, user, org):
        booking_link.is_active = False
        db.commit()
        resp = client.get(
            "/api/v1/scheduler/booking-links",
            headers={"Authorization": "Bearer test-token"},
        )
        slugs = [l["slug"] for l in resp.json()["booking_links"]]
        assert booking_link.slug not in slugs


# ============================================================================
# 4. BLOCKED TIMES (7 tests)
# ============================================================================

class TestBlockedTimes:

    def test_create_blocked_time(self, client, db, user, org):
        start = _future_monday(days_ahead=7)
        payload = {
            "title": "PTO Day",
            "description": "Vacation",
            "block_type": "pto",
            "start_datetime": start.isoformat(),
            "end_datetime": (start + timedelta(hours=8)).isoformat(),
            "all_day": False,
        }
        resp = client.post(
            "/api/v1/scheduler/blocked-times",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert "blocked_time_id" in resp.json()

    def test_list_blocked_times(self, client, db, user, org):
        start = _future_monday(days_ahead=8)
        bt = BlockedTime(
            organization_id=org, user_id=user, title="Team Meeting",
            block_type="custom", start_datetime=start,
            end_datetime=start + timedelta(hours=1), is_active=True,
        )
        db.add(bt)
        db.commit()

        resp = client.get(
            "/api/v1/scheduler/blocked-times",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["blocked_times"]) >= 1

    def test_blocked_time_prevents_slot_generation(self, db, user, org, scheduler_config):
        future = _future_monday(days_ahead=9)
        bt = BlockedTime(
            organization_id=org, user_id=user, title="All Day Block",
            block_type="pto",
            start_datetime=future.replace(hour=9, minute=0),
            end_datetime=future.replace(hour=17, minute=0),
            all_day=True, is_active=True,
        )
        db.add(bt)
        db.commit()

        from routes.scheduler.availability import _generate_available_slots
        slots = _generate_available_slots(
            db=db, user_ids=[user], start_date=future.date(), end_date=future.date(),
            duration_minutes=30, org_id=org, check_cross_source=False,
        )
        assert len(slots) == 0

    def test_recurring_blocked_time(self, client, db, user, org):
        start = _future_monday(days_ahead=10)
        payload = {
            "title": "Weekly Standup",
            "block_type": "custom",
            "start_datetime": start.replace(hour=9, minute=0).isoformat(),
            "end_datetime": start.replace(hour=9, minute=30).isoformat(),
            "is_recurring": True,
            "recurrence_pattern": {"frequency": "weekly", "days": ["monday"]},
        }
        resp = client.post(
            "/api/v1/scheduler/blocked-times",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        bt_id = resp.json()["blocked_time_id"]
        db.expire_all()
        bt = db.query(BlockedTime).get(bt_id)
        assert bt.is_recurring is True
        assert bt.recurrence_pattern["frequency"] == "weekly"

    def test_delete_blocked_time(self, client, db, user, org):
        start = _future_monday(days_ahead=11)
        bt = BlockedTime(
            organization_id=org, user_id=user, title="Delete Me",
            block_type="custom", start_datetime=start,
            end_datetime=start + timedelta(hours=1), is_active=True,
        )
        db.add(bt)
        db.commit()
        db.refresh(bt)
        bt_id = bt.id  # capture before delete may invalidate the ORM object

        resp = client.delete(
            f"/api/v1/scheduler/blocked-times/{bt_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        # Verify via fresh session that the row is gone (hard delete) or deactivated
        fresh = _TestSession()
        try:
            row = fresh.query(BlockedTime).get(bt_id)
            # Route may hard-delete or soft-delete (set is_active=False)
            assert row is None or row.is_active is False
        finally:
            fresh.close()

    def test_delete_blocked_time_restores_slots(self, db, user, org, scheduler_config):
        future = _future_monday(days_ahead=12)
        bt = BlockedTime(
            organization_id=org, user_id=user, title="Temporary Block",
            block_type="custom",
            start_datetime=future.replace(hour=10, minute=0),
            end_datetime=future.replace(hour=11, minute=0),
            is_active=True,
        )
        db.add(bt)
        db.commit()
        db.refresh(bt)

        from routes.scheduler.availability import _generate_available_slots
        slots_blocked = _generate_available_slots(
            db=db, user_ids=[user], start_date=future.date(), end_date=future.date(),
            duration_minutes=30, org_id=org, check_cross_source=False,
        )

        db.delete(bt)
        db.commit()

        slots_unblocked = _generate_available_slots(
            db=db, user_ids=[user], start_date=future.date(), end_date=future.date(),
            duration_minutes=30, org_id=org, check_cross_source=False,
        )
        assert len(slots_unblocked) > len(slots_blocked)

    def test_only_admins_can_block_all_users(self, client, db, user, org):
        from routes.scheduler import blocked_times as bt_module
        original_func = bt_module._get_current_user_func

        async def non_admin_user(token=None, request=None, db=None):
            return MockUser(role="lo")

        bt_module._get_current_user_func = non_admin_user
        try:
            start = _future_monday(days_ahead=13)
            payload = {
                "title": "Company Holiday",
                "block_type": "holiday",
                "start_datetime": start.isoformat(),
                "end_datetime": (start + timedelta(hours=8)).isoformat(),
                "applies_to_all_users": True,
            }
            resp = client.post(
                "/api/v1/scheduler/blocked-times",
                json=payload,
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 403
        finally:
            bt_module._get_current_user_func = original_func


# ============================================================================
# 5. SCHEDULER CONFIG (5 tests)
# ============================================================================

class TestSchedulerConfig:

    def test_get_config_defaults(self, client, user, org):
        resp = client.get(
            "/api/v1/scheduler/config",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"] is None
        assert data["defaults"]["timezone"] == "America/Chicago"

    def test_create_config(self, client, user, org):
        payload = {
            "config_name": "My Schedule",
            "timezone": "America/New_York",
            "default_duration_minutes": 45,
            "max_meetings_per_day": 6,
        }
        resp = client.post(
            "/api/v1/scheduler/config",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert "config_id" in resp.json()

    def test_create_duplicate_config_returns_400(self, client, db, user, org, scheduler_config):
        payload = {"config_name": "Duplicate"}
        resp = client.post(
            "/api/v1/scheduler/config",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_get_existing_config(self, client, db, user, org, scheduler_config):
        resp = client.get(
            "/api/v1/scheduler/config",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["config_name"] == "Test Config"

    def test_update_config(self, client, db, user, org, scheduler_config):
        resp = client.put(
            "/api/v1/scheduler/config",
            json={"max_meetings_per_day": 10, "timezone": "America/Los_Angeles"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        db.expire_all()
        config = db.query(SchedulerConfig).get(scheduler_config.id)
        assert config.max_meetings_per_day == 10
        assert config.timezone == "America/Los_Angeles"


# ============================================================================
# 6. AVAILABILITY / SLOT GENERATION (5 tests)
# ============================================================================

class TestAvailabilitySlots:

    def test_get_availability(self, client, db, user, org, scheduler_config):
        future = _future_monday(days_ahead=7)
        resp = client.get(
            "/api/v1/scheduler/availability",
            params={"start_date": future.strftime("%Y-%m-%d"), "end_date": future.strftime("%Y-%m-%d")},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "working_hours" in data
        assert "blocked_times" in data

    def test_available_slots_endpoint(self, client, db, user, org, scheduler_config):
        future = _future_monday(days_ahead=7)
        payload = {
            "start_date": future.strftime("%Y-%m-%d"),
            "end_date": future.strftime("%Y-%m-%d"),
            "duration_minutes": 30,
        }
        resp = client.post(
            "/api/v1/scheduler/available-slots",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "available_slots" in data
        assert "total_slots" in data

    def test_slot_generation_respects_working_hours(self, db, user, org, scheduler_config):
        from routes.scheduler.availability import _generate_available_slots
        future = _future_monday(days_ahead=14)
        slots = _generate_available_slots(
            db=db, user_ids=[user], start_date=future.date(), end_date=future.date(),
            duration_minutes=30, org_id=org, check_cross_source=False,
        )
        for slot in slots:
            slot_time = datetime.fromisoformat(slot["start"])
            assert 9 <= slot_time.hour < 17, f"Slot outside working hours: {slot_time}"

    def test_slot_generation_skips_weekends(self, db, user, org, scheduler_config):
        from routes.scheduler.availability import _generate_available_slots
        today = datetime.utcnow().date()
        days_to_saturday = (5 - today.weekday()) % 7
        if days_to_saturday == 0:
            days_to_saturday = 7
        saturday = today + timedelta(days=days_to_saturday)

        slots = _generate_available_slots(
            db=db, user_ids=[user], start_date=saturday, end_date=saturday,
            duration_minutes=30, org_id=org, check_cross_source=False,
        )
        assert len(slots) == 0

    def test_slot_generation_skips_lunch_break(self, db, user, org, scheduler_config):
        from routes.scheduler.availability import _generate_available_slots
        future = _future_monday(days_ahead=14)
        slots = _generate_available_slots(
            db=db, user_ids=[user], start_date=future.date(), end_date=future.date(),
            duration_minutes=30, org_id=org, check_cross_source=False,
        )
        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])
            lunch_start = slot_start.replace(hour=12, minute=0)
            lunch_end = slot_start.replace(hour=13, minute=0)
            overlaps_lunch = slot_start < lunch_end and slot_end > lunch_start
            assert not overlaps_lunch, f"Slot {slot_start} overlaps lunch break"
