"""Test ensure_client_file — the hook called on every lead creation path."""
import pytest
from services.client_file_service import ensure_client_file


def test_ensure_client_file_creates_new(db_session):
    from database.models import Lead
    lead = Lead(
        organization_id=1,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="+15551234567",
        source="website",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()

    cf = ensure_client_file(db_session, lead)

    assert cf is not None
    assert cf.lead_id == lead.id
    assert cf.first_name == "Jane"
    assert cf.last_name == "Doe"
    assert cf.primary_email == "jane@example.com"
    assert cf.organization_id == 1
    assert cf.lifecycle_stage == "new_lead"
    assert cf.assigned_loan_officer_id == 1


def test_ensure_client_file_is_idempotent(db_session):
    from database.models import Lead
    lead = Lead(
        organization_id=1,
        first_name="Bob",
        last_name="Smith",
        email="bob@example.com",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()

    cf1 = ensure_client_file(db_session, lead)
    cf2 = ensure_client_file(db_session, lead)

    assert cf1.id == cf2.id
