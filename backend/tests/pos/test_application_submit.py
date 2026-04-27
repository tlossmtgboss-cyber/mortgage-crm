"""Submit transition tests -- the most consequential operation."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from database.models.pos import POSApplication, POSSectionKey


REQUIRED_CERTS = [
    "truth_certification",
    "esign_consent",
    "credit_authorization",
]


def _complete_all_sections(
    client: TestClient, application_id: str, *, skip: tuple[str, ...] = ()
) -> None:
    """Mark every required section complete for a clean submit."""
    for key in POSSectionKey.ORDERED:
        if key == POSSectionKey.REVIEW or key in skip:
            continue
        client.patch(
            f"/api/v1/pos/applications/{application_id}/sections/{key}",
            json={"data": {"placeholder": True}, "mark_complete": True},
        )


def test_submit_happy_path(
    client: TestClient, alice_application: POSApplication
) -> None:
    _complete_all_sections(client, str(alice_application.id))

    resp = client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": 5042,
            "acknowledged_certifications": REQUIRED_CERTS,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["submitted_appointment_id"] == 5042
    assert body["confirmation_number"].startswith("PRN-")
    assert len(body["next_steps"]) >= 3


def test_submit_blocked_when_sections_incomplete(
    client: TestClient, alice_application: POSApplication
) -> None:
    """Even with all certs, can't submit if a required section is incomplete."""
    _complete_all_sections(
        client, str(alice_application.id), skip=("declarations",)
    )

    resp = client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": REQUIRED_CERTS,
        },
    )
    assert resp.status_code == 409
    assert "declarations" in resp.text


def test_submit_blocked_without_certifications(
    client: TestClient, alice_application: POSApplication
) -> None:
    _complete_all_sections(client, str(alice_application.id))

    resp = client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": ["truth_certification"],  # only 1 of 3
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert "esign_consent" in body["detail"]
    assert "credit_authorization" in body["detail"]


def test_double_submit_blocked(
    client: TestClient, alice_application: POSApplication
) -> None:
    """Submitting twice returns 409, not 200."""
    _complete_all_sections(client, str(alice_application.id))

    first = client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": REQUIRED_CERTS,
        },
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": REQUIRED_CERTS,
        },
    )
    assert second.status_code == 409
    assert "already" in second.json()["detail"].lower()


def test_submit_emits_event_with_full_payload(
    client: TestClient,
    alice_application: POSApplication,
) -> None:
    """The POS_APPLICATION_SUBMITTED event carries the full payload for the
    canonical-store handler to consume."""
    _complete_all_sections(client, str(alice_application.id))

    with patch("services.pos.application_service.event_bus") as mock_bus:
        mock_bus.publish = AsyncMock()
        resp = client.post(
            f"/api/v1/pos/applications/{alice_application.id}/submit",
            json={
                "appointment_id": 7777,
                "acknowledged_certifications": REQUIRED_CERTS,
            },
        )
        assert resp.status_code == 200

        mock_bus.publish.assert_awaited_once()
        event = mock_bus.publish.await_args.args[0]
        # EventType comparison tolerant of string-Enum or extension shim.
        assert "pos.application.submitted" in str(event.type).lower() or str(
            event.type
        ).endswith("POS_APPLICATION_SUBMITTED")
        data = event.data
        assert data["application_id"] == str(alice_application.id)
        assert data["appointment_id"] == 7777
        assert "payload" in data
        assert "sections" in data["payload"]
        assert data["payload"]["version"] == "pos_1003_v1"


def test_submitted_application_blocks_section_writes(
    client: TestClient, alice_application: POSApplication
) -> None:
    """Once submitted, the borrower cannot edit section data."""
    _complete_all_sections(client, str(alice_application.id))
    client.post(
        f"/api/v1/pos/applications/{alice_application.id}/submit",
        json={
            "appointment_id": None,
            "acknowledged_certifications": REQUIRED_CERTS,
        },
    )

    resp = client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {"first_name": "Mallory"}},
    )
    assert resp.status_code == 409
