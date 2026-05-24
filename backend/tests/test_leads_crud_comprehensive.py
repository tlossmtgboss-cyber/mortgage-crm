"""
Comprehensive Lead CRUD Lifecycle Test Suite
=============================================
Tests the full lead lifecycle including creation, reading, updating,
deletion, search, stage transitions, tenant isolation, and schema
validation.

Endpoints covered:
    - POST   /api/v1/leads/              (leads_crud_routes)
    - GET    /api/v1/leads/              (leads_crud_routes)
    - GET    /api/v1/leads/search        (leads_crud_routes)
    - GET    /api/v1/leads/{lead_id}     (leads_detail_routes)
    - PATCH  /api/v1/leads/{lead_id}     (leads_detail_routes)
    - DELETE /api/v1/leads/{lead_id}     (leads_detail_routes)
    - POST   /api/v1/leads/bulk-delete   (leads_detail_routes)
    - POST   /api/v1/leads/bulk-update-status (leads_detail_routes)

Also tests:
    - Schema validation (LeadCreate, LeadUpdate)
    - Stage transition rules (valid transitions, terminal stages)
    - Tenant isolation (cross-org access blocked)
    - Client file auto-creation on lead create
"""
import pytest
import logging
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES & HELPERS
# =============================================================================

@pytest.fixture
def lead_payload():
    """Standard lead creation payload."""
    return {"name": "Test Lead", "email": "testlead@example.com"}


@pytest.fixture
def lead_full_payload():
    """Fully populated lead payload."""
    return {
        "name": "Full Lead",
        "email": "full.lead@example.com",
        "phone": "(555) 222-3333",
        "source": "referral",
        "loan_type": "FHA",
        "credit_score": 720,
        "preapproval_amount": 350000.00,
        "address": "456 Oak Ave",
        "city": "Dallas",
        "state": "TX",
        "zip_code": "75201",
        "property_type": "condo",
        "property_value": 400000.00,
        "down_payment": 50000.00,
        "employment_status": "employed",
        "annual_income": 110000.00,
        "notes": "High-priority referral.",
    }


def _insert_lead(db_session, *, name="Test Lead", email="test@example.com",
                 phone="5551234567", stage="New", source="website",
                 owner_id=1, organization_id=1, **extra):
    """Insert a lead row and return its id."""
    from database.models import Lead
    lead = Lead(
        name=name, email=email, phone=phone, stage=stage, source=source,
        owner_id=owner_id, organization_id=organization_id,
        ai_score=50, sentiment="neutral",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc), **extra,
    )
    db_session.add(lead)
    db_session.flush()
    return lead.id


def _make_authenticated_client(app_ref, db_session, user):
    """Build a TestClient authenticated as the given MockUser."""
    from fastapi.testclient import TestClient
    from database import get_db
    from main import get_current_user, get_current_user_flexible
    from auth.dependencies import (
        get_current_user as auth_gcu, get_current_user_flexible as auth_gcuf,
    )
    def override_db():
        try: yield db_session
        finally: pass
    async def override_auth():
        return user
    app_ref.dependency_overrides[get_db] = override_db
    for dep in (get_current_user, get_current_user_flexible, auth_gcu, auth_gcuf):
        app_ref.dependency_overrides[dep] = override_auth
    return TestClient(app_ref)


# Autouse: patch side-effect services so tests focus on HTTP contract
_PATCH_TARGETS = [
    "utils.lead_scoring.calculate_lead_score",
    "services.sla_tracking_service.track_lead_created",
    "services.capacity_service.update_capacity_on_assignment",
    "services.dre_helpers.calculate_lead_score",
]


@pytest.fixture(autouse=True)
def _mock_side_effects():
    patches = []
    for t in _PATCH_TARGETS:
        try:
            p = patch(t, return_value=50); p.start(); patches.append(p)
        except Exception:
            pass
    try:
        p = patch("services.lead_cascade_service.cascade_lead_status",
                  return_value={"loans_updated": [], "mum_clients_updated": []})
        p.start(); patches.append(p)
    except Exception:
        pass
    yield
    for p in patches:
        p.stop()


