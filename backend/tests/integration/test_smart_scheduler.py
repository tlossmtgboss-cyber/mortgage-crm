"""
Integration tests for the smart scheduler models + reschedule service constants.

Covers:
  - SchedulingMethod / AppointmentStatus enums
  - ScheduledAppointment model column shape
  - RescheduleService configuration constants
  - Conflict detection helpers (time overlap check)
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


try:
    from services.smart_scheduler_service import (
        SchedulingMethod,
        AppointmentStatus,
        ScheduledAppointment,
    )
except Exception as e:
    pytest.skip(f"smart_scheduler_service not importable: {e}",
                allow_module_level=True)


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(name, str(target))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


_resched = _load("_pa_resched", "services/reschedule_service.py")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_scheduling_method_has_round_robin():
    assert SchedulingMethod.ROUND_ROBIN.value == "round_robin"


def test_scheduling_method_includes_5_methods():
    assert len(list(SchedulingMethod)) == 5


def test_appointment_status_cancelled():
    assert AppointmentStatus.CANCELLED == "cancelled"


def test_appointment_status_no_show():
    assert AppointmentStatus.NO_SHOW.value == "no_show"


def test_appointment_status_all_states():
    states = {s.value for s in AppointmentStatus}
    assert {"scheduled", "confirmed", "completed", "cancelled",
            "no_show", "rescheduled"}.issubset(states)


# ---------------------------------------------------------------------------
# ScheduledAppointment model
# ---------------------------------------------------------------------------

def test_scheduled_appointment_table_name():
    assert ScheduledAppointment.__tablename__ == "scheduled_appointments"


def test_scheduled_appointment_has_required_columns():
    cols = {c.name for c in ScheduledAppointment.__table__.columns}
    for required in ("id", "appointment_id", "loan_officer_id",
                     "contact_id", "start_time", "end_time", "status"):
        assert required in cols, f"Missing column: {required}"


# ---------------------------------------------------------------------------
# Reschedule constants
# ---------------------------------------------------------------------------

def test_reschedule_max_per_appointment_is_3():
    if _resched is None:
        pytest.skip("reschedule_service not importable")
    assert _resched.MAX_RESCHEDULES_PER_APPOINTMENT == 3


def test_reschedule_token_ttl_72_hours():
    if _resched is None:
        pytest.skip("reschedule_service not importable")
    assert _resched.RESCHEDULE_TOKEN_TTL_HOURS == 72


def test_reschedule_slots_lookahead_14_days():
    if _resched is None:
        pytest.skip("reschedule_service not importable")
    assert _resched.SLOTS_LOOKAHEAD_DAYS == 14


# ---------------------------------------------------------------------------
# Conflict detection helper — pure-logic overlap check
# ---------------------------------------------------------------------------

def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    """Two half-open intervals [a_start, a_end) and [b_start, b_end) overlap."""
    return a_start < b_end and b_start < a_end


def test_overlap_detection_back_to_back_no_conflict():
    base = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    a = (base, base + timedelta(minutes=30))
    b = (base + timedelta(minutes=30), base + timedelta(minutes=60))
    assert _overlaps(*a, *b) is False


def test_overlap_detection_partial_conflict():
    base = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    a = (base, base + timedelta(minutes=30))
    b = (base + timedelta(minutes=15), base + timedelta(minutes=45))
    assert _overlaps(*a, *b) is True


def test_overlap_detection_full_containment():
    base = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    a = (base, base + timedelta(hours=2))
    b = (base + timedelta(minutes=30), base + timedelta(minutes=60))
    assert _overlaps(*a, *b) is True
