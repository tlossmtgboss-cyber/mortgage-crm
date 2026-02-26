"""
Tests for SOC 2 Change Management Service.
Coverage: Record deployment, config change, database migration.
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from soc2_compliance.services.change_management_service import ChangeManagementService
from soc2_compliance.constants import ChangeType, ChangeStatus


@pytest.fixture
def cms(mock_db):
    return ChangeManagementService(mock_db)


class TestRecordDeployment:
    """Test deployment event recording."""

    def test_record_deployment_returns_uuid(self, cms):
        record_id = cms.record_deployment(
            title="v2.0 release",
            description="New features",
        )
        assert record_id is not None

    def test_record_deployment_with_git_info(self, cms, mock_db):
        cms.record_deployment(
            title="v2.0 release",
            description="New features",
            git_commit="abc123",
            git_branch="main",
            deployment_id="deploy-456",
        )
        assert mock_db.execute.called
        assert mock_db.commit.called

    def test_record_deployment_with_all_fields(self, cms, mock_db):
        user_id = uuid4()
        tenant_id = uuid4()
        cms.record_deployment(
            title="Full deployment",
            description="With all fields",
            git_commit="abc123",
            git_branch="main",
            pull_request_url="https://github.com/org/repo/pull/42",
            deployment_id="deploy-789",
            requested_by=user_id,
            tenant_id=tenant_id,
            affected_systems=["app", "database"],
        )
        assert mock_db.execute.called


class TestRecordConfigChange:
    """Test configuration change recording."""

    def test_record_config_change(self, cms, mock_db):
        record_id = cms.record_configuration_change(
            title="Update rate limit",
            description="Increased rate limit from 60 to 120 RPM",
        )
        assert record_id is not None
        assert mock_db.commit.called

    def test_record_config_with_values(self, cms, mock_db):
        cms.record_configuration_change(
            title="Update rate limit",
            description="Increased rate limit",
            changed_by=uuid4(),
            old_values={"rate_limit": 60},
            new_values={"rate_limit": 120},
        )
        assert mock_db.execute.called


class TestRecordMigration:
    """Test database migration recording."""

    def test_record_migration(self, cms, mock_db):
        record_id = cms.record_database_migration(
            title="Add vendor registry table",
            description="New soc2_vendor_registry table for CC9 compliance",
            migration_name="add_vendor_registry",
        )
        assert record_id is not None
        assert mock_db.commit.called

    def test_record_migration_with_user(self, cms, mock_db):
        user_id = uuid4()
        cms.record_database_migration(
            title="Schema update",
            description="Migration details",
            migration_name="v2_schema",
            requested_by=user_id,
        )
        assert mock_db.execute.called
