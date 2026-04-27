"""Calendar route tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from database.models.pos import POSApplication


# ---------------------------------------------------------------------------
# Available slots
# ---------------------------------------------------------------------------


def test_get_available_slots_returns_grouped_by_date(
    client: TestClient,
    alice_application_with_loan: POSApplication,
) -> None:
    """Slots come back grouped by ISO date string with the recommended slot flagged."""
    # Stub out resolve_loan_officer to return a fake LO.
    fake_lo = type(
        "_LO", (), {"id": 200, "first_name": "Sarah", "last_name": "Reyes", "nmls_id": "2014872"}
    )()
    fake_link = type("_Link", (), {"slug": "sarah", "id": 1})()

    with patch(
        "services.pos.calendar_service.CalendarService.resolve_loan_officer",
        new=MagicMock(return_value=fake_lo),
    ), patch(
        "services.pos.calendar_service.CalendarService.get_booking_link_for_lo",
        new=MagicMock(return_value=fake_link),
    ):
        start = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
        resp = client.get(
            f"/api/v1/pos/calendar/applications/{alice_application_with_loan.id}/available-slots",
            params={
                "start_date": start,
                "end_date": end,
                "duration_minutes": 30,
                "timezone": "America/New_York",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["loan_officer_user_id"] == 200
    assert body["loan_officer_name"] == "Sarah Reyes"
    assert isinstance(body["slots_by_date"], dict)
    # FakeSchedulerBridge returns 3 slots; at least one date should have >= 1.
    total = sum(len(v) for v in body["slots_by_date"].values())
    assert total >= 2


def test_date_range_too_wide_rejected(
    client: TestClient, alice_application_with_loan: POSApplication
) -> None:
    """Borrowers can't fetch >60 days at once (DDOS guard)."""
    start = "2026-01-01"
    end = "2026-12-31"
    resp = client.get(
        f"/api/v1/pos/calendar/applications/{alice_application_with_loan.id}/available-slots",
        params={"start_date": start, "end_date": end},
    )
    assert resp.status_code == 422


def test_no_assigned_lo_returns_409(
    client: TestClient, alice_application: POSApplication
) -> None:
    """An application without a linked loan has no assigned LO."""
    start = "2026-05-01"
    end = "2026-05-14"
    resp = client.get(
        f"/api/v1/pos/calendar/applications/{alice_application.id}/available-slots",
        params={"start_date": start, "end_date": end},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


def test_create_hold_round_trips_through_bridge(
    client: TestClient,
    fake_scheduler_bridge,
    alice_application_with_loan: POSApplication,
) -> None:
    fake_lo = type(
        "_LO", (), {"id": 200, "first_name": "Sarah", "last_name": "Reyes", "nmls_id": None}
    )()
    fake_link = type("_Link", (), {"slug": "sarah", "id": 1})()

    with patch(
        "services.pos.calendar_service.CalendarService.resolve_loan_officer",
        new=MagicMock(return_value=fake_lo),
    ), patch(
        "services.pos.calendar_service.CalendarService.get_booking_link_for_lo",
        new=MagicMock(return_value=fake_link),
    ):
        resp = client.post(
            "/api/v1/pos/calendar/holds",
            json={
                "application_id": str(alice_application_with_loan.id),
                "slot_start": "2026-05-01T15:00:00+00:00",
                "slot_end": "2026-05-01T15:30:00+00:00",
                "duration_minutes": 30,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hold_id"] == 9001
    assert "expires_at" in body
    assert len(fake_scheduler_bridge.holds_placed) == 1


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


def test_book_creates_appointment_with_loan_id(
    client: TestClient,
    fake_scheduler_bridge,
    alice_application_with_loan: POSApplication,
) -> None:
    """Booking sets Appointment.loan_id and audits the action."""
    # Pre-populate the personal section so attendee resolution succeeds.
    client.patch(
        f"/api/v1/pos/applications/{alice_application_with_loan.id}/sections/personal",
        json={
            "data": {
                "first_name": "Alice",
                "last_name": "Anderson",
                "email": "alice@example.com",
                "phone": "555-1234",
            }
        },
    )

    fake_lo = type(
        "_LO", (), {"id": 200, "first_name": "Sarah", "last_name": "Reyes", "nmls_id": "2014872"}
    )()
    fake_link = type(
        "_Link",
        (),
        {
            "slug": "sarah",
            "id": 1,
            "default_appointment_type_id": 7,
            "appointment_types": [],
        },
    )()

    with patch(
        "services.pos.calendar_service.CalendarService.resolve_loan_officer",
        new=MagicMock(return_value=fake_lo),
    ), patch(
        "services.pos.calendar_service.CalendarService.get_booking_link_for_lo",
        new=MagicMock(return_value=fake_link),
    ):
        resp = client.post(
            "/api/v1/pos/calendar/bookings",
            json={
                "application_id": str(alice_application_with_loan.id),
                "meeting_type": "application_review",
                "slot_start": "2026-05-01T15:00:00+00:00",
                "slot_end": "2026-05-01T15:30:00+00:00",
                "timezone": "America/New_York",
                "notes": "Looking forward to it",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["appointment_id"] == 5000
    assert body["loan_id"] == 42  # alice_application_with_loan.loan_id
    assert body["loan_officer_user_id"] == 200
    assert body["email_sent"] is True
    assert body["calendar_event_created"] is True

    # Bridge received the loan_id for downstream linking.
    assert fake_scheduler_bridge.bookings_made[0]["loan_id"] == 42


def test_book_requires_personal_section_completed(
    client: TestClient,
    alice_application_with_loan: POSApplication,
) -> None:
    """Without name/email in personal section, booking returns 409."""
    fake_lo = type("_LO", (), {"id": 200, "first_name": "Sarah", "last_name": "Reyes"})()
    fake_link = type(
        "_Link",
        (),
        {"slug": "sarah", "id": 1, "default_appointment_type_id": 7, "appointment_types": []},
    )()

    with patch(
        "services.pos.calendar_service.CalendarService.resolve_loan_officer",
        new=MagicMock(return_value=fake_lo),
    ), patch(
        "services.pos.calendar_service.CalendarService.get_booking_link_for_lo",
        new=MagicMock(return_value=fake_link),
    ):
        resp = client.post(
            "/api/v1/pos/calendar/bookings",
            json={
                "application_id": str(alice_application_with_loan.id),
                "meeting_type": "application_review",
                "slot_start": "2026-05-01T15:00:00+00:00",
                "slot_end": "2026-05-01T15:30:00+00:00",
                "timezone": "America/New_York",
            },
        )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_returns_404_for_unrelated_appointment(
    client: TestClient,
) -> None:
    """If no application of this borrower owns the appointment, return 404."""
    resp = client.request(
        "DELETE",
        "/api/v1/pos/calendar/bookings/999999",
        json={"reason": "testing"},
    )
    assert resp.status_code == 404
