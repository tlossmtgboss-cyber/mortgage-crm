"""
Tests for scheduler bulk operations routes.

Covers:
  - POST /appointments/bulk-create       Batch appointment creation
  - POST /appointments/bulk-cancel       Batch cancellation
  - POST /appointments/bulk-reschedule   Batch rescheduling
  - POST /appointments/bulk-assign       Batch LO reassignment (admin only)

Focus: validation, auth/permission checks, partial failure handling,
tenant isolation, and size limits.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="admin", email="admin@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email
        self.full_name = "Admin User"
        self.first_name = "Admin"
        self.last_name = "User"


class MockAppointment:
    """Minimal mock appointment object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.organization_id = kwargs.get("organization_id", 1)
        self.title = kwargs.get("title", "Loan Review")
        self.status = kwargs.get("status", MagicMock(value="booked"))
        self.assigned_user_id = kwargs.get("assigned_user_id", 1)
        self.created_by_user_id = kwargs.get("created_by_user_id", 1)
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc))
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.attendee_name = kwargs.get("attendee_name", "John Smith")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.attendee_phone = "+15551234567"
        self.lead_id = kwargs.get("lead_id", 10)
        self.loan_id = kwargs.get("loan_id", 20)
        self.meeting_mode = MagicMock(value="video")
        self.meeting_type = MagicMock(value="review_call")
        self.video_link = None
        self.reschedule_count = 0
        self.cancelled_at = None
        self.cancellation_reason = None
        self.status_changed_at = None
        self.status_changed_by = None


# Fake AppointmentStatus enum for comparisons
class FakeAppointmentStatus:
    BOOKED = "booked"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBulkCreate:
    """Tests for POST /appointments/bulk-create."""

    @pytest.mark.asyncio
    async def test_bulk_create_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.bulk_operations import bulk_create_appointments, BulkCreateRequest, BulkAppointmentItem

        payload = BulkCreateRequest(appointments=[
            BulkAppointmentItem(
                title="Test",
                scheduled_start=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            )
        ])

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await bulk_create_appointments(payload, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_bulk_create_non_admin_cannot_assign_others(self):
        """Non-admin users cannot create appointments assigned to other users."""
        from routes.scheduler.bulk_operations import bulk_create_appointments, BulkCreateRequest, BulkAppointmentItem

        non_admin = MockUser(id=5, role="loan_officer")
        payload = BulkCreateRequest(
            appointments=[
                BulkAppointmentItem(
                    title="Assigned to someone else",
                    scheduled_start=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
                    assigned_user_id=99,  # Different user
                )
            ],
            send_notifications=False,
        )

        db = MagicMock()
        db.commit = MagicMock()
        db.begin_nested = MagicMock(return_value=MagicMock())

        mock_appointment_class = MagicMock()
        mock_models = {"Appointment": mock_appointment_class}

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin), \
             patch("routes.scheduler.bulk_operations.get_models", return_value=mock_models), \
             patch("routes.scheduler.bulk_operations._check_appointment_conflict"), \
             patch("routes.scheduler.bulk_operations._check_duplicate_booking"), \
             patch("routes.scheduler.bulk_operations._audit_log"), \
             patch("routes.scheduler.bulk_operations._log_appointment_activity"), \
             patch("routes.scheduler.bulk_operations._ensure_lead_for_booking", return_value=None), \
             patch("routes.scheduler.bulk_operations._create_followup_task"):
            result = await bulk_create_appointments(payload, MagicMock(), db)

        # The item should fail since non-admin tried to assign to a different user
        assert result.failed == 1
        assert result.succeeded == 0
        assert "Non-admin" in result.results[0].error

    @pytest.mark.asyncio
    async def test_bulk_create_validates_max_size(self):
        """Request with > MAX_BULK_SIZE items should be rejected by Pydantic."""
        from routes.scheduler.bulk_operations import BulkCreateRequest, BulkAppointmentItem

        # Pydantic should reject lists longer than MAX_BULK_SIZE (50)
        items = [
            BulkAppointmentItem(
                title=f"Appt {i}",
                scheduled_start=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc) + timedelta(hours=i),
            )
            for i in range(51)
        ]

        with pytest.raises(Exception):
            # This should raise a validation error
            BulkCreateRequest(appointments=items)


