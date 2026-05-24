"""
Comprehensive Compliance Engine Test Suite
===========================================
Tests the deterministic compliance calculation engine covering:
    - TRID: LE delivery deadline (3 business days from application)
    - TRID: CD delivery deadline (3 business days before closing)
    - TRID: Business day calculation (weekends, federal holidays)
    - TRID: Fee tolerance buckets (0%, 10%, unlimited)
    - TRID: Changed circumstance re-disclosure
    - TRID: CD waiting period enforcement
    - ECOA: Adverse action notice deadline (30 calendar days)
    - ECOA: Counteroffer response window (90 calendar days)
    - ECOA: Full compliance report
    - TCPA: Contact window enforcement (8am-9pm callee local time)
    - TCPA: Timezone resolution from area code
    - TCPA: Boundary conditions (exactly 8am, exactly 9pm)
    - TCPA: Next contact window calculation
    - Cross-boundary edge cases (year, month, holiday sequences)

All tests are pure/deterministic -- no DB or LLM needed.
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
    _observed,
)


@pytest.mark.unit
class TestBusinessDayArithmetic:
    """Test business day calculations with weekends and holidays."""

    def test_add_3_from_monday(self):
        """3 business days from Monday = Thursday."""
        assert add_business_days(date(2026, 5, 11), 3) == date(2026, 5, 14)

    def test_add_3_over_weekend(self):
        """3 business days from Thursday skips weekend = Tuesday."""
        assert add_business_days(date(2026, 5, 14), 3) == date(2026, 5, 19)

    def test_add_3_over_holiday(self):
        """3 business days from Friday before MLK Day skips weekend + holiday."""
        # Jan 16 (Fri) -> Jan 19 (MLK), Jan 20 (Tue), Jan 21 (Wed), Jan 22 (Thu)
        assert add_business_days(date(2026, 1, 16), 3) == date(2026, 1, 22)

    def test_add_0_returns_same_date(self):
        """Adding 0 business days to a business day returns the same date."""
        assert add_business_days(date(2026, 5, 14), 0) == date(2026, 5, 14)

    def test_add_0_from_weekend_advances_to_monday(self):
        """Adding 0 business days from Saturday advances to Monday."""
        assert add_business_days(date(2026, 5, 16), 0) == date(2026, 5, 18)

    def test_add_across_year_boundary(self):
        """Adding business days across year boundary (Dec 31 -> Jan)."""
        # Dec 31 (Thu) + 1 bday: Jan 1 (New Year holiday), Jan 2-3 (weekend Fri-Sat)
        # wait, let me recalculate: Dec 31, 2026 = Thu, Jan 1, 2027 = Fri (holiday),
        # Jan 2 (Sat), Jan 3 (Sun), Jan 4 (Mon) -> next business day
        # HOWEVER Jan 1, 2027 is Thursday not Friday. Let me check.
        # Actually in 2027, Jan 1 is a Friday. So:
        # Dec 31 Thu + 1 = Jan 2? No, Jan 1 is holiday (Fri), Jan 2 is Sat, Jan 3 Sun
        # Next business day = Jan 4 Mon
        result = add_business_days(date(2026, 12, 31), 1)
        assert result == date(2027, 1, 4)

    def test_add_negative_raises(self):
        """Negative days should raise ValueError."""
        with pytest.raises(ValueError):
            add_business_days(date(2026, 5, 14), -1)

    def test_subtract_3_from_thursday(self):
        """3 business days back from Thursday = Monday."""
        assert subtract_business_days(date(2026, 5, 14), 3) == date(2026, 5, 11)

    def test_subtract_3_over_weekend(self):
        """3 business days back from Tuesday skips weekend = Thursday."""
        assert subtract_business_days(date(2026, 5, 19), 3) == date(2026, 5, 14)

    def test_subtract_over_holiday(self):
        """3 business days back from Thursday after MLK Day."""
        # Jan 22 (Thu) back 3: Jan 21 (Wed), Jan 20 (Tue), Jan 19 (MLK skip), Jan 16 (Fri)
        assert subtract_business_days(date(2026, 1, 22), 3) == date(2026, 1, 16)

    def test_count_same_date(self):
        """Same start and end returns 0."""
        assert count_business_days(date(2026, 5, 14), date(2026, 5, 14)) == 0

    def test_count_over_weekend(self):
        """Thursday to Tuesday: Fri + Mon = 2 business days between."""
        assert count_business_days(date(2026, 5, 14), date(2026, 5, 19)) == 2

    def test_count_full_week(self):
        """Monday to next Monday: 4 business days between."""
        assert count_business_days(date(2026, 5, 11), date(2026, 5, 18)) == 4


@pytest.mark.unit
class TestFederalHolidays:
    """Test federal holiday computation."""

    def test_2026_has_11_holidays(self):
        """2026 should have 11 federal holidays."""
        assert len(compute_federal_holidays(2026)) == 11

    def test_new_years_day(self):
        """New Year's Day 2026 is Jan 1 (Thursday)."""
        assert date(2026, 1, 1) in compute_federal_holidays(2026)

    def test_mlk_day(self):
        """MLK Day 2026 is 3rd Monday = Jan 19."""
        assert date(2026, 1, 19) in compute_federal_holidays(2026)

    def test_independence_day_saturday_observed_friday(self):
        """July 4, 2026 (Saturday) observed on Friday July 3."""
        holidays = compute_federal_holidays(2026)
        assert date(2026, 7, 3) in holidays
        assert date(2026, 7, 4) not in holidays

    def test_christmas_day(self):
        """Christmas 2026 is Friday Dec 25."""
        assert date(2026, 12, 25) in compute_federal_holidays(2026)

    def test_holiday_caching(self):
        """get_federal_holidays caches results (same object)."""
        h1 = get_federal_holidays(2026)
        h2 = get_federal_holidays(2026)
        assert h1 is h2

    def test_observed_saturday_to_friday(self):
        """Saturday holiday observed on preceding Friday."""
        assert _observed(date(2026, 7, 4)) == date(2026, 7, 3)

    def test_observed_sunday_to_monday(self):
        """Sunday holiday observed on following Monday."""
        assert _observed(date(2023, 1, 1)) == date(2023, 1, 2)

    def test_observed_weekday_unchanged(self):
        """Weekday holiday stays on that day."""
        assert _observed(date(2026, 1, 1)) == date(2026, 1, 1)


