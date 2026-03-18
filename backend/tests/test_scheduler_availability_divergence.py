"""
Integration tests for availability data source divergence.

Verifies that:
1. Working hours JSON and RecurringAvailability tables stay in sync
2. Divergence detection correctly identifies when sources differ
3. Slot generation uses the correct source (RecurringAvailability takes precedence)
4. Sync functions properly propagate changes between sources

The dual-source architecture is documented in:
- routes/scheduler/_helpers.py (lines 1066-1097, slot generator source precedence)
- services/availability_sync_service.py (divergence detection + sync utilities)
- database/models/recurring_availability.py (model docstring)
"""

import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import MagicMock, patch

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
from services.availability_sync_service import (
    check_availability_divergence,
    get_availability_source,
    sync_working_hours_to_recurring,
    sync_recurring_to_working_hours,
    _working_hours_to_schedule_dict,
    _recurring_rows_to_schedule_dict,
    _schedules_are_equivalent,
    _schedule_dict_to_working_hours,
    _describe_divergence,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def test_engine():
    """Create in-memory SQLite engine for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    RecurringAvailability.__table__.create(bind=engine, checkfirst=True)
    AvailabilityException.__table__.create(bind=engine, checkfirst=True)
    AvailabilityTemplate.__table__.create(bind=engine, checkfirst=True)

    # Create a minimal scheduler_configs table for the sync service
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduler_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                user_id INTEGER,
                team_id INTEGER,
                config_name TEXT NOT NULL DEFAULT 'default',
                description TEXT,
                timezone TEXT DEFAULT 'America/Chicago',
                default_duration_minutes INTEGER DEFAULT 30,
                min_duration_minutes INTEGER DEFAULT 15,
                max_duration_minutes INTEGER DEFAULT 120,
                buffer_before_minutes INTEGER DEFAULT 5,
                buffer_after_minutes INTEGER DEFAULT 5,
                min_notice_hours INTEGER DEFAULT 2,
                max_advance_days INTEGER DEFAULT 60,
                max_meetings_per_day INTEGER DEFAULT 8,
                max_consecutive_meetings INTEGER DEFAULT 3,
                lunch_break_start TEXT,
                lunch_break_end TEXT,
                enforce_lunch_break INTEGER DEFAULT 1,
                working_hours TEXT,
                preferred_meeting_modes TEXT,
                default_meeting_mode TEXT,
                zoom_enabled INTEGER DEFAULT 1,
                google_meet_enabled INTEGER DEFAULT 1,
                auto_create_meeting_link INTEGER DEFAULT 1,
                routing_strategy TEXT,
                accept_overflow_bookings INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        conn.commit()

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


# Helper constants
USER_ID = 10
ORG_ID = 1

# Standard Mon-Fri 9-5 JSON working hours
STANDARD_WORKING_HOURS_JSON = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
}

# Different hours (08:00-16:00) to test divergence
DIVERGENT_WORKING_HOURS_JSON = {
    "monday": {"start": "08:00", "end": "16:00", "enabled": True},
    "tuesday": {"start": "08:00", "end": "16:00", "enabled": True},
    "wednesday": {"start": "08:00", "end": "16:00", "enabled": True},
    "thursday": {"start": "08:00", "end": "16:00", "enabled": True},
    "friday": {"start": "08:00", "end": "16:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
}


def _create_scheduler_config(db_session, user_id, org_id, working_hours):
    """Insert a SchedulerConfig row with working_hours JSON via raw SQL."""
    import json
    from sqlalchemy import text
    wh_json = json.dumps(working_hours)
    db_session.execute(
        text("""
            INSERT INTO scheduler_configs (organization_id, user_id, config_name, working_hours)
            VALUES (:org_id, :user_id, 'default', :wh)
        """),
        {"org_id": org_id, "user_id": user_id, "wh": wh_json},
    )
    db_session.flush()


def _create_recurring_rows(db_session, user_id, org_id, schedule_dict, tz="America/Chicago"):
    """Create RecurringAvailability rows from a schedule dict."""
    for dow, blocks in schedule_dict.items():
        for block in blocks:
            start = datetime.strptime(block["start"], "%H:%M").time()
            end = datetime.strptime(block["end"], "%H:%M").time()
            row = RecurringAvailability(
                user_id=user_id,
                organization_id=org_id,
                day_of_week=int(dow),
                start_time=start,
                end_time=end,
                is_active=True,
                timezone=tz,
            )
            db_session.add(row)
    db_session.flush()


# =============================================================================
# TEST: AVAILABILITY SOURCE PRECEDENCE
# =============================================================================

class TestAvailabilitySourcePrecedence:
    """Test which availability source takes precedence in the slot generator."""

    def test_recurring_takes_precedence_over_json(self, db_session, service):
        """When RecurringAvailability exists, it should be used instead of JSON.

        This is the core precedence rule documented in _helpers.py line 1070-1073:
        'If a user has ANY active rows in the `recurring_availability` table,
        those structured patterns are used as the availability source.'
        """
        # Create JSON working hours with 9-5 schedule
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        # Create RecurringAvailability with DIFFERENT 8-4 schedule
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "08:00", "end": "16:00"}],  # Monday only
        })

        # Check which source the system reports
        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        assert source_info["source"] == "recurring"
        assert source_info["has_recurring"] is True
        assert source_info["has_json"] is True
        assert source_info["recurring_block_count"] == 1

    def test_json_used_when_no_recurring(self, db_session):
        """When no RecurringAvailability exists, working_hours JSON should be used."""
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        assert source_info["source"] == "json"
        assert source_info["has_recurring"] is False
        assert source_info["has_json"] is True
        assert source_info["json_day_count"] == 5  # Mon-Fri enabled

    def test_empty_sources_return_none(self, db_session):
        """When neither source has data, source should be 'none'."""
        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        assert source_info["source"] == "none"
        assert source_info["has_recurring"] is False
        assert source_info["has_json"] is False

    def test_only_recurring_no_json(self, db_session):
        """When only RecurringAvailability exists (no SchedulerConfig), recurring is active."""
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
        })

        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        assert source_info["source"] == "recurring"
        assert source_info["has_recurring"] is True
        assert source_info["has_json"] is False
        assert source_info["diverged"] is False  # Can't diverge with only one source

    def test_disabled_json_days_not_counted(self, db_session):
        """JSON with all days disabled should be treated as no JSON data."""
        all_disabled = {
            "monday": {"start": "09:00", "end": "17:00", "enabled": False},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": False},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": False},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": False},
            "friday": {"start": "09:00", "end": "17:00", "enabled": False},
            "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
            "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
        }
        _create_scheduler_config(db_session, USER_ID, ORG_ID, all_disabled)

        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        assert source_info["has_json"] is False
        assert source_info["json_day_count"] == 0
        assert source_info["source"] == "none"


# =============================================================================
# TEST: DIVERGENCE DETECTION
# =============================================================================

class TestAvailabilityDivergenceDetection:
    """Test detection of diverged availability sources."""

    def test_divergence_detected_when_both_exist_with_different_data(self, db_session):
        """Should detect divergence when RecurringAvailability and JSON have different hours."""
        # JSON: 9-5 schedule
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        # Recurring: 8-4 schedule (different from JSON)
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "08:00", "end": "16:00"}],  # Monday 8-4
            1: [{"start": "08:00", "end": "16:00"}],  # Tuesday 8-4
            2: [{"start": "08:00", "end": "16:00"}],  # Wednesday 8-4
            3: [{"start": "08:00", "end": "16:00"}],  # Thursday 8-4
            4: [{"start": "08:00", "end": "16:00"}],  # Friday 8-4
        })

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is True

        # Also verify via get_availability_source
        source_info = get_availability_source(db_session, USER_ID, ORG_ID)
        assert source_info["diverged"] is True
        assert len(source_info["differences"]) > 0

        # Each day should show up in differences
        diff_days = {d["day"] for d in source_info["differences"]}
        assert "monday" in diff_days

    def test_no_divergence_when_only_json(self, db_session):
        """Should not flag divergence when only JSON exists."""
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is False

    def test_no_divergence_when_only_recurring(self, db_session):
        """Should not flag divergence when only RecurringAvailability exists."""
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
        })

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is False

    def test_no_divergence_when_both_match(self, db_session):
        """Should not flag divergence when both sources have the same data."""
        # JSON: Mon-Fri 9-5
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        # Recurring: same Mon-Fri 9-5
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "09:00", "end": "17:00"}],
            2: [{"start": "09:00", "end": "17:00"}],
            3: [{"start": "09:00", "end": "17:00"}],
            4: [{"start": "09:00", "end": "17:00"}],
        })

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is False

    def test_divergence_with_extra_recurring_day(self, db_session):
        """Divergence when recurring has Saturday hours but JSON has Saturday disabled."""
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        # Recurring: Mon-Sat (Saturday enabled, but JSON has Saturday disabled)
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "09:00", "end": "17:00"}],
            2: [{"start": "09:00", "end": "17:00"}],
            3: [{"start": "09:00", "end": "17:00"}],
            4: [{"start": "09:00", "end": "17:00"}],
            5: [{"start": "10:00", "end": "14:00"}],  # Saturday
        })

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is True

        source_info = get_availability_source(db_session, USER_ID, ORG_ID)
        diff_days = {d["day"] for d in source_info["differences"]}
        assert "saturday" in diff_days

    def test_divergence_with_multi_block_vs_single_block(self, db_session):
        """Divergence when recurring has morning+afternoon blocks but JSON has single 9-5."""
        # JSON: single block 9-5
        _create_scheduler_config(db_session, USER_ID, ORG_ID, {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": False},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": False},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": False},
            "friday": {"start": "09:00", "end": "17:00", "enabled": False},
            "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
            "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
        })

        # Recurring: two blocks (morning 9-12, afternoon 13-17) on Monday
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [
                {"start": "09:00", "end": "12:00"},
                {"start": "13:00", "end": "17:00"},
            ],
        })

        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        # JSON block = [09:00-17:00], Recurring blocks = [09:00-12:00, 13:00-17:00]
        # These are structurally different even though they cover similar hours
        assert diverged is True


# =============================================================================
# TEST: SYNC FUNCTIONS
# =============================================================================

class TestAvailabilitySync:
    """Test synchronization between the two availability sources."""

    def test_sync_json_to_recurring_creates_rows(self, db_session):
        """sync_working_hours_to_recurring should create RecurringAvailability rows from JSON."""
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)

        result = sync_working_hours_to_recurring(db_session, USER_ID, ORG_ID)

        assert result["created"] == 5  # Mon-Fri
        assert result["skipped"] == 0
        assert result["source"] == "json_to_recurring"

        # Verify rows were created
        rows = (
            db_session.query(RecurringAvailability)
            .filter(
                RecurringAvailability.user_id == USER_ID,
                RecurringAvailability.organization_id == ORG_ID,
                RecurringAvailability.is_active == True,
            )
            .all()
        )
        assert len(rows) == 5

        # After sync, sources should match (no divergence)
        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is False

    def test_sync_recurring_to_json_updates_config(self, db_session):
        """sync_recurring_to_working_hours should update the JSON blob from RecurringAvailability."""
        # Create config with default (empty-ish) hours
        _create_scheduler_config(db_session, USER_ID, ORG_ID, {
            "monday": {"start": "09:00", "end": "17:00", "enabled": False},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": False},
        })

        # Create recurring rows with 8-4 schedule
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "08:00", "end": "16:00"}],
            1: [{"start": "08:00", "end": "16:00"}],
        })

        result = sync_recurring_to_working_hours(db_session, USER_ID, ORG_ID)

        assert result["updated"] is True
        assert result["reason"] == "synced"

        # Verify the JSON blob was updated
        new_wh = result["working_hours"]
        assert new_wh["monday"]["start"] == "08:00"
        assert new_wh["monday"]["end"] == "16:00"
        assert new_wh["monday"]["enabled"] is True
        assert new_wh["tuesday"]["start"] == "08:00"
        assert new_wh["tuesday"]["end"] == "16:00"
        assert new_wh["tuesday"]["enabled"] is True

    def test_sync_json_to_recurring_deactivates_old_rows(self, db_session):
        """sync_working_hours_to_recurring should deactivate existing rows first."""
        # Create existing recurring rows for Mon 10-18
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "10:00", "end": "18:00"}],
        })

        # Create JSON config with different hours (9-17)
        _create_scheduler_config(db_session, USER_ID, ORG_ID, {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
        })

        result = sync_working_hours_to_recurring(db_session, USER_ID, ORG_ID)

        assert result["deactivated"] == 1
        assert result["created"] == 1

        # Verify only the new row is active
        active_rows = (
            db_session.query(RecurringAvailability)
            .filter(
                RecurringAvailability.user_id == USER_ID,
                RecurringAvailability.organization_id == ORG_ID,
                RecurringAvailability.is_active == True,
            )
            .all()
        )
        assert len(active_rows) == 1
        assert active_rows[0].start_time == time(9, 0)
        assert active_rows[0].end_time == time(17, 0)

    def test_sync_no_config_returns_early(self, db_session):
        """sync_working_hours_to_recurring with no SchedulerConfig should return early."""
        result = sync_working_hours_to_recurring(db_session, USER_ID, ORG_ID)

        assert result["created"] == 0
        assert result["source"] == "no_config"

    def test_sync_recurring_to_json_already_in_sync(self, db_session):
        """sync_recurring_to_working_hours should detect already-synced state."""
        _create_scheduler_config(db_session, USER_ID, ORG_ID, {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
        })
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
        })

        result = sync_recurring_to_working_hours(db_session, USER_ID, ORG_ID)

        assert result["updated"] is False
        assert result["reason"] == "already_in_sync"


# =============================================================================
# TEST: INTERNAL COMPARISON HELPERS
# =============================================================================

class TestScheduleComparisonHelpers:
    """Test the internal schedule comparison and conversion functions."""

    def test_schedules_are_equivalent_same_data(self):
        """Identical schedule dicts should be equivalent."""
        sched = {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "09:00", "end": "17:00"}],
        }
        assert _schedules_are_equivalent(sched, sched) is True

    def test_schedules_are_equivalent_different_times(self):
        """Schedule dicts with different times should not be equivalent."""
        sched_a = {0: [{"start": "09:00", "end": "17:00"}]}
        sched_b = {0: [{"start": "08:00", "end": "16:00"}]}
        assert _schedules_are_equivalent(sched_a, sched_b) is False

    def test_schedules_are_equivalent_different_days(self):
        """Schedule dicts with different enabled days should not be equivalent."""
        sched_a = {0: [{"start": "09:00", "end": "17:00"}]}  # Monday only
        sched_b = {1: [{"start": "09:00", "end": "17:00"}]}  # Tuesday only
        assert _schedules_are_equivalent(sched_a, sched_b) is False

    def test_schedules_are_equivalent_multi_block(self):
        """Multi-block schedules with same blocks should be equivalent."""
        sched = {
            0: [
                {"start": "09:00", "end": "12:00"},
                {"start": "13:00", "end": "17:00"},
            ],
        }
        # Same blocks but in different order
        sched_reordered = {
            0: [
                {"start": "13:00", "end": "17:00"},
                {"start": "09:00", "end": "12:00"},
            ],
        }
        assert _schedules_are_equivalent(sched, sched_reordered) is True

    def test_working_hours_to_schedule_dict_filters_disabled(self):
        """_working_hours_to_schedule_dict should skip disabled days."""
        wh = {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
        }
        result = _working_hours_to_schedule_dict(wh)

        assert 0 in result  # Monday
        assert 5 not in result  # Saturday (disabled)

    def test_schedule_dict_to_working_hours_roundtrip(self):
        """Converting schedule dict -> working hours -> schedule dict should preserve data."""
        original = {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "10:00", "end": "18:00"}],
        }
        working_hours = _schedule_dict_to_working_hours(original)
        roundtripped = _working_hours_to_schedule_dict(working_hours)

        assert _schedules_are_equivalent(original, roundtripped) is True

    def test_describe_divergence_shows_per_day_diffs(self):
        """_describe_divergence should list each day that differs."""
        json_sched = {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "09:00", "end": "17:00"}],
        }
        recurring_sched = {
            0: [{"start": "08:00", "end": "16:00"}],  # Different
            1: [{"start": "09:00", "end": "17:00"}],  # Same
        }
        diffs = _describe_divergence(json_sched, recurring_sched)

        assert len(diffs) == 1
        assert diffs[0]["day"] == "monday"
        assert diffs[0]["json_blocks"] == [{"start": "09:00", "end": "17:00"}]
        assert diffs[0]["recurring_blocks"] == [{"start": "08:00", "end": "16:00"}]


# =============================================================================
# TEST: SLOT GENERATION SOURCE SELECTION
# =============================================================================

class TestSlotGenerationSourceSelection:
    """Test that _generate_available_slots uses the correct source.

    These tests mock the slot generator's internal source selection to verify
    the precedence logic without requiring the full scheduler infrastructure.
    """

    def test_recurring_schedule_provides_effective_blocks(self, db_session, service):
        """RecurringAvailabilityService.get_effective_schedule should provide blocks
        when RecurringAvailability rows exist."""
        # Set up recurring schedule: Monday 9-12, 13-17
        service.set_weekly_schedule(
            user_id=USER_ID, org_id=ORG_ID,
            schedule={0: [
                {"start": "09:00", "end": "12:00"},
                {"start": "13:00", "end": "17:00"},
            ]},
        )
        db_session.flush()

        # Monday 2026-03-16
        effective = service.get_effective_schedule(USER_ID, ORG_ID, date(2026, 3, 16))

        assert len(effective) == 2
        assert effective[0]["start"] == "09:00"
        assert effective[0]["end"] == "12:00"
        assert effective[1]["start"] == "13:00"
        assert effective[1]["end"] == "17:00"

    def test_no_recurring_returns_empty_effective(self, db_session, service):
        """When no RecurringAvailability rows exist, get_effective_schedule returns empty."""
        effective = service.get_effective_schedule(USER_ID, ORG_ID, date(2026, 3, 16))
        assert effective == []

    def test_slots_from_recurring_skip_gaps(self, db_session, service):
        """Slots generated from recurring availability should skip gaps between blocks.

        This verifies that the lunch break between blocks (12:00-13:00) is
        respected when using RecurringAvailability as the source."""
        service.set_weekly_schedule(
            user_id=USER_ID, org_id=ORG_ID,
            schedule={0: [
                {"start": "11:00", "end": "12:00"},  # 1 hour morning
                {"start": "13:00", "end": "14:00"},  # 1 hour afternoon
            ]},
        )
        db_session.flush()

        slots = service.get_available_slots(
            user_id=USER_ID, org_id=ORG_ID,
            start_date=date(2026, 3, 16),
            end_date=date(2026, 3, 16),
            duration_minutes=30,
        )

        # 2 slots in morning block (11:00, 11:30) + 2 in afternoon (13:00, 13:30)
        assert len(slots) == 4

        slot_starts = [s["start"] for s in slots]
        assert "11:00" in slot_starts
        assert "11:30" in slot_starts
        assert "13:00" in slot_starts
        assert "13:30" in slot_starts

        # No slots during the 12:00-13:00 gap
        assert "12:00" not in slot_starts
        assert "12:30" not in slot_starts


# =============================================================================
# TEST: SETTINGS UPDATE DIVERGENCE WARNINGS
# =============================================================================

class TestAvailabilitySettingsUpdate:
    """Test that settings updates handle the dual-source correctly."""

    def test_json_update_creates_divergence_when_recurring_exists(self, db_session):
        """Updating working_hours JSON while RecurringAvailability is active
        should be detectable as divergence (unless sync is performed)."""
        # Create recurring rows first (standard 9-5)
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "09:00", "end": "17:00"}],
            1: [{"start": "09:00", "end": "17:00"}],
        })

        # Simulate a settings UI save with different hours (8-4)
        _create_scheduler_config(db_session, USER_ID, ORG_ID, {
            "monday": {"start": "08:00", "end": "16:00", "enabled": True},
            "tuesday": {"start": "08:00", "end": "16:00", "enabled": True},
        })

        # The sources have diverged
        diverged = check_availability_divergence(db_session, USER_ID, ORG_ID)
        assert diverged is True

        # The slot generator would still use recurring (09:00-17:00), not the
        # JSON (08:00-16:00), meaning the UI shows stale data
        source_info = get_availability_source(db_session, USER_ID, ORG_ID)
        assert source_info["source"] == "recurring"

    def test_settings_endpoint_returns_divergence_warning(self, db_session):
        """get_availability_source should provide enough info for a UI warning."""
        # Set up diverged state
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "07:00", "end": "15:00"}],  # Different from JSON
        })

        source_info = get_availability_source(db_session, USER_ID, ORG_ID)

        # UI should be able to show a warning based on these fields
        assert source_info["diverged"] is True
        assert source_info["source"] == "recurring"  # Tell user which is actually active
        assert len(source_info["differences"]) > 0

        # The differences should identify Monday as diverged
        monday_diff = next(
            (d for d in source_info["differences"] if d["day"] == "monday"),
            None,
        )
        assert monday_diff is not None
        assert monday_diff["json_blocks"] == [{"start": "09:00", "end": "17:00"}]
        assert monday_diff["recurring_blocks"] == [{"start": "07:00", "end": "15:00"}]

    def test_sync_resolves_divergence(self, db_session):
        """After syncing recurring -> JSON, divergence should be resolved."""
        # Create diverged state
        _create_scheduler_config(db_session, USER_ID, ORG_ID, STANDARD_WORKING_HOURS_JSON)
        _create_recurring_rows(db_session, USER_ID, ORG_ID, {
            0: [{"start": "08:00", "end": "16:00"}],
        })

        # Confirm divergence exists
        assert check_availability_divergence(db_session, USER_ID, ORG_ID) is True

        # Sync recurring -> JSON to resolve
        sync_recurring_to_working_hours(db_session, USER_ID, ORG_ID)

        # Divergence should be resolved
        assert check_availability_divergence(db_session, USER_ID, ORG_ID) is False
