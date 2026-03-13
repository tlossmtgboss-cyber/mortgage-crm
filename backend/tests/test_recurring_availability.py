"""
Tests for Recurring Availability System

Tests cover:
- Model creation and constraints
- RecurringAvailabilityService methods
- Weekly schedule CRUD
- Exception management
- Template management
- Effective schedule computation (recurring + exceptions merge)
- Slot computation with appointment conflicts
- Edge cases (overlapping blocks, full-day blocks, empty schedules)
- Route endpoint validation
- Integration with existing slot generation engine
"""

import pytest
from datetime import datetime, date, time, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import Base
from database.models.recurring_availability import (
    RecurringAvailability,
    AvailabilityException,
    AvailabilityTemplate,
)
from services.recurring_availability_service import RecurringAvailabilityService


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def test_engine():
    """Create in-memory SQLite engine for tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Create only the tables we need for these tests
    RecurringAvailability.__table__.create(bind=engine, checkfirst=True)
    AvailabilityException.__table__.create(bind=engine, checkfirst=True)
    AvailabilityTemplate.__table__.create(bind=engine, checkfirst=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Create a fresh DB session with transaction rollback for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def service(db_session):
    """Create a RecurringAvailabilityService instance."""
    return RecurringAvailabilityService(db_session)


@pytest.fixture
def standard_schedule():
    """Standard Mon-Fri 9-5 schedule with lunch break."""
    return {
        0: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],  # Mon
        1: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],  # Tue
        2: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],  # Wed
        3: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],  # Thu
        4: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],  # Fri
    }


# =============================================================================
# MODEL TESTS
# =============================================================================

class TestRecurringAvailabilityModel:
    """Test the RecurringAvailability SQLAlchemy model."""

    def test_create_recurring_availability(self, db_session):
        """Test creating a recurring availability record."""
        row = RecurringAvailability(
            user_id=1,
            organization_id=1,
            day_of_week=0,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_active=True,
            timezone="America/Chicago",
        )
        db_session.add(row)
        db_session.flush()

        assert row.id is not None
        assert row.day_of_week == 0
        assert row.start_time == time(9, 0)
        assert row.end_time == time(17, 0)
        assert row.is_active is True

    def test_create_with_effective_dates(self, db_session):
        """Test creating recurring availability with effective date range."""
        row = RecurringAvailability(
            user_id=1,
            organization_id=1,
            day_of_week=5,  # Saturday
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_active=True,
            effective_from=date(2026, 6, 1),
            effective_until=date(2026, 8, 31),
            timezone="America/New_York",
        )
        db_session.add(row)
        db_session.flush()

        assert row.effective_from == date(2026, 6, 1)
        assert row.effective_until == date(2026, 8, 31)
        assert row.timezone == "America/New_York"

    def test_multiple_blocks_per_day(self, db_session):
        """Test multiple availability blocks on the same day (morning + afternoon)."""
        morning = RecurringAvailability(
            user_id=1, organization_id=1, day_of_week=0,
            start_time=time(9, 0), end_time=time(12, 0), is_active=True,
        )
        afternoon = RecurringAvailability(
            user_id=1, organization_id=1, day_of_week=0,
            start_time=time(13, 0), end_time=time(17, 0), is_active=True,
        )
        db_session.add_all([morning, afternoon])
        db_session.flush()

        rows = db_session.query(RecurringAvailability).filter(
            RecurringAvailability.user_id == 1,
            RecurringAvailability.day_of_week == 0,
        ).all()
        assert len(rows) == 2


class TestAvailabilityExceptionModel:
    """Test the AvailabilityException model."""

    def test_create_full_day_block(self, db_session):
        """Test creating a full-day block exception."""
        exc = AvailabilityException(
            user_id=1,
            organization_id=1,
            date=date(2026, 12, 25),
            is_blocked=True,
            reason="Christmas Holiday",
        )
        db_session.add(exc)
        db_session.flush()

        assert exc.id is not None
        assert exc.start_time is None
        assert exc.end_time is None
        assert exc.is_blocked is True
        assert exc.reason == "Christmas Holiday"

    def test_create_partial_block(self, db_session):
        """Test creating a partial-day block exception."""
        exc = AvailabilityException(
            user_id=1,
            organization_id=1,
            date=date(2026, 3, 15),
            start_time=time(14, 0),
            end_time=time(16, 0),
            is_blocked=True,
            reason="Doctor appointment",
        )
        db_session.add(exc)
        db_session.flush()

        assert exc.start_time == time(14, 0)
        assert exc.end_time == time(16, 0)

    def test_create_extra_availability(self, db_session):
        """Test creating an extra availability exception (is_blocked=False)."""
        exc = AvailabilityException(
            user_id=1,
            organization_id=1,
            date=date(2026, 3, 16),  # Saturday
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_blocked=False,
            reason="Extra office hours for busy season",
        )
        db_session.add(exc)
        db_session.flush()

        assert exc.is_blocked is False


class TestAvailabilityTemplateModel:
    """Test the AvailabilityTemplate model."""

    def test_create_template(self, db_session):
        """Test creating an availability template."""
        schedule = {
            "0": [{"start": "09:00", "end": "17:00"}],
            "1": [{"start": "09:00", "end": "17:00"}],
            "2": [{"start": "09:00", "end": "17:00"}],
            "3": [{"start": "09:00", "end": "17:00"}],
            "4": [{"start": "09:00", "end": "17:00"}],
        }
        tmpl = AvailabilityTemplate(
            organization_id=1,
            name="Standard 9-5",
            description="Standard Monday-Friday 9am to 5pm",
            schedule=schedule,
            is_default=True,
            timezone="America/Chicago",
        )
        db_session.add(tmpl)
        db_session.flush()

        assert tmpl.id is not None
        assert tmpl.name == "Standard 9-5"
        assert tmpl.is_default is True
        assert "0" in tmpl.schedule


# =============================================================================
# SERVICE TESTS - WEEKLY SCHEDULE
# =============================================================================

class TestWeeklyScheduleService:
    """Test weekly schedule management."""

    def test_set_weekly_schedule(self, service, db_session, standard_schedule):
        """Test setting a complete weekly schedule."""
        result = service.set_weekly_schedule(
            user_id=1, org_id=1, schedule=standard_schedule
        )
        db_session.flush()

        # 5 days * 2 blocks = 10 total blocks
        assert len(result) == 10
        assert result[0]["day_of_week"] == 0
        assert result[0]["start_time"] == "09:00"
        assert result[0]["end_time"] == "12:00"

    def test_get_weekly_schedule(self, service, db_session, standard_schedule):
        """Test retrieving the weekly schedule."""
        service.set_weekly_schedule(user_id=1, org_id=1, schedule=standard_schedule)
        db_session.flush()

        schedule = service.get_weekly_schedule(user_id=1, org_id=1)
        assert len(schedule) == 10

        # Verify Monday morning block
        monday_blocks = [b for b in schedule if b["day_of_week"] == 0]
        assert len(monday_blocks) == 2
        assert monday_blocks[0]["start_time"] == "09:00"
        assert monday_blocks[0]["end_time"] == "12:00"

    def test_set_schedule_replaces_previous(self, service, db_session):
        """Test that setting a new schedule deactivates the old one."""
        # Set initial schedule
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        db_session.flush()

        # Set new schedule
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "10:00", "end": "16:00"}]}
        )
        db_session.flush()

        schedule = service.get_weekly_schedule(user_id=1, org_id=1)
        assert len(schedule) == 1
        assert schedule[0]["start_time"] == "10:00"
        assert schedule[0]["end_time"] == "16:00"

    def test_set_schedule_invalid_day(self, service):
        """Test that invalid day_of_week raises ValueError."""
        with pytest.raises(ValueError, match="Invalid day_of_week"):
            service.set_weekly_schedule(
                user_id=1, org_id=1,
                schedule={7: [{"start": "09:00", "end": "17:00"}]}
            )

    def test_set_schedule_invalid_time_order(self, service):
        """Test that start >= end raises ValueError."""
        with pytest.raises(ValueError, match="must be before"):
            service.set_weekly_schedule(
                user_id=1, org_id=1,
                schedule={0: [{"start": "17:00", "end": "09:00"}]}
            )

    def test_set_schedule_same_start_end(self, service):
        """Test that start == end raises ValueError."""
        with pytest.raises(ValueError, match="must be before"):
            service.set_weekly_schedule(
                user_id=1, org_id=1,
                schedule={0: [{"start": "09:00", "end": "09:00"}]}
            )

    def test_empty_schedule(self, service, db_session):
        """Test setting an empty schedule (no days)."""
        result = service.set_weekly_schedule(user_id=1, org_id=1, schedule={})
        db_session.flush()
        assert len(result) == 0

    def test_schedule_with_timezone(self, service, db_session):
        """Test setting schedule with specific timezone."""
        result = service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]},
            tz="America/New_York",
        )
        db_session.flush()

        assert result[0]["timezone"] == "America/New_York"

    def test_multi_user_isolation(self, service, db_session):
        """Test that different users have separate schedules."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        service.set_weekly_schedule(
            user_id=2, org_id=1,
            schedule={0: [{"start": "10:00", "end": "18:00"}]}
        )
        db_session.flush()

        user1_schedule = service.get_weekly_schedule(user_id=1, org_id=1)
        user2_schedule = service.get_weekly_schedule(user_id=2, org_id=1)

        assert user1_schedule[0]["start_time"] == "09:00"
        assert user2_schedule[0]["start_time"] == "10:00"