@pytest.mark.unit
class TestIsBusinessDay:
    """Test is_business_day function."""

    def test_regular_wednesday(self):
        """Regular Wednesday is a business day."""
        assert is_business_day(date(2026, 5, 14)) is True

    def test_saturday_not_business_day(self):
        """Saturday is not a business day."""
        assert is_business_day(date(2026, 5, 16)) is False

    def test_sunday_not_business_day(self):
        """Sunday is not a business day."""
        assert is_business_day(date(2026, 5, 17)) is False

    def test_federal_holiday_not_business_day(self):
        """MLK Day is not a business day."""
        assert is_business_day(date(2026, 1, 19)) is False

    def test_custom_holiday_not_business_day(self):
        """Custom org-level holiday is not a business day."""
        custom = frozenset({date(2026, 5, 14)})
        assert is_business_day(date(2026, 5, 14), custom) is False

    def test_christmas_eve_is_business_day(self):
        """Christmas Eve (Dec 24) is NOT a federal holiday."""
        assert is_business_day(date(2026, 12, 24)) is True


# ---------------------------------------------------------------------------
# TRID Engine Tests
# ---------------------------------------------------------------------------

from services.compliance.trid import (
    TRIDEngine,
    ToleranceBucket,
    ChangedCircumstanceType,
    ZERO_TOLERANCE_FEES,
    TEN_PERCENT_TOLERANCE_FEES,
    UNLIMITED_TOLERANCE_FEES,
)


