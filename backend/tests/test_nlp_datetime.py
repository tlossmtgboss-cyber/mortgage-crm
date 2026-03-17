"""
Tests for Natural Language Date/Time Parser and Slot Matcher

Covers all expression types listed in the spec:
- Relative dates (tomorrow, next week, in 3 days)
- Time-of-day keywords (morning, afternoon, evening)
- Specific times (at 2, at 2:30, around 3pm)
- Time ranges (between 1 and 4, after lunch, before noon)
- Multi-option dates (Monday or Wednesday)
- ASAP expressions (as soon as possible, first available)
- Vague expressions (sometime next week)
- Negation / constraints (not mornings, I work until noon)
- Edge cases (DST, year boundaries, ambiguous)
- Confidence scoring validation
- Slot matching and ranking
"""

import pytest
from datetime import date, time, datetime, timedelta

from services.nlp_datetime_parser import (
    ParsedDateRange,
    parse_datetime_expression,
    _next_weekday,
    _weekdays_in_range,
    _word_to_number,
)
from services.slot_matcher import match_slots_to_preference


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Use a fixed reference date to make tests deterministic.
# 2026-03-10 is a Tuesday.
REF = datetime(2026, 3, 10, 10, 0, 0)
REF_DATE = REF.date()


def parse(text: str, ref: datetime = REF) -> ParsedDateRange:
    """Shortcut for tests."""
    return parse_datetime_expression(text, reference_date=ref, timezone="America/New_York")


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_word_to_number_words(self):
        assert _word_to_number("three") == 3
        assert _word_to_number("twelve") == 12

    def test_word_to_number_digits(self):
        assert _word_to_number("5") == 5
        assert _word_to_number("14") == 14

    def test_word_to_number_invalid(self):
        assert _word_to_number("blah") is None

    def test_next_weekday_same_day_advances(self):
        # 2026-03-10 is Tuesday (weekday=1); asking for Tuesday should give next Tuesday
        result = _next_weekday(REF_DATE, 1)
        assert result == date(2026, 3, 17)

    def test_next_weekday_later_in_week(self):
        # Ask for Friday (4) from Tuesday (1)
        result = _next_weekday(REF_DATE, 4)
        assert result == date(2026, 3, 13)

    def test_weekdays_in_range(self):
        start = date(2026, 3, 9)  # Monday
        end = date(2026, 3, 15)   # Sunday
        result = _weekdays_in_range(start, end)
        assert len(result) == 5
        assert result[0] == date(2026, 3, 9)
        assert result[-1] == date(2026, 3, 13)


# ---------------------------------------------------------------------------
# Relative date expressions
# ---------------------------------------------------------------------------

class TestRelativeDates:
    def test_today(self):
        r = parse("today")
        assert REF_DATE in r.dates
        assert r.confidence >= 0.8

    def test_tomorrow(self):
        r = parse("tomorrow")
        assert date(2026, 3, 11) in r.dates
        assert r.confidence >= 0.8

    def test_tomorrow_afternoon(self):
        r = parse("tomorrow afternoon")
        assert date(2026, 3, 11) in r.dates
        assert r.time_range is not None
        assert r.time_range[0] >= time(12, 0)
        assert r.time_range[1] <= time(17, 0)

    def test_day_after_tomorrow(self):
        r = parse("day after tomorrow")
        assert date(2026, 3, 12) in r.dates

    def test_in_3_days(self):
        r = parse("in 3 days")
        assert date(2026, 3, 13) in r.dates
        assert r.flexibility == "exact"

    def test_in_two_weeks(self):
        r = parse("in about two weeks")
        # Should give weekdays of the week 2 weeks out
        assert len(r.dates) >= 3
        assert r.flexibility == "flexible"
        # All dates should be roughly 2 weeks from reference
        for d in r.dates:
            assert 10 <= (d - REF_DATE).days <= 18

    def test_in_five_days(self):
        r = parse("in five days")
        assert date(2026, 3, 15) in r.dates


# ---------------------------------------------------------------------------
# Named day expressions
# ---------------------------------------------------------------------------

