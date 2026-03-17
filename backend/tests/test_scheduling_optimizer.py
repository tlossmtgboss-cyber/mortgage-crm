"""
Tests for Scheduling Optimizer - AI-Powered Scheduling Decision Engine

Tests the SchedulingOptimizer service with mock historical data, covering:
1. Hourly show rate calculation
2. Day-of-week show rate calculation
3. Slot scoring algorithm
4. Optimal slot ranking
5. No-show risk prediction by attendee email
6. Org-level booking insights
7. Best times for next week
8. Edge cases (no data, sparse data, past dates)
"""

import os
import sys
import math
import pytest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock
from collections import namedtuple

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.scheduling_optimizer import (
    SchedulingOptimizer,
    _wilson_lower_bound,
    _pct,
    _safe_float,
    _get_no_show_recommendation,
    _build_insights_recommendation,
)


# ---------------------------------------------------------------------------
# Helpers for building mock DB result rows
# ---------------------------------------------------------------------------

def _make_row(**kwargs):
    """Create a mock row object with named attributes (simulates SQLAlchemy Row)."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


def _make_mock_db(execute_results=None):
    """
    Create a mock DB session where db.execute(text(...), params).fetchall()
    returns execute_results (a list of lists of rows), consumed in order.

    Each call to .execute().fetchall() pops the first item from the list.
    Calls to .execute().fetchone() return the first element of the popped list.
    """
    db = MagicMock()
    results = list(execute_results or [])

    def _execute_side_effect(*args, **kwargs):
        mock_result = MagicMock()
        if results:
            rows = results.pop(0)
        else:
            rows = []
        mock_result.fetchall.return_value = rows
        mock_result.fetchone.return_value = rows[0] if rows else None
        return mock_result

    db.execute.side_effect = _execute_side_effect
    return db


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

class TestWilsonLowerBound:
    def test_zero_total_returns_zero(self):
        assert _wilson_lower_bound(0, 0) == 0.0

    def test_perfect_small_sample_penalized(self):
        """1/1 should score lower than 95/100."""
        score_1_of_1 = _wilson_lower_bound(1, 1)
        score_95_of_100 = _wilson_lower_bound(95, 100)
        assert score_95_of_100 > score_1_of_1

    def test_returns_float_between_zero_and_one(self):
        for pos, total in [(5, 10), (0, 10), (10, 10), (50, 100)]:
            score = _wilson_lower_bound(pos, total)
            assert 0.0 <= score <= 1.0, f"Score {score} out of bounds for {pos}/{total}"

    def test_higher_ratio_higher_score_same_sample(self):
        """90% should score higher than 50% at same sample size."""
        assert _wilson_lower_bound(90, 100) > _wilson_lower_bound(50, 100)


class TestHelpers:
    def test_pct_normal(self):
        assert _pct(3, 10) == 30.0

    def test_pct_zero_denominator(self):
        assert _pct(5, 0) == 0.0

    def test_safe_float_none(self):
        assert _safe_float(None) == 0.0

    def test_safe_float_valid(self):
        assert _safe_float(3.14) == 3.14

    def test_safe_float_string(self):
        assert _safe_float("not_a_number", default=1.0) == 1.0


# ---------------------------------------------------------------------------
# Hourly show rates
# ---------------------------------------------------------------------------

class TestHourlyShowRates:
    def test_returns_rates_by_hour(self):
        rows = [
            _make_row(hour=9, total=20, completed=18, no_shows=2),
            _make_row(hour=10, total=15, completed=12, no_shows=3),
            _make_row(hour=14, total=10, completed=5, no_shows=5),
        ]
        db = _make_mock_db([[rows[0], rows[1], rows[2]]])

        result = SchedulingOptimizer.get_hourly_show_rates(db, org_id=1)

        assert 9 in result
        assert 10 in result
        assert 14 in result
        assert result[9]["total"] == 20
        assert result[9]["completed"] == 18
        assert result[9]["show_rate"] == 0.9
        assert result[14]["show_rate"] == 0.5

    def test_empty_data_returns_empty(self):
        db = _make_mock_db([[]])
        result = SchedulingOptimizer.get_hourly_show_rates(db, org_id=1)
        assert result == {}

    def test_with_user_filter(self):
        rows = [_make_row(hour=10, total=5, completed=4, no_shows=1)]
        db = _make_mock_db([rows])
        result = SchedulingOptimizer.get_hourly_show_rates(db, org_id=1, user_id=42)

        # Verify user_id was included in the query
        call_args = db.execute.call_args
        query_text = str(call_args[0][0].text)
        assert "assigned_user_id" in query_text
        assert result[10]["total"] == 5


# ---------------------------------------------------------------------------
# Day-of-week show rates
# ---------------------------------------------------------------------------

class TestDOWShowRates:
    def test_returns_rates_by_dow(self):
        rows = [
            _make_row(dow=1, total=25, completed=22, no_shows=3),  # Monday
            _make_row(dow=5, total=12, completed=6, no_shows=6),   # Friday
        ]
        db = _make_mock_db([rows])
        result = SchedulingOptimizer.get_dow_show_rates(db, org_id=1)

        assert 1 in result
        assert result[1]["day_name"] == "Monday"
        assert result[1]["show_rate"] == pytest.approx(0.88, abs=0.01)
        assert result[5]["day_name"] == "Friday"
        assert result[5]["show_rate"] == 0.5

    def test_empty_data(self):
        db = _make_mock_db([[]])
        result = SchedulingOptimizer.get_dow_show_rates(db, org_id=1)
        assert result == {}


# ---------------------------------------------------------------------------
# Slot scoring algorithm
# ---------------------------------------------------------------------------

class TestSlotScoring:
    def test_high_show_rate_scores_higher(self):
        """A slot at a high-show-rate hour should score higher than a low one."""
        high_hour_stats = {
            10: {"total": 50, "show_rate": 0.92, "wilson_score": 0.83},
        }
        low_hour_stats = {
            16: {"total": 50, "show_rate": 0.45, "wilson_score": 0.32},
        }
        dow_stats = {
            1: {"total": 30, "show_rate": 0.8, "wilson_score": 0.65},
        }

        score_high = SchedulingOptimizer.calculate_slot_score(
            slot_hour=10, slot_dow=1,
            hourly_stats=high_hour_stats, dow_stats=dow_stats,
        )
        score_low = SchedulingOptimizer.calculate_slot_score(
            slot_hour=16, slot_dow=1,
            hourly_stats=low_hour_stats, dow_stats=dow_stats,
        )
        assert score_high > score_low

    def test_returns_between_zero_and_one(self):
        stats = {10: {"total": 20, "show_rate": 0.5, "wilson_score": 0.3}}
        dow = {1: {"total": 20, "show_rate": 0.5, "wilson_score": 0.3}}
        score = SchedulingOptimizer.calculate_slot_score(10, 1, stats, dow)
        assert 0.0 <= score <= 1.0

    def test_missing_hour_uses_default(self):
        """When no data for the hour, score should use default show_rate."""
        score = SchedulingOptimizer.calculate_slot_score(
            slot_hour=15, slot_dow=1,
            hourly_stats={},  # No data
            dow_stats={},     # No data
        )
        # Should use default 0.5 for both, resulting in ~0.5
        assert 0.2 <= score <= 0.7

    def test_meeting_type_bonus_applied(self):
        """Meeting type stats should influence the score."""
        hourly = {10: {"total": 20, "show_rate": 0.8, "wilson_score": 0.65}}
        dow = {1: {"total": 20, "show_rate": 0.8, "wilson_score": 0.65}}
        mt_stats = {"discovery_call": 0.9, "rate_lock_discussion": 0.3}

        score_good_type = SchedulingOptimizer.calculate_slot_score(
            10, 1, hourly, dow,
            meeting_type_stats=mt_stats, meeting_type="discovery_call",
        )
        score_bad_type = SchedulingOptimizer.calculate_slot_score(
            10, 1, hourly, dow,
            meeting_type_stats=mt_stats, meeting_type="rate_lock_discussion",
        )
        assert score_good_type > score_bad_type


# ---------------------------------------------------------------------------
# Optimal slot ranking
# ---------------------------------------------------------------------------

class TestGetOptimalSlots:
    @pytest.mark.asyncio
    async def test_returns_ranked_slots(self):
        """Should return slots sorted by score descending."""
        # Mock: hourly stats, dow stats, meeting type stats, booked slots
        hourly_rows = [
            _make_row(hour=9, total=20, completed=18, no_shows=2),
            _make_row(hour=10, total=20, completed=16, no_shows=4),
            _make_row(hour=11, total=20, completed=10, no_shows=10),
            _make_row(hour=13, total=20, completed=15, no_shows=5),
            _make_row(hour=14, total=20, completed=8, no_shows=12),
        ]
        dow_rows = [
            _make_row(dow=1, total=30, completed=25, no_shows=5),
        ]
        booked_rows = [
            _make_row(hour=10, minute=0),  # 10:00 is taken
        ]

        db = _make_mock_db([
            hourly_rows,    # get_hourly_show_rates
            dow_rows,        # get_dow_show_rates
            booked_rows,     # booked slots query
        ])

        # Use a Monday (dow=1 in PG) for predictable results
        # Find the next Monday from today
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)

        result = await SchedulingOptimizer.get_optimal_slots(
            db=db,
            org_id=1,
            user_id=42,
            target_date=next_monday,
            count=5,
        )

        assert "slots" in result
        assert result["returned_count"] <= 5
        assert result["date"] == next_monday.isoformat()

        # Verify slots are sorted by score descending
        scores = [s["score"] for s in result["slots"]]
        assert scores == sorted(scores, reverse=True)

        # 10:00 should not appear (booked)
        slot_displays = [s["display"] for s in result["slots"]]
        assert "10:00" not in slot_displays

    @pytest.mark.asyncio
    async def test_empty_history_still_returns_slots(self):
        """Even with no historical data, should return default-scored slots."""
        db = _make_mock_db([
            [],  # hourly stats (empty)
            [],  # dow stats (empty)
            [],  # booked (empty)
        ])

        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)

        result = await SchedulingOptimizer.get_optimal_slots(
            db=db, org_id=1, user_id=1,
            target_date=next_monday, count=3,
        )

        assert result["total_available"] > 0
        assert len(result["slots"]) <= 3
        # Data quality should show zero data points
        assert result["data_quality"]["hourly_data_points"] == 0


# ---------------------------------------------------------------------------
# No-show risk prediction
# ---------------------------------------------------------------------------

class TestNoShowRisk:
    @pytest.mark.asyncio
    async def test_unknown_attendee(self):
        """No history should return risk 'unknown' with score 0.5."""
        db = _make_mock_db([[]])  # Empty result
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="new@example.com", org_id=1,
        )
        assert result["risk"] == "unknown"
        assert result["score"] == 0.5
        assert result["history_count"] == 0

    @pytest.mark.asyncio
    async def test_reliable_attendee_low_risk(self):
        """Attendee who always shows should be low or medium risk.

        Wilson lower bound is conservative with small samples:
        15/15 = wilson 0.796, risk 0.204 -> medium.
        With 50+ appointments all completed, risk drops to low.
        """
        # Large sample: 50 completed, 0 no-shows -> low risk
        rows = [
            _make_row(status="completed", count=50),
        ]
        db = _make_mock_db([rows])
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="reliable@example.com", org_id=1,
        )
        assert result["risk"] == "low"
        assert result["score"] < 0.15
        assert result["completed_count"] == 50
        assert result["no_show_count"] == 0

    @pytest.mark.asyncio
    async def test_flaky_attendee_high_risk(self):
        """Attendee who frequently no-shows should be high risk."""
        rows = [
            _make_row(status="completed", count=3),
            _make_row(status="no_show", count=7),
        ]
        db = _make_mock_db([rows])
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="flaky@example.com", org_id=1,
        )
        assert result["risk"] == "high"
        assert result["score"] > 0.3
        assert result["no_show_count"] == 7
        assert "recommendation" in result
        assert "High risk" in result["recommendation"] or "no-show" in result["recommendation"].lower()

    @pytest.mark.asyncio
    async def test_moderate_attendee_medium_risk(self):
        """Attendee with occasional no-shows should not be low risk.

        Wilson lower bound for 8/10 completed = 0.49, risk = 0.51 -> high.
        For larger sample: 40/50 completed = wilson ~0.67, risk ~0.33 -> high.
        For very mild: 45/50 = wilson ~0.80, risk ~0.20 -> medium.
        """
        rows = [
            _make_row(status="completed", count=45),
            _make_row(status="no_show", count=5),
        ]
        db = _make_mock_db([rows])
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="moderate@example.com", org_id=1,
        )
        assert result["risk"] in ("medium", "high")
        assert 0.0 < result["score"] < 0.6

    @pytest.mark.asyncio
    async def test_only_cancellations(self):
        """Attendee with only cancellations (no actual attendance) should get moderate risk."""
        rows = [
            _make_row(status="cancelled", count=5),
        ]
        db = _make_mock_db([rows])
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="canceller@example.com", org_id=1,
        )
        assert result["risk"] in ("medium", "high")
        assert result["cancelled_count"] == 5


# ---------------------------------------------------------------------------
# Booking insights
# ---------------------------------------------------------------------------

class TestBookingInsights:
    @pytest.mark.asyncio
    async def test_returns_comprehensive_insights(self):
        """Should return all expected insight sections."""
        overall_row = _make_row(
            total=100, completed=75, no_shows=15, cancelled=10,
            avg_lead_time_days=3.5, avg_duration_minutes=30.0,
        )
        best_hours = [
            _make_row(hour=10, total=20, completed=18),
            _make_row(hour=9, total=15, completed=13),
        ]
        best_days = [
            _make_row(dow=2, total=25, completed=22),  # Tuesday
            _make_row(dow=3, total=20, completed=17),   # Wednesday
        ]
        meeting_types = [
            _make_row(meeting_type="discovery_call", total=40, completed=35, no_shows=5),
            _make_row(meeting_type="rate_lock_discussion", total=20, completed=12, no_shows=8),
        ]
        by_source = [
            _make_row(booking_source="manual", total=50, completed=40, no_shows=10),
            _make_row(booking_source="ai", total=30, completed=25, no_shows=5),
        ]

        db = _make_mock_db([
            [overall_row],
            best_hours,
            best_days,
            meeting_types,
            by_source,
        ])

        result = await SchedulingOptimizer.get_booking_insights(
            db=db, org_id=1, days=90,
        )

        assert result["period_days"] == 90
        assert result["summary"]["total_appointments"] == 100
        assert result["summary"]["completed"] == 75
        assert result["summary"]["no_shows"] == 15
        assert result["summary"]["show_rate_pct"] == pytest.approx(83.3, abs=0.1)
        assert len(result["best_hours"]) == 2
        assert len(result["best_days"]) == 2
        assert len(result["meeting_types"]) == 2
        assert len(result["by_booking_source"]) == 2
        assert "recommendation" in result

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeroes(self):
        """With no appointment data, all metrics should be zero."""
        empty_row = _make_row(
            total=0, completed=0, no_shows=0, cancelled=0,
            avg_lead_time_days=None, avg_duration_minutes=None,
        )
        db = _make_mock_db([
            [empty_row],
            [],  # best hours
            [],  # best days
            [],  # meeting types
            [],  # by source
        ])

        result = await SchedulingOptimizer.get_booking_insights(
            db=db, org_id=1,
        )
        assert result["summary"]["total_appointments"] == 0
        assert result["summary"]["show_rate_pct"] == 0.0
        assert result["best_hours"] == []


# ---------------------------------------------------------------------------
# Best times next week
# ---------------------------------------------------------------------------

class TestBestTimesNextWeek:
    @pytest.mark.asyncio
    async def test_returns_ranked_slots_for_next_week(self):
        """Should return slots across multiple days sorted by score."""
        hourly_rows = [
            _make_row(hour=9, total=20, completed=18, no_shows=2),
            _make_row(hour=10, total=20, completed=16, no_shows=4),
            _make_row(hour=14, total=20, completed=10, no_shows=10),
        ]
        dow_rows = [
            _make_row(dow=1, total=30, completed=25, no_shows=5),  # Monday
            _make_row(dow=2, total=30, completed=27, no_shows=3),  # Tuesday
        ]
        booked_rows = []  # Nothing booked

        db = _make_mock_db([
            hourly_rows,
            dow_rows,
            booked_rows,
        ])

        result = await SchedulingOptimizer.get_best_times_next_week(
            db=db, org_id=1, user_id=42, count=10,
        )

        assert "best_times" in result
        assert result["returned_count"] <= 10
        assert result["total_available"] > 0

        # Verify sorted by score descending
        scores = [s["score"] for s in result["best_times"]]
        assert scores == sorted(scores, reverse=True)

        # All slots should be in the future
        today = date.today()
        for slot in result["best_times"]:
            slot_date = date.fromisoformat(slot["date"])
            assert slot_date > today

    @pytest.mark.asyncio
    async def test_excludes_booked_slots(self):
        """Booked slots should not appear in results."""
        hourly_rows = [
            _make_row(hour=10, total=20, completed=18, no_shows=2),
        ]
        dow_rows = [
            _make_row(dow=1, total=20, completed=18, no_shows=2),
        ]

        # Book 10:00 for every day next week
        today = date.today()
        booked = []
        for offset in range(1, 8):
            d = today + timedelta(days=offset)
            if d.weekday() < 5:  # Weekday only
                booked.append(_make_row(appt_date=d, hour=10, minute=0))
                booked.append(_make_row(appt_date=d, hour=10, minute=30))

        db = _make_mock_db([hourly_rows, dow_rows, booked])

        result = await SchedulingOptimizer.get_best_times_next_week(
            db=db, org_id=1, user_id=42, count=20,
        )

        # 10:00 and 10:30 should not appear
        for slot in result["best_times"]:
            assert not (slot["hour"] == 10 and slot["minute"] == 0), \
                f"Booked slot 10:00 appeared on {slot['date']}"
            assert not (slot["hour"] == 10 and slot["minute"] == 30), \
                f"Booked slot 10:30 appeared on {slot['date']}"


# ---------------------------------------------------------------------------
# Recommendation text helpers
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_no_show_recommendation_high(self):
        text = _get_no_show_recommendation("high", 5, 8, 2)
        assert "High risk" in text
        assert "SMS" in text or "reminder" in text.lower()

    def test_no_show_recommendation_medium(self):
        text = _get_no_show_recommendation("medium", 2, 10, 0)
        assert "Moderate risk" in text

    def test_no_show_recommendation_low(self):
        text = _get_no_show_recommendation("low", 0, 10, 0)
        assert "Low risk" in text

    def test_insights_recommendation_low_data(self):
        text = _build_insights_recommendation([], [], total=5)
        assert "more data" in text.lower() or "only" in text.lower()

    def test_insights_recommendation_with_data(self):
        hours = [{"display": "10:00", "show_rate_pct": 90.0, "total": 20}]
        days = [{"day_name": "Tuesday", "show_rate_pct": 88.0, "total": 25}]
        text = _build_insights_recommendation(hours, days, total=100)
        assert "10:00" in text
        assert "Tuesday" in text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_wilson_score_with_zero_positives(self):
        """Zero successes should produce a very low score."""
        score = _wilson_lower_bound(0, 20)
        assert score < 0.05

    def test_wilson_score_all_positive(self):
        """All successes should produce a high but not perfect score."""
        score = _wilson_lower_bound(20, 20)
        assert score > 0.8
        assert score < 1.0

    @pytest.mark.asyncio
    async def test_no_show_risk_handles_all_no_shows(self):
        """Attendee who always no-shows should be max risk."""
        rows = [_make_row(status="no_show", count=10)]
        db = _make_mock_db([rows])
        result = await SchedulingOptimizer.get_no_show_risk(
            db=db, attendee_email="ghost@example.com", org_id=1,
        )
        assert result["risk"] == "high"
        assert result["score"] > 0.7

    def test_slot_score_extreme_values(self):
        """Score should remain in [0, 1] even with extreme inputs."""
        hourly = {10: {"total": 1000, "show_rate": 1.0, "wilson_score": 0.99}}
        dow = {1: {"total": 1000, "show_rate": 1.0, "wilson_score": 0.99}}
        score = SchedulingOptimizer.calculate_slot_score(10, 1, hourly, dow)
        assert 0.0 <= score <= 1.0

        hourly_bad = {10: {"total": 1000, "show_rate": 0.0, "wilson_score": 0.01}}
        dow_bad = {1: {"total": 1000, "show_rate": 0.0, "wilson_score": 0.01}}
        score_bad = SchedulingOptimizer.calculate_slot_score(10, 1, hourly_bad, dow_bad)
        assert 0.0 <= score_bad <= 1.0
