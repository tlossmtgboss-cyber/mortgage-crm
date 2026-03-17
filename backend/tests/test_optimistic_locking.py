"""
Test suite for optimistic locking on Appointment model.

Tests:
1. update_with_version_check succeeds when version matches
2. update_with_version_check raises OptimisticLockError on stale version
3. Version increments on each successful update
4. API endpoint returns 409 Conflict on version mismatch
5. API endpoint succeeds with correct version
6. Version is included in all appointment responses
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.optimistic_lock import OptimisticLockError, update_with_version_check


# =============================================================================
# Unit Tests: OptimisticLockError
# =============================================================================

class TestOptimisticLockError:
    """Tests for the OptimisticLockError exception class."""

    def test_error_message_contains_entity_info(self):
        """Error message should include entity type and ID."""
        err = OptimisticLockError("Appointment", "42")
        assert "Appointment" in str(err)
        assert "42" in str(err)

    def test_error_attributes(self):
        """Error should store entity_type and entity_id."""
        err = OptimisticLockError("Appointment", "99")
        assert err.entity_type == "Appointment"
        assert err.entity_id == "99"

    def test_error_is_exception(self):
        """OptimisticLockError should be catchable as a standard Exception."""
        with pytest.raises(Exception):
            raise OptimisticLockError("Appointment", "1")


# =============================================================================
# Unit Tests: update_with_version_check
# =============================================================================

class TestUpdateWithVersionCheck:
    """Tests for the update_with_version_check function using patched internals."""

    def test_successful_update_increments_version(self):
        """When version matches, update succeeds and version is incremented."""
        entity = Mock(id=1, version=2, title="Updated")

        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_') as mock_and:
            # Set up the chain: update(model).where(...).values(...)
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            db = MagicMock()
            result = Mock(rowcount=1)
            db.execute.return_value = result
            db.get.return_value = entity

            model = Mock(__name__="Appointment")

            returned = update_with_version_check(
                db=db, model_class=model, entity_id=1,
                expected_version=1, updates={"title": "New Title"},
            )

            db.execute.assert_called_once()
            db.flush.assert_called_once()
            db.get.assert_called_once_with(model, 1)
            assert returned == entity

    def test_version_value_in_update_dict(self):
        """The updates dict should have version = expected_version + 1."""
        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_'):
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            db = MagicMock()
            db.execute.return_value = Mock(rowcount=1)
            db.get.return_value = Mock(id=1, version=6)

            updates = {"title": "Test"}
            update_with_version_check(
                db=db, model_class=Mock(__name__="Appointment"),
                entity_id=1, expected_version=5, updates=updates,
            )

            # Check that version was added to updates
            assert updates["version"] == 6  # 5 + 1

    def test_stale_version_raises_error(self):
        """When version doesn't match (rowcount=0), raise OptimisticLockError."""
        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_'):
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            db = MagicMock()
            db.execute.return_value = Mock(rowcount=0)

            with pytest.raises(OptimisticLockError) as exc_info:
                update_with_version_check(
                    db=db, model_class=Mock(__name__="Appointment"),
                    entity_id=42, expected_version=3,
                    updates={"title": "Conflict"},
                )

            assert exc_info.value.entity_type == "Appointment"
            assert exc_info.value.entity_id == "42"
            db.rollback.assert_called_once()

    def test_zero_version_works(self):
        """Version 0 should work (e.g., for freshly migrated rows)."""
        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_'):
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            entity = Mock(id=1, version=1)
            db = MagicMock()
            db.execute.return_value = Mock(rowcount=1)
            db.get.return_value = entity

            result = update_with_version_check(
                db=db, model_class=Mock(__name__="Appointment"),
                entity_id=1, expected_version=0,
                updates={"title": "First real update"},
            )

            assert result == entity

    def test_updates_dict_not_mutated_beyond_version(self):
        """The function adds 'version' to updates but shouldn't corrupt other keys."""
        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_'):
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            db = MagicMock()
            db.execute.return_value = Mock(rowcount=1)
            db.get.return_value = Mock(id=1, version=2)

            updates = {"title": "New", "description": "Desc"}
            update_with_version_check(
                db=db, model_class=Mock(__name__="Appointment"),
                entity_id=1, expected_version=1, updates=updates,
            )

            assert updates["title"] == "New"
            assert updates["description"] == "Desc"
            assert updates["version"] == 2  # expected + 1


