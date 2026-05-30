"""
Tests for the PURL-token-authenticated borrower dashboard endpoints.

Covers the deferred borrower-portal backend work:
  - GET /api/v1/portal/borrower/{loan_id}/dashboard
  - GET /api/v1/portal/borrower/{loan_id}/mum-dashboard
  - crm_loan_id / main_loan_id exposure in PURL workspace serialization

Security focus (the load-bearing part of the design):
  - PURL token is REQUIRED (401 without it).
  - The path loan_id is treated as a CRM loan id and validated against the
    token's (organization_id, workspace_id). A token for workspace A cannot
    read workspace B's loan even by guessing the CRM loan id -> 404, never a
    silent fall-through (IDOR guard).
  - Happy path returns home_value + risks for the borrower's own loan.

These tests seed real rows (PURLWorkspace, PURLLoan, PortalLoan) and override
require_purl_token to forge a PURLAuthContext bound to a specific workspace/org,
exactly mirroring what a verified purl_live_ token would yield.
"""

import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Mapper-registry shim (test environment only) — see explanation below.
#
# The workflow-SLA factory models (models/workflow_sla.py) declare
# relationship("Role"). String-based relationships resolve against the
# declarative registry of the *same* Base the factory is built on — db.Base.
# But the only `Role` mapped class (models/user_onboarding.py) is declared
# against a PRIVATE `declarative_base()` of its own, so it is NEVER registered
# in db.Base's registry. As a result, the first ORM query inside ANY request
# triggers SQLAlchemy configure_mappers(), which fails with
# "expression 'Role' failed to locate a name". This is a pre-existing,
# application-level defect (user_onboarding.py uses its own Base) that also
# breaks unrelated suites such as tests/test_leads_crud.py — it is NOT
# introduced by the portal feature under test here.
#
# To exercise the portal endpoints' real ORM path without altering application
# code outside this feature, register a minimal `Role` mapped to db.Base for
# the duration of the test process so configure_mappers() can resolve the
# string target. This is a test-only shim; it does not change any app module.
from db import Base as _DBBase
from sqlalchemy import Column as _Col, Integer as _Int, String as _Str

if "Role" not in _DBBase.registry._class_registry:
    class Role(_DBBase):  # type: ignore[misc]
        __tablename__ = "roles"
        __table_args__ = {"extend_existing": True}
        id = _Col(_Int, primary_key=True)
        name = _Col(_Str(100))

from main import app
from database import get_db
from middleware.purl_auth import require_purl_token, PURLAuthContext
from models.purl import TokenScope
from models.portal_models import LifecycleStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_A = 9001
ORG_B = 9002


def _ensure_org(db, org_id: int):
    """Insert a minimal organizations row if the table exists (FK target)."""
    try:
        db.execute(
            text(
                "INSERT INTO organizations (id, name) VALUES (:id, :name) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": org_id, "name": f"Test Org {org_id}"},
        )
    except Exception:
        # organizations table may have additional NOT NULL columns or not be
        # FK-enforced in the test DB; the per-table create uses use_alter so a
        # missing parent row won't block inserts. Roll back the failed statement
        # so the session stays usable.
        db.rollback()


def _seed_workspace_loan(
    db,
    *,
    org_id: int,
    slug: str,
    crm_loan_id: int,
    create_portal_loan: bool = True,
    lifecycle_stage: LifecycleStage = LifecycleStage.PROCESSING,
):
    """Create a PURLWorkspace + PURLLoan (+ optional PortalLoan) via raw SQL.

    Raw SQL is used deliberately so test setup never instantiates ORM models
    (which would trigger SQLAlchemy mapper configuration at an arbitrary point
    in the import cycle). The route handlers under test still exercise the real
    ORM queries inside a fully-initialized app request.

    Returns (workspace_id, purl_loan_id, portal_loan_id|None).
    """
    _ensure_org(db, org_id)

    ws_id = db.execute(
        text(
            "INSERT INTO purl_workspaces (organization_id, slug, status, display_name) "
            "VALUES (:org, :slug, :status, :name) RETURNING id"
        ),
        {"org": org_id, "slug": slug, "status": "active_loan",
         "name": f"Workspace {slug}"},
    ).scalar_one()

    purl_loan_id = db.execute(
        text(
            "INSERT INTO purl_loans "
            "(organization_id, workspace_id, main_loan_id, loan_number, status) "
            "VALUES (:org, :ws, :main, :ln, :status) RETURNING id"
        ),
        {"org": org_id, "ws": ws_id, "main": crm_loan_id,
         "ln": f"LN-{crm_loan_id}", "status": "active"},
    ).scalar_one()

    portal_loan_id = None
    if create_portal_loan:
        portal_loan_id = db.execute(
            text(
                "INSERT INTO portal_loans (crm_deal_id, lifecycle_stage, is_active) "
                "VALUES (:crm, :stage, :active) RETURNING id"
            ),
            {"crm": crm_loan_id, "stage": lifecycle_stage.value, "active": True},
        ).scalar_one()

    db.flush()
    return ws_id, purl_loan_id, portal_loan_id


