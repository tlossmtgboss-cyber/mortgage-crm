"""
API Integration Tests: Workflow SLA System

Tests the REST API endpoints for the workflow SLA system.
Uses FastAPI TestClient for endpoint testing.
"""

import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    user.organization_id = 1
    user.role = "loan_officer"
    return user


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def client(mock_user, mock_db):
    """Create test client with mocked dependencies."""
    from main import app, get_db, get_current_user

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client = TestClient(app)
    yield client

    # Clean up
    app.dependency_overrides.clear()


# =============================================================================
# ENROLLMENT ENDPOINT TESTS
# =============================================================================

class TestEnrollmentEndpoints:
    """Test workflow enrollment endpoints."""

    def test_enroll_lead_success(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/leads/{lead_id}/enroll"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.enroll_lead.return_value = {
                "success": True,
                "instance_id": 100,
                "workflow_key": "prospect"
            }
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/leads/1/enroll",
                json={"workflow_key": "prospect"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data.get("success") is True

    def test_enroll_lead_invalid_workflow(self, client, mock_db):
        """Test enrollment with invalid workflow key."""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.enroll_lead.return_value = {
                "success": False,
                "error": "Invalid workflow key"
            }
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/leads/1/enroll",
                json={"workflow_key": "invalid_workflow"}
            )

            assert response.status_code == 400

    def test_enroll_loan_success(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/loans/{loan_id}/enroll"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.enroll_loan.return_value = {
                "success": True,
                "instance_id": 101,
                "workflow_key": "under_contract"
            }
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/loans/1/enroll",
                json={"workflow_key": "under_contract"}
            )

            assert response.status_code == 200


# =============================================================================
# WORKFLOW STATUS ENDPOINT TESTS
# =============================================================================

class TestWorkflowStatusEndpoints:
    """Test workflow status endpoints."""

    def test_get_workflow_status(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/instances/{instance_id}"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.get_workflow_status.return_value = {
                "instance_id": 100,
                "workflow_key": "prospect",
                "status": "active",
                "tasks": []
            }
            mock_svc.return_value = mock_service

            response = client.get("/api/v1/workflow-sla/instances/100")

            assert response.status_code == 200
            data = response.json()
            assert data["instance_id"] == 100

    def test_get_workflow_status_not_found(self, client, mock_db):
        """Test GET for non-existent workflow."""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.get_workflow_status.return_value = None
            mock_svc.return_value = mock_service

            response = client.get("/api/v1/workflow-sla/instances/99999")

            assert response.status_code == 404

    def test_get_lead_workflows(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/leads/{lead_id}/workflows"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.get_active_workflows_for_lead.return_value = [
                {"instance_id": 100, "workflow_key": "prospect"}
            ]
            mock_svc.return_value = mock_service

            response = client.get("/api/v1/workflow-sla/leads/1/workflows")

            assert response.status_code == 200
            data = response.json()
            assert "workflows" in data


# =============================================================================
# WORKFLOW CONTROL ENDPOINT TESTS
# =============================================================================

