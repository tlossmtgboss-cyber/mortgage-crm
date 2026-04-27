"""Cross-borrower access denial.

This is the most important test file in the skill. If any of these tests
fail, a borrower could access another borrower's loan data -- which would be
a critical privacy and compliance violation (GLBA, ECOA, state privacy laws).

Every read and write endpoint must return 404 (not 403) when the
authenticated borrower's contact_id does not match the application's
contact_id. The status code is intentionally 404 -- returning 403 would leak
the existence of the resource.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from database.models.pos import POSApplication


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


def test_get_application_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    """Bob cannot fetch Alice's application by ID -- 404, not 403."""
    resp = client_as_bob.get(
        f"/api/v1/pos/applications/{alice_application.id}"
    )
    assert resp.status_code == 404
    # Body should not echo the application_id back, lest it confirm existence.
    body = resp.json()
    assert "Application not found" in body.get("detail", "")
    assert str(alice_application.id) not in body.get("detail", "")


def test_get_section_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    resp = client_as_bob.get(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal"
    )
    assert resp.status_code == 404


def test_get_qa_history_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    resp = client_as_bob.get(
        f"/api/v1/pos/ai-qa/applications/{alice_application.id}/history"
    )
    assert resp.status_code == 404


def test_get_assigned_lo_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application_with_loan: POSApplication
) -> None:
    resp = client_as_bob.get(
        f"/api/v1/pos/calendar/applications/{alice_application_with_loan.id}/assigned-lo"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Write endpoints -- section autosave
# ---------------------------------------------------------------------------


def test_patch_section_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    """Bob cannot modify Alice's section data."""
    resp = client_as_bob.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {"first_name": "Mallory"}, "mark_complete": False},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Write endpoints -- submit
# ---------------------------------------------------------------------------


def test_submit_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    """Bob cannot submit Alice's application."""
    resp = client_as_bob.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": [
                "truth_certification",
                "esign_consent",
                "credit_authorization",
            ],
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def test_book_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application_with_loan: POSApplication
) -> None:
    """Bob cannot book a meeting against Alice's application."""
    resp = client_as_bob.post(
        "/api/v1/pos/calendar/bookings",
        json={
            "application_id": str(alice_application_with_loan.id),
            "meeting_type": "application_review",
            "slot_start": "2026-05-01T15:00:00+00:00",
            "slot_end": "2026-05-01T15:30:00+00:00",
            "timezone": "America/New_York",
        },
    )
    assert resp.status_code == 404


def test_hold_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application_with_loan: POSApplication
) -> None:
    resp = client_as_bob.post(
        "/api/v1/pos/calendar/holds",
        json={
            "application_id": str(alice_application_with_loan.id),
            "slot_start": "2026-05-01T15:00:00+00:00",
            "slot_end": "2026-05-01T15:30:00+00:00",
            "duration_minutes": 30,
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AI Q&A
# ---------------------------------------------------------------------------


def test_ask_returns_404_for_wrong_borrower(
    client_as_bob: TestClient, alice_application: POSApplication
) -> None:
    """Bob cannot ask Aria about Alice's loan -- even framed innocuously."""
    resp = client_as_bob.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "What's my loan amount?",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Nonexistent application
# ---------------------------------------------------------------------------


def test_nonexistent_application_returns_404_same_as_wrong_borrower(
    client: TestClient,
) -> None:
    """Same response shape whether the app doesn't exist or belongs to someone else."""
    nonexistent = "11111111-1111-1111-1111-111111111111"
    resp = client.get(f"/api/v1/pos/applications/{nonexistent}")
    assert resp.status_code == 404
    assert resp.json().get("detail") == "Application not found"


# ---------------------------------------------------------------------------
# Read scope vs Write scope
# ---------------------------------------------------------------------------


def test_readonly_purl_token_blocked_from_writes(
    app, db_session, borrower_alice_readonly, alice_application: POSApplication
) -> None:
    """A PURL token with READ scope cannot patch sections.

    The middleware-level enforcement happens in `require_purl_write_scope`.
    This test ensures we depend on the right one in mutation routes.
    """
    from middleware.purl_auth import require_purl_token, require_purl_write_scope
    from fastapi import HTTPException

    app.dependency_overrides[require_purl_token] = lambda: borrower_alice_readonly

    # Make require_purl_write_scope raise like the real middleware would.
    def _reject_read_only():
        raise HTTPException(status_code=403, detail="Write scope required")

    app.dependency_overrides[require_purl_write_scope] = _reject_read_only

    with TestClient(app) as readonly_client:
        resp = readonly_client.patch(
            f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
            json={"data": {"first_name": "Alice"}},
        )
    assert resp.status_code == 403
