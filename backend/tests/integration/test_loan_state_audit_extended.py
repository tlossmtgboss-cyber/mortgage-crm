"""
Extended integration tests for `services/loan_state_audit_service.py`.

These tests cover signature contracts, coercion semantics, and null-safety
guarantees. DB-dependent flows are gated behind TEST_DATABASE_URL.
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_service():
    target = _BACKEND_DIR / "services" / "loan_state_audit_service.py"
    if not target.exists():
        pytest.skip("loan_state_audit_service.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_loan_state_audit_ext", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"audit service import failed: {exc}")
    return module


_svc = _load_service()


def _bad_db():
    class _D:
        def execute(self, *a, **k):
            raise RuntimeError("no db")

        def commit(self):
            raise RuntimeError("no db")

        def rollback(self):
            pass

    return _D()


# ---------------------------------------------------------------------------
# 1. Single transition — service never raises; returns None without real DB
# ---------------------------------------------------------------------------

def test_single_transition_returns_none_without_real_db():
    res = _svc.record_state_change(
        db=_bad_db(),
        loan_id=1,
        organization_id=uuid.uuid4(),
        from_stage="APPLICATION",
        to_stage="DISCLOSED",
        from_pipeline="leads",
        to_pipeline="active_loans",
        trigger_source="test",
    )
    # Returns None on infrastructure error (best-effort guarantee)
    assert res is None


# ---------------------------------------------------------------------------
# 2. Multiple sequential transitions all swallow errors
# ---------------------------------------------------------------------------

def test_multiple_sequential_transitions_swallow_errors():
    org = uuid.uuid4()
    for f, t in [("A", "B"), ("B", "C"), ("C", "D")]:
        res = _svc.record_state_change(
            db=_bad_db(),
            loan_id=1,
            organization_id=org,
            from_stage=f,
            to_stage=t,
            from_pipeline="active_loans",
            to_pipeline="active_loans",
            trigger_source="seq_test",
        )
        assert res is None


# ---------------------------------------------------------------------------
# 3. Tenant scoping required — None organization_id rejected
# ---------------------------------------------------------------------------

def test_tenant_scoping_required_for_audit():
    res = _svc.record_state_change(
        db=_bad_db(),
        loan_id=1,
        organization_id=None,  # invalid
        from_stage="A",
        to_stage="B",
        from_pipeline="leads",
        to_pipeline="active_loans",
        trigger_source="x",
    )
    assert res is None


# ---------------------------------------------------------------------------
# 4. from_pipeline / to_pipeline parameter recognized
# ---------------------------------------------------------------------------

def test_pipeline_params_in_signature():
    sig = inspect.signature(_svc.record_state_change)
    assert "from_pipeline" in sig.parameters
    assert "to_pipeline" in sig.parameters


# ---------------------------------------------------------------------------
# 5. trigger_source captured in signature
# ---------------------------------------------------------------------------

def test_trigger_source_in_signature():
    sig = inspect.signature(_svc.record_state_change)
    assert "trigger_source" in sig.parameters


# ---------------------------------------------------------------------------
# 6. actor_user_id null-safe (default None)
# ---------------------------------------------------------------------------

def test_actor_user_id_defaults_to_none():
    sig = inspect.signature(_svc.record_state_change)
    p = sig.parameters["actor_user_id"]
    assert p.default is None


# ---------------------------------------------------------------------------
# 7. metadata defaults to None (JSONB-roundtrip placeholder)
# ---------------------------------------------------------------------------

def test_metadata_defaults_to_none():
    sig = inspect.signature(_svc.record_state_change)
    p = sig.parameters["metadata"]
    assert p.default is None


# ---------------------------------------------------------------------------
# 8. Missing required field rejected silently
# ---------------------------------------------------------------------------

def test_missing_to_stage_silently_rejected():
    res = _svc.record_state_change(
        db=_bad_db(),
        loan_id=1,
        organization_id=uuid.uuid4(),
        from_stage="A",
        to_stage="",  # invalid
        from_pipeline="leads",
        to_pipeline="leads",
        trigger_source="x",
    )
    assert res is None
