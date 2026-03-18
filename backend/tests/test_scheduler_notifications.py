"""
Tests for scheduler notification routes.

Covers:
  - GET  /notifications             List notifications for current user
  - PUT  /notifications/{id}/read   Mark single notification as read
  - PUT  /notifications/read-all    Mark all notifications as read

Also tests internal helpers:
  - _generate_notifications_for_user (feed generation from appointment events)
  - _stable_id (deterministic notification ID generation)
  - _format_datetime (display formatting)
"""

import pytest
from datetime import datetime, timedelta, timezone
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
    """Minimal appointment mock for notification generation."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.assigned_user_id = kwargs.get("assigned_user_id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.title = kwargs.get("title", "Loan Review")
        self.attendee_name = kwargs.get("attendee_name", "John Smith")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.status = kwargs.get("status", "booked")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.created_at = kwargs.get("created_at", now - timedelta(hours=1))
        self.updated_at = kwargs.get("updated_at", now - timedelta(hours=1))
        self.scheduled_start = kwargs.get("scheduled_start", now + timedelta(minutes=30))
        self.scheduled_end = kwargs.get("scheduled_end", now + timedelta(minutes=60))


# ---------------------------------------------------------------------------
# Tests: Helper Functions
# ---------------------------------------------------------------------------

class TestStableId:
    """Tests for deterministic notification ID generation."""

    def test_stable_id_deterministic(self):
        """Same inputs should always produce the same ID."""
        from routes.scheduler.notifications import _stable_id

        ts = datetime(2026, 3, 15, 10, 0, 0)
        id1 = _stable_id("booking", 100, ts)
        id2 = _stable_id("booking", 100, ts)
        assert id1 == id2

    def test_stable_id_different_for_different_types(self):
        """Different notification types produce different IDs."""
        from routes.scheduler.notifications import _stable_id

        ts = datetime(2026, 3, 15, 10, 0, 0)
        id_booking = _stable_id("booking", 100, ts)
        id_cancel = _stable_id("cancellation", 100, ts)
        assert id_booking != id_cancel

    def test_stable_id_handles_none_timestamp(self):
        """None timestamp should not crash."""
        from routes.scheduler.notifications import _stable_id

        result = _stable_id("booking", 100, None)
        assert isinstance(result, str)
        assert len(result) == 16  # SHA256 truncated to 16 hex chars


class TestFormatDatetime:
    """Tests for datetime formatting helper."""

    def test_format_valid_datetime(self):
        """Valid datetime should be formatted."""
        from routes.scheduler.notifications import _format_datetime

        dt = datetime(2026, 3, 15, 14, 30)
        result = _format_datetime(dt)
        assert "Mar" in result
        assert "15" in result
        assert "02:30 PM" in result

    def test_format_none_returns_empty(self):
        """None datetime should return empty string."""
        from routes.scheduler.notifications import _format_datetime

        assert _format_datetime(None) == ""


# ---------------------------------------------------------------------------
# Tests: Notification Feed Generation
# ---------------------------------------------------------------------------

class TestGenerateNotifications:
    """Tests for _generate_notifications_for_user."""

    def test_empty_when_no_appointments(self):
        """No appointments should produce empty notification list."""
        from routes.scheduler.notifications import _generate_notifications_for_user

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.order_by = MagicMock(return_value=query_mock)
        query_mock.limit = MagicMock(return_value=query_mock)
        query_mock.all = MagicMock(return_value=[])
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        with patch("routes.scheduler.notifications.get_models", return_value=mock_models):
            result = _generate_notifications_for_user(db, 1, 1)

        assert result == []

    def test_no_appointment_model_returns_empty(self):
        """If Appointment model is not available, return empty list."""
        from routes.scheduler.notifications import _generate_notifications_for_user

        with patch("routes.scheduler.notifications.get_models", return_value={}):
            result = _generate_notifications_for_user(MagicMock(), 1, 1)

        assert result == []

    def test_deduplication_by_id(self):
        """Duplicate notification IDs should be removed."""
        from routes.scheduler.notifications import _generate_notifications_for_user

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Same appointment appears in both bookings and reschedules queries
        appt = MockAppointment(
            id=100,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(minutes=30),
            scheduled_start=now + timedelta(hours=2),  # Not in upcoming window
        )

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.order_by = MagicMock(return_value=query_mock)
        query_mock.limit = MagicMock(return_value=query_mock)
        # Return the same appointment for all queries
        query_mock.all = MagicMock(return_value=[appt])
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        with patch("routes.scheduler.notifications.get_models", return_value=mock_models):
            result = _generate_notifications_for_user(db, 1, 1, limit=50, since_hours=72)

        # Each notification gets a unique stable_id, so dedup happens by ID
        ids = [n["id"] for n in result]
        assert len(ids) == len(set(ids))  # All unique


# ---------------------------------------------------------------------------
# Tests: Route Endpoints
# ---------------------------------------------------------------------------

class TestGetNotifications:
    """Tests for GET /notifications."""

    @pytest.mark.asyncio
    async def test_get_notifications_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.notifications import get_notifications

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await get_notifications(MagicMock(), 50, 72, MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_notifications_happy_path(self):
        """Authenticated user gets notification feed."""
        from routes.scheduler.notifications import get_notifications

        user = MockUser()

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.notifications._generate_notifications_for_user",
                    return_value=[{"id": "abc123", "type": "booking", "title": "New booking"}]):
            result = await get_notifications(MagicMock(), 50, 72, MagicMock())

        assert result["total"] == 1
        assert result["notifications"][0]["type"] == "booking"

    @pytest.mark.asyncio
    async def test_get_notifications_no_user_id_returns_401(self):
        """User object without id should return 401."""
        from routes.scheduler.notifications import get_notifications

        user = MockUser()
        user.id = None

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await get_notifications(MagicMock(), 50, 72, MagicMock())
            assert exc_info.value.status_code == 401


class TestMarkNotificationRead:
    """Tests for PUT /notifications/{notification_id}/read."""

    @pytest.mark.asyncio
    async def test_mark_read_returns_success(self):
        """Marking a notification as read should acknowledge."""
        from routes.scheduler.notifications import mark_notification_read

        user = MockUser()

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock, return_value=user):
            result = await mark_notification_read("abc123", MagicMock(), MagicMock())

        assert result["success"] is True
        assert result["notification_id"] == "abc123"
        assert result["status"] == "read"

    @pytest.mark.asyncio
    async def test_mark_read_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.notifications import mark_notification_read

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await mark_notification_read("abc123", MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401


class TestMarkAllRead:
    """Tests for PUT /notifications/read-all."""

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_success(self):
        """Marking all as read should return success."""
        from routes.scheduler.notifications import mark_all_notifications_read

        user = MockUser()

        with patch("routes.scheduler.notifications.get_current_user",
                    new_callable=AsyncMock, return_value=user):
            result = await mark_all_notifications_read(MagicMock(), MagicMock())

        assert result["success"] is True
        assert result["status"] == "all_read"
