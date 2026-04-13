"""
Tests for Mobile Task Update Endpoint

PATCH /api/v1/mobile/tasks/{task_id}

Supports partial updates to status, priority, title, and due_date.
Used by CarPlayAPIService.completeTask() and notification quick actions.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models.task import Task
from tests.conftest import MockUser


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_task(db_session, mock_user):
    """Insert a real Task row into the test database and return it."""
    now = datetime.now(timezone.utc)
    task = Task(
        title="Follow up with borrower",
        description="Call John Smith about appraisal",
        status="pending",
        priority="medium",
        due_date=now + timedelta(hours=1),
        owner_id=mock_user.id,
        organization_id=mock_user.organization_id,
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def other_org_task(db_session):
    """Task belonging to a different organization (org_id=999)."""
    now = datetime.now(timezone.utc)
    task = Task(
        title="Other org task",
        status="pending",
        priority="low",
        due_date=now + timedelta(hours=2),
        owner_id=9999,
        organization_id=999,
    )
    db_session.add(task)
    db_session.flush()
    return task


# =============================================================================
# AUTH TESTS
# =============================================================================

class TestUpdateAuth:
    """Verify that the update endpoint rejects unauthenticated requests."""

    def test_update_requires_auth(self, client):
        """PATCH /api/v1/mobile/tasks/{id} returns 401/403 without auth."""
        response = client.patch("/api/v1/mobile/tasks/1", json={"status": "completed"})
        assert response.status_code in (401, 403)


# =============================================================================
# STATUS UPDATE TESTS
# =============================================================================

class TestUpdateStatus:
    """Test updating task status."""

    def test_mark_task_completed(self, authenticated_client, sample_task):
        """Setting status=completed should auto-set completed_at."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"status": "completed"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == sample_task.id
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

        # completed_at should be parseable and recent
        completed_at = datetime.fromisoformat(data["completed_at"])
        assert completed_at > datetime.now(timezone.utc) - timedelta(seconds=5)

    def test_invalid_status_rejected(self, authenticated_client, sample_task):
        """Invalid status value returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"status": "invalid_status"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid status" in data["detail"]

    def test_status_is_case_insensitive(self, authenticated_client, sample_task):
        """Status value should be normalized to lowercase."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"status": "In_Progress"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"


# =============================================================================
# PRIORITY UPDATE TESTS
# =============================================================================

class TestUpdatePriority:
    """Test updating task priority."""

    def test_update_priority(self, authenticated_client, sample_task):
        """Setting priority=high should update the task priority."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"priority": "high"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["priority"] == "high"

    def test_invalid_priority_rejected(self, authenticated_client, sample_task):
        """Invalid priority value returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"priority": "urgent"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid priority" in data["detail"]


# =============================================================================
# TITLE UPDATE TESTS
# =============================================================================

class TestUpdateTitle:
    """Test updating task title."""

    def test_update_title(self, authenticated_client, sample_task):
        """Setting title should update the task title."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"title": "Updated task title"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["title"] == "Updated task title"

    def test_title_is_stripped(self, authenticated_client, sample_task):
        """Title should be stripped of leading/trailing whitespace."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"title": "  Trimmed title  "},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Trimmed title"


# =============================================================================
# DUE DATE UPDATE TESTS
# =============================================================================

class TestUpdateDueDate:
    """Test updating task due_date."""

    def test_update_due_date_iso(self, authenticated_client, sample_task):
        """Setting due_date with ISO datetime should update the task."""
        target = datetime.now(timezone.utc) + timedelta(days=3)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"due_date": target_iso},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["due_date"] is not None

        parsed = datetime.fromisoformat(data["due_date"])
        assert abs((parsed - target).total_seconds()) < 1

    def test_invalid_due_date_rejected(self, authenticated_client, sample_task):
        """Malformed due_date returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"due_date": "not-a-date"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid due_date" in data["detail"]


# =============================================================================
# EMPTY BODY / NO VALID FIELDS
# =============================================================================

class TestUpdateEmptyBody:
    """Test that empty body is rejected."""

    def test_empty_body_rejected(self, authenticated_client, sample_task):
        """Sending {} with no valid fields returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={},
        )

        assert response.status_code == 422
        data = response.json()
        assert "No valid fields" in data["detail"]


# =============================================================================
# NOT FOUND
# =============================================================================

class TestUpdateNotFound:
    """Test 404 when task does not exist."""

    def test_task_not_found(self, authenticated_client):
        """Non-existent task_id returns 404."""
        response = authenticated_client.patch(
            "/api/v1/mobile/tasks/999999",
            json={"status": "completed"},
        )

        assert response.status_code == 404


# =============================================================================
# ORGANIZATION ISOLATION
# =============================================================================

class TestUpdateOrgIsolation:
    """Verify tenant isolation: cannot update another org's task."""

    def test_org_isolation(self, authenticated_client, other_org_task):
        """Attempting to update a task from a different organization returns 404."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{other_org_task.id}",
            json={"status": "completed"},
        )

        # update_mobile_task filters by organization_id, so a cross-org task appears as not found
        assert response.status_code == 404


# =============================================================================
# RESPONSE SHAPE
# =============================================================================

class TestUpdateResponseShape:
    """Verify the response payload contains expected fields."""

    def test_response_contains_all_fields(self, authenticated_client, sample_task):
        """Response contains {success, task_id, status, priority, title, due_date, completed_at, updated_at}."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}",
            json={"priority": "low"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["task_id"] == sample_task.id
        assert "status" in data
        assert "priority" in data
        assert "title" in data
        assert "due_date" in data
        assert "completed_at" in data
        assert "updated_at" in data

        # updated_at should be a parseable ISO datetime
        parsed = datetime.fromisoformat(data["updated_at"])
        assert parsed > datetime.now(timezone.utc) - timedelta(seconds=5)
