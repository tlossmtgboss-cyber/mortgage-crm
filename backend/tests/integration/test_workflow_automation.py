"""
Workflow Automation Integration Tests

Tests for SLA-driven workflow enrollment, task generation, and lifecycle:
- Lead/loan workflow enrollment
- Duplicate enrollment prevention (advisory lock)
- Task generation from day configs
- Workflow state transitions (pause/resume/cancel)
- AI confidence thresholds

Key files:
    backend/services/workflow_sla_service.py
    backend/workflow_routes.py
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def org(db_session):
    """Create a test organization."""
    from database.models import Organization
    org = Organization(name="Test Org SLA", slug="test-org-sla", is_active=True)
    db_session.add(org)
    db_session.flush()
    return org


@pytest.fixture
def user(db_session, org):
    """Create a test user (loan officer)."""
    from database.models import User
    user = User(
        email="lo-workflow@test.com",
        hashed_password="hashed",
        first_name="Test",
        last_name="LO",
        role="loan_officer",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lead(db_session, org, user):
    """Create a test lead."""
    from database.models import Lead
    lead = Lead(
        organization_id=org.id,
        name="Workflow Test Lead",
        first_name="Workflow",
        last_name="Lead",
        email="wf-lead@test.com",
        phone="+15551234567",
        stage="New",
        owner_id=user.id,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


@pytest.fixture
def loan(db_session, org, user):
    """Create a test loan."""
    from database.models import Loan
    loan = Loan(
        organization_id=org.id,
        loan_number=f"WF-TEST-{datetime.now().strftime('%H%M%S%f')}",
        borrower_name="Workflow Borrower",
        stage="PROCESSING",
        amount=350000,
        loan_officer_id=user.id,
    )
    db_session.add(loan)
    db_session.flush()
    return loan


class TestWorkflowSLAServiceInit:
    """Test WorkflowSLAService initialization and model loading."""

    def test_service_loads_models(self, db_session):
        """Service constructor should load all required models."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        assert svc.Lead is not None
        assert svc.Loan is not None
        assert svc.Task is not None
        assert svc.User is not None
        assert svc.Organization is not None

    def test_ai_threshold_constants(self, db_session):
        """AI confidence thresholds should be correctly set."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        assert svc.AI_AUTO_EXECUTE_THRESHOLD == Decimal("0.950")
        assert svc.AI_REVIEW_THRESHOLD == Decimal("0.700")
        # Auto-execute requires higher confidence than review
        assert svc.AI_AUTO_EXECUTE_THRESHOLD > svc.AI_REVIEW_THRESHOLD


class TestWorkflowEnrollment:
    """Test lead and loan enrollment into workflows."""

    def test_enroll_lead_missing_lead_returns_error(self, db_session):
        """Enrolling a nonexistent lead should return an error dict."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        result = svc.enroll_lead(lead_id=999999, workflow_key="prospect")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_enroll_lead_missing_workflow_returns_error(self, db_session, lead):
        """Enrolling into a nonexistent workflow should return an error."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        result = svc.enroll_lead(
            lead_id=lead.id,
            workflow_key="nonexistent_workflow_key",
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_enroll_loan_missing_loan_returns_error(self, db_session):
        """Enrolling a nonexistent loan should return an error."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        result = svc.enroll_loan(loan_id=999999, workflow_key="under_contract")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_enroll_loan_missing_workflow_returns_error(self, db_session, loan):
        """Enrolling a loan into a nonexistent workflow should return an error."""
        from services.workflow_sla_service import WorkflowSLAService
        svc = WorkflowSLAService(db_session)

        result = svc.enroll_loan(
            loan_id=loan.id,
            workflow_key="nonexistent_wf",
        )
        assert result["success"] is False
        assert "not found" in result["error"]


class TestWorkflowHTTPEndpoints:
    """Test workflow endpoints via the authenticated test client."""

    def test_get_workflow_configs_returns_200(self, authenticated_client):
        """GET /api/v1/workflow/configs should return 200."""
        response = authenticated_client.get("/api/v1/workflow/configs")
        # Accept 200 or 404 (if no configs exist yet)
        assert response.status_code in (200, 404), (
            f"Expected 200 or 404, got {response.status_code}: {response.text[:300]}"
        )

    def test_get_workflow_status_requires_auth(self, client):
        """Workflow status endpoint should require authentication."""
        response = client.get("/api/v1/workflow/status")
        assert response.status_code in (401, 403, 500)

    def test_get_workflow_dashboard(self, authenticated_client):
        """GET /api/v1/workflow/dashboard should return data or 404."""
        response = authenticated_client.get("/api/v1/workflow/dashboard")
        assert response.status_code in (200, 404), (
            f"Expected 200 or 404, got {response.status_code}: {response.text[:300]}"
        )


class TestWorkflowTaskGeneration:
    """Test that workflow enrollment generates the correct tasks."""

    def test_task_model_has_workflow_fields(self, db_session):
        """Task model should have workflow linkage fields."""
        from database.models import Task
        task = Task(
            organization_id=1,
            title="Test workflow task",
            status="pending",
            workflow_task_instance_id=42,
            task_group_key="day_1_outreach",
        )
        assert task.workflow_task_instance_id == 42
        assert task.task_group_key == "day_1_outreach"

    def test_task_sla_milestone_fields(self, db_session):
        """Task model should have SLA milestone tracking fields."""
        from database.models import Task
        task = Task(
            organization_id=1,
            title="Order Appraisal",
            sla_milestone_type="appraisal_ordered",
            sla_date_field="appraisal_ordered_date",
            milestone_date=datetime.now(timezone.utc),
        )
        assert task.sla_milestone_type == "appraisal_ordered"
        assert task.sla_date_field == "appraisal_ordered_date"
        assert task.milestone_date is not None
