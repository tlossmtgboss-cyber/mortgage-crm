"""
Tests for GET /api/v1/dashboard/summary

Validates pipeline summary endpoint used by iOS BackgroundSyncManager and widgets.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from main import app
from database import get_db
from routes.auth_deps import require_auth, current_user_dep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockUser:
    def __init__(self, id=1, organization_id=1):
        self.id = id
        self.email = "lo@example.com"
        self.organization_id = organization_id
        self.role = "loan_officer"
        self.is_active = True


def _make_authed_client(db_session, org_id=1):
    """Build a TestClient with auth overrides scoped to a given org."""
    user = _MockUser(organization_id=org_id)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_require_auth():
        return user

    async def override_current_user_dep():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_require_auth
    app.dependency_overrides[current_user_dep] = override_current_user_dep
    return TestClient(app)


ENDPOINT = "/api/v1/dashboard/summary"

# Expected top-level camelCase keys in every response
_EXPECTED_KEYS = {
    "urgentTaskCount",
    "activeLoanCount",
    "rateAlertCount",
    "newLeadCount",
    "todayAppointmentCount",
    "pipelineSummary",
}

_PIPELINE_KEYS = {
    "applicationCount",
    "processingCount",
    "underwritingCount",
    "clearToCloseCount",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def authed_client(db_session):
    """Authenticated client for org_id=1."""
    client = _make_authed_client(db_session, org_id=1)
    with client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client(db_session):
    """Client with NO auth overrides — requests should be rejected."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def _seed_org(db_session, org_id=1, name="Test Org"):
    """Insert an Organization row if it doesn't already exist."""
    from database.models.core import Organization
    existing = db_session.get(Organization, org_id)
    if existing:
        return existing
    org = Organization(id=org_id, name=name)
    db_session.add(org)
    db_session.flush()
    return org


def _seed_loan(db_session, *, org_id, stage, loan_number, borrower="Test Borrower"):
    from database.models.lead_loan import Loan
    loan = Loan(
        organization_id=org_id,
        stage=stage,
        loan_number=loan_number,
        borrower_name=borrower,
        amount=400000,
    )
    db_session.add(loan)
    db_session.flush()
    return loan


def _seed_lead(db_session, *, org_id, created_at=None, name="Lead Test", email=None):
    from database.models.lead_loan import Lead
    lead = Lead(
        organization_id=org_id,
        name=name,
        email=email or f"{name.lower().replace(' ', '.')}@example.com",
        phone="+15550001234",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(lead)
    db_session.flush()
    return lead


def _seed_task(db_session, *, org_id, status="pending", due_date=None):
    from database.models.task import Task
    task = Task(
        organization_id=org_id,
        title="Follow up",
        status=status,
        due_date=due_date or datetime.now(timezone.utc),
    )
    db_session.add(task)
    db_session.flush()
    return task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDashboardSummaryAuth:
    """Authentication / authorization gate."""

    def test_dashboard_summary_requires_auth(self, unauthed_client):
        """GET /summary with no token should return 401 or 403."""
        resp = unauthed_client.get(ENDPOINT)
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {resp.status_code}"
        )


class TestDashboardSummaryShape:
    """Response structure validation."""

    def test_dashboard_summary_returns_camel_case(self, authed_client, db_session):
        """All top-level keys must be camelCase (consumed by Swift Codable)."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        resp = authed_client.get(ENDPOINT)
        assert resp.status_code == 200
        data = resp.json()

        assert set(data.keys()) == _EXPECTED_KEYS, (
            f"Top-level keys mismatch: {set(data.keys())}"
        )

        # No snake_case keys anywhere at top level
        for key in data:
            assert "_" not in key, f"Snake-case key found: {key}"

    def test_dashboard_summary_pipeline_summary_structure(self, authed_client, db_session):
        """pipelineSummary must contain the four expected count fields."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        resp = authed_client.get(ENDPOINT)
        assert resp.status_code == 200
        pipeline = resp.json()["pipelineSummary"]

        assert set(pipeline.keys()) == _PIPELINE_KEYS, (
            f"pipelineSummary keys mismatch: {set(pipeline.keys())}"
        )
        for key, val in pipeline.items():
            assert isinstance(val, int), f"{key} should be int, got {type(val)}"


