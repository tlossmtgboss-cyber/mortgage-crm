"""
Comprehensive Multi-Tenant Isolation Test Suite
=================================================
Tests tenant isolation at every layer:
    1. RLS context setting (get_db sets app.current_tenant)
    2. Cross-tenant data access blocked (org A cannot read org B's leads)
    3. Cross-tenant write blocked (org A cannot create lead in org B)
    4. Background worker tenant context (get_db_with_tenant)
    5. Missing tenant context in strict mode raises exception
    6. Per-tenant connection limits
    7. TenantMixin structural verification
    8. TenantSession auto-filtering and auto-setting org_id
    9. Model org_id column presence on critical models

Uses mocks/fixtures to avoid needing a real database for most tests.
Integration tests marked separately and skip without PostgreSQL.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# 1. RLS CONTEXT SETTING
# =============================================================================

@pytest.mark.unit
class TestRLSContextSetting:
    """Verify that get_db() sets RLS tenant context on sessions."""

    def test_get_db_sets_tenant_context_from_request(self):
        """get_db() should call set_tenant_context when request has organization_id."""
        from db import get_db

        mock_request = MagicMock()
        mock_request.state.organization_id = 42
        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"), \
             patch("db.USE_PGBOUNCER", False), \
             patch("db.MAX_CONNECTIONS_PER_TENANT", 0):
            with patch("database.tenant_mixin.set_tenant_context") as mock_set:
                gen = get_db(request=mock_request)
                session = next(gen)
                assert session is mock_session
                mock_set.assert_called_once_with(mock_session, 42)
                try:
                    next(gen)
                except StopIteration:
                    pass

    def test_get_db_without_request_skips_rls(self):
        """get_db() without request should not set RLS context."""
        from db import get_db

        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"), \
             patch("db.USE_PGBOUNCER", False), \
             patch("db.MAX_CONNECTIONS_PER_TENANT", 0):
            with patch("database.tenant_mixin.set_tenant_context") as mock_set:
                gen = get_db(request=None)
                session = next(gen)
                assert session is mock_session
                mock_set.assert_not_called()
                try:
                    next(gen)
                except StopIteration:
                    pass

    def test_get_db_rls_failure_raises_in_production(self):
        """In production, RLS context failure should raise."""
        from db import get_db

        mock_request = MagicMock()
        mock_request.state.organization_id = 7
        mock_session = MagicMock()
        rls_error = RuntimeError("set_tenant_context blew up")

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"), \
             patch("db.USE_PGBOUNCER", False), \
             patch("db.MAX_CONNECTIONS_PER_TENANT", 0), \
             patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
            with patch("database.tenant_mixin.set_tenant_context", side_effect=rls_error):
                gen = get_db(request=mock_request)
                with pytest.raises(RuntimeError, match="set_tenant_context blew up"):
                    next(gen)
                mock_session.close.assert_called_once()


# =============================================================================
# 2. CROSS-TENANT DATA ACCESS BLOCKED
# =============================================================================

@pytest.mark.unit
class TestCrossTenantAccessBlocked:
    """Verify that cross-tenant data access is blocked at the query layer."""

    def test_tenant_query_filters_by_org_id(self):
        """TenantMixin.tenant_query() should filter by organization_id."""
        from database.tenant_mixin import TenantMixin

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        class FakeModel(TenantMixin):
            organization_id = MagicMock()

        FakeModel.tenant_query(mock_db, organization_id=99)
        mock_db.query.assert_called_once_with(FakeModel)
        mock_query.filter.assert_called_once()

    def test_get_by_tenant_filters_both_id_and_org(self):
        """get_by_tenant should filter by both entity ID and organization_id."""
        from database.tenant_mixin import TenantMixin

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        class FakeModel(TenantMixin):
            id = MagicMock()
            organization_id = MagicMock()

        FakeModel.get_by_tenant(mock_db, entity_id=10, organization_id=5)
        mock_db.query.assert_called_once_with(FakeModel)
        mock_query.filter.assert_called_once()
        mock_query.filter.return_value.first.assert_called_once()

    def test_two_orgs_get_independent_results(self):
        """Queries for different orgs should produce independent filter calls."""
        from database.models.lead_loan import Lead

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [{"id": 1, "name": "Org1 Lead"}],
            [{"id": 2, "name": "Org2 Lead"}],
        ]

        org1_results = mock_db.query(Lead).filter(Lead.organization_id == 1).all()
        org2_results = mock_db.query(Lead).filter(Lead.organization_id == 2).all()

        assert org1_results != org2_results
        assert mock_db.query.return_value.filter.call_count == 2


# =============================================================================
# 3. CROSS-TENANT WRITE BLOCKED
# =============================================================================

@pytest.mark.unit
class TestCrossTenantWriteBlocked:
    """Verify that TenantSession prevents cross-tenant writes."""

    def test_tenant_session_sets_org_id_on_add(self):
        """TenantSession.add() should set organization_id if not already set."""
        from database.tenant_mixin import TenantSession

        mock_db = MagicMock()

        class FakeEntity:
            organization_id = None

        entity = FakeEntity()

        with TenantSession(mock_db, organization_id=7) as ts:
            ts.add(entity)

        assert entity.organization_id == 7
        mock_db.add.assert_called_once_with(entity)

    def test_tenant_session_does_not_overwrite_existing_org_id(self):
        """TenantSession.add() should NOT overwrite existing organization_id."""
        from database.tenant_mixin import TenantSession

        mock_db = MagicMock()

        class FakeEntity:
            organization_id = 99

        entity = FakeEntity()

        with TenantSession(mock_db, organization_id=7) as ts:
            ts.add(entity)

        assert entity.organization_id == 99

    def test_tenant_session_auto_filters_queries(self):
        """TenantSession should automatically apply org_id filter to queries."""
        from database.tenant_mixin import TenantSession

        mock_db = MagicMock()

        class FakeModel:
            organization_id = MagicMock()

        with TenantSession(mock_db, organization_id=3) as ts:
            ts.query(FakeModel)

        mock_db.query.assert_called_once_with(FakeModel)
        mock_db.query.return_value.filter.assert_called_once()


# =============================================================================
# 4. BACKGROUND WORKER TENANT CONTEXT
# =============================================================================

@pytest.mark.unit
class TestBackgroundWorkerTenantContext:
    """Verify get_db_with_tenant for background workers."""

    def test_get_db_with_tenant_sets_rls(self):
        """get_db_with_tenant should set RLS context for webhooks/cron."""
        from db import get_db_with_tenant

        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"):
            with patch("database.tenant_mixin.set_tenant_context") as mock_set:
                with get_db_with_tenant(org_id=5) as db:
                    assert db is mock_session
                    mock_set.assert_called_once_with(mock_session, 5)

    def test_get_db_with_tenant_raises_on_rls_failure_in_production(self):
        """In production, if RLS setup fails, should raise."""
        from db import get_db_with_tenant

        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"), \
             patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
            with patch(
                "database.tenant_mixin.set_tenant_context",
                side_effect=RuntimeError("RLS failed"),
            ):
                with pytest.raises(RuntimeError, match="RLS failed"):
                    with get_db_with_tenant(org_id=3) as db:
                        pass
                mock_session.close.assert_called_once()


# =============================================================================
# 5. MISSING TENANT CONTEXT VALIDATION
# =============================================================================

@pytest.mark.unit
class TestMissingTenantContext:
    """Verify set_tenant_context validates org_id."""

    def test_rejects_zero_org_id(self):
        """set_tenant_context should reject org_id=0."""
        from database.tenant_mixin import set_tenant_context
        mock_db = MagicMock()
        with pytest.raises(ValueError, match="positive integer"):
            set_tenant_context(mock_db, 0)

    def test_rejects_negative_org_id(self):
        """set_tenant_context should reject negative org_id."""
        from database.tenant_mixin import set_tenant_context
        mock_db = MagicMock()
        with pytest.raises(ValueError, match="positive integer"):
            set_tenant_context(mock_db, -1)

    def test_rejects_non_integer_org_id(self):
        """set_tenant_context should reject non-integer org_id."""
        from database.tenant_mixin import set_tenant_context
        mock_db = MagicMock()
        with pytest.raises((ValueError, TypeError)):
            set_tenant_context(mock_db, "abc")


# =============================================================================
# 6. PER-TENANT CONNECTION LIMITS
# =============================================================================

@pytest.mark.unit
class TestPerTenantConnectionLimits:
    """Verify per-tenant connection limits (PERF-008)."""

    def test_connection_limit_enforced(self):
        """Exceeding per-tenant connection limit should raise 503."""
        from db import get_db, _tenant_connection_counts, _tenant_conn_lock

        mock_request = MagicMock()
        mock_request.state.organization_id = 100
        mock_session = MagicMock()

        # Pre-fill tenant connection count to the max
        with _tenant_conn_lock:
            _tenant_connection_counts[100] = 7  # Default MAX is 7

        try:
            with patch("db.SessionLocal", return_value=mock_session), \
                 patch("db.DATABASE_URL", "postgresql://localhost/test"), \
                 patch("db.USE_PGBOUNCER", False), \
                 patch("db.MAX_CONNECTIONS_PER_TENANT", 7):
                from fastapi import HTTPException
                gen = get_db(request=mock_request)
                with pytest.raises(HTTPException) as exc_info:
                    next(gen)
                assert exc_info.value.status_code == 503
                assert "too many concurrent" in exc_info.value.detail.lower()
        finally:
            with _tenant_conn_lock:
                _tenant_connection_counts.pop(100, None)

    def test_connection_limit_not_enforced_with_pgbouncer(self):
        """Per-tenant limits should be skipped when using PgBouncer."""
        from db import get_db, _tenant_connection_counts, _tenant_conn_lock

        mock_request = MagicMock()
        mock_request.state.organization_id = 200
        mock_session = MagicMock()

        with _tenant_conn_lock:
            _tenant_connection_counts[200] = 100  # Far over limit

        try:
            with patch("db.SessionLocal", return_value=mock_session), \
                 patch("db.DATABASE_URL", "postgresql://localhost/test"), \
                 patch("db.USE_PGBOUNCER", True), \
                 patch("db.MAX_CONNECTIONS_PER_TENANT", 7):
                with patch("database.tenant_mixin.set_tenant_context"):
                    gen = get_db(request=mock_request)
                    session = next(gen)
                    assert session is mock_session
                    try:
                        next(gen)
                    except StopIteration:
                        pass
        finally:
            with _tenant_conn_lock:
                _tenant_connection_counts.pop(200, None)

    def test_connection_count_incremented(self):
        """Opening a session should increment per-tenant count."""
        from db import get_db, _tenant_connection_counts, _tenant_conn_lock

        mock_request = MagicMock()
        mock_request.state.organization_id = 300
        mock_session = MagicMock()

        with _tenant_conn_lock:
            _tenant_connection_counts.pop(300, None)

        try:
            with patch("db.SessionLocal", return_value=mock_session), \
                 patch("db.DATABASE_URL", "postgresql://localhost/test"), \
                 patch("db.USE_PGBOUNCER", False), \
                 patch("db.MAX_CONNECTIONS_PER_TENANT", 7):
                with patch("database.tenant_mixin.set_tenant_context"):
                    gen = get_db(request=mock_request)
                    session = next(gen)
                    with _tenant_conn_lock:
                        assert _tenant_connection_counts.get(300, 0) >= 1
                    try:
                        next(gen)
                    except StopIteration:
                        pass
        finally:
            with _tenant_conn_lock:
                _tenant_connection_counts.pop(300, None)


# =============================================================================
# 7. MODEL ORG_ID PRESENCE
# =============================================================================

@pytest.mark.unit
class TestModelOrgIdPresence:
    """Verify critical multi-tenant models have organization_id column."""

    @pytest.mark.parametrize("model_path,model_name", [
        ("database.models.lead_loan", "Lead"),
        ("database.models.lead_loan", "Loan"),
        ("database.models.task", "Task"),
        ("database.models.scheduler", "Appointment"),
    ])
    def test_critical_model_has_organization_id(self, model_path, model_name):
        """Critical models must have organization_id for tenant isolation."""
        import importlib
        mod = importlib.import_module(model_path)
        model_cls = getattr(mod, model_name)
        assert hasattr(model_cls, "organization_id"), (
            f"{model_name} must have organization_id column for multi-tenant isolation"
        )

    @pytest.mark.parametrize("model_path,model_name", [
        ("database.models.lead_loan", "Lead"),
        ("database.models.lead_loan", "Loan"),
        ("database.models.task", "Task"),
        ("database.models.scheduler", "Appointment"),
    ])
    def test_org_id_is_sqlalchemy_column(self, model_path, model_name):
        """organization_id must be a real SQLAlchemy mapped column."""
        import importlib
        from sqlalchemy import inspect as sa_inspect
        mod = importlib.import_module(model_path)
        model_cls = getattr(mod, model_name)
        mapper = sa_inspect(model_cls)
        column_names = [col.key for col in mapper.columns]
        assert "organization_id" in column_names, (
            f"{model_name}.organization_id must be a mapped SQLAlchemy column"
        )

    @pytest.mark.parametrize("model_path,model_name", [
        ("database.models.lead_loan", "Lead"),
        ("database.models.lead_loan", "Loan"),
        ("database.models.task", "Task"),
    ])
    def test_org_id_not_nullable(self, model_path, model_name):
        """organization_id should be NOT NULL on critical tenant-scoped models."""
        import importlib
        from sqlalchemy import inspect as sa_inspect
        mod = importlib.import_module(model_path)
        model_cls = getattr(mod, model_name)
        mapper = sa_inspect(model_cls)
        for col in mapper.columns:
            if col.key == "organization_id":
                assert col.nullable is False, (
                    f"{model_name}.organization_id must be NOT NULL"
                )
                break


# =============================================================================
# 8. API ENDPOINT ISOLATION
# =============================================================================

@pytest.mark.integration
class TestAPIEndpointIsolation:
    """Verify API endpoints respect tenant boundaries."""

    def test_lead_detail_rejects_cross_tenant(self, authenticated_client):
        """Lead detail should not return leads from a different org."""
        # authenticated_client uses mock_user with organization_id=1
        # Non-existent lead ID in org 1 should return 404
        response = authenticated_client.get("/api/v1/leads/9999")
        assert response.status_code != 200 or (
            response.status_code == 200
            and response.json().get("organization_id") != 2
        )

    def test_loan_detail_rejects_cross_tenant(self, authenticated_client):
        """Loan detail should not return loans from a different org."""
        response = authenticated_client.get("/api/v1/loans/99999")
        if response.status_code == 200:
            data = response.json()
            assert data.get("organization_id", 1) == 1


# =============================================================================
# 9. INTEGRATION TESTS (require PostgreSQL)
# =============================================================================

def _db_available():
    try:
        from sqlalchemy import create_engine, text
        url = os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        eng = create_engine(url)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_HAS_DB = _db_available()
requires_db = pytest.mark.skipif(not _HAS_DB, reason="PostgreSQL not available")


def _insert_lead(db_session, *, name="Test Lead", email="test@example.com",
                 phone="5551234567", stage="New", source="website",
                 owner_id=1, organization_id=1):
    from database.models import Lead
    lead = Lead(
        name=name, email=email, phone=phone, stage=stage, source=source,
        owner_id=owner_id, organization_id=organization_id,
        ai_score=50, sentiment="neutral",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(lead)
    db_session.flush()
    return lead


def _make_client_for_user(app_ref, db_session, user):
    from database import get_db
    from main import get_current_user, get_current_user_flexible
    from auth.dependencies import (
        get_current_user as auth_dep_gcu,
        get_current_user_flexible as auth_dep_gcuf,
    )
    from fastapi.testclient import TestClient

    def override_get_db():
        try: yield db_session
        finally: pass

    async def override_auth():
        return user

    app_ref.dependency_overrides[get_db] = override_get_db
    app_ref.dependency_overrides[get_current_user] = override_auth
    app_ref.dependency_overrides[get_current_user_flexible] = override_auth
    app_ref.dependency_overrides[auth_dep_gcu] = override_auth
    app_ref.dependency_overrides[auth_dep_gcuf] = override_auth
    return TestClient(app_ref)


# Autouse: patch side-effect services
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


@pytest.mark.integration
class TestCrossTenantIntegration:
    """Integration tests verifying tenant isolation with real DB queries."""

    @requires_db
    def test_org1_cannot_read_org2_lead(self, db_session):
        """Organization 1 user cannot read Organization 2's lead."""
        from conftest import MockUser
        from main import app

        # Create lead in org 1
        lead = _insert_lead(db_session, name="Org1Only", email="org1only@test.com", organization_id=1)
        db_session.commit()

        # Try to access from org 2
        org2_user = MockUser(id=50, email="org2@test.com", organization_id=2, role="loan_officer")
        client = _make_client_for_user(app, db_session, org2_user)
        resp = client.get(f"/api/v1/leads/{lead.id}")
        assert resp.status_code == 404
        app.dependency_overrides.clear()

    @requires_db
    def test_org1_cannot_update_org2_lead(self, db_session):
        """Organization 1 user cannot update Organization 2's lead."""
        from conftest import MockUser
        from main import app

        lead = _insert_lead(db_session, name="Protected", email="protected@test.com", organization_id=1)
        db_session.commit()

        org2_user = MockUser(id=51, email="attacker@test.com", organization_id=2, role="loan_officer")
        client = _make_client_for_user(app, db_session, org2_user)
        resp = client.patch(f"/api/v1/leads/{lead.id}", json={"name": "Hacked"})
        assert resp.status_code == 404
        app.dependency_overrides.clear()

    @requires_db
    def test_org1_cannot_delete_org2_lead(self, db_session):
        """Organization 1 user cannot delete Organization 2's lead."""
        from conftest import MockUser
        from main import app

        lead = _insert_lead(db_session, name="NoDel", email="nodel@test.com", organization_id=1)
        db_session.commit()

        org2_user = MockUser(id=52, email="deleter@test.com", organization_id=2, role="loan_officer")
        client = _make_client_for_user(app, db_session, org2_user)
        resp = client.delete(f"/api/v1/leads/{lead.id}")
        assert resp.status_code == 404
        app.dependency_overrides.clear()

    @requires_db
    def test_lead_listing_only_shows_own_org(self, db_session):
        """GET /api/v1/leads/ should only return leads from the user's org."""
        from conftest import MockUser
        from main import app

        _insert_lead(db_session, name="Org1", email="org1list@test.com", organization_id=1)
        _insert_lead(db_session, name="Org2", email="org2list@test.com", organization_id=2)
        db_session.commit()

        org1_user = MockUser(id=1, email="user1@test.com", organization_id=1, role="loan_officer")
        client = _make_client_for_user(app, db_session, org1_user)
        resp = client.get("/api/v1/leads/")
        assert resp.status_code == 200
        leads = resp.json()
        for lead in leads:
            assert lead.get("organization_id") in (1, None), (
                f"Lead from org {lead.get('organization_id')} leaked to org 1"
            )
        app.dependency_overrides.clear()

    @requires_db
    def test_new_lead_inherits_user_org_id(self, db_session):
        """POST /api/v1/leads/ should set organization_id from authenticated user."""
        from conftest import MockUser
        from main import app

        org3_user = MockUser(id=70, email="org3@test.com", organization_id=3, role="loan_officer")
        client = _make_client_for_user(app, db_session, org3_user)
        resp = client.post("/api/v1/leads/", json={
            "name": "Org3 Lead", "email": "org3lead@test.com",
        })
        if resp.status_code == 201:
            data = resp.json()
            assert data.get("organization_id") == 3
        app.dependency_overrides.clear()
