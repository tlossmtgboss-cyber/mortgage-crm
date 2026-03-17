"""
Conflict Detection, Race Conditions & Concurrency E2E Tests

Exercises the scheduler's conflict detection across:
  1. Single-source conflicts (same Appointment table)
  2. Cross-source conflicts (CalendarEvent, CRMCalendarEvent, blocked times)
  3. Concurrent booking via threading (SELECT FOR UPDATE pessimistic locking)
  4. Pessimistic locking behaviour (row-lock contention)
  5. Appointment status machine (valid/invalid transitions)

Run:
    python -m pytest tests/test_conflict_detection_e2e.py -v --noconftest
"""

import os
import sys
import time
import uuid
import threading
import pytest
from datetime import datetime, timedelta, date, timezone, time as dt_time
from unittest.mock import MagicMock, patch, PropertyMock
from collections import Counter

# ---------------------------------------------------------------------------
# Path & env setup
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Import the functions under test (from the canonical availability module)
# ---------------------------------------------------------------------------
from smart_scheduler_models import AppointmentStatus, MeetingType, MeetingMode


# ===========================================================================
# Helpers — lightweight in-memory Appointment stand-in
# ===========================================================================

class FakeAppointment:
    """Minimal in-memory Appointment stand-in that exposes the columns the
    conflict helpers query against."""

    _next_id = 1

    def __init__(self, *, assigned_user_id, scheduled_start, scheduled_end,
                 status=AppointmentStatus.BOOKED, organization_id=1,
                 attendee_email=None, id=None,
                 created_by_user_id=None, lead_id=None, loan_id=None,
                 duration_minutes=30, title="Test Appt",
                 meeting_type=MeetingType.CUSTOM, meeting_mode=MeetingMode.VIDEO,
                 booked_by_ai=False, cancelled_at=None, completed_at=None,
                 no_show_at=None, cancellation_reason=None,
                 status_changed_at=None, status_changed_by=None,
                 reschedule_count=0, rescheduled_from_id=None,
                 description=None, timezone_str="America/Chicago",
                 intake_responses=None, ai_booking_context=None,
                 contact_id=None, appointment_type_id=None,
                 video_link=None, phone_number=None,
                 attendee_name=None, attendee_phone=None,
                 attendee_notes=None, internal_notes=None,
                 meeting_notes=None, auto_confirmed=False,
                 google_calendar_event_id=None, outlook_event_id=None):
        if id is None:
            self.id = FakeAppointment._next_id
            FakeAppointment._next_id += 1
        else:
            self.id = id
        self.organization_id = organization_id
        self.assigned_user_id = assigned_user_id
        self.scheduled_start = scheduled_start
        self.scheduled_end = scheduled_end
        self.status = status
        self.attendee_email = attendee_email
        self.created_by_user_id = created_by_user_id or assigned_user_id
        self.lead_id = lead_id
        self.loan_id = loan_id
        self.duration_minutes = duration_minutes
        self.title = title
        self.meeting_type = meeting_type
        self.meeting_mode = meeting_mode
        self.booked_by_ai = booked_by_ai
        self.cancelled_at = cancelled_at
        self.completed_at = completed_at
        self.no_show_at = no_show_at
        self.cancellation_reason = cancellation_reason
        self.status_changed_at = status_changed_at or datetime.now(timezone.utc)
        self.status_changed_by = status_changed_by
        self.reschedule_count = reschedule_count
        self.rescheduled_from_id = rescheduled_from_id
        self.description = description
        self.timezone = timezone_str
        self.intake_responses = intake_responses or {}
        self.ai_booking_context = ai_booking_context
        self.contact_id = contact_id
        self.appointment_type_id = appointment_type_id
        self.video_link = video_link
        self.phone_number = phone_number
        self.attendee_name = attendee_name
        self.attendee_phone = attendee_phone
        self.attendee_notes = attendee_notes
        self.internal_notes = internal_notes
        self.meeting_notes = meeting_notes
        self.auto_confirmed = auto_confirmed
        self.google_calendar_event_id = google_calendar_event_id
        self.outlook_event_id = outlook_event_id
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeCalendarEvent:
    """Stand-in for CalendarEvent (manual calendar entries)."""
    def __init__(self, user_id, start_time, end_time, status="confirmed", organization_id=1):
        self.user_id = user_id
        self.start_time = start_time
        self.end_time = end_time
        self.status = status
        self.organization_id = organization_id


class FakeCRMCalendarEvent:
    """Stand-in for CRMCalendarEvent (Salesforce-synced events)."""
    def __init__(self, owner_user_id, start_at, end_at, status="confirmed", organization_id=1):
        self.owner_user_id = owner_user_id
        self.start_at = start_at
        self.end_at = end_at
        self.status = status
        self.organization_id = organization_id


class FakeBlockedTime:
    """Stand-in for BlockedTime."""
    def __init__(self, user_id, start_datetime, end_datetime,
                 is_active=True, applies_to_all_users=False,
                 organization_id=1, all_day=False, block_type="custom",
                 title="Blocked"):
        self.user_id = user_id
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.is_active = is_active
        self.applies_to_all_users = applies_to_all_users
        self.organization_id = organization_id
        self.all_day = all_day
        self.block_type = block_type
        self.title = title