@pytest.mark.unit
class TestTRIDLEDeadline:
    """Test TRID Loan Estimate deadline calculations."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_le_deadline_3_business_days(self):
        """LE deadline is 3 business days from application date."""
        result = self.engine.calculate_le_deadline(date(2026, 5, 11))
        assert result.le_deadline == date(2026, 5, 14)

    def test_le_deadline_skips_weekend(self):
        """LE deadline skips weekends."""
        result = self.engine.calculate_le_deadline(date(2026, 5, 14))
        assert result.le_deadline == date(2026, 5, 19)

    def test_le_deadline_skips_holiday(self):
        """LE deadline skips MLK Day."""
        result = self.engine.calculate_le_deadline(date(2026, 1, 16))
        assert result.le_deadline == date(2026, 1, 22)

    def test_le_compliant_when_delivered_on_time(self):
        """LE delivered within deadline is compliant."""
        result = self.engine.calculate_le_deadline(
            date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 13),
        )
        assert result.is_compliant is True

    def test_le_violation_when_delivered_late(self):
        """LE delivered after deadline is a violation."""
        result = self.engine.calculate_le_deadline(
            date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 20),
        )
        assert result.is_compliant is False

    def test_le_friday_application(self):
        """Application on Friday: 3 bdays = next Wednesday."""
        result = self.engine.calculate_le_deadline(date(2026, 5, 15))
        assert result.le_deadline == date(2026, 5, 20)

    def test_le_audit_metadata(self):
        """LE result includes audit metadata with rule and regulation."""
        result = self.engine.calculate_le_deadline(date(2026, 5, 11))
        assert result.audit is not None
        assert result.audit.rule == "LE 3-business-day delivery"
        assert "1026.19" in result.audit.regulation
        assert "application_date" in result.audit.inputs


@pytest.mark.unit
class TestTRIDCDDeadline:
    """Test TRID Closing Disclosure deadline calculations."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_cd_deadline_3_business_days_before_closing(self):
        """CD must be delivered 3 business days before closing."""
        result = self.engine.calculate_cd_deadline(date(2026, 5, 22))
        assert result.cd_delivery_deadline == date(2026, 5, 19)

    def test_cd_compliant(self):
        """CD delivered before deadline is compliant."""
        result = self.engine.calculate_cd_deadline(
            closing_date=date(2026, 5, 22),
            cd_delivered_date=date(2026, 5, 18),
        )
        assert result.is_compliant is True

    def test_cd_violation(self):
        """CD delivered too late is a violation."""
        result = self.engine.calculate_cd_deadline(
            closing_date=date(2026, 5, 22),
            cd_delivered_date=date(2026, 5, 21),
        )
        assert result.is_compliant is False

    def test_cd_monday_closing(self):
        """Closing on Monday: CD due Wednesday prior."""
        result = self.engine.calculate_cd_deadline(date(2026, 5, 18))
        assert result.cd_delivery_deadline == date(2026, 5, 13)


@pytest.mark.unit
class TestTRIDCDWaitingPeriod:
    """Test TRID CD 3-business-day waiting period."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_waiting_period_satisfied(self):
        """Closing 4+ business days after CD should be allowed."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 11),
            proposed_closing_date=date(2026, 5, 18),
        )
        assert result.can_close is True
        assert result.business_days_between >= 3

    def test_waiting_period_not_met(self):
        """Closing < 3 business days after CD should be blocked."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 14),
            proposed_closing_date=date(2026, 5, 15),
        )
        assert result.can_close is False

    def test_earliest_allowed_closing(self):
        """Should calculate earliest allowed closing date."""
        result = self.engine.check_cd_waiting_period(
            cd_delivery_date=date(2026, 5, 14),
            proposed_closing_date=date(2026, 5, 15),
        )
        assert result.earliest_allowed_closing == date(2026, 5, 19)


@pytest.mark.unit
class TestTRIDFeeTolerance:
    """Test TRID fee tolerance bucket classification."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_origination_charge_zero_tolerance(self):
        """Origination charge is zero tolerance."""
        result = self.engine.classify_fee("origination_charge")
        assert result.bucket == ToleranceBucket.ZERO

    def test_appraisal_fee_ten_percent(self):
        """Appraisal fee is 10% tolerance."""
        result = self.engine.classify_fee("appraisal_fee")
        assert result.bucket == ToleranceBucket.TEN_PERCENT

    def test_homeowners_insurance_unlimited(self):
        """Homeowners insurance is unlimited tolerance."""
        result = self.engine.classify_fee("homeowners_insurance")
        assert result.bucket == ToleranceBucket.UNLIMITED

    def test_unknown_fee_defaults_unlimited(self):
        """Unknown fee defaults to unlimited tolerance."""
        result = self.engine.classify_fee("mystery_fee")
        assert result.bucket == ToleranceBucket.UNLIMITED

    def test_zero_tolerance_fees_complete(self):
        """All zero-tolerance fees should be in the constant set."""
        assert "origination_charge" in ZERO_TOLERANCE_FEES
        assert "discount_points" in ZERO_TOLERANCE_FEES
        assert "lender_credits" in ZERO_TOLERANCE_FEES

    def test_ten_percent_fees_complete(self):
        """All 10% tolerance fees should be in the constant set."""
        assert "appraisal_fee" in TEN_PERCENT_TOLERANCE_FEES
        assert "credit_report_fee" in TEN_PERCENT_TOLERANCE_FEES

    def test_unlimited_fees_complete(self):
        """All unlimited tolerance fees should be in the constant set."""
        assert "homeowners_insurance" in UNLIMITED_TOLERANCE_FEES
        assert "prepaid_interest" in UNLIMITED_TOLERANCE_FEES