class TestWorkflowControlEndpoints:
    """Test workflow control endpoints (pause, resume, cancel)."""

    def test_pause_workflow(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/instances/{id}/pause"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.pause_workflow.return_value = {"success": True}
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/instances/100/pause",
                json={"reason": "Customer requested"}
            )

            assert response.status_code == 200

    def test_resume_workflow(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/instances/{id}/resume"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.resume_workflow.return_value = {"success": True}
            mock_svc.return_value = mock_service

            response = client.post("/api/v1/workflow-sla/instances/100/resume")

            assert response.status_code == 200

    def test_cancel_workflow(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/instances/{id}/cancel"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.cancel_workflow.return_value = {"success": True}
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/instances/100/cancel",
                json={"reason": "Lead converted"}
            )

            assert response.status_code == 200


# =============================================================================
# TASK MANAGEMENT ENDPOINT TESTS
# =============================================================================

class TestTaskManagementEndpoints:
    """Test task management endpoints."""

    def test_complete_task(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/tasks/{id}/complete"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.complete_task.return_value = {
                "success": True,
                "siblings_cancelled": 2
            }
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/tasks/1/complete",
                json={
                    "completion_source": "user",
                    "contact_made": True
                }
            )

            assert response.status_code == 200

    def test_skip_task(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/tasks/{id}/skip"""
        with patch('routes.workflow_sla_routes.get_workflow_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.skip_task.return_value = {"success": True}
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/tasks/1/skip",
                json={"reason": "Customer unavailable"}
            )

            assert response.status_code == 200

    def test_generate_tasks(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/instances/{id}/generate-tasks"""
        with patch('routes.workflow_sla_routes.get_task_generator') as mock_gen:
            mock_generator = MagicMock()
            mock_generator.generate_tasks_for_instance.return_value = {
                "success": True,
                "tasks_created": 5
            }
            mock_gen.return_value = mock_generator

            response = client.post(
                "/api/v1/workflow-sla/instances/100/generate-tasks"
            )

            assert response.status_code == 200


# =============================================================================
# AI ENDPOINT TESTS
# =============================================================================

class TestAIEndpoints:
    """Test AI evaluation and execution endpoints."""

    def test_evaluate_task_confidence(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/ai/evaluate/{task_id}"""
        with patch('services.workflow_ai_evaluator.WorkflowAIEvaluator') as MockEval:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_task.return_value = {
                "success": True,
                "confidence_score": 0.92,
                "recommendation": "auto_execute"
            }
            MockEval.return_value = mock_evaluator

            response = client.post(
                "/api/v1/workflow-sla/ai/evaluate/1",
                json={"auto_execute": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert "confidence_score" in data

    def test_get_pending_ai_tasks(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/ai/pending-tasks"""
        with patch('services.workflow_ai_evaluator.WorkflowAIEvaluator') as MockEval:
            mock_evaluator = MagicMock()
            mock_evaluator.get_pending_ai_tasks.return_value = [
                {"task_instance_id": 1, "task_name": "Morning Text"}
            ]
            MockEval.return_value = mock_evaluator

            response = client.get("/api/v1/workflow-sla/ai/pending-tasks")

            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data

    def test_execute_ai_task(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/ai/execute/{task_id}"""
        with patch('services.workflow_ai_executor.WorkflowAIExecutor') as MockExec:
            mock_executor = MagicMock()
            mock_executor.execute_task.return_value = {
                "success": True,
                "summary": "SMS sent successfully"
            }
            MockExec.return_value = mock_executor

            response = client.post(
                "/api/v1/workflow-sla/ai/execute/1",
                json={"force_execute": True}
            )

            assert response.status_code == 200

    def test_run_autonomous_execution(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/ai/run-autonomous"""
        with patch('services.workflow_ai_executor.run_autonomous_ai_tasks') as mock_run:
            mock_run.return_value = {
                "success": True,
                "executed_count": 5
            }

            response = client.post(
                "/api/v1/workflow-sla/ai/run-autonomous?max_tasks=10"
            )

            assert response.status_code == 200


# =============================================================================
# DIALER ENDPOINT TESTS
# =============================================================================

class TestDialerEndpoints:
    """Test dialer integration endpoints."""

    def test_get_phone_tasks(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/dialer/phone-tasks"""
        with patch('services.workflow_dialer_integration.WorkflowDialerIntegration') as MockInt:
            mock_integration = MagicMock()
            mock_integration.get_phone_tasks_for_dialer.return_value = [
                {"workflow_task_id": 1, "contact_name": "John Doe"}
            ]
            MockInt.return_value = mock_integration

            response = client.get("/api/v1/workflow-sla/dialer/phone-tasks")

            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data

    def test_create_dialer_session(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/dialer/create-session"""
        with patch('services.workflow_dialer_integration.WorkflowDialerIntegration') as MockInt:
            mock_integration = MagicMock()
            mock_integration.create_dialer_session_from_workflow.return_value = {
                "success": True,
                "session_id": 50,
                "total_tasks": 5
            }
            MockInt.return_value = mock_integration

            response = client.post(
                "/api/v1/workflow-sla/dialer/create-session",
                json={"workflow_task_ids": [1, 2, 3, 4, 5]}
            )

            assert response.status_code == 200
            data = response.json()
            assert data.get("session_id") == 50

    def test_handle_dialer_completion(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/dialer/task-completion/{id}"""
        with patch('services.workflow_dialer_integration.WorkflowDialerIntegration') as MockInt:
            mock_integration = MagicMock()
            mock_integration.handle_dialer_task_completion.return_value = {
                "success": True,
                "contact_made": True,
                "siblings_cancelled": 2
            }
            MockInt.return_value = mock_integration

            response = client.post(
                "/api/v1/workflow-sla/dialer/task-completion/100",
                json={
                    "call_status": "completed",
                    "call_duration": 120
                }
            )

            assert response.status_code == 200

    def test_get_dialer_queue(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/dialer/queue"""
        with patch('services.workflow_dialer_integration.WorkflowDialerIntegration') as MockInt:
            mock_integration = MagicMock()
            mock_integration.get_dialer_queue_for_user.return_value = {
                "user_id": 1,
                "summary": {"total": 10},
                "tasks": []
            }
            MockInt.return_value = mock_integration

            response = client.get("/api/v1/workflow-sla/dialer/queue")

            assert response.status_code == 200


# =============================================================================
# SCHEDULER ENDPOINT TESTS
# =============================================================================

class TestSchedulerEndpoints:
    """Test scheduler endpoints."""

    def test_run_scheduler(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/scheduler/run"""
        with patch('routes.workflow_sla_routes.run_scheduled_workflow_tasks') as mock_run:
            mock_run.return_value = {
                "success": True,
                "operations": {}
            }

            response = client.post("/api/v1/workflow-sla/scheduler/run")

            assert response.status_code == 200

    def test_run_task_generation(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/scheduler/generate-tasks"""
        with patch('routes.workflow_sla_routes.WorkflowScheduler') as MockSched:
            mock_scheduler = MagicMock()
            mock_scheduler.generate_due_tasks.return_value = {
                "success": True,
                "tasks_generated": 10
            }
            MockSched.return_value = mock_scheduler

            response = client.post(
                "/api/v1/workflow-sla/scheduler/generate-tasks"
            )

            assert response.status_code == 200


# =============================================================================
# ROLE ASSIGNMENT ENDPOINT TESTS
# =============================================================================

class TestRoleAssignmentEndpoints:
    """Test role assignment endpoints."""

    def test_get_lead_roles(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/leads/{lead_id}/roles"""
        with patch('routes.workflow_sla_routes.get_role_assignment_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.get_lead_role_assignments.return_value = [
                {"role_id": 1, "role_name": "Loan Officer", "user_id": 5}
            ]
            mock_svc.return_value = mock_service

            response = client.get("/api/v1/workflow-sla/leads/1/roles")

            assert response.status_code == 200

    def test_assign_lead_role(self, client, mock_db):
        """Test POST /api/v1/workflow-sla/leads/{lead_id}/roles"""
        with patch('routes.workflow_sla_routes.get_role_assignment_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.assign_role_to_lead.return_value = {"success": True}
            mock_svc.return_value = mock_service

            response = client.post(
                "/api/v1/workflow-sla/leads/1/roles",
                json={"role_id": 1, "user_id": 5}
            )

            assert response.status_code == 200

    def test_get_available_roles(self, client, mock_db):
        """Test GET /api/v1/workflow-sla/roles/available"""
        with patch('routes.workflow_sla_routes.get_role_assignment_service') as mock_svc:
            mock_service = MagicMock()
            mock_service.get_available_roles.return_value = [
                {"id": 1, "role_key": "loan_officer", "role_name": "Loan Officer"}
            ]
            mock_svc.return_value = mock_service

            response = client.get("/api/v1/workflow-sla/roles/available")

            assert response.status_code == 200
            data = response.json()
            assert "roles" in data


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
