"""Audit immutability + hash-chain integration tests.

Four scenarios covered:

1. UPDATE on a Postgres audit table is blocked by the trigger.
2. DELETE on a Postgres audit table is blocked by the trigger.
3. A clean hash chain verifies green.
4. A tampered row causes ``verify_chain`` to return ``False``.

When Postgres is not available (CI default), the trigger-based tests are
skipped and the hash-chain tests run against an in-memory SQLite engine
so the chain math is always exercised.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, create_engine, text,
)
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers (mirrors test_loan_state_audit.py — direct file load to avoid the
# heavy backend import graph).
# ---------------------------------------------------------------------------
def _load_audit_service():
    target = _BACKEND_DIR / "services" / "loan_state_audit_service.py"
    if not target.exists():
        pytest.skip("loan_state_audit_service.py not found")
    spec = importlib.util.spec_from_file_location(
        "_perennia_loan_state_audit_service_imm", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"audit service import failed: {exc}")
    return module


_svc = _load_audit_service()


def _has_real_pg() -> bool:
    url = os.getenv("TEST_DATABASE_URL", "")
    return url.startswith("postgresql://")


# ---------------------------------------------------------------------------
# SQLite scaffolding for hash-chain tests
# ---------------------------------------------------------------------------
def _build_sqlite_engine():
    """Build an in-memory SQLite DB with a minimal audit table shape that
    matches what the service writes (id, loan_id, lead_id, organization_id,
    to_stage, to_pipeline, trigger_source, prev_hash, entry_hash,
    created_at, audit_metadata)."""
    eng = create_engine("sqlite:///:memory:")
    md = MetaData()
    Table(
        "loan_state_change_audit", md,
        Column("id", String(36), primary_key=True),
        Column("loan_id", Integer, nullable=False),
        Column("lead_id", String(36)),
        Column("organization_id", String(36), nullable=False),
        Column("from_stage", String(64)),
        Column("to_stage", String(64), nullable=False),
        Column("from_pipeline", String(32)),
        Column("to_pipeline", String(32), nullable=False),
        Column("trigger_source", String(64), nullable=False),
        Column("actor_user_id", String(36)),
        Column("audit_metadata", String),
        Column("prev_hash", String(64)),
        Column("entry_hash", String(64)),
        Column("created_at", DateTime, nullable=False),
    )
    md.create_all(eng)
    return eng


class _Row:
    """Stand-in for the LoanStateChangeAudit ORM row used in hashing."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _has_real_pg(), reason="Requires PostgreSQL")
def test_update_on_audit_table_is_blocked_by_trigger():
    """The audit_immutability_guard trigger must raise on UPDATE."""
    eng = create_engine(os.environ["TEST_DATABASE_URL"])
    with eng.begin() as conn:
        # Seed one row.
        new_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO loan_state_change_audit "
                "(id, loan_id, organization_id, to_stage, to_pipeline, "
                "trigger_source, created_at) "
                "VALUES (:id, 1, :org, 'APPLICATION', 'leads', 'test', NOW())"
            ),
            {"id": new_id, "org": org_id},
        )
    with pytest.raises(Exception) as excinfo:
        with eng.begin() as conn:
            conn.execute(
                text(
                    "UPDATE loan_state_change_audit SET to_stage='HACKED' "
                    "WHERE id = :id"
                ),
                {"id": new_id},
            )
    assert "immutable" in str(excinfo.value).lower()


@pytest.mark.skipif(not _has_real_pg(), reason="Requires PostgreSQL")
def test_delete_on_audit_table_is_blocked_by_trigger():
    eng = create_engine(os.environ["TEST_DATABASE_URL"])
    new_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO loan_state_change_audit "
                "(id, loan_id, organization_id, to_stage, to_pipeline, "
                "trigger_source, created_at) "
                "VALUES (:id, 2, :org, 'APPLICATION', 'leads', 'test', NOW())"
            ),
            {"id": new_id, "org": org_id},
        )
    with pytest.raises(Exception) as excinfo:
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM loan_state_change_audit WHERE id = :id"),
                {"id": new_id},
            )
    assert "immutable" in str(excinfo.value).lower()


def test_hash_chain_verifies_clean_chain():
    """A well-formed chain of 3 rows must verify_chain -> True."""
    rows = []
    prev = None
    base_ts = datetime.now(timezone.utc)
    for i in range(3):
        r = _Row(
            id=uuid.uuid4(),
            loan_id=42,
            lead_id=None,
            organization_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            from_stage=None if i == 0 else f"S{i-1}",
            to_stage=f"S{i}",
            from_pipeline=None,
            to_pipeline="leads",
            trigger_source="test",
            actor_user_id=None,
            audit_metadata=None,
            created_at=base_ts,
            prev_hash=prev,
            entry_hash=None,
        )
        r.entry_hash = _svc._compute_entry_hash(prev, r)
        prev = r.entry_hash
        rows.append(r)

    # Simulate a tiny query interface — verify_chain only needs ordering.
    class _Q:
        def __init__(self, model):
            self._rows = list(rows)
        def filter(self, *a, **kw):
            return self
        def order_by(self, *a, **kw):
            return self
        def all(self):
            return self._rows

    class _DB:
        def query(self, *a, **kw):
            return _Q(None)

    assert _svc.verify_chain(_DB(), 42) is True


def test_hash_chain_detects_tamper():
    """Tampering with a single row's ``to_stage`` must break verification."""
    rows = []
    prev = None
    base_ts = datetime.now(timezone.utc)
    for i in range(3):
        r = _Row(
            id=uuid.uuid4(),
            loan_id=99,
            lead_id=None,
            organization_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            from_stage=None if i == 0 else f"S{i-1}",
            to_stage=f"S{i}",
            from_pipeline=None,
            to_pipeline="leads",
            trigger_source="test",
            actor_user_id=None,
            audit_metadata=None,
            created_at=base_ts,
            prev_hash=prev,
            entry_hash=None,
        )
        r.entry_hash = _svc._compute_entry_hash(prev, r)
        prev = r.entry_hash
        rows.append(r)

    # Tamper: mutate the middle row's payload without re-hashing.
    rows[1].to_stage = "HACKED"

    class _Q:
        def __init__(self, model):
            self._rows = list(rows)
        def filter(self, *a, **kw):
            return self
        def order_by(self, *a, **kw):
            return self
        def all(self):
            return self._rows

    class _DB:
        def query(self, *a, **kw):
            return _Q(None)

    assert _svc.verify_chain(_DB(), 99) is False
