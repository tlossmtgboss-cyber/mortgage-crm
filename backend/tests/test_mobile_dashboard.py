"""
Tests for Mobile Dashboard Endpoints

GET /api/v1/mobile/dashboard  — Pipeline summary for the iOS PerenniaWidget
GET /api/v1/mobile/pipeline   — Stage breakdown for the iOS PerenniaWidget

Covers response shape, auth enforcement, and empty-data defaults.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models.task import Task
from database.models.lead_loan import Lead, Loan
from tests.conftest import MockUser


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_leads(db_session, mock_user):
    """Insert recent leads into the test database."""
    now = datetime.now(timezone.utc)
    leads = []
    for i in range(3):
        lead = Lead(
            name=f"Test Lead {i}",
            first_name=f"Test{i}",
            last_name=f"Lead{i}",
            email=f"lead{i}@example.com",
            phone=f"+1555000000{i}",
            organization_id=mock_user.organization_id,
            stage="New",
            created_at=now - timedelta(days=i),
        )
        db_session.add(lead)
        leads.append(lead)
    db_session.flush()
    return leads


@pytest.fixture
def sample_loans(db_session, mock_user):
    """Insert active loans in various stages."""
    now = datetime.now(timezone.utc)
    loans_data = [
        {"loan_number": "TEST-001", "stage": "APPLICATION", "amount": 300000, "borrower_name": "Alice Smith"},
        {"loan_number": "TEST-002", "stage": "PROCESSING", "amount": 450000, "borrower_name": "Bob Jones"},
        {"loan_number": "TEST-003", "stage": "CTC", "amount": 250000, "borrower_name": "Carol White"},
        {"loan_number": "TEST-004", "stage": "DOCS_OUT", "amount": 500000, "borrower_name": "Dan Brown"},
    ]
    loans = []
    for ld in loans_data:
        loan = Loan(
            loan_number=ld["loan_number"],
            stage=ld["stage"],
            amount=ld["amount"],
            borrower_name=ld["borrower_name"],
            organization_id=mock_user.organization_id,
            created_at=now,
        )
        db_session.add(loan)
        loans.append(loan)
    db_session.flush()
    return loans


@pytest.fixture
def sample_tasks_due_today(db_session, mock_user):
    """Insert tasks that are due today."""
    now = datetime.now(timezone.utc)
    tasks = []
    for i in range(2):
        task = Task(
            title=f"Due today task {i}",
            status="pending",
            priority="medium",
            due_date=now - timedelta(hours=i),  # Due earlier today
            owner_id=mock_user.id,
            organization_id=mock_user.organization_id,
        )
        db_session.add(task)
        tasks.append(task)
    db_session.flush()
    return tasks


# =============================================================================
# AUTH TESTS
# =============================================================================

class TestDashboardAuth:
    """Verify both dashboard endpoints reject unauthenticated requests."""

    def test_dashboard_requires_auth(self, client):
        """GET /api/v1/mobile/dashboard returns 401 without auth."""
        response = client.get("/api/v1/mobile/dashboard")
        assert response.status_code in (401, 403)

    def test_pipeline_requires_auth(self, client):
        """GET /api/v1/mobile/pipeline returns 401 without auth."""
        response = client.get("/api/v1/mobile/pipeline")
        assert response.status_code in (401, 403)


# =============================================================================
# DASHBOARD RESPONSE SHAPE TESTS
# =============================================================================

class TestDashboardResponseShape:
    """Verify the dashboard response has the expected structure."""

    def test_dashboard_returns_expected_keys(self, authenticated_client):
        """Response contains pipeline, tasks_due_today, recent_activity."""
        # Clear any cached data so endpoint hits the DB
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert "pipeline" in data
        assert "tasks_due_today" in data
        assert "recent_activity" in data

    def test_dashboard_pipeline_has_expected_keys(self, authenticated_client):
        """Pipeline object contains active, closing_soon, volume."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        pipeline = response.json()["pipeline"]
        assert "active" in pipeline
        assert "closing_soon" in pipeline
        assert "volume" in pipeline

    def test_dashboard_recent_activity_is_list(self, authenticated_client):
        """recent_activity is a list."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["recent_activity"], list)


# =============================================================================
# EMPTY DATA TESTS
# =============================================================================

class TestDashboardEmptyData:
    """Verify empty data returns zeros and empty lists, not errors."""

    def test_dashboard_empty_returns_zeros(self, authenticated_client):
        """Dashboard with no data returns zero counts and empty activity."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert data["pipeline"]["active"] == 0
        assert data["pipeline"]["closing_soon"] == 0
        # volume should be 0 or 0.0
        assert data["pipeline"]["volume"] == 0 or data["pipeline"]["volume"] == 0.0
        assert data["tasks_due_today"] == 0
        assert data["recent_activity"] == []

    def test_pipeline_empty_returns_zeros(self, authenticated_client):
        """Pipeline with no loans returns zero counts and volume."""
        from routes.mobile_dashboard_routes import _pipeline_cache
        _pipeline_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/pipeline")
        assert response.status_code == 200

        data = response.json()
        assert data["stage_counts"] == {}
        assert data["total_count"] == 0
        assert data["total_volume"] == 0 or data["total_volume"] == 0.0