class TestNamedDays:
    def test_this_friday(self):
        r = parse("this Friday")
        assert date(2026, 3, 13) in r.dates

    def test_next_tuesday(self):
        # Reference is Tuesday; "next Tuesday" should be the one after this week
        r = parse("next Tuesday")
        # Should be March 24 (skip this week's Tuesday which is today, skip March 17 because "next")
        assert date(2026, 3, 24) in r.dates

    def test_monday(self):
        r = parse("Monday")
        # Next Monday from Tuesday is March 16
        assert date(2026, 3, 16) in r.dates

    def test_wednesday(self):
        r = parse("Wednesday")
        # Next Wednesday from Tuesday is March 11
        assert date(2026, 3, 11) in r.dates

    def test_monday_or_wednesday(self):
        r = parse("Monday or Wednesday")
        assert len(r.dates) >= 2
        assert r.flexibility == "flexible"
        weekdays = {d.weekday() for d in r.dates}
        assert 0 in weekdays  # Monday
        assert 2 in weekdays  # Wednesday


# ---------------------------------------------------------------------------
# Week expressions
# ---------------------------------------------------------------------------

class TestWeekExpressions:
    def test_next_week(self):
        r = parse("sometime next week")
        # Next week starts Monday March 16
        assert len(r.dates) == 5
        assert r.dates[0] == date(2026, 3, 16)
        assert r.dates[-1] == date(2026, 3, 20)
        assert r.flexibility == "very_flexible"

    def test_this_week(self):
        r = parse("this week")
        # Reference is Tuesday March 10; should include remaining weekdays
        for d in r.dates:
            assert d.weekday() < 5  # All weekdays
            assert d >= REF_DATE

    def test_week_of_the_15th(self):
        r = parse("the week of the 15th")
        # March 15 is Sunday; week of = Mon March 9 through Fri March 13
        # But since ref is March 10, the 15th is upcoming
        assert len(r.dates) >= 3
        assert r.flexibility == "flexible"


# ---------------------------------------------------------------------------
# Specific time expressions
# ---------------------------------------------------------------------------

class TestSpecificTimes:
    def test_at_2pm(self):
        r = parse("tomorrow at 2pm")
        assert r.time_range is not None
        assert r.time_range[0].hour == 14
        assert r.confidence >= 0.7

    def test_at_2_30(self):
        r = parse("at 2:30 pm")
        assert r.time_range is not None
        assert r.time_range[0] == time(14, 30)

    def test_at_10am(self):
        r = parse("Monday at 10am")
        assert r.time_range is not None
        assert r.time_range[0].hour == 10

    def test_bare_number_assumes_pm(self):
        r = parse("at 3")
        assert r.time_range is not None
        # "at 3" with no am/pm should assume 3pm for business context
        assert r.time_range[0].hour == 15

    def test_at_9am(self):
        r = parse("at 9 am")
        assert r.time_range is not None
        assert r.time_range[0].hour == 9

    def test_around_3pm(self):
        r = parse("around 3pm")
        assert r.time_range is not None
        # "around" creates a +/-1h window, so start ~2pm, end ~4pm
        assert r.time_range[0].hour <= 14
        assert r.time_range[1].hour >= 16
        assert r.confidence < 0.8  # Lower confidence for approximate


# ---------------------------------------------------------------------------
# Time ranges
# ---------------------------------------------------------------------------

class TestTimeRanges:
    def test_between_1_and_4(self):
        r = parse("between 1 and 4")
        assert r.time_range is not None
        assert r.time_range[0].hour == 13  # 1pm
        assert r.time_range[1].hour == 16  # 4pm

    def test_from_2_to_5_pm(self):
        r = parse("from 2 to 5 pm")
        assert r.time_range is not None
        assert r.time_range[0].hour == 14
        assert r.time_range[1].hour == 17

    def test_1_dash_3pm(self):
        r = parse("1-3pm")
        assert r.time_range is not None
        assert r.time_range[0].hour == 13
        assert r.time_range[1].hour == 15

    def test_after_3pm(self):
        r = parse("after 3pm any day")
        assert r.time_range is not None
        assert r.time_range[0].hour == 15
        assert r.time_range[1].hour >= 17

    def test_after_lunch(self):
        r = parse("after lunch")
        assert r.time_range is not None
        assert r.time_range[0].hour == 12

    def test_before_noon(self):
        r = parse("before noon")
        assert r.time_range is not None
        assert r.time_range[1].hour == 12
        assert r.time_range[0].hour <= 9


