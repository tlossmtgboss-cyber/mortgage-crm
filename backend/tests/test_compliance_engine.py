"""
Tests for the deterministic compliance calculation engine.

Covers:
    - Business day arithmetic (weekends, holidays, year boundaries)
    - Federal holiday computation and observance rules
    - TRID LE/CD deadline calculations
    - TRID CD waiting period enforcement
    - TRID fee tolerance classification
    - TRID changed circumstance re-disclosure
    - ECOA adverse action deadline calculations
    - ECOA counteroffer response window
    - TCPA time-of-day window checks
    - TCPA area code timezone inference
    - ComplianceService integration (with mocked DB)

All tests are pure/deterministic — no DB or LLM needed.
"""

import pytest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Business Day Tests
# ---------------------------------------------------------------------------

from services.compliance.business_days import (
    add_business_days,
    subtract_business_days,
    count_business_days,
    is_business_day,
    compute_federal_holidays,
    get_federal_holidays,
    get_holiday_calendar,
    _observed,
    _nth_weekday,
    _last_weekday,
)


class TestFederalHolidays:
    """Test federal holiday computation."""

    def test_2026_holidays_count(self):
        """2026 should have 11 federal holidays."""
        holidays = compute_federal_holidays(2026)
        assert len(holidays) == 11

    def test_2026_new_years_day(self):
        """New Year's Day 2026 is Thursday Jan 1."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 1, 1) in holidays

    def test_2026_mlk_day(self):
        """MLK Day 2026 is 3rd Monday in January = Jan 19."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 1, 19) in holidays

    def test_2026_presidents_day(self):
        """Presidents' Day 2026 is 3rd Monday in February = Feb 16."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 2, 16) in holidays

    def test_2026_memorial_day(self):
        """Memorial Day 2026 is last Monday in May = May 25."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 5, 25) in holidays

    def test_2026_independence_day_observed(self):
        """July 4, 2026 is Saturday -> observed Friday July 3."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 7, 3) in holidays
        assert date(2026, 7, 4) not in holidays

    def test_2026_labor_day(self):
        """Labor Day 2026 is 1st Monday in September = Sep 7."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 9, 7) in holidays

    def test_2026_christmas_observed(self):
        """Christmas 2026 is Friday Dec 25."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 12, 25) in holidays

    def test_2027_new_years_observed(self):
        """New Year's Day 2027 is Friday Jan 1."""
        holidays = compute_federal_holidays(2027)
        assert date(2027, 1, 1) in holidays

    def test_2027_juneteenth_observed(self):
        """Juneteenth 2027: June 19 is Saturday -> observed Friday June 18."""
        holidays = compute_federal_holidays(2027)
        assert date(2027, 6, 18) in holidays

    def test_holiday_cache(self):
        """get_federal_holidays should cache results."""
        h1 = get_federal_holidays(2026)
        h2 = get_federal_holidays(2026)
        assert h1 is h2  # Same object reference (cached)

    def test_holiday_calendar_structure(self):
        """get_holiday_calendar should return named holidays."""
        cal = get_holiday_calendar(2026)
        assert cal.year == 2026
        assert len(cal.holidays) == 11
        names = {h.name for h in cal.holidays}
        assert "Christmas Day" in names
        assert "Thanksgiving Day" in names
        assert "Independence Day" in names


class TestObservedRules:
    """Test OPM Saturday/Sunday observance rules."""

    def test_saturday_observed_friday(self):
        """Holiday on Saturday is observed on preceding Friday."""
        # July 4, 2026 is Saturday
        assert _observed(date(2026, 7, 4)) == date(2026, 7, 3)

    def test_sunday_observed_monday(self):
        """Holiday on Sunday is observed on following Monday."""
        # Juneteenth 2027: June 19 is Saturday
        # Let's test a Sunday case: Jan 1, 2023 is Sunday
        assert _observed(date(2023, 1, 1)) == date(2023, 1, 2)

    def test_weekday_unchanged(self):
        """Holiday on a weekday stays on that day."""
        # Jan 1, 2026 is Thursday
        assert _observed(date(2026, 1, 1)) == date(2026, 1, 1)


