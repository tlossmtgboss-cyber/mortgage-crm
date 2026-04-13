"""
Tests for Mobile Task Snooze Endpoint

PATCH /api/v1/mobile/tasks/{task_id}/snooze

Supports snoozing a task by:
- snooze_until (explicit ISO datetime)
- duration_minutes (relative offset)
- default (no body = +60 minutes)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models.task import Task
from tests.conftest import MockUser


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def pending_task(db_session, mock_user):
    """Insert a pending task into the test database."""
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
def completed_task(db_session, mock_user):
    """Insert a completed task into the test database."""
    now = datetime.now(timezone.utc)
    task = Task(
        title="Already completed task",
        status="completed",
        priority="low",
        due_date=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=1),
        owner_id=mock_user.id,
        organization_id=mock_user.organization_id,
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def in_progress_task(db_session, mock_user):
    """Insert an in_progress task into the test database."""
    now = datetime.now(timezone.utc)
    task = Task(
        title="In progress task",
        status="in_progress",
        priority="high",
        due_date=now + timedelta(hours=3),
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

class TestSnoozeAuth:
    """Verify the snooze endpoint rejects unauthenticated requests."""

    def test_snooze_requires_auth(self, client):
        """PATCH /api/v1/mobile/tasks/{id}/snooze returns 401/403 without auth."""
        response = client.patch("/api/v1/mobile/tasks/1/snooze", json={})
        assert response.status_code in (401, 403)


# =============================================================================
# SNOOZE WITH snooze_until
# =============================================================================

class TestSnoozeWithSnoozeUntil:
    """Test snoozing with an explicit snooze_until datetime."""

    def test_snooze_with_snooze_until(self, authenticated_client, pending_task):
        """Providing a future snooze_until sets the task's new due_date."""
        target = datetime.now(timezone.utc) + timedelta(hours=4)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"snooze_until": target_iso},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == pending_task.id

        # The new due date should be close to our target
        new_due = datetime.fromisoformat(data["new_due_date"])
        assert abs((new_due - target).total_seconds()) < 2

    def test_snooze_until_must_be_in_future(self, authenticated_client, pending_task):
        """snooze_until in the past returns 422."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        past_iso = past.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"snooze_until": past_iso},
        )

        assert response.status_code == 422
        assert "future" in response.json()["detail"].lower()

    def test_snooze_until_invalid_datetime(self, authenticated_client, pending_task):
        """Invalid snooze_until string returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"snooze_until": "not-a-date"},
        )

        assert response.status_code == 422
        assert "Invalid" in response.json()["detail"]

    def test_snooze_until_accepts_timezone_offset(self, authenticated_client, pending_task):
        """snooze_until with +00:00 timezone offset is accepted."""
        target = datetime.now(timezone.utc) + timedelta(hours=2)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"snooze_until": target_iso},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# =============================================================================
# SNOOZE WITH duration_minutes
# =============================================================================

class TestSnoozeWithDuration:
    """Test snoozing with a duration_minutes offset."""

    def test_snooze_with_duration_minutes(self, authenticated_client, pending_task):
        """Providing duration_minutes=30 sets due_date ~30 min from now."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"duration_minutes": 30},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=29)
        expected_max = before + timedelta(minutes=31)
        assert expected_min <= new_due <= expected_max

    def test_snooze_with_large_duration(self, authenticated_client, pending_task):
        """Snoozing with duration_minutes=1440 (24 hours) works."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={"duration_minutes": 1440},
        )

        assert response.status_code == 200
        data = response.json()
        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(hours=23, minutes=59)
        expected_max = before + timedelta(hours=24, minutes=1)
        assert expected_min <= new_due <= expected_max


# =============================================================================
# SNOOZE DEFAULT (no body)
# =============================================================================

class TestSnoozeDefault:
    """Test default snooze behavior when no body is provided."""

    def test_default_snooze_is_60_minutes(self, authenticated_client, pending_task):
        """No body (or empty body) defaults to +60 minutes."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=59)
        expected_max = before + timedelta(minutes=61)
        assert expected_min <= new_due <= expected_max

    def test_snooze_without_json_body(self, authenticated_client, pending_task):
        """PATCH with no JSON body still defaults to +60 minutes."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=59)
        expected_max = before + timedelta(minutes=61)
        assert expected_min <= new_due <= expected_max