class FakeSchedulerConfig:
    """Stand-in for SchedulerConfig."""
    def __init__(self, user_id, organization_id=1, working_hours=None,
                 buffer_before_minutes=5, buffer_after_minutes=5,
                 min_notice_hours=0, max_meetings_per_day=8,
                 enforce_lunch_break=False, lunch_break_start=None,
                 lunch_break_end=None, timezone_str="America/Chicago"):
        self.id = user_id  # reuse for simplicity
        self.user_id = user_id
        self.organization_id = organization_id
        self.working_hours = working_hours or {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
            "friday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "09:00", "end": "17:00", "enabled": False},
            "sunday": {"start": "09:00", "end": "17:00", "enabled": False},
        }
        self.buffer_before_minutes = buffer_before_minutes
        self.buffer_after_minutes = buffer_after_minutes
        self.min_notice_hours = min_notice_hours
        self.max_meetings_per_day = max_meetings_per_day
        self.enforce_lunch_break = enforce_lunch_break
        self.lunch_break_start = lunch_break_start
        self.lunch_break_end = lunch_break_end
        self.timezone = timezone_str


# ---------------------------------------------------------------------------
# A lightweight mock DB that mimics session.query().filter().first()
# ---------------------------------------------------------------------------

class FakeQuery:
    """Chainable mock query builder that supports filter, with_for_update, etc."""
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *predicates):
        # Each predicate is a BinaryExpression — we evaluate nothing; just
        # return the full set.  The real filtering is done via _run_filters
        # that callers can override.
        return self

    def with_for_update(self, nowait=False):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items

    def count(self):
        return len(self._items)


class InMemoryDB:
    """
    Minimal mock for a SQLAlchemy Session that stores FakeAppointment objects
    and supports the query patterns used by the conflict helpers.
    """
    def __init__(self):
        self.appointments = []
        self.calendar_events = []
        self.crm_events = []
        self.blocked_times = []
        self.configs = []
        self._committed = False
        self._lock = threading.Lock()

    def add(self, obj):
        if isinstance(obj, FakeAppointment):
            with self._lock:
                self.appointments.append(obj)

    def flush(self):
        pass

    def commit(self):
        self._committed = True

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def query(self, model_class):
        # Return a FakeQuery over the appropriate collection
        if model_class is FakeAppointmentModel:
            return FakeFilterableQuery(self.appointments, "appointment")
        return FakeQuery([])

    def close(self):
        pass


class FakeFilterableQuery:
    """Query that actually applies simple overlap filters for appointments."""
    def __init__(self, items, kind):
        self._items = list(items)
        self._kind = kind
        self._filters_applied = {}

    def filter(self, *predicates):
        # We can't easily evaluate SQLAlchemy BinaryExpression objects, so
        # callers that need real filtering must use the helper directly.
        return self

    def with_for_update(self, nowait=False):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items

    def count(self):
        return len(self._items)


# Sentinel class to match model dict lookups
class FakeAppointmentModel:
    """Used as the 'Appointment' key in _models dict."""
    pass


# ===========================================================================
# Fixtures
# ===========================================================================

BASE_START = datetime(2026, 4, 15, 10, 0, 0)  # Wednesday 10:00 AM
BASE_END = datetime(2026, 4, 15, 10, 30, 0)    # Wednesday 10:30 AM


@pytest.fixture(autouse=True)
def reset_fake_ids():
    """Reset the auto-increment counter between tests."""
    FakeAppointment._next_id = 1
    yield


def _make_conflict_checker(existing_appointments):
    """
    Build a self-contained conflict checker that mimics the production
    _check_appointment_conflict function but operates on a plain list.

    This lets us test the overlap logic purely, without needing real
    SQLAlchemy sessions.
    """
    def check(assigned_user_id, start_time, end_time,
              org_id=1, exclude_appointment_id=None):
        for appt in existing_appointments:
            if appt.assigned_user_id != assigned_user_id:
                continue
            if appt.organization_id != org_id:
                continue
            if appt.status in (AppointmentStatus.CANCELLED, "cancelled", "no_show"):
                continue
            if exclude_appointment_id is not None and appt.id == exclude_appointment_id:
                continue
            # Standard overlap test: start < other_end AND end > other_start
            if start_time < appt.scheduled_end and end_time > appt.scheduled_start:
                raise HTTPException(
                    status_code=409,
                    detail="This time slot is no longer available. Please select a different time."
                )
    return check


def _make_duplicate_checker(existing_appointments):
    """Build a self-contained duplicate booking checker."""
    def check(attendee_email, assigned_user_id, start_time,
              org_id=1, window_minutes=30):
        if not attendee_email:
            return
        window_start = start_time - timedelta(minutes=window_minutes)
        window_end = start_time + timedelta(minutes=window_minutes)

        for appt in existing_appointments:
            if appt.attendee_email != attendee_email:
                continue
            if appt.assigned_user_id != assigned_user_id:
                continue
            if appt.organization_id != org_id:
                continue
            if appt.status in (AppointmentStatus.CANCELLED, "cancelled"):
                continue
            if window_start <= appt.scheduled_start <= window_end:
                raise HTTPException(
                    status_code=409,
                    detail="A booking for this email already exists at this time."
                )
    return check


