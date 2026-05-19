"""
Unit-style integration tests for LoanReconciliationService.

Uses importlib.util.spec_from_file_location to load the service module
directly so we exercise reconciliation logic, state transitions, and audit
metadata without booting the FastAPI app, the agents package, or hitting
a real database.

The service's DB-touching helpers (`_get_own_db`, `_write_audit_log`,
`_log_unmapped_stage`, `_store_raw_sf_stage`, `_is_duplicate_transition`,
`_get_loan_info`, `_create_disposition_task`) are stubbed out so we only
exercise the in-memory reconciliation routing logic, which is the part
that the SLA/MUM-promotion contract depends on.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_module(rel_path: str, mod_name: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# Load workflow_constants first (the service imports from it). We register
# it under the path the service will look up (`services.workflow_constants`).
_constants = _load_module("services/workflow_constants.py", "services.workflow_constants")
sys.modules["services.workflow_constants"] = _constants

# The service also pulls in `services.loan_state_audit_service.record_state_change`
# via a deferred import deep inside `_record_state_change_audit`. We don't
# trigger that path in these tests (we stub `_write_audit_log` directly).

_recon = _load_module(
    "services/loan_reconciliation_service.py",
    "services.loan_reconciliation_service",
)

LoanReconciliationService = _recon.LoanReconciliationService
ReconciliationAction = _recon.ReconciliationAction
ReconciliationResult = _recon.ReconciliationResult


class _StubDB:
    """Minimal db stub — never used because we patch every DB helper."""

    def execute(self, *a, **kw):
        raise AssertionError("DB execute should not be called in these tests")


@pytest.fixture
def service(monkeypatch):
    svc = LoanReconciliationService(_StubDB())

    # Patch the DB-touching helpers so reconcile() runs purely on the
    # in-memory routing logic.
    monkeypatch.setattr(svc, "_get_own_db", lambda: _StubDB())
    monkeypatch.setattr(svc, "_close_own_db", lambda: None)
    monkeypatch.setattr(svc, "_write_audit_log", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_store_raw_sf_stage", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_log_unmapped_stage", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_is_duplicate_transition", lambda *a, **kw: False)
    monkeypatch.setattr(svc, "_get_loan_info", lambda loan_id: None)
    monkeypatch.setattr(svc, "_create_disposition_task", lambda **kw: None)
    return svc


# ---------------------------------------------------------------------------
# Test 1: Idempotent skip when stage hasn't changed
# ---------------------------------------------------------------------------

def test_reconcile_idempotent_when_stages_match(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "PROCESSING"},
        new_data={"stage": "PROCESSING"},
    )
    assert result.action == ReconciliationAction.SKIP
    assert result.audit_metadata == {"reason": "idempotent_skip"}


# ---------------------------------------------------------------------------
# Test 2: Funded → PROMOTE_TO_MUM with should_promote_mum flag
# ---------------------------------------------------------------------------

def test_reconcile_funded_promotes_to_mum(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "CLOSING"},
        new_data={"stage": "FUNDED"},
    )
    assert result.action == ReconciliationAction.PROMOTE_TO_MUM
    assert result.should_promote_mum is True
    assert result.old_stage == "CLOSING"
    assert result.new_stage == "FUNDED"


# ---------------------------------------------------------------------------
# Test 3: Suspended → PAUSE_SLA with pause + disposition flags
# ---------------------------------------------------------------------------

def test_reconcile_suspended_pauses_sla(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "UNDERWRITING"},
        new_data={"stage": "SUSPENDED"},
    )
    assert result.action == ReconciliationAction.PAUSE_SLA
    assert result.should_pause_sla is True
    assert result.should_create_disposition is True


# ---------------------------------------------------------------------------
# Test 4: Terminal stages → ARCHIVE with stop_workflows flag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "terminal", ["CANCELLED", "WITHDRAWN", "DENIED", "DEAD", "DOES_NOT_QUALIFY"]
)
def test_reconcile_terminal_archives_and_stops_workflows(service, terminal):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "PROCESSING"},
        new_data={"stage": terminal},
    )
    assert result.action == ReconciliationAction.ARCHIVE
    assert result.should_stop_workflows is True
    assert result.should_create_disposition is True


# ---------------------------------------------------------------------------
# Test 5: DENIED triggers compliance routing (compliance_trigger_stages)
# ---------------------------------------------------------------------------

def test_reconcile_denied_triggers_compliance(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "UW_RECEIVED"},
        new_data={"stage": "DENIED"},
    )
    assert result.should_trigger_compliance is True


# ---------------------------------------------------------------------------
# Test 6: Cancelled (not in compliance trigger set) does NOT set compliance
# ---------------------------------------------------------------------------

def test_reconcile_cancelled_does_not_trigger_compliance(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "PROCESSING"},
        new_data={"stage": "CANCELLED"},
    )
    assert result.should_trigger_compliance is False


# ---------------------------------------------------------------------------
# Test 7: Reactivation from terminal back to active stage
# ---------------------------------------------------------------------------

def test_reconcile_reactivation_from_cancelled(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "CANCELLED"},
        new_data={"stage": "PROCESSING"},
    )
    assert result.action == ReconciliationAction.REACTIVATE
    assert any("Reactivation" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Test 8: Forward progression returns ALLOW + create disposition
# ---------------------------------------------------------------------------

def test_reconcile_forward_progression_allows(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "APPLICATION"},
        new_data={"stage": "PROCESSING"},
    )
    assert result.action == ReconciliationAction.ALLOW
    assert result.should_create_disposition is True


# ---------------------------------------------------------------------------
# Test 9: Backward movement detected via STAGE_ORDER
# ---------------------------------------------------------------------------

def test_reconcile_backward_movement_flagged(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "UNDERWRITING"},
        new_data={"stage": "PROCESSING"},
    )
    assert result.is_backward_movement is True
    assert any("Backward movement" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Test 10: Dedup window suppresses identical transition
# ---------------------------------------------------------------------------

def test_reconcile_dedup_suppresses_recent_duplicate(service, monkeypatch):
    monkeypatch.setattr(service, "_is_duplicate_transition", lambda *a, **kw: True)
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "APPLICATION"},
        new_data={"stage": "PROCESSING"},
    )
    assert result.action == ReconciliationAction.SKIP
    assert result.audit_metadata == {"reason": "duplicate_within_window"}


# ---------------------------------------------------------------------------
# Test 11: Unmapped Salesforce stage flagged for admin review
# ---------------------------------------------------------------------------

def test_reconcile_unmapped_sf_stage_flagged(service):
    result = service.reconcile(
        loan_id=1,
        old_data={"stage": "PROCESSING"},
        new_data={"stage": None, "salesforce_raw_stage": "Mystery Stage Z"},
    )
    assert result.action == ReconciliationAction.FLAG_FOR_REVIEW
    assert result.admin_review_reason is not None
    assert "Mystery Stage Z" in result.admin_review_reason


# ---------------------------------------------------------------------------
# Test 12: ReconciliationResult dataclass exposes the contracted fields
# ---------------------------------------------------------------------------

def test_reconciliation_result_default_fields():
    r = ReconciliationResult(
        action=ReconciliationAction.ALLOW, old_stage="A", new_stage="B"
    )
    # All optional flags default to False
    assert r.should_promote_mum is False
    assert r.should_pause_sla is False
    assert r.should_stop_workflows is False
    assert r.should_trigger_compliance is False
    assert r.is_backward_movement is False
    # Collections default to empty
    assert r.warnings == []
    assert r.audit_metadata == {}
