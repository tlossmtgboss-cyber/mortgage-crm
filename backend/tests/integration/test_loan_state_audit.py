"""
Integration tests for the LoanStateChangeAudit write path.

The audit service in `services/loan_state_audit_service.py` guarantees:
  * INSERT-ONLY, fresh-session write (durable across caller rollback)
  * Never raises — failures are logged
  * Captures trigger_source, actor, from/to stage + pipeline

These tests exercise the service against a real Postgres test database when
TEST_DATABASE_URL is configured. When not, they import the model + service
and validate the contract surface without writing rows.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _has_real_db() -> bool:
    url = os.getenv("TEST_DATABASE_URL", "")
    return url.startswith("postgresql://") and "test_perennia" in url


requires_real_db = pytest.mark.skipif(
    not _has_real_db(),
    reason="Real Postgres TEST_DATABASE_URL not configured",
)


def _load_audit_service():
    """Direct-file-load the service module to avoid pulling the full backend
    package graph (which requires LangGraph, OpenAI, etc.)."""
    target = _BACKEND_DIR / "services" / "loan_state_audit_service.py"
    if not target.exists():
        pytest.skip("loan_state_audit_service.py not found")
    spec = importlib.util.spec_from_file_location(
        "_perennia_loan_state_audit_service", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"audit service import failed: {exc}")
    return module


_svc = _load_audit_service()


# ---------------------------------------------------------------------------
# 1. service signature contract — record_state_change accepts the documented args
# ---------------------------------------------------------------------------

def test_record_state_change_signature_contract():
    import inspect

    sig = inspect.signature(_svc.record_state_change)
    params = sig.parameters
    for required in (
        "db",
        "loan_id",
        "organization_id",
        "to_stage",
        "to_pipeline",
        "trigger_source",
    ):
        assert required in params, f"missing required param: {required}"
    # Optional but contractual:
    for optional in ("from_stage", "from_pipeline", "actor_user_id", "metadata"):
        assert optional in params, f"missing optional param: {optional}"


# ---------------------------------------------------------------------------
# 2. invalid org id returns None (never raises) — best-effort guarantee
# ---------------------------------------------------------------------------

def test_record_state_change_returns_none_on_invalid_org():
    """A bad organization_id must NOT raise — service must swallow and return None."""

    class _DummyDb:
        def execute(self, *_a, **_kw):
            raise RuntimeError("no real session")

    result = _svc.record_state_change(
        db=_DummyDb(),
        loan_id=1,
        organization_id=None,  # invalid
        from_stage="APPLICATION",
        to_stage="DISCLOSED",
        from_pipeline="leads",
        to_pipeline="active_loans",
        trigger_source="unit_test",
    )
    assert result is None


# ---------------------------------------------------------------------------
# 3. legacy int IDs map deterministically to UUIDs (audit-row stability)
# ---------------------------------------------------------------------------

def test_legacy_int_id_coercion_is_deterministic():
    a = _svc._coerce_uuid(42, kind="org")
    b = _svc._coerce_uuid("42", kind="org")
    c = _svc._coerce_uuid(43, kind="org")
    assert a is not None and isinstance(a, uuid.UUID)
    assert a == b, "same int must map to same UUID"
    assert a != c, "different ints must map to different UUIDs"


# ---------------------------------------------------------------------------
# 4. ordered audit rows across multiple transitions (xfail without real DB)
# ---------------------------------------------------------------------------

@requires_real_db
def test_multiple_transitions_produce_ordered_audit_rows(db_session):  # pragma: no cover
    from database.models.loan_state_audit import LoanStateChangeAudit

    org = uuid.uuid4()
    for from_s, to_s in [
        ("APPLICATION", "DISCLOSED"),
        ("DISCLOSED", "PROCESSING"),
        ("PROCESSING", "UNDERWRITING"),
    ]:
        _svc.record_state_change(
            db=db_session,
            loan_id=9001,
            organization_id=org,
            from_stage=from_s,
            to_stage=to_s,
            from_pipeline="active_loans",
            to_pipeline="active_loans",
            trigger_source="integration_test",
        )

    rows = (
        db_session.query(LoanStateChangeAudit)
        .filter(LoanStateChangeAudit.loan_id == 9001)
        .order_by(LoanStateChangeAudit.created_at)
        .all()
    )
    assert len(rows) >= 3
    assert [r.to_stage for r in rows[:3]] == [
        "DISCLOSED",
        "PROCESSING",
        "UNDERWRITING",
    ]


# ---------------------------------------------------------------------------
# 5. audit metadata captures trigger_source (xfail without real DB)
# ---------------------------------------------------------------------------

@requires_real_db
def test_audit_metadata_captures_trigger_source(db_session):  # pragma: no cover
    from database.models.loan_state_audit import LoanStateChangeAudit

    org = uuid.uuid4()
    audit_id = _svc.record_state_change(
        db=db_session,
        loan_id=9002,
        organization_id=org,
        from_stage="PROCESSING",
        to_stage="UNDERWRITING",
        from_pipeline="active_loans",
        to_pipeline="active_loans",
        trigger_source="salesforce_sync",
        metadata={"raw_sf_stage": "Underwriting Submitted"},
    )
    assert audit_id is not None
    row = (
        db_session.query(LoanStateChangeAudit)
        .filter(LoanStateChangeAudit.id == audit_id)
        .one()
    )
    assert row.trigger_source == "salesforce_sync"
    assert row.audit_metadata == {"raw_sf_stage": "Underwriting Submitted"}
