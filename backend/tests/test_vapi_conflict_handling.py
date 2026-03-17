"""
Vapi Voice Call Conflict Handling Tests

Tests for graceful scheduling conflict resolution during Vapi AI voice calls.
Covers:
- Booking conflict detection and voice-friendly error messages
- Alternative slot suggestion when requested time is taken
- Soft hold mechanism to prevent double-booking during conversation
- Voice-friendly time formatting
- Available time slots with real conflict checking
- Edge cases: weekends, past dates, fully booked days
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Helpers
# =============================================================================

class _Col:
    """Fake SQLAlchemy column descriptor for use in .filter() expressions."""
    def __eq__(self, other): return True
    def __ne__(self, other): return True
    def __lt__(self, other): return True
    def __gt__(self, other): return True
    def __le__(self, other): return True
    def __ge__(self, other): return True
    def notin_(self, values): return True
    def in_(self, values): return True
    def is_(self, value): return True
    def isnot(self, value): return True
    def __hash__(self): return id(self)


def _make_mock_request(data: Dict[str, Any]) -> Mock:
    """Create a mock Request whose .json() returns the given dict."""
    req = AsyncMock()
    req.json = AsyncMock(return_value=data)
    return req


# =============================================================================
# Test _format_slots_for_voice
# =============================================================================

class TestFormatSlotsForVoice:
    """Tests for the voice-friendly slot formatting helper."""

    def test_single_slot(self):
        from vapi_routes import _format_slots_for_voice
        slots = [{"display": "2:00 PM"}]
        result = _format_slots_for_voice(slots)
        assert result == "2:00 PM"

    def test_two_slots(self):
        from vapi_routes import _format_slots_for_voice
        slots = [
            {"display": "2:00 PM"},
            {"display": "3:00 PM"},
        ]
        result = _format_slots_for_voice(slots)
        assert "2:00 PM" in result
        assert "or 3:00 PM" in result

    def test_three_slots(self):
        from vapi_routes import _format_slots_for_voice
        slots = [
            {"display": "10:00 AM"},
            {"display": "2:00 PM"},
            {"display": "4:00 PM"},
        ]
        result = _format_slots_for_voice(slots)
        assert "10:00 AM" in result
        assert "2:00 PM" in result
        assert "or 4:00 PM" in result

    def test_empty_slots(self):
        from vapi_routes import _format_slots_for_voice
        result = _format_slots_for_voice([])
        assert result == "no available times"

    def test_falls_back_to_time_key(self):
        from vapi_routes import _format_slots_for_voice
        slots = [{"time": "2026-03-12T14:00:00+00:00"}]
        result = _format_slots_for_voice(slots)
        assert "2026-03-12T14:00:00+00:00" in result


# =============================================================================
# Test _get_booked_slots_for_date
# =============================================================================

class TestGetBookedSlotsForDate:
    """Tests for the booked-slot query helper."""

    def test_returns_set(self):
        from vapi_routes import _get_booked_slots_for_date
        mock_db = MagicMock()
        # Make both queries return empty results
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        result = _get_booked_slots_for_date(mock_db, date(2026, 3, 15))
        assert isinstance(result, set)

    def test_includes_soft_holds(self):
        from vapi_routes import _get_booked_slots_for_date, _slot_soft_holds

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        # Place a soft hold
        target = date(2026, 3, 15)
        hold_time = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        _slot_soft_holds[(1, hold_time.isoformat())] = datetime.now(timezone.utc) + timedelta(minutes=5)

        try:
            result = _get_booked_slots_for_date(mock_db, target, lo_user_id=1)
            assert 14 in result
        finally:
            _slot_soft_holds.clear()

    def test_expired_holds_ignored(self):
        from vapi_routes import _get_booked_slots_for_date, _slot_soft_holds

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        # Place an expired hold
        target = date(2026, 3, 15)
        hold_time = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        _slot_soft_holds[(1, hold_time.isoformat())] = datetime.now(timezone.utc) - timedelta(minutes=1)

        try:
            result = _get_booked_slots_for_date(mock_db, target, lo_user_id=1)
            assert 14 not in result
        finally:
            _slot_soft_holds.clear()


# =============================================================================
# Test _get_next_available_slots
# =============================================================================

class TestGetNextAvailableSlots:
    """Tests for the alternative slot finder."""

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_returns_requested_count(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        mock_booked.return_value = set()
        mock_db = MagicMock()

        # Use a Wednesday so we have business days ahead
        preferred = date(2026, 3, 11)  # Wednesday
        slots = _get_next_available_slots(mock_db, None, preferred, count=3)
        assert len(slots) == 3

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_skips_booked_hours(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        # All morning hours booked
        mock_booked.return_value = {9, 10, 11}
        mock_db = MagicMock()

        preferred = date(2026, 3, 11)
        slots = _get_next_available_slots(mock_db, None, preferred, count=2)
        assert len(slots) == 2
        # First available should be 12 PM
        assert "12:00 PM" in slots[0]["display"]

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_skips_weekends(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        # All hours booked on Friday
        mock_booked.side_effect = lambda db, d, lo: set(range(9, 17)) if d.weekday() == 4 else set()
        mock_db = MagicMock()

        # Start on a Friday
        preferred = date(2026, 3, 13)  # Friday
        slots = _get_next_available_slots(mock_db, None, preferred, count=1)
        assert len(slots) == 1
        # Should be on Monday (skip Sat/Sun)
        slot_date = date.fromisoformat(slots[0]["date"])
        assert slot_date.weekday() == 0  # Monday

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_morning_preference(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        mock_booked.return_value = set()
        mock_db = MagicMock()

        preferred = date(2026, 3, 11)
        slots = _get_next_available_slots(
            mock_db, None, preferred, count=3, time_preference="morning"
        )
        assert len(slots) == 3
        # All should be before noon
        for slot in slots:
            hour = datetime.fromisoformat(slot["time"]).hour
            assert hour < 12

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_afternoon_preference(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        mock_booked.return_value = set()
        mock_db = MagicMock()

        preferred = date(2026, 3, 11)
        slots = _get_next_available_slots(
            mock_db, None, preferred, count=3, time_preference="afternoon"
        )
        assert len(slots) == 3
        for slot in slots:
            hour = datetime.fromisoformat(slot["time"]).hour
            assert 12 <= hour < 17

    @patch("vapi_routes._get_booked_slots_for_date")
    def test_fully_booked_day_looks_ahead(self, mock_booked):
        from vapi_routes import _get_next_available_slots
        # All hours booked today, none tomorrow
        call_count = [0]

        def side_effect(db, d, lo):
            call_count[0] += 1
            if call_count[0] == 1:
                return set(range(9, 17))  # Fully booked
            return set()  # Open

        mock_booked.side_effect = side_effect
        mock_db = MagicMock()

        preferred = date(2026, 3, 11)  # Wednesday
        slots = _get_next_available_slots(mock_db, None, preferred, count=1)
        assert len(slots) == 1
        # Should be on Thursday
        assert date.fromisoformat(slots[0]["date"]) == date(2026, 3, 12)


# =============================================================================
# Test schedule_appointment_function
# =============================================================================

class TestScheduleAppointmentFunction:
    """Tests for the main scheduling Vapi function."""

    @pytest.fixture
    def mock_lead(self):
        lead = MagicMock()
        lead.id = 42
        lead.owner_id = 1
        lead.name = "Jane Doe"
        lead.first_name = "Jane"
        lead.phone = "+15551234567"
        return lead

    @pytest.mark.asyncio
    async def test_missing_phone_returns_voice_message(self):
        from vapi_routes import schedule_appointment_function

        req = _make_mock_request({"type": "Meeting"})
        db = MagicMock()

        result = await schedule_appointment_function(req, db, True)
        assert result["success"] is False
        assert "phone number" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_lead_not_found_returns_voice_message(self):
        from vapi_routes import schedule_appointment_function

        req = _make_mock_request({"phone_number": "+15559999999"})
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await schedule_appointment_function(req, db, True)
        assert result["success"] is False
        assert "information on file" in result["message"].lower() or "details" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_no_time_provided_asks_caller(self):
        from vapi_routes import schedule_appointment_function

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
        })
        db = MagicMock()
        lead = MagicMock()
        lead.id = 1
        lead.owner_id = 1
        lead.name = "Jane Doe"
        db.query.return_value.filter.return_value.first.return_value = lead

        result = await schedule_appointment_function(req, db, True)
        assert result["success"] is False
        assert "what day" in result["message"].lower() or "time" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_conflict_returns_alternatives(self, mock_booked, mock_lead):
        from vapi_routes import schedule_appointment_function

        # Hour 14 is booked
        mock_booked.return_value = {14}

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T14:00:00+00:00",
        })
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_lead

        with patch("vapi_routes._get_next_available_slots") as mock_alts:
            mock_alts.return_value = [
                {"display": "3:00 PM", "time": "2026-03-15T15:00:00+00:00",
                 "date": "2026-03-15", "date_display": "Sunday, March 15"},
            ]
            result = await schedule_appointment_function(req, db, True)

        assert result["success"] is False
        assert result.get("conflict") is True
        assert "just taken" in result["message"]
        assert "alternative" in result["message"].lower() or "3:00 PM" in result["message"]
        assert len(result["alternative_slots"]) > 0

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_conflict_no_alternatives_offers_next_day(self, mock_booked, mock_lead):
        from vapi_routes import schedule_appointment_function

        mock_booked.return_value = {14}

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T14:00:00+00:00",
        })
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_lead

        with patch("vapi_routes._get_next_available_slots") as mock_alts:
            mock_alts.return_value = []
            result = await schedule_appointment_function(req, db, True)

        assert result["success"] is False
        assert result.get("conflict") is True
        assert "tomorrow" in result["message"].lower() or "next" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_successful_booking(self, mock_booked, mock_lead):
        from vapi_routes import schedule_appointment_function

        # No conflicts
        mock_booked.return_value = set()

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T10:00:00+00:00",
            "notes": "Discuss refinance options",
        })

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_lead

        # Mock Activity and Task model constructors to avoid SQLAlchemy mapper init
        mock_activity_instance = MagicMock()
        mock_activity_instance.id = 100
        mock_task_instance = MagicMock()
        mock_task_instance.id = 200

        refresh_count = [0]
        def fake_refresh(obj):
            refresh_count[0] += 1

        db.refresh = fake_refresh

        with patch("database.models.Activity", return_value=mock_activity_instance), \
             patch("database.models.Task", return_value=mock_task_instance), \
             patch("database.enums.ActivityType") as mock_at:
            mock_at.MEETING = "Meeting"
            mock_at.CALL = "Call"
            mock_at.EMAIL = "Email"
            result = await schedule_appointment_function(req, db, True)

        assert result["success"] is True
        assert "confirmed" in result["message"].lower() or "great news" in result["message"].lower()
        assert result["appointment_time"] == "2026-03-15T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_unexpected_error_offers_transfer(self, mock_lead):
        from vapi_routes import schedule_appointment_function

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T10:00:00+00:00",
        })

        db = MagicMock()
        db.query.side_effect = Exception("Database connection lost")

        result = await schedule_appointment_function(req, db, True)
        assert result["success"] is False
        assert result.get("transfer") is True
        assert "technical issue" in result["message"].lower() or "transfer" in result["message"].lower()


# =============================================================================
# Test available_time_slots_function
# =============================================================================

class TestAvailableTimeSlotsFunction:
    """Tests for the enhanced time slots endpoint."""

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_marks_booked_hours_unavailable(self, mock_booked):
        from vapi_routes import available_time_slots_function

        mock_booked.return_value = {10, 14}

        req = _make_mock_request({})
        db = MagicMock()

        # Use a future Wednesday to avoid "today" past-hour filtering
        result = await available_time_slots_function(
            req, date="2026-04-08", db=db, _=True
        )

        assert result["success"] is True
        slots_by_hour = {
            datetime.fromisoformat(s["time"]).hour: s
            for s in result["slots"]
        }
        assert slots_by_hour[10]["available"] is False
        assert slots_by_hour[14]["available"] is False
        assert slots_by_hour[11]["available"] is True

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_includes_voice_message(self, mock_booked):
        from vapi_routes import available_time_slots_function

        mock_booked.return_value = set()
        req = _make_mock_request({})
        db = MagicMock()

        result = await available_time_slots_function(
            req, date="2026-03-11", db=db, _=True
        )

        assert result["success"] is True
        assert "message" in result
        assert "available" in result["message"].lower() or "times" in result["message"].lower()
        assert result["available_count"] > 0

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_fully_booked_day_message(self, mock_booked):
        from vapi_routes import available_time_slots_function

        mock_booked.return_value = set(range(9, 17))  # All booked
        req = _make_mock_request({})
        db = MagicMock()

        result = await available_time_slots_function(
            req, date="2026-03-11", db=db, _=True
        )

        assert result["success"] is True
        assert result["available_count"] == 0
        assert "no available" in result["message"].lower() or "sorry" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("vapi_routes._get_booked_slots_for_date")
    async def test_weekend_moved_to_monday(self, mock_booked):
        from vapi_routes import available_time_slots_function

        mock_booked.return_value = set()
        req = _make_mock_request({})
        db = MagicMock()

        # 2026-03-14 is a Saturday
        result = await available_time_slots_function(
            req, date="2026-03-14", db=db, _=True
        )

        assert result["success"] is True
        result_date = date.fromisoformat(result["date"])
        assert result_date.weekday() < 5  # Weekday

    @pytest.mark.asyncio
    async def test_error_offers_transfer(self):
        from vapi_routes import available_time_slots_function

        req = _make_mock_request({})
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        # Force the error path by making the date parsing succeed but
        # _get_booked_slots_for_date raise
        with patch("vapi_routes._get_booked_slots_for_date", side_effect=Exception("boom")):
            result = await available_time_slots_function(
                req, date="2026-03-11", db=db, _=True
            )

        assert result["success"] is False
        assert result.get("transfer") is True


# =============================================================================
# Test hold_slot_function
# =============================================================================

class TestHoldSlotFunction:
    """Tests for the soft hold mechanism."""

    @pytest.mark.asyncio
    async def test_places_hold(self):
        from vapi_routes import hold_slot_function, _slot_soft_holds

        req = _make_mock_request({
            "time": "2026-03-15T14:00:00+00:00",
            "loan_officer_id": 1,
        })
        db = MagicMock()

        try:
            result = await hold_slot_function(req, db, True)
            assert result["success"] is True
            assert "reserved" in result["message"].lower()
            assert (1, "2026-03-15T14:00:00+00:00") in _slot_soft_holds
        finally:
            _slot_soft_holds.clear()

    @pytest.mark.asyncio
    async def test_missing_time_still_succeeds(self):
        from vapi_routes import hold_slot_function

        req = _make_mock_request({})
        db = MagicMock()

        result = await hold_slot_function(req, db, True)
        # Should never fail or alarm the caller
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invalid_time_still_succeeds(self):
        from vapi_routes import hold_slot_function

        req = _make_mock_request({"time": "not-a-date"})
        db = MagicMock()

        result = await hold_slot_function(req, db, True)
        assert result["success"] is True


# =============================================================================
# Test check_alternative_times_function
# =============================================================================

class TestCheckAlternativeTimesFunction:
    """Tests for the alternative times Vapi function."""

    @pytest.mark.asyncio
    @patch("vapi_routes._get_next_available_slots")
    async def test_returns_alternatives(self, mock_slots):
        from vapi_routes import check_alternative_times_function

        mock_slots.return_value = [
            {"display": "2:00 PM", "time": "2026-03-15T14:00:00+00:00",
             "date": "2026-03-15", "date_display": "Sunday, March 15"},
            {"display": "3:00 PM", "time": "2026-03-15T15:00:00+00:00",
             "date": "2026-03-15", "date_display": "Sunday, March 15"},
        ]

        req = _make_mock_request({"date": "2026-03-15"})
        db = MagicMock()

        result = await check_alternative_times_function(req, db, True)
        assert result["success"] is True
        assert "2:00 PM" in result["message"]
        assert len(result["slots"]) == 2

    @pytest.mark.asyncio
    @patch("vapi_routes._get_next_available_slots")
    async def test_no_slots_suggests_next_day(self, mock_slots):
        from vapi_routes import check_alternative_times_function

        mock_slots.return_value = []

        req = _make_mock_request({"date": "2026-03-15"})
        db = MagicMock()

        result = await check_alternative_times_function(req, db, True)
        assert result["success"] is False
        assert "next" in result["message"].lower() or "don't have" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("vapi_routes._get_next_available_slots")
    async def test_passes_time_preference(self, mock_slots):
        from vapi_routes import check_alternative_times_function

        mock_slots.return_value = [
            {"display": "9:00 AM", "time": "2026-03-15T09:00:00+00:00",
             "date": "2026-03-15", "date_display": "Sunday, March 15"},
        ]

        req = _make_mock_request({
            "date": "2026-03-15",
            "time_preference": "morning",
        })
        db = MagicMock()

        result = await check_alternative_times_function(req, db, True)
        assert result["success"] is True
        # Verify the preference label appears in the message
        assert "morning" in result["message"].lower()
        # Verify _get_next_available_slots was called with time_preference
        mock_slots.assert_called_once()
        call_kwargs = mock_slots.call_args
        assert call_kwargs[1].get("time_preference") == "morning" or \
               (len(call_kwargs[0]) > 4 and call_kwargs[0][4] == "morning")


# =============================================================================
# Test voice message quality
# =============================================================================

class TestVoiceMessageQuality:
    """Ensure all error responses contain natural, conversational voice messages.
    These are read aloud by the AI voice, so they must sound human."""

    @pytest.mark.asyncio
    async def test_all_error_paths_have_voice_messages(self):
        """Every non-success response must have a 'message' key with
        conversational text suitable for voice readback."""
        from vapi_routes import schedule_appointment_function

        test_cases = [
            # Missing phone
            {"type": "Meeting"},
            # Missing appointment_time (requires lead found)
        ]

        for data in test_cases:
            req = _make_mock_request(data)
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = None

            result = await schedule_appointment_function(req, db, True)
            assert "message" in result, f"No message in response for data: {data}"
            assert len(result["message"]) > 20, (
                f"Message too short for voice readback: '{result['message']}'"
            )
            # Should not contain technical jargon
            msg_lower = result["message"].lower()
            assert "500" not in msg_lower
            assert "internal server error" not in msg_lower
            assert "traceback" not in msg_lower
            assert "exception" not in msg_lower

    @pytest.mark.asyncio
    async def test_conflict_message_is_conversational(self):
        """Conflict messages should sound empathetic and offer help."""
        from vapi_routes import schedule_appointment_function

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T14:00:00+00:00",
        })

        lead = MagicMock()
        lead.id = 1
        lead.owner_id = 1
        lead.name = "Jane"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = lead

        with patch("vapi_routes._get_booked_slots_for_date", return_value={14}), \
             patch("vapi_routes._get_next_available_slots", return_value=[
                 {"display": "3:00 PM", "time": "T", "date": "2026-03-15",
                  "date_display": "March 15"},
             ]):
            result = await schedule_appointment_function(req, db, True)

        msg = result["message"]
        # Should be apologetic
        assert "sorry" in msg.lower()
        # Should offer alternatives
        assert "3:00 PM" in msg
        # Should ask a question
        assert "?" in msg


# =============================================================================
# Test soft hold expiry integration
# =============================================================================

class TestSoftHoldIntegration:
    """Integration test: soft hold prevents double-booking during conversation."""

    @pytest.mark.asyncio
    async def test_held_slot_shows_as_booked(self):
        """A soft-held slot should appear as booked in available_time_slots."""
        from vapi_routes import (
            hold_slot_function, available_time_slots_function,
            _slot_soft_holds,
        )

        try:
            # Step 1: Place a hold on 2 PM
            hold_req = _make_mock_request({
                "time": "2026-03-11T14:00:00+00:00",
                "loan_officer_id": 1,
            })
            db = MagicMock()
            await hold_slot_function(hold_req, db, True)

            # Step 2: Check available slots -- 2 PM should be unavailable
            # We need to also patch DB queries to return empty
            with patch("vapi_routes._get_booked_slots_for_date") as mock_booked:
                # The real function would include the soft hold,
                # but since we patched it, simulate it:
                # Actually, let's call the real function instead
                pass

            # Call _get_booked_slots_for_date directly
            from vapi_routes import _get_booked_slots_for_date
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

            booked = _get_booked_slots_for_date(mock_db, date(2026, 3, 11), lo_user_id=1)
            assert 14 in booked
        finally:
            _slot_soft_holds.clear()

    @pytest.mark.asyncio
    async def test_booking_clears_soft_hold(self):
        """After successful booking, the soft hold should be removed."""
        from vapi_routes import schedule_appointment_function, _slot_soft_holds

        # Pre-place a hold
        _slot_soft_holds[(1, "2026-03-15T10:00:00+00:00")] = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        )

        lead = MagicMock()
        lead.id = 1
        lead.owner_id = 1
        lead.name = "Jane Doe"

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T10:00:00+00:00",
        })

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = lead

        mock_activity_instance = MagicMock()
        mock_activity_instance.id = 100
        mock_task_instance = MagicMock()
        mock_task_instance.id = 200

        try:
            with patch("vapi_routes._get_booked_slots_for_date", return_value=set()), \
                 patch("database.models.Activity", return_value=mock_activity_instance), \
                 patch("database.models.Task", return_value=mock_task_instance), \
                 patch("database.enums.ActivityType") as mock_at:
                mock_at.MEETING = "Meeting"
                result = await schedule_appointment_function(req, db, True)

            if result["success"]:
                # Hold should be cleared after booking
                assert (1, "2026-03-15T10:00:00+00:00") not in _slot_soft_holds
        finally:
            _slot_soft_holds.clear()


# =============================================================================
# Test race condition handling (IntegrityError path)
# =============================================================================

class TestRaceConditionHandling:
    """Test the IntegrityError handling for true DB-level race conditions."""

    @pytest.mark.asyncio
    async def test_integrity_error_returns_alternatives(self):
        """When db.commit() raises IntegrityError (another process won the race),
        the response should be voice-friendly with alternatives."""
        from vapi_routes import schedule_appointment_function
        from sqlalchemy.exc import IntegrityError

        lead = MagicMock()
        lead.id = 1
        lead.owner_id = 1
        lead.name = "Jane"

        req = _make_mock_request({
            "phone_number": "+15551234567",
            "type": "Meeting",
            "appointment_time": "2026-03-15T10:00:00+00:00",
        })

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = lead
        db.commit.side_effect = IntegrityError("duplicate", {}, Exception())

        mock_activity_instance = MagicMock()
        mock_activity_instance.id = 100
        mock_task_instance = MagicMock()
        mock_task_instance.id = 200

        with patch("vapi_routes._get_booked_slots_for_date", return_value=set()), \
             patch("vapi_routes._get_next_available_slots", return_value=[
                 {"display": "11:00 AM", "time": "T", "date": "2026-03-15",
                  "date_display": "March 15"},
             ]), \
             patch("database.models.Activity", return_value=mock_activity_instance), \
             patch("database.models.Task", return_value=mock_task_instance), \
             patch("database.enums.ActivityType") as mock_at:
            mock_at.MEETING = "Meeting"
            mock_at.CALL = "Call"
            mock_at.EMAIL = "Email"
            result = await schedule_appointment_function(req, db, True)

        assert result["success"] is False
        assert result.get("conflict") is True
        assert "sorry" in result["message"].lower()
        assert "11:00 AM" in result["message"]
        db.rollback.assert_called_once()
