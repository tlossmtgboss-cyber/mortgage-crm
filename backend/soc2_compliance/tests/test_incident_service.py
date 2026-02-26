"""
Tests for SOC 2 Incident Service.
Coverage: Lifecycle, timeline, root cause, tenant isolation, metrics.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone

from soc2_compliance.services.incident_service import IncidentService
from soc2_compliance.constants import IncidentStatus, IncidentCategory, SeverityLevel


class TestIncidentCreation:
    """Test incident creation."""

    def test_create_returns_uuid(self, incident_service, mock_db):
        incident_id = incident_service.create(
            title="Test incident",
            description="A test incident",
            category=IncidentCategory.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.HIGH,
        )
        assert incident_id is not None
        assert mock_db.execute.called
        assert mock_db.commit.called

    def test_create_with_all_fields(self, incident_service, mock_db):
        user_id = uuid4()
        tenant_id = uuid4()
        incident_id = incident_service.create(
            title="Full incident",
            description="Detailed description",
            category=IncidentCategory.DATA_BREACH,
            severity=SeverityLevel.CRITICAL,
            reported_by=user_id,
            assigned_to=user_id,
            tenant_id=tenant_id,
            affected_systems=["auth", "database"],
        )
        assert incident_id is not None

    def test_create_adds_timeline_entry(self, incident_service, mock_db):
        incident_service.create(
            title="Test incident",
            description="Description",
            category=IncidentCategory.OTHER,
            severity=SeverityLevel.LOW,
        )
        # Should have at least 2 execute calls: insert + timeline
        assert mock_db.execute.call_count >= 2


class TestIncidentStatusUpdate:
    """Test status transitions."""

    def test_update_status_success(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("open",)
        mock_db.execute.return_value = mock_result

        result = incident_service.update_status(
            uuid4(), IncidentStatus.INVESTIGATING
        )
        assert result is True

    def test_update_status_not_found(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = incident_service.update_status(uuid4(), IncidentStatus.RESOLVED)
        assert result is False

    def test_contained_sets_contained_at(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("open",)
        mock_db.execute.return_value = mock_result

        incident_service.update_status(uuid4(), IncidentStatus.CONTAINED)
        # Verify SQL contains contained_at by inspecting text() objects
        found = False
        for c in mock_db.execute.call_args_list:
            sql_obj = c[0][0] if c[0] else None
            if sql_obj is not None and hasattr(sql_obj, 'text') and "contained_at" in sql_obj.text:
                found = True
                break
        assert found, "Expected SQL with 'contained_at' not found"

    def test_resolved_sets_resolved_at(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("investigating",)
        mock_db.execute.return_value = mock_result

        incident_service.update_status(uuid4(), IncidentStatus.RESOLVED)
        found = False
        for c in mock_db.execute.call_args_list:
            sql_obj = c[0][0] if c[0] else None
            if sql_obj is not None and hasattr(sql_obj, 'text') and "resolved_at" in sql_obj.text:
                found = True
                break
        assert found, "Expected SQL with 'resolved_at' not found"

    def test_closed_sets_closed_at(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("resolved",)
        mock_db.execute.return_value = mock_result

        incident_service.update_status(uuid4(), IncidentStatus.CLOSED)
        found = False
        for c in mock_db.execute.call_args_list:
            sql_obj = c[0][0] if c[0] else None
            if sql_obj is not None and hasattr(sql_obj, 'text') and "closed_at" in sql_obj.text:
                found = True
                break
        assert found, "Expected SQL with 'closed_at' not found"


class TestIncidentTenantIsolation:
    """Test tenant isolation in incident queries."""

    def test_update_with_tenant_filter(self, incident_service, mock_db):
        tenant_id = uuid4()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("open",)
        mock_db.execute.return_value = mock_result

        incident_service.update_status(
            uuid4(), IncidentStatus.INVESTIGATING, tenant_id=tenant_id
        )
        sql_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("tenant_id" in s for s in sql_calls)

    def test_get_incident_with_tenant_filter(self, incident_service, mock_db):
        tenant_id = uuid4()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = incident_service.get_incident(uuid4(), tenant_id=tenant_id)
        assert result is None
        sql_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("tenant_id" in s for s in sql_calls)

    def test_add_note_with_tenant_isolation(self, incident_service, mock_db):
        tenant_id = uuid4()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None  # Not found for this tenant
        mock_db.execute.return_value = mock_result

        result = incident_service.add_note(uuid4(), "test note", tenant_id=tenant_id)
        assert result is False


class TestRootCause:
    """Test root cause documentation."""

    def test_set_root_cause_success(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = incident_service.set_root_cause(
            uuid4(),
            root_cause="SQL injection",
            remediation_steps="Parameterize queries",
            preventive_measures="Add input validation",
        )
        assert result is True

    def test_set_root_cause_not_found(self, incident_service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = incident_service.set_root_cause(
            uuid4(),
            root_cause="Unknown",
            remediation_steps="N/A",
            preventive_measures="N/A",
        )
        assert result is False