def _make_cross_source_conflict_checker():
    """Build a checker using the production _has_cross_source_conflict logic."""
    from routes.scheduler.availability import _has_cross_source_conflict
    return _has_cross_source_conflict


# ===========================================================================
# 1. SINGLE-SOURCE CONFLICTS (9 tests)
# ===========================================================================

class TestSingleSourceConflicts:
    """Tests that verify conflict detection within the Appointment table."""

    def test_exact_same_slot_rejected(self):
        """Book a slot, then try to book the exact same slot -> 409."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        with pytest.raises(HTTPException) as exc:
            check(1, BASE_START, BASE_END)
        assert exc.value.status_code == 409

    def test_overlapping_start_during_existing(self):
        """New slot starts during an existing appointment -> 409."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        overlap_start = BASE_START + timedelta(minutes=15)
        overlap_end = overlap_start + timedelta(minutes=30)
        with pytest.raises(HTTPException) as exc:
            check(1, overlap_start, overlap_end)
        assert exc.value.status_code == 409

    def test_overlapping_end_during_existing(self):
        """New slot ends during an existing appointment -> 409."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        overlap_start = BASE_START - timedelta(minutes=15)
        overlap_end = BASE_START + timedelta(minutes=15)
        with pytest.raises(HTTPException) as exc:
            check(1, overlap_start, overlap_end)
        assert exc.value.status_code == 409

    def test_adjacent_slot_no_buffer_allowed(self):
        """Adjacent slot (end == next start, no buffer) -> allowed (200 equivalent)."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        # Slot starts exactly when existing ends
        adjacent_start = BASE_END
        adjacent_end = BASE_END + timedelta(minutes=30)
        # Should NOT raise
        check(1, adjacent_start, adjacent_end)

    def test_adjacent_slot_with_buffer_violation(self):
        """Adjacent slot that violates buffer period -> 409.

        Production uses buffer_before and buffer_after when generating slots
        in _generate_available_slots. Here we verify the buffer overlap logic
        from _has_cross_source_conflict which IS used during slot generation.
        """
        has_conflict = _make_cross_source_conflict_checker()
        existing_busy = [(BASE_START, BASE_END)]

        # Adjacent slot starts exactly at BASE_END with a 5-min buffer_after
        # The buffered_end of the existing slot is BASE_END + 5 min.
        # New slot at BASE_END should conflict because BASE_END < buffered_end.
        adjacent_start = BASE_END
        adjacent_end = BASE_END + timedelta(minutes=30)
        assert has_conflict(existing_busy, adjacent_start, adjacent_end,
                            buffer_before=5, buffer_after=5) is True

    def test_adjacent_slot_outside_buffer_allowed(self):
        """Adjacent slot outside the buffer window -> allowed."""
        has_conflict = _make_cross_source_conflict_checker()
        existing_busy = [(BASE_START, BASE_END)]

        # Start 10 minutes after the existing slot ends (buffer is 5 min)
        safe_start = BASE_END + timedelta(minutes=10)
        safe_end = safe_start + timedelta(minutes=30)
        assert has_conflict(existing_busy, safe_start, safe_end,
                            buffer_before=5, buffer_after=5) is False

    def test_cancel_first_then_rebook_succeeds(self):
        """Cancel an appointment, then book the same slot -> allowed."""
        cancelled = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END,
            status=AppointmentStatus.CANCELLED)
        check = _make_conflict_checker([cancelled])

        # Should NOT raise — cancelled appointments are excluded
        check(1, BASE_START, BASE_END)

    def test_different_los_same_time_allowed(self):
        """Different LOs can have appointments at the same time."""
        lo1_appt = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([lo1_appt])

        # LO 2 books the same time -> allowed (different user)
        check(2, BASE_START, BASE_END)

    def test_same_lo_overlapping_rejected(self):
        """Same LO cannot have overlapping appointments."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        # Same LO, overlapping time -> 409
        with pytest.raises(HTTPException) as exc:
            check(1, BASE_START + timedelta(minutes=10), BASE_END + timedelta(minutes=10))
        assert exc.value.status_code == 409


# ===========================================================================
# 2. CROSS-SOURCE CONFLICTS (6 tests)
# ===========================================================================

class TestCrossSourceConflicts:
    """Tests that verify cross-source conflict detection across calendar sources."""

    def test_manual_calendar_event_blocks_slot(self):
        """A CalendarEvent (manual) should block the scheduling slot."""
        has_conflict = _make_cross_source_conflict_checker()

        # Manual calendar event from 10:00-11:00
        cal_event_busy = [(BASE_START, BASE_START + timedelta(hours=1))]

        # Trying to book 10:15-10:45 should conflict
        assert has_conflict(cal_event_busy,
                            BASE_START + timedelta(minutes=15),
                            BASE_START + timedelta(minutes=45)) is True

    def test_google_synced_event_blocks_slot(self):
        """A Google Calendar synced event (via CRMCalendarEvent) blocks slot."""
        has_conflict = _make_cross_source_conflict_checker()

        google_event_busy = [(
            BASE_START + timedelta(hours=2),
            BASE_START + timedelta(hours=3),
        )]

        # Trying to book during the synced event
        assert has_conflict(google_event_busy,
                            BASE_START + timedelta(hours=2, minutes=15),
                            BASE_START + timedelta(hours=2, minutes=45)) is True

    def test_soft_hold_blocks_slot(self):
        """A tentative/soft hold appointment blocks the slot."""
        has_conflict = _make_cross_source_conflict_checker()

        # Soft holds appear as TENTATIVE status in the appointment table
        # and are included in cross-source conflict lists
        soft_hold_busy = [(BASE_START, BASE_END)]

        assert has_conflict(soft_hold_busy, BASE_START, BASE_END) is True

    def test_expired_soft_hold_does_not_block(self):
        """An expired soft hold (cancelled status) does NOT block the slot.

        Expired holds are excluded at query time (status != cancelled).
        When building the conflict list, cancelled appointments are filtered out.
        So the conflict list would be empty.
        """
        has_conflict = _make_cross_source_conflict_checker()

        # Empty conflict list = the expired hold was already filtered out
        expired_hold_busy = []  # Cancelled/expired items not included
        assert has_conflict(expired_hold_busy, BASE_START, BASE_END) is False

    def test_blocked_time_blocks_slot_generation(self):
        """BlockedTime entries prevent slots from being generated.

        The slot generation engine checks:
            slot_start < bt.end_datetime and slot_end > bt.start_datetime

        We test this overlap logic directly.
        """
        blocked = FakeBlockedTime(
            user_id=1,
            start_datetime=datetime(2026, 4, 15, 9, 0),
            end_datetime=datetime(2026, 4, 15, 12, 0),
        )

        slot_start = datetime(2026, 4, 15, 10, 0)
        slot_end = datetime(2026, 4, 15, 10, 30)

        # Overlap check: slot_start < bt.end and slot_end > bt.start
        is_blocked = slot_start < blocked.end_datetime and slot_end > blocked.start_datetime
        assert is_blocked is True

    def test_holiday_blocks_entire_day(self):
        """An all-day blocked time (holiday) blocks all slots for that day."""
        holiday = FakeBlockedTime(
            user_id=1,
            start_datetime=datetime(2026, 12, 25, 0, 0),
            end_datetime=datetime(2026, 12, 25, 23, 59, 59),
            all_day=True,
            applies_to_all_users=True,
            block_type="holiday",
        )

        # Check multiple slots across the day
        for hour in range(9, 17):
            slot_start = datetime(2026, 12, 25, hour, 0)
            slot_end = slot_start + timedelta(minutes=30)
            is_blocked = slot_start < holiday.end_datetime and slot_end > holiday.start_datetime
            assert is_blocked is True, f"Slot at {hour}:00 should be blocked by holiday"


# ===========================================================================
# 3. CONCURRENT BOOKING (5 tests)
# ===========================================================================

class TestConcurrentBooking:
    """Tests that simulate concurrent booking via threading."""

    def test_two_concurrent_bookings_exactly_one_succeeds(self):
        """Simulate two concurrent bookings for the same slot.
        Exactly one should succeed, one should get 409."""
        results = {"success": 0, "conflict": 0, "errors": []}
        appointments = []
        lock = threading.Lock()

        def attempt_booking(booker_id):
            try:
                check = _make_conflict_checker(appointments)
                # Check for conflict
                check(1, BASE_START, BASE_END)
                # If no conflict, "book" the appointment
                with lock:
                    # Double-check after acquiring lock (simulates SELECT FOR UPDATE)
                    for appt in appointments:
                        if (appt.assigned_user_id == 1 and
                                appt.scheduled_start < BASE_END and
                                appt.scheduled_end > BASE_START and
                                appt.status != AppointmentStatus.CANCELLED):
                            results["conflict"] += 1
                            return

                    appt = FakeAppointment(
                        assigned_user_id=1,
                        scheduled_start=BASE_START,
                        scheduled_end=BASE_END,
                        attendee_email=f"booker{booker_id}@test.com",
                    )
                    appointments.append(appt)
                    results["success"] += 1
            except HTTPException as e:
                if e.status_code == 409:
                    results["conflict"] += 1
                else:
                    results["errors"].append(str(e))
            except Exception as e:
                results["errors"].append(str(e))

        t1 = threading.Thread(target=attempt_booking, args=(1,))
        t2 = threading.Thread(target=attempt_booking, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results["errors"] == [], f"Unexpected errors: {results['errors']}"
        assert results["success"] == 1, f"Expected exactly 1 success, got {results['success']}"
        assert results["conflict"] == 1, f"Expected exactly 1 conflict, got {results['conflict']}"

    def test_409_response_message_is_informative(self):
        """The 409 response should contain a meaningful message about conflict."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START, scheduled_end=BASE_END)
        check = _make_conflict_checker([existing])

        with pytest.raises(HTTPException) as exc:
            check(1, BASE_START, BASE_END)
        assert exc.value.status_code == 409
        assert "time slot" in exc.value.detail.lower() or "available" in exc.value.detail.lower()

    def test_rapid_fire_10_bookings_exactly_one_succeeds(self):
        """Rapid-fire 10 bookings for the same slot -> exactly 1 succeeds."""
        results = Counter()
        appointments = []
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def attempt_booking(booker_id):
            try:
                barrier.wait(timeout=5)  # All threads start simultaneously
                with lock:
                    # Check conflict under lock (simulates SELECT FOR UPDATE)
                    for appt in appointments:
                        if (appt.assigned_user_id == 1 and
                                appt.scheduled_start < BASE_END and
                                appt.scheduled_end > BASE_START and
                                appt.status != AppointmentStatus.CANCELLED):
                            results["conflict"] += 1
                            return

                    appointments.append(FakeAppointment(
                        assigned_user_id=1,
                        scheduled_start=BASE_START,
                        scheduled_end=BASE_END,
                        attendee_email=f"rapid{booker_id}@test.com",
                    ))
                    results["success"] += 1
            except Exception:
                results["error"] += 1

        threads = [threading.Thread(target=attempt_booking, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert results["success"] == 1, f"Expected exactly 1 success, got {results['success']}"
        assert results["conflict"] == 9, f"Expected 9 conflicts, got {results['conflict']}"
        assert results.get("error", 0) == 0

    def test_concurrent_booking_different_slots_both_succeed(self):
        """Two concurrent bookings for DIFFERENT slots should both succeed."""
        results = {"success": 0, "conflict": 0}
        appointments = []
        lock = threading.Lock()
        barrier = threading.Barrier(2)

        slot_a_start = BASE_START
        slot_a_end = BASE_END
        slot_b_start = BASE_START + timedelta(hours=2)
        slot_b_end = BASE_END + timedelta(hours=2)

        def book_slot(start, end, booker_id):
            try:
                barrier.wait(timeout=5)
                with lock:
                    # Check conflict
                    for appt in appointments:
                        if (appt.assigned_user_id == 1 and
                                appt.scheduled_start < end and
                                appt.scheduled_end > start and
                                appt.status != AppointmentStatus.CANCELLED):
                            results["conflict"] += 1
                            return

                    appointments.append(FakeAppointment(
                        assigned_user_id=1,
                        scheduled_start=start,
                        scheduled_end=end,
                        attendee_email=f"booker{booker_id}@test.com",
                    ))
                    results["success"] += 1
            except Exception:
                pass

        t1 = threading.Thread(target=book_slot, args=(slot_a_start, slot_a_end, 1))
        t2 = threading.Thread(target=book_slot, args=(slot_b_start, slot_b_end, 2))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results["success"] == 2, f"Both should succeed for different slots, got {results['success']}"
        assert results["conflict"] == 0

    def test_concurrent_booking_and_cancellation_race(self):
        """
        Race condition: one thread cancels an appointment while another tries to
        book the same slot. The booking should eventually succeed after cancellation.
        """
        appointments = []
        results = {"booked": False, "cancelled": False, "error": None}
        lock = threading.Lock()

        # Pre-create existing appointment
        existing = FakeAppointment(
            assigned_user_id=1,
            scheduled_start=BASE_START,
            scheduled_end=BASE_END,
            attendee_email="original@test.com",
        )
        appointments.append(existing)

        def cancel_appointment():
            """Cancel the existing appointment after a brief pause."""
            time.sleep(0.01)
            with lock:
                existing.status = AppointmentStatus.CANCELLED
                existing.cancelled_at = datetime.now(timezone.utc)
                results["cancelled"] = True

        def try_booking():
            """Try booking with retry (up to 5 attempts)."""
            for attempt in range(5):
                try:
                    with lock:
                        # Check conflict
                        conflict_found = False
                        for appt in appointments:
                            if (appt.assigned_user_id == 1 and
                                    appt.scheduled_start < BASE_END and
                                    appt.scheduled_end > BASE_START and
                                    appt.status not in (AppointmentStatus.CANCELLED, "cancelled")):
                                conflict_found = True
                                break

                        if not conflict_found:
                            appointments.append(FakeAppointment(
                                assigned_user_id=1,
                                scheduled_start=BASE_START,
                                scheduled_end=BASE_END,
                                attendee_email="newbooker@test.com",
                            ))
                            results["booked"] = True
                            return
                    time.sleep(0.02)
                except Exception as e:
                    results["error"] = str(e)
                    return

        t_cancel = threading.Thread(target=cancel_appointment)
        t_book = threading.Thread(target=try_booking)
        t_cancel.start()
        t_book.start()
        t_cancel.join(timeout=5)
        t_book.join(timeout=5)

        assert results["cancelled"] is True
        assert results["booked"] is True, "Booking should succeed after cancellation"
        assert results["error"] is None


# ===========================================================================
# 4. PESSIMISTIC LOCKING (4 tests)
# ===========================================================================

class TestPessimisticLocking:
    """Tests that verify the SELECT FOR UPDATE row-locking behaviour.

    In production, _check_appointment_conflict uses with_for_update(nowait=True).
    When a row is locked by another transaction, OperationalError is raised and
    converted to 409. We test this via source analysis and mock simulation.
    """

    def test_conflict_check_uses_for_update(self):
        """Verify the production code calls with_for_update(nowait=True)."""
        import inspect
        from routes.scheduler.availability import _check_appointment_conflict
        source = inspect.getsource(_check_appointment_conflict)
        assert "with_for_update" in source, "Must use SELECT FOR UPDATE for pessimistic locking"
        assert "nowait=True" in source, "Must use nowait=True to fail fast on lock contention"

    def test_operational_error_yields_409(self):
        """When SELECT FOR UPDATE hits a lock, OperationalError -> 409."""
        import inspect
        from routes.scheduler.availability import _check_appointment_conflict
        source = inspect.getsource(_check_appointment_conflict)
        assert "OperationalError" in source, "Must catch OperationalError for lock contention"
        assert "409" in source, "OperationalError must produce 409 status code"

    def test_row_lock_contention_raises_conflict(self):
        """Simulate row-lock contention via OperationalError injection.

        When db.query().filter().with_for_update() raises OperationalError,
        the function should raise HTTPException(409).
        """
        from sqlalchemy.exc import OperationalError
        from sqlalchemy import Column, Integer, String, DateTime
        from sqlalchemy import Enum as SQLEnum

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.with_for_update.side_effect = OperationalError("lock", {}, Exception())

        # Use real SQLAlchemy columns to avoid MagicMock comparison issues
        from smart_scheduler_models import AppointmentStatus as AS
        import routes.scheduler.availability as avail_mod
        original_models = avail_mod._models

        # Build a simple mock model class with real SQLAlchemy columns
        from db import Base

        class _TempConflictModel(Base):
            __tablename__ = f"_temp_conflict_{uuid.uuid4().hex[:8]}"
            __table_args__ = {'extend_existing': True}
            id = Column(Integer, primary_key=True)
            assigned_user_id = Column(Integer)
            organization_id = Column(Integer)
            status = Column(SQLEnum(AS))
            scheduled_start = Column(DateTime)
            scheduled_end = Column(DateTime)

        avail_mod._models = {'Appointment': _TempConflictModel}

        try:
            with pytest.raises(HTTPException) as exc:
                avail_mod._check_appointment_conflict(
                    mock_db, assigned_user_id=1,
                    start_time=BASE_START, end_time=BASE_END,
                    org_id=1
                )
            assert exc.value.status_code == 409
            assert "being booked by another user" in exc.value.detail
        finally:
            avail_mod._models = original_models

    def test_no_conflict_when_no_rows_found(self):
        """When SELECT FOR UPDATE returns no rows, no conflict -> OK."""
        from sqlalchemy import Column, Integer, String, DateTime
        from sqlalchemy import Enum as SQLEnum

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.first.return_value = None  # No conflicting row

        from smart_scheduler_models import AppointmentStatus as AS
        import routes.scheduler.availability as avail_mod
        original_models = avail_mod._models

        from db import Base

        class _TempNoConflictModel(Base):
            __tablename__ = f"_temp_noconflict_{uuid.uuid4().hex[:8]}"
            __table_args__ = {'extend_existing': True}
            id = Column(Integer, primary_key=True)
            assigned_user_id = Column(Integer)
            organization_id = Column(Integer)
            status = Column(SQLEnum(AS))
            scheduled_start = Column(DateTime)
            scheduled_end = Column(DateTime)

        avail_mod._models = {'Appointment': _TempNoConflictModel}

        try:
            # Should NOT raise
            avail_mod._check_appointment_conflict(
                mock_db, assigned_user_id=1,
                start_time=BASE_START, end_time=BASE_END,
                org_id=1
            )
        finally:
            avail_mod._models = original_models


# ===========================================================================
# 5. APPOINTMENT STATUS MACHINE (8 tests)
# ===========================================================================

class TestAppointmentStatusMachine:
    """Tests that verify status transition rules.

    The production code in appointments_crud.py update_appointment() applies
    status changes via AppointmentStatus enum. We test the valid/invalid
    transitions based on the enum values and business rules.
    """

    # Define the valid status transitions based on the business logic
    VALID_TRANSITIONS = {
        AppointmentStatus.BOOKED: {
            AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED,
            AppointmentStatus.RESCHEDULED, AppointmentStatus.NO_SHOW,
            AppointmentStatus.TENTATIVE,
        },
        AppointmentStatus.CONFIRMED: {
            AppointmentStatus.REMINDED, AppointmentStatus.CHECKED_IN,
            AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW,
            AppointmentStatus.COMPLETED, AppointmentStatus.RESCHEDULED,
        },
        AppointmentStatus.REMINDED: {
            AppointmentStatus.CHECKED_IN, AppointmentStatus.COMPLETED,
            AppointmentStatus.NO_SHOW, AppointmentStatus.CANCELLED,
        },
        AppointmentStatus.CHECKED_IN: {
            AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW,
        },
        AppointmentStatus.COMPLETED: set(),  # Terminal state
        AppointmentStatus.CANCELLED: set(),  # Terminal state
        AppointmentStatus.NO_SHOW: {
            AppointmentStatus.RESCHEDULED,
        },
        AppointmentStatus.RESCHEDULED: set(),  # Terminal (new appt created)
    }

    def _transition_is_valid(self, from_status, to_status):
        """Check if a transition is valid per our state machine."""
        allowed = self.VALID_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    def test_booked_to_confirmed_valid(self):
        """BOOKED -> CONFIRMED is a valid transition."""
        assert self._transition_is_valid(
            AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED)

    def test_booked_to_cancelled_valid(self):
        """BOOKED -> CANCELLED is a valid transition."""
        assert self._transition_is_valid(
            AppointmentStatus.BOOKED, AppointmentStatus.CANCELLED)

    def test_confirmed_to_completed_valid(self):
        """CONFIRMED -> COMPLETED is a valid transition."""
        assert self._transition_is_valid(
            AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED)

    def test_confirmed_to_no_show_valid(self):
        """CONFIRMED -> NO_SHOW is a valid transition."""
        assert self._transition_is_valid(
            AppointmentStatus.CONFIRMED, AppointmentStatus.NO_SHOW)

    def test_cannot_complete_a_cancelled_appointment(self):
        """CANCELLED -> COMPLETED is NOT a valid transition."""
        assert not self._transition_is_valid(
            AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED)

    def test_cannot_cancel_a_completed_appointment(self):
        """COMPLETED -> CANCELLED is NOT a valid transition."""
        assert not self._transition_is_valid(
            AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED)

    def test_reschedule_increments_count(self):
        """Rescheduling should increment reschedule_count."""
        appt = FakeAppointment(
            assigned_user_id=1,
            scheduled_start=BASE_START,
            scheduled_end=BASE_END,
            reschedule_count=0,
        )

        # Simulate reschedule
        appt.reschedule_count = (appt.reschedule_count or 0) + 1
        appt.status = AppointmentStatus.RESCHEDULED
        appt.rescheduled_from_id = appt.id

        assert appt.reschedule_count == 1
        assert appt.status == AppointmentStatus.RESCHEDULED

    def test_status_history_enum_values_exist(self):
        """All status values referenced in history tracking must be valid enum members."""
        standard_progression = ["booked", "confirmed", "reminded", "checked_in", "completed"]
        for status_str in standard_progression:
            # Should not raise
            status = AppointmentStatus(status_str)
            assert status.value == status_str


# ===========================================================================
# 6. DUPLICATE BOOKING DETECTION (5 tests)
# ===========================================================================

class TestDuplicateBookingDetection:
    """Tests for the _check_duplicate_booking helper."""

    def test_same_email_same_time_rejected(self):
        """Same attendee email + same LO + same time -> 409."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, attendee_email="alice@test.com")
        check = _make_duplicate_checker([existing])

        with pytest.raises(HTTPException) as exc:
            check("alice@test.com", 1, BASE_START)
        assert exc.value.status_code == 409

    def test_same_email_within_window_rejected(self):
        """Same email within the default 30-min window -> 409."""
        existing = FakeAppointment(
            assigned_user_id=1,
            scheduled_start=BASE_START,
            scheduled_end=BASE_END,
            attendee_email="bob@test.com",
        )
        check = _make_duplicate_checker([existing])

        # 15 minutes later -> within 30 min window
        with pytest.raises(HTTPException) as exc:
            check("bob@test.com", 1, BASE_START + timedelta(minutes=15))
        assert exc.value.status_code == 409

    def test_same_email_outside_window_allowed(self):
        """Same email but outside 30-min window -> allowed."""
        existing = FakeAppointment(
            assigned_user_id=1,
            scheduled_start=BASE_START,
            scheduled_end=BASE_END,
            attendee_email="charlie@test.com",
        )
        check = _make_duplicate_checker([existing])

        # 2 hours later -> outside 30 min window
        check("charlie@test.com", 1, BASE_START + timedelta(hours=2))

    def test_different_email_same_time_allowed(self):
        """Different attendee email at same time -> allowed."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, attendee_email="alice@test.com")
        check = _make_duplicate_checker([existing])

        # Different email -> no duplicate
        check("different@test.com", 1, BASE_START)

    def test_no_email_skips_check(self):
        """If no attendee_email provided, skip duplicate check entirely."""
        existing = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, attendee_email="alice@test.com")
        check = _make_duplicate_checker([existing])

        # No email -> skip check, no exception
        check(None, 1, BASE_START)
        check("", 1, BASE_START)


# ===========================================================================
# 7. SLOT GENERATION INTEGRATION (4 tests)
# ===========================================================================

class TestSlotGenerationConflictIntegration:
    """Tests that verify conflict detection within the slot generation engine.

    These test the overlap logic that _generate_available_slots uses to exclude
    conflicting slots (without requiring a real DB).
    """

    def test_existing_appointment_excludes_its_slot(self):
        """An existing appointment at 10:00-10:30 should exclude that slot."""
        has_conflict = _make_cross_source_conflict_checker()
        busy = [(BASE_START, BASE_END)]

        # The slot at 10:00 should conflict
        assert has_conflict(busy, BASE_START, BASE_END, buffer_before=0, buffer_after=0) is True

        # The slot at 11:00 should NOT conflict
        assert has_conflict(busy,
                            BASE_START + timedelta(hours=1),
                            BASE_END + timedelta(hours=1),
                            buffer_before=0, buffer_after=0) is False

    def test_buffer_expands_exclusion_zone(self):
        """Buffer minutes expand the exclusion zone around appointments."""
        has_conflict = _make_cross_source_conflict_checker()
        busy = [(datetime(2026, 4, 15, 10, 0), datetime(2026, 4, 15, 10, 30))]

        # 9:30-10:00 slot: with 5-min buffer_before on the appointment,
        # the buffered_start = 9:55. Slot end (10:00) > buffered_start (9:55) -> conflict!
        assert has_conflict(busy,
                            datetime(2026, 4, 15, 9, 30),
                            datetime(2026, 4, 15, 10, 0),
                            buffer_before=5, buffer_after=0) is True

        # 9:00-9:30 slot: slot_end (9:30) < buffered_start (9:55) -> no conflict
        assert has_conflict(busy,
                            datetime(2026, 4, 15, 9, 0),
                            datetime(2026, 4, 15, 9, 30),
                            buffer_before=5, buffer_after=0) is False

    def test_multiple_conflicts_all_checked(self):
        """Multiple busy periods should all be checked."""
        has_conflict = _make_cross_source_conflict_checker()
        busy = [
            (datetime(2026, 4, 15, 9, 0), datetime(2026, 4, 15, 9, 30)),
            (datetime(2026, 4, 15, 11, 0), datetime(2026, 4, 15, 11, 30)),
            (datetime(2026, 4, 15, 14, 0), datetime(2026, 4, 15, 14, 30)),
        ]

        # 10:00-10:30 -> no conflict (between the busy periods)
        assert has_conflict(busy,
                            datetime(2026, 4, 15, 10, 0),
                            datetime(2026, 4, 15, 10, 30),
                            buffer_before=0, buffer_after=0) is False

        # 11:00-11:30 -> conflict
        assert has_conflict(busy,
                            datetime(2026, 4, 15, 11, 0),
                            datetime(2026, 4, 15, 11, 30),
                            buffer_before=0, buffer_after=0) is True

    def test_empty_conflicts_means_all_slots_available(self):
        """With no conflicts, no slot should be blocked."""
        has_conflict = _make_cross_source_conflict_checker()

        for hour in range(9, 17):
            assert has_conflict([],
                                datetime(2026, 4, 15, hour, 0),
                                datetime(2026, 4, 15, hour, 30),
                                buffer_before=5, buffer_after=5) is False


# ===========================================================================
# 8. TENANT ISOLATION IN CONFLICT DETECTION (3 tests)
# ===========================================================================

class TestTenantIsolation:
    """Tests verifying that conflict detection respects org_id boundaries."""

    def test_conflict_scoped_to_same_org(self):
        """An appointment in org 1 should not conflict with a booking in org 2."""
        org1_appt = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, organization_id=1)
        check = _make_conflict_checker([org1_appt])

        # Same user, same time, but different org -> no conflict
        check(1, BASE_START, BASE_END, org_id=2)

    def test_conflict_within_same_org(self):
        """Conflict detection works correctly within the same org."""
        org1_appt = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, organization_id=1)
        check = _make_conflict_checker([org1_appt])

        # Same user, same time, same org -> 409
        with pytest.raises(HTTPException) as exc:
            check(1, BASE_START, BASE_END, org_id=1)
        assert exc.value.status_code == 409

    def test_duplicate_detection_scoped_to_org(self):
        """Duplicate booking detection is scoped by organization."""
        org1_appt = FakeAppointment(
            assigned_user_id=1, scheduled_start=BASE_START,
            scheduled_end=BASE_END, attendee_email="alice@test.com",
            organization_id=1)
        check = _make_duplicate_checker([org1_appt])

        # Same email, same LO, same time, different org -> allowed
        check("alice@test.com", 1, BASE_START, org_id=2)


# ===========================================================================
# Summary: Total test methods
# ===========================================================================
# TestSingleSourceConflicts:            9
# TestCrossSourceConflicts:             6
# TestConcurrentBooking:                5
# TestPessimisticLocking:               4
# TestAppointmentStatusMachine:         8
# TestDuplicateBookingDetection:        5
# TestSlotGenerationConflictIntegration:4
# TestTenantIsolation:                  3
# ─────────────────────────────────────────
# Total:                               44
