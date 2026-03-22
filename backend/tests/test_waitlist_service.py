"""
Waitlist Service Test Suite

Comprehensive tests for the waiting room / queue management system:
- Join/leave waitlist
- Position management
- Offer/accept flow
- Expiration logic
- Cancellation auto-offer
- Preference matching
- Reorder
- Edge cases and error handling
"""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models.waiting_room import WaitlistEntry, WaitlistStatus
from services.waitlist_service import WaitlistService, OFFER_TIMEOUT_HOURS


# =============================================================================
# FIXTURES
# =============================================================================

class MockAppointmentType:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.type_name = kwargs.get("type_name", "Discovery Call")
        self.default_duration_minutes = kwargs.get("default_duration_minutes", 30)
        self.organization_id = kwargs.get("organization_id", 1)


class MockAppointment:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.organization_id = kwargs.get("organization_id", 1)
        self.appointment_type_id = kwargs.get("appointment_type_id", 1)
        self.title = kwargs.get("title", "Test Appointment")
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc))
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.attendee_name = kwargs.get("attendee_name", None)
        self.attendee_email = kwargs.get("attendee_email", None)
        self.attendee_phone = kwargs.get("attendee_phone", None)
        self.attendee_notes = kwargs.get("attendee_notes", None)
        self.status = kwargs.get("status", "booked")


class InMemoryWaitlistDB:
    """Simple in-memory mock for SQLAlchemy session that holds WaitlistEntry objects."""

    def __init__(self):
        self._entries = []
        self._appointments = []
        self._appointment_types = []
        self._next_id = 1
        self._next_appt_id = 100

    def query(self, model_class):
        return InMemoryQuery(self, model_class)

    def add(self, obj):
        if isinstance(obj, WaitlistEntry):
            if not obj.id:
                obj.id = self._next_id
                self._next_id += 1
            self._entries.append(obj)
        elif hasattr(obj, 'title') and hasattr(obj, 'scheduled_start'):
            # It's an Appointment mock
            if not obj.id:
                obj.id = self._next_appt_id
                self._next_appt_id += 1
            self._appointments.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def get_entries(self):
        return self._entries

    def add_appointment_type(self, appt_type):
        self._appointment_types.append(appt_type)

    def add_appointment(self, appt):
        if not appt.id:
            appt.id = self._next_appt_id
            self._next_appt_id += 1
        self._appointments.append(appt)


class InMemoryQuery:
    """Simple in-memory query mock that supports filter, order_by, etc."""

    def __init__(self, db, model_class):
        self._db = db
        self._model_class = model_class
        self._filters = []

    def filter(self, *args, **kwargs):
        # Store filters for later evaluation
        # We can't easily evaluate SQLAlchemy filter expressions, so
        # we store them as callables when possible
        new_query = InMemoryQuery(self._db, self._model_class)
        new_query._filters = self._filters + list(args)
        return new_query

    def order_by(self, *args):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def scalar(self):
        return None

    def count(self):
        return len(self.all())

    def first(self):
        results = self.all()
        return results[0] if results else None

    def all(self):
        if self._model_class == WaitlistEntry:
            return list(self._db._entries)
        if self._model_class == MockAppointmentType:
            return list(self._db._appointment_types)
        if self._model_class == MockAppointment:
            return list(self._db._appointments)
        return []


@pytest.fixture
def mock_db():
    """Create an in-memory mock database."""
    return InMemoryWaitlistDB()


@pytest.fixture
def mock_models():
    """Create mock model classes."""
    return {
        "Appointment": type("Appointment", (), {
            "id": None,
            "organization_id": None,
            "appointment_type_id": None,
            "title": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "duration_minutes": None,
            "attendee_name": None,
            "attendee_email": None,
            "attendee_phone": None,
            "attendee_notes": None,
            "status": None,
            "__init__": lambda self, **kw: [setattr(self, k, v) for k, v in kw.items()],
        }),
        "AppointmentType": MockAppointmentType,
    }


@pytest.fixture
def service(mock_models):
    """Create a WaitlistService with a real SQLAlchemy in-memory DB."""
    # Use a real database so we can test actual SQL behavior
    engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))

    from db import Base
    # Create the waitlist_entries table
    WaitlistEntry.__table__.create(engine, checkfirst=True)

    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    svc = WaitlistService(db, mock_models)
    yield svc, db

    db.close()


