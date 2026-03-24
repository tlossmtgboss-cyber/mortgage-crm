"""
Tests for the scheduler booking links CRUD and analytics endpoints.

Covers:
  - POST   /booking-links              Create a booking link
  - GET    /booking-links              List user's booking links
  - GET    /booking-links/all          List all org booking links (admin only)
  - DELETE /booking-links/{link_id}    Deactivate a booking link
  - GET    /booking-links/{link_id}/analytics    Per-link performance stats
  - GET    /booking-links/analytics/summary      Org-wide analytics summary

Edge cases:
  - Non-admin cannot access /all or analytics/summary
  - Delete of non-existent link returns 404
  - Delete by non-owner returns 404
  - Deactivated links excluded from list
  - Analytics for non-existent link returns 404
  - Analytics forbidden for non-owner non-admin
  - Pagination on list endpoint
  - Reserved slug rejected at schema level
  - Created link gets random suffix appended to slug

Uses an isolated SQLite in-memory DB with the same test infrastructure
pattern as test_scheduler_public_booking_flow.py.
"""

import pytest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables before any app imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-booking-links")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
import base64
_key_material = b"test-key-booking-links-test-0032"[:32].ljust(32, b"0")
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
# Import scheduler enums and models
# ---------------------------------------------------------------------------
from smart_scheduler_models import (
    AppointmentStatus,
    MeetingType,
    MeetingMode,
    RoutingStrategy,
    DEFAULT_WORKING_HOURS,
    create_smart_scheduler_models,
)

from database.models import Organization, User, Lead, Loan
from database.models.communication import Activity
from database.models.task import Task

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
# Models dict for DI
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


_current_mock_user = MockUser()


# ---------------------------------------------------------------------------
# FastAPI app + TestClient wiring
# ---------------------------------------------------------------------------
def _build_app():
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

    from routes.scheduler._helpers import set_dependencies as helpers_set_deps
    helpers_set_deps(override_get_db, mock_get_current_user, _models_dict)

    from routes.scheduler.booking_links import router as bl_router

    prefix = "/api/v1/scheduler"
    app.include_router(bl_router, prefix=prefix)

    return app


# ---------------------------------------------------------------------------
# Patch external services globally
# ---------------------------------------------------------------------------
import routes.scheduler.constants  # noqa: E402, F401
import scheduler_email_service as _ses  # noqa: E402, F401
import services.notification_service as _ns  # noqa: E402, F401

_patches = [
    patch("scheduler_email_service.send_appointment_confirmation_email", return_value={"success": True}),
    patch("scheduler_email_service.send_appointment_confirmation_sms", return_value={"success": True}),
    patch("services.notification_service.notification_service", new=MagicMock()),
]

for p in _patches:
    p.start()


from fastapi.testclient import TestClient  # noqa: E402

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


@pytest.fixture(autouse=True)
def _reset_mock_user():
    """Reset mock user to default admin between tests."""
    global _current_mock_user
    _current_mock_user = MockUser(id=1, organization_id=1, role="admin")
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
    existing = db.query(User).filter(User.id == 2).first()
    if not existing:
        db.add(User(
            id=2,
            organization_id=org,
            email="lo2@test.com",
            hashed_password="$2b$12$test_hashed_password_for_testing",
            first_name="Other",
            last_name="LO",
            role="lo",
            permission_role="lo",
            is_active=True,
        ))
        db.commit()
    return 2


