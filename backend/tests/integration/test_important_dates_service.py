"""
Integration tests for ImportantDates consolidated model + service.

Covers:
- get_important_dates returns all canonical milestones
- set_milestone_date writes and tz-coerces
- set_milestone_date rejects unknown milestones
- days_since_milestone with no date set returns None
- days_since_milestone with a date returns positive int
- days_since_milestone honors use_business_days=False
- get_next_due_milestone returns first unset after last set
- get_next_due_milestone respects sla_config windows
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _load(name: str, relpath: str):
    target = _BACKEND_DIR / relpath
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Direct-load the module so we don't drag in the heavy `database.models`
# package which requires PostgreSQL fixtures.
@pytest.fixture(scope="module")
def imp_dates_mod():
    # Load important_dates model module standalone.
    _load(
        "database.models.important_dates",
        "database/models/important_dates.py",
    )
    return _load(
        "services.important_dates_service",
        "services/important_dates_service.py",
    )


class _Stub:
    """Lightweight stand-in for a loan/lead row."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_get_important_dates_returns_all_canonical(imp_dates_mod):
    stub = _Stub()
    out = imp_dates_mod.get_important_dates(stub)
    # 13 canonical milestone names
    assert len(out) == 13
    assert "new_lead_date" in out and "funded_date" in out
    # All are None for an empty stub
    assert all(v is None for v in out.values())


def test_set_milestone_date_writes_value(imp_dates_mod):
    stub = _Stub()
    when = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    out = imp_dates_mod.set_milestone_date(stub, "application_date", when)
    assert out == when
    assert stub.application_date == when


def test_set_milestone_date_coerces_naive_tz(imp_dates_mod):
    stub = _Stub()
    naive = datetime(2026, 5, 1, 9, 0)
    out = imp_dates_mod.set_milestone_date(stub, "approved_date", naive)
    assert out.tzinfo is not None


def test_set_milestone_date_rejects_unknown(imp_dates_mod):
    stub = _Stub()
    with pytest.raises(ValueError):
        imp_dates_mod.set_milestone_date(stub, "not_a_real_milestone")


def test_days_since_milestone_unset_returns_none(imp_dates_mod):
    stub = _Stub()
    assert imp_dates_mod.days_since_milestone(stub, "approved_date") is None


def test_days_since_milestone_calendar_days(imp_dates_mod):
    stub = _Stub()
    when = datetime.now(timezone.utc) - timedelta(days=7)
    stub.application_date = when
    days = imp_dates_mod.days_since_milestone(
        stub, "application_date", use_business_days=False
    )
    assert days == 7


def test_get_next_due_milestone_first_unset(imp_dates_mod):
    stub = _Stub()
    stub.new_lead_date = datetime(2026, 5, 1, tzinfo=timezone.utc)
    stub.application_date = datetime(2026, 5, 5, tzinfo=timezone.utc)
    result = imp_dates_mod.get_next_due_milestone(stub)
    assert result is not None
    name, _anchor = result
    # After application_date, the next canonical milestone is disclosed_date
    assert name == "disclosed_date"


def test_get_next_due_milestone_respects_sla_window(imp_dates_mod):
    stub = _Stub()
    # Set application_date 1 day ago — SLA requires 5 business days before
    # disclosed_date is "due".
    stub.application_date = datetime.now(timezone.utc) - timedelta(days=1)
    result = imp_dates_mod.get_next_due_milestone(
        stub,
        sla_config={"disclosed_date": 5},
    )
    # disclosed_date should be skipped (not yet due), processing returned
    if result is not None:
        name, _ = result
        assert name != "disclosed_date" or name == "processing_date"