@pytest.fixture
def base_join_data():
    """Base data for joining waitlist."""
    return {
        "organization_id": 1,
        "appointment_type_id": 1,
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "555-0100",
        "preferred_dates": ["2026-03-20", "2026-03-21"],
        "preferred_times": ["morning", "afternoon"],
        "notes": "First time buyer",
    }


# =============================================================================
# JOIN WAITLIST TESTS
# =============================================================================

class TestJoinWaitlist:
    """Tests for WaitlistService.join_waitlist()."""

    def test_join_waitlist_basic(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)

        assert entry.id is not None
        assert entry.name == "John Doe"
        assert entry.email == "john@example.com"
        assert entry.phone == "555-0100"
        assert entry.position == 1
        assert entry.status == WaitlistStatus.WAITING
        assert entry.organization_id == 1
        assert entry.appointment_type_id == 1
        assert entry.preferred_dates == ["2026-03-20", "2026-03-21"]
        assert entry.preferred_times == ["morning", "afternoon"]
        assert entry.notes == "First time buyer"

    def test_join_waitlist_assigns_sequential_positions(self, service, base_join_data):
        svc, db = service

        e1 = svc.join_waitlist(base_join_data)
        assert e1.position == 1

        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        data2["name"] = "Jane Doe"
        e2 = svc.join_waitlist(data2)
        assert e2.position == 2

        data3 = base_join_data.copy()
        data3["email"] = "bob@example.com"
        data3["name"] = "Bob Smith"
        e3 = svc.join_waitlist(data3)
        assert e3.position == 3

    def test_join_waitlist_duplicate_raises(self, service, base_join_data):
        svc, db = service
        svc.join_waitlist(base_join_data)

        with pytest.raises(ValueError, match="Already on the waitlist"):
            svc.join_waitlist(base_join_data)

    def test_join_waitlist_same_email_different_type(self, service, base_join_data):
        svc, db = service
        svc.join_waitlist(base_join_data)

        data2 = base_join_data.copy()
        data2["appointment_type_id"] = 2
        entry = svc.join_waitlist(data2)
        assert entry.id is not None
        assert entry.appointment_type_id == 2

    def test_join_waitlist_minimal_data(self, service):
        svc, db = service
        entry = svc.join_waitlist({
            "organization_id": 1,
            "appointment_type_id": 1,
            "name": "Minimal User",
            "email": "min@example.com",
        })
        assert entry.id is not None
        assert entry.preferred_dates == []
        assert entry.preferred_times == []
        assert entry.phone is None

    def test_join_waitlist_with_user_id(self, service, base_join_data):
        svc, db = service
        base_join_data["user_id"] = 42
        entry = svc.join_waitlist(base_join_data)
        assert entry.user_id == 42


# =============================================================================
# LEAVE WAITLIST TESTS
# =============================================================================

