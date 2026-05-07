"""
IDOR (Insecure Direct Object Reference) Protection Test Suite

Systematic tests verifying that multi-tenant isolation prevents users from
one organization from accessing, modifying, or deleting resources belonging
to another organization.

Covers:
  - Leads: GET, PATCH, DELETE cross-org
  - Loans: GET, PATCH, DELETE cross-org
  - Documents: GET cross-org
  - Bulk operations: bulk-delete cross-org

Uses the authenticated_client pattern from conftest.py with two distinct
mock users from different organizations. Resources are created directly
in the test DB session and scoped to org_A. Requests are made by org_B
user, which must receive 404 (not 200/403) — IDOR prevention means the
resource simply "does not exist" from the attacker's perspective.
"""

import os
import sys
import pytest
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


# =============================================================================
# Fixtures: Two users from different organizations
# =============================================================================

ORG_A_ID = 100
ORG_B_ID = 200


class MockUserOrgA:
    """User belonging to organization A."""
    def __init__(self):
        self.id = 10
        self.email = "alice@org-a.com"
        self.organization_id = ORG_A_ID
        self.role = "loan_officer"
        self.permission_role = "sales"
        self.is_active = True


class MockUserOrgB:
    """User belonging to organization B (the attacker)."""
    def __init__(self):
        self.id = 20
        self.email = "bob@org-b.com"
        self.organization_id = ORG_B_ID
        self.role = "loan_officer"
        self.permission_role = "sales"
        self.is_active = True


@pytest.fixture
def user_org_a():
    return MockUserOrgA()


@pytest.fixture
def user_org_b():
    return MockUserOrgB()


def _make_authenticated_client(app, db_session, mock_user):
    """Build a TestClient with auth overrides for the given mock user."""
    from fastapi.testclient import TestClient
    from database import get_db
    from main import get_current_user, get_current_user_flexible
    from auth.dependencies import (
        get_current_user as auth_dep_gcu,
        get_current_user_flexible as auth_dep_gcuf,
    )

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_current_user():
        return mock_user

    async def override_get_current_user_flexible():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_flexible] = override_get_current_user_flexible
    app.dependency_overrides[auth_dep_gcu] = override_get_current_user
    app.dependency_overrides[auth_dep_gcuf] = override_get_current_user_flexible

    return TestClient(app)


@pytest.fixture
def client_org_a(db_session, user_org_a):
    """Authenticated client for org A user."""
    from main import app
    client = _make_authenticated_client(app, db_session, user_org_a)
    with client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_org_b(db_session, user_org_b):
    """Authenticated client for org B user (the attacker)."""
    from main import app
    client = _make_authenticated_client(app, db_session, user_org_b)
    with client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# Helper: Create resources scoped to org A directly in DB
# =============================================================================

@pytest.fixture
def lead_in_org_a(db_session, user_org_a):
    """Create a lead belonging to org A."""
    from database.models import Lead
    lead = Lead(
        organization_id=ORG_A_ID,
        first_name="OrgA",
        last_name="Lead",
        email="orga-lead@example.com",
        owner_id=user_org_a.id,
        stage="New",
    )
    db_session.add(lead)
    db_session.flush()
    return lead


@pytest.fixture
def loan_in_org_a(db_session, user_org_a, lead_in_org_a):
    """Create a loan belonging to org A."""
    from database.models import Loan
    loan = Loan(
        organization_id=ORG_A_ID,
        loan_officer_id=user_org_a.id,
        borrower_name="OrgA Borrower",
        loan_amount=400000,
        stage="APPLICATION",
        lead_id=lead_in_org_a.id,
    )
    db_session.add(loan)
    db_session.flush()
    return loan


@pytest.fixture
def document_in_org_a(db_session, user_org_a, lead_in_org_a, loan_in_org_a):
    """Create a document belonging to org A."""
    from database.models import Document
    doc = Document(
        organization_id=ORG_A_ID,
        borrower_id=lead_in_org_a.id,
        loan_id=loan_in_org_a.id,
        doc_type="PAY_STUB",
        filename="paystub.pdf",
        file_location="/test/paystub.pdf",
        source="MANUAL_UPLOAD",
        uploaded_by_user_id=user_org_a.id,
    )
    db_session.add(doc)
    db_session.flush()
    return doc


# =============================================================================
# 1. Lead IDOR Tests
# =============================================================================