# =============================================================================
# SERVICE TESTS - EXCEPTIONS
# =============================================================================

class TestExceptionService:
    """Test exception management."""

    def test_add_full_day_block(self, service, db_session):
        """Test adding a full-day block exception."""
        exc = service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 12, 25),
            is_blocked=True,
            reason="Christmas",
        )
        db_session.flush()

        assert exc["date"] == "2026-12-25"
        assert exc["is_blocked"] is True
        assert exc["start_time"] is None
        assert exc["end_time"] is None
        assert exc["reason"] == "Christmas"

    def test_add_partial_block(self, service, db_session):
        """Test adding a partial-day block."""
        exc = service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 20),
            start_time=time(14, 0),
            end_time=time(16, 0),
            is_blocked=True,
            reason="Meeting",
        )
        db_session.flush()

        assert exc["start_time"] == "14:00"
        assert exc["end_time"] == "16:00"

    def test_add_extra_availability(self, service, db_session):
        """Test adding extra availability on a non-work day."""
        exc = service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 21),  # Saturday
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_blocked=False,
            reason="Extra hours",
        )
        db_session.flush()

        assert exc["is_blocked"] is False

    def test_add_extra_availability_requires_times(self, service):
        """Test that extra availability without times raises ValueError."""
        with pytest.raises(ValueError, match="start_time and end_time are required"):
            service.add_exception(
                user_id=1, org_id=1,
                exc_date=date(2026, 3, 21),
                is_blocked=False,
            )

    def test_add_exception_invalid_time_order(self, service):
        """Test that start >= end raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be before end_time"):
            service.add_exception(
                user_id=1, org_id=1,
                exc_date=date(2026, 3, 20),
                start_time=time(16, 0),
                end_time=time(14, 0),
                is_blocked=True,
            )

    def test_get_exceptions(self, service, db_session):
        """Test listing exceptions."""
        service.add_exception(user_id=1, org_id=1, exc_date=date(2026, 3, 20), is_blocked=True)
        service.add_exception(user_id=1, org_id=1, exc_date=date(2026, 3, 25), is_blocked=True)
        db_session.flush()

        exceptions = service.get_exceptions(user_id=1, org_id=1)
        assert len(exceptions) == 2

    def test_get_exceptions_with_date_filter(self, service, db_session):
        """Test filtering exceptions by date range."""
        service.add_exception(user_id=1, org_id=1, exc_date=date(2026, 3, 1), is_blocked=True)
        service.add_exception(user_id=1, org_id=1, exc_date=date(2026, 3, 15), is_blocked=True)
        service.add_exception(user_id=1, org_id=1, exc_date=date(2026, 3, 30), is_blocked=True)
        db_session.flush()

        # Filter: only March 10-20
        exceptions = service.get_exceptions(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 20),
        )
        assert len(exceptions) == 1
        assert exceptions[0]["date"] == "2026-03-15"

    def test_remove_exception(self, service, db_session):
        """Test removing an exception."""
        exc = service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 20),
            is_blocked=True,
        )
        db_session.flush()

        deleted = service.remove_exception(exc["id"], user_id=1, org_id=1)
        assert deleted is True

        # Verify it's gone
        remaining = service.get_exceptions(user_id=1, org_id=1)
        assert len(remaining) == 0

    def test_remove_exception_not_found(self, service):
        """Test removing a non-existent exception."""
        deleted = service.remove_exception(99999, user_id=1, org_id=1)
        assert deleted is False

    def test_remove_exception_wrong_user(self, service, db_session):
        """Test that removing another user's exception fails."""
        exc = service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 20),
            is_blocked=True,
        )
        db_session.flush()

        # Try to delete as user 2
        deleted = service.remove_exception(exc["id"], user_id=2, org_id=1)
        assert deleted is False