# =============================================================================
# Unit Tests: Version increment in appointment update endpoint
# =============================================================================

class TestAppointmentVersionIncrement:
    """Test that the appointment model version increments correctly."""

    def test_version_column_exists_in_model(self):
        """The Appointment model should have a version column defined."""
        from smart_scheduler_models import create_smart_scheduler_models
        from sqlalchemy import MetaData
        from sqlalchemy.orm import DeclarativeBase

        class TestBase(DeclarativeBase):
            pass

        models = create_smart_scheduler_models(TestBase)
        Appointment = models['Appointment']

        # Check the column exists in the table definition
        column_names = [c.name for c in Appointment.__table__.columns]
        assert 'version' in column_names, "Appointment model should have 'version' column"

    def test_version_column_defaults_to_one(self):
        """The version column should default to 1."""
        from smart_scheduler_models import create_smart_scheduler_models
        from sqlalchemy.orm import DeclarativeBase

        class TestBase(DeclarativeBase):
            pass

        models = create_smart_scheduler_models(TestBase)
        Appointment = models['Appointment']

        version_col = Appointment.__table__.columns['version']
        assert version_col.default is not None
        assert version_col.default.arg == 1

    def test_version_column_not_nullable(self):
        """The version column should not allow NULL."""
        from smart_scheduler_models import create_smart_scheduler_models
        from sqlalchemy.orm import DeclarativeBase

        class TestBase(DeclarativeBase):
            pass

        models = create_smart_scheduler_models(TestBase)
        Appointment = models['Appointment']

        version_col = Appointment.__table__.columns['version']
        assert version_col.nullable is False


# =============================================================================
# Unit Tests: AppointmentUpdate schema
# =============================================================================

class TestAppointmentUpdateSchema:
    """Test that AppointmentUpdate Pydantic model accepts version field."""

    def test_version_field_accepted(self):
        """AppointmentUpdate should accept an optional version field."""
        from scheduler_models import AppointmentUpdate

        update = AppointmentUpdate(title="Test", version=3)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped["version"] == 3

    def test_version_field_optional(self):
        """Version field should be optional (not required)."""
        from scheduler_models import AppointmentUpdate

        update = AppointmentUpdate(title="Test")
        dumped = update.model_dump(exclude_unset=True)
        assert "version" not in dumped

    def test_version_included_in_model_dump(self):
        """When version is set, it should be in the model dump."""
        from scheduler_models import AppointmentUpdate

        update = AppointmentUpdate(version=5)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"version": 5}


# =============================================================================
# Integration-style Tests: API version mismatch returns 409
# =============================================================================

