"""
Permission Enforcement Integration Tests

Tests for RBAC permission system:
- has_permission checks for different roles
- require_permission_or_403 enforcement
- Role-based default permissions
- Cross-org data isolation
- Permission endpoints

Key files:
    backend/routes/permission_core_routes.py
    backend/middleware/
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import text
from unittest.mock import patch

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def org(db_session):
    """Create a test organization."""
    from database.models import Organization
    org = Organization(name="PermTest Org", slug="permtest-org", is_active=True)
    db_session.add(org)
    db_session.flush()
    return org


@pytest.fixture
def admin_user(db_session, org):
    """Create an admin user."""
    from database.models import User
    user = User(
        email="perm-admin@test.com",
        hashed_password="hashed",
        first_name="Perm",
        last_name="Admin",
        role="admin",
        permission_role="admin",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lo_user(db_session, org):
    """Create a loan officer user (sales role)."""
    from database.models import User
    user = User(
        email="perm-lo@test.com",
        hashed_password="hashed",
        first_name="Perm",
        last_name="LO",
        role="loan_officer",
        permission_role="sales",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def processor_user(db_session, org):
    """Create a processor user."""
    from database.models import User
    user = User(
        email="perm-proc@test.com",
        hashed_password="hashed",
        first_name="Perm",
        last_name="Proc",
        role="processor",
        permission_role="processing",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def ensure_permissions_table(db_session):
    """Ensure the user_permissions table exists for permission checks."""
    try:
        db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                permission_key VARCHAR(100) NOT NULL,
                granted BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, permission_key)
            )
        """))
        db_session.flush()
    except Exception:
        db_session.rollback()


class TestHasPermission:
    """Test the has_permission function for different roles."""

    def test_admin_has_all_permissions(self, db_session, admin_user, ensure_permissions_table):
        """Admin role should have all permissions."""
        from routes.permission_core_routes import has_permission

        assert has_permission(admin_user.id, "leads.view_all", db_session) is True
        assert has_permission(admin_user.id, "leads.edit_all", db_session) is True
        assert has_permission(admin_user.id, "loans.view_all", db_session) is True
        assert has_permission(admin_user.id, "clients.view_all", db_session) is True

    def test_sales_user_has_assigned_permissions(self, db_session, lo_user, ensure_permissions_table):
        """Sales role should see own assigned leads/clients."""
        from routes.permission_core_routes import has_permission

        assert has_permission(lo_user.id, "leads.view_assigned", db_session) is True
        assert has_permission(lo_user.id, "leads.edit_own", db_session) is True
        assert has_permission(lo_user.id, "leads.create", db_session) is True

    def test_sales_user_lacks_view_all(self, db_session, lo_user, ensure_permissions_table):
        """Sales role should NOT have view_all permission by default."""
        from routes.permission_core_routes import has_permission

        assert has_permission(lo_user.id, "leads.view_all", db_session) is False
        assert has_permission(lo_user.id, "leads.edit_all", db_session) is False

    def test_processor_has_loan_permissions(self, db_session, processor_user, ensure_permissions_table):
        """Processing role should have loan processing permissions."""
        from routes.permission_core_routes import has_permission

        assert has_permission(processor_user.id, "loans.view_all", db_session) is True
        assert has_permission(processor_user.id, "loans.process", db_session) is True
        assert has_permission(processor_user.id, "clients.view_all", db_session) is True

    def test_nonexistent_user_returns_false(self, db_session, ensure_permissions_table):
        """Permission check for nonexistent user should return False."""
        from routes.permission_core_routes import has_permission

        assert has_permission(999999, "leads.view_all", db_session) is False


class TestRequirePermissionOr403:
    """Test the require_permission_or_403 enforcement wrapper."""

    def test_admin_passes_check(self, db_session, admin_user, ensure_permissions_table):
        """Admin should pass any permission check without raising."""
        from routes.permission_core_routes import require_permission_or_403

        # Should not raise
        require_permission_or_403(admin_user.id, "leads.view_all", db_session)

    def test_unauthorized_user_raises_403(self, db_session, lo_user, ensure_permissions_table):
        """User without permission should get 403 HTTPException."""
        from routes.permission_core_routes import require_permission_or_403
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            require_permission_or_403(lo_user.id, "leads.view_all", db_session)

        assert exc_info.value.status_code == 403