# ---------------------------------------------------------------------------
# Time-of-day keywords
# ---------------------------------------------------------------------------

class TestTimeOfDay:
    def test_morning(self):
        r = parse("tomorrow morning")
        assert r.time_range is not None
        assert r.time_range[0].hour == 9
        assert r.time_range[1].hour == 12

    def test_afternoon(self):
        r = parse("Wednesday afternoon")
        assert r.time_range is not None
        assert r.time_range[0].hour == 12
        assert r.time_range[1].hour == 17

    def test_evening(self):
        r = parse("Friday evening")
        assert r.time_range is not None
        assert r.time_range[0].hour == 17
        assert r.time_range[1].hour == 20

    def test_early_morning(self):
        r = parse("early morning")
        assert r.time_range is not None
        assert r.time_range[0].hour == 8

    def test_late_afternoon(self):
        r = parse("late afternoon")
        assert r.time_range is not None
        assert r.time_range[0].hour == 15
        assert r.time_range[1].hour == 17

    def test_end_of_day(self):
        r = parse("end of day")
        assert r.time_range is not None
        assert r.time_range[0].hour == 16


# ---------------------------------------------------------------------------
# ASAP / urgency expressions
# ---------------------------------------------------------------------------

class TestASAP:
    def test_asap(self):
        r = parse("as soon as possible")
        assert len(r.dates) >= 2
        assert r.flexibility == "very_flexible"
        assert r.confidence >= 0.7

    def test_first_available(self):
        r = parse("first available")
        assert len(r.dates) >= 2
        assert r.flexibility == "very_flexible"

    def test_earliest(self):
        r = parse("the earliest appointment you have")
        assert len(r.dates) >= 2

    def test_asap_abbreviation(self):
        r = parse("ASAP please")
        assert r.flexibility == "very_flexible"


# ---------------------------------------------------------------------------
# Vague / flexible expressions
# ---------------------------------------------------------------------------

class TestVague:
    def test_sometime(self):
        r = parse("sometime")
        assert len(r.dates) >= 3
        assert r.flexibility == "very_flexible"
        assert r.confidence <= 0.5

    def test_whenever(self):
        r = parse("whenever works for you")
        assert r.flexibility == "very_flexible"
        assert "caller_flexible" in r.constraints

    def test_any_day(self):
        r = parse("any day is fine")
        assert len(r.dates) >= 3

    def test_im_flexible(self):
        r = parse("Monday or Wednesday, I'm flexible")
        assert len(r.dates) >= 2
        assert "caller_flexible" in r.constraints
        assert r.flexibility == "very_flexible"


# ---------------------------------------------------------------------------
# Negation / constraints
# ---------------------------------------------------------------------------

class TestConstraints:
    def test_not_mornings(self):
        r = parse("not mornings")
        assert "no_mornings" in r.constraints
        # Should have time range set to afternoon+
        assert r.time_range is not None
        assert r.time_range[0].hour >= 12

    def test_work_until_noon(self):
        r = parse("I work until noon")
        assert "no_mornings" in r.constraints

    def test_work_until_3pm(self):
        r = parse("I work until 3 pm")
        assert any("unavailable_before" in c for c in r.constraints)
        assert r.time_range is not None
        assert r.time_range[0].hour >= 15

    def test_cant_do_mornings(self):
        r = parse("I can't do mornings")
        assert "no_mornings" in r.constraints

    def test_no_mondays(self):
        r = parse("not on Mondays")
        assert "no_monday" in r.constraints

    def test_no_weekends(self):
        r = parse("no weekends please")
        assert "no_weekends" in r.constraints

    def test_not_afternoons(self):
        r = parse("not afternoons, please")
        assert "no_afternoons" in r.constraints
        assert r.time_range is not None
        assert r.time_range[1].hour <= 12


# ---------------------------------------------------------------------------
# Specific date expressions
# ---------------------------------------------------------------------------