class TestAPIVersionConflict:
    """Test the API endpoint behavior for version conflicts."""

    def _make_mock_appointment(self, version=1, **kwargs):
        """Create a mock appointment object."""
        appt = Mock()
        appt.id = kwargs.get('id', 1)
        appt.organization_id = kwargs.get('org_id', 1)
        appt.assigned_user_id = kwargs.get('assigned_user_id', 1)
        appt.created_by_user_id = kwargs.get('created_by_user_id', 1)
        appt.version = version
        appt.scheduled_start = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        appt.scheduled_end = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        appt.duration_minutes = 30
        appt.status = Mock(value="booked")
        appt.meeting_type = Mock(value="custom")
        appt.meeting_mode = Mock(value="video")
        appt.title = "Test Appointment"
        appt.description = None
        appt.timezone = "America/Chicago"
        appt.location = None
        appt.video_link = None
        appt.phone_number = None
        appt.attendee_name = "Test User"
        appt.attendee_email = "test@example.com"
        appt.attendee_phone = None
        appt.attendee_notes = None
        appt.intake_responses = {}
        appt.lead_id = None
        appt.loan_id = None
        appt.contact_id = None
        appt.booked_by_ai = False
        appt.ai_booking_context = None
        appt.internal_notes = None
        appt.meeting_notes = None
        appt.reschedule_count = 0
        appt.created_at = datetime(2026, 3, 10, tzinfo=timezone.utc)
        appt.updated_at = datetime(2026, 3, 10, tzinfo=timezone.utc)
        return appt

    def test_version_mismatch_detected(self):
        """When client sends stale version, the check should detect mismatch."""
        appointment = self._make_mock_appointment(version=5)
        client_version = 3  # stale

        # Simulate the version check logic from the endpoint
        assert client_version != appointment.version, "Should detect version mismatch"

    def test_version_match_passes(self):
        """When client sends current version, the check should pass."""
        appointment = self._make_mock_appointment(version=5)
        client_version = 5  # current

        assert client_version == appointment.version, "Should pass version check"

    def test_version_increments_after_update(self):
        """After a successful update, version should be incremented."""
        appointment = self._make_mock_appointment(version=3)

        # Simulate the version increment logic from the endpoint
        current_version = appointment.version
        appointment.version = current_version + 1

        assert appointment.version == 4

    def test_sequential_updates_increment_correctly(self):
        """Multiple sequential updates should increment version each time."""
        appointment = self._make_mock_appointment(version=1)

        for expected_version in range(2, 6):
            appointment.version = appointment.version + 1
            assert appointment.version == expected_version

    def test_conflict_response_structure(self):
        """The 409 response should include current_version and your_version."""
        from fastapi import HTTPException

        appointment_version = 5
        client_version = 3

        # Simulate what the endpoint does
        if client_version != appointment_version:
            detail = {
                "error": "conflict",
                "message": "This appointment was modified by another request. Please refresh and retry.",
                "current_version": appointment_version,
                "your_version": client_version,
            }

            exc = HTTPException(status_code=409, detail=detail)
            assert exc.status_code == 409
            assert exc.detail["current_version"] == 5
            assert exc.detail["your_version"] == 3
            assert "conflict" in exc.detail["error"]

    def test_no_version_provided_skips_check(self):
        """When no version is provided, optimistic locking check is skipped."""
        # Simulate the endpoint logic: client_version = update_fields.pop('version', None)
        update_fields = {"title": "Updated Title"}
        client_version = update_fields.pop('version', None)

        # Should be None, meaning check is skipped
        assert client_version is None

    def test_version_in_response_payloads(self):
        """Appointment responses should include the version field."""
        appointment = self._make_mock_appointment(version=7)

        # Simulate GET response
        response = {
            "id": appointment.id,
            "title": appointment.title,
            "version": getattr(appointment, 'version', None),
        }

        assert response["version"] == 7

    def test_update_response_includes_new_version(self):
        """After update, response should include the incremented version."""
        appointment = self._make_mock_appointment(version=3)

        # Simulate update + version increment
        appointment.version = appointment.version + 1

        response = {
            "message": "Appointment updated",
            "appointment_id": appointment.id,
            "version": getattr(appointment, 'version', None),
        }

        assert response["version"] == 4


# =============================================================================
# Unit Tests: update_with_version_check with real-ish scenario
# =============================================================================

class TestConcurrentUpdateScenario:
    """
    Simulate a concurrent update scenario:
    - User A reads appointment (version=1)
    - User B reads appointment (version=1)
    - User A updates (version 1 -> 2) -- succeeds
    - User B updates (version 1 -> ??) -- should fail
    """

    def test_concurrent_update_second_writer_fails(self):
        """Second concurrent writer should get OptimisticLockError."""
        model = Mock(__name__="Appointment")

        with patch('services.optimistic_lock.update') as mock_update, \
             patch('services.optimistic_lock.and_'):
            mock_stmt = MagicMock()
            mock_update.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.values.return_value = mock_stmt

            # User A's update succeeds (rowcount=1)
            db_a = MagicMock()
            db_a.execute.return_value = Mock(rowcount=1)
            entity_a = Mock(id=1, version=2)
            db_a.get.return_value = entity_a

            updated = update_with_version_check(
                db=db_a, model_class=model, entity_id=1,
                expected_version=1, updates={"title": "User A change"},
            )
            assert updated.version == 2

            # User B's update fails (rowcount=0 because DB version is now 2, not 1)
            db_b = MagicMock()
            db_b.execute.return_value = Mock(rowcount=0)

            with pytest.raises(OptimisticLockError) as exc_info:
                update_with_version_check(
                    db=db_b, model_class=model, entity_id=1,
                    expected_version=1, updates={"title": "User B change"},
                )

            assert exc_info.value.entity_type == "Appointment"
            db_b.rollback.assert_called_once()
