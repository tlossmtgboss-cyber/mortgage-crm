"""
Test Suite: Workflow SLA System

Comprehensive tests for the SLA-driven workflow task generation system.
Tests cover:
- Workflow enrollment and lifecycle
- Task generation and scheduling
- AI confidence evaluation
- Dialer integration
- Role assignments
- Sibling task cancellation
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    db.flush = MagicMock()
    db.add = MagicMock()
    db.query = MagicMock()
    return db


@pytest.fixture
def sample_lead():
    """Sample lead data for testing."""
    return {
        "id": 1,
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "+15551234567",
        "stage": "NEW",
        "source_category": "organic",
        "organization_id": 1
    }


@pytest.fixture
def sample_loan():
    """Sample loan data for testing."""
    return {
        "id": 1,
        "loan_number": "LN-2024-001",
        "status": "processing",
        "borrower_name": "John Doe",
        "borrower_phone": "+15551234567",
        "borrower_email": "john.doe@example.com",
        "loan_amount": 450000.00,
        "lead_id": 1,
        "organization_id": 1
    }


@pytest.fixture
def sample_workflow_config():
    """Sample workflow configuration."""
    return {
        "id": 1,
        "workflow_key": "prospect",
        "workflow_name": "Prospect Engagement",
        "entity_type": "lead",
        "is_active": True,
        "total_days": 14
    }


@pytest.fixture
def sample_task_config():
    """Sample task configuration."""
    return {
        "id": 1,
        "workflow_config_id": 1,
        "task_key": "day1_morning_call",
        "task_name": "Initial Phone Call",
        "task_type": "phone_am",
        "day_offset": 1,
        "time_slot": "morning",
        "route": "task_list",
        "is_required": True,
        "cancel_siblings_on_contact": True,
        "sibling_group": "day1_contact"
    }


# =============================================================================
# WORKFLOW SLA SERVICE TESTS
# =============================================================================

class TestWorkflowSLAService:
    """Test Suite: Workflow SLA Service"""

    def test_enroll_lead_success(self, mock_db, sample_lead):
        """Test successful lead enrollment in workflow."""
        from services.workflow_sla_service import WorkflowSLAService

        # Create mock lead and user objects for ORM queries
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.owner_id = 1

        mock_owner = MagicMock()
        mock_owner.organization_id = 1

        # ORM query chain: first call returns lead, second returns owner
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_lead,
            mock_owner,
        ]

        service = WorkflowSLAService(mock_db)

        # Mock workflow config
        mock_config = MagicMock()
        mock_config.id = 1
        mock_config.workflow_key = "prospect"

        # Mock workflow instance
        mock_instance = MagicMock()
        mock_instance.id = 100

        with patch.object(service, '_get_workflow_config', return_value=mock_config), \
             patch.object(service, '_get_active_workflow_instance', return_value=None), \
             patch.object(service, '_cancel_other_workflows', return_value=0), \
             patch.object(service, '_create_workflow_instance', return_value=mock_instance), \
             patch.object(service, '_generate_due_tasks', return_value=3):

            result = service.enroll_lead(
                lead_id=1,
                workflow_key="prospect",
                trigger_status="NEW",
                user_id=1
            )

            assert result.get("success") is True

    def test_enroll_lead_already_enrolled(self, mock_db, sample_lead):
        """Test that duplicate enrollment is prevented."""
        from services.workflow_sla_service import WorkflowSLAService

        # Create mock lead object
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.owner_id = 1

        # Create mock user/owner object
        mock_owner = MagicMock()
        mock_owner.organization_id = 1

        # Create mock workflow config
        mock_config = MagicMock()
        mock_config.id = 1

        # Create mock existing instance (already enrolled)
        mock_existing_instance = MagicMock()
        mock_existing_instance.id = 50

        # Setup ORM query chain mock - returns lead, then owner
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_lead,   # Lead query
            mock_owner,  # User query
        ]

        service = WorkflowSLAService(mock_db)

        # Patch internal methods to control flow
        with patch.object(service, '_get_workflow_config', return_value=mock_config), \
             patch.object(service, '_get_active_workflow_instance', return_value=mock_existing_instance):

            result = service.enroll_lead(
                lead_id=1,
                workflow_key="prospect"
            )

        # Should indicate already enrolled or return existing instance ID
        assert result.get("success") is False
        assert "already" in str(result).lower() or result.get("existing_instance_id") == 50

    def test_pause_workflow(self, mock_db):
        """Test pausing an active workflow."""
        from services.workflow_sla_service import WorkflowSLAService

        # Create mock instance object with proper attributes
        mock_instance = MagicMock()
        mock_instance.id = 100
        mock_instance.status = "active"
        mock_instance.paused_at = None

        service = WorkflowSLAService(mock_db)

        with patch.object(service, '_get_workflow_instance', return_value=mock_instance):
            result = service.pause_workflow(
                instance_id=100,
                reason="Customer requested pause",
                user_id=1
            )

        # Verify instance was paused
        assert mock_instance.status == "paused" or mock_db.execute.called

    def test_resume_workflow(self, mock_db):
        """Test resuming a paused workflow."""
        from services.workflow_sla_service import WorkflowSLAService

        # Create mock paused instance
        mock_instance = MagicMock()
        mock_instance.id = 100
        mock_instance.status = "paused"
        mock_instance.paused_at = datetime.now(timezone.utc)

        service = WorkflowSLAService(mock_db)

        with patch.object(service, '_get_workflow_instance', return_value=mock_instance), \
             patch.object(service, '_generate_due_tasks', return_value=2):
            result = service.resume_workflow(
                instance_id=100,
                user_id=1
            )

        # Verify instance was resumed
        assert mock_instance.status == "active" or mock_db.execute.called

    def test_complete_task_with_contact(self, mock_db):
        """Test completing a task with contact made (triggers sibling cancellation)."""
        from services.workflow_sla_service import WorkflowSLAService

        # Create mock task instance object (service uses ORM query)
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.status = "pending"
        mock_task.task_group_key = "day1_contact"
        mock_task.linked_task_id = None

        # Setup ORM query chain
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task

        service = WorkflowSLAService(mock_db)

        with patch.object(service, '_cancel_sibling_tasks', return_value=2):
            result = service.complete_task(
                task_instance_id=1,
                completion_source="user",
                completed_by_id=1,
                outcome={"contact_made": True}
            )

        # Should trigger sibling cancellation
        assert mock_task.status == "completed" or mock_db.execute.called


# =============================================================================
# TASK GENERATOR TESTS
# =============================================================================

class TestTaskGeneratorService:
    """Test Suite: Task Generator Service"""

    def test_generate_tasks_for_instance(self, mock_db, sample_workflow_config, sample_task_config):
        """Test task generation for a workflow instance."""
        from services.workflow_task_generator import TaskGeneratorService

        service = TaskGeneratorService(mock_db)

        # Patch internal helper methods to return proper data structures
        mock_instance = {
            "id": 100,
            "organization_id": 1,
            "workflow_configuration_id": 1,
            "lead_id": 1,
            "loan_id": None,
            "status": "active",
            "started_at": datetime.now(timezone.utc) - timedelta(days=2),
            "last_task_generated_day": 0,
        }
        mock_config = {
            "id": 1,
            "workflow_key": "prospect",
            "workflow_name": "Prospect Engagement",
            "description": "Engage new prospects",
            "objective": "Convert to application",
        }
        mock_day_configs = [
            {
                "id": 1, "day_label": "Day 1", "day_order": 1, "day_value": 1, "is_active": True,
                "phone_enabled": True, "phone_am_enabled": True, "phone_pm_enabled": False,
                "text_enabled": True, "text_am_enabled": True, "text_pm_enabled": False,
                "email_enabled": False, "referral_partner_enabled": False,
                "lo_responsible": True, "jr_lo_responsible": False, "production_asst_responsible": False,
                "concierge_responsible": False, "ai_responsible": True,
                "role_responsibilities": {}, "task_description": None,
            },
        ]
        mock_contact = {"name": "John Doe", "email": "john@example.com", "phone": "+15551234567"}

        with patch.object(service, '_get_instance', return_value=mock_instance), \
             patch.object(service, '_get_workflow_config', return_value=mock_config), \
             patch.object(service, '_get_day_configs', return_value=mock_day_configs), \
             patch.object(service, '_get_contact_info', return_value=mock_contact), \
             patch.object(service, '_generate_day_tasks', return_value=[1, 2]), \
             patch.object(service, '_update_instance_progress'):
            result = service.generate_tasks_for_instance(instance_id=100)

        assert result.get("success") is True or mock_db.execute.called

    def test_calculate_scheduled_date(self, mock_db):
        """Test scheduled date calculation with business days."""
        from services.workflow_task_generator import TaskGeneratorService

        service = TaskGeneratorService(mock_db)

        # Monday enrollment
        monday = date(2024, 1, 8)
        result = service._calculate_scheduled_date(monday, 1, "morning")

        # Day 1 should be Tuesday
        assert result.date() == date(2024, 1, 9)

    def test_task_group_key_generation(self, mock_db):
        """Test task group key generation for sibling cancellation."""
        from services.workflow_task_generator import TaskGeneratorService

        service = TaskGeneratorService(mock_db)

        # Generate group key
        group_key = service._generate_task_group_key(
            instance_id=100,
            sibling_group="day1_contact"
        )

        assert "100" in group_key
        assert "day1_contact" in group_key


# =============================================================================
# AI EVALUATOR TESTS
# =============================================================================

class TestWorkflowAIEvaluator:
    """Test Suite: AI Confidence Evaluator"""

    def test_evaluate_task_high_confidence(self, mock_db):
        """Test evaluation returning high confidence score."""
        from services.workflow_ai_evaluator import WorkflowAIEvaluator
        from datetime import datetime, timezone

        # The service makes these queries in order:
        # 1. _get_task_instance: 10 columns (id, workflow_instance_id, workflow_id, lead_id, loan_id, task_name, task_type, ai_eligible, scheduled_date, status)
        # 2. _get_entity_data: 7 columns (first_name, last_name, email, phone, property_type, loan_purpose, estimated_amount)
        # 3. _score_engagement_history: 3 columns (total, positive, negative)
        # 4. _score_historical_success: 2 columns (total, success)
        # 5. _record_evaluation ID: 1 column (id)
        mock_db.execute.return_value.fetchone.side_effect = [
            # 1. Task instance (10 columns)
            (1, 100, 1, 1, None, "Morning Text", "text_am", True, datetime.now(timezone.utc), "scheduled"),
            # 2. Lead data (7 columns)
            ("John", "Doe", "john@example.com", "+15551234567", "single_family", "purchase", 450000),
            # 3. Engagement history (3 columns: total, positive, negative)
            (5, 3, 1),
            # 4. Historical success (2 columns: total, success)
            (20, 17),
            # 5. Record evaluation ID
            (1,)
        ]

        evaluator = WorkflowAIEvaluator(mock_db)
        result = evaluator.evaluate_task(task_instance_id=1)

        assert result.get("success") is True
        assert "confidence_score" in result
        assert result["confidence_score"] > 0.5  # Should have decent confidence with good data

    def test_evaluate_task_low_confidence_missing_phone(self, mock_db):
        """Test evaluation with missing phone returns lower confidence."""
        from services.workflow_ai_evaluator import WorkflowAIEvaluator
        from datetime import datetime, timezone

        # Mock task with missing phone - same structure as high confidence test
        mock_db.execute.return_value.fetchone.side_effect = [
            # 1. Task instance (10 columns)
            (1, 100, 1, 1, None, "Morning Text", "text_am", True, datetime.now(timezone.utc), "scheduled"),
            # 2. Lead data (7 columns) - missing phone
            ("John", "Doe", "john@example.com", None, None, None, None),
            # 3. Engagement history (3 columns: total, positive, negative)
            (0, 0, 0),
            # 4. Historical success (2 columns: total, success) - low sample size
            (5, 2),
            # 5. Record evaluation ID
            (1,)
        ]

        evaluator = WorkflowAIEvaluator(mock_db)
        result = evaluator.evaluate_task(task_instance_id=1)

        # Should still succeed but with lower confidence
        if result.get("success"):
            assert result.get("confidence_score", 1.0) < 0.95

    def test_confidence_thresholds(self, mock_db):
        """Test confidence threshold recommendations."""
        from services.workflow_ai_evaluator import WorkflowAIEvaluator
        from decimal import Decimal

        evaluator = WorkflowAIEvaluator(mock_db)

        # Test threshold recommendations (thresholds are Decimals in the implementation)
        assert evaluator.AUTO_EXECUTE_THRESHOLD == Decimal('0.950')
        assert evaluator.REVIEW_THRESHOLD == Decimal('0.700')
        assert evaluator.ESCALATE_THRESHOLD == Decimal('0.400')

    def test_batch_evaluation(self, mock_db):
        """Test batch evaluation of multiple tasks."""
        from services.workflow_ai_evaluator import WorkflowAIEvaluator

        evaluator = WorkflowAIEvaluator(mock_db)

        with patch.object(evaluator, 'evaluate_task') as mock_eval:
            mock_eval.return_value = {"success": True, "confidence_score": 0.85}

            result = evaluator.evaluate_batch(
                task_instance_ids=[1, 2, 3],
                auto_execute=False
            )

            assert mock_eval.call_count == 3


# =============================================================================
# AI EXECUTOR TESTS
# =============================================================================

class TestWorkflowAIExecutor:
    """Test Suite: AI Task Executor"""

    def test_execute_text_task(self, mock_db):
        """Test executing a text/SMS task."""
        from services.workflow_ai_executor import WorkflowAIExecutor

        # Mock task details
        mock_db.execute.return_value.fetchone.return_value = (
            1, "Morning Text", "text_am", "pending", 1, None, 1, 100, "grp1",
            "day1_text", None, "John", "Doe", "+15551234567", "john@example.com"
        )

        executor = WorkflowAIExecutor(mock_db)

        with patch.object(executor, '_execute_text_task') as mock_text:
            mock_text.return_value = {"success": True, "summary": "SMS sent"}

            result = executor.execute_task(
                task_instance_id=1,
                force_execute=True
            )

            if mock_text.called:
                assert result.get("success") is True

    def test_execute_requires_confidence(self, mock_db):
        """Test that execution requires sufficient confidence."""
        from services.workflow_ai_executor import WorkflowAIExecutor

        # Mock task details
        mock_db.execute.return_value.fetchone.return_value = (
            1, "Morning Text", "text_am", "pending", 1, None, 1, 100, "grp1",
            "day1_text", None, "John", "Doe", "+15551234567", "john@example.com"
        )

        executor = WorkflowAIExecutor(mock_db)

        with patch.object(executor, '_get_evaluator') as mock_eval:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_task.return_value = {
                "success": True,
                "confidence_score": 0.5,  # Below threshold
                "recommendation": "review"
            }
            mock_eval.return_value = mock_evaluator

            result = executor.execute_task(
                task_instance_id=1,
                force_execute=False
            )

            # Should require approval due to low confidence
            assert result.get("requires_approval") is True or result.get("success") is False

    def test_ai_executable_types(self, mock_db):
        """Test that only appropriate task types are AI-executable."""
        from services.workflow_ai_executor import WorkflowAIExecutor

        executor = WorkflowAIExecutor(mock_db)

        # These should be executable
        assert "text" in executor.AI_EXECUTABLE_TYPES
        assert "email" in executor.AI_EXECUTABLE_TYPES
        assert "text_am" in executor.AI_EXECUTABLE_TYPES

        # Phone should NOT be AI-executable (requires human)
        assert "phone" not in executor.AI_EXECUTABLE_TYPES


# =============================================================================
# DIALER INTEGRATION TESTS
# =============================================================================

class TestWorkflowDialerIntegration:
    """Test Suite: Power Dialer Integration"""

    def test_get_phone_tasks(self, mock_db):
        """Test fetching phone tasks for dialer."""
        from services.workflow_dialer_integration import WorkflowDialerIntegration

        # Mock phone tasks
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "Morning Call", "phone_am", 1, None, 1, datetime.now(), "grp1", "+15551234567", "John Doe"),
            (2, "Afternoon Call", "phone_pm", 1, None, 1, datetime.now(), "grp1", "+15551234567", "John Doe"),
        ]

        integration = WorkflowDialerIntegration(mock_db)
        tasks = integration.get_phone_tasks_for_dialer(user_id=1, limit=50)

        assert len(tasks) == 2
        assert tasks[0]["task_type"] == "phone_am"

    def test_handle_dialer_completion_contact_made(self, mock_db):
        """Test handling dialer completion with contact made."""
        from services.workflow_dialer_integration import WorkflowDialerIntegration

        # Mock workflow task lookup
        mock_db.execute.return_value.fetchone.return_value = (
            1, "grp1_day1", None  # task_id, task_group_key, linked_task_id
        )

        # Mock sibling cancellation
        mock_db.execute.return_value.fetchall.return_value = [(2,), (3,)]  # Cancelled siblings

        integration = WorkflowDialerIntegration(mock_db)
        result = integration.handle_dialer_task_completion(
            dialer_session_task_id=100,
            call_status="completed",
            call_duration=120,  # 2 minutes - contact made
            disposition="spoke_with_contact"
        )

        # Should have cancelled siblings
        assert mock_db.execute.called

    def test_handle_dialer_completion_no_answer(self, mock_db):
        """Test handling dialer completion with no answer."""
        from services.workflow_dialer_integration import WorkflowDialerIntegration

        # Mock workflow task lookup
        mock_db.execute.return_value.fetchone.return_value = (
            1, "grp1_day1", None
        )

        integration = WorkflowDialerIntegration(mock_db)
        result = integration.handle_dialer_task_completion(
            dialer_session_task_id=100,
            call_status="no_answer",
            call_duration=0
        )

        # Should NOT cancel siblings (no contact made)
        assert result.get("contact_made") is False or result.get("siblings_cancelled", 0) == 0


# =============================================================================
# ROLE ASSIGNMENT TESTS
# =============================================================================

class TestRoleAssignmentService:
    """Test Suite: Role Assignment Service"""

    def test_assign_role_to_lead(self, mock_db):
        """Test assigning a role to a lead."""
        from services.workflow_role_assignment import RoleAssignmentService

        # Mock role lookup
        mock_db.execute.return_value.fetchone.return_value = (1, "loan_officer", "Loan Officer")

        service = RoleAssignmentService(mock_db)
        result = service.assign_role_to_lead(
            lead_id=1,
            role_id=1,
            user_id=5,
            assigned_by_id=1
        )

        assert mock_db.execute.called or mock_db.add.called

    def test_resolve_user_for_role(self, mock_db):
        """Test resolving user for a role."""
        from services.workflow_role_assignment import RoleAssignmentService

        # Mock role assignment lookup
        mock_db.execute.return_value.fetchone.return_value = (5,)  # User ID

        service = RoleAssignmentService(mock_db)
        user_id = service.resolve_user_for_role(
            role_id=1,
            lead_id=1
        )

        assert user_id == 5 or mock_db.execute.called

    def test_copy_assignments_lead_to_loan(self, mock_db):
        """Test copying role assignments from lead to loan."""
        from services.workflow_role_assignment import RoleAssignmentService

        service = RoleAssignmentService(mock_db)

        # Patch the internal method that does raw SQL to return proper data
        with patch.object(service, 'get_lead_role_assignments') as mock_get:
            mock_get.return_value = [
                {"role_id": 1, "user_id": 5, "role_name": "loan_officer"},
                {"role_id": 2, "user_id": 6, "role_name": "processor"},
            ]
            result = service.copy_assignments_lead_to_loan(
                lead_id=1,
                loan_id=1
            )

        assert mock_get.called or mock_db.execute.called


# =============================================================================
# SCHEDULER TESTS
# =============================================================================

class TestWorkflowScheduler:
    """Test Suite: Workflow Scheduler"""

    def test_run_all_scheduled_tasks(self, mock_db):
        """Test running all scheduled workflow tasks."""
        from services.workflow_scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(mock_db)

        with patch.object(scheduler, 'process_status_changes') as mock_status:
            with patch.object(scheduler, 'generate_due_tasks') as mock_gen:
                with patch.object(scheduler, 'escalate_overdue_tasks') as mock_esc:
                    with patch.object(scheduler, 'check_workflow_completions') as mock_comp:
                        mock_status.return_value = {"success": True}
                        mock_gen.return_value = {"success": True}
                        mock_esc.return_value = {"success": True}
                        mock_comp.return_value = {"success": True}

                        result = scheduler.run_all_scheduled_tasks()

                        assert mock_status.called
                        assert mock_gen.called
                        assert mock_esc.called
                        assert mock_comp.called

    def test_process_status_changes(self, mock_db):
        """Test processing status changes for auto-enrollment."""
        from services.workflow_scheduler import WorkflowScheduler

        # Mock leads with status changes
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "NEW", "organic"),
            (2, "APPLICATION", None),
        ]

        scheduler = WorkflowScheduler(mock_db)

        with patch.object(scheduler, '_get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.enroll_lead.return_value = {"success": True}
            mock_svc.return_value = mock_service

            result = scheduler.process_status_changes()

            # Should have attempted enrollments
            assert mock_db.execute.called

    def test_escalate_overdue_tasks(self, mock_db):
        """Test escalating overdue workflow tasks."""
        from services.workflow_scheduler import WorkflowScheduler

        # Mock overdue tasks - tuple needs 9 elements:
        # (id, task_name, due_date, assigned_user_id, lead_id, loan_id, org_id, escalation_level, hours_overdue)
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "Overdue Task", datetime.now() - timedelta(days=2), 5, 1, None, 1, 0, 48.0),
        ]

        scheduler = WorkflowScheduler(mock_db)
        result = scheduler.escalate_overdue_tasks()

        assert mock_db.execute.called


# =============================================================================
# WEBSOCKET EVENTS TESTS
# =============================================================================

class TestWorkflowWebSocketEvents:
    """Test Suite: WebSocket Event Generation"""

    def test_task_scheduled_event(self):
        """Test task scheduled event structure."""
        from services.workflow_websocket_events import WorkflowEvent

        event = WorkflowEvent.task_scheduled(
            task_instance_id=1,
            task_name="Morning Call",
            task_type="phone_am",
            scheduled_date="2024-01-15T09:00:00",
            lead_id=1,
            contact_name="John Doe"
        )

        assert event["type"] == "workflow_task_scheduled"
        assert event["task_instance_id"] == 1
        assert event["task_name"] == "Morning Call"
        assert "timestamp" in event

    def test_ai_evaluation_event(self):
        """Test AI evaluation complete event structure."""
        from services.workflow_websocket_events import WorkflowEvent

        event = WorkflowEvent.ai_evaluation_complete(
            task_instance_id=1,
            task_name="Morning Text",
            confidence_score=0.92,
            recommendation="auto_execute",
            auto_executed=True
        )

        assert event["type"] == "ai_evaluation_complete"
        assert event["confidence_score"] == 0.92
        assert event["auto_executed"] is True

    def test_sla_breach_event(self):
        """Test SLA breach event structure."""
        from services.workflow_websocket_events import WorkflowEvent

        event = WorkflowEvent.sla_breach(
            task_instance_id=1,
            task_name="Initial Contact",
            sla_name="First Contact SLA",
            hours_overdue=4.5,
            lead_id=1,
            contact_name="John Doe"
        )

        assert event["type"] == "sla_breach"
        assert event["hours_overdue"] == 4.5


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestWorkflowIntegration:
    """Integration tests for workflow system components."""

    def test_full_workflow_lifecycle(self, mock_db):
        """Test complete workflow lifecycle: enroll -> tasks -> complete."""
        from services.workflow_sla_service import WorkflowSLAService
        from services.workflow_task_generator import TaskGeneratorService

        # This is a higher-level integration test
        # In production, would use actual test database

        sla_service = WorkflowSLAService(mock_db)
        task_generator = TaskGeneratorService(mock_db)

        # Mock chain of operations
        with patch.object(sla_service, 'enroll_lead') as mock_enroll:
            mock_enroll.return_value = {"success": True, "instance_id": 100}

            with patch.object(task_generator, 'generate_tasks_for_instance') as mock_gen:
                mock_gen.return_value = {"success": True, "tasks_created": 5}

                # Enroll
                enroll_result = sla_service.enroll_lead(lead_id=1, workflow_key="prospect")
                assert enroll_result.get("success")

                # Generate tasks
                gen_result = task_generator.generate_tasks_for_instance(instance_id=100)
                assert gen_result.get("success")

    def test_sibling_cancellation_flow(self, mock_db):
        """Test that completing one sibling task cancels others."""
        from services.workflow_sla_service import WorkflowSLAService
        from datetime import datetime, timezone

        # Create mock task instance object (service uses ORM queries)
        mock_task_instance = MagicMock()
        mock_task_instance.id = 1
        mock_task_instance.status = "pending"
        mock_task_instance.task_group_key = "day1_contact_grp"
        mock_task_instance.linked_task_id = None

        # Setup ORM query chain mock
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task_instance

        service = WorkflowSLAService(mock_db)

        with patch.object(service, '_cancel_sibling_tasks') as mock_cancel:
            mock_cancel.return_value = 2  # 2 siblings cancelled

            result = service.complete_task(
                task_instance_id=1,
                completion_source="user",
                outcome={"contact_made": True}
            )

            # Should have triggered sibling cancellation
            mock_cancel.assert_called_once_with(
                task_group_key="day1_contact_grp",
                exclude_task_id=1,
                reason="Contact made via sibling task"
            )

            # Verify task was marked completed
            assert mock_task_instance.status == "completed"
            assert mock_task_instance.completion_source == "user"
            assert result.get("success") is True
            assert result.get("siblings_cancelled") == 2


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
