"""
Tests for Task Snooze Endpoints

PATCH /api/v1/tasks/{task_id}/snooze
PATCH /api/v1/mobile/tasks/{task_id}/snooze

Both endpoints delegate to the shared _snooze_task() helper in
mobile_tasks_routes.py, which resolves a new due_date from either
snooze_until (ISO datetime) or duration_minutes (int), defaulting
to +60 minutes when neither is provided.
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

class TestSnoozeAuth:
    """Verify that the snooze endpoint rejects unauthenticated requests."""

    def test_snooze_requires_auth(self, client):
        """PATCH /api/v1/tasks/{id}/snooze returns 401/403 without auth."""
        response = client.patch("/api/v1/tasks/1/snooze", json={})
        assert response.status_code in (401, 403)

    def test_snooze_mobile_requires_auth(self, client):
        """PATCH /api/v1/mobile/tasks/{id}/snooze returns 401/403 without auth."""
        response = client.patch("/api/v1/mobile/tasks/1/snooze", json={})
        assert response.status_code in (401, 403)


# =============================================================================
# SNOOZE LOGIC TESTS
# =============================================================================

class TestSnoozeDuration:
    """Test snooze with explicit duration_minutes."""

    def test_snooze_with_duration(self, authenticated_client, sample_task):
        """Sending {duration_minutes: 120} pushes due_date forward by ~2 hours."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={"duration_minutes": 120},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=119)
        expected_max = before + timedelta(minutes=121)
        assert expected_min <= new_due <= expected_max


class TestSnoozeIsoDatetime:
    """Test snooze with an explicit snooze_until ISO datetime."""

    def test_snooze_with_iso_datetime(self, authenticated_client, sample_task):
        """Sending {snooze_until: ISO string} sets due_date to that exact time."""
        target = datetime.now(timezone.utc) + timedelta(hours=5)
        target_iso = target.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={"snooze_until": target_iso},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        # Should match to within 1 second
        assert abs((new_due - target).total_seconds()) < 1

    def test_snooze_past_datetime_rejected(self, authenticated_client, sample_task):
        """snooze_until in the past returns 422."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        past_iso = past.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={"snooze_until": past_iso},
        )

        assert response.status_code == 422

    def test_snooze_invalid_datetime_rejected(self, authenticated_client, sample_task):
        """Malformed snooze_until returns 422."""
        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={"snooze_until": "not-a-date"},
        )

        assert response.status_code == 422


class TestSnoozeDefault:
    """Test the default snooze behavior (empty body = +60 minutes)."""

    def test_snooze_default_60_minutes(self, authenticated_client, sample_task):
        """Empty body defaults to a 60-minute snooze."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=59)
        expected_max = before + timedelta(minutes=61)
        assert expected_min <= new_due <= expected_max


class TestSnoozeResponse:
    """Verify the response payload shape."""

    def test_snooze_returns_new_due_date(self, authenticated_client, sample_task):
        """Response contains {success: true, task_id, new_due_date}."""
        response = authenticated_client.patch(
            f"/api/v1/tasks/{sample_task.id}/snooze",
            json={"duration_minutes": 30},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["task_id"] == sample_task.id
        assert "new_due_date" in data

        # new_due_date should be a parseable ISO datetime
        parsed = datetime.fromisoformat(data["new_due_date"])
        assert parsed > datetime.now(timezone.utc) - timedelta(seconds=5)


# =============================================================================
# ERROR / ISOLATION TESTS
# =============================================================================

class TestSnoozeNotFound:
    """Test 404 when task does not exist."""

    def test_snooze_task_not_found(self, authenticated_client):
        """Non-existent task_id returns 404."""
        response = authenticated_client.patch(
            "/api/v1/tasks/999999/snooze",
            json={"duration_minutes": 30},
        )

        assert response.status_code == 404


class TestSnoozeOrgIsolation:
    """Verify tenant isolation: cannot snooze another org's task."""

    def test_snooze_org_isolation(self, authenticated_client, other_org_task):
        """Attempting to snooze a task from a different organization returns 404."""
        response = authenticated_client.patch(
            f"/api/v1/tasks/{other_org_task.id}/snooze",
            json={"duration_minutes": 30},
        )

        # _snooze_task filters by organization_id, so a cross-org task appears as not found
        assert response.status_code == 404


# =============================================================================
# MOBILE ALIAS TEST
# =============================================================================

class TestSnoozeMobileAlias:
    """Verify the mobile endpoint behaves identically."""

    def test_snooze_mobile_alias(self, authenticated_client, sample_task):
        """PATCH /api/v1/mobile/tasks/{id}/snooze works the same as the primary route."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}/snooze",
            json={"duration_minutes": 45},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == sample_task.id

        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=44)
        expected_max = before + timedelta(minutes=46)
        assert expected_min <= new_due <= expected_max

    def test_snooze_mobile_not_found(self, authenticated_client):
        """Mobile endpoint also returns 404 for non-existent task."""
        response = authenticated_client.patch(
            "/api/v1/mobile/tasks/999999/snooze",
            json={},
        )

        assert response.status_code == 404

    def test_snooze_mobile_default(self, authenticated_client, sample_task):
        """Mobile endpoint also defaults to +60 minutes."""
        before = datetime.now(timezone.utc)

        response = authenticated_client.patch(
            f"/api/v1/mobile/tasks/{sample_task.id}/snooze",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        new_due = datetime.fromisoformat(data["new_due_date"])
        expected_min = before + timedelta(minutes=59)
        expected_max = before + timedelta(minutes=61)
        assert expected_min <= new_due <= expected_max