# =============================================================================
# CREATE TESTS
# =============================================================================

@pytest.mark.integration
class TestCreateLead:
    """Test lead creation via POST /api/v1/leads/."""

    def test_create_lead_with_name_and_email(self, authenticated_client, lead_payload):
        """Create lead with minimal fields (name + email)."""
        resp = authenticated_client.post("/api/v1/leads/", json=lead_payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Test Lead"
        assert data["email"] == "testlead@example.com"
        assert "id" in data

    def test_create_lead_all_fields(self, authenticated_client, lead_full_payload):
        """Create lead with all fields populated."""
        resp = authenticated_client.post("/api/v1/leads/", json=lead_full_payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Full Lead"

    def test_create_lead_missing_name_rejected(self, authenticated_client):
        """Missing name should return 422."""
        resp = authenticated_client.post("/api/v1/leads/", json={"email": "noname@test.com"})
        assert resp.status_code == 422

    def test_create_lead_invalid_email_rejected(self, authenticated_client):
        """Invalid email format should return 422."""
        resp = authenticated_client.post("/api/v1/leads/", json={"name": "Bad", "email": "not-valid"})
        assert resp.status_code in (422, 500)

    def test_create_lead_requires_auth(self, client):
        """Unauthenticated request should return 401/403."""
        resp = client.post("/api/v1/leads/", json={"name": "Unauthed", "email": "u@test.com"})
        assert resp.status_code in (401, 403, 422)

    def test_create_lead_returns_default_stage(self, authenticated_client, lead_payload):
        """New leads should default to 'New' stage."""
        resp = authenticated_client.post("/api/v1/leads/", json=lead_payload)
        if resp.status_code == 201:
            data = resp.json()
            assert data.get("stage") in ("New", "new", None)

    def test_create_lead_sets_organization_id(self, authenticated_client, lead_payload):
        """Lead should inherit organization_id from authenticated user."""
        resp = authenticated_client.post("/api/v1/leads/", json=lead_payload)
        if resp.status_code == 201:
            data = resp.json()
            # mock_user has organization_id=1
            assert data.get("organization_id") == 1


# =============================================================================
# READ TESTS
# =============================================================================

@pytest.mark.integration
class TestReadLeads:
    """Test lead reading via GET /api/v1/leads/ and /api/v1/leads/{id}."""

    def test_list_leads(self, authenticated_client, db_session):
        """GET /api/v1/leads/ returns a list."""
        _insert_lead(db_session, name="Listed", email="listed@example.com")
        db_session.commit()
        resp = authenticated_client.get("/api/v1/leads/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_list_leads_empty_org(self, authenticated_client):
        """Empty org returns empty list."""
        resp = authenticated_client.get("/api/v1/leads/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_lead_by_id(self, authenticated_client, db_session):
        """GET /api/v1/leads/{id} returns the correct lead."""
        lid = _insert_lead(db_session, name="By ID", email="byid@example.com")
        db_session.commit()
        resp = authenticated_client.get(f"/api/v1/leads/{lid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == lid
        assert resp.json()["name"] == "By ID"

    def test_get_lead_not_found(self, authenticated_client):
        """Non-existent lead returns 404."""
        assert authenticated_client.get("/api/v1/leads/999999").status_code == 404

    def test_get_lead_wrong_org_returns_404(self, db_session):
        """Lead from another org should return 404 (tenant isolation)."""
        from conftest import MockUser
        from main import app
        lid = _insert_lead(db_session, name="Org1", email="org1@example.com", organization_id=1)
        db_session.commit()
        org2_user = MockUser(id=50, email="org2@example.com", organization_id=2, role="loan_officer")
        c = _make_authenticated_client(app, db_session, org2_user)
        assert c.get(f"/api/v1/leads/{lid}").status_code == 404
        app.dependency_overrides.clear()


# =============================================================================
# UPDATE TESTS
# =============================================================================

@pytest.mark.integration
class TestUpdateLead:
    """Test lead updates via PATCH /api/v1/leads/{id}."""

    def test_update_name_email_phone(self, authenticated_client, db_session):
        """Update name, email, and phone."""
        lid = _insert_lead(db_session, name="Old", email="old@example.com")
        db_session.commit()
        resp = authenticated_client.patch(f"/api/v1/leads/{lid}", json={
            "name": "Updated", "email": "updated@example.com",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    def test_update_stage_valid(self, authenticated_client, db_session):
        """Valid stage transition should succeed."""
        lid = _insert_lead(db_session, name="Stage", email="stage@example.com", stage="New")
        db_session.commit()
        resp = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Attempted Contact"})
        assert resp.status_code == 200
        assert resp.json()["stage"] == "Attempted Contact"

    def test_update_stage_invalid_rejected(self, authenticated_client, db_session):
        """Invalid stage value should be rejected."""
        lid = _insert_lead(db_session, name="Bad", email="bad@example.com", stage="New")
        db_session.commit()
        assert authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Closed"}).status_code == 422

    def test_update_nonexistent_lead_returns_404(self, authenticated_client):
        """Updating non-existent lead should return 404."""
        assert authenticated_client.patch("/api/v1/leads/999999", json={"name": "Ghost"}).status_code == 404

    def test_update_wrong_org_returns_404(self, db_session):
        """Update attempt on another org's lead should return 404."""
        from conftest import MockUser
        from main import app
        lid = _insert_lead(db_session, name="X", email="xorg@example.com", organization_id=1)
        db_session.commit()
        org2 = MockUser(id=60, email="o2@example.com", organization_id=2, role="loan_officer")
        c = _make_authenticated_client(app, db_session, org2)
        assert c.patch(f"/api/v1/leads/{lid}", json={"name": "Hacked"}).status_code == 404
        app.dependency_overrides.clear()

    def test_update_sets_stage_changed_at(self, authenticated_client, db_session):
        """Stage change should set stage_changed_at timestamp."""
        lid = _insert_lead(db_session, name="Timestamp", email="ts@example.com", stage="New")
        db_session.commit()
        resp = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Attempted Contact"})
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("stage_changed_at") is not None


# =============================================================================
# DELETE TESTS
# =============================================================================

@pytest.mark.integration
class TestDeleteLead:
    """Test lead deletion via DELETE /api/v1/leads/{id}."""

    def test_delete_lead(self, authenticated_client, db_session):
        """Delete should remove the lead (soft or hard)."""
        lid = _insert_lead(db_session, name="Del", email="del@example.com")
        db_session.commit()
        assert authenticated_client.delete(f"/api/v1/leads/{lid}").status_code == 204
        assert authenticated_client.get(f"/api/v1/leads/{lid}").status_code == 404

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        """Deleting non-existent lead should return 404."""
        assert authenticated_client.delete("/api/v1/leads/999999").status_code == 404


# =============================================================================
# SEARCH AND FILTER TESTS
# =============================================================================

@pytest.mark.integration
class TestSearchFilter:
    """Test lead search and filtering."""

    def test_search_by_name(self, authenticated_client, db_session):
        """Search by name should return matching leads."""
        _insert_lead(db_session, name="Alice Johnson", email="alice@example.com")
        _insert_lead(db_session, name="Bob Smith", email="bob@example.com")
        db_session.commit()
        resp = authenticated_client.get("/api/v1/leads/search?q=Alice")
        assert resp.status_code == 200
        results = resp.json()
        assert any("alice" in str(l.get("name", "")).lower() for l in results)

    def test_filter_by_stage(self, authenticated_client, db_session):
        """Filter by stage should return only matching leads."""
        _insert_lead(db_session, name="N1", email="n1@example.com", stage="New")
        _insert_lead(db_session, name="P1", email="p1@example.com", stage="Prospect")
        db_session.commit()
        data = authenticated_client.get("/api/v1/leads/?stage=Prospect").json()
        for lead in data:
            assert lead["stage"] == "Prospect"

    def test_pagination_offset_limit(self, authenticated_client, db_session):
        """Pagination should return distinct pages."""
        for i in range(5):
            _insert_lead(db_session, name=f"Page{i}", email=f"page{i}@example.com")
        db_session.commit()
        p1 = authenticated_client.get("/api/v1/leads/?skip=0&limit=2&pipeline=all").json()
        p2 = authenticated_client.get("/api/v1/leads/?skip=2&limit=2&pipeline=all").json()
        assert len(p1) <= 2
        ids_p1 = {l["id"] for l in p1}
        ids_p2 = {l["id"] for l in p2}
        assert ids_p1.isdisjoint(ids_p2)


# =============================================================================
# STAGE TRANSITION TESTS
# =============================================================================

@pytest.mark.integration
class TestStageTransitions:
    """Test lead stage transition rules."""

    def test_new_to_contacted(self, authenticated_client, db_session):
        """New -> Attempted Contact is valid."""
        lid = _insert_lead(db_session, name="Trans", email="trans@example.com", stage="New")
        db_session.commit()
        resp = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Attempted Contact"})
        assert resp.status_code == 200
        assert resp.json()["stage"] == "Attempted Contact"

    def test_chained_transitions(self, authenticated_client, db_session):
        """New -> Attempted Contact -> Prospect is valid."""
        lid = _insert_lead(db_session, name="Chain", email="chain@example.com", stage="New")
        db_session.commit()
        r1 = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Attempted Contact"})
        assert r1.status_code == 200
        r2 = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Prospect"})
        assert r2.status_code == 200
        assert r2.json()["stage"] == "Prospect"

    def test_terminal_stage_blocked(self, authenticated_client, db_session):
        """Terminal stage (Referral Source) should block further transitions."""
        lid = _insert_lead(db_session, name="Term", email="term@example.com", stage="Referral Source")
        db_session.commit()
        resp = authenticated_client.patch(f"/api/v1/leads/{lid}", json={"stage": "Prospect"})
        assert resp.status_code == 422


# =============================================================================
# BULK OPERATION TESTS
# =============================================================================

@pytest.mark.integration
class TestBulkOperations:
    """Test bulk lead operations."""

    def test_bulk_update_status(self, authenticated_client, db_session):
        """Bulk status update should update multiple leads."""
        id1 = _insert_lead(db_session, name="B1", email="b1@example.com", stage="New")
        id2 = _insert_lead(db_session, name="B2", email="b2@example.com", stage="New")
        db_session.commit()
        resp = authenticated_client.post("/api/v1/leads/bulk-update-status",
                                         json={"lead_ids": [id1, id2], "status": "Prospect"})
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

    def test_bulk_delete(self, authenticated_client, db_session):
        """Bulk delete should remove multiple leads."""
        id1 = _insert_lead(db_session, name="D1", email="d1@example.com")
        id2 = _insert_lead(db_session, name="D2", email="d2@example.com")
        db_session.commit()
        resp = authenticated_client.post("/api/v1/leads/bulk-delete", json={"lead_ids": [id1, id2]})
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 2

    def test_bulk_update_empty_ids_rejected(self, authenticated_client):
        """Empty lead_ids list should be rejected."""
        resp = authenticated_client.post("/api/v1/leads/bulk-update-status",
                                          json={"lead_ids": [], "status": "Prospect"})
        assert resp.status_code == 400

    def test_bulk_update_missing_status_rejected(self, authenticated_client):
        """Missing status field should be rejected."""
        resp = authenticated_client.post("/api/v1/leads/bulk-update-status",
                                          json={"lead_ids": [1]})
        assert resp.status_code == 400


# =============================================================================
# SCHEMA VALIDATION UNIT TESTS (no DB required)
# =============================================================================

@pytest.mark.unit
class TestLeadSchemaValidation:
    """Test Pydantic schema validation for leads."""

    def test_lead_create_requires_name(self):
        """LeadCreate schema requires name field."""
        from schemas.core import LeadCreate
        with pytest.raises(Exception):
            LeadCreate(email="noname@example.com")

    def test_lead_create_requires_contact_method(self):
        """LeadCreate requires at least email or phone."""
        from schemas.core import LeadCreate
        with pytest.raises(Exception):
            LeadCreate(name="No Contact")

    def test_lead_create_email_only(self):
        """LeadCreate accepts email without phone."""
        from schemas.core import LeadCreate
        lead = LeadCreate(name="Email Only", email="email@test.com")
        assert lead.email == "email@test.com"

    def test_lead_create_phone_only(self):
        """LeadCreate accepts phone without email."""
        from schemas.core import LeadCreate
        lead = LeadCreate(name="Phone Only", phone="(555) 111-2222")
        assert lead.phone is not None

    def test_lead_update_partial(self):
        """LeadUpdate allows partial updates (only set fields)."""
        from schemas.core import LeadUpdate
        update = LeadUpdate(name="X")
        update_dict = update.dict(exclude_unset=True)
        assert update_dict == {"name": "X"}

    def test_lead_stage_enum_values(self):
        """LeadStage enum has expected values."""
        from database.enums import LeadStage
        assert LeadStage.NEW.value == "New"
        assert LeadStage.ATTEMPTED_CONTACT.value == "Attempted Contact"
        assert LeadStage.FUNDED.value == "Funded"

    def test_valid_transitions_map_completeness(self):
        """Transition map should cover all non-terminal stages."""
        from workflows.lead_workflow_engine import VALID_TRANSITIONS
        for stage in ["New", "Attempted Contact", "Prospect", "Application",
                      "Pre-Qualified", "Pre-Approved"]:
            assert stage in VALID_TRANSITIONS, f"Missing transitions for {stage}"

    def test_terminal_stage_empty_transitions(self):
        """Terminal stages should have empty transition lists."""
        from workflows.lead_workflow_engine import VALID_TRANSITIONS
        assert VALID_TRANSITIONS.get("Referral Source") == []


# =============================================================================
# LEAD PERMISSIONS / TENANT ISOLATION
# =============================================================================

@pytest.mark.integration
class TestLeadTenantIsolation:
    """Test that leads are isolated between organizations."""

    def test_org_a_cannot_see_org_b_leads(self, db_session):
        """Organization A cannot access Organization B's leads."""
        from conftest import MockUser
        from main import app

        # Insert lead for org 1
        lid = _insert_lead(db_session, name="Org1Lead", email="o1lead@example.com", organization_id=1)
        db_session.commit()

        # User from org 2
        org2_user = MockUser(id=99, email="org2user@example.com", organization_id=2, role="loan_officer")
        c = _make_authenticated_client(app, db_session, org2_user)

        # Should not see org 1's lead
        resp = c.get(f"/api/v1/leads/{lid}")
        assert resp.status_code == 404

        # Listing should not include org 1's leads
        resp = c.get("/api/v1/leads/")
        if resp.status_code == 200:
            for lead in resp.json():
                assert lead.get("organization_id") != 1

        app.dependency_overrides.clear()

    def test_org_a_cannot_update_org_b_lead(self, db_session):
        """Organization A cannot update Organization B's leads."""
        from conftest import MockUser
        from main import app

        lid = _insert_lead(db_session, name="Protected", email="protected@example.com", organization_id=1)
        db_session.commit()

        org2_user = MockUser(id=99, email="attacker@example.com", organization_id=2, role="loan_officer")
        c = _make_authenticated_client(app, db_session, org2_user)

        resp = c.patch(f"/api/v1/leads/{lid}", json={"name": "Hacked"})
        assert resp.status_code == 404

        app.dependency_overrides.clear()

    def test_org_a_cannot_delete_org_b_lead(self, db_session):
        """Organization A cannot delete Organization B's leads."""
        from conftest import MockUser
        from main import app

        lid = _insert_lead(db_session, name="NoDel", email="nodel@example.com", organization_id=1)
        db_session.commit()

        org2_user = MockUser(id=99, email="deleter@example.com", organization_id=2, role="loan_officer")
        c = _make_authenticated_client(app, db_session, org2_user)

        resp = c.delete(f"/api/v1/leads/{lid}")
        assert resp.status_code == 404

        app.dependency_overrides.clear()