class TestSpecificDates:
    def test_march_15(self):
        r = parse("March 15")
        assert date(2026, 3, 15) in r.dates
        assert r.confidence >= 0.8

    def test_march_15th(self):
        r = parse("March 15th")
        assert date(2026, 3, 15) in r.dates

    def test_the_20th(self):
        r = parse("the 20th")
        assert date(2026, 3, 20) in r.dates

    def test_the_5th_wraps_to_next_month(self):
        # Reference is March 10; "the 5th" should be April 5th
        r = parse("the 5th")
        assert date(2026, 4, 5) in r.dates

    def test_december_wraps_year(self):
        # Reference is March; "December 25" should still be 2026
        r = parse("December 25")
        assert date(2026, 12, 25) in r.dates


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string(self):
        r = parse("")
        assert r.confidence == 0.0
        assert not r.dates

    def test_none_text(self):
        r = parse_datetime_expression(None, reference_date=REF)
        assert r.confidence == 0.0

    def test_gibberish(self):
        r = parse("asdfghjkl qwerty")
        assert r.confidence <= 0.3

    def test_year_boundary(self):
        # Reference is Dec 30, 2026; "next Tuesday" should be in January 2027
        ref_dec = datetime(2026, 12, 30, 10, 0, 0)  # Wednesday
        r = parse("next Tuesday", ref=ref_dec)
        assert any(d.year == 2027 for d in r.dates)

    def test_dst_spring_forward(self):
        # March 8, 2026 is DST transition in US Eastern.
        # Parser should not crash or produce wrong dates.
        ref_dst = datetime(2026, 3, 7, 10, 0, 0)  # Saturday
        r = parse("tomorrow morning", ref=ref_dst)
        assert date(2026, 3, 8) in r.dates
        assert r.time_range is not None

    def test_dst_fall_back(self):
        # November 1, 2026 is DST fall-back.
        ref_fall = datetime(2026, 10, 31, 10, 0, 0)  # Saturday
        r = parse("tomorrow afternoon", ref=ref_fall)
        assert date(2026, 11, 1) in r.dates
        assert r.time_range is not None

    def test_leap_year_feb_29(self):
        # 2028 is a leap year
        ref_leap = datetime(2028, 2, 28, 10, 0, 0)
        r = parse("tomorrow", ref=ref_leap)
        assert date(2028, 2, 29) in r.dates

    def test_to_dict(self):
        r = parse("tomorrow afternoon")
        d = r.to_dict()
        assert "dates" in d
        assert "time_range" in d
        assert "flexibility" in d
        assert "confidence" in d
        assert isinstance(d["dates"], list)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_exact_datetime_high_confidence(self):
        r = parse("tomorrow at 2pm")
        assert r.confidence >= 0.7

    def test_vague_low_confidence(self):
        r = parse("sometime")
        assert r.confidence <= 0.5

    def test_asap_moderate_confidence(self):
        r = parse("as soon as possible")
        assert 0.5 <= r.confidence <= 0.9

    def test_specific_date_no_time_moderate(self):
        r = parse("next Friday")
        # Date without time = moderate
        assert 0.5 <= r.confidence <= 0.9

    def test_full_spec_highest(self):
        r = parse("next Wednesday at 2:30 pm")
        assert r.confidence >= 0.7


# ---------------------------------------------------------------------------
# Slot Matcher Tests
# ---------------------------------------------------------------------------


def _make_slots(base_date: date, hours: list) -> list:
    """Create mock available slots for testing."""
    slots = []
    for h in hours:
        start = datetime.combine(base_date, time(h, 0))
        end = start + timedelta(minutes=30)
        slots.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "display": start.strftime("%A, %B %d at %I:%M %p"),
            "available": True,
        })
    return slots