@pytest.mark.unit
class TestLeadIDOR:
    """Verify org B user cannot access org A leads."""

    def test_org_b_cannot_get_org_a_lead(self, client_org_b, lead_in_org_a):
        """GET /api/v1/leads/{id} for a lead in another org must return 404."""
        resp = client_org_b.get(f"/api/v1/leads/{lead_in_org_a.id}")
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org lead access, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_cannot_update_org_a_lead(self, client_org_b, lead_in_org_a):
        """PATCH /api/v1/leads/{id} for a lead in another org must return 404."""
        resp = client_org_b.patch(
            f"/api/v1/leads/{lead_in_org_a.id}",
            json={"first_name": "Hacked"},
        )
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org lead update, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_cannot_delete_org_a_lead(self, client_org_b, lead_in_org_a):
        """DELETE /api/v1/leads/{id} for a lead in another org must return 404."""
        resp = client_org_b.delete(f"/api/v1/leads/{lead_in_org_a.id}")
        # 404 is expected; 204 would mean the lead was actually deleted (IDOR vuln)
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org lead delete, got {resp.status_code}: {resp.text}"
        )

    def test_org_a_can_access_own_lead(self, client_org_a, lead_in_org_a):
        """Sanity check: org A user CAN access their own lead."""
        resp = client_org_a.get(f"/api/v1/leads/{lead_in_org_a.id}")
        assert resp.status_code == 200, (
            f"Expected 200 for same-org lead access, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_list_does_not_include_org_a_leads(self, client_org_b, lead_in_org_a):
        """GET /api/v1/leads/ should not return leads from other orgs."""
        resp = client_org_b.get("/api/v1/leads/")
        assert resp.status_code == 200
        data = resp.json()
        # data may be a list or wrapped in a dict
        leads = data if isinstance(data, list) else data.get("data", data.get("leads", []))
        if isinstance(leads, list):
            lead_ids = [l.get("id") for l in leads if isinstance(l, dict)]
            assert lead_in_org_a.id not in lead_ids, (
                f"Org B listing includes org A lead {lead_in_org_a.id} — IDOR vulnerability"
            )

    def test_org_b_bulk_delete_cannot_delete_org_a_leads(
        self, client_org_b, lead_in_org_a, db_session
    ):
        """Bulk delete with org A lead IDs should not delete them when called by org B."""
        from database.models import Lead
        lead_id = lead_in_org_a.id

        resp = client_org_b.request(
            "DELETE",
            "/api/v1/leads/bulk-delete",
            json={"lead_ids": [lead_id]},
        )
        # The endpoint may return 200 with 0 deleted, or 404, or even 403
        # The key assertion: the lead must still exist in the DB
        db_session.expire_all()
        still_exists = db_session.query(Lead).filter(Lead.id == lead_id).first()
        assert still_exists is not None, (
            f"Lead {lead_id} was deleted by org B user — IDOR vulnerability in bulk-delete"
        )


# =============================================================================
# 2. Loan IDOR Tests
# =============================================================================

@pytest.mark.unit
class TestLoanIDOR:
    """Verify org B user cannot access org A loans."""

    def test_org_b_cannot_get_org_a_loan(self, client_org_b, loan_in_org_a):
        """GET /api/v1/loans/{id} for a loan in another org must return 404."""
        resp = client_org_b.get(f"/api/v1/loans/{loan_in_org_a.id}")
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org loan access, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_cannot_update_org_a_loan(self, client_org_b, loan_in_org_a):
        """PATCH /api/v1/loans/{id} for a loan in another org must return 404."""
        resp = client_org_b.patch(
            f"/api/v1/loans/{loan_in_org_a.id}",
            json={"borrower_name": "Hacked Borrower"},
        )
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org loan update, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_cannot_delete_org_a_loan(self, client_org_b, loan_in_org_a):
        """DELETE /api/v1/loans/{id} for a loan in another org must return 404."""
        resp = client_org_b.delete(f"/api/v1/loans/{loan_in_org_a.id}")
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org loan delete, got {resp.status_code}: {resp.text}"
        )

    def test_org_a_can_access_own_loan(self, client_org_a, loan_in_org_a):
        """Sanity check: org A user CAN access their own loan."""
        resp = client_org_a.get(f"/api/v1/loans/{loan_in_org_a.id}")
        assert resp.status_code == 200, (
            f"Expected 200 for same-org loan access, got {resp.status_code}: {resp.text}"
        )

    def test_org_b_list_does_not_include_org_a_loans(self, client_org_b, loan_in_org_a):
        """GET /api/v1/loans/ should not return loans from other orgs."""
        resp = client_org_b.get("/api/v1/loans/")
        assert resp.status_code == 200
        data = resp.json()
        loans = data if isinstance(data, list) else data.get("data", data.get("loans", []))
        if isinstance(loans, list):
            loan_ids = [l.get("id") for l in loans if isinstance(l, dict)]
            assert loan_in_org_a.id not in loan_ids, (
                f"Org B listing includes org A loan {loan_in_org_a.id} — IDOR vulnerability"
            )