# =============================================================================
# PIPELINE RESPONSE SHAPE TESTS
# =============================================================================

class TestPipelineResponseShape:
    """Verify the pipeline response has the expected structure."""

    def test_pipeline_returns_expected_keys(self, authenticated_client):
        """Response contains stage_counts, total_count, total_volume."""
        from routes.mobile_dashboard_routes import _pipeline_cache
        _pipeline_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/pipeline")
        assert response.status_code == 200

        data = response.json()
        assert "stage_counts" in data
        assert "total_count" in data
        assert "total_volume" in data

    def test_pipeline_stage_counts_is_dict(self, authenticated_client):
        """stage_counts is a dictionary."""
        from routes.mobile_dashboard_routes import _pipeline_cache
        _pipeline_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/pipeline")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["stage_counts"], dict)


# =============================================================================
# DASHBOARD WITH DATA TESTS
# =============================================================================

class TestDashboardWithData:
    """Verify dashboard correctly aggregates real data."""

    def test_dashboard_includes_recent_leads(self, authenticated_client, sample_leads):
        """Recent leads appear in recent_activity."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        data = response.json()
        activity = data["recent_activity"]
        # Should have 3 recent leads
        assert len(activity) == 3

        # Each activity entry has expected shape
        for item in activity:
            assert "summary" in item
            assert "type" in item
            assert "time" in item
            assert item["type"] == "lead"
            assert item["summary"].startswith("New lead:")

    def test_dashboard_counts_tasks_due_today(
        self, authenticated_client, sample_tasks_due_today,
    ):
        """tasks_due_today reflects pending tasks with due_date before end of today."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert data["tasks_due_today"] >= 2


# =============================================================================
# CACHE BEHAVIOR TESTS
# =============================================================================

class TestDashboardCache:
    """Verify caching behavior."""

    def test_dashboard_caches_result(self, authenticated_client):
        """Second call within TTL returns cached data (same result)."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        r1 = authenticated_client.get("/api/v1/mobile/dashboard")
        r2 = authenticated_client.get("/api/v1/mobile/dashboard")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_pipeline_caches_result(self, authenticated_client):
        """Second call within TTL returns cached data."""
        from routes.mobile_dashboard_routes import _pipeline_cache
        _pipeline_cache.clear()

        r1 = authenticated_client.get("/api/v1/mobile/pipeline")
        r2 = authenticated_client.get("/api/v1/mobile/pipeline")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_dashboard_has_cache_control_header(self, authenticated_client):
        """Response includes Cache-Control header."""
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        response = authenticated_client.get("/api/v1/mobile/dashboard")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert "private" in response.headers["cache-control"]


# =============================================================================
# NO ORG ID EDGE CASE
# =============================================================================

class TestDashboardNoOrgId:
    """Test behavior when user has no organization_id."""

    def test_dashboard_no_org_returns_empty(self, db_session):
        """User with organization_id=None gets empty dashboard."""
        from main import app, get_current_user, get_current_user_flexible
        from auth.dependencies import (
            get_current_user as auth_dep_gcu,
            get_current_user_flexible as auth_dep_gcuf,
        )
        from database import get_db
        from routes.auth_deps import require_auth, current_user_dep
        from routes.mobile_dashboard_routes import _dashboard_cache
        _dashboard_cache.clear()

        no_org_user = MockUser(id=99, organization_id=None)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        async def override_auth():
            return no_org_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_current_user_flexible] = override_auth
        app.dependency_overrides[auth_dep_gcu] = override_auth
        app.dependency_overrides[auth_dep_gcuf] = override_auth
        app.dependency_overrides[require_auth] = override_auth
        app.dependency_overrides[current_user_dep] = override_auth

        try:
            with TestClient(app) as tc:
                response = tc.get("/api/v1/mobile/dashboard")
                assert response.status_code == 200
                data = response.json()
                assert data["pipeline"]["active"] == 0
                assert data["tasks_due_today"] == 0
                assert data["recent_activity"] == []
        finally:
            app.dependency_overrides.clear()


# Needed for the TestClient import inside the class
from fastapi.testclient import TestClient