class TestNthWeekday:
    """Test nth weekday calculator."""

    def test_third_monday_jan_2026(self):
        """3rd Monday in January 2026 = Jan 19."""
        assert _nth_weekday(2026, 1, 0, 3) == date(2026, 1, 19)

    def test_first_monday_sep_2026(self):
        """1st Monday in September 2026 = Sep 7."""
        assert _nth_weekday(2026, 9, 0, 1) == date(2026, 9, 7)

    def test_fourth_thursday_nov_2026(self):
        """4th Thursday in November 2026 = Nov 26."""
        assert _nth_weekday(2026, 11, 3, 4) == date(2026, 11, 26)


class TestLastWeekday:
    """Test last weekday calculator."""

    def test_last_monday_may_2026(self):
        """Last Monday in May 2026 = May 25."""
        assert _last_weekday(2026, 5, 0) == date(2026, 5, 25)

    def test_last_monday_may_2027(self):
        """Last Monday in May 2027 = May 31."""
        assert _last_weekday(2027, 5, 0) == date(2027, 5, 31)


class TestIsBusinessDay:
    """Test is_business_day."""

    def test_weekday_non_holiday(self):
        """A regular Wednesday should be a business day."""
        # May 14, 2026 is Wednesday (not a holiday)
        assert is_business_day(date(2026, 5, 14)) is True

    def test_saturday(self):
        """Saturday is not a business day."""
        assert is_business_day(date(2026, 5, 16)) is False

    def test_sunday(self):
        """Sunday is not a business day."""
        assert is_business_day(date(2026, 5, 17)) is False

    def test_federal_holiday(self):
        """Federal holiday is not a business day."""
        # MLK Day 2026 = Jan 19 (Monday)
        assert is_business_day(date(2026, 1, 19)) is False

    def test_custom_holiday(self):
        """Custom org-level holiday should not be a business day."""
        custom = frozenset({date(2026, 5, 14)})
        assert is_business_day(date(2026, 5, 14), custom) is False

    def test_christmas_eve_is_business_day(self):
        """Dec 24, 2026 (Thursday) is a business day (not a federal holiday)."""
        assert is_business_day(date(2026, 12, 24)) is True


class TestAddBusinessDays:
    """Test add_business_days."""

    def test_add_3_from_monday(self):
        """Adding 3 business days from Monday should give Thursday."""
        # May 11, 2026 is Monday
        result = add_business_days(date(2026, 5, 11), 3)
        assert result == date(2026, 5, 14)  # Thursday

    def test_add_3_over_weekend(self):
        """Adding 3 business days from Thursday should skip weekend."""
        # May 14, 2026 is Thursday
        result = add_business_days(date(2026, 5, 14), 3)
        assert result == date(2026, 5, 19)  # Tuesday (next week)

    def test_add_3_over_holiday(self):
        """Adding business days should skip holidays."""
        # Jan 16, 2026 is Friday. Jan 19 is MLK Day (Monday).
        # 3 business days from Jan 16: skip weekend + MLK = Jan 22 (Thursday)
        result = add_business_days(date(2026, 1, 16), 3)
        assert result == date(2026, 1, 22)

    def test_add_0_days(self):
        """Adding 0 business days should return the same date (if business day)."""
        result = add_business_days(date(2026, 5, 14), 0)
        assert result == date(2026, 5, 14)

    def test_add_0_from_weekend(self):
        """Adding 0 business days from Saturday should advance to Monday."""
        result = add_business_days(date(2026, 5, 16), 0)
        assert result == date(2026, 5, 18)  # Monday

    def test_add_across_year_boundary(self):
        """Adding business days across year boundary."""
        # Dec 31, 2026 is Thursday. Jan 1, 2027 is Friday (New Year's Day holiday).
        # Jan 2-3 is weekend. Next business day = Jan 4 (Monday).
        result = add_business_days(date(2026, 12, 31), 1)
        assert result == date(2027, 1, 4)

    def test_negative_raises(self):
        """Negative num_days should raise ValueError."""
        with pytest.raises(ValueError):
            add_business_days(date(2026, 5, 14), -1)