class TestLeaveWaitlist:
    """Tests for WaitlistService.leave_waitlist()."""

    def test_leave_waitlist_basic(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        result = svc.leave_waitlist(entry.id)
        assert result is True
        assert entry.status == WaitlistStatus.CANCELLED

    def test_leave_waitlist_recalculates_positions(self, service, base_join_data):
        svc, db = service

        e1 = svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        e2 = svc.join_waitlist(data2)
        data3 = base_join_data.copy()
        data3["email"] = "bob@example.com"
        e3 = svc.join_waitlist(data3)
        db.commit()

        # Remove the first entry
        svc.leave_waitlist(e1.id)
        db.commit()

        # Positions should be recalculated
        db.refresh(e2)
        db.refresh(e3)
        assert e2.position == 1
        assert e3.position == 2

    def test_leave_waitlist_not_found(self, service):
        svc, db = service
        with pytest.raises(ValueError, match="not found"):
            svc.leave_waitlist(999)

    def test_leave_waitlist_already_cancelled(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        entry.status = WaitlistStatus.CANCELLED
        db.commit()

        with pytest.raises(ValueError, match="Cannot leave"):
            svc.leave_waitlist(entry.id)

    def test_leave_waitlist_with_org_isolation(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        # Wrong org should fail
        with pytest.raises(ValueError, match="not found"):
            svc.leave_waitlist(entry.id, org_id=999)


# =============================================================================
# GET POSITION TESTS
# =============================================================================

class TestGetPosition:
    """Tests for WaitlistService.get_position()."""

    def test_get_position_basic(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        result = svc.get_position(entry.id)
        assert result["id"] == entry.id
        assert result["position"] == 1
        assert result["total_waiting"] == 1
        assert result["status"] == "waiting"
        assert result["name"] == "John Doe"
        assert result["email"] == "john@example.com"

    def test_get_position_not_found(self, service):
        svc, db = service
        with pytest.raises(ValueError, match="not found"):
            svc.get_position(999)

    def test_get_position_shows_offered_info(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        result = svc.get_position(entry.id)
        assert result["status"] == "offered"
        assert result["offered_at"] is not None
        assert result["offered_slot_time"] is not None
        assert result["expires_at"] is not None


# =============================================================================
# GET WAITLIST TESTS
# =============================================================================

class TestGetWaitlist:
    """Tests for WaitlistService.get_waitlist()."""

    def test_get_waitlist_empty(self, service):
        svc, db = service
        result = svc.get_waitlist(org_id=1)
        assert result["entries"] == []
        assert result["total"] == 0

    def test_get_waitlist_returns_entries(self, service, base_join_data):
        svc, db = service
        svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        svc.join_waitlist(data2)
        db.commit()

        result = svc.get_waitlist(org_id=1)
        assert result["total"] == 2
        assert len(result["entries"]) == 2

    def test_get_waitlist_filter_by_appointment_type(self, service, base_join_data):
        svc, db = service
        svc.join_waitlist(base_join_data)

        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        data2["appointment_type_id"] = 2
        svc.join_waitlist(data2)
        db.commit()

        result = svc.get_waitlist(org_id=1, appointment_type_id=1)
        assert result["total"] == 1

    def test_get_waitlist_filter_by_status(self, service, base_join_data):
        svc, db = service
        e1 = svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        e2 = svc.join_waitlist(data2)
        db.commit()

        e1.status = WaitlistStatus.CANCELLED
        db.commit()

        result = svc.get_waitlist(org_id=1, status="waiting")
        assert result["total"] == 1

    def test_get_waitlist_invalid_status(self, service):
        svc, db = service
        with pytest.raises(ValueError, match="Invalid status"):
            svc.get_waitlist(org_id=1, status="invalid")


# =============================================================================
# OFFER SLOT TESTS
# =============================================================================

class TestOfferSlot:
    """Tests for WaitlistService.offer_slot()."""

    def test_offer_slot_basic(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        updated = svc.offer_slot(entry.id, slot_time)

        assert updated.status == WaitlistStatus.OFFERED
        assert updated.offered_at is not None
        assert updated.offered_slot_time == slot_time
        assert updated.expires_at is not None
        # Expires in ~24 hours
        expected_expiry = updated.offered_at + timedelta(hours=OFFER_TIMEOUT_HOURS)
        assert abs((updated.expires_at - expected_expiry).total_seconds()) < 2

    def test_offer_slot_not_found(self, service):
        svc, db = service
        with pytest.raises(ValueError, match="not found"):
            svc.offer_slot(999, datetime.now(timezone.utc))

    def test_offer_slot_wrong_status(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        entry.status = WaitlistStatus.OFFERED
        db.commit()

        with pytest.raises(ValueError, match="WAITING status"):
            svc.offer_slot(entry.id, datetime.now(timezone.utc))

    def test_offer_slot_with_org_isolation(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        with pytest.raises(ValueError, match="not found"):
            svc.offer_slot(entry.id, datetime.now(timezone.utc), org_id=999)


# =============================================================================
# ACCEPT OFFER TESTS
# =============================================================================

class TestAcceptOffer:
    """Tests for WaitlistService.accept_offer()."""

    def test_accept_offer_basic(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        result = svc.accept_offer(entry.id)

        assert result is not None
        assert result["waitlist_entry"]["status"] == "accepted"
        assert result["appointment"]["scheduled_start"] is not None
        assert result["appointment"]["attendee_name"] == "John Doe"
        assert result["appointment"]["attendee_email"] == "john@example.com"

    def test_accept_offer_sets_status(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        svc.accept_offer(entry.id)
        db.commit()

        db.refresh(entry)
        assert entry.status == WaitlistStatus.ACCEPTED
        assert entry.accepted_at is not None
        assert entry.appointment_id is not None

    def test_accept_offer_not_offered(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        with pytest.raises(ValueError, match="OFFERED status"):
            svc.accept_offer(entry.id)

    def test_accept_expired_offer(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)

        # Manually expire the offer
        entry.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        with pytest.raises(ValueError, match="expired"):
            svc.accept_offer(entry.id)

        db.refresh(entry)
        assert entry.status == WaitlistStatus.EXPIRED


# =============================================================================
# EXPIRE OFFERS TESTS
# =============================================================================

class TestExpireOffers:
    """Tests for WaitlistService.expire_offers()."""

    def test_expire_offers_none_expired(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        count = svc.expire_offers()
        assert count == 0

    def test_expire_offers_with_expired(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)

        # Expire the offer
        entry.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        count = svc.expire_offers()
        assert count == 1

        db.refresh(entry)
        assert entry.status == WaitlistStatus.EXPIRED

    def test_expire_offers_multiple(self, service, base_join_data):
        svc, db = service

        # Create 3 entries, offer all, expire 2
        entries = []
        for i in range(3):
            data = base_join_data.copy()
            data["email"] = f"user{i}@example.com"
            e = svc.join_waitlist(data)
            entries.append(e)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        for e in entries:
            svc.offer_slot(e.id, slot_time)

        # Expire only first two
        entries[0].expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        entries[1].expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

        count = svc.expire_offers()
        assert count == 2


# =============================================================================
# PROCESS CANCELLATION TESTS
# =============================================================================

class TestProcessCancellation:
    """Tests for WaitlistService.process_cancellation()."""

    def test_process_cancellation_offers_to_first(self, service, base_join_data, mock_models):
        svc, db = service

        # Create an appointment
        Appointment = mock_models["Appointment"]
        appt = Appointment(
            id=100,
            organization_id=1,
            appointment_type_id=1,
            scheduled_start=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.commit()

        # Create waitlist entry
        svc.join_waitlist(base_join_data)
        db.commit()

        result = svc.process_cancellation(100, org_id=1)
        assert result is not None
        assert result["name"] == "John Doe"

    def test_process_cancellation_no_waitlist(self, service, mock_models):
        svc, db = service

        Appointment = mock_models["Appointment"]
        appt = Appointment(
            id=100,
            organization_id=1,
            appointment_type_id=1,
            scheduled_start=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.commit()

        result = svc.process_cancellation(100, org_id=1)
        assert result is None

    def test_process_cancellation_no_appointment(self, service):
        svc, db = service
        result = svc.process_cancellation(999, org_id=1)
        assert result is None


# =============================================================================
# NOTIFY NEXT TESTS
# =============================================================================

class TestNotifyNext:
    """Tests for WaitlistService.notify_next()."""

    def test_notify_next_basic(self, service, base_join_data):
        svc, db = service
        svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        result = svc.notify_next(1, 1, slot_time=slot_time)

        assert result is not None
        assert result["name"] == "John Doe"
        assert result["offered_slot_time"] is not None

    def test_notify_next_no_waiting(self, service):
        svc, db = service
        result = svc.notify_next(1, 1)
        assert result is None

    def test_notify_next_prefers_matching_preferences(self, service, base_join_data):
        svc, db = service

        # First entry: prefers afternoon
        data1 = base_join_data.copy()
        data1["preferred_times"] = ["afternoon"]
        svc.join_waitlist(data1)

        # Second entry: prefers morning
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        data2["name"] = "Jane Doe"
        data2["preferred_times"] = ["morning"]
        svc.join_waitlist(data2)
        db.commit()

        # Offer a morning slot
        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        result = svc.notify_next(1, 1, slot_time=slot_time)

        assert result is not None
        assert result["name"] == "Jane Doe"
        assert result["match_type"] == "preference"

    def test_notify_next_falls_back_to_position(self, service, base_join_data):
        svc, db = service

        data1 = base_join_data.copy()
        data1["preferred_times"] = ["evening"]
        svc.join_waitlist(data1)

        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        data2["preferred_times"] = ["evening"]
        svc.join_waitlist(data2)
        db.commit()

        # Offer a morning slot - no preference match
        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        result = svc.notify_next(1, 1, slot_time=slot_time)

        assert result is not None
        assert result["match_type"] == "position"
        assert result["position"] == 1


# =============================================================================
# REORDER TESTS
# =============================================================================

class TestReorder:
    """Tests for WaitlistService.reorder_entry()."""

    def test_reorder_move_down(self, service, base_join_data):
        svc, db = service

        e1 = svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        e2 = svc.join_waitlist(data2)
        data3 = base_join_data.copy()
        data3["email"] = "bob@example.com"
        e3 = svc.join_waitlist(data3)
        db.commit()

        svc.reorder_entry(e1.id, 3, org_id=1)
        db.commit()

        db.refresh(e1)
        assert e1.position == 3

    def test_reorder_move_up(self, service, base_join_data):
        svc, db = service

        e1 = svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        e2 = svc.join_waitlist(data2)
        data3 = base_join_data.copy()
        data3["email"] = "bob@example.com"
        e3 = svc.join_waitlist(data3)
        db.commit()

        svc.reorder_entry(e3.id, 1, org_id=1)
        db.commit()

        db.refresh(e3)
        assert e3.position == 1

    def test_reorder_not_found(self, service):
        svc, db = service
        with pytest.raises(ValueError, match="not found"):
            svc.reorder_entry(999, 1, org_id=1)

    def test_reorder_caps_position(self, service, base_join_data):
        svc, db = service

        e1 = svc.join_waitlist(base_join_data)
        data2 = base_join_data.copy()
        data2["email"] = "jane@example.com"
        e2 = svc.join_waitlist(data2)
        db.commit()

        svc.reorder_entry(e1.id, 100, org_id=1)
        db.commit()

        db.refresh(e1)
        assert e1.position == 2  # Capped to max


# =============================================================================
# PREFERENCE MATCHING TESTS
# =============================================================================

class TestPreferenceMatching:
    """Tests for the _find_best_match() internal method."""

    def test_match_by_date(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = ["2026-03-20"]
        data["preferred_times"] = []
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None
        assert match.id == entry.id

    def test_no_match_by_date(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = ["2026-03-25"]
        data["preferred_times"] = []
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is None

    def test_match_by_morning_time(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = ["morning"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_match_by_afternoon_time(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = ["afternoon"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_match_by_evening_time(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = ["evening"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_match_by_time_range(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = ["09:00-12:00"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_no_match_by_time_range(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = ["09:00-12:00"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 15, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is None

    def test_match_combined_date_and_time(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = ["2026-03-20"]
        data["preferred_times"] = ["morning"]
        entry = svc.join_waitlist(data)
        db.commit()

        # Right date and time
        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_no_match_wrong_date_right_time(self, service, base_join_data):
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = ["2026-03-25"]
        data["preferred_times"] = ["morning"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is None


# =============================================================================
# ENTRY SERIALIZATION TESTS
# =============================================================================

class TestEntrySerialization:
    """Tests for WaitlistService._entry_to_dict()."""

    def test_entry_to_dict_waiting(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        d = svc._entry_to_dict(entry)
        assert d["id"] == entry.id
        assert d["status"] == "waiting"
        assert d["name"] == "John Doe"
        assert d["email"] == "john@example.com"
        assert d["position"] == 1
        assert d["offered_at"] is None
        assert d["expires_at"] is None
        assert d["appointment_id"] is None

    def test_entry_to_dict_offered(self, service, base_join_data):
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        d = svc._entry_to_dict(entry)
        assert d["status"] == "offered"
        assert d["offered_at"] is not None
        assert d["offered_slot_time"] is not None
        assert d["expires_at"] is not None


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_preferences_match_anything(self, service, base_join_data):
        """Entry with no preferences should match any slot."""
        svc, db = service

        data = base_join_data.copy()
        data["preferred_dates"] = []
        data["preferred_times"] = []
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        match = svc._find_best_match([entry], slot_time)
        assert match is not None

    def test_position_stays_correct_after_multiple_leaves(self, service, base_join_data):
        svc, db = service

        entries = []
        for i in range(5):
            data = base_join_data.copy()
            data["email"] = f"user{i}@example.com"
            entries.append(svc.join_waitlist(data))
        db.commit()

        # Remove entries 1 and 3
        svc.leave_waitlist(entries[0].id)
        svc.leave_waitlist(entries[2].id)
        db.commit()

        # Remaining: entries[1], entries[3], entries[4]
        db.refresh(entries[1])
        db.refresh(entries[3])
        db.refresh(entries[4])
        assert entries[1].position == 1
        assert entries[3].position == 2
        assert entries[4].position == 3

    def test_concurrent_offers_prevented(self, service, base_join_data):
        """Only WAITING entries can be offered a slot."""
        svc, db = service
        entry = svc.join_waitlist(base_join_data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        svc.offer_slot(entry.id, slot_time)
        db.commit()

        # Second offer should fail
        with pytest.raises(ValueError, match="WAITING status"):
            svc.offer_slot(entry.id, slot_time + timedelta(hours=1))

    def test_malformed_time_preference_ignored(self, service, base_join_data):
        """Malformed time preference strings should not crash matching."""
        svc, db = service

        data = base_join_data.copy()
        data["preferred_times"] = ["invalid", "also-bad-range", "09:00-12:00"]
        entry = svc.join_waitlist(data)
        db.commit()

        slot_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        # Should not raise
        match = svc._find_best_match([entry], slot_time)
        assert match is not None  # Matches on the valid range