# =============================================================================
# SERVICE TESTS - TEMPLATES
# =============================================================================

class TestTemplateService:
    """Test template management."""

    def test_create_template(self, service, db_session):
        """Test creating a template."""
        schedule = {
            "0": [{"start": "09:00", "end": "17:00"}],
            "1": [{"start": "09:00", "end": "17:00"}],
        }
        template = service.create_template(
            org_id=1,
            name="Standard 9-5",
            description="Monday-Tuesday only",
            schedule=schedule,
        )
        db_session.flush()

        assert template["id"] is not None
        assert template["name"] == "Standard 9-5"
        assert "0" in template["schedule"]

    def test_create_default_template(self, service, db_session):
        """Test creating a default template clears previous defaults."""
        service.create_template(
            org_id=1, name="Old Default",
            schedule={"0": [{"start": "09:00", "end": "17:00"}]},
            is_default=True,
        )
        db_session.flush()

        service.create_template(
            org_id=1, name="New Default",
            schedule={"0": [{"start": "10:00", "end": "18:00"}]},
            is_default=True,
        )
        db_session.flush()

        templates = service.get_templates(org_id=1)
        defaults = [t for t in templates if t["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "New Default"

    def test_get_templates(self, service, db_session):
        """Test listing org templates."""
        service.create_template(org_id=1, name="Template A", schedule={"0": []})
        service.create_template(org_id=1, name="Template B", schedule={"0": []})
        db_session.flush()

        templates = service.get_templates(org_id=1)
        assert len(templates) >= 2

    def test_get_templates_org_isolation(self, service, db_session):
        """Test that templates are scoped by organization."""
        service.create_template(org_id=1, name="Org1 Template", schedule={"0": []})
        service.create_template(org_id=2, name="Org2 Template", schedule={"0": []})
        db_session.flush()

        org1_templates = service.get_templates(org_id=1)
        org2_templates = service.get_templates(org_id=2)

        org1_names = [t["name"] for t in org1_templates]
        org2_names = [t["name"] for t in org2_templates]

        assert "Org1 Template" in org1_names
        assert "Org2 Template" not in org1_names
        assert "Org2 Template" in org2_names

    def test_apply_template(self, service, db_session):
        """Test applying a template to a user."""
        schedule = {
            0: [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "16:00"}],
            1: [{"start": "08:00", "end": "16:00"}],
        }
        template = service.create_template(
            org_id=1, name="Early Bird", schedule=schedule,
        )
        db_session.flush()

        result = service.apply_template(user_id=1, org_id=1, template_id=template["id"])
        db_session.flush()

        assert len(result) == 3  # 2 Mon blocks + 1 Tue block

        # Verify user's schedule was updated
        user_schedule = service.get_weekly_schedule(user_id=1, org_id=1)
        assert len(user_schedule) == 3

    def test_apply_template_not_found(self, service):
        """Test applying a non-existent template."""
        with pytest.raises(ValueError, match="not found"):
            service.apply_template(user_id=1, org_id=1, template_id=99999)

    def test_apply_template_wrong_org(self, service, db_session):
        """Test applying a template from another org."""
        template = service.create_template(
            org_id=2, name="Other Org Template",
            schedule={"0": [{"start": "09:00", "end": "17:00"}]},
        )
        db_session.flush()

        with pytest.raises(ValueError, match="not found"):
            service.apply_template(user_id=1, org_id=1, template_id=template["id"])


# =============================================================================
# SERVICE TESTS - EFFECTIVE SCHEDULE
# =============================================================================

class TestEffectiveSchedule:
    """Test effective schedule computation (recurring + exceptions)."""

    def test_basic_effective_schedule(self, service, db_session):
        """Test effective schedule with no exceptions."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}]}
        )
        db_session.flush()

        # A Monday
        target = date(2026, 3, 16)  # Monday
        schedule = service.get_effective_schedule(user_id=1, org_id=1, target_date=target)

        assert len(schedule) == 2
        assert schedule[0]["start"] == "09:00"
        assert schedule[0]["end"] == "12:00"
        assert schedule[1]["start"] == "13:00"
        assert schedule[1]["end"] == "17:00"

    def test_full_day_block_exception(self, service, db_session):
        """Test that a full-day block removes all availability."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 16),  # Monday
            is_blocked=True,
            reason="Day off",
        )
        db_session.flush()

        schedule = service.get_effective_schedule(
            user_id=1, org_id=1, target_date=date(2026, 3, 16)
        )
        assert len(schedule) == 0

    def test_partial_block_splits_range(self, service, db_session):
        """Test that a partial block splits availability."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        # Block 12:00-13:00 (lunch)
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 16),
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_blocked=True,
        )
        db_session.flush()

        schedule = service.get_effective_schedule(
            user_id=1, org_id=1, target_date=date(2026, 3, 16)
        )
        assert len(schedule) == 2
        assert schedule[0]["start"] == "09:00"
        assert schedule[0]["end"] == "12:00"
        assert schedule[1]["start"] == "13:00"
        assert schedule[1]["end"] == "17:00"

    def test_extra_availability_on_non_work_day(self, service, db_session):
        """Test adding extra availability on a day with no recurring schedule."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}  # Monday only
        )
        # Add Saturday availability
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 21),  # Saturday
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_blocked=False,
        )
        db_session.flush()

        schedule = service.get_effective_schedule(
            user_id=1, org_id=1, target_date=date(2026, 3, 21)
        )
        assert len(schedule) == 1
        assert schedule[0]["start"] == "10:00"
        assert schedule[0]["end"] == "14:00"

    def test_no_schedule_returns_empty(self, service, db_session):
        """Test that a day with no recurring schedule and no exceptions returns empty."""
        schedule = service.get_effective_schedule(
            user_id=99, org_id=1, target_date=date(2026, 3, 16)
        )
        assert schedule == []

    def test_effective_date_filtering(self, service, db_session):
        """Test that effective_from/effective_until are respected."""
        # Summer-only Saturday hours
        row = RecurringAvailability(
            user_id=1, organization_id=1, day_of_week=5,
            start_time=time(10, 0), end_time=time(14, 0),
            is_active=True, timezone="America/Chicago",
            effective_from=date(2026, 6, 1),
            effective_until=date(2026, 8, 31),
        )
        db_session.add(row)
        db_session.flush()

        # Saturday in summer - should be available
        summer_sat = date(2026, 7, 4)
        schedule = service.get_effective_schedule(user_id=1, org_id=1, target_date=summer_sat)
        assert len(schedule) == 1

        # Saturday in winter - should be empty
        winter_sat = date(2026, 12, 5)
        schedule = service.get_effective_schedule(user_id=1, org_id=1, target_date=winter_sat)
        assert len(schedule) == 0

    def test_multiple_exceptions_on_same_date(self, service, db_session):
        """Test multiple exceptions on the same date."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        # Block morning (09:00-10:00)
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 16),
            start_time=time(9, 0), end_time=time(10, 0),
            is_blocked=True, reason="Late start",
        )
        # Block afternoon (15:00-17:00)
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 16),
            start_time=time(15, 0), end_time=time(17, 0),
            is_blocked=True, reason="Early finish",
        )
        db_session.flush()

        schedule = service.get_effective_schedule(
            user_id=1, org_id=1, target_date=date(2026, 3, 16)
        )
        assert len(schedule) == 1
        assert schedule[0]["start"] == "10:00"
        assert schedule[0]["end"] == "15:00"


# =============================================================================
# SERVICE TESTS - SLOT COMPUTATION
# =============================================================================

class TestSlotComputation:
    """Test available slot computation."""

    def test_basic_slot_generation(self, service, db_session):
        """Test generating slots from recurring schedule."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "11:00"}]}  # 2 hours = 4 x 30min slots
        )
        db_session.flush()

        # Query a single Monday
        slots = service.get_available_slots(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 16),
            end_date=date(2026, 3, 16),
            duration_minutes=30,
        )

        assert len(slots) == 4
        assert slots[0]["start"] == "09:00"
        assert slots[0]["end"] == "09:30"
        assert slots[3]["start"] == "10:30"
        assert slots[3]["end"] == "11:00"

    def test_slot_generation_skips_blocked_days(self, service, db_session):
        """Test that blocked exceptions remove slots for that day."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={
                0: [{"start": "09:00", "end": "11:00"}],  # Monday
                1: [{"start": "09:00", "end": "11:00"}],  # Tuesday
            }
        )
        # Block Monday
        service.add_exception(
            user_id=1, org_id=1,
            exc_date=date(2026, 3, 16),  # Monday
            is_blocked=True,
        )
        db_session.flush()

        slots = service.get_available_slots(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 16),  # Monday
            end_date=date(2026, 3, 17),    # Tuesday
            duration_minutes=30,
        )

        # Only Tuesday slots should appear
        dates = set(s["date"] for s in slots)
        assert "2026-03-16" not in dates
        assert "2026-03-17" in dates

    def test_slot_duration_60_minutes(self, service, db_session):
        """Test generating 60-minute slots."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "12:00"}]}  # 3 hours
        )
        db_session.flush()

        slots = service.get_available_slots(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 16),
            end_date=date(2026, 3, 16),
            duration_minutes=60,
        )

        # With 30-min stepping: 09:00-10:00, 09:30-10:30, 10:00-11:00, 10:30-11:30, 11:00-12:00
        assert len(slots) == 5

    def test_max_per_day_limit(self, service, db_session):
        """Test max_per_day limits slots returned."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={0: [{"start": "09:00", "end": "17:00"}]}
        )
        db_session.flush()

        slots = service.get_available_slots(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 16),
            end_date=date(2026, 3, 16),
            duration_minutes=30,
            max_per_day=3,
        )

        assert len(slots) == 3

    def test_multi_day_range(self, service, db_session):
        """Test slot generation across multiple days."""
        service.set_weekly_schedule(
            user_id=1, org_id=1,
            schedule={
                0: [{"start": "09:00", "end": "10:00"}],  # Monday - 2 slots
                1: [{"start": "09:00", "end": "10:00"}],  # Tuesday - 2 slots
                2: [{"start": "09:00", "end": "10:00"}],  # Wednesday - 2 slots
            }
        )
        db_session.flush()

        # Mon-Wed
        slots = service.get_available_slots(
            user_id=1, org_id=1,
            start_date=date(2026, 3, 16),
            end_date=date(2026, 3, 18),
            duration_minutes=30,
        )

        # 2 slots per day * 3 days = 6
        assert len(slots) == 6

        dates = set(s["date"] for s in slots)
        assert len(dates) == 3


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Test internal helper functions."""

    def test_subtract_range_no_overlap(self):
        """Test subtracting a range that doesn't overlap."""
        ranges = [(time(9, 0), time(17, 0))]
        result = RecurringAvailabilityService._subtract_range(
            ranges, time(18, 0), time(19, 0)
        )
        assert result == [(time(9, 0), time(17, 0))]

    def test_subtract_range_middle(self):
        """Test subtracting from the middle of a range."""
        ranges = [(time(9, 0), time(17, 0))]
        result = RecurringAvailabilityService._subtract_range(
            ranges, time(12, 0), time(13, 0)
        )
        assert len(result) == 2
        assert result[0] == (time(9, 0), time(12, 0))
        assert result[1] == (time(13, 0), time(17, 0))

    def test_subtract_range_start(self):
        """Test subtracting from the start of a range."""
        ranges = [(time(9, 0), time(17, 0))]
        result = RecurringAvailabilityService._subtract_range(
            ranges, time(9, 0), time(10, 0)
        )
        assert result == [(time(10, 0), time(17, 0))]

    def test_subtract_range_end(self):
        """Test subtracting from the end of a range."""
        ranges = [(time(9, 0), time(17, 0))]
        result = RecurringAvailabilityService._subtract_range(
            ranges, time(16, 0), time(17, 0)
        )
        assert result == [(time(9, 0), time(16, 0))]

    def test_subtract_range_complete_overlap(self):
        """Test subtracting a range that completely covers the available range."""
        ranges = [(time(9, 0), time(17, 0))]
        result = RecurringAvailabilityService._subtract_range(
            ranges, time(8, 0), time(18, 0)
        )
        assert result == []

    def test_merge_ranges_no_overlap(self):
        """Test merging non-overlapping ranges."""
        ranges = [(time(9, 0), time(12, 0)), (time(14, 0), time(17, 0))]
        result = RecurringAvailabilityService._merge_ranges(ranges)
        assert len(result) == 2

    def test_merge_ranges_overlapping(self):
        """Test merging overlapping ranges."""
        ranges = [(time(9, 0), time(13, 0)), (time(12, 0), time(17, 0))]
        result = RecurringAvailabilityService._merge_ranges(ranges)
        assert len(result) == 1
        assert result[0] == (time(9, 0), time(17, 0))

    def test_merge_ranges_adjacent(self):
        """Test merging adjacent ranges (touching endpoints)."""
        ranges = [(time(9, 0), time(12, 0)), (time(12, 0), time(17, 0))]
        result = RecurringAvailabilityService._merge_ranges(ranges)
        assert len(result) == 1
        assert result[0] == (time(9, 0), time(17, 0))

    def test_merge_ranges_empty(self):
        """Test merging empty list."""
        result = RecurringAvailabilityService._merge_ranges([])
        assert result == []

    def test_merge_ranges_unsorted(self):
        """Test merging unsorted ranges."""
        ranges = [(time(14, 0), time(17, 0)), (time(9, 0), time(12, 0))]
        result = RecurringAvailabilityService._merge_ranges(ranges)
        assert len(result) == 2
        assert result[0] == (time(9, 0), time(12, 0))
        assert result[1] == (time(14, 0), time(17, 0))