class TestSubtractBusinessDays:
    """Test subtract_business_days."""

    def test_subtract_3_from_thursday(self):
        """Subtracting 3 business days from Thursday gives Monday (prev week)."""
        # May 14, 2026 is Thursday
        result = subtract_business_days(date(2026, 5, 14), 3)
        assert result == date(2026, 5, 11)  # Monday

    def test_subtract_3_over_weekend(self):
        """Subtracting 3 business days from Tuesday should skip weekend."""
        # May 19, 2026 is Tuesday
        result = subtract_business_days(date(2026, 5, 19), 3)
        assert result == date(2026, 5, 14)  # Thursday (prev week)

    def test_subtract_3_over_holiday(self):
        """Subtracting business days should skip holidays."""
        # Jan 22, 2026 is Thursday. Jan 19 is MLK Day.
        # 3 business days back: Jan 21 (Wed), Jan 20 (Tue), Jan 16 (Fri)
        result = subtract_business_days(date(2026, 1, 22), 3)
        assert result == date(2026, 1, 16)  # Friday

    def test_negative_raises(self):
        """Negative num_days should raise ValueError."""
        with pytest.raises(ValueError):
            subtract_business_days(date(2026, 5, 14), -1)


class TestCountBusinessDays:
    """Test count_business_days."""

    def test_same_date(self):
        """Same start and end returns 0."""
        assert count_business_days(date(2026, 5, 14), date(2026, 5, 14)) == 0

    def test_consecutive_weekdays(self):
        """Monday to Wednesday has 1 business day between (Tuesday)."""
        # Mon May 11 to Wed May 13 -> 1 bday (Tue May 12)
        assert count_business_days(date(2026, 5, 11), date(2026, 5, 13)) == 1

    def test_over_weekend(self):
        """Thursday to Tuesday should count 1 (Friday only between)."""
        # Thu May 14 to Tue May 19 -> Fri May 15, Sat/Sun skip, Mon May 18
        assert count_business_days(date(2026, 5, 14), date(2026, 5, 19)) == 2

    def test_full_week(self):
        """Monday to next Monday has 4 business days between."""
        # Mon May 11 to Mon May 18 -> Tue-Fri = 4
        assert count_business_days(date(2026, 5, 11), date(2026, 5, 18)) == 4

    def test_negative_range(self):
        """End before start returns negative count."""
        result = count_business_days(date(2026, 5, 14), date(2026, 5, 11))
        assert result < 0


# ---------------------------------------------------------------------------
# TRID Engine Tests
# ---------------------------------------------------------------------------

from services.compliance.trid import (
    TRIDEngine,
    ToleranceBucket,
    ChangedCircumstanceType,
)


