"""
Tests for Calendar RBAC (Role-Based Access Control).

Tests cover:
- Permission resolution from user roles
- Role-to-permission mapping
- Appointment visibility (view) checks
- Appointment manageability (manage) checks
- Team member resolution via team_name and branch_id
- get_viewable_user_ids for different roles
- get_manageable_user_ids for different roles
- build_appointment_visibility_filter SQL clause generation
- check_appointment_access helper (HTTP exception behavior)
- Edge cases: unknown roles, missing fields, None values
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace
from fastapi import HTTPException

from services.calendar_permissions import (
    CalendarRole,
    CalendarPermission,
    CalendarAccessControl,
    ROLE_PERMISSIONS,
    check_appointment_access,
    build_appointment_visibility_filter,
    _get_team_member_ids,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _make_user(
    id=1,
    permission_role="sales",
    role="loan_officer",
    organization_id=100,
    team_name=None,
    branch_id=None,
):
    """Create a mock user object."""
    return SimpleNamespace(
        id=id,
        permission_role=permission_role,
        role=role,
        organization_id=organization_id,
        team_name=team_name,
        branch_id=branch_id,
        is_active=True,
    )


def _make_appointment(
    id=10,
    assigned_user_id=1,
    created_by_user_id=1,
    organization_id=100,
):
    """Create a mock appointment object."""
    return SimpleNamespace(
        id=id,
        assigned_user_id=assigned_user_id,
        created_by_user_id=created_by_user_id,
        organization_id=organization_id,
    )


# =============================================================================
# PERMISSION RESOLUTION
# =============================================================================

class TestPermissionResolution:
    """Test _resolve_permission_role and get_permissions."""

    def test_sales_role_gets_basic_permissions(self):
        user = _make_user(permission_role="sales")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms
        assert CalendarPermission.VIEW_TEAM not in perms
        assert CalendarPermission.MANAGE_ALL not in perms

    def test_processing_role_gets_basic_permissions(self):
        user = _make_user(permission_role="processing")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms
        assert CalendarPermission.VIEW_TEAM not in perms

    def test_operations_role_gets_basic_permissions(self):
        user = _make_user(permission_role="operations")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms
        assert CalendarPermission.VIEW_TEAM not in perms

    def test_leadership_gets_view_team(self):
        user = _make_user(permission_role="leadership")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms
        assert CalendarPermission.VIEW_TEAM in perms
        assert CalendarPermission.MANAGE_TEAM not in perms
        assert CalendarPermission.VIEW_ANALYTICS not in perms

    def test_management_gets_team_manage_and_analytics(self):
        user = _make_user(permission_role="management")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms
        assert CalendarPermission.VIEW_TEAM in perms
        assert CalendarPermission.MANAGE_TEAM in perms
        assert CalendarPermission.VIEW_ANALYTICS in perms
        assert CalendarPermission.MANAGE_ALL not in perms
        assert CalendarPermission.MANAGE_SETTINGS not in perms

    def test_admin_gets_all_permissions(self):
        user = _make_user(permission_role="admin")
        perms = CalendarAccessControl.get_permissions(user)
        for p in CalendarPermission:
            assert p in perms, f"Admin missing permission: {p.value}"

    def test_site_admin_gets_all_permissions(self):
        user = _make_user(permission_role="site_admin")
        perms = CalendarAccessControl.get_permissions(user)
        for p in CalendarPermission:
            assert p in perms, f"Site admin missing permission: {p.value}"

    def test_platform_admin_gets_all_permissions(self):
        user = _make_user(permission_role="platform_admin")
        perms = CalendarAccessControl.get_permissions(user)
        for p in CalendarPermission:
            assert p in perms, f"Platform admin missing permission: {p.value}"

    def test_unknown_role_defaults_to_sales(self):
        user = _make_user(permission_role="intern")
        perms = CalendarAccessControl.get_permissions(user)
        assert perms == ROLE_PERMISSIONS["sales"]

    def test_none_permission_role_falls_back_to_role(self):
        user = _make_user(permission_role=None, role="loan_officer")
        perms = CalendarAccessControl.get_permissions(user)
        # loan_officer maps to sales via legacy map
        assert CalendarPermission.VIEW_OWN in perms
        assert CalendarPermission.MANAGE_OWN in perms

    def test_none_both_roles_defaults_to_sales(self):
        user = _make_user(permission_role=None, role=None)
        perms = CalendarAccessControl.get_permissions(user)
        assert perms == ROLE_PERMISSIONS["sales"]

    def test_legacy_role_mapping_team_lead(self):
        user = _make_user(permission_role=None, role="team_lead")
        perms = CalendarAccessControl.get_permissions(user)
        # team_lead -> leadership
        assert CalendarPermission.VIEW_TEAM in perms

    def test_legacy_role_mapping_manager(self):
        user = _make_user(permission_role=None, role="manager")
        perms = CalendarAccessControl.get_permissions(user)
        # manager -> management
        assert CalendarPermission.MANAGE_TEAM in perms
        assert CalendarPermission.VIEW_ANALYTICS in perms

    def test_case_insensitive_role(self):
        user = _make_user(permission_role="ADMIN")
        perms = CalendarAccessControl.get_permissions(user)
        for p in CalendarPermission:
            assert p in perms

    def test_role_with_whitespace(self):
        user = _make_user(permission_role="  management  ")
        perms = CalendarAccessControl.get_permissions(user)
        assert CalendarPermission.MANAGE_TEAM in perms


# =============================================================================
# HAS_PERMISSION
# =============================================================================

class TestHasPermission:
    def test_has_permission_true(self):
        user = _make_user(permission_role="admin")
        assert CalendarAccessControl.has_permission(user, CalendarPermission.MANAGE_ALL)

    def test_has_permission_false(self):
        user = _make_user(permission_role="sales")
        assert not CalendarAccessControl.has_permission(user, CalendarPermission.VIEW_TEAM)


# =============================================================================
# CAN_VIEW_APPOINTMENT
# =============================================================================

class TestCanViewAppointment:
    def test_admin_can_view_any(self):
        user = _make_user(id=1, permission_role="admin")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_view_appointment(user, appt) is True

    def test_sales_can_view_own_assigned(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=5, created_by_user_id=99)
        assert CalendarAccessControl.can_view_appointment(user, appt) is True

    def test_sales_can_view_own_created(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=5)
        assert CalendarAccessControl.can_view_appointment(user, appt) is True

    def test_sales_cannot_view_others(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_view_appointment(user, appt) is False

    def test_leadership_can_view_team(self):
        user = _make_user(id=5, permission_role="leadership")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        # VIEW_TEAM returns True (team check is at query level)
        assert CalendarAccessControl.can_view_appointment(user, appt) is True

    def test_management_can_view_team(self):
        user = _make_user(id=5, permission_role="management")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_view_appointment(user, appt) is True


# =============================================================================
# CAN_MANAGE_APPOINTMENT
# =============================================================================

class TestCanManageAppointment:
    def test_admin_can_manage_any(self):
        user = _make_user(id=1, permission_role="admin")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is True

    def test_management_can_manage_team(self):
        user = _make_user(id=5, permission_role="management")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is True

    def test_sales_can_manage_own_assigned(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=5, created_by_user_id=99)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is True

    def test_sales_can_manage_own_created(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=5)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is True

    def test_sales_cannot_manage_others(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is False

    def test_leadership_cannot_manage_team(self):
        """Leadership has VIEW_TEAM but not MANAGE_TEAM."""
        user = _make_user(id=5, permission_role="leadership")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        assert CalendarAccessControl.can_manage_appointment(user, appt) is False


# =============================================================================
# GET_VIEWABLE_USER_IDS
# =============================================================================

class TestGetViewableUserIds:
    def test_admin_gets_none_for_all(self):
        user = _make_user(permission_role="admin")
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert result is None  # None means "all users"

    def test_sales_gets_own_id_only(self):
        user = _make_user(id=42, permission_role="sales")
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert result == [42]

    @patch("services.calendar_permissions._get_team_member_ids")
    def test_leadership_gets_team_ids(self, mock_team):
        mock_team.return_value = [10, 11, 12]
        user = _make_user(id=10, permission_role="leadership")
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert 10 in result
        assert 11 in result
        assert 12 in result

    @patch("services.calendar_permissions._get_team_member_ids")
    def test_leadership_with_no_team_gets_own_only(self, mock_team):
        mock_team.return_value = []
        user = _make_user(id=10, permission_role="leadership")
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert result == [10]

    @patch("services.calendar_permissions._get_team_member_ids")
    def test_management_gets_team_ids(self, mock_team):
        mock_team.return_value = [20, 21, 22]
        user = _make_user(id=20, permission_role="management")
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert set(result) == {20, 21, 22}


# =============================================================================
# GET_MANAGEABLE_USER_IDS
# =============================================================================

class TestGetManageableUserIds:
    def test_admin_gets_none_for_all(self):
        user = _make_user(permission_role="admin")
        db = MagicMock()
        result = CalendarAccessControl.get_manageable_user_ids(db, user)
        assert result is None

    def test_sales_gets_own_id_only(self):
        user = _make_user(id=42, permission_role="sales")
        db = MagicMock()
        result = CalendarAccessControl.get_manageable_user_ids(db, user)
        assert result == [42]

    @patch("services.calendar_permissions._get_team_member_ids")
    def test_management_gets_team_ids(self, mock_team):
        mock_team.return_value = [30, 31, 32]
        user = _make_user(id=30, permission_role="management")
        db = MagicMock()
        result = CalendarAccessControl.get_manageable_user_ids(db, user)
        assert set(result) == {30, 31, 32}

    @patch("services.calendar_permissions._get_team_member_ids")
    def test_leadership_gets_own_only(self, mock_team):
        """Leadership has VIEW_TEAM but not MANAGE_TEAM."""
        mock_team.return_value = [40, 41, 42]
        user = _make_user(id=40, permission_role="leadership")
        db = MagicMock()
        result = CalendarAccessControl.get_manageable_user_ids(db, user)
        # Leadership doesn't have MANAGE_TEAM, so falls through to own-only
        assert result == [40]


# =============================================================================
# TEAM MEMBER RESOLUTION
# =============================================================================

class TestTeamMemberResolution:
    @patch("services.calendar_permissions.logger")
    def test_no_org_returns_empty(self, mock_logger):
        user = _make_user(organization_id=None)
        db = MagicMock()
        result = _get_team_member_ids(db, user)
        assert result == []

    def test_team_name_match(self):
        user = _make_user(team_name="Alpha Team", organization_id=100)
        db = MagicMock()

        # Mock the query chain
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter

        # Return mock user rows
        member1 = SimpleNamespace(id=10)
        member2 = SimpleNamespace(id=11)
        member3 = SimpleNamespace(id=12)
        mock_filter.all.return_value = [member1, member2, member3]

        with patch("services.calendar_permissions.UserModel", create=True):
            # We need to mock the import
            with patch.dict("sys.modules", {"database.models.core": MagicMock()}):
                result = _get_team_member_ids(db, user)
                assert set(result) == {10, 11, 12}

    def test_no_team_name_no_branch_returns_empty(self):
        user = _make_user(team_name=None, branch_id=None, organization_id=100)
        db = MagicMock()
        # With no team_name and no branch_id, should return empty
        with patch.dict("sys.modules", {"database.models.core": MagicMock()}):
            result = _get_team_member_ids(db, user)
            assert result == []


# =============================================================================
# CHECK_APPOINTMENT_ACCESS
# =============================================================================

class TestCheckAppointmentAccess:
    def test_view_allowed_for_owner(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=5)
        # Should not raise
        check_appointment_access(user, appt, action="view")

    def test_view_denied_raises_404(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        with pytest.raises(HTTPException) as exc_info:
            check_appointment_access(user, appt, action="view")
        assert exc_info.value.status_code == 404

    def test_manage_allowed_for_admin(self):
        user = _make_user(id=1, permission_role="admin")
        appt = _make_appointment(assigned_user_id=99)
        # Should not raise
        check_appointment_access(user, appt, action="manage")

    def test_manage_denied_raises_404(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=99, created_by_user_id=99)
        with pytest.raises(HTTPException) as exc_info:
            check_appointment_access(user, appt, action="manage")
        assert exc_info.value.status_code == 404

    def test_manage_allowed_for_owner(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=5, created_by_user_id=99)
        # Should not raise
        check_appointment_access(user, appt, action="manage")


# =============================================================================
# BUILD_APPOINTMENT_VISIBILITY_FILTER
# =============================================================================

class TestBuildVisibilityFilter:
    def test_admin_returns_no_conditions(self):
        user = _make_user(permission_role="admin")
        db = MagicMock()
        Appointment = MagicMock()
        conditions = build_appointment_visibility_filter(db, user, Appointment)
        assert conditions == []

    @patch("services.calendar_permissions.CalendarAccessControl.get_viewable_user_ids")
    def test_sales_returns_filter_conditions(self, mock_viewable):
        mock_viewable.return_value = [42]
        user = _make_user(id=42, permission_role="sales")
        db = MagicMock()

        # Use real SQLAlchemy column mocks that produce valid clause elements
        from sqlalchemy import Column, Integer
        from sqlalchemy.ext.declarative import declarative_base

        TestBase = declarative_base()

        class FakeAppointment(TestBase):
            __tablename__ = "fake_appointments"
            id = Column(Integer, primary_key=True)
            assigned_user_id = Column(Integer)
            created_by_user_id = Column(Integer)

        conditions = build_appointment_visibility_filter(db, user, FakeAppointment)
        # Should return exactly 1 OR condition
        assert len(conditions) == 1


# =============================================================================
# ROLE PERMISSIONS MAPPING CONSISTENCY
# =============================================================================

class TestRolePermissionsMapping:
    def test_all_roles_have_view_own(self):
        """Every defined role should at least be able to view own calendar."""
        for role, perms in ROLE_PERMISSIONS.items():
            assert CalendarPermission.VIEW_OWN in perms, (
                f"Role '{role}' is missing VIEW_OWN permission"
            )

    def test_all_roles_have_manage_own(self):
        """Every role should be able to manage own calendar."""
        for role, perms in ROLE_PERMISSIONS.items():
            assert CalendarPermission.MANAGE_OWN in perms, (
                f"Role '{role}' is missing MANAGE_OWN permission"
            )

    def test_admin_tiers_have_all_permissions(self):
        """Admin, site_admin, platform_admin should have every permission."""
        for admin_role in ("admin", "site_admin", "platform_admin"):
            perms = ROLE_PERMISSIONS[admin_role]
            for p in CalendarPermission:
                assert p in perms, (
                    f"Admin role '{admin_role}' missing permission: {p.value}"
                )

    def test_management_has_analytics_but_not_settings(self):
        """Management can view analytics but cannot manage system settings."""
        perms = ROLE_PERMISSIONS["management"]
        assert CalendarPermission.VIEW_ANALYTICS in perms
        assert CalendarPermission.MANAGE_SETTINGS not in perms

    def test_leadership_has_view_team_but_not_manage_team(self):
        """Leadership can view team but not manage team appointments."""
        perms = ROLE_PERMISSIONS["leadership"]
        assert CalendarPermission.VIEW_TEAM in perms
        assert CalendarPermission.MANAGE_TEAM not in perms

    def test_permission_enum_completeness(self):
        """All CalendarPermission values should be covered by at least one role."""
        covered = set()
        for perms in ROLE_PERMISSIONS.values():
            covered.update(perms)
        for p in CalendarPermission:
            assert p in covered, f"Permission {p.value} not assigned to any role"


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    def test_user_with_empty_string_role(self):
        user = _make_user(permission_role="", role="")
        perms = CalendarAccessControl.get_permissions(user)
        assert perms == ROLE_PERMISSIONS["sales"]

    def test_user_with_no_id(self):
        user = SimpleNamespace(
            id=None,
            permission_role="sales",
            role="loan_officer",
            organization_id=100,
        )
        db = MagicMock()
        result = CalendarAccessControl.get_viewable_user_ids(db, user)
        assert result == []

    def test_appointment_with_none_user_ids(self):
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id=None, created_by_user_id=None)
        assert CalendarAccessControl.can_view_appointment(user, appt) is False

    def test_can_view_with_string_id_comparison(self):
        """IDs are compared as strings for flexibility."""
        user = _make_user(id=5, permission_role="sales")
        appt = _make_appointment(assigned_user_id="5", created_by_user_id=99)
        # String "5" vs int 5 — should still match
        assert CalendarAccessControl.can_view_appointment(user, appt) is True

    def test_calendar_permission_values_are_namespaced(self):
        """All permission values should follow calendar: namespace convention."""
        for p in CalendarPermission:
            assert p.value.startswith("calendar:"), (
                f"Permission {p.name} value '{p.value}' should start with 'calendar:'"
            )

    def test_calendar_role_enum_values(self):
        """CalendarRole enum should have expected values."""
        assert CalendarRole.OWNER == "owner"
        assert CalendarRole.TEAM_VIEWER == "team_viewer"
        assert CalendarRole.TEAM_MANAGER == "team_manager"
        assert CalendarRole.ORG_ADMIN == "org_admin"
