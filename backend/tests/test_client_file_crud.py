"""
Client File CRUD Tests

Tests the client file aggregate root operations:
- Creating a client file via ensure_client_file
- Getting a client file by ID
- _get_cf() orphan repair behavior
- _get_cf() 404 for nonexistent ID
- _get_or_create via ensure_client_file idempotency
- Client file API endpoints

Exercises real code from:
- services/client_file_service.py (ensure_client_file)
- routes/client_file_routes.py (_get_cf, API endpoints)
- database/models/client_file.py (ClientFile model)
"""

import pytest
import uuid
import logging
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# =============================================================================
# ensure_client_file (services/client_file_service.py)
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestEnsureClientFile:
    """Test the ensure_client_file service function."""

    def test_creates_client_file_for_new_lead(self, db_session):
        """ensure_client_file creates a new ClientFile linked to a lead."""
        from database.models import Lead
        from services.client_file_service import ensure_client_file

        lead = Lead(
            organization_id=1,
            first_name="Alice",
            last_name="Wonder",
            email="alice@example.com",
            phone="+15551234567",
            source="referral",
            owner_id=1,
        )
        db_session.add(lead)
        db_session.flush()

        cf = ensure_client_file(db_session, lead)

        assert cf is not None
        assert cf.lead_id == lead.id
        assert cf.first_name == "Alice"
        assert cf.last_name == "Wonder"
        assert cf.primary_email == "alice@example.com"
        assert cf.primary_phone == "+15551234567"
        assert cf.organization_id == 1
        assert cf.lifecycle_stage == "new_lead"
        assert cf.source == "referral"
        assert cf.assigned_loan_officer_id == 1
        assert cf.id is not None  # UUID assigned

    def test_is_idempotent_returns_same_cf(self, db_session):
        """Calling ensure_client_file twice returns the same ClientFile."""
        from database.models import Lead
        from services.client_file_service import ensure_client_file

        lead = Lead(
            organization_id=1,
            first_name="Bob",
            last_name="Builder",
            email="bob@example.com",
            owner_id=1,
        )
        db_session.add(lead)
        db_session.flush()

        cf1 = ensure_client_file(db_session, lead)
        cf2 = ensure_client_file(db_session, lead)

        assert cf1.id == cf2.id

    def test_handles_lead_without_phone(self, db_session):
        """ensure_client_file works when lead has no phone."""
        from database.models import Lead
        from services.client_file_service import ensure_client_file

        lead = Lead(
            organization_id=1,
            first_name="NoPhone",
            last_name="Person",
            email="nophone@example.com",
            owner_id=1,
        )
        db_session.add(lead)
        db_session.flush()

        cf = ensure_client_file(db_session, lead)
        assert cf.primary_phone is None
        assert cf.primary_email == "nophone@example.com"

    def test_handles_lead_without_source(self, db_session):
        """ensure_client_file works when lead has no source."""
        from database.models import Lead
        from services.client_file_service import ensure_client_file

        lead = Lead(
            organization_id=1,
            first_name="NoSource",
            last_name="Lead",
            email="nosource@example.com",
            owner_id=1,
        )
        db_session.add(lead)
        db_session.flush()

        cf = ensure_client_file(db_session, lead)
        assert cf.source is None


# =============================================================================
# _get_cf() (routes/client_file_routes.py)
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestGetCF:
    """Test the _get_cf() helper that enforces tenant boundaries."""

    def test_returns_client_file_for_matching_org(self, db_session):
        """_get_cf returns the client file when org_id matches."""
        from routes.client_file_routes import _get_cf
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=1,
            first_name="Match",
            last_name="Org",
            lifecycle_stage="new_lead",
        )
        db_session.add(cf)
        db_session.flush()

        result = _get_cf(db_session, cf.id, org_id=1)
        assert result.id == cf.id
        assert result.first_name == "Match"

    def test_raises_404_for_nonexistent_id(self, db_session):
        """_get_cf raises HTTPException(404) for a UUID that does not exist."""
        from routes.client_file_routes import _get_cf

        fake_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            _get_cf(db_session, fake_id, org_id=1)
        assert exc_info.value.status_code == 404

    def test_orphan_repair_reassigns_org(self, db_session):
        """_get_cf repairs orphaned records by updating org_id to requester's org."""
        from routes.client_file_routes import _get_cf
        from database.models.client_file import ClientFile

        # Create a client file with org_id=999 (orphan / wrong org)
        cf = ClientFile(
            organization_id=999,
            first_name="Orphan",
            last_name="Record",
            lifecycle_stage="new_lead",
        )
        db_session.add(cf)
        db_session.flush()
        cf_id = cf.id

        # Request from org_id=1 should trigger orphan repair
        result = _get_cf(db_session, cf_id, org_id=1)
        assert result is not None
        assert result.id == cf_id
        # After repair, org_id should be updated to 1
        assert result.organization_id == 1


# =============================================================================
# Client File API Endpoint
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestClientFileAPI:
    """Test the GET /api/v1/clients/{id} endpoint."""

    def test_get_client_file_success(self, authenticated_client, db_session):
        """GET /api/v1/clients/{id} returns client file data."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=1,
            first_name="API",
            last_name="Test",
            lifecycle_stage="new_lead",
            primary_email="apitest@example.com",
        )
        db_session.add(cf)
        db_session.flush()
        db_session.commit()

        resp = authenticated_client.get(f"/api/v1/clients/{cf.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["first_name"] == "API"
        assert data["last_name"] == "Test"
        assert data["lifecycle_stage"] == "new_lead"

    def test_get_client_file_not_found(self, authenticated_client):
        """GET /api/v1/clients/{id} returns 404 for nonexistent UUID."""
        fake_id = uuid.uuid4()
        resp = authenticated_client.get(f"/api/v1/clients/{fake_id}")
        assert resp.status_code == 404

    def test_get_client_file_invalid_uuid(self, authenticated_client):
        """GET /api/v1/clients/{id} returns 422 for invalid UUID format."""
        resp = authenticated_client.get("/api/v1/clients/not-a-uuid")
        assert resp.status_code == 422