class TestTRIDEngine:
    """Test TRID deadline calculations."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_le_deadline_3_business_days(self):
        """LE deadline should be 3 business days from application."""
        # Application: Monday May 11, 2026
        result = self.engine.calculate_le_deadline(date(2026, 5, 11))
        assert result.le_deadline == date(2026, 5, 14)  # Thursday

    def test_le_deadline_over_weekend(self):
        """LE deadline should skip weekends."""
        # Application: Thursday May 14, 2026
        result = self.engine.calculate_le_deadline(date(2026, 5, 14))
        assert result.le_deadline == date(2026, 5, 19)  # Tuesday

    def test_le_compliant(self):
        """LE delivered on time should be compliant."""
        result = self.engine.calculate_le_deadline(
            date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 13),  # Wednesday (within 3 bdays)
        )
        assert result.is_compliant is True

    def test_le_violation(self):
        """LE delivered late should be a violation."""
        result = self.engine.calculate_le_deadline(
            date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 20),  # The following Wednesday
        )
        assert result.is_compliant is False

    def test_le_deadline_over_holiday(self):
        """LE deadline should skip holidays."""
        # Application: Friday Jan 16, 2026. MLK Day is Mon Jan 19.
        result = self.engine.calculate_le_deadline(date(2026, 1, 16))
        # 3 bdays: skip weekend + MLK Mon = Tue Jan 20, Wed Jan 21, Thu Jan 22
        assert result.le_deadline == date(2026, 1, 22)

    def test_cd_deadline_3_business_days_before_closing(self):
        """CD must be delivered 3 business days before closing."""
        # Closing: Friday May 22, 2026
        result = self.engine.calculate_cd_deadline(date(2026, 5, 22))
        # 3 bdays back from Fri: Thu May 21, Wed May 20, Tue May 19
        assert result.cd_delivery_deadline == date(2026, 5, 19)

    def test_cd_compliant(self):
        """CD delivered on time should be compliant."""
        result = self.engine.calculate_cd_deadline(
            closing_date=date(2026, 5, 22),
            cd_delivered_date=date(2026, 5, 18),  # Monday (4 bdays before)
        )
        assert result.is_compliant is True

    def test_cd_violation(self):
        """CD delivered too late should be a violation."""
        result = self.engine.calculate_cd_deadline(
            closing_date=date(2026, 5, 22),
            cd_delivered_date=date(2026, 5, 21),  # Thursday (only 1 bday before)
        )
        assert result.is_compliant is False

    def test_cd_waiting_period_satisfied(self):
        """Closing 4+ business days after CD should be allowed."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 11),  # Monday
            proposed_closing_date=date(2026, 5, 18),  # Next Monday
        )
        assert result.can_close is True
        assert result.business_days_between >= 3

    def test_cd_waiting_period_not_met(self):
        """Closing < 3 business days after CD should be blocked."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 14),  # Thursday
            proposed_closing_date=date(2026, 5, 15),  # Friday (1 bday)
        )
        assert result.can_close is False

    def test_cd_waiting_period_earliest_closing(self):
        """Should calculate the earliest allowed closing date."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 14),  # Thursday
            proposed_closing_date=date(2026, 5, 15),
        )
        # 3 bdays from Thursday = skip Fri, skip weekend, Mon, Tue, Wed
        # Actually: Fri, Mon, Tue = 3 bdays
        assert result.earliest_allowed_closing == date(2026, 5, 19)

    def test_re_disclosure_deadline(self):
        """Re-disclosure deadline should be 3 business days from change."""
        result = self.engine.check_re_disclosure(
            circumstance_type=ChangedCircumstanceType.RATE_CHANGE,
            circumstance_date=date(2026, 5, 14),  # Thursday
        )
        assert result.re_disclosure_deadline == date(2026, 5, 19)  # Tuesday

    def test_fee_classification_zero_tolerance(self):
        """Origination charge should be zero tolerance."""
        result = self.engine.classify_fee("origination_charge")
        assert result.bucket == ToleranceBucket.ZERO

    def test_fee_classification_ten_percent(self):
        """Appraisal fee should be 10% tolerance."""
        result = self.engine.classify_fee("appraisal_fee")
        assert result.bucket == ToleranceBucket.TEN_PERCENT

    def test_fee_classification_unlimited(self):
        """Homeowners insurance should be unlimited tolerance."""
        result = self.engine.classify_fee("homeowners_insurance")
        assert result.bucket == ToleranceBucket.UNLIMITED

    def test_fee_classification_unknown_defaults_unlimited(self):
        """Unknown fee should default to unlimited tolerance."""
        result = self.engine.classify_fee("mystery_fee")
        assert result.bucket == ToleranceBucket.UNLIMITED

    def test_full_trid_check_all_compliant(self):
        """Full TRID check with all dates compliant."""
        report = self.engine.full_trid_check(
            application_date=date(2026, 5, 11),
            closing_date=date(2026, 5, 29),
            le_delivered_date=date(2026, 5, 12),
            cd_delivered_date=date(2026, 5, 22),
        )
        assert report.overall_compliant is True
        assert len(report.issues) == 0

    def test_full_trid_check_le_violation(self):
        """Full TRID check with LE violation."""
        report = self.engine.full_trid_check(
            application_date=date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 20),  # Late
        )
        assert report.overall_compliant is False
        assert len(report.issues) >= 1

    def test_audit_metadata_present(self):
        """All results should include audit metadata."""
        result = self.engine.calculate_le_deadline(date(2026, 5, 11))
        assert result.audit is not None
        assert result.audit.rule == "LE 3-business-day delivery"
        assert "1026.19" in result.audit.regulation
        assert "application_date" in result.audit.inputs


# ---------------------------------------------------------------------------
# ECOA Engine Tests
# ---------------------------------------------------------------------------

from services.compliance.ecoa import ECOAEngine, AdverseActionStatus, UrgencyLevel