class TestSlotMatcher:
    def test_exact_date_and_time_match(self):
        """Slots on the preferred date and time should rank highest."""
        target = date(2026, 3, 11)  # Wednesday
        slots = (
            _make_slots(date(2026, 3, 11), [9, 10, 14, 15])
            + _make_slots(date(2026, 3, 12), [9, 10, 14, 15])
        )
        parsed = parse("tomorrow afternoon")  # March 11, 12-5pm
        ranked = match_slots_to_preference(slots, parsed, top_n=3)

        assert len(ranked) >= 1
        # Top result should be on March 11 in the afternoon
        top = ranked[0]
        top_dt = datetime.fromisoformat(top["start"])
        assert top_dt.date() == target
        assert top_dt.hour >= 12

    def test_time_of_day_ranking(self):
        """Morning slots should rank lower when preference is afternoon."""
        slots = _make_slots(date(2026, 3, 11), [9, 10, 11, 14, 15, 16])
        parsed = parse("Wednesday afternoon")
        ranked = match_slots_to_preference(slots, parsed, top_n=3)

        # All top results should be afternoon hours
        for slot in ranked:
            dt = datetime.fromisoformat(slot["start"])
            assert dt.hour >= 12

    def test_constraint_filtering(self):
        """Slots violating constraints should be excluded."""
        slots = _make_slots(date(2026, 3, 11), [9, 10, 11, 14, 15, 16])
        parsed = parse("not mornings")
        ranked = match_slots_to_preference(slots, parsed, top_n=5)

        for slot in ranked:
            dt = datetime.fromisoformat(slot["start"])
            assert dt.hour >= 12, f"Morning slot should be filtered: {dt}"

    def test_no_day_constraint(self):
        """Slots on excluded days should be filtered out."""
        monday_slots = _make_slots(date(2026, 3, 16), [10, 14])  # Monday
        tuesday_slots = _make_slots(date(2026, 3, 17), [10, 14])  # Tuesday
        all_slots = monday_slots + tuesday_slots

        parsed = parse("not on Mondays")
        ranked = match_slots_to_preference(all_slots, parsed, top_n=5)

        for slot in ranked:
            dt = datetime.fromisoformat(slot["start"])
            assert dt.weekday() != 0, "Monday slots should be excluded"

    def test_match_reasons_present(self):
        """Each result should have match_reasons."""
        slots = _make_slots(date(2026, 3, 11), [14, 15])
        parsed = parse("tomorrow afternoon")
        ranked = match_slots_to_preference(slots, parsed, top_n=2)

        for slot in ranked:
            assert "match_score" in slot
            assert "match_reasons" in slot
            assert isinstance(slot["match_reasons"], list)

    def test_empty_slots_returns_empty(self):
        parsed = parse("tomorrow")
        ranked = match_slots_to_preference([], parsed)
        assert ranked == []

    def test_top_n_limits_results(self):
        slots = _make_slots(date(2026, 3, 11), list(range(9, 17)))
        parsed = parse("tomorrow")
        ranked = match_slots_to_preference(slots, parsed, top_n=3)
        assert len(ranked) <= 3

    def test_multi_date_preference(self):
        """Slots matching either preferred date should score well."""
        mon_slots = _make_slots(date(2026, 3, 16), [10, 14])  # Monday
        wed_slots = _make_slots(date(2026, 3, 18), [10, 14])  # Wednesday
        thu_slots = _make_slots(date(2026, 3, 19), [10, 14])  # Thursday (not preferred)
        all_slots = mon_slots + wed_slots + thu_slots

        parsed = parse("Monday or Wednesday")
        ranked = match_slots_to_preference(all_slots, parsed, top_n=5)

        # Top results should be from Monday or Wednesday
        top_dates = {datetime.fromisoformat(s["start"]).date() for s in ranked[:4]}
        assert date(2026, 3, 16) in top_dates or date(2026, 3, 18) in top_dates

    def test_asap_prefers_sooner(self):
        """ASAP should prefer slots on nearer dates."""
        today_slots = _make_slots(REF_DATE, [14, 15])
        tomorrow_slots = _make_slots(REF_DATE + timedelta(days=1), [14, 15])
        later_slots = _make_slots(REF_DATE + timedelta(days=5), [14, 15])
        all_slots = today_slots + tomorrow_slots + later_slots

        parsed = parse("as soon as possible")
        ranked = match_slots_to_preference(all_slots, parsed, top_n=3)

        # Top result should be today or tomorrow
        top_dt = datetime.fromisoformat(ranked[0]["start"])
        assert (top_dt.date() - REF_DATE).days <= 1

    def test_original_slot_keys_preserved(self):
        """Extra keys on slot dicts should pass through."""
        slots = [{
            "start": datetime.combine(date(2026, 3, 11), time(14, 0)).isoformat(),
            "end": datetime.combine(date(2026, 3, 11), time(14, 30)).isoformat(),
            "custom_field": "test_value",
            "available": True,
        }]
        parsed = parse("tomorrow")
        ranked = match_slots_to_preference(slots, parsed, top_n=1)
        assert ranked[0]["custom_field"] == "test_value"
        assert ranked[0]["available"] is True