@pytest.mark.unit
class TestTRIDReDisclosure:
    """Test TRID changed circumstance re-disclosure."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_re_disclosure_deadline(self):
        """Re-disclosure deadline is 3 business days from change."""
        result = self.engine.check_re_disclosure(
            circumstance_type=ChangedCircumstanceType.RATE_CHANGE,
            circumstance_date=date(2026, 5, 14),
        )
        assert result.re_disclosure_deadline == date(2026, 5, 19)


@pytest.mark.unit
class TestTRIDFullCheck:
    """Test full TRID compliance check."""

    def setup_method(self):
        self.engine = TRIDEngine()

    def test_all_compliant(self):
        """Full check with all dates compliant produces no issues."""
        report = self.engine.full_trid_check(
            application_date=date(2026, 5, 11),
            closing_date=date(2026, 5, 29),
            le_delivered_date=date(2026, 5, 12),
            cd_delivered_date=date(2026, 5, 22),
        )
        assert report.overall_compliant is True
        assert len(report.issues) == 0

    def test_le_violation_detected(self):
        """Full check detects LE violation."""
        report = self.engine.full_trid_check(
            application_date=date(2026, 5, 11),
            le_delivered_date=date(2026, 5, 20),
        )
        assert report.overall_compliant is False
        assert len(report.issues) >= 1


# ---------------------------------------------------------------------------
# ECOA Engine Tests
# ---------------------------------------------------------------------------

from services.compliance.ecoa import ECOAEngine, AdverseActionStatus, UrgencyLevel


@pytest.mark.unit
class TestECOAAdverseAction:
    """Test ECOA adverse action notice deadline (30 calendar days)."""

    def setup_method(self):
        self.engine = ECOAEngine()

    def test_deadline_30_calendar_days(self):
        """Deadline is exactly 30 calendar days from denial."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 5, 1))
        assert result.notice_deadline == date(2026, 5, 31)

    def test_compliant_notice_sent_within_deadline(self):
        """Notice sent within 30 days is compliant."""
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 15),
        )
        assert result.is_compliant is True
        assert result.status == AdverseActionStatus.COMPLIANT

    def test_violation_notice_sent_after_deadline(self):
        """Notice sent after 30 days is a violation."""
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 6, 5),
        )
        assert result.is_compliant is False
        assert result.status == AdverseActionStatus.VIOLATION

    def test_notice_sent_on_deadline_day_compliant(self):
        """Notice sent exactly on the 30th day is compliant."""
        result = self.engine.calculate_adverse_action_deadline(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 31),
        )
        assert result.is_compliant is True

    @patch("services.compliance.ecoa.date")
    def test_overdue_status(self, mock_date):
        """Unsent notice past deadline should be overdue."""
        mock_date.today.return_value = date(2026, 7, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = self.engine.calculate_adverse_action_deadline(date(2026, 5, 1))
        assert result.status == AdverseActionStatus.OVERDUE
        assert result.urgency == UrgencyLevel.OVERDUE

    def test_deadline_across_month_boundary(self):
        """30-day deadline crossing month boundary."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 1, 15))
        assert result.notice_deadline == date(2026, 2, 14)

    def test_deadline_february_non_leap_year(self):
        """30-day deadline in February of non-leap year."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 2, 1))
        assert result.notice_deadline == date(2026, 3, 3)

    def test_audit_metadata_includes_regulation(self):
        """ECOA result includes regulation reference."""
        result = self.engine.calculate_adverse_action_deadline(date(2026, 5, 1))
        assert "1002.9" in result.audit.regulation


@pytest.mark.unit
class TestECOACounteroffer:
    """Test ECOA counteroffer response window (90 calendar days)."""

    def setup_method(self):
        self.engine = ECOAEngine()

    def test_counteroffer_90_day_window(self):
        """Response deadline is 90 calendar days from counteroffer."""
        result = self.engine.calculate_counteroffer_deadline(date(2026, 5, 1))
        assert result.response_deadline == date(2026, 7, 30)

    def test_response_within_window(self):
        """Response within 90 days is within window."""
        result = self.engine.calculate_counteroffer_deadline(
            counteroffer_date=date(2026, 5, 1),
            response_received_date=date(2026, 6, 15),
        )
        assert result.is_within_window is True

    def test_response_after_window(self):
        """Response after 90 days is outside window."""
        result = self.engine.calculate_counteroffer_deadline(
            counteroffer_date=date(2026, 5, 1),
            response_received_date=date(2026, 8, 15),
        )
        assert result.is_within_window is False


@pytest.mark.unit
class TestECOAFullCheck:
    """Test full ECOA compliance check."""

    def setup_method(self):
        self.engine = ECOAEngine()

    def test_full_check_compliant(self):
        """Full ECOA check with compliant dates produces no issues."""
        report = self.engine.full_ecoa_check(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 15),
        )
        assert report.overall_compliant is True
        assert report.adverse_action is not None
        assert report.adverse_action.is_compliant is True

    def test_full_check_with_violation(self):
        """Full ECOA check with late notice produces issues."""
        report = self.engine.full_ecoa_check(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 6, 5),
        )
        assert report.overall_compliant is False
        assert len(report.issues) >= 1

    def test_full_check_with_counteroffer(self):
        """Full ECOA check includes counteroffer analysis."""
        report = self.engine.full_ecoa_check(
            counteroffer_date=date(2026, 5, 1),
            counteroffer_response_date=date(2026, 6, 15),
        )
        assert report.counteroffer is not None
        assert report.counteroffer.is_within_window is True