def _override_context(db_session, context: PURLAuthContext):
    """Wire dependency overrides for a forged PURL context + test db session."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def _override_require_purl_token():
        return context

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_purl_token] = _override_require_purl_token


@pytest.fixture
def purl_client(db_session):
    """TestClient with get_db overridden; require_purl_token set per-test."""
    from fastapi.testclient import TestClient

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# crm_loan_id / main_loan_id serialization
# ---------------------------------------------------------------------------

def test_loan_to_dict_exposes_crm_loan_id(db_session):
    """_loan_to_dict must surface main_loan_id under crm_loan_id (the bridge id).

    Uses a lightweight stub with the attributes _loan_to_dict reads, so the test
    does not depend on instantiating the ORM model (mapper-config independent).
    """
    from types import SimpleNamespace
    from services.purl_workspace_service import PURLWorkspaceService

    stub_loan = SimpleNamespace(
        id=4242,                # PURLLoan.id (one id-space)
        main_loan_id=55501,     # CRM loan id (the bridge value)
        organization_id=ORG_A,
        workspace_id=7,
        application_id=None,
        loan_number="LN-55501",
        status="active",
        loan_purpose=None,
        product_type=None,
        loan_amount=None,
        interest_rate=None,
        property_address=None,
        property_type=None,
        target_close_date=None,
        actual_close_date=None,
        los_loan_id=None,
        meta_data={},
        created_at=None,
        updated_at=None,
    )

    svc = PURLWorkspaceService(db_session)
    result = svc._loan_to_dict(stub_loan)

    assert result["id"] == 4242                    # PURLLoan.id preserved
    assert result["crm_loan_id"] == 55501          # CRM bridge id exposed
    assert result["main_loan_id"] == 55501         # raw column also exposed
    # The two id-spaces must NOT be conflated.
    assert result["id"] != result["crm_loan_id"]


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------

def test_borrower_dashboard_requires_purl_token(db_session):
    """No PURL token -> 401 (require_purl_token NOT overridden here)."""
    from fastapi.testclient import TestClient

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/v1/portal/borrower/12345/dashboard")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_mum_dashboard_requires_purl_token(db_session):
    from fastapi.testclient import TestClient

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/v1/portal/borrower/12345/mum-dashboard")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Cross-tenant denied (IDOR guard)
# ---------------------------------------------------------------------------

def test_borrower_dashboard_cross_tenant_denied(db_session, purl_client):
    """
    A token bound to workspace A must NOT read workspace B's loan via the
    CRM loan id. The ownership guard returns 404 (not the loan, not 403) so it
    does not confirm existence of other tenants' ids.
    """
    # Workspace A (the token holder) and workspace B (victim) in a different org.
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="tenant-a", crm_loan_id=70001
    )
    _seed_workspace_loan(
        db_session, org_id=ORG_B, slug="tenant-b", crm_loan_id=70002
    )

    ctx = PURLAuthContext(
        token_id=1,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="tenant-a",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    # Attempt to read tenant B's CRM loan id with tenant A's token.
    resp = purl_client.get("/api/v1/portal/borrower/70002/dashboard")
    assert resp.status_code == 404

    # An entirely fabricated id is likewise rejected.
    resp2 = purl_client.get("/api/v1/portal/borrower/99999999/dashboard")
    assert resp2.status_code == 404


def test_mum_dashboard_cross_tenant_denied(db_session, purl_client):
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="mum-a", crm_loan_id=71001,
        lifecycle_stage=LifecycleStage.FUNDED,
    )
    _seed_workspace_loan(
        db_session, org_id=ORG_B, slug="mum-b", crm_loan_id=71002,
        lifecycle_stage=LifecycleStage.FUNDED,
    )

    ctx = PURLAuthContext(
        token_id=2,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="mum-a",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    resp = purl_client.get("/api/v1/portal/borrower/71002/mum-dashboard")
    assert resp.status_code == 404


def test_borrower_dashboard_same_org_other_workspace_denied(db_session, purl_client):
    """
    Even within the SAME org, a token bound to workspace A cannot read another
    workspace's loan (workspace_id is the tenant key here).
    """
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="same-org-a", crm_loan_id=72001
    )
    # Different workspace, same org, different CRM loan id.
    _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="same-org-b", crm_loan_id=72002
    )

    ctx = PURLAuthContext(
        token_id=3,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="same-org-a",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    resp = purl_client.get("/api/v1/portal/borrower/72002/dashboard")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_borrower_dashboard_happy_path(db_session, purl_client):
    """Token for workspace A reading its OWN loan returns the dashboard payload
    including the new home_value key and the existing risks key."""
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="happy-a", crm_loan_id=73001
    )

    ctx = PURLAuthContext(
        token_id=4,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="happy-a",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    resp = purl_client.get("/api/v1/portal/borrower/73001/dashboard")
    assert resp.status_code == 200
    body = resp.json()

    assert body["loan_id"] == 73001
    # New: home_value is present. With no PropertyValueBaseline it degrades to
    # has_baseline:false rather than erroring.
    assert "home_value" in body
    assert body["home_value"].get("has_baseline") is False
    # risks ships today on this endpoint; empty for a freshly seeded loan.
    assert "risks" in body
    assert isinstance(body["risks"], list)
    assert "lifecycle" in body


def test_mum_dashboard_happy_path(db_session, purl_client):
    """MUM dashboard for a FUNDED loan owned by the token's workspace returns
    home_value without persisting a valuation (save_valuation=False path)."""
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="mum-happy", crm_loan_id=74001,
        lifecycle_stage=LifecycleStage.FUNDED,
    )

    ctx = PURLAuthContext(
        token_id=5,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="mum-happy",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    resp = purl_client.get("/api/v1/portal/borrower/74001/mum-dashboard")
    assert resp.status_code == 200
    body = resp.json()

    assert body["loan_id"] == 74001
    assert "home_value" in body
    assert body["home_value"].get("has_baseline") is False


def test_mum_dashboard_rejects_non_funded_loan(db_session, purl_client):
    """MUM dashboard is only for funded/MUM loans; an ACTIVE loan -> 400.
    The ownership guard still runs first, so this proves the loan IS owned."""
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="mum-active", crm_loan_id=75001,
        lifecycle_stage=LifecycleStage.PROCESSING,
    )

    ctx = PURLAuthContext(
        token_id=6,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="mum-active",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    resp = purl_client.get("/api/v1/portal/borrower/75001/mum-dashboard")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# IDOR regression: id-space collision (the actual exploitable failure mode)
# ---------------------------------------------------------------------------

def test_borrower_dashboard_resolves_own_loan_not_id_colliding_foreign(db_session, purl_client):
    """Regression for the cross-tenant IDOR the review panel caught.

    The ownership guard passes for the borrower's own crm_loan_id, but a FOREIGN
    tenant's PortalLoan has primary key id == that same integer. The borrower
    must read THEIR PortalLoan (matched by crm_deal_id), never the foreign row
    that merely collides on PortalLoan.id. The old dual-precedence resolver
    (PortalLoan.id matched FIRST) would have leaked the foreign row; the fix
    resolves by crm_deal_id only.
    """
    COLLIDE = 76001

    # Workspace A owns crm_loan_id=76001; its own PortalLoan is ACTIVE (PROCESSING).
    # Seeded first so its autoincrement id is NOT 76001.
    ws_a_id, _, _ = _seed_workspace_loan(
        db_session, org_id=ORG_A, slug="collide-a", crm_loan_id=COLLIDE,
        lifecycle_stage=LifecycleStage.PROCESSING,
    )

    # Foreign tenant's PortalLoan, primary key forced to id == 76001 (the collision),
    # FUNDED, with its OWN unrelated crm_deal_id. No org scoping on portal_loans.
    db_session.execute(
        text(
            "INSERT INTO portal_loans (id, crm_deal_id, lifecycle_stage, is_active) "
            "VALUES (:id, :crm, :stage, :active)"
        ),
        {"id": COLLIDE, "crm": 99990001,
         "stage": LifecycleStage.FUNDED.value, "active": True},
    )
    db_session.flush()

    ctx = PURLAuthContext(
        token_id=7,
        organization_id=ORG_A,
        workspace_id=ws_a_id,
        workspace_slug="collide-a",
        workspace_status="active_loan",
        scope=TokenScope.READ,
    )
    _override_context(db_session, ctx)

    # MUM endpoint is the cleanest discriminator: the borrower's OWN loan is
    # PROCESSING -> 400 (not funded). The OLD id-first resolver would have matched
    # the FOREIGN FUNDED row (id == 76001) and returned 200 with another tenant's
    # servicing data — the exact leak.
    resp = purl_client.get(f"/api/v1/portal/borrower/{COLLIDE}/mum-dashboard")
    assert resp.status_code == 400, (
        "IDOR: borrower path resolved a foreign id-colliding PortalLoan "
        "instead of their own crm_deal_id-matched loan"
    )

    # And the dashboard endpoint resolves the borrower's OWN loan (200), echoing
    # the CRM loan id it was asked for.
    resp2 = purl_client.get(f"/api/v1/portal/borrower/{COLLIDE}/dashboard")
    assert resp2.status_code == 200
    assert resp2.json()["loan_id"] == COLLIDE
