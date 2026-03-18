"""
Tests for scheduler conflicts routes.

Covers:
  - GET  /conflicts/check                    Check for conflicts before booking
  - GET  /conflicts/list                     List all current conflicts for user
  - POST /conflicts/resolve/{appointment_id} Resolve a conflict by rescheduling
  - 401 without auth
  - 404 for missing appointments
  - 400 for invalid datetime formats
  - 409 when new slot still has hard conflicts
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="loan_officer", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockAppointment:
    """Mock Appointment ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.assigned_user_id = kwargs.get("assigned_user_id", 1)
        self.created_by_user_id = kwargs.get("created_by_user_id", 1)
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 20, 10, 0))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 20, 10, 30))
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.status = kwargs.get("status", "booked")
        self.reschedule_count = kwargs.get("reschedule_count", 0)


# Bypass feature_tier decorator in all tests
_noop_tier = lambda x: lambda f: f


# ---------------------------------------------------------------------------
# Tests: Authentication
# ---------------------------------------------------------------------------

class TestConflictsAuth:
    """Tests for auth enforcement on conflict endpoints."""

    @pytest.mark.asyncio
    async def test_check_conflicts_requires_auth(self):
        """GET /conflicts/check without auth should return 401."""
        from routes.scheduler.conflicts import check_conflicts

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await check_conflicts(
                    MagicMock(), None,
                    "2026-03-20T10:00:00", "2026-03-20T10:30:00",
                    None, 30, MagicMock(),
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_conflicts_requires_auth(self):
        """GET /conflicts/list without auth should return 401."""
        from routes.scheduler.conflicts import list_conflicts

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await list_conflicts(MagicMock(), None, None, None, MagicMock())
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Tests: Check Conflicts
# ---------------------------------------------------------------------------

class TestCheckConflicts:
    """Tests for GET /conflicts/check."""

    @pytest.mark.asyncio
    async def test_check_invalid_datetime_returns_400(self):
        """Invalid datetime format should return 400."""
        from routes.scheduler.conflicts import check_conflicts

        user = MockUser()

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await check_conflicts(
                    MagicMock(), None,
                    "not-a-date", "also-not-a-date",
                    None, 30, MagicMock(),
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_check_end_before_start_returns_400(self):
        """End time before start time should return 400."""
        from routes.scheduler.conflicts import check_conflicts

        user = MockUser()

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await check_conflicts(
                    MagicMock(), None,
                    "2026-03-20T11:00:00", "2026-03-20T10:00:00",
                    None, 30, MagicMock(),
                )
            assert exc_info.value.status_code == 400
            assert "End time" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_check_no_conflicts_found(self):
        """When no conflicts exist, has_conflicts should be False."""
        from routes.scheduler.conflicts import check_conflicts

        user = MockUser()

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.detect_conflicts", return_value=[]), \
             patch("routes.scheduler.conflicts.auto_resolve_soft_conflicts", return_value=[]), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            result = await check_conflicts(
                MagicMock(), None,
                "2026-03-20T10:00:00", "2026-03-20T10:30:00",
                None, 30, MagicMock(),
            )

        assert result["has_conflicts"] is False
        assert result["conflict_count"] == 0
        assert result["conflicts"] == []

    @pytest.mark.asyncio
    async def test_check_detects_hard_conflict(self):
        """Hard conflicts should be returned with alternatives."""
        from routes.scheduler.conflicts import check_conflicts

        user = MockUser()

        mock_conflicts = [
            {
                "severity": "hard",
                "appointment_id": 5,
                "title": "Team Meeting",
                "reason": "Overlapping appointment",
            }
        ]
        mock_alternatives = [
            {"start": "2026-03-20T11:00:00", "end": "2026-03-20T11:30:00", "score": 0.9}
        ]

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.detect_conflicts", return_value=mock_conflicts), \
             patch("routes.scheduler.conflicts.suggest_alternatives", return_value=mock_alternatives), \
             patch("routes.scheduler.conflicts.auto_resolve_soft_conflicts", return_value=[]), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            result = await check_conflicts(
                MagicMock(), None,
                "2026-03-20T10:00:00", "2026-03-20T10:30:00",
                None, 30, MagicMock(),
            )

        assert result["has_conflicts"] is True
        assert result["has_hard_conflicts"] is True
        assert result["conflict_count"] == 1
        assert len(result["alternatives"]) == 1


# ---------------------------------------------------------------------------
# Tests: List Conflicts
# ---------------------------------------------------------------------------

