"""AI Q&A route tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.pos import POSAIQAMessage, POSApplication, POSStatus


# ---------------------------------------------------------------------------
# Ask happy path
# ---------------------------------------------------------------------------


def test_ask_returns_aria_response_with_sources(
    client: TestClient,
    fake_guidelines_agent,
    alice_application: POSApplication,
) -> None:
    resp = client.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "Can my parents send a gift for my down payment?",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "aria"
    assert "gift" in body["content"].lower()
    assert len(body["sources"]) == 2
    types = {s["type"] for s in body["sources"]}
    assert "guideline" in types
    assert "loan_file" in types
    assert body["confidence"] == "high"  # 2 sources -> high
    assert body["escalation_recommended"] is False
    # Agent received loan_context AND history from the database.
    assert fake_guidelines_agent.calls[0]["loan_context"]["application_id"] == str(
        alice_application.id
    )


def test_ask_persists_both_turns(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    client.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "What's my next step?",
        },
    )

    msgs = (
        db_session.execute(
            select(POSAIQAMessage)
            .where(POSAIQAMessage.application_id == alice_application.id)
            .order_by(POSAIQAMessage.created_at.asc())
        )
    ).scalars().all()

    assert len(msgs) == 2
    assert msgs[0].role == "borrower"
    assert msgs[0].content == "What's my next step?"
    assert msgs[1].role == "aria"
    assert msgs[1].confidence in {"high", "medium", "low"}


def test_escalation_path_marks_response(
    client: TestClient, alice_application: POSApplication
) -> None:
    """When the agent declines, Aria's response is flagged for LO follow-up."""
    resp = client.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "Please escalate this complex question",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == "escalate"
    assert body["escalation_recommended"] is True
    assert body["escalation_reason"] == "test_escalation"


# ---------------------------------------------------------------------------
# Submitted application -- Aria locked
# ---------------------------------------------------------------------------


def test_ask_blocked_after_submit(
    client: TestClient,
    db_session: Session,
    alice_application: POSApplication,
) -> None:
    """Submitted applications can't ask Aria -- they should message Sarah."""
    alice_application.status = POSStatus.SUBMITTED
    db_session.flush()

    resp = client.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "What now?",
        },
    )
    assert resp.status_code == 410
    assert "submitted" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_returns_messages_in_chronological_order(
    client: TestClient, alice_application: POSApplication
) -> None:
    for q in ("Question A", "Question B", "Question C"):
        client.post(
            "/api/v1/pos/ai-qa/ask",
            json={"application_id": str(alice_application.id), "message": q},
        )

    resp = client.get(
        f"/api/v1/pos/ai-qa/applications/{alice_application.id}/history"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 6  # 3 borrower + 3 aria

    # First three borrower messages preserve order.
    borrower_msgs = [m for m in body["messages"] if m["role"] == "borrower"]
    assert [m["content"] for m in borrower_msgs] == ["Question A", "Question B", "Question C"]


# ---------------------------------------------------------------------------
# Loan context retrieval
# ---------------------------------------------------------------------------


def test_loan_context_excludes_raw_pii(
    client: TestClient,
    fake_guidelines_agent,
    alice_application: POSApplication,
) -> None:
    """The agent must never receive raw SSN -- only presence flags."""
    # Save SSN to PII table.
    client.patch(
        f"/api/v1/pos/applications/{alice_application.id}/sections/personal",
        json={"data": {"first_name": "Alice"}, "ssn": "123-45-6789"},
    )

    client.post(
        "/api/v1/pos/ai-qa/ask",
        json={
            "application_id": str(alice_application.id),
            "message": "What documents do I owe?",
        },
    )

    loan_context = fake_guidelines_agent.calls[0]["loan_context"]
    flat = str(loan_context)
    assert "123-45-6789" not in flat
    assert "123456789" not in flat
    assert loan_context["presence_flags"]["has_ssn"] is True