class TestBulkCancel:
    """Tests for POST /appointments/bulk-cancel."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_deduplicates_ids(self):
        """Duplicate appointment IDs should be deduplicated."""
        from routes.scheduler.bulk_operations import bulk_cancel_appointments, BulkCancelRequest

        admin = MockUser(role="admin")
        mock_appt = MockAppointment(id=100)

        db = MagicMock()
        db.commit = MagicMock()
        savepoint = MagicMock()
        db.begin_nested = MagicMock(return_value=savepoint)

        # DB query returns the appointment
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=mock_appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock(), "User": MagicMock()}

        payload = BulkCancelRequest(
            appointment_ids=[100, 100, 100],  # Duplicates
            reason="test",
            send_notifications=False,
        )

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.bulk_operations.get_models", return_value=mock_models), \
             patch("routes.scheduler.bulk_operations._audit_log"), \
             patch("routes.scheduler.bulk_operations._log_appointment_activity"), \
             patch("routes.scheduler.bulk_operations._create_followup_task"), \
             patch("routes.scheduler.bulk_operations.AppointmentStatus", FakeAppointmentStatus):
            result = await bulk_cancel_appointments(payload, MagicMock(), db)

        # Only 1 unique ID, so total should be 1
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_bulk_cancel_not_found_returns_failure(self):
        """Appointment not found results in a failed item, not a crash."""
        from routes.scheduler.bulk_operations import bulk_cancel_appointments, BulkCancelRequest

        admin = MockUser(role="admin")

        db = MagicMock()
        db.commit = MagicMock()
        savepoint = MagicMock()
        db.begin_nested = MagicMock(return_value=savepoint)

        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)  # Not found
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock(), "User": MagicMock()}

        payload = BulkCancelRequest(
            appointment_ids=[999],
            send_notifications=False,
        )

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.bulk_operations.get_models", return_value=mock_models), \
             patch("routes.scheduler.bulk_operations.AppointmentStatus", FakeAppointmentStatus):
            result = await bulk_cancel_appointments(payload, MagicMock(), db)

        assert result.failed == 1
        assert result.succeeded == 0
        assert "not found" in result.results[0].error


class TestBulkReschedule:
    """Tests for POST /appointments/bulk-reschedule."""

    @pytest.mark.asyncio
    async def test_bulk_reschedule_cancelled_appointment_fails(self):
        """Cannot reschedule a cancelled appointment."""
        from routes.scheduler.bulk_operations import bulk_reschedule_appointments, BulkRescheduleRequest, BulkRescheduleItem

        admin = MockUser(role="admin")
        cancelled_appt = MockAppointment(id=100)
        cancelled_appt.status = FakeAppointmentStatus.CANCELLED

        db = MagicMock()
        db.commit = MagicMock()
        savepoint = MagicMock()
        db.begin_nested = MagicMock(return_value=savepoint)

        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=cancelled_appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        payload = BulkRescheduleRequest(
            items=[BulkRescheduleItem(
                appointment_id=100,
                new_scheduled_start=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
            )],
            send_notifications=False,
        )

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.bulk_operations.get_models", return_value=mock_models), \
             patch("routes.scheduler.bulk_operations.AppointmentStatus", FakeAppointmentStatus):
            result = await bulk_reschedule_appointments(payload, MagicMock(), db)

        assert result.failed == 1
        assert "cancelled" in result.results[0].error.lower()


class TestBulkAssign:
    """Tests for POST /appointments/bulk-assign."""

    @pytest.mark.asyncio
    async def test_bulk_assign_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.bulk_operations import bulk_assign_appointments, BulkAssignRequest, BulkAssignItem

        non_admin = MockUser(role="loan_officer")
        payload = BulkAssignRequest(items=[
            BulkAssignItem(appointment_id=100, new_lo_id=5),
        ])

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            with pytest.raises(HTTPException) as exc_info:
                await bulk_assign_appointments(payload, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_assign_invalid_lo_fails(self):
        """Assignment to a non-existent LO in the org should fail."""
        from routes.scheduler.bulk_operations import bulk_assign_appointments, BulkAssignRequest, BulkAssignItem

        admin = MockUser(role="admin")
        db = MagicMock()
        db.commit = MagicMock()
        savepoint = MagicMock()
        db.begin_nested = MagicMock(return_value=savepoint)

        # Pre-validation query returns no valid LOs
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.all = MagicMock(return_value=[])
        query_mock.first = MagicMock(return_value=None)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock(), "User": MagicMock()}

        payload = BulkAssignRequest(
            items=[BulkAssignItem(appointment_id=100, new_lo_id=999)],
            send_notifications=False,
        )

        with patch("routes.scheduler.bulk_operations.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.bulk_operations.get_models", return_value=mock_models), \
             patch("routes.scheduler.bulk_operations.AppointmentStatus", FakeAppointmentStatus):
            result = await bulk_assign_appointments(payload, MagicMock(), db)

        assert result.failed == 1
        assert "not found" in result.results[0].error.lower()
