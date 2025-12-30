"""
Test Suite: SLA Monitoring Agent

Tests for the SLA monitoring agent that creates tasks when milestones
reach 90% (at-risk) or 100% (breached) of their SLA target.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sla_monitoring_agent import (
    SLAMonitoringAgent,
    AlertLevel,
    MilestoneCheck,
    MILESTONE_ROLE_MAPPING,
    MILESTONE_DATE_FIELDS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.query = MagicMock()
    return db


@pytest.fixture
def mock_sla_measure():
    """Create a mock SLA measure."""
    measure = MagicMock()
    measure.milestone_type = MagicMock()
    measure.milestone_type.value = "appraisal_ordered"
    measure.target_value = 24  # 24 hours target
    measure.target_unit = MagicMock()
    measure.target_unit.value = "hours"
    measure.is_active = True
    return measure


@pytest.fixture
def mock_milestone():
    """Create a mock in-progress milestone."""
    milestone = MagicMock()
    milestone.milestone_type = MagicMock()
    milestone.milestone_type.value = "appraisal_ordered"
    milestone.loan_id = 1
    milestone.lead_id = None
    milestone.started_at = datetime.now(timezone.utc) - timedelta(hours=22)  # 22 hours ago (at risk)
    milestone.completed_at = None
    return milestone


@pytest.fixture
def agent(mock_db):
    """Create SLA monitoring agent with mock db."""
    return SLAMonitoringAgent(mock_db, organization_id=1)


# =============================================================================
# UNIT TESTS - Role Mapping
# =============================================================================

class TestMilestoneRoleMapping:
    """Test milestone to team member role mapping."""

    def test_appraisal_maps_to_processor(self):
        """Appraisal milestones should be assigned to processor."""
        assert MILESTONE_ROLE_MAPPING["appraisal_ordered"] == "processor"
        assert MILESTONE_ROLE_MAPPING["appraisal_received"] == "processor"

    def test_title_maps_to_processor(self):
        """Title milestones should be assigned to processor."""
        assert MILESTONE_ROLE_MAPPING["title_ordered"] == "processor"
        assert MILESTONE_ROLE_MAPPING["title_received"] == "processor"

    def test_flood_insurance_maps_to_processor(self):
        """Flood insurance milestones should be assigned to processor."""
        assert MILESTONE_ROLE_MAPPING["flood_insurance_ordered"] == "processor"
        assert MILESTONE_ROLE_MAPPING["flood_insurance_received"] == "processor"

    def test_hazard_insurance_maps_to_processor(self):
        """Hazard insurance milestones should be assigned to processor."""
        assert MILESTONE_ROLE_MAPPING["hazard_insurance_ordered"] == "processor"
        assert MILESTONE_ROLE_MAPPING["hazard_insurance_received"] == "processor"

    def test_underwriting_maps_to_underwriter(self):
        """Underwriting milestones should be assigned to underwriter."""
        assert MILESTONE_ROLE_MAPPING["submitted_to_uw"] == "underwriter"
        assert MILESTONE_ROLE_MAPPING["approved"] == "underwriter"

    def test_closing_maps_to_closer(self):
        """Closing milestones should be assigned to closer."""
        assert MILESTONE_ROLE_MAPPING["clear_to_close"] == "closer"
        assert MILESTONE_ROLE_MAPPING["funded"] == "closer"

    def test_lead_milestones_map_to_lo(self):
        """Lead stage milestones should be assigned to loan officer."""
        assert MILESTONE_ROLE_MAPPING["lead_response"] == "loan_officer"
        assert MILESTONE_ROLE_MAPPING["pre_qualified"] == "loan_officer"


# =============================================================================
# UNIT TESTS - Date Field Mapping
# =============================================================================

class TestMilestoneDateFields:
    """Test milestone to database field mapping."""

    def test_processing_fields_mapped(self):
        """Processing log fields should be mapped correctly."""
        assert MILESTONE_DATE_FIELDS["appraisal_ordered"] == "appraisal_ordered_date"
        assert MILESTONE_DATE_FIELDS["appraisal_received"] == "appraisal_received_date"
        assert MILESTONE_DATE_FIELDS["flood_insurance_ordered"] == "flood_insurance_ordered_date"
        assert MILESTONE_DATE_FIELDS["flood_insurance_received"] == "flood_insurance_received_date"

    def test_important_dates_mapped(self):
        """Important milestone dates should be mapped correctly."""
        assert MILESTONE_DATE_FIELDS["approved"] == "approved_date"
        assert MILESTONE_DATE_FIELDS["clear_to_close"] == "clear_to_close_date"
        assert MILESTONE_DATE_FIELDS["funded"] == "funded_date"


# =============================================================================
# UNIT TESTS - Alert Level
# =============================================================================

class TestAlertLevel:
    """Test alert level enumeration."""

    def test_alert_levels_exist(self):
        """Alert levels should be defined correctly."""
        assert AlertLevel.AT_RISK.value == "at_risk"
        assert AlertLevel.BREACHED.value == "breached"


# =============================================================================
# UNIT TESTS - SLA Monitoring Agent
# =============================================================================

class TestSLAMonitoringAgent:
    """Test SLA monitoring agent functionality."""

    def test_agent_initialization(self, mock_db):
        """Agent should initialize with correct thresholds."""
        agent = SLAMonitoringAgent(mock_db, organization_id=1)

        assert agent.db == mock_db
        assert agent.organization_id == 1
        assert agent.warning_threshold_pct == 90
        assert agent.critical_threshold_pct == 100

    def test_run_monitoring_alias(self, agent):
        """run_monitoring should be an alias for run_monitoring_cycle."""
        with patch.object(agent, 'run_monitoring_cycle', return_value={"test": True}) as mock_cycle:
            result = agent.run_monitoring()
            mock_cycle.assert_called_once()
            assert result == {"test": True}

    def test_get_target_hours_from_hours(self, agent):
        """Should return hours directly when unit is hours."""
        mock_measure = MagicMock()
        mock_measure.target_value = 24

        # Mock TimeUnit
        with patch('services.sla_monitoring_agent.TimeUnit') as mock_time_unit:
            mock_time_unit.HOURS = "hours"
            mock_measure.target_unit = "hours"

            result = agent._get_target_hours(mock_measure)
            assert result == 24

    def test_get_target_hours_from_days(self, agent):
        """Should convert days to hours (24 hours per day)."""
        mock_measure = MagicMock()
        mock_measure.target_value = 2  # 2 days

        with patch('services.sla_monitoring_agent.TimeUnit') as mock_time_unit:
            mock_time_unit.HOURS = "hours"
            mock_time_unit.DAYS = "days"
            mock_measure.target_unit = "days"

            result = agent._get_target_hours(mock_measure)
            assert result == 48  # 2 days * 24 hours

    def test_get_target_hours_from_business_days(self, agent):
        """Should convert business days to hours (8 hours per day)."""
        mock_measure = MagicMock()
        mock_measure.target_value = 2  # 2 business days

        with patch('services.sla_monitoring_agent.TimeUnit') as mock_time_unit:
            mock_time_unit.HOURS = "hours"
            mock_time_unit.DAYS = "days"
            mock_time_unit.BUSINESS_DAYS = "business_days"
            mock_measure.target_unit = "business_days"

            result = agent._get_target_hours(mock_measure)
            assert result == 16  # 2 business days * 8 hours


# =============================================================================
# UNIT TESTS - Milestone Check
# =============================================================================

class TestMilestoneCheck:
    """Test MilestoneCheck dataclass."""

    def test_milestone_check_creation(self):
        """Should create MilestoneCheck with all fields."""
        now = datetime.now(timezone.utc)
        target = now + timedelta(hours=24)

        check = MilestoneCheck(
            milestone_type="appraisal_ordered",
            loan_id=1,
            lead_id=None,
            loan_number="LN-2024-001",
            borrower_name="John Doe",
            started_at=now,
            target_deadline=target,
            elapsed_hours=22.0,
            target_hours=24.0,
            percent_elapsed=91.67,
            alert_level=AlertLevel.AT_RISK,
            assigned_to_role="processor",
            assigned_to_id=5,
            assigned_to_name="Jane Smith"
        )

        assert check.milestone_type == "appraisal_ordered"
        assert check.loan_id == 1
        assert check.percent_elapsed == 91.67
        assert check.alert_level == AlertLevel.AT_RISK
        assert check.assigned_to_role == "processor"


# =============================================================================
# INTEGRATION TESTS - Task Description
# =============================================================================

class TestTaskDescription:
    """Test task description generation."""

    def test_generate_at_risk_description(self, agent):
        """Should generate correct description for at-risk milestone."""
        now = datetime.now(timezone.utc)
        check = MilestoneCheck(
            milestone_type="appraisal_ordered",
            loan_id=1,
            lead_id=None,
            loan_number="LN-2024-001",
            borrower_name="John Doe",
            started_at=now - timedelta(hours=22),
            target_deadline=now + timedelta(hours=2),
            elapsed_hours=22.0,
            target_hours=24.0,
            percent_elapsed=91.67,
            alert_level=AlertLevel.AT_RISK,
            assigned_to_role="processor",
            assigned_to_id=5,
            assigned_to_name="Jane Smith"
        )

        description = agent._generate_task_description(check)

        assert "At Risk" in description
        assert "91.7%" in description
        assert "Appraisal Ordered" in description
        assert "LN-2024-001" in description
        assert "John Doe" in description

    def test_generate_breached_description(self, agent):
        """Should generate correct description for breached milestone."""
        now = datetime.now(timezone.utc)
        check = MilestoneCheck(
            milestone_type="appraisal_ordered",
            loan_id=1,
            lead_id=None,
            loan_number="LN-2024-001",
            borrower_name="John Doe",
            started_at=now - timedelta(hours=30),
            target_deadline=now - timedelta(hours=6),
            elapsed_hours=30.0,
            target_hours=24.0,
            percent_elapsed=125.0,
            alert_level=AlertLevel.BREACHED,
            assigned_to_role="processor",
            assigned_to_id=5,
            assigned_to_name="Jane Smith"
        )

        description = agent._generate_task_description(check)

        assert "OVERDUE" in description
        assert "25.0%" in description  # 125 - 100 = 25% over
        assert "Appraisal Ordered" in description


# =============================================================================
# INTEGRATION TESTS - Monitoring Status
# =============================================================================

class TestMonitoringStatus:
    """Test get_monitoring_status method."""

    def test_get_monitoring_status_returns_structure(self, agent):
        """Should return proper status structure."""
        # Mock the methods
        agent._get_active_sla_measures = MagicMock(return_value={})
        agent._get_in_progress_milestones = MagicMock(return_value=[])

        # Mock the tasks query
        agent.db.execute.return_value.fetchall.return_value = []

        status = agent.get_monitoring_status()

        assert "timestamp" in status
        assert "total_active" in status
        assert "at_risk" in status
        assert "overdue" in status
        assert "recent_tasks" in status
        assert status["total_active"] == 0
        assert status["at_risk"] == []
        assert status["overdue"] == []


# =============================================================================
# INTEGRATION TESTS - Full Monitoring Cycle
# =============================================================================

class TestMonitoringCycle:
    """Test complete monitoring cycle."""

    def test_monitoring_cycle_with_no_milestones(self, agent):
        """Should handle empty pipeline gracefully."""
        agent._get_active_sla_measures = MagicMock(return_value={})
        agent._get_in_progress_milestones = MagicMock(return_value=[])

        results = agent.run_monitoring_cycle()

        assert results["status"] == "success" or "milestones_checked" in results
        assert results["milestones_checked"] == 0
        assert results["at_risk_count"] == 0
        assert results["breached_count"] == 0
        assert results["tasks_created"] == 0

    def test_monitoring_cycle_commits_on_success(self, agent):
        """Should commit database changes on successful run."""
        agent._get_active_sla_measures = MagicMock(return_value={})
        agent._get_in_progress_milestones = MagicMock(return_value=[])

        agent.run_monitoring_cycle()

        agent.db.commit.assert_called_once()

    def test_monitoring_cycle_rollback_on_error(self, agent):
        """Should rollback on error."""
        agent._get_active_sla_measures = MagicMock(side_effect=Exception("DB Error"))

        results = agent.run_monitoring_cycle()

        assert len(results["errors"]) > 0
        agent.db.rollback.assert_called_once()


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
