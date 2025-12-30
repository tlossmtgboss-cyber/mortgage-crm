"""
Standalone Test Script for SLA Monitoring Agent

This script tests the SLA monitoring agent without requiring the full
application dependencies.
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

# Add backend to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# Mock all the models before importing agent
mock_sla_tracking = MagicMock()
mock_sla_tracking.SLAMeasure = MagicMock()
mock_sla_tracking.LoanMilestoneHistory = MagicMock()
mock_sla_tracking.SLAStatus = MagicMock()
mock_sla_tracking.SLAAlert = MagicMock()
mock_sla_tracking.AlertStatus = MagicMock()
mock_sla_tracking.TimeUnit = MagicMock()
mock_sla_tracking.TimeUnit.HOURS = "hours"
mock_sla_tracking.TimeUnit.DAYS = "days"
mock_sla_tracking.TimeUnit.BUSINESS_DAYS = "business_days"

sys.modules['models'] = MagicMock()
sys.modules['models.sla_tracking'] = mock_sla_tracking
sys.modules['database'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.orm'] = MagicMock()

# Import the agent module directly
import importlib.util
agent_path = os.path.join(backend_dir, 'services', 'sla_monitoring_agent.py')
spec = importlib.util.spec_from_file_location("sla_monitoring_agent", agent_path)
sla_agent_module = importlib.util.module_from_spec(spec)
sys.modules['sla_monitoring_agent'] = sla_agent_module
spec.loader.exec_module(sla_agent_module)

# Get the classes we need
SLAMonitoringAgent = sla_agent_module.SLAMonitoringAgent
AlertLevel = sla_agent_module.AlertLevel
MilestoneCheck = sla_agent_module.MilestoneCheck
MILESTONE_ROLE_MAPPING = sla_agent_module.MILESTONE_ROLE_MAPPING
MILESTONE_DATE_FIELDS = sla_agent_module.MILESTONE_DATE_FIELDS

# Test results
passed = 0
failed = 0


def test(name):
    """Decorator for test functions."""
    def decorator(func):
        def wrapper():
            global passed, failed
            try:
                func()
                print(f"  ✓ {name}")
                passed += 1
            except AssertionError as e:
                print(f"  ✗ {name}")
                print(f"    Error: {e}")
                failed += 1
            except Exception as e:
                print(f"  ✗ {name}")
                print(f"    Exception: {type(e).__name__}: {e}")
                failed += 1
        return wrapper
    return decorator


# =============================================================================
# TEST: Role Mapping
# =============================================================================
print("\n=== Testing Role Mapping ===")


@test("Appraisal milestones map to processor")
def test_appraisal_maps_to_processor():
    assert MILESTONE_ROLE_MAPPING["appraisal_ordered"] == "processor"
    assert MILESTONE_ROLE_MAPPING["appraisal_received"] == "processor"


@test("Title milestones map to processor")
def test_title_maps_to_processor():
    assert MILESTONE_ROLE_MAPPING["title_ordered"] == "processor"
    assert MILESTONE_ROLE_MAPPING["title_received"] == "processor"


@test("Flood insurance milestones map to processor")
def test_flood_insurance_maps_to_processor():
    assert MILESTONE_ROLE_MAPPING["flood_insurance_ordered"] == "processor"
    assert MILESTONE_ROLE_MAPPING["flood_insurance_received"] == "processor"


@test("Hazard insurance milestones map to processor")
def test_hazard_insurance_maps_to_processor():
    assert MILESTONE_ROLE_MAPPING["hazard_insurance_ordered"] == "processor"
    assert MILESTONE_ROLE_MAPPING["hazard_insurance_received"] == "processor"


@test("Underwriting milestones map to underwriter")
def test_underwriting_maps_to_underwriter():
    assert MILESTONE_ROLE_MAPPING["submitted_to_uw"] == "underwriter"
    assert MILESTONE_ROLE_MAPPING["approved"] == "underwriter"


@test("Closing milestones map to closer")
def test_closing_maps_to_closer():
    assert MILESTONE_ROLE_MAPPING["clear_to_close"] == "closer"
    assert MILESTONE_ROLE_MAPPING["funded"] == "closer"


@test("Lead milestones map to loan officer")
def test_lead_milestones_map_to_lo():
    assert MILESTONE_ROLE_MAPPING["lead_response"] == "loan_officer"
    assert MILESTONE_ROLE_MAPPING["pre_qualified"] == "loan_officer"


# Run all role mapping tests
test_appraisal_maps_to_processor()
test_title_maps_to_processor()
test_flood_insurance_maps_to_processor()
test_hazard_insurance_maps_to_processor()
test_underwriting_maps_to_underwriter()
test_closing_maps_to_closer()
test_lead_milestones_map_to_lo()


# =============================================================================
# TEST: Date Field Mapping
# =============================================================================
print("\n=== Testing Date Field Mapping ===")


@test("Processing date fields mapped correctly")
def test_processing_fields_mapped():
    assert MILESTONE_DATE_FIELDS["appraisal_ordered"] == "appraisal_ordered_date"
    assert MILESTONE_DATE_FIELDS["appraisal_received"] == "appraisal_received_date"
    assert MILESTONE_DATE_FIELDS["flood_insurance_ordered"] == "flood_insurance_ordered_date"
    assert MILESTONE_DATE_FIELDS["flood_insurance_received"] == "flood_insurance_received_date"


@test("Important milestone dates mapped correctly")
def test_important_dates_mapped():
    assert MILESTONE_DATE_FIELDS["approved"] == "approved_date"
    assert MILESTONE_DATE_FIELDS["clear_to_close"] == "clear_to_close_date"
    assert MILESTONE_DATE_FIELDS["funded"] == "funded_date"


test_processing_fields_mapped()
test_important_dates_mapped()


# =============================================================================
# TEST: Alert Levels
# =============================================================================
print("\n=== Testing Alert Levels ===")


@test("Alert levels defined correctly")
def test_alert_levels_exist():
    assert AlertLevel.AT_RISK.value == "at_risk"
    assert AlertLevel.BREACHED.value == "breached"


test_alert_levels_exist()


# =============================================================================
# TEST: SLA Monitoring Agent Initialization
# =============================================================================
print("\n=== Testing SLA Monitoring Agent ===")


@test("Agent initializes with correct thresholds")
def test_agent_initialization():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    assert agent.db == mock_db
    assert agent.organization_id == 1
    assert agent.warning_threshold_pct == 90
    assert agent.critical_threshold_pct == 100


@test("run_monitoring is alias for run_monitoring_cycle")
def test_run_monitoring_alias():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    with patch.object(agent, 'run_monitoring_cycle', return_value={"test": True}) as mock_cycle:
        result = agent.run_monitoring()
        mock_cycle.assert_called_once()
        assert result == {"test": True}


test_agent_initialization()
test_run_monitoring_alias()


# =============================================================================
# TEST: Milestone Check Dataclass
# =============================================================================
print("\n=== Testing MilestoneCheck Dataclass ===")


@test("MilestoneCheck creates with all fields")
def test_milestone_check_creation():
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


test_milestone_check_creation()


# =============================================================================
# TEST: Task Description Generation
# =============================================================================
print("\n=== Testing Task Description Generation ===")


@test("At-risk description contains correct info")
def test_generate_at_risk_description():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

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


@test("Breached description contains OVERDUE")
def test_generate_breached_description():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

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


test_generate_at_risk_description()
test_generate_breached_description()


# =============================================================================
# TEST: Monitoring Cycle
# =============================================================================
print("\n=== Testing Monitoring Cycle ===")


@test("Monitoring cycle handles empty pipeline")
def test_monitoring_cycle_with_no_milestones():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    agent._get_active_sla_measures = MagicMock(return_value={})
    agent._get_in_progress_milestones = MagicMock(return_value=[])

    results = agent.run_monitoring_cycle()

    assert results["milestones_checked"] == 0
    assert results["at_risk_count"] == 0
    assert results["breached_count"] == 0
    assert results["tasks_created"] == 0


@test("Monitoring cycle commits on success")
def test_monitoring_cycle_commits():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    agent._get_active_sla_measures = MagicMock(return_value={})
    agent._get_in_progress_milestones = MagicMock(return_value=[])

    agent.run_monitoring_cycle()

    mock_db.commit.assert_called_once()


@test("Monitoring cycle rolls back on error")
def test_monitoring_cycle_rollback():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    agent._get_active_sla_measures = MagicMock(side_effect=Exception("DB Error"))

    results = agent.run_monitoring_cycle()

    assert len(results["errors"]) > 0
    mock_db.rollback.assert_called_once()


test_monitoring_cycle_with_no_milestones()
test_monitoring_cycle_commits()
test_monitoring_cycle_rollback()


# =============================================================================
# TEST: Get Monitoring Status
# =============================================================================
print("\n=== Testing Get Monitoring Status ===")


@test("Get monitoring status returns proper structure")
def test_get_monitoring_status():
    mock_db = MagicMock()
    agent = SLAMonitoringAgent(mock_db, organization_id=1)

    agent._get_active_sla_measures = MagicMock(return_value={})
    agent._get_in_progress_milestones = MagicMock(return_value=[])
    mock_db.execute.return_value.fetchall.return_value = []

    status = agent.get_monitoring_status()

    assert "timestamp" in status
    assert "total_active" in status
    assert "at_risk" in status
    assert "overdue" in status
    assert "recent_tasks" in status
    assert status["total_active"] == 0
    assert status["at_risk"] == []
    assert status["overdue"] == []


test_get_monitoring_status()


# =============================================================================
# TEST SUMMARY
# =============================================================================
print("\n" + "=" * 50)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 50)

if failed > 0:
    print("\n❌ Some tests failed!")
    sys.exit(1)
else:
    print("\n✅ All tests passed!")
    sys.exit(0)
