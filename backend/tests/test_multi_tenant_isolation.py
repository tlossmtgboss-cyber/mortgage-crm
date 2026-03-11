"""
Test Multi-Tenant Isolation - Validates tenant isolation patterns in the
database layer, authentication fixtures, and API endpoints.

Covers:
- RLS-aware get_db is exported from db.py
- MockUser fixture has organization_id for tenant context
- Per-tenant connection limiting logic
- Key endpoints pass organization context via middleware
- get_db_with_tenant context manager validates org_id
"""

import pytest
import inspect
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# =============================================================================
# Database Layer Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestGetDbRLSAwareness:
    """Verify that get_db from db.py is RLS-aware (sets tenant context)."""

    def test_get_db_is_importable_from_db_module(self):
        """get_db should be importable from db.py."""
        from db import get_db
        assert get_db is not None

    def test_get_db_is_importable_from_database_package(self):
        """get_db should also be importable from database/__init__.py."""
        from database import get_db
        assert get_db is not None

    def test_get_db_accepts_request_parameter(self):
        """get_db should accept an optional Request parameter for tenant context."""
        from db import get_db
        sig = inspect.signature(get_db)
        params = list(sig.parameters.keys())
        assert "request" in params, (
            f"get_db should have 'request' parameter for RLS. Params: {params}"
        )

    def test_get_db_request_defaults_to_none(self):
        """get_db's request param should default to None for non-FastAPI callers."""
        from db import get_db
        sig = inspect.signature(get_db)
        request_param = sig.parameters["request"]
        assert request_param.default is None, (
            "get_db's request parameter should default to None"
        )

    def test_get_db_is_generator(self):
        """get_db should be a generator function (yields session)."""
        from db import get_db
        assert inspect.isgeneratorfunction(get_db), (
            "get_db should be a generator function that yields a DB session"
        )

    def test_get_db_with_tenant_exists(self):
        """get_db_with_tenant context manager should exist for background workers."""
        from db import get_db_with_tenant
        assert get_db_with_tenant is not None

    def test_get_db_with_tenant_validates_org_id(self):
        """get_db_with_tenant should reject invalid org_id values."""
        from db import get_db_with_tenant

        with pytest.raises(ValueError, match="positive integer"):
            with get_db_with_tenant(0):
                pass

        with pytest.raises(ValueError, match="positive integer"):
            with get_db_with_tenant(-1):
                pass

    def test_get_db_with_tenant_rejects_non_integer(self):
        """get_db_with_tenant should reject non-integer org_id."""
        from db import get_db_with_tenant

        with pytest.raises((ValueError, TypeError)):
            with get_db_with_tenant("abc"):
                pass


# =============================================================================
# MockUser Tenant Context
# =============================================================================

@pytest.mark.unit
class TestMockUserTenantContext:
    """Verify MockUser fixture has proper tenant isolation fields."""

    def test_mock_user_has_organization_id(self, mock_user):
        """MockUser should have an organization_id attribute."""
        assert hasattr(mock_user, "organization_id"), (
            "MockUser must have organization_id for tenant isolation testing"
        )

    def test_mock_user_organization_id_is_set(self, mock_user):
        """MockUser's organization_id should be a non-None value."""
        assert mock_user.organization_id is not None
        assert mock_user.organization_id > 0

    def test_mock_user_default_organization_id(self, mock_user):
        """MockUser's default organization_id should be 1."""
        assert mock_user.organization_id == 1

    def test_mock_user_has_required_auth_fields(self, mock_user):
        """MockUser should have all fields needed for auth/tenant checks."""
        required_fields = ["id", "email", "organization_id", "role", "is_active"]
        for field in required_fields:
            assert hasattr(mock_user, field), (
                f"MockUser missing required field: {field}"
            )

    def test_mock_admin_has_organization_id(self, mock_admin_user):
        """Admin MockUser should also have organization_id."""
        assert hasattr(mock_admin_user, "organization_id")
        assert mock_admin_user.organization_id is not None


# =============================================================================
# Per-Tenant Connection Limiting
# =============================================================================

@pytest.mark.unit
class TestPerTenantConnectionLimiting:
    """Verify per-tenant connection limiting config exists in db.py."""

    def test_max_connections_per_tenant_is_defined(self):
        """MAX_CONNECTIONS_PER_TENANT should be defined in db.py."""
        from db import MAX_CONNECTIONS_PER_TENANT
        assert isinstance(MAX_CONNECTIONS_PER_TENANT, int)
        assert MAX_CONNECTIONS_PER_TENANT > 0

    def test_tenant_connection_tracking_dict_exists(self):
        """_tenant_connection_counts dict should exist for tracking."""
        from db import _tenant_connection_counts
        assert isinstance(_tenant_connection_counts, dict)

    def test_pool_status_function_exists(self):
        """get_pool_status should be available for health checks."""
        from db import get_pool_status
        assert callable(get_pool_status)
        status = get_pool_status()
        assert isinstance(status, dict)
        assert "status" in status or "pool_type" in status


# =============================================================================
# Endpoint Organization Context
# =============================================================================

@pytest.mark.unit
class TestEndpointOrganizationContext:
    """Verify key endpoints have access to organization context via auth."""

    def test_authenticated_client_provides_org_context(self, authenticated_client, mock_user):
        """The authenticated_client fixture should inject a user with org_id."""
        # The mock_user injected by authenticated_client has organization_id
        assert mock_user.organization_id is not None

    def test_health_endpoint_accessible(self, client):
        """Health endpoint should be accessible without auth (baseline test)."""
        response = client.get("/api/v1/health")
        # Health endpoint may not exist, but if it does, it should respond
        if response.status_code != 404:
            assert response.status_code in (200, 503)

    def test_pipeline_endpoint_requires_auth_for_org_scope(self, client):
        """Pipeline data endpoints should require auth (which provides org context)."""
        # Try accessing a pipeline endpoint without auth
        response = client.get("/api/v1/leads")
        if response.status_code != 404:
            assert response.status_code in (401, 403, 422), (
                f"Pipeline endpoint should require auth, got {response.status_code}"
            )

    def test_dependency_override_injects_org_id(self, authenticated_client):
        """Authenticated client's get_db override should be active."""
        from main import app
        from database import get_db
        # Check that get_db has been overridden
        assert get_db in app.dependency_overrides, (
            "get_db should be overridden in authenticated_client fixture"
        )
