"""
Integration tests for IRS tax-deadline detection in the holiday calendar
and the storm-window / IRS-deadline SLA adjustments in
``BusinessHoursCalculator``.

Tests load modules by file path to avoid pulling the wider ``services``
package surface (which imports SQLAlchemy models).
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _load_by_path(name: str, rel_path: str):
    backend_dir = Path(__file__).resolve().parents[2]
    target = backend_dir / rel_path
    if not target.exists():  # pragma: no cover
        pytest.skip(f"{rel_path} not found at {target}")
    spec = importlib.util.spec_from_file_location(name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_hc = _load_by_path(
    "_perennia_holiday_calendar_under_test",
    "services/holiday_calendar.py",
)
HolidayCalendar = _hc.HolidayCalendar
IRS_TAX_DEADLINES = _hc.IRS_TAX_DEADLINES


# --------------------------------------------------------------------- deadline detection

def test_is_tax_deadline_apr_15():
    cal = HolidayCalendar()
    assert cal.is_tax_deadline(date(2026, 4, 15)) is True
    assert cal.is_tax_deadline(date(2026, 4, 14)) is False


def test_is_tax_deadline_quarterly_estimated():
    cal = HolidayCalendar()
    for d in (
        date(2026, 1, 15),
        date(2026, 4, 15),
        date(2026, 6, 15),
        date(2026, 9, 15),
        date(2026, 10, 15),
    ):
        assert cal.is_tax_deadline(d), f"{d} should be a tax deadline"


def test_next_tax_deadline_after_returns_soonest():
    cal = HolidayCalendar()
    nxt = cal.next_tax_deadline_after(date(2026, 5, 1))
    assert nxt is not None
    d, name = nxt
    assert d == date(2026, 6, 15)
    assert "Q2" in name


# --------------------------------------------------------------------- SLA calculator

# Load the SLA calculator module without dragging in DB models. We import
# the BusinessHoursCalculator class directly.
def _load_sla_calc():
    backend_dir = Path(__file__).resolve().parents[2]
    target = (
        backend_dir
        / "services"
        / "smart_docs"
        / "enterprise"
        / "sla_enforcement_service.py"
    )
    # Heavy module — try a normal import which will succeed in CI environments
    # with proper sys.path; otherwise skip.
    try:
        sys.path.insert(0, str(backend_dir))
        from services.smart_docs.enterprise.sla_enforcement_service import (  # type: ignore
            BusinessHoursCalculator,
        )
        return BusinessHoursCalculator
    except Exception as exc:
        pytest.skip(f"BusinessHoursCalculator unavailable: {exc}")


def test_sla_velocity_multiplier_around_tax_day():
    BHC = _load_sla_calc()
    calc = BHC(
        start_hour=8,
        end_hour=18,
        exclude_weekends=True,
        exclude_holidays=False,
        consider_irs_deadlines=True,
    )
    # Tax-stress window Apr 14-16 → 1.5x SLA window
    assert calc.velocity_multiplier(date(2026, 4, 14)) == 1.5
    assert calc.velocity_multiplier(date(2026, 4, 15)) == 1.5
    assert calc.velocity_multiplier(date(2026, 4, 16)) == 1.5
    # Other days normal
    assert calc.velocity_multiplier(date(2026, 4, 17)) == 1.0
    assert calc.velocity_multiplier(date(2026, 5, 1)) == 1.0


def test_sla_velocity_multiplier_off_when_disabled():
    BHC = _load_sla_calc()
    calc = BHC(
        start_hour=8,
        end_hour=18,
        exclude_weekends=True,
        exclude_holidays=False,
        consider_irs_deadlines=False,
    )
    # Disabled → no multiplier, even on tax day
    assert calc.velocity_multiplier(date(2026, 4, 15)) == 1.0
    assert calc.is_tax_stress_day(date(2026, 4, 15)) is True


def test_sla_storm_window_marks_day_non_business():
    BHC = _load_sla_calc()
    storm_dates = {date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 12)}
    calc = BHC(
        start_hour=8,
        end_hour=18,
        exclude_weekends=True,
        exclude_holidays=False,
        storm_window_dates=storm_dates,
    )
    # Storm-window dates are NOT business days
    for d in storm_dates:
        assert calc.is_business_day(d) is False, f"{d} should be non-business"
    # A nearby weekday outside the storm IS a business day
    # 2026-09-15 (Tuesday)
    assert calc.is_business_day(date(2026, 9, 15)) is True
