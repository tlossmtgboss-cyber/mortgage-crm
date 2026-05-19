"""
Integration tests for HolidayCalendar.

Covers:
- Federal holidays detected (2026)
- Weekend detection
- CA-specific: Cesar Chavez Day + Day After Thanksgiving
- NY-specific: Election Day
- TX-specific: Texas Independence Day + Battle of San Jacinto
- FL: no extra state closures
- IL: Lincoln's Birthday + Casimir Pulaski Day
- next_business_day skips weekends + holidays
- business_days_between math
- Custom closures honored
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture(scope="module")
def cal_mod():
    target = _BACKEND_DIR / "services" / "holiday_calendar.py"
    spec = importlib.util.spec_from_file_location(
        "services.holiday_calendar", target
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.holiday_calendar"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_federal_holidays_2026_count(cal_mod):
    # 11 federal holidays (10 standard + Juneteenth)
    assert len(cal_mod.FEDERAL_HOLIDAYS_2026) == 11
    names = {n for _d, n in cal_mod.FEDERAL_HOLIDAYS_2026}
    assert "Juneteenth" in names
    assert "Independence Day" in names


def test_is_holiday_federal(cal_mod):
    cal = cal_mod.HolidayCalendar()
    assert cal.is_holiday(date(2026, 7, 4)) is True  # Independence Day
    assert cal.is_holiday(date(2026, 12, 25)) is True  # Christmas
    assert cal.is_holiday(date(2026, 7, 5)) is False  # random Sunday


def test_weekend_detection(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # 2026-07-04 is a Saturday — both holiday AND weekend
    assert cal.is_weekend(date(2026, 7, 4)) is True
    # 2026-05-20 is a Wednesday
    assert cal.is_weekend(date(2026, 5, 20)) is False


def test_ca_holidays(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # Cesar Chavez Day — March 31
    assert cal.is_holiday(date(2026, 3, 31), state="CA") is True
    assert cal.is_holiday(date(2026, 3, 31), state=None) is False
    # Day After Thanksgiving — 2026 Thanksgiving = Nov 26, day after = Nov 27
    assert cal.is_holiday(date(2026, 11, 27), state="CA") is True


def test_ny_election_day(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # Election Day 2026 = Nov 3 (1st Tue after 1st Mon)
    assert cal.is_holiday(date(2026, 11, 3), state="NY") is True
    assert cal.is_holiday(date(2026, 11, 3), state=None) is False


def test_tx_holidays(cal_mod):
    cal = cal_mod.HolidayCalendar()
    assert cal.is_holiday(date(2026, 3, 2), state="TX") is True   # TX Indep
    assert cal.is_holiday(date(2026, 4, 21), state="TX") is True  # San Jacinto


def test_fl_no_extra_holidays(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # FL has no state-specific closures — Mar 2 (TX-only) should be a regular day
    assert cal.is_holiday(date(2026, 3, 2), state="FL") is False
    # Verify FL still respects federal
    assert cal.is_holiday(date(2026, 7, 4), state="FL") is True


def test_il_holidays(cal_mod):
    cal = cal_mod.HolidayCalendar()
    assert cal.is_holiday(date(2026, 2, 12), state="IL") is True  # Lincoln
    assert cal.is_holiday(date(2026, 3, 6), state="IL") is True   # Pulaski


def test_next_business_day_skips_weekend_and_holiday(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # 2026-07-03 is Friday; July 4 is Saturday (holiday). Next biz day = Mon Jul 6
    nxt = cal.next_business_day(date(2026, 7, 3))
    assert nxt == date(2026, 7, 6)


def test_business_days_between_skips_weekends(cal_mod):
    cal = cal_mod.HolidayCalendar()
    # Mon 2026-05-18 to Mon 2026-05-25 = 5 business days (M,T,W,Th,F)
    n = cal.business_days_between(date(2026, 5, 18), date(2026, 5, 25))
    assert n == 5


def test_custom_closures(cal_mod):
    cal = cal_mod.HolidayCalendar(custom_closures=[date(2026, 5, 20)])
    assert cal.is_holiday(date(2026, 5, 20)) is True
    assert cal.is_business_day(date(2026, 5, 20)) is False
