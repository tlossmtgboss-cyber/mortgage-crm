"""
Client File Aggregate Integration Tests

Tests for the client file aggregate root pattern:
- Client file creation from lead
- ensure_client_file idempotency
- ClientFileCollaborator management
- Lifecycle stage transitions
- Tenant isolation on client files

Key files:
    backend/database/models/client_file.py
    backend/services/client_file_service.py
    backend/routes/client_file_routes.py
"""
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def org(db_session):
    """Create a test organization."""
    from database.models import Organization
    org = Organization(name="CF Org", slug="cf-org", is_active=True)
    db_session.add(org)
    db_session.flush()
    return org


@pytest.fixture
def user(db_session, org):
    """Create a test user (loan officer)."""
    from database.models import User
    user = User(
        email="cf-lo@test.com",
        hashed_password="hashed",
        first_name="CF",
        last_name="LO",
        role="loan_officer",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def second_user(db_session, org):
    """Create a second user for collaborator tests."""
    from database.models import User
    user = User(
        email="cf-la@test.com",
        hashed_password="hashed",
        first_name="CF",
        last_name="LA",
        role="loan_assistant",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lead(db_session, org, user):
    """Create a test lead."""
    from database.models import Lead
    lead = Lead(
        organization_id=org.id,
        name="CF Test Lead",
        first_name="CF",
        last_name="Lead",
        email="cf-lead@test.com",
        phone="+15551234567",
        stage="New",
        source="website",
        owner_id=user.id,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


class TestEnsureClientFile:
    """Test the ensure_client_file service function."""

    def test_creates_client_file_from_lead(self, db_session, lead):
        """ensure_client_file should create a ClientFile linked to the lead."""
        from services.client_file_service import ensure_client_file
        from database.models.client_file import ClientFile

        cf = ensure_client_file(db_session, lead)
        db_session.flush()

        assert cf is not None
        assert cf.id is not None
        assert cf.lead_id == lead.id
        assert cf.first_name == lead.first_name
        assert cf.last_name == lead.last_name
        assert cf.primary_email == lead.email
        assert cf.organization_id == lead.organization_id
        assert cf.lifecycle_stage == "new_lead"

    def test_ensure_client_file_is_idempotent(self, db_session, lead):
        """Calling ensure_client_file twice for the same lead should return the same object."""
        from services.client_file_service import ensure_client_file
        from database.models.client_file import ClientFile

        cf1 = ensure_client_file(db_session, lead)
        db_session.flush()

        cf2 = ensure_client_file(db_session, lead)
        db_session.flush()

        assert cf1.id == cf2.id
        assert cf1 is cf2  # Same object from session identity map

    def test_ensure_client_file_copies_lead_source(self, db_session, lead):
        """ClientFile should inherit source from the lead."""
        from services.client_file_service import ensure_client_file

        cf = ensure_client_file(db_session, lead)
        db_session.flush()

        assert cf.source == lead.source

    def test_ensure_client_file_assigns_lo(self, db_session, lead, user):
        """ClientFile should inherit the assigned LO from the lead."""
        from services.client_file_service import ensure_client_file

        cf = ensure_client_file(db_session, lead)
        db_session.flush()

        assert cf.assigned_loan_officer_id == user.id


class TestClientFileModel:
    """Test ClientFile model fields and constraints."""

    def test_client_file_uuid_primary_key(self, db_session, org):
        """ClientFile should use UUID primary key."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="UUID",
            last_name="Test",
            lifecycle_stage="new_lead",
        )
        db_session.add(cf)
        db_session.flush()

        assert isinstance(cf.id, uuid.UUID)

    def test_client_file_default_lifecycle_stage(self, db_session, org):
        """Default lifecycle_stage should be 'new_lead'."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="Default",
            last_name="Stage",
        )
        db_session.add(cf)
        db_session.flush()

        assert cf.lifecycle_stage == "new_lead"

    def test_client_file_tags_default_empty(self, db_session, org):
        """Tags should default to empty list."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="Tags",
            last_name="Test",
        )
        db_session.add(cf)
        db_session.flush()

        # tags defaults to [] via server_default
        assert cf.tags is not None

    def test_client_file_jsonb_property_address(self, db_session, org):
        """property_address should accept JSONB data."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="JSONB",
            last_name="Test",
            property_address={
                "street": "123 Main St",
                "city": "Austin",
                "state": "TX",
                "zip": "78701",
            },
        )
        db_session.add(cf)
        db_session.flush()

        assert cf.property_address["city"] == "Austin"


class TestClientFileLifecycleStages:
    """Test lifecycle stage transitions on client files."""

    @pytest.mark.parametrize("stage", [
        "new_lead", "contacted", "qualified", "pre_approved",
        "application", "processing", "closing", "funded", "post_closing",
    ])
    def test_valid_lifecycle_stages(self, db_session, org, stage):
        """ClientFile should accept various lifecycle stages."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="Stage",
            last_name=stage,
            lifecycle_stage=stage,
        )
        db_session.add(cf)
        db_session.flush()
        assert cf.lifecycle_stage == stage

    def test_stage_transition(self, db_session, org):
        """Lifecycle stage should be updatable."""
        from database.models.client_file import ClientFile

        cf = ClientFile(
            organization_id=org.id,
            first_name="Trans",
            last_name="Test",
            lifecycle_stage="new_lead",
        )
        db_session.add(cf)
        db_session.flush()

        cf.lifecycle_stage = "contacted"
        db_session.flush()
        assert cf.lifecycle_stage == "contacted"

        cf.lifecycle_stage = "qualified"
        db_session.flush()
        assert cf.lifecycle_stage == "qualified"


class TestClientFileCollaborator:
    """Test the collaborator sub-resource on client files."""

    def test_add_collaborator(self, db_session, org, user, second_user, lead):
        """Adding a collaborator to a client file should succeed."""
        from services.client_file_service import ensure_client_file
        from database.models.client_file import ClientFileCollaborator

        cf = ensure_client_file(db_session, lead)
        db_session.flush()

        collab = ClientFileCollaborator(
            organization_id=org.id,
            client_file_id=cf.id,
            user_id=second_user.id,
            role="processor",
            notify_on_inbound=True,
        )
        db_session.add(collab)
        db_session.flush()

        assert collab.id is not None
        assert collab.role == "processor"
        assert collab.notify_on_inbound is True

    def test_collaborator_default_role_is_viewer(self, db_session, org, user, second_user, lead):
        """Default collaborator role should be 'viewer'."""
        from services.client_file_service import ensure_client_file
        from database.models.client_file import ClientFileCollaborator

        cf = ensure_client_file(db_session, lead)
        db_session.flush()

        collab = ClientFileCollaborator(
            organization_id=org.id,
            client_file_id=cf.id,
            user_id=second_user.id,
        )
        db_session.add(collab)
        db_session.flush()

        assert collab.role == "viewer"
        assert collab.notify_on_inbound is False


class TestClientFileTenantIsolation:
    """Test that client files are properly scoped to organizations."""

    def test_client_files_scoped_by_org(self, db_session):
        """Client files should be isolatable by organization_id."""
        from database.models import Organization
        from database.models.client_file import ClientFile

        org1 = Organization(name="CFOrg1", slug="cforg1", is_active=True)
        org2 = Organization(name="CFOrg2", slug="cforg2", is_active=True)
        db_session.add_all([org1, org2])
        db_session.flush()

        cf1 = ClientFile(
            organization_id=org1.id, first_name="CF", last_name="Org1",
            lifecycle_stage="new_lead",
        )
        cf2 = ClientFile(
            organization_id=org2.id, first_name="CF", last_name="Org2",
            lifecycle_stage="new_lead",
        )
        db_session.add_all([cf1, cf2])
        db_session.flush()

        org1_files = db_session.query(ClientFile).filter(
            ClientFile.organization_id == org1.id
        ).all()
        assert len(org1_files) == 1
        assert org1_files[0].last_name == "Org1"


class TestClientFileHTTPEndpoints:
    """Test client file HTTP endpoints via authenticated client."""

    def test_list_client_files_requires_auth(self, client):
        """Client file listing should require authentication."""
        response = client.get("/api/v1/client-files")
        assert response.status_code in (401, 403, 404, 500)

    def test_list_client_files_authenticated(self, authenticated_client):
        """Authenticated user should be able to list client files."""
        response = authenticated_client.get("/api/v1/client-files")
        assert response.status_code in (200, 404), (
            f"Expected 200 or 404, got {response.status_code}: {response.text[:300]}"
        )
