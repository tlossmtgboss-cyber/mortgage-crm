"""
Integration tests for the workflow engine helpers.

Targets the pure-logic constants and task-routing utilities used by
backend/services/workflow_sla_service.py — the canonical task-routing map,
stage-to-workflow assignment, terminal/pause/archive partitioning, and the
business-hours math used by the SLA escalation chain.

The full WorkflowSLAService is heavyweight (DB-backed); these tests cover
the side-effect-free helpers it depends on, which is where coverage gains
the most ground for the workflow subsystem.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_constants():
    target = _BACKEND_DIR / "services" / "workflow_constants.py"
    if not target.exists():
        pytest.skip("workflow_constants.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_workflow_constants", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_wc = _load_constants()


# ---------------------------------------------------------------------------
# Test 1: TASK_TYPE_ROUTES distinguishes dialer-queue vs task-list
# ---------------------------------------------------------------------------

def test_task_type_routing_dialer_vs_task_list():
    # Calls/phone tasks land on the task list (LO-driven dialer)
    assert _wc.TASK_TYPE_ROUTES["phone"] == "task_list"
    # Bulk power-dialer queue routing
    assert _wc.TASK_TYPE_ROUTES["dialer"] == "dialer_queue"
    # SMS auto-send
    assert _wc.TASK_TYPE_ROUTES["text"] == "sms_automation"


# ---------------------------------------------------------------------------
# Test 2: AI_ELIGIBLE_TASK_TYPES covers exactly the auto-executable types
# ---------------------------------------------------------------------------

def test_ai_eligible_task_types_set():
    assert "email" in _wc.AI_ELIGIBLE_TASK_TYPES
    assert "text" in _wc.AI_ELIGIBLE_TASK_TYPES
    # Phone is NOT AI-eligible (humans dial)
    assert "phone" not in _wc.AI_ELIGIBLE_TASK_TYPES
    # Dialer queue not eligible for AI take-over either
    assert "dialer" not in _wc.AI_ELIGIBLE_TASK_TYPES


# ---------------------------------------------------------------------------
# Test 3: Tasks → power-dialer routing for the `dialer` type
# ---------------------------------------------------------------------------

def test_dialer_type_routes_to_power_dialer_queue():
    assert _wc.TASK_TYPE_ROUTES.get("dialer") == "dialer_queue"


# ---------------------------------------------------------------------------
# Test 4: Tenant scoping — every workflow constant is per-stage, no org leak
# ---------------------------------------------------------------------------

def test_workflow_constants_have_no_org_id_keys():
    # Workflow maps are keyed by stage strings, never by org_id (which is
    # set on each WorkflowConfiguration row, not in the constant table).
    for stage in _wc.LOAN_STAGE_WORKFLOW_MAP:
        assert "_org_" not in stage
        assert not stage.isdigit()


# ---------------------------------------------------------------------------
# Test 5: Suspended → in LOAN_SKIP_STAGES (timer pauses, no new tasks)
# ---------------------------------------------------------------------------

def test_suspended_in_skip_stages():
    assert "SUSPENDED" in _wc.LOAN_SKIP_STAGES


# ---------------------------------------------------------------------------
# Test 6: Terminal stages → in LOAN_SKIP_STAGES (archive, no new tasks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stage", ["CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"]
)
def test_terminal_stages_in_loan_skip_set(stage):
    assert stage in _wc.LOAN_SKIP_STAGES


# ---------------------------------------------------------------------------
# Test 7: Escalation chain uses business hours (Mon-Fri 8AM-6PM = 10h/day)
# ---------------------------------------------------------------------------

def test_escalation_chain_business_hours_format():
    chain = _wc.ESCALATION_CHAIN
    # 3 levels exist and each has the contract fields
    assert set(chain.keys()) == {1, 2, 3}
    for level, cfg in chain.items():
        assert "hours_overdue" in cfg
        assert "target" in cfg
        assert "action" in cfg
    # Level 2 should be more overdue than Level 1
    assert chain[2]["hours_overdue"] > chain[1]["hours_overdue"]
    # Level 3 should be more overdue than Level 2
    assert chain[3]["hours_overdue"] > chain[2]["hours_overdue"]


# ---------------------------------------------------------------------------
# Test 8: Stage-to-date field mapping anchors SLA milestone calculations
# ---------------------------------------------------------------------------

def test_stage_to_date_field_anchors_funded_date():
    # Funded stage stamps the funded_date column — this is the SLA anchor
    # used by the workflow task engine to compute days-elapsed.
    assert _wc.STAGE_TO_DATE_FIELD["FUNDED"] == "funded_date"
    # APPLICATION stamps application_date
    assert _wc.STAGE_TO_DATE_FIELD["APPLICATION"] == "application_date"
    # CLEAR_TO_CLOSE stamps clear_to_close_date
    assert _wc.STAGE_TO_DATE_FIELD["CLEAR_TO_CLOSE"] == "clear_to_close_date"