# ---------------------------------------------------------------------------
# TCPA Checker Tests
# ---------------------------------------------------------------------------

from services.compliance.tcpa import TCPAChecker, TCPA_START_HOUR, TCPA_END_HOUR


@pytest.mark.unit
class TestTCPATimezoneResolution:
    """Test TCPA timezone resolution from area codes."""

    def setup_method(self):
        self.checker = TCPAChecker()

    def test_nyc_area_code(self):
        """212 is America/New_York."""
        assert self.checker._resolve_timezone(phone="+12125551234") == "America/New_York"

    def test_sf_area_code(self):
        """415 is America/Los_Angeles."""
        assert self.checker._resolve_timezone(phone="4155551234") == "America/Los_Angeles"

    def test_chicago_area_code(self):
        """312 is America/Chicago."""
        assert self.checker._resolve_timezone(phone="3125551234") == "America/Chicago"

    def test_denver_area_code(self):
        """303 is America/Denver."""
        assert self.checker._resolve_timezone(phone="3035551234") == "America/Denver"

    def test_hawaii_area_code(self):
        """808 is Pacific/Honolulu."""
        assert self.checker._resolve_timezone(phone="8085551234") == "Pacific/Honolulu"

    def test_alaska_area_code(self):
        """907 is America/Anchorage."""
        assert self.checker._resolve_timezone(phone="9075551234") == "America/Anchorage"

    def test_explicit_tz_overrides_phone(self):
        """Explicit tz_id takes priority over phone area code."""
        tz = self.checker._resolve_timezone(
            tz_id="America/Chicago",
            phone="+12125551234",
        )
        assert tz == "America/Chicago"

    def test_unknown_area_code_returns_none(self):
        """Unknown area code returns None."""
        assert self.checker._resolve_timezone(phone="0005551234") is None

    def test_country_code_stripped(self):
        """Phone with +1 country code is handled correctly."""
        tz = self.checker._resolve_timezone(phone="+13125551234")
        assert tz == "America/Chicago"


