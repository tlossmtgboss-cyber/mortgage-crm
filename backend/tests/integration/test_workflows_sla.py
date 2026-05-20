"""
Integration tests for SLA escalation, business-hour math, and stage routing.

Targets the pure-logic constants in:
  - services/workflow_constants.py (escalation chain, SLA targets,
    terminal/pause/archive stages, stage→date map)
  - services/holiday_calendar.py (business-day skipping for SLA breach times)

The full WorkflowSLAService is DB-backed and tested via test_workflow_engine.py;
these tests cover the rule surface that determines breach thresholds.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_wc = _load("_pa_wc_sla", "services/workflow_constants.py")
_hc = _load("_pa_hc_sla", "services/holiday_calendar.py")


# ---------------------------------------------------------------------------
# Escalation chain — breach detection thresholds
# ---------------------------------------------------------------------------

def test_escalation_level_1_at_8_business_hours():
    assert _wc.ESCALATION_CHAIN[1]["hours_overdue"] == 8


def test_escalation_level_2_at_16_business_hours():
    assert _wc.ESCALATION_CHAIN[2]["hours_overdue"] == 16


def test_escalation_level_3_at_24_business_hours():
    assert _wc.ESCALATION_CHAIN[3]["hours_overdue"] == 24


def test_escalation_targets_route_up_the_chain():
    targets = [_wc.ESCALATION_CHAIN[i]["target"] for i in (1, 2, 3)]
    assert targets == ["assignee", "manager", "branch_manager"]


def test_escalation_level_2_reassigns():
    assert _wc.ESCALATION_CHAIN[2]["action"] == "notify_and_reassign"


# ---------------------------------------------------------------------------
# Suspension pause/resume — SUSPENDED in skip set
# ---------------------------------------------------------------------------

def test_suspended_in_pause_stages():
    assert "SUSPENDED" in _wc.PAUSE_STAGES


def test_suspended_in_loan_skip_stages():
    assert "SUSPENDED" in _wc.LOAN_SKIP_STAGES


def test_archive_stages_partition_does_not_include_suspended():
    # Archive = terminal, suspended is pause not terminal
    assert "SUSPENDED" not in _wc.ARCHIVE_STAGES
    assert "CANCELLED" in _wc.ARCHIVE_STAGES


# ---------------------------------------------------------------------------
# Holiday exclusion — business-day skipping
# ---------------------------------------------------------------------------

def test_july_4_skipped_when_computing_next_business_day():
    cal = _hc.HolidayCalendar()
    # July 3 2026 = Friday; next biz day skips July 4 (Sat) and Sun
    nbd = cal.next_business_day(date(2026, 7, 3))
    assert nbd == date(2026, 7, 6)


def test_business_days_between_skips_christmas_week():
    cal = _hc.HolidayCalendar()
    # Dec 24 (Thu) to Dec 30 (Wed) 2026 — Christmas is Friday Dec 25
    count = cal.business_days_between(date(2026, 12, 24), date(2026, 12, 31))
    # 24 (Thu), 25 (Fri, holiday), 26-27 weekend, 28 (Mon), 29 (Tue), 30 (Wed)
    # Half-open [24, 31): Thu + Mon + Tue + Wed = 4
    assert count == 4


def test_ca_cesar_chavez_day_is_holiday():
    cal = _hc.HolidayCalendar()
    assert cal.is_holiday(date(2026, 3, 31), state="CA") is True
    # Not a holiday for FL
    assert cal.is_holiday(date(2026, 3, 31), state="FL") is False


# ---------------------------------------------------------------------------
# SLA targets — per-stage transition durations
# ---------------------------------------------------------------------------

def test_sla_application_to_disclosed_is_3_days():
    assert _wc.SLA_TARGETS["APPLICATION_to_DISCLOSED"] == 3


def test_stage_sla_days_application_window():
    assert _wc.STAGE_SLA_DAYS["APPLICATION"] == 3


def test_stage_to_date_field_funded_anchor():
    assert _wc.STAGE_TO_DATE_FIELD["FUNDED"] == "funded_date"


def test_terminal_stages_are_six():
    assert len(_wc.TERMINAL_LOAN_STAGES) == 6
    assert "FUNDED" in _wc.TERMINAL_LOAN_STAGES


# ---------------------------------------------------------------------------
# Loan/Lead stage workflow routing
# ---------------------------------------------------------------------------

def test_loan_stage_disclosed_routes_to_under_contract():
    assert _wc.LOAN_STAGE_WORKFLOW_MAP["DISCLOSED"] == "under_contract"


def test_loan_stage_funded_routes_to_post_close():
    assert _wc.LOAN_STAGE_WORKFLOW_MAP["FUNDED"] == "post_close"


def test_loan_stage_clear_to_close_is_last_mile():
    assert _wc.LOAN_STAGE_WORKFLOW_MAP["CLEAR_TO_CLOSE"] == "last_mile"


def test_lead_status_new_routes_to_prospect():
    assert _wc.LEAD_STATUS_WORKFLOW_MAP["New"] == "prospect"


def test_lead_status_skip_includes_do_not_call():
    assert "Do Not Call" in _wc.LEAD_SKIP_STAGES


# ---------------------------------------------------------------------------
# Stage order
# ---------------------------------------------------------------------------

def test_stage_order_funded_max():
    assert _wc.STAGE_ORDER["FUNDED"] == 100


def test_stage_order_cancelled_negative():
    assert _wc.STAGE_ORDER["CANCELLED"] < 0


def test_active_loan_stages_excludes_funded():
    assert "FUNDED" not in _wc.ACTIVE_LOAN_STAGES
    assert "PROCESSING" in _wc.ACTIVE_LOAN_STAGES
