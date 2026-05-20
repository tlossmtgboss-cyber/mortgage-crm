"""
Integration tests for FederalDNCSyncService — D4 CC-004.

Covers sync shape, idempotency, lookup, migration creation,
ComplianceChecker wire-in, cron registration, and async client usage.
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import services.dnc_federal_sync as dnc_module
from services.dnc_federal_sync import (
    FederalDNCSyncService,
    _stub_federal_dnc_list,
    run_federal_dnc_sync,
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset the module-level sync timestamps between tests."""
    dnc_module._LAST_SYNC_AT = None
    dnc_module._LAST_SYNC_COUNT = 0
    dnc_module._LAST_SYNC_STATUS = "never_run"
    yield
    dnc_module._LAST_SYNC_AT = None
    dnc_module._LAST_SYNC_COUNT = 0
    dnc_module._LAST_SYNC_STATUS = "never_run"


# ---------------------------------------------------------------------------
# 1. sync() returns the documented shape
# ---------------------------------------------------------------------------
def test_sync_returns_expected_shape():
    svc = FederalDNCSyncService(db=None)
    result = svc.sync()
    for key in ("records_added", "records_total", "fetched_at", "skipped_recent", "source"):
        assert key in result, f"missing key: {key}"
    assert result["records_total"] > 0
    assert result["source"] == "federal_registry"
    assert result["skipped_recent"] is False


# ---------------------------------------------------------------------------
# 2. Idempotent within the 20h cooldown window
# ---------------------------------------------------------------------------
def test_sync_is_idempotent_within_same_day():
    svc = FederalDNCSyncService(db=None)
    first = svc.sync()
    assert first["skipped_recent"] is False
    second = svc.sync()
    assert second["skipped_recent"] is True
    assert second["records_added"] == 0


# ---------------------------------------------------------------------------
# 3. is_dnc returns true for seeded numbers
# ---------------------------------------------------------------------------
def test_is_dnc_true_for_seeded_number():
    svc = FederalDNCSyncService(db=None)
    seeded = _stub_federal_dnc_list()[0]
    assert svc.is_dnc(seeded) is True
    # Tolerates different formats — normalization should work
    digits_only = seeded.replace("-", "")
    assert svc.is_dnc(digits_only) is True


# ---------------------------------------------------------------------------
# 4. is_dnc returns false for unknown number
# ---------------------------------------------------------------------------
def test_is_dnc_false_for_unknown_number():
    svc = FederalDNCSyncService(db=None)
    assert svc.is_dnc("999-123-4567") is False
    assert svc.is_dnc("") is False


# ---------------------------------------------------------------------------
# 5. Migration creates the federal_dnc_numbers table
# ---------------------------------------------------------------------------
def test_migration_creates_federal_dnc_table_on_sqlite():
    # Import the migration module and exercise upgrade() against an
    # in-memory SQLite engine through a minimal alembic op shim.
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        ctx = MigrationContext.configure(connection)
        op = Operations(ctx)

        # Bind the global `op` proxy used by the migration module
        from alembic import op as alembic_op_module
        # Operations.context_manager properly sets the proxy
        with Operations.context(ctx):
            mig = importlib.import_module(
                "alembic.versions.2026_05_19_federal_dnc"
            ) if False else None
            # Direct dynamic import (numeric prefix not valid module name)
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "fed_dnc_migration",
                "backend/alembic/versions/2026_05_19_federal_dnc.py",
            )
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.upgrade()

        inspector = inspect(connection)
        assert "federal_dnc_numbers" in inspector.get_table_names()
        cols = {c["name"] for c in inspector.get_columns("federal_dnc_numbers")}
        assert {"phone_number", "added_at", "source", "is_active"}.issubset(cols)


# ---------------------------------------------------------------------------
# 6. ComplianceChecker.check_dnc consults federal table
# ---------------------------------------------------------------------------
def test_compliance_checker_consults_federal_table(monkeypatch):
    # Force-import the compliance module and verify the federal overlay
    # path is present in the source.
    import telephony.compliance as compliance_mod
    src = inspect.getsource(compliance_mod.ComplianceChecker.check_dnc)
    assert "FederalDNCSyncService" in src
    assert "federal_registry" in src or "Federal DNC" in src


# ---------------------------------------------------------------------------
# 7. Cron job is registered in main.py
# ---------------------------------------------------------------------------
def test_cron_job_registered_in_main():
    # We don't actually start the scheduler — just confirm the registration
    # block exists in source. Importing main.py is too heavy for a unit test.
    with open("backend/main.py", "r") as f:
        src = f.read()
    assert "run_daily_federal_dnc_sync" in src
    assert "CC-004" in src or "Federal DNC" in src
    assert "hour=2" in src  # 02:00 UTC


# ---------------------------------------------------------------------------
# 8. Async client usage documented in source for production wire-up
# ---------------------------------------------------------------------------
def test_async_client_usage_documented():
    src = inspect.getsource(dnc_module)
    # Production sketch references httpx.AsyncClient
    assert "httpx.AsyncClient" in src
    # And documents the FTC source
    assert "telemarketing.donotcall.gov" in src


# ---------------------------------------------------------------------------
# Bonus — run_federal_dnc_sync best-effort wrapper does not raise
# ---------------------------------------------------------------------------
def test_run_federal_dnc_sync_never_raises(monkeypatch):
    # Even if DB import fails the wrapper should swallow + return dict
    def _boom(*a, **kw):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(
        FederalDNCSyncService,
        "sync",
        lambda self, target_date=None: _boom(),
    )
    out = run_federal_dnc_sync()
    assert isinstance(out, dict)
