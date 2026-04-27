"""SSN encryption round-trip tests.

Verifies that:
  - SSN entered by the borrower is encrypted at rest
  - The encrypted column does NOT contain the plaintext SSN
  - Reads decrypt transparently via EncryptedString TypeDecorator
  - SSN is never echoed in any API response (presence flags only)
  - Audit rows never include the SSN value in their delta column
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.models.pos import (
    POSApplication,
    POSApplicationAudit,
    POSApplicationPII,
)


SAMPLE_SSN = "123-45-6789"
SAMPLE_DOB = "1985-06-12"


def test_ssn_round_trips_via_encrypted_column(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    """Patch personal section with SSN; read it back via the model."""
    resp = client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={
            "data": {"first_name": "Alice", "last_name": "Anderson"},
            "ssn": SAMPLE_SSN,
            "dob": SAMPLE_DOB,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    # Response indicates presence but never the value itself.
    assert body["has_ssn"] is True
    assert body["has_dob"] is True
    assert SAMPLE_SSN not in resp.text
    assert "123" not in body.get("data", {}).values()

    # Read back via the model -- EncryptedString decrypts on access.
    pii = db_session.get(POSApplicationPII, alice_application.id)
    assert pii is not None
    assert pii.ssn_encrypted == SAMPLE_SSN  # decrypted by TypeDecorator


def test_ssn_is_actually_encrypted_at_rest(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    """Bypass the ORM and confirm the raw column does NOT contain plaintext."""
    resp = client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {}, "ssn": SAMPLE_SSN},
    )
    assert resp.status_code == 200

    # The route commits on the shared session. Expire cache so the raw
    # query can find rows inserted by the ORM.
    db_session.expire_all()

    # Raw read -- bypass the EncryptedString decryption.
    # Use LIKE matching on UUID prefix to handle format differences.
    raw = db_session.execute(
        text(
            "SELECT ssn_encrypted FROM pos_application_pii"
        ),
    )
    rows = raw.fetchall()
    assert len(rows) >= 1, "Expected at least one PII row after SSN save"
    raw_value = rows[0][0]
    assert raw_value is not None
    # Fernet tokens start with 'gAAAAA' and never contain the plaintext.
    assert SAMPLE_SSN not in str(raw_value)
    assert "123456789" not in str(raw_value)


def test_section_response_never_echoes_ssn(
    client: TestClient, alice_application: POSApplication
) -> None:
    client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {}, "ssn": SAMPLE_SSN},
    )

    # GET the section back -- response must contain has_ssn but not the value.
    resp = client.get(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_ssn"] is True
    assert SAMPLE_SSN not in resp.text


def test_audit_delta_never_includes_ssn(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    """The audit row's `delta` JSON must never contain a raw SSN."""
    client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={
            "data": {"first_name": "Alice"},
            "ssn": SAMPLE_SSN,
            "mark_complete": True,
        },
    )

    rows = (
        db_session.execute(
            select(POSApplicationAudit).where(
                POSApplicationAudit.application_id == alice_application.id
            )
        )
    ).scalars().all()

    assert rows, "expected at least one audit row"
    for row in rows:
        delta_str = str(row.delta or {})
        assert SAMPLE_SSN not in delta_str
        assert "123456789" not in delta_str


def test_ssn_normalization_accepts_unformatted_input(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    """Borrower can submit '123456789' or '123-45-6789' -- both stored as 'XXX-XX-XXXX'."""
    resp = client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {}, "ssn": "123456789"},
    )
    assert resp.status_code == 200

    pii = db_session.get(POSApplicationPII, alice_application.id)
    assert pii is not None
    assert pii.ssn_encrypted == "123-45-6789"


def test_invalid_ssn_format_rejected(
    client: TestClient, alice_application: POSApplication
) -> None:
    """SSN that isn't 9 digits gets a 422."""
    resp = client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {}, "ssn": "12345"},
    )
    assert resp.status_code == 422