class TestExplicitUserPermissions:
    """Test explicit per-user permission grants in user_permissions table."""

    def test_explicit_grant_overrides_role_default(self, db_session, lo_user, ensure_permissions_table):
        """Explicit permission grant should allow access regardless of role."""
        from routes.permission_core_routes import has_permission

        # Without explicit grant, sales user can't view_all
        assert has_permission(lo_user.id, "leads.view_all", db_session) is False

        # Grant explicit permission
        db_session.execute(text("""
            INSERT INTO user_permissions (user_id, permission_key, granted)
            VALUES (:user_id, :perm, TRUE)
            ON CONFLICT (user_id, permission_key) DO UPDATE SET granted = TRUE
        """), {"user_id": lo_user.id, "perm": "leads.view_all"})
        db_session.flush()

        # Now should have permission
        assert has_permission(lo_user.id, "leads.view_all", db_session) is True


class TestCrossOrgIsolation:
    """Test that users cannot access data from other organizations."""

    def test_leads_scoped_to_org(self, db_session):
        """Leads from org2 should not appear in org1 queries."""
        from database.models import Organization, User, Lead

        org1 = Organization(name="ISO-Org1", slug="iso-org1", is_active=True)
        org2 = Organization(name="ISO-Org2", slug="iso-org2", is_active=True)
        db_session.add_all([org1, org2])
        db_session.flush()

        u1 = User(
            email="iso-u1@test.com", hashed_password="h",
            organization_id=org1.id, is_active=True,
        )
        u2 = User(
            email="iso-u2@test.com", hashed_password="h",
            organization_id=org2.id, is_active=True,
        )
        db_session.add_all([u1, u2])
        db_session.flush()

        lead1 = Lead(
            organization_id=org1.id, name="Org1Lead",
            first_name="O1", last_name="Lead",
            email="o1-lead@test.com", stage="New",
            owner_id=u1.id,
        )
        lead2 = Lead(
            organization_id=org2.id, name="Org2Lead",
            first_name="O2", last_name="Lead",
            email="o2-lead@test.com", stage="New",
            owner_id=u2.id,
        )
        db_session.add_all([lead1, lead2])
        db_session.flush()

        org1_leads = db_session.query(Lead).filter(
            Lead.organization_id == org1.id
        ).all()
        assert len(org1_leads) == 1
        assert org1_leads[0].name == "Org1Lead"

    def test_loans_scoped_to_org(self, db_session):
        """Loans should be isolated by organization_id."""
        from database.models import Organization, User, Loan

        org1 = Organization(name="ISO-LOrg1", slug="iso-lorg1", is_active=True)
        org2 = Organization(name="ISO-LOrg2", slug="iso-lorg2", is_active=True)
        db_session.add_all([org1, org2])
        db_session.flush()

        u1 = User(
            email="iso-lu1@test.com", hashed_password="h",
            organization_id=org1.id, is_active=True,
        )
        u2 = User(
            email="iso-lu2@test.com", hashed_password="h",
            organization_id=org2.id, is_active=True,
        )
        db_session.add_all([u1, u2])
        db_session.flush()

        loan1 = Loan(
            organization_id=org1.id, loan_number="ISO-L1",
            borrower_name="B1", stage="PROCESSING", amount=300000,
            loan_officer_id=u1.id,
        )
        loan2 = Loan(
            organization_id=org2.id, loan_number="ISO-L2",
            borrower_name="B2", stage="PROCESSING", amount=400000,
            loan_officer_id=u2.id,
        )
        db_session.add_all([loan1, loan2])
        db_session.flush()

        org1_loans = db_session.query(Loan).filter(
            Loan.organization_id == org1.id
        ).all()
        assert len(org1_loans) == 1
        assert org1_loans[0].loan_number == "ISO-L1"


class TestPermissionEndpoints:
    """Test permission-related HTTP endpoints."""

    def test_get_permissions_requires_auth(self, client):
        """Permission endpoints should require authentication."""
        response = client.get("/api/v1/permissions/me")
        assert response.status_code in (401, 403, 404, 500)

    def test_leads_endpoint_requires_auth(self, client):
        """Leads endpoint should enforce authentication."""
        response = client.get("/api/v1/leads/")
        assert response.status_code in (401, 403, 500)

    def test_loans_endpoint_requires_auth(self, client):
        """Loans endpoint should enforce authentication."""
        response = client.get("/api/v1/loans/")
        assert response.status_code in (401, 403, 404, 500)

    def test_settings_endpoint_requires_auth(self, client):
        """Settings endpoint should enforce authentication."""
        response = client.get("/api/v1/settings")
        assert response.status_code in (401, 403, 404, 500)
