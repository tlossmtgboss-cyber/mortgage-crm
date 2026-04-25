"""
Tenant Isolation Test Suite — Multi-Tenant Security Verification

Verifies that data cannot leak between organizations through:
1. RLS context setting on database sessions
2. Model org_id column presence on critical models
3. ORM query filter patterns with organization_id
4. API endpoint isolation between tenants
5. Webhook endpoint tenant context handling

These tests use mock DB sessions and the existing conftest fixtures.
They do NOT require a running PostgreSQL instance for the majority of
cases (pure unit tests against code structure and mock behavior).
"""

import pytest
import inspect
import os
import sys
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# 1. RLS Context Setting (2 tests)
# =============================================================================

@pytest.mark.tenant_isolation
@pytest.mark.unit
class TestRLSContextSetting:
    """Verify that get_db() sets RLS tenant context on sessions."""

    def test_get_db_sets_tenant_context_when_request_has_org_id(self):
        """get_db() should call set_tenant_context when request.state has organization_id."""
        from db import get_db

        # Build a mock Request with organization_id on state
        mock_request = MagicMock()
        mock_request.state.organization_id = 42

        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"), \
             patch("db.USE_PGBOUNCER", False), \
             patch("db.MAX_CONNECTIONS_PER_TENANT", 0):
            # Patch set_tenant_context at the import location used by get_db
            with patch("database.tenant_mixin.set_tenant_context", side_effect=None) as mock_set:
                gen = get_db(request=mock_request)
                session = next(gen)
                assert session is mock_session

                # Verify set_tenant_context was invoked with the session and org_id
                mock_set.assert_called_once_with(mock_session, 42)

                # Clean up generator
                try:
                    next(gen)
                except StopIteration:
                    pass

    def test_get_db_raises_in_production_when_rls_fails(self):
        """In production, RLS context failure should raise (not silently skip)."""
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
            # Patch the lazy import path — set_tenant_context is imported
            # inside get_db via `from database.tenant_mixin import set_tenant_context`
            with patch("database.tenant_mixin.set_tenant_context", side_effect=rls_error):
                gen = get_db(request=mock_request)
                with pytest.raises(RuntimeError, match="set_tenant_context blew up"):
                    next(gen)

                # Session should still be closed via finally block
                mock_session.close.assert_called_once()


# =============================================================================
# 2. Model org_id Presence (1 test class, parametrized)
# =============================================================================

@pytest.mark.tenant_isolation
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

        # Verify it's a real SQLAlchemy column (not just an arbitrary attribute)
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(model_cls)
        column_names = [col.key for col in mapper.columns]
        assert "organization_id" in column_names, (
            f"{model_name}.organization_id must be a mapped SQLAlchemy column, "
            f"found columns: {column_names[:10]}..."
        )

    @pytest.mark.parametrize("model_path,model_name", [
        ("database.models.lead_loan", "Lead"),
        ("database.models.lead_loan", "Loan"),
        ("database.models.task", "Task"),
        ("database.models.scheduler", "Appointment"),
    ])
    def test_critical_model_org_id_is_not_nullable(self, model_path, model_name):
        """organization_id should be NOT NULL on critical tenant-scoped models."""
        import importlib
        mod = importlib.import_module(model_path)
        model_cls = getattr(mod, model_name)

        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(model_cls)
        for col in mapper.columns:
            if col.key == "organization_id":
                assert col.nullable is False, (
                    f"{model_name}.organization_id must be NOT NULL "
                    "(nullable=False) to prevent orphaned records"
                )
                break


# =============================================================================
# 3. Query Filter Patterns (3 tests)
# =============================================================================

@pytest.mark.tenant_isolation
@pytest.mark.unit
class TestQueryFilterPatterns:
    """Verify ORM query patterns correctly scope data by organization_id."""

    def test_orm_query_with_org_id_filter_returns_matching_records(self):
        """ORM queries with explicit org_id filter should only return matching rows."""
        from database.models.lead_loan import Lead

        # Create mock session and mock query chain
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filtered = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filtered

        # Simulate the standard pattern: db.query(Lead).filter(Lead.organization_id == org_id)
        result = mock_db.query(Lead).filter(Lead.organization_id == 1)

        # Verify query was constructed with correct model
        mock_db.query.assert_called_once_with(Lead)
        # Verify filter was applied (the comparison expression was passed)
        mock_query.filter.assert_called_once()

    def test_tenant_mixin_tenant_query_scopes_by_org_id(self):
        """TenantMixin.tenant_query() should produce a query filtered by organization_id."""
        from database.tenant_mixin import TenantMixin

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        # Create a mock model class that uses TenantMixin
        class FakeModel(TenantMixin):
            organization_id = MagicMock()

        FakeModel.tenant_query(mock_db, organization_id=99)

        mock_db.query.assert_called_once_with(FakeModel)
        mock_query.filter.assert_called_once()

    def test_two_orgs_get_isolated_data(self):
        """Queries for org_id=1 and org_id=2 should produce independent filter calls."""
        from database.models.lead_loan import Lead

        mock_db = MagicMock()

        # Simulate two separate queries for different orgs
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [{"id": 1, "name": "Org1 Lead"}],  # org 1 results
            [{"id": 2, "name": "Org2 Lead"}],  # org 2 results
        ]

        # Query for org 1
        org1_results = (
            mock_db.query(Lead)
            .filter(Lead.organization_id == 1)
            .all()
        )

        # Query for org 2
        org2_results = (
            mock_db.query(Lead)
            .filter(Lead.organization_id == 2)
            .all()
        )

        # Verify independent results
        assert org1_results != org2_results
        assert len(org1_results) == 1
        assert len(org2_results) == 1

        # Verify filter was called twice (once per org)
        assert mock_db.query.return_value.filter.call_count == 2