# =============================================================================
# 3. Document IDOR Tests
# =============================================================================

@pytest.mark.unit
class TestDocumentIDOR:
    """Verify org B user cannot access org A documents."""

    def test_org_b_cannot_get_org_a_lead_documents(
        self, client_org_b, lead_in_org_a, document_in_org_a
    ):
        """GET /api/v1/leads/{id}/documents for a lead in another org must return 404."""
        resp = client_org_b.get(f"/api/v1/leads/{lead_in_org_a.id}/documents")
        # The lead itself should not be visible to org B, so 404
        assert resp.status_code == 404, (
            f"Expected 404 for cross-org document access via lead, "
            f"got {resp.status_code}: {resp.text}"
        )

    def test_org_a_can_access_own_documents(
        self, client_org_a, lead_in_org_a, document_in_org_a
    ):
        """Sanity check: org A user CAN access their own lead's documents."""
        resp = client_org_a.get(f"/api/v1/leads/{lead_in_org_a.id}/documents")
        assert resp.status_code == 200, (
            f"Expected 200 for same-org document access, got {resp.status_code}: {resp.text}"
        )


# =============================================================================
# 4. Cross-org resource mutation verification
# =============================================================================

@pytest.mark.unit
class TestCrossOrgMutationProtection:
    """Verify that even if an attacker guesses a valid resource ID,
    mutations are blocked by org scoping."""

    def test_lead_update_does_not_modify_cross_org(
        self, client_org_b, lead_in_org_a, db_session
    ):
        """PATCH to another org's lead must not change the record."""
        from database.models import Lead
        original_name = lead_in_org_a.first_name

        client_org_b.patch(
            f"/api/v1/leads/{lead_in_org_a.id}",
            json={"first_name": "HACKED"},
        )

        db_session.expire_all()
        lead = db_session.query(Lead).filter(Lead.id == lead_in_org_a.id).first()
        assert lead is not None
        assert lead.first_name == original_name, (
            f"Lead first_name was changed from '{original_name}' to '{lead.first_name}' "
            f"by cross-org request — IDOR mutation vulnerability"
        )

    def test_loan_update_does_not_modify_cross_org(
        self, client_org_b, loan_in_org_a, db_session
    ):
        """PATCH to another org's loan must not change the record."""
        from database.models import Loan
        original_name = loan_in_org_a.borrower_name

        client_org_b.patch(
            f"/api/v1/loans/{loan_in_org_a.id}",
            json={"borrower_name": "HACKED BORROWER"},
        )

        db_session.expire_all()
        loan = db_session.query(Loan).filter(Loan.id == loan_in_org_a.id).first()
        assert loan is not None
        assert loan.borrower_name == original_name, (
            f"Loan borrower_name was changed from '{original_name}' to '{loan.borrower_name}' "
            f"by cross-org request — IDOR mutation vulnerability"
        )

    def test_lead_delete_does_not_remove_cross_org(
        self, client_org_b, lead_in_org_a, db_session
    ):
        """DELETE of another org's lead must not remove the record."""
        from database.models import Lead
        lead_id = lead_in_org_a.id

        client_org_b.delete(f"/api/v1/leads/{lead_id}")

        db_session.expire_all()
        lead = db_session.query(Lead).filter(Lead.id == lead_id).first()
        assert lead is not None, (
            f"Lead {lead_id} was deleted by cross-org request — IDOR vulnerability"
        )
        # Also check it wasn't soft-deleted
        assert lead.deleted_at is None, (
            f"Lead {lead_id} was soft-deleted by cross-org request — IDOR vulnerability"
        )

    def test_loan_delete_does_not_remove_cross_org(
        self, client_org_b, loan_in_org_a, db_session
    ):
        """DELETE of another org's loan must not remove the record."""
        from database.models import Loan
        loan_id = loan_in_org_a.id

        client_org_b.delete(f"/api/v1/loans/{loan_id}")

        db_session.expire_all()
        loan = db_session.query(Loan).filter(Loan.id == loan_id).first()
        assert loan is not None, (
            f"Loan {loan_id} was deleted by cross-org request — IDOR vulnerability"
        )