@pytest.fixture
def scheduler_config(db, org, user):
    config = SchedulerConfig(
        organization_id=org,
        user_id=user,
        working_hours=DEFAULT_WORKING_HOURS,
        timezone="America/New_York",
        slot_duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        min_notice_hours=1,
        max_advance_days=60,
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
        slug="test-link-abc123",
        link_name="Test Booking Link",
        description="For CRUD testing",
        appointment_type_ids=[appointment_type.id],
        is_public=True,
        is_active=True,
        view_count=50,
        booking_count=10,
        routing_strategy=RoutingStrategy.RELATIONSHIP,
        assigned_users=[user],
        created_at=datetime.now(timezone.utc) - timedelta(days=15),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@pytest.fixture
def second_booking_link(db, org, user):
    link = BookingLink(
        organization_id=org,
        user_id=user,
        slug="second-link-def456",
        link_name="Second Booking Link",
        is_public=True,
        is_active=True,
        view_count=20,
        booking_count=5,
        routing_strategy=RoutingStrategy.RELATIONSHIP,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@pytest.fixture
def inactive_booking_link(db, org, user):
    link = BookingLink(
        organization_id=org,
        user_id=user,
        slug="inactive-link-ghi789",
        link_name="Inactive Link",
        is_public=True,
        is_active=False,
        routing_strategy=RoutingStrategy.RELATIONSHIP,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@pytest.fixture
def expired_booking_link(db, org, user, appointment_type):
    link = BookingLink(
        organization_id=org,
        user_id=user,
        slug="expired-link-jkl012",
        link_name="Expired Link",
        is_public=True,
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        appointment_type_ids=[appointment_type.id],
        routing_strategy=RoutingStrategy.RELATIONSHIP,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# ============================================================================
# TEST CLASS: Create Booking Link (POST /booking-links)
# ============================================================================

class TestCreateBookingLink:
    """POST /api/v1/scheduler/booking-links"""

    def test_create_booking_link_success(self, client, db, org, user, appointment_type):
        """Creating a booking link returns 200 with link_id and URL."""
        payload = {
            "slug": "my-new-link",
            "link_name": "My New Link",
            "description": "A test booking link",
            "appointment_type_ids": [appointment_type.id],
            "is_public": True,
            "routing_strategy": "relationship",
        }
        resp = client.post("/api/v1/scheduler/booking-links", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "link_id" in data
        assert data["message"] == "Booking link created"
        # The slug gets a random suffix appended
        assert data["url"].startswith("/book/my-new-link-")
        assert len(data["url"]) > len("/book/my-new-link-")

    def test_create_booking_link_slug_gets_random_suffix(self, client, db, org, user):
        """The created slug should have a 6-char hex suffix appended."""
        payload = {
            "slug": "deterministic-slug",
            "link_name": "Suffix Test",
        }
        resp = client.post("/api/v1/scheduler/booking-links", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # URL pattern: /book/deterministic-slug-<6hex>
        url = data["url"]
        assert url.startswith("/book/deterministic-slug-")
        suffix = url.split("deterministic-slug-")[1]
        assert len(suffix) == 6
        # Verify it's valid hex
        int(suffix, 16)

    def test_create_booking_link_default_expiration(self, client, db, org, user):
        """A link created without explicit expires_at gets 90-day default."""
        payload = {
            "slug": "default-expiry",
            "link_name": "Default Expiry Link",
        }
        resp = client.post("/api/v1/scheduler/booking-links", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["expires_at"] is not None
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        # Should be approximately 90 days from now
        expected = datetime.now(timezone.utc) + timedelta(days=90)
        delta = abs((expires - expected).total_seconds())
        assert delta < 60, f"Expiration should be ~90 days from now, got delta={delta}s"

    def test_create_booking_link_reserved_slug_rejected(self, client, db, org, user):
        """A reserved slug (e.g. 'admin') should be rejected with 422."""
        payload = {
            "slug": "admin",
            "link_name": "Admin Link",
        }
        resp = client.post("/api/v1/scheduler/booking-links", json=payload)
        assert resp.status_code == 422, "Reserved slugs should be rejected by schema validation"

    def test_create_booking_link_invalid_slug_format(self, client, db, org, user):
        """Slugs with invalid characters should be rejected with 422."""
        payload = {
            "slug": "UPPER CASE!",
            "link_name": "Bad Slug",
        }
        resp = client.post("/api/v1/scheduler/booking-links", json=payload)
        assert resp.status_code == 422


# ============================================================================
# TEST CLASS: List Booking Links (GET /booking-links)
# ============================================================================

class TestListBookingLinks:
    """GET /api/v1/scheduler/booking-links"""

    def test_list_user_booking_links(self, client, db, org, user, booking_link, second_booking_link):
        """Lists active booking links owned by the current user."""
        resp = client.get("/api/v1/scheduler/booking-links")
        assert resp.status_code == 200
        data = resp.json()

        assert "booking_links" in data
        assert data["total"] == 2
        links = data["booking_links"]
        assert len(links) == 2

        # Verify response shape
        first = links[0]
        assert "id" in first
        assert "slug" in first
        assert "link_name" in first
        assert "url" in first
        assert "view_count" in first
        assert "booking_count" in first

    def test_list_excludes_inactive_links(self, client, db, org, user, booking_link, inactive_booking_link):
        """Inactive (deleted) links should not appear in the user's list."""
        resp = client.get("/api/v1/scheduler/booking-links")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 1
        slugs = [link["slug"] for link in data["booking_links"]]
        assert "inactive-link-ghi789" not in slugs

    def test_list_pagination(self, client, db, org, user, booking_link, second_booking_link):
        """Pagination params limit and offset work correctly."""
        resp = client.get("/api/v1/scheduler/booking-links", params={"limit": 1, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["booking_links"]) == 1
        assert data["total"] == 2  # total count still reflects all matching

    def test_list_only_own_links(self, client, db, org, user, second_user, booking_link):
        """A non-owner user should see only their own links."""
        global _current_mock_user
        _current_mock_user = MockUser(id=2, organization_id=1, role="lo")

        # Create a link owned by user 2
        link2 = BookingLink(
            organization_id=1,
            user_id=2,
            slug="user2-link",
            link_name="User 2 Link",
            is_public=True,
            is_active=True,
            routing_strategy=RoutingStrategy.RELATIONSHIP,
        )
        db.add(link2)
        db.commit()

        resp = client.get("/api/v1/scheduler/booking-links")
        assert resp.status_code == 200
        data = resp.json()

        # Should only see user 2's link, not user 1's booking_link
        assert data["total"] == 1
        assert data["booking_links"][0]["slug"] == "user2-link"


# ============================================================================
# TEST CLASS: List All Booking Links - Admin (GET /booking-links/all)
# ============================================================================

class TestListAllBookingLinks:
    """GET /api/v1/scheduler/booking-links/all"""

    def test_admin_can_list_all_org_links(self, client, db, org, user, booking_link, second_booking_link):
        """Admin user can see all org booking links."""
        resp = client.get("/api/v1/scheduler/booking-links/all")
        assert resp.status_code == 200
        data = resp.json()

        assert "booking_links" in data
        assert len(data["booking_links"]) == 2

    def test_non_admin_forbidden(self, client, db, org, user, booking_link):
        """Non-admin user gets 403 on /all endpoint."""
        global _current_mock_user
        _current_mock_user = MockUser(id=1, organization_id=1, role="lo")

        resp = client.get("/api/v1/scheduler/booking-links/all")
        assert resp.status_code == 403


# ============================================================================
# TEST CLASS: Delete Booking Link (DELETE /booking-links/{link_id})
# ============================================================================

class TestDeleteBookingLink:
    """DELETE /api/v1/scheduler/booking-links/{link_id}"""

    def test_delete_deactivates_link(self, client, db, org, user, booking_link):
        """Deleting a link sets is_active=False (soft delete)."""
        link_id = booking_link.id
        resp = client.delete(f"/api/v1/scheduler/booking-links/{link_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Booking link deactivated"

        # Verify in DB
        fresh = _TestSession()
        try:
            updated = fresh.query(BookingLink).filter(BookingLink.id == link_id).first()
            assert updated.is_active is False
        finally:
            fresh.close()

    def test_delete_nonexistent_link_returns_404(self, client, db, org, user):
        """Deleting a non-existent link returns 404."""
        resp = client.delete("/api/v1/scheduler/booking-links/99999")
        assert resp.status_code == 404

    def test_delete_other_users_link_returns_404(self, client, db, org, user, second_user):
        """A user cannot delete another user's link (filtered by user_id)."""
        # Create link owned by user 2
        link = BookingLink(
            organization_id=1,
            user_id=2,
            slug="other-user-link",
            link_name="Other User Link",
            is_public=True,
            is_active=True,
            routing_strategy=RoutingStrategy.RELATIONSHIP,
        )
        db.add(link)
        db.commit()
        db.refresh(link)

        # Current mock user is user 1 (admin) -- but delete filters by user_id
        resp = client.delete(f"/api/v1/scheduler/booking-links/{link.id}")
        assert resp.status_code == 404, "Should not be able to delete another user's link"


# ============================================================================
# TEST CLASS: Per-Link Analytics (GET /booking-links/{link_id}/analytics)
# ============================================================================

class TestBookingLinkAnalytics:
    """GET /api/v1/scheduler/booking-links/{link_id}/analytics"""

    def test_owner_can_view_analytics(self, client, db, org, user, booking_link):
        """Link owner can view analytics for their own link."""
        resp = client.get(f"/api/v1/scheduler/booking-links/{booking_link.id}/analytics")
        assert resp.status_code == 200
        data = resp.json()

        assert data["link_id"] == booking_link.id
        assert data["slug"] == booking_link.slug
        assert data["is_active"] is True
        assert "metrics" in data
        metrics = data["metrics"]
        assert metrics["total_views"] == 50
        assert metrics["total_bookings"] == 10
        assert metrics["conversion_rate_pct"] == 20.0
        assert metrics["days_active"] >= 15

    def test_analytics_nonexistent_link_returns_404(self, client, db, org, user):
        """Analytics for a non-existent link returns 404."""
        resp = client.get("/api/v1/scheduler/booking-links/99999/analytics")
        assert resp.status_code == 404

    def test_non_owner_non_admin_forbidden(self, client, db, org, user, second_user, booking_link):
        """A non-owner, non-admin user gets 403 on another user's link analytics."""
        global _current_mock_user
        _current_mock_user = MockUser(id=2, organization_id=1, role="lo")

        resp = client.get(f"/api/v1/scheduler/booking-links/{booking_link.id}/analytics")
        assert resp.status_code == 403

    def test_admin_can_view_any_link_analytics(self, client, db, org, user, second_user):
        """An admin can view analytics on any link in the org."""
        # Create link owned by user 2
        link = BookingLink(
            organization_id=1,
            user_id=2,
            slug="user2-analytics-link",
            link_name="User 2 Analytics Link",
            is_public=True,
            is_active=True,
            view_count=100,
            booking_count=25,
            routing_strategy=RoutingStrategy.RELATIONSHIP,
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db.add(link)
        db.commit()
        db.refresh(link)

        # Current user is admin (user 1)
        resp = client.get(f"/api/v1/scheduler/booking-links/{link.id}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metrics"]["total_views"] == 100
        assert data["metrics"]["total_bookings"] == 25

    def test_analytics_zero_views_conversion_rate(self, client, db, org, user):
        """A link with zero views should return 0.0 conversion rate (no division by zero)."""
        link = BookingLink(
            organization_id=1,
            user_id=1,
            slug="zero-views-link",
            link_name="Zero Views",
            is_public=True,
            is_active=True,
            view_count=0,
            booking_count=0,
            routing_strategy=RoutingStrategy.RELATIONSHIP,
            created_at=datetime.now(timezone.utc),
        )
        db.add(link)
        db.commit()
        db.refresh(link)

        resp = client.get(f"/api/v1/scheduler/booking-links/{link.id}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metrics"]["conversion_rate_pct"] == 0.0
        assert data["metrics"]["avg_daily_views"] == 0.0


# ============================================================================
# TEST CLASS: Summary Analytics (GET /booking-links/analytics/summary)
# ============================================================================

class TestBookingLinksSummaryAnalytics:
    """GET /api/v1/scheduler/booking-links/analytics/summary"""

    def test_admin_gets_org_summary(self, client, db, org, user, booking_link, second_booking_link):
        """Admin gets aggregate analytics across all org links."""
        resp = client.get("/api/v1/scheduler/booking-links/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert data["organization_id"] == 1
        assert data["total_links"] == 2
        assert data["total_views"] == 70   # 50 + 20
        assert data["total_bookings"] == 15  # 10 + 5
        # Conversion rate: 15/70 * 100 = 21.4%
        assert data["overall_conversion_rate_pct"] == pytest.approx(21.4, abs=0.1)

        # Per-link breakdown sorted by bookings desc
        links = data["links"]
        assert len(links) == 2
        assert links[0]["bookings"] >= links[1]["bookings"]

    def test_non_admin_forbidden(self, client, db, org, user, booking_link):
        """Non-admin user gets 403 on summary analytics."""
        global _current_mock_user
        _current_mock_user = MockUser(id=1, organization_id=1, role="lo")

        resp = client.get("/api/v1/scheduler/booking-links/analytics/summary")
        assert resp.status_code == 403

    def test_summary_excludes_inactive_links(self, client, db, org, user, booking_link, inactive_booking_link):
        """Inactive links should not be counted in summary analytics."""
        resp = client.get("/api/v1/scheduler/booking-links/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_links"] == 1
        assert data["total_views"] == 50
        assert data["total_bookings"] == 10
