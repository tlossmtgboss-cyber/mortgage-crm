"""Test ClientFile and ClientFileCollaborator model definitions."""
import uuid
from database.models.client_file import ClientFile, ClientFileCollaborator


def test_client_file_has_uuid_pk():
    cf = ClientFile(
        organization_id=1,
        first_name="John",
        last_name="Doe",
        lifecycle_stage="new_lead",
    )
    assert cf.organization_id == 1
    assert cf.lifecycle_stage == "new_lead"


def test_client_file_collaborator_has_uuid_pk():
    collab = ClientFileCollaborator(
        organization_id=1,
        client_file_id=uuid.uuid4(),
        user_id=1,
        role="viewer",
    )
    assert collab.role == "viewer"
    assert collab.user_id == 1