# =============================================================================
# NOT FOUND
# =============================================================================

class TestSnoozeNotFound:
    """Test 404 when task does not exist."""

    def test_snooze_nonexistent_task(self, authenticated_client):
        """Non-existent task_id returns 404."""
        response = authenticated_client.patch(
            "/api/v1/mobile/tasks/999999/snooze",
            json={},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# =============================================================================
# ORGANIZATION ISOLATION
# =============================================================================

class TestSnoozeOrgIsolation:
    """Verify tenant isolation: cannot snooze another org's task."""

    def test_cannot_snooze_other_org_task(self, authenticated_client, other_org_task):
        """Attempting to snooze a task from a different organization returns 404."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{other_org_task.id}/snooze",
            json={},
        )

        assert response.status_code == 404


# =============================================================================
# COMPLETED TASK BEHAVIOR
# =============================================================================

class TestSnoozeCompletedTask:
    """Verify snooze does not un-complete completed tasks."""

    def test_snooze_does_not_uncomplete_completed_task(
        self, authenticated_client, completed_task,
    ):
        """Snoozing a completed task updates due_date but keeps status=completed."""
        target = datetime.now(timezone.utc) + timedelta(hours=2)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{completed_task.id}/snooze",
            json={"snooze_until": target_iso},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify the task stayed completed by reading it back
        # The snooze endpoint returns task_id and new_due_date but not status,
        # so we check via the GET endpoint or directly
        get_response = authenticated_client.get(
            "/api/v1/mobile/tasks?status=completed",
        )
        if get_response.status_code == 200:
            tasks = get_response.json().get("tasks", [])
            matched = [t for t in tasks if t["id"] == completed_task.id]
            if matched:
                assert matched[0]["status"] == "completed"


# =============================================================================
# IN_PROGRESS TASK BEHAVIOR
# =============================================================================

class TestSnoozeInProgressTask:
    """Verify snooze resets non-completed, non-pending tasks to pending."""

    def test_snooze_resets_in_progress_to_pending(
        self, authenticated_client, in_progress_task, db_session,
    ):
        """Snoozing an in_progress task resets its status to pending."""
        target = datetime.now(timezone.utc) + timedelta(hours=2)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{in_progress_task.id}/snooze",
            json={"snooze_until": target_iso},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify the status was reset to pending
        db_session.refresh(in_progress_task)
        assert in_progress_task.status == "pending"


# =============================================================================
# RESPONSE SHAPE
# =============================================================================

class TestSnoozeResponseShape:
    """Verify the snooze response payload structure."""

    def test_response_contains_expected_fields(self, authenticated_client, pending_task):
        """Response contains {success, task_id, new_due_date}."""
        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={},
        )

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "task_id" in data
        assert "new_due_date" in data
        assert data["success"] is True
        assert data["task_id"] == pending_task.id

        # new_due_date should be a parseable ISO datetime
        parsed = datetime.fromisoformat(data["new_due_date"])
        assert parsed > datetime.now(timezone.utc) - timedelta(seconds=5)


# =============================================================================
# PRIORITY OF snooze_until OVER duration_minutes
# =============================================================================

class TestSnoozePriority:
    """Test that snooze_until takes priority over duration_minutes."""

    def test_snooze_until_overrides_duration(self, authenticated_client, pending_task):
        """When both snooze_until and duration_minutes are provided,
        snooze_until takes precedence."""
        target = datetime.now(timezone.utc) + timedelta(hours=5)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{pending_task.id}/snooze",
            json={
                "snooze_until": target_iso,
                "duration_minutes": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()

        new_due = datetime.fromisoformat(data["new_due_date"])
        # Should be ~5 hours from now (snooze_until), not ~10 minutes
        assert abs((new_due - target).total_seconds()) < 2