class TestECOAEngine:
    """Test ECOA deadline calculations."""

    def setup_method(self):
        self.engine = ECOAEngine()

    def test_adverse_action_30_days(self):
        """Adverse action deadline should be 30 calendar days from denial."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 5, 1))
        assert result.notice_deadline == date(2026, 5, 31)

    def test_adverse_action_compliant(self):
        """Notice sent within 30 days should be compliant."""
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 15),
        )
        assert result.is_compliant is True
        assert result.status == AdverseActionStatus.COMPLIANT

    def test_adverse_action_violation(self):
        """Notice sent after 30 days should be a violation."""
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 6, 5),  # 35 days later
        )
        assert result.is_compliant is False
        assert result.status == AdverseActionStatus.VIOLATION

    @patch("services.compliance.ecoa.date")
    def test_adverse_action_overdue(self, mock_date):
        """Unsent notice past deadline should be overdue."""
        mock_date.today.return_value = date(2026, 7, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
        )
        assert result.status == AdverseActionStatus.OVERDUE
        assert result.urgency == UrgencyLevel.OVERDUE

    def test_counteroffer_90_day_window(self):
        """Counteroffer response deadline should be 90 calendar days."""
        result = self.engine.calculate_counteroffer_deadline(date(2026, 5, 1))
        assert result.response_deadline == date(2026, 7, 30)

    def test_counteroffer_response_in_window(self):
        """Response within 90 days should be within window."""
        result = self.engine.calculate_counteroffer_deadline(
            counteroffer_date=date(2026, 5, 1),
            response_received_date=date(2026, 6, 15),
        )
        assert result.is_within_window is True

    def test_counteroffer_response_late(self):
        """Response after 90 days should be outside window."""
        result = self.engine.calculate_counteroffer_deadline(
            counteroffer_date=date(2026, 5, 1),
            response_received_date=date(2026, 8, 15),  # > 90 days
        )
        assert result.is_within_window is False

    def test_full_ecoa_check(self):
        """Full ECOA check with denial date should produce report."""
        report = self.engine.full_ecoa_check(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 15),
        )
        assert report.overall_compliant is True
        assert report.adverse_action is not None
        assert report.adverse_action.is_compliant is True

    def test_ecoa_audit_metadata(self):
        """ECOA results should include audit metadata."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 5, 1))
        assert result.audit is not None
        assert "1002.9" in result.audit.regulation


# ---------------------------------------------------------------------------
# TCPA Checker Tests
# ---------------------------------------------------------------------------

from services.compliance.tcpa import TCPAChecker