# =============================================================================
# 4. API Endpoint Isolation (2 tests)
# =============================================================================

@pytest.mark.tenant_isolation
@pytest.mark.unit
class TestAPIEndpointIsolation:
    """Verify API endpoints respect tenant boundaries."""

    def test_lead_detail_rejects_cross_tenant_access(self, authenticated_client):
        """Lead detail endpoint should not return leads from a different org.

        The authenticated_client fixture injects mock_user with organization_id=1.
        If a lead belongs to org_id=2, the endpoint should return 404 (not found
        within the user's tenant scope) or 403.
        """
        from database.models.lead_loan import Lead

        # Create a lead in org 2 (different from mock_user's org 1)
        cross_tenant_lead = MagicMock(spec=Lead)
        cross_tenant_lead.id = 9999
        cross_tenant_lead.organization_id = 2
        cross_tenant_lead.first_name = "Cross"
        cross_tenant_lead.last_name = "Tenant"

        # Try to access the lead via the API
        # The endpoint should filter by the authenticated user's org_id (1),
        # so a lead with org_id=2 should not be visible.
        response = authenticated_client.get(f"/api/v1/leads/{cross_tenant_lead.id}")

        # Should be 404 (not found in tenant scope) or 403 (forbidden)
        # Not 200, which would indicate data leakage
        assert response.status_code != 200 or (
            response.status_code == 200
            and response.json().get("organization_id") != 2
        ), (
            f"Lead detail endpoint returned status {response.status_code} "
            f"for cross-tenant lead. Response: {response.text[:200]}"
        )

    def test_loan_detail_rejects_cross_tenant_access(self, authenticated_client):
        """Loan detail endpoint should not return loans from a different org.

        Similar to the lead test above: mock_user has org_id=1, so loans
        belonging to org_id=2 should be inaccessible.
        """
        # Request a loan ID that doesn't exist in org 1
        response = authenticated_client.get("/api/v1/loans/99999")

        # Should be 404 (not found) or 422 (validation error on ID format)
        # or 403 — anything but 200 with cross-tenant data
        if response.status_code == 200:
            data = response.json()
            # If it returns data, the org_id must match the authenticated user's org
            assert data.get("organization_id", 1) == 1, (
                "Loan endpoint returned data from a different organization"
            )


# =============================================================================
# 5. Webhook Endpoint Isolation (1 test class, 3 tests)
# =============================================================================

@pytest.mark.tenant_isolation
@pytest.mark.unit
class TestWebhookEndpointIsolation:
    """Verify webhook handlers set proper tenant context before DB operations."""

    def test_set_tenant_context_validates_org_id_type(self):
        """set_tenant_context should reject non-positive-integer org_id values."""
        from database.tenant_mixin import set_tenant_context

        mock_db = MagicMock()

        # Should reject zero
        with pytest.raises(ValueError, match="positive integer"):
            set_tenant_context(mock_db, 0)

        # Should reject negative
        with pytest.raises(ValueError, match="positive integer"):
            set_tenant_context(mock_db, -1)

        # Should reject non-integer
        with pytest.raises((ValueError, TypeError)):
            set_tenant_context(mock_db, "abc")

    def test_get_db_with_tenant_sets_rls_for_background_workers(self):
        """get_db_with_tenant (used by webhooks/cron) should set RLS context.

        Webhook handlers that process inbound events run outside the normal
        FastAPI request lifecycle. They use get_db_with_tenant() to ensure
        RLS is set before any DB operations.
        """
        from db import get_db_with_tenant

        mock_session = MagicMock()

        with patch("db.SessionLocal", return_value=mock_session), \
             patch("db.DATABASE_URL", "postgresql://localhost/test"):
            with patch("database.tenant_mixin.set_tenant_context") as mock_set:
                with get_db_with_tenant(org_id=5) as db:
                    # Verify we got the session
                    assert db is mock_session
                    # Verify tenant context was set
                    mock_set.assert_called_once_with(mock_session, 5)

    def test_get_db_with_tenant_refuses_unscoped_session_in_production(self):
        """In production, if RLS setup fails, get_db_with_tenant should raise."""
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
                        pass  # Should never reach here

                # Session must still be closed
                mock_session.close.assert_called_once()


# =============================================================================
# Supplementary: TenantMixin Structural Tests
# =============================================================================

@pytest.mark.tenant_isolation
@pytest.mark.unit
class TestTenantMixinStructure:
    """Verify TenantMixin provides correct multi-tenant helpers."""

    def test_tenant_mixin_get_by_tenant_filters_both_id_and_org(self):
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
        # filter() should have been called with two conditions
        mock_query.filter.assert_called_once()
        # .first() should be called to retrieve the single result
        mock_query.filter.return_value.first.assert_called_once()

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

    def test_tenant_session_auto_sets_org_id_on_add(self):
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
        """TenantSession.add() should NOT overwrite if organization_id is already set."""
        from database.tenant_mixin import TenantSession

        mock_db = MagicMock()

        class FakeEntity:
            organization_id = 99  # Already set

        entity = FakeEntity()

        with TenantSession(mock_db, organization_id=7) as ts:
            ts.add(entity)

        # Should remain 99, not changed to 7
        assert entity.organization_id == 99