class TestDashboardSummaryLoanCounts:
    """Active loan counting and stage breakdown."""

    def test_dashboard_summary_counts_active_loans(self, authed_client, db_session):
        """Loans in APPLICATION, PROCESSING, UNDERWRITING should be counted."""
        _seed_org(db_session, org_id=1)
        _seed_loan(db_session, org_id=1, stage="APPLICATION", loan_number="ACTIVE-001")
        _seed_loan(db_session, org_id=1, stage="PROCESSING", loan_number="ACTIVE-002")
        _seed_loan(db_session, org_id=1, stage="UNDERWRITING", loan_number="ACTIVE-003")
        _seed_loan(db_session, org_id=1, stage="CTC", loan_number="ACTIVE-004")
        db_session.commit()

        resp = authed_client.get(ENDPOINT)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 4
        pipeline = data["pipelineSummary"]
        assert pipeline["applicationCount"] == 1
        assert pipeline["processingCount"] == 1
        assert pipeline["underwritingCount"] == 1
        assert pipeline["clearToCloseCount"] == 1  # CTC is a closing stage

    def test_dashboard_summary_excludes_terminal_loans(self, authed_client, db_session):
        """FUNDED, CANCELLED, DENIED loans must NOT appear in activeLoanCount."""
        _seed_org(db_session, org_id=1)
        # Terminal
        _seed_loan(db_session, org_id=1, stage="FUNDED", loan_number="TERM-001")
        _seed_loan(db_session, org_id=1, stage="CANCELLED", loan_number="TERM-002")
        _seed_loan(db_session, org_id=1, stage="DENIED", loan_number="TERM-003")
        _seed_loan(db_session, org_id=1, stage="DEAD", loan_number="TERM-004")
        _seed_loan(db_session, org_id=1, stage="WITHDRAWN", loan_number="TERM-005")
        # One active for contrast
        _seed_loan(db_session, org_id=1, stage="APPLICATION", loan_number="ACTIVE-001")
        db_session.commit()

        resp = authed_client.get(ENDPOINT)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 1, (
            f"Only the APPLICATION loan should be active, got {data['activeLoanCount']}"
        )


class TestDashboardSummaryEdgeCases:
    """Empty org and tenant isolation."""

    def test_dashboard_summary_empty_org(self, authed_client, db_session):
        """An org with no loans/leads/tasks should return all zeros, not errors."""
        _seed_org(db_session, org_id=1)
        db_session.commit()

        resp = authed_client.get(ENDPOINT)
        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 0
        assert data["urgentTaskCount"] == 0
        assert data["newLeadCount"] == 0
        assert data["rateAlertCount"] == 0
        assert data["todayAppointmentCount"] == 0

        pipeline = data["pipelineSummary"]
        for key in _PIPELINE_KEYS:
            assert pipeline[key] == 0, f"{key} should be 0 for empty org"

    def test_dashboard_summary_org_scoping(self, db_session):
        """Data from org_id=2 must not appear when authenticated as org_id=1."""
        _seed_org(db_session, org_id=1, name="Org One")
        _seed_org(db_session, org_id=2, name="Org Two")

        # Seed data for org 2 only
        _seed_loan(db_session, org_id=2, stage="APPLICATION", loan_number="ORG2-001")
        _seed_loan(db_session, org_id=2, stage="PROCESSING", loan_number="ORG2-002")
        _seed_lead(db_session, org_id=2, name="Org2 Lead", email="org2lead@example.com")
        _seed_task(db_session, org_id=2, status="pending")
        db_session.commit()

        # Authenticate as org 1
        client = _make_authed_client(db_session, org_id=1)
        with client:
            resp = client.get(ENDPOINT)
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()

        assert data["activeLoanCount"] == 0, "Org 1 should see zero loans"
        assert data["newLeadCount"] == 0, "Org 1 should see zero leads"
        assert data["urgentTaskCount"] == 0, "Org 1 should see zero tasks"