# =============================================================================
# ROUTE SCHEMA VALIDATION TESTS
# =============================================================================

class TestRouteSchemas:
    """Test Pydantic schema validation for route endpoints."""

    def test_weekly_schedule_update_schema(self):
        """Test WeeklyScheduleUpdate schema."""
        from routes.scheduler.recurring_availability import WeeklyScheduleUpdate, TimeBlock

        data = WeeklyScheduleUpdate(
            schedule={"0": [TimeBlock(start="09:00", end="17:00")]},
            timezone="America/Chicago",
        )
        assert data.timezone == "America/Chicago"
        assert len(data.schedule["0"]) == 1

    def test_exception_create_schema(self):
        """Test ExceptionCreate schema."""
        from routes.scheduler.recurring_availability import ExceptionCreate

        data = ExceptionCreate(
            date="2026-03-20",
            start_time="14:00",
            end_time="16:00",
            is_blocked=True,
            reason="Doctor",
        )
        assert data.date == "2026-03-20"
        assert data.is_blocked is True

    def test_exception_create_full_day(self):
        """Test ExceptionCreate schema with no times (full day)."""
        from routes.scheduler.recurring_availability import ExceptionCreate

        data = ExceptionCreate(
            date="2026-12-25",
            is_blocked=True,
            reason="Holiday",
        )
        assert data.start_time is None
        assert data.end_time is None

    def test_template_create_schema(self):
        """Test TemplateCreate schema."""
        from routes.scheduler.recurring_availability import TemplateCreate, TimeBlock

        data = TemplateCreate(
            name="Standard 9-5",
            description="Mon-Fri 9am-5pm",
            schedule={
                "0": [TimeBlock(start="09:00", end="12:00"), TimeBlock(start="13:00", end="17:00")],
            },
            is_default=True,
        )
        assert data.name == "Standard 9-5"
        assert data.is_default is True
        assert len(data.schedule["0"]) == 2