@pytest.mark.unit
class TestTCPAContactWindow:
    """Test TCPA contact window enforcement."""

    def setup_method(self):
        self.checker = TCPAChecker()

    def test_unknown_timezone_blocks_contact(self):
        """Should block contact when timezone cannot be determined."""
        result = self.checker.can_contact_now(phone="0005551234")
        assert result.can_contact is False
        assert "Cannot determine" in result.message

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_allowed_during_window(self, mock_now):
        """Contact allowed during 8 AM - 9 PM window."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 14, 30, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is True

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_blocked_before_8am(self, mock_now):
        """Contact blocked before 8 AM."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 6, 30, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_blocked_after_9pm(self, mock_now):
        """Contact blocked after 9 PM."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 21, 30, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_boundary_8am_allowed(self, mock_now):
        """Exactly 8:00 AM is allowed."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 8, 0, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is True

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_boundary_9pm_blocked(self, mock_now):
        """Exactly 9:00 PM (21:00) is NOT allowed."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 21, 0, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is False

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_one_minute_before_close_allowed(self, mock_now):
        """8:59 PM is still allowed."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 20, 59, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.can_contact is True

    @patch("services.compliance.tcpa.TCPAChecker._get_local_now")
    def test_minutes_until_close_calculated(self, mock_now):
        """When in window, minutes_until_window_closes is set."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        mock_now.return_value = datetime(2026, 5, 14, 14, 0, 0, tzinfo=tz)
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.minutes_until_window_closes is not None
        # 9 PM - 2 PM = 7 hours = 420 minutes
        assert result.minutes_until_window_closes == 420


@pytest.mark.unit
class TestTCPACheckAtTime:
    """Test TCPA contact check at a specific time."""

    def setup_method(self):
        self.checker = TCPAChecker()

    def test_2pm_eastern_allowed(self):
        """2 PM Eastern is within window."""
        contact_time = datetime(2026, 5, 14, 18, 0, 0, tzinfo=timezone.utc)  # 2 PM ET
        assert self.checker.check_contact_at_time(contact_time, "America/New_York") is True

    def test_1am_eastern_blocked(self):
        """1 AM Eastern is outside window."""
        contact_time = datetime(2026, 5, 14, 5, 0, 0, tzinfo=timezone.utc)  # 1 AM ET
        assert self.checker.check_contact_at_time(contact_time, "America/New_York") is False

    def test_midnight_blocked(self):
        """Midnight is outside window."""
        contact_time = datetime(2026, 5, 14, 4, 0, 0, tzinfo=timezone.utc)  # midnight ET
        assert self.checker.check_contact_at_time(contact_time, "America/New_York") is False

    def test_noon_pacific_allowed(self):
        """Noon Pacific is within window."""
        contact_time = datetime(2026, 5, 14, 19, 0, 0, tzinfo=timezone.utc)  # noon PT
        assert self.checker.check_contact_at_time(contact_time, "America/Los_Angeles") is True


@pytest.mark.unit
class TestTCPANextWindow:
    """Test TCPA next contact window calculation."""

    def setup_method(self):
        self.checker = TCPAChecker()

    def test_next_window_returns_timezone(self):
        """next_contact_window returns the correct timezone."""
        result = self.checker.next_contact_window(tz_id="America/New_York")
        assert result.timezone_id == "America/New_York"

    def test_next_window_has_utc_times(self):
        """next_contact_window returns UTC open/close times."""
        result = self.checker.next_contact_window(tz_id="America/New_York")
        assert result.window_opens_utc != "unknown"
        assert result.window_closes_utc != "unknown"

    def test_next_window_unknown_timezone(self):
        """Unknown timezone returns 'unknown' values."""
        result = self.checker.next_contact_window(phone="0005551234")
        assert result.timezone_id == "unknown"
        assert result.is_open_now is False

    def test_audit_metadata_present(self):
        """TCPA results include audit metadata."""
        result = self.checker.can_contact_now(tz_id="America/New_York")
        assert result.audit is not None
        assert "64.1200" in result.audit.regulation


# ---------------------------------------------------------------------------
# Cross-boundary Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComplianceEdgeCases:
    """Test edge cases across multiple compliance modules."""

    def test_trid_across_thanksgiving(self):
        """Business days across Thanksgiving week."""
        # Thanksgiving 2026 = Nov 26 (Thursday)
        count = count_business_days(date(2026, 11, 23), date(2026, 11, 30))
        assert count == 3

    def test_multiple_custom_holidays(self):
        """Business days with multiple sequential custom holidays."""
        custom = frozenset({date(2026, 12, 24)})
        result = add_business_days(date(2026, 12, 23), 3, custom)
        assert result == date(2026, 12, 30)

    def test_ecoa_and_trid_same_loan(self):
        """Both TRID and ECOA can run on the same loan dates."""
        trid = TRIDEngine()
        ecoa = ECOAEngine()

        trid_report = trid.full_trid_check(
            application_date=date(2026, 5, 11),
            closing_date=date(2026, 5, 29),
            le_delivered_date=date(2026, 5, 12),
            cd_delivered_date=date(2026, 5, 22),
        )

        ecoa_report = ecoa.full_ecoa_check(
            denial_date=date(2026, 5, 1),
            notice_sent_date=date(2026, 5, 15),
        )

        assert trid_report.overall_compliant is True
        assert ecoa_report.overall_compliant is True
