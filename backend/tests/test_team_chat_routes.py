"""Test team chat API endpoints."""
import uuid
import pytest


def test_send_message_returns_201(authenticated_client, db_session):
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(organization_id=1, first_name="Route", last_name="Test",
                email="rt@test.com", owner_id=1)
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()

    resp = authenticated_client.post(
        f"/api/v1/clients/{cf.id}/team-chat/messages",
        json={"body": "Hello from test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "Hello from test"
    assert data["author"]["kind"] == "human"


def test_list_messages_returns_200(authenticated_client, db_session):
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(organization_id=1, first_name="List", last_name="Test",
                email="lt@test.com", owner_id=1)
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()

    resp = authenticated_client.get(
        f"/api/v1/clients/{cf.id}/team-chat/messages"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