class TestListConflicts:
    """Tests for GET /conflicts/list."""

    @pytest.mark.asyncio
    async def test_list_returns_conflicts(self):
        """List should return conflict pairs for the user."""
        from routes.scheduler.conflicts import list_conflicts

        user = MockUser()
        mock_pairs = [
            {"appointment_a_id": 1, "appointment_b_id": 2, "severity": "hard"},
            {"appointment_a_id": 3, "appointment_b_id": 4, "severity": "soft"},
        ]

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.list_user_conflicts", return_value=mock_pairs), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            result = await list_conflicts(MagicMock(), None, None, None, MagicMock())

        assert result["user_id"] == 1
        assert result["conflict_count"] == 2
        assert len(result["conflicts"]) == 2

    @pytest.mark.asyncio
    async def test_list_invalid_date_format_returns_400(self):
        """Invalid start_date format should return 400."""
        from routes.scheduler.conflicts import list_conflicts

        user = MockUser()

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await list_conflicts(MagicMock(), None, "bad-date", None, MagicMock())
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Resolve Conflict
# ---------------------------------------------------------------------------

class TestResolveConflict:
    """Tests for POST /conflicts/resolve/{appointment_id}."""

    @pytest.mark.asyncio
    async def test_resolve_appointment_not_found_returns_404(self):
        """Resolving a non-existent appointment should return 404."""
        from routes.scheduler.conflicts import resolve_conflict, ResolveConflictRequest

        user = MockUser()
        body = ResolveConflictRequest(
            new_start="2026-03-20T14:00:00",
            new_end="2026-03-20T14:30:00",
        )

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.get_models", return_value=mock_models), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_conflict(999, body, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_cancelled_appointment_returns_400(self):
        """Cannot reschedule a cancelled appointment."""
        from routes.scheduler.conflicts import resolve_conflict, ResolveConflictRequest

        user = MockUser()
        body = ResolveConflictRequest(
            new_start="2026-03-20T14:00:00",
            new_end="2026-03-20T14:30:00",
        )

        # Create a mock cancelled appointment
        appt = MockAppointment(id=1)

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        # Mock AppointmentStatus so the cancelled check triggers
        mock_status = MagicMock()
        mock_status.CANCELLED = "cancelled"
        mock_status.COMPLETED = "completed"
        appt.status = "cancelled"

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.get_models", return_value=mock_models), \
             patch("routes.scheduler.conflicts.AppointmentStatus", mock_status), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_conflict(1, body, MagicMock(), db)
            assert exc_info.value.status_code == 400
            assert "cancelled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_resolve_new_slot_has_hard_conflict_returns_409(self):
        """If the proposed new slot still has hard conflicts, return 409."""
        from routes.scheduler.conflicts import resolve_conflict, ResolveConflictRequest

        user = MockUser()
        body = ResolveConflictRequest(
            new_start="2026-03-20T14:00:00",
            new_end="2026-03-20T14:30:00",
        )

        appt = MockAppointment(id=1, status="booked")

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        mock_status = MagicMock()
        mock_status.CANCELLED = "cancelled"
        mock_status.COMPLETED = "completed"

        hard_conflicts = [{"severity": "hard", "reason": "Overlap with another"}]

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.get_models", return_value=mock_models), \
             patch("routes.scheduler.conflicts.AppointmentStatus", mock_status), \
             patch("routes.scheduler.conflicts.detect_conflicts", return_value=hard_conflicts), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_conflict(1, body, MagicMock(), db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_resolve_happy_path(self):
        """Successfully resolve a conflict by moving an appointment."""
        from routes.scheduler.conflicts import resolve_conflict, ResolveConflictRequest

        user = MockUser()
        body = ResolveConflictRequest(
            new_start="2026-03-20T14:00:00",
            new_end="2026-03-20T14:30:00",
        )

        old_start = datetime(2026, 3, 20, 10, 0)
        old_end = datetime(2026, 3, 20, 10, 30)
        appt = MockAppointment(
            id=1, status="booked",
            scheduled_start=old_start, scheduled_end=old_end,
        )

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        mock_status = MagicMock()
        mock_status.CANCELLED = "cancelled"
        mock_status.COMPLETED = "completed"

        with patch("routes.scheduler.conflicts.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.conflicts.get_models", return_value=mock_models), \
             patch("routes.scheduler.conflicts.AppointmentStatus", mock_status), \
             patch("routes.scheduler.conflicts.detect_conflicts", return_value=[]), \
             patch("routes.scheduler.conflicts._audit_log"), \
             patch("routes.scheduler.conflicts.require_feature_tier", _noop_tier):
            result = await resolve_conflict(1, body, MagicMock(), db)

        assert result["status"] == "resolved"
        assert result["appointment_id"] == 1
        assert result["new_start"] == "2026-03-20T14:00:00"
        assert result["new_end"] == "2026-03-20T14:30:00"
        assert result["remaining_soft_conflicts"] == 0
        # Verify the appointment was updated
        assert appt.reschedule_count == 1
        assert appt.duration_minutes == 30