class TestTCPAChecker:
    """Test TCPA time-of-day checks."""

    def setup_method(self):
        self.checker = TCPAChecker()

    def test_timezone_resolution_from_phone(self):
        """Should resolve timezone from US area code."""
        tz = self.checker._resolve_timezone(phone="+12125551234")
        assert tz == "America/New_York"

    def test_timezone_resolution_pacific(self):
        """Should resolve West Coast timezone."""
        tz = self.checker._resolve_timezone(phone="4155551234")
        assert tz == "America/Los_Angeles"

    def test_timezone_resolution_central(self):
        """Should resolve Central timezone."""
        tz = self.checker._resolve_timezone(phone="3125551234")
        assert tz == "America/Chicago"

    def test_timezone_resolution_mountain(self):
        """Should resolve Mountain timezone."""
        tz = self.checker._resolve_timezone(phone="3035551234")
        assert tz == "America/Denver"

    def test_timezone_explicit_overrides_phone(self):
        """Explicit tz_id should take priority over phone."""
        tz = self.checker._resolve_timezone(
            tz_id="America/Chicago",
            phone="+12125551234",  # NYC area code
        )
        assert tz == "America/Chicago"

    def test_unknown_area_code(self):
        """Unknown area code should return None."""
        tz = self.checker._resolve_timezone(phone="0005551234")
        assert tz is None

    def test_can_contact_no_timezone(self):
        """Should block contact when timezone cannot be determined."""
        result = self.checker.can_contact_now(phone="0005551234")
        assert result.can_contact is False
        assert "Cannot determine" in result.message

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_can_contact_during_window(self, mock_now):
        """Should allow contact during 8 AM - 9 PM window."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 14, 30, 0, tzinfo=tz)  # 2:30 PM

        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is True

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_cannot_contact_before_window(self, mock_now):
        """Should block contact before 8 AM."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 6, 30, 0, tzinfo=tz)  # 6:30 AM

        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_cannot_contact_after_window(self, mock_now):
        """Should block contact after 9 PM."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 21, 30, 0, tzinfo=tz)  # 9:30 PM

        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_window_boundary_8am(self, mock_now):
        """Exactly 8:00 AM should be allowed."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 8, 0, 0, tzinfo=tz)

        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is True

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_window_boundary_9pm(self, mock_now):
        """Exactly 9:00 PM (21:00) should NOT be allowed."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 21, 0, 0, tzinfo=tz)

        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    def test_check_contact_at_specific_time(self):
        """check_contact_at_time should validate a specific datetime."""
        # 2 PM Eastern = within window
        contact_time = datetime(2026, 5, 14, 18, 0, 0, tzinfo=timezone.utc)  # 2 PM ET
        assert self.checker.check_contact_at_time(
            contact_time, "America/New_York"
        ) is True

    def test_check_contact_at_specific_time_early(self):
        """Early morning UTC should be outside window in Eastern."""
        contact_time = datetime(2026, 5, 14, 5, 0, 0, tzinfo=timezone.utc)  # 1 AM ET
        assert self.checker.check_contact_at_time(
            contact_time, "America/New_York"
        ) is False

    def test_next_contact_window(self):
        """next_contact_window should return structured result."""
        result = self.checker.next_contact_window(tz_id="America/New_York")
        assert result.timezone_id == "America/New_York"
        assert result.window_opens_utc != "unknown"

    def test_tcpa_audit_metadata(self):
        """TCPA results should include audit metadata."""
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.audit is not None
        assert "64.1200" in result.audit.regulation


# ---------------------------------------------------------------------------
# Integration / Edge Case Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and cross-boundary scenarios."""

    def test_trid_le_deadline_friday_application(self):
        """Application on Friday: 3 bdays = next Wednesday."""
        engine = TRIDEngine()
        # Friday May 15, 2026
        result = engine.calculate_le_deadline(date(2026, 5, 15))
        # Skip weekend: Mon, Tue, Wed = 3 bdays
        assert result.le_deadline == date(2026, 5, 20)

    def test_trid_cd_deadline_monday_closing(self):
        """Closing on Monday: CD due 3 bdays before = prior Wednesday."""
        engine = TRIDEngine()
        # Monday May 18, 2026
        result = engine.calculate_cd_deadline(date(2026, 5, 18))
        # 3 bdays back: Fri May 15, Thu May 14, Wed May 13
        assert result.cd_delivery_deadline == date(2026, 5, 13)

    def test_business_days_across_thanksgiving(self):
        """Business day calculation should handle Thanksgiving week."""
        # Thanksgiving 2026 = Nov 26 (Thursday)
        # Count bdays between Nov 23 (Mon) and Nov 30 (Mon)
        # Nov 24 (Tue), Nov 25 (Wed), Nov 26 (HOLIDAY), Nov 27 (Fri) = 3
        count = count_business_days(date(2026, 11, 23), date(2026, 11, 30))
        assert count == 3

    def test_ecoa_deadline_across_month(self):
        """ECOA 30-day deadline crossing month boundary."""
        engine = ECOAEngine()
        result = engine.calculate_adverse_action_deadline(date(2026, 1, 15))
        assert result.notice_deadline == date(2026, 2, 14)

    def test_ecoa_deadline_february_leap_year(self):
        """ECOA deadline in February of a non-leap year."""
        engine = ECOAEngine()
        # Feb 1, 2026 + 30 days = Mar 3
        result = engine.calculate_adverse_action_deadline(date(2026, 2, 1))
        assert result.notice_deadline == date(2026, 3, 3)

    def test_multiple_holidays_in_sequence(self):
        """Business day calculation with multiple sequential holidays."""
        # Custom holidays to simulate multi-day closure
        custom = frozenset({
            date(2026, 12, 24),  # Christmas Eve
        })
        # Dec 23 (Wed) + 3 bdays:
        # Dec 24 (custom holiday), Dec 25 (Christmas/holiday), Dec 26-27 (Sat-Sun)
        # Dec 28 (Mon) = 1, Dec 29 (Tue) = 2, Dec 30 (Wed) = 3
        result = add_business_days(date(2026, 12, 23), 3, custom)
        assert result == date(2026, 12, 30)
